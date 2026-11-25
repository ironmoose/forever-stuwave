-- Forever STUwave: Config builders
-- The FS.ConfigWindow.UI builders every page uses, plus the popup menu and the confirm / prompt dialog. A builder takes
-- (content, opts), seats itself as the next row of the tab it is building in, binds `key` to FS.Config (or `get` / `set`),
-- registers one refresh with Track, records itself in the row registry (CW.Rows()) and returns its row; `row.control` is
-- the clickable part. Sizes come from CW.Spec; the window chrome and the flow live in ConfigWindow.lua.

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI
local I = CW.I
local S = CW.Spec
local D = CW.D
local C = CW.C

local Theme = FS.Theme
local Config = FS.Config

local ui, menuState, dialogState = I.ui, I.menuState, I.dialogState
local Forward, Writable, Capitalize, Say = I.Forward, I.Writable, I.Capitalize, I.Say
local Mix, Tint, Label, Outline, Disc, TintAll = I.Mix, I.Tint, I.Label, I.Outline, I.Disc, I.TintAll
local SetLook, Track = I.SetLook, I.Track

local SLIDER_BAR_H = 2          -- the rail and fill of a slider are two units thick
local MENU_ITEM_H = S.MENU_ROW_H

-------------------------------------------------------------------------------
-- Pixel arrows
-------------------------------------------------------------------------------

-- The arrows of this window are drawn, not typed. The bundled fonts (the window's Mononoki included) carry neither U+25B8 nor
-- U+25BE, the prototype's small triangles, and the ASCII stand-ins read as what they are: ">" is a greater-than sign and "v" a
-- letter. So an arrow is a few rects ({ x, y, w, h } from the glyph's top left, one run per column or row), centred on a host
-- frame so every edge lands on a whole unit: left and right are 4 by 8, up and down 8 by 4. Used by the Order arrows, the tab
-- mark, the section chevrons and the Dropdown caret.
local ARROW_W, ARROW_H = 4, 8   -- the horizontal arrows' size; the tab mark frame takes it
local ARROW_RUNS = {
    left = { { 0, 3, 1, 2 }, { 1, 2, 1, 4 }, { 2, 1, 1, 6 }, { 3, 0, 1, 8 } },
    right = { { 0, 0, 1, 8 }, { 1, 1, 1, 6 }, { 2, 2, 1, 4 }, { 3, 3, 1, 2 } },
    up = { { 3, 0, 2, 1 }, { 2, 1, 4, 1 }, { 1, 2, 6, 1 }, { 0, 3, 8, 1 } },
    down = { { 0, 0, 8, 1 }, { 1, 1, 6, 1 }, { 2, 2, 4, 1 }, { 3, 3, 2, 1 } },
}
local ARROW_SIZE = { left = { 4, 8 }, right = { 4, 8 }, up = { 8, 4 }, down = { 8, 4 } }
local ARROW_DIS = { 0.361, 0.329, 0.502, 1 }   -- the window's dim violet (--dis)

local function NewArrowGlyph(host, direction)
    local runs, size = ARROW_RUNS[direction], ARROW_SIZE[direction]
    if not runs then error("arrow direction '" .. tostring(direction) .. "' is not left, right, up or down", 2) end
    local w, h = size[1], size[2]
    local glyph = { textures = {}, direction = direction, width = w, height = h }
    for _, r in ipairs(runs) do
        local t = host:CreateTexture(nil, "OVERLAY", nil, 1)
        t:SetSize(r[3], r[4])
        t:SetPoint("TOPLEFT", host, "CENTER", -w / 2 + r[1], h / 2 - r[2])
        glyph.textures[#glyph.textures + 1] = t
    end
    function glyph.SetColor(color)
        for _, t in ipairs(glyph.textures) do t:SetColorTexture(color[1], color[2], color[3], color[4] or 1) end
    end
    function glyph.SetShown(shown)
        for _, t in ipairs(glyph.textures) do t:SetShown(shown) end
    end
    return glyph
end
I.NewArrowGlyph, I.ARROW_W, I.ARROW_H = NewArrowGlyph, ARROW_W, ARROW_H

-- The reset mark (U+21BA, a turn back arrow) is drawn the same way: the fonts carry no glyph for it, so typed it showed as an
-- empty box. 8 by 8, one rect per run of lit pixels in each row, centred on the host.
local RESET_ROWS = {
    "X.XXXX..",
    "XX....X.",
    "XXX....X",
    ".......X",
    ".......X",
    "X......X",
    ".X....X.",
    "..XXXX..",
}
local function NewResetGlyph(host, color)
    local h, w = #RESET_ROWS, #RESET_ROWS[1]
    local textures = {}
    for y, row in ipairs(RESET_ROWS) do
        local x = 1
        while x <= w do
            if row:sub(x, x) == "X" then
                local run = x
                while run + 1 <= w and row:sub(run + 1, run + 1) == "X" do run = run + 1 end
                local t = host:CreateTexture(nil, "OVERLAY", nil, 1)
                t:SetSize(run - x + 1, 1)
                t:SetPoint("TOPLEFT", host, "CENTER", -w / 2 + (x - 1), h / 2 - (y - 1))
                t:SetColorTexture(color[1], color[2], color[3], color[4] or 1)
                textures[#textures + 1] = t
                x = run + 1
            else
                x = x + 1
            end
        end
    end
    return textures
end

local CHEV_CELL = 8   -- the square a chevron or caret is centred in; the chevron's is the gutter the page leaves left of the content

-------------------------------------------------------------------------------
-- Rows
-------------------------------------------------------------------------------

local function TextWidth(fs)
    return fs:GetStringWidth() or 0
end

-- The row every labelled control is built on: the label (and its ? icon) on the left, the control the builder adds on the
-- right. `sub` indents it under the row above with the short tree line.
local function NewRow(content, o, kind)
    local row = CreateFrame("Frame", nil, content)
    row:SetHeight(o.height or S.ROW_H)
    local inset = o.inset or (o.sub and S.SUB_INSET or 0)
    row.fsLabel = Label(row, o.label, o.size or S.TEXT, C.text)
    row.fsLabel:SetPoint("LEFT", row, "LEFT", inset, 0)
    if o.tip then
        row.fsHelp = UI.HelpIcon(row, o.tip)
        row.fsHelp:SetPoint("LEFT", row.fsLabel, "RIGHT", S.Q_GAP, 0)
    end
    if o.sub then
        local down = row:CreateTexture(nil, "ARTWORK")
        down:SetColorTexture(C.line[1], C.line[2], C.line[3], 1)
        down:SetSize(1, S.ROW_H / 2)
        down:SetPoint("TOPLEFT", row, "TOPLEFT", 4, 0)
        local across = row:CreateTexture(nil, "ARTWORK")
        across:SetColorTexture(C.line[1], C.line[2], C.line[3], 1)
        across:SetSize(7, 1)
        across:SetPoint("TOPLEFT", row, "TOPLEFT", 4, -S.ROW_H / 2)
        row.fsTree = { down, across }
    end
    row.fsWhen = o.when
    UI.Stack(content, row, o.half)
    local entry = I.Register(row, o, kind or "row")
    entry.opts = o
    if o.needs or o.enabled then
        if o.enabled and not (o.needs or o.reason) then
            Forward("row '" .. tostring(o.label) .. "' has enabled() but neither needs nor reason")
        end
        if not row.fsHelp then
            row.fsHelp = UI.HelpIcon(row, "")
            row.fsHelp:SetPoint("LEFT", row.fsLabel, "RIGHT", S.Q_GAP, 0)
            row.fsHelp:Hide()
        end
        I.TrackState(function() I.ApplyRowState(row, o, entry) end)
    end
    return row
end
I.NewRow = NewRow

-- Whether a row is switched off now, and the line that says why. `needs` is the key of the switch that must be on (its
-- label comes from the registry unless `nl` names it); `enabled` is a function, `reason` the line to show for it.
local function RowReason(o)
    if o.needs then
        local parent = CW.RowByKey(o.needs)
        local value = Config.Get(o.needs)
        local on = (parent and parent.inverted) and value ~= true or (not (parent and parent.inverted) and value == true)
        if not on then
            local name = o.nl or (parent and parent.label) or tostring(o.needs)
            return true, "Requires |cffffffff" .. name .. "|r to be on."
        end
    end
    if o.enabled then
        local ok, value = pcall(o.enabled)
        if not (ok and value == true) then return true, o.reason end
    end
    return false
end

-- The default as the row itself would show it ("on", "10 px", "Automatic"), or nil when the row has no registered default
-- to look up (a get / set row, a colour) and the plain changed line has to do.
local function DefaultText(entry)
    local key = entry.cfgKey
    local default = key and Config.GetDefault(key)
    if default == nil or type(default) == "table" then return nil end
    local o = entry.opts or {}
    if type(default) == "boolean" then
        if entry.inverted then default = not default end
        return default and "on" or "off"
    end
    if entry.kind == "slider" then
        local fmt = o.fmt
        local ok, text = pcall(function()
            if type(fmt) == "function" then return fmt(default) end
            return (fmt or "%s"):format(default)
        end)
        return ok and tostring(text) or tostring(default)
    elseif entry.kind == "segmented" then
        for _, option in ipairs(o.options or {}) do
            if option.value == default then return tostring(option.text) end
        end
    elseif entry.kind == "dropdown" and o.text then
        local ok, text = pcall(o.text, default)
        if ok then return tostring(text) end
    end
    return tostring(default)
end

-- The ? tip of a row: the plain tip, or (when the row is off) its label, the reason and the tip, and a last line when the
-- value differs from its default ("Changed. Default: <value>").
function I.RefreshTip(row)
    local icon, entry = row.fsHelp, row.fsEntry
    if not (icon and entry) then return end
    local o = entry.opts
    local parts = {}
    local off = entry.disabled
    if off then
        parts[#parts + 1] = o.label or ""
        if entry.why then parts[#parts + 1] = entry.why end
    end
    if o.tip then parts[#parts + 1] = o.tip end
    local changed = I.EntryChanged(entry)
    if changed then
        local default = DefaultText(entry)
        parts[#parts + 1] = default and ("Changed. Default: " .. default) or "Changed from the default."
    end
    icon.fsTip = table.concat(parts, "\n")
    icon:SetShown(off or o.tip ~= nil or changed)
    icon:SetAlpha(1)
end

-- Run before the controls' own refreshes: dims the label, marks the row off, and puts the reason first in the ? tip.
function I.ApplyRowState(row, o, entry)
    local off, reason = RowReason(o)
    row.fsRowOff = off or nil
    entry.disabled, entry.why = off, reason
    row.fsLabel:SetAlpha(off and 0.4 or 1)
    I.RefreshTip(row)
end

-- The changed dot, the reset button and the tip's last line for one keyed (or isChanged / reset) row. `edge` is the
-- control part furthest left: the reset button sits CTL_GAP to its left.
function I.AttachChanged(row, edge)
    local entry = row.fsEntry
    if not entry or entry.nodot then return end
    if not (entry.cfgKey or entry.isChanged) then return end
    local dot = row:CreateTexture(nil, "OVERLAY")
    dot:SetColorTexture(C.pink[1], C.pink[2], C.pink[3], 1)
    dot:SetSize(S.DOT, S.DOT)
    -- the page clips PAD_X (8) left of the content: keep the dot inside it
    dot:SetPoint("LEFT", row, "LEFT", math.max(S.DOT_X, -8), 0)
    dot:Hide()
    local glow = row:CreateTexture(nil, "BACKGROUND")
    glow:SetColorTexture(C.pink[1], C.pink[2], C.pink[3], 0.25)
    glow:SetSize(S.DOT + 4, S.DOT + 4)
    glow:SetPoint("CENTER", dot, "CENTER", 0, 0)
    glow:Hide()
    local reset = I.MakeButton(row, { width = S.RESET, height = S.RESET, ring = C.line, textColor = C.cyan, chamfer = 3,
        text = "", glow = 0 })
    reset.fsGlyph = NewResetGlyph(reset, C.cyan)
    reset:SetPoint("RIGHT", edge or row.control or row, "LEFT", -S.CTL_GAP, 0)
    I.HoverStyle(reset, C.cyan)
    reset:Hide()
    reset:SetAlpha(0.45)
    reset:SetScript("OnClick", function()
        if not Writable() then return end
        I.EntryReset(entry)
        CW.RefreshAll()
    end)
    reset:HookScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetText("Reset to the default", 1, 1, 1, 1, true)
        GameTooltip:Show()
    end)
    reset:HookScript("OnLeave", function() GameTooltip:Hide() end)
    row.fsDot, row.fsReset = dot, reset
    entry.resetButton = reset
    Track(function()
        local changed = I.EntryChanged(entry)
        dot:SetShown(changed)
        glow:SetShown(changed)
        reset:SetShown(changed)
        reset:SetAlpha(ui.hover == entry and 1 or 0.45)
        I.RefreshTip(row)
    end)
end

CW.On("rowEnter", function(entry) if entry.resetButton then entry.resetButton:SetAlpha(1) end end)
CW.On("rowLeave", function(entry) if entry.resetButton then entry.resetButton:SetAlpha(0.45) end end)

-------------------------------------------------------------------------------
-- Help icon
-------------------------------------------------------------------------------

-- A small circled ? whose tooltip carries the explanation, in the addon's skinned GameTooltip.
function UI.HelpIcon(parent, tip)
    local icon = CreateFrame("Frame", nil, parent)
    icon:SetSize(S.Q, S.Q)
    icon:EnableMouse(true)
    icon.fsTip = tip
    local ringColor = Mix(C.violet, C.line, 0.3)
    local ring = Disc(icon, S.Q, ringColor, 0)
    Disc(icon, S.Q - 2, C.track, 1)
    local glyph = Label(icon, "?", 9, C.muted)
    glyph:SetPoint("CENTER", icon, "CENTER", 0, 0)
    icon:SetScript("OnEnter", function(self)
        TintAll(ring, C.cyan)
        Theme.ApplyMono(glyph, 9, C.cyan)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetText(self.fsTip, 1, 1, 1, 1, true)
        GameTooltip:Show()
    end)
    icon:SetScript("OnLeave", function()
        TintAll(ring, ringColor)
        Theme.ApplyMono(glyph, 9, C.muted)
        GameTooltip:Hide()
    end)
    return icon
end

-------------------------------------------------------------------------------
-- Section header
-------------------------------------------------------------------------------

-- UI.Section(content, { title, tip, fold, two, meta, when }) starts a section: the "// TITLE" header with an optional ?,
-- a right meta slot and a rule to the right edge. `fold` makes the header click to fold the section (it starts folded, and
-- the choice is saved account wide); `two` lays the rows out in two columns; `when` hides the whole section. Returns the
-- section table: { title, header, meta, SetMeta(text), folded }. A plain title string works too.
function UI.Section(content, o)
    if type(o) == "string" then o = { title = o } end
    o = o or {}
    local title = tostring(o.title or "")
    local rec = I.TabRecOf(content)
    local id = (rec and rec.id or "?") .. "/" .. title
    local sec = { title = title, tip = o.tip, two = o.two == true, when = o.when, id = id }
    -- a section never folds on the Class modules page, whatever it declares
    sec.foldable = o.fold == true and not (rec and rec.cat.key == "classmod")
    sec.folded = sec.foldable and CW.IsFolded(id, true) or false
    local header = CreateFrame("Button", nil, content)
    header:SetHeight(S.SEC_H)
    header:RegisterForClicks("LeftButtonUp")
    local slash = Label(header, "//", S.TEXT, C.line)
    slash:SetPoint("LEFT", header, "LEFT", 0, 0)
    local text = Label(header, title:upper(), S.TEXT, C.violet)
    text:SetPoint("LEFT", slash, "RIGHT", 8, 0)
    local last = text
    if o.tip then
        local icon = UI.HelpIcon(header, o.tip)
        icon:SetPoint("LEFT", text, "RIGHT", S.Q_GAP, 0)
        last = icon
    end
    local meta = Label(header, "", S.SMALL, C.muted)
    meta:SetPoint("RIGHT", header, "RIGHT", 0, 0)
    -- the changed count: a pink "• N" after the title (and its ?) while any row of the section differs from its default
    local chip = Label(header, "", S.SMALL, C.pink)
    chip:SetPoint("LEFT", last, "RIGHT", 8, 0)
    chip:Hide()
    local rule = header:CreateTexture(nil, "ARTWORK")
    rule:SetColorTexture(C.violet[1], C.violet[2], C.violet[3], 0.35)
    rule:SetHeight(1)
    rule:SetPoint("LEFT", last, "RIGHT", 8, 0)
    local metaOn = false
    local function SeatRule(hasMeta)
        metaOn = hasMeta
        local from = (sec.changed or 0) > 0 and chip or last
        rule:ClearAllPoints()
        rule:SetPoint("LEFT", from, "RIGHT", 8, 0)
        if hasMeta then rule:SetPoint("RIGHT", meta, "LEFT", -8, 0)
        elseif sec.button then rule:SetPoint("RIGHT", sec.button, "LEFT", -8, 0)
        else rule:SetPoint("RIGHT", header, "RIGHT", 0, 0) end
    end
    sec.SeatRule = function() SeatRule(metaOn) end
    SeatRule(false)
    function sec.SetChanged(count)
        count = count or 0
        if sec.changed == count then return end
        sec.changed = count
        chip:SetText("\226\128\162 " .. count)
        chip:SetShown(count > 0)
        SeatRule(metaOn)
    end
    function sec.SetMeta(value)
        value = value and tostring(value) or ""
        meta:SetText(value)
        SeatRule(value ~= "")
    end
    if type(o.meta) == "string" then sec.SetMeta(o.meta) end
    sec.header, sec.meta, sec.text = header, meta, text
    header.fsSection = sec
    if sec.foldable then
        -- The fold chevron (the prototype's .chev): a pixel triangle in the 8 unit gutter the page's clip leaves left of the
        -- content, pointing right while folded and down while open. Dim violet while folded, cyan while the header is hovered,
        -- and nothing while it is open and idle. The player's own click flips it; a search jump that opens the section calls
        -- sec.PaintChevron().
        local cell = CreateFrame("Frame", nil, header)
        cell:SetSize(CHEV_CELL, CHEV_CELL)
        cell:SetPoint("LEFT", header, "LEFT", -CHEV_CELL, 0)
        cell.fsGlyphs = { right = NewArrowGlyph(cell, "right"), down = NewArrowGlyph(cell, "down") }
        sec.chevron = cell
        local lit = false
        function sec.PaintChevron()
            local folded = sec.folded == true
            cell.fsGlyphs.right.SetShown(folded)
            cell.fsGlyphs.down.SetShown(not folded)
            cell.fsGlyph = folded and cell.fsGlyphs.right or cell.fsGlyphs.down
            cell.fsGlyph.SetColor(lit and C.cyan or ARROW_DIS)
            cell:SetShown(folded or lit)
        end
        sec.PaintChevron()
        header:SetScript("OnEnter", function() lit = true; Theme.ApplyMono(text, S.TEXT, C.cyan); sec.PaintChevron() end)
        header:SetScript("OnLeave", function() lit = false; Theme.ApplyMono(text, S.TEXT, C.violet); sec.PaintChevron() end)
        header:SetScript("OnClick", function()
            sec.folded = not sec.folded
            CW.SetFolded(id, sec.folded)
            sec.PaintChevron()
            CW.RefreshScroll()
        end)
    end
    UI.StackHeader(content, header, sec)
    if type(o.meta) == "function" then
        Track(function() sec.SetMeta(o.meta()) end)
    end
    return sec
end

-- The old name: a section that never folds.
function UI.Header(content, text, tip)
    local sec = UI.Section(content, { title = text, tip = tip })
    return sec.header
end

-------------------------------------------------------------------------------
-- Buttons
-------------------------------------------------------------------------------

local function MakeButton(parent, o)
    local b = CreateFrame("Button", nil, parent)
    if o.width then b:SetSize(o.width, o.height) else b:SetHeight(o.height) end
    b:RegisterForClicks("LeftButtonUp")
    b.fsRing = o.ring
    b.fsFill = Theme.AddCutSliceFill(b, o.fill or C.ink, o.chamfer)
    b.fsSkin = Theme.SkinButton(b, { borderColor = o.ring, chamfer = o.chamfer, glowAlpha = o.glow or 0.35 })
    b.fsLabel = Label(b, o.text or "", o.size or S.TEXT, o.textColor)
    b.fsLabel:SetPoint("CENTER", b, "CENTER", 0, 0)
    return b
end

-- Retints a button's ring, glow, fill and label together (selected, hovered or plain).
local function Restyle(b, ring, textColor, fill, glow)
    Tint(b.fsSkin and b.fsSkin.border and b.fsSkin.border.ring, ring, 1)
    Tint(b.fsSkin and b.fsSkin.glow, ring, glow)
    Tint(b.fsFill, fill, 1)
    Theme.ApplyMono(b.fsLabel, select(2, b.fsLabel:GetFont()) or S.TEXT, textColor)
    b.fsRing = ring
end

local function HoverStyle(b, ring)
    b:SetScript("OnEnter", function(self)
        if self.fsSelected or not self:IsEnabled() then return end
        Tint(self.fsFill, Mix(C.ink, ring, 0.16), 1)
    end)
    b:SetScript("OnLeave", function(self)
        if self.fsSelected then return end
        Tint(self.fsFill, C.ink, 1)
    end)
    b:SetScript("OnMouseDown", function(self)
        if self.fsSelected or not self:IsEnabled() then return end
        Tint(self.fsFill, Mix(C.ink, ring, 0.3), 1)
    end)
    b:SetScript("OnMouseUp", function(self)
        if self.fsSelected or not self:IsEnabled() then return end
        Tint(self.fsFill, Mix(C.ink, ring, 0.16), 1)
    end)
end

I.MakeButton, I.Restyle, I.HoverStyle = MakeButton, Restyle, HoverStyle

local function BuildButton(parent, o)
    local ring = o.warn and C.pink or (o.big and C.cyan or C.violet)
    local textColor = o.warn and C.pink or C.cyan
    local b = MakeButton(parent, {
        height = o.big and 36 or S.BTN_H, ring = ring, textColor = textColor,
        chamfer = 6, size = o.big and 14 or S.TEXT, text = o.text,
    })
    if not o.big then
        -- a box sized by its text rounds its width up to the next TEXT_SNAP
        b:SetWidth(S.Snap(TextWidth(b.fsLabel) + 2 * S.BTN_PAD_X))
    end
    b.fsWarn = o.warn == true
    b.fsStretch = o.big == true
    HoverStyle(b, ring)
    if o.enabled and not o.reason then
        Forward("button '" .. tostring(o.text) .. "' has enabled() but no reason")
    end
    if o.reason then
        b:HookScript("OnEnter", function(self)
            if self:IsEnabled() then return end
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:SetText(o.reason, 1, 1, 1, 1, true)
            GameTooltip:Show()
        end)
        b:HookScript("OnLeave", function() GameTooltip:Hide() end)
    end
    b:SetScript("OnClick", function(self)
        if not self:IsEnabled() then return end
        local function run()
            if o.onClick then o.onClick(self) end
            CW.RefreshAll()
        end
        local confirm = o.confirm
        if type(confirm) == "function" then confirm = confirm() end
        if confirm then UI.Confirm(confirm, run) else run() end
    end)
    Track(function()
        SetLook(b, Writable() and (o.enabled == nil or o.enabled() == true))
    end)
    return b
end

-- {text, big, warn, onClick, confirm}. With `label` (and optional `tip`) the button sits at the right
-- of a label row. `enabled` is an optional function re-read on refresh. `confirm` may be a function.
function UI.Button(content, o)
    if o.label then
        local row = NewRow(content, o, "button")
        local b = BuildButton(row, o)
        b:SetPoint("RIGHT", row, "RIGHT", 0, 0)
        row.control = b
        return row
    end
    local b = BuildButton(content, o)
    return UI.Stack(content, b)
end

-- A small window style button in a section header's right end (the alert sections' Test toggle): { text, onClick, tip }. The
-- header's meta text and rule make room for it. Returns the button; b.Relabel(text) changes its text and re-sizes it.
function UI.SectionButton(sec, o)
    local b = BuildButton(sec.header, o)
    b:SetPoint("RIGHT", sec.header, "RIGHT", 0, 0)
    sec.button = b
    sec.meta:ClearAllPoints()
    sec.meta:SetPoint("RIGHT", b, "LEFT", -8, 0)
    if sec.SeatRule then sec.SeatRule() end
    function b.Relabel(text)
        b.fsLabel:SetText(text)
        b:SetWidth(S.Snap(TextWidth(b.fsLabel) + 2 * S.BTN_PAD_X))
    end
    if o.tip then
        b:HookScript("OnEnter", function(self)
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:SetText(o.tip, 1, 1, 1, 1, true)
            GameTooltip:Show()
        end)
        b:HookScript("OnLeave", function() GameTooltip:Hide() end)
    end
    return b
end

-- A row of buttons side by side: a list of the same tables UI.Button takes.
function UI.ButtonRow(content, list)
    local row = CreateFrame("Frame", nil, content)
    row:SetHeight(S.ROW_H)
    local prev
    for _, o in ipairs(list) do
        local b = BuildButton(row, o)
        if prev then b:SetPoint("LEFT", prev, "RIGHT", S.CTL_GAP, 0) else b:SetPoint("LEFT", row, "LEFT", 0, 0) end
        prev = b
    end
    return UI.Stack(content, row)
end

-- {label, tip, buttons = { {text, warn, onClick, confirm, enabled}, ... }}: a labelled row with several buttons at the right.
function UI.Acts(content, o)
    local row = NewRow(content, o, "acts")
    local prev
    row.fsButtons = {}
    for i = #o.buttons, 1, -1 do
        local b = BuildButton(row, o.buttons[i])
        if prev then b:SetPoint("RIGHT", prev, "LEFT", -S.CTL_GAP, 0) else b:SetPoint("RIGHT", row, "RIGHT", 0, 0) end
        prev = b
        table.insert(row.fsButtons, 1, b)
    end
    row.control = row.fsButtons[1]
    return row
end

-------------------------------------------------------------------------------
-- Toggle and segmented control
-------------------------------------------------------------------------------

-- A switch row with `inverted` shows the opposite of the stored flag: "Show player frame" over unitFrames.hidePlayer.
local function ReadValue(o)
    local value
    if o.key then value = Config.Get(o.key) else value = o.get() end
    if o.inverted then return value ~= true end
    return value
end

local function WriteValue(o, value)
    if o.inverted then value = not (value == true) end
    local ok, result
    if o.key then ok, result = pcall(Config.Set, o.key, value) else ok, result = pcall(o.set, value) end
    if not ok then
        Forward(result)
        Say("that setting could not be changed.")
    elseif result == false then
        Say("settings are read-only this session.")
    end
    return ok and result ~= false
end

local function MakeToggle(parent)
    local b = CreateFrame("Button", nil, parent)
    b:SetSize(S.SW_W, S.SW_H)
    b:RegisterForClicks("LeftButtonUp")
    b.fsFill = Theme.AddCutSliceFill(b, C.track, 4)
    b.fsSkin = Theme.SkinButton(b, { borderColor = C.line, chamfer = 4, glowAlpha = 0 })
    local knob = CreateFrame("Frame", nil, b)
    knob:SetSize(S.KNOB_W, S.KNOB_H)
    b.fsKnob = knob
    knob.fsFill = Theme.AddCutSliceFill(knob, C.knob, 3)
    return b
end

local function PaintToggle(b, on)
    b.fsChecked = on
    local ring = on and C.cyan or C.line
    Tint(b.fsSkin.border.ring, ring, 1)
    Tint(b.fsSkin.glow, C.cyan, on and 0.35 or 0)
    Tint(b.fsFill, on and Mix(C.track, C.cyan, 0.14) or C.track, 1)
    Tint(b.fsKnob.fsFill, on and C.cyan or C.knob, 1)
    b.fsKnob:ClearAllPoints()
    b.fsKnob:SetPoint(on and "RIGHT" or "LEFT", b, on and "RIGHT" or "LEFT", on and -S.KNOB_INSET or S.KNOB_INSET, 0)
end

-- {label, key, get, set, tip, half, master, reload, inverted}: bound to FS.Config.Get/Set(key), or to get()/set(v).
-- `reload` (master rows) is a function returning the line to show beside a Reload button, or nil for none: the
-- part of a change that only a /reload can apply, so the row never silently does nothing.
function UI.Toggle(content, o)
    local master = o.master == true
    local row = NewRow(content, {
        label = o.label, tip = o.tip, half = o.half, height = master and S.ROW_H + 2 or S.ROW_H,
        size = master and 12 or S.TEXT, inset = master and 10 or o.inset, sub = o.sub,
        key = o.key, regKey = o.regKey, needs = o.needs, nl = o.nl, reason = o.reason, enabled = o.enabled, reload = o.reload,
        target = o.target, when = o.when, inverted = o.inverted, nodot = o.nodot,
        isChanged = o.isChanged, reset = o.reset,
    }, "switch")
    if master then
        Theme.AddCutSliceFill(row, { C.violet[1], C.violet[2], C.violet[3], 0.07 }, 6)
        Theme.SkinButton(row, { borderColor = C.violet, chamfer = 6, glowAlpha = 0 })
    end
    local b = MakeToggle(row)
    b:SetPoint("RIGHT", row, "RIGHT", master and -10 or 0, 0)
    local state
    if not o.half then
        state = Label(row, "OFF", S.SMALL, C.line)
        state:SetWidth(S.STATE_W)
        state:SetJustifyH("RIGHT")
        state:SetPoint("RIGHT", b, "LEFT", -S.CTL_GAP, 0)
    end
    b:SetScript("OnClick", function(self)
        if not self:IsEnabled() then return end
        WriteValue(o, not (ReadValue(o) == true))
        CW.RefreshAll()
    end)
    local note, reloadButton
    if o.reload and state then
        reloadButton = BuildButton(row, {
            text = "Reload", warn = true,
            -- Addon code cannot reload on this client: the secure reload button is laid over this one
            -- while the pointer is on it, so a click lands there. This click only runs without it.
            onClick = function()
                local SR = FS.SecureReload
                if SR and SR.Explain then SR.Explain() end
            end,
        })
        reloadButton:HookScript("OnEnter", function(self)
            local SR = FS.SecureReload
            if SR and SR.Cover then SR.Cover(self) end
        end)
        reloadButton:HookScript("OnHide", function(self)
            local SR = FS.SecureReload
            if SR and SR.Covering and SR.Covering() == self then SR.Uncover() end
        end)
        reloadButton:SetPoint("RIGHT", state, "LEFT", -12, 0)
        note = Label(row, "", S.SMALL, C.pink)
        note:SetPoint("RIGHT", reloadButton, "LEFT", -S.CTL_GAP, 0)
    end
    Track(function()
        local on = ReadValue(o) == true
        PaintToggle(b, on)
        if note then
            local line = o.reload()
            note:SetText(line or "")
            note:SetShown(line ~= nil)
            reloadButton:SetShown(line ~= nil)
        end
        if state then
            state:SetText(on and "ON" or "OFF")
            Theme.ApplyMono(state, S.SMALL, on and C.cyan or C.line)
        end
        SetLook(b, Writable())
    end)
    I.AttachChanged(row, note or state or b)
    row.control = b
    return row
end

-- {label, options = {{value, text}, ...}, key, get, set, tip, sub, enabled}: one button per option, one selected.
-- `sub` indents the row under the toggle above it with the tree line; `enabled` is re-read on refresh. Over six options
-- the buttons share the row's width evenly instead of sizing by their text.
function UI.Segmented(content, o)
    local row = NewRow(content, o, "segmented")
    local holder = CreateFrame("Frame", nil, row)
    holder:SetPoint("RIGHT", row, "RIGHT", 0, 0)
    local buttons = {}
    local many = #o.options > 6
    local function WidthFor(option, index)
        local b = buttons[index].button
        return S.Snap(TextWidth(b.fsLabel) + 2 * S.SEG_PAD_X)
    end
    for _, option in ipairs(o.options) do
        local b = MakeButton(holder, {
            height = S.SEG_H, ring = C.line, textColor = C.muted, chamfer = 4, size = S.TEXT, glow = 0,
            text = option.text,
        })
        b:SetScript("OnClick", function(self)
            if not self:IsEnabled() then return end
            WriteValue(o, option.value)
            CW.RefreshAll()
        end)
        buttons[#buttons + 1] = { button = b, value = option.value }
    end
    local function Lay()
        local x = 0
        local width
        if many then
            local labelW = TextWidth(row.fsLabel) + (o.tip and (S.Q + S.Q_GAP) or 0) + (o.inset or (o.sub and S.SUB_INSET or 0))
            local avail = D.CONTENT_W - labelW - 16
            width = math.floor((avail - (#buttons - 1) * S.SEG_GAP) / #buttons)
        end
        for i, item in ipairs(buttons) do
            local w = width or WidthFor(nil, i)
            item.button:SetWidth(w)
            item.button:ClearAllPoints()
            item.button:SetPoint("LEFT", holder, "LEFT", x, 0)
            x = x + w + S.SEG_GAP
        end
        holder:SetSize(math.max(x - S.SEG_GAP, 1), S.SEG_H)
    end
    Lay()
    row.fsOnResize = many and Lay or nil
    Track(function()
        local current = ReadValue(o)
        holder.fsValue = current
        for _, item in ipairs(buttons) do
            local selected = item.value == current
            item.button.fsSelected = selected
            if selected then
                Restyle(item.button, C.cyan, C.cyan, Mix(C.ink, C.cyan, 0.2), 0.5)
            else
                Restyle(item.button, C.line, C.muted, C.ink, 0)
            end
            SetLook(item.button, Writable() and (o.enabled == nil or o.enabled() == true))
        end
    end)
    I.AttachChanged(row, holder)
    row.control = holder
    return row
end

-------------------------------------------------------------------------------
-- Slider
-------------------------------------------------------------------------------

-- The value for a position along the track (0 to 1), held inside the range and snapped to the step.
local function SliderValue(lo, hi, step, fraction)
    if not (hi > lo) then return lo end
    local steps = math.floor(math.min(1, math.max(0, fraction)) * (hi - lo) / step + 0.5)
    local value = math.floor((lo + steps * step) * 1e6 + 0.5) / 1e6
    return math.min(hi, value)
end
I.SliderValue = SliderValue

-- The mouse position along the track as a fraction of its width, or nil when the client cannot say.
local function CursorFraction(track)
    local left, scale = track:GetLeft(), track:GetEffectiveScale()
    if type(GetCursorPosition) ~= "function" or not left or not scale or scale <= 0 then return nil end
    return ((GetCursorPosition()) / scale - left) / S.SLIDER_W
end

local function PaintSlider(track, lo, hi, value)
    local x = hi > lo and (value - lo) / (hi - lo) * S.SLIDER_W or 0
    track.fsValue = value
    track.fsThumb:ClearAllPoints()
    track.fsThumb:SetPoint("CENTER", track, "LEFT", x, 0)
    track.fsFill:SetShown(x > 0)
    if x > 0 then track.fsFill:SetWidth(x) end
end

-- One slider edit box has the keyboard at a time. A click anywhere else in the window or on the screen lets go of it, so the
-- movement keys work again at once: a catcher behind the window takes clicks outside it, the window's own background takes
-- clicks inside it, and hiding the window ends it.
function I.SliderFocused(edit, lost)
    if edit then
        if I.sliderFocus and I.sliderFocus ~= edit then I.sliderFocus:ClearFocus() end
        I.sliderFocus = edit
        local win = ui.frame
        if win and not I.focusCatcher then
            local catcher = CreateFrame("Button", nil, UIParent)
            catcher:SetAllPoints(UIParent)
            catcher:EnableMouse(true)
            catcher:RegisterForClicks("AnyDown", "AnyUp")
            catcher:SetScript("OnClick", function() if I.sliderFocus then I.sliderFocus:ClearFocus() end end)
            I.focusCatcher = catcher
            win:HookScript("OnMouseDown", function() if I.sliderFocus then I.sliderFocus:ClearFocus() end end)
            win:HookScript("OnHide", function() if I.sliderFocus then I.sliderFocus:ClearFocus() end end)
        end
        local catcher = I.focusCatcher
        if catcher and win then
            catcher:SetFrameStrata(win:GetFrameStrata() or "DIALOG")
            catcher:SetFrameLevel(math.max(0, (win:GetFrameLevel() or 1) - 1))
            catcher:Show()
        end
    elseif I.sliderFocus == lost then
        I.sliderFocus = nil
        if I.focusCatcher then I.focusCatcher:Hide() end
    end
end

-- {label, key, get, set, min, max, step, fmt, tip}: a thin track with a cyan fill, a slab thumb and a mono readout.
-- `fmt` is a format string or a function of the value. Click or drag the track, or use the mouse wheel. A step of 0.5
-- and a format with no unit both work.
function UI.Slider(content, o)
    local lo, hi = o.min or 0, o.max or 100
    local step = (o.step and o.step > 0) and o.step or 1
    local row = NewRow(content, o, "slider")
    -- The value box: a mono cyan edit box with the unit beside the number, outside the editable text.
    local box = CreateFrame("Frame", nil, row)
    box:SetSize(S.VALUE_W, S.VALUE_H)
    box:SetPoint("RIGHT", row, "RIGHT", 0, 0)
    row.fsValueBox = box
    local fill = box:CreateTexture(nil, "BACKGROUND")
    fill:SetColorTexture(C.track[1], C.track[2], C.track[3], 1)
    fill:SetAllPoints(box)
    local edges = Outline(box, C.line, 1)
    local unit = Label(box, "", S.TEXT, C.muted)
    unit:SetPoint("RIGHT", box, "RIGHT", -6, 0)
    unit:SetJustifyH("RIGHT")
    row.fsUnit = unit
    local edit = CreateFrame("EditBox", nil, box)
    edit:SetPoint("LEFT", box, "LEFT", 6, 0)
    edit:SetPoint("RIGHT", unit, "LEFT", -2, 0)
    edit:SetHeight(S.VALUE_H - 4)
    edit:SetFont(Theme.FONT_MONO, S.TEXT, "")
    edit:SetTextColor(C.cyan[1], C.cyan[2], C.cyan[3], 1)
    edit:SetJustifyH("RIGHT")
    edit:SetAutoFocus(false)
    edit:SetMaxLetters(12)
    edit.fsSlider = true
    row.fsEdit = edit
    -- the full formatted text ("6 px", "80%"), kept for readers of the row; it is not drawn
    local readout = Label(box, "", S.TEXT, C.cyan)
    readout:Hide()
    row.fsReadout = readout

    local track = CreateFrame("Button", nil, row)
    row.fsTrack = track
    track:SetSize(S.SLIDER_W, S.SLIDER_H)
    track:SetPoint("RIGHT", box, "LEFT", -S.CTL_GAP, 0)
    track:EnableMouse(true)
    track:EnableMouseWheel(true)
    track:SetHitRectInsets(0, 0, -4, -4)
    local rail = track:CreateTexture(nil, "ARTWORK")
    local railColor = Mix(C.line, C.violet, 0.45)
    rail:SetColorTexture(railColor[1], railColor[2], railColor[3], 1)
    rail:SetHeight(SLIDER_BAR_H)
    rail:SetPoint("LEFT", track, "LEFT", 0, 0)
    rail:SetPoint("RIGHT", track, "RIGHT", 0, 0)
    track.fsFill = track:CreateTexture(nil, "ARTWORK", nil, 1)
    track.fsFill:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 1)
    track.fsFill:SetHeight(SLIDER_BAR_H)
    track.fsFill:SetPoint("LEFT", track, "LEFT", 0, 0)
    local thumb = CreateFrame("Frame", nil, track)
    thumb:SetSize(S.THUMB_W, S.THUMB_H)
    thumb.fsFill = Theme.AddCutSliceFill(thumb, C.ink, 3)
    thumb.fsSkin = Theme.SkinButton(thumb, { borderColor = C.cyan, chamfer = 3, glowAlpha = 0.55 })
    track.fsThumb = thumb

    local function Refresh()
        local value = ReadValue(o)
        if type(value) ~= "number" or value ~= value then value = lo end
        value = math.min(hi, math.max(lo, value))
        local text = o.fmt
        if type(text) == "function" then text = text(value) else text = (text or "%s"):format(value) end
        text = tostring(text)
        readout:SetText(text)
        -- the number goes in the edit box, whatever surrounds it in the format (a unit, a bracket) beside it
        local number = tostring(value)
        local at = text:find(number, 1, true)
        local rest = at and (text:sub(1, at - 1) .. text:sub(at + #number)) or ""
        unit:SetText((rest:gsub("^%s+", ""):gsub("%s+$", "")))
        if not edit:HasFocus() then edit:SetText(number) end
        PaintSlider(track, lo, hi, value)
        return value
    end

    local function StopDrag()
        track.fsDragging = false
        track:SetScript("OnUpdate", nil)
    end
    -- Writes only a changed value; a refused write ends a drag so it cannot repeat every frame. A keyed slider is
    -- repainted by the Config.OnAnyChange refresh; only a get / set one has to repaint itself.
    local function Commit(value)
        if value == ReadValue(o) then return end
        if not WriteValue(o, value) then StopDrag() end
        if not o.key then Refresh() end
    end
    local function Drag()
        if not track:IsEnabled() then StopDrag() return end
        local fraction = CursorFraction(track)
        if fraction then Commit(SliderValue(lo, hi, step, fraction)) end
    end
    -- ---- typed values -------------------------------------------------------------------------------------------
    local function Flash()
        box.fsFlash = true
        for _, t in ipairs(edges) do Tint(t, C.pink) end
        if C_Timer and C_Timer.After then
            C_Timer.After(0.4, function()
                box.fsFlash = false
                local color = edit:HasFocus() and C.cyan or C.line
                for _, t in ipairs(edges) do Tint(t, color) end
            end)
        end
    end
    local function Seat(value) edit:SetText(tostring(value)) end
    -- Parses what was typed. A number is clamped to the range and snapped to the step (pink when it had to move); text
    -- that is not a number puts the old value back (pink).
    local function Enter(text)
        local typed = tonumber((tostring(text or ""):gsub("[%s,]", "")))
        local current = ReadValue(o)
        if not typed then
            Flash()
            Refresh()
            return
        end
        local clamped = math.min(hi, math.max(lo, typed))
        if clamped ~= typed then Flash() end
        local snapped = SliderValue(lo, hi, step, hi > lo and (clamped - lo) / (hi - lo) or 0)
        if snapped ~= current then Commit(snapped) end
        Refresh()
    end
    local function Release() edit:ClearFocus() end
    edit:SetScript("OnEditFocusGained", function(self)
        for _, t in ipairs(edges) do Tint(t, C.cyan) end
        self:HighlightText()
        I.SliderFocused(self)
    end)
    edit:SetScript("OnEditFocusLost", function(self)
        for _, t in ipairs(edges) do Tint(t, box.fsFlash and C.pink or C.line) end
        self:HighlightText(0, 0)
        I.SliderFocused(nil, self)
        if self.fsEscaped then
            self.fsEscaped = nil
            Refresh()
        elseif self.fsEntered then
            self.fsEntered = nil
        else
            Enter(self:GetText())
        end
    end)
    edit:SetScript("OnEnterPressed", function(self)
        self.fsEntered = true
        local text = self:GetText()
        self:ClearFocus()
        Enter(text)
    end)
    edit:SetScript("OnEscapePressed", function(self)
        self.fsEscaped = true
        self:ClearFocus()
    end)
    edit:SetScript("OnTabPressed", function(self) self:ClearFocus() end)
    edit:SetScript("OnArrowPressed", function(self, key)
        if key ~= "UP" and key ~= "DOWN" then return end
        if not track:IsEnabled() then return end
        local jump = (I.ShiftHeld() and 10 or 1) * step
        local typed = tonumber((tostring(self:GetText() or ""):gsub("[%s,]", ""))) or ReadValue(o) or lo
        local value = math.min(hi, math.max(lo, typed + (key == "UP" and jump or -jump)))
        local snapped = SliderValue(lo, hi, step, hi > lo and (value - lo) / (hi - lo) or 0)
        Seat(snapped)
        Commit(snapped)
    end)
    edit:SetScript("OnHide", function(self) self:ClearFocus() end)
    row.fsReleaseFocus = Release

    track:SetScript("OnMouseDown", function(self, button)
        if button ~= "LeftButton" or not self:IsEnabled() then return end
        self.fsDragging = true
        Drag()
        self:SetScript("OnUpdate", Drag)
    end)
    track:SetScript("OnMouseUp", StopDrag)
    track:SetScript("OnHide", StopDrag)
    track:SetScript("OnMouseWheel", function(self, delta)
        -- On a page that scrolls the wheel scrolls it, so passing over a slider never changes a setting by accident;
        -- hold Shift to adjust the slider.
        local page = I.FindScrollPage(content)
        if page and (page.fsRange or 0) > 0 and not I.ShiftHeld() then
            I.ScrollBy(page, delta)
            return
        end
        if not self:IsEnabled() or not (hi > lo) then return end
        local value = Refresh() + (delta > 0 and step or -step)
        Commit(SliderValue(lo, hi, step, (value - lo) / (hi - lo)))
    end)
    Track(function()
        Refresh()
        local on = Writable() and not I.RowOff(track)
        if on then track:Enable() else track:Disable() end
        edit:EnableMouse(on)
        if not on then edit:ClearFocus() end
        row:SetAlpha(on and 1 or 0.4)                    -- the label and the readout dim with the track
    end)
    I.AttachChanged(row, track)
    row.control = track
    return row
end

-------------------------------------------------------------------------------
-- Popup menu and dropdown
-------------------------------------------------------------------------------

-- While `frame` is shown it consumes Escape to run `close`, so Escape does not close the whole window;
-- every other key still reaches the game.
local function CloseOnEscape(frame, close)
    frame:SetScript("OnShow", function(self) self:EnableKeyboard(true) end)
    frame:SetScript("OnHide", function(self) self:EnableKeyboard(false) end)
    frame:SetScript("OnKeyDown", function(self, key)
        if key == "ESCAPE" then
            self:SetPropagateKeyboardInput(false)
            close()
        else
            self:SetPropagateKeyboardInput(true)
        end
    end)
end

local function CloseMenu()
    if menuState.catcher then menuState.catcher:Hide() end
end
I.CloseMenu = CloseMenu

local function EnsureMenu()
    if menuState.frame then return menuState end
    local catcher = CreateFrame("Button", nil, UIParent)
    catcher:SetAllPoints(UIParent)
    catcher:SetFrameStrata("FULLSCREEN_DIALOG")
    catcher:EnableMouse(true)
    catcher:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    catcher:SetScript("OnClick", CloseMenu)
    -- The wheel stops here: it must not reach a page or a slider behind the open menu.
    catcher:EnableMouseWheel(true)
    catcher:SetScript("OnMouseWheel", function() end)
    CloseOnEscape(catcher, CloseMenu)
    catcher:Hide()
    local frame = CreateFrame("Frame", "ForeverSTUwaveConfigMenu", catcher)
    frame:SetFrameLevel(catcher:GetFrameLevel() + 2)
    frame:EnableMouse(true)
    Theme.SkinPanel(frame, { strip = false, scanline = false })
    menuState.catcher, menuState.frame, menuState.items = catcher, frame, {}
    return menuState
end

local function MenuItem(index)
    local state = menuState
    local item = state.items[index]
    if item then return item end
    item = CreateFrame("Button", nil, state.frame)
    item:SetHeight(MENU_ITEM_H)
    item:RegisterForClicks("LeftButtonUp")
    item.fsHover = item:CreateTexture(nil, "BACKGROUND")
    item.fsHover:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 0.12)
    item.fsHover:SetAllPoints(item)
    item.fsHover:Hide()
    item.fsLabel = Label(item, "", S.TEXT, C.text)
    item.fsLabel:SetPoint("LEFT", item, "LEFT", 10, 0)
    item:SetScript("OnEnter", function(self) self.fsHover:Show() end)
    item:SetScript("OnLeave", function(self) self.fsHover:Hide() end)
    state.items[index] = item
    return item
end

-- Lists `items` ({value, text}) under `anchor`; a pick runs onPick(value) and closes the menu.
local function OpenMenu(anchor, items, onPick, current)
    local state = EnsureMenu()
    if #items == 0 then return end
    local width = math.max(anchor:GetWidth(), 160)
    state.frame:ClearAllPoints()
    state.frame:SetPoint("TOPLEFT", anchor, "BOTTOMLEFT", 0, -2)
    state.frame:SetSize(width, #items * MENU_ITEM_H + 8)
    for i, entry in ipairs(items) do
        local item = MenuItem(i)
        item:ClearAllPoints()
        item:SetPoint("TOPLEFT", state.frame, "TOPLEFT", 4, -4 - (i - 1) * MENU_ITEM_H)
        item:SetWidth(width - 8)
        item.fsLabel:SetText(entry.text)
        Theme.ApplyMono(item.fsLabel, S.TEXT, entry.value == current and C.cyan or C.text)
        item:SetScript("OnClick", function()
            CloseMenu()
            onPick(entry.value)
            CW.RefreshAll()
        end)
        item:Show()
    end
    for i = #items + 1, #state.items do state.items[i]:Hide() end
    state.catcher:Show()
end
I.OpenMenu = OpenMenu

-- The dropdown's button: violet ring, cyan name, the drawn caret, the hover and press fills. `o` is the builder's own options
-- ({ get, items, set, text, free }, read when used); `clip` holds the name between its left inset and the caret, so a long
-- one is cut short instead of running under it. UI.Dropdown seats one in a row and UI.HeadPicker in the head band, so the
-- two look alike. b.fsPaint() reads the value again (the caller files it with Track).
local function NewDropdownButton(parent, o, width, clip)
    local b = MakeButton(parent, { width = width, height = S.BTN_H, ring = C.violet, textColor = C.cyan, chamfer = 6, text = "" })
    b.fsLabel:ClearAllPoints()
    b.fsLabel:SetPoint("LEFT", b, "LEFT", 10, 0)
    -- The caret is the prototype's small down triangle, drawn (see Pixel arrows). Its cell is a child of the button, so the
    -- button's own dimming while it is disabled takes the caret with it.
    local caretCell = CreateFrame("Frame", nil, b)
    caretCell:SetSize(CHEV_CELL, CHEV_CELL)
    caretCell:SetPoint("RIGHT", b, "RIGHT", -8, 0)
    b.fsCaret = NewArrowGlyph(caretCell, "down")
    b.fsCaret.SetColor(C.cyan)
    if clip then
        b.fsLabel:SetPoint("RIGHT", b, "RIGHT", -(8 + CHEV_CELL + 4), 0)
        b.fsLabel:SetJustifyH("LEFT")
        b.fsLabel:SetWordWrap(false)
    end
    HoverStyle(b, C.violet)
    b:SetScript("OnClick", function(self)
        if not self:IsEnabled() then return end
        OpenMenu(self, o.items(), o.set, o.get())
    end)
    function b.fsPaint()
        local value = o.get()
        b.fsValue = value
        b.fsLabel:SetText(o.text and o.text(value) or tostring(value))
        SetLook(b, o.free or Writable())
    end
    return b
end

-- {label, tip, get, items, set, text, free}: `free` keeps it usable when settings are read-only (it picks a view, not a setting). `items` is a function returning {value, text} entries; `text(value)`
-- names the current value on the button (it shows tostring(value) without it).
function UI.Dropdown(content, o)
    local row = NewRow(content, o, "dropdown")
    local b = NewDropdownButton(row, o, 200)
    b:SetPoint("RIGHT", row, "RIGHT", 0, 0)
    Track(b.fsPaint)
    I.AttachChanged(row, b)
    row.control = b
    return row
end

-- The head band's picker: a small muted label, then a dropdown button, in one frame BTN_H high that its caller seats (the
-- window puts it at the right of the head band). {label, width, get, items, set, text, free}. It is no row: nothing in the
-- registry, so search and the hover flash never see it, and built outside a tab, so every RefreshAll repaints it. A long
-- name is clipped inside the button.
function UI.HeadPicker(parent, o)
    local host = CreateFrame("Frame", nil, parent)
    local label = Label(host, o.label, S.SMALL, C.muted)
    label:SetPoint("LEFT", host, "LEFT", 0, 0)
    local b = NewDropdownButton(host, o, o.width, true)
    b:SetPoint("RIGHT", host, "RIGHT", 0, 0)
    host:SetSize(S.Snap(TextWidth(label)) + S.CTL_GAP + o.width, S.BTN_H)
    host.control = b
    Track(b.fsPaint)
    return host
end

-------------------------------------------------------------------------------
-- Text rows: a value line, an info row, a note, colour chips, a wrapped block
-------------------------------------------------------------------------------

-- A muted line whose text comes from `fn`; `|cff22e0ff...|r` in it renders cyan.
function UI.Value(content, fn)
    local line = CreateFrame("Frame", nil, content)
    line:SetHeight(S.ROW_H / 2 + 2)
    local fs = Label(line, "", S.TEXT, C.muted)
    fs:SetPoint("LEFT", line, "LEFT", 0, 0)
    Track(function() fs:SetText(fn()) end)
    return UI.Stack(content, line)
end

-- {label, value, tip}: a row with a label on the left and its value (text or a function returning text) on the right.
function UI.Info(content, o)
    local row = NewRow(content, o, "info")
    local fs = Label(row, "", S.TEXT, C.cyan)
    fs:SetPoint("RIGHT", row, "RIGHT", 0, 0)
    fs:SetJustifyH("RIGHT")
    row.fsValue = fs
    Track(function()
        local v = o.value
        if type(v) == "function" then v = v() end
        fs:SetText(tostring(v or ""))
    end)
    return row
end

-- A note line in the amber band: {text or fn, when}. Text is a string or a function returning one.
function UI.Note(content, o)
    if type(o) == "string" then o = { text = o } end
    local row = CreateFrame("Frame", nil, content)
    row:SetHeight(S.NOTE_H + 4)
    local box = CreateFrame("Frame", nil, row)
    box:SetPoint("TOPLEFT", row, "TOPLEFT", 0, -2)
    box:SetPoint("BOTTOMRIGHT", row, "BOTTOMRIGHT", 0, 2)
    local fill = box:CreateTexture(nil, "BACKGROUND")
    fill:SetColorTexture(C.amber[1], C.amber[2], C.amber[3], 0.05)
    fill:SetAllPoints(box)
    Outline(box, C.amber, 0.35)
    local badge = Label(box, "!", S.TEXT, C.amber)
    badge:SetPoint("LEFT", box, "LEFT", 8, 0)
    row.fsBadge = badge
    local fs = Label(box, "", S.TEXT, C.amber)
    fs:SetPoint("LEFT", box, "LEFT", 24, 0)
    fs:SetPoint("RIGHT", box, "RIGHT", -8, 0)
    fs:SetJustifyH("LEFT")
    row.fsText = fs
    row.fsWhen = o.when
    UI.Stack(content, row)
    I.Register(row, { label = type(o.text) == "string" and o.text or nil, when = o.when }, "note")
    Track(function()
        local text = o.text
        if type(text) == "function" then text = text() end
        fs:SetText(tostring(text or ""))
    end)
    return row
end

-- {label, tip, colors = { {color, name}, ... }, sub, needs, nl, when}: coloured chips with their names.
function UI.Swatch(content, o)
    local row = NewRow(content, o, "swatch")
    local x = 0
    row.fsChips = {}
    for i = #o.colors, 1, -1 do
        local color, name = o.colors[i][1], o.colors[i][2]
        local chip = CreateFrame("Frame", nil, row)
        local text = Label(chip, name, S.SMALL, C.muted)
        local w = S.Snap(TextWidth(text) + 12 + 6 + 2 * S.SEG_PAD_X)
        chip:SetSize(w, S.SEG_H)
        if row.fsChips[1] then chip:SetPoint("RIGHT", row.fsChips[1], "LEFT", -S.SEG_GAP, 0) else chip:SetPoint("RIGHT", row, "RIGHT", 0, 0) end
        local box = chip:CreateTexture(nil, "ARTWORK")
        box:SetColorTexture(color[1], color[2], color[3], 1)
        box:SetSize(12, 12)
        box:SetPoint("LEFT", chip, "LEFT", S.SEG_PAD_X, 0)
        text:SetPoint("LEFT", box, "RIGHT", 6, 0)
        Outline(chip, C.line, 1)
        table.insert(row.fsChips, 1, chip)
    end
    return row
end

-- A wrapped block of text from `fn`, for the Help page. When the text changes it grows or shrinks and the tab follows.
function UI.Text(content, fn)
    local block = CreateFrame("Frame", nil, content)
    block:SetHeight(S.ROW_H / 2 + 2)
    local fs = Label(block, "", S.TEXT, C.text)
    fs:SetPoint("TOPLEFT", block, "TOPLEFT", 0, 0)
    fs:SetWidth(D.CONTENT_W)
    fs:SetJustifyH("LEFT")
    fs:SetJustifyV("TOP")
    fs:SetSpacing(4)
    block.fsOnResize = function() fs:SetWidth(D.CONTENT_W) end
    UI.Stack(content, block)
    Track(function()
        fs:SetText(fn())
        local h = math.max(S.ROW_H / 2 + 2, math.ceil(fs:GetStringHeight() or 0) + 6)
        block:SetHeight(h)
        CW.RefreshScroll()
    end)
    return block
end

-- The prototype's .mv: a plain arrow is cyan on the ink fill, hover lights the ring and lifts the fill, pressed darkens the
-- fill, disabled takes the dim violet glyph on the darkest fill and ring (--dis, --disfill, --disedge) and answers nothing.
local ARROW_DIS_FILL = { 0.039, 0.024, 0.078, 1 }
local ARROW_DIS_EDGE = { 0.165, 0.094, 0.275, 1 }
local ARROW_PRESSED = { 0.024, 0.133, 0.165, 1 }

local function PaintArrow(b)
    local ring, fill, glyph = C.line, C.ink, C.cyan
    if not b:IsEnabled() then
        ring, fill, glyph = ARROW_DIS_EDGE, ARROW_DIS_FILL, ARROW_DIS
    elseif b.fsPressed then
        ring, fill = C.cyan, ARROW_PRESSED
    elseif b.fsHover then
        ring, fill = C.cyan, Mix(C.ink, C.cyan, 0.16)
    end
    Restyle(b, ring, glyph, fill, 0)
    b.fsGlyph.SetColor(glyph)
end

-- A tooltip for a small control: the text, at the right of it. A disabled control says nothing.
local function Hint(button, text)
    button:HookScript("OnEnter", function(self)
        if not self:IsEnabled() then return end
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetText(text, 1, 1, 1, 1, true)
        GameTooltip:Show()
    end)
    button:HookScript("OnLeave", function() GameTooltip:Hide() end)
end

-- {label, key | get + set, tip, getTitle, setTitle, onType, maxLetters, canUp, canDown, onUp, onDown, upHint, downHint, lock,
--  isChanged, reset, enabled, reason}: a data bar segment row. Left to right: the label, the title box (an edit box, ten
-- characters), the two arrows (up points left and moves a segment along the bar, down points right), the ON / OFF word and
-- the switch. Fixed fields only, so the page supplies the data and none of the behaviour:
--   * `onType(text)` hears every keystroke (not a SetText), so the title can change on screen while it is typed
--   * the box shows a cyan edge and selects its text on focus and is the one box with the keyboard (I.SliderFocused: a click
--     elsewhere, a click on the window, Tab and the window or the box hiding let go of it)
--   * Enter, Tab and a click elsewhere keep what was typed (`setTitle(text)` runs as the box lets go); Esc puts back the
--     title the box had when it was clicked into
--   * `lock()` is a function: while it answers true (or a reason) the switch alone is disabled (the last one on stays on); the row, its
--     arrows and its box stay live. `enabled` / `reason` dim the whole row, as on every other builder
--   * the changed dot and reset follow `isChanged` / `reset`; the hints read `upHint` ("Move left") and `downHint` ("Move right")
function UI.Order(content, o)
    local row = NewRow(content, o, "order")
    local function Arrow(direction, anchor, onClick, enabled, hint)
        local b = MakeButton(row, { width = S.RESET, height = S.RESET, ring = C.line, textColor = C.cyan, chamfer = 3, text = "", glow = 0 })
        b:SetPoint("RIGHT", anchor, "LEFT", -S.CTL_GAP, 0)
        b.fsGlyph = NewArrowGlyph(b, direction)
        b:HookScript("OnEnter", function(self) self.fsHover = true; PaintArrow(self) end)
        b:HookScript("OnLeave", function(self) self.fsHover, self.fsPressed = false, false; PaintArrow(self) end)
        b:HookScript("OnMouseDown", function(self) self.fsPressed = true; PaintArrow(self) end)
        b:HookScript("OnMouseUp", function(self) self.fsPressed = false; PaintArrow(self) end)
        b:SetScript("OnClick", function(self)
            if self:IsEnabled() and onClick then onClick() CW.RefreshAll() end
        end)
        Hint(b, hint)
        Track(function()
            local on = Writable() and not I.RowOff(b) and (enabled == nil or enabled() == true)
            if on then b:Enable() else b:Disable() end
            PaintArrow(b)
        end)
        return b
    end
    local toggle = MakeToggle(row)
    toggle:SetPoint("RIGHT", row, "RIGHT", 0, 0)
    toggle:SetScript("OnClick", function(self)
        if not self:IsEnabled() then return end
        WriteValue(o, not (ReadValue(o) == true))
        CW.RefreshAll()
    end)
    local state = Label(row, "OFF", S.SMALL, C.line)
    state:SetWidth(S.STATE_W)
    state:SetJustifyH("RIGHT")
    state:SetPoint("RIGHT", toggle, "LEFT", -S.CTL_GAP, 0)
    local down = Arrow("right", state, o.onDown, o.canDown, o.downHint or "Move right")
    local up = Arrow("left", down, o.onUp, o.canUp, o.upHint or "Move left")
    local holder = CreateFrame("Frame", nil, row)
    holder:SetSize(S.VALUE_W + 20, S.VALUE_H)
    holder:SetPoint("RIGHT", up, "LEFT", -S.CTL_GAP, 0)
    local well = holder:CreateTexture(nil, "BACKGROUND")
    well:SetColorTexture(C.track[1], C.track[2], C.track[3], 1)
    well:SetAllPoints(holder)
    local edges = Outline(holder, C.line, 1)
    local edit = CreateFrame("EditBox", nil, holder)
    edit:SetPoint("TOPLEFT", holder, "TOPLEFT", 6, -2)
    edit:SetPoint("BOTTOMRIGHT", holder, "BOTTOMRIGHT", -6, 2)
    edit:SetFont(Theme.FONT_MONO, S.TEXT, "")
    edit:SetTextColor(C.cyan[1], C.cyan[2], C.cyan[3], 1)
    edit:SetAutoFocus(false)
    edit:SetMaxLetters(o.maxLetters or 10)
    edit:SetScript("OnTextChanged", function(self, userInput)
        if userInput and o.onType then o.onType(self:GetText()) end
    end)
    edit:SetScript("OnEditFocusGained", function(self)
        self.fsBefore = o.getTitle and o.getTitle() or self:GetText()
        for _, t in ipairs(edges) do Tint(t, C.cyan) end
        self:HighlightText()
        I.SliderFocused(self)
    end)
    edit:SetScript("OnEditFocusLost", function(self)
        for _, t in ipairs(edges) do Tint(t, C.line) end
        self:HighlightText(0, 0)
        I.SliderFocused(nil, self)
        if o.setTitle then o.setTitle(self:GetText()) end
        CW.RefreshAll()
    end)
    edit:SetScript("OnEnterPressed", function(self) self:ClearFocus() end)
    edit:SetScript("OnTabPressed", function(self) self:ClearFocus() end)
    -- The title is live on screen while typing, so Esc puts the old one back in the box first; the box letting go then
    -- commits that, not what was typed.
    edit:SetScript("OnEscapePressed", function(self)
        if self.fsBefore ~= nil then self:SetText(self.fsBefore) end
        self:ClearFocus()
    end)
    edit:SetScript("OnHide", function(self) self:ClearFocus() end)
    row.fsTitleBox, row.fsUp, row.fsDown, row.fsState = edit, up, down, state
    Track(function()
        local on = ReadValue(o) == true
        PaintToggle(toggle, on)
        local locked = false
        if o.lock then
            local ok, value = pcall(o.lock)
            if ok then locked = value and true or false else Forward(value) end
        end
        SetLook(toggle, Writable() and not locked)
        state:SetText(on and "ON" or "OFF")
        Theme.ApplyMono(state, S.SMALL, on and C.cyan or C.line)
        if not edit:HasFocus() and o.getTitle then edit:SetText(o.getTitle() or "") end
        local usable = Writable() and not I.RowOff(edit)
        edit:SetEnabled(usable)
        if not usable then edit:ClearFocus() end
        holder:SetAlpha(usable and 1 or 0.4)
    end)
    I.AttachChanged(row, holder)
    row.control = toggle
    return row
end

-------------------------------------------------------------------------------
-- Confirm and prompt
-------------------------------------------------------------------------------

local function CloseDialog()
    local d = dialogState
    if not d.overlay then return end
    d.edit:ClearFocus()
    d.overlay:Hide()
end
I.CloseDialog = CloseDialog

local function AcceptDialog()
    local d = dialogState
    local result = d.editHolder:IsShown() and d.edit:GetText() or nil
    local ok, err = d.onAccept(result)
    if ok == false then
        d.error:SetText(Capitalize(err))
        return
    end
    CloseDialog()
    CW.RefreshAll()
end

local function EnsureDialog()
    local d = dialogState
    if d.overlay then return d end
    local overlay = CreateFrame("Frame", nil, ui.frame)
    overlay:SetAllPoints(ui.frame)
    overlay:SetFrameLevel(ui.frame:GetFrameLevel() + 30)
    overlay:EnableMouse(true)
    CloseOnEscape(overlay, CloseDialog)
    local dim = overlay:CreateTexture(nil, "BACKGROUND")
    dim:SetColorTexture(0, 0, 0, 0.55)
    dim:SetAllPoints(overlay)
    local panel = CreateFrame("Frame", "ForeverSTUwaveConfigDialog", overlay)
    panel:SetSize(S.DLG_W, S.DLG_H)
    panel:SetPoint("CENTER", overlay, "CENTER", 0, 0)
    panel:EnableMouse(true)
    Theme.SkinPanel(panel, { strip = false })
    d.message = Label(panel, "", S.TEXT, C.text)
    d.message:SetWidth(S.DLG_W - 2 * S.PAD - 8)
    d.message:SetJustifyH("CENTER")
    d.message:SetWordWrap(true)
    d.message:SetPoint("TOP", panel, "TOP", 0, -22)

    local holder = CreateFrame("Frame", nil, panel)
    holder:SetSize(280, S.VALUE_H)
    holder:SetPoint("TOP", d.message, "BOTTOM", 0, -12)
    local well = holder:CreateTexture(nil, "BACKGROUND")
    well:SetColorTexture(C.track[1], C.track[2], C.track[3], 1)
    well:SetAllPoints(holder)
    Outline(holder, C.line, 1)
    local edit = CreateFrame("EditBox", nil, holder)
    edit:SetPoint("TOPLEFT", holder, "TOPLEFT", 8, -2)
    edit:SetPoint("BOTTOMRIGHT", holder, "BOTTOMRIGHT", -8, 2)
    edit:SetFont(Theme.FONT_MONO, S.TEXT, "")
    edit:SetTextColor(C.cyan[1], C.cyan[2], C.cyan[3], 1)
    edit:SetAutoFocus(false)
    edit:SetMaxLetters(Config.NAME_MAX or 32)
    edit:SetScript("OnEnterPressed", AcceptDialog)
    edit:SetScript("OnEscapePressed", CloseDialog)
    d.error = Label(panel, "", S.SMALL, C.pink)
    d.error:SetPoint("TOP", holder, "BOTTOM", 0, -6)

    d.accept = MakeButton(panel, { width = 96, height = S.BTN_H, ring = C.cyan, textColor = C.cyan, chamfer = 6, text = "OK" })
    d.accept:SetPoint("BOTTOM", panel, "BOTTOM", -52, S.PAD)
    d.accept:SetScript("OnClick", AcceptDialog)
    d.cancel = MakeButton(panel, { width = 96, height = S.BTN_H, ring = C.violet, textColor = C.cyan, chamfer = 6, text = "Cancel" })
    d.cancel:SetPoint("BOTTOM", panel, "BOTTOM", 52, S.PAD)
    d.cancel:SetScript("OnClick", CloseDialog)
    d.overlay, d.panel, d.editHolder, d.edit = overlay, panel, holder, edit
    overlay:Hide()
    return d
end

local function ShowDialog(text, initial, acceptText, onAccept)
    local d = EnsureDialog()
    CloseMenu()
    d.message:SetText(text)
    d.error:SetText("")
    d.onAccept = onAccept
    d.accept.fsLabel:SetText(acceptText)
    d.editHolder:SetShown(initial ~= nil)
    d.panel:SetHeight(initial ~= nil and S.DLG_H + 24 or S.DLG_H)
    d.overlay:Show()
    if initial ~= nil then
        d.edit:SetText(initial)
        d.edit:SetFocus()
        d.edit:HighlightText()
    end
end

-- Asks first; onAccept runs only on Confirm. An in-window overlay, so no Blizzard popup taints.
function UI.Confirm(text, onAccept)
    if not ui.frame then CW.EnsureBuilt() end
    ShowDialog(text, nil, "Confirm", function()
        onAccept()
    end)
end

-- Asks for a line of text; onAccept(text) returns false and a reason to keep the prompt open.
function UI.Prompt(text, initial, onAccept)
    if not ui.frame then CW.EnsureBuilt() end
    ShowDialog(text, initial or "", "OK", onAccept)
end

-------------------------------------------------------------------------------
-- What each class module shows
-------------------------------------------------------------------------------

-- "Name: what it means" per piece, as the class module `?` tip. The words live in HelpModules.lua, the one source the
-- Help page and the listing pictures also read.
local HelpModules = FS.HelpModules
FS.ClassModuleHelp = setmetatable({}, { __index = function(_, token)
    return HelpModules and HelpModules.Tip(token) or nil
end })
