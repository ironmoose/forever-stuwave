-- Forever STUwave: the power buttons and the module list (ticket B5)
-- Every module of Core/ModuleSwitch.lua that has a page gets a power button in the nav (pink glyph on, dim glyph off, the
-- nav text muted); an off module's page shows the off card instead of its settings. The Modules page lists all the switches
-- with a RELOAD tag on the ones that wait for a Reload UI, and Profiles gets a Modules section with ALL ON. Everything here
-- reads and writes through FS.ModuleSwitch; the window is reached only through its extension points (NavSlot, On,
-- RegisterCategory, ExtendTab) and the shared builders. Without the store (a harness that does not load it) the file does nothing.

local _, FS = ...

local CW = FS.ConfigWindow
local MS = FS.ModuleSwitch
if not (CW and CW.UI and CW.I and MS) then return end

local UI, I, S, C = CW.UI, CW.I, CW.Spec, CW.C
local Theme = FS.Theme
local ui = I.ui

-------------------------------------------------------------------------------
-- Look (prototype: .pwr, .navi.off, .offcard, .rl in mockups/config-window-2026-11-25.html)
-------------------------------------------------------------------------------

-- Colours the prototype's CSS names but ConfigSpec's map does not carry: the off glyph and off nav text (--dis), the
-- off nav text on the selected row, and the off card's frame (--dim).
local DIS = { 0.361, 0.329, 0.502, 1 }
local DIS_SELECTED = { 0.373, 0.561, 0.612, 1 }
local DIM = { 0.294, 0.165, 0.525, 1 }
local WHITE = { 1, 1, 1, 1 }

-- The off card: a 64 unit button (1 unit frame) holding the glyph at 2x, 16 above the two text lines (16 high each).
local CARD_BOX, CARD_GRID, CARD_UNIT, CARD_GAP, CARD_LINE_H = 64, 16, 2, 16, 16
local GLOW_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\glow_round.tga"

-- The prototype's power glyph (PWR_SVG: an arc open at the top with a bar through the gap) as rects on a unit grid,
-- { x, y, w, h }, drawn by hand for the 12 grid (nav, glyph 12 in the PWR box) and the 16 grid (the card, at 2x = 32).
local GLYPHS = {
    [12] = {
        { 5, 0, 2, 6 }, { 2, 3, 1, 1 }, { 9, 3, 1, 1 }, { 1, 4, 2, 4 }, { 9, 4, 2, 4 },
        { 2, 8, 2, 1 }, { 8, 8, 2, 1 }, { 3, 9, 6, 1 }, { 4, 10, 4, 1 },
    },
    [16] = {
        { 7, 0, 2, 8 }, { 3, 4, 1, 1 }, { 12, 4, 1, 1 }, { 2, 5, 3, 1 }, { 11, 5, 3, 1 }, { 2, 6, 2, 5 }, { 12, 6, 2, 5 },
        { 3, 11, 2, 1 }, { 11, 11, 2, 1 }, { 3, 12, 3, 1 }, { 10, 12, 3, 1 }, { 4, 13, 8, 1 }, { 6, 14, 4, 1 },
    },
}

local function NewGlyph(parent, grid, unit)
    local size = grid * unit
    local glyph = { textures = {}, grid = grid, unit = unit }
    for _, r in ipairs(GLYPHS[grid]) do
        local t = parent:CreateTexture(nil, "ARTWORK")
        t:SetSize(r[3] * unit, r[4] * unit)
        t:SetPoint("TOPLEFT", parent, "CENTER", -size / 2 + r[1] * unit, size / 2 - r[2] * unit)
        glyph.textures[#glyph.textures + 1] = t
    end
    function glyph.SetColor(color)
        for _, t in ipairs(glyph.textures) do t:SetColorTexture(color[1], color[2], color[3], color[4] or 1) end
    end
    return glyph
end

-- The tooltip line a switch change needs a reload for, or says it applies at once.
local function ApplyLine(key)
    if MS.IsLive(key) then return "Takes effect at once." end
    return "Takes effect after Reload UI."
end

-- "A", "A and B", "A, B and C" from module keys.
local function JoinLabels(keys)
    local names = {}
    for i, key in ipairs(keys) do names[i] = MS.Label(key) or key end
    if #names <= 1 then return names[1] or "" end
    return table.concat(names, ", ", 1, #names - 1) .. " and " .. names[#names]
end

-------------------------------------------------------------------------------
-- Asking for a change
-------------------------------------------------------------------------------

-- The one path every switch control takes. Turning one on pulls in what it requires; turning one off that another module
-- needs asks once, naming them, and turns them off too on Confirm. Returns false (and says why) when settings are read-only.
local function Request(key, on)
    if not MS.IsWritable() then
        I.Say("settings are read-only this session.")
        return false
    end
    if on then
        MS.SetWithDeps(key, true)
        return true
    end
    local dependents = MS.Dependents(key)
    if #dependents == 0 then
        MS.Set(key, false)
        return true
    end
    UI.Confirm(("Turning off %s also turns off %s."):format(MS.Label(key) or key, JoinLabels(dependents)), function()
        MS.SetWithDeps(key, false)
    end)
    return true
end

-------------------------------------------------------------------------------
-- The power button (nav and off card)
-------------------------------------------------------------------------------

local function PowerColor(b)
    local color = b.fsOn and C.pink or DIS
    if b.fsHover then color = C.cyan end
    if b.fsDown then color = I.Mix(color, WHITE, 0.4) end
    return color
end

local function PaintPower(b)
    local color = PowerColor(b)
    b.fsGlyph.SetColor(color)
    if b.fsGlow then
        b.fsGlow:SetVertexColor(color[1], color[2], color[3], (b.fsOn or b.fsHover) and 0.35 or 0)
    end
    if b.fsRing then I.TintAll(b.fsRing, b.fsHover and C.cyan or DIM) end
    b:SetAlpha(MS.IsWritable() and 1 or 0.4)
end

-- o = { box, grid, unit, glow, ring, tip(owner) }. The caller sets b.fsOn and calls b.fsPaint().
local function NewPowerButton(parent, o)
    local b = CreateFrame("Button", nil, parent)
    b:SetSize(o.box, o.box)
    b:RegisterForClicks("LeftButtonUp")
    if o.glow then
        b.fsGlow = b:CreateTexture(nil, "BACKGROUND")
        b.fsGlow:SetTexture(GLOW_TEXTURE)
        b.fsGlow:SetBlendMode("ADD")
        b.fsGlow:SetSize(o.box + 8, o.box + 8)
        b.fsGlow:SetPoint("CENTER", b, "CENTER", 0, 0)
    end
    if o.ring then b.fsRing = I.Outline(b, DIM, 1) end
    b.fsGlyph = NewGlyph(b, o.grid, o.unit)
    b.fsOn = true
    b.fsPaint = function() PaintPower(b) end
    b:SetScript("OnEnter", function(self)
        self.fsHover = true
        PaintPower(self)
        if o.tip then o.tip(self) end
    end)
    b:SetScript("OnLeave", function(self)
        self.fsHover, self.fsDown = false, false
        PaintPower(self)
        GameTooltip:Hide()
    end)
    b:SetScript("OnMouseDown", function(self) self.fsDown = true; PaintPower(self) end)
    b:SetScript("OnMouseUp", function(self) self.fsDown = false; PaintPower(self) end)
    PaintPower(b)
    return b
end

-- Title, what else it turns off or on, and when it takes effect.
local function ShowPowerTip(owner, key, label)
    local on = MS.Wanted(key)
    GameTooltip:SetOwner(owner, "ANCHOR_RIGHT")
    GameTooltip:SetText((on and "Turn off " or "Turn on ") .. label, 1, 1, 1, 1, true)
    if on then
        local dependents = MS.Dependents(key)
        if #dependents > 0 then GameTooltip:AddLine("Also turns off " .. JoinLabels(dependents) .. ".", 1, 1, 1, true) end
    else
        local needed = {}
        for _, k in ipairs(MS.Requires(key)) do
            if not MS.Wanted(k) then needed[#needed + 1] = k end
        end
        if #needed > 0 then GameTooltip:AddLine("Also turns on " .. JoinLabels(needed) .. ".", 1, 1, 1, true) end
    end
    GameTooltip:AddLine(ApplyLine(key), 1, 1, 1, true)
    if not MS.IsWritable() then GameTooltip:AddLine("Settings are read-only this session.", 1, 1, 1, true) end
    GameTooltip:Show()
end

-------------------------------------------------------------------------------
-- Nav
-------------------------------------------------------------------------------

local HELP_GAP = S.PWR + S.PWR_R + 6 + S.DOT + 4     -- right edge of the ? mark: left of the changed dot

local function PageLabel(page)
    for _, cat in ipairs(CW.Categories()) do
        if cat.key == page then return cat.label end
    end
    return page
end

-- The nav text is recoloured by the nav on every select (SetSelected), so the muting lives in the label's own
-- SetTextColor: when the module is off the colour handed in is replaced by the off colour.
local function HookLabel(nav, key)
    local label = nav.fsLabel
    if label.fsMuteHook then return end
    label.fsMuteHook = true
    local plain = label.SetTextColor
    label.SetTextColor = function(self, r, g, b, a)
        if not MS.Wanted(key) then
            local c = nav.fsSelected and DIS_SELECTED or DIS
            return plain(self, c[1], c[2], c[3], a or 1)
        end
        return plain(self, r, g, b, a)
    end
end

local function PaintNav(nav, key)
    local power = nav.fsPower
    if not power then return end
    power.fsOn = MS.Wanted(key)
    PaintPower(power)
    local base = nav.fsSelected and C.cyan or C.muted
    nav.fsLabel:SetTextColor(base[1], base[2], base[3], 1)
    -- a ? beside the button while turning this module off would turn others off too
    local dependents = power.fsOn and MS.Dependents(key) or {}
    local help = nav.fsPowerHelp
    if #dependents > 0 then
        help.fsTip = "Turning this off also turns off " .. JoinLabels(dependents) .. "."
        help:Show()
    else
        help:Hide()
    end
end

local function AttachPower(nav, key, page)
    local slot = nav.fsSlot
    local power = NewPowerButton(slot, {
        box = S.PWR, grid = 12, unit = 1, glow = true,
        tip = function(self) ShowPowerTip(self, key, PageLabel(page)) end,
    })
    power:SetPoint("CENTER", slot, "CENTER", 0, 0)
    power.fsKey = key
    power:SetScript("OnClick", function() Request(key, not MS.Wanted(key)) end)
    -- the nav row keeps its hover tint while the pointer is on the button
    power:HookScript("OnEnter", function()
        local fn = nav:GetScript("OnEnter")
        if fn then fn(nav) end
    end)
    power:HookScript("OnLeave", function()
        local over = type(nav.IsMouseOver) == "function" and nav:IsMouseOver()
        local fn = nav:GetScript("OnLeave")
        if fn and not over then fn(nav) end
    end)
    nav.fsPower = power
    local help = UI.HelpIcon(nav, "")
    help:SetPoint("RIGHT", nav, "RIGHT", -HELP_GAP, 0)
    help:Hide()
    nav.fsPowerHelp = help
    HookLabel(nav, key)
    PaintNav(nav, key)
end

-- The Modules item of the nav counts the switches that wait for a Reload UI (the same tag as the list rows).
local chip

local function PaintChip()
    local nav = ui.nav and ui.nav.modules
    if not nav then return end
    if not chip then
        local slot = nav.fsSlot
        chip = CreateFrame("Frame", nil, slot)
        chip:SetHeight(S.COUNT_H)
        chip:SetPoint("RIGHT", slot, "RIGHT", 0, 0)
        chip.fsEdges = I.Outline(chip, C.pink, 0.5)
        chip.fsText = I.Label(chip, "", S.SMALL, C.pink)
        chip.fsText:SetPoint("CENTER", chip, "CENTER", 0, 0)
    end
    local count = MS.PendingCount()
    chip.fsText:SetText(tostring(count))
    chip:SetWidth(S.Snap(chip.fsText:GetStringWidth() + 8))
    chip:SetShown(count > 0)
end

local function AttachAll()
    if not ui.frame then return end
    for _, key in ipairs(MS.Keys()) do
        local page = MS.Page(key)
        local nav = page and ui.nav[page]
        if nav and not nav.fsPower and CW.NavSlot(page) then AttachPower(nav, key, page) end
    end
    PaintChip()
end

local function PaintAllNav()
    for _, key in ipairs(MS.Keys()) do
        local page = MS.Page(key)
        local nav = page and ui.nav[page]
        if nav then PaintNav(nav, key) end
    end
    PaintChip()
end

-------------------------------------------------------------------------------
-- The off card
-------------------------------------------------------------------------------

local card
local held       -- the tab page the card hides

-- A module whose off card adds one thing: a ? after the second line carries it. The game's pet unit frame is hidden by Unit
-- frames, not by the pet bar, so turning the pet bar off leaves it hidden while Unit frames is on.
local OFF_NOTES = {
    ["m.pet"] = "The game's own pet unit frame is handled by Unit frames, not by this switch.",
}
local HELP_GAP_CARD = 6

-- The module of the page on screen when it is off, with the page key; false when no card is wanted.
local function CardWanted()
    local frame = ui.frame
    if not (frame and frame:IsShown()) then return false end
    local page = ui.current
    for _, key in ipairs(MS.Keys()) do
        if MS.Page(key) == page then
            if MS.Wanted(key) then return false end
            return true, page, key
        end
    end
    return false
end

local function EnsureCard()
    if card then return card end
    local well = ui.well
    card = CreateFrame("Frame", "ForeverSTUwaveConfigOffCard", well)
    card:SetFrameLevel(well:GetFrameLevel() + 40)
    card:EnableMouse(true)
    card:EnableMouseWheel(true)
    card:SetScript("OnMouseWheel", function() end)
    local fill = card:CreateTexture(nil, "BACKGROUND")
    fill:SetColorTexture(C.track[1], C.track[2], C.track[3], 1)
    fill:SetAllPoints(card)
    -- the area the scrolling page would have had: the block of button and text is centred in it
    local area = CreateFrame("Frame", nil, card)
    area:SetPoint("TOPLEFT", card, "TOPLEFT", S.CONTENT_L, -S.CONTENT_T)
    area:SetPoint("BOTTOMRIGHT", card, "BOTTOMRIGHT", -S.CONTENT_R, S.CONTENT_B)
    local big = NewPowerButton(card, { box = CARD_BOX, grid = CARD_GRID, unit = CARD_UNIT, ring = true })
    big.fsOn = false
    big:SetPoint("TOP", area, "CENTER", 0, (CARD_BOX + CARD_GAP + 2 * CARD_LINE_H) / 2)
    big:SetScript("OnClick", function()
        if card.fsKey then Request(card.fsKey, true) end
    end)
    card.fsBig = big
    card.fsLine1 = I.Label(card, "", S.TEXT, C.text)
    card.fsLine1:SetPoint("TOP", big, "BOTTOM", 0, -CARD_GAP)
    card.fsLine1:SetPoint("LEFT", area, "LEFT", 0, 0)
    card.fsLine1:SetPoint("RIGHT", area, "RIGHT", 0, 0)
    card.fsLine1:SetJustifyH("CENTER")
    card.fsLine2 = I.Label(card, "", S.TEXT, C.muted)
    card.fsLine2:SetPoint("TOP", card.fsLine1, "BOTTOM", 0, 0)
    card.fsLine2:SetPoint("LEFT", area, "LEFT", 0, 0)
    card.fsLine2:SetPoint("RIGHT", area, "RIGHT", 0, 0)
    card.fsLine2:SetJustifyH("CENTER")
    card.fsHelp = UI.HelpIcon(card, "")
    card.fsHelp:Hide()
    card:Hide()
    return card
end

-- The two lines: "<Page> is off." (or "turns off at the next Reload UI." while it still runs this session) and what happens.
local function PaintCard(page, key)
    local live = MS.IsLive(key)
    local label = PageLabel(page)
    card.fsKey = key
    card.fsLine1:SetText((not live and MS.On(key)) and (label .. " turns off at the next Reload UI.") or (label .. " is off."))
    card.fsLine2:SetText(live and "Blizzard's own shows instead. Turn it on with the power button here or in the list."
        or "Blizzard's own shows instead. Turning it on takes a Reload UI.")
    card.fsBig.fsOn = false
    card.fsBig.fsHover, card.fsBig.fsDown = false, false
    PaintPower(card.fsBig)
    -- the ? sits right of where the centred second line ends
    local note = OFF_NOTES[key]
    local help = card.fsHelp
    if note then
        help.fsTip = note
        help:ClearAllPoints()
        help:SetPoint("LEFT", card.fsLine2, "CENTER", S.Snap(card.fsLine2:GetStringWidth() / 2 + HELP_GAP_CARD), 0)
        help:Show()
    else
        help:Hide()
    end
end

-- A tab page hidden under the card stays hidden when the window selects it again.
local function HookPage(page)
    if page.fsCardHook then return end
    page.fsCardHook = true
    page:HookScript("OnShow", function(self)
        if ui.tabRec and ui.tabRec.page == self and CardWanted() then self:Hide() end
    end)
end

local function UpdateCard()
    local want, page, key = CardWanted()
    local rec = ui.tabRec
    if want and rec and rec.page then
        EnsureCard()
        card:ClearAllPoints()
        card:SetPoint("TOPLEFT", ui.well, "TOPLEFT", 0, -(ui.stripH and S.TAB_STRIP_H or 0))
        card:SetPoint("BOTTOMRIGHT", ui.well, "BOTTOMRIGHT", 0, 0)
        PaintCard(page, key)
        card:Show()
        HookPage(rec.page)
        if rec.page:IsShown() then rec.page:Hide() end
        held = rec.page
    else
        if card then card:Hide() end
        local page = held
        held = nil
        if page and ui.tabRec and ui.tabRec.page == page and ui.frame and ui.frame:IsShown() then
            page:Show()
            CW.RefreshScroll()
        end
    end
end

-------------------------------------------------------------------------------
-- The Modules page
-------------------------------------------------------------------------------

-- The RELOAD tag of the prototype (.rl): pink text in a pink half strength box, COUNT_H tall.
local function NewTag(parent, text)
    local tag = CreateFrame("Frame", nil, parent)
    tag:SetHeight(S.COUNT_H)
    I.Outline(tag, C.pink, 0.5)
    local label = I.Label(tag, text, S.SMALL, C.pink)
    label:SetPoint("CENTER", tag, "CENTER", 0, 0)
    tag:SetWidth(S.Snap(label:GetStringWidth() + 8))
    return tag
end

local function BuildSwitchRow(content, key)
    local live = MS.IsLive(key)
    local row = UI.Toggle(content, {
        label = MS.Label(key),
        tip = (not live) and "Takes effect after Reload UI." or nil,
        get = function() return MS.Wanted(key) end,
        set = function(on)
            if not MS.IsWritable() then return false end
            return Request(key, on)
        end,
        isChanged = function() return not MS.Wanted(key) end,
        reset = function() MS.SetWithDeps(key, true) end,
    })
    local entry = row.fsEntry
    -- the registry knows the row by the switch key, and says what waits on a reload (the footer counts these)
    entry.key = key
    entry.reload = function()
        if MS.Pending(key) then return "Takes a Reload UI." end
    end
    local tag = NewTag(row, "RELOAD")
    tag:SetPoint("LEFT", row.fsHelp or row.fsLabel, "RIGHT", S.Q_GAP, 0)
    I.Track(function() tag:SetShown(MS.Pending(key)) end)
end

local function BuildModules(content)
    UI.Section(content, { title = "Modules" })
    for _, key in ipairs(MS.Keys()) do BuildSwitchRow(content, key) end
end

-- After Profiles, before Help. Not in the prototype's nav: the power buttons are the way in, this is the list.
CW.RegisterCategory({
    key = "modules", label = "Modules", group = "GENERAL", order = 2.5,
    tabs = { { key = "all", label = "All modules", build = BuildModules } },
})

-- Profiles / Modules: every switch back on (after Share, before Saved data).
CW.ExtendTab("profiles", "p", { title = "Modules" }, function(content)
    UI.Button(content, {
        label = "Turn every module back on", regKey = "modules.allon", text = "ALL ON",
        tip = "Every power button in the list back on. Takes a Reload UI.",
        onClick = function()
            if not MS.IsWritable() then
                I.Say("settings are read-only this session.")
                return
            end
            MS.TurnAllOn()
        end,
    })
end, 200)

-------------------------------------------------------------------------------
-- Wiring
-------------------------------------------------------------------------------

local function Refresh()
    AttachAll()
    UpdateCard()
end

CW.On("show", Refresh)
CW.On("select", Refresh)

-- The footer's Reload UI count: every switch that waits on a reload, even one flipped before the Modules page was built.
if CW.AddReloadSource then
    CW.AddReloadSource(function()
        local list = {}
        for _, key in ipairs(MS.PendingKeys()) do
            list[#list + 1] = { MS.Label(key) or key, "Takes a Reload UI." }
        end
        return list
    end)
end

-- Any change of a switch (a click, ALL ON, an import): repaint the buttons, the card, the tags and the list.
MS.OnAnyChange(function()
    if not ui.frame then return end
    PaintAllNav()
    UpdateCard()
    CW.RefreshAll()
end)
