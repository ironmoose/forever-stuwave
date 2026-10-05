#!/usr/bin/env python3
"""Headless check of Bags.lua: our slot plate only (no Blizzard slot art) and the data bar money line.

Runs the real addons/forever-stuwave/Bags.lua under lupa against a small mock WoW API. The mock models
the Blizzard structures the file touches, the way the 12.1 FrameXML builds them (corroborating only; the
target client is 16001):

  * an item slot is an ItemButton: `icon`, `Count`, `IconBorder` (quality), `IconOverlay`, `NewItemTexture`,
    `flash`, `UpgradeIcon`, `JunkIcon`, `searchOverlay`, ... and the button's own NormalTexture
    (Interface\\Buttons\\UI-Quickslot2, the square slot frame), Pushed/Highlight textures;
  * an EMPTY container slot has no background region of its own: SetItemButtonTexture(nil) points the ICON at
    the `bags-item-slot64` atlas (the brown winged slot), so that is what the empty-slot hook must clear;
  * a combined-bags slot makes `ItemSlotBackground` (UI-Bag-Components) inside Initialize, AFTER the first skin;
  * a bank slot has a `Background` region re-pointed by UpdateBackgroundForBankType;
  * Blizzard "re-shows" slot art in two ways, both modelled: a plain alpha write on the region, and a NEW region
    (SetNormalTexture after ClearNormalTexture, the combined-bags background made inside Initialize); SetAtlas and
    SetTexture on an existing region leave its alpha alone, as in the engine;
  * the money frame is the SmallMoneyFrame: Gold/Silver/CopperButton each with a `Text` FontString and a coin
    NormalTexture, whose update re-points (or recreates, after ClearNormalTexture) the coin atlas and calls
    SetText, and whose colour helper calls SetNormalFontObject; the colorblindMode CVar is read through
    CVarCallbackRegistry like MoneyFrame.lua does.

`pcall` is replaced by a recording wrapper: any error Bags.lua swallows is a failure unless a case expects it.

What it pins:

  * item slots: Blizzard's normal texture, the combined-bags background, the bank background and the empty-slot
    icon art are hidden after the skin AND stay hidden after Blizzard re-shows them (alpha write, a region
    created later); a region whose hook install failed is retried on the next pass; a filled slot keeps its icon;
  * the quality IconBorder (and IconOverlay, NewItemTexture, flash, UpgradeIcon, JunkIcon, search overlay,
    pushed and highlight textures, ExtendedSlot) is never hooked, hidden or recoloured by us;
  * our plate (cut2 button texture, BACKGROUND -8) and border (SkinCutButton) exist once per button across
    repeated UpdateItems; an empty slot shows only the plate and the ring; hooks are installed once;
  * the money line (container, combined bags, bank) follows DataBar.lua's GOLD segment: same coin colours, dot
    texture and size, text font size and dot to text gap, all read from DataBar.lua, never retyped; the
    Blizzard coin atlas stays hidden through the update path, a recreated texture and a font object swap; in
    colorblind mode (letters instead of coins, no coin gap) the dots are hidden and come back when it is off;
  * nothing errors when a region, a method or Theme.AddCut2Texture is absent.

    python3 tools/bags-harness.py

Exit 0 = every check passed; otherwise the number of failures.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
BAGS_LUA = Path(os.environ.get("BAGS_LUA") or ADDON / "Modules/Bags/Bags.lua")   # BAGS_LUA: a mutated scratch copy
DATABAR_LUA = ADDON / "Modules/DataBars/DataBar.lua"


# ---------------------------------------------------------------------------------------
# What DataBar.lua's GOLD segment draws. Read, never retyped.
# ---------------------------------------------------------------------------------------

def databar_money() -> dict:
    src = DATABAR_LUA.read_text(encoding="utf-8")

    def triple(name: str) -> list[float]:
        m = re.search(rf"local {name}\s*=\s*\{{\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)\s*\}}", src)
        if not m:
            sys.exit(f"DataBar.lua: {name} not found")
        return [float(v) for v in m.groups()]

    def number(pattern: str) -> int:
        m = re.search(pattern, src)
        if not m:
            sys.exit(f"DataBar.lua: {pattern} not found")
        return int(m.group(1))

    tex = re.search(r'local GLOW_ROUND_TEXTURE\s*=\s*("[^"\n]*")', src)
    if not tex:
        sys.exit("DataBar.lua: GLOW_ROUND_TEXTURE not found")
    path = LuaRuntime().eval("function(s) return loadstring('return ' .. s)() end")(tex.group(1))
    return {
        "gold": triple("COIN_GOLD"),
        "silver": triple("COIN_SILVER"),
        "copper": triple("COIN_COPPER"),
        "size": number(r"local COIN_SIZE\s*=\s*(\d+)"),
        "gap": number(r"local COIN_TEXT_GAP\s*=\s*(\d+)"),
        "font": number(r"ApplyMono\(text,\s*(\d+),\s*spec\.color\)"),
        "texture": str(path),
    }


# ---------------------------------------------------------------------------------------
# The mock
# ---------------------------------------------------------------------------------------

MOCK = r"""
SWALLOWED, DEGRADE, CALLS, HOOKED = {}, {}, {}, {}
local rawpcall = pcall
local function wrap(ok, ...) if not ok then SWALLOWED[#SWALLOWED + 1] = tostring((...)) end return ok, ... end
function pcall(f, ...) return wrap(rawpcall(f, ...)) end
function __clearSwallowed() SWALLOWED = {} end

CVARS = { colorblindMode = "0" }
CVarCallbackRegistry = { GetCVarValueBool = function(_, name) return CVARS[name] == "1" end }
function GetCVar(name) return CVARS[name] end

local Class = {}
local Mt = { __index = Class }
local function new(kind, parent)
    return setmetatable({ _kind = kind, _parent = parent, _shown = true, _alpha = 1, _pts = {}, _regions = {},
        _children = {}, _scripts = {}, _w = 0, _h = 0 }, Mt)
end
local function region(parent, kind, tag)
    local r = new(kind, parent)
    r._tag = tag
    parent._regions[#parent._regions + 1] = r
    return r
end

function hooksecurefunc(a, b, c)
    local tbl, name, fn = a, b, c
    if type(a) == "string" then tbl, name, fn = _G, a, b end
    local orig = tbl[name]
    if type(orig) ~= "function" then error("hooksecurefunc(): " .. tostring(name) .. " is not a function") end
    HOOKED[#HOOKED + 1] = { tbl = tbl, name = name }
    rawset(tbl, name, function(...) local r = { orig(...) }; fn(...); return unpack(r) end)
end

-- widget methods ---------------------------------------------------------------------------------
function Class:GetObjectType() return self._kind end
function Class:SetAlpha(a) self._alpha = a end
function Class:GetAlpha() return self._alpha end
function Class:SetAtlas(a) self._atlas = a; self._texture = nil end        -- the engine leaves alpha alone
function Class:GetAtlas() return self._atlas end
function Class:SetTexture(t) self._texture = t; self._atlas = nil end
function Class:GetTexture() return self._texture end
function Class:SetVertexColor(r, g, b, a) self._vc = { r, g, b, a } end
function Class:GetVertexColor() local v = self._vc or { 1, 1, 1, 1 }; return v[1], v[2], v[3], v[4] end
function Class:SetBlendMode(m) self._blend = m end
function Class:SetDrawLayer(l, s) self._layer, self._sub = l, s end
function Class:SetSize(w, h) self._w, self._h = w, h end
function Class:SetWidth(w) self._w = w end
function Class:SetHeight(h) self._h = h end
function Class:GetWidth() return self._w end
function Class:GetHeight() return self._h end
function Class:SetPoint(...) self._pts[#self._pts + 1] = { ... } end
function Class:ClearAllPoints() self._pts = {} end
function Class:Show() self._shown = true end
function Class:Hide() self._shown = false end
function Class:SetShown(v) self._shown = v and true or false end
function Class:IsShown() return self._shown end
function Class:HookScript(which, fn) self._scripts[which] = self._scripts[which] or {}; table.insert(self._scripts[which], fn) end
function Class:GetRegions() return unpack(self._regions) end
function Class:CreateTexture(_, layer, _, sub)
    local t = region(self, "Texture", "created")
    t._layer, t._sub = layer, sub
    return t
end
function Class:CreateFontString()
    local f = region(self, "FontString", "created")
    return f
end
-- FontString
function Class:SetFont(path, size, flags) self._font = { path, size, flags } end
function Class:GetFont() local f = self._font or { "blizz", 13, "" }; return f[1], f[2], f[3] end
function Class:SetTextColor(r, g, b, a) self._tc = { r, g, b, a } end
function Class:GetTextColor() local c = self._tc or { 1, 1, 1, 1 }; return c[1], c[2], c[3], c[4] end
function Class:SetShadowColor() end
function Class:SetText(t) self._text = t end
function Class:GetText() return self._text end
-- Button: normal texture the way the engine keeps it
function Class:GetNormalTexture() return self._normal end
function Class:ClearNormalTexture() self._normal = nil end
function Class:SetNormalTexture(arg)
    if type(arg) == "table" then self._normal = arg
    else
        if not self._normal then self._normal = region(self, "Texture", "normal") end
        self._normal:SetTexture(arg)
    end
end
function Class:SetNormalAtlas(a)
    if not self._normal then self._normal = region(self, "Texture", "normal") end
    self._normal:SetAtlas(a)
end
function Class:SetNormalFontObject(fo)           -- the engine re-applies the font object to the ButtonText
    local text = self.Text
    if text then text._font = { fo.path, fo.size, "" }; text._tc = { fo.r, fo.g, fo.b, 1 } end
end
function Class:GetFontString() return self.Text end
function Class:SetEnabled() end

function CreateFrame(kind, name, parent)
    local f = new(kind, parent)
    if name then _G[name] = f end
    if parent then parent._children[#parent._children + 1] = f end
    return f
end

-- Blizzard-shaped builders -----------------------------------------------------------------------
local function tex(parent, tag, opts)
    local t = region(parent, "Texture", tag)
    opts = opts or {}
    t._shown = opts.shown ~= false
    t._alpha = opts.alpha or 1
    if opts.atlas then t._atlas = opts.atlas elseif opts.file then t._texture = opts.file end
    return t
end

-- An ItemButton as ItemButtonTemplate.xml + ContainerFrameItemButtonTemplate build it.
-- `kind` is "container" or "bank". Instance functions mimic the mixin, which is copied onto the frame.
function MkItemButton(parent, kind)
    local b = new("Button", parent)
    b._kind = "Button"
    b.emptyBackgroundAtlas = "bags-item-slot64"
    b.icon = tex(b, "icon", { file = "ICON-PLACEHOLDER" })
    b.icon._texture = nil
    b.Count = region(b, "FontString", "Count")
    b.IconBorder = tex(b, "IconBorder", { shown = false, file = "Interface\\Common\\WhiteIconFrame" })
    b.IconOverlay = tex(b, "IconOverlay", { shown = false })
    b.IconOverlay2 = tex(b, "IconOverlay2", { shown = false })
    b.searchOverlay = tex(b, "searchOverlay", { shown = false })
    b.ItemContextOverlay = tex(b, "ItemContextOverlay", { shown = false })
    b.NewItemTexture = tex(b, "NewItemTexture", { alpha = 0, atlas = "bags-glow-green" })
    b.BattlepayItemTexture = tex(b, "BattlepayItemTexture", { shown = false, file = "Interface\\Store\\store-item-highlight" })
    b.flash = tex(b, "flash", { alpha = 0, atlas = "bags-glow-flash" })
    b.UpgradeIcon = tex(b, "UpgradeIcon", { shown = false, atlas = "bags-greenarrow" })
    b.JunkIcon = tex(b, "JunkIcon", { shown = false, atlas = "bags-junkcoin" })
    b.IconQuestTexture = tex(b, "IconQuestTexture", { shown = false })
    b.ExtendedSlot = tex(b, "ExtendedSlot", { shown = false, file = "Interface\\Buttons\\UI-Quickslot2" })
    b.NormalTexture = tex(b, "NormalTexture", { file = "Interface\\Buttons\\UI-Quickslot2" })
    b._normal = b.NormalTexture
    b.PushedTexture = tex(b, "PushedTexture", { shown = false, file = "Interface\\Buttons\\UI-Quickslot-Depress" })
    b.HighlightTexture = tex(b, "HighlightTexture", { shown = false, file = "Interface\\Buttons\\ButtonHilight-Square" })
    if kind == "bank" then
        b.Background = tex(b, "Background", { atlas = "bags-item-slot64" })
        b.UpdateBackgroundForBankType = function(self)
            self.Background:SetAtlas("bags-item-slot64")      -- Blizzard re-points it
        end
    end
    -- ItemButtonTemplate.lua SetItemButtonTexture_Base
    if kind == "bank" then
        -- BankPanelItemButtonMixin:Refresh: the icon only shows an item; the slot art is the separate Background
        b.emptyBackgroundAtlas = nil
        b.SetItemButtonTexture = function(self, texture)
            self.icon:SetShown(texture ~= nil)
            if texture then self.icon:SetTexture(texture) end
        end
    else
        b.SetItemButtonTexture = function(self, texture)
            local atlas = (not texture) and self.emptyBackgroundAtlas or nil
            self.icon:SetShown(texture ~= nil or atlas ~= nil)
            if texture then self.icon:SetTexture(texture) elseif atlas then self.icon:SetAtlas(atlas) end
        end
    end
    if kind == "container" then
        -- ContainerFrameItemButtonMixin:Initialize
        b.Initialize = function(self)
            local combined = self._parent and self._parent.isCombined
            if combined and not self.ItemSlotBackground then
                self.ItemSlotBackground = tex(self, "ItemSlotBackground", { file = "Interface\\ContainerFrame\\UI-Bag-Components" })
            end
            if self.ItemSlotBackground then self.ItemSlotBackground:SetShown(combined) end
            self:Show()
        end
    end
    return b
end

-- What a Blizzard repaint of one button does, in the order UpdateItems/Refresh do it: the quality border
-- is vertex coloured per item, the icon gets the item or the empty art.
function BlizzardPaint(b, info)
    b:SetItemButtonTexture(info and info.icon or nil)
    if info and info.quality then
        b.IconBorder:SetVertexColor(info.quality[1], info.quality[2], info.quality[3])
        b.IconBorder:Show()
    else
        b.IconBorder:Hide()
    end
end

-- Blizzard re-sets the slot art outside any of our hooks' control.
function BlizzardReset(b)
    b:SetNormalTexture("Interface\\Buttons\\UI-Quickslot2")
    b.NormalTexture:SetAlpha(1)
    if b.ItemSlotBackground then b.ItemSlotBackground:SetTexture("Interface\\ContainerFrame\\UI-Bag-Components") end
    if b.UpdateBackgroundForBankType then b:UpdateBackgroundForBankType() end
end

function MkMoneyFrame(parent, name)
    local m = new("Frame", parent)
    m.info = { collapse = 1 }
    for _, spec in ipairs({ { "GoldButton", "coin-gold" }, { "SilverButton", "coin-silver" }, { "CopperButton", "coin-copper" } }) do
        local btn = new("Button", m)
        btn._kind = "Button"
        btn._atlasName = spec[2]
        btn.Text = region(btn, "FontString", "MoneyText")
        btn.Text._font = { "blizzard-number-font", 13, "" }
        btn.NormalTexture = tex(btn, "coin", { atlas = spec[2] })
        btn._normal = btn.NormalTexture
        m[spec[1]] = btn
    end
    -- MoneyFrame_Update's icon init (dirty on every call in the real code): the same texture is re-pointed, or
    -- a NEW one is created after ClearNormalTexture (colorblind off again).
    m.__update = function(self)
        for _, key in ipairs({ "GoldButton", "SilverButton", "CopperButton" }) do
            local btn = self[key]
            local t = btn:GetNormalTexture() or btn:CreateTexture()
            t:SetAtlas(btn._atlasName)
            btn:SetNormalTexture(t)
            btn:SetText("1")
        end
    end
    m.__colorblind = function(self) for _, key in ipairs({ "GoldButton", "SilverButton", "CopperButton" }) do self[key]:ClearNormalTexture() end end
    if name then _G[name] = m end
    return m
end

function MkContainer(name, nButtons, combined)
    local c = CreateFrame("Frame", name, UIParent)
    c.isCombined = combined or false
    c.Items = {}
    for i = 1, nButtons do c.Items[i] = MkItemButton(c, "container") end
    c.infos = {}
    c.MoneyFrame = MkMoneyFrame(c)
    c.EnumerateValidItems = function(self)
        local i = 0
        return function() i = i + 1; local b = self.Items[i]; if b then return i, b end end
    end
    c.UpdateItems = function(self)
        for i, b in self:EnumerateValidItems() do if b.SetItemButtonTexture then BlizzardPaint(b, self.infos[i]) end end
    end
    c.GenerateSlots = function(self) for _, b in ipairs(self.Items) do b:Initialize() end end
    return c
end

function MkBank(nButtons)
    BankFrame = CreateFrame("Frame", "BankFrame", UIParent)
    local p = CreateFrame("Frame", "BankPanel", BankFrame)
    p.pool = {}
    for i = 1, nButtons do p.pool[i] = MkItemButton(p, "bank") end
    p.infos = {}
    p.EnumerateValidItems = function(self)
        local i = 0
        return function() i = i + 1; return self.pool[i] end        -- pool:EnumerateActive yields just the button
    end
    local function paint(self) for i, b in ipairs(self.pool) do BlizzardPaint(b, self.infos[i]) end end
    p.GenerateItemSlotsForSelectedTab = paint
    p.RefreshAllItemsForSelectedTab = paint
    p.MoneyFrame = new("Frame", p)
    p.MoneyFrame.MoneyDisplay = MkMoneyFrame(p.MoneyFrame)
    p.MoneyFrame.WithdrawButton = new("Button", p.MoneyFrame)
    return p
end

-- Theme / PanelSkins stand-ins: they record, and build the regions the real helpers build -----------
local function themeTex(frame, path, layer, sub, tag)
    local t = frame:CreateTexture(nil, layer, nil, sub)
    t._tag = tag
    t:SetTexture(path)
    return t
end
FS = {
    LogDegradeOnce = function(key, msg) DEGRADE[#DEGRADE + 1] = key end,
    PanelSkins = {
        RequireExport = function(fn) return fn ~= nil end,
        DeferCombat = function(fn) fn() end,
        TryStyleMoney = function(frame) CALLS[#CALLS + 1] = { "TryStyleMoney", frame } end,
        RegisterRecon = function() end,
    },
    Theme = {
        FONT_MONO = "mono", SLICE_CUT2_BUTTON_TEXTURE = "slice_cut2_button.tga", SLICE_CUT_MARGIN = 6,
        SkinPanel = function(frame) CALLS[#CALLS + 1] = { "SkinPanel", frame } end,
        ApplyMono = function(fs, size, color)
            CALLS[#CALLS + 1] = { "ApplyMono", fs, size, color }
            fs:SetFont("mono", size, "")
            local c = color or { 1, 1, 1 }
            fs:SetTextColor(c[1], c[2], c[3], 1)
        end,
        AddCut2Texture = function(frame, path, color, layer, sub)
            CALLS[#CALLS + 1] = { "AddCut2Texture", frame, path, layer, sub }
            return themeTex(frame, path, layer, sub, "plate")
        end,
    },
}
local function skin(name)
    return function(button, opts)
        CALLS[#CALLS + 1] = { name, button, opts }
        if not button.fsSkin then
            button.fsSkin = { chamfer = 6 }
            themeTex(button, "slice_cut2_outline.tga", "OVERLAY", 1, "ring")
        end
        if opts and opts.count then FS.Theme.ApplyMono(opts.count, 11) end
        return button.fsSkin
    end
end
FS.Theme.SkinButton = skin("SkinButton")
FS.Theme.SkinCutButton = skin("SkinCutButton")

UIParent = new("Frame", nil)
_G.UIParent = UIParent

function __load(src)
    local chunk = assert(loadstring(src, "@Bags.lua"))
    chunk("forever-stuwave", FS)
end

-- inspection helpers -----------------------------------------------------------------------------
local function visible(r) return r._shown and r._alpha > 0 and (r._texture ~= nil or r._atlas ~= nil) end
function Visible(r) return visible(r) end
-- tags of every visible region of a button, sorted
function VisibleTags(b)
    local out = {}
    for _, r in ipairs(b._regions) do
        if r._kind == "Texture" and visible(r) then out[#out + 1] = r._tag end
    end
    table.sort(out)
    return table.concat(out, ",")
end
function Count(name, button)
    local n = 0
    for _, c in ipairs(CALLS) do if c[1] == name and (button == nil or c[2] == button) then n = n + 1 end end
    return n
end
function RegionCount(b, tag)
    local n = 0
    for _, r in ipairs(b._regions) do if r._tag == tag then n = n + 1 end end
    return n
end
function HookCount(obj, name)
    local n = 0
    for _, h in ipairs(HOOKED) do if h.tbl == obj and h.name == name then n = n + 1 end end
    return n
end
function TouchedByUs(r)           -- true when any hook of ours sits on the region
    for _, h in ipairs(HOOKED) do if h.tbl == r then return true end end
    return false
end
function DotShown(button)         -- the one dot of a coin button
    local d = DotsOf(button)[1]
    return d ~= nil and d._shown
end
function DotsOf(button)
    local out = {}
    for _, r in ipairs(button._regions) do
        if r._kind == "Texture" and r._blend == "ADD" and r._texture and r._texture ~= "" and r._tag == "created" then out[#out + 1] = r end
    end
    return out
end
"""

FAILS: list[str] = []
CHECKS = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILS.append(name)
        print(f"    FAIL  {name}" + (f"  [{detail}]" if detail else ""))


def near(a: float, b: float, eps: float = 1e-4) -> bool:
    return abs(a - b) <= eps


class World:
    """A mock client with ContainerFrame1/2, the combined bags frame and the bank built BEFORE Bags.lua loads.

    Bags.lua skins everything present while it loads (inside this constructor), so a case that needs a different
    starting state passes `pre`, Lua run just before the load.
    """

    def __init__(self, src: str | None = None, *, with_plate_helper: bool = True, pre: str = "") -> None:
        self.rt = LuaRuntime(unpack_returned_tuples=False)
        self.g = self.rt.globals()
        self.rt.eval("function(src) assert(loadstring(src))() end")(MOCK)
        self.run("""
            local EMPTY, AXE = nil, { icon = 135, quality = { 0.1, 0.9, 0.2 } }
            c1 = MkContainer("ContainerFrame1", 4)
            c1.infos = { AXE, nil, AXE, nil }
            c1:UpdateItems()
            c2 = MkContainer("ContainerFrame2", 2)
            comb = MkContainer("ContainerFrameCombinedBags", 3, true)
            comb.infos = { AXE, nil, AXE }
            bank = MkBank(3)
            bank.infos = { AXE, nil, nil }
            bank.GenerateItemSlotsForSelectedTab(bank)
        """)
        if not with_plate_helper:
            self.run("FS.Theme.AddCut2Texture = nil")
        if pre:
            self.run(pre)          # a mutation applied AFTER the frames exist and BEFORE Bags.lua loads (and skins them)
        self.rt.eval("__load")(src if src is not None else BAGS_LUA.read_text(encoding="utf-8"))

    def run(self, code: str):
        return self.rt.execute(code)

    def ev(self, code: str):
        return self.rt.eval(code)

    def swallowed(self) -> str:
        return "; ".join(str(v) for v in self.ev("SWALLOWED").values())

    def degrade(self) -> str:
        return ",".join(str(v) for v in self.ev("DEGRADE").values())


def tags(world: World, expr: str) -> str:
    return str(world.ev(f"VisibleTags({expr})"))


def check_art() -> None:
    w = World()
    # --- the container slot, filled and empty, after the first skin pass
    w.run("c1:UpdateItems()")
    check("art.normal_texture_hidden_after_skin", w.ev("not Visible(c1.Items[1].NormalTexture) and not Visible(c1.Items[2].NormalTexture)"),
          tags(w, "c1.Items[2]"))
    check("art.empty_slot_icon_art_cleared", w.ev("not Visible(c1.Items[2].icon)"), tags(w, "c1.Items[2]"))
    check("art.filled_slot_keeps_its_icon", w.ev("Visible(c1.Items[1].icon) and c1.Items[1].icon._texture == 135"), tags(w, "c1.Items[1]"))

    # --- Blizzard re-shows: a reset (re-texture plus alpha write), then a bare alpha write and a re-atlas
    w.run("for _, b in ipairs(c1.Items) do BlizzardReset(b) end")
    w.run("c1.Items[2].NormalTexture:SetAlpha(1); c1.Items[2].NormalTexture:SetAtlas('x'); c1.Items[2].NormalTexture:SetTexture('y')")
    check("art.normal_texture_stays_hidden_after_reset", w.ev("not Visible(c1.Items[1].NormalTexture) and not Visible(c1.Items[2].NormalTexture)"),
          tags(w, "c1.Items[1]"))
    w.run("c1.Items[3]:ClearNormalTexture(); c1.Items[3]:SetNormalAtlas('a-new-one')")
    check("art.a_recreated_normal_region_is_caught_by_the_setter_hook", w.ev("not Visible(c1.Items[3]:GetNormalTexture())"))

    # --- the empty slot's winged background is the ICON pointed at bags-item-slot64
    w.run("c1.Items[4]:SetItemButtonTexture(nil)")
    check("art.empty_icon_clears_when_blizzard_repoints_it", w.ev("not Visible(c1.Items[4].icon) and c1.Items[4].icon._atlas == nil"),
          tags(w, "c1.Items[4]"))
    w.run("c1.Items[4]:SetItemButtonTexture(136)")
    check("art.item_arriving_in_an_empty_slot_shows", w.ev("Visible(c1.Items[4].icon) and c1.Items[4].icon._texture == 136"))
    w.run("c1.Items[4].icon:SetAtlas('Garrison-Bag')")
    check("art.a_real_atlas_icon_is_left_alone", w.ev("Visible(c1.Items[4].icon) and c1.Items[4].icon._atlas == 'Garrison-Bag'"))
    w.run("c1.Items[4]:SetItemButtonTexture(nil)")
    check("art.emptying_again_clears_again", w.ev("not Visible(c1.Items[4].icon)"))

    # --- combined bags: ItemSlotBackground is made inside Initialize, after our first skin
    check("art.combined_background_not_yet_made_at_skin", w.ev("comb.Items[1].ItemSlotBackground == nil"))
    w.run("comb:GenerateSlots()")
    check("art.combined_background_hidden_the_moment_initialize_makes_it",
          w.ev("not Visible(comb.Items[1].ItemSlotBackground) and not Visible(comb.Items[2].ItemSlotBackground)"), tags(w, "comb.Items[2]"))
    w.run("comb:UpdateItems(); for _, b in ipairs(comb.Items) do BlizzardReset(b); b.ItemSlotBackground:SetShown(true) end")
    check("art.combined_background_stays_hidden_after_reset", w.ev("not Visible(comb.Items[1].ItemSlotBackground)"))

    # a region made without going through Initialize (a client that builds it elsewhere) is caught by the next pass
    w.run("""
        local b = c2.Items[1]
        b.ItemSlotBackground = b:CreateTexture(); b.ItemSlotBackground._tag = "ItemSlotBackground"
        b.ItemSlotBackground:SetTexture("late")
        c2:UpdateItems()
    """)
    check("art.a_region_that_appears_later_is_held_on_the_next_pass", w.ev("not Visible(c2.Items[1].ItemSlotBackground)"))

    # --- bank
    w.run("bank.RefreshAllItemsForSelectedTab(bank)")
    check("art.bank_background_hidden", w.ev("not Visible(bank.pool[1].Background) and not Visible(bank.pool[2].Background)"),
          tags(w, "bank.pool[2]"))
    w.run("bank.pool[2]:UpdateBackgroundForBankType(); bank.pool[2].Background:SetAlpha(1)")
    check("art.bank_background_stays_hidden_after_blizzard_repoints_it", w.ev("not Visible(bank.pool[2].Background)"))
    check("art.bank_normal_texture_hidden", w.ev("not Visible(bank.pool[1].NormalTexture)"))
    check("art.nothing_swallowed", w.swallowed() == "", w.swallowed())
    check("art.no_degrade_logs", w.degrade() == "", w.degrade())


def check_untouched() -> None:
    w = World()
    w.run("c1:UpdateItems(); for _, b in ipairs(c1.Items) do BlizzardReset(b) end; c1:UpdateItems()")
    keep = ["IconBorder", "IconOverlay", "IconOverlay2", "NewItemTexture", "BattlepayItemTexture", "flash", "UpgradeIcon",
            "JunkIcon", "IconQuestTexture", "searchOverlay", "ItemContextOverlay", "PushedTexture", "HighlightTexture",
            "ExtendedSlot", "Count"]
    hooked = [field for field in keep if w.ev(f"TouchedByUs(c1.Items[1].{field})")]
    check("keep.no_hook_on_any_untouched_region", not hooked, "hooked by us: " + ", ".join(hooked))
    # the quality border keeps Blizzard's own colour and shown state for a filled slot and an empty one
    r, g, b = (float(v) for v in w.ev("(function() local x = c1.Items[1].IconBorder; local r, g, b = x:GetVertexColor(); return {r, g, b} end)()").values())
    check("keep.icon_border_colour_is_blizzards", near(r, 0.1) and near(g, 0.9) and near(b, 0.2), f"{r},{g},{b}")
    check("keep.icon_border_shown_for_a_filled_slot_only", w.ev("c1.Items[1].IconBorder:IsShown() and not c1.Items[2].IconBorder:IsShown()"))
    check("keep.icon_border_alpha_untouched", w.ev("c1.Items[1].IconBorder:GetAlpha() == 1"))
    check("keep.new_item_glow_alpha_left_to_blizzard", w.ev("c1.Items[1].NewItemTexture:GetAlpha() == 0 and c1.Items[1].flash:GetAlpha() == 0"))
    w.run("c1.Items[1].NewItemTexture:SetAlpha(0.7)")
    check("keep.new_item_glow_alpha_write_is_not_reverted", w.ev("c1.Items[1].NewItemTexture:GetAlpha() == 0.7"))
    check("keep.count_restyled_to_mono_as_before", w.ev("c1.Items[1].Count._font[1] == 'mono'"))
    check("keep.nothing_swallowed", w.swallowed() == "", w.swallowed())


def check_plate_and_border() -> None:
    w = World()
    for _ in range(3):
        w.run("c1:UpdateItems(); comb:UpdateItems(); c1:GenerateSlots(); bank.RefreshAllItemsForSelectedTab(bank)")
    w.run("comb:GenerateSlots(); comb:UpdateItems(); bank.GenerateItemSlotsForSelectedTab(bank)")
    for expr in ("c1.Items[1]", "bank.pool[1]"):          # a container slot and a pooled bank slot
        check(f"plate.{expr}_one_plate", w.ev(f"RegionCount({expr}, 'plate') == 1"), str(w.ev(f"RegionCount({expr}, 'plate')")))
        check(f"plate.{expr}_one_border_ring", w.ev(f"RegionCount({expr}, 'ring') == 1"))
        check(f"plate.{expr}_skinned_once", w.ev(f"Count('SkinCutButton', {expr}) == 1"), str(w.ev(f"Count('SkinCutButton', {expr})")))
    plate = dict(w.ev("(function() local c = nil; for _, x in ipairs(CALLS) do if x[1] == 'AddCut2Texture' and x[2] == c1.Items[1] then c = x end end; if not c then return {} end; return { path = c[3], layer = c[4], sub = c[5] } end)()").items())
    check("plate.is_the_cut2_button_texture_at_background_minus_8",
          plate == {"path": "slice_cut2_button.tga", "layer": "BACKGROUND", "sub": -8}, str(plate))
    opts = w.ev("(function() for _, x in ipairs(CALLS) do if x[1] == 'SkinCutButton' and x[2] == c1.Items[1] then return x[3].count == c1.Items[1].Count end end end)()")
    check("plate.border_is_skincutbutton_with_the_count", bool(opts))
    check("plate.no_plain_skinbutton_call_left", w.ev("Count('SkinButton') == 0"))
    # hooks installed once per region / per button method however many passes ran
    check("plate.normal_region_alpha_hooked_once", w.ev("HookCount(c1.Items[1].NormalTexture, 'SetAlpha') == 1"),
          str(w.ev("HookCount(c1.Items[1].NormalTexture, 'SetAlpha')")))
    # the engine does not write alpha through SetAtlas / SetTexture, so the art regions carry no hook for them
    check("plate.art_regions_have_no_atlas_or_texture_hook",
          w.ev("HookCount(c1.Items[1].NormalTexture, 'SetAtlas') == 0 and HookCount(c1.Items[1].NormalTexture, 'SetTexture') == 0 "
               "and HookCount(bank.pool[1].Background, 'SetAtlas') == 0"))
    check("plate.icon_hooked_once", w.ev("HookCount(c1.Items[1].icon, 'SetAtlas') == 1"), str(w.ev("HookCount(c1.Items[1].icon, 'SetAtlas')")))
    check("plate.container_update_hooked_once", w.ev("HookCount(c1, 'UpdateItems') == 1 and HookCount(comb, 'UpdateItems') == 1"))
    check("plate.combined_background_hooked_once", w.ev("HookCount(comb.Items[1].ItemSlotBackground, 'SetAlpha') == 1"))

    # an empty slot shows only our plate and ring (no Blizzard slot art at all)
    w.run("BlizzardReset(c1.Items[2]); c1.Items[2]:SetItemButtonTexture(nil); c1:UpdateItems()")
    check("plate.empty_slot_shows_only_plate_and_ring", tags(w, "c1.Items[2]") == "plate,ring", tags(w, "c1.Items[2]"))
    w.run("bank.RefreshAllItemsForSelectedTab(bank); bank.pool[2]:UpdateBackgroundForBankType()")
    check("plate.empty_bank_slot_shows_only_plate_and_ring", tags(w, "bank.pool[2]") == "plate,ring", tags(w, "bank.pool[2]"))
    w.run("comb.Items[2]:SetItemButtonTexture(nil); comb:UpdateItems()")
    check("plate.empty_combined_slot_shows_only_plate_and_ring", tags(w, "comb.Items[2]") == "plate,ring", tags(w, "comb.Items[2]"))
    # a filled slot: icon (the item) on top of the plate, and the quality border is Blizzard's, shown
    check("plate.filled_slot_has_icon_plate_ring_and_the_quality_border", tags(w, "c1.Items[1]") == "IconBorder,icon,plate,ring", tags(w, "c1.Items[1]"))
    check("plate.nothing_swallowed", w.swallowed() == "", w.swallowed())
    check("plate.no_degrade_logs", w.degrade() == "", w.degrade())


def check_hold_retry() -> None:
    # A region whose SetAlpha hook cannot be installed is not recorded as held: the next pass tries again.
    w = World(pre="""
        local real = hooksecurefunc
        FAIL_HOOK_ON = c2.Items[1].NormalTexture
        hooksecurefunc = function(obj, name, fn)
            if obj == FAIL_HOOK_ON and name == "SetAlpha" then error("hook refused") end
            return real(obj, name, fn)
        end
    """)
    check("hold.a_failed_hook_install_leaves_no_hook", w.ev("HookCount(c2.Items[1].NormalTexture, 'SetAlpha') == 0"))
    check("hold.the_failed_install_was_not_swallowed_silently", "hook refused" in w.swallowed(), w.swallowed())
    w.run("FAIL_HOOK_ON = nil; c2:UpdateItems()")
    check("hold.the_next_pass_retries_and_holds", w.ev("HookCount(c2.Items[1].NormalTexture, 'SetAlpha') == 1"),
          str(w.ev("HookCount(c2.Items[1].NormalTexture, 'SetAlpha')")))
    w.run("c2.Items[1].NormalTexture:SetAlpha(1)")
    check("hold.the_retried_hold_works", w.ev("not Visible(c2.Items[1].NormalTexture)"))
    w.run("c2:UpdateItems(); c2:UpdateItems()")
    check("hold.a_held_region_is_not_hooked_again", w.ev("HookCount(c2.Items[1].NormalTexture, 'SetAlpha') == 1"))


def dot_colour(w: World, btn: str) -> tuple[float, float, float]:
    r, g, b = (float(v) for v in w.ev(f"(function() local r, g, b = DotsOf({btn})[1]:GetVertexColor(); return {{r, g, b}} end)()").values())
    return r, g, b


def check_money(db: dict) -> None:
    w = World()
    gold = "c1.MoneyFrame.GoldButton"

    # colour and font, all three denominations on one frame: text and dot
    for key, color in (("GoldButton", db["gold"]), ("SilverButton", db["silver"]), ("CopperButton", db["copper"])):
        btn = f"c1.MoneyFrame.{key}"
        fs = dict(w.ev(f"(function() local f = {btn}.Text; local p, s = f:GetFont(); local r, g, b = f:GetTextColor(); return {{ path = p, size = s, r = r, g = g, b = b }} end)()").items())
        check(f"money.{key}.text_is_mono_at_the_data_bar_size_and_colour",
              fs["path"] == "mono" and fs["size"] == db["font"] and near(fs["r"], color[0]) and near(fs["g"], color[1]) and near(fs["b"], color[2]), str(fs))
        dr, dg, db_ = dot_colour(w, btn)
        check(f"money.{key}.dot_is_tinted_like_the_data_bar", near(dr, color[0]) and near(dg, color[1]) and near(db_, color[2]), f"{dr},{dg},{db_}")

    # structure, once per frame on the gold button
    for expr, label in (("c1.MoneyFrame", "container"), ("comb.MoneyFrame", "combined bags"), ("bank.MoneyFrame.MoneyDisplay", "bank")):
        btn = f"{expr}.GoldButton"
        tag = f"money.{label}"
        check(f"{tag}.blizzard_coin_hidden", w.ev(f"not Visible({btn}.NormalTexture)"))
        dots = list(w.ev(f"DotsOf({btn})").values())
        check(f"{tag}.one_dot", len(dots) == 1, str(len(dots)))
        if len(dots) != 1:
            continue
        d = dict(w.ev(f"(function() local t = DotsOf({btn})[1]; local p = t._pts[1]; "
                      f"return {{ tex = t._texture, w = t._w, h = t._h, blend = t._blend, "
                      f"point = p[1], rel = p[2] == {btn}.Text, relPoint = p[3], x = p[4], y = p[5] }} end)()").items())
        check(f"{tag}.dot_is_the_data_bar_glow_texture_and_size", d["tex"] == db["texture"] and d["w"] == db["size"] and d["h"] == db["size"], str(d))
        check(f"{tag}.dot_is_added", d["blend"] == "ADD", str(d))
        check(f"{tag}.dot_sits_before_its_number_with_the_data_bar_gap",
              d["point"] == "RIGHT" and d["rel"] and d["relPoint"] == "LEFT" and d["x"] == -db["gap"] and d["y"] == 0, str(d))
    # the Blizzard update path (every MoneyFrame_Update re-inits the coin textures) must not bring the coin back
    w.run("for _, m in ipairs({ c1.MoneyFrame, comb.MoneyFrame, bank.MoneyFrame.MoneyDisplay }) do m:__update() end")
    check("money.coin_stays_hidden_through_the_update_path",
          w.ev("not Visible(c1.MoneyFrame.GoldButton.NormalTexture) and not Visible(c1.MoneyFrame.CopperButton:GetNormalTexture())"))
    w.run("for _, m in ipairs({ c1.MoneyFrame, bank.MoneyFrame.MoneyDisplay }) do m:__colorblind(); m:__update() end")
    check("money.a_recreated_coin_texture_is_hidden_too",
          w.ev("not Visible(c1.MoneyFrame.GoldButton:GetNormalTexture()) and not Visible(bank.MoneyFrame.MoneyDisplay.SilverButton:GetNormalTexture())"))
    # Blizzard's SetMoneyFrameColor swaps the font object on each button; the data bar font and colour come back
    w.run(f"{gold}:SetNormalFontObject({{ path = 'blizz-red', size = 13, r = 1, g = 0, b = 0 }})")
    fs = dict(w.ev(f"(function() local f = {gold}.Text; local p, s = f:GetFont(); local r, g, b = f:GetTextColor(); return {{ path = p, size = s, r = r, g = g, b = b }} end)()").items())
    check("money.font_object_swap_is_restyled", fs["path"] == "mono" and fs["size"] == db["font"] and near(fs["r"], db["gold"][0]), str(fs))
    # a second skin pass or a container re-show adds nothing
    for _ in range(3):
        w.run("for _, c in ipairs({ c1, comb }) do for _, fn in ipairs(c._scripts.OnShow or {}) do fn(c) end end; c1:UpdateItems()")
    check("money.dots_stay_one_per_button_across_reshows",
          w.ev("#DotsOf(c1.MoneyFrame.GoldButton) == 1 and #DotsOf(c1.MoneyFrame.CopperButton) == 1 and #DotsOf(bank.MoneyFrame.MoneyDisplay.GoldButton) == 1"))
    check("money.old_name_based_helper_not_used_when_styled",
          w.ev("Count('TryStyleMoney', c1) == 0 and Count('TryStyleMoney', comb) == 0"), str(w.ev("Count('TryStyleMoney')")))
    check("money.nothing_swallowed", w.swallowed() == "", w.swallowed())
    check("money.no_degrade_logs", w.degrade() == "", w.degrade())


def check_colorblind() -> None:
    # Colorblind mode: Blizzard drops the coin gap and prints g/s/c letters, so a dot would sit on the previous
    # number. The dots go away while it is on and come back when it is off, driven by the money updates.
    all_dots = "DotShown(c1.MoneyFrame.GoldButton) or DotShown(c1.MoneyFrame.SilverButton) or DotShown(c1.MoneyFrame.CopperButton)"
    w = World()
    check("colorblind.off_shows_the_dots", w.ev("DotShown(c1.MoneyFrame.GoldButton) and DotShown(c1.MoneyFrame.SilverButton) and DotShown(c1.MoneyFrame.CopperButton)"))
    w.run("CVARS.colorblindMode = '1'; c1.MoneyFrame:__update(); bank.MoneyFrame.MoneyDisplay:__update()")
    check("colorblind.on_hides_every_dot_on_the_next_update", w.ev(f"not ({all_dots}) and not DotShown(bank.MoneyFrame.MoneyDisplay.GoldButton)"))
    w.run("c1.MoneyFrame.GoldButton:SetNormalFontObject({ path = 'blizz-red', size = 13, r = 1, g = 0, b = 0 })")
    check("colorblind.stays_hidden_through_a_font_object_swap", w.ev("not DotShown(c1.MoneyFrame.GoldButton)"))
    w.run("CVARS.colorblindMode = '0'; c1.MoneyFrame:__update()")
    check("colorblind.off_again_brings_the_dots_back", w.ev("DotShown(c1.MoneyFrame.GoldButton) and DotShown(c1.MoneyFrame.CopperButton)"))
    check("colorblind.nothing_swallowed", w.swallowed() == "", w.swallowed())

    w = World(pre="CVARS.colorblindMode = '1'")
    check("colorblind.already_on_at_skin_time_hides_the_dots", w.ev(f"not ({all_dots})"))
    # a client without CVarCallbackRegistry falls back to the plain CVar read
    w = World(pre="CVarCallbackRegistry = nil; CVARS.colorblindMode = '1'")
    check("colorblind.falls_back_to_getcvar", w.ev(f"not ({all_dots})"))
    w = World(pre="CVarCallbackRegistry = nil; GetCVar = nil; CVARS.colorblindMode = '1'")
    check("colorblind.no_cvar_api_at_all_leaves_the_dots_shown", w.ev("DotShown(c1.MoneyFrame.GoldButton)") and w.swallowed() == "", w.swallowed())


def check_absent() -> None:
    # --- no Theme.AddCut2Texture: the slot still skins (border, count), no plate, no throw, one log at most
    w = World(with_plate_helper=False)
    w.run("c1:UpdateItems(); c1:UpdateItems()")
    check("absent.no_plate_helper_still_skins_the_border", w.ev("Count('SkinCutButton', c1.Items[1]) == 1"))
    check("absent.no_plate_helper_makes_no_plate", w.ev("RegionCount(c1.Items[1], 'plate') == 0"))
    check("absent.no_plate_helper_still_hides_blizzard_art", w.ev("not Visible(c1.Items[2].NormalTexture) and not Visible(c1.Items[2].icon)"))
    check("absent.no_plate_helper_logs_once", w.degrade().count("bags_plate") == 1, w.degrade())
    check("absent.no_plate_helper_nothing_swallowed", w.swallowed() == "", w.swallowed())

    # --- a bare button (no NormalTexture, no icon, no setters) and a container with no MoneyFrame
    w = World()
    w.run("""
        bare = CreateFrame("Button", nil, UIParent)
    """)
    # the hook Bags.lua installed on ContainerFrame1 now walks a button with no art regions at all
    w.run("c1.Items = { bare }; c1:UpdateItems()")
    check("absent.bare_button_does_not_throw", w.swallowed() == "", w.swallowed())
    check("absent.bare_button_still_gets_a_plate", w.ev("RegionCount(bare, 'plate') == 1"))
    # a container with no MoneyFrame at all (removed before Bags.lua loads and skins it) falls back to the
    # name-based helper exactly once and throws nothing
    w2 = World(pre="c2.MoneyFrame = nil")
    check("absent.container_without_money_frame_uses_the_name_based_helper_once", w2.ev("Count('TryStyleMoney', c2) == 1"),
          str(w2.ev("Count('TryStyleMoney', c2)")))
    check("absent.container_without_money_frame_swallows_nothing", w2.swallowed() == "", w2.swallowed())


def main() -> int:
    db = databar_money()
    check_art()
    check_untouched()
    check_plate_and_border()
    check_hold_retry()
    check_money(db)
    check_colorblind()
    check_absent()
    print(f"\n{CHECKS} checks, {len(FAILS)} failed" if FAILS else f"\nall {CHECKS} checks passed")
    return len(FAILS)


if __name__ == "__main__":
    sys.exit(main())
