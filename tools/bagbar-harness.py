#!/usr/bin/env python3
"""Headless check of BagBar.lua: the bag slots are SECURE buttons that delegate the click to Blizzard's stock bag buttons.

Runs the real addons/forever-stuwave/Deck.lua and BagBar.lua under lupa against a small STRICT mock WoW API (a method
the mock does not define is a nil call). The mock models the two things the live bug turned on:

  * taint: ToggleBackpack / ToggleBag / ToggleAllBags / OpenBag / CloseBag are recording stubs. The mock's stock bag
    buttons run their own OnClick WITHOUT touching those globals (that is Blizzard code, untainted), so any call that
    reaches a global stub came from our addon code, which on the live client throws ADDON_ACTION_FORBIDDEN when the
    stock item buttons later read the state our call tainted;
  * protection: a button made from SecureActionButtonTemplate is protected, and so is every ancestor of it. A frame a
    protected frame depends on (an anchor target) is RESTRICTED too, and that edge is transitive through the anchors:
    here the chassis (an ancestor of the buttons) is anchored to ForeverSTUwaveXPBar, which is anchored to
    ForeverSTUwaveDataBar, so all three are restricted. In combat a Show/Hide/SetPoint/SetSize/SetParent on any
    restricted frame, or a SetAttribute on a button, is recorded in BLOCKED and does nothing (the client prints
    ADDON_ACTION_BLOCKED). The XP bar and data bar are stubs here; XPBar.lua and DataBar.lua are too heavy to load into
    this mock, so their own combat behaviour (no SetSize/Show/Hide while restricted, replayed at regen) is pinned in
    xpbar-harness.py and databar-harness.py, and this file pins only that the chain makes them restricted.

What it pins:

  * BagBar.lua contains no call to ToggleBackpack/ToggleBag/ToggleAllBags/OpenBag/CloseBag (source scan);
  * each slot is a SecureActionButtonTemplate button with type="click" and clickbutton = its stock button (backpack
    MainMenuBarBackpackButton, bags CharacterBag0..3Slot, reagent CharacterReagentBag0Slot, keyring KeyRingButton),
    useOnKeyDown=false (belt and braces: 12.1's SecureActionButton_OnClick already forces an engine mouse press to the
    up event and RegisterForClicks("AnyUp") dispatches no down event, so a drag start never toggles the bag; the
    attribute still governs a key press or an addon :Click()) and no addon OnClick script (SetScript("OnClick") would
    replace the template's secure handler);
  * a plain, a shift-modified and a right click on each slot reaches the stock button's OnClick exactly once with the
    same mouse button, and NO container-opening global is called from addon code;
  * the stock buttons stay dimmed (alpha 0, mouse off) and are still clicked through;
  * a slot whose stock button is missing is hidden, logged once and never falls back to a Toggle* call;
  * drop (OnReceiveDrag) puts the cursor item in that bag through the C Put* functions and calls no Toggle*, drag
    picks a bag up (not the backpack or the keyring);
  * combat: a layout, availability or rescale change in combat touches no protected frame (BLOCKED stays empty, the
    seated geometry holds), the visual state (lock, hover, pulse, open) still updates, and PLAYER_REGEN_ENABLED
    applies what was deferred; built in combat, the attributes wait for regen; the deck chassis follows the same rule,
    including its PLAYER_LOGIN seat (a login in combat seats at regen, not at login) and the C_Timer retry of that seat
    (combat starting between the login and the retry defers it to regen); PLAYER_ENTERING_WORLD in combat does only the
    non-restricted refresh;
  * hover: entering a bag slot asks Bags.lua (FS.BagHighlight) to light that bag's item slots (backpack 0, bags 1-4,
    reagent 5), leaving or hiding the hovered slot clears, the keyring (no container ID) lights nothing, it works in
    combat without touching a protected frame, and a missing FS.BagHighlight is no error;
  * the restriction chain: the XP bar and the data bar become restricted once the chassis is anchored to the XP bar.

    python3 tools/bagbar-harness.py

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
BAGBAR_LUA = Path(os.environ.get("BAGBAR_LUA") or ADDON / "Modules/Bags/BagBar.lua")   # BAGBAR_LUA: a mutated scratch copy
DECK_LUA = Path(os.environ.get("DECK_LUA") or ADDON / "Modules/ActionBars/Deck.lua")
THEME_LUA = ADDON / "Core/Theme.lua"
EPS = 0.01

STOCK = {
    "backpack": "MainMenuBarBackpackButton",
    "bag1": "CharacterBag0Slot",
    "bag2": "CharacterBag1Slot",
    "bag3": "CharacterBag2Slot",
    "bag4": "CharacterBag3Slot",
    "reagent": "CharacterReagentBag0Slot",
    "keyring": "KeyRingButton",
}
KEYS = list(STOCK)

MOCK = r"""
SCALE, IN_COMBAT = 1, false
LOGS, ALL, BLOCKED, TOGGLES, PUTS, STOCKCLICKS, SETSCRIPT_ONCLICK = {}, {}, {}, {}, {}, {}, 0
CURSOR, KEYRING_ON, RESCALE = nil, true, {}
local noop = function() end

local M = {}
local Obj = { __index = M }
local function newObj(kind, parent, name)
    local o = setmetatable({ kind = kind, parent = parent, name = name, shown = true, w = 0, h = 0, pts = {},
        level = 0, alpha = 1, regions = {}, kids = {}, hooks = {}, scripts = {}, events = {}, mouse = true,
        attrs = {} }, Obj)
    ALL[#ALL + 1] = o
    if parent and parent.kids and kind ~= "Texture" and kind ~= "FontString" then parent.kids[#parent.kids + 1] = o end
    if name then _G[name] = o end
    return o
end

-- Protection: the button itself and every ancestor of it are protected; every frame a protected frame is anchored to
-- is RESTRICTED, transitively (the chassis -> the XP bar -> the data bar). Computed on demand from the live anchors.
local function isFrame(o) return o.kind ~= "Texture" and o.kind ~= "FontString" end
local function restrictedSet()
    local set, work = {}, {}
    for _, o in ipairs(ALL) do
        if isFrame(o) and (o.protected or o.protDesc) then set[o] = true; work[#work + 1] = o end
    end
    while #work > 0 do
        local o = table.remove(work)
        for _, pt in ipairs(o.pts) do
            local rel = pt[2]
            if type(rel) == "table" and isFrame(rel) and not set[rel] then set[rel] = true; work[#work + 1] = rel end
        end
    end
    return set
end
local function restricted(o) return restrictedSet()[o] == true end
local function blocked(o, what)
    if IN_COMBAT and restricted(o) then
        BLOCKED[#BLOCKED + 1] = tostring(o.name or o.kind) .. ":" .. what
        return true
    end
    return false
end

function M:GetObjectType() return self.kind end
function M:GetName() return self.name end
function M:SetSize(w, h) if blocked(self, "SetSize") then return end self.w, self.h = w, h end
function M:SetWidth(w) if blocked(self, "SetWidth") then return end self.w = w end
function M:SetHeight(h) if blocked(self, "SetHeight") then return end self.h = h end
function M:GetWidth() return self.w end
function M:GetHeight() return self.h end
function M:SetPoint(point, rel, relPoint, x, y)
    if blocked(self, "SetPoint") then return end
    self.pts[#self.pts + 1] = { point, rel, relPoint or point, x or 0, y or 0 }
end
function M:ClearAllPoints() if blocked(self, "ClearAllPoints") then return end self.pts = {} end
function M:GetPoint(i) local p = self.pts[i or 1]; if p then return p[1], p[2], p[3], p[4], p[5] end end
function M:SetAllPoints(rel) self.pts = {}; self.allPoints = rel or self.parent end
function M:SetParent(p) if blocked(self, "SetParent") then return end self.parent = p end
function M:GetParent() return self.parent end
function M:Show() if blocked(self, "Show") then return end self.shown = true end
function M:Hide() if blocked(self, "Hide") then return end self.shown = false end
function M:SetShown(v) if blocked(self, "SetShown") then return end self.shown = v and true or false end
function M:IsShown() return self.shown end
function M:IsForbidden() return false end
function M:IsVisible() return self.shown end
function M:HookScript(which, fn) self.hooks[which] = self.hooks[which] or {}; table.insert(self.hooks[which], fn) end
function M:SetScript(which, fn)
    if which == "OnClick" then SETSCRIPT_ONCLICK = SETSCRIPT_ONCLICK + 1 end
    self.scripts[which] = fn
end
function M:HasScript() return true end
function M:RegisterEvent(e) self.events[e] = true end
function M:UnregisterEvent(e) self.events[e] = nil end
function M:RegisterForClicks(...) self.clicks = { ... } end
function M:RegisterForDrag(...) self.drags = { ... } end
function M:EnableMouse(v) self.mouse = v end
function M:IsMouseEnabled() return self.mouse end
function M:SetFrameLevel(l) self.level = l end
function M:GetFrameLevel() return self.level end
function M:SetFrameStrata(s) self.strata = s end
function M:SetAlpha(a) self.alpha = a end
function M:GetAlpha() return self.alpha end
function M:GetID() return self.id or 0 end
function M:GetChildren() return unpack(self.kids) end
function M:GetRegions() return unpack(self.regions) end
function M:CreateTexture(_, layer, _, sub)
    local t = newObj("Texture", self)
    t.layer, t.sublevel = layer, sub
    self.regions[#self.regions + 1] = t
    return t
end
function M:CreateFontString()
    local t = newObj("FontString", self)
    self.regions[#self.regions + 1] = t
    return t
end
function M:SetText(s) self.text = s end
function M:SetTexture(p) self.tex = p end
function M:GetTexture() if NO_ART then return nil end return self.tex end   -- NO_ART: a texture that reads back nil (missing file)
function M:SetAtlas(a) self.atlas = a end
function M:SetColorTexture() end
function M:SetVertexColor(r, g, b, a) self.vertex = { r, g, b, a } end
function M:SetBlendMode() end
function M:SetTexCoord(l, r, t, b) self.texcoord = { l, r, t, b } end
function M:SetDesaturated(v) self.desat = v end

-- Secure template attributes: a protected button refuses SetAttribute in combat.
function M:SetAttribute(k, v)
    if IN_COMBAT and self.protected then BLOCKED[#BLOCKED + 1] = tostring(self.name) .. ":SetAttribute"; return end
    self.attrs[k] = v
end
function M:GetAttribute(k) return self.attrs[k] end
-- Button:Click ignores EnableMouse and the shown state, like the client.
function M:Click(btn) if self.scripts.OnClick then self.scripts.OnClick(self, btn, false) end end

function CreateFrame(kind, name, parent, template)
    local o = newObj(kind, parent, name)
    if template and template:find("SecureActionButtonTemplate", 1, true) then
        o.protected = true
        local p = parent
        while p do p.protDesc = true; p = p.parent end
    end
    return o
end
function CreateColor(r, g, b, a) return { r, g, b, a } end
function M:SetGradient() end
function hooksecurefunc(a, b, c)
    local tbl, name, fn = a, b, c
    if type(a) == "string" then tbl, name, fn = _G, a, b end
    local orig = tbl[name]
    if type(orig) ~= "function" then error("hooksecurefunc(): " .. tostring(name) .. " is not a function") end
    tbl[name] = function(...) local r = { orig(...) }; fn(...); return unpack(r) end
end
function InCombatLockdown() return IN_COMBAT end
function GetTime() return 100 end

UIParent = newObj("Frame", nil, "UIParent")
GameTooltip = newObj("Frame", nil, "GameTooltip")
function GameTooltip:SetOwner(o) self.owner = o end
function GameTooltip:GetOwner() return self.owner end
TIP_LINES = {}
function GameTooltip:SetText() TIP_LINES = {} end
function GameTooltip:AddLine(text) TIP_LINES[#TIP_LINES + 1] = text end
function GameTooltip:AppendText() end
function GameTooltip:SetInventoryItem() return false end

-- Container-opening Blizzard Lua: a call that reaches these came from OUR code.
local function toggle(name) return function(...) TOGGLES[#TOGGLES + 1] = name end end
ToggleBackpack, ToggleBag, ToggleAllBags, OpenBag, CloseBag, OpenAllBags, CloseAllBags =
    toggle("ToggleBackpack"), toggle("ToggleBag"), toggle("ToggleAllBags"), toggle("OpenBag"), toggle("CloseBag"),
    toggle("OpenAllBags"), toggle("CloseAllBags")
-- The C functions the drop and drag paths use.
function PutItemInBag(inv) PUTS[#PUTS + 1] = "PutItemInBag:" .. tostring(inv) end
function PutItemInBackpack() PUTS[#PUTS + 1] = "PutItemInBackpack" end
function PutKeyInKeyRing() PUTS[#PUTS + 1] = "PutKeyInKeyRing" end
function PickupBagFromSlot(inv) PUTS[#PUTS + 1] = "PickupBagFromSlot:" .. tostring(inv) end
function CursorHasItem() return CURSOR ~= nil end
function GetCursorInfo() if CURSOR then return "item", CURSOR end end
function IsModifiedClick(which) if MODIFIER then return which == nil or which == MODIFIER end return false end
function GetInventoryItemTexture(_, inv) if EQUIPPED[inv] then return "bagtex" .. inv end end
function IsInventoryItemLocked(inv) return LOCKED[inv] == true end
KEYRING_CONTAINER = -2
-- Bag families: BAGFAMILY[bagID] = the second return of GetContainerNumFreeSlots (nil = the client gives none);
-- ITEMID[inv] / ITEMFAMILY[itemID] feed GetInventoryItemID and GetItemFamily. FAMILY_THROWS makes every family API raise.
BAGFAMILY, ITEMID, ITEMFAMILY, FAMILY_THROWS, FAMILY_SECRET = {}, {}, {}, false, false
C_Container = { ContainerIDToInventoryID = function(id) return 19 + id end }   -- bag N -> inventory slot 19 + N (stock GetID)
-- Opt-in (h_family installs it): the free-count tests rely on the client NOT having it, and a family test needs it.
function h_installFreeSlots()
    C_Container.GetContainerNumFreeSlots = function(bag)
        if FAMILY_THROWS then error("GetContainerNumFreeSlots exploded") end
        if bag == 0 then return 7, 0 end
        return 5, BAGFAMILY[bag]
    end
end
C_Item = { GetItemFamily = function(id)
    if FAMILY_THROWS then error("GetItemFamily exploded") end
    return ITEMFAMILY[id]
end }
function GetInventoryItemID(_, inv) return ITEMID[inv] end
-- The combined bags CVar (Blizzard's own VARIABLES_LOADED handler reads exactly this): true = one combined window.
CVAR_BOOL = { combinedBags = true }
function GetCVarBool(name) return CVAR_BOOL[name] end
-- The Blizzard atlas lookup the backpack used to paint from: any call is recorded, so a test can prove it is gone.
ATLAS_CALLS = {}
C_Texture = { GetAtlasInfo = function(name)
    ATLAS_CALLS[#ATLAS_CALLS + 1] = name
    return { leftTexCoord = 0.25, rightTexCoord = 0.5, topTexCoord = 0.25, bottomTexCoord = 0.5 }
end }
C_ActionBar = { ShouldShowKeyring = function() return KEYRING_ON end }
Enum = { BagIndex = { Bag_1 = 1, Bag_2 = 2, Bag_3 = 3, Bag_4 = 4, ReagentBag = 5, Keyring = -2 },
    ItemClass = { Container = 1, Quiver = 11 } }
EQUIPPED, LOCKED = { [20] = true, [21] = true, [22] = true, [23] = true, [24] = true }, {}

INSPECT = {}
FS = {
    Layout = { Scale = function() return SCALE end, OnRescale = function(fn) RESCALE[#RESCALE + 1] = fn end,
        deck = { w = 572, h = 38, rightMargin = 92 } },
    PanelSkins = { RequireExport = function() return true end },
    IsSecret = function(v) return SECRET_FN ~= nil and SECRET_FN(v) == true end,   -- SECRET_FN: set by a test to mark values secret
    LogDegradeOnce = function(key, msg) LOGS[#LOGS + 1] = key .. ": " .. msg end,
    Theme = { SLICE_CUT_MARGIN = 6, SLICE_CUT2_FILL_TEXTURE = "cut2_fill", SLICE_CUT2_OUTLINE_TEXTURE = "cut2_outline",
        SLICE_GLOW_TEXTURE = "glow", SLICE_GLOW_MARGIN = 10, SLICE_GLOW_PAD = 4,
        COLOR_POWER = { 0.133, 0.878, 1, 1 }, COLOR_HEALTH = { 1, 0.18, 0.592, 1 }, COLOR_HUD_SCRIM = { 0.05, 0.02, 0.1, 0.5 } },
}
-- FS.Config as Config.lua gives it: Get answers the stored value, else the registered default; OnChange callbacks get
-- (new, old, key). h_cfg stores a value and fires them.
CFG, CFG_DEFAULTS, CFG_CHANGE = {}, {}, {}
FS.Config = {
    Get = function(key) if CFG[key] ~= nil then return CFG[key] end return CFG_DEFAULTS[key] end,
    RegisterDefault = function(key, value) CFG_DEFAULTS[key] = value end,
    OnChange = function(key, fn) CFG_CHANGE[key] = CFG_CHANGE[key] or {}; table.insert(CFG_CHANGE[key], fn) end,
}
function h_cfg(key, value)
    local old = FS.Config.Get(key)
    CFG[key] = value
    for _, fn in ipairs(CFG_CHANGE[key] or {}) do fn(value, old, key) end
end
-- Bags.lua's single bag window, as BagBar.lua sees it: a recording stub (the real one is pinned in bags-harness.py).
SOLO_CALLS, SOLO_OPEN = {}, {}
function h_soloStub()
    FS.SpecialBag = {
        Toggle = function(bagID, kind, anchor) SOLO_CALLS[#SOLO_CALLS + 1] = { bagID, kind, anchor and anchor.name }; SOLO_OPEN[bagID] = not SOLO_OPEN[bagID] end,
        IsOpen = function(bagID) return SOLO_OPEN[bagID] == true end,
    }
end
function FS.Theme.AddCut2Texture(frame, path, color, layer, sublevel, inset)
    local t = frame:CreateTexture(nil, layer or "BACKGROUND", nil, sublevel)
    t:SetTexture(path)
    inset = inset or 0
    t:SetPoint("TOPLEFT", frame, "TOPLEFT", inset, -inset)
    t:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -inset, inset)
    if color then t:SetVertexColor(color[1], color[2], color[3], color[4] or 1) end
    return t
end
FS.Theme.AddSliceTexture = function() return newObj("Texture", UIParent) end
FS.Theme.ApplyNineSlice = noop
FS.Theme.ApplyMono = noop

-- Blizzard's stock bag buttons: their OnClick is Blizzard code and never reaches our global stubs.
local STOCK_IDS = { CharacterBag0Slot = 20, CharacterBag1Slot = 21, CharacterBag2Slot = 22, CharacterBag3Slot = 23,
    CharacterReagentBag0Slot = 24, MainMenuBarBackpackButton = 0, KeyRingButton = 0 }
function h_addStock(name)
    local b = newObj("Button", UIParent, name)
    b.id = STOCK_IDS[name]
    b.scripts.OnClick = function(_, btn)
        STOCKCLICKS[name] = (STOCKCLICKS[name] or 0) + 1
        STOCKCLICKS[name .. "#button"] = btn
    end
end
-- The XP bar is built at PLAYER_LOGIN in the game, anchored flush on the data bar (XPBar.lua Build). Stubs, see the header.
function h_makeXP()
    FS.dataBar = newObj("Frame", UIParent, "ForeverSTUwaveDataBar")
    FS.dataBar:SetPoint("BOTTOM", UIParent, "BOTTOM", 0, 0)
    local xp = newObj("Frame", UIParent, "ForeverSTUwaveXPBar")
    xp:SetPoint("BOTTOM", FS.dataBar, "TOP", 0, 0)
end
function h_setup(missing, lateXP)
    for name in pairs(STOCK_IDS) do
        if name ~= missing then h_addStock(name) end
    end
    if not lateXP then h_makeXP() end
    assert(loadstring(DECK_SRC, "@Deck.lua"))("forever-stuwave", FS)
end
function h_load()
    assert(loadstring(BAGBAR_SRC, "@BagBar.lua"))("forever-stuwave", FS)
end
function h_fire(event, ...)
    for _, f in ipairs(ALL) do
        if f.events[event] and f.scripts.OnEvent then f.scripts.OnEvent(f, event, ...) end
    end
end
function h_rescale(s) SCALE = s; for _, fn in ipairs(RESCALE) do fn() end end
function h_logs() return table.concat(LOGS, "\n") end
function h_blocked() return table.concat(BLOCKED, ",") end
function h_toggles() return table.concat(TOGGLES, ",") end
function h_puts() return table.concat(PUTS, ",") end
function h_reset() BLOCKED, TOGGLES, PUTS, STOCKCLICKS, SOLO_CALLS = {}, {}, {}, {}, {}; BLOCKED_N = 0 end
function h_stockClicks(name) return STOCKCLICKS[name] or 0, STOCKCLICKS[name .. "#button"] end

local function slot(key) return _G["ForeverSTUwaveBagSlot_" .. key] end
-- The template's click handler as it treats a KEY press or an addon :Click() (not an engine mouse press, which 12.1 forces
-- to mouse UP whatever useOnKeyDown says): with useOnKeyDown nil and the CVar on, the action fires on key DOWN, so the up
-- event does nothing; the click type calls delegate:Click(button). Kept as the conservative model: the attribute must be set.
function h_click(key, btn)
    local b = slot(key)
    if b.scripts.OnClick then b.scripts.OnClick(b, btn, false); return "addon-script" end
    if not b.protected then return "none" end
    if b.attrs.useOnKeyDown == nil then return "key-down-only" end
    -- The engine's attribute lookup: type<button suffix> before type; the empty string is the noop that excludes an action.
    local suffix = btn == "RightButton" and "2" or (btn == "LeftButton" and "1" or "")
    local action = b.attrs["type" .. suffix]
    if action == nil then action = b.attrs.type end
    local result = "no-action"
    if action == "" then result = "noop"
    elseif action == "click" and b.attrs.clickbutton then b.attrs.clickbutton:Click(btn); result = "secure" end
    -- PostClick runs after the secure action whatever it was (an insecure hook, so it only ever sees the outcome).
    for _, fn in ipairs(b.hooks.PostClick or {}) do fn(b, btn, false) end
    return result
end
function h_modifier(m) MODIFIER = m end
function h_script(key, which, ...) local b = slot(key); local fn = b.scripts[which]; if fn then fn(b, ...) end return fn ~= nil end
function h_cursor(v) CURSOR = v; h_fire("CURSOR_CHANGED") end
function h_keyring(v) KEYRING_ON = v end
-- Family helpers: bag N's family from the free-slot call (nil = none given), or from the bag item (inv 19 + N, item 900 + N).
function h_family(bag, mask) h_installFreeSlots(); BAGFAMILY[bag] = mask end
function h_itemFamily(bag, mask) ITEMID[19 + bag] = 900 + bag; ITEMFAMILY[900 + bag] = mask end
function h_combined(v) CVAR_BOOL.combinedBags = v end
function h_tooltip(key) h_script(key, "OnEnter"); return TIP_LINES end
function h_lock(inv, v) LOCKED[inv] = v end
function h_equip(inv, v) EQUIPPED[inv] = v end

function h_slots()
    local out = {}
    for i, s in ipairs(FS.BagBar.slots) do
        local b = s.button
        local p = b.pts[1]
        out[i] = { key = s.key, active = s.active, shown = b.shown, w = b.w, x = p and p[4] or -1, npts = #b.pts,
            protected = b.protected == true, type = b.attrs.type, click = b.attrs.clickbutton and b.attrs.clickbutton.name,
            onKeyDown = b.attrs.useOnKeyDown, hasKeyDown = b.attrs.useOnKeyDown ~= nil,
            clicks = b.clicks and table.concat(b.clicks, ",") or "", drags = b.drags and table.concat(b.drags, ",") or "",
            iconAlpha = s.icon.alpha, locked = s.locked, glowShown = s.glow.shown,
            type2 = b.attrs.type2, family = s.family, special = s.special, soloClick = s.soloClick, open = s.open }
    end
    return out
end
function h_stock(name) local b = _G[name]; return { alpha = b.alpha, mouse = b.mouse } end
function h_deck()
    local c, b = FS.Deck.frame, FS.Deck.bagSlot
    local p = c.pts[1]
    return { cw = c.w, bw = b.w, chassisProtected = c.protDesc == true, hostProtected = b.protDesc == true,
        anchorRel = p and p[2] and p[2].name or "none", npts = #c.pts }
end
-- Is the named frame restricted right now (protected, an ancestor of a protected frame, or an anchor target of one)?
function h_restricted(name) return restricted(_G[name]) end
-- Attempt the four geometry/visibility ops on a frame; the BLOCKED log says which the client refused.
function h_poke(name)
    local f = _G[name]
    f:SetSize(1, 1); f:Show(); f:Hide(); f:SetPoint("CENTER", UIParent, "CENTER", 0, 0)
end
function h_bar() return { w = FS.BagBar.bar.w, h = FS.BagBar.bar.h } end
-- C_Timer is opt-in (World(timers=True)): callbacks queue until h_flushTimers, so a test can change the world (combat
-- on or off, the XP bar appearing) between a C_Timer.After call and its callback, as a real frame boundary does.
TIMERS = {}
function h_timers() C_Timer = { After = function(_, fn) TIMERS[#TIMERS + 1] = fn end } end
function h_flushTimers()
    local q = TIMERS
    TIMERS = {}
    for _, fn in ipairs(q) do fn() end
    return #q
end
"""

FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def near(a: float, b: float, eps: float = EPS) -> bool:
    return abs(a - b) <= eps


def py(v):
    """A Lua table (or scalar) as plain Python."""
    if hasattr(v, "items"):
        d = {k: py(x) for k, x in v.items()}
        if d and all(isinstance(k, int) for k in d):
            return [d[k] for k in sorted(d)]
        return d
    return v


def epic_ring_table() -> str:
    """Theme.COLOR_EPIC_RING exactly as Theme.lua writes it (the Epic edge colour, shared with Bags.lua): read, never retyped."""
    m = re.search(r"Theme\.COLOR_EPIC_RING\s*=\s*(\{[^}]*\})", THEME_LUA.read_text(encoding="utf-8"))
    if not m:
        sys.exit("Theme.lua: COLOR_EPIC_RING not found")
    return m.group(1)


class World:
    def __init__(self, scale: float = 1.0, missing: str | None = None, combat_at_load: bool = False,
                 late_xp: bool = False, login_in_combat: bool = False, xp_after_login: bool = False,
                 timers: bool = False, no_art: bool = False):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MOCK)
        self.lua.execute(f"FS.Theme.COLOR_EPIC_RING = {epic_ring_table()}")
        g = self.lua.globals()
        g.DECK_SRC = DECK_LUA.read_text(encoding="utf-8")
        g.BAGBAR_SRC = BAGBAR_LUA.read_text(encoding="utf-8")
        g.SCALE = scale
        g.NO_ART = no_art
        self.g = g
        # xp_after_login: the XP bar does not exist at PLAYER_LOGIN either, so Deck schedules its C_Timer retry (needs
        # timers=True); the test builds the XP bar itself (h_makeXP) before flushing the timers.
        # The game's order: Deck.lua and BagBar.lua load (the bag buttons exist, so the chassis is already protected),
        # then PLAYER_LOGIN fires and Deck seats the chassis on the XP bar. late_xp: the XP bar is built at login, so
        # the file-scope seat parks the chassis at the screen bottom first.
        if timers:
            g.h_timers()
        g.h_setup(missing, late_xp or xp_after_login)
        g.IN_COMBAT = combat_at_load
        g.h_load()
        if late_xp and not xp_after_login:
            g.h_makeXP()
        g.IN_COMBAT = combat_at_load or login_in_combat
        g.h_fire("PLAYER_LOGIN")

    def call(self, fn: str, *args):
        return getattr(self.g, fn)(*args)

    def slots(self) -> dict[str, dict]:
        out = {s["key"]: s for s in py(self.g.h_slots())}
        for v in out.values():          # a Lua nil is a missing key: name the optional ones so a test can compare to None
            for k in ("family", "special", "soloClick", "type2", "open", "locked"):
                v.setdefault(k, None)
        return out

    def combat(self, on: bool) -> None:
        self.g.IN_COMBAT = on

    def regen(self) -> None:
        self.g.IN_COMBAT = False
        self.g.h_fire("PLAYER_REGEN_ENABLED")

    def blocked(self) -> str:
        return self.g.h_blocked()

    def toggles(self) -> str:
        return self.g.h_toggles()

    def logs(self) -> str:
        return self.g.h_logs()


def stock_clicks(w: World, key: str) -> tuple[int, str | None]:
    n, btn = w.call("h_stockClicks", STOCK[key])
    return n, btn


def check_build() -> None:
    w = World()
    s = w.slots()
    check("build.seven_slots", list(s) == KEYS, f"{list(s)}")
    check("build.every_slot_is_a_secure_button", all(v["protected"] for v in s.values()),
          f"{[k for k, v in s.items() if not v['protected']]}")
    check("build.type_is_click_on_every_slot", all(v.get("type") == "click" for v in s.values()),
          f"{[(k, v.get('type')) for k, v in s.items()]}")
    check("build.clickbutton_is_the_stock_button", all(v.get("click") == STOCK[k] for k, v in s.items()),
          f"{[(k, v.get('click')) for k, v in s.items() if v.get('click') != STOCK[k]]}")
    check("build.click_lands_on_mouse_up", all(v["hasKeyDown"] and v.get("onKeyDown") is False for v in s.values()),
          f"{[(k, v.get('onKeyDown')) for k, v in s.items()]}")
    check("build.registers_only_the_up_click", all(v["clicks"] == "AnyUp" for v in s.values()), f"{[v['clicks'] for v in s.values()]}")
    check("build.drag_is_registered", all(v["drags"] == "LeftButton" for v in s.values()))
    check("build.no_addon_onclick_script_replaces_the_secure_one", w.g.SETSCRIPT_ONCLICK == 0, f"{w.g.SETSCRIPT_ONCLICK} SetScript(OnClick)")
    check("build.all_slots_active_and_seated", all(v["active"] and v["shown"] and v["npts"] == 1 for v in s.values()))
    xs = [v["x"] for v in s.values()]
    check("build.slots_are_chained_left_to_right", xs == sorted(xs) and len(set(xs)) == 7, f"{xs}")
    check("build.no_toggle_while_building", w.toggles() == "", w.toggles())
    check("build.no_blocked_op_while_building", w.blocked() == "", w.blocked())
    check("build.no_degrade_logs", w.logs() == "", w.logs())


def check_clicks() -> None:
    for label, modifier, button in (("plain_left", None, "LeftButton"), ("plain_right", None, "RightButton"),
                                    ("shift_left", "OPENALLBAGS", "LeftButton")):
        w = World()
        w.call("h_modifier", modifier)
        for key in KEYS:
            result = w.call("h_click", key, button)
            n, got = stock_clicks(w, key)
            check(f"click.{label}.{key}_reaches_the_stock_onclick_once_with_the_same_button",
                  result == "secure" and n == 1 and got == button, f"{result} {n} {got}")
        check(f"click.{label}.no_container_opening_global_is_called_from_addon_code", w.toggles() == "", w.toggles())
    w = World()
    # Stock buttons stay dimmed and are still clicked through (Click ignores EnableMouse).
    dims = [w.call("h_stock", name) for name in STOCK.values()]
    dims = [py(d) for d in dims]
    check("click.stock_buttons_are_dimmed_alpha_0_mouse_off", all(d["alpha"] == 0 and d["mouse"] is False for d in dims), f"{dims}")
    w.call("h_click", "bag1", "LeftButton")
    check("click.a_dimmed_mouse_off_stock_button_still_gets_the_click", stock_clicks(w, "bag1")[0] == 1)
    # The same click through our own handler would have gone to the global: prove the stub catches it.
    w.call("h_reset")
    w.g.ToggleBag(1)
    check("click.harness_stub_records_a_direct_toggle", w.toggles() == "ToggleBag")


def check_missing_stock() -> None:
    for key in KEYS:
        w = World(missing=STOCK[key])
        s = w.slots()
        v = s[key]
        check(f"missing.{key}_is_hidden_and_inactive", not v["active"] and not v["shown"], f"{v}")
        check(f"missing.{key}_has_no_click_attributes", v.get("type") is None and v.get("click") is None, f"{v}")
        result = w.call("h_click", key, "LeftButton")
        check(f"missing.{key}_click_does_nothing_and_never_falls_back_to_toggle", w.toggles() == "" and result != "secure", f"{result} {w.toggles()}")
        others = [k for k in KEYS if k != key]
        check(f"missing.{key}_leaves_the_other_slots_working", all(s[k]["active"] and s[k].get("click") == STOCK[k] for k in others))
        logged = w.logs().count("\n") + 1 if w.logs() else 0
        check(f"missing.{key}_logs_exactly_once", logged == 1, f"{logged}: {w.logs()}")
        w.g.h_fire("PLAYER_ENTERING_WORLD")
        w.g.h_fire("BAG_CONTAINER_UPDATE")
        logged = w.logs().count("\n") + 1 if w.logs() else 0
        check(f"missing.{key}_still_logs_once_after_more_refreshes", logged == 1, f"{logged}")
        check(f"missing.{key}_no_blocked_op", w.blocked() == "", w.blocked())
        # The stock button shows up later (a late-loading Blizzard addon): the next refresh binds and shows the slot.
        w.call("h_addStock", STOCK[key])
        w.g.h_fire("PLAYER_ENTERING_WORLD")
        v = w.slots()[key]
        check(f"missing.{key}_binds_once_its_stock_button_exists",
              v["active"] and v["shown"] and v.get("click") == STOCK[key] and v.get("type") == "click" and v.get("onKeyDown") is False, f"{v}")


def check_drop_and_drag() -> None:
    w = World()
    w.call("h_cursor", 4242)
    expect = {"backpack": "PutItemInBackpack", "keyring": "PutKeyInKeyRing", "bag1": "PutItemInBag:20",
              "bag2": "PutItemInBag:21", "bag3": "PutItemInBag:22", "bag4": "PutItemInBag:23", "reagent": "PutItemInBag:24"}
    for key, call in expect.items():
        w.call("h_reset")
        w.call("h_script", key, "OnReceiveDrag")
        check(f"drop.{key}_puts_the_cursor_item_through_the_c_function", w.g.h_puts() == call, f"{w.g.h_puts()} want {call}")
        check(f"drop.{key}_calls_no_toggle", w.toggles() == "", w.toggles())
    w.call("h_cursor", None)
    w.call("h_reset")
    for key in KEYS:
        w.call("h_script", key, "OnReceiveDrag")
    check("drop.empty_cursor_puts_nothing", w.g.h_puts() == "", w.g.h_puts())
    for key in KEYS:
        w.call("h_reset")
        w.call("h_script", key, "OnDragStart")
        want = f"PickupBagFromSlot:{ {'bag1': 20, 'bag2': 21, 'bag3': 22, 'bag4': 23, 'reagent': 24}[key] }" if key not in ("backpack", "keyring") else ""
        check(f"drag.{key}_pickup", w.g.h_puts() == want, f"{w.g.h_puts()} want {want}")


def check_combat() -> None:
    # Visual state keeps working in combat on the secure buttons.
    w = World()
    w.combat(True)
    w.call("h_lock", 20, True)
    w.g.h_fire("ITEM_LOCK_CHANGED")
    w.call("h_script", "bag2", "OnEnter")
    w.call("h_cursor", None)
    s = w.slots()
    check("combat.lock_state_still_paints_on_the_icon", s["bag1"]["locked"] is True and s["bag1"]["iconAlpha"] == 0.5, f"{s['bag1']}")
    check("combat.hover_still_paints_the_glow", s["bag2"]["glowShown"] is True)
    check("combat.visual_updates_touch_no_protected_frame", w.blocked() == "", w.blocked())

    # A layout, availability or rescale change in combat is deferred, not attempted.
    w = World()
    before = w.slots()
    bar_before = py(w.call("h_bar"))
    deck_before = py(w.call("h_deck"))
    w.combat(True)
    w.call("h_keyring", False)
    w.g.h_fire("BAG_CONTAINER_UPDATE")
    w.call("h_equip", 23, False)
    w.g.h_fire("PLAYER_EQUIPMENT_CHANGED")
    w.g.h_fire("BAG_UPDATE_DELAYED")
    w.call("h_rescale", 0.64)
    check("combat.no_protected_frame_is_touched_by_availability_or_rescale", w.blocked() == "", w.blocked())
    after = w.slots()
    held = all(near(after[k]["w"], before[k]["w"]) and near(after[k]["x"], before[k]["x"]) and after[k]["shown"] == before[k]["shown"] for k in KEYS)
    check("combat.seated_geometry_and_shown_state_hold_until_regen", held)
    check("combat.the_bar_frame_holds", py(w.call("h_bar")) == bar_before)
    d = py(w.call("h_deck"))
    check("combat.the_deck_chassis_is_protected_by_its_bag_buttons", d["chassisProtected"] and d["hostProtected"], f"{d}")
    check("combat.the_deck_chassis_holds_in_a_combat_rescale", near(d["cw"], deck_before["cw"]) and near(d["bw"], deck_before["bw"]),
          f"{d} vs {deck_before}")
    w.regen()
    after = w.slots()
    check("combat.regen_applies_the_hidden_keyring", after["keyring"]["shown"] is False and after["keyring"]["active"] is False)
    check("combat.regen_applies_the_new_scale", all(near(after[k]["w"], 26 * 0.64) for k in KEYS if after[k]["active"]),
          f"{[(k, after[k]['w']) for k in KEYS]}")
    d = py(w.call("h_deck"))
    check("combat.regen_applies_the_deck_rescale", near(d["cw"], deck_before["cw"] * 0.64), f"{d['cw']} vs {deck_before['cw'] * 0.64}")
    check("combat.regen_touches_nothing_blocked", w.blocked() == "", w.blocked())
    xs = [after[k]["x"] for k in KEYS if after[k]["active"]]
    check("combat.regen_reseats_the_remaining_slots_chained", xs == sorted(xs) and len(set(xs)) == len(xs) and near(xs[0], 0), f"{xs}")

    # Built in combat: no SetAttribute attempted, the attributes land after regen.
    w = World(combat_at_load=True)
    s = w.slots()
    check("combat_load.no_blocked_op", w.blocked() == "", w.blocked())
    check("combat_load.attributes_wait_for_regen", all(v.get("type") is None for v in s.values()), f"{[(k, v.get('type')) for k, v in s.items()]}")
    w.regen()
    s = w.slots()
    check("combat_load.regen_binds_every_slot",
          all(v.get("type") == "click" and v.get("click") == STOCK[k] and v.get("onKeyDown") is False for k, v in s.items()), f"{s}")
    check("combat_load.regen_shows_and_seats_the_slots", all(v["active"] and v["shown"] and v["npts"] == 1 for v in s.values()))
    check("combat_load.regen_blocks_nothing", w.blocked() == "", w.blocked())


def check_chain() -> None:
    """The restriction chain the deck puts on the bars below it: slot buttons -> bar, bagSlot, chassis -> XP bar -> data bar."""
    w = World()
    d = py(w.call("h_deck"))
    check("chain.the_chassis_is_anchored_to_the_xp_bar", d["anchorRel"] == "ForeverSTUwaveXPBar" and d["npts"] == 1, f"{d}")
    for name in ("ForeverSTUwaveDeck", "ForeverSTUwaveXPBar", "ForeverSTUwaveDataBar"):
        check(f"chain.{name}_is_restricted", w.call("h_restricted", name) is True)
    check("chain.an_unrelated_stock_button_is_not_restricted", w.call("h_restricted", "CharacterBag0Slot") is False)
    # Out of combat every op on the restricted frames is legal; in combat each is blocked.
    w.call("h_poke", "ForeverSTUwaveXPBar")
    check("chain.out_of_combat_the_xp_bar_can_be_resized_shown_hidden_and_moved", w.blocked() == "", w.blocked())
    w.combat(True)
    for name in ("ForeverSTUwaveXPBar", "ForeverSTUwaveDataBar"):
        w.call("h_reset")
        w.call("h_poke", name)
        got = sorted(w.blocked().split(","))
        want = sorted(f"{name}:{op}" for op in ("SetSize", "Show", "Hide", "SetPoint"))
        check(f"chain.in_combat_{name}_refuses_size_show_hide_and_anchor", got == want, f"{got}")


def check_login_in_combat() -> None:
    """PLAYER_LOGIN in combat: the deck seat waits for regen instead of touching the protected chassis."""
    w = World(late_xp=True, login_in_combat=True)
    d = py(w.call("h_deck"))
    check("login_in_combat.no_blocked_op", w.blocked() == "", w.blocked())
    check("login_in_combat.the_chassis_is_still_parked_not_seated_on_the_xp_bar", d["anchorRel"] == "UIParent", f"{d}")
    w.regen()
    d = py(w.call("h_deck"))
    check("login_in_combat.regen_seats_the_chassis_on_the_xp_bar", d["anchorRel"] == "ForeverSTUwaveXPBar" and d["npts"] == 1, f"{d}")
    check("login_in_combat.regen_blocks_nothing", w.blocked() == "", w.blocked())
    check("login_in_combat.no_degrade_log", w.logs() == "", w.logs())
    # The ordinary login (out of combat) seats at once.
    w = World(late_xp=True)
    d = py(w.call("h_deck"))
    check("login.out_of_combat_the_chassis_is_seated_on_the_xp_bar_at_login", d["anchorRel"] == "ForeverSTUwaveXPBar" and d["npts"] == 1, f"{d}")


def check_entering_world_in_combat() -> None:
    """PLAYER_ENTERING_WORLD fires on a zone change and can land in combat: it must do only the non-restricted half."""
    w = World()
    before = w.slots()
    bar_before = py(w.call("h_bar"))
    w.combat(True)
    w.call("h_keyring", False)   # an availability change waiting to be applied
    w.g.h_fire("PLAYER_ENTERING_WORLD")
    check("entering_world_in_combat.touches_no_protected_frame", w.blocked() == "", w.blocked())
    after = w.slots()
    held = all(near(after[k]["w"], before[k]["w"]) and near(after[k]["x"], before[k]["x"]) and after[k]["shown"] == before[k]["shown"]
               and after[k]["active"] == before[k]["active"] for k in KEYS)
    check("entering_world_in_combat.the_seated_slots_and_bar_hold", held and py(w.call("h_bar")) == bar_before)
    w.regen()
    check("entering_world_in_combat.regen_applies_the_deferred_availability",
          w.slots()["keyring"]["shown"] is False and w.slots()["keyring"]["active"] is False)
    check("entering_world_in_combat.regen_blocks_nothing", w.blocked() == "", w.blocked())


def check_login_retry_in_combat() -> None:
    """Deck's PLAYER_LOGIN retry (C_Timer.After) runs a frame later: if combat starts in between, it must defer, not seat."""
    w = World(xp_after_login=True, timers=True)
    d = py(w.call("h_deck"))
    check("login_retry.the_chassis_is_parked_until_the_xp_bar_exists", d["anchorRel"] == "UIParent", f"{d}")
    w.call("h_makeXP")   # XPBar.lua builds its frame before the retry fires
    w.combat(True)       # combat starts between the login seat and the retry
    w.call("h_reset")
    w.call("h_flushTimers")
    d = py(w.call("h_deck"))
    check("login_retry.in_combat_the_retry_touches_no_protected_frame", w.blocked() == "", w.blocked())
    check("login_retry.in_combat_the_chassis_stays_parked", d["anchorRel"] == "UIParent" and d["npts"] == 1, f"{d}")
    w.regen()
    d = py(w.call("h_deck"))
    check("login_retry.regen_replays_the_seat_on_the_xp_bar", d["anchorRel"] == "ForeverSTUwaveXPBar" and d["npts"] == 1, f"{d}")
    check("login_retry.regen_blocks_nothing", w.blocked() == "", w.blocked())
    check("login_retry.no_degrade_log", w.logs() == "", w.logs())
    # Out of combat the same retry seats at once.
    w = World(xp_after_login=True, timers=True)
    w.call("h_makeXP")
    w.call("h_flushTimers")
    d = py(w.call("h_deck"))
    check("login_retry.out_of_combat_the_retry_seats_the_chassis", d["anchorRel"] == "ForeverSTUwaveXPBar" and d["npts"] == 1, f"{d}")
    # If the XP bar never appears, the degrade logs exactly once under the key deck_anchor. The login fires a second
    # time and the timers flush again, so the degrade is reached twice and only Deck.lua's per-key latch holds it to one.
    w = World(xp_after_login=True, timers=True)
    w.call("h_flushTimers")
    w.g.h_fire("PLAYER_LOGIN")
    w.call("h_flushTimers")
    anchor_logs = [ln for ln in w.logs().splitlines() if ln.startswith("deck_anchor: ")]
    check("login_retry.no_xp_bar_logs_the_anchor_degrade_exactly_once", len(anchor_logs) == 1, w.logs())


def check_hover_highlight() -> None:
    rec = """
        HL = {}
        FS.BagHighlight = { Set = function(id) HL[#HL + 1] = "set:" .. tostring(id) end,
                            Clear = function() HL[#HL + 1] = "clear" end }
        function h_hl() local t = HL; HL = {}; return table.concat(t, ",") end
    """
    w = World()
    w.lua.execute(rec)
    want = {"backpack": 0, "bag1": 1, "bag2": 2, "bag3": 3, "bag4": 4, "reagent": 5}
    for key, bag in want.items():
        w.call("h_script", key, "OnEnter")
        check(f"hover.{key}_lights_bag_{bag}", w.g.h_hl() == f"set:{bag}", w.g.h_hl())
        w.call("h_script", key, "OnLeave")
        check(f"hover.{key}_leave_clears", w.g.h_hl() == "clear", w.g.h_hl())
    w.call("h_script", "keyring", "OnEnter")
    check("hover.keyring_has_no_container_id_and_lights_nothing", w.g.h_hl() == "clear", w.g.h_hl())

    # hiding the slot under the mouse clears; hiding one that is not hovered does not clear someone else's
    w.call("h_script", "bag2", "OnEnter")
    w.g.h_hl()
    w.call("h_script", "bag3", "OnHide")
    check("hover.hiding_another_slot_leaves_the_highlight", w.g.h_hl() == "", w.g.h_hl())
    w.call("h_script", "bag2", "OnHide")
    check("hover.hiding_the_hovered_slot_clears", w.g.h_hl() == "clear", w.g.h_hl())

    # combat: the secure buttons are protected. BagHighlight is a recorder here, so this pins that the BAR's handlers
    # make no protected call; the item-button side (our regions only) is pinned in bags-harness.py.
    w = World()
    w.lua.execute(rec)
    w.combat(True)
    w.call("h_script", "bag4", "OnEnter")
    got = w.g.h_hl()
    w.call("h_script", "bag4", "OnLeave")
    check("hover.combat_enter_and_leave_still_drive_the_highlight", got == "set:4" and w.g.h_hl() == "clear", got)
    check("hover.combat_bar_handlers_make_no_protected_calls", w.blocked() == "", w.blocked())

    # Bags.lua absent: hover still paints the slot, nothing throws
    w = World()
    w.lua.execute("FS.BagHighlight = nil")
    ok = w.call("h_script", "bag1", "OnEnter") and w.call("h_script", "bag1", "OnLeave") and w.call("h_script", "bag1", "OnHide")
    check("hover.missing_bag_highlight_api_is_no_error", ok is True and w.slots()["bag1"]["glowShown"] is False)
    check("hover.no_degrade_logs", w.logs() == "", w.logs())


def check_source() -> None:
    """No call to container-opening Blizzard Lua anywhere in BagBar.lua (comments and strings do not count)."""
    pattern = re.compile(r"\b(ToggleBackpack\w*|ToggleBag\w*|ToggleAllBags|OpenBag|CloseBag|OpenAllBags|CloseAllBags|ToggleKeyRing)\s*\(")
    hits = []
    for n, line in enumerate(BAGBAR_LUA.read_text(encoding="utf-8").splitlines(), 1):
        code = re.sub(r'"[^"]*"', '""', line.split("--", 1)[0])
        if pattern.search(code):
            hits.append(f"{n}: {line.strip()}")
    check("source.no_container_opening_call_in_BagBar_lua", not hits, f"{hits}")
    # Stock bag queries that fill a lazy cache on their first call: from our code the cache is built under our taint and
    # every later stock bag check reads it (live 2026-11-18: the combined bags flag, then the bank, then a blocked bag click).
    lazy = re.compile(r"\b(IsBagOpen|IsAnyBagOpen|AreAllBagsOpen|ContainerFrameUtil_\w+|EnumerateValidItems|GetBagSize)\b")
    hits = []
    for n, line in enumerate(BAGBAR_LUA.read_text(encoding="utf-8").splitlines(), 1):
        code = re.sub(r'"[^"]*"', '""', line.split("--", 1)[0])
        if lazy.search(code):
            hits.append(f"{n}: {line.strip()}")
    check("source.no_lazy_cache_stock_bag_query_in_BagBar_lua", not hits, f"{hits}")
    # The right click never runs a stock button from addon code (a :Click() from here would run the stock OnClick tainted).
    hits = []
    for n, line in enumerate(BAGBAR_LUA.read_text(encoding="utf-8").splitlines(), 1):
        code = re.sub(r'"[^"]*"', '""', line.split("--", 1)[0])
        if re.search(r"[:.]Click\s*\(", code):
            hits.append(f"{n}: {line.strip()}")
    check("source.no_addon_side_click_on_a_stock_button_in_BagBar_lua", not hits, f"{hits}")


def check_events() -> None:
    w = World()
    w.call("h_cursor", 1)
    w.call("h_cursor", None)
    for event in ("BAG_UPDATE", "BAG_UPDATE_DELAYED", "BAG_CONTAINER_UPDATE", "PLAYER_EQUIPMENT_CHANGED", "ITEM_LOCK_CHANGED",
                  "CURSOR_CHANGED", "BAG_OPEN", "BAG_CLOSED", "PLAYER_ENTERING_WORLD", "PLAYER_REGEN_ENABLED"):
        w.g.h_fire(event)
    check("events.out_of_combat_refreshes_open_no_toggle_and_block_nothing", w.toggles() == "" and w.blocked() == "", f"{w.toggles()} {w.blocked()}")
    check("events.out_of_combat_rescale_applies_at_once", (lambda: (w.call("h_rescale", 0.64), near(w.slots()["bag1"]["w"], 26 * 0.64))[1])())
    check("events.no_degrade_logs", w.logs() == "", w.logs())


def check_quality_border() -> None:
    w = World()
    w.lua.execute("""
ITEM_QUALITY_COLORS = { [3] = { r = 0, g = 0.5, b = 1 } }
function GetInventoryItemQuality() return 3 end
function h_bag1() for _, x in ipairs(FS.BagBar.slots) do if x.key == "bag1" then return x end end end
""")
    w.g.h_fire("PLAYER_EQUIPMENT_CHANGED")
    v = py(w.lua.eval("h_bag1().edge.vertex"))
    check("quality.a_rare_bag_edge_takes_its_quality_colour_at_0.85", v == [0, 0.5, 1, 0.85], f"{v}")
    w.lua.execute("QC1 = h_bag1().qualityColor")
    w.g.h_fire("PLAYER_EQUIPMENT_CHANGED")
    check("quality.rereading_an_item_allocates_no_new_colour_table", w.lua.eval("h_bag1().qualityColor == QC1"))
    c = py(w.lua.eval("{ ITEM_QUALITY_COLORS[3].r, ITEM_QUALITY_COLORS[3].g, ITEM_QUALITY_COLORS[3].b }"))
    check("quality.refreshing_leaves_the_shared_quality_colour_untouched", c == [0, 0.5, 1], f"{c}")
    w.lua.execute("ITEM_QUALITY_COLORS[3] = { r = 1, g = 0, b = 0 }")
    w.g.h_fire("PLAYER_EQUIPMENT_CHANGED")
    v = py(w.lua.eval("h_bag1().edge.vertex"))
    check("quality.a_changed_quality_colour_is_picked_up", v == [1, 0, 0, 0.85], f"{v}")

    # Epic takes the shared ring colour (Theme.COLOR_EPIC_RING, the colour Bags.lua gives an Epic item slot's ring) at the
    # same 0.85, not Blizzard's Epic; Theme.lua is the one source, so the edge reads the table the Theme holds.
    w.lua.execute("ITEM_QUALITY_COLORS[4] = { r = 0.64, g = 0.21, b = 0.93 }; function GetInventoryItemQuality() return 4 end")
    w.g.h_fire("PLAYER_EQUIPMENT_CHANGED")
    v = py(w.lua.eval("h_bag1().edge.vertex"))
    want = py(w.lua.eval("{ FS.Theme.COLOR_EPIC_RING[1], FS.Theme.COLOR_EPIC_RING[2], FS.Theme.COLOR_EPIC_RING[3], 0.85 }"))
    check("quality.an_epic_bag_edge_takes_the_shared_epic_ring_colour_at_0.85", v == want and v[:3] != [0.64, 0.21, 0.93], f"{v} want {want}")
    w.lua.execute("FS.Theme.COLOR_EPIC_RING[1] = 0.25")
    w.g.h_fire("PLAYER_EQUIPMENT_CHANGED")
    check("quality.the_epic_edge_follows_the_theme_table", py(w.lua.eval("h_bag1().edge.vertex"))[0] == 0.25)
    w.lua.execute("FS.Theme.COLOR_EPIC_RING = nil")
    w.g.h_fire("PLAYER_EQUIPMENT_CHANGED")
    v = py(w.lua.eval("h_bag1().edge.vertex"))
    check("quality.without_the_theme_colour_epic_uses_the_quality_colour", v == [0.64, 0.21, 0.93, 0.85], f"{v}")
    w.lua.execute("ITEM_QUALITY_COLORS[4] = nil")
    w.g.h_fire("PLAYER_EQUIPMENT_CHANGED")
    check("quality.without_either_epic_keeps_the_accent_edge", py(w.lua.eval("h_bag1().edge.vertex"))[3] == 0.75)


def check_free_count_text() -> None:
    w = World()
    w.lua.execute("""
FREE = 7
C_Container.CalculateTotalNumberOfFreeBagSlots = function() return FREE end
function h_backpack() for _, x in ipairs(FS.BagBar.slots) do if x.kind == "backpack" then return x end end end
TEXTS = 0
local count = h_backpack().count
local realSet = count.SetText
count.SetText = function(self, t) TEXTS = TEXTS + 1; return realSet(self, t) end
""")
    w.g.h_fire("BAG_UPDATE")
    check("free.the_count_text_shows_the_free_slots", w.lua.eval("h_backpack().count.text") == "7")
    w.lua.execute("TEXTS = 0")
    for _ in range(10):
        w.g.h_fire("BAG_UPDATE")
    check("free.an_unchanged_free_count_is_not_rewritten", w.lua.eval("TEXTS") == 0, f"{w.lua.eval('TEXTS')}")
    w.lua.execute("FREE = 6; TEXTS = 0")
    w.g.h_fire("BAG_UPDATE")
    check("free.a_changed_free_count_is_rewritten", w.lua.eval("TEXTS") == 1 and w.lua.eval("h_backpack().count.text") == "6")
    w.lua.execute("FREE = nil")
    w.g.h_fire("BAG_UPDATE")
    check("free.an_unreadable_free_count_blanks_the_text", w.lua.eval("h_backpack().count.text") == "")


def check_backpack_icon() -> None:
    """The backpack slot paints the classic backpack item icon like the real bag slots do: same crop, no tint, no atlas."""
    w = World()
    w.lua.execute("function h_bp() for _, x in ipairs(FS.BagBar.slots) do if x.kind == 'backpack' then return x end end end")
    w.lua.execute("function h_bag1() for _, x in ipairs(FS.BagBar.slots) do if x.key == 'bag1' then return x end end end")
    tex = w.lua.eval("h_bp().icon.tex")
    check("backpack.paints_the_classic_backpack_icon", tex == "Interface\\Icons\\INV_Misc_Bag_08", f"{tex}")
    coords = py(w.lua.eval("h_bp().icon.texcoord"))
    bag_coords = py(w.lua.eval("h_bag1().icon.texcoord"))
    check("backpack.icon_is_cropped_like_the_bag_slots", coords == bag_coords == [0.08, 0.92, 0.08, 0.92], f"{coords} vs {bag_coords}")
    check("backpack.icon_is_untinted", w.lua.eval("h_bp().icon.vertex") is None, f"{py(w.lua.eval('h_bp().icon.vertex'))}")
    check("backpack.icon_is_shown_full_colour_and_opaque",
          w.lua.eval("h_bp().icon.shown") is not False and w.lua.eval("h_bp().icon.desat") is False
          and w.lua.eval("h_bp().icon.alpha") == 1,
          f"{w.lua.eval('h_bp().icon.shown')} {w.lua.eval('h_bp().icon.desat')} {w.lua.eval('h_bp().icon.alpha')}")
    check("backpack.no_atlas_is_set_or_looked_up", w.lua.eval("h_bp().icon.atlas") is None and w.lua.eval("#ATLAS_CALLS") == 0,
          f"{w.lua.eval('h_bp().icon.atlas')} {w.lua.eval('#ATLAS_CALLS')}")
    w.g.h_fire("BAG_UPDATE")
    w.g.h_fire("PLAYER_ENTERING_WORLD")
    check("backpack.refreshes_keep_the_icon_untinted_and_never_ask_for_an_atlas",
          w.lua.eval("h_bp().icon.tex") == tex and w.lua.eval("h_bp().icon.vertex") is None
          and py(w.lua.eval("h_bp().icon.texcoord")) == coords
          and w.lua.eval("#ATLAS_CALLS") == 0 and w.lua.eval("h_bp().glyph") is None)
    keyring = py(w.lua.eval("(function() for _, x in ipairs(FS.BagBar.slots) do if x.kind == 'keyring' then return x.icon.vertex end end end)()"))
    check("backpack.other_slots_icons_stay_untinted", keyring is None, f"{keyring}")


def check_backpack_letter_fallback() -> None:
    """When the icon texture reads back nil the backpack falls back to a "B" letter; with the art present it never does."""
    w = World()
    w.lua.execute("function h_bp() for _, x in ipairs(FS.BagBar.slots) do if x.kind == 'backpack' then return x end end end")
    check("backpack.with_art_no_letter_glyph_is_created", w.lua.eval("h_bp().glyph") is None and w.lua.eval("h_bp().glyphOnly") is None)
    w = World(no_art=True)
    w.lua.execute("function h_bp() for _, x in ipairs(FS.BagBar.slots) do if x.kind == 'backpack' then return x end end end")
    w.g.h_fire("BAG_UPDATE")
    check("backpack.missing_art_falls_back_to_a_B_letter",
          w.lua.eval("h_bp().glyphOnly") is True and w.lua.eval("h_bp().glyph.text") == "B", f"{w.lua.eval('h_bp().glyph and h_bp().glyph.text')}")
    check("backpack.missing_art_letter_is_shown", w.lua.eval("h_bp().glyph and h_bp().glyph.shown") is True)


def with_families(fams: dict[int, int | None], item_fams: dict[int, int] | None = None, **kw) -> World:
    """A world whose bags 1-4 report the given families (free-slot second return) and/or bag item families, then one refresh."""
    w = World(**kw)
    w.call("h_soloStub")
    for bag, mask in fams.items():
        w.call("h_family", bag, mask)
    for bag, mask in (item_fams or {}).items():
        w.call("h_itemFamily", bag, mask)
    w.g.h_fire("PLAYER_EQUIPMENT_CHANGED")
    return w


def solo_calls(w: World) -> list:
    return py(w.lua.eval("SOLO_CALLS")) or []


def check_family() -> None:
    """Bag family detection: the free-slot call's second return, else GetItemFamily of the bag item; classic masks only."""
    w = with_families({1: 1, 2: 2, 3: 4, 4: 0})
    s = w.slots()
    got = {k: (s[k]["family"], s[k]["special"]) for k in ("bag1", "bag2", "bag3", "bag4")}
    check("family.free_slot_return_reads_quiver_ammo_pouch_soul_bag_and_a_generic_bag",
          got == {"bag1": (1, "quiver"), "bag2": (2, "ammo"), "bag3": (4, "shard"), "bag4": (0, None)}, f"{got}")
    check("family.no_error_or_log_while_reading", w.logs() == "" and w.blocked() == "", f"{w.logs()} {w.blocked()}")

    w = with_families({}, {1: 4, 3: 1})
    s = w.slots()
    check("family.get_item_family_answers_when_the_free_slot_call_gives_none",
          (s["bag1"]["special"], s["bag3"]["special"], s["bag2"]["special"]) == ("shard", "quiver", None),
          f"{[(k, s[k]['family'], s[k]['special']) for k in ('bag1', 'bag2', 'bag3')]}")

    w = World()
    w.lua.execute("local f = C_Item.GetItemFamily; C_Item = nil; GetItemFamily = f")
    w.call("h_itemFamily", 2, 2)
    w.g.h_fire("PLAYER_EQUIPMENT_CHANGED")
    check("family.the_global_get_item_family_is_the_second_fallback", w.slots()["bag2"]["special"] == "ammo", f"{w.slots()['bag2']}")

    w = with_families({1: 0}, {1: 4})
    check("family.a_nonzero_item_family_counts_when_the_free_slot_call_says_zero", w.slots()["bag1"]["special"] == "shard", f"{w.slots()['bag1']}")
    w = with_families({1: 1}, {1: 4})
    check("family.the_free_slot_answer_wins_when_both_name_a_family", w.slots()["bag1"]["special"] == "quiver", f"{w.slots()['bag1']}")

    w = with_families({1: 8, 2: 32, 3: 1024, 4: 256})
    s = w.slots()
    check("family.trade_bag_and_key_families_are_not_special",
          all(s[k]["special"] is None for k in ("bag1", "bag2", "bag3", "bag4")) and [s[k]["family"] for k in ("bag1", "bag2", "bag3", "bag4")] == [8, 32, 1024, 256],
          f"{[(k, s[k]['family'], s[k]['special']) for k in ('bag1', 'bag2', 'bag3', 'bag4')]}")
    w = with_families({1: 3})
    check("family.a_mask_with_several_bits_takes_the_first_in_quiver_ammo_shard_order", w.slots()["bag1"]["special"] == "quiver")

    w = with_families({1: 4, 2: 4})
    w.lua.execute("BAGFAMILY[5] = 4; BAGFAMILY[0] = 4")
    w.g.h_fire("PLAYER_EQUIPMENT_CHANGED")
    s = w.slots()
    check("family.the_backpack_reagent_bag_and_keyring_are_never_special",
          all(s[k]["special"] is None and not s[k]["soloClick"] for k in ("backpack", "reagent", "keyring")),
          f"{[(k, s[k]['special']) for k in ('backpack', 'reagent', 'keyring')]}")

    w = with_families({1: 4, 2: 1})
    w.call("h_equip", 20, False)
    w.g.h_fire("PLAYER_EQUIPMENT_CHANGED")
    s = w.slots()
    check("family.an_empty_bag_slot_has_no_family", s["bag1"]["family"] is None and s["bag1"]["special"] is None and s["bag2"]["special"] == "quiver", f"{s['bag1']}")

    w = with_families({2: 2})
    w.call("h_family", 2, 0)
    w.g.h_fire("PLAYER_EQUIPMENT_CHANGED")
    check("family.a_swapped_bag_is_read_again", w.slots()["bag2"]["special"] is None and w.slots()["bag2"]["type2"] is None, f"{w.slots()['bag2']}")
    w.call("h_family", 2, 4)
    w.g.h_fire("BAG_UPDATE_DELAYED")
    check("family.the_next_bag_update_picks_up_a_new_family", w.slots()["bag2"]["special"] == "shard" and w.slots()["bag2"]["type2"] == "", f"{w.slots()['bag2']}")

    w = with_families({1: 4})
    w.lua.execute("SECRET_FN = function(v) return v == 4 end")
    w.g.h_fire("PLAYER_EQUIPMENT_CHANGED")
    check("family.a_secret_family_is_never_used", w.slots()["bag1"]["special"] is None and w.slots()["bag1"]["family"] is None, f"{w.slots()['bag1']}")
    w.lua.execute("SECRET_FN = function(v) return true end")
    w.g.h_fire("PLAYER_EQUIPMENT_CHANGED")
    w.g.h_fire("BAG_UPDATE_DELAYED")
    check("family.a_world_of_secrets_reads_no_family_and_throws_nothing", all(v["special"] is None for v in w.slots().values()))

    w = with_families({1: 4})
    w.lua.execute("FAMILY_THROWS = true")
    w.g.h_fire("PLAYER_EQUIPMENT_CHANGED")
    s = w.slots()
    check("family.api_that_throws_reads_as_no_family_and_leaves_the_slot_working",
          s["bag1"]["special"] is None and s["bag1"]["active"] and s["bag1"].get("type") == "click" and w.logs() == "", f"{s['bag1']} {w.logs()}")
    w = World()
    w.lua.execute("C_Container.GetContainerNumFreeSlots = nil; C_Item = nil; GetItemFamily = nil")
    w.g.h_fire("PLAYER_EQUIPMENT_CHANGED")
    check("family.a_client_with_neither_api_reads_no_family", all(v["special"] is None for v in w.slots().values()) and w.logs() == "")


def check_solo_click() -> None:
    """A special bag's right click leaves the secure path and asks Bags.lua for that bag alone; everything else is stock."""
    w = with_families({1: 1, 2: 2, 3: 4})
    s = w.slots()
    check("solo.special_slots_exclude_the_right_click_from_the_secure_path",
          all(s[k]["type2"] == "" and s[k]["soloClick"] is True and s[k]["type"] == "click" for k in ("bag1", "bag2", "bag3")),
          f"{[(k, s[k]['type'], s[k]['type2'], s[k]['soloClick']) for k in ('bag1', 'bag2', 'bag3')]}")
    check("solo.every_other_slot_keeps_the_stock_right_click",
          all(s[k]["type2"] is None and not s[k]["soloClick"] and s[k]["type"] == "click" for k in ("bag4", "backpack", "reagent", "keyring")),
          f"{[(k, s[k]['type2']) for k in ('bag4', 'backpack', 'reagent', 'keyring')]}")
    check("solo.the_bar_registers_no_extra_click_script", w.g.SETSCRIPT_ONCLICK == 0)

    w.call("h_reset")
    result = w.call("h_click", "bag1", "LeftButton")
    n, got = stock_clicks(w, "bag1")
    check("solo.left_click_on_a_special_slot_is_still_the_stock_click", result == "secure" and n == 1 and got == "LeftButton" and solo_calls(w) == [],
          f"{result} {n} {got} {solo_calls(w)}")

    w.call("h_reset")
    result = w.call("h_click", "bag2", "RightButton")
    n, _ = stock_clicks(w, "bag2")
    check("solo.right_click_on_a_special_slot_reaches_no_stock_button", result == "noop" and n == 0, f"{result} {n}")
    check("solo.right_click_asks_for_that_bag_alone_with_its_id_kind_and_slot",
          solo_calls(w) == [[2, "ammo", "ForeverSTUwaveBagSlot_bag2"]], f"{solo_calls(w)}")
    check("solo.no_container_opening_global_is_called_from_addon_code", w.toggles() == "" and w.blocked() == "", f"{w.toggles()} {w.blocked()}")
    w.call("h_click", "bag2", "RightButton")
    check("solo.a_second_right_click_asks_again_so_the_window_can_close", len(solo_calls(w)) == 2)
    check("solo.the_hook_never_clicks_a_stock_button_itself", stock_clicks(w, "bag2")[0] == 0 and stock_clicks(w, "bag1")[0] == 0)

    for key in ("bag4", "reagent", "backpack", "keyring"):
        w.call("h_reset")
        result = w.call("h_click", key, "RightButton")
        n, got = stock_clicks(w, key)
        check(f"solo.right_click_on_{key}_is_the_stock_click", result == "secure" and n == 1 and got == "RightButton" and solo_calls(w) == [], f"{result} {n} {solo_calls(w)}")

    # A modified or cursor-holding right click is the stock's business (it does nothing here, never opens the window).
    w.call("h_reset")
    w.call("h_modifier", "OPENALLBAGS")
    w.call("h_click", "bag3", "RightButton")
    w.call("h_modifier", None)
    check("solo.a_modified_right_click_does_not_open_the_window", solo_calls(w) == [], f"{solo_calls(w)}")
    w.call("h_cursor", 4242)
    w.call("h_click", "bag3", "RightButton")
    w.call("h_cursor", None)
    check("solo.a_right_click_with_an_item_on_the_cursor_does_not_open_the_window", solo_calls(w) == [], f"{solo_calls(w)}")

    # The window is Bags.lua's: without it the click does nothing and breaks nothing.
    w.lua.execute("FS.SpecialBag = nil")
    w.call("h_reset")
    result = w.call("h_click", "bag1", "RightButton")
    check("solo.without_the_window_module_the_right_click_is_a_quiet_noop", result == "noop" and w.toggles() == "" and w.logs() == "", f"{result} {w.logs()}")


def check_solo_modes() -> None:
    """Individual windows, the setting and the CVar events keep the attribute in step; the default is on."""
    w = with_families({1: 1, 2: 2})
    check("solo.the_setting_registers_with_a_default_of_on", w.lua.eval("CFG_DEFAULTS['bagbar.specialRight']") is True)
    w.call("h_combined", False)
    w.g.h_fire("USE_COMBINED_BAGS_CHANGED", False)
    s = w.slots()
    check("solo.individual_windows_leave_the_stock_right_click_alone", s["bag1"]["type2"] is None and not s["bag1"]["soloClick"], f"{s['bag1']}")
    w.call("h_reset")
    result = w.call("h_click", "bag1", "RightButton")
    check("solo.individual_windows_right_click_is_the_stock_click", result == "secure" and stock_clicks(w, "bag1")[0] == 1 and solo_calls(w) == [], f"{result}")
    w.call("h_combined", True)
    w.g.h_fire("CVAR_UPDATE", "combinedBags", "1")
    check("solo.the_cvar_update_event_brings_the_right_click_back", w.slots()["bag1"]["type2"] == "", f"{w.slots()['bag1']}")
    w.call("h_combined", False)
    w.g.h_fire("CVAR_UPDATE", "somethingElse", "0")
    check("solo.an_unrelated_cvar_update_changes_nothing", w.slots()["bag1"]["type2"] == "")
    w.g.h_fire("CVAR_UPDATE", "combinedBags", "0")
    check("solo.the_combined_cvar_update_turns_it_off", w.slots()["bag1"]["type2"] is None)
    w.call("h_combined", True)
    w.g.h_fire("USE_COMBINED_BAGS_CHANGED", True)

    w.call("h_cfg", "bagbar.specialRight", False)
    s = w.slots()
    check("solo.the_setting_off_gives_every_slot_the_stock_right_click", all(v["type2"] is None and not v["soloClick"] for v in s.values()), f"{s['bag1']}")
    w.call("h_cfg", "bagbar.specialRight", True)
    check("solo.the_setting_back_on_restores_the_special_right_click", w.slots()["bag1"]["type2"] == "" and w.slots()["bag2"]["type2"] == "")
    check("solo.changing_the_setting_blocks_nothing", w.blocked() == "", w.blocked())

    w.lua.execute("FS.Config = nil")
    w.g.h_fire("PLAYER_EQUIPMENT_CHANGED")
    check("solo.without_a_config_module_the_default_is_on", w.slots()["bag1"]["type2"] == "")
    w2 = World()
    w2.lua.execute("GetCVarBool = nil")
    w2.call("h_soloStub")
    w2.call("h_family", 1, 1)
    w2.g.h_fire("PLAYER_EQUIPMENT_CHANGED")
    check("solo.a_client_that_cannot_say_counts_as_combined", w2.slots()["bag1"]["type2"] == "")


def check_solo_combat() -> None:
    """The attribute is a protected write: nothing is attempted in combat, the change lands at regen."""
    w = with_families({1: 1, 2: 2})
    w.combat(True)
    w.call("h_family", 1, 0)
    w.call("h_family", 4, 4)
    w.g.h_fire("PLAYER_EQUIPMENT_CHANGED")
    w.g.h_fire("BAG_UPDATE_DELAYED")
    s = w.slots()
    check("solo.combat_changes_no_attribute_and_blocks_nothing", w.blocked() == "" and s["bag1"]["type2"] == "" and s["bag4"]["type2"] is None,
          f"{w.blocked()} {s['bag1']['type2']} {s['bag4']['type2']}")
    check("solo.combat_still_reads_the_new_family", s["bag1"]["special"] is None and s["bag4"]["special"] == "shard", f"{s['bag1']} {s['bag4']}")
    w.call("h_reset")
    w.call("h_click", "bag1", "RightButton")
    check("solo.a_stale_attribute_in_combat_still_opens_nothing_wrong_and_blocks_nothing", w.blocked() == "", w.blocked())
    w.regen()
    s = w.slots()
    check("solo.regen_applies_the_new_right_click_attributes", s["bag1"]["type2"] is None and s["bag4"]["type2"] == "" and s["bag2"]["type2"] == "", f"{s['bag1']['type2']} {s['bag4']['type2']}")
    check("solo.regen_blocks_nothing", w.blocked() == "", w.blocked())

    w = World(combat_at_load=True)
    w.call("h_soloStub")
    w.call("h_family", 3, 4)
    check("solo.built_in_combat_no_attribute_is_written", all(v.get("type2") is None and v.get("type") is None for v in w.slots().values()) and w.blocked() == "")
    w.regen()
    s = w.slots()
    check("solo.built_in_combat_regen_reads_the_family_and_binds_the_special_slot", s["bag3"]["special"] == "shard" and s["bag3"]["type2"] == "" and s["bag3"]["type"] == "click",
          f"{s['bag3']}")


def check_solo_ui() -> None:
    """The tooltip hint and the open light follow the single bag window."""
    w = with_families({1: 1})
    tip = py(w.call("h_tooltip", "bag1")) or []
    check("solo.a_special_slot_tooltip_names_the_right_click", len(tip) == 1 and "ight click" in str(tip[0]), f"{tip}")
    tip = py(w.call("h_tooltip", "bag2")) or []
    check("solo.an_ordinary_slot_tooltip_gets_nothing_new", tip == [], f"{tip}")
    tip = py(w.call("h_tooltip", "reagent")) or []
    check("solo.the_reagent_slot_tooltip_gets_nothing_new", tip == [], f"{tip}")
    w.call("h_cfg", "bagbar.specialRight", False)
    tip = py(w.call("h_tooltip", "bag1")) or []
    check("solo.the_setting_off_drops_the_tooltip_hint", tip == [], f"{tip}")
    w.call("h_cfg", "bagbar.specialRight", True)

    check("solo.the_slot_is_not_lit_while_nothing_is_open", w.slots()["bag1"]["open"] is False)
    w.call("h_click", "bag1", "RightButton")      # the stub marks bag 1 open
    w.lua.execute("FS.BagBar.RefreshOpen()")
    s = w.slots()
    check("solo.the_slot_lights_while_its_single_window_is_open", s["bag1"]["open"] is True and s["bag2"]["open"] is False, f"{s['bag1']['open']}")
    w.call("h_click", "bag1", "RightButton")
    w.lua.execute("FS.BagBar.RefreshOpen()")
    check("solo.the_slot_goes_dark_when_the_window_closes", w.slots()["bag1"]["open"] is False)
    check("solo.refresh_open_is_exported_and_blocks_nothing", w.blocked() == "")


def main() -> int:
    check_build()
    check_clicks()
    check_missing_stock()
    check_drop_and_drag()
    check_combat()
    check_chain()
    check_login_in_combat()
    check_entering_world_in_combat()
    check_login_retry_in_combat()
    check_events()
    check_hover_highlight()
    check_quality_border()
    check_free_count_text()
    check_backpack_icon()
    check_backpack_letter_fallback()
    check_family()
    check_solo_click()
    check_solo_modes()
    check_solo_combat()
    check_solo_ui()
    check_source()
    print(f"\n{len(FAILS)} failed" if FAILS else "\nall checks passed")
    return len(FAILS)


if __name__ == "__main__":
    sys.exit(main())
