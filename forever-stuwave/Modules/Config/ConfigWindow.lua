-- Forever STUwave: Config window
-- /fsconfig opens one fixed size themed window: a category nav on the left, a content well on the right.
-- Pages register through FS.ConfigWindow.RegisterCategory and are built lazily; the FS.ConfigWindow.UI
-- builders stack rows in the shared style. The window is a plain non-secure frame, so it opens in combat.

local addonName, FS = ...

FS.ConfigWindow = FS.ConfigWindow or {}
local CW = FS.ConfigWindow
CW.UI = CW.UI or {}
local UI = CW.UI

local Theme = FS.Theme
local Config = FS.Config

-------------------------------------------------------------------------------
-- Constants
-------------------------------------------------------------------------------

local FRAME_NAME = "ForeverSTUwaveConfig"
local WIN_W, WIN_H = 780, 560
local NAV_W, NAV_ITEM_H, NAV_GAP = 150, 28, 3
local WELL_W = WIN_W - 2 * 17 - NAV_W - 10
local CONTENT_W = WELL_W - 14 - 22
local HALF_GAP = 28
local HALF_W = (CONTENT_W - HALF_GAP) / 2
local ROW_H, GROUP_GAP = 28, 12

local C = {
    text = { 0.886, 0.910, 0.941, 1 },
    muted = Theme.COLOR_MUTED,
    cyan = Theme.COLOR_POWER,
    violet = Theme.COLOR_BORDER,
    pink = Theme.COLOR_HEALTH,
    line = Theme.COLOR_BAR_BORDER,
    track = Theme.COLOR_BAR_TRACK,
    green = Theme.COLOR_CARET_HEALTH,
    ink = { 0.090, 0.047, 0.165, 1 },
    knob = { 0.357, 0.290, 0.541, 1 },
}

local categories = {}        -- key -> { key, label, order, build }
local sorted = {}            -- the same, by order then key
local ui = { pages = {}, nav = {} }
local controls = {}          -- refresh functions of every control built
local cursors = setmetatable({}, { __mode = "k" })
local menuState, dialogState = {}, {}

-------------------------------------------------------------------------------
-- Small helpers
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

local function SetLook(control, on)
    if on then control:Enable() else control:Disable() end
    control:SetAlpha(on and 1 or 0.4)
end

-- Every control registers one refresh function; RefreshAll runs them all.
local function Track(fn)
    controls[#controls + 1] = fn
    fn()
end

-- Does nothing while the window is hidden: Open and Select refresh before anything is seen.
function CW.RefreshAll()
    if not (ui.frame and ui.frame:IsShown()) then return end
    for _, fn in ipairs(controls) do
        local ok, err = pcall(fn)
        if not ok then Forward(err) end
    end
    if ui.readOnlyIcon then ui.readOnlyIcon:SetShown(Config.IsReadOnly()) end
end

-------------------------------------------------------------------------------
-- Stacking
-------------------------------------------------------------------------------

local function Cursor(content)
    local c = cursors[content]
    if not c then
        c = { y = 0 }
        cursors[content] = c
    end
    return c
end

-- Seats `frame` below the previous row of `content`. A frame at most 1 wide stretches across the page;
-- half = "left" or "right" places two rows side by side and drops the cursor after the right one.
function UI.Stack(content, frame, half)
    local c = Cursor(content)
    local h = frame:GetHeight()
    if half then
        frame:SetWidth(HALF_W)
        frame:SetPoint("TOPLEFT", content, "TOPLEFT", half == "left" and 0 or HALF_W + HALF_GAP, -c.y)
        if half == "left" then
            c.pending = h
        else
            c.y = c.y + math.max(h, c.pending or 0)
            c.pending = nil
        end
        return frame
    end
    if c.pending then
        c.y = c.y + c.pending
        c.pending = nil
    end
    frame:SetPoint("TOPLEFT", content, "TOPLEFT", 0, -c.y)
    if frame:GetWidth() <= 1 then frame:SetPoint("TOPRIGHT", content, "TOPRIGHT", 0, -c.y) end
    c.y = c.y + h
    return frame
end

local function NewRow(content, o)
    local row = CreateFrame("Frame", nil, content)
    row:SetHeight(o.height or ROW_H)
    local inset = o.inset or 0
    row.fsLabel = Label(row, o.label, o.size or 11, C.text)
    row.fsLabel:SetPoint("LEFT", row, "LEFT", inset, 0)
    if o.tip then
        row.fsHelp = UI.HelpIcon(row, o.tip)
        row.fsHelp:SetPoint("LEFT", row.fsLabel, "RIGHT", 6, 0)
    end
    UI.Stack(content, row, o.half)
    return row
end

-------------------------------------------------------------------------------
-- Help icon
-------------------------------------------------------------------------------

-- A small circled ? whose tooltip carries the explanation, in the addon's skinned GameTooltip.
function UI.HelpIcon(parent, tip)
    local icon = CreateFrame("Frame", nil, parent)
    icon:SetSize(12, 12)
    icon:EnableMouse(true)
    icon.fsTip = tip
    local ringColor = Mix(C.violet, C.line, 0.3)
    local ring = Disc(icon, 12, ringColor, 0)
    Disc(icon, 10, C.track, 1)
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
-- Header
-------------------------------------------------------------------------------

-- The "// TEXT" section header with a rule; `tip` adds the ? icon.
function UI.Header(content, text, tip)
    local c = Cursor(content)
    if c.pending then
        c.y = c.y + c.pending
        c.pending = nil
    end
    if c.y > 0 then c.y = c.y + GROUP_GAP end
    local header = CreateFrame("Frame", nil, content)
    header:SetHeight(16)
    local slash = Label(header, "//", 10, C.line)
    slash:SetPoint("LEFT", header, "LEFT", 0, 0)
    local title = Label(header, text:upper(), 10, C.violet)
    title:SetPoint("LEFT", slash, "RIGHT", 6, 0)
    local last = title
    if tip then
        local icon = UI.HelpIcon(header, tip)
        icon:SetPoint("LEFT", title, "RIGHT", 6, 0)
        last = icon
    end
    local rule = header:CreateTexture(nil, "ARTWORK")
    rule:SetColorTexture(C.violet[1], C.violet[2], C.violet[3], 0.35)
    rule:SetHeight(1)
    rule:SetPoint("LEFT", last, "RIGHT", 8, 0)
    rule:SetPoint("RIGHT", header, "RIGHT", 0, 0)
    return UI.Stack(content, header)
end

-------------------------------------------------------------------------------
-- Buttons
-------------------------------------------------------------------------------

local function MakeButton(parent, o)
    local b = CreateFrame("Button", nil, parent)
    b:SetSize(o.width, o.height)
    b:RegisterForClicks("LeftButtonUp")
    b.fsRing = o.ring
    b.fsFill = Theme.AddCutSliceFill(b, o.fill or C.ink, o.chamfer)
    b.fsSkin = Theme.SkinButton(b, { borderColor = o.ring, chamfer = o.chamfer, glowAlpha = o.glow or 0.35 })
    b.fsLabel = Label(b, o.text or "", o.size or 11, o.textColor)
    b.fsLabel:SetPoint("CENTER", b, "CENTER", 0, 0)
    return b
end

-- Retints a button's ring, glow, fill and label together (selected, hovered or plain).
local function Restyle(b, ring, textColor, fill, glow)
    Tint(b.fsSkin and b.fsSkin.border and b.fsSkin.border.ring, ring, 1)
    Tint(b.fsSkin and b.fsSkin.glow, ring, glow)
    Tint(b.fsFill, fill, 1)
    Theme.ApplyMono(b.fsLabel, select(2, b.fsLabel:GetFont()) or 11, textColor)
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
end

local function BuildButton(parent, o)
    local ring = o.warn and C.pink or (o.big and C.cyan or C.violet)
    local textColor = o.warn and C.pink or C.cyan
    local width = o.big and 1 or math.max(70, math.floor(#o.text * 6.6 + 28))
    local b = MakeButton(parent, {
        width = width, height = o.big and 36 or 24, ring = ring, textColor = textColor,
        chamfer = 6, size = o.big and 14 or 11, text = o.text,
    })
    b.fsWarn = o.warn == true
    HoverStyle(b, ring)
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
        local row = NewRow(content, { label = o.label, tip = o.tip })
        local b = BuildButton(row, o)
        b:SetPoint("RIGHT", row, "RIGHT", 0, 0)
        row.control = b
        return row
    end
    local b = BuildButton(content, o)
    return UI.Stack(content, b)
end

-- A row of buttons side by side: a list of the same tables UI.Button takes.
function UI.ButtonRow(content, list)
    local row = CreateFrame("Frame", nil, content)
    row:SetHeight(32)
    local prev
    for _, o in ipairs(list) do
        local b = BuildButton(row, o)
        if prev then b:SetPoint("LEFT", prev, "RIGHT", 8, 0) else b:SetPoint("LEFT", row, "LEFT", 0, 0) end
        prev = b
    end
    return UI.Stack(content, row)
end

-------------------------------------------------------------------------------
-- Toggle and segmented control
-------------------------------------------------------------------------------

local function ReadValue(o)
    if o.key then return Config.Get(o.key) end
    return o.get()
end

local function WriteValue(o, value)
    local ok, result
    if o.key then ok, result = pcall(Config.Set, o.key, value) else ok, result = pcall(o.set, value) end
    if not ok then
        Forward(result)
        Say("that setting could not be changed.")
    elseif result == false then
        Say("settings are read-only this session.")
    end
end

local function MakeToggle(parent)
    local b = CreateFrame("Button", nil, parent)
    b:SetSize(34, 16)
    b:RegisterForClicks("LeftButtonUp")
    b.fsFill = Theme.AddCutSliceFill(b, C.track, 4)
    b.fsSkin = Theme.SkinButton(b, { borderColor = C.line, chamfer = 4, glowAlpha = 0 })
    local knob = CreateFrame("Frame", nil, b)
    knob:SetSize(12, 8)
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
    b.fsKnob:SetPoint(on and "RIGHT" or "LEFT", b, on and "RIGHT" or "LEFT", on and -4 or 4, 0)
end

-- {label, key, get, set, tip, half, master}: bound to FS.Config.Get/Set(key), or to get()/set(v).
function UI.Toggle(content, o)
    local master = o.master == true
    local row = NewRow(content, {
        label = o.label, tip = o.tip, half = o.half, height = master and 34 or ROW_H,
        size = master and 12 or 11, inset = master and 10 or 0,
    })
    if master then
        Theme.AddCutSliceFill(row, { C.violet[1], C.violet[2], C.violet[3], 0.07 }, 6)
        Theme.SkinButton(row, { borderColor = C.violet, chamfer = 6, glowAlpha = 0 })
    end
    local b = MakeToggle(row)
    b:SetPoint("RIGHT", row, "RIGHT", master and -10 or 0, 0)
    local state
    if not o.half then
        state = Label(row, "OFF", 9, C.line)
        state:SetPoint("RIGHT", b, "LEFT", -8, 0)
    end
    b:SetScript("OnClick", function(self)
        if not self:IsEnabled() then return end
        WriteValue(o, not (ReadValue(o) == true))
        CW.RefreshAll()
    end)
    Track(function()
        local on = ReadValue(o) == true
        PaintToggle(b, on)
        if state then
            state:SetText(on and "ON" or "OFF")
            Theme.ApplyMono(state, 9, on and C.cyan or C.line)
        end
        SetLook(b, Writable())
    end)
    row.control = b
    return row
end

-- {label, options = {{value, text}, ...}, key, get, set, tip}: one button per option, one selected.
function UI.Segmented(content, o)
    local row = NewRow(content, { label = o.label, tip = o.tip })
    local holder = CreateFrame("Frame", nil, row)
    holder:SetPoint("RIGHT", row, "RIGHT", 0, 0)
    local buttons, total = {}, 0
    for _, option in ipairs(o.options) do
        local width = math.floor(#option.text * 6.3 + 22)
        local b = MakeButton(holder, {
            width = width, height = 22, ring = C.line, textColor = C.muted, chamfer = 4, size = 10.5, glow = 0,
            text = option.text,
        })
        b:SetPoint("LEFT", holder, "LEFT", total, 0)
        total = total + width + 2
        b:SetScript("OnClick", function(self)
            if not self:IsEnabled() then return end
            WriteValue(o, option.value)
            CW.RefreshAll()
        end)
        buttons[#buttons + 1] = { button = b, value = option.value }
    end
    holder:SetSize(math.max(total - 2, 1), 22)
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
            SetLook(item.button, Writable())
        end
    end)
    row.control = holder
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

local MENU_ITEM_H = 24

local function CloseMenu()
    if menuState.catcher then menuState.catcher:Hide() end
end

local function EnsureMenu()
    if menuState.frame then return menuState end
    local catcher = CreateFrame("Button", nil, UIParent)
    catcher:SetAllPoints(UIParent)
    catcher:SetFrameStrata("FULLSCREEN_DIALOG")
    catcher:EnableMouse(true)
    catcher:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    catcher:SetScript("OnClick", CloseMenu)
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
    item.fsLabel = Label(item, "", 11, C.text)
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
        Theme.ApplyMono(item.fsLabel, 11, entry.value == current and C.cyan or C.text)
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

-- {label, tip, get, items, set}: `items` is a function returning {value, text} entries.
function UI.Dropdown(content, o)
    local row = NewRow(content, { label = o.label, tip = o.tip })
    local b = MakeButton(row, { width = 200, height = 24, ring = C.violet, textColor = C.cyan, chamfer = 6, text = "" })
    b:SetPoint("RIGHT", row, "RIGHT", 0, 0)
    b.fsLabel:ClearAllPoints()
    b.fsLabel:SetPoint("LEFT", b, "LEFT", 10, 0)
    local chevron = Label(b, "v", 10, C.cyan)
    chevron:SetPoint("RIGHT", b, "RIGHT", -8, 0)
    HoverStyle(b, C.violet)
    b:SetScript("OnClick", function(self)
        if not self:IsEnabled() then return end
        OpenMenu(self, o.items(), o.set, o.get())
    end)
    Track(function()
        local value = o.get()
        b.fsValue = value
        b.fsLabel:SetText(tostring(value))
        SetLook(b, Writable())
    end)
    row.control = b
    return row
end

-- A muted line whose text comes from `fn`; `|cff22e0ff...|r` in it renders cyan.
function UI.Value(content, fn)
    local line = CreateFrame("Frame", nil, content)
    line:SetHeight(18)
    local fs = Label(line, "", 10, C.muted)
    fs:SetPoint("LEFT", line, "LEFT", 0, 0)
    Track(function() fs:SetText(fn()) end)
    return UI.Stack(content, line)
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
    panel:SetSize(380, 150)
    panel:SetPoint("CENTER", overlay, "CENTER", 0, 0)
    panel:EnableMouse(true)
    Theme.SkinPanel(panel, { strip = false })
    d.message = Label(panel, "", 11, C.text)
    d.message:SetWidth(340)
    d.message:SetJustifyH("CENTER")
    d.message:SetWordWrap(true)
    d.message:SetPoint("TOP", panel, "TOP", 0, -22)

    local holder = CreateFrame("Frame", nil, panel)
    holder:SetSize(280, 24)
    holder:SetPoint("TOP", d.message, "BOTTOM", 0, -12)
    local well = holder:CreateTexture(nil, "BACKGROUND")
    well:SetColorTexture(C.track[1], C.track[2], C.track[3], 1)
    well:SetAllPoints(holder)
    Outline(holder, C.line, 1)
    local edit = CreateFrame("EditBox", nil, holder)
    edit:SetPoint("TOPLEFT", holder, "TOPLEFT", 8, -2)
    edit:SetPoint("BOTTOMRIGHT", holder, "BOTTOMRIGHT", -8, 2)
    edit:SetFont(Theme.FONT_MONO, 11, "")
    edit:SetTextColor(C.cyan[1], C.cyan[2], C.cyan[3], 1)
    edit:SetAutoFocus(false)
    edit:SetMaxLetters(Config.NAME_MAX or 32)
    edit:SetScript("OnEnterPressed", AcceptDialog)
    edit:SetScript("OnEscapePressed", CloseDialog)
    d.error = Label(panel, "", 10, C.pink)
    d.error:SetPoint("TOP", holder, "BOTTOM", 0, -6)

    d.accept = MakeButton(panel, { width = 96, height = 24, ring = C.cyan, textColor = C.cyan, chamfer = 6, text = "OK" })
    d.accept:SetPoint("BOTTOM", panel, "BOTTOM", -52, 16)
    d.accept:SetScript("OnClick", AcceptDialog)
    d.cancel = MakeButton(panel, { width = 96, height = 24, ring = C.violet, textColor = C.cyan, chamfer = 6, text = "Cancel" })
    d.cancel:SetPoint("BOTTOM", panel, "BOTTOM", 52, 16)
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
    d.panel:SetHeight(initial ~= nil and 176 or 128)
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
-- The window
-------------------------------------------------------------------------------

local function SortCategories()
    sorted = {}
    for _, cat in pairs(categories) do sorted[#sorted + 1] = cat end
    table.sort(sorted, function(a, b)
        if a.order ~= b.order then return a.order < b.order end
        return a.key < b.key
    end)
end

local function Version()
    local get = _G.C_AddOns and _G.C_AddOns.GetAddOnMetadata or _G.GetAddOnMetadata
    if type(get) ~= "function" then return nil end
    local ok, value = pcall(get, addonName, "Version")
    if ok and type(value) == "string" and value ~= "" then return value end
end

local function SetSelected(key)
    for _, b in pairs(ui.nav) do
        local selected = b.fsCategory == key
        b.fsSelected = selected
        b.fsHighlight:SetShown(selected)
        b.fsBar:SetShown(selected)
        Theme.ApplyMono(b.fsLabel, 11, selected and C.cyan or C.muted)
        Theme.ApplyMono(b.fsNumber, 9, selected and C.pink or C.line)
    end
end

local function MakeNavButton(cat)
    local b = CreateFrame("Button", nil, ui.frame)
    b:SetSize(NAV_W, NAV_ITEM_H)
    b:RegisterForClicks("LeftButtonUp")
    b.fsCategory = cat.key
    b.fsHighlight = Theme.AddCutSliceFill(b, { C.cyan[1], C.cyan[2], C.cyan[3], 0.10 }, 4)
    b.fsBar = b:CreateTexture(nil, "ARTWORK")
    b.fsBar:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 1)
    b.fsBar:SetWidth(2)
    b.fsBar:SetPoint("TOPLEFT", b, "TOPLEFT", 0, -5)
    b.fsBar:SetPoint("BOTTOMLEFT", b, "BOTTOMLEFT", 0, 5)
    b.fsNumber = Label(b, "", 9, C.line)
    b.fsNumber:SetPoint("LEFT", b, "LEFT", 10, 0)
    b.fsLabel = Label(b, "", 11, C.muted)
    b.fsLabel:SetPoint("LEFT", b, "LEFT", 32, 0)
    b:SetScript("OnClick", function() CW.Open(cat.key) end)
    return b
end

local function LayoutNav()
    for i, cat in ipairs(sorted) do
        local b = ui.nav[cat.key]
        if not b then
            b = MakeNavButton(cat)
            ui.nav[cat.key] = b
        end
        b.fsNumber:SetText(("%02d"):format(i))
        b.fsLabel:SetText(cat.label)
        b:ClearAllPoints()
        b:SetPoint("TOPLEFT", ui.frame, "TOPLEFT", 17, -96 - (i - 1) * (NAV_ITEM_H + NAV_GAP))
        b:Show()
    end
    SetSelected(ui.current)
end

local function Select(key)
    local cat = categories[key]
    if not cat then return end
    ui.current = key
    for k, page in pairs(ui.pages) do page:SetShown(k == key) end
    local page = ui.pages[key]
    if not page then
        page = CreateFrame("Frame", nil, ui.content)
        page:SetAllPoints(ui.content)
        ui.pages[key] = page
        local ok, err = pcall(cat.build, page)
        if not ok then Forward(err) end
    end
    page:Show()
    ui.category:SetText("CATEGORY |cff22e0ff/ " .. cat.label:upper() .. "|r")
    SetSelected(key)
    CW.RefreshAll()
end

local function BuildChrome(frame)
    Theme.SkinPanel(frame, { strip = false, title = "config" })

    local title = frame:CreateFontString(nil, "OVERLAY")
    Theme.ApplyFontGeneric(title, Theme.FONT_ORBITRON, 17, C.text, "")
    title:SetPoint("TOPLEFT", frame, "TOPLEFT", 17, -33)
    title:SetText("FOREVER |cffff2e97STU|rWAVE")

    local sub = Label(frame, "", 10, C.muted)
    sub:SetPoint("TOPLEFT", frame, "TOPLEFT", 17, -55)
    local version = Version()
    sub:SetText((version and ("v" .. version .. "  \194\183  ") or "") .. "|cff22e0ff/fsconfig|r")

    local icon = UI.HelpIcon(frame,
        "Saved settings could not be loaded, so every setting and profile is read-only this session.")
    icon.fsReadOnlyIcon = true
    icon:SetPoint("LEFT", sub, "RIGHT", 8, 0)
    icon:Hide()
    ui.readOnlyIcon = icon

    ui.category = Label(frame, "", 10, C.muted)
    ui.category:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -17, -36)

    local close = MakeButton(frame, {
        width = 26, height = 14, ring = C.pink, textColor = C.pink, chamfer = 4, size = 11, text = "X", glow = 0.55,
    })
    close:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -7, -5)
    close:SetScript("OnClick", function() CW.Close() end)

    local navHeader = Label(frame, "// settings", 9, C.muted)
    navHeader:SetPoint("TOPLEFT", frame, "TOPLEFT", 19, -78)
    local navCommands = Label(frame, "/fsgun  /fsedit  /fsbug", 9, C.line)
    navCommands:SetPoint("BOTTOMLEFT", frame, "BOTTOMLEFT", 19, 42)

    local well = CreateFrame("Frame", nil, frame)
    well:SetPoint("TOPLEFT", frame, "TOPLEFT", 17 + NAV_W + 10, -74)
    well:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -17, 36)
    local fill = well:CreateTexture(nil, "BACKGROUND")
    fill:SetColorTexture(C.track[1], C.track[2], C.track[3], 0.95)
    fill:SetAllPoints(well)
    Outline(well, C.line, 1)
    ui.content = CreateFrame("Frame", nil, well)
    ui.content:SetPoint("TOPLEFT", well, "TOPLEFT", 14, -10)
    ui.content:SetPoint("BOTTOMRIGHT", well, "BOTTOMRIGHT", -22, 8)

    local rule = frame:CreateTexture(nil, "ARTWORK")
    rule:SetColorTexture(C.violet[1], C.violet[2], C.violet[3], 0.30)
    rule:SetHeight(1)
    rule:SetPoint("BOTTOMLEFT", frame, "BOTTOMLEFT", 3, 34)
    rule:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -3, 34)
    local dot = frame:CreateTexture(nil, "ARTWORK")
    dot:SetColorTexture(C.green[1], C.green[2], C.green[3], 1)
    dot:SetSize(6, 6)
    dot:SetPoint("LEFT", frame, "BOTTOMLEFT", 17, 18)
    local applies = Label(frame, "Changes apply instantly", 10, C.muted)
    applies:SetPoint("LEFT", dot, "RIGHT", 8, 0)
    local chip = CreateFrame("Frame", nil, frame)
    chip:SetSize(62, 18)
    chip:SetPoint("RIGHT", frame, "BOTTOMRIGHT", -17, 18)
    local chipFill = chip:CreateTexture(nil, "BACKGROUND")
    chipFill:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 0.08)
    chipFill:SetAllPoints(chip)
    Outline(chip, C.cyan, 0.4)
    local key = Label(chip, "/fsconfig", 10, C.cyan)
    key:SetPoint("CENTER", chip, "CENTER", 0, 0)
    local openWith = Label(frame, "open with", 10, C.muted)
    openWith:SetPoint("RIGHT", chip, "LEFT", -8, 0)
end

local function BuildWindow()
    local frame = CreateFrame("Frame", FRAME_NAME, UIParent)
    frame:Hide()
    frame:SetSize(WIN_W, WIN_H)
    frame:SetPoint("CENTER", UIParent, "CENTER", 0, 40)
    frame:SetFrameStrata("DIALOG")
    frame:SetToplevel(true)
    frame:SetClampedToScreen(true)
    frame:SetMovable(true)
    frame:EnableMouse(true)
    frame:RegisterForDrag("LeftButton")
    frame:SetScript("OnDragStart", frame.StartMoving)
    frame:SetScript("OnDragStop", frame.StopMovingOrSizing)
    frame:SetScript("OnHide", function(self)
        CloseMenu()
        CloseDialog()
        local owner = GameTooltip:GetOwner()
        while owner and owner ~= self do owner = owner:GetParent() end
        if owner then GameTooltip:Hide() end
    end)
    local ok, err = pcall(BuildChrome, frame)
    if not ok then
        frame:Hide()
        error(err, 0)
    end
    ui.frame = frame
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
    LayoutNav()
    return ui.frame
end

-------------------------------------------------------------------------------
-- Public surface
-------------------------------------------------------------------------------

-- {key, label, order, build}: build(content) runs once, the first time the page is shown.
-- Registering a key again updates its label and order but the first build wins; a built page is never rebuilt.
function CW.RegisterCategory(spec)
    if type(spec) ~= "table" or type(spec.key) ~= "string" or spec.key == "" then return false end
    if type(spec.build) ~= "function" then return false end
    categories[spec.key] = {
        key = spec.key, label = tostring(spec.label or spec.key), order = tonumber(spec.order) or 100,
        build = spec.build,
    }
    SortCategories()
    if ui.frame then LayoutNav() end
    return true
end

function CW.Categories()
    local list = {}
    for i, cat in ipairs(sorted) do list[i] = { key = cat.key, label = cat.label, order = cat.order } end
    return list
end

function CW.Open(key)
    local ok, err = pcall(CW.EnsureBuilt)
    if not ok then
        Forward(err)
        Say("the config window could not open.")
        return
    end
    if key ~= nil and categories[key] then ui.current = key end
    if not (ui.current and categories[ui.current]) then ui.current = sorted[1] and sorted[1].key end
    ui.frame:Show()
    if ui.current then Select(ui.current) end
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

-- Repaints the controls whenever any setting changes, which includes a profile switch.
Config.OnAnyChange(function()
    if ui.frame then CW.RefreshAll() end
end)

local function Squash(text)
    return (tostring(text or ""):lower():gsub("%s+", ""))
end

SLASH_FSCONFIG1 = "/fsconfig"
SlashCmdList["FSCONFIG"] = function(msg)
    local want = Squash(msg)
    if want ~= "" then
        for _, cat in ipairs(sorted) do
            if Squash(cat.key) == want or Squash(cat.label) == want then
                CW.Open(cat.key)
                return
            end
        end
    end
    CW.Toggle()
end

-------------------------------------------------------------------------------
-- Pages
-------------------------------------------------------------------------------

CW.RegisterCategory({ key = "unitframes", label = "Unit Frames", order = 1, build = function(page)
    UI.Header(page, "Player and target", "Hidden frames stay click-through and invisible.")
    UI.Toggle(page, { label = "Hide player frame", key = "unitFrames.hidePlayer" })
    UI.Toggle(page, { label = "Hide target frame", key = "unitFrames.hideTarget" })
end })

local PIECE_ORDER = { "you", "tgt", "next", "dot", "shard", "prc", "buff", "party" }
local PIECE_LABELS = {
    you = "Your cast bar", tgt = "Target cast bar", next = "Next cast tile", dot = "DoT time axis",
    shard = "Soul shards", prc = "Proc posts", buff = "Buff reminders", party = "Party frames",
}

if FS.Gunsight and FS.Gunsight.PIECES then
    CW.RegisterCategory({ key = "gunsight", label = "Gunsight HUD", order = 2, build = function(page)
        local Gunsight = FS.Gunsight
        UI.Toggle(page, {
            label = "Gunsight HUD", key = Gunsight.CONFIG_ENABLED, master = true,
            tip = "Master switch for the whole HUD. Takes effect after /reload.",
        })
        UI.Header(page, "Pieces")
        local known, n = {}, 0
        for _, key in ipairs(Gunsight.PIECES) do known[key] = true end
        for _, key in ipairs(PIECE_ORDER) do
            if known[key] then
                n = n + 1
                UI.Toggle(page, {
                    label = PIECE_LABELS[key], key = Gunsight.PieceConfigKey(key),
                    half = n % 2 == 1 and "left" or "right",
                })
            end
        end
    end })
end

local function CharacterLabel()
    local db = _G.ForeverSTUwaveDB
    local guid
    if type(UnitGUID) == "function" then
        local ok, value = pcall(UnitGUID, "player")
        if ok and not (FS.IsSecret and FS.IsSecret(value)) then guid = value end
    end
    local label = type(db) == "table" and type(db.profileLabels) == "table" and guid and db.profileLabels[guid]
    if type(label) == "string" and label ~= "" then return label end
    local name = type(UnitName) == "function" and UnitName("player") or nil
    if type(name) == "string" and not (FS.IsSecret and FS.IsSecret(name)) then return name end
    return "unknown"
end

local function ProfileItems(...)
    local skip, items = {}, {}
    for _, name in ipairs({ ... }) do skip[name] = true end
    for _, name in ipairs(Config.ListProfiles()) do
        if not skip[name] then items[#items + 1] = { value = name, text = name } end
    end
    return items
end

local function Check(ok, err)
    if ok == false then Say(err) end
end

local function ProfilesPage(page)
    local default = Config.DEFAULT_PROFILE
    UI.Header(page, "Active profile",
        "A profile holds layout positions and every setting in this window. Bug reports and logs stay account-wide.")
    UI.Dropdown(page, {
        label = "Profile in use",
        get = Config.ActiveProfile,
        items = function() return ProfileItems() end,
        set = function(name) Check(Config.SetActiveProfile(name)) end,
    })
    UI.Value(page, function() return "This character: |cff22e0ff" .. CharacterLabel() .. "|r" end)
    UI.Header(page, "Manage")
    UI.ButtonRow(page, {
        { text = "New profile", onClick = function()
            UI.Prompt("Name the new profile.", "", function(name)
                local ok, made = Config.NewProfile(name)
                if not ok then return false, made end
                Check(Config.SetActiveProfile(made))
            end)
        end },
        { text = "Copy from...", enabled = function() return #ProfileItems(Config.ActiveProfile()) > 0 end,
          onClick = function(b)
              OpenMenu(b, ProfileItems(Config.ActiveProfile()), function(from)
                  local active = Config.ActiveProfile()
                  UI.Confirm(("Replace the settings and layout of %s with a copy of %s?"):format(active, from),
                      function() Check(Config.CopyProfile(from)) end)
              end)
          end },
        { text = "Rename", enabled = function() return Config.ActiveProfile() ~= default end, onClick = function()
            local active = Config.ActiveProfile()
            UI.Prompt(("Rename the profile %s."):format(active), active, function(name)
                local ok, err = Config.RenameProfile(active, name)
                if not ok then return false, err end
            end)
        end },
    })
    UI.Button(page, {
        label = "Delete a profile", tip = "Default and the active profile cannot be deleted. Cannot be undone.",
        text = "Delete", warn = true,
        enabled = function() return #ProfileItems(default, Config.ActiveProfile()) > 0 end,
        onClick = function(b)
            OpenMenu(b, ProfileItems(default, Config.ActiveProfile()), function(name)
                UI.Confirm(("Delete the profile %s?"):format(name), function() Check(Config.DeleteProfile(name)) end)
            end)
        end,
    })
    UI.Button(page, {
        label = "Put this profile back to the defaults", tip = "Cannot be undone.",
        text = "Reset profile", warn = true,
        confirm = function()
            return ("Put %s back to the defaults? Its layout positions are cleared too."):format(Config.ActiveProfile())
        end,
        onClick = function() Check(Config.ResetProfile()) end,
    })
end

CW.RegisterCategory({ key = "profiles", label = "Profiles", order = 9, build = ProfilesPage })
