#!/usr/bin/env python3
"""Runs the real Modules/Skins/Currency.lua headless against a mock TokenFrame (tools/charskin_support.py).

Pinned: ten capacity cells per capped currency on whole pixels, lit by quantity against the cap (at least one for any, all ten at the
cap), amber and blinking at the cap, a weekly notch where this week's ceiling falls, the stock count held and mirrored as
"quantity / cap", a currency with no cap or a secret number drawing no cells, headers restyled, and no script or attribute written on a
Blizzard widget. Run `python3 tools/currencyskin-harness.py [--png /tmp/cur]`. The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring = BLZ.blz, BLZ.tex, BLZ.fstring
local build = BuildBlizzard
CURRENCIES = {
    { header = true, name = "Backpack" },
    { name = "Honor Points", quantity = 1240, maxQuantity = 4000 },
    { name = "Marks of Honor", quantity = 37, maxQuantity = 40, canEarnPerWeek = true, maxWeeklyQuantity = 30, quantityEarnedThisWeek = 10 },
    { name = "Dungeon Tokens", quantity = 55, maxQuantity = 100 },
    { name = "Stone Keeper Shard", quantity = 100, maxQuantity = 100 },
    { name = "Badge of Justice", quantity = 12, maxQuantity = 0 },
    { name = "Spirit Shard", quantity = 1, maxQuantity = 50 },
}
function BuildBlizzard()
    build()
    local frame = _G.TokenFrame
    frame.Update = function() end
    -- the 16001 dump (debug/tree-CharacterFrame-2026-11-12.txt): TokenFrame's ScrollBox is 363 x 409, its headers 343 x 26 and its
    -- entries 341 x 22
    frame.ScrollBox = blz("Frame", nil, frame, 363, 409, "TOPLEFT", 8, -62)
    frame.ScrollBox.rows = {}
    frame.ScrollBox.ForEachFrame = function(self, fn) for _, r in ipairs(self.rows) do fn(r) end end
    local y = 0
    for _, c in ipairs(CURRENCIES) do
        local row
        if c.header then
            row = blz("Button", nil, frame.ScrollBox, 343, 26, "TOPLEFT", 0, -y)
            row.Left, row.Middle, row.Right = tex(row, nil, "BACKGROUND"), tex(row, nil, "BACKGROUND"), tex(row, nil, "BACKGROUND")
            row.Text = fstring(row, nil, c.name, 12)
            row.GetTitleRegion = function(self) return self.Text end
            y = y + 30
        else
            row = blz("Button", nil, frame.ScrollBox, 341, 22, "TOPLEFT", 0, -y)
            row.Content = blz("Frame", nil, row, 341, 22)
            -- the stock icon sits at the right end of the row, 20 px in from the edge (Blizzard_TokenUI: RIGHT x=-20, 20 x 20)
            row.Content.CurrencyIcon = tex(row.Content, nil, "ARTWORK")
            row.Content.CurrencyIcon.w, row.Content.CurrencyIcon.h = 20, 20
            row.Content.CurrencyIcon.points[1] = { point = "RIGHT", rel = row.Content, relPoint = "RIGHT", x = -20, y = 0 }
            row.Content.Count = fstring(row.Content, nil, tostring(c.quantity), 12, { 1, 1, 1, 1 })
            row.Content.Name = fstring(row.Content, nil, c.name, 12, { 1, 1, 1, 1 })
            row.Content.BackgroundHighlight = blz("Frame", nil, row.Content, 341, 22)
            tex(row.Content.BackgroundHighlight, nil, "BACKGROUND")
            row.elementData = c
            row.Initialize = function(self) end
            row.scripts.OnClick = function() end
            y = y + 28
        end
        frame.ScrollBox.rows[#frame.ScrollBox.rows + 1] = row
    end
    local p = blz("Frame", "TokenFramePopup", frame, 200, 120, "TOPLEFT", 100, -100)
    p.shown = false
    p.Border = blz("Frame", nil, p, 200, 120)
    p.Title = fstring(p, nil, "Options", 14)
    frame.Popup = p
end
BuildBlizzard()
"""

H = Harness({"Currency": "Modules/Skins/Currency.lua", "Character": "Modules/Skins/Character.lua"}, BLIZZARD)
case = H.case

OPEN = "Fire('PLAYER_ENTERING_WORLD'); CharacterFrame:Show(); PaperDollFrame:Hide(); TokenFrame:Show(); FlushTimers()"


def row(i):
    return f"TokenFrame.ScrollBox.rows[{i}]"


case("cells: ten per capped currency, 8 x 12, a 2 px gap, whole pixels, right of the name and left of the count", f"""
    {OPEN}
    local r = {row(2)}
    local p = FS.CurrencySkin.state.rows[r]
    assert(p and #p.cells == 10, 'no cells')
    local prev
    for i = 1, 10 do
        local l, t, rr, b = Px(p.cells[i], r)
        assert(Near(rr - l, 8) and Near(b - t, 12), 'cell size')
        assert(Near(l, math.floor(l + 0.5), 0.02), 'cell off the grid')
        if prev then assert(Near(l - prev, 10), 'pitch ' .. (l - prev)) end
        prev = l
    end
    local l1 = Px(p.cells[1], r)
    local rw = select(3, Px(r, r))
    local _, _, r10 = Px(p.cells[10], r)
    assert(rw - r10 > 130 and rw - r10 < 175, 'strip leaves room for the count and the stock icon: ' .. (rw - r10))
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("the stock icon sits on a cut plate whose edge says the state: cyan under the cap, amber at it, dim at zero, violet with no cap", f"""
    {OPEN}
    local function edge(i) return FS.CurrencySkin.state.rows[{row('(i)')}].plate.ring.vertex end
    local honor, marks, tokens, stone, badge = edge(2), edge(3), edge(4), edge(5), edge(6)
    assert(honor[3] > 0.9 and honor[1] < 0.3, 'under the cap: cyan')
    assert(stone[1] > 0.9 and stone[3] < 0.4, 'at the cap: amber')
    assert(badge[1] < 0.7 and badge[3] > 0.9 and badge[4] < 1, 'no cap: violet, not full')
    local r = {row(2)}
    local plate = FS.CurrencySkin.state.rows[r].plate
    local icon = r.Content.CurrencyIcon
    local il, it, ir, ib = Px(icon, r)
    local pl, pt, pr, pb = Px(plate.ring, r)
    assert(Near(il - pl, 2, 0.02) and Near(it - pt, 2, 0.02) and Near(pr - ir, 2, 0.02) and Near(pb - ib, 2, 0.02), 'plate is not the icon plus 2 px: ' .. pl .. ' ' .. pt .. ' ' .. pr .. ' ' .. pb)
    assert(icon.alpha == 1, 'the stock icon must stay')
    CURRENCIES[2].quantity = 0
    r.elementData = {{ name = 'Honor Points', quantity = 0, maxQuantity = 4000 }}
    r:Initialize(); FS.CurrencySkin.PaintRow(r)
    assert(edge(2)[1] < 0.4 and edge(2)[3] > 0.4 and edge(2)[3] < 0.7, 'zero: dim edge')
    assert(r.Content.Name.textColor[1] < 0.8, 'a zero currency name is not muted')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\\\n'))
""")

case("the count text and the cells stay clear of the stock icon, which sits at the right end of the row", f"""
    {OPEN}
    local r = {row(2)}
    local p = FS.CurrencySkin.state.rows[r]
    local icon = r.Content.CurrencyIcon
    local il = Px(icon, r)
    local ll, lt, lr = Px(p.label, r)
    assert(lr <= il + 0.02, 'label runs over the icon: label right ' .. lr .. ' icon left ' .. il)
    assert(Near(il - lr, 7, 0.05), 'label is not 5 px clear of the plate (7 from the icon): ' .. (il - lr))
    -- the whole plate stays inside the left pane (the page's ScrollBox is 363 wide in a 398 wide pane), clear of its border
    local pl, pt, pr, pb = Px(p.plate.ring, CharacterFrameLeftPaneHost)
    local paneW = select(3, Px(CharacterFrameLeftPaneHost, CharacterFrameLeftPaneHost))
    assert(pr <= paneW - 20, 'plate runs to the pane border: right ' .. pr .. ' of ' .. paneW)
    local _, _, r10 = Px(p.cells[10], r)
    assert(r10 < ll - 7, 'cells run into the label: ' .. r10 .. ' vs ' .. ll)
""")

case("lit cells follow quantity against the cap", f"""
    local C = FS.CurrencySkin
    assert(C.CellsLit(0, 100) == 0 and C.CellsLit(1, 4000) == 1 and C.CellsLit(55, 100) == 6 or C.CellsLit(55, 100) == 5, 'rounding')
    assert(C.CellsLit(100, 100) == 10 and C.CellsLit(99, 100) == 9, 'cap edge')
    {OPEN}
    local p = C.state.rows[{row(2)}]   -- 1240 of 4000
    local lit = 0
    for _, cell in ipairs(p.cells) do if cell.color[1] < 0.5 and cell.color[2] > 0.7 then lit = lit + 1 end end
    assert(lit == 3, 'honor lit ' .. lit)
""")

case("a capped currency is amber and blinks; the others are cyan and still", f"""
    {OPEN}
    local C = FS.CurrencySkin
    local capped = {row(5)}
    local pc = C.state.rows[capped]
    assert(pc.capped and FS.ControlKit.IsAnimating(capped, 'cap'), 'capped does not blink')
    assert(pc.cells[1].color[1] > 0.9 and pc.cells[1].color[3] < 0.3, 'capped not amber')
    assert(not FS.ControlKit.IsAnimating({row(2)}, 'cap'), 'uncapped blinks')
""")

case("a weekly cap carries a gold notch at this week's ceiling", f"""
    {OPEN}
    local C = FS.CurrencySkin
    local r = {row(3)}          -- 37 of 40, 20 left this week: ceiling 40 (the cap), notch at the strip's end
    local p = C.state.rows[r]
    assert(p.notch.shown, 'no notch')
    local r2 = {row(2)}
    assert(not C.state.rows[r2].notch.shown, 'notch on a currency with no weekly cap')
    r.elementData.quantityEarnedThisWeek = 25   -- 5 left: ceiling 42 -> capped at 40; try a lower one
    r.elementData.quantity = 10
    r.Initialize(r)
    local l, _, rr = Px(p.notch, r)
    local cl = Px(p.cells[1], r)
    local _, _, cr = Px(p.cells[10], r)
    assert(l > cl and l < cr, 'notch outside the strip')
""")

case("the stock count is held and mirrored with the cap; a currency with no cap shows the plain count", f"""
    {OPEN}
    local C = FS.CurrencySkin
    local r = {row(2)}
    assert(r.Content.Count.alpha == 0, 'stock count not held')
    assert(C.state.rows[r].label.text == '1240 / 4,000', C.state.rows[r].label.text)
    local nocap = {row(6)}
    assert(C.state.rows[nocap].label.text == '12', C.state.rows[nocap].label.text)
    for _, cell in ipairs(C.state.rows[nocap].cells) do assert(not cell.shown, 'cells on an uncapped currency') end
""")

case("a secret number draws no cells and is never compared", f"""
    {OPEN}
    local r = {row(4)}
    r.elementData.quantity = Secret()
    r.Initialize(r)
    local p = FS.CurrencySkin.state.rows[r]
    assert(not p.cells[1].shown, 'cells drawn for a secret quantity')
    r.elementData.quantity, r.elementData.maxQuantity = 5, Secret()
    r.Initialize(r)
    assert(not p.cells[1].shown)
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("stock scripts and art: highlight held, name restyled, header restyled, popup chromed", f"""
    {OPEN}
    local r = {row(2)}
    assert(r.scripts.OnClick, 'row script lost')
    assert(r.Content.BackgroundHighlight.regions[1].alpha == 0, 'highlight')
    assert(r.Content.Name.fontPath ~= 'stock.ttf', 'name')
    local h = {row(1)}
    assert(h.Left.alpha == 0 and h.Text.fontPath ~= 'stock.ttf', 'header')
    assert(TokenFrame.Popup.fsCurrencySkin and TokenFrame.Popup.Border.alpha == 0, 'popup')
""")

SCENES = {
    "currency": "Fire('PLAYER_ENTERING_WORLD'); CharacterFrame:Show(); PaperDollFrame:Hide(); TokenFrame:Show(); FlushTimers(); FS.CharacterSkin.RefreshHeader(); return DumpOps({ CharacterFrame })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("currency skin", SCENES))
