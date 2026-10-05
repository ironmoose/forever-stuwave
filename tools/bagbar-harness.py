#!/usr/bin/env python3
"""Headless check of BagBar.lua: the bag slots are SECURE buttons that delegate the click to Blizzard's stock bag buttons.

Runs the real addons/ForeverSynthwave/Deck.lua and BagBar.lua under lupa against a small STRICT mock WoW API (a method
the mock does not define is a nil call). The mock models the two things the live bug turned on:

  * taint: ToggleBackpack / ToggleBag / ToggleAllBags / OpenBag / CloseBag are recording stubs. The mock's stock bag
    buttons run their own OnClick WITHOUT touching those globals (that is Blizzard code, untainted), so any call that
    reaches a global stub came from our addon code, which on the live client throws ADDON_ACTION_FORBIDDEN when the
    stock item buttons later read the state our call tainted;
  * protection: a button made from SecureActionButtonTemplate is protected, and so is every ancestor of it. A frame a
    protected frame depends on (an anchor target) is RESTRICTED too, and that edge is transitive through the anchors:
    here the chassis (an ancestor of the buttons) is anchored to ForeverSynthwaveXPBar, which is anchored to
    ForeverSynthwaveDataBar, so all three are restricted. In combat a Show/Hide/SetPoint/SetSize/SetParent on any
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
ADDON = HERE.parent
BAGBAR_LUA = Path(os.environ.get("BAGBAR_LUA") or ADDON / "BagBar.lua")   # BAGBAR_LUA: a mutated scratch copy
DECK_LUA = Path(os.environ.get("DECK_LUA") or ADDON / "Deck.lua")
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
function M:GetTexture() return self.tex end
function M:SetAtlas(a) self.atlas = a end
function M:SetColorTexture() end
function M:SetVertexColor(r, g, b, a) self.vertex = { r, g, b, a } end
function M:SetBlendMode() end
function M:SetTexCoord() end
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
function GameTooltip:SetText() end
function GameTooltip:AddLine() end
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
C_Container = { ContainerIDToInventoryID = function(id) return 19 + id end }   -- bag N -> inventory slot 19 + N (stock GetID)
C_ActionBar = { ShouldShowKeyring = function() return KEYRING_ON end }
Enum = { BagIndex = { Bag_1 = 1, Bag_2 = 2, Bag_3 = 3, Bag_4 = 4, ReagentBag = 5, Keyring = -2 },
    ItemClass = { Container = 1, Quiver = 11 } }
EQUIPPED, LOCKED = { [20] = true, [21] = true, [22] = true, [23] = true, [24] = true }, {}

RECON = {}
FS = {
    Layout = { Scale = function() return SCALE end, OnRescale = function(fn) RESCALE[#RESCALE + 1] = fn end,
        deck = { w = 572, h = 38, rightMargin = 92 } },
    PanelSkins = { RequireExport = function() return true end },
    IsSecret = function() return false end,
    LogDegradeOnce = function(key, msg) LOGS[#LOGS + 1] = key .. ": " .. msg end,
    Theme = { SLICE_CUT_MARGIN = 6, SLICE_CUT2_FILL_TEXTURE = "cut2_fill", SLICE_CUT2_OUTLINE_TEXTURE = "cut2_outline",
        SLICE_GLOW_TEXTURE = "glow", SLICE_GLOW_MARGIN = 10, SLICE_GLOW_PAD = 4,
        COLOR_POWER = { 0.133, 0.878, 1, 1 }, COLOR_HEALTH = { 1, 0.18, 0.592, 1 }, COLOR_HUD_SCRIM = { 0.05, 0.02, 0.1, 0.5 } },
}
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
    FS.dataBar = newObj("Frame", UIParent, "ForeverSynthwaveDataBar")
    FS.dataBar:SetPoint("BOTTOM", UIParent, "BOTTOM", 0, 0)
    local xp = newObj("Frame", UIParent, "ForeverSynthwaveXPBar")
    xp:SetPoint("BOTTOM", FS.dataBar, "TOP", 0, 0)
end
function h_setup(missing, lateXP)
    for name in pairs(STOCK_IDS) do
        if name ~= missing then h_addStock(name) end
    end
    if not lateXP then h_makeXP() end
    assert(loadstring(DECK_SRC, "@Deck.lua"))("ForeverSynthwave", FS)
end
function h_load()
    assert(loadstring(BAGBAR_SRC, "@BagBar.lua"))("ForeverSynthwave", FS)
end
function h_fire(event)
    for _, f in ipairs(ALL) do
        if f.events[event] and f.scripts.OnEvent then f.scripts.OnEvent(f, event) end
    end
end
function h_rescale(s) SCALE = s; for _, fn in ipairs(RESCALE) do fn() end end
function h_logs() return table.concat(LOGS, "\n") end
function h_blocked() return table.concat(BLOCKED, ",") end
function h_toggles() return table.concat(TOGGLES, ",") end
function h_puts() return table.concat(PUTS, ",") end
function h_reset() BLOCKED, TOGGLES, PUTS, STOCKCLICKS = {}, {}, {}, {}; BLOCKED_N = 0 end
function h_stockClicks(name) return STOCKCLICKS[name] or 0, STOCKCLICKS[name .. "#button"] end

local function slot(key) return _G["ForeverSynthwaveBagSlot_" .. key] end
-- The template's click handler as it treats a KEY press or an addon :Click() (not an engine mouse press, which 12.1 forces
-- to mouse UP whatever useOnKeyDown says): with useOnKeyDown nil and the CVar on, the action fires on key DOWN, so the up
-- event does nothing; the click type calls delegate:Click(button). Kept as the conservative model: the attribute must be set.
function h_click(key, btn)
    local b = slot(key)
    if b.scripts.OnClick then b.scripts.OnClick(b, btn, false); return "addon-script" end
    if not b.protected then return "none" end
    if b.attrs.useOnKeyDown == nil then return "key-down-only" end
    if b.attrs.type == "click" and b.attrs.clickbutton then b.attrs.clickbutton:Click(btn); return "secure" end
    return "no-action"
end
function h_modifier(m) MODIFIER = m end
function h_script(key, which, ...) local b = slot(key); local fn = b.scripts[which]; if fn then fn(b, ...) end return fn ~= nil end
function h_cursor(v) CURSOR = v; h_fire("CURSOR_CHANGED") end
function h_keyring(v) KEYRING_ON = v end
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
            iconAlpha = s.icon.alpha, locked = s.locked, glowShown = s.glow.shown }
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


class World:
    def __init__(self, scale: float = 1.0, missing: str | None = None, combat_at_load: bool = False,
                 late_xp: bool = False, login_in_combat: bool = False, xp_after_login: bool = False,
                 timers: bool = False):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MOCK)
        g = self.lua.globals()
        g.DECK_SRC = DECK_LUA.read_text(encoding="utf-8")
        g.BAGBAR_SRC = BAGBAR_LUA.read_text(encoding="utf-8")
        g.SCALE = scale
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
        return {s["key"]: s for s in py(self.g.h_slots())}

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
    check("chain.the_chassis_is_anchored_to_the_xp_bar", d["anchorRel"] == "ForeverSynthwaveXPBar" and d["npts"] == 1, f"{d}")
    for name in ("ForeverSynthwaveDeck", "ForeverSynthwaveXPBar", "ForeverSynthwaveDataBar"):
        check(f"chain.{name}_is_restricted", w.call("h_restricted", name) is True)
    check("chain.an_unrelated_stock_button_is_not_restricted", w.call("h_restricted", "CharacterBag0Slot") is False)
    # Out of combat every op on the restricted frames is legal; in combat each is blocked.
    w.call("h_poke", "ForeverSynthwaveXPBar")
    check("chain.out_of_combat_the_xp_bar_can_be_resized_shown_hidden_and_moved", w.blocked() == "", w.blocked())
    w.combat(True)
    for name in ("ForeverSynthwaveXPBar", "ForeverSynthwaveDataBar"):
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
    check("login_in_combat.regen_seats_the_chassis_on_the_xp_bar", d["anchorRel"] == "ForeverSynthwaveXPBar" and d["npts"] == 1, f"{d}")
    check("login_in_combat.regen_blocks_nothing", w.blocked() == "", w.blocked())
    check("login_in_combat.no_degrade_log", w.logs() == "", w.logs())
    # The ordinary login (out of combat) seats at once.
    w = World(late_xp=True)
    d = py(w.call("h_deck"))
    check("login.out_of_combat_the_chassis_is_seated_on_the_xp_bar_at_login", d["anchorRel"] == "ForeverSynthwaveXPBar" and d["npts"] == 1, f"{d}")


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
    check("login_retry.regen_replays_the_seat_on_the_xp_bar", d["anchorRel"] == "ForeverSynthwaveXPBar" and d["npts"] == 1, f"{d}")
    check("login_retry.regen_blocks_nothing", w.blocked() == "", w.blocked())
    check("login_retry.no_degrade_log", w.logs() == "", w.logs())
    # Out of combat the same retry seats at once.
    w = World(xp_after_login=True, timers=True)
    w.call("h_makeXP")
    w.call("h_flushTimers")
    d = py(w.call("h_deck"))
    check("login_retry.out_of_combat_the_retry_seats_the_chassis", d["anchorRel"] == "ForeverSynthwaveXPBar" and d["npts"] == 1, f"{d}")
    # If the XP bar never appears, the degrade logs exactly once under the key deck_anchor. The login fires a second
    # time and the timers flush again, so the degrade is reached twice and only Deck.lua's per-key latch holds it to one.
    w = World(xp_after_login=True, timers=True)
    w.call("h_flushTimers")
    w.g.h_fire("PLAYER_LOGIN")
    w.call("h_flushTimers")
    anchor_logs = [ln for ln in w.logs().splitlines() if ln.startswith("deck_anchor: ")]
    check("login_retry.no_xp_bar_logs_the_anchor_degrade_exactly_once", len(anchor_logs) == 1, w.logs())


def check_source() -> None:
    """No call to container-opening Blizzard Lua anywhere in BagBar.lua (comments and strings do not count)."""
    pattern = re.compile(r"\b(ToggleBackpack\w*|ToggleBag\w*|ToggleAllBags|OpenBag|CloseBag|OpenAllBags|CloseAllBags|ToggleKeyRing)\s*\(")
    hits = []
    for n, line in enumerate(BAGBAR_LUA.read_text(encoding="utf-8").splitlines(), 1):
        code = re.sub(r'"[^"]*"', '""', line.split("--", 1)[0])
        if pattern.search(code):
            hits.append(f"{n}: {line.strip()}")
    check("source.no_container_opening_call_in_BagBar_lua", not hits, f"{hits}")


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
    check_source()
    print(f"\n{len(FAILS)} failed" if FAILS else "\nall checks passed")
    return len(FAILS)


if __name__ == "__main__":
    sys.exit(main())
