#!/usr/bin/env python3
"""Runs the real Modules/Skins/Talents.lua headless against a mock PlayerSpellsFrame (tools/charskin_support.py).

Pinned: a talent button is a cut plate whose edge is told by the stock border atlas and the node's ranks (locked and idle dim,
available violet, learned cyan, maxed amber, refund pink, hover cyan) with a veil on a locked icon and a legible "x/y" rank chip in
its bottom right corner, the stock ring, shadow, dimmer and rank texts held, no script, attribute or field written on it, and a
button built later is met on the next refresh. The arrows between nodes are a solid line in the palette and a bright head tinted to
match, following each stock atlas swap, the ghost parts stock. The stock frame art, class paintings and dividers are held and no line
of ours crosses a header or a number: three tree panels fill the gaps between the stock dividers (lit on the tree with points), the
spec headers are a row of square icon plate, name and points chip, the Unspent Talents box is fitted around its label and number,
the Primary and Secondary tabs lose the inline check and lock markup for glyphs of ours and fit their text (alone and under
TabSkins). The minimise and maximise buttons wear the close button's key in cyan, the spellbook parchment is held and dark text
retinted with state colours left alone, each spell entry is a cut card whose edge follows its state (learned, passive, trainable,
level locked, hover) with its icon button on the shared slot layer and the page keys of the paging controls cut keys, and nothing
is built in combat.
Run `python3 tools/talentsskin-harness.py [--png /tmp/tal]`. The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring, atex = BLZ.blz, BLZ.tex, BLZ.fstring, nil
local build = BuildBlizzard
function BuildBlizzard()
    build()
    atex = BLZ.atex
    for k in pairs(_G) do if type(k) == "string" and k:find("^PlayerSpells") then _G[k] = nil end end
    local win = blz("Frame", "PlayerSpellsFrame", UIParent, 1218, 708)
    win.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 100, y = -80 }
    win.shown = false
    win.CloseButton = blz("Button", "PlayerSpellsFrameCloseButton", win, 15, 15, "TOPRIGHT", -4, -4)
    local mm = blz("Frame", nil, win, 28, 28, "TOPRIGHT", -30, -6)
    win.MaximizeMinimizeButton = mm
    mm.MinimizeButton = blz("Button", nil, mm, 28, 28)
    atex(mm.MinimizeButton, nil, "ARTWORK", "RedButton-Condense", 28, 28)
    mm.MinimizeButton.scripts.OnClick = function() end
    mm.MaximizeButton = blz("Button", nil, mm, 28, 28)
    atex(mm.MaximizeButton, nil, "ARTWORK", "RedButton-Expand", 28, 28)
    mm.MaximizeButton.scripts.OnClick = function() end
    mm.MaximizeButton.shown = false

    -- measuring calls the engine has and the shared mock does not (the client's y runs up)
    function Obj:GetTop() local _, t = self:Rect(); return -t end
    function Obj:GetBottom() local _, _, _, b = self:Rect(); return -b end
    function Obj:GetRight() local _, _, r = self:Rect(); return r end
    function Obj:GetPoint(i) local p = self.points[i or 1]; if p then return p.point, p.rel, p.relPoint, p.x, p.y end end
    function Obj:SetThickness(v) self.thickness = v end
    function Obj:RemoveMaskTexture(m) self.maskRemoved = m end
    function Obj:MarkDirty() self.dirty = (self.dirty or 0) + 1 end

    local tf = blz("Frame", nil, win, 1212, 681, "TOPLEFT", 3, -24)
    win.TalentsFrame = tf
    for key, atlas in pairs({ Background = "Talents-Background-c60", BackgroundBorder = "Talents-inner-frame-c60",
        DividerHorizontalLeft = "Talents-divider-left-c60", DividerHorizontalRight = "Talents-divider-right-c60",
        DividerVerticalLeft = "Talents-divider-vertical-c60", DividerVerticalRight = "Talents-divider-vertical-c60",
        Clouds1 = "talents-animations-clouds", Clouds2 = "talents-animations-clouds", AirParticlesClose = "talents-animations-particles",
        AirParticlesFar = "talents-animations-particles", ClassBackground = "talent-background-shaman",
        BackgroundFlash = "talent-background-shaman", OverlayBackgroundRight = "talent-background-shaman",
        OverlayBackgroundMid = "talent-background-shaman" }) do
        tf[key] = atex(tf, nil, "BACKGROUND", atlas, 600, 400)
    end
    -- where the stock layout puts the inner frame and the two dividers between the three trees (units from the frame's top left)
    tf.BackgroundBorder.w, tf.BackgroundBorder.h = 1216, 603
    tf.BackgroundBorder.points[1] = { point = "TOPLEFT", rel = tf, relPoint = "TOPLEFT", x = -2, y = -58 }
    for key, x in pairs({ DividerVerticalLeft = 404, DividerVerticalRight = 808 }) do
        tf[key].w, tf[key].h = 2, 468
        tf[key].points[1] = { point = "TOPLEFT", rel = tf, relPoint = "TOPLEFT", x = x, y = -120 }
    end
    for key, x in pairs({ DividerHorizontalLeft = 0, DividerHorizontalRight = 600 }) do
        tf[key].w, tf[key].h = 600, 56
        tf[key].points[1] = { point = "TOPLEFT", rel = tf, relPoint = "TOPLEFT", x = x, y = -10 }
    end
    tf.ButtonsParent = blz("Frame", nil, tf, 1212, 641, "TOPLEFT", 0, 0)
    -- a talent button (TalentButtonArt): the ring, a hover ring, the shadow, the dimmer, the glow, the rank text and its four
    -- outline copies; `info` is the node data the stock code keeps on the button
    local function node(name, atlas, x, y, info)
        local b = blz("Button", name, tf.ButtonsParent, 40, 40, "TOPLEFT", x, y)
        b.Shadow = atex(b, nil, "BACKGROUND", "talents-node-square-shadow", 78, 78)
        b.Icon = tex(b, nil, "BORDER")
        b.Icon.path, b.Icon.w, b.Icon.h = "Interface\\Icons\\spell_nature_riptide", 36, 36
        b.Icon.points[1] = { point = "CENTER", rel = b, relPoint = "CENTER", x = 0, y = 0 }
        b.DisabledOverlay = tex(b, nil, "BORDER")
        b.DisabledOverlay.w, b.DisabledOverlay.h = 36, 36
        b.StateBorder = atex(b, nil, "ARTWORK", atlas, 40, 40)
        b.StateBorderHover = atex(b, nil, "ARTWORK", atlas, 40, 40)
        b.Glow = atex(b, nil, "OVERLAY", "talents-node-square-greenglow", 84, 84)
        b.SelectableGlow = atex(b, nil, "OVERLAY", "talents-node-square-greenglow", 61, 61)
        b.SpendText = fstring(b, nil, "", 16, { 1, 1, 1, 1 })
        b.spendTextShadows = {}
        for i = 1, 4 do b.spendTextShadows[i] = fstring(b, nil, "", 16, { 0, 0, 0, 1 }) end
        b.nodeInfo = info
        for _, r in ipairs({ b.StateBorder, b.StateBorderHover, b.Glow, b.SelectableGlow }) do
            r.SetDesaturated = function(self, v) self.desat = v end
        end
        -- the stock rank text: the current rank once a point is spent (or the node can take one), nothing before
        function b:UpdateSpendText()
            local ni = self.nodeInfo
            local text = (ni and (ni.ranksPurchased > 0 or self.StateBorder.atlas:find("green"))) and tostring(ni.currentRank) or ""
            self.SpendText:SetText(text)
            for _, s in ipairs(self.spendTextShadows) do s:SetText(text) end
        end
        b:UpdateSpendText()
        b.scripts.OnClick = function() end
        b.scripts.OnEnter = function() end
        b.scripts.OnLeave = function() end
        return b
    end
    local function info(current, max) return { currentRank = current, activeRank = current, ranksPurchased = current, maxRanks = max } end
    node("Riptide", "talents-node-square-locked", 60, -150, info(0, 3))
    node("Purification", "talents-node-square-gray", 120, -150, info(0, 5))
    node("Healing Way", "talents-node-square-yellow", 180, -150, info(3, 3))
    node("Tidal Focus", "talents-node-square-green", 240, -150, info(0, 5))
    node("Nature's Swiftness", "talents-node-square-yellow", 300, -150, info(2, 5))
    node("Cultivation", "talents-node-square-red", 360, -150, info(1, 2))
    -- the arrows between nodes (TalentEdgeArrowTemplate): a Line and an ArrowHead whose atlas the stock UpdateState swaps by
    -- state; the line is a stock Line region (thickness 6)
    EDGES = {}
    function BLZ.edge(name, state)
        local e = blz("Frame", name, tf.ButtonsParent, 60, 6, "TOPLEFT", 100, -80)
        e.state = state
        e.Line = atex(e, nil, "OVERLAY", "talents-arrow-line-" .. state, 60, 6)
        e.Line.thickness = 6
        e.ArrowHead = atex(e, nil, "OVERLAY", "talents-arrow-head-" .. state, 14, 12)
        e.GhostLine = atex(e, nil, "OVERLAY", "talents-arrow-line-ghost", 60, 6)
        e.GhostArrowHead = atex(e, nil, "OVERLAY", "talents-arrow-head-ghost", 12, 12)
        for _, r in ipairs({ e.Line, e.ArrowHead }) do r.SetDesaturated = function(self, v) self.desat = v end end
        function e:UpdateState()
            self.Line:SetAtlas("talents-arrow-line-" .. self.state)
            self.ArrowHead:SetAtlas("talents-arrow-head-" .. self.state)
        end
        EDGES[#EDGES + 1] = e
        return e
    end
    BLZ.edge("EdgeGray", "gray")
    BLZ.edge("EdgeYellow", "yellow")
    BLZ.edge("EdgeLocked", "locked")
    BLZ.edge("EdgeRed", "red")
    -- the three spec headers: a 48 x 48 frame holding the round icon and its mask, the gold ring, the count box with its count,
    -- the name to the right of the ring and the small divider under it
    for i, spec in ipairs({ { "Elemental Combat", 0 }, { "Enhancement", 13 }, { "Restoration", 0 } }) do
        local h = blz("Frame", nil, tf, 48, 48, "TOPLEFT", 150 + (i - 1) * 404, -78)
        h.Icon = tex(h, nil, "BORDER")
        h.Icon.path, h.Icon.w, h.Icon.h = "Interface\\Icons\\spell_nature_lightning", 36, 36
        h.Icon.points[1] = { point = "CENTER", rel = h, relPoint = "CENTER", x = 0, y = 0 }
        local mask = new("MaskTexture", nil, h, true)
        mask.w = 40
        h.regions[#h.regions + 1] = mask
        h.MainRing = atex(h, nil, "OVERLAY", "Talents-Main-Ring-c60", 55, 55)
        h.MainRing.points[1] = { point = "CENTER", rel = h, relPoint = "CENTER", x = 0, y = 0 }
        h.Name = fstring(h, nil, spec[1], 14, { 1, 0.82, 0, 1 })
        h.Name.points[1] = { point = "LEFT", rel = h, relPoint = "RIGHT", x = 12, y = 0 }
        h.TextBackground = atex(h, nil, "OVERLAY", "Talents-Main-Ring-Box-c60", 24, 20)
        h.TextBackground.points[1] = { point = "BOTTOMRIGHT", rel = h.Icon, relPoint = "BOTTOMRIGHT", x = 8, y = -8 }
        h.Text = fstring(h, nil, tostring(spec[2]), 11, { 1, 0.82, 0, 1 })
        h.Text.points[1] = { point = "CENTER", rel = h.TextBackground, relPoint = "CENTER", x = 0, y = 0 }
        h.Divider = atex(h, nil, "OVERLAY", "Talents-small-divider-c60", 355, 64)
        h.Divider.points[1] = { point = "CENTER", rel = h, relPoint = "CENTER", x = 100, y = 0 }
        h.MainRing.SetDesaturated = function(self, v) self.desat = v end
    end
    -- the Unspent Talents readout (a layout frame): the label, then the amount container to its right, the amount in the container's
    -- middle, and the box art, a fixed 125 x 45 texture
    local cur = blz("Frame", nil, tf, 160, 45, "TOPRIGHT", -20, -10)
    tf.ClassCurrencyDisplay = cur
    cur.Border = atex(cur, nil, "ARTWORK", "Talents-Square-Box-c60", 125, 45)
    cur.UnspentLabel = fstring(cur, nil, "Unspent Talents", 12, { 1, 1, 1, 1 })
    cur.UnspentLabel.points[1] = { point = "LEFT", rel = cur, relPoint = "LEFT", x = 4, y = 0 }
    cur.CurrentAmountContainer = blz("Frame", nil, cur, 48, 36)
    cur.CurrentAmountContainer.points[1] = { point = "LEFT", rel = cur.UnspentLabel, relPoint = "RIGHT", x = 3, y = 0 }
    cur.CurrentAmountContainer.CurrencyAmount = fstring(cur.CurrentAmountContainer, nil, "0", 22, { 1, 1, 1, 1 })
    cur.CurrentAmountContainer.CurrencyAmount.points[1] = { point = "CENTER", rel = cur.CurrentAmountContainer, relPoint = "CENTER", x = 0, y = 0 }

    -- the Primary / Secondary tabs (a TabSystem): the label carries inline atlases for the checkmark and the lock
    local ts = blz("Frame", nil, tf, 301, 32, "TOPLEFT", 40, -4)
    tf.TabSystem = ts
    local function tab(x, text)
        local t = blz("Button", nil, ts, 150, 32, "TOPLEFT", x, 0)
        t.Text = fstring(t, nil, text, 12, { 1, 0.82, 0, 1 })
        t.Text.points[1] = { point = "CENTER", rel = t, relPoint = "CENTER", x = 0, y = 0 }
        t.Text.w = 140
        t.fs = t.Text
        t.SetTabEnabled = function(self, on) self.Text:SetText(on and self.tabText or ("|cff808080" .. self.tabText .. "|r")) end
        t.UpdateTabWidth = function(self) self.w = 150 end
        t.tabText = text
        t.scripts.OnClick = function() end
        return t
    end
    ts.primary = tab(0, "Primary |A:Talents-Checkmark-c60:15:20:0:0|a")
    ts.secondary = tab(151, "|cff808080Secondary |A:Talents-lock-c60:14:10:0:0|a|r")
    ts.secondary.tabText = "Secondary |A:Talents-lock-c60:14:10:0:0|a"

    local book = blz("Frame", nil, win, 1148, 702, "TOPLEFT", 3, -24)
    book.shown = false
    win.SpellBookFrame = book
    book.BookBGLeft = atex(book, nil, "BACKGROUND", "spellbook-Page-Left-C60", 574, 702)
    book.BookBGRight = atex(book, nil, "BACKGROUND", "spellbook-Page-Right-C60", 574, 702)
    book.BookCornerFlipbook = atex(book, nil, "BACKGROUND", "spellbook-corner-flipbook-evergreen", 150, 155)
    book.tabSystem = blz("Frame", nil, book, 0, 0)
    local t = blz("Button", nil, book.tabSystem, 44, 32)
    t.SquareBackground = atex(t, nil, "ARTWORK", "spellbook-Tab-Frame-C60", 43, 38)
    t.SquareBackgroundActive = atex(t, nil, "ARTWORK", "spellbook-Tab-Frame-Glow-C60", 43, 38)
    t.SquareBackgroundActiveGlow = atex(t, nil, "ARTWORK", "spellbook-Tab-Frame-glow-gradient-C60", 43, 38)
    local row = blz("Frame", nil, book, 500, 40, "TOPLEFT", 20, -60)
    atex(row, nil, "BACKGROUND", "spellbook-Divider-C60", 500, 8)
    book.dark = fstring(row, nil, "Lightning Bolt", 12, { 0.15, 0.1, 0.05, 1 })
    book.state = fstring(row, nil, "Rank 2", 12, { 1, 0.13, 0.13, 1 })
    book.RefreshDisplay = function() end

    -- the paged pages: two views holding pooled entry frames and a header, and the paging controls (Blizzard_SpellBook)
    local paged = blz("Frame", nil, book, 1148, 652, "TOPLEFT", 0, -50)
    book.PagedSpellsFrame = paged
    paged.View1 = blz("Frame", nil, paged, 448, 520, "TOPLEFT", 60, -20)
    paged.View2 = blz("Frame", nil, paged, 448, 520, "TOPLEFT", 600, -20)
    function paged:ForEachFrame(fn)
        for _, v in ipairs({ self.View1, self.View2 }) do for _, f in ipairs(v.children) do fn(f) end end
    end
    function paged:DisplayViewsForCurrentPage() end
    function paged:OnPageChanged() end
    local pc = blz("Frame", nil, paged, 133, 32, "BOTTOM", 0, 10)
    paged.PagingControls = pc
    pc.PageText = fstring(pc, nil, "Page 1/3", 12, { 1, 1, 1, 1 })
    local function pager(key)
        local b = blz("Button", nil, pc, 32, 32, "CENTER", key == "PrevPageButton" and 40 or 80, 0)
        b.NormalTexture = tex(b, nil, "ARTWORK")
        b.GetNormalTexture = function(self) return self.NormalTexture end
        b.scripts.OnClick = function() end
        pc[key] = b
    end
    pager("PrevPageButton"); pager("NextPageButton")
    pc.PrevPageButton:Disable()

    local function header(view, text, x, y)
        local h = blz("Frame", nil, view, 300, 51, "TOPLEFT", x, y)
        h.Backplate = atex(h, nil, "BACKGROUND", "spellbook-list-backplate", 416, 106)
        h.Text = fstring(h, nil, text, 24, { 0.15, 0.1, 0.05, 1 })
        h.Border = atex(h, nil, "ARTWORK", "spellbook-divider", 300, 11)
        h.Border.points[1] = { point = "BOTTOMLEFT", rel = h, relPoint = "BOTTOMLEFT", x = -32, y = 0 }
        return h
    end
    -- o: unlearned, trainable, passive; the stock fields the skin reads (isUnlearned, isTrainable, spellBookItemInfo.isPassive)
    local function entry(view, name, x, y, o)
        o = o or {}
        local it = blz("Frame", nil, view, 220, 60, "TOPLEFT", x, y)
        it.Backplate = atex(it, nil, "BACKGROUND", "spellbook-item-backplate", 130, 76)
        it.TextContainer = blz("Frame", nil, it, 170, 44, "LEFT", 50, -1)
        local ink = { 0.15, 0.1, 0.05, 1 }
        it.TextContainer.Name = fstring(it.TextContainer, nil, name, 16, ink)
        it.TextContainer.SubName = fstring(it.TextContainer, nil, o.passive and "Passive" or "Rank 2", 12, ink)
        it.TextContainer.RequiredLevel = fstring(it.TextContainer, nil, o.trainable and "Trainable" or (o.unlearned and "Available at level 14" or ""), 12, ink)
        it.Name, it.SubName, it.RequiredLevel = it.TextContainer.Name, it.TextContainer.SubName, it.TextContainer.RequiredLevel
        -- the stock stack: Name at the top of the container, SubName under it, RequiredLevel under that
        it.SubName.points[1] = { point = "TOPLEFT", rel = it.Name, relPoint = "BOTTOMLEFT", x = 0, y = -2 }
        it.RequiredLevel.points[1] = { point = "TOPLEFT", rel = it.SubName, relPoint = "BOTTOMLEFT", x = 0, y = -2 }
        local b = blz("Button", nil, it, 40, 40, "LEFT", 0, 0)
        it.Button = b
        b.Icon = tex(b, nil, "ARTWORK")
        b.Icon.path = "Interface\\Icons\\spell_nature_lightning"
        b.Icon.w, b.Icon.h = 36, 36
        b.Icon.points[1] = { point = "CENTER", rel = b, relPoint = "CENTER", x = 0, y = 0 }
        b.Border = atex(b, nil, "OVERLAY", o.passive and "talents-node-circle-gray" or "spellbook-item-iconframe", 56, 56)
        b.TrainableBackplate = atex(b, nil, "BACKGROUND", "spellbook-item-needtrainer-iconframe-backplate", 56, 56)
        b.TrainableShadow = atex(b, nil, "BACKGROUND", "spellbook-item-needtrainer-shadow", 56, 56)
        b.BorderSheen = atex(b, nil, "OVERLAY", "talents-sheen-node", 80, 40)
        b.IconHighlight = atex(b, nil, "OVERLAY", "spellbook-item-iconframe-hover", 40, 40)
        b.scripts.OnClick = function() end
        b.scripts.OnEnter = function() end
        b.scripts.OnLeave = function() end
        it.isUnlearned, it.isTrainable = o.unlearned or false, o.trainable or false
        it.spellBookItemInfo = { isPassive = o.passive or false, name = name }
        function it:UpdateVisuals() end
        function it:Init() self:UpdateVisuals() end
        return it
    end
    BLZ.entry, BLZ.header = entry, header
    header(paged.View1, "Elemental", 0, 0)
    entry(paged.View1, "Lightning Bolt", 0, -60)
    entry(paged.View1, "Mace Specialization", 230, -60, { passive = true })
    entry(paged.View1, "Ancestral Spirit", 0, -130, { unlearned = true, trainable = true })
    entry(paged.View1, "Rockbiter Weapon", 230, -130, { unlearned = true })
end
"""

H = Harness({"ButtonSkins": "Core/ButtonSkins.lua", "Character": "Modules/Skins/Character.lua", "Talents": "Modules/Skins/Talents.lua",
             "Quest": "Modules/Skins/Quest.lua"}, BLIZZARD)
case = H.case

OPEN = "Fire('PLAYER_ENTERING_WORLD'); Fire('ADDON_LOADED', 'Blizzard_PlayerSpells'); PlayerSpellsFrame:Show(); FlushTimers()"

PRE = """
local T = FS.Theme
local function near(a, b, e) return math.abs(a - b) <= (e or 0.02) end
local function is(v, c, e) return v ~= nil and near(v[1], c[1], e) and near(v[2], c[2], e) and near(v[3], c[3], e) end
local function rect(o) local l, t, r, b = o:Rect(); return { l = l, t = t, r = r, b = b } end
local function inside(a, b, s) s = s or 0.02; return a.l >= b.l - s and a.r <= b.r + s and a.t >= b.t - s and a.b <= b.b + s end
local function overlap(a, b) return a.l < b.r - 0.01 and b.l < a.r - 0.01 and a.t < b.b - 0.01 and b.t < a.b - 0.01 end
local function lum(c) return c[1] * 0.3 + c[2] * 0.59 + c[3] * 0.11 end
local function nrec(n) return FS.TalentsSkin.state.nodes[_G[n]] end
local function heads(tf) local out = {}; for _, ch in ipairs({ tf:GetChildren() }) do if ch.MainRing then out[#out + 1] = ch end end; return out end
local VIOLET, CYAN, PINK, AMBER, DIM, MUTED = T.COLOR_BORDER, T.COLOR_POWER, T.COLOR_HEALTH, T.COLOR_AMBER, T.COLOR_CTRL_DIM, T.COLOR_MUTED
"""

case("talent buttons: the stock ring, shadow, dimmer and rank text are held; a cut plate stands in, its edge told by the state", OPEN + PRE + """
    local locked, gray, maxed, open, partial, bad = nrec('Riptide'), nrec('Purification'), nrec('Healing Way'), nrec('Tidal Focus'), nrec("Nature's Swiftness"), nrec('Cultivation')
    for _, n in ipairs({ 'Riptide', 'Purification', 'Healing Way', 'Tidal Focus', "Nature's Swiftness", 'Cultivation' }) do
        local b = _G[n]
        assert(nrec(n) and nrec(n).plate, n .. ' has no plate')
        for _, k in ipairs({ 'StateBorder', 'StateBorderHover', 'Shadow', 'DisabledOverlay' }) do assert(b[k].alpha == 0, n .. ' ' .. k .. ' not held') end
        assert(b.SpendText.alpha == 0, n .. ' stock rank text not held')
        for _, s in ipairs(b.spendTextShadows) do assert(s.alpha == 0, n .. ' stock rank outline not held') end
        assert(b.Icon.alpha == 1, n .. ' icon touched')
        assert(b.scripts.OnClick and b.scripts.OnEnter, 'stock script lost')
    end
    assert(is(locked.plate.ring.vertex, DIM) and not locked.plate.ring2.shown, 'locked: a 1 px dim edge')
    assert(is(gray.plate.ring.vertex, DIM), 'gray (no points to spend): dim edge')
    assert(is(open.plate.ring.vertex, VIOLET) and open.plate.ring2.shown, 'available: a 2 px violet edge')
    assert(is(partial.plate.ring.vertex, CYAN) and partial.plate.ring2.shown, 'learned, ranks left: cyan edge')
    assert(is(maxed.plate.ring.vertex, AMBER) and maxed.plate.ring2.shown, 'maxed: amber edge')
    assert(is(bad.plate.ring.vertex, PINK), 'refund invalid: pink edge')
    assert(locked.dim.alpha > 0 and locked.dim:IsShown() and not open.dim:IsShown() and not maxed.dim:IsShown(), 'only locked nodes are dimmed')
    assert(lum(DIM) < lum(locked.plate.ring.vertex) + 0.001 and locked.plate.fill.vertex[1] < 0.1, 'locked face is the dark ink')
    assert(_G.Tidal.Glow == nil or true)
    assert(is(_G['Tidal Focus'].Glow.vertex, VIOLET) and _G['Tidal Focus'].Glow.desat == true, 'glow not violet')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""".replace("_G.Tidal.Glow == nil or true", "true"))

case("the rank chip: x/y from the node, legible, in the bottom right corner, fitted to its text, one colour per state", OPEN + PRE + """
    local function chipText(n) return nrec(n).chip.text:GetText() end
    assert(chipText('Riptide') == '0/3' and chipText('Purification') == '0/5' and chipText('Healing Way') == '3/3', 'rank text')
    assert(chipText("Nature's Swiftness") == '2/5' and chipText('Tidal Focus') == '0/5' and chipText('Cultivation') == '1/2', 'rank text 2')
    for _, n in ipairs({ 'Riptide', 'Healing Way', "Nature's Swiftness", 'Tidal Focus' }) do
        local r, b = nrec(n), _G[n]
        local chip, node = rect(r.chip.fill), rect(b)
        assert(chip.r >= node.r - 0.5 and chip.b >= node.b - 0.5, n .. ': chip not in the bottom right corner')
        assert(chip.r <= node.r + 3 and chip.b <= node.b + 3, n .. ': chip floats away from the node')
        assert(chip.l > node.l + (node.r - node.l) * 0.2, n .. ': chip covers the node')
        local text = rect(r.chip.text)
        assert(inside(text, chip, 0.3), n .. ': the text spills out of its chip ' .. text.l .. ' ' .. text.r .. ' vs ' .. chip.l .. ' ' .. chip.r)
        assert(r.chip.text.size * 1.2 >= 10, n .. ': text under 10 px')
        assert(r.chip.text.fontPath ~= 'stock.ttf', n .. ': text is not mono')
    end
    local one, many = rect(nrec('Riptide').chip.fill), rect(nrec('Healing Way').chip.fill)
    assert(near(one.r - one.l, many.r - many.l, 0.01), 'same width for the same text length')
    assert(is(nrec('Healing Way').chip.text.textColor, AMBER) and is(nrec("Nature's Swiftness").chip.text.textColor, CYAN), 'learned chips: amber maxed, cyan partial')
    assert(is(nrec('Riptide').chip.text.textColor, MUTED) and nrec('Riptide').chip.text.textColor[1] > 0.5, 'locked chip text must stay readable')
    assert(is(nrec('Riptide').chip.edges[1].color, DIM) and is(nrec('Healing Way').chip.edges[1].color, AMBER), 'chip edge follows the state')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("a state swap or a rank change by the stock code repaints the plate and the chip; hover lights the edge", OPEN + PRE + """
    local b = _G['Riptide']
    b.StateBorder:SetAtlas('talents-node-square-green')
    assert(is(nrec('Riptide').plate.ring.vertex, VIOLET), 'ring did not follow the atlas swap')
    assert(not nrec('Riptide').dim:IsShown(), 'dimmer stayed on an available node')
    b.nodeInfo.currentRank, b.nodeInfo.ranksPurchased = 3, 3
    b:UpdateSpendText()
    assert(nrec('Riptide').chip.text:GetText() == '3/3', 'chip did not follow the rank: ' .. tostring(nrec('Riptide').chip.text:GetText()))
    b.StateBorder:SetAtlas('talents-node-square-yellow')
    assert(is(nrec('Riptide').plate.ring.vertex, AMBER) and is(nrec('Riptide').chip.text.textColor, AMBER), 'maxed did not turn amber')
    b.StateBorder:SetAtlas('talents-node-square-gray')
    assert(is(nrec('Riptide').plate.ring.vertex, DIM), 'ring did not fall back')
    b:RunScript('OnEnter')
    assert(is(nrec('Riptide').plate.ring.vertex, CYAN), 'hover did not light the edge')
    b:RunScript('OnLeave')
    assert(is(nrec('Riptide').plate.ring.vertex, DIM), 'hover stuck')
    assert(b.scripts.OnClick and b.scripts.OnEnter, 'stock script lost')
""")

case("a node with no rank data gets no chip; the stock number stands in when only it is known; a secret value does not throw", OPEN + PRE + """
    local b = _G['Purification']
    b.nodeInfo = nil
    b.SpendText:SetText('')
    b.StateBorder:SetAtlas('talents-node-square-gray')
    assert(not nrec('Purification').chip.fill:IsShown(), 'chip shown with nothing to say')
    b.SpendText:SetText('2')
    assert(nrec('Purification').chip.text:GetText() == '2', 'stock number not used: ' .. tostring(nrec('Purification').chip.text:GetText()))
    b.nodeInfo = Secret()
    b.StateBorder:SetAtlas('talents-node-square-gray')
    b.nodeInfo = { currentRank = Secret(), maxRanks = Secret() }
    b.StateBorder:SetAtlas('talents-node-square-gray')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("a button built later is met on the next refresh", OPEN + PRE + """
    local b = BLZ.blz('Button', 'Latecomer', PlayerSpellsFrame.TalentsFrame.ButtonsParent, 40, 40)
    b.StateBorder = BLZ.atex(b, nil, 'ARTWORK', 'talents-node-square-green', 40, 40)
    b.Icon = BLZ.tex(b, nil, 'BORDER')
    b.nodeInfo = { currentRank = 1, maxRanks = 4, ranksPurchased = 1 }
    PlayerSpellsFrame.TalentsFrame:Hide(); PlayerSpellsFrame.TalentsFrame:Show(); FlushTimers()
    assert(nrec('Latecomer') and nrec('Latecomer').chip.text:GetText() == '1/4', 'late button not met')
    assert(is(nrec('Latecomer').plate.ring.vertex, VIOLET), 'late button not painted')
""")

case("the arrows between nodes: a solid line and a bright head in the palette, thick enough to read, the ghost parts stay stock", OPEN + PRE + """
    local g, y, l, r = _G.EdgeGray, _G.EdgeYellow, _G.EdgeLocked, _G.EdgeRed
    for _, e in ipairs({ g, y, l, r }) do
        assert(e.Line.color and e.Line.color[4] == 1, 'line is not a solid colour')
        assert(e.Line.thickness and e.Line.thickness < 6 / 1.2 + 0.01 and e.Line.thickness >= 1.5 / 1.2 - 0.01, 'line thickness ' .. tostring(e.Line.thickness))
        assert(e.ArrowHead.desat == true and e.ArrowHead.alpha == 1 and e.ArrowHead.vertex[4] == 1, 'head not tinted and visible')
        assert(e.ArrowHead.atlas:find('yellow'), 'head art is not the bright one: ' .. tostring(e.ArrowHead.atlas))
        assert(e.GhostLine.color == nil and e.GhostLine.vertex == nil and e.GhostArrowHead.vertex == nil, 'ghost parts touched')
        assert(math.max(e.Line.color[1], e.Line.color[2], e.Line.color[3]) >= 0.55, 'line too dark to read')
    end
    assert(is(y.Line.color, CYAN) and is(y.ArrowHead.vertex, CYAN), 'learned path is not cyan')
    assert(is(r.Line.color, PINK) and is(r.ArrowHead.vertex, PINK), 'refund path is not pink')
    assert(g.Line.color[3] > g.Line.color[2] and g.Line.color[1] > 0.3, 'idle edge is not violet')
    assert(lum(g.Line.color) > lum(DIM) + 0.05, 'idle edge is no brighter than the dim edge colour')
    assert(lum(l.Line.color) > lum(DIM) and lum(l.Line.color) < lum(g.Line.color), 'locked edge sits between dim and idle')
    assert(y.Line.thickness > g.Line.thickness, 'the lit path is not the thicker one')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("an arrow follows the stock state swap (UpdateState or a bare SetAtlas)", OPEN + PRE + """
    local e = _G.EdgeGray
    e.state = 'yellow'; e:UpdateState()
    assert(is(e.Line.color, CYAN) and is(e.ArrowHead.vertex, CYAN), 'arrow did not follow to the lit colour')
    e.Line:SetAtlas('talents-arrow-line-red')
    assert(is(e.Line.color, PINK), 'line did not follow a bare atlas swap')
    e.state = 'locked'; e:UpdateState()
    assert(not is(e.Line.color, PINK) and not is(e.Line.color, CYAN), 'line stuck on the old state')
    assert(e.ArrowHead.atlas:find('yellow'), 'the head art was left on a dim atlas')
""")

case("an arrow the pool hands out later is met on the next refresh; a talent button is not mistaken for one", OPEN + PRE + """
    local e = BLZ.edge('EdgeLate', 'yellow')
    PlayerSpellsFrame.TalentsFrame:Hide(); PlayerSpellsFrame.TalentsFrame:Show(); FlushTimers()
    assert(e.Line.color and is(e.Line.color, CYAN), 'late arrow not painted')
    assert(_G.Riptide.Line == nil and nrec('Riptide') and not FS.TalentsSkin.state.edges[_G.Riptide])
""")

case("the stock frame art, the class paintings and the divider rules are gone; no rule is drawn on the talent frame", OPEN + PRE + """
    local tf = PlayerSpellsFrame.TalentsFrame
    for _, k in ipairs({ 'Background', 'BackgroundBorder', 'DividerHorizontalLeft', 'DividerHorizontalRight', 'DividerVerticalLeft',
        'DividerVerticalRight', 'Clouds1', 'AirParticlesFar', 'ClassBackground', 'BackgroundFlash', 'OverlayBackgroundRight', 'OverlayBackgroundMid' }) do
        assert(tf[k].alpha == 0, k .. ' not held')
    end
    for _, rec in ipairs(FS.TalentsSkin.state.rules) do assert(rec.host ~= tf, 'a line is still drawn on the talent frame') end
    for _, h in ipairs(heads(tf)) do
        for _, rec in ipairs(FS.TalentsSkin.state.rules) do assert(rec.host ~= h, 'a line is still drawn on a spec header') end
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("three tree panels fill the gaps the stock dividers marked: inside the inner frame, apart from each other, each around its header and nodes", OPEN + PRE + """
    local tf = PlayerSpellsFrame.TalentsFrame
    local cols = FS.TalentsSkin.state.cols
    assert(cols and #cols == 3, 'three panels')
    local inner = rect(tf.BackgroundBorder)
    local hs = heads(tf)
    table.sort(hs, function(a, b) return a:Rect() < b:Rect() end)
    for i, c in ipairs(cols) do
        local r = rect(c.frame)
        assert(r.r > r.l + 100 and r.b > r.t + 100, 'panel ' .. i .. ' has no size')
        assert(inside(r, inner), 'panel ' .. i .. ' leaves the inner frame')
        assert(inside(rect(hs[i]), r, 0.5), 'header ' .. i .. ' is not inside panel ' .. i)
        assert(c.frame.level <= tf.level, 'a panel must not sit above the talent buttons')
        for _, d in ipairs({ tf.DividerVerticalLeft, tf.DividerVerticalRight }) do assert(not overlap(rect(d), r), 'panel ' .. i .. ' covers a stock divider') end
        if cols[i + 1] then assert(r.r < rect(cols[i + 1].frame).l - 2, 'panels ' .. i .. ' and ' .. (i + 1) .. ' touch') end
    end
    local first = rect(cols[1].frame)
    assert(inside(rect(_G.Riptide), first), 'the first tree\\'s nodes are inside its panel')
    -- the tree with points is lit, the others are dim
    assert(is(cols[2].plate.ring.vertex, VIOLET) and is(cols[1].plate.ring.vertex, DIM) and is(cols[3].plate.ring.vertex, DIM), 'the spent tree is lit')
    -- a panel follows the stock size when the frame is re-laid out
    tf.BackgroundBorder.w = 1100
    tf:RunScript('OnSizeChanged')
    FlushTimers()
    assert(rect(cols[3].frame).r <= rect(tf.BackgroundBorder).r + 0.02, 'panel did not follow the inner frame')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("spec headers: a tidy row of square icon, name and a points chip; nothing crosses the icon, nothing overlaps", OPEN + PRE + """
    local tf = PlayerSpellsFrame.TalentsFrame
    local hs = heads(tf)
    assert(#hs == 3)
    for i, h in ipairs(hs) do
        local rec = FS.TalentsSkin.state.specs[h]
        for _, k in ipairs({ 'MainRing', 'TextBackground', 'Divider' }) do assert(h[k].alpha == 0, 'header ' .. i .. ' ' .. k .. ' kept') end
        assert(h.Icon.maskRemoved, 'icon keeps its round mask')
        local icon, plate = rect(h.Icon), rect(rec.plate.fill)
        assert(plate.l < icon.l and plate.r > icon.r and plate.t < icon.t and plate.b > icon.b, 'the icon plate does not surround the icon')
        local name, chip, text = rect(h.Name), rect(rec.chip.fill), rect(h.Text)
        assert(name.l >= plate.r + 2, 'the name starts on the icon')
        assert(not overlap(name, plate) and not overlap(chip, plate) and not overlap(chip, name), 'header parts overlap')
        assert(chip.l >= name.r + 4 and chip.l < name.r + 40, 'the chip is not next to the name')
        assert(inside(text, chip, 0.3), 'the count spills out of its chip')
        assert(near((chip.t + chip.b) / 2, (icon.t + icon.b) / 2, 3), 'chip is off the icon row')
        assert(near((name.t + name.b) / 2, (icon.t + icon.b) / 2, 3), 'name is off the icon row')
        assert(h.Name.fontPath ~= 'stock.ttf' and h.Text.fontPath ~= 'stock.ttf', 'texts not mono')
    end
    assert(is(FS.TalentsSkin.state.specs[hs[2]].plate.ring.vertex, CYAN), 'icon ring is not cyan')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("the points chip is amber while the tree has points, muted at zero, and follows the stock count", OPEN + PRE + """
    local hs = heads(PlayerSpellsFrame.TalentsFrame)
    local zero, spent = FS.TalentsSkin.state.specs[hs[1]], FS.TalentsSkin.state.specs[hs[2]]
    assert(is(spent.chip.edges[1].color, AMBER) and is(hs[2].Text.textColor, AMBER), 'chip with points is not amber')
    assert(is(zero.chip.edges[1].color, DIM) and is(hs[1].Text.textColor, MUTED), 'empty chip is not muted')
    hs[1].Text:SetText('7')
    assert(is(zero.chip.edges[1].color, AMBER) and is(hs[1].Text.textColor, AMBER), 'chip did not follow a new count')
    hs[1].Text:SetTextColor(1, 0.82, 0, 1)
    assert(hs[1].Text.textColor[3] < 0.35 and hs[1].Text.textColor[1] > 0.9, 'count colour not pinned')
    hs[1].Text:SetText('0')
    assert(is(hs[1].Text.textColor, MUTED), 'chip did not fall back to muted')
    hs[1].Name:SetTextColor(1, 0.82, 0, 1)
    assert(hs[1].Name.textColor[1] < 0.95, 'name colour not pinned')
""")

case("the Unspent Talents box wraps its label and its number, the stock box art is held, the number lights when points are unspent", OPEN + PRE + """
    local cur = PlayerSpellsFrame.TalentsFrame.ClassCurrencyDisplay
    local rec = FS.TalentsSkin.state.currency
    assert(cur.Border.alpha == 0, 'stock box kept')
    local label, amount = cur.UnspentLabel, cur.CurrentAmountContainer.CurrencyAmount
    assert(label.fontPath ~= 'stock.ttf' and amount.fontPath ~= 'stock.ttf', 'texts not mono')
    local box, l, a = rect(rec.fill), rect(label), rect(amount)
    assert(box.l <= l.l - 4 / 1.2 + 0.05, 'the label starts outside the box: box ' .. box.l .. ' label ' .. l.l)
    assert(box.r >= a.r + 4 / 1.2 - 0.05, 'the number ends outside the box')
    assert(box.t <= a.t and box.b >= a.b and box.t <= l.t and box.b >= l.b, 'the text is taller than the box')
    assert(box.r - box.l < 160, 'box is not fitted to its text')
    for _, e in ipairs(rec.edges) do assert(e:IsShown()) end
    assert(is(amount.textColor, MUTED), 'zero is not muted')
    amount:SetText('3')
    assert(is(amount.textColor, AMBER) and is(rec.edges[1].color, AMBER), 'unspent points do not light the number and the box')
    amount:SetTextColor(0.5, 0.5, 0.5, 1)
    assert(is(amount.textColor, AMBER), 'number colour not pinned')
    assert(is(label.textColor, MUTED), 'label colour')
    -- the box still fits when the label grows
    label:SetText('Unspent Talent Points')
    PlayerSpellsFrame.TalentsFrame:Hide(); PlayerSpellsFrame.TalentsFrame:Show(); FlushTimers()
    local grown, l2 = rect(rec.fill), rect(label)
    assert(grown.l <= l2.l - 3 and grown.r - grown.l > box.r - box.l, 'box did not grow with its label')
""")

case("the Primary and Secondary tabs: the stock check and lock are replaced by our glyphs, and each tab fits its text", OPEN + PRE + """
    local ts = PlayerSpellsFrame.TalentsFrame.TabSystem
    local P, S2 = ts.primary, ts.secondary
    local rp, rs = FS.TalentsSkin.state.tabs[P], FS.TalentsSkin.state.tabs[S2]
    assert(rp and rs, 'tabs not met')
    for _, t in ipairs({ P, S2 }) do
        local text = t.Text:GetText()
        assert(not text:find('|A', 1, true) and not text:find('|c', 1, true) and not text:find('|r', 1, true), 'markup left in the label: ' .. text)
    end
    assert(P.Text:GetText() == 'Primary' and S2.Text:GetText() == 'Secondary', 'label text changed beyond the markup')
    assert(rp.glyph:IsShown() and rp.glyph.path:find('ctl_tick') and is(rp.glyph.vertex, CYAN), 'the active tab has no cyan tick')
    assert(rs.glyph:IsShown() and rs.glyph.path:find('ctl_lock') and is(rs.glyph.vertex, T.COLOR_CTRL_DIS), 'the locked tab has no dim lock')
    for _, t in ipairs({ P, S2 }) do
        local g, label, tab = rect(FS.TalentsSkin.state.tabs[t].glyph), rect(t.Text), rect(t)
        assert(g.l >= label.r + 0.5 and not overlap(g, label), 'glyph overlaps the label')
        assert(inside(label, tab, 0) and inside(g, tab, 0), 'text or glyph outside the tab')
        local slack = (tab.r - tab.l) - (g.r - label.l)
        assert(slack >= 20 and slack < 70, 'tab does not fit its text: spare ' .. slack)
        assert(t.w < 150 and t.w > 60, 'tab width ' .. t.w)
    end
    assert(ts.dirty and ts.dirty >= 1, 'the tab layout was not asked to re-flow')
    -- the stock code writes the markup again (SetTabEnabled): it is cleaned again
    S2:SetTabEnabled(false)
    assert(S2.Text:GetText() == 'Secondary', 'a stock text write brought the markup back: ' .. S2.Text:GetText())
    P:SetTabEnabled(true)
    assert(P.Text:GetText() == 'Primary' and rp.glyph:IsShown(), 'the tick was lost on a stock write')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("with TabSkins on the tabs (its mono font, its label seat, its width fit) the tabs still fit their text, the glyph stays clear of the label and the layout settles", OPEN + PRE + """
    local tf = PlayerSpellsFrame.TalentsFrame
    local ts = BLZ.blz('Frame', nil, tf, 301, 32, 'TOPLEFT', 40, -4)
    local tabs = {}
    local function tabOf(x, text)
        local b = BLZ.blz('Button', nil, ts, 150, 32, 'TOPLEFT', x, 0)
        for _, key in ipairs({ 'LeftActive', 'RightActive', 'MiddleActive', 'Left', 'Right', 'Middle', 'LeftHighlight', 'MiddleHighlight', 'RightHighlight' }) do
            b[key] = BLZ.tex(b, nil, 'BACKGROUND'); b[key].atlas = 'uiframe-tab-' .. key:lower()
        end
        b.Text = BLZ.fstring(b, nil, text, 12)
        b.Text.points[1] = { point = 'CENTER', rel = b, relPoint = 'CENTER', x = 0, y = 2 }
        b.Text.w = 140
        b.tabText = text
        b.isSelected = false
        function b:SetTabSelected(sel) self.isSelected = sel; self.Left:SetShown(not sel); self.LeftActive:SetShown(sel); self.Text:SetPoint('CENTER', self, 'CENTER', 0, sel and -3 or 2) end
        function b:SetTabEnabled(on) self.Text:SetText(on and self.tabText or ('|cff808080' .. self.tabText .. '|r')) end
        function b:UpdateTabWidth() self.Text:SetWidth(140); self:SetWidth(150) end
        b.scripts.OnClick = function() end
        tabs[#tabs + 1] = b
        return b
    end
    local P = tabOf(0, 'Primary |A:Talents-Checkmark-c60:15:20:0:0|a')
    local S2 = tabOf(151, '|cff808080Secondary |A:Talents-lock-c60:14:10:0:0|a|r')
    P:SetTabSelected(true)
    for _, b in ipairs(tabs) do FS.TabSkins.Skin(b) end
    assert(FS.TabSkins.Parts(P) and FS.TabSkins.Parts(S2), 'TabSkins did not take the tabs')
    tf.TabSystem = ts
    tf:Hide(); tf:Show(); FlushTimers()
    local function settle()
        P:RunScript('OnEnter'); P:RunScript('OnLeave'); S2:RunScript('OnEnter'); S2:RunScript('OnLeave')
        P:SetTabSelected(true); S2:SetTabEnabled(false); P:UpdateTabWidth(); S2:UpdateTabWidth()
        FlushTimers()
    end
    settle()
    local w1, w2 = P.w, S2.w
    for _ = 1, 4 do settle() end
    assert(near(P.w, w1, 0.01) and near(S2.w, w2, 0.01), 'tab widths keep moving: ' .. w1 .. ' -> ' .. P.w .. ', ' .. w2 .. ' -> ' .. S2.w)
    for _, t in ipairs({ P, S2 }) do
        local rec = FS.TalentsSkin.state.tabs[t]
        local label, tab, g = rect(t.Text), rect(t), rect(rec.glyph)
        assert(not t.Text:GetText():find('|', 1, true), 'markup left: ' .. t.Text:GetText())
        assert(rec.glyph:IsShown() and not overlap(g, label) and g.l >= label.r - 0.01, 'glyph on the label')
        assert(inside(label, tab, 0.01) and inside(g, tab, 0.01), 'text or glyph outside the tab')
        local left, right = label.l - tab.l, tab.r - g.r
        assert(near(left, right, 2.5), 'label and glyph are not centred as one: ' .. left .. ' vs ' .. right)
        assert(tab.r - tab.l < 150 / 1.2 + 1 and tab.r - tab.l > 60, 'tab width ' .. (tab.r - tab.l))
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("minimise and maximise wear the close button's key in cyan beside the close button and keep their click", f"""
    {OPEN}
    local mm = PlayerSpellsFrame.MaximizeMinimizeButton
    local close = PlayerSpellsFrame.CloseButton
    for _, b in ipairs({{ mm.MinimizeButton, mm.MaximizeButton }}) do
        assert(b.regions[1].alpha == 0, 'stock art kept')
        assert(b.scripts.OnClick, 'click lost')
        local pt = b.points[1]
        assert(pt and pt.point == 'RIGHT' and pt.rel == close and pt.relPoint == 'LEFT', 'not seated beside the close button')
    end
    local cells = FS.ButtonSkins.GlyphCells('max')
    assert(#cells == 6 * 3 + 3 * 2, 'window glyph: two title rows, a bottom row, two sides')
""")

case("spellbook: parchment held, dark text lifted, state colour kept, tab frames held", f"""
    {OPEN}
    local book = PlayerSpellsFrame.SpellBookFrame
    book:Show(); FlushTimers()
    assert(book.BookBGLeft.alpha == 0 and book.BookBGRight.alpha == 0 and book.BookCornerFlipbook.alpha == 0, 'page art')
    assert(book.dark.textColor[1] > 0.6, 'dark text not lifted ' .. book.dark.textColor[1])
    assert(book.state.textColor[1] > 0.9 and book.state.textColor[2] < 0.3, 'state colour was repainted')
    local tab = book.tabSystem.children[1]
    assert(tab.SquareBackground.alpha == 0 and tab.SquareBackgroundActive.alpha == 0, 'tab frame')
""")


ENTRIES = "PlayerSpellsFrame.SpellBookFrame.PagedSpellsFrame.View1.children"

case("spellbook entries: the stock backplate, icon frame and sheen are held, a cut card stands behind each, the icon is a slot", f"""
    {OPEN}
    local book = PlayerSpellsFrame.SpellBookFrame
    book:Show(); FlushTimers()
    local I = FS.TalentsSkin.state.items
    local n = 0
    for _, it in ipairs({ENTRIES}) do
        if it.Button then
            n = n + 1
            assert(it.Backplate.alpha == 0, 'backplate kept')
            for _, k in ipairs({{ 'Border', 'TrainableBackplate', 'TrainableShadow', 'BorderSheen', 'IconHighlight' }}) do
                assert(it.Button[k].alpha == 0, k .. ' kept')
            end
            local rec = I[it]
            assert(rec and rec.plate and rec.plate.fill.alpha ~= 0 and rec.plate.ring.alpha ~= 0, 'no card')
            assert(FS.QuestSkin.state.squares[it.Button], 'icon button is not on the slot layer')
            assert(FS.ItemSlotSkins.Parts(it.Button), 'slot layer not built')
            assert(it.Button.scripts.OnClick and it.Button.scripts.OnEnter, 'stock script lost')
        end
    end
    assert(n == 4, 'entries met: ' .. n)
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\\\n'))
""")

case("spellbook entries: edge by state, texts mono and lifted, level text amber or pink", f"""
    {OPEN}
    PlayerSpellsFrame.SpellBookFrame:Show(); FlushTimers()
    local I = FS.TalentsSkin.state.items
    local T = FS.Theme
    local items = {ENTRIES}
    local learned, passive, train, locked = items[2], items[3], items[4], items[5]
    local function edge(it) local v = I[it].plate.ring.vertex; return v end
    local function is(v, c) return Near(v[1], c[1], 0.02) and Near(v[2], c[2], 0.02) and Near(v[3], c[3], 0.02) end
    assert(is(edge(learned), T.COLOR_BORDER) and edge(learned)[4] < 1, 'learned: violet edge, not full')
    assert(is(edge(passive), T.COLOR_POWER), 'passive: cyan edge')
    assert(is(edge(train), T.COLOR_HEALTH), 'trainable: pink edge')
    assert(is(edge(locked), T.COLOR_CTRL_DIM), 'level locked: dim edge')
    assert(learned.Name.fontPath ~= 'stock.ttf' and learned.SubName.fontPath ~= 'stock.ttf', 'texts not mono')
    assert(learned.Name.textColor[1] > 0.6, 'dark name not lifted')
    assert(Near(learned.SubName.textColor[1], T.COLOR_MUTED[1], 0.02), 'sub text not muted')
    assert(train.RequiredLevel.textColor[1] > 0.9 and train.RequiredLevel.textColor[2] < 0.3, 'train text not pink')
    assert(locked.RequiredLevel.textColor[1] > 0.9 and locked.RequiredLevel.textColor[2] > 0.6 and locked.RequiredLevel.textColor[3] < 0.4, 'level text not amber')
    assert(locked.Name.textColor[1] < 0.8, 'locked name should be muted')
    assert(train.Name.textColor[1] > 0.9 and train.Name.textColor[2] < 0.3, 'train name not pink')
    learned.Name:SetTextColor(0.1, 0.1, 0.1, 1)
    assert(learned.Name.textColor[1] > 0.6, 'name colour not pinned')
""")

case("spellbook entries: hover on the icon lights the card, the stock repaint (UpdateVisuals) follows a state change", f"""
    {OPEN}
    PlayerSpellsFrame.SpellBookFrame:Show(); FlushTimers()
    local I = FS.TalentsSkin.state.items
    local it = {ENTRIES}[2]
    local rest = I[it].plate.fill.vertex[1]
    local restEdge = I[it].plate.ring.vertex[1]
    it.Button:RunScript('OnEnter')
    assert(I[it].plate.fill.vertex[1] > rest or I[it].plate.ring.vertex[1] > restEdge, 'hover did not light the card')
    it.Button:RunScript('OnLeave')
    assert(Near(I[it].plate.fill.vertex[1], rest) and Near(I[it].plate.ring.vertex[1], restEdge), 'hover stuck')
    it.isTrainable, it.isUnlearned = true, true
    it:UpdateVisuals()
    assert(Near(I[it].plate.ring.vertex[1], FS.Theme.COLOR_HEALTH[1], 0.02) and Near(I[it].plate.ring.vertex[2], FS.Theme.COLOR_HEALTH[2], 0.02), 'stock repaint did not move the edge')
    it.isTrainable, it.isUnlearned = false, false
    it:UpdateVisuals()
    assert(Near(I[it].plate.ring.vertex[1], FS.Theme.COLOR_BORDER[1], 0.02), 'edge did not return')
""")

case("spellbook entries: a state the stock code leaves unreadable is read as plain, a secret value does not throw", f"""
    {OPEN}
    PlayerSpellsFrame.SpellBookFrame:Show(); FlushTimers()
    local it = {ENTRIES}[2]
    it.isTrainable = Secret(); it.isUnlearned = Secret(); it.spellBookItemInfo = Secret()
    it:UpdateVisuals()
    assert(Near(FS.TalentsSkin.state.items[it].plate.ring.vertex[1], FS.Theme.COLOR_BORDER[1], 0.02), 'a secret state must read as the plain learned look')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\\\n'))
""")

case("spellbook entries: a frame the pool hands out later is met when the pages redisplay; headers get a rule and mono text", f"""
    {OPEN}
    local book = PlayerSpellsFrame.SpellBookFrame
    book:Show(); FlushTimers()
    local paged = book.PagedSpellsFrame
    local late = BLZ.entry(paged.View2, 'Late Spell', 0, 0)
    local head = BLZ.header(paged.View2, 'Racial', 0, -80)
    paged:DisplayViewsForCurrentPage(); FlushTimers()
    assert(late.Backplate.alpha == 0 and FS.TalentsSkin.state.items[late], 'late entry not met')
    assert(head.Backplate.alpha == 0 and head.Border.alpha == 0, 'header art kept')
    assert(head.Text.fontPath ~= 'stock.ttf' and head.Text.textColor[1] > 0.6, 'header text')
    local rules = 0
    for _, r in ipairs(FS.TalentsSkin.state.rules) do if r.host == head then rules = rules + 1 end end
    assert(rules == 1, 'header rule: ' .. rules)
    paged:DisplayViewsForCurrentPage(); FlushTimers()
    rules = 0
    for _, r in ipairs(FS.TalentsSkin.state.rules) do if r.host == head then rules = rules + 1 end end
    assert(rules == 1, 'header rule doubled: ' .. rules)
""")

case("spellbook paging: page keys are cut keys with a chevron, stock arrows held, text mono, disabled key dimmed", f"""
    {OPEN}
    local book = PlayerSpellsFrame.SpellBookFrame
    book:Show(); FlushTimers()
    local pc = book.PagedSpellsFrame.PagingControls
    local P = FS.QuestSkin.state.pagers
    assert(P[pc.PrevPageButton] and #P[pc.PrevPageButton].glyph == 9, 'prev key')
    assert(P[pc.NextPageButton] and #P[pc.NextPageButton].glyph == 9, 'next key')
    assert(pc.PrevPageButton.NormalTexture.alpha == 0, 'stock arrow kept')
    assert(pc.PrevPageButton.scripts.OnClick, 'click lost')
    assert(P[pc.PrevPageButton].glyph[1].alpha == 0.35, 'disabled key not dimmed')
    assert(pc.PageText.fontPath ~= 'stock.ttf', 'page text not mono')
""")

case("nothing is built in combat; it is built when combat ends", f"""
    Reset()
    __combat = true
    Load({{ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'Character', 'Talents' }})
    assert(not PlayerSpellsFrame.fsTalentsSkin, 'built in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(PlayerSpellsFrame.fsTalentsSkin, 'not built when combat ended')
""")

SCENES = {
    "talents": "Fire('PLAYER_ENTERING_WORLD'); Fire('ADDON_LOADED', 'Blizzard_PlayerSpells'); PlayerSpellsFrame:Show(); FlushTimers(); return DumpOps({ PlayerSpellsFrame })",
    "spellbook": ("Fire('PLAYER_ENTERING_WORLD'); Fire('ADDON_LOADED', 'Blizzard_PlayerSpells'); PlayerSpellsFrame:Show(); "
                  "PlayerSpellsFrame.TalentsFrame:Hide(); PlayerSpellsFrame.SpellBookFrame:Show(); FlushTimers(); "
                  "PlayerSpellsFrame.SpellBookFrame.PagedSpellsFrame.View1.children[2].Button:RunScript('OnEnter'); "
                  "return DumpOps({ PlayerSpellsFrame.SpellBookFrame })"),
}

if __name__ == "__main__":
    raise SystemExit(H.main("talents skin", SCENES))
