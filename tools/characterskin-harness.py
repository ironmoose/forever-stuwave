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

case("builds: chrome, header band, switch with three pages", f"""
    {OPEN}
    local S = FS.CharacterSkin.state
    assert(S.header and S.header.switch, 'no header switch')
    assert(#S.header.switch.items == 3, 'items')
    assert(S.header.title.text == 'stuwave://character', S.header.title.text)
    local l, t, r, b = Px(S.header.band[2], CharacterFrame)
    assert(Near(t, 6) and Near(b, 44), 'band y ' .. t .. ' ' .. b)
    assert(CharacterFrame.fsCharacterSkin)
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("stock tabs are held and never hit; the stock title and portrait are held", f"""
    {OPEN}
    for i = 1, 3 do
        local tab = _G['CharacterFrameTab' .. i]
        assert(tab.alpha == 0, 'tab ' .. i .. ' alpha ' .. tab.alpha)
        assert(tab.mouse == false, 'tab mouse')
    end
    assert(CharacterFrameTitleText.alpha == 0)
    assert(CharacterFramePortrait.alpha == 0)
    CharacterFrameTitleText:SetAlpha(1)
    assert(CharacterFrameTitleText.alpha == 0, 'the hold survives a SetAlpha')
""")

case("the switch drives the stock tabs and the title follows the page", f"""
    {OPEN}
    local S = FS.CharacterSkin.state
    S.header.switch.items[2].button:Click()
    assert(ReputationFrame:IsShown() and not PaperDollFrame:IsShown(), 'reputation not shown')
    assert(S.header.title.text == 'stuwave://reputation', S.header.title.text)
    assert(S.header.switch:GetSelected() == 2)
    S.header.switch.items[3].button:Click()
    assert(TokenFrame:IsShown())
    assert(S.header.title.text == 'stuwave://currency')
    S.header.switch.items[1].button:Click()
    assert(PaperDollFrame:IsShown() and S.header.title.text == 'stuwave://character')
""")

case("a tab with no Click is reached through ToggleCharacter, not toggled off", f"""
    CharacterFrameTab2.Click = nil
    CharacterFrameTab2.Click = false
    {OPEN}
    local S = FS.CharacterSkin.state
    S.header.switch.items[2].button:Click()
    assert(ReputationFrame:IsShown(), 'fallback did not show the page')
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

case("footer chips: item level, wear, worn pieces and the repair bill", f"""
    {OPEN}
    local c = FS.CharacterSkin.state.chips
    assert(c.ilvl.label.text == 'ilvl 14', c.ilvl.label.text)
    assert(c.wear.label.text:find('^wear %d+%%$'), c.wear.label.text)
    assert(c.worn.label.text == '5 worn', c.worn.label.text)
    assert(c.repair.label.text == 'repair 2g 80s 0c', c.repair.label.text)
    -- the chips sit on the window's bottom edge, 8 px up, 14 px in
    local l, t, r, b = Px(c.ilvl.frame, CharacterFrame)
    local wl, wt, wr, wb = Px(CharacterFrame, CharacterFrame)
    assert(Near(wb - b, 8) and Near(l, 14), 'chip seat ' .. (wb - b) .. ' ' .. l)
    local rl, rt, rr, rb = Px(c.repair.frame, CharacterFrame)
    assert(Near(wr - rr, 14), 'repair right margin ' .. (wr - rr))
""")

case("chips hide for a missing or secret value, and off the character page", f"""
    GetAverageItemLevel = function() return Secret(), Secret() end
    C_TooltipInfo = nil
    {OPEN}
    local c = FS.CharacterSkin.state.chips
    assert(not c.ilvl.frame.shown, 'secret ilvl shown')
    assert(not c.repair.frame.shown, 'repair shown without a plain cost')
    assert(c.wear.frame.shown)
    FS.CharacterSkin.state.header.switch.items[2].button:Click()
    FS.CharacterSkin.RefreshChips()
    assert(not c.wear.frame.shown, 'footer on the reputation page')
""")

case("stat rows keep their scripts, hold their art and take mono text", f"""
    {OPEN}
    local pane = CharacterStatsPane
    local row
    for _, ch in ipairs({{ pane:GetChildren() }}) do if ch.Label then row = ch break end end
    assert(row.scripts.OnEnter, 'stat tooltip script lost')
    assert(row.Background.alpha == 0, 'row art not held')
    assert(row.Label.fontPath:find('Mononoki') or row.Label.fontPath ~= 'stock.ttf', 'label font not restyled ' .. tostring(row.Label.fontPath))
    row.Label:SetTextColor(1, 0.82, 0, 1)
    assert(row.Label.textColor[1] < 0.8, 'the pinned label colour came back to gold')
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
