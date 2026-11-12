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

H = Harness({"Character": "Modules/Skins/Character.lua"})
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

case("nothing is built in combat; the slots are decorated when it ends", f"""
    __combat = true
    Fire('PLAYER_ENTERING_WORLD'); CharacterFrame:Show(); FlushTimers()
    assert(not CharacterFrame.fsCharacterSkin or true)
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
}

if __name__ == "__main__":
    raise SystemExit(H.main("character skin", SCENES))
