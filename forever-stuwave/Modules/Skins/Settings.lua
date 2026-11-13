-- Forever STUwave: Options panel (SettingsPanel)
-- The category list, the Game / AddOns tabs, the pooled rows of the settings list and the Keybindings page, restyled in place from
-- the approved SETTINGS mockup (mockups/settings-system-2026-11-12.html, sections 1 and 2). The outer panel, its Apply, Close and
-- Defaults plates, the search box and the scroll bars already wear the shared panel skin (Panels.lua) and the controls sweep; this
-- file adds the parts that were still stock. The checkboxes, sliders and dropdowns of the rows are the shared controls (CheckSkins,
-- SliderSkins, DropdownSkins): a pooled row is not reached by the panel sweep (it never walks into a ScrollBox), so each row is
-- swept here as the list shows it.
--
-- Skin only, as in Commerce.lua: no SetScript, no SetAttribute, no reparent, no resize or re-anchor of a Blizzard frame; alpha
-- holds (FS.HeldArt), post-hooks and our own textures. Every click, tooltip, binding and apply flow stays stock. Names are the
-- real 12.1 tree (Blizzard_Settings_Shared: Blizzard_SettingsPanel.xml, Blizzard_CategoryList.xml, Blizzard_SettingsList.xml,
-- Blizzard_SettingControls.xml, Blizzard_Keybindings.xml; Blizzard_SettingsDefinitions_Frame Keybindings.xml, Blizzard_SharedXML
-- MinimalTab.xml); each one is feature-detected and a missing frame is skipped silently. The Forever client uses this page for key
-- bindings (the old KeyBindingFrame is gone), so the mockup's KeyBindingFrame names do not apply.
--
-- Stock labels get a font object swapped in on every state change (the row label, the category label, the tab label), which hands
-- the stock font and colour back, so those labels are pinned: a SetFontObject puts our mono font on again and a SetTextColor is
-- mapped to ours (a gray, the stock "disabled" colour, becomes the dim text of the kit).
--
-- Left out on purpose, because the mockup shows a computed or invented display and the rule for this pass is "keep the functionality
-- the same as vanilla": the amber pending dots on the categories and the "N pending" chip by Apply, the ghost marker, default tick and
-- live peak segment of the faders, the matched letter lighting and result count of the search, the breadcrumb path in the header,
-- the elbow of a sub page, the bind map keyboard with its modifier pips and the pulsing conflict key, the status strip of the
-- bindings page, the disabled row chip ("needs restart") and the lamp switch option B.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char, G = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin, FS.GroupSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and G and Char.Box and Char.PaintBox and G.Bar and G.Rule and G.Card
    and PanelSkins.RequireExport(Theme.ApplyMono and Kit.Plate,
        "Settings.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit, FS.CharacterSkin or FS.GroupSkin missing")) then return end

local Set = {}
FS.SettingsSkin = Set

local C = G.C
local Try, Plain, List, Weak = Kit.Try, Kit.Plain, Char.List, G.Weak
local DIS = Theme.COLOR_CTRL_DIS or C.dim

local S = {
    tabs = Weak(), cats = Weak(), toggles = Weak(), rows = Weak(), steppers = Weak(), sections = Weak(), keys = Weak(),
    wells = Weak(), headers = Weak(), pins = Weak(), done = {},
}
Set.state = S

local function Step(name, fn, ...) return G.Step("settings", name, fn, ...) end

-------------------------------------------------------------------------------
-- Shared pieces
-------------------------------------------------------------------------------

-- Restyles a stock label in mono at `px` and pins it: `pick(r, g, b)` answers the colour for whatever colour the stock code writes
-- to it, and a SetFontObject (which gives the stock font and colour back) is undone. Returns the record.
local function Pin(fs, host, px, pick)
    if type(fs) ~= "table" or Kit.TypeOf(fs) ~= "FontString" then return nil end
    if S.pins[fs] then return S.pins[fs] end
    local rec = { px = px }
    S.pins[fs] = rec
    local r, g, b = Try(fs.GetTextColor, fs)
    r, g, b = Plain(r), Plain(g), Plain(b)
    rec.color = pick(type(r) == "number" and r or 1, type(g) == "number" and g or 1, type(b) == "number" and b or 1)
    Kit.RestyleLabel(fs, host, px, rec.color)
    local busy = false
    Kit.HookFunc(fs, "SetTextColor", function(_, nr, ng, nb)
        if busy then return end
        nr, ng, nb = Plain(nr), Plain(ng), Plain(nb)
        if type(nr) ~= "number" or type(ng) ~= "number" or type(nb) ~= "number" then return end
        local c = pick(nr, ng, nb)
        rec.color = c
        if nr ~= c[1] or ng ~= c[2] or nb ~= c[3] then
            busy = true
            pcall(fs.SetTextColor, fs, c[1], c[2], c[3], 1)
            busy = false
        end
    end)
    Kit.HookFunc(fs, "SetFontObject", function()
        if busy then return end
        busy = true
        Kit.RestyleLabel(fs, host, rec.px, rec.color)
        busy = false
    end)
    return rec
end

local function Const(color) return function() return color end end

-- The colour of a row label for a colour the stock code wrote: a gray is "disabled", anything else is the label.
local function ElementPick(r, g, b)
    if math.abs(r - g) < 0.06 and math.abs(g - b) < 0.06 and r < 0.7 then return DIS end
    return C.text
end

-- Tints a stock hover wash (a white 10 percent texture the stock code only shows and hides) violet.
local function Wash(region)
    if type(region) == "table" and type(region.SetColorTexture) == "function" then
        pcall(region.SetColorTexture, region, C.violet[1], C.violet[2], C.violet[3], 0.14)
    end
end

-- Holds the texture regions of `frame` whose atlas starts with `prefix` (the stock art of one family, found by name of the atlas so
-- our own regions on the same frame are left alone).
local function HoldAtlas(frame, prefix)
    for _, region in ipairs(List(frame, "GetRegions")) do
        local atlas = Try(region.GetAtlas, region)
        if type(atlas) == "string" and atlas:find(prefix) then HeldArt.Hold(region) end
    end
end

-- A chevron of 2 px cells (the pager keys draw theirs the same way) centred in `host`: dir "l", "r", "u" or "d", `n` cells across
-- (odd). rec.cells are the cell textures, rec.Paint(color, alpha) tints them all.
local function Chevron(host, dir, n, thick, step)
    thick, step = thick or 2, step or 2
    local half = (n - 1) / 2
    local horizontal = dir == "l" or dir == "r"
    local depth = half * step + thick
    local gw, gh = depth, n * thick
    if not horizontal then gw, gh = gh, gw end
    local hw, hh = Kit.SizePx(host)
    local ox, oy = math.floor(((hw or gw) - gw) / 2), math.floor(((hh or gh) - gh) / 2)
    local rec = { cells = {} }
    for i = 0, n - 1 do
        local d = math.abs(i - half)
        local x, y
        if horizontal then
            x, y = (dir == "l") and d * step or (half - d) * step, i * thick
        else
            x, y = i * thick, (dir == "u") and d * step or (half - d) * step
        end
        rec.cells[#rec.cells + 1] = Kit.Rect(host, ox + x, oy + y, thick, thick, C.violet, 1, "OVERLAY", 7)
    end
    function rec.Paint(c, a)
        for _, t in ipairs(rec.cells) do t:SetColorTexture(c[1], c[2], c[3], a or 1) end
    end
    function rec.SetShown(shown)
        for _, t in ipairs(rec.cells) do t:SetShown(shown) end
    end
    return rec
end

-------------------------------------------------------------------------------
-- The panel: inner frame art, output text, the two wells
-------------------------------------------------------------------------------

local function SkinPanelParts(panel)
    HoldAtlas(panel, "^Options_")
    G.Mono(panel.OutputText, panel, 12, C.text)
    for _, key in ipairs({ "CategoryList", "Container" }) do
        local f = panel[key]
        if type(f) == "table" and type(f.CreateTexture) == "function" and not S.wells[f] then
            local box = Char.Box(f, "BORDER")
            Char.PaintBox(box, C.ink, 0.55, C.dim, 1, 1)
            S.wells[f] = box
        end
    end
end

-------------------------------------------------------------------------------
-- The Game / AddOns tabs (MinimalTabTemplate): a cut plate over the lower part of the stock tab, where its label sits
-------------------------------------------------------------------------------

local TAB = { H = 28, CUT = 5 }

local function SeatTab(tab)
    local rec = S.tabs[tab]
    if not rec then return end
    local w, h = Kit.SizePx(tab)
    if not w then return end
    local ph = math.min(TAB.H, h)
    local y = h - ph
    Kit.Place(rec.plate.fill, tab, 0, y, w, ph)
    Kit.Place(rec.plate.ring, tab, 0, y, w, ph)
    if rec.plate.ring2 then Kit.Place(rec.plate.ring2, tab, 1, y + 1, w - 2, ph - 2) end
    Kit.Move(rec.led, 6, y + ph - 4, math.max(1, w - 12), 2)
end

local function PaintTab(tab)
    local rec = S.tabs[tab]
    if not rec then return end
    local selected = Plain(Try(tab.IsSelected, tab)) == true
    local hover = rec.state and (rec.state.hover or rec.state.pressed)
    Kit.PaintPlate(rec.plate, selected and C.band or C.ink, 1, selected and C.cyan or (hover and C.violet or C.dim), 1, selected and 2 or 1)
    rec.led:SetShown(selected)
    rec.color = selected and C.cyan or (hover and C.text or C.muted)
    if rec.label then Kit.Recolor(rec.label, rec.color) end
end

local function SkinTab(tab)
    if type(tab) ~= "table" or S.tabs[tab] or type(tab.CreateTexture) ~= "function" then return end
    HeldArt.HoldButton(tab)
    local w, h = Kit.SizePx(tab)
    local rec = { plate = Kit.Plate(tab, TAB.CUT, w or 100, math.min(TAB.H, h or TAB.H)) }
    rec.led = Kit.Rect(tab, 6, 0, 1, 2, C.cyan, 1, "OVERLAY", 3)
    S.tabs[tab] = rec
    Pin(tab.Text, tab, 12, function() return rec.color or C.muted end)
    rec.label = tab.Text
    rec.state = Kit.Track(tab, PaintTab)
    Kit.HookFunc(tab, "OnSelected", function() PaintTab(tab) end)
    Kit.HookScript(tab, "OnSizeChanged", function() SeatTab(tab) end)
    SeatTab(tab)
    PaintTab(tab)
end

-------------------------------------------------------------------------------
-- The category list
-------------------------------------------------------------------------------

local function PaintCat(row)
    local rec = S.cats[row]
    if not rec then return end
    local hover = rec.state and (rec.state.hover or rec.state.pressed)
    if rec.selected then
        Char.PaintBox(rec.box, C.band, 1, C.violet, 0, 1)
    elseif hover then
        Char.PaintBox(rec.box, C.violet, 0.16, C.violet, 0, 1)
    else
        Char.PaintBox(rec.box, C.band, 0, C.violet, 0, 1)
    end
    rec.led.Paint(rec.selected and C.cyan or C.violet, rec.selected and 1 or 0)
    rec.color = rec.selected and C.cyan or C.text
    if rec.label then Kit.Recolor(rec.label, rec.color) end
end

local function PaintToggle(button)
    local rec = S.toggles[button]
    if not rec then return end
    local c = rec.state and (rec.state.hover or rec.state.pressed) and C.cyan or C.muted
    rec.open.Paint(c)
    rec.closed.Paint(c)
end

local function Expanded(row)
    local data = Try(row.GetElementData, row)
    local category = type(data) == "table" and type(data.data) == "table" and data.data.category
    local open = type(category) == "table" and Plain(Try(category.IsExpanded, category))
    return open ~= false
end

local function SkinToggle(row)
    local button = row.Toggle
    if type(button) ~= "table" or S.toggles[button] or type(button.CreateTexture) ~= "function" then return end
    HeldArt.HoldButton(button)
    local rec = { open = Chevron(button, "d", 5), closed = Chevron(button, "r", 5) }
    S.toggles[button] = rec
    local function show(expanded)
        rec.open.SetShown(expanded)
        rec.closed.SetShown(not expanded)
    end
    show(Expanded(row))
    Kit.HookFunc(row, "SetExpanded", function(_, expanded) show(Plain(expanded) == true) end)
    rec.state = Kit.Track(button, PaintToggle)
    PaintToggle(button)
end

local function IsActiveBar(region)
    return type(region) == "table" and Try(region.GetAtlas, region) == "Options_List_Active" and Try(region.IsShown, region) == true
end

local function SkinCategoryButton(row)
    local rec = S.cats[row]
    if rec then
        rec.selected = IsActiveBar(row.Texture) or rec.selected
        PaintCat(row)
        return
    end
    local selected = IsActiveBar(row.Texture)
    HeldArt.HoldButton(row)
    rec = { box = Char.Box(row, "BORDER"), led = G.Bar(row, C.violet, 3, 0), selected = selected }
    S.cats[row] = rec
    Pin(row.Label, row, 12, function() return rec.color or C.text end)
    rec.label = row.Label
    rec.state = Kit.Track(row, PaintCat)
    Kit.HookFunc(row, "UpdateStateInternal", function(_, selectedNow)
        rec.selected = Plain(selectedNow) == true
        PaintCat(row)
    end)
    Step("toggle", SkinToggle, row)
    PaintCat(row)
end

local function SkinCategoryHeader(row)
    if S.cats[row] then return end
    S.cats[row] = { header = true }
    HeldArt.Hold(row.Background)
    Pin(row.Label, row, 11, Const(C.muted))
    G.Rule(row, C.dim, 1, -1, 4)
end

local function SkinCategoryRow(row)
    if type(row) ~= "table" then return end
    if type(row.Toggle) == "table" and type(row.Label) == "table" then
        SkinCategoryButton(row)
    elseif type(row.Background) == "table" and type(row.Label) == "table" then
        SkinCategoryHeader(row)
    end
end

-------------------------------------------------------------------------------
-- The settings list: header and pooled rows
-------------------------------------------------------------------------------

local function SkinListHeader(list)
    local head = list.Header
    if type(head) ~= "table" or S.headers[head] then return end
    G.HoldRegions(head)
    Pin(head.Title, head, 16, Const(C.cyan))
    S.headers[head] = G.Rule(head, C.dim, 1, -1, 0)
end

-- A stepper key of a dropdown row (its Decrement and Increment buttons): the stock art held, a bare chevron of ours, violet at
-- rest, cyan under the hand, dim when the dropdown is at its end.
local function PaintStepper(button)
    local rec = S.steppers[button]
    if not rec then return end
    local on = Kit.IsEnabled(button)
    local hover = on and rec.state and (rec.state.hover or rec.state.pressed)
    rec.Paint(not on and DIS or (hover and C.cyan or C.violet), on and 1 or 0.6)
end

local function SkinStepper(button, dir)
    if type(button) ~= "table" or S.steppers[button] or type(button.CreateTexture) ~= "function" then return end
    HeldArt.HoldButton(button)
    local rec = Chevron(button, dir, 7)
    S.steppers[button] = rec
    rec.state = Kit.Track(button, PaintStepper)
    PaintStepper(button)
end

local function SkinElement(row)
    Pin(row.Text, row, 12, ElementPick)
    if type(row.Tooltip) == "table" then Wash(row.Tooltip.HoverBackground) end
    if type(row.Checkbox) == "table" then Wash(row.Checkbox.HoverBackground) end
    local control = row.Control
    if type(control) == "table" then
        SkinStepper(control.DecrementButton, "l")
        SkinStepper(control.IncrementButton, "r")
        Pin(control.Label, control, 12, Const(C.text))
    end
end

local function SkinSectionTitle(row)
    Pin(row.Title, row, 14, Const(C.cyan))
    G.Rule(row, C.dim, 1, -4, 7)
end

-- An expandable section (the "Advanced" bars): a band bar with a plus that turns to a minus.
local function SectionOpen(row)
    local data = Try(row.GetElementData, row)
    return type(data) == "table" and type(data.data) == "table" and Plain(data.data.expanded) == true
end

local function PaintSection(button)
    local rec = S.sections[button]
    if not rec then return end
    local hover = rec.state and (rec.state.hover or rec.state.pressed)
    Char.PaintBox(rec.box, C.band, 1, hover and C.cyan or C.dim, 1, 1)
    rec.hbar:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 1)
    rec.vbar:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 1)
end

local function SyncSection(row)
    local rec = row.Button and S.sections[row.Button]
    if rec then rec.vbar:SetShown(not SectionOpen(row)) end
end

local function SkinSection(row)
    local button = row.Button
    if type(button) ~= "table" or S.sections[button] or type(button.CreateTexture) ~= "function" then return end
    HeldArt.HoldButton(button)
    local rec = { box = Char.Box(button, "BORDER") }
    S.sections[button] = rec
    local _, h = Kit.SizePx(button)
    local mid = math.floor((h or 30) / 2)
    rec.hbar = Kit.Rect(button, 8, mid - 1, 8, 2, C.cyan, 1, "OVERLAY", 3)
    rec.vbar = Kit.Rect(button, 11, mid - 4, 2, 8, C.cyan, 1, "OVERLAY", 3)
    Pin(button.Text, button, 12, Const(C.text))
    rec.state = Kit.Track(button, PaintSection)
    Kit.HookScript(button, "OnClick", function() SyncSection(row) end)
    PaintSection(button)
end

-- A keybinding key cell. The shared text button plate is the key; on top of it an LED underline (violet bound, dim free, cyan under
-- the hand, amber while it listens for a key) and an amber ring while it listens, since the stock selected glow is held with the rest.
local function PaintKey(button)
    local rec = S.keys[button]
    if not rec then return end
    local glow = button.SelectedHighlight
    local listening = type(glow) == "table" and Try(glow.IsShown, glow) == true
    local text = Plain(Try(button.GetText, button))
    local bound = type(text) == "string" and text ~= "" and text ~= _G.NOT_BOUND
    local hover = rec.state and (rec.state.hover or rec.state.pressed)
    local c = listening and C.amber or (hover and C.cyan or (bound and C.violet or C.dim))
    rec.led:SetColorTexture(c[1], c[2], c[3], (listening or hover or bound) and 1 or 0.6)
    Char.PaintBox(rec.box, C.ink, 0, C.amber, listening and 1 or 0, 2)
end

local function SkinKey(button)
    if type(button) ~= "table" or S.keys[button] or type(button.CreateTexture) ~= "function" then return end
    local w, h = Kit.SizePx(button)
    local rec = { box = Char.Box(button, "OVERLAY") }
    rec.led = Kit.Rect(button, 5, (h or 22) - 5, math.max(1, (w or 160) - 10), 2, C.violet, 1, "OVERLAY", 2)
    S.keys[button] = rec
    rec.state = Kit.Track(button, PaintKey)
    Kit.HookFunc(button, "SetSelected", function() PaintKey(button) end)
    Kit.HookFunc(button, "SetText", function() PaintKey(button) end)
    PaintKey(button)
end

local function SkinBinding(row)
    Pin(row.Label, row, 12, Const(C.text))
    Wash(row.Highlight)
    PanelSkins.SweepTextButtons(row)
    SkinKey(row.Button1)
    SkinKey(row.Button2)
end

local function SkinSearch(row)
    G.Card(row, { hold = { "^MouseoverOverlay" }, accent = C.cyan, px = 12 })
end

local function RowKind(row)
    if type(row) ~= "table" then return nil end
    if row.Button1 and row.Button2 and row.Label then return "binding" end
    if row.MouseoverOverlay and row.Title then return "search" end
    if row.Text and row.Tooltip then return "element" end
    if type(row.Button) == "table" and row.Button.Text and row.Button.Left then return "section" end
    if row.Title and not row.Text then return "header" end
    if type(row.text) == "table" and Kit.TypeOf(row.text) == "FontString" then return "preface" end
    if row.Text then return "notice" end
    return nil
end

local SKIN = {
    binding = SkinBinding, search = SkinSearch, element = SkinElement, section = SkinSection, header = SkinSectionTitle,
    preface = function(row) Pin(row.text, row, 12, Const(C.muted)) end,
    notice = function(row) Pin(row.Text, row, 12, Const(C.pink)) end,
}

local function SkinListRow(row)
    local kind = RowKind(row)
    if not kind then return end
    -- the shared controls kit and text buttons first: a binding key's plate must exist before our LED is drawn over it
    PanelSkins.SweepControls(row)
    PanelSkins.SweepTextButtons(row)
    if not S.rows[row] then
        S.rows[row] = kind
        SKIN[kind](row)
    end
    if kind == "section" then SyncSection(row) end
end

-------------------------------------------------------------------------------
-- Drive
-------------------------------------------------------------------------------

local function Reseat()
    for tab in pairs(S.tabs) do SeatTab(tab) end
end

local function Build()
    local panel = _G.SettingsPanel
    if type(panel) ~= "table" or S.done.panel or type(panel.CreateTexture) ~= "function" then return end
    S.done.panel = true
    panel.fsSettingsSkin = true
    Step("panel", SkinPanelParts, panel)
    Step("game tab", SkinTab, panel.GameTab)
    Step("addons tab", SkinTab, panel.AddOnsTab)
    local categories = panel.CategoryList
    if type(categories) == "table" then
        G.Rows(categories.ScrollBox, function(row) Step("category", SkinCategoryRow, row) end)
    end
    local list = panel.Container and panel.Container.SettingsList
    if type(list) == "table" then
        Step("header", SkinListHeader, list)
        G.Rows(list.ScrollBox, function(row) Step("row", SkinListRow, row) end)
    end
    Kit.HookScript(panel, "OnShow", function() Kit.Later(Reseat) end)
    Kit.OnReseat(Reseat)
end

PanelSkins.RegisterInspect("Settings", { { name = "SettingsPanel", guard = "fsSettingsSkin" } })

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
