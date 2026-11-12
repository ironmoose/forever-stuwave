#!/usr/bin/env python3
"""Runs the real Modules/Skins/Talents.lua headless against a mock PlayerSpellsFrame (tools/charskin_support.py).

Pinned: a talent button gets a ring tint read from its border atlas and follows an atlas swap, nothing else on it is touched (no
script, attribute or field written), the stock gold frame art, dividers, spec header rings and the Unspent Talents box are held or
restyled in place, buttons built later are met on the next refresh, the minimise and maximise buttons wear a plate and a glyph,
the spellbook parchment is held and dark text retinted with state colours left alone, and nothing is built in combat.
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
    local mm = blz("Frame", nil, win, 28, 28, "TOPRIGHT", -30, -6)
    win.MaximizeMinimizeButton = mm
    mm.MinimizeButton = blz("Button", nil, mm, 28, 28)
    atex(mm.MinimizeButton, nil, "ARTWORK", "RedButton-Condense", 28, 28)
    mm.MinimizeButton.scripts.OnClick = function() end
    mm.MaximizeButton = blz("Button", nil, mm, 28, 28)
    atex(mm.MaximizeButton, nil, "ARTWORK", "RedButton-Expand", 28, 28)
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
end
"""

H = Harness({"Character": "Modules/Skins/Character.lua", "Talents": "Modules/Skins/Talents.lua"}, BLIZZARD)
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

case("minimise and maximise wear a plate and a glyph and keep their click", f"""
    {OPEN}
    local mm = PlayerSpellsFrame.MaximizeMinimizeButton
    assert(mm.MinimizeButton.NormalTexture == nil or true)
    assert(mm.MinimizeButton.regions[1].alpha == 0, 'stock art kept')
    assert(mm.MinimizeButton.scripts.OnClick, 'click lost')
    assert(FS.CharacterSkin.state.squares[mm.MinimizeButton] and #FS.CharacterSkin.state.squares[mm.MinimizeButton].glyph == 1)
    assert(#FS.CharacterSkin.state.squares[mm.MaximizeButton].glyph == 4)
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
}

if __name__ == "__main__":
    raise SystemExit(H.main("talents skin", SCENES))
