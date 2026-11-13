#!/usr/bin/env python3
"""Runs the real Modules/Skins/LookingForGroup.lua with the real shared kits (tools/charskin_support.py) against a mock group finder.

tools/lfgskin-harness.py pins the window chrome, the text buttons, the scroll bar and the category rings against a stub of the
shared skins. This one adds what needs the real kits: the Browse page's result rows become ink cards (stock row art held, labels in
mono, the role icons kept, a row the pool makes later skinned too), the controls sweep reaches the window, the scroll bar sweep never
does (the Listing activity bar stays stock), and no script or attribute is written on a Blizzard widget. Run
`python3 tools/lfgrows-harness.py [--png debug/lfg]`. The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring = BLZ.blz, BLZ.tex, BLZ.fstring
local build = BuildBlizzard
FILTER = "Filter"

local function resultRow(parent, y, name, comment, locked)
    local b = blz("Button", nil, parent, 330, 40, "TOPLEFT", 0, -y)
    b.Background = tex(b, nil, "BACKGROUND")
    b.Highlight = tex(b, nil, "HIGHLIGHT")
    b.Name = fstring(b, nil, name, 12, { 1, 0.82, 0, 1 })
    b.Name.points[1] = { point = "TOPLEFT", rel = b, relPoint = "TOPLEFT", x = 8, y = -6 }
    b.Comment = fstring(b, nil, comment, 11, { 0.7, 0.7, 0.7, 1 })
    b.Comment.points[1] = { point = "TOPLEFT", rel = b, relPoint = "TOPLEFT", x = 8, y = -22 }
    b.TankIcon = tex(b, nil, "ARTWORK"); b.TankIcon.w, b.TankIcon.h = 16, 16
    b.TankIcon.points[1] = { point = "RIGHT", rel = b, relPoint = "RIGHT", x = -8, y = 0 }
    b.scripts.OnClick = function() end
    b.scripts.OnEnter = function() end
    b.LockHighlight = function(self) self.locked = true end
    b.UnlockHighlight = function(self) self.locked = false end
    parent.rows[#parent.rows + 1] = b
    return b
end

function BuildBlizzard()
    build()
    for k in pairs(_G) do
        if type(k) == "string" and (k:find("^LFG") or k:find("^Blizzard_Group")) then _G[k] = nil end
    end
    local win = blz("Frame", "LFGParentFrame", UIParent, 420, 500)
    win.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 100, y = -80 }
    win.shown = false
    tex(win, "LFGParentFramePortrait", "ARTWORK")
    local close = blz("Button", "LFGParentFrameCloseButton", win, 15, 15, "TOPRIGHT", -6, -4)
    tex(close, nil, "BACKGROUND")
    win.CloseButton = close
    local browse = blz("Frame", "LFGBrowseFrame", win, 420, 480, "TOPLEFT", 0, -20)
    tex(browse, "LFGBrowseFrameBg", "BACKGROUND")
    tex(browse, "LFGBrowseFrameBackgroundArt", "BACKGROUND")
    local box = blz("Frame", "LFGBrowseFrameScrollBox", browse, 350, 320, "TOPLEFT", 10, -90)
    box.rows = {}
    box.ForEachFrame = function(self, fn) for _, r in ipairs(self.rows) do fn(r) end end
    box.Update, box.FullUpdate, box.SetDataProvider = function() end, function() end, function() end
    resultRow(box, 0, "Deadmines run", "need tank", false)
    resultRow(box, 44, "Wailing Caverns", "all welcome", false)
    local listing = blz("Frame", "LFGListingFrame", win, 420, 480, "TOPLEFT", 0, -20)
    listing.shown = false
    tex(listing, "LFGListingFrameBg", "BACKGROUND")
    local who = blz("Frame", "LFGWhoListFrame", win, 420, 480, "TOPLEFT", 0, -20)
    who.shown = false
    tex(who, "LFGWhoListFrameBg", "BACKGROUND")
    -- a scroll bar the listing page owns: must stay stock
    local bar = blz("Frame", "LFGListingFrameActivityViewScrollBar", listing, 12, 300, "TOPRIGHT", -4, -60)
    bar.Track = blz("Frame", nil, bar, 12, 300)
end
"""

H = Harness({
    "ButtonSkins": "Core/ButtonSkins.lua",
    "ScrollBarSkins": "Core/ScrollBarSkins.lua",
    "Character": "Modules/Skins/Character.lua",
    "Commerce": "Modules/Skins/Commerce.lua",
    "GroupKit": "Modules/Skins/GroupKit.lua",
    "LookingForGroup": "Modules/Skins/LookingForGroup.lua",
}, BLIZZARD)
case = H.case

SHOW = "Fire('PLAYER_ENTERING_WORLD'); LFGParentFrame:Show(); FlushTimers()"

case("browse rows: each result is an ink card, the stock row art held, the labels mono, the role icon and clicks kept", f"""
    {SHOW}
    local G = FS.GroupSkin
    for i, r in ipairs(LFGBrowseFrameScrollBox.rows) do
        assert(G.cards[r], 'row ' .. i .. ' not carded')
        assert(r.Background.alpha == 0 and r.Highlight.alpha == 0, 'stock row art kept on row ' .. i)
        assert(r.Name.fontPath ~= 'stock.ttf' and r.Comment.fontPath ~= 'stock.ttf', 'labels not mono on row ' .. i)
        assert(r.TankIcon.alpha == 1, 'role icon held on row ' .. i)
        assert(r.scripts.OnClick and r.scripts.OnEnter, 'click lost on row ' .. i)
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("browse rows: a row the pool makes later is carded when the list updates", f"""
    {SHOW}
    local box = LFGBrowseFrameScrollBox
    local late = box.rows[1]
    local extra = CreateFrame('Button', nil, box)
    extra.Background = extra:CreateTexture(nil, 'BACKGROUND')
    extra.Background.blizz = true
    box.rows[#box.rows + 1] = extra
    box:Update()
    assert(FS.GroupSkin.cards[extra], 'late row not carded')
""")

case("browse rows: hover and selection light the edge", f"""
    {SHOW}
    local r = LFGBrowseFrameScrollBox.rows[1]
    local rec = FS.GroupSkin.cards[r]
    local idle = rec.box.edges[1].color
    local idleB = idle[3]
    r:RunScript('OnEnter')
    assert(rec.box.edges[1].color[3] > idleB or rec.box.edges[1].color[2] > idle[2], 'hover did not light the edge')
    r:RunScript('OnLeave')
    r:LockHighlight()
    assert(rec.selected, 'selection not followed')
""")

case("the controls sweep reaches the window and the scroll bar sweep never does", f"""
    {SHOW}
    local sweeps, bars = 0, 0
    local P = FS.PanelSkins
    local controls, scroll = P.SweepControls, P.SweepScrollBars
    P.SweepControls = function(frame) if frame == LFGParentFrame then sweeps = sweeps + 1 end return controls(frame) end
    P.SweepScrollBars = function(frame) if frame == LFGParentFrame or frame == LFGListingFrame then bars = bars + 1 end return scroll(frame) end
    Fire('PLAYER_ENTERING_WORLD'); FlushTimers()
    assert(sweeps >= 1, 'controls not swept')
    assert(bars == 0, 'scroll bars swept: ' .. bars)
    assert(not (FS.ScrollBarSkins.Parts and FS.ScrollBarSkins.Parts(LFGListingFrameActivityViewScrollBar)), 'activity bar skinned')
""")

case("a client without the shared group kit still gets the chrome and logs nothing", f"""
    FS = Load({{ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'ButtonSkins', 'ScrollBarSkins', 'LookingForGroup' }})
    Fire('PLAYER_ENTERING_WORLD'); LFGParentFrame:Show(); FlushTimers()
    assert(LFGParentFramePortrait.shown == false or LFGParentFramePortrait.alpha == 0, 'chrome not applied')
    assert(not FS.GroupSkin, 'group kit should be absent')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

SCENES = {
    "lfg": "Fire('PLAYER_ENTERING_WORLD'); LFGParentFrame:Show(); LFGBrowseFrameScrollBox.rows[2]:LockHighlight(); FlushTimers(); return DumpOps({ LFGParentFrame })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("lfg rows", SCENES))
