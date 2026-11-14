#!/usr/bin/env python3
"""Runs the real Modules/Skins/Talents.lua headless against a mock PlayerSpellsFrame (tools/charskin_support.py).

Pinned: a talent button gets a ring tint read from its border atlas and follows an atlas swap, nothing else on it is touched (no
script, attribute or field written), the stock gold frame art, dividers, spec header rings and the Unspent Talents box are held or
restyled in place, buttons built later are met on the next refresh, the minimise and maximise buttons wear the close button's key in cyan,
the spellbook parchment is held and dark text retinted with state colours left alone, each spell entry is a cut card whose edge
follows its state (learned, passive, trainable, level locked, hover) with its icon button on the shared slot layer and the page keys
of the paging controls cut keys, and nothing is built in combat.
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

    local tf = blz("Frame", nil, win, 1212, 681, "TOPLEFT", 3, -24)
    win.TalentsFrame = tf
    for key, atlas in pairs({ Background = "Talents-Background-c60", BackgroundBorder = "Talents-inner-frame-c60",
        DividerHorizontalLeft = "Talents-divider-left-c60", DividerHorizontalRight = "Talents-divider-right-c60",
        DividerVerticalLeft = "Talents-divider-vertical-c60", DividerVerticalRight = "Talents-divider-vertical-c60",
        Clouds1 = "talents-animations-clouds", Clouds2 = "talents-animations-clouds", AirParticlesClose = "talents-animations-particles",
        AirParticlesFar = "talents-animations-particles", ClassBackground = "talent-background-shaman" }) do
        tf[key] = atex(tf, nil, "BACKGROUND", atlas, 600, 400)
    end
    tf.BackgroundBorder.w, tf.BackgroundBorder.h = 1216, 603
    tf.ButtonsParent = blz("Frame", nil, tf, 1212, 641, "TOPLEFT", 0, 0)
    local function node(name, atlas, x, y)
        local b = blz("Button", name, tf.ButtonsParent, 40, 40, "TOPLEFT", x, y)
        b.Shadow = atex(b, nil, "BACKGROUND", "talents-node-square-shadow", 78, 78)
        b.Icon = tex(b, nil, "BORDER")
        b.StateBorder = atex(b, nil, "ARTWORK", atlas, 40, 40)
        b.StateBorderHover = atex(b, nil, "ARTWORK", atlas, 40, 40)
        b.Glow = atex(b, nil, "OVERLAY", "talents-node-square-greenglow", 84, 84)
        b.StateBorder.SetDesaturated = function(self, v) self.desat = v end
        b.StateBorderHover.SetDesaturated = function(self, v) self.desat = v end
        b.Glow.SetDesaturated = function(self, v) self.desat = v end
        b.scripts.OnClick = function() end
        b.scripts.OnEnter = function() end
        return b
    end
    node("Riptide", "talents-node-square-locked", 60, 60)
    node("Purification", "talents-node-square-gray", 120, 60)
    node("Healing Way", "talents-node-square-yellow", 180, 60)
    node("Tidal Focus", "talents-node-square-green", 240, 60)
    -- the arrows between nodes (TalentEdgeArrowTemplate): a Line and an ArrowHead whose atlas the stock UpdateState swaps by state
    EDGES = {}
    function BLZ.edge(name, state)
        local e = blz("Frame", name, tf.ButtonsParent, 60, 6, "TOPLEFT", 100, -80)
        e.state = state
        e.Line = atex(e, nil, "OVERLAY", "talents-arrow-line-" .. state, 60, 6)
        e.ArrowHead = atex(e, nil, "OVERLAY", "talents-arrow-head-" .. state, 12, 12)
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
    for i, spec in ipairs({ { "Elemental Combat", 0 }, { "Enhancement", 13 }, { "Restoration", 0 } }) do
        local h = blz("Frame", nil, tf, 48, 48, "TOPLEFT", 80 + (i - 1) * 400, -40)
        h.Icon = tex(h, nil, "BORDER")
        h.MainRing = atex(h, nil, "OVERLAY", "Talents-Main-Ring-c60", 55, 55)
        h.TextBackground = atex(h, nil, "OVERLAY", "Talents-Main-Ring-Box-c60", 24, 20)
        h.Divider = atex(h, nil, "OVERLAY", "Talents-small-divider-c60", 355, 64)
        h.Name = fstring(h, nil, spec[1], 14, { 1, 0.82, 0, 1 })
        h.Text = fstring(h, nil, tostring(spec[2]), 11, { 1, 0.82, 0, 1 })
        h.MainRing.SetDesaturated = function(self, v) self.desat = v end
    end
    local cur = blz("Frame", nil, tf, 160, 45, "TOPRIGHT", -20, -10)
    tf.ClassCurrencyDisplay = cur
    cur.Border = atex(cur, nil, "ARTWORK", "Talents-Square-Box-c60", 125, 45)
    cur.UnspentLabel = fstring(cur, nil, "Unspent Talents", 12, { 1, 1, 1, 1 })
    cur.CurrentAmountContainer = blz("Frame", nil, cur, 48, 36)
    cur.CurrentAmountContainer.CurrencyAmount = fstring(cur.CurrentAmountContainer, nil, "0", 22, { 1, 1, 1, 1 })

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

case("a talent button gets a ring tint by its border atlas, and only that", f"""
    local before = {{}}
    {OPEN}
    local function node(n) return _G[n] end
    local locked, gray, yellow, green = node('Riptide'), node('Purification'), node('Healing Way'), node('Tidal Focus')
    assert(locked.StateBorder.vertex[3] > locked.StateBorder.vertex[1] and locked.StateBorder.vertex[1] < 0.4, 'locked not dim violet')
    assert(gray.StateBorder.vertex[1] < 0.4, 'gray not dim')
    assert(yellow.StateBorder.vertex[1] > 0.9 and yellow.StateBorder.vertex[3] < 0.3, 'yellow not amber')
    assert(green.StateBorder.vertex[2] > 0.8 and green.StateBorder.vertex[1] < 0.4, 'green not cyan')
    assert(yellow.StateBorder.desat == true, 'ring not desaturated')
    for _, b in ipairs({{ locked, gray, yellow, green }}) do
        assert(b.scripts.OnClick and b.scripts.OnEnter, 'stock script lost')
        assert(b.Icon.alpha == 1 and b.Shadow.alpha == 1, 'something other than the ring was touched')
        assert(b.StateBorder.alpha == 1, 'the ring itself is not held, it is tinted')
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\\\n'))
""")

case("a state swap by the stock code repaints the ring", f"""
    {OPEN}
    local b = _G['Riptide']
    b.StateBorder:SetAtlas('talents-node-square-green')
    assert(b.StateBorder.vertex[2] > 0.8, 'ring did not follow the atlas swap')
    b.StateBorder:SetAtlas('talents-node-square-yellow')
    assert(b.StateBorder.vertex[1] > 0.9 and b.StateBorder.vertex[3] < 0.3, 'ring did not follow to amber')
""")

case("a button built later is met on the next refresh", f"""
    {OPEN}
    local nb = blz and nil
    local b = BLZ.blz('Button', 'Latecomer', PlayerSpellsFrame.TalentsFrame.ButtonsParent, 40, 40)
    b.StateBorder = BLZ.atex(b, nil, 'ARTWORK', 'talents-node-square-green', 40, 40)
    PlayerSpellsFrame.TalentsFrame:Hide(); PlayerSpellsFrame.TalentsFrame:Show(); FlushTimers()
    assert(b.StateBorder.vertex and b.StateBorder.vertex[2] > 0.8, 'late button not tinted')
""")

case("the arrows between nodes: line and arrow head take the state colour from their atlas, the ghost parts stay stock", f"""
    {OPEN}
    local function color(r) return r.vertex end
    local g, y, l, r = _G.EdgeGray, _G.EdgeYellow, _G.EdgeLocked, _G.EdgeRed
    for _, e in ipairs({{ g, y, l, r }}) do
        for _, part in ipairs({{ e.Line, e.ArrowHead }}) do
            assert(part.desat == true and part.alpha == 1, 'arrow part not desaturated and visible')
        end
        assert(e.GhostLine.vertex == nil and e.GhostArrowHead.vertex == nil, 'ghost parts touched')
    end
    assert(y.Line.vertex[1] > 0.9 and y.Line.vertex[3] < 0.3 and y.ArrowHead.vertex[1] > 0.9, 'active edge not amber')
    assert(g.Line.vertex[1] < 0.4 and l.ArrowHead.vertex[1] < 0.4 and g.ArrowHead.vertex[3] > g.ArrowHead.vertex[1], 'idle edge not dim violet')
    assert(r.Line.vertex[1] > 0.9 and r.Line.vertex[2] < 0.4 and r.ArrowHead.vertex[1] > 0.9, 'refund edge not pink')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\\\n'))
""")

case("an arrow follows the stock state swap (UpdateState or a bare SetAtlas)", f"""
    {OPEN}
    local e = _G.EdgeGray
    e.state = 'yellow'; e:UpdateState()
    assert(e.Line.vertex[1] > 0.9 and e.Line.vertex[3] < 0.3 and e.ArrowHead.vertex[1] > 0.9, 'arrow did not follow to amber')
    e.Line:SetAtlas('talents-arrow-line-red')
    assert(e.Line.vertex[1] > 0.9 and e.Line.vertex[2] < 0.4, 'line did not follow a bare atlas swap')
""")

case("an arrow the pool hands out later is met on the next refresh; a talent button is not mistaken for one", f"""
    {OPEN}
    local e = BLZ.edge('EdgeLate', 'yellow')
    PlayerSpellsFrame.TalentsFrame:Hide(); PlayerSpellsFrame.TalentsFrame:Show(); FlushTimers()
    assert(e.Line.vertex and e.Line.vertex[1] > 0.9, 'late arrow not tinted')
    assert(_G.Riptide.Line == nil and _G.Riptide.StateBorder.alpha == 1)
""")

case("the gold frame art, dividers and clouds are held; violet rules stand in; the class art stays", f"""
    {OPEN}
    local tf = PlayerSpellsFrame.TalentsFrame
    for _, k in ipairs({{ 'Background', 'BackgroundBorder', 'DividerHorizontalLeft', 'DividerVerticalLeft', 'Clouds1', 'AirParticlesFar' }}) do
        assert(tf[k].alpha == 0, k .. ' not held')
    end
    assert(tf.ClassBackground.alpha == 1, 'the class art must stay')
    assert(#FS.TalentsSkin.state.rules >= 4, 'no dividers drawn')
""")

case("spec headers: gold ring desaturated to cyan, count box amber, mono name", f"""
    {OPEN}
    local tf = PlayerSpellsFrame.TalentsFrame
    local head
    for _, ch in ipairs({{ tf:GetChildren() }}) do if ch.MainRing then head = ch break end end
    assert(head.TextBackground.alpha == 0 and head.Divider.alpha == 0, 'stock count box or divider kept')
    assert(head.MainRing.desat and head.MainRing.vertex[2] > 0.8, 'ring not cyan')
    assert(head.Name.fontPath ~= 'stock.ttf', 'name not mono')
    head.Name:SetTextColor(1, 0.82, 0, 1)
    assert(head.Name.textColor[1] < 0.95, 'name colour not pinned')
    assert(head.Text.textColor[1] > 0.9 and head.Text.textColor[3] < 0.3, 'count not amber')
""")

case("the Unspent Talents box is ours: stock border held, mono texts", f"""
    {OPEN}
    local cur = PlayerSpellsFrame.TalentsFrame.ClassCurrencyDisplay
    assert(cur.Border.alpha == 0, 'border kept')
    assert(cur.UnspentLabel.fontPath ~= 'stock.ttf' and cur.CurrentAmountContainer.CurrencyAmount.textColor[1] > 0.9, 'texts')
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
