#!/usr/bin/env python3
"""Runs the real GunsightClass.lua (the Gunsight Class Module: Warlock shards, Rogue and Druid combo points) headless.

GunsightClass.lua registers the module "class" through FS.GunsightAreas.RegisterModule and draws it in the
upper or lower area the area host gives it (mockups/gunsight-modules-concepts-v7-2026-10-08.html: states A and B
for the shard count, state F for the combo points; shardsSlot and comboModule). FS.GunsightAreas is a FAKE here
with the same API as the real one (its own harness covers it). The checks pin:

  * registration: one "class" spec for WARLOCK, ROGUE and DRUID, with build, seat, onShow and onHide;
  * the shard module: ONE shard glyph and the count (never a row of four), the label SOUL SHARDS, the glyph, the
    count and the label at the mockup's offsets inside the area rect, a dim glyph and a muted 0 at zero shards,
    nothing drawn for an unknown or secret count, a Hud subscription only while the module is shown;
  * the combo module: five diamond pips (yellow, the lit ones bright) and the count, the label COMBO POINTS,
    the events that refresh it, a secret count reaching the number only through SetFormattedText with the pips
    hidden, a Druid outside cat form (or one whose form cannot be read) drawing nothing;
  * any other class (a Mage) draws nothing, a secret class token draws nothing, a rescale re-seats in place.

The mock is strict (a widget method it does not define fails as a nil call); Layout.lua, Config.lua and
Gunsight.lua are the real files. It is NOT the real client.

    python3 tools/gunsightclass-harness.py

Exit 0 = every check passed. GUNSIGHTCLASS_LUA=<path> runs another file in place of GunsightClass.lua.
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
CLASS = Path(os.environ.get("GUNSIGHTCLASS_LUA") or ADDON / "Modules/CombatHud/GunsightClass.lua")
GUNSIGHT = ADDON / "Modules/CombatHud/Gunsight.lua"
COMBATHUD = ADDON / "Modules/CombatHud/CombatHud.lua"
LAYOUT = ADDON / "Core/Layout.lua"
CONFIG = ADDON / "Core/Config.lua"
TOC = ADDON / "forever-stuwave.toc"
MOCKUP = HERE.parent / "mockups" / "gunsight-modules-concepts-v7-2026-10-08.html"
TEXTURES = ADDON / "Media" / "Textures"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DOTS_HARNESS = _load("gunsightdots-harness")


def _m(pattern: str, text: str, what: str) -> re.Match:
    m = re.search(pattern, text, re.S)
    if not m:
        sys.exit(f"mockup: cannot find {what} (pattern {pattern!r}); the mockup changed shape")
    return m


def mockup_class() -> dict:
    """The numbers shardsSlot and comboModule draw, in image px, read out of the v7 mockup."""
    src = MOCKUP.read_text(encoding="utf-8")
    shard_fn = _m(r"function shardsSlot\(\)\{(.*?)\n\}", src, "shardsSlot").group(1)
    combo_fn = _m(r"function comboModule\(\)\{(.*?)\n\}", src, "comboModule").group(1)
    lab = _m(r"txt\((\d+),(\d+),'SOUL SHARDS',(\d+),C\.violet,\{op:([\d.]+)\}\)", shard_fn, "shard label")
    gly = _m(r"shard\((\d+),(\d+),(\d+),(\d+),C\.violet,true\)", shard_fn, "shard glyph")
    num = _m(r"txt\((\d+),(\d+),'3',(\d+),C\.white\)", shard_fn, "shard number")
    clab = _m(r"txt\((\d+),(\d+),'COMBO POINTS',(\d+),C\.violet,\{op:([\d.]+)\}\)", combo_fn, "combo label")
    pip = _m(r"var cx=(\d+)\+i\*(\d+),cy=(\d+),lit=i<n;", combo_fn, "combo pip row")
    rad = _m(r"cx\+','\+\(cy-(\d+)\)", combo_fn, "pip half diagonal")
    fills = _m(r"fill-opacity=\"'\+\(lit\?\.(\d+):\.(\d+)\)", combo_fn, "pip fill alpha")
    strokes = _m(r"stroke-opacity=\"'\+\(lit\?(\d+):\.(\d+)\)", combo_fn, "pip stroke alpha")
    cnum = _m(r"txt\((\d+),(\d+),String\(n\),(\d+),C\.white\)", combo_fn, "combo number")
    yel = _m(r"Y='(#[0-9a-fA-F]{6})'", combo_fn, "pip colour")
    home = _m(r"function homeShards\(\)\{.*?\n\}", src, "homeShards").group(0)
    hg = _m(r"shard\((\d+),(\d+),([\d.]+),(\d+),C\.violet,n>0\)", home, "home glyph")
    hn = _m(r"txt\((\d+),(\d+),String\(n\),(\d+),", home, "home number")
    slot = _m(r"function emptySlot\(y,h,label\)\{\s*return '<rect x=\"(\d+)\" y=\"'\+y\+'\" width=\"(\d+)\" height=\"'\+h", src, "area rect")
    up = _m(r"emptySlot\((\d+),(\d+),'UPPER AREA", src, "upper area")
    lo = _m(r"emptySlot\((\d+),(\d+),'LOWER AREA", src, "lower area")
    shard_def = _m(r"function shard\(x,y,w,h,col,filled\)\{(.*?)\n\}", src, "shard()").group(1)
    sf = _m(r"fill-opacity=\"'\+\(filled\?\.(\d+):\.(\d+)\)", shard_def, "shard fill alpha")
    ss = _m(r"stroke-opacity=\"'\+\(filled\?(\d+):\.(\d+)\)", shard_def, "shard stroke alpha")
    hexs = yel.group(1)
    return {
        "AREA_X": int(slot.group(1)), "AREA_W": int(slot.group(2)),
        "UPPER_Y": int(up.group(1)), "LOWER_Y": int(lo.group(1)), "AREA_H": int(lo.group(2)),
        "SHARD_LABEL_X": int(lab.group(1)), "SHARD_LABEL_Y": int(lab.group(2)), "LABEL_PX": int(lab.group(3)),
        "LABEL_ALPHA": float(lab.group(4)),
        "GLYPH_X": int(gly.group(1)), "GLYPH_Y": int(gly.group(2)), "GLYPH_W": int(gly.group(3)), "GLYPH_H": int(gly.group(4)),
        "NUM_X": int(num.group(1)), "NUM_BASE": int(num.group(2)), "NUM_PX": int(num.group(3)),
        "COMBO_LABEL_X": int(clab.group(1)), "COMBO_LABEL_Y": int(clab.group(2)),
        "PIP_X0": int(pip.group(1)), "PIP_STEP": int(pip.group(2)), "PIP_Y": int(pip.group(3)), "PIP_R": int(rad.group(1)),
        "PIP_FILL_LIT": float("0." + fills.group(1)), "PIP_FILL_OFF": float("0." + fills.group(2)),
        "PIP_STROKE_LIT": float(strokes.group(1)), "PIP_STROKE_OFF": float("0." + strokes.group(2)),
        "COMBO_NUM_X": int(cnum.group(1)), "COMBO_NUM_BASE": int(cnum.group(2)), "COMBO_NUM_PX": int(cnum.group(3)),
        "YELLOW": [int(hexs[i:i + 2], 16) / 255 for i in (1, 3, 5)],
        "HOME_GLYPH_W": float(hg.group(3)), "HOME_GLYPH_H": int(hg.group(4)), "HOME_NUM_PX": int(hn.group(3)),
        "SHARD_FILL_LIT": float("0." + sf.group(1)), "SHARD_FILL_OFF": float("0." + sf.group(2)),
        "SHARD_STROKE_LIT": float(ss.group(1)), "SHARD_STROKE_OFF": float("0." + ss.group(2)),
    }


def tune_numbers() -> dict:
    """CombatHud's shard texture canvases (design px), which GunsightClass scales by the same ratios."""
    src = COMBATHUD.read_text(encoding="utf-8")
    cw = _m(r"SHARD_CANVAS_W = (\d+), SHARD_CANVAS_H = (\d+)", src, "SHARD_CANVAS")
    gc = _m(r"SHARD_GLOW_CANVAS = (\d+)", src, "SHARD_GLOW_CANVAS")
    return {"CANVAS_W": int(cw.group(1)), "CANVAS_H": int(cw.group(2)), "GLOW": int(gc.group(1))}


def lua_value(v) -> str:
    if isinstance(v, dict):
        return "{" + ",".join(f"{k}={lua_value(x)}" for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        return "{" + ",".join(lua_value(x) for x in v) + "}"
    if isinstance(v, str):
        return '"' + v + '"'
    return repr(v)


# ---------------------------------------------------------------------------------------
# The mock client: the Dots harness's strict mock, plus a fake area host, a secret sentinel and the combo APIs
# ---------------------------------------------------------------------------------------

MOCK = DOTS_HARNESS.MOCK + r"""
-- A secret: any arithmetic, comparison or concatenation raises, like the client's secret values.
SECRET = setmetatable({}, {
    __lt = function() error("SECRET_OP: compare", 2) end, __le = function() error("SECRET_OP: compare", 2) end,
    __add = function() error("SECRET_OP: arith", 2) end, __sub = function() error("SECRET_OP: arith", 2) end,
    __mul = function() error("SECRET_OP: arith", 2) end, __div = function() error("SECRET_OP: arith", 2) end,
    __unm = function() error("SECRET_OP: arith", 2) end, __concat = function() error("SECRET_OP: concat", 2) end,
    __len = function() error("SECRET_OP: len", 2) end,
})
-- The Hud stand-in lives here, not in the borrowed mock: the state is pushed by the test.
function stubHud_()
    FS.Hud = {
        GetProfile = function() return PROFILE end,
        GetState = function() return STATE end,
        Subscribe = function(fn)
            SUBS[#SUBS + 1] = fn
            if STATE then fn(STATE) end
            return fn
        end,
        Unsubscribe = function(fn)
            for i = #SUBS, 1, -1 do if SUBS[i] == fn then table.remove(SUBS, i) end end
        end,
    }
end
function push(state)
    STATE = state
    for _, fn in ipairs({ unpack(SUBS) }) do fn(state) end
end
-- SetFormattedText is a SINK: a secret reaches it (recorded), a plain value formats as usual.
do
    local FrameMT = getmetatable(UIParent).__index
    local create = FrameMT.CreateFontString
    function FrameMT:CreateFontString(...)
        local s = create(self, ...)
        function s:SetFormattedText(fmt, ...)
            if not self.hasFont then error("Font not set", 2) end
            local v = ...
            self.formatCalls = (self.formatCalls or 0) + 1
            if v == SECRET then self.text = nil; self.secretFed = true; return end
            self.secretFed = false
            self.text = string.format(fmt, ...)
        end
        return s
    end
end
"""

PRELUDE = r"""
local AREA_X, AREA_W, AREA_H = MU.AREA_X, MU.AREA_W, MU.AREA_H
RECTS = { upper = { x = AREA_X, y = MU.UPPER_Y, w = AREA_W, h = AREA_H }, lower = { x = AREA_X, y = MU.LOWER_Y, w = AREA_W, h = AREA_H } }
SECRET_FN = function(v) return v == SECRET end

-- The fake area host: the same API as FS.GunsightAreas, minus the area frames.
local function fakeAreas()
    MODS, AREA_OF, AREA_CBS = {}, {}, {}
    FS.GunsightAreas = {
        RegisterModule = function(id, spec) MODS[id] = spec; return true end,
        AreaOf = function(id) return AREA_OF[id] end,
        OnAreaChanged = function(fn) AREA_CBS[#AREA_CBS + 1] = fn end,
    }
end

COMBO, FORM_POWER = 0, { 3, "ENERGY" }
COMBO_ARGS = {}
local function boot(opts)
    opts = opts or {}
    resetWorld()
    SetScreen(opts.height or 1440)
    ForeverSTUwaveDB = opts.db
    FS.IsSecret = function(v) return SECRET_FN(v) end
    stubTheme_()
    FS.Theme.COLOR_TEXT_WHITE = { 1, 1, 1, 1 }
    FS.Theme.COLOR_MUTED = { 0.6157, 0.5765, 0.7686, 1 }
    -- the real ApplyMono sets the font and the colour; the stub records both the way SetTextColor would
    function FS.Theme.ApplyMono(fs, size, color)
        fs.monoSize, fs.hasFont = size, true
        fs.textColor = { color[1], color[2], color[3], color[4] or 1 }
    end
    stubHud_()
    assert(loadstring(HAS_TARGET_SRC, "@Theme.lua"))()
    TARGET = { exists = true, dead = false, attackable = true }
    UnitExists = function() return TARGET.exists end
    UnitIsDeadOrGhost = function() return TARGET.dead end
    UnitCanAttack = function() return TARGET.attackable end
    loadAddonFile(LAYOUT_SRC, "Core/Layout.lua")
    loadAddonFile(CONFIG_SRC, "Core/Config.lua")
    loadAddonFile(GUNSIGHT_SRC, "Modules/CombatHud/Gunsight.lua")
    fakeAreas()
    local class = opts.class or "WARLOCK"
    UnitClass = function() return "Class", opts.classToken ~= nil and opts.classToken or class end
    COMBO, FORM_POWER, COMBO_ARGS = opts.combo or 0, opts.form or { 3, "ENERGY" }, {}
    GetComboPoints = function(unit, target) COMBO_ARGS[#COMBO_ARGS + 1] = { unit, target }; return COMBO end
    UnitPowerType = function(unit) return FORM_POWER[1], FORM_POWER[2] end
    if opts.noCombo then GetComboPoints = nil end
    if opts.noPowerType then UnitPowerType = nil end
    STATE = opts.state
    loadAddonFile(CLASS_SRC, "Modules/CombatHud/GunsightClass.lua")
    fire("ADDON_LOADED", "forever-stuwave")
    fire("PLAYER_LOGIN")
    return FS.GunsightClass
end

-- Mounts the registered module the way the area host does: build(host), seat(rect), onShow(area).
local function mount(area)
    local spec = MODS.class
    check(spec, "no class module registered")
    local host = CreateFrame("Frame", nil, FS.Gunsight.root)
    host:SetSize(1, 1)
    local frame = spec.build(host)
    check(frame ~= nil, "build(host) returned no frame")
    spec.seat(RECTS[area])
    spec.onShow(area)
    return spec, host, frame
end

local function under(r, host)
    while r do if r == host then return true end; r = r.parent end
    return false
end
-- Every texture and font string under `host` that is visible (itself and every ancestor shown).
local function drawn(host)
    local tex, txt = {}, {}
    for _, t in ipairs(TEXTURES) do if under(t, host) and isVisible(t) then tex[#tex + 1] = t end end
    for _, s in ipairs(FONTSTRINGS) do if under(s, host) and isVisible(s) then txt[#txt + 1] = s end end
    return tex, txt
end
local function texWith(host, name)
    local out = {}
    local tex = drawn(host)
    for _, t in ipairs(tex) do if t.path and t.path:find(name, 1, true) then out[#out + 1] = t end end
    return out
end
local function textOf(host, str)
    local _, txt = drawn(host)
    for _, s in ipairs(txt) do if s.text == str then return s end end
    return nil
end
-- image px of a region's centre
local function cx(r) local x, y = imgCenter(r); return x, y end
local K = 1.28
TEXT_MID = 0.35        -- a line's visual centre sits this fraction of its size above the baseline (GunsightClass.TEXT_MID)
local function near3(a, b, what) near(a, b, what, 1e-2) end
local function fsPx(s) return s.monoSize / (K * FS.Layout.Scale()) end
local function colorIs(c, want, what)
    for i = 1, 3 do near(c[i], want[i], what .. " channel " .. i, 1e-3) end
end
local function shardState(n) return { active = true, class = "WARLOCK", row = {}, buffsMissing = {}, procs = {}, inCombat = false, shards = n } end
"""

CASES: list[tuple[str, str]] = []


def case(name: str):
    def deco(body: str):
        CASES.append((name, body))
        return body
    return deco


case("registers_one_class_module_for_warlock_rogue_and_druid_through_the_seam")(r"""
boot({ class = "WARLOCK" })
local spec = MODS.class
check(spec, "no module registered under the id class")
local seen = {}
for _, c in ipairs(spec.classes) do seen[c] = true end
check(#spec.classes == 3 and seen.WARLOCK and seen.ROGUE and seen.DRUID, "classes must be exactly WARLOCK, ROGUE, DRUID, got " .. #spec.classes)
for _, f in ipairs({ "build", "seat", "onShow", "onHide" }) do
    check(type(spec[f]) == "function", "the module has no " .. f)
end
check(#DEGRADED == 0 and next(DEGRADED) == nil, "a degrade was logged: " .. tostring(next(DEGRADED)))
""")

case("without_the_areas_seam_nothing_registers_and_nothing_throws")(r"""
resetWorld()
SetScreen(1440)
FS.IsSecret = function(v) return false end
stubTheme_(); stubHud_()
loadAddonFile(LAYOUT_SRC, "Core/Layout.lua"); loadAddonFile(CONFIG_SRC, "Core/Config.lua"); loadAddonFile(GUNSIGHT_SRC, "Modules/CombatHud/Gunsight.lua")
UnitClass = function() return "Class", "WARLOCK" end
FS.GunsightAreas = {}
loadAddonFile(CLASS_SRC, "Modules/CombatHud/GunsightClass.lua")
FS.GunsightAreas = nil
loadAddonFile(CLASS_SRC, "Modules/CombatHud/GunsightClass.lua")
""")

case("shard_module_is_one_glyph_and_the_count_at_the_mockups_offsets")(r"""
boot({ class = "WARLOCK", state = shardState(3) })
local spec, host = mount("lower")
local k = K * FS.Layout.Scale()
local lines = texWith(host, "hud_shard_line.tga")
check(#lines == 1, "one shard glyph, not a row: " .. #lines .. " line textures")
for _, name in ipairs({ "hud_shard_glow.tga", "hud_shard_fill.tga", "hud_shard_facet.tga" }) do
    check(#texWith(host, name) == 1, "exactly one " .. name .. " shown")
end
local gx, gy = cx(lines[1])
near3(gx, MU.GLYPH_X + MU.GLYPH_W / 2, "glyph centre x")
near3(gy, MU.GLYPH_Y + MU.GLYPH_H / 2, "glyph centre y")
-- the canvas is the baked line texture scaled by the glyph box over the 10 x 18 cell the files were baked for
near3(lines[1].w, MU.GLYPH_W * k * TN.CANVAS_W / FS.Gunsight.G.SH_W, "glyph canvas width")
near3(lines[1].h, MU.GLYPH_H * k * TN.CANVAS_H / FS.Gunsight.G.SH_H, "glyph canvas height")
local glow = texWith(host, "hud_shard_glow.tga")[1]
near3(glow.w, MU.GLYPH_W * k * TN.GLOW / FS.Gunsight.G.SH_W, "glow canvas width")
local num = textOf(host, "3")
check(num, "the count 3 is not drawn")
local nx, ny = cx(num)
near3(nx, MU.NUM_X, "count x (left edge)")
near3(ny, MU.NUM_BASE - TEXT_MID * MU.NUM_PX, "count centre sits TEXT_MID of its size above the baseline")
near3(fsPx(num), MU.NUM_PX, "count size in image px")
colorIs(num.textColor, FS.Theme.COLOR_TEXT_WHITE, "a held count is white")
local label = textOf(host, "SOUL SHARDS")
check(label, "the label SOUL SHARDS is not drawn")
local lx, ly = cx(label)
near3(lx, MU.SHARD_LABEL_X, "label x")
near3(ly, MU.SHARD_LABEL_Y - TEXT_MID * MU.LABEL_PX, "label y")
near3(fsPx(label), MU.LABEL_PX, "label size")
near3(label.textColor[4], MU.LABEL_ALPHA, "label alpha")
colorIs(label.textColor, FS.Theme.COLOR_BORDER, "label is the violet")
-- the glyph is lit: the violet line at full alpha, the halo shown
near3(lines[1].vertex[4], MU.SHARD_STROKE_LIT, "lit line alpha")
near3(texWith(host, "hud_shard_fill.tga")[1].vertex[4], MU.SHARD_FILL_LIT, "lit fill alpha")
""")

case("shard_module_follows_the_hud_count_and_goes_dim_at_zero")(r"""
boot({ class = "WARLOCK", state = shardState(3) })
local spec, host = mount("lower")
push(shardState(7))
check(textOf(host, "7") and not textOf(host, "3"), "the count follows the push")
check(#texWith(host, "hud_shard_line.tga") == 1, "still one glyph at seven shards")
push(shardState(0))
local zero = textOf(host, "0")
check(zero, "zero shards still draws the count 0")
colorIs(zero.textColor, FS.Theme.COLOR_MUTED, "the 0 is muted")
local line = texWith(host, "hud_shard_line.tga")[1]
check(line, "the dim glyph is still drawn at zero")
near3(line.vertex[4], MU.SHARD_STROKE_OFF, "the glyph outline is dim at zero")
check(#texWith(host, "hud_shard_glow.tga") == 0, "no halo at zero")
near3(texWith(host, "hud_shard_fill.tga")[1].vertex[4], MU.SHARD_FILL_OFF, "unlit fill alpha")
push(shardState(2))
colorIs(textOf(host, "2").textColor, FS.Theme.COLOR_TEXT_WHITE, "back to white when held")
check(#texWith(host, "hud_shard_glow.tga") == 1, "the halo returns")
""")

case("shard_module_draws_nothing_for_an_unknown_or_secret_count")(r"""
boot({ class = "WARLOCK", state = shardState(3) })
local spec, host = mount("lower")
local none = shardState(nil)
push(none)
local tex, txt = drawn(host)
check(#tex == 0 and #txt == 0, "an unknown count draws " .. #tex .. " textures and " .. #txt .. " strings")
push(shardState(4))
check(textOf(host, "4"), "back after an unknown count")
push(shardState(SECRET))
tex, txt = drawn(host)
check(#tex == 0 and #txt == 0, "a secret count draws " .. #tex .. " textures and " .. #txt .. " strings")
push(shardState("x"))
tex, txt = drawn(host)
check(#tex == 0 and #txt == 0, "a non number count draws nothing")
""")

case("shard_module_subscribes_to_the_hud_only_while_shown")(r"""
boot({ class = "WARLOCK", state = shardState(3) })
check(#SUBS == 0, "no subscription before the module is shown, got " .. #SUBS)
local spec, host = mount("lower")
check(#SUBS == 1, "one subscription while shown, got " .. #SUBS)
spec.onShow("lower")
check(#SUBS == 1, "a second onShow does not subscribe twice, got " .. #SUBS)
spec.onHide("lower")
check(#SUBS == 0, "unsubscribed on hide, got " .. #SUBS)
spec.onShow("upper")
check(#SUBS == 1, "subscribed again on the next show")
check(textOf(host, "3"), "the first push after a re-show repaints at once")
""")

case("shard_module_sits_in_the_upper_area_with_the_same_offsets")(r"""
boot({ class = "WARLOCK", state = shardState(5) })
local spec, host = mount("upper")
local line = texWith(host, "hud_shard_line.tga")[1]
local gx, gy = cx(line)
near3(gx, MU.GLYPH_X + MU.GLYPH_W / 2, "glyph x in the upper area")
near3(gy, MU.UPPER_Y + (MU.GLYPH_Y - MU.LOWER_Y) + MU.GLYPH_H / 2, "glyph y follows the area")
""")

case("rescale_reseats_in_place_and_builds_nothing")(r"""
boot({ class = "WARLOCK", state = shardState(3), height = 1440 })
local spec, host = mount("lower")
local line = texWith(host, "hud_shard_line.tga")[1]
local frames, texes, strs = #FRAMES, #TEXTURES, #FONTSTRINGS
SetScreen(1200)
fire("UI_SCALE_CHANGED")
spec.seat(RECTS.lower)
local k = K * 1200 / 1440
near3(line.w, MU.GLYPH_W * k * TN.CANVAS_W / FS.Gunsight.G.SH_W, "glyph canvas follows the scale")
local gx, gy = cx(line)
near3(gx, MU.GLYPH_X + MU.GLYPH_W / 2, "glyph x after the rescale")
near3(fsPx(textOf(host, "3")), MU.NUM_PX, "count size in image px after the rescale")
check(#FRAMES == frames and #TEXTURES == texes and #FONTSTRINGS == strs, "a rescale built regions")
spec.seat(RECTS.upper)
local _, uy = cx(line)
near3(uy, MU.UPPER_Y + (MU.GLYPH_Y - MU.LOWER_Y) + MU.GLYPH_H / 2, "seat to another rect moves it")
""")

case("combo_module_is_five_yellow_pips_and_the_count")(r"""
boot({ class = "ROGUE", combo = 4 })
local spec, host = mount("lower")
local fills = texWith(host, "\\hud_diamond.tga")
local rings = texWith(host, "glyph_hud_diamond.tga")
check(#fills == 5 and #rings == 5, "five pips: " .. #fills .. " fills and " .. #rings .. " outlines")
local k = K * FS.Layout.Scale()
local lit = 0
for i = 1, 5 do
    local f = fills[i]
    local x, y = cx(f)
    near3(x, MU.PIP_X0 + (i - 1) * MU.PIP_STEP, "pip " .. i .. " x")
    near3(y, MU.PIP_Y, "pip " .. i .. " y")
    near3(f.w, 2 * MU.PIP_R * k, "pip width is the mockup's diagonal")
    colorIs(f.vertex, MU.YELLOW, "pip " .. i .. " is yellow")
    if i <= 4 then
        near3(f.vertex[4], MU.PIP_FILL_LIT, "lit pip " .. i .. " fill alpha"); lit = lit + 1
        near3(rings[i].vertex[4], MU.PIP_STROKE_LIT, "lit pip " .. i .. " outline alpha")
    else
        near3(f.vertex[4], MU.PIP_FILL_OFF, "unlit pip fill alpha")
        near3(rings[i].vertex[4], MU.PIP_STROKE_OFF, "unlit pip outline alpha")
    end
end
check(lit == 4, "four lit pips")
local num = textOf(host, "4")
check(num, "the count 4 is not drawn")
local nx, ny = cx(num)
near3(nx, MU.COMBO_NUM_X, "count x")
near3(fsPx(num), MU.COMBO_NUM_PX, "count size")
local label = textOf(host, "COMBO POINTS")
check(label, "the label COMBO POINTS is not drawn")
local clx, cly = cx(label)
near3(clx, MU.COMBO_LABEL_X, "label x")
near3(cly, MU.COMBO_LABEL_Y - TEXT_MID * MU.LABEL_PX, "label y")
near3(ny, MU.COMBO_NUM_BASE - TEXT_MID * MU.COMBO_NUM_PX, "count centre above its baseline")
check(#texWith(host, "hud_shard") == 0, "no shard glyph in the combo module")
check(COMBO_ARGS[1] and COMBO_ARGS[1][1] == "player" and COMBO_ARGS[1][2] == "target", "GetComboPoints is asked for player and target")
""")

case("combo_module_follows_its_events_and_dims_at_zero")(r"""
boot({ class = "ROGUE", combo = 0 })
local spec, host = mount("lower")
local fills = texWith(host, "\\hud_diamond.tga")
for i = 1, 5 do near3(fills[i].vertex[4], MU.PIP_FILL_OFF, "all pips unlit at zero") end
local zero = textOf(host, "0")
check(zero, "the count 0 is drawn")
colorIs(zero.textColor, FS.Theme.COLOR_MUTED, "a zero count is muted")
for _, ev in ipairs({ { "PLAYER_COMBO_POINTS" }, { "UNIT_POWER_UPDATE", "player", "COMBO_POINTS" }, { "PLAYER_TARGET_CHANGED" } }) do
    COMBO = COMBO + 1
    fire(unpack(ev))
    check(textOf(host, tostring(COMBO)), ev[1] .. " must refresh the count to " .. COMBO)
    local lit = 0
    for _, f in ipairs(texWith(host, "\\hud_diamond.tga")) do if f.vertex[4] > 0.5 then lit = lit + 1 end end
    check(lit == COMBO, ev[1] .. ": " .. lit .. " lit pips, want " .. COMBO)
end
COMBO = 5
fire("UNIT_POWER_UPDATE", "player", "ENERGY")
check(not textOf(host, "5"), "an energy power update does not read the combo points")
fire("UNIT_POWER_UPDATE", "player", "COMBO_POINTS")
check(textOf(host, "5"), "five combo points")
colorIs(textOf(host, "5").textColor, FS.Theme.COLOR_TEXT_WHITE, "a held count is white")
""")

case("a_combo_event_the_client_refuses_is_logged_once_and_the_power_update_still_works")(r"""
boot({ class = "ROGUE", combo = 1 })
local FrameMT = getmetatable(UIParent).__index
local register = FrameMT.RegisterEvent
function FrameMT:RegisterEvent(e)
    if e == "PLAYER_COMBO_POINTS" then error("Attempt to register unknown event \"" .. e .. "\"", 2) end
    return register(self, e)
end
local spec, host = mount("lower")
check(DEGRADED["gunsightclass_event_PLAYER_COMBO_POINTS"], "the refused event is logged through the degrade path")
check(textOf(host, "1"), "the module still draws")
COMBO = 4
fire("UNIT_POWER_UPDATE", "player", "COMBO_POINTS")
check(textOf(host, "4"), "UNIT_POWER_UPDATE for the player alone updates the count")
local lit = 0
for _, f in ipairs(texWith(host, "\\hud_diamond.tga")) do if f.vertex[4] > 0.5 then lit = lit + 1 end end
check(lit == 4, "and the pips: " .. lit .. " lit")
DEGRADED["gunsightclass_event_PLAYER_COMBO_POINTS"] = nil
spec.onHide("lower"); spec.onShow("lower")
check(DEGRADED["gunsightclass_event_PLAYER_COMBO_POINTS"] == nil, "a second show does not log it again")
check(PRINTED[1] == nil, "nothing is printed to chat")
""")

case("combo_module_registers_events_only_while_shown")(r"""
boot({ class = "ROGUE", combo = 2 })
local spec, host, frame = mount("lower")
local function listening()
    local n = 0
    for _, f in ipairs(FRAMES) do
        if f.events.PLAYER_COMBO_POINTS or f.events.PLAYER_TARGET_CHANGED or f.events.UNIT_POWER_UPDATE then n = n + 1 end
    end
    return n
end
check(listening() >= 1, "listens while shown")
spec.onHide("lower")
check(listening() == 0, "no event stays registered after onHide, got " .. listening())
COMBO = 3
fire("PLAYER_COMBO_POINTS")
check(not textOf(host, "3"), "a hidden module does not repaint")
spec.onShow("lower")
check(textOf(host, "3"), "showing again repaints from the live count")
""")

case("combo_module_secret_count_goes_only_to_the_number_sink_and_hides_the_pips")(r"""
boot({ class = "ROGUE", combo = 3 })
local spec, host = mount("lower")
COMBO = SECRET
fire("PLAYER_COMBO_POINTS")
local _, txt = drawn(host)
local fed
for _, s in ipairs(txt) do if s.secretFed then fed = s end end
check(fed, "a secret count must reach a number string through SetFormattedText")
check(#texWith(host, "\\hud_diamond.tga") == 0 and #texWith(host, "glyph_hud_diamond.tga") == 0, "the pips hide when the count is secret")
COMBO = 2
fire("PLAYER_COMBO_POINTS")
check(textOf(host, "2"), "a plain count draws again")
check(#texWith(host, "\\hud_diamond.tga") == 5, "the pips come back with a plain count")
""")

case("combo_module_draws_nothing_without_the_combo_api")(r"""
boot({ class = "ROGUE", noCombo = true })
local spec, host = mount("lower")
local tex, txt = drawn(host)
check(#tex == 0 and #txt == 0, "no GetComboPoints: nothing drawn, got " .. #tex .. " textures and " .. #txt .. " strings")
""")

case("combo_module_draws_nothing_without_a_hostile_live_target_but_shards_do")(r"""
boot({ class = "ROGUE", combo = 3 })
local spec, host = mount("lower")
check(textOf(host, "3"), "a hostile target: the combo module draws")
TARGET.exists = false
fire("PLAYER_TARGET_CHANGED")
local tex, txt = drawn(host)
check(#tex == 0 and #txt == 0, "no target: nothing drawn, got " .. #tex .. " textures and " .. #txt .. " strings")
TARGET.exists, TARGET.attackable = true, false
fire("PLAYER_TARGET_CHANGED")
tex, txt = drawn(host)
check(#tex == 0 and #txt == 0, "a friendly target: nothing drawn")
TARGET.attackable, TARGET.dead = true, true
fire("PLAYER_TARGET_CHANGED")
tex, txt = drawn(host)
check(#tex == 0 and #txt == 0, "a dead target: nothing drawn")
TARGET.dead = false
fire("PLAYER_TARGET_CHANGED")
check(textOf(host, "3") and #texWith(host, "\\hud_diamond.tga") == 5, "a hostile target again: drawn")
boot({ class = "WARLOCK", state = shardState(3) })
TARGET.exists = false
local _, host2 = mount("lower")
check(textOf(host2, "3") and #texWith(host2, "hud_shard_line.tga") == 1, "shards keep showing with no target")
""")

case("druid_draws_combo_points_in_cat_form_only")(r"""
boot({ class = "DRUID", combo = 2, form = { 3, "ENERGY" } })
local spec, host = mount("lower")
check(#texWith(host, "\\hud_diamond.tga") == 5 and textOf(host, "2"), "cat form draws the pips and the count")
FORM_POWER = { 0, "MANA" }
fire("UNIT_DISPLAYPOWER", "player")
local tex, txt = drawn(host)
check(#tex == 0 and #txt == 0, "caster form draws nothing, got " .. #tex .. " textures and " .. #txt .. " strings")
FORM_POWER = { 1, "RAGE" }
fire("UPDATE_SHAPESHIFT_FORM")
tex, txt = drawn(host)
check(#tex == 0 and #txt == 0, "bear form draws nothing")
FORM_POWER = { 3, "ENERGY" }
fire("UPDATE_SHAPESHIFT_FORM")
check(#texWith(host, "\\hud_diamond.tga") == 5, "back in cat form")
""")

case("druid_with_an_unreadable_form_draws_nothing")(r"""
boot({ class = "DRUID", combo = 2, noPowerType = true })
local spec, host = mount("lower")
local tex, txt = drawn(host)
check(#tex == 0 and #txt == 0, "no UnitPowerType: nothing drawn")
""")

case("druid_with_a_secret_form_draws_nothing")(r"""
boot({ class = "DRUID", combo = 2 })
local spec, host = mount("lower")
FORM_POWER = { SECRET, SECRET }
fire("UPDATE_SHAPESHIFT_FORM")
local tex, txt = drawn(host)
check(#tex == 0 and #txt == 0, "a secret form draws nothing")
""")

case("a_class_without_a_module_draws_nothing")(r"""
boot({ class = "MAGE", combo = 3, state = shardState(4) })
local spec, host = mount("lower")
local tex, txt = drawn(host)
check(#tex == 0 and #txt == 0, "a Mage draws " .. #tex .. " textures and " .. #txt .. " strings")
check(#SUBS == 0, "a Mage never subscribes to the Hud")
""")

case("a_secret_class_token_draws_nothing")(r"""
boot({ classToken = SECRET, combo = 3, state = shardState(4) })
local spec, host = mount("lower")
local tex, txt = drawn(host)
check(#tex == 0 and #txt == 0, "a secret class token draws nothing")
""")


def static_checks() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        c, a = toc.index("Modules/CombatHud/GunsightClass.lua"), toc.index("Modules/CombatHud/GunsightAreas.lua")
        out.append(("toc_loads_class_after_areas",
                    None if c > a else f"GunsightClass.lua must load after GunsightAreas.lua (positions {a}, {c})"))
    except ValueError as e:
        out.append(("toc_loads_class_after_areas", f"{e}"))
    src = CLASS.read_text(encoding="utf-8") if CLASS.exists() else ""
    out.append(("no_em_or_en_dashes", None if not re.search("[–—]", src) else "GunsightClass.lua has an em or en dash"))
    out.append(("player_text_never_says_tape", None if not re.search(r"\"[^\"]*\btape\b[^\"]*\"", src, re.I) else "player text says tape"))
    for tex in ("hud_shard_line", "hud_shard_fill", "hud_shard_glow", "hud_shard_facet", "hud_diamond", "glyph_hud_diamond"):
        out.append((f"texture_{tex}_exists", None if (TEXTURES / f"{tex}.tga").exists() else f"{tex}.tga is missing"))
    return out


def run_case(name: str, body: str, mu: dict, tn: dict) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    g = lua.globals()
    g.LAYOUT_SRC = LAYOUT.read_text(encoding="utf-8")
    g.CONFIG_SRC = CONFIG.read_text(encoding="utf-8")
    g.GUNSIGHT_SRC = GUNSIGHT.read_text(encoding="utf-8")
    g.CLASS_SRC = CLASS.read_text(encoding="utf-8")
    g.HAS_TARGET_SRC = _load("gunsight-harness").theme_target_rule_lua()
    lua.execute("MU = " + lua_value(mu) + "\nTN = " + lua_value(tn))
    try:
        lua.execute(PRELUDE + "\n" + body)
    except LuaError as e:
        return str(e)
    return None


def main() -> int:
    mu, tn = mockup_class(), tune_numbers()
    failures = 0

    def report(name: str, err: str | None) -> None:
        nonlocal failures
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      " + err.replace("\n", "\n      "))

    if not CLASS.exists():
        print(f"FAIL  {CLASS.name} is missing")
        return 1
    for name, body in CASES:
        try:
            err = run_case(name, body, mu, tn)
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
