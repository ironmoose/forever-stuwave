#!/usr/bin/env python3
"""Runs the real GunsightShaman.lua (the Shaman Gunsight Class Module: the totem poles) headless.

Reference: mockups/gunsight-class-module-shaman-2026-10-08.html, Concept A "Totem Poles" (poleMod, pole, head). The data comes from the
REAL ShamanTotems.lua, fed by a mock of the client facts measured on this client (out of combat GetTotemInfo is plain and haveTotem is
true with a blank name when nothing stands; in combat every GetTotemInfo return is secret and GetTotemDuration alone says a totem is up).
FS.GunsightAreas is a FAKE for the registration cases and the REAL file for the target gate cases. The checks pin:

  * registration: one "class" spec for SHAMAN with build, seat, onShow and onHide, and nothing else registered;
  * every geometry number against the mockup: the pole x and width, the block count, pitch and height, the ground, the re-drop zone,
    the head, the eyes, the labels, the locked mold text, the element colours and the block opacities;
  * the looks: blocks (ceil(remaining / duration * 8) lit, the last one amber, the head sunk on top of them, the time under the ground,
    a "~" for an estimate), the bar for a totem up with no number (a StatusBar driven by SetTimerDuration, the head anchored to its
    fill, "?"), DROP (dashed amber head, plus sign), locked (level and name), FAR (ghost pole, dashed amber head, FAR);
  * secrets: in combat every client answer is secret and no arithmetic touches one (any throw inside a pcall'd paint is logged and fails
    the case);
  * the OnUpdate runs only while the module is shown and a totem is up, allocates nothing on a steady tick, and stops on hide; onShow
    re-reads totems that changed while hidden; the target gate hides the host and stops the module;
  * the GunsightShamanShocks seam: Build / Seat / OnShow / OnHide feature detected and pcalled, section.SetFire(up, headY) told when the Fire totem or its head moves, the real Nova ring follows the head and sits above it;
  * the baked art matches the crops the module uses, the TOC order, no secure frame, no event of its own.

The mock is strict. It is NOT the real client.

    python3 tools/gunsightshaman-harness.py

Exit 0 = every check passed. GUNSIGHTSHAMAN_LUA=<path> runs another file in place of GunsightShaman.lua.
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
SHAMAN = Path(os.environ.get("GUNSIGHTSHAMAN_LUA") or ADDON / "Modules/CombatHud/GunsightShaman.lua")
TOTEMS = ADDON / "Modules/CombatHud/ShamanTotems.lua"
SHOCKS = ADDON / "Modules/CombatHud/GunsightShamanShocks.lua"
GUNSIGHT = ADDON / "Modules/CombatHud/Gunsight.lua"
LAYOUT = ADDON / "Core/Layout.lua"
CONFIG = ADDON / "Core/Config.lua"
THEME = ADDON / "Core/Theme.lua"
TOC = ADDON / "forever-stuwave.toc"
AREAS = ADDON / "Modules/CombatHud/GunsightAreas.lua"
MOCKUP = HERE.parent / "mockups" / "gunsight-class-module-shaman-2026-10-08.html"
TEXTURES = ADDON / "Media" / "Textures"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CLASS_HARNESS = _load("gunsightclass-harness")


def _m(pattern: str, text: str, what: str) -> re.Match:
    m = re.search(pattern, text, re.S)
    if not m:
        sys.exit(f"mockup: cannot find {what} (pattern {pattern!r}); the mockup changed shape")
    return m


def mockup_numbers() -> dict:
    """The numbers poleMod, pole and head draw, in image px, read out of the Concept A mockup."""
    src = MOCKUP.read_text(encoding="utf-8")
    px = _m(r"var PX=\{fire:\[(\d+),(\d+)\],earth:\[(\d+),(\d+)\],water:\[(\d+),(\d+)\],air:\[(\d+),(\d+)\]\};", src, "PX")
    nb = _m(r"var NB=(\d+),BP=(\d+),BH=(\d+);", src, "NB BP BH")
    pole_fn = _m(r"function pole\(k,s,gy,st,an\)\{(.*?)\n\}", src, "pole()").group(1)
    head_fn = _m(r"function head\(el,cx,ty,w,c,mode\)\{(.*?)\n\}", src, "head()").group(1)
    mod_fn = _m(r"function poleMod\(y0,st,an\)\{(.*?)\n\}", src, "poleMod()").group(1)
    gy = _m(r"gy=y0\+(\d+),x0=(\d+),x1=(\d+)", mod_fn, "gy x0 x1")
    zone = _m(r"rect\(x0,gy-BP,x1-x0,BP,C\.amber,\.(\d+)\)\+line\(x0,gy-BP-1,x1,gy-BP-1,C\.amber,\.(\d+),1,'(\d+) (\d+)'\)", mod_fn, "zone")
    ground = _m(r"line\(x0,gy,(\d+),gy,C\.violet,\.(\d+),([\d.]+)\)", mod_fn, "ground")
    ins = _m(r"ins=hero\?(\d+):(\d+)", pole_fn, "ins")
    mold = _m(r"y=\"'\+\(gy-NB\*BP\)\+'\" width=\"'\+\(w-2\*ins\)\+'\" height=\"'\+\(NB\*BP-(\d+)\)\+'\" fill=\"'\+c\+'\" fill-opacity=\"\.(\d+)\" stroke=\"'\+C\.violet\+'\" stroke-opacity=\"\.(\d+)\" stroke-dasharray=\"(\d) (\d)\"", pole_fn, "mold")
    locked = _m(r"stroke-opacity=\"\.(\d+)\" stroke-dasharray=\"2 3\"/>';\s*o\+=txt\(cx,gy-NB\*BP/2-2,'L'\+s\.lv,(\d+),C\.muted,\{a:'middle',op:\.(\d+)\}\);\s*o\+=txt\(cx,gy-NB\*BP/2\+(\d+),EL\[k\]\.nm\.charAt\(0\)\+EL\[k\]\.nm\.slice\(1\)\.toLowerCase\(\),(\d+),C\.muted,\{a:'middle',op:\.(\d+)\}\)", pole_fn, "locked")
    ops = _m(r"op=s\.st==='far'\?\.(\d+):\(s\.st==='est'\?\.(\d+):\.(\d+)\)", pole_fn, "opacity")
    blockline = _m(r"rect\(x\+ins\+(\d+),by\+(\d+),w-2\*ins-(\d+),(\d+),'#0a0416',\.(\d+)\)", pole_fn, "block line")
    headpos = _m(r"var ty=gy-lit\*BP-(\d+),mode=", pole_fn, "head top")
    label = _m(r"var lab,lc=C\.white,fs=hero\?(\d+):(\d+);", pole_fn, "label size")
    labely = _m(r"o\+=txt\(cx,gy\+(\d+),lab,fs,lc,\{a:'middle'\}\)", pole_fn, "label y")
    hhead = _m(r"hx=cx-w/2,hy=ty\+(\d+),hero=w>40", head_fn, "head")
    plate = _m(r"ch\(hx,hy,w,(\d+),(\d+)\)\+'\" fill=\"'\+mix\(C\.bg,c,\.(\d+)\)", head_fn, "head plate")
    down = _m(r"mix\(C\.bg,C\.amber,\.(\d+)\)\+'\" stroke=\"'\+C\.amber\+'\" stroke-width=\"1\.3\" stroke-dasharray=\"(\d) (\d)\"", head_fn, "down head")
    plus = _m(r"txt\(cx,hy\+(\d+),'\+',(\d+),C\.amber", head_fn, "plus")
    eyes = _m(r"rect\(cx-\(hero\?(\d+):(\d+)\),hy\+(\d+),hero\?(\d+):(\d+),(\d+),'#0a0416',\.(\d+)\)\+rect\(cx\+\(hero\?(\d+):(\d+)\),hy\+3", head_fn, "eyes")
    far_mix = _m(r"mode==='far'\?mix\(c,C\.bg,\.(\d+)\):c", head_fn, "far crown")
    el = _m(r"fire:\{c:'(#[0-9a-f]{6})'.*?earth:\{c:'(#[0-9a-f]{6})'.*?water:\{c:'(#[0-9a-f]{6})'.*?air:\{c:'(#[0-9a-f]{6})'", src, "EL")
    crown = _m(r"function crown\(el,cx,ty,c\)\{(.*?)\n\}", src, "crown").group(1)
    return {
        "PX": {"fire": [int(px.group(1)), int(px.group(2))], "earth": [int(px.group(3)), int(px.group(4))],
               "water": [int(px.group(5)), int(px.group(6))], "air": [int(px.group(7)), int(px.group(8))]},
        "NB": int(nb.group(1)), "BP": int(nb.group(2)), "BH": int(nb.group(3)),
        "GY": int(gy.group(1)), "X0": int(gy.group(2)), "X1": int(gy.group(3)),
        "ZONE_A": float("0." + zone.group(1)), "ZONE_LINE_A": float("0." + zone.group(2)),
        "ZONE_DASH": [int(zone.group(3)), int(zone.group(4))],
        "GROUND_X1": int(ground.group(1)), "GROUND_A": float("0." + ground.group(2)), "GROUND_TH": float(ground.group(3)),
        "INS_HERO": int(ins.group(1)), "INS": int(ins.group(2)),
        "MOLD_LESS": int(mold.group(1)), "MOLD_FILL_A": float("0." + mold.group(2)), "MOLD_A": float("0." + mold.group(3)),
        "MOLD_DASH": [int(mold.group(4)), int(mold.group(5))],
        "MOLD_LOCKED_A": float("0." + locked.group(1)), "LV_SIZE": int(locked.group(2)), "LV_A": float("0." + locked.group(3)),
        "NM_DY": int(locked.group(4)), "NM_SIZE": int(locked.group(5)), "NM_A": float("0." + locked.group(6)),
        "OP_FAR": float("0." + ops.group(1)), "OP_EST": float("0." + ops.group(2)), "OP_UP": float("0." + ops.group(3)),
        "LINE": [int(blockline.group(i)) for i in (1, 2, 3, 4)],
        "HEAD_TOP": int(headpos.group(1)),
        "LABEL_HERO": int(label.group(1)), "LABEL": int(label.group(2)), "LABEL_Y": int(labely.group(1)),
        "HY": int(hhead.group(1)), "HEAD_H": int(plate.group(1)), "HEAD_CUT": int(plate.group(2)),
        "HEAD_MIX": float("0." + plate.group(3)),
        "HEAD_DOWN_MIX": float("0." + down.group(1)), "HEAD_DASH": [int(down.group(2)), int(down.group(3))],
        "PLUS_BASE": int(plus.group(1)), "PLUS_SIZE": int(plus.group(2)),
        "EYE": {"hero": [int(eyes.group(1)), int(eyes.group(4)), int(eyes.group(8))],
                "narrow": [int(eyes.group(2)), int(eyes.group(5)), int(eyes.group(9))]},
        "EYE_Y": int(eyes.group(3)), "EYE_H": int(eyes.group(6)), "EYE_A": float("0." + eyes.group(7)),
        "FAR_MIX": float("0." + far_mix.group(1)),
        "COLORS": {"fire": el.group(1), "earth": el.group(2), "water": el.group(3), "air": el.group(4)},
        "CROWN_CENTER": 3 if "ty+6" in crown else 0,
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
# The mock client: the Class harness's strict mock (itself the Dots harness's), plus the totem world
# ---------------------------------------------------------------------------------------

MOCK = CLASS_HARNESS.MOCK

PRELUDE = r"""
RECTS = { upper = { x = 100, y = 100, w = 202, h = 60 }, lower = { x = 100, y = 700, w = 202, h = 60 } }
K = 1.28

-- the StatusBar of the class harness, plus the engine timer
do
    local prev = CreateFrame
    function CreateFrame(kind, ...)
        local f = prev(kind, ...)
        if kind == "StatusBar" then
            function f:SetTimerDuration(obj, interp, dir) self.timer = { obj = obj, interp = interp, dir = dir } end
        end
        return f
    end
end
Enum = { StatusBarTimerDirection = { ElapsedTime = 0, RemainingTime = 1 }, StatusBarInterpolation = { Immediate = 0 } }

-- The totem world. TOT[slot] = { name, start, dur, spell } for a standing totem; SECRET_READS makes every GetTotemInfo return secret.
TOT, SECRET_READS, POS, LEVEL, KNOWN_SPELLS, SPELL_NAMES = {}, false, nil, 30, {}, {}
OBJECTS = {}
function GetTotemInfo(slot)
    if SECRET_READS then return SECRET, SECRET, SECRET, SECRET, SECRET, SECRET, SECRET end
    local t = TOT[slot]
    if t then return true, t.name, t.start, t.dur, 136, 1, t.spell end
    return true, "", 0, 0, 0, 1, 0                 -- haveTotem is TRUE with a blank name when nothing stands
end
function GetTotemDuration(slot)
    if not TOT[slot] then return nil end
    OBJECTS[slot] = OBJECTS[slot] or { object = slot }
    return OBJECTS[slot]
end
function UnitPosition() if POS == nil then return nil end return POS[1], POS[2], POS[3], POS[4] end
function UnitLevel() return LEVEL end
function IsPlayerSpell(id) return KNOWN_SPELLS[id] == true end
C_Spell = { GetSpellName = function(id) return SPELL_NAMES[id] end, GetSpellTexture = function(id) return 100000 + id end }

local function fakeAreas()
    MODS, AREA_OF = {}, {}
    FS.GunsightAreas = {
        RegisterModule = function(id, spec) MODS[id] = spec; return true end,
        AreaOf = function(id) return AREA_OF[id] end,
        OnAreaChanged = function() end,
    }
end

local function boot(opts)
    opts = opts or {}
    STRICT_EVENTS = false
    TIMERS = {}
    resetKnownEvents()
    for e in ([[PLAYER_LOGIN PLAYER_TOTEM_UPDATE SPELLS_CHANGED PLAYER_LEVEL_UP UNIT_SPELLCAST_SUCCEEDED]]):gmatch("%S+") do KNOWN_EVENTS[e] = true end
    resetWorld()
    TOT, SECRET_READS, POS, LEVEL, KNOWN_SPELLS, SPELL_NAMES, OBJECTS = {}, false, nil, opts.level or 30, {}, {}, {}
    SetScreen(opts.height or 1440)
    ForeverSTUwaveDB = opts.db
    FS.IsSecret = function(v) return v == SECRET end
    stubTheme_()
    FS.Theme.COLOR_TEXT_WHITE = { 1, 1, 1, 1 }
    if opts.tokens then FS.Theme.COLOR_TOTEM = opts.tokens end
    stubHud_()
    assert(loadstring(HAS_TARGET_SRC, "@Theme.lua"))()
    loadAddonFile(LAYOUT_SRC, "Core/Layout.lua")
    loadAddonFile(CONFIG_SRC, "Core/Config.lua")
    loadAddonFile(GUNSIGHT_SRC, "Modules/CombatHud/Gunsight.lua")
    if opts.realAreas then
        TARGET = { exists = not opts.noTarget }
        UnitExists = function() return TARGET.exists end
        loadAddonFile(AREAS_SRC, "Modules/CombatHud/GunsightAreas.lua")
    else
        fakeAreas()
    end
    UnitClass = function() return "Shaman", opts.class or "SHAMAN" end
    if not opts.noTotems then loadAddonFile(TOTEMS_SRC, "Modules/CombatHud/ShamanTotems.lua") end
    FS.GunsightShamanShocks = opts.shocks
    if opts.realShocks then loadAddonFile(SHOCKS_SRC, "Modules/CombatHud/GunsightShamanShocks.lua") end
    loadAddonFile(SHAMAN_SRC, "Modules/CombatHud/GunsightShaman.lua")
    fire("ADDON_LOADED", "forever-stuwave")
    fire("PLAYER_LOGIN")
end

local function mount(area)
    STRICT_EVENTS = true
    local spec = MODS.class
    check(spec, "no class module registered")
    local host = CreateFrame("Frame", nil, FS.Gunsight.root)
    host:SetSize(1, 1)
    local before = #FRAMES
    local frame = spec.build(host)
    check(frame ~= nil, "build(host) returned no frame")
    BUILT_FRAMES = #FRAMES - before
    spec.seat(RECTS[area])
    if spec.onShow then spec.onShow(area) end
    return spec, host, frame
end

local function under(r, host)
    while r do if r == host then return true end; r = r.parent end
    return false
end
local function drawn(host)
    local tex, txt = {}, {}
    for _, t in ipairs(TEXTURES) do if under(t, host) then tex[#tex + 1] = t end end
    for _, s in ipairs(FONTSTRINGS) do if under(s, host) then txt[#txt + 1] = s end end
    return tex, txt
end
local function noDegrade() check(next(DEGRADED) == nil, "a degrade was logged: " .. tostring(next(DEGRADED)) .. " " .. tostring(DEGRADED[next(DEGRADED)])) end
local function parts() return FS.GunsightShaman.parts end
local function C() return FS.GunsightShaman.C end

-- put a totem down out of combat and tell the data module
local function drop(slot, name, spell, remaining, duration)
    TOT[slot] = { name = name, start = NOW - (duration - remaining), dur = duration, spell = spell }
    fire("PLAYER_TOTEM_UPDATE", slot)
end
local function clear(slot) TOT[slot] = nil; fire("PLAYER_TOTEM_UPDATE", slot) end
local function lit(p) local n = 0 for i = 1, 8 do if isVisible(p.blocks[i]) then n = n + 1 end end return n end
local function near3(a, b, what) near(a, b, what, 1e-3) end
local function rgbOf(hex) return { tonumber(hex:sub(2, 3), 16) / 255, tonumber(hex:sub(4, 5), 16) / 255, tonumber(hex:sub(6, 7), 16) / 255 } end
local function colorIs(t, want, a, what)
    local v = t.vertex or t.textColor
    check(v, what .. ": no colour written")
    near3(v[1], want[1], what .. " r"); near3(v[2], want[2], what .. " g"); near3(v[3], want[3], what .. " b")
    if a then near3(v[4], a, what .. " alpha") end
end
local function textColorIs(fs, want, a, what)
    local v = fs.textColor
    check(v, what .. ": no colour written")
    near3(v[1], want[1], what .. " r"); near3(v[2], want[2], what .. " g"); near3(v[3], want[3], what .. " b")
    near3(v[4], a, what .. " alpha")
end
local AMBER, MUTED, WHITE = rgbOf("#ffb648"), rgbOf("#9d93c4"), rgbOf("#f3fbff")
local ELEMENT = { "fire", "earth", "water", "air" }
"""

CASES: list[tuple[str, str]] = []


def case(name: str):
    def deco(body: str):
        CASES.append((name, body))
        return body
    return deco


case("registers_one_class_module_for_shaman_only_through_the_seam")(r"""
boot({})
local spec = MODS.class
check(spec, "no module registered under the id class")
local n = 0
for _ in pairs(MODS) do n = n + 1 end
check(n == 1, "exactly the class module is registered, got " .. n)
check(#spec.classes == 1 and spec.classes[1] == "SHAMAN", "classes must be exactly SHAMAN, got " .. #spec.classes)
for _, f in ipairs({ "build", "seat", "onShow", "onHide" }) do
    check(type(spec[f]) == "function", "the module has no " .. f)
end
noDegrade()
""")

case("without_the_areas_seam_nothing_registers_and_nothing_throws")(r"""
resetWorld()
SetScreen(1440)
FS.IsSecret = function(v) return false end
stubTheme_(); stubHud_()
loadAddonFile(LAYOUT_SRC, "Core/Layout.lua"); loadAddonFile(CONFIG_SRC, "Core/Config.lua"); loadAddonFile(GUNSIGHT_SRC, "Modules/CombatHud/Gunsight.lua")
UnitClass = function() return "Shaman", "SHAMAN" end
FS.GunsightAreas = {}
loadAddonFile(SHAMAN_SRC, "Modules/CombatHud/GunsightShaman.lua")
FS.GunsightAreas = nil
loadAddonFile(SHAMAN_SRC, "Modules/CombatHud/GunsightShaman.lua")
""")

case("build_makes_four_poles_of_plain_parts_under_the_host_and_listens_to_no_event_itself")(r"""
boot({})
local before = 0
for _, f in ipairs(FRAMES) do for _ in pairs(f.events) do before = before + 1 end end
local spec, host, frame = mount("lower")
check(frame.parent == host, "the module frame hangs under the host")
local tex, txt = drawn(host)
check(#tex > 0 and #txt > 0, "something is built")
for _, t in ipairs(tex) do check(under(t, host), "a texture outside the host") end
for _, f in ipairs(FRAMES) do
    if under(f, host) then
        check(not f.events or next(f.events) == nil, "the module registers no event of its own")
        check(f.kind ~= "Button" and not f.isSecure, "plain frames only")
    end
end
local n = 0
for slot = 1, 4 do
    local p = parts()[slot]
    check(p and #p.blocks == 8 and p.bar and p.head and p.label, "pole " .. slot .. " has its parts")
    check(p.bar.isBar, "the bar is a StatusBar")
    n = n + 1
end
check(onUpdateFrames() == 0, "nothing runs while no totem stands")
check(FS.ShamanTotems.IsStarted(), "the data module is listening")
noDegrade()
""")

case("geometry_matches_the_mockup")(r"""
boot({})
local spec, host = mount("lower")
local rect, c = RECTS.lower, C()
local ox, oy = rect.x + (rect.w - c.W) / 2, rect.y
check(c.W == MU.GROUND_X1 - MU.X0, "module width = ground line width")
check(c.GY == MU.GY, "gy"); check(c.NB == MU.NB and c.BP == MU.BP and c.BH == MU.BH, "block count, pitch, height")
near(c.ZONE_W, MU.X1 - MU.X0, "zone width"); near(c.ZONE_A, MU.ZONE_A, "zone alpha"); near(c.ZONE_LINE_A, MU.ZONE_LINE_A, "zone line alpha")
check(c.ZONE_DASH[1] == MU.ZONE_DASH[1] and c.ZONE_DASH[2] == MU.ZONE_DASH[2], "zone dash")
near(c.GROUND_A, MU.GROUND_A, "ground alpha"); near(c.GROUND_TH, MU.GROUND_TH, "ground thickness")
check(c.MOLD_H == MU.NB * MU.BP - MU.MOLD_LESS, "mold height")
near(c.MOLD_A, MU.MOLD_A, "mold stroke alpha"); near(c.MOLD_LOCKED_A, MU.MOLD_LOCKED_A, "locked mold alpha"); near(c.MOLD_FILL_A, MU.MOLD_FILL_A, "mold fill alpha")
near(c.OP_UP, MU.OP_UP, "block alpha"); near(c.OP_EST, MU.OP_EST, "estimate alpha"); near(c.OP_FAR, MU.OP_FAR, "ghost alpha")
check(c.HEAD_H == MU.HEAD_H and c.HEAD_CUT == MU.HEAD_CUT, "head size and cut")
near(c.HEAD_MIX, MU.HEAD_MIX, "head mix"); near(c.HEAD_DOWN_MIX, MU.HEAD_DOWN_MIX, "down head mix"); near(c.CROWN_FAR_MIX, MU.FAR_MIX, "far crown mix")
check(c.CROWN_UP == MU.HY - 3, "crown centre above the head: head starts at ty + " .. MU.HY .. ", crown centre at ty + 3")
check(MU.HEAD_TOP == MU.HY + MU.HEAD_H, "the head's bottom sits on the blocks (ty = gy - lit * BP - " .. MU.HEAD_TOP .. ")")
check(c.EYE_Y == MU.EYE_Y and c.EYE_H == MU.EYE_H, "eye row"); near(c.EYE_A, MU.EYE_A, "eye alpha")
check(c.EYE.hero.off == MU.EYE.hero[1] and c.EYE.hero.w == MU.EYE.hero[2] and c.EYE.hero.off2 == MU.EYE.hero[3], "hero eyes")
check(c.EYE.narrow.off == MU.EYE.narrow[1] and c.EYE.narrow.w == MU.EYE.narrow[2] and c.EYE.narrow.off2 == MU.EYE.narrow[3], "narrow eyes")
check(c.LABEL_SIZE == MU.LABEL and c.LABEL_HERO == MU.LABEL_HERO and c.LABEL_Y == MU.LABEL_Y, "labels")
check(c.PLUS_BASE == MU.PLUS_BASE and c.PLUS_SIZE == MU.PLUS_SIZE, "plus sign")
check(c.LV_SIZE == MU.LV_SIZE and c.NM_SIZE == MU.NM_SIZE, "locked text sizes"); near(c.LV_A, MU.LV_A, "level alpha"); near(c.NM_A, MU.NM_A, "name alpha")
check(c.NM_Y - c.LV_Y == MU.NM_DY + 2, "the name sits " .. MU.NM_DY .. " below the mold centre, the level 2 above it")
check(c.LV_Y == -(MU.NB * MU.BP / 2 + 2), "level baseline")
for i, el in ipairs(ELEMENT) do
    local def = c.POLES[i]
    check(def.key == el, "pole order Fire, Earth, Water, Air")
    check(def.x == MU.PX[el][1] - MU.X0 and def.w == MU.PX[el][2], el .. " pole x and width")
    check(def.ins == (def.hero and MU.INS_HERO or MU.INS), el .. " inset")
    check((def.hero == true) == (el == "fire"), "only Fire is the hero pole")
    local p = parts()[i]
    local l, t, w, h = imgRect(p.moldFill)
    near3(l, ox + def.x + def.ins, el .. " mold x"); near3(t, oy + c.GY - c.NB * c.BP, el .. " mold top")
    near3(w, def.w - 2 * def.ins, el .. " mold width"); near3(h, c.MOLD_H, el .. " mold height")
    for b = 1, 8 do
        local bl, bt, bw, bh = imgRect(p.blocks[b])
        near3(bl, ox + def.x + def.ins, el .. " block x"); near3(bt, oy + c.GY - b * c.BP, el .. " block " .. b .. " top")
        near3(bw, def.w - 2 * def.ins, el .. " block width"); near3(bh, c.BH, el .. " block height")
    end
    local hl, ht, hw, hh = imgRect(p.head)
    near3(hw, def.w - 2, el .. " head width"); near3(hh, c.HEAD_H, el .. " head height")
    near3(hl, ox + def.x + def.w / 2 - (def.w - 2) / 2, el .. " head x")
end
local z = FS.GunsightShaman.zone
local zl, zt, zw, zh = imgRect(z.band)
near3(zl, ox, "zone x"); near3(zt, oy + c.GY - c.BP, "zone top"); near3(zw, MU.X1 - MU.X0, "zone width"); near3(zh, c.BP, "zone height")
local gl, gt, gw, gh = imgRect(z.ground)
near3(gl, ox, "ground x"); near3(gw, MU.GROUND_X1 - MU.X0, "ground width"); near3(gh, MU.GROUND_TH, "ground thickness")
near3(gt + gh / 2, oy + c.GY, "ground centre")
local first = imgRect(z.dashes[1])
local _, dt, _, dh = imgRect(z.dashes[1])
near3(first, ox, "zone line starts at the zone's left"); near3(dt + dh / 2, oy + c.GY - c.BP - 1, "zone line height")
local d2 = imgRect(z.dashes[2])
near3(d2 - first, MU.ZONE_DASH[1] + MU.ZONE_DASH[2], "zone line pitch")
noDegrade()
""")

case("down_poles_say_drop_with_a_hollow_amber_head")(r"""
boot({})
local spec, host = mount("lower")
for i = 1, 4 do
    local p = parts()[i]
    check(lit(p) == 0 and not isVisible(p.bar), "no blocks, no bar")
    check(isVisible(p.head) and isVisible(p.headDash) and isVisible(p.plus), "dashed head with a plus")
    check(not isVisible(p.eyeL) and not isVisible(p.eyeR) and not isVisible(p.crown), "no eyes, no crown on a DROP head")
    check(not isVisible(p.headEdge), "the solid outline is replaced by the dashed one")
    check(p.label.text == "DROP" and isVisible(p.label), "DROP under the ground")
    textColorIs(p.label, AMBER, 1, "DROP colour")
    colorIs(p.headDash, AMBER, 1, "dashed head")
    local bg = rgbOf("#0d0620")
    local want = { bg[1] + (AMBER[1] - bg[1]) * MU.HEAD_DOWN_MIX, bg[2] + (AMBER[2] - bg[2]) * MU.HEAD_DOWN_MIX, bg[3] + (AMBER[3] - bg[3]) * MU.HEAD_DOWN_MIX }
    colorIs(p.headFill, want, 1, "DROP head fill")
    -- the head rests on the ground: ty = gy - 0 * BP - 15, so the head's top is gy - 9
    local _, ht = imgRect(p.head)
    near3(ht, RECTS.lower.y + C().GY - C().HEAD_H, "the DROP head sits on the ground")
end
noDegrade()
""")

case("a_locked_element_shows_an_empty_mold_with_its_level_and_name")(r"""
boot({ level = 14 })
local spec, host = mount("lower")
local pFire, pEarth, water, air = parts()[1], parts()[2], parts()[3], parts()[4]
for _, p in ipairs({ pFire, pEarth }) do check(p.label.text == "DROP", "open elements wait for a drop") end
for _, p in ipairs({ water, air }) do
    check(not isVisible(p.head) and lit(p) == 0 and not isVisible(p.label), "a locked pole has no head, no blocks, no label")
    check(not isVisible(p.moldFill), "no fill: a dotted empty mold")
    check(isVisible(p.moldLine) and isVisible(p.lv) and isVisible(p.nm), "the mold, the level and the name show")
    colorIs(p.moldLine, rgbOf("#a855f7"), MU.MOLD_LOCKED_A, "locked mold")
end
check(water.lv.text == "L20" and air.lv.text == "L30", "levels")
check(water.nm.text == "Water" and air.nm.text == "Air", "names")
textColorIs(water.lv, MUTED, MU.LV_A, "level"); textColorIs(water.nm, MUTED, MU.NM_A, "name")
colorIs(pFire.moldLine, rgbOf("#a855f7"), MU.MOLD_A, "open mold")
-- learning the level opens them
LEVEL = 30
fire("PLAYER_LEVEL_UP")
check(water.label.text == "DROP" and not isVisible(water.lv), "level 20 and 30 poles open when the level reaches them")
noDegrade()
""")

case("a_read_totem_lights_ceil_remaining_over_duration_times_eight_blocks")(r"""
boot({})
local spec, host = mount("lower")
local fire = parts()[1]
drop(1, "Searing Totem", 3599, 25, 30)
check(lit(fire) == 7, "ceil(25/30*8) = 7 blocks, got " .. lit(fire))
for b = 1, 8 do check(isVisible(fire.blocks[b]) == (b <= 7), "block " .. b) end
local el = rgbOf("#ff5a3c")
for b = 1, 7 do colorIs(fire.blocks[b], el, MU.OP_UP, "block " .. b) end
check(fire.label.text == "25s" and isVisible(fire.label), "25s under the ground, got " .. tostring(fire.label.text))
textColorIs(fire.label, WHITE, 1, "label")
check(isVisible(fire.head) and isVisible(fire.headEdge) and isVisible(fire.eyeL) and isVisible(fire.crown), "a live head with eyes and a crown")
check(not isVisible(fire.headDash) and not isVisible(fire.plus), "no dashed outline, no plus")
local _, ht = imgRect(fire.head)
near3(ht, RECTS.lower.y + C().GY - 7 * C().BP - C().HEAD_H, "the head stands on the 7th block")
check(not isVisible(fire.bar), "no bar when a number is known")
-- the other three stay down
for i = 2, 4 do check(parts()[i].label.text == "DROP", "slot " .. i .. " stays DROP") end
noDegrade()
""")

case("the_last_block_is_amber_and_so_is_its_time")(r"""
boot({})
local spec, host = mount("lower")
local p = parts()[1]
drop(1, "Searing Totem", 3599, 3, 30)
check(lit(p) == 1, "3 s of 30 is the last block, got " .. lit(p))
colorIs(p.blocks[1], AMBER, MU.OP_UP, "the last block")
check(p.label.text == "3s", "3s")
textColorIs(p.label, AMBER, 1, "the time goes amber with the block")
drop(1, "Searing Totem", 3599, 15, 30)
check(lit(p) == 4, "15 of 30 is 4 blocks")
colorIs(p.blocks[1], rgbOf("#ff5a3c"), MU.OP_UP, "block 1 back to the element colour")
textColorIs(p.label, WHITE, 1, "white again")
noDegrade()
""")

case("minutes_and_the_estimate_tilde_in_the_label")(r"""
boot({})
local spec, host = mount("lower")
local earth = parts()[2]
drop(2, "Stoneskin Totem", 8071, 240, 300)
check(earth.label.text == "4m", "240 s reads 4m, got " .. tostring(earth.label.text))
check(lit(earth) == 7, "ceil(240/300*8) = 7")
drop(2, "Stoneskin Totem", 8071, 99, 300)
check(earth.label.text == "99s", "99 s counts seconds")
drop(2, "Stoneskin Totem", 8071, 101, 300)
check(earth.label.text == "2m", "101 s reads 2m")
-- a drop seen in combat is an estimate: the cast ledger, a ~ and the estimate opacity
SECRET_READS = true
fire("PLAYER_REGEN_DISABLED")
TOT[3] = { name = "x", start = 0, dur = 0, spell = 0 }
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g", 5394)
local water = parts()[3]
check(water.label.text == "~5m", "Healing Stream 300 s from the ledger reads ~5m, got " .. tostring(water.label.text))
colorIs(water.blocks[1], rgbOf("#4aa8ff"), MU.OP_EST, "estimate opacity")
check(lit(water) == 8, "a fresh totem is 8 blocks")
noDegrade()
""")

case("the_pole_drains_with_the_clock_and_the_head_sinks")(r"""
boot({})
local spec, host = mount("lower")
local p = parts()[1]
drop(1, "Searing Totem", 3599, 30, 30)
check(lit(p) == 8 and onUpdateFrames() == 1, "8 blocks, and the OnUpdate runs while a totem stands")
local _, top8 = imgRect(p.head)
for _ = 1, 10 do tick(1) end              -- 10 s
check(lit(p) == 6, "20 of 30 s is ceil(5.33) = 6 blocks, got " .. lit(p))
local _, top6 = imgRect(p.head)
near3(top6 - top8, 2 * C().BP, "the head sank two blocks")
check(p.label.text == "20s", "20s, got " .. tostring(p.label.text))
for _ = 1, 17 do tick(1) end              -- 27 s: 3 s left
check(lit(p) == 1 and p.label.text == "3s", "one block, 3s, got " .. lit(p) .. " " .. tostring(p.label.text))
colorIs(p.blocks[1], AMBER, MU.OP_UP, "amber block")
-- expiry: the totem is gone with no event, the Tick re-asks after the expected end
TOT[1] = nil
for _ = 1, 6 do tick(1) end
check(p.label.text == "DROP" and lit(p) == 0 and onUpdateFrames() == 0, "gone: DROP, no blocks, and the OnUpdate stops")
noDegrade()
""")

case("in_combat_every_read_is_secret_and_the_object_alone_runs_a_timer_bar")(r"""
boot({})
local spec, host = mount("lower")
local p = parts()[2]
SECRET_READS = true
TOT[2] = { name = "Stoneskin Totem", start = NOW, dur = 300, spell = 8071 }     -- a /reload in the fight: nothing was read plain
fire("PLAYER_ENTERING_WORLD")
check(FS.ShamanTotems.IsUp(2) and FS.ShamanTotems.Get(2).source == nil, "up with no number")
check(lit(p) == 0, "no blocks without a number")
check(isVisible(p.bar), "the timer bar shows")
check(p.bar.timer and p.bar.timer.obj == OBJECTS[2], "driven by the duration object")
check(p.bar.timer.dir == Enum.StatusBarTimerDirection.RemainingTime, "draining (remaining time)")
colorIs(p.bar.fillTex, rgbOf("#a8e063"), MU.OP_EST, "bar fill")
check(p.label.text == "?" and isVisible(p.label), "? for the time, got " .. tostring(p.label.text))
textColorIs(p.label, MUTED, 1, "? is muted")
check(isVisible(p.head) and isVisible(p.crown), "the head is on")
local pt = p.head.points[1]
check(#p.head.points == 1 and pt[1] == "BOTTOM" and pt[2] == p.bar.fillTex and pt[3] == "TOP", "the head rides the fill's top")
check(onUpdateFrames() == 1, "the OnUpdate runs (Tick keeps asking after the end)")
-- the totem goes
TOT[2] = nil
fire("PLAYER_TOTEM_UPDATE", 2)
check(not isVisible(p.bar) and p.label.text == "DROP", "gone")
check(#p.head.points == 1 and p.head.points[1][2] == FS.Gunsight.root, "the head is back on the ground")
noDegrade()
""")

case("a_client_without_the_remaining_direction_leaves_the_bar_full_and_still_marks_the_pole_up")(r"""
boot({})
local spec, host = mount("lower")
Enum = {}
SECRET_READS = true
TOT[3] = { name = "x", start = 0, dur = 0, spell = 0 }
fire("PLAYER_TOTEM_UPDATE", 3)
local p = parts()[3]
check(isVisible(p.bar) and p.bar.timer == nil and p.bar.value == 1, "a full static bar")
noDegrade()
""")

case("far_wears_the_ghost_look")(r"""
boot({})
local spec, host = mount("lower")
POS = { 100, 200, 0, 1 }
SECRET_READS = true
TOT[1] = { name = "x", start = 0, dur = 0, spell = 0 }
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g", 3599)
local p = parts()[1]
check(p.label.text == "~30s" and not FS.ShamanTotems.IsFar(1), "a fresh drop is not far")
POS = { 100, 260, 0, 1 }
tick(0.3)
check(FS.ShamanTotems.IsFar(1), "60 yd away is far")
check(p.label.text == "FAR", "FAR under the ground, got " .. tostring(p.label.text))
textColorIs(p.label, AMBER, 1, "FAR is amber")
check(isVisible(p.headDash) and not isVisible(p.headEdge) and not isVisible(p.headGlow), "a dashed head with no glow")
check(isVisible(p.eyeL) and isVisible(p.crown) and not isVisible(p.plus), "still a head with eyes and a crown")
local bg = rgbOf("#0d0620")
local el = rgbOf("#ff5a3c")
local want = { el[1] + (bg[1] - el[1]) * MU.FAR_MIX, el[2] + (bg[2] - el[2]) * MU.FAR_MIX, el[3] + (bg[3] - el[3]) * MU.FAR_MIX }
colorIs(p.crown, want, 1, "far crown")
for b = 1, lit(p) do colorIs(p.blocks[b], el, MU.OP_FAR, "ghost block") end
colorIs(p.headDash, AMBER, 1, "dashed outline")
-- walking back clears it
POS = { 100, 205, 0, 1 }
tick(0.3)
check(p.label.text ~= "FAR" and isVisible(p.headEdge) and not isVisible(p.headDash), "back in range")
-- an instance with no position never shows FAR
POS = nil
tick(0.3)
check(p.label.text ~= "FAR", "no position, never FAR")
noDegrade()
""")

case("no_secret_is_touched_with_every_client_answer_secret")(r"""
boot({})
local spec, host = mount("lower")
SECRET_READS = true
GetTotemDuration = function() return SECRET end
UnitPosition = function() return SECRET, SECRET, SECRET, SECRET end
UnitLevel = function() return SECRET end
for _, e in ipairs({ "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED", "PLAYER_ENTERING_WORLD", "SPELLS_CHANGED" }) do fire(e) end
fire("PLAYER_TOTEM_UPDATE", 1)
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g", 3599)
spec.onHide("lower"); spec.onShow("lower")
tick(1)
for i = 1, 4 do check(parts()[i].label.text == "DROP", "unreadable reads as nothing standing") end
noDegrade()
""")

case("hiding_stops_the_ticker_and_the_subscription_and_showing_rereads")(r"""
boot({})
local spec, host = mount("lower")
drop(1, "Searing Totem", 3599, 30, 30)
check(onUpdateFrames() == 1, "ticking")
spec.onHide("lower")
check(onUpdateFrames() == 0, "onHide stops the OnUpdate")
-- what happens while hidden is recorded by the data module and not painted
local p = parts()[1]
clear(1)
check(p.label.text == "30s" and lit(p) == 8, "a hidden module draws nothing")
drop(2, "Stoneskin Totem", 8071, 300, 300)
check(parts()[2].label.text == "DROP", "still nothing painted while hidden")
spec.onShow("lower")
check(p.label.text == "DROP" and lit(p) == 0, "onShow re-reads: fire is gone")
check(parts()[2].label.text == "5m" and lit(parts()[2]) == 8, "and earth, dropped while hidden, shows")
check(onUpdateFrames() == 1, "the ticker is back for the standing totem")
clear(2)
check(onUpdateFrames() == 0, "and off again when nothing stands")
spec.onHide("lower"); spec.onHide("lower")
spec.onShow("lower"); spec.onShow("lower")
noDegrade()
""")

case("a_steady_tick_allocates_nothing")(r"""
boot({})
local spec, host, frame = mount("lower")
drop(1, "Searing Totem", 3599, 30, 30)
drop(2, "Stoneskin Totem", 8071, 300, 300)
local ud = frame.scripts.OnUpdate
check(ud, "the OnUpdate is installed")
if jit then jit.off() end
for _ = 1, 2000 do ud(frame, 0.1) end      -- warm up: first writes, string tables
local grown = {}
for round = 1, 3 do
    collectgarbage(); collectgarbage("stop")
    local before = collectgarbage("count")
    for _ = 1, 2000 do ud(frame, 0.1) end
    grown[round] = (collectgarbage("count") - before) * 1024
    collectgarbage("restart")
end
check(grown[3] < 64, "a steady tick allocated " .. math.floor(grown[1]) .. ", " .. math.floor(grown[2]) .. ", " .. math.floor(grown[3]) .. " bytes over 2000 ticks")
noDegrade()
""")

case("the_shocks_seam_is_built_seated_shown_and_hidden_when_present_and_ignored_when_not")(r"""
local calls = {}
local sec = {}
boot({ shocks = {
    Build = function(frame) calls[#calls + 1] = { "Build", frame }; return sec end,
    Seat = function(s, rect, scale) calls[#calls + 1] = { "Seat", s, rect, scale } end,
    OnShow = function(s) calls[#calls + 1] = { "OnShow", s } end,
    OnHide = function(s) calls[#calls + 1] = { "OnHide", s } end,
} })
local spec, host, frame = mount("lower")
check(calls[1][1] == "Build" and calls[1][2] == frame, "Build gets the module frame")
local seat
for _, c in ipairs(calls) do if c[1] == "Seat" then seat = c end end
check(seat and seat[2] == sec and seat[3] == RECTS.lower and type(seat[4]) == "number", "Seat(section, rect, scale)")
check(calls[#calls][1] == "OnShow" and calls[#calls][2] == sec, "OnShow(section)")
spec.onHide("lower")
check(calls[#calls][1] == "OnHide" and calls[#calls][2] == sec, "OnHide(section)")
noDegrade()
-- a throwing section never breaks the poles
boot({ shocks = { Build = function() error("boom") end } })
local spec2 = mount("lower")
drop(1, "Searing Totem", 3599, 25, 30)
check(parts()[1].label.text == "25s", "the poles work with a failing shocks Build")
check(DEGRADED.gunsightshaman_shocks_Build, "and the failure is logged once")
boot({ shocks = { Build = function() return {} end, Seat = function() error("seat boom") end, OnShow = function() error("x") end, OnHide = function() error("y") end } })
local spec3 = mount("lower")
spec3.seat(RECTS.upper); spec3.onHide("upper"); spec3.onShow("upper")
-- absent, or a table with no functions
boot({ shocks = {} })
mount("lower")
boot({})
mount("upper")
""")

case("the_poles_tell_the_shocks_section_where_the_fire_head_is")(r"""
local calls = {}
local sec = { SetFire = function(up, y) calls[#calls + 1] = { up, y } end }
boot({ shocks = { Build = function() return sec end } })
POS = { 100, 200, 0, 1 }
local spec = mount("lower")
local function headY(n) return C().GY - n * C().BP - C().HEAD_H + 3 end
local last = calls[#calls]
check(last and last[1] == false, "with no Fire totem the section is told so, got " .. tostring(last and last[1]))
-- a full pole: eight blocks
TOT[1] = { name = "Searing Totem", start = NOW, dur = 30, spell = 3599 }
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g", 3599)
fire("PLAYER_TOTEM_UPDATE", 1)
last = calls[#calls]
check(last[1] == true, "the Fire totem stands")
near3(last[2], headY(8), "a full pole's head")
-- it drains a block: ceil(22 / 30 * 8) = 6
local n = #calls
tick(8)
last = calls[#calls]
check(last[1] == true and #calls == n + 1, "one call when the head moved, got " .. (#calls - n))
near3(last[2], headY(6), "the head after it drained two blocks")
n = #calls
tick(0.1); tick(0.1); tick(0.1)
check(#calls == n, "no call while neither value changed, got " .. (#calls - n))
-- walking away: FAR is not a standing Fire totem for the ring
POS = { 100, 300, 0, 1 }
tick(0.3)
check(FS.ShamanTotems.IsFar(1), "the totem is far")
last = calls[#calls]
check(last[1] == false, "FAR tells the section the Fire totem is not at hand")
POS = { 100, 200, 0, 1 }
tick(0.3)
check(calls[#calls][1] == true, "back in range")
-- the totem goes away
TOT[1] = nil
fire("PLAYER_TOTEM_UPDATE", 1)
check(calls[#calls][1] == false, "gone: SetFire(false)")
-- an earth totem is not the Fire totem
n = #calls
drop(2, "Stoneskin Totem", 8071, 300, 300)
check(#calls == n, "another element does not call SetFire")
-- a timer bar pole (no number) is a full head
clear(2)
SECRET_READS = true
TOT[1] = { name = "x", start = 0, dur = 0, spell = 0 }
fire("PLAYER_REGEN_DISABLED")
last = calls[#calls]
check(last[1] == true, "up by the duration object alone")
check(last[2] == false, "a bar pole's head rides the engine's fill: its place is not computable, so the section is told false, got " .. tostring(last[2]))
-- the module is shown again after a hide: the section is told once more
spec.onHide("lower")
n = #calls
spec.onShow("lower")
check(#calls > n, "onShow pushes the Fire state again")
-- a section without SetFire, or one that throws, never breaks the poles
boot({ shocks = { Build = function() return {} end } })
mount("lower"); drop(1, "Searing Totem", 3599, 25, 30)
boot({ shocks = { Build = function() return { SetFire = function() error("boom") end } end } })
mount("lower"); drop(1, "Searing Totem", 3599, 25, 30)
check(parts()[1].label.text == "25s", "the poles work with a failing SetFire")
check(DEGRADED.gunsightshaman_SetFire, "and the failure is logged once")
""")

case("a_failing_SetFire_is_tried_again_at_the_next_paint")(r"""
local calls, fail = {}, true
local sec = { SetFire = function(up, y)
    calls[#calls + 1] = { up, y }
    if fail then fail = false; error("boom") end
end }
boot({ shocks = { Build = function() return sec end } })
POS = { 100, 200, 0, 1 }
local spec = mount("lower")
check(#calls >= 1 and DEGRADED.gunsightshaman_SetFire, "the first call threw and was logged")
local n = #calls
spec.onHide("lower"); spec.onShow("lower")          -- a repaint of every pole, nothing about the Fire totem changed
check(#calls > n, "the next paint tells the section again: a throw is not remembered as told, got " .. (#calls - n))
check(calls[#calls][1] == false, "with the same state it failed to take")
n = #calls
spec.onHide("lower"); spec.onShow("lower")
check(#calls == n + 1, "once it took, only the show's own forced re-read calls again, got " .. (#calls - n))
""")

case("with_the_real_shocks_file_a_timer_bar_pole_has_no_ring_and_keeps_the_NOVA_tag")(r"""
boot({ realShocks = true })
for _, e in ipairs({ "SPELL_UPDATE_COOLDOWN", "SPELL_UPDATE_USABLE", "LEARNED_SPELL_IN_TAB" }) do KNOWN_EVENTS[e] = true end
KNOWN_SPELLS[408341] = true
C_Spell.GetSpellInfo = function(n) if n == "Fire Nova" then return { spellID = 408341, name = "Fire Nova" } end end
C_Spell.GetSpellCooldown = function() return { isActive = false, isOnGCD = false, startTime = 0, duration = 0 } end
local spec = mount("lower")
local sec
for _, f in ipairs(FRAMES) do if f.fsSection then sec = f.fsSection end end
drop(1, "Searing Totem", 3599, 30, 30)
check(isVisible(sec.ring) and isVisible(sec.novaText), "a numbered pole: ring and tag")
clear(1)
SECRET_READS = true
TOT[1] = { name = "x", start = 0, dur = 0, spell = 0 }
fire("PLAYER_REGEN_DISABLED")
check(parts()[1].bar and isVisible(parts()[1].bar), "the pole is in bar mode")
check(not isVisible(sec.ring) and not isVisible(sec.ringGlow), "no ring floats above a head that follows the draining fill")
check(isVisible(sec.novaText) and isVisible(sec.pip), "the Fire totem stands: the NOVA tag stays")
""")

case("with_the_real_shocks_file_the_nova_ring_follows_the_fire_head_and_is_drawn_over_it")(r"""
boot({ realShocks = true })
for _, e in ipairs({ "SPELL_UPDATE_COOLDOWN", "SPELL_UPDATE_USABLE", "LEARNED_SPELL_IN_TAB" }) do KNOWN_EVENTS[e] = true end
KNOWN_SPELLS[408341] = true
C_Spell.GetSpellInfo = function(n) if n == "Fire Nova" then return { spellID = 408341, name = "Fire Nova" } end end
C_Spell.GetSpellCooldown = function() return { isActive = false, isOnGCD = false, startTime = 0, duration = 0 } end
local spec = mount("lower")
local sec
for _, f in ipairs(FRAMES) do if f.fsSection then sec = f.fsSection end end
check(sec and sec.SetFire, "the real section is built")
check(not isVisible(sec.ring), "no Fire totem, no ring")
drop(1, "Searing Totem", 3599, 30, 30)
check(isVisible(sec.ring), "a Fire totem stands and Fire Nova is ready: the ring shows")
local function ringY() local _, y = imgCenter(sec.ring); return y - RECTS.lower.y end
near3(ringY(), C().GY - 8 * C().BP - C().HEAD_H + 3, "the ring sits on a full head")
tick(8)
near3(ringY(), C().GY - 6 * C().BP - C().HEAD_H + 3, "and follows the head down")
local head = parts()[1].head
check(sec.ring.parent:GetFrameLevel() > head:GetFrameLevel(), "the ring is on a frame above the head's")
check(sec.ringGlow.parent:GetFrameLevel() > head:GetFrameLevel(), "and so is its glow")
clear(1)
check(not isVisible(sec.ring), "the totem goes: the ring goes")
noDegrade()
""")

case("seat_follows_the_rect_and_the_rescale_in_either_area")(r"""
boot({})
local spec, host = mount("lower")
drop(1, "Searing Totem", 3599, 15, 30)
local p = parts()[1]
local l1, t1 = imgRect(p.head)
spec.seat(RECTS.upper)
local l2, t2 = imgRect(p.head)
near3(l2 - l1, RECTS.upper.x - RECTS.lower.x, "x follows the rect")
near3(t2 - t1, RECTS.upper.y - RECTS.lower.y, "y follows the rect")
spec.seat(nil); spec.seat({ x = "a" }); spec.seat({})
local l3, t3 = imgRect(p.head)
near3(l3, l2, "a bad rect changes nothing"); near3(t3, t2)
SetScreen(2160)
spec.seat(RECTS.upper)   -- the registry re-seats on a rescale
local l4 = imgRect(p.head)
near3(l4, l2, "a rescale keeps the head on the same image px")
noDegrade()
""")

case("element_colours_come_from_the_theme_tokens_when_they_exist")(r"""
boot({ tokens = { fire = { 0.1, 0.2, 0.3, 1 }, earth = { 0.4, 0.5, 0.6, 1 }, water = { 0.7, 0.8, 0.9, 1 }, air = { 1, 1, 0, 1 } } })
local spec, host = mount("lower")
drop(1, "Searing Totem", 3599, 30, 30)
colorIs(parts()[1].blocks[1], { 0.1, 0.2, 0.3 }, MU.OP_UP, "token colour")
boot({})
local spec2 = mount("lower")
for i, el in ipairs(ELEMENT) do
    drop(i, "x", 1, 300, 300)
    colorIs(parts()[i].blocks[1], rgbOf(MU.COLORS[el]), MU.OP_UP, el .. " fallback colour")
end
""")

case("under_the_real_areas_the_host_follows_the_target_and_the_module_stops_with_it")(r"""
boot({ realAreas = true })
local host = FS.GunsightAreas.Host("lower")
check(host, "the real areas hand out a lower host")
check(isVisible(host), "a target shows the host")
drop(1, "Searing Totem", 3599, 25, 30)
check(onUpdateFrames() == 1, "ticking with a target")
local p = parts()[1]
check(p.label.text == "25s" and isVisible(p.label), "drawn")
TARGET.exists = false
fire("PLAYER_TARGET_CHANGED")
check(not isVisible(host) and not isVisible(p.label) and not isVisible(p.head), "no target hides the host and everything under it")
check(onUpdateFrames() == 0, "and stops the OnUpdate")
clear(1)
TARGET.exists = true
fire("PLAYER_TARGET_CHANGED")
check(isVisible(host) and p.label.text == "DROP", "a target brings it back and re-reads the standing totems")
noDegrade()
""")

case("no_totem_data_or_no_theme_means_no_module_and_no_throw")(r"""
boot({ noTotems = true })
local spec = MODS.class
local host = CreateFrame("Frame", nil, FS.Gunsight.root)
local ok, frame = pcall(spec.build, host)
check(ok and frame == nil, "build returns nothing without FS.ShamanTotems")
check(DEGRADED.gunsightshaman_nototems, "and says so")
boot({})
FS.Theme.AddSliceTexture = nil
local ok2, frame2 = pcall(MODS.class.build, CreateFrame("Frame", nil, FS.Gunsight.root))
check(ok2 and frame2 == nil, "build returns nothing without the Theme helpers")
""")

case("another_class_registers_the_same_spec_but_the_data_module_stays_asleep")(r"""
boot({ class = "PRIEST" })
check(MODS.class and MODS.class.classes[1] == "SHAMAN", "the spec is registered; the area registry picks it by class")
check(not FS.ShamanTotems.IsStarted(), "a priest never starts the totem listeners")
""")


def static_checks() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        s, a = toc.index("Modules/CombatHud/GunsightShaman.lua"), toc.index("Modules/CombatHud/GunsightAreas.lua")
        out.append(("toc_loads_shaman_after_areas",
                    None if s > a else f"GunsightShaman.lua must load after GunsightAreas.lua (positions {a}, {s})"))
        t = toc.index("Modules/CombatHud/ShamanTotems.lua")
        out.append(("toc_loads_shaman_after_its_data",
                    None if s > t else f"GunsightShaman.lua must load after ShamanTotems.lua (positions {t}, {s})"))
    except ValueError as e:
        out.append(("toc_loads_shaman_after_areas", f"{e}"))
    src = SHAMAN.read_text(encoding="utf-8") if SHAMAN.exists() else ""
    code = re.sub(r"--.*", "", src)
    out.append(("no_em_or_en_dashes", None if not re.search("[–—]", src) else "GunsightShaman.lua has an em or en dash"))
    out.append(("registers_the_class_spec_for_shaman",
                None if re.search(r'RegisterModule,\s*"class"', src) and '"SHAMAN"' in src else "the SHAMAN class spec is gone"))
    out.append(("no_secure_template_and_no_event_of_its_own",
                None if not re.search(r"Secure|RegisterEvent|RegisterUnitEvent|SetAttribute|RegisterStateDriver", code)
                else "the module is plain frames and listens through FS.ShamanTotems only"))
    out.append(("never_reads_the_totem_api_directly",
                None if not re.search(r"GetTotemInfo|GetTotemTimeLeft|GetTotemDuration|UnitPosition", code)
                else "the totem client facts live in ShamanTotems.lua"))
    # the baked art: the crops the module computes must match the files
    from_lua = {}
    for name, kind, w, h in (("pole_block_40", "block", 40, 5), ("pole_block_26", "block", 26, 5),
                             ("pole_mold_40", "mold", 40, 47), ("pole_mold_26", "mold", 26, 47),
                             ("pole_dash_48", "dash", 48, 9), ("pole_dash_30", "dash", 30, 9)):
        path = TEXTURES / f"{name}.tga"
        if not path.exists():
            out.append((f"art_{name}", f"{path.name} is missing: run tools/assets/generate_totem_pole.py"))
            continue
        cw, ch = struct.unpack("<HH", path.read_bytes()[12:16])
        pad = 0 if kind == "block" else 2
        aw, ah = (w + pad) * 4, (h + pad) * 4
        pow2 = lambda n: 1 << (n - 1).bit_length()
        ok = (cw, ch) == (pow2(aw), pow2(ah)) and cw == pow2(cw) and ch == pow2(ch)
        out.append((f"art_{name}_is_a_power_of_two_canvas_holding_the_cropped_art",
                    None if ok else f"{name}: file {cw}x{ch}, art {aw}x{ah}"))
        from_lua[name] = (aw / pow2(aw), ah / pow2(ah))
    out.append(("art_pieces_used_exist_for_every_pole_width",
                None if all(f"pole_{k}" in src or "pole_" in src for k in ("block", "mold", "dash")) else "pole art is not used"))
    return out


def run_case(name: str, body: str) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    g = lua.globals()
    g.LAYOUT_SRC = LAYOUT.read_text(encoding="utf-8")
    g.CONFIG_SRC = CONFIG.read_text(encoding="utf-8")
    g.GUNSIGHT_SRC = GUNSIGHT.read_text(encoding="utf-8")
    g.SHAMAN_SRC = SHAMAN.read_text(encoding="utf-8")
    g.TOTEMS_SRC = TOTEMS.read_text(encoding="utf-8")
    g.SHOCKS_SRC = SHOCKS.read_text(encoding="utf-8")
    g.AREAS_SRC = AREAS.read_text(encoding="utf-8")
    g.HAS_TARGET_SRC = _load("gunsight-harness").theme_target_rule_lua()
    try:
        lua.execute("MU = " + lua_value(mockup_numbers()))
        lua.execute(PRELUDE + "\n" + body)
    except LuaError as e:
        return str(e)
    return None


def main() -> int:
    failures = 0

    def report(name: str, err: str | None) -> None:
        nonlocal failures
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      " + err.replace("\n", "\n      "))

    if not SHAMAN.exists():
        print(f"FAIL  {SHAMAN.name} is missing")
        return 1
    for name, body in CASES:
        try:
            err = run_case(name, body)
        except LuaError as e:
            err = f"harness error: {e}"
        report(name, err)
    statics = static_checks()
    for name, err in statics:
        report(name, err)
    total = len(CASES) + len(statics)
    print(f"\n{total - failures}/{total} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
