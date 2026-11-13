#!/usr/bin/env python3
"""Runs the real Modules/Skins/ChatSettings.lua (and GroupKit.lua) headless against a mock chat settings window (tools/charskin_support.py).

Pinned: the panel chrome and band title replace the stock border and header (the border frame is never boxed), every backdrop well (the category
list, the page well, the message type boxes, the combat filter list) loses its nine slice and gets an ink ring, every message type row
and colour row is an ink card with its label in mono and its check button and colour swatch left stock, the category buttons and the
combat filter rows are cards that light with the stock highlight lock, a row a stock builder makes later (the channel rows) is skinned
after the builder runs, the sweep for the text buttons and check boxes is on the window, no script or attribute is written on a
Blizzard widget, and nothing is built in combat. Run `python3 tools/chatsettingsskin-harness.py [--png debug/chat]`. The mock is NOT
the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring = BLZ.blz, BLZ.tex, BLZ.fstring
local build = BuildBlizzard

-- TooltipBackdropTemplate: a NineSlice child that carries the pieces
local function well(parent, name, w, h, x, y)
    local f = blz("Frame", name, parent, w, h, "TOPLEFT", x, y)
    f.NineSlice = blz("Frame", nil, f, w, h)
    f.NineSlice.TopLeftCorner = tex(f.NineSlice, nil, "BORDER")
    f.NineSlice.Center = tex(f.NineSlice, nil, "BACKGROUND")
    f.backdropBorderColorAlpha = 0.5
    return f
end

local function titled(f, name, title)
    f.header = fstring(f, name and (name .. "Title") or nil, title, 12, { 1, 0.82, 0, 1 })
    f.header.points[1] = { point = "TOPLEFT", rel = f, relPoint = "TOPLEFT", x = 10, y = -8 }
    return f
end

local function swatch(row, name)
    local s = blz("Button", name .. "ColorSwatch", row, 16, 16, "RIGHT", -8, 0)
    s.SwatchBg = tex(s, nil, "BACKGROUND")
    s.scripts.OnClick = function() end
    row.ColorSwatch = s
    return s
end

-- ChatConfigCheckboxWithSwatchTemplate: a border box (clear backdrop) that carries a check button and a swatch
local function checkRow(parent, name, y, label, withSwatch)
    local r = blz("Frame", name, parent, 300, 24, "TOPLEFT", 8, -y)
    r.NineSlice = blz("Frame", nil, r, 300, 24)
    r.NineSlice.TopLeftCorner = tex(r.NineSlice, nil, "BORDER")
    r.backdropColorAlpha = 0
    r.CheckButton = blz("CheckButton", name .. "Check", r, 24, 24, "LEFT", 2, 0)
    r.CheckButton.Text = fstring(r.CheckButton, nil, label, 12, { 1, 1, 1, 1 })
    r.CheckButton.Text.points[1] = { point = "LEFT", rel = r.CheckButton, relPoint = "RIGHT", x = 2, y = 0 }
    r.CheckButton.scripts.OnClick = function() end
    r.BlankText = fstring(r, nil, "", 12, { 1, 1, 1, 1 })
    if withSwatch then swatch(r, name) end
    return r
end

-- ChatConfigSwatchTemplate: a border box with a label and a swatch and no check button
local function colourRow(parent, name, y, label)
    local r = blz("Frame", name, parent, 300, 24, "TOPLEFT", 8, -y)
    r.NineSlice = blz("Frame", nil, r, 300, 24)
    r.NineSlice.TopLeftCorner = tex(r.NineSlice, nil, "BORDER")
    r.backdropColorAlpha = 0
    r.label = fstring(r, nil, label, 12, { 1, 1, 1, 1 })
    r.label.points[1] = { point = "LEFT", rel = r, relPoint = "LEFT", x = 8, y = 0 }
    swatch(r, name)
    return r
end

-- ConfigCategoryButtonTemplate
local function categoryButton(parent, name, y, label, id)
    local b = blz("Button", name, parent, 112, 22, "TOPLEFT", 6, -y)
    b:SetID(id)
    b.NormalText = fstring(b, name and (name .. "NormalText") or nil, label, 12, { 1, 0.82, 0, 1 })
    b.NormalText.points[1] = { point = "LEFT", rel = b, relPoint = "LEFT", x = 4, y = 0 }
    b.Highlight = tex(b, name and (name .. "Highlight") or nil, "HIGHLIGHT")
    b.GetHighlightTexture = function(self) return self.Highlight end
    b.LockHighlight = function(self) self.locked = true end
    b.UnlockHighlight = function(self) self.locked = false end
    b.scripts.OnClick = function() end
    b.scripts.OnEnter = function() end
    return b
end

local function panelButton(parent, name, label, x)
    local b = blz("Button", name, parent, 110, 22, "BOTTOMLEFT", x, 12)
    b.Left = tex(b, nil, "BACKGROUND"); b.Middle = tex(b, nil, "BACKGROUND"); b.Right = tex(b, nil, "BACKGROUND")
    b.Text = fstring(b, nil, label, 12, { 1, 0.82, 0, 1 })
    b.Text.points[1] = { point = "CENTER", rel = b, relPoint = "CENTER", x = 0, y = 0 }
    b.GetFontString = function(self) return self.Text end
    b.GetText = function(self) return self.Text.text end
    b.scripts.OnClick = function() end
    return b
end

function BuildBlizzard()
    build()
    for k in pairs(_G) do
        if type(k) == "string" and (k:find("^ChatConfig") or k:find("^CombatConfig") or k:find("^TextToSpeech")) then _G[k] = nil end
    end
    local win = blz("Frame", "ChatConfigFrame", UIParent, 745, 560)
    win.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 60, y = -40 }
    win.shown = false

    -- DialogBorderTemplate is itself the nine slice: its pieces are keyed on it, there is no NineSlice child
    win.Border = blz("Frame", nil, win, 745, 560)
    win.Border.TopLeftCorner = tex(win.Border, nil, "BORDER")
    win.Border.Bg = tex(win.Border, nil, "BACKGROUND")
    -- DialogHeaderTemplate
    win.Header = blz("Frame", nil, win, 200, 39, "TOP", 0, 11)
    win.Header.points[1] = { point = "TOP", rel = win, relPoint = "TOP", x = 0, y = 11 }
    win.Header.LeftBG = tex(win.Header, nil, "ARTWORK")
    win.Header.RightBG = tex(win.Header, nil, "ARTWORK")
    win.Header.CenterBG = tex(win.Header, nil, "ARTWORK")
    win.Header.Text = fstring(win.Header, nil, "Chat Settings", 14, { 1, 0.82, 0, 1 })
    win.Header.Text.points[1] = { point = "TOP", rel = win.Header, relPoint = "TOP", x = 0, y = -13 }

    local cats = well(win, "ChatConfigCategoryFrame", 125, 470, 12, -57)
    for i, label in ipairs({ "Chat", "Combat", "Channels", "Other", "Settings", "Chat 2", "Channels 2" }) do
        local b = categoryButton(cats, "ChatConfigCategoryFrameButton" .. i, 6 + (i - 1) * 24, label, i)
        b.shown = i <= 4
    end

    local bg = well(win, "ChatConfigBackgroundFrame", 590, 470, 142, -57)

    -- chat page
    local chat = blz("Frame", "ChatConfigChatSettings", bg, 570, 450, "TOPLEFT", 8, -8)
    local left = titled(well(chat, "ChatConfigChatSettingsLeft", 560, 200, 0, 0), "ChatConfigChatSettingsLeft", "Player messages")
    fstring(left, "ChatConfigChatSettingsLeftColorHeader", "COLOR", 10, { 1, 0.82, 0, 1 })
    ChatConfigChatSettingsLeftColorHeader.points[1] = { point = "TOPRIGHT", rel = left, relPoint = "TOPRIGHT", x = -10, y = -8 }
    left.rows = {}
    for i, n in ipairs({ "Say", "Emote", "Yell" }) do
        left.rows[i] = checkRow(left, "ChatConfigChatSettingsLeftCheckBox" .. i, 30 + (i - 1) * 28, n, true)
    end

    -- other page: a box of swatch rows (no check button)
    local other = blz("Frame", "ChatConfigOtherSettings", bg, 570, 450, "TOPLEFT", 8, -8)
    other.shown = false
    local combat = titled(well(other, "ChatConfigOtherSettingsCombat", 270, 120, 0, 0), "ChatConfigOtherSettingsCombat", "Combat")
    colourRow(combat, "ChatConfigOtherSettingsCombatSwatch1", 30, "Self hits")

    -- channels page: the rows are made later by the stock builder
    local chan = blz("Frame", "ChatConfigChannelSettings", bg, 570, 450, "TOPLEFT", 8, -8)
    chan.shown = false
    titled(well(chan, "ChatConfigChannelSettingsLeft", 560, 300, 0, 0), "ChatConfigChannelSettingsLeft", "Channels")
    function ChatConfig_CreateCheckboxes(frame, ...)
        local n = (frame.made or 0) + 1
        frame.made = n
        return checkRow(frame, frame:GetName() .. "CheckBox" .. n, 30 + (n - 1) * 28, "Trade", true)
    end

    -- combat page: the filter list (a ScrollBox of category style buttons)
    local csets = blz("Frame", "ChatConfigCombatSettings", bg, 570, 450, "TOPLEFT", 8, -8)
    csets.shown = false
    local filters = well(csets, "ChatConfigCombatSettingsFilters", 300, 160, 0, 0)
    csets.Filters = filters
    filters.ScrollBox = blz("Frame", nil, filters, 280, 120, "TOPLEFT", 6, -6)
    filters.ScrollBox.rows = {}
    filters.ScrollBox.ForEachFrame = function(self, fn) for _, r in ipairs(self.rows) do fn(r) end end
    filters.ScrollBox.Update, filters.ScrollBox.FullUpdate, filters.ScrollBox.SetDataProvider = function() end, function() end, function() end
    for i, n in ipairs({ "Everything", "What happened to me" }) do
        local b = categoryButton(filters.ScrollBox, nil, (i - 1) * 24, n, i)
        filters.ScrollBox.rows[i] = b
    end

    win.DefaultButton = panelButton(win, "ChatConfigFrameDefaultButton", "Defaults", 20)
    win.OkayButton = panelButton(win, "ChatConfigFrameOkayButton", "Okay", 600)
end
"""

H = Harness({
    "ButtonSkins": "Core/ButtonSkins.lua",
    "Character": "Modules/Skins/Character.lua",
    "GroupKit": "Modules/Skins/GroupKit.lua",
    "ChatSettings": "Modules/Skins/ChatSettings.lua",
}, BLIZZARD)
case = H.case

SHOW = "Fire('PLAYER_ENTERING_WORLD'); ChatConfigFrame:Show(); FlushTimers()"

case("window: the stock border and header are held, the band title is on, the border is never boxed", f"""
    {SHOW}
    local w = ChatConfigFrame
    assert(w.fsPanelTitle and w.fsPanelTitle.text == 'stuwave://chat settings', 'no band title')
    assert(w.Border.alpha == 0, 'stock border kept')
    assert(w.Header.alpha == 0, 'stock header kept')
    assert(not FS.ChatSettingsSkin.state.boxes[w.Border], 'the border was boxed')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("wells: the category list, the page well, the message boxes and the filter list are held and ringed, the headings mono", f"""
    {SHOW}
    local S = FS.ChatSettingsSkin.state
    for _, n in ipairs({{ 'ChatConfigCategoryFrame', 'ChatConfigBackgroundFrame', 'ChatConfigChatSettingsLeft', 'ChatConfigOtherSettingsCombat',
                         'ChatConfigChannelSettingsLeft', 'ChatConfigCombatSettingsFilters' }}) do
        local b = _G[n]
        assert(S.boxes[b], n .. ' not ringed')
        assert(b.NineSlice.alpha == 0, n .. ' nine slice kept')
    end
    assert(ChatConfigChatSettingsLeft.header.fontPath ~= 'stock.ttf', 'box title not mono')
    assert(ChatConfigChatSettingsLeftColorHeader.fontPath ~= 'stock.ttf', 'colour heading not mono')
""")

case("rows: a message type row is an ink card, the label mono, the check button and the colour swatch stock", f"""
    {SHOW}
    local G = FS.GroupSkin
    for i, r in ipairs(ChatConfigChatSettingsLeft.rows) do
        assert(G.cards[r], 'row ' .. i .. ' not carded')
        assert(not FS.ChatSettingsSkin.state.boxes[r], 'row ' .. i .. ' ringed as a well')
        assert(r.NineSlice.alpha == 0, 'row nine slice kept ' .. i)
        assert(r.CheckButton.Text.fontPath ~= 'stock.ttf', 'label not mono ' .. i)
        assert(r.CheckButton.scripts.OnClick and r.ColorSwatch.scripts.OnClick, 'click lost ' .. i)
        assert(r.ColorSwatch.SwatchBg.alpha == 1, 'swatch art held ' .. i)
    end
""")

case("colour rows without a check button are cards too and their swatch stays stock", f"""
    {SHOW}
    local r = ChatConfigOtherSettingsCombatSwatch1
    assert(FS.GroupSkin.cards[r], 'colour row not carded')
    assert(r.label.fontPath ~= 'stock.ttf', 'colour row label not mono')
    assert(r.ColorSwatch.SwatchBg.alpha == 1, 'swatch art held')
    assert(not FS.ChatSettingsSkin.state.boxes[r], 'colour row ringed as a well')
""")

case("categories: each button is a card with the stock highlight held, the chosen one lit by the stock lock, hover lights the edge", f"""
    {SHOW}
    local G = FS.GroupSkin
    for i = 1, 7 do
        local b = _G['ChatConfigCategoryFrameButton' .. i]
        assert(G.cards[b], 'button ' .. i .. ' not carded')
        assert(b.Highlight.alpha == 0, 'highlight kept ' .. i)
        assert(b.NormalText.fontPath ~= 'stock.ttf', 'label not mono ' .. i)
        assert(b.scripts.OnClick, 'click lost ' .. i)
    end
    local b = ChatConfigCategoryFrameButton2
    local rec = G.cards[b]
    assert(not rec.selected, 'selected before the lock')
    b:LockHighlight()
    assert(rec.selected, 'stock lock not followed')
    b:UnlockHighlight()
    assert(not rec.selected, 'stock unlock not followed')
    local idle = rec.box.edges[1].color[2]
    b:RunScript('OnEnter')
    assert(rec.box.edges[1].color[2] > idle, 'hover did not light the edge')
""")

case("combat filters: the list rows are cards, a row the pool makes later is carded when the list updates", f"""
    {SHOW}
    local G = FS.GroupSkin
    local box = ChatConfigCombatSettingsFilters.ScrollBox
    for i, r in ipairs(box.rows) do assert(G.cards[r], 'filter row ' .. i .. ' not carded') end
    local late = CreateFrame('Button', nil, box)
    late.Highlight = late:CreateTexture(nil, 'HIGHLIGHT')
    late.Highlight.blizz = true
    box.rows[#box.rows + 1] = late
    box:Update()
    assert(G.cards[late], 'late filter row not carded')
""")

case("rows the stock builder makes later (the channel list) are skinned after the builder runs", f"""
    {SHOW}
    local row = ChatConfig_CreateCheckboxes(ChatConfigChannelSettingsLeft)
    assert(not FS.GroupSkin.cards[row], 'carded before the timer')
    FlushTimers()
    assert(FS.GroupSkin.cards[row], 'late row not carded')
    assert(row.CheckButton.Text.fontPath ~= 'stock.ttf', 'late label not mono')
    local n = #row.regions
    ChatConfig_CreateCheckboxes(ChatConfigChannelSettingsLeft); FlushTimers()
    assert(#row.regions == n, 'regions grew on a second pass')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("the sweep for the text buttons, scroll bars and check boxes is on the window", f"""
    {SHOW}
    assert(ChatConfigFrame.fsSweepHook, 'window not swept on show')
    assert(FS.ButtonSkins.Parts(ChatConfigFrameOkayButton) and FS.ButtonSkins.Parts(ChatConfigFrameDefaultButton), 'text buttons not skinned')
    assert(ChatConfigFrame.fsChatSettingsSkin, 'marker missing')
""")

case("nothing is built in combat; it is built when combat ends", """
    Reset()
    __combat = true
    FS = Load({ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'ButtonSkins', 'Character', 'GroupKit', 'ChatSettings' })
    assert(not ChatConfigFrame.fsChatSettingsSkin and not FS.GroupSkin.cards[ChatConfigCategoryFrameButton1], 'built in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(ChatConfigFrame.fsChatSettingsSkin and FS.GroupSkin.cards[ChatConfigCategoryFrameButton1], 'not built when combat ended')
""")

case("a client without some of the frames degrades quietly, and a second build adds nothing", f"""
    {SHOW}
    local n = #ChatConfigCategoryFrame.regions
    FS.ChatSettingsSkin.Build(); FlushTimers()
    assert(#ChatConfigCategoryFrame.regions == n, 'regions grew')
    ChatConfigCombatSettingsFilters = nil
    ChatConfigCategoryFrameButton5 = nil
    ChatConfigFrame.Header = nil
    FS.ChatSettingsSkin.Build()
    ChatConfigFrame = nil
    FS.ChatSettingsSkin.Build()
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

SCENES = {
    "chat": "Fire('PLAYER_ENTERING_WORLD'); ChatConfigFrame:Show(); ChatConfigCategoryFrameButton1:LockHighlight(); FlushTimers(); return DumpOps({ ChatConfigFrame })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("chat settings skin", SCENES))
