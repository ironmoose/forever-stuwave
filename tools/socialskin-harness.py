#!/usr/bin/env python3
"""Runs the real Modules/Skins/Social.lua (and GroupKit.lua) headless against a mock friends window (tools/charskin_support.py).

Pinned: friends rows get a card with an LED bar in the status colour and a reticle on the selected one, the stock wash, status icon
and highlight are held while the game icon and favourite star are kept, rows are painted again after a ScrollBox update, request
rows and their header are amber cards with Accept and Decline keys, the banner is a band card, the ignore list window wears the
panel skin and its rows are cards, the Who headings are band keys with their stock art held, Who rows are cards, the raid cells
are cards, no script or attribute is written on a Blizzard widget, and nothing is built in combat. Run
`python3 tools/socialskin-harness.py [--png debug/social]`. The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring, atex = BLZ.blz, BLZ.tex, BLZ.fstring, nil
local build = BuildBlizzard

FRIENDS_TEXTURE_ONLINE = "Interface\\FriendsFrame\\StatusIcon-Online"
FRIENDS_TEXTURE_AFK = "Interface\\FriendsFrame\\StatusIcon-Away"
FRIENDS_TEXTURE_DND = "Interface\\FriendsFrame\\StatusIcon-DnD"
FRIENDS_TEXTURE_OFFLINE = "Interface\\FriendsFrame\\StatusIcon-Offline"

local function scrollBox(parent, w, h, x, y)
    local box = blz("Frame", nil, parent, w, h, "TOPLEFT", x, y)
    box.rows = {}
    box.ForEachFrame = function(self, fn) for _, r in ipairs(self.rows) do fn(r) end end
    box.Update, box.FullUpdate, box.SetDataProvider = function() end, function() end, function() end
    return box
end

local function selectable(b)
    b.LockHighlight = function(self) self.locked = true end
    b.UnlockHighlight = function(self) self.locked = false end
end

local PRESENCE = {
    online = FRIENDS_TEXTURE_ONLINE, afk = FRIENDS_TEXTURE_AFK, dnd = FRIENDS_TEXTURE_DND, offline = FRIENDS_TEXTURE_OFFLINE,
}

-- FriendsListButtonTemplate
local function friendRow(parent, y, name, info, presence)
    local b = blz("Button", nil, parent, 298, 34, "TOPLEFT", 0, -y)
    b.background = tex(b, nil, "BACKGROUND")
    b.status = tex(b, nil, "ARTWORK"); b.status.w, b.status.h = 16, 16
    b.status.path = PRESENCE[presence]
    b.gameIcon = tex(b, nil, "ARTWORK"); b.gameIcon.w, b.gameIcon.h = 24, 24
    b.Favorite = tex(b, nil, "ARTWORK"); b.Favorite.w, b.Favorite.h = 17, 17
    b.name = fstring(b, nil, name, 12, { 0.51, 0.77, 1, 1 })
    b.name.points[1] = { point = "TOPLEFT", rel = b, relPoint = "TOPLEFT", x = 24, y = -4 }
    b.info = fstring(b, nil, info, 10, { 0.5, 0.5, 0.5, 1 })
    b.info.points[1] = { point = "TOPLEFT", rel = b, relPoint = "TOPLEFT", x = 24, y = -19 }
    b.highlight = tex(b, nil, "HIGHLIGHT")
    b.highlightTex = b.highlight
    b.travelPassButton = blz("Button", nil, b, 24, 32, "TOPRIGHT", 1, -1)
    b.travelPassButton.NormalTexture = tex(b.travelPassButton, nil, "ARTWORK")
    b.travelPassButton.shown = false
    b.scripts.OnClick = function() end
    b.scripts.OnEnter = function() end
    b.scripts.OnLeave = function() end
    selectable(b)
    parent.rows[#parent.rows + 1] = b
    return b
end

local function inviteRow(parent, y, name)
    local f = blz("Frame", nil, parent, 298, 34, "TOPLEFT", 0, -y)
    f.Background = tex(f, nil, "BACKGROUND")
    f.Name = fstring(f, nil, name, 12, { 0.51, 0.77, 1, 1 })
    f.Name.points[1] = { point = "LEFT", rel = f, relPoint = "LEFT", x = 8, y = 0 }
    f.DeclineButton = blz("Button", nil, f, 24, 22, "RIGHT", -7, 0)
    tex(f.DeclineButton, nil, "BACKGROUND")
    f.DeclineButton.NormalTexture = tex(f.DeclineButton, nil, "ARTWORK")
    f.DeclineButton.Icon = tex(f.DeclineButton, nil, "ARTWORK"); f.DeclineButton.Icon.w, f.DeclineButton.Icon.h = 12, 12
    f.DeclineButton.scripts.OnClick = function() end
    f.AcceptButton = blz("Button", nil, f, 80, 22, "RIGHT", -33, 0)
    tex(f.AcceptButton, nil, "BACKGROUND")
    f.AcceptButton.Text = fstring(f.AcceptButton, nil, "Accept", 11, { 1, 1, 1, 1 })
    f.AcceptButton.fs = f.AcceptButton.Text
    f.AcceptButton.GetFontString = function(self) return self.Text end
    f.AcceptButton.scripts.OnClick = function() end
    parent.rows[#parent.rows + 1] = f
    return f
end

function BuildBlizzard()
    build()
    atex = BLZ.atex
    for k in pairs(_G) do
        if type(k) == "string" and (k:find("^Friends") or k:find("^Who") or k:find("^Raid") or k:find("^IgnoreList")) then _G[k] = nil end
    end
    -- the window, as FriendsFrame.xml builds it (ButtonFrameTemplate 385 x 424)
    local win = blz("Frame", "FriendsFrame", UIParent, 385, 424)
    win.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 100, y = -80 }
    win.shown = false
    win.Bg = tex(win, nil, "BACKGROUND")
    win.NineSlice = blz("Frame", nil, win, 385, 424)
    win.TitleContainer = blz("Frame", nil, win, 330, 20)
    win.Inset = blz("Frame", nil, win, 370, 330, "TOPLEFT", 5, -80)
    win.Inset.NineSlice = blz("Frame", nil, win.Inset, 370, 330)
    tex(win, "FriendsFrameIcon", "OVERLAY")
    fstring(win, "FriendsFrameTitleText", "Friends")
    local close = blz("Button", "FriendsFrameCloseButton", win, 15, 15, "TOPRIGHT", -6, -4)
    tex(close, nil, "BACKGROUND")
    win.CloseButton = close

    -- the Battle.net banner
    local header = blz("Frame", "FriendsTabHeader", win, 385, 424, "TOPLEFT", 0, 0)
    local banner = blz("Frame", "FriendsFrameBattlenetFrame", header, 190, 29, "TOPLEFT", 105, -46)
    header.BattlenetFrame = banner
    tex(banner, nil, "BACKGROUND")
    banner.Tag = fstring(banner, nil, "Stu#1234", 12, { 0.345, 0.667, 0.867, 1 })
    banner.Tag.points[1] = { point = "CENTER", rel = banner, relPoint = "CENTER", x = 0, y = 0 }
    banner.UnavailableLabel = fstring(banner, nil, "Unavailable", 12, { 1, 0.82, 0, 1 })
    banner.UnavailableLabel.shown = false
    local menu = blz("Button", nil, banner, 32, 32, "LEFT", 195, 0)
    menu.NormalTexture = tex(menu, nil, "ARTWORK")
    menu.Icon = tex(menu, nil, "OVERLAY"); menu.Icon.w, menu.Icon.h = 12, 12
    menu.scripts.OnClick = function() end
    banner.ContactsMenuButton = menu

    -- the friends list: a ScrollBox of pooled rows
    local list = blz("Frame", "FriendsListFrame", win, 385, 424, "TOPLEFT", 0, 0)
    list.FriendsDisabledText = fstring(list, nil, "", 12, { 1, 1, 1, 1 })
    list.ScrollBox = scrollBox(list, 298, 300, 8, -87)
    local box = list.ScrollBox
    friendRow(box, 0, "Mook, Level 12 Hunter", "Mulgore", "online")
    friendRow(box, 34, "Thrall, Level 40 Shaman", "Orgrimmar", "afk")
    friendRow(box, 68, "Cairne, Level 60 Warrior", "Thunder Bluff", "dnd")
    friendRow(box, 102, "Magatha", "Offline", "offline")
    local hdr = blz("Button", nil, box, 295, 30, "TOPLEFT", 0, -136)
    hdr.BG = tex(hdr, nil, "BACKGROUND")
    hdr.RightArrow = tex(hdr, nil, "ARTWORK"); hdr.RightArrow.w, hdr.RightArrow.h = 8, 14
    hdr.DownArrow = tex(hdr, nil, "ARTWORK"); hdr.DownArrow.w, hdr.DownArrow.h = 14, 8
    hdr.Flash = tex(hdr, nil, "OVERLAY")
    hdr.NormalTexture = tex(hdr, nil, "ARTWORK")
    hdr.fs = fstring(hdr, nil, "Friend Requests (1)", 12, { 1, 0.82, 0, 1 })
    hdr.GetFontString = function(self) return self.fs end
    hdr.scripts.OnClick = function() end
    box.rows[#box.rows + 1] = hdr
    inviteRow(box, 170, "Rexxar#4321")
    local div = blz("Frame", nil, box, 298, 16, "TOPLEFT", 0, -204)
    tex(div, nil, "ARTWORK")
    box.rows[#box.rows + 1] = div
    -- a recycle: the stock code points a row at another friend and the ScrollBox updates
    function SetPresence(row, presence) row.status:SetTexture(PRESENCE[presence]) end

    -- ignore list window (a ButtonFrameTemplate child)
    local ign = blz("Frame", nil, win, 273, 292, "TOPLEFT", 390, -53)
    win.IgnoreListWindow = ign
    ign.shown = false
    ign.Bg = tex(ign, nil, "BACKGROUND")
    ign.NineSlice = blz("Frame", nil, ign, 273, 292)
    ign.TitleContainer = blz("Frame", nil, ign, 220, 20)
    ign.Inset = blz("Frame", nil, ign, 260, 220, "TOPLEFT", 5, -50)
    ign.Inset.NineSlice = blz("Frame", nil, ign.Inset, 260, 220)
    ign.CloseButton = blz("Button", nil, ign, 15, 15, "TOPRIGHT", -6, -4)
    tex(ign.CloseButton, nil, "BACKGROUND")
    ign.UnignorePlayerButton = blz("Button", nil, ign, 130, 22, "BOTTOM", 0, 8)
    tex(ign.UnignorePlayerButton, nil, "BACKGROUND")
    ign.UnignorePlayerButton.fs = fstring(ign.UnignorePlayerButton, nil, "Stop Ignoring", 11, { 1, 1, 1, 1 })
    ign.UnignorePlayerButton.GetFontString = function(self) return self.fs end
    ign.UnignorePlayerButton.scripts.OnClick = function() end
    ign.ScrollBox = scrollBox(ign, 250, 220, 1, -50)
    for i, n in ipairs({ "Gnoll", "Spammer", "Murloc" }) do
        local r = blz("Button", nil, ign.ScrollBox, 246, 16, "TOPLEFT", 0, -(i - 1) * 16)
        r.name = fstring(r, nil, n, 12, { 1, 0.82, 0, 1 })
        r.name.points[1] = { point = "LEFT", rel = r, relPoint = "LEFT", x = 4, y = 0 }
        r.highlight = tex(r, nil, "HIGHLIGHT")
        r.scripts.OnClick = function() end
        selectable(r)
        ign.ScrollBox.rows[#ign.ScrollBox.rows + 1] = r
    end
    local sec = blz("Frame", nil, ign.ScrollBox, 246, 20, "TOPLEFT", 0, -60)
    sec.Title = fstring(sec, nil, "Ignored", 12, { 1, 0.82, 0, 1 })
    sec.Title.points[1] = { point = "LEFT", rel = sec, relPoint = "LEFT", x = 4, y = 0 }
    tex(sec, nil, "BACKGROUND")
    ign.ScrollBox.rows[#ign.ScrollBox.rows + 1] = sec

    -- the Who page
    local who = blz("Frame", "WhoFrame", win, 385, 424, "TOPLEFT", 0, 0)
    who.shown = false
    who.EditBox = blz("EditBox", "WhoFrameEditBox", who, 330, 20, "BOTTOMLEFT", 18, 32)
    who.EditBox.Backdrop = tex(who.EditBox, nil, "BACKGROUND")
    local inset = blz("Frame", "WhoFrameListInset", who, 370, 270, "TOPLEFT", 5, -83)
    who.WhoFrameListInset = inset
    inset.NineSlice = blz("Frame", nil, inset, 370, 270)
    inset.Bg = tex(inset, nil, "BACKGROUND")
    inset.WhoFrameTotals = fstring(inset, "WhoFrameTotals", "3 players", 11, { 1, 0.82, 0, 1 })
    local prev
    for i, label in ipairs({ "Name", "Zone", "Lvl", "Class" }) do
        local h = blz("Button", "WhoFrameColumnHeader" .. i, who, 80 + (i == 1 and 30 or 0), 28, "TOPLEFT", (i - 1) * 84 + 8, -57)
        h.Left = tex(h, "WhoFrameColumnHeader" .. i .. "Left", "BACKGROUND")
        h.Middle = tex(h, "WhoFrameColumnHeader" .. i .. "Middle", "BACKGROUND")
        h.Right = tex(h, "WhoFrameColumnHeader" .. i .. "Right", "BACKGROUND")
        h.HighlightTexture = tex(h, nil, "HIGHLIGHT")
        h.Text = fstring(h, nil, label, 11, { 1, 0.82, 0, 1 })
        h.fs = h.Text
        h.GetFontString = function(self) return self.Text end
        h.scripts.OnClick = function() end
        prev = h
    end
    who.ScrollBox = scrollBox(who, 340, 260, 8, -87)
    for i, r in ipairs({ { "Mook", "Mulgore", "12", "Hunter" }, { "Grom", "Durotar", "22", "Warrior" }, { "Vol", "Orgrimmar", "30", "Shaman" } }) do
        local b = blz("Button", nil, who.ScrollBox, 298, 16, "TOPLEFT", 0, -(i - 1) * 16)
        local function at(fs, x) fs.points[1] = { point = "LEFT", rel = b, relPoint = "LEFT", x = x, y = 0 } return fs end
        b.Name = at(fstring(b, nil, r[1], 11, { 1, 0.82, 0, 1 }), 4)
        b.Variable = at(fstring(b, nil, r[2], 11, { 1, 0.82, 0, 1 }), 100)
        b.Level = at(fstring(b, nil, r[3], 11, { 1, 0.82, 0, 1 }), 205)
        b.Class = at(fstring(b, nil, r[4], 11, { 0.5, 0.8, 0.2, 1 }), 250)
        b.highlight = tex(b, nil, "HIGHLIGHT")
        b.scripts.OnClick = function() end
        selectable(b)
        who.ScrollBox.rows[#who.ScrollBox.rows + 1] = b
    end

    -- the raid page: group outlines, cells (secure buttons), class buttons, the Raid Info window
    local raid = blz("Frame", "RaidFrame", win, 385, 424, "TOPLEFT", 0, 0)
    raid.shown = false
    for g = 1, 2 do
        local grp = blz("Frame", "RaidGroup" .. g, raid, 80, 190, "TOPLEFT", 10 + (g - 1) * 90, -90)
        tex(grp, "RaidGroup" .. g .. "GroupOutline", "BACKGROUND")
        local label = blz("Button", "RaidGroup" .. g .. "Label", grp, 60, 14, "TOP", 0, 0)
        label.fs = fstring(label, nil, "Group " .. g, 11, { 1, 0.82, 0, 1 })
        label.GetFontString = function(self) return self.fs end
        for s = 1, 5 do
            local cell = blz("Button", "RaidGroupButton" .. ((g - 1) * 5 + s), grp, 70, 30, "TOPLEFT", 5, -(s - 1) * 34 - 20)
            cell.NormalTexture = tex(cell, nil, "ARTWORK")
            local nm = fstring(cell, "RaidGroupButton" .. ((g - 1) * 5 + s) .. "Name", "Member " .. s, 11, { 1, 0.82, 0, 1 })
            nm.points[1] = { point = "LEFT", rel = cell, relPoint = "LEFT", x = 4, y = 0 }
            local lv = fstring(cell, "RaidGroupButton" .. ((g - 1) * 5 + s) .. "Level", "60", 10, { 1, 1, 1, 1 })
            lv.points[1] = { point = "RIGHT", rel = cell, relPoint = "RIGHT", x = -4, y = 0 }
            cell.scripts.OnEnter = function() end
            cell.scripts.OnClick = function() end
        end
    end
    for i = 1, 3 do
        local cb = blz("Button", "RaidClassButton" .. i, raid, 28, 28, "TOPLEFT", 190 + (i - 1) * 32, -90)
        cb.NormalTexture = tex(cb, nil, "ARTWORK")
        fstring(cb, "RaidClassButton" .. i .. "Count", "3", 10, { 1, 1, 1, 1 })
        cb.scripts.OnEnter = function() end
    end
    local notin = blz("Frame", "RaidFrameNotInRaid", raid, 300, 40, "TOP", 0, -120)
    notin.Text = fstring(notin, nil, "You are not in a raid", 12, { 1, 1, 1, 1 })
    for k, n in ipairs({ "RaidFrameConvertToRaidButton", "RaidFrameRaidInfoButton" }) do
        local b = blz("Button", n, raid, 150, 22, "BOTTOMLEFT", 10 + (k - 1) * 160, 8)
        tex(b, nil, "BACKGROUND")
        b.fs = fstring(b, n .. "Text", n, 11, { 1, 1, 1, 1 })
        b.GetFontString = function(self) return self.fs end
        b.scripts.OnClick = function() end
    end
    local rinfo = blz("Frame", "RaidInfoFrame", raid, 300, 300, "TOPLEFT", 390, -50)
    rinfo.shown = false
    rinfo.Border = blz("Frame", nil, rinfo, 300, 300)
    tex(rinfo.Border, nil, "BORDER")
    tex(rinfo, nil, "BACKGROUND")
    local lbl = blz("Button", "RaidInfoInstanceLabel", rinfo, 160, 24, "TOPLEFT", 10, -30)
    lbl.Left = tex(lbl, nil, "BACKGROUND"); lbl.Middle = tex(lbl, nil, "BACKGROUND"); lbl.Right = tex(lbl, nil, "BACKGROUND")
    lbl.fs = fstring(lbl, nil, "Instance", 11, { 1, 0.82, 0, 1 })
    lbl.GetFontString = function(self) return self.fs end
    for k, n in ipairs({ "RaidInfoExtendButton", "RaidInfoCancelButton" }) do
        local b = blz("Button", n, rinfo, 130, 22, "BOTTOMLEFT", 10 + (k - 1) * 145, 8)
        tex(b, nil, "BACKGROUND")
        b.fs = fstring(b, nil, n, 11, { 1, 1, 1, 1 })
        b.GetFontString = function(self) return self.fs end
        b.scripts.OnClick = function() end
    end
    win.shown = false
end
"""

H = Harness({
    "ButtonSkins": "Core/ButtonSkins.lua",
    "Character": "Modules/Skins/Character.lua",
    "Commerce": "Modules/Skins/Commerce.lua",
    "GroupKit": "Modules/Skins/GroupKit.lua",
    "Social": "Modules/Skins/Social.lua",
}, BLIZZARD)
case = H.case

SHOW = "Fire('PLAYER_ENTERING_WORLD'); FriendsFrame:Show(); FlushTimers()"

case("friends rows: the stock wash, status icon and highlight are held, the game icon and star are kept, each row has a card", f"""
    {SHOW}
    local rows = FriendsListFrame.ScrollBox.rows
    local S = FS.SocialSkin.state
    for i = 1, 4 do
        local r = rows[i]
        assert(S.rows[r], 'row ' .. i .. ' not skinned')
        assert(r.background.alpha == 0 and r.status.alpha == 0 and r.highlight.alpha == 0, 'stock art kept on row ' .. i)
        assert(r.gameIcon.alpha == 1 and r.Favorite.alpha == 1, 'info art held on row ' .. i)
        assert(r.name.fontPath ~= 'stock.ttf' and r.info.fontPath ~= 'stock.ttf', 'text not mono on row ' .. i)
        assert(r.scripts.OnClick and r.scripts.OnEnter, 'click lost on row ' .. i)
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("friends rows: the LED is cyan online, amber away, pink busy and dim offline", f"""
    {SHOW}
    local rows = FriendsListFrame.ScrollBox.rows
    local S = FS.SocialSkin.state
    local function led(r) local c = S.rows[r].led.t.color; return c[1], c[2], c[3] end
    local function same(r, want) local a, b, c = led(r); return math.abs(a - want[1]) < 0.01 and math.abs(b - want[2]) < 0.01 and math.abs(c - want[3]) < 0.01 end
    local T = FS.Theme
    assert(same(rows[1], T.COLOR_POWER), 'online not cyan')
    assert(same(rows[2], T.COLOR_AMBER), 'away not amber')
    assert(same(rows[3], T.COLOR_HEALTH), 'busy not pink')
    assert(same(rows[4], FS.GroupSkin.C.dim), 'offline not dim')
""")

case("friends rows: a row the ScrollBox recycles is painted again after the update", f"""
    {SHOW}
    local rows = FriendsListFrame.ScrollBox.rows
    local S = FS.SocialSkin.state
    SetPresence(rows[1], 'dnd')
    FriendsListFrame.ScrollBox:Update()
    local c = S.rows[rows[1]].led.t.color
    local T = FS.Theme.COLOR_HEALTH
    assert(math.abs(c[1] - T[1]) < 0.01 and math.abs(c[2] - T[2]) < 0.01, 'LED did not follow the status icon')
""")

case("friends rows: the selected row is lit with the reticle and the stock selection calls still work", f"""
    {SHOW}
    local rows = FriendsListFrame.ScrollBox.rows
    local S = FS.SocialSkin.state
    local ret = S.rows[rows[1]].reticle
    assert(not ret.tlH.shown, 'reticle shown before a selection')
    rows[1]:LockHighlight()
    assert(rows[1].locked, 'stock LockHighlight lost')
    assert(ret.tlH.shown and ret.brV.shown, 'reticle not shown on the selected row')
    rows[1]:UnlockHighlight()
    assert(not rows[1].locked and not ret.tlH.shown, 'reticle stays after the selection is cleared')
""")

case("friends rows: hover lights the edge", f"""
    {SHOW}
    local r = FriendsListFrame.ScrollBox.rows[1]
    local S = FS.SocialSkin.state
    local function edgeColor() return S.rows[r].box.edges[1].color end
    local idle = edgeColor()
    r:RunScript('OnEnter')
    local on = edgeColor()
    assert(on[3] > idle[3] or on[2] > idle[2], 'hover did not change the edge')
    r:RunScript('OnLeave')
""")

case("requests: the header and the request row are amber cards, Accept is a text key, Decline a pink square key", f"""
    {SHOW}
    local rows = FriendsListFrame.ScrollBox.rows
    local hdr, inv = rows[5], rows[6]
    local S = FS.SocialSkin.state
    assert(S.cards[hdr] and S.cards[inv], 'cards missing')
    assert(hdr.BG.alpha == 0 and hdr.NormalTexture.alpha == 0, 'header art kept')
    assert(hdr.RightArrow.alpha == 1 and hdr.DownArrow.alpha == 1, 'arrows held')
    assert(inv.Background.alpha == 0, 'request wash kept')
    assert(FS.ButtonSkins.Parts(inv.AcceptButton), 'accept not a text key')
    assert(FS.GroupSkin.squares[inv.DeclineButton], 'decline not a square key')
    assert(inv.DeclineButton.Icon.alpha == 1, 'decline icon held')
    assert(inv.AcceptButton.scripts.OnClick and inv.DeclineButton.scripts.OnClick, 'click lost')
""")

case("dividers: the stock rule art is held and one rule of ours replaces it", f"""
    {SHOW}
    local d = FriendsListFrame.ScrollBox.rows[7]
    assert(FS.SocialSkin.state.dividers[d], 'divider not skinned')
    assert(d.regions[1].alpha == 0, 'divider art kept')
""")

case("banner: the stock art is held, the tag is mono, the contacts menu is a square key", f"""
    {SHOW}
    local b = FriendsFrameBattlenetFrame
    assert(b.regions[1].alpha == 0, 'banner art kept')
    assert(b.Tag.fontPath ~= 'stock.ttf', 'tag not mono')
    assert(FS.GroupSkin.squares[b.ContactsMenuButton], 'contacts button not a square key')
    assert(b.ContactsMenuButton.Icon.alpha == 1, 'menu icon held')
    assert(b.ContactsMenuButton.scripts.OnClick, 'click lost')
""")

case("ignore window: it wears the panel skin and its rows are cards, the selected one lit", f"""
    {SHOW}
    local w = FriendsFrame.IgnoreListWindow
    assert(w.fsStripped, 'ignore window not stripped')
    assert(w.fsPanelTitle and w.fsPanelTitle:GetText():find('ignored'), 'no title band')
    assert(FS.ButtonSkins.Parts(w.UnignorePlayerButton), 'unignore not a text key')
    local S = FS.SocialSkin.state
    local r = w.ScrollBox.rows[1]
    assert(S.rows[r], 'ignore row not skinned')
    assert(r.name.fontPath ~= 'stock.ttf', 'name not mono')
    local before = S.rows[r].box.edges[1].color[1]
    r:LockHighlight()
    assert(S.rows[r].selected, 'selection not followed')
    assert(w.ScrollBox.rows[4].Title.fontPath ~= 'stock.ttf', 'section header not mono')
""")

case("who: the headings are band keys with the stock art held, rows are cards, the inset is held", f"""
    {SHOW}
    local G = FS.GroupSkin
    for i = 1, 4 do
        local h = _G['WhoFrameColumnHeader' .. i]
        assert(G.headers[h], 'heading ' .. i .. ' not skinned')
        assert(h.Left.alpha == 0 and h.Middle.alpha == 0 and h.Right.alpha == 0 and h.HighlightTexture.alpha == 0, 'heading art kept ' .. i)
        assert(h.scripts.OnClick, 'sort click lost')
    end
    assert(WhoFrameListInset.NineSlice.alpha == 0 and WhoFrameListInset.Bg.alpha == 0, 'inset art kept')
    assert(WhoFrameEditBox.Backdrop.alpha == 0, 'search backdrop kept')
    local S = FS.SocialSkin.state
    for _, r in ipairs(WhoFrame.ScrollBox.rows) do
        assert(S.rows[r], 'who row not skinned')
        assert(r.Name.fontPath ~= 'stock.ttf' and r.Class.fontPath ~= 'stock.ttf', 'who text not mono')
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("raid: group outlines, cells and class buttons are cards, the secure cells keep their scripts", f"""
    {SHOW}
    local S = FS.SocialSkin.state
    assert(S.cards[RaidGroup1] and S.cards[RaidGroup2], 'groups not carded')
    assert(RaidGroup1GroupOutline.alpha == 0, 'outline kept')
    for i = 1, 10 do
        local c = _G['RaidGroupButton' .. i]
        assert(S.cards[c], 'cell ' .. i)
        assert(c.NormalTexture.alpha == 0, 'cell art kept ' .. i)
        assert(c.scripts.OnClick and c.scripts.OnEnter, 'cell script lost ' .. i)
    end
    assert(S.cards[RaidClassButton1], 'class button')
    assert(FS.ButtonSkins.Parts(RaidFrameConvertToRaidButton), 'convert key')
    assert(RaidGroup1Label.fs.fontPath ~= 'stock.ttf', 'group label not mono')
""")

case("raid info: the window is a dialog, headings and keys are skinned", f"""
    {SHOW}
    local info = RaidInfoFrame
    assert(FS.CommerceSkin.state.dialogs[info], 'raid info not a dialog')
    assert(info.Border.alpha == 0, 'border kept')
    assert(FS.GroupSkin.headers[RaidInfoInstanceLabel], 'heading')
    assert(FS.ButtonSkins.Parts(RaidInfoExtendButton) and FS.ButtonSkins.Parts(RaidInfoCancelButton), 'keys')
""")

case("combat: nothing is built while in combat, the build runs when it ends", """
    Reset()
    __combat = true
    FS = Load({ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'ButtonSkins', 'Character', 'Commerce', 'GroupKit', 'Social' })
    local first = FriendsListFrame.ScrollBox.rows[1]
    assert(not FS.SocialSkin.state.rows[first], 'built in combat')
    assert(not FriendsFrame.fsSocialSkin, 'marked in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(FS.SocialSkin.state.rows[first] and FriendsFrame.fsSocialSkin, 'not built when combat ended')
""")

case("a client without the Who, Raid and ignore frames degrades quietly", f"""
    WhoFrame, RaidFrame, RaidInfoFrame, FriendsFrameBattlenetFrame = nil, nil, nil, nil
    FriendsFrame.IgnoreListWindow = nil
    {SHOW}
    assert(FS.SocialSkin.state.rows[FriendsListFrame.ScrollBox.rows[1]], 'friends not skinned')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("running the skin again changes nothing: no second card or hook per row", f"""
    {SHOW}
    local r = FriendsListFrame.ScrollBox.rows[1]
    local n = #r.regions
    FS.SocialSkin.Build(); FriendsListFrame.ScrollBox:Update(); FlushTimers()
    assert(#r.regions == n, 'regions grew: ' .. n .. ' -> ' .. #r.regions)
""")

SCENES = {
    "friends": "Fire('PLAYER_ENTERING_WORLD'); FS.Theme.SkinPanel(FriendsFrame, {title='social'}); FriendsFrame:Show(); FriendsListFrame:Show(); FriendsListFrame.ScrollBox.rows[2]:LockHighlight(); FlushTimers(); return DumpOps({ FriendsFrame })",
    "ignore": "Fire('PLAYER_ENTERING_WORLD'); FriendsFrame:Show(); FriendsFrame.IgnoreListWindow:Show(); FriendsFrame.IgnoreListWindow.ScrollBox.rows[2]:LockHighlight(); FlushTimers(); return DumpOps({ FriendsFrame.IgnoreListWindow })",
    "who": "Fire('PLAYER_ENTERING_WORLD'); FS.Theme.SkinPanel(FriendsFrame, {title='social'}); FriendsFrame:Show(); FriendsListFrame:Hide(); FriendsTabHeader:Hide(); WhoFrame:Show(); WhoFrame.ScrollBox.rows[1]:LockHighlight(); FlushTimers(); return DumpOps({ FriendsFrame })",
    "raid": "Fire('PLAYER_ENTERING_WORLD'); FS.Theme.SkinPanel(FriendsFrame, {title='social'}); FriendsFrame:Show(); FriendsListFrame:Hide(); FriendsTabHeader:Hide(); RaidFrame:Show(); RaidInfoFrame:Show(); FlushTimers(); return DumpOps({ FriendsFrame, RaidInfoFrame })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("social skin", SCENES))
