-- Forever STUwave: guild bank and guild control
-- The guild bank (Blizzard_GuildBankUI: the item grid, the tab rail, the log, the money log, the tab info page, the money box and
-- the tab name and icon pop up) and the guild control window (Blizzard_GuildControlUI), restyled in place from the ODDS AND ENDS
-- mockup (mockups/odds-ends-2026-11-12.html). The text buttons, the bottom tabs, the scroll bars, the drop downs, the search and
-- edit boxes and the check boxes already wear the shared skins (the controls sweep, run on show here); this file adds the parts
-- that were still stock. One section per window below.
--
-- Skin only, as in Commerce.lua: no SetScript, no SetAttribute, no reparent, no resize or re-anchor of a Blizzard frame, post-hooks
-- and alpha holds (FS.HeldArt) only, so every deposit, withdrawal, tab purchase, rank edit and search stays stock. Names are the
-- real 12.1 tree (Blizzard_GuildBankUI Mainline, the variant the 16001 globals dump matches, Blizzard_GuildControlUI, and the
-- IconSelectorPopupFrameTemplate of Blizzard_SharedXML); each one is feature detected and a missing frame is skipped, which also
-- covers a client whose bank is the older layout. The two windows load on demand and are caught when their addon loads. The rank
-- rows and the bank tab rows of the control window are made by Blizzard's own update functions, so each is skinned right after
-- the stock call that makes it.
--
-- Left out on purpose, because the mockup shows a computed display and the rule for this pass is "keep the functionality the same
-- as vanilla": the ration pips and the drawer gauge under the item grid, the withdrawal and deposit only badges, the in and out
-- flow strip and the glyphs of the ledger tapes (the log and the money log keep Blizzard's own lines, in mono), the rank ladder
-- insignia, the permission matrix across all ranks with its amber differences, and the bank tab allowance pips of the guild
-- control window. The guild emblem in the corner keeps its stock art.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char, G, Commerce, Odd = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin,
    FS.GroupSkin, FS.CommerceSkin, FS.OddsEndsSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and G and Commerce and Commerce.Dialog and Odd and Odd.RingKey
    and Char.Box and Char.PaintBox and Char.PinColor and Char.IconOf and G.Square and PanelSkins.RequireExport(
    Theme.SkinPanel and Theme.ApplyMono and Theme.StyleMoney,
    "GuildBank.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit, FS.CharacterSkin, FS.GroupSkin, FS.CommerceSkin or FS.OddsEndsSkin missing")) then return end

local Gb = {}
FS.GuildBankSkin = Gb

local C, Weak, Region, Named, Mono, HoldRegions = G.C, G.Weak, G.Region, G.Named, G.Mono, G.HoldRegions
local Try, Plain, List = Kit.Try, Kit.Plain, Char.List
local function Step(name, fn, ...) return G.Step("guildbank", name, fn, ...) end

local S = { panels = Weak(), slots = Weak(), quality = Weak(), tabs = Weak(), wells = Weak(), pages = Weak(), rows = Weak(),
    sections = Weak(), edits = Weak(), chips = {}, done = {} }
Gb.state = S

-- A stock label in mono with its colour pinned against the stock code.
local function Pin(fs, host, px, color)
    if type(fs) ~= "table" or Kit.TypeOf(fs) ~= "FontString" then return end
    Mono(fs, host, px, color)
    Char.PinColor(fs, color)
end

-- The same for a label whose font the stock code resets with SetFontObject each time its text changes.
local function PinFont(fs, host, px, color)
    if type(fs) ~= "table" or Kit.TypeOf(fs) ~= "FontString" then return end
    Pin(fs, host, px, color)
    Kit.HookFunc(fs, "SetFontObject", function() Kit.RestyleLabel(fs, host, px, color) end)
end

-- A stock label the panel band already says (the guild control title): held at alpha 0, so its place stays for the anchors.
local function HoldText(fs)
    if type(fs) ~= "table" or Kit.TypeOf(fs) ~= "FontString" or type(fs.SetAlpha) ~= "function" then return end
    fs:SetAlpha(0)
    Kit.HookFunc(fs, "SetAlpha", function(self, alpha) if Plain(alpha) ~= 0 then self:SetAlpha(0) end end)
end

local function BoxShown(box, shown)
    box.fill:SetShown(shown)
    for _, t in ipairs(box.edges) do t:SetShown(shown) end
end

-------------------------------------------------------------------------------
-- Item slots (the 14 buttons of each of the 7 columns)
-------------------------------------------------------------------------------

-- The search overlay is not held: the stock code dims the slots that do not match the search with it.
local SLOT_ART = { "NormalTexture", "IconBorder", "IconOverlay", "IconOverlay2", "ItemSlotBackground", "Background" }
local SLOT_GLOW = { "NewItemTexture", "BattlepayItemTexture", "flash", "IconQuestTexture" }

local function SweepSlotArt(button)
    HeldArt.HoldNormal(button)
    for _, f in ipairs(SLOT_ART) do HeldArt.Hold(button[f]) end
    for _, f in ipairs(SLOT_GLOW) do HeldArt.Hold(button[f]) end
end

-- The state of a slot as ItemSlotSkins asks: the quality the stock code handed SetItemButtonQuality, empty without an icon.
local function ReadSlot(button)
    local icon = Char.IconOf(button)
    local texture = icon and Plain(Try(icon.GetTexture, icon))
    return { quality = S.quality[button], empty = texture == nil or texture == "" or texture == 0 }
end

local function SkinSlot(button)
    if type(button) ~= "table" or S.slots[button] or type(button.CreateTexture) ~= "function" then return end
    S.slots[button] = true
    SweepSlotArt(button)
    if type(Theme.AddCut2Texture) == "function" and Theme.SLICE_CUT2_BUTTON_TEXTURE then
        pcall(Theme.AddCut2Texture, button, Theme.SLICE_CUT2_BUTTON_TEXTURE, { 1, 1, 1, 1 }, "BACKGROUND", -8)
    end
    local cut = Theme.SkinCutButton or Theme.SkinButton
    if cut then pcall(cut, button, { count = button.Count }) end
    local icon = Char.IconOf(button)
    if icon and type(icon.SetTexCoord) == "function" then pcall(icon.SetTexCoord, icon, 0.07, 0.93, 0.07, 0.93) end
    local slotSkins = FS.ItemSlotSkins
    if slotSkins and slotSkins.Decorate and slotSkins.Decorate(button, ReadSlot) and slotSkins.SeatIcon and icon then
        slotSkins.SeatIcon(button, icon)
    end
    Kit.HookFunc(button, "SetNormalTexture", function() SweepSlotArt(button) end)
    Kit.HookFunc(button, "SetItemButtonQuality", function(self, quality)
        S.quality[self] = Plain(quality)
        if slotSkins and slotSkins.Refresh then slotSkins.Refresh(self) end
    end)
end

local function ColumnButtons(col)
    local list = {}
    if type(col.Buttons) == "table" then
        for _, b in ipairs(col.Buttons) do list[#list + 1] = b end
    else
        for i = 1, 14 do list[#list + 1] = col["Button" .. i] end
    end
    return list
end

local function SkinSlots(win)
    for c = 1, 7 do
        local col = (type(win.Columns) == "table" and win.Columns[c]) or Region(win, "Column" .. c)
        if type(col) == "table" and not S.wells[col] then
            HeldArt.Hold(col.Background)
            S.wells[col] = Char.Box(col, "BORDER")
            Char.PaintBox(S.wells[col], C.row, 1, C.dim, 1, 1)
            for _, button in ipairs(ColumnButtons(col)) do SkinSlot(button) end
        end
    end
    if not S.done.quality then
        S.done.quality = true
        -- the global the stock grid update calls on each slot, for a client whose buttons have no such method
        Kit.HookFunc(_G, "SetItemButtonQuality", function(button, quality)
            if type(button) == "table" and S.slots[button] then
                S.quality[button] = Plain(quality)
                if FS.ItemSlotSkins and FS.ItemSlotSkins.Refresh then FS.ItemSlotSkins.Refresh(button) end
            end
        end)
    end
end

-------------------------------------------------------------------------------
-- The window, its name chips, its tab rail, its money box, its pages
-------------------------------------------------------------------------------

local WINDOW_ART = { "TabTitleBG", "TabTitleBGLeft", "TabTitleBGRight", "TabLimitBG", "TabLimitBGLeft", "TabLimitBGRight", "Portrait",
    "RedMarbleBG", "BlackBG" }
local FRAME_PIECES = { "BottomLeftOuter", "BottomRightOuter", "TopRightOuter", "TopLeftOuter", "LeftOuter", "RightOuter", "TopOuter",
    "BottomOuter", "BottomLeftInner", "BottomRightInner", "TopRightInner", "TopLeftInner", "LeftInner", "RightInner", "TopInner", "BottomInner" }

-- A ring round a stock name chip (the title of the tab and its withdrawal limit). The stock code shows and hides the chip art
-- together with its label, but SkinPanel hides that art once itself, so the ring follows the label, not the art.
local function Chip(win, key, labelKey, left, right)
    local label, l, r = Region(win, labelKey), Region(win, left), Region(win, right)
    if not (label and l and r) or S.chips[key] then return end
    local ref = win:CreateTexture(nil, "BACKGROUND")
    ref:SetPoint("TOPLEFT", l, "TOPLEFT", 0, 0)
    ref:SetPoint("BOTTOMRIGHT", r, "BOTTOMRIGHT", 0, 0)
    local box = Char.Box(win, "BORDER", ref)
    Char.PaintBox(box, C.ink, 0, C.dim, 1, 1)
    S.chips[key] = box
    local function follow() BoxShown(box, Try(label.IsShown, label) ~= false) end
    for _, m in ipairs({ "Show", "Hide", "SetShown" }) do Kit.HookFunc(label, m, follow) end
    follow()
end

local function SkinTabs(win)
    for i = 1, 8 do
        local tab = (type(win.BankTabs) == "table" and win.BankTabs[i]) or Named("GuildBankTab" .. i)
        if type(tab) == "table" and not S.tabs[tab] then
            S.tabs[tab] = true
            HoldRegions(tab)
            local btn = Region(tab, "Button")
            if btn then
                Odd.RingKey(btn, { holdNormal = true, selected = function() return Try(btn.GetChecked, btn) == true end })
            end
        end
    end
end

local function SkinMoney(win)
    local bg = Region(win, "MoneyFrameBG")
    if bg and not S.done.moneyBox then
        S.done.moneyBox = true
        G.HoldInset(bg)
        Char.PaintBox(Char.Box(win, "OVERLAY", bg), C.ink, 0, C.violet, 1, 1)
        Pin(bg.LimitLabel, bg, 11, C.muted)
        Pin(bg.UnlimitedLabel, bg, 11, C.cyan)
    end
    for _, name in ipairs({ "GuildBankMoneyFrame", "GuildBankWithdrawMoneyFrame", "GuildBankFrameTabCostMoneyFrame" }) do
        Theme.StyleMoney(Named(name))
    end
    local buy = Region(win, "BuyInfo")
    if buy then
        Pin(buy.TabText, buy, 12, C.text)
        Pin(buy.PurchasedText, buy, 11, C.muted)
        Pin(Named("GuildBankFrameTabCost"), buy, 12, C.muted)
    end
end

-- A ring round `around` drawn on `host` (a frame whose children draw above it), `out` units out.
local function Page(host, around, out)
    if type(host) ~= "table" or type(around) ~= "table" or S.pages[host] then return nil end
    local ref = host:CreateTexture(nil, "BACKGROUND")
    ref:SetPoint("TOPLEFT", around, "TOPLEFT", -out, out)
    ref:SetPoint("BOTTOMRIGHT", around, "BOTTOMRIGHT", out, -out)
    local box = Char.Box(host, "BORDER", ref)
    Char.PaintBox(box, C.ink, 1, C.dim, 1, 1)
    S.pages[host] = box
    return box
end

local function SkinPages(win)
    local log = Region(win, "Log")
    local mf = log and Region(log, "MessageFrame")
    if mf then
        Page(log, mf, 8)
        Kit.RestyleLabel(mf, mf, 12, C.text)
    end
    local info = Region(win, "Info")
    local scroll = info and Region(info, "ScrollFrame")
    if scroll then
        Page(info, scroll, 6)
        local edit = Region(scroll, "EditBox") or Named("GuildBankTabInfoEditBox")
        if edit then Kit.RestyleLabel(edit, edit, 12, C.text) end
    end
end

local function SkinBankFrame(win)
    if S.panels[win] then return end
    S.panels[win] = true
    win.fsGuildBankSkin = true
    Theme.SkinPanel(win, { title = "guild bank", fillColor = Theme.COLOR_BG, accent = C.violet })
    G.HoldKeys(win, WINDOW_ART)
    for _, piece in ipairs(FRAME_PIECES) do HeldArt.Hold(Named("GuildBankFrame" .. piece)) end
    Chip(win, "title", "TabTitle", "TabTitleBGLeft", "TabTitleBGRight")
    Chip(win, "limit", "LimitLabel", "TabLimitBGLeft", "TabLimitBGRight")
    Pin(win.TabTitle, win, 12, C.text)
    Pin(win.LimitLabel, win, 11, C.amber)
    Pin(win.ErrorMessage, win, 12, C.muted)
    if PanelSkins.SweepOnShow then PanelSkins.SweepOnShow(win) end
end

-------------------------------------------------------------------------------
-- The tab name and icon pop up (GuildBankPopupFrame, an IconSelectorPopupFrameTemplate)
-------------------------------------------------------------------------------

-- The field skin takes the name box when it qualifies; otherwise the stock backdrop is held and a ring drawn.
local function SkinEdit(box)
    if type(box) ~= "table" or S.edits[box] then return end
    S.edits[box] = true
    Kit.HoldFrame(box.NineSlice or box.Border)
    HoldRegions(box)
    if FS.FieldSkins and FS.FieldSkins.Skin and FS.FieldSkins.Skin(box) then return end
    Char.PaintBox(Char.Box(box, "BACKGROUND"), C.ink, 1, C.violet, 1, 1)
    Kit.RestyleLabel(box, box, 12, C.text)
end

local function SkinPopup(pop)
    if S.panels[pop] then return end
    S.panels[pop] = true
    pop.fsGuildBankPopupSkin = true
    Commerce.Dialog(pop, C.cyan)
    local box = Region(pop, "BorderBox")
    if box then
        HoldRegions(box)
        Pin(box.EditBoxHeaderText, box, 11, C.muted)
        Pin(box.IconSelectionText, box, 11, C.muted)
        SkinEdit(Region(box, "IconSelectorEditBox"))
        local area = Region(box, "SelectedIconArea")
        local btn = area and Region(area, "SelectedIconButton")
        if btn then
            local keep = {}
            if type(btn.Icon) == "table" then keep[btn.Icon] = true end
            HoldRegions(btn, keep)
            Odd.RingKey(btn, { accent = C.cyan })
        end
        local text = area and Region(area, "SelectedIconText")
        if text then
            PinFont(text.SelectedIconHeader, text, 10, C.muted)
            PinFont(text.SelectedIconDescription, text, 10, C.text)
        end
    end
    if PanelSkins.SweepOnShow then PanelSkins.SweepOnShow(pop) end
end

-------------------------------------------------------------------------------
-- The guild control window (GuildControlUI)
-------------------------------------------------------------------------------

local MAX_RANKS, MAX_BANK_TABS = 20, 8

-- One rank row: a card with the name box, the rank label in mono and three square keys that keep their icons.
local function SkinRankRow(row)
    if type(row) ~= "table" or S.rows[row] or type(row.CreateTexture) ~= "function" then return end
    S.rows[row] = Char.Box(row, "BORDER")
    Char.PaintBox(S.rows[row], C.row, 1, C.dim, 1, 1)
    Pin(row.rankLabel, row, 11, C.muted)
    for _, key in ipairs({ "deleteButton", "downButton", "upButton" }) do
        local b = row[key]
        if type(b) == "table" then
            local icon = b.Icon or b.icon
            if type(icon) ~= "table" and type(b.GetName) == "function" and b:GetName() then icon = _G[b:GetName() .. "Icon"] end
            G.Square(b, { icon = type(icon) == "table" and icon or nil, accent = key == "deleteButton" and C.pink or C.violet })
        end
    end
end

local function SweepRankRows()
    for i = 1, MAX_RANKS do
        local row = Named("GuildControlUIRankOrderFrameRank" .. i)
        if not row then break end
        SkinRankRow(row)
    end
end

-- One bank tab row of a rank (made by GuildControlUI_BankTabPermissions_Update): the stock wash held, a card, mono labels.
local function SkinBankRow(row)
    if type(row) ~= "table" or S.rows[row] or type(row.CreateTexture) ~= "function" then return end
    local name = Try(row.GetName, row)
    if type(name) == "string" then HeldArt.Hold(Named(name .. "Bg")) end
    S.rows[row] = Char.Box(row, "BORDER")
    Char.PaintBox(S.rows[row], C.row, 1, C.dim, 1, 1)
    local owned = Region(row, "owned")
    if owned then
        Pin(owned.tabName, owned, 11, C.text)
        for _, key in ipairs({ "viewCB", "depositCB" }) do
            local cb = Region(owned, key)
            if cb then Pin(cb.text, cb, 10, C.muted) end
        end
        local edit = Region(owned, "editBox")
        if edit then
            for _, region in ipairs(List(edit, "GetRegions")) do Pin(region, edit, 10, C.muted) end
        end
    end
    local buy = Region(row, "buy")
    if buy then
        for _, region in ipairs(List(buy, "GetRegions")) do Pin(region, buy, 11, C.text) end
        Theme.StyleMoney(Region(buy, "money"))
    end
end

local function SweepBankRows()
    for i = 1, MAX_BANK_TABS do
        local row = Named("GuildControlBankTab" .. i)
        if not row then break end
        SkinBankRow(row)
    end
end

-- The three sections of the rank settings page (the officer rights, the roster rights, the bank): the stock tinted wash is held and
-- a card drawn over the same rect.
local function SkinSettings(perm)
    if type(perm) ~= "table" or S.done.settings then return end
    S.done.settings = true
    for _, key in ipairs({ "OfficerBg", "RosterBg", "BankBg" }) do
        local bg = Region(perm, key)
        if bg then
            HeldArt.Hold(bg)
            local box = Char.Box(perm, "BORDER", bg)
            Char.PaintBox(box, C.row, 1, C.dim, 1, 1)
            S.sections[bg] = box
        end
    end
    Pin(perm.OfficerPermissions, perm, 12, C.cyan)
    Pin(Named("GuildControlUIRankSettingsFrameBankLabel"), perm, 12, C.cyan)
    for _, child in ipairs(List(perm, "GetChildren")) do
        if Kit.TypeOf(child) == "CheckButton" then Pin(child.text, child, 10, C.text) end
    end
    local gold = Region(perm, "goldBox")
    if gold then
        for _, region in ipairs(List(gold, "GetRegions")) do Pin(region, gold, 10, C.muted) end
    end
end

local function SweepControl()
    local gc = Named("GuildControlUI")
    if not gc then return end
    SweepRankRows()
    SweepBankRows()
    SkinSettings(Region(gc, "rankPermFrame"))
    for _, key in ipairs({ "orderFrame", "bankTabFrame", "rankPermFrame", "discordFrame" }) do
        local page = Region(gc, key)
        if page and PanelSkins.SweepOnShow and not S.done["sweep" .. key] then
            S.done["sweep" .. key] = true
            PanelSkins.SweepOnShow(page)
        end
    end
end

local function SkinControl()
    local gc = Named("GuildControlUI")
    if not gc then return end
    if not S.panels[gc] then
        S.panels[gc] = true
        gc.fsGuildControlSkin = true
        Theme.SkinPanel(gc, { title = "guild control", fillColor = Theme.COLOR_BG, accent = C.violet })
        Kit.HoldFrame(Named("GuildControlUIHbar"))
        HoldText(Named("GuildControlUITitle"))
        if PanelSkins.SweepOnShow then PanelSkins.SweepOnShow(gc) end
        Kit.HookScript(gc, "OnShow", function() Kit.Later(function() Step("control.sweep", SweepControl) end) end)
        for _, name in ipairs({ "GuildControlUI_RankOrder_Update", "GuildControlUI_BankTabPermissions_Update" }) do
            Kit.HookFunc(_G, name, function() Step("control.sweep", SweepControl) end)
        end
    end
    SweepControl()
end

-------------------------------------------------------------------------------
-- Drive
-------------------------------------------------------------------------------

local function BuildBank()
    local win = Named("GuildBankFrame")
    if not win then return end
    Step("bank.frame", SkinBankFrame, win)
    Step("bank.slots", SkinSlots, win)
    Step("bank.tabs", SkinTabs, win)
    Step("bank.money", SkinMoney, win)
    Step("bank.pages", SkinPages, win)
    local pop = Named("GuildBankPopupFrame")
    if pop then Step("bank.popup", SkinPopup, pop) end
    if not S.done.shown then
        S.done.shown = true
        Kit.HookScript(win, "OnShow", function() Kit.Later(function() PanelSkins.DeferCombat(Gb.Build) end) end)
    end
end

local function Build()
    Step("bank", BuildBank)
    Step("control", SkinControl)
end
Gb.Build = Build

PanelSkins.RegisterInspect("GuildBank", { { name = "GuildBankFrame", guard = "fsGuildBankSkin" },
    { name = "GuildBankPopupFrame", guard = "fsGuildBankPopupSkin" }, { name = "GuildControlUI", guard = "fsGuildControlSkin" } })

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
