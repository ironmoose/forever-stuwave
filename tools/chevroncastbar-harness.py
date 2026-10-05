#!/usr/bin/env python3
"""Runs the real ChevronCastBar.lua headless against a small mock WoW API.

The engine is the shared chevron cast-bar run (segments, caret, success lock-in,
power-outage interrupt, channel drain). The parse gate proves it compiles; these
checks pin its BEHAVIOUR with a stepped clock:

  * layout: segment count and pixel-snapped pitch, texture recycling across Layout calls;
  * pixel grid: equal gaps and whole-pixel sizes for several stubbed scales and screen
    heights, slack at the far end, progress mapped onto the occupied span, and a
    re-layout on a scale change only when the pixel size changed;
  * lighting: a segment lights only once progress passes its END, and settles
    to the solid cyan after the Medium ignite;
  * determinism: per-segment flicker comes from a seeded PRNG; the golden
    numbers below were produced by the PROTOTYPE'S OWN JavaScript
    (mockups/castbar-v2-chevrons-locked-2026-10-01.html, makeFlicker + rng) so a
    drift in the Lua port shows up here;
  * caret: tip at the true progress x, mirrored for channels;
  * Succeed / Interrupt / channel timelines and the phase boundaries;
  * OnUpdate is only installed while animating, nothing allocates per frame,
    a steady frame touches only the caret, a secret time refuses cleanly, and UpdateTimes re-times without re-igniting;
  * vertical runs (opts.vertical, the Gunsight tapes): seats stacked on the Y axis with pixel snapping on Y,
    the caret and burst along Y, the Y flip for a channel, opts.textures and the chevron size overrides, the
    vertical strip StatusBar and its feature detection (the mock can hide StatusBar methods);
  * FS.ChevronCastBar.Fx: the exported motion functions with golden values and a caller supplied base colour.

The mock is strict: it implements exactly the widget methods the engine may use
(each one is in the 16001 widgets dump), so a call to anything else fails as a
nil method. It does NOT render and is not the real client.

    python3 tools/chevroncastbar-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ADDON = Path(__file__).resolve().parent.parent / "addon" / "ForeverSynthwave"

MOCK = r"""
__now = 0
-- A secret number: type() still says "number" (the real engine hides nothing
-- about the type), but any arithmetic or ordering on it throws.
__SECRET = {}
-- A secret castID (a GUID string in the real client). Ordering and concatenation
-- of it throw, and so does `secret == secret`; but Lua only calls __eq when BOTH
-- operands are tables, so `secret == "Cast-1"` quietly returns false here and a
-- check cannot prove that case was avoided (the real client throws on it). A
-- passing check therefore proves the engine never ordered, concatenated or
-- compared the secret against another secret; MatchesCast's own contract tests
-- below cover the rest. rawequal is the only safe way to recognise it.
__SECRET_ID = setmetatable({}, {
    __eq = function() error("secret castID compared") end,
    __lt = function() error("secret castID ordered") end,
    __le = function() error("secret castID ordered") end,
    __concat = function() error("secret castID concatenated") end,
})
local realType = type
function type(v)
    if rawequal(v, __SECRET) then return "number" end
    return realType(v)
end
__stats = {}
local function count(name) __stats[name] = (__stats[name] or 0) + 1 end
function GetTime() return __now end

-- Regions: preallocated state, so a steady-state call allocates nothing.
local Region = {}
Region.__index = Region
__textures = 0

local function new(kind, parent)
    local r = setmetatable({
        _kind = kind, _parent = parent, _points = {}, _scripts = {}, _shown = true,
        _alpha = 1, _w = 0, _h = 0, _level = (parent and parent._level or 0) + 1,
        _vc = { 0, 0, 0, 1 }, _tc = { 0, 1, 0, 1 }, _groups = {}, _vcCalls = 0,
    }, Region)
    return r
end

function Region:SetSize(w, h) count("SetSize"); self._w, self._h = w, h end
function Region:GetSize() return self._w, self._h end
function Region:GetWidth() return self._w end
function Region:GetHeight() return self._h end
function Region:SetPoint(point, rel, relPoint, x, y)
    count("SetPoint")
    local p = self._points[point]
    if not p then p = {}; self._points[point] = p end   -- once per named point
    p.rel, p.relPoint, p.x, p.y = rel, relPoint, x or 0, y or 0
end
function Region:ClearAllPoints() count("ClearAllPoints"); self._points = {} end
function Region:SetAllPoints(rel) count("SetAllPoints"); self._allPoints = rel end
function Region:GetFrameLevel() return self._level end
function Region:SetFrameLevel(l) self._level = l end
function Region:SetShown(v) count("SetShown"); self._shown = v and true or false end
function Region:Show() self._shown = true end
function Region:Hide() self._shown = false end
function Region:IsShown() return self._shown end
function Region:SetAlpha(a) count("SetAlpha"); self._alpha = a end
function Region:GetAlpha() return self._alpha end
function Region:SetClipsChildren(v) self._clips = v end
function Region:SetScript(k, fn) self._scripts[k] = fn end
function Region:GetScript(k) return self._scripts[k] end
-- HookScript adds to a separate list, so a later SetScript from a caller does not remove it
-- (as in the client).
function Region:HookScript(k, fn)
    self._hooks = self._hooks or {}
    self._hooks[k] = self._hooks[k] or {}
    table.insert(self._hooks[k], fn)
end
function Region:SetTexture(t) self._texture = t end
function Region:SetBlendMode(m) self._blend = m end
function Region:SetVertexColor(r, g, b, a)
    count("SetVertexColor")
    local v = self._vc
    v[1], v[2], v[3], v[4] = r, g, b, a or 1
    self._vcCalls = self._vcCalls + 1
end
function Region:SetTexCoord(l, r, t, b)
    local c = self._tc
    c[1], c[2], c[3], c[4] = l, r, t, b
end
function Region:CreateTexture(name, layer, tmpl, sub)
    __textures = __textures + 1
    return new("Texture", self)
end

-- Animation groups: record Play/Stop; animations accept only the setters we know.
local Anim = {}
Anim.__index = Anim
for _, n in ipairs({ "SetOrder", "SetDuration", "SetFromAlpha", "SetToAlpha", "SetSmoothing",
                     "SetScaleFrom", "SetScaleTo", "SetOrigin", "SetScale" }) do
    Anim[n] = function(self, ...) self._args = self._args or {}; self._args[n] = { ... } end
end
local Group = {}
Group.__index = Group
function Group:CreateAnimation(kind)
    local a = setmetatable({ _kind = kind }, Anim)
    self._anims[#self._anims + 1] = a
    return a
end
function Group:SetToFinalAlpha() end
function Group:SetScript(k, fn) self._scripts[k] = fn end
function Group:Play() self.plays = self.plays + 1; self.playing = true end
function Group:Stop() self.stops = self.stops + 1; self.playing = false end
function Region:CreateAnimationGroup()
    local g = setmetatable({ _anims = {}, _scripts = {}, plays = 0, stops = 0 }, Group)
    self._groups[#self._groups + 1] = g
    return g
end

-- StatusBar and its fill texture. __sbMissing / __sbTexMissing name methods the simulated client
-- lacks (a lookup of one returns nil, so the engine's feature detection sees it absent).
__sbMissing, __sbTexMissing = {}, {}
local SB, SBT = {}, {}
-- Region methods win over these (another harness that loads this mock, petcastbar-harness.py, adds its
-- own StatusBar methods to Region and must keep seeing them).
local SBMeta = { __index = function(_, k)
    if __sbMissing[k] then return nil end
    local v = Region[k]
    if v ~= nil then return v end
    return SB[k]
end }
local SBTexMeta = { __index = function(_, k)
    if __sbTexMissing[k] then return nil end
    local v = Region[k]
    if v ~= nil then return v end
    return SBT[k]
end }
function SBT:SetVertTile(v) self._vertTile = v end
function SBT:SetHorizTile(v) self._horizTile = v end
function SB:SetStatusBarTexture(path)
    self._sbPath = path
    if not self._sbTex then self._sbTex = setmetatable(new("Texture", self), SBTexMeta) end
end
function SB:GetStatusBarTexture() return self._sbTex end
function SB:SetOrientation(o) self._orientation = o end
function SB:SetMinMaxValues(a, b) self._min, self._max = a, b end
function SB:SetValue(v) self._value = v end
function SB:SetTimerDuration(d) self._timer = d end
function SB:SetStatusBarColor(r, g, b, a) self._sbColor = { r, g, b, a } end

function CreateFrame(kind, name, parent)
    if kind == "StatusBar" then return setmetatable(new(kind, parent), SBMeta) end
    return new(kind, parent)
end

-- Pixel grid. The effective scale is the product of every ancestor's SetScale, rooted at
-- UIParent (a check sets it with __setUIScale); the physical screen height is __physH.
-- PixelUtil.GetPixelToUIUnitFactor is Blizzard's own (768 / physical height), as in
-- Blizzard_SharedXML/PixelUtil.lua. __left stands in for frame:GetLeft() (nil = no rect yet).
__physH = 768
function GetPhysicalScreenSize() return __physH * 16 / 9, __physH end
PixelUtil = {
    GetPixelToUIUnitFactor = function() local _, h = GetPhysicalScreenSize(); return 768 / h end,
}
function Region:SetScale(s) self._scale = s end
function Region:GetScale() return self._scale or 1 end
function Region:GetParent() return self._parent end
function Region:GetEffectiveScale()
    count("GetEffectiveScale")
    local p = self._parent
    return (self._scale or 1) * (p and p:GetEffectiveScale() or 1)
end
__left = nil
function Region:GetLeft() return __left end
__bottom = nil
function Region:GetBottom() return __bottom end
-- The client's error handler: errors a hook swallows still have to reach it.
__errors = {}
function geterrorhandler() return function(e) __errors[#__errors + 1] = e end end
function __setUIScale(s) UIParent._scale = s end
-- Events: frames that RegisterEvent get OnEvent when __fire names one.
__evFrames = {}
function Region:RegisterEvent(e)
    self._events = self._events or {}
    self._events[e] = true
    __evFrames[#__evFrames + 1] = self
end
function Region:UnregisterEvent(e) if self._events then self._events[e] = nil end end
function __fire(event)
    for _, f in ipairs(__evFrames) do
        local fn = f._events and f._events[event] and f._scripts.OnEvent
        if fn then fn(f, event) end
    end
end
-- Post-hook, as the client's hooksecurefunc does for a method on one frame.
function hooksecurefunc(obj, name, fn)
    local orig = obj[name]
    obj[name] = function(...) local r = orig(...); fn(...); return r end
end

__degrades = {}
FS = {
    IsSecret = function(v) return rawequal(v, __SECRET) or rawequal(v, __SECRET_ID) end,
    LogDegradeOnce = function(key, msg) __degrades[#__degrades + 1] = key end,
    Theme = {},
}
UIParent = new("Frame", nil)

function __load_theme_constants(lines)
    assert(loadstring("local Theme = ...\n" .. table.concat(lines, "\n"), "@Theme.lua(constants)"))(FS.Theme)
end
function __load(path, src)
    local fn = assert(loadstring(src, "@" .. path))
    return fn("ForeverSynthwave", FS)
end
"""

THEME_CONSTANTS = (
    "CHROME_CORNERS",  # first: later constants (SLICE_GLOW_TEXTURE/MARGIN) branch on it
    "COLOR_POWER", "COLOR_BORDER", "CAST_CHEVRON_FILL_TEXTURE", "CAST_CHEVRON_OUTLINE_TEXTURE",
    "CAST_CHEVRON_GLOW_TEXTURE", "CAST_CHEVRON_BURST_TEXTURE", "CAST_CHEVRON_ASPECT",
    "CAST_CHEVRON_GAP_FRACTION", "CAST_CHEVRON_GLOW_PAD_FRACTION", "CAST_CHEVRON_STRIP_TEXTURE",
)


def _extract_theme_constant(source: str, name: str) -> str:
    match = re.search(rf"^Theme\.{name}\s*=.*$", source, re.M)
    if not match:
        sys.exit(f"Theme.{name} not found in Theme.lua; update THEME_CONSTANTS")
    return match.group(0)


def boot() -> "LuaRuntime":
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    theme_src = (ADDON / "Theme.lua").read_text(encoding="utf-8")
    consts = [_extract_theme_constant(theme_src, n) for n in THEME_CONSTANTS]
    lua.eval("__load_theme_constants")(lua.table_from(consts))
    path = ADDON / "ChevronCastBar.lua"
    if not path.exists():
        raise FileNotFoundError(path)
    src = path.read_text(encoding="utf-8")
    lua.eval("function(s) __src = s end")(src)
    lua.eval("__load")("ChevronCastBar.lua", src)
    return lua


CHECKS = r"""
local T = {}
local CCB = FS.ChevronCastBar
local CAST = 2.5

local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end
local function near(a, b, tol, msg)
    if a == nil or math.abs(a - b) > (tol or 1e-6) then
        error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2)
    end
end
local function ok(v, msg) if not v then error(msg or "expected true", 2) end end

-- Fresh run on a fresh clock.
local function mk(opts)
    __now = 100
    opts = opts or {}
    opts.width = opts.width or 150
    opts.height = opts.height or 18
    local parent = CreateFrame("Frame", nil, UIParent)
    return CCB.Create(parent, opts), parent
end

-- Advance the mocked clock to `t` seconds after `base` and run the installed OnUpdate.
local function at(run, t)
    __now = t
    local fn = run.frame:GetScript("OnUpdate")
    if fn then fn(run.frame, 0) end
end
local function stepTo(run, from, to, fps)
    local dt = 1 / (fps or 60)
    local t = from
    while t < to do t = math.min(to, t + dt); at(run, t) end
    return t
end

local function lit(seg) return seg.lit._shown and seg.lit._vc[4] > 0 end
local function litCount(run)
    local n = 0
    for i = 1, run.count do if lit(run.segs[i]) then n = n + 1 end end
    return n
end
local function topLeftX(tex) return tex._points["TOPLEFT"].x end

-- ---- layout ------------------------------------------------------------

function T.layout_segment_count_and_pitch()
    -- Player run: h 18 -> box 18, arm 9, gap 18/6 = 3, pitch 12; (150 - 18) / 12 + 1 = 12.
    local run = mk({ width = 150, height = 18 })
    eq(run.count, 12, "player count")
    eq(topLeftX(run.segs[1].lit), 0, "first x")
    near(topLeftX(run.segs[2].lit), 12, 1e-6, "pitch")
    near(topLeftX(run.segs[12].lit) + run.segs[12].lit._w, 150, 1e-6, "last chevron ends at the run edge")
    eq(run.segs[1].lit._w, 18, "chevron width"); eq(run.segs[1].lit._h, 18, "chevron height")
    -- Pet run: h 10, gap fraction 0.2 -> arm 5 + 2 = pitch 7; floor(90 / 7) + 1 = 13. The pitch is never
    -- stretched to eat the slack (6 units here): it stays 7 and the slack sits at the far end.
    local pet = mk({ width = 100, height = 10, gapFraction = 0.2 })
    eq(pet.count, 13, "pet count")
    near(topLeftX(pet.segs[2].lit), 7, 1e-6, "pixel pitch, not stretched")
    near(topLeftX(pet.segs[13].lit) + pet.segs[13].lit._w, 94, 1e-6, "last chevron ends where the run ends, slack after it")
end

-- ---- pixel exact layout --------------------------------------------------

-- Four distinct pixel sizes (physical height, effective scale) and two shapes: an awkward
-- player width that leaves slack, and the pet run (gap fraction 0.2).
local GRIDS = { { 1440, 0.64 }, { 1080, 0.71 }, { 1080, 1.0 }, { 1080, 1.15 } }
local SHAPES = { { width = 333.3, height = 18 }, { width = 100, height = 10, gapFraction = 0.2 } }

-- One physical pixel in the run frame's units, from the stubs (what PixelUtil says over the effective scale).
local function pixelOf(run)
    return (768 / __physH) / run.frame:GetEffectiveScale()
end
local function isWhole(v, tol) return math.abs(v - math.floor(v + 0.5)) <= (tol or 1e-6) end
local function pitchOf(run) return topLeftX(run.segs[2].lit) - topLeftX(run.segs[1].lit) end

local function eachGrid(fn)
    for _, g in ipairs(GRIDS) do
        __physH = g[1]; __setUIScale(g[2])
        for _, o in ipairs(SHAPES) do
            local run = mk({ width = o.width, height = o.height, gapFraction = o.gapFraction })
            fn(run, pixelOf(run), "h" .. g[1] .. " s" .. g[2] .. " w" .. o.width)
        end
    end
end

function T.layout_gaps_are_equal_and_everything_is_whole_pixels()
    eachGrid(function(run, px, tag)
        ok(run.count >= 2, tag .. ": a row")
        local w, pitch = run.segs[1].lit._w, pitchOf(run)
        ok(isWhole(w / px), tag .. ": chevron width " .. w .. " is whole pixels (px " .. px .. ")")
        ok(isWhole(pitch / px), tag .. ": pitch is whole pixels")
        eq(topLeftX(run.segs[1].lit), 0, tag .. ": the run starts at its own origin")
        for i = 2, run.count do
            eq(run.segs[i].lit._w, w, tag .. ": identical chevron width " .. i)
            near(topLeftX(run.segs[i].lit) - topLeftX(run.segs[i - 1].lit), pitch, 1e-9, tag .. ": gap " .. i .. " equals the first")
        end
        near(run.pitch, pitch, 1e-9, tag .. ": run.pitch is the engine's pitch")
    end)
end

function T.layout_keeps_the_count_rule_and_puts_the_slack_at_the_far_end()
    eachGrid(function(run, px, tag)
        local w, pitch = run.segs[1].lit._w, pitchOf(run)
        local last = topLeftX(run.segs[run.count].lit) + w
        ok(last <= run.W + 1e-6, tag .. ": the chevrons fit the run")
        -- As many whole chevrons as fit: one more would not.
        ok(last + pitch > run.W + 1e-6, tag .. ": one more chevron would not fit")
        near(run.span, last, 1e-9, tag .. ": run.span is the occupied width")
    end)
    -- Never stretched: more width adds chevrons, not a wider pitch.
    local a = mk({ width = 150, height = 18 })
    local b = mk({ width = 155, height = 18 })
    near(pitchOf(b), pitchOf(a), 1e-9, "same pitch")
    eq(b.segs[1].lit._w, a.segs[1].lit._w, "same chevron width")
end

function T.progress_maps_onto_the_occupied_span_last_chevron_lights_at_one()
    eachGrid(function(run, px, tag)
        local n = run.count
        eq(run.segs[n].b, 1, tag .. ": the last chevron ends at progress 1")
        eq(run.segs[1].a, 0, tag .. ": the first starts at 0")
        run:StartCast(100, 100 + CAST, false)
        run:SetProgressOverride(0); at(run, 101)
        eq(litCount(run), 0, tag .. ": none lit at 0")
        run:SetProgressOverride(0.9999); at(run, 102)
        eq(lit(run.segs[n]), false, tag .. ": the last is not lit just before 1")
        run:SetProgressOverride(1); at(run, 103)
        eq(litCount(run), n, tag .. ": every chevron lit at 1, the last one included")
        run:Stop()
    end)
end

function T.caret_burst_and_stagger_follow_the_occupied_span()
    __physH = 1080; __setUIScale(0.71)
    __left = 100.3137                          -- a fractional origin, so the origin term matters
    local run = mk({ width = 333.3, height = 18 })
    local n, w = run.count, run.segs[1].lit._w
    local origin = topLeftX(run.segs[1].lit)
    local lastX = topLeftX(run.segs[n].lit)
    local span = lastX + w - origin
    ok(span < run.W - 1, "this width leaves slack")
    run:StartCast(100, 100 + CAST, false)
    run:SetProgressOverride(0.5); at(run, 101)
    -- Cast caret: tip (right edge of the box) at origin + f * span, not f * W.
    near(run.outline._points["TOPLEFT"].x + run.outline._w, origin + 0.5 * span, 1e-9, "caret tip on the span")
    -- The burst sits on the last chevron, not on the run's right edge.
    local bp = run.burst._points["CENTER"]
    eq(bp.relPoint, "TOPLEFT", "burst anchored from the left")
    near(bp.x, lastX + w / 2, 1e-9, "burst on the last chevron")
    -- Channel stagger: proportional to the chevron centres' distance along the span.
    local ch = mk({ width = 333.3, height = 18 })
    ch:StartCast(100, 200, true)
    for i = 1, n - 1 do
        local c1 = topLeftX(ch.segs[i].lit) + w / 2 - origin
        local c2 = topLeftX(ch.segs[i + 1].lit) + w / 2 - origin
        near(ch.segs[i].litSince - ch.segs[i + 1].litSince, (c2 - c1) / span * 350, 1e-6, "stagger " .. i)
    end
    __left = nil
end

function T.origin_is_pixel_aligned_and_never_overhangs_the_run()
    for _, g in ipairs(GRIDS) do
        __physH = g[1]; __setUIScale(g[2])
        for _, o in ipairs(SHAPES) do
            __left = 100.3137
            local run = mk({ width = o.width, height = o.height, gapFraction = o.gapFraction })
            local px = pixelOf(run)
            for i = 1, run.count do
                ok(isWhole((__left + topLeftX(run.segs[i].lit)) / px, 1e-6), "chevron " .. i .. " on a physical pixel (s " .. g[2] .. ", h " .. g[1] .. ")")
            end
            ok(topLeftX(run.segs[run.count].lit) + run.segs[1].lit._w <= run.W + 1e-9, "the last chevron does not pass the run's right edge")
            ok(math.abs(topLeftX(run.segs[1].lit)) < px, "the origin moves by less than a pixel")
        end
    end
    -- One pixel per unit (768 high, scale 1). Slack 3: nudged RIGHT onto the pixel (0.7 < 3).
    __physH = 768; __setUIScale(1.0); __left = 100.3
    local roomy = mk({ width = 333.3, height = 18 })
    near(roomy.span, 330, 1e-9); near(topLeftX(roomy.segs[1].lit), 0.7, 1e-9, "nudged right when the slack allows")
    -- No slack (the chevrons exactly fill the run): nudged LEFT, so nothing passes the right edge.
    local tight = mk({ width = 150, height = 18 })
    near(tight.span, 150, 1e-9); near(topLeftX(tight.segs[1].lit), -0.3, 1e-9, "nudged left when there is no slack")
    __left = nil
end

function T.a_throwing_or_secret_getleft_is_tolerated()
    __physH = 1080; __setUIScale(0.71)
    local run = mk({ width = 150, height = 18 })
    run.frame.GetLeft = function() error("can't measure restricted regions") end
    local okc, err = pcall(run.Layout, run, 150, 18)
    ok(okc, "Layout threw when GetLeft threw: " .. tostring(err))
    eq(topLeftX(run.segs[1].lit), 0, "no nudge without a measurement")
    run.frame.GetLeft = function() return __SECRET end
    okc, err = pcall(run.Layout, run, 150, 18)
    ok(okc, "Layout threw on a secret GetLeft: " .. tostring(err))
    eq(topLeftX(run.segs[1].lit), 0, "no nudge from a secret")
end

function T.a_half_pixel_tie_rounds_the_same_at_every_scale()
    -- Identical physical geometry (a 7.5 px high run, aspect 1, 100 px wide) at several scales:
    -- the .5 ties in the rounding must not flip on float noise.
    __physH = 1080
    local ref
    for _, s in ipairs({ 0.64, 0.71, 0.8, 1.0, 1.15, 1.3 }) do
        __setUIScale(s)
        local px = (768 / 1080) / s
        -- Sizes derived the way a caller would (physical size to UI units, then to frame units),
        -- not as px multiples, so the quotient carries float noise: 7.4999999 at some scales.
        local run = mk({ width = (100 * 768 / 1080) / s, height = (7.5 * 768 / 1080) / s, gapFraction = 0.2 })
        local got = { count = run.count, w = run.segs[1].lit._w / px, pitch = pitchOf(run) / px }
        ref = ref or got
        eq(got.count, ref.count, "count at scale " .. s)
        near(got.w, ref.w, 1e-6, "chevron width at scale " .. s)
        near(got.pitch, ref.pitch, 1e-6, "pitch at scale " .. s)
    end
end

-- ---- re-layout when the pixel size can change -----------------------------

local function countLayouts(run)
    local state = { n = 0 }
    local orig = run.Layout
    run.Layout = function(...) state.n = state.n + 1; return orig(...) end
    return state
end

local function fireShow(f)
    local fn = f._scripts.OnShow
    if fn then fn(f) end
    for _, h in ipairs(f._hooks and f._hooks.OnShow or {}) do h(f) end
end

function T.scale_events_relayout_only_when_the_pixel_size_changed()
    __physH = 1080; __setUIScale(0.71)
    local run = mk({ width = 150, height = 18 })
    local seen = {}
    for _, f in ipairs(__evFrames) do for e in pairs(f._events) do seen[e] = true end end
    ok(seen.UI_SCALE_CHANGED and seen.DISPLAY_SIZE_CHANGED, "both rescale events are registered")
    local st = countLayouts(run)
    local laid = 0
    run.onLayout = function() laid = laid + 1 end
    __fire("UI_SCALE_CHANGED"); __fire("DISPLAY_SIZE_CHANGED")
    eq(st.n, 0, "same scale and size: no re-layout")
    eq(laid, 0, "and no onLayout")
    local before = run.px
    __setUIScale(0.64); __fire("UI_SCALE_CHANGED")
    eq(st.n, 1, "a new effective scale re-lays out")
    eq(laid, 1, "onLayout fires after the re-layout")
    ok(run.px ~= before, "the new pixel size is stored")
    near(run.px, pixelOf(run), 1e-12, "stored pixel size is the current one")
    near(run.pitch, pitchOf(run), 1e-9, "run.pitch follows the re-layout")
    __fire("UI_SCALE_CHANGED"); __fire("DISPLAY_SIZE_CHANGED")
    eq(st.n, 1, "the same scale again: still one")
    __physH = 1440; __fire("DISPLAY_SIZE_CHANGED")
    eq(st.n, 2, "a new display size re-lays out")
    -- The new geometry is on the new grid.
    local px = pixelOf(run)
    ok(isWhole(run.segs[1].lit._w / px) and isWhole(pitchOf(run) / px), "chevron width and pitch on the new grid")
end

function T.a_parent_rescale_relayouts_and_an_unchanged_scale_does_not()
    __physH = 1080; __setUIScale(1.0)
    local run, parent = mk({ width = 150, height = 18 })
    local st = countLayouts(run)
    parent:SetScale(1)
    eq(st.n, 0, "SetScale to the same value: no re-layout")
    parent:SetScale(0.8)
    eq(st.n, 1, "the parent's SetScale re-lays out")
    local px = pixelOf(run)
    ok(isWhole(run.segs[1].lit._w / px), "on the grid of the rescaled parent")
    UIParent:SetScale(0.5)
    eq(st.n, 2, "a grandparent's SetScale re-lays out too")
    UIParent:SetScale(0.5)
    eq(st.n, 2, "and not twice for the same value")
end

function T.ancestor_hooks_and_the_event_watcher_are_shared_not_stacked_per_run()
    local hooked = {}
    local orig = hooksecurefunc
    hooksecurefunc = function(o, name, fn)
        if name == "SetScale" then hooked[o] = (hooked[o] or 0) + 1 end
        return orig(o, name, fn)
    end
    __physH = 1080; __setUIScale(1.0)
    local runs = {}
    for i = 1, 3 do runs[i] = mk({ width = 150, height = 18 }) end
    hooksecurefunc = orig
    eq(hooked[UIParent], 1, "UIParent's SetScale is hooked once for three runs")
    for i = 1, 3 do eq(hooked[runs[i].frame], 1, "run frame " .. i .. " hooked once") end
    local distinct, seenF = 0, {}
    for _, f in ipairs(__evFrames) do
        if f._events.UI_SCALE_CHANGED and not seenF[f] then seenF[f] = true; distinct = distinct + 1 end
    end
    eq(distinct, 1, "one event watcher for all runs")
    -- The one hook still reaches every run, and a collection does not drop a held run.
    collectgarbage(); collectgarbage()
    local st = {}
    for i = 1, 3 do st[i] = countLayouts(runs[i]) end
    UIParent:SetScale(0.5)
    for i = 1, 3 do eq(st[i].n, 1, "run " .. i .. " re-laid out by the shared hook") end
end

function T.a_failing_ancestor_hook_does_not_stop_the_walk_and_is_retried()
    local orig = hooksecurefunc
    local failFor
    hooksecurefunc = function(o, name, fn)
        if o == failFor then error("hook refused") end
        return orig(o, name, fn)
    end
    __physH = 1080; __setUIScale(1.0)
    local parent = CreateFrame("Frame", nil, UIParent)
    failFor = parent
    local okc, run = pcall(CCB.Create, parent, { width = 150, height = 18 })
    ok(okc, "Create threw on a refused hook: " .. tostring(run))
    local st = countLayouts(run)
    UIParent:SetScale(0.5)                     -- UIParent sits above the refused frame
    eq(st.n, 1, "the walk continued past the refused ancestor")
    -- Not marked as hooked, so the next run under it tries again and succeeds.
    failFor = nil
    local calls = 0
    hooksecurefunc = function(o, name, fn) if o == parent then calls = calls + 1 end return orig(o, name, fn) end
    CCB.Create(parent, { width = 150, height = 18 })
    hooksecurefunc = orig
    eq(calls, 1, "the refused frame is retried")
end

function T.one_failing_run_does_not_skip_the_others_on_a_rescale()
    __physH = 1080; __setUIScale(1.0)
    local runs = {}
    for i = 1, 4 do runs[i] = mk({ width = 150, height = 18 }) end
    for i = 1, 3 do runs[i].RefreshPixels = function() error("boom") end end
    local st = countLayouts(runs[4])
    local okc, err = pcall(UIParent.SetScale, UIParent, 0.5)
    ok(okc, "the rescale threw: " .. tostring(err))
    eq(st.n, 1, "the healthy run still re-laid out")
    eq(#__errors, 3, "each failure reached the error handler")
    ok(string.find(__errors[1], "boom", 1, true), "with its message")
end

function T.an_onlayout_that_rescales_settles_on_the_new_pixel_size_once()
    __physH = 1080; __setUIScale(1.0)
    local run = mk({ width = 150, height = 18 })
    local st = countLayouts(run)
    local n = 0
    run.onLayout = function()
        n = n + 1
        if n == 1 then UIParent:SetScale(0.5) end     -- the first layout rescales again
    end
    UIParent:SetScale(0.9)
    eq(st.n, 2, "the dropped rescale is replayed once, no cascade")
    eq(n, 2, "onLayout ran for both")
    near(run.px, pixelOf(run), 1e-12, "and the run ends on the current pixel size")
end

function T.an_onlayout_that_always_rescales_still_terminates()
    __physH = 1080; __setUIScale(1.0)
    local run = mk({ width = 150, height = 18 })
    local st = countLayouts(run)
    local n = 0
    run.onLayout = function()
        n = n + 1
        UIParent:SetScale(0.5 + 0.01 * n)      -- every layout changes the pixel size again
    end
    UIParent:SetScale(0.9)
    ok(st.n <= 2, "bounded: " .. st.n .. " layouts")
    ok(not run.inLayout, "the guard is released")
end

function T.a_throw_through_layout_keeps_the_message_releases_the_guard_and_retries()
    __physH = 1080; __setUIScale(1.0)
    local run = mk({ width = 150, height = 18 })
    run.onLayout = function() error("boom from onLayout") end
    local okc, err = pcall(run.Layout, run, 150, 18)
    eq(okc, false, "the error propagates")
    ok(string.find(tostring(err), "boom from onLayout", 1, true), "message intact: " .. tostring(err))
    eq(run.inLayout, false, "guard released")
    -- px was reset, so the next trigger re-lays out even though nothing rescaled.
    run.onLayout = nil
    eq(run:RefreshPixels(), true, "a failed layout is retried by the next trigger")
    near(run.px, pixelOf(run), 1e-12)
    ok(run:Layout(150, 18), "a later Layout works")
    -- With debugstack available the throw site is appended to the message.
    debugstack = function() return "STACK-AT-THROW" end
    run.onLayout = function() error("second boom") end
    okc, err = pcall(run.Layout, run, 150, 18)
    debugstack = nil
    ok(string.find(tostring(err), "second boom", 1, true) and string.find(tostring(err), "STACK-AT-THROW", 1, true),
        "message and stack kept: " .. tostring(err))
end

function T.a_nested_layout_from_onlayout_is_dropped()
    __physH = 1080; __setUIScale(1.0)
    local run = mk({ width = 150, height = 18 })
    local calls, nested = 0, nil
    run.onLayout = function(r)
        calls = calls + 1
        nested = r:Layout(300, 18)
    end
    ok(run:Layout(150, 18))
    eq(nested, false, "the nested Layout returns false")
    eq(calls, 1, "and does not recurse")
    eq(run.W, 150, "the outer size stands")
end

function T.a_missed_rescale_is_caught_when_the_run_is_shown_or_a_cast_starts()
    __physH = 1080; __setUIScale(1.0)
    local run = mk({ width = 150, height = 18 })
    local st = countLayouts(run)
    -- A caller's own OnShow handler (SetScript) must not remove the engine's check (HookScript).
    local callerShown = 0
    run.frame:SetScript("OnShow", function() callerShown = callerShown + 1 end)
    __setUIScale(0.64)                        -- no event reached us
    fireShow(run.frame)
    eq(callerShown, 1, "the caller's handler still runs")
    eq(st.n, 1, "OnShow re-checks the pixel size")
    __setUIScale(1.15)
    ok(run:StartCast(100, 100 + CAST, false))
    eq(st.n, 2, "StartCast re-checks the pixel size")
    ok(isWhole(run.segs[1].lit._w / pixelOf(run)), "and the cast runs on the new grid")
    __setUIScale(0.71)
    run:ShowIdle()
    eq(st.n, 3, "ShowIdle re-checks the pixel size")
end

function T.start_cast_fires_no_stale_verdict_when_a_rescale_is_pending()
    __physH = 1080; __setUIScale(1.0)
    local run = mk({ width = 150, height = 18 })
    local fin = 0
    run.onFinished = function() fin = fin + 1 end
    run:StartCast(100, 100 + CAST, false); run:SetProgressOverride(0.5); at(run, 101)
    ok(run:Succeed())                         -- a hold begins at 101
    __now = 110                               -- far past the hold and the fade; no frame ran
    __setUIScale(0.64)
    ok(run:StartCast(110, 112.5, false))
    eq(fin, 0, "the abandoned hold must not finish inside StartCast")
    eq(run:GetPhase(), "cast", "the new cast is running")
    near(run.px, pixelOf(run), 1e-12, "on the new grid")
end

function T.onupdate_never_reads_the_pixel_size()
    __physH = 1080; __setUIScale(0.71)
    local run = mk({ width = 150, height = 18 })
    run:StartCast(100, 110, false)
    stepTo(run, 100, 101, 60)
    __stats.GetEffectiveScale = 0
    stepTo(run, 101, 104, 60)
    eq(__stats.GetEffectiveScale or 0, 0, "no pixel-size query while animating")
end

function T.pixel_size_falls_back_without_pixelutil_then_without_either()
    __physH = 1080; __setUIScale(0.71)
    local want = (768 / 1080) / 0.71
    PixelUtil = nil
    local a = mk({ width = 150, height = 18 })
    near(a.px, want, 1e-12, "GetPhysicalScreenSize alone gives 768 / height")
    PixelUtil = { GetPixelToUIUnitFactor = function() return 768 / 1080 end }
    GetPhysicalScreenSize = nil
    local b = mk({ width = 150, height = 18 })
    near(b.px, want, 1e-12, "PixelUtil alone")
    PixelUtil = nil
    eq(#__degrades, 0, "nothing logged while one API answers")
    local c = mk({ width = 150, height = 18 })
    near(c.px, 1 / 0.71, 1e-12, "neither: whole UI units")
    ok(isWhole(c.segs[1].lit._w / c.px) and isWhole(pitchOf(c) / c.px), "still snapped to that grid")
    c:Layout(160, 18); mk({ width = 150, height = 18 })
    eq(#__degrades, 1, "the degrade is logged once"); eq(__degrades[1], "chevron_no_pixel_api")
end

function T.layout_recycles_textures()
    local run = mk({ width = 150, height = 18 })
    local made = __textures
    local first = run.segs[1].lit
    run:Layout(100, 18)                       -- fewer: floor(82 / 12) + 1
    eq(run.count, 7, "shrunk"); eq(run.segs[8].lit._shown, false, "extra hidden")
    run:Layout(150, 18)                       -- back to the original: no new textures
    eq(run.count, 12, "regrown"); eq(__textures, made, "textures recycled"); ok(run.segs[1].lit == first)
end

-- ---- lighting and flicker ----------------------------------------------

function T.segment_lights_only_after_progress_passes_its_end()
    local run = mk()
    ok(run:StartCast(100, 100 + CAST, false))
    local s5 = run.segs[4]                    -- x0 = 36, so b = (36 + 18) / 150 = 0.36
    near(s5.b, 0.36, 1e-9, "segment end")
    run:SetProgressOverride(0.35)
    at(run, 101)
    eq(lit(s5), false, "unlit before its end")
    run:SetProgressOverride(0.37)
    at(run, 101.5)                            -- past the end, ignite over (<= 220ms later)
    local v = s5.lit._vc
    eq(lit(s5), true, "lit after its end")
    stepTo(run, 101.5, 102, 60)
    v = s5.lit._vc
    near(v[1], 0.133, 0.01, "settled r"); near(v[2], 0.878, 0.01, "settled g"); near(v[3], 1, 0.01, "settled b")
    near(v[4], 1, 1e-6, "settled alpha")
    eq(lit(run.segs[5]), false, "next segment still unlit (b = 0.44)")
    -- Scrubbing back turns segments off at once.
    run:SetProgressOverride(0.1)
    at(run, 102.1)
    eq(lit(s5), false, "scrubbed back")
end

function T.flicker_is_seeded_and_matches_the_prototype()
    -- Golden values from the prototype's own makeFlicker('medium') + rng, seeds
    -- (72 * 131 + 13) * 1009 + i * 7919 + 12345 for i = 0..2 (node, 2026-10-01).
    local gold = {
        { 206, 0.04843413915019482, 0.24843413915019483, 2, 0.4420048024505377, 0.6220048024505377, 0.5251788871828467 },
        { 214, 0.08178474087733775, 0.28178474087733774, 1, 0.40470788097009064, 0.5847078809700906, 0.8100013923831284 },
        { 210, 0.04766116026323289, 0.2476611602632329, 2, 0.4524506656266749, 0.6324506656266748, 0.11214530747383833 },
    }
    local run = mk()
    local function checkRow(r, idx, g, label)
        local sg = r.segs[idx]
        eq(sg.ign, g[1], label .. " ign")
        near(sg.blinks[1].t0, g[2], 1e-9, label .. " blink1 t0"); near(sg.blinks[1].t1, g[3], 1e-9, label .. " blink1 t1")
        eq(sg.blinks[1].code, g[4], label .. " blink1 code")
        near(sg.blinks[2].t0, g[5], 1e-9, label .. " blink2 t0"); near(sg.blinks[2].t1, g[6], 1e-9, label .. " blink2 t1")
        eq(sg.blinks[2].code, 4, label .. " blink2 code")
        near(sg.jit, g[7], 1e-9, label .. " jit")
    end
    for i, g in ipairs(gold) do checkRow(run, i, g, "seg " .. i) end
    -- Further draws from the same JS, deeper into the seed range and with the pet
    -- bar's salt (7), so a drift in the 32 bit multiply or in the salt shows up
    -- even where the first three segments happen to agree (node, 2026-10-01).
    checkRow(run, 6, { 198, 0.08212591553106904, 0.282125915531069, 2, 0.4607256787270308, 0.6407256787270308, 0.6102470280602574 }, "salt 13 seg 6")
    checkRow(run, 12, { 210, 0.08270431369077413, 0.28270431369077414, 1, 0.40773667860776186, 0.5877366786077618, 0.3810157408006489 }, "salt 13 seg 12")
    local pet = mk({ width = 100, height = 10, gapFraction = 0.2, seedSalt = 7 })
    checkRow(pet, 1, { 207, 0.08382610500324517, 0.2838261050032452, 2, 0.4423671481572092, 0.6223671481572092, 0.8373230323195457 }, "salt 7 seg 1")
end

-- ---- caret -------------------------------------------------------------

function T.caret_tip_sits_at_true_progress()
    local run = mk()
    run:StartCast(100, 100 + CAST, false)
    run:SetProgressOverride(0.4)
    at(run, 101)
    eq(run.clip._shown, true, "caret shown mid cast")
    -- Cast: the outline box spans [x - w, x], tip (right edge) at 0.4 * 150 = 60.
    local p = run.outline._points["TOPLEFT"]
    -- SetClipsChildren clips child FRAMES, not the clipping frame's own regions
    -- (FrameHelpers.lua's convention), so the caret textures live on a child of clip.
    eq(run.clip._clips, true, "clip frame clips its children")
    eq(run.body._parent, run.clip, "caret body is a child frame of the clip frame")
    eq(run.outline._parent, run.body, "outline sits on the clipped child, not on the clip frame itself")
    eq(run.glow._parent, run.body, "glow sits on the clipped child")
    eq(p.rel, run.body, "anchored to the clipped child frame")
    eq(run.body._allPoints, run.clip, "child fills the clip frame")
    near(p.x + run.outline._w, 60, 1e-6, "tip x")
    eq(run.outline._w, 18, "caret is one chevron wide")
    eq(run.glow._points["CENTER"].rel, run.outline, "glow rides the outline")
    near(run.glow._w, 36, 1e-6, "glow is 2x")
    eq(run.glow._blend, "ADD")
    run:SetProgressOverride(0)
    at(run, 101.1)
    eq(run.clip._shown, false, "hidden at 0")
    run:SetProgressOverride(1)
    at(run, 101.2)
    eq(run.clip._shown, false, "hidden at full")
end

-- ---- success -----------------------------------------------------------

local function withEffects()
    local parent = CreateFrame("Frame", nil, UIParent)
    local fx = {
        flare = parent:CreateTexture(), glow = parent:CreateTexture(), holdGlow = parent:CreateTexture(),
        pop = CreateFrame("Frame", nil, parent),
    }
    fx.flare:SetVertexColor(0.659, 0.333, 0.969, 1)
    return fx
end

function T.succeed_holds_locks_in_fades_then_finishes()
    local fx = withEffects()
    local run = mk({ flareTarget = fx.flare, glowBurst = fx.glow, holdGlow = fx.holdGlow, scaleTarget = fx.pop })
    local finished = 0
    run.onFinished = function() finished = finished + 1 end
    run:StartCast(100, 100 + CAST, false)
    run:SetProgressOverride(0.5)
    at(run, 101)
    ok(litCount(run) < run.count, "not all lit before success")
    ok(run:Succeed(), "Succeed accepted")
    at(run, 101)
    eq(litCount(run), run.count, "whole bar lit")
    for i = 1, run.count do near(run.segs[i].lit._vc[4], 1, 1e-9, "full alpha " .. i) end
    -- lock-in: chevron burst and glow burst played, NO scale pop (the snap was dropped); frame flare moves toward near-white.
    eq(run.burst._groups[1].plays, 1, "chevron burst")
    eq(fx.glow._groups[1].plays, 1, "glow burst")
    eq(#fx.pop._groups, 0, "no scale pop group on the scale target")
    eq(run.burst._shown, true)
    at(run, 101.03)                           -- 30ms in: flare is at its peak
    ok(fx.flare._vc[1] > 0.8 and fx.flare._vc[2] > 0.8, "flare toward near-white")
    near(fx.holdGlow._alpha, 0.7, 1e-9, "hold glow")
    stepTo(run, 101.03, 101.5, 60)            -- after the 250ms flare window
    near(fx.flare._vc[1], 0.659, 1e-6, "flare eased back"); near(fx.flare._vc[3], 0.969, 1e-6)
    eq(finished, 0, "still holding")
    stepTo(run, 101.5, 101.99, 60)
    eq(finished, 0, "hold lasts 1.0s")
    at(run, 102.15)                           -- 150ms into the 300ms fade
    near(run.segs[1].lit._vc[4], 0.5, 0.02, "fade is flat and linear")
    stepTo(run, 102.15, 102.29, 60)
    eq(finished, 0, "fade lasts 300ms")
    at(run, 102.31)
    eq(finished, 1, "onFinished after hold + fade")
    eq(run:IsBusy(), false)
    eq(run.frame:GetScript("OnUpdate"), nil, "OnUpdate cleared")
    near(fx.holdGlow._alpha, 0, 1e-9, "hold glow cleared")
end

function T.new_cast_cancels_hold_and_lock_in()
    local fx = withEffects()
    local run = mk({ flareTarget = fx.flare, glowBurst = fx.glow, holdGlow = fx.holdGlow, scaleTarget = fx.pop })
    local finished = 0
    run.onFinished = function() finished = finished + 1 end
    run:StartCast(100, 100 + CAST, false)
    run:SetProgressOverride(0.5)
    at(run, 101)
    run:Succeed()
    at(run, 101.05)
    at(run, 101.5)
    ok(run:StartCast(101.5, 101.5 + CAST, false), "new cast accepted during hold")
    eq(run.phase, "cast")
    eq(run.burst._groups[1].stops >= 1 and run.burst._groups[1].playing, false, "burst stopped")
    eq(run.burst._shown, false); eq(fx.glow._shown, false)
    near(fx.flare._vc[1], 0.659, 1e-6, "flare restored")
    near(fx.holdGlow._alpha, 0, 1e-9, "hold glow off")
    stepTo(run, 101.5, 104.2, 60)
    eq(finished, 0, "the cancelled hold never finishes")
end

-- ---- interrupt ---------------------------------------------------------

local function startInterrupted(opts)
    local run = mk(opts)
    run.finishedCount = 0
    run.onFinished = function(r) r.finishedCount = r.finishedCount + 1 end
    run:StartCast(100, 100 + CAST, false)
    run:SetProgressOverride(0.5)
    at(run, 101)
    stepTo(run, 101, 101.5, 60)
    __now = 110
    ok(run:Interrupt(), "Interrupt accepted")
    return run, 110
end

function T.interrupt_phase_boundaries_and_finish()
    local run, t0 = startInterrupted()
    at(run, t0 + 0.24); eq(run.intrPhase, "brown")
    at(run, t0 + 0.26); eq(run.intrPhase, "stutter")
    at(run, t0 + 0.54); eq(run.intrPhase, "stutter")
    at(run, t0 + 0.56); eq(run.intrPhase, "cut")
    at(run, t0 + 0.79); eq(run.intrPhase, "cut")
    at(run, t0 + 0.81); eq(run.intrPhase, "fade")
    near(run.alphaTarget:GetAlpha(), 1 - 0.7 * ((0.81 - 0.80) / 0.20), 1e-6, "outage fade dims the target")
    eq(run.finishedCount, 0)
    at(run, t0 + 0.99)
    eq(run.finishedCount, 0, "not finished before 1.0s")
    at(run, t0 + 1.0)
    eq(run.finishedCount, 1, "onFinished at 1.0s")
    eq(run:IsBusy(), false); eq(run.frame:GetScript("OnUpdate"), nil, "OnUpdate cleared")
end

function T.interrupt_brownout_and_stutter_peak()
    local run, t0 = startInterrupted()
    local s = run.segs[2]                     -- lit (b = 0.2 <= 0.5), jit 0.8100013923831284
    -- Brownout at u = 0.4: level 1 - 0.6 * ease(0.4) = 0.7888, warm tint pulls red up.
    at(run, t0 + 0.1)
    near(s.lit._vc[4], 1 - 0.6 * (0.4 * 0.4 * (3 - 0.8)), 1e-6, "brownout level")
    ok(s.lit._vc[1] > 0.133 + 0.1, "warm tint raises red")
    -- Stutter: the second surge peaks at u = (0.55 + jit * 0.05 + 0.72) / 2 and reaches full level.
    local u = (0.55 + s.jit * 0.05 + 0.72) / 2
    at(run, t0 + 0.25 + 0.30 * u)
    near(s.lit._vc[4], 1.0, 0.01, "stutter peak is full level")
end

function T.interrupt_cut_out_runs_from_the_leading_edge_back()
    local run, t0 = startInterrupted()
    local gone = {}
    local lastLit = 0
    for i = 1, run.count do if run.segs[i].b <= 0.5 then lastLit = i end end
    ok(lastLit >= 4, "enough lit segments to order")
    local t = t0 + 0.55
    while t < t0 + 0.80 do
        t = t + 0.001
        at(run, t)
        for i = 1, lastLit do
            if gone[i] == nil and not run.segs[i].lit._shown then gone[i] = t end
        end
    end
    for i = 1, lastLit do ok(gone[i], "segment " .. i .. " is cut out") end
    for i = 2, lastLit do
        ok(gone[i] < gone[i - 1], "segment " .. i .. " goes before segment " .. (i - 1))
    end
end

-- ---- channel -----------------------------------------------------------

function T.channel_cascades_in_then_drains_right_to_left_mirrored()
    local run = mk()
    ok(run:StartCast(100, 200, true), "channel accepted")        -- long: progress stays about 0
    -- Mirrored textures; the stagger runs right to left (right-most starts first).
    eq(run.segs[1].lit._tc[1], 1); eq(run.segs[1].lit._tc[2], 0, "segments mirrored")
    eq(run.outline._tc[1], 1); eq(run.outline._tc[2], 0, "caret outline mirrored")
    eq(run.glow._tc[1], 1); eq(run.glow._tc[2], 0, "caret glow mirrored")
    for i = 1, run.count - 1 do
        ok(run.segs[i].litSince > run.segs[i + 1].litSince, "stagger " .. i)
    end
    near(run.segs[1].litSince - run.segs[run.count].litSince, (run.segs[run.count].frac - run.segs[1].frac) * 350, 1e-6)
    at(run, 100.2)
    eq(lit(run.segs[run.count]), true, "right-most lit first")
    eq(lit(run.segs[1]), false, "left-most still waiting")
    stepTo(run, 100.2, 100.8, 60)
    eq(litCount(run), run.count, "all lit once the cascade is done")
    -- Drain: lit segments are always a prefix, shrinking as progress grows.
    local prev = run.count + 1
    for _, p in ipairs({ 0.2, 0.4, 0.6, 0.8 }) do
        run:SetProgressOverride(p)
        at(run, 101 + p)
        local n = 0
        for i = 1, run.count do
            if lit(run.segs[i]) then
                ok(i == n + 1, "lit segments form a prefix at p=" .. p)
                n = n + 1
            end
        end
        ok(n < prev, "drains as progress grows"); prev = n
    end
    -- Caret: mirrored, tip (left edge) at f * W, box extends to the right.
    run:SetProgressOverride(0.25)
    at(run, 102)
    eq(run.clip._shown, true)
    near(run.outline._points["TOPLEFT"].x, 0.75 * 150, 1e-6, "channel caret tip")
    -- With the finish switched off a channel ends at once (the old behaviour).
    run:SetChannelFinish("none")
    local finished = 0
    run.onFinished = function() finished = finished + 1 end
    ok(run:Succeed())
    eq(finished, 1, "channel finishes at once"); eq(run.burst._groups[1].plays, 0, "no burst")
    -- A following cast un-mirrors.
    run:StartCast(103, 105.5, false)
    eq(run.segs[1].lit._tc[1], 0); eq(run.outline._tc[1], 0); eq(run.outline._tc[2], 1)
    eq(run.glow._tc[1], 0); eq(run.glow._tc[2], 1, "caret un-mirrored")
end

-- ---- channel finish (natural end only) ------------------------------------

-- A 3s channel run to its natural end on the stepped clock (empty bar, no verdict yet).
local function runChannel(opts)
    local fx = withEffects()
    opts = opts or {}
    opts.flareTarget, opts.glowBurst, opts.holdGlow, opts.scaleTarget = fx.flare, fx.glow, fx.holdGlow, fx.pop
    local run = mk(opts)
    run.finishedCount = 0
    run.onFinished = function(r) r.finishedCount = r.finishedCount + 1 end
    ok(run:StartCast(100, 103, true), "channel accepted")
    stepTo(run, 100, 103, 60)
    return run, fx
end

function T.lock_in_has_no_scale_pop_by_default_and_lock_snap_brings_it_back()
    local function lockedIn(opts)
        local fx = withEffects()
        opts = opts or {}
        opts.scaleTarget, opts.glowBurst = fx.pop, fx.glow
        local run = mk(opts)
        run:StartCast(100, 100 + CAST, false); run:SetProgressOverride(0.5); at(run, 101)
        ok(run:Succeed())
        return run, fx
    end
    local run, fx = lockedIn()
    eq(#fx.pop._groups, 0, "default: no pop group"); eq(run.burst._groups[1].plays, 1, "chevron burst"); eq(fx.glow._groups[1].plays, 1, "glow burst")
    run, fx = lockedIn({ lockSnap = true })
    eq(#fx.pop._groups, 1, "lockSnap builds the pop"); eq(fx.pop._groups[1].plays, 1, "and plays it at lock-in")
    local a = fx.pop._groups[1]._anims
    eq(a[1]._args.SetScaleTo[1], 1.04, "up to 1.04"); eq(a[2]._args.SetScaleTo[1], 1, "and back to 1.0")
    run:Stop(); eq(fx.pop._groups[1].playing, false, "Stop cancels the pop")
    -- Reduced motion never pops, even with lockSnap.
    run, fx = lockedIn({ lockSnap = true, reducedMotion = true })
    eq(#fx.pop._groups, 0, "reduced motion: no pop")
    -- A channel finish never scales the bar.
    local ch, cfx = runChannel({ lockSnap = true })
    ok(ch:EndChannel()); eq(#cfx.pop._groups, 1, "the pop group exists"); eq(cfx.pop._groups[1].plays, 0, "but a channel finish does not play it")
end

function T.channel_natural_end_plays_the_drain_burst_by_default()
    local run, fx = runChannel()
    eq(run:EndChannel(), true, "a natural end plays the finish")
    eq(run:GetPhase(), "hold"); ok(run:IsFinishing(), "finishing")
    eq(run.burst._groups[1].plays, 1, "chevron burst"); eq(fx.glow._groups[1].plays, 1, "glow burst")
    -- At the left end (the last chevron to go out), pointing left.
    near(run.burst._points["CENTER"].x, run.segs[1].x0 + run.segs[1].lit._w / 2, 1e-6, "burst on the leftmost chevron")
    eq(run.burst._tc[1], 1, "burst mirrored"); eq(run.burst._tc[2], 0)
    eq(#fx.pop._groups, 0, "no scale pop")
    at(run, 103.03)
    ok(fx.flare._vc[1] > 0.8, "frame flare")
    eq(litCount(run), 0, "drain leaves the run empty")
    stepTo(run, 103.03, 103.99, 60)
    eq(run.finishedCount, 0, "the finish lasts the hold")
    at(run, 104.01)
    eq(run.finishedCount, 1, "onFinished at the end of the hold"); eq(run:IsBusy(), false)
    eq(run.frame:GetScript("OnUpdate"), nil, "OnUpdate cleared")
    near(fx.flare._vc[1], 0.659, 1e-6, "flare restored")
    -- A later cast puts the burst back on the right end, unmirrored.
    run:StartCast(104.1, 107, false); run:SetProgressOverride(0.5); at(run, 104.5)
    run:Succeed()
    near(run.burst._points["CENTER"].x, run.span - run.segs[1].lit._w / 2, 1e-6, "cast burst on the last chevron")
    eq(run.burst._tc[1], 0, "unmirrored")
end

function T.channel_end_is_judged_by_the_engines_own_schedule_a_clip_gets_the_plain_stop()
    -- Early stop (a clip): plain Stop, no animation, no onFinished.
    local run, fx = runChannel()
    run:StartCast(103, 106, true); stepTo(run, 103, 104.5, 60)
    eq(run:EndChannel(), false, "mid-channel stop is a clip")
    eq(run:GetPhase(), "idle"); eq(run.frame._shown, false, "stopped")
    eq(run.burst._groups[1].plays, 0, "no burst"); eq(fx.glow._groups[1].plays, 0, "no glow")
    eq(run.finishedCount, 0, "Stop does not fire onFinished")
    -- The window: 0.1s before the end is natural, 0.3s is not.
    local a = runChannel()
    a:StartCast(103, 106, true); stepTo(a, 103, 105.9, 60)
    eq(a:EndChannel(), true, "0.1s before the end is natural")
    local b = runChannel()
    b:StartCast(103, 106, true); stepTo(b, 103, 105.7, 60)
    eq(b:EndChannel(), false, "0.3s before the end is a clip")
    -- A pushback (CHANNEL_UPDATE) moves the end: a stop at the old end is now a clip.
    local c = runChannel()
    c:StartCast(103, 106, true); stepTo(c, 103, 105.95, 60)
    ok(c:UpdateTimes(103, 108), "retimed")
    __now = 106
    eq(c:EndChannel(), false, "the retimed end has not come")
    -- Not a running channel, or a verdict already playing: ignored (nil), nothing touched.
    local d = mk()
    eq(d:EndChannel(), nil, "idle")
    d:StartCast(100, 102.5, false); d:SetProgressOverride(0.5); at(d, 101)
    eq(d:EndChannel(), nil, "a cast is not a channel"); eq(d:GetPhase(), "cast")
    local e = runChannel(); e:EndChannel()
    eq(e:EndChannel(), nil, "already finishing"); eq(e:GetPhase(), "hold")
end

function T.channel_finish_styles_echo_sweep_ember_none()
    -- Echo: the whole row as a near-white ghost, frame flare and glow burst, no chevron burst.
    local run, fx = runChannel({ channelFinish = "echo" })
    ok(run:EndChannel()); at(run, 103.04)
    eq(litCount(run), run.count, "echo lights every chevron")
    near(run.segs[3].lit._vc[4], 0.6 * (1 - 0.04), 1e-3, "echo alpha")
    ok(run.segs[3].lit._vc[1] > 0.7, "near-white ghost")
    eq(run.burst._groups[1].plays, 0, "no chevron burst"); eq(fx.glow._groups[1].plays, 1, "glow burst")
    at(run, 103.9)
    eq(litCount(run), run.count, "still fading near the end"); near(run.segs[3].lit._vc[4], 0.6 * (1 - 0.9), 1e-3)
    -- Sweep: a wave left to right; no frame flare, glow or burst.
    run, fx = runChannel({ channelFinish = "sweep" })
    ok(run:EndChannel()); at(run, 103.05)
    eq(lit(run.segs[1]), true, "wave starts at the left"); eq(lit(run.segs[run.count]), false, "not at the right yet")
    near(fx.flare._vc[1], 0.659, 1e-6, "no flare"); eq(fx.glow._groups[1].plays, 0, "no glow burst")
    at(run, 103.3)
    eq(lit(run.segs[run.count]), true, "wave reached the right")
    local t0 = run.segs[run.count].frac * 150          -- the wave's arrival at the last chevron
    near(run.segs[run.count].lit._vc[4], 0.4 * (1 - (300 - t0 - 30) / (1000 - t0 - 30)), 0.02, "cyan afterglow tail")
    -- Ember: only the last chevron to go out (the leftmost), its own small burst, frame flare, no glow burst.
    run, fx = runChannel({ channelFinish = "ember" })
    ok(run:EndChannel()); at(run, 103.05)
    eq(litCount(run), 1, "one chevron"); eq(lit(run.segs[1]), true, "the leftmost")
    near(run.segs[1].lit._vc[4], 0.05 / 0.6 / 0.1, 1e-3, "ember alpha still on its attack")
    eq(run.burst._groups[1].plays, 0, "not the drain burst"); eq(run.burst._groups[2].plays, 1, "ember burst")
    eq(fx.glow._groups[1].plays, 0, "no glow burst"); ok(fx.flare._vc[1] > 0.8, "frame flare")
    -- None, or a hold under 80ms: the plain Stop. An unknown style falls back to drain.
    run = runChannel({ channelFinish = "none" })
    eq(run:EndChannel(), false, "none"); eq(run.frame._shown, false)
    run = runChannel({ holdMs = 50 })
    eq(run:EndChannel(), false, "hold under 80ms")
    run = runChannel({ channelFinish = "bogus" })
    eq(run:EndChannel(), true); eq(run.burst._groups[1].plays, 1, "drain")
end

function T.channel_finish_reduced_motion_is_short_and_has_no_scale_or_whitening()
    local run, fx = runChannel({ channelFinish = "echo", reducedMotion = true })
    ok(run:EndChannel()); at(run, 103.04)
    near(run.segs[3].lit._vc[4], 0.6 * (1 - 0.2), 1e-3, "echo alpha over the 200ms finish")
    near(run.segs[3].lit._vc[1], run.baseR, 1e-6, "no near-white")
    eq(run.finishedCount, 0); at(run, 103.21)
    eq(run.finishedCount, 1, "the finish is cut to 200ms")
    local drain = runChannel({ reducedMotion = true })
    ok(drain:EndChannel()); eq(drain.burst._groups[1]._anims[1]._kind, "Alpha", "burst is alpha only, no scale")
    -- Sweep: no wave and no whitening, every chevron fades together at the base color, 200ms long.
    local sw = runChannel({ channelFinish = "sweep", reducedMotion = true })
    ok(sw:EndChannel()); at(sw, 103.04)
    eq(litCount(sw), sw.count, "no wave: every chevron is lit at once")
    near(sw.segs[1].lit._vc[4], 0.5 * (1 - 0.2), 1e-3, "sweep alpha over the 200ms finish")
    near(sw.segs[sw.count].lit._vc[4], 0.5 * (1 - 0.2), 1e-3, "the same alpha at the far end")
    near(sw.segs[1].lit._vc[1], sw.baseR, 1e-6, "no near-white"); near(sw.segs[1].lit._vc[2], sw.baseG, 1e-6)
    eq(sw.finishedCount, 0); at(sw, 103.21)
    eq(sw.finishedCount, 1, "cut to 200ms"); eq(litCount(sw), 0, "and cleared")
end

function T.succeed_on_a_channel_plays_the_default_drain_finish_and_waits_for_the_hold()
    local run, fx = runChannel()
    ok(run:Succeed(), "Succeed on a channel")
    eq(run:GetPhase(), "hold", "enters the hold"); ok(run:IsFinishing(), "finishing")
    eq(run.finishedCount, 0, "onFinished does not fire at once")
    eq(run.burst._groups[1].plays, 1, "the drain chevron burst plays"); eq(fx.glow._groups[1].plays, 1, "and the glow burst")
    eq(run.burst._tc[1], 1, "pointing left, at the leftmost chevron")
    stepTo(run, 103, 103.99, 60)
    eq(run.finishedCount, 0, "still waiting through the hold"); eq(run:GetPhase(), "hold")
    at(run, 104.01)
    eq(run.finishedCount, 1, "onFinished after the hold"); eq(run:IsBusy(), false)
    -- "none" ends at once.
    local none = runChannel({ channelFinish = "none" })
    ok(none:Succeed()); eq(none.finishedCount, 1, "none: onFinished at once"); eq(none:GetPhase(), "idle")
end

function T.channel_early_natural_end_in_drain_clears_the_still_lit_chevrons()
    local run = mk()
    run.finishedCount = 0
    run.onFinished = function(r) r.finishedCount = r.finishedCount + 1 end
    ok(run:StartCast(100, 103, true), "channel accepted")
    stepTo(run, 100, 102.9, 60)
    ok(litCount(run) > 0, "chevrons are still lit just before the scheduled end")
    eq(run:EndChannel(), true, "0.1s early is still a natural end")
    eq(litCount(run), 0, "drain: the lit chevrons are cleared at once")
    stepTo(run, 102.9, 103.5, 60)
    eq(litCount(run), 0, "and none relight through the drain")
    -- The finish clock starts at the EndChannel call, not at the scheduled end.
    stepTo(run, 103.5, 103.89, 60)
    eq(run.finishedCount, 0, "still inside the hold")
    at(run, 103.91)
    eq(run.finishedCount, 1, "onFinished one hold after EndChannel")
end

function T.set_channel_finish_mid_play_applies_to_the_next_finish_and_rejects_bad_modes()
    local run, fx = runChannel({ channelFinish = "echo" })
    ok(run:EndChannel()); at(run, 103.1)
    ok(run:SetChannelFinish("ember"), "accepted mid-play")
    at(run, 103.5)
    eq(litCount(run), run.count, "the running echo keeps painting every chevron")
    near(run.segs[3].lit._vc[4], 0.6 * (1 - 0.5), 1e-3, "echo alpha keeps fading (not frozen)")
    eq(run.burst._groups[2].plays, 0, "no ember burst joins the running echo")
    stepTo(run, 103.5, 104.01, 60)
    eq(run.finishedCount, 1, "the echo ends on its own clock"); eq(litCount(run), 0)
    -- The next finish is the ember.
    ok(run:StartCast(104.1, 107, true), "next channel")
    stepTo(run, 104.1, 107, 60)
    ok(run:EndChannel()); at(run, 107.05)
    eq(litCount(run), 1, "ember: one chevron"); eq(run.burst._groups[2].plays, 1, "ember burst")
    -- A bad mode is refused and leaves the mode alone.
    eq(run:SetChannelFinish("bogus"), false, "bogus refused"); eq(run.channelFinish, "ember", "mode unchanged")
    eq(run:SetChannelFinish(nil), false, "nil refused"); eq(run.channelFinish, "ember", "mode unchanged")
    local oks, rs = pcall(run.SetChannelFinish, run, __SECRET)
    ok(oks and rs == false, "a secret mode is refused without throwing"); eq(run.channelFinish, "ember", "mode unchanged")
    eq(run:SetChannelFinish("sweep"), true, "a real mode is accepted"); eq(run.channelFinish, "sweep")
end

function T.channel_finish_cleans_up_and_a_new_cast_cancels_it()
    local run, fx = runChannel({ channelFinish = "sweep" })
    ok(run:EndChannel()); stepTo(run, 103, 104.01, 60)
    eq(run.finishedCount, 1); eq(litCount(run), 0, "every ghost gone at the end")
    run, fx = runChannel({ channelFinish = "echo" })
    ok(run:EndChannel()); at(run, 103.1)
    ok(run:StartCast(103.1, 106, false), "a new cast during the finish")
    eq(run.phase, "cast"); eq(litCount(run), 0, "ghosts cleared")
    eq(run.burst._shown, false); eq(fx.glow._shown, false); near(fx.flare._vc[1], 0.659, 1e-6, "flare restored")
    stepTo(run, 103.1, 104.5, 60)
    eq(run.finishedCount, 0, "the cancelled finish never completes")
end

-- ---- fit width -------------------------------------------------------------------

function T.fit_width_adds_the_chevron_the_mockup_adds()
    -- The mockup's four bars: the run holds n chevrons with 4 units of slack, and the bar grows by
    -- (pitch - slack) to hold one more with none: pet 180 -> 183 (17), player 320 -> 328 (19),
    -- stack 260 -> 268 (14), stackw 440 -> 448 (29). Run widths here are span(n) + 4.
    local rows = {
        { h = 10, gap = 0.2, span = 115, delta = 3, n = 17 },
        { h = 18, span = 222, delta = 8, n = 19 },
        { h = 18, span = 162, delta = 8, n = 14 },
        { h = 18, span = 342, delta = 8, n = 29 },
    }
    for i, r in ipairs(rows) do
        local run = mk({ width = r.span + 4, height = r.h, gapFraction = r.gap })
        local want = r.span + 4 + r.delta
        near(run:FitWidth(r.span + 4), want, 1e-9, "row " .. i .. " fitted width")
        run:Layout(want, r.h)
        eq(run.count, r.n, "row " .. i .. " chevrons"); near(run.span, want, 1e-9, "row " .. i .. " zero slack")
        near(run:FitWidth(want), want, 1e-9, "an exact fit stays")
        near(run:FitWidth(want + 1), want + run.pitch, 1e-9, "one more unit adds a chevron")
    end
    -- Height may be passed before any Layout.
    local fresh = CCB.Create(CreateFrame("Frame", nil, UIParent), { points = { { "TOPLEFT" } }, gapFraction = 0.2 })
    near(fresh:FitWidth(119, 10), 122, 1e-9, "no prior Layout: height argument")
    -- Unusable arguments return nil (never a width, never a throw).
    local bad = mk({ width = 119, height = 10, gapFraction = 0.2 })
    eq(bad:FitWidth(__SECRET), nil, "secret"); eq(bad:FitWidth(0 / 0), nil, "NaN")
    eq(bad:FitWidth(-5), nil, "negative"); eq(bad:FitWidth(math.huge), nil, "infinite")
    eq(bad:FitWidth(nil), nil, "nil"); eq(bad:FitWidth("119"), nil, "not a number")
    eq(bad:FitWidth(119, __SECRET), nil, "secret height"); eq(bad:FitWidth(119, 0), nil, "zero height")
end

function T.fit_width_is_minimal_and_zero_slack_on_every_pixel_grid()
    eachGrid(function(run, px, tag)
        local req = run.W
        local f = run:FitWidth(req)
        ok(f >= req - 1e-9, tag .. ": never smaller than requested")
        ok(f - run.pitch < req - 1e-9, tag .. ": the smallest such width (one chevron less is too small)")
        local n = run.count
        run:Layout(f, run.H)
        near(run.span, run.W, 1e-6, tag .. ": zero slack")
        ok(run.count >= n, tag .. ": whole chevrons")
    end)
end

function T.fit_within_returns_the_largest_whole_chevron_span_that_fits()
    -- The pet console dock: a 14 high run, gap fraction 0.2 -> box 14, arm 7, gap 3, pitch 10 at scale 1.
    __physH = 768; __setUIScale(1)
    local pet = mk({ width = 111, height = 14, gapFraction = 0.2 })
    near(pet.pitch, 10, 1e-9, "pet pitch is 10")
    near(pet:FitWithin(111, 14), 104, 1e-9, "111 px track: 10 chevrons")
    near(pet:FitWidth(111, 14), 114, 1e-9, "FitWidth still rounds the same track UP to 11 chevrons")
    near(pet:FitWithin(112), 104, 1e-9, "112 px track: still 10 (height defaults to the last layout)")
    near(pet:FitWithin(114, 14), 114, 1e-9, "an exact fit is returned as is: 11 chevrons")
    near(pet:FitWithin(113.9, 14), 104, 1e-9, "a hair under 11 stays at 10")
    -- Never over max, whole chevrons, and the largest such span, on three UI scales and two run shapes.
    for _, sc in ipairs({ 1, 0.8333, 0.64 }) do
        __physH = 768; __setUIScale(sc)
        for _, o in ipairs({ { height = 14, gapFraction = 0.2 }, { height = 18 } }) do
            local run = mk({ width = 200, height = o.height, gapFraction = o.gapFraction })
            local px = pixelOf(run)
            local tag = "scale " .. sc .. " h" .. o.height
            local wPx = math.floor(o.height / px + 0.5 + 1e-6)
            local checked = 0
            for m = 20, 260, 1.7 do
                local f = run:FitWithin(m, o.height)
                if f == nil then
                    ok(math.floor(m / px + 1e-6) < wPx, tag .. ": nil only when no chevron fits (max " .. m .. ")")
                else
                    checked = checked + 1
                    ok(f <= m + 1e-9, tag .. ": never over max " .. m)
                    ok(f + run.pitch > m - 1e-6, tag .. ": the largest span (one more chevron would not fit) at " .. m)
                    run:Layout(f, o.height)
                    near(run.span, f, 1e-6, tag .. ": whole chevrons, zero slack at " .. m)
                    near(run:FitWithin(m, o.height), f, 1e-9, tag .. ": idempotent")
                    ok(isWhole(f / px, 1e-6), tag .. ": on the pixel grid")
                end
            end
            ok(checked > 20, tag .. ": the sweep reached real results")
            -- Less than one chevron: nil. Exactly one: that chevron.
            run:Layout(200, o.height)
            local boxW = run.segW
            eq(run:FitWithin(boxW - px * 0.5, o.height), nil, tag .. ": half a pixel short of one chevron")
            near(run:FitWithin(boxW, o.height), boxW, 1e-9, tag .. ": exactly one chevron")
            -- FitWithin and FitWidth bracket the request: down and up, at most one pitch apart.
            local fw, fi = run:FitWidth(150, o.height), run:FitWithin(150, o.height)
            ok(fi <= 150 + 1e-9 and fw >= 150 - 1e-9 and fw - fi <= run.pitch + 1e-6, tag .. ": brackets the request with FitWidth")
        end
    end
    __physH = 768; __setUIScale(1)
    -- Unusable arguments return nil, like FitWidth.
    local bad = mk({ width = 111, height = 14, gapFraction = 0.2 })
    eq(bad:FitWithin(__SECRET), nil, "secret"); eq(bad:FitWithin(0 / 0), nil, "NaN")
    eq(bad:FitWithin(-5), nil, "negative"); eq(bad:FitWithin(0), nil, "zero")
    eq(bad:FitWithin(math.huge), nil, "infinite"); eq(bad:FitWithin(nil), nil, "nil")
    eq(bad:FitWithin("111"), nil, "not a number")
    eq(bad:FitWithin(111, __SECRET), nil, "secret height"); eq(bad:FitWithin(111, 0), nil, "zero height")
    -- Vertical runs: nil, as FitWidth.
    local v = CCB.Create(CreateFrame("Frame", nil, UIParent), { width = 20, height = 100, vertical = true, textures = CCB.TEXTURES_UP })
    eq(v:FitWithin(100), nil, "vertical: FitWithin is a horizontal feature")
    eq(v:FitWidth(100), nil, "vertical: FitWidth still nil")
end

function T.fit_mode_refits_through_onlayout_when_scale_or_display_changes()
    __physH = 768; __setUIScale(1)
    local run = mk({ width = 119, height = 10, gapFraction = 0.2, fitWidth = true })
    near(run.W, 122, 1e-9, "fitted at creation"); near(run.span, run.W, 1e-9, "zero slack")
    local seen = {}
    run.onLayout = function(r) seen[#seen + 1] = r.W end
    __setUIScale(0.64); __fire("UI_SCALE_CHANGED")
    eq(#seen, 1, "onLayout fires on the rescale")
    ok(seen[1] >= 119, "still at least the request"); near(run.span, run.W, 1e-6, "zero slack at the new pitch")
    ok(math.abs(seen[1] - 122) > 1e-6, "a new pixel pitch gives a new width")
    __physH = 1440; __fire("DISPLAY_SIZE_CHANGED")
    eq(#seen, 2, "and on a display change"); near(run.span, run.W, 1e-6)
    __physH = 768; __setUIScale(1); __fire("UI_SCALE_CHANGED")
    near(run.W, 122, 1e-9, "the request is remembered, so it comes back")
end

-- ---- reduced motion ----------------------------------------------------

function T.reduced_motion_snaps_dims_and_skips_motion()
    local fx = withEffects()
    local run = mk({ reducedMotion = true, scaleTarget = fx.pop, glowBurst = fx.glow })
    run:StartCast(100, 100 + CAST, false)
    run:SetProgressOverride(0.37)
    at(run, 101)
    local s5 = run.segs[4]
    eq(lit(s5), true, "ignite snaps on the very first frame")
    near(s5.lit._vc[1], 0.133, 0.01); near(s5.lit._vc[4], 1, 1e-9)
    eq(#fx.pop._groups, 0, "no scale pop group")
    -- Outage is a plain dim of 1 - t over 1.0s.
    __now = 102
    ok(run:Interrupt())
    at(run, 102.5)
    near(s5.lit._vc[4], 0.5, 1e-6, "plain dim")
    near(s5.lit._vc[1], 0.133, 0.01, "no warm tint")
end

-- ---- OnUpdate, allocation, secrets --------------------------------------

function T.onupdate_is_installed_only_while_animating()
    local run = mk()
    eq(run.frame:GetScript("OnUpdate"), nil, "idle before a cast")
    run:StartCast(100, 101, false)
    ok(run.frame:GetScript("OnUpdate") ~= nil, "installed while casting")
    stepTo(run, 100, 101.3, 60)               -- cast done, ignites settled, no verdict yet
    ok(run.frame:GetScript("OnUpdate") ~= nil, "kept while the verdict window is open")
    eq(run:IsBusy(), true, "still busy until Succeed/Interrupt/Stop")
    run:Succeed()
    ok(run.frame:GetScript("OnUpdate") ~= nil, "back while holding")
    run:Stop()
    eq(run.frame:GetScript("OnUpdate"), nil, "cleared by Stop")
    eq(run:IsBusy(), false); eq(run.frame._shown, false, "Stop hides")
end

function T.steady_frame_touches_only_the_caret()
    local run = mk()
    run:StartCast(100, 110, false)            -- 10s cast: a segment lights every 0.8s
    stepTo(run, 100, 104, 60)                 -- segment 4 lit at 3.6s and settled; segment 5 lights at 4.4s
    for _, k in ipairs({ "SetVertexColor", "SetShown", "SetAlpha", "SetSize", "ClearAllPoints", "SetPoint" }) do
        __stats[k] = 0
    end
    local frames = 0
    local t = 104
    while t < 104 + 14 / 60 do t = t + 1 / 60; at(run, t); frames = frames + 1 end
    eq(__stats.SetVertexColor or 0, 0, "no color writes")
    eq(__stats.SetShown or 0, 0, "no visibility writes")
    eq(__stats.SetSize or 0, 0, "no resizes"); eq(__stats.ClearAllPoints or 0, 0, "no re-anchors")
    ok((__stats.SetPoint or 0) <= frames, "at most one SetPoint per frame (the caret)")
    ok((__stats.SetPoint or 0) > 0, "the caret moves")
end

-- Bytes the Lua code allocates over `frames` frames after `warm` untimed ones.
-- JIT trace compilation allocates GC objects of its own, which would drown the
-- measurement; callers switch it off first.
local function allocOver(run, t, warm, frames)
    for _ = 1, warm do t = t + 1 / 60; at(run, t) end
    collectgarbage(); collectgarbage()
    collectgarbage("stop")
    local before = collectgarbage("count")
    for _ = 1, frames do t = t + 1 / 60; at(run, t) end
    local grown = collectgarbage("count") - before
    collectgarbage("restart")
    return grown, t
end

function T.no_per_frame_allocation()
    -- The interpreter shows exactly what the Lua code allocates.
    if jit then jit.off() end
    local run = mk()
    run:StartCast(100, 100 + 12, false)       -- 12s cast: 720 frames, so 600 sit inside it
    local grown, t = allocOver(run, 100, 90, 600)
    -- Interrupt too: brownout, stutter, cut-out and fade repaint every segment every frame.
    __now = t
    run:Interrupt()
    local grown2 = allocOver(run, t, 0, 62)
    -- A table per frame would be at least 600 * 40 bytes = 23 KB.
    ok(grown < 1.0, "cast frames allocated " .. grown .. " KB")
    ok(grown2 < 1.0, "outage frames allocated " .. grown2 .. " KB")
end

function T.no_per_frame_allocation_in_hold_fade_and_channel()
    if jit then jit.off() end
    -- Hold (60 frames) then fade (18 frames) then the finish, with every effect wired.
    local fx = withEffects()
    local run = mk({ flareTarget = fx.flare, glowBurst = fx.glow, holdGlow = fx.holdGlow, scaleTarget = fx.pop })
    run:StartCast(100, 112, false)
    run:SetProgressOverride(0.5)
    local t = 100
    for _ = 1, 10 do t = t + 1 / 60; at(run, t) end
    __now = t
    ok(run:Succeed())
    local grown = allocOver(run, t, 5, 80)
    eq(run:IsBusy(), false, "the measured window covered the whole finish")
    ok(grown < 1.0, "hold/fade frames allocated " .. grown .. " KB")
    -- Channel: the right-to-left cascade, then the mirrored drain with its caret.
    local ch = mk()
    ch:StartCast(100, 112, true)
    local grown3 = allocOver(ch, 100, 5, 600)
    ok(grown3 < 1.0, "channel frames allocated " .. grown3 .. " KB")
    -- The channel finish (sweep paints every chevron every frame).
    local cf = mk({ channelFinish = "sweep" })
    cf:StartCast(100, 103, true)
    local t2 = stepTo(cf, 100, 103, 60)
    __now = t2
    ok(cf:EndChannel())
    local grown4 = allocOver(cf, t2, 5, 50)
    ok(grown4 < 1.0, "channel finish frames allocated " .. grown4 .. " KB")
end

function T.secret_times_are_refused_without_throwing()
    local run = mk()
    local ok1, r1 = pcall(run.StartCast, run, __SECRET, 105, false)
    local ok2, r2 = pcall(run.StartCast, run, 100, __SECRET, false)
    local ok3, r3 = pcall(run.StartCast, run, nil, 105, false)
    ok(ok1 and ok2 and ok3, "no throw")
    eq(r1, false); eq(r2, false); eq(r3, false)
    eq(run:IsBusy(), false, "no state change"); eq(run.frame:GetScript("OnUpdate"), nil)
    ok(run:StartCast(100, 105, false), "a plain cast still works afterwards")
end

-- ---- verdict API, safety net, guards -------------------------------------

function T.phase_queries_follow_the_state_machine()
    local run = mk()
    eq(run:GetPhase(), "idle"); eq(run:IsFinishing(), false); eq(run:IsComplete(), false)
    run:StartCast(100, 100 + CAST, false)
    eq(run:GetPhase(), "cast"); eq(run:IsFinishing(), false)
    __now = 100 + CAST - 0.01
    eq(run:IsComplete(), false, "not complete a hair before the end")
    __now = 100 + CAST
    eq(run:IsComplete(), true, "complete once progress reaches 1, before any frame ticks")
    near(run:GetProgress(), 1, 1e-9)
    ok(run:Succeed())
    eq(run:GetPhase(), "hold"); eq(run:IsFinishing(), true); eq(run:IsComplete(), false, "hold is not a cast")
    at(run, 100 + CAST + 1.05)
    eq(run:GetPhase(), "fade"); eq(run:IsFinishing(), true)
    at(run, 100 + CAST + 1.4)
    eq(run:GetPhase(), "idle"); eq(run:IsFinishing(), false)
    __now = 111
    run:StartCast(110, 112.5, false)
    ok(run:Interrupt())
    eq(run:GetPhase(), "intr"); eq(run:IsFinishing(), true)
end

function T.dropped_verdict_auto_succeeds_a_finished_cast()
    local run = mk()
    local fin = 0
    run.onFinished = function() fin = fin + 1 end
    run:StartCast(100, 101, false)
    stepTo(run, 100, 101.4, 60)
    eq(run:GetPhase(), "cast", "waits for a verdict inside the grace window")
    ok(run.frame:GetScript("OnUpdate") ~= nil, "OnUpdate alive for the window")
    at(run, 101.6)
    eq(run:GetPhase(), "hold", "auto Succeed after 0.5s with no verdict")
    eq(run.burst._groups[1].plays, 1, "lock-in played")
    stepTo(run, 101.6, 103.0, 60)
    eq(fin, 1, "onFinished fired once"); eq(run:IsBusy(), false)
    eq(run.frame:GetScript("OnUpdate"), nil, "OnUpdate cleared afterwards")
end

function T.dropped_verdict_ends_a_channel_with_stop_and_on_finished()
    local run = mk()
    local fin = 0
    run.onFinished = function() fin = fin + 1 end
    run:StartCast(100, 101, true)
    stepTo(run, 100, 101.4, 60)
    eq(run:GetPhase(), "cast"); eq(fin, 0)
    at(run, 101.6)
    eq(fin, 1, "onFinished fired"); eq(run:IsBusy(), false)
    eq(run.frame._shown, false, "stopped"); eq(run.frame:GetScript("OnUpdate"), nil)
    eq(run.burst._groups[1].plays, 0, "a channel has no lock-in")
end

function T.verdict_window_restarts_when_progress_drops_below_one()
    local run = mk()
    run:StartCast(100, 101, false)
    run:SetProgressOverride(1)                -- window opens at 100 (the override ticks at once)
    at(run, 100.3)
    at(run, 100.4)
    run:SetProgressOverride(0.5)
    at(run, 100.45)                           -- below 1 again: the window is forgotten
    run:SetProgressOverride(1)                -- reopens at 100.45
    at(run, 100.9)                            -- 0.45s later
    eq(run:GetPhase(), "cast", "window restarted")
    at(run, 101.0)
    eq(run:GetPhase(), "hold", "fires 0.5s after the second completion")
end

function T.an_explicit_verdict_inside_the_window_wins()
    local run = mk()
    local fin = 0
    run.onFinished = function() fin = fin + 1 end
    run:StartCast(100, 101, false)
    stepTo(run, 100, 101.2, 60)
    ok(run:Succeed())
    stepTo(run, 101.2, 103.0, 60)
    eq(fin, 1, "one finish, no second auto verdict")
    eq(run.burst._groups[1].plays, 1)
end

function T.start_cast_rejects_bad_arguments_without_throwing()
    local run = mk()
    local nan, inf = 0 / 0, math.huge
    local bad = {
        { nan, 105, false }, { 100, nan, false }, { 100, inf, false }, { -inf, 105, false },
        { inf, inf, false }, { 100, 100, false }, { 105, 100, false }, { 100, "x", false },
        { 100, 105, __SECRET },
    }
    for i, c in ipairs(bad) do
        local okc, r = pcall(run.StartCast, run, c[1], c[2], c[3])
        ok(okc, "case " .. i .. " threw: " .. tostring(r))
        eq(r, false, "case " .. i .. " refused")
        eq(run:IsBusy(), false, "case " .. i .. " left no state")
        eq(run.frame:GetScript("OnUpdate"), nil, "case " .. i .. " installed no OnUpdate")
    end
    ok(run:StartCast(100, 105, false), "a plain cast still works afterwards")
end

function T.start_cast_refuses_a_cast_that_finished_before_the_grace_window()
    local run = mk()                          -- clock at 100
    local fin = 0
    local shownBefore = run.frame._shown
    run.onFinished = function() fin = fin + 1 end
    eq(run:StartCast(90, 95, false), false, "long finished cast refused")
    eq(run:StartCast(90, 95, true), false, "long finished channel refused")
    eq(run:IsBusy(), false, "no state change"); eq(run.frame:GetScript("OnUpdate"), nil, "no OnUpdate")
    eq(run.frame._shown, shownBefore, "frame untouched"); eq(run.burst._groups[1].plays, 0, "no lock-in replayed")
    at(run, 101); eq(fin, 0, "no onFinished from a refused cast")
    __now = 100
    -- Just inside the window (ended 0.3s ago): accepted, snaps to complete, normal path runs.
    ok(run:StartCast(97.6, 99.7, false), "within the grace window")
    eq(run:GetPhase(), "cast"); eq(run:IsComplete(), true, "snapped to complete")
    at(run, 100.6)
    eq(run:GetPhase(), "hold", "safety net gives the verdict as usual")
    -- The boundary itself (endTime + 0.5 == now) is still inside the window.
    local edge = mk()
    ok(edge:StartCast(95, 99.5, false), "exactly at the end of the window")
end

function T.match_cast_compares_plain_ids_and_never_touches_secrets()
    local run = mk()
    eq(run:MatchesCast("Cast-1"), nil, "no id known yet")
    ok(run:StartCast(100, 100 + CAST, false, "Cast-1"), "castID rides in on StartCast")
    eq(run:MatchesCast("Cast-1"), true, "same id")
    eq(run:MatchesCast("Cast-2"), false, "different id")
    eq(run:MatchesCast(nil), nil, "event with no id is unknown")
    local okc, r = pcall(run.MatchesCast, run, __SECRET_ID)
    ok(okc, "secret event id threw: " .. tostring(r)); eq(r, nil, "secret event id is unknown")
    run:SetCastID(__SECRET_ID)
    okc, r = pcall(run.MatchesCast, run, "Cast-1")
    ok(okc, "secret stored id threw: " .. tostring(r)); eq(r, nil, "secret stored id is unknown")
    okc, r = pcall(run.MatchesCast, run, __SECRET_ID)
    ok(okc and r == nil, "secret against secret is unknown, not equal")
    run:SetCastID("Cast-3")
    eq(run:MatchesCast("Cast-3"), true, "SetCastID replaces"); eq(run:MatchesCast("Cast-1"), false)
    ok(run:StartCast(110, 112, false), "next cast without an id")
    eq(run:MatchesCast("Cast-3"), nil, "StartCast forgets the previous castID")
end

function T.lock_in_glow_sizing_survives_a_secret_size()
    local fx = withEffects()
    fx.glow:SetSize(40, 10)
    local run = mk({ glowBurst = fx.glow })
    run:StartCast(100, 100 + CAST, false); run:SetProgressOverride(0.5); at(run, 101)
    ok(run:Succeed())
    local to = run.glowScale._args.SetScaleTo
    near(to[1], 1 + 2 * 5 / 40, 1e-9, "scale x from the real size"); near(to[2], 1 + 2 * 5 / 10, 1e-9, "scale y")
    -- A secret size must not be compared; the burst still plays with its prebuilt scale.
    local fx2 = withEffects()
    fx2.glow.GetSize = function() return __SECRET, __SECRET end
    local run2 = mk({ glowBurst = fx2.glow })
    run2:StartCast(100, 100 + CAST, false); run2:SetProgressOverride(0.5); at(run2, 101)
    local okS, err = pcall(run2.Succeed, run2)
    ok(okS, "Succeed threw on a secret glow size: " .. tostring(err))
    eq(fx2.glow._groups[1].plays, 1, "burst still plays")
    eq(fx2.glow._shown, true)
end

function T.stop_restores_every_effect_and_the_alpha()
    local fx = withEffects()
    local dim = CreateFrame("Frame", nil, UIParent)
    local run = mk({ flareTarget = fx.flare, glowBurst = fx.glow, holdGlow = fx.holdGlow, scaleTarget = fx.pop, alphaTarget = dim })
    run:StartCast(100, 100 + CAST, false); run:SetProgressOverride(0.5); at(run, 101)
    ok(run:Succeed()); at(run, 101.03)
    ok(fx.flare._vc[1] > 0.8, "flare is up before Stop")
    eq(fx.glow._shown, true); eq(run.burst._shown, true)
    near(fx.holdGlow._alpha, 0.7, 1e-9)
    run:Stop()
    near(fx.flare._vc[1], 0.659, 1e-6, "flare color restored"); near(fx.flare._vc[3], 0.969, 1e-6)
    eq(fx.glow._shown, false, "glow burst hidden"); eq(run.burst._shown, false, "chevron burst hidden")
    eq(fx.glow._groups[1].playing, false, "glow group stopped"); eq(run.burst._groups[1].playing, false, "burst group stopped")
    near(fx.holdGlow._alpha, 0, 1e-9, "hold glow off")
    -- The outage dims the alpha target; Stop gives it back.
    __now = 110
    run:StartCast(110, 110 + CAST, false); run:SetProgressOverride(0.5); at(run, 110.5)
    ok(run:Interrupt()); at(run, 111.4)
    ok(dim._alpha < 0.9, "the outage dimmed the alpha target")
    run:Stop()
    near(dim._alpha, 1, 1e-9, "alpha restored")
end

function T.show_idle_parks_a_visible_unlit_row_and_a_cast_ignites_from_it()
    local fx = withEffects()
    local dim = CreateFrame("Frame", nil, UIParent)
    local run = mk({ glowBurst = fx.glow, holdGlow = fx.holdGlow, scaleTarget = fx.pop, alphaTarget = dim })
    run:ShowIdle(0.35)
    eq(run.frame._shown, true, "ShowIdle keeps the frame visible"); eq(run:GetPhase(), "idle"); eq(run:IsBusy(), false)
    eq(run.frame:GetScript("OnUpdate"), nil, "no OnUpdate in the idle row")
    for i = 1, run.count do
        eq(run.segs[i].lit._shown, false, "unlit"); eq(run.segs[i].dim._shown, true, "dim drawn")
        near(run.segs[i].dim._vc[4], 0.35, 1e-9, "idle alpha")
    end
    eq(run.clip._shown, false, "no caret")
    -- A rescale in the idle row builds new segments at the idle alpha too.
    run:Layout(run.W + 60, run.H)
    for i = 1, run.count do near(run.segs[i].dim._vc[4], 0.35, 1e-9, "new segment " .. i) end
    -- A cast ignites from it and uses the engine's own unlit alpha.
    __now = 100
    ok(run:StartCast(100, 100 + CAST, false))
    for i = 1, run.count do near(run.segs[i].dim._vc[4], 0.2, 1e-9, "cast look " .. i) end
    stepTo(run, 100, 101.2, 60)
    ok(run.segs[1].lit._shown, "ignites from idle"); eq(run.segs[run.count].lit._shown, false)
    -- It is also the way out of an outage: alpha back, effects off, row visible again.
    ok(run:Interrupt()); at(run, 102.15)
    ok(dim._alpha < 1, "the outage dimmed the target")
    run:ShowIdle(0.35)
    near(dim._alpha, 1, 1e-9, "alpha restored"); eq(run.frame._shown, true); eq(run:GetPhase(), "idle")
    for i = 1, run.count do eq(run.segs[i].lit._shown, false) end
    -- onFinished may park it again from inside the callback.
    local fired = 0
    run.onFinished = function(r) fired = fired + 1; r:ShowIdle(0.35) end
    __now = 110
    ok(run:StartCast(110, 110 + CAST, false)); run:SetProgressOverride(0.5); at(run, 110.5)
    ok(run:Succeed()); at(run, 111.6); at(run, 111.9); at(run, 112.0)
    eq(fired, 1, "onFinished fired once"); eq(run:GetPhase(), "idle"); eq(run.frame._shown, true, "idle row after the finish")
    eq(run.frame:GetScript("OnUpdate"), nil)
    -- A bad alpha falls back to the engine's unlit look.
    run:ShowIdle(__SECRET)
    near(run.segs[1].dim._vc[4], 0.2, 1e-9, "secret alpha refused")
    run:ShowIdle(0 / 0)
    near(run.segs[1].dim._vc[4], 0.2, 1e-9, "NaN alpha refused")
    run:Stop()
    eq(run.frame._shown, false, "Stop still hides")
end

function T.joining_a_cast_underway_snaps_lit_segments_on()
    local run = mk()
    __now = 101.25                            -- halfway through a 2.5s cast
    ok(run:StartCast(100, 100 + CAST, false)) -- StartCast's own first tick; no further frame
    local n = 0
    for i = 1, run.count do
        local sg = run.segs[i]
        if sg.b <= 0.5 then
            n = n + 1
            eq(lit(sg), true, "segment " .. i .. " lit at once")
            near(sg.lit._vc[4], 1, 1e-9, "segment " .. i .. " at full alpha, not mid flicker")
        end
    end
    ok(n >= 5, "enough segments below the join point")
end

function T.reduced_motion_hold_skips_the_fade()
    local run = mk({ reducedMotion = true })
    local fin = 0
    run.onFinished = function() fin = fin + 1 end
    run:StartCast(100, 100 + CAST, false); run:SetProgressOverride(0.5); at(run, 101)
    ok(run:Succeed())
    at(run, 101.99)
    eq(fin, 0, "still holding"); eq(run:GetPhase(), "hold")
    near(run.segs[1].lit._vc[4], 1, 1e-9, "full alpha through the hold")
    at(run, 102.0)
    eq(fin, 1, "finished the moment the hold ended"); eq(run:GetPhase(), "idle")
end

function T.verdicts_outside_a_cast_are_refused()
    local fx = withEffects()
    local run = mk({ scaleTarget = fx.pop, glowBurst = fx.glow })
    eq(run:Succeed(), false, "Succeed while idle"); eq(run:Interrupt(), false, "Interrupt while idle")
    eq(run.burst._groups[1].plays, 0, "nothing played")
    eq(run:IsBusy(), false); eq(run.frame:GetScript("OnUpdate"), nil)
    run:StartCast(100, 100 + CAST, false); run:SetProgressOverride(0.5); at(run, 101)
    ok(run:Succeed())
    eq(run:Succeed(), false, "second Succeed during the hold")
    eq(run:Interrupt(), false, "Interrupt during the hold")
    eq(run.burst._groups[1].plays, 1, "lock-in played once")
end

function T.layout_while_active_re_ticks_at_once()
    local run = mk()
    run:StartCast(100, 100 + CAST, false); run:SetProgressOverride(0.5); at(run, 101)
    ok(litCount(run) > 0)
    __now = 101
    ok(run:Layout(300, 18))
    eq(run.count, 24)
    local want = 0
    for i = 1, run.count do if run.segs[i].b <= 0.5 then want = want + 1 end end
    eq(litCount(run), want, "segments re-lit by Layout's own tick, with no frame in between")
    for i = 1, run.count do
        if lit(run.segs[i]) then near(run.segs[i].lit._vc[4], 1, 1e-9, "snapped, not flickering " .. i) end
    end
    eq(run.clip._shown, true)
    near(run.outline._points["TOPLEFT"].x + run.outline._w, 0.5 * run.span, 1e-6, "caret re-seated for the new span")
    eq(run.span, 294, "24 chevrons at pitch 12 span 294 of 300")
end

-- ---- UpdateTimes (DELAYED / CHANNEL_UPDATE) ---------------------------------

function T.update_times_retimes_a_running_cast_without_re_igniting_lit_segments()
    local run = mk()
    ok(run:StartCast(100, 100 + CAST, false, "Cast-1"))
    stepTo(run, 100, 100.8, 30)
    local before = {}
    for i = 1, run.count do before[i] = run.segs[i].litSince end
    ok(before[1] ~= false and before[3] ~= false, "the leading segments are lit")
    local calls = run.segs[1].lit._vcCalls
    __now = 100.8
    ok(run:UpdateTimes(100, 100 + CAST + 0.5), "accepted mid cast")
    near(run.dur, CAST + 0.5, 1e-9, "new length")
    near(run:GetProgress(), 0.8 / (CAST + 0.5), 1e-9, "progress follows the new length")
    eq(run:GetPhase(), "cast"); eq(run:MatchesCast("Cast-1"), true, "castID kept")
    for i = 1, run.count do
        if before[i] ~= false and run.segs[i].litSince ~= false then
            eq(run.segs[i].litSince, before[i], "segment " .. i .. " keeps its ignite clock")
        end
    end
    eq(run.segs[1].lit._vcCalls, calls, "a settled segment is not repainted")
    ok(run.frame:GetScript("OnUpdate") ~= nil, "still animating")
    -- Contrast: StartCast with the same times near the start WOULD restart the ignite.
    local fresh = mk()
    fresh:StartCast(100, 100 + CAST, false)
    stepTo(fresh, 100, 100.5, 30)
    local lit1 = fresh.segs[1].litSince
    ok(lit1 ~= false)
    fresh:StartCast(100, 100 + CAST + 0.5, false)
    ok(fresh.segs[1].litSince == false or fresh.segs[1].litSince ~= lit1, "StartCast is what re-ignites")
end

function T.update_times_extends_a_cast_that_had_reached_progress_one()
    local run = mk()
    run:StartCast(100, 101, false)
    stepTo(run, 100, 101.2, 30)
    ok(run:IsComplete(), "complete, waiting for a verdict")
    __now = 101.2
    ok(run:UpdateTimes(100, 103))
    eq(run:IsComplete(), false, "the extension reopens the cast")
    stepTo(run, 101.2, 101.9, 30)
    eq(run:GetPhase(), "cast", "the stale verdict window did not fire")
end

function T.update_times_refuses_outside_a_cast_and_bad_arguments()
    local run = mk()
    eq(run:UpdateTimes(100, 105), false, "idle")
    run:StartCast(100, 100 + CAST, false)
    local nan, inf = 0 / 0, math.huge
    local bad = { { nan, 105 }, { 100, nan }, { 100, inf }, { -inf, 105 }, { 100, 100 }, { 105, 100 }, { 100, "x" },
        { __SECRET, 105 }, { 100, __SECRET }, { nil, 105 }, { 80, 85 } }
    for i, c in ipairs(bad) do
        local okc, r = pcall(run.UpdateTimes, run, c[1], c[2])
        ok(okc, "case " .. i .. " threw: " .. tostring(r)); eq(r, false, "case " .. i .. " refused")
    end
    near(run.dur, CAST, 1e-9, "a refused update changes nothing")
    run:SetProgressOverride(0.5); at(run, 101)
    ok(run:Succeed())
    eq(run:UpdateTimes(100, 110), false, "refused during the hold")
    near(run.dur, CAST, 1e-9)
end

function T.rng_self_check_is_quiet_when_bit_agrees_and_loud_when_it_does_not()
    eq(#__degrades, 0, "no degrade log on a healthy load")
    eq(FS.ChevronCastBar.rngOk, true)
    local realBit = bit
    local fake = {}
    for k, v in pairs(realBit) do fake[k] = v end
    fake.rshift = function(a, n) return realBit.rshift(a, n + 1) end
    bit = fake
    local okLoad, err = pcall(__load, "ChevronCastBar.lua", __src)
    bit = realBit
    ok(okLoad, "load threw on a divergent bit library: " .. tostring(err))
    eq(#__degrades, 1, "one degrade logged"); eq(__degrades[1], "chevron_rng_mismatch")
    eq(FS.ChevronCastBar.rngOk, false)
    local run = mk()
    ok(run:StartCast(100, 100 + CAST, false), "the engine still runs after the fallback")
end

-- ---- vertical runs (the Gunsight tapes) ---------------------------------------

-- A vertical run: the frame is `width` across and `height` long, the chevron box defaults to a 28 x 17
-- tape chevron, the pitch to 17 * 12.2 / 13.5 = 15.36 (the mockup's ratio), which rounds to 15 at one
-- pixel per unit.
local function mkv(opts)
    opts = opts or {}
    opts.vertical = true
    opts.width = opts.width or 34
    opts.height = opts.height or 300
    opts.chevronWidth = opts.chevronWidth or 28
    opts.chevronHeight = opts.chevronHeight or 17
    return mk(opts)
end
local function atBL(tex) return tex._points["BOTTOMLEFT"] end
local function sameCoords(tex, l, r, t, b, msg)
    eq(tex._tc[1], l, msg .. " l"); eq(tex._tc[2], r, msg .. " r")
    eq(tex._tc[3], t, msg .. " t"); eq(tex._tc[4], b, msg .. " b")
end

function T.vertical_layout_stacks_the_seats_bottom_to_top_on_the_y_pitch()
    -- 17 high chevrons at pitch 15: floor((300 - 17) / 15) + 1 = 19, span 18 * 15 + 17 = 287.
    local run = mkv()
    eq(run.vertical, true)
    eq(run.count, 19, "count along the run's length")
    eq(run.span, 287, "span"); eq(run.pitch, 15, "pitch")
    eq(run.frame._w, 34, "frame is the cross width"); eq(run.frame._h, 300, "and the length")
    for i = 1, run.count do
        local seg = run.segs[i]
        eq(seg.lit._w, 28, "chevron width " .. i); eq(seg.lit._h, 17, "chevron height " .. i)
        local p = atBL(seg.lit)
        ok(p ~= nil and seg.lit._points["TOPLEFT"] == nil, "seats are BOTTOMLEFT anchors " .. i)
        eq(p.rel, run.frame, "anchored to the run frame"); eq(p.relPoint, "BOTTOMLEFT", "from its bottom left")
        eq(p.x, 3, "centred across: (34 - 28) / 2"); eq(p.y, (i - 1) * 15, "seat " .. i .. " rises one pitch")
        local d = atBL(seg.dim)
        eq(d.x, p.x); eq(d.y, p.y, "dim and lit share a seat")
    end
    eq(run.segs[1].a, 0); near(run.segs[2].a, 15 / 287, 1e-12, "a is the fraction of the span")
    near(run.segs[1].b, 17 / 287, 1e-12); eq(run.segs[19].b, 1, "the top chevron ends at progress 1")
    -- An explicit pitch (16.4 rounds to 16): floor(283 / 16) + 1 = 18.
    local p16 = mkv({ pitch = 16.4 })
    eq(p16.pitch, 16); eq(p16.count, 18)
    -- No chevron size: the box is the cross width, 28 / 13.5 * 28 high.
    local d = mk({ vertical = true, width = 28, height = 100 })
    eq(d.segs[1].lit._w, 28, "default chevron is the cross width wide")
    eq(d.segs[1].lit._h, math.floor(28 * 13.5 / 28 + 0.5), "and the mockup's depth ratio high")
    -- Horizontal runs are unchanged and say so.
    eq(mk().vertical, false)
end

function T.vertical_chevron_size_override_keeps_the_art_and_changes_the_box()
    local narrow = mkv({ width = 20, chevronWidth = 20 })
    local wide = mkv({ width = 28, chevronWidth = 28 })
    eq(narrow.segs[1].lit._w, 20, "player tape 20 wide"); eq(wide.segs[1].lit._w, 28, "target tape 28 wide")
    eq(narrow.segs[1].lit._h, wide.segs[1].lit._h, "same height")
    eq(narrow.count, wide.count, "same count")
    eq(narrow.segs[1].lit._texture, wide.segs[1].lit._texture, "same art")
    -- Bad sizes are ignored, not thrown on.
    local bad = mk({ vertical = true, width = 28, height = 100, chevronWidth = __SECRET, chevronHeight = -4, pitch = 0 / 0 })
    eq(bad.segs[1].lit._w, 28, "a secret or negative size falls back to the defaults")
end

function T.vertical_pixel_snapping_works_on_the_y_axis_on_every_grid()
    local shapes = {
        { width = 28, height = 313, chevronWidth = 28, chevronHeight = 17.28 },
        { width = 20, height = 313.3, chevronWidth = 20, chevronHeight = 17.28 },
    }
    for _, g in ipairs(GRIDS) do
        __physH = g[1]; __setUIScale(g[2])
        for _, o in ipairs(shapes) do
            __bottom = 100.3137; __left = 50.77
            local run = mkv({ width = o.width, height = o.height, chevronWidth = o.chevronWidth, chevronHeight = o.chevronHeight })
            local px = pixelOf(run)
            local tag = "h" .. g[1] .. " s" .. g[2] .. " w" .. o.width
            ok(run.count >= 2, tag .. ": a column")
            local h, w = run.segs[1].lit._h, run.segs[1].lit._w
            ok(isWhole(h / px) and isWhole(w / px), tag .. ": whole pixel box")
            local pitch = atBL(run.segs[2].lit).y - atBL(run.segs[1].lit).y
            ok(isWhole(pitch / px), tag .. ": whole pixel pitch")
            near(run.pitch, pitch, 1e-9, tag .. ": run.pitch")
            for i = 1, run.count do
                local p = atBL(run.segs[i].lit)
                eq(run.segs[i].lit._h, h, tag .. ": identical height " .. i)
                if i > 1 then near(p.y - atBL(run.segs[i - 1].lit).y, pitch, 1e-9, tag .. ": equal gap " .. i) end
                ok(isWhole((__bottom + p.y) / px, 1e-6), tag .. ": seat " .. i .. " bottom on a physical pixel")
                ok(isWhole((__left + p.x) / px, 1e-6), tag .. ": seat " .. i .. " left on a physical pixel")
            end
            local top = atBL(run.segs[run.count].lit).y + h
            ok(top <= run.H + 1e-9, tag .. ": the top chevron does not pass the run's top")
            near(run.span, top - atBL(run.segs[1].lit).y, 1e-9, tag .. ": span")
            ok(run.span + pitch > math.floor(run.H / px + 1e-6) * px - 1e-6, tag .. ": one more would not fit")
            ok(math.abs(atBL(run.segs[1].lit).y) < px, tag .. ": the origin moves by under a pixel")
        end
    end
    -- One pixel per unit: nudged UP when the slack allows, DOWN when there is none.
    __physH = 768; __setUIScale(1.0); __bottom = 100.3; __left = nil
    local roomy = mkv({ height = 300 })               -- span 287, slack 13
    near(atBL(roomy.segs[1].lit).y, 0.7, 1e-9, "nudged up")
    local tight = mkv({ height = 287 })
    near(atBL(tight.segs[1].lit).y, -0.3, 1e-9, "nudged down when it would pass the top")
    __bottom = nil
end

function T.vertical_progress_lights_from_the_bottom_and_maps_onto_the_span()
    local run = mkv()
    ok(run:StartCast(100, 100 + CAST, false))
    run:SetProgressOverride(0); at(run, 101)
    eq(litCount(run), 0)
    run:SetProgressOverride(0.5); at(run, 102)
    for i = 1, run.count do eq(lit(run.segs[i]), run.segs[i].b <= 0.5, "segment " .. i .. " lit iff its end is under the caret") end
    ok(lit(run.segs[1]) and not lit(run.segs[run.count]), "lit from the bottom")
    run:SetProgressOverride(0.9999); at(run, 103)
    eq(lit(run.segs[run.count]), false, "the top one waits for 1")
    run:SetProgressOverride(1); at(run, 104)
    eq(litCount(run), run.count, "all lit at 1")
end

function T.vertical_caret_moves_along_y_and_the_clip_leaves_room_across()
    local run = mkv()
    ok(run:StartCast(100, 100 + CAST, false))
    run:SetProgressOverride(0.5); at(run, 101)
    eq(run.clip._shown, true)
    local u = 17 / 13.5
    local capW, capH = 28 + 6 * u, 16 * u
    near(run.outline._w, capW, 1e-9, "the caret is the bigger, thicker chevron: wider by 3 image px a side")
    near(run.outline._h, capH, 1e-9, "and 16 / 13.5 as tall")
    local p = run.outline._points["BOTTOMLEFT"]
    eq(p.rel, run.body, "on the clipped child")
    near(p.y + run.outline._h, 0.5 * run.span, 1e-9, "tip (top edge) at origin + f * span")
    -- The clip frame is widened across so the caret and its halo are not shaved off at the sides.
    local tl, br = run.clip._points["TOPLEFT"], run.clip._points["BOTTOMRIGHT"]
    ok(tl.x < 0 and br.x > 0, "clip extends past both sides")
    near(-tl.x, br.x, 1e-9, "evenly")
    ok(br.x >= (run.glow._w - run.W) / 2, "far enough for the halo")
    near(p.x - (-tl.x) + capW / 2, 3 + 14, 1e-9, "caret centred on the chevron column")
    near(run.glow._w, 2 * capW, 1e-9, "halo is 2x the caret"); near(run.glow._h, 2 * capH, 1e-9)
    eq(run.glow._points["CENTER"].rel, run.outline, "halo rides the caret")
    run:SetProgressOverride(0); at(run, 101.1); eq(run.clip._shown, false, "hidden at 0")
    run:SetProgressOverride(1); at(run, 101.2); eq(run.clip._shown, false, "hidden at 1")
end

function T.vertical_channel_flips_the_art_along_y_with_the_tip_at_the_bottom()
    local run = mkv()
    ok(run:StartCast(100, 200, true))
    sameCoords(run.segs[1].lit, 0, 1, 1, 0, "segments flipped vertically")
    sameCoords(run.outline, 0, 1, 1, 0, "caret flipped"); sameCoords(run.glow, 0, 1, 1, 0, "halo flipped")
    run:SetProgressOverride(0.25); at(run, 101)
    -- Drains from the top: f = 0.75, the flipped caret's tip is its BOTTOM edge.
    near(run.outline._points["BOTTOMLEFT"].y, 0.75 * run.span, 1e-9, "channel caret tip at f * span")
    local n = 0
    for i = 1, run.count do
        if lit(run.segs[i]) then n = n + 1; ok(i == n, "lit segments form a bottom prefix") end
    end
    ok(n > 0 and n < run.count)
    -- A following cast un-flips.
    run:StartCast(103, 105.5, false)
    sameCoords(run.segs[1].lit, 0, 1, 0, 1, "segments upright again"); sameCoords(run.outline, 0, 1, 0, 1, "caret upright")
    -- opts.mirrorChannel = false keeps the art upright for channels too.
    local up = mkv({ mirrorChannel = false })
    up:StartCast(100, 200, true)
    sameCoords(up.segs[1].lit, 0, 1, 0, 1, "mirrorChannel false")
    -- The horizontal engine still mirrors across x.
    local hz = mk(); hz:StartCast(100, 200, true)
    sameCoords(hz.segs[1].lit, 1, 0, 0, 1, "horizontal mirror unchanged")
end

function T.vertical_burst_sits_at_the_top_and_the_channel_finish_at_the_bottom()
    local fx = withEffects()
    local run = mkv({ glowBurst = fx.glow })
    run:StartCast(100, 100 + CAST, false); run:SetProgressOverride(0.5); at(run, 101)
    ok(run:Succeed())
    local bp = run.burst._points["CENTER"]
    eq(bp.rel, run.frame); eq(bp.relPoint, "BOTTOMLEFT")
    near(bp.x, 3 + 14, 1e-9, "centred across the column")
    near(bp.y, run.span - 8.5, 1e-9, "on the top chevron")
    eq(run.burst._w, 56, "2x the chevron wide"); eq(run.burst._h, 34, "and tall")
    sameCoords(run.burst, 0, 1, 0, 1, "upright")
    eq(run.burst._groups[1].plays, 1, "lock-in burst played")
    -- A natural channel end (drain): the burst on the FIRST chevron, flipped, pointing down.
    local ch2 = mkv()
    ch2.finishedCount = 0
    ch2.onFinished = function(r) r.finishedCount = r.finishedCount + 1 end
    ok(ch2:StartCast(100, 103, true)); stepTo(ch2, 100, 103, 60)
    __now = 103
    eq(ch2:EndChannel(), true, "the finish plays")
    local cb = ch2.burst._points["CENTER"]
    near(cb.y, 8.5, 1e-9, "burst on the first chevron")
    sameCoords(ch2.burst, 0, 1, 1, 0, "flipped to point down")
    stepTo(ch2, 103, 104.2, 60)
    eq(ch2.finishedCount, 1, "finish ends")
    -- A rescale keeps the burst on its end.
    local rs = mkv()
    rs:Layout(34, 200)
    near(rs.burst._points["CENTER"].y, rs.span - 8.5, 1e-9, "re-seated after Layout")
end

function T.vertical_run_lifecycle_succeed_interrupt_and_zero_allocation()
    if jit then jit.off() end
    local fx = withEffects()
    local run = mkv({ flareTarget = fx.flare, glowBurst = fx.glow, holdGlow = fx.holdGlow })
    run.finishedCount = 0
    run.onFinished = function(r) r.finishedCount = r.finishedCount + 1 end
    run:StartCast(100, 112, false)
    local grown, t = allocOver(run, 100, 90, 600)
    ok(grown < 1.0, "vertical cast frames allocated " .. grown .. " KB")
    __now = t
    ok(run:Succeed())
    eq(run:GetPhase(), "hold")
    stepTo(run, t, t + 1.4, 60)
    eq(run.finishedCount, 1, "hold and fade end in onFinished"); eq(run:GetPhase(), "idle")
    -- Interrupt: the outage runs 1.0s and cuts from the top (the leading edge) down.
    local r2 = mkv()
    r2.finishedCount = 0
    r2.onFinished = function(r) r.finishedCount = r.finishedCount + 1 end
    r2:StartCast(100, 110, false); r2:SetProgressOverride(0.5); at(r2, 101)
    __now = 101
    ok(r2:Interrupt())
    local lastLit = 0
    for i = 1, r2.count do if r2.segs[i].b <= 0.5 then lastLit = i end end
    local gone, tt = {}, 101.55
    while tt < 101.8 do
        tt = tt + 0.001; at(r2, tt)
        for i = 1, lastLit do if gone[i] == nil and not r2.segs[i].lit._shown then gone[i] = tt end end
    end
    for i = 2, lastLit do ok(gone[i] < gone[i - 1], "segment " .. i .. " is cut before segment " .. (i - 1)) end
    at(r2, 102.0)
    eq(r2.finishedCount, 1)
end

function T.vertical_run_relayouts_on_a_scale_change_and_ignores_fit_width()
    __physH = 1080; __setUIScale(0.71)
    local run = mkv({ chevronHeight = 17.28 })
    local st = countLayouts(run)
    __fire("UI_SCALE_CHANGED")
    eq(st.n, 0, "same scale: nothing")
    __setUIScale(0.64); __fire("UI_SCALE_CHANGED")
    eq(st.n, 1, "new scale re-lays out")
    local px = pixelOf(run)
    ok(isWhole(run.segs[1].lit._h / px) and isWhole(run.pitch / px), "the new grid")
    eq(run:FitWidth(120), nil, "FitWidth is a horizontal feature")
    local fit = mkv({ fitWidth = true, height = 301 })
    eq(fit.fit, false, "fitWidth does not apply to a vertical run")
    eq(fit.frame._h, 301, "the run keeps the height it was given")
end

-- ---- texture overrides -------------------------------------------------------

function T.textures_option_overrides_each_art_path_and_lit_defaults_to_fill()
    local def = mk()
    local t = { fill = "F.tga", lit = "L.tga", outline = "O.tga", glow = "G.tga", burst = "B.tga", strip = "S.tga" }
    local run = mkv({ textures = t })
    for i = 1, run.count do
        eq(run.segs[i].dim._texture, "F.tga", "dim " .. i); eq(run.segs[i].lit._texture, "L.tga", "lit " .. i)
    end
    eq(run.outline._texture, "O.tga"); eq(run.glow._texture, "G.tga"); eq(run.burst._texture, "B.tga")
    eq(run.textures.strip, "S.tga", "strip path is kept for the strip")
    -- New segments from a bigger Layout use the override too.
    ok(run:Layout(34, 600)); eq(run.segs[run.count].dim._texture, "F.tga"); eq(run.segs[run.count].lit._texture, "L.tga")
    -- lit falls back to fill; anything unset or unusable keeps the default.
    local partial = mkv({ textures = { fill = "F.tga", glow = 5, burst = __SECRET, outline = "" } })
    eq(partial.segs[1].lit._texture, "F.tga", "lit defaults to fill")
    eq(partial.glow._texture, def.glow._texture, "a non-string is ignored")
    eq(partial.burst._texture, def.burst._texture, "a secret is ignored")
    eq(partial.outline._texture, "", "an empty string is a string")
    eq(partial.textures.strip, FS.Theme.CAST_CHEVRON_STRIP_TEXTURE, "strip default")
    -- Horizontal runs take overrides too.
    local hz = mk({ textures = { fill = "HF.tga" } })
    eq(hz.segs[1].dim._texture, "HF.tga"); eq(hz.segs[1].lit._texture, "HF.tga")
    eq(hz.outline._texture, def.outline._texture)
    -- The up set: five files the media generator writes.
    local up = CCB.TEXTURES_UP
    for _, k in ipairs({ "fill", "outline", "glow", "burst", "strip" }) do
        ok(type(up[k]) == "string" and up[k]:find("cast_chevron_up_" .. k .. ".tga", 1, true), "TEXTURES_UP." .. k)
    end
    local viaPreset = mkv({ textures = CCB.TEXTURES_UP })
    eq(viaPreset.segs[1].lit._texture, up.fill, "the preset is a valid textures table")
end

-- ---- the strip StatusBar --------------------------------------------------------

function T.vertical_strip_is_a_vertical_statusbar_with_a_vertical_tile()
    local run = mkv({ textures = CCB.TEXTURES_UP })
    local bar, why = run:CreateStrip(run.frame)
    ok(bar, "strip built: " .. tostring(why))
    eq(bar._kind, "StatusBar"); eq(bar._orientation, "VERTICAL", "grows bottom to top")
    eq(bar._sbPath, CCB.TEXTURES_UP.strip, "fill is the up strip art")
    eq(bar._sbTex._vertTile, true, "tiled along y"); eq(bar._sbTex._horizTile, nil, "not along x")
    eq(bar._min, 0); eq(bar._max, 1); eq(bar._shown, false, "built hidden")
    -- One tile is one chevron (16 texels): the scale lands the tile on the engine's whole-pixel pitch.
    eq(run:ApplyStripScale(bar), 15 / 16); eq(bar._scale, 15 / 16)
    eq(bar.fsTexelsPerChevron, 16)
    -- Horizontal runs: a horizontal strip, no orientation call, the pet bar's scale (2 * pitch / 32).
    local hz = mk()
    local hbar = hz:CreateStrip(hz.frame)
    eq(hbar._orientation, nil, "no orientation for a horizontal strip"); eq(hbar._sbTex._horizTile, true)
    eq(hbar._sbPath, FS.Theme.CAST_CHEVRON_STRIP_TEXTURE)
    eq(hz:ApplyStripScale(hbar), hz.pitch / 16)
    eq(hz:ApplyStripScale(nil), nil, "no strip, no scale")
end

function T.supports_vertical_strip_reports_what_was_detected()
    local run = mkv()
    local okv, caps = run:SupportsVerticalStrip()
    eq(okv, true); eq(caps.orientation, true); eq(caps.vertTile, true); eq(caps.timer, true)
    eq(CCB.SupportsVerticalStrip(), true, "module level too")
end

function T.vertical_strip_degrades_without_orientation_support()
    __sbMissing.SetOrientation = true
    local run = mkv()
    local okv, caps = run:SupportsVerticalStrip()
    eq(okv, false); eq(caps.orientation, false); eq(caps.vertTile, true)
    local bar, why = run:CreateStrip(run.frame)
    eq(bar, nil, "no vertical strip"); ok(type(why) == "string" and why:find("SetOrientation"), "says why: " .. tostring(why))
    -- A horizontal strip does not need it.
    local hz = mk()
    ok(hz:CreateStrip(hz.frame), "horizontal strip unaffected")
end

function T.vertical_strip_degrades_without_vertical_tiling_or_a_timer()
    __sbTexMissing.SetVertTile = true
    local run = mkv()
    local okv, caps = run:SupportsVerticalStrip()
    eq(okv, false); eq(caps.vertTile, false); eq(caps.orientation, true)
    local bar, why = run:CreateStrip(run.frame)
    eq(bar, nil); ok(type(why) == "string" and why:find("SetVertTile"), "says why: " .. tostring(why))
end

function T.vertical_strip_reports_a_missing_timer_but_still_builds()
    __sbMissing.SetTimerDuration = true
    local run = mkv()
    local okv, caps = run:SupportsVerticalStrip()
    eq(okv, false, "not usable for a secret-timed bar"); eq(caps.timer, false)
    ok(run:CreateStrip(run.frame), "the strip itself still builds (a static or hand driven bar)")
end

-- ---- Fx: the motion functions for other consumers (the toggle key rings) ----------

local GOLD1 = { 206, 0.04843413915019482, 0.24843413915019483, 2, 0.4420048024505377, 0.6220048024505377, 0.5251788871828467 }

function T.fx_table_exports_the_motion_functions_and_constants()
    local Fx = CCB.Fx
    ok(type(Fx) == "table", "FS.ChevronCastBar.Fx")
    for _, name in ipairs({ "rng", "makeBusyFlicker", "makeFlicker", "flick", "phaseOf", "intrParams", "segLook",
        "bumps", "bumpA", "bumpB", "stutterTint", "lockInFlare", "ease", "spike", "mix", "clamp",
        "MakePalette", "NewSeg", "NewContext", "SeedFor", "GetBoost" }) do
        ok(type(Fx[name]) == "function", "Fx." .. name)
    end
    eq(Fx.INT_FR.brown, 0.25); eq(Fx.INT_FR.stutter, 0.30); eq(Fx.INT_FR.cut, 0.25); eq(Fx.INT_FR.fade, 0.20)
    eq(Fx.SURGE, 0.6); eq(Fx.DIM_ALPHA, 0.2); eq(Fx.INTR_MS, 1000); eq(Fx.FLARE_MS, 250); eq(Fx.LOCK_MS, 360)
    -- The engine's own rng, so the flicker is the same sequence.
    near(Fx.rng(12345)(), 0.9797282677609473, 1e-12, "rng golden draw")
end

function T.fx_new_seg_reproduces_the_golden_flicker()
    local Fx = CCB.Fx
    local seg = Fx.NewSeg(Fx.SeedFor(13, 1))
    local g = GOLD1
    eq(seg.ign, g[1], "ign")
    near(seg.blinks[1].t0, g[2], 1e-9); near(seg.blinks[1].t1, g[3], 1e-9); eq(seg.blinks[1].code, g[4])
    near(seg.blinks[2].t0, g[5], 1e-9); near(seg.blinks[2].t1, g[6], 1e-9); eq(seg.blinks[2].code, 4)
    near(seg.jit, g[7], 1e-9, "jit")
    -- It is the very seed a run gives its first chevron (salt 13), so the two flicker identically.
    local run = mk()
    eq(run.segs[1].ign, seg.ign); near(run.segs[1].jit, seg.jit, 1e-12)
    local seg6 = Fx.NewSeg(Fx.SeedFor(13, 6))
    eq(seg6.ign, run.segs[6].ign); near(seg6.blinks[1].t0, run.segs[6].blinks[1].t0, 1e-12)
    -- makeFlicker onto a table of the caller's own.
    local mine = { blinks = { { t0 = 0, t1 = 0, code = 1 }, { t0 = 0, t1 = 0, code = 4 } } }
    Fx.makeFlicker(mine, Fx.SeedFor(13, 1))
    eq(mine.ign, g[1]); eq(mine.settle, 0.75); eq(mine.boostMax, 0.3)
    -- The busy flicker is the one the prototype's Medium inherits jit from.
    near(Fx.makeBusyFlicker(Fx.SeedFor(13, 1)).jit, g[7], 1e-9, "busy flicker jit")
end

function T.fx_flick_phase_and_outage_parameters_match_the_engine()
    local Fx = CCB.Fx
    local seg = Fx.NewSeg(Fx.SeedFor(13, 1))      -- ign 206, blinks [10.0, 51.2) code 2 and [91.1, 128.1) code 4, settle 154.5
    eq(Fx.flick(seg, -5), 0, "before the ignite"); eq(Fx.GetBoost(), 0)
    eq(Fx.flick(seg, 2), 0, "dark before the first blink")
    eq(Fx.flick(seg, 30), 2, "off-hue flash"); eq(Fx.flick(seg, 70), 0, "dark between the blinks")
    eq(Fx.flick(seg, 100), 4, "mid"); eq(Fx.flick(seg, 140), 0, "dark after the second blink")
    eq(Fx.flick(seg, 160), 3, "settling")
    local k = (160 / 206 - 0.75) / 0.25
    near(Fx.GetBoost(), 0.3 * (1 - k) * (1 - k), 1e-9, "settle overshoot")
    eq(Fx.flick(seg, 206), 3); eq(Fx.GetBoost(), 0, "settled")
    -- Phase boundaries (25 / 30 / 25 / 20).
    local P = Fx.phaseOf
    eq(P(0.1).phase, "brown"); near(P(0.1).u, 0.4, 1e-12)
    eq(P(0.26).phase, "stutter"); near(P(0.4).u, (0.4 - 0.25) / 0.30, 1e-12)
    eq(P(0.56).phase, "cut"); eq(P(0.81).phase, "fade")
    -- intrParams: the brownout level and the idle values.
    local ph = P(0.1)
    local ip = Fx.intrParams(ph)
    near(ip.level, 1 - 0.6 * (0.4 * 0.4 * (3 - 0.8)), 1e-9, "brownout level"); near(ip.tint, 0.55 * (0.4 * 0.4 * (3 - 0.8)), 1e-9)
    ip = Fx.intrParams(nil)
    eq(ip.level, 1); eq(ip.tint, 0); eq(ip.cutU, -1); eq(ip.dead, false)
    ip = Fx.intrParams(P(0.9)); eq(ip.dead, true); eq(ip.level, 0)
    ip = Fx.intrParams({ phase = "reduced", uT = 0.3 }); near(ip.level, 0.7, 1e-12); eq(ip.reduced, true)
    near(Fx.lockInFlare(0), 0, 1e-12); near(Fx.lockInFlare(0.12 * 250), 1, 1e-12)
end

function T.fx_seg_look_takes_its_base_colour_from_the_palette()
    local Fx = CCB.Fx
    local text = { 0.886, 0.910, 0.941 }
    local base = { 1, 0.2, 0.6 }
    local P = Fx.MakePalette({ base = base })
    near(P.baseR, 1, 1e-12); near(P.baseG, 0.2, 1e-12); near(P.baseB, 0.6, 1e-12)
    near(P.paleR, 1 + (text[1] - 1) * 0.6, 1e-9, "the off-hue flash is the base pulled 60% to text")
    local pw = Fx.MakePalette()
    near(pw.baseR, FS.Theme.COLOR_POWER[1], 1e-12, "default base is the power cyan")
    local seg = Fx.NewSeg(Fx.SeedFor(13, 1))
    local ctx = Fx.NewContext()
    ctx.lit, ctx.snap, ctx.level, ctx.fadeLit, ctx.extent, ctx.intr, ctx.ip = true, false, 1, 1, 1, nil, Fx.intrParams(nil)
    local lk = Fx.segLook(P, seg, 1000, ctx)          -- first lit frame: age 0, dark
    eq(lk.alpha, 0, "dark at age 0"); eq(lk.anim, true, "still igniting")
    lk = Fx.segLook(P, seg, 1030, ctx)                -- code 2
    near(lk.alpha, 0.95, 1e-12); near(lk.r, P.paleR, 1e-12); near(lk.g, P.paleG, 1e-12); near(lk.b, P.paleB, 1e-12)
    lk = Fx.segLook(P, seg, 1100, ctx)                -- code 4: mid, the base colour
    near(lk.alpha, 0.8, 1e-12); near(lk.r, 1, 1e-12); near(lk.g, 0.2, 1e-12); near(lk.b, 0.6, 1e-12)
    lk = Fx.segLook(P, seg, 1300, ctx)                -- settled
    near(lk.alpha, 1, 1e-12); near(lk.r, 1, 1e-12); near(lk.g, 0.2, 1e-12); near(lk.b, 0.6, 1e-12); eq(lk.anim, false)
    -- Another base, the same time: another colour.
    local cyan = Fx.MakePalette({ base = { 0, 1, 1 } })
    lk = Fx.segLook(cyan, seg, 1300, ctx)
    near(lk.r, 0, 1e-12); near(lk.g, 1, 1e-12)
    -- The power outage: the fade phase is dark, the cut phase takes the leading edge first.
    ctx.intr = Fx.phaseOf(0.9); ctx.ip = Fx.intrParams(ctx.intr)
    eq(Fx.segLook(P, seg, 1300, ctx).alpha, 0, "dead in the fade")
    seg.a = 0; ctx.extent = 1
    ctx.intr = Fx.phaseOf(0.7); ctx.ip = Fx.intrParams(ctx.intr)
    eq(Fx.segLook(P, seg, 1300, ctx).alpha > 0, true, "still lit early in the cut")
    ctx.intr = Fx.phaseOf(0.79); ctx.ip = Fx.intrParams(ctx.intr)
    eq(Fx.segLook(P, seg, 1300, ctx).alpha, 0, "gone late in the cut")
    -- Reduced motion: no ignite flicker.
    local red = Fx.MakePalette({ base = base }, true)
    local s2 = Fx.NewSeg(Fx.SeedFor(13, 2))
    local c2 = Fx.NewContext()
    c2.lit, c2.snap, c2.level, c2.fadeLit, c2.extent, c2.intr, c2.ip = true, false, 1, 1, 1, nil, Fx.intrParams(nil)
    near(Fx.segLook(red, s2, 5, c2).alpha, 1, 1e-12, "lit at once")
    -- The engine's own runs are unchanged by the palette split: a run with that base lights that colour.
    local run = mk({ colors = { base = base } })
    run:StartCast(100, 100 + CAST, false); run:SetProgressOverride(0.4); at(run, 101); at(run, 102)
    local v = run.segs[1].lit._vc
    near(v[1], 1, 1e-9); near(v[2], 0.2, 1e-9); near(v[3], 0.6, 1e-9); near(v[4], 1, 1e-9)
end

__checks = T
"""


# The up art set the engine ships as TEXTURES_UP, and the sizes the engine's 2x halo / burst rule and its
# 16 texels per chevron strip scale assume (media/generate_cast_chevron_up.py writes them).
UP_ART_SIZES = {
    "fill": (64, 32), "outline": (64, 32), "glow": (128, 64), "burst": (128, 64), "strip": (32, 16),
}


def check_up_art(lua) -> list[str]:
    """Each TEXTURES_UP path names a real media file with the size the engine assumes."""
    problems = []
    paths = lua.eval("FS.ChevronCastBar.TEXTURES_UP")
    for key, (want_w, want_h) in UP_ART_SIZES.items():
        path = paths[key]
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        if name != f"cast_chevron_up_{key}.tga":
            problems.append(f"{key}: unexpected file name {name}")
            continue
        file = ADDON / "media" / name
        if not file.exists():
            problems.append(f"{key}: {file} does not exist")
            continue
        head = file.read_bytes()[:18]
        width = int.from_bytes(head[12:14], "little")
        height = int.from_bytes(head[14:16], "little")
        if (width, height) != (want_w, want_h):
            problems.append(f"{key}: {name} is {width}x{height}, the engine assumes {want_w}x{want_h}")
    return problems


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
    art = check_up_art(boot())
    for problem in art:
        print(f"FAIL  up_art_matches_the_engines_assumptions: {problem}")
    if not art:
        print("ok    up_art_matches_the_engines_assumptions")
    total = len(names) + 1
    failed += 1 if art else 0
    print(f"{total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
