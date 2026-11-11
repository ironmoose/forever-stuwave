#!/usr/bin/env python3
"""Runs the real GunsightSeals.lua (the Paladin's Gunsight Class Module) and its generated PaladinArt.lua headless.

The module draws the design mockup "Paladin seal and hammer" (2026-11-10, idea 1 SLAM, hammer A): a wax seal whose colour
drains as the seal runs out, and a warhammer that fills over the Judgement cooldown and slams into the ground on a Judgement.
These checks pin:

  * the art: the committed PaladinArt.lua and the three paladin_*.tga files are exactly what the generator writes now, and
    every sprite name the module can ask for exists in the manifest;
  * the registration: one "class" module for PALADIN only, a frame named ForeverSTUwaveGunsightSeals under the host;
  * the data: state.seal (seven keys, false = no seal, nil / a secret / an unknown key = unknown), judgeAt (a new stamp is
    the bonk, ridden by the seal up at the push) and state.judged (the target's debuff); secrets are dropped, never compared;
  * the seal: the drain crops the three wax layers at the level line, the time label, the amber crack and label under 3 s,
    the no seal and unknown rings;
  * the hammer: the upright frame cropped at the fill row (cold above, filled and the seal tint below, the edge line on it),
    full and breathing when ready, the wind-up, the swing's afterimages, the planted frame with the impact (whiteout, pillar,
    rays, shockwaves, debris, cracks, shake, flash, the seal's ring), the rise frames, the cooldown label;
  * the ground rune: the target's debuff ring drains over its length (Justice 10 s), a damage seal's rune fades in 2 s;
  * reduced motion: no shake, no flash, no bob;
  * onShow subscribes and starts one OnUpdate, onHide stops both; a rescale rewrites every size;
  * the paint allocates nothing once warm;
  * under the REAL GunsightAreas.lua the host hides with no target, the module stops, and it comes back with a target.

    python3 tools/gunsightseals-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ADDON = ROOT / "forever-stuwave"
MODULE = (ADDON / "Modules/CombatHud/GunsightSeals.lua").read_text(encoding="utf-8")
ARTLUA_PATH = ADDON / "Modules/CombatHud/PaladinArt.lua"
ARTLUA = ARTLUA_PATH.read_text(encoding="utf-8")
GENERATOR = ROOT / "tools/assets/generate_paladin_seal.py"
MEDIA = ADDON / "Media/Textures"

MOCK = r"""
local Obj = {}
Obj.__index = function(t, k)
    local v = rawget(Obj, k)
    if v ~= nil then return v end
    if type(k) == "string" and k:match("^%u") then return function() end end
end
__all, __frames = {}, {}
local seq = 0
function New(kind, parent)
    seq = seq + 1
    local o = setmetatable({ kind = kind, shown = true, parent = parent, seq = seq, level = 0, writes = 0 }, Obj)
    __all[#__all + 1] = o
    return o
end
function Obj:SetPoint(p, rel, rp, x, y) self.pt = { p, rel, rp, x or 0, y or 0 }; self.writes = self.writes + 1 end
function Obj:ClearAllPoints() self.pt = nil end
function Obj:SetAllPoints(rel) self.pt = { "TOPLEFT", rel, "TOPLEFT", 0, 0 } end
function Obj:SetSize(w, h) self.w, self.h = w, h; self.sizes = (self.sizes or 0) + 1 end
function Obj:Show() self.shown = true end
function Obj:Hide() self.shown = false end
function Obj:IsShown() return self.shown end
function Obj:SetScript(n, fn) self.scripts = self.scripts or {}; self.scripts[n] = fn end
function Obj:SetTexture(p) self.tex = p end
function Obj:SetTexCoord(l, r, t, b) self.tc = { l, r, t, b } end
function Obj:SetVertexColor(r, g, b, a) self.color = { r, g, b, a or 1 } end
function Obj:SetFrameLevel(l) self.level = l end
function Obj:GetFrameLevel() return self.level end
function Obj:CreateTexture(name, layer, inh, sub) local t = New("Texture", self); t.layer = layer; t.sub = sub or 0; return t end
function CreateFrame(kind, name, parent)
    local f = New("Frame", parent); f.name = name
    __frames[#__frames + 1] = f
    return f
end
__now = 1000
__scale = 1
function GetTime() return __now end
SECRET = setmetatable({}, { __tostring = function() return "secret" end })
local Areas = { specs = {} }
function Areas.RegisterModule(id, spec) Areas.specs[#Areas.specs + 1] = { id = id, spec = spec }; return true end
SUBS = {}
STATE = nil
FS = {
    IsSecret = function(v) return v == SECRET end,
    Gunsight = { ui = function(px) return px * __scale end, Point = function(f, p, x, y) f.pt = { p, "root", "CENTER", x, y } end },
    GunsightAreas = Areas,
    HudSpells = { jd = { cooldown = 10 } },
    Hud = {
        Subscribe = function(fn) SUBS[#SUBS + 1] = fn; if STATE then fn(STATE) end; return fn end,
        Unsubscribe = function(fn) for i = #SUBS, 1, -1 do if SUBS[i] == fn then table.remove(SUBS, i) end end end,
    },
    LogDegradeOnce = function(k, m) __logged = __logged or {}; __logged[k] = m end,
}
function push(state) STATE = state; for i = 1, #SUBS do SUBS[i](state) end end
assert(loadstring(ARTLUA_SRC, "@PaladinArt.lua"))("forever-stuwave", FS)
assert(loadstring(MODULE_SRC, "@GunsightSeals.lua"))("forever-stuwave", FS)
M, Art = FS.GunsightSeals, FS.PaladinArt
SPEC = Areas.specs[1] and Areas.specs[1].spec
HOST = New("Frame")
function Build()
    local m = SPEC.build(HOST)
    SPEC.seat({ x = 0, y = 0, w = 200, h = 128 })
    SPEC.onShow("lower")
    return m
end
function P() return M.parts end
function On(t) return t.shown and t.fsOn == true end
-- the crop a sprite region shows: name, c0, c1, r0, r1 (sprite px)
function Crop(t) return t.fsName, t.fsC0, t.fsC1, t.fsR0, t.fsR1 end
-- the hammer row j as a local row of sprite `name` (upright frame)
function LocalRow(name, j) return j - Art.PIVY + Art.sprites[name][7] end
function Near(a, b, eps) return math.abs(a - b) <= (eps or 1e-6) end
function Seal(key, left, judgeAgo, judged)
    local st = { inCombat = true, seal = key == false and false or (key and { key = key, expiresAt = __now + left, duration = 30 }) }
    if judgeAgo then st.judgeAt = __now - judgeAgo end
    st.judged = judged
    return st
end
function Paint(t) __now = t or __now; M.Paint(__now) end
function Label(l)
    local o = {}
    for i = 1, 3 do if On(l[i]) then o[#o + 1] = l[i].fsName:sub(7) end end
    return table.concat(o)
end
function ColorIs(t, c, a)
    return t.color and Near(t.color[1], c[1], 1e-4) and Near(t.color[2], c[2], 1e-4) and Near(t.color[3], c[3], 1e-4)
        and (a == nil or Near(t.color[4], a, 1e-4))
end
function NoLog()
    for k, v in pairs(__logged or {}) do error("logged " .. k .. ": " .. tostring(v)) end
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("registers_the_class_module_for_paladins_only", """
    assert(SPEC and SPEC.classes[1] == "PALADIN" and #SPEC.classes == 1)
    assert(not M.frame, "nothing is built at load")
    local m = Build()
    assert(m and m.name == "ForeverSTUwaveGunsightSeals" and m.parent == HOST)
    NoLog()
""")

case("every_sprite_the_module_names_is_in_the_manifest", """
    local missing = {}
    local function walk(t)
        for _, v in pairs(t) do
            if type(v) == "table" then walk(v)
            elseif type(v) == "string" and not Art.sprites[v] then missing[#missing + 1] = v end
        end
    end
    walk(M.NAME)
    for _, n in ipairs({ "wax_crack", "column", "column_pool", "halo", "cracks_odd", "cracks_even" }) do
        if not Art.sprites[n] then missing[#missing + 1] = n end
    end
    assert(#missing == 0, "missing sprites: " .. table.concat(missing, ", "))
    assert(#Art.STAND >= 3 and Near(Art.STAND[1], 0) and Near(Art.STAND[#Art.STAND], math.pi / 2, 1e-5))
""")

case("the_seal_follows_the_hud_and_drops_what_it_cannot_read", """
    Build()
    local ids = { sor = "righteousness", sotc = "crusader", sofu = "fury", soc = "command", sol = "light", sow = "wisdom",
        soj = "justice" }
    for key, id in pairs(ids) do
        push(Seal(key, 20))
        assert(M.data.sealMode == "seal" and M.data.seal == id, key)
        assert(P().waxFull.fsName == "wax_full_" .. id, "the wax wears the seal: " .. tostring(P().waxFull.fsName))
    end
    push(Seal(false))
    assert(M.data.sealMode == "none" and not On(P().waxFull) and On(P().dashIn[1]), "false is no seal: the amber ring")
    assert(ColorIs(P().dashIn[1], M.COLORS.amber), "amber")
    push(Seal(nil))
    assert(M.data.sealMode == "unknown" and not On(P().waxFull) and ColorIs(P().dashIn[1], M.COLORS.muted), "nil is unknown")
    push({ seal = { key = SECRET, expiresAt = __now + 5, duration = 30 } })
    assert(M.data.sealMode == "unknown", "a secret key is unknown")
    push({ seal = { key = "sor", expiresAt = SECRET, duration = 30 } })
    assert(M.data.sealMode == "unknown", "a secret expiry is unknown")
    push({ seal = { key = "bogus", expiresAt = __now + 5 } })
    assert(M.data.sealMode == "unknown", "an unmapped key is unknown")
    push({ seal = { key = "sor", expiresAt = __now + 5 }, judgeAt = SECRET, judged = { key = "sotc", expiresAt = SECRET, duration = 40 } })
    assert(M.data.judgeAt == nil and M.data.debKey == nil, "secret judgement fields are dropped")
    NoLog()
""")

case("the_wax_drains_from_the_top_at_the_level_line", """
    Build()
    push(Seal("sor", 15))
    local s = Art.sprites.wax_full_righteousness
    local oy = s[7]
    -- level .5: the line is round(17 - 34 * .5) = 0 rows from the centre
    local _, _, _, r0, r1 = Crop(P().waxDrain)
    assert(r0 == 0 and r1 == oy, "drained rows above the line: " .. tostring(r1))
    _, _, _, r0, r1 = Crop(P().waxLine)
    assert(r0 == oy and r1 == oy + 1, "the line row")
    _, _, _, r0, r1 = Crop(P().waxFull)
    assert(r0 == oy + 1 and r1 == s[5], "full rows below")
    assert(Label(P().sealLabel) == "15S" and ColorIs(P().sealLabel[1], M.SEAL_COLORS.righteousness))
    assert(not On(P().waxCrack), "no crack with time to spare")
    push(Seal("sor", 30))
    assert(not On(P().waxDrain), "a fresh seal has nothing drained")
    push(Seal("sor", 2.2))
    assert(On(P().waxCrack) and ColorIs(P().sealLabel[1], M.COLORS.amber) and Label(P().sealLabel) == "3S",
        "under 3 s: the amber crack and label")
    Paint(__now + 3)
    assert(M.data.sealMode == "seal" and not On(P().waxFull) and On(P().dashIn[1]), "an expired seal reads as no seal")
    NoLog()
""")

case("the_hammer_fills_from_the_pommel_over_the_cooldown", """
    Build()
    push(Seal("sotc", 20, 15))                     -- judged 15 s ago: ready
    local cold, filled, tint, edge, outline = P().cold, P().filled, P().tint, P().edge, P().outline
    assert(not On(cold) and On(filled) and filled.fsName == "stand0_filled", "ready: filled whole")
    assert(ColorIs(tint, M.SEAL_COLORS.crusader, Art.TINT_A), "the tint mask in the seal colour")
    assert(not On(edge), "no level line when full")
    assert(not ColorIs(outline, M.COLORS.out), "the outline breathes in the seal colour when ready")
    assert(Label(P().cdLabel) == "", "no cooldown label when ready")
    assert(On(P().column) and On(P().halo), "the light and the halo while raised")
    -- 5 s into the cooldown: half full
    push(Seal("sotc", 20, 5))
    local fill = math.floor(Art.BOTTOM_ROW + 1 - (Art.BOTTOM_ROW - Art.TOP_ROW + 1) * 0.5 + 0.5)
    local _, _, _, r0, r1 = Crop(cold)
    assert(On(cold) and r0 == 0 and r1 == LocalRow("stand0_cold", fill), "cold above the fill row")
    _, _, _, r0 = Crop(filled)
    assert(r0 == LocalRow("stand0_filled", fill + 1), "filled below it")
    _, _, _, r0, r1 = Crop(edge)
    assert(On(edge) and r0 == LocalRow("stand0_mask", fill) and r1 == r0 + 1 and ColorIs(edge, {
        M.SEAL_COLORS.crusader[1] + (1 - M.SEAL_COLORS.crusader[1]) * 0.85,
        M.SEAL_COLORS.crusader[2] + (1 - M.SEAL_COLORS.crusader[2]) * 0.85,
        M.SEAL_COLORS.crusader[3] + (1 - M.SEAL_COLORS.crusader[3]) * 0.85 }), "the level line")
    assert(ColorIs(outline, M.COLORS.out), "a charging outline is plain")
    assert(Label(P().cdLabel) == "5S" and ColorIs(P().cdLabel[1], M.COLORS.muted))
    -- no seal: everything cold, no emblem, no light
    push(Seal(false, nil, 15))
    local _, _, _, r0b, r1b = Crop(cold)
    assert(On(cold) and r0b == 0 and r1b == Art.sprites.stand0_cold[5] and not On(filled) and not On(P().embLit)
        and not On(P().column), "no seal: cold, dark, unlit")
    NoLog()
""")

case("a_judgement_swings_the_hammer_into_the_ground", """
    Build()
    push(Seal("sor", 20))                          -- never judged: ready, upright
    __now = __now + 1
    push(Seal("sor", 20, 0))                       -- our Judgement lands now
    assert(M.data.judgeKey == "righteousness", "the blow rides the seal that is up")
    local function at(since) Paint(M.data.judgeAt + since) end
    at(0.1)                                        -- s = .056: the wind-up, leaning back
    local f = tonumber(P().filled.fsName:match("stand(%d+)_"))
    assert(Art.STAND[f + 1] < 0, "wound up: " .. P().filled.fsName)
    assert(not On(P().after[1].mask), "no afterimages before the swing")
    assert(On(P().column) and On(P().filled) and not On(P().cold), "the light flares; full until the blow lands")
    at(0.36)                                       -- s = .2: the swing
    assert(On(P().after[1].mask) and On(P().after[3].mask), "afterimages trail the swing")
    at(0.45)                                       -- s = .25: impact
    assert(P().cold.fsName == "stand" .. (#Art.STAND - 1) .. "_cold", "planted on its side")
    assert(On(P().whiteout), "the hammer flashes white")
    assert(On(P().pillarCore) and On(P().raysWhite) and On(P().shockA) and On(P().debris[1]), "pillar, rays, shockwave, debris")
    assert(On(P().cracksOdd) and On(P().flash), "cracks and the hit flash")
    assert(On(P().sealRing[1]), "the seal rings")
    local art = M.frame.parent and nil
    local moved = false
    for i = 1, #__frames do local fr = __frames[i]; if fr.fsSX and (fr.fsSX ~= 0 or fr.fsSY ~= 0) then moved = true end end
    assert(moved, "the module shakes")
    at(1.5)                                        -- s = .83: planted, spent
    assert(not On(P().flash) and not On(P().pillarCore) and Label(P().cdLabel) == "9S")
    assert(On(P().filled) and P().filled.fsC1 < Art.sprites[P().filled.fsName][4], "the fill starts at the pommel (left)")
    at(2.4)                                        -- s = 1.33: rising
    assert(P().cold.fsName:match("^rise%d+_coldout$"), "rising: " .. tostring(P().cold.fsName))
    assert(On(P().embDark), "the emblem stays dark while the fill is low")
    at(3)
    assert(P().cold.fsName == "stand0_cold" and On(P().column), "back upright, charging in the light")
    assert(On(P().runeRing[1]) and P().runeRing[1].color[4] < 0.5, "a damage seal's rune is fading")
    at(5)
    assert(not On(P().runeRing[1]), "and gone 2 s (slam time) after the blow")
    at(10.5)
    assert(On(P().burst[1]), "the ready ring opens")
    NoLog()
""")

case("the_ground_rune_follows_the_targets_judgement", """
    Build()
    push(Seal("sotc", 20, 30, { key = "sotc", expiresAt = __now + 30, duration = 40 }))
    assert(On(P().runeRing[1]) and On(P().runeEmb) and P().runeEmb.fsName == "rune_crusader", "the rune burns")
    local lit = 0
    for i = 1, 48 do if ColorIs(P().runeRing[i], M.SEAL_COLORS.crusader) then lit = lit + 1 end end
    assert(lit == 36, "30 of 40 s: 36 of 48 ring dots lit, got " .. lit)
    push(Seal("soj", 20, 30, { key = "soj", expiresAt = __now + 5, duration = 10 }))
    lit = 0
    for i = 1, 48 do if ColorIs(P().runeRing[i], M.SEAL_COLORS.justice) then lit = lit + 1 end end
    assert(lit == 24 and P().runeEmb.fsName == "rune_justice", "Justice drains over 10 s: " .. lit)
    push(Seal("soj", 20, 30, false))
    assert(not On(P().runeRing[1]), "no debuff, no rune")
    NoLog()
""")

case("reduced_motion_holds_the_shake_flash_and_bob", """
    ForeverSTUwaveDB = { reducedMotion = true }
    Build()
    push(Seal("sor", 20, 0))
    Paint(M.data.judgeAt + 0.45)
    assert(not On(P().flash), "no white flash")
    for i = 1, #__frames do local fr = __frames[i]; assert(not fr.fsSX or (fr.fsSX == 0 and fr.fsSY == 0), "no shake") end
    Paint(M.data.judgeAt + 20)
    local y = P().filled.fsY
    for k = 1, 20 do Paint(__now + 0.37); assert(P().filled.fsY == y, "no bob") end
    assert(not On(P().motes[1]) and not On(P().glint), "no motes, no glint")
    ForeverSTUwaveDB = nil
    NoLog()
""")

case("show_and_hide_drive_the_subscription_and_the_ticker", """
    local m = Build()
    assert(#SUBS == 1 and m.scripts.OnUpdate, "onShow subscribes and ticks")
    SPEC.onHide("lower")
    assert(#SUBS == 0 and not m.scripts.OnUpdate, "onHide stops both")
    SPEC.onShow("lower")
    assert(#SUBS == 1 and m.scripts.OnUpdate, "and they come back")
    NoLog()
""")

case("a_rescale_rewrites_every_size", """
    Build()
    push(Seal("sor", 15, 3))
    local filled = P().filled
    local w = filled.w
    __scale = 2
    SPEC.seat({ x = 0, y = 0, w = 200, h = 128 })
    assert(Near(filled.w, w * 2), "the hammer doubles with the scale: " .. tostring(filled.w) .. " vs " .. tostring(w))
    assert(Near(P().ground.w, 52 * 1.25 * 2), "a flat region too")
    NoLog()
""")

case("the_paint_allocates_nothing_once_warm", """
    Build()
    push(Seal("sotc", 20, 0, { key = "sotc", expiresAt = __now + 40, duration = 40 }))
    local t0 = __now
    -- the mock's setters must not allocate either
    for _, o in ipairs(__all) do
        o.SetPoint = function(self, p, rel, rp, x, y) self.px, self.py = x, y end
        o.SetTexCoord = function(self, l, r, t, b) self.tl = l end
        o.SetVertexColor = function(self, r, g, b, a) self.ca = a end
    end
    if jit then jit.off() end
    -- warm every path: the whole slam, the rise, charging, ready
    for i = 0, 400 do Paint(t0 + i * 0.033) end
    collectgarbage("collect")
    collectgarbage("stop")
    -- ten passes over the whole cycle (4010 paints): a per paint allocation of even 8 bytes would be over 30 KB; the
    -- interpreter's own one off growth (under 1 KB, the same at 100 or 2000 calls) is not the paint's
    local before = collectgarbage("count")
    for pass = 1, 10 do
        for i = 0, 400 do Paint(t0 + i * 0.033) end
    end
    local grew = collectgarbage("count") - before
    collectgarbage("restart")
    assert(grew < 2, "the paint allocated " .. grew .. " KB over 4010 paints")
    NoLog()
""")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


REAL_CASE = r"""
STRICT_EVENTS = false
resetKnownEvents()
resetWorld()
SetScreen(1440)
ForeverSTUwaveDB = nil
FS.IsSecret = function(v) return v == SECRET end
stubTheme_()
stubHud_()
FS.HudSpells = { jd = { cooldown = 10 } }
assert(loadstring(HAS_TARGET_SRC, "@Theme.lua"))()
loadAddonFile(LAYOUT_SRC, "Core/Layout.lua")
loadAddonFile(CONFIG_SRC, "Core/Config.lua")
loadAddonFile(FRAMEHELPERS_SRC, "Core/FrameHelpers.lua")
loadAddonFile(GUNSIGHT_SRC, "Modules/CombatHud/Gunsight.lua")
TARGET = { exists = true }
UnitExists = function(u) if u == "player" then return true end return u == "target" and TARGET.exists end
loadAddonFile(AREAS_SRC, "Modules/CombatHud/GunsightAreas.lua")
UnitClass = function() return "Paladin", "PALADIN" end
loadAddonFile(ARTLUA_SRC, "Modules/CombatHud/PaladinArt.lua")
loadAddonFile(MODULE_SRC, "Modules/CombatHud/GunsightSeals.lua")
push({ seal = { key = "sor", expiresAt = GetTime() + 20, duration = 30 }, judgeAt = GetTime() - 4 })
fire("ADDON_LOADED", "forever-stuwave")
fire("PLAYER_LOGIN")

local host = FS.GunsightAreas.Host("lower")
check(host, "the real areas hand out a lower host")
check(isVisible(host), "a target shows the host")
local G = FS.GunsightSeals
check(G.frame and isVisible(G.frame), "the module is built and drawn under the host")
check(onUpdateFrames() == 1, "ticking: " .. onUpdateFrames())
check(isVisible(G.parts.cold), "the hammer is drawn")
TARGET.exists = false
fire("PLAYER_TARGET_CHANGED")
check(not isVisible(host) and not isVisible(G.frame) and not isVisible(G.parts.cold) and not isVisible(G.parts.waxFull),
    "no target hides the host and everything under it")
check(onUpdateFrames() == 0, "and stops the OnUpdate")
TARGET.exists = true
fire("PLAYER_TARGET_CHANGED")
check(isVisible(host) and isVisible(G.parts.cold), "a target brings it back")
check(onUpdateFrames() == 1, "and the ticker with it")
for k, v in pairs(DEGRADED) do error("degraded " .. k .. ": " .. tostring(v)) end
"""


def run_real_case() -> str | None:
    cls = _load("gunsightclass-harness")
    gs = _load("gunsight-harness")
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(cls.MOCK)
    g = lua.globals()
    g.LAYOUT_SRC = (ADDON / "Core/Layout.lua").read_text(encoding="utf-8")
    g.CONFIG_SRC = (ADDON / "Core/Config.lua").read_text(encoding="utf-8")
    g.FRAMEHELPERS_SRC = (ADDON / "Core/FrameHelpers.lua").read_text(encoding="utf-8")
    g.GUNSIGHT_SRC = (ADDON / "Modules/CombatHud/Gunsight.lua").read_text(encoding="utf-8")
    g.AREAS_SRC = (ADDON / "Modules/CombatHud/GunsightAreas.lua").read_text(encoding="utf-8")
    g.ARTLUA_SRC, g.MODULE_SRC = ARTLUA, MODULE
    g.HAS_TARGET_SRC = gs.theme_target_rule_lua()
    try:
        lua.execute(REAL_CASE)
    except LuaError as e:
        return str(e)
    return None


def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    g = rt.globals()
    g.ARTLUA_SRC, g.MODULE_SRC = ARTLUA, MODULE
    try:
        rt.execute(MOCK)
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


def static_checks() -> list[str]:
    """The committed art is exactly what the generator writes now."""
    errs = []
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, FS_ASSET_OUTPUT_DIR=tmp, FS_ART_LUA_OUTPUT=str(Path(tmp) / "PaladinArt.lua"))
        run = subprocess.run([sys.executable, str(GENERATOR)], env=env, capture_output=True, text=True)
        if run.returncode != 0:
            return [f"the generator failed: {run.stderr.strip()[-400:]}"]
        if (Path(tmp) / "PaladinArt.lua").read_text(encoding="utf-8") != ARTLUA:
            errs.append("PaladinArt.lua differs from the generator's (run tools/assets/generate_paladin_seal.py)")
        for name in ("paladin_seal", "paladin_hammer", "paladin_fx"):
            mine = MEDIA / f"{name}.tga"
            if not mine.exists():
                errs.append(f"missing texture {name}.tga")
            elif mine.read_bytes() != (Path(tmp) / f"{name}.tga").read_bytes():
                errs.append(f"{name}.tga differs from the generator's")
    toc = (ADDON / "forever-stuwave.toc").read_text(encoding="utf-8").splitlines()
    toc = [line.strip() for line in toc]
    art, mod = "Modules/CombatHud/PaladinArt.lua", "Modules/CombatHud/GunsightSeals.lua"
    if art not in toc or mod not in toc or toc.index(art) > toc.index(mod):
        errs.append("the toc must load PaladinArt.lua before GunsightSeals.lua")
    return errs


def main() -> int:
    failures = 0
    for err in static_checks():
        failures += 1
        print(f"FAIL  static: {err}")
    for name, body in CASES:
        err = run_case(body)
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}: {err}")
    err = run_real_case()
    name = "under_the_real_areas_the_host_follows_the_target_and_the_module_stops_with_it"
    if err is None:
        print(f"ok    {name}")
    else:
        failures += 1
        print(f"FAIL  {name}: {err}")
    total = len(CASES) + 1
    print(f"{total - min(failures, total)}/{total} checks passed")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
