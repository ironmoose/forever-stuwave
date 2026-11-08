#!/usr/bin/env python3
"""Runs the real GunsightShamanShocks.lua (the shock disc and the Fire Nova ring) headless.

The Shaman Gunsight Class Module (GunsightShaman.lua) owns the module frame and the totem poles; this file is the second
lane of Concept A "Totem Poles" as polished by the design mockup "Shaman Shock Tracker Polish" (2026-11-07): the shared
Earth / Flame / Frost Shock cooldown is a carved rune disc with a Sowilo pixel bolt, a rim that refills clockwise and a bolt
that charges from its tip up (both drawn by the engine from the cooldown), a RDY / seconds label under it, a ready breath,
a cast beat and a ready beat; and the cyan ring around the Fire totem head while Fire Nova is ready with the NOVA footer
tag, as shipped. The zig-zag line under the poles is gone. It draws no KICK tag: that comes from GunsightTape.lua's class
neutral tag. GunsightShaman.lua calls it through FS.GunsightShamanShocks = { Build(frame), Seat(section, rect, scale),
OnShow(section), OnHide(section) }. The harness builds the section on a plain frame under a fake host, as
GunsightShaman.lua does. The checks pin:

  * the table holds exactly Build, Seat, OnShow and OnHide; Build hangs everything under the frame it is given, installs
    no OnUpdate and listens only to the player's own casts (a ledger that stays on through OnHide);
  * every piece at the mockup's offset from the rect's top left (numbers read out of the mockup), in the upper and the
    lower area, re-seated on a rescale, a bad rect tolerated; the baked art (cell order, box sizes, the bolt's rows) agrees
    with the generator and with the mockup's own polygon;
  * the disc: nothing without a shock, RDY with the lit rim, the ready bolt and the stepped halo breathing when the shared
    cooldown is off (a plain isActive of false, or a cooldown that is only the global one), the engine refill (the duration
    object into the bolt's StatusBar and the rim's reversed Cooldown) while it charges, the plain fallback without the API,
    the plain seconds out of combat, "~" and the cast ledger when the timing is secret in combat, a muted outline bolt and
    "?" when even isActive is secret, any rank of any shock starting the shared cooldown;
  * the beats: the cast flash, eight sparks and the fast drain (a mirrored swipe and a plain bar), the cooldown's end with
    its flash, expanding ring and white label, no beat for what happened while hidden or for an unknown shock; the shimmer,
    crackle and tip sparks of a ready bolt, the spark on the rim front, the seam under the fill's edge, the canvas clip;
  * secret values: not one is compared or computed on (the mock's secret raises), only handed to the engine's setters;
  * Fire Nova: nothing before it is learned (and it appears when it is), the ring and NOVA tag lit while it is ready, the
    tag dim and the ring gone on its cooldown, both gone when the poles say the Fire totem is down, the ring following the
    head the poles report;
  * no KICK tag and no target reads: the build makes none, and only the player's own casts and the view events listen;
  * OnHide stops the ticker and every view event, a cast while hidden is still ledgered, and OnShow re-reads everything;
  * the per frame path allocates nothing on the addon side, the beats included.

The mock is strict. It is NOT the real client.

    python3 tools/gunsightshamanshocks-harness.py

Exit 0 = every check passed. GUNSIGHTSHAMANSHOCKS_LUA=<path> runs another file in place of GunsightShamanShocks.lua.
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
ADDON = HERE.parent / "forever-stuwave"
SHOCKS = Path(os.environ.get("GUNSIGHTSHAMANSHOCKS_LUA") or ADDON / "Modules/CombatHud/GunsightShamanShocks.lua")
GUNSIGHT = ADDON / "Modules/CombatHud/Gunsight.lua"
LAYOUT = ADDON / "Core/Layout.lua"
CONFIG = ADDON / "Core/Config.lua"
FRAMEHELPERS = ADDON / "Core/FrameHelpers.lua"
TOC = ADDON / "forever-stuwave.toc"
TEXTURES = ADDON / "Media" / "Textures"
MOCKUP = HERE.parent / "mockups" / "gunsight-class-module-shaman-polish-2026-11-07.html"
GENERATOR = HERE / "assets" / "generate_shaman_disc.py"


def _load(name: str, folder: Path = HERE):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), folder / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CLASS_HARNESS = _load("gunsightclass-harness")


def _m(pattern: str, text: str, what: str) -> re.Match:
    m = re.search(pattern, text, re.S)
    if not m:
        sys.exit(f"mockup: cannot find {what} (pattern {pattern!r}); the mockup changed shape")
    return m


def dec(digits: str) -> float:
    """The digits after a decimal point as the number they are: '8' is .8, '08' is .08 (the mockup writes .8 and .08)."""
    return float("0." + digits)


def mockup_numbers() -> dict:
    """The numbers the polish mockup draws the rune disc, its beats, the Nova ring and the NOVA footer with, in image px."""
    src = MOCKUP.read_text(encoding="utf-8")
    geo = _m(r"const W=(\d+), H=(\d+), OX=(\d+), GY=(\d+), NB=(\d+), BP=(\d+), BH=(\d+), HEAD_H=(\d+);", src, "geometry")
    disc = _m(r"const SCX=(\d+), SCY=GY-(\d+), SR=(\d+);", src, "rune disc")
    pts = _m(r"const BOLT_PTS=(\[\[.*?\]\]);", src, "bolt polygon")
    shock = _m(r"function drawShock\(g,st\)\{(.*?)\n\}\nfunction RING_HALO", src, "drawShock").group(1)
    flash = _m(r"flash=\(rdyFlash&&sr<([\d.]+)\)\|\|\(!unk&&sc<([\d.]+)\)", shock, "flash")
    halo = _m(r"SR\+1,SR\+2,COL\.cyan,\.(\d+)\+halo\*\.(\d+)\).*?SR\+2,SR\+3,COL\.cyan,\.(\d+)\+halo\*\.(\d+)\)", shock, "halo")
    wash = _m(r"c=mix\(c,COL\.cyan,\.(\d+)\+halo\*\.(\d+)\)", shock, "ready wash")
    fl = _m(r"mix\(mix\(c,COL\.cyan,\.(\d+)\),COL\.white,\.(\d+)\)", shock, "flash wash")
    rim = _m(r"a=lit\?\.(\d+):\.(\d+)", shock, "rim alphas")
    rimmix = _m(r"mix\(COL\.cyan,COL\.white,Math\.max\(0,step20-\.(\d+)\)\*\.(\d+)\)", shock, "rim breath")
    bolt = _m(r"const bx=SCX, by=SCY, H=(\d+);", shock, "bolt fill scale")
    rows = _m(r"return \{px,out,top:(-?\d+),bot:(-?\d+)\}", src, "bolt rows")
    shim = _m(r"BOLT\.top\+Math\.floor\(\(t\*(\d+)\)%(\d+)\)-(\d+)", shock, "shimmer")
    crack = _m(r"const n=Math\.floor\(t\*(\d+)\);.*?hsh\(n\*3\+k\+21\)<([\d.]+)", shock, "crackle")
    burst = _m(r"if\(!unk&&sc<([\d.]+)\)\{ // cast burst.*?d=SR\+1\+sc\*(\d+)", shock, "cast burst")
    ring = _m(r"if\(rdyFlash&&sr>=([\d.]+)\)\{.*?r=SR\+1\+k\*(\d+), a=\(1-k\)\*\.(\d+)", shock, "ready ring")
    label = _m(r"txt\(g,lab,(\d+),SCY\+SR\+(\d+),(\d+),unk\?COL\.muted:ready\?\(rdyFlash&&sr<([\d.]+)\?COL\.white", shock, "label")
    breath = _m(r"step20=Math\.floor\(beat\(t,([\d.]+)\)\*20\)/20", shock, "breath")
    drain = _m(r"casting=!unk&&sc<([\d.]+)&&!ready", shock, "cast drain")
    rdy = _m(r"rdyFlash=ready&&sr<([\d.]+);", shock, "ready beat")
    ringc = _m(r"const cx=fireHead\.cx, cy=fireHead\.hy\+3;.*?g\.arc\(cx,cy,(\d+),0,Math\.PI\*2\).*?moveTo\(cx\+(\d+)\*Math\.cos", src, "Nova ring")
    foot = _m(r"g\.moveTo\(OX\+(\d+)\+(\d+)\*Math\.cos\(a0\),GY\+(\d+)\+(\d+)\+(\d+)\*Math\.sin.*?txt\(g,'NOVA',OX\+(\d+),GY\+(\d+)\+(\d+),(\d+)",
              src, "NOVA footer")
    fire = _m(r"key:'fire',\s*x:(\d+),\s*w:(\d+)", src, "Fire pole")
    W, H, OX, GY, NB, BP, BH, HEAD_H = (int(geo.group(i)) for i in range(1, 9))
    gy = GY
    polygon = [tuple(int(v) for v in p.split(",")) for p in re.findall(r"\[(-?\d+,-?\d+)\]", pts.group(1))]
    return {
        "W": W, "H": H, "OX": OX, "GY": gy, "NB": NB, "BP": BP,
        "SCX": int(disc.group(1)), "SCY": gy - int(disc.group(2)), "SR": int(disc.group(3)),
        "BOLT_PTS": polygon, "BOLT_SPAN": int(bolt.group(1)), "BOLT_TOP": int(rows.group(1)), "BOLT_BOT": int(rows.group(2)),
        "RDY_FLASH": float(flash.group(1)), "CAST_FLASH": float(flash.group(2)),
        "HALO1": [dec(halo.group(1)), dec(halo.group(2))], "HALO2": [dec(halo.group(3)), dec(halo.group(4))],
        "WASH": [dec(wash.group(1)), dec(wash.group(2))], "FLASH_WASH": [dec(fl.group(1)), dec(fl.group(2))],
        "RIM_A": dec(rim.group(1)), "RIM_DIM_A": dec(rim.group(2)),
        "RIM_BREATH": [dec(rimmix.group(1)), dec(rimmix.group(2))],
        "SHIMMER": int(shim.group(1)), "SHIMMER_SPAN": int(shim.group(2)), "SHIMMER_BACK": int(shim.group(3)),
        "CRACKLE": int(crack.group(1)), "CRACKLE_P": float(crack.group(2)),
        "CAST_BURST": float(burst.group(1)), "BURST_SPEED": int(burst.group(2)),
        "RDY_RING_FROM": float(ring.group(1)), "RING_GROW": int(ring.group(2)), "RING_A": dec(ring.group(3)),
        "LABEL_X": int(label.group(1)), "LABEL_DY": int(label.group(2)), "LABEL_SIZE": int(label.group(3)),
        "RDY_LABEL": float(label.group(4)),
        "BREATH": float(breath.group(1)), "DRAIN": float(drain.group(1)), "RDY_BEAT": float(rdy.group(1)),
        "RING_OUT": int(ringc.group(1)), "RING_IN": int(ringc.group(2)),
        "PIP_X": OX + int(foot.group(1)), "PIP_R": int(foot.group(2)), "FOOT_DY": int(foot.group(3)), "PIP_DY": int(foot.group(4)),
        "NOVA_X": OX + int(foot.group(6)), "NOVA_BASE": int(foot.group(8)), "NOVA_SIZE": int(foot.group(9)),
        "FIRE_X": OX + int(fire.group(1)) + int(fire.group(2)) // 2,
        "FIRE_Y": gy - NB * BP - HEAD_H + 3,
    }


def lua_value(v) -> str:
    if isinstance(v, dict):
        return "{" + ",".join(f"{k}={lua_value(x)}" for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        return "{" + ",".join(lua_value(x) for x in v) + "}"
    if isinstance(v, str):
        return '"' + v + '"'
    return repr(v)


# ---------------------------------------------------------------------------------------
# The mock client: the Class harness's strict mock (itself the Dots harness's), plus the spell, cooldown and cast APIs
# ---------------------------------------------------------------------------------------

MOCK = CLASS_HARNESS.MOCK + r"""
do
    -- the frame kinds and calls the disc uses: a StatusBar driven by the engine's timer (it records the object it was given and how),
    -- a Cooldown (the rim's swipe: a plain SetCooldown refuses a secret, the duration object route takes anything), and clipping
    local create = CreateFrame
    function CreateFrame(kind, name, parent, template)
        local f
        if kind == "Cooldown" then
            f = create("Frame", name, parent, template)
            f.isCooldown = true
            function f:SetSwipeTexture(path) self.swipe = path end
            function f:SetSwipeColor() end
            function f:SetDrawEdge(on) self.drawEdge = on end
            function f:SetDrawBling(on) self.drawBling = on end
            function f:SetHideCountdownNumbers(on) self.hideNumbers = on end
            function f:SetReverse(on) self.reverse = on and true or false end
            function f:SetCooldown(start, dur)
                if SECRET_FN(start) or SECRET_FN(dur) then error("SetCooldown refuses a secret value from addon code", 2) end
                self.cd = { start, dur }
                self.fromObject = nil
            end
            function f:SetCooldownFromDurationObject(obj)
                self.fromObject = obj
                self.fromObjectCalls = (self.fromObjectCalls or 0) + 1
                self.cd = nil
            end
        else
            f = create(kind, name, parent, template)
        end
        if kind == "StatusBar" then
            function f:SetTimerDuration(obj, interp, dir)
                self.timer, self.timerInterp, self.timerDir = obj, interp, dir
                self.timerCalls = (self.timerCalls or 0) + 1
            end
        end
        function f:SetClipsChildren(on) self.clips = on and true or false end
        return f
    end
end
"""

PRELUDE = r"""
RECTS = { upper = { x = 1213, y = 500, w = 202, h = 128 }, lower = { x = 1213, y = 632, w = 202, h = 128 } }
NAMES = { [8042] = "Earth Shock", [25454] = "Earth Shock", [8050] = "Flame Shock", [10447] = "Flame Shock", [8056] = "Frost Shock",
    [408341] = "Fire Nova", [403] = "Lightning Bolt", [1535] = "Fire Nova Totem" }
IDOF = { ["Earth Shock"] = 8042, ["Flame Shock"] = 8050, ["Frost Shock"] = 8056, ["Fire Nova"] = 408341 }
KNOWN = {}
CD, CD_CALLS, DUR_CALLS, DUR = {}, 0, 0, {}
USABLE = {}
local RESULT, INFO = {}, {}                       -- reused: the mock's own tables are not what the cases count
SECRET_FN = function(v) return v == SECRET end

local function mockSpells()
    C_Spell = {
        GetSpellInfo = function(x)
            local id = type(x) == "number" and x or IDOF[x]
            if not id or not NAMES[id] then return nil end
            if type(x) == "string" and not KNOWN[id] then return nil end    -- by name only a spell in the book answers
            INFO.name, INFO.spellID, INFO.iconID = NAMES[id], id, 1
            return INFO
        end,
        GetSpellName = function(id) return NAMES[id] end,
        GetSpellCooldown = function(id)
            CD_CALLS = CD_CALLS + 1
            local c = CD[id]
            if not c then return nil end
            RESULT.isActive, RESULT.isOnGCD, RESULT.startTime, RESULT.duration = c.isActive, c.isOnGCD, c.startTime, c.duration
            return RESULT
        end,
        GetSpellCooldownDuration = function(id)
            DUR_CALLS = DUR_CALLS + 1
            DUR[id] = DUR[id] or { durationFor = id }
            return DUR[id]
        end,
        IsSpellUsable = function(id)
            local u = USABLE[id]
            if u == nil then return true, false end
            return u[1], u[2]
        end,
    }
    IsPlayerSpell = function(id) return KNOWN[id] == true end
    IsSpellKnown = function(id) return KNOWN[id] == true end
end

local function learn(...)
    for _, name in ipairs({ ... }) do KNOWN[IDOF[name]] = true end
end
local function setCd(id, active, onGcd, start, dur) CD[id] = { isActive = active, isOnGCD = onGcd, startTime = start, duration = dur } end
local function cdReady(id) setCd(id, false, false, 0, 0) end
local function cdPlain(id, left, total) setCd(id, true, false, NOW - (total - left), total) end   -- out of combat: plain timing
local function cdSecret(id) setCd(id, true, false, SECRET, SECRET) end                           -- in combat: isActive plain, timing secret
local function cdBlind(id) setCd(id, SECRET, SECRET, SECRET, SECRET) end
local EARTH, FLAME, FROST, NOVA = 8042, 8050, 8056, 408341
-- every spell off cooldown unless a case says otherwise
local function allReady() for _, id in ipairs({ EARTH, FLAME, FROST, NOVA }) do cdReady(id) end end

local function boot(opts)
    opts = opts or {}
    STRICT_EVENTS = false
    resetKnownEvents()
    for e in ([[SPELL_UPDATE_COOLDOWN SPELLS_CHANGED LEARNED_SPELL_IN_SKILL_LINE PLAYER_LEVEL_UP UNIT_SPELLCAST_SUCCEEDED
        SPELL_UPDATE_USABLE PLAYER_REGEN_ENABLED PLAYER_REGEN_DISABLED]]):gmatch("%S+") do
        KNOWN_EVENTS[e] = true     -- any other event (a target cast, a target change) is refused and would be logged
    end
    resetWorld()
    SetScreen(opts.height or 1440)
    KNOWN, CD, USABLE, DUR = {}, {}, {}, {}
    CD_CALLS, DUR_CALLS = 0, 0
    NOW = 5000
    Enum = { StatusBarTimerDirection = { ElapsedTime = 1, RemainingTime = 0 }, StatusBarInterpolation = { Immediate = 0 } }
    FS.IsSecret = function(v) return SECRET_FN(v) end
    stubTheme_()
    local T = FS.Theme
    T.COLOR_TEXT_WHITE = { 1, 1, 1, 1 }
    T.COLOR_POWER = { 0.133, 0.878, 1, 1 }
    T.COLOR_MUTED = { 0.6157, 0.5765, 0.7686, 1 }
    T.COLOR_HUD_SCRIM = { 0.051, 0.024, 0.125, 0.4675 }
    stubHud_()
    assert(loadstring(HAS_TARGET_SRC, "@Theme.lua"))()
    loadAddonFile(LAYOUT_SRC, "Core/Layout.lua")
    loadAddonFile(CONFIG_SRC, "Core/Config.lua")
    loadAddonFile(FRAMEHELPERS_SRC, "Core/FrameHelpers.lua")
    loadAddonFile(GUNSIGHT_SRC, "Modules/CombatHud/Gunsight.lua")
    UnitExists = function() return true end
    UnitClass = function() return "Shaman", "SHAMAN" end
    mockSpells()
    if opts.known ~= false then learn("Earth Shock", "Flame Shock", "Fire Nova") end
    if opts.ready ~= false then allReady() end
    FRAMES_BEFORE = #FRAMES
    loadAddonFile(SHOCKS_SRC, "Modules/CombatHud/GunsightShamanShocks.lua")
    Shocks = FS.GunsightShamanShocks
    fire("ADDON_LOADED", "forever-stuwave")
    fire("PLAYER_LOGIN")
end

-- Builds the section the way GunsightShaman.lua does: a plain frame under a host, then Build, Seat, OnShow
local function mount(area, opts)
    opts = opts or {}
    STRICT_EVENTS = true
    HOST = CreateFrame("Frame", nil, FS.Gunsight.root)
    HOST:SetSize(1, 1)
    FRAME = CreateFrame("Frame", nil, HOST)
    FRAME:SetAllPoints(HOST)
    local before = #FRAMES
    SEC = Shocks.Build(FRAME)
    check(type(SEC) == "table", "Build(frame) returned no section")
    BUILT = before
    AREA = area or "lower"
    Shocks.Seat(SEC, RECTS[AREA], 1.28)
    if opts.show ~= false then Shocks.OnShow(SEC) end
    return SEC
end

local function under(r, frame)
    while r do if r == frame then return true end; r = r.parent end
    return false
end
local function built()           -- the frames the module made, in creation order
    local list = {}
    for i = BUILT + 1, #FRAMES do list[#list + 1] = FRAMES[i] end
    return list
end
local function listeners()
    local n = 0
    for _, f in ipairs(FRAMES) do
        for _ in pairs(f.events) do n = n + 1 end
        if f.scripts.OnUpdate then n = n + 1 end
    end
    return n
end
local function onUpdates() return onUpdateFrames() end
local function noDegrade() check(next(DEGRADED) == nil, "a degrade was logged: " .. tostring(next(DEGRADED))) end
local function vis(r) return r ~= nil and isVisible(r) end
local function tintIs(r, rr, gg, bb, aa, what)
    local v = r.vertex
    check(v and math.abs(v[1] - rr) < 0.005 and math.abs(v[2] - gg) < 0.005 and math.abs(v[3] - bb) < 0.005
        and (aa == nil or math.abs(v[4] - aa) < 0.005),
        (what or "tint") .. ": got " .. (v and string.format("%.3f %.3f %.3f %.3f", v[1], v[2], v[3], v[4]) or "nil")
        .. ", want " .. string.format("%.3f %.3f %.3f %s", rr, gg, bb, tostring(aa)))
end
local function cyanTint(r)
    local v = r.vertex
    return math.abs(v[1] - 0.133) < 0.01 and math.abs(v[2] - 0.878) < 0.01 and math.abs(v[3] - 1) < 0.01
end
local function mutedTint(r)
    local v = r.vertex
    return math.abs(v[1] - 0.6157) < 0.01 and math.abs(v[2] - 0.5765) < 0.01
end
local function textRgb(fs) local c = fs.textColor; return c[1], c[2], c[3] end
local function cast(id, unit) fire("UNIT_SPELLCAST_SUCCEEDED", unit or "player", "guid", id) end
local function nearRect(r, x, y, w, h, what)
    local l, t, rw, rh = imgRect(r)
    near(l, x, what .. " left", 0.02); near(t, y, what .. " top", 0.02)
    if w then near(rw, w, what .. " width", 0.02) end
    if h then near(rh, h, what .. " height", 0.02) end
end
local CAP = 325 / 1024      -- Mononoki's line centre above the baseline, as GunsightSeals.lua uses it
local floor, sin, cos, pi = math.floor, math.sin, math.cos, math.pi
-- the mockup's drawShock in Lua: the same expressions, from the mockup's own numbers
local function beatOf(t) return 0.5 + 0.5 * sin(t * 2 * pi / MU.BREATH) end
local function step20(t) return floor(beatOf(t) * 20) / 20 end
local function boltFraction(p) return (16 - MU.BOLT_BOT + MU.BOLT_SPAN * p) / 32 end     -- the box is 32 px tall, the tip's bottom edge 4 px above its bottom
local function runTicks(n, dt) for i = 1, n do tick(dt or 0.04) end end
"""

CASES: list[tuple[str, str]] = []


def case(name: str):
    def deco(body: str):
        CASES.append((name, body))
        return body
    return deco


case("the_table_holds_exactly_the_four_functions")(r"""
boot({})
local n = 0
for k, v in pairs(Shocks) do
    n = n + 1
    check(k == "Build" or k == "Seat" or k == "OnShow" or k == "OnHide", "unexpected key " .. tostring(k))
    check(type(v) == "function", tostring(k) .. " is not a function")
end
check(n == 4, "the table must hold exactly Build, Seat, OnShow and OnHide, has " .. n)
noDegrade()
""")

case("build_hangs_everything_under_the_frame_and_installs_no_ticker")(r"""
boot({})
local texBefore, strBefore = #TEXTURES, #FONTSTRINGS
local before = listeners()
mount("lower", { show = false })
check(#built() > 0, "Build made no frame")
for _, f in ipairs(built()) do check(under(f, FRAME), "a frame is not under the module frame") end
for i = texBefore + 1, #TEXTURES do check(under(TEXTURES[i], FRAME), "a texture is not under the module frame") end
for i = strBefore + 1, #FONTSTRINGS do check(under(FONTSTRINGS[i], FRAME), "a font string is not under the module frame") end
check(onUpdates() == 0, "no OnUpdate before the first show")
check(listeners() - before == 1, "only the player's own cast ledger listens before the first show, got " .. (listeners() - before))
for _, f in ipairs(built()) do
    check(not f:IsProtected(), "no protected frame")
end
check(SEC.kick == nil and SEC.kickLabel == nil, "no KICK tag of its own: GunsightTape.lua draws it")
noDegrade()
""")

case("the_zig_zag_line_is_gone_and_its_art_is_not_loaded")(r"""
boot({})
mount("lower")
check(SEC.base == nil and SEC.ready == nil and SEC.glow == nil, "no trace parts")
check(SEC.boltFill == nil and SEC.boltLine == nil and SEC.boltGlow == nil, "no flat bolt parts")
for _, t in ipairs(TEXTURES) do
    check(not (t.path and (t.path:find("shock_trace", 1, true) or t.path:find("shock_bolt_", 1, true))), "an old trace or bolt texture is loaded: " .. tostring(t.path))
end
noDegrade()
""")

case("nothing_is_drawn_without_a_shock_or_nova_in_the_book")(r"""
boot({ known = false })
mount("lower")
for _, name in ipairs({ "disc", "tint", "dots", "rimDim", "rimFill", "rimDrain", "rimLit", "notches", "spark", "outline", "boltEmpty",
    "boltMuted", "boltReady", "bar", "drain", "flashBolt", "halo1", "halo2", "seam", "shimA", "shimB", "ringG", "label" }) do
    check(not vis(SEC[name]), name .. " is drawn without a shock")
end
for i = 1, 6 do check(not vis(SEC.crack[i]), "no crackle") end
for i = 1, 24 do check(not vis(SEC.burst[i]), "no cast spark") end
check(not vis(SEC.ring) and not vis(SEC.pip) and not vis(SEC.novaText), "no Nova pieces before Fire Nova is learned")
check(onUpdates() == 0, "nothing ticks")
noDegrade()
""")

case("a_ready_shock_lights_the_disc_and_breathes")(r"""
boot({})
mount("lower")
for _, name in ipairs({ "disc", "dots", "rimDim", "notches", "outline", "rimLit", "tint", "boltReady", "halo1", "halo2", "shimA", "shimB" }) do
    check(vis(SEC[name]), name .. " is drawn when ready")
end
check(not vis(SEC.boltEmpty) and not vis(SEC.boltMuted), "no empty or muted bolt when ready")
check(not vis(SEC.bar) and not vis(SEC.rimFill) and not vis(SEC.drain) and not vis(SEC.rimDrain) and not vis(SEC.seam) and not vis(SEC.spark), "no refill when ready")
check(not vis(SEC.flashBolt) and not vis(SEC.ringG), "no beat on the first show")
check(vis(SEC.label) and SEC.label.text == "RDY", "the label says RDY, got " .. tostring(SEC.label.text))
local r, g, b = textRgb(SEC.label)
check(math.abs(r - 0.133) < 0.01 and math.abs(b - 1) < 0.01, "RDY is cyan")
check(onUpdates() == 1, "a ready shock breathes: one ticker")
-- the breath: the halos, the wash and the rim step with beat(t, 1.6) in 20 steps
local W = { 243 / 255, 251 / 255, 1 }
local C = { 0.133, 0.878, 1 }
local seen = {}
for i = 1, 40 do
    tick(0.05)
    local h = step20(NOW)
    tintIs(SEC.halo1, C[1], C[2], C[3], MU.HALO1[1] + h * MU.HALO1[2], "inner halo")
    tintIs(SEC.halo2, C[1], C[2], C[3], MU.HALO2[1] + h * MU.HALO2[2], "outer halo")
    tintIs(SEC.tint, C[1], C[2], C[3], MU.WASH[1] + h * MU.WASH[2], "plate wash")
    local t = math.max(0, h - MU.RIM_BREATH[1]) * MU.RIM_BREATH[2]
    tintIs(SEC.rimLit, C[1] + (W[1] - C[1]) * t, C[2] + (W[2] - C[2]) * t, C[3] + (W[3] - C[3]) * t, MU.RIM_A, "lit rim")
    seen[h] = true
end
local n = 0
for _ in pairs(seen) do n = n + 1 end
check(n >= 6, "the breath goes through several steps in two seconds, saw " .. n)
noDegrade()
""")

case("a_cooldown_that_is_only_the_global_one_reads_ready")(r"""
boot({})
setCd(8042, true, true, SECRET, SECRET)
mount("lower")
check(SEC.label.text == "RDY", "isOnGCD true is ready, got " .. tostring(SEC.label.text))
setCd(8042, true, false, NOW - 0.5, 1.5)
fire("SPELL_UPDATE_COOLDOWN")
check(SEC.label.text == "RDY", "a plain cooldown no longer than the global one is ready, got " .. tostring(SEC.label.text))
noDegrade()
""")

case("a_shock_on_cooldown_out_of_combat_shows_the_plain_seconds_and_refills_through_the_engine")(r"""
boot({})
cdPlain(8042, 4, 6)
mount("lower")
for _, name in ipairs({ "disc", "dots", "rimDim", "notches", "outline", "boltEmpty", "bar", "rimFill", "seam" }) do
    check(vis(SEC[name]), name .. " is drawn while charging")
end
check(not vis(SEC.rimLit) and not vis(SEC.halo1) and not vis(SEC.halo2) and not vis(SEC.tint) and not vis(SEC.boltReady) and not vis(SEC.boltMuted), "none of the ready looks")
check(not vis(SEC.drain) and not vis(SEC.rimDrain) and not vis(SEC.flashBolt), "no cast drain without a cast")
check(SEC.bar.timer ~= nil and SEC.bar.timer.durationFor == 8042, "the bolt fills from the cooldown's duration object")
check(SEC.bar.timerDir == 1 and SEC.bar.timerInterp == 0, "elapsed time, no interpolation")
check(SEC.rimFill.fromObject == SEC.bar.timer, "the rim takes the same duration object")
check(SEC.rimFill.reverse == true, "the rim swipe is reversed: the elapsed arc grows clockwise")
check(SEC.rimDrain.reverse == false, "the drain swipe is not")
check(SEC.rimFill.swipe:find("shaman_disc_rim.tga", 1, true) and SEC.rimDrain.swipe:find("shaman_disc_rim_mirror.tga", 1, true), "the swipe arts")
check(SEC.bar.max == 1 and SEC.bar.min == 0, "a 0 to 1 bar")
check(SEC.label.text == "4s", "plain seconds above 3 are whole, got " .. tostring(SEC.label.text))
local r = textRgb(SEC.label)
check(r > 0.9, "the seconds are white")
check(onUpdates() == 1, "a charging shock ticks")
tick(1)
check(SEC.label.text == "3s", "one second later, got " .. tostring(SEC.label.text))
tick(0.8)
check(SEC.label.text == "2.2s", "under 3 s the tenths show, got " .. tostring(SEC.label.text))
cdReady(8042)
fire("SPELL_UPDATE_COOLDOWN")
check(SEC.label.text == "RDY" and vis(SEC.rimLit) and vis(SEC.boltReady), "the lit looks come back when the cooldown ends, got " .. tostring(SEC.label.text))
check(not vis(SEC.bar) and not vis(SEC.rimFill) and not vis(SEC.seam), "the refill goes")
noDegrade()
""")

case("the_refill_falls_back_to_numbers_without_the_duration_object_api")(r"""
boot({})
cdPlain(8042, 3, 6)
C_Spell.GetSpellCooldownDuration = nil
mount("lower")
check(vis(SEC.bar) and SEC.bar.timer == nil, "no timer without the API")
check(vis(SEC.rimFill) and SEC.rimFill.fromObject == nil and SEC.rimFill.cd ~= nil, "the rim is fed a plain start and length")
near(SEC.rimFill.cd[1], NOW - 3, "start", 0.001); near(SEC.rimFill.cd[2], 6, "length", 0.001)
near(SEC.bar.value, boltFraction(0.5), "the bolt is the spent share on the mockup's fill scale", 0.003)
tick(1.5)
near(SEC.bar.value, boltFraction(0.75), "and it follows the clock", 0.005)
noDegrade()
""")

case("the_rim_spark_rides_the_front_of_the_refill")(r"""
boot({})
cdPlain(8042, 4.2, 6)                 -- the share 0.3
mount("lower")
local R = RECTS.lower
local ang = 0.3 * 2 * pi
local x, y = floor(sin(ang) * (MU.SR - 0.9)), floor(-cos(ang) * (MU.SR - 0.9))   -- the mockup's Math.round(v - .5)
check(vis(SEC.spark), "the spark shows while charging")
nearRect(SEC.spark, R.x + MU.SCX + x, R.y + MU.SCY + y, 1, 1, "spark")
tintIs(SEC.spark, 243 / 255, 251 / 255, 1, nil, "spark")
tick(1.2)                              -- the share 0.5
nearRect(SEC.spark, R.x + MU.SCX + floor(sin(pi) * (MU.SR - 0.9)), R.y + MU.SCY + floor(-cos(pi) * (MU.SR - 0.9)), 1, 1, "spark at the bottom")
cdReady(8042); fire("SPELL_UPDATE_COOLDOWN")
check(not vis(SEC.spark), "no spark once ready")
noDegrade()
""")

case("the_seam_hangs_from_the_fill_edge_and_the_sparks_are_clipped_to_the_canvas")(r"""
boot({})
cdPlain(8042, 4, 6)
mount("lower")
local R = RECTS.lower
local fill = SEC.bar:GetStatusBarTexture()
check(fill ~= nil, "the bolt bar has a fill texture")
check(SEC.seam.clips == true and vis(SEC.seam), "a clipping frame while charging")
check(#SEC.seam.points == 2, "two anchors")
check(SEC.seam.points[1][1] == "TOPLEFT" and SEC.seam.points[1][2] == fill and SEC.seam.points[1][3] == "TOPLEFT", "left to the fill's top left")
check(SEC.seam.points[2][1] == "TOPRIGHT" and SEC.seam.points[2][2] == fill and SEC.seam.points[2][3] == "TOPRIGHT", "right to the fill's top right")
near(SEC.seam.h, 1.25 * FS.Gunsight.ui(1), "a little over a px tall", 0.001)
check(SEC.shimA.clips and SEC.shimB.clips, "the shimmer rows clip")
check(SEC.canvas.clips == true, "the canvas clips its children")
nearRect(SEC.canvas, R.x, R.y, MU.W, MU.H, "canvas")
check(SEC.burst[1].parent == SEC.canvas and SEC.crack[1].parent == SEC.canvas and SEC.tips[1].parent == SEC.canvas, "the sparks are in the canvas")
check(SEC.ringG.parent == SEC.canvas and SEC.rdyRing[1].parent == SEC.ringG and #SEC.rdyRing == 72, "the ring's 72 px are in the canvas")
cdReady(8042); fire("SPELL_UPDATE_COOLDOWN")
check(not vis(SEC.seam), "no seam when ready")
noDegrade()
""")

case("secret_timing_in_combat_uses_the_cast_ledger_and_marks_the_estimate")(r"""
boot({})
IN_COMBAT = true
mount("lower")
cdSecret(8042)
cast(25454)                                  -- Earth Shock rank 5: the client reports the rank id, the name is the key
check(SEC.label.text == "~6s", "just cast: an estimated 6 s, got " .. tostring(SEC.label.text))
check(vis(SEC.drain), "the first 0.3 s drain")
tick(0.35)
check(vis(SEC.bar) and vis(SEC.rimFill) and not vis(SEC.rimLit), "charging")
check(SEC.bar.timer ~= nil, "the engine still draws the fill from the duration object (a secret one is handed over untouched)")
check(SEC.rimFill.fromObject ~= nil, "and the rim")
tick(2.65)
check(SEC.label.text == "~3s", "got " .. tostring(SEC.label.text))
tick(1.5)
check(SEC.label.text == "~1.5s", "got " .. tostring(SEC.label.text))
tick(1.6)
check(SEC.label.text == "RDY" and vis(SEC.rimLit), "the ledger says elapsed: ready, got " .. tostring(SEC.label.text))
noDegrade()
""")

case("a_plain_false_is_trusted_over_the_ledger_in_combat")(r"""
boot({})
IN_COMBAT = true
mount("lower")
cdSecret(8042)
cast(8042)
check(SEC.label.text == "~6s", "ledger charging")
cdReady(8042)                                -- a reset (or a cooldown the ledger did not know): the client says off
fire("SPELL_UPDATE_COOLDOWN")
check(SEC.label.text == "RDY", "a plain isActive of false is ready whatever the ledger says, got " .. tostring(SEC.label.text))
noDegrade()
""")

case("secret_active_flag_reads_unknown_and_guesses_nothing")(r"""
boot({})
IN_COMBAT = true
cdBlind(8042)
mount("lower")
for _, name in ipairs({ "disc", "dots", "rimDim", "notches", "outline", "boltMuted" }) do
    check(vis(SEC[name]), name .. " stays")
end
for _, name in ipairs({ "boltEmpty", "boltReady", "rimLit", "tint", "halo1", "halo2", "bar", "rimFill", "drain", "rimDrain", "flashBolt", "shimA", "spark", "seam" }) do
    check(not vis(SEC[name]), name .. " is not drawn when unknown")
end
check(SEC.label.text == "?", "the label says ?, got " .. tostring(SEC.label.text))
local r = textRgb(SEC.label)
check(math.abs(r - 0.6157) < 0.01, "? is muted")
check(onUpdates() == 0, "nothing moves")
cast(8042)                                   -- an own cast while nothing is knowable: no beat, no guess
check(not vis(SEC.flashBolt) and not vis(SEC.burst[1]) and not vis(SEC.drain), "no beat for an unknown shock")
noDegrade()
""")

case("a_secret_cooldown_value_is_never_computed_on")(r"""
boot({})
IN_COMBAT = true
mount("lower")
cdSecret(8042)
cast(8042)
for i = 1, 40 do tick(0.1) end               -- the mock's secret raises on any arithmetic or comparison; a throw would be logged
cdSecret(408341)
fire("SPELL_UPDATE_COOLDOWN")
cdBlind(408341); cdBlind(8042)
fire("SPELL_UPDATE_COOLDOWN")
noDegrade()
""")

case("any_rank_of_any_shock_starts_the_shared_cooldown_and_other_spells_do_not")(r"""
boot({})
IN_COMBAT = true
learn("Frost Shock")
mount("lower")
cdSecret(8042)
cast(403)                                    -- Lightning Bolt
check(SEC.label.text == "RDY", "another spell never starts the shock cooldown, got " .. tostring(SEC.label.text))
cast(10447)                                  -- Flame Shock rank 2
check(SEC.label.text == "~6s", "Flame Shock shares the cooldown, got " .. tostring(SEC.label.text))
cdReady(8042); fire("SPELL_UPDATE_COOLDOWN")
cdSecret(8042)
cast(8056)
check(SEC.label.text == "~6s", "Frost Shock too, got " .. tostring(SEC.label.text))
cast(8042, "target")                         -- somebody else's cast
cdSecret(8042); NOW = NOW + 7; tick(0.1)
check(SEC.label.text == "RDY", "elapsed, got " .. tostring(SEC.label.text))
cast(8042, "target")
check(SEC.label.text == "RDY", "a cast by another unit is not ours, got " .. tostring(SEC.label.text))
noDegrade()
""")

case("the_cooldown_length_is_learned_from_a_plain_read_that_started_at_our_cast")(r"""
boot({})
mount("lower")
cast(8042)
cdPlain(8042, 5, 5)                          -- a talent shortens the cooldown to 5 s
fire("SPELL_UPDATE_COOLDOWN")
check(SEC.label.text == "5s", "plain 5 s, got " .. tostring(SEC.label.text))
IN_COMBAT = true
cdSecret(8042)
cast(8042)
check(SEC.label.text == "~5s", "the ledger uses the learned 5 s, got " .. tostring(SEC.label.text))
noDegrade()
""")

case("a_shock_cast_flashes_throws_eight_sparks_and_drains_fast")(r"""
boot({})
mount("lower")
local R = RECTS.lower
local W, C = { 243 / 255, 251 / 255, 1 }, { 0.133, 0.878, 1 }
cast(8042)                                    -- our own cast: the ledger stamps it, the cooldown is still read as off
check(vis(SEC.flashBolt) and vis(SEC.rimLit), "the flash starts with the cast")
cdPlain(8042, 6, 6)
fire("SPELL_UPDATE_COOLDOWN")
tick(0.05)                                    -- 0.05 s after the cast
check(0.05 < MU.CAST_FLASH, "the mockup flashes for 0.1 s")
check(vis(SEC.flashBolt), "the bolt is white")
tintIs(SEC.rimLit, W[1], W[2], W[3], MU.RIM_A, "the rim is white")
check(vis(SEC.rimLit) and vis(SEC.tint), "rim and plate flash")
-- the plate wash is the mockup's two mixes folded into one overlay
local a = SEC.tint.vertex[4]
near(a, 1 - (1 - MU.FLASH_WASH[1]) * (1 - MU.FLASH_WASH[2]), "wash alpha", 0.001)
for _, p in ipairs({ 0.04, 0.5, 0.9 }) do
    for i = 1, 3 do
        local want = (p * (1 - MU.FLASH_WASH[1]) + C[i] * MU.FLASH_WASH[1]) * (1 - MU.FLASH_WASH[2]) + W[i] * MU.FLASH_WASH[2]
        near(p * (1 - a) + SEC.tint.vertex[i] * a, want, "folded wash channel " .. i, 0.002)
    end
end
-- eight sparks of three px, stepping out and fading
local sc = NOW - 5000
for i = 1, 8 do
    for j = 0, 2 do
        local px = SEC.burst[(i - 1) * 3 + j + 1]
        check(vis(px), "spark " .. i .. "." .. j)
        local d = MU.SR + 1 + sc * MU.BURST_SPEED - j * 2
        local ang = (i - 1) / 8 * 2 * pi + 0.2
        local l, t = imgRect(px)
        near(l, R.x + floor(MU.SCX + cos(ang) * d + 0.5), "spark x", 0.02)
        near(t, R.y + floor(MU.SCY + sin(ang) * d + 0.5), "spark y", 0.02)
        near(px.alpha, math.max(0, (1 - sc / MU.CAST_BURST) * (1 - j * 0.3)), "spark alpha", 0.01)
    end
end
-- the drain: a mirrored swipe and a plain bolt value, not the refill
check(vis(SEC.drain) and vis(SEC.rimDrain), "the drain shows")
check(not vis(SEC.bar) and not vis(SEC.rimFill), "the refill waits")
near(SEC.drain.value, boltFraction(1 - sc / MU.DRAIN), "the bolt drains from full", 0.004)
near(SEC.rimDrain.cd[1], NOW - 0.05, "the swipe starts at the cast", 0.001); near(SEC.rimDrain.cd[2], MU.DRAIN, "and lasts the drain", 0.001)
tick(0.1)                                     -- 0.15 s
check(not vis(SEC.flashBolt) and not vis(SEC.rimLit), "the flash is over")
near(SEC.drain.value, boltFraction(1 - 0.15 / MU.DRAIN), "half drained", 0.004)
tick(0.2)                                     -- 0.35 s
check(not vis(SEC.drain) and not vis(SEC.rimDrain), "the drain is over")
check(vis(SEC.bar) and vis(SEC.rimFill), "the engine's refill takes over")
check(vis(SEC.burst[1]), "the sparks run to 0.5 s")
tick(0.2)                                     -- 0.55 s
for i = 1, 24 do check(not vis(SEC.burst[i]), "the sparks are gone") end
noDegrade()
""")

case("the_cooldown_ending_flashes_rings_and_turns_the_label_white")(r"""
boot({})
cdPlain(8042, 1, 6)
mount("lower")
local R = RECTS.lower
local W = { 243 / 255, 251 / 255, 1 }
check(not vis(SEC.ringG), "no ring while charging")
cdReady(8042)
fire("SPELL_UPDATE_COOLDOWN")                 -- it ends while we watch
check(SEC.label.text == "RDY", "ready")
tick(0.05)                                    -- 0.05 s after
check(0.05 < MU.RDY_FLASH and MU.RDY_RING_FROM > 0.05, "the mockup flashes first and rings from 0.1 s")
check(vis(SEC.flashBolt), "the flash")
tintIs(SEC.rimLit, W[1], W[2], W[3], MU.RIM_A, "white rim")
check(not vis(SEC.ringG), "the ring waits")
local r = textRgb(SEC.label)
check(r > 0.99, "the label flashes white")
tick(0.1)                                     -- 0.15 s
check(not vis(SEC.flashBolt), "the flash is over")
check(vis(SEC.ringG), "the ring is out")
local sr = NOW - 5000
local k = (sr - MU.RDY_RING_FROM) / (MU.RDY_BEAT - MU.RDY_RING_FROM)
near(SEC.ringG.alpha, (1 - k) * MU.RING_A, "ring alpha", 0.01)
local radius = MU.SR + 1 + k * MU.RING_GROW
for i = 1, 72 do
    local ang = (i - 1) / 72 * 2 * pi
    local l, t = imgRect(SEC.rdyRing[i])
    near(l, R.x + floor(MU.SCX + cos(ang) * radius), "ring x " .. i, 0.02)
    near(t, R.y + floor(MU.SCY + sin(ang) * radius), "ring y " .. i, 0.02)
end
tintIs(SEC.rdyRing[1], 243 / 255, 251 / 255, 1, nil, "ring px 1 is white")
tintIs(SEC.rdyRing[2], 0.133, 0.878, 1, nil, "ring px 2 is cyan")
r = textRgb(SEC.label)
check(r > 0.99, "still white at 0.15 s")
tick(0.2)                                     -- 0.35 s
r = textRgb(SEC.label)
check(math.abs(r - 0.133) < 0.01, "the label is cyan again after 0.3 s")
check(vis(SEC.ringG), "the ring runs to 0.6 s")
tick(0.3)                                     -- 0.65 s
check(not vis(SEC.ringG), "the ring is gone")
noDegrade()
""")

case("no_beat_for_what_happened_while_hidden_or_on_the_first_show")(r"""
boot({})
mount("lower")
runTicks(5)
check(not vis(SEC.flashBolt) and not vis(SEC.ringG) and not vis(SEC.burst[1]), "no beat on the first show of a ready shock")
Shocks.OnHide(SEC)
cdPlain(8042, 1, 6)
Shocks.OnShow(SEC)
cdReady(8042)
Shocks.OnHide(SEC)
Shocks.OnShow(SEC)                            -- it ended while hidden
runTicks(3)
check(SEC.label.text == "RDY", "ready")
check(not vis(SEC.flashBolt) and not vis(SEC.ringG), "no ready beat for a cooldown that ended while hidden")
cast(8042)
Shocks.OnHide(SEC)
NOW = NOW + 2
Shocks.OnShow(SEC)
runTicks(3)
check(not vis(SEC.flashBolt) and not vis(SEC.burst[1]), "no cast beat two seconds after a cast made while hidden")
noDegrade()
""")

case("a_ready_bolt_shimmers_crackles_and_sparks_at_its_tips")(r"""
boot({})
mount("lower")
local R = RECTS.lower
local function nz(i) local v = sin(i * 12.9898) * 43758.5453; return v - floor(v) end   -- the module's documented sine hash
local sawArc, sawNone = false, false
for step = 1, 80 do
    tick(0.04)
    local ry = MU.BOLT_TOP - MU.SHIMMER_BACK + floor((NOW * MU.SHIMMER) % MU.SHIMMER_SPAN)
    local l, t, w, h = imgRect(SEC.shimA)
    near(l, R.x + MU.SCX - MU.CELL / 2, "shimmer x", 0.02); near(t, R.y + MU.SCY + ry, "shimmer row", 0.02)
    near(w, MU.CELL, "shimmer width", 0.02); near(h, 1, "shimmer height", 0.02)
    local _, t2 = imgRect(SEC.shimB)
    near(t2, R.y + MU.SCY + ry - 1, "the row above", 0.02)
    local n = floor(NOW * MU.CRACKLE)
    for k = 0, 1 do
        local on = nz(n * 3 + k + 21) < MU.CRACKLE_P
        check(vis(SEC.crack[k * 3 + 1]) == on, "arc " .. k .. " visible " .. tostring(on) .. " at n " .. n)
        if on then
            sawArc = true
            local ang = nz(n * 7 + k + 31) * 2 * pi
            local l1, t1 = imgRect(SEC.crack[k * 3 + 1])
            near(l1, R.x + floor(MU.SCX + cos(ang) * (MU.SR + 1) + 0.5), "arc start x", 0.02)
            near(t1, R.y + floor(MU.SCY + sin(ang) * (MU.SR + 1) + 0.5), "arc start y", 0.02)
            near(SEC.crack[k * 3 + 1].alpha, 0.95, "arc head alpha", 0.001)
            near(SEC.crack[k * 3 + 3].alpha, 0.55, "arc tail alpha", 0.001)
        else
            sawNone = true
        end
    end
    local l3, t3 = imgRect(SEC.tips[1])
    near(l3, R.x + MU.SCX - 6 + floor(nz(n + 41) * 3), "top tip x", 0.02); near(t3, R.y + MU.SCY - 13, "top tip y", 0.02)
    near(SEC.tips[1].alpha, nz(n + 43) < 0.5 and 1 or 0.4, "top tip alpha", 0.001)
    local l4, t4 = imgRect(SEC.tips[2])
    near(l4, R.x + MU.SCX + 1 + floor(nz(n + 47) * 3), "bottom tip x", 0.02); near(t4, R.y + MU.SCY + 13, "bottom tip y", 0.02)
end
check(sawArc and sawNone, "arcs come and go over 3 s")
-- the shimmer rows are the white bolt cell and the inner cell
check(SEC.shimA.children[1].texcoord[1] == 0.5 and SEC.shimA.children[1].texcoord[3] == 0.5, "the white bolt cell")
check(SEC.shimB.children[1].texcoord[1] == 0.75 and SEC.shimB.children[1].texcoord[3] == 0.5, "the inner bolt cell")
-- a charging shock has none of it
cdPlain(8042, 4, 6); fire("SPELL_UPDATE_COOLDOWN")
tick(0.05)
check(not vis(SEC.shimA) and not vis(SEC.crack[1]) and not vis(SEC.tips[1]), "no shimmer, arcs or tip sparks while charging")
noDegrade()
""")

case("fire_nova_appears_when_it_is_learned")(r"""
boot({ known = false })
learn("Earth Shock")
mount("lower")
check(not vis(SEC.ring) and not vis(SEC.pip) and not vis(SEC.novaText), "locked")
learn("Fire Nova")
fire("SPELLS_CHANGED")
check(vis(SEC.ring) and vis(SEC.pip) and vis(SEC.novaText), "the ring and the NOVA tag show once it is in the book")
noDegrade()
""")

case("a_ready_fire_nova_lights_the_ring_and_the_NOVA_tag")(r"""
boot({})
mount("lower")
check(vis(SEC.ring) and cyanTint(SEC.ring), "the ring is cyan")
check(vis(SEC.ringGlow), "with its glow")
check(vis(SEC.pip) and cyanTint(SEC.pip) and vis(SEC.novaText) and SEC.novaText.text == "NOVA", "the footer pip and the NOVA word")
local r, g, b = textRgb(SEC.novaText)
check(math.abs(r - 0.133) < 0.01 and math.abs(b - 1) < 0.01, "NOVA is cyan")
check(onUpdates() == 1, "only the ready shock breathes")
noDegrade()
""")

case("fire_nova_on_cooldown_dims_the_tag_and_drops_the_ring")(r"""
boot({})
IN_COMBAT = true
mount("lower")
cdSecret(408341)
cast(408341)
check(not vis(SEC.ring) and not vis(SEC.ringGlow), "no ring while it cools down")
check(vis(SEC.pip) and mutedTint(SEC.pip) and vis(SEC.novaText), "the footer tag stays, muted")
check(onUpdates() >= 1, "ticks until it is ready")
tick(11)
check(vis(SEC.ring) and cyanTint(SEC.ring), "ready again once the ledger says elapsed")
check(onUpdates() == 1, "only the ready shock breathes")
cdBlind(408341); fire("SPELL_UPDATE_COOLDOWN")
check(not vis(SEC.ring) and vis(SEC.pip) and mutedTint(SEC.pip), "unreadable: no ring, a muted tag")
noDegrade()
""")

case("the_poles_say_whether_the_fire_totem_is_up_and_where_its_head_is")(r"""
boot({})
mount("lower")
local c0x, c0y = imgCenter(SEC.ring)
near(c0x, RECTS.lower.x + MU.FIRE_X, "the default ring centre x", 0.05)
near(c0y, RECTS.lower.y + MU.FIRE_Y, "the default ring centre y (a full pole's head)", 0.05)
SEC.SetFire(true, 40)
local x, y = imgCenter(SEC.ring)
near(y, 632 + 40, "the ring follows the head the poles report", 0.05)
SEC.SetFire(false)
check(not vis(SEC.ring) and not vis(SEC.ringGlow) and not vis(SEC.pip) and not vis(SEC.novaText), "no Fire totem: no ring, no NOVA tag")
SEC.SetFire(true, 30)
check(vis(SEC.ring) and vis(SEC.novaText), "back with the totem")
SEC.SetFire(true, "bad")
SEC.SetFire(nil)
noDegrade()
""")

case("the_ring_frame_has_a_rect_of_its_own_so_the_client_draws_its_textures")(r"""
boot({})
mount("lower")
local rf = SEC.ringFrame
check(rf and (rf:GetNumPoints() > 0 or rf.allPoints ~= nil), "a frame with no points has no rect on this client and draws nothing: the ring frame needs an anchor")
check(rf.allPoints == SEC.holder, "the ring frame fills the holder")
check(SEC.ring.parent == rf and SEC.ringGlow.parent == rf, "the ring and its glow are drawn by that frame")
check(vis(SEC.ring), "and the ring shows")
noDegrade()
""")

case("a_head_that_cannot_be_placed_hides_the_ring_and_keeps_the_NOVA_tag")(r"""
boot({})
mount("lower")
check(vis(SEC.ring) and vis(SEC.ringGlow), "the ring shows on a full head")
SEC.SetFire(true, false)
check(not vis(SEC.ring) and not vis(SEC.ringGlow), "headY false: the head's place is unknown, no ring")
check(vis(SEC.pip) and vis(SEC.novaText), "the Fire totem still stands: the NOVA tag stays")
SEC.SetFire(true, 40)
check(vis(SEC.ring) and vis(SEC.ringGlow), "a head with a place brings the ring back")
local _, y = imgCenter(SEC.ring)
near(y, 632 + 40, "at that place", 0.05)
SEC.SetFire(false, false)
check(not vis(SEC.ring) and not vis(SEC.pip) and not vis(SEC.novaText), "no Fire totem: nothing")
noDegrade()
""")

case("without_a_word_from_the_poles_an_unusable_nova_reads_as_no_fire_totem")(r"""
boot({})
USABLE[408341] = { false, false }
mount("lower")
check(not vis(SEC.ring) and not vis(SEC.novaText), "unusable for a reason other than mana: no totem, nothing shown")
USABLE[408341] = { false, true }
fire("SPELL_UPDATE_USABLE")
check(vis(SEC.ring), "no mana is not a missing totem")
USABLE[408341] = { SECRET, SECRET }           -- unreadable in combat: never a verdict
fire("SPELL_UPDATE_USABLE")
check(vis(SEC.ring), "a secret usability reads as a Fire totem that stands")
noDegrade()
""")

case("a_view_event_the_client_lacks_is_skipped_without_a_chat_line_and_the_rest_still_listen")(r"""
boot({})
KNOWN_EVENTS.SPELL_UPDATE_USABLE = nil
local printed = {}
print = function(...) printed[#printed + 1] = table.concat({ ... }, " ") end
ForeverSTUwaveDB = {}
mount("lower", { show = false })
Shocks.OnShow(SEC)
check(next(DEGRADED) == nil, "no chat line through the degrade path: " .. tostring(next(DEGRADED)))
check(#printed == 0, "nothing printed")
check(ForeverSTUwaveDB.unknownEvents and ForeverSTUwaveDB.unknownEvents.SPELL_UPDATE_USABLE, "the refused event is recorded in the saved variables")
local on = false
for _, f in ipairs(FRAMES) do if f.events.SPELL_UPDATE_COOLDOWN then on = true end end
check(on, "the events the client has are still on")
""")

case("a_cast_ledger_the_client_refuses_is_recorded_quietly")(r"""
boot({})
KNOWN_EVENTS.UNIT_SPELLCAST_SUCCEEDED = nil
local printed = {}
print = function(...) printed[#printed + 1] = table.concat({ ... }, " ") end
ForeverSTUwaveDB = {}
mount("lower", { show = false })
check(next(DEGRADED) == nil, "no chat line through the degrade path: " .. tostring(next(DEGRADED)))
check(#printed == 0, "nothing printed")
check(ForeverSTUwaveDB.unknownEvents and ForeverSTUwaveDB.unknownEvents.UNIT_SPELLCAST_SUCCEEDED, "recorded in the saved variables")
""")

case("OnHide_stops_the_ticker_and_every_view_event_but_the_ledger_stays")(r"""
boot({})
IN_COMBAT = true
mount("lower", { show = false })
local ledgerOnly = listeners()
Shocks.OnShow(SEC)
local showing = listeners()
check(showing > ledgerOnly, "showing listens to more than the ledger")
cdSecret(8042)
cast(8042)
check(onUpdates() >= 1, "charging ticks")
Shocks.OnHide(SEC)
check(onUpdates() == 0, "OnHide clears the ticker")
check(listeners() == ledgerOnly, "OnHide drops every view event, back to the ledger alone: " .. listeners() .. " vs " .. ledgerOnly)
local calls = CD_CALLS
fire("SPELL_UPDATE_COOLDOWN"); fire("SPELL_UPDATE_USABLE"); tick(2)
check(CD_CALLS == calls, "nothing reads a cooldown while hidden")
cast(8042)                                    -- a shock cast while hidden: only the ledger records it
check(CD_CALLS == calls, "the ledger records without reading the client")
Shocks.OnShow(SEC)
check(onUpdates() >= 1, "OnShow starts ticking again from a re-read")
check(SEC.label.text == "~6s" or SEC.label.text == "~5.9s", "the cast made while hidden is in the ledger, got " .. tostring(SEC.label.text))
noDegrade()
""")

case("OnShow_re_reads_the_spellbook_and_the_cooldown")(r"""
boot({ known = false })
mount("lower")
check(not vis(SEC.label), "nothing known at first")
Shocks.OnHide(SEC)
learn("Earth Shock", "Fire Nova")
cdPlain(8042, 4, 6)
Shocks.OnShow(SEC)
check(vis(SEC.label) and SEC.label.text == "4s", "learned while hidden: drawn on show, got " .. tostring(SEC.label.text))
check(vis(SEC.ring), "Fire Nova too")
noDegrade()
""")

case("a_shock_that_ends_while_hidden_reads_ready_on_show")(r"""
boot({})
cdPlain(8042, 4, 6)
mount("lower")
check(SEC.label.text == "4s", "charging")
Shocks.OnHide(SEC)
cdReady(8042)
NOW = NOW + 10
Shocks.OnShow(SEC)
check(SEC.label.text == "RDY", "got " .. tostring(SEC.label.text))
check(onUpdates() == 1, "the ready shock breathes")
noDegrade()
""")

case("the_baked_cells_are_cut_in_the_generators_order")(r"""
boot({})
mount("lower")
local FIELD = { disc = "disc", tint = "mask", dots = "dots", rimDim = "rimDim", rimLit = "rimLit", notches = "notches",
    outline = "boltOutline", boltEmpty = "boltEmpty", boltReady = "boltReady", boltMuted = "boltMuted", flashBolt = "boltWhite" }
local index = {}
for i, name in ipairs(MU.CELLS) do index[name] = i - 1 end
for field, cell in pairs(FIELD) do
    local i = index[cell]
    check(i ~= nil, "the generator has no cell " .. cell)
    local tc = SEC[field].texcoord
    local l, top = (i % 4) * 0.25, floor(i / 4) * 0.25
    check(tc and math.abs(tc[1] - l) < 1e-9 and math.abs(tc[2] - l - 0.25) < 1e-9 and math.abs(tc[3] - top) < 1e-9 and math.abs(tc[4] - top - 0.25) < 1e-9,
        field .. " is not cell " .. cell .. " (" .. i .. ")")
    check(SEC[field].path:find("shaman_disc.tga", 1, true), field .. " reads the wrong file")
end
check(SEC.halo1.texcoord[1] == 0 and SEC.halo1.texcoord[2] == 0.5 and SEC.halo2.texcoord[1] == 0.5 and SEC.halo2.texcoord[2] == 1, "the halo cells: inner, outer")
check(SEC.halo1.path:find("shaman_disc_halo.tga", 1, true), "halo file")
check(SEC.bar:GetStatusBarTexture().path:find("shaman_bolt_lit.tga", 1, true) and SEC.drain:GetStatusBarTexture().path:find("shaman_bolt_lit.tga", 1, true), "bolt bars")
noDegrade()
""")

for area, key in (("upper", "UPPER"), ("lower", "LOWER")):
    case(f"every_piece_sits_at_the_mockups_offset_in_the_{area}_area")(rf"""
boot({{}})
cdPlain(8042, 4, 6)
mount("{area}")
local R = RECTS["{area}"]
local gy = MU.GY
local cx, cy, half = R.x + MU.SCX, R.y + MU.SCY, MU.CELL / 2
-- the disc: every cell is 32 px with the disc's centre corner in the middle; the halos 64 px
for _, name in ipairs({{ "disc", "tint", "dots", "rimDim", "rimLit", "notches", "outline", "boltEmpty", "boltMuted", "boltReady", "flashBolt", "rimFill", "rimDrain" }}) do
    nearRect(SEC[name], cx - half, cy - half, MU.CELL, MU.CELL, name)
end
nearRect(SEC.halo1, cx - MU.HALO / 2, cy - MU.HALO / 2, MU.HALO, MU.HALO, "inner halo")
nearRect(SEC.halo2, cx - MU.HALO / 2, cy - MU.HALO / 2, MU.HALO, MU.HALO, "outer halo")
-- the bolt's bars: 16 x 32 px from the disc centre
nearRect(SEC.bar, cx + MU.BOLT_BOX[1], cy + MU.BOLT_BOX[2], MU.BOLT_BOX[3], MU.BOLT_BOX[4], "bolt bar")
nearRect(SEC.drain, cx + MU.BOLT_BOX[1], cy + MU.BOLT_BOX[2], MU.BOLT_BOX[3], MU.BOLT_BOX[4], "drain bar")
nearRect(SEC.canvas, R.x, R.y, MU.W, MU.H, "canvas")
-- the label is centred under the disc, its baseline SCY + SR + 12
local lx, ly = imgCenter(SEC.label)
near(lx, R.x + MU.LABEL_X, "label x", 0.05)
near(ly, R.y + MU.SCY + MU.SR + MU.LABEL_DY - CAP * MU.LABEL_SIZE, "label y", 0.1)
-- the Nova ring centred on the Fire head (a full pole's)
local d = 2 * MU.RING_OUT + 8          -- the ring canvas: 4 px of margin past the outer ring each side
nearRect(SEC.ring, R.x + MU.FIRE_X - d / 2, R.y + MU.FIRE_Y - d / 2, d, d, "ring")
nearRect(SEC.ringGlow, R.x + MU.FIRE_X - d / 2, R.y + MU.FIRE_Y - d / 2, d, d, "ring glow")
-- the footer: the pip centred at (PIP_X, fy + PIP_DY) 10 px, NOVA from NOVA_X on the baseline fy + NOVA_BASE
local fy = gy + MU.FOOT_DY
local px, py = imgCenter(SEC.pip)
near(px, R.x + MU.PIP_X, "pip x", 0.05); near(py, R.y + fy + MU.PIP_DY, "pip y", 0.05)
local _, _, pw = imgRect(SEC.pip)
near(pw, 10, "pip size", 0.02)
check(SEC.novaText.points[1][1] == "LEFT", "NOVA is left anchored")
local nx, ny = imgCenter(SEC.novaText)
near(nx, R.x + MU.NOVA_X, "NOVA x", 0.05)
near(ny, R.y + fy + MU.NOVA_BASE - CAP * MU.NOVA_SIZE, "NOVA y", 0.1)
noDegrade()
""")

case("a_rescale_re_seats_in_place_and_a_bad_rect_changes_nothing")(r"""
boot({})
cdPlain(8042, 4.2, 6)
mount("lower")
local R = RECTS.lower
local frames, texes = #FRAMES, #TEXTURES
SetScreen(1080)
Shocks.Seat(SEC, RECTS.lower, 1.28)
check(#FRAMES == frames and #TEXTURES == texes, "a seat creates nothing")
local l, t, w, h = imgRect(SEC.disc)
near(w, MU.CELL, "the disc keeps its image width at another screen height", 0.05)
nearRect(SEC.bar, R.x + MU.SCX + MU.BOLT_BOX[1], R.y + MU.SCY + MU.BOLT_BOX[2], MU.BOLT_BOX[3], MU.BOLT_BOX[4], "bolt bar")
-- the moving px are put back where they belong from the new anchors
local ang = 0.3 * 2 * pi
nearRect(SEC.spark, R.x + MU.SCX + floor(sin(ang) * (MU.SR - 0.9)), R.y + MU.SCY + floor(-cos(ang) * (MU.SR - 0.9)), 1, 1, "spark after the rescale")
Shocks.Seat(SEC, nil, 1.28)
Shocks.Seat(SEC, { x = "a" }, nil)
Shocks.Seat(nil, RECTS.lower, 1.28)
Shocks.OnShow(nil); Shocks.OnHide(nil)
local l2, t2 = imgRect(SEC.disc)
near(l2, l, "left", 0.001); near(t2, t, "top", 0.001)
noDegrade()
""")

case("a_rescale_keeps_the_colours_the_texts_wear")(r"""
boot({})
IN_COMBAT = true
mount("lower")
cdSecret(408341); cast(408341)               -- Fire Nova cools down: NOVA is muted at .75
local c = SEC.novaText.textColor
check(math.abs(c[1] - 0.6157) < 0.01 and math.abs(c[4] - 0.75) < 0.01, "NOVA is muted")
Shocks.Seat(SEC, RECTS.lower, 1.28)         -- ApplyMono resets a font string's colour; the seat puts the worn one back
c = SEC.novaText.textColor
check(math.abs(c[1] - 0.6157) < 0.01 and math.abs(c[4] - 0.75) < 0.01, "NOVA stays muted at .75 after a seat, got " .. c[1] .. " " .. tostring(c[4]))
c = SEC.label.textColor
check(math.abs(c[1] - 0.133) < 0.01, "RDY stays cyan after a seat")
noDegrade()
""")

case("the_per_frame_path_allocates_nothing")(r"""
jit.off()
boot({})
IN_COMBAT = true
mount("lower")
-- the mock allocates on some setters (a fresh anchor entry, a colour table): swap in versions that reuse, so the count is the module's
local FrameMT = getmetatable(UIParent).__index
function FrameMT:SetPoint(point, rel, relPoint, x, y)
    local e = self.points[1]
    if not e then e = {}; self.points[1] = e end
    e[1], e[2], e[3], e[4], e[5] = point, rel, relPoint or point, x or 0, y or 0
end
function FrameMT:ClearAllPoints() end
for _, t in ipairs(TEXTURES) do
    t.SetVertexColor = function(self, r, g, b, a) local v = self.vertex; v[1], v[2], v[3], v[4] = r, g, b, a == nil and 1 or a end
    t.SetColorTexture = function(self, r, g, b, a) local c = self.color or { 0, 0, 0, 0 }; self.color = c; c[1], c[2], c[3], c[4] = r, g, b, a end
end
for _, s in ipairs(FONTSTRINGS) do
    s.textColor = { 0, 0, 0, 0 }
    s.SetTextColor = function(self, r, g, b, a) local c = self.textColor; c[1], c[2], c[3], c[4] = r, g, b, a end
end
for _, f in ipairs(FRAMES) do
    if f.isCooldown then
        f.cd = { 0, 0 }
        f.SetCooldown = function(self, a, b) self.cd[1], self.cd[2] = a, b end
    end
end
cdSecret(8042); cdSecret(408341)
local before
local ticker = SEC.holder.scripts.OnUpdate
check(ticker, "a ready shock ticks")
for i = 1, 300 do NOW = NOW + 0.01; ticker(SEC.holder) end          -- the ready breath, shimmer and crackle
-- one whole cycle first (a field or a table the first beat creates is a one time cost), then the one that is counted
for round = 1, 2 do
    cast(8042); cast(408341)
    if round == 2 then collectgarbage(); collectgarbage("stop"); before = collectgarbage("count") end
    for i = 1, 1100 do NOW = NOW + 0.01; ticker(SEC.holder) end       -- 11 s: the cast beat and drain, the charge, the ready beat and ring, the breath again, Nova's return
end
local grown = (collectgarbage("count") - before) * 1024
collectgarbage("restart")
check(SEC.label.text == "RDY", "the shock came back to ready, got " .. tostring(SEC.label.text))
check(grown < 512, "1100 frames allocated " .. math.floor(grown) .. " bytes")
""")


def _tga_size(path: Path) -> tuple[int, int]:
    d = path.read_bytes()
    return struct.unpack("<HH", d[12:16])


def static_checks(mu: dict) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        s = toc.index("Modules/CombatHud/GunsightShamanShocks.lua")
        sh = toc.index("Modules/CombatHud/GunsightShaman.lua")
        a = toc.index("Modules/CombatHud/GunsightAreas.lua")
        out.append(("toc_loads_shocks_right_before_shaman",
                    None if s + 1 == sh and s > a else f"GunsightShamanShocks.lua must sit right before GunsightShaman.lua (positions {s}, {sh})"))
    except ValueError as e:
        out.append(("toc_loads_shocks_right_before_shaman", f"{e}"))
    src = SHOCKS.read_text(encoding="utf-8") if SHOCKS.exists() else ""
    out.append(("no_em_or_en_dashes", None if not re.search("[–—]", src) else "GunsightShamanShocks.lua has an em or en dash"))
    code = "\n".join(re.sub(r"--.*$", "", ln) for ln in src.splitlines())
    out.append(("player_text_never_says_tape", None if not re.search(r"\"[^\"]*\btape\b[^\"]*\"", code, re.I) else "player text says tape"))
    out.append(("draws_no_kick_tag_and_reads_no_target_cast", None if not re.search(r"\"KICK\"|UnitCastingInfo|UnitChannelInfo|SetAlphaFromBoolean", code)
                else "KICK comes from GunsightTape.lua: this file draws no tag and reads no target cast"))
    out.append(("never_touches_a_secure_template", None if "SecureActionButtonTemplate" not in src and "SecureUnitButtonTemplate" not in src
                else "a secure template under a host would make it protected"))
    out.append(("never_parents_to_uiparent_or_the_root", None if not re.search(r"CreateFrame\([^)]*(UIParent|Gunsight\.root)", src)
                else "everything hangs under the module frame"))
    out.append(("never_says_what_the_client_must_not_see", None if not re.search(r"\b(bot|macro|automation|addon)\b", re.sub(r"--.*", "", "\n".join(
        re.findall(r"\"[^\"\n]*\"", code))), re.I) else "a string in the file carries a word the client must not see"))
    for tex in ("shaman_disc", "shaman_disc_halo", "shaman_disc_rim", "shaman_disc_rim_mirror", "shaman_bolt_lit",
                "nova_ring", "nova_ring_glow", "nova_pip"):
        out.append((f"texture_{tex}_exists", None if (TEXTURES / f"{tex}.tga").exists() else f"{tex}.tga is missing"))
        out.append((f"texture_{tex}_is_used", None if tex + ".tga" in src else f"{tex}.tga is never used"))
    for tex in ("shock_trace_line", "shock_trace_glow", "shock_bolt_fill", "shock_bolt_line", "shock_bolt_glow"):
        gone = not (TEXTURES / f"{tex}.tga").exists() and tex not in src
        out.append((f"old_texture_{tex}_is_gone", None if gone else f"{tex} must be removed with the zig-zag line"))
    out.append(("pixel_art_is_sampled_nearest", None if '"NEAREST"' in src else "the baked pixel art must be drawn with nearest neighbour"))
    # the files agree with the generator and the generator with the mockup
    gen = _load("generate_shaman_disc", HERE / "assets")
    dims = {"shaman_disc": (256, 256), "shaman_disc_halo": (256, 128), "shaman_disc_rim": (64, 64),
            "shaman_disc_rim_mirror": (64, 64), "shaman_bolt_lit": (32, 64)}
    for name, want in dims.items():
        p = TEXTURES / f"{name}.tga"
        got = _tga_size(p) if p.exists() else None
        out.append((f"texture_{name}_is_{want[0]}x{want[1]}", None if got == want else f"{name}.tga is {got}"))
    out.append(("generator_bolt_polygon_is_the_mockups", None if [tuple(p) for p in gen.BOLT_PTS] == [tuple(p) for p in mu["BOLT_PTS"]]
                else f"generator polygon {gen.BOLT_PTS} vs mockup {mu['BOLT_PTS']}"))
    out.append(("generator_radius_is_the_mockups", None if gen.SR == mu["SR"] else f"generator SR {gen.SR} vs mockup {mu['SR']}"))
    rows = [y for (_, y, _, _, _) in gen.BOLT_PX]
    out.append(("generator_bolt_rows_start_at_the_mockups_top_and_end_above_its_bottom_edge",
                None if min(rows) == mu["BOLT_TOP"] and max(rows) < mu["BOLT_BOT"] else f"rows {min(rows)}..{max(rows)} vs {mu['BOLT_TOP']}..{mu['BOLT_BOT']}"))
    cells = re.search(r"local DISC_CELL = \{(.*?)\}", src, re.S)
    lua_order = None
    if cells:
        pairs = re.findall(r"(\w+) = (\d+)", cells.group(1))
        lua_order = {name: int(i) for name, i in pairs}
    want_lua = {"disc": "disc", "mask": "mask", "dots": "dots", "rimDim": "rimDim", "rimLit": "rimLit", "notches": "notches",
                "outline": "boltOutline", "boltEmpty": "boltEmpty", "boltReady": "boltReady", "boltMuted": "boltMuted",
                "boltWhite": "boltWhite", "boltInner": "boltInner"}
    ok = lua_order is not None and all(gen.DISC_CELLS.index(g) == lua_order.get(k) for k, g in want_lua.items()) and len(lua_order) == len(gen.DISC_CELLS)
    out.append(("lua_cell_map_is_the_generators_order", None if ok else f"DISC_CELL {lua_order} vs generator {gen.DISC_CELLS}"))
    consts = {k: re.search(rf"\b{k} = (-?\d+)", src) for k in ("SCX", "SCY", "SR", "CELL", "HALO", "BOLT_X", "BOLT_Y", "BOLT_W", "BOLT_H",
                                                              "BOLT_TOP", "BOLT_BOT", "BOLT_SPAN", "W", "H")}
    got = {k: (int(m.group(1)) if m else None) for k, m in consts.items()}
    want = {"SCX": mu["SCX"], "SCY": mu["SCY"], "SR": mu["SR"], "CELL": gen.CELL // gen.SCALE, "HALO": gen.HALO_CELL // gen.SCALE,
            "BOLT_X": gen.BOLT_BOX[0], "BOLT_Y": gen.BOLT_BOX[1], "BOLT_W": gen.BOLT_BOX[2], "BOLT_H": gen.BOLT_BOX[3],
            "BOLT_TOP": mu["BOLT_TOP"], "BOLT_BOT": mu["BOLT_BOT"], "BOLT_SPAN": mu["BOLT_SPAN"], "W": mu["W"], "H": mu["H"]}
    out.append(("lua_constants_are_the_mockups_and_the_generators", None if got == want else f"{got} vs {want}"))
    out.append(("bolt_box_texels_are_the_files", None if (gen.BOLT_BOX[2] * gen.SCALE, gen.BOLT_BOX[3] * gen.SCALE) == gen.BOLT_FILE else "bolt box vs file"))
    out.append(("bolt_rows_sit_inside_the_box", None if gen.BOLT_BOX[1] <= mu["BOLT_TOP"] and mu["BOLT_BOT"] <= gen.BOLT_BOX[1] + gen.BOLT_BOX[3] else "rows outside the box"))
    return out


def build_cases() -> list[tuple[str, str]]:
    """The case list, with the earlier build's bodies (the Nova, ledger and event cases) carried over where `kept` asks."""
    return CASES


def run_case(name: str, body: str, mu: dict) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    g = lua.globals()
    g.LAYOUT_SRC = LAYOUT.read_text(encoding="utf-8")
    g.CONFIG_SRC = CONFIG.read_text(encoding="utf-8")
    g.FRAMEHELPERS_SRC = FRAMEHELPERS.read_text(encoding="utf-8")
    g.GUNSIGHT_SRC = GUNSIGHT.read_text(encoding="utf-8")
    g.SHOCKS_SRC = SHOCKS.read_text(encoding="utf-8")
    g.HAS_TARGET_SRC = _load("gunsight-harness").theme_target_rule_lua()
    lua.execute("MU = " + lua_value(mu))
    try:
        lua.execute(PRELUDE + "\n" + body)
    except LuaError as e:
        return str(e)
    return None


def main() -> int:
    if not MOCKUP.exists():
        print(f"SKIP  {MOCKUP.name} is absent (mockups/ is not in this checkout)")
        return 0
    mu = mockup_numbers()
    gen = _load("generate_shaman_disc", HERE / "assets")
    mu["CELLS"] = list(gen.DISC_CELLS)
    mu["CELL"] = gen.CELL // gen.SCALE
    mu["HALO"] = gen.HALO_CELL // gen.SCALE
    mu["BOLT_BOX"] = list(gen.BOLT_BOX)
    failures = 0

    def report(name: str, err: str | None) -> None:
        nonlocal failures
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      " + err.replace("\n", "\n      "))

    if not SHOCKS.exists():
        print(f"FAIL  {SHOCKS.name} is missing")
        return 1
    for name, body in build_cases():
        try:
            err = run_case(name, body, mu)
        except LuaError as e:
            err = f"harness error: {e}"
        report(name, err)
    statics = static_checks(mu)
    for name, err in statics:
        report(name, err)
    total = len(CASES) + len(statics)
    print(f"\n{total - failures}/{total} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
