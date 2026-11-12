#!/usr/bin/env python3
"""Runs the real Modules/Skins/Reputation.lua headless against a mock ReputationFrame (tools/charskin_support.py).

Pinned: eight ladder segments per entry row with a 4 px gap on whole pixels, lit up to the standing and filled by the stock bar's own
progress, dim above it, an exalted row fully lit, the stock bar art held while the stock bar keeps its value and scripts, header rows
restyled, a secret or missing standing drawing no ladder, rows rebuilt by the scroll list repainted, and no script or attribute
written on a Blizzard widget. Run `python3 tools/reputationskin-harness.py [--png /tmp/rep]`. The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring = BLZ.blz, BLZ.tex, BLZ.fstring
local build = BuildBlizzard
FACTIONS = {
    { header = true, name = "Classic" },
    { name = "Thunder Bluff", reaction = 5, min = 0, max = 6000, value = 2210 },
    { name = "Orgrimmar", reaction = 6, min = 0, max = 9000, value = 3300 },
    { name = "Darkspear Trolls", reaction = 4, min = 0, max = 3000, value = 450 },
    { name = "Gnomeregan Exiles", reaction = 2, min = 0, max = 3000, value = 600 },
    { name = "Warsong Outriders", reaction = 7, min = 0, max = 21000, value = 5200 },
    { name = "The Defilers", reaction = 8, min = 0, max = 999, value = 999 },
}
function BuildBlizzard()
    build()
    local frame = _G.ReputationFrame
    frame.Update = function() end
    frame.ScrollBox = blz("Frame", nil, frame, 440, 330, "TOPLEFT", 8, -62)
    frame.ScrollBox.rows = {}
    frame.ScrollBox.ForEachFrame = function(self, fn) for _, r in ipairs(self.rows) do fn(r) end end
    local y = 0
    for i, f in ipairs(FACTIONS) do
        local row
        if f.header then
            row = blz("Button", nil, frame.ScrollBox, 430, 24, "TOPLEFT", 0, -y)
            row.Left, row.Middle, row.Right = tex(row, nil, "BACKGROUND"), tex(row, nil, "BACKGROUND"), tex(row, nil, "BACKGROUND")
            row.Name = fstring(row, nil, f.name, 12)
            y = y + 30
        else
            row = blz("Button", nil, frame.ScrollBox, 430, 44, "TOPLEFT", 0, -y)
            row.Content = blz("Frame", nil, row, 430, 44)
            local bar = blz("Frame", nil, row.Content, 400, 14, "TOPLEFT", 5, -22)
            bar.Background = tex(bar, nil, "BACKGROUND")
            bar.LeftTexture, bar.RightTexture = tex(bar, nil, "BORDER"), tex(bar, nil, "BORDER")
            bar.BarText = fstring(bar, nil, "Friendly", 11, { 1, 1, 1, 1 })
            bar.fillTex = tex(bar, nil, "ARTWORK")
            bar.GetMinMaxValues = function() return f.min, f.max end
            bar.GetValue = function() return f.value end
            bar.GetStatusBarTexture = function(self) return self.fillTex end
            bar.UpdateBarValues = function() end
            row.Content.ReputationBar = bar
            row.Content.Name = fstring(row.Content, nil, f.name, 12, { 1, 1, 1, 1 })
            row.Content.BackgroundHighlight = blz("Frame", nil, row.Content, 430, 44)
            tex(row.Content.BackgroundHighlight, nil, "BACKGROUND")
            row.elementData = { reaction = f.reaction, name = f.name }
            row.Initialize = function(self) end
            row.scripts.OnClick = function() end
            row.scripts.OnEnter = function() end
            y = y + 50
        end
        frame.ScrollBox.rows[#frame.ScrollBox.rows + 1] = row
    end
    local d = blz("Frame", nil, frame, 300, 200, "TOPLEFT", 100, -100)
    d.shown = false
    d.Border = blz("Frame", nil, d, 300, 200)
    d.Divider = tex(d, nil, "ARTWORK")
    d.Title = fstring(d, nil, "Thunder Bluff", 14)
    frame.ReputationDetailFrame = d
end
BuildBlizzard()
"""

H = Harness({"Reputation": "Modules/Skins/Reputation.lua", "Character": "Modules/Skins/Character.lua"}, BLIZZARD)
case = H.case

OPEN = "Fire('PLAYER_ENTERING_WORLD'); CharacterFrame:Show(); PaperDollFrame:Hide(); ReputationFrame:Show(); FlushTimers()"


def row(i):
    return f"ReputationFrame.ScrollBox.rows[{i}]"


case("an entry row draws eight segments with a 4 px gap, inside the bar, on whole pixels", f"""
    {OPEN}
    local row = {row(2)}
    local p = FS.ReputationSkin.state.rows[row]
    assert(p and #p.segs == 8, 'no ladder')
    local bar = row.Content.ReputationBar
    local prev
    for i = 1, 8 do
        local l, t, r, b = Px(p.segs[i], bar)
        assert(Near(l, math.floor(l + 0.5), 0.02) and Near(r, math.floor(r + 0.5), 0.02), 'segment ' .. i .. ' off the grid')
        assert(Near(b - t, 8), 'segment height')
        if prev then assert(Near(l - prev, 4), 'gap ' .. (l - prev)) end
        prev = r
    end
    local l1 = Px(p.segs[1], bar)
    local bw = (select(3, Px(bar, bar)))
    local _, _, r8 = Px(p.segs[8], bar)
    assert(Near(l1, 8, 0.02) and Near(bw - r8, 8, 1.01), 'inset ' .. l1 .. ' ' .. (bw - r8))
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("segments below the standing are lit, the standing fills by progress, above are dim", f"""
    {OPEN}
    local row = {row(2)}  -- friendly (5), 2210 of 6000
    local p = FS.ReputationSkin.state.rows[row]
    for i = 1, 4 do assert(p.fills[i].shown, 'segment ' .. i .. ' not lit') end
    local _, _, rr = Px(p.segs[5], row.Content.ReputationBar)
    local l5, _, r5 = Px(p.segs[5], row.Content.ReputationBar)
    local fl, _, fr = Px(p.fills[5], row.Content.ReputationBar)
    local want = math.floor((r5 - l5) * 2210 / 6000 + 0.5)
    assert(Near(fr - fl, want, 1), 'progress width ' .. (fr - fl) .. ' wanted ' .. want)
    for i = 6, 8 do assert(not p.fills[i].shown, 'segment ' .. i .. ' lit above the standing') end
""")

case("an exalted row is fully lit and does not breathe", f"""
    {OPEN}
    local row = {row(7)}
    local p = FS.ReputationSkin.state.rows[row]
    for i = 1, 8 do assert(p.fills[i].shown, 'exalted segment ' .. i) end
    assert(not FS.ControlKit.IsAnimating(row.Content.ReputationBar, 'lead'), 'capped row breathes')
    assert(FS.ControlKit.IsAnimating({row(2)}.Content.ReputationBar, 'lead'), 'leading edge does not breathe')
""")

case("the stock bar art, text and scripts are kept; its name and standing text are restyled", f"""
    {OPEN}
    local row = {row(2)}
    local bar = row.Content.ReputationBar
    assert(bar.Background.alpha == 0 and bar.LeftTexture.alpha == 0 and bar.RightTexture.alpha == 0, 'bar art')
    assert(bar.fillTex.alpha == 0, 'stock fill not held under the ladder')
    assert(row.scripts.OnClick and row.scripts.OnEnter, 'row scripts lost')
    assert(bar.BarText.alpha == 0, 'stock standing text not held')
    local p = FS.ReputationSkin.state.rows[row]
    assert(p.label.text == 'friendly', 'standing text not mirrored: ' .. tostring(p.label.text))
    bar.BarText:SetText('2210 / 6000')
    assert(p.label.text == '2210 / 6000', 'progress text not mirrored')
    assert(row.Content.Name.fontPath ~= 'stock.ttf', 'name not restyled')
    assert(row.Content.BackgroundHighlight.regions[1].alpha == 0, 'stock highlight not held')
""")

case("a header row is restyled and keeps its art held", f"""
    {OPEN}
    local h = {row(1)}
    assert(h.Left.alpha == 0 and h.Middle.alpha == 0 and h.Right.alpha == 0)
    assert(h.Name.fontPath ~= 'stock.ttf' and h.Name.textColor[3] > 0.9, 'header text')
""")

case("a secret or missing standing draws no ladder and leaves the stock bar", f"""
    {OPEN}
    local row = {row(3)}
    row.elementData.reaction = Secret()
    row.Initialize(row)
    FlushTimers()
    local p = FS.ReputationSkin.state.rows[row]
    assert(not p.segs[1].shown, 'ladder drawn for a secret standing')
    row.elementData.reaction = nil
    row.Initialize(row)
    assert(not p.segs[1].shown)
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("a row the scroll list re-initialises is repainted for its new faction", f"""
    {OPEN}
    local row = {row(2)}
    row.elementData.reaction = 3
    row.Initialize(row)
    local p = FS.ReputationSkin.state.rows[row]
    assert(p.reaction == 3, 'repaint')
    assert(p.fills[3].shown and not p.fills[4].shown)
""")

case("the detail pane takes the panel chrome, keeps its parts and writes no script", f"""
    {OPEN}
    local d = ReputationFrame.ReputationDetailFrame
    assert(d.fsRepSkin and d.Divider.alpha == 0, 'detail art')
    assert(d.Border.alpha == 0, 'detail border held')
""")

SCENES = {
    "reputation": "Fire('PLAYER_ENTERING_WORLD'); CharacterFrame:Show(); PaperDollFrame:Hide(); ReputationFrame:Show(); FlushTimers(); FS.CharacterSkin.RefreshHeader(); return DumpOps({ CharacterFrame })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("reputation skin", SCENES))
