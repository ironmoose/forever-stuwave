#!/usr/bin/env python3
"""Runs the real Modules/Skins/Collections.lua (and GroupKit.lua) headless against a mock collections journal (tools/charskin_support.py).

Pinned: the mount list rows are ink cards (the stock row art held, the name in mono and its colour kept to the stock collected or
not state through every SetFontObject the stock code writes, an LED edge that follows the summoned and cannot use here states), the
journal insets are held and given ring wells, the count chips and progress bars wear the chip look, the model display and info block
lose their stock art, the summon spell key is a ring key that keeps its cover; the pet rows are cards with a dead and summoned LED
and the pet card loses its stock art; the toy slots and heirloom slots lose the stock slot frames and gain a ring box with a ready or
cooling LED, the pools of heirlooms are caught as they are made; the paging keys are cut keys. No script or attribute is written on a
Blizzard widget, a client without a journal degrades quietly and a second build adds nothing. Run
`python3 tools/collectionsskin-harness.py [--png debug/collections]`. The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring = BLZ.blz, BLZ.tex, BLZ.fstring
local build = BuildBlizzard

-- The level texts are keyed `lvl` here: the mock engine keeps a frame's level in `.level`, the real key (`level`) would collide with it.
-- the stock fonts: SetFontObject resets the face and the colour (GameFontDisable is the grey of an uncollected row)
local function stock(fs)
    fs.SetFontObject = function(self, o)
        self.fontPath = "stock.ttf"
        self.textColor = (o == "GameFontDisable") and { 0.5, 0.5, 0.5, 1 } or { 1, 0.82, 0, 1 }
    end
    return fs
end
local function vtex(parent, layer)
    local t = tex(parent, nil, layer)
    t.GetVertexColor = function(self) local v = self.vertex or { 1, 1, 1, 1 }; return v[1], v[2], v[3], v[4] end
    return t
end
local function at(fs, rel, point, x, y)
    fs.points[1] = { point = point, rel = rel, relPoint = point, x = x or 0, y = y or 0 }
    return fs
end
local function inset(parent, w, h, point, x, y)
    local f = blz("Frame", nil, parent, w, h, point, x, y)
    f.NineSlice = blz("Frame", nil, f, w, h)
    f.Bg = tex(f, nil, "BACKGROUND")
    tex(f, nil, "BORDER")
    return f
end
local function chip(parent, w, h, x, y, label, count)
    local f = inset(parent, w, h, "TOPLEFT", x, y)
    f.Count = at(stock(fstring(f, nil, count, 11, { 1, 1, 1, 1 })), f, "RIGHT", -10)
    f.Count.justify = "RIGHT"
    f.Label = at(stock(fstring(f, nil, label, 11)), f, "LEFT", 10)
    return f
end
local function scrollBox(parent, w, h, x, y, init)
    local box = blz("Frame", nil, parent, w, h, "TOPLEFT", x, y)
    box.rows, box.data = {}, {}
    box.ForEachFrame = function(self, fn) for _, r in ipairs(self.rows) do fn(r) end end
    box.Update = function(self) for i, r in ipairs(self.rows) do init(r, self.data[i]) end end
    box.FullUpdate = function(self) self:Update() end
    box.SetDataProvider = function(self) self:Update() end
    return box
end
local function progressBar(parent, w, h, x, y, text)
    local bar = blz("StatusBar", nil, parent, w, h, "TOP", x, y)
    tex(bar, nil, "BACKGROUND").color = { 0, 0, 0, 1 }
    bar.border = tex(bar, nil, "OVERLAY")
    bar.text = at(stock(fstring(bar, nil, text, 11, { 1, 1, 1, 1 })), bar, "CENTER")
    bar.text.justify = "CENTER"
    bar.SetStatusBarTexture = function(self, p) self.barPath = p end
    bar.SetStatusBarColor = function(self, r, g, b, a) self.barColor = { r, g, b, a or 1 } end
    return bar
end
local function paging(parent, x, y, page)
    local p = blz("Frame", nil, parent, 160, 32, "BOTTOM", x, y)
    for _, spec in ipairs({ { "PrevPageButton", "LEFT", 0 }, { "NextPageButton", "RIGHT", 0 } }) do
        local b = blz("Button", nil, p, 32, 32, spec[2], spec[3], 0)
        b:SetNormalTexture("Interface\\Buttons\\UI-SpellbookIcon-PrevPage-Up")
        b.highlightTex = tex(b, nil, "HIGHLIGHT")
        b.scripts.OnClick = function() end
        p[spec[1]] = b
    end
    p.PageText = at(stock(fstring(p, nil, page, 12, { 1, 1, 1, 1 })), p, "CENTER")
    p.PageText.justify = "CENTER"
    return p
end

-- a CollectionsSpellButton: the toy and heirloom slot
local function spellButton(parent, id, x, y, name)
    local b = blz("CheckButton", nil, parent, 50, 50, "TOPLEFT", x, y)
    b.id = id
    b.iconTexture = tex(b, nil, "BACKGROUND"); b.iconTexture.path = "Interface\\Icons\\inv_misc_toy"
    b.iconTextureUncollected = tex(b, nil, "BACKGROUND"); b.iconTextureUncollected.alpha = 0.18
    b.slotFrameUncollectedInnerGlow = tex(b, nil, "BORDER")
    b.slotFrameCollected = tex(b, nil, "ARTWORK")
    b.slotFrameUncollected = tex(b, nil, "ARTWORK")
    b.newGlow = tex(b, nil, "OVERLAY"); b.newGlow.shown = false
    b.new = stock(fstring(b, nil, "NEW", 11, { 1, 1, 1, 1 })); b.new.shown = false
    b.name = at(stock(fstring(b, nil, name, 12)), b, "LEFT", 58)
    b.cooldown = blz("Cooldown", nil, b, 50, 50, "TOPLEFT", 0, 0)
    b.cooldown.shown = false
    b.cooldownWrapper = blz("Frame", nil, b, 50, 50, "TOPLEFT", 0, 0)
    b.cooldownWrapper.slotFavorite = tex(b.cooldownWrapper, nil, "OVERLAY")
    b.HighlightTexture = tex(b, nil, "HIGHLIGHT"); b.highlightTex = b.HighlightTexture
    b.scripts.OnClick = function() end
    b.scripts.OnEnter = function() end
    return b
end
local function spellInit(b, d)
    b.iconTexture:SetShown(d.collected)
    b.iconTextureUncollected:SetShown(not d.collected)
    b.slotFrameCollected:SetShown(d.collected)
    b.slotFrameUncollected:SetShown(not d.collected)
    b.slotFrameUncollectedInnerGlow:SetShown(not d.collected)
    if d.collected then b.name:SetTextColor(1, 0.82, 0, 1) else b.name:SetTextColor(0.33, 0.27, 0.20, 1) end
    b.cooldown:SetShown(d.cooling and true or false)
    b.name:SetText(d.name)
end

-------------------------------------------------------------------------------
-- Mounts
-------------------------------------------------------------------------------
MOUNTS = {
    { name = "Swift Timber Wolf", collected = true, usable = true, selected = true, favorite = true },
    { name = "Great Brown Kodo", collected = true, usable = true, mounted = true, favorite = true },
    { name = "Swift Green Windrider", collected = true, usable = false },
    { name = "Black Wolf", collected = false },
}
local function mountInit(b, d)
    b.DragButton.ActiveTexture:SetShown(d.mounted and true or false)
    b.selectedTexture:SetShown(d.selected and true or false)
    b.favorite:SetShown(d.favorite and true or false)
    b.background:SetVertexColor(1, 1, 1, 1)
    if d.collected then
        b.name:SetFontObject("GameFontNormal")
        if not d.usable then b.background:SetVertexColor(1, 0, 0, 1) end
    else
        b.name:SetFontObject("GameFontDisable")
    end
    b.name:SetText(d.name)
end

local function buildMounts(journal)
    local mj = blz("Frame", "MountJournal", journal, 700, 540, "TOPLEFT", 0, 0)
    mj.LeftInset = inset(mj, 260, 330, "TOPLEFT", 4, -60)
    mj.RightInset = inset(mj, 426, 330, "TOPLEFT", 270, -60)
    mj.BottomLeftInset = inset(mj, 260, 90, "TOPLEFT", 4, -400)
    mj.MountCount = chip(mj, 130, 20, 70, -35, "Mounts:", "11 / 24")
    mj.ScrollBox = scrollBox(mj, 250, 320, 8, -66, mountInit)
    mj.ScrollBox.data = MOUNTS
    for i, d in ipairs(MOUNTS) do
        local b = blz("Button", nil, mj.ScrollBox, 246, 46, "TOPLEFT", 0, -(i - 1) * 48)
        b.background = vtex(b, "BACKGROUND")
        b.icon = tex(b, nil, "ARTWORK"); b.icon.w, b.icon.h = 38, 38
        b.icon.points[1] = { point = "LEFT", rel = b, relPoint = "LEFT", x = 4, y = 0 }
        b.icon.path = "Interface\\Icons\\ability_mount_" .. i
        b.iconBorder = tex(b, nil, "OVERLAY"); b.iconBorder.shown = false
        b.factionIcon = tex(b, nil, "OVERLAY"); b.factionIcon.shown = false
        b.name = at(stock(fstring(b, nil, d.name, 12)), b, "LEFT", 50, 6)
        b.SteadyFlightLabel = at(stock(fstring(b, nil, "", 10, { 0.5, 0.5, 0.5, 1 })), b, "LEFT", 50, -10)
        b.favorite = tex(b, nil, "OVERLAY"); b.favorite.w, b.favorite.h = 16, 16
        b.favorite.points[1] = { point = "RIGHT", rel = b, relPoint = "RIGHT", x = -8, y = 0 }
        b.selectedTexture = tex(b, nil, "ARTWORK")
        b.new = stock(fstring(b, nil, "NEW", 10, { 1, 1, 1, 1 })); b.new.shown = false
        b.newGlow = tex(b, nil, "OVERLAY"); b.newGlow.shown = false
        b.DragButton = blz("Button", nil, b, 38, 38, "LEFT", 4, 0)
        b.DragButton.ActiveTexture = tex(b.DragButton, nil, "OVERLAY")
        b.DragButton.scripts.OnDragStart = function() end
        b.scripts.OnClick = function() end
        b.scripts.OnEnter = function() end
        mj.ScrollBox.rows[i] = b
    end
    mj.ScrollBox:Update()

    local d = blz("Frame", nil, mj, 420, 324, "TOPLEFT", 273, -63)
    mj.MountDisplay = d
    d.YesMountsTex = tex(d, nil, "BACKGROUND")
    d.NoMountsTex = tex(d, nil, "BACKGROUND"); d.NoMountsTex.shown = false
    d.NoMounts = at(stock(fstring(d, nil, "No mounts", 14, { 1, 1, 1, 1 })), d, "CENTER"); d.NoMounts.shown = false
    d.ShadowOverlay = blz("Frame", nil, d, 420, 324, "TOPLEFT", 0, 0)
    tex(d.ShadowOverlay, nil, "OVERLAY")
    d.ModelScene = blz("Frame", nil, d, 420, 260, "TOPLEFT", 0, -40)
    d.ModelScene.ControlFrame = blz("Frame", nil, d.ModelScene, 100, 30, "BOTTOM", 0, 6)
    local info = blz("Button", nil, d, 400, 60, "TOPLEFT", 10, -6)
    d.InfoButton = info
    info.Icon = tex(info, nil, "ARTWORK"); info.Icon.w, info.Icon.h = 40, 40
    info.Icon.path = "Interface\\Icons\\ability_mount_1"
    info.Name = at(stock(fstring(info, nil, "Swift Timber Wolf", 16, { 1, 1, 1, 1 })), info, "TOPLEFT", 50, 0)
    info.Source = at(stock(fstring(info, nil, "Vendor: Mulgore", 12, { 1, 1, 1, 1 })), info, "TOPLEFT", 50, -22)
    info.Lore = at(stock(fstring(info, nil, "A wolf, swift and timbered.", 12)), info, "TOPLEFT", 0, -64)
    info.New = stock(fstring(info, nil, "NEW", 11, { 1, 1, 1, 1 })); info.New.shown = false
    info.NewGlow = tex(info, nil, "OVERLAY"); info.NewGlow.shown = false

    -- the random favourite key (UIPanelSpellButtonFrameTemplate)
    local sf = blz("Frame", nil, mj, 206, 33, "TOPRIGHT", -8, -25)
    mj.SummonRandomFavoriteSpellFrame = sf
    sf.Label = at(stock(fstring(sf, nil, "Summon Random Favorite Mount", 11, { 1, 1, 1, 1 })), sf, "RIGHT", -40)
    sf.Label.justify = "RIGHT"
    local sb = blz("Button", nil, sf, 33, 33, "RIGHT", 0, 0)
    sf.Button = sb
    sb.Icon = tex(sb, nil, "ARTWORK"); sb.Icon.path = "Interface\\Icons\\ability_mount_1"
    sb.BlackCover = tex(sb, nil, "OVERLAY"); sb.BlackCover.shown = false
    sb.Border = tex(sb, nil, "OVERLAY")
    sb.LockIcon = tex(sb, nil, "OVERLAY"); sb.LockIcon.shown = false
    sb.highlightTex = tex(sb, nil, "HIGHLIGHT")
    sb.Cooldown = blz("Cooldown", nil, sb, 33, 33, "TOPLEFT", 0, 0)
    sb.scripts.OnClick = function() end
    sb.scripts.OnEnter = function() end
    return mj
end

-------------------------------------------------------------------------------
-- Pets
-------------------------------------------------------------------------------
PETS = {
    { name = "Mulgore Hatchling", sub = "Companion", selected = true, summoned = true },
    { name = "Prairie Dog", sub = "Companion" },
    { name = "Lost Whelpling", sub = "Companion", dead = true },
}
local function petInit(b, d)
    b.dragButton.ActiveTexture:SetShown(d.summoned and true or false)
    b.isDead:SetShown(d.dead and true or false)
    b.selectedTexture:SetShown(d.selected and true or false)
    b.name:SetFontObject("GameFontNormal")
    b.name:SetText(d.name)
    b.subName:SetFontObject("GameFontNormal")
    b.subName:SetText(d.sub)
end

local function buildPets(journal)
    local pj = blz("Frame", "PetJournal", journal, 700, 540, "TOPLEFT", 0, 0)
    pj.shown = false
    pj.PetCount = chip(pj, 130, 20, 70, -35, "Pets:", "3 / 9")
    pj.LeftInset = inset(pj, 260, 380, "TOPLEFT", 4, -60)
    pj.RightInset = inset(pj, 426, 440, "TOPLEFT", 270, -60)
    pj.ScrollBox = scrollBox(pj, 250, 370, 8, -66, petInit)
    pj.ScrollBox.data = PETS
    for i, d in ipairs(PETS) do
        local b = blz("Button", nil, pj.ScrollBox, 246, 46, "TOPLEFT", 0, -(i - 1) * 48)
        b.background = vtex(b, "BACKGROUND")
        b.icon = tex(b, nil, "ARTWORK"); b.icon.w, b.icon.h = 38, 38
        b.icon.points[1] = { point = "LEFT", rel = b, relPoint = "LEFT", x = 4, y = 0 }
        b.icon.path = "Interface\\Icons\\ability_pet_" .. i
        b.petTypeIcon = tex(b, nil, "ARTWORK"); b.petTypeIcon.w, b.petTypeIcon.h = 16, 16
        b.iconBorder = tex(b, nil, "OVERLAY"); b.iconBorder.shown = false
        b.name = at(stock(fstring(b, nil, d.name, 12)), b, "LEFT", 50, 6)
        b.subName = at(stock(fstring(b, nil, d.sub, 10)), b, "LEFT", 50, -10)
        b.isDead = tex(b, nil, "OVERLAY"); b.isDead.shown = false
        b.selectedTexture = tex(b, nil, "ARTWORK")
        b.new = stock(fstring(b, nil, "NEW", 10, { 1, 1, 1, 1 })); b.new.shown = false
        b.newGlow = tex(b, nil, "OVERLAY"); b.newGlow.shown = false
        local dg = blz("Button", nil, b, 38, 38, "LEFT", 4, 0)
        b.dragButton = dg
        dg.ActiveTexture = tex(dg, nil, "OVERLAY")
        dg.levelBG = tex(dg, nil, "OVERLAY"); dg.levelBG.w, dg.levelBG.h = 16, 16
        dg.lvl = at(stock(fstring(dg, nil, "12", 10)), dg, "BOTTOMRIGHT")
        dg.favorite = tex(dg, nil, "OVERLAY"); dg.favorite.w, dg.favorite.h = 14, 14
        b.scripts.OnClick = function() end
        b.scripts.OnEnter = function() end
        pj.ScrollBox.rows[i] = b
    end
    pj.ScrollBox:Update()

    local pc = blz("Frame", nil, pj, 420, 430, "TOPLEFT", 273, -63)
    pj.PetCard = pc
    for i = 1, 3 do pc["AbilitiesBG" .. i] = tex(pc, nil, "BACKGROUND") end
    pc.shadows = tex(pc, nil, "BACKGROUND")
    pc.CannotBattleText = stock(fstring(pc, nil, "Cannot battle", 12))
    local pi = blz("Button", nil, pc, 400, 60, "TOPLEFT", 10, -6)
    pc.PetInfo = pi
    pi.icon = tex(pi, nil, "ARTWORK"); pi.icon.w, pi.icon.h = 40, 40
    pi.icon.path = "Interface\\Icons\\ability_pet_1"
    pi.qualityBorder = tex(pi, nil, "OVERLAY")
    pi.name = at(stock(fstring(pi, nil, "Mulgore Hatchling", 14)), pi, "TOPLEFT", 50, 0)
    pi.subName = at(stock(fstring(pi, nil, "Companion", 11)), pi, "TOPLEFT", 50, -20)
    pi.levelBG = tex(pi, nil, "OVERLAY"); pi.levelBG.w, pi.levelBG.h = 16, 16
    pi.lvl = at(stock(fstring(pi, nil, "12", 10)), pi, "BOTTOMRIGHT")
    pi.favorite = tex(pi, nil, "OVERLAY")
    pi.isDead = tex(pi, nil, "OVERLAY"); pi.isDead.shown = false
    pi.new = stock(fstring(pi, nil, "NEW", 10, { 1, 1, 1, 1 })); pi.new.shown = false
    pi.newGlow = tex(pi, nil, "OVERLAY"); pi.newGlow.shown = false
    pc.TypeInfo = blz("Frame", nil, pc, 100, 20, "TOPRIGHT", -10, -6)
    pc.TypeInfo.typeIcon = tex(pc.TypeInfo, nil, "ARTWORK")
    pc.TypeInfo.type = at(stock(fstring(pc.TypeInfo, nil, "Beast", 11)), pc.TypeInfo, "RIGHT")
    for _, spec in ipairs({ { "HealthFrame", "health" }, { "PowerFrame", "power" }, { "SpeedFrame", "speed" }, { "QualityFrame", "quality" } }) do
        local f = blz("Frame", nil, pc, 100, 24, "TOPLEFT", 10, -80)
        f[spec[2]] = at(stock(fstring(f, nil, "100", 11, { 1, 1, 1, 1 })), f, "LEFT")
        pc[spec[1]] = f
    end
    return pj
end

-------------------------------------------------------------------------------
-- Toys
-------------------------------------------------------------------------------
TOYS = {
    { name = "Foam Sword Rack", collected = true },
    { name = "Whistle of Distant Drums", collected = true, cooling = true },
    { name = "Tiny Totem", collected = false },
    { name = "Ancestral Rattle", collected = true },
}
local function buildToys(journal)
    local tb = blz("Frame", "ToyBox", journal, 700, 540, "TOPLEFT", 0, 0)
    tb.shown = false
    tb.progressBar = progressBar(tb, 196, 13, 0, -39, "4 / 12")
    local icons = inset(tb, 690, 440, "TOPLEFT", 4, -60)
    tb.iconsFrame = icons
    icons.BackgroundTile = tex(icons, nil, "BACKGROUND")
    icons.ShadowCornerTopLeft = tex(icons, nil, "BORDER")
    icons.ShadowCornerBottom = tex(icons, nil, "BORDER")
    for i, d in ipairs(TOYS) do
        local b = spellButton(icons, i, 20 + ((i - 1) % 2) * 300, -20 - math.floor((i - 1) / 2) * 70, d.name)
        icons["spellButton" .. i] = b
        spellInit(b, d)
    end
    tb.PagingFrame = paging(tb, 21, 43, "Page 1 of 3")
    return tb
end

-------------------------------------------------------------------------------
-- Heirlooms (the entries and headers are made as a page is laid out)
-------------------------------------------------------------------------------
HEIRLOOMS = {
    { name = "Mulgore Walking Stick", collected = true, level = 3 },
    { name = "Thunder Bluff Cloak", collected = true, level = 7 },
    { name = "Faded Satchel", collected = false },
}
local function buildHeirlooms(journal)
    local hj = blz("Frame", "HeirloomsJournal", journal, 700, 540, "TOPLEFT", 0, 0)
    hj.shown = false
    hj.progressBar = progressBar(hj, 196, 13, 0, -39, "2 / 3")
    local icons = inset(hj, 690, 440, "TOPLEFT", 4, -60)
    hj.iconsFrame = icons
    icons.BackgroundTile = tex(icons, nil, "BACKGROUND")
    icons.ShadowCornerTopLeft = tex(icons, nil, "BORDER")
    hj.PagingFrame = paging(hj, 21, 43, "Page 1 of 2")
    hj.heirloomEntryFrames, hj.heirloomHeaderFrames = {}, {}
    function hj:UpdateButton(b)
        local d = HEIRLOOMS[b.itemID]
        spellInit(b, d)
        b.special:SetShown(false)
        if d.collected then
            b.levelBackground:Show(); b.lvl:Show()
            b.lvl:SetFontObject("GameFontWhiteSmall"); b.lvl:SetText(d.level)
            b.special:SetTextColor(0.427, 0.352, 0, 1)
        else
            b.levelBackground:Hide(); b.lvl:Hide()
        end
    end
    function hj:LayoutCurrentPage()
        for i = 1, 2 do
            if not self.heirloomHeaderFrames[i] then
                local h = blz("Frame", nil, icons, 625, 24, "TOP", 0, -10 - (i - 1) * 140)
                tex(h, nil, "BACKGROUND")
                h.text = at(stock(fstring(h, nil, i == 1 and "Weapons" or "Armor", 16, { 0.47, 0.44, 0.28, 1 })), h, "CENTER")
                h.text.justify = "CENTER"
                self.heirloomHeaderFrames[i] = h
            end
        end
        for i, d in ipairs(HEIRLOOMS) do
            if not self.heirloomEntryFrames[i] then
                local b = spellButton(icons, i, 20 + (i - 1) * 200, -50, d.name)
                b.itemID = i
                b.special = at(stock(fstring(b, nil, "PvP", 10)), b, "LEFT", 58, -14); b.special.shown = false
                b.glow = tex(b, nil, "OVERLAY"); b.glow.alpha = 0
                b.pendingUpgradeGlow = tex(b, nil, "OVERLAY"); b.pendingUpgradeGlow.shown = false
                b.levelBackground = tex(b, nil, "OVERLAY"); b.levelBackground.w, b.levelBackground.h = 18, 18
                b.levelBackground.points[1] = { point = "BOTTOMRIGHT", rel = b, relPoint = "BOTTOMRIGHT", x = 2, y = -2 }
                b.lvl = at(stock(fstring(b, nil, "3", 10, { 1, 1, 1, 1 })), b, "BOTTOMRIGHT", -4, 4)
                self.heirloomEntryFrames[i] = b
                self:UpdateButton(b)
            end
        end
    end
    return hj
end

function BuildBlizzard()
    build()
    for _, n in ipairs({ "CollectionsJournal", "MountJournal", "PetJournal", "ToyBox", "HeirloomsJournal" }) do _G[n] = nil end
    local win = blz("Frame", "CollectionsJournal", UIParent, 700, 540)
    win.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 60, y = -60 }
    win.shown = false
    win.Bg = tex(win, nil, "BACKGROUND")
    win.NineSlice = blz("Frame", nil, win, 700, 540)
    win.TitleContainer = blz("Frame", nil, win, 640, 20)
    win.CloseButton = blz("Button", nil, win, 15, 15, "TOPRIGHT", -6, -4)
    tex(win.CloseButton, nil, "BACKGROUND")
    buildMounts(win)
    buildPets(win)
    buildToys(win)
    buildHeirlooms(win)
end
"""

H = Harness({
    "ButtonSkins": "Core/ButtonSkins.lua",
    "Character": "Modules/Skins/Character.lua",
    "GroupKit": "Modules/Skins/GroupKit.lua",
    "Collections": "Modules/Skins/Collections.lua",
}, BLIZZARD)
case = H.case

SHOW = "Fire('PLAYER_ENTERING_WORLD'); CollectionsJournal:Show(); FlushTimers(); local C = FS.GroupSkin.C; local S = FS.CollectionsSkin.state\n"
LUA_HELPERS = """
local function same(a, b) return math.abs(a[1] - b[1]) < 0.01 and math.abs(a[2] - b[2]) < 0.01 and math.abs(a[3] - b[3]) < 0.01 end
local function textIs(fs, c) local r, g, b = fs:GetTextColor(); return same({ r, g, b }, c) end
local function mono(fs) return fs.fontPath ~= 'stock.ttf' end
"""
PRE = SHOW + LUA_HELPERS

case("mounts: the insets are held and the list and model wells are rings of ours", PRE + """
    local m = MountJournal
    for _, key in ipairs({ 'LeftInset', 'RightInset', 'BottomLeftInset' }) do
        assert(m[key].NineSlice.alpha == 0 and m[key].Bg.alpha == 0, key .. ' stock art kept')
        assert(S.wells[m[key]] and S.wells[m[key]].edges[1].color, key .. ' has no ring well')
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("mounts: each row is an ink card with the stock art held, the icon ringed and the name mono", PRE + """
    for i, r in ipairs(MountJournal.ScrollBox.rows) do
        local rec = S.rows[r]
        assert(rec, 'row ' .. i .. ' not carded')
        assert(r.background.alpha == 0 and r.selectedTexture.alpha == 0 and r.newGlow.alpha == 0, 'row art kept ' .. i)
        assert(r.icon.alpha == 1 and r.favorite.alpha == 1, 'icon or star held ' .. i)
        assert(S.rings[r.icon], 'icon ' .. i .. ' not ringed')
        assert(mono(r.name), 'name not mono ' .. i)
        assert(r.scripts.OnClick and r.scripts.OnEnter and r.DragButton.scripts.OnDragStart, 'click lost ' .. i)
    end
""")

case("mounts: the name colour follows the stock collected state through every SetFontObject", PRE + """
    local rows = MountJournal.ScrollBox.rows
    assert(textIs(rows[1].name, C.text), 'collected name is not text')
    assert(textIs(rows[4].name, C.muted), 'uncollected name is not muted')
    MountJournal.ScrollBox:Update()
    assert(mono(rows[1].name) and mono(rows[4].name), 'stock update undid the mono font')
    assert(textIs(rows[1].name, C.text) and textIs(rows[4].name, C.muted), 'stock update undid the colour')
    rows[1].name:SetFontObject('GameFontDisable')
    assert(mono(rows[1].name) and textIs(rows[1].name, C.muted), 'a later SetFontObject was not followed')
""")

case("mounts: the LED edge follows summoned and cannot use here, the card the selection", PRE + """
    local rows = MountJournal.ScrollBox.rows
    assert(same(S.rows[rows[2]].led.t.color, C.cyan), 'summoned row is not cyan')
    assert(same(S.rows[rows[3]].led.t.color, C.pink), 'unusable row is not pink')
    assert(same(S.rows[rows[1]].led.t.color, C.dim), 'plain row is not dim')
    assert(S.rows[rows[1]].selected and not S.rows[rows[2]].selected, 'selection not read')
    rows[2].DragButton.ActiveTexture:Hide()
    assert(same(S.rows[rows[2]].led.t.color, C.dim), 'dismount not followed')
    rows[1].selectedTexture:Hide(); rows[2].selectedTexture:Show()
    assert(not S.rows[rows[1]].selected and S.rows[rows[2]].selected, 'selection not followed')
""")

case("mounts: hover lights the edge of a row", PRE + """
    local r = MountJournal.ScrollBox.rows[3]
    local rec = S.rows[r]
    local before = rec.box.edges[1].color[2]
    r:RunScript('OnEnter')
    assert(rec.box.edges[1].color[2] ~= before, 'hover did not change the edge')
""")

case("mounts: the model display and the info block lose their stock art and wear mono text", PRE + """
    local d = MountJournal.MountDisplay
    assert(d.YesMountsTex.alpha == 0 and d.NoMountsTex.alpha == 0, 'backdrop kept')
    assert(d.ShadowOverlay.alpha == 0, 'shadow overlay kept')
    assert(mono(d.NoMounts), 'empty text not mono')
    local i = d.InfoButton
    assert(mono(i.Name) and mono(i.Source) and mono(i.Lore), 'info text not mono')
    assert(i.Icon.alpha == 1 and S.rings[i.Icon], 'info icon not ringed')
    assert(i.NewGlow.alpha == 0, 'new glow kept')
    assert(d.ModelScene.alpha == 1 and d.ModelScene.ControlFrame.alpha == 1, 'model scene must stay stock')
""")

case("counts: the chip insets are held, ringed, the label muted and the count cyan", PRE + """
    for _, chipf in ipairs({ MountJournal.MountCount, PetJournal.PetCount }) do
        assert(chipf.NineSlice.alpha == 0 and chipf.Bg.alpha == 0, 'chip art kept')
        assert(S.wells[chipf], 'chip has no ring')
        assert(mono(chipf.Label) and textIs(chipf.Label, C.muted), 'label not muted mono')
        assert(mono(chipf.Count) and textIs(chipf.Count, C.cyan), 'count not cyan mono')
    end
""")

case("summon key: the spell key loses its frame art, keeps the icon and the cover, and is a ring key", PRE + """
    local sb = MountJournal.SummonRandomFavoriteSpellFrame.Button
    assert(sb.Border.alpha == 0 and sb.LockIcon.alpha == 0, 'border kept')
    assert(sb.Icon.alpha == 1 and sb.BlackCover.alpha == 1, 'icon or cover held')
    assert(FS.GroupSkin.squares[sb], 'not a ring key')
    assert(mono(MountJournal.SummonRandomFavoriteSpellFrame.Label), 'label not mono')
    assert(sb.scripts.OnClick and sb.scripts.OnEnter, 'click lost')
""")

case("pets: rows are cards, the dead and summoned LED, level and names mono, icon and quality border kept", PRE + """
    local rows = PetJournal.ScrollBox.rows
    for i, r in ipairs(rows) do
        assert(S.rows[r], 'pet row ' .. i)
        assert(r.background.alpha == 0 and r.selectedTexture.alpha == 0 and r.newGlow.alpha == 0, 'row art kept ' .. i)
        assert(r.icon.alpha == 1 and r.iconBorder.alpha == 1 and r.petTypeIcon.alpha == 1, 'info held ' .. i)
        assert(S.rings[r.icon], 'icon not ringed ' .. i)
        assert(mono(r.name) and mono(r.subName) and mono(r.dragButton.lvl), 'text not mono ' .. i)
        assert(r.dragButton.levelBG.alpha == 1 and r.dragButton.favorite.alpha == 1, 'bubble or star held ' .. i)
    end
    assert(same(S.rows[rows[1]].led.t.color, C.cyan), 'summoned pet is not cyan')
    assert(same(S.rows[rows[3]].led.t.color, C.pink), 'dead pet is not pink')
    assert(S.rows[rows[1]].selected, 'selection not read')
    PetJournal.ScrollBox:Update()
    assert(mono(rows[2].name) and textIs(rows[2].name, C.text), 'stock update undid the name')
""")

case("pets: the insets are held and ringed, the pet card loses its stock art and wears mono", PRE + """
    local p = PetJournal
    for _, key in ipairs({ 'LeftInset', 'RightInset' }) do
        assert(p[key].NineSlice.alpha == 0 and S.wells[p[key]], key)
    end
    local c = p.PetCard
    for i = 1, 3 do assert(c['AbilitiesBG' .. i].alpha == 0, 'abilities bg kept ' .. i) end
    assert(c.shadows.alpha == 0, 'shadows kept')
    assert(mono(c.PetInfo.name) and mono(c.PetInfo.subName) and mono(c.TypeInfo.type), 'card text not mono')
    assert(mono(c.HealthFrame.health) and mono(c.PowerFrame.power) and mono(c.SpeedFrame.speed) and mono(c.QualityFrame.quality), 'stat text not mono')
    assert(c.PetInfo.icon.alpha == 1 and c.PetInfo.qualityBorder.alpha == 1, 'card icon or quality held')
""")

case("toys: the shelf and the slots lose their stock frames, keep icon and cooldown, gain a ring box", PRE + """
    local tb = ToyBox
    local icons = tb.iconsFrame
    assert(icons.NineSlice.alpha == 0 and icons.Bg.alpha == 0 and icons.BackgroundTile.alpha == 0 and icons.ShadowCornerTopLeft.alpha == 0, 'shelf art kept')
    assert(S.wells[icons], 'shelf has no ring')
    for i = 1, 4 do
        local b = icons['spellButton' .. i]
        assert(S.slots[b] and S.slots[b].box, 'slot ' .. i)
        assert(b.slotFrameCollected.alpha == 0 and b.slotFrameUncollected.alpha == 0 and b.slotFrameUncollectedInnerGlow.alpha == 0, 'slot frame kept ' .. i)
        assert(b.HighlightTexture.alpha == 0 and b.newGlow.alpha == 0, 'highlight or glow kept ' .. i)
        assert(b.iconTexture.alpha == 1 and b.iconTextureUncollected.alpha == 0.18, 'icons touched ' .. i)
        assert(b.cooldown.alpha == 1 and b.cooldownWrapper.slotFavorite.alpha == 1, 'cooldown or star held ' .. i)
        assert(mono(b.name), 'name not mono ' .. i)
        assert(b.scripts.OnClick and b.scripts.OnEnter, 'click lost ' .. i)
    end
""")

case("toys: the name colour follows the stock write, the LED reads ready, cooling and uncollected", PRE + """
    local icons = ToyBox.iconsFrame
    local b1, b2, b3 = icons.spellButton1, icons.spellButton2, icons.spellButton3
    assert(textIs(b1.name, C.text) and textIs(b3.name, C.muted), 'name colours')
    b3.name:SetTextColor(1, 0.82, 0, 1)
    assert(textIs(b3.name, C.text), 'a later stock colour was not mapped')
    assert(same(S.slots[b1].led.t.color, C.cyan), 'ready is not cyan')
    assert(same(S.slots[b2].led.t.color, C.amber), 'cooling is not amber')
    b2.cooldown:Hide()
    assert(same(S.slots[b2].led.t.color, C.cyan), 'cooldown end not followed')
    b3.slotFrameCollected:Hide(); b3.slotFrameUncollected:Show()
    assert(S.slots[b3].led.t.color[4] < 0.5, 'uncollected LED is not dim')
""")

case("toys: hover lights the edge of a slot", PRE + """
    local b = ToyBox.iconsFrame.spellButton1
    local before = S.slots[b].box.edges[1].color[2]
    b:RunScript('OnEnter')
    assert(S.slots[b].box.edges[1].color[2] ~= before, 'hover did not change the edge')
""")

case("progress bars: border and backdrop held, flat cyan bar, ring, mono text", PRE + """
    for _, bar in ipairs({ ToyBox.progressBar, HeirloomsJournal.progressBar }) do
        assert(bar.border.alpha == 0, 'border kept')
        for _, r in ipairs(bar.regions) do
            if r.kind == 'Texture' and r.path then assert(r.alpha == 0, 'bar texture kept') end
        end
        assert(bar.barPath and bar.barPath ~= '', 'bar texture not flat')
        assert(same(bar.barColor, C.cyan), 'bar not cyan')
        assert(S.bars[bar], 'bar has no ring')
        assert(mono(bar.text) and textIs(bar.text, C.text), 'bar text')
    end
""")

case("paging: prev and next are cut keys with the stock art held, the page text mono", PRE + """
    for _, p in ipairs({ ToyBox.PagingFrame, HeirloomsJournal.PagingFrame }) do
        for _, key in ipairs({ 'PrevPageButton', 'NextPageButton' }) do
            local b = p[key]
            assert(S.pagers[b], key .. ' not a key')
            assert(b.normalTex.alpha == 0 and b.highlightTex.alpha == 0, key .. ' stock art kept')
            assert(b.scripts.OnClick, key .. ' click lost')
        end
        assert(mono(p.PageText) and textIs(p.PageText, C.muted), 'page text')
    end
""")

case("heirlooms: entries and headers made when a page is laid out are skinned as they appear", PRE + """
    local hj = HeirloomsJournal
    assert(#hj.heirloomEntryFrames == 0, 'mock made entries early')
    hj:LayoutCurrentPage()
    for i, b in ipairs(hj.heirloomEntryFrames) do
        assert(S.slots[b], 'entry ' .. i)
        assert(b.slotFrameCollected.alpha == 0 and b.slotFrameUncollected.alpha == 0 and b.HighlightTexture.alpha == 0, 'slot frame kept ' .. i)
        assert(b.levelBackground.alpha == 1 and mono(b.lvl) and mono(b.name), 'level or name ' .. i)
        assert(b.glow.alpha == 0 and b.pendingUpgradeGlow.alpha == 1, 'stock upgrade glows are animated and stay stock')
    end
    for i, h in ipairs(hj.heirloomHeaderFrames) do
        for _, r in ipairs(h.regions) do if r.kind == 'Texture' and r.path then assert(r.alpha == 0, 'header art kept ' .. i) end end
        assert(mono(h.text), 'header text not mono ' .. i)
    end
    assert(textIs(hj.heirloomEntryFrames[1].name, C.text) and textIs(hj.heirloomEntryFrames[3].name, C.muted), 'entry name colours')
    local n = #hj.heirloomEntryFrames[1].regions
    hj:LayoutCurrentPage()
    assert(#hj.heirloomEntryFrames[1].regions == n, 'regions grew on a second layout')
""")

case("heirlooms: the shelf is held and ringed like the toy box", PRE + """
    local icons = HeirloomsJournal.iconsFrame
    assert(icons.NineSlice.alpha == 0 and icons.BackgroundTile.alpha == 0 and icons.ShadowCornerTopLeft.alpha == 0, 'shelf art kept')
    assert(S.wells[icons], 'shelf has no ring')
""")

case("nothing is built in combat; it is built when combat ends", """
    Reset()
    __combat = true
    FS = Load({ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'ButtonSkins', 'Character', 'GroupKit', 'Collections' })
    local first = MountJournal.ScrollBox.rows[1]
    assert(not FS.CollectionsSkin.state.rows[first], 'built in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(FS.CollectionsSkin.state.rows[first], 'not built when combat ended')
""")

case("a client without a journal degrades quietly, and a second build adds nothing", PRE + """
    local r = MountJournal.ScrollBox.rows[1]
    local n = #r.regions
    FS.CollectionsSkin.Build(); MountJournal.ScrollBox:Update(); FlushTimers()
    assert(#r.regions == n, 'regions grew')
    local pn = #PetJournal.ScrollBox.rows[1].regions
    PetJournal.ScrollBox:Update(); FS.CollectionsSkin.Build()
    assert(#PetJournal.ScrollBox.rows[1].regions == pn, 'pet regions grew')
    MountJournal, PetJournal, ToyBox, HeirloomsJournal, CollectionsJournal = nil, nil, nil, nil, nil
    FS.CollectionsSkin.Build()
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

SCENE = "Fire('PLAYER_ENTERING_WORLD'); FS.Theme.SkinPanel(CollectionsJournal, {title='collections'}); CollectionsJournal:Show(); %s FlushTimers(); return DumpOps({ CollectionsJournal })"
SCENES = {
    "mounts": SCENE % "",
    "pets": SCENE % "MountJournal:Hide(); PetJournal:Show();",
    "toys": SCENE % "MountJournal:Hide(); ToyBox:Show();",
    "heirlooms": SCENE % "MountJournal:Hide(); HeirloomsJournal:Show(); HeirloomsJournal:LayoutCurrentPage();",
}

if __name__ == "__main__":
    raise SystemExit(H.main("collections skin", SCENES))
