#!/usr/bin/env python3
"""Headless check of Bags.lua: our slot plate only (no Blizzard slot art) and the data bar money line.

Runs the real addons/forever-stuwave/Bags.lua under lupa against a small mock WoW API. The mock models
the Blizzard structures the file touches, the way the 12.1 FrameXML builds them (corroborating only; the
target client is 16001):

  * an item slot is an ItemButton: `icon`, `Count`, `IconBorder` (Interface\\Common\\WhiteIconFrame, shown and tinted by
    SetItemButtonQuality for every Common-and-up item), `IconOverlay`, `NewItemTexture`, `flash`, `UpgradeIcon`,
    `JunkIcon`, `searchOverlay`, ... and the button's own NormalTexture (Interface\\Buttons\\UI-Quickslot2, the
    square slot frame), Pushed/Highlight textures; ItemButtonMixin:SetAlpha writes alpha through to the icon and the
    IconBorder (Blizzard_ItemButton/Shared/ItemButtonTemplate.lua);
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

  * item slots: Blizzard's normal texture, the combined-bags background, the bank background, the empty-slot
    icon art and the quality IconBorder (the square rounded frame a FILLED slot wears) are hidden after the skin
    AND stay hidden after Blizzard re-shows them (alpha write, a region created later, a repaint that re-shows and
    re-tints the border, ItemButtonMixin:SetAlpha); a region whose hook install failed is retried on the next
    pass; a filled slot keeps its icon; Blizzard's shown state and colour of the IconBorder are left alone (only
    its alpha is held);
  * IconOverlay, NewItemTexture, flash, UpgradeIcon, JunkIcon, IconQuestTexture, search overlay, pushed and
    highlight textures, ExtendedSlot are never hooked, hidden or recoloured by us;
  * our plate (cut2 button texture, BACKGROUND -8) and border (SkinCutButton) exist once per button across
    repeated UpdateItems; an empty slot shows only the plate and the ring; hooks are installed once;
  * the icon corners: a MaskTexture does not clip on this client, so a filled slot's square icon is cut by an opaque
    panel-coloured wedge (the cut2 erase nine-slice, OVERLAY -1: above the icon, under the ring and the glow) in the TOP-LEFT
    and BOTTOM-RIGHT corners; it shows only while the icon holds an item (never on an empty slot, whichever way the
    icon is emptied or filled, with or without an UpdateItems pass), is made once per button, changes nothing
    protected in combat, and a missing Theme piece degrades to the plain icon with one log;
  * the money line (container, combined bags, bank) follows DataBar.lua's GOLD segment: same coin colours, dot
    texture and size, text font size and dot to text gap, all read from DataBar.lua, never retyped; the
    Blizzard coin atlas stays hidden through the update path, a recreated texture and a font object swap; in
    colorblind mode (letters instead of coins, no coin gap) the dots are hidden and come back when it is off;
  * the gamepad bag bar (Blizzard's GamepadBagBar, a child of the combined bags that covers the Clean Up button)
    is hidden while no controller is connected (C_GamePad missing, disabled, or GetAllDeviceIDs empty), stays
    hidden when Blizzard shows it again (Show, SetShown, OnShow), is never forced back on (a controller appearing just
    stops us re-hiding it), is left alone while one is connected (an erroring C_GamePad counts as one), is hidden in combat
    too, and nothing errors when C_GamePad,
    GamepadBagBar or one of the events is absent;
  * the bag bar hover (FS.BagHighlight.Set / Clear, called by BagBar.lua): the item slots of the hovered bag, in the
    individual windows or the combined one, get a cut2 ring and glow in the hover colour (Theme.COLOR_HEALTH) and no
    other slot does; Clear removes them; a closed window shows nothing and no error; closing a window while hovering
    clears it and reopening lights it again; a pooled button re-used for another bag follows its new bag on the next
    UpdateItems; in combat the item buttons (protected) get no Show/Hide/SetAttribute/SetPoint/SetSize/SetParent, only
    our regions change; a secret or missing GetBagID, a missing Theme piece and the bank are harmless;
  * the quality ring: a filled slot's ring (the purple outline) is tinted by item quality, read per slot from
    C_Container.GetContainerItemInfo (a bank slot: the itemInfo Blizzard just read): Poor grey, Common the default ring
    (the dark violet Theme.COLOR_BAG_RING, #5b2d9e), Uncommon, Rare, Epic, Legendary and up the colour Blizzard's bags
    use (player overrides included). Empty slots, unknown or secret answers keep the default ring; it follows every
    UpdateItems and bank refresh, the icon emptying without a pass, combat (nothing protected is touched) and a
    missing colour source (default ring, one log);
  * nothing errors when a region, a method or Theme.AddCut2Texture is absent.

    python3 tools/bags-harness.py

Exit 0 = every check passed; otherwise the number of failures.
"""

from __future__ import annotations

import math
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
THEME_LUA = ADDON / "Core/Theme.lua"
HELDART_LUA = ADDON / "Core/HeldArt.lua"
BUTTONSKINS_LUA = ADDON / "Core/ButtonSkins.lua"


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


def bag_ring_table() -> str:
    """Theme.COLOR_BAG_RING exactly as Theme.lua writes it: read, never retyped."""
    m = re.search(r"Theme\.COLOR_BAG_RING\s*=\s*(\{[^}]*\})", THEME_LUA.read_text(encoding="utf-8"))
    if not m:
        sys.exit("Theme.lua: COLOR_BAG_RING not found")
    return m.group(1)


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
-- geometry the window layout reads: a rect is { left, right, top, bottom } in screen units (y up), set by PlaceGrid
function Class:GetLeft() return self._rect and self._rect[1] end
function Class:GetRight() return self._rect and self._rect[2] end
function Class:GetTop() return self._rect and self._rect[3] end
function Class:GetBottom() return self._rect and self._rect[4] end
function Class:GetParent() return self._parent end
function Class:SetParent(p) self._parent = p end
function Class:SetFrameLevel(l) self._level = l end
function Class:GetFrameLevel() return self._level or 1 end
function Class:EnableMouse(v) self._mouse = v end
function Class:SetHitRectInsets(l, r, t, b) self._hit = { l, r, t, b }; self._hitCalls = (self._hitCalls or 0) + 1 end
function Class:IsProtected() return self._protected == true end
function Class:SetSnapToPixelGrid(v) self._snap = v end
function Class:SetTexelSnappingBias(v) self._bias = v end
function Class:SetColorTexture(r, g, b, a) self._color = { r, g, b, a }; self._texture = "color" end
function Class:SetAllPoints(f) self._pts = { { "ALL", f } } end
function Class:SetTextInsets(...) self._insets = { ... } end
function Class:SetJustifyH(j) self._jh = j end
function Class:SetJustifyV(j) self._jv = j end
function Class:SetHorizTile() end
function Class:SetVertTile() end
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

-- events: RegisterEvent throws on a name the client does not know, like the engine; OnEvent scripts are driven by FireEvent
KNOWN_EVENTS = { GAME_PAD_CONNECTED = true, GAME_PAD_DISCONNECTED = true, GAME_PAD_ACTIVE_CHANGED = true, PLAYER_ENTERING_WORLD = true,
    PLAYER_MONEY = true, PLAYER_REGEN_ENABLED = true }
EVENT_FRAMES = {}
function Class:RegisterEvent(ev)
    if not KNOWN_EVENTS[ev] then error("Frame:RegisterEvent(): Attempt to register unknown event \"" .. tostring(ev) .. "\"") end
    self._events = self._events or {}
    self._events[ev] = true
    EVENT_FRAMES[#EVENT_FRAMES + 1] = self
end
function Class:SetScript(which, fn) self._set = self._set or {}; self._set[which] = fn end
function FireEvent(ev)
    for _, f in ipairs(EVENT_FRAMES) do
        if f._events[ev] and f._set and f._set.OnEvent then f._set.OnEvent(f, ev) end
    end
end
-- combat: DeferCombat queues while INCOMBAT, like the real wrapper waiting for PLAYER_REGEN_ENABLED
INCOMBAT, DEFERRED = false, {}
function InCombatLockdown() return INCOMBAT end
function EndCombat() INCOMBAT = false; local q = DEFERRED; DEFERRED = {}; for _, fn in ipairs(q) do fn() end end

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
PROTECTED_CALLS = {}
function MkItemButton(parent, kind)
    local b = new("Button", parent)
    b._kind = "Button"
    -- Item buttons are secure: in combat the engine refuses these on them (recorded, never our business).
    for _, method in ipairs({ "Show", "Hide", "SetShown", "SetPoint", "ClearAllPoints", "SetSize", "SetWidth", "SetHeight", "SetParent", "SetAttribute" }) do
        b[method] = function(self, ...)
            if INCOMBAT then PROTECTED_CALLS[#PROTECTED_CALLS + 1] = method; return end
            if Class[method] then return Class[method](self, ...) end
        end
    end
    b.GetBagID = function(self) return self._bagID end
    b.GetID = function(self) return self._slot or 0 end
    b._k = kind
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
    if b._k == "bank" then b.itemInfo = info and { iconFileID = info.icon, quality = info.q } or nil end   -- BankPanelItemButtonMixin:RefreshItemInfo
    b:SetItemButtonTexture(info and info.icon or nil)
    if info and info.quality then
        b.IconBorder:SetVertexColor(info.quality[1], info.quality[2], info.quality[3])
        b.IconBorder:Show()
    else
        b.IconBorder:Hide()
    end
end

-- Mirrors ItemButtonMixin:SetAlpha (12.1 source, Blizzard_ItemButton/Shared/ItemButtonTemplate.lua lines 233-239), which
-- also writes IconOverlay, Stock and Count; only the two regions this file reads are modelled. A button alpha write goes
-- to the icon and to the IconBorder as a plain region SetAlpha, whatever alpha we are holding there. If the source line
-- changes, change this with it.
function BlizzardButtonAlpha(b, a)
    b.icon:SetAlpha(a)
    b.IconBorder:SetAlpha(a)
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

-- Blizzard's quality colours. The bag set (ColorManager.GetColorDataForBagItemQuality, no Poor entry, a player's colour
-- override already applied) and ITEM_QUALITY_COLORS (Poor included) differ here so a check can tell which one was read.
BAG_COLORS = {
    [1] = { r = 0.70, g = 0.70, b = 0.70 }, [2] = { r = 0.12, g = 1.00, b = 0.00 }, [3] = { r = 0.00, g = 0.44, b = 0.87 },
    [4] = { r = 0.64, g = 0.21, b = 0.93 }, [5] = { r = 1.00, g = 0.50, b = 0.00 }, [6] = { r = 0.90, g = 0.80, b = 0.50 },
    [7] = { r = 0.00, g = 0.80, b = 1.00 }, [8] = { r = 0.00, g = 0.80, b = 1.00 },
}
ITEM_QUALITY_COLORS = {
    [0] = { r = 0.62, g = 0.62, b = 0.62 }, [1] = { r = 1.00, g = 1.00, b = 1.00 }, [2] = { r = 0.10, g = 0.90, b = 0.10 },
    [3] = { r = 0.10, g = 0.40, b = 0.80 }, [4] = { r = 0.60, g = 0.20, b = 0.90 }, [5] = { r = 0.90, g = 0.45, b = 0.05 },
    [6] = { r = 0.85, g = 0.75, b = 0.45 }, [7] = { r = 0.05, g = 0.75, b = 0.95 },
}
ColorManager = {
    GetColorDataForBagItemQuality = function(q) return BAG_COLORS[q] end,
    GetColorDataForItemQuality = function(q) return ITEM_QUALITY_COLORS[q] end,
}
function RingColor(b)
    local r, g, bl, a = b.fsSkin.border.ring:GetVertexColor()
    return { r, g, bl, a }
end

-- C_Container.GetContainerItemInfo answers from the container that holds (bag, slot); an info's `q` is the item quality
ALL_CONTAINERS, INFO_QUERIES = {}, 0
C_Container = { GetContainerItemInfo = function(bag, slot)
    INFO_QUERIES = INFO_QUERIES + 1
    for _, c in ipairs(ALL_CONTAINERS) do
        for i, b in ipairs(c.Items) do
            if b._bagID == bag and b._slot == slot then
                local info = c.infos[i]
                return info and { iconFileID = info.icon, quality = info.q } or nil
            end
        end
    end
end }

function MkContainer(name, nButtons, combined, bag)
    local c = CreateFrame("Frame", name, UIParent)
    c.isCombined = combined or false
    c.Items = {}
    for i = 1, nButtons do c.Items[i] = MkItemButton(c, "container"); c.Items[i]._bagID = bag; c.Items[i]._slot = i end
    ALL_CONTAINERS[#ALL_CONTAINERS + 1] = c
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
    -- PortraitFrameFlat's own controls: the close button (art regions), the portrait dropdown with its round highlight
    c.CloseButton = new("Button", c)
    tex(c.CloseButton, "closeArt", { file = "Interface\\Buttons\\UI-Panel-MinimizeButton-Up" })
    c.PortraitButton = new("Button", c)
    c.PortraitButton.Highlight = tex(c.PortraitButton, "Highlight", { atlas = "bags-roundhighlight" })
    -- ContainerFrameMixin:UpdateSearchBox (ContainerFrame.lua 969): the backpack and the combined window own the one
    -- search box and sort button, re-parent and re-anchor them on every Update(), and Update() runs UpdateItems after it
    c.UpdateSearchBox = function(self)
        if self._backpack or self.isCombined then
            BagItemSearchBox:SetParent(self); BagItemSearchBox:ClearAllPoints()
            BagItemSearchBox:SetPoint("TOPLEFT", self, "TOPLEFT", self.isCombined and 62 or 42, -37)
            BagItemSearchBox:SetWidth(self.isCombined and 330 or 96)
            BagItemSearchBox:Show()
            BagItemAutoSortButton:SetParent(self)
            BagItemAutoSortButton:SetPoint("TOPRIGHT", self, "TOPRIGHT", -9, -34)      -- no ClearAllPoints, like Blizzard
            BagItemAutoSortButton:Show()
        elseif BagItemSearchBox._parent == self then
            BagItemSearchBox:Hide(); BagItemAutoSortButton:Hide()
        end
    end
    c.Update = function(self) self:UpdateSearchBox(); self:UpdateItems() end
    return c
end

-- The one search box and sort button Blizzard shares between the backpack and the combined window
-- (BagSearchBoxTemplate: Left/Middle/Right border art, the magnifier, the placeholder, a clear button).
function MkBagControls()
    local e = new("EditBox", UIParent)
    e._kind = "EditBox"; e._shown = false
    e.Left = tex(e, "sbLeft", { file = "Interface\\Common\\Common-Input-Border-L" })
    e.Middle = tex(e, "sbMiddle", { file = "Interface\\Common\\Common-Input-Border-M" })
    e.Right = tex(e, "sbRight", { file = "Interface\\Common\\Common-Input-Border-R" })
    e.searchIcon = tex(e, "searchIcon", { atlas = "common-search-magnifyingglass" })
    e.Instructions = region(e, "FontString", "Instructions")
    e.clearButton = new("Button", e)
    e.SetFocus = function(self) self._focus = true end
    _G.BagItemSearchBox = e
    local s = new("Button", UIParent)
    s._kind = "Button"; s._shown = false
    s.NormalTexture = tex(s, "sortNormal", { atlas = "bags-button-autosort-up" })
    s._normal = s.NormalTexture
    s.PushedTexture = tex(s, "sortPushed", { shown = false, atlas = "bags-button-autosort-down" })
    s.HighlightTexture = tex(s, "sortHighlight", { shown = false, file = "Interface\\Buttons\\ButtonHilight-Square" })
    _G.BagItemAutoSortButton = s
end

-- BackpackTokenFrame as BackpackTokenFrameTemplate and ContainerFrameTokenWatcherMixin build it (retail 12.1.0 Blizzard_TokenUI,
-- ContainerFrame.lua): a child of the container with a Border frame (Left / Middle / Right art), pooled token Buttons (Icon, Count)
-- that Update re-points, and the container's UpdateTokenTracker / UpdateCurrencyFrames (the strip is anchored to the container's
-- bottom with two points). Built in a World's `pre`, before Bags.lua hooks the container's methods.
function MkTracker(c, n)
    local t = CreateFrame("Frame", "BackpackTokenFrame", c)
    t._n, t._pool = n or 2, {}
    t.Border = CreateFrame("Frame", nil, t)
    t.Border.Left = tex(t.Border, "tkLeft", { atlas = "common-currencybox-left" })
    t.Border.Middle = tex(t.Border, "tkMiddle", { atlas = "_common-currencybox-center" })
    t.Border.Right = tex(t.Border, "tkRight", { atlas = "common-currencybox-right" })
    t:SetSize(1, 17)
    t.Tokens = {}
    t.Update = function(self)
        self.Tokens = {}
        for i = 1, self._n do
            local b = self._pool[i]
            if not b then
                b = CreateFrame("Button", nil, self)
                b.Icon = tex(b, "tkIcon", { file = "Interface\\Icons\\token" })
                b.Count = region(b, "FontString", "tkCount")
                self._pool[i] = b
            end
            b.Count:SetText(tostring(100 * i))
            self.Tokens[i] = b
        end
    end
    c.UpdateCurrencyFrames = function(self)
        t:ClearAllPoints()
        t:SetPoint("BOTTOMLEFT", self, "BOTTOMLEFT", 8, 8)
        t:SetPoint("BOTTOMRIGHT", self, "BOTTOMRIGHT", -8, 8)
    end
    c.UpdateTokenTracker = function(self)
        t:SetShown(t._n > 0 and self:IsShown())
        self:UpdateCurrencyFrames()
    end
    local update = c.Update
    c.Update = function(self) update(self); self:UpdateTokenTracker() end
    t:Update()
    return t
end

-- Lays a container out the way Blizzard does: the item grid at a pitch with the frame padding around it
-- (combined: left 7, right 8, top 75, bottom 28). `o` = { left, top, cols, size, pitch, padL, padR, padT, padB }.
function PlaceGrid(c, o)
    local n, cols = #c.Items, o.cols
    local rows = math.ceil(n / cols)
    local gl, gt = o.left + o.padL, o.top - o.padT
    for i, b in ipairs(c.Items) do
        local col, row = (i - 1) % cols, math.floor((i - 1) / cols)
        local l, t = gl + col * o.pitch, gt - row * o.pitch
        b._rect = { l, l + o.size, t, t - o.size }
    end
    local gr = gl + (cols - 1) * o.pitch + o.size
    local gb = gt - (rows - 1) * o.pitch - o.size
    c._rect = { o.left, gr + o.padR, o.top, gb - o.padB }
    c._grid = { gl, gr, gt, gb }
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
SECRET_IDS = false
SECRET_VALUE = {}                 -- an opaque stand-in for a secret icon texture
FS = {
    IsSecret = function(v) return SECRET_IDS or v == SECRET_VALUE end,
    LogDegradeOnce = function(key, msg) DEGRADE[#DEGRADE + 1] = key end,
    PanelSkins = {
        RequireExport = function(fn) return fn ~= nil end,
        DeferCombat = function(fn) if INCOMBAT then DEFERRED[#DEFERRED + 1] = fn else fn() end end,
        TryStyleMoney = function(frame) CALLS[#CALLS + 1] = { "TryStyleMoney", frame } end,
        RegisterInspect = function() end,
    },
    Theme = {
        FONT_MONO = "mono", SLICE_CUT2_BUTTON_TEXTURE = "slice_cut2_button.tga", SLICE_CUT_MARGIN = 6,
        SLICE_CUT2_OUTLINE_TEXTURE = "slice_cut2_outline.tga", SLICE_CUT2_GLOW_TEXTURE = "slice_cut2_glow.tga",
        SLICE_CUT2_GLOW_PAD = 4, SLICE_CUT2_GLOW_MARGIN = 10, COLOR_HEALTH = { 1, 0.18, 0.592, 1 },
        SLICE_CUT2_ERASE_TEXTURE = "slice_cut2_erase_c6.tga", COLOR_BG = { 0.102, 0.063, 0.145, 0.80 },
        COLOR_BORDER = { 0.659, 0.333, 0.969, 1 }, COLOR_POWER = { 0.133, 0.878, 1, 1 },
        COLOR_BUTTON_INK = { 0.090, 0.047, 0.165, 1 }, COLOR_BAR_TRACK = { 0.039, 0.016, 0.086, 1 },
        ApplyNineSlice = function(t, margin) t._slice = margin; return true end,
        SnapCut = function(c) return c end,
        SkinPanel = function(frame, opts)
            CALLS[#CALLS + 1] = { "SkinPanel", frame, opts }
            local fill = frame:CreateTexture(nil, "BACKGROUND", nil, -2)
            fill._tag = "panelFill"; fill:SetTexture("slice_fill.tga")
        end,
        StripBlizzardChrome = function(frame) CALLS[#CALLS + 1] = { "StripBlizzardChrome", frame } end,
        AddCutSliceFill = function(panel, color, radius)
            CALLS[#CALLS + 1] = { "AddCutSliceFill", panel, radius }
            local t = themeTex(panel, "slice_cut2_fill.tga", "BACKGROUND", -1, "face")
            t:SetVertexColor(color[1], color[2], color[3], color[4] or 1)
            t._chamfer = radius
            return t
        end,
        ApplyMono = function(fs, size, color)
            CALLS[#CALLS + 1] = { "ApplyMono", fs, size, color }
            fs:SetFont("mono", size, "")
            local c = color or { 1, 1, 1 }
            fs:SetTextColor(c[1], c[2], c[3], 1)
        end,
        AddCut2Texture = function(frame, path, color, layer, sub)
            CALLS[#CALLS + 1] = { "AddCut2Texture", frame, path, layer, sub }
            local tag = layer == "BACKGROUND" and "plate" or (path:find("erase", 1, true) and "corners" or (sub == -3 and "well" or "cut2"))
            local t = themeTex(frame, path, layer, sub, tag)
            if color then t:SetVertexColor(color[1], color[2], color[3], color[4] or 1) end
            return t
        end,
    },
}
ES = 1                            -- physical pixels per UI unit the mock reports (FrameHelpers.PixelsPerUnit)
FS.FrameHelpers = { PixelsPerUnit = function() return ES end }
MONEY = 0
function GetMoney() return MONEY end
local function skin(name)
    return function(button, opts)
        CALLS[#CALLS + 1] = { name, button, opts }
        if not button.fsSkin then
            button.fsSkin = { chamfer = (opts and opts.chamfer) or 6 }
            local ring = themeTex(button, "slice_cut2_outline.tga", "OVERLAY", 1, "ring")
            ring:SetVertexColor(0.659, 0.333, 0.969, 1)
            button.fsSkin.border = { ring = ring }
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
    -- Bags.lua holds Blizzard's slot art through FS.HeldArt (Core/HeldArt.lua, loaded before it in the .toc)
    assert(loadstring(HELDART_SRC, "@HeldArt.lua"))("forever-stuwave", FS)
    assert(loadstring(BUTTONSKINS_SRC, "@ButtonSkins.lua"))("forever-stuwave", FS)
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
function CloseWindow(c)           -- Hide plus the OnHide scripts, the way the engine runs them
    c:Hide()
    for _, fn in ipairs(c._scripts.OnHide or {}) do fn(c) end
end
function OpenWindow(c)            -- Show, then the repopulation Blizzard does on show
    c:Show()
    c:UpdateItems()
end
function OpenWindowRefreshFirst(c)  -- UpdateItems while still hidden, then Show (OnShow scripts run, like the engine)
    c:UpdateItems()
    c:Show()
    for _, fn in ipairs(c._scripts.OnShow or {}) do fn(c) end
end
function Lit(b)                   -- ring and glow both shown on this item button
    local hl = b.fsBagHighlight
    return hl ~= nil and hl.ring._shown and hl.glow._shown
end
function AnyLit(b)
    local hl = b.fsBagHighlight
    return hl ~= nil and (hl.ring._shown or hl.glow._shown)
end
function LitSet(c)                -- "1,3" = the item indexes lit in a container
    local out = {}
    for i, b in ipairs(c.Items) do if Lit(b) then out[#out + 1] = i end end
    return table.concat(out, ",")
end
function OpenFull(c)              -- Show, the OnShow scripts, then Blizzard's Update() (search box placement, then UpdateItems)
    c:Show()
    for _, fn in ipairs(c._scripts.OnShow or {}) do fn(c) end
    c:Update()
end
function WellOf(b)
    for _, r in ipairs(b._regions) do if r._tag == "well" then return r end end
end
function WellShown(b)
    local r = WellOf(b)
    return r ~= nil and r._shown and r._alpha > 0
end
function FsFields(t)              -- every string key starting with "fs" that is set on a widget table
    local out = {}
    for k in pairs(t) do if type(k) == "string" and k:sub(1, 2) == "fs" then out[#out + 1] = k end end
    table.sort(out)
    return table.concat(out, ",")
end
function HookNames(obj)
    local out = {}
    for _, h in ipairs(HOOKED) do if h.tbl == obj then out[#out + 1] = h.name end end
    table.sort(out)
    return table.concat(out, ",")
end
function GlyphBox(slot)           -- bounding box, in physical pixels from the slot's top left, of the glyph cells on a plate
    local minx, maxx, miny, maxy
    for _, r in ipairs(slot._regions) do
        if r._tag == "created" and r._color and r._shown then
            local pt = r._pts[#r._pts]
            local x, y = pt[4] * ES, -pt[5] * ES
            local w, h = r._w * ES, r._h * ES
            minx = math.min(minx or x, x); miny = math.min(miny or y, y)
            maxx = math.max(maxx or x + w, x + w); maxy = math.max(maxy or y + h, y + h)
        end
    end
    return { minx, maxx, miny, maxy }
end
function RegionCount(b, tag)
    local n = 0
    for _, r in ipairs(b._regions) do if r._tag == tag then n = n + 1 end end
    return n
end
function Corners(b)               -- the icon-corner wedge of an item button (tag set by the AddCut2Texture stand-in)
    for _, r in ipairs(b._regions) do if r._tag == "corners" then return r end end
end
function CornersAlpha(b)
    local r = Corners(b)
    return r and r:GetAlpha() or -1
end
function CornersShown(b)
    local r = Corners(b)
    return r ~= nil and Visible(r)
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
        self.g.HELDART_SRC = HELDART_LUA.read_text(encoding="utf-8")
        self.g.BUTTONSKINS_SRC = BUTTONSKINS_LUA.read_text(encoding="utf-8")
        self.rt.eval("function(src) assert(loadstring(src))() end")(MOCK)
        self.run(f"FS.Theme.COLOR_BAG_RING = {bag_ring_table()}")
        self.run("""
            local EMPTY, AXE = nil, { icon = 135, quality = { 0.1, 0.9, 0.2 } }
            MkBagControls()
            c1 = MkContainer("ContainerFrame1", 4, false, 1)
            c1._backpack = true
            c1.infos = { AXE, nil, AXE, nil }
            c1:UpdateItems()
            c2 = MkContainer("ContainerFrame2", 2, false, 2)
            comb = MkContainer("ContainerFrameCombinedBags", 3, true)
            comb.Items[1]._bagID, comb.Items[2]._bagID, comb.Items[3]._bagID = 0, 1, 1
            comb.Items[1]._slot, comb.Items[2]._slot, comb.Items[3]._slot = 1, 11, 12
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
    w.run("c1.infos[4] = { icon = 136 }; c1.Items[4]:SetItemButtonTexture(136)")      # an item arrives WITH its data: the item API outranks the art
    check("art.item_arriving_in_an_empty_slot_shows", w.ev("Visible(c1.Items[4].icon) and c1.Items[4].icon._texture == 136"))
    w.run("c1.Items[4].icon:SetAtlas('Garrison-Bag')")
    check("art.a_real_atlas_icon_is_left_alone", w.ev("Visible(c1.Items[4].icon) and c1.Items[4].icon._atlas == 'Garrison-Bag'"))
    w.run("c1.infos[4] = nil; c1.Items[4]:SetItemButtonTexture(nil)")
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


def check_icon_border() -> None:
    # A filled slot wears Blizzard's IconBorder (WhiteIconFrame, 37 x 37, tinted by quality for Common and up): a square
    # rounded frame whose corners poke past the cut corners of our ring. It is held at alpha 0 like the other slot art.
    # Only the alpha is ours: Blizzard keeps the shown state, the colour and the texture.
    w = World()
    w.run("comb:UpdateItems()")          # the combined window is painted after the load in this mock; the others before it
    filled = ["c1.Items[1]", "c1.Items[3]", "comb.Items[1]", "comb.Items[3]", "bank.pool[1]"]
    every = " and ".join(f"not Visible({b}.IconBorder)" for b in filled)
    check("border.hidden_on_every_filled_slot_after_the_skin", w.ev(every), "; ".join(tags(w, b) for b in filled))
    check("border.blizzards_shown_state_and_colour_are_untouched",
          w.ev("c1.Items[1].IconBorder:IsShown() and not c1.Items[2].IconBorder:IsShown() and bank.pool[1].IconBorder:IsShown()"))
    r, g, b = (float(v) for v in w.ev("(function() local r, g, b = c1.Items[1].IconBorder:GetVertexColor(); return {r, g, b} end)()").values())
    check("border.blizzards_colour_is_untouched", near(r, 0.1) and near(g, 0.9) and near(b, 0.2), f"{r},{g},{b}")
    check("border.blizzards_texture_is_untouched", w.ev("c1.Items[1].IconBorder:GetTexture() == 'Interface\\\\Common\\\\WhiteIconFrame'"))

    # Blizzard repaints every slot: border re-shown and re-tinted, then the button alpha written through
    w.run("c1.infos[1].quality = { 0.64, 0.21, 0.93 }; c1:UpdateItems(); comb:UpdateItems(); bank.RefreshAllItemsForSelectedTab(bank)")
    check("border.stays_hidden_after_blizzard_repaints_and_retints_it", w.ev(every), "; ".join(tags(w, b) for b in filled))
    check("border.repaint_still_owns_the_colour_and_shown_state",
          w.ev("c1.Items[1].IconBorder:IsShown() and select(1, c1.Items[1].IconBorder:GetVertexColor()) == 0.64"))
    w.run("for _, expr in ipairs({ c1.Items[1], comb.Items[1], bank.pool[1] }) do BlizzardButtonAlpha(expr, 1) end")
    check("border.stays_hidden_after_the_button_alpha_write", w.ev(every), "; ".join(tags(w, b) for b in filled))
    w.run("BlizzardButtonAlpha(c1.Items[1], 0.5)")
    check("border.the_icon_alpha_stays_blizzards", w.ev("c1.Items[1].icon:GetAlpha() == 0.5 and not Visible(c1.Items[1].IconBorder)"))

    # an item arriving in an empty slot, then a Blizzard reset of the slot art: still icon, plate and ring only
    w.run("c1.infos[2] = { icon = 136, quality = { 1, 1, 1 } }; c1:UpdateItems(); BlizzardReset(c1.Items[2])")
    check("border.item_arriving_in_an_empty_slot_shows_no_border", tags(w, "c1.Items[2]") == "corners,icon,plate,ring", tags(w, "c1.Items[2]"))
    w.run("bank.infos[2] = { icon = 137, quality = { 0, 0.44, 0.87 } }; bank.RefreshAllItemsForSelectedTab(bank)")
    check("border.item_arriving_in_an_empty_bank_slot_shows_no_border", tags(w, "bank.pool[2]") == "corners,icon,plate,ring", tags(w, "bank.pool[2]"))

    # one alpha hook per region however many passes ran (Blizzard's own shown state and colour are pinned above)
    for _ in range(3):
        w.run("c1:UpdateItems(); comb:UpdateItems(); bank.RefreshAllItemsForSelectedTab(bank)")
    check("border.alpha_hooked_once", w.ev("HookCount(c1.Items[1].IconBorder, 'SetAlpha') == 1 and HookCount(bank.pool[1].IconBorder, 'SetAlpha') == 1"),
          str(w.ev("HookCount(c1.Items[1].IconBorder, 'SetAlpha')")))
    check("border.nothing_swallowed", w.swallowed() == "", w.swallowed())
    check("border.no_degrade_logs", w.degrade() == "", w.degrade())


def check_untouched() -> None:
    w = World()
    w.run("c1:UpdateItems(); for _, b in ipairs(c1.Items) do BlizzardReset(b) end; c1:UpdateItems()")
    keep = ["IconOverlay", "IconOverlay2", "UpgradeIcon",
            "JunkIcon", "searchOverlay", "ItemContextOverlay", "PushedTexture", "HighlightTexture",
            "ExtendedSlot", "Count"]
    hooked = [field for field in keep if w.ev(f"TouchedByUs(c1.Items[1].{field})")]
    check("keep.no_hook_on_any_untouched_region", not hooked, "hooked by us: " + ", ".join(hooked))
    # the new-item glows and the quest border are square art past the cut ring: held at alpha 0
    w.run("c1.Items[1].NewItemTexture:SetAlpha(0.7)")
    check("glow.new_item_glow_is_held_at_zero", w.ev("c1.Items[1].NewItemTexture:GetAlpha() == 0"))
    check("glow.quest_border_and_flash_are_held",
          w.ev("TouchedByUs(c1.Items[1].IconQuestTexture) and TouchedByUs(c1.Items[1].flash)"))
    # the stock "!" for an item that begins a quest is on the held IconQuestTexture: our own amber mark stands in for it,
    # only on a starter not yet taken, and it goes when the quest is accepted
    w.run("""
        QUEST_INFO = { [1] = { isQuestItem = true, questID = 42, isActive = false }, [2] = { isQuestItem = true } }
        C_Container.GetContainerItemQuestInfo = function(bag, slot)
            for i, b in ipairs(c1.Items) do if b._bagID == bag and b._slot == slot then return QUEST_INFO[i] or {} end end
            return {}
        end
        function BangOf(b)
            for _, r in ipairs({ b:GetRegions() }) do
                if r._text == '!' then return r end
            end
        end
        c1.infos[1] = c1.infos[1] or { icon = 149, q = 1 }; c1.infos[2] = c1.infos[2] or { icon = 150, q = 1 }
        c1:UpdateItems()
    """)
    check("quest.starter_shows_bang", w.ev("BangOf(c1.Items[1]) ~= nil and BangOf(c1.Items[1]):IsShown()"))
    check("quest.plain_quest_item_has_no_bang", w.ev("not (BangOf(c1.Items[2]) and BangOf(c1.Items[2]):IsShown())"))
    w.run("QUEST_INFO[1].isActive = true; c1:UpdateItems()")
    check("quest.bang_goes_once_taken", w.ev("not BangOf(c1.Items[1]):IsShown()"))
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
    plate = dict(w.ev("(function() local c = nil; for _, x in ipairs(CALLS) do if x[1] == 'AddCut2Texture' and x[2] == c1.Items[1] and x[4] == 'BACKGROUND' then c = x end end; if not c then return {} end; return { path = c[3], layer = c[4], sub = c[5] } end)()").items())
    check("plate.is_the_cut2_button_texture_at_background_minus_8",
          plate == {"path": "slice_cut2_button.tga", "layer": "BACKGROUND", "sub": -8}, str(plate))
    opts = w.ev("(function() for _, x in ipairs(CALLS) do if x[1] == 'SkinCutButton' and x[2] == c1.Items[1] then return x[3].count == c1.Items[1].Count end end end)()")
    check("plate.border_is_skincutbutton_with_the_count", bool(opts))
    check("plate.no_plain_skinbutton_call_left_on_an_item_slot",
          w.ev("(function() for _, c in ipairs(CALLS) do if c[1] == 'SkinButton' and c[2]._k then return false end end return true end)()"))
    # hooks installed once per region / per button method however many passes ran
    check("plate.normal_region_alpha_hooked_once", w.ev("HookCount(c1.Items[1].NormalTexture, 'SetAlpha') == 1"),
          str(w.ev("HookCount(c1.Items[1].NormalTexture, 'SetAlpha')")))
    # the engine does not write alpha through SetAtlas / SetTexture, so the art regions carry no hook for them
    check("plate.art_regions_have_no_atlas_or_texture_hook",
          w.ev("HookCount(c1.Items[1].NormalTexture, 'SetAtlas') == 0 and HookCount(c1.Items[1].NormalTexture, 'SetTexture') == 0 "
               "and HookCount(bank.pool[1].Background, 'SetAtlas') == 0"))
    # SetAtlas carries two post-hooks, the empty-art clear and the icon-corner sync; neither is added again by a pass
    check("plate.icon_hooked_once", w.ev("HookCount(c1.Items[1].icon, 'SetAtlas') == 2"), str(w.ev("HookCount(c1.Items[1].icon, 'SetAtlas')")))
    check("plate.container_update_hooked_once", w.ev("HookCount(c1, 'UpdateItems') == 1 and HookCount(comb, 'UpdateItems') == 1"))
    check("plate.combined_background_hooked_once", w.ev("HookCount(comb.Items[1].ItemSlotBackground, 'SetAlpha') == 1"))

    # an empty slot shows only our plate and ring (no Blizzard slot art at all)
    w.run("BlizzardReset(c1.Items[2]); c1.Items[2]:SetItemButtonTexture(nil); c1:UpdateItems()")
    check("plate.empty_slot_shows_only_plate_ring_and_well", tags(w, "c1.Items[2]") == "plate,ring,well", tags(w, "c1.Items[2]"))
    w.run("bank.RefreshAllItemsForSelectedTab(bank); bank.pool[2]:UpdateBackgroundForBankType()")
    check("plate.empty_bank_slot_shows_only_plate_and_ring", tags(w, "bank.pool[2]") == "plate,ring", tags(w, "bank.pool[2]"))
    w.run("comb.Items[2]:SetItemButtonTexture(nil); comb:UpdateItems()")
    check("plate.empty_combined_slot_shows_only_plate_ring_and_well", tags(w, "comb.Items[2]") == "plate,ring,well", tags(w, "comb.Items[2]"))
    # a filled slot: the icon (the item) on top of the plate, our ring, and no Blizzard border at all
    check("plate.filled_slot_has_only_icon_corners_plate_and_ring", tags(w, "c1.Items[1]") == "corners,icon,plate,ring", tags(w, "c1.Items[1]"))
    check("plate.nothing_swallowed", w.swallowed() == "", w.swallowed())
    check("plate.no_degrade_logs", w.degrade() == "", w.degrade())


def check_icon_corners() -> None:
    # MaskTexture does not clip on this client (Theme.lua, verified in game), so the cut that a mask would make is a baked
    # wedge: the cut2 erase nine-slice (opaque in the TOP-LEFT and BOTTOM-RIGHT corner slices only) tinted the panel colour,
    # over the same rect as the ring. It hides the filled slot's square icon corner outside the cut and nothing else.
    w = World()
    w.run("comb:UpdateItems()")          # the combined window is painted after the load in this mock; the others before it
    filled = ["c1.Items[1]", "c1.Items[3]", "comb.Items[1]", "comb.Items[3]", "bank.pool[1]"]
    empty = ["c1.Items[2]", "c1.Items[4]", "comb.Items[2]", "bank.pool[2]", "bank.pool[3]"]

    def shown(expr: str) -> bool:
        return bool(w.ev(f"CornersShown({expr})"))

    check("corners.shown_on_every_filled_slot", all(shown(b) for b in filled), "; ".join(f"{b}={shown(b)}" for b in filled))
    check("corners.hidden_on_every_empty_slot", not any(shown(b) for b in empty), "; ".join(f"{b}={shown(b)}" for b in empty))

    # the look: the erase file over the button rect, the panel colour opaque, above the icon and under the ring and glow
    look = dict(w.ev("(function() local r = Corners(c1.Items[1]); if not r then return { path = 'none', layer = 'none', sub = 0, ringSub = 0 } end; "
                     "local cr, cg, cb, ca = r:GetVertexColor(); local call; "
                     "for _, x in ipairs(CALLS) do if x[1] == 'AddCut2Texture' and x[2] == c1.Items[1] and x[3] == 'slice_cut2_erase_c6.tga' then call = x end end; "
                     "return { path = r._texture, layer = r._layer, sub = r._sub, slice = r._slice, r = cr, g = cg, b = cb, a = ca, "
                     "ringSub = (function() for _, q in ipairs(c1.Items[1]._regions) do if q._tag == 'ring' then return q._sub end end end)(), "
                     "viaHelper = call ~= nil } end)()").items())
    check("corners.is_the_cut2_erase_nine_slice_via_the_theme_helper", look["path"] == "slice_cut2_erase_c6.tga" and look.get("viaHelper", False), str(look))
    check("corners.is_the_panel_colour_and_opaque", all(k in look for k in "rgba") and near(look["r"], 0.102) and near(look["g"], 0.063)
          and near(look["b"], 0.145) and near(look["a"], 1), str(look))
    check("corners.draw_above_the_icon_and_under_the_ring", look["layer"] == "OVERLAY" and look["sub"] == -1 and look["sub"] < look["ringSub"], str(look))

    # made once per button however many passes ran, on every kind of slot, with one hook per icon method
    for _ in range(3):
        w.run("c1:UpdateItems(); comb:UpdateItems(); c1:GenerateSlots(); bank.RefreshAllItemsForSelectedTab(bank)")
    for expr in ("c1.Items[1]", "c1.Items[2]", "comb.Items[1]", "bank.pool[1]", "bank.pool[2]"):
        check(f"corners.{expr}_one_region", w.ev(f"RegionCount({expr}, 'corners') == 1"), str(w.ev(f"RegionCount({expr}, 'corners')")))
    hooks = {m: int(w.ev(f"HookCount(c1.Items[1].icon, '{m}')")) for m in ("SetTexture", "SetShown", "Show", "Hide")}
    check("corners.icon_hooked_once_per_method", all(n == 1 for n in hooks.values()), str(hooks))
    check("corners.pass_leaves_the_state_alone", all(shown(b) for b in filled) and not any(shown(b) for b in empty))

    # the wedge follows the ICON, with no UpdateItems pass in between
    w.run("c1.infos[2] = { icon = 136 }; c1.Items[2]:SetItemButtonTexture(136)")      # the item API outranks the art: data arrives with the icon
    check("corners.an_item_arriving_shows_them", shown("c1.Items[2]"))
    w.run("c1.infos[2] = nil; c1.Items[2]:SetItemButtonTexture(nil)")
    check("corners.the_slot_emptying_hides_them", not shown("c1.Items[2]"))
    w.run("c1.infos[4] = { icon = 144 }; c1.Items[4].icon:SetAtlas('Garrison-Bag')")
    check("corners.a_real_atlas_icon_counts_as_art", shown("c1.Items[4]"))
    w.run("c1.infos[4] = nil; c1.Items[4]:SetItemButtonTexture(nil)")
    check("corners.the_empty_slot_atlas_does_not", not shown("c1.Items[4]"))
    # the bank empties a slot by hiding the icon and leaves its old texture on it
    w.run("bank.pool[2].icon:SetTexture(137); bank.pool[2].icon:SetShown(true)")
    check("corners.a_bank_icon_shown_with_a_texture_shows_them", shown("bank.pool[2]"))
    w.run("bank.pool[2].icon:SetShown(false)")
    check("corners.a_hidden_bank_icon_hides_them_though_it_keeps_its_texture", not shown("bank.pool[2]") and w.ev("bank.pool[2].icon._texture == 137"))
    w.run("bank.pool[2].icon:Show()")
    check("corners.icon_show_shows_them", shown("bank.pool[2]"))
    w.run("bank.pool[2].icon:Hide()")
    check("corners.icon_hide_hides_them", not shown("bank.pool[2]"))
    w.run("bank.pool[2].icon:SetTexture(nil); bank.pool[2].icon:Show()")
    check("corners.a_shown_icon_with_no_texture_shows_none", not shown("bank.pool[2]"))

    # a repaint that empties, then refills, a filled slot
    w.run("c1.infos[1] = nil; c1:UpdateItems()")
    check("corners.a_pass_that_empties_a_filled_slot_hides_them", not shown("c1.Items[1]"))
    w.run("c1.infos[1] = { icon = 138 }; c1:UpdateItems()")
    check("corners.a_pass_that_fills_it_again_shows_them", shown("c1.Items[1]"))

    # Blizzard's alpha writes and the slot art holds never move them; the icon, its alpha and the other regions stay Blizzard's
    w.run("BlizzardButtonAlpha(c1.Items[1], 0.5); BlizzardReset(c1.Items[1])")
    check("corners.keep_the_icon_alpha_and_the_other_art_untouched",
          w.ev("c1.Items[1].icon:GetAlpha() == 0.5 and CornersAlpha(c1.Items[1]) == 1 and not Visible(c1.Items[1].NormalTexture)")
          and shown("c1.Items[1]"))

    # a secret icon texture is never compared or tested: it counts as an item
    w.run("c1.infos[2] = { icon = 145 }; c1.Items[2].icon:SetTexture(SECRET_VALUE); c1.Items[2].icon:SetShown(true)")
    check("corners.a_secret_texture_counts_as_an_item", shown("c1.Items[2]") and w.swallowed() == "", w.swallowed())
    w.run("c1.infos[2] = nil; c1.Items[2]:SetItemButtonTexture(nil)")

    # combat: the item buttons are protected, only our region changes
    w.run("INCOMBAT = true; PROTECTED_CALLS = {}")
    w.run("c1.infos[2] = { icon = 139 }; c1.infos[1] = nil; c1:UpdateItems(); bank.pool[1].icon:SetShown(false); comb:UpdateItems()")
    prot = str(w.ev("table.concat(PROTECTED_CALLS, ',')"))
    check("corners.combat_repaint_moves_them_with_no_protected_call",
          shown("c1.Items[2]") and not shown("c1.Items[1]") and not shown("bank.pool[1]") and prot == "", prot)
    w.run("EndCombat()")
    check("corners.nothing_swallowed", w.swallowed() == "", w.swallowed())
    check("corners.no_degrade_logs", w.degrade() == "", w.degrade())

    # a missing Theme piece: the slot keeps its icon, plate and ring, and one log says why
    for label, pre in (("erase_texture", "FS.Theme.SLICE_CUT2_ERASE_TEXTURE = nil"), ("panel_colour", "FS.Theme.COLOR_BG = nil"),
                       ("cut2_helper", "FS.Theme.AddCut2Texture = nil"),
                       ("helper_throwing", "FS.Theme.AddCut2Texture = function(f, path) if path:find('erase', 1, true) then error('boom') end "
                                           "return FS.Theme.__plate(f, path) end")):
        pre_code = pre
        if label == "helper_throwing":
            pre_code = "FS.Theme.__plate = FS.Theme.AddCut2Texture; " + pre
        w2 = World(pre=pre_code)
        w2.run("c1:UpdateItems(); c1:UpdateItems()")
        check(f"corners.missing_{label}_makes_none_and_logs_once",
              w2.ev("RegionCount(c1.Items[1], 'corners') == 0") and w2.degrade().count("bags_icon_corners") == 1, w2.degrade())
        check(f"corners.missing_{label}_keeps_the_slot_skinned",
              w2.ev("Count('SkinCutButton', c1.Items[1]) == 1 and Visible(c1.Items[1].icon)") and not w2.ev("Visible(c1.Items[1].IconBorder)"))
        if label != "helper_throwing":
            check(f"corners.missing_{label}_swallows_nothing", w2.swallowed() == "", w2.swallowed())

    # an icon with no state methods at all (a bare button) is harmless
    w3 = World()
    w3.run("bare = CreateFrame('Button', nil, UIParent); bare.icon = { GetObjectType = function() return 'Texture' end }; "
           "c1.Items = { bare }; c1:UpdateItems()")
    check("corners.an_icon_without_state_methods_is_harmless", w3.swallowed() == "" and w3.ev("not CornersShown(bare)"), w3.swallowed())


BAG_RING_HEX = "#5b2d9e"             # the approved dark violet of an empty or Common slot (option E1), so Epic's bright purple stands clear


def hex_rgb(h: str) -> tuple[float, float, float]:
    return tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))      # type: ignore[return-value]


def check_quality_ring() -> None:
    # A filled slot's ring is tinted by item quality; read from C_Container (a bank slot: the itemInfo Blizzard just read),
    # Poor grey, Common the default dark violet ring, the rest Blizzard's bag colour, Epic included.
    w = World()
    w.run("comb:UpdateItems()")
    default = hex_rgb(BAG_RING_HEX)

    def ring(expr: str) -> tuple[float, float, float, float]:
        r, g, b, a = (float(v) for v in w.ev(f"RingColor({expr})").values())
        return r, g, b, a

    def is_color(expr: str, rgb: tuple[float, float, float], eps: float = 1e-3) -> bool:
        r, g, b, a = ring(expr)
        return near(r, rgb[0], eps) and near(g, rgb[1], eps) and near(b, rgb[2], eps) and near(a, 1)

    def paint(q: int | None, slot: str = "c1.Items[1]", container: str = "c1", index: int = 1) -> None:
        info = "nil" if q is None else f"{{ icon = 140, q = {q} }}"
        w.run(f"{container}.infos[{index}] = {info}; {container}:UpdateItems()")

    check("ring.empty_slot_keeps_the_default_ring", is_color("c1.Items[2]", default), str(ring("c1.Items[2]")))

    # the colour of every quality, from the colour sources Blizzard's bags use
    bag = {2: (0.12, 1.0, 0.0), 3: (0.0, 0.44, 0.87), 5: (1.0, 0.5, 0.0), 6: (0.9, 0.8, 0.5), 7: (0.0, 0.8, 1.0)}
    paint(0)
    check("ring.poor_is_grey_from_the_item_quality_colours", is_color("c1.Items[1]", (0.62, 0.62, 0.62)), str(ring("c1.Items[1]")))
    paint(1)
    check("ring.common_keeps_the_default_ring", is_color("c1.Items[1]", default), str(ring("c1.Items[1]")))
    for q, rgb in bag.items():
        paint(q)
        check(f"ring.quality_{q}_is_the_bag_colour", is_color("c1.Items[1]", rgb), str(ring("c1.Items[1]")))
    paint(4)
    epic = (0.64, 0.21, 0.93)
    check("ring.epic_is_the_bag_colour", is_color("c1.Items[1]", epic), f"{ring('c1.Items[1]')} want {epic}")
    check("ring.epic_stands_clear_of_the_default_ring", not is_color("c1.Items[1]", default, 0.15))
    paint(None)
    check("ring.the_slot_emptying_resets_the_ring", is_color("c1.Items[1]", default), str(ring("c1.Items[1]")))
    w4 = World()
    w4.run("FS.Theme.COLOR_BAG_RING = nil; c1:UpdateItems()")
    check("ring.without_the_theme_colour_the_default_ring_is_the_border",
          is_color_for(w4, "c1.Items[2]", (0.659, 0.333, 0.969)) and w4.swallowed() == "")

    # an unknown quality (a token, a number outside the table) keeps the default ring
    paint(9)
    check("ring.a_quality_with_no_colour_keeps_the_default_ring", is_color("c1.Items[1]", default))
    paint(-1)
    check("ring.a_negative_quality_keeps_the_default_ring", is_color("c1.Items[1]", default))

    # combined bags and the bank follow too; a bank slot is read from its itemInfo, not through C_Container
    w.run("comb.infos[3] = { icon = 141, q = 3 }; comb:UpdateItems()")
    check("ring.a_combined_bags_slot_is_tinted", is_color("comb.Items[3]", bag[3]), str(ring("comb.Items[3]")))
    w.run("bank.infos[1] = { icon = 142, q = 5 }; INFO_QUERIES = 0; bank.RefreshAllItemsForSelectedTab(bank)")
    check("ring.a_bank_slot_is_tinted_from_its_item_info", is_color("bank.pool[1]", bag[5]) and w.ev("INFO_QUERIES == 0"),
          f"{ring('bank.pool[1]')} queries={w.ev('INFO_QUERIES')}")
    w.run("bank.infos[1] = nil; bank.RefreshAllItemsForSelectedTab(bank)")
    check("ring.an_emptied_bank_slot_resets", is_color("bank.pool[1]", default))

    # re-applied on every update: a different item in the same slot, a repeat pass, a window re-show
    paint(2)
    paint(3)
    check("ring.a_new_item_in_the_slot_retints", is_color("c1.Items[1]", bag[3]))
    w.run("for _ = 1, 3 do c1:UpdateItems() end")
    check("ring.repeat_passes_keep_it", is_color("c1.Items[1]", bag[3]))
    w.run("CloseWindow(c1); OpenWindow(c1)")
    check("ring.a_reopened_window_keeps_it", is_color("c1.Items[1]", bag[3]))

    # a player's colour override is honoured on the next pass; the Epic constant is ours either way
    w.run("BAG_COLORS[3] = { r = 0.9, g = 0.1, b = 0.9 }; c1:UpdateItems()")
    check("ring.a_players_colour_override_is_followed", is_color("c1.Items[1]", (0.9, 0.1, 0.9)))
    w.run("BAG_COLORS[3] = { r = 0.00, g = 0.44, b = 0.87 }")

    # the icon emptying with no pass in between: the ring resets at once, and a stale colour never lands on a new item
    paint(3)
    w.run("c1.Items[1]:SetItemButtonTexture(nil)")
    check("ring.the_icon_emptying_resets_without_a_pass", is_color("c1.Items[1]", default))
    w.run("c1.Items[1]:SetItemButtonTexture(143)")
    check("ring.an_item_arriving_waits_for_the_pass", is_color("c1.Items[1]", default))
    w.run("c1:UpdateItems()")
    check("ring.the_pass_then_tints_it", is_color("c1.Items[1]", bag[3]))
    w.run("c1.infos[1] = nil; c1:UpdateItems()")

    # secret answers: a secret quality or info keeps the default ring and nothing throws
    w.run("SECRET_IDS = false; c1.infos[1] = { icon = 144, q = SECRET_VALUE }; c1:UpdateItems()")
    check("ring.a_secret_quality_keeps_the_default_ring", is_color("c1.Items[1]", default) and w.swallowed() == "", w.swallowed())
    w.run("c1.infos[1] = nil; c1.Items[1].itemInfo = SECRET_VALUE; c1:UpdateItems(); c1.Items[1].itemInfo = nil")
    check("ring.a_secret_item_info_keeps_the_default_ring", is_color("c1.Items[1]", default) and w.swallowed() == "", w.swallowed())

    # combat: only our ring changes, nothing protected on the item button
    w.run("INCOMBAT = true; PROTECTED_CALLS = {}; c1.infos[1] = { icon = 145, q = 5 }; c1:UpdateItems(); bank.infos[2] = { icon = 146, q = 2 }; "
          "bank.RefreshAllItemsForSelectedTab(bank)")
    prot = str(w.ev("table.concat(PROTECTED_CALLS, ',')"))
    check("ring.combat_updates_the_ring_with_no_protected_call",
          is_color("c1.Items[1]", bag[5]) and is_color("bank.pool[2]", bag[2]) and prot == "", f"{prot} {ring('c1.Items[1]')}")
    w.run("EndCombat()")
    check("ring.nothing_swallowed", w.swallowed() == "", w.swallowed())
    check("ring.no_degrade_logs", w.degrade() == "", w.degrade())

    # the colour sources: the bag colours first, ITEM_QUALITY_COLORS when ColorManager is missing, and no source at all
    w = World()
    w.run("ColorManager = nil; c1.infos[1] = { icon = 147, q = 2 }; c1.infos[3] = { icon = 148, q = 0 }; c1:UpdateItems()")
    check("ring.without_colormanager_the_item_quality_colours_are_used",
          is_color("c1.Items[1]", (0.1, 0.9, 0.1)) and is_color("c1.Items[3]", (0.62, 0.62, 0.62)), f"{ring('c1.Items[1]')} {ring('c1.Items[3]')}")
    check("ring.without_colormanager_nothing_logged_or_swallowed", w.degrade() == "" and w.swallowed() == "", f"{w.degrade()} {w.swallowed()}")
    w.run("ColorManager = { GetColorDataForBagItemQuality = function() error('boom') end }; c1:UpdateItems()")
    check("ring.a_throwing_colormanager_falls_back", is_color("c1.Items[1]", (0.1, 0.9, 0.1)))
    w.run("ColorManager = { GetColorDataForBagItemQuality = function() return {} end }; ITEM_QUALITY_COLORS = nil; c1:UpdateItems()")
    check("ring.a_colour_without_channels_keeps_the_default_ring", is_color("c1.Items[1]", default) and w.degrade() == "", w.degrade())
    w2 = World()
    w2.run("ColorManager = nil; ITEM_QUALITY_COLORS = nil; c1.infos[1] = { icon = 147, q = 2 }; c1.infos[3] = { icon = 148, q = 4 }; c1:UpdateItems(); c1:UpdateItems()")
    r1 = tuple(float(v) for v in w2.ev("RingColor(c1.Items[1])").values())
    r3 = tuple(float(v) for v in w2.ev("RingColor(c1.Items[3])").values())
    check("ring.no_colour_source_keeps_the_default_ring_and_logs_once",
          near(r1[0], default[0]) and near(r1[1], default[1]) and w2.degrade().count("bags_quality_ring") == 1, w2.degrade())
    check("ring.epic_with_no_colour_source_keeps_the_default_ring",
          near(r3[0], default[0], 1e-3) and near(r3[2], default[2], 1e-3), str(r3))

    # no C_Container, no GetID, no skin ring: the slot is left alone and nothing throws
    w3 = World()
    w3.run("C_Container = nil; c1.infos[1] = { icon = 149, q = 5 }; c1:UpdateItems()")
    check("ring.no_c_container_keeps_the_default_ring", is_color_for(w3, "c1.Items[1]", default) and w3.swallowed() == "", w3.swallowed())
    w3 = World()
    w3.run("c1.Items[1].GetID = nil; c1.infos[1] = { icon = 150, q = 5 }; c1:UpdateItems(); c1.Items[1].GetBagID = nil; c1:UpdateItems()")
    check("ring.a_button_without_ids_keeps_the_default_ring", is_color_for(w3, "c1.Items[1]", default) and w3.swallowed() == "", w3.swallowed())
    w3 = World()
    w3.run("c1.Items[1].fsSkin.border = nil; c1.infos[1] = { icon = 151, q = 5 }; c1:UpdateItems()")
    check("ring.a_skin_without_a_ring_is_harmless", w3.swallowed() == "", w3.swallowed())


def is_color_for(w: World, expr: str, rgb: tuple[float, float, float]) -> bool:
    r, g, b, a = (float(v) for v in w.ev(f"RingColor({expr})").values())
    return near(r, rgb[0], 1e-3) and near(g, rgb[1], 1e-3) and near(b, rgb[2], 1e-3) and near(a, 1)


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


# Blizzard's GamepadBagBar: a Frame under the combined bags, shown by default. Show() fires OnShow when it was hidden.
BAR = """
    comb.GamepadBagBar = CreateFrame("Frame", "GamepadBagBar", comb)
    local bar = GamepadBagBar
    bar.Show = function(self) if not self._shown then self._shown = true; for _, fn in ipairs(self._scripts.OnShow or {}) do fn(self) end end end
"""
NO_PAD = "C_GamePad = { IsEnabled = function() return true end, GetAllDeviceIDs = function() return {} end }"
PAD = "C_GamePad = { IsEnabled = function() return true end, GetAllDeviceIDs = function() return { 5 } end }"


def check_gamepad_bar() -> None:
    # no controller: hidden at skin time, and hidden again every way Blizzard can show it
    w = World(pre=BAR + NO_PAD)
    check("gamepad.no_device_hides_the_bar", w.ev("not GamepadBagBar:IsShown()"))
    w.run("GamepadBagBar:Show()")
    check("gamepad.no_device_rehides_after_Show", w.ev("not GamepadBagBar:IsShown()"))
    w.run("GamepadBagBar:SetShown(true)")
    check("gamepad.no_device_rehides_after_SetShown", w.ev("not GamepadBagBar:IsShown()"))
    w.run("GamepadBagBar._shown = true; for _, fn in ipairs(GamepadBagBar._scripts.OnShow or {}) do fn(GamepadBagBar) end")
    check("gamepad.no_device_rehides_in_OnShow", w.ev("not GamepadBagBar:IsShown()"))
    check("gamepad.no_device_nothing_swallowed", w.swallowed() == "", w.swallowed())

    # the same when the API says gamepads are off, or the namespace is missing altogether
    w = World(pre=BAR + "C_GamePad = { IsEnabled = function() return false end, GetAllDeviceIDs = function() return { 5 } end }")
    check("gamepad.disabled_hides_the_bar", w.ev("not GamepadBagBar:IsShown()"))
    w = World(pre=BAR + "C_GamePad = nil")
    check("gamepad.no_api_hides_the_bar", w.ev("not GamepadBagBar:IsShown()") and w.swallowed() == "", w.swallowed())

    # a controller: Blizzard stays in charge, even of a bar it hid itself
    w = World(pre=BAR + PAD)
    check("gamepad.device_leaves_the_bar_shown", w.ev("GamepadBagBar:IsShown()"))
    w.run("GamepadBagBar:Hide(); GamepadBagBar:Show()")
    check("gamepad.device_lets_blizzard_show_it", w.ev("GamepadBagBar:IsShown()"))
    w.run("GamepadBagBar:Hide(); FireEvent('GAME_PAD_ACTIVE_CHANGED')")
    check("gamepad.device_never_shows_a_bar_we_did_not_hide", w.ev("not GamepadBagBar:IsShown()"))

    # connect / disconnect on the events: connecting never forces the bar on, Blizzard shows it on its next update
    w = World(pre=BAR + NO_PAD)
    w.run("C_GamePad.GetAllDeviceIDs = function() return { 5 } end; FireEvent('GAME_PAD_CONNECTED')")
    check("gamepad.connect_does_not_force_show", w.ev("not GamepadBagBar:IsShown()"))
    w.run("GamepadBagBar:Show()")
    check("gamepad.connect_then_blizzard_show_sticks", w.ev("GamepadBagBar:IsShown()"))
    w.run("C_GamePad.GetAllDeviceIDs = function() return {} end; FireEvent('GAME_PAD_DISCONNECTED')")
    check("gamepad.disconnect_hides_it_again", w.ev("not GamepadBagBar:IsShown()"))
    w.run("C_GamePad.GetAllDeviceIDs = function() return { 5 } end; FireEvent('GAME_PAD_ACTIVE_CHANGED')")
    check("gamepad.active_changed_reevaluates", w.ev("not GamepadBagBar:IsShown()"))
    w.run("GamepadBagBar:Show()")
    check("gamepad.active_changed_then_show_sticks", w.ev("GamepadBagBar:IsShown()"))
    check("gamepad.events_nothing_swallowed", w.swallowed() == "", w.swallowed())

    # Blizzard hid the bar after we did, then a controller connects: we do not show it back
    w = World(pre=BAR + NO_PAD)
    w.run("GamepadBagBar:Hide(); C_GamePad.GetAllDeviceIDs = function() return { 5 } end; FireEvent('GAME_PAD_CONNECTED')")
    check("gamepad.connect_leaves_a_blizzard_hidden_bar_hidden", w.ev("not GamepadBagBar:IsShown()"))

    # connecting while the bags frame is hidden leaves the bar not visible
    w = World(pre=BAR + NO_PAD)
    w.run("comb:Hide(); C_GamePad.GetAllDeviceIDs = function() return { 5 } end; FireEvent('GAME_PAD_CONNECTED')")
    check("gamepad.connect_with_bags_hidden_shows_nothing", w.ev("not comb:IsShown() and not GamepadBagBar:IsShown()"))

    # an API that errors counts as a controller, whichever call fails
    w = World(pre=BAR + "C_GamePad = { IsEnabled = function() error('boom') end, GetAllDeviceIDs = function() return {} end }")
    check("gamepad.is_enabled_error_leaves_blizzard_in_charge", w.ev("GamepadBagBar:IsShown()"))
    w = World(pre=BAR + "C_GamePad = { IsEnabled = function() return true end, GetAllDeviceIDs = function() error('boom') end }")
    check("gamepad.device_ids_error_leaves_blizzard_in_charge", w.ev("GamepadBagBar:IsShown()"))

    # a bar that does not exist yet at load time is caught on PLAYER_ENTERING_WORLD
    w = World(pre=NO_PAD)
    check("gamepad.absent_bar_does_not_throw", w.swallowed() == "", w.swallowed())
    w.run(BAR + "FireEvent('PLAYER_ENTERING_WORLD')")
    check("gamepad.late_bar_hidden_on_entering_world", w.ev("not GamepadBagBar:IsShown()"))
    w.run("GamepadBagBar:Show()")
    check("gamepad.late_bar_rehidden_after_Show", w.ev("not GamepadBagBar:IsShown()"))

    # an event this client does not know is skipped, the rest still work
    w = World(pre=BAR + NO_PAD + "; KNOWN_EVENTS.GAME_PAD_ACTIVE_CHANGED = nil")
    check("gamepad.unknown_event_still_hides", w.ev("not GamepadBagBar:IsShown()"))
    w.run("C_GamePad.GetAllDeviceIDs = function() return { 5 } end; FireEvent('GAME_PAD_CONNECTED')")
    w.run("GamepadBagBar:Show()")
    check("gamepad.unknown_event_others_still_work", w.ev("GamepadBagBar:IsShown()"))

    # combat: the bar is unprotected, so a Blizzard Show and a disconnect event are handled at once
    w = World(pre=BAR + PAD)
    w.run("INCOMBAT = true; C_GamePad.GetAllDeviceIDs = function() return {} end; FireEvent('GAME_PAD_DISCONNECTED')")
    check("gamepad.combat_event_hides_immediately", w.ev("not GamepadBagBar:IsShown()"))
    w.run("GamepadBagBar:Show()")
    check("gamepad.combat_rehides_after_Show", w.ev("not GamepadBagBar:IsShown()") and w.swallowed() == "", w.swallowed())

    # nothing but the bar is touched: the sort button, its art and the CVar stay as Blizzard left them
    w = World(pre=BAR + NO_PAD + "; comb.sort = CreateFrame('Button', 'BagItemAutoSortButton', comb); CVARS.GamePadEnable = '1'")
    check("gamepad.sort_button_and_cvar_untouched", w.ev("BagItemAutoSortButton:IsShown() and CVARS.GamePadEnable == '1' and #BagItemAutoSortButton._pts == 0"))


def lit(w: World, expr: str) -> str:
    return str(w.ev(f"LitSet({expr})"))


def check_bag_highlight() -> None:
    w = World()
    w.run("c1:UpdateItems(); c2:UpdateItems(); comb:UpdateItems()")

    # individual windows: hovering bag 2 lights bag 2's slots and nothing else
    w.run("FS.BagHighlight.Set(2)")
    check("hover.bag2_lights_only_bag2_slots", lit(w, "c2") == "1,2" and lit(w, "c1") == "" and lit(w, "comb") == "",
          f"c1={lit(w, 'c1')} c2={lit(w, 'c2')} comb={lit(w, 'comb')}")
    w.run("FS.BagHighlight.Clear()")
    check("hover.leave_clears_every_slot", lit(w, "c1") == "" and lit(w, "c2") == "" and lit(w, "comb") == "")
    w.run("FS.BagHighlight.Set(1)")
    check("hover.bag1_lights_bag1_slots", lit(w, "c1") == "1,2,3,4" and lit(w, "c2") == "", f"{lit(w, 'c1')} {lit(w, 'c2')}")

    # the combined window mixes bags: backpack is bag 0
    w.run("FS.BagHighlight.Clear(); FS.BagHighlight.Set(0)")
    check("hover.backpack_lights_bag0_slots_in_the_combined_window", lit(w, "comb") == "1" and lit(w, "c1") == "", lit(w, "comb"))
    w.run("FS.BagHighlight.Set(1)")
    check("hover.moving_to_another_bag_swaps_the_lit_slots", lit(w, "comb") == "2,3" and lit(w, "c1") == "1,2,3,4", lit(w, "comb"))
    w.run("FS.BagHighlight.Set(5)")
    check("hover.reagent_bag_5_lights_only_its_own_slots", lit(w, "comb") == "" and lit(w, "c1") == "" and lit(w, "c2") == "")
    w.run("FS.BagHighlight.Set(2); FS.BagHighlight.Set(nil)")
    check("hover.a_non_number_clears", lit(w, "c2") == "")

    # the look: the slot's own cut2 set, the hover colour, nothing else restyled
    w.run("FS.BagHighlight.Set(2)")
    hl = w.ev("(function() local h = c2.Items[1].fsBagHighlight; local r, g, b, a = h.glow:GetVertexColor(); local rr, rg, rb = h.ring:GetVertexColor(); "
              "return { ring = h.ring._texture, glow = h.glow._texture, blend = h.glow._blend, ringLayer = h.ring._layer, ringSub = h.ring._sub, "
              "glowLayer = h.glow._layer, glowSub = h.glow._sub, slice = h.glow._slice, r = r, g = g, b = b, a = a, rr = rr, rg = rg, rb = rb, "
              "pts = #h.glow._pts } end)()")
    hl = {k: v for k, v in hl.items()}
    check("hover.ring_is_the_cut2_outline_and_glow_the_cut2_glow", hl["ring"] == "slice_cut2_outline.tga" and hl["glow"] == "slice_cut2_glow.tga", str(hl))
    check("hover.glow_is_additive_and_pad_anchored", hl["blend"] == "ADD" and hl["pts"] == 2 and hl["slice"] == 10, str(hl))
    check("hover.drawn_above_the_icon_on_overlay", hl["ringLayer"] == "OVERLAY" and hl["glowLayer"] == "OVERLAY" and hl["ringSub"] == 3 and hl["glowSub"] == 2, str(hl))
    check("hover.colour_is_the_theme_hover_colour", near(hl["r"], 1) and near(hl["g"], 0.18) and near(hl["b"], 0.592) and near(hl["a"], 0.9)
          and near(hl["rr"], 1) and near(hl["rg"], 0.18) and near(hl["rb"], 0.592), str(hl))
    check("hover.other_slots_are_not_restyled", w.ev("not AnyLit(c1.Items[1]) and RegionCount(c1.Items[1], 'plate') == 1 and RegionCount(c1.Items[1], 'ring') == 1"))
    check("hover.slot_plate_and_art_untouched_on_the_lit_slot",
          w.ev("RegionCount(c2.Items[1], 'ring') == 1 and not Visible(c2.Items[1].NormalTexture) and c2.Items[1].icon:GetAlpha() == 1 and c2.Items[1]:GetAlpha() == 1"))
    for _ in range(3):
        w.run("c2:UpdateItems(); FS.BagHighlight.Set(2)")
    check("hover.regions_are_made_once_per_button", w.ev("(function() local n = 0; for _, r in ipairs(c2.Items[1]._regions) do if r._texture == 'slice_cut2_glow.tga' then n = n + 1 end end return n end)()") == 1)
    w.run("FS.BagHighlight.Clear()")

    # closed window: nothing lit, no error; closing while hovering clears; reopening while still hovering lights again
    w.run("CloseWindow(c1); FS.BagHighlight.Set(1)")
    check("hover.closed_window_shows_nothing", lit(w, "c1") == "", lit(w, "c1"))
    w.run("OpenWindow(c1)")
    check("hover.opening_the_window_while_hovering_lights_it", lit(w, "c1") == "1,2,3,4", lit(w, "c1"))
    w.run("CloseWindow(c1)")
    check("hover.closing_the_window_while_hovering_clears_it", lit(w, "c1") == "", lit(w, "c1"))
    w.run("OpenWindow(c1); FS.BagHighlight.Clear(); CloseWindow(c1); OpenWindow(c1)")
    check("hover.leave_then_reopen_stays_dark", lit(w, "c1") == "", lit(w, "c1"))
    w.run("CloseWindow(c1); CloseWindow(c2); CloseWindow(comb); FS.BagHighlight.Set(2); FS.BagHighlight.Clear()")
    check("hover.every_window_closed_is_no_error", w.swallowed() == "", w.swallowed())
    w.run("OpenWindow(c1); OpenWindow(c2); OpenWindow(comb)")

    w.run("FS.BagHighlight.Set(1); CloseWindow(c1); OpenWindowRefreshFirst(c1)")
    check("hover.refresh_while_hidden_then_show_still_lights_via_OnShow", lit(w, "c1") == "1,2,3,4", lit(w, "c1"))
    w.run("FS.BagHighlight.Clear(); OpenWindow(c1)")

    # a pooled button re-used for another bag follows its new bag on the next UpdateItems
    w.run("FS.BagHighlight.Set(2)")
    w.run("c2.Items[1]._bagID = 1; c2:UpdateItems()")
    check("hover.a_reused_button_stops_lighting_for_the_old_bag", lit(w, "c2") == "2", lit(w, "c2"))
    w.run("c1.Items[2]._bagID = 2; c1:UpdateItems()")
    check("hover.a_reused_button_lights_for_the_new_bag", lit(w, "c1") == "2", lit(w, "c1"))
    w.run("c2.Items[1]._bagID = 2; c1.Items[2]._bagID = 1; FS.BagHighlight.Clear()")

    # the bank is not a bag-bar bag
    w.run("FS.BagHighlight.Set(0); FS.BagHighlight.Set(1)")
    check("hover.bank_slots_never_light", w.ev("bank.pool[1].fsBagHighlight == nil and bank.pool[2].fsBagHighlight == nil"))
    w.run("FS.BagHighlight.Clear()")
    check("hover.nothing_swallowed", w.swallowed() == "", w.swallowed())
    check("hover.no_degrade_logs", w.degrade() == "", w.degrade())

    # combat: item buttons are protected; only our regions change
    w = World()
    w.run("c2:UpdateItems(); comb:UpdateItems(); INCOMBAT = true; PROTECTED_CALLS = {}")
    w.run("FS.BagHighlight.Set(2); comb:UpdateItems(); FS.BagHighlight.Set(1); FS.BagHighlight.Clear(); FS.BagHighlight.Set(2); CloseWindow(c2); OpenWindow(c2)")
    check("combat.hover_lights_in_combat", lit(w, "c2") == "1,2", lit(w, "c2"))
    prot = str(w.ev("table.concat(PROTECTED_CALLS, ',')"))
    check("combat.highlight_calls_no_protected_method_on_an_item_button", prot == "", prot)
    check("combat.nothing_swallowed", w.swallowed() == "", w.swallowed())

    # one container that throws does not stop the others, and is logged once however often it is hovered
    w = World()
    w.run("c1:UpdateItems(); c2:UpdateItems(); c1.EnumerateValidItems = function() error('boom') end; __clearSwallowed()")
    for _ in range(3):
        w.run("FS.BagHighlight.Set(2)")
    check("hover.a_throwing_container_does_not_skip_the_others", lit(w, "c2") == "1,2", lit(w, "c2"))
    check("hover.a_throwing_container_is_logged_once", w.degrade() == "bags_hover_sync", w.degrade())

    # a throw while building the regions leaves nothing visible behind
    for broken in ("SetBlendMode", "SetVertexColor", "SetTexture"):
        w = World()
        w.run(f"c2:UpdateItems(); __clearSwallowed(); local mk = c2.Items[1].CreateTexture; "
              f"c2.Items[1].CreateTexture = function(self, ...) local t = mk(self, ...); t.{broken} = function() error('boom') end; return t end; "
              "FS.BagHighlight.Set(2)")
        check(f"hover.{broken.lower()}_throwing_leaves_no_visible_orphan",
              w.ev("(function() for _, r in ipairs(c2.Items[1]._regions) do if r._tag == 'created' and r._shown then return false end end return true end)()")
              and w.ev("c2.Items[1].fsBagHighlight == nil") and w.degrade() == "bags_hover_highlight", f"{w.degrade()}")

    # a bag button hovered before its slots were ever skinned (a button the first pass never saw) is skinned and lit
    w = World()
    w.run("c1.Items[1].fsBagItemSkinned = nil; c1.Items[1].fsBagHighlight = nil; FS.BagHighlight.Set(1)")
    check("hover.a_fresh_button_gets_its_regions_on_the_first_hover", w.ev("Lit(c1.Items[1])"))

    # defensive paths: GetBagID missing, erroring or secret; Theme pieces missing
    w = World()
    w.run("c1.Items[1].GetBagID = nil; c1.Items[2].GetBagID = function() error('boom') end; FS.BagHighlight.Set(1)")
    check("hover.a_button_without_a_usable_GetBagID_is_skipped", lit(w, "c1") == "3,4", lit(w, "c1"))
    w.run("FS.BagHighlight.Clear(); SECRET_IDS = true; FS.BagHighlight.Set(1)")
    check("hover.a_secret_bag_id_lights_nothing", lit(w, "c1") == "" and lit(w, "c2") == "")
    w.run("SECRET_IDS = false; FS.BagHighlight.Clear(); __clearSwallowed()")
    w.run("FS.Theme.ApplyNineSlice = nil; FS.BagHighlight.Set(1); FS.BagHighlight.Set(2)")
    check("hover.missing_theme_helper_degrades_quietly_and_once",
          lit(w, "c1") == "" and w.degrade() == "bags_hover_highlight" and "ApplyNineSlice" in w.swallowed(), f"{w.degrade()} / {w.swallowed()}")
    check("hover.slots_keep_their_plate_when_the_highlight_cannot_be_built", w.ev("RegionCount(c1.Items[1], 'plate') == 1"))


# ---------------------------------------------------------------------------------------------------------------------
# The window: header row, footer, chrome, empty wells (the approved bag redesign, mockups/minimap-bags-cleanup-2026-11-12)
# ---------------------------------------------------------------------------------------------------------------------

# Design values in UI units (the mockup is drawn at 2x: 14 px margins = 7, 34 px keys = 17, 8 px = 4, 12 px = 6, 54 px = 27)
MARGIN, KEY, KEY_GAP, SEARCH_GAP, RULE_GAP, FOOT_BELOW, CELL = 7, 17, 4, 6, 7, 27, 19


def px(units: float, es: float) -> int:
    return math.floor(units * es + 0.5)


def even_px(units: float, es: float) -> int:
    n = max(2, math.ceil(units * es - 1e-6))
    return n + (n % 2)


def whole(v: float, eps: float = 1e-6) -> bool:
    return abs(v - round(v)) < eps


PLACE = "{ left = 100.3, top = 800.7, cols = %d, size = 37, pitch = 42, padL = 7, padR = 8, padT = 75, padB = 28 }"


def scene(es: float = 1.0, *, cols: int = 3, **kw) -> World:
    """A world with the combined window and the backpack laid out like Blizzard lays them out, at `es` pixels per unit."""
    w = World(**kw)
    w.run(f"ES = {es}")
    w.run(f"PlaceGrid(comb, {PLACE % cols}); PlaceGrid(c1, {PLACE % 2}); PlaceGrid(c2, {PLACE % 2})")
    return w


def window_ok(w: World, name: str, frame: str = "comb") -> bool:
    ok = bool(w.ev(f"FS.BagsWindow ~= nil and FS.BagsWindow.Of({frame}) ~= nil"))
    if not ok:
        check(name, False, "FS.BagsWindow.Of(frame) is missing")
    return ok


def check_window_spacing() -> None:
    # Every distance, in physical pixels, at several UI scales. Equal design values give equal pixel counts, so the margin
    # above the header row equals the gap under it; every edge and glyph lands on a whole pixel.
    for es in (1.0, 1.2, 1.25, 1.5, 2.0):
        t = f"window.es{es}"
        w = scene(es)
        w.run("OpenFull(comb)")
        if not window_ok(w, f"{t}.exists"):
            continue
        L = lambda path: float(w.ev(f"FS.BagsWindow.Of(comb).layout.{path}")) * es       # noqa: E731  (pixels)
        m, key, kg, sg = px(MARGIN, es), even_px(KEY, es), px(KEY_GAP, es), px(SEARCH_GAP, es)
        names = ("width", "height", "grid.left", "grid.right", "grid.top", "grid.bottom", "search.x", "search.y", "search.w", "search.h",
                 "sort.x", "sort.y", "sort.w", "sort.h", "close.x", "close.y", "close.w", "close.h", "rule.x", "rule.y", "rule.w",
                 "rule.h", "count.x", "count.cy", "money.right", "band.y", "band.h")
        check(f"{t}.every_edge_on_a_whole_pixel", all(whole(L(n)) for n in names), str({n: L(n) for n in names if not whole(L(n))}))
        # frame edge to row == row to grid, and the same at the sides
        check(f"{t}.margin_above_the_row", round(L("search.y")) == m and round(L("close.y")) == m, f"{L('search.y')} vs {m}")
        check(f"{t}.row_to_grid_gap_equals_the_margin", round(L("grid.top") - L("search.y") - L("search.h")) == m,
              f"gap {L('grid.top') - L('search.y') - L('search.h')} vs {m}")
        check(f"{t}.side_margins", round(L("grid.left")) == m and round(L("width") - L("grid.right")) == m, f"{L('grid.left')} / {L('width') - L('grid.right')}")
        check(f"{t}.keys_are_square_and_even", round(L("close.w")) == key and round(L("close.h")) == key and round(L("sort.w")) == key and round(L("sort.h")) == key
              and round(L("search.h")) == key, f"{L('close.w')} {L('sort.w')} {L('search.h')} vs {key}")
        check(f"{t}.search_starts_on_the_grid_left_edge", round(L("search.x")) == round(L("grid.left")), f"{L('search.x')} vs {L('grid.left')}")
        check(f"{t}.keys_end_on_the_grid_right_edge", round(L("close.x") + L("close.w")) == round(L("grid.right")), f"{L('close.x') + L('close.w')} vs {L('grid.right')}")
        check(f"{t}.sort_close_gap", round(L("close.x") - L("sort.x") - L("sort.w")) == kg, f"{L('close.x') - L('sort.x') - L('sort.w')} vs {kg}")
        check(f"{t}.search_sort_gap", round(L("sort.x") - L("search.x") - L("search.w")) == sg, f"{L('sort.x') - L('search.x') - L('search.w')} vs {sg}")
        # footer: rule 7 under the grid, the window 27 under it; count on the grid's left edge, money on its right edge
        check(f"{t}.rule_gap_under_the_grid", round(L("rule.y") - L("grid.bottom")) == px(RULE_GAP, es), f"{L('rule.y') - L('grid.bottom')}")
        check(f"{t}.rule_is_one_physical_pixel_and_spans_the_grid", round(L("rule.h")) == 1 and round(L("rule.x")) == round(L("grid.left"))
              and round(L("rule.w")) == round(L("grid.right") - L("grid.left")), f"{L('rule.h')} {L('rule.x')} {L('rule.w')}")
        check(f"{t}.window_bottom_under_the_grid", round(L("height") - L("grid.bottom")) == px(FOOT_BELOW, es), f"{L('height') - L('grid.bottom')}")
        check(f"{t}.count_on_the_grid_left_edge", round(L("count.x")) == round(L("grid.left")), f"{L('count.x')}")
        check(f"{t}.money_on_the_grid_right_edge", round(L("money.right")) == round(L("grid.right")), f"{L('money.right')}")
        top_gap = L("count.cy") - (L("rule.y") + L("rule.h"))
        bottom_gap = L("height") - L("count.cy")
        check(f"{t}.footer_text_centred_between_rule_and_edge", abs(top_gap - bottom_gap) <= 1.0001, f"{top_gap} vs {bottom_gap}")

        # the chrome frame sits MARGIN + KEY + MARGIN above and FOOT_BELOW under the grid, MARGIN beside it: its top left corner is
        # pixel snapped (within half a pixel of the ideal edge), its size is the layout's exactly
        chrome_pts = int(w.ev("#FS.BagsWindow.Of(comb).chrome._pts"))
        if chrome_pts == 1 and str(w.ev("FS.BagsWindow.Of(comb).chrome._pts[1][1]")) == "TOPLEFT":
            def pt(k): return float(w.ev(f"FS.BagsWindow.Of(comb).chrome._pts[1][{k}]"))
            fl, ft = (float(w.ev(f"comb._rect[{i}]")) for i in (1, 3))
            gl, gt = (float(w.ev(f"comb._grid[{i}]")) for i in (1, 3))
            want = (gl - m / es - fl, gt + (2 * m + key) / es - ft)
            got = (pt(4), pt(5))
            check(f"{t}.chrome_corner_follows_the_measured_grid",
                  all(abs(a - b) <= 0.5 / es + 1e-6 for a, b in zip(got, want)) and all(whole(v * es) for v in got), f"{got} vs {want}")
            check(f"{t}.chrome_size_is_the_layouts",
                  abs(float(w.ev("FS.BagsWindow.Of(comb).chrome._w")) - L("width") / es) < 1e-6 and abs(float(w.ev("FS.BagsWindow.Of(comb).chrome._h")) - L("height") / es) < 1e-6)
            gw_units = float(w.ev("comb._grid[2] - comb._grid[1]"))
            check(f"{t}.chrome_width_is_the_grid_plus_two_margins", abs(L("width") - (px(gw_units, es) + 2 * m)) < 1e-6, f"{L('width')} vs {px(gw_units, es) + 2 * m}")
        else:
            check(f"{t}.chrome_is_anchored_by_its_top_left_corner", False, str(chrome_pts))

        # Blizzard's own controls sit exactly on the layout's rects
        def ctrl(expr: str, key_: str) -> bool:
            p = lambda k: float(w.ev(f"{expr}._pts[#{expr}._pts][{k}]"))                                           # noqa: E731
            chrome_ok = bool(w.ev(f"{expr}._pts[#{expr}._pts][2] == FS.BagsWindow.Of(comb).chrome and #{expr}._pts == 1"))
            return (chrome_ok and abs(p(4) - float(w.ev(f"FS.BagsWindow.Of(comb).layout.{key_}.x"))) < 1e-6
                    and abs(-p(5) - float(w.ev(f"FS.BagsWindow.Of(comb).layout.{key_}.y"))) < 1e-6
                    and abs(float(w.ev(f"{expr}._w")) - float(w.ev(f"FS.BagsWindow.Of(comb).layout.{key_}.w"))) < 1e-6
                    and abs(float(w.ev(f"{expr}._h")) - float(w.ev(f"FS.BagsWindow.Of(comb).layout.{key_}.h"))) < 1e-6)
        check(f"{t}.search_box_sits_on_its_rect", ctrl("BagItemSearchBox", "search"))
        check(f"{t}.sort_button_sits_on_its_rect", ctrl("BagItemAutoSortButton", "sort"))
        check(f"{t}.close_button_sits_on_its_rect", ctrl("comb.CloseButton", "close"))

        # glyphs centred in their slots, to the pixel
        for label, slot in (("sort", "FS.BagsWindow.Of(comb).sortPlate"), ("close", "FS.BagsWindow.Of(comb).closePlate"),
                            ("magnifier", "FS.BagsWindow.Of(comb).searchCell")):
            box = [float(v) for v in w.ev(f"(function() local b = GlyphBox({slot}); return b[1] .. ' ' .. b[2] .. ' ' .. b[3] .. ' ' .. b[4] end)()").split()]
            sw = float(w.ev(f"{slot}._w")) * es
            sh = float(w.ev(f"{slot}._h")) * es
            check(f"{t}.{label}_glyph_centred_in_its_slot",
                  abs(box[0] - (sw - box[1])) < 1e-6 and abs(box[2] - (sh - box[3])) < 1e-6 and all(whole(v) for v in box),
                  f"box {box} in {sw}x{sh}")
        check(f"{t}.nothing_swallowed", w.swallowed() == "", w.swallowed())


def check_window_shapes() -> None:
    # What the pieces are: the chrome is OURS (a child frame with the panel look), Blizzard's own frame art is stripped, the
    # keys are cut-corner plates (search chamfer 4, keys 3) with the approved edge colours, no stock art shows.
    w = scene(1.2)
    w.run("OpenFull(comb)")
    if not window_ok(w, "window.shapes.exists"):
        return
    check("window.chrome_is_a_child_frame_with_the_panel_look",
          w.ev("FS.BagsWindow.Of(comb).chrome._parent == comb and Count('SkinPanel', FS.BagsWindow.Of(comb).chrome) == 1"))
    check("window.panel_look_is_not_drawn_on_the_blizzard_frame_itself", w.ev("Count('SkinPanel', comb) == 0 and Count('StripBlizzardChrome', comb) >= 1"))
    check("window.chrome_sits_at_the_frame_level_under_the_controls", w.ev("FS.BagsWindow.Of(comb).chrome:GetFrameLevel() <= comb:GetFrameLevel()"))
    check("window.chrome_takes_no_mouse", w.ev("FS.BagsWindow.Of(comb).chrome._mouse ~= true and FS.BagsWindow.Of(comb).searchPlate._mouse ~= true "
                                               "and FS.BagsWindow.Of(comb).sortPlate._mouse ~= true and FS.BagsWindow.Of(comb).closePlate._mouse ~= true"))
    chamfers = {k: w.ev(f"FS.BagsWindow.Of(comb).{k}.fsSkin and FS.BagsWindow.Of(comb).{k}.fsSkin.chamfer") for k in ("searchPlate", "sortPlate", "closePlate")}
    check("window.search_plate_chamfer_4_keys_chamfer_3", chamfers == {"searchPlate": 4, "sortPlate": 3, "closePlate": 3}, str(chamfers))
    ink = w.ev("(function() for _, r in ipairs(FS.BagsWindow.Of(comb).searchPlate._regions) do if r._tag == 'face' then "
               "local a, b, c, d = r:GetVertexColor(); return a .. ' ' .. b .. ' ' .. c .. ' ' .. d end end end)()")
    check("window.search_field_has_a_dark_ink_face", ink is not None and float(str(ink).split()[0]) < 0.1 and float(str(ink).split()[3]) == 1.0, str(ink))
    check("window.keys_have_no_face_fill", w.ev("(function() for _, k in ipairs({ 'sortPlate', 'closePlate' }) do for _, r in ipairs(FS.BagsWindow.Of(comb)[k]._regions) do "
                                                "if r._tag == 'face' then return false end end end return true end)()"))

    def ring(plate: str) -> list[float]:
        return [float(v) for v in str(w.ev(f"(function() local r = FS.BagsWindow.Of(comb).{plate}.fsSkin.border.ring; local a, b, c, d = r:GetVertexColor(); "
                                           f"return a .. ' ' .. b .. ' ' .. c .. ' ' .. d end)()")).split()]
    cyan, violet, pink = ring("searchPlate"), ring("sortPlate"), ring("closePlate")
    check("window.search_edge_is_cyan_at_about_55_percent", near(cyan[0], 0.133) and near(cyan[2], 1) and 0.5 <= cyan[3] <= 0.6, str(cyan))
    check("window.sort_edge_is_violet", near(violet[0], 0.659) and near(violet[2], 0.969), str(violet))
    check("window.close_edge_is_pink", near(pink[0], 1) and near(pink[1], 0.18) and near(pink[2], 0.592), str(pink))
    # no stock art on any control, whatever Blizzard does to it afterwards
    w.run("BagItemSearchBox.Left:SetAlpha(1); BagItemSearchBox.searchIcon:SetAlpha(1); BagItemAutoSortButton:SetNormalTexture('x'); "
          "BagItemAutoSortButton.NormalTexture:SetAlpha(1); comb.CloseButton._regions[1]:SetAlpha(1); comb.PortraitButton.Highlight:SetAlpha(1)")
    check("window.search_box_art_is_held_hidden", w.ev("not Visible(BagItemSearchBox.Left) and not Visible(BagItemSearchBox.Middle) and not Visible(BagItemSearchBox.Right) "
                                                       "and not Visible(BagItemSearchBox.searchIcon)"))
    check("window.sort_button_art_is_held_hidden", w.ev("not Visible(BagItemAutoSortButton.NormalTexture) and not Visible(BagItemAutoSortButton.PushedTexture)"))
    check("window.close_button_art_is_held_hidden", w.ev("not Visible(comb.CloseButton._regions[1])"))
    check("window.portrait_highlight_is_held_hidden", w.ev("not Visible(comb.PortraitButton.Highlight)"))
    # the Blizzard search placeholder and typed text wear the mono font; the placeholder starts after the magnifier cell
    check("window.search_text_is_mono", w.ev("BagItemSearchBox.Instructions._font ~= nil and BagItemSearchBox.Instructions._font[1] == 'mono'"))
    check("window.search_placeholder_starts_after_the_magnifier_cell",
          w.ev("(function() local p = BagItemSearchBox.Instructions._pts[#BagItemSearchBox.Instructions._pts]; return p ~= nil and p[1] == 'TOPLEFT' "
               "and p[4] >= 19 end)()"))
    check("window.nothing_swallowed", w.swallowed() == "", w.swallowed())
    check("window.no_degrade_logs", w.degrade() == "", w.degrade())


def check_window_states() -> None:
    # Hover and press follow Blizzard's own control (post-hooks on its scripts), and the shared sort button lights the plate of
    # the window that owns it at that moment.
    w = scene(1.2)
    w.run("OpenFull(comb); OpenFull(c1)")
    if not window_ok(w, "window.states.exists"):
        return
    glyph = lambda win: [round(float(v), 4) for v in str(w.ev(f"(function() local r = FS.BagsWindow.Of({win}).sortPlate._regions; "
                                                              "for _, q in ipairs(r) do if q._tag == 'created' and q._color then return q._color[1] .. ' ' .. q._color[2] .. ' ' .. q._color[3] end end end)()")).split()]
    fire = lambda obj, script: w.run(f"for _, fn in ipairs({obj}._scripts.{script} or {{}}) do fn({obj}) end")      # noqa: E731
    rest = glyph("c1")
    fire("BagItemAutoSortButton", "OnEnter")
    hover = glyph("c1")
    check("window.states.hover_lifts_the_glyph_of_the_owning_window", hover[0] > rest[0] and hover[1] > rest[1], f"{rest} -> {hover}")
    check("window.states.the_other_window_is_not_painted", glyph("comb") == rest, str(glyph("comb")))
    fire("BagItemAutoSortButton", "OnMouseDown")
    pressed = glyph("c1")
    check("window.states.pressed_lifts_more", pressed[1] > hover[1], f"{hover} -> {pressed}")
    fire("BagItemAutoSortButton", "OnLeave")
    check("window.states.leaving_restores_the_rest_look", glyph("c1") == rest, f"{glyph('c1')} vs {rest}")
    fire("BagItemSearchBox", "OnEditFocusGained")
    ring = float(w.ev("FS.BagsWindow.Of(c1).searchPlate.fsSkin.border.ring._vc[4]"))
    check("window.states.focus_takes_the_search_edge_to_full", ring == 1, str(ring))
    fire("BagItemSearchBox", "OnEditFocusLost")
    check("window.states.focus_lost_returns_it", 0.5 <= float(w.ev("FS.BagsWindow.Of(c1).searchPlate.fsSkin.border.ring._vc[4]")) <= 0.6)
    w.run("OpenFull(comb)")
    fire("BagItemAutoSortButton", "OnEnter")
    check("window.states.ownership_moves_the_painting_with_it", glyph("comb")[0] > rest[0] and glyph("c1") == rest, f"{glyph('comb')} {glyph('c1')}")
    check("window.states.hooks_installed_once_per_control",
          int(w.ev("#(BagItemAutoSortButton._scripts.OnEnter or {})")) == 1 and int(w.ev("#(BagItemSearchBox._scripts.OnEditFocusGained or {})")) == 1)
    check("window.states.nothing_swallowed", w.swallowed() == "", w.swallowed())


def check_window_membership() -> None:
    # The plates follow Blizzard's own ownership of the search box and sort button (one of each, re-parented between the
    # backpack and the combined window), a bag with neither has just the close key, and Blizzard's re-anchoring on every
    # Update() never leaves the controls off their rects.
    w = scene(1.2)
    w.run("OpenFull(comb); OpenFull(c1); OpenFull(c2)")
    if not window_ok(w, "window.membership.exists", "c2"):
        return
    check("window.membership.the_owner_of_the_search_box_shows_its_plates",
          w.ev("FS.BagsWindow.Of(c1).searchPlate._shown and FS.BagsWindow.Of(c1).sortPlate._shown"))
    check("window.membership.the_former_owner_hides_its_plates",
          w.ev("not FS.BagsWindow.Of(comb).searchPlate._shown and not FS.BagsWindow.Of(comb).sortPlate._shown"))
    check("window.membership.a_bag_without_search_has_the_close_key_only",
          w.ev("not FS.BagsWindow.Of(c2).searchPlate._shown and not FS.BagsWindow.Of(c2).sortPlate._shown and FS.BagsWindow.Of(c2).closePlate._shown"))
    check("window.membership.close_key_flush_right_without_a_search_row_neighbour",
          w.ev("FS.BagsWindow.Of(c2).layout.search == nil and FS.BagsWindow.Of(c2).layout.sort == nil")
          and abs(float(w.ev("FS.BagsWindow.Of(c2).layout.close.x + FS.BagsWindow.Of(c2).layout.close.w - FS.BagsWindow.Of(c2).layout.grid.right")) * 1.2) < 1e-6)
    check("window.membership.controls_follow_the_owner",
          w.ev("BagItemSearchBox._pts[#BagItemSearchBox._pts][2] == FS.BagsWindow.Of(c1).chrome"))
    w.run("OpenFull(comb)")
    check("window.membership.ownership_moves_back_with_blizzards_reparent",
          w.ev("BagItemSearchBox._pts[#BagItemSearchBox._pts][2] == FS.BagsWindow.Of(comb).chrome and FS.BagsWindow.Of(comb).searchPlate._shown "
               "and not FS.BagsWindow.Of(c1).searchPlate._shown"))
    # Blizzard re-anchors on every Update; the post-hook puts the controls back every time, with one anchor each
    for _ in range(3):
        w.run("comb:Update()")
    check("window.membership.update_after_update_keeps_one_anchor_each",
          w.ev("#BagItemSearchBox._pts == 1 and #BagItemAutoSortButton._pts == 1 and #comb.CloseButton._pts == 1"))
    # the grid changing (the player's column setting) re-lays everything out
    w.run(f"PlaceGrid(comb, {PLACE % 2}); comb:UpdateItems()")
    es = 1.2
    check("window.membership.a_new_grid_width_resizes_the_window",
          abs(float(w.ev("FS.BagsWindow.Of(comb).layout.width")) * es - (round((37 + 42) * es) + 2 * px(MARGIN, es))) <= 1.0001,
          str(w.ev("FS.BagsWindow.Of(comb).layout.width")))
    check("window.membership.nothing_swallowed", w.swallowed() == "", w.swallowed())


def check_window_footer(db: dict) -> None:
    w = scene(1.0)
    w.run("MONEY = 13790; OpenFull(comb); OpenFull(c1)")
    if not window_ok(w, "window.footer.exists"):
        return
    hexes = {k: "".join(f"{int(c * 255 + 0.5):02x}" for c in db[k]) for k in ("gold", "silver", "copper")}
    text = str(w.ev("FS.BagsWindow.Of(comb).money:GetText()"))
    want = f"|cff{hexes['gold']}1g|r |cff{hexes['silver']}37s|r |cff{hexes['copper']}90c|r"
    check("window.footer.money_in_the_data_bar_gold_look", text == want, f"{text!r} vs {want!r}")
    check("window.footer.no_gold_label", "GOLD" not in text.upper() and "gold" not in text, text)
    for amount, shown in ((0, "0c"), (100, "1s 0c"), (10000, "1g 0s 0c"), (123456789, "12345g 67s 89c")):
        w.run(f"MONEY = {amount}; FireEvent('PLAYER_MONEY')")
        plain = re.sub(r"\|c[0-9a-f]{8}|\|r", "", str(w.ev("FS.BagsWindow.Of(comb).money:GetText()")))
        check(f"window.footer.money_{amount}_collapses_like_blizzards", plain == shown, f"{plain!r} vs {shown!r}")
    w.run("MONEY = 13790; FireEvent('PLAYER_MONEY')")
    count = str(w.ev("FS.BagsWindow.Of(comb).count:GetText()"))
    check("window.footer.count_is_used_over_total_combined", count == "2/3", count)
    check("window.footer.count_is_used_over_total_backpack", str(w.ev("FS.BagsWindow.Of(c1).count:GetText()")) == "2/4",
          str(w.ev("FS.BagsWindow.Of(c1).count:GetText()")))
    check("window.footer.count_has_no_label", re.fullmatch(r"\d+/\d+", count) is not None, count)
    cyan = [float(v) for v in str(w.ev("(function() local a, b, c, d = FS.BagsWindow.Of(comb).count:GetTextColor(); return a .. ' ' .. b .. ' ' .. c .. ' ' .. d end)()")).split()]
    check("window.footer.count_is_cyan", near(cyan[0], 0.133) and near(cyan[1], 0.878) and near(cyan[2], 1), str(cyan))
    # the count follows the bag: a slot filling, a slot emptying
    w.run("comb.infos[2] = { icon = 140 }; comb:UpdateItems()")
    check("window.footer.count_follows_a_slot_filling", str(w.ev("FS.BagsWindow.Of(comb).count:GetText()")) == "3/3")
    w.run("comb.infos = {}; comb:UpdateItems()")
    check("window.footer.count_follows_the_bag_emptying", str(w.ev("FS.BagsWindow.Of(comb).count:GetText()")) == "0/3")
    # Blizzard's own money frame stays functional but invisible; a bag without a money line shows none of ours
    check("window.footer.blizzard_money_frame_is_invisible_not_hidden", w.ev("comb.MoneyFrame:GetAlpha() == 0 and comb.MoneyFrame:IsShown()"))
    w.run("c2.MoneyFrame:Hide(); OpenFull(c2)")
    check("window.footer.a_bag_without_money_shows_no_money", w.ev("not FS.BagsWindow.Of(c2).money._shown and FS.BagsWindow.Of(c2).count._shown"))
    # a secret amount is never formatted
    w.run("SECRET_IDS = true; local real = GetMoney; GetMoney = function() return SECRET_VALUE end; FireEvent('PLAYER_MONEY'); GetMoney = real; SECRET_IDS = false")
    check("window.footer.a_secret_amount_swallows_nothing", w.swallowed() == "", w.swallowed())
    check("window.footer.no_degrade_logs", w.degrade() == "", w.degrade())


def check_empty_wells() -> None:
    w = scene(1.0)
    w.run("OpenFull(comb); OpenFull(c1)")
    if not window_ok(w, "wells.window_exists"):
        return
    shown = lambda e: bool(w.ev(f"WellShown({e})"))                                                             # noqa: E731
    check("wells.empty_slot_shows_a_dark_well", shown("comb.Items[2]") and shown("c1.Items[2]") and shown("c1.Items[4]"))
    check("wells.filled_slots_show_none", not shown("comb.Items[1]") and not shown("comb.Items[3]") and not shown("c1.Items[1]"))
    look = dict(w.ev("(function() local r = WellOf(comb.Items[2]); return { path = r._texture, layer = r._layer, sub = r._sub, "
                     "ringSub = (function() for _, q in ipairs(comb.Items[2]._regions) do if q._tag == 'ring' then return q._sub end end end)() } end)()").items())
    check("wells.well_is_the_slot_plate_shape_above_the_icon_under_the_ring",
          look["path"] == "slice_cut2_button.tga" and look["layer"] == "OVERLAY" and look["sub"] < -1 and look["sub"] < look["ringSub"], str(look))

    # whatever the empty art is called, it is covered: the cover follows the item API, not a name
    w.run("comb.Items[2].icon:SetAtlas('some-art-this-patch-invented'); comb.Items[2].icon:SetShown(true); comb:UpdateItems()")
    check("wells.an_unknown_empty_art_still_gets_a_well", shown("comb.Items[2]"))
    check("wells.an_unknown_empty_art_is_cleared_off_the_icon", w.ev("comb.Items[2].icon._atlas == nil and comb.Items[2].icon._texture == nil"))
    check("wells.an_unknown_empty_art_is_not_an_item_for_ring_or_corners",
          w.ev("not CornersShown(comb.Items[2])") and near(float(w.ev("RingColor(comb.Items[2])[1]")), 0x5b / 255))
    # an empty slot that wears a plain texture (not an atlas) is covered too
    w.run("comb.Items[2].icon:SetTexture('Interface\\\\Anything\\\\Pouch'); comb.Items[2].icon:SetShown(true); comb:UpdateItems()")
    check("wells.an_empty_slot_with_any_texture_still_gets_a_well", shown("comb.Items[2]") and not w.ev("CornersShown(comb.Items[2])"))
    # a filled slot is never covered, whatever its texture is
    w.run("comb.Items[1].icon:SetTexture('Interface\\\\Icons\\\\NeverSeenBefore'); comb:UpdateItems()")
    check("wells.a_filled_slot_with_an_unusual_texture_is_not_covered", not shown("comb.Items[1]") and w.ev("comb.Items[1].icon._texture ~= nil") and w.ev("CornersShown(comb.Items[1])"))
    # filling and emptying follow the next pass
    w.run("comb.infos[2] = { icon = 141 }; comb:UpdateItems()")
    check("wells.a_filled_slot_loses_its_well", not shown("comb.Items[2]") and w.ev("CornersShown(comb.Items[2])"))
    w.run("comb.infos[2] = nil; comb:UpdateItems()")
    check("wells.an_emptied_slot_gets_one", shown("comb.Items[2]") and not w.ev("CornersShown(comb.Items[2])"))
    # an icon repaint with no pass (Blizzard sets the empty art again)
    w.run("comb.Items[2]:SetItemButtonTexture(nil)")
    check("wells.the_well_survives_blizzard_repainting_the_empty_art", shown("comb.Items[2]"))
    # once per button, however many passes
    for _ in range(3):
        w.run("comb:UpdateItems(); c1:UpdateItems(); OpenFull(comb)")
    check("wells.one_well_per_button", all(w.ev(f"RegionCount({b}, 'well') == 1") for b in ("comb.Items[1]", "comb.Items[2]", "c1.Items[2]")))
    # the bank is not a bag window: never covered
    w.run("bank.RefreshAllItemsForSelectedTab(bank)")
    check("wells.bank_slots_never_get_a_well", all(w.ev(f"RegionCount(bank.pool[{i}], 'well') == 0") for i in (1, 2, 3)))
    # nothing readable: no cover, no error
    w.run("SECRET_IDS = true; comb.Items[2]:SetItemButtonTexture(nil); comb:UpdateItems(); SECRET_IDS = false")
    check("wells.unreadable_item_data_covers_nothing_and_swallows_nothing", w.swallowed() == "", w.swallowed())
    w2 = scene(1.0)
    w2.run("C_Container = nil; OpenFull(comb)")
    check("wells.no_item_api_means_no_well_and_no_error", w2.ev("not WellShown(comb.Items[2])") and w2.swallowed() == "", w2.swallowed())
    # a well that cannot be built logs once, is not retried on every pass, and leaves the slot as it was
    w5 = scene(1.0, pre="FS.Theme.__plate = FS.Theme.AddCut2Texture; FS.Theme.AddCut2Texture = function(f, path, c, l, s) "
                        "if s == -3 then error('boom') end return FS.Theme.__plate(f, path, c, l, s) end")
    w5.run("OpenFull(comb)")
    first = len(w5.swallowed().split("; "))
    for _ in range(3):
        w5.run("comb:UpdateItems(); OpenFull(comb)")
    check("wells.a_failed_well_logs_once_and_is_not_retried", w5.degrade().count("bags_well") == 1 and len(w5.swallowed().split("; ")) == first,
          f"{w5.degrade()} {first} {len(w5.swallowed().split('; '))}")
    check("wells.a_failed_well_leaves_the_slot_skinned", w5.ev("Count('SkinCutButton', comb.Items[2]) == 1 and RegionCount(comb.Items[2], 'plate') == 1"))
    # combat: nothing protected is touched, the well still follows
    w3 = scene(1.0)
    w3.run("OpenFull(comb); INCOMBAT = true; PROTECTED_CALLS = {}; comb.infos[2] = { icon = 142 }; comb.infos[1] = nil; comb:UpdateItems()")
    prot = str(w3.ev("table.concat(PROTECTED_CALLS, ',')"))
    check("wells.combat_pass_moves_wells_with_no_protected_call", prot == "" and w3.ev("WellShown(comb.Items[1]) and not WellShown(comb.Items[2])"), prot)
    w3.run("EndCombat()")
    check("wells.nothing_swallowed", w3.swallowed() == "" and w.degrade() == "", w3.swallowed() + w.degrade())


def check_window_taint_surface() -> None:
    # The open ADDON_ACTION_FORBIDDEN UseContainerItem report is blamed on this addon: nothing new may be written onto Blizzard's
    # item buttons or container frames (fields, hooks, anchors, parents, attributes, hit rects of the buttons).
    w = scene(1.2)
    w.run("OpenFull(comb); OpenFull(c1); OpenFull(c2); bank.RefreshAllItemsForSelectedTab(bank)")
    if not window_ok(w, "taint.window_exists"):
        return
    item_ok = {"fsBagItemSkinned", "fsSkin", "fsBagPlate", "fsBagCorners", "fsBagRingColor", "fsBagHighlight"}
    cont_ok = {"fsBagSkin", "fsBagShowHooked", "fsBagHideHooked", "fsBagItemHooks"}
    for expr in ("c1.Items[1]", "c1.Items[2]", "comb.Items[1]", "comb.Items[2]", "bank.pool[1]"):
        got = set(filter(None, str(w.ev(f"FsFields({expr})")).split(",")))
        check(f"taint.{expr}_has_no_new_fields", got <= item_ok, f"extra: {sorted(got - item_ok)}")
        names = set(filter(None, str(w.ev(f"HookNames({expr})")).split(",")))
        check(f"taint.{expr}_has_no_new_hooks", names <= {"SetNormalTexture", "SetNormalAtlas", "Initialize"}, str(sorted(names)))
    for expr in ("c1", "c2", "comb"):
        got = set(filter(None, str(w.ev(f"FsFields({expr})")).split(",")))
        check(f"taint.{expr}_has_no_new_fields", got <= cont_ok, f"extra: {sorted(got - cont_ok)}")
        check(f"taint.{expr}_has_only_the_existing_hooks", str(w.ev(f"HookNames({expr})")) == "UpdateItems"
              and int(w.ev(f"#({expr}._scripts.OnShow or {{}})")) == 2 and int(w.ev(f"#({expr}._scripts.OnHide or {{}})")) == 1,
              f"{w.ev(f'HookNames({expr})')} {w.ev(f'#({expr}._scripts.OnShow or {{}})')} {w.ev(f'#({expr}._scripts.OnHide or {{}})')}")
    for expr in ("BagItemSearchBox", "BagItemAutoSortButton", "comb.CloseButton", "c1.CloseButton"):
        check(f"taint.{expr}_has_no_fields", str(w.ev(f"FsFields({expr})")) == "", str(w.ev(f"FsFields({expr})")))
    # item buttons: no anchors, sizes, parents or hit rects of ours
    check("taint.item_buttons_are_never_moved_or_resized", w.ev("(function() for _, b in ipairs(comb.Items) do if b._hit ~= nil or b._parent ~= comb or #b._pts ~= 0 then return false end end return true end)()"))
    check("taint.nothing_swallowed", w.swallowed() == "", w.swallowed())


def check_window_combat() -> None:
    w = scene(1.2)
    w.run("OpenFull(comb); PlaceGrid(comb, %s)" % (PLACE % 3))
    if not window_ok(w, "window.combat.exists"):
        return
    check("window.combat.hit_rect_shrinks_to_the_visible_window",
          w.ev("comb._hit ~= nil and comb._hit[3] > 40 and comb._hit[1] >= 0 and comb._hit[2] >= 0 and comb._hit[4] >= 0"), str(w.ev("comb._hit and table.concat(comb._hit, ',')")))
    # combat: our own regions and plain frames still follow; a protected container's hit rect and our anchors to it are left alone
    w.run("INCOMBAT = true; PROTECTED_CALLS = {}; comb._hitCalls = 0; PlaceGrid(comb, %s); comb:Update()" % (PLACE % 2))
    prot = str(w.ev("table.concat(PROTECTED_CALLS, ',')"))
    check("window.combat.relayout_in_combat_calls_no_protected_method", prot == "", prot)
    check("window.combat.unprotected_container_is_relaid_out", abs(float(w.ev("FS.BagsWindow.Of(comb).layout.width")) * 1.2 - (round(79 * 1.2) + 2 * px(MARGIN, 1.2))) <= 1.0001)
    w.run("EndCombat(); comb._protected = true; INCOMBAT = true; comb._hitCalls = 0; local n = #FS.BagsWindow.Of(comb).chrome._pts; CHROME_PTS = n; "
          "PlaceGrid(comb, %s); comb:Update()" % (PLACE % 3))
    check("window.combat.protected_container_is_not_re_anchored_to_in_combat",
          w.ev("#FS.BagsWindow.Of(comb).chrome._pts == CHROME_PTS and comb._hitCalls == 0"))
    w.run("EndCombat()")
    w.run("EndCombat(); FireEvent('PLAYER_REGEN_ENABLED')")
    check("window.combat.the_layout_catches_up_when_combat_ends",
          abs(float(w.ev("FS.BagsWindow.Of(comb).layout.width")) * 1.2 - (round((2 * 42 + 37) * 1.2) + 2 * px(MARGIN, 1.2))) <= 1.0001,
          str(w.ev("FS.BagsWindow.Of(comb).layout.width")))
    check("window.combat.nothing_swallowed", w.swallowed() == "", w.swallowed())


def check_window_degrade() -> None:
    # no geometry yet (a window that was never laid out): nothing placed, Blizzard's controls untouched, no error, no log
    w = World()
    w.run("OpenFull(comb)")
    if window_ok(w, "window.degrade.exists_without_geometry"):
        check("window.degrade.chrome_stays_hidden_until_measured", w.ev("not FS.BagsWindow.Of(comb).chrome._shown"))
        check("window.degrade.controls_keep_blizzards_anchors", w.ev("BagItemSearchBox._pts[#BagItemSearchBox._pts][2] == comb and BagItemSearchBox._pts[1][4] == 62"))
        check("window.degrade.blizzard_money_frame_stays_visible_until_the_footer_exists", w.ev("comb.MoneyFrame:GetAlpha() == 1"))
        check("window.degrade.quiet", w.swallowed() == "" and w.degrade() == "", w.swallowed() + w.degrade())
    # a Theme without the strip helper falls back to the old panel skin, with one log
    w = World(pre="FS.Theme.StripBlizzardChrome = nil")
    w.run("PlaceGrid(comb, %s); OpenFull(comb)" % (PLACE % 3))
    check("window.degrade.no_strip_helper_uses_the_old_panel_skin_and_logs_once",
          w.ev("Count('SkinPanel', comb) == 1 and (FS.BagsWindow == nil or FS.BagsWindow.Of(comb) == nil)") and w.degrade().count("bags_window") == 1 and w.swallowed() == "", w.degrade() + w.swallowed())
    # no cut fill helper: the search face is a flat ink fill, nothing errors
    w = World(pre="FS.Theme.AddCutSliceFill = nil")
    w.run("PlaceGrid(comb, %s); OpenFull(comb)" % (PLACE % 3))
    check("window.degrade.no_cut_fill_helper_still_builds_the_window", window_ok(w, "window.degrade.cut_fill_exists") and w.swallowed() == "", w.swallowed())
    # a throwing Theme.SkinButton: the window falls back, once
    w = World(pre="local orig = FS.Theme.SkinButton; FS.Theme.SkinButton = function(b, o) if o and o.chamfer and o.chamfer <= 4 then error('boom') end return orig(b, o) end")
    w.run("PlaceGrid(comb, %s); OpenFull(comb)" % (PLACE % 3))
    check("window.degrade.a_throwing_button_skin_falls_back_with_one_log", w.degrade().count("bags_window") == 1, w.degrade())


TOKEN_H = 17


def check_window_tokens() -> None:
    # Blizzard's watched-currency strip (BackpackTokenFrame): the window grows a row under the footer for it, the strip is
    # seated on that row, its border art is held, its counts are mono, and the window is exactly the old one without it.
    for es in (1.0, 1.2, 1.25, 1.5):
        t = f"tokens.es{es}"
        w = scene(es, pre="MkTracker(comb, 2)")
        base = scene(es)
        w.run("OpenFull(comb)")
        base.run("OpenFull(comb)")
        if not window_ok(w, f"{t}.exists"):
            continue
        L = lambda path: float(w.ev(f"FS.BagsWindow.Of(comb).layout.{path}")) * es       # noqa: E731  (pixels)
        B = lambda path: float(base.ev(f"FS.BagsWindow.Of(comb).layout.{path}")) * es    # noqa: E731
        m, h = px(MARGIN, es), px(TOKEN_H, es)
        names = ("tokens.x", "tokens.y", "tokens.w", "tokens.h", "tokens.slack", "height")
        check(f"{t}.every_edge_on_a_whole_pixel", all(whole(L(n)) for n in names), str({n: L(n) for n in names if not whole(L(n))}))
        check(f"{t}.row_sits_under_the_footer_and_spans_the_grid",
              round(L("tokens.y")) == round(B("height")) and round(L("tokens.x")) == round(L("grid.left"))
              and round(L("tokens.w")) == round(L("grid.right") - L("grid.left")), f"{L('tokens.y')} vs {B('height')}")
        check(f"{t}.row_is_the_stock_height", round(L("tokens.h")) == h, f"{L('tokens.h')} vs {h}")
        check(f"{t}.window_ends_a_margin_under_the_row", round(L("height") - L("tokens.y") - L("tokens.h")) == m, f"{L('height')}")
        check(f"{t}.last_token_ends_a_margin_inside_the_plate",
              round(L("tokens.slack")) == px(13, es) - m, f"{L('tokens.slack')}")
        check(f"{t}.the_rest_of_the_window_is_the_old_one",
              all(round(L(n)) == round(B(n)) for n in ("width", "grid.top", "grid.bottom", "rule.y", "count.cy", "money.right", "band.h", "close.x", "search.w")),
              str({n: (L(n), B(n)) for n in ("width", "rule.y", "count.cy", "band.h")}))
        check(f"{t}.nothing_swallowed", w.swallowed() == "", w.swallowed())

    w = scene(1.2, pre="MkTracker(comb, 2)")
    w.run("OpenFull(comb)")
    if not window_ok(w, "tokens.seat.exists"):
        return
    win = "FS.BagsWindow.Of(comb)"
    check("tokens.seat.the_plate_is_ours_shown_and_on_the_row",
          w.ev(f"{win}.tokensPlate._shown and {win}.tokensPlate._pts[#{win}.tokensPlate._pts][2] == {win}.chrome "
               f"and math.abs({win}.tokensPlate._pts[#{win}.tokensPlate._pts][4] - {win}.layout.tokens.x) < 1e-6 "
               f"and math.abs(-{win}.tokensPlate._pts[#{win}.tokensPlate._pts][5] - {win}.layout.tokens.y) < 1e-6 "
               f"and math.abs({win}.tokensPlate._w - {win}.layout.tokens.w) < 1e-6 and math.abs({win}.tokensPlate._h - {win}.layout.tokens.h) < 1e-6"))
    seated = (f"#BackpackTokenFrame._pts == 1 and BackpackTokenFrame._pts[1][1] == 'TOPLEFT' and BackpackTokenFrame._pts[1][2] == {win}.chrome "
              f"and math.abs(BackpackTokenFrame._pts[1][4] - {win}.layout.tokens.x) < 1e-6 and math.abs(-BackpackTokenFrame._pts[1][5] - {win}.layout.tokens.y) < 1e-6 "
              f"and math.abs(BackpackTokenFrame._w - ({win}.layout.tokens.w + {win}.layout.tokens.slack)) < 1e-6 "
              f"and math.abs(BackpackTokenFrame._h - {win}.layout.tokens.h) < 1e-6")
    check("tokens.seat.the_strip_sits_on_its_row_with_one_anchor", w.ev(seated))
    w.run("comb:UpdateCurrencyFrames()")
    check("tokens.seat.blizzard_re_anchoring_is_answered", w.ev(seated))
    w.run("BackpackTokenFrame.Border.Left:SetAlpha(1); BackpackTokenFrame.Border.Middle:SetAlpha(1)")
    check("tokens.art.the_border_pieces_are_held_and_stay_held",
          w.ev("BackpackTokenFrame.Border.Left._alpha == 0 and BackpackTokenFrame.Border.Middle._alpha == 0 and BackpackTokenFrame.Border.Right._alpha == 0"))
    check("tokens.art.each_token_keeps_its_icon_and_click",
          w.ev("BackpackTokenFrame.Tokens[1].Icon._alpha == 1 and BackpackTokenFrame.Tokens[2].Icon._alpha == 1"))
    check("tokens.text.counts_are_mono_at_the_footer_size_in_white",
          w.ev("(function() for i = 1, 2 do local c = BackpackTokenFrame.Tokens[i].Count; local f = c._font; "
               "if not (f and f[1] == 'mono' and f[2] == 11 and c._tc[1] == 1 and c._tc[2] == 1 and c._tc[3] == 1) then return false end end return true end)()"))
    w.run("BackpackTokenFrame._n = 3; BackpackTokenFrame:Update()")
    check("tokens.text.a_token_added_later_is_styled_too",
          w.ev("BackpackTokenFrame.Tokens[3].Count._font ~= nil and BackpackTokenFrame.Tokens[3].Count._font[1] == 'mono'"))
    check("tokens.text.the_stock_words_are_kept", w.ev("BackpackTokenFrame.Tokens[2].Count:GetText() == '200'"))
    w.run("comb:Update(); comb:Update(); comb:UpdateTokenTracker()")
    check("tokens.hooks.one_post_hook_each_however_often_it_is_shown",
          w.ev("HookCount(BackpackTokenFrame, 'Update') == 1 and HookCount(comb, 'UpdateCurrencyFrames') == 1"))

    # the strip leaves: the window is the old one again; the strip moves to another window: this one lets go of the row
    base = scene(1.2)
    base.run("OpenFull(comb)")
    w.run("BackpackTokenFrame._n = 0; comb:UpdateTokenTracker()")
    check("tokens.gone.the_row_and_the_plate_go",
          w.ev(f"{win}.layout.tokens == nil and not {win}.tokensPlate._shown")
          and abs(float(w.ev(f"{win}.layout.height")) - float(base.ev("FS.BagsWindow.Of(comb).layout.height"))) < 1e-6)
    w.run("BackpackTokenFrame._n = 2; comb:UpdateTokenTracker(); OpenFull(c1); BackpackTokenFrame:SetParent(c1); comb:UpdateCurrencyFrames()")
    check("tokens.owner.the_strip_follows_its_parent",
          w.ev(f"{win}.layout.tokens == nil and not {win}.tokensPlate._shown"))

    # combat: a protected container is left alone, the layout catches up when combat ends
    w = scene(1.2, pre="MkTracker(comb, 2)")
    w.run("OpenFull(comb); BackpackTokenFrame._n = 0; comb:UpdateTokenTracker(); comb._protected = true; INCOMBAT = true; BackpackTokenFrame._n = 2; comb:UpdateTokenTracker()")
    check("tokens.combat.a_protected_window_is_not_re_anchored_in_combat",
          w.ev("#BackpackTokenFrame._pts == 2 and BackpackTokenFrame._pts[1][1] == 'BOTTOMLEFT'"))
    w.run("EndCombat(); FireEvent('PLAYER_REGEN_ENABLED')")
    check("tokens.combat.the_strip_is_seated_when_combat_ends", w.ev(seated))
    check("tokens.combat.nothing_swallowed", w.swallowed() == "", w.swallowed())

    # a client without the strip, or one whose strip lacks the art, builds the same window and never errors
    w = scene(1.2, pre="MkTracker(comb, 2); BackpackTokenFrame.Border = nil; BackpackTokenFrame.Update = nil")
    w.run("OpenFull(comb)")
    check("tokens.degrade.a_strip_without_border_or_update_is_still_seated", window_ok(w, "tokens.degrade.exists") and w.ev(seated.replace("BackpackTokenFrame._pts", "BackpackTokenFrame._pts")) and w.swallowed() == "", w.swallowed())


def main() -> int:
    db = databar_money()
    check_art()
    check_icon_border()
    check_untouched()
    check_plate_and_border()
    check_icon_corners()
    check_quality_ring()
    check_hold_retry()
    check_money(db)
    check_colorblind()
    check_absent()
    check_gamepad_bar()
    check_bag_highlight()
    check_window_spacing()
    check_window_shapes()
    check_window_states()
    check_window_membership()
    check_window_footer(db)
    check_empty_wells()
    check_window_taint_surface()
    check_window_combat()
    check_window_degrade()
    check_window_tokens()
    print(f"\n{CHECKS} checks, {len(FAILS)} failed" if FAILS else f"\nall {CHECKS} checks passed")
    return len(FAILS)


if __name__ == "__main__":
    sys.exit(main())
