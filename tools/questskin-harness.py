#!/usr/bin/env python3
"""Runs the real Modules/Skins/Quest.lua headless against mock quest, gossip and book windows (tools/charskin_support.py).

Pinned, per window: the quest reward and required item cards get a card, a slot of the shared item slot layer over the stock icon
(the stock name plate and quality border held) seated inside the card with equal padding, the picked reward lights pink and the
rest dim; gossip options and quest titles are cut cards with a glyph per kind (the stock icon held), spacers and the greeting
paragraph get no card, a recycled frame that stops being a button drops its card; the speaker band, the typed greeting (skippable
by a click, never in the way of one), the rows landing one after another and the waveform stop when the window hides; the bare
scroll rail goes with the thumb; the book page keys are cut keys with a chevron; no script or attribute is written on a Blizzard
widget, and nothing is built in combat. Run `python3 tools/questskin-harness.py [--png debug/quest]`. The mock is NOT the real
client: the stock gossip elements (a greeting frame of the text height, a 15 high spacer measured as 16, 300 x 16 buttons with a
16 x 16 icon) and the quest title pool follow the 12.1 sources, and the window chrome drawn here stands in for Panels.lua.
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import charskin_support as support  # noqa: E402
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring, atex = BLZ.blz, BLZ.tex, BLZ.fstring, nil
local build = BuildBlizzard

-------------------------------------------------------------------------------
-- What the client has and the shared mock does not
-------------------------------------------------------------------------------
__now = 100
function GetTime() return __now end
NPC = { name = "Baine Bloodhoof" }
function UnitName(unit) if unit == "npc" or unit == "questnpc" then return NPC.name end end
function UnitExists(unit) return NPC.name ~= nil end
Enum = { GossipOptionStatus = { Available = 0, Unavailable = 1, Locked = 2, AlreadyComplete = 3 } }
-- file ids the mock client resolves; the numbers are the mock's own
FILEIDS = {
    [7000001] = "Interface\\GossipFrame\\GossipGossipIcon", [7000002] = "Interface\\GossipFrame\\VendorGossipIcon",
    [7000003] = "Interface\\GossipFrame\\TrainerGossipIcon", [7000004] = "Interface\\GossipFrame\\BinderGossipIcon",
    [7000005] = "Interface\\GossipFrame\\TaxiGossipIcon", [7000006] = "Interface\\GossipFrame\\PetitionGossipIcon",
}
C_Texture = { GetFilenameFromFileDataID = function(id) return FILEIDS[id] end }

function Obj:GetPoint(i)
    local p = self.points[i or 1]
    if not p then return nil end
    return p.point, p.rel, p.relPoint, p.x, p.y
end
function Obj:GetSize() return self:GetWidth(), self:GetHeight() end
function Obj:GetTop() local _, t = self:Rect(); return -t end
function Obj:IsMouseOver() return false end
function Obj:IsVisible()
    local o = self
    while o do
        if o.shown == false then return false end
        o = o.parent
    end
    return true
end
function Obj:SetTexture(p)
    if type(p) == "number" then self.fileID, self.path = p, "Interface\\stock\\fileid" else self.fileID, self.path = nil, p end
    self.color, self.atlas = nil, nil
end
function Obj:GetTexture() return self.fileID or self.path end
function Obj:SetAtlas(a) self.atlas, self.path, self.fileID, self.color = a, nil, nil, nil end
function Obj:GetAtlas() return self.atlas end
function Obj:SetTexCoord(a, b, c, d, e, f, g, h)
    if e then self.tc = { a, e, b, d } else self.tc = { a, b, c, d } end
end
function Obj:GetVertexColor() local v = self.vertex or { 1, 1, 1, 1 }; return v[1], v[2], v[3], v[4] end

-- text layout: a word wrap at the object's width, the way the client breaks a paragraph (0.5615 of the size per character)
function Obj:WrappedLines()
    local text = tostring(self.text or ""):gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")
    local cw = (self.size or 12) * 0.5615
    local wrapW = (self.w or 0) > 0 and self:GetWidth() or 0
    local maxChars = math.max(1, math.floor((wrapW > 0 and wrapW or 1e6) / cw))
    local lines, cur, pos = {}, nil, 1
    while true do
        local s, e = text:find("%S+", pos)
        if not s then break end
        local word = text:sub(s, e)
        if cur and (e - cur.first + 1) <= maxChars then
            cur.last, cur.text = e, text:sub(cur.first, e)
        else
            cur = { first = s, last = e, text = word }
            lines[#lines + 1] = cur
        end
        pos = e + 1
    end
    if #lines == 0 then lines[1] = { first = 1, last = 0, text = "" } end
    return lines, cw
end
function Obj:GetNumLines() return #self:WrappedLines() end
function Obj:GetLineHeight() return (self.size or 12) * 1.2 end
function Obj:SetAlphaGradient(start, length) self.gradient = { start, length }; return true end
function Obj:ClearAlphaGradient() self.gradient = nil end
function Obj:CalculateScreenAreaFromCharacterSpan(l, r)
    local lines, cw = self:WrappedLines()
    local lh, out = self:GetLineHeight(), {}
    for i, ln in ipairs(lines) do
        local a, b = math.max(l, ln.first), math.min(r, ln.last)
        if a <= b then out[#out + 1] = { left = (a - ln.first) * cw, bottom = (#lines - i) * lh, width = (b - a + 1) * cw, height = lh } end
    end
    if #out == 0 then return nil end
    return out
end
-- a paragraph whose height follows its text, the way a FontString with no height does
function AutoFit(fs)
    fs.autoH = true
    local setText, setFont = fs.SetText, fs.SetFont
    local function refit() fs.h = #fs:WrappedLines() * fs:GetLineHeight() end
    fs.SetText = function(self, t) setText(self, t); refit() end
    fs.SetFont = function(self, ...) local r = setFont(self, ...); refit(); return r end
    refit()
end

-- one animation frame for every visible OnUpdate that is not a Blizzard frame's, then the timers
function Advance(sec, step)
    step = step or (1 / 30)
    local n = math.floor(sec / step + 0.5)
    assert(n <= 1200, "Advance too long")
    for _ = 1, n do
        __now = __now + step
        local count = #ALL
        for i = 1, count do
            local o = ALL[i]
            if o.scripts.OnUpdate and not o.blizz and o:IsVisible() then o.scripts.OnUpdate(o, step) end
        end
        FlushTimers()
    end
end

local function money(parent, name, x, y)
    local m = blz("Frame", name, parent, 100, 14, "TOPLEFT", x, y)
    m.staticMoney = true
    for _, k in ipairs({ "Gold", "Silver", "Copper" }) do fstring(m, name .. k .. "ButtonText", "12", 12, { 1, 1, 1, 1 }) end
    return m
end

-- LargeItemButtonTemplate (Blizzard_ItemButton): 147 x 41, Icon 39 x 39 at the top left, NameFrame (128 x 64, 10 under the icon's
-- right edge) and Name (90 x 36 on it), Count at the icon's bottom right, the quality border and overlays
local function largeItem(parent, name, x, y, id, kind)
    local b = blz("Button", name, parent, 147, 41, "TOPLEFT", x, y)
    b.id, b.type = id, kind
    b.Icon = tex(b, name .. "IconTexture", "BACKGROUND")
    b.Icon.w, b.Icon.h = 39, 39
    b.Icon.points[1] = { point = "TOPLEFT", rel = b, relPoint = "TOPLEFT", x = 0, y = 0 }
    b.NameFrame = tex(b, name .. "NameFrame", "BACKGROUND")
    b.NameFrame.w, b.NameFrame.h = 128, 64
    b.NameFrame.stock = { 0.35, 0.28, 0.1 }
    b.NameFrame.points[1] = { point = "LEFT", rel = b.Icon, relPoint = "RIGHT", x = -10, y = 0 }
    b.Name = fstring(b, name .. "Name", "Item", 12, { 1, 1, 1, 1 })
    b.Name.w, b.Name.h = 90, 36
    b.Name.points[1] = { point = "LEFT", rel = b.NameFrame, relPoint = "LEFT", x = 15, y = 0 }
    b.IconBorder = tex(b, nil, "OVERLAY")
    b.IconOverlay = tex(b, nil, "OVERLAY")
    b.IconOverlay2 = tex(b, nil, "OVERLAY")
    b.Count = fstring(b, name .. "Count", "", 12, { 1, 1, 1, 1 })
    b.Count.points[1] = { point = "BOTTOMRIGHT", rel = b.Icon, relPoint = "BOTTOMRIGHT", x = -1, y = 1 }
    b.Count.justify = "RIGHT"
    b.highlightTex = tex(b, nil, "HIGHLIGHT")
    b.scripts.OnClick = QuestInfoItem_OnClick
    b.scripts.OnEnter = function() end
    b.scripts.OnLeave = function() end
    return b
end

local function pager(parent, name, dir)
    local b = blz("Button", name, parent, 32, 32, "CENTER", dir == "<" and 25 or 310, 96)
    b.points[1].relPoint = "BOTTOMLEFT"
    local label = fstring(b, nil, dir == "<" and "PREV" or "NEXT", 12, { 1, 0.82, 0, 1 })
    label.points[1] = { point = dir == "<" and "LEFT" or "RIGHT", rel = b, relPoint = dir == "<" and "RIGHT" or "LEFT", x = 0, y = 0 }
    b.NormalTexture = tex(b, nil, "ARTWORK")
    b.GetNormalTexture = function(self) return self.NormalTexture end
    b.pushedTex, b.highlightTex = tex(b, nil, "ARTWORK"), tex(b, nil, "HIGHLIGHT")
    b.scripts.OnClick = function() end
    return b
end

function SetItemButtonQuality(button, quality)
    if button.SetItemButtonQuality then button:SetItemButtonQuality(quality) else button.q = quality end
end

-- a stand-in for the Panels.lua chrome (fill, header band, rule, title, Goodbye) so a render reads as a window
local function flat(parent, r, g, b, a, sub)
    local t = tex(parent, nil, "BACKGROUND")
    t.path, t.color, t.sub = nil, { r, g, b, a }, sub or 0
    return t
end
local function chrome(win, title, goodbyeParent)
    local fill = flat(win, 0.043, 0.024, 0.094, 1, -8)
    fill.points = { { point = "TOPLEFT", rel = win, relPoint = "TOPLEFT", x = 0, y = 0 }, { point = "BOTTOMRIGHT", rel = win, relPoint = "BOTTOMRIGHT", x = 0, y = 0 } }
    local band = flat(win, 0.102, 0.051, 0.173, 1, -7)
    band.points = { { point = "TOPLEFT", rel = win, relPoint = "TOPLEFT", x = 3, y = -3 }, { point = "TOPRIGHT", rel = win, relPoint = "TOPRIGHT", x = -3, y = -3 } }
    band.h = 18
    local rule = flat(win, 0.36, 0.18, 0.72, 1, -6)
    rule.points = { { point = "TOPLEFT", rel = win, relPoint = "TOPLEFT", x = 3, y = -21 }, { point = "TOPRIGHT", rel = win, relPoint = "TOPRIGHT", x = -3, y = -21 } }
    rule.h = 1 / PPU
    local t = fstring(win, nil, title, 11, { 0.13, 0.88, 1, 1 })
    t.points[1] = { point = "TOPLEFT", rel = win, relPoint = "TOPLEFT", x = 10, y = -5 }
    t.w, t.h = 200, 14
    t.layer = "ARTWORK"
    local g = blz("Button", nil, goodbyeParent, 78, 22, "BOTTOMRIGHT", -6, 4)
    g.points[1].rel = win
    local gf = flat(g, 0.06, 0.03, 0.12, 1, 0)
    gf.points = { { point = "TOPLEFT", rel = g, relPoint = "TOPLEFT", x = 0, y = 0 }, { point = "BOTTOMRIGHT", rel = g, relPoint = "BOTTOMRIGHT", x = 0, y = 0 } }
    local gl = fstring(g, nil, "GOODBYE", 11, { 0.13, 0.88, 1, 1 })
    gl.w, gl.h = 70, 14
    gl.points[1] = { point = "CENTER", rel = g, relPoint = "CENTER", x = 0, y = 0 }
    gl.justify = "CENTER"
    g.scripts.OnClick = function() end
    return g
end

-- MinimalScrollBar: a Track holding a Thumb that is hidden while there is nothing to scroll (ScrollBarMixin:Update)
local function scrollBar(parent, anchor, dx, dy, h)
    local bar = blz("Frame", nil, parent, 8, h, "TOPLEFT", 0, 0)
    bar.points[1] = { point = "TOPLEFT", rel = anchor, relPoint = "TOPRIGHT", x = dx, y = dy }
    bar.Track = blz("Frame", nil, bar, 8, h, "TOPLEFT", 0, 0)
    bar.Track.Thumb = blz("Button", nil, bar.Track, 8, 40, "TOPLEFT", 0, 0)
    bar.Track.Thumb.shown = false
    bar.scrollable = false
    bar.Update = function(self) self.Track.Thumb:SetShown(self.scrollable) end
    return bar
end

-- the pooled title buttons of the quest greeting panel (QuestTitleButtonTemplate, parented to the scroll child)
local function titleButton(parent)
    local b = blz("Button", nil, parent, 300, 16, "TOPLEFT", 0, 0)
    b.Icon = tex(b, nil, "BACKGROUND")
    b.Icon.w, b.Icon.h = 16, 16
    b.Icon.stock = { 0.95, 0.78, 0.2 }
    b.Icon.points[1] = { point = "LEFT", rel = b, relPoint = "LEFT", x = 4, y = 0 }
    b.highlightTex = tex(b, nil, "HIGHLIGHT")
    b.highlightTex.stock = { 1, 0.9, 0.5 }
    b.fs = fstring(b, nil, "", 13, { 0.2, 0.1, 0.05, 1 })
    b.fs.w, b.fs.h = 275, 16
    b.fs.points[1] = { point = "TOPLEFT", rel = b, relPoint = "TOPLEFT", x = 20, y = 0 }
    b.scripts.OnClick = function(self) CLICKED = self end
    b.scripts.OnEnter = function() end
    b.scripts.OnLeave = function() end
    return b
end

-- the quest list the greeting panel shows (GetNumActiveQuests and friends)
QUESTS = {
    greeting = "Ah, Stu. There is much to do around the village.",
    active = { { title = "Hunting Pack", complete = true }, { title = "Red Cloud Mesa Survey", complete = false } },
    available = { { title = "Taming the Beast" } },
}

-- the stock gossip elements (GossipFrameShared / GossipFrame.xml): a greeting frame as tall as its text with the text 10 down and
-- 10 in, a spacer frame the view measures as 16, 300 x 16 option and quest buttons with a 16 x 16 icon at 3, 1. Frames are pooled by
-- template and reused; the view stretches each to the box's width and stacks them with no gap
GOSSIP_DATA = nil
CLICKED = nil
local function newGossipFrame(box, kind)
    local target = box.ScrollTarget
    if kind == "title" then
        local f = blz("Frame", nil, target, 270, 10, "TOPLEFT", 0, 0)
        f.GreetingText = fstring(f, nil, "", 13, { 0.2, 0.1, 0.05, 1 })
        f.GreetingText.w = 270
        f.GreetingText.points[1] = { point = "TOPLEFT", rel = f, relPoint = "TOPLEFT", x = 10, y = -10 }
        AutoFit(f.GreetingText)
        return f
    elseif kind == "spacer" then
        return blz("Frame", nil, target, 5, 15, "TOPLEFT", 0, 0)
    end
    local b = blz("Button", nil, target, 300, 16, "TOPLEFT", 0, 0)
    b.Icon = tex(b, nil, "BACKGROUND")
    b.Icon.w, b.Icon.h = 16, 16
    b.Icon.stock = { 0.95, 0.78, 0.2 }
    b.Icon.points[1] = { point = "TOPLEFT", rel = b, relPoint = "TOPLEFT", x = 3, y = 1 }
    b.highlightTex = tex(b, nil, "HIGHLIGHT")
    b.highlightTex.stock = { 1, 0.9, 0.5 }
    b.fs = fstring(b, nil, "", 13, { 0.2, 0.1, 0.05, 1 })
    b.fs.w, b.fs.h = 275, 16
    b.fs.points[1] = { point = "LEFT", rel = b, relPoint = "LEFT", x = 20, y = 0 }
    b.scripts.OnClick = function(self) CLICKED = self end
    b.scripts.OnEnter = function() end
    b.scripts.OnLeave = function() end
    return b
end

local function acquire(box, kind)
    local pool = box.pools[kind]
    if not pool then pool = {}; box.pools[kind] = pool end
    for _, f in ipairs(pool) do
        if not f.inUse then f.inUse = true; return f end
    end
    local f = newGossipFrame(box, kind)
    f.inUse = true
    pool[#pool + 1] = f
    return f
end

function RebuildGossip()
    local box = GossipFrame.GreetingPanel.ScrollBox
    for _, f in ipairs(box.rows) do f:Hide(); f:ClearAllPoints(); f.inUse = false end
    box.rows = {}
    local y = 0
    for _, el in ipairs(GOSSIP_DATA.list) do
        local f = acquire(box, el.t == "title" and "title" or (el.t == "spacer" and "spacer" or "button"))
        local extent = 16
        if el.t == "title" then
            f.GreetingText:SetText(GOSSIP_DATA.greeting)
            extent = f.GreetingText.h
        elseif el.t == "option" then
            f:SetID(el.orderIndex or 0)
            f:SetText(el.name)
            f.Icon:SetTexture(el.overrideIcon or el.icon)
            f.Icon:SetVertexColor(1, 1, 1, 1)
        elseif el.t == "available" or el.t == "active" then
            f:SetID(el.questID)
            f:SetText(el.title)
            if el.atlas then f.Icon:SetAtlas(el.atlas) else f.Icon:SetTexture(el.path) end
            local g = el.trivial and 0.5 or 1
            f.Icon:SetVertexColor(g, g, g, 1)
        end
        f:ClearAllPoints()
        f:SetPoint("TOPLEFT", box.ScrollTarget, "TOPLEFT", 0, -y)
        f:SetPoint("TOPRIGHT", box.ScrollTarget, "TOPRIGHT", 0, -y)
        f.h = extent
        f:Show()
        box.rows[#box.rows + 1] = f
        y = y + extent
    end
    box.ScrollTarget.h = y
    box:Update()
end

C_GossipInfo = {
    GetOptions = function()
        local t = {}
        for _, e in ipairs(GOSSIP_DATA and GOSSIP_DATA.list or {}) do
            if e.t == "option" then t[#t + 1] = { name = e.name, icon = e.icon, orderIndex = e.orderIndex, status = e.status or 0 } end
        end
        return t
    end,
    GetAvailableQuests = function()
        local t = {}
        for _, e in ipairs(GOSSIP_DATA and GOSSIP_DATA.list or {}) do
            if e.t == "available" then t[#t + 1] = { questID = e.questID, title = e.title, isTrivial = e.trivial } end
        end
        return t
    end,
    GetActiveQuests = function()
        local t = {}
        for _, e in ipairs(GOSSIP_DATA and GOSSIP_DATA.list or {}) do
            if e.t == "active" then t[#t + 1] = { questID = e.questID, title = e.title, isComplete = e.complete } end
        end
        return t
    end,
}

OFFER, ACTIVE = "Interface/GossipFrame/AvailableQuestIcon", "Interface/GossipFrame/ActiveQuestIcon"
-- a vendor, a trainer, an inn, a flight master, a paid option, a plain talk option and the three quest kinds
DEFAULT_GOSSIP = {
    greeting = "Greetings, Stu. The hunt has been poor this season and the elders grow restless. If you have a steady hand and a free afternoon, there is work to be done.",
    list = {
        { t = "title" }, { t = "spacer" },
        { t = "option", name = "I want to browse your goods.", icon = 7000002, orderIndex = 1 },
        { t = "option", name = "Train me in the ways of the Shaman.", icon = 7000003, orderIndex = 2 },
        { t = "option", name = "Make this inn my home.", icon = 7000004, orderIndex = 3 },
        { t = "option", name = "I want to fly to Thunder Bluff.", icon = 7000005, orderIndex = 4 },
        { t = "option", name = "Send me home. |TInterface\\MoneyFrame\\UI-GoldIcon:0:0:2:0|t", icon = 7000001, orderIndex = 5, status = 1 },
        { t = "option", name = "Tell me about the Grimtotem.", icon = 7000001, orderIndex = 6 },
        { t = "spacer" },
        { t = "available", questID = 11, title = "Taming the Beast", path = OFFER },
        { t = "active", questID = 12, title = "Hunting Pack", path = ACTIVE, complete = true },
        { t = "active", questID = 13, title = "Red Cloud Mesa Survey", atlas = "SideInProgressquesticon" },
        { t = "spacer" },
    },
}
-- the screenshot that showed four cards: the greeting, a spacer, one available quest, a trailing spacer (with the stock's second spacer)
SPACER_GOSSIP = {
    greeting = "Greetings, Stu. The hunt has been poor this season and the elders grow restless.",
    list = { { t = "title" }, { t = "spacer" }, { t = "spacer" },
        { t = "available", questID = 11, title = "The Battleboars", path = OFFER }, { t = "spacer" } },
}

function OpenGossip(data)
    GOSSIP_DATA = data or DEFAULT_GOSSIP
    Fire('PLAYER_ENTERING_WORLD')
    GossipFrame:Show()
    FlushTimers()
end
function OpenGreeting(quests)
    QUESTS = quests or QUESTS
    Fire('PLAYER_ENTERING_WORLD')
    QuestFrame:Show()
    QuestFrameGreetingPanel:Show()
    FlushTimers()
end
function ListRows() return GossipFrame.GreetingPanel.ScrollBox.rows end

function BuildBlizzard()
    build()
    atex = BLZ.atex
    for k in pairs(_G) do
        if type(k) == "string" and (k:find("^Quest") or k:find("^Gossip") or k:find("^ItemText") or k:find("^Greeting")
            or k:find("^CurrentQuests") or k:find("^AvailableQuests")) then _G[k] = nil end
    end
    CLICKED = nil
    QuestInfoFrame = { itemChoice = 0 }
    function QuestInfoItem_OnClick(self)
        if self.type == "choice" then
            QuestInfoItemHighlight:SetPoint("TOPLEFT", self, "TOPLEFT", -8, 7)
            QuestInfoItemHighlight:Show()
            QuestInfoFrame.itemChoice = self:GetID()
        end
    end
    function QuestInfo_Display() end
    function QuestFrameProgressItems_Update() end
    -- QuestFrame (370 wide in the client) and its four pages
    local win = blz("Frame", "QuestFrame", UIParent, 370, 496)
    win.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 100, y = -80 }
    win.shown = false
    local pages = {}
    for _, n in ipairs({ "QuestFrameDetailPanel", "QuestFrameProgressPanel", "QuestFrameRewardPanel", "QuestFrameGreetingPanel" }) do
        pages[n] = blz("Frame", n, win, 370, 496, "TOPLEFT", 0, 0)
        pages[n].shown = false
    end
    local detail, progress, reward, greeting = pages.QuestFrameDetailPanel, pages.QuestFrameProgressPanel, pages.QuestFrameRewardPanel, pages.QuestFrameGreetingPanel
    chrome(win, "stuwave://quest", win)
    for _, spec in ipairs({
        { detail, "QuestInfoTitleHeader", "Taming the Beast", 18 }, { detail, "QuestInfoDescriptionText", "The wild beasts have grown bold.", 13 },
        { detail, "QuestInfoObjectivesHeader", "Objectives", 18 }, { detail, "QuestInfoObjectivesText", "Kill Plainstrider Hens", 13 },
        { detail, "QuestInfoObjective1", "Plainstrider Hens: 0/8", 13 }, { detail, "QuestInfoObjective2", "Hen Feathers: 3/6", 13 },
        { detail, "QuestInfoRewardText", "Well hunted.", 13 },
        { progress, "QuestProgressTitleText", "Hunting Pack", 18 }, { progress, "QuestProgressText", "Show me what you have.", 13 },
        { progress, "QuestProgressRequiredItemsText", "Required items", 18 }, { progress, "QuestProgressRequiredMoneyText", "Required money:", 13 },
    }) do
        local f = fstring(spec[1], spec[2], spec[3], spec[4], { 0.2, 0.1, 0.05, 1 })
        f.w, f.h = 280, 20
    end
    for i, f in ipairs({ QuestInfoTitleHeader, QuestInfoDescriptionText, QuestInfoObjectivesHeader, QuestInfoObjectivesText, QuestInfoObjective1,
        QuestInfoObjective2, QuestInfoRewardText }) do f.points[1] = { point = "TOPLEFT", rel = detail, relPoint = "TOPLEFT", x = 20, y = -70 - (i - 1) * 24 } end
    for n, y in pairs({ QuestProgressTitleText = 66, QuestProgressText = 96, QuestProgressRequiredItemsText = 144, QuestProgressRequiredMoneyText = 304 }) do
        local f = _G[n]
        f.points[1] = { point = "TOPLEFT", rel = f.parent, relPoint = "TOPLEFT", x = 20, y = -y }
    end
    -- the rewards frame: header texts, five buttons built on demand, the money and XP lines, the pick highlight
    local rf = blz("Frame", "QuestInfoRewardsFrame", detail, 285, 220, "TOPLEFT", 20, -240)
    win.QuestInfoRewardsFrame = rf
    rf.Header = fstring(rf, nil, "Rewards", 18, { 0.2, 0.1, 0.05, 1 })
    rf.ItemChooseText = fstring(rf, nil, "You will be able to choose one of these rewards:", 13, { 0.2, 0.1, 0.05, 1 })
    rf.ItemReceiveText = fstring(rf, nil, "You will receive:", 13, { 0.2, 0.1, 0.05, 1 })
    for i, f in ipairs({ rf.Header, rf.ItemChooseText, rf.ItemReceiveText }) do
        f.w, f.h = 280, 18
        f.points[1] = { point = "TOPLEFT", rel = rf, relPoint = "TOPLEFT", x = 0, y = -(i - 1) * 20 }
    end
    rf.RewardButtons = {}
    for i = 1, 5 do
        local col, r = (i - 1) % 2, math.floor((i - 1) / 2)
        local b = largeItem(rf, "QuestInfoRewardsFrameQuestInfoItem" .. i, col * 150, -(70 + r * 44), i, i <= 3 and "choice" or "reward")
        b.Name:SetText(({ "Hunting Gloves", "Tracker's Belt", "Hide Bracers", "Linen Bandage", "Hunter's Mark Scroll" })[i])
        b.Icon.path = "Interface\\Icons\\inv_" .. i
        rf.RewardButtons[i] = b
    end
    rf.MoneyFrame = money(rf, "QuestInfoMoneyFrame", 90, -200)
    rf.XPFrame = blz("Frame", "QuestInfoXPFrame", rf, 200, 18, "TOPLEFT", 0, -196)
    rf.XPFrame.ReceiveText = fstring(rf.XPFrame, nil, "Experience:", 13, { 0.2, 0.1, 0.05, 1 })
    rf.XPFrame.ValueText = fstring(rf.XPFrame, nil, "450", 13, { 1, 1, 1, 1 })
    rf.XPFrame.ValueText.points[1] = { point = "LEFT", rel = rf.XPFrame, relPoint = "LEFT", x = 90, y = 0 }
    rf.XPFrame.ReceiveText.points[1] = { point = "LEFT", rel = rf.XPFrame, relPoint = "LEFT", x = 0, y = 0 }
    rf.ItemHighlight = blz("Frame", "QuestInfoItemHighlight", rf, 256, 64, "TOPLEFT", 0, 0)
    rf.ItemHighlight.shown = false
    tex(rf.ItemHighlight, nil, "BACKGROUND").path = "Interface\\QuestFrame\\UI-QuestItemHighlight"
    -- the progress page's required item buttons, anchored the way QuestFrame.xml does (the first under the header at -3, -5)
    local items = {}
    for i = 1, 4 do
        local b = largeItem(progress, "QuestProgressItem" .. i, 0, 0, i, "required")
        b.Name:SetText(({ "Bristleback Belt", "Hen Meat", "Swoop Talon", "Empty Vial" })[i])
        b.Icon.path = "Interface\\Icons\\inv_misc_" .. i
        b.Count:SetText(({ "12", "8", "", "" })[i])
        items[i] = b
    end
    items[1].points[1] = { point = "TOPLEFT", rel = QuestProgressRequiredItemsText, relPoint = "BOTTOMLEFT", x = -3, y = -5 }
    items[2].points[1] = { point = "LEFT", rel = items[1], relPoint = "RIGHT", x = 2, y = 0 }
    items[3].points[1] = { point = "TOP", rel = items[1], relPoint = "BOTTOM", x = 0, y = -3 }
    items[4].points[1] = { point = "LEFT", rel = items[3], relPoint = "RIGHT", x = 2, y = 0 }
    QuestProgressItem4:Hide()
    progress.MoneyFrame = money(progress, "QuestProgressRequiredMoneyFrame", 150, -300)
    -- the greeting panel: a ScrollFrame whose child holds the paragraph and the two headers, and a pool of title buttons on it
    local sf = blz("ScrollFrame", "QuestGreetingScrollFrame", greeting, 300, 403, "TOPLEFT", 5, -65)
    local child = blz("Frame", "QuestGreetingScrollChildFrame", sf, 300, 403, "TOPLEFT", 0, 0)
    sf.scrollChild = child
    sf.ScrollBar = scrollBar(greeting, sf, 9, -2, 399)
    local g = fstring(child, "GreetingText", "", 13, { 0.2, 0.1, 0.05, 1 })
    g.w = 270
    g.points[1] = { point = "TOPLEFT", rel = child, relPoint = "TOPLEFT", x = 10, y = -10 }
    AutoFit(g)
    for _, n in ipairs({ "CurrentQuestsText", "AvailableQuestsText" }) do
        local f = fstring(child, n, n == "CurrentQuestsText" and "Current Quests" or "Available Quests", 13, { 0.2, 0.1, 0.05, 1 })
        f.w, f.h = 300, 16
        f.points[1] = { point = "TOPLEFT", rel = GreetingText, relPoint = "BOTTOMLEFT", x = 0, y = -10 }
    end
    local brk = tex(child, "QuestGreetingFrameHorizontalBreak", "ARTWORK")
    brk.path = "Interface\\QuestFrame\\UI-HorizontalBreak"
    brk.stock = { 0.5, 0.4, 0.2 }
    brk.w, brk.h = 256, 32
    brk.points[1] = { point = "TOPLEFT", rel = child, relPoint = "TOPLEFT", x = 22, y = 5 }
    local pool = { active = {}, free = {} }
    function pool:Acquire()
        local b = table.remove(self.free) or titleButton(child)
        self.active[#self.active + 1] = b
        return b
    end
    function pool:ReleaseAll()
        for _, b in ipairs(self.active) do b:Hide(); b:ClearAllPoints(); self.free[#self.free + 1] = b end
        self.active = {}
    end
    function pool:EnumerateActive()
        local i = 0
        return function() i = i + 1; return self.active[i] end
    end
    greeting.titleButtonPool = pool
    -- QuestFrameGreetingPanel_OnShow (QuestFrame.lua): the paragraph, "Current Quests" and its buttons, the break, "Available Quests"
    function QuestFrameGreetingPanel_OnShow()
        pool:ReleaseAll()
        GreetingText:SetText(QUESTS.greeting)
        local last
        if #QUESTS.active == 0 then
            CurrentQuestsText:Hide()
            QuestGreetingFrameHorizontalBreak:Hide()
        else
            CurrentQuestsText:SetPoint("TOPLEFT", GreetingText, "BOTTOMLEFT", 0, -10)
            CurrentQuestsText:Show()
            for i, q in ipairs(QUESTS.active) do
                local b = pool:Acquire()
                b:SetText(q.title)
                b.Icon:SetVertexColor(1, 1, 1, 1)
                if q.complete then b.Icon:SetTexture(ACTIVE) else b.Icon:SetAtlas("SideInProgressquesticon") end
                b:SetID(i)
                b.isActive = 1
                if last then b:SetPoint("TOPLEFT", last, "BOTTOMLEFT", 0, -2) else b:SetPoint("TOPLEFT", CurrentQuestsText, "BOTTOMLEFT", -10, -5) end
                b:Show()
                last = b
            end
        end
        if #QUESTS.available == 0 then
            AvailableQuestsText:Hide()
            if #QUESTS.active == 0 then QuestGreetingFrameHorizontalBreak:Hide() end
        else
            if #QUESTS.active > 0 then
                QuestGreetingFrameHorizontalBreak:SetPoint("TOPLEFT", last, "BOTTOMLEFT", 22, -10)
                QuestGreetingFrameHorizontalBreak:Show()
                AvailableQuestsText:SetPoint("TOPLEFT", QuestGreetingFrameHorizontalBreak, "BOTTOMLEFT", -12, -10)
            else
                AvailableQuestsText:SetPoint("TOPLEFT", GreetingText, "BOTTOMLEFT", 0, -10)
            end
            AvailableQuestsText:Show()
            last = nil
            for i, q in ipairs(QUESTS.available) do
                local b = pool:Acquire()
                b:SetText(q.title)
                b.Icon:SetTexture(OFFER)
                local gr = q.trivial and 0.5 or 1
                b.Icon:SetVertexColor(gr, gr, gr, 1)
                b:SetID(i)
                b.isActive = 0
                if last then b:SetPoint("TOPLEFT", last, "BOTTOMLEFT", 0, -2) else b:SetPoint("TOPLEFT", AvailableQuestsText, "BOTTOMLEFT", -10, -5) end
                b:Show()
                last = b
            end
        end
    end
    greeting.scripts.OnShow = function() QuestFrameGreetingPanel_OnShow() end
    -- the gossip window: a ScrollBox of pooled elements (its rows live on ScrollTarget), a scroll bar, the friendship bar, Goodbye
    local gw = blz("Frame", "GossipFrame", UIParent, 370, 496)
    gw.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 520, y = -80 }
    gw.shown = false
    local gp = blz("Frame", nil, gw, 370, 496, "TOPLEFT", 0, 0)
    gw.GreetingPanel = gp
    chrome(gw, "stuwave://dialog", gp)
    local box = blz("Frame", nil, gp, 300, 403, "TOPLEFT", 8, -65)
    gp.ScrollBox = box
    box.ScrollTarget = blz("Frame", nil, box, 300, 1, "TOPLEFT", 0, 0)
    box.ScrollTarget.points[2] = { point = "TOPRIGHT", rel = box, relPoint = "TOPRIGHT", x = 0, y = 0 }
    box.rows, box.pools = {}, {}
    box.ForEachFrame = function(self, fn) for _, r in ipairs(self.rows) do fn(r) end end
    box.GetView = function() return {} end
    box.Update = function() end
    gp.ScrollBar = scrollBar(gp, box, 6, -3, 397)
    local friend = blz("StatusBar", nil, gw, 130, 12, "TOPLEFT", 80, -41)
    friend.shown = false
    gw.FriendshipStatusBar = friend
    gw.scripts.OnShow = function() RebuildGossip() end
    -- a book
    local book = blz("Frame", "ItemTextFrame", UIParent, 338, 496)
    book.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 900, y = -80 }
    book.shown = false
    atex(book, "ItemTextFramePageBg", "BACKGROUND", "QuestBG-Parchment", 330, 440)
    local bsf = blz("ScrollFrame", "ItemTextScrollFrame", book, 280, 360, "TOPLEFT", 20, -60)
    fstring(book, "ItemTextCurrentPage", "Page 1", 12, { 1, 0.82, 0, 1 }).points[1] = { point = "BOTTOM", rel = book, relPoint = "BOTTOM", x = 0, y = 40 }
    pager(book, "ItemTextPrevPageButton", "<").enabled = false
    pager(book, "ItemTextNextPageButton", ">")
end
"""

# The glyph atlas, read once: the alpha of the 12 x 12 art of each of the eight cells (4 columns x 2 rows of 16 px), so a render shows
# the real glyphs, tinted by the vertex colour the skin gave them.
GLYPH_TGA = support.ADDON / "Media/Textures/gossip_glyphs.tga"


def glyph_alpha() -> dict[int, list[int]]:
    data = GLYPH_TGA.read_bytes()
    width, height = struct.unpack("<HH", data[12:16])
    pixels = data[18:]
    cells: dict[int, list[int]] = {}
    for cell in range(8):
        cx, cy = cell % 4, cell // 4
        cells[cell] = [pixels[((cy * 16 + 2 + j) * width + cx * 16 + 2 + i) * 4 + 3] for j in range(12) for i in range(12)]
    return cells


# After the measuring helpers: the glyph textures become flat texels in the render ops, and a typed or wrapped paragraph is drawn
# as its lines (the base renderer draws one text op per FontString on a single line)
GLYPH_LUA = r"""
local baseDump = DumpOps
function DumpOps(roots)
    local ops = baseDump(roots)
    local out = {}
    for _, op in ipairs(ops) do
        local lines
        if op.kind == "text" then
            for _, o in ipairs(ALL) do
                if o.kind == "FontString" and o.autoH and o.text == op.text and visible(o) then
                    local wrapped = o:WrappedLines()
                    local lh = o:GetLineHeight() * PPU
                    local n = o.gradient and o.gradient[1] or math.huge
                    lines = {}
                    for i, ln in ipairs(wrapped) do
                        local k = math.min(#ln.text, n - ln.first + 1)
                        if k > 0 then
                            lines[#lines + 1] = { kind = "text", l = op.l, r = op.r, t = op.t + (i - 1) * lh, b = op.t + i * lh,
                                text = ln.text:sub(1, k), size = op.size, rgba = op.rgba, justify = op.justify }
                        end
                    end
                    break
                end
            end
        end
        if lines then for _, l in ipairs(lines) do out[#out + 1] = l end else out[#out + 1] = op end
    end
    for _, o in ipairs(ALL) do
        if o.kind == "Texture" and type(o.path) == "string" and o.path:find("gossip_glyphs", 1, true) and o.tc and visible(o) then
            local a = alphaOf(o)
            if a > 0 then
                local l, t, r, b = Px(o, UIParent)
                local cx, cy = math.floor(o.tc[1] * 64 / 16), math.floor(o.tc[3] * 32 / 16)
                local cell = GLYPH_ALPHA[cy * 4 + cx]
                local v = o.vertex or { 1, 1, 1, 1 }
                if cell then
                    local w, h = (r - l) / 12, (b - t) / 12
                    for j = 0, 11 do
                        local i = 0
                        while i < 12 do
                            local px = cell[j * 12 + i + 1]
                            if px > 0 then
                                local e = i
                                while e + 1 < 12 and cell[j * 12 + e + 2] == px do e = e + 1 end
                                out[#out + 1] = { kind = "flat", l = l + i * w, r = l + (e + 1) * w, t = t + j * h, b = t + (j + 1) * h,
                                    rgba = { v[1], v[2], v[3], px / 255 * (v[4] or 1) * a } }
                                i = e + 1
                            else
                                i = i + 1
                            end
                        end
                    end
                end
            end
        end
    end
    return out
end
"""


class QuestHarness(Harness):
    def runtime(self):
        rt = support.LuaRuntime(unpack_returned_tuples=False)
        rt.globals()["SOURCES_PY"] = rt.table_from(self.sources)
        rt.execute("SOURCES = SOURCES_PY")
        alpha = glyph_alpha()
        table = "{" + ",".join(f"[{k}]={{" + ",".join(map(str, v)) + "}" for k, v in alpha.items()) + "}"
        rt.execute("\n".join([support.ENGINE, support.GLUE, support.CHARACTER_LUA, self.blizzard_lua, support.MEASURE,
                              f"GLYPH_ALPHA = {table}", GLYPH_LUA, "BuildBlizzard()"]))
        return rt


H = QuestHarness({"ButtonSkins": "Core/ButtonSkins.lua", "FieldSkins": "Core/FieldSkins.lua", "ScrollBarSkins": "Core/ScrollBarSkins.lua",
                  "Character": "Modules/Skins/Character.lua", "Quest": "Modules/Skins/Quest.lua"}, BLIZZARD)
case = H.case

OPEN = "Fire('PLAYER_ENTERING_WORLD'); QuestFrame:Show(); QuestFrameDetailPanel:Show(); QuestInfo_Display(); FlushTimers()"
OPEN_PROGRESS = ("Fire('PLAYER_ENTERING_WORLD'); QuestFrame:Show(); QuestFrameDetailPanel:Hide(); QuestFrameProgressPanel:Show(); "
                 "QuestFrameProgressItems_Update(); FlushTimers()")

case("quest rewards: every button gets a card and a slot over its icon, the stock name plate and quality border are held, scripts stay", f"""
    {OPEN}
    local S = FS.QuestSkin.state
    local rf = QuestInfoRewardsFrame
    for i = 1, 5 do
        local b = rf.RewardButtons[i]
        assert(S.cards[b], 'button ' .. i .. ' not carded')
        assert(b.NameFrame.alpha == 0 and b.IconBorder.alpha == 0 and b.IconOverlay.alpha == 0 and b.IconOverlay2.alpha == 0, 'stock art kept on ' .. i)
        assert(b.Icon.alpha ~= 0, 'the icon must stay on ' .. i)
        assert(b.scripts.OnClick and b.scripts.OnEnter, 'stock script lost on ' .. i)
        assert(b.Name.fontPath ~= 'stock.ttf', 'name not mono on ' .. i)
        local host = S.slots[b]
        assert(host and FS.ItemSlotSkins.Parts(host), 'no slot layer on ' .. i)
        assert(b.Icon.points[1].rel == host, 'icon not seated in its slot on ' .. i)
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("quest rewards: the slot takes its quality from SetItemButtonQuality and a card dims when its row is empty", f"""
    {OPEN}
    local S = FS.QuestSkin.state
    local b = QuestInfoRewardsFrame.RewardButtons[2]
    SetItemButtonQuality(b, 4)
    local parts = FS.ItemSlotSkins.Parts(S.slots[b])
    local epic = FS.Theme.COLOR_QUALITY[4]
    assert(math.abs(parts.led.color[1] - epic[1]) < 0.01 and math.abs(parts.led.color[3] - epic[3]) < 0.01, 'LED not epic')
    SetItemButtonQuality(b, 2)
    assert(math.abs(parts.led.color[2] - FS.Theme.COLOR_QUALITY[2][2]) < 0.01, 'LED did not follow the quality')
""")

case("quest rewards: the picked choice lights pink, the other choices dim, a reward that is not a choice is untouched; the stock glow is held", f"""
    {OPEN}
    local S = FS.QuestSkin.state
    local rf = QuestInfoRewardsFrame
    local c1, c2, c3, r4 = rf.RewardButtons[1], rf.RewardButtons[2], rf.RewardButtons[3], rf.RewardButtons[4]
    local idle = S.cards[c1].box.edges[1].color
    assert(idle[3] > 0.4 and idle[1] < 0.4, 'idle edge not the dim violet')
    assert(not S.cards[c2].scrim.shown, 'a scrim before any pick')
    c2:RunScript('OnClick')
    local pink = S.cards[c2].box.edges[1].color
    assert(pink[1] > 0.9 and pink[2] < 0.3, 'picked card not pink')
    assert(S.cards[c1].scrim.shown and S.cards[c3].scrim.shown and not S.cards[c2].scrim.shown, 'the others must dim, the pick must not')
    assert(not S.cards[r4].scrim.shown, 'a plain reward dimmed')
    assert(S.cards[c2].reticle and S.cards[c2].reticle.tlH.shown, 'no lock-on brackets on the pick')
    for _, t in ipairs(rf.ItemHighlight.regions) do assert(t.alpha == 0, 'stock pick glow kept') end
    -- a new page clears the pick
    QuestInfoFrame.itemChoice = 0
    QuestInfo_Display()
    assert(not S.cards[c2].scrim.shown and not S.cards[c1].scrim.shown, 'the pick outlived the page')
""")

case("quest rewards: a card lights cyan under the hand and returns", f"""
    {OPEN}
    local S = FS.QuestSkin.state
    local b = QuestInfoRewardsFrame.RewardButtons[1]
    b:RunScript('OnEnter')
    assert(S.cards[b].box.edges[1].color[2] > 0.8 and S.cards[b].box.edges[1].color[1] < 0.3, 'hover edge not cyan')
    assert(FS.ItemSlotSkins.Parts(S.slots[b]).state.hover, 'the slot did not follow the hover')
    b:RunScript('OnLeave')
    assert(S.cards[b].box.edges[1].color[2] < 0.4, 'did not return to idle')
    assert(not FS.ItemSlotSkins.Parts(S.slots[b]).state.hover, 'the slot kept the hover')
""")

case("quest text: the headers and texts are mono, the money and XP lines wear the shared money style", f"""
    {OPEN}
    for _, n in ipairs({{ 'QuestInfoTitleHeader', 'QuestInfoDescriptionText', 'QuestInfoObjectivesHeader', 'QuestInfoObjectivesText',
        'QuestInfoObjective1', 'QuestInfoObjective2', 'QuestInfoRewardText' }}) do
        assert(_G[n].fontPath ~= 'stock.ttf', n .. ' not mono')
    end
    local rf = QuestInfoRewardsFrame
    assert(rf.Header.fontPath ~= 'stock.ttf' and rf.ItemChooseText.fontPath ~= 'stock.ttf' and rf.XPFrame.ReceiveText.fontPath ~= 'stock.ttf', 'rewards texts')
    assert(QuestInfoMoneyFrameGoldButtonText.fontPath ~= 'stock.ttf', 'money not styled')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("quest progress: the required items are cards with a slot, the money line is styled, the page texts are mono", f"""
    {OPEN_PROGRESS}
    local S = FS.QuestSkin.state
    for i = 1, 4 do
        local b = _G['QuestProgressItem' .. i]
        assert(S.cards[b] and S.slots[b], 'item ' .. i .. ' not skinned')
        assert(b.NameFrame.alpha == 0, 'name plate kept on ' .. i)
        assert(b.Count.fontPath ~= 'stock.ttf', 'count not mono')
    end
    assert(QuestProgressRequiredMoneyFrameGoldButtonText.fontPath ~= 'stock.ttf', 'fee not styled')
    assert(QuestProgressText.fontPath ~= 'stock.ttf' and QuestProgressTitleText.fontPath ~= 'stock.ttf', 'texts')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

# The item card, from the stock numbers: 147 x 41 button, 39 x 39 icon at its top left, Count at the icon's bottom right, Name 90 x 36
# on a 128 x 64 name plate (all held). The slot sits inside the card with the same padding on every side, the icon is centred in it,
# the count is inside it clear of the bottom right chamfer, the name is one line centred on the slot.
ITEM_CARD = """
    local S = FS.QuestSkin.state
    local ppu = PPU
    local card, slot = S.cards[b], S.slots[b]
    assert(card and slot, 'no card or slot')
    local cl, ct, cr, cb = Px(card.ref, b)
    local sl, st, sr, sb = Px(slot, b)
    local pads = { sl - cl, st - ct, cb - sb }
    local lo, hi = math.min(unpack(pads)), math.max(unpack(pads))
    assert(lo >= 2 and hi - lo <= 1.01, string.format('slot padding in the card: l=%.2f t=%.2f b=%.2f', unpack(pads)))
    assert(Near(sr - sl, sb - st, 0.01), 'slot not square')
    local il, it, ir, ib = Px(b.Icon, slot)
    local sw = sr - sl
    local m = { il, it, sw - ir, sw - ib }
    assert(math.max(unpack(m)) - math.min(unpack(m)) <= 0.51 and math.min(unpack(m)) >= 3, string.format('icon margins in the ring: %.2f %.2f %.2f %.2f', unpack(m)))
    assert(b.Icon.points[1].rel == slot, 'icon not seated on the slot')
    local nl, nt, nr, nb = Px(b.Name, b)
    local ncy, scy = (nt + nb) / 2, (st + sb) / 2
    assert(math.abs(ncy - scy) <= 1, string.format('name centre %.2f vs slot centre %.2f', ncy, scy))
    assert(nl >= sr + 4, string.format('name starts %.2f px after the slot', nl - sr))
    assert(nr <= cr, string.format('name runs %.2f px past the card', nr - cr))
    local lines, full, avail = b.Name:GetNumLines(), b.Name:GetStringWidth() * ppu, nr - nl
    assert((lines == 1 and full <= avail + 0.5) or lines <= 2, string.format('name %.1f px wide in %.1f takes %d lines', full, avail, lines))
    if b.Name:GetText() == 'Bristleback Belt' then assert(lines == 1, 'Bristleback Belt wraps') end
    if b.Count.text ~= '' then
        local kl, kt, kr, kb = Px(b.Count, b)
        assert(kr <= sr and kb <= sb and kl >= sl and kt >= st, 'count outside the slot')
        assert((sr - kr) + (sb - kb) >= 9, string.format('count %.2f + %.2f from the bottom right corner crowds the chamfer', sr - kr, sb - kb))
        assert(kl >= sl + il + 2, 'count runs onto the left of the icon')
    end
"""

case("quest progress: Bristleback Belt (count 12) sits in its card with equal padding, the icon centred in the ring, the count clear of the chamfer, the name on one line", f"""
    {OPEN_PROGRESS}
    local b = QuestProgressItem1
    assert(b.Name:GetText() == 'Bristleback Belt' and b.Count:GetText() == '12', 'mock item')
    {ITEM_CARD}
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("quest detail and reward pages: every reward and choose-one card has the same seat as the required item card", f"""
    {OPEN}
    for i = 1, 5 do
        local b = QuestInfoRewardsFrame.RewardButtons[i]
        {ITEM_CARD}
    end
    {OPEN_PROGRESS}
    for i = 2, 3 do
        local b = _G['QuestProgressItem' .. i]
        {ITEM_CARD}
    end
""")

# ---------------------------------------------------------------------------------------------------------------------
# The quest greeting list, the gossip window: cards only on real buttons, a glyph per kind, the band, the typed greeting
# ---------------------------------------------------------------------------------------------------------------------

# cell of the glyph atlas by kind (generate_gossip_glyphs.py): bubble 0, bag 1, book 2, house 3, plane 4, bang 5, qmark 6, coin 7
CELL = """
    function CellOf(t)
        assert(t.tc, 'glyph has no texcoord')
        return math.floor(t.tc[1] * 64 / 16) + 4 * math.floor(t.tc[3] * 32 / 16)
    end
    function CardsOn(rows)
        local n = 0
        for _, r in ipairs(rows) do
            local rec = FS.QuestSkin.state.rows[r]
            if rec and rec.on then n = n + 1 end
        end
        return n
    end
"""

case("gossip: only the option and quest buttons are cards; the greeting frame and every spacer get no card, nothing is drawn on them", CELL + """
    OpenGossip(SPACER_GOSSIP)
    local S = FS.QuestSkin.state
    local rows = ListRows()
    assert(#rows == 5, 'mock rows ' .. #rows)
    assert(CardsOn(rows) == 1, 'cards on ' .. CardsOn(rows) .. ' rows, wanted the one quest button')
    assert(S.rows[rows[4]] and S.rows[rows[4]].on, 'the quest button has no card')
    for i, r in ipairs(rows) do
        if i ~= 4 and i ~= 1 then
            assert(#r.regions == 0 and #r.children == 0, 'spacer ' .. i .. ' got ' .. #r.regions .. ' regions and ' .. #r.children .. ' children')
        end
    end
    assert(not S.rows[rows[1]], 'the greeting frame is a button row')
    assert(rows[1].GreetingText.fontPath ~= 'stock.ttf', 'greeting not mono')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("gossip: a frame that is reused and stops being a button drops its card, and gets it back when it is one again", CELL + """
    OpenGossip()
    local S = FS.QuestSkin.state
    local box = GossipFrame.GreetingPanel.ScrollBox
    local b = ListRows()[3]
    local rec = S.rows[b]
    assert(rec and rec.on, 'option not carded')
    local function parts() return { rec.fill, rec.ring, rec.glyph, rec.bar } end
    b:SetText('')
    box:Update(); FlushTimers()
    assert(not rec.on, 'the card outlived the text')
    for _, t in ipairs(parts()) do assert(not t.shown, 'a card part is still shown') end
    b:SetText('Back again.')
    box:Update(); FlushTimers()
    assert(rec.on, 'the card did not come back')
    for _, t in ipairs({ rec.fill, rec.ring, rec.glyph }) do assert(t.shown, 'a card part is hidden') end
    -- a frame with no icon is a spacer
    local keep = b.Icon
    b.Icon = nil
    box:Update(); FlushTimers()
    assert(not rec.on, 'a frame without an icon kept its card')
    b.Icon = keep
    box:Update(); FlushTimers()
    assert(rec.on, 'the card did not come back with the icon')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("gossip: a recycled frame takes the new element's kind (trainer then vendor), a pooled frame reused by a later page is re-read", CELL + """
    OpenGossip()
    local S = FS.QuestSkin.state
    local first = ListRows()[3]
    assert(S.rows[first].kind == 'vendor', 'first kind ' .. tostring(S.rows[first].kind))
    local copy = { greeting = 'New text.', list = { { t = 'title' }, { t = 'spacer' }, { t = 'option', name = 'Train me.', icon = 7000003, orderIndex = 1 } } }
    GOSSIP_DATA = copy
    RebuildGossip(); FlushTimers()
    local rows = ListRows()
    assert(rows[3] == first, 'the frame was not reused')
    assert(S.rows[first].kind == 'trainer', 'reused frame kept ' .. tostring(S.rows[first].kind))
    assert(CellOf(S.rows[first].glyph) == 2, 'glyph not the book')
    assert(CardsOn(rows) == 1, 'cards ' .. CardsOn(rows))
""")

case("gossip: a glyph and a colour per option kind from what the client gives, the stock icon held and unchanged", CELL + """
    OpenGossip()
    local S = FS.QuestSkin.state
    local rows = ListRows()
    local want = {
        { 3, 'vendor', 1 }, { 4, 'trainer', 2 }, { 5, 'binder', 3 }, { 6, 'flight', 4 }, { 7, 'paid', 7 }, { 8, 'gossip', 0 },
        { 10, 'qnew', 5 }, { 11, 'qdone', 6 }, { 12, 'qwip', 6 },
    }
    for _, w in ipairs(want) do
        local r = rows[w[1]]
        local rec = S.rows[r]
        assert(rec and rec.on, 'row ' .. w[1] .. ' not carded')
        assert(rec.kind == w[2], 'row ' .. w[1] .. ' kind ' .. tostring(rec.kind) .. ', wanted ' .. w[2])
        assert(CellOf(rec.glyph) == w[3], 'row ' .. w[1] .. ' glyph cell ' .. CellOf(rec.glyph) .. ', wanted ' .. w[3])
        assert(r.Icon.alpha == 0, 'stock icon of row ' .. w[1] .. ' kept')
        assert(r.highlightTex.alpha == 0, 'stock highlight of row ' .. w[1] .. ' kept')
        assert(r.scripts.OnClick and r.scripts.OnEnter and r.scripts.OnLeave, 'stock script lost on row ' .. w[1])
    end
    -- the stock icon still says what the client set
    assert(rows[3].Icon:GetTexture() == 7000002, 'stock icon changed')
    assert(rows[11].Icon:GetTexture() == 'Interface/GossipFrame/ActiveQuestIcon', 'quest icon changed')
    assert(rows[12].Icon:GetAtlas() == 'SideInProgressquesticon', 'atlas icon changed')
    -- colours: gold quest marks, a grey in-progress mark, amber for a vendor and a paid option, pink for the inn
    local function col(i) local v = S.rows[rows[i]].glyph.vertex; return v[1], v[2], v[3] end
    local r, g, b = col(10)
    assert(r > 0.9 and g > 0.7 and g < 0.9 and b < 0.4, 'available mark not gold')
    r, g, b = col(12)
    assert(math.abs(r - g) < 0.2 and b > r and r < 0.6, 'in progress mark not grey')
    r, g, b = col(3)
    assert(r > 0.9 and g > 0.6 and b < 0.3, 'vendor not amber')
    r, g, b = col(5)
    assert(r > 0.9 and g < 0.4, 'inn not pink')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("gossip: the glyph is 12 px square, whole pixels, centred on the row's line; the label keeps the stock place", CELL + """
    OpenGossip()
    local S = FS.QuestSkin.state
    local rows = ListRows()
    for _, i in ipairs({ 3, 5, 10, 11 }) do
        local r = rows[i]
        local g = S.rows[r].glyph
        local gl, gt, gr, gb = Px(g, r)
        local rl, rt, rr, rb = Px(r, r)
        assert(Near(gr - gl, 12) and Near(gb - gt, 12), 'glyph size ' .. (gr - gl) .. ' x ' .. (gb - gt))
        assert(Near(gl, math.floor(gl + 0.5), 0.001) and Near(gt, math.floor(gt + 0.5), 0.001), 'glyph off the pixel grid')
        assert(math.abs(((gt + gb) / 2) - ((rt + rb) / 2)) <= 1, string.format('glyph centre %.2f vs row centre %.2f', (gt + gb) / 2, (rt + rb) / 2))
        local tl = Px(r.fs, r)
        assert(gr + 4 <= tl, 'glyph runs into the label')
    end
""")

case("gossip: an unknown file id gets the neutral bubble, a client without C_Texture does not break, a dim kind greys its glyph", CELL + """
    local copy = { greeting = 'Hello.', list = { { t = 'title' }, { t = 'spacer' },
        { t = 'option', name = 'Mystery.', icon = 9999999, orderIndex = 1 },
        { t = 'option', name = 'Locked.', icon = 7000002, orderIndex = 2, status = 1 },
        { t = 'available', questID = 5, title = 'Old news', path = OFFER, trivial = true } } }
    OpenGossip(copy)
    local S = FS.QuestSkin.state
    local rows = ListRows()
    assert(S.rows[rows[3]].kind == 'gossip' and CellOf(S.rows[rows[3]].glyph) == 0, 'unknown id is not the bubble')
    assert(S.rows[rows[4]].dim, 'an unavailable option is not dimmed')
    assert(S.rows[rows[5]].dim, 'a trivial quest is not dimmed')
    assert(not S.rows[rows[3]].dim, 'a plain option is dimmed')
    local dv, nv = S.rows[rows[4]].glyph.vertex, S.rows[rows[3]].glyph.vertex
    assert(math.abs(dv[1] - dv[2]) < 0.15 and dv[1] < 0.5, 'dim glyph not grey')
    C_Texture = nil
    GOSSIP_DATA = copy
    RebuildGossip(); FlushTimers()
    assert(S.rows[ListRows()[4]].kind == 'gossip', 'without C_Texture the kind is not neutral')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("gossip: the ready chip is on the quest that can be turned in and nowhere else", CELL + """
    OpenGossip()
    local S = FS.QuestSkin.state
    local rows = ListRows()
    for i, r in ipairs(rows) do
        local rec = S.rows[r]
        if rec then
            local want = (i == 11)
            assert((rec.chip ~= nil and rec.chip.shown == true) == want, 'row ' .. i .. ' chip shown: ' .. tostring(rec.chip and rec.chip.shown))
        end
    end
    local rec = S.rows[rows[11]]
    assert(rec.chipLabel:GetText() == 'ready', 'chip text ' .. tostring(rec.chipLabel:GetText()))
    local cl, ct, cr, cb = Px(rec.chip, rows[11])
    local _, rt, rr, rb = Px(rows[11], rows[11])
    assert(Near(rr - cr, 6, 0.6), 'chip right margin ' .. (rr - cr))
    assert(math.abs((ct + cb) / 2 - (rt + rb) / 2) <= 1, 'chip not centred on the row')
    -- a quest that is no longer ready drops the chip
    rows[11].Icon:SetAtlas('SideInProgressquesticon')
    GossipFrame.GreetingPanel.ScrollBox:Update(); FlushTimers()
    assert(S.rows[rows[11]].kind == 'qwip' and not rec.chip.shown, 'the chip stayed on a quest in progress')
""")

case("gossip: a card lights cyan with a left bar under the hand and returns; the row follows the hover of a recycled frame", CELL + """
    OpenGossip()
    local S = FS.QuestSkin.state
    local r = ListRows()[5]
    local rec = S.rows[r]
    local idle = rec.ring.vertex
    assert(idle[3] > 0.3 and idle[1] < 0.4 and idle[2] < 0.3, 'idle ring not the dim violet')
    assert(not rec.bar.shown, 'bar before the hover')
    r:RunScript('OnEnter')
    assert(rec.ring.vertex[2] > 0.8 and rec.ring.vertex[1] < 0.3, 'hover ring not cyan')
    assert(rec.bar.shown, 'no bar under the hand')
    assert(rec.fill.vertex[3] > 0.15, 'hover fill not lifted')
    r:RunScript('OnLeave')
    assert(rec.ring.vertex[2] < 0.3 and not rec.bar.shown, 'did not return to idle')
    -- a recycled frame starts idle even if it was left under the hand
    r:RunScript('OnEnter')
    r:Hide(); r:Show()
    assert(rec.ring.vertex[2] < 0.3 and not rec.bar.shown, 'a reused frame kept the hover')
""")

case("gossip: the speaker band names the NPC from UnitName, a secret or missing name falls back, nothing reads the name unguarded", CELL + """
    OpenGossip()
    local S = FS.QuestSkin.state
    local band = S.band
    assert(band and band.frame:IsShown(), 'no speaker band')
    assert(band.name:GetText() == 'Baine Bloodhoof', 'name ' .. tostring(band.name:GetText()))
    assert(band.letter:GetText() == 'B', 'initial ' .. tostring(band.letter:GetText()))
    assert(band.chipLabel:GetText() == 'speaking', 'chip ' .. tostring(band.chipLabel:GetText()))
    local sf, st, sr, sb = Px(band.frame, GossipFrame.GreetingPanel.ScrollBox)
    local box = GossipFrame.GreetingPanel.ScrollBox
    assert(Near(sb, -6, 0.6), 'band sits ' .. (-sb) .. ' px above the list, wanted 6')
    local _, _, rr = Px(box, box)
    assert(Near(sr, rr, 0.6), 'band right edge ' .. sr .. ' vs list ' .. rr)
    assert(Near(sb - st, 40, 0.6), 'band height ' .. (sb - st))
    -- a secret name
    GossipFrame:Hide()
    NPC.name = Secret()
    GossipFrame:Show(); FlushTimers()
    assert(band.name:GetText() == 'unknown', 'secret name shown as ' .. tostring(band.name:GetText()))
    GossipFrame:Hide()
    NPC.name = nil
    GossipFrame:Show(); FlushTimers()
    assert(band.name:GetText() == 'unknown', 'missing name shown as ' .. tostring(band.name:GetText()))
    GossipFrame:Hide()
    NPC.name = 'Thorn Grimtotem'
    GossipFrame:Show(); FlushTimers()
    assert(band.name:GetText() == 'Thorn Grimtotem' and band.letter:GetText() == 'T', 'the band did not follow the new NPC')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("gossip: the band draws under the friendship bar and the waveform moves while shown", CELL + """
    OpenGossip()
    local S = FS.QuestSkin.state
    local band = S.band
    assert(band.frame:GetFrameLevel() < GossipFrame.FriendshipStatusBar:GetFrameLevel(), 'band above the friendship bar')
    assert(#band.bars >= 10, 'bars ' .. #band.bars)
    local function heights() local t = {}; for i, b in ipairs(band.bars) do local _, bt, _, bb = Px(b, band.frame); t[i] = bb - bt end; return t end
    Advance(0.1)
    local a = heights()
    Advance(0.5)
    local b2 = heights()
    local moved = 0
    for i = 1, #a do if a[i] ~= b2[i] then moved = moved + 1 end end
    assert(moved >= 4, 'waveform barely moved: ' .. moved)
    for i, b in ipairs(band.bars) do
        local bl, bt, br, bb = Px(b, band.frame)
        assert(Near(bl, math.floor(bl + 0.5), 0.001) and Near(bt, math.floor(bt + 0.5), 0.001) and Near(bb, math.floor(bb + 0.5), 0.001), 'bar ' .. i .. ' off the pixel grid')
        local hh = math.floor(bb - bt + 0.5)
        assert(Near(br - bl, 3, 0.01) and Near(bb - bt, hh, 0.01) and hh % 2 == 0, string.format('bar %d size %.4f x %.4f', i, br - bl, bb - bt))
        assert(Near((bt + bb) / 2, 20, 0.6), 'bar ' .. i .. ' not centred on the band')
    end
""")

case("gossip: nothing runs while the window is hidden, and the wave and the typing start again when it opens", CELL + """
    local idle = FS.ControlKit.AnimationCount()
    OpenGossip()
    local S = FS.QuestSkin.state
    local band = S.band
    assert(FS.ControlKit.AnimationCount() > idle, 'the wave and the typing are not running')
    Advance(0.3)
    local ticks = band.ticks
    assert(ticks > 0, 'the wave never ticked')
    GossipFrame:Hide()
    Advance(1.5)
    assert(band.ticks == ticks, 'the wave ticked while hidden: ' .. (band.ticks - ticks))
    assert(FS.ControlKit.AnimationCount() == idle, 'animations left running: ' .. (FS.ControlKit.AnimationCount() - idle))
    GossipFrame:Show(); FlushTimers()
    Advance(0.3)
    assert(band.ticks > ticks, 'the wave did not start again')
    local fs = ListRows()[1].GreetingText
    assert(fs.gradient and fs.gradient[1] < #fs.text, 'the typing did not start again')
""")

case("gossip: the greeting types in line by line with a caret, finishes on its own, and the rows land one after another", CELL + """
    OpenGossip()
    local S = FS.QuestSkin.state
    local rows = ListRows()
    local fs = rows[1].GreetingText
    local total = #fs.text
    assert(fs.gradient, 'the greeting is not typed')
    local g0 = fs.gradient[1]
    assert(g0 < total / 4, 'typing starts at ' .. g0)
    Advance(0.4)
    local g1 = fs.gradient and fs.gradient[1] or total
    assert(g1 > g0 and g1 < total, 'typing at ' .. g1 .. ' of ' .. total)
    local caret = S.typed.caret
    assert(caret and caret.shown, 'no caret while typing')
    -- the caret follows the last typed character: inside the paragraph, on the line that character is on
    local fl, ft, fr, fb = Px(fs, UIParent)
    local cl, ct, cr, cb = Px(caret, UIParent)
    assert(cl >= fl and cr <= fr + 8 and ct >= ft - 2 and cb <= fb + 2, 'caret outside the paragraph')
    -- the grid is the paragraph's own: whole pixels from its top left
    local dl, dt = cl - fl, ct - ft
    assert(Near(dl, math.floor(dl + 0.5), 0.05) and Near(dt, math.floor(dt + 0.5), 0.05), string.format('caret off the pixel grid: %.3f %.3f', dl, dt))
    -- rows are invisible until the text is done, then land in order
    for i = 3, 12 do if S.rows[rows[i]] then assert(rows[i].alpha == 0, 'row ' .. i .. ' visible while typing: ' .. rows[i].alpha) end end
    local t = 0
    local guard = 0
    while fs.gradient and guard < 200 do Advance(0.05); guard = guard + 1 end
    assert(not fs.gradient, 'the typing never finished')
    assert(not caret.shown, 'the caret stayed after the text')
    Advance(0.15)
    local early, late = rows[3].alpha, rows[12].alpha
    assert(early > late and early > 0, string.format('rows do not land in order: first %.2f last %.2f', early, late))
    Advance(1.5)
    for i = 3, 12 do if S.rows[rows[i]] then assert(rows[i].alpha == 1, 'row ' .. i .. ' ended at alpha ' .. rows[i].alpha) end end
    assert(FS.ControlKit.IsAnimating(S.band.frame, 'intro') == false, 'the intro kept running')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("gossip: a click on an option while the greeting types shows it all at once, and the click itself is the stock one", CELL + """
    OpenGossip()
    local S = FS.QuestSkin.state
    local rows = ListRows()
    local fs = rows[1].GreetingText
    Advance(0.2)
    assert(fs.gradient, 'not typing')
    assert(rows[4].alpha == 0, 'row visible before its time')
    rows[4]:RunScript('OnMouseDown', 'LeftButton')
    assert(not fs.gradient, 'a click on an option did not finish the typing')
    assert(not S.typed.caret.shown, 'caret kept after a skip')
    for i = 3, 12 do if S.rows[rows[i]] then assert(rows[i].alpha == 1, 'row ' .. i .. ' not shown after a skip') end end
    CLICKED = nil
    rows[4]:RunScript('OnClick', 'LeftButton')
    assert(CLICKED == rows[4], 'the stock click did not run')
    assert(FS.ControlKit.IsAnimating(S.band.frame, 'intro') == false, 'the intro kept running after a skip')
""")

case("gossip: a click anywhere in the window or on the greeting skips too; an option can be clicked while it is still invisible", CELL + """
    OpenGossip()
    local S = FS.QuestSkin.state
    local rows = ListRows()
    local fs = rows[1].GreetingText
    Advance(0.2)
    assert(rows[5].alpha == 0 and rows[5].scripts.OnClick, 'row not clickable while it is invisible')
    CLICKED = nil
    rows[5]:RunScript('OnClick', 'LeftButton')
    assert(CLICKED == rows[5], 'an invisible row did not take its click')
    GossipFrame:RunScript('OnMouseDown', 'LeftButton')
    assert(not fs.gradient, 'a click on the window did not skip')
    for i = 3, 12 do if S.rows[rows[i]] then assert(rows[i].alpha == 1, 'row ' .. i) end end
    -- the same for a click on the greeting frame itself
    GossipFrame:Hide(); GossipFrame:Show(); FlushTimers()
    Advance(0.2)
    assert(ListRows()[1].GreetingText.gradient, 'did not type again')
    ListRows()[1]:RunScript('OnMouseDown', 'LeftButton')
    assert(not ListRows()[1].GreetingText.gradient, 'a click on the greeting did not skip')
""")

case("gossip: the same text on a later update is not typed again; new text is; closing and opening again types it once more", CELL + """
    OpenGossip()
    local S = FS.QuestSkin.state
    local fs = ListRows()[1].GreetingText
    Advance(4)
    assert(not fs.gradient, 'did not finish')
    local box = GossipFrame.GreetingPanel.ScrollBox
    RebuildGossip(); FlushTimers(); Advance(0.2)
    assert(not ListRows()[1].GreetingText.gradient, 'the same text was typed again')
    for i = 3, 12 do if S.rows[ListRows()[i]] then assert(ListRows()[i].alpha == 1, 'row ' .. i .. ' faded again') end end
    GOSSIP_DATA = { greeting = 'A different thing to say, in several words.', list = DEFAULT_GOSSIP.list }
    RebuildGossip(); FlushTimers(); Advance(0.2)
    assert(ListRows()[1].GreetingText.gradient, 'new text was not typed')
    Advance(4)
    GossipFrame:Hide(); GossipFrame:Show(); FlushTimers(); Advance(0.2)
    assert(ListRows()[1].GreetingText.gradient, 'a reopened window did not type')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("gossip: hiding the window mid-typing leaves every row and the paragraph fully shown for the next element that reuses them", CELL + """
    OpenGossip()
    local S = FS.QuestSkin.state
    local rows = ListRows()
    Advance(0.3)
    GossipFrame:Hide()
    for i = 3, 12 do if S.rows[rows[i]] then assert(rows[i].alpha == 1, 'row ' .. i .. ' left at alpha ' .. rows[i].alpha) end end
    assert(not rows[1].GreetingText.gradient, 'a gradient left on the stock paragraph')
    assert(not S.typed.caret.shown, 'caret left')
""")

case("gossip: the greeting sits on a text card, the list on cut cards, the window has a band on top and the card edges line up", CELL + """
    OpenGossip()
    Advance(4)
    local S = FS.QuestSkin.state
    local rows = ListRows()
    local tc = S.textCards[rows[1].GreetingText]
    assert(tc and tc.fill and tc.ring, 'no card behind the paragraph')
    local fl, ft, fr, fb = Px(rows[1].GreetingText, UIParent)
    local cl, ct, cr, cb = Px(tc.fill, UIParent)
    assert(cl <= fl - 6 and ct <= ft - 5 and cb >= fb + 5, string.format('paragraph pad l=%.1f t=%.1f b=%.1f', fl - cl, ft - ct, cb - fb))
    local rl, rt, rr, rb = Px(rows[3], UIParent)
    assert(Near(cl, rl, 0.6) and Near(cr, rr, 0.6), string.format('text card x %.1f..%.1f vs rows %.1f..%.1f', cl, cr, rl, rr))
    -- the card never runs into the first button (it ends inside the spacer that follows)
    assert(cb <= rt + 0.5, 'the text card runs into the first option: ' .. (cb - rt))
    -- every row card sits inside its row's rect, one pixel in from top and bottom, whole pixels
    for _, i in ipairs({ 3, 4, 10, 11 }) do
        local r = rows[i]
        local rec = S.rows[r]
        local l, t, rr2, b = Px(rec.fill, r)
        local _, _, w, h = Px(r, r)
        assert(Near(l, 0, 0.6) and Near(t, 2, 0.6) and Near(rr2, w, 0.6) and Near(b, h - 2, 0.6), string.format('card rect %.2f %.2f %.2f %.2f in %.2f x %.2f', l, t, rr2, b, w, h))
    end
""")

case("scroll bars: the rail goes with the thumb on the gossip list and on the quest greeting", CELL + """
    OpenGossip()
    local S = FS.QuestSkin.state
    local bar = GossipFrame.GreetingPanel.ScrollBar
    local parts = FS.ScrollBarSkins.Parts(bar)
    assert(parts and parts.rail, 'bar not skinned')
    assert(not parts.rail.shown, 'a bare rail with nothing to scroll')
    bar.scrollable = true
    bar:Update(); FlushTimers()
    assert(parts.rail.shown, 'the rail did not come with the thumb')
    bar.scrollable = false
    bar:Update(); FlushTimers()
    assert(not parts.rail.shown, 'the rail stayed after the thumb went')
    OpenGreeting()
    local qbar = QuestGreetingScrollFrame.ScrollBar
    local qp = FS.ScrollBarSkins.Parts(qbar)
    assert(qp and not qp.rail.shown, 'bare rail on the quest list')
    qbar.scrollable = true; qbar:Update(); FlushTimers()
    assert(qp.rail.shown, 'quest list rail did not come')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("quest greeting: two active quests (one ready, one in progress) and one available are cards with their glyphs, the break and the headers are skinned", CELL + """
    OpenGreeting()
    local S = FS.QuestSkin.state
    local pool = QuestFrameGreetingPanel.titleButtonPool
    local list = {}
    for b in pool:EnumerateActive() do list[#list + 1] = b end
    assert(#list == 3, 'buttons ' .. #list)
    local want = { { 'qdone', 6, true }, { 'qwip', 6, false }, { 'qnew', 5, false } }
    for i, b in ipairs(list) do
        local rec = S.rows[b]
        assert(rec and rec.on, 'title button ' .. i .. ' not carded')
        assert(rec.kind == want[i][1], 'button ' .. i .. ' kind ' .. tostring(rec.kind) .. ', wanted ' .. want[i][1])
        assert(CellOf(rec.glyph) == want[i][2], 'button ' .. i .. ' glyph')
        assert((rec.chip ~= nil and rec.chip.shown == true) == want[i][3], 'button ' .. i .. ' chip')
        assert(b.Icon.alpha == 0 and b.highlightTex.alpha == 0, 'stock art kept on ' .. i)
        assert(b.scripts.OnClick, 'click lost')
        assert(b.fs.fontPath ~= 'stock.ttf', 'title not mono')
    end
    assert(QuestGreetingFrameHorizontalBreak.alpha == 0, 'the stock break was kept')
    assert(GreetingText.fontPath ~= 'stock.ttf' and CurrentQuestsText.fontPath ~= 'stock.ttf' and AvailableQuestsText.fontPath ~= 'stock.ttf', 'texts')
    assert(CardsOn(list) == 3, 'cards')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("quest greeting: the band names the NPC, the greeting types and the titles land after it; a click skips; a new page types again", CELL + """
    local idle = FS.ControlKit.AnimationCount()
    OpenGreeting()
    local S = FS.QuestSkin.state
    local band = S.band
    assert(band and band.frame:IsShown() and band.name:GetText() == 'Baine Bloodhoof', 'band ' .. tostring(band and band.name:GetText()))
    local sf, st, sr, sb = Px(band.frame, QuestGreetingScrollFrame)
    assert(Near(sb, -6, 0.6) and Near(sb - st, 40, 0.6), 'band place ' .. sb .. ' ' .. (sb - st))
    assert(GreetingText.gradient, 'the quest greeting is not typed')
    local list = {}
    for b in QuestFrameGreetingPanel.titleButtonPool:EnumerateActive() do list[#list + 1] = b end
    assert(list[1].alpha == 0, 'title visible while typing')
    Advance(0.3)
    list[1]:RunScript('OnMouseDown', 'LeftButton')
    assert(not GreetingText.gradient, 'a click on a title did not skip')
    for _, b in ipairs(list) do assert(b.alpha == 1, 'title not shown after a skip') end
    CLICKED = nil
    list[2]:RunScript('OnClick', 'LeftButton')
    assert(CLICKED == list[2], 'the stock click did not run')
    -- the next page of the same panel types again
    QuestFrameGreetingPanel:Hide()
    assert(FS.ControlKit.AnimationCount() == idle, 'animations left after the panel hid: ' .. (FS.ControlKit.AnimationCount() - idle))
    QUESTS.greeting = 'The hunt is over. Rest.'
    QuestFrameGreetingPanel:Show(); FlushTimers(); Advance(0.2)
    assert(GreetingText.gradient, 'the new greeting was not typed')
    Advance(4)
    assert(not GreetingText.gradient and not S.typed.caret.shown, 'did not finish')
    for b in QuestFrameGreetingPanel.titleButtonPool:EnumerateActive() do assert(b.alpha == 1, 'title not landed') end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("quest greeting: the text card sits behind the paragraph, the title cards stay on the stock rects", CELL + """
    OpenGreeting()
    Advance(4)
    local S = FS.QuestSkin.state
    local tc = S.textCards[GreetingText]
    assert(tc and tc.fill, 'no card behind the greeting')
    local fl, ft, fr, fb = Px(GreetingText, UIParent)
    local cl, ct, cr, cb = Px(tc.fill, UIParent)
    assert(cl < fl and ct < ft and cb > fb, 'card does not hold the paragraph')
    local cqt = select(2, Px(CurrentQuestsText, UIParent))
    assert(cb <= cqt + 0.5, 'the text card runs onto the Current Quests header')
    local spans = {}
    for b in QuestFrameGreetingPanel.titleButtonPool:EnumerateActive() do
        local l, t, r, bt = Px(S.rows[b].fill, b)
        local _, _, w, h = Px(b, b)
        assert(Near(l, 0, 0.6) and Near(r, w, 0.6) and t >= 1.5 and bt <= h - 1.5, 'card off the row')
        assert(bt - t <= 15.5 and math.abs(t - (h - bt)) <= 1.1, string.format('card not a centred 15 px strip: %.1f..%.1f of %.1f', t, bt, h))
        -- the hover ring follows the card one px in, never the stock row rect
        local ring2 = S.rows[b].plate.ring2
        if ring2 then
            local hl, ht, hr, hb = Px(ring2, b)
            assert(Near(hl, 1, 0.6) and Near(ht, t + 1, 0.6) and Near(hr, w - 1, 0.6) and Near(hb, bt - 1, 0.6),
                string.format('hover ring off the card: %.1f,%.1f,%.1f,%.1f card %.1f..%.1f', hl, ht, hr, hb, t, bt))
        end
        local _, at, _, ab = Px(S.rows[b].fill, UIParent)
        spans[#spans + 1] = { at, ab }
    end
    -- neighbouring cards (and their hover rings) never touch: rows stacked edge to edge keep a 4 px gap
    table.sort(spans, function(a, b) return a[1] < b[1] end)
    for i = 2, #spans do
        local gap = spans[i][1] - spans[i - 1][2]
        if gap > -0.5 and gap < 20 then assert(gap >= 3.5, string.format('cards %d and %d only %.2f px apart', i - 1, i, gap)) end
    end
""")

case("gossip: the existing sweeps leave a row that arrives on a later page carded once, a recycled row is not carded twice", CELL + """
    OpenGossip()
    local S = FS.QuestSkin.state
    local box = GossipFrame.GreetingPanel.ScrollBox
    local first = ListRows()[3]
    local fillA = S.rows[first].fill
    box:Update(); FlushTimers()
    assert(S.rows[first].fill == fillA, 'recycled row carded twice')
    local n = #first.regions
    box:Update(); FlushTimers(); box:Update(); FlushTimers()
    assert(#first.regions == n, 'regions grew on repeated updates: ' .. n .. ' -> ' .. #first.regions)
    local b = BLZ.blz('Button', nil, box.ScrollTarget, 300, 16, 'TOPLEFT', 0, -300)
    b.Icon = BLZ.tex(b, nil, 'BACKGROUND'); b.highlightTex = BLZ.tex(b, nil, 'HIGHLIGHT'); b.fs = BLZ.fstring(b, nil, 'New', 12)
    box.rows[#box.rows + 1] = b
    box:Update(); FlushTimers()
    assert(S.rows[b] and S.rows[b].on, 'a later row was not carded')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("books: the page keys hold the stock arrows and draw a cut key with a chevron, the page gets a ring box, the clicks stay", f"""
    Fire('PLAYER_ENTERING_WORLD'); ItemTextFrame:Show(); FlushTimers()
    local S = FS.QuestSkin.state
    local prev, nxt = ItemTextPrevPageButton, ItemTextNextPageButton
    local P = S.pagers
    assert(P[prev] and #P[prev].glyph == 9 and P[prev].key, 'prev key')
    assert(P[nxt] and #P[nxt].glyph == 9 and P[nxt].key, 'next key')
    assert(P[prev].key.ring.alpha ~= 0 and P[prev].key.fill.alpha ~= 0, 'the key must not be held')
    assert(prev.NormalTexture.alpha == 0 and nxt.NormalTexture.alpha == 0, 'stock arrow kept')
    assert(prev.scripts.OnClick and nxt.scripts.OnClick, 'page click lost')
    assert(P[prev].glyph[1].alpha == 0.35, 'disabled previous page not dimmed')
    assert(P[nxt].glyph[1].alpha == 1, 'enabled next page dimmed')
    prev:Enable()
    assert(P[prev].glyph[1].alpha == 1, 'enable did not undim')
    assert(S.page, 'no page box')
    assert(ItemTextCurrentPage.fontPath ~= 'stock.ttf', 'page number not mono')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("no script or attribute is written on a Blizzard widget while the windows are skinned and used (the mock throws on one)", CELL + """
    OpenGossip()
    Advance(0.5)
    ListRows()[4]:RunScript('OnMouseDown', 'LeftButton')
    GossipFrame:RunScript('OnMouseDown', 'LeftButton')
    GossipFrame:Hide(); GossipFrame:Show(); FlushTimers(); Advance(5)
    OpenGreeting(); Advance(5)
    for b in QuestFrameGreetingPanel.titleButtonPool:EnumerateActive() do b:RunScript('OnMouseDown', 'LeftButton') end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("nothing is built in combat; it is built when combat ends", f"""
    Reset()
    __combat = true
    Load({{ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'ButtonSkins', 'FieldSkins', 'ScrollBarSkins', 'Character', 'Quest' }})
    assert(not QuestFrame.fsQuestSkin, 'built in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(QuestFrame.fsQuestSkin and GossipFrame.fsQuestSkin and ItemTextFrame.fsQuestSkin, 'not built when combat ended')
""")

SCENES = {
    "detail": "Fire('PLAYER_ENTERING_WORLD'); QuestFrame:Show(); QuestFrameDetailPanel:Show(); QuestInfo_Display(); QuestInfoRewardsFrame.RewardButtons[2]:RunScript('OnClick'); FlushTimers(); return DumpOps({ QuestFrame })",
    "progress": "Fire('PLAYER_ENTERING_WORLD'); QuestFrame:Show(); QuestFrameDetailPanel:Hide(); QuestFrameProgressPanel:Show(); QuestFrameProgressItems_Update(); FlushTimers(); QuestProgressItem2:RunScript('OnEnter'); return DumpOps({ QuestFrame })",
    "greeting": "OpenGreeting(); Advance(5); QuestFrameGreetingPanel.titleButtonPool.active[2]:RunScript('OnEnter'); return DumpOps({ QuestFrame })",
    "greeting-typing": "OpenGreeting(); Advance(0.45); return DumpOps({ QuestFrame })",
    "gossip": "OpenGossip(); Advance(5); ListRows()[5]:RunScript('OnEnter'); return DumpOps({ GossipFrame })",
    "gossip-typing": "OpenGossip(); Advance(0.55); return DumpOps({ GossipFrame })",
    "gossip-spacers": "OpenGossip(SPACER_GOSSIP); Advance(5); return DumpOps({ GossipFrame })",
    "book": "Fire('PLAYER_ENTERING_WORLD'); ItemTextFrame:Show(); FlushTimers(); return DumpOps({ ItemTextFrame })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("quest skin", SCENES))
