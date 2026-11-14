#!/usr/bin/env python3
"""Runs the real Modules/Skins/Charters.lua (with Collections.lua and GroupKit.lua) headless against mock charter, invite, rename and death recap windows (tools/charskin_support.py).

Pinned: the guild registrar (parchment held, the greeting options cards with their icon kept, the guild name edit box a ring box with
its chat border art held, texts in mono, the cost label muted), the petition (parchment held, titles cyan, names text), the guild
invite (the stock frame art and the gold ring held, the guild tabard kept, panel chrome and an LED edge of ours, texts in mono), the
guild rename window (panel skin, texts in mono, its options cards), and the death recap (the eight border pieces and backdrop held,
panel chrome of ours, every list row a card with a pink LED for the killing blow, amounts kept red in mono, spell icons ringed); no
script or attribute is written on a Blizzard widget, nothing is built in combat, a missing window is skipped quietly and a second
build adds nothing. Run `python3 tools/charterskin-harness.py [--png debug/charter]`. The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring = BLZ.blz, BLZ.tex, BLZ.fstring
local build = BuildBlizzard
local DARK = { 0.17, 0.12, 0.05, 1 }   -- parchment ink

local function stock(fs)
    fs.SetFontObject = function(self, o)
        self.fontPath = "stock.ttf"
        self.textColor = { 1, 0.82, 0, 1 }
    end
    return fs
end
local function at(fs, rel, point, x, y)
    fs.points[1] = { point = point, rel = rel, relPoint = point, x = x or 0, y = y or 0 }
    return fs
end
local function titleButton(parent, name, text, x, y)
    local b = blz("Button", name, parent, 300, 16, "TOPLEFT", x, y)
    b.Icon = tex(b, nil, "BACKGROUND"); b.Icon.w, b.Icon.h = 16, 16
    b.highlightTex = tex(b, nil, "HIGHLIGHT")
    b.fs = at(stock(fstring(b, nil, text, 12, DARK)), b, "TOPLEFT", 20, 0)
    b.scripts.OnClick = function() end
    b.scripts.OnEnter = function() end
    return b
end
local function frameBase(name, w, h, x, y)
    local win = blz("Frame", name, UIParent, w, h, "TOPLEFT", x, y)
    win.shown = false
    win.NineSlice = blz("Frame", nil, win, w, h)
    win.Bg = tex(win, nil, "BACKGROUND")
    win.TitleContainer = blz("Frame", nil, win, w - 40, 20)
    win.CloseButton = blz("Button", nil, win, 15, 15, "TOPRIGHT", -6, -4)
    tex(win.CloseButton, nil, "BACKGROUND")
    return win
end
local function button(parent, name, text, w, x, y, point)
    local b = blz("Button", name, parent, w, 22, point or "TOPLEFT", x, y)
    b.fs = fstring(b, nil, text, 12, { 1, 1, 1, 1 })
    b.scripts.OnClick = function() end
    return b
end

function BuildBlizzard()
    build()
    for k in pairs(_G) do
        if type(k) == "string" and (k:find("^GuildRegistrar") or k:find("^Petition") or k:find("^GuildInvite") or k:find("^GuildRename")
            or k:find("^DeathRecap") or k == "AvailableServicesText") then _G[k] = nil end
    end

    -- the guild registrar
    local reg = frameBase("GuildRegistrarFrame", 338, 424, 60, -60)
    reg.Bg = tex(reg, "GuildRegistrarFrameBg", "BACKGROUND")
    tex(reg, "GuildRegistrarFramePortrait", "BACKGROUND")
    at(stock(fstring(reg, "GuildRegistrarText", "Greetings, I can sell you a charter.", 12, DARK)), reg, "TOPLEFT", 20, -330)
    local npc = blz("Frame", "GuildRegistrarNpcNameFrame", reg, 300, 14, "TOP", 0, -4)
    at(fstring(npc, "GuildRegistrarFrameNpcNameText", "Keeper Mook", 12, { 1, 1, 1, 1 }), npc, "CENTER")
    local greet = blz("Frame", "GuildRegistrarGreetingFrame", reg, 338, 424, "TOPLEFT", 0, 0)
    at(stock(fstring(greet, "AvailableServicesText", "Available Services", 14, DARK)), greet, "TOPLEFT", 20, -130)
    titleButton(greet, "GuildRegistrarButton1", "Purchase a guild charter", 10, -170)
    titleButton(greet, "GuildRegistrarButton2", "Register a guild charter", 10, -190)
    button(greet, "GuildRegistrarFrameGoodbyeButton", "Cancel", 75, -6, 4, "BOTTOMRIGHT")
    local buy = blz("Frame", "GuildRegistrarPurchaseFrame", reg, 338, 424, "TOPLEFT", 0, 0)
    buy.shown = false
    at(stock(fstring(buy, "GuildRegistrarPurchaseText", "Name your guild.", 12, DARK)), buy, "TOPLEFT", 20, -80)
    at(stock(fstring(buy, "GuildRegistrarCostLabel", "Costs:", 12)), buy, "TOPLEFT", 20, -140)
    local money = blz("Frame", "GuildRegistrarMoneyFrame", buy, 100, 20, "TOPLEFT", 90, -138)
    local edit = blz("EditBox", "GuildRegistrarFrameEditBox", buy, 130, 32, "TOPLEFT", 20, -170)
    edit.fontPath, edit.size = "chat.ttf", 14
    tex(edit, nil, "BACKGROUND"); tex(edit, nil, "BACKGROUND")
    edit.scripts.OnEnterPressed = function() end
    button(buy, "GuildRegistrarFramePurchaseButton", "Purchase", 85, 6, 4, "BOTTOMLEFT")
    button(buy, "GuildRegistrarFrameCancelButton", "Cancel", 75, -6, 4, "BOTTOMRIGHT")

    -- the petition
    local pet = frameBase("PetitionFrame", 338, 424, 420, -60)
    pet.Bg = tex(pet, "PetitionFrameBg", "BACKGROUND")
    local function line(name, text, size, y)
        at(stock(fstring(pet, name, text, size or 12, DARK)), pet, "TOPLEFT", 20, y)
    end
    line("PetitionFrameCharterTitle", "Guild Charter", 14, -70)
    line("PetitionFrameCharterName", "Stu's Crew", 12, -90)
    line("PetitionFrameMasterTitle", "Guild Master", 14, -120)
    line("PetitionFrameMasterName", "Stu", 12, -140)
    line("PetitionFrameMemberTitle", "Members", 14, -170)
    for i = 1, 9 do line("PetitionFrameMemberName" .. i, i <= 3 and ({ "Mook", "Grom", "Tala" })[i] or "", 12, -190 - (i - 1) * 16) end
    line("PetitionFrameInstructions", "Ask nine players to sign.", 12, -350)
    button(pet, "PetitionFrameCancelButton", "Close", 75, -6, 4, "BOTTOMRIGHT")
    button(pet, "PetitionFrameSignButton", "Sign", 75, 6, 4, "BOTTOMLEFT")

    -- the guild invite
    local inv = blz("Frame", "GuildInviteFrame", UIParent, 310, 188, "TOPLEFT", 60, -520)
    inv.shown = false
    inv.NineSlice = blz("Frame", nil, inv, 310, 188)
    inv.Bg = tex(inv, nil, "BACKGROUND")
    local back = tex(inv, "GuildInviteFrameBackground", "BACKGROUND"); back.w, back.h = 287, 116
    back.points[1] = { point = "TOP", rel = inv, relPoint = "TOP", x = 0, y = -12 }
    local tb = tex(inv, "GuildInviteFrameTabardBackground", "BORDER"); tb.w, tb.h = 62, 62
    tb.points[1] = { point = "BOTTOM", rel = back, relPoint = "BOTTOM", x = 0, y = -4 }
    local te = tex(inv, "GuildInviteFrameTabardEmblem", "ARTWORK"); te.w, te.h = 56, 64
    te.points[1] = { point = "CENTER", rel = tb, relPoint = "CENTER", x = 0, y = 0 }
    local tbd = tex(inv, "GuildInviteFrameTabardBorder", "ARTWORK"); tbd.w, tbd.h = 61, 60
    tbd.points[1] = { point = "CENTER", rel = tb, relPoint = "CENTER", x = 0, y = 0 }
    local ring = tex(inv, "GuildInviteFrameTabardRing", "OVERLAY"); ring.w, ring.h = 118, 76
    ring.points[1] = { point = "BOTTOM", rel = back, relPoint = "BOTTOM", x = 0, y = -12 }
    at(stock(fstring(inv, "GuildInviteFrameInviterName", "Mook", 11, { 1, 1, 1, 1 })), inv, "TOP", 0, -28)
    at(stock(fstring(inv, "GuildInviteFrameInviteText", "invites you to join", 11, { 1, 1, 1, 1 })), inv, "TOP", 0, -40)
    at(stock(fstring(inv, "GuildInviteFrameGuildName", "Stu's Crew", 14)), inv, "TOP", 0, -52)
    at(stock(fstring(inv, "GuildInviteFrameWarningText", "Joining removes you from your guild.", 12, { 1, 1, 1, 1 })), inv, "TOPLEFT", 12, -130)
    local pts = blz("Frame", nil, inv, 10, 10, "TOPRIGHT", -54, -86)
    inv.Points = pts
    pts.Title = at(stock(fstring(pts, nil, "Achievements", 11, { 1, 1, 1, 1 })), pts, "BOTTOM", -13, 0)
    pts.Text = at(stock(fstring(pts, nil, "25", 16, { 0, 1, 0, 1 })), pts, "TOP", -28, -3)
    pts.Icon = tex(pts, nil, "OVERLAY")
    button(inv, "GuildInviteFrameJoinButton", "Join", 110, 24, 24, "BOTTOMLEFT")
    button(inv, "GuildInviteFrameDeclineButton", "Decline", 140, -24, 24, "BOTTOMRIGHT")

    -- the guild rename window (load on demand)
    local ren = frameBase("GuildRenameFrame", 338, 496, 800, -60)
    ren.Background = tex(ren, nil, "BACKGROUND")
    local tf = blz("Frame", nil, ren, 320, 400, "TOPLEFT", 8, -62)
    ren.TitleFlow = tf
    tf.Description = at(stock(fstring(tf, nil, "Change your guild name or take a refund.", 12, DARK)), tf, "TOPLEFT", 10, -10)
    tf.RenameOption = titleButton(tf, nil, "Rename the guild", 10, -60)
    tf.RefundOption = titleButton(tf, nil, "Refund the guild", 10, -80)
    local rf = blz("Frame", nil, ren, 320, 400, "TOPLEFT", 8, -62)
    rf.shown = false
    ren.RenameFlow = rf
    rf.Description = at(stock(fstring(rf, nil, "Pick a new name.", 12, DARK)), rf, "TOPLEFT", 10, -10)
    rf.NameBox = blz("EditBox", nil, rf, 260, 22, "TOPLEFT", 15, -40)
    rf.StatusText = at(stock(fstring(rf, nil, "That name is taken.", 12, { 1, 0.1, 0.1, 1 })), rf, "TOPLEFT", 10, -70)
    rf.CostLabel = at(stock(fstring(rf, nil, "Costs:", 12, DARK)), rf, "TOPLEFT", 10, -100)
    rf.CostFrame = blz("Frame", nil, rf, 100, 20, "TOPLEFT", 10, -120)
    ren.ContextButton = button(ren, nil, "Go", 100, -6, 4, "BOTTOMRIGHT")
    ren.MoneyFrame = blz("Frame", nil, ren, 100, 20, "BOTTOMRIGHT", -120, 6)
    ren.GuildIcon = blz("Frame", nil, ren, 41, 52, "BOTTOMLEFT", 6, -11)

    -- the death recap
    local rec = blz("Frame", "DeathRecapFrame", UIParent, 410, 326, "TOPLEFT", 420, -520)
    rec.shown = false
    for _, n in ipairs({ "TopLeft", "TopRight", "BottomLeft", "BottomRight", "Top", "Bottom", "Left", "Right" }) do
        tex(rec, "DeathRecapFrameBorder" .. n, "BORDER")
    end
    rec.Background = tex(rec, nil, "BACKGROUND")
    rec.BackgroundInnerGlow = tex(rec, nil, "BACKGROUND")
    rec.Title = at(stock(fstring(rec, nil, "Death Recap", 12)), rec, "TOPLEFT", 12, -9)
    rec.Divider = tex(rec, nil, "ARTWORK")
    rec.Unavailable = at(stock(fstring(rec, nil, "Recap unavailable", 12)), rec, "CENTER")
    rec.Unavailable.shown = false
    rec.CloseXButton = blz("Button", nil, rec, 24, 24, "TOPRIGHT", 2, 1)
    tex(rec.CloseXButton, nil, "BACKGROUND")
    rec.CloseButton = button(rec, nil, "Close", 144, 0, 15, "BOTTOM")
    local box = blz("Frame", nil, rec, 380, 250, "TOPLEFT", 14, -34)
    rec.ScrollBox = box
    box.rows = {}
    box.ForEachFrame = function(self, fn) for _, r in ipairs(self.rows) do fn(r) end end
    box.Update = function() end
    box.FullUpdate, box.SetDataProvider = box.Update, box.Update
    DEATHS = {
        { amount = "-120", spell = "Frostbolt", caster = "Mook", died = false },
        { amount = "-840", spell = "Fireball", caster = "Grom", died = true, big = true },
    }
    for i, d in ipairs(DEATHS) do
        local row = blz("Frame", nil, box, 380, 32, "TOPLEFT", 0, -(i - 1) * 36)
        local di = blz("Frame", nil, row, 140, 32, "TOPLEFT", 0, 0)
        row.DamageInfo = di
        di.TombstoneIcon = tex(di, nil, "ARTWORK"); di.TombstoneIcon.shown = d.died
        di.AvoidableIcon = tex(di, nil, "ARTWORK"); di.AvoidableIcon.shown = false
        di.DeadlyIcon = tex(di, nil, "ARTWORK"); di.DeadlyIcon.shown = false
        di.Amount = at(stock(fstring(di, nil, d.amount, 12, { 0.75, 0.05, 0.05, 1 })), di, "RIGHT")
        di.AmountLarge = at(stock(fstring(di, nil, d.amount, 16, { 1, 0.07, 0.07, 1 })), di, "RIGHT")
        di.Amount.shown, di.AmountLarge.shown = not d.big, d.big and true or false
        di.scripts.OnEnter = function() end
        local si = blz("Frame", nil, row, 224, 32, "TOPLEFT", 156, 0)
        row.SpellInfo = si
        si.Icon = tex(si, nil, "ARTWORK"); si.Icon.w, si.Icon.h = 32, 32
        si.Icon.path = "Interface\\Icons\\spell_frost_" .. i
        si.Name = at(stock(fstring(si, nil, d.spell, 12)), si, "TOPLEFT", 40, -2)
        si.Caster = at(stock(fstring(si, nil, d.caster, 10, { 0.5, 0.5, 0.5, 1 })), si, "TOPLEFT", 40, -16)
        si.IconBorder = tex(si, nil, "OVERLAY")
        si.scripts.OnEnter = function() end
        box.rows[i] = row
    end
    rec.ScrollBar = blz("Frame", nil, rec, 12, 240, "TOPRIGHT", -8, -40)
end
"""

H = Harness({
    "ButtonSkins": "Core/ButtonSkins.lua",
    "Character": "Modules/Skins/Character.lua",
    "GroupKit": "Modules/Skins/GroupKit.lua",
    "Collections": "Modules/Skins/Collections.lua",
    "Charters": "Modules/Skins/Charters.lua",
}, BLIZZARD)
case = H.case

SHOW = "Fire('PLAYER_ENTERING_WORLD'); FlushTimers(); local C = FS.GroupSkin.C; local S = FS.CharterSkin.state\n"
LUA_HELPERS = """
local function same(a, b) return math.abs(a[1] - b[1]) < 0.01 and math.abs(a[2] - b[2]) < 0.01 and math.abs(a[3] - b[3]) < 0.01 end
local function textIs(fs, c) local r, g, b = fs:GetTextColor(); return same({ r, g, b }, c) end
local function mono(fs) return fs.fontPath ~= 'stock.ttf' and fs.fontPath ~= 'chat.ttf' end
local function held(o) return o.alpha == 0 end
local function stockArtHeld(frame, what)
    for _, r in ipairs(frame.regions) do
        if r.kind == 'Texture' and r.path then assert(r.alpha == 0, what .. ' stock art kept') end
    end
end
"""
PRE = SHOW + LUA_HELPERS

case("registrar: the parchment is held, the greeting texts are mono on light ink, the services title cyan", PRE + """
    local r = GuildRegistrarFrame
    assert(held(r.Bg) and held(GuildRegistrarFrameBg), 'parchment kept')
    assert(GuildRegistrarFramePortrait.alpha == 1, 'portrait must stay')
    assert(mono(GuildRegistrarText) and textIs(GuildRegistrarText, C.text), 'greeting text')
    assert(mono(GuildRegistrarFrameNpcNameText), 'npc name')
    assert(mono(AvailableServicesText) and textIs(AvailableServicesText, C.cyan), 'services title')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("registrar: the two options are cards, the stock highlight held, the icon and the click kept", PRE + """
    for _, n in ipairs({ 'GuildRegistrarButton1', 'GuildRegistrarButton2' }) do
        local b = _G[n]
        assert(S.cards[b], n .. ' not a card')
        assert(held(b.highlightTex) and b.Icon.alpha == 1, n .. ' art')
        assert(mono(b.fs) and textIs(b.fs, C.text), n .. ' label')
        assert(b.scripts.OnClick, n .. ' click lost')
    end
    local b = GuildRegistrarButton1
    local before = FS.GroupSkin.cards[b].box.edges[1].color[2]
    b:RunScript('OnEnter')
    assert(FS.GroupSkin.cards[b].box.edges[1].color[2] ~= before, 'hover did not light the edge')
""")

case("registrar: the purchase page wears mono text, a muted cost label and a ring round the guild name box", PRE + """
    assert(mono(GuildRegistrarPurchaseText) and textIs(GuildRegistrarPurchaseText, C.text), 'purchase text')
    assert(mono(GuildRegistrarCostLabel) and textIs(GuildRegistrarCostLabel, C.muted), 'cost label')
    local e = GuildRegistrarFrameEditBox
    stockArtHeld(e, 'edit box')
    assert(S.edits[e] and S.edits[e].edges[1].color, 'edit box has no ring')
    assert(mono(e) and e.scripts.OnEnterPressed, 'edit box font or script')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("petition: the parchment is held, titles cyan, names and the note readable mono", PRE + """
    assert(held(PetitionFrame.Bg) and held(PetitionFrameBg), 'parchment kept')
    for _, n in ipairs({ 'PetitionFrameCharterTitle', 'PetitionFrameMasterTitle', 'PetitionFrameMemberTitle' }) do
        assert(mono(_G[n]) and textIs(_G[n], C.cyan), n)
    end
    for _, n in ipairs({ 'PetitionFrameCharterName', 'PetitionFrameMasterName', 'PetitionFrameMemberName1', 'PetitionFrameMemberName9' }) do
        assert(mono(_G[n]) and textIs(_G[n], C.text), n)
    end
    assert(mono(PetitionFrameInstructions) and textIs(PetitionFrameInstructions, C.muted), 'note')
""")

case("invite: the stock frame art and the gold ring are held, the tabard kept, panel chrome and an LED of ours", PRE + """
    local f = GuildInviteFrame
    assert(held(f.NineSlice) and held(f.Bg), 'frame art kept')
    assert(held(GuildInviteFrameBackground) and held(GuildInviteFrameTabardRing), 'backdrop or ring kept')
    for _, n in ipairs({ 'GuildInviteFrameTabardBackground', 'GuildInviteFrameTabardEmblem', 'GuildInviteFrameTabardBorder' }) do
        assert(_G[n].alpha == 1, n .. ' (the guild crest) must stay')
    end
    assert(S.chrome[f] and S.leds[f], 'no chrome or LED')
    assert(f.scripts.OnClick == nil and GuildInviteFrameJoinButton.scripts.OnClick, 'click lost')
""")

case("invite: the texts are mono, the guild name cyan, the points keep their colour", PRE + """
    assert(mono(GuildInviteFrameInviterName) and textIs(GuildInviteFrameInviterName, C.muted), 'inviter')
    assert(mono(GuildInviteFrameInviteText) and textIs(GuildInviteFrameInviteText, C.muted), 'invite text')
    assert(mono(GuildInviteFrameGuildName) and textIs(GuildInviteFrameGuildName, C.cyan), 'guild name')
    assert(mono(GuildInviteFrameWarningText) and textIs(GuildInviteFrameWarningText, C.muted), 'warning')
    local p = GuildInviteFrame.Points
    assert(mono(p.Title) and textIs(p.Title, C.muted), 'points title')
    assert(mono(p.Text) and textIs(p.Text, { 0, 1, 0 }), 'points value must keep its stock green')
""")

case("rename: the panel skin, the parchment held, texts mono, options are cards, the status keeps its red", PRE + """
    local r = GuildRenameFrame
    assert(r.fsStripped and r.fsPanelTitle, 'panel skin missing')
    assert(held(r.Background), 'background kept')
    assert(mono(r.TitleFlow.Description) and textIs(r.TitleFlow.Description, C.text), 'description')
    assert(mono(r.RenameFlow.Description) and mono(r.RenameFlow.CostLabel) and textIs(r.RenameFlow.CostLabel, C.muted), 'flow text')
    assert(mono(r.RenameFlow.StatusText) and textIs(r.RenameFlow.StatusText, { 1, 0.1, 0.1 }), 'status must keep its red')
    for _, key in ipairs({ 'RenameOption', 'RefundOption' }) do
        local b = r.TitleFlow[key]
        assert(S.cards[b] and held(b.highlightTex) and b.Icon.alpha == 1 and b.scripts.OnClick, key)
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("death recap: the border pieces and backdrop are held, panel chrome of ours, title cyan", PRE + """
    local f = DeathRecapFrame
    for _, n in ipairs({ 'TopLeft', 'TopRight', 'BottomLeft', 'BottomRight', 'Top', 'Bottom', 'Left', 'Right' }) do
        assert(held(_G['DeathRecapFrameBorder' .. n]), n .. ' border kept')
    end
    assert(held(f.Background) and held(f.BackgroundInnerGlow) and held(f.Divider), 'backdrop kept')
    assert(S.chrome[f], 'no chrome')
    assert(mono(f.Title) and textIs(f.Title, C.cyan), 'title')
    assert(mono(f.Unavailable) and textIs(f.Unavailable, C.muted), 'unavailable text')
    assert(f.ScrollBox.alpha == 1 and f.CloseButton.alpha == 1 and f.CloseButton.scripts.OnClick, 'frames must stay stock')
""")

case("death recap: each row is a card, the killing blow lights pink, amounts keep their red in mono, the spell icon is ringed", PRE + """
    local rows = DeathRecapFrame.ScrollBox.rows
    for i, r in ipairs(rows) do
        assert(S.cards[r], 'row ' .. i)
        local di, si = r.DamageInfo, r.SpellInfo
        assert(mono(di.Amount) and mono(di.AmountLarge) and mono(si.Name) and mono(si.Caster), 'text not mono ' .. i)
        assert(textIs(di.Amount, { 0.75, 0.05, 0.05 }) and textIs(di.AmountLarge, { 1, 0.07, 0.07 }), 'amount colour lost ' .. i)
        assert(textIs(si.Name, C.text) and textIs(si.Caster, C.muted), 'name colours ' .. i)
        assert(held(si.IconBorder) and si.Icon.alpha == 1 and S.rings[si.Icon], 'icon ' .. i)
        assert(di.TombstoneIcon.alpha == 1, 'tombstone must stay')
        assert(di.scripts.OnEnter and si.scripts.OnEnter, 'tooltip scripts lost ' .. i)
    end
    assert(same(S.cards[rows[2]].led.t.color, C.pink), 'killing blow is not pink')
    assert(same(S.cards[rows[1]].led.t.color, C.dim), 'plain row is not dim')
    rows[1].DamageInfo.TombstoneIcon:Show()
    DeathRecapFrame.ScrollBox:Update()
    assert(same(S.cards[rows[1]].led.t.color, C.pink), 'a late killing blow was not followed')
""")

case("nothing is built in combat; it is built when combat ends", """
    Reset()
    __combat = true
    FS = Load({ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'ButtonSkins', 'Character', 'GroupKit', 'Collections', 'Charters' })
    assert(not FS.CharterSkin.state.cards[GuildRegistrarButton1], 'built in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(FS.CharterSkin.state.cards[GuildRegistrarButton1], 'not built when combat ended')
""")

case("a client without these windows degrades quietly, and a second build adds nothing", PRE + """
    local n = #GuildRegistrarButton1.regions
    local m = #DeathRecapFrame.ScrollBox.rows[1].regions
    FS.CharterSkin.Build(); DeathRecapFrame.ScrollBox:Update(); FlushTimers()
    assert(#GuildRegistrarButton1.regions == n and #DeathRecapFrame.ScrollBox.rows[1].regions == m, 'regions grew')
    GuildRegistrarFrame, PetitionFrame, GuildInviteFrame, GuildRenameFrame, DeathRecapFrame = nil, nil, nil, nil, nil
    FS.CharterSkin.Build()
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

SCENES = {
    "registrar": "Fire('PLAYER_ENTERING_WORLD'); FS.Theme.SkinPanel(GuildRegistrarFrame, {title='charter'}); GuildRegistrarFrame:Show(); GuildRegistrarGreetingFrame:Show(); FlushTimers(); return DumpOps({ GuildRegistrarFrame })",
    "purchase": "Fire('PLAYER_ENTERING_WORLD'); FS.Theme.SkinPanel(GuildRegistrarFrame, {title='charter'}); GuildRegistrarFrame:Show(); GuildRegistrarGreetingFrame:Hide(); GuildRegistrarPurchaseFrame:Show(); FlushTimers(); return DumpOps({ GuildRegistrarFrame })",
    "petition": "Fire('PLAYER_ENTERING_WORLD'); FS.Theme.SkinPanel(PetitionFrame, {title='petition'}); PetitionFrame:Show(); FlushTimers(); return DumpOps({ PetitionFrame })",
    "invite": "Fire('PLAYER_ENTERING_WORLD'); GuildInviteFrame:Show(); FlushTimers(); return DumpOps({ GuildInviteFrame })",
    "recap": "Fire('PLAYER_ENTERING_WORLD'); DeathRecapFrame:Show(); FlushTimers(); return DumpOps({ DeathRecapFrame })",
    "rename": "Fire('PLAYER_ENTERING_WORLD'); GuildRenameFrame:Show(); FlushTimers(); return DumpOps({ GuildRenameFrame })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("charter skin", SCENES))
