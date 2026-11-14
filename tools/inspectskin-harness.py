#!/usr/bin/env python3
"""Runs the real Modules/Skins/Inspect.lua headless against a mock InspectFrame (tools/charskin_support.py).

Pinned: the header band and switch driving the stock tabs, every slot wearing the shared item slot in place with no wear bar, the
item level delta chip on each slot (their piece minus yours, cyan above, pink below, hidden when level, empty or unreadable; a
ring or trinket against your better one), the footer chips, secret values hidden, and no script or attribute written on a Blizzard
widget. The leftovers: the model well's stock art held and four cyan corner brackets (the gunsight) around it, the model control
panel's keys as square keys (the panel is hidden until the model is hovered, as stock), the level line held and mirrored on an amber
chip in the well's bottom left (below the header band), the stock slot frames held, and the two stock text buttons (view, talents)
swept. Run `python3 tools/inspectskin-harness.py [--png /tmp/insp]`. The mock is NOT the real client.
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
    local atex = BLZ.atex
    -- the real model sits at x 52 of a 338 wide window, between slot columns anchored 4 + 4 in from each side; this mock is 440 wide
    -- with its columns at 20 and 383, so the same well is centred between them (x 104) to keep the margins symmetric
    local model = blz("Frame", "InspectModelFrame", pd, 231, 320, "TOPLEFT", 104, -70)
    for _, n in ipairs({ "TopLeft", "TopRight", "BotLeft", "BotRight" }) do
        model["Background" .. n] = tex(model, "InspectModelFrameBackground" .. n, "BACKGROUND")
    end
    model.BackgroundOverlay = tex(model, "InspectModelFrameBackgroundOverlay", "BORDER")
    for _, n in ipairs({ "TopLeft", "TopRight", "BottomLeft", "BottomRight", "Left", "Right", "Top", "Bottom", "Bottom2" }) do
        atex(model, "InspectModelFrameBorder" .. n, "OVERLAY", "Char-Inner-Left", 8, 8)
    end
    local control = blz("Frame", "InspectModelFrameControlFrame", model, 112, 23, "TOP", 0, -2)
    control.shown = false   -- ModelWithControlsTemplate: hidden="true"; the model's own hover shows it
    model.controlFrame = control
    for _, n in ipairs({ "Left", "Middle", "Right" }) do tex(control, "InspectModelFrameControlFrame" .. n, "BACKGROUND") end
    CONTROLS = {}
    for i, n in ipairs({ "ZoomIn", "ZoomOut", "Pan", "RotateLeft", "RotateRight", "RotateReset" }) do
        local b = blz("Button", "InspectModelFrameControlFrame" .. n .. "Button", control, 18, 18, "TOPLEFT", 2 + (i - 1) * 18, 0)
        b.bg = tex(b, nil, "BACKGROUND")
        b.icon = tex(b, nil, "ARTWORK")
        b.icon.path = "Interface\\Common\\UI-ModelControlPanel"
        b.scripts.OnClick = function() end
        CONTROLS[i] = b
    end
    local lv = fstring(pd, "InspectLevelText", "Level 40 |cffabd473Troll Hunter|r", 12)
    lv.points[1] = { point = "TOP", rel = pd, relPoint = "TOP", x = 0, y = -27 }   -- LevelTextWrapper TOP 0 -27, 220 wide
    lv.w, lv.h, lv.justify = 220, 12, "CENTER"
    lv.SetFormattedText = function(self, fmt, ...) self.text = string.format(fmt, ...) end
    pd.ViewButton = blz("Button", nil, pd, 100, 22, "TOP", 0, -39)
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
        atex(b, "Inspect" .. name .. "SlotFrame", "BACKGROUND", "Char-LeftSlot", 64, 64)
        if name == "MainHand" then b.Decor = atex(b, nil, "BACKGROUND", "Char-Slot-Bottom-Left", 20, 20) end
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

case("the model well: stock backgrounds, borders and the control panel art are held, nothing moves", f"""
    local l0, t0 = Px(InspectModelFrame, InspectFrame)
    {OPEN}
    for _, n in ipairs({{ 'TopLeft', 'TopRight', 'BotLeft', 'BotRight' }}) do
        assert(_G['InspectModelFrameBackground' .. n].alpha == 0, 'background ' .. n)
    end
    assert(InspectModelFrameBackgroundOverlay.alpha == 0, 'overlay')
    for _, n in ipairs({{ 'TopLeft', 'TopRight', 'BottomLeft', 'BottomRight', 'Left', 'Right', 'Top', 'Bottom', 'Bottom2' }}) do
        assert(_G['InspectModelFrameBorder' .. n].alpha == 0, 'border ' .. n)
    end
    for _, n in ipairs({{ 'Left', 'Middle', 'Right' }}) do
        assert(_G['InspectModelFrameControlFrame' .. n].alpha == 0, 'control panel ' .. n)
    end
    local l1, t1 = Px(InspectModelFrame, InspectFrame)
    assert(Near(l0, l1) and Near(t0, t1), 'model moved')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("the gunsight: four cyan corner brackets around the model well, an L of ten pixels, three in from each corner", f"""
    {OPEN}
    local S = FS.InspectSkin.state
    local m = InspectModelFrame
    local W, H = FS.ControlKit.SizePx(m)
    local L, M = 10, 3
    local want = {{
        {{ M, M, L, 1 }}, {{ M, M + 1, 1, L - 1 }},
        {{ W - M - L, M, L, 1 }}, {{ W - M - 1, M + 1, 1, L - 1 }},
        {{ M, H - M - 1, L, 1 }}, {{ M, H - M - L, 1, L - 1 }},
        {{ W - M - L, H - M - 1, L, 1 }}, {{ W - M - 1, H - M - L, 1, L - 1 }},
    }}
    assert(S.reticle and #S.reticle == 8, 'no reticle')
    for i, r in ipairs(S.reticle) do
        local w = want[i]
        Expect(r, m, w[1], w[2], w[3], w[4], 'bracket ' .. i)
        assert(r.shown ~= false and r.color[3] > 0.9 and r.color[1] < 0.3, 'bracket ' .. i .. ' not cyan')
    end
""")

case("the model control keys are square keys: stock art held, the icon cyan, the click untouched", f"""
    {OPEN}
    local S = FS.CharacterSkin.state
    assert(#CONTROLS == 6)
    for i, b in ipairs(CONTROLS) do
        assert(S.squares[b], 'control ' .. i .. ' not skinned')
        assert(b.bg.alpha == 0, 'control ' .. i .. ' stock art')
        assert(b.icon.alpha == 1 and b.icon.vertex[2] > 0.8 and b.icon.vertex[1] < 0.5, 'control ' .. i .. ' icon not cyan')
        assert(b.scripts.OnClick, 'control ' .. i .. ' click lost')
        local box = S.squares[b].box
        for j, region in ipairs({{ box.fill, box.edges[1], box.edges[2], box.edges[3], box.edges[4] }}) do
            assert(region.alpha == 1, 'control ' .. i .. ' box region ' .. j .. ' held invisible')
        end
    end
    CONTROLS[1]:RunScript('OnEnter')
    assert(S.squares[CONTROLS[1]].box.edges[1].color[3] > 0.9, 'hover edge not cyan')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("the level line: the stock text is held and mirrored on an amber chip in the well's bottom left, clear of the header band and the brackets", f"""
    {OPEN}
    local S = FS.InspectSkin.state
    local c = S.chips.level
    assert(c and c.frame.shown, 'no level chip')
    assert(InspectLevelText.alpha == 0, 'stock level line not held')
    assert(c.label.text == InspectLevelText.text and c.label.text:find('|cffabd473', 1, true), 'text not mirrored with its class colour')
    local W, H = FS.ControlKit.SizePx(InspectModelFrame)
    local l, t, r, b = Px(c.frame, InspectModelFrame)
    assert(Near(l, 12) and Near(H - b, 12) and Near(b - t, 20), 'chip not 12 px in from the left and bottom: ' .. l .. ' ' .. (H - b))
    assert(r <= W - 12, 'chip runs out of the well')
    local _, top = Px(c.frame, InspectFrame)
    assert(top >= FS.InspectSkin.GEOM.HEAD_H + 8, 'chip not clear below the header band: ' .. top)
    for i, br in ipairs(S.reticle) do
        local bl, bt, brr, bb = Px(br, InspectModelFrame)
        assert(brr <= l or bl >= r or bb <= t or bt >= b, 'chip overlaps bracket ' .. i)
    end
    InspectLevelText:SetFormattedText('Level %d |c%s%s|r', 41, 'ffc79c6e', 'Warrior')
    assert(c.label.text == 'Level 41 |cffc79c6eWarrior|r', 'the chip did not follow the stock text: ' .. c.label.text)
    InspectLevelText.text = Secret()
    FS.InspectSkin.RefreshLevel()
    assert(not c.frame.shown, 'a secret text is shown')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("the model control keys are hidden with their panel until the model is hovered (as stock)", f"""
    {OPEN}
    assert(InspectModelFrame.controlFrame.shown == false, 'control panel shown by default')
""")

case("the stock slot frames and the main hand corner are held; the stock text buttons are swept", f"""
    {OPEN}
    for _, n in ipairs(SLOTS) do
        assert(_G['Inspect' .. n .. 'SlotFrame'].alpha == 0, n .. ' slot frame')
    end
    assert(InspectMainHandSlot.Decor.alpha == 0, 'main hand corner')
    assert(InspectPaperDollFrame.fsSweepHook, 'paper doll not swept (view and talents buttons)')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

SCENES = {
    "inspect": "Fire('PLAYER_ENTERING_WORLD'); InspectFrame:Show(); Fire('INSPECT_READY'); FlushTimers(); return DumpOps({ InspectFrame })",
    "inspect-controls": "Fire('PLAYER_ENTERING_WORLD'); InspectFrame:Show(); Fire('INSPECT_READY'); FlushTimers(); InspectModelFrame.controlFrame:Show(); return DumpOps({ InspectFrame })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("inspect skin", SCENES))
