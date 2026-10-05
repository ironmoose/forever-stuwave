#!/usr/bin/env python3
"""Pin Minimap.lua's cut-corner chrome arguments against the REAL Theme.lua.

Loads Theme.lua and Minimap.lua under lupa on a permissive mock WoW API, fires PLAYER_LOGIN,
and checks (under Theme.CHROME_CORNERS "cut", and "round" for the A/B path):

  * map face glow + border take chamfer 6 (the mask_minimap.tga TOP-LEFT / BOTTOM-RIGHT cut),
    "round" keeps the square radius 0;
  * bezel, readout box and the addon-button tray drawer (identified by frame) keep requested
    chamfer 4 (what the 2C primitives snap to);
  * a bezel key's fill is the two-corner cut2 fill tinted READOUT_FILL, nine-sliced at the SAME
    chamfer SkinButton's ring gets (c = 6 at the 30 px key of the raw 250 px map; c = 4 at the
    ~208 px map of a 1200 tall UIParent, scale 0.833, which resolves to slice_cut2_fill_c4), and
    no rounded fill is drawn there.

  Then the addon-button tray (LibDBIcon collection), against a fake LibStub whose "LibDBIcon-1.0"
  object is shaped like the real LibDBIcon-1.0 (minor 56): lib.objects, lib.callbacks:Fire of
  "LibDBIcon_IconCreated" (button, name), GetButtonList / GetMinimapButton, and the local
  updatePosition that Refresh / Show / SetButtonRadius use to SetPoint("CENTER", Minimap, ...):

  * a pre-existing lib button and a stray FooMinimapButton child of Minimap both end up parented
    in the drawer and seated in tiles; a later IconCreated button is collected too;
  * Blizzard bezel buttons (tracking, calendar, mail, zoom, expansion button) and unrelated
    frames are NOT collected;
  * the lib's reposition (Refresh / Show / SetButtonRadius) does not move a collected button back,
    and drag-to-move is switched off;
  * the toggle shows and hides the drawer, persists the state in ForeverSynthwaveDB, shows the
    count badge and the "Addon buttons (N)" tooltip, and is hidden with zero buttons;
  * tiles wrap to more rows and the drawer grows; combat defers collection to PLAYER_REGEN_ENABLED.

    python3 tools/minimap-harness.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ADDON = Path(__file__).resolve().parent.parent
THEME_SRC = (ADDON / "Theme.lua").read_text(encoding="utf-8")
# MINIMAP_LUA / LAYOUT_LUA point the harness at a mutant copy (mutation checks).
LAYOUT_SRC = Path(os.environ.get("LAYOUT_LUA", ADDON / "Layout.lua")).read_text(encoding="utf-8")
MINIMAP_SRC = Path(os.environ.get("MINIMAP_LUA", ADDON / "Minimap.lua")).read_text(encoding="utf-8")

MOCK = r"""
local THEME_SRC, MINIMAP_SRC, MODE, UI_HEIGHT, LAYOUT_SRC, SETUP, PRE_DB = ...
local mediaPrefix = "Interface\\AddOns\\ForeverSynthwave\\media\\"
local Region = {}
Region.__index = function(t, k)
    if Region[k] then return Region[k] end
    if type(k) == "string" and k:match("^[SGHEMRCIPAUFLD]%l") and not k:match("^Zoom") then
        local verb = k:match("^%u%l+")
        local verbs = { Set = 1, Get = 1, Hide = 1, Show = 1, Enable = 1, Register = 1, Unregister = 1,
            Clear = 1, Is = 1, Hook = 1, Create = 1, Raise = 1, Lower = 1, Disable = 1, Update = 1 }
        if verbs[verb] then return function() end end
    end
end
allFrames = {}
local function new(kind, parent)
    local o = setmetatable({ kind = kind, parent = parent, regions = {}, children = {}, w = 250, h = 250,
        scripts = {}, points = {}, shown = true, events = {}, level = 1,
        strata = (parent and parent.strata) or "MEDIUM" }, Region)
    if kind == "frame" then allFrames[#allFrames + 1] = o end
    return o
end
function Region:SetSize(w, h) self.w, self.h = w, h end
function Region:SetWidth(w) self.w = w end
function Region:SetHeight(h) self.h = h end
function Region:GetWidth() return self.w end
function Region:GetHeight() return self.h end
function Region:SetTexture(p) self.texture = p end
function Region:GetTexture() return self.texture end
function Region:SetVertexColor(r, g, b, a) self.tint = { r, g, b, a } end
function Region:SetTextureSliceMargins(l) self.slice = l end
function Region:SetScript(n, fn) self.scripts[n] = fn end
function Region:GetScript(n) return self.scripts[n] end
function Region:CreateTexture(_, layer, _, sublevel)
    local t = new("texture", self)
    t.layer, t.sublevel = layer, sublevel
    self.regions[#self.regions + 1] = t
    return t
end
function Region:CreateFontString() return new("fontstring", self) end
function Region:SetParent(p)
    if self.parent then
        for i, c in ipairs(self.parent.children) do
            if c == self then table.remove(self.parent.children, i) break end
        end
    end
    self.parent = p
    if p then p.children[#p.children + 1] = self end
end
function Region:GetParent() return self.parent end
function Region:GetChildren() return unpack(self.children) end
function Region:GetRegions() return unpack(self.regions) end
function Region:GetObjectType()
    if self.kind == "texture" then return "Texture" end
    if self.kind == "fontstring" then return "FontString" end
    return self.otype or "Frame"
end
function Region:GetName() return self.name end
function Region:Show() self.shown = true end
function Region:Hide() self.shown = false end
function Region:IsShown() return self.shown end
function Region:IsVisible()
    if not self.shown then return false end
    return (not self.parent) or self.parent:IsVisible()
end
function Region:SetPoint(point, rel, relPoint, x, y)
    if type(rel) == "number" then x, y, rel, relPoint = rel, relPoint, nil, nil end
    self.points[point] = { rel = rel, relPoint = relPoint, x = x or 0, y = y or 0 }
end
function Region:ClearAllPoints() self.points = {} end
function Region:RegisterEvent(e) self.events[e] = true end
function Region:UnregisterEvent(e) self.events[e] = nil end
function Region:RegisterForDrag(...) self.dragButtons = select("#", ...) end
function Region:SetText(t) self.text = t end
function Region:GetText() return self.text end
-- Strata/level: a frame flagged fixed ignores a plain set (the conservative reading of
-- SetFixedFrameStrata/Level, which LibDBIcon buttons use), so only an unfix-first caller moves it.
function Region:SetFrameLevel(l) if not self.fixedLevel then self.level = l end end
function Region:GetFrameLevel() return self.level end
function Region:SetFrameStrata(s) if not self.fixedStrata then self.strata = s end end
function Region:GetFrameStrata() return self.strata end
function Region:SetFixedFrameStrata(v) self.fixedStrata = v and true or false end
function Region:SetFixedFrameLevel(v) self.fixedLevel = v and true or false end
function Region:SetScale(s) self.scale = s end
function Region:GetScale() return self.scale or 1 end
function Region:IsProtected() return self.protected and true or false end
function Region:SetHighlightTexture(tex, mode)
    self.highlight = self.highlight or new("texture", self)
    self.highlight.texture, self.highlight.mode = tex, mode
end
function Region:GetHighlightTexture() return self.highlight end
function Region:GetFont() return "font", 10 end
function Region:SetFont(_, size) self.fontSize = size; return true end
function Region:GetStringWidth() return 20 end
function Region:GetLeft() return 0 end
function Region:GetTop() return 0 end
function Region:GetEffectiveScale() return 1 end

function CreateFrame(otype, name, parent)
    local f = new("frame", parent)
    f.otype = otype or "Frame"
    f.name = name
    if name then _G[name] = f end
    if parent then parent.children[#parent.children + 1] = f end
    __last = f
    return f
end
UIParent = new("frame")
if UI_HEIGHT then UIParent.h = UI_HEIGHT end
Minimap = new("frame", UIParent)
MinimapCluster = new("frame", UIParent)
MinimapCluster.Tracking = new("frame", MinimapCluster)
MinimapCluster.Tracking.otype = "Button"
GameFontNormal = new("font")
DEFAULT_CHAT_FRAME = new("frame")
__combat = false
function InCombatLockdown() return __combat end
function hooksecurefunc(a, b, c)
    local obj, name, fn = a, b, c
    if type(a) == "string" then obj, name, fn = _G, a, b end
    local orig = obj[name]
    if type(orig) ~= "function" then return end
    obj[name] = function(...) local r = { orig(...) }; fn(...); return unpack(r) end
end
Enum = { UITextureSliceMode = { Stretched = 1 } }
__timers = {}
C_Timer = { After = function(_, fn) __timers[#__timers + 1] = fn end }
function RunTimers()
    local t = __timers; __timers = {}
    for _, fn in ipairs(t) do fn() end
end
function FireEvent(ev, ...)
    for _, f in ipairs(allFrames) do
        if f.events[ev] and f.scripts.OnEvent then f.scripts.OnEvent(f, ev, ...) end
    end
end
GameTooltip = { text = nil, shown = false }
function GameTooltip:SetOwner(o) self.owner = o end
function GameTooltip:SetText(t) self.text = t end
function GameTooltip:Show() self.shown = true end
function GameTooltip:Hide() self.shown = false end

FS = { LogDegradeOnce = function() end }
assert(loadstring(THEME_SRC, "@Theme.lua"))("ForeverSynthwave", FS)
local Theme = FS.Theme
Theme.CHROME_CORNERS = MODE
Theme.FONT_MONO = Theme.FONT_MONO or "mono"

calls = { glow = {}, border = {}, fill = {}, skin = {} }
local function wrap(name, bucket)
    local orig = Theme[name]
    Theme[name] = function(frame, ...)
        local args = { ... }
        calls[bucket][#calls[bucket] + 1] = { frame = frame, args = args, isMap = (frame == Minimap) }
        return orig(frame, ...)
    end
end
wrap("AddOuterGlow", "glow")
wrap("AddGradientBorder", "border")
wrap("AddRoundedFill", "fill")
wrap("SkinButton", "skin")

if PRE_DB then ForeverSynthwaveDB = PRE_DB end
if SETUP then assert(loadstring(SETUP, "@setup"))() end

-- With a UIParent height, seat the real FS.Layout so Minimap.lua derives its metrics from
-- the scaled map size exactly as in game (scale = UI_HEIGHT / 1440).
if UI_HEIGHT then assert(loadstring(LAYOUT_SRC, "@Layout.lua"))("ForeverSynthwave", FS) end
assert(loadstring(MINIMAP_SRC, "@Minimap.lua"))("ForeverSynthwave", FS)
-- the loader frame is the last frame created at file scope
__loader = __last
__Theme = Theme
return Theme
"""

# A LibDBIcon-1.0 look-alike, kept to what the real source (minor 56) does: createButton builds a
# Button parented to Minimap named LibDBIcon10_<name> with .border/.background/.icon and fires
# lib.callbacks "LibDBIcon_IconCreated" (button, name); updatePosition is a file-local that
# SetPoint("CENTER", Minimap, "CENTER", x, y) and is what Refresh / Show / SetButtonRadius call.
# lib.RegisterCallback(owner, event, fn) calls fn(event, ...) per CallbackHandler-1.0.
LIB_SETUP = r"""
local lib = { objects = {}, radius = 5 }
lib.callbacks = { events = {} }
function lib.callbacks:Fire(ev, ...)
    for _, fn in pairs(self.events[ev] or {}) do fn(ev, ...) end
end
function lib.RegisterCallback(owner, ev, fn)
    lib.callbacks.events[ev] = lib.callbacks.events[ev] or {}
    lib.callbacks.events[ev][owner] = fn
end
local function updatePosition(button, position)
    button:SetPoint("CENTER", Minimap, "CENTER", 120, 40)
end
function lib:Register(name, object, db)
    local button = CreateFrame("Button", "LibDBIcon10_" .. name, Minimap)
    button.dataObject = object
    button.db = db
    lib.objects[name] = button
    -- createButton pins strata and level as FIXED (LibDBIcon-1.0 lines 257-260)
    button:SetFrameStrata("MEDIUM")
    button:SetFixedFrameStrata(true)
    button:SetFrameLevel(8)
    button:SetFixedFrameLevel(true)
    button:RegisterForDrag("LeftButton")
    lib:ResetButtonHighlightTexture(name)
    lib:ResetButtonSize(name)
    button.border = button:CreateTexture(nil, "OVERLAY")
    lib:ResetButtonBorder(name)
    button.background = button:CreateTexture(nil, "BACKGROUND")
    lib:ResetButtonBackground(name)
    button.icon = button:CreateTexture(nil, "ARTWORK")
    lib:ResetButtonIcon(name)
    updatePosition(button, db and db.minimapPos)
    lib.callbacks:Fire("LibDBIcon_IconCreated", button, name)
end
function lib:GetMinimapButton(name) return lib.objects[name] end
-- Button configuration, shaped like the real lib's non-mainline branch.
function lib:SetButtonSize(name, size)
    local button = lib:GetMinimapButton(name)
    if button and type(size) == "number" then button:SetSize(size, size) end
end
function lib:ResetButtonSize(name)
    local button = lib:GetMinimapButton(name)
    if button then button:SetSize(31, 31) end
end
function lib:SetButtonHighlightTexture(name, tex)
    local button = lib:GetMinimapButton(name)
    if button and (type(tex) == "number" or type(tex) == "string") then button:SetHighlightTexture(tex) end
end
function lib:ResetButtonHighlightTexture(name)
    local button = lib:GetMinimapButton(name)
    if button then button:SetHighlightTexture(136477) end
end
function lib:ResetButtonBorder(name)
    local button = lib:GetMinimapButton(name)
    if button.border then
        button.border:Show()
        button.border:ClearAllPoints()
        button.border:SetPoint("TOPLEFT", 0, 0)
        button.border:SetTexture(136430)
        button.border:SetSize(53, 53)
    end
end
function lib:SetButtonBorder(name, tex, size, framePoint, ox, oy)
    local button = lib:GetMinimapButton(name)
    if button.border then
        lib:ResetButtonBorder(name)
        if type(tex) == "number" or type(tex) == "string" then button.border:SetTexture(tex) end
        if type(size) == "number" then button.border:SetSize(size, size) end
        if type(framePoint) == "string" then
            button.border:ClearAllPoints()
            button.border:SetPoint(framePoint, ox or 0, oy or 0)
        end
    end
end
function lib:ResetButtonBackground(name)
    local button = lib:GetMinimapButton(name)
    if button.background then
        button.background:Show()
        button.background:ClearAllPoints()
        button.background:SetTexture(136467)
        button.background:SetSize(20, 20)
        button.background:SetPoint("TOPLEFT", 7, -5)
    end
end
function lib:SetButtonBackground(name, tex, size, framePoint, ox, oy)
    local button = lib:GetMinimapButton(name)
    if button.background then
        lib:ResetButtonBackground(name)
        if type(tex) == "number" or type(tex) == "string" then button.background:SetTexture(tex) end
        if type(size) == "number" then button.background:SetSize(size, size) end
        if type(framePoint) == "string" then
            button.background:ClearAllPoints()
            button.background:SetPoint(framePoint, ox or 0, oy or 0)
        end
    end
end
function lib:ResetButtonIcon(name)
    local button = lib:GetMinimapButton(name)
    if button.icon then
        button.icon:SetTexture(button.dataObject.icon)
        button.icon:SetSize(17, 17)
        button.icon:ClearAllPoints()
        button.icon:SetPoint("TOPLEFT", 7, -6)
    end
end
function lib:SetButtonIcon(name, tex, size, framePoint, ox, oy)
    local button = lib:GetMinimapButton(name)
    if button.icon then
        lib:ResetButtonIcon(name)
        if type(tex) == "number" or type(tex) == "string" then button.icon:SetTexture(tex) end
        if type(size) == "number" then button.icon:SetSize(size, size) end
        if type(framePoint) == "string" then
            button.icon:ClearAllPoints()
            button.icon:SetPoint(framePoint, ox or 0, oy or 0)
        end
    end
end
function lib:GetButtonList()
    local t = {}
    for name in next, lib.objects do t[#t + 1] = name end
    return t
end
function lib:Refresh(name, db)
    local button = lib:GetMinimapButton(name)
    if button then updatePosition(button, db and db.minimapPos); button:Show() end
end
function lib:Show(name)
    local button = lib:GetMinimapButton(name)
    if button then button:Show(); updatePosition(button) end
end
function lib:Hide(name)
    local button = lib:GetMinimapButton(name)
    if button then button:Hide() end
end
function lib:SetButtonRadius(radius)
    lib.radius = radius
    for _, button in next, lib.objects do updatePosition(button) end
end
function lib:ShowOnEnter(name, value)
    local button = lib:GetMinimapButton(name)
    if button then button.showOnMouseover = value and true or false; button:SetAlpha(value and 0 or 1) end
end
LibStub = setmetatable({}, { __call = function(_, name, silent)
    if name == "LibDBIcon-1.0" then return lib end
end })
__lib = lib
function MakeObj(name) return { type = "launcher", icon = "Interface\\Icons\\" .. name } end
"""

def run(mode: str, ui_height: float | None = None, setup: str | None = None, pre_db=None,
        login: bool = True):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute("function ___run(...) " + MOCK + " end")
    pre = None
    if pre_db is not None:
        pre = lua.table_from(pre_db)
    lua.globals().___run(THEME_SRC, MINIMAP_SRC, mode, ui_height, LAYOUT_SRC, setup, pre)
    if login:
        lua.execute("__loader.scripts.OnEvent(__loader)")
    return lua


failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("PASS " if ok else "FAIL ") + label)
    if not ok:
        failures += 1


ROLE_LUA = """
function __role(f)
    if f == Minimap then return "map" end
    if f == Minimap.fsBezel then return "bezel" end
    if f == Minimap.fsReadoutBox then return "readout" end
    if f == Minimap.fsTray then return "tray" end
    if f == Minimap.fsTrayToggle then return "toggle" end
    if f.fsTrayOwned then return "tile" end
    return "other"
end
"""


TRAY_BLIZZARD = r"""
-- Blizzard furniture the bezel already owns, plus things that must never be collected.
GameTimeFrame = CreateFrame("Button", "GameTimeFrame", Minimap)
ExpansionLandingPageMinimapButton = CreateFrame("Button", "ExpansionLandingPageMinimapButton", Minimap)
Minimap.ZoomIn = CreateFrame("Button", "MinimapZoomIn", Minimap)
MinimapCluster.IndicatorFrame = { MailFrame = CreateFrame("Button", "MiniMapMailFrame", MinimapCluster) }
MiniMapMailIcon = MinimapCluster:CreateTexture(nil, "ARTWORK") -- Blizzard draws the envelope on ARTWORK
SomeRandomButton = CreateFrame("Button", "SomeRandomButton", Minimap)
SomeRandomFrame = CreateFrame("Frame", "SomeRandomMinimapButtonHolder", Minimap)
-- excluded by the hidden-by-HideBlizzardChrome flag alone, and by a Blizzard name prefix alone
FlagHiddenMinimapButton = CreateFrame("Button", "FlagHiddenMinimapButton", Minimap)
FlagHiddenMinimapButton.fsHideHooked = true
ExpansionLandingPageMinimapButton2 = CreateFrame("Button", "ExpansionLandingPageMinimapButton2", Minimap)
"""

TRAY_FULL = LIB_SETUP + TRAY_BLIZZARD + r"""
FooMinimapButton = CreateFrame("Button", "FooMinimapButton", Minimap)
__lib:Register("Alpha", MakeObj("Alpha"), {})
"""

TRAY_EMPTY = TRAY_BLIZZARD


def tray_checks() -> None:
    def same(g, a, b):
        return bool(g.__same(a, b))

    helpers = """
    function __same(a, b) return a == b end
    function __seat(b) return b.points.TOPLEFT end
    function __only_tray_anchor(b)
        local n = 0
        for _ in pairs(b.points) do n = n + 1 end
        return n == 1 and b.points.TOPLEFT and b.points.TOPLEFT.rel == Minimap.fsTray
    end
    function __click(f) f.scripts.OnClick(f, "LeftButton") end
    """

    # ---- A: a lib button, a stray, Blizzard furniture, a late IconCreated, the lib re-seating
    lua = run("cut", None, TRAY_FULL, None)
    lua.execute(helpers)
    g = lua.globals()
    tray, toggle = g.Minimap.fsTray, g.Minimap.fsTrayToggle
    alpha, foo = g.__lib.objects.Alpha, g.FooMinimapButton
    check("[tray] drawer and toggle exist", tray is not None and toggle is not None)
    check("[tray] lib button Alpha is parented in the drawer", same(g, alpha.parent, tray))
    check("[tray] stray FooMinimapButton is parented in the drawer", same(g, foo.parent, tray))
    check("[tray] both are seated in tiles (single TOPLEFT anchor on the drawer)",
          bool(g.__only_tray_anchor(alpha)) and bool(g.__only_tray_anchor(foo)))
    check("[tray] two tiles are on distinct x positions",
          g.__seat(alpha).x != g.__seat(foo).x)
    check("[tray] tiles are square and no bigger than a bezel key",
          alpha.w == alpha.h and foo.w == alpha.w and 0 < alpha.w <= 30)
    check("[tray] LibDBIcon round border and background art are hidden",
          alpha.border.shown is False and alpha.background.shown is False)
    check("[tray] LibDBIcon icon is re-seated in the tile centre",
          alpha.icon.points.CENTER is not None and alpha.icon.w < alpha.w)
    check("[tray] drag-to-move is switched off (RegisterForDrag with no buttons)",
          alpha.dragButtons == 0 and foo.dragButtons == 0)
    check("[tray] tile chrome: skin ring with an accent, underline texture present",
          alpha.fsSkin is not None and len(list(alpha.regions.values())) >= 4)

    check("[tray] bezel keys stay in the bezel (tracking, calendar, mail)",
          same(g, g.MinimapCluster.Tracking.parent, g.Minimap.fsBezel)
          and same(g, g.GameTimeFrame.parent, g.Minimap.fsBezel)
          and same(g, g.MinimapCluster.IndicatorFrame.MailFrame.parent, g.Minimap.fsBezel))
    check("[tray] expansion button, zoom button, a random button and a non-button are NOT collected",
          same(g, g.ExpansionLandingPageMinimapButton.parent, g.Minimap)
          and same(g, g.Minimap.ZoomIn.parent, g.Minimap)
          and same(g, g.SomeRandomButton.parent, g.Minimap)
          and same(g, g.SomeRandomFrame.parent, g.Minimap))
    check("[tray] a button HideBlizzardChrome hid, and a Blizzard-prefixed one, are NOT collected",
          same(g, g.FlagHiddenMinimapButton.parent, g.Minimap)
          and same(g, g.ExpansionLandingPageMinimapButton2.parent, g.Minimap))

    check("[tray] count badge reads 2", toggle.count.text == "2")
    check("[tray] toggle is shown with buttons collected", toggle.shown is True)
    toggle.scripts.OnEnter(toggle)
    check("[tray] toggle tooltip reads 'Addon buttons (2)'", g.GameTooltip.text == "Addon buttons (2)")

    # late IconCreated
    lua.execute('__lib:Register("Bravo", MakeObj("Bravo"), {})')
    bravo = g.__lib.objects.Bravo
    check("[tray] a later IconCreated button is collected and seated",
          same(g, bravo.parent, tray) and bool(g.__only_tray_anchor(bravo)))
    check("[tray] count badge reads 3 after the late button", toggle.count.text == "3")

    # the lib's own reposition must not drag a collected button back around the map
    lua.execute('__lib:Refresh("Alpha", {}); __lib:Show("Alpha"); __lib:SetButtonRadius(9)')
    check("[tray] lib Refresh/Show/SetButtonRadius do not move a collected button back",
          same(g, alpha.parent, tray) and bool(g.__only_tray_anchor(alpha))
          and alpha.points.CENTER is None and bool(g.__only_tray_anchor(bravo)))
    lua.execute('__lib:ShowOnEnter("Alpha", true)')
    check("[tray] a hover-fade request does not blank a collected button",
          alpha.showOnMouseover is False)

    # lib sizing / reparent / scale calls after adoption must not undo the tile
    tile = alpha.w
    lua.execute('__lib:SetButtonSize("Alpha", 40); __lib:ResetButtonSize("Alpha")')
    check("[tray] lib SetButtonSize/ResetButtonSize leave the button tile-sized",
          alpha.w == tile and alpha.h == tile)
    lua.execute('local a = __lib.objects.Alpha; a:SetSize(50, 50); a:SetWidth(60); a:SetHeight(61); '
                'a:SetScale(2); a:SetParent(Minimap)')
    check("[tray] direct SetSize/SetWidth/SetHeight/SetScale/SetParent are ignored",
          alpha.w == tile and alpha.h == tile and alpha.scale == 1 and same(g, alpha.parent, tray))
    check("[tray] strata matches the drawer and level sits above it, flags re-fixed",
          alpha.strata == tray.strata and alpha.level == tray.level + 2
          and alpha.fixedStrata is True and alpha.fixedLevel is True
          and foo.level == tray.level + 2)

    # lib art re-applications after adoption must be re-stripped / re-seated
    lua.execute('''
        __lib:ResetButtonBorder("Alpha"); __lib:ResetButtonBackground("Alpha")
        __lib:ResetButtonIcon("Alpha"); __lib:ResetButtonHighlightTexture("Alpha")
    ''')
    check("[tray] lib ResetButtonBorder/Background keep the round art hidden",
          alpha.border.shown is False and alpha.background.shown is False)
    check("[tray] lib ResetButtonIcon keeps the icon at the tile centre",
          alpha.icon.points.CENTER is not None and alpha.icon.points.TOPLEFT is None
          and alpha.icon.w < alpha.w)
    check("[tray] lib ResetButtonHighlightTexture keeps the square ADD wash",
          alpha.highlight.texture == "Interface\\Buttons\\WHITE8X8" and alpha.highlight.mode == "ADD")
    lua.execute('''
        __lib:SetButtonBorder("Alpha", 136430, 40, "TOPLEFT", 1, 1)
        __lib:SetButtonBackground("Alpha", 136467, 30, "CENTER", 0, 0)
        __lib:SetButtonIcon("Alpha", "NewIcon", 18, "TOPLEFT", 7, -6)
        __lib:SetButtonHighlightTexture("Alpha", 136477)
    ''')
    check("[tray] lib SetButtonBorder/Background keep the round art hidden",
          alpha.border.shown is False and alpha.background.shown is False)
    check("[tray] lib SetButtonIcon keeps the icon at the tile centre",
          alpha.icon.points.CENTER is not None and alpha.icon.points.TOPLEFT is None
          and alpha.icon.w < alpha.w)
    check("[tray] lib SetButtonHighlightTexture keeps the square ADD wash",
          alpha.highlight.texture == "Interface\\Buttons\\WHITE8X8" and alpha.highlight.mode == "ADD")

    # an addon hiding its own button drops it from the count; showing it brings it back
    alpha.Hide(alpha)
    check("[tray] a hidden button leaves the count", toggle.count.text == "2")
    alpha.Show(alpha)
    check("[tray] a shown button rejoins the count", toggle.count.text == "3")

    # a Show/Hide that changes nothing must not relayout (drawer:SetHeight is the layout's tell)
    lua.execute('__relayouts = 0; local d = Minimap.fsTray; local orig = d.SetHeight; '
                'd.SetHeight = function(self, h) __relayouts = __relayouts + 1; return orig(self, h) end')
    alpha.Show(alpha); alpha.Show(alpha)
    check("[tray] Show on an already shown button does not relayout", g.__relayouts == 0)
    alpha.Hide(alpha); alpha.Hide(alpha)
    check("[tray] Hide twice relayouts once", g.__relayouts == 1)
    alpha.Show(alpha)
    check("[tray] Show after Hide relayouts once more", g.__relayouts == 2)

    # toggle: default closed, click opens and persists, click closes and persists
    check("[tray] drawer starts closed", tray.shown is False)
    lua.execute("__click(Minimap.fsTrayToggle)")
    check("[tray] toggle click opens the drawer and persists open", tray.shown is True
          and g.ForeverSynthwaveDB.minimapTrayOpen is True)
    lua.execute("__click(Minimap.fsTrayToggle)")
    check("[tray] second click closes the drawer and persists closed", tray.shown is False
          and g.ForeverSynthwaveDB.minimapTrayOpen is False)

    # ---- B: saved open state is restored at login
    lua = run("cut", None, TRAY_FULL, {"minimapTrayOpen": True})
    check("[tray] saved open state reopens the drawer at login", lua.globals().Minimap.fsTray.shown is True)

    # ---- C: nothing to collect: toggle and drawer hidden; a late stray is picked up by a re-sweep
    lua = run("cut", None, LIB_SETUP + TRAY_EMPTY, {"minimapTrayOpen": True})
    lua.execute(helpers)
    g = lua.globals()
    check("[tray] zero buttons: toggle hidden", g.Minimap.fsTrayToggle.shown is False)
    check("[tray] zero buttons: drawer hidden even when saved open", g.Minimap.fsTray.shown is False)
    lua.execute('LateMinimapButton = CreateFrame("Button", "LateMinimapButton", Minimap); '
                'FireEvent("ADDON_LOADED", "SomeAddon")')
    check("[tray] a button created late is collected on ADDON_LOADED",
          same(g, g.LateMinimapButton.parent, g.Minimap.fsTray) and g.Minimap.fsTrayToggle.shown is True)
    lua.execute('LaterMinimapIcon = CreateFrame("Button", "LaterMinimapIcon", Minimap); '
                'FireEvent("PLAYER_ENTERING_WORLD"); RunTimers()')
    check("[tray] PLAYER_ENTERING_WORLD plus the delayed timer sweeps again",
          same(g, g.LaterMinimapIcon.parent, g.Minimap.fsTray) and g.Minimap.fsTrayToggle.count.text == "2")

    # ---- D: tiles wrap and the drawer grows
    lua = run("cut", None, LIB_SETUP + TRAY_EMPTY + r"""
    for i = 1, 20 do CreateFrame("Button", "Wrap" .. i .. "MinimapButton", Minimap) end
    """, None)
    g = lua.globals()
    tray = g.Minimap.fsTray
    lua2 = run("cut", None, LIB_SETUP + TRAY_EMPTY + 'CreateFrame("Button", "OneMinimapButton", Minimap)', None)
    one_h = lua2.globals().Minimap.fsTray.h
    ys, xs, count = set(), [], 0
    for i in range(1, 21):
        pt = g[f"Wrap{i}MinimapButton"].points.TOPLEFT
        ys.add(round(pt.y, 3))
        xs.append(pt.x)
        count += 1
    tile = g.Wrap1MinimapButton.w
    check("[tray] 20 tiles wrap onto more than one row", len(ys) >= 2)
    check("[tray] drawer height grows with the rows", tray.h > one_h)
    check("[tray] no tile spills past the drawer's right edge", max(xs) + tile <= g.Minimap.w)
    check("[tray] 20 tiles collected, badge 20", g.Minimap.fsTrayToggle.count.text == "20")

    # ---- E: combat defers the collection to PLAYER_REGEN_ENABLED
    lua = run("cut", None, LIB_SETUP + TRAY_EMPTY, None)
    lua.execute(helpers)
    g = lua.globals()
    lua.execute('__combat = true; __lib:Register("Charlie", MakeObj("Charlie"), {})')
    charlie = g.__lib.objects.Charlie
    check("[tray] in combat a new button is not reparented", same(g, charlie.parent, g.Minimap))
    lua.execute('__combat = false; FireEvent("PLAYER_REGEN_ENABLED")')
    check("[tray] PLAYER_REGEN_ENABLED collects it", same(g, charlie.parent, g.Minimap.fsTray)
          and bool(g.__only_tray_anchor(charlie)))


LOGGING = r"""
__logs = {}
FS.LogDegradeOnce = function(key, msg) __logs[#__logs + 1] = tostring(key) .. "|" .. tostring(msg) end
"""


def tray_failure_checks() -> None:
    def same(g, a, b):
        return bool(g.__same(a, b))

    helpers = "function __same(a, b) return a == b end"

    # ---- F: a failing adopt step is logged, not swallowed, and the other steps still run
    lua = run("cut", None, LIB_SETUP + LOGGING + r"""
    BoomMinimapButton = CreateFrame("Button", "BoomMinimapButton", Minimap)
    BoomMinimapButton.SetMovable = function() error("movableboom") end
    """, None)
    lua.execute(helpers)
    g = lua.globals()
    logs = [str(g.__logs[i]) for i in range(1, len(g.__logs) + 1)]
    check("[tray] a failing adopt step is logged through LogTrayFailure",
          len(logs) == 1 and "movableboom" in logs[0] and logs[0].startswith("minimap_tray|"))
    check("[tray] a failing adopt step does not stop the rest (still in the drawer, counted)",
          same(g, g.BoomMinimapButton.parent, g.Minimap.fsTray) and g.Minimap.fsTrayToggle.count.text == "1")

    # ---- G: a throw while building the toggle leaves no half-built tab or drawer
    lua = run("cut", None, LIB_SETUP + LOGGING + r"""
    local orig = FS.Theme.SkinButton
    FS.Theme.SkinButton = function(frame, ...)
        if frame.name == "ForeverSynthwaveMinimapTrayToggle" then error("toggleboom") end
        return orig(frame, ...)
    end
    """, None)
    g = lua.globals()
    logs = [str(g.__logs[i]) for i in range(1, len(g.__logs) + 1)]
    toggle = g.ForeverSynthwaveMinimapTrayToggle
    check("[tray] a toggle build failure is logged", len(logs) == 1 and "toggleboom" in logs[0])
    check("[tray] a toggle build failure leaves Minimap.fsTray / fsTrayToggle unset",
          g.Minimap.fsTray is None and g.Minimap.fsTrayToggle is None)
    check("[tray] the half-built tab is not left visible", toggle is not None and toggle.shown is False)

    # ---- H: drawer visibility in combat with a protected collected button waits for the regen
    lua = run("cut", None, LIB_SETUP + r"""
    __lib:Register("Prot", MakeObj("Prot"), {})
    __lib:Register("Plain", MakeObj("Plain"), {})
    """, None)
    lua.execute(helpers + "; function __click(f) f.scripts.OnClick(f, 'LeftButton') end")
    g = lua.globals()
    tray = g.Minimap.fsTray
    lua.execute("__lib.objects.Prot.protected = true; __combat = true")
    lua.execute("__click(Minimap.fsTrayToggle)")
    check("[tray] combat + protected button: the open click is deferred (drawer untouched)",
          tray.shown is False and g.ForeverSynthwaveDB.minimapTrayOpen is True)
    lua.execute("__combat = false; FireEvent('PLAYER_REGEN_ENABLED')")
    check("[tray] PLAYER_REGEN_ENABLED applies the deferred open", tray.shown is True)
    lua.execute("__combat = true; __click(Minimap.fsTrayToggle)")
    check("[tray] combat + protected button: the close click is deferred too", tray.shown is True)
    lua.execute("__combat = false; FireEvent('PLAYER_REGEN_ENABLED')")
    check("[tray] PLAYER_REGEN_ENABLED applies the deferred close", tray.shown is False)
    lua.execute("__lib.objects.Prot.protected = false; __combat = true; __click(Minimap.fsTrayToggle)")
    check("[tray] combat with no protected button: the drawer toggles at once", tray.shown is True)
    lua.execute("__combat = false")


MAIL_ARRIVES = r"""
-- What Blizzard 12.1 does when UPDATE_PENDING_MAIL says there is mail (Blizzard_Minimap/Mainline/Minimap.lua).
-- MiniMapMailFrameMixin:OnEvent shows the FRAME, starts the arrival animation (MinimapMailAnimMixin:OnPlay
-- hides the envelope, 0.4 to 0.5 s) and asks the PARENT to lay out. The envelope (MiniMapMailIcon, hidden="true"
-- in the XML) is shown only by MinimapMailAnimMixin:OnFinished, and MiniMapMailFrameMixin:OnHide runs
-- ResetMailIcon, which hides it. The parent was MinimapCluster.IndicatorFrame, a LayoutFrame; after our
-- reparent it is the bezel.
function __same(a, b) return a == b end
function __mail_arrives()
    local mail = MinimapCluster.IndicatorFrame.MailFrame
    MiniMapMailIcon:Hide()
    mail:Show()
    mail:GetParent():Layout()
end
function __mail_anim_finished()
    MiniMapMailIcon:Show()
end
function __mail_hides()
    local mail = MinimapCluster.IndicatorFrame.MailFrame
    mail:Hide()
    MiniMapMailIcon:Hide()
end
function __visible(r) return r:IsVisible() end
-- The notification dot is our own texture child of the mail frame: the one anchored TOPRIGHT of it,
-- plus the halo that is centred on that dot.
function __find_dot()
    local mail = MinimapCluster.IndicatorFrame.MailFrame
    local dot, halo
    for _, r in ipairs({ mail:GetRegions() }) do
        if r.points and r.points.TOPRIGHT and r.points.TOPRIGHT.rel == mail then dot = r end
    end
    for _, r in ipairs({ mail:GetRegions() }) do
        if dot and r.points and r.points.CENTER and r.points.CENTER.rel == dot then halo = r end
    end
    return dot, halo
end
"""

# Mononoki Nerd Font Mono advance, measured with PIL (0.5615 em); "99.9, 99.9" + one space + "19:56"
MONO_ADVANCE = 0.5615
READOUT_CHARS = 16
READOUT_TEXT_PAD = 8
# Mockup .mmbtn .nd: top:-2px; right:-2px; size max(3, btn * 0.34); round, pink, 5px pink glow.
DOT_OFFSET = 2
DOT_FRACTION = 0.34
DOT_GLOW_REACH = 3
GLOW_ROUND = "Interface\\AddOns\\ForeverSynthwave\\media\\glow_round.tga"
LAYER_RANK = {"BACKGROUND": 0, "BORDER": 1, "ARTWORK": 2, "OVERLAY": 3, "HIGHLIGHT": 4}


def mail_checks() -> None:
    """Mail arriving shows the third bezel key (the pink slot). Its envelope must sit centred in
    that slot at glyph size, the key must sit above the coord / clock box, and the box must start
    to the right of the slot instead of underneath it (the box used to start at 85 px against a
    key ending at 112 px on the 250 px map, so the slot lay on top of the clock)."""
    for label, ui_height in (("250", None), ("208", 1200)):
        lua = run("cut", ui_height, LIB_SETUP + TRAY_BLIZZARD, None)
        lua.execute(MAIL_ARRIVES)
        lua.execute("__mail_arrives()")
        g = lua.globals()
        m = g.Minimap.w
        bezel, box = g.Minimap.fsBezel, g.Minimap.fsReadoutBox
        k1, k2 = g.MinimapCluster.Tracking, g.GameTimeFrame
        mail = g.MinimapCluster.IndicatorFrame.MailFrame
        icon = g.MiniMapMailIcon

        def same(a, b):
            return bool(g.__same(a, b))

        check(f"[mail@{label}] mail key is the third bezel key, shown and parented in the bezel",
              same(mail.parent, bezel) and mail.shown is True and same(mail.points.LEFT.rel, k2))
        key_right = k1.points.LEFT.x + 3 * mail.w + k2.points.LEFT.x + mail.points.LEFT.x
        box_left = m - box.points.RIGHT.x * -1 - box.w
        gap = mail.points.LEFT.x
        check(f"[mail@{label}] clock box starts right of the pink slot "
              f"(box left {box_left:.1f} >= slot right {key_right:.1f} + gap {gap:.1f})",
              box_left >= key_right + gap - 1e-6)
        check(f"[mail@{label}] pink slot is drawn above the clock box (level {mail.level} > {box.level})",
              mail.level > box.level)
        key_font = max(5, mail.w * 0.5)
        want_w, want_h = key_font * 4 / 3, key_font
        pts = [k for k, _ in icon.points.items()]
        check(f"[mail@{label}] envelope is parented to the slot and anchored CENTER only, no offset",
              same(icon.parent, mail) and pts == ["CENTER"] and same(icon.points.CENTER.rel, mail)
              and icon.points.CENTER.x == 0 and icon.points.CENTER.y == 0)
        check(f"[mail@{label}] envelope is glyph sized ({want_w:.1f} x {want_h:.1f}), inside the slot",
              abs(icon.w - want_w) < 1e-6 and abs(icon.h - want_h) < 1e-6
              and icon.w <= mail.w and icon.h <= mail.h)
        dot, halo = g.__find_dot()
        # Mid animation (frame shown, envelope not yet): the dot is up and the envelope is not.
        mid = (dot is not None and bool(g.__visible(dot)) and not bool(g.__visible(icon)))
        check(f"[mail@{label}] while the arrival animation plays the dot shows alone, the envelope is not up yet",
              mid)
        lua.execute("__mail_anim_finished()")
        check(f"[mail@{label}] the envelope shows once the animation finishes, with the dot still up",
              bool(g.__visible(icon)) and dot is not None and bool(g.__visible(dot)))
        lua.execute("__mail_hides()")
        check(f"[mail@{label}] hiding the frame hides the envelope and the dot together",
              not bool(g.__visible(icon)) and dot is not None and not bool(g.__visible(dot)))
        lua.execute("__mail_arrives()")
        check(f"[mail@{label}] a notification dot exists: a glow_round texture on the slot", dot is not None
              and dot.texture == GLOW_ROUND and same(dot.parent, mail))
        if dot is not None:
            tr = dot.points.TOPRIGHT
            want_dot = max(3, mail.w * DOT_FRACTION)
            check(f"[mail@{label}] dot is anchored TOPRIGHT of the slot at +{DOT_OFFSET},+{DOT_OFFSET} (the mockup's -2px)",
                  same(tr.rel, mail) and tr.x == DOT_OFFSET and tr.y == DOT_OFFSET)
            check(f"[mail@{label}] dot is round and sized max(3, key * {DOT_FRACTION}) = {want_dot:.2f}",
                  abs(dot.w - want_dot) < 1e-6 and abs(dot.h - want_dot) < 1e-6)
            tint = dot.tint
            check(f"[mail@{label}] dot is tinted pink",
                  tint is not None and abs(tint[1] - 1) < 1e-6 and tint[2] < 0.5 and tint[3] > 0.4)
            check(f"[mail@{label}] dot has a pink glow halo centred on it, reaching {DOT_GLOW_REACH}px past its edge",
                  halo is not None and abs(halo.w - (dot.w + 2 * DOT_GLOW_REACH)) < 1e-6
                  and halo.points.CENTER.x == 0 and halo.points.CENTER.y == 0)
            mail.Hide(mail)
            hidden = (not dot.IsVisible(dot)) and (halo is None or not halo.IsVisible(halo))
            mail.Show(mail)
            shown = dot.IsVisible(dot) and (halo is None or halo.IsVisible(halo))
            check(f"[mail@{label}] dot hides with the mail frame and shows with it (no hooks, own flag untouched)",
                  hidden and shown and dot.shown is True)
            rank = lambda r: (LAYER_RANK.get(str(r.layer), -1), r.sublevel or 0)
            check(f"[mail@{label}] dot sits above the envelope ({dot.layer}/{dot.sublevel} over {icon.layer}/{icon.sublevel}), "
                  f"halo below the dot",
                  rank(dot) > rank(icon) and (halo is None or rank(halo) < rank(dot)))
        for name, fs in (("coords", g.Minimap.fsReadoutCoords), ("clock", g.Minimap.fsReadoutClock)):
            need = READOUT_CHARS * MONO_ADVANCE * fs.fontSize + READOUT_TEXT_PAD
            check(f"[mail@{label}] {name} font {fs.fontSize:.1f} fits a typical reading in the box "
                  f"({need:.1f} <= {box.w})", need <= box.w + 1e-6)


def coords_setup(x: float, y: float, secret: bool = False) -> str:
    """Seat a player map position (0-1 fractions) and a game clock before the addon loads, so the
    readout's first update at login formats them. With secret=True the position's numbers are an
    opaque sentinel that throws on any arithmetic, and FS.IsSecret recognises it, like a secret
    number on a live client."""
    pos = "__SECRET, __SECRET" if secret else f"{x}, {y}"
    return f"""
__SECRET = setmetatable({{}}, {{ __mul = function() error("secret arithmetic", 2) end }})
FS.IsSecret = function(v) return v == __SECRET end
C_Map = {{
    GetBestMapForUnit = function() return 1 end,
    GetPlayerMapPosition = function() return {{ GetXY = function() return {pos} end }} end,
}}
function GetGameTime() return 19, 56 end
"""


def coords_checks() -> None:
    """The readout shows the player position as 'x, y' percentages. A fraction of 1.0 would format
    as '100.0' (17 glyphs with the clock, about 7 px over the box at m = 250), so each axis clamps
    to 99.9, and a secret position blanks the text instead of throwing."""
    for label, ui_height in (("250", None), ("208", 1200)):
        cases = (
            ("(1.0, 1.0) clamps to 99.9, 99.9", 1.0, 1.0, False, "99.9, 99.9"),
            ("(0.9996, 1.5) rounds and clamps, never 100.0", 0.9996, 1.5, False, "99.9, 99.9"),
            ("(0.5, 0.25) is untouched", 0.5, 0.25, False, "50.0, 25.0"),
            ("a secret position blanks the text", 0, 0, True, ""),
        )
        for name, x, y, secret, want in cases:
            lua = run("cut", ui_height, coords_setup(x, y, secret), None)
            g = lua.globals()
            box, coords, clock = g.Minimap.fsReadoutBox, g.Minimap.fsReadoutCoords, g.Minimap.fsReadoutClock
            check(f"[coords@{label}] {name}: reads {want!r}", (coords.text or "") == want)
            if want:
                glyphs = len(coords.text) + 1 + len(clock.text)
                need = glyphs * MONO_ADVANCE * coords.fontSize + READOUT_TEXT_PAD
                check(f"[coords@{label}] {name}: {glyphs} glyphs with the clock fit the box "
                      f"({need:.1f} <= {box.w})", glyphs <= READOUT_CHARS and need <= box.w + 1e-6)


# A geometry world for the Edit Mode seat checks. The permissive mock above answers 0 for every
# rect, so the compensation never measures anything there; this one resolves single-anchor frames
# into UIParent coordinates (offsets and sizes scaled by the frame's effective scale), and shapes
# MinimapCluster like the 12.1 source:
#   * a ResizeLayoutFrame (Minimap.xml:3): any Layout pass (the synchronous one in
#     EditModeMinimapSystemMixin:UpdateSystemSettingHeaderUnderneath, or the deferred OnUpdate one a
#     MarkDirty arms) resets its size to the children's extents, overriding the SetSize
#     FS.Layout.Apply wrote;
#   * MinimapContainer (parentKey) anchored TOP of the cluster at (10, -30), the Minimap CENTERed in
#     it, so the map hangs from the cluster's TOP edge and its centre column, not from its middle;
#   * an Edit Mode system: InitSystemAnchors parks it TOPLEFT 0,0, UpdateSystem runs
#     ApplySystemAnchor, then the Size setting (SetEditModeScale on the container) and
#     SetHeaderUnderneath (re-anchors the container, then Layout()).
# EditModeManagerFrame:UpdateLayoutInfo is that sequence; Layout.lua hooks it at load.
LAYOUT_W, LAYOUT_H = 256, 270   # what a Layout pass leaves the cluster at (children's extents)

GEO_SETUP = r"""
ForeverSynthwaveDB = {}
local now = 100
function GetTime() now = now + 0.25; return now end
local R = getmetatable(UIParent)
UIParent.w = UIParent.h * 16 / 9
local LAYOUT_W, LAYOUT_H = %(lw)d, %(lh)d
local FRAC = { TOPLEFT = { 0, 1 }, TOP = { .5, 1 }, TOPRIGHT = { 1, 1 }, LEFT = { 0, .5 },
    CENTER = { .5, .5 }, RIGHT = { 1, .5 }, BOTTOMLEFT = { 0, 0 }, BOTTOM = { .5, 0 }, BOTTOMRIGHT = { 1, 0 } }
local function escale(f)
    local s = 1
    while f and f ~= UIParent do s = s * (f.scale or 1); f = f.parent end
    return s
end
local function rect(f)
    if f == UIParent then return 0, 0, UIParent.w, UIParent.h end
    local es = escale(f)
    local w, h = f.w * es, f.h * es
    local point, p = next(f.points)
    if not p then return 0, 0, w, h end
    local rl, rb, rw, rh = rect(p.rel or f.parent or UIParent)
    local rf = FRAC[p.relPoint or point]
    local ff = FRAC[point]
    local x, y = rl + rf[1] * rw + p.x * es, rb + rf[2] * rh + p.y * es
    return x - ff[1] * w, y - ff[2] * h, w, h
end
-- Like the client, GetLeft/GetTop/... answer in the frame's OWN scale space (screen units divided
-- by its effective scale): the Minimap inside a container scaled by Edit Mode's Size setting reads
-- bigger numbers than the unscaled cluster for the same screen position. __rect stays absolute.
function R:GetEffectiveScale() return escale(self) end
function R:GetLeft() local l = rect(self); return l / escale(self) end
function R:GetBottom() local _, b = rect(self); return b / escale(self) end
function R:GetRight() local l, _, w = rect(self); return (l + w) / escale(self) end
function R:GetTop() local _, b, _, h = rect(self); return (b + h) / escale(self) end
function R:GetCenter() local l, b, w, h = rect(self); local s = escale(self); return (l + w / 2) / s, (b + h / 2) / s end
function R:GetPoint(i)
    local point, p = next(self.points)
    if not p then return end
    return point, p.rel or self.parent, p.relPoint or point, p.x, p.y
end
function R:IsClampedToScreen() return self.clamped and true or false end
function R:SetClampedToScreen(v) self.clamped = v and true or false end
__rect = rect

local container = CreateFrame("Frame", nil, MinimapCluster)
container.w, container.h = 215, 226
container:SetPoint("TOP", MinimapCluster, "TOP", 10, -30)
MinimapCluster:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", 0, 0)
MinimapCluster.MinimapContainer = container
Minimap:SetParent(container)
Minimap.w, Minimap.h = 198, 198
Minimap:SetPoint("CENTER", container, "CENTER", 0, 0)
MinimapCluster.w, MinimapCluster.h = LAYOUT_W, LAYOUT_H
MinimapCluster.clamped = true                       -- EditModeSystemTemplate clampedToScreen="true"

function MinimapCluster:Layout() self.w, self.h = LAYOUT_W, LAYOUT_H; self.dirty = false; __layouts = (__layouts or 0) + 1 end
function MinimapCluster:MarkDirty() self.dirty = true end
function MinimapCluster:SetEditModeScale(s) container.scale = s end
-- Blizzard_Minimap/Mainline/Minimap.lua SetHeaderUnderneath: Header Underneath hangs the container
-- from the cluster's BOTTOM edge (10, 30) instead of its TOP edge (10, -30), both /scale.
function MinimapCluster:SetHeaderUnderneath(under)
    local s = container.scale or 1
    container:ClearAllPoints()
    if under then
        container:SetPoint("BOTTOM", self, "BOTTOM", 10 / s, 30 / s)
    else
        container:SetPoint("TOP", self, "TOP", 10 / s, -30 / s)
    end
end
-- Edit Mode system frames keep the originals as *Base and override SetPoint/ClearAllPoints.
MinimapCluster.SetPointBase, MinimapCluster.ClearAllPointsBase = R.SetPoint, R.ClearAllPoints
function MinimapCluster:SetPoint(...) __dirtyFlagWrites = (__dirtyFlagWrites or 0) + 1; return R.SetPoint(self, ...) end
function MinimapCluster:ApplySystemAnchor()
    R.ClearAllPoints(self); R.SetPoint(self, "TOPRIGHT", UIParent, "TOPRIGHT", 0, 0)
end
__editScale = 1
__header = false
function MinimapCluster:UpdateSystem()
    self:ApplySystemAnchor()
    self:SetEditModeScale(__editScale)
    self:SetHeaderUnderneath(__header or false)
    self:Layout()
end
function MinimapCluster:GetNumPoints() return 1 end

EditModeManagerFrame = CreateFrame("Frame", "EditModeManagerFrame", UIParent)
function EditModeManagerFrame:UpdateLayoutInfo()
    R.ClearAllPoints(MinimapCluster); R.SetPoint(MinimapCluster, "TOPLEFT", UIParent, "TOPLEFT", 0, 0)
    MinimapCluster:UpdateSystem()
end

-- One client frame. Whether the deferred Layout OnUpdate or a C_Timer.After(0) timer runs first in
-- a frame is the engine's business, so every sequence is driven in both orders.
function __frame(layoutFirst)
    local function layout() if MinimapCluster.dirty then MinimapCluster:Layout() end end
    if layoutFirst then layout(); RunTimers() else RunTimers(); layout() end
end
function __frames(n, layoutFirst) for _ = 1, n do __frame(layoutFirst) end end

-- The map's expected edges for the layout entry: top and left from the entry, in UIParent coords.
function __want()
    local L, s = FS.Layout.minimap, FS.Layout.Scale()
    local left = UIParent.w / 2 + L.x * s - L.w * s / 2
    return UIParent.h / 2 + L.y * s + L.h * s / 2, left, left + L.w * s
end
function __got()
    local l, b, w, h = rect(Minimap)
    return b + h, l, l + w
end
"""


def geo_world(setup_extra: str = "") -> "LuaRuntime":
    setup = GEO_SETUP % {"lw": LAYOUT_W, "lh": LAYOUT_H} + setup_extra
    return run("cut", 1200, setup, None, login=False)


def first_login_checks() -> None:
    """A new character's first login: the seat at PLAYER_LOGIN is right, then the server's
    EDIT_MODE_LAYOUTS_UPDATED runs EditModeManagerFrame:UpdateLayoutInfo, which parks MinimapCluster
    at TOPLEFT 0,0, re-applies its system anchor, its Size (the container scale) and its header
    (re-anchoring the container and running a Layout pass that resets the cluster's size to its
    children's extents), and a later dirty-triggered Layout pass can land after our re-seat. The
    visible MAP must end up at FS.Layout.minimap's top and left (and right at scale 1) in every
    ordering, and again after a /reload-style sequence."""
    tol = 0.01

    def at_target(g, scale_one: bool) -> tuple[bool, str]:
        wt, wl, wr = g.__want()
        gt, gl, gr = g.__got()
        ok = abs(gt - wt) < tol and abs(gl - wl) < tol and (not scale_one or abs(gr - wr) < tol)
        return ok, f"top {gt:.2f}/{wt:.2f} left {gl:.2f}/{wl:.2f} right {gr:.2f}/{wr:.2f}"

    for order in (False, True):
        o = "layout-first" if order else "timers-first"
        flag = "true" if order else "false"
        # --- first login: seat, settle, then the server's layout update, then Blizzard dirties it
        lua = geo_world()
        g = lua.globals()
        lua.execute('FireEvent("PLAYER_LOGIN")')
        lua.execute(f"__frames(3, {flag})")
        ok, msg = at_target(g, True)
        check(f"[first login {o}] map on target after the PLAYER_LOGIN seat ({msg})", ok)
        lua.execute("EditModeManagerFrame:UpdateLayoutInfo()")
        lua.execute("MinimapCluster:MarkDirty()")   # Blizzard dirties the cluster after our hook
        lua.execute(f"__frames(4, {flag})")
        ok, msg = at_target(g, True)
        check(f"[first login {o}] map on target after UpdateLayoutInfo + a later Layout pass ({msg})", ok)
        # a Layout pass that lands after our last re-seat (Blizzard dirties the cluster again)
        lua.execute("MinimapCluster:MarkDirty()")
        lua.execute(f"__frames(3, {flag})")
        ok, msg = at_target(g, True)
        check(f"[first login {o}] the cluster really was re-laid out after our seat (size "
              f"{g.MinimapCluster.h:g} = children's extents {LAYOUT_H}) and the map is still on target ({msg})",
              g.MinimapCluster.h == LAYOUT_H and ok)

        # --- a Size change (container scale 1.2) arriving later moves the map's edges, not its anchor
        lua.execute("__editScale = 1.2; MinimapCluster:SetEditModeScale(1.2); MinimapCluster:SetHeaderUnderneath(false)")
        lua.execute(f"__frames(4, {flag})")
        ok, msg = at_target(g, False)
        check(f"[first login {o}] map top and left on target after a later Edit Mode Size change ({msg})", ok)

        # --- the whole first-login sequence with a non-default Size
        lua = geo_world("__editScale = 1.2")
        g = lua.globals()
        lua.execute('FireEvent("PLAYER_LOGIN")')
        lua.execute(f"__frames(3, {flag})")
        lua.execute("EditModeManagerFrame:UpdateLayoutInfo(); MinimapCluster:MarkDirty()")
        lua.execute(f"__frames(4, {flag})")
        ok, msg = at_target(g, False)
        check(f"[first login {o}] Size 120: map top and left on target ({msg})", ok)

        # --- /reload: Edit Mode already applied (and the layout settled) before the addon loads
        lua = geo_world("EditModeManagerFrame:UpdateLayoutInfo()")
        g = lua.globals()
        lua.execute('FireEvent("PLAYER_LOGIN")')
        lua.execute(f"__frames(4, {flag})")
        ok, msg = at_target(g, True)
        check(f"[reload {o}] map on target after the PLAYER_LOGIN seat ({msg})", ok)
        lua.execute("MinimapCluster:MarkDirty()")
        lua.execute(f"__frames(3, {flag})")
        ok, msg = at_target(g, True)
        check(f"[reload {o}] map still on target after a later Layout pass ({msg})", ok)
        lua.execute('FireEvent("PLAYER_ENTERING_WORLD", false, true)')
        lua.execute(f"__frames(3, {flag})")
        ok, msg = at_target(g, True)
        check(f"[reload {o}] map on target after PLAYER_ENTERING_WORLD ({msg})", ok)

    # --- no double compensation: re-running the compensation does not move the cluster twice
    lua = geo_world()
    g = lua.globals()
    lua.execute('FireEvent("PLAYER_LOGIN")')
    lua.execute("__frames(3, false)")
    lua.execute("EditModeManagerFrame:UpdateLayoutInfo(); __frames(3, false)")
    lua.execute("__p0 = { MinimapCluster:GetPoint() }")
    before = list(lua.eval("__p0").values())
    lua.execute(r"""
        for _ = 1, 3 do
            for _, fn in ipairs(FS.Layout._rescaleCallbacks) do pcall(fn) end
            __frames(2, false)
        end
        __p1 = { MinimapCluster:GetPoint() }
    """)
    after = list(lua.eval("__p1").values())
    same_anchor = (before[0], before[2]) == (after[0], after[2]) and all(
        abs(float(a) - float(b)) < 1e-6 for a, b in zip(before[3:], after[3:]))
    ok, msg = at_target(g, True)
    check(f"[idempotent] three more compensation passes leave the cluster anchor unchanged "
          f"({before[0]} {before[3]:.3f},{before[4]:.3f} -> {after[0]} {after[3]:.3f},{after[4]:.3f})", same_anchor)
    check(f"[idempotent] and the map on target ({msg})", ok)
    # a UI scale change re-Applies the raw seat, then the compensation puts the correction back once
    lua.execute("UIParent.h = 1080; UIParent.w = 1080 * 16 / 9; FireEvent('UI_SCALE_CHANGED'); __frames(3, false)")
    ok, msg = at_target(g, False)
    check(f"[idempotent] a UI scale change re-seats and the map is on target again ({msg})", ok)
    check("[clamp] screen clamping stays off on the cluster after the sequence",
          not g.MinimapCluster.IsClampedToScreen(g.MinimapCluster))


def trigger_checks() -> None:
    """Each thing Blizzard can do to the cluster after our seat, ALONE (no other hook rescues it),
    must end with the map back on target; plus the combat hold and the one-timer coalescing."""
    tol = 0.01

    def on_target(g, scale_one: bool = False) -> tuple[bool, str]:
        wt, wl, wr = g.__want()
        gt, gl, gr = g.__got()
        ok = abs(gt - wt) < tol and abs(gl - wl) < tol and (not scale_one or abs(gr - wr) < tol)
        return ok, f"top {gt:.2f}/{wt:.2f} left {gl:.2f}/{wl:.2f}"

    def seated():
        lua = geo_world()
        lua.execute('FireEvent("PLAYER_LOGIN")')
        lua.execute("__frames(3, false)")
        return lua, lua.globals()

    # The container scale alone (Edit Mode's Size setting), then the header alone.
    lua, g = seated()
    lua.execute("__editScale = 1.2; MinimapCluster:SetEditModeScale(1.2)")
    lua.execute("__frames(3, false)")
    ok, msg = on_target(g)
    check(f"[trigger] SetEditModeScale alone re-compensates ({msg})", ok)
    lua, g = seated()
    lua.execute("MinimapCluster:SetHeaderUnderneath(true)")
    lua.execute("__frames(3, false)")
    ok, msg = on_target(g, True)
    check(f"[trigger] SetHeaderUnderneath alone re-compensates ({msg})", ok)

    # ApplySystemAnchor reached without UpdateLayoutInfo (Reset to default position) re-seats a frame later.
    lua, g = seated()
    lua.execute("MinimapCluster:ApplySystemAnchor()")
    wrong = not on_target(g, True)[0]
    lua.execute("__frames(3, false)")
    ok, msg = on_target(g, True)
    check(f"[trigger] ApplySystemAnchor alone: the cluster really moved, then is re-seated ({msg})", wrong and ok)

    # Blizzard moves the cluster AFTER UpdateLayoutInfo returned (its callers' later steps), through
    # the Base call so no hooked method runs: our own post-hook and the event watcher re-seat a frame later.
    for how, fire in (("UpdateLayoutInfo hook", "EditModeManagerFrame:UpdateLayoutInfo()"),
                      ("EDIT_MODE_LAYOUTS_UPDATED", 'FireEvent("EDIT_MODE_LAYOUTS_UPDATED")')):
        lua, g = seated()
        lua.execute(fire)
        lua.execute("""local R = getmetatable(UIParent)
            R.ClearAllPoints(MinimapCluster); R.SetPoint(MinimapCluster, "TOPLEFT", UIParent, "TOPLEFT", 0, 0)""")
        wrong = not on_target(g, True)[0]
        lua.execute("__frames(3, false)")
        ok, msg = on_target(g, True)
        check(f"[trigger] a move after {how} returned is re-seated a frame later ({msg})", wrong and ok)

    # The first PLAYER_ENTERING_WORLD of a login re-seats; a zone change does not.
    lua, g = seated()
    lua.execute("""local R = getmetatable(UIParent)
        R.ClearAllPoints(MinimapCluster); R.SetPoint(MinimapCluster, "TOPLEFT", UIParent, "TOPLEFT", 0, 0)""")
    lua.execute('FireEvent("PLAYER_ENTERING_WORLD", true, false)')
    lua.execute("__frames(3, false)")
    ok, msg = on_target(g, True)
    check(f"[trigger] PLAYER_ENTERING_WORLD of a login re-seats ({msg})", ok)
    lua, g = seated()
    lua.execute('FireEvent("PLAYER_ENTERING_WORLD", false, false)')
    lua.execute("__frames(3, false)")
    seen = lua.eval('(function() for _, e in ipairs(ForeverSynthwaveDB.minimapSeatLog) do '
                    'if e.ev == "PLAYER_ENTERING_WORLD" or e.ev == "reseat" then return true end end return false end)()')
    check("[trigger] a zone-change PLAYER_ENTERING_WORLD does not re-seat", not seen)

    # Combat: a protected cluster is not touched (no SetPoint), and the seat lands when combat ends.
    lua, g = seated()
    lua.execute("""
        MinimapCluster.IsProtected = function() return true end
        __writes = 0
        local base = MinimapCluster.SetPointBase
        MinimapCluster.SetPointBase = function(...) __writes = __writes + 1; return base(...) end
        __combat = true
        EditModeManagerFrame:UpdateLayoutInfo()
        __frames(3, false)
    """)
    held = lua.eval("__writes") == 0
    lua.execute("__combat = false; FireEvent('PLAYER_REGEN_ENABLED'); __frames(3, false)")
    ok, msg = on_target(g, True)
    check(f"[trigger] a protected cluster is left alone in combat and re-seated when it ends "
          f"(writes in combat held: {held}; {msg})", held and ok)

    # Many hook calls in one frame arm one timer, not one each.
    lua, g = seated()
    lua.execute("__timers = {}; for _ = 1, 6 do MinimapCluster:SetEditModeScale(1) end")
    n = lua.eval("#__timers")
    check(f"[trigger] six SetEditModeScale calls in a frame arm one compensation timer (got {n})", n == 1)
    lua.execute("__timers = {}; for _ = 1, 6 do MinimapCluster:ApplySystemAnchor() end")
    n = lua.eval("#__timers")
    check(f"[trigger] six ApplySystemAnchor calls in a frame arm one re-seat timer (got {n})", n == 1)


def review_checks() -> None:
    """Held compensation, Header Underneath, scale spaces, the log's session handling, hook retry."""
    tol = 0.01

    def on_target(g, scale_one: bool = False) -> tuple[bool, str]:
        wt, wl, wr = g.__want()
        gt, gl, gr = g.__got()
        ok = abs(gt - wt) < tol and abs(gl - wl) < tol and (not scale_one or abs(gr - wr) < tol)
        return ok, f"top {gt:.2f}/{wt:.2f} left {gl:.2f}/{wl:.2f}"

    def seated(extra: str = ""):
        lua = geo_world(extra)
        lua.execute('FireEvent("PLAYER_LOGIN")')
        lua.execute("__frames(3, false)")
        return lua, lua.globals()

    # --- a compensation refused in combat is finished at regen, and compensation works afterwards
    lua, g = seated()
    lua.execute("""
        MinimapCluster.IsProtected = function() return true end
        __combat = true
        __editScale = 1.2
        MinimapCluster:SetEditModeScale(1.2)
        __frames(3, false)
    """)
    lua.execute("__combat = false; FireEvent('PLAYER_REGEN_ENABLED'); __frames(4, false)")
    ok, msg = on_target(g)
    check(f"[held] SetEditModeScale in combat, then regen: the map lands on target ({msg})", ok)
    lua.execute("__header = true; MinimapCluster:SetHeaderUnderneath(true); __frames(4, false)")
    ok, msg = on_target(g)
    check(f"[held] and a later SetHeaderUnderneath is still compensated (the pending flag was released) ({msg})", ok)

    # --- Header Underneath hangs the map from the cluster's BOTTOM: still on target, still idempotent
    for order in (False, True):
        o = "layout-first" if order else "timers-first"
        flag = "true" if order else "false"
        lua, g = seated("__header = true")
        lua.execute("EditModeManagerFrame:UpdateLayoutInfo(); MinimapCluster:MarkDirty()")
        lua.execute(f"__frames(4, {flag})")
        ok, msg = on_target(g, True)
        check(f"[header under {o}] first login: map on target after UpdateLayoutInfo + a Layout pass ({msg})", ok)
        lua.execute("__p0 = { MinimapCluster:GetPoint() }")
        lua.execute(f"MinimapCluster:MarkDirty(); __frames(3, {flag})")
        lua.execute("""
            for _ = 1, 3 do for _, fn in ipairs(FS.Layout._rescaleCallbacks) do pcall(fn) end; __frames(2, false) end
            __p1 = { MinimapCluster:GetPoint() }
        """)
        before, after = list(lua.eval("__p0").values()), list(lua.eval("__p1").values())
        same = before[0] == after[0] and all(abs(float(a) - float(b)) < 1e-6 for a, b in zip(before[3:], after[3:]))
        ok, msg = on_target(g, True)
        check(f"[header under {o}] a later Layout pass and three more compensations leave the anchor "
              f"({before[0]}) and the map unchanged ({msg})", same and ok)
        lua, g = seated("__header = true; __editScale = 1.2")
        lua.execute("EditModeManagerFrame:UpdateLayoutInfo(); MinimapCluster:MarkDirty()")
        lua.execute(f"__frames(4, {flag})")
        ok, msg = on_target(g)
        check(f"[header under {o}] Size 120: map top and left on target ({msg})", ok)

    # --- the idempotent pass writes nothing: no anchor write at all
    lua, g = seated()
    lua.execute("""
        __writes = 0
        local base, clear = MinimapCluster.SetPointBase, MinimapCluster.ClearAllPointsBase
        MinimapCluster.SetPointBase = function(...) __writes = __writes + 1; return base(...) end
        MinimapCluster.ClearAllPointsBase = function(...) __writes = __writes + 1; return clear(...) end
        for _ = 1, 4 do for _, fn in ipairs(FS.Layout._rescaleCallbacks) do pcall(fn) end; __frames(2, false) end
        MinimapCluster:SetEditModeScale(1); __frames(2, false)
    """)
    check("[idempotent] a compensation that finds the anchor already right writes nothing (no clear, no set)",
          lua.eval("__writes") == 0)
    lua.execute("""
        __writes = 0
        MinimapCluster:MarkDirty(); __frames(3, false)   -- a Layout pass moves nothing: still no write
    """)
    check("[idempotent] and a later Layout pass needs no write either", lua.eval("__writes") == 0)

    # --- GetTop/GetLeft are in each frame's own scale space (the map sits at container scale 1.2)
    lua, g = seated("__editScale = 1.2")
    lua.execute("EditModeManagerFrame:UpdateLayoutInfo(); __frames(4, false)")
    ok, msg = on_target(g)
    scale_space = abs(float(lua.eval("Minimap:GetLeft() - select(1, __rect(Minimap))")) ) > 1
    check(f"[scale spaces] the mock really answers in frame space at Size 120, and the map is on target ({msg})",
          scale_space and ok)

    # --- the log: this session starts with the PLAYER_LOGIN rescale pass, the previous one is untouched
    lua = geo_world('ForeverSynthwaveDB.minimapSeatLog = { { ev = "old1" }, { ev = "old2" } }')
    lua.execute('FireEvent("PLAYER_LOGIN")'); lua.execute("__frames(3, false)")
    prev = lua.eval('(function() local t = {} for _, e in ipairs(ForeverSynthwaveDB.minimapSeatLogPrev or {}) do '
                    't[#t + 1] = e.ev end return table.concat(t, ",") end)()')
    check(f"[seat log] the PLAYER_LOGIN rescale pass lands in this session's log, the previous log stays "
          f"exactly as it was ({prev})", prev == "old1,old2"
          and lua.eval("ForeverSynthwaveDB.minimapSeatLog[1].ev") == "rescale:PLAYER_LOGIN")

    # --- minimapSeatLogFirst: filled only when no log existed, never rotated or overwritten
    lua = geo_world()
    lua.execute('FireEvent("PLAYER_LOGIN")'); lua.execute("__frames(3, false)")
    lua.execute("EditModeManagerFrame:UpdateLayoutInfo(); __frames(3, false)")
    check("[first slot] the first session ever logged fills minimapSeatLogFirst (it holds the login sequence)",
          lua.eval('(function() local f = ForeverSynthwaveDB.minimapSeatLogFirst; if not f then return false end '
                   'for _, e in ipairs(f) do if e.ev == "UpdateLayoutInfo" then return true end end return false end)()'))
    lua = geo_world('ForeverSynthwaveDB.minimapSeatLogFirst = { { ev = "first1" } }; '
                    'ForeverSynthwaveDB.minimapSeatLog = { { ev = "second" } }')
    lua.execute('FireEvent("PLAYER_LOGIN")'); lua.execute("__frames(3, false)")
    lua.execute("for i = 1, 40 do UIParent.h = 1200 + i; FireEvent('EDIT_MODE_LAYOUTS_UPDATED'); __frames(2, false) end")
    check("[first slot] later sessions leave it alone however much they log, and the previous session rotates as before",
          lua.eval("#(ForeverSynthwaveDB.minimapSeatLogFirst or {})") == 1
          and lua.eval("(ForeverSynthwaveDB.minimapSeatLogFirst[1] or {}).ev") == "first1"
          and lua.eval("((ForeverSynthwaveDB.minimapSeatLogPrev or {})[1] or {}).ev") == "second")
    lua = geo_world('ForeverSynthwaveDB.minimapSeatLog = { { ev = "old" } }')
    lua.execute('FireEvent("PLAYER_LOGIN")'); lua.execute("__frames(3, false)")
    check("[first slot] a session that finds a log from before does not fill it",
          lua.eval("ForeverSynthwaveDB.minimapSeatLogFirst") is None)

    # --- hooks: a missing method is skipped, the log says which exist, the retry installs it later
    lua, g = seated("__asa = MinimapCluster.ApplySystemAnchor; MinimapCluster.ApplySystemAnchor = nil")
    hk = lua.eval('(function() for _, e in ipairs(ForeverSynthwaveDB.minimapSeatLog) do '
                  'if e.ev == "hooks" then return e.hk end end end)()')
    check(f"[hooks] a client without ApplySystemAnchor installs the others and logs which ({hk})", hk == "SHU")
    lua.execute("MinimapCluster.ApplySystemAnchor = __asa; FireEvent('ADDON_LOADED', 'Blizzard_EditMode')")
    hk2 = lua.eval('(function() local last; for _, e in ipairs(ForeverSynthwaveDB.minimapSeatLog) do '
                   'if e.ev == "hooks" then last = e.hk end end return last end)()')
    lua.execute("MinimapCluster:ApplySystemAnchor()")
    wrong = not on_target(g, True)[0]
    lua.execute("__frames(3, false)")
    ok, msg = on_target(g, True)
    check(f"[hooks] a method that appears when Blizzard_EditMode loads is hooked then ({hk2}); "
          f"the Reset path is re-seated ({msg})", hk2 == "SHAU" and wrong and ok)
    lua, g = seated()
    hk = lua.eval('(function() for _, e in ipairs(ForeverSynthwaveDB.minimapSeatLog) do '
                  'if e.ev == "hooks" then return e.hk end end end)()')
    check(f"[hooks] a full client logs all four hooks installed ({hk})", hk == "SHAU")


def mutation_gap_checks() -> None:
    """Behaviours the first mutation pass left unpinned: the cluster's own scale, the regen
    replay of a held re-seat, the raw seat between a re-seat and its compensation, the log's
    dedupe of two hook installs, and the log's scale space."""
    tol = 0.01

    def seated(extra: str = ""):
        lua = geo_world(extra)
        lua.execute('FireEvent("PLAYER_LOGIN")')
        lua.execute("__frames(3, false)")
        return lua, lua.globals()

    def on_target(g, scale_one: bool = False) -> tuple[bool, str]:
        wt, wl, wr = g.__want()
        gt, gl, gr = g.__got()
        ok = abs(gt - wt) < tol and abs(gl - wl) < tol and (not scale_one or abs(gr - wr) < tol)
        return ok, f"top {gt:.2f}/{wt:.2f} left {gl:.2f}/{wl:.2f}"

    # A cluster whose own scale is not UIParent's: SetPoint offsets are in the cluster's space.
    lua, g = seated("MinimapCluster.scale = 0.8")
    lua.execute("EditModeManagerFrame:UpdateLayoutInfo(); __frames(4, false)")
    ok, msg = on_target(g)
    check(f"[cluster scale] a cluster scaled 0.8 still puts the map on target ({msg})", ok)

    # A re-seat refused in combat (only ApplySystemAnchor ran, no scale or header hook to rescue it)
    # is replayed at regen.
    lua, g = seated()
    lua.execute("""
        MinimapCluster.IsProtected = function() return true end
        __combat = true
        MinimapCluster:ApplySystemAnchor()
        __frames(3, false)
    """)
    wrong = not on_target(g, True)[0]
    lua.execute("__combat = false; FireEvent('PLAYER_REGEN_ENABLED'); __frames(4, false)")
    ok, msg = on_target(g, True)
    check(f"[regen] a re-seat refused in combat is done at regen (it was off target: {wrong}; {msg})", wrong and ok)

    # The held compensation is released at regen: a second regen arms nothing.
    lua, g = seated()
    lua.execute("""
        MinimapCluster.IsProtected = function() return true end
        __combat = true
        MinimapCluster:SetEditModeScale(1.2)
        __frames(3, false)
        __combat = false; FireEvent('PLAYER_REGEN_ENABLED'); __frames(4, false)
        __timers = {}
        FireEvent('PLAYER_REGEN_ENABLED')
    """)
    n = lua.eval("#__timers")
    check(f"[regen] a second regen after the held compensation finished arms no timer (got {n})", n == 0)

    # A re-seat shows the map where it belongs at once: the cluster is written once, with the
    # inset measured before, so no rendered frame sees the raw layout seat (the map ~38 units off).
    lua, g = seated()
    lua.execute("""
        MinimapCluster:ApplySystemAnchor()
        local timers = __timers; __timers = {}
        for _, fn in ipairs(timers) do fn() end       -- only the re-seat timer, not the compensation it arms
        __armed = #__timers
    """)
    ok, msg = on_target(g, True)
    check(f"[reseat] the map is on target as soon as the re-seat ran, with a compensation still armed "
          f"({msg}, armed {lua.eval('__armed')})", ok and lua.eval("__armed") == 1)

    # Per rendered frame: after the first seat, none of the events that re-seat the cluster shows the
    # map off target for even one frame (sampled right after the event and after every client frame).
    for size_label, extra in (("Size 100", ""), ("Size 120", "__editScale = 1.2"),
                              ("Header Underneath", "__header = true")):
        for ev_label, ev in (("reload PLAYER_ENTERING_WORLD", 'FireEvent("PLAYER_ENTERING_WORLD", false, true)'),
                             ("EDIT_MODE_LAYOUTS_UPDATED", 'FireEvent("EDIT_MODE_LAYOUTS_UPDATED")'),
                             ("UpdateLayoutInfo", "EditModeManagerFrame:UpdateLayoutInfo()")):
            for layout_first in ("false", "true"):
                lua = geo_world(extra + "; EditModeManagerFrame:UpdateLayoutInfo()")
                g = lua.globals()
                lua.execute('FireEvent("PLAYER_LOGIN")')
                lua.execute(f"__frames(5, {layout_first})")
                lua.execute(ev)
                devs = []
                for _ in range(4):
                    devs.append(abs(g.__got()[0] - g.__want()[0]))
                    lua.execute(f"__frame({layout_first})")
                check(f"[no jump] {size_label}, {ev_label}, layout {'first' if layout_first == 'true' else 'last'}: "
                      f"no rendered frame is off target (worst {max(devs):.2f})", max(devs) < tol)

    # Two hook-install entries in a row are two entries, not a repeat.
    lua = geo_world("__asa = MinimapCluster.ApplySystemAnchor; MinimapCluster.ApplySystemAnchor = nil")
    lua.execute('FireEvent("PLAYER_LOGIN")')
    lua.execute("MinimapCluster.ApplySystemAnchor = __asa; FireEvent('ADDON_LOADED', 'Blizzard_EditMode')")
    hks = lua.eval('(function() local t = {} for _, e in ipairs(ForeverSynthwaveDB.minimapSeatLog) do '
                   'if e.ev == "hooks" then t[#t + 1] = e.hk end end return table.concat(t, ",") end)()')
    check(f"[seat log] a late hook install right after the first is its own entry ({hks})", hks == "SHU,SHAU")

    # The log's map readings are in the same space as its targets (UIParent units) at Size 120.
    lua, g = seated("__editScale = 1.2")
    lua.execute("EditModeManagerFrame:UpdateLayoutInfo(); __frames(4, false)")
    d = lua.eval('(function() local last; for _, e in ipairs(ForeverSynthwaveDB.minimapSeatLog) do '
                 'if e.ev == "compensate" then last = e end end '
                 'return { mt = last.mt, tt = last.tt, ml = last.ml, tl = last.tl } end)()')
    ok = (None not in (d["mt"], d["tt"], d["ml"], d["tl"])
          and abs(float(d["mt"]) - float(d["tt"])) < 0.2 and abs(float(d["ml"]) - float(d["tl"])) < 0.2)
    check(f"[seat log] at Size 120 the logged map edges match the logged targets "
          f"(mt {d['mt']} tt {d['tt']}, ml {d['ml']} tl {d['tl']})", ok)


def seat_log_checks() -> None:
    """ForeverSynthwaveDB.minimapSeatLog: what /fsbug shows when the minimap is seated wrong."""
    lua = geo_world()
    lua.execute('FireEvent("PLAYER_LOGIN")')
    lua.execute("__frames(3, false)")
    lua.execute("EditModeManagerFrame:UpdateLayoutInfo(); __frames(3, false)")
    lua.execute("""
        local evs, fields = {}, true
        for i, e in ipairs(ForeverSynthwaveDB.minimapSeatLog) do
            evs[#evs + 1] = e.ev
            for _, k in ipairs({ "ev", "t", "pt", "x", "y", "mt", "ml", "tt", "tl", "sc", "clamp" }) do
                if e[k] == nil then fields = false end
            end
            for k, v in pairs(e) do
                local t = type(v)
                if t ~= "number" and t ~= "string" and t ~= "boolean" then fields = false end
            end
        end
        __seatEvs, __seatFields = table.concat(evs, ","), fields
    """)
    evs = str(lua.eval("__seatEvs"))
    check(f"[seat log] the login sequence is logged in order ({evs})",
          evs.startswith("rescale:PLAYER_LOGIN,seat,hooks,") and ",UpdateLayoutInfo," in evs and "compensate" in evs
          and "rescale:UpdateLayoutInfo" in evs)
    lua.execute('FireEvent("EDIT_MODE_LAYOUTS_UPDATED"); __frames(2, false)')
    check("[seat log] the server's EDIT_MODE_LAYOUTS_UPDATED is logged, so its order against our seat can be read",
          bool(lua.eval('(function() for _, e in ipairs(ForeverSynthwaveDB.minimapSeatLog) do '
                        'if e.ev == "EDIT_MODE_LAYOUTS_UPDATED" then return true end end return false end)()')))
    check("[seat log] every entry carries event, time, cluster point and offsets, map top and left, "
          "layout target, scale and clamp, as plain numbers, strings or booleans", bool(lua.eval("__seatFields")))
    check("[seat log] the cluster's clamp is logged as off after the compensation",
          bool(lua.eval("ForeverSynthwaveDB.minimapSeatLog[#ForeverSynthwaveDB.minimapSeatLog].clamp == false")))

    # --- 20 entries, the first 10 pinned, a repeat counts up instead of taking a slot
    lua.execute("""
        for i = 1, 4 do                                   -- pad the login sequence past 10 entries
            UIParent.h = 1200 - i; UIParent.w = UIParent.h * 16 / 9
            FireEvent("EDIT_MODE_LAYOUTS_UPDATED"); __frames(2, false)
        end
        __first10 = {}
        for i = 1, 10 do __first10[i] = ForeverSynthwaveDB.minimapSeatLog[i].ev .. ":" .. ForeverSynthwaveDB.minimapSeatLog[i].t end
        local n0 = #ForeverSynthwaveDB.minimapSeatLog
        for i = 1, 60 do
            UIParent.h = 1200 + i                       -- a different state every time
            UIParent.w = UIParent.h * 16 / 9
            FireEvent("EDIT_MODE_LAYOUTS_UPDATED")
            __frames(2, false)
        end
        __logN = #ForeverSynthwaveDB.minimapSeatLog
        __pinned = true
        for i = 1, 10 do
            local e = ForeverSynthwaveDB.minimapSeatLog[i]
            if e.ev .. ":" .. e.t ~= __first10[i] then __pinned = false end
        end
    """)
    check(f"[seat log] capped at 20 entries ({lua.eval('__logN')})", lua.eval("__logN") == 20)
    check("[seat log] the first 10 entries (the login sequence) stay pinned", bool(lua.eval("__pinned")))
    lua.execute("""
        local before = #ForeverSynthwaveDB.minimapSeatLog
        for _ = 1, 5 do FS.Layout.rescaleWhy = "repeat"; for _, fn in ipairs(FS.Layout._rescaleCallbacks) do pcall(fn) end end
        FS.Layout.rescaleWhy = nil
        local last = ForeverSynthwaveDB.minimapSeatLog[#ForeverSynthwaveDB.minimapSeatLog]
        __repeatN, __repeatGrew = last.n, #ForeverSynthwaveDB.minimapSeatLog > before + 1
    """)
    check(f"[seat log] the same state repeated counts up (n={lua.eval('__repeatN')}) instead of taking slots",
          lua.eval("__repeatN") == 5 and not lua.eval("__repeatGrew"))

    # --- the previous session is kept, the new one starts empty
    lua = geo_world('ForeverSynthwaveDB.minimapSeatLog = { { ev = "old session" } }')
    lua.execute('FireEvent("PLAYER_LOGIN")')
    lua.execute("__frames(3, false)")
    check("[seat log] the previous session's log is kept as minimapSeatLogPrev",
          lua.eval("((ForeverSynthwaveDB.minimapSeatLogPrev or {})[1] or {}).ev") == "old session")
    check("[seat log] and this session starts a fresh log",
          lua.eval("ForeverSynthwaveDB.minimapSeatLog[1].ev") == "rescale:PLAYER_LOGIN")

    # --- a secret reading never lands in the log or breaks the seat
    lua = geo_world("""
        FS.IsSecret = function(v) return v == __secret end
        __secret = 12345.5
        local R2 = getmetatable(UIParent)
        local orig = R2.GetLeft
        R2.GetLeft = function(self) if self == Minimap then return __secret end return orig(self) end
    """)
    lua.execute('FireEvent("PLAYER_LOGIN")')
    lua.execute("__frames(3, false)")
    lua.execute("""
        __secretLeaked = false
        for _, e in ipairs(ForeverSynthwaveDB.minimapSeatLog) do
            for _, v in pairs(e) do if v == __secret then __secretLeaked = true end end
        end
    """)
    check("[seat log] a secret map reading is dropped, never stored, and does not throw",
          not lua.eval("__secretLeaked") and lua.eval("#ForeverSynthwaveDB.minimapSeatLog") > 0)


def main() -> int:
    # (label, chrome mode, UIParent height or None for the raw 250 px design map,
    #  expected key chamfer, expected cut2 fill file name)
    cases = (
        ("cut", "cut", None, 6, "slice_cut2_fill.tga"),
        ("round", "round", None, None, None),
        # UIParent 1200 tall -> scale 1200 / 1440 = 0.833, map ~208 px, key ~25 px -> chamfer 4.
        ("cut@208", "cut", 1200, 4, "slice_cut2_fill_c4.tga"),
    )
    for label, mode, ui_height, key_c, key_file in cases:
        lua = run(mode, ui_height, LIB_SETUP + '__lib:Register("Alpha", MakeObj("Alpha"), {})')
        lua.execute(ROLE_LUA)
        g = lua.globals()
        role = g.__role
        calls = g.calls

        def rows(bucket):
            return list(calls[bucket].values())

        glow, border, fill, skin = (rows(b) for b in ("glow", "border", "fill", "skin"))
        tray_fill = [c for c in fill if role(c.frame) == "tray"]
        tray_border = [c for c in border if role(c.frame) == "tray"]
        tile_fill = [c for c in fill if role(c.frame) == "tile"]
        toggle_fill = [c for c in fill if role(c.frame) == "toggle"]
        tile_skin = [c for c in skin if role(c.frame) == "tile"]
        toggle_skin = [c for c in skin if role(c.frame) == "toggle"]
        fill = [c for c in fill if role(c.frame) in ("bezel", "readout", "other")]
        skin = [c for c in skin if role(c.frame) == "other"]
        if ui_height:
            width = g.Minimap.w
            check(f"[{label}] map seated at the scaled width (~208)", abs(width - 250 * ui_height / 1440) < 1e-6)
        map_glow = [c for c in glow if role(c.frame) == "map"]
        map_border = [c for c in border if role(c.frame) == "map"]
        want_map = 6 if mode == "cut" else 0
        check(f"[{label}] map glow radius {want_map}", len(map_glow) == 1 and map_glow[0].args[6] == want_map)
        check(f"[{label}] map border radius {want_map}", len(map_border) == 1 and map_border[0].args[3] == want_map)
        # bezel / readout, identified by their frame (not by radius, which the map border could
        # share): radius 4 on both fill and border.
        for who in ("bezel", "readout"):
            who_fill = [c for c in fill if role(c.frame) == who]
            who_border = [c for c in border if role(c.frame) == who]
            check(f"[{label}] {who} fill and border at 4",
                  len(who_fill) == 1 and who_fill[0].args[2] == 4
                  and len(who_border) == 1 and who_border[0].args[3] == 4)
        check(f"[{label}] tray drawer fill and border at 4",
              len(tray_fill) == 1 and tray_fill[0].args[2] == 4
              and len(tray_border) == 1 and tray_border[0].args[3] == 4)
        key_skins = skin
        assert key_skins, f"[{label}] no key was skinned: StyleBezelKey never reached SkinButton"
        if mode == "cut":
            check(f"[{label}] key SkinButton gets chamfer {key_c}",
                  all(c.args[1]["chamfer"] == key_c for c in key_skins))
            key = key_skins[0].frame
            fills = [t for t in key.regions.values() if isinstance(t.texture, str) and "slice_cut2_fill" in t.texture]
            check(f"[{label}] key fill is {key_file}, margin {key_c}, READOUT_FILL tint",
                  len(fills) == 1 and fills[0].texture.endswith("\\" + key_file) and fills[0].slice == key_c
                  and abs(fills[0].tint[1] - 0.016) < 1e-9)
            check(f"[{label}] key draws no rounded fill (bezel + readout only)", len(fill) == 2)
        else:
            check(f"[{label}] key keeps the rounded fill (bezel + readout + key)", len(fill) == 3)

        # tray tile + toggle tab chrome: same recipe as a key, chamfer from their own size
        tile, toggle = g.__lib.objects.Alpha, g.Minimap.fsTrayToggle
        check(f"[{label}] tray tile and toggle each get exactly one SkinButton",
              len(tile_skin) == 1 and len(toggle_skin) == 1)
        for who, frame, skins, rounded in (("tile", tile, tile_skin, tile_fill),
                                            ("toggle", toggle, toggle_skin, toggle_fill)):
            if mode == "cut":
                want_c = g.__Theme.Cut2ButtonSet(g.__Theme.CutSizeIcon(frame.h))[2]
                fills = [t for t in frame.regions.values() if isinstance(t.texture, str) and "slice_cut2_fill" in t.texture]
                check(f"[{label}] {who} SkinButton chamfer {want_c} (size {frame.h:g})",
                      skins[0].args[1]["chamfer"] == want_c)
                check(f"[{label}] {who} fill is a cut2 slice at margin {want_c}, READOUT_FILL tint, no rounded fill",
                      len(fills) == 1 and fills[0].slice == want_c and abs(fills[0].tint[1] - 0.016) < 1e-9
                      and len(rounded) == 0)
            else:
                check(f"[{label}] {who} keeps the rounded fill and no chamfer",
                      len(rounded) == 1 and skins[0].args[1]["chamfer"] is None)
    tray_checks()
    tray_failure_checks()
    mail_checks()
    coords_checks()
    first_login_checks()
    trigger_checks()
    review_checks()
    mutation_gap_checks()
    seat_log_checks()
    print("failures:", failures)
    return failures


if __name__ == "__main__":
    sys.exit(main())
