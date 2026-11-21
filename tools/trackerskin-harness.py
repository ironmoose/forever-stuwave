#!/usr/bin/env python3
"""Runs the real Modules/Tracker/Tracker.lua headless against a mock objective tracker (tools/charskin_support.py).

The mock is built from the 12.1.0 Blizzard_ObjectiveTracker source: a container (NineSlice, 32 px Header with its
MinimizeButton, topModulePadding 38) holding module frames (Header, usedBlocks), quest blocks (HeaderText, HeaderButton,
poiButton hung TOPRIGHT of HeaderText at -7,+5, usedLines with Dash and Text, lastRegion). The widget engine throws on a
SetScript or SetAttribute against a Blizzard widget, so every case below also proves the skin writes neither.

Pinned: the band sits in the container's own 32 px header strip over the full-height panel; collapsed, the panel is exactly
the 24 px bar and Blizzard's NineSlice stays at alpha 0 whatever it writes; the bar carries one tick per quest and an amber
LED while one is ready; the plus and minus are the same two bars; module headers keep their own text as a mono sub-head with
a diamond; quest rows get the spine, ticks, fill and wash states of the mockup, built from our own regions anchored to stock
rows; failed quests wear the X marker; no Blizzard layout field is written. Run `python3 tools/trackerskin-harness.py
[--png debug/tracker]`. The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
function BuildBlizzard()
    local blz, tex, fstring = BLZ.blz, BLZ.tex, BLZ.fstring
    NOW = 100
    function GetTime() return NOW end
    -- an error our hooks catch is handed to the error handler: collected, and every case ends by asserting none came
    ERRS = {}
    function geterrorhandler() return function(e) ERRS[#ERRS + 1] = tostring(e) end end
    function Clean()
        assert(#DEGRADED == 0, table.concat(DEGRADED, '\n'))
        assert(#ERRS == 0, table.concat(ERRS, '\n'))
    end
    -- widget methods the shared engine has no use for yet
    function Obj:IsVisible() local o = self while o do if o.shown == false then return false end o = o.parent end return true end
    function Obj:GetLeft() local l = self:Rect() return l end
    function Obj:GetRight() local _, _, r = self:Rect() return r end
    function Obj:GetTop() local _, t = self:Rect() return UI_H - t end
    function Obj:GetBottom() local _, _, _, b = self:Rect() return UI_H - b end
    function Obj:GetCenter() local l, t, r, b = self:Rect() return (l + r) / 2, UI_H - (t + b) / 2 end
    function Obj:SetFrameStrata(s) self.strata = s end
    function Obj:GetFrameStrata() return self.strata or "LOW" end
    function Obj:SetHitRectInsets(a, b, c, d) self.hit = { a, b, c, d } end
    function Obj:GetHitRectInsets() local h = self.hit or { 0, 0, 0, 0 } return h[1], h[2], h[3], h[4] end
    function Obj:SetMaxLines() end
    function Obj:GetTextColor() local c = self.textColor or { 1, 1, 1, 1 } return c[1], c[2], c[3], c[4] end

    OBJECTIVE_TRACKER_COLOR = {
        Normal = { r = 0.8, g = 0.8, b = 0.8 }, Complete = { r = 0.6, g = 0.6, b = 0.6 },
        Failed = { r = 0.8, g = 0.2, b = 0.2 }, Header = { r = 1, g = 0.82, b = 0 },
    }
    OBJECTIVE_DASH_STYLE_SHOW = 1
    POIButtonUtil = { Style = { QuestComplete = "complete", QuestInProgress = "progress", QuestDisabled = "disabled",
        Quest = "available" } }

    -- the quest log the tracker reads
    QUESTS = {
        { id = 11, title = "The Long Road, ch. 2", style = "progress", module = "Campaign", objectives = {
            { "Speak with Elder Rise", true }, { "Follow the river path", false } } },
        { id = 21, title = "Rite of Strength", style = "progress", module = "Quest", followed = true, objectives = {
            { "Palemane Poacher slain 4/8", false }, { "Poacher Pouch 1/3", false } } },
        { id = 22, title = "Water Pouch Bounty", style = "progress", module = "Quest", objectives = {
            { "Water Pouch collected 6/12", false } } },
        { id = 23, title = "Swoop Hunting", style = "complete", module = "Quest", ready = true, objectives = {
            { "Turn in: Harken Windtotem", false } } },
        { id = 24, title = "A Fallen Caravan", style = "progress", module = "Quest", failed = true, objectives = {} },
    }
    local function questById(id) for _, q in ipairs(QUESTS) do if q.id == id then return q end end end
    C_QuestLog = {
        GetNumQuestLogEntries = function() return #QUESTS + 2, #QUESTS end,
        GetMaxNumQuestsCanAccept = function() return 40 end,
        GetInfo = function(i)
            if i == 1 then return { isHeader = true, title = "Mulgore" } end
            local q = QUESTS[i - 1]
            if i > #QUESTS + 1 then return { isHeader = true, title = "Done" } end
            return { isHeader = false, questID = q.id, title = q.title }
        end,
        IsComplete = function(id) local q = questById(id) return q and q.ready == true or false end,
        IsFailed = function(id) local q = questById(id) return q and q.failed == true or false end,
    }

    -- the container, as Blizzard_ObjectiveTrackerContainer builds it
    local FULL_H = 330
    local frame = blz("Frame", "ObjectiveTrackerFrame", UIParent, 260, FULL_H, "TOPRIGHT", -80, -250)
    frame.topModulePadding, frame.moduleSpacing, frame.bottomModulePadding = 38, 10, 10
    frame.NineSlice = blz("Frame", nil, frame, 0, 0)
    frame.NineSlice.points = {
        { point = "TOPLEFT", rel = frame, relPoint = "TOPLEFT", x = -30, y = 0 },
        { point = "BOTTOMRIGHT", rel = frame, relPoint = "BOTTOMRIGHT", x = 5, y = 0 },
    }
    tex(frame.NineSlice, nil, "BACKGROUND")
    local header = blz("Frame", nil, frame, 260, 32, "TOPLEFT", 0, 0)
    frame.Header = header
    header.Background = tex(header, nil, "BACKGROUND")
    header.Text = fstring(header, nil, "Objectives", 14, { 1, 0.82, 0, 1 })
    header.Text.points[1] = { point = "LEFT", rel = header, relPoint = "LEFT", x = 7, y = 0 }
    local mb = blz("Button", nil, header, 18, 19, "RIGHT", -4, 0)
    mb.NormalTexture = tex(mb, nil, "ARTWORK")
    mb.pushedTex = tex(mb, nil, "ARTWORK")
    mb.highlightTex = tex(mb, nil, "HIGHLIGHT")
    mb.scripts.OnClick = function() end
    mb.scripts.OnEnter = function() end
    mb.scripts.OnLeave = function() end
    header.MinimizeButton = mb
    frame.modules = {}
    frame.Update = function(self) end
    frame.IsCollapsed = function(self) return self.Header.collapsed == true end
    frame.SetBackgroundAlpha = function(self, a) self.NineSlice:SetAlpha(a) end
    header.SetCollapsed = function(self, collapsed)
        self.collapsed = collapsed
        frame.h = collapsed and 32 or FULL_H
        for _, m in ipairs(frame.modules) do m.shown = not collapsed end
        frame:Update()
    end

    -- one module: header (25), then its blocks
    local function mkModule(name, title, y, qs)
        local m = blz("Frame", name, frame, 250, 0, "TOPLEFT", 0, -y)
        m.headerHeight, m.fromHeaderOffsetY, m.fromBlockOffsetY, m.blockOffsetX, m.lineSpacing = 25, -10, -10, 20, 4
        local h = blz("Frame", nil, m, 250, 25, "TOPLEFT", 0, 0)
        m.Header = h
        h.Background = tex(h, nil, "BACKGROUND")
        h.Background.SetAtlas = function(self, a) self.atlas = a end
        h.Text = fstring(h, nil, title, 14, { 1, 0.82, 0, 1 })
        h.Text.points[1] = { point = "LEFT", rel = h, relPoint = "LEFT", x = 7, y = 0 }
        h.MinimizeButton = blz("Button", nil, h, 16, 16, "RIGHT", -4, 0)
        h.MinimizeButton.NormalTexture = tex(h.MinimizeButton, nil, "ARTWORK")
        m.usedBlocks = { QuestTemplate = {} }
        m.EndLayout = function(self) end
        m.GetContentsHeight = function(self) return self.h end
        local by = 25 + 10
        for _, q in ipairs(qs) do
            local b = blz("Frame", nil, m, 230, 0, "TOPLEFT", 20, -by)
            b.isHighlighted = false
            b.HeaderText = fstring(b, nil, q.title, 12, { 1, 0.82, 0, 1 })
            b.HeaderText.w, b.HeaderText.h = 230, 14
            b.HeaderButton = blz("Button", nil, b, 230, 14, "TOPLEFT", 0, 0)
            b.HeaderButton.points = {
                { point = "TOPLEFT", rel = b.HeaderText, relPoint = "TOPLEFT", x = 0, y = 0 },
                { point = "BOTTOMRIGHT", rel = b.HeaderText, relPoint = "BOTTOMRIGHT", x = 0, y = 0 },
            }
            b.HeaderButton.scripts.OnEnter = function() b.isHighlighted = true end
            b.HeaderButton.scripts.OnLeave = function() b.isHighlighted = false end
            b.HeaderButton.scripts.OnClick = function() end
            b.UpdateHighlight = function(self) end
            local poi = blz("Button", nil, b, 20, 20)
            poi.points = { { point = "TOPRIGHT", rel = b.HeaderText, relPoint = "TOPLEFT", x = -7, y = 5 } }
            poi.NormalTexture = tex(poi, nil, "ARTWORK")
            poi.Display = blz("Frame", nil, poi, 20, 20, "CENTER", 0, 0)
            poi.Display.Icon = tex(poi.Display, nil, "ARTWORK")
            poi.style, poi.selected, poi.questID = q.style, q.followed == true, q.id
            poi.GetStyle = function(self) return self.style end
            poi.IsSelected = function(self) return self.selected end
            poi.GetQuestID = function(self) return self.questID end
            poi.SetSelected = function(self, v) self.selected = v end
            poi.SetStyle = function(self, s) self.style = s end
            poi.scripts.OnClick = function() end
            poi.scripts.OnEnter = function() end
            b.poiButton = poi
            b.usedLines = {}
            local last, ly = b.HeaderText, 14
            local function addLine(key, text, colorStyle)
                local line = blz("Frame", nil, b, 0, 12)
                line.points = {
                    { point = "TOPLEFT", rel = last, relPoint = "BOTTOMLEFT", x = 0, y = -4 },
                    { point = "RIGHT", rel = b, relPoint = "RIGHT", x = 0, y = 0 },
                }
                line.Dash = fstring(line, nil, "-", 11, { 0.8, 0.8, 0.8, 1 })
                line.Dash.points[1] = { point = "TOPLEFT", rel = line, relPoint = "TOPLEFT", x = 0, y = 1 }
                line.Text = fstring(line, nil, text, 11, { 0.8, 0.8, 0.8, 1 })
                line.Text.points = {
                    { point = "TOP", rel = line, relPoint = "TOP", x = 0, y = 0 },
                    { point = "LEFT", rel = line.Dash, relPoint = "RIGHT", x = 0, y = 0 },
                    { point = "RIGHT", rel = line, relPoint = "RIGHT", x = 0, y = 0 },
                }
                line.Text.colorStyle = colorStyle
                line.objectiveKey = key
                b.usedLines[key] = line
                last = line
                ly = ly + 16
            end
            for i, o in ipairs(q.objectives) do
                addLine(i, o[1], o[2] and OBJECTIVE_TRACKER_COLOR.Complete or OBJECTIVE_TRACKER_COLOR.Normal)
            end
            if q.failed then addLine("Failed", "Failed", OBJECTIVE_TRACKER_COLOR.Failed) end
            b.lastRegion = last ~= b.HeaderText and last or nil
            b.h = ly
            b.height = ly
            m.usedBlocks.QuestTemplate[q.id] = b
            by = by + ly + 10
        end
        m.h = by - 10
        frame.modules[#frame.modules + 1] = m
        return m, by
    end
    local campaign, y1 = mkModule("CampaignQuestObjectiveTracker", "Campaign", 38, { QUESTS[1] })
    local quests = mkModule("QuestObjectiveTracker", "Quests", 38 + y1 - 10 + 10, { QUESTS[2], QUESTS[3], QUESTS[4], QUESTS[5] })

    -- every Blizzard widget the skin is not allowed to script
    function Step(seconds)
        local dt = 1 / 60
        for _ = 1, math.floor(seconds / dt + 0.5) do
            NOW = NOW + dt
            for _, o in ipairs(ALL) do
                if o.scripts.OnUpdate and o.shown and not o.blizz then o.scripts.OnUpdate(o, dt) end
            end
        end
    end
    function Block(i) return QuestObjectiveTracker.usedBlocks.QuestTemplate[({ 21, 22, 23, 24 })[i]] end
    function Layout() for _, m in ipairs(ObjectiveTrackerFrame.modules) do m:EndLayout() end ObjectiveTrackerFrame:Update() end
end
"""

H = Harness({"Tracker": "Modules/Tracker/Tracker.lua"}, BLIZZARD)


def case(name, body):
    H.case(name, body + "\n    Clean()")


PRE = r"""
    local S = FS.Tracker.state
    local C = S.chrome
    local T = ObjectiveTrackerFrame
    local function ui(o) local l, t, r, b = o:Rect() return l, t, r, b end
    local function visible(o) return o:IsVisible() and (o.alpha or 1) > 0 end
    local function snapshot()
        local s = { T.topModulePadding, T.moduleSpacing, T.bottomModulePadding }
        for _, m in ipairs(T.modules) do s[#s + 1] = m.headerHeight; s[#s + 1] = m.fromHeaderOffsetY; s[#s + 1] = m.lineSpacing end
        return table.concat(s, ',')
    end
"""

case("expanded: the panel is the whole container strip and the band sits in the 32 px header strip", PRE + r"""
    local P = FS.Tracker.Panel()
    assert(P and P == C.backdrop, 'no panel')
    local pl, pt, pr, pb = ui(P)
    local nl, nt, nr, nb = ui(T.NineSlice)
    assert(Near(pt, nt) and Near(pb, nb) and Near(pr, nr), 'panel is not the container strip ' .. pt .. ' ' .. nt)
    assert(C.label:GetText() == 'stuwave://objectives', 'band reads ' .. tostring(C.label:GetText()))
    local bl, bt, br, bb = ui(C.band)
    assert(Near(bb - bt, 32), 'band height ' .. (bb - bt))
    local mt = select(2, ui(CampaignQuestObjectiveTracker.Header))
    assert(bb <= mt, 'band overlaps the first module header: ' .. bb .. ' vs ' .. mt)
    assert(Near(bt, pt + 3), 'band top ' .. bt .. ' panel top ' .. pt)
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\n'))
""")

case("expanded: Blizzard's NineSlice stays at alpha 0 whatever the container writes", PRE + r"""
    assert(T.NineSlice.alpha == 0, 'not held')
    T:SetBackgroundAlpha(1)
    assert(T.NineSlice.alpha == 0, 'container write restored the stock art')
    T.Header:SetCollapsed(true)
    T:SetBackgroundAlpha(0.8)
    assert(T.NineSlice.alpha == 0, 'restored while collapsed')
""")

case("collapsed: the backdrop is exactly the 24 px bar on the right edge and reads quests (n/40)", PRE + r"""
    T.Header:SetCollapsed(true)
    local P = FS.Tracker.Panel()
    local pl, pt, pr, pb = ui(P)
    local nl, nt, nr = ui(T.NineSlice)
    assert(Near(pb - pt, 24), 'bar height ' .. (pb - pt))
    assert(Near(pr, nr), 'bar right edge')
    assert(Near(pt, nt), 'bar top')
    assert(pr - pl < 200, 'bar width ' .. (pr - pl))
    assert(C.label:GetText() == 'quests (5/40)', 'label ' .. tostring(C.label:GetText()))
    T.Header:SetCollapsed(false)
    local _, t2, _, b2 = ui(FS.Tracker.Panel())
    assert(b2 - t2 > 100, 'expanded again but the panel is ' .. (b2 - t2))
    assert(C.label:GetText() == 'stuwave://objectives', 'band label back')
""")

case("collapsed bar: one tick per quest, amber for ready, pink for failed, an LED only while one is ready", PRE + r"""
    T.Header:SetCollapsed(true)
    local shown = {}
    for _, t in ipairs(C.ticks) do if t:IsShown() then shown[#shown + 1] = t end end
    assert(#shown == 5, 'ticks shown ' .. #shown)
    local function col(t) local c = t.color return c and c[1] .. ',' .. c[2] .. ',' .. c[3] or 'none' end
    local amber, pink, cyan = FS.Theme.COLOR_AMBER, FS.Theme.COLOR_HEALTH, FS.Theme.COLOR_POWER
    assert(col(shown[4]) == amber[1] .. ',' .. amber[2] .. ',' .. amber[3], 'ready tick ' .. col(shown[4]))
    assert(col(shown[5]) == pink[1] .. ',' .. pink[2] .. ',' .. pink[3], 'failed tick ' .. col(shown[5]))
    assert(col(shown[1]) == cyan[1] .. ',' .. cyan[2] .. ',' .. cyan[3], 'open tick ' .. col(shown[1]))
    -- evenly spaced, whole pixels, inside the bar
    local pl, _, pr = ui(FS.Tracker.Panel())
    local x1 = ui(shown[1]); local x2 = ui(shown[2])
    assert(Near((x2 - x1) * PPU, 4, 0.05), 'tick stride ' .. (x2 - x1) * PPU)
    local lastR = select(3, ui(shown[#shown]))
    assert(lastR <= pr and x1 > pl, 'ticks outside the bar')
    assert(C.led and C.led:IsShown(), 'no LED with a quest ready')
    QUESTS[4].ready = false
    FS.Tracker.Refresh()
    assert(not C.led:IsShown(), 'LED stays with nothing ready')
    QUESTS[4].ready = true
""")

case("collapsed bar: the quest count follows the log", PRE + r"""
    T.Header:SetCollapsed(true)
    table.remove(QUESTS, 2)
    Fire('QUEST_LOG_UPDATE')
    assert(C.label:GetText() == 'quests (4/40)', 'label ' .. tostring(C.label:GetText()))
""")

case("one collapse control: the plus and minus are the same two bars, the band's glyph is Blizzard's own button", PRE + r"""
    local button = T.Header.MinimizeButton
    assert(C.button == button, 'glyph is not the container button')
    local h, v = C.glyphH, C.glyphV
    assert(h and v, 'bars missing')
    local hl, ht, hr, hb = ui(h)
    assert(Near((hr - hl) * PPU, math.floor((hr - hl) * PPU + 0.5), 0.05), 'bar not on whole pixels')
    assert(not v:IsShown() or Near(select(4, ui(v)) - select(2, ui(v)), 0), 'plus drawn while expanded')
    T.Header:SetCollapsed(true)
    Step(0.5)
    local vl, vt, vr, vb = ui(v)
    assert(v:IsShown() and Near(vb - vt, hr - hl, 0.5), 'vertical bar ' .. (vb - vt) .. ' vs ' .. (hr - hl))
    local hx, hy = CenterOf(h, button); local vx, vy = CenterOf(v, button)
    assert(Near(hx, vx, 0.6) and Near(hy, vy, 0.6), 'bars not crossed on one centre')
    T.Header:SetCollapsed(false)
    Step(0.5)
    assert(not v:IsShown() or Near(select(4, ui(v)) - select(2, ui(v)), 0), 'plus kept after expanding')
    -- module headers lose their own minus
    assert(not CampaignQuestObjectiveTracker.Header.MinimizeButton:IsShown(), 'module minus shown')
    assert(not QuestObjectiveTracker.Header.MinimizeButton:IsShown(), 'module minus shown')
    CampaignQuestObjectiveTracker.Header.MinimizeButton:Show()
    assert(not CampaignQuestObjectiveTracker.Header.MinimizeButton:IsShown(), 'module minus came back')
""")

case("collapsed bar: a click anywhere is the button's own, and hover turns the edge pink", PRE + r"""
    local button = T.Header.MinimizeButton
    local wide = select(2, button:GetHitRectInsets())
    T.Header:SetCollapsed(true)
    local _, r2 = button:GetHitRectInsets()
    assert(r2 < wide, 'hit rect not widened over the bar: ' .. tostring(r2))
    local pink, cyan = FS.Theme.COLOR_HEALTH, FS.Theme.COLOR_POWER
    local function edge() local v = C.border.vertex return v[1] .. ',' .. v[2] end
    assert(edge() == cyan[1] .. ',' .. cyan[2], 'edge not cyan at rest ' .. edge())
    button:RunScript('OnEnter')
    assert(edge() == pink[1] .. ',' .. pink[2], 'edge not pink on hover ' .. edge())
    button:RunScript('OnLeave')
    assert(edge() == cyan[1] .. ',' .. cyan[2], 'edge not back to cyan ' .. edge())
    T.Header:SetCollapsed(false)
    local _, r3 = button:GetHitRectInsets()
    assert(r3 == wide, 'hit rect not restored')
""")

case("collapsed bar draws nothing while the console's quests key is on screen", PRE + r"""
    T.Header:SetCollapsed(true)
    assert(C.backdrop:IsShown(), 'bar hidden without the key')
    FSConsoleKeyquests = CreateFrame('Frame')
    FS.Tracker.Refresh()
    assert(not C.backdrop:IsShown(), 'bar shown with the key')
    FSConsoleKeyquests = nil
    FS.Tracker.Refresh()
    assert(C.backdrop:IsShown(), 'bar not back')
""")

case("expanding plays a shutter on our own overlay, ends, and leaves no animation behind", PRE + r"""
    T.Header:SetCollapsed(true)
    T.Header:SetCollapsed(false)
    assert(C.shutter and C.shutter:IsShown(), 'no shutter')
    assert(FS.ControlKit.IsAnimating(C.shutter, 'wipe'), 'no wipe running')
    Step(0.1)
    assert(C.shutter:IsShown(), 'shutter gone too early')
    Step(0.6)
    assert(not C.shutter:IsShown(), 'shutter stays over the tracker')
    assert(not FS.ControlKit.IsAnimating(C.shutter, 'wipe'), 'the wipe never ended')
    assert(C.shutter.alpha ~= nil, 'shutter state')
    assert(not C.shutter.mouse, 'shutter takes the mouse')
""")

case("module headers keep their text as a mono sub-head: diamond, lowercase label, rule, stock text held", PRE + r"""
    for _, name in ipairs({ 'CampaignQuestObjectiveTracker', 'QuestObjectiveTracker' }) do
        local m = _G[name]
        local sk = S.headers[m.Header]
        assert(sk, name .. ' header not skinned')
        local want = m.Header.Text:GetText():lower() .. (name == 'QuestObjectiveTracker' and ' (5/40)' or '')
        assert(sk.label:IsShown() and sk.label:GetText() == want, name .. ' label ' .. tostring(sk.label:GetText()))
        assert(m.Header.Text.alpha == 0, name .. ' stock text visible')
        m.Header.Text:SetAlpha(1)
        assert(m.Header.Text.alpha == 0, name .. ' stock text came back')
        assert(#sk.diamond == 11, name .. ' diamond rows ' .. #sk.diamond)
        local pl, _, pr = ui(C.backdrop)
        local dl = ui(sk.diamond[6])
        assert(dl >= pl, name .. ' diamond outside the panel')
        local ll = ui(sk.label)
        assert(ll > select(3, ui(sk.diamond[6])), name .. ' label overlaps the diamond')
        assert(S.rules[m.Header] and S.rules[m.Header]:IsShown(), name .. ' rule')
    end
    CampaignQuestObjectiveTracker.Header.Text:SetText('Campaign Updates')
    Layout()
    assert(S.headers[CampaignQuestObjectiveTracker.Header].label:GetText() == 'campaign updates', 'label did not follow the text')
    QuestObjectiveTracker.Header.Text:SetText('Quests')
    assert(S.headers[QuestObjectiveTracker.Header].label:GetText() == 'quests (5/40)', 'the quest sub-head lost its count: ' .. tostring(S.headers[QuestObjectiveTracker.Header].label:GetText()))
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\n'))
""")

case("quest rows: the spine runs behind the marker, a tick off it per objective, anchored to the stock rows", PRE + r"""
    local b = Block(1) -- Rite of Strength, followed, two open objectives
    local r = S.blocks[b]
    assert(r, 'block not skinned')
    assert(r.spine:IsShown(), 'no spine')
    local hl, ht = ui(b.HeaderText)
    local sl, st, sr, sb = ui(r.spine)
    assert(Near((sr - sl) * PPU, 2, 0.05), 'spine width ' .. (sr - sl) * PPU)
    local poi = b.poiButton
    local pcx = (select(1, ui(poi)) + select(3, ui(poi))) / 2
    assert(Near((sl + sr) / 2, pcx, 0.6), 'spine not under the marker centre: ' .. (sl + sr) / 2 .. ' vs ' .. pcx)
    local line2 = b.usedLines[2]
    local _, _, _, lb = ui(line2)
    assert(Near(sb, lb, 0.6), 'spine ends ' .. sb .. ' last row ends ' .. lb)
    assert(st <= ht, 'no stub above the marker')
    for key, line in pairs(b.usedLines) do
        local tick = S.lines[line]
        assert(tick and tick:IsShown(), 'no tick on objective ' .. tostring(key))
        local tl, tt, tr, tb = ui(tick)
        assert(Near((tb - tt) * PPU, 2, 0.05), 'tick thickness')
        assert(tl >= sl - 0.01 and tr <= select(1, ui(line)) + 0.01, 'tick runs past the spine or into the text')
        assert(line.Dash.alpha == 0, 'stock dash drawn next to our tick')
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\n'))
""")

case("quest rows: the spine charges to the last finished objective, in cyan; open ticks are dim", PRE + r"""
    local b = CampaignQuestObjectiveTracker.usedBlocks.QuestTemplate[11]
    local r = S.blocks[b]
    assert(r.fill:IsShown(), 'no charge')
    local line1, line2 = b.usedLines[1], b.usedLines[2]
    local _, ft, _, fb = ui(r.fill)
    local _, l1t = ui(line1)
    assert(fb > l1t and fb <= select(4, ui(line1)), 'charge ends at ' .. fb .. ' not on objective 1')
    local c = r.fill.color
    assert(c[1] == FS.Theme.COLOR_POWER[1] and c[3] == FS.Theme.COLOR_POWER[3], 'charge not cyan')
    local done, open = S.lines[line1].color, S.lines[line2].color
    assert(done[4] > open[4], 'finished tick not brighter than open')
    local none = S.blocks[Block(2)]
    assert(not none.fill:IsShown(), 'charge with nothing finished')
""")

case("quest rows: a ready quest is amber top to bottom, a failed one pink with the X marker", PRE + r"""
    local ready, failed = S.blocks[Block(3)], S.blocks[Block(4)]
    local amber, pink = FS.Theme.COLOR_AMBER, FS.Theme.COLOR_HEALTH
    assert(ready.fill:IsShown() and ready.fill.color[1] == amber[1] and ready.fill.color[2] == amber[2], 'ready charge not amber')
    local _, _, _, sb = ui(ready.spine); local _, _, _, fb = ui(ready.fill)
    assert(Near(sb, fb, 0.6), 'ready charge does not run the whole spine')
    assert(S.lines[Block(3).usedLines[1]].color[1] == amber[1], 'ready tick not amber')
    assert(not failed.fill:IsShown(), 'charge on a failed quest')
    assert(failed.spine.color[1] == pink[1] and failed.spine.color[2] == pink[2], 'failed spine not pink')
    local m = S.markers[Block(4).poiButton]
    assert(m and m.kind == 'fail', 'failed marker kind ' .. tostring(m and m.kind))
    assert(#m.cells == 9 and m.cells[1]:IsShown(), 'X glyph cells ' .. #m.cells)
""")

case("quest rows: hover washes cyan, pressed deeper, the followed quest pink with a sweeping scanline", PRE + r"""
    local plain, followed = Block(2), Block(1)
    local rp, rf = S.blocks[plain], S.blocks[followed]
    assert(not rp.wash:IsShown(), 'wash at rest')
    plain.HeaderButton:RunScript('OnEnter')
    assert(rp.wash:IsShown() and rp.wash.color[3] == FS.Theme.COLOR_POWER[3], 'no cyan hover wash')
    local hoverA = rp.wash.color[4]
    plain.HeaderButton:RunScript('OnMouseDown')
    assert(rp.wash.color[4] > hoverA, 'pressed not deeper')
    plain.HeaderButton:RunScript('OnMouseUp'); plain.HeaderButton:RunScript('OnLeave')
    assert(not rp.wash:IsShown(), 'wash stays after leaving')
    local pink = FS.Theme.COLOR_HEALTH
    assert(rf.wash:IsShown() and rf.wash.color[1] == pink[1] and rf.wash.color[2] == pink[2], 'followed wash not pink')
    assert(rf.scan and rf.scan:IsShown(), 'no scanline on the followed quest')
    local _, t0 = ui(rf.scan)
    Step(1.0)
    local _, t1 = ui(rf.scan)
    assert(math.abs(t1 - t0) > 1, 'scanline does not move')
    -- the wash spans the panel, edge to edge, over the stock row
    local wl, _, wr = ui(rf.wash)
    local pl, _, pr = ui(C.backdrop)
    assert(wl >= pl and wr <= pr + 0.01 and (wr - wl) > (pr - pl) - 12, 'wash not across the panel: ' .. wl .. ' ' .. wr .. ' vs ' .. pl .. ' ' .. pr)
    followed.poiButton:SetSelected(false)
    assert(not rf.wash:IsShown(), 'followed wash stays after unfollowing')
    Step(0.05)
    assert(not rf.scan:IsShown(), 'scanline stays after unfollowing')
""")

case("no Blizzard layout field is written, no script or attribute is put on a stock widget, nothing is queued in combat", PRE + r"""
    local before = snapshot()
    T.Header:SetCollapsed(true); T.Header:SetCollapsed(false); Step(1)
    Layout()
    assert(snapshot() == before, 'a layout field changed: ' .. before .. ' -> ' .. snapshot())
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\n'))
    -- (the engine throws on SetScript / SetAttribute against a Blizzard widget: reaching here proves neither was called)
""")

case("in combat nothing is built, and the chrome appears when combat ends", r"""
    Reset()
    __combat = true
    local FS2 = Load({ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'Tracker' })
    assert(FS2.Tracker.Panel() == nil, 'chrome built in combat')
    assert(not ObjectiveTrackerFrame.fsTrackerChromeBuilt, 'container marked built in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED')
    assert(FS2.Tracker.Panel() ~= nil, 'chrome not built after combat')
""")

SCENES = {
    "expanded": "return DumpOps({ ObjectiveTrackerFrame, FS.Tracker.Panel() })",
    "collapsed": "ObjectiveTrackerFrame.Header:SetCollapsed(true); Step(0.5); return DumpOps({ ObjectiveTrackerFrame, FS.Tracker.Panel() })",
    "collapsed-hover": ("ObjectiveTrackerFrame.Header:SetCollapsed(true); Step(0.5); ObjectiveTrackerFrame.Header.MinimizeButton:RunScript('OnEnter'); "
                        "return DumpOps({ ObjectiveTrackerFrame, FS.Tracker.Panel() })"),
    "hover": ("local b = Block(2); b.HeaderButton:RunScript('OnEnter'); return DumpOps({ ObjectiveTrackerFrame, FS.Tracker.Panel() })"),
}

if __name__ == "__main__":
    raise SystemExit(H.main("tracker skin", SCENES))
