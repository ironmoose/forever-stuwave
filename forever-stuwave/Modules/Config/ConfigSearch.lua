-- Forever STUwave: the config search box and its results
-- A box over the nav finds any setting by label, section or tip and jumps to it. The index is the row registry
-- (CW.Rows()): every row a built tab recorded, so the first focus builds the tabs nobody opened, hidden, one per frame and
-- never in combat. Ranking: label prefix, label substring, section title, tip text, then loose letters of the label (3 or
-- more, "cbar" finds Cast bar); spaces are ignored; equal scores go to the shorter label. A jump opens the page and tab
-- through CW.Open, sets whatever picker hides the row (the class strip, the Style frame picker: see CW.SearchGate), unfolds
-- the section, scrolls the row in and outlines it in cyan until the next click or search. CW.JumpHighlight is that outline;
-- CW.Open calls it for any caller, so the layout editor's jumps get it too. Visuals follow the prototype
-- (mockups/config-window-2026-11-25.html, frames B, C and K) and are pending owner review. Harness: tools/configsearch-harness.py.

local _, FS = ...

local CW = FS.ConfigWindow
if not (CW and CW.I and CW.Spec and CW.Rows) then return end

local I, S, C = CW.I, CW.Spec, CW.C
local Theme, Config = FS.Theme, FS.Config
local Mix, Label, Outline, Forward = I.Mix, I.Label, I.Outline, I.Forward

local Search = {}
CW.Search = Search

-------------------------------------------------------------------------------
-- Constants and small helpers
-------------------------------------------------------------------------------

local FADE = 0.3              -- the jump outline fades in over this many seconds
local OUTSET = 7              -- the outline reaches this far past a row, inside the page's own margin (8)
local HEAD_PAD, ROW_PAD_L, ROW_PAD_T, BADGE_R, BADGE_T = 8, 12, 2, 8, 4

-- The prototype's dim greys, derived from the colour map (--dim, --dis, --dis2, --disedge).
local DIM = Mix(C.line, C.violet, 0.18)
local DIS = Mix(C.line, C.muted, 0.38)
local DIS2 = Mix(C.line, C.muted, 0.7)
local DISEDGE = Mix(C.track, C.line, 0.65)
local PINK_EDGE = Mix(C.track, C.pink, 0.5)

local function Esc(color)
    return ("|cff%02x%02x%02x"):format(math.floor(color[1] * 255 + 0.5), math.floor(color[2] * 255 + 0.5), math.floor(color[3] * 255 + 0.5))
end
local CYAN, TEXT, SEP = Esc(C.cyan), Esc(C.text), Esc(DIS)

local function Guard(fn)
    return function(...)
        local ok, err = pcall(fn, ...)
        if not ok then Forward(err) end
    end
end

-- Text without colour escapes.
local function Plain(text)
    text = tostring(text or "")
    text = text:gsub("|c%x%x%x%x%x%x%x%x", "")
    text = text:gsub("|r", "")
    return text
end

local function Squash(text)
    return (Plain(text):lower():gsub("%s+", ""))
end

local function Fit(text, width)
    if #text <= width then return text end
    return text:sub(1, width - 2) .. ".."
end

local state = { text = "", changed = false, results = {}, sel = 1, top = 1 }
Search.state = state

-------------------------------------------------------------------------------
-- The index: one record per searchable row, extended as tabs build
-------------------------------------------------------------------------------

local index, indexed = {}, 0

local function Indexable(entry)
    return entry.kind ~= "note" and entry.page ~= nil and entry.tab ~= nil and type(entry.label) == "string" and entry.label ~= ""
end

-- The records of every row in the registry so far. Rows are only ever appended, so only the new ones are read.
function Search.Index()
    local rows = CW.Rows()
    if #rows < indexed then index, indexed = {}, 0 end
    if #rows > indexed then
        for i = indexed + 1, #rows do
            local entry = rows[i]
            if Indexable(entry) then
                local label = Plain(entry.label)
                local rec = {
                    entry = entry, label = label, ls = Squash(label), ss = Squash(entry.section),
                    ts = type(entry.tip) == "string" and Squash(entry.tip) or "", pos = #index + 1,
                }
                rec.ll = #rec.ls
                rec.res = { item = rec, score = 0 }
                index[#index + 1] = rec
            end
        end
        indexed = #rows
    end
    return index
end

local function Subsequence(text, letters)
    local j, n = 1, #letters
    for i = 1, #text do
        if text:byte(i) == letters:byte(j) then
            j = j + 1
            if j > n then return true end
        end
    end
    return false
end

local function Better(a, b)
    local x, y = a.item, b.item
    if a.score ~= b.score then return a.score > b.score end
    if x.ll ~= y.ll then return x.ll < y.ll end
    return x.pos < y.pos
end

-- Ranked results for `text`: a list of { item, score }. `changedOnly` keeps the rows that differ from their default; with
-- an empty text it lists them all.
function Search.Run(text, changedOnly)
    local q = Squash(text)
    local nq = #q
    local list = Search.Index()
    local out, n = {}, 0
    for i = 1, #list do
        local rec = list[i]
        local score = 0
        if changedOnly == true and not I.EntryChanged(rec.entry) then
            score = 0
        elseif nq == 0 then
            score = changedOnly == true and 1 or 0
        elseif rec.ls:sub(1, nq) == q then
            score = 5
        elseif rec.ls:find(q, 1, true) then
            score = 4
        elseif rec.ss ~= "" and rec.ss:find(q, 1, true) then
            score = 3
        elseif rec.ts ~= "" and rec.ts:find(q, 1, true) then
            score = 2
        elseif nq >= 3 and Subsequence(rec.ls, q) then
            score = 1
        end
        if score > 0 then
            local res = rec.res
            res.score = score
            n = n + 1
            out[n] = res
        end
    end
    table.sort(out, Better)
    return out
end

-- The label with the part that matched in cyan: the typed run, or the loose letters one by one.
local function Mark(label, q)
    if q == "" or label:find("|", 1, true) then return label end
    local map, chars = {}, {}
    for i = 1, #label do
        local ch = label:sub(i, i)
        if not ch:find("%s") then
            map[#map + 1] = i
            chars[#chars + 1] = ch:lower()
        end
    end
    local flat = table.concat(chars)
    local from, to = flat:find(q, 1, true)
    if from then
        local a, b = map[from], map[to]
        return label:sub(1, a - 1) .. CYAN .. label:sub(a, b) .. "|r" .. label:sub(b + 1)
    end
    if #q >= 3 and not label:find("[\128-\255]") then
        local marked, j = {}, 1
        for k = 1, #flat do
            if j <= #q and flat:sub(k, k) == q:sub(j, j) then
                marked[map[k]] = true
                j = j + 1
            end
        end
        if j > #q then
            local out = {}
            for i = 1, #label do
                local ch = label:sub(i, i)
                out[#out + 1] = marked[i] and (CYAN .. ch .. "|r") or ch
            end
            return table.concat(out)
        end
    end
    return label
end

-------------------------------------------------------------------------------
-- What hides or disables a row
-------------------------------------------------------------------------------

-- A row and its section show unless a `when` says no (the same rule as the window's own re-read of every `when`).
local function Shown(entry)
    local function hides(fn)
        if not fn then return false end
        local ok, value = pcall(fn)
        return ok and not value
    end
    if hides(entry.when) then return false end
    local sec = entry.secObj
    if sec and hides(sec.when) then return false end
    return true
end

-- Whether the row is switched off now, the reason line and the short word for the badge. Read fresh, not from the
-- registry's `disabled` (a tab nobody is looking at repaints only when shown).
local function Disabled(entry)
    local opts = entry.opts or {}
    if entry.needs then
        local parent = CW.RowByKey(entry.needs)
        local value = Config.Get(entry.needs)
        local inverted = parent and parent.inverted
        local on
        if inverted then on = value ~= true else on = value == true end
        if not on then
            local name = Plain(opts.nl or (parent and parent.label) or tostring(entry.needs))
            return true, "Requires " .. name .. " to be on.", "NEEDS " .. Fit(name:upper(), 22)
        end
    end
    if entry.enabled then
        local ok, value = pcall(entry.enabled)
        if not (ok and value == true) then
            local reason = Plain(opts.reason or entry.reason or "Not available right now.")
            local name = reason:match("^Requires (.+) to be on%.$") or reason:match("^Needs (.+)$")
            name = name and name:gsub("%.$", "")
            return true, reason, name and ("NEEDS " .. Fit(name:upper(), 22)) or "UNAVAILABLE"
        end
    end
    return false
end

-- The module switch store (Core/ModuleSwitch.lua) when this build has one: the label of the module that owns `page` and
-- is switched off.
local function ModuleOff(page)
    local MS = FS.ModuleSwitch
    if type(MS) ~= "table" or type(MS.Keys) ~= "function" or type(MS.Page) ~= "function" then return nil end
    local isOn = MS.Wanted or MS.IsOn or MS.On
    if type(isOn) ~= "function" then return nil end
    for _, key in ipairs(MS.Keys()) do
        if MS.Page(key) == page then
            local ok, on = pcall(isOn, key)
            if ok and on == false then
                return type(MS.Label) == "function" and MS.Label(key) or tostring(key)
            end
        end
    end
end

-------------------------------------------------------------------------------
-- Gates: a picker that decides whether a row is on screen
-------------------------------------------------------------------------------

-- CW.SearchGate{ id, page, tab (optional), values = fn() -> { {value, text}, ... }, set = fn(value),
-- with = fn(value, check) }. `with` runs check() as if the picker held `value` and puts everything back, without a
-- refresh, a saved write or any other effect; the search uses it to name the value that shows a hidden row. `set` makes the
-- choice for real, on a jump. A row hidden by a `when` that no gate can open is shown dim as HIDDEN.
local gates = {}

function Search.AddGate(spec)
    if type(spec) ~= "table" or type(spec.page) ~= "string" then return false end
    if type(spec.values) ~= "function" or type(spec.set) ~= "function" or type(spec.with) ~= "function" then return false end
    if spec.id then
        for i, g in ipairs(gates) do
            if g.id == spec.id then
                gates[i] = spec
                return true
            end
        end
    end
    gates[#gates + 1] = spec
    return true
end
CW.SearchGate = Search.AddGate

-- The gate and value that show a hidden row, or nil.
local function GateFor(entry)
    for _, g in ipairs(gates) do
        if g.page == entry.page and (g.tab == nil or g.tab == entry.tab) then
            local ok, values = pcall(g.values)
            if ok and type(values) == "table" then
                for _, v in ipairs(values) do
                    local shows = g.with(v.value, function() return Shown(entry) end)
                    if shows then return g, v end
                end
            end
        end
    end
end

-- Addon tabs: the class strip (ConfigPageAddonTabs.lua keeps its choice in the account window state).
Search.AddGate({
    id = "tabs.cls", page = "tabs",
    values = function()
        local list = {}
        for _, c in ipairs(CW.CLASS_STRIP or {}) do list[#list + 1] = { value = c[1], text = c[2] } end
        return list
    end,
    set = function(value) CW.UIState("tabsCls", value) end,
    with = function(value, check)
        local old = CW.UIState("tabsCls")
        CW.UIState("tabsCls", value)
        local ok, result = pcall(check)
        CW.UIState("tabsCls", old)
        return ok and result
    end,
})

-- Unit Frames, Style tab: the frame picker is the profile setting bars.module (ConfigPageBars.lua reads it through
-- Config.Get, so a check reads the pretend value while `with` runs).
local STYLE_FRAMES = { "player", "target", "focus", "boss" }
Search.AddGate({
    id = "bars.module", page = "unit", tab = "bars",
    values = function()
        local style = FS.FrameStyle
        local list = {}
        for _, key in ipairs(STYLE_FRAMES) do
            list[#list + 1] = { value = key, text = style and style.LABELS and style.LABELS[key] or key }
        end
        return list
    end,
    set = function(value) Config.Set("bars.module", value) end,
    with = function(value, check)
        local real = Config.Get
        Config.Get = function(key, ...)
            if key == "bars.module" then return value end
            return real(key, ...)
        end
        local ok, result = pcall(check)
        Config.Get = real
        return ok and result
    end,
})

-------------------------------------------------------------------------------
-- Revealing a row and the jump outline
-------------------------------------------------------------------------------

local function OnShownTab(entry)
    local rec = I.ui.tabRec
    return rec ~= nil and rec.id == entry.page .. "/" .. entry.tab
end

-- Unfolds the row's section and scrolls the row (or its section header, when the row itself is hidden) to a section height
-- below the top of the page. Returns whether the row is on screen.
local function Reveal(entry)
    if not OnShownTab(entry) then return false end
    local sec = entry.secObj
    if sec and sec.folded then
        sec.folded = false
        if sec.id then CW.SetFolded(sec.id, false) end
        if sec.chevron then sec.chevron:SetText("v") end
    end
    CW.RefreshScroll()
    local row = entry.row
    local item = row.fsItem
    local shown = row:IsShown() and item ~= nil
    local at = shown and item or (sec and sec.item)
    local page = I.FindScrollPage(row)
    if at and page and at.y then
        local target = math.max(0, math.min(page.fsRange or 0, at.y - S.SEC_H))
        page:SetVerticalScroll(target)
        CW.RefreshScroll()
    end
    return shown
end

local hilite

local function Hilite()
    if hilite then return hilite end
    local f = CreateFrame("Frame", nil, UIParent)
    f:Hide()
    f.fsEdges = Outline(f, C.cyan, 1)                 -- one pixel, cyan
    local halo = CreateFrame("Frame", nil, f)         -- the soft ring just outside it
    halo:SetPoint("TOPLEFT", f, "TOPLEFT", -1, 1)
    halo:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", 1, -1)
    f.fsHalo = Outline(halo, C.cyan, 0.3)
    local tint = f:CreateTexture(nil, "BACKGROUND")
    tint:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 0.06)
    tint:SetAllPoints(f)
    f.fsTint = tint
    f:EnableMouse(false)
    f:SetScript("OnUpdate", function(self, dt)
        self.fsT = (self.fsT or 0) + (dt or 0)
        self:SetAlpha(math.min(1, self.fsT / FADE))
        -- the next click anywhere ends it; the click that made the jump is already down, so it does not count
        if type(IsMouseButtonDown) == "function" then
            local down = IsMouseButtonDown("LeftButton") or IsMouseButtonDown("RightButton")
            if down and not self.fsDown then
                Search.ClearHighlight()
                return
            end
            self.fsDown = down
        end
    end)
    hilite = f
    Search.hilite = f
    return f
end

function Search.ClearHighlight()
    if hilite then hilite:Hide() end
end

-- CW.JumpHighlight(entry): the registry row a jump landed on gets a cyan one pixel outline that fades in over 0.3 s and
-- holds until the next click, a new search, a tab change or the window closing.
function CW.JumpHighlight(entry)
    if type(entry) ~= "table" or not entry.row then return end
    local shown = Reveal(entry)
    Search.ClearHighlight()
    if not shown then return end
    local f = Hilite()
    local row = entry.row
    f:SetParent(row)
    f:ClearAllPoints()
    f:SetPoint("TOPLEFT", row, "TOPLEFT", -OUTSET, 0)
    f:SetPoint("BOTTOMRIGHT", row, "BOTTOMRIGHT", OUTSET, 0)
    f:SetFrameLevel((row:GetFrameLevel() or 1) + 8)
    f.fsT = 0
    f.fsDown = type(IsMouseButtonDown) == "function" and (IsMouseButtonDown("LeftButton") or IsMouseButtonDown("RightButton")) or false
    f:SetAlpha(0)
    f:Show()
end

-------------------------------------------------------------------------------
-- Jumping
-------------------------------------------------------------------------------

local function ClearBox(silent)
    local edit = Search.edit
    if not edit then return end
    state.silent = silent == true
    if (edit:GetText() or "") ~= "" then edit:SetText("") end
    state.silent = false
    state.text, state.changed = "", false
    state.results, state.sel, state.top = {}, 1, 1
    if edit:HasFocus() then edit:ClearFocus() end
    Search.Paint()
end

function Search.Jump(item)
    local entry = item and item.entry
    if not entry then return end
    state.jumping = true
    ClearBox(true)
    local ok, err = pcall(function()
        CW.Open(entry.page, entry.tab)
        if not Shown(entry) then
            local gate, value = GateFor(entry)
            if gate then
                gate.set(value.value)
                CW.RefreshAll()
            end
        end
        if entry.key ~= nil and CW.RowByKey(entry.key, entry.page) == entry then
            CW.Open(entry.page, entry.tab, entry.key)
        else
            I.Fire("jump", entry)
            pcall(CW.JumpHighlight, entry)
        end
    end)
    state.jumping = false
    if not ok then Forward(err) end
end

-------------------------------------------------------------------------------
-- The hidden pre build
-------------------------------------------------------------------------------

local function Built(page, tab)
    local rec = I.ui.tabs[page .. "/" .. tab]
    return rec ~= nil and rec.built == true
end

local function Pending()
    local list = {}
    for _, cat in ipairs(CW.Categories()) do
        for _, tab in ipairs(cat.tabs) do
            if not Built(cat.key, tab.key) then list[#list + 1] = { cat.key, tab.key } end
        end
    end
    return list
end

-- Builds one tab nobody has opened without leaving the page and tab you are on: the window's own hook when it has one,
-- else open the tab (which builds it) and come straight back inside the same frame, so nothing is drawn in between.
local function BuildHidden(page, tab)
    if type(CW.BuildTabHidden) == "function" then
        CW.BuildTabHidden(page, tab)
        return
    end
    local ui = I.ui
    local curPage, curTab = CW.Current()
    local rec = ui.tabRec
    local scroll = rec and rec.page and rec.page:GetVerticalScroll() or nil
    local remembered = {}
    for k, v in pairs(ui.tabFor or {}) do remembered[k] = v end
    state.building = true
    local ok, err = pcall(function()
        CW.Open(page, tab)
        if curPage then CW.Open(curPage, curTab) end
    end)
    state.building = false
    ui.tabFor = remembered
    local now = ui.tabRec
    if scroll and now and now.page and now.id == (rec and rec.id) then
        now.page:SetVerticalScroll(scroll)
        CW.RefreshScroll()
    end
    if not ok then Forward(err) end
end

-- One step of the pre build; true while there is more to do. Waits while the window is shut and in combat.
function Search.Step()
    if not state.prebuilding then return false end
    if not CW.IsShown() then return true end
    if type(InCombatLockdown) == "function" and InCombatLockdown() then return true end
    if not state.queue or #state.queue == 0 then
        state.queue = Pending()
        if #state.queue == 0 then
            state.prebuilding, state.queue = false, nil
            if Search.driver then Search.driver:SetScript("OnUpdate", nil) end
            return false
        end
    end
    local want = table.remove(state.queue, 1)
    if not Built(want[1], want[2]) then BuildHidden(want[1], want[2]) end
    if Search.panel and Search.panel:IsShown() then Search.Refresh() end
    if #state.queue == 0 and #Pending() == 0 then
        state.prebuilding, state.queue = false, nil
        if Search.driver then Search.driver:SetScript("OnUpdate", nil) end
        return false
    end
    return true
end

function Search.StartPrebuild()
    if state.prebuilding then return end
    if #Pending() == 0 then return end
    state.prebuilding, state.queue = true, nil
    if not Search.driver then Search.driver = CreateFrame("Frame", nil, UIParent) end
    Search.driver:SetScript("OnUpdate", Guard(function() Search.Step() end))
end

-------------------------------------------------------------------------------
-- The box and the results panel
-------------------------------------------------------------------------------

local function Crumb(item, cats)
    local entry = item.entry
    local cat = cats[entry.page]
    local parts = { cat and cat.label or entry.page }
    if cat and cat.ntabs > 1 then parts[#parts + 1] = cat.tabs[entry.tab] or entry.tab end
    if item.entry.section and item.entry.section ~= "" then parts[#parts + 1] = Plain(entry.section) end
    if not Shown(entry) then
        local gate, value = GateFor(entry)
        if gate then parts[#parts + 1] = tostring(value.text or value.value) end
    end
    return table.concat(parts, " " .. SEP .. ">|r ")
end

local function CategoryLabels()
    local cats = {}
    for _, cat in ipairs(CW.Categories()) do
        local tabs = {}
        for _, t in ipairs(cat.tabs) do tabs[t.key] = t.label end
        cats[cat.key] = { label = cat.label, tabs = tabs, ntabs = #cat.tabs }
    end
    return cats
end

-- The short word for the badge and the full line for the footer, when the row cannot be used as it stands.
local function Dim(entry)
    local off = ModuleOff(entry.page)
    if off then return "MODULE OFF", off .. " is off." end
    local disabled, reason, short = Disabled(entry)
    if disabled then return short, reason end
    if not Shown(entry) and not GateFor(entry) then return "HIDDEN", "Not shown right now." end
    return nil
end

local function VisibleCount()
    return math.min(S.RES_MAX, #state.results)
end

local function KeepSelectionInView()
    local n = #state.results
    if n == 0 then
        state.sel, state.top = 1, 1
        return
    end
    state.sel = math.max(1, math.min(n, state.sel))
    local view = math.min(S.RES_MAX, n)
    if state.sel < state.top then state.top = state.sel end
    if state.sel > state.top + view - 1 then state.top = state.sel - view + 1 end
    state.top = math.max(1, math.min(n - view + 1, state.top))
end

local function PaintFilters()
    local pink = state.changed and C.pink or C.muted
    local all = state.changed and C.muted or C.pink
    Theme.ApplyMono(Search.changedOnly.fsLabel, S.SMALL, pink)
    Theme.ApplyMono(Search.all.fsLabel, S.SMALL, all)
end

local function PaintBox()
    local edit = Search.edit
    if not edit then return end
    local text = edit:GetText() or ""
    local active = edit:HasFocus() or text ~= ""
    if active then
        I.Restyle(Search.box, C.cyan, C.muted, C.track, 0.35)
    else
        I.Restyle(Search.box, DIM, C.muted, C.track, 0)
    end
    Search.placeholder:SetShown(text == "")
    Search.clear:SetShown(text ~= "")
end

local function PaintBadge(row, text, pink)
    local badge = row.fsBadge
    if not text then
        badge:Hide()
        row.fsBadgeText:SetText("")
        return 0
    end
    row.fsBadgeText:SetText(text)
    local color = pink and C.pink or DIS
    Theme.ApplyMono(row.fsBadgeText, S.SMALL, color)
    local w = S.Snap((row.fsBadgeText:GetStringWidth() or 0) + 8)
    badge:SetWidth(w)
    for _, edge in ipairs(badge.fsEdges) do
        edge:SetColorTexture((pink and PINK_EDGE or DISEDGE)[1], (pink and PINK_EDGE or DISEDGE)[2], (pink and PINK_EDGE or DISEDGE)[3], 1)
    end
    badge:Show()
    return w
end

-- Draws the box and, when there is something to list, the panel under it.
function Search.Paint()
    local panel = Search.panel
    if not panel then return end
    PaintBox()
    local edit = Search.edit
    local active = state.text ~= "" or state.changed
    if not (active and edit:HasFocus()) then
        panel:Hide()
        return
    end
    PaintFilters()
    local total = #state.results
    local view = VisibleCount()
    KeepSelectionInView()
    local cats = CategoryLabels()
    local q = Squash(state.text)
    local footerNote
    for i = 1, S.RES_MAX do
        local row = Search.rows[i]
        local res = state.results[state.top + i - 1]
        if i <= view and res then
            local item = res.item
            local entry = item.entry
            row.fsResult = item
            local short, long = Dim(entry)
            row.fsDim = short ~= nil
            local changed = not short and I.EntryChanged(entry)
            local w = PaintBadge(row, short or (changed and "CHANGED" or nil), not short and changed)
            row.fsL1:ClearAllPoints()
            row.fsL1:SetPoint("TOPLEFT", row, "TOPLEFT", ROW_PAD_L, -ROW_PAD_T)
            row.fsL1:SetPoint("RIGHT", row, "RIGHT", -(BADGE_R + (w > 0 and w + 8 or 0)), 0)
            Theme.ApplyMono(row.fsL1, S.TEXT, short and DIS2 or C.text)
            row.fsL1:SetText(Mark(item.label, q))
            Theme.ApplyMono(row.fsL2, S.SMALL, C.muted)
            row.fsL2:SetText(Crumb(item, cats))
            local selected = state.top + i - 1 == state.sel
            row.fsSel:SetShown(selected)
            row.fsBar:SetShown(selected)
            if selected and short then footerNote = long end
            row:Show()
        else
            row.fsResult, row.fsDim = nil, nil
            row:Hide()
        end
    end
    Search.header.count:SetText(("%d FOUND"):format(total))
    Search.empty:SetShown(total == 0)
    panel:SetHeight(2 + S.RES_HEAD_H + math.max(1, view) * S.RES_ROW_H + S.RES_FOOT_H)
    if footerNote then
        Search.footer:SetText(Esc(C.muted) .. Plain(footerNote) .. "|r")
    else
        Search.footer:SetText(TEXT .. "up/down|r move   " .. TEXT .. "enter|r open   " .. TEXT .. "esc|r close")
    end
    -- the rail beside a list longer than the panel
    local rail = Search.rail
    if total > S.RES_MAX then
        local room = view * S.RES_ROW_H
        local h = math.max(8, math.floor(room * view / total))
        rail.thumb:SetHeight(h)
        rail.thumb:ClearAllPoints()
        rail.thumb:SetPoint("TOP", rail, "TOP", 0, -math.floor((room - h) * (state.top - 1) / math.max(1, total - view) + 0.5))
        rail:SetHeight(room)
        rail:Show()
    else
        rail:Hide()
    end
    panel:Show()
end

-- Re-runs the query for the box as it stands.
function Search.Refresh()
    if not Search.edit then return end
    state.results = Search.Run(state.text, state.changed)
    KeepSelectionInView()
    Search.Paint()
end

local function Select(i)
    if #state.results == 0 then return end
    state.sel = math.max(1, math.min(#state.results, i))
    KeepSelectionInView()
    Search.Paint()
end

local function Scroll(delta)
    local n = #state.results
    local view = math.min(S.RES_MAX, n)
    state.top = math.max(1, math.min(math.max(1, n - view + 1), state.top + delta))
    state.sel = math.max(state.top, math.min(state.top + view - 1, state.sel))
    Search.Paint()
end

local function BuildPanel()
    local ui = I.ui
    local frame = ui.frame
    local panel = I.MakeButton(frame, { height = 10, ring = C.cyan, textColor = C.muted, fill = C.track, chamfer = 6, size = S.SMALL, glow = 0.25, text = "" })
    panel:SetWidth(S.RES_W)
    panel:SetPoint("TOPLEFT", ui.well, "TOPLEFT", -1, 1)
    panel:SetFrameLevel((frame:GetFrameLevel() or 1) + 60)
    panel:EnableMouse(true)
    panel:EnableMouseWheel(true)
    panel:SetScript("OnMouseWheel", Guard(function(_, delta) Scroll(-delta) end))
    panel:Hide()
    Search.panel = panel

    -- the header: the count on the left, all / changed only on the right
    local header = CreateFrame("Frame", nil, panel)
    header:SetSize(S.RES_W - 2, S.RES_HEAD_H)
    header:SetPoint("TOPLEFT", panel, "TOPLEFT", 1, -1)
    local count = Label(header, "", S.SMALL, DIS)
    count:SetPoint("LEFT", header, "LEFT", HEAD_PAD, 0)
    header.count = count
    local rule = header:CreateTexture(nil, "ARTWORK")
    rule:SetColorTexture(C.line[1], C.line[2], C.line[3], 1)
    rule:SetHeight(1)
    rule:SetPoint("BOTTOMLEFT", header, "BOTTOMLEFT", 0, 0)
    rule:SetPoint("BOTTOMRIGHT", header, "BOTTOMRIGHT", 0, 0)
    Search.header = header
    local function Filter(text, anchor, gap, onClick)
        local b = CreateFrame("Button", nil, header)
        b:RegisterForClicks("LeftButtonUp")
        b.fsLabel = Label(b, text, S.SMALL, C.muted)
        b.fsLabel:SetPoint("CENTER", b, "CENTER", 0, 0)
        b:SetSize((b.fsLabel:GetStringWidth() or 0) + 4, S.RES_HEAD_H)
        if anchor then b:SetPoint("RIGHT", anchor, "LEFT", -gap, 0) else b:SetPoint("RIGHT", header, "RIGHT", -HEAD_PAD, 0) end
        b:SetScript("OnEnter", function(self) Theme.ApplyMono(self.fsLabel, S.SMALL, C.cyan) end)
        b:SetScript("OnLeave", Guard(PaintFilters))
        b:SetScript("OnClick", Guard(function()
            onClick()
            state.sel, state.top = 1, 1
            Search.edit:SetFocus()
            Search.Refresh()
        end))
        return b
    end
    Search.changedOnly = Filter("changed only", nil, 0, function() state.changed = true end)
    Search.all = Filter("all", Search.changedOnly, 8, function() state.changed = false end)

    -- the rows
    Search.rows = {}
    for i = 1, S.RES_MAX do
        local row = CreateFrame("Button", nil, panel)
        row:RegisterForClicks("LeftButtonUp")
        row:SetSize(S.RES_W - 2, S.RES_ROW_H)
        row:SetPoint("TOPLEFT", panel, "TOPLEFT", 1, -(1 + S.RES_HEAD_H + (i - 1) * S.RES_ROW_H))
        row.fsSel = row:CreateTexture(nil, "BACKGROUND")
        row.fsSel:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 0.12)
        row.fsSel:SetAllPoints(row)
        row.fsBar = row:CreateTexture(nil, "ARTWORK")
        row.fsBar:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 1)
        row.fsBar:SetWidth(2)
        row.fsBar:SetPoint("TOPLEFT", row, "TOPLEFT", 0, -4)
        row.fsBar:SetPoint("BOTTOMLEFT", row, "BOTTOMLEFT", 0, 4)
        row.fsL1 = Label(row, "", S.TEXT, C.text)
        row.fsL1:SetJustifyH("LEFT")
        row.fsL1:SetWordWrap(false)
        row.fsL2 = Label(row, "", S.SMALL, C.muted)
        row.fsL2:SetJustifyH("LEFT")
        row.fsL2:SetWordWrap(false)
        row.fsL2:SetPoint("TOPLEFT", row, "TOPLEFT", ROW_PAD_L, -(ROW_PAD_T + 16))
        row.fsL2:SetPoint("RIGHT", row, "RIGHT", -BADGE_R, 0)
        local badge = CreateFrame("Frame", nil, row)
        badge:SetHeight(S.COUNT_H)
        badge:SetPoint("TOPRIGHT", row, "TOPRIGHT", -BADGE_R, -BADGE_T)
        badge.fsEdges = Outline(badge, DISEDGE, 1)
        row.fsBadge = badge
        row.fsBadgeText = Label(badge, "", S.SMALL, DIS)
        row.fsBadgeText:SetPoint("CENTER", badge, "CENTER", 0, 0)
        badge:Hide()
        row:SetScript("OnEnter", Guard(function(self)
            for j, r in ipairs(Search.rows) do
                if r == self and state.results[state.top + j - 1] then
                    state.sel = state.top + j - 1
                    Search.Paint()
                end
            end
        end))
        row:SetScript("OnClick", Guard(function(self)
            if self.fsResult then Search.Jump(self.fsResult) end
        end))
        row:Hide()
        Search.rows[i] = row
    end

    -- nothing found (frame K)
    local empty = Label(panel, "Nothing matches.", S.TEXT, C.muted)
    empty:SetPoint("TOPLEFT", panel, "TOPLEFT", ROW_PAD_L + 1, -(1 + S.RES_HEAD_H + 10))
    empty:Hide()
    Search.empty = empty

    -- the keys line, or the reason the selected result cannot be used
    local foot = CreateFrame("Frame", nil, panel)
    foot:SetSize(S.RES_W - 2, S.RES_FOOT_H)
    foot:SetPoint("BOTTOMLEFT", panel, "BOTTOMLEFT", 1, 1)
    local frule = foot:CreateTexture(nil, "ARTWORK")
    frule:SetColorTexture(C.line[1], C.line[2], C.line[3], 1)
    frule:SetHeight(1)
    frule:SetPoint("TOPLEFT", foot, "TOPLEFT", 0, 0)
    frule:SetPoint("TOPRIGHT", foot, "TOPRIGHT", 0, 0)
    Search.footer = Label(foot, "", S.SMALL, C.muted)
    Search.footer:SetPoint("LEFT", foot, "LEFT", HEAD_PAD, 0)
    Search.footer:SetPoint("RIGHT", foot, "RIGHT", -HEAD_PAD, 0)
    Search.footer:SetJustifyH("LEFT")
    Search.footer:SetWordWrap(false)

    -- a thin rail for a list longer than the panel
    local rail = CreateFrame("Frame", nil, panel)
    rail:SetWidth(2)
    rail:SetPoint("TOPRIGHT", panel, "TOPRIGHT", -3, -(1 + S.RES_HEAD_H))
    local track = rail:CreateTexture(nil, "BACKGROUND")
    track:SetColorTexture(DISEDGE[1], DISEDGE[2], DISEDGE[3], 1)
    track:SetAllPoints(rail)
    rail.thumb = CreateFrame("Frame", nil, rail)
    rail.thumb:SetWidth(2)
    local thumb = rail.thumb:CreateTexture(nil, "ARTWORK")
    thumb:SetColorTexture(DIM[1], DIM[2], DIM[3], 1)
    thumb:SetAllPoints(rail.thumb)
    rail:Hide()
    Search.rail = rail
end

-- Esc clears the box first (and the filter); a second Esc leaves it.
local function OnEscape()
    local edit = Search.edit
    if state.text ~= "" or state.changed or (edit:GetText() or "") ~= "" then
        state.silent = true
        edit:SetText("")
        state.silent = false
        state.text, state.changed = "", false
        state.results, state.sel, state.top = {}, 1, 1
        Search.Paint()
    else
        edit:ClearFocus()
    end
end

local function OnTextChanged()
    if state.silent then return end
    local edit = Search.edit
    local text = edit:GetText() or ""
    Search.ClearHighlight()
    if text ~= state.text then state.sel, state.top = 1, 1 end
    state.text = text
    Search.Refresh()
end

local function BuildBox()
    local slot = CW.SearchSlot()
    if not slot then return end
    local box = I.MakeButton(slot, { height = S.SEARCH_H, ring = DIM, textColor = C.muted, fill = C.track, chamfer = 4, size = S.TEXT, glow = 0, text = "" })
    box:SetPoint("TOPLEFT", slot, "TOPLEFT", 0, 0)
    box:SetPoint("BOTTOMRIGHT", slot, "BOTTOMRIGHT", 0, 0)
    Search.box = box

    local prompt = Label(box, ">", S.TEXT, C.cyan)
    prompt:SetPoint("CENTER", box, "LEFT", S.SEARCH_PROMPT_W / 2, 0)
    Search.prompt = prompt
    local divider = box:CreateTexture(nil, "ARTWORK")
    divider:SetColorTexture(C.line[1], C.line[2], C.line[3], 1)
    divider:SetWidth(1)
    divider:SetPoint("TOPLEFT", box, "TOPLEFT", S.SEARCH_PROMPT_W - 1, -1)
    divider:SetPoint("BOTTOMLEFT", box, "BOTTOMLEFT", S.SEARCH_PROMPT_W - 1, 1)

    local edit = CreateFrame("EditBox", nil, box)
    edit:SetPoint("LEFT", box, "LEFT", S.SEARCH_PROMPT_W + 8, 0)
    edit:SetPoint("RIGHT", box, "RIGHT", -S.SEARCH_PROMPT_W, 0)
    edit:SetHeight(S.SEARCH_H - 4)
    edit:SetFont(Theme.FONT_MONO, S.TEXT, "")
    edit:SetTextColor(C.text[1], C.text[2], C.text[3], 1)
    edit:SetAutoFocus(false)
    edit:SetMaxLetters(40)
    -- configwindow-harness.py finds a dialog's edit box as the first visible one without this flag, which it names for the
    -- slider boxes; the search box is a window box too, so it says the same.
    edit.fsSlider = true
    Search.edit = edit

    local placeholder = Label(box, "search settings", S.TEXT, C.muted)
    placeholder:SetPoint("LEFT", edit, "LEFT", 0, 0)
    placeholder:SetAlpha(0.75)
    Search.placeholder = placeholder

    local clear = CreateFrame("Button", nil, box)
    clear:RegisterForClicks("LeftButtonUp")
    clear:SetSize(S.SEARCH_PROMPT_W, S.SEARCH_H - 2)
    clear:SetPoint("RIGHT", box, "RIGHT", -1, 0)
    clear.fsLabel = Label(clear, "x", S.TEXT, C.muted)
    clear.fsLabel:SetPoint("CENTER", clear, "CENTER", 0, 0)
    clear:SetScript("OnEnter", function(self) Theme.ApplyMono(self.fsLabel, S.TEXT, C.pink) end)
    clear:SetScript("OnLeave", function(self) Theme.ApplyMono(self.fsLabel, S.TEXT, C.muted) end)
    clear:SetScript("OnClick", Guard(function()
        edit:SetText("")
        OnTextChanged()
        edit:SetFocus()
    end))
    clear:Hide()
    Search.clear = clear

    -- a click on the prompt or the empty edge puts the keyboard in the box
    box:SetScript("OnClick", function() edit:SetFocus() end)

    edit:SetScript("OnEditFocusGained", Guard(function(self)
        I.SliderFocused(self)
        Search.StartPrebuild()
        Search.Refresh()
    end))
    edit:SetScript("OnEditFocusLost", Guard(function(self)
        I.SliderFocused(nil, self)
        PaintBox()
        local panel = Search.panel
        if panel and panel:IsShown() and not (panel.IsMouseOver and panel:IsMouseOver()) then panel:Hide() end
    end))
    edit:SetScript("OnTextChanged", Guard(OnTextChanged))
    edit:SetScript("OnEscapePressed", Guard(OnEscape))
    edit:SetScript("OnTabPressed", function(self) self:ClearFocus() end)
    edit:SetScript("OnEnterPressed", Guard(function()
        local res = state.results[state.sel]
        if res then Search.Jump(res.item) end
    end))
    edit:SetScript("OnArrowPressed", Guard(function(_, key)
        if key == "DOWN" then Select(state.sel + 1) elseif key == "UP" then Select(state.sel - 1) end
    end))

    BuildPanel()
    PaintBox()
    PaintFilters()
end

-- Whatever was typed or outlined goes when the window closes or you pick a page or tab yourself.
function Search.Reset()
    Search.ClearHighlight()
    ClearBox(true)
end

CW.On("show", function()
    if not Search.box then BuildBox() end
end)
CW.On("hide", function()
    if Search.box then Search.Reset() end
end)
CW.On("select", function()
    if state.jumping or state.building then return end
    if Search.box then Search.Reset() end
end)
