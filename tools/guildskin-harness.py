#!/usr/bin/env python3
"""Runs the real Modules/Skins/Guild.lua (and GroupKit.lua) headless against a mock guild window (tools/charskin_support.py).

Pinned: the roster rows are ink cards (stock row art held, labels mono, class icon and clicks kept), the column headings are band keys
with their nine slice frames held and a late heading is caught, the column display and the insets are held, the community list entries
are cards that light with the stock selection, the guild pages lose their inset border art, the three pop ups wear the panel skin,
no script or attribute is written on a Blizzard widget, and nothing is built in combat. Run
`python3 tools/guildskin-harness.py [--png debug/guild]`. The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring = BLZ.blz, BLZ.tex, BLZ.fstring
local build = BuildBlizzard

local function scrollBox(parent, w, h, x, y)
    local box = blz("Frame", nil, parent, w, h, "TOPLEFT", x, y)
    box.rows = {}
    box.ForEachFrame = function(self, fn) for _, r in ipairs(self.rows) do fn(r) end end
    box.Update, box.FullUpdate, box.SetDataProvider = function() end, function() end, function() end
    return box
end

local function inset(parent, w, h, x, y)
    local f = blz("Frame", nil, parent, w, h, "TOPLEFT", x, y)
    f.NineSlice = blz("Frame", nil, f, w, h)
    f.Bg = tex(f, nil, "BACKGROUND")
    return f
end

local function at(fs, rel, point, x)
    fs.points[1] = { point = point, rel = rel, relPoint = point, x = x, y = 0 }
    return fs
end

function BuildBlizzard()
    build()
    for k in pairs(_G) do
        if type(k) == "string" and (k:find("^Communities") or k:find("^ClubFinder")) then _G[k] = nil end
    end
    local win = blz("Frame", "CommunitiesFrame", UIParent, 814, 426)
    win.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 60, y = -60 }
    win.shown = false
    win.Bg = tex(win, nil, "BACKGROUND")
    win.NineSlice = blz("Frame", nil, win, 814, 426)
    win.TitleContainer = blz("Frame", nil, win, 760, 20)
    win.CloseButton = blz("Button", nil, win, 15, 15, "TOPRIGHT", -6, -4)
    tex(win.CloseButton, nil, "BACKGROUND")

    -- the community list down the left side
    local list = blz("Frame", nil, win, 160, 360, "TOPLEFT", 10, -50)
    win.CommunitiesList = list
    list.Bg = tex(list, nil, "BACKGROUND")
    list.TopFiligree = tex(list, nil, "ARTWORK")
    list.BottomFiligree = tex(list, nil, "ARTWORK")
    list.FilligreeOverlay = blz("Frame", nil, list, 160, 360, "TOPLEFT", 0, 0)
    tex(list.FilligreeOverlay, nil, "OVERLAY")
    list.InsetFrame = inset(list, 160, 360, 0, 0)
    list.ScrollBox = scrollBox(list, 150, 330, 5, -10)
    for i, n in ipairs({ "Stu's Crew", "Mulgore Mutuals" }) do
        local e = blz("Button", nil, list.ScrollBox, 146, 40, "TOPLEFT", 0, -(i - 1) * 44)
        e.Background = tex(e, nil, "BACKGROUND")
        e.Selection = tex(e, nil, "BACKGROUND")
        e.Selection.shown = (i == 1)
        e.NewCommunityFlash = tex(e, nil, "OVERLAY")
        e.Icon = tex(e, nil, "ARTWORK"); e.Icon.w, e.Icon.h = 28, 28
        e.Name = at(fstring(e, nil, n, 12, { 1, 0.82, 0, 1 }), e, "LEFT", 40)
        e.scripts.OnClick = function() end
        e.scripts.OnEnter = function() end
        list.ScrollBox.rows[i] = e
    end

    -- the roster
    local roster = blz("Frame", nil, win, 600, 360, "TOPLEFT", 190, -50)
    win.MemberList = roster
    roster.MemberCount = fstring(roster, nil, "3 members", 11, { 1, 0.82, 0, 1 })
    roster.InsetFrame = inset(roster, 600, 330, 0, -28)
    tex(roster, nil, "BORDER")
    roster.InsetBorderTopLeft = tex(roster, nil, "BORDER")
    local cd = blz("Frame", nil, roster, 590, 28, "TOPLEFT", 4, -4)
    roster.ColumnDisplay = cd
    cd.Background = tex(cd, nil, "BACKGROUND")
    cd.TopTileStreaks = tex(cd, nil, "ARTWORK")
    cd.InsetBorderTop = tex(cd, nil, "BORDER")
    function cd.LayoutColumns(self)
        for i, label in ipairs({ "Name", "Level", "Zone", "Rank" }) do
            local h = blz("Button", nil, cd, 140, 24, "TOPLEFT", (i - 1) * 142, 0)
            h.Left = tex(h, nil, "BACKGROUND"); h.Middle = tex(h, nil, "BACKGROUND"); h.Right = tex(h, nil, "BACKGROUND")
            h.NormalNineSlice = blz("Frame", nil, h, 140, 24)
            h.HighlightNineSlice = blz("Frame", nil, h, 140, 24)
            h.Text = fstring(h, nil, label, 11, { 1, 0.82, 0, 1 })
            h.GetFontString = function(self2) return self2.Text end
            h.scripts.OnClick = function() end
        end
    end
    cd:LayoutColumns()
    roster.ScrollBox = scrollBox(roster, 580, 300, 6, -36)
    for i, m in ipairs({ { "Stu", "12", "Mulgore", "Guild Master" }, { "Mook", "9", "Thunder Bluff", "Officer" }, { "Grom", "22", "Durotar", "Member" } }) do
        local r = blz("Button", nil, roster.ScrollBox, 580, 28, "TOPLEFT", 0, -(i - 1) * 30)
        r.Background = tex(r, nil, "BACKGROUND")
        r.HighlightTexture = tex(r, nil, "HIGHLIGHT")
        r.highlightTex = r.HighlightTexture
        r.NameFrame = blz("Frame", nil, r, 160, 28, "LEFT", 4, 0)
        r.NameFrame.Name = at(fstring(r.NameFrame, nil, m[1], 12, { 1, 1, 1, 1 }), r.NameFrame, "LEFT", 24)
        r.NameFrame.PresenceIcon = tex(r.NameFrame, nil, "ARTWORK"); r.NameFrame.PresenceIcon.w, r.NameFrame.PresenceIcon.h = 12, 12
        r.Level = at(fstring(r, nil, m[2], 11, { 1, 1, 1, 1 }), r, "LEFT", 170)
        r.Class = tex(r, nil, "ARTWORK"); r.Class.w, r.Class.h = 16, 16
        r.Zone = at(fstring(r, nil, m[3], 11, { 1, 1, 1, 1 }), r, "LEFT", 260)
        r.Rank = at(fstring(r, nil, m[4], 11, { 1, 1, 1, 1 }), r, "LEFT", 420)
        r.scripts.OnClick = function() end
        r.scripts.OnEnter = function() end
        r.LockHighlight = function(self) self.locked = true end
        r.UnlockHighlight = function(self) self.locked = false end
        roster.ScrollBox.rows[i] = r
    end

    -- the guild pages
    for _, key in ipairs({ "GuildDetailsFrame", "GuildBenefitsFrame" }) do
        local pg = blz("Frame", nil, win, 600, 360, "TOPLEFT", 190, -50)
        win[key] = pg
        pg.shown = false
        pg.InsetBorderTopLeft = tex(pg, nil, "BORDER")
        pg.InsetBorderLeft = tex(pg, nil, "BORDER")
        pg.Info = blz("Frame", nil, pg, 300, 300)
        pg.Info.InsetBorderTopLeft = tex(pg.Info, nil, "BORDER")
    end

    -- the three pop ups
    for _, n in ipairs({ "CommunitiesGuildLogFrame", "CommunitiesGuildTextEditFrame", "CommunitiesGuildNewsFiltersFrame" }) do
        local p = blz("Frame", n, UIParent, 384, 300, "TOPLEFT", 900, -100)
        p.shown = false
        p.NineSlice = blz("Frame", nil, p, 384, 300)
        p.CloseButton = blz("Button", n .. "CloseButton", p, 15, 15, "TOPRIGHT", -6, -4)
        tex(p.CloseButton, nil, "BACKGROUND")
        fstring(p, n .. "Title", "Title", 12, { 1, 0.82, 0, 1 })
    end
end
"""

H = Harness({
    "ButtonSkins": "Core/ButtonSkins.lua",
    "Character": "Modules/Skins/Character.lua",
    "GroupKit": "Modules/Skins/GroupKit.lua",
    "Guild": "Modules/Skins/Guild.lua",
}, BLIZZARD)
case = H.case

SHOW = "Fire('PLAYER_ENTERING_WORLD'); CommunitiesFrame:Show(); FlushTimers()"

case("roster: each member is an ink card, the stock row art held, the labels mono, the class icon and clicks kept", f"""
    {SHOW}
    local S = FS.GuildSkin.state
    for i, r in ipairs(CommunitiesFrame.MemberList.ScrollBox.rows) do
        assert(S.rows[r], 'row ' .. i .. ' not carded')
        assert(r.Background.alpha == 0 and r.HighlightTexture.alpha == 0, 'stock row art kept on row ' .. i)
        assert(r.Level.fontPath ~= 'stock.ttf' and r.Zone.fontPath ~= 'stock.ttf' and r.Rank.fontPath ~= 'stock.ttf', 'labels not mono on row ' .. i)
        assert(r.NameFrame.Name.fontPath ~= 'stock.ttf', 'name not mono on row ' .. i)
        assert(r.Class.alpha == 1 and r.NameFrame.PresenceIcon.alpha == 1, 'info icon held on row ' .. i)
        assert(r.scripts.OnClick and r.scripts.OnEnter, 'click lost on row ' .. i)
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("roster: hover lights the edge of a member card", f"""
    {SHOW}
    local r = CommunitiesFrame.MemberList.ScrollBox.rows[1]
    local rec = FS.GuildSkin.state.rows[r]
    local before = rec.box.edges[1].color[2]
    r:RunScript('OnEnter')
    assert(rec.box.edges[1].color[2] > before, 'hover did not light the edge')
    r:RunScript('OnLeave')
""")

case("column headings: band keys with the stock art and nine slice frames held, a late heading is caught", f"""
    {SHOW}
    local cd = CommunitiesFrame.MemberList.ColumnDisplay
    assert(cd.Background.alpha == 0 and cd.TopTileStreaks.alpha == 0 and cd.InsetBorderTop.alpha == 0, 'display art kept')
    local n = 0
    for _, h in ipairs({{ cd:GetChildren() }}) do
        n = n + 1
        assert(FS.GroupSkin.headers[h], 'heading ' .. n .. ' not skinned')
        assert(h.Left.alpha == 0 and h.NormalNineSlice.alpha == 0 and h.HighlightNineSlice.alpha == 0, 'heading art kept ' .. n)
        assert(h.scripts.OnClick, 'sort click lost')
    end
    assert(n == 4, 'headings ' .. n)
    cd:LayoutColumns()
    local late = 0
    for _, h in ipairs({{ cd:GetChildren() }}) do if FS.GroupSkin.headers[h] then late = late + 1 end end
    assert(late == 8, 'late headings skinned ' .. late)
""")

case("insets: the roster and list insets, borders and stock frame art are held", f"""
    {SHOW}
    local w = CommunitiesFrame
    assert(w.MemberList.InsetFrame.NineSlice.alpha == 0 and w.MemberList.InsetFrame.Bg.alpha == 0, 'roster inset kept')
    assert(w.MemberList.InsetBorderTopLeft.alpha == 0, 'roster border kept')
    assert(w.CommunitiesList.Bg.alpha == 0 and w.CommunitiesList.TopFiligree.alpha == 0 and w.CommunitiesList.BottomFiligree.alpha == 0, 'list art kept')
    assert(w.CommunitiesList.FilligreeOverlay.alpha == 0, 'filigree overlay kept')
    assert(w.CommunitiesList.InsetFrame.NineSlice.alpha == 0, 'list inset kept')
""")

case("community list: entries are cards and the stock selection lights the chosen one", f"""
    {SHOW}
    local S = FS.GuildSkin.state
    local rows = CommunitiesFrame.CommunitiesList.ScrollBox.rows
    for i, r in ipairs(rows) do
        assert(S.rows[r], 'entry ' .. i)
        assert(r.Background.alpha == 0 and r.Selection.alpha == 0 and r.NewCommunityFlash.alpha == 0, 'entry art kept ' .. i)
        assert(r.Icon.alpha == 1, 'icon held ' .. i)
        assert(r.Name.fontPath ~= 'stock.ttf', 'name not mono ' .. i)
    end
    assert(S.rows[rows[1]].selected and not S.rows[rows[2]].selected, 'selection not read')
    rows[1].Selection:Hide(); rows[2].Selection:Show()
    assert(not S.rows[rows[1]].selected and S.rows[rows[2]].selected, 'selection not followed')
""")

case("guild pages lose their inset border art", f"""
    {SHOW}
    for _, key in ipairs({{ 'GuildDetailsFrame', 'GuildBenefitsFrame' }}) do
        local pg = CommunitiesFrame[key]
        assert(pg.InsetBorderTopLeft.alpha == 0 and pg.InsetBorderLeft.alpha == 0, key .. ' border kept')
        assert(pg.Info.InsetBorderTopLeft.alpha == 0, key .. ' sub border kept')
    end
""")

case("pop ups: the log, text edit and news filter windows wear the panel skin", f"""
    {SHOW}
    for _, n in ipairs({{ 'CommunitiesGuildLogFrame', 'CommunitiesGuildTextEditFrame', 'CommunitiesGuildNewsFiltersFrame' }}) do
        local p = _G[n]
        assert(p.fsStripped and p.fsPanelTitle, n .. ' not skinned')
    end
""")

case("nothing is built in combat; it is built when combat ends", """
    Reset()
    __combat = true
    FS = Load({ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'ButtonSkins', 'Character', 'GroupKit', 'Guild' })
    local first = CommunitiesFrame.MemberList.ScrollBox.rows[1]
    assert(not FS.GuildSkin.state.rows[first] and not CommunitiesFrame.fsGuildSkin, 'built in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(FS.GuildSkin.state.rows[first] and CommunitiesFrame.fsGuildSkin, 'not built when combat ended')
""")

case("a client without the guild window degrades quietly, and a second build adds nothing", f"""
    {SHOW}
    local r = CommunitiesFrame.MemberList.ScrollBox.rows[1]
    local n = #r.regions
    FS.GuildSkin.Build(); CommunitiesFrame.MemberList.ScrollBox:Update(); FlushTimers()
    assert(#r.regions == n, 'regions grew')
    CommunitiesFrame = nil
    FS.GuildSkin.Build()
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

SCENES = {
    "guild": "Fire('PLAYER_ENTERING_WORLD'); FS.Theme.SkinPanel(CommunitiesFrame, {title='communities'}); CommunitiesFrame:Show(); CommunitiesFrame.MemberList.ScrollBox.rows[2]:LockHighlight(); FlushTimers(); return DumpOps({ CommunitiesFrame })",
    "guildlog": "Fire('PLAYER_ENTERING_WORLD'); CommunitiesGuildLogFrame:Show(); FlushTimers(); return DumpOps({ CommunitiesGuildLogFrame })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("guild skin", SCENES))
