#!/usr/bin/env python3
"""Runs the real PetCastBar.lua and ChevronCastBar.lua headless against a mock WoW API.

PetCastBar.lua wires the shared chevron engine into the pet frame's cast slot. The
parse gate proves it compiles; these checks pin the WIRING, end to end with mocked
spellcast events and a stepped clock:

  * build: one engine run with the pet run geometry (gapFraction 0.2: 14 high, pitch 10),
    the pop/alpha target is the cast bar's own frame (not the pet container),
    dedicated glow regions, an outline the engine flares, no leading-edge caret, no
    triangle texture, the timer reading "elapsed / total" at the mockup's font size;
  * geometry: every number of the console-dock option C cast bar (bar 26 high, icon 20 at
    3 / 3, run 14 high from x 28, the spell name over the timer, NO tab) parsed back out of
    mockups/gunsight-hud-v2-2026-10-02 (peCastDc, peDcCount, PE_DC_*) and checked at
    scales 1, 0.8333 and 0.64; the text column is a fixed design constant (NAME_MAX_W) wide enough
    for the timer sample and about 9 characters of the 8 pt name, the chevron track is a pure
    function of constants (run:FitWithin over the slot less run x, NAME_MAX_W, the pad and the
    gap; no font measurement anywhere), giving exactly 11 at scales 1 and 0.8333 and 10 at 0.64
    with margin (a sweep pins the window: NAME_MAX_W 39 to 45 keep 11 / 11 / 10, 38 and 46 break it);
    no GetStringWidth call exists in the file; the spell name is never compared and
    its FontString is NAME_MAX_W wide with word wrap off (the engine truncates a long name); the
    timer's is NAME_MAX_W + RUN_GAP wide (the gap is free, the run ends before it) with word wrap off
    (its values may be secret, so a wide readout is clipped, not shortened), and a check computes from
    the run's span that the right justified timer box never overlaps the run at every scale;
  * events: the eight pet-unit spellcast events plus UNIT_PET, never SUCCEEDED;
  * the verdict mapping from the engine's caller recipe (ChevronCastBar.lua header):
    castID-matched STOP -> Succeed (hold, lock-in, fade, then the panel hides);
    INTERRUPTED/FAILED go through MatchesCast, with the secret-castID fallback;
    CHANNEL_STOP -> Stop(), or Interrupt() when interruptedBy is set; everything is
    ignored while the engine is finishing; DELAYED re-times without re-igniting;
  * secret times: the engine refuses, a simple engine-timed tiled strip bar takes over
    and nothing throws;
  * the timer size (Parker: "if both casts are 10s or more... temporarily decrease the font size"):
    the timer FontString wears the small size (TIMER_SMALL_FONT_SIZE, parsed from the source; the
    largest half point that fits "99.9 / 99.9" in the 48 px box at scales 1, 0.8333 and 0.64) while the
    FIRST number of the readout (elapsed for a cast, remaining for a channel; never above the total) is
    at least TIMER_SMALL_FIRST_FROM, 9.95 (where "%.1f" turns to "10.0"), so it can flip mid cast; 8.5
    returns below that and at every cast start and stop; the font is re-applied only on a flip. A
    SECRET first number (the mock's sentinel raises on any comparison) is never compared: a second
    FontString takes the same readout (the raw SetFormattedText arguments are compared) and the mock
    engine's EvaluateElapsedDuration (EvaluateRemainingDuration for a channel), a Step curve at 9.95,
    drives the two layers' alphas (the engine's answer goes straight to SetAlpha, secret or plain); a
    missing, throwing or non-number engine answer, a refused SetAlpha or a missing curve API falls back
    to 8.5 pt clipped. A check that lists variants in __variants runs once per variant, each on a fresh
    client, and counts as one check; a source pin forbids truth tests on the curve results.

The mock is strict (a widget method it does not define fails as a nil call) and is NOT
the real client. Theme.lua's constants are read from the real file; the Theme helper
functions the pet cast bar calls, FrameHelpers' step runner and Layout are small stubs
here (the real ChevronCastBar.lua is loaded unchanged).

    python3 tools/petcastbar-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"


def _load_chevron_harness():
    # The engine harness already owns the strict widget mock and the Theme constant
    # extractor; reuse them rather than keep a second copy in step.
    spec = importlib.util.spec_from_file_location("chevroncastbar_harness", HERE / "chevroncastbar-harness.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHEV = _load_chevron_harness()


MOCKUP_HTML = Path(__file__).resolve().parent.parent / "mockups" / "gunsight-hud-v2-2026-10-02" / "gunsight-hud-v2-2026-10-02.html"
MONONOKI = ADDON / "Media" / "Fonts" / "MononokiNerdFontMono-Bold.ttf"
# Mononoki Bold's advance as a fraction of the em (561.5 / 1000, read from the TTF with PIL). The
# mockup's canvas measureText and this mock's GetStringWidth both use it, so the derived chevron
# count can be compared with the mockup's own.
MONONOKI_ADVANCE = 0.5615


def _mononoki_advance() -> float:
    try:
        from PIL import ImageFont
        return ImageFont.truetype(str(MONONOKI), 1000).getlength("0") / 1000
    except Exception:  # PIL or the font missing: the number above is the font's
        return MONONOKI_ADVANCE


def mockup_constants() -> dict:
    """The console-docked pet option C cast bar's numbers, parsed back out of the gunsight HUD mockup
    (peCastDc, peDcCount, PE_DC_*, PE_G.dc). A mockup move fails the checks that use them."""
    src = MOCKUP_HTML.read_text(encoding="utf-8")

    def grab(pattern: str, *names: str) -> dict:
        match = re.search(pattern, src)
        assert match, f"mockup no longer matches {pattern!r}; update this harness with it"
        return {n: (float(v) if re.fullmatch(r"[\d.]+", v) else v)
                for n, v in zip(names, match.groups(), strict=True)}

    c: dict = {}
    c.update(grab(r"var PE_X=\d+,PE_BOT=\d+,PE_PAD=(\d+),PE_LW=(\d+),PE_GX=(\d+),", "PAD", "LW", "GX"))
    c.update(grab(r"var PE_G=\{bf:\{[^}]*\},bx:\{[^}]*\},dc:\{W:(\d+),H:(\d+),TOPH:(\d+)\}\};", "PW", "PH", "TOPH"))
    c.update(grab(r"var PE_DC_RUNX=(\d+),PE_DC_PAD=PE_PAD,PE_DC_GAP=(\d+),PE_DC_CW=(\d+),PE_DC_CH=(\d+),"
                  r"PE_DC_PITCH=(\d+);", "RUNX", "GAP", "CW", "RUNH", "PITCH"))
    # peDcCount: the two measured samples, their padding, and the whole-chevron formula.
    c.update(grab(r"ctx\.font='700 (\d+)px \"Mononoki\",monospace';txt=ctx\.measureText\('([A-Z]+)'\)\.width\+(\d+);",
                  "NAMEFS", "NAMESAMPLE", "TEXTPAD"))
    m = re.search(r"ctx\.font='700 ([\d.]+)px \"Mononoki\",monospace';txt=Math\.max\(txt,ctx\.measureText\('([0-9. /]+)'\)"
                  r"\.width\+(\d+)\)", src)
    assert m, "mockup no longer measures the timer sample in peDcCount"
    c.update({"TIMERFS": float(m.group(1)), "TIMERSAMPLE": m.group(2), "TIMERPAD": float(m.group(3))})
    # peCastDc: bar height, plate alpha ghost/cast, chamfer, icon, outline alpha, name and timer rows.
    dc = re.search(r"function peCastDc\(x,y,w,st\)\{.*?\n\}", src, re.S)
    assert dc, "mockup no longer has peCastDc"
    body = dc.group(0)

    def grab_dc(pattern: str, *names: str) -> dict:
        match = re.search(pattern, body)
        assert match, f"peCastDc no longer matches {pattern!r}; update this harness with it"
        return {n: (float(v) if re.fullmatch(r"[\d.]+", v) else v)
                for n, v in zip(names, match.groups(), strict=True)}

    c.update(grab_dc(r"ghost=!c,bh=(\d+),a=ghost\?([\d.]+):([\d.]+),", "CBH", "PLATEIDLE", "PLATECAST"))
    c.update(grab_dc(r"chamfer\(x,y,w,bh,(\d+)\);A\(a\);ctx\.fillStyle='#0a0416'", "CHAMFER"))
    c.update(grab_dc(r"if\(!ghost\)\{A\(1\);glow\(K\.cyan,[\d.]+\);\}else A\(([\d.]+)\);", "OUTLINEIDLE"))
    c["OUTLINECAST"] = 1.0
    c.update(grab_dc(r"peIcon\(x\+(\d+),y\+(\d+),(\d+),(\d+),1\);", "ICONX", "ICONY", "ICON", "ICONCUT"))
    c.update(grab_dc(r"peT\('FIREBOLT',x\+w-(\d+),y\+(\d+),(\d+),K\.cyan", "NAMERIGHT", "NAMEBASE", "NAMEFS2"))
    c.update(grab_dc(r"peTimer\(st,x\+w-(\d+),y\+(\d+),([\d.]+),1\);", "TIMERRIGHT", "TIMERBASE", "TIMERFS2"))
    # The ghost run's stroke alpha (peRun, ghost branch).
    c.update(grab(r"if\(ghost\)\{peChev\(x\+i\*pitch,y,cw,ch\);A\(([\d.]+)\);ctx\.strokeStyle=K\.cyan", "GHOSTALPHA"))

    assert c["NAMEFS"] == c["NAMEFS2"] and c["TIMERFS"] == c["TIMERFS2"], "mockup font sizes disagree"
    assert c["PAD"] == c["TIMERRIGHT"] == c["NAMERIGHT"], "the right pad is PE_PAD"
    c["CAST_W"] = c["PW"] - c["PAD"] - (c["PAD"] + c["LW"] + c["GX"])        # cw = W - PE_PAD - cx
    c["RUNY"] = (c["CBH"] - c["RUNH"]) / 2                                   # ry = y + (bh - PE_DC_CH) / 2
    adv = _mononoki_advance()
    c["ADV"] = adv
    c["NAMEW"] = len(c["NAMESAMPLE"]) * c["NAMEFS"] * adv + c["TEXTPAD"]
    timer_w = len(c["TIMERSAMPLE"]) * c["TIMERFS"] * adv
    c["TIMERW"] = timer_w
    c["TEXTW"] = max(c["NAMEW"], timer_w + c["TIMERPAD"])
    c["TRACKW"] = c["CAST_W"] - c["RUNX"] - c["PAD"] - c["TEXTW"] - c["GAP"]
    c["COUNT"] = float(max(1, int((c["TRACKW"] - (c["CW"] + c["RUNH"] / 2)) // c["PITCH"]) + 1))
    return c


MOCKUP = mockup_constants()

THEME_CONSTANTS = CHEV.THEME_CONSTANTS + (
    "COLOR_HEALTH", "COLOR_CAST_NO_INTERRUPT", "FLAT_TEXTURE", "COLOR_BAR_TRACK", "COLOR_BAR_BORDER",
    "SLICE_CUT2_FILL_TEXTURE", "SLICE_CUT2_OUTLINE_TEXTURE",
    "SLICE_GLOW_TEXTURE", "SLICE_GLOW_PAD", "SLICE_GLOW_MARGIN",
    "CAST_CHEVRON_STRIP_TEXTURE", "CAST_CHEVRON_STRIP_TILE_W", "CAST_CHEVRON_STRIP_TILE_H",
)

# Widget methods and globals the pet cast bar needs on top of the engine's mock.
MOCK = r"""
local Region = getmetatable(UIParent)
__all = {}
__printed = {}
function print(...)
    local t = {}
    for i = 1, select("#", ...) do t[#t + 1] = tostring((select(i, ...))) end
    __printed[#__printed + 1] = table.concat(t, " ")
end

-- Hover-only mouse (FrameHelpers.HoverOnly), the tooltip the real spell-tooltip helpers draw into, and OnHide
-- hooks: the client fires OnHide when a shown frame hides.
function Region:SetMouseMotionEnabled(v) self._mouseMotion = v end
function Region:SetMouseClickEnabled(v) self._mouseClick = v end
function Region:EnableMouse(v) self._mouse = v end
local origHide, origSetShown = Region.Hide, Region.SetShown
local function fireHide(self, was)
    if was then for _, fn in ipairs(self._hooks and self._hooks.OnHide or {}) do fn(self) end end
end
function Region:Hide() local was = self._shown; origHide(self); fireHide(self, was) end
function Region:SetShown(v) local was = self._shown; origSetShown(self, v); if not v then fireHide(self, was) end end
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
function InCombatLockdown() return __inCombat == true end

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
    t._layer = layer
    __all[#__all + 1] = t
    return t
end
function Region:CreateFontString(name, layer)
    local t = origCreateTexture(self, name, layer)
    t._kind, t._layer, t._text = "FontString", layer, ""
    __all[#__all + 1] = t
    return t
end

-- Width by the real font's advance (Mononoki Bold, __mock.ADV of the em) at the size the font was
-- applied at; 6 a character before any font is applied. Records that it was asked: the spell
-- name must never be measured.
function Region:GetStringWidth()
    self._measured = (self._measured or 0) + 1
    local adv = self._fontSize and self._fontSize * __mock.ADV or 6
    return #(self._text or "") * adv
end
function Region:SetText(s) self._text = s end
function Region:GetText() return self._text end
-- SetFormattedText takes a secret like the real client does (the engine formats it, Lua never reads
-- it): the secret sentinel prints as 0 here, and the FontString remembers that it holds one.
function Region:SetFormattedText(fmt, ...)
    local n = select("#", ...)
    local args = { ... }
    -- The raw arguments, secret sentinels and all, so a check can compare what two FontStrings were
    -- handed argument by argument (rawequal), not just the text they printed.
    self._fmtArgs = { fmt = fmt, n = n, ... }
    self._secretText = false
    for i = 1, n do
        if rawequal(args[i], __SECRET) then args[i] = 0; self._secretText = true end
    end
    self._text = string.format(fmt, unpack(args, 1, n))
end
function Region:SetJustifyH(j) self._justifyH = j end
function Region:SetJustifyV(j) self._justifyV = j end
function Region:SetWidth(w) self._w = w end
function Region:SetWordWrap(v) self._wordWrap = v end
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
function Region:SetTimerDuration(d) self._timer = d; self._timerCalls = (self._timerCalls or 0) + 1 end
function Region:SetHorizTile(v) self._horizTile = v end
function Region:SetColorTexture(r, g, b, a) self._colorTexture = { r, g, b, a } end
function Region:SetAlphaFromBoolean(b, t, f) self._alpha = b and t or f end

-- The pet unit: a plain cast, or a channel, or nothing. Times are in ms, GetTime() domain.
__unit = { exists = true, guid = "Pet-0-1-A", cast = nil, chan = nil }
function UnitExists(u) return __unit.exists end
function UnitGUID(u) return __unit.guid end
function UnitCastingInfo(u)
    local c = __unit.cast
    if not c then return nil end
    return c.name, "", c.tex, c.startMS, c.endMS, false, c.castID, c.notInt, c.spellID or 1
end
function UnitChannelInfo(u)
    local c = __unit.chan
    if not c then return nil end
    return c.name, "", c.tex, c.startMS, c.endMS, false, c.notInt, c.spellID or 1
end
-- The curve API the secret-timing crossfade uses (C_CurveUtil.CreateCurve, Curve:SetType/AddPoint, the
-- Step type), with the engine's evaluation modelled: a Step curve returns the y of the last point whose x
-- is at or below the input, the first y below the first point.
Enum = { LuaCurveType = { Linear = 0, Step = 1 } }
C_CurveUtil = {
    CreateCurve = function()
        local curve = { points = {} }
        function curve:SetType(t) self.curveType = t end
        function curve:AddPoint(x, y) self.points[#self.points + 1] = { x, y } end
        return curve
    end,
}
local function stepEvaluate(curve, x)
    local y = curve.points[1] and curve.points[1][2] or 0
    for _, p in ipairs(curve.points) do
        if p[1] <= x then y = p[2] end
    end
    return y
end
__stepEvaluate = stepEvaluate   -- the checks read a built curve through the same model
-- A curve result the engine hands back for a secret duration: Lua can pass it to a setter and ask its
-- type, nothing else (any ordering, arithmetic or equality on it throws). The real value is kept in a
-- weak side table that only the harness reads.
__secretAlphas = setmetatable({}, { __mode = "k" })
local secretMeta = {
    __eq = function() error("secret curve result compared") end,
    __lt = function() error("secret curve result ordered") end,
    __le = function() error("secret curve result ordered") end,
    __add = function() error("secret curve result used in arithmetic") end,
    __concat = function() error("secret curve result concatenated") end,
    __tostring = function() error("secret curve result formatted") end,
}
local realType = type
function type(v)
    if realType(v) == "table" and __secretAlphas[v] ~= nil then return "number" end
    return realType(v)
end
__evalCalls = 0
__evalLog = {}   -- { method, curve } for every Evaluate* call, in order
-- The duration object a cast hands out. Flags on the cast table, read at CALL time so a check can flip
-- them mid cast: secretDur (every reader answers the secret sentinel), plainTotal (with it, the total
-- stays a number), secretTotal (only the total is secret), secretFirst (only elapsed/remaining are),
-- evaluatePlain / evaluateReturns / evaluateThrows / noEvaluate (what the Evaluate* methods do).
local function duration(c)
    if not c then return nil end
    local function secretFirst() return c.secretDur or c.secretFirst end
    local function secretTotal() return (c.secretDur and not c.plainTotal) or c.secretTotal end
    local function first(v) if secretFirst() then return __SECRET end return v end
    local function elapsed() return c.elapsed or (GetTime() - c.startMS / 1000) end
    local function remaining() return c.remaining or (c.endMS / 1000 - GetTime()) end
    local function total() return c.total or ((c.endMS - c.startMS) / 1000) end
    local d = {
        GetRemainingDuration = function() return first(remaining()) end,
        GetElapsedDuration = function() return first(elapsed()) end,
        GetTotalDuration = function() if secretTotal() then return __SECRET end return total() end,
    }
    if not c.noEvaluate then
        -- The engine evaluates the quantity against the curve. The documentation marks these
        -- SecretWhenCurveSecret only, so whether the answer is secret for a secret duration is not
        -- known; the mock hands back a secret object (the harder case for the code) unless the cast
        -- says evaluatePlain, and the code must work either way.
        local function evaluate(which, quantity, isSecret)
            return function(self, curve)
                __evalCalls = __evalCalls + 1
                __evalLog[#__evalLog + 1] = { which, curve }
                if c.evaluateThrows then error("Evaluate" .. which .. " refused") end
                if c.evaluateReturns ~= nil then return c.evaluateReturns end
                local y = stepEvaluate(curve, quantity())
                if not isSecret() or c.evaluatePlain then return y end
                local s = setmetatable({}, secretMeta)
                __secretAlphas[s] = y
                return s
            end
        end
        d.EvaluateElapsedDuration = evaluate("elapsed", elapsed, secretFirst)
        d.EvaluateRemainingDuration = evaluate("remaining", remaining, secretFirst)
        d.EvaluateTotalDuration = evaluate("total", total, secretTotal)
    end
    return d
end
function UnitCastingDuration(u) return duration(__unit.cast) end
function UnitChannelDuration(u) return duration(__unit.chan) end
"""

# Stubs for what PetCastBar.lua reads off FS, then the two real files.
WIRE = r"""
local Theme = FS.Theme
Theme.ApplyMono = function(fs, size, color) fs._fontSize = size; fs._color = color; fs._fontApplies = (fs._fontApplies or 0) + 1 end
Theme.ApplyNineSlice = function(tex, margin) tex._sliceMargin = margin; return true end
Theme.AddSliceTexture = function(frame, path, color, layer, sublevel, inset)
    local t = frame:CreateTexture(nil, layer or "BACKGROUND", nil, sublevel)
    t:SetTexture(path)
    t._inset = inset or 0
    if color then t:SetVertexColor(color[1], color[2], color[3], color[4] or 1) end
    return t
end
Theme.AddCut2Texture = function(frame, path, color, layer, sublevel, inset)
    local t = frame:CreateTexture(nil, layer or "BACKGROUND", nil, sublevel)
    t:SetTexture(path)
    t._inset, t._cut2 = inset or 0, true
    if color then t:SetVertexColor(color[1], color[2], color[3], color[4] or 1) end
    return t
end
FS.Layout = { Scale = function() return __layoutScale or 1 end, OnRescale = function(fn) __rescale = fn end }
__caretCalls = 0
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
    -- The old leading-edge caret. Its return shape is only here so the old file boots.
    CreateCaret = function() __caretCalls = __caretCalls + 1; return { host = CreateFrame("Frame", nil, UIParent) } end,
}
-- The real spell tooltip helpers (hover-only, cached id), loaded into a scratch FS and lent to the stub.
do
    local real = {}
    local scratch = { Theme = FS.Theme, IsSecret = FS.IsSecret, AurasReadable = function() return not InCombatLockdown() end, FrameHelpers = real }
    assert(loadstring(__helpers_source, "@Core/FrameHelpers.lua"))("forever-stuwave", scratch)
    for _, k in ipairs({ "HoverOnly", "SetTipSpell", "SpellIDForName", "AttachSpellTooltip", "RefreshSpellTooltip" }) do
        FS.FrameHelpers[k] = real[k]
    end
end
local container = CreateFrame("Frame", "FSPetContainer", UIParent)
local castSlot = CreateFrame("Frame", nil, container)
castSlot:SetSize(198, 26)   -- the console-dock cast slot: 198 wide, the top row 26 high
FS.PetFrame = { container = container, castSlot = castSlot }

-- Capture every engine run the pet bar builds, with the options it passed.
__runs = {}
__loadChevron = function(path, src)
    __load(path, src)
    local create = FS.ChevronCastBar.Create
    FS.ChevronCastBar.Create = function(parent, opts)
        local run = create(parent, opts)
        __runs[#__runs + 1] = { run = run, opts = opts, parent = parent }
        return run
    end
end
"""


_announced: list[bool] = []  # the override notice prints once per run, not once per boot


def boot() -> "LuaRuntime":
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(CHEV.MOCK)
    lua.execute(MOCK)
    theme_src = (ADDON / "Core/Theme.lua").read_text(encoding="utf-8")
    consts = [CHEV._extract_theme_constant(theme_src, n) for n in THEME_CONSTANTS]
    lua.eval("__load_theme_constants")(lua.table_from(consts))
    lua.globals()["__helpers_source"] = (ADDON / "Core/FrameHelpers.lua").read_text(encoding="utf-8")
    lua.execute(WIRE)
    lua.globals()["__mock"] = lua.table_from({k: float(v) for k, v in MOCKUP.items() if isinstance(v, float)})
    chevron = (ADDON / "Core/ChevronCastBar.lua").read_text(encoding="utf-8")
    lua.eval("__loadChevron")("Core/ChevronCastBar.lua", chevron)
    # PETCASTBAR_LUA points the harness at another copy of PetCastBar.lua (mutation runs).
    override = os.environ.get("PETCASTBAR_LUA")
    if override and not _announced:
        _announced.append(True)
        print(f"harness: PETCASTBAR_LUA={override}", file=sys.stderr)
    pet = Path(override or ADDON / "Modules/Pet/PetCastBar.lua")
    pet_src = pet.read_text(encoding="utf-8")
    lua.globals()["__pet_source"] = pet_src
    width = re.search(r"^local NAME_MAX_W = (\d+(?:\.\d+)?)\s*$", pet_src, re.M)
    assert width, "PetCastBar.lua no longer declares a plain `local NAME_MAX_W = <number>`"
    lua.globals()["__mock"]["NAMEMAXW"] = float(width.group(1))
    # The small timer size and the threshold; the checks fail on their own while the file has no such
    # constant (7.5 and 10 stand in only so the harness can boot; the threshold must be 9.95).
    small = re.search(r"^local TIMER_SMALL_FONT_SIZE = (\d+(?:\.\d+)?)\s*$", pet_src, re.M)
    lua.globals()["__mock"]["TIMERSMALL"] = float(small.group(1)) if small else 7.5
    from_s = re.search(r"^local TIMER_SMALL_FIRST_FROM = (\d+(?:\.\d+)?)\s*$", pet_src, re.M)
    lua.globals()["__mock"]["TIMERSMALLFROM"] = float(from_s.group(1)) if from_s else 10.0
    lua.eval("__load")("Modules/Pet/PetCastBar.lua", pet_src)
    return lua


CHECKS = r"""
local T = {}
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

-- Finds the first object in __all matching a predicate.
local function find(pred)
    for _, o in ipairs(__all) do if pred(o) then return o end end
end

-- Logs in (the loader frame's PLAYER_LOGIN) and hands back the pieces the checks poke.
local function world(before)
    __now = 100
    if before then before() end
    local login = find(function(o) return o._events and o._events.PLAYER_LOGIN end)
    ok(login, "the loader registers PLAYER_LOGIN")
    login._scripts.OnEvent(login, "PLAYER_LOGIN")
    local W = { castSlot = FS.PetFrame.castSlot, container = FS.PetFrame.container }
    local built = __runs[1]
    W.run, W.opts = built and built.run, built and built.opts
    W.events = find(function(o) return o._unitEvents and o._unitEvents.UNIT_SPELLCAST_START end)
    W.panel = W.opts and W.opts.scaleTarget
    W.strip = find(function(o) return o._kind == "StatusBar" end)
    -- The bar frame: the 26 high plate inside the slot that holds the chrome, the icon, the run, the
    -- spell name and the timer (the dedicated glow regions are its textures).
    W.bar = W.opts and W.opts.glowBurst and W.opts.glowBurst._parent
    -- The bar's two FontStrings: the timer (8.5 pt) and the spell name above it (8 pt), told apart by
    -- the size they were given at the scale the world was built at.
    local sc = __layoutScale or 1
    W.timerText = find(function(o) return o._kind == "FontString" and o._parent == W.bar and o._fontSize == __mock.TIMERFS * sc end)
    W.nameText = find(function(o) return o._kind == "FontString" and o._parent == W.bar and o._fontSize == __mock.NAMEFS * sc end)
    W.timerSmall = find(function(o) return o._kind == "FontString" and o._parent == W.bar and o._fontSize == __mock.TIMERSMALL * sc end)
    W.plate = find(function(o) return o._cut2 and o._parent == W.bar and o._layer == "BACKGROUND" and o._texture == FS.Theme.SLICE_CUT2_FILL_TEXTURE end)
    W.outline = find(function(o) return o._cut2 and o._parent == W.bar and o._texture == FS.Theme.SLICE_CUT2_OUTLINE_TEXTURE end)
    W.iconTexture = find(function(o) return o._kind == "Texture" and o._parent == W.bar and o._layer == "ARTWORK" end)
    W.iconHover = find(function(o) return o._hooks and o._hooks.OnEnter ~= nil and o._parent == W.bar end)
    W.ticker = find(function(o) return o._scripts and o._scripts.OnUpdate ~= nil and o ~= (W.run and W.run.frame) end)
    -- The icon box: the icon, its four 1px stroke edges and the shield overlay (everything on the
    -- bar that is anchored to the icon).
    W.iconBox = { W.iconTexture }
    for _, o in ipairs(__all) do
        if o._kind == "Texture" and o._parent == W.bar and o ~= W.iconTexture then
            local anchored = (o._allPoints == W.iconTexture)
            for _, pt in pairs(o._points) do if pt.rel == W.iconTexture then anchored = true end end
            if anchored then W.iconBox[#W.iconBox + 1] = o end
        end
    end
    -- The ghost row's outline chevron anchored over engine chevron i (nil before it exists).
    function W.ghost(i)
        local seg = W.run.segs[i]
        return seg and find(function(o)
            return o._kind == "Texture" and o._allPoints == seg.dim and o._texture == W.run.textures.outline
        end)
    end
    W.finished = 0
    function W.fire(event, unit, castID, spellID, interruptedBy)
        local f = W.events
        f._scripts.OnEvent(f, event, unit or "pet", castID, spellID or 1, interruptedBy)
    end
    -- A plain cast of CAST seconds starting at `t0`, announced by UNIT_SPELLCAST_START.
    function W.cast(id, t0, secs)
        __now = t0 or 100
        __unit.cast = { name = "Firebolt", tex = "icon", startMS = __now * 1000,
            endMS = (__now + (secs or CAST)) * 1000, castID = id or "C1", notInt = false }
        __unit.chan = nil
    end
    function W.channel(t0, secs)
        __now = t0 or 100
        __unit.chan = { name = "Drain", tex = "icon", startMS = __now * 1000,
            endMS = (__now + (secs or 4)) * 1000, notInt = false }
        __unit.cast = nil
    end
    function W.at(t)
        __now = t
        local fn = W.run.frame:GetScript("OnUpdate")
        if fn then fn(W.run.frame, 0) end
    end
    function W.stepTo(from, to, fps)
        local dt = 1 / (fps or 30)
        local t = from
        while t < to do t = math.min(to, t + dt); W.at(t) end
    end
    function W.clean()
        eq(#__printed, 0, "no printed errors: " .. tostring(__printed[1]))
    end
    -- The idle look (mockup option C ghost): the panel stays up and shows a row of OUTLINE chevrons
    -- (cyan, faint) under a faint plate and outline; the icon box, spell name, timer, caret and strip
    -- are gone.
    function W.idle(msg)
        msg = msg or "idle"
        eq(W.run:GetPhase(), "idle", msg .. ": engine idle")
        eq(W.run:IsBusy(), false, msg)
        eq(W.panel._shown, true, msg .. ": the panel stays up for the idle row")
        eq(W.run.frame._shown, true, msg .. ": the idle row is visible")
        eq(W.run.frame:GetScript("OnUpdate"), nil, msg .. ": no OnUpdate while idle")
        ok(W.run.count > 1, msg .. ": a row of chevrons")
        eq(W.nameText._text, "", msg .. ": no spell name")
        near(W.plate._alpha, __mock.PLATEIDLE, 1e-9, msg .. ": the plate is the mockup's ghost plate")
        near(W.outline._alpha, __mock.OUTLINEIDLE, 1e-9, msg .. ": its outline is the mockup's ghost outline")
        -- No icon box at all: the mockup's idle has no icon, no stroke, no shield.
        ok(#W.iconBox >= 5, msg .. ": the icon box is the icon, four edges and the shield")
        for _, o in ipairs(W.iconBox) do eq(o._shown, false, msg .. ": icon box piece hidden") end
        -- The ghost row: an OUTLINE chevron per engine chevron at the mockup's ghost alpha, cyan,
        -- and no filled chevron under it.
        local c = FS.Theme.COLOR_POWER
        for i = 1, W.run.count do
            local seg = W.run.segs[i]
            eq(seg.lit._shown, false, msg .. ": chevron " .. i .. " unlit")
            near(seg.dim._vc[4], 0, 1e-9, msg .. ": chevron " .. i .. " has no filled dim chevron")
            local g = W.ghost(i)
            ok(g, msg .. ": chevron " .. i .. " has a ghost outline")
            eq(g._shown, true, msg .. ": ghost outline " .. i .. " drawn")
            eq(g._parent, W.run.frame, msg .. ": ghost outlines live on the engine's run frame")
            near(g._vc[4], 0.24, 1e-9, msg .. ": the ghost row alpha")
            ok(g._vc[4] <= __mock.GHOSTALPHA, msg .. ": never brighter than the mockup's ghost (the outline art is thicker than its 1 px stroke)")
            near(g._vc[1], c[1], 1e-9, msg .. ": cyan"); near(g._vc[3], c[3], 1e-9)
        end
        local n = 0
        for _, o in ipairs(__all) do
            if o._kind == "Texture" and o._parent == W.run.frame and o._texture == W.run.textures.outline and o._shown then
                n = n + 1
            end
        end
        eq(n, W.run.count, msg .. ": exactly one visible ghost outline per chevron")
        eq(W.run.clip._shown, false, msg .. ": no caret")
        eq(W.strip._shown, false, msg .. ": no strip")
        eq(W.timerText._text, "", msg .. ": timer blank")
        eq(W.ticker._shown, false, msg .. ": timer ticker off")
        eq(W.iconTexture._texture, nil, msg .. ": icon blank")
        near(W.panel._alpha, 1, 1e-9, msg .. ": alpha back to 1")
        eq(W.run.burst._shown, false, msg .. ": no burst left over")
    end
    return W
end

local function litSinces(run)
    local r = {}
    for i = 1, run.count do r[i] = run.segs[i].litSince end
    return r
end

-- ---- build ------------------------------------------------------------------

function T.build_wires_one_engine_run_with_the_pet_options()
    local W = world()
    W.clean()
    eq(#__runs, 1, "exactly one engine run")
    eq(W.opts.gapFraction, 0.2, "the pet run geometry: gapFraction 0.2 (7 arm, 14 high, pitch 10)")
    ok(W.panel, "a scale target is passed")
    ok(W.panel ~= W.container, "the pop never scales the whole pet container")
    ok(W.panel ~= W.castSlot, "the cast bar has its own frame inside the slot")
    eq(W.panel._parent, W.castSlot, "the cast bar's frame sits in the cast slot")
    eq(W.opts.alphaTarget, W.panel, "the outage dims the cast bar's own frame")
    ok(W.outline and W.opts.flareTarget == W.outline, "the cast bar's own outline is the engine's flare target")
    local g, h = W.opts.glowBurst, W.opts.holdGlow
    ok(g and h and g ~= h, "dedicated burst and hold glow regions")
    eq(g._kind, "Texture"); eq(h._kind, "Texture")
    eq(g._shown, false, "the burst glow starts hidden")
    near(h._alpha, 0, 1e-9, "the hold glow starts dark")
    W.idle("at build")
    eq(W.run.H, __mock.RUNH, "run is the pet run's 14 high")
    near(W.run.segs[2].x0 - W.run.segs[1].x0, __mock.PITCH, 0.5, "pitch 10")
    eq(W.run.count, __mock.COUNT, "the mockup's own chevron count")
end

function T.build_leaves_no_caret_and_no_triangles()
    local W = world()
    W.clean()
    eq(__caretCalls, 0, "the old leading-edge caret is gone")
    for _, o in ipairs(__all) do
        if o._texture then ok(not tostring(o._texture):find("pet_cast_triangle", 1, true), "no triangle texture") end
    end
end

function T.timer_reads_elapsed_over_total_at_the_mockup_font_size()
    local W = world()
    eq(W.timerText._fontSize, __mock.TIMERFS, "timer font size")
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    ok(W.ticker, "the timer ticker exists")
    W.ticker._scripts.OnUpdate(W.ticker, 0.2)
    eq(W.timerText._text, "0.0 / 2.5", "elapsed over total, read through the duration object")
    __now = 101
    W.ticker._scripts.OnUpdate(W.ticker, 0.2)
    eq(W.timerText._text, "1.0 / 2.5")
    W.clean()
end

function T.a_channel_timer_counts_down_over_total()
    local W = world()
    W.channel(100, 4); W.fire("UNIT_SPELLCAST_CHANNEL_START")
    __now = 101
    W.ticker._scripts.OnUpdate(W.ticker, 0.2)
    eq(W.timerText._text, "3.0 / 4.0", "a channel shows what is left over the total")
    W.clean()
end

-- ---- the console-dock cast bar's numbers, parsed out of the mockup ---------

-- Point offsets as a check reads them: { x, y } of the named point.
local function pt(frame, point)
    local p = frame._points[point]
    ok(p, "no " .. point .. " anchor")
    return p.x, p.y, p.rel, p.relPoint
end

-- The track the run has to fit at scale s: the slot, less the run's left edge, the fixed text column
-- (NAME_MAX_W), the right pad and the gap. A pure function of constants.
local function track_at(s)
    local m = __mock
    return (m.CAST_W - m.RUNX - m.NAMEMAXW - m.PAD - m.GAP) * s
end

-- The run is the largest whole-chevron run inside the track (FitWithin's contract).
local function fits_the_track(W, s)
    local track = track_at(s)
    ok(W.run.W <= track + 1e-6, "the run (" .. W.run.W .. ") fits the track (" .. track .. ") at scale " .. s)
    ok(W.run.W + W.run.pitch > track - 1e-6, "and no further chevron would fit, at scale " .. s)
end

local function geometry_at(s, wantCount)
    local W = world(function() __layoutScale = s end)
    W.clean()
    local m = __mock
    -- The bar: the mockup's 26 high plate, the whole slot.
    eq(W.bar._parent, W.panel, "the bar sits in the cast bar's panel")
    near(W.bar._h, m.CBH * s, 1e-9, "bar is CBH high at scale " .. s)
    local _, _, rel1 = pt(W.bar, "TOPLEFT"); local _, _, rel2 = pt(W.bar, "TOPRIGHT")
    eq(rel1, W.panel); eq(rel2, W.panel, "the bar spans the slot's width")
    -- The icon: 20 square at (3, 3) inside the bar.
    near(W.iconTexture._w, m.ICON * s, 1e-9, "icon size at scale " .. s)
    near(W.iconTexture._h, m.ICON * s, 1e-9)
    local ix, iy = pt(W.iconTexture, "TOPLEFT")
    near(ix, m.ICONX * s, 1e-9, "icon x"); near(iy, -m.ICONY * s, 1e-9, "icon y")
    -- The run: 14 high from x 28, centred in the bar.
    local run = W.opts.points[1][2]
    local rx, ry = pt(run, "TOPLEFT")
    near(rx, m.RUNX * s, 1e-9, "run x at scale " .. s); near(ry, -m.RUNY * s, 1e-9, "run y")
    near(run._h, m.RUNH * s, 1e-9, "run height")
    near(W.run.H, m.RUNH * s, 1e-9, "the engine run is RUNH high")
    -- The text column: the spell name over the timer, both right aligned, the pad in from the right.
    eq(W.timerText._fontSize, m.TIMERFS * s, "timer font at scale " .. s)
    eq(W.nameText._fontSize, m.NAMEFS * s, "name font at scale " .. s)
    eq(W.timerText._justifyH, "RIGHT"); eq(W.nameText._justifyH, "RIGHT")
    local nx, ny, nrel = pt(W.nameText, "RIGHT")
    local tx, ty, trel = pt(W.timerText, "RIGHT")
    near(nx, -m.NAMERIGHT * s, 1e-9, "name pad from the right edge"); near(tx, -m.TIMERRIGHT * s, 1e-9, "timer pad")
    eq(nrel, W.bar); eq(trel, W.bar)
    -- Rows: the mockup's baselines less 0.36 em, the glyph middle, within half a design px.
    near(ny, -(m.NAMEBASE - 0.36 * m.NAMEFS) * s, 0.5 * s, "name row at scale " .. s)
    near(ty, -(m.TIMERBASE - 0.36 * m.TIMERFS) * s, 0.5 * s, "timer row at scale " .. s)
    ok(ny > ty, "the spell name sits above the timer")
    -- The slot the track is computed from is the mockup's cast slot.
    near(W.castSlot._w, m.CAST_W, 1e-9, "the cast slot is the mockup's 198 wide")
    near(W.castSlot._h, m.CBH, 1e-9, "and one bar high")
    fits_the_track(W, s)
    eq(W.run.count, wantCount, "chevron count at scale " .. s)
    -- The name column is the fixed NAME_MAX_W with word wrap off, so a long or secret name is cut by
    -- the engine's own truncation instead of wrapping or running into the chevrons.
    near(W.nameText._w, m.NAMEMAXW * s, 1e-6, "the name FontString is NAME_MAX_W wide at scale " .. s)
    eq(W.nameText._wordWrap, false, "the name does not wrap")
    -- The timer is NAME_MAX_W + RUN_GAP wide (the gap is free: the run ends before it): its values may
    -- be secret, so the readout cannot be shortened by comparing them; a wider one ("10.0 / 12.5",
    -- about 52 px) is cut at the box, right justified, and never grows leftwards over the chevrons.
    near(W.timerText._w, (m.NAMEMAXW + m.GAP) * s, 1e-6, "the timer FontString is NAME_MAX_W + RUN_GAP wide at scale " .. s)
    eq(W.timerText._wordWrap, false, "the timer does not wrap")
    -- The right justified timer box's left edge, from the slot's right edge, the pad and the box width,
    -- never passes the run's right edge (its x plus the engine run's width), so the widened box cannot
    -- overlap the chevrons. Computed from the run span, nothing hardcoded.
    local timerLeft = m.CAST_W * s + tx - W.timerText._w
    local runRight = rx + W.run.W
    ok(runRight <= timerLeft + 1e-6, "the timer box (left " .. timerLeft .. ") does not overlap the run (right " .. runRight .. ") at scale " .. s)
    return W
end

function T.cast_bar_geometry_matches_the_mockup_at_scale_1()
    local W = geometry_at(1, 11)
    local m = __mock
    near(W.run.pitch, m.PITCH, 1e-9, "pitch")
    eq(W.run.count, m.COUNT, "the mockup's own count (peDcCount)")
    eq(W.run.count, 11, "11 chevrons at scale 1")
    near(W.run.span, (m.COUNT - 1) * m.PITCH + m.CW + m.RUNH / 2, 1e-9, "the run's span is the mockup's")
end

function T.cast_bar_geometry_matches_the_mockup_at_scale_0_8333()
    eq(geometry_at(0.8333, 11).run.count, 11, "11 chevrons at scale 0.8333")
end

function T.cast_bar_geometry_matches_the_mockup_at_scale_0_64()
    eq(geometry_at(0.64, 10).run.count, 10, "10 chevrons at scale 0.64")
end

-- The mockup draws the bar chamfer 4 and the icon chamfer 3; the baked cut textures are 6 (a known
-- deviation, documented in the file header). Pinning the parsed numbers makes a mockup change fail here.
function T.the_mockups_cut_sizes_are_4_on_the_bar_and_3_on_the_icon()
    eq(__mock.CHAMFER, 4, "the bar's chamfer in peCastDc")
    eq(__mock.ICONCUT, 3, "the icon's chamfer in peIcon")
end

-- NAME_MAX_W is a design constant picked by eye, not measured. It must hold the timer sample at
-- 8.5 pt (the widest readout), show about 9 characters of the 8 pt name, and leave the track a
-- comfortable margin either side of the 11 chevron count (the run snaps down to whole chevrons, so
-- the count is only wrong if the track strays outside [need, need + pitch)).
function T.name_max_w_is_a_fixed_constant_that_fits_the_timer_and_nine_name_characters()
    local m = __mock
    ok(m.NAMEMAXW >= m.TIMERW, "NAME_MAX_W " .. m.NAMEMAXW .. " holds the timer sample " .. m.TIMERW)
    ok(m.NAMEMAXW >= 9 * m.NAMEFS * m.ADV, "NAME_MAX_W holds 9 characters of the 8 pt name")
    -- The timer box is NAME_MAX_W + RUN_GAP wide: "0.0 / 12.0" (10 characters) fits whole.
    ok(m.NAMEMAXW + m.GAP >= 10 * m.TIMERFS * m.ADV, "the timer box holds \"0.0 / 12.0\" (" .. 10 * m.TIMERFS * m.ADV .. ")")
    local need = (m.COUNT - 1) * m.PITCH + m.CW + m.RUNH / 2
    local track = track_at(1)
    ok(track - need >= 1, "the 11 chevron track clears the need (" .. need .. ") by at least 1 px: " .. track)
    ok(need + m.PITCH - track >= 5, "and sits well short of a 12th chevron: " .. track)
end

-- The chevron count of the track a given NAME_MAX_W leaves at scale s, through the engine's own
-- FitWithin and Layout (the model ApplyGeometry uses), after the world was rescaled to s.
local function count_with_width(W, width, s)
    local m = __mock
    local track = (m.CAST_W - m.RUNX - width - m.PAD - m.GAP) * s
    local runWidth = W.run:FitWithin(track, m.RUNH * s) or W.run:FitWidth(1, m.RUNH * s) or track
    W.run:Layout(runWidth, m.RUNH * s)
    return W.run.count
end

-- The documented window: NAME_MAX_W 39 to 45 all keep 11 / 11 / 10 chevrons at scales 1, 0.8333 and
-- 0.64, and 38 and 46 each break that count at some scale, so the shipped 43 sits mid window. The
-- count is a pure function of constants (the font is never consulted, pinned by the source check
-- below), so a width change moves it only through this track.
function T.name_max_w_39_to_45_keep_11_11_10_and_38_and_46_break_it()
    local want = { [1] = 11, [0.8333] = 11, [0.64] = 10 }
    local broken = {}
    local W = world()
    for _, s in ipairs({ 1, 0.8333, 0.64 }) do
        __layoutScale = s
        __rescale()
        W.clean()
        for width = 38, 46 do
            local count = count_with_width(W, width, s)
            if width >= 39 and width <= 45 then
                eq(count, want[s], "NAME_MAX_W " .. width .. " at scale " .. s)
            elseif count ~= want[s] then
                broken[width] = true
            end
        end
    end
    ok(broken[38], "38 breaks the 11 / 11 / 10 counts at some scale")
    ok(broken[46], "46 breaks the 11 / 11 / 10 counts at some scale")
    ok(__mock.NAMEMAXW >= 39 and __mock.NAMEMAXW <= 45, "the shipped NAME_MAX_W is inside the window")
end

function T.the_run_is_sized_with_fit_within_over_the_text_column_track()
    local W = world()
    local m = __mock
    local calls = {}
    local orig = W.run.FitWithin
    W.run.FitWithin = function(self, maxWidth, height)
        calls[#calls + 1] = { maxWidth, height }
        return orig(self, maxWidth, height)
    end
    for _, s in ipairs({ 1, 0.8333, 0.64 }) do
        calls = {}
        __layoutScale = s
        __rescale()
        W.clean()
        eq(#calls, 1, "one FitWithin per layout at scale " .. s)
        near(calls[1][1], track_at(s), 1e-6, "FitWithin gets the slot less run x, text column, pad and gap at scale " .. s)
        near(calls[1][2], m.RUNH * s, 1e-9, "and the run height")
        fits_the_track(W, s)
    end
end

-- One behavioural pin for "no font dependence"; the source pin below owns the rest (no GetStringWidth
-- anywhere in the file). The client's text measuring is made to throw and the advance is doubled: the
-- build, a rescale, a cast and its verdict must neither ask the font nor change the count.
function T.the_count_does_not_depend_on_the_font()
    local W = world(function()
        __mock.ADV = __mock.ADV * 2
        getmetatable(UIParent).GetStringWidth = function() error("restricted") end
    end)
    W.clean()
    eq(W.run.count, 11, "11 chevrons at build whatever the font")
    __layoutScale = 0.64; __rescale()
    eq(W.run.count, 10, "10 chevrons after a rescale to 0.64")
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    __now = 101; W.ticker._scripts.OnUpdate(W.ticker, 0.2)
    __unit.cast = nil
    W.fire("UNIT_SPELLCAST_STOP", "pet", "C1")
    W.at(103.81)
    eq(W.timerText._measured, nil, "the timer is never measured")
    eq(W.nameText._measured, nil, "nor is the spell name")
    W.clean()
end

function T.there_is_no_label_tab()
    local W = world()
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    -- Nothing hangs off the bar: the panel's only frame child is the bar, and the bar has no
    -- wedge texture.
    for _, o in ipairs(__all) do
        if o._kind == "Frame" and o._parent == W.panel then eq(o, W.bar, "the only frame in the panel is the bar") end
        if o._texture then ok(not tostring(o._texture):find("tab_slant", 1, true), "no tab wedge texture") end
    end
    local code = __pet_source:gsub("%-%-[^\n]*", "")
    for _, word in ipairs({ "tab_slant", "LayoutTab", "ShowTab", "HideTab", "BuildTab", "tabName", "tabParts", "TAB_" }) do
        ok(not code:find(word, 1, true), "PetCastBar.lua still mentions " .. word)
    end
    W.clean()
end

function T.the_spell_name_shows_above_the_timer_while_casting()
    local W = world()
    local m = __mock
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    eq(W.nameText._text, "Firebolt", "the spell name, as is")
    eq(W.nameText._shown, true)
    eq(W.nameText._fontSize, m.NAMEFS, "name text size")
    eq(W.nameText._color, FS.Theme.COLOR_POWER, "the name is cyan")
    W.ticker._scripts.OnUpdate(W.ticker, 0.2)
    eq(W.timerText._text, "0.0 / 2.5", "the timer still sits under it")
    near(W.plate._alpha, m.PLATECAST, 1e-9, "the plate firms up while casting")
    near(W.outline._alpha, m.OUTLINECAST, 1e-9, "and so does the outline")
    __unit.cast = nil
    W.fire("UNIT_SPELLCAST_STOP", "pet", "C1")
    W.at(103.81)
    W.idle("the name goes with the cast")
    W.clean()
end

function T.a_secret_spell_name_reaches_set_text_untouched_and_unmeasured()
    local W = world()
    __now = 100
    __unit.cast = { name = __SECRET, tex = "icon", startMS = 100 * 1000, endMS = 102.5 * 1000, castID = "C1", notInt = false }
    local okf, err = pcall(W.fire, "UNIT_SPELLCAST_START")
    ok(okf, "no throw on a secret name: " .. tostring(err))
    W.clean()
    ok(rawequal(W.nameText._text, __SECRET), "the secret name went to SetText as is")
    eq(W.nameText._measured, nil, "and was never measured")
    -- A rescale with the secret name on screen does not touch it either.
    __layoutScale = 0.64
    ok(pcall(__rescale), "a rescale with a secret name shown")
    ok(rawequal(W.nameText._text, __SECRET), "still the same value after a rescale")
    eq(W.nameText._measured, nil)
    -- And the secret timing path (strip) takes the name the same way.
    __unit.cast = { name = __SECRET, tex = "icon", startMS = __SECRET, endMS = __SECRET, castID = __SECRET_ID,
        notInt = false, remaining = 1.5, elapsed = 0.5, total = 2.0 }
    ok(pcall(W.fire, "UNIT_SPELLCAST_START"), "no throw on a secret name with secret times")
    ok(rawequal(W.nameText._text, __SECRET))
    eq(W.nameText._measured, nil)
end

-- Tooltips: the icon is a hover-only frame over the icon box; the spell id comes from the cast and is cached on
-- the frame, a secret id is never stored.
function T.the_pet_cast_icon_shows_the_casting_spell_on_hover()
    local W = world()
    ok(W.iconHover, "the icon has a hover frame")
    ok(W.iconHover._mouseMotion == true and W.iconHover._mouseClick == false and W.iconHover._mouse == nil,
        "hover only: motion on, clicks off, EnableMouse never called")
    W.cast("C1"); __unit.cast.spellID = 3110
    W.fire("UNIT_SPELLCAST_START")
    hover(W.iconHover)
    ok(TT.owner == W.iconHover and TT.spellID == 3110, "the cast's spell: " .. tostring(TT.spellID))
    -- the next cast replaces it while the cursor stays put
    W.cast("C2"); __unit.cast.spellID = 5676
    W.fire("UNIT_SPELLCAST_START")
    ok(TT.owner == W.iconHover and TT.spellID == 5676, "the open tip follows the new cast: " .. tostring(TT.spellID))
    -- a channel reads its id from UnitChannelInfo
    W.channel(); __unit.chan.spellID = 689
    W.fire("UNIT_SPELLCAST_CHANNEL_START")
    ok(TT.owner == W.iconHover and TT.spellID == 689, "a channel's spell: " .. tostring(TT.spellID))
    -- the cast ends: the icon box goes and takes the tip with it
    __unit.chan = nil
    W.fire("UNIT_SPELLCAST_CHANNEL_STOP")
    ok(not TT.shown, "no tip once the cast is gone")
    ok(W.iconHover.fsSpellID == nil, "and no id is kept")
end

function T.a_secret_spell_id_shows_no_stale_tip()
    local W = world()
    W.cast("C1"); __unit.cast.spellID = 3110
    W.fire("UNIT_SPELLCAST_START")
    hover(W.iconHover)
    ok(TT.spellID == 3110, "the plain cast shows")
    W.cast("C2"); __unit.cast.spellID = __SECRET
    ok(pcall(W.fire, "UNIT_SPELLCAST_START"), "no throw on a secret spell id")
    ok(TT.spellID ~= 3110, "the previous cast's spell is not shown for the secret one")
    ok(W.iconHover.fsSpellID == nil, "a secret id is never stored")
    ok(TT.text == "Firebolt", "the plain name is what is left")
    W.cast("C3"); __unit.cast.spellID = __SECRET; __unit.cast.name = __SECRET
    ok(pcall(W.fire, "UNIT_SPELLCAST_START"), "no throw on a secret id and name")
    ok(not TT.shown, "nothing known, nothing shown")
    ok(W.iconHover.fsName == nil, "a secret name is never stored")
end

function T.the_spell_name_is_never_measured_or_compared_in_the_source()
    -- A secret name cannot be compared (Lua cannot trap `secret ~= nil`, and a behavioral check cannot
    -- see a truth test), so pin the source: the name reaches the FontString by one SetText and
    -- every use of the name FontString is layout or that SetText.
    local code = __pet_source:gsub("%-%-[^\n]*", "")
    local uses, names = 0, 0
    for line in code:gmatch("[^\n]+") do
        if line:find("nameText", 1, true) then
            uses = uses + 1
            for _, bad in ipairs({ "GetStringWidth", "GetWidth", "GetText", "IsSecret", "==", "~=", "type(", "Present" }) do
                ok(not line:find(bad, 1, true), "the name FontString is used with " .. bad .. ": " .. line)
            end
        end
        if line:find("info.name", 1, true) then
            names = names + 1
            -- ShowName, and SetTipSpell (it stores a plain name and clears a secret one, FrameHelpers' contract)
            ok(line:find("ShowName(info.name)", 1, true) or line:find("SetTipSpell(iconHover, info.spellID, info.name)", 1, true),
                "info.name goes only to ShowName and SetTipSpell: " .. line)
        end
    end
    ok(uses >= 5, "the name FontString is built and seated")
    eq(names, 2, "info.name appears on exactly two code lines")
    -- Nothing in the file measures text at all: the column is a constant.
    for _, word in ipairs({ "GetStringWidth", "GetUnboundedStringWidth", "GetWidth", "MeasureTextColumn", "TRACK_SLACK" }) do
        ok(not code:find(word, 1, true), "PetCastBar.lua still uses " .. word)
    end
end

function T.nothing_here_is_protected_so_there_is_no_combat_gate()
    local code = __pet_source:gsub("%-%-[^\n]*", "")
    for _, word in ipairs({ "SetAttribute", "InCombatLockdown", "SecureActionButton", "RegisterStateDriver", "RegisterForClicks" }) do
        ok(not code:find(word, 1, true), "PetCastBar.lua uses " .. word .. ", it would need a combat gate")
    end
end

-- ---- idle ghost vs casting look ---------------------------------------------

function T.casting_shows_the_icon_box_and_lit_chevrons_and_hides_the_ghost_row()
    local W = world()
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    eq(W.run:GetPhase(), "cast")
    eq(W.iconTexture._shown, true, "the icon shows while casting")
    eq(W.iconTexture._texture, "icon", "and holds the spell icon")
    for _, o in ipairs(W.iconBox) do eq(o._shown, true, "icon box piece shown while casting") end
    for i = 1, W.run.count do
        local g = W.ghost(i)
        ok(g, "ghost " .. i .. " exists")
        eq(g._shown, false, "ghost outline " .. i .. " hidden while casting")
        near(W.run.segs[i].dim._vc[4], 0.2, 1e-9, "the engine's own unlit chevron look while casting")
    end
    __unit.cast = nil
    W.fire("UNIT_SPELLCAST_STOP", "pet", "C1")
    W.at(103.81)
    W.idle("the icon box and ghost swap back after the cast")
    W.clean()
end

function T.the_ghost_row_follows_a_rescale_at_idle()
    local W = world()
    W.idle("before")
    __layoutScale = 0.64
    __rescale()
    W.idle("after a rescale")
    W.clean()
end

function T.a_channel_then_idle_keeps_the_ghosts_upright_and_the_box_hidden()
    local W = world()
    local function upright(msg)
        for i = 1, W.run.count do
            local g = W.ghost(i)
            ok(g, msg .. ": ghost " .. i .. " exists")
            local tc = g._tc
            ok(tc[1] == 0 and tc[2] == 1 and tc[3] == 0 and tc[4] == 1,
                msg .. ": ghost " .. i .. " texcoords are upright (0,1,0,1), got " .. table.concat(tc, ","))
        end
    end
    upright("at idle")
    W.channel(100, 4); W.fire("UNIT_SPELLCAST_CHANNEL_START")
    eq(W.iconTexture._shown, true, "icon box shows for a channel")
    -- Premise guard: the engine mirrors a channel's own chevrons. If this stops holding, the
    -- after-channel upright check below no longer proves the ghosts were un-mirrored.
    eq(W.run.segs[1].dim._tc[1], 1, "the engine's chevrons are mirrored mid channel")
    __unit.chan = nil
    W.fire("UNIT_SPELLCAST_CHANNEL_STOP", "pet", "X", 1, nil)
    W.at(102)
    W.idle("after a quiet channel end")
    upright("after a channel")
    W.clean()
end

function T.a_shown_name_keeps_its_text_and_is_reseated_at_the_new_scale_on_rescale()
    local W = world()
    local m = __mock
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    eq(W.nameText._text, "Firebolt")
    __layoutScale = 0.64
    __rescale()
    W.clean()
    local s = 0.64
    eq(W.nameText._text, "Firebolt", "the name survives the rescale")
    eq(W.nameText._fontSize, m.NAMEFS * s, "name font at the new scale")
    local x = pt(W.nameText, "RIGHT")
    near(x, -m.NAMERIGHT * s, 1e-9, "name pad at the new scale")
    eq(W.timerText._fontSize, m.TIMERFS * s, "timer font at the new scale")
    __unit.cast = nil
    W.fire("UNIT_SPELLCAST_STOP", "pet", "C1")
    W.at(103.81)
    W.idle("after the rescaled cast")
    W.clean()
end

-- The ghost row follows the derived count at every scale: one outline per engine chevron.
function T.the_ghost_row_follows_the_derived_count_at_every_scale()
    local W = world()
    for _, s in ipairs({ 1, 0.8333, 0.64 }) do
        __layoutScale = s
        __rescale()
        W.clean()
        ok(W.run.count >= 10 and W.run.count <= 12, "count " .. W.run.count .. " at scale " .. s)
        W.idle("at scale " .. s)
    end
end

-- A chevron count that changes (a narrower run, then wider again) must recycle the ghost pool:
-- no texture is created per sync, every ghost past the count is hidden, and each shown ghost sits
-- on the CURRENT segment's dim texture. Checked at idle and across a cast (ghosts hidden, still
-- synced) back to idle.
function T.the_ghost_pool_is_recycled_and_synced_when_the_chevron_count_changes()
    local W = world()
    local full = W.run.count
    local maxSeen = full
    local fullW, fullH = W.run.W, W.run.H
    local function relayout(frac)
        W.run:Layout(fullW * frac, fullH)
        if W.run.count > maxSeen then maxSeen = W.run.count end
    end
    -- The ghost object seen for each chevron index the first time, to prove relayouts recycle it.
    local seen = {}
    -- Audits the pool: every outline texture on the run frame (shown or not) is counted, and each
    -- chevron's ghost is the same object it was before every relayout.
    local function audit(msg, idle)
        local pool, shown = 0, 0
        for _, o in ipairs(__all) do
            if o._kind == "Texture" and o._parent == W.run.frame and o._texture == W.run.textures.outline then
                pool = pool + 1
                if o._shown then shown = shown + 1 end
            end
        end
        ok(pool <= maxSeen, msg .. ": " .. pool .. " outline textures created, but at most " .. maxSeen .. " were ever needed")
        eq(shown, idle and W.run.count or 0, msg .. ": shown ghosts")
        for i = 1, W.run.count do
            local g = W.ghost(i)
            ok(g, msg .. ": chevron " .. i .. " has a ghost anchored to its dim texture")
            eq(g._shown, idle and true or false, msg .. ": ghost " .. i)
            seen[i] = seen[i] or g
            ok(rawequal(seen[i], g), msg .. ": ghost " .. i .. " is the same object as before the relayouts")
        end
        for i = W.run.count + 1, #W.run.segs do
            local g = W.ghost(i)
            if g then eq(g._shown, false, msg .. ": ghost " .. i .. " is past the count and hidden") end
        end
    end
    audit("start", true)

    relayout(0.5)
    ok(W.run.count < full, "a narrower run has fewer chevrons")
    audit("narrow at idle", true)
    relayout(1)
    eq(W.run.count, full, "the full width has the full count back")
    audit("wide again at idle", true)
    relayout(0.5)
    audit("narrow again at idle", true)

    -- Mid cast: the ghosts are hidden, but a relayout still keeps the pool in step.
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    eq(W.run:GetPhase(), "cast")
    audit("narrow, mid cast", false)
    relayout(1)
    audit("wide, mid cast", false)
    relayout(0.5)
    audit("narrow again, mid cast", false)
    __unit.cast = nil
    W.fire("UNIT_SPELLCAST_STOP", "pet", "C1")
    W.at(103.81)
    audit("narrow, idle after the cast", true)
    relayout(1)
    W.idle("wide, idle after the cast")
    audit("wide, idle after the cast", true)
    W.clean()
end

-- ---- events -----------------------------------------------------------------

function T.registers_the_pet_unit_events_and_never_succeeded()
    local W = world()
    local want = { "UNIT_SPELLCAST_START", "UNIT_SPELLCAST_STOP", "UNIT_SPELLCAST_FAILED",
        "UNIT_SPELLCAST_INTERRUPTED", "UNIT_SPELLCAST_DELAYED", "UNIT_SPELLCAST_CHANNEL_START",
        "UNIT_SPELLCAST_CHANNEL_STOP", "UNIT_SPELLCAST_CHANNEL_UPDATE" }
    for _, e in ipairs(want) do eq(W.events._unitEvents[e], "pet", e .. " on unit pet") end
    eq(W.events._unitEvents.UNIT_SPELLCAST_SUCCEEDED, nil, "SUCCEEDED is not a verdict")
    eq(W.events._events.UNIT_SPELLCAST_SUCCEEDED, nil, "SUCCEEDED is not registered either")
    eq(W.events._events.UNIT_PET, true, "UNIT_PET on the owner token")
end

-- ---- verdicts ---------------------------------------------------------------

function T.cast_then_matching_stop_succeeds_holds_then_hides()
    local W = world()
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    eq(W.run:GetPhase(), "cast"); eq(W.panel._shown, true, "panel shown for the cast")
    W.stepTo(100, 102.5)
    __unit.cast = nil
    W.fire("UNIT_SPELLCAST_STOP", "pet", "C1")
    eq(W.run:GetPhase(), "hold", "matching STOP calls Succeed"); eq(W.run.burst._groups[1].plays, 1, "lock-in played")
    eq(W.panel._shown, true, "the panel stays shown through the hold")
    W.stepTo(102.5, 103.6)
    eq(W.run:GetPhase(), "fade"); eq(W.panel._shown, true, "and through the fade")
    W.at(103.81)
    W.idle("back to the idle row once onFinished fired")
    W.clean()
end

function T.failed_with_another_castid_mid_cast_is_ignored()
    local W = world()
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    W.stepTo(100, 101)
    W.fire("UNIT_SPELLCAST_FAILED", "pet", "OTHER")
    W.fire("UNIT_SPELLCAST_STOP", "pet", "OTHER")
    W.fire("UNIT_SPELLCAST_INTERRUPTED", "pet", "OTHER")
    eq(W.run:GetPhase(), "cast", "a different castID touches nothing"); eq(W.panel._shown, true)
    W.clean()
end

function T.interrupted_with_the_matching_castid_runs_the_outage()
    local W = world()
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    W.stepTo(100, 101)
    __unit.cast = nil
    W.fire("UNIT_SPELLCAST_INTERRUPTED", "pet", "C1")
    eq(W.run:GetPhase(), "intr", "outage"); eq(W.panel._shown, true, "panel stays up for the outage")
    W.at(101.3); eq(W.run.intrPhase, "stutter")
    W.at(101.99); eq(W.panel._shown, true)
    W.at(102.01); W.idle("back to the idle row after the outage")
    W.clean()
end

function T.channel_stop_without_interrupted_by_stops_quietly()
    local W = world()
    W.channel(100, 4); W.fire("UNIT_SPELLCAST_CHANNEL_START")
    eq(W.run:GetPhase(), "cast"); eq(W.run.channel, true, "channel mode"); eq(W.panel._shown, true)
    W.stepTo(100, 101)
    __unit.chan = nil
    W.fire("UNIT_SPELLCAST_CHANNEL_STOP", "pet", "X", 1, nil)
    W.idle("no interruptedBy: Stop() returns to the idle row at once")
    eq(W.run.burst._groups[1].plays, 0, "no lock-in for a channel")
    W.clean()
end

function T.channel_stop_with_interrupted_by_runs_the_outage()
    local W = world()
    W.channel(100, 4); W.fire("UNIT_SPELLCAST_CHANNEL_START")
    W.stepTo(100, 101)
    __unit.chan = nil
    W.fire("UNIT_SPELLCAST_CHANNEL_STOP", "pet", "X", 1, "Player-1-ABC")
    eq(W.run:GetPhase(), "intr", "interruptedBy: Interrupt()"); eq(W.panel._shown, true, "panel stays for the outage")
    W.at(102.01); W.idle("after the channel outage")
    W.clean()
end

function T.channel_stop_with_a_secret_interrupted_by_stops_quietly()
    local W = world()
    W.channel(100, 4); W.fire("UNIT_SPELLCAST_CHANNEL_START")
    W.stepTo(100, 101)
    __unit.chan = nil
    ok(pcall(W.fire, "UNIT_SPELLCAST_CHANNEL_STOP", "pet", "X", 1, __SECRET_ID), "threw on a secret interruptedBy")
    W.idle("the quiet outcome is the safer misfire")
    W.clean()
end

function T.a_cast_event_does_not_end_a_channel()
    local W = world()
    W.channel(100, 4); W.fire("UNIT_SPELLCAST_CHANNEL_START")
    W.fire("UNIT_SPELLCAST_STOP", "pet", "C1")
    W.fire("UNIT_SPELLCAST_INTERRUPTED", "pet", "C1")
    eq(W.run:GetPhase(), "cast", "cast events leave a channel alone")
    W.clean()
end

function T.channel_stop_does_not_end_a_cast()
    local W = world()
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    W.fire("UNIT_SPELLCAST_CHANNEL_STOP", "pet", "C1", 1, nil)
    eq(W.run:GetPhase(), "cast", "CHANNEL_STOP leaves a cast alone")
    W.clean()
end

function T.events_during_the_hold_are_ignored()
    local W = world()
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    W.stepTo(100, 102.5)
    W.fire("UNIT_SPELLCAST_STOP", "pet", "C1")
    eq(W.run:GetPhase(), "hold")
    __unit.cast = nil
    W.stepTo(102.5, 103)
    W.fire("UNIT_SPELLCAST_STOP", "pet", "C1")
    W.fire("UNIT_SPELLCAST_FAILED", "pet", "C1")
    W.fire("UNIT_SPELLCAST_INTERRUPTED", "pet", "C1")
    W.fire("UNIT_SPELLCAST_START")                 -- a nil refresh: no cast info any more
    W.fire("UNIT_SPELLCAST_DELAYED")
    W.fire("UNIT_PET", "party1")
    eq(W.run:GetPhase(), "hold", "still holding"); eq(W.run.burst._groups[1].plays, 1, "one lock-in only")
    eq(W.panel._shown, true)
    W.at(103.81); W.idle("after the hold and fade")
    W.clean()
end

function T.a_new_cast_during_the_hold_takes_over()
    local W = world()
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    W.stepTo(100, 102.5)
    W.fire("UNIT_SPELLCAST_STOP", "pet", "C1")
    W.cast("C2", 103, CAST); W.fire("UNIT_SPELLCAST_START")
    eq(W.run:GetPhase(), "cast", "the next cast replaces the hold"); eq(W.panel._shown, true)
    eq(W.run:MatchesCast("C2"), true, "castID captured at start")
    W.clean()
end

-- ---- delayed / channel update -----------------------------------------------

function T.delayed_updates_the_times_without_re_igniting_lit_segments()
    local W = world()
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    W.stepTo(100, 101.6)
    local before = litSinces(W.run)
    local lit = 0
    for i = 1, W.run.count do if before[i] ~= false then lit = lit + 1 end end
    ok(lit >= 4, "a few of the eight segments are already lit")
    local first = W.run.segs[1]
    local calls = first.lit._vcCalls
    __unit.cast.endMS = (100 + CAST + 0.5) * 1000      -- pushed back half a second
    W.fire("UNIT_SPELLCAST_DELAYED", "pet", "C1")
    near(W.run.dur, CAST + 0.5, 1e-9, "the engine got the new length")
    eq(W.run:GetPhase(), "cast"); eq(W.run:MatchesCast("C1"), true, "castID kept")
    local after = litSinces(W.run)
    for i = 1, W.run.count do
        if before[i] ~= false and after[i] ~= false then eq(after[i], before[i], "segment " .. i .. " keeps its ignite clock") end
    end
    eq(first.lit._vcCalls, calls, "a settled segment is not repainted by the re-time")
    W.clean()
end

function T.channel_update_re_times_a_running_channel()
    local W = world()
    W.channel(100, 4); W.fire("UNIT_SPELLCAST_CHANNEL_START")
    W.stepTo(100, 101)
    __unit.chan.endMS = 106 * 1000
    W.fire("UNIT_SPELLCAST_CHANNEL_UPDATE", "pet", "X")
    near(W.run.dur, 6, 1e-9, "channel length updated"); eq(W.run:GetPhase(), "cast")
    W.clean()
end

-- ---- secrets ----------------------------------------------------------------

function T.strip_tile_follows_the_engine_pitch_and_a_rescale()
    -- 1080p at effective scale 0.64: one pixel is 1.111 units; the strip follows the engine's own
    -- whole pixel pitch (run.pitch), not a recomputation from the mockup's 12.
    local W = world(function() __physH = 1080; __setUIScale(0.64) end)
    local tile = FS.Theme.CAST_CHEVRON_STRIP_TILE_W
    ok(W.run.pitch > 0, "the engine exposes its pitch")
    near(W.run.pitch, W.run.segs[2].x0 - W.run.segs[1].x0, 1e-9, "run.pitch is the pitch the segments sit at")
    near(W.strip._scale, 2 * W.run.pitch / tile, 1e-9, "strip period is two engine pitches")
    -- A rescale re-lays out the engine (its own SetScale hook on UIParent); the strip follows.
    local before = W.strip._scale
    UIParent:SetScale(0.9)
    near(W.strip._scale, 2 * W.run.pitch / tile, 1e-9, "strip period follows the rescale")
    ok(W.strip._scale ~= before, "the scale actually changed")
end

function T.secret_times_fall_back_to_the_engine_timed_strip()
    local W = world()
    __now = 100
    __unit.cast = { name = "Firebolt", tex = "icon", startMS = __SECRET, endMS = __SECRET, castID = __SECRET_ID,
        notInt = false, remaining = 1.5, elapsed = 0.5, total = 2.0 }
    local okf, err = pcall(W.fire, "UNIT_SPELLCAST_START")
    ok(okf, "no throw on secret times: " .. tostring(err))
    W.clean()
    eq(W.run:IsBusy(), false, "the engine took no part")
    eq(W.panel._shown, true, "panel shown for the fallback")
    ok(W.strip, "a strip bar exists")
    eq(W.strip._shown, true, "strip bar shown")
    ok(W.strip._timer ~= nil, "SetTimerDuration got the duration object")
    eq(W.strip._fill._texture, FS.Theme.CAST_CHEVRON_STRIP_TEXTURE, "tiled chevron strip texture")
    eq(W.strip._fill._horizTile, true, "tiled horizontally")
    -- Two chevrons per 32 wide tile: scale so the period is two engine pitches (20 at the pet pitch 10).
    near(W.strip._scale, 2 * __mock.PITCH / 32, 0.02, "tile scale matches the engine pitch")
    W.ticker._scripts.OnUpdate(W.ticker, 0.2)
    eq(W.timerText._text, "0.5 / 2.0", "the timer still reads the duration object")
    -- A verdict ends it.
    __unit.cast = nil
    local ok2, err2 = pcall(W.fire, "UNIT_SPELLCAST_STOP", "pet", __SECRET_ID)
    ok(ok2, "secret castID on STOP threw: " .. tostring(err2))
    W.idle("the strip gives way to the idle row when the cast is gone")
    -- A later plain cast uses the engine again and keeps the strip away.
    W.cast("C2", 110, CAST); W.fire("UNIT_SPELLCAST_START")
    eq(W.run:IsBusy(), true); eq(W.strip._shown, false)
    W.clean()
end

function T.secret_castid_interrupted_still_interrupts()
    -- INTERRUPTED only fires for a cast that started, so an unknowable id still interrupts.
    local W = world()
    W.cast(__SECRET_ID); W.fire("UNIT_SPELLCAST_START")
    W.stepTo(100, 101)
    local okf, err = pcall(W.fire, "UNIT_SPELLCAST_INTERRUPTED", "pet", __SECRET_ID)
    ok(okf, "threw: " .. tostring(err)); eq(W.run:GetPhase(), "intr")
    W.clean()
end

function T.secret_castid_failed_waits_for_a_plain_nil_cast()
    local W = world()
    W.cast(__SECRET_ID); W.fire("UNIT_SPELLCAST_START")
    W.stepTo(100, 101)
    ok(pcall(W.fire, "UNIT_SPELLCAST_FAILED", "pet", __SECRET_ID))
    eq(W.run:GetPhase(), "cast", "FAILED with an unknowable id is ignored while the cast is alive")
    __unit.cast = nil
    ok(pcall(W.fire, "UNIT_SPELLCAST_FAILED", "pet", __SECRET_ID))
    eq(W.run:GetPhase(), "intr", "FAILED once UnitCastingInfo returns a plain nil name")
    W.clean()
end

function T.secret_castid_stop_only_succeeds_at_completion()
    local W = world()
    W.cast(__SECRET_ID); W.fire("UNIT_SPELLCAST_START")
    W.stepTo(100, 101)
    ok(pcall(W.fire, "UNIT_SPELLCAST_STOP", "pet", __SECRET_ID))
    eq(W.run:GetPhase(), "cast", "an unknowable STOP mid-cast does not lock in")
    W.stepTo(101, 102.5)
    ok(pcall(W.fire, "UNIT_SPELLCAST_STOP", "pet", __SECRET_ID))
    eq(W.run:GetPhase(), "hold", "an unknowable STOP at completion succeeds")
    W.clean()
end

-- ---- lifecycle --------------------------------------------------------------

function T.unit_pet_for_the_owner_resets_a_running_cast()
    local W = world()
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    W.stepTo(100, 101)
    __unit.cast = nil
    W.fire("UNIT_PET", "party1")
    eq(W.run:IsBusy(), true, "another unit's pet changing is none of our business")
    W.fire("UNIT_PET", "player")
    W.idle("the owner's pet changed")
    W.clean()
end

function T.a_pet_already_casting_at_login_shows_the_bar()
    local W = world(function()
        __now = 100
        __unit.cast = { name = "Firebolt", tex = "icon", startMS = 99 * 1000, endMS = 101.5 * 1000, castID = "C1", notInt = false }
    end)
    eq(W.run:IsBusy(), true); eq(W.panel._shown, true)
    W.clean()
end

function T.a_stale_cast_is_not_shown()
    local W = world()
    __now = 100
    __unit.cast = { name = "Firebolt", tex = "icon", startMS = 80 * 1000, endMS = 82.5 * 1000, castID = "C1", notInt = false }
    W.fire("UNIT_SPELLCAST_START")
    W.idle("a stale cast shows nothing")
    W.clean()
end

-- ---- gates the review found untested (mutation: removing either let a check pass) ----

function T.a_secret_castid_stop_during_the_hold_does_not_kill_it()
    -- Without the phase gate in HandleEvent, an unknowable STOP in the hold reaches
    -- HandleRunVerdict: matches == nil and the cast is plainly gone -> QuietStop.
    local W = world()
    W.cast(__SECRET_ID); W.fire("UNIT_SPELLCAST_START")
    W.stepTo(100, 102.5)
    ok(pcall(W.fire, "UNIT_SPELLCAST_STOP", "pet", __SECRET_ID))
    eq(W.run:GetPhase(), "hold", "an unknowable STOP at completion succeeds")
    __unit.cast = nil
    ok(pcall(W.fire, "UNIT_SPELLCAST_STOP", "pet", __SECRET_ID))
    eq(W.run:GetPhase(), "hold", "a second unknowable STOP must not QuietStop the hold")
    eq(W.panel._shown, true); eq(W.run.burst._groups[1].plays, 1, "one lock-in only")
    W.stepTo(102.5, 103.6)
    eq(W.run:GetPhase(), "fade")
    W.clean()
end

function T.delayed_during_the_hold_leaves_it_intact()
    -- Without the finishing guard in RetimeCast, a refresh that still finds a cast
    -- restarts the timer text under the hold (and a cast/channel flip would BeginCast).
    local W = world()
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    W.stepTo(100, 102.5)
    W.fire("UNIT_SPELLCAST_STOP", "pet", "C1")
    eq(W.run:GetPhase(), "hold")
    eq(W.timerText._text, "", "the verdict blanked the timer")
    ok(__unit.cast ~= nil, "UnitCastingInfo still reports a cast (the case under test)")
    W.fire("UNIT_SPELLCAST_DELAYED", "pet", "C1")
    eq(W.run:GetPhase(), "hold", "DELAYED leaves the hold alone")
    eq(W.timerText._text, "", "and does not restart the timer under it")
    eq(W.ticker._shown, false, "the timer ticker stays off")
    eq(W.run.burst._groups[1].plays, 1, "one lock-in only")
    W.channel(102.6, 4)
    W.fire("UNIT_SPELLCAST_CHANNEL_UPDATE", "pet", "X")
    eq(W.run:GetPhase(), "hold", "a cast -> channel flip mid hold does not BeginCast over it")
    W.clean()
end

-- ---- idle row ---------------------------------------------------------------

function T.idle_to_cast_to_finish_to_idle()
    local W = world()
    W.idle("start")
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    eq(W.run:GetPhase(), "cast"); eq(W.panel._shown, true)
    near(W.run.segs[1].dim._vc[4], 0.2, 1e-9, "a cast uses the engine's own unlit look")
    W.stepTo(100, 101.2)
    local litCount = 0
    for i = 1, W.run.count do
        if W.run.segs[i].litSince ~= false then litCount = litCount + 1 end
    end
    ok(litCount >= 3 and litCount < W.run.count, "segments ignite as the caret passes them from idle")
    eq(W.run.segs[1].lit._shown, true, "the first chevron is lit")
    eq(W.run.segs[W.run.count].lit._shown, false, "the last is not yet")
    W.stepTo(101.2, 102.5)
    __unit.cast = nil
    W.fire("UNIT_SPELLCAST_STOP", "pet", "C1")
    eq(W.run:GetPhase(), "hold"); eq(W.panel._shown, true, "the hold is not hidden")
    W.stepTo(102.5, 103.6); eq(W.run:GetPhase(), "fade")
    W.at(103.81)
    W.idle("finish returns to the idle row, not to nothing")
    -- And the next cast ignites again from the idle row.
    W.cast("C2", 110, CAST); W.fire("UNIT_SPELLCAST_START")
    W.stepTo(110, 111)
    eq(W.run:GetPhase(), "cast"); eq(W.run.segs[1].lit._shown, true, "ignites again after the idle row")
    near(W.run.segs[W.run.count].dim._vc[4], 0.2, 1e-9)
    W.clean()
end

function T.an_interrupted_cast_also_returns_to_the_idle_row_at_full_alpha()
    local W = world()
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    W.stepTo(100, 101)
    __unit.cast = nil
    W.fire("UNIT_SPELLCAST_INTERRUPTED", "pet", "C1")
    W.at(101.9)
    ok(W.panel._alpha < 1, "the outage dimmed the panel")
    W.at(102.01)
    W.idle("outage over")
    W.clean()
end

-- ---- PLAYER_ENTERING_WORLD reset ------------------------------------------

function T.player_entering_world_is_registered_and_resets_the_engine_path()
    local W = world()
    eq(W.events._events.PLAYER_ENTERING_WORLD, true, "PLAYER_ENTERING_WORLD is registered")
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    W.stepTo(100, 101)
    __unit.cast = nil
    W.fire("PLAYER_ENTERING_WORLD", false, false)
    W.idle("after a loading screen")
    W.clean()
end

function T.player_entering_world_resets_a_stranded_strip()
    -- A verdict dropped across a loading screen must not leave the full strip showing.
    local W = world()
    __now = 100
    __unit.cast = { name = "Firebolt", tex = "icon", startMS = __SECRET, endMS = __SECRET, castID = __SECRET_ID,
        notInt = false, remaining = 1.5, elapsed = 0.5, total = 2.0 }
    W.fire("UNIT_SPELLCAST_START")
    eq(W.strip._shown, true, "strip up")
    __unit.cast = nil                                   -- the verdict never arrived
    W.fire("PLAYER_ENTERING_WORLD", true, false)
    W.idle("strip reset by the loading screen")
    W.clean()
end

function T.player_entering_world_with_the_pet_still_casting_resumes_it()
    local W = world()
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    W.stepTo(100, 101)
    W.fire("PLAYER_ENTERING_WORLD", false, false)
    eq(W.run:GetPhase(), "cast", "the pet is still mid cast: the bar picks it back up")
    W.clean()
end

-- ---- UNIT_PET keeps the hold for the same pet -------------------------------

function T.unit_pet_with_the_same_guid_keeps_the_hold()
    local W = world()
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    W.stepTo(100, 102.5)
    W.fire("UNIT_SPELLCAST_STOP", "pet", "C1")
    eq(W.run:GetPhase(), "hold")
    __unit.cast = nil
    W.fire("UNIT_PET", "player")
    eq(W.run:GetPhase(), "hold", "same pet GUID: the hold survives")
    W.stepTo(102.5, 103.6); eq(W.run:GetPhase(), "fade", "and the lock-in plays out")
    eq(W.run.burst._groups[1].plays, 1, "one lock-in only")
    W.at(103.81); W.idle("finished normally")
    W.clean()
end

-- Enters the hold for pet "Pet-0-1-A", runs `change` (the world after the cast), then UNIT_PET.
local function unit_pet_mid_hold(change)
    local W = world()
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    W.stepTo(100, 102.5)
    W.fire("UNIT_SPELLCAST_STOP", "pet", "C1")
    eq(W.run:GetPhase(), "hold")
    __unit.cast = nil
    change()
    ok(pcall(W.fire, "UNIT_PET", "player"), "UNIT_PET threw")
    return W
end

function T.unit_pet_with_a_different_guid_aborts_the_hold()
    unit_pet_mid_hold(function() __unit.guid = "Pet-0-1-B" end).idle("a different pet")
end

function T.unit_pet_with_the_pet_gone_aborts_the_hold()
    unit_pet_mid_hold(function() __unit.exists = false end).idle("a dismissed pet")
end

function T.unit_pet_with_a_secret_guid_now_aborts_the_hold()
    unit_pet_mid_hold(function() __unit.guid = __SECRET_ID end).idle("cannot tell")
end

function T.unit_pet_with_a_secret_cast_guid_aborts_the_hold()
    local W = world()
    __unit.guid = __SECRET_ID
    W.cast("C1"); W.fire("UNIT_SPELLCAST_START")
    W.stepTo(100, 102.5)
    W.fire("UNIT_SPELLCAST_STOP", "pet", "C1")
    eq(W.run:GetPhase(), "hold")
    __unit.cast = nil
    ok(pcall(W.fire, "UNIT_PET", "player"))
    W.idle("a secret GUID at cast start keeps the old abort")
end

-- ---- the timer shrinks while BOTH numbers of the readout are 10 or more (Parker: "if both casts are 10s
-- or more... temporarily decrease the font size") -----------------------------------------------------

-- The timer box is NAME_MAX_W + RUN_GAP wide (48 px) and the readout is right justified with no wrap, so
-- "10.0 / 12.5" (11 characters, about 52 px at 8.5 pt) would clip. The first number (elapsed for a cast,
-- remaining for a channel) is never above the total, so "both at least 10" is "the first at least 10",
-- and the cutoff is 9.95 because "%.1f" prints 9.95 and up as "10.0". Plain first number: the same
-- FontString is given the small size (ApplyMono) while it is, and the state flips mid cast. Secret first
-- number: nothing is compared; two FontStrings take the same text and the engine drives their alphas
-- from a Step curve at 9.95 evaluated on the duration method of that number.

local function tick(W, dt) W.ticker._scripts.OnUpdate(W.ticker, dt or 0.2) end
local SMALL, FROM, TIMERFS = __mock.TIMERSMALL, __mock.TIMERSMALLFROM, __mock.TIMERFS
-- A curve result as a plain number, whether the mock handed back a secret object or a number.
local function real(a) local v = __secretAlphas[a]; if v ~= nil then return v end return a end
local function alphas(W) return real(W.timerText._alpha), real(W.timerSmall._alpha) end
local function stop_at_once(W, id)
    __unit.cast = nil
    W.fire("UNIT_SPELLCAST_STOP", "pet", id)
    W.at(__now + 4)
end

-- A cast whose timing is secret: the engine refuses it, the strip bar runs, and the duration object
-- answers its readers with the secret sentinel (a comparison on it throws). `extra` sets the mock's
-- flags and times; the default is 11 s in, where the engine should pick the small layer.
local function secret_cast(W, total, extra)
    __now = 100
    local c = { name = "Firebolt", tex = "icon", startMS = __SECRET, endMS = __SECRET, castID = __SECRET_ID,
        notInt = false, secretDur = true, total = total, elapsed = 11 }
    for k, v in pairs(extra or {}) do c[k] = v end
    c.remaining = c.remaining or (total - c.elapsed)
    __unit.cast = c
    __unit.chan = nil
    W.fire("UNIT_SPELLCAST_START")
end
local function secret_channel(W, total, extra)
    __now = 100
    local c = { name = "Drain", tex = "icon", startMS = __SECRET, endMS = __SECRET, notInt = false,
        secretDur = true, total = total, remaining = 11 }
    for k, v in pairs(extra or {}) do c[k] = v end
    c.elapsed = c.elapsed or (total - c.remaining)
    __unit.chan = c
    __unit.cast = nil
    W.fire("UNIT_SPELLCAST_CHANNEL_START")
end

function T.the_small_timer_font_exists_and_the_cutoff_is_where_one_decimal_prints_10_0()
    local W = world()
    W.clean()
    ok(W.timerSmall, "a second timer FontString wears the small size")
    ok(SMALL < TIMERFS, "the small size is under the mockup's 8.5")
    eq(FROM, 9.95, "the cutoff is 9.95, not 10")
    eq(string.format("%.1f", FROM + 1e-9), "10.0", "from the cutoff on, %.1f prints the 11 character readout")
    eq(string.format("%.1f", FROM - 0.01), "9.9", "and just under it still prints the 10 character one")
    eq(W.timerSmall._justifyH, "RIGHT"); eq(W.timerSmall._wordWrap, false)
    eq(W.timerSmall._text, "", "blank at idle")
    near(W.timerSmall._alpha or 0, 0, 1e-9, "and invisible at idle")
end

function T.a_cast_wears_the_small_font_only_from_9_95_s_elapsed()
    local W = world()
    W.cast("C1", 100, 12.5); W.fire("UNIT_SPELLCAST_START")
    eq(W.timerText._fontSize, TIMERFS, "a long cast starts at 8.5: nothing has elapsed")
    eq(W.timerText._text, "0.0 / 12.5")
    __unit.cast.elapsed = FROM - 0.01; tick(W)
    eq(W.timerText._text, "9.9 / 12.5"); eq(W.timerText._fontSize, TIMERFS, "9.94 s in")
    __unit.cast.elapsed = FROM; tick(W)
    eq(W.timerText._fontSize, SMALL, "9.95 s in: the readout is about to print 10.0")
    __unit.cast.elapsed = 9.96; tick(W)
    eq(W.timerText._text, "10.0 / 12.5"); eq(W.timerText._fontSize, SMALL)
    __unit.cast.elapsed = 12.5; tick(W)
    eq(W.timerText._text, "12.5 / 12.5"); eq(W.timerText._fontSize, SMALL, "and small to the end")
    near(W.timerText._alpha or 1, 1, 1e-9, "fully visible")
    eq(W.timerSmall._text, "", "the second FontString is not used on the plain path")
    eq(__evalCalls, 0, "a plain number is compared, not curved")
    -- A cast whose whole readout stays under the cutoff never shrinks.
    stop_at_once(W, "C1")
    W.cast("C2", 110, 9); W.fire("UNIT_SPELLCAST_START")
    __unit.cast.elapsed = 9; tick(W)
    eq(W.timerText._text, "9.0 / 9.0"); eq(W.timerText._fontSize, TIMERFS, "a 9 s cast reads at 8.5 to the end")
    W.clean()
end

function T.a_long_channel_counts_out_of_the_small_font()
    local W = world()
    W.channel(100, 12); W.fire("UNIT_SPELLCAST_CHANNEL_START")
    eq(W.timerText._fontSize, SMALL, "12 s left of 12: small from the first frame")
    __now = 102; tick(W)
    eq(W.timerText._text, "10.0 / 12.0", "remaining over total"); eq(W.timerText._fontSize, SMALL)
    __now = 102.1; tick(W)
    eq(W.timerText._text, "9.9 / 12.0"); eq(W.timerText._fontSize, TIMERFS, "under 9.95 s left the 8.5 returns, mid channel")
    W.clean()
end

-- The first number can jump between ticks (no event, no new object): the tick alone follows it both
-- ways, and every way a cast ends puts 8.5 back.
function T.the_font_follows_the_first_number_both_ways_and_every_stop_restores_8_5()
    local W = world()
    W.cast("C1", 100, 12.5); W.fire("UNIT_SPELLCAST_START")
    __unit.cast.elapsed = 11; tick(W)
    eq(W.timerText._fontSize, SMALL, "the tick alone shrinks it"); eq(W.timerText._text, "11.0 / 12.5")
    __unit.cast.elapsed = 5; tick(W)
    eq(W.timerText._fontSize, TIMERFS, "and the tick alone restores it"); eq(W.timerText._text, "5.0 / 12.5")
    __unit.cast.elapsed = 11; tick(W)
    eq(W.timerText._fontSize, SMALL)
    __now = 101
    W.fire("UNIT_SPELLCAST_INTERRUPTED", "pet", "C1")
    eq(W.timerText._text, "", "the verdict blanked the timer")
    eq(W.timerText._fontSize, TIMERFS, "and put the font back")
    W.at(104.4)
    W.cast("C2", 110, 12.5); W.fire("UNIT_SPELLCAST_START")
    __unit.cast.elapsed = 11; tick(W)
    eq(W.timerText._fontSize, SMALL)
    __unit.cast = nil
    W.fire("UNIT_PET", "player")
    eq(W.timerText._fontSize, TIMERFS, "an abandoned cast too")
    W.cast("C3", 120, 12.5); W.fire("UNIT_SPELLCAST_START")
    __unit.cast.elapsed = 11; tick(W)
    eq(W.timerText._fontSize, SMALL)
    stop_at_once(W, "C3")
    eq(W.timerText._fontSize, TIMERFS, "a completed cast, once it is over")
    W.idle("after the long cast")
    W.cast("C4", 130, 2.5); W.fire("UNIT_SPELLCAST_START"); tick(W)
    eq(W.timerText._fontSize, TIMERFS, "the next short cast reads at 8.5")
    W.clean()
end

function T.the_font_is_reapplied_only_when_the_state_flips()
    local W = world()
    local base, smallBase = W.timerText._fontApplies, W.timerSmall._fontApplies
    W.cast("C1", 100, 2.5); W.fire("UNIT_SPELLCAST_START")
    for i = 1, 8 do __now = 100 + i * 0.25; tick(W) end
    eq(W.timerText._fontApplies, base, "a short cast never touches the font")
    stop_at_once(W, "C1")
    eq(W.timerText._fontApplies, base, "nor does its stop")
    W.cast("C2", 120, 12.5); W.fire("UNIT_SPELLCAST_START")
    for i = 1, 36 do __now = 120 + i * 0.25; tick(W) end
    eq(W.timerText._fontApplies, base, "nine seconds into a long cast it is still at 8.5, nothing applied")
    __now = 130; tick(W)
    local atFlip = W.timerText._fontApplies
    eq(atFlip, base + 1, "crossing the cutoff applies the small font once")
    for i = 1, 40 do __now = 130 + i * 0.05; tick(W) end
    eq(W.timerText._fontApplies, atFlip, "forty ticks of the same state re-apply nothing")
    eq(W.timerSmall._fontApplies, smallBase, "the second FontString keeps the font it got at build")
    stop_at_once(W, "C2")
    eq(W.timerText._fontApplies, atFlip + 1, "the stop restores 8.5 with one apply")
    W.clean()
end

-- The whole point: at 8.5 pt the widest long readout overflows the 48 px box, at the small size it fits,
-- at every scale (a linear glyph advance: real pixel snapping at small scales is not modelled).
local fit_variants = { "1", "0.8333", "0.64" }
function T.a_99_9_over_99_9_readout_fits_the_timer_box_at_every_scale(variant)
    local s = tonumber(variant)
    local m = __mock
    if s == 1 then
        local w = m.NAMEMAXW + m.GAP
        ok(11 * TIMERFS * m.ADV > w, "at 8.5 pt \"99.9 / 99.9\" (" .. 11 * TIMERFS * m.ADV .. ") overflows " .. w)
        ok(11 * SMALL * m.ADV <= w, "the small size fits it: " .. 11 * SMALL * m.ADV)
        ok(11 * (SMALL + 0.5) * m.ADV > w, "one half point more would not fit, so the shrink is the smallest that works")
    end
    local W = world(function() __layoutScale = s end)
    W.cast("C1", 100, 99.9); W.fire("UNIT_SPELLCAST_START")
    __unit.cast.elapsed = 99.9
    tick(W)
    eq(W.timerText._text, "99.9 / 99.9")
    eq(W.timerText._fontSize, SMALL * s, "small size at scale " .. s)
    local width = W.timerText:GetStringWidth()
    ok(width <= W.timerText._w + 1e-9, "\"99.9 / 99.9\" is " .. width .. " px in a " .. W.timerText._w .. " px box at scale " .. s)
    W.clean()
end

function T.a_rescale_keeps_the_state_and_seats_both_timer_fonts()
    local W = world()
    W.cast("C1", 100, 12.5); W.fire("UNIT_SPELLCAST_START")
    __unit.cast.elapsed = 11; tick(W)
    __layoutScale = 0.64; __rescale()
    eq(W.timerText._fontSize, SMALL * 0.64, "the small state survives the rescale")
    eq(W.timerSmall._fontSize, SMALL * 0.64)
    near(W.timerText._w, (__mock.NAMEMAXW + __mock.GAP) * 0.64, 1e-9)
    near(W.timerSmall._w, W.timerText._w, 1e-9, "the same box")
    local x1, y1 = pt(W.timerText, "RIGHT"); local x2, y2 = pt(W.timerSmall, "RIGHT")
    near(x1, x2, 1e-9, "same right edge"); near(y1, y2, 1e-9, "same row")
    stop_at_once(W, "C1")
    eq(W.timerText._fontSize, TIMERFS * 0.64, "and 8.5 returns at the new scale")
    W.clean()
end

-- ---- plain first number, secret total ----------------------------------------

-- The decision is made on the first number: a secret total beside a plain elapsed time neither
-- compares nor curves anything, and the font follows the elapsed time.
function T.a_plain_first_number_decides_even_when_the_total_is_secret()
    local W = world()
    W.cast("C1", 100, 12.5); __unit.cast.secretTotal = true
    W.fire("UNIT_SPELLCAST_START")
    tick(W)
    ok(W.timerText._secretText, "the secret total reached SetFormattedText")
    eq(W.timerText._fontSize, TIMERFS, "0.5 s in: 8.5, although the total is secret")
    __unit.cast.elapsed = 11; tick(W)
    eq(W.timerText._fontSize, SMALL, "11 s in: small")
    eq(W.timerSmall._text, "", "the second FontString is not used"); eq(W.timerText._alpha, 1)
    eq(__evalCalls, 0, "no engine curve for a plain first number")
    eq(#__degrades, 0, "nothing degraded")
    W.clean()
end

-- ---- secret first number: never compared, crossfaded by the engine ------------

function T.a_secret_first_number_is_never_compared_and_both_layers_get_the_same_arguments()
    local W = world()
    -- The first number secret, the total a plain 12.5: the two arguments are different values, so a
    -- swap between the FontStrings shows.
    local okf, err = pcall(secret_cast, W, 12.5, { plainTotal = true })
    ok(okf, "no throw on a secret first number: " .. tostring(err))
    tick(W)
    W.clean()
    ok(W.timerText._secretText, "the secret readout reached SetFormattedText")
    ok(W.timerText._text ~= "", "the timer was not disabled by a throw (a comparison on the sentinel would latch it)")
    eq(W.timerSmall._text, W.timerText._text, "the second FontString holds the same readout")
    local a, b = W.timerText._fmtArgs, W.timerSmall._fmtArgs
    ok(a and b, "both FontStrings were written through SetFormattedText")
    eq(b.fmt, a.fmt, "the same format"); eq(b.n, a.n); eq(a.n, 2)
    for i = 1, a.n do ok(rawequal(b[i], a[i]), "argument " .. i .. " is the same value in both FontStrings") end
    ok(rawequal(a[1], __SECRET), "the first argument is the secret first number"); eq(a[2], 12.5, "the second the plain total")
    eq(#__degrades, 0, "nothing degraded")
end

-- Whether the engine's answer is a secret object or a plain number is not documented
-- (SecretWhenCurveSecret): the code works the same either way.
local crossfade_variants = { "secret_result", "plain_result" }
function T.a_secret_first_number_crossfades_through_an_engine_step_curve(variant)
    local W = world()
    secret_cast(W, 12.5, { elapsed = 0.5, evaluatePlain = (variant == "plain_result") })
    tick(W)
    local normal, small = alphas(W)
    eq(normal, 1, "0.5 s in the 8.5 layer is up, although the total is 12.5"); eq(small, 0)
    __unit.cast.elapsed = 11; tick(W)
    normal, small = alphas(W)
    eq(normal, 0, "11 s in the 8.5 layer is faded out"); eq(small, 1, "and the small one is up")
    ok(__evalCalls >= 4, "the engine evaluated the first number against the curves")
    if variant == "secret_result" then
        ok(__secretAlphas[W.timerText._alpha] ~= nil and __secretAlphas[W.timerSmall._alpha] ~= nil,
            "the setters got the engine's own result objects")
    end
    eq(W.timerText._fontSize, TIMERFS, "the first layer stays 8.5 pt on the secret path")
    eq(W.timerSmall._fontSize, SMALL, "the second is the small size")
    __unit.cast.elapsed = 5; tick(W)
    normal, small = alphas(W)
    eq(normal, 1, "and back both ways"); eq(small, 0)
    eq(#__degrades, 0, "nothing degraded")
    W.clean()
end

-- The curves are read off the engine calls (the mock logs each one). The 8.5 layer's curve is
-- evaluated first, on the duration method that matches the first number shown.
local curve_variants = { "cast", "channel" }
function T.the_curves_are_a_step_at_9_95_on_the_duration_method_of_the_first_number(variant)
    local W = world()
    if variant == "cast" then secret_cast(W, 12.5) else secret_channel(W, 12) end
    tick(W)
    local want = (variant == "cast") and "elapsed" or "remaining"
    ok(#__evalLog >= 2, "both curves were evaluated: " .. #__evalLog)
    for _, e in ipairs(__evalLog) do eq(e[1], want, "evaluated on the " .. want .. " duration, never another") end
    local a, b = __evalLog[1][2], __evalLog[2][2]
    ok(a ~= b, "two curves")
    eq(a.curveType, Enum.LuaCurveType.Step, "a Step curve"); eq(b.curveType, Enum.LuaCurveType.Step)
    local at = __stepEvaluate
    eq(at(a, FROM - 0.01), 1, "the 8.5 layer is up under the cutoff"); eq(at(a, FROM), 0, "and gone from it")
    eq(at(b, FROM - 0.01), 0, "the small layer is hidden under the cutoff"); eq(at(b, FROM), 1, "and up from it")
    eq(at(a, 0), 1, "from the first instant"); eq(at(b, 0), 0)
    eq(at(a, 99.9), 0, "and far above"); eq(at(b, 99.9), 1)
    eq(a.points[2][1], FROM, "the step sits at the cutoff constant")
end

function T.the_crossfade_resets_at_the_stop_and_a_plain_cast_afterwards_is_unaffected()
    local W = world()
    secret_cast(W, 12.5)
    tick(W)
    local normal, small = alphas(W)
    eq(normal, 0); eq(small, 1)
    __unit.cast = nil
    W.fire("UNIT_SPELLCAST_STOP", "pet", __SECRET_ID)
    W.idle("the strip gives way to the idle row")
    eq(W.timerText._alpha, 1, "the 8.5 layer is back at a plain 1")
    eq(W.timerSmall._alpha, 0, "the small layer is hidden")
    eq(W.timerSmall._text, "", "and blank")
    eq(W.timerText._fontSize, TIMERFS)
    local before = __evalCalls
    W.cast("C2", 110, 12.5); W.fire("UNIT_SPELLCAST_START")
    __unit.cast.elapsed = 11; tick(W)
    eq(W.timerText._alpha, 1, "a plain cast does not fade")
    eq(W.timerSmall._alpha, 0)
    eq(W.timerText._fontSize, SMALL, "it shrinks the single FontString instead")
    eq(__evalCalls, before, "and asks the engine nothing")
    W.clean()
end

-- A long plain cast whose timing turns secret mid cast: the single FontString must get its 8.5 back
-- (the engine's crossfade picks the layer from then on), and a return to plain leaves the layers clean.
function T.a_long_plain_cast_that_turns_secret_mid_cast_gets_its_8_5_font_back()
    local W = world()
    W.cast("C1", 100, 12.5); W.fire("UNIT_SPELLCAST_START")
    __unit.cast.elapsed = 11; tick(W)
    eq(W.timerText._fontSize, SMALL, "plain, 11 s in: small")
    __unit.cast.secretDur = true
    tick(W)
    eq(W.timerText._fontSize, TIMERFS, "secret now: the 8.5 layer is 8.5 again, not left at the small size")
    local normal, small = alphas(W)
    eq(normal, 0, "and the engine fades it out"); eq(small, 1)
    __unit.cast.secretDur = nil
    tick(W)
    eq(W.timerText._fontSize, SMALL, "plain again: small")
    eq(W.timerText._alpha, 1, "the 8.5 layer is a plain 1 again"); eq(W.timerSmall._alpha, 0)
    eq(W.timerSmall._text, "", "the small layer is blank")
    W.clean()
end

-- ---- fallbacks: 8.5 pt, clipped as before the shrink, logged once -----------------

local function curve_fallback(extra)
    local W = world()
    secret_cast(W, 12.5, extra)
    tick(W); tick(W); tick(W)
    W.clean()
    ok(W.timerText._text ~= "", "the timer text still runs")
    eq(W.timerText._fontSize, TIMERFS, "8.5 pt, clipped as before")
    eq(W.timerText._alpha, 1, "the 8.5 layer stays up")
    eq(W.timerSmall._alpha, 0, "the small layer stays down")
    eq(#__degrades, 1, "logged exactly once across three ticks")
end
-- A string is truthy and not nil, a false is not: neither is a number, and the code asks for a number.
local nonnumber_variants = { "false", "string" }
function T.a_non_number_curve_answer_falls_back_to_8_5(variant)
    if variant == "false" then curve_fallback({ evaluateReturns = false }) else curve_fallback({ evaluateReturns = "x" }) end
end
local unavailable_variants = { "missing", "throws" }
function T.an_evaluate_method_that_is_missing_or_throws_falls_back_to_8_5(variant)
    if variant == "missing" then curve_fallback({ noEvaluate = true }) else curve_fallback({ evaluateThrows = true }) end
end

-- The setters may take the first layer's result and refuse the second's: the half written fade must not
-- leave the 8.5 pt layer invisible.
function T.a_refused_set_alpha_puts_both_layers_back_to_plain_values()
    local W = world()
    local realSetAlpha = W.timerSmall.SetAlpha
    W.timerSmall.SetAlpha = function(self, a)
        if __secretAlphas[a] ~= nil then error("SetAlpha refused a secret") end
        return realSetAlpha(self, a)
    end
    secret_cast(W, 12.5)
    tick(W); tick(W)
    W.clean()
    eq(W.timerText._alpha, 1, "the 8.5 layer is back at a plain 1, not left at the engine's 0")
    eq(W.timerSmall._alpha, 0)
    eq(W.timerSmall._text, "", "the small layer is blank")
    ok(W.timerText._text ~= "", "the readout still runs")
    eq(#__degrades, 1, "logged once")
end

-- Each of these leaves the curves unbuilt at load: no Enum.LuaCurveType.Step (a Step type of nil must
-- not build a curve of some other type), no Enum, no C_CurveUtil, or a CreateCurve that throws (the
-- pcall around the build is required).
local nocurve_variants = { "no_curve_util", "no_enum", "no_step_type", "create_curve_throws" }
function T.a_client_without_a_usable_curve_api_leaves_the_secret_path_at_8_5(variant)
    local W = world(function()
        if variant == "no_curve_util" then C_CurveUtil = nil
        elseif variant == "no_enum" then Enum = nil
        elseif variant == "no_step_type" then Enum.LuaCurveType.Step = nil
        else C_CurveUtil.CreateCurve = function() error("CreateCurve refused") end end
    end)
    secret_cast(W, 12.5)
    tick(W); tick(W)
    W.clean()
    ok(W.timerText._text ~= "", "the timer runs")
    eq(W.timerText._fontSize, TIMERFS); eq(W.timerText._alpha, 1); eq(W.timerSmall._alpha, 0)
    eq(#__degrades, 0, "silently: there is nothing to refuse")
    eq(__evalCalls, 0, "and the engine is never asked")
    -- A plain cast still shrinks without the curve API.
    __unit.cast = nil; W.fire("UNIT_SPELLCAST_STOP", "pet", __SECRET_ID)
    W.cast("C2", 120, 12.5); W.fire("UNIT_SPELLCAST_START")
    __unit.cast.elapsed = 11; tick(W)
    eq(W.timerText._fontSize, SMALL, "the plain path needs no curve")
end

-- A curve result may be secret: a bare truth test or comparison on one throws, and Lua cannot trap a
-- `secret ~= nil` behaviorally, so pin the source: the two results are only type()d and handed to
-- the setters.
function T.the_curve_results_are_never_truth_tested_or_compared_in_the_source()
    local code = __pet_source:gsub("%-%-[^\n]*", "")
    local checked = 0
    for _, n in ipairs({ "normal", "small" }) do
        local bad = {
            "%f[%w_]if%s+" .. n .. "%f[^%w_]", "%f[%w_]elseif%s+" .. n .. "%f[^%w_]", "%f[%w_]while%s+" .. n .. "%f[^%w_]",
            "%f[%w_]not%s+" .. n .. "%f[^%w_]",
            "%f[%w_]" .. n .. "%s+and%f[^%w_]", "%f[%w_]and%s+" .. n .. "%f[^%w_]",
            "%f[%w_]" .. n .. "%s+or%f[^%w_]", "%f[%w_]or%s+" .. n .. "%f[^%w_]",
            "%f[%w_]" .. n .. "%s*[~=]=", "%f[%w_]" .. n .. "%s*[<>]",
            "[~=]=%s*" .. n .. "%f[^%w_]", "[<>]=?%s*" .. n .. "%f[^%w_]",
        }
        for _, pat in ipairs(bad) do
            local at = code:find(pat)
            ok(not at, "the curve result `" .. n .. "` is truth tested or compared: " .. tostring(at and code:sub(math.max(1, at - 20), at + 40)))
        end
        if code:find("type%(" .. n .. "%)") then checked = checked + 1 end
    end
    eq(checked, 2, "both curve results are checked with type()")
end

__variants = {
    a_99_9_over_99_9_readout_fits_the_timer_box_at_every_scale = fit_variants,
    a_secret_first_number_crossfades_through_an_engine_step_curve = crossfade_variants,
    the_curves_are_a_step_at_9_95_on_the_duration_method_of_the_first_number = curve_variants,
    a_non_number_curve_answer_falls_back_to_8_5 = nonnumber_variants,
    an_evaluate_method_that_is_missing_or_throws_falls_back_to_8_5 = unavailable_variants,
    a_client_without_a_usable_curve_api_leaves_the_secret_path_at_8_5 = nocurve_variants,
}

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
    # A check listed in __variants runs once per variant (a string handed to it), each on a fresh client;
    # it counts as one check and passes only when every variant does.
    variants = lua.eval("__variants")
    failed = 0
    stale_keys = 0
    # A __variants key that names no check is a typo or a deleted check: fail loudly, never skip it.
    for stale in sorted(k for k in variants.keys() if k not in names):
        stale_keys += 1
        print(f"FAIL  __variants: key {stale!r} matches no check")
    for name in names:
        listed = variants[name]
        if listed is None:
            runs = [None]
        else:
            # Lua array order, by integer key, so the run order never depends on table hashing.
            runs = [listed[k] for k in sorted(listed.keys())]
            if not runs:
                failed += 1
                print(f"FAIL  {name}: its __variants list is empty")
                continue
        bad = []
        for variant in runs:
            # A fresh client per check: a failure must not leak state into the rest.
            lua = boot()
            lua.execute(CHECKS)
            try:
                if variant is None:
                    lua.eval("__checks")[name]()
                else:
                    lua.eval("__checks")[name](variant)
            except LuaError as err:
                bad.append(f"[{variant}] {err}" if variant is not None else str(err))
        if bad:
            failed += 1
            for line in bad:
                print(f"FAIL  {name}: {line}")
        else:
            print(f"ok    {name}" + (f"  ({', '.join(runs)})" if len(runs) > 1 or runs[0] is not None else ""))
    print(f"{len(names) - failed}/{len(names)} checks passed")
    return 1 if failed or stale_keys else 0


if __name__ == "__main__":
    sys.exit(main())
