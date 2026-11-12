-- Forever STUwave: Talents and Spellbook
-- The talent trees and the spellbook (PlayerSpellsFrame, readout debug/tree-PlayerSpellsFrame-2026-11-12.txt) restyled in place,
-- from the approved SPELLS mockup (mockups/character-spells-2026-11-12.html, section 2). The window chrome, the Primary and
-- Secondary tabs, the search box and the Apply Changes button already wear the shared panel and control skins (Panels.lua and
-- the controls sweep); this adds the parts that were still stock:
--
--   * the TalentsFrame: the gold top band, inner frame border, dividers, clouds and particles are held, a one pixel violet frame
--     and dividers stand in; the class art stays;
--   * the three spec headers (round icon with its count, name, small divider): the gold ring is desaturated to cyan, the count
--     box is an amber box, the name is mono;
--   * the Unspent Talents box: our own box and mono texts;
--   * every talent button gets a RING ONLY: its stock border art is desaturated and tinted by state, read from the atlas the
--     stock code set (locked or gray dim, yellow amber, green cyan), and follows it when the stock code swaps the atlas. Nothing
--     else on a talent button is touched, so every click, tooltip, drag and the commit flow stay stock;
--   * the window's minimise and maximise buttons: held art, a plate, a glyph;
--   * the spellbook: parchment page art held with a dark underlay, dark parchment text retinted, category tab frames held.
--
-- Skin only: no SetAttribute, no reparent, no resize of a Blizzard frame, no field written on a talent or spell button, post-hooks
-- only. Talent buttons are met again whenever the tree is rebuilt (spec change, respec); the sweep is idempotent.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and Char.Box and Char.SkinSquare and PanelSkins.RequireExport(
    Theme.ApplyMono and PanelSkins.RetintDarkText,
    "Talents.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit or FS.CharacterSkin missing")) then return end

local Tal = {}
FS.TalentsSkin = Tal

local C = {
    violet = Theme.COLOR_BORDER, cyan = Theme.COLOR_POWER, pink = Theme.COLOR_HEALTH, amber = Theme.COLOR_AMBER,
    muted = Theme.COLOR_MUTED, ink = Theme.COLOR_CTRL_INK, text = Theme.COLOR_CTRL_TEXT or { 0.914, 0.886, 1 },
    dim = Theme.COLOR_CTRL_DIM or { 0.294, 0.165, 0.525 },
}

local function Weak() return setmetatable({}, { __mode = "k" }) end
local S = { done = false, nodes = Weak(), specs = Weak(), books = Weak(), rules = {}, texts = Weak() }
Tal.state = S

local Plain, Try = Kit.Plain, Kit.Try
local List, AtlasOf = Char.List, Char.AtlasOf

local logged = {}
local function Step(name, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok and not logged[name] then
        logged[name] = true
        FS.LogDegradeOnce("talents:" .. name, ("|cffff4488Forever STUwave|r: talents skin step '%s' failed: %s"):format(name, tostring(err)))
    end
    return ok
end

-- A 1 px line anchored over `ref` (a frame or a texture): across it ("h", through its middle) or along it ("v", through its
-- middle), colour `color`. Re-sized on a change of pixel scale.
local function Rule(host, ref, orient, color, alpha)
    local t = host:CreateTexture(nil, "OVERLAY", nil, 5)
    t:SetColorTexture(color[1], color[2], color[3], alpha or 1)
    local rec = { t = t, host = host, ref = ref, orient = orient }
    function rec.apply()
        local u = Kit.U(host, 1)
        t:ClearAllPoints()
        if orient == "h" then
            t:SetPoint("LEFT", ref, "LEFT", 0, 0)
            t:SetPoint("RIGHT", ref, "RIGHT", 0, 0)
            t:SetHeight(u)
        else
            t:SetPoint("TOP", ref, "TOP", 0, 0)
            t:SetPoint("BOTTOM", ref, "BOTTOM", 0, 0)
            t:SetWidth(u)
        end
    end
    S.rules[#S.rules + 1] = rec
    rec.apply()
    return t
end

local function Tint(region, color, desaturate)
    if type(region) ~= "table" then return end
    if desaturate and type(region.SetDesaturated) == "function" then pcall(region.SetDesaturated, region, true) end
    if type(region.SetVertexColor) == "function" then pcall(region.SetVertexColor, region, color[1], color[2], color[3], 1) end
end

-------------------------------------------------------------------------------
-- Talent buttons: a ring only
-------------------------------------------------------------------------------

-- The ring colour of a state, told by the atlas the stock code gave the border; nil for one this does not know (left stock).
local function RingColor(atlas)
    if type(atlas) ~= "string" then return nil end
    atlas = atlas:lower()
    if atlas:find("locked") or atlas:find("gray") or atlas:find("grey") or atlas:find("disabled") then return C.dim end
    if atlas:find("yellow") or atlas:find("gold") or atlas:find("maxed") then return C.amber end
    if atlas:find("green") or atlas:find("learn") then return C.cyan end
    if atlas:find("red") then return C.pink end
    return nil
end

local function PaintNode(btn)
    local border = btn.StateBorder
    local color = RingColor(AtlasOf(border))
    if color then Tint(border, color, true) end
    Tint(btn.StateBorderHover, C.cyan, true)
    Tint(btn.Glow, C.cyan, true)
    Tint(btn.SelectableGlow, C.cyan, true)
end

local NODE_HOOKS = { "UpdateStateBorder", "UpdateVisualState", "UpdateNonStateVisuals", "SetVisualState", "UpdateAll" }

local function SkinNode(btn)
    if type(btn) ~= "table" or S.nodes[btn] or type(btn.StateBorder) ~= "table" then return end
    S.nodes[btn] = true
    if btn.StateBorder.SetAtlas then Kit.HookFunc(btn.StateBorder, "SetAtlas", function() PaintNode(btn) end) end
    for _, m in ipairs(NODE_HOOKS) do Kit.HookFunc(btn, m, function() PaintNode(btn) end) end
    PaintNode(btn)
end

local function SkinNodes(frame)
    local parent = frame.ButtonsParent
    if type(parent) ~= "table" then return end
    for _, child in ipairs(List(parent, "GetChildren")) do SkinNode(child) end
end

-------------------------------------------------------------------------------
-- The talent frame
-------------------------------------------------------------------------------

local FRAME_ART = {
    "Background", "BackgroundBorder", "DividerHorizontalLeft", "DividerHorizontalRight", "DividerVerticalLeft",
    "DividerVerticalRight", "Clouds1", "Clouds2", "AirParticlesClose", "AirParticlesFar",
}

local function SkinFrameArt(frame)
    for _, key in ipairs(FRAME_ART) do HeldArt.Hold(frame[key]) end
    if S.frameRules then return end
    S.frameRules = true
    local border = frame.BackgroundBorder
    if border then
        local box = Char.Box(frame, "OVERLAY", border)
        Char.PaintBox(box, C.ink, 0, C.violet, 1, 1)
    end
    for _, key in ipairs({ "DividerVerticalLeft", "DividerVerticalRight" }) do
        if frame[key] then Rule(frame, frame[key], "v", C.violet, 0.8) end
    end
    for _, key in ipairs({ "DividerHorizontalLeft", "DividerHorizontalRight" }) do
        if frame[key] then Rule(frame, frame[key], "h", C.violet, 0.8) end
    end
end

local function SkinSpecHeader(head)
    if S.specs[head] then return end
    S.specs[head] = true
    HeldArt.Hold(head.TextBackground)
    HeldArt.Hold(head.Divider)
    Tint(head.MainRing, C.cyan, true)
    if head.TextBackground then
        local box = Char.Box(head, "OVERLAY", head.TextBackground)
        Char.PaintBox(box, C.ink, 1, C.amber, 1, 1)
    end
    if head.Divider then Rule(head, head.Divider, "h", C.violet, 0.8) end
    if head.Name then Kit.RestyleLabel(head.Name, head, 15, C.text); Char.PinColor(head.Name, C.text) end
    if head.Text then Kit.RestyleLabel(head.Text, head, 12, C.amber); Char.PinColor(head.Text, C.amber) end
end

local function SkinSpecHeaders(frame)
    for _, child in ipairs(List(frame, "GetChildren")) do
        if type(child) == "table" and child.MainRing and child.TextBackground and child.Name then SkinSpecHeader(child) end
    end
end

local function SkinCurrency(frame)
    local box = frame.ClassCurrencyDisplay
    if type(box) ~= "table" or S.currency then return end
    S.currency = true
    HeldArt.Hold(box.Border)
    if box.Border then
        local b = Char.Box(box, "OVERLAY", box.Border)
        Char.PaintBox(b, C.ink, 1, C.violet, 1, 1)
    end
    if box.UnspentLabel then Kit.RestyleLabel(box.UnspentLabel, box, 12, C.muted); Char.PinColor(box.UnspentLabel, C.muted) end
    local amount = box.CurrentAmountContainer and box.CurrentAmountContainer.CurrencyAmount
    if amount then Kit.RestyleLabel(amount, box, 22, C.amber); Char.PinColor(amount, C.amber) end
end

local function SkinTalents(frame)
    SkinFrameArt(frame)
    SkinSpecHeaders(frame)
    SkinCurrency(frame)
    SkinNodes(frame)
end

-------------------------------------------------------------------------------
-- Minimise and maximise
-------------------------------------------------------------------------------

local function SkinSizeButton(btn, glyphOutline)
    if type(btn) ~= "table" then return end
    local s = Char.SkinSquare(btn, {})
    if not s then return end
    local bw, bh = Kit.SizePx(btn)
    bw, bh = bw or 28, bh or 28
    local gw, gh = 14, glyphOutline and 12 or 2
    local gx, gy = math.floor((bw - gw) / 2), math.floor((bh - gh) / 2)
    local function r(x, y, w, h) return Kit.Rect(btn, gx + x, gy + y, w, h, C.cyan, 1, "OVERLAY", 7) end
    if glyphOutline then
        s.glyph = { r(0, 0, gw, 2), r(0, gh - 2, gw, 2), r(0, 0, 2, gh), r(gw - 2, 0, 2, gh) }
    else
        s.glyph = { r(0, 0, gw, gh) }
    end
    Char.PaintSquare(btn)
end

local function SkinSizeButtons(win)
    local pair = win.MaximizeMinimizeButton
    if type(pair) ~= "table" then return end
    SkinSizeButton(pair.MinimizeButton, false)
    SkinSizeButton(pair.MaximizeButton, true)
end

-------------------------------------------------------------------------------
-- The spellbook
-------------------------------------------------------------------------------

local BOOK_KEEP = { "rotationhelper", "Tab%-Frame" }

local function IsBookArt(atlas)
    if not atlas:find("^spellbook%-") then return false end
    for _, p in ipairs(BOOK_KEEP) do if atlas:find(p) then return false end end
    return true
end

local function HoldBookArt(frame, depth)
    if type(frame) ~= "table" or depth > 7 then return end
    for _, region in ipairs(List(frame, "GetRegions")) do
        local kind = Try(region.GetObjectType, region)
        if kind == "Texture" then
            local atlas = AtlasOf(region)
            if atlas and IsBookArt(atlas) then HeldArt.Hold(region) end
        elseif kind == "FontString" then
            -- the pages were written for parchment: dark text is lifted to the light text colour, state colours pass through
            pcall(PanelSkins.RetintDarkText, region, C.text)
        end
    end
    for _, child in ipairs(List(frame, "GetChildren")) do
        if type(child) == "table" and child.Track == nil then HoldBookArt(child, depth + 1) end
    end
end

local BOOK_REFRESH = { "UpdateDisplay", "Update", "UpdateTabs", "DisplayPage", "SetCategory", "RefreshDisplay" }

local function SkinBook(book)
    if type(book) ~= "table" then return end
    for _, key in ipairs({ "BookBGHalved", "BookBGLeft", "BookBGRight", "BookCornerFlipbook" }) do HeldArt.Hold(book[key]) end
    if not S.books[book] then
        S.books[book] = true
        local under = book:CreateTexture(nil, "BACKGROUND", nil, -6)
        under:SetAllPoints(book)
        under:SetColorTexture(C.ink[1], C.ink[2], C.ink[3], 0.55)
        for _, m in ipairs(BOOK_REFRESH) do Kit.HookFunc(book, m, function() Kit.Later(function() HoldBookArt(book, 0) end) end) end
        Kit.HookScript(book, "OnShow", function() Kit.Later(function() HoldBookArt(book, 0) end) end)
    end
    -- the category tabs keep their STUwave plate; the stock gold square frame behind each icon is held
    local tabs = book.tabSystem
    for _, tab in ipairs(List(tabs, "GetChildren")) do
        for _, key in ipairs({ "SquareBackground", "SquareBackgroundActive", "SquareBackgroundActiveGlow" }) do HeldArt.Hold(tab[key]) end
    end
    HoldBookArt(book, 0)
end

-------------------------------------------------------------------------------
-- Drive
-------------------------------------------------------------------------------

function Tal.Refresh()
    if not S.done then return end
    local win = _G.PlayerSpellsFrame
    if not win then return end
    Step("size", SkinSizeButtons, win)
    if win.TalentsFrame then Step("talents", SkinTalents, win.TalentsFrame) end
    if win.SpellBookFrame then Step("book", SkinBook, win.SpellBookFrame) end
end

local function Relayout()
    for _, rec in ipairs(S.rules) do rec.apply() end
end

local TALENT_REFRESH = { "UpdateTreeInfo", "UpdateInspecting", "RefreshAllData", "ReleaseAllTalentButtons", "UpdateAll", "LoadTalentTree" }

local function Build()
    local win = _G.PlayerSpellsFrame
    if not win or S.done then return end
    S.done = true
    win.fsTalentsSkin = true
    local talents = win.TalentsFrame
    if talents then
        for _, m in ipairs(TALENT_REFRESH) do Kit.HookFunc(talents, m, function() Kit.Later(Tal.Refresh) end) end
        Kit.HookScript(talents, "OnShow", function() Kit.Later(Tal.Refresh) end)
    end
    Kit.HookScript(win, "OnShow", function() Kit.Later(Tal.Refresh) end)
    Kit.OnReseat(function() Relayout(); Tal.Refresh() end)
    Tal.Refresh()
end

local watcher = CreateFrame("Frame")
for _, event in ipairs({ "TRAIT_CONFIG_UPDATED", "TRAIT_TREE_CURRENCY_INFO_UPDATED", "PLAYER_TALENT_UPDATE", "ACTIVE_PLAYER_SPECIALIZATION_CHANGED" }) do
    pcall(watcher.RegisterEvent, watcher, event)
end
watcher:SetScript("OnEvent", function() if S.done then Kit.Later(Tal.Refresh) end end)

PanelSkins.RegisterInspect("Talents", { { name = "PlayerSpellsFrame", guard = "fsTalentsSkin" } })

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
