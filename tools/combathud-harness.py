#!/usr/bin/env python3
"""Runs the real CombatHud.lua headless against a mock WoW API.

CombatHud.lua is the DISPLAY layer over FS.Hud (HudSpells -> HudProfiles -> HudLogic): a spell
row, the next-cast tile, soul shard diamonds and buff reminders, seated around the Stack A cast
bars exactly where mockups/combat-hud-stack-a-2026-10-02.html puts them. FS.Hud is a mock here
(its own behaviour is pinned by hud-harness.py); the real HudSpells.lua and HudProfiles.lua are
loaded so the profiles' selfBuffs, dots and procs are the shipped data. The checks pin:

  * geometry: every unit and offset is read back out of the mockup's CSS and JS and out of
    CastBars.lua, and the frames' resolved screen rects (a small anchor solver in the mock) are
    compared with the mockup's own arithmetic, for the Stack A fallback seat and for real cast
    bar frames that sit somewhere else;
  * the spell row: one tile per row entry, dim states, cooldown text on a 10 Hz throttle, the
    cyan next ring and the gold proc ring, the row dimmed out of combat;
  * AuraContainer slots: one slot per DoT tile on a unit "target" container (HARMFUL|PLAYER,
    includeSpellIDs), built out of combat only, a container failure leaves tiles without a
    timer and logs once, the container path is given up after repeated failures, and no aura
    read API is ever touched;
  * the next tile, the shard row and the buff row (out of combat from buffsMissing, in combat
    through the occlusion trick: warning tile BEHIND an aura slot on unit "player");
  * secrets: sentinels raise on any operation and the mock pcall records every swallowed
    SECRET_OP, so a guarded-away touch still fails;
  * Subscribe / Unsubscribe, the idle cast bar calls, the slash command and its SavedVariables;
  * the mockup fidelity items: the baked 135 degree tile gradient (and its flat fallback, for a
    throwing and for a silently missing texture), the ooc style (every tile plain, no rings, no
    seconds, no slot timers) and the opener style that restores them, with the cast bars' rest
    alpha, the next tile's real keybind (every API guarded, secrets skipped, hidden when
    unresolved, no claim on the main bar key while a vehicle, override, temp shapeshift or bonus
    page is up, cached per spell, a binding event redraws only the next tile), the Hud's DoT estimate when no aura
    slot exists, the seconds corner beside a live slot, static rings, the hudpulse buff glow, the
    whole tile greyed when dim, outlined seconds, container and slot cleanup, and a no
    allocation 10 Hz tick.

The Stack A cases above run under a Gunsight-DISABLED stub (`/fsgun off`: IsEnabled false, and it
counts any OnReady wait or piece registration, which Stack A must never make). The "gunsight_*" cases
run the REAL Layout.lua and Gunsight.lua instead and pin the Gunsight view: the NEXT tile, soul shards
and buff reminder sit on FS.Gunsight.anchors.next / shards / buff with the Gunsight mockup's DESIGN px
sizes (NEXT 56, shard 10 x 18 gap 4, line art glyphs, buff 24, parsed back out of the mockup) times FS.Layout.Scale() at
scale 1.0 and 1200/1440 (and a chamfer / stroke / type check at 0.5), a rescale re-derives them in
place, the pieces `next`, `shard` and `buff` register through FS.Gunsight.OnReady (also when the HUD
enables before Gunsight is ready), the spell row, its ticker and the target DoT container are never
built, FS.CastBars and the cast bar frames are trapped so any touch fails, a shard count above four
shows four line art shard glyphs plus "+N" (the Stack A view keeps its diamonds), the buff border pulses .35 to 1 over 1.4 s, and `/fsgun off` still
yields the working Stack A view.

The mock is strict (a widget method it does not define fails as a nil call) and is NOT the real
client. Theme.lua's colour constants are read from the real file.

    python3 tools/combathud-harness.py

Exit 0 = every check passed. COMBATHUD_LUA=<path> runs another file in place of CombatHud.lua.
"""

from __future__ import annotations

import importlib.util
import os
import re
import struct
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent
COMBATHUD = Path(os.environ.get("COMBATHUD_LUA") or ADDON / "CombatHud.lua")
MOCKUP = ADDON / "mockups" / "combat-hud-stack-a-2026-10-02.html"
OFFSTATE_MOCKUP = ADDON / "mockups" / "off-state-and-bridge-2026-10-02.html"
GUNSIGHT_MOCKUP = ADDON / "mockups" / "gunsight-hud-v2-2026-10-02" / "gunsight-hud-v2-2026-10-02.html"
SHARD_GENERATOR = ADDON / "media" / "generate_hud_shard.py"
CASTBARS = ADDON / "CastBars.lua"
THEME = ADDON / "Theme.lua"
TOC = ADDON / "ForeverSynthwave.toc"

THEME_CONSTANTS = (
    "COLOR_TEXT_WHITE", "COLOR_BG", "COLOR_BORDER", "COLOR_BAR_TRACK", "COLOR_BAR_BORDER",
    "COLOR_HEALTH", "COLOR_POWER", "FONT_MONO", "FLAT_TEXTURE",
    "CHROME_CORNERS", "CUT_SIZES", "SLICE_CUT2_OUTLINE_TEXTURE", "SLICE_CUT2_GLOW_TEXTURE",
    "SLICE_CUT2_GLOW_PAD",
)
# Real Theme.lua functions the cut tiles lean on, extracted whole so the chamfer snapping and the
# baked-set paths cannot drift from the mock.
THEME_FUNCTIONS = ("SnapCut", "Cut2ButtonSet")


# ---------------------------------------------------------------------------------------
# Numbers the mockup and CastBars.lua own. Read, never retyped, so a drift fails here.
# ---------------------------------------------------------------------------------------

def _css(selector: str, prop: str) -> float:
    """First `prop: calc(N * var(--u))` of the rule whose selector is exactly `selector`."""
    src = MOCKUP.read_text(encoding="utf-8")
    block = re.search(rf"(?m)^{re.escape(selector)}\s*\{{([^}}]*)\}}", src)
    if not block:
        sys.exit(f"mockup: rule {selector!r} not found; update combathud-harness.py")
    m = re.search(rf"(?<![\w-]){re.escape(prop)}:\s*calc\(\s*(-?[\d.]+)\s*\*\s*var\(--u\)\s*\)", block.group(1))
    if not m:
        sys.exit(f"mockup: {selector!r} has no {prop}: calc(N * var(--u)); update combathud-harness.py")
    return float(m.group(1))


def _first(pattern: str, text: str, what: str) -> str:
    m = re.search(pattern, text)
    if not m:
        sys.exit(f"{what} not found; update combathud-harness.py")
    return m.group(1)


def mockup_units() -> dict:
    src = MOCKUP.read_text(encoding="utf-8")
    js = re.search(r"var HUD_ROW = (\d+), HUD_ROW_GAP = (\d+), HUD_NEXT = (\d+);", src)
    if not js:
        sys.exit("mockup: HUD_ROW / HUD_ROW_GAP / HUD_NEXT not found; update combathud-harness.py")
    stack = re.search(r"^\s*stack:\s*\{([^}]*)\}", src, re.M)
    if not stack:
        sys.exit("mockup: SIZES.stack not found; update combathud-harness.py")
    return {
        "HUD_ROW": int(js.group(1)), "HUD_ROW_GAP": int(js.group(2)), "HUD_NEXT": int(js.group(3)),
        "TAB_H": int(_first(r"tabH:\s*(\d+)", stack.group(1), "SIZES.stack.tabH")),
        "BAR_H": int(_first(r"\bH:\s*(\d+)", stack.group(1), "SIZES.stack.H")),
        "TILE": _css(".hud-ic", "width"),
        "TILE_GAP": _css(".hud-spells", "gap"),
        "NEXT_PAD": _css(".hud", "padding-left") - int(js.group(3)),
        "SHARD_GAP": _css(".hud-shards", "gap"),
        "SHARD_H_ROW": _css(".hud-shards", "height"),
        "SHARD_TOP": _css(".hud-shards", "margin-top"),
        "SHARD_W": _css(".hud-shards .shard", "width"),
        "SHARD_H": _css(".hud-shards .shard", "height"),
        "BUFF_GAP": _css(".hud-buffs", "gap"),
        "BUFF_ROW_H": _css(".hud-buffs", "height"),
        "BUFF_TOP": _css(".hud-buffs", "margin-top"),
        "BUFF": _css(".hud-buff", "width"),
        **buff_pulse(src),
    }


def buff_pulse(src: str) -> dict:
    """The .hud-buff animation: duration, the border alpha it starts from and the glow it ends at."""
    anim = _first(r"\.hud-buff \{[^}]*animation:\s*hudpulse\s+([\d.]+)s", src, ".hud-buff animation")
    frames = re.search(r"@keyframes hudpulse \{\s*from \{([^}]*)\}\s*to \{([^}]*)\}", src)
    if not frames:
        sys.exit("mockup: @keyframes hudpulse not found; update combathud-harness.py")
    start = _first(r"border-color:\s*rgba\([^)]*,\s*([\d.]+)\)", frames.group(1), "hudpulse from border-color")
    glow = _first(r"box-shadow:\s*0 0 ([\d.]+)px", frames.group(2), "hudpulse to box-shadow")
    return {"BUFF_PULSE_S": float(anim), "BUFF_PULSE_FROM": float(start), "BUFF_GLOW": float(glow)}


def shard_glyph(src: str) -> dict:
    """The mockup's SH_GLYPH: outline, facets and lit as lists of (x, y) in 0..1 box coordinates."""
    body = re.search(r"var SH_GLYPH=\{(.*?)\n\};", src, re.S)
    if not body:
        sys.exit("gunsight mockup: SH_GLYPH not found; update combathud-harness.py")
    def pts(name: str):
        hit = re.search(name + r":(\[\[.*?\]\]),?\n", body.group(1) + "\n")
        if not hit:
            sys.exit(f"gunsight mockup: SH_GLYPH.{name} not found")
        nums = [float(v) for v in re.findall(r"-?\d*\.?\d+", hit.group(1))]
        return [(nums[i], nums[i + 1]) for i in range(0, len(nums), 2)]
    facets = pts("facets")
    return {"outline": pts("outline"), "facets": [(facets[i], facets[i + 1]) for i in range(0, len(facets), 2)], "lit": pts("lit")}


def shard_generator():
    spec = importlib.util.spec_from_file_location("generate_hud_shard", SHARD_GENERATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def gunsight_units() -> dict:
    """The Gunsight mockup's own numbers for the three pieces CombatHud re-homes (drawNext, drawShards,
    drawBuff). Addon units there are scaled by U = 1/1.28 into image px, i.e. they are DESIGN px."""
    src = GUNSIGHT_MOCKUP.read_text(encoding="utf-8")
    def m(pattern: str, what: str) -> re.Match:
        hit = re.search(pattern, src)
        if not hit:
            sys.exit(f"gunsight mockup: {what} not found (pattern {pattern!r}); update combathud-harness.py")
        return hit
    nxt = int(m(r"var NXT=\{s:(\d+)\*U\}", "NXT size").group(1))
    sh = [int(v) for v in m(r"var SH_SC=(\d+),SH_W=(\d+)\*U,SH_H=(\d+)\*U,SH_G=(\d+)\*U", "shard row").groups()]
    bs = int(m(r"var bs=(\d+)\*U,u=reduce", "buff tile").group(1))
    pulse_from, pulse_span = m(r"A\(\.(\d+)\+\.(\d+)\*u\)", "buff border pulse").groups()
    seconds = float(m(r"Math\.PI\*clock/([\d.]+)", "buff pulse period").group(1))
    # Text sizes in the Gunsight mockup are CANVAS (image) px, drawn through ctx.scale(cv.width / W), so
    # design px = image px * GRID (U = 1 / GRID); only `16*U+2` (the NEXT abbreviation) is already an
    # addon unit scaled by U plus a raw image px tweak.
    grid = float(m(r"var U=1/([\d.]+);", "U scale").group(1))
    abbr_units, abbr_add = (int(v) for v in m(r"text\(NXA\[CLS\],n\.x\+n\.s/2,n\.y\+n\.s/2\+[\d.]+,(\d+)\*U\+(\d+),K\.white", "NEXT abbreviation").groups())
    glyph = shard_glyph(src)
    gen = shard_generator()
    return {
        "SHARD_FILL_ALPHA": float(m(r"shPath\(SH_GLYPH\.lit,dx,dy,true\);A\((\.\d+)\);ctx\.fillStyle=K\.violet", "shard lit fill alpha").group(1)),
        "SHARD_FACET_MIX": float(m(r"A\(1\);ctx\.strokeStyle=mix\(K\.violet,'#ffffff',(\.\d+)\);ctx\.lineWidth=LW\*\.8", "shard facet colour").group(1)),
        "SHARD_LINE_W": gen.LINE_TEX[2], "SHARD_LINE_H": gen.LINE_TEX[3],
        "SHARD_GLOW_W": gen.GLOW_TEX[2], "SHARD_GLOW_H": gen.GLOW_TEX[3],
        "GRID": grid, "ABBR_UNITS": abbr_units, "ABBR_ADD": abbr_add,
        "KEY_PX": int(m(r"textO\('3',[^,]+,[^,]+,(\d+),K\.cyan", "NEXT keybind size").group(1)),
        "LBL_PX": int(m(r"text\('NEXT',[^,]+,[^,]+,(\d+),K\.muted", "NEXT caption size").group(1)),
        "BUFF_ABBR_PX": int(m(r"text\(BFA\[CLS\]\|\|'DA',bx\+bs/2,by\+bs/2\+[\d.]+,(\d+),K\.white", "buff abbreviation size").group(1)),
        "NXT": nxt, "SH_SC": sh[0], "SH_W": sh[1], "SH_H": sh[2], "SH_G": sh[3], "BUFF": bs,
        "NXT_CUT": int(m(r"tileFill\(n\.x,n\.y,n\.s,(\d+)\*U\)", "next chamfer").group(1)),
        "BUFF_CUT": int(m(r"tileFill\(bx,by,bs,(\d+)\*U\)", "buff chamfer").group(1)),
        "PULSE_FROM": float("0." + pulse_from), "PULSE_SPAN": float("0." + pulse_span), "PULSE_S": seconds,
    }


def lua_value(v) -> str:
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k} = {lua_value(x)}" for k, x in v.items()) + "}"
    return repr(v)


def castbars_units() -> dict:
    src = CASTBARS.read_text(encoding="utf-8")
    fx = re.search(r"^local SEAT_X, SEAT_Y = (-?\d+), (-?\d+)", src, re.M)
    if not fx:
        sys.exit("CastBars.lua: SEAT_X, SEAT_Y not found; update combathud-harness.py")
    off = OFFSTATE_MOCKUP.read_text(encoding="utf-8")
    return {
        "TAB_H": int(_first(r"(?m)^local TAB_H = (\d+)", src, "CastBars.lua TAB_H")),
        "FRAME_H": int(_first(r"(?m)^local FRAME_H = (\d+)", src, "CastBars.lua FRAME_H")),
        "GAP": int(_first(r"(?m)^local GAP = (\d+)", src, "CastBars.lua GAP")),
        "SEAT_X": int(fx.group(1)), "SEAT_Y": int(fx.group(2)),
        # The cast bar gap the CastBars seat is built from is the off-state mockup's (18, the bridge
        # has left the stack). The Stack A mockup above still draws 64 and is not the gap's source.
        "OFFSTATE_GAP": int(_first(r"var GAP = (\d+);", off, "off-state mockup GAP")),
    }


def lua_table(d: dict) -> str:
    return "{" + ", ".join(f"{k} = {v!r}" for k, v in d.items()) + "}"


def _extract_theme_constant(source: str, name: str) -> str:
    match = re.search(rf"^Theme\.{name}\s*=.*$", source, re.M)
    if not match:
        sys.exit(f"Theme.{name} not found in Theme.lua; update THEME_CONSTANTS")
    return match.group(0)


def _extract_theme_function(source: str, name: str) -> str:
    match = re.search(rf"^function Theme\.{name}\(.*?^end$", source, re.M | re.S)
    if not match:
        sys.exit(f"function Theme.{name} not found in Theme.lua; update THEME_FUNCTIONS")
    return match.group(0)


def tile_cut_fraction() -> float:
    """The chamfer of hud_tile_cut2.tga as a fraction of the tile, read from its generator."""
    gen = (ADDON / "media" / "generate_hud_tile.py").read_text(encoding="utf-8")
    m = re.search(r"(?m)^CUT_FRACTION = ([0-9.]+) / ([0-9.]+)", gen)
    if not m:
        sys.exit("generate_hud_tile.py: CUT_FRACTION not found; update combathud-harness.py")
    return float(m.group(1)) / float(m.group(2))


# ---------------------------------------------------------------------------------------
# The mock
# ---------------------------------------------------------------------------------------

MOCK = r"""
__realType = type
local realType = type
local realPcall = pcall
local realTostring = tostring

-- Secret sentinels: type() still reports the pretended type, but every operation raises
-- SECRET_OP, so a forbidden touch either throws or (inside a pcall) is recorded below.
SENT = {}
local function sentinel(kind)
    local function bad(what) return function() error("SECRET_OP " .. what, 2) end end
    local s = setmetatable({}, {
        __index = bad("index"), __newindex = bad("newindex"), __call = bad("call"),
        __concat = bad("concat"), __add = bad("add"), __sub = bad("sub"), __mul = bad("mul"),
        __div = bad("div"), __mod = bad("mod"), __pow = bad("pow"), __unm = bad("unm"),
        __lt = bad("lt"), __le = bad("le"), __eq = bad("eq"), __len = bad("len"),
        __tostring = bad("tostring"),
    })
    SENT[s] = kind
    return s
end
SN, SB, SS = sentinel("number"), sentinel("boolean"), sentinel("string")
function type(v)
    local k = SENT[v]
    if k then return k end
    return realType(v)
end
function issecretvalue(v) return SENT[v] ~= nil end

__touches = {}
local function noteTouch(ok, ...)
    if not ok then
        local m = ...
        if realType(m) == "string" and string.find(m, "SECRET_OP", 1, true) then
            __touches[#__touches + 1] = m
        end
    end
    return ok, ...
end
function pcall(f, ...) return noteTouch(realPcall(f, ...)) end

__printed, __degrade, __frames = {}, {}, {}
__now, __combat, __combatThrows = 1000, false, false
function print(...)
    local t = {}
    for i = 1, select("#", ...) do t[#t + 1] = realTostring((select(i, ...))) end
    __printed[#__printed + 1] = table.concat(t, " ")
end
function GetTime() return __now end
function InCombatLockdown()
    if __combatThrows then error("boom: InCombatLockdown") end
    return __combat
end

-- Every aura read API is a tripwire: the HUD display must never read an aura itself.
__auraRead = nil
local function tripwire(path)
    return function() __auraRead = __auraRead or path; error("aura read: " .. path) end
end
C_UnitAuras = {}
for _, n in ipairs({ "GetAuraDataByIndex", "GetUnitAuras", "GetPlayerAuraBySpellID", "GetAuraDataBySpellName",
                     "GetUnitAuraBySpellID", "GetAuraDuration", "GetAuraDataByAuraInstanceID" }) do
    C_UnitAuras[n] = tripwire("C_UnitAuras." .. n)
end
UnitAura, UnitBuff, UnitDebuff = tripwire("UnitAura"), tripwire("UnitBuff"), tripwire("UnitDebuff")
AuraUtil = { ForEachAura = tripwire("AuraUtil.ForEachAura"), FindAuraByName = tripwire("AuraUtil.FindAuraByName") }

-- Regions ---------------------------------------------------------------------------------
-- Three method sets (frame, texture, font string) over one shared region base. A method that
-- is not listed here is nil, so a call to anything else fails.
local Base, FrameM, TexM, FontM = {}, {}, {}, {}
local OFF = {
    TOPLEFT = { 0, 1 }, TOP = { 0.5, 1 }, TOPRIGHT = { 1, 1 }, LEFT = { 0, 0.5 }, CENTER = { 0.5, 0.5 },
    RIGHT = { 1, 0.5 }, BOTTOMLEFT = { 0, 0 }, BOTTOM = { 0.5, 0 }, BOTTOMRIGHT = { 1, 0 },
}
__calls = {}
local function count(name) __calls[name] = (__calls[name] or 0) + 1 end

function Base:SetPoint(point, a, b, c, d)
    count("SetPoint")
    assert(OFF[point], "bad point " .. realTostring(point))
    local rel, relPoint, x, y
    if realType(a) == "number" or a == nil then
        rel, relPoint, x, y = self._parent, point, a or 0, b or 0
    else
        rel = a
        if realType(b) == "string" then
            assert(OFF[b], "bad relative point " .. b)
            relPoint, x, y = b, c or 0, d or 0
        else
            relPoint, x, y = point, b or 0, c or 0
        end
    end
    self._allPoints = nil
    self._points[point] = { rel = rel, relPoint = relPoint, x = x, y = y }
end
function Base:ClearAllPoints() count("ClearAllPoints"); self._points = {}; self._allPoints = nil end
function Base:SetAllPoints(rel) count("SetAllPoints"); self._points = {}; self._allPoints = rel or self._parent end
function Base:SetSize(w, h) count("SetSize"); self._w, self._h = w, h end
function Base:SetWidth(w) self._w = w end
function Base:SetHeight(h) self._h = h end
function Base:GetWidth() return self._w end
function Base:GetHeight() return self._h end
function Base:GetSize() return self._w, self._h end
function Base:Show() self._shown = true end
function Base:Hide() self._shown = false end
function Base:IsShown() return self._shown end
function Base:SetShown(v) self._shown = v and true or false end
function Base:SetAlpha(a) count("SetAlpha"); self._alpha = a end
function Base:GetAlpha() return self._alpha end
function Base:GetParent() return self._parent end

-- Resolved rect in UIParent-centred coordinates (x right, y up): l, b, r, t.
function Base:Rect()
    if self == UIParent then return -self._w / 2, -self._h / 2, self._w / 2, self._h / 2 end
    if self._allPoints then return self._allPoints:Rect() end
    local L, R, CX, B, T, CY
    for point, p in pairs(self._points) do
        local rel = p.rel or self._parent
        local rl, rb, rr, rt = rel:Rect()
        local f, o = OFF[p.relPoint], OFF[point]
        local ax = rl + (rr - rl) * f[1] + p.x
        local ay = rb + (rt - rb) * f[2] + p.y
        if o[1] == 0 then L = ax elseif o[1] == 1 then R = ax else CX = ax end
        if o[2] == 0 then B = ay elseif o[2] == 1 then T = ay else CY = ay end
    end
    local w, h = self._w, self._h
    if L and R then w = R - L elseif L then R = L + w elseif R then L = R - w
    elseif CX then L = CX - w / 2; R = CX + w / 2 else error("no horizontal anchor: " .. (self._name or self._kind)) end
    if B and T then h = T - B elseif B then T = B + h elseif T then B = T - h
    elseif CY then B = CY - h / 2; T = CY + h / 2 else error("no vertical anchor: " .. (self._name or self._kind)) end
    return L, B, R, T
end

for k, v in pairs(Base) do FrameM[k] = v; TexM[k] = v; FontM[k] = v end

-- Frame
function FrameM:SetFrameLevel(l) self._level = l end
function FrameM:GetFrameLevel() return self._level end
function FrameM:SetFrameStrata(s) self._strata = s end
function FrameM:SetScript(k, fn) count("SetScript"); self._scripts[k] = fn end
function FrameM:GetScript(k) return self._scripts[k] end
-- Events the 16001 client rejects ("Attempt to register unknown event"); an unguarded
-- RegisterEvent on one of these throws at file scope and kills the rest of the file.
local UNKNOWN_EVENTS = { LEARNED_SPELL_IN_TAB = true }
function FrameM:RegisterEvent(e)
    if UNKNOWN_EVENTS[e] then error("Frame:RegisterEvent(): Attempt to register unknown event \"" .. e .. "\"", 2) end
    self._events[e] = true
end
function FrameM:RegisterUnitEvent(e) self._events[e] = true end
function FrameM:UnregisterEvent(e) self._events[e] = nil end
function FrameM:EnableMouse(v) self._mouse = v end
function FrameM:SetParent(p) self._parent = p end
function FrameM:CreateTexture(name, layer, tmpl, sub)
    local t = __new("Texture", self, name)
    t._layer = layer
    return t
end
function FrameM:CreateFontString(name, layer, template)
    local t = __new("FontString", self, name)
    t._layer, t._text = layer, ""
    -- an inherits template carries its font (the client's behaviour); otherwise SetFont / SetFontObject must come first
    if realType(template) == "string" then t._hasFont = true end
    return t
end
__groupOwners = {}
function FrameM:CreateAnimationGroup()
    local g = { plays = 0, stops = 0, playing = false, anims = {} }
    function g:SetLooping(m) self.looping = m end
    function g:SetToFinalAlpha(v) self.finalAlpha = v end
    function g:SetScript(n, fn) self.scripts = self.scripts or {}; self.scripts[n] = fn end
    function g:CreateAnimation(kind)
        local a = { kind = kind }
        function a:SetFromAlpha(v) self.from = v end
        function a:SetToAlpha(v) self.to = v end
        function a:SetDuration(v) self.duration = v end
        function a:SetSmoothing(v) self.smoothing = v end
        self.anims[#self.anims + 1] = a
        return a
    end
    function g:Play() self.plays = self.plays + 1; self.playing = true end
    function g:Stop() self.stops = self.stops + 1; self.playing = false end
    function g:IsPlaying() return self.playing end
    self._groups = self._groups or {}
    self._groups[#self._groups + 1] = g
    __groupOwners[#__groupOwners + 1] = self       -- every frame that ever got an AnimationGroup
    return g
end

-- Texture
__texThrows = nil     -- a substring: SetTexture of a path containing it throws (a texture that cannot load)
__texMissing = nil    -- a substring: SetTexture of a path containing it is accepted but loads nothing (WoW does not throw for a missing file)
function TexM:SetTexture(t)
    if __texThrows and realType(t) == "string" and t:find(__texThrows, 1, true) then error("boom: SetTexture " .. t) end
    if __texMissing and realType(t) == "string" and t:find(__texMissing, 1, true) then self._texture = nil; return end
    self._texture = t
end
__texReadThrows, __texReadSecret = false, false   -- GetTexture itself throws / answers with a secret
function TexM:GetTexture()
    if __texReadThrows then error("boom: GetTexture") end
    if __texReadSecret then return SS end
    return self._texture
end
function TexM:SetColorTexture(r, g, b, a) self._color = { r, g, b, a or 1 } end
function TexM:SetVertexColor(r, g, b, a) self._vc = { r, g, b, a or 1 } end
function TexM:SetTexCoord(...) self._tc = { ... } end
function TexM:SetDesaturated(v) self._desat = v and true or false end
function TexM:SetBlendMode(m) self._blend = m end
function TexM:SetGradient(...) self._gradient = { ... } end

-- FontString
function FontM:SetFont(path, size, flags) self._font = { path, size, flags }; self._hasFont = true; return true end
function FontM:SetFontObject() self._hasFont = true end
function FontM:GetFont() return self._font and self._font[1], self._font and self._font[2], self._font and self._font[3] end
-- The client throws "Font not set" for SetText / SetFormattedText on a FontString with no font yet; a write
-- before the font silently kills a pcall'd build there. The mock throws too (after counting, like the call).
function FontM:SetText(s)
    count("SetText")
    if not self._hasFont then error("Font not set", 2) end
    self._text = s
end
function FontM:SetFormattedText(fmt, ...)
    if not self._hasFont then error("Font not set", 2) end
    self._text = string.format(fmt, ...)
end
function FontM:GetText() return self._text end
function FontM:SetTextColor(r, g, b, a) self._textColor = { r, g, b, a or 1 } end
function FontM:SetShadowColor(r, g, b, a) self._shadow = { r, g, b, a } end
function FontM:SetShadowOffset(x, y) self._shadowOff = { x, y } end
function FontM:SetJustifyH(j) self._justifyH = j end
function FontM:SetJustifyV(j) self._justifyV = j end

local SETS = { Frame = FrameM, Texture = TexM, FontString = FontM }

function __new(kind, parent, name)
    local methods = SETS[kind] or FrameM
    local r = setmetatable({
        _kind = kind, _parent = parent, _name = name, _points = {}, _scripts = {}, _events = {},
        _shown = true, _alpha = 1, _w = 0, _h = 0,
        _level = (kind == "Texture" or kind == "FontString") and nil or ((parent and parent._level or 0) + 1),
    }, { __index = methods })
    __frames[#__frames + 1] = r
    if realType(name) == "string" then _G[name] = r end
    return r
end

-- AuraContainer: strict, only the methods the addon is allowed to call.
__acs, __acAttempts = {}, 0
__acThrows, __acSetUnitThrows, __acSlotThrows, __template = false, false, nil, true
local ACM = setmetatable({}, { __index = FrameM })
function ACM:SetUnit(u)
    if __acSetUnitThrows then error("boom: SetUnit") end
    self._unit = u
end
-- __acRefuse: the engine blocks SetEnabled / Show / Hide without raising (a protected call in combat);
-- __acProtected: IsProtected answers true.
__acRefuse, __acProtected = false, false
function ACM:SetEnabled(v)
    self._enableCalls = (self._enableCalls or 0) + 1
    if __acRefuse then return end
    self._enabled = v and true or false
end
function ACM:Show() self._showCalls = (self._showCalls or 0) + 1; if not __acRefuse then self._shown = true end end
function ACM:Hide() self._hideCalls = (self._hideCalls or 0) + 1; if not __acRefuse then self._shown = false end end
function ACM:IsProtected() return __acProtected == true end
function ACM:IsEnabled() return self._enabled == true end
function ACM:UpdateAllAuras() self._updates = (self._updates or 0) + 1 end
function ACM:AddAuraSlot(key, filter, opts)
    assert(realType(key) == "string" and key ~= "", "slotKey must be a non-empty string")
    assert(realType(filter) == "string" and (filter:match("^HELPFUL") or filter:match("^HARMFUL")), "bad filter " .. realTostring(filter))
    assert(not self._slots[key], "aura slot already exists: " .. key)
    assert(realType(opts) == "table" and realType(opts.initializeFrame) == "function", "initializeFrame required")
    local ids = opts.candidateFilters and opts.candidateFilters.includeSpellIDs
    assert(realType(ids) == "table", "includeSpellIDs must be a table")
    for id, v in pairs(ids) do assert(realType(id) == "number" and v == true, "includeSpellIDs is a map id -> true") end
    if __acSlotThrows == key or __acSlotThrows == true then error("boom: AddAuraSlot " .. key) end
    local frame = __new("AuraFrame", self, nil)
    frame._order, frame._icon, frame._durationText = {}, nil, nil
    setmetatable(frame, { __index = function(t, k)
        local m = FrameM[k]
        if m then return m end
        local f = ({
            SetMouseMotionEnabled = function(me, v) me._order[#me._order + 1] = "SetMouseMotionEnabled"; me._mouseMotion = v end,
            SetMouseClickEnabled = function(me, v) me._order[#me._order + 1] = "SetMouseClickEnabled"; me._mouseClick = v end,
            SetHideTooltipInCombat = function(me, v) me._order[#me._order + 1] = "SetHideTooltipInCombat" end,
            SetIcon = function(me, tex) me._order[#me._order + 1] = "SetIcon"; me._icon = tex end,
            SetDurationText = function(me, fs, o) me._order[#me._order + 1] = "SetDurationText"; me._durationText = fs end,
            SetDurationCooldown = function(me, cd) me._order[#me._order + 1] = "SetDurationCooldown" end,
            SetApplicationCount = function(me, fs) me._order[#me._order + 1] = "SetApplicationCount" end,
        })[k]
        return f
    end })
    self._slots[key] = { filter = filter, ids = ids, frame = frame, opts = opts }
    self._slotOrder[#self._slotOrder + 1] = key
    opts.initializeFrame(frame)
    return frame
end
function ACM:HasAuraSlot(key) return self._slots[key] ~= nil end

function CreateFrame(kind, name, parent, tmpl)
    if kind == "AuraContainer" then
        __acAttempts = __acAttempts + 1
        if __acThrows then error("boom: CreateFrame AuraContainer") end
        assert(tmpl == "CustomAuraContainerTemplate", "wrong template: " .. realTostring(tmpl))
        local f = __new("AuraContainer", parent, name)
        f._shown = true
        f._slots, f._slotOrder = {}, {}
        setmetatable(f, { __index = ACM })
        __acs[#__acs + 1] = f
        return f
    end
    return __new(kind, parent, name)
end

UIParent = __new("Frame", nil, nil)
UIParent._level = 0
UIParent._w, UIParent._h = 1920, 1080
function setScreen(h) UIParent._h = h; UIParent._w = h * 16 / 9 end    -- FS.Layout.Scale() is h / 1440
C_XMLUtil = { GetTemplateInfo = function(name)
    if __template == "throw" then error("boom: GetTemplateInfo") end
    if __template and name == "CustomAuraContainerTemplate" then return { name = name } end
end }
AnchorUtil = { FlowDirection = { Right = 1, Left = -1, Up = 1, Down = -1 } }
AuraContainerSortMethod = { Default = 0, Expiration = 1 }
AuraContainerSortDirection = { Normal = 0 }

-- Events and slash commands ----------------------------------------------------------------
SlashCmdList = {}
function fire(event, ...)
    local n = 0
    for _, f in ipairs(__frames) do
        local fn = f._events and f._events[event] and f._scripts.OnEvent
        if fn then
            n = n + 1
            local ok, err = realPcall(fn, f, event, ...)
            if not ok then error("event handler threw on " .. event .. ": " .. realTostring(err), 2) end
        end
    end
    return n
end

-- World: spells, class, theme, FS, the mock Hud ------------------------------------------
__spellInfo, __known = {}, {}
function IsPlayerSpell(id) return __known[id] == true end
C_Spell = { GetSpellInfo = function(x)
    local info = realType(x) == "string" and __spellInfo[x] or nil
    if realType(x) == "number" then
        for _, i in pairs(__spellInfo) do if i.spellID == x then info = i end end
    end
    return info
end }

__class = "WARLOCK"
function UnitClass() return "Class", __class end

function check(c, msg) if not c then error("CHECK FAILED: " .. realTostring(msg), 2) end end
function near(a, b, msg, tol)
    if a == nil or b == nil or math.abs(a - b) > (tol or 1e-6) then
        error("CHECK FAILED: " .. realTostring(msg) .. ": got " .. realTostring(a) .. ", want " .. realTostring(b), 2)
    end
end
function degraded(key)
    local n = 0
    for _, k in ipairs(__degrade) do if k == key then n = n + 1 end end
    return n
end
function printed(pattern)
    for _, s in ipairs(__printed) do if s:find(pattern, 1, true) then return true end end
    return false
end

function __setupWorld(class)
    __class = class
    FS = {
        IsSecret = function(v) return SENT[v] ~= nil end,
        LogDegradeOnce = function(key, msg) __degrade[#__degrade + 1] = key end,
        Theme = {},
    }
    -- The Gunsight-DISABLED stub (`/fsgun off`): every Stack A check runs under it. It counts what
    -- the HUD asks of it, so a Stack A build that registers a piece or waits for OnReady fails.
    __gsCalls = { onReady = 0, pieces = {} }
    FS.Gunsight = {
        IsEnabled = function() return false end,
        IsPieceOn = function() return true end,
        OnReady = function() __gsCalls.onReady = __gsCalls.onReady + 1 end,
        RegisterPiece = function(key) __gsCalls.pieces[#__gsCalls.pieces + 1] = key; return true end,
    }
    local T = FS.Theme
    function T.ApplyFontGeneric(fs, path, size, color, flags)
        fs:SetFont(path, size, flags)
        local c = color or T.COLOR_TEXT_WHITE
        fs:SetTextColor(c[1], c[2], c[3], c[4] or 1)
        fs:SetShadowColor(0, 0, 0, 1)
        fs:SetShadowOffset(1, -1)
    end
    function T.ApplyMono(fs, size, color)
        T.ApplyFontGeneric(fs, T.FONT_MONO, size, color, "")
        fs:SetShadowColor(0, 0, 0, 0)
    end
    -- nine-slice helpers: the margin is recorded on the texture (_slice), the real ones only call
    -- SetTextureSliceMargins
    function T.ApplyNineSlice(tex, margin) tex._slice = margin; return true end
    function T.AddSliceTexture(frame, path, color, layer, sublevel, inset)
        local tex = frame:CreateTexture(nil, layer or "BACKGROUND", nil, sublevel)
        tex:SetTexture(path)
        T.ApplyNineSlice(tex)
        inset = inset or 0
        tex:SetPoint("TOPLEFT", frame, "TOPLEFT", inset, -inset)
        tex:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -inset, inset)
        if color then tex:SetVertexColor(color[1], color[2], color[3], color[4] or 1) end
        tex._inset = inset
        return tex
    end
    __glows = {}
    function T.AddOuterGlow(frame, r, g, b, size, alpha, radius)
        __glows[#__glows + 1] = { frame = frame, r = r, g = g, b = b, size = size, alpha = alpha, radius = radius }
        frame._glow = __glows[#__glows]
    end
end
function __loadThemeConstants(lines)
    assert(loadstring("local Theme = ...\n" .. table.concat(lines, "\n"), "@Theme.lua(constants)"))(FS.Theme)
end
function __load(path, src)
    local fn = assert(loadstring(src, "@" .. path))
    return fn("ForeverSynthwave", FS)
end

-- Spell info for every dictionary name; ids are the dictionary's first id, else 900000+n.
function __setupSpells()
    local n = 0
    local keys = {}
    for k in pairs(FS.HudSpells) do keys[#keys + 1] = k end
    table.sort(keys)
    for _, k in ipairs(keys) do
        local def = FS.HudSpells[k]
        for _, name in ipairs(def.names) do
            n = n + 1
            __spellInfo[name] = { name = name, spellID = (def.ids and def.ids[1]) or (900000 + n), iconID = 5000 + n }
        end
    end
end
function iconOf(key) local i = __spellInfo[FS.HudSpells[key].names[1]]; return i and i.iconID end
function idOf(key) local i = __spellInfo[FS.HudSpells[key].names[1]]; return i and i.spellID end
function learn(key) for _, name in ipairs(FS.HudSpells[key].names) do __known[__spellInfo[name].spellID] = true end end
function forget(key) for _, name in ipairs(FS.HudSpells[key].names) do __known[__spellInfo[name].spellID] = nil end end
function learnAll() for k in pairs(FS.HudSpells) do learn(k) end end

-- The mock FS.Hud. GetState counts its calls: the display must not poll it.
__state = nil
function __setupHud()
    local Hud = { subs = {}, getStateCalls = 0, subscribeCalls = 0, unsubscribeCalls = 0 }
    function Hud.GetState() Hud.getStateCalls = Hud.getStateCalls + 1; return __state end
    function Hud.GetProfile() return FS.HudProfiles[__class] end
    function Hud.Subscribe(fn)
        Hud.subscribeCalls = Hud.subscribeCalls + 1
        Hud.subs[#Hud.subs + 1] = fn
        local ok, err = realPcall(fn, __state)
        if not ok then __hudPushErrors = (__hudPushErrors or 0) + 1; __hudLastError = err end
        return fn
    end
    function Hud.Unsubscribe(fn)
        Hud.unsubscribeCalls = Hud.unsubscribeCalls + 1
        for i = #Hud.subs, 1, -1 do if Hud.subs[i] == fn then table.remove(Hud.subs, i) end end
    end
    FS.Hud = Hud
end
function push(state)
    __state = state
    for _, fn in ipairs(FS.Hud.subs) do
        local ok, err = realPcall(fn, state)
        if not ok then __hudPushErrors = (__hudPushErrors or 0) + 1; __hudLastError = err end
    end
end

function mkState(over)
    local s = { active = true, class = __class, inCombat = false, row = {}, buffsMissing = {}, procs = {} }
    for k, v in pairs(over or {}) do s[k] = v end
    return s
end
function rowEntry(key, o)
    local e = { key = key, icon = iconOf(key) }
    for k, v in pairs(o or {}) do e[k] = v end
    return e
end
-- A full warlock row: Corruption, Bane of Agony, Immolate, Siphon Life, Shadow Bolt.
function lockRow(over)
    local row = {
        rowEntry("corruption", { missing = false, remaining = 11 }),
        rowEntry("bane_agony", { missing = false, remaining = 19 }),
        rowEntry("immolate", { missing = true }),
        rowEntry("siphon", { missing = false, remaining = 22 }),
        rowEntry("shadow_bolt"),
    }
    for i, o in pairs(over or {}) do for k, v in pairs(o) do row[i][k] = v end end
    return row
end

-- The Stack A cast bars as CastBars.lua seats them: 268 x 22 frames, CENTER anchored.
function useCastBars(x, y, gap, w)
    gap = gap or 18
    w = w or 268
    local function mk(name, cy)
        local f = CreateFrame("Frame", name, UIParent)
        f:SetSize(w, 22)
        f:SetPoint("CENTER", UIParent, "CENTER", x, cy)
        return f
    end
    FS.targetCastBar = { frame = mk("FakeTargetCastBar", y + gap / 2 + 11) }
    FS.playerCastBar = { frame = mk("FakePlayerCastBar", y - gap / 2 - 11) }
    __idle = { visible = {}, hints = {} }
    __rest = {}
    FS.CastBars = {
        SetIdleHint = function(unit, text) __idle.hints[#__idle.hints + 1] = { unit, text }; return true end,
        SetIdleVisible = function(v) __idle.visible[#__idle.visible + 1] = v end,
        SetRestAlpha = function(a) __rest[#__rest + 1] = a; return true end,
    }
end

function login() return fire("PLAYER_LOGIN") end
function rect(f) local l, b, r, t = f:Rect(); return { l = l, b = b, r = r, t = t } end
function rectEq(f, l, b, r, t, msg)
    local q = rect(f)
    near(q.l, l, msg .. " left"); near(q.b, b, msg .. " bottom"); near(q.r, r, msg .. " right"); near(q.t, t, msg .. " top")
end
GOLD = { 1, 210 / 255, 63 / 255, 1 }      -- the mockup's --gold #ffd23f, not a Theme token yet
function colorEq(a, b, tol)
    tol = tol or 1e-6
    return a and b and math.abs(a[1] - b[1]) < tol and math.abs(a[2] - b[2]) < tol and math.abs(a[3] - b[3]) < tol
end
-- How many AnimationGroups were ever created on `root` or any frame below it.
function animGroupsUnder(root)
    local n = 0
    for _, owner in ipairs(__groupOwners) do
        local f = owner
        while f do
            if f == root then n = n + 1; break end
            f = f._parent
        end
    end
    return n
end
function allShownDescendants(frame)
    local out = {}
    for _, f in ipairs(__frames) do if f._parent == frame then out[#out + 1] = f end end
    return out
end
-- Warlock: everything learned, the real HUD default on.
function standard()
    learnAll()
    useCastBars(0, -317)
end
"""

# Mockup numbers, resolved once. COMBATHUD_LUA mutation runs still read the real mockup.
LUA_FILE_SHIM = r"""
function __loadCombatHud(src)
    local fn, err = loadstring(src, "@CombatHud.lua")
    if not fn then error("CombatHud.lua failed to compile: " .. tostring(err), 0) end
    return fn("ForeverSynthwave", FS)
end
"""


def build_runtime(cls: str, gunsight: bool = False):
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.execute(LUA_FILE_SHIM)
    lua.execute(f'__setupWorld("{cls}")')
    theme_src = THEME.read_text(encoding="utf-8")
    consts = [_extract_theme_constant(theme_src, n) for n in THEME_CONSTANTS]
    consts += [_extract_theme_function(theme_src, n) for n in THEME_FUNCTIONS]
    lua.eval("__loadThemeConstants")(lua.table_from(consts))
    loader = lua.eval("__load")
    for fname in ("HudSpells.lua", "HudProfiles.lua"):
        loader(fname, (ADDON / fname).read_text(encoding="utf-8"))
    lua.execute("__setupSpells(); __setupHud()")
    lua.execute(f"MU = {lua_table(mockup_units())}; CB = {lua_table(castbars_units())}; CUT_FRACTION = {tile_cut_fraction()!r}")
    if gunsight:
        # the real Layout.lua and Gunsight.lua replace the disabled stub; GU is the Gunsight mockup's numbers
        lua.execute("FS.Gunsight = nil; __gsCalls = nil; setScreen(1440)")
        for fname in ("Layout.lua", "Gunsight.lua"):
            loader(fname, (ADDON / fname).read_text(encoding="utf-8"))
        lua.execute(f"GU = {lua_value(gunsight_units())}")
    return lua


CASES: list[tuple[str, str, str, bool]] = []


# Lua run after the mock world is built and BEFORE CombatHud.lua loads: client globals the file
# reads at load time (a case name -> a snippet).
PRELUDES: dict[str, str] = {}


def case(name: str, cls: str = "WARLOCK", gunsight: bool = False):
    def deco(body: str):
        CASES.append((name, cls, body, gunsight))
        return body
    return deco


# ---------------------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------------------

case("constants_match_the_mockup_and_castbars")(r"""
local G = FS.CombatHud.geometry
check(G, "no geometry table")
local function eq(a, b, msg) check(a == b, msg .. ": CombatHud has " .. tostring(a) .. ", mockup/CastBars has " .. tostring(b)) end
eq(G.TILE, MU.TILE, "spell tile"); eq(G.TILE_GAP, MU.TILE_GAP, "tile gap")
eq(G.ROW_H, MU.HUD_ROW, "HUD_ROW"); eq(G.ROW_GAP, MU.HUD_ROW_GAP, "HUD_ROW_GAP")
eq(G.NEXT, MU.HUD_NEXT, "HUD_NEXT"); eq(G.NEXT_GAP, MU.NEXT_PAD, "next tile gap to the column")
eq(G.SHARD_W, MU.SHARD_W, "shard w"); eq(G.SHARD_H, MU.SHARD_H, "shard h"); eq(G.SHARD_GAP, MU.SHARD_GAP, "shard gap")
eq(G.SHARD_TOP, MU.SHARD_TOP, "shard margin-top"); eq(G.SHARD_ROW_H, MU.SHARD_H_ROW, "shard row height")
eq(G.BUFF, MU.BUFF, "buff tile"); eq(G.BUFF_GAP, MU.BUFF_GAP, "buff gap"); eq(G.BUFF_TOP, MU.BUFF_TOP, "buff margin-top")
eq(G.BUFF_ROW_H, MU.BUFF_ROW_H, "buff row height")
eq(G.TAB_H, MU.TAB_H, "mockup tabH"); eq(G.TAB_H, CB.TAB_H, "CastBars TAB_H")
eq(G.FRAME_H, MU.BAR_H, "mockup bar H"); eq(G.FRAME_H, CB.FRAME_H, "CastBars FRAME_H")
eq(G.GAP, CB.GAP, "CastBars GAP")
-- The Stack A mockup says 64; the gap in force is the approved off-state mockup's 18 (the bridge left the stack).
eq(CB.GAP, CB.OFFSTATE_GAP, "off-state mockup GAP")
eq(G.FALLBACK_X, CB.SEAT_X, "fixed seat x"); eq(G.FALLBACK_Y, CB.SEAT_Y, "fixed seat y")
""")

case("fallback_geometry_matches_the_mockup_offsets")(r"""
learnAll()                         -- no cast bars: the fixed Stack A seat
__state = mkState({ inCombat = true, row = lockRow(), shards = 3,
    next = { key = "shadow_bolt", icon = iconOf("shadow_bolt") },
    buffsMissing = { { key = "demon_armor", icon = iconOf("demon_armor") }, { key = "pet" } } })
login()
local ui = FS.CombatHud.ui
-- The mockup's own arithmetic (px from its CSS/JS), in UIParent-centred coordinates.
local W = 268
local gapY = CB.SEAT_Y
local tTop = gapY + CB.GAP / 2 + MU.BAR_H        -- target frame top
local pBot = gapY - CB.GAP / 2 - MU.BAR_H        -- player frame bottom
local rowBottom = tTop + MU.TAB_H + MU.HUD_ROW_GAP
local rowTop = rowBottom + MU.HUD_ROW
local rowW = 5 * MU.TILE + 4 * MU.TILE_GAP
rectEq(ui.row, -rowW / 2, rowBottom, rowW / 2, rowTop, "spell row")
for i = 1, 5 do
    local t = ui.tiles[({ "corruption", "bane_agony", "immolate", "siphon", "shadow_bolt" })[i]]
    local l = -rowW / 2 + (i - 1) * (MU.TILE + MU.TILE_GAP)
    rectEq(t.holder, l, rowBottom, l + MU.TILE, rowTop, "tile " .. i)
end
-- the next tile: left of the column, 10 units clear, centred on the gap
rectEq(ui.nextTile.holder, -W / 2 - MU.NEXT_PAD - MU.HUD_NEXT, gapY - MU.HUD_NEXT / 2, -W / 2 - MU.NEXT_PAD, gapY + MU.HUD_NEXT / 2, "next tile")
-- shards: under the player tab (+6), right aligned to the bar's right edge, 10 x 12, gap 3
local shTop = pBot - MU.TAB_H - MU.SHARD_TOP
rectEq(ui.shards, W / 2 - (3 * MU.SHARD_W + 2 * MU.SHARD_GAP), shTop - MU.SHARD_H_ROW, W / 2, shTop, "shard row")
local d1 = rect(ui.diamonds[1]); near(d1.r, W / 2, "first diamond is flush right"); near(d1.r - d1.l, MU.SHARD_W, "diamond w"); near(d1.t - d1.b, MU.SHARD_H, "diamond h")
local d2 = rect(ui.diamonds[2]); near(d1.l - d2.r, MU.SHARD_GAP, "diamond gap")
-- buffs: centred, 8 below the shard row
local bTop = shTop - MU.SHARD_H_ROW - MU.BUFF_TOP
local bW = 2 * MU.BUFF + MU.BUFF_GAP
rectEq(ui.buffs, -bW / 2, bTop - MU.BUFF_ROW_H, bW / 2, bTop, "buff row")
""")

case("no_shards_pulls_the_buff_row_up_to_the_player_tab")(r"""
learnAll()
__state = mkState({ inCombat = true, row = lockRow(), shards = 0, buffsMissing = { { key = "demon_armor" } } })
login()
local ui = FS.CombatHud.ui
local pBot = CB.SEAT_Y - CB.GAP / 2 - MU.BAR_H
local bTop = pBot - MU.TAB_H - MU.BUFF_TOP
rectEq(ui.buffs, -MU.BUFF / 2, bTop - MU.BUFF_ROW_H, MU.BUFF / 2, bTop, "buff row without shards")
check(not ui.shards:IsShown(), "the shard row is hidden at 0")
push(mkState({ inCombat = true, row = lockRow(), shards = 2, buffsMissing = { { key = "demon_armor" } } }))
local shTop = pBot - MU.TAB_H - MU.SHARD_TOP
rectEq(ui.buffs, -MU.BUFF / 2, shTop - MU.SHARD_H_ROW - MU.BUFF_TOP - MU.BUFF_ROW_H, MU.BUFF / 2, shTop - MU.SHARD_H_ROW - MU.BUFF_TOP, "buff row under the shards")
""")

case("fallback_is_logged_once")(r"""
learnAll()
__state = mkState({ row = lockRow() })
login()
check(degraded("combathud_no_castbars") == 1, "the missing cast bars are logged once: " .. degraded("combathud_no_castbars"))
FS.CombatHud.Disable(); FS.CombatHud.Enable(); FS.CombatHud.Disable(); FS.CombatHud.Enable()
check(degraded("combathud_no_castbars") == 1, "still once after re-enabling")
""")

case("follows_real_castbar_frames_wherever_castbars_put_them")(r"""
learnAll()
-- a seat well away from the fixed one, with a wider gap than the real one
useCastBars(250, 100, 80, 268)
__state = mkState({ inCombat = true, row = lockRow(), shards = 4,
    next = { key = "shadow_bolt", icon = iconOf("shadow_bolt") } })
login()
local ui = FS.CombatHud.ui
local tTop = 100 + 40 + 22
rectEq(ui.row, 250 - 102, tTop + 15 + 10, 250 + 102, tTop + 15 + 10 + 36, "row follows the target bar")
rectEq(ui.nextTile.holder, 250 - 134 - 10 - 56, 100 - 28, 250 - 134 - 10, 100 + 28, "next tile centred on the wider gap")
local pBot = 100 - 40 - 22
near(rect(ui.shards).t, pBot - 15 - 6, "shard row under the player bar")
check(degraded("combathud_no_castbars") == 0, "real frames, no fallback")
-- CastBars re-seats the stack (a UI scale change): the HUD follows without being told
FS.targetCastBar.frame:SetPoint("CENTER", UIParent, "CENTER", -300, 200)
FS.playerCastBar.frame:SetPoint("CENTER", UIParent, "CENTER", -300, 100)
near(rect(ui.row).l, -300 - 102, "row moved with the bars")
near(rect(ui.nextTile.holder).r, -300 - 134 - 10, "next tile moved with the bars")
""")

# ---------------------------------------------------------------------------------------
# Spell row
# ---------------------------------------------------------------------------------------

case("one_tile_per_row_entry_with_its_icon")(r"""
standard()
__state = mkState({ inCombat = true, row = lockRow() })
login()
local ui = FS.CombatHud.ui
local keys = { "corruption", "bane_agony", "immolate", "siphon", "shadow_bolt" }
for _, k in ipairs(keys) do
    local t = ui.tiles[k]
    check(t and t.holder:IsShown(), "tile for " .. k)
    check(t.icon._texture == iconOf(k), "icon of " .. k)
    check(t.holder:GetWidth() == 36 and t.holder:GetHeight() == 36, "36 x 36 tile")
end
-- the row shrinks (a spell is dropped): its tile hides and the rest re-centre
local row = lockRow(); table.remove(row, 4)
push(mkState({ inCombat = true, row = row }))
check(not ui.tiles.siphon.holder:IsShown(), "dropped spell's tile is hidden")
local w = 4 * 36 + 3 * 6
rectEq(ui.row, -w / 2, rect(ui.row).b, w / 2, rect(ui.row).t, "row re-centred at four tiles")
""")

case("an_empty_or_inactive_state_hides_everything")(r"""
standard()
__state = mkState({ inCombat = true, row = lockRow(), shards = 3, next = { key = "shadow_bolt" }, buffsMissing = { { key = "pet" } } })
login()
local ui = FS.CombatHud.ui
check(ui.row:IsShown() and ui.nextTile.holder:IsShown() and ui.shards:IsShown() and ui.buffs:IsShown(), "all up")
push(mkState({ active = false }))
check(not ui.nextTile.holder:IsShown() and not ui.shards:IsShown() and not ui.buffs:IsShown(), "inactive: nothing shown")
for _, t in pairs(ui.tiles) do check(not t.holder:IsShown(), "inactive: no tile") end
""")

case("dim_states_follow_the_mockup")(r"""
standard()
__state = mkState({ inCombat = true, row = lockRow({
    [3] = { missing = true },                          -- a DoT that is down
    [5] = { onCd = true, cdRemaining = 7 },            -- a spell on cooldown
}) })
login()
local ui = FS.CombatHud.ui
local function dim(k) return ui.tiles[k].face:GetAlpha() == 0.45 and ui.tiles[k].icon._desat == true end
check(not dim("corruption"), "a DoT that is up is not dim")
check(dim("immolate"), "a missing DoT is dim (grayscale, opacity .45)")
check(dim("shadow_bolt"), "a spell on cooldown is dim")
check(not dim("siphon"), "up DoT")
-- unknown (nil) DoT state is never guessed dim
push(mkState({ inCombat = true, row = lockRow({ [1] = { missing = false }, [3] = { missing = SB } }) }))
check(not dim("immolate"), "a secret DoT state is not dim")
-- a DoT that is up wins over its own cooldown (mockup: up, then cooldown, then missing)
push(mkState({ inCombat = true, row = lockRow({ [1] = { missing = false, onCd = true, cdRemaining = 30 } }) }))
check(not dim("corruption"), "DoT up beats its cooldown")
check(ui.tiles.corruption.secs:GetText() == "", "no cooldown text while the aura timer owns the corner")
""")

case("cooldown_text_counts_down_on_a_ten_hertz_throttle")(r"""
standard()
__now = 1000
__state = mkState({ inCombat = true, row = lockRow({ [5] = { onCd = true, cdRemaining = 8 } }) })
login()
local ui = FS.CombatHud.ui
local t = ui.tiles.shadow_bolt
check(t.secs:GetText() == "8", "cooldown text on arrival: " .. tostring(t.secs:GetText()))
local onUpdate = ui.root:GetScript("OnUpdate")
check(onUpdate, "an OnUpdate exists while a cooldown is showing")
-- two simulated seconds at 64 fps (1/64 is exact in binary, so the clock does not drift)
local stats = FS.CombatHud.stats
local before = stats.cdTicks or 0
for i = 1, 128 do __now = __now + 1 / 64; onUpdate(ui.root, 1 / 64) end
local ticks = (stats.cdTicks or 0) - before
check(ticks >= 18 and ticks <= 20, "the cooldown work ran " .. ticks .. " times in two seconds (want 18 to 20, at most 10 Hz)")
check(t.secs:GetText() == "7", "counted down to 7 after two seconds: " .. tostring(t.secs:GetText()))
-- a large frame step cannot run the work more than once
before = stats.cdTicks
onUpdate(ui.root, 5)
check(stats.cdTicks - before == 1, "a long frame still runs it once")
""")

case("cooldown_text_clears_at_zero_and_the_onupdate_is_removed_when_idle")(r"""
standard()
__now = 1000
__state = mkState({ inCombat = true, row = lockRow({ [5] = { onCd = true, cdRemaining = 1.5 } }) })
login()
local ui = FS.CombatHud.ui
check(ui.root:GetScript("OnUpdate"), "ticking while a cooldown runs")
__now = __now + 2
ui.root:GetScript("OnUpdate")(ui.root, 0.2)
check(ui.tiles.shadow_bolt.secs:GetText() == "", "text clears when the cooldown has run out")
check(ui.root:GetScript("OnUpdate") == nil, "no OnUpdate when nothing counts down")
-- the Hud says ready: nothing to tick, nothing installed
push(mkState({ inCombat = true, row = lockRow() }))
check(ui.root:GetScript("OnUpdate") == nil, "still no OnUpdate")
-- minutes read as Nm
push(mkState({ inCombat = true, row = lockRow({ [5] = { onCd = true, cdRemaining = 100 } }) }))
check(ui.tiles.shadow_bolt.secs:GetText() == "2m", "100 s reads 2m: " .. tostring(ui.tiles.shadow_bolt.secs:GetText()))
""")

case("next_ring_is_cyan_and_proc_ring_is_gold_and_both_are_static")(r"""
standard()
local CYAN = FS.Theme.COLOR_POWER
__state = mkState({ inCombat = true, row = lockRow({ [5] = { isNext = true } }) })
login()
local ui = FS.CombatHud.ui
local ring = ui.tiles.shadow_bolt.ring
check(ring:IsShown() and ring.kind == "cyan", "next spell gets the cyan ring")
check(colorEq(ring.edges[1]._vc, CYAN), "ring edges are the cyan token")
check(animGroupsUnder(ring) == 0, "the next ring has no AnimationGroup on it or its glow hosts")
check(not ui.tiles.corruption.ring:IsShown(), "other tiles have no ring")
check(#ring.edges == 2 and ring.edges[2]._inset == 1, "2 unit ring: two stacked 1 texel cut outlines")
-- a proc on the same tile: gold, pulsing, with a glow built in the same colour
push(mkState({ inCombat = true, row = lockRow({ [5] = { isNext = true, proc = "gold" } }) }))
check(ring.kind == "gold" and colorEq(ring.edges[1]._vc, GOLD), "proc ring is gold")
check(animGroupsUnder(ring) == 0, "the proc ring is static: no AnimationGroup on the ring or its glow hosts (the mockup's .ring.gold has no animation)")
local glow = ring.glows.gold
check(glow and glow._glow and colorEq({ glow._glow.r, glow._glow.g, glow._glow.b }, GOLD) and glow._glow.size == 8, "gold glow, size 8 as box-shadow 0 0 8px")
-- back to a plain next: cyan again, pulse stopped
push(mkState({ inCombat = true, row = lockRow({ [5] = { isNext = true } }) }))
check(ring.kind == "cyan" and animGroupsUnder(ring) == 0, "proc over: cyan, still no animation")
""")

case("proc_glow_also_comes_from_state_procs_through_the_profiles_overlay_spell")(r"""
standard()
-- Nightfall (shadow_trance) lights Shadow Bolt by the profile's overlaySpell, even when the row
-- entry carries no proc of its own.
__state = mkState({ inCombat = true, row = lockRow(),
    procs = { { key = "shadow_trance", glow = "gold", active = true }, { key = "decimation", glow = "red", active = false } } })
login()
local ui = FS.CombatHud.ui
check(ui.tiles.shadow_bolt.ring:IsShown() and ui.tiles.shadow_bolt.ring.kind == "gold", "Shadow Bolt glows gold")
check(not ui.tiles.corruption.ring:IsShown(), "no other glow")
push(mkState({ inCombat = true, row = lockRow(), procs = { { key = "shadow_trance", glow = "gold", active = false } } }))
check(not ui.tiles.shadow_bolt.ring:IsShown(), "inactive proc, no glow")
push(mkState({ inCombat = true, row = lockRow(), procs = { { key = "shadow_trance", glow = "gold", active = nil } } }))
check(not ui.tiles.shadow_bolt.ring:IsShown(), "unknown proc, no glow")
""")

# ---------------------------------------------------------------------------------------
# DoT timers: AuraContainer slots
# ---------------------------------------------------------------------------------------

case("each_dot_tile_gets_a_target_slot_with_its_rank_ids")(r"""
standard()
__state = mkState({ inCombat = false, row = lockRow() })
login()
local ui = FS.CombatHud.ui
local c = FS.CombatHud.containers.target
check(c and c._unit == "target", "a container on unit target")
check(c._enabled == true and c._shown, "the target container is enabled and shown")
check(__acs[1]._kind == "AuraContainer", "an AuraContainer was built")
for _, k in ipairs({ "corruption", "bane_agony", "immolate", "siphon" }) do
    local s = c._slots["dot_" .. k]
    check(s, "slot for " .. k)
    check(s.filter == "HARMFUL|PLAYER", "own harmful filter for " .. k .. ": " .. tostring(s.filter))
    check(s.ids[idOf(k)], "the resolved top rank id of " .. k)
    check(ui.tiles[k].slot == s.frame, "the tile keeps its slot frame")
end
check(not c._slots.dot_shadow_bolt, "a plain cast has no slot")
-- ranks the profile's dictionary does not list: Corruption ranks 2 to 6
local cor = c._slots.dot_corruption.ids
check(cor[172] and cor[25311] and cor[6222] and cor[7648] and cor[11671] and cor[11672], "every Corruption rank")
""")

case("a_grouped_dot_slot_covers_every_bane")(r"""
standard()
__state = mkState({ row = lockRow() })
login()
local ids = FS.CombatHud.containers.target._slots.dot_bane_agony.ids
check(ids[idOf("bane_agony")] and ids[idOf("bane_doom")], "Bane of Agony's slot also shows Bane of Doom (one bane group)")
""")

case("priest_dots_get_slots_and_the_priest_row_follows_its_profile", "PRIEST")(r"""
learnAll()
useCastBars(0, -317)
__state = mkState({ inCombat = true, row = {
    rowEntry("sw_pain", { missing = false }), rowEntry("dplague", { missing = true, onCd = true, cdRemaining = 20 }),
    rowEntry("mind_blast", { onCd = true, cdRemaining = 3 }), rowEntry("swd"), rowEntry("mind_flay"), rowEntry("smite") } })
login()
local c = FS.CombatHud.containers.target
check(c._slots.dot_sw_pain and c._slots.dot_dplague, "SW:P and Devouring Plague have slots")
check(not c._slots.dot_mind_blast and not c._slots.dot_swd, "cooldown spells do not")
local swp = c._slots.dot_sw_pain.ids
check(swp[589] and swp[594] and swp[10894], "SW:P ranks 1, 3 (594 is what own casts report) and 7")
check(FS.CombatHud.ui.tiles.dplague.secs:GetText() == "20", "a DoT that is down shows its cooldown")
""")

case("slot_frames_are_initialised_mouse_off_first_with_timer_text_and_sit_on_the_tile")(r"""
standard()
__state = mkState({ row = lockRow() })
login()
local ui = FS.CombatHud.ui
local s = FS.CombatHud.containers.target._slots.dot_corruption
local f = s.frame
check(f._order[1] == "SetMouseMotionEnabled" and f._order[2] == "SetMouseClickEnabled", "mouse off before anything else: " .. table.concat(f._order, ","))
check(f._mouseMotion == false and f._mouseClick == false, "mouse disabled")
local has = {}
for _, n in ipairs(f._order) do has[n] = true end
check(has.SetDurationText and f._durationText, "the aura frame carries the engine's duration text")
check(not has.SetIcon, "a DoT slot draws no icon: the tile already shows the spell")
local fs = f._durationText
check(fs._font and fs._font[2] == 11 and fs._font[1] == FS.Theme.FONT_MONO, "11pt mono, the mockup's .secs")
check(fs._font[3] == "OUTLINE", "outlined, the mockup's 4 way black text-shadow")
check(colorEq(fs._textColor, { 1, 1, 1 }), "white")
local tl = rect(ui.tiles.corruption.holder)
rectEq(f, tl.l, tl.b, tl.r, tl.t, "slot sits exactly on its tile")
check(f:GetFrameLevel() > ui.tiles.corruption.holder:GetFrameLevel(), "the timer is drawn above the tile")
""")

case("containers_and_slots_are_built_out_of_combat_only_and_pending_ones_follow_regen")(r"""
standard()
__combat = true
__state = mkState({ inCombat = true, row = lockRow() })
login()
local ui = FS.CombatHud.ui
check(__acAttempts == 0, "no container built in combat")
for _, k in ipairs({ "corruption", "immolate" }) do check(ui.tiles[k].holder:IsShown() and ui.tiles[k].slot == nil, "tile without a timer in combat: " .. k) end
__combat = false
fire("PLAYER_REGEN_ENABLED")
local c = FS.CombatHud.containers.target
check(c and c._slots.dot_corruption and c._slots.dot_immolate, "slots are built once combat ends")
check(ui.tiles.corruption.slot == c._slots.dot_corruption.frame, "and wired to the tiles")
-- a spell that appears in the row mid fight waits for the next out of combat moment
__combat = true
local row = lockRow(); row[#row + 1] = rowEntry("wrack", { missing = true })
push(mkState({ inCombat = true, row = row }))
check(c._slots.dot_wrack == nil and FS.CombatHud.ui.tiles.wrack.holder:IsShown(), "new DoT tile in combat has no slot yet")
__combat = false
fire("PLAYER_REGEN_ENABLED")
-- Wrack has no dictionary ids (names only), so its slot is keyed on the id its name resolves to
check(c._slots.dot_wrack and c._slots.dot_wrack.ids[idOf("wrack")], "the pending slot is built, on the resolved id")
""")

case("a_dot_with_no_resolvable_ids_gets_no_slot_and_one_log")(r"""
standard()
__spellInfo["Wrack"] = nil          -- the client does not know the name: nothing to key a slot on
__state = mkState({ row = lockRow({}) })
local row = lockRow(); row[#row + 1] = rowEntry("wrack", { missing = true })
__state = mkState({ row = row })
login()
push(mkState({ row = row }))
check(FS.CombatHud.containers.target._slots.dot_wrack == nil, "no slot without ids")
check(FS.CombatHud.ui.tiles.wrack.holder:IsShown(), "the tile is still drawn")
check(degraded("combathud_no_ids") == 1, "logged once: " .. degraded("combathud_no_ids"))
""")

case("no_aura_read_api_is_ever_touched")(r"""
standard()
__state = mkState({ inCombat = true, row = lockRow(), buffsMissing = { { key = "pet" } },
    next = { key = "shadow_bolt" }, shards = 3 })
login()
check(FS.CombatHud.IsEnabled() and FS.CombatHud.ui.tiles.corruption, "the HUD is up, so this tripwire means something")
push(mkState({ inCombat = false, row = lockRow(), buffsMissing = { { key = "demon_armor" } } }))
fire("PLAYER_TARGET_CHANGED")
__combat = true; push(mkState({ inCombat = true, row = lockRow() }))
check(__auraRead == nil, "an aura read API was called: " .. tostring(__auraRead))
""")

case("container_failure_leaves_the_tiles_without_a_timer_and_logs_once")(r"""
standard()
__acThrows = true
__state = mkState({ inCombat = true, row = lockRow() })
login()
local ui = FS.CombatHud.ui
for _, k in ipairs({ "corruption", "bane_agony", "immolate", "siphon", "shadow_bolt" }) do
    check(ui.tiles[k].holder:IsShown(), "tile still shown: " .. k)
    check(ui.tiles[k].slot == nil, "and without a slot: " .. k)
end
check(ui.tiles.corruption.secs:GetText() == "11", "no engine timer: the Hud's own estimate stands in")
check(degraded("combathud_aura_container") == 1, "logged once: " .. degraded("combathud_aura_container"))
push(mkState({ inCombat = true, row = lockRow() }))
check(degraded("combathud_aura_container") == 1, "still once after another redraw")
""")

case("repeated_container_failures_give_the_path_up")(r"""
standard()
__acThrows = true
__state = mkState({ inCombat = true, row = lockRow() })
login()
for _ = 1, 8 do push(mkState({ inCombat = true, row = lockRow() })) end
check(__acAttempts == 3, "three build attempts, then no more: " .. __acAttempts)
check(degraded("combathud_aura_container_giveup") == 1, "the give-up is logged once")
__acThrows = false
for _ = 1, 3 do push(mkState({ inCombat = true, row = lockRow() })) end
fire("PLAYER_REGEN_ENABLED")
check(__acAttempts == 3, "a healthy client later does not revive it this session")
check(FS.CombatHud.ui.tiles.corruption.holder:IsShown(), "tiles are fine")
check(FS.CombatHud.ui.tiles.corruption.slot == nil and FS.CombatHud.ui.tiles.corruption.secs:GetText() == "11", "given up: no slot, the Hud's remaining stands in")
""")

case("a_failing_slot_does_not_take_the_other_tiles_down")(r"""
standard()
__acSlotThrows = "dot_immolate"
__state = mkState({ row = lockRow() })
login()
local ui = FS.CombatHud.ui
local c = FS.CombatHud.containers.target
check(ui.tiles.immolate.holder:IsShown() and ui.tiles.immolate.slot == nil, "immolate shown without a timer")
check(c._slots.dot_corruption and c._slots.dot_siphon, "the others still have slots")
check(degraded("combathud_aura_slot") == 1, "slot failure logged once")
""")

case("a_throwing_setunit_is_a_container_failure_not_a_crash")(r"""
standard()
__acSetUnitThrows = true
__state = mkState({ row = lockRow() })
login()
check(FS.CombatHud.ui.tiles.corruption.holder:IsShown(), "tile shown")
check(FS.CombatHud.ui.tiles.corruption.slot == nil, "no timer")
check(degraded("combathud_aura_container") == 1, "logged")
""")

case("no_aura_container_template_means_tiles_without_timers_and_one_log")(r"""
standard()
__template = false
__state = mkState({ inCombat = true, row = lockRow() })
login()
check(__acAttempts == 0, "no container is attempted without the template")
check(FS.CombatHud.ui.tiles.corruption.holder:IsShown(), "tile shown")
check(FS.CombatHud.ui.tiles.corruption.slot == nil and FS.CombatHud.ui.tiles.corruption.secs:GetText() == "11", "no template: the Hud's remaining shows")
check(degraded("combathud_aura_container") == 1, "the missing template is logged once")
""")

case("retarget_refreshes_the_target_container")(r"""
standard()
__state = mkState({ row = lockRow() })
login()
local c = FS.CombatHud.containers.target
local before = c._updates or 0
fire("PLAYER_TARGET_CHANGED")
check((c._updates or 0) == before + 1, "UpdateAllAuras on a retarget (SetUnit is a no-op for an unchanged token)")
__combat = true
fire("PLAYER_TARGET_CHANGED")
check((c._updates or 0) == before + 2, "also in combat")
""")

# ---------------------------------------------------------------------------------------
# Next tile
# ---------------------------------------------------------------------------------------

case("next_tile_shows_icon_label_and_hides_without_a_next")(r"""
standard()
local CYAN = FS.Theme.COLOR_POWER
__state = mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt", icon = iconOf("shadow_bolt") } })
login()
local n = FS.CombatHud.ui.nextTile
check(n.holder:IsShown(), "next tile shown")
check(n.holder:GetWidth() == 56 and n.holder:GetHeight() == 56, "56 x 56")
check(n.icon._texture == iconOf("shadow_bolt"), "the next spell's icon")
check(n.key:GetText() == "" and not n.key:IsShown(), "no keybind resolved: the top right label is hidden, not the abbreviation")
check(n.lbl:GetText() == "NEXT", "the NEXT caption")
check(n.ring.kind == "cyan" and colorEq(n.ring.edges[1]._vc, CYAN), "cyan border and glow")
check(n.ring.glows.cyan and n.ring.glows.cyan._glow.size == 10, "glow 10, as box-shadow 0 0 10px")
push(mkState({ inCombat = true, row = lockRow() }))
check(not n.holder:IsShown(), "no next, no tile")
push(mkState({ inCombat = true, row = lockRow(), next = { key = "corruption" } }))
check(n.holder:IsShown() and n.icon._texture == iconOf("corruption"), "icon falls back to the spell lookup")
""")

case("next_tile_border_turns_gold_for_a_proc")(r"""
standard()
__state = mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt", icon = iconOf("shadow_bolt"), glow = "gold" } })
login()
local n = FS.CombatHud.ui.nextTile
check(n.ring.kind == "gold" and colorEq(n.ring.edges[1]._vc, GOLD), "gold border when the next spell is the proc")
check(animGroupsUnder(n.ring) == 0, "static: no AnimationGroup on the next ring or its glow hosts (the mockup's .hud-next.gold has no animation)")
push(mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt" } }))
check(n.ring.kind == "cyan", "plain next: cyan")
-- a proc found only through state.procs (overlaySpell) also turns the border gold
push(mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt" }, procs = { { key = "shadow_trance", glow = "gold", active = true } } }))
check(n.ring.kind == "gold", "proc through state.procs")
""")

# ---------------------------------------------------------------------------------------
# Review round 1: gradient fill, ooc style, keybind, DoT timers, deviations, cleanup
# ---------------------------------------------------------------------------------------

case("tile_fill_is_the_baked_gradient_texture_on_tiles_next_and_buffs")(r"""
standard()
__state = mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt" }, buffsMissing = { { key = "pet" } } })
login()
local ui = FS.CombatHud.ui
local function baked(tex) return tex._texture and tostring(tex._texture):find("hud_tile_cut2.tga", 1, true) and tex._color == nil end
for k, t in pairs(ui.tiles) do check(baked(t.bg), "spell tile " .. k .. " uses the baked gradient") end
check(baked(ui.nextTile.bg), "next tile uses the baked gradient")
check(baked(ui.buffTiles.pet.bg), "buff tile uses the baked gradient")
""")

# WoW does not throw for a missing texture file: SetTexture succeeds and GetTexture reads back nil.
# Both ways of "cannot load" must land on the flat fill.
_FLAT_FALLBACK = r"""
standard()
__TEX_FLAG__ = "hud_tile"
__state = mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt" }, buffsMissing = { { key = "pet" } } })
login()
local ui = FS.CombatHud.ui
local function flat(tex) return tex._color and math.abs(tex._color[1] - 0.139) < 0.002 and math.abs(tex._color[3] - 0.2255) < 0.002 end
for k, t in pairs(ui.tiles) do if not t.dim then check(flat(t.bg), "flat fill on tile " .. k) end end
check(flat(ui.nextTile.bg), "flat fill on the next tile")
check(ui.tiles.immolate.dim and ui.tiles.immolate.bg._color[1] == ui.tiles.immolate.bg._color[2], "a dim tile greys the flat fill")
check(flat(ui.buffTiles.pet.bg), "flat fill on the buff tile")
check(FS.CombatHud.IsEnabled() and ui.tiles.corruption.holder:IsShown(), "the HUD still works")
"""
for _flag, _name in (("__texThrows", "tile_fill_falls_back_to_the_flat_colour_when_the_texture_cannot_be_set"),
                     ("__texMissing", "tile_fill_falls_back_to_the_flat_colour_when_the_texture_file_is_missing")):
    case(_name)(_FLAT_FALLBACK.replace("__TEX_FLAG__", _flag))

# SetTexture succeeded, so an unreadable read-back (a throw, or a secret) cannot say the file is
# missing: the baked texture stays, it does not drop to the flat fill.
_KEEP_BAKED = r"""
standard()
__READ_FLAG__ = true
__state = mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt" }, buffsMissing = { { key = "pet" } } })
login()
local ui = FS.CombatHud.ui
local function baked(tex) return tex._texture and tostring(tex._texture):find("hud_tile_cut2.tga", 1, true) and tex._color == nil end
for k, t in pairs(ui.tiles) do check(baked(t.bg), "spell tile " .. k .. " keeps the baked texture") end
check(baked(ui.nextTile.bg), "the next tile keeps the baked texture")
check(baked(ui.buffTiles.pet.bg), "the buff tile keeps the baked texture")
check(FS.CombatHud.IsEnabled() and ui.tiles.corruption.holder:IsShown(), "the HUD still works")
"""
for _flag, _name in (("__texReadThrows", "tile_fill_keeps_the_texture_when_the_read_back_throws"),
                     ("__texReadSecret", "tile_fill_keeps_the_texture_when_the_read_back_is_secret")):
    case(_name)(_KEEP_BAKED.replace("__READ_FLAG__", _flag))

case("out_of_combat_with_no_next_is_the_ooc_style_and_a_next_makes_it_the_opener")(r"""
standard()
__state = mkState({ inCombat = false, row = lockRow() })
login()
local ui = FS.CombatHud.ui
near(ui.row:GetAlpha(), 0.55, "ooc: the row at .55")
check(not ui.nextTile.holder:IsShown(), "ooc: the next tile hidden")
push(mkState({ inCombat = false, row = lockRow(), next = { key = "corruption", icon = iconOf("corruption") } }))
near(ui.row:GetAlpha(), 1, "opener: the row at full opacity")
check(ui.nextTile.holder:IsShown(), "opener: the next tile shown")
push(mkState({ inCombat = true, row = lockRow(), next = { key = "corruption" } }))
near(ui.row:GetAlpha(), 1, "combat with a next: full opacity"); check(ui.nextTile.holder:IsShown(), "combat with a next: shown")
push(mkState({ inCombat = true, row = lockRow() }))
near(ui.row:GetAlpha(), 1, "combat, no next: full opacity"); check(not ui.nextTile.holder:IsShown(), "combat, no next: hidden")
push(mkState({ inCombat = false, row = lockRow(), next = { key = SS } }))
near(ui.row:GetAlpha(), 0.55, "a secret next key is no next: ooc"); check(not ui.nextTile.holder:IsShown(), "and no tile")
push(mkState({ inCombat = SB, row = lockRow() }))
near(ui.row:GetAlpha(), 1, "an unknown combat state reads as in combat")
""")

case("the_ooc_style_dims_the_cast_bars_through_set_rest_alpha_and_only_then")(r"""
standard()
__state = mkState({ inCombat = false, row = lockRow() })
login()
check(__rest[#__rest] == 0.55, "ooc: rest alpha .55: " .. tostring(__rest[#__rest]))
local n = #__rest
push(mkState({ inCombat = false, row = lockRow(), shards = 2 }))
check(#__rest == n, "an unchanged style makes no call")
push(mkState({ inCombat = false, row = lockRow(), next = { key = "corruption" } }))
check(__rest[#__rest] == 1, "opener: full alpha")
push(mkState({ inCombat = true, row = lockRow() }))
check(__rest[#__rest] == 1, "combat: full alpha")
push(mkState({ inCombat = false, row = lockRow() }))
check(__rest[#__rest] == 0.55, "ooc again")
push(mkState({ active = false }))
check(__rest[#__rest] == 1, "a hidden HUD releases the bars")
push(mkState({ inCombat = false, row = lockRow() }))
FS.CombatHud.Disable()
check(__rest[#__rest] == 1, "disable releases the bars")
""")

case("a_castbars_without_set_rest_alpha_is_skipped_and_logged_once")(r"""
standard()
FS.CastBars.SetRestAlpha = nil
__state = mkState({ inCombat = false, row = lockRow() })
login()
push(mkState({ inCombat = false, row = lockRow(), shards = 1 }))
check(FS.CombatHud.ui.tiles.corruption.holder:IsShown(), "the HUD works")
check(degraded("combathud_no_rest_alpha_api") == 1, "logged once: " .. degraded("combathud_no_rest_alpha_api"))
""")

case("ooc_renders_every_tile_plain_with_no_dim_ring_seconds_or_slot_timer_and_the_other_states_restore_them")(r"""
standard()
-- a DoT that is down (dim in combat) and a proc spell that is also the next cast and on cooldown
-- (gold ring and seconds in combat)
local function rows() return lockRow({ [3] = { missing = true }, [5] = { isNext = true, proc = "gold", onCd = true, cdRemaining = 7 } }) end
__state = mkState({ inCombat = false, row = rows() })
login()
local ui = FS.CombatHud.ui
local function dimmed(k) local t = ui.tiles[k]; return t.face:GetAlpha() == 0.45 and t.icon._desat == true and t.bg._desat == true end
local function plain(k)
    local t = ui.tiles[k]
    return t.face:GetAlpha() == 1 and not t.icon._desat and not t.bg._desat and not t.ring:IsShown() and t.secs:GetText() == ""
end
local function slotsShown()
    local n, up = 0, 0
    for _, t in pairs(ui.tiles) do if t.slot then n = n + 1; if t.slot:IsShown() then up = up + 1 end end end
    return n, up
end
-- ooc: no combat and no next cast. The slots exist (built out of combat) and are hidden.
for k in pairs(ui.tiles) do check(plain(k), "ooc: plain 'ready' look on " .. k) end
local n, up = slotsShown()
check(n == 4 and up == 0, "ooc: " .. n .. " DoT slots, " .. up .. " shown (the engine timer would escape the row's dim)")
check(ui.root:GetScript("OnUpdate") == nil, "ooc: no cooldown is counting down")
near(ui.row:GetAlpha(), 0.55, "ooc: the row at .55")
-- the opener (a next cast, out of combat): everything is back
push(mkState({ inCombat = false, row = rows(), next = { key = "corruption" } }))
check(dimmed("immolate"), "opener: a missing DoT is dim")
check(ui.tiles.shadow_bolt.ring:IsShown() and ui.tiles.shadow_bolt.ring.kind == "gold", "opener: the proc ring")
check(ui.tiles.shadow_bolt.secs:GetText() == "7" and ui.root:GetScript("OnUpdate"), "opener: the cooldown seconds count")
n, up = slotsShown()
check(n == 4 and up == 4, "opener: every slot is shown again: " .. up)
-- ooc again, then in combat
push(mkState({ inCombat = false, row = rows() }))
for k in pairs(ui.tiles) do check(plain(k), "ooc again: plain on " .. k) end
n, up = slotsShown(); check(up == 0, "ooc again: slots hidden")
check(ui.root:GetScript("OnUpdate") == nil, "ooc again: the ticker is gone")
push(mkState({ inCombat = true, row = rows() }))
check(dimmed("immolate") and dimmed("shadow_bolt"), "combat: dim states back")
check(ui.tiles.shadow_bolt.ring.kind == "gold" and ui.tiles.shadow_bolt.secs:GetText() == "7", "combat: ring and seconds back")
n, up = slotsShown(); check(up == 4, "combat: slots shown again: " .. up)
-- a plain ooc proc ring and a next ring are gone too
push(mkState({ inCombat = false, row = lockRow({ [1] = { isNext = true }, [2] = { proc = "gold" } }) }))
check(not ui.tiles.corruption.ring:IsShown() and not ui.tiles.bane_agony.ring:IsShown(), "ooc: neither a next ring nor a proc ring")
""")

case("ooc_hides_the_huds_own_dot_seconds_when_there_is_no_slot_and_the_opener_shows_them")(r"""
standard()
__template = false                                  -- no engine timer: the tile's own seconds stand in
__state = mkState({ inCombat = false, row = lockRow() })
login()
local ui = FS.CombatHud.ui
check(ui.tiles.corruption.slot == nil, "no slot")
check(ui.tiles.corruption.secs:GetText() == "" and ui.tiles.siphon.secs:GetText() == "", "ooc: no seconds, not even the Hud's remaining")
check(ui.tiles.immolate.face:GetAlpha() == 1 and not ui.tiles.immolate.icon._desat, "ooc: a missing DoT is not dim (not 0.45 under the row's 0.55)")
push(mkState({ inCombat = false, row = lockRow(), next = { key = "corruption" } }))
check(ui.tiles.corruption.secs:GetText() == "11" and ui.tiles.siphon.secs:GetText() == "22", "opener: the Hud's remaining shows")
check(ui.tiles.immolate.face:GetAlpha() == 0.45, "opener: the missing DoT is dim")
push(mkState({ inCombat = false, row = lockRow() }))
check(ui.tiles.corruption.secs:GetText() == "", "ooc again: cleared")
""")

PRELUDES["bar6_keybind_slots_follow_the_clients_multibar5_page"] = "MULTIBAR_5_ACTIONBAR_PAGE = 15"
case("bar6_keybind_slots_follow_the_clients_multibar5_page")(r"""
standard()
local sb = idOf("shadow_bolt")
C_ActionBar = { FindSpellActionButtons = function(id) return __actionSlots[id] end }
GetBindingKey = function(cmd) return __binds[cmd] end
GetBindingText = function(key) return key end
__state = mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt", icon = iconOf("shadow_bolt") } })
login()
local n = FS.CombatHud.ui.nextTile
check(FS.CombatHud.slotBindings[6].first == 169, "page 15 -> first slot 169, got " .. tostring(FS.CombatHud.slotBindings[6].first))
for _, c in ipairs({ { 169, "MULTIACTIONBAR5BUTTON1" }, { 180, "MULTIACTIONBAR5BUTTON12" } }) do
    __actionSlots = { [sb] = { c[1] } }
    __binds = { [c[2]] = "K" .. c[1] }
    fire("UPDATE_BINDINGS")
    check(n.key:GetText() == "K" .. c[1], "slot " .. c[1] .. " resolves through " .. c[2] .. ": " .. tostring(n.key:GetText()))
end
-- the client-default slots are no longer bar 6 once the page says otherwise
__actionSlots = { [sb] = { 145 } }
__binds = { MULTIACTIONBAR5BUTTON1 = "X" }
fire("UPDATE_BINDINGS")
check(not n.key:IsShown(), "slot 145 is not bar 6 on a page-15 client")
""")

case("next_tile_key_label_is_the_real_keybind_for_every_bar")(r"""
standard()
local sb = idOf("shadow_bolt")
C_ActionBar = { FindSpellActionButtons = function(id) return __actionSlots[id] end }
GetBindingKey = function(cmd) return __binds[cmd] end
local abbrevArg
GetBindingText = function(key, abbrev) abbrevArg = abbrev; return (key:gsub("SHIFT%-", "S-")) end
__state = mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt", icon = iconOf("shadow_bolt") } })
__actionSlots = { [sb] = { 15, 3 } }       -- slot 15 is page 2 (no direct binding), slot 3 is ACTIONBUTTON3
__binds = { ACTIONBUTTON3 = "SHIFT-3" }
login()
local n = FS.CombatHud.ui.nextTile
check(n.key:GetText() == "S-3" and n.key:IsShown(), "the first slot with a binding wins: " .. tostring(n.key:GetText()))
check(abbrevArg == 1, "GetBindingText is asked to abbreviate, as ActionBars.lua does")
check(colorEq(n.key._textColor, FS.Theme.COLOR_POWER), "cyan, the mockup's .hud-next .key")
local cases = { { 1, "ACTIONBUTTON1" }, { 12, "ACTIONBUTTON12" }, { 25, "MULTIACTIONBAR3BUTTON1" }, { 36, "MULTIACTIONBAR3BUTTON12" },
    { 37, "MULTIACTIONBAR4BUTTON1" }, { 49, "MULTIACTIONBAR2BUTTON1" }, { 61, "MULTIACTIONBAR1BUTTON1" },
    { 145, "MULTIACTIONBAR5BUTTON1" }, { 156, "MULTIACTIONBAR5BUTTON12" } }
for _, c in ipairs(cases) do
    __actionSlots = { [sb] = { c[1] } }
    __binds = { [c[2]] = "K" .. c[1] }
    fire("UPDATE_BINDINGS")
    check(n.key:GetText() == "K" .. c[1], "slot " .. c[1] .. " resolves through " .. c[2] .. ": " .. tostring(n.key:GetText()))
end
-- slot 73 is action page 7 (a bonus bar the main bar flips to), no longer bar 6's range
__actionSlots = { [sb] = { 73 } }
__binds = { MULTIACTIONBAR5BUTTON1 = "X" }
fire("UPDATE_BINDINGS")
check(not n.key:IsShown(), "slot 73 (bonus page 7) has no direct binding: " .. tostring(n.key:GetText()))
-- a rebind shows without a new state
__actionSlots = { [sb] = { 156 } }
__binds = { MULTIACTIONBAR5BUTTON12 = "Z" }
fire("UPDATE_BINDINGS")
check(n.key:GetText() == "Z", "refreshed on UPDATE_BINDINGS")
__actionSlots = { [sb] = { 2 } }; __binds = { ACTIONBUTTON2 = "Q" }
fire("ACTIONBAR_SLOT_CHANGED")
check(n.key:GetText() == "Q", "refreshed when the bars change")
""")

case("next_tile_key_label_is_hidden_when_no_keybind_resolves")(r"""
standard()
local sb = idOf("shadow_bolt")
C_ActionBar = { FindSpellActionButtons = function(id) return __actionSlots[id] end }
GetBindingKey = function(cmd) return __binds[cmd] end
GetBindingText = function(key) return key end
__state = mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt" } })
__actionSlots = { [sb] = { 3 } }; __binds = { ACTIONBUTTON3 = "5" }
login()
local n = FS.CombatHud.ui.nextTile
check(n.key:GetText() == "5", "resolved first")
local function hidden(msg) check(n.key:GetText() == "" and not n.key:IsShown(), msg .. ": " .. tostring(n.key:GetText())) end
__actionSlots = {};                    fire("UPDATE_BINDINGS"); hidden("the spell is on no bar")
__actionSlots = { [sb] = { 3 } }; __binds = {}; fire("UPDATE_BINDINGS"); hidden("the slot has no key")
__actionSlots = { [sb] = { 15, 20 } }; __binds = { ACTIONBUTTON3 = "5" }; fire("UPDATE_BINDINGS"); hidden("only slots of a non-main page")
__actionSlots = { [sb] = { 90, 0, -1 } }; fire("UPDATE_BINDINGS"); hidden("slots outside every bar")
__actionSlots = { [sb] = { 3 } }; fire("UPDATE_BINDINGS")
check(n.key:GetText() == "5", "back")
_G.GetActionBarPage = function() return 2 end
fire("UPDATE_BINDINGS"); hidden("the main bar shows another page, so ACTIONBUTTON3 is not that slot")
_G.GetActionBarPage = nil
fire("UPDATE_BINDINGS"); check(n.key:GetText() == "5", "back again")
GetBindingText = function() error("boom: GetBindingText") end
fire("UPDATE_BINDINGS"); hidden("a throwing GetBindingText")
GetBindingText = function(key) return "" end
fire("UPDATE_BINDINGS"); hidden("an empty binding text")
GetBindingText = function(key) return key end
C_ActionBar.FindSpellActionButtons = function() error("boom: Find") end
fire("UPDATE_BINDINGS"); hidden("a throwing FindSpellActionButtons")
C_ActionBar = nil
fire("UPDATE_BINDINGS"); hidden("no C_ActionBar at all")
C_ActionBar = {}
fire("UPDATE_BINDINGS"); hidden("no FindSpellActionButtons")
check(FS.CombatHud.ui.tiles.corruption.holder:IsShown() and n.holder:IsShown(), "the HUD is fine")
""")

case("keybind_lookup_never_touches_a_secret_value")(r"""
standard()
local sb = idOf("shadow_bolt")
GetBindingText = function(key) return key end
__state = mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt" } })
login()
local n = FS.CombatHud.ui.nextTile
C_ActionBar = { FindSpellActionButtons = function() return SB end }       -- a secret table
GetBindingKey = function() return "5" end
fire("UPDATE_BINDINGS"); check(n.key:GetText() == "" and not n.key:IsShown(), "a secret slot list is unknown")
C_ActionBar = { FindSpellActionButtons = function() return { SN, 3 } end }   -- a secret slot, then a plain one
GetBindingKey = function() return SS end                                    -- a secret key
fire("UPDATE_BINDINGS"); check(n.key:GetText() == "" and not n.key:IsShown(), "a secret key is unknown")
GetBindingKey = function() return "5" end
GetBindingText = function() return SS end                                   -- a secret text
fire("UPDATE_BINDINGS"); check(n.key:GetText() == "" and not n.key:IsShown(), "a secret text is unknown")
GetBindingText = function(k) return k end
fire("UPDATE_BINDINGS"); check(n.key:GetText() == "5", "the plain slot after a secret one still resolves")
_G.GetActionBarPage = function() return SN end
fire("UPDATE_BINDINGS"); check(n.key:GetText() == "5", "an unreadable page does not hide the key")
_G.GetActionBarPage = nil
""")

case("keybind_slots_1_to_12_do_not_claim_the_main_bar_key_on_a_vehicle_override_temp_shapeshift_or_bonus_page")(r"""
standard()
local sb = idOf("shadow_bolt")
C_ActionBar = { FindSpellActionButtons = function(id) return __actionSlots[id] end }
GetBindingKey = function(cmd) return __binds[cmd] end
GetBindingText = function(key) return key end
__state = mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt" } })
__actionSlots = { [sb] = { 3 } }; __binds = { ACTIONBUTTON3 = "5" }
login()
local n = FS.CombatHud.ui.nextTile
check(n.key:GetText() == "5", "page 1 resolves")
-- the main bar's slots show another page: ACTIONBUTTON3 fires THAT page's third slot, not slot 3.
-- Same switch order and index fallbacks as ActionBars.lua's CurrentPage.
local pages = { { "HasVehicleActionBar", "GetVehicleBarIndex" }, { "HasOverrideActionBar", "GetOverrideBarIndex" },
                { "HasTempShapeshiftActionBar", "GetTempShapeshiftBarIndex" }, { "HasBonusActionBar", "GetBonusBarIndex" } }
for _, p in ipairs(pages) do
    _G[p[1]] = function() return true end
    fire("UPDATE_BINDINGS")
    check(n.key:GetText() == "" and not n.key:IsShown(), p[1] .. ": slot 3 is not the main bar key (no index function)")
    _G[p[2]] = function() return 9 end
    fire("UPDATE_BINDINGS")
    check(n.key:GetText() == "" and not n.key:IsShown(), p[1] .. ": slot 3 is not the main bar key (with an index)")
    _G[p[1]] = function() return false end
    fire("UPDATE_BINDINGS")
    check(n.key:GetText() == "5", p[1] .. " false: the main bar again")
    _G[p[1]], _G[p[2]] = nil, nil
end
-- an unreadable check is not "active", and the other bars are unaffected by a special page
_G.HasBonusActionBar = function() return SB end
fire("UPDATE_BINDINGS"); check(n.key:GetText() == "5", "a secret bar check does not hide the key")
_G.HasBonusActionBar = function() return true end
__actionSlots = { [sb] = { 3, 25 } }; __binds = { ACTIONBUTTON3 = "5", MULTIACTIONBAR3BUTTON1 = "F" }
fire("UPDATE_BINDINGS"); check(n.key:GetText() == "F", "slot 25 still resolves on a bonus page: " .. tostring(n.key:GetText()))
_G.HasBonusActionBar = nil
""")

case("a_special_bar_that_is_active_on_page_1_still_claims_the_main_bar_key")(r"""
standard()
local sb = idOf("shadow_bolt")
C_ActionBar = { FindSpellActionButtons = function(id) return __actionSlots[id] end }
GetBindingKey = function(cmd) return __binds[cmd] end
GetBindingText = function(key) return key end
__state = mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt" } })
__actionSlots = { [sb] = { 1, 12 } }; __binds = { ACTIONBUTTON1 = "Q", ACTIONBUTTON12 = "Z" }
login()
local n = FS.CombatHud.ui.nextTile
for _, p in ipairs({ { "HasVehicleActionBar", "GetVehicleBarIndex" }, { "HasOverrideActionBar", "GetOverrideBarIndex" },
                     { "HasTempShapeshiftActionBar", "GetTempShapeshiftBarIndex" }, { "HasBonusActionBar", "GetBonusBarIndex" } }) do
    _G[p[1]] = function() return true end
    _G[p[2]] = function() return 1 end
    fire("UPDATE_BINDINGS")
    check(n.key:GetText() == "Q", p[1] .. " active on page 1: slot 1 is ACTIONBUTTON1: " .. tostring(n.key:GetText()))
    __actionSlots = { [sb] = { 12 } }
    fire("UPDATE_BINDINGS")
    check(n.key:GetText() == "Z", p[1] .. " active on page 1: slot 12 is ACTIONBUTTON12: " .. tostring(n.key:GetText()))
    __actionSlots = { [sb] = { 1, 12 } }
    _G[p[1]], _G[p[2]] = nil, nil
end
""")

case("the_special_bar_checks_run_in_order_and_the_first_active_ones_index_is_the_page")(r"""
standard()
local sb = idOf("shadow_bolt")
C_ActionBar = { FindSpellActionButtons = function(id) return __actionSlots[id] end }
GetBindingKey = function(cmd) return __binds[cmd] end
GetBindingText = function(key) return key end
__state = mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt" } })
__actionSlots = { [sb] = { 3 } }; __binds = { ACTIONBUTTON3 = "5" }
login()
local n = FS.CombatHud.ui.nextTile
local pages = { { "HasVehicleActionBar", "GetVehicleBarIndex" }, { "HasOverrideActionBar", "GetOverrideBarIndex" },
                { "HasTempShapeshiftActionBar", "GetTempShapeshiftBarIndex" }, { "HasBonusActionBar", "GetBonusBarIndex" } }
-- for each bar i: it is active on page 1 while every LATER bar is active on page 7. The earlier
-- one wins, so the main bar key resolves; a swapped pair or a dropped bar would read page 7.
for i = 1, #pages - 1 do
    for j = i, #pages do
        _G[pages[j][1]] = function() return true end
        _G[pages[j][2]] = function() return j == i and 1 or 7 end
    end
    fire("UPDATE_BINDINGS")
    check(n.key:GetText() == "5", pages[i][1] .. " wins over the later bars: " .. tostring(n.key:GetText()))
    for j = i, #pages do _G[pages[j][1]], _G[pages[j][2]] = nil, nil end
end
-- the index function's value is the page, not the fallback: page 7 hides the key, page 1 shows it,
-- whatever the default for that bar is
for _, p in ipairs(pages) do
    _G[p[1]] = function() return true end
    _G[p[2]] = function() return 7 end
    fire("UPDATE_BINDINGS"); check(n.key:GetText() == "", p[1] .. " on page 7: no main bar key")
    _G[p[2]] = function() return 1 end
    fire("UPDATE_BINDINGS"); check(n.key:GetText() == "5", p[1] .. " on page 1: the main bar key")
    _G[p[1]], _G[p[2]] = nil, nil
end
""")

case("a_has_bar_check_that_returns_a_plain_number_counts_as_active")(r"""
standard()
local sb = idOf("shadow_bolt")
C_ActionBar = { FindSpellActionButtons = function(id) return __actionSlots[id] end }
GetBindingKey = function(cmd) return __binds[cmd] end
GetBindingText = function(key) return key end
__state = mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt" } })
__actionSlots = { [sb] = { 3 } }; __binds = { ACTIONBUTTON3 = "5" }
login()
local n = FS.CombatHud.ui.nextTile
-- ActionBars.lua's CurrentPage tests plain truthiness, so 1 (not only true) is "active"
_G.HasBonusActionBar = function() return 1 end
fire("UPDATE_BINDINGS")
check(n.key:GetText() == "", "HasBonusActionBar returning 1 is active (bonus page 7): " .. tostring(n.key:GetText()))
_G.HasBonusActionBar = function() return nil end
fire("UPDATE_BINDINGS"); check(n.key:GetText() == "5", "nil is not active")
_G.HasBonusActionBar = function() return false end
fire("UPDATE_BINDINGS"); check(n.key:GetText() == "5", "false is not active")
_G.HasBonusActionBar = nil
""")

case("a_rebind_or_a_moved_spell_refreshes_only_the_next_tile_not_the_whole_hud")(r"""
standard()
local sb = idOf("shadow_bolt")
C_ActionBar = { FindSpellActionButtons = function(id) return __actionSlots[id] end }
GetBindingKey = function(cmd) return __binds[cmd] end
GetBindingText = function(key) return key end
__state = mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt" } })
__actionSlots = { [sb] = { 3 } }; __binds = { ACTIONBUTTON3 = "5" }
login()
local ui = FS.CombatHud.ui
check(ui.nextTile.key:GetText() == "5", "resolved")
-- A full render writes the row's alpha every time; a next-tile refresh must not touch the row.
for i, e in ipairs({ "UPDATE_BINDINGS", "ACTIONBAR_SLOT_CHANGED", "ACTIONBAR_PAGE_CHANGED" }) do
    ui.row:SetAlpha(0.9)
    __binds = { ACTIONBUTTON3 = "K" .. i }
    fire(e)
    check(ui.nextTile.key:GetText() == "K" .. i and ui.nextTile.key:IsShown(), e .. " refreshes the label: " .. tostring(ui.nextTile.key:GetText()))
    near(ui.row:GetAlpha(), 0.9, e .. " did not re-render the row")
end
-- nothing to refresh when the HUD is off or hidden, and nothing throws
push(mkState({ active = false }))
fire("UPDATE_BINDINGS"); check(not ui.nextTile.holder:IsShown(), "a hidden HUD stays hidden")
FS.CombatHud.Disable()
fire("UPDATE_BINDINGS")
""")

case("the_keybind_lookup_is_cached_per_spell_and_dropped_by_every_refresh_event")(r"""
standard()
local sb = idOf("shadow_bolt")
local finds = 0
C_ActionBar = { FindSpellActionButtons = function(id) finds = finds + 1; return __actionSlots[id] end }
GetBindingKey = function(cmd) return __binds[cmd] end
GetBindingText = function(key) return key end
__actionSlots = { [sb] = { 3 } }; __binds = { ACTIONBUTTON3 = "5" }
__state = mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt" } })
login()
local n = FS.CombatHud.ui.nextTile
local first = finds
check(first >= 1, "the first render asked the bars")
push(mkState({ inCombat = true, row = lockRow(), shards = 1, next = { key = "shadow_bolt" } }))
check(finds == first, "a second render of the same spell reads the cache: " .. finds .. " vs " .. first)
-- a spell with NO key is cached too (the miss), not looked up on every render
push(mkState({ inCombat = true, row = lockRow(), next = { key = "corruption" } }))
local miss = finds
check(miss > first and n.key:GetText() == "", "an unbound spell resolves to no label")
push(mkState({ inCombat = true, row = lockRow(), shards = 2, next = { key = "corruption" } }))
check(finds == miss, "the miss is cached: " .. finds .. " vs " .. miss)
-- every refresh event drops it: change the world, send the event, and the label follows
-- (LEARNED_SPELL_IN_TAB is not registered: the client has no such event, SPELLS_CHANGED covers it)
push(mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt" } }))
check(n.key:GetText() == "5", "back on Shadow Bolt")
local n2 = 0
for _, e in ipairs({ "SPELLS_CHANGED", "PLAYER_LEVEL_UP", "UPDATE_BINDINGS", "ACTIONBAR_SLOT_CHANGED", "ACTIONBAR_PAGE_CHANGED" }) do
    n2 = n2 + 1
    __binds = { ACTIONBUTTON3 = "E" .. n2 }
    fire(e)
    check(n.key:GetText() == "E" .. n2, e .. " drops the cached key: " .. tostring(n.key:GetText()))
end
-- PLAYER_ENTERING_WORLD drops it too (the bars may have been empty at the last look); it does not
-- re-render, so the next state shows the new key
__binds = { ACTIONBUTTON3 = "W" }
push(mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt" } }))
check(n.key:GetText() == "E" .. n2, "stale until something drops the cache: " .. tostring(n.key:GetText()))
fire("PLAYER_ENTERING_WORLD")
push(mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt" } }))
check(n.key:GetText() == "W", "PLAYER_ENTERING_WORLD dropped the cache: " .. tostring(n.key:GetText()))
""")

case("a_binding_key_that_is_not_a_non_empty_string_is_no_key")(r"""
standard()
local sb = idOf("shadow_bolt")
C_ActionBar = { FindSpellActionButtons = function(id) return __actionSlots[id] end }
local textCalls = 0
GetBindingText = function() textCalls = textCalls + 1; return "TXT" end       -- would "resolve" any key it is handed
__actionSlots = { [sb] = { 3 } }
__state = mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt" } })
GetBindingKey = function() return "K" end
login()
local n = FS.CombatHud.ui.nextTile
check(n.key:GetText() == "TXT", "a real key resolves")
for _, bad in ipairs({ 7, true, {}, "" }) do
    GetBindingKey = function() return bad end
    textCalls = 0
    fire("UPDATE_BINDINGS")
    check(textCalls == 0, "GetBindingText is not asked about a " .. type(bad) .. " key: " .. textCalls)
    check(n.key:GetText() == "" and not n.key:IsShown(), "and the label is hidden for a " .. type(bad) .. " key")
end
""")

case("a_dot_tile_without_a_slot_shows_the_hud_remaining_when_it_is_plain")(r"""
standard()
__combat = true                                   -- no container can be built in combat
__state = mkState({ inCombat = true, row = lockRow() })
login()
local ui = FS.CombatHud.ui
local function secs(k) return ui.tiles[k].secs:GetText() end
check(ui.tiles.corruption.slot == nil, "no slot")
check(secs("corruption") == "11" and secs("bane_agony") == "19" and secs("siphon") == "22", "the Hud's remaining: " .. secs("corruption") .. "," .. secs("bane_agony") .. "," .. secs("siphon"))
check(secs("immolate") == "" and secs("shadow_bolt") == "", "a missing DoT and a plain cast have no timer")
push(mkState({ inCombat = true, row = lockRow({ [1] = { remaining = SN } }) }))
check(secs("corruption") == "", "a secret remaining shows nothing")
push(mkState({ inCombat = true, row = lockRow({ [1] = { remaining = "11" } }) }))
check(secs("corruption") == "", "a non-number shows nothing")
push(mkState({ inCombat = true, row = lockRow({ [1] = { remaining = 0 } }) }))
check(secs("corruption") == "", "nothing at zero")
push(mkState({ inCombat = true, row = lockRow({ [1] = { remaining = 100 } }) }))
check(secs("corruption") == "2m", "minutes read as Nm")
push(mkState({ inCombat = true, row = lockRow({ [1] = { remaining = 11, missing = true } }) }))
check(secs("corruption") == "", "a DoT the Hud calls missing shows no timer")
-- once a slot exists the engine owns the timer
__combat = false
fire("PLAYER_REGEN_ENABLED")
check(ui.tiles.corruption.slot ~= nil, "slot built")
push(mkState({ inCombat = true, row = lockRow() }))
check(secs("corruption") == "" and secs("siphon") == "", "with a slot the Lua timer is silent")
""")

case("a_dot_slots_timer_and_the_tiles_own_cooldown_text_never_share_a_corner", "PRIEST")(r"""
learnAll(); useCastBars(0, -317)
__combat = true
local function rows() return { rowEntry("sw_pain", { missing = false, remaining = 9 }), rowEntry("dplague", { missing = true, onCd = true, cdRemaining = 20 }),
    rowEntry("mind_blast", { onCd = true, cdRemaining = 3 }) } end
__state = mkState({ inCombat = true, row = rows() })
login()
local ui = FS.CombatHud.ui
local function corner(fs) return fs._points.BOTTOMRIGHT and "R" or (fs._points.BOTTOMLEFT and "L" or "?") end
check(ui.tiles.dplague.slot == nil, "no slot in combat")
check(corner(ui.tiles.dplague.secs) == "R", "without a slot the tile's seconds sit bottom right")
__combat = false
fire("PLAYER_REGEN_ENABLED")
push(mkState({ inCombat = true, row = rows() }))
check(ui.tiles.dplague.slot ~= nil, "slot built")
local slotText = ui.tiles.dplague.slot._durationText
check(corner(slotText) == "R", "the engine's DoT timer is bottom right, the mockup's .secs corner")
do -- the engine's DoT timer clears the cut corner too (same u + v >= chamfer + stroke rule as the tile's own seconds)
    local p = slotText._points.BOTTOMRIGHT
    local c = FS.Theme.SnapCut(6)
    check(p and -p.x + p.y >= c + 1, "the slot timer clears the cut corner: u + v = " .. tostring(p and (-p.x + p.y)) .. " vs " .. (c + 1))
end
check(corner(ui.tiles.dplague.secs) == "L", "the tile's own cooldown seconds move to bottom left beside a live slot")
check(ui.tiles.dplague.secs:GetText() == "20", "and still read")
check(corner(ui.tiles.mind_blast.secs) == "R", "a tile with no slot keeps the mockup corner")
do -- the bottom right seconds clear the cut corner: the label box corner (u from the right, v from the bottom) sits past the chamfer line u + v = chamfer + stroke
    local p = ui.tiles.mind_blast.secs._points.BOTTOMRIGHT
    local c = FS.Theme.SnapCut(6)
    check(p and p.rel == ui.tiles.mind_blast.holder and -p.x + p.y >= c + 1, "the seconds label clears the cut corner: u + v = " .. tostring(p and (-p.x + p.y)) .. " vs " .. (c + 1))
end
check(ui.tiles.mind_blast.secs:GetText() == "3", "cooldown text")
""")

case("seconds_text_is_outlined_mono_like_the_mockups_secs")(r"""
standard()
__state = mkState({ inCombat = true, row = lockRow({ [5] = { onCd = true, cdRemaining = 8 } }) })
login()
local f = FS.CombatHud.ui.tiles.shadow_bolt.secs._font
check(f[3] == "OUTLINE" and f[1] == FS.Theme.FONT_MONO and f[2] == 11, "11 pt mono with the OUTLINE flag")
""")

case("dim_greys_the_whole_tile_including_the_border")(r"""
standard()
local B = FS.Theme.COLOR_BORDER
__state = mkState({ inCombat = true, row = lockRow({ [3] = { missing = true } }) })
login()
local ui = FS.CombatHud.ui
local t = ui.tiles.immolate
local function grey(c) return math.abs(c[1] - c[2]) < 1e-6 and math.abs(c[2] - c[3]) < 1e-6 end
for _, e in ipairs(t.border) do check(grey(e._vc), "dim border edge is grey") end
local want = 0.2126 * B[1] + 0.7152 * B[2] + 0.0722 * B[3]
near(t.border[1]._vc[1], want, "CSS grayscale(1) luminance", 1e-6)
check(t.bg._desat == true and t.icon._desat == true, "fill and icon desaturated")
check(grey(t.abbr._textColor), "the label too")
local up = ui.tiles.corruption
check(colorEq(up.border[1]._vc, B) and not up.bg._desat and not up.icon._desat, "a lit tile keeps its colours")
push(mkState({ inCombat = true, row = lockRow({ [3] = { missing = false, remaining = 5 } }) }))
check(colorEq(t.border[1]._vc, B) and not t.bg._desat and not t.icon._desat, "undimmed: colours back")
check(colorEq(t.abbr._textColor, FS.Theme.COLOR_TEXT_WHITE) or t.abbr._textColor[1] > 0.8, "label colour back")
""")

case("buff_tiles_pulse_border_and_glow_exactly_like_the_mockups_hudpulse")(r"""
standard()
local PINK = FS.Theme.COLOR_HEALTH
__state = mkState({ inCombat = false, row = lockRow(), buffsMissing = { { key = "demon_armor", icon = iconOf("demon_armor") } } })
login()
local a = FS.CombatHud.ui.buffTiles.demon_armor
local pb = a.pulse.anims[1]
check(a.pulse.looping == "BOUNCE" and a.pulse.playing, "the border pulse loops back and forth")
near(pb.duration, MU.BUFF_PULSE_S, "duration from the mockup"); near(pb.from, MU.BUFF_PULSE_FROM, "border alpha from"); near(pb.to, 1, "to the full pink")
check(a.glowHost and a.glowHost._glow, "a glow host")
local g = a.glowHost._glow
check(colorEq({ g.r, g.g, g.b }, PINK) and g.size == MU.BUFF_GLOW, "pink glow of the mockup's size: " .. tostring(g.size))
local pg = a.glowPulse.anims[1]
check(a.glowPulse.playing and a.glowPulse.looping == "BOUNCE", "the glow pulses with it")
near(pg.duration, MU.BUFF_PULSE_S, "same duration"); near(pg.from, 0, "from no shadow"); near(pg.to, 1, "to the full glow")
push(mkState({ inCombat = false, row = lockRow(), buffsMissing = {} }))
check(not a.pulse.playing and not a.glowPulse.playing, "both stop with the tile")
""")

case("hiding_everything_also_releases_the_target_container_and_a_returning_state_revives_it")(r"""
standard()
__state = mkState({ inCombat = false, row = lockRow() })
login()
local c = FS.CombatHud.containers.target
check(c._enabled and c._shown, "live with DoT slots")
push(mkState({ active = false }))
check(c._enabled == false and c._shown == false, "HideAll turns the target container off")
push(mkState({ inCombat = false, row = lockRow() }))
check(c._enabled == true and c._shown == true, "a returning state turns it on again")
""")

case("a_dropped_row_tile_hides_its_slot_and_a_returning_tile_shows_it_again")(r"""
standard()
__state = mkState({ inCombat = true, row = lockRow() })
login()
local ui = FS.CombatHud.ui
local slot = ui.tiles.siphon.slot
check(slot and slot:IsShown(), "siphon has a live slot")
local row = lockRow(); table.remove(row, 4)
push(mkState({ inCombat = true, row = row }))
check(not ui.tiles.siphon.holder:IsShown(), "the tile is dropped")
check(slot:IsShown() == false, "and so is its slot frame (it hangs off the container, not the tile)")
check(ui.tiles.corruption.slot:IsShown(), "the other slots stay")
push(mkState({ inCombat = true, row = lockRow() }))
check(slot:IsShown() == true, "back with its tile")
push(mkState({ active = false }))
push(mkState({ inCombat = true, row = lockRow() }))
check(slot:IsShown() == true, "and after a full hide")
""")

case("a_slot_attached_to_a_tile_that_is_not_in_the_row_stays_hidden")(r"""
standard()
__combat = true                                      -- no slots yet
__state = mkState({ inCombat = true, row = lockRow() })
login()
local ui = FS.CombatHud.ui
local row = lockRow(); table.remove(row, 4)           -- Siphon Life leaves the row (its tile is hidden, still without a slot)
push(mkState({ inCombat = true, row = row }))
check(not ui.tiles.siphon.holder:IsShown() and ui.tiles.siphon.slot == nil, "siphon is dropped and has no slot")
__combat = false
fire("PLAYER_REGEN_ENABLED")                            -- BuildPending attaches a slot to EVERY dot tile
local c = FS.CombatHud.containers.target
local stray = ui.tiles.siphon.slot
check(stray and c._slots.dot_siphon, "BuildPending built a slot for the dropped tile")
check(stray:IsShown() == false, "and it stays hidden with its tile (a floating timer on an empty spot)")
check(ui.tiles.corruption.slot:IsShown(), "a tile still in the row keeps its slot shown")
push(mkState({ inCombat = true, row = lockRow() }))
check(stray:IsShown() == true, "back with its tile")
""")

case("a_slot_attached_by_regen_while_the_last_state_is_ooc_stays_hidden")(r"""
standard()
__combat = true                                      -- no slots yet, and the state is ooc (no combat, no next)
__state = mkState({ inCombat = false, row = lockRow() })
login()
local ui = FS.CombatHud.ui
check(ui.tiles.corruption.holder:IsShown() and ui.tiles.corruption.slot == nil, "the tile is up, with no slot")
__combat = false
fire("PLAYER_REGEN_ENABLED")                            -- BuildPending attaches the slots, no render follows
local s = ui.tiles.corruption.slot
check(s, "BuildPending built the slot")
check(s:IsShown() == false, "it stays hidden: the ooc look hides every engine timer")
for k, t in pairs(ui.tiles) do check(t.slot == nil or t.slot:IsShown() == false, "ooc: the slot of " .. k .. " is hidden") end
push(mkState({ inCombat = true, row = lockRow() }))
check(s:IsShown() == true, "combat shows it again")
""")

case("the_cooldown_tick_allocates_nothing_per_tick")(r"""
standard()
__now = 1000
if jit then jit.off() end            -- a compiled trace is itself a collectable object and would count as growth
__state = mkState({ inCombat = true, row = lockRow({ [5] = { onCd = true, cdRemaining = 300 }, [3] = { onCd = true, missing = true, cdRemaining = 250 } }) })
login()
local ui = FS.CombatHud.ui
local onUpdate = ui.root:GetScript("OnUpdate")
check(onUpdate, "ticking")
local function state() return mkState({ inCombat = true, row = lockRow({ [5] = { onCd = true, cdRemaining = 300 }, [3] = { onCd = true, missing = true, cdRemaining = 250 } }) }) end
for i = 1, 1000 do __now = __now + 0.1; onUpdate(ui.root, 0.1) end     -- warm: every string it needs is cached
__now = 1000
push(state())
onUpdate = ui.root:GetScript("OnUpdate")
collectgarbage("collect"); collectgarbage("stop")
local before = collectgarbage("count")
for i = 1, 1000 do __now = __now + 0.1; onUpdate(ui.root, 0.1) end
local grown = collectgarbage("count") - before
collectgarbage("restart")
check(grown < 3, "1000 ticks allocated " .. grown .. " KB (a table or a string per tick would be 50 KB or more)")
check(ui.tiles.shadow_bolt.secs:GetText() ~= "", "and it still counted")
""")

# ---------------------------------------------------------------------------------------
# Shards
# ---------------------------------------------------------------------------------------

case("shard_diamonds_one_per_shard_and_hidden_for_nil_zero_and_other_classes")(r"""
standard()
local TINT = FS.Theme.COLOR_BORDER
__state = mkState({ inCombat = true, row = lockRow(), shards = 4 })
login()
local ui = FS.CombatHud.ui
local shown = 0
for _, d in ipairs(ui.diamonds) do if d:IsShown() then shown = shown + 1 end end
check(shown == 4, "four shards, four diamonds: " .. shown)
check(ui.shards:IsShown(), "row shown")
near(ui.shards:GetWidth(), 4 * 10 + 3 * 3, "row width")
check(colorEq(ui.diamonds[1]._vc, TINT), "violet diamonds")
check(ui.diamonds[1]._texture and ui.diamonds[1]._texture:find("hud_diamond", 1, true), "the diamond texture")
push(mkState({ inCombat = true, row = lockRow(), shards = 2 }))
shown = 0; for _, d in ipairs(ui.diamonds) do if d:IsShown() then shown = shown + 1 end end
check(shown == 2, "down to two")
for _, v in ipairs({ 0, -1 }) do
    push(mkState({ inCombat = true, row = lockRow(), shards = v }))
    check(not ui.shards:IsShown(), "hidden at " .. v)
end
push(mkState({ inCombat = true, row = lockRow(), shards = nil }))
check(not ui.shards:IsShown(), "hidden at nil")
push(mkState({ inCombat = true, row = lockRow(), shards = 99 }))
shown = 0; for _, d in ipairs(ui.diamonds) do if d:IsShown() then shown = shown + 1 end end
check(shown == 20, "a huge stack is clamped to what fits the column: " .. shown)
check(ui.shards:GetWidth() <= 268, "the row never widens the HUD column")
""")

case("a_class_without_shards_never_shows_the_row", "PRIEST")(r"""
learnAll(); useCastBars(0, -317)
__state = mkState({ inCombat = true, row = { rowEntry("sw_pain", { missing = false }) }, shards = 5 })
login()
check(not FS.CombatHud.ui.shards:IsShown(), "a priest profile has no shard resource")
""")

# ---------------------------------------------------------------------------------------
# Buffs
# ---------------------------------------------------------------------------------------

case("out_of_combat_a_tile_per_missing_buff_centred_with_a_pulsing_pink_border")(r"""
standard()
local PINK = FS.Theme.COLOR_HEALTH
__state = mkState({ inCombat = false, row = lockRow(), buffsMissing = {
    { key = "demon_armor", icon = iconOf("demon_armor") }, { key = "pet", icon = 4242 } } })
login()
local ui = FS.CombatHud.ui
check(ui.buffs:IsShown(), "buff row shown")
local a, b = ui.buffTiles.demon_armor, ui.buffTiles.pet
check(a.holder:IsShown() and b.holder:IsShown(), "a tile per missing buff")
check(a.holder:GetWidth() == 24 and a.holder:GetHeight() == 24, "24 x 24")
check(a.icon._texture == iconOf("demon_armor") and b.icon._texture == 4242, "icons from buffsMissing")
check(colorEq(a.border[1]._vc, PINK), "pink border")
check(a.pulse and a.pulse.playing, "the border pulses (hudpulse)")
local ra, rb = rect(a.holder), rect(b.holder)
near(rb.l - ra.r, 6, "6 unit gap")
near((ra.l + rb.r) / 2, 0, "centred on the column")
-- fixed: a buff that is back disappears
push(mkState({ inCombat = false, row = lockRow(), buffsMissing = { { key = "pet" } } }))
check(not a.holder:IsShown() and b.holder:IsShown(), "only the still-missing buff remains")
push(mkState({ inCombat = false, row = lockRow(), buffsMissing = {} }))
check(not ui.buffs:IsShown(), "nothing missing, no row")
check(not a.pulse.playing and not b.pulse.playing, "pulse stopped with the tile")
""")

case("out_of_combat_the_player_container_is_disabled_so_no_stray_aura_icons")(r"""
standard()
__state = mkState({ inCombat = false, row = lockRow(), buffsMissing = { { key = "demon_armor" } } })
login()
local p = FS.CombatHud.containers.player
check(p, "a player container exists for the occlusion trick")
check(p._unit == "player", "on unit player")
check(p._enabled == false and p._shown == false, "disabled and hidden out of combat")
""")

case("in_combat_every_tracked_buff_gets_a_warning_tile_behind_a_player_aura_slot")(r"""
standard()
__state = mkState({ inCombat = false, row = lockRow() })
login()
push(mkState({ inCombat = true, row = lockRow() }))     -- the Hud reports nothing missing: auras are unreadable
local ui = FS.CombatHud.ui
local p = FS.CombatHud.containers.player
check(p._enabled == true and p._shown == true, "the player container is live in combat")
-- the warlock's aura buff is Demon Armor; the pet is a pet check, not an aura
local slot = p._slots.buff_demon_armor
check(slot, "slot for Demon Armor")
check(slot.filter == "HELPFUL", "helpful filter: " .. tostring(slot.filter))
check(slot.ids[687] and slot.ids[696] and slot.ids[706] and slot.ids[11735], "Demon Skin and Demon Armor ranks")
check(not p._slots.buff_pet, "no slot for a pet check")
local warn = ui.buffTiles.demon_armor
check(warn.holder:IsShown(), "the warning tile is up in combat: it is the thing behind the aura icon")
check(warn.slot == slot.frame, "the tile owns its slot")
-- OCCLUSION: the warning is BEHIND the slot. The aura icon (present buff) covers it, an absent buff
-- leaves it showing.
check(warn.holder:GetFrameLevel() < slot.frame:GetFrameLevel(), "warning frame level " .. warn.holder:GetFrameLevel() .. " is below the aura slot's " .. slot.frame:GetFrameLevel())
local w, s = rect(warn.holder), rect(slot.frame)
near(w.l, s.l, "slot covers the warning left"); near(w.b, s.b, "bottom"); near(w.r, s.r, "right"); near(w.t, s.t, "top")
local has = {}
for _, n in ipairs(slot.frame._order) do has[n] = true end
check(has.SetIcon and slot.frame._icon, "the slot draws the aura's icon (opaque, so it hides the warning)")
check(slot.frame._icon._alpha == 1, "fully opaque")
-- the cover is cut too: a cut tile fill under the icon (so the warning tile's border cannot show
-- through a present buff), the icon seated inside the chamfer, a cut outline border, no flat strips
local parts = allShownDescendants(slot.frame)
local fill, outline, flat
for _, r in ipairs(parts) do
    if r._texture and tostring(r._texture):find("hud_tile_cut2.tga", 1, true) then fill = r end
    if r._texture and tostring(r._texture):find("slice_cut2_outline_c4", 1, true) then outline = r end
    if r._color then flat = r end
end
check(fill, "the cover has the cut tile fill")
check(outline and outline._slice == 4, "the cover border is the c4 cut outline")
check(flat == nil, "no flat colour strip on the cover")
local tl = slot.frame._icon._points.TOPLEFT
check(tl and tl.x >= 2 and -tl.y >= 2, "the cover icon is inset ceil(4 / 2) so its corner stays inside the cut")
check(slot.frame._order[1] == "SetMouseMotionEnabled", "mouse off first on the buff slot too")
-- the warning has to be above everything else of ours that could draw over it
check(slot.frame:GetFrameLevel() > ui.buffs:GetFrameLevel(), "slot above the buff row")
""")

case("in_combat_unknown_spells_are_not_tracked")(r"""
standard()
forget("demon_armor")
__state = mkState({ inCombat = false, row = lockRow() })
login()
push(mkState({ inCombat = true, row = lockRow() }))
check(FS.CombatHud.containers.player == nil or FS.CombatHud.containers.player._slots.buff_demon_armor == nil, "no slot for a spell the player does not know")
local t = FS.CombatHud.ui.buffTiles.demon_armor
check(t == nil or not t.holder:IsShown(), "and no false 'missing' warning for it")
""")

case("in_combat_form_and_pet_checks_come_from_buffsmissing_without_a_slot", "PRIEST")(r"""
learnAll(); useCastBars(0, -317)
__state = mkState({ inCombat = false, row = { rowEntry("sw_pain", { missing = false }) } })
login()
-- Shadowform is a form check (plain in combat): the Hud reports it; fortitude and inner fire are auras
push(mkState({ inCombat = true, row = { rowEntry("sw_pain", { missing = false }) }, buffsMissing = { { key = "shadowform", icon = iconOf("shadowform") } } }))
local ui = FS.CombatHud.ui
local p = FS.CombatHud.containers.player
check(p._slots.buff_fort and p._slots.buff_inner_fire, "Fortitude and Inner Fire are occluded in combat even though the profile marks them oocOnly")
check(p._slots.buff_fort.ids[1243] and p._slots.buff_fort.ids[21562] and p._slots.buff_fort.ids[10938], "Fortitude ranks and Prayer of Fortitude")
check(not p._slots.buff_shadowform, "a form check has no slot")
check(ui.buffTiles.shadowform.holder:IsShown() and ui.buffTiles.shadowform.slot == nil, "Shadowform shows straight from buffsMissing")
check(ui.buffTiles.fort.holder:IsShown() and ui.buffTiles.inner_fire.holder:IsShown(), "the two aura buffs have their tiles up behind the slots")
local n = 0; for _, f in ipairs({ ui.buffTiles.shadowform, ui.buffTiles.fort, ui.buffTiles.inner_fire }) do if f.holder:IsShown() then n = n + 1 end end
check(n == 3, "three tiles")
local w = rect(ui.buffs); near(w.r - w.l, 3 * 24 + 2 * 6, "centred row of three")
-- the Hud later reports the form restored
push(mkState({ inCombat = true, row = { rowEntry("sw_pain", { missing = false }) }, buffsMissing = {} }))
check(not ui.buffTiles.shadowform.holder:IsShown(), "Shadowform tile gone")
""")

case("without_a_player_container_combat_shows_only_what_the_hud_reports")(r"""
standard()
__acThrows = true
__state = mkState({ inCombat = false, row = lockRow() })
login()
push(mkState({ inCombat = true, row = lockRow(), buffsMissing = { { key = "pet" } } }))
local ui = FS.CombatHud.ui
check(not (ui.buffTiles.demon_armor and ui.buffTiles.demon_armor.holder:IsShown()), "no occlusion available: a tile that would always be 'missing' must not show")
check(ui.buffTiles.pet.holder:IsShown(), "what the Hud reports still shows")
""")

case("buff_slots_are_only_built_out_of_combat")(r"""
standard()
__combat = true
__state = mkState({ inCombat = true, row = lockRow() })
login()
check(__acAttempts == 0, "no container in combat")
local t = FS.CombatHud.ui.buffTiles.demon_armor
check(t == nil or not t.holder:IsShown(), "no slot yet, so no warning tile in combat")
__combat = false
fire("PLAYER_REGEN_ENABLED")
check(FS.CombatHud.containers.player and FS.CombatHud.containers.player._slots.buff_demon_armor, "built when combat ends")
""")

# ---------------------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------------------

case("secret_values_in_the_state_neither_throw_nor_get_touched")(r"""
standard()
local st = mkState({
    inCombat = true, shards = SN,
    row = {
        { key = SS, icon = 1 },
        { key = "corruption", icon = SN, missing = SB, remaining = SN, onCd = SB, cdRemaining = SN, proc = SS, isNext = SB },
        { key = "immolate", icon = iconOf("immolate"), missing = false, onCd = true, cdRemaining = SN },
        { key = "siphon", icon = iconOf("siphon"), onCd = true, cdRemaining = 5 },
    },
    next = { key = SS, icon = SN, glow = SS },
    buffsMissing = { { key = SS, icon = SN }, { key = "pet", icon = SN } },
    procs = { { key = SS, glow = SS, active = SB }, { key = "shadow_trance", glow = SS, active = SB } },
})
login()
push(st)
local ui = FS.CombatHud.ui
check(ui.tiles.corruption and ui.tiles.corruption.holder:IsShown(), "the tile with secret fields is still drawn")
check(ui.tiles.siphon.secs:GetText() == "5", "a plain cooldown still reads")
check(ui.tiles.immolate.secs:GetText() == "", "a secret cooldown draws no text")
check(not ui.nextTile.holder:IsShown(), "a secret next key draws no next tile")
check(not ui.shards:IsShown(), "a secret shard count draws no shards")
check(ui.buffTiles.pet and ui.buffTiles.pet.holder:IsShown(), "a plain buff beside a secret one still shows")
check(#__touches == 0, "a secret was touched: " .. tostring(__touches[1]))
-- in combat, secret flags everywhere
push(mkState({ inCombat = SB, shards = SN, row = { { key = "corruption", icon = SN, missing = SB, onCd = SB, cdRemaining = SN } },
    next = { key = "shadow_bolt", icon = SN, glow = SS }, procs = { { key = "shadow_trance", glow = SS, active = SB } } }))
check(ui.nextTile.holder:IsShown(), "next with a plain key and secret extras still shows")
check(#__touches == 0, "a secret was touched (round 2): " .. tostring(__touches[1]))
-- the ooc look (no combat, no next) reads the same row fields down its own paths
push(mkState({ inCombat = false, shards = SN,
    row = { { key = SS, icon = 1 }, { key = "corruption", icon = SN, missing = SB, remaining = SN, onCd = SB, cdRemaining = SN, proc = SS, isNext = SB },
            { key = "immolate", icon = iconOf("immolate"), missing = false, onCd = true, cdRemaining = SN } },
    buffsMissing = { { key = SS, icon = SN }, { key = "pet", icon = SN } },
    procs = { { key = SS, glow = SS, active = SB } } }))
check(not ui.nextTile.holder:IsShown(), "ooc: no next tile")
check(ui.tiles.corruption.holder:IsShown(), "ooc: the tile with secret fields is still drawn")
check(#__touches == 0, "a secret was touched (ooc round): " .. tostring(__touches[1]))
check(__hudPushErrors == nil, "the subscriber threw: " .. tostring(__hudLastError))
""")

case("a_throwing_render_is_contained_and_logged_once")(r"""
standard()
__state = mkState({ row = lockRow() })
login()
-- LuaJIT ipairs is raw, so the throwing metatable goes on the state itself
local bad = setmetatable({}, { __index = function() error("boom: state") end })
push(bad); push(bad)
check(__hudPushErrors == nil, "the error never reaches the Hud: " .. tostring(__hudLastError))
check(degraded("combathud_render") == 1, "logged once: " .. degraded("combathud_render"))
""")

# ---------------------------------------------------------------------------------------
# Subscribe / unsubscribe / updates
# ---------------------------------------------------------------------------------------

case("subscribes_on_enable_and_unsubscribes_and_hides_on_disable")(r"""
standard()
__state = mkState({ inCombat = true, row = lockRow(), shards = 3, next = { key = "shadow_bolt" }, buffsMissing = { { key = "pet" } } })
login()
local Hud, ui = FS.Hud, FS.CombatHud.ui
check(#Hud.subs == 1 and Hud.subscribeCalls == 1, "one subscription")
check(FS.CombatHud.IsEnabled(), "enabled by default for a warlock")
FS.CombatHud.Disable()
check(#Hud.subs == 0 and Hud.unsubscribeCalls == 1, "unsubscribed")
check(not ui.root:IsShown(), "root hidden")
check(ui.root:GetScript("OnUpdate") == nil, "no OnUpdate left behind")
local c = FS.CombatHud.containers.target
check(c._enabled == false and c._shown == false, "target container disabled and hidden")
check(not FS.CombatHud.IsEnabled(), "reports disabled")
FS.CombatHud.Disable()
check(Hud.unsubscribeCalls == 1, "disable is idempotent")
-- states pushed while disabled are ignored
local pushes = 0
push(mkState({ inCombat = true, row = lockRow({ [5] = { onCd = true, cdRemaining = 9 } }) }))
check(not ui.root:IsShown() and ui.root:GetScript("OnUpdate") == nil, "nothing redrawn while disabled")
FS.CombatHud.Enable()
check(#Hud.subs == 1 and Hud.subscribeCalls == 2, "re-subscribed")
check(ui.root:IsShown(), "shown again")
check(c._enabled == true, "target container live again")
check(ui.tiles.shadow_bolt.secs:GetText() == "9", "the Hud's push on Subscribe redraws")
FS.CombatHud.Enable()
check(Hud.subscribeCalls == 2, "enable is idempotent")
""")

case("the_display_never_polls_the_hud_and_runs_no_per_frame_work_without_a_cooldown")(r"""
standard()
__state = mkState({ inCombat = true, row = lockRow(), shards = 3, next = { key = "shadow_bolt" }, buffsMissing = { { key = "pet" } } })
login()
check(FS.Hud.getStateCalls == 0, "GetState is the Hud's job: it pushes, we never pull (" .. FS.Hud.getStateCalls .. " calls)")
local ui = FS.CombatHud.ui
check(ui.root:GetScript("OnUpdate") == nil, "no root OnUpdate")
for _, t in pairs(ui.tiles) do check(t.holder:GetScript("OnUpdate") == nil and t.face:GetScript("OnUpdate") == nil, "no tile OnUpdate") end
for _, f in ipairs(__frames) do
    if f._scripts and f._scripts.OnUpdate and f ~= ui.root then error("an OnUpdate on " .. tostring(f._name or f._kind)) end
end
""")

case("a_redraw_of_the_same_state_does_not_reanchor_anything")(r"""
standard()
local st = function() return mkState({ inCombat = true, row = lockRow(), shards = 3, next = { key = "shadow_bolt" }, buffsMissing = { { key = "pet" } } }) end
__state = st()
login()
local before = (__calls.SetPoint or 0)
push(st()); push(st())
check((__calls.SetPoint or 0) == before, "identical redraws re-seat no frame: " .. ((__calls.SetPoint or 0) - before) .. " SetPoint calls")
""")

# ---------------------------------------------------------------------------------------
# Idle cast bars
# ---------------------------------------------------------------------------------------

case("idle_row_is_turned_on_with_the_next_spell_as_the_player_hint")(r"""
standard()
__state = mkState({ inCombat = false, row = lockRow(), next = { key = "corruption" } })
login()
check(FS.CombatHud.idleCastBars == true, "idleCastBars defaults to true")
check(__idle.visible[#__idle.visible] == true, "SetIdleVisible(true)")
local function hint(unit) local h; for _, x in ipairs(__idle.hints) do if x[1] == unit then h = x[2] end end return h end
check(hint("player") == "Corruption", "the player bar names the next spell: " .. tostring(hint("player")))
check(hint("target") == nil, "the target bar carries no hint")
-- the next spell changes: the hint follows, once
local n = #__idle.hints
push(mkState({ inCombat = false, row = lockRow(), next = { key = "immolate" } }))
check(hint("player") == "Immolate" and #__idle.hints == n + 1, "hint follows the next spell")
push(mkState({ inCombat = false, row = lockRow(), next = { key = "immolate" }, shards = 1 }))
check(#__idle.hints == n + 1, "an unchanged hint is not sent again")
-- no next: the class filler, which is the wand
push(mkState({ inCombat = false, row = lockRow() }))
check(hint("player") == "Shoot", "no next: the filler (the wand): " .. tostring(hint("player")))
""")

case("idle_row_also_follows_in_combat_per_the_mockup")(r"""
standard()
__state = mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt" } })
login()
check(__idle.visible[#__idle.visible] == true, "the idle row stays on in combat (CastBars hides it while a cast runs)")
check(__idle.hints[#__idle.hints][2] == "Shadow Bolt", "hint is the next spell in combat too")
""")

case("idle_option_off_makes_no_calls_and_turning_it_off_hides_the_row")(r"""
standard()
FS.CombatHud.idleCastBars = false
__state = mkState({ row = lockRow(), next = { key = "corruption" } })
login()
check(#__idle.visible == 0 and #__idle.hints == 0, "no CastBars calls with the option off")
FS.CombatHud.SetIdleCastBars(true)
check(__idle.visible[#__idle.visible] == true and FS.CombatHud.idleCastBars == true, "turned on live")
FS.CombatHud.SetIdleCastBars(false)
check(__idle.visible[#__idle.visible] == false, "turned off: the idle row is released")
""")

case("disable_releases_the_idle_row")(r"""
standard()
__state = mkState({ row = lockRow(), next = { key = "corruption" } })
login()
FS.CombatHud.Disable()
check(__idle.visible[#__idle.visible] == false, "SetIdleVisible(false) on disable")
FS.CombatHud.Enable()
check(__idle.visible[#__idle.visible] == true, "and on again")
""")

case("missing_castbars_idle_api_is_skipped_silently_and_logged_once")(r"""
learnAll()
FS.targetCastBar = nil; FS.playerCastBar = nil
FS.CastBars = nil
__state = mkState({ row = lockRow(), next = { key = "corruption" } })
login()
push(mkState({ row = lockRow(), next = { key = "immolate" } }))
check(FS.CombatHud.ui.tiles.corruption.holder:IsShown(), "the HUD works without the idle API")
check(degraded("combathud_no_idle_api") == 1, "logged once: " .. degraded("combathud_no_idle_api"))
""")

# ---------------------------------------------------------------------------------------
# Defaults, slash command, SavedVariables
# ---------------------------------------------------------------------------------------

case("default_on_for_warlock", "WARLOCK")(r"""
standard(); __state = mkState({ row = lockRow() }); login()
check(FS.CombatHud.IsEnabled(), "on for a warlock")
""")

case("default_on_for_priest", "PRIEST")(r"""
learnAll(); useCastBars(0, -317); __state = mkState({ row = { rowEntry("sw_pain") } }); login()
check(FS.CombatHud.IsEnabled(), "on for a priest")
""")

case("paladin_next_tile_is_gold_with_an_empty_row", "PALADIN")(r"""
-- The paladin profile is a cooldown tracker with no row: only the NEXT tile shows, Holy Strike, gold
-- while it is ready (HudLogic hands the glow on state.next from the rule's procActive).
standard()
__state = mkState({ inCombat = true, row = {}, next = { key = "hs", icon = iconOf("hs"), glow = "gold" },
    procs = { { key = "hs", glow = "gold", active = true, icon = iconOf("hs") },
              { key = "jd", glow = "gold", active = true, icon = iconOf("jd") } } })
login()
check(FS.CombatHud.IsEnabled(), "on for a paladin")
local n = FS.CombatHud.ui.nextTile
check(n.holder:IsShown() and n.icon._texture == iconOf("hs"), "the NEXT tile shows Holy Strike's icon")
check(n.ring.kind == "gold" and colorEq(n.ring.edges[1]._vc, GOLD), "gold while Holy Strike is ready")
check(not FS.CombatHud.ui.row:IsShown(), "no row tiles")
check(not FS.CombatHud.ui.shards:IsShown(), "no shard data, no shard row")
check(not FS.CombatHud.ui.buffs:IsShown(), "no missing buffs, no buff tiles")
push(mkState({ inCombat = true, row = {}, procs = { { key = "hs", glow = "gold", active = false, icon = iconOf("hs") } } }))
check(not n.holder:IsShown(), "Holy Strike on cooldown: no NEXT")
""")

case("default_off_for_a_class_with_no_hud_profile", "MAGE")(r"""
learnAll(); useCastBars(0, -317); __state = mkState({ active = false }); login()
check(not FS.CombatHud.IsEnabled(), "off for a mage")
check(#FS.Hud.subs == 0, "and never subscribed")
check(FS.CombatHud.ui == nil or not FS.CombatHud.ui.root or not FS.CombatHud.ui.root:IsShown(), "nothing on screen")
SlashCmdList.FSHUD("on")
check(not FS.CombatHud.IsEnabled(), "/fshud on cannot start a HUD with no profile")
check(printed("no HUD"), "and says why")
check(#__degrade == 0, "no degrade logged")
""")

case("slash_command_toggles_and_persists_per_class")(r"""
standard(); __state = mkState({ row = lockRow() }); login()
check(SLASH_FSHUD1 == "/fshud" and type(SlashCmdList.FSHUD) == "function", "/fshud is registered")
SlashCmdList.FSHUD("off")
check(not FS.CombatHud.IsEnabled(), "off")
check(ForeverSynthwaveDB.combatHud.enabled.WARLOCK == false, "saved for the class in the account-wide table")
check(#FS.Hud.subs == 0, "unsubscribed")
SlashCmdList.FSHUD("  ON ")
check(FS.CombatHud.IsEnabled(), "on (case and spaces ignored)")
check(ForeverSynthwaveDB.combatHud.enabled.WARLOCK == true, "saved")
SlashCmdList.FSHUD("idle off")
check(FS.CombatHud.idleCastBars == false and ForeverSynthwaveDB.combatHud.idleCastBars == false, "idle off persisted")
SlashCmdList.FSHUD("idle on")
check(FS.CombatHud.idleCastBars == true and ForeverSynthwaveDB.combatHud.idleCastBars == true, "idle on persisted")
local n = #__printed
SlashCmdList.FSHUD("bogus")
check(#__printed > n and printed("/fshud"), "bad input prints the usage")
check(FS.CombatHud.IsEnabled(), "bad input changes nothing")
SlashCmdList.FSHUD("")
check(printed("combat HUD"), "no argument prints the state")
""")

case("saved_settings_are_honoured_at_login")(r"""
standard()
ForeverSynthwaveDB = { combatHud = { enabled = { WARLOCK = false }, idleCastBars = false } }
__state = mkState({ row = lockRow() })
login()
check(not FS.CombatHud.IsEnabled(), "a saved off wins over the class default")
check(FS.CombatHud.idleCastBars == false, "saved idle option")
SlashCmdList.FSHUD("on")
check(FS.CombatHud.IsEnabled() and #__idle.visible == 0, "enabled, idle option still off")
""")

case("a_saved_on_for_another_class_does_not_leak")(r"""
standard()
ForeverSynthwaveDB = { combatHud = { enabled = { PRIEST = false } } }
__state = mkState({ row = lockRow() })
login()
check(FS.CombatHud.IsEnabled(), "the priest's off does not turn the warlock's HUD off")
""")

case("login_retries_once_the_world_loads_when_the_hud_profile_was_not_ready")(r"""
standard()
local profile = FS.HudProfiles.WARLOCK
FS.HudProfiles.WARLOCK = nil           -- HudLogic's Setup has not seen the class yet
__state = mkState({ row = lockRow() })
login()
check(not FS.CombatHud.IsEnabled(), "no profile yet, no HUD")
FS.HudProfiles.WARLOCK = profile
fire("PLAYER_ENTERING_WORLD")
check(FS.CombatHud.IsEnabled(), "enabled on PLAYER_ENTERING_WORLD")
fire("PLAYER_ENTERING_WORLD")
check(FS.Hud.subscribeCalls == 1, "and only once")
""")

case("a_missing_hud_is_logged_once_and_does_nothing")(r"""
standard()
FS.Hud = nil
login(); fire("PLAYER_ENTERING_WORLD")
check(degraded("combathud_no_hud") == 1, "logged once: " .. degraded("combathud_no_hud"))
check(not FS.CombatHud.IsEnabled(), "disabled")
""")

# ---------------------------------------------------------------------------------------
# Cut corners (Parker, 2026-10-02): tiles are TOP-LEFT and BOTTOM-RIGHT chamfered like every
# other rectangle. The fill is hud_tile_cut2.tga (chamfer baked at 1/6 of the tile), the ring a
# cut outline nine-slice, the glow the cut glow, the icon seated inside the cut.
# ---------------------------------------------------------------------------------------

case("tile_rings_borders_and_glows_are_cut_outlines_that_match_the_baked_chamfer_at_each_size")(r"""
standard()
__state = mkState({ inCombat = true, row = lockRow({ [5] = { isNext = true } }), next = { key = "shadow_bolt" },
                    buffsMissing = { { key = "pet" } } })
login()
local ui = FS.CombatHud.ui
local T = FS.Theme
local function outlineOf(c) local o = T.Cut2ButtonSet(c); return o end
local function isCutOutline(tex, c, what)
    check(tex._texture == outlineOf(c), what .. " uses the cut2 outline for c=" .. c .. ", got " .. tostring(tex._texture))
    check(tex._slice == c, what .. " slices at the chamfer " .. c .. ", got " .. tostring(tex._slice))
    check(tex._color == nil, what .. " is a tinted texture, not a flat colour strip")
end
-- the chamfer the baked tile has at a size, and the baked ring size closest to it
local function bakedCut(size) return size * CUT_FRACTION end
local sizes = { spell = 36, next = 56, buff = 24 }
local want = {}
for k, size in pairs(sizes) do
    want[k] = T.SnapCut(math.floor(size / 6 + 0.5))
    local off = math.abs(want[k] - bakedCut(size))
    -- 36 and 24 land on a baked ring size (within a pixel); 56 wants 9.3 and the set tops out at 6
    if k == "next" then check(off <= 3.5, "the 56 tile's ring is the closest baked size, off by " .. off)
    else check(off <= 1, k .. " ring matches the baked chamfer within a pixel, off by " .. off) end
end
check(want.spell == 6 and want.buff == 4 and want.next == 6, "ring chamfers 6 / 6 / 4 for 36 / 56 / 24")
-- spell tile: a 1 texel border on the face, a 2 texel ring outside, the glow with the same chamfer
local t = ui.tiles.shadow_bolt
check(#t.border == 1, "spell tile border is one outline")
isCutOutline(t.border[1], want.spell, "spell tile border")
check(#t.ring.edges == 2, "spell tile ring is two stacked 1 texel outlines (the mockup's 2px ring)")
for i, e in ipairs(t.ring.edges) do isCutOutline(e, want.spell, "spell ring stroke " .. i) end
check(t.ring.edges[1]._inset == 0 and t.ring.edges[2]._inset == 1, "the second stroke sits one unit inside the first")
-- next tile
local n = ui.nextTile
check(#n.ring.edges == 2, "next ring is two outlines (2px)")
for i, e in ipairs(n.ring.edges) do isCutOutline(e, want.next, "next ring stroke " .. i) end
-- buff tile
local b = ui.buffTiles.pet
check(#b.border == 1, "buff border is one outline")
isCutOutline(b.border[1], want.buff, "buff border")
check(b.border[1]._texture:find("outline_c4", 1, true), "the 24 tile uses the c4 outline file")
-- glows: a chamfer, never the square 0
local cg = t.ring.glows.cyan
check(cg and cg._glow and cg._glow.radius == want.spell, "spell ring glow is cut at " .. want.spell .. ", got " .. tostring(cg and cg._glow and cg._glow.radius))
check(n.ring.glows.cyan._glow.radius == want.next, "next ring glow is cut at " .. want.next)
check(b.glowHost._glow and b.glowHost._glow.radius == want.buff, "buff glow is cut at " .. want.buff)
-- a proc keeps the shape: same textures, gold tint, a gold glow with the same chamfer
push(mkState({ inCombat = true, row = lockRow({ [5] = { isNext = true, proc = "gold" } }), next = { key = "shadow_bolt", glow = "gold" } }))
for i, e in ipairs(t.ring.edges) do
    isCutOutline(e, want.spell, "gold ring stroke " .. i)
    check(colorEq(e._vc, GOLD), "gold ring stroke " .. i .. " is gold")
end
check(t.ring.glows.gold._glow.radius == want.spell, "the gold glow keeps the chamfer")
for i, e in ipairs(n.ring.edges) do isCutOutline(e, want.next, "gold next stroke " .. i) end
check(n.ring.glows.gold._glow.radius == want.next, "the next tile's gold glow keeps the chamfer")
""")

case("tile_icons_are_seated_inside_the_cut_so_no_corner_pokes_past_it")(r"""
standard()
__state = mkState({ inCombat = true, row = lockRow(), next = { key = "shadow_bolt", icon = iconOf("shadow_bolt") },
                    buffsMissing = { { key = "pet", icon = 4242 } } })
login()
local ui = FS.CombatHud.ui
local function seated(icon, c, what)
    local tl, br = icon._points.TOPLEFT, icon._points.BOTTOMRIGHT
    local inset = math.ceil(c / 2)
    check(tl and br, what .. " icon is anchored by its two corners")
    check(tl.x >= inset and -tl.y >= inset and -br.x >= inset and br.y >= inset,
          what .. " icon inset is at least ceil(" .. c .. " / 2) = " .. inset .. " on every side")
    -- the icon's top left corner (i, i) must be on or inside the chamfer line x + y = c
    check(tl.x + (-tl.y) >= c, what .. " icon corner is inside the cut")
end
seated(ui.tiles.shadow_bolt.icon, 6, "spell tile")
seated(ui.nextTile.icon, 6, "next tile")
seated(ui.buffTiles.pet.icon, 4, "buff tile")
""")

case("no_flat_colour_strips_are_left_on_tile_rings_or_borders")(r"""
standard()
__state = mkState({ inCombat = true, row = lockRow({ [5] = { isNext = true } }), next = { key = "shadow_bolt" },
                    buffsMissing = { { key = "pet" } } })
login()
local ui = FS.CombatHud.ui
local lists = { ui.tiles.shadow_bolt.border, ui.tiles.shadow_bolt.ring.edges, ui.nextTile.ring.edges, ui.buffTiles.pet.border }
for i, list in ipairs(lists) do
    check(#list >= 1, "list " .. i .. " has outline pieces")
    for _, e in ipairs(list) do check(e._color == nil and e._texture ~= nil, "list " .. i .. ": a texture, not a SetColorTexture strip") end
end
-- no glow anywhere is the square one
for _, g in ipairs(__glows) do check(g.radius and g.radius > 0, "every tile glow has a chamfer, got " .. tostring(g.radius)) end
check(#__glows >= 3, "glows were built")
""")

# ---------------------------------------------------------------------------------------
# The Gunsight view (FS.Gunsight.IsEnabled() true): NEXT tile, soul shards and buff reminder re-homed
# onto the Gunsight anchors, the Stack A spell row retired. These cases run the REAL Layout.lua and
# Gunsight.lua; the Stack A cases above run under a Gunsight-disabled stub.
# ---------------------------------------------------------------------------------------

GS_PRELUDE = r"""
-- Boots the Gunsight world: screen height h (scale h / 1440), an optional first Hud state, and traps on
-- everything CastBars owns, so a Gunsight view that consults a cast bar frame or the idle API fails loudly.
function gsBoot(o)
    o = o or {}
    setScreen(o.h or 1440)
    learnAll()
    ForeverSynthwaveDB = o.db or {}
    if o.traps ~= false then
        local function trap(what)
            return setmetatable({}, { __index = function(_, k) error("CastBars touched in the Gunsight view: " .. what .. "." .. tostring(k)) end })
        end
        FS.targetCastBar, FS.playerCastBar, FS.CastBars = trap("targetCastBar"), trap("playerCastBar"), trap("CastBars")
    end
    __state = o.state
    fire("ADDON_LOADED", "ForeverSynthwave")
    seen = {}
    local gs = FS.Gunsight
    local orig = gs.RegisterPiece
    gs.RegisterPiece = function(key, spec) seen[key] = spec; return orig(key, spec) end
    if o.enableFirst then
        check(FS.CombatHud.Enable(), "the HUD did not enable")
        return FS.CombatHud.ui, gs
    end
    login()
    return FS.CombatHud.ui, gs
end
function sameRect(a, b, msg)
    local q = rect(b)
    rectEq(a, q.l, q.b, q.r, q.t, msg)
end
function rectSize(f) local q = rect(f); return q.r - q.l, q.t - q.b end
function shownCount(list) local n = 0; for _, f in ipairs(list) do if f._shown then n = n + 1 end end; return n end
function isUnder(f, root) while f do if f == root then return true end; f = f._parent end; return false end
-- The shard glyphs: four textures per held shard (glow, line, fill, facet), each a canvas larger than the 10 x 18
-- cell and centred on it, cells right aligned to the shard anchor with SH_G between.
function checkShardGlyphs(ui, anchor, k, n, label)
    local sa = rect(anchor)
    local step = (GU.SH_W + GU.SH_G) * k
    for i = 1, n do
        local g = ui.shardGlyphs[i]
        check(g ~= nil, label .. " glyph " .. i .. " exists")
        local cx = sa.r - (i - 1) * step - GU.SH_W * k / 2
        local cy = (sa.t + sa.b) / 2
        for _, e in ipairs({ { "line", GU.SHARD_LINE_W, GU.SHARD_LINE_H }, { "fill", GU.SHARD_LINE_W, GU.SHARD_LINE_H },
                             { "facet", GU.SHARD_LINE_W, GU.SHARD_LINE_H }, { "glow", GU.SHARD_GLOW_W, GU.SHARD_GLOW_H } }) do
            local t = g[e[1]]
            check(t ~= nil and t._shown, label .. " glyph " .. i .. " " .. e[1] .. " shows")
            local q = rect(t)
            -- the four textures share one centre, so every glyph's position is checked on the line texture and
            -- the other kinds on glyph 1; the size is a per kind check
            if i == 1 then
                near(q.r - q.l, e[2] * k, label .. " " .. e[1] .. " width")
                near(q.t - q.b, e[3] * k, label .. " " .. e[1] .. " height")
            end
            if e[1] == "line" or i == 1 then
                near((q.l + q.r) / 2, cx, label .. " glyph " .. i .. " " .. e[1] .. " centre x")
                near((q.t + q.b) / 2, cy, label .. " glyph " .. i .. " " .. e[1] .. " centre y")
            end
        end
    end
end
function textureCount(parent) local n = 0; for _, f in ipairs(__frames) do if f._kind == "Texture" and (parent == nil or f._parent == parent) then n = n + 1 end end; return n end
function shardGlyphCount(ui)
    local n = 0
    for _, g in ipairs(ui.shardGlyphs) do if g.line._shown then n = n + 1 end end
    return n
end
function effectivelyShown(f) while f do if f._shown == false then return false end; f = f._parent end; return true end
function nextState(over)
    local s = { inCombat = false, shards = 3, next = { key = "shadow_bolt", icon = iconOf("shadow_bolt") },
                buffsMissing = { { key = "demon_armor", icon = iconOf("demon_armor") } } }
    for k, v in pairs(over or {}) do s[k] = v end
    return mkState(s)
end
"""


def gcase(name: str, body: str, cls: str = "WARLOCK") -> None:
    case(name, cls, True)(GS_PRELUDE + body)


_GEOMETRY = r"""
local k = HEIGHT / 1440
local ui, gs = gsBoot({ h = HEIGHT, state = nextState() })
check(FS.CombatHud.IsGunsight(), "the Gunsight view is not active")
local A = gs.anchors
-- NEXT: the anchor's own rect, 56 design px at scale k (the mockup's NXT.s = 56 * U image px)
sameRect(ui.nextTile.holder, A.next, "the next tile sits exactly on anchors.next")
local w, h = rectSize(ui.nextTile.holder)
near(w, GU.NXT * k, "next tile width"); near(h, GU.NXT * k, "next tile height")
-- SHARDS: the line art glyphs, a 10 x 18 cell with gap 4, right aligned to the anchor, which is sized for the mockup's four
local sa = rect(A.shards)
near(sa.r - sa.l, (GU.SH_SC * GU.SH_W + (GU.SH_SC - 1) * GU.SH_G) * k, "the shard anchor is sized for four")
near(sa.t - sa.b, GU.SH_H * k, "the shard anchor is SH_H tall")
check(shardGlyphCount(ui) == 3, "three held shards are three glyphs")
check(#ui.diamonds == 0, "the Gunsight view builds no diamonds")
checkShardGlyphs(ui, A.shards, k, 3, "geometry")
-- BUFF: 24 design px, on anchors.buff
local tile = ui.buffTiles.demon_armor
check(tile and tile.holder._shown, "the buff tile shows")
sameRect(tile.holder, A.buff, "the buff tile sits exactly on anchors.buff")
w, h = rectSize(tile.holder)
near(w, GU.BUFF * k, "buff tile width"); near(h, GU.BUFF * k, "buff tile height")
"""

for _h in (1440, 1200):
    gcase(f"gunsight_tiles_sit_on_the_anchors_with_design_px_sizes_at_{_h}_of_1440", _GEOMETRY.replace("HEIGHT", str(_h)))

gcase("gunsight_view_registers_the_next_shard_and_buff_pieces_on_the_anchors", r"""
local ui, gs = gsBoot({ state = nextState() })
local n = 0
for _ in pairs(seen) do n = n + 1 end
check(n == 3 and seen.next and seen.shard and seen.buff, "exactly the pieces next, shard and buff are registered")
sameRect(seen.next.frame, gs.anchors.next, "next piece frame is on anchors.next")
sameRect(seen.shard.frame, gs.anchors.shards, "shard piece frame is on anchors.shards")
sameRect(seen.buff.frame, gs.anchors.buff, "buff piece frame is on anchors.buff")
check(isUnder(ui.nextTile.holder, seen.next.frame), "the next tile lives inside its piece frame")
check(isUnder(ui.shards, seen.shard.frame) and isUnder(ui.shardGlyphs[1].line, seen.shard.frame), "the shard row lives inside its piece frame")
check(isUnder(ui.buffs, seen.buff.frame) and isUnder(ui.buffTiles.demon_armor.holder, seen.buff.frame), "the buff row lives inside its piece frame")
-- the registry owns the piece frames: switching a piece off hides it, on shows it
gs.SetPiece("next", false, true)
check(seen.next.frame._shown == false and seen.next.frame._alpha == 0, "next piece off hides its frame")
gs.SetPiece("next", true, true)
check(seen.next.frame._shown == true and seen.next.frame._alpha == 1, "next piece back on shows it")
gs.SetPiece("shard", false, true)
check(seen.shard.frame._shown == false, "shard piece off hides its frame")
gs.SetPiece("buff", false, true)
check(seen.buff.frame._shown == false, "buff piece off hides its frame")
check(degraded("combathud_render") == 0 and degraded("gunsight_hook_next_onShow") == 0, "no render or hook failure")
""")

gcase("pieces_register_once_gunsight_is_ready_even_when_the_hud_enables_first", r"""
local ui, gs = gsBoot({ state = nextState(), enableFirst = true })
local n = 0
for _ in pairs(seen) do n = n + 1 end
check(n == 0, "Gunsight is not ready yet, so nothing registered yet")
fire("PLAYER_LOGIN")
n = 0
for _ in pairs(seen) do n = n + 1 end
check(n == 3 and seen.next and seen.shard and seen.buff, "the pieces register through OnReady at login")
sameRect(ui.nextTile.holder, gs.anchors.next, "the next tile is seated once Gunsight has seated its anchors")
""")

gcase("gunsight_view_never_builds_the_spell_row_the_ticker_or_the_target_container", r"""
local row = lockRow({ [1] = { onCd = true, cdRemaining = 7 }, [3] = { onCd = true, cdRemaining = 3 } })
local ui, gs = gsBoot({ state = mkState({ inCombat = true, row = row, shards = 2,
    next = { key = "shadow_bolt", icon = iconOf("shadow_bolt"), glow = "gold" } }) })
push(mkState({ inCombat = true, row = row, procs = { { key = "shadow_trance", active = true } } }))
check(ui.row == nil, "no spell row frame")
check(next(ui.tiles) == nil, "no spell tile was built")
check(ui.gap == nil and ui.playerBar == nil and ui.targetBar == nil, "no cast bar derived frames")
check(FS.CombatHud.containers.target == nil, "no DoT (target) aura container")
for _, ac in ipairs(__acs) do check(ac._unit ~= "target", "an aura container was built on the target") end
check(ui.root:GetScript("OnUpdate") == nil, "no root OnUpdate with no cooldown row")
check(FS.CombatHud.stats.cdTicks == 0, "the cooldown ticker never ran")
fire("PLAYER_TARGET_CHANGED"); fire("PLAYER_REGEN_ENABLED")
check(FS.CombatHud.containers.target == nil, "a retarget and regen still build no DoT container")
check(ui.root:GetScript("OnUpdate") == nil, "still no OnUpdate")
check(degraded("combathud_no_castbars") == 0 and degraded("combathud_render") == 0 and degraded("combathud_build") == 0,
    "no cast bar fallback log, no render or build failure")
-- the idle row and the rest alpha belong to the cast bars: the traps fire if either is asked
push(mkState({ inCombat = false, row = row }))
push(mkState({ inCombat = true, row = row, next = { key = "shadow_bolt" } }))
FS.CombatHud.SetIdleCastBars(true)
FS.CombatHud.Disable()
check(degraded("combathud_render") == 0, "nothing touched the cast bars on any state")
""")

gcase("gunsight_shard_row_shows_only_held_shards_and_a_plus_n_count_above_four", r"""
local ui, gs = gsBoot({ state = nextState({ shards = 1 }) })
local expect = { { 1, 1, nil }, { 2, 2, nil }, { 4, 4, nil }, { 5, 4, "+1" }, { 7, 4, "+3" }, { 20, 4, "+16" }, { 3, 3, nil } }
for _, e in ipairs(expect) do
    push(nextState({ shards = e[1] }))
    check(ui.shards._shown, e[1] .. " shards: the row shows")
    check(shardGlyphCount(ui) == e[2], e[1] .. " shards: " .. e[2] .. " glyphs, got " .. shardGlyphCount(ui))
    if e[3] then
        check(ui.shardMore and ui.shardMore._shown and ui.shardMore._text == e[3], e[1] .. " shards: the count reads " .. e[3] .. ", got " .. tostring(ui.shardMore and ui.shardMore._text))
        local fourth = rect(gs.anchors.shards).r - 3 * (GU.SH_W + GU.SH_G) - GU.SH_W
        near(rect(ui.shardMore).r, fourth - GU.SH_G, "the count is one gap left of the fourth cell")
    else
        check(ui.shardMore == nil or not ui.shardMore._shown, e[1] .. " shards: no count")
    end
end
push(nextState({ shards = 0 }))
check(not ui.shards._shown, "zero shards hides the row")
local none = nextState(); none.shards = nil
push(none)
check(not ui.shards._shown, "an unknown shard count hides the row")
push(nextState({ shards = SN }))
check(not ui.shards._shown, "a secret shard count hides the row")
local V = FS.Theme.COLOR_BORDER
local g1 = ui.shardGlyphs[1]
check(colorEq(g1.line._vc, V) and g1.line._vc[4] == 1, "the line is the mockup's violet at full alpha")
check(colorEq(g1.glow._vc, V) and g1.glow._vc[4] == 1, "the glow texture is violet (its strength is baked into the file)")
check(colorEq(g1.fill._vc, V), "the lit facet fill is violet")
near(g1.fill._vc[4], GU.SHARD_FILL_ALPHA, "the lit facet fill is the mockup's faint alpha")
local lighter = { V[1] + (1 - V[1]) * GU.SHARD_FACET_MIX, V[2] + (1 - V[2]) * GU.SHARD_FACET_MIX, V[3] + (1 - V[3]) * GU.SHARD_FACET_MIX }
check(colorEq(g1.facet._vc, lighter), "the facet lines are violet mixed toward white like the mockup: " .. table.concat(g1.facet._vc, ",") .. " vs " .. table.concat(lighter, ",") .. " mix " .. tostring(GU.SHARD_FACET_MIX))
for _, name in ipairs({ "line", "fill", "facet", "glow" }) do
    local tex = g1[name]._texture
    check(tex and tex:find("hud_shard_" .. name .. ".tga", 1, true), "the " .. name .. " texture is hud_shard_" .. name .. ".tga, got " .. tostring(tex))
end
""")

gcase("gunsight_buff_row_is_one_tile_on_the_anchor_and_grows_as_a_centred_row", r"""
local k = 1
local ui, gs = gsBoot({ state = nextState() })
local a = rect(gs.anchors.buff)
sameRect(ui.buffTiles.demon_armor.holder, gs.anchors.buff, "one missing buff is the anchor tile")
push(nextState({ buffsMissing = { { key = "demon_armor", icon = iconOf("demon_armor") }, { key = "pet" } } }))
local t1, t2 = rect(ui.buffTiles.demon_armor.holder), rect(ui.buffTiles.pet.holder)
local width = 2 * GU.BUFF + 6
near((t1.l + t2.r) / 2, (a.l + a.r) / 2, "the row is centred under the tape on the anchor centre")
near(t2.r - t1.l, width, "two tiles, gap 6")
near(t2.l - t1.r, 6, "tile gap")
near(t1.t, a.t, "the row hangs from the anchor top")
push(nextState({ buffsMissing = {} }))
check(not ui.buffs._shown, "no missing buff hides the row")
""")

gcase("gunsight_buff_border_pulses_alpha_from_the_mockups_floor_over_its_period", r"""
local ui, gs = gsBoot({ state = nextState() })
local tile = ui.buffTiles.demon_armor
for _, p in ipairs({ { tile.pulse, GU.PULSE_FROM, "border" }, { tile.glowPulse, 0, "glow" } }) do
    local g, from = p[1], p[2]
    check(g.playing, p[3] .. " pulse is playing on the shown tile")
    check(g.looping == "BOUNCE", p[3] .. " pulse bounces")
    local a = g.anims[1]
    near(a.from, from, p[3] .. " pulse from alpha"); near(a.to, 1, p[3] .. " pulse to alpha")
    near(a.duration, GU.PULSE_S, p[3] .. " pulse seconds")
end
near(GU.PULSE_FROM + GU.PULSE_SPAN, 1, "the mockup's border alpha runs .35 to 1")
push(nextState({ buffsMissing = {} }))
check(not tile.pulse.playing and not tile.glowPulse.playing, "the pulse stops when the tile goes")
""")

_SCALE = r"""
local k = HEIGHT / 1440
local ui, gs = gsBoot({ h = HEIGHT, state = nextState({ next = { key = "shadow_bolt", icon = iconOf("shadow_bolt"), glow = "gold" } }) })
local T = FS.Theme
local function cutOf(px) return T.SnapCut(math.floor(px / 6 + 0.5)) end
local cutN, cutB = cutOf(GU.NXT * k), cutOf(GU.BUFF * k)
local thick = math.max(1, math.floor(2 * k + 0.5))
local ring = ui.nextTile.ring
check(ring.kind == "gold", "a proc makes the next tile gold")
check(#ring.edges == thick, "next border is " .. thick .. " stacked strokes, got " .. #ring.edges)
for _, e in ipairs(ring.edges) do check(e._slice == cutN, "next ring chamfer " .. cutN .. ", got " .. tostring(e._slice)) end
local glow = ring.glows.gold._glow
check(glow and glow.radius == cutN, "next glow chamfer follows the ring")
near(glow.size, 10 * k, "next glow size is 10 design px")
local tile = ui.buffTiles.demon_armor
for _, e in ipairs(tile.border) do check(e._slice == cutB, "buff border chamfer " .. cutB .. ", got " .. tostring(e._slice)) end
local bg = tile.glowHost._glow
check(bg and bg.radius == cutB, "buff glow chamfer")
near(bg.size, 8 * k, "buff glow size is 8 design px")
-- the icon stays inside the cut at this size
local function inset(tex) local p = tex._points.TOPLEFT; return p.x end
check(inset(ui.nextTile.icon) >= math.max(thick, math.ceil(cutN / 2)), "next icon inset clears the cut")
check(inset(tile.icon) >= math.ceil(cutB / 2), "buff icon inset clears the cut")
-- type and offsets scale with the design
local function size(fs) return fs._font[2] end
local want = function(v) return math.max(1, math.floor(v * k + 0.5)) end
-- the mockup's text sizes are canvas (image) px: design px = image px * 1.28
check(size(ui.nextTile.key) == want(GU.KEY_PX * GU.GRID), "keybind font " .. GU.KEY_PX .. " image px, got " .. size(ui.nextTile.key))
check(size(ui.nextTile.lbl) == want(GU.LBL_PX * GU.GRID), "NEXT caption font " .. GU.LBL_PX .. " image px, got " .. size(ui.nextTile.lbl))
check(size(ui.nextTile.abbr) == want(GU.ABBR_UNITS + GU.ABBR_ADD * GU.GRID), "NEXT abbreviation 16 * U + 2 image px, got " .. size(ui.nextTile.abbr))
check(size(tile.abbr) == want(GU.BUFF_ABBR_PX * GU.GRID), "buff abbreviation " .. GU.BUFF_ABBR_PX .. " image px, got " .. size(tile.abbr))
local kp, lp = ui.nextTile.key._points.TOPRIGHT, ui.nextTile.lbl._points.TOP
near(kp.x, -4 * k, "keybind sits 4 in from the right"); near(kp.y, -2 * k, "keybind sits 2 down")
near(lp.y, -3 * k, "NEXT caption 3 under the tile")
check(ui.nextTile.lbl._text == "NEXT", "the caption reads NEXT")
"""

for _h in (1440, 720):
    gcase(f"gunsight_chamfers_strokes_glows_and_type_follow_the_scale_at_{_h}_of_1440", _SCALE.replace("HEIGHT", str(_h)))

gcase("gunsight_next_tile_is_cyan_gold_on_a_proc_and_shows_the_keybind_top_right", r"""
local ui, gs = gsBoot({ state = nextState({ next = { key = "shadow_bolt", icon = iconOf("shadow_bolt") } }) })
local ring = ui.nextTile.ring
check(ring.kind == "cyan", "no proc: the next border is cyan")
check(colorEq(ring.edges[1]._vc, FS.Theme.COLOR_POWER), "cyan border colour")
push(nextState({ next = { key = "shadow_bolt", icon = iconOf("shadow_bolt"), glow = "gold" } }))
check(ui.nextTile.ring.kind == "gold" and colorEq(ui.nextTile.ring.edges[1]._vc, GOLD), "a proc turns the border gold")
-- the real keybind label
C_ActionBar = { FindSpellActionButtons = function(id) return { 1 } end }
GetBindingKey = function(cmd) if cmd == "ACTIONBUTTON1" then return "3" end end
GetBindingText = function(key) return key end
GetActionBarPage = function() return 1 end
fire("UPDATE_BINDINGS")
check(ui.nextTile.key._shown and ui.nextTile.key._text == "3", "the keybind number shows top right")
local none = nextState(); none.next = nil
push(none)
check(not ui.nextTile.holder._shown, "no next cast hides the tile")
""")

gcase("gunsight_view_out_of_combat_with_no_next_hides_only_the_next_tile", r"""
local ui, gs = gsBoot({ state = nextState({ next = false, shards = 2 }) })
check(not ui.nextTile.holder._shown, "ooc with no next: no next tile")
check(ui.shards._shown and shardGlyphCount(ui) == 2, "shards still show")
check(ui.buffs._shown and ui.buffTiles.demon_armor.holder._shown, "buffs still show")
check(degraded("combathud_render") == 0, "no cast bar call")
""")

gcase("gunsight_occlusion_slot_sits_on_the_buff_anchor_and_follows_the_buff_piece", r"""
local ui, gs = gsBoot({ state = nextState({ inCombat = false }) })
local c = FS.CombatHud.containers.player
check(c, "the player container was built out of combat for the occlusion slots")
__combat = true                      -- the cover is live only when the client really is in combat
push(nextState({ inCombat = true, buffsMissing = {} }))
local tile = ui.buffTiles.demon_armor
check(tile and tile.slot, "demon armor has an occlusion slot")
sameRect(tile.holder, gs.anchors.buff, "the warning tile sits on anchors.buff")
sameRect(tile.slot, gs.anchors.buff, "the slot frame covers the warning tile exactly")
check(c._enabled == true and c._shown == true and c._alpha == 1, "the container is live in combat: enabled, shown, alpha 1")
-- the covers hang under the buff piece frame, so its fade and its hide carry them too
check(isUnder(c, seen.buff.frame), "the player container is a child of the buff piece frame")
-- the piece off leaves the container's own alpha at 1 (it follows the piece through its parent) and never switches it off
gs.SetPiece("buff", false, true)
check(seen.buff.frame._shown == false and seen.buff.frame._alpha == 0, "the buff piece is hidden")
check(c._alpha == 1 and c._enabled == true and c._shown == true, "the piece off leaves the container's own alpha 1, enabled and shown")
check(not effectivelyShown(c), "the cover is not visible: its parent piece is hidden")
gs.SetPiece("buff", true, true)
check(seen.buff.frame._shown == true and c._enabled == true and c._alpha == 1, "the buff piece back on shows the covers again")
check(effectivelyShown(c), "the cover is visible again with the piece")
""")

gcase("gunsight_rescale_resizes_every_piece_in_place_and_a_repeat_changes_nothing", r"""
local ui, gs = gsBoot({ h = 1440, state = nextState({ shards = 5, buffsMissing = { { key = "demon_armor" }, { key = "pet" } } }) })
setScreen(1200)
fire("UI_SCALE_CHANGED")
local k = 1200 / 1440
sameRect(ui.nextTile.holder, gs.anchors.next, "next tile follows its anchor")
local w = rectSize(ui.nextTile.holder)
near(w, GU.NXT * k, "next width after the rescale")
local glyphs, g1line = ui.shardGlyphs, ui.shardGlyphs[1].line
checkShardGlyphs(ui, gs.anchors.shards, k, 4, "after the rescale")
check(shardGlyphCount(ui) == 4, "four glyphs shown after the rescale")
local t1, t2 = rect(ui.buffTiles.demon_armor.holder), rect(ui.buffTiles.pet.holder)
near(t1.r - t1.l, GU.BUFF * k, "buff tile width after the rescale")
near(t2.l - t1.r, 6 * k, "buff gap after the rescale")
check(#ui.nextTile.ring.edges == math.max(1, math.floor(2 * k + 0.5)), "next border thickness follows the scale")
check(ui.shardMore and ui.shardMore._text == "+1", "the shard count survives the rescale")
local frames = #__frames
fire("UI_SCALE_CHANGED")
check(#__frames == frames, "a rescale to the same scale builds nothing")
local tex = textureCount(ui.shards)
setScreen(720); fire("UI_SCALE_CHANGED"); setScreen(1440); fire("UI_SCALE_CHANGED")
check(textureCount(ui.shards) == tex, "a rescale builds no new shard texture, got " .. (textureCount(ui.shards) - tex))
check(ui.shardGlyphs == glyphs and ui.shardGlyphs[1].line == g1line, "the glyph textures are reused in place")
checkShardGlyphs(ui, gs.anchors.shards, 1, 4, "back at full scale")
""")

gcase("gunsight_rescale_reuses_rings_and_glow_hosts_instead_of_building_new_ones", r"""
local ui, gs = gsBoot({ h = 1440, state = nextState({ shards = 3,
    next = { key = "shadow_bolt", icon = iconOf("shadow_bolt"), glow = "gold" } }) })
local function visit(h) setScreen(h); fire("UI_SCALE_CHANGED") end
visit(720); visit(1200)
for _, g in ipairs(__glows) do check(g.size == math.floor(g.size), "glow size " .. g.size .. " is not a whole number") end
check(ui.nextTile.ring.glowSize == math.floor(ui.nextTile.ring.glowSize), "the next ring's glow size is a whole number")
local frames, glows = #__frames, #__glows
visit(1440); visit(720); visit(1200); visit(1440)
check(#__frames == frames, "revisiting a scale built " .. (#__frames - frames) .. " new frames")
check(#__glows == glows, "revisiting a scale built " .. (#__glows - glows) .. " new glows")
check(ui.nextTile.ring.kind == "gold" and ui.nextTile.ring:IsShown(), "the revisited ring shows the proc kind")
local shown = 0
for _, r in pairs(ui.nextTile.rings) do if r:IsShown() then shown = shown + 1 end end
check(shown == 1, "exactly one next ring is shown after the revisits, got " .. shown)
-- two scales that snap to the same chamfer, stroke count and glow sizes share every ring and glow host
visit(1200)
frames, glows = #__frames, #__glows
visit(1190)
check(#__frames == frames and #__glows == glows, "a scale that snaps to the same sizes built " .. (#__frames - frames) .. " frames")
""")

gcase("gunsight_aura_cover_follows_a_rescale_and_waits_for_combat_to_end", r"""
local ui, gs = gsBoot({ h = 1440, state = nextState({ inCombat = false }) })
local tile = ui.buffTiles.demon_armor
check(tile and tile.slot and tile.cover, "the slot cover is recorded on its tile")
local T = FS.Theme
local function inset(tex) return tex._points.TOPLEFT.x end
local cut0 = T.SnapCut(math.floor(24 / 6 + 0.5))
for _, e in ipairs(tile.cover.border) do check(e._slice == cut0, "cover border chamfer " .. cut0 .. " at 1.0, got " .. tostring(e._slice)) end
check(inset(tile.cover.icon) == math.ceil(cut0 / 2), "cover icon inset at 1.0")
setScreen(720); fire("UI_SCALE_CHANGED")
local cut1 = T.SnapCut(math.floor(12 / 6 + 0.5))
check(cut1 ~= cut0, "the test needs two different chamfers")
for _, e in ipairs(tile.cover.border) do check(e._slice == cut1, "cover border re-cut to " .. cut1 .. ", got " .. tostring(e._slice)) end
check(inset(tile.cover.icon) == math.ceil(cut1 / 2), "cover icon re-seated to the new chamfer")
-- a rescale that lands in combat leaves the engine-built cover alone until combat ends
__combat = true
setScreen(1440); fire("UI_SCALE_CHANGED")
for _, e in ipairs(tile.cover.border) do check(e._slice == cut1, "cover untouched in combat") end
check(inset(tile.cover.icon) == math.ceil(cut1 / 2), "cover icon untouched in combat")
__combat = false
fire("PLAYER_REGEN_ENABLED")
for _, e in ipairs(tile.cover.border) do check(e._slice == cut0, "cover re-cut at the end of combat, got " .. tostring(e._slice)) end
check(inset(tile.cover.icon) == math.ceil(cut0 / 2), "cover icon re-seated at the end of combat")
""")

gcase("gunsight_cover_is_armed_out_of_combat_and_driven_by_alpha_alone", r"""
local ui, gs = gsBoot({ state = nextState({ inCombat = false }) })
local c = FS.CombatHud.containers.player
-- built, given its unit and slots, then enabled and shown out of combat; invisible until combat
check(c and c._unit == "player", "the player container is on unit player")
check(c._enabled == true and c._shown == true, "the cover is enabled and shown out of combat, and stays so")
check(c._alpha == 0, "alpha 0 out of combat: a live slot draws nothing over a hidden tile")
local function calls() return (c._enableCalls or 0), (c._showCalls or 0), (c._hideCalls or 0) end
local e0, s0, h0 = calls()
local function combatState() return nextState({ inCombat = true, buffsMissing = {} }) end
-- combat starts while the engine refuses every SetEnabled / Show / Hide and calls the frame protected:
-- the covers still appear, because alpha is the only thing combat ever writes
__combat = true; __acProtected = true; __acRefuse = true
push(combatState())
check(c._alpha == 1, "alpha 1 in combat with the buff piece on")
check(ui.buffTiles.demon_armor.holder._shown, "the warning is up behind the cover")
local e1, s1, h1 = calls()
check(e1 == e0 and s1 == s0 and h1 == h0, "no SetEnabled, Show or Hide on the container in combat")
-- combat ends: alpha 0, nothing replayed (no stale enable), the container is simply left armed
__combat = false; __acProtected = false; __acRefuse = false
push(nextState({ inCombat = false, buffsMissing = {} }))
fire("PLAYER_REGEN_ENABLED")
check(c._alpha == 0, "alpha 0 again once combat is over")
check(c._enabled == true and c._shown == true, "the container is left armed, not toggled")
-- the piece off in combat does not touch the cover's own alpha: the piece carries it
__combat = true
push(combatState())
check(c._alpha == 1, "combat again: alpha 1")
gs.SetPiece("buff", false, true)
check(c._alpha == 1 and not effectivelyShown(c), "the buff piece off: own alpha stays 1, not visible through the piece")
gs.SetPiece("buff", true, true)
check(c._alpha == 1 and effectivelyShown(c), "the buff piece on: alpha 1, visible")
__combat = false
push(nextState({ inCombat = false, buffsMissing = {} }))
-- something left it off: the end of combat arms it again, alpha untouched
c._enabled, c._shown = false, false
fire("PLAYER_REGEN_ENABLED")
check(c._enabled == true and c._shown == true and c._alpha == 0, "re-armed at the end of combat, still invisible")
""")

gcase("gunsight_regen_enabled_zeroes_the_cover_with_no_state_push_after_combat", r"""
-- the end of combat must not wait for the next Hud push (about 0.2 s): the covers go to alpha 0 on the event itself
local ui, gs = gsBoot({ state = nextState({ inCombat = false }) })
local c = FS.CombatHud.containers.player
__combat = true
push(nextState({ inCombat = true, buffsMissing = {} }))
check(c._alpha == 1, "alpha 1 in combat with a tile to cover")
__combat = false
fire("PLAYER_REGEN_ENABLED")        -- deliberately NO state push after combat
check(c._alpha == 0, "alpha 0 on PLAYER_REGEN_ENABLED itself, got " .. tostring(c._alpha))
check(c._enabled == true and c._shown == true, "and the container stays armed")
""")

gcase("gunsight_regen_disabled_lights_the_cover_when_lockdown_starts_after_the_hud_said_inCombat", r"""
-- HudLogic can say inCombat (UnitAffectingCombat) a beat before InCombatLockdown is on: that push leaves the
-- cover at alpha 0, and nothing else re-renders when lockdown starts, so PLAYER_REGEN_DISABLED must
local ui, gs = gsBoot({ state = nextState({ inCombat = false }) })
local c = FS.CombatHud.containers.player
__combat = false
push(nextState({ inCombat = true, buffsMissing = {} }))
check(c._alpha == 0, "inCombat pushed with no lockdown yet: the cover stays at alpha 0, got " .. tostring(c._alpha))
__combat = true                      -- lockdown starts; deliberately NO state push
fire("PLAYER_REGEN_DISABLED")
check(c._alpha == 1, "alpha 1 on PLAYER_REGEN_DISABLED itself, got " .. tostring(c._alpha))
check(ui.buffTiles.demon_armor.holder._shown, "the warning is up behind the cover")
check(degraded("combathud_render") == 0 and degraded("combathud_event_PLAYER_REGEN_DISABLED") == 0, "no render or event failure")
-- an out of combat state at that moment (a stale event) must not light anything
__combat = false
push(nextState({ inCombat = false, buffsMissing = {} }))
fire("PLAYER_REGEN_DISABLED")
check(c._alpha == 0, "no cover for an out of combat state, got " .. tostring(c._alpha))
""")

gcase("gunsight_buff_piece_shown_just_after_combat_keeps_the_cover_at_alpha_zero", r"""
-- the piece's onShow replays lastState, which can still say inCombat for ~0.2 s after the client left
-- combat: the cover is live only when the client is in combat NOW, and a throwing check is not live
local ui, gs = gsBoot({ state = nextState({ inCombat = false }) })
local c = FS.CombatHud.containers.player
__combat = true
push(nextState({ inCombat = true, buffsMissing = {} }))
check(c._alpha == 1, "alpha 1 in combat with a tile to cover")
gs.SetPiece("buff", false, true)
__combat = false                     -- combat ended; lastState still says inCombat = true (no push yet)
gs.SetPiece("buff", true, true)      -- onShow -> Rerender replays lastState
check(c._alpha == 0, "the buff piece shown out of combat leaves the cover at alpha 0, got " .. tostring(c._alpha))
-- the check itself throwing is not live either
gs.SetPiece("buff", false, true)
__combat = true; __combatThrows = true
c._alpha, c.fsAlpha = 0, 0
gs.SetPiece("buff", true, true)
check(c._alpha == 0, "a throwing combat check fails closed to alpha 0, got " .. tostring(c._alpha))
__combatThrows = false
""")

gcase("gunsight_arming_the_cover_writes_alpha_zero_before_any_state_arrives", r"""
-- a freshly armed cover is invisible without a Hud push: a live slot must never draw over a hidden tile
local ui, gs = gsBoot({ state = nextState({ inCombat = false }) })
local c = FS.CombatHud.containers.player
-- alpha 1 with a stale cache saying 0: only arming itself (not the cached SetCover) can put it right
c._alpha, c.fsAlpha, c._enabled, c._shown, c.fsArmed = 1, 0, false, false, nil
__state = nil
fire("PLAYER_REGEN_ENABLED")
check(c._enabled == true and c._shown == true, "re-armed")
check(c._alpha == 0 and c.fsAlpha == 0, "arming wrote alpha 0, got " .. tostring(c._alpha))
""")

gcase("gunsight_buff_piece_on_rerenders_so_a_stopped_pulse_plays_again", r"""
-- a hidden frame may stop its AnimationGroups, and SetPulse only plays a group that is not playing:
-- bringing the piece back on must redraw (onShow), while hiding it has nothing to redraw (no onHide)
local ui, gs = gsBoot({ state = nextState({ inCombat = false }) })
local tile = ui.buffTiles.demon_armor
check(type(seen.buff.onShow) == "function" and seen.buff.onHide == nil, "the buff piece has an onShow redraw and no onHide")
check(tile.pulse.playing and tile.glowPulse.playing, "both pulses play with the piece on")
gs.SetPiece("buff", false, true)
tile.pulse:Stop(); tile.glowPulse:Stop()             -- what the engine may do under a hidden frame
check(not tile.pulse.playing, "the test stopped the pulse")
gs.SetPiece("buff", true, true)
check(tile.pulse.playing and tile.glowPulse.playing, "piece back on: both pulses play again")
check(degraded("combathud_render") == 0 and degraded("gunsight_hook_buff_onShow") == 0, "no render or hook failure")
""")

gcase("gunsight_without_an_armed_cover_combat_shows_only_what_the_hud_reports", r"""
-- the engine will not enable the container: no cover can ever appear, so a warning drawn in combat
-- would be a permanent false alarm and must not be
__acRefuse = true
local ui, gs = gsBoot({ state = nextState({ inCombat = false }) })
local c = FS.CombatHud.containers.player
check(c and c._enabled ~= true, "the container could not be armed")
__combat = true
push(nextState({ inCombat = true, buffsMissing = {} }))
check(ui.buffTiles.demon_armor and not ui.buffTiles.demon_armor.holder._shown, "no warning in combat without a cover to occlude it")
check(c._alpha == 0, "and the container stays invisible")
-- the engine takes it at the end of combat: the next fight has its covers
__acRefuse = false; __combat = false
fire("PLAYER_REGEN_ENABLED")
check(c._enabled == true and c._shown == true, "armed at the end of combat")
__combat = true
push(nextState({ inCombat = true, buffsMissing = {} }))
check(ui.buffTiles.demon_armor.holder._shown and c._alpha == 1, "the next fight shows the warning behind its cover")
""")

gcase("gunsight_shard_glyphs_carry_a_baked_glow_texture_and_a_rescale_builds_nothing", r"""
local ui, gs = gsBoot({ h = 1440, state = nextState({ shards = 2 }) })
local function glows()
    local n = 0
    for _, g in ipairs(ui.shardGlyphs) do if g.glow._shown then n = n + 1 end end
    return n
end
check(glows() == 2, "only the two held shards glow, got " .. glows())
for _, g in ipairs(ui.shardGlyphs) do
    check(not g.glow._shown == not g.line._shown, "a glyph's glow follows its line")
    check(g.glow._parent == ui.shards, "the glows sit on the row, under every glyph")
end
push(nextState({ shards = 4 }))
check(glows() == 4, "four held shards, four glows, got " .. glows())
local built, glowHosts = textureCount(ui.shards), #__glows
for i = 1, 5 do push(nextState({ shards = 4 })); push(nextState({ shards = 3 })); push(nextState({ shards = 4 })) end
check(textureCount(ui.shards) == built, "re-rendering builds no more textures, got " .. (textureCount(ui.shards) - built) .. " new")
check(#__glows == glowHosts, "the shards never build an AddOuterGlow host, got " .. (#__glows - glowHosts) .. " new")
push(nextState({ shards = 1 }))
check(glows() == 1 and ui.shardGlyphs[1].glow._shown, "one held shard, one glow")
for i = 2, 4 do
    for _, name in ipairs({ "glow", "line", "fill", "facet" }) do
        check(not ui.shardGlyphs[i][name]._shown, "glyph " .. i .. " " .. name .. " hides when the shard is not held")
    end
end
setScreen(720); fire("UI_SCALE_CHANGED")
checkShardGlyphs(ui, gs.anchors.shards, 0.5, 1, "half scale")
""")

gcase("gunsight_next_ring_glow_is_the_mockups_full_strength_in_cyan_and_gold", r"""
local ui, gs = gsBoot({ state = nextState({ next = { key = "shadow_bolt", icon = iconOf("shadow_bolt") } }) })
local ring = ui.nextTile.ring
check(ring.kind == "cyan" and ring.glows.cyan, "cyan next ring with its glow")
near(ring.glows.cyan._glow.alpha, 1, "the mockup draws the next glow at strength 1")
push(nextState({ next = { key = "shadow_bolt", icon = iconOf("shadow_bolt"), glow = "gold" } }))
near(ui.nextTile.ring.glows.gold._glow.alpha, 1, "gold glow at strength 1")
check(colorEq({ ring.glows.gold._glow.r, ring.glows.gold._glow.g, ring.glows.gold._glow.b }, GOLD), "gold glow colour")
""")

gcase("fsgun_off_keeps_the_stack_a_fallback_working", r"""
local ui, gs = gsBoot({ traps = false, db = { gunsight = { enabled = false } },
    state = mkState({ inCombat = true, row = lockRow({ [5] = { onCd = true, cdRemaining = 4 } }), shards = 2,
                      next = { key = "shadow_bolt", icon = iconOf("shadow_bolt") } }) })
check(gs.IsEnabled() == false, "Gunsight is off in this world")
check(not FS.CombatHud.IsGunsight(), "the HUD is in the Stack A view")
check(ui.row and ui.gap and next(ui.tiles) ~= nil, "the Stack A row and its tiles are built")
check(ui.root:GetScript("OnUpdate") ~= nil, "the cooldown ticker runs for a cooldown tile")
local n = 0
for _ in pairs(seen) do n = n + 1 end
check(n == 0, "no Gunsight piece is registered in the fallback")
check(ui.nextTile.holder._shown and FS.CombatHud.containers.target ~= nil, "next tile and the DoT container work as before")
""")

case("stack_a_asks_nothing_of_a_disabled_gunsight")(r"""
standard()
__state = mkState({ inCombat = true, row = lockRow(), shards = 2, next = { key = "shadow_bolt" } })
login()
check(not FS.CombatHud.IsGunsight(), "a disabled Gunsight leaves the Stack A view")
check(FS.CombatHud.ui.row ~= nil, "the row is built")
check(#__gsCalls.pieces == 0, "no piece registered under a disabled Gunsight")
check(__gsCalls.onReady == 0, "no OnReady wait under a disabled Gunsight")
""")

case("stack_a_keeps_its_own_ring_glow_container_parent_and_text_sizes")(r"""
standard()
__state = mkState({ inCombat = false, row = lockRow(), next = { key = "shadow_bolt", icon = iconOf("shadow_bolt") },
                    buffsMissing = { { key = "demon_armor" } } })
login()
local ui = FS.CombatHud.ui
check(not FS.CombatHud.IsGunsight(), "the Stack A view")
-- the NEXT ring's glow is the Stack A strength, not the Gunsight mockup's 1
local ring = ui.nextTile.ring
check(ring and ring.glows.cyan, "the cyan next ring has its glow")
near(ring.glows.cyan._glow.alpha, 0.5, "Stack A next glow alpha")
-- the occlusion container hangs off the HUD root (there is no buff piece), and keeps the enable/show/hide
-- switching in combat
local c = FS.CombatHud.containers.player
check(c and c._parent == ui.root and ui.buffPiece == nil, "the player container is parented to ui.root")
check(c._enabled == false and c._shown == false, "off out of combat")
push(mkState({ inCombat = true, row = lockRow() }))
check(c._enabled == true and c._shown == true, "enabled and shown in combat")
push(mkState({ inCombat = false, row = lockRow() }))
check(c._enabled == false and c._shown == false, "disabled and hidden again out of combat")
-- the unconverted type sizes (UI units, not canvas px times 1.28)
local function size(fs) return fs._font[2] end
check(size(ui.nextTile.key) == 12, "Stack A keybind size 12, got " .. size(ui.nextTile.key))
check(size(ui.nextTile.lbl) == 9, "Stack A NEXT caption size 9, got " .. size(ui.nextTile.lbl))
check(size(ui.nextTile.abbr) == 16, "Stack A NEXT abbreviation size 16, got " .. size(ui.nextTile.abbr))
local tile = ui.buffTiles.demon_armor
check(tile and size(tile.abbr) == 8, "Stack A buff abbreviation size 8")
""")



# ---------------------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------------------

FILE_CASES = {}


def file_check(name: str):
    def deco(fn):
        FILE_CASES[name] = fn
        return fn
    return deco


@file_check("toc_lists_combathud_after_hudlogic_with_crlf_intact")
def _toc():
    raw = TOC.read_bytes()
    if raw.count(b"\r\n") != raw.count(b"\n"):
        return "ForeverSynthwave.toc lost its CRLF line endings"
    lines = raw.decode("utf-8").split("\r\n")
    names = [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]
    if "CombatHud.lua" not in names:
        return "CombatHud.lua is not in the .toc"
    pos = names.index("CombatHud.lua")
    for dep in ("Theme.lua", "Layout.lua", "FrameHelpers.lua", "CastBars.lua", "HudSpells.lua", "HudProfiles.lua",
                "HudLogic.lua", "Gunsight.lua"):
        if dep not in names or names.index(dep) > pos:
            return f"CombatHud.lua must load after {dep}"
    return None


@file_check("no_em_or_en_dashes_in_the_new_files")
def _dashes():
    for path in (COMBATHUD, Path(__file__).resolve()):
        if path.exists():
            text = path.read_text(encoding="utf-8")
            for bad in (chr(0x2014), chr(0x2013)):
                if bad in text:
                    return f"{path.name} contains an em or en dash"
    return None


@file_check("diamond_texture_exists")
def _diamond():
    if not (ADDON / "media" / "hud_diamond.tga").exists():
        return "media/hud_diamond.tga is missing"
    return None


@file_check("shard_textures_are_power_of_two_tgas_of_the_generators_size_and_the_glyph_is_the_mockups")
def _shard_textures():
    gen = shard_generator()
    glyph = shard_glyph(GUNSIGHT_MOCKUP.read_text(encoding="utf-8"))
    def close(a, b):
        return len(a) == len(b) and all(abs(p[0] - q[0]) < 1e-9 and abs(p[1] - q[1]) < 1e-9 for p, q in zip(a, b))
    if not close(gen.OUTLINE, glyph["outline"]) or not close(gen.LIT, glyph["lit"]):
        return "generate_hud_shard.py OUTLINE or LIT differs from the mockup's SH_GLYPH"
    if not close([p for f in gen.FACETS for p in f], [p for f in glyph["facets"] for p in f]):
        return "generate_hud_shard.py FACETS differ from the mockup's SH_GLYPH"
    src = GUNSIGHT_MOCKUP.read_text(encoding="utf-8")
    sh = re.search(r"var SH_SC=(\d+),SH_W=(\d+)\*U,SH_H=(\d+)\*U,SH_G=(\d+)\*U", src)
    if not sh or (gen.SH_W, gen.SH_H) != (float(sh.group(2)), float(sh.group(3))):
        return "generate_hud_shard.py SH_W / SH_H differ from the mockup's shard box"
    for name, (w, h, uw, uh) in gen.FILES.items():
        path = ADDON / "media" / (name + ".tga")
        if not path.exists():
            return f"media/{name}.tga is missing"
        data = path.read_bytes()
        if len(data) != 18 + w * h * 4:
            return f"{name}.tga is {len(data)} bytes, expected {18 + w * h * 4} for {w}x{h}"
        idtype, = struct.unpack("<B", data[2:3])
        width, height, depth, desc = struct.unpack("<HHBB", data[12:18])
        if (idtype, width, height, depth, desc) != (2, w, h, 32, 0x28):
            return f"{name}.tga header is {(idtype, width, height, depth, desc)}"
        if any(n & (n - 1) for n in (width, height)):
            return f"{name}.tga {width}x{height} is not a power of two"
        # canvas units agree with the texel size at an even texel density per axis
        if abs(w / uw - h / uh) > 1e-9:
            return f"{name}: texels per unit differ between the axes ({w}/{uw} vs {h}/{uh})"
        alpha = data[18 + 3::4]
        if max(alpha) == 0:
            return f"{name}.tga is empty"
        # the shape must not touch the canvas edge: a clipped stroke or halo would show a hard line
        edge = [alpha[x] for x in range(w)] + [alpha[(h - 1) * w + x] for x in range(w)]
        edge += [alpha[y * w] for y in range(h)] + [alpha[y * w + w - 1] for y in range(h)]
        limit = 3 if name == "hud_shard_glow" else 0
        if max(edge) > limit:
            return f"{name}.tga has alpha {max(edge)} on its border, the canvas clips the shape"
    tex_w, tex_h, units_w, units_h = gen.LINE_TEX
    if (units_h - gen.SH_H) / 2 * (tex_h / units_h) != 28:
        return "the line canvas does not centre the 18 unit box 28 texels in from the top (4 texels per unit)"
    return None


@file_check("hud_tile_texture_is_the_mockups_135_degree_gradient_with_a_generator")
def _tile():
    gen = ADDON / "media" / "generate_hud_tile.py"
    tga = ADDON / "media" / "hud_tile_cut2.tga"
    if not gen.exists():
        return "media/generate_hud_tile.py is missing"
    if not tga.exists():
        return "media/hud_tile_cut2.tga is missing"
    src = MOCKUP.read_text(encoding="utf-8")
    rule = re.search(r"(?m)^\.hud-ic \.tile, \.hud-next, \.hud-buff \{([^}]*)\}", src)
    if not rule or "linear-gradient(135deg, var(--surface), var(--bg))" not in rule.group(1):
        return "mockup's tile gradient changed; update the generator and this check"
    def colour(name):
        m = re.search(rf"--{name}:\s*#([0-9a-fA-F]{{6}})", src)
        return tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))
    surface, bg = colour("surface"), colour("bg")
    raw = tga.read_bytes()
    if raw[2] != 2 or raw[16] != 32 or raw[17] != 0x28:
        return "hud_tile_cut2.tga is not an uncompressed 32 bit top-left TGA"
    w, h = raw[12] | raw[13] << 8, raw[14] | raw[15] << 8
    if w != h or len(raw) != 18 + w * h * 4:
        return f"hud_tile_cut2.tga has a bad size {w}x{h}, {len(raw)} bytes"
    def px(x, y):
        o = 18 + (y * w + x) * 4
        return (raw[o + 2], raw[o + 1], raw[o], raw[o + 3])
    def near(a, b, tol=2):
        return all(abs(p - q) <= tol for p, q in zip(a, b))
    # The two-corner cut: TOP-LEFT and BOTTOM-RIGHT chamfered in alpha at 1/6 of the tile, the
    # other two corners and the whole interior opaque.
    cut = tile_cut_fraction() * w
    if abs(tile_cut_fraction() - 1 / 6) > 1e-9:
        return "the cut is 1/6 of the tile (6 px on the 36 px spell tile); update the ring sizes in CombatHud.lua with it"
    if px(0, 0)[3] != 0 or px(w - 1, h - 1)[3] != 0:
        return "the top left and bottom right corners must be cut away (alpha 0)"
    if px(w - 1, 0)[3] != 255 or px(0, h - 1)[3] != 255:
        return "the top right and bottom left corners must stay square (opaque)"
    k = int(cut / 2) - 1
    if px(k, k)[3] != 0 or px(w - 1 - k, h - 1 - k)[3] != 0:
        return f"the chamfer should clear ({k}, {k}) at both cut corners (cut {cut:.1f} texels)"
    far = int(cut) + 2
    if px(far, far)[3] != 255 or px(w - 1 - far, h - 1 - far)[3] != 255 or px(w // 2, h // 2)[3] != 255:
        return "the tile must be opaque past the chamfer"
    # the gradient is the same as hud_tile.tga's RGB, byte for byte, even under the cut
    plain = (ADDON / "media" / "hud_tile.tga")
    if plain.exists():
        praw = plain.read_bytes()
        if praw[18:] and len(praw) == len(raw):
            for i in range(18, len(raw), 4):
                if raw[i:i + 3] != praw[i:i + 3]:
                    return "hud_tile_cut2.tga RGB differs from hud_tile.tga: the gradient must be identical"
    if not near(px(w - 1, 0)[:3], tuple((a + b) / 2 for a, b in zip(surface, bg)), 2):
        return f"top right is on the anti diagonal, the midpoint of the gradient, got {px(w - 1, 0)[:3]}"
    if not near(px(far, far)[:3], surface, 40):
        return f"just past the top left cut the fill should still be near --surface {surface}, got {px(far, far)[:3]}"
    mid = tuple((a + b) / 2 for a, b in zip(surface, bg))
    for x, y in ((w - 1, 0), (0, h - 1), (w // 2, h // 2 - 1)):
        if not near(px(x, y)[:3], mid, 2):
            return f"the anti diagonal ({x}, {y}) should be the midpoint {mid}, got {px(x, y)[:3]}"
    for x, y in ((3, 40), (10, 50), (20, 5)):
        if px(x, y) != px(y, x):
            return f"a 135 degree gradient is symmetric about the diagonal; ({x}, {y}) differs from ({y}, {x})"
    if px(8, 8)[:3] == px(8, 9)[:3] == px(9, 8)[:3]:
        return "no gradient steps between neighbours"
    return None


@file_check("combathud_uses_the_cut2_tile_and_no_flat_edges_or_square_glows")
def _cut_source():
    src = COMBATHUD.read_text(encoding="utf-8")
    if "hud_tile_cut2.tga" not in src:
        return "CombatHud.lua does not use media/hud_tile_cut2.tga"
    if re.search(r'hud_tile\.tga"', src):
        return "CombatHud.lua still points at the square hud_tile.tga"
    if "FlatEdges" in src:
        return "CombatHud.lua still builds FlatEdges (square strips); rings and borders are cut outlines"
    if re.search(r"AddOuterGlow\([^\n]*,\s*0\s*\)", src):
        return "CombatHud.lua still calls AddOuterGlow with radius 0 (a square glow)"
    return None


@file_check("no_dead_fshasslots_field_is_left_in_combathud")
def _dead():
    if "fsHasSlots" in COMBATHUD.read_text(encoding="utf-8"):
        return "the dead containers.target.fsHasSlots test is still in CombatHud.lua"
    return None


@file_check("slot_to_binding_table_matches_actionbars")
def _bindings():
    def first_slot(text: str, token: str, symbol: str) -> int | None:
        """A literal first slot, or the symbol derived from its file's MULTIBAR_5_ACTIONBAR_PAGE
        fallback: (page - 1) * 12 + 1, the same rule both files apply at load."""
        if token.isdigit():
            return int(token)
        if token != symbol:
            return None
        page = re.search(r"MULTIBAR_5_ACTIONBAR_PAGE or (\d+)", text)
        return (int(page.group(1)) - 1) * 12 + 1 if page else None

    ab = (ADDON / "ActionBars.lua").read_text(encoding="utf-8")
    pairs = re.findall(r"firstAction = (\w+),[^}]*binding = \"([A-Z0-9]+)\"", ab)
    want = {first_slot(ab, first, "MULTIBAR5_FIRST_ACTION"): prefix for first, prefix in pairs}
    want[1] = "ACTIONBUTTON"
    hud = COMBATHUD.read_text(encoding="utf-8")
    got = {int(first): prefix for first, prefix in re.findall(r"first = (\d+), prefix = \"([A-Z0-9]+)\"", hud)}
    if len(want) < 6 or None in want or None in got:
        return "could not read BARS out of ActionBars.lua"
    if got != want:
        return f"CombatHud slot ranges {got} differ from ActionBars.lua BARS {want}"
    return None


def run_case(name: str, cls: str, body: str, gunsight: bool = False) -> str | None:
    if not COMBATHUD.exists():
        return f"{COMBATHUD.name} is missing"
    try:
        lua = build_runtime(cls, gunsight)
        if name in PRELUDES:
            lua.execute(PRELUDES[name])
        lua.eval("__loadCombatHud")(COMBATHUD.read_text(encoding="utf-8"))
    except LuaError as err:
        return f"CombatHud.lua failed to load: {err}"
    try:
        lua.execute(body)
        lua.execute('check(#__touches == 0, "a secret was touched: " .. tostring(__touches[1]))')
    except LuaError as err:
        return str(err)
    return None


def main() -> int:
    failures = 0
    for name, cls, body, gunsight in CASES:
        error = run_case(name, cls, body, gunsight)
        if error is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      {error}")
    for name, fn in FILE_CASES.items():
        error = fn()
        if error is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      {error}")
    total = len(CASES) + len(FILE_CASES)
    print(f"{total - failures}/{total} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
