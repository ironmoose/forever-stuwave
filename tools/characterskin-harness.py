#!/usr/bin/env python3
"""Runs the real Modules/Skins/Character.lua headless against a mock CharacterFrame (tools/charskin_support.py).

Pinned: the header band and its switch (character / reputation / currency) drive the stock tabs, the stock tabs are held, every
equipment slot wears the shared item slot with a wear bar of the right height and colour, no slot is moved or given a script or
attribute, the stat rows keep their scripts and take mono text, the footer chips read plain values and hide for a secret or a
missing one, and nothing is built in combat. Run `python3 tools/characterskin-harness.py [--png /tmp/char]`.
The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

# the stock equipment flyout (Blizzard_FrameXML/EquipmentFlyout.xml): the highlight ring, the leather strip, the page frame and
# the item buttons the stock code makes the first time they are needed (EquipmentFlyout_UpdateItems)
BLIZZARD = r"""
local blz, tex, fstring, atex = BLZ.blz, BLZ.tex, BLZ.fstring, nil
local build = BuildBlizzard
function BuildBlizzard()
    build()
    atex = BLZ.atex
    for k in pairs(_G) do if type(k) == "string" and k:find("^EquipmentFlyout") then _G[k] = nil end end
    -- Blizzard_FrameXML/EquipmentFlyout.lua + .xml: the frame is seated on the slot it opened from (Show re-anchors it), the strip
    -- frame goes right of the slot (paper doll settings anchorX 0, anchorY -3) and is sized by the item count (37 px buttons 4 apart,
    -- five to a row), and the navigation frame (214 x 41) hangs under the strip at x -5, its PREVIOUS text anchored LEFT 36 and its
    -- NEXT text RIGHT -33, its keys LEFT 6 and RIGHT -3 (32 x 32)
    local fly = blz("Frame", "EquipmentFlyoutFrame", UIParent, 43, 43, "TOPLEFT", 60, -100)
    fly.shown = false
    fly.buttons = {}
    fly.Highlight = tex(fly, nil, "OVERLAY")
    fly.Highlight.w, fly.Highlight.h = 50, 50
    fly.Highlight.SetDesaturated = function(self, v) self.desat = v end
    local bf = blz("Frame", "EquipmentFlyoutFrameButtons", fly, 43, 43, "TOPLEFT", 40, 0)
    fly.buttonFrame = bf
    bf.numBGs = 1
    bf.bg1 = tex(bf, nil, "BACKGROUND")
    bf.bg1.w, bf.bg1.h = 60, 50
    local nav = blz("Frame", nil, fly, 214, 41, "TOPLEFT", 35, -43)
    fly.NavigationFrame = nav
    nav.BottomBackground = tex(nav, nil, "BACKGROUND")
    nav.BottomBackground.w, nav.BottomBackground.h = 214, 41
    local prevText = fstring(nav, nil, "PREVIOUS", 10, { 1, 1, 1, 1 })
    prevText.points[1] = { point = "LEFT", rel = nav, relPoint = "LEFT", x = 36, y = -1 }
    local nextText = fstring(nav, nil, "NEXT", 10, { 1, 1, 1, 1 })
    nextText.points[1] = { point = "RIGHT", rel = nav, relPoint = "RIGHT", x = -33, y = -1 }
    nextText.justify = "RIGHT"
    for _, key in ipairs({ "PrevButton", "NextButton" }) do
        local b = blz("Button", nil, nav, 32, 32, key == "PrevButton" and "LEFT" or "RIGHT", key == "PrevButton" and 6 or -3, -1)
        b.NormalTexture = tex(b, nil, "ARTWORK")
        b.GetNormalTexture = function(self) return self.NormalTexture end
        b.scripts.OnClick = function() end
        nav[key] = b
    end
    -- the stock UpdateItems: a button per item (made once, kept), one more strip texture per two buttons
    function EquipmentFlyout_UpdateItems()
        local n = fly.totalItems or 0
        for i = #fly.buttons + 1, n do
            local col, rowN = (i - 1) % 5, math.floor((i - 1) / 5)
            local b = blz("Button", "EquipmentFlyoutFrameButton" .. i, bf, 37, 37, "TOPLEFT", 3 + col * 41, -3 - rowN * 42)
            b.icon = tex(b, nil, "BORDER")
            b.icon.path = "Interface\\Icons\\inv_misc_" .. i
            b.icon.w, b.icon.h = 30, 30
            b.IconBorder = tex(b, nil, "OVERLAY")
            b.NormalTexture = tex(b, nil, "ARTWORK")
            b.Count = fstring(b, nil, "", 12)
            b.scripts.OnClick = function() end
            b.scripts.OnEnter = function() end
            fly.buttons[i] = b
        end
        local across = math.min(n, 5)
        bf.w = across * 37 + math.max(across - 1, 0) * 4 + 3
        bf.h = 43 + math.floor((math.max(n, 1) - 1) / 5) * 42
        while bf.numBGs < math.ceil(n / 2) + 1 do
            bf.numBGs = bf.numBGs + 1
            bf["bg" .. bf.numBGs] = tex(bf, nil, "BACKGROUND")
        end
        nav:SetShown(n > 8)
    end
    function EquipmentFlyout_Show(itemButton)
        fly.totalItems = fly.pending or 3
        fly.points[1] = { point = "TOPLEFT", rel = itemButton, relPoint = "TOPLEFT", x = -3, y = 3 }
        bf.points[1] = { point = "TOPLEFT", rel = itemButton, relPoint = "TOPRIGHT", x = 0, y = -3 }
        nav.points[1] = { point = "TOPLEFT", rel = bf, relPoint = "BOTTOMLEFT", x = -5, y = 0 }
        fly:Show()
        EquipmentFlyout_UpdateItems()
    end
end
"""

H = Harness({"Character": "Modules/Skins/Character.lua", "Quest": "Modules/Skins/Quest.lua"}, BLIZZARD)
case = H.case

# FS is already loaded (Theme ... TabSkins, Character) by the harness; this opens the window the way the client does.
OPEN = "Fire('PLAYER_ENTERING_WORLD'); CharacterFrame:Show(); FlushTimers()"

case("builds: chrome, header band over the stock top strip, no switch, the window one footer taller", f"""
    {OPEN}
    local S = FS.CharacterSkin.state
    assert(S.header and not S.header.switch, 'header or a leftover switch')
    assert(S.header.title.text == 'stuwave://character', S.header.title.text)
    local l, t, r, b = Px(S.header.band[1], CharacterFrame)
    local wl, wt, wr, wb = Px(CharacterFrame, CharacterFrame)
    assert(Near(l, 0) and Near(r, wr), 'band spans the window ' .. l .. ' ' .. r .. ' of ' .. wr)
    assert(b >= 24 and b <= 40, 'band height ' .. b)
    -- two anchors: a window that changes width drags the band along
    CharacterFrame.w = CharacterFrame.w + 100
    local l2, t2, r2 = Px(S.header.band[1], CharacterFrame)
    local _, _, wr2 = Px(CharacterFrame, CharacterFrame)
    assert(Near(r2, wr2), 'band did not follow the width')
    assert(CharacterFrame.fsCharacterSkin)
    assert(Near(CharacterFrame.h * PPU, math.floor(484 * PPU + 0.5) + 40, 0.01), 'window height ' .. CharacterFrame.h)
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("the stock title and portrait are held; no Inset is touched", f"""
    {OPEN}
    assert(CharacterFrameTitleText.alpha == 0)
    assert(CharacterFramePortrait.alpha == 0)
    CharacterFrameTitleText:SetAlpha(1)
    assert(CharacterFrameTitleText.alpha == 0, 'the hold survives a SetAlpha')
    assert(CharacterFrame.Inset == nil and CharacterFrame.InsetRight == nil, 'an Inset came back')
""")

case("the six mode tabs are restyled in place: held art, a plate, pink when selected, cyan on hover, stock scripts kept", f"""
    {OPEN}
    local S = FS.CharacterSkin.state
    for i = 1, 6 do
        local tab = _G['CharacterFrameModeTab' .. i]
        assert(S.tabs[tab], 'tab ' .. i .. ' not skinned')
        assert(tab.Background.alpha == 0 and tab.HighlightTexture.alpha == 0 and tab.TabGlow.alpha == 0, 'stock art ' .. i)
        assert(tab.SelectedTexture.alpha == 0, 'stock selected art ' .. i)
        assert(tab.Icon.alpha == 1, 'the icon must stay')
        assert(tab.scripts.OnMouseUp, 'stock click lost on tab ' .. i)
    end
    local function edge(i) return S.tabs[_G['CharacterFrameModeTab' .. i]].box.edges[1].color end
    assert(edge(1)[1] > 0.9 and edge(1)[2] < 0.4, 'selected tab edge not pink')
    assert(edge(2)[1] < 0.5 and edge(2)[3] < 0.7, 'idle tab edge not dim')
    -- a click the stock way moves the selection and the paint
    CharacterFrameModeTab3.scripts.OnMouseUp()
    assert(SkillsFrame:IsShown() and not PaperDollFrame:IsShown(), 'skills page not shown')
    assert(edge(3)[1] > 0.9 and edge(3)[2] < 0.4, 'selected paint did not follow')
    assert(edge(1)[1] < 0.5, 'the old tab kept the selected paint')
    for _, f in ipairs(CharacterFrameModeTab4.hooks.OnEnter) do f(CharacterFrameModeTab4) end
    assert(edge(4)[2] > 0.8, 'hover not cyan')
    for _, f in ipairs(CharacterFrameModeTab4.hooks.OnLeave) do f(CharacterFrameModeTab4) end
    assert(edge(4)[2] < 0.5, 'hover stuck')
""")

case("the title follows all six pages", f"""
    {OPEN}
    local S = FS.CharacterSkin.state
    local want = {{ 'character', 'reputation', 'skills', 'pvp', 'currency', 'statistics' }}
    for i = 1, 6 do
        _G['CharacterFrameModeTab' .. i].scripts.OnMouseUp()
        assert(S.header.title.text == 'stuwave://' .. want[i], i .. ' ' .. S.header.title.text)
    end
""")

case("the stock top strip, level line, pane art and divider are held, our own band under the strip", f"""
    {OPEN}
    local S = FS.CharacterSkin.state
    local strip = PaperDollFrame.TopBackgroundStripHost
    assert(strip.TopBackgroundStrip.alpha == 0 and strip.TopBackgroundStripBottomEdge.alpha == 0, 'strip art')
    assert(S.stripUnder, 'no band under the strip')
    assert(CharacterFrameLeftPaneHost.regions[1].alpha == 0, 'left pane art')
    assert(CharacterFrameRightPaneHost.regions[1].alpha == 0, 'right pane art')
    assert(CharacterFrameRightPaneHostStoneBg.alpha == 0, 'stone')
    assert(CharacterFrameRightPaneHost.children[1].regions[1].alpha == 0, 'stock divider')
    assert(S.rightUnder and S.rightDivider, 'no own right pane')
    assert(CharacterModelScene.BackgroundOverlay.alpha == 0, 'model overlay')
    assert(CharacterLevelText.textColor[1] > 0.9 and CharacterLevelText.textColor[3] < 0.3, 'level line not amber')
""")

case("model buttons, sidebar tabs and the pane toggle are restyled in place", f"""
    {OPEN}
    local S = FS.CharacterSkin.state
    local b = CharacterModelScene.ControlFrame.zoomInButton
    assert(S.squares[b], 'zoom not skinned')
    assert(b.NormalTexture.alpha == 0 and b.PushedTexture.alpha == 0, 'stock button art')
    assert(b.Icon.alpha == 1 and b.Icon.vertex[2] > 0.8, 'icon not cyan')
    assert(b.scripts.OnClick, 'click lost')
    local t1, t2 = PaperDollSidebarTab1, PaperDollSidebarTab2
    assert(S.squares[t1] and S.squares[t1].box.edges[1].color[1] > 0.9, 'selected sidebar tab not pink')
    assert(S.squares[t2].box.edges[1].color[1] < 0.5, 'idle sidebar tab pink')
    t2:SetChecked(true); t1:SetChecked(false)
    assert(S.squares[t2].box.edges[1].color[1] > 0.9 and S.squares[t1].box.edges[1].color[1] < 0.5, 'sidebar paint did not follow')
    local tg = CharacterFrameRightPaneToggleButton
    assert(#S.squares[tg].glyph == 5, 'toggle glyph')
    assert(tg.scripts.OnClick, 'toggle click lost')
""")

case("a skinned square's own box is never held: the fill and ring stay visible and survive a SetAlpha", f"""
    {OPEN}
    local S = FS.CharacterSkin.state
    local n = 0
    local function check(btn, what)
        local s = S.squares[btn]
        assert(s, what .. ' not skinned')
        for i, region in ipairs({{ s.box.fill, s.box.edges[1], s.box.edges[2], s.box.edges[3], s.box.edges[4] }}) do
            assert(region.alpha == 1, what .. ' box region ' .. i .. ' is held invisible (alpha ' .. tostring(region.alpha) .. ')')
            region:SetAlpha(0.5)
            assert(region.alpha == 0.5, what .. ' box region ' .. i .. ' carries the hold hook')
            region:SetAlpha(1)
        end
        -- the stock art next to it is still held
        assert(btn.NormalTexture == nil or btn.NormalTexture.alpha == 0, what .. ' stock art not held')
        n = n + 1
    end
    for _, key in ipairs({{ 'zoomInButton', 'zoomOutButton', 'rotateLeftButton', 'rotateRightButton', 'resetButton' }}) do
        check(CharacterModelScene.ControlFrame[key], 'model ' .. key)
    end
    for i = 1, 3 do check(_G['PaperDollSidebarTab' .. i], 'sidebar tab ' .. i) end
    check(CharacterFrameRightPaneToggleButton, 'pane toggle')
    assert(n == 9, 'checked ' .. n)
""")

case("every slot wears the shared item slot, in place, with no script or attribute written", f"""
    local before = {{}}
    for _, n in ipairs(SLOTS) do
        local b = _G['Character' .. n .. 'Slot']
        local l, t = Px(b, CharacterFrame)
        before[n] = {{ l, t }}
    end
    {OPEN}
    for _, n in ipairs(SLOTS) do
        local b = _G['Character' .. n .. 'Slot']
        assert(FS.ItemSlotSkins.Parts(b), n .. ' not decorated')
        local l, t = Px(b, CharacterFrame)
        assert(Near(l, before[n][1]) and Near(t, before[n][2]), n .. ' moved')
        assert(b.NormalTexture.alpha == 0, n .. ' normal art not held')
        assert(b.IconBorder.alpha == 0, n .. ' icon border not held')
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("slots: the stock pressed art and hover highlight are held, the slot layer draws the hover", f"""
    {OPEN}
    for _, n in ipairs(SLOTS) do
        local b = _G['Character' .. n .. 'Slot']
        assert(b.PushedTexture.alpha == 0 and b.HighlightTexture.alpha == 0, n .. ' stock pressed or hover art kept')
    end
    local b = CharacterHeadSlot
    b.HighlightTexture:SetAlpha(1)
    assert(b.HighlightTexture.alpha == 0, 'hold not kept')
""")

case("an empty slot's silhouette is tinted dim, a filled slot is left alone, and the tint follows a change of gear", f"""
    {OPEN}
    local function dim(icon) return icon.vertex and icon.vertex[1] < 0.4 and icon.vertex[3] > 0.4 end
    assert(dim(CharacterRangedSlot.icon), 'empty ranged slot not dim')
    assert(not dim(CharacterHeadSlot.icon), 'filled slot tinted')
    GEAR[18] = {{ 2, 100, 100 }}
    Fire('PLAYER_EQUIPMENT_CHANGED'); FlushTimers()
    assert(not dim(CharacterRangedSlot.icon), 'tint kept after the slot was filled')
    GEAR[18] = nil
    CharacterRangedSlot.icon:SetTexture('Interface\\\\PaperDoll\\\\UI-PaperDoll-Slot-Ranged')
    assert(dim(CharacterRangedSlot.icon), 'the stock texture swap did not retint the empty slot')
""")

case("a broken slot (no durability left) gets a pink halo around it, a worn or whole slot does not", f"""
    {OPEN}
    local S = FS.CharacterSkin.state
    local legs, head = S.slots[CharacterLegsSlot], S.slots[CharacterHeadSlot]
    assert(legs.halo and legs.halo.shown, 'broken legs: no halo')
    assert(legs.halo.color[1] > 0.9 and legs.halo.color[2] < 0.4, 'halo not pink')
    local hl, ht, hr, hb = Px(legs.halo, CharacterLegsSlot)
    local sl, st, sr, sb = Px(CharacterLegsSlot, CharacterLegsSlot)
    assert(hl < sl and ht < st and hr > sr and hb > sb, 'halo does not stand out around the slot')
    assert(not (head.halo and head.halo.shown), 'worn head has a halo')
    GEAR[7][2] = 40
    Fire('UPDATE_INVENTORY_DURABILITY'); FlushTimers()
    assert(not legs.halo.shown, 'repaired legs keep the halo')
""")

case("the equipment flyout: strip art held, a box stands behind the buttons, each button is a slot, the ring is cyan", f"""
    {OPEN}
    local fly = EquipmentFlyoutFrame
    fly.pending = 5
    EquipmentFlyout_Show(CharacterHeadSlot)
    local bf = fly.buttonFrame
    for i = 1, bf.numBGs do assert(bf['bg' .. i].alpha == 0, 'strip ' .. i .. ' kept') end
    assert(bf.numBGs >= 3, 'the stock code did not add strips')
    local S = FS.CharacterSkin.state
    assert(S.flyBox and S.flyBox.fill.alpha == 1, 'no box behind the buttons')
    local fl, ft, fr, fb = Px(S.flyBox.fill, bf)
    local bl, bt, br, bb = Px(bf, bf)
    assert(Near(fl, bl) and Near(ft, bt) and Near(fr, br) and Near(fb, bb), 'the box is not the strip rect')
    assert(#fly.buttons == 5, 'buttons: ' .. #fly.buttons)
    for i, b in ipairs(fly.buttons) do
        assert(FS.QuestSkin.state.squares[b], 'button ' .. i .. ' is not a slot')
        assert(FS.ItemSlotSkins.Parts(b), 'button ' .. i .. ' not on the slot layer')
        assert(b.scripts.OnClick and b.scripts.OnEnter, 'stock script lost on ' .. i)
        assert(b.NormalTexture.alpha == 0, 'stock normal art kept on ' .. i)
    end
    assert(fly.Highlight.desat and fly.Highlight.vertex[2] > 0.8 and fly.Highlight.vertex[1] < 0.4, 'highlight ring not cyan')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\\\n'))
""")

case("the equipment flyout: a button made later (a longer list) is met, the page frame wears the cut keys and mono text", f"""
    {OPEN}
    local fly = EquipmentFlyoutFrame
    fly.pending = 3
    EquipmentFlyout_Show(CharacterHeadSlot)
    fly.pending = 12
    EquipmentFlyout_Show(CharacterHeadSlot)
    assert(#fly.buttons == 12, 'buttons: ' .. #fly.buttons)
    assert(FS.QuestSkin.state.squares[fly.buttons[12]], 'late button not a slot')
    for i = 1, fly.buttonFrame.numBGs do assert(fly.buttonFrame['bg' .. i].alpha == 0, 'late strip ' .. i .. ' kept') end
    local nav = fly.NavigationFrame
    assert(nav.BottomBackground.alpha == 0, 'nav art kept')
    local P = FS.QuestSkin.state.pagers
    assert(P[nav.PrevButton] and P[nav.NextButton], 'page keys')
    for _, r in ipairs(nav.regions) do
        if r.kind == 'FontString' then assert(r.fontPath ~= 'stock.ttf', 'nav text not mono') end
    end
    assert(FS.CharacterSkin.state.flyNav, 'no box behind the nav')
""")

case("the equipment flyout: the page keys and their texts do not overlap, the gaps match, and the flyout opens below the window header", f"""
    {OPEN}
    local fly = EquipmentFlyoutFrame
    fly.pending = 10
    EquipmentFlyout_Show(CharacterHeadSlot)
    local nav = fly.NavigationFrame
    local P = FS.QuestSkin.state.pagers
    local pl, _, pr = Px(P[nav.PrevButton].key.ring, nav)
    local nl, _, nr = Px(P[nav.NextButton].key.ring, nav)
    local texts = {{}}
    for _, r in ipairs(nav.regions) do if r.kind == 'FontString' then texts[r.text] = r end end
    local tpl, _, tpr = Px(texts.PREVIOUS, nav)
    local tnl, _, tnr = Px(texts.NEXT, nav)
    assert(tpl - pr >= 3, 'PREVIOUS runs into its key: ' .. (tpl - pr))
    assert(nl - tnr >= 3, 'NEXT runs into its key: ' .. (nl - tnr))
    assert(tnl - tpr >= 20, 'the two texts meet: ' .. (tnl - tpr))
    assert(math.abs((tpl - pr) - (nl - tnr)) <= 1, 'key to text gaps differ: ' .. (tpl - pr) .. ' vs ' .. (nl - tnr))
    local navW = select(3, Px(nav, nav))
    assert(pl >= 8 and navW - nr >= 8, 'a key is closer than 8 px to the nav edge')
    -- the strip and the page frame open beside the slot they came from, under the window's header
    local hb = select(4, Px(PaperDollFrame.TopBackgroundStripHost, CharacterFrame))
    local _, st = Px(fly.buttonFrame, CharacterFrame)
    assert(st >= hb, 'the flyout strip overlaps the window header: ' .. st .. ' vs ' .. hb)
    local _, nt = Px(nav, CharacterFrame)
    local _, _, _, sb = Px(fly.buttonFrame, CharacterFrame)
    assert(Near(nt, sb, 0.5), 'the page frame is not under the strip')
""")

case("wear bars: height follows durability, colour follows the band, full wear shows nothing", f"""
    {OPEN}
    local S = FS.CharacterSkin.state
    local function bar(name) return S.slots[_G['Character' .. name .. 'Slot']] end
    local head = _G.CharacterHeadSlot
    local w = bar('Head')
    local _, _, _, full = Px(head, head)
    -- 72 percent: cyan
    local pl, pt, pr, pb = Px(w.bar, head)
    local _, ph = Px(head, head)
    local sizeW, sizeH = Px(head, head)
    local fullH = (select(4, Px(head, head))) - 12
    assert(w.bar.shown, 'head bar hidden')
    assert(Near(pb - pt, math.floor(fullH * 0.72 + 0.5), 1), 'head height ' .. (pb - pt))
    assert(Near(pr - pl, 2), 'bar width')
    assert(w.bar.color[2] > w.bar.color[1], 'head not cyan')
    -- 34 percent: amber (r high, b low); 12 percent: pink; broken: pink and full
    local sh = bar('Shoulder').bar.color
    assert(sh[1] > 0.8 and sh[3] < 0.3, 'shoulder not amber')
    local ch = bar('Chest').bar.color
    assert(ch[1] > 0.9 and ch[2] < 0.4, 'chest not pink')
    local lg = bar('Legs')
    local l2, t2, r2, b2 = Px(lg.bar, _G.CharacterLegsSlot)
    assert(Near(b2 - t2, fullH, 1), 'broken legs bar not full: ' .. (b2 - t2))
    assert(not bar('Back').bar.shown, 'full durability shows a bar')
    assert(not bar('Neck').bar.shown, 'no durability shows a bar')
""")

case("a durability that changes repaints the bar", f"""
    {OPEN}
    GEAR[1][2] = 10
    Fire('UPDATE_INVENTORY_DURABILITY'); FlushTimers()
    local w = FS.CharacterSkin.state.slots[CharacterHeadSlot]
    assert(w.bar.color[1] > 0.9 and w.bar.color[2] < 0.4, 'head not pink after wear')
    GEAR[1][2] = 100
    Fire('UPDATE_INVENTORY_DURABILITY'); FlushTimers()
    assert(not w.bar.shown, 'bar still shown at full')
""")

case("a secret durability shows no bar and is never compared", f"""
    GetInventoryItemDurability = function(id) if id == 1 then return Secret(), Secret() end return nil end
    {OPEN}
    local w = FS.CharacterSkin.state.slots[CharacterHeadSlot]
    assert(not w.bar.shown, 'secret shown')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("footer chips: one shared line, even spacing, the repair bill right aligned", f"""
    {OPEN}
    local c = FS.CharacterSkin.state.chips
    assert(c.ilvl.label.text == 'ilvl 14', c.ilvl.label.text)
    assert(c.wear.label.text:find('^wear %d+%%$'), c.wear.label.text)
    assert(c.worn.label.text == '5 worn', c.worn.label.text)
    assert(c.repair.label.text == 'repair 2g 80s 0c', c.repair.label.text)
    local wl, wt, wr, wb = Px(CharacterFrame, CharacterFrame)
    local l1, t1, r1, b1 = Px(c.ilvl.frame, CharacterFrame)
    local l2, t2, r2, b2 = Px(c.wear.frame, CharacterFrame)
    local l3, t3, r3, b3 = Px(c.worn.frame, CharacterFrame)
    local l4, t4, r4, b4 = Px(c.repair.frame, CharacterFrame)
    assert(Near(t1, t2) and Near(t2, t3) and Near(t3, t4), 'chips are not on one line')
    assert(Near(l1, 14), 'first chip x ' .. l1)
    assert(Near(l2 - r1, l3 - r2), 'uneven gaps ' .. (l2 - r1) .. ' ' .. (l3 - r2))
    assert(Near(wr - r4, 14), 'repair right margin ' .. (wr - r4))
    -- the line is centred in the footer band
    assert(Near(wb - b1, t1 - (wb - 40), 1), 'chips not centred in the footer: ' .. (wb - b1) .. ' vs ' .. (t1 - (wb - 40)))
    local fl, ft, fr, fb = Px(FS.CharacterSkin.state.footer.band, CharacterFrame)
    assert(Near(fb, wb) and Near(fb - ft, 40), 'footer band ' .. ft .. ' ' .. fb)
""")

case("chips hide for a missing or secret value, and off the character page", f"""
    GetAverageItemLevel = function() return Secret(), Secret() end
    C_TooltipInfo = nil
    {OPEN}
    local c = FS.CharacterSkin.state.chips
    assert(not c.ilvl.frame.shown, 'secret ilvl shown')
    assert(not c.repair.frame.shown, 'repair shown without a plain cost')
    assert(c.wear.frame.shown)
    CharacterFrameModeTab2.scripts.OnMouseUp()
    assert(not c.wear.frame.shown, 'footer on the reputation page')
    CharacterFrameModeTab1.scripts.OnMouseUp()
    assert(c.wear.frame.shown, 'footer chips did not come back on the character page')
""")

case("stat rows (the ScrollBox's recycled rows) keep their scripts, hold their art and take mono text", f"""
    {OPEN}
    local box = CharacterStatsPaneScrollBox.ScrollBox
    local row
    for _, r in ipairs(box.rows) do if r.Label then row = r break end end
    assert(row.scripts.OnEnter, 'stat tooltip script lost')
    assert(row.Background.alpha == 0, 'row art not held')
    assert(row.Label.fontPath ~= 'stock.ttf', 'label font not restyled ' .. tostring(row.Label.fontPath))
    row.Label:SetTextColor(1, 0.82, 0, 1)
    assert(row.Label.textColor[1] < 0.8, 'the pinned label colour came back to gold')
    local cat = box.rows[1]
    assert(cat.Background.alpha == 0 and cat.Title.textColor[2] > 0.8 and cat.Title.textColor[1] < 0.5, 'category not cyan')
    assert(CharacterStatsPaneScrollBox.Border.alpha == 0 and CharacterStatsPaneScrollBox.ClassBackground.alpha == 0, 'pane art')
    -- a row the list builds later is restyled on its next update
    local f = BLZ.blz('Frame', nil, box.ScrollTarget, 193, 23)
    f.Background = BLZ.atex(f, nil, 'BACKGROUND', 'UI-Character-Info-Line-Bounce2', 213, 23)
    f.Label = BLZ.fstring(f, nil, 'Armor', 11)
    box.rows[#box.rows + 1] = f
    box:Update(); FlushTimers()
    assert(f.Background.alpha == 0 and f.Label.fontPath ~= 'stock.ttf', 'a later row was not restyled')
""")

case("the other pages: line overlays, header rows and detail panes held, the honor badge kept", f"""
    {OPEN}
    local sk = SkillsFrame
    sk:Show(); FlushTimers()
    local ov = sk.ScrollBox.children[1]
    assert(ov.regions[1].alpha == 0, 'scroll line overlay')
    local hdr = sk.ScrollBox.rows[1]
    assert(hdr.regions[1].alpha == 0, 'header art')
    assert(hdr.StateIcon.alpha == 1 and hdr.StateIcon.vertex[2] > 0.8, 'state icon not cyan')
    assert(sk.SkillDetailFrame.Divider.alpha == 0, 'detail divider')
    assert(sk.SkillDetailFrame.Title.textColor[2] > 0.8 and sk.SkillDetailFrame.Title.textColor[1] < 0.5, 'detail title')
    local pv = PVPRankFrame
    assert(pv.MainInfoFrame.regions[1].alpha == 0, 'honor level band')
    assert(pv.MainInfoFrame.badge.alpha == 1, 'the honor badge must stay')
    assert(StatisticsFrame.ScrollBox.children[1].regions[1].alpha == 0, 'statistics overlay')
""")

case("nothing is built in combat; the skin is built when it ends", f"""
    Reset()
    __combat = true
    Load({{ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'Character' }})
    Fire('PLAYER_ENTERING_WORLD'); CharacterFrame:Show(); FlushTimers()
    assert(not CharacterFrame.fsCharacterSkin, 'built in combat')
    assert(CharacterFrame.h == 484, 'the window was resized in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(CharacterFrame.fsCharacterSkin, 'not built when combat ended')
""")

case("pixels: wear bar and chips land on whole screen pixels at 1.2 and 1.0", f"""
    {OPEN}
    local function whole(o, what, ref)
        local l, t, r, b = Px(o, ref)
        for _, v in ipairs({{ l, t, r, b }}) do assert(Near(v, math.floor(v + 0.5), 0.02), what .. ' off the pixel grid: ' .. v) end
    end
    whole(FS.CharacterSkin.state.slots[CharacterHeadSlot].bar, 'bar', CharacterHeadSlot)
    whole(FS.CharacterSkin.state.chips.ilvl.frame, 'chip', CharacterFrame)
""")

SCENES = {
    "character": "Fire('PLAYER_ENTERING_WORLD'); CharacterFrame:Show(); FlushTimers(); return DumpOps({ CharacterFrame })",
    "flyout": ("Fire('PLAYER_ENTERING_WORLD'); CharacterFrame:Show(); FlushTimers(); EquipmentFlyoutFrame.pending = 10; "
               "EquipmentFlyout_Show(CharacterHeadSlot); FlushTimers(); return DumpOps({ CharacterFrame, EquipmentFlyoutFrame })"),
}

if __name__ == "__main__":
    raise SystemExit(H.main("character skin", SCENES))
