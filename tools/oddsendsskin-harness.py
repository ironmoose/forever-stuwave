#!/usr/bin/env python3
"""Runs the real Modules/Skins/OddsEnds.lua (with GroupKit.lua and Commerce.lua) headless against mock queue, clock, stopwatch,
battlefield map and pet stable windows (tools/charskin_support.py).

Pinned: the queue list drops its stock backdrop for the panel chrome, every ticket entry (made by the pool before or after the
skin ran) has its texts in mono, its stock separator held and one rule of ours that follows it, and its role icons stay stock;
the clock page keeps the stock check, edit box and drop downs but restyles the ticker and the labels, and the stopwatch toggle,
play and reset keys keep their own icons under a ring; the stopwatch window and its tab wear the panel chrome; the battlefield
map tab and bezel are held and ringed with lock on corners while the map itself is untouched; the pet stable gets the panel
skin, ringed pet slots that keep their icons, and mono texts; no script or attribute is written on a Blizzard widget, a frame a
client does not have is skipped, and nothing is built in combat. Run `python3 tools/oddsendsskin-harness.py [--png debug/odds]`.
The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring = BLZ.blz, BLZ.tex, BLZ.fstring
local build = BuildBlizzard
local STOCK = "Interface\\stock\\art"

function Ours(frame)
    local n = 0
    for _, r in ipairs(frame.regions) do
        if r.kind == "Texture" and r.path ~= STOCK then n = n + 1 end
    end
    return n
end

local function label(parent, name, text, size, color, point, x, y)
    local f = fstring(parent, name, text, size, color)
    f.points[1] = { point = point or "TOPLEFT", rel = parent, relPoint = point or "TOPLEFT", x = x or 0, y = y or 0 }
    return f
end

local function keyed(btn, normal)
    btn.NormalTexture = tex(btn, nil, "ARTWORK")
    btn.normalTex = btn.NormalTexture
    btn.highlightTex = tex(btn, nil, "HIGHLIGHT")
    btn.pushedTex = tex(btn, nil, "ARTWORK")
    btn.scripts.OnClick = function() end
    btn.scripts.OnEnter = function() end
    btn.scripts.OnLeave = function() end
    return btn
end

local function window(name, w, h, x, y)
    local win = blz("Frame", name, UIParent, w, h, "TOPLEFT", x, y)
    win.shown = false
    win.Bg = tex(win, nil, "BACKGROUND")
    win.NineSlice = blz("Frame", nil, win, w, h)
    win.TitleContainer = blz("Frame", nil, win, w - 40, 20)
    fstring(win, name .. "TitleText", name)
    local close = blz("Button", name .. "CloseButton", win, 15, 15, "TOPRIGHT", -6, -4)
    tex(close, nil, "BACKGROUND")
    win.CloseButton = close
    return win
end

function BuildBlizzard()
    build()
    for k in pairs(_G) do
        if type(k) == "string" and (k:find("^QueueStatus") or k:find("^Stopwatch") or k:find("^TimeManager")
            or k:find("^Battlefield") or k:find("^PetStable")) then _G[k] = nil end
    end

    -- the LFG ticket list: QueueStatusFrame (TooltipBackdropTemplate) and the pooled QueueStatusEntryTemplate frames
    local qf = blz("Frame", "QueueStatusFrame", UIParent, 275, 150, "TOPLEFT", 600, -120)
    qf.shown = false
    qf.NineSlice = blz("Frame", nil, qf, 275, 150)
    tex(qf.NineSlice, nil, "BACKGROUND"); tex(qf.NineSlice, nil, "BORDER")
    qf.active = {}
    qf.statusEntriesPool = {
        EnumerateActive = function(pool)
            local i = 0
            return function() i = i + 1; return qf.active[i] end
        end,
    }
    local function roleCount(parent, key, x)
        local f = blz("Frame", nil, parent, 40, 40, "TOP", x, -80)
        f.RoleIcon = tex(f, nil, "ARTWORK"); f.RoleIcon.w, f.RoleIcon.h = 40, 40
        f.Count = label(f, nil, "1/1", 12, { 1, 1, 1, 1 }, "TOP", 0, -42)
        parent[key] = f
    end
    function NewQueueEntry(h)
        local e = blz("Frame", nil, qf, 275, h or 150, "TOP", 0, -(#qf.active * 150))
        e.Title = label(e, nil, "", 16, { 1, 1, 1, 1 }, "TOPLEFT", 10, -10)
        e.Status = label(e, nil, "", 12, { 1, 0.82, 0, 1 }, "TOPLEFT", 10, -28)
        e.SubTitle = label(e, nil, "", 12, { 1, 0.82, 0, 1 }, "TOPLEFT", 10, -44)
        for i = 1, 3 do
            e["RoleIcon" .. i] = tex(e, nil, "ARTWORK"); e["RoleIcon" .. i].w, e["RoleIcon" .. i].h = 23, 23
        end
        e.TimeInQueue = label(e, nil, "Time in queue: 2 min", 12, { 1, 0.82, 0, 1 }, "TOPLEFT", 10, -100)
        e.AverageWait = label(e, nil, "Average wait: 5 min", 12, { 1, 0.82, 0, 1 }, "TOPLEFT", 10, -116)
        e.ExtraText = label(e, nil, "", 10, { 0.5, 0.5, 0.5, 1 }, "TOPLEFT", 10, -132)
        e.EntrySeparator = tex(e, nil, "ARTWORK"); e.EntrySeparator.h = 2
        roleCount(e, "HealersFound", 0); roleCount(e, "TanksFound", -50); roleCount(e, "DamagersFound", 50)
        e.AssignedSpec = blz("Frame", nil, e, 22, 22, "TOPRIGHT", -7, -8)
        e.AssignedSpec.Icon = tex(e.AssignedSpec, nil, "BACKGROUND")
        e.AssignedSpec.Border = tex(e.AssignedSpec, nil, "BORDER")
        e.AssignedSpec.shown = false
        qf.active[#qf.active + 1] = e
        return e
    end
    function QueueStatusEntry_SetMinimalDisplay(entry, title, status, subTitle)
        entry.Title:SetText(title); entry.Status:SetText(status); entry.Status:Show()
        entry.SubTitle:SetText(subTitle or ""); entry.AverageWait:Hide(); entry.TanksFound:Hide()
    end
    function QueueStatusEntry_SetFullDisplay(entry, title)
        entry.Title:SetText(title); entry.Status:Hide(); entry.TanksFound:Show(); entry.AverageWait:Show()
    end
    function QueueStatusFrame_SortAndAnchorEntries(frame)
        for i, e in ipairs(frame.active) do
            e:ClearAllPoints(); e:SetPoint("TOP", frame, "TOP", 0, -((i - 1) * 150))
            if i == 1 then e.EntrySeparator:Hide() else e.EntrySeparator:Show() end
        end
    end
    -- the eye: held by MicroBars.lua, not by this file
    local eye = blz("Button", "QueueStatusButton", UIParent, 45, 45, "TOPLEFT", 900, -120)
    eye.Eye = blz("Frame", nil, eye, 30, 30, "CENTER", 0, 0)
    eye.Eye.texture = tex(eye.Eye, nil, "ARTWORK")
    eye.scripts.OnEnter = function() end

    -- the clock page (ButtonFrameTemplate) and the stopwatch
    local tm = window("TimeManagerFrame", 200, 330, 100, -100)
    tex(tm, "TimeManagerGlobe", "OVERLAY")
    label(tm, "TimeManagerFrameTicker", "12:34 PM", 18, { 1, 1, 1, 1 }, "TOP", 0, -48)
    local swf = blz("Frame", "TimeManagerStopwatchFrame", tm, 180, 34, "TOPLEFT", 10, -86)
    label(swf, "TimeManagerStopwatchFrameText", "Show stopwatch", 11, { 1, 0.82, 0, 1 }, "LEFT", 4, 0)
    local chk = keyed(blz("CheckButton", "TimeManagerStopwatchCheck", swf, 32, 32, "RIGHT", -2, 0))
    chk.checkedTex = tex(chk, nil, "ARTWORK")
    local at = blz("Frame", "TimeManagerAlarmTimeFrame", tm, 180, 60, "TOPLEFT", 10, -130)
    tm.AlarmTimeFrame = at
    label(at, "TimeManagerAlarmTimeLabel", "Alarm time", 11, { 1, 0.82, 0, 1 }, "TOPLEFT", 0, 0)
    local am = blz("Frame", "TimeManagerAlarmMessageFrame", tm, 180, 60, "TOPLEFT", 10, -196)
    label(am, "TimeManagerAlarmMessageLabel", "Alarm message", 11, { 1, 0.82, 0, 1 }, "TOPLEFT", 0, 0)
    local eb = blz("EditBox", "TimeManagerAlarmMessageEditBox", am, 160, 20, "TOPLEFT", 4, -20)
    eb.fontPath, eb.size = "stock.ttf", 12
    for i, n in ipairs({ "TimeManagerAlarmEnabledButton", "TimeManagerMilitaryTimeCheck", "TimeManagerLocalTimeCheck" }) do
        local c = blz("CheckButton", n, tm, 24, 24, "TOPLEFT", 10, -250 - (i - 1) * 26)
        c.NormalTexture = tex(c, nil, "ARTWORK")
        c.Text = label(c, n .. "Text", n, 11, { 1, 1, 1, 1 }, "LEFT", 28, 0)
    end

    local sw = blz("Frame", "StopwatchFrame", UIParent, 150, 56, "TOPLEFT", 340, -130)
    sw.shown = false
    tex(sw, "StopwatchFrameBackgroundLeft", "BACKGROUND"); tex(sw, nil, "BACKGROUND")
    local tick = blz("Frame", "StopwatchTicker", sw, 150, 32, "TOP", 0, -6)
    for i, n in ipairs({ "StopwatchTickerHour", "StopwatchTickerMinute", "StopwatchTickerSecond" }) do
        label(tick, n, "00", 16, { 1, 1, 1, 1 }, "LEFT", 14 + (i - 1) * 40, 0)
        if i < 3 then label(tick, nil, ":", 16, { 1, 1, 1, 1 }, "LEFT", 14 + (i - 1) * 40 + 24, 0) end
    end
    local tab = blz("Frame", "StopwatchTabFrame", sw, 150, 22, "BOTTOM", 0, 62)
    for _, n in ipairs({ "Left", "Middle", "Right" }) do tex(tab, "StopwatchTabFrame" .. n, "BACKGROUND") end
    label(tab, "StopwatchTitle", "Stopwatch", 10, { 1, 0.82, 0, 1 }, "CENTER", 0, 0)
    local sclose = blz("Button", "StopwatchCloseButton", tab, 16, 16, "TOPRIGHT", 0, 0)
    tex(sclose, nil, "BACKGROUND")
    keyed(blz("Button", "StopwatchResetButton", sw, 22, 22, "BOTTOMLEFT", 8, 4))
    keyed(blz("Button", "StopwatchPlayPauseButton", sw, 22, 22, "BOTTOMLEFT", 36, 4))

    -- the battlefield map: a tab and the map canvas with its BorderFrame
    local bt = blz("Button", "BattlefieldMapTab", UIParent, 90, 32, "TOPLEFT", 500, -400)
    bt.Left = tex(bt, nil, "BACKGROUND"); bt.Middle = tex(bt, nil, "BACKGROUND"); bt.Right = tex(bt, nil, "BACKGROUND")
    bt.Text = label(bt, nil, "Map", 10, { 1, 1, 1, 1 }, "LEFT", 6, -5)
    bt.scripts.OnClick = function() end
    local bm = blz("Frame", "BattlefieldMapFrame", UIParent, 225, 150, "TOPLEFT", 500, -440)
    bm.shown = false
    local bf = blz("Frame", nil, bm, 225, 150, "TOPLEFT", 0, 0)
    bm.BorderFrame = bf
    for _, k in ipairs({ "TopLeft", "TopRight", "BottomLeft", "BottomRight", "Top", "Bottom", "Left", "Right" }) do bf[k] = tex(bf, nil, "ARTWORK") end
    bf.CloseButton = blz("Button", nil, bf, 16, 16, "TOPRIGHT", 2, 6)
    tex(bf.CloseButton, nil, "BACKGROUND")
    bf.CloseButton.scripts.OnClick = function() end
    bm.ScrollContainer = blz("Frame", nil, bm, 220, 145, "TOPLEFT", 2, -2)
    tex(bm.ScrollContainer, nil, "BACKGROUND")

    -- the hunter pet stable (names from the 16001 globals dump; no reference source)
    local ps = window("PetStableFrame", 340, 430, 700, -100)
    ps.shown = false
    tex(ps, "PetStableFramePortrait", "OVERLAY")
    for _, k in ipairs({ "Top", "Bottom", "Left", "Right", "TopLeft", "TopRight", "BottomLeft", "BottomRight" }) do tex(ps, "PetStableFrame" .. k, "BORDER") end
    label(ps, "PetStableFrameText", "Stable", 12, { 1, 1, 1, 1 }, "TOP", 0, -34)
    label(ps, "PetStableLevelText", "Level 12", 12, { 1, 1, 1, 1 }, "TOP", 0, -50)
    label(ps, "PetStableLoyaltyText", "Loyal", 12, { 1, 0.82, 0, 1 }, "TOP", 0, -66)
    label(ps, "PetStableSlotText", "Stable slots", 12, { 1, 0.82, 0, 1 }, "TOPLEFT", 20, -250)
    label(ps, "PetStableCostLabel", "Cost", 12, { 1, 0.82, 0, 1 }, "BOTTOMLEFT", 20, 40)
    local function slot(name, x, y)
        local b = blz("CheckButton", name, ps, 40, 40, "TOPLEFT", x, y)
        b.NormalTexture = tex(b, name .. "NormalTexture", "ARTWORK"); b.normalTex = b.NormalTexture
        b.icon = tex(b, name .. "IconTexture", "BORDER")
        b.icon.path = "Interface\\Icons\\Ability_Hunter_Pet_Wolf"
        b.highlightTex = tex(b, nil, "HIGHLIGHT")
        b.scripts.OnClick = function() end; b.scripts.OnEnter = function() end; b.scripts.OnLeave = function() end
        return b
    end
    slot("PetStableCurrentPet", 150, -90)
    slot("PetStableStabledPet1", 40, -280); slot("PetStableStabledPet2", 90, -280)
    for _, n in ipairs({ "PetStableMoneyFrame", "PetStableCostMoneyFrame" }) do
        local m = blz("Frame", n, ps, 120, 18, "BOTTOMRIGHT", -20, n == "PetStableMoneyFrame" and 14 or 40)
        for _, c in ipairs({ "Gold", "Silver", "Copper" }) do
            local b = blz("Button", n .. c .. "Button", m, 30, 18, "LEFT", 0, 0)
            fstring(b, n .. c .. "ButtonText", "1", 12, { 1, 1, 1, 1 })
        end
    end
    local buy = blz("Button", "PetStablePurchaseButton", ps, 120, 22, "BOTTOMLEFT", 20, 14)
    buy.Left = tex(buy, nil, "BACKGROUND"); buy.Middle = tex(buy, nil, "BACKGROUND"); buy.Right = tex(buy, nil, "BACKGROUND")
    buy.fs = fstring(buy, nil, "Buy slot", 11, { 1, 1, 1, 1 })
    buy.GetFontString = function(self) return self.fs end
    buy.scripts.OnClick = function() end
end
"""

H = Harness({
    "ButtonSkins": "Core/ButtonSkins.lua",
    "Character": "Modules/Skins/Character.lua",
    "Commerce": "Modules/Skins/Commerce.lua",
    "GroupKit": "Modules/Skins/GroupKit.lua",
    "OddsEnds": "Modules/Skins/OddsEnds.lua",
}, BLIZZARD)
BOOT = "Fire('PLAYER_ENTERING_WORLD'); FlushTimers()"


def case(name, body):
    H.case(name, body.replace("@BOOT@", BOOT))


case("queue list: the stock backdrop is held, the panel chrome and a cyan edge are drawn, the eye is left to the micro bars", """
    @BOOT@
    local f = QueueStatusFrame
    assert(f.NineSlice.alpha == 0, 'stock backdrop kept')
    assert(FS.OddsEndsSkin.state.panels[f], 'queue list not skinned')
    assert(Ours(f) >= 3, 'no chrome drawn: ' .. Ours(f))
    assert(f.fsOddsQueueSkin, 'no inspect marker')
    assert(QueueStatusButton.Eye.alpha == 1 and QueueStatusButton.Eye.texture.alpha == 1, 'eye touched')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("queue entries: texts in mono, separator held, our rule follows it, role art and counts stay stock", """
    @BOOT@
    local a, b = NewQueueEntry(), NewQueueEntry()
    QueueStatusEntry_SetMinimalDisplay(a, 'Hellfire Ramparts', 'Proposal', 'Normal')
    QueueStatusEntry_SetFullDisplay(b, 'Battleground')
    QueueStatusFrame_SortAndAnchorEntries(QueueStatusFrame)
    local S = FS.OddsEndsSkin.state
    for _, e in ipairs({ a, b }) do
        assert(S.entries[e], 'entry not skinned')
        assert(e.Title.fontPath ~= 'stock.ttf' and e.Status.fontPath ~= 'stock.ttf' and e.TimeInQueue.fontPath ~= 'stock.ttf'
            and e.AverageWait.fontPath ~= 'stock.ttf' and e.ExtraText.fontPath ~= 'stock.ttf' and e.SubTitle.fontPath ~= 'stock.ttf', 'text not mono')
        assert(e.EntrySeparator.alpha == 0, 'separator kept')
        assert(e.RoleIcon1.alpha == 1 and e.TanksFound.RoleIcon.alpha == 1, 'role art held')
        assert(e.TanksFound.Count.fontPath ~= 'stock.ttf', 'count not mono')
        assert(e.AssignedSpec.Border.alpha == 0 and e.AssignedSpec.Icon.alpha == 1, 'spec border/icon wrong')
    end
    assert(not S.entries[a].rule.shown, 'rule on the first entry, whose stock separator is hidden')
    assert(S.entries[b].rule.shown, 'rule missing on the second entry')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("queue entries: an entry that never went through the stock setup calls is skinned when the list is shown", """
    @BOOT@
    local e = NewQueueEntry()
    assert(not FS.OddsEndsSkin.state.entries[e], 'skinned before the list was shown')
    QueueStatusFrame:Show(); FlushTimers()
    assert(FS.OddsEndsSkin.state.entries[e], 'entry never skinned')
""")

case("clock page: ticker and labels mono, the stopwatch check keeps its icon under a ring, check, edit box and labels untouched", """
    @BOOT@
    local S = FS.OddsEndsSkin.state
    assert(TimeManagerFrameTicker.fontPath ~= 'stock.ttf', 'ticker not mono')
    assert(TimeManagerStopwatchFrameText.fontPath ~= 'stock.ttf' and TimeManagerAlarmTimeLabel.fontPath ~= 'stock.ttf'
        and TimeManagerAlarmMessageLabel.fontPath ~= 'stock.ttf', 'labels not mono')
    local chk = TimeManagerStopwatchCheck
    assert(S.keys[chk], 'check not a ring key')
    assert(chk.NormalTexture.alpha == 1, 'stopwatch icon held')
    assert(chk.highlightTex.alpha == 0, 'stock highlight kept')
    assert(Ours(chk) >= 5, 'ring not drawn')
    assert(chk.scripts.OnClick, 'click lost')
    assert(TimeManagerFrame.fsOddsClockSkin, 'no inspect marker')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("clock page: the ring lights on hover and follows the checked state", """
    @BOOT@
    local S = FS.OddsEndsSkin.state
    local chk = TimeManagerStopwatchCheck
    local function edge() return S.keys[chk].box.edges[1].color end
    local idle = { edge()[1], edge()[2], edge()[3] }
    chk:RunScript('OnEnter')
    assert(edge()[2] > idle[2] or edge()[3] > idle[3], 'hover did not light the edge')
    chk:RunScript('OnLeave')
    chk:SetChecked(true)
    local c = edge()
    local cy = FS.Theme.COLOR_POWER
    assert(math.abs(c[1] - cy[1]) < 0.01 and math.abs(c[2] - cy[2]) < 0.01, 'checked did not turn the edge cyan')
""")

case("stopwatch: the background and tab art are held, chrome and a ring tab are drawn, ticker in mono, keys keep their icons", """
    @BOOT@
    local S = FS.OddsEndsSkin.state
    assert(StopwatchFrameBackgroundLeft.alpha == 0, 'background kept')
    assert(StopwatchTabFrameLeft.alpha == 0 and StopwatchTabFrameMiddle.alpha == 0 and StopwatchTabFrameRight.alpha == 0, 'tab art kept')
    assert(S.panels[StopwatchFrame], 'no chrome')
    assert(StopwatchTickerHour.fontPath ~= 'stock.ttf' and StopwatchTickerMinute.fontPath ~= 'stock.ttf' and StopwatchTickerSecond.fontPath ~= 'stock.ttf', 'digits not mono')
    for _, r in ipairs(StopwatchTicker.regions) do assert(r.fontPath ~= 'stock.ttf', 'colon not mono') end
    assert(StopwatchTitle.fontPath ~= 'stock.ttf', 'title not mono')
    for _, b in ipairs({ StopwatchResetButton, StopwatchPlayPauseButton }) do
        assert(S.keys[b] and b.NormalTexture.alpha == 1, 'stopwatch key lost its icon or its ring')
        assert(b.scripts.OnClick, 'click lost')
    end
    assert(FS.ButtonSkins.Parts(StopwatchCloseButton), 'close key not skinned')
    assert(StopwatchFrame.fsOddsStopwatchSkin, 'no inspect marker')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("battlefield map: tab art and bezel art held, bezel ringed with lock on corners, the map canvas untouched", """
    @BOOT@
    local S = FS.OddsEndsSkin.state
    local bt, bf = BattlefieldMapTab, BattlefieldMapFrame.BorderFrame
    assert(bt.Left.alpha == 0 and bt.Middle.alpha == 0 and bt.Right.alpha == 0, 'tab art kept')
    assert(bt.Text.fontPath ~= 'stock.ttf', 'tab text not mono')
    assert(S.tabs[bt], 'tab not boxed')
    for _, k in ipairs({ 'TopLeft', 'TopRight', 'BottomLeft', 'BottomRight', 'Top', 'Bottom', 'Left', 'Right' }) do assert(bf[k].alpha == 0, 'bezel art kept ' .. k) end
    local rec = S.bezels[bf]
    assert(rec and rec.reticle and rec.reticle.tlH, 'no lock on corners')
    assert(BattlefieldMapFrame.ScrollContainer.regions[1].alpha == 1, 'map canvas held')
    assert(FS.ButtonSkins.Parts(bf.CloseButton), 'close key not skinned')
    assert(not rec.reticle.trH.shown and not rec.reticle.trV.shown and rec.reticle.tlH.shown, 'top right bracket kept under the close key')
    assert(BattlefieldMapFrame.fsOddsMapSkin, 'no inspect marker')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("pet stable: panel skin, ringed slots that keep their icons, texts in mono, money styled, keys swept", """
    @BOOT@
    PetStableFrame:Show(); FlushTimers()
    local S = FS.OddsEndsSkin.state
    assert(PetStableFrame.fsStripped, 'panel not stripped')
    assert(PetStableFrame.fsPanelTitle and PetStableFrame.fsPanelTitle:GetText():find('stable'), 'no title band')
    for _, n in ipairs({ 'PetStableCurrentPet', 'PetStableStabledPet1', 'PetStableStabledPet2' }) do
        local b = _G[n]
        assert(S.keys[b], n .. ' not a ring key')
        assert(_G[n .. 'IconTexture'].alpha == 1, 'pet icon held')
        assert(_G[n .. 'NormalTexture'].alpha == 0, 'slot frame art kept')
        assert(b.scripts.OnClick, 'click lost')
    end
    for _, n in ipairs({ 'PetStableLevelText', 'PetStableLoyaltyText', 'PetStableSlotText', 'PetStableCostLabel', 'PetStableFrameText' }) do
        assert(_G[n].fontPath ~= 'stock.ttf', n .. ' not mono')
    end
    assert(PetStableMoneyFrameGoldButtonText.fontPath ~= 'stock.ttf', 'money not styled')
    assert(FS.ButtonSkins.Parts(PetStablePurchaseButton), 'purchase key not swept')
    assert(PetStableFrame.fsOddsStableSkin, 'no inspect marker')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("no script or attribute is written on a Blizzard widget (the mock raises on it), and a second pass adds nothing", """
    @BOOT@
    QueueStatusFrame:Show(); PetStableFrame:Show(); StopwatchFrame:Show(); FlushTimers()
    local n, m = Ours(QueueStatusFrame), Ours(StopwatchFrame)
    FS.OddsEndsSkin.Build(); FlushTimers()
    assert(Ours(QueueStatusFrame) == n and Ours(StopwatchFrame) == m, 'a second build drew again')
""")

case("a client without these frames degrades quietly", """
    QueueStatusFrame, TimeManagerFrame, StopwatchFrame, BattlefieldMapTab, BattlefieldMapFrame, PetStableFrame = nil, nil, nil, nil, nil, nil
    QueueStatusEntry_SetMinimalDisplay, QueueStatusEntry_SetFullDisplay, QueueStatusFrame_SortAndAnchorEntries = nil, nil, nil
    Fire('PLAYER_ENTERING_WORLD'); FlushTimers()
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("combat: nothing is built while in combat, the build runs when it ends", """
    Reset()
    __combat = true
    FS = Load({ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'ButtonSkins', 'Character', 'Commerce', 'GroupKit', 'OddsEnds' })
    assert(not FS.OddsEndsSkin.state.panels[QueueStatusFrame], 'built in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(FS.OddsEndsSkin.state.panels[QueueStatusFrame], 'not built when combat ended')
""")

SCENES = {
    "queue": "Fire('PLAYER_ENTERING_WORLD'); local a, b = NewQueueEntry(250), NewQueueEntry(150); QueueStatusEntry_SetMinimalDisplay(a, 'Hellfire Ramparts', 'Proposal', 'Normal'); a:SetHeight(100); QueueStatusEntry_SetFullDisplay(b, 'Warsong Gulch'); QueueStatusFrame_SortAndAnchorEntries(QueueStatusFrame); QueueStatusFrame:SetHeight(300); QueueStatusFrame:Show(); FlushTimers(); return DumpOps({ QueueStatusFrame })",
    "clock": "Fire('PLAYER_ENTERING_WORLD'); FS.Theme.SkinPanel(TimeManagerFrame, {title='clock'}); TimeManagerFrame:Show(); StopwatchFrame:Show(); TimeManagerStopwatchCheck:SetChecked(true); FlushTimers(); return DumpOps({ TimeManagerFrame, StopwatchFrame })",
    "map": "Fire('PLAYER_ENTERING_WORLD'); BattlefieldMapFrame:Show(); FlushTimers(); return DumpOps({ BattlefieldMapTab, BattlefieldMapFrame })",
    "stable": "Fire('PLAYER_ENTERING_WORLD'); PetStableFrame:Show(); FlushTimers(); return DumpOps({ PetStableFrame })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("odds and ends skin", SCENES))
