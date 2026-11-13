#!/usr/bin/env python3
"""Runs the real Modules/Skins/PvP.lua (and GroupKit.lua) headless against mock match windows (tools/charskin_support.py).

Pinned: both windows (PVPMatchScoreboard, PVPMatchResults) get the panel chrome and a band title, the stock art is held, and the border
pieces the stock Init makes later are held too while the chrome is not; the table well and tab bar art are held; each score row is an
ink card with a left bar in the colour of the stock team wash (blue cyan, red pink, gold amber, purple violet) that follows the stock
Populate, the stock wash is held, the cell labels are mono and the class icon and clicks are kept; the column headings the stock Init
makes are mono; a row the pool makes later is carded; the end of match window restyles its result line and reward lines, holds its
decoration and earnings art, and gives Requeue and Leave their keys; no script or attribute is written on a Blizzard widget, and nothing
is built in combat. Run `python3 tools/pvpskin-harness.py [--png debug/pvp]`. The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring = BLZ.blz, BLZ.tex, BLZ.fstring
local build = BuildBlizzard

local RED, BLUE, GOLD, PURPLE = { 0.7, 0.1, 0.1 }, { 0.1, 0.3, 0.8 }, { 0.8, 0.7, 0.1 }, { 0.5, 0.1, 0.8 }
local ROW_ART = { "backgroundLeft", "backgroundRight", "backgroundCenter" }

local function scrollBox(parent, w, h, x, y)
    local box = blz("Frame", nil, parent, w, h, "TOPLEFT", x, y)
    box.rows = {}
    box.ForEachFrame = function(self, fn) for _, r in ipairs(self.rows) do fn(r) end end
    box.Update, box.FullUpdate, box.SetDataProvider = function() end, function() end, function() end
    box.Background = tex(box, nil, "BACKGROUND")
    return box
end

-- PVPTableRowTemplate with the cells the table builder makes: a name button, a class icon, a stat
local function scoreRow(box, i, tint, name, stat)
    local r = blz("Frame", nil, box, 960, 16, "TOPLEFT", 0, -(i - 1) * 18)
    for _, k in ipairs(ROW_ART) do
        r[k] = tex(r, nil, "BACKGROUND")
        r[k].GetVertexColor = function(self) return unpack(self.vertex or { 1, 1, 1, 1 }) end
    end
    r.tint = tint
    function r:Populate()
        for _, k in ipairs(ROW_ART) do self[k]:SetVertexColor(self.tint[1], self.tint[2], self.tint[3]) end
    end
    r:Populate()
    local class = blz("Frame", nil, r, 16, 16, "LEFT", 4, 0)
    class.icon = tex(class, nil, "BACKGROUND"); class.icon.w, class.icon.h = 16, 16
    local who = blz("Button", nil, r, 220, 16, "LEFT", 30, 0)
    who.text = fstring(who, nil, name, 12, { 1, 1, 1, 1 })
    who.text.points[1] = { point = "LEFT", rel = who, relPoint = "LEFT", x = 0, y = 0 }
    who.scripts.OnClick = function() end
    who.scripts.OnEnter = function() end
    local cell = blz("Frame", nil, r, 80, 16, "LEFT", 500, 0)
    cell.text = fstring(cell, nil, stat, 12, { 1, 1, 1, 1 })
    cell.text.points[1] = { point = "CENTER", rel = cell, relPoint = "CENTER", x = 0, y = 0 }
    box.rows[#box.rows + 1] = r
    return r
end

local function heading(parent, x, label)
    local h = blz("Button", nil, parent, 80, 18, "TOPLEFT", x, -2)
    h.text = fstring(h, nil, label, 12, { 1, 0.82, 0, 1 })
    h.text.points[1] = { point = "CENTER", rel = h, relPoint = "CENTER", x = 0, y = 0 }
    h.scripts.OnClick = function() end
    return h
end

-- the nine slice pieces of the faction border are made when a match starts
local function setupArtwork(self)
    if not self.TopLeftCorner then
        self.TopLeftCorner = tex(self, nil, "BORDER")
        self.TopRightCorner = tex(self, nil, "BORDER")
    end
end

local function panelButton(parent, name, label, x)
    local b = blz("Button", name, parent, 150, 21, "TOPLEFT", x, 0)
    b.Left = tex(b, nil, "BACKGROUND"); b.Middle = tex(b, nil, "BACKGROUND"); b.Right = tex(b, nil, "BACKGROUND")
    b.Text = fstring(b, nil, label, 12, { 1, 0.82, 0, 1 })
    b.Text.points[1] = { point = "CENTER", rel = b, relPoint = "CENTER", x = 0, y = 0 }
    b.GetFontString = function(self) return self.Text end
    b.GetText = function(self) return self.Text.text end
    b.scripts.OnClick = function() end
    return b
end

local function closeKey(win)
    local close = blz("Button", nil, win, 24, 24, "TOPRIGHT", 3, 3)
    close.NormalTexture = tex(close, nil, "ARTWORK")
    close.scripts.OnClick = function() end
    win.CloseButton = close
end

function BuildBlizzard()
    build()
    for k in pairs(_G) do
        if type(k) == "string" and k:find("^PVPMatch") then _G[k] = nil end
    end

    -- the scoreboard
    local sb = blz("Frame", "PVPMatchScoreboard", UIParent, 1024, 420)
    sb.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 60, y = -60 }
    sb.shown = false
    tex(sb, nil, "BACKGROUND")
    closeKey(sb)
    local c = blz("Frame", nil, sb, 964, 350, "TOPLEFT", 30, -35)
    sb.Content = c
    c.Background = tex(c, nil, "BACKGROUND")
    c.InsetBorderTopLeft = tex(c, nil, "OVERLAY")
    c.InsetBorderTop = tex(c, nil, "OVERLAY")
    c.ScrollCategories = blz("Frame", nil, c, 930, 50, "TOPLEFT", 3, -3)
    c.ScrollBox = scrollBox(c, 930, 256, 3, -53)
    scoreRow(c.ScrollBox, 1, BLUE, "Stu", "38.2k")
    scoreRow(c.ScrollBox, 2, RED, "Gorak", "36.4k")
    scoreRow(c.ScrollBox, 3, BLUE, "Mira", "29.8k")
    c.TabContainer = blz("Frame", nil, c, 964, 45, "BOTTOMLEFT", 0, 0)
    c.TabContainer.InsetBorderTop = tex(c.TabContainer, nil, "ARTWORK")
    c.TabContainer.MatchmakingText = fstring(c.TabContainer, nil, "Matchmaking", 12, { 1, 0.82, 0, 1 })
    sb.SetupArtwork = setupArtwork
    sb.UpdateTable = function() end
    function sb:Init()
        if self.isInitialized then return end
        self.isInitialized = true
        heading(self.Content.ScrollCategories, 600, "Killing Blows")
        heading(self.Content.ScrollCategories, 700, "Damage")
        self:SetupArtwork()
    end

    -- the end of match window
    local res = blz("Frame", "PVPMatchResults", UIParent, 1024, 620)
    res.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 60, y = -60 }
    res.shown = false
    tex(res, nil, "BACKGROUND")
    res.glowTop = tex(res, nil, "BORDER")
    res.header = fstring(res, nil, "Victory", 42, { 1, 0.82, 0, 1 })
    res.header.points[1] = { point = "TOP", rel = res, relPoint = "TOP", x = 0, y = -25 }
    closeKey(res)
    res.overlay = blz("Frame", nil, res, 1024, 620)
    res.overlay.decorator = tex(res.overlay, nil, "ARTWORK")
    local rc = blz("Frame", nil, res, 964, 430, "TOPLEFT", 30, -90)
    res.content = rc
    rc.background = tex(rc, nil, "BACKGROUND")
    rc.InsetBorderTopLeft = tex(rc, nil, "OVERLAY")
    rc.scrollCategories = blz("Frame", nil, rc, 930, 50, "TOPLEFT", 3, -3)
    rc.scrollBox = scrollBox(rc, 930, 256, 3, -53)
    scoreRow(rc.scrollBox, 1, PURPLE, "Stu", "12")
    scoreRow(rc.scrollBox, 2, GOLD, "Aldric", "9")
    rc.tabContainer = blz("Frame", nil, rc, 964, 42, "TOPLEFT", 0, -310)
    rc.tabContainer.InsetBorderTop = tex(rc.tabContainer, nil, "ARTWORK")
    rc.tabContainer.matchmakingText = fstring(rc.tabContainer, nil, "Matchmaking", 12, { 1, 0.82, 0, 1 })
    local art = blz("Frame", nil, rc, 964, 100, "TOPLEFT", 0, -352)
    rc.earningsArt = art
    art.background = tex(art, nil, "ARTWORK")
    art.OrangeGlow = tex(art, nil, "OVERLAY")
    local earn = blz("Frame", nil, rc, 600, 100, "TOPLEFT", 120, -360)
    rc.earningsContainer = earn
    earn.rewardsContainer = blz("Frame", nil, earn, 200, 80, "TOPLEFT", 0, 0)
    earn.rewardsContainer.header = fstring(earn.rewardsContainer, nil, "Item rewards", 12, { 1, 0.82, 0, 1 })
    earn.progressContainer = blz("Frame", nil, earn, 300, 80, "TOPLEFT", 250, 0)
    earn.progressContainer.header = fstring(earn.progressContainer, nil, "Progress", 12, { 1, 0.82, 0, 1 })
    for i, k in ipairs({ "honor", "conquest", "rating" }) do
        local line = blz("Frame", nil, earn.progressContainer, 90, 30, "TOPLEFT", (i - 1) * 95, -24)
        line.text = fstring(line, nil, "+312 honor", 12, { 1, 0.82, 0, 1 })
        earn.progressContainer[k] = line
    end
    res.buttonContainer = blz("Frame", nil, res, 340, 40, "TOP", 0, -540)
    res.buttonContainer.points[1] = { point = "TOPLEFT", rel = res, relPoint = "TOPLEFT", x = 300, y = -540 }
    res.buttonContainer.requeueButton = panelButton(res.buttonContainer, nil, "Queue Again", 0)
    res.buttonContainer.leaveButton = panelButton(res.buttonContainer, nil, "Leave Match", 180)
    res.SetupArtwork = setupArtwork
    function res:Init()
        if self.isInitialized then return end
        self.isInitialized = true
        heading(self.content.scrollCategories, 600, "Damage")
        self:SetupArtwork()
    end
end
"""

H = Harness({
    "ButtonSkins": "Core/ButtonSkins.lua",
    "Character": "Modules/Skins/Character.lua",
    "GroupKit": "Modules/Skins/GroupKit.lua",
    "PvP": "Modules/Skins/PvP.lua",
}, BLIZZARD)
case = H.case

SHOW = "Fire('PLAYER_ENTERING_WORLD'); PVPMatchScoreboard:Show(); PVPMatchResults:Show(); FlushTimers()"

case("windows: the panel chrome and band title are on, the stock art is held, the close key is skinned", f"""
    {SHOW}
    local P = FS.PvPSkin.state
    for _, spec in ipairs({{ {{ 'PVPMatchScoreboard', 'stuwave://scoreboard' }}, {{ 'PVPMatchResults', 'stuwave://match results' }} }}) do
        local w = _G[spec[1]]
        assert(w.fsPanelTitle and w.fsPanelTitle.text == spec[2], spec[1] .. ' no band title')
        assert(P.windows[w] and w.fsPvPSkin, spec[1] .. ' not marked')
        assert(w.regions[1].alpha == 0, spec[1] .. ' stock background kept')
        assert(FS.ButtonSkins.Parts(w.CloseButton), spec[1] .. ' close key not skinned')
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("windows: the border pieces the stock Init makes later are held, the chrome is not", f"""
    {SHOW}
    local w = PVPMatchScoreboard
    assert(not w.TopLeftCorner, 'pieces exist before the match starts')
    w:Init()
    assert(w.TopLeftCorner and w.TopLeftCorner.alpha == 0 and w.TopRightCorner.alpha == 0, 'late border pieces kept')
    local n = 0
    for region in pairs(FS.PvPSkin.state.keep[w]) do
        n = n + 1
        assert(region.alpha ~= 0, 'chrome held')
    end
    assert(n > 0, 'no chrome recorded')
    local r = PVPMatchResults
    r:Init()
    assert(r.TopLeftCorner.alpha == 0, 'results border pieces kept')
""")

case("table well: the content art and tab bar art are held, a ring is drawn, the tab text and the row wash are restyled", f"""
    {SHOW}
    local c = PVPMatchScoreboard.Content
    assert(c.Background.alpha == 0 and c.InsetBorderTopLeft.alpha == 0 and c.InsetBorderTop.alpha == 0, 'content art kept')
    assert(c.ScrollBox.Background.alpha == 0, 'scroll box wash kept')
    assert(c.TabContainer.InsetBorderTop.alpha == 0, 'tab bar art kept')
    assert(c.TabContainer.MatchmakingText.fontPath ~= 'stock.ttf', 'matchmaking text not mono')
    local rc = PVPMatchResults.content
    assert(rc.background.alpha == 0 and rc.scrollBox.Background.alpha == 0 and rc.tabContainer.InsetBorderTop.alpha == 0, 'results art kept')
""")

case("headings: the column headings the stock Init makes are restyled, the click kept", f"""
    {SHOW}
    local w = PVPMatchScoreboard
    w:Init()
    local n = 0
    for _, h in ipairs({{ w.Content.ScrollCategories:GetChildren() }}) do
        n = n + 1
        assert(h.text.fontPath ~= 'stock.ttf', 'heading ' .. n .. ' not mono')
        assert(h.scripts.OnClick, 'sort click lost')
    end
    assert(n == 2, 'headings ' .. n)
""")

case("rows: each score row is an ink card, the stock wash held, the labels mono, the class icon and clicks kept", f"""
    {SHOW}
    local P, G = FS.PvPSkin.state, FS.GroupSkin
    for i, r in ipairs(PVPMatchScoreboard.Content.ScrollBox.rows) do
        assert(P.rows[r] and G.cards[r], 'row ' .. i .. ' not carded')
        assert(r.backgroundLeft.alpha == 0 and r.backgroundRight.alpha == 0 and r.backgroundCenter.alpha == 0, 'wash kept on row ' .. i)
        for _, cell in ipairs({{ r:GetChildren() }}) do
            if cell.text then assert(cell.text.fontPath ~= 'stock.ttf', 'cell label not mono on row ' .. i) end
            if cell.icon then assert(cell.icon.alpha == 1, 'class icon held on row ' .. i) end
        end
    end
    local name = PVPMatchScoreboard.Content.ScrollBox.rows[1]:GetChildren()
    assert(select(2, PVPMatchScoreboard.Content.ScrollBox.rows[1]:GetChildren()).scripts.OnClick, 'name click lost')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("rows: the left bar takes the colour of the stock team wash and follows the stock Populate", f"""
    {SHOW}
    local P, T = FS.PvPSkin.state, FS.Theme
    local function led(r) local c = P.rows[r].led.t.color; return c[1], c[2], c[3] end
    local function same(r, want) local a, b, c = led(r); return math.abs(a - want[1]) < 0.01 and math.abs(b - want[2]) < 0.01 and math.abs(c - want[3]) < 0.01 end
    local rows = PVPMatchScoreboard.Content.ScrollBox.rows
    assert(same(rows[1], T.COLOR_POWER), 'blue wash is not cyan')
    assert(same(rows[2], T.COLOR_HEALTH), 'red wash is not pink')
    local res = PVPMatchResults.content.scrollBox.rows
    assert(same(res[1], T.COLOR_BORDER), 'purple wash is not violet')
    assert(same(res[2], T.COLOR_AMBER), 'gold wash is not amber')
    rows[1].tint = {{ 0.7, 0.1, 0.1 }}
    rows[1]:Populate()
    assert(same(rows[1], T.COLOR_HEALTH), 'bar did not follow Populate')
""")

case("rows: hover lights the edge", f"""
    {SHOW}
    local r = PVPMatchScoreboard.Content.ScrollBox.rows[1]
    local rec = FS.GroupSkin.cards[r]
    local idle = rec.box.edges[1].color[2]
    r:RunScript('OnEnter')
    assert(rec.box.edges[1].color[2] > idle, 'hover did not light the edge')
    r:RunScript('OnLeave')
""")

case("rows: a row the pool makes later is carded when the list updates", f"""
    {SHOW}
    local box = PVPMatchScoreboard.Content.ScrollBox
    local late = CreateFrame('Frame', nil, box)
    late.backgroundLeft = late:CreateTexture(nil, 'BACKGROUND')
    late.backgroundLeft.blizz = true
    box.rows[#box.rows + 1] = late
    box:Update()
    assert(FS.PvPSkin.state.rows[late], 'late row not carded')
    assert(late.backgroundLeft.alpha == 0, 'late wash kept')
""")

case("results: the result line, reward lines and art are restyled, Requeue is cyan and Leave pink", f"""
    {SHOW}
    local r = PVPMatchResults
    assert(r.header.fontPath ~= 'stock.ttf', 'result line not mono')
    assert(r.overlay.decorator.alpha == 0, 'decoration kept')
    local art = r.content.earningsArt
    assert(art.background.alpha == 0 and art.OrangeGlow.alpha == 0, 'earnings art kept')
    local e = r.content.earningsContainer
    assert(e.rewardsContainer.header.fontPath ~= 'stock.ttf' and e.progressContainer.header.fontPath ~= 'stock.ttf', 'headings not mono')
    for _, k in ipairs({{ 'honor', 'conquest', 'rating' }}) do assert(e.progressContainer[k].text.fontPath ~= 'stock.ttf', k .. ' line not mono') end
    local keys = r.buttonContainer
    local requeue, leave = FS.ButtonSkins.Parts(keys.requeueButton), FS.ButtonSkins.Parts(keys.leaveButton)
    assert(requeue and leave, 'keys not skinned')
    assert(requeue.accent == 'cyan' and leave.accent == 'pink', 'accents ' .. tostring(requeue.accent) .. ' ' .. tostring(leave.accent))
    assert(keys.leaveButton.scripts.OnClick and keys.requeueButton.scripts.OnClick, 'click lost')
""")

case("the sweep for the tabs, scroll bar and text buttons is on both windows", f"""
    {SHOW}
    assert(PVPMatchScoreboard.fsSweepHook and PVPMatchResults.fsSweepHook, 'windows not swept on show')
""")

case("nothing is built in combat; it is built when combat ends", """
    Reset()
    __combat = true
    FS = Load({ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'ButtonSkins', 'Character', 'GroupKit', 'PvP' })
    local first = PVPMatchScoreboard.Content.ScrollBox.rows[1]
    assert(not PVPMatchScoreboard.fsPvPSkin and not FS.PvPSkin.state.rows[first], 'built in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(PVPMatchScoreboard.fsPvPSkin and FS.PvPSkin.state.rows[first], 'not built when combat ended')
""")

case("a client without one of the windows degrades quietly, and a second build adds nothing", f"""
    {SHOW}
    local r = PVPMatchScoreboard.Content.ScrollBox.rows[1]
    local n = #r.regions
    FS.PvPSkin.Build(); PVPMatchScoreboard.Content.ScrollBox:Update(); FlushTimers()
    assert(#r.regions == n, 'regions grew')
    PVPMatchResults = nil
    FS.PvPSkin.Build()
    PVPMatchScoreboard = nil
    FS.PvPSkin.Build()
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

SCENES = {
    "scoreboard": "Fire('PLAYER_ENTERING_WORLD'); PVPMatchScoreboard:Init(); PVPMatchScoreboard:Show(); FlushTimers(); return DumpOps({ PVPMatchScoreboard })",
    "results": "Fire('PLAYER_ENTERING_WORLD'); PVPMatchResults:Init(); PVPMatchResults:Show(); FlushTimers(); return DumpOps({ PVPMatchResults })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("pvp skin", SCENES))
