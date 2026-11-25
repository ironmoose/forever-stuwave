-- Forever STUwave: Config window
-- /fsconfig opens one resizable themed window: a grouped page list on the left, a sub tab strip and a content well on
-- the right, a head band with the brand and the breadcrumb, and a footer band with empty slots. This file is the chrome:
-- the window, the nav, the tabs, the sections that fold, the row registry, the scroll and the extension points other
-- files use. Sizes live in ConfigSpec.lua, the UI.* builders in ConfigBuilders.lua, each page in its ConfigPage*.lua.
-- The window is a plain non-secure frame, so it opens in combat.

local addonName, FS = ...

FS.ConfigWindow = FS.ConfigWindow or {}
local CW = FS.ConfigWindow
CW.UI = CW.UI or {}
CW.I = CW.I or {}
local UI = CW.UI
local I = CW.I

local Theme = FS.Theme
local Config = FS.Config
local S = CW.Spec
local D = CW.D
local C = CW.C

-------------------------------------------------------------------------------
-- Constants
-------------------------------------------------------------------------------

local FRAME_NAME = "ForeverSTUwaveConfig"
-- Each tab page scrolls inside a ScrollFrame that reaches PAD_X to the sides and PAD_TOP / PAD_BOT beyond the content
-- area, so a button glow is not clipped.
local PAD_X, PAD_TOP, PAD_BOT = 8, 6, 4
local WHEEL_STEP = 42
local THUMB_MIN_H, BAR_HIT = 24, 4     -- BAR_HIT: invisible hit area added to each side of the bar and thumb
local GRIP = 16
local NAV_GROUPS = { "FRAMES", "SCREEN", "PANELS", "GENERAL" }
local DEFAULT_GROUP = "GENERAL"
local ALIASES = { unitframes = "unit" }     -- page keys the first release used

local categories = {}        -- key -> { key, label, group, order, tabs = { { key, label, build, tip } } }
local sorted = {}            -- the same, by group then order then key
local ui = { tabs = {}, strips = {}, nav = {}, groups = {} }
local controls = {}          -- refresh functions of every control built
local cursors = setmetatable({}, { __mode = "k" })
local registry = {}          -- every row builder run, in build order
local extensions = {}        -- "page/tab" -> list of { fn, order, title }
local handlers = {}          -- event -> list of functions
local menuState, dialogState = {}, {}
I.menuState, I.dialogState = menuState, dialogState
I.ui, I.controls, I.registry = ui, controls, registry

-------------------------------------------------------------------------------
-- Small helpers (shared with the builders through CW.I)
-------------------------------------------------------------------------------

local function Forward(err)
    if FS.Layout and FS.Layout.ForwardError then
        FS.Layout.ForwardError(err)
    elseif type(geterrorhandler) == "function" then
        geterrorhandler()(err)
    end
end

local function Writable() return not Config.IsReadOnly() end

local function Capitalize(text)
    text = tostring(text or "")
    return (text:gsub("^%l", string.upper))
end

local function Say(text)
    print("|cffff4488Forever STUwave|r: " .. Capitalize(text))
end

local function Mix(a, b, t)
    return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t, 1 }
end

local function Tint(texture, color, alpha)
    if texture then texture:SetVertexColor(color[1], color[2], color[3], alpha or color[4] or 1) end
end

local function Label(parent, text, size, color)
    local fs = parent:CreateFontString(nil, "OVERLAY")
    Theme.ApplyMono(fs, size, color)
    fs:SetText(text)
    return fs
end

-- One pixel edges around a frame, as a list so a caller can retint them.
local function Outline(frame, color, alpha)
    local edges = {}
    local function edge(p1, p2, horizontal)
        local t = frame:CreateTexture(nil, "BORDER")
        t:SetColorTexture(color[1], color[2], color[3], alpha or 1)
        t:SetPoint(p1, frame, p1, 0, 0)
        t:SetPoint(p2, frame, p2, 0, 0)
        if horizontal then t:SetHeight(1) else t:SetWidth(1) end
        edges[#edges + 1] = t
    end
    edge("TOPLEFT", "TOPRIGHT", true)
    edge("BOTTOMLEFT", "BOTTOMRIGHT", true)
    edge("TOPLEFT", "BOTTOMLEFT", false)
    edge("TOPRIGHT", "BOTTOMRIGHT", false)
    return edges
end

-- A filled circle of `size` units from four of Theme's quarter discs meeting at the frame centre.
local DISC_QUADS = {
    { "BOTTOMRIGHT", 0, 1, 0, 1 }, { "BOTTOMLEFT", 1, 0, 0, 1 },
    { "TOPRIGHT", 0, 1, 1, 0 }, { "TOPLEFT", 1, 0, 1, 0 },
}
local function Disc(frame, size, color, sublevel)
    local quads = {}
    for _, q in ipairs(DISC_QUADS) do
        local t = frame:CreateTexture(nil, "ARTWORK", nil, sublevel)
        t:SetTexture(Theme.FILL_CORNER_TEXTURE)
        t:SetSize(size / 2, size / 2)
        t:SetPoint(q[1], frame, "CENTER", 0, 0)
        t:SetTexCoord(q[2], q[3], q[4], q[5])
        t:SetVertexColor(color[1], color[2], color[3], color[4] or 1)
        quads[#quads + 1] = t
    end
    return quads
end

local function TintAll(list, color)
    for _, t in ipairs(list) do Tint(t, color) end
end

-- A row switched off by its `needs` / `enabled` (ConfigBuilders.lua) marks itself fsRowOff; every control under it reads
-- as disabled, whatever its own refresh says.
local function RowOff(frame)
    local p = frame
    while p do
        if p.fsRowOff then return true end
        p = p.GetParent and p:GetParent() or nil
    end
    return false
end
I.RowOff = RowOff

local function SetLook(control, on)
    if on and RowOff(control) then on = false end
    if on then control:Enable() else control:Disable() end
    control:SetAlpha(on and 1 or 0.4)
end

-- One function per row that can be switched off: RefreshAll runs these first, so the controls' own refreshes see the state.
local rowStates = {}
I.rowStates = rowStates

-- Every control registers one refresh function; RefreshAll runs them all.
local function Track(fn)
    controls[#controls + 1] = fn
    fn()
end

I.Forward, I.Writable, I.Capitalize, I.Say = Forward, Writable, Capitalize, Say
I.Mix, I.Tint, I.Label, I.Outline, I.Disc, I.TintAll = Mix, Tint, Label, Outline, Disc, TintAll
I.SetLook, I.Track = SetLook, Track

-------------------------------------------------------------------------------
-- Events: CW.On(event, fn)
-------------------------------------------------------------------------------

-- "show", "hide", "select" (page, tab), "rowEnter" / "rowLeave" (the registry row), "change" (key, new, old).
function CW.On(event, fn)
    if type(event) ~= "string" or type(fn) ~= "function" then return false end
    handlers[event] = handlers[event] or {}
    table.insert(handlers[event], fn)
    return true
end

local function Fire(event, ...)
    for _, fn in ipairs(handlers[event] or {}) do
        local ok, err = pcall(fn, ...)
        if not ok then Forward(err) end
    end
end
I.Fire = Fire

-------------------------------------------------------------------------------
-- Account wide window state (size, folded sections, the class strip), kept outside every profile
-------------------------------------------------------------------------------

local memoryState = {}

local function StateTable()
    local db = _G.ForeverSTUwaveDB
    if type(db) == "table" and not Config.IsReadOnly() then
        if type(db.ui) ~= "table" then db.ui = {} end
        return db.ui
    end
    return memoryState
end

-- CW.UIState(key) reads; CW.UIState(key, value) writes. A nil value clears. Never a profile setting.
function CW.UIState(key, ...)
    if type(key) ~= "string" then return nil end
    local t = StateTable()
    if select("#", ...) > 0 then
        t[key] = (...)
        return (...)
    end
    return t[key]
end

local function FoldTable()
    local t = StateTable()
    if type(t.folds) ~= "table" then t.folds = {} end
    return t.folds
end

-------------------------------------------------------------------------------
-- Flow: rows are recorded in build order and laid out again whenever one hides, folds or the window resizes
-------------------------------------------------------------------------------

local function FlowOwner(frame)
    while frame do
        if frame.fsFlow then return frame end
        frame = frame:GetParent()
    end
end

local function TabRecOf(frame)
    local owner = FlowOwner(frame)
    return owner and owner.fsTabRec
end

I.FlowOwner, I.TabRecOf = FlowOwner, TabRecOf

local function Cursor(content)
    local c = cursors[content]
    if not c then
        c = { y = 0 }
        cursors[content] = c
    end
    return c
end

-- Seats `frame` as the next row of `content`. A frame with `fsStretch` set, or at most 1 wide, stretches across the
-- page; half = "left" or "right" places two rows side by side. A two column section pairs its rows on its own.
function UI.Stack(content, frame, half)
    local owner = FlowOwner(content)
    if not owner then
        owner = content
        owner.fsFlow = owner.fsFlow or {}
    end
    local item = { frame = frame, half = half, section = owner.fsSectionCur, when = frame.fsWhen, kind = "row" }
    frame.fsItem = item
    owner.fsFlow[#owner.fsFlow + 1] = item
    local c = Cursor(owner)
    c.dirty = true
    if owner.fsTabRec and owner.fsTabRec.built then I.Reflow(owner) end      -- a row added to a built tab
    return frame
end

function UI.StackHeader(content, frame, section)
    local owner = FlowOwner(content)
    if not owner then
        owner = content
        owner.fsFlow = owner.fsFlow or {}
    end
    local item = { frame = frame, kind = "header", section = section, when = section.when }
    frame.fsItem = item
    section.item = item
    owner.fsSectionCur = section
    owner.fsFlow[#owner.fsFlow + 1] = item
    return frame
end

local function ItemVisible(item)
    local sec = item.section
    if item.hidden then return false end
    if sec then
        if sec.hidden then return false end
        if sec.folded and item.kind ~= "header" then return false end
    end
    return true
end

-- Positions every visible item below the previous one and sizes the holder to what they take.
function I.Reflow(owner)
    local flow = owner.fsFlow
    if not flow then return end
    local y, pending, sawVisible = 0, nil, false
    local secCount = {}
    for _, item in ipairs(flow) do
        local frame, sec = item.frame, item.section
        local visible = ItemVisible(item)
        frame:SetShown(visible)
        if visible then
            frame:ClearAllPoints()
            local h = frame:GetHeight()
            if item.kind == "header" then
                if pending then y = y + pending; pending = nil end
                if sawVisible then y = y + S.SEC_GAP end
                frame:SetPoint("TOPLEFT", owner, "TOPLEFT", 0, -y)
                frame:SetPoint("TOPRIGHT", owner, "TOPRIGHT", 0, -y)
                item.y = y
                y = y + h
            else
                local half = item.half
                if sec and sec.two then
                    secCount[sec] = (secCount[sec] or 0) + 1
                    half = secCount[sec] % 2 == 1 and "left" or "right"
                end
                if half then
                    frame:SetWidth(D.HALF_W)
                    frame:SetPoint("TOPLEFT", owner, "TOPLEFT", half == "left" and 0 or D.HALF_W + S.HALF_GAP, -y)
                    item.y = y
                    if half == "left" then
                        pending = h
                    else
                        y = y + math.max(h, pending or 0)
                        pending = nil
                    end
                else
                    if pending then y = y + pending; pending = nil end
                    frame:SetPoint("TOPLEFT", owner, "TOPLEFT", 0, -y)
                    if frame.fsStretch or frame:GetWidth() <= 1 then frame:SetPoint("TOPRIGHT", owner, "TOPRIGHT", 0, -y) end
                    item.y = y
                    y = y + h
                end
            end
            sawVisible = true
        end
    end
    if pending then y = y + pending end
    local c = Cursor(owner)
    c.y, c.pending, c.dirty = y, nil, false
    owner:SetHeight(math.max(y, 1))
    local rec = owner.fsTabRec
    if rec then rec.total = y end
end

-- Re-reads every `when` of the tab; true when something showed or hid.
function I.EvalWhens(owner)
    local changed = false
    for _, item in ipairs(owner.fsFlow or {}) do
        if item.when then
            local ok, value = pcall(item.when)
            local hide = ok and not value
            if item.kind == "header" then
                if (item.section.hidden == true) ~= hide then item.section.hidden = hide; changed = true end
            elseif (item.hidden == true) ~= hide then
                item.hidden = hide
                changed = true
            end
        end
    end
    return changed
end

-------------------------------------------------------------------------------
-- Scrolling
-------------------------------------------------------------------------------

local function ShiftHeld()
    return type(IsShiftKeyDown) == "function" and IsShiftKeyDown() == true
end

local function ViewH()
    local rec = ui.tabRec
    local band = rec and rec.bandH or 0
    return math.max(1, D.SCROLL_H + (ui.stripH and 0 or S.TAB_STRIP_H) - S.CONTENT_T - S.CONTENT_B - band)
end

-- The nearest scroll page at or above `frame` (a builder's content may be a sub-frame of the page holder).
local function FindScrollPage(frame)
    while frame do
        if frame.fsScrollPage then return frame.fsScrollPage end
        frame = frame:GetParent()
    end
end

local function MeasurePage(page)
    local owner = page.fsHolder
    local y = Cursor(owner).y
    owner:SetHeight(math.max(y, 1))
    page.fsChild:SetHeight(y + PAD_TOP + PAD_BOT)
    page.fsRange = math.max(0, y - ViewH())
end

-- The slim bar in the well's right margin: shown only while the current tab overflows.
local function UpdateBar()
    local bar = ui.bar
    if not bar then return end
    local page = ui.tabRec and ui.tabRec.page
    local range = page and page.fsRange or 0
    if range <= 0 then
        bar:Hide()
        return
    end
    local view = ViewH()
    local thumb = bar.fsThumb
    local height = math.max(THUMB_MIN_H, math.floor(view * view / (view + range)))
    local travel = view - height
    thumb:SetHeight(height)
    thumb:ClearAllPoints()
    thumb:SetPoint("TOP", bar, "TOP", 0, -math.floor(travel * page:GetVerticalScroll() / range + 0.5))
    bar:Show()
end

local function SetScroll(page, value)
    value = math.min(page.fsRange or 0, math.max(0, value))
    if value == page:GetVerticalScroll() then return end
    page:SetVerticalScroll(value)
    -- An open dropdown menu follows its button, which just moved; close it rather than let it hang off the panel.
    I.CloseMenu()
    local owner = GameTooltip:GetOwner()
    while owner and owner ~= page do owner = owner:GetParent() end
    if owner then GameTooltip:Hide() end
    if ui.tabRec and ui.tabRec.page == page then UpdateBar() end
end

local function ScrollBy(page, delta)
    SetScroll(page, page:GetVerticalScroll() - delta * WHEEL_STEP)
end

I.FindScrollPage, I.ScrollBy, I.ShiftHeld = FindScrollPage, ScrollBy, ShiftHeld

-- Re-measures the page after its rows changed height or the window came back: a new range, the offset kept inside it.
local function Remeasure(page)
    MeasurePage(page)
    SetScroll(page, page:GetVerticalScroll())
    if ui.tabRec and ui.tabRec.page == page then UpdateBar() end
end

-- Call after a builder adds or removes rows on a tab that is already built.
function CW.RefreshScroll()
    local rec = ui.tabRec
    if rec and rec.page then
        I.Reflow(rec.page.fsHolder)
        Remeasure(rec.page)
    end
end

-- One ScrollFrame per tab; builders stack into `fsHolder`, a frame inset by PAD_X inside the scroll child.
local function NewTabPage(rec)
    local page = CreateFrame("ScrollFrame", nil, ui.content)
    page:SetPoint("TOPLEFT", ui.content, "TOPLEFT", -PAD_X, PAD_TOP)
    page:SetPoint("BOTTOMRIGHT", ui.content, "BOTTOMRIGHT", PAD_X, -PAD_BOT)
    page:SetClipsChildren(true)
    page:EnableMouseWheel(true)
    page.fsPageKey = rec.cat.key
    local child = CreateFrame("Frame", nil, page)
    child:SetSize(D.CONTENT_W + 2 * PAD_X, 1)
    page:SetScrollChild(child)
    local holder = CreateFrame("Frame", nil, child)
    holder:SetWidth(D.CONTENT_W)
    holder:SetPoint("TOPLEFT", child, "TOPLEFT", PAD_X, -PAD_TOP)
    holder.fsScrollPage = page
    holder.fsFlow = {}
    holder.fsTabRec = rec
    page.fsChild, page.fsHolder, page.fsRange = child, holder, 0
    page:SetScript("OnMouseWheel", function(self, delta) ScrollBy(self, delta) end)
    return page
end

local function BuildScrollbar(well)
    local bar = CreateFrame("Frame", nil, well)
    bar.fsScrollbar = true
    bar:SetWidth(S.BAR_W)
    bar:SetPoint("TOPRIGHT", well, "TOPRIGHT", -S.BAR_INSET, -S.CONTENT_T)
    bar:SetPoint("BOTTOMRIGHT", well, "BOTTOMRIGHT", -S.BAR_INSET, S.CONTENT_B)
    -- A click on the rail jumps the thumb under the cursor (a click on the thumb itself starts a drag instead).
    bar:EnableMouse(true)
    bar:SetHitRectInsets(-BAR_HIT, -BAR_HIT, 0, 0)
    bar:SetScript("OnMouseDown", function(self, button)
        if button ~= "LeftButton" then return end
        local page = ui.tabRec and ui.tabRec.page
        local top = self:GetTop()
        if not (page and (page.fsRange or 0) > 0 and top) then return end
        local _, y = GetCursorPosition()
        local travel = ViewH() - self.fsThumb:GetHeight()
        if travel <= 0 then return end
        local thumbTop = (top - y / self:GetEffectiveScale()) - self.fsThumb:GetHeight() / 2
        SetScroll(page, thumbTop / travel * page.fsRange)
    end)
    bar:EnableMouseWheel(true)
    bar:SetScript("OnMouseWheel", function(_, delta)
        local page = ui.tabRec and ui.tabRec.page
        if page then ScrollBy(page, delta) end
    end)
    local rail = bar:CreateTexture(nil, "BACKGROUND")
    rail:SetColorTexture(C.violet[1], C.violet[2], C.violet[3], 0.25)
    rail:SetWidth(1)
    rail:SetPoint("TOP", bar, "TOP", 0, 0)
    rail:SetPoint("BOTTOM", bar, "BOTTOM", 0, 0)
    local thumb = CreateFrame("Frame", nil, bar)
    thumb:SetSize(S.BAR_W, THUMB_MIN_H)
    thumb:SetPoint("TOP", bar, "TOP", 0, 0)
    thumb:EnableMouse(true)
    thumb:SetHitRectInsets(-BAR_HIT, -BAR_HIT, 0, 0)
    local fill = thumb:CreateTexture(nil, "ARTWORK")
    fill:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 0.85)
    fill:SetAllPoints(thumb)
    bar.fsThumb = thumb
    -- Dragging maps the cursor's travel over the track to the page's scroll range.
    local startY, startScroll
    local function StopDrag()
        startY = nil
        thumb:SetScript("OnUpdate", nil)
    end
    thumb:SetScript("OnMouseDown", function(self, button)
        if button ~= "LeftButton" then return end
        local page = ui.tabRec and ui.tabRec.page
        if not (page and page.fsRange > 0) then return end
        local _, y = GetCursorPosition()
        startY, startScroll = y / self:GetEffectiveScale(), page:GetVerticalScroll()
        self:SetScript("OnUpdate", function()
            local _, now = GetCursorPosition()
            local travel = ViewH() - self:GetHeight()
            if not startY or travel <= 0 then return end
            SetScroll(page, startScroll + (startY - now / self:GetEffectiveScale()) * page.fsRange / travel)
        end)
    end)
    thumb:SetScript("OnMouseUp", StopDrag)
    thumb:SetScript("OnHide", StopDrag)
    bar:Hide()
    ui.bar = bar
end

-------------------------------------------------------------------------------
-- Pinned band: a frame that sticks to the top of the scroll area while the tab scrolls beneath it
-------------------------------------------------------------------------------

-- UI.Band(content, height) returns a frame the tab's builder fills (a preview, a role bar). One per tab.
function UI.Band(content, height)
    local rec = TabRecOf(content)
    if not rec then return nil end
    height = height or 64
    if not rec.band then
        rec.band = CreateFrame("Frame", nil, ui.content)
        rec.band:SetPoint("TOPLEFT", ui.content, "TOPLEFT", 0, 0)
        rec.band:SetPoint("TOPRIGHT", ui.content, "TOPRIGHT", 0, 0)
        rec.band.fsBand = true
        local rule = rec.band:CreateTexture(nil, "ARTWORK")
        rule:SetColorTexture(C.line[1], C.line[2], C.line[3], 1)
        rule:SetHeight(1)
        rule:SetPoint("BOTTOMLEFT", rec.band, "BOTTOMLEFT", -S.CONTENT_L, 0)
        rule:SetPoint("BOTTOMRIGHT", rec.band, "BOTTOMRIGHT", S.CONTENT_R, 0)
        rec.band.fsRule = rule
    end
    rec.band:SetHeight(height)
    rec.bandH = height + 8
    rec.band:SetShown(ui.tabRec == rec)
    I.PlaceTabPage(rec)
    return rec.band
end

function I.PlaceTabPage(rec)
    if not rec.page then return end
    rec.page:ClearAllPoints()
    rec.page:SetPoint("TOPLEFT", ui.content, "TOPLEFT", -PAD_X, PAD_TOP - (rec.bandH or 0))
    rec.page:SetPoint("BOTTOMRIGHT", ui.content, "BOTTOMRIGHT", PAD_X, -PAD_BOT)
end

-------------------------------------------------------------------------------
-- Row registry
-------------------------------------------------------------------------------

-- Every builder records its row here: { key, label, tip, page, tab, section, row, sub, needs, reason, enabled, reload,
-- min, max, target, when, inverted, nodot, kind }.
function I.Register(row, o, kind)
    local rec = TabRecOf(row:GetParent() or row)
    local owner = row:GetParent() and FlowOwner(row:GetParent())
    local sec = owner and owner.fsSectionCur
    local entry = {
        key = o.regKey or o.key, label = o.label, tip = o.tip, kind = kind,
        page = rec and rec.cat.key, tab = rec and rec.def.key, section = sec and sec.title,
        row = row, sub = o.sub == true, needs = o.needs, reason = o.reason or (o.nl and ("Needs " .. o.nl) or nil),
        enabled = o.enabled, reload = o.reload, min = o.min, max = o.max, target = o.target, when = o.when,
        inverted = o.inverted == true, nodot = o.nodot == true,
        secObj = sec, cfgKey = o.key, isChanged = o.isChanged, resetFn = o.reset,
    }
    row.fsEntry = entry
    registry[#registry + 1] = entry
    return entry
end

function CW.Rows()
    return registry
end

-- Changed state: a keyed row differs from its default when the active profile stores a value for it; a row built with
-- get/set opts in with isChanged / reset functions; `nodot` rows (pickers) never count.
function I.EntryChanged(entry)
    if entry.nodot or entry.kind == "note" then return false end
    if entry.cfgKey then return Config.IsStored(entry.cfgKey) end
    if entry.isChanged then
        local ok, value = pcall(entry.isChanged)
        return ok and value == true
    end
    return false
end

function I.EntryReset(entry)
    if entry.resetFn then
        local ok, err = pcall(entry.resetFn)
        if not ok then Forward(err) end
    elseif entry.cfgKey then
        Config.Set(entry.cfgKey, nil)
    end
end

-- The keys of the changed rows of a page (and tab), for the page reset and the search. Only built tabs have rows.
function CW.ChangedKeys(page, tab)
    page = ALIASES[page] or page
    local list = {}
    for _, entry in ipairs(registry) do
        if (page == nil or entry.page == page) and (tab == nil or entry.tab == tab) and I.EntryChanged(entry) then
            list[#list + 1] = entry.cfgKey or entry.key or entry.label
        end
    end
    return list
end

-- One write per key (a registry row resets by its own function), then one refresh.
function CW.ResetKeys(list)
    for _, key in ipairs(list or {}) do
        local entry
        for _, e in ipairs(registry) do
            if e.cfgKey == key or e.key == key then entry = e break end
        end
        if entry then I.EntryReset(entry) else Config.Set(key, nil) end
    end
    CW.RefreshAll()
end

-- Repaints every changed marker: the row dots and resets (their own refresh), the section chips, the tab dots, the nav dots.
function I.UpdateChanged()
    local sections, tabs, pages = {}, {}, {}
    for _, entry in ipairs(registry) do
        if I.EntryChanged(entry) then
            if entry.secObj then sections[entry.secObj] = (sections[entry.secObj] or 0) + 1 end
            tabs[entry.page .. "/" .. entry.tab] = (tabs[entry.page .. "/" .. entry.tab] or 0) + 1
            pages[entry.page] = (pages[entry.page] or 0) + 1
        end
    end
    for _, entry in ipairs(registry) do
        local sec = entry.secObj
        if sec and sec.SetChanged then sec.SetChanged(sections[sec] or 0) end
    end
    for key, strip in pairs(ui.strips) do
        for _, b in ipairs(strip.fsButtons or {}) do
            if b.fsDot then b.fsDot:SetShown((tabs[key .. "/" .. b.fsTabKey] or 0) > 0) end
        end
    end
    for key, b in pairs(ui.nav) do
        if b.fsNdot then b.fsNdot:SetShown((pages[key] or 0) > 0) end
    end
end

function CW.RowByKey(key, page)
    for _, entry in ipairs(registry) do
        if entry.key == key and (page == nil or entry.page == page) then return entry end
    end
end

-- Hover: one poll while the window is up, so a row and the controls on it count as one place.
local function SetHover(entry)
    if ui.hover == entry then return end
    local old = ui.hover
    ui.hover = entry
    if old then Fire("rowLeave", old) end
    if entry then Fire("rowEnter", entry) end
end
I.SetHover = SetHover
CW.SetHover = SetHover

local function PollHover()
    local rec = ui.tabRec
    if not (rec and rec.page and ui.frame and ui.frame:IsShown()) then return SetHover(nil) end
    local found
    for _, entry in ipairs(registry) do
        local row = entry.row
        if entry.page == rec.cat.key and entry.tab == rec.def.key and row:IsShown() and type(row.IsMouseOver) == "function"
            and row:IsMouseOver() then
            found = entry
            break
        end
    end
    SetHover(found)
end

-------------------------------------------------------------------------------
-- Categories
-------------------------------------------------------------------------------

local function GroupRank(group)
    for i, name in ipairs(NAV_GROUPS) do
        if name == group then return i end
    end
    return #NAV_GROUPS + 1
end

local function SortCategories()
    sorted = {}
    for _, cat in pairs(categories) do sorted[#sorted + 1] = cat end
    table.sort(sorted, function(a, b)
        local ga, gb = GroupRank(a.group), GroupRank(b.group)
        if ga ~= gb then return ga < gb end
        if a.group ~= b.group then return a.group < b.group end
        if a.order ~= b.order then return a.order < b.order end
        return a.key < b.key
    end)
end

local function Squash(text)
    return (tostring(text or ""):lower():gsub("%s+", ""))
end

local function ResolveCategory(name)
    if name == nil then return nil end
    name = ALIASES[name] or name
    if categories[name] then return categories[name] end
    local want = Squash(name)
    for _, cat in ipairs(sorted) do
        if Squash(cat.key) == want or Squash(cat.label) == want then return cat end
    end
end

local function ResolveTab(cat, name)
    if not cat or name == nil then return nil end
    local want = Squash(name)
    for _, tab in ipairs(cat.tabs) do
        if tab.key == name or Squash(tab.key) == want or Squash(tab.label) == want then return tab end
    end
end

local function TabRec(cat, def)
    local id = cat.key .. "/" .. def.key
    local rec = ui.tabs[id]
    if not rec then
        rec = { cat = cat, def = def, id = id }
        ui.tabs[id] = rec
    end
    rec.def, rec.cat = def, cat
    return rec
end

-- {key, label, group, order, tabs = { {key, label, build, tip}, ... }}; a plain `build` fn is one tab named for the page.
-- Registering a key again updates its label, group and order, and the tabs not yet built; a built tab is never rebuilt.
function CW.RegisterCategory(spec)
    if type(spec) ~= "table" or type(spec.key) ~= "string" or spec.key == "" then return false end
    local tabs = {}
    if type(spec.tabs) == "table" and #spec.tabs > 0 then
        for _, t in ipairs(spec.tabs) do
            if type(t) ~= "table" or type(t.key) ~= "string" or type(t.build) ~= "function" then return false end
            tabs[#tabs + 1] = { key = t.key, label = tostring(t.label or t.key), build = t.build, tip = t.tip }
        end
    elseif type(spec.build) == "function" then
        tabs[1] = { key = "main", label = tostring(spec.label or spec.key), build = spec.build }
    else
        return false
    end
    local group = type(spec.group) == "string" and spec.group:upper() or DEFAULT_GROUP
    local old = categories[spec.key]
    if old then
        -- keep a built tab's definition: it is never rebuilt
        for i, t in ipairs(tabs) do
            local rec = ui.tabs[spec.key .. "/" .. t.key]
            if rec and rec.built then tabs[i] = rec.def end
        end
    end
    categories[spec.key] = {
        key = spec.key, label = tostring(spec.label or spec.key), group = group, order = tonumber(spec.order) or 100,
        tabs = tabs,
    }
    SortCategories()
    if ui.frame then I.LayoutNav() end
    return true
end

function CW.Categories()
    local list = {}
    for i, cat in ipairs(sorted) do
        local tabs = {}
        for j, t in ipairs(cat.tabs) do tabs[j] = { key = t.key, label = t.label } end
        list[i] = { key = cat.key, label = cat.label, order = cat.order, group = cat.group, tabs = tabs }
    end
    return list
end

-- CW.ExtendTab(page, tab, sectionTitle, buildFn, order): another file adds a section to a tab. `sectionTitle` is the
-- section's title (or a table {title, tip, fold, two, meta, when}); buildFn(content, section) builds its rows. Order 0 is
-- the tab's own content: below 0 builds before it, above after it. A tab already built gets the section at the end.
function CW.ExtendTab(page, tab, sectionTitle, buildFn, order)
    if type(page) ~= "string" or type(tab) ~= "string" or type(buildFn) ~= "function" then return false end
    page = ALIASES[page] or page
    local id = page .. "/" .. tab
    extensions[id] = extensions[id] or {}
    local ext = { fn = buildFn, order = tonumber(order) or 100, title = sectionTitle, seq = #extensions[id] + 1 }
    table.insert(extensions[id], ext)
    local rec = ui.tabs[id]
    if rec and rec.built and rec.page then I.RunExtension(rec, ext) end
    return true
end

-------------------------------------------------------------------------------
-- Building a tab
-------------------------------------------------------------------------------

function I.RunExtension(rec, ext)
    local holder = rec.page.fsHolder
    local ok, err = pcall(function()
        local section
        if ext.title ~= nil then
            local opts = type(ext.title) == "table" and ext.title or { title = tostring(ext.title) }
            section = UI.Section(holder, opts)
        end
        ext.fn(holder, section)
    end)
    if not ok then Forward(err) end
    if rec.built then I.Reflow(holder) end
end

local function BuildTab(rec)
    local page = NewTabPage(rec)
    rec.page = page
    local steps = { { order = 0, seq = 0, fn = function() rec.def.build(page.fsHolder) end } }
    for _, ext in ipairs(extensions[rec.id] or {}) do steps[#steps + 1] = { order = ext.order, seq = ext.seq, ext = ext } end
    table.sort(steps, function(a, b)
        if a.order ~= b.order then return a.order < b.order end
        return a.seq < b.seq
    end)
    for _, step in ipairs(steps) do
        if step.ext then
            I.RunExtension(rec, step.ext)
        else
            local ok, err = pcall(step.fn)
            if not ok then Forward(err) end
        end
    end
    rec.built = true
    I.EvalWhens(page.fsHolder)
    I.Reflow(page.fsHolder)
    I.PlaceTabPage(rec)
    return page
end

-------------------------------------------------------------------------------
-- Window chrome
-------------------------------------------------------------------------------

local function Version()
    local get = _G.C_AddOns and _G.C_AddOns.GetAddOnMetadata or _G.GetAddOnMetadata
    if type(get) ~= "function" then return nil end
    local ok, value = pcall(get, addonName, "Version")
    if ok and type(value) == "string" and value ~= "" then return value end
end

local function SetSelected(key)
    for k, b in pairs(ui.nav) do
        local selected = k == key
        b.fsSelected = selected
        b.fsHighlight:SetShown(selected)
        b.fsBar:SetShown(selected)
        Theme.ApplyMono(b.fsLabel, S.TEXT, selected and C.cyan or C.muted)
    end
end

-- Tab buttons: width is the text rounded up to TEXT_SNAP; the active one cyan with a pink underline.
local function PaintTabs(strip)
    for _, b in ipairs(strip.fsButtons) do
        local on = b.fsTabKey == ui.tab
        b.fsSelected = on
        b.fsUnderline:SetShown(on)
        local color = on and C.cyan or (b.fsHover and C.text or C.muted)
        if b.fsDisabled then color = C.line end
        Theme.ApplyMono(b.fsLabel, S.TEXT, color)
    end
end

local function BuildStrip(cat)
    local strip = CreateFrame("Frame", nil, ui.well)
    strip:SetHeight(S.TAB_STRIP_H)
    strip:SetPoint("TOPLEFT", ui.well, "TOPLEFT", 0, 0)
    strip:SetPoint("TOPRIGHT", ui.well, "TOPRIGHT", 0, 0)
    local rule = strip:CreateTexture(nil, "ARTWORK")
    rule:SetColorTexture(C.line[1], C.line[2], C.line[3], 1)
    rule:SetHeight(1)
    rule:SetPoint("BOTTOMLEFT", strip, "BOTTOMLEFT", 0, 0)
    rule:SetPoint("BOTTOMRIGHT", strip, "BOTTOMRIGHT", 0, 0)
    strip.fsButtons = {}
    local x = S.CONTENT_L
    for _, def in ipairs(cat.tabs) do
        local b = CreateFrame("Button", nil, strip)
        b:RegisterForClicks("LeftButtonUp")
        b.fsTabKey = def.key
        b.fsLabel = Label(b, def.label, S.TEXT, C.muted)
        b.fsLabel:SetPoint("LEFT", b, "LEFT", S.TAB_PAD_X, 0)
        local width = (b.fsLabel:GetStringWidth() or 0) + 2 * S.TAB_PAD_X
        if def.tip then
            b.fsHelp = UI.HelpIcon(b, def.tip)
            b.fsHelp:SetPoint("LEFT", b.fsLabel, "RIGHT", S.Q_GAP, 0)
            width = width + S.Q + S.Q_GAP + S.TAB_PAD_X
        end
        width = S.Snap(width)
        b:SetSize(width, S.TAB_H)
        b:SetPoint("BOTTOMLEFT", strip, "BOTTOMLEFT", x, 0)
        x = x + width + S.TAB_GAP
        b.fsDot = b:CreateTexture(nil, "OVERLAY")
        b.fsDot:SetColorTexture(C.pink[1], C.pink[2], C.pink[3], 1)
        b.fsDot:SetSize(S.DOT, S.DOT)
        b.fsDot:SetPoint("TOPRIGHT", b, "TOPRIGHT", -4, -6)
        b.fsDot:Hide()
        b.fsUnderline = b:CreateTexture(nil, "ARTWORK")
        b.fsUnderline:SetColorTexture(C.pink[1], C.pink[2], C.pink[3], 1)
        b.fsUnderline:SetHeight(S.TAB_LINE_H)
        b.fsUnderline:SetPoint("BOTTOMLEFT", b, "BOTTOMLEFT", S.TAB_PAD_X / 2, 0)
        b.fsUnderline:SetPoint("BOTTOMRIGHT", b, "BOTTOMRIGHT", -S.TAB_PAD_X / 2, 0)
        b:SetScript("OnEnter", function(self) self.fsHover = true; PaintTabs(strip) end)
        b:SetScript("OnLeave", function(self) self.fsHover = false; PaintTabs(strip) end)
        b:SetScript("OnMouseDown", function(self) if self:IsEnabled() then Theme.ApplyMono(self.fsLabel, S.TEXT, C.cyan) end end)
        b:SetScript("OnClick", function(self)
            if not self:IsEnabled() then return end
            CW.Open(cat.key, def.key)
        end)
        strip.fsButtons[#strip.fsButtons + 1] = b
    end
    strip:Hide()
    return strip
end

-- Seats the content area under the tab strip (or the top of the well when the page has one tab).
local function PlaceContent()
    ui.content:ClearAllPoints()
    local top = (ui.stripH and S.TAB_STRIP_H or 0) + S.CONTENT_T
    ui.content:SetPoint("TOPLEFT", ui.well, "TOPLEFT", S.CONTENT_L, -top)
    ui.content:SetPoint("BOTTOMRIGHT", ui.well, "BOTTOMRIGHT", -S.CONTENT_R, S.CONTENT_B)
end

local function UpdateCrumb(cat, tab)
    local text = "|cff22e0ff" .. cat.label:upper() .. "|r"
    if tab and #cat.tabs > 1 then text = text .. " / " .. tab.label:upper() end
    ui.crumb:SetText(text)
end

local function Select(cat, tab)
    if not cat then return end
    local changedPage = ui.current ~= cat.key
    tab = tab or ResolveTab(cat, ui.tabFor and ui.tabFor[cat.key]) or cat.tabs[1]
    local changedTab = changedPage or ui.tab ~= tab.key
    ui.current, ui.tab = cat.key, tab.key
    ui.tabFor = ui.tabFor or {}
    ui.tabFor[cat.key] = tab.key
    -- the strip
    for key, strip in pairs(ui.strips) do strip:SetShown(key == cat.key and #cat.tabs > 1) end
    ui.stripH = #cat.tabs > 1 or nil
    if ui.stripH then
        local strip = ui.strips[cat.key]
        if not strip then
            strip = BuildStrip(cat)
            ui.strips[cat.key] = strip
        end
        strip:Show()
        PaintTabs(strip)
    end
    PlaceContent()
    -- the page
    local rec = TabRec(cat, tab)
    for _, other in pairs(ui.tabs) do
        if other ~= rec then
            if other.page then other.page:Hide() end
            if other.band then other.band:Hide() end
        end
    end
    ui.tabRec = rec
    if not rec.page then BuildTab(rec) end
    I.PlaceTabPage(rec)
    rec.page:Show()
    if rec.band then rec.band:Show() end
    if changedTab then SetScroll(rec.page, 0) end         -- reselecting the tab you are on keeps your place
    I.Reflow(rec.page.fsHolder)
    Remeasure(rec.page)
    UpdateCrumb(cat, tab)
    SetSelected(cat.key)
    I.ScrollNavTo(cat.key)
    CW.RefreshAll()
    if changedTab then Fire("select", cat.key, tab.key) end
end

-- Does nothing while the window is hidden: Open and Select refresh before anything is seen.
function CW.RefreshAll()
    if not (ui.frame and ui.frame:IsShown()) then return end
    for _, fn in ipairs(rowStates) do
        local ok, err = pcall(fn)
        if not ok then Forward(err) end
    end
    for _, fn in ipairs(controls) do
        local ok, err = pcall(fn)
        if not ok then Forward(err) end
    end
    if ui.readOnlyIcon then ui.readOnlyIcon:SetShown(Config.IsReadOnly()) end
    I.UpdateChanged()
    local rec = ui.tabRec
    if rec and rec.page then
        if I.EvalWhens(rec.page.fsHolder) then
            I.Reflow(rec.page.fsHolder)
            Remeasure(rec.page)
        end
    end
end

-------------------------------------------------------------------------------
-- Nav
-------------------------------------------------------------------------------

local function MakeNavButton(cat)
    local b = CreateFrame("Button", nil, ui.navChild)
    b:SetSize(S.NAV_W, S.NAV_ITEM_H)
    b:RegisterForClicks("LeftButtonUp")
    b.fsCategory = cat.key
    b.fsHighlight = Theme.AddCutSliceFill(b, { C.cyan[1], C.cyan[2], C.cyan[3], 0.12 }, 0)
    b.fsHover = Theme.AddCutSliceFill(b, { C.cyan[1], C.cyan[2], C.cyan[3], 0.06 }, 0)
    b.fsHover:Hide()
    b.fsBar = b:CreateTexture(nil, "ARTWORK")
    b.fsBar:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 1)
    b.fsBar:SetWidth(S.NAV_SEL_W)
    b.fsBar:SetPoint("TOPLEFT", b, "TOPLEFT", 0, -6)
    b.fsBar:SetPoint("BOTTOMLEFT", b, "BOTTOMLEFT", 0, 6)
    b.fsLabel = Label(b, "", S.TEXT, C.muted)
    b.fsLabel:SetPoint("LEFT", b, "LEFT", S.NAV_SEL_W + 6, 0)
    b.fsLabel:SetPoint("RIGHT", b, "RIGHT", -(S.PWR + S.PWR_R), 0)
    b.fsLabel:SetJustifyH("LEFT")
    b.fsNdot = b:CreateTexture(nil, "OVERLAY")
    b.fsNdot:SetColorTexture(C.pink[1], C.pink[2], C.pink[3], 1)
    b.fsNdot:SetSize(S.DOT, S.DOT)
    b.fsNdot:SetPoint("RIGHT", b, "RIGHT", -(S.PWR + S.PWR_R + 6), 0)
    b.fsNdot:Hide()
    -- the right slot: B5's power button lives here
    b.fsSlot = CreateFrame("Frame", nil, b)
    b.fsSlot:SetSize(S.PWR, S.PWR)
    b.fsSlot:SetPoint("RIGHT", b, "RIGHT", -S.PWR_R, 0)
    b:SetScript("OnClick", function() CW.Open(cat.key) end)
    b:SetScript("OnEnter", function(self) if not self.fsSelected then self.fsHover:Show() end end)
    b:SetScript("OnLeave", function(self) self.fsHover:Hide() end)
    return b
end

local function NavTotal()
    return ui.navTotal or 0
end

local function NavRange()
    return math.max(0, NavTotal() - D.NAVSCROLL_H)
end

local function UpdateNavRail()
    local rail = ui.navRail
    if not rail then return end
    local range = NavRange()
    if range <= 0 then rail:Hide() return end
    local view = D.NAVSCROLL_H
    local height = math.max(THUMB_MIN_H, math.floor(view * view / (view + range)))
    rail.fsThumb:SetHeight(height)
    rail.fsThumb:ClearAllPoints()
    rail.fsThumb:SetPoint("TOP", rail, "TOP", 0, -math.floor((view - height) * ui.navScroll:GetVerticalScroll() / range + 0.5))
    rail:Show()
end

local function SetNavScroll(value)
    value = math.min(NavRange(), math.max(0, value))
    ui.navScroll:SetVerticalScroll(value)
    UpdateNavRail()
end

function I.LayoutNav()
    local y = 0
    local lastGroup
    local rows = {}
    for key, label in pairs(ui.groups) do label:Hide() end
    for _, cat in ipairs(sorted) do
        local b = ui.nav[cat.key]
        if not b then
            b = MakeNavButton(cat)
            ui.nav[cat.key] = b
        end
        if cat.group ~= lastGroup then
            if lastGroup then y = y + S.NAVGRP_GAP end
            local label = ui.groups[cat.group]
            if not label then
                label = Label(ui.navChild, "// " .. cat.group, S.SMALL, C.muted)
                ui.groups[cat.group] = label
            end
            label:ClearAllPoints()
            label:SetPoint("TOPLEFT", ui.navChild, "TOPLEFT", 0, -y)
            label:SetHeight(S.NAVLAB_H)
            label:Show()
            y = y + S.NAVLAB_H + S.NAV_ITEM_GAP
            lastGroup = cat.group
        end
        b.fsLabel:SetText(cat.label)
        b.fsY = y
        b:ClearAllPoints()
        b:SetPoint("TOPLEFT", ui.navChild, "TOPLEFT", 0, -y)
        b:Show()
        y = y + S.NAV_ITEM_H
        rows[#rows + 1] = cat.key
    end
    for key, b in pairs(ui.nav) do
        if not categories[key] then b:Hide() end
    end
    ui.navTotal = y
    ui.navChild:SetHeight(math.max(y, 1))
    SetSelected(ui.current)
    SetNavScroll(ui.navScroll:GetVerticalScroll())
end

-- The selected row centred in the visible list.
function I.ScrollNavTo(key)
    local b = ui.nav[key]
    if not (b and b.fsY) then return end
    SetNavScroll(b.fsY + S.NAV_ITEM_H / 2 - D.NAVSCROLL_H / 2)
end

-- CW.NavRows(): { { key, label, group, button, slot } } in list order, for the power buttons, counts and search.
function CW.NavRows()
    pcall(CW.EnsureBuilt)
    local list = {}
    for _, cat in ipairs(sorted) do
        local b = ui.nav[cat.key]
        if b then list[#list + 1] = { key = cat.key, label = cat.label, group = cat.group, button = b, slot = b.fsSlot } end
    end
    return list
end

function CW.NavSlot(navKey)
    pcall(CW.EnsureBuilt)
    local b = ui.nav[ResolveCategory(navKey) and ResolveCategory(navKey).key or navKey]
    return b and b.fsSlot or nil
end

function CW.FooterSlot(side)
    pcall(CW.EnsureBuilt)
    return ui.footer and ui.footer[side == "right" and "right" or "left"] or nil
end

function CW.SearchSlot()
    pcall(CW.EnsureBuilt)
    return ui.searchSlot
end

-- No-op until the search ticket replaces it: it takes the registry row a jump landed on.
function CW.JumpHighlight(entry) end

-- The scroll body of a page (its tab, or the first built one): where a page's own builder adds rows.
function CW.PageBody(page, tab)
    local cat = ResolveCategory(page)
    if not cat then return nil end
    local def = ResolveTab(cat, tab) or ResolveTab(cat, ui.tabFor and ui.tabFor[cat.key]) or cat.tabs[1]
    local rec = ui.tabs[cat.key .. "/" .. def.key]
    return rec and rec.page and rec.page.fsHolder or nil
end

-------------------------------------------------------------------------------
-- Building the window
-------------------------------------------------------------------------------

local function ClampSize(w, h)
    w = math.min(S.WIN_MAX_W, math.max(S.WIN_MIN_W, math.floor((tonumber(w) or S.WIN_W) + 0.5)))
    h = math.min(S.WIN_MAX_H, math.max(S.WIN_MIN_H, math.floor((tonumber(h) or S.WIN_H) + 0.5)))
    return w, h
end

-- Everything that follows the size: the derived values, the nav list, the width of each built tab, the scroll range.
local function ApplyDerived(w, h)
    for k, v in pairs(S.Derive(w, h)) do D[k] = v end
    if not ui.frame then return end
    ui.navScroll:SetHeight(D.NAVSCROLL_H)
    ui.navRail:SetHeight(D.NAVSCROLL_H)
    for _, rec in pairs(ui.tabs) do
        if rec.page then
            rec.page.fsChild:SetSize(D.CONTENT_W + 2 * PAD_X, rec.page.fsChild:GetHeight())
            rec.page.fsHolder:SetWidth(D.CONTENT_W)
            for _, item in ipairs(rec.page.fsHolder.fsFlow) do
                if item.frame.fsOnResize then pcall(item.frame.fsOnResize, D) end
            end
            I.Reflow(rec.page.fsHolder)
            Remeasure(rec.page)
        end
    end
    SetNavScroll(ui.navScroll:GetVerticalScroll())
    if ui.current then I.ScrollNavTo(ui.current) end
end

-- Resizes the window (clamped to the min and max), repeating every derived value. `save` remembers the size account wide.
function CW.SetSize(w, h, save)
    w, h = ClampSize(w, h)
    if ui.frame then ui.frame:SetSize(w, h) end
    ApplyDerived(w, h)
    if save then
        CW.UIState("winW", w)
        CW.UIState("winH", h)
    end
    return w, h
end

local function BuildChrome(frame)
    -- the title strip ("stuwave://config" and its rule) is the panel's own header band, STRIP_H tall
    Theme.SkinPanel(frame, { strip = false, title = "config", bandHeight = S.STRIP_H })

    -- the head: brand, version and the breadcrumb
    local title = frame:CreateFontString(nil, "OVERLAY")
    Theme.ApplyFontGeneric(title, Theme.FONT_ORBITRON, S.BRAND_SIZE, C.text, "")
    title:SetPoint("TOPLEFT", frame, "TOPLEFT", S.PAD, -D.BRAND_Y)
    title:SetText("FOREVER |cffff2e97STU|rWAVE")
    ui.brand = title

    local sub = Label(frame, "", S.TEXT, C.muted)
    sub:SetPoint("TOPLEFT", frame, "TOPLEFT", S.PAD, -D.VER_Y)
    local version = Version()
    sub:SetText((version and ("v" .. version .. "  \194\183  ") or "") .. "|cff22e0ff/fsconfig|r")
    ui.version = sub

    local icon = UI.HelpIcon(frame,
        "Saved settings could not be loaded, so every setting and profile is read-only this session.")
    icon.fsReadOnlyIcon = true
    icon:SetPoint("LEFT", sub, "RIGHT", 8, 0)
    icon:Hide()
    ui.readOnlyIcon = icon

    ui.crumb = Label(frame, "", S.TEXT, C.muted)
    ui.crumb:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -S.PAD, -D.VER_Y)
    ui.crumb:SetJustifyH("RIGHT")

    FS.ButtonSkins.NewCloseButton(frame, function() CW.Close() end) -- the shared STUwave X, seats itself top right

    local headRule = frame:CreateTexture(nil, "ARTWORK")
    headRule:SetColorTexture(C.line[1], C.line[2], C.line[3], 1)
    headRule:SetHeight(1)
    headRule:SetPoint("TOPLEFT", frame, "TOPLEFT", 0, -D.BODY_T)
    headRule:SetPoint("TOPRIGHT", frame, "TOPRIGHT", 0, -D.BODY_T)

    -- the search slot above the nav (B1 fills it)
    ui.searchSlot = CreateFrame("Frame", nil, frame)
    ui.searchSlot:SetSize(S.NAV_W, S.SEARCH_H)
    ui.searchSlot:SetPoint("TOPLEFT", frame, "TOPLEFT", S.PAD, -D.BODY_T)

    -- the nav list: clipped, wheel scrolled, a thin rail
    ui.navScroll = CreateFrame("ScrollFrame", nil, frame)
    ui.navScroll:SetSize(S.NAV_W, D.NAVSCROLL_H)
    ui.navScroll:SetPoint("TOPLEFT", frame, "TOPLEFT", S.PAD, -D.NAVLAB_Y)
    ui.navScroll:SetClipsChildren(true)
    ui.navScroll:EnableMouseWheel(true)
    ui.navChild = CreateFrame("Frame", nil, ui.navScroll)
    ui.navChild:SetSize(S.NAV_W, 1)
    ui.navScroll:SetScrollChild(ui.navChild)
    ui.navScroll:SetScript("OnMouseWheel", function(_, delta) SetNavScroll(ui.navScroll:GetVerticalScroll() - delta * WHEEL_STEP) end)
    ui.navRail = CreateFrame("Frame", nil, frame)
    ui.navRail:SetSize(2, D.NAVSCROLL_H)
    ui.navRail:SetPoint("TOPLEFT", frame, "TOPLEFT", S.PAD + S.NAV_W + 6, -D.NAVLAB_Y)
    local railFill = ui.navRail:CreateTexture(nil, "BACKGROUND")
    railFill:SetColorTexture(C.line[1], C.line[2], C.line[3], 0.6)
    railFill:SetAllPoints(ui.navRail)
    local railThumb = CreateFrame("Frame", nil, ui.navRail)
    railThumb:SetSize(2, THUMB_MIN_H)
    railThumb:SetPoint("TOP", ui.navRail, "TOP", 0, 0)
    local thumbFill = railThumb:CreateTexture(nil, "ARTWORK")
    thumbFill:SetColorTexture(C.violet[1], C.violet[2], C.violet[3], 1)
    thumbFill:SetAllPoints(railThumb)
    ui.navRail.fsThumb = railThumb
    ui.navRail:Hide()

    local navCommands = Label(frame, "/fsgun  /fsedit  /fsbug", S.SMALL, C.line)
    navCommands:SetPoint("TOPLEFT", frame, "TOPLEFT", S.PAD, -D.NAVFOOT_Y)

    -- the well
    local well = CreateFrame("Frame", nil, frame)
    well:SetPoint("TOPLEFT", frame, "TOPLEFT", D.WELL_X, -D.BODY_T)
    well:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -S.PAD, S.FOOT_H)
    local fill = well:CreateTexture(nil, "BACKGROUND")
    fill:SetColorTexture(C.track[1], C.track[2], C.track[3], 0.95)
    fill:SetAllPoints(well)
    Outline(well, C.line, 1)
    ui.well = well
    ui.content = CreateFrame("Frame", nil, well)
    PlaceContent()
    BuildScrollbar(well)

    -- the footer band: empty slots (B2 fills them)
    local foot = CreateFrame("Frame", nil, frame)
    foot:SetHeight(S.FOOT_H)
    foot:SetPoint("BOTTOMLEFT", frame, "BOTTOMLEFT", 0, 0)
    foot:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", 0, 0)
    local footFill = foot:CreateTexture(nil, "BACKGROUND")
    footFill:SetColorTexture(C.ink[1], C.ink[2], C.ink[3], 0.6)
    footFill:SetAllPoints(foot)
    local footRule = foot:CreateTexture(nil, "ARTWORK")
    footRule:SetColorTexture(C.violet[1], C.violet[2], C.violet[3], 0.30)
    footRule:SetHeight(1)
    footRule:SetPoint("TOPLEFT", foot, "TOPLEFT", 0, 0)
    footRule:SetPoint("TOPRIGHT", foot, "TOPRIGHT", 0, 0)
    ui.foot = foot
    local left = CreateFrame("Frame", nil, foot)
    left:SetHeight(S.BTN_H)
    left:SetPoint("LEFT", foot, "LEFT", S.PAD, 0)
    left:SetPoint("RIGHT", foot, "CENTER", -S.PAD / 2, 0)
    local right = CreateFrame("Frame", nil, foot)
    right:SetHeight(S.BTN_H)
    right:SetPoint("LEFT", foot, "CENTER", S.PAD / 2, 0)
    right:SetPoint("RIGHT", foot, "RIGHT", -S.PAD, 0)
    ui.footer = { left = left, right = right }

    -- the resize grip, bottom right
    local grip = CreateFrame("Button", nil, frame)
    grip:SetSize(GRIP, GRIP)
    grip:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -2, 2)
    grip:SetFrameLevel(frame:GetFrameLevel() + 10)
    grip.fsGrip = true
    for i = 1, 3 do
        local line = grip:CreateTexture(nil, "OVERLAY")
        line:SetColorTexture(C.violet[1], C.violet[2], C.violet[3], 0.8)
        line:SetSize(2 + i * 3, 1)
        line:SetPoint("BOTTOMRIGHT", grip, "BOTTOMRIGHT", -1, 1 + (i - 1) * 3)
    end
    grip:SetScript("OnEnter", function(self) self.fsHover = true end)
    grip:SetScript("OnLeave", function(self) self.fsHover = false end)
    grip:SetScript("OnMouseDown", function(self, button)
        if button ~= "LeftButton" then return end
        local f = ui.frame
        -- a frame anchored by its centre grows both ways: seat it by its top left corner first
        local left, top = f:GetLeft(), f:GetTop()
        if left and top then
            f:ClearAllPoints()
            f:SetPoint("TOPLEFT", UIParent, "BOTTOMLEFT", left, top)
        end
        if type(f.StartSizing) == "function" then f:StartSizing("BOTTOMRIGHT") end
    end)
    grip:SetScript("OnMouseUp", function()
        local f = ui.frame
        f:StopMovingOrSizing()
        CW.SetSize(f:GetWidth(), f:GetHeight(), true)
    end)
    ui.grip = grip
end

local function BuildWindow()
    local w, h = ClampSize(CW.UIState("winW") or S.WIN_W, CW.UIState("winH") or S.WIN_H)
    for k, v in pairs(S.Derive(w, h)) do D[k] = v end
    local frame = CreateFrame("Frame", FRAME_NAME, UIParent)
    frame:Hide()
    frame:SetSize(w, h)
    frame:SetPoint("CENTER", UIParent, "CENTER", 0, 40)
    frame:SetFrameStrata("DIALOG")
    frame:SetToplevel(true)
    frame:SetClampedToScreen(true)
    frame:SetMovable(true)
    if type(frame.SetResizable) == "function" then frame:SetResizable(true) end
    if type(frame.SetResizeBounds) == "function" then
        frame:SetResizeBounds(S.WIN_MIN_W, S.WIN_MIN_H, S.WIN_MAX_W, S.WIN_MAX_H)
    elseif type(frame.SetMinResize) == "function" then
        frame:SetMinResize(S.WIN_MIN_W, S.WIN_MIN_H)
        if type(frame.SetMaxResize) == "function" then frame:SetMaxResize(S.WIN_MAX_W, S.WIN_MAX_H) end
    end
    frame:EnableMouse(true)
    frame:RegisterForDrag("LeftButton")
    frame:SetScript("OnDragStart", frame.StartMoving)
    frame:SetScript("OnDragStop", frame.StopMovingOrSizing)
    frame:SetScript("OnShow", function()
        CW.RefreshScroll()
        Fire("show")
    end)
    frame:SetScript("OnHide", function(self)
        I.CloseMenu()
        I.CloseDialog()
        SetHover(nil)
        local owner = GameTooltip:GetOwner()
        while owner and owner ~= self do owner = owner:GetParent() end
        if owner then GameTooltip:Hide() end
        Fire("hide")
    end)
    -- Real size changes while the grip drags: re-derive and relay out (the final size is saved on release).
    frame:SetScript("OnSizeChanged", function(self, nw, nh)
        if not ui.frame or ui.sizing then return end
        nw, nh = ClampSize(nw, nh)
        if nw == D.WIN_W and nh == D.WIN_H then return end
        ui.sizing = true
        ApplyDerived(nw, nh)
        ui.sizing = false
    end)
    local elapsed = 0
    frame:SetScript("OnUpdate", function(_, dt)
        elapsed = elapsed + (dt or 0)
        if elapsed < 0.05 then return end
        elapsed = 0
        PollHover()
    end)
    ui.frame = frame
    local ok, err = pcall(BuildChrome, frame)
    if not ok then
        frame:Hide()
        ui.frame = nil
        error(err, 0)
    end
    local specials = _G.UISpecialFrames
    if type(specials) == "table" then
        local present = false
        for _, name in ipairs(specials) do
            if name == FRAME_NAME then present = true end
        end
        if not present then table.insert(specials, FRAME_NAME) end
    end
    return frame
end

function CW.EnsureBuilt()
    if not ui.frame then BuildWindow() end
    I.LayoutNav()
    return ui.frame
end

-------------------------------------------------------------------------------
-- Public surface
-------------------------------------------------------------------------------

-- CW.Open(page, tab, rowKey): the window on a page, optionally a tab and a row (scrolled into view and highlighted).
function CW.Open(page, tab, rowKey)
    local ok, err = pcall(CW.EnsureBuilt)
    if not ok then
        Forward(err)
        Say("the config window could not open.")
        return
    end
    local cat = ResolveCategory(page)
    if not cat then
        cat = ResolveCategory(ui.current) or sorted[1]
    end
    ui.frame:Show()
    if cat then
        local def = ResolveTab(cat, tab)
        Select(cat, def)
        if rowKey then
            local entry = CW.RowByKey(rowKey, cat.key)
            if entry and entry.row.fsItem and ui.tabRec and ui.tabRec.page then
                SetScroll(ui.tabRec.page, (entry.row.fsItem.y or 0) - S.SEC_H)
                Fire("jump", entry)
                pcall(CW.JumpHighlight, entry)
            end
        end
    end
end

function CW.Close()
    if ui.frame then ui.frame:Hide() end
end

function CW.IsShown()
    return ui.frame ~= nil and ui.frame:IsShown() == true
end

function CW.Toggle()
    if CW.IsShown() then CW.Close() else CW.Open() end
end

-- The page and tab now showing, as keys.
function CW.Current()
    return ui.current, ui.tab
end

-- Section fold state (an account wide table, never a profile): `id` is "page/tab/Title".
function CW.IsFolded(id, default)
    local value = FoldTable()[id]
    if value == nil then return default == true end
    return value == true
end

function CW.SetFolded(id, folded)
    FoldTable()[id] = folded == true
end

-- Repaints the controls whenever any setting changes, which includes a profile switch.
Config.OnAnyChange(function(key, new, old)
    if ui.frame then CW.RefreshAll() end
    Fire("change", key, new, old)
end)

-- /fsconfig, /fsconfig <page>, /fsconfig <page> <tab>: a page or tab matches its key or its label, spaces ignored.
SLASH_FSCONFIG1 = "/fsconfig"
SlashCmdList["FSCONFIG"] = function(msg)
    msg = tostring(msg or "")
    local words = {}
    for word in msg:gmatch("%S+") do words[#words + 1] = word end
    if #words > 0 then
        -- the longest run of leading words that names a page, the rest names its tab
        for n = #words, 1, -1 do
            local cat = ResolveCategory(table.concat(words, " ", 1, n))
            if cat then
                local tab = n < #words and table.concat(words, " ", n + 1) or nil
                CW.Open(cat.key, tab and ResolveTab(cat, tab) and ResolveTab(cat, tab).key or nil)
                return
            end
        end
    end
    CW.Toggle()
end
