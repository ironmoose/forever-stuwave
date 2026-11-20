#!/usr/bin/env python3
"""Runs the real Modules/Skins/Mail.lua headless against a mock mailbox and checks its spacing.

The mock is a small widget engine with a real anchor solver: SetPoint, SetAllPoints and SetSize are
resolved to rectangles, so every margin, gap and alignment of the MAIL v2 design (mockups/
minimap-bags-cleanup-2026-11-12.html) is measured in physical pixels (1.2 px per UI unit, the player's
display) instead of eyeballed. Blizzard's widgets are built from the 16001 globals dump names; their
SetScript and SetAttribute throw, so a skin that writes either fails a check. The real Theme.lua,
HeldArt.lua and PanelSkins.lua are loaded; only the engine is mocked.

Pinned here:

  * inbox: the window is 432 px wide, rows are 404 x 68 with a 14 px margin on both sides and a 10 px gap,
    the footer keys sit 16 px above the bottom and 14 px in from the same row edges, the pager count is
    centred between its keys, the header band, switch and close key keep the mock's 18 px margins and are
    centred on the band;
  * letter: docked 22 px right of the window and 48 px down, flush with its bottom, 440 px wide, three
    equal keys with an 8 px gap and 14 px side margins, wells on a 50 px pitch;
  * send: prompt lines, postage chip, pad, cargo strip (8 px inside margins, 48 px pitch), money segments
    (80 px pitch), the send / c.o.d. switch and the footer keys on the mock's margins;
  * every edge the skin places lands on a whole screen pixel, at 1.2 and at another pixel scale;
  * Blizzard's art is held, its text replaced from the API, and no Blizzard widget gets a script or an
    attribute written;
  * the same pieces rebuild nothing on a second scan, and nothing is built in combat.

Run:

    python3 tools/mailskin-harness.py                       # checks only
    python3 tools/mailskin-harness.py --png /tmp/mail       # also writes /tmp/mail-inbox.png and -send.png

Exit 0 = every check passed. The mock is NOT the real client.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ADDON = Path(__file__).resolve().parent.parent / "forever-stuwave"
SOURCES = {
    name: (ADDON / path).read_text(encoding="utf-8")
    for name, path in {
        "Theme": "Core/Theme.lua",
        "HeldArt": "Core/HeldArt.lua",
        "PanelSkins": "Core/PanelSkins.lua",
        "Mail": "Modules/Skins/Mail.lua",
    }.items()
}
FONT = ADDON / "Media/Fonts/MononokiNerdFontMono-Bold.ttf"

MOCK = r"""
PPU = 1.2
UI_W, UI_H = 2560 / 1.2, 1440 / 1.2
DEGRADED = {}
SlashCmdList = {}
UISpecialFrames = {}
ATTACHMENTS_MAX_SEND = 8
ATTACHMENTS_MAX_RECEIVE = 16
INBOXITEMS_TO_DISPLAY = 7
UNKNOWN = "Unknown"
MAIL_RETURN = "Return to Sender"
__combat = false
function InCombatLockdown() return __combat end

local TIMERS = {}
C_Timer = { After = function(_, fn) TIMERS[#TIMERS + 1] = fn end }
function FlushTimers()
    for _ = 1, 20 do
        if #TIMERS == 0 then return end
        local list = TIMERS
        TIMERS = {}
        for _, fn in ipairs(list) do fn() end
    end
end

-------------------------------------------------------------------------------
-- Widgets
-------------------------------------------------------------------------------

local Obj = {}
Obj.__index = Obj
local ALL = {}
local seq = 0
local LAYER = { BACKGROUND = 1, BORDER = 2, ARTWORK = 3, OVERLAY = 4, HIGHLIGHT = 5 }

local function new(kind, name, parent, blizz)
    seq = seq + 1
    local o = setmetatable({
        kind = kind, fsName = name, parent = parent, seq = seq, blizz = blizz or false, children = {}, regions = {},
        points = {}, shown = true, alpha = 1, scripts = {}, hooks = {}, events = {}, enabled = true, w = 0, h = 0,
        level = parent and ((parent.level or 0) + 1) or 0, layer = "ARTWORK", sub = 0, text = "", size = 12,
        color = nil, vertex = nil, checked = false,
    }, Obj)
    if name then _G[name] = o end
    ALL[#ALL + 1] = o
    return o
end

local REGION = { Texture = true, FontString = true }
local function adopt(parent, o)
    if parent then
        if REGION[o.kind] then parent.regions[#parent.regions + 1] = o else parent.children[#parent.children + 1] = o end
    end
    return o
end

function CreateFrame(kind, name, parent)
    local o = adopt(parent or UIParent, new(kind, name, parent or UIParent, false))
    return o
end
function Obj:CreateTexture(name, layer, template, sub)
    local t = adopt(self, new("Texture", name, self, self.blizz))
    t.layer, t.sub = layer or "ARTWORK", sub or 0
    return t
end
function Obj:CreateFontString(name, layer)
    local f = adopt(self, new("FontString", name, self, self.blizz))
    f.layer = layer or "ARTWORK"
    return f
end

function Obj:GetObjectType() return self.kind end
function Obj:GetName() return self.fsName end
function Obj:GetParent() return self.parent end
function Obj:GetRegions() return unpack(self.regions) end
function Obj:GetChildren() return unpack(self.children) end
function Obj:IsForbidden() return false end
function Obj:IsProtected() return false end
function Obj:GetEffectiveScale() return 1 end
function Obj:SetID(i) self.id = i end
function Obj:GetID() return self.id end

-- visibility and scripts
local function runScript(o, k, ...)
    if o.scripts[k] then o.scripts[k](o, ...) end
    for _, fn in ipairs(o.hooks[k] or {}) do fn(o, ...) end
end
Obj.RunScript = runScript
function Obj:Show()
    local was = self.shown
    self.shown = true
    if not was and not REGION[self.kind] then runScript(self, "OnShow") end
end
function Obj:Hide()
    local was = self.shown
    self.shown = false
    if was and not REGION[self.kind] then runScript(self, "OnHide") end
end
function Obj:SetShown(v) if v then self:Show() else self:Hide() end end
function Obj:IsShown() return self.shown end
function Obj:SetAlpha(a) self.alpha = a end
function Obj:GetAlpha() return self.alpha end
function Obj:SetScript(k, fn)
    if self.blizz then error("SetScript on a Blizzard widget: " .. tostring(self.fsName), 2) end
    self.scripts[k] = fn
end
function Obj:GetScript(k) return self.scripts[k] end
function Obj:HookScript(k, fn)
    self.hooks[k] = self.hooks[k] or {}
    table.insert(self.hooks[k], fn)
end
function Obj:SetAttribute() if self.blizz then error("SetAttribute on a Blizzard widget: " .. tostring(self.fsName), 2) end end
function Obj:RegisterEvent(e) self.events[e] = true end
function Obj:UnregisterEvent(e) self.events[e] = nil end
function Obj:EnableMouse(v) self.mouse = v end
function Obj:SetFrameLevel(l) self.level = l end
function Obj:GetFrameLevel() return self.level end
function Obj:SetHitRectInsets() end
function Obj:SetClipsChildren() end
function Obj:SetScrollChild(c) self.scrollChild = c end
function Obj:Click() runScript(self, "OnClick", "LeftButton") end
function Obj:Enable() local was = self.enabled; self.enabled = true; if not was then runScript(self, "OnEnable") end end
function Obj:Disable() local was = self.enabled; self.enabled = false; if was then runScript(self, "OnDisable") end end
function Obj:SetEnabled(v) if v then self:Enable() else self:Disable() end end
function Obj:IsEnabled() return self.enabled end
function Obj:SetChecked(v) self.checked = v and true or false end
function Obj:GetChecked() return self.checked end
function Obj:SetFocus() end
function Obj:ClearFocus() end

-- text
function Obj:SetFont(path, size, flags) self.fontPath, self.size, self.flags = path, size, flags; return true end
function Obj:GetFont() return self.fontPath, self.size, self.flags end
function Obj:SetFontObject() end
function Obj:SetTextColor(r, g, b, a) self.textColor = { r, g, b, a or 1 } end
function Obj:SetShadowColor() end
function Obj:SetShadowOffset() end
function Obj:SetJustifyH(j) self.justify = j end
function Obj:SetJustifyV() end
function Obj:SetWordWrap() end
function Obj:SetTextInsets() end
function Obj:SetSpacing() end
function Obj:IsTruncated() return false end
function Obj:GetFontString() return self.fs end
function Obj:SetText(t)
    if self.kind == "FontString" and not self.fontPath then error("Font not set", 2) end
    t = t == nil and "" or tostring(t)
    if self.kind == "Button" or self.kind == "CheckButton" then
        if self.fs then self.fs.text = t end
    end
    self.text = t
end
function Obj:GetText()
    if self.fs and (self.kind == "Button" or self.kind == "CheckButton") then return self.fs.text end
    return self.text
end
local function plainLen(text)
    text = tostring(text or ""):gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")
    return #text
end
function Obj:GetStringWidth() return plainLen(self.text) * (self.size or 12) * 0.5615 end
function Obj:GetStringHeight() return (self.size or 12) * 1.2 end
function Obj:SetWidth(w) self.w = w end
function Obj:SetHeight(h) self.h = h end
function Obj:GetWidth() local l, t, r, b = self:Rect(); return r - l end
function Obj:GetHeight() local l, t, r, b = self:Rect(); return b - t end
function Obj:SetSize(w, h) self.w, self.h = w, h end

-- textures
function Obj:SetTexture(path) self.path = path; self.color = nil end
function Obj:GetTexture() return self.path end
function Obj:SetColorTexture(r, g, b, a) self.path = nil; self.color = { r, g, b, a or 1 } end
function Obj:SetVertexColor(r, g, b, a) self.vertex = { r, g, b, a or 1 } end
function Obj:SetTexCoord() end
function Obj:SetBlendMode(m) self.blend = m end
function Obj:SetDrawLayer(layer, sub) self.layer, self.sub = layer, sub or 0 end
function Obj:SetSnapToPixelGrid() end
function Obj:SetTexelSnappingBias() end
function Obj:SetTextureSliceMargins(l) self.slice = l end
function Obj:SetTextureSliceMode() end
function Obj:SetHorizTile() end
function Obj:SetVertTile() end
function Obj:SetDesaturated() end
function Obj:SetAtlas() end
function Obj:SetNormalTexture(path)
    if not self.normalTex then
        self.normalTex = adopt(self, new("Texture", nil, self, self.blizz))
        self.normalTex.layer = "ARTWORK"
    end
    self.normalTex.path = path
    self.normalTex.shown = true
end
function Obj:ClearNormalTexture() if self.normalTex then self.normalTex.path = nil end end
function Obj:GetNormalTexture() return self.normalTex end
function Obj:GetPushedTexture() return self.pushedTex end
function Obj:GetHighlightTexture() return self.highlightTex end
function Obj:GetDisabledTexture() return self.disabledTex end
function Obj:GetCheckedTexture() return self.checkedTex end
function Obj:GetDisabledCheckedTexture() return self.disabledCheckedTex end

-- anchors
function Obj:ClearAllPoints() self.points = {} end
function Obj:SetPoint(point, rel, relPoint, x, y)
    if type(rel) == "number" then x, y, rel, relPoint = rel, relPoint, nil, nil end
    if type(rel) == "string" then error("string anchor " .. rel, 2) end
    -- a point already set is replaced, like the engine
    for i, p in ipairs(self.points) do
        if p.point == point then table.remove(self.points, i) break end
    end
    self.points[#self.points + 1] = { point = point, rel = rel or self.parent, relPoint = relPoint or point, x = x or 0, y = y or 0 }
end
function Obj:SetAllPoints(rel)
    self.points = {}
    local r = rel or self.parent
    self.points[1] = { point = "TOPLEFT", rel = r, relPoint = "TOPLEFT", x = 0, y = 0 }
    self.points[2] = { point = "BOTTOMRIGHT", rel = r, relPoint = "BOTTOMRIGHT", x = 0, y = 0 }
end
function Obj:GetNumPoints() return #self.points end

local function sizeOf(o)
    if o.kind == "FontString" and (o.w == 0 or o.w == nil) then return o:GetStringWidth(), (o.size or 12) * 1.2 end
    return o.w, o.h
end

-- The rectangle of an object in UI units, y running down: left, top, right, bottom.
function Obj:Rect()
    if self == UIParent then return 0, 0, UI_W, UI_H end
    local W, H = sizeOf(self)
    local left, right, cx, top, bottom, cy
    for _, p in ipairs(self.points) do
        local rl, rt, rr, rb = p.rel:Rect()
        local ax, ay
        local rp = p.relPoint
        if rp:find("LEFT") then ax = rl elseif rp:find("RIGHT") then ax = rr else ax = (rl + rr) / 2 end
        if rp:find("TOP") then ay = rt elseif rp:find("BOTTOM") then ay = rb else ay = (rt + rb) / 2 end
        ax, ay = ax + p.x, ay - p.y
        local pt = p.point
        if pt:find("LEFT") then left = ax elseif pt:find("RIGHT") then right = ax else cx = ax end
        if pt:find("TOP") then top = ay elseif pt:find("BOTTOM") then bottom = ay else cy = ay end
    end
    if #self.points == 0 then
        local pl, pt = self.parent:Rect()
        left, top = pl, pt
    end
    if left and right then W = right - left
    elseif left then right = left + W
    elseif right then left = right - W
    elseif cx then left = cx - W / 2; right = left + W
    else left = 0; right = W end
    if top and bottom then H = bottom - top
    elseif top then bottom = top + H
    elseif bottom then top = bottom - H
    elseif cy then top = cy - H / 2; bottom = top + H
    else top = 0; bottom = H end
    return left, top, right, bottom
end

function hooksecurefunc(a, b, c)
    local tbl, name, fn = _G, a, b
    if type(a) == "table" then tbl, name, fn = a, b, c end
    local orig = tbl[name]
    if type(orig) ~= "function" then error("hooksecurefunc: no function " .. tostring(name), 2) end
    tbl[name] = function(...)
        local r = orig(...)
        fn(...)
        return r
    end
end

function CreateFont() return { SetFont = function() end, SetTextColor = function() end, SetShadowColor = function() end } end
function GetCursorPosition() return 0, 0 end
function GetPhysicalScreenSize() return 2560, 1440 end
function print() end

UIParent = new("Frame", "UIParent", nil)

function Fire(event, ...)
    for _, o in ipairs(ALL) do
        if o.events[event] and o.scripts.OnEvent then o.scripts.OnEvent(o, event, ...) end
    end
end

-------------------------------------------------------------------------------
-- Blizzard's mailbox, as the 16001 globals dump names it
-------------------------------------------------------------------------------

local function blz(kind, name, parent, w, h, point)
    local o = adopt(parent, new(kind, name, parent, true))
    o.w, o.h = w or 0, h or 0
    o.points[1] = { point = point or "TOPLEFT", rel = parent, relPoint = point or "TOPLEFT", x = 0, y = 0 }
    return o
end
local function tex(parent, name, layer)
    local t = adopt(parent, new("Texture", name, parent, true))
    t.layer = layer or "BACKGROUND"
    t.path = "Interface\\stock\\art"
    return t
end
local function fstring(parent, name, text, size)
    local f = adopt(parent, new("FontString", name, parent, true))
    f.fontPath, f.size, f.text = "stock.ttf", size or 12, text or ""
    f.textColor = { 1, 0.82, 0, 1 }
    f.points[1] = { point = "TOPLEFT", rel = parent, relPoint = "TOPLEFT", x = 0, y = 0 }
    return f
end
-- a stock text button: UIPanelButtonTemplate keeps its art in Left, Middle and Right and has a Text
local function textButton(parent, name, text, w, h)
    local b = blz("Button", name, parent, w, h)
    b.Left, b.Middle, b.Right = tex(b, nil, "BACKGROUND"), tex(b, nil, "BACKGROUND"), tex(b, nil, "BACKGROUND")
    b.fs = fstring(b, name .. "Text", text, 12)
    b.pushedTex, b.highlightTex = tex(b, nil, "HIGHLIGHT"), tex(b, nil, "HIGHLIGHT")
    return b
end
local function editBox(parent, name, label, w, h)
    local e = blz("EditBox", name, parent, w, h)
    tex(e, name .. "Left", "BACKGROUND"); tex(e, name .. "Middle", "BACKGROUND"); tex(e, name .. "Right", "BACKGROUND")
    -- 16001 lists the FontString that draws the typed text among an EditBox's regions
    e.display = fstring(e, nil, "", 12)
    if label then e.caption = fstring(e, nil, label, 12) end
    e.fontPath, e.size = "stock.ttf", 12
    return e
end
local function itemButton(parent, name, w, h, iconKey)
    local b = blz("Button", name, parent, w, h)
    tex(b, nil, "BACKGROUND")
    if iconKey then b.icon = tex(b, name .. iconKey, "ARTWORK") end
    tex(b, name .. "NormalTexture", "ARTWORK")
    b.count = fstring(b, name .. "Count", "", 12)
    fstring(b, name .. "Stock", "", 12)
    return b
end

INBOX = {}
OPEN = {}
SEND = { items = {}, price = 30, money = 14239 }

function BuildBlizzard()
    for k in pairs(_G) do
        if type(k) == "string" and (k:find("^MailItem") or k:find("^OpenMail") or k:find("^SendMail")) then _G[k] = nil end
    end
    local M = blz("Frame", "MailFrame", UIParent, 338, 424)
    M.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 250, y = -100 }
    M.shown = false
    tex(M, "MailFrameBg", "BACKGROUND"); tex(M, "MailFramePortrait", "ARTWORK")
    fstring(M, "MailFrameTitleText", "Inbox")
    blz("Frame", "MailFrameInset", M, 330, 360).Bg = nil
    tex(_G.MailFrameInset, nil, "BACKGROUND")
    local close = blz("Button", "MailFrameCloseButton", M, 24, 24, "TOPRIGHT")
    tex(close, nil, "BACKGROUND")
    for i = 1, 2 do
        local tab = blz("Button", "MailFrameTab" .. i, M, 90, 32, "BOTTOMLEFT")
        tab.fs = fstring(tab, "MailFrameTab" .. i .. "Text", i == 1 and "Inbox" or "Send Mail")
        tex(tab, nil, "BACKGROUND")
        tab.scripts.OnClick = function() MailTab(i) end
    end

    local inbox = blz("Frame", "InboxFrame", M, 384, 512)
    tex(inbox, "InboxFrameBg", "BACKGROUND")
    fstring(inbox, "InboxCurrentPage", "Page 1")
    InboxPrevPageMixin = { OnClick = function() end, Update = function() end }
    InboxNextPageMixin = { OnClick = function() end, Update = function() end }
    for _, spec in ipairs({ { "InboxPrevPageMixin" }, { "InboxNextPageMixin" } }) do
        local b = blz("Button", nil, inbox, 32, 32)
        tex(b, nil, "BACKGROUND")
        -- the 16001 pager draws its Prev / Next caption as a template FontString, not the button's own text
        b.caption = fstring(b, nil, spec[1] == "InboxPrevPageMixin" and "Prev" or "Next")
        for k, v in pairs(_G[spec[1]]) do rawset(b, k, v) end
        if spec[1] == "InboxPrevPageMixin" then inbox.prev = b else inbox.next = b end
    end
    local too = blz("Frame", "InboxTooMuchMail", inbox, 384, 32)
    too.shown = false
    fstring(too, "InboxTooMuchMailText", "Too much mail")
    inbox.pageNum = 1

    for i = 1, 7 do
        local row = blz("Frame", "MailItem" .. i, inbox, 305, 45)
        tex(row, nil, "BACKGROUND"); tex(row, nil, "BACKGROUND")
        fstring(row, "MailItem" .. i .. "Sender", "")
        fstring(row, "MailItem" .. i .. "Subject", "")
        local expire = blz("Button", "MailItem" .. i .. "ExpireTime", row, 100, 16, "TOPRIGHT")
        expire.caption = fstring(expire, nil, "30 Days")
        local b = blz("CheckButton", "MailItem" .. i .. "Button", row, 37, 37)
        b.shown = false
        tex(b, "MailItem" .. i .. "ButtonSlot", "BACKGROUND")
        tex(b, "MailItem" .. i .. "ButtonIcon", "ARTWORK")
        tex(b, "MailItem" .. i .. "ButtonIconBorder", "OVERLAY")
        tex(b, "MailItem" .. i .. "ButtonCODBackground", "OVERLAY")
        fstring(b, "MailItem" .. i .. "ButtonCOD", "COD")
        fstring(b, "MailItem" .. i .. "ButtonCount", "")
        b.checkedTex = tex(b, nil, "OVERLAY")
        b.scripts.OnClick = function(self)
            InboxFrame.openMailID = self.index
            for n = 1, 7 do _G["MailItem" .. n .. "Button"]:SetChecked(n == i) end
            OpenMailUpdate()
        end
    end
    local open = textButton(inbox, "OpenAllMail", "Open All Mail", 120, 25)
    open.points[1] = { point = "BOTTOMRIGHT", rel = inbox, relPoint = "BOTTOMRIGHT", x = -10, y = 90 }

    -- the send page
    local send = blz("Frame", "SendMailFrame", M, 384, 512)
    send.shown = false
    tex(send, "SendMailHorizontalBarLeft", "BACKGROUND"); tex(send, "SendMailHorizontalBarLeft2", "BACKGROUND")
    fstring(send, "SendMailErrorText", "")
    tex(send, "SendMailErrorCoin", "ARTWORK")
    blz("Frame", "SendMailMoneyInset", send, 300, 30); tex(_G.SendMailMoneyInset, nil, "BACKGROUND")
    blz("Frame", "SendMailMoneyBg", send, 300, 30)
    local cost = blz("Frame", "SendMailCostMoneyFrame", send, 120, 16)
    fstring(cost, nil, "Postage:")
    blz("Frame", "SendMailMoneyFrame", send, 150, 16)
    editBox(send, "SendMailNameEditBox", "To:", 150, 20)
    editBox(send, "SendMailSubjectEditBox", "Subject:", 250, 20)
    local scroll = blz("ScrollFrame", "SendMailScrollFrame", send, 290, 150)
    tex(scroll, "SendStationeryBackgroundLeft", "BACKGROUND"); tex(scroll, "SendStationeryBackgroundRight", "BACKGROUND")
    blz("Frame", "SendMailScrollChildFrame", scroll, 287, 20)
    editBox(_G.SendMailScrollChildFrame, "SendMailBodyEditBox", nil, 287, 20)
    for i = 1, 16 do
        local b = itemButton(send, "SendMailAttachment" .. i, 37, 37, nil)
        b.shown = i <= ATTACHMENTS_MAX_SEND
        b.points[1] = { point = "TOPLEFT", rel = send, relPoint = "TOPLEFT", x = 10 + (i - 1) * 40, y = -300 }
    end
    local mb = blz("Frame", "SendMailMoneyButton", send, 300, 60)
    fstring(mb, "SendMailMoneyText", "Amount to send:")
    local mi = blz("Frame", "SendMailMoney", mb, 200, 20)
    for _, n in ipairs({ "Gold", "Silver", "Copper" }) do editBox(mi, "SendMailMoney" .. n, nil, 80, 20); tex(_G["SendMailMoney" .. n], nil, "ARTWORK") end
    for i, n in ipairs({ "SendMailSendMoneyButton", "SendMailCODButton" }) do
        local r = blz("CheckButton", n, mb, 20, 20)
        r.fs = fstring(r, n .. "Text", i == 1 and "Send Money" or "C.O.D.")
        r.checkedTex, r.disabledCheckedTex = tex(r, nil, "ARTWORK"), tex(r, nil, "ARTWORK")
        tex(r, nil, "BACKGROUND")
        r.scripts.OnClick = function(self)
            SendMailSendMoneyButton:SetChecked(i == 1)
            SendMailCODButton:SetChecked(i == 2)
        end
    end
    SendMailSendMoneyButton.checked = true
    textButton(send, "SendMailCancelButton", "Cancel", 80, 22)
    textButton(send, "SendMailMailButton", "Send", 80, 22)

    -- the open letter
    local O = blz("Frame", "OpenMailFrame", UIParent, 345, 408)
    O.points[1] = { point = "TOPLEFT", rel = inbox, relPoint = "TOPRIGHT", x = -14, y = 0 }
    O.shown = false
    tex(O, "OpenMailFrameBg", "BACKGROUND"); tex(O, "OpenMailFramePortrait", "ARTWORK")
    fstring(O, "OpenMailFrameTitleText", "")
    blz("Frame", "OpenMailFrameInset", O, 330, 200)
    blz("Button", "OpenMailFrameCloseButton", O, 24, 24, "TOPRIGHT")
    fstring(O, "OpenMailSenderLabel", "From:"); fstring(O, "OpenMailSubjectLabel", "Subject:")
    local sender = blz("Frame", "OpenMailSender", O, 200, 18)
    sender.Name = fstring(sender, nil, "")
    fstring(O, "OpenMailSubject", "")
    fstring(O, "OpenMailAttachmentText", "Attachments:")
    tex(O, "OpenMailHorizontalBarLeft", "ARTWORK"); tex(O, "OpenMailArithmeticLine", "ARTWORK")
    local sc = blz("ScrollFrame", "OpenMailScrollFrame", O, 290, 180)
    tex(sc, "OpenStationeryBackgroundLeft", "BACKGROUND"); tex(sc, "OpenStationeryBackgroundRight", "BACKGROUND")
    blz("Frame", "OpenMailScrollChildFrame", sc, 270, 20)
    local body = blz("SimpleHTML", "OpenMailBodyText", _G.OpenMailScrollChildFrame, 270, 20)
    function body:SetFont(element, path, size) self.fonts = self.fonts or {}; self.fonts[element] = { path, size } end
    for i = 1, 16 do
        local b = itemButton(O, "OpenMailAttachmentButton" .. i, 37, 37, "IconTexture")
        b.shown = false
    end
    local letter = itemButton(O, "OpenMailLetterButton", 37, 37, "IconTexture"); letter.shown = false
    local money = itemButton(O, "OpenMailMoneyButton", 37, 37, "IconTexture"); money.shown = false
    textButton(O, "OpenMailReplyButton", "Reply", 80, 22)
    textButton(O, "OpenMailDeleteButton", "Delete", 80, 22)
    textButton(O, "OpenMailReportSpamButton", "Report Spam", 80, 22).shown = false
    textButton(O, "OpenMailCancelButton", "Close", 80, 22)
    local inv = blz("Frame", "OpenMailInvoiceFrame", sc, 270, 100)
    inv.shown = false
    for _, n in ipairs({ "ItemLabel", "Purchaser", "SalePrice" }) do fstring(inv, "OpenMailInvoice" .. n, "x") end

    function MailTab(i)
        SendMailFrame:SetShown(i == 2)
        InboxFrame:SetShown(i == 1)
        MailFrameTitleText:SetText(i == 1 and "Inbox" or "Send Mail")
    end
    function InboxUpdate()
        local n = #INBOX
        for i = 1, INBOXITEMS_TO_DISPLAY do
            local idx = (InboxFrame.pageNum - 1) * INBOXITEMS_TO_DISPLAY + i
            local b = _G["MailItem" .. i .. "Button"]
            if idx <= n then
                local d = INBOX[idx]
                b:Show()
                b.index = idx
                _G["MailItem" .. i .. "Subject"]:SetText(d.subject)
                _G["MailItem" .. i .. "Sender"]:SetText(d.sender)
                _G["MailItem" .. i .. "Sender"]:SetTextColor(1, 0.82, 0)
                _G["MailItem" .. i .. "ExpireTime"]:SetText("29d")
                b:SetChecked(InboxFrame.openMailID == idx)
            else
                b:Hide()
                _G["MailItem" .. i .. "Sender"]:SetText("")
                _G["MailItem" .. i .. "Subject"]:SetText("")
            end
        end
    end
    function OpenMailUpdate()
        local d = INBOX[InboxFrame.openMailID]
        if not d then return end
        OpenMailSender.Name:SetText(d.sender)
        OpenMailSubject:SetText(d.subject)
        OpenMailFrame:Show()
        for i = 1, 16 do _G["OpenMailAttachmentButton" .. i]:SetShown(i <= (d.attach or 0)) end
        OpenMailMoneyButton:SetShown((d.money or 0) > 0)
        OpenMailDeleteButton:SetText(d.canDelete == false and MAIL_RETURN or "Delete")
        OpenMailReportSpamButton:SetShown(d.spam == true)
        OpenMailReplyButton:SetEnabled(d.canReply ~= false)
    end
    function SendMailFrame_Update()
        for i = 1, ATTACHMENTS_MAX_SEND do
            local b = _G["SendMailAttachment" .. i]
            if SEND.items[i] then b:SetNormalTexture("Interface\\Icons\\x"); b.count:SetText("2") else b:ClearNormalTexture(); b.count:SetText("") end
            -- the stock update re-anchors every slot to its own grid (MailFrame.lua)
            b:SetPoint("TOPLEFT", SendMailFrame, "BOTTOMLEFT", 20 + i * 40, 120)
        end
    end
    function OpenMail_Update() OpenMailUpdate() end
    OpenMailFrame.scripts.OnShow = nil
    MailFrame.scripts.OnShow = function() InboxUpdate() end
    InboxFrame.scripts.OnShow = function() InboxUpdate() end
    OpenMailFrame.points[1] = { point = "TOPLEFT", rel = InboxFrame, relPoint = "TOPRIGHT", x = -14, y = 0 }
end

function GetInboxNumItems() return #INBOX, #INBOX end
function GetInboxHeaderInfo(i)
    local d = INBOX[i]
    if not d then return nil end
    return "pkg", "stat", d.sender, d.subject, d.money or 0, d.cod or 0, d.days, d.attach or 0, d.read or false,
        false, true, true, false
end
function GetMoney() return SEND.money end
function GetSendMailPrice() return SEND.price end
function HasSendMailItem(i) return SEND.items[i] ~= nil end
AUTOLOOT = {}
function AutoLootMailItem(i) AUTOLOOT[#AUTOLOOT + 1] = i end

INBOX = {
    { sender = "Stu Moolah", subject = "Thunder Lizard Tail (2)", money = 12 * 100, days = 28, attach = 2, read = false },
    { sender = "Auction House", subject = "Auction successful: Linen", money = 41000, days = 1.2, attach = 0, read = true },
    { sender = "Gnome Mailer", subject = "Goods for you", cod = 50000, days = 0.12, attach = 1, read = false },
    { sender = "Thrall", subject = "Re: totems", days = 6, attach = 0, read = true, canDelete = false },
}

-------------------------------------------------------------------------------
-- Loading the addon files
-------------------------------------------------------------------------------

function Load(opts)
    opts = opts or {}
    FS = { LogDegradeOnce = function(key, msg) DEGRADED[#DEGRADED + 1] = key .. " :: " .. tostring(msg) end }
    FS.FrameHelpers = { PixelsPerUnit = function() return PPU end }
    FS.Layout = { Scale = function() return 1 end }
    for _, name in ipairs({ "Theme", "HeldArt", "PanelSkins", "Mail" }) do
        local chunk, err = load(SOURCES[name], "=" .. name .. ".lua")
        if not chunk then error(err) end
        chunk("forever-stuwave", FS)
    end
    return FS
end

-- Opens the inbox the way the client does: MailFrame shown, rows repopulated.
function ShowInbox(openIndex)
    MailFrame:Show()
    InboxFrame:Show()
    FlushTimers()
    if openIndex then
        _G["MailItem" .. openIndex .. "Button"]:Click()
    end
    FlushTimers()
end
function ShowSend(items)
    SEND.items = items or {}
    MailFrame:Show()
    MailTab(2)
    SendMailFrame_Update()
    FlushTimers()
end
function Reset()
    for i = #ALL, 2, -1 do ALL[i] = nil end
    TIMERS = {}
    DEGRADED = {}
    __combat = false
    PPU = 1.2
    UISpecialFrames = {}
    ATTACHMENTS_MAX_SEND = 8
    UIParent.children, UIParent.regions = {}, {}
    BuildBlizzard()
end

-------------------------------------------------------------------------------
-- Measuring
-------------------------------------------------------------------------------

-- Rectangle of `o` in physical pixels relative to the top left of `ref`.
function Px(o, ref)
    local l, t, r, b = o:Rect()
    local rl, rt = ref:Rect()
    return (l - rl) * PPU, (t - rt) * PPU, (r - rl) * PPU, (b - rt) * PPU
end
function Near(a, b, tol) return math.abs(a - b) <= (tol or 0.01) end
function Expect(o, ref, l, t, w, h, what)
    local pl, pt, pr, pb = Px(o, ref)
    assert(Near(pl, l) and Near(pt, t) and Near(pr - pl, w) and Near(pb - pt, h), string.format(
        "%s: x=%.2f y=%.2f w=%.2f h=%.2f, wanted x=%s y=%s w=%s h=%s", what, pl, pt, pr - pl, pb - pt, l, t, w, h))
end
function CenterOf(o, ref)
    local l, t, r, b = Px(o, ref)
    return (l + r) / 2, (t + b) / 2
end
function Mine() return FS.MailSkin.state end
function ObjCount() return #ALL end
function HookCount()
    local n = 0
    for _, o in ipairs(ALL) do
        for _, list in pairs(o.hooks) do n = n + #list end
    end
    return n
end

-- Ops for the renderer, in draw order.
local function visible(o)
    while o do
        if o.shown == false then return false end
        o = o.parent
    end
    return true
end
local function alphaOf(o)
    local a = 1
    while o do a = a * (o.alpha or 1); o = o.parent end
    return a
end
function DumpOps(roots)
    local ops = {}
    local function region(o)
        if not visible(o) then return end
        local a = alphaOf(o)
        if a <= 0 then return end
        local l, t, r, b = Px(o, UIParent)
        if o.kind == "Texture" then
            local c = o.color or o.vertex
            if o.path and o.path:find("slice_cut2") then
                local kind = o.path:find("glow") and "glow" or (o.path:find("outline") or o.path:find("border")) and "ring" or "fill"
                if kind ~= "glow" and o.vertex then
                    ops[#ops + 1] = { kind = kind, l = l, t = t, r = r, b = b, c = o.slice or 4, rgba = { o.vertex[1], o.vertex[2], o.vertex[3], o.vertex[4] * a } }
                end
            elseif o.color then
                ops[#ops + 1] = { kind = "flat", l = l, t = t, r = r, b = b, rgba = { o.color[1], o.color[2], o.color[3], o.color[4] * a } }
            elseif o.path and o.path:find("Icons") then
                ops[#ops + 1] = { kind = "flat", l = l, t = t, r = r, b = b, rgba = { 0.78, 0.63, 0.31, a } }
            end
        elseif o.kind == "FontString" and o.text and o.text ~= "" then
            local tc = o.textColor or { 1, 1, 1, 1 }
            ops[#ops + 1] = { kind = "text", l = l, t = t, r = r, b = b, text = o.text, size = (o.size or 12) * PPU,
                rgba = { tc[1], tc[2], tc[3], (tc[4] or 1) * a }, justify = o.justify or "LEFT" }
        end
    end
    -- the engine draws every frame of a strata in (frame level, creation) order, whatever the tree says,
    -- so flatten the visible frames and sort them that way
    local frames = {}
    local function collect(f)
        if not visible(f) then return end
        frames[#frames + 1] = f
        for _, c in ipairs(f.children) do collect(c) end
    end
    local function draw(f)
        local regions = {}
        for _, r in ipairs(f.regions) do regions[#regions + 1] = r end
        table.sort(regions, function(x, y)
            local lx, ly = LAYER[x.layer] or 3, LAYER[y.layer] or 3
            if lx ~= ly then return lx < ly end
            if (x.sub or 0) ~= (y.sub or 0) then return (x.sub or 0) < (y.sub or 0) end
            return x.seq < y.seq
        end)
        for _, r in ipairs(regions) do region(r) end
    end
    for _, r in ipairs(roots) do collect(r) end
    table.sort(frames, function(x, y)
        if x.level ~= y.level then return x.level < y.level end
        return x.seq < y.seq
    end)
    for _, f in ipairs(frames) do draw(f) end
    return ops
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


def run_case(body: str):
    rt = LuaRuntime(unpack_returned_tuples=False)
    for key, src in SOURCES.items():
        rt.globals()["SRC_" + key] = src
    try:
        rt.execute("SOURCES = { Theme = SRC_Theme, HeldArt = SRC_HeldArt, PanelSkins = SRC_PanelSkins, Mail = SRC_Mail }")
        rt.execute(MOCK)
        rt.execute("BuildBlizzard()\nlocal function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc), None
    return None, rt


PRELUDE = """
    local FS = Load()
    ShowInbox()
    Fire("PLAYER_ENTERING_WORLD")
    ShowInbox()
    assert(#DEGRADED == 0, "degraded: " .. table.concat(DEGRADED, " | "))
    local S = Mine()
    local W = MailFrame
"""

case("the_window_is_432_by_670_and_every_placed_edge_is_a_whole_pixel", PRELUDE + """
    Expect(W, W, 0, 0, 432, 670, "window")
    local n = 0
    for obj, p in pairs(S.placed) do
        if obj.kind ~= "FontString" then
            local l, t, r, b = Px(obj, W)
            for _, v in ipairs({ l, t, r, b }) do
                assert(Near(v, math.floor(v + 0.5), 0.001), string.format("%s %s edge %.4f is not a whole pixel",
                    obj.kind, tostring(obj.fsName), v))
            end
            n = n + 1
        end
    end
    assert(n > 80, "only " .. n .. " placed objects were measured")
""")

case("inbox_rows_are_404_by_68_with_a_14_px_margin_both_sides_and_a_10_px_gap", PRELUDE + """
    for i = 1, 7 do
        Expect(S.rows[i].row, W, 14, 62 + (i - 1) * 78, 404, 68, "row " .. i)
        Expect(S.rows[i].card, W, 14, 62 + (i - 1) * 78, 404, 68, "card " .. i)
    end
    local _, _, r1 = Px(S.rows[1].row, W)
    assert(Near(432 - r1, 14), "right margin " .. (432 - r1))
    local _, _, _, b7 = Px(S.rows[7].row, W)
    assert(Near(b7, 598), "last row bottom " .. b7)
    -- the item button is the whole card
    for i = 1, 7 do
        Expect(S.rows[i].button, W, 14, 62 + (i - 1) * 78, 404, 68, "item button " .. i)
    end
""")

case("the_footer_keys_share_the_row_edges_and_sit_16_px_above_the_bottom", PRELUDE + """
    local f = S.footer
    Expect(f.rule, W, 14, 612, 404, 1, "footer rule")
    Expect(f.prev, W, 14, 624, 34, 30, "prev key")
    Expect(f.nxt, W, 108, 624, 34, 30, "next key")
    Expect(f.open, W, 270, 624, 148, 30, "open all key")
    local _, _, _, b = Px(f.open, W)
    assert(Near(670 - b, 16), "bottom margin " .. (670 - b))
    local cx, cy = CenterOf(f.count, W)
    local pl, _, pr = Px(f.prev, W)
    local nl = Px(f.nxt, W)
    assert(Near(cx, (pr + nl) / 2, 0.5), "count centre " .. cx)
    assert(Near(cy, 639, 0.5), "count centre y " .. cy)
    -- rows end 14 px above the rule
    local _, _, _, rowsBottom = Px(S.rows[7].row, W)
    assert(Near(612 - rowsBottom, 14), "rows to rule " .. (612 - rowsBottom))
""")

case("pager_keys_are_found_by_shape_when_the_mixins_are_gone", """
    -- a build whose mixin tables and copied methods differ: no names, no handlers, only two small buttons in the inbox
    InboxPrevPageMixin, InboxNextPageMixin = nil, nil
    for _, b in ipairs({ InboxFrame.prev, InboxFrame.next }) do b.OnClick = nil; b.Update = nil end
    local FS = Load()
    ShowInbox()
    Fire("PLAYER_ENTERING_WORLD")
    ShowInbox()
    local S, W = Mine(), MailFrame
    assert(S.footer.prev == InboxFrame.prev and S.footer.nxt == InboxFrame.next, "pagers not found by shape")
    Expect(S.footer.prev, W, 14, 624, 34, 30, "prev key")
    Expect(S.footer.nxt, W, 108, 624, 34, 30, "next key")
    assert(InboxFrame.prev.caption.alpha == 0 and InboxFrame.next.caption.alpha == 0, "pager captions")
    assert(S.keys[InboxFrame.prev] and S.keys[InboxFrame.next], "pagers are not keys")
    assert(#DEGRADED == 0, "degraded: " .. table.concat(DEGRADED, " | "))
""")

case("one_pager_found_by_mixin_leaves_the_other_to_the_shape_scan", """
    InboxPrevPageMixin = nil
    InboxFrame.prev.OnClick = nil; InboxFrame.prev.Update = nil
    local FS = Load()
    ShowInbox()
    Fire("PLAYER_ENTERING_WORLD")
    ShowInbox()
    local S = Mine()
    assert(S.footer.prev == InboxFrame.prev and S.footer.nxt == InboxFrame.next, "prev not found by shape beside a mixin next")
    assert(#DEGRADED == 0, "degraded: " .. table.concat(DEGRADED, " | "))
""")

case("a_stray_small_button_keeps_the_pagers_stock_instead_of_guessing", """
    InboxPrevPageMixin, InboxNextPageMixin = nil, nil
    for _, b in ipairs({ InboxFrame.prev, InboxFrame.next }) do b.OnClick = nil; b.Update = nil end
    local stray = CreateFrame("Button", nil, InboxFrame)
    stray:SetSize(20, 20)
    local FS = Load()
    ShowInbox()
    Fire("PLAYER_ENTERING_WORLD")
    ShowInbox()
    local S = Mine()
    assert(S.footer.prev == nil and S.footer.nxt == nil, "a pager was guessed from an ambiguous shape")
    assert(InboxFrame.prev.caption.alpha == 1 and not S.keys[InboxFrame.prev], "a stock pager was skinned anyway")
    assert(S.footer.open, "the rest of the footer must still be built")
    assert(#DEGRADED == 0, "degraded: " .. table.concat(DEGRADED, " | "))
""")

case("the_header_band_switch_and_close_key_keep_the_mocks_margins_and_are_centred", PRELUDE + """
    local h = S.header
    Expect(h.band[3], W, 1, 48, 430, 1, "header rule")
    local sw = h.switch
    Expect(sw.plate, W, 206, 10, 170, 28, "switch plate")
    Expect(sw.segs[1].button, W, 209, 13, 80, 22, "inbox segment")
    Expect(sw.segs[2].button, W, 293, 13, 80, 22, "send segment")
    Expect(h.close, W, 386, 10, 28, 28, "close key")
    local _, cy = CenterOf(sw.plate, W)
    assert(Near(cy, 24), "switch centre " .. cy)
    local _, ccy = CenterOf(h.close, W)
    assert(Near(ccy, 24), "close centre " .. ccy)
    local _, ty = CenterOf(h.title, W)
    assert(Near(ty, 24, 0.5), "title centre " .. ty)
    local tl = Px(h.title, W)
    assert(Near(tl, 52), "title x " .. tl)
    -- the envelope and the close key keep the same 18 px margin from their side
    local el = Px(h.env[1], W)
    local _, _, cr = Px(h.close, W)
    assert(Near(el, 18) and Near(432 - cr, 18), "margins " .. el .. " / " .. (432 - cr))
    -- the envelope is centred on the band
    local el1, et, er, eb = Px(h.env[1], W)
    local minT, maxB = 1e9, -1e9
    for _, t in ipairs(h.env) do local _, a, _, b = Px(t, W); minT = math.min(minT, a); maxB = math.max(maxB, b) end
    assert(Near((minT + maxB) / 2, 24), "envelope centre " .. (minT + maxB) / 2)
    -- segment labels sit on their segment centres
    for i = 1, 2 do
        local lx, ly = CenterOf(sw.segs[i].label, W)
        local sx, sy = CenterOf(sw.segs[i].button, W)
        assert(Near(lx, sx, 0.5) and Near(ly, sy, 0.5), "segment label " .. i)
    end
""")

case("a_letter_card_keeps_the_mocks_inner_spacing", PRELUDE + """
    local r = S.rows[1]
    Expect(r.led, r.card, 12, 15, 8, 8, "led")
    local sl = Px(r.sender, r.card)
    assert(Near(sl, 32), "sender x " .. sl)
    local _, _, ar = Px(r.age, r.card)
    assert(Near(404 - ar, 12), "age right inset " .. (404 - ar))
    -- chips: 20 px tall, 35 px down, 6 px apart, flush with the age's right edge
    local c1, c2 = r.chips[1], r.chips[2]
    local l1, t1, r1, b1 = Px(c1, r.card)
    local l2, t2, r2, b2 = Px(c2, r.card)
    assert(Near(b1 - t1, 20) and Near(t1, 35), "chip rect")
    assert(Near(r2, 392), "rightmost chip edge " .. r2)
    assert(Near(l2 - r1, 6), "chip gap " .. (l2 - r1))
    local _, cy = CenterOf(c1.fsLabel, r.card)
    assert(Near(cy, 45, 0.5), "chip label centre " .. cy)
    local _, sy = CenterOf(r.sender, r.card)
    assert(Near(sy, 19, 0.5), "sender line centre " .. sy)
""")

case("rows_read_the_mailbox_api_and_paint_unread_and_the_selected_card", PRELUDE + """
    local r = S.rows[1]
    assert(r.sender.text == "Stu Moolah" and r.subject.text == "Thunder Lizard Tail (2)", "text")
    assert(r.age.text == "28d", "age " .. r.age.text)
    assert(r.chips[1].fsLabel.text == "x2" and r.chips[2].fsLabel.text == "12s", "chips")
    assert(r.chips[3]:IsShown() == false, "third chip")
    -- the led is pink while unread and dim once read
    assert(r.led.color[1] > 0.9 and r.led.color[2] < 0.3, "unread led")
    assert(S.rows[2].led.color[1] < 0.3, "read led")
    assert(S.rows[3].chips[2].fsLabel.text == "COD 5g" and S.rows[3].age.text == "2h", "cod row " .. S.rows[3].age.text)
    assert(S.rows[2].chips[1].fsLabel.text == "4g 10s" and S.rows[2].age.text == "1d", "money row")
    assert(S.rows[4].chips[1]:IsShown() == false, "no chips on a plain letter")
    -- rows past the last letter are not drawn
    assert(S.rows[5].card:IsShown() == false, "empty row drawn")
    -- selecting a letter paints its card cyan, shows the bracket and opens the panel
    ShowInbox(1)
    assert(S.rows[1].shape.ring.vertex[2] > 0.8 and S.rows[1].shape.ring.vertex[3] > 0.9, "selected ring")
    assert(S.rows[2].shape.ring.vertex[1] < 0.3, "plain ring")
    assert(S.bracket.line:IsShown() and S.bracket.knob:IsShown(), "bracket")
    local ll, lt, lr, lb = Px(S.bracket.line, W)
    assert(Near(ll, 418) and Near(lr, 450) and Near(lb - lt, 2), "bracket line " .. ll .. " " .. lr)
    -- the knob is 10 px square and ends flush with the open letter's left edge, centred on the line
    local kl, kt, kr, kb = Px(S.bracket.knob, W)
    assert(Near(kr, 454) and Near(kr - kl, 10) and Near(kb - kt, 10), "bracket knob " .. kl .. " " .. kr)
    assert(Near((kt + kb) / 2, (lt + lb) / 2), "knob centred on the line")
    local _, ly = CenterOf(S.bracket.line, W)
    assert(Near(ly, 62 + 34, 0.01), "bracket y " .. ly)
    ShowInbox(2)
    assert(S.rows[2].shape.ring.vertex[2] > 0.8 and S.rows[1].shape.ring.vertex[1] < 0.3, "selection moved")
""")

case("the_letter_panel_docks_22_px_right_and_48_px_down_and_ends_with_the_window", PRELUDE + """
    ShowInbox(1)
    local O = OpenMailFrame
    Expect(O, W, 454, 48, 440, 622, "letter panel")
    local L = S.letter
    Expect(L.pad, O, 14, 88, 412, 248, "body pad")
    local pl, _, pr = Px(L.pad, O)
    assert(Near(pl, 440 - pr), "pad side margins " .. pl .. " / " .. (440 - pr))
    Expect(L.take, O, 14, 436, 412, 46, "take all")
    local reply, delete = OpenMailReplyButton, OpenMailDeleteButton
    -- two attachments and a money chip are laid on the package row; the report key is hidden: two keys
    local rl, rt, rr, rb = Px(reply, O)
    local dl, dt, dr, db = Px(delete, O)
    assert(Near(rt, 496) and Near(rb - rt, 36), "key row " .. rt)
    assert(Near(rl, 14) and Near(dr, 426), "key edges " .. rl .. " " .. dr)
    assert(Near(rr - rl, dr - dl) and Near(dl - rr, 8), "two equal keys with an 8 px gap")
    -- two wells and the money chip
    local a1, a2 = OpenMailAttachmentButton1, OpenMailAttachmentButton2
    Expect(a1, O, 18, 374, 44, 44, "well 1")
    Expect(a2, O, 68, 374, 44, 44, "well 2")
    Expect(OpenMailMoneyButton, O, 124, 374, 120, 44, "money chip")
    -- a stock icon is 30 px inset 7
    Expect(OpenMailAttachmentButton1IconTexture, a1, 7, 7, 30, 30, "icon")
    local _, _, _, ab = Px(a1, O)
    assert(Near(436 - ab, 18), "wells to take all " .. (436 - ab))
""")

case("three_letter_keys_are_equal_width_and_evenly_spaced", PRELUDE + """
    INBOX[1].spam = true
    ShowInbox(1)
    local O = OpenMailFrame
    local x = {}
    for i, name in ipairs({ "OpenMailReplyButton", "OpenMailDeleteButton", "OpenMailReportSpamButton" }) do
        local l, t, r, b = Px(_G[name], O)
        x[i] = { l, r, t, b }
        assert(Near(r - l, 132), name .. " width " .. (r - l))
    end
    assert(Near(x[1][1], 14) and Near(x[3][2], 426), "outer edges")
    assert(Near(x[2][1] - x[1][2], 8) and Near(x[3][1] - x[2][2], 8), "gaps")
    -- a letter that can only be returned takes the amber accent and the label follows the stock text
    INBOX[1].spam = nil
""")

case("a_text_only_letter_has_no_package_row_and_a_disabled_take_all", PRELUDE + """
    ShowInbox(4)
    local O = OpenMailFrame
    local L = S.letter
    assert(L.package:IsShown() == false, "package label on a text letter")
    assert(L.take:IsEnabled() == false, "take all enabled with nothing to take")
    Expect(L.pad, O, 14, 88, 412, 436 - 18 - 88, "pad grows over the empty package row")
    assert(OpenMailDeleteButton:GetText() == MAIL_RETURN, "stock text")
    local k = S.keys[OpenMailDeleteButton]
    assert(k.accent[1] > 0.9 and k.accent[2] > 0.6 and k.accent[3] < 0.4, "return is amber")
    ShowInbox(2)
    assert(S.keys[OpenMailDeleteButton].accent[1] > 0.9 and S.keys[OpenMailDeleteButton].accent[2] < 0.3, "delete is pink")
""")

case("take_all_loots_the_open_letter_through_the_stock_api", PRELUDE + """
    ShowInbox(1)
    assert(S.letter.take:IsEnabled(), "take all disabled")
    S.letter.take.scripts.OnClick()
    assert(AUTOLOOT[1] == 1, "AutoLootMailItem not called with the open letter")
""")

case("an_auction_invoice_opens_as_our_receipt_ledger", PRELUDE + """
    function GetInboxInvoiceInfo(i)
        return "seller", "Bolt of Woolen Cloth", "Cuddly Cow", 1467, 0, 100, 73, 0, nil, nil, 3
    end
    ShowInbox(1)
    local r = S.letter.receipt
    assert(r and r:IsShown(), "receipt not shown")
    assert(OpenMailInvoiceFrame == nil or OpenMailInvoiceFrame.alpha == 0, "stock receipt visible")
    assert(r.chip.fsLabel.text == "SOLD", "chip " .. tostring(r.chip.fsLabel.text))
    assert(r.item.text:find("Bolt of Woolen Cloth") and r.item.text:find("x3"), "item " .. r.item.text)
    assert(r.who.text:find("Cuddly Cow"), "buyer")
    assert(r.rows[1].value.text:find("14s") and r.rows[1].value.text:find("67c"), "sale " .. r.rows[1].value.text)
    assert(r.rows[2].value.text:find("+") and r.rows[2].value.text:find("1s"), "deposit " .. r.rows[2].value.text)
    assert(r.rows[3].value.text:find("73c"), "cut " .. r.rows[3].value.text)
    assert(r.total.text:find("14s") and r.total.text:find("94c"), "total " .. r.total.text)
    assert(S.letter.scroll.alpha == 0, "stock body still showing under the receipt")
    -- a plain letter puts the body back
    function GetInboxInvoiceInfo(i) return nil end
    ShowInbox(1)
    assert(not r:IsShown() and S.letter.scroll.alpha == 1, "plain letter")
""")

case("the_letter_header_lines_keep_the_mocks_positions", PRELUDE + """
    ShowInbox(1)
    local L = S.letter
    local O = OpenMailFrame
    assert(L.from.text == "Stu Moolah" and L.re.text == "Thunder Lizard Tail (2)" and L.expires.text == "expires 28d", "text")
    local fl, fy = Px(L.from, O)
    assert(Near(fl, 70), "from x " .. fl)
    local _, _, er = Px(L.expires, O)
    assert(Near(440 - er, 18), "expires right inset " .. (440 - er))
""")

local_send_prelude = """
    local FS = Load()
    ShowInbox()
    Fire("PLAYER_ENTERING_WORLD")
    ShowSend({ [1] = true })
    assert(#DEGRADED == 0, "degraded: " .. table.concat(DEGRADED, " | "))
    local S = Mine()
    local W = MailFrame
    local P = SendMailFrame
"""

case("the_subject_fills_from_the_item_or_the_gold_and_never_over_typed_text", local_send_prelude + """
    local box = SendMailSubjectEditBox
    function GetSendMailItem(i) return SEND.items[i] and "Linen Cloth" or nil, 2589, "tex", 20, 1 end
    local copper = 0
    function MoneyInputFrame_GetCopper() return copper end
    box:SetText("")
    SEND.items = { [1] = true }
    SendMailFrame_Update()
    assert(box:GetText() == "Linen Cloth (20)", "item fill: " .. tostring(box:GetText()))
    SEND.items = {}
    SendMailFrame_Update()
    assert(box:GetText() == "", "its own text clears with the item: " .. tostring(box:GetText()))
    copper = 254012
    FS.MailAutoSubject()
    assert(box:GetText() == "25g 40s 12c", "gold fill: " .. tostring(box:GetText()))
    copper = 10000
    FS.MailAutoSubject()
    assert(box:GetText() == "1g", "gold follows the amount: " .. tostring(box:GetText()))
    box:SetText("rent")
    SEND.items = { [1] = true }
    SendMailFrame_Update()
    assert(box:GetText() == "rent", "typed subject kept: " .. tostring(box:GetText()))
""")

case("send_prompt_lines_postage_chip_and_pad_keep_the_mocks_margins", local_send_prelude + """
    local name, subject = SendMailNameEditBox, SendMailSubjectEditBox
    -- the typed text starts 12 px after its label (TO 16 px, SUBJECT 55 px wide); TO stops 12 px short of the postage chip
    Expect(name, W, 64, 68, 234, 24, "to field")
    Expect(subject, W, 103, 110, 311, 24, "subject field")
    local _, ny = CenterOf(name, W)
    local _, sy = CenterOf(subject, W)
    assert(Near(ny, 80) and Near(sy, 122), "field centres")
    local pl, pt, pr = Px(S.send.postage.parent or P, W)
    -- the postage chip is 18 px from the right edge, level with the to line
    local chip
    for _, c in ipairs(P.children) do
        local l, t, r, b = Px(c, W)
        if Near(l, 310) and Near(t, 68) then chip = c end
    end
    assert(chip, "postage chip")
    Expect(chip, W, 310, 68, 104, 24, "postage chip")
    local _, cy = CenterOf(chip, W)
    assert(Near(cy, 80), "chip centre " .. cy)
    assert(Near(432 - 414, 18), "")
    -- the message pad keeps 18 px each side and grows by the 78 px the taller window gives
    local pad
    for _, c in ipairs(P.children) do
        local l, t = Px(c, W)
        if Near(l, 18) and Near(t, 152) then pad = c end
    end
    assert(pad, "pad")
    Expect(pad, W, 18, 152, 396, 228, "message pad")
""")

case("send_cargo_strip_money_segments_and_footer_keep_the_mocks_spacing", local_send_prelude + """
    local strip
    for _, c in ipairs(P.children) do
        local l, t = Px(c, W)
        if Near(l, 18) and Near(t, 414) then strip = c end
    end
    assert(strip, "cargo strip")
    Expect(strip, W, 18, 414, 396, 58, "cargo strip")
    for i = 1, 8 do
        Expect(_G["SendMailAttachment" .. i], strip, 8 + (i - 1) * 48, 7, 44, 44, "slot " .. i)
    end
    local _, _, r8 = Px(SendMailAttachment8, W)
    assert(Near(414 - r8, 8), "last slot to the strip edge " .. (414 - r8))
    -- three money segments on an 82 px pitch, the edit boxes end 30 px before each segment's end (the coin chip)
    local segs = {}
    for _, c in ipairs(P.children) do
        local l, t, r, b = Px(c, W)
        if Near(t, 510) and Near(b - t, 36) and Near(r - l, 76) then segs[#segs + 1] = c end
    end
    table.sort(segs, function(a, b) return Px(a, W) < Px(b, W) end)
    assert(#segs == 3, "segments " .. #segs)
    for i, seg in ipairs(segs) do Expect(seg, W, 18 + (i - 1) * 82, 510, 76, 36, "segment " .. i) end
    Expect(SendMailMoneyGold, segs[1], 6, 6, 40, 24, "gold box")
    -- the send / c.o.d. switch ends at the 414 edge, level with the segments
    local sw = S.send.mode.plate
    Expect(sw, W, 264, 510, 150, 36, "mode switch")
    Expect(S.send.mode.segs[1].button, sw, 3, 3, 71, 30, "send segment")
    Expect(S.send.mode.segs[2].button, sw, 76, 3, 71, 30, "cod segment")
    -- footer keys
    Expect(SendMailCancelButton, W, 204, 618, 110, 36, "cancel")
    Expect(SendMailMailButton, W, 322, 618, 92, 36, "send")
    local _, _, sr, sb = Px(SendMailMailButton, W)
    assert(Near(432 - sr, 18) and Near(670 - sb, 16), "footer margins")
    local _, _, cr = Px(SendMailCancelButton, W)
    local sl = Px(SendMailMailButton, W)
    assert(Near(sl - cr, 8), "cancel to send gap")
    -- the rule is 16 px above the keys and the keys 16 px above the bottom: one rhythm either side
    local rule
    for _, r in ipairs(P.regions) do
        local l, tp, rr, b = Px(r, W)
        if Near(l, 18) and Near(rr - l, 396) and Near(b - tp, 1) and tp > 560 then rule = r; assert(Near(tp, 601), "rule y " .. tp) end
    end
    assert(rule, "send footer rule")
    local _, _, _, rb = Px(rule, W)
    local _, kt = Px(SendMailMailButton, W)
    assert(Near(kt - rb, 16), "rule to keys " .. (kt - rb))
    local bx, by = CenterOf(S.send.balance, W)
    assert(Near(by, 636, 0.5), "balance centre " .. by)
""")

case("twelve_send_slots_wrap_to_a_second_row_and_the_form_still_fits", """
    ATTACHMENTS_MAX_SEND = 12
    for i = 1, 16 do SendMailAttachment1.shown = true end
""" + local_send_prelude + """
    local strip
    for _, c in ipairs(P.children) do
        local l, t = Px(c, W)
        if Near(l, 18) and Near(t, 366) then strip = c end
    end
    assert(strip, "cargo strip moved up by the extra row")
    Expect(strip, W, 18, 366, 396, 106, "two row strip")
    Expect(SendMailAttachment9, strip, 8, 55, 44, 44, "slot 9")
    Expect(SendMailMailButton, W, 322, 618, 92, 36, "send")
    assert(S.send.cargo.text == "1/12", "cargo count " .. S.send.cargo.text)
""")

case("send_text_comes_from_the_api_and_the_mode_switch_follows_the_radios", local_send_prelude + """
    assert(S.send.cargo.text == "1/8", "cargo " .. S.send.cargo.text)
    assert(S.send.postage.text:find("30c"), "postage " .. S.send.postage.text)
    assert(S.send.balance.text:find("1g") and S.send.balance.text:find("42s") and S.send.balance.text:find("39c"), "balance " .. S.send.balance.text)
    assert(S.send.mode.active == 1, "send money active")
    SendMailCODButton:Click()
    FlushTimers()
    assert(S.send.mode.active == 2, "cod active after the radio changed")
    -- the segment is a proxy for nothing: the Blizzard radio is the click target and is the switch's button
    assert(S.send.mode.segs[2].button == SendMailCODButton, "switch drives the stock radio")
""")

case("typed_text_stays_visible_and_the_slots_survive_the_stock_update", local_send_prelude + """
    assert(SendMailNameEditBox.display.alpha ~= 0, "typed name hidden")
    assert(SendMailSubjectEditBox.display.alpha ~= 0, "typed subject hidden")
    assert(SendMailNameEditBox.caption.alpha == 0, "stock To: caption")
    local before = SendMailAttachment1.points[1].rel
    assert(before ~= SendMailFrame, "slot starts on our strip")
    SendMailFrame_Update()
    assert(SendMailAttachment1.points[1].rel == before, "slot left on the stock grid after SendMailFrame_Update")
""")

case("the_header_switch_drives_the_stock_tabs_and_follows_the_page", PRELUDE + """
    local sw = S.header.switch
    assert(sw.active == 1, "inbox active")
    sw.segs[2].button.scripts.OnClick()
    FlushTimers()
    assert(SendMailFrame:IsShown() and not InboxFrame:IsShown(), "send page")
    assert(sw.active == 2, "send active")
    sw.segs[1].button.scripts.OnClick()
    assert(InboxFrame:IsShown() and sw.active == 1, "back to the inbox")
    assert(sw.segs[1].label.text == "inbox 2", "unread count " .. sw.segs[1].label.text)
    assert(MailFrameTab1.alpha == 0 and MailFrameTab2.alpha == 0, "stock tabs are drawn")
""")

case("blizzard_art_is_held_its_text_replaced_and_no_script_or_attribute_was_written", PRELUDE + """
    ShowInbox(1)
    assert(MailFrameBg.shown == false and MailFramePortrait.shown == false, "window art")
    assert(MailFrameTitleText.alpha == 0, "stock title")
    for i = 1, 7 do
        assert(_G["MailItem" .. i .. "Sender"].alpha == 0 and _G["MailItem" .. i .. "Subject"].alpha == 0, "row text " .. i)
        assert(_G["MailItem" .. i .. "ButtonIcon"].alpha == 0 and _G["MailItem" .. i .. "ButtonSlot"].alpha == 0, "row art " .. i)
        assert(_G["MailItem" .. i .. "ButtonCOD"].alpha == 0, "cod stamp " .. i)
    end
    assert(OpenMailSender.alpha == 0 and OpenMailSubject.alpha == 0 and OpenMailSenderLabel.alpha == 0, "letter text")
    assert(OpenMailReplyButton.Left.alpha == 0 and OpenMailReplyButton.fs.alpha == 0, "reply art and text")
    assert(OpenMailAttachmentButton1IconTexture.alpha == 1, "the item icon stays visible")
    assert(OpenMailAttachmentButton1NormalTexture.alpha == 0, "slot art")
    assert(SendMailNameEditBoxLeft.alpha == 0, "edit box art")
    -- a stray SetAlpha puts a held region back to zero
    MailItem1Sender:SetAlpha(1)
    assert(MailItem1Sender.alpha == 0, "alpha was not held")
    -- the label of a stock key is the lowercase of its text
    assert(S.keys[OpenMailReplyButton].label.text == "reply", "label " .. S.keys[OpenMailReplyButton].label.text)
    assert(S.keys[OpenAllMail].label.text == "open all", "open all label")
    OpenAllMail:SetText("Opening...")
    assert(S.keys[OpenAllMail].label.text == "opening...", "stock progress text")
    OpenMailReplyButton:SetText("Antworten")
    assert(S.keys[OpenMailReplyButton].label.text == "antworten", "mirrored text")
    -- template captions that GetFontString does not return are held too, and our own labels stay visible
    assert(InboxFrame.prev.caption.alpha == 0 and InboxFrame.next.caption.alpha == 0, "pager captions")
    for i = 1, 7 do assert(_G["MailItem" .. i .. "ExpireTime"].caption.alpha == 0, "expiry caption " .. i) end
    assert(S.keys[OpenAllMail].label.alpha ~= 0, "our open all label")
    -- a caption a button creates on its first SetText is held as well
    local late = OpenMailReplyButton:CreateFontString(nil, "OVERLAY")
    late.fontPath = "stock.ttf"
    OpenMailReplyButton:SetText("Reply")
    assert(late.alpha == 0, "late caption")
    assert(#DEGRADED == 0, "degraded: " .. table.concat(DEGRADED, " | "))
""")

case("a_second_scan_builds_nothing_new_and_combat_defers_the_build", """
    local FS = Load()
    ShowInbox()
    Fire("PLAYER_ENTERING_WORLD")
    local before, hooks = ObjCount(), HookCount()
    assert(hooks > 0, "no hooks installed")
    Fire("PLAYER_ENTERING_WORLD")
    Fire("ADDON_LOADED", "Blizzard_MailFrame")
    ShowInbox()
    assert(ObjCount() == before, "objects grew " .. before .. " -> " .. ObjCount())
    assert(HookCount() == hooks, "hooks grew " .. hooks .. " -> " .. HookCount())
""")

case("nothing_is_built_in_combat_and_the_build_runs_when_it_ends", """
    __combat = true
    local FS = Load()
    local hooks, kids, regions = HookCount(), #MailFrame.children, #MailFrame.regions
    ShowInbox()
    Fire("PLAYER_ENTERING_WORLD")
    assert(Mine().done.window == nil, "built in combat")
    assert(HookCount() == hooks, "hooks added in combat")
    assert(#MailFrame.children == kids and #MailFrame.regions == regions, "mail frame given new parts in combat")
    assert(MailFrameBg.alpha == 1 and MailFrameTitleText.alpha == 1, "mail frame touched in combat")
    __combat = false
    Fire("PLAYER_REGEN_ENABLED")
    assert(Mine().done.window, "not built after combat")
    assert(#DEGRADED == 0, "degraded: " .. table.concat(DEGRADED, " | "))
""")

case("a_change_of_pixel_scale_reseats_every_edge_on_whole_pixels", PRELUDE + """
    PPU = 1.25
    Fire("UI_SCALE_CHANGED")
    Expect(W, W, 0, 0, 432, 670, "window at 1.25")
    for i = 1, 7 do Expect(S.rows[i].row, W, 14, 62 + (i - 1) * 78, 404, 68, "row at 1.25") end
    for obj in pairs(S.placed) do
        if obj.kind ~= "FontString" then
            local l, t, r, b = Px(obj, W)
            for _, v in ipairs({ l, t, r, b }) do
                assert(Near(v, math.floor(v + 0.5), 0.001), string.format("%s edge %.4f at 1.25", obj.kind, v))
            end
        end
    end
    PPU = 1
    Fire("UI_SCALE_CHANGED")
    Expect(W, W, 0, 0, 432, 670, "window at 1.0")
""")

case("mail_lua_leaves_no_other_panel_skin_on_the_mail_windows", PRELUDE + """
    -- Panels.lua no longer owns MailFrame: no fsPanelSkin marker, the Mail guard is set instead
    assert(MailFrame.fsMailSkin and OpenMailFrame.fsMailSkin, "inspect guards")
    assert(MailFrame.fsPanelSkin == nil, "panel skin on mail")
    assert(#UISpecialFrames == 1 and UISpecialFrames[1] == "OpenMailFrame", "esc closes the letter")
""")


def main() -> int:
    png = None
    if "--png" in sys.argv:
        png = sys.argv[sys.argv.index("--png") + 1]
    failures = 0
    for name, body in CASES:
        err, _ = run_case(body)
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}: {err}")
    print(f"{len(CASES) - failures}/{len(CASES)} checks passed")
    if png:
        render(png)
    return int(failures > 0)


# ---------------------------------------------------------------------------------------------
# Renderer (PNG for a look; the checks above are the contract)
# ---------------------------------------------------------------------------------------------


def render(prefix: str) -> None:
    from PIL import Image, ImageDraw, ImageFont

    scenes = {
        "inbox": "local FS = Load(); ShowInbox(); Fire('PLAYER_ENTERING_WORLD'); ShowInbox(1); return DumpOps({ MailFrame, OpenMailFrame })",
        "receipt": "local FS = Load(); function GetInboxInvoiceInfo() return 'seller', 'Bolt of Woolen Cloth', 'Cuddly Cow', 1467, 0, 100, 73, 0, nil, nil, 3 end; ShowInbox(); Fire('PLAYER_ENTERING_WORLD'); ShowInbox(1); return DumpOps({ MailFrame, OpenMailFrame })",
        "send": "local FS = Load(); ShowInbox(); Fire('PLAYER_ENTERING_WORLD'); ShowSend({ [1] = true }); return DumpOps({ MailFrame })",
    }
    for scene, code in scenes.items():
        rt = LuaRuntime(unpack_returned_tuples=False)
        for key, src in SOURCES.items():
            rt.globals()["SRC_" + key] = src
        rt.execute("SOURCES = { Theme = SRC_Theme, HeldArt = SRC_HeldArt, PanelSkins = SRC_PanelSkins, Mail = SRC_Mail }")
        rt.execute(MOCK)
        rt.execute("BuildBlizzard()")
        ops = rt.execute("local function main()\n" + code + "\nend\nreturn main()")
        flat = []
        for i in range(1, len(ops) + 1):
            op = ops[i]
            flat.append({k: (dict((j, v[j]) for j in range(1, len(v) + 1)) if hasattr(v, "__len__") and not isinstance(v, str) else v)
                         for k, v in dict(op.items()).items()})
        xs = [o["l"] for o in flat] + [o["r"] for o in flat]
        ys = [o["t"] for o in flat] + [o["b"] for o in flat]
        pad = 24
        ox, oy = min(xs) - pad, min(ys) - pad
        W, H = int(max(xs) - ox + pad), int(max(ys) - oy + pad)
        img = Image.new("RGBA", (W, H), (11, 6, 24, 255))
        fonts: dict[int, ImageFont.FreeTypeFont] = {}
        for op in flat:
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            rgba = op["rgba"]
            col = tuple(int(max(0, min(1, rgba[k])) * 255 + 0.5) for k in (1, 2, 3)) + (int(max(0, min(1, rgba[4])) * 255 + 0.5),)
            l, t, r, b = (round(op["l"] - ox), round(op["t"] - oy), round(op["r"] - ox), round(op["b"] - oy))
            kind = op["kind"]
            if kind == "text":
                size = max(6, round(op["size"]))
                font = fonts.setdefault(size, ImageFont.truetype(str(FONT), size))
                text = op["text"]
                segments = []
                color = col
                import re
                pos = 0
                for m in re.finditer(r"\|c([0-9a-fA-F]{8})|\|r", text):
                    if m.start() > pos:
                        segments.append((text[pos:m.start()], color))
                    if m.group(1):
                        h = m.group(1)
                        color = (int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16), col[3])
                    else:
                        color = col
                    pos = m.end()
                segments.append((text[pos:], color))
                total = sum(font.getlength(s) for s, _ in segments)
                x = l if op["justify"] == "LEFT" else (r - total if op["justify"] == "RIGHT" else (l + r) / 2 - total / 2)
                cy = (t + b) / 2
                for s, c in segments:
                    d.text((x, cy), s, font=font, fill=c, anchor="lm")
                    x += font.getlength(s)
            else:
                c = max(0, min(int(op.get("c", 0)), (b - t) // 2))
                pts = [(l + c, t), (r - 1, t), (r - 1, b - 1 - c), (r - 1 - c, b - 1), (l, b - 1), (l, t + c)] if kind in ("fill", "ring") else None
                if kind == "flat":
                    d.rectangle([l, t, r - 1, b - 1], fill=col)
                elif kind == "fill":
                    d.polygon(pts, fill=col)
                elif kind == "ring":
                    d.line(pts + [pts[0]], fill=col, width=1)
            img = Image.alpha_composite(img, layer)
        out = f"{prefix}-{scene}.png"
        img.convert("RGB").save(out)
        print("wrote", out)


if __name__ == "__main__":
    raise SystemExit(main())
