-- Forever STUwave: Commerce windows
-- The vendor, the bank, the stack split, the colour picker and the prompts with an edit box or a money input, restyled in place
-- from the approved COMMERCE mockup (mockups/commerce-2026-11-12.html). The window chrome, the text buttons, the tabs, the
-- dropdowns, the check boxes and the plain edit boxes already wear the shared panel and control skins (Panels.lua, Popups.lua and
-- the controls sweep); this file adds the parts that were still stock. One section per window below.
--
-- Skin only, as in Character.lua and Talents.lua: no SetScript, no SetAttribute, no reparent, no resize or re-anchor of a
-- Blizzard frame, post-hooks and alpha holds (FS.HeldArt) only, so every click, drag, tooltip and purchase flow stays stock. Names
-- are the real 12.1 tree (Blizzard_UIPanels_Game MerchantFrame.xml, BankFrame.xml, Blizzard_FrameXML StackSplitFrame.xml,
-- Blizzard_ColorPickerFrame, Blizzard_StaticPopup_Game GameDialog.xml, Blizzard_MoneyFrame); each one is feature-detected and a
-- missing frame is skipped silently.
--
-- Left out on purpose, because the mockup shows a computed display and the rule for this pass is "keep the functionality the
-- same as vanilla": the purse gauge, the repair wear strip, the receipt tape, the bank drawer gauges and manifest strip, the
-- depth chart, the totem split poles, the coin rollers, the character count pips and the colour dial.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and Char.Box and Char.SkinSquare and Char.PaintBox and PanelSkins.RequireExport(
    Theme.ApplyMono and Theme.StyleMoney and Theme.AddPanelChrome,
    "Commerce.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit or FS.CharacterSkin missing")) then return end

local ButtonSkins = FS.ButtonSkins
local Com = {}
FS.CommerceSkin = Com

local C = {
    violet = Theme.COLOR_BORDER, cyan = Theme.COLOR_POWER, pink = Theme.COLOR_HEALTH, amber = Theme.COLOR_AMBER,
    muted = Theme.COLOR_MUTED, ink = Theme.COLOR_CTRL_INK, text = Theme.COLOR_CTRL_TEXT or { 0.914, 0.886, 1 },
    dim = Theme.COLOR_CTRL_DIM or { 0.294, 0.165, 0.525 }, row = { 0.059, 0.031, 0.125 },
    gold = Theme.COLOR_GOLD or { 1, 0.824, 0.247 }, silver = { 0.784, 0.816, 0.863 }, copper = { 0.878, 0.565, 0.353 },
}

local function Weak() return setmetatable({}, { __mode = "k" }) end
local S = { cards = Weak(), slots = Weak(), quality = Weak(), pagers = Weak(), done = {} }
Com.state = S

local Plain, Try = Kit.Plain, Kit.Try
local List = Char.List

local logged = {}
local function Step(name, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok and not logged[name] then
        logged[name] = true
        FS.LogDegradeOnce("commerce:" .. name, ("|cffff4488Forever STUwave|r: commerce skin step '%s' failed: %s"):format(name, tostring(err)))
    end
    return ok
end

local function Region(frame, key)
    return type(frame) == "table" and type(frame[key]) == "table" and frame[key] or nil
end

-- Holds every texture region of `frame` (not its sub frames), except those in `keep`.
local function HoldRegions(frame, keep)
    for _, region in ipairs(List(frame, "GetRegions")) do
        if not (keep and keep[region]) then HeldArt.Hold(region) end
    end
end

-- Style a stock label in mono and keep its colour as the stock code sets it (a quality colour, a red state).
local function Mono(fs, host, px, color)
    if type(fs) == "table" then Kit.RestyleLabel(fs, host, px, color or C.text) end
end

-------------------------------------------------------------------------------
-- Shared: an item slot, a small square button with a glyph
-------------------------------------------------------------------------------

local SLOT_ART = { "NormalTexture", "IconBorder", "IconOverlay", "IconOverlay2", "ItemSlotBackground", "Background" }
local SLOT_GLOW = { "NewItemTexture", "BattlepayItemTexture", "flash", "IconQuestTexture", "SearchOverlay" }

local function SweepSlotArt(button)
    HeldArt.HoldNormal(button)
    for _, f in ipairs(SLOT_ART) do HeldArt.Hold(button[f]) end
    for _, f in ipairs(SLOT_GLOW) do HeldArt.Hold(button[f]) end
end

local function IconOf(button)
    return Char.IconOf and Char.IconOf(button) or nil
end

-- The state of a vendor slot, read the way ItemSlotSkins asks: the quality the stock code handed SetItemButtonQuality (kept
-- here, since the button stores none), and empty when there is no icon.
local function ReadVendorSlot(button)
    local icon = IconOf(button)
    local texture = icon and Plain(Try(icon.GetTexture, icon))
    local empty = texture == nil or texture == "" or texture == 0
    return { quality = S.quality[button], empty = empty }
end

-- Skins one vendor item slot in place, the way Character.lua skins an equipment slot: the stock art held, the cut plate and ring
-- of the bags, the shared item slot layer (quality LED, glint, hover, lock), the icon seated and cropped.
local function SkinItemSlot(button, read)
    if type(button) ~= "table" or S.slots[button] then return end
    S.slots[button] = true
    SweepSlotArt(button)
    if type(Theme.AddCut2Texture) == "function" and Theme.SLICE_CUT2_BUTTON_TEXTURE then
        pcall(Theme.AddCut2Texture, button, Theme.SLICE_CUT2_BUTTON_TEXTURE, { 1, 1, 1, 1 }, "BACKGROUND", -8)
    end
    local cut = Theme.SkinCutButton or Theme.SkinButton
    if cut then pcall(cut, button, { count = button.Count }) end
    local icon = IconOf(button)
    if icon and type(icon.SetTexCoord) == "function" then pcall(icon.SetTexCoord, icon, 0.07, 0.93, 0.07, 0.93) end
    local slotSkins = FS.ItemSlotSkins
    if slotSkins and slotSkins.Decorate and slotSkins.Decorate(button, read) and slotSkins.SeatIcon and icon then
        slotSkins.SeatIcon(button, icon)
    end
    Kit.HookFunc(button, "SetNormalTexture", function() SweepSlotArt(button) end)
    Kit.HookFunc(button, "SetItemButtonQuality", function(self, quality)
        S.quality[self] = Plain(quality)
        if slotSkins and slotSkins.Refresh then slotSkins.Refresh(self) end
    end)
end

-- A chevron of cells on a small square button: held art, a ring box, the glyph tinted with the state. dir is "<" or ">".
local function ChevronSquare(btn, dir)
    if type(btn) ~= "table" then return end
    local s = Char.SkinSquare(btn, {})
    if not s then return end
    local bw, bh = Kit.SizePx(btn)
    bw, bh = bw or 32, bh or 32
    local step, rows, thick = 2, 7, 2
    local gw, gh = 3 * step + thick, rows * thick
    local gx, gy = math.floor((bw - gw) / 2), math.floor((bh - gh) / 2)
    s.glyph = {}
    for row = 0, rows - 1 do
        local d = math.abs(row - 3)
        local x = dir == "<" and d * step or (3 - d) * step
        s.glyph[#s.glyph + 1] = Kit.Rect(btn, gx + x, gy + row * thick, thick, thick, C.cyan, 1, "OVERLAY", 7)
    end
    S.pagers[btn] = s
    local function dim()
        local on = Kit.IsEnabled(btn)
        for _, t in ipairs(s.glyph) do t:SetAlpha(on and 1 or 0.35) end
    end
    for _, script in ipairs({ "OnEnable", "OnDisable", "OnShow", "OnEnter", "OnLeave" }) do Kit.HookScript(btn, script, dim) end
    for _, m in ipairs({ "Enable", "Disable", "SetEnabled" }) do Kit.HookFunc(btn, m, dim) end
    Char.PaintSquare(btn)
    dim()
end

-- A square button whose own icon is the picture (the vendor's repair keys): held art, a ring box that follows the state.
local function IconSquare(btn)
    if type(btn) ~= "table" or type(btn.Icon) ~= "table" then return end
    Char.SkinSquare(btn, { icon = btn.Icon })
    Char.PaintSquare(btn)
end

-- A dialog that has chrome of the stock kind only (a DialogBorderTemplate frame, gold edge art): the border frame and its art
-- held, our panel fill, glow and ring drawn over it, and a 3 px LED edge down the left side (cyan asks, pink is money).
S.rules = {}
S.dialogs = Weak()
S.money, S.edits, S.popups = Weak(), Weak(), Weak()

local function Led(frame, color)
    local t = frame:CreateTexture(nil, "OVERLAY", nil, 6)
    t:SetColorTexture(color[1], color[2], color[3], 1)
    local rec = { t = t }
    function rec.apply()
        local u = Kit.U(frame, 1)
        t:ClearAllPoints()
        t:SetPoint("TOPLEFT", frame, "TOPLEFT", 3 * u, -9 * u)
        t:SetPoint("BOTTOMLEFT", frame, "BOTTOMLEFT", 3 * u, 9 * u)
        t:SetWidth(3 * u)
    end
    S.rules[#S.rules + 1] = rec
    rec.apply()
    return t
end

function Com.Dialog(frame, accent)
    if type(frame) ~= "table" or S.dialogs[frame] or type(frame.CreateTexture) ~= "function" then return false end
    S.dialogs[frame] = true
    Kit.HoldFrame(frame.Border)
    HoldRegions(frame)
    Theme.AddPanelChrome(frame, { accent = accent or C.violet, fillColor = Theme.COLOR_BG, glowAlpha = 0.35 })
    Led(frame, accent or C.cyan)
    return true
end

-------------------------------------------------------------------------------
-- The vendor (MerchantFrame)
-------------------------------------------------------------------------------

local MERCHANT_ROWS = 12

local function CardShown(card, shown)
    card.fill:SetShown(shown)
    for _, t in ipairs(card.edges) do t:SetShown(shown) end
end

local function PaintCard(row)
    local card = S.cards[row]
    if not card then return end
    local button = row.ItemButton
    local shown = type(button) ~= "table" or Try(button.IsShown, button) ~= false
    CardShown(card.box, shown)
    if not shown then return end
    local hover = card.state and card.state.hover
    Char.PaintBox(card.box, C.row, 1, hover and C.cyan or C.dim, 1, 1)
end

local function SkinVendorRow(row)
    if type(row) ~= "table" or S.cards[row] then return end
    local button = row.ItemButton
    local name = Try(row.GetName, row)
    HeldArt.Hold(row.SlotTexture)
    if type(name) == "string" then HeldArt.Hold(_G[name .. "NameFrame"]) end
    local card = { box = Char.Box(row, "BORDER") }
    S.cards[row] = card
    if type(button) == "table" then
        SkinItemSlot(button, ReadVendorSlot)
        card.state = Kit.Track(button, function() PaintCard(row) end)
        for _, m in ipairs({ "Show", "Hide", "SetShown" }) do Kit.HookFunc(button, m, function() PaintCard(row) end) end
    end
    Mono(row.Name, row, 11, C.text)
    if type(name) == "string" then Theme.StyleMoney(_G[name .. "MoneyFrame"]) end
    PaintCard(row)
end

local function SkinVendorPage(win)
    for i = 1, MERCHANT_ROWS do SkinVendorRow(_G["MerchantItem" .. i]) end
    local back = _G.MerchantBuyBackItem
    if back and not S.cards[back] then
        S.cards[back] = true
        HeldArt.Hold(back.SlotTexture)
        HeldArt.Hold(_G.MerchantBuyBackItemNameFrame)
        if type(back.ItemButton) == "table" then
            SkinItemSlot(back.ItemButton, ReadVendorSlot)
            HeldArt.Hold(Region(back.ItemButton.UndoFrame, "Arrow"))
        end
        Mono(back.Name, back, 11, C.text)
        Theme.StyleMoney(_G.MerchantBuyBackItemMoneyFrame)
    end
    for i = 1, MERCHANT_ROWS do PaintCard(_G["MerchantItem" .. i]) end
end

-- The two inset wells under the shop (the bought currencies, the money) are art-only frames: held, and a ring box of ours drawn
-- over the same rect.
local function SkinVendorFooter(win)
    for _, name in ipairs({ "MerchantExtraCurrencyInset", "MerchantExtraCurrencyBg", "MerchantMoneyInset", "MerchantMoneyBg" }) do
        Kit.HoldFrame(_G[name])
    end
    if S.done.footer then return end
    S.done.footer = true
    for _, name in ipairs({ "MerchantExtraCurrencyBg", "MerchantMoneyBg" }) do
        local ref = _G[name]
        if ref then Char.PaintBox(Char.Box(win, "OVERLAY", ref), C.ink, 1, C.violet, 1, 1) end
    end
end

local function SkinVendorButtons(win)
    for _, name in ipairs({ "MerchantSellAllJunkButton", "MerchantRepairAllButton", "MerchantRepairItemButton", "MerchantGuildBankRepairButton" }) do
        IconSquare(_G[name])
    end
    for _, spec in ipairs({ { "MerchantPrevPageButton", "<" }, { "MerchantNextPageButton", ">" } }) do
        local btn = _G[spec[1]]
        if btn and not S.pagers[btn] then
            ChevronSquare(btn, spec[2])
            for _, region in ipairs(List(btn, "GetRegions")) do
                if Try(region.GetObjectType, region) == "FontString" then Mono(region, btn, 12, C.muted); Char.PinColor(region, C.muted) end
            end
        end
    end
    Mono(_G.MerchantPageText, win, 12, C.muted)
    Char.PinColor(_G.MerchantPageText, C.muted)
end

function Com.RefreshVendor()
    local win = _G.MerchantFrame
    if not win then return end
    Step("vendor.rows", SkinVendorPage, win)
    Step("vendor.footer", SkinVendorFooter, win)
    Step("vendor.buttons", SkinVendorButtons, win)
    -- the stock page change hides and shows the repair keys; the sweep is idempotent
    if PanelSkins.SweepOnShow and not S.done.sweep then
        S.done.sweep = true
        PanelSkins.SweepOnShow(win)
    end
end

local function BuildVendor()
    local win = _G.MerchantFrame
    if not win or S.done.vendor then return end
    S.done.vendor = true
    win.fsCommerceSkin = true
    Kit.HookFunc(_G, "MerchantFrame_Update", function() Kit.Later(Com.RefreshVendor) end)
    Kit.HookScript(win, "OnShow", function() Kit.Later(Com.RefreshVendor) end)
    Com.RefreshVendor()
end

-------------------------------------------------------------------------------
-- The bank (BankFrame, BankPanel)
-------------------------------------------------------------------------------
-- The slots, the money line and the window chrome are Bags.lua's. This adds what was still stock: the inset art and edge shadows
-- of the panel, the tab rail, the sort key, the money box, the purchase and lock prompts and the clean up confirmation.

C.band = { 0.102, 0.051, 0.173 }

local function PaintBankTab(tab)
    local t = S.bankTabs[tab]
    if not t then return end
    local selected = type(tab.IsSelected) == "function" and Try(tab.IsSelected, tab) == true
    local hover = t.state and t.state.hover
    local enabled = Kit.IsEnabled(tab)
    local edge = (selected and C.pink) or (hover and C.cyan) or (enabled and C.dim) or C.dim
    Char.PaintBox(t.box, selected and C.band or C.ink, 1, edge, 1, selected and 2 or 1)
    local icon = tab.Icon
    if type(icon) == "table" and icon.SetVertexColor then
        local v = (selected or hover) and 1 or (enabled and 0.8 or 0.5)
        pcall(icon.SetVertexColor, icon, v, v, v, 1)
    end
end

S.bankTabs = Weak()

local function SkinBankTab(tab)
    if type(tab) ~= "table" or S.bankTabs[tab] then return end
    S.bankTabs[tab] = { box = Char.Box(tab) }
    local keep = {}
    for _, key in ipairs({ "Icon", "SearchOverlay" }) do if type(tab[key]) == "table" then keep[tab[key]] = true end end
    HeldArt.HoldButton(tab, keep)
    HeldArt.Hold(tab.Border)
    HeldArt.Hold(tab.SelectedTexture)
    HeldArt.Hold(tab.Background)
    S.bankTabs[tab].state = Kit.Track(tab, PaintBankTab)
    for _, m in ipairs({ "Init", "RefreshVisuals", "OnNewBankTabSelected", "SetEnabledState" }) do
        Kit.HookFunc(tab, m, function() PaintBankTab(tab) end)
    end
    PaintBankTab(tab)
end

local function SkinBankTabs(panel)
    local pool = panel.bankTabPool
    if type(pool) == "table" and type(pool.EnumerateActive) == "function" then
        pcall(function() for tab in pool:EnumerateActive() do SkinBankTab(tab) end end)
    end
    SkinBankTab(panel.PurchaseTab)
    for tab in pairs(S.bankTabs) do PaintBankTab(tab) end
end

-- The sort key: stock icon art held, a ring box, three bars and an arrow drawn over it.
local function SkinSortKey(btn)
    if type(btn) ~= "table" or S.pagers[btn] then return end
    local s = Char.SkinSquare(btn, {})
    if not s then return end
    S.pagers[btn] = s
    local bw, bh = Kit.SizePx(btn)
    bw, bh = bw or 34, bh or 31
    local x0, y0 = math.floor((bw - 18) / 2), math.floor((bh - 12) / 2)
    local function r(x, y, w, h) return Kit.Rect(btn, x0 + x, y0 + y, w, h, C.cyan, 1, "OVERLAY", 7) end
    s.glyph = { r(0, 0, 10, 2), r(0, 5, 7, 2), r(0, 10, 4, 2), r(13, 0, 2, 10), r(11, 8, 2, 2), r(15, 8, 2, 2) }
    Char.PaintSquare(btn)
end

local function SkinPrompt(prompt)
    if type(prompt) ~= "table" or S.done[prompt] then return end
    S.done[prompt] = true
    HoldRegions(prompt, prompt.Background and { [prompt.Background] = true } or nil)
    Char.PaintBox(Char.Box(prompt, "OVERLAY"), C.ink, 0, C.violet, 1, 1)
    Mono(prompt.Title, prompt, 22, C.cyan)
    Char.PinColor(prompt.Title, C.cyan)
    Mono(prompt.PromptText, prompt, 14, C.text)
    Char.PinColor(prompt.PromptText, C.text)
    local cost = prompt.TabCostFrame
    if type(cost) == "table" then
        Mono(cost.TabCost, cost, 13, C.muted)
        Char.PinColor(cost.TabCost, C.muted)
        Theme.StyleMoney(cost.MoneyDisplay)
    end
end

local function SkinBankMoney(panel)
    local money = panel.MoneyFrame
    if type(money) ~= "table" or S.done.bankMoney then return end
    S.done.bankMoney = true
    if type(money.Border) == "table" then
        Kit.HoldFrame(money.Border)
        Char.PaintBox(Char.Box(money, "OVERLAY", money.Border), C.ink, 1, C.violet, 1, 1)
    end
end

local function SkinBankPanel(panel)
    Kit.HoldFrame(panel.NineSlice)
    Kit.HoldFrame(panel.EdgeShadows)
    Mono(Region(panel, "Header") and panel.Header.Text, panel, 15, C.text)
    Step("bank.money", SkinBankMoney, panel)
    Step("bank.tabs", SkinBankTabs, panel)
    Step("bank.sort", SkinSortKey, panel.AutoSortButton)
    SkinPrompt(panel.PurchasePrompt)
    SkinPrompt(panel.LockPrompt)
    if PanelSkins.SweepOnShow and not S.done.bankSweep then
        S.done.bankSweep = true
        PanelSkins.SweepOnShow(panel)
    end
end

function Com.RefreshBank()
    local win = _G.BankFrame
    if not win then return end
    HeldArt.Hold(win.Background)
    Mono(_G.BankFrameTitleText, win, 14, C.muted)
    local panel = _G.BankPanel
    if panel then Step("bank.panel", SkinBankPanel, panel) end
end

-- The clean up confirmation (BankCleanUpConfirmationPopup): a dialog with a stock border frame, a text, a check box and two
-- buttons; its buttons and check box come from the controls sweep.
local function SkinCleanUpPopup()
    local pop = _G.BankCleanUpConfirmationPopup
    if type(pop) ~= "table" or S.done.cleanup then return end
    S.done.cleanup = true
    Com.Dialog(pop, C.cyan)
    Mono(pop.Text, pop, 14, C.text)
    Char.PinColor(pop.Text, C.text)
    local box = pop.HidePopupCheckbox
    if type(box) == "table" then Mono(box.Label, box, 12, C.muted); Char.PinColor(box.Label, C.muted) end
    if PanelSkins.SweepOnShow then PanelSkins.SweepOnShow(pop) end
end

local function BuildBank()
    local win = _G.BankFrame
    if not win or S.done.bank then return end
    S.done.bank = true
    win.fsCommerceBankSkin = true
    local panel = _G.BankPanel
    if panel then
        for _, m in ipairs({ "RefreshBankTabs", "RefreshBankPanel", "SelectTab", "OnNewBankTabSelected", "SetBankType" }) do
            Kit.HookFunc(panel, m, function() Kit.Later(Com.RefreshBank) end)
        end
        Kit.HookScript(panel, "OnShow", function() Kit.Later(Com.RefreshBank) end)
    end
    Kit.HookScript(win, "OnShow", function() Kit.Later(Com.RefreshBank) end)
    Com.RefreshBank()
    Step("bank.cleanup", SkinCleanUpPopup)
end

-------------------------------------------------------------------------------
-- Shared: a money input (gold, silver, copper boxes) and a plain edit box
-------------------------------------------------------------------------------

local COIN_KEYS = { { "gold", "gold" }, { "silver", "silver" }, { "copper", "copper" } }

-- Restyles one MoneyInputFrameTemplate in place: the stock box art is held, a ring box goes round each part and the text takes the
-- coin colour. The coin icon and label stay where the stock code puts them; no script is replaced.
function Com.SkinMoneyInput(frame)
    if type(frame) ~= "table" or S.money[frame] then return false end
    S.money[frame] = true
    for _, pair in ipairs(COIN_KEYS) do
        local box = Region(frame, pair[1])
        if box then
            for _, key in ipairs({ "Left", "Middle", "Right" }) do HeldArt.Hold(box[key]) end
            local name = type(box.GetName) == "function" and box:GetName()
            if name then HeldArt.Hold(_G[name .. "Left"]); HeldArt.Hold(_G[name .. "Middle"]); HeldArt.Hold(_G[name .. "Right"]) end
            local color = C[pair[2]] or C.text
            Char.PaintBox(Char.Box(box, "BACKGROUND"), C.ink, 1, color, 1, 1)
            if type(box.SetFont) == "function" then Kit.RestyleLabel(box, box, 12, color) end
            Char.PinColor(box, color)
        end
    end
    return true
end

-- The StaticPopup edit box: the stock backdrop is held and the shared field skin takes over when the box qualifies; otherwise a ring box.
local function SkinPopupEdit(box)
    if type(box) ~= "table" or S.edits[box] then return end
    S.edits[box] = true
    Kit.HoldFrame(box.NineSlice or box.Border)
    for _, key in ipairs({ "Left", "Middle", "Right" }) do HeldArt.Hold(box[key]) end
    if FS.FieldSkins and FS.FieldSkins.Skin and FS.FieldSkins.Skin(box) then return end
    Char.PaintBox(Char.Box(box, "BACKGROUND"), C.ink, 1, C.violet, 1, 1)
    Kit.RestyleLabel(box, box, 12, C.text)
end

local function SkinPopup(pop)
    if type(pop) ~= "table" then return end
    SkinPopupEdit(Region(pop, "EditBox") or Region(pop, "editBox"))
    local mif = Region(pop, "MoneyInputFrame") or Region(pop, "moneyInputFrame")
    if mif then Com.SkinMoneyInput(mif) end
end

local function BuildPopups()
    for i = 1, 4 do
        local pop = _G["StaticPopup" .. i]
        if type(pop) == "table" and not S.popups[pop] then
            S.popups[pop] = true
            Kit.HookScript(pop, "OnShow", function() Kit.Later(function() Step("popup", SkinPopup, pop) end) end)
            Step("popup", SkinPopup, pop)
        end
    end
end

-------------------------------------------------------------------------------
-- Stack split
-------------------------------------------------------------------------------

local function BuildStackSplit()
    local win = _G.StackSplitFrame
    if type(win) ~= "table" or S.done.split then return end
    S.done.split = true
    win.fsCommerceSplitSkin = true
    HeldArt.Hold(win.SingleItemSplitBackground)
    HeldArt.Hold(win.MultiItemSplitBackground)
    HoldRegions(win)
    Com.Dialog(win, C.cyan)
    Mono(win.StackSplitText, win, 14, C.text)
    Mono(win.StackItemCountText, win, 11, C.muted)
    if win.LeftButton then ChevronSquare(win.LeftButton, "<") end
    if win.RightButton then ChevronSquare(win.RightButton, ">") end
    if ButtonSkins and ButtonSkins and ButtonSkins.SkinTextButton then
        if win.OkayButton then ButtonSkins.SkinTextButton(win.OkayButton, { accent = "cyan" }) end
        if win.CancelButton then ButtonSkins.SkinTextButton(win.CancelButton) end
    end
end

-------------------------------------------------------------------------------
-- Colour picker
-------------------------------------------------------------------------------

local function BuildColorPicker()
    local win = _G.ColorPickerFrame
    if type(win) ~= "table" or S.done.color then return end
    S.done.color = true
    win.fsCommerceColorSkin = true
    HeldArt.Hold(win.Border)
    Kit.HoldFrame(win.Border)
    HoldRegions(win)
    local content = Region(win, "Content")
    Com.Dialog(win, C.violet)
    if win.Header then
        HoldRegions(win.Header)
        Mono(win.Header.Text, win, 13, C.text)
    end
    if win.DragBar then HoldRegions(win.DragBar) end
    if content then
        for _, key in ipairs({ "ColorSwatchCurrent", "ColorSwatchOriginal" }) do
            local sw = content[key]
            if type(sw) == "table" and type(sw.CreateTexture) == "function" then
                Char.PaintBox(Char.Box(sw, "OVERLAY"), { 0, 0, 0, 0 }, 1, C.cyan, 1, 1)
            end
        end
        local hex = content.HexBox
        if hex then
            HoldRegions(hex)
            if FS.FieldSkins and FS.FieldSkins.Skin then FS.FieldSkins.Skin(hex.Hex or hex) end
            Mono(hex.Hash, hex, 12, C.muted)
        end
    end
    local foot = Region(win, "Footer")
    if foot and ButtonSkins and ButtonSkins.SkinTextButton then
        if foot.OkayButton then ButtonSkins.SkinTextButton(foot.OkayButton, { accent = "cyan" }) end
        if foot.CancelButton then ButtonSkins.SkinTextButton(foot.CancelButton) end
    end
    local op = _G.OpacityFrame
    if type(op) == "table" then Com.Dialog(op, C.violet) end
end

-------------------------------------------------------------------------------
-- Drive
-------------------------------------------------------------------------------

local function Relayout()
    for _, rec in ipairs(S.rules) do rec.apply() end
end

local function Build()
    Step("vendor", BuildVendor)
    Step("bank", BuildBank)
    Step("popups", BuildPopups)
    Step("split", BuildStackSplit)
    Step("color", BuildColorPicker)
    if not S.done.reseat then
        S.done.reseat = true
        Kit.OnReseat(Relayout)
    end
end

PanelSkins.RegisterInspect("Commerce", { { name = "MerchantFrame", guard = "fsCommerceSkin" },
    { name = "BankFrame", guard = "fsCommerceBankSkin" },
    { name = "StackSplitFrame", guard = "fsCommerceSplitSkin" }, { name = "ColorPickerFrame", guard = "fsCommerceColorSkin" } })

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
