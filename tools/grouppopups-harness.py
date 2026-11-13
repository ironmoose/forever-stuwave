#!/usr/bin/env python3
"""Runs the real Modules/Skins/GroupPopups.lua headless against mock group popups (tools/charskin_support.py).

Pinned: the ready check is one panel skin on ReadyCheckListenerFrame with a `stuwave://ready` band (the stock dialog art held, the
portrait frame held, the empty panel Popups.lua draws on the outer frame held so the player's own ready check shows no blank box),
its two keys are cut keys over the stock buttons (a green READY with a check, a pink NOT READY), every stock art piece of the
button held and the stock label replaced by ours; the role poll and the PvP role check hold the stock dialog border and heading,
wear a band, and every role button is a key with a drawn glyph (shield, cross, blade), the role word and a lit line, steel and
hatched when the stock code turns it off; the battleground invite is a pink panel with the stock background, border and divider
held and an amber name; nothing is written on a Blizzard widget; a second scan builds nothing; nothing is built in combat.
Run `python3 tools/grouppopups-harness.py [--png debug/popups]`. The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring = BLZ.blz, BLZ.tex, BLZ.fstring
local build = BuildBlizzard

local function atex(parent, name, layer, atlas, w, h)
    local t = tex(parent, name, layer)
    t.atlas = atlas
    t.GetAtlas = function(self) return self.atlas end
    t.SetAtlas = function(self, a) self.atlas = a end
    if w then t.w, t.h = w, h end
    return t
end
local function textButton(parent, name, text, w, h, point, relPoint, x, y)
    local b = blz("Button", name, parent, w, h)
    b.points[1] = { point = point, rel = parent, relPoint = relPoint or point, x = x or 0, y = y or 0 }
    b.Left, b.Middle, b.Right = atex(b, nil, "BACKGROUND", "UI-Panel-Button-Up", 8, h), atex(b, nil, "BACKGROUND", "UI-Panel-Button-Up", 8, h), atex(b, nil, "BACKGROUND", "UI-Panel-Button-Up", 8, h)
    b.fs = fstring(b, name and (name .. "Text") or nil, text, 12)
    b.fs.points[1] = { point = "CENTER", rel = b, relPoint = "CENTER", x = 0, y = 0 }
    b.pushedTex, b.highlightTex = tex(b, nil, "HIGHLIGHT"), tex(b, nil, "HIGHLIGHT")
    b.scripts.OnClick = function() end
    return b
end
local function dialogBorder(win)
    local b = blz("Frame", nil, win, win.w, win.h, "TOPLEFT", 0, 0)
    b.points[2] = { point = "BOTTOMRIGHT", rel = win, relPoint = "BOTTOMRIGHT", x = 0, y = 0 }
    atex(b, nil, "BORDER", "UI-Frame-DiamondMetal-CornerTopLeft", 32, 32)
    atex(b, nil, "BORDER", "UI-Frame-DiamondMetal-CornerBottomRight", 32, 32)
    b.Bg = tex(b, nil, "BACKGROUND")
    return b
end
local function closeButton(win, name)
    local b = blz("Button", name, win, 24, 24, "TOPRIGHT", -2, -2)
    atex(b, nil, "BACKGROUND", "UI-Panel-MinimizeButton-Up", 24, 24)
    b.scripts.OnClick = function() win:Hide() end
    return b
end
-- a role button as LFGRoleButtonTemplate / RolePollRoleButtonTemplate build it (70 x 70, the role icon as its normal texture, a check button)
local function roleButton(win, name, role, point, x, y, rel, relPoint, radio)
    local b = blz("Button", name, win, 70, 70, point, x, y)
    if rel then b.points[1] = { point = point, rel = rel, relPoint = relPoint, x = x, y = y } end
    b.role = role
    b.NormalTexture = atex(b, nil, "ARTWORK", "UI-LFG-RoleIcon-" .. role, 70, 70)
    b.GetNormalTexture = function(self) return self.NormalTexture end
    b.SetNormalAtlas = function(self, a) self.NormalTexture.atlas = a end
    local c = blz("CheckButton", nil, b, 24, 24, "BOTTOMLEFT", -5, -5)
    c.NormalTexture = atex(c, nil, "ARTWORK", radio and "common-radiobutton-circle" or "checkbox-minimal", 24, 24)
    c.CheckedTexture = atex(c, nil, "ARTWORK", radio and "common-radiobutton-dot" or "checkmark-minimal", 24, 24)
    c.GetNormalTexture = function(self) return self.NormalTexture end
    c.GetCheckedTexture = function(self) return self.CheckedTexture end
    c.scripts.OnClick = function() end
    c.IsVisible = function(self) return self.shown end
    b.checkButton = c
    b.scripts.OnEnter = function() end
    b.scripts.OnLeave = function() end
    b.scripts.OnClick = function() end
    return b
end

function BuildBlizzard()
    build()
    for k in pairs(_G) do
        if type(k) == "string" and (k:find("^ReadyCheck") or k:find("^RolePoll") or k:find("^PVPRoleCheck") or k:find("^PVPReady") or k:find("^CompactRaidFrameManager")) then _G[k] = nil end
    end

    -- ReadyCheckFrame (323 x 100): an invisible container, ReadyCheckListenerFrame carries all the art, the text and the two buttons
    local rc = blz("Frame", "ReadyCheckFrame", UIParent, 323, 100, "CENTER", 0, -10)
    rc.shown = false
    local l = blz("Frame", "ReadyCheckListenerFrame", rc, 323, 100, "TOPLEFT", 0, 0)
    l.points[2] = { point = "BOTTOMRIGHT", rel = rc, relPoint = "BOTTOMRIGHT", x = 0, y = 0 }
    l.shown = false
    l.Bg = tex(l, nil, "BACKGROUND")
    l.NineSlice = blz("Frame", nil, l, 323, 100, "TOPLEFT", 0, 0)
    atex(l.NineSlice, nil, "BORDER", "UI-Frame-PortraitMetal-CornerTopLeft", 80, 80)
    l.TitleContainer = blz("Frame", nil, l, 241, 20, "TOPLEFT", 58, -1)
    l.TitleContainer.TitleText = fstring(l.TitleContainer, nil, "Ready Check", 12)
    l.PortraitContainer = blz("Frame", nil, l, 1, 1, "TOPLEFT", 0, 0)
    local portrait = tex(l.PortraitContainer, "ReadyCheckPortrait", "BACKGROUND")
    portrait.w, portrait.h = 54, 54
    portrait.points[1] = { point = "TOPLEFT", rel = l.PortraitContainer, relPoint = "TOPLEFT", x = 0, y = 3 }
    local text = fstring(l, "ReadyCheckFrameText", "Ready check from Brannoch", 12)
    text.w, text.h = 240, 30
    text:SetJustifyH("CENTER")
    text.points[1] = { point = "TOP", rel = l, relPoint = "TOP", x = 20, y = -37 }
    textButton(l, "ReadyCheckFrameYesButton", "Ready", 119, 24, "BOTTOMRIGHT", "BOTTOM", 11, 16)
    textButton(l, "ReadyCheckFrameNoButton", "Not Ready", 119, 24, "BOTTOMLEFT", "BOTTOM", 22, 16)

    -- RolePollPopup (306 x 160)
    local rp = blz("Frame", "RolePollPopup", UIParent, 306, 160, "CENTER", 0, 100)
    rp.shown = false
    local head = fstring(rp, nil, "Select your role", 12, { 1, 1, 1, 1 })
    head.points[1] = { point = "TOP", rel = rp, relPoint = "TOP", x = 0, y = -15 }
    rp.Border = dialogBorder(rp)
    closeButton(rp, "RolePollPopupCloseButton")
    local rt = roleButton(rp, "RolePollPopupRoleButtonTank", "Tank", "TOPLEFT", 35, -35, nil, nil, true)
    local rh = roleButton(rp, "RolePollPopupRoleButtonHealer", "Healer", "LEFT", 15, 0, rt, "RIGHT", true)
    local rd = roleButton(rp, "RolePollPopupRoleButtonDPS", "DPS", "LEFT", 15, 0, rh, "RIGHT", true)
    rp.acceptButton = textButton(rp, "RolePollPopupAcceptButton", "Accept", 115, 22, "BOTTOM", "BOTTOM", 0, 15)

    -- PVPRoleCheckPopup (306 x 180)
    local pv = blz("Frame", "PVPRoleCheckPopup", UIParent, 306, 180, "CENTER", 0, 100)
    pv.shown = false
    local head2 = fstring(pv, nil, "Confirm your role", 12, { 1, 1, 1, 1 })
    head2.points[1] = { point = "TOP", rel = pv, relPoint = "TOP", x = 0, y = -15 }
    pv.Border = dialogBorder(pv)
    pv.TankIcon = roleButton(pv, "PVPRoleCheckPopupRoleButtonTank", "Tank", "TOPLEFT", 35, -35)
    pv.HealerIcon = roleButton(pv, "PVPRoleCheckPopupRoleButtonHealer", "Healer", "LEFT", 15, 0, pv.TankIcon, "RIGHT")
    pv.DPSIcon = roleButton(pv, "PVPRoleCheckPopupRoleButtonDPS", "DPS", "LEFT", 15, 0, pv.HealerIcon, "RIGHT")
    textButton(pv, "PVPRoleCheckPopupAcceptButton", "Accept", 115, 22, "BOTTOMRIGHT", "BOTTOM", -3, 15)
    local decline = textButton(pv, "PVPRoleCheckPopupDeclineButton", "Decline", 115, 22, "LEFT", "RIGHT", 6, 0)
    decline.points[1].rel = PVPRoleCheckPopupAcceptButton
    pv.Description = blz("Frame", "PVPRoleCheckPopupDescription", pv, 1, 16, "CENTER", 0, 57)
    pv.Description.points[1] = { point = "CENTER", rel = pv, relPoint = "BOTTOM", x = 0, y = 57 }
    pv.Description.Text = fstring(pv.Description, "PVPRoleCheckPopupDescriptionText", "Queued for Warsong Gulch", 12, { 1, 1, 1, 1 })
    pv.Description.Text.points[1] = { point = "CENTER", rel = pv.Description, relPoint = "CENTER", x = 0, y = 0 }

    -- PVPReadyDialog (306 x 210)
    local rd2 = blz("Frame", "PVPReadyDialog", UIParent, 306, 210, "CENTER", 0, 100)
    rd2.shown = false
    rd2.background = tex(rd2, "PVPReadyDialogBackground", "BACKGROUND")
    rd2.background.w, rd2.background.h = 294, 118
    rd2.background.points[1] = { point = "TOP", rel = rd2, relPoint = "TOP", x = 0, y = -11 }
    rd2.label = fstring(rd2, "PVPReadyDialogLabel", "Your battleground is ready", 12, { 1, 1, 1, 1 })
    rd2.label.w, rd2.label.h = 200, 14
    rd2.label:SetJustifyH("CENTER")
    rd2.label.points[1] = { point = "TOP", rel = rd2, relPoint = "TOP", x = 0, y = -15 }
    rd2.bottomArt = atex(rd2, "PVPReadyDialogBottomArt", "OVERLAY", "UI-LFG-DividerLine", 287, 4)
    rd2.bottomArt.points[1] = { point = "TOP", rel = rd2.background, relPoint = "BOTTOM", x = 0, y = 1 }
    rd2.roleDescription = fstring(rd2, "PVPReadyDialogYourRoleDescription", "Your role", 10, { 1, 1, 1, 1 })
    rd2.roleDescription.points[1] = { point = "BOTTOMRIGHT", rel = rd2, relPoint = "BOTTOMLEFT", x = 108, y = 93 }
    rd2.roleLabel = fstring(rd2, "PVPReadyDialogRoleLabel", "Healer", 16)
    rd2.roleLabel.points[1] = { point = "TOPRIGHT", rel = rd2.roleDescription, relPoint = "BOTTOMRIGHT", x = 0, y = 0 }
    rd2.Border = dialogBorder(rd2)
    closeButton(rd2, "PVPReadyDialogCloseButton")
    rd2.enterButton = textButton(rd2, "PVPReadyDialogEnterBattleButton", "Enter Battle", 115, 22, "BOTTOMRIGHT", "BOTTOM", -7, 25)
    rd2.leaveButton = textButton(rd2, "PVPReadyDialogLeaveQueueButton", "Leave Queue", 115, 22, "BOTTOMLEFT", "BOTTOM", 7, 25)
    rd2.roleIcon = blz("Frame", "PVPReadyDialogRoleIcon", rd2, 67, 67, "BOTTOM", -1, 54)
    rd2.roleIcon.texture = atex(rd2.roleIcon, nil, "ARTWORK", "UI-LFG-RoleIcon-Healer", 67, 67)
    rd2.roleIcon.texture.points[1] = { point = "CENTER", rel = rd2.roleIcon, relPoint = "CENTER", x = 0, y = 0 }
    rd2.instanceInfo = blz("Frame", "PVPReadyDialogInstanceInfoFrame", rd2, 170, 50, "TOP", 0, -30)
    rd2.instanceInfo.underline = tex(rd2.instanceInfo, nil, "BACKGROUND")
    rd2.instanceInfo.underline.w, rd2.instanceInfo.underline.h = 170, 40
    rd2.instanceInfo.underline.points[1] = { point = "TOP", rel = rd2.instanceInfo, relPoint = "TOP", x = 0, y = 0 }
    rd2.instanceInfo.name = fstring(rd2.instanceInfo, "PVPReadyDialogInstanceInfoFrameName", "Warsong Gulch", 16)
    rd2.instanceInfo.name.w, rd2.instanceInfo.name.h = 280, 20
    rd2.instanceInfo.name:SetJustifyH("CENTER")
    rd2.instanceInfo.name.points[1] = { point = "BOTTOM", rel = rd2.instanceInfo.underline, relPoint = "TOP", x = 0, y = -30 }
    rd2.instanceInfo.statusText = fstring(rd2.instanceInfo, "PVPReadyDialogInstanceInfoFrameStatusText", "Battleground", 12)
    rd2.instanceInfo.statusText.points[1] = { point = "BOTTOM", rel = rd2.instanceInfo, relPoint = "BOTTOM", x = 0, y = 0 }

    -- CompactRaidFrameManager (222 x 140, the pull-out of the left edge): a Background texture, the toggle arrow, a DisplayFrame
    -- over all of it with the RAID label and the member count, the bottom buttons (Leave Party, Leave Instance Group)
    local m = blz("Frame", "CompactRaidFrameManager", UIParent, 222, 140, "TOPLEFT", 7, -140)
    m.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 7, y = -140 }
    m.shown = false
    m.Background = atex(m, nil, "ARTWORK", "GM-bgOpen-leader", 222, 140)
    m.Background.points[1] = { point = "TOPLEFT", rel = m, relPoint = "TOPLEFT", x = 0, y = 0 }
    m.Background.points[2] = { point = "BOTTOMRIGHT", rel = m, relPoint = "BOTTOMRIGHT", x = 0, y = 0 }
    m.toggleButtonForward = blz("Button", "CompactRaidFrameManagerToggleButtonForward", m, 16, 35, "RIGHT", -7, 0)
    m.toggleButtonForward.NormalTexture = atex(m.toggleButtonForward, nil, "ARTWORK", "gm-btnforward-normal", 16, 35)
    m.toggleButtonForward.scripts.OnClick = function() end
    local d = blz("Frame", "CompactRaidFrameManagerDisplayFrame", m, 222, 140, "TOPLEFT", 0, 0)
    d.points[2] = { point = "BOTTOMRIGHT", rel = m, relPoint = "BOTTOMRIGHT", x = 0, y = 0 }
    d.label = fstring(d, "CompactRaidFrameManagerDisplayFrameRaidMembersLabel", "RAID", 14)
    d.label.points[1] = { point = "TOPLEFT", rel = d, relPoint = "TOPLEFT", x = 10, y = -15 }
    d.memberCountLabel = fstring(d, "CompactRaidFrameManagerDisplayFrameRaidMemberCountLabel", "10/10", 14)
    d.memberCountLabel.points[1] = { point = "TOPRIGHT", rel = d, relPoint = "TOPRIGHT", x = -30, y = -15 }
    m.displayFrame = d
    m.BottomButtons = blz("Frame", nil, m, 160, 53, "BOTTOM", 0, 10)
    textButton(m.BottomButtons, "CompactRaidFrameManagerBottomButtonsLeavePartyButton", "Leave Party", 160, 24, "TOP", "TOP", 0, 0)
end
"""

H = Harness({"ButtonSkins": "Core/ButtonSkins.lua", "CheckSkins": "Core/CheckSkins.lua", "FieldSkins": "Core/FieldSkins.lua",
             "Character": "Modules/Skins/Character.lua", "GroupKit": "Modules/Skins/GroupKit.lua", "Loot": "Modules/Skins/Loot.lua",
             "Popups": "Modules/Skins/Popups.lua", "GroupPopups": "Modules/Skins/GroupPopups.lua"}, BLIZZARD)
case = H.case

OPEN_READY = "Fire('PLAYER_ENTERING_WORLD'); ReadyCheckFrame:Show(); ReadyCheckListenerFrame:Show(); FlushTimers()"
OPEN_ROLES = "Fire('PLAYER_ENTERING_WORLD'); RolePollPopup:Show(); FlushTimers()"
OPEN_QUEUE = "Fire('PLAYER_ENTERING_WORLD'); PVPRoleCheckPopup:Show(); FlushTimers()"
OPEN_INVITE = "Fire('PLAYER_ENTERING_WORLD'); PVPReadyDialog:Show(); FlushTimers()"

case("ready check: one panel skin on the listener with a ready band, the stock dialog art held, the blank outer panel held", f"""
    {OPEN_READY}
    local l = ReadyCheckListenerFrame
    assert(l.fsSkinCache, 'no panel chrome on the listener')
    assert(l.fsPanelTitle and l.fsPanelTitle:GetText() == 'stuwave://ready', 'band label')
    assert(l.Bg.alpha == 0 or l.Bg.shown == false, 'dialog background kept')
    assert(l.NineSlice.alpha == 0 and l.TitleContainer.alpha == 0 and l.PortraitContainer.alpha == 0, 'portrait frame art kept')
    assert(ReadyCheckFrameText.fontPath ~= 'stock.ttf', 'text not mono')
    for i, r in ipairs({{ ReadyCheckFrame:GetRegions() }}) do assert(r.alpha == 0, 'blank outer panel region ' .. i .. ' kept') end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("ready check: READY is a green key with a check, NOT READY a pink key; stock art and label held, clicks stock", f"""
    {OPEN_READY}
    local S = FS.GroupPopupSkin.state
    local yes, no = ReadyCheckFrameYesButton, ReadyCheckFrameNoButton
    local ky, kn = S.keys[yes], S.keys[no]
    assert(ky and kn, 'keys not skinned')
    assert(ky.color[2] > 0.9 and ky.color[1] < 0.4, 'ready key not green')
    assert(kn.color[1] > 0.9 and kn.color[2] < 0.4, 'not ready key not pink')
    assert(ky.glyph and #ky.glyph.rects > 0 and not kn.glyph, 'check glyph on the ready key only')
    assert(ky.label:GetText() == 'Ready' and kn.label:GetText() == 'Not Ready', 'labels')
    assert(yes.fs.alpha == 0 and yes.Left.alpha == 0, 'stock label or art kept')
    local p = FS.ButtonSkins.Parts(yes)
    assert(p and p.face.alpha == 0 and p.ring.alpha == 0 and p.halo.alpha == 0, 'the default key plate still shows')
    assert(yes.scripts.OnClick and no.scripts.OnClick, 'click lost')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("ready check keys: hover lights the edge, a disabled key goes steel", f"""
    {OPEN_READY}
    local S = FS.GroupPopupSkin.state
    local yes = ReadyCheckFrameYesButton
    local k = S.keys[yes]
    local idle = k.plate.ring.vertex[4]
    yes:RunScript('OnEnter')
    assert(k.plate.ring.vertex[4] > idle, 'hover did not brighten the edge')
    yes:RunScript('OnLeave')
    yes:Disable()
    local v = k.plate.ring.vertex
    assert(v[1] > 0.4 and v[3] > 0.5 and v[2] < 0.7, 'disabled edge not steel')
""")

case("role poll: heading and dialog border held, a roles band, accept and close keys", f"""
    {OPEN_ROLES}
    local w = RolePollPopup
    assert(w.Border.alpha == 0, 'dialog border kept')
    local S = FS.GroupPopupSkin.state
    assert(S.bands[w] and S.bands[w].label:GetText() == 'stuwave://roles', 'band label')
    assert(S.bands[w].label.alpha ~= 0, 'our band label is held')
    for i, r in ipairs({{ w:GetRegions() }}) do
        if r.kind == 'FontString' and r ~= S.bands[w].label then assert(r.alpha == 0, 'stock heading kept') end
    end
    local k = S.keys[w.acceptButton]
    assert(k and k.color[3] > 0.9 and k.color[1] < 0.3, 'accept not a cyan key')
    assert(k.glyph, 'accept check glyph')
    assert(FS.ButtonSkins.Parts(RolePollPopupCloseButton), 'close key')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("role poll: each role button is a key with a drawn glyph, the role word and a lit line; the stock icon art held", f"""
    {OPEN_ROLES}
    local S = FS.GroupPopupSkin.state
    local want = {{ [RolePollPopupRoleButtonTank] = 'shield', [RolePollPopupRoleButtonHealer] = 'cross', [RolePollPopupRoleButtonDPS] = 'blade' }}
    for b, glyph in pairs(want) do
        local r = S.roles[b]
        assert(r and r.plate and r.led and r.label, 'role key missing')
        assert(r.glyph.name == glyph, 'glyph ' .. tostring(r.glyph.name) .. ' want ' .. glyph)
        assert(b.NormalTexture.alpha == 0, 'stock role icon kept')
        assert(r.label:GetText() ~= '' and r.label.fontPath ~= 'stock.ttf', 'role word')
        assert(b.scripts.OnClick and b.scripts.OnEnter, 'role click lost')
        assert(FS.CheckSkins.Parts(b.checkButton), 'radio not skinned')
    end
    local t = S.roles[RolePollPopupRoleButtonTank]
    local h = S.roles[RolePollPopupRoleButtonHealer]
    local d = S.roles[RolePollPopupRoleButtonDPS]
    local function rgb(r) local c = r.glyph.rects[1].color; return c end
    assert(rgb(t)[3] > 0.9 and rgb(t)[1] < 0.3, 'tank not cyan')
    assert(rgb(h)[2] > 0.9 and rgb(h)[1] < 0.4 and rgb(h)[3] < 0.3, 'healer not green')
    assert(rgb(d)[1] > 0.9 and rgb(d)[2] < 0.4, 'dps not red')
""")

case("a role the class cannot take: the stock code disables the button, the key goes steel, hatched, no lit line", f"""
    {OPEN_ROLES}
    local S = FS.GroupPopupSkin.state
    local b = RolePollPopupRoleButtonTank
    local r = S.roles[b]
    assert(not r.hatch.shown or r.hatch.alpha == 0, 'hatch on an open role')
    b.permDisabled = true
    b:Disable()
    assert(r.hatch.shown and r.hatch.alpha > 0, 'no hatch on a closed role')
    local c = r.glyph.rects[1].color
    assert(c[1] > 0.4 and c[3] > 0.5 and c[2] < 0.7, 'glyph not steel')
    assert(r.led.alpha == 0 or not r.led.shown, 'lit line on a closed role')
    b:Enable()
    assert(not r.hatch.shown or r.hatch.alpha == 0, 'hatch kept after enable')
    assert(r.led.shown, 'lit line lost')
""")

case("a checked role lights the key: cyan edge and band", f"""
    {OPEN_ROLES}
    local S = FS.GroupPopupSkin.state
    local b = RolePollPopupRoleButtonDPS
    local r = S.roles[b]
    local idle = {{ r.plate.ring.vertex[1], r.plate.ring.vertex[2], r.plate.ring.vertex[3] }}
    b.checkButton:SetChecked(true)
    local v = r.plate.ring.vertex
    assert(v[1] ~= idle[1] or v[2] ~= idle[2] or v[3] ~= idle[3], 'checking did not repaint the key')
    b.checkButton:SetChecked(false)
    v = r.plate.ring.vertex
    assert(v[1] == idle[1] and v[2] == idle[2] and v[3] == idle[3], 'unchecking did not restore it')
""")

case("pvp role check: its own panel skin with a queue band, border and heading held, role keys, accept and decline keys, mono description", f"""
    {OPEN_QUEUE}
    local w = PVPRoleCheckPopup
    local S = FS.GroupPopupSkin.state
    assert(w.fsSkinCache, 'no panel chrome')
    assert(w.fsPanelTitle and w.fsPanelTitle:GetText() == 'stuwave://queue', 'band label')
    assert(w.Border.alpha == 0, 'dialog border kept')
    assert(w.fsPanelTitle.alpha ~= 0, 'our band label is held')
    for i, r in ipairs({{ w:GetRegions() }}) do
        if r.kind == 'FontString' and r ~= w.fsPanelTitle then assert(r.alpha == 0, 'stock heading kept') end
    end
    for _, b in ipairs({{ w.TankIcon, w.HealerIcon, w.DPSIcon }}) do assert(S.roles[b], 'role key missing') end
    local a, d = S.keys[PVPRoleCheckPopupAcceptButton], S.keys[PVPRoleCheckPopupDeclineButton]
    assert(a and a.color[3] > 0.9 and a.color[1] < 0.3, 'accept not cyan')
    assert(d and d.color[1] > 0.9 and d.color[2] < 0.4, 'decline not pink')
    assert(w.Description.Text.fontPath ~= 'stock.ttf', 'description not mono')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("invite ticket: a pink panel with an invite band, background, border and divider held, amber name, enter and leave keys", f"""
    {OPEN_INVITE}
    local w = PVPReadyDialog
    local S = FS.GroupPopupSkin.state
    assert(w.fsSkinCache, 'no panel chrome')
    assert(w.fsPanelTitle and w.fsPanelTitle:GetText() == 'stuwave://invite', 'band label')
    assert(w.background.alpha == 0 or w.background.shown == false, 'battleground art kept')
    assert(w.bottomArt.alpha == 0 or w.bottomArt.shown == false, 'divider kept')
    assert(w.Border.alpha == 0, 'dialog border kept')
    assert(w.instanceInfo.underline.alpha == 0, 'underline kept')
    local n = w.instanceInfo.name
    assert(n.fontPath ~= 'stock.ttf' and n.textColor[1] > 0.9 and n.textColor[2] > 0.6 and n.textColor[3] < 0.5, 'name not amber mono')
    assert(w.label.fontPath ~= 'stock.ttf' and w.roleLabel.fontPath ~= 'stock.ttf', 'texts not mono')
    local e, l = S.keys[w.enterButton], S.keys[w.leaveButton]
    assert(e and e.color[3] > 0.9 and e.color[1] < 0.3, 'enter not cyan')
    assert(l and l.color[1] > 0.9 and l.color[2] < 0.4, 'leave not pink')
    assert(w.roleIcon.texture.alpha ~= 0, 'the stock role icon is the ticket stub: kept')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("raid manager: the pull-out wears our panel, its stock background and label tints held, its buttons skinned, its alpha stays the party code's", f"""
    Fire('PLAYER_ENTERING_WORLD'); CompactRaidFrameManager:Show(); FlushTimers()
    local m = CompactRaidFrameManager
    assert(m.fsGroupManagerSkin, 'not skinned')
    assert(m.Background.alpha == 0, 'stock background kept')
    assert(#({{ m:GetRegions() }}) > 1, 'no chrome drawn')
    local d = m.displayFrame
    assert(d.label.fontPath ~= 'stock.ttf' and d.memberCountLabel.fontPath ~= 'stock.ttf', 'labels not mono')
    assert(FS.ButtonSkins.Parts(CompactRaidFrameManagerBottomButtonsLeavePartyButton), 'leave key')
    assert(m.toggleButtonForward.scripts.OnClick, 'toggle click lost')
    m:SetAlpha(0); assert(m.alpha == 0, 'alpha not 0')
    m:SetAlpha(1); assert(m.alpha == 1, 'alpha held at 0: the party code could not give the manager back')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("nothing is written on a Blizzard widget, a second pass builds nothing, nothing is built in combat", f"""
    {OPEN_READY}
    RolePollPopup:Show(); PVPRoleCheckPopup:Show(); PVPReadyDialog:Show(); CompactRaidFrameManager:Show(); FlushTimers()
    local n = ObjCount()
    for _, f in ipairs({{ ReadyCheckListenerFrame, RolePollPopup, PVPRoleCheckPopup, PVPReadyDialog, CompactRaidFrameManager }}) do f:Hide(); f:Show() end
    Fire('PLAYER_ENTERING_WORLD'); FlushTimers()
    assert(ObjCount() == n, 'rebuilt ' .. (ObjCount() - n))
    Reset()
    __combat = true
    Load({{ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'ButtonSkins', 'CheckSkins', 'FieldSkins', 'Character', 'GroupKit', 'Loot', 'Popups', 'GroupPopups' }})
    assert(not _G.FS.GroupPopupSkin.state.keys[ReadyCheckFrameYesButton], 'built in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(_G.FS.GroupPopupSkin.state.keys[ReadyCheckFrameYesButton], 'not built after combat')
""")

SCENES = {
    "ready": "Fire('PLAYER_ENTERING_WORLD'); ReadyCheckFrame:Show(); ReadyCheckListenerFrame:Show(); FlushTimers(); return DumpOps({ ReadyCheckFrame })",
    "roles": "Fire('PLAYER_ENTERING_WORLD'); RolePollPopup:Show(); RolePollPopupRoleButtonTank.permDisabled = true; RolePollPopupRoleButtonTank:Disable(); RolePollPopupRoleButtonDPS.checkButton:SetChecked(true); FlushTimers(); return DumpOps({ RolePollPopup })",
    "queue": "Fire('PLAYER_ENTERING_WORLD'); PVPRoleCheckPopup:Show(); PVPRoleCheckPopup.HealerIcon.checkButton:SetChecked(true); FlushTimers(); return DumpOps({ PVPRoleCheckPopup })",
    "invite": "Fire('PLAYER_ENTERING_WORLD'); PVPReadyDialog:Show(); FlushTimers(); return DumpOps({ PVPReadyDialog })",
    "manager": "Fire('PLAYER_ENTERING_WORLD'); CompactRaidFrameManager:Show(); FlushTimers(); return DumpOps({ CompactRaidFrameManager })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("group popups skin", SCENES))
