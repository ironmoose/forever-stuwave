#!/usr/bin/env python3
"""Runs the real CastBars.lua and ChevronCastBar.lua headless against a mock WoW API.

CastBars.lua puts the PLAYER and TARGET cast bars on the shared chevron engine, laid out as
the locked "Stack A": two bars of one width (268 at pixel scale 1), the target on top and
the player below, 18 units apart on a fixed seat (gap centre at (0, -317)); the ForeverDebugBridge
frame is not read at all. The parse gate proves it compiles; these checks pin the WIRING with mocked spellcast events, a stepped
clock and a stubbed screen:

  * build: both bars 268 x 22 at scale 1 (14 chevrons), stacked with an 18 gap, tabs on the
    outer edges (target top-right, player under-left) as 5-unit trapezoids (fill wedges, strokes,
    flips), a 1px icon stroke, lock-in without a scale pop, the default channel finish, the
    Blizzard bars dimmed only after both builds succeeded, the events registered, the timer
    column measured from the font (and the fallback of 56 when it cannot be);
  * placement: the fixed seat (target and player CENTER at -317 +- (9 + 11), x 0), also at a UI
    scale of 0.64, every frame edge on a whole physical pixel and the gap 18 (within a pixel of
    snapping), a ForeverDebugBridge frame anywhere on screen never moves the bars and is never read, the
    engine is re-laid out once per move (no loop), and a UI scale change re-places the stack and
    refits the bars;
  * casts: start, succeed and lock-in (timer "0.9 / 1.5" style, " / total" muted), a natural
    channel end plays the engine's finish, a clip stops, the tick counter (by spell id, then
    name) and CUT, DELAYED never restarts the engine, mismatched castIDs and cast events during a
    channel are ignored, PLAYER_ENTERING_WORLD resets;
  * secrets: the target with secret cast info (name, times, castID, interruptible flag)
    neither throws nor compares a secret; the engine-timed strip takes over, follows the
    engine pitch, drops the total's decimal at 10s when it is plain, and ends on its own when
    the cast is plainly gone (never on a secret);
  * the idle row API (FS.CastBars.SetIdleHint / SetIdleVisible) and event error reporting.

The mock is strict (a widget method it does not define fails as a nil call) and is NOT the
real client. Theme.lua's constants are read from the real file; the Theme helper functions
CastBars.lua calls and FrameHelpers' step runner are small stubs (the real
ChevronCastBar.lua is loaded unchanged).

    python3 tools/castbars-harness.py

Exit 0 = every check passed. CASTBARS_LUA=<path> runs another file in place of CastBars.lua.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
CASTBARS = Path(os.environ.get("CASTBARS_LUA", ADDON / "Modules/CastBars/CastBars.lua"))


def _load_chevron_harness():
    # The engine harness already owns the strict widget mock and the Theme constant
    # extractor; reuse them rather than keep a second copy in step.
    spec = importlib.util.spec_from_file_location("chevroncastbar_harness", HERE / "chevroncastbar-harness.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHEV = _load_chevron_harness()

THEME_CONSTANTS = CHEV.THEME_CONSTANTS + (
    "COLOR_HEALTH", "COLOR_CAST_NO_INTERRUPT", "COLOR_BAR_TRACK", "COLOR_BAR_BORDER", "COLOR_TEXT_PARCHMENT",
    "SLICE_GLOW_TEXTURE", "SLICE_GLOW_PAD", "SLICE_GLOW_MARGIN",
    "SLICE_CUT2_FILL_TEXTURE", "SLICE_CUT2_OUTLINE_TEXTURE", "SLICE_CUT_MARGIN",
    "CAST_CHEVRON_STRIP_TEXTURE", "CAST_CHEVRON_STRIP_TILE_W", "CAST_CHEVRON_STRIP_TILE_H",
)

# Widget methods and globals CastBars.lua needs on top of the engine's mock.
MOCK = r"""
local Region = getmetatable(UIParent)
__all = {}
__printed = {}
function print(...)
    local t = {}
    for i = 1, select("#", ...) do t[#t + 1] = tostring((select(i, ...))) end
    __printed[#__printed + 1] = table.concat(t, " ")
end

-- A secret string (a spell name) and a secret boolean. type() answers like the client:
-- "string" / "boolean". Any method call on the name, ordering or concatenation throws.
__SECRET_NAME = setmetatable({}, {
    __eq = function() error("secret name compared") end,
    __lt = function() error("secret name ordered") end,
    __concat = function() error("secret name concatenated") end,
})
__SECRET_BOOL = setmetatable({}, { __eq = function() error("secret flag compared") end })
local typeBefore = type
function type(v)
    if rawequal(v, __SECRET_NAME) then return "string" end
    if rawequal(v, __SECRET_BOOL) then return "boolean" end
    return typeBefore(v)
end
local function isSecret(v)
    return rawequal(v, __SECRET) or rawequal(v, __SECRET_ID) or rawequal(v, __SECRET_NAME) or rawequal(v, __SECRET_BOOL)
end

local origCreateFrame = CreateFrame
function CreateFrame(kind, name, parent, tmpl)
    local f = origCreateFrame(kind, name, parent)
    f._kind, f._name, f._events, f._unitEvents = kind, name, {}, {}
    f._min, f._max, f._value = 0, 1, 0
    __all[#__all + 1] = f
    return f
end
local origCreateTexture = Region.CreateTexture
function Region:CreateTexture(name, layer, tmpl, sub)
    local t = origCreateTexture(self, name, layer, tmpl, sub)
    t._layer, t._sub = layer, sub
    __all[#__all + 1] = t
    self._regions = self._regions or {}
    self._regions[#self._regions + 1] = t
    return t
end
-- The client throws "Font not set" for SetText / SetFormattedText on a FontString with no font: one made
-- with an inherits template carries that template's font, otherwise SetFont / SetFontObject (Theme.ApplyMono
-- calls SetFont) must come first. A write before that kills a pcall'd build.
function Region:CreateFontString(name, layer, template)
    local t = origCreateTexture(self, name, layer)
    t._kind, t._layer, t._text = "FontString", layer, ""
    if type(template) == "string" then t._hasFont = true end
    __all[#__all + 1] = t
    return t
end
function Region:SetFont(path, size, flags) self._hasFont, self._fontSize = true, size; return true end
function Region:SetFontObject() self._hasFont = true end

function Region:SetText(s)
    if self._kind == "FontString" and not self._hasFont then error("Font not set", 2) end
    self._text = s
end
function Region:GetText() return self._text end
function Region:SetFormattedText(fmt, ...)
    if self._kind == "FontString" and not self._hasFont then error("Font not set", 2) end
    for i = 1, select("#", ...) do
        if isSecret((select(i, ...))) then self._text, self._secretText = "<secret>", true; return end
    end
    self._text, self._secretText = string.format(fmt, ...), false
end
-- 6 units a character: "0.0 / 0.0" measures 54, the mockup's width at 11pt. __charW overrides it
-- (a number, or "throw" for a client that cannot measure).
function Region:GetStringWidth()
    if rawequal(self._text, __SECRET_NAME) then error("measured a secret string") end
    if __charW == "throw" then error("cannot measure") end
    return #tostring(self._text) * (__charW or 6)
end
function Region:SetTextColor(r, g, b) self._textColor = { r, g, b } end
function Region:SetJustifyH(j) self._justifyH = j end
function Region:SetWordWrap(v) self._wordWrap = v end
function Region:SetWidth(w) self._w = w end
function Region:SetHeight(h) self._h = h end
function Region:SetScale(s) self._scale = s end
function Region:GetScale() return self._scale or 1 end
function Region:RegisterEvent(e) self._events[e] = true end
function Region:UnregisterEvent(e) self._events[e] = nil end
function Region:RegisterUnitEvent(e, u) self._unitEvents[e] = u end
function Region:SetStatusBarTexture(path)
    if not self._fill then
        self._fill = origCreateTexture(self, nil, "ARTWORK")
        self._fill._kind = "Texture"
        __all[#__all + 1] = self._fill
    end
    self._fill._texture = path
end
function Region:GetStatusBarTexture() return self._fill end
function Region:SetStatusBarColor(r, g, b, a) self._fill._vc = { r, g, b, a or 1 } end
function Region:SetMinMaxValues(lo, hi) self._min, self._max = lo, hi end
function Region:SetValue(v) self._value = v end
function Region:SetTimerDuration(d) self._timer = d end
function Region:SetHorizTile(v) self._horizTile = v end
function Region:SetColorTexture(r, g, b, a) self._colorTexture = { r, g, b, a } end
-- Stores the boolean RAW: a truth test on a secret cannot be trapped, so the check is that the
-- value reached the setter untouched.
function Region:SetAlphaFromBoolean(b, t, f) self._fromBool = b end

-- Screen. UIParent's centre is a fixed point on the screen (683, 384 in screen units); in
-- UIParent's own units that is centre / effective scale. __ui(s) sets the UI scale.
function Region:GetCenter() return self._cx, self._cy end
function Region:GetLeft() return self._l end
function Region:GetRight() return self._r end
function Region:GetBottom() return self._b end
function Region:GetTop() return self._t end
function Region:GetRegions() return unpack(self._regions or {}) end
function __ui(s)
    UIParent._scale = s
    UIParent._cx, UIParent._cy = 683 / s, 384 / s
end
__ui(1)
-- Fires an event at every frame that registered it (the engine's rescale watcher included).
function __fireEvent(event, ...)
    local frames = {}
    for _, f in ipairs(__all) do if f._events and f._events[event] then frames[#frames + 1] = f end end
    for _, f in ipairs(frames) do
        local fn = f._scripts.OnEvent
        if fn then fn(f, event, ...) end
    end
end
-- C_Timer.After: callbacks wait for __flushTimers (the next frame).
__timers = {}
C_Timer = { After = function(sec, fn) __timers[#__timers + 1] = fn end }
function __flushTimers()
    local t = __timers
    __timers = {}
    for _, fn in ipairs(t) do fn() end
end

-- The two units: a plain cast, or a channel, or nothing. Times are in ms, GetTime() domain.
-- A "secret" unit hands out secret values for everything but the texture.
__units = { player = { exists = true }, target = { exists = true } }
function UnitExists(u) return __units[u].exists end
function UnitCastingInfo(u)
    local c = __units[u].cast
    if not c then return nil end
    return c.name, "", c.tex, c.startMS, c.endMS, false, c.castID, c.notInt, c.spellID or 1
end
function UnitChannelInfo(u)
    local c = __units[u].chan
    if not c then return nil end
    return c.name, "", c.tex, c.startMS, c.endMS, false, c.notInt, c.spellID
end
local function duration(c)
    if not c then return nil end
    if c.dur then
        return { GetRemainingDuration = function() return c.dur.rem end,
                 GetElapsedDuration = function() return c.dur.el end,
                 GetTotalDuration = function() return c.dur.total end }
    end
    if c.secret then
        return { GetRemainingDuration = function() return __SECRET end,
                 GetElapsedDuration = function() return __SECRET end,
                 GetTotalDuration = function() return __SECRET end }
    end
    local total = (c.endMS - c.startMS) / 1000
    return { GetRemainingDuration = function() return c.endMS / 1000 - GetTime() end,
             GetElapsedDuration = function() return GetTime() - c.startMS / 1000 end,
             GetTotalDuration = function() return total end }
end
function UnitCastingDuration(u) return duration(__units[u].cast) end
function UnitChannelDuration(u) return duration(__units[u].chan) end

-- Hover-only mouse (FrameHelpers.HoverOnly), the tooltip the real spell tooltip helpers draw into, and OnHide
-- hooks (the client fires OnHide when a shown frame hides).
function Region:SetMouseMotionEnabled(v) self._mouseMotion = v end
function Region:SetMouseClickEnabled(v) self._mouseClick = v end
function Region:EnableMouse(v) self._mouse = v end
do
    local origHide, origSetShown = Region.Hide, Region.SetShown
    local function fireHide(self, was)
        if was then for _, fn in ipairs(self._hooks and self._hooks.OnHide or {}) do fn(self) end end
    end
    function Region:Hide() local was = self._shown; origHide(self); fireHide(self, was) end
    function Region:SetShown(v) local was = self._shown; origSetShown(self, v); if not v then fireHide(self, was) end end
end
function hover(f) for _, fn in ipairs(f._hooks and f._hooks.OnEnter or {}) do fn(f) end end
TT = {}
GameTooltip = TT
function TT:Reset() self.owner, self.shown, self.spellID, self.text, self.lines = nil, false, nil, nil, {} end
function TT:SetOwner(o) self:Reset(); self.owner = o end
function TT:GetOwner() return self.owner end
function TT:SetText(t) self.text = t end
function TT:AddLine(t) self.lines[#self.lines + 1] = t end
function TT:Show() self.shown = true end
function TT:Hide() self.shown = false; self.owner = nil end
function TT:SetSpellByID(id) self.spellID = id; self.shown = true end
TT:Reset()
InCombatLockdown = InCombatLockdown or function() return false end
"""

# Stubs for what CastBars.lua reads off FS, then the engine; CastBars.lua itself loads inside
# each check (its Init runs at file scope, after the check has set the screen and any bridge frame).
WIRE = r"""
FS.IsSecret = function(v)
    return rawequal(v, __SECRET) or rawequal(v, __SECRET_ID) or rawequal(v, __SECRET_NAME) or rawequal(v, __SECRET_BOOL)
end
local Theme = FS.Theme
Theme.ApplyMono = function(fs, size, color) fs._fontSize, fs._monoColor, fs._hasFont = size, color, true end   -- the real one calls SetFont
Theme.ApplyNineSlice = function(tex, margin) tex._sliceMargin = margin; return true end
Theme.AddSliceTexture = function(frame, path, color, layer, sublevel, inset)
    local t = frame:CreateTexture(nil, layer or "BACKGROUND", nil, sublevel)
    t:SetTexture(path)
    t._inset = inset or 0
    if color then t:SetVertexColor(color[1], color[2], color[3], color[4] or 1) end
    return t
end
Theme.AddCut2Texture = function(frame, path, color, layer, sublevel, inset)
    local isOutline = path == Theme.SLICE_CUT2_OUTLINE_TEXTURE
    if isOutline then
        __outlineCalls = (__outlineCalls or 0) + 1
        if __failOutlineAt == __outlineCalls then error("outline build failed") end
    end
    local t = Theme.AddSliceTexture(frame, path, color, layer, sublevel, inset)
    t._sliceMargin = Theme.SLICE_CUT_MARGIN
    t._cutOutline = isOutline or nil
    return t
end
__dimmed = {}
FS.FrameHelpers = {
    NewStepRunner = function(describeStep)
        return function(frame, label, fn)
            local ok, err = pcall(fn, frame)
            if not ok then print(describeStep(label) .. " failed: " .. tostring(err)) end
        end, function() end
    end,
    SafeRegisterUnitEvent = function(events, event, unit, onFail)
        local ok, err = pcall(events.RegisterUnitEvent, events, event, unit)
        if not ok then onFail(event, err) end
    end,
    DimBlizzardFrame = function(frame) __dimmed[#__dimmed + 1] = frame end,
}
-- The real spell tooltip helpers (hover-only, cached id), lent to the stub when a harness hands over the source.
if __helpers_source then
    local real = {}
    local scratch = { Theme = FS.Theme, IsSecret = FS.IsSecret, AurasReadable = function() return not InCombatLockdown() end, FrameHelpers = real }
    assert(loadstring(__helpers_source, "@Core/FrameHelpers.lua"))("forever-stuwave", scratch)
    for _, k in ipairs({ "HoverOnly", "SetTipSpell", "SpellIDForName", "AttachSpellTooltip", "RefreshSpellTooltip" }) do
        FS.FrameHelpers[k] = real[k]
    end
end

-- Capture every engine run the cast bars build, with the options they passed.
__runs = {}
__loadChevron = function(path, src)
    __load(path, src)
    local create = FS.ChevronCastBar.Create
    FS.ChevronCastBar.Create = function(parent, opts)
        local run = create(parent, opts)
        __runs[#__runs + 1] = { run = run, opts = opts, parent = parent }
        local layout = run.Layout
        run.layoutCalls = 0
        run.Layout = function(self, ...) self.layoutCalls = self.layoutCalls + 1; return layout(self, ...) end
        local startCast = run.StartCast
        run.startCasts = 0
        run.StartCast = function(self, ...) self.startCasts = self.startCasts + 1; return startCast(self, ...) end
        return run
    end
end
"""


WEDGE_TGA = ADDON / "Media" / "Textures" / "tab_slant.tga"


def read_wedge_alpha() -> list[int]:
    """Alpha of media/tab_slant.tga, row-major from the TOP row (texcoord v = 0), 32 x 32.

    Reads the real file: uncompressed truecolour (type 2), 32 bpp BGRA; descriptor bit 5 says
    the origin is top-left (0x28 for this file), otherwise the rows are stored bottom-up.
    """
    data = WEDGE_TGA.read_bytes()
    id_len, cmap_type, img_type = data[0], data[1], data[2]
    width = int.from_bytes(data[12:14], "little")
    height = int.from_bytes(data[14:16], "little")
    bpp, desc = data[16], data[17]
    if (cmap_type, img_type, bpp) != (0, 2, 32) or (width, height) != (32, 32):
        sys.exit(f"{WEDGE_TGA.name}: expected a 32 x 32 uncompressed 32 bpp TGA, got type {img_type}, {bpp} bpp, {width} x {height}")
    px = data[18 + id_len:18 + id_len + width * height * 4]
    rows = [[px[(y * width + x) * 4 + 3] for x in range(width)] for y in range(height)]
    if not desc & 0x20:
        rows.reverse()
    return [a for row in rows for a in row]


def boot() -> "LuaRuntime":
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.eval("function(t) __wedge = t end")(lua.table_from(read_wedge_alpha()))
    lua.execute(CHEV.MOCK)
    lua.execute(MOCK)
    theme_src = (ADDON / "Core/Theme.lua").read_text(encoding="utf-8")
    consts = [CHEV._extract_theme_constant(theme_src, n) for n in THEME_CONSTANTS]
    lua.eval("__load_theme_constants")(lua.table_from(consts))
    lua.globals()["__helpers_source"] = (ADDON / "Core/FrameHelpers.lua").read_text(encoding="utf-8")
    lua.execute(WIRE)
    chevron = (ADDON / "Core/ChevronCastBar.lua").read_text(encoding="utf-8")
    lua.eval("__loadChevron")("Core/ChevronCastBar.lua", chevron)
    lua.eval("function(s) __castSrc = s end")(CASTBARS.read_text(encoding="utf-8"))
    return lua


CHECKS = r"""
local T = {}

local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end
local function near(a, b, tol, msg)
    if a == nil or math.abs(a - b) > (tol or 1e-6) then
        error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2)
    end
end
local function ok(v, msg) if not v then error(msg or "expected true", 2) end end

local function find(pred)
    for _, o in ipairs(__all) do if pred(o) then return o end end
end

-- A timer's text with colour escapes dropped: what the digits say, whatever their colour.
local function txt(fs)
    local s = fs._text:gsub("|c%x%x%x%x%x%x%x%x", "")
    s = s:gsub("|r", "")
    return s
end

-- A stand-in for ForeverDebugBridgeFrame as ForeverDebugBridge builds it: a 1 x 1 frame at the screen
-- centre whose effective scale is held at 1 (SetScale(1 / UIParent's scale)), with the lattice
-- of cell textures hanging off it. The lattice is w x h SCREEN units, centred (dx, dy) from the
-- screen centre; two corner cells are enough for a union. Own units = screen units.
-- w, h, dx, dy are screen units. Only the CastBars checks that it must not matter use it.
local function mkBridge(w, h, dx, dy)
    local b = CreateFrame("Frame", "ForeverDebugBridgeFrame", UIParent)
    b:SetSize(1, 1)
    b.cells = { b:CreateTexture(nil, "OVERLAY"), b:CreateTexture(nil, "OVERLAY") }
    local e = 1                                   -- ForeverDebugBridge pins its scale so a unit is a pixel
    b:SetScale(e / UIParent._scale)
    b._cx, b._cy = 683 / e, 384 / e                -- the 1 x 1 anchor: at the screen centre
    b._l, b._r, b._b, b._t = (683 - 0.5) / e, (683 + 0.5) / e, (384 - 0.5) / e, (384 + 0.5) / e
    local l, t = 683 + dx - w / 2, 384 + dy + h / 2
    local tl, br = b.cells[1], b.cells[2]
    tl._l, tl._r, tl._t, tl._b = l / e, (l + 8) / e, t / e, (t - 8) / e
    br._l, br._r, br._t, br._b = (l + w - 8) / e, (l + w) / e, (t - h + 8) / e, (t - h) / e
    _G.ForeverDebugBridgeFrame = b
    return b
end

-- Loads CastBars.lua on a screen at UI scale `opts.scale`, with an optional ForeverDebugBridgeFrame
-- (which must NOT matter), and hands back
-- the pieces the checks poke.
local function world(opts)
    opts = opts or {}
    __now = 100
    __ui(opts.scale or 1)
    _G.ForeverDebugBridgeFrame = nil
    PlayerCastingBarFrame, TargetFrameSpellBar = CreateFrame("Frame"), CreateFrame("Frame")
    local W = { bridge = opts.bridge and mkBridge(opts.bridge[1], opts.bridge[2], opts.bridge[3], opts.bridge[4]) }
    if opts.beforeLoad then opts.beforeLoad() end
    __load("Modules/CastBars/CastBars.lua", __castSrc)
    W.P, W.G = FS.playerCastBar, FS.targetCastBar      -- G = target
    ok(W.P and W.G, "the bars are exported")
    W.eventsFor = function(unit)
        return find(function(o) return o._unitEvents and o._unitEvents.UNIT_SPELLCAST_START == unit end)
    end
    function W.fire(bar, event, castID, interruptedBy)
        local f = bar.events
        f._scripts.OnEvent(f, event, bar.unit, castID, 1, interruptedBy)
    end
    function W.cast(unit, name, id, t0, secs)
        __now = t0 or 100
        __units[unit].cast = { name = name, tex = "icon", startMS = __now * 1000,
            endMS = (__now + secs) * 1000, castID = id or "C1", notInt = false }
        __units[unit].chan = nil
    end
    function W.channel(unit, name, t0, secs, spellID)
        __now = t0 or 100
        __units[unit].chan = { name = name, tex = "icon", startMS = __now * 1000,
            endMS = (__now + secs) * 1000, notInt = false, spellID = spellID }
        __units[unit].cast = nil
    end
    function W.secretCast(unit, isChannel)
        local c = { name = __SECRET_NAME, tex = "icon", startMS = __SECRET, endMS = __SECRET,
            castID = __SECRET_ID, notInt = __SECRET_BOOL, secret = true }
        if isChannel then __units[unit].chan, __units[unit].cast = c, nil else __units[unit].cast, __units[unit].chan = c, nil end
    end
    -- Runs the engine's OnUpdate and the readout ticker at clock t.
    function W.at(bar, t)
        __now = t
        local fn = bar.run.frame:GetScript("OnUpdate")
        if fn then fn(bar.run.frame, 0) end
        if bar.ticker._shown then bar.ticker._scripts.OnUpdate(bar.ticker, 0.2) end
    end
    function W.stepTo(bar, from, to)
        local t = from
        while t < to do t = math.min(to, t + 1 / 30); W.at(bar, t) end
    end
    function W.clean() eq(#__printed, 0, "no printed errors: " .. tostring(__printed[1])) end
    function W.idle(bar, msg)
        eq(bar.frame._shown, false, msg .. ": bar hidden")
        eq(bar.run:GetPhase(), "idle", msg .. ": engine idle")
        eq(bar.timer._text, "", msg .. ": timer blank")
        eq(bar.ticker._shown, false, msg .. ": ticker off")
    end
    -- Where the gap's centre is on the SCREEN, from the two bars' anchors alone.
    function W.gapCentreScreen()
        local pt, pp = W.G.frame._points.CENTER, W.P.frame._points.CENTER
        local s = UIParent._scale
        local topOfPlayer = pp.y + W.P.frame._h / 2
        local bottomOfTarget = pt.y - W.G.frame._h / 2
        return (pt.x + UIParent._cx) * s, ((topOfPlayer + bottomOfTarget) / 2 + UIParent._cy) * s,
            bottomOfTarget - topOfPlayer
    end
    return W
end

-- ---- build ---------------------------------------------------------------------

function T.both_bars_build_at_268_stacked_with_an_18_gap()
    local W = world()
    W.clean()
    for _, bar in ipairs({ W.P, W.G }) do
        eq(bar.frame._w, 268, bar.unit .. ": 268 wide at pixel scale 1")
        eq(bar.frame._h, 22, bar.unit .. ": 22 high")
        eq(bar.run.W, 174, bar.unit .. ": the run is fitted to a whole number of chevrons")
        eq(bar.run.count, 14, bar.unit .. ": 14 chevrons")
        near(bar.run.span, bar.run.W, 1e-9, bar.unit .. ": zero slack")
    end
    local pt, pp = W.G.frame._points.CENTER, W.P.frame._points.CENTER
    ok(pt.y > pp.y, "the target is on top")
    local _, _, gap = W.gapCentreScreen()
    near(gap, 18, 1e-9, "18 units between the two frames")
    eq(W.P.frame._points.CENTER.rel, UIParent, "seated on UIParent")
end

function T.build_keeps_the_blizzard_dim_and_hides_the_bars()
    local W = world()
    eq(__dimmed[1], PlayerCastingBarFrame, "player Blizzard bar dimmed")
    eq(__dimmed[2], TargetFrameSpellBar, "target Blizzard bar dimmed")
    eq(W.P.frame._shown, false, "idle: hidden"); eq(W.G.frame._shown, false)
end

function T.build_passes_the_locked_engine_options()
    local W = world()
    eq(#__runs, 2, "one run per bar")
    for i, bar in ipairs({ W.P, W.G }) do
        local o = __runs[i].opts
        eq(o.fitWidth, true, "fit to whole chevrons")
        eq(o.lockSnap, nil, "lockSnap unset: no scale pop")
        eq(o.channelFinish, nil, "the default channel finish")
        eq(bar.run.channelFinish, "drain")
        eq(o.scaleTarget, bar.frame); eq(o.alphaTarget, bar.frame)
        ok(o.flareTarget and o.flareTarget._cutOutline, "the frame outline flares at lock-in")
        local g, h = o.glowBurst, o.holdGlow
        ok(g and h and g ~= h, "dedicated burst and hold glow regions")
        near(h._alpha, 0, 1e-9, "the hold glow starts dark")
        eq(#bar.frame._groups, 0, "no animation group on the bar frame: no pop")
    end
end

function T.tabs_sit_top_right_for_the_target_and_under_left_for_the_player()
    local W = world()
    local tt = W.G.tab._points
    eq(tt.BOTTOMRIGHT.rel, W.G.frame); eq(tt.BOTTOMRIGHT.relPoint, "TOPRIGHT", "target tab: above the frame, right end")
    local pl = W.P.tab._points
    eq(pl.TOPLEFT.rel, W.P.frame); eq(pl.TOPLEFT.relPoint, "BOTTOMLEFT", "player tab: under the frame, left end")
end

function T.registers_the_unit_events_and_never_succeeded()
    local W = world()
    local want = { "UNIT_SPELLCAST_START", "UNIT_SPELLCAST_STOP", "UNIT_SPELLCAST_FAILED",
        "UNIT_SPELLCAST_INTERRUPTED", "UNIT_SPELLCAST_DELAYED", "UNIT_SPELLCAST_CHANNEL_START",
        "UNIT_SPELLCAST_CHANNEL_STOP", "UNIT_SPELLCAST_CHANNEL_UPDATE" }
    for _, bar in ipairs({ W.P, W.G }) do
        local f = W.eventsFor(bar.unit)
        ok(f, bar.unit .. ": an event frame")
        for _, e in ipairs(want) do eq(f._unitEvents[e], bar.unit, bar.unit .. " " .. e) end
        eq(f._unitEvents.UNIT_SPELLCAST_SUCCEEDED, nil, "SUCCEEDED is not a verdict")
        eq(f._events.UNIT_SPELLCAST_SUCCEEDED, nil)
        eq(f._events.PLAYER_ENTERING_WORLD, true, "a loading screen can swallow a verdict")
    end
    eq(W.eventsFor("target")._events.PLAYER_TARGET_CHANGED, true, "the target re-reads on a target change")
    eq(W.eventsFor("player")._events.PLAYER_TARGET_CHANGED, nil)
end

-- ---- placement -----------------------------------------------------------------

function T.the_stack_sits_on_the_fixed_seat_with_the_gap_centre_at_0_minus_317()
    local W = world()
    local pt, pp = W.G.frame._points.CENTER, W.P.frame._points.CENTER
    near(pt.x, 0, 1e-9, "x"); near(pp.x, 0, 1e-9)
    near(pt.y, -317 + 9 + 11, 1e-9, "target CENTER: the seat plus half the gap plus half a frame")
    near(pp.y, -317 - 9 - 11, 1e-9, "player CENTER: the seat minus half the gap minus half a frame")
end

function T.a_ui_scale_change_replaces_the_stack_and_refits_the_bars()
    local W = world()
    eq(W.P.frame._w, 268)
    -- the player moves the UI scale slider, then the events fire
    __ui(0.64)
    __fireEvent("UI_SCALE_CHANGED"); __fireEvent("DISPLAY_SIZE_CHANGED")
    near(W.G.frame._points.CENTER.x, 0, 0.5 / 0.64 + 1e-6, "still on the seat, in the new UIParent units")
    near((W.G.frame._points.CENTER.y + W.P.frame._points.CENTER.y) / 2, -317, 0.5 / 0.64 + 1e-6, "gap centre still at -317")
    ok(math.abs(W.P.frame._w - 268) > 1e-6, "the pixel pitch changed, so the fitted width did")
    near(W.P.frame._w, W.P.run.W + 94, 1e-9, "frame = fitted run + fixed chrome")
    near(W.G.frame._w, W.G.run.W + 94, 1e-9)
    W.clean()
    -- and back
    __ui(1)
    __fireEvent("UI_SCALE_CHANGED")
    eq(W.P.frame._w, 268, "back to 268 at scale 1")
    near(W.G.frame._points.CENTER.y, -317 + 9 + 11, 1e-9)
end

function T.an_engine_relayout_alone_re_places_the_stack()
    -- The scale changed and nobody fired our events: the engine notices at the next StartCast /
    -- OnShow (RefreshPixels) and its onLayout is the only trigger the stack gets.
    local W = world()
    __ui(0.64)
    ok(W.P.run:RefreshPixels(), "the engine re-laid out")
    near(W.G.frame._points.CENTER.x, 0, 0.5 / 0.64 + 1e-6, "re-placed from onLayout")
    local edgePx = (UIParent._cx + W.G.frame._points.CENTER.x - W.G.frame._w / 2) * 0.64
    near(edgePx, math.floor(edgePx + 0.5), 1e-6, "on the NEW pixel grid (no second pass needed)")
    near(W.P.frame._w, W.P.run.W + 94, 1e-9, "and re-sized")
end

-- ---- player casts --------------------------------------------------------------

function T.player_cast_start_succeed_and_lock_in_with_no_pop()
    local W = world()
    local P = W.P
    W.cast("player", "Shadow Bolt", "C1", 100, 1.5)
    W.fire(P, "UNIT_SPELLCAST_START")
    eq(P.frame._shown, true); eq(P.run:GetPhase(), "cast")
    eq(P.icon._texture, "icon", "spell icon")
    eq(P.tabName._text, "SHADOW BOLT", "the tab names the spell in capitals")
    eq(txt(P.timer), "0.0 / 1.5", "the real cast length")
    W.at(P, 100.9)
    eq(txt(P.timer), "0.9 / 1.5", "elapsed over the cast length")
    W.stepTo(P, 100.9, 101.5)
    __units.player.cast = nil
    W.fire(P, "UNIT_SPELLCAST_STOP", "C1")
    eq(P.run:GetPhase(), "hold", "a matching STOP calls Succeed")
    eq(P.run.burst._groups[1].plays, 1, "the chevron burst plays")
    eq(P.run.glowBurst._groups[1].plays, 1, "the glow burst plays")
    eq(txt(P.timer), "1.5 / 1.5", "the readout settles at the full length")
    eq(P.frame._shown, true, "the bar stays up through the hold")
    eq(P.frame._scale, nil, "the bar frame is never scaled: no pop")
    eq(#P.frame._groups, 0, "no scale animation exists")
    W.stepTo(P, 101.5, 102.6)
    eq(P.run:GetPhase(), "fade")
    W.at(P, 102.81)
    W.idle(P, "after the lock-in")
    W.clean()
end

function T.a_stop_for_another_castid_leaves_the_cast_alone()
    local W = world()
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5)
    W.fire(W.P, "UNIT_SPELLCAST_START")
    W.stepTo(W.P, 100, 101)
    W.fire(W.P, "UNIT_SPELLCAST_STOP", "OTHER")
    W.fire(W.P, "UNIT_SPELLCAST_FAILED", "OTHER")
    eq(W.P.run:GetPhase(), "cast", "a different castID touches nothing")
    W.clean()
end

function T.player_interrupt_runs_the_outage_then_hides()
    local W = world()
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5)
    W.fire(W.P, "UNIT_SPELLCAST_START")
    W.stepTo(W.P, 100, 101)
    __units.player.cast = nil
    W.fire(W.P, "UNIT_SPELLCAST_INTERRUPTED", "C1")
    eq(W.P.run:GetPhase(), "intr"); eq(W.P.frame._shown, true, "stays up for the outage")
    eq(txt(W.P.timer), "1.0 / 2.5", "the readout is held where it was cut")
    W.at(W.P, 102.01)
    W.idle(W.P, "after the outage")
    W.clean()
end

function T.channel_natural_end_plays_the_finish()
    local W = world()
    local P = W.P
    W.channel("player", "Drain Life", 100, 5)
    W.fire(P, "UNIT_SPELLCAST_CHANNEL_START")
    eq(P.run:GetPhase(), "cast"); eq(P.run.channel, true)
    eq(txt(P.timer), "5.0 / 5.0", "a channel counts down over its length")
    W.stepTo(P, 100, 105)
    __units.player.chan = nil
    W.fire(P, "UNIT_SPELLCAST_CHANNEL_STOP", nil, nil)
    eq(P.run:GetPhase(), "hold", "a stop at the scheduled end is natural: the finish plays")
    eq(P.run.chanMode, "drain", "the default channel finish")
    eq(P.frame._shown, true, "the bar stays up while the finish plays")
    eq(txt(P.timer), "0.0 / 5.0")
    W.stepTo(P, 105, 106.2)
    W.idle(P, "after the finish")
    W.clean()
end

function T.channel_clip_gets_the_plain_stop()
    local W = world()
    local P = W.P
    W.channel("player", "Mind Flay", 100, 3)
    W.fire(P, "UNIT_SPELLCAST_CHANNEL_START")
    W.stepTo(P, 100, 101.2)
    __units.player.chan = nil
    W.fire(P, "UNIT_SPELLCAST_CHANNEL_STOP", nil, nil)
    W.idle(P, "an early stop is a clip")
    eq(P.run.chanMode, nil, "no finish was played")
    eq(P.run.burst._groups[1].plays, 0)
    W.clean()
end

function T.a_kicked_channel_runs_the_outage_and_a_secret_stop_is_quiet()
    local W = world()
    W.channel("player", "Mind Flay", 100, 3)
    W.fire(W.P, "UNIT_SPELLCAST_CHANNEL_START")
    W.stepTo(W.P, 100, 101)
    __units.player.chan = nil
    W.fire(W.P, "UNIT_SPELLCAST_CHANNEL_STOP", nil, "Creature-1")
    eq(W.P.run:GetPhase(), "intr", "interruptedBy: outage")
    W.at(W.P, 102.01); W.idle(W.P, "after the outage")
    W.channel("player", "Mind Flay", 110, 3)
    W.fire(W.P, "UNIT_SPELLCAST_CHANNEL_START")
    W.stepTo(W.P, 110, 111)
    __units.player.chan = nil
    ok(pcall(W.fire, W.P, "UNIT_SPELLCAST_CHANNEL_STOP", nil, __SECRET_ID), "threw on a secret interruptedBy")
    W.idle(W.P, "the quiet outcome is the safer misfire")
    W.clean()
end

function T.delayed_retimes_the_cast_without_restarting_it()
    local W = world()
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5)
    W.fire(W.P, "UNIT_SPELLCAST_START")
    W.stepTo(W.P, 100, 101)
    eq(W.P.run.startCasts, 1)
    __units.player.cast.endMS = 103.0 * 1000
    W.fire(W.P, "UNIT_SPELLCAST_DELAYED")
    eq(W.P.run:GetPhase(), "cast")
    eq(W.P.run.startCasts, 1, "DELAYED re-times in place: StartCast would reset every ignite")
    W.at(W.P, 101)
    eq(txt(W.P.timer), "1.0 / 3.0", "the new length shows")
    W.channel("player", "Mind Flay", 110, 3)
    W.fire(W.P, "UNIT_SPELLCAST_CHANNEL_START")
    eq(W.P.run.startCasts, 2)
    __units.player.chan.endMS = 114 * 1000
    W.fire(W.P, "UNIT_SPELLCAST_CHANNEL_UPDATE")
    eq(W.P.run.startCasts, 2, "CHANNEL_UPDATE re-times in place too")
    W.clean()
end

-- ---- tick counter ---------------------------------------------------------------

function T.drain_soul_counts_n_of_5_over_15_seconds()
    local W = world()
    local P = W.P
    W.channel("player", "Drain Soul", 100, 15)
    W.fire(P, "UNIT_SPELLCAST_CHANNEL_START")
    eq(P.tabTicks._shown, true, "the counter is on the tab")
    eq(P.tabName._text, "DRAIN SOUL")
    eq(P.tabTicks._text, "0/5")
    W.at(P, 103.4); eq(P.tabTicks._text, "1/5", "first tick lands at 3s")
    eq(txt(P.timer), "11.6 / 15", "a 15s channel drops the decimal on its total to fit the column")
    W.at(P, 109); eq(P.tabTicks._text, "3/5")
    W.at(P, 115); eq(P.tabTicks._text, "5/5")
    eq(P.tabTicks._textColor[1], FS.Theme.COLOR_TEXT_PARCHMENT[1], "parchment, not pink")
    W.clean()
end

function T.mind_flay_shows_cut_in_pink_once_clipAfter_ticks_have_landed()
    local W = world()
    local P = W.P
    W.channel("player", "Mind Flay", 100, 3)
    W.fire(P, "UNIT_SPELLCAST_CHANNEL_START")
    W.at(P, 101.4); eq(P.tabTicks._text, "1/3")
    W.at(P, 101.95); eq(P.tabTicks._text, "1/3", "2 ticks have not landed yet at 1.95s")
    W.at(P, 102.1); eq(P.tabTicks._text, "CUT", "2 of 3 landed: time to cut")
    local c = FS.Theme.COLOR_HEALTH
    eq(P.tabTicks._textColor[1], c[1], "pink"); eq(P.tabTicks._textColor[2], c[2])
    W.clean()
end

function T.drain_life_counts_n_of_5_over_5_seconds()
    local W = world()
    W.channel("player", "Drain Life", 100, 5)
    W.fire(W.P, "UNIT_SPELLCAST_CHANNEL_START")
    W.at(W.P, 102.2); eq(W.P.tabTicks._text, "2/5")
    W.at(W.P, 104.9); eq(W.P.tabTicks._text, "4/5")
end

function T.spells_without_ticks_and_the_target_show_no_counter()
    local W = world()
    for _, name in ipairs({ "Health Funnel", "Shoot" }) do
        W.channel("player", name, 100, 5)
        W.fire(W.P, "UNIT_SPELLCAST_CHANNEL_START")
        eq(W.P.tabTicks._shown, false, name .. ": no counter")
        eq(W.P.tabTicks._text, "", name)
        W.at(W.P, 101)
        eq(W.P.tabTicks._text, "")
    end
    W.channel("target", "Mind Flay", 100, 3)
    W.fire(W.G, "UNIT_SPELLCAST_CHANNEL_START")
    eq(W.G.tabTicks._shown, false, "the target has no counter")
    W.clean()
end

-- ---- target and secrets ---------------------------------------------------------

function T.target_cast_with_plain_info_runs_on_the_engine()
    local W = world()
    W.cast("target", "Frostbolt", "T1", 100, 3)
    W.fire(W.G, "UNIT_SPELLCAST_START")
    eq(W.G.run:GetPhase(), "cast"); eq(W.G.mode, "run")
    eq(W.G.tabName._text, "FROSTBOLT")
    eq(txt(W.G.timer), "0.0 / 3.0")
    W.clean()
end

function T.target_with_secret_cast_info_does_not_throw_or_compare_a_secret()
    local W = world()
    local G = W.G
    W.secretCast("target", false)
    ok(pcall(W.fire, G, "UNIT_SPELLCAST_START"), "START threw on secret cast info")
    W.clean()
    eq(G.frame._shown, true, "the bar shows")
    eq(G.mode, "strip", "secret times: the engine-timed strip takes over")
    eq(G.run:IsBusy(), false, "the engine refused the secret times and stays idle")
    eq(G.strip._shown, true); ok(G.strip._timer, "the duration object went to SetTimerDuration")
    ok(rawequal(G.tabName._text, __SECRET_NAME), "the secret name went to SetText untouched")
    ok(rawequal(G.shield._fromBool, __SECRET_BOOL), "the interruptible flag went to SetAlphaFromBoolean untouched")
    eq(G.timer._secretText, true, "the secret numbers went straight into SetFormattedText")
    ok(pcall(G.ticker._scripts.OnUpdate, G.ticker, 0.2), "the readout ticker threw")
    ok(pcall(W.fire, G, "UNIT_SPELLCAST_DELAYED"), "DELAYED threw")
    ok(pcall(W.fire, G, "UNIT_SPELLCAST_FAILED", __SECRET_ID), "FAILED threw on a secret castID")
    eq(G.frame._shown, true, "a secret castID with the cast still reading as present: unknown, not gone")
    __units.target.cast = nil
    ok(pcall(W.fire, G, "UNIT_SPELLCAST_STOP", __SECRET_ID), "STOP threw on a secret castID")
    W.clean()
    eq(G.frame._shown, false, "the cast is plainly gone: the verdict ends the strip bar")
    W.idle(G, "after the strip verdict")
    eq(G.strip._shown, false)
end

function T.target_secret_channel_and_secret_interrupted_by_do_not_throw()
    local W = world()
    W.secretCast("target", true)
    ok(pcall(W.fire, W.G, "UNIT_SPELLCAST_CHANNEL_START"), "CHANNEL_START threw")
    eq(W.G.mode, "strip"); eq(W.G.tabTicks._shown, false)
    ok(pcall(W.fire, W.G, "UNIT_SPELLCAST_CHANNEL_STOP", nil, __SECRET_ID), "CHANNEL_STOP threw")
    W.idle(W.G, "channel stop")
    W.clean()
end

function T.target_with_a_secret_castid_but_plain_times_still_locks_in_safely()
    local W = world()
    W.cast("target", "Frostbolt", __SECRET_ID, 100, 3)
    W.fire(W.G, "UNIT_SPELLCAST_START")
    eq(W.G.mode, "run")
    W.stepTo(W.G, 100, 103)
    __units.target.cast = nil
    ok(pcall(W.fire, W.G, "UNIT_SPELLCAST_STOP", __SECRET_ID), "STOP threw on a secret castID")
    eq(W.G.run:GetPhase(), "hold", "nil match at a complete cast succeeds")
    W.clean()
end

function T.a_target_change_drops_the_old_cast_and_rereads()
    local W = world()
    W.cast("target", "Frostbolt", "T1", 100, 3)
    W.fire(W.G, "UNIT_SPELLCAST_START")
    W.stepTo(W.G, 100, 101)
    __units.target.cast = nil
    __fireEvent("PLAYER_TARGET_CHANGED")
    W.idle(W.G, "the new target is not casting")
    W.cast("target", "Fear", "T2", 101, 2)
    __fireEvent("PLAYER_TARGET_CHANGED")
    eq(W.G.run:GetPhase(), "cast", "the new target is already mid cast")
    eq(W.G.tabName._text, "FEAR")
    W.clean()
end

-- ---- review fixes ----------------------------------------------------------------

-- One physical pixel in UIParent units (the mock's screen is 768 high: a pixel is 1 screen unit).
local function pxU() return 1 / UIParent._scale end
local function onGrid(v, px, msg)
    local q = v / px
    if math.abs(q - math.floor(q + 0.5)) > 1e-6 then error((msg or "off the pixel grid") .. ": " .. v .. " / " .. px .. " = " .. q, 2) end
end

-- MED-1: the tab is the mockup's trapezoid, 5 units of slant at each end.
function T.the_tab_is_a_trapezoid_with_a_5_unit_slant_on_each_end()
    local W = world()
    W.cast("target", "Frostbolt", "T1", 100, 3)
    W.fire(W.G, "UNIT_SPELLCAST_START")
    W.cast("player", "Frostbolt", "P1", 100, 3)
    W.fire(W.P, "UNIT_SPELLCAST_START")
    local dx = math.sqrt(1 + (5 / 15) ^ 2)
    for _, bar in ipairs({ W.G, W.P }) do
        local u = bar.unit
        local pl = bar.tabParts
        ok(pl, u .. ": the tab exposes its parts")
        eq(bar.tab._w, 54 + 2 * 6 + 2 * 5, u .. ": body + 2 x pad + 2 x slant")
        eq(bar.tab._h, 15, u .. ": 15 high")
        -- the caps are the shared slant texture, 5 wide, one per end
        ok(pl.capL._texture and pl.capL._texture:find("tab_slant.tga", 1, true), u .. ": the shared slant texture")
        eq(pl.capR._texture, pl.capL._texture)
        eq(pl.capL._w, 5, u .. ": left cap 5 wide"); eq(pl.capR._w, 5, u .. ": right cap 5 wide")
        eq(pl.edgeL._w, 5, u .. ": the stroke wedge is the same size"); eq(pl.edgeR._w, 5)
        -- the stroke wedge sits at the tab edge, the fill wedge one stroke inward of it
        near(pl.capL._points.TOPLEFT.x, dx, 1e-9, u .. ": left fill wedge inset by one stroke")
        near(pl.capR._points.TOPRIGHT.x, -dx, 1e-9, u .. ": right fill wedge inset by one stroke")
        eq(pl.edgeL._points.TOPLEFT.x, 0); eq(pl.edgeR._points.TOPRIGHT.x, 0)
        -- the body spans between the two fill wedges, so nothing is covered twice
        near(pl.body._points.TOPLEFT.x, 5 + dx, 1e-9, u .. ": body starts where the left wedge ends")
        near(pl.body._points.BOTTOMRIGHT.x, -(5 + dx), 1e-9)
        -- the name starts after the slant and the padding
        eq(bar.tabName._points.LEFT.x, 5 + 6, u .. ": name after slant + pad")
        -- the free edge: a 1 high stroke between the two slants
        eq(pl.line._h, 1)
        eq(pl.line._points[bar.isTarget and "TOPLEFT" or "BOTTOMLEFT"].x, 5, u .. ": free edge starts at the slant")
        eq(pl.line._points[bar.isTarget and "TOPRIGHT" or "BOTTOMRIGHT"].x, -5)
        local c = FS.Theme.COLOR_BORDER
        near(pl.line._colorTexture[1], c[1], 1e-9, u .. ": stroke colour")
    end
end

-- The shape, not the flip strings: sample the REAL tab_slant.tga alpha through each piece's
-- texcoords, as the client maps them onto the piece's rect, and read off where the opaque run
-- starts and ends at the row on the frame edge and the row on the free edge. A trapezoid is wide
-- at the frame edge and narrow at the free edge for BOTH caps, the left cap's outer edge leaning
-- out toward the frame edge and the right cap's mirrored. The target's tab sits above its frame
-- (frame edge = bottom of the tab), the player's below (frame edge = top).
local function wedgeAlpha(u, v)
    local x = math.min(31, math.max(0, math.floor(u * 32)))
    local y = math.min(31, math.max(0, math.floor(v * 32)))
    return __wedge[y * 32 + x + 1]
end

-- First and last opaque sample across the piece at screen row fraction sy (0 = top, 1 = bottom),
-- as fractions of the piece's width (0 = its left side). nil, nil when the row is empty.
local function opaqueSpan(piece, sy)
    local l, r, t, b = piece._tc[1], piece._tc[2], piece._tc[3], piece._tc[4]
    local N, lo, hi = 320, nil, nil
    for i = 0, N - 1 do
        local sx = (i + 0.5) / N
        if wedgeAlpha(l + (r - l) * sx, t + (b - t) * sy) > 127 then
            lo = lo or sx
            hi = sx
        end
    end
    return lo, hi
end

function T.the_tab_wedges_are_wide_at_the_frame_edge_and_narrow_at_the_free_edge()
    local W = world()
    local cases = 0
    for _, bar in ipairs({ W.G, W.P }) do
        local u = bar.unit
        local frameSy = bar.isTarget and 63 / 64 or 1 / 64
        local freeSy = bar.isTarget and 1 / 64 or 63 / 64
        for _, name in ipairs({ "capL", "edgeL", "capR", "edgeR" }) do
            local piece = bar.tabParts[name]
            local left = name:sub(-1) == "L"
            local tc = piece._tc[1] .. piece._tc[2] .. piece._tc[3] .. piece._tc[4]
            local what = u .. " " .. name .. " (texcoords " .. tc .. ")"
            local fLo, fHi = opaqueSpan(piece, frameSy)
            local eLo, eHi = opaqueSpan(piece, freeSy)
            ok(fLo and eLo, what .. ": opaque at both edge rows")
            ok((fHi - fLo) > (eHi - eLo) + 0.5, what .. ": wider at the frame edge (" .. (fHi - fLo) .. ") than at the free edge (" .. (eHi - eLo) .. ")")
            if left then
                ok(fHi > 0.95 and eHi > 0.95, what .. ": the solid side is the inner (right) side at both rows")
                ok(fLo < eLo - 0.5, what .. ": the outer edge leans outward toward the frame edge (" .. fLo .. " vs " .. eLo .. ")")
            else
                ok(fLo < 0.05 and eLo < 0.05, what .. ": the solid side is the inner (left) side at both rows")
                ok(fHi > eHi + 0.5, what .. ": the outer edge leans outward toward the frame edge (" .. fHi .. " vs " .. eHi .. ")")
            end
            cases = cases + 1
        end
    end
    eq(cases, 8, "target and player, fill and stroke, left and right")
end

function T.a_ticking_tab_widens_by_the_counter_and_keeps_the_slants()
    local W = world()
    W.channel("player", "Drain Soul", 100, 15)
    W.fire(W.P, "UNIT_SPELLCAST_CHANNEL_START")
    -- "DRAIN SOUL" 10 chars x 6, gap 4, "5/5" 3 chars x 6, 2 x pad, 2 x slant
    eq(W.P.tab._w, 60 + 4 + 18 + 12 + 10)
end

-- MED-2: a strip bar has a safety net on its 0.1s ticker.
function T.the_strip_goes_idle_when_the_cast_is_plainly_gone_and_never_on_a_secret()
    local W = world()
    local G = W.G
    W.secretCast("target", false)
    W.fire(G, "UNIT_SPELLCAST_START")
    eq(G.mode, "strip")
    G.ticker._scripts.OnUpdate(G.ticker, 0.2)
    eq(G.frame._shown, true, "a secret name is unknown, not gone")
    __units.target.cast = nil                          -- the end event was lost
    G.ticker._scripts.OnUpdate(G.ticker, 0.2)
    W.idle(G, "no cast or channel reads back")
    eq(G.strip._shown, false)
    -- a channel the same way
    W.secretCast("target", true)
    W.fire(G, "UNIT_SPELLCAST_CHANNEL_START")
    eq(G.mode, "strip")
    G.ticker._scripts.OnUpdate(G.ticker, 0.2)
    eq(G.frame._shown, true, "a secret channel name is not gone")
    __units.target.chan = nil
    G.ticker._scripts.OnUpdate(G.ticker, 0.2)
    W.idle(G, "the channel is gone")
    -- the target vanished (dead, untargeted without the event)
    W.secretCast("target", false)
    W.fire(G, "UNIT_SPELLCAST_START")
    __units.target.exists = false
    G.ticker._scripts.OnUpdate(G.ticker, 0.2)
    W.idle(G, "the unit is plainly gone")
    W.clean()
end

-- LOW-1: our bars first, Blizzard's dimmed only after both builds succeeded.
function T.a_failed_build_leaves_blizzards_bars_alone()
    __now = 100
    PlayerCastingBarFrame, TargetFrameSpellBar = CreateFrame("Frame"), CreateFrame("Frame")
    __failOutlineAt = 2                                -- the target bar's build throws
    local loaded = pcall(__load, "Modules/CastBars/CastBars.lua", __castSrc)
    eq(loaded, false, "the build error surfaces")
    eq(#__dimmed, 0, "Blizzard's bars are still up")
end

-- LOW-2: the timer column comes from the font.
function T.the_timer_column_is_measured_once_from_the_sample_text()
    __charW = 10                                       -- "0.0 / 0.0" is 90 wide here, not 54
    local W = world()
    -- column = 90 + 2 padding; chrome = 27 + 4 + 92 + 2 + 5 = 130; the run is asked for 260 - 130
    eq(__runs[1].run.requestedW, 130, "the run request follows the measured column")
    eq(W.P.frame._w, W.P.run.W + 130, "frame = fitted run + measured chrome")
    eq(W.G.frame._w, W.P.frame._w, "both bars of the stack share it")
end

function T.an_unmeasurable_timer_column_falls_back_to_56()
    for _, v in ipairs({ "throw", 0 }) do
        __charW = v
        local W = world()
        eq(__runs[#__runs - 1].run.requestedW, 166, "the 260 - 94 request")
        eq(W.P.frame._w, 268, "the fallback column gives the known 268")
    end
end

function T.the_total_is_muted_on_the_plain_path()
    local W = world()
    W.cast("player", "Shadow Bolt", "C1", 100, 1.5)
    W.fire(W.P, "UNIT_SPELLCAST_START")
    eq(W.P.timer._text, "0.0|cff9a8fbd / 1.5|r", "digits in the text colour, ' / total' muted")
    W.channel("player", "Drain Soul", 100, 15)
    W.fire(W.P, "UNIT_SPELLCAST_CHANNEL_START")
    eq(W.P.timer._text, "15.0|cff9a8fbd / 15|r")
end

function T.the_strip_total_drops_the_decimal_from_10s_and_stays_one_colour()
    local W = world()
    W.secretCast("target", false)
    __units.target.cast.dur = { el = 3.2, rem = 11.8, total = 15 }
    W.fire(W.G, "UNIT_SPELLCAST_START")
    eq(W.G.mode, "strip")
    eq(W.G.timer._text, "3.2 / 15", "a plain total of 10s or more has no decimal; no colour codes on a strip")
    __units.target.cast.dur = { el = 1.2, rem = 1.8, total = 3 }
    W.fire(W.G, "UNIT_SPELLCAST_DELAYED")
    eq(W.G.timer._text, "1.2 / 3.0", "a short cast keeps its decimal")
    W.secretCast("target", false)
    W.fire(W.G, "UNIT_SPELLCAST_START")
    eq(W.G.timer._secretText, true, "a secret total still goes through untouched")
end

-- LOW-3 (deferred display): the idle API the HUD will drive.
function T.the_idle_api_shows_a_dim_row_with_a_hint_and_is_off_by_default()
    local W = world()
    local API = FS.CastBars
    ok(API and API.SetIdleHint and API.SetIdleVisible, "FS.CastBars.SetIdleHint / SetIdleVisible exist")
    eq(W.P.frame._shown, false, "no idle row by default"); eq(W.G.frame._shown, false)
    API.SetIdleHint("player", "Shadow Bolt")
    eq(W.P.frame._shown, false, "a hint alone shows nothing")
    API.SetIdleVisible(true)
    for _, bar in ipairs({ W.P, W.G }) do
        eq(bar.frame._shown, true, bar.unit .. ": idle row up")
        eq(bar.run.frame._shown, true); eq(bar.run:GetPhase(), "idle")
        near(bar.run.segs[1].dim._vc[4], 0.35, 1e-9, bar.unit .. ": unlit chevrons at the idle alpha")
        eq(bar.strip._shown, false); eq(bar.timer._text, ""); eq(bar.ticker._shown, false)
    end
    eq(W.P.tab._shown, true); eq(W.P.tabName._text, "SHADOW BOLT", "the hint names the tab")
    eq(W.P.tabTicks._shown, false)
    eq(W.G.tab._shown, false, "no hint, no tab")
    API.SetIdleHint("target", nil); API.SetIdleHint("player", nil)
    eq(W.P.tab._shown, false, "clearing the hint hides the tab")
    API.SetIdleHint("player", "Mind Blast")
    eq(W.P.tabName._text, "MIND BLAST")
    -- a cast replaces the row and the row comes back after the lock-in
    W.cast("player", "Shadow Bolt", "C1", 100, 1.5)
    W.fire(W.P, "UNIT_SPELLCAST_START")
    eq(W.P.tabName._text, "SHADOW BOLT"); eq(W.P.run:GetPhase(), "cast")
    W.stepTo(W.P, 100, 101.5)
    __units.player.cast = nil
    W.fire(W.P, "UNIT_SPELLCAST_STOP", "C1")
    W.stepTo(W.P, 101.5, 103)
    eq(W.P.frame._shown, true, "back to the idle row, not hidden")
    eq(W.P.run:GetPhase(), "idle"); eq(W.P.tabName._text, "MIND BLAST", "the hint is back on the tab")
    eq(W.P.timer._text, "")
    -- off again
    API.SetIdleVisible(false)
    eq(W.P.frame._shown, false); eq(W.G.frame._shown, false)
    -- turning it on in the middle of a cast leaves the cast alone
    W.cast("player", "Shadow Bolt", "C2", 110, 2)
    W.fire(W.P, "UNIT_SPELLCAST_START")
    API.SetIdleVisible(true)
    eq(W.P.run:GetPhase(), "cast"); eq(W.P.tabName._text, "SHADOW BOLT")
    W.clean()
end

-- The HUD's out-of-combat look: .hud-stack.ooc .bar-host { opacity: .55 } on the resting row only.
function T.rest_alpha_dims_the_idle_row_only_and_changes_nothing_until_called()
    local W = world()
    local API = FS.CastBars
    ok(type(API.SetRestAlpha) == "function", "FS.CastBars.SetRestAlpha exists")
    local function a(bar) return bar.frame._alpha or 1 end
    API.SetIdleVisible(true)
    eq(a(W.P), 1, "default: the idle row is at full alpha, behaviour unchanged"); eq(a(W.G), 1)
    eq(API.SetRestAlpha(0.55), true, "a plain number is accepted")
    near(a(W.P), 0.55, 1e-9, "the idle row takes the rest alpha"); near(a(W.G), 0.55, 1e-9)
    -- never during an active cast
    W.cast("player", "Shadow Bolt", "C1", 100, 1.5)
    W.fire(W.P, "UNIT_SPELLCAST_START")
    eq(a(W.P), 1, "a running cast is at full alpha")
    near(a(W.G), 0.55, 1e-9, "the other bar keeps resting")
    W.stepTo(W.P, 100, 101.5)
    eq(a(W.P), 1, "still full alpha at the end of the cast")
    __units.player.cast = nil
    W.fire(W.P, "UNIT_SPELLCAST_STOP", "C1")
    W.stepTo(W.P, 101.5, 103)
    eq(W.P.run:GetPhase(), "idle")
    near(a(W.P), 0.55, 1e-9, "back to the rest alpha after the lock-in")
    -- a secret-timed cast runs the strip path: full alpha during, rest alpha after
    W.secretCast("target", false)
    W.fire(W.G, "UNIT_SPELLCAST_START")
    eq(a(W.G), 1, "the strip path is at full alpha")
    __units.target.cast = nil
    W.fire(W.G, "UNIT_SPELLCAST_STOP", __SECRET_ID)
    W.at(W.G, 105)
    near(a(W.G), 0.55, 1e-9, "the strip bar rests again")
    -- a later cast after resting starts at full alpha (the engine skips a write it believes redundant)
    W.cast("player", "Mind Blast", "C3", 120, 1.5)
    W.fire(W.P, "UNIT_SPELLCAST_START")
    eq(a(W.P), 1, "the next cast is at full alpha")
    W.stepTo(W.P, 120, 121.5)
    __units.player.cast = nil
    W.fire(W.P, "UNIT_SPELLCAST_STOP", "C3")
    W.stepTo(W.P, 121.5, 123)
    -- bad values change nothing; 1 puts it back; clearing the idle row restores full alpha
    eq(API.SetRestAlpha(__SECRET), false, "a secret is refused"); eq(API.SetRestAlpha("x"), false); eq(API.SetRestAlpha(0 / 0), false)
    near(a(W.P), 0.55, 1e-9, "refused values change nothing")
    API.SetRestAlpha(1)
    eq(a(W.P), 1, "1 restores the default look"); eq(a(W.G), 1)
    API.SetRestAlpha(0.55)
    API.SetIdleVisible(false)
    eq(W.P.frame._shown, false); eq(a(W.P), 1, "a hidden row is left at full alpha")
    API.SetIdleVisible(true)
    near(a(W.P), 0.55, 1e-9, "the setting survives the idle row being toggled")
    W.clean()
end

-- SetRestAlpha's `S.mode == nil` guard: a value set DURING a cast must not dim the running bar.
function T.a_rest_alpha_set_mid_cast_leaves_the_running_cast_alone_and_lands_when_it_ends()
    local W = world()
    local API = FS.CastBars
    local function a(bar) return bar.frame._alpha or 1 end
    API.SetIdleVisible(true)
    W.cast("player", "Shadow Bolt", "C1", 100, 1.5)
    W.fire(W.P, "UNIT_SPELLCAST_START")
    eq(W.P.run:GetPhase(), "cast", "the player bar is casting")
    eq(API.SetRestAlpha(0.55), true, "a plain number is accepted mid cast")
    eq(a(W.P), 1, "the running cast stays at full alpha")
    near(a(W.G), 0.55, 1e-9, "the idle bar takes it at once")
    W.stepTo(W.P, 100, 101.5)
    eq(a(W.P), 1, "still full alpha at the end of the cast")
    __units.player.cast = nil
    W.fire(W.P, "UNIT_SPELLCAST_STOP", "C1")
    W.stepTo(W.P, 101.5, 103)
    eq(W.P.run:GetPhase(), "idle", "the bar went idle")
    near(a(W.P), 0.55, 1e-9, "the rest alpha lands once the bar is idle")
    W.clean()
end

function T.entering_the_world_resets_a_bar_that_missed_its_verdict()
    local W = world()
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5)
    W.fire(W.P, "UNIT_SPELLCAST_START")
    W.stepTo(W.P, 100, 101)
    __units.player.cast = nil                          -- the loading screen swallowed the STOP
    __fireEvent("PLAYER_ENTERING_WORLD")
    W.idle(W.P, "reset by PLAYER_ENTERING_WORLD")
    -- and a cast that is still going is picked up again
    W.cast("player", "Shadow Bolt", "C2", 110, 2.5)
    __fireEvent("PLAYER_ENTERING_WORLD")
    eq(W.P.run:GetPhase(), "cast"); eq(W.P.frame._shown, true, "re-read")
    -- and a verdict that was playing is cut
    __units.player.cast = nil
    W.fire(W.P, "UNIT_SPELLCAST_STOP", "C2")
    eq(W.P.run:GetPhase(), "hold")
    __fireEvent("PLAYER_ENTERING_WORLD")
    W.idle(W.P, "the hold is dropped too")
    W.clean()
end

function T.a_run_mode_stop_with_a_secret_castid_after_the_cast_is_gone_goes_idle()
    local W = world()
    W.cast("target", "Frostbolt", __SECRET_ID, 100, 3)
    W.fire(W.G, "UNIT_SPELLCAST_START")
    eq(W.G.mode, "run")
    W.stepTo(W.G, 100, 101)                            -- not complete: the safe branch is "gone"
    ok(pcall(W.fire, W.G, "UNIT_SPELLCAST_STOP", __SECRET_ID), "threw")
    eq(W.G.run:GetPhase(), "cast", "the cast still reads back: unknown, left alone")
    __units.target.cast = nil
    ok(pcall(W.fire, W.G, "UNIT_SPELLCAST_STOP", __SECRET_ID), "threw")
    W.idle(W.G, "plainly gone: idle with no verdict")
    W.clean()
end

function T.an_interrupt_for_another_castid_is_ignored()
    local W = world()
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5)
    W.fire(W.P, "UNIT_SPELLCAST_START")
    W.stepTo(W.P, 100, 101)
    W.fire(W.P, "UNIT_SPELLCAST_INTERRUPTED", "OTHER")
    eq(W.P.run:GetPhase(), "cast", "a mismatched castID touches nothing")
    W.fire(W.P, "UNIT_SPELLCAST_INTERRUPTED", "C1")
    eq(W.P.run:GetPhase(), "intr", "the matching one interrupts")
    -- the strip: a plain castID with secret times
    W.secretCast("target", false)
    __units.target.cast.castID = "T1"
    W.fire(W.G, "UNIT_SPELLCAST_START")
    eq(W.G.mode, "strip")
    W.fire(W.G, "UNIT_SPELLCAST_INTERRUPTED", "OTHER")
    eq(W.G.mode, "strip", "the strip ignores a mismatch too"); eq(W.G.frame._shown, true)
    W.fire(W.G, "UNIT_SPELLCAST_INTERRUPTED", "T1")
    W.idle(W.G, "the matching interrupt ends the strip")
end

function T.cast_events_during_a_channel_are_ignored()
    local W = world()
    W.channel("player", "Mind Flay", 100, 3)
    W.fire(W.P, "UNIT_SPELLCAST_CHANNEL_START")
    W.stepTo(W.P, 100, 101)
    for _, e in ipairs({ "UNIT_SPELLCAST_STOP", "UNIT_SPELLCAST_FAILED", "UNIT_SPELLCAST_INTERRUPTED" }) do
        W.fire(W.P, e, "C9")
        eq(W.P.run:GetPhase(), "cast", e .. " during a channel is for another cast")
        eq(W.P.frame._shown, true)
    end
    W.secretCast("target", true)
    W.fire(W.G, "UNIT_SPELLCAST_CHANNEL_START")
    eq(W.G.mode, "strip")
    for _, e in ipairs({ "UNIT_SPELLCAST_STOP", "UNIT_SPELLCAST_FAILED", "UNIT_SPELLCAST_INTERRUPTED" }) do
        ok(pcall(W.fire, W.G, e, __SECRET_ID), e)
        eq(W.G.mode, "strip", e .. " during a strip channel is ignored")
    end
    W.clean()
end

function T.the_strip_tile_follows_the_engine_pitch()
    local W = world()
    local tile = FS.Theme.CAST_CHEVRON_STRIP_TILE_W
    W.secretCast("target", false)
    W.fire(W.G, "UNIT_SPELLCAST_START")
    near(W.G.strip._scale, 2 * W.G.run.pitch / tile, 1e-9, "one tile = two engine pitches")
    local before = W.G.strip._scale
    __ui(0.64)
    ok(W.G.run:RefreshPixels(), "relaid out")
    ok(math.abs(W.G.strip._scale - before) > 1e-6, "the pitch changed")
    near(W.G.strip._scale, 2 * W.G.run.pitch / tile, 1e-9, "re-scaled from onLayout")
end

-- The stack sits on whole physical pixels, and the engine is re-laid out once.
function T.the_fixed_seat_lands_on_whole_physical_pixels_at_scale_1_and_0_64()
    for _, scale in ipairs({ 1, 0.64 }) do
        local W = world({ scale = scale })
        local px = pxU()
        for _, bar in ipairs({ W.P, W.G }) do
            local c = bar.frame._points.CENTER
            onGrid(UIParent._cx + c.x - bar.frame._w / 2, px, "scale " .. scale .. " " .. bar.unit .. " left edge")
            onGrid(UIParent._cy + c.y - bar.frame._h / 2, px, "scale " .. scale .. " " .. bar.unit .. " bottom edge")
        end
        -- snapping moves a frame by at most half a pixel: still the (0, -317) seat with the 18 gap
        near(W.G.frame._points.CENTER.x, 0, px / 2 + 1e-6, "scale " .. scale .. ": x on the seat")
        local _, _, gap = W.gapCentreScreen()
        near(gap, 18, px, "scale " .. scale .. ": the 18 gap, within a pixel of snapping")
        near((W.G.frame._points.CENTER.y + W.P.frame._points.CENTER.y) / 2, -317, px, "scale " .. scale .. ": gap centre at -317")
    end
    -- an odd scale snaps too
    local W = world({ scale = 0.85 })
    local px = pxU()
    local c = W.G.frame._points.CENTER
    onGrid(UIParent._cx + c.x - W.G.frame._w / 2, px, "0.85 left"); onGrid(UIParent._cy + c.y - W.G.frame._h / 2, px, "0.85 bottom")
end

-- The pixel bridge now lives in the data bar: the cast bars must not read it, at build, on a
-- scale event or from the engine's onLayout, wherever the frame is.
function T.a_foreverdebugbridge_frame_never_moves_the_bars_and_is_never_read()
    local ref = world()
    local want = {}
    for _, bar in ipairs({ ref.P, ref.G }) do want[bar.unit] = { bar.frame._points.CENTER.x, bar.frame._points.CENTER.y } end
    local function sameSeat(W, what)
        for _, bar in ipairs({ W.P, W.G }) do
            near(bar.frame._points.CENTER.x, want[bar.unit][1], 1e-9, bar.unit .. " x, " .. what)
            near(bar.frame._points.CENTER.y, want[bar.unit][2], 1e-9, bar.unit .. " y, " .. what)
        end
    end
    for _, spot in ipairs({ { 0, 0 }, { -10, -146 }, { 168, -269 } }) do
        local what = "bridge at " .. spot[1] .. "," .. spot[2]
        local W = world({ bridge = { 228, 18, spot[1], spot[2] } })
        sameSeat(W, what)
        -- and from here on every read of the frame is counted (CastBars wraps its placement in
        -- pcall, so a throwing getter alone would be swallowed; the count is what must stay 0)
        local hits = 0
        local function boom() hits = hits + 1; error("the cast bars read ForeverDebugBridgeFrame") end
        for _, m in ipairs({ "GetRegions", "GetLeft", "GetRight", "GetTop", "GetBottom", "GetEffectiveScale", "GetCenter" }) do
            W.bridge[m] = boom
        end
        __fireEvent("UI_SCALE_CHANGED"); __fireEvent("PLAYER_ENTERING_WORLD"); __flushTimers()
        W.P.run:RefreshPixels()
        sameSeat(W, what .. " after events")
        W.clean()
        eq(hits, 0, what .. ": ForeverDebugBridgeFrame was never read")
        eq(#__degrades, 0, what .. ": no degrade logs")
    end
end

function T.placement_re_lays_out_the_engine_once_and_not_in_a_loop()
    local W = world()
    local a, b = W.P.run.layoutCalls, W.G.run.layoutCalls
    eq(a, 2, "player: the build's own Layout plus exactly one refit once the frame had a seat")
    eq(b, 2, "target: the build's own Layout plus exactly one refit once the frame had a seat")
    __fireEvent("UI_SCALE_CHANGED"); __fireEvent("PLAYER_ENTERING_WORLD"); __flushTimers()
    eq(W.P.run.layoutCalls, a, "nothing moved: no relayout")
    eq(W.G.run.layoutCalls, b, "nothing moved: no relayout")
    W.clean()
end

-- The build's own placement is pcall'd like every other caller: a throw there must not leave
-- Blizzard's bars dimmed with none of our events wired.
function T.a_placement_that_throws_at_build_still_wires_the_events_and_logs()
    local real = UIParent.GetCenter
    local W = world({ beforeLoad = function() UIParent.GetCenter = function() error("no centre yet") end end })
    UIParent.GetCenter = real
    ok(W.P and W.G, "the bars still exist and are exported")
    ok(W.eventsFor("player") and W.eventsFor("target"), "both bars' events are wired")
    local logged = false
    for _, k in ipairs(__degrades) do if k == "castbar_place" then logged = true end end
    ok(logged, "the failure is logged")
    -- and a later placement (the scale event) recovers
    __fireEvent("UI_SCALE_CHANGED"); __flushTimers()
    eq(#__printed, 0, "no printed errors after recovery")
end

function T.the_icon_has_a_one_pixel_stroke()
    local W = world()
    local c = FS.Theme.COLOR_BAR_BORDER
    for _, bar in ipairs({ W.P, W.G }) do
        local e = bar.iconEdges
        ok(e and #e == 4, bar.unit .. ": four edges")
        local tops, sides = 0, 0
        for _, t in ipairs(e) do
            near(t._colorTexture[1], c[1], 1e-9, "the --line colour"); near(t._colorTexture[3], c[3], 1e-9)
            if t._h == 1 then tops = tops + 1 end
            if t._w == 1 then sides = sides + 1 end
            local any
            for _, p in pairs(t._points) do any = any or p.rel end
            eq(any, bar.icon, "anchored to the icon")
        end
        eq(tops, 2, "top and bottom"); eq(sides, 2, "left and right")
    end
end

function T.an_event_allocates_no_closure_and_a_failure_still_reports()
    local W = world()
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5)
    W.fire(W.P, "UNIT_SPELLCAST_START")
    local f = W.P.events
    local fn = f._scripts.OnEvent
    collectgarbage(); collectgarbage("stop")
    local before = collectgarbage("count")
    for _ = 1, 2000 do fn(f, "UNIT_SPELLCAST_STOP", "player", "OTHER", 1, nil) end
    local grown = collectgarbage("count") - before
    collectgarbage("restart")
    ok(grown < 16, "2000 events grew the heap by " .. grown .. " KB")
    local real = UnitCastingInfo
    UnitCastingInfo = function() error("boom") end
    fn(f, "UNIT_SPELLCAST_START", "player", "C1", 1, nil)
    UnitCastingInfo = real
    ok(__printed[1] and __printed[1]:find("UNIT_SPELLCAST_START", 1, true) and __printed[1]:find("boom", 1, true),
        "a failing step is still reported: " .. tostring(__printed[1]))
end

-- Tooltips: a skill that shows up has a tooltip. The Stack A icon is a hover-only frame over the icon box,
-- shown with the cast; the id comes from the cast and is cached on the frame, a secret id is never stored.
function T.the_stack_a_cast_icon_shows_the_casting_spell_on_hover()
    local W = world()
    local h = W.P.iconHover
    ok(h, "the player bar has an icon hover frame")
    ok(h._mouseMotion == true and h._mouseClick == false and h._mouse == nil,
        "hover only: motion on, clicks off, EnableMouse never called")
    eq(h._shown, false, "an idle bar has no hover frame up")
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5); __units.player.cast.spellID = 686
    W.fire(W.P, "UNIT_SPELLCAST_START")
    eq(h._shown, true, "shown with the cast")
    hover(h)
    ok(TT.owner == h and TT.spellID == 686, "the cast's spell: " .. tostring(TT.spellID))
    W.channel("player", "Drain Life", 100, 3, 689)
    W.fire(W.P, "UNIT_SPELLCAST_CHANNEL_START")
    ok(TT.owner == h and TT.spellID == 689, "a channel's spell, redrawn under the cursor: " .. tostring(TT.spellID))
    __units.player.chan = nil
    W.fire(W.P, "UNIT_SPELLCAST_CHANNEL_STOP")
    W.stepTo(W.P, 100, 104)
    eq(h._shown, false, "gone with the cast")
    ok(not TT.shown, "no tip once the cast is over")
    ok(h.fsSpellID == nil and h.fsName == nil, "and no id is kept")
    -- the target's icon too
    ok(W.G.iconHover, "the target bar has one")
end

function T.a_secret_target_spell_shows_no_stale_stack_a_tip()
    local W = world()
    local h = W.G.iconHover
    W.cast("target", "Fear", "T1", 100, 1.5); __units.target.cast.spellID = 5782
    W.fire(W.G, "UNIT_SPELLCAST_START")
    hover(h)
    ok(TT.spellID == 5782, "the plain cast shows")
    W.secretCast("target")
    __units.target.cast.spellID = __SECRET_ID
    ok(pcall(W.fire, W.G, "UNIT_SPELLCAST_START"), "no throw on a secret spell id")
    ok(TT.spellID ~= 5782, "the previous cast's spell is not shown for the secret one")
    ok(h.fsSpellID == nil and h.fsName == nil, "a secret id and name are never stored")
    ok(not TT.shown, "nothing known, nothing shown")
    W.clean()
end

function T.channel_ticks_are_keyed_by_spell_id_then_by_name()
    local W = world()
    local function counter(name, id)
        W.channel("player", name, 100, 3, id)
        W.fire(W.P, "UNIT_SPELLCAST_CHANNEL_START")
        return W.P.tabTicks._shown and W.P.tabTicks._text or nil
    end
    eq(counter("Gedankenschinden", 17312), "0/3", "a Mind Flay rank by id, whatever the (localized) name")
    eq(counter("Mind Flay", 15407), "0/3", "rank 1")
    eq(counter("Mind Flay", 99999), "0/3", "an unknown id falls back to the name")
    eq(counter("Mind Flay", nil), "0/3", "no id: the name")
    eq(counter("Zehren", 1120), "0/5", "a Drain Soul rank by id")
    eq(counter("Zehren", 27217), "0/5", "Drain Soul rank 5")
    eq(counter("Lebensentzug", 689), "0/5", "a Drain Life rank by id")
    eq(counter("Health Funnel", 755), nil, "Health Funnel has no counter")
    eq(counter("Something Else", 99999), nil, "neither: none")
    -- the clip rule follows the spec found by id
    W.channel("player", "Gedankenschinden", 100, 3, 17312)
    W.fire(W.P, "UNIT_SPELLCAST_CHANNEL_START")
    W.at(W.P, 102.1)
    eq(W.P.tabTicks._text, "CUT")
end


__checks = T
"""


def main() -> int:
    try:
        lua = boot()
    except (FileNotFoundError, LuaError) as err:
        print(f"FAIL  boot: {err}")
        return 1
    lua.execute(CHECKS)
    names = sorted(k for k in lua.eval("__checks").keys())
    failed = 0
    for name in names:
        # A fresh client per check: a failure must not leak state into the rest.
        lua = boot()
        lua.execute(CHECKS)
        try:
            lua.eval("__checks")[name]()
            print(f"ok    {name}")
        except LuaError as err:
            failed += 1
            print(f"FAIL  {name}: {err}")
    print(f"{len(names) - failed}/{len(names)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
