#!/usr/bin/env python3
"""Runs the real Modules/Skins/Inspect.lua headless against a mock InspectFrame (tools/charskin_support.py).

Pinned: the header band and switch driving the stock tabs, every slot wearing the shared item slot in place with no wear bar, the
item level delta chip on each slot (their piece minus yours, cyan above, pink below, hidden when level, empty or unreadable; a
ring or trinket against your better one), the footer chips, secret values hidden, and no script or attribute written on a Blizzard
widget. Run `python3 tools/inspectskin-harness.py [--png /tmp/insp]`. The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring = BLZ.blz, BLZ.tex, BLZ.fstring
local build = BuildBlizzard
-- item levels: yours (player) and theirs (target), by slot id
MINE = { [1] = 10, [3] = 20, [5] = 12, [11] = 8, [12] = 14, [16] = 15 }
THEIRS = { [1] = 14, [3] = 15, [5] = 12, [11] = 12, [12] = 9, [15] = 30, [16] = 25 }
GetInventoryItemLink = function(unit, id)
    local t = unit == "player" and MINE or THEIRS
    return t[id] and (unit .. ":" .. id) or nil
end
C_Item = { GetDetailedItemLevelInfo = function(link)
    local unit, id = link:match("^(%a+):(%d+)$")
    return (unit == "player" and MINE or THEIRS)[tonumber(id)]
end }
C_PaperDollInfo = { GetInspectItemLevel = function() return 33 end }
function BuildBlizzard()
    build()
    for k in pairs(_G) do if type(k) == "string" and k:find("^Inspect") then _G[k] = nil end end
    local win = blz("Frame", "InspectFrame", UIParent, 440, 480)
    win.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 250, y = -100 }
    win.shown = false
    win.unit = "target"
    win.selectedTab = 1
    win.Bg = tex(win, nil, "BACKGROUND")
    win.Inset = blz("Frame", "InspectFrameInset", win, 400, 380)
    tex(win, "InspectFramePortrait", "ARTWORK")
    fstring(win, "InspectFrameTitleText", "Grakk")
    local close = blz("Button", "InspectFrameCloseButton", win, 24, 24, "TOPRIGHT")
    tex(close, nil, "BACKGROUND")
    win.CloseButton = close
    local pd = blz("Frame", "InspectPaperDollFrame", win, 440, 480)
    tex(pd, nil, "BACKGROUND")
    for i, label in ipairs({ "Character", "Talents" }) do
        local tab = blz("Button", "InspectFrameTab" .. i, win, 90, 32, "BOTTOMLEFT", 11 + (i - 1) * 91, 2)
        tab.fs = fstring(tab, "InspectFrameTab" .. i .. "Text", label)
        tab.scripts.OnClick = function() win.selectedTab = i end
        tex(tab, nil, "BACKGROUND")
    end
    InspectSwitchTabs = function() end
    local left = { "Head", "Neck", "Shoulder", "Back", "Chest", "Shirt", "Tabard", "Wrist" }
    local right = { "Hands", "Waist", "Legs", "Feet", "Finger0", "Finger1", "Trinket0", "Trinket1" }
    local ids = { Head = 1, Neck = 2, Shoulder = 3, Shirt = 4, Chest = 5, Waist = 6, Legs = 7, Feet = 8, Wrist = 9, Hands = 10,
        Finger0 = 11, Finger1 = 12, Trinket0 = 13, Trinket1 = 14, Back = 15, MainHand = 16, SecondaryHand = 17, Ranged = 18, Tabard = 19 }
    local function slot(name, x, y)
        local b = blz("Button", "Inspect" .. name .. "Slot", pd, 37, 37, "TOPLEFT", x, y)
        b.id = ids[name]
        b.NormalTexture = tex(b, nil, "ARTWORK")
        b.icon = tex(b, "Inspect" .. name .. "SlotIconTexture", "BORDER")
        b.icon.path = "Interface\\Icons\\inv_" .. ids[name]
        b.IconBorder = tex(b, nil, "OVERLAY")
        b.Count = fstring(b, "Inspect" .. name .. "SlotCount", "", 12)
        b.GetID = function(self) return self.id end
    end
    for i, n in ipairs(left) do slot(n, 20, -(70 + (i - 1) * 41)) end
    for i, n in ipairs(right) do slot(n, 383, -(70 + (i - 1) * 41)) end
    slot("MainHand", 150, -410); slot("SecondaryHand", 200, -410); slot("Ranged", 250, -410)
end
BuildBlizzard()
"""

H = Harness({"Character": "Modules/Skins/Character.lua", "Inspect": "Modules/Skins/Inspect.lua"}, BLIZZARD)
case = H.case

OPEN = "Fire('PLAYER_ENTERING_WORLD'); InspectFrame:Show(); Fire('INSPECT_READY'); FlushTimers()"


def slot(name):
    return f"_G.Inspect{name}Slot"


case("builds: chrome, header band, a switch over the two stock tabs that drives their Click", f"""
    {OPEN}
    local S = FS.InspectSkin.state
    assert(InspectFrame.fsInspectSkin and S.header and #S.header.switch.items == 2, 'header')
    assert(S.header.switch.items[1].label.text == 'character' and S.header.switch.items[2].label.text == 'talents')
    assert(InspectFrameTab1.alpha == 0 and InspectFrameTab1.mouse == false, 'stock tab held')
    S.header.switch.items[2].button:Click()
    assert(InspectFrame.selectedTab == 2, 'stock tab not clicked')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("slots wear the shared item slot in place, with no wear bar on another player's gear", f"""
    local l0, t0 = Px({slot('Head')}, InspectFrame)
    {OPEN}
    for _, n in ipairs(SLOTS) do
        local b = _G['Inspect' .. n .. 'Slot']
        assert(FS.ItemSlotSkins.Parts(b), n .. ' not decorated')
        assert(b.NormalTexture.alpha == 0 and b.IconBorder.alpha == 0, n .. ' art')
        local w = FS.CharacterSkin.state.slots[b]
        assert(not w.bar or not w.bar.shown, n .. ' shows wear on another unit')
    end
    local l1, t1 = Px({slot('Head')}, InspectFrame)
    assert(Near(l0, l1) and Near(t0, t1), 'head moved')
""")

case("delta chips: theirs minus yours, cyan above and pink below, hidden when level or empty", f"""
    {OPEN}
    local I = FS.InspectSkin
    local function chip(name) local d = I.state.deltas[{slot('')[:0]}_G['Inspect' .. name .. 'Slot']] return d end
    local head = chip('Head')
    assert(head.label.shown and head.label.text == '+4', 'head ' .. tostring(head.label.text))
    assert(head.label.textColor[3] > 0.9 and head.label.textColor[1] < 0.3, 'head not cyan')
    local sh = chip('Shoulder')
    assert(sh.label.text == '-5' and sh.label.textColor[1] > 0.9, 'shoulder ' .. tostring(sh.label.text))
    assert(not chip('Chest').label.shown, 'level piece shows a chip')
    assert(not chip('Neck').label.shown, 'empty on both sides shows a chip')
    assert(not chip('Back').label.shown, 'empty on your side shows a chip')
""".replace("{slot('')[:0]}", ""))

case("rings compare against your better ring; the main hand against yours", f"""
    {OPEN}
    local I = FS.InspectSkin
    assert(I.Delta(11, 'target') == 12 - 14, 'ring 1')
    assert(I.Delta(12, 'target') == 9 - 14, 'ring 2')
    assert(I.Delta(16, 'target') == 10, 'main hand')
""")

case("an item the client has not cached, or a secret level, hides its chip", f"""
    {OPEN}
    local I = FS.InspectSkin
    C_Item.GetDetailedItemLevelInfo = function() return nil end
    Fire('GET_ITEM_INFO_RECEIVED'); FlushTimers()
    for b, d in pairs(I.state.deltas) do assert(not d.label or not d.label.shown, 'chip shown without a level') end
    C_Item.GetDetailedItemLevelInfo = function() return Secret() end
    Fire('GET_ITEM_INFO_RECEIVED')
    for b, d in pairs(I.state.deltas) do assert(not d.label or not d.label.shown, 'chip shown for a secret level') end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("footer chips: their item level and how it stands against yours", f"""
    {OPEN}
    local c = FS.InspectSkin.state.chips
    assert(c.ilvl.label.text == 'ilvl 33', c.ilvl.label.text)
    assert(c.you.label.text == 'vs you +19', c.you.label.text)   -- 33 against your equipped 14.2
    C_PaperDollInfo.GetInspectItemLevel = function() return Secret() end
    FS.InspectSkin.RefreshChips()
    assert(not c.ilvl.frame.shown and not c.you.frame.shown, 'chips for a secret level')
""")

SCENES = {
    "inspect": "Fire('PLAYER_ENTERING_WORLD'); InspectFrame:Show(); Fire('INSPECT_READY'); FlushTimers(); return DumpOps({ InspectFrame })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("inspect skin", SCENES))
