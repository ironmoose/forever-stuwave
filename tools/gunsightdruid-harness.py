#!/usr/bin/env python3
"""Runs the real GunsightDruid.lua (the Druid's Gunsight Class Module), DruidState.lua and the generated DruidArt.lua headless.

The module draws the design "Druid Gunsight Module: Wildshape Eyes" (2026-11-16): owl, slit, angry and leaf eyes that follow the
form, one gauge under them (Eclipse moons, five claw gashes and the energy bar, the rage bar and Lacerate pips, two heal over time
lanes) and a cue word. These checks pin:

  * the art: the committed DruidArt.lua and the eight druid_*.tga files are exactly what the generator writes now, every sprite
    name the module can ask for is in the manifest, the toc loads art, state, then module after the generic class module;
  * the registration: one "class" module for DRUID only; the generic GunsightClass.lua no longer lists DRUID;
  * the form: UnitPowerType ENERGY is Cat, RAGE is Bear, a travel form id is Travel, caster is Moon on a hostile target and
    Tree on a friendly one, a secret answer is caster;
  * the Eclipse ledger (Wrath +2, Starfire -1, cap 4, 15 s, locked under level 30, unknown after a reload in combat), the cue words;
  * the Cat: the gashes and the five point flare are bars fed the count (a secret one reaches only SetValue), FINISH / SHIFT only
    from plain reads, the number only through SetFormattedText, the chip's engine timer or its ledger fallback, the spend streak;
  * the Bear: the rage bar, the cue priority, the Lacerate ledger (5 stacks, 15 s, reset on another target), the pips;
  * the Restoration lanes: our HoTs by target name, the cue order, Swiftmend, the bloom flash;
  * every value secret at once (power, level, name, cooldown flags, form) draws without an error or a log line;
  * the shift (eyes shut, flash, sparks), reduced motion (no blink, flash, sparks, pulses), a rescale;
  * onShow subscribes and starts one OnUpdate and the power events, onHide stops them;
  * the paint allocates nothing once warm, in every form;
  * under the REAL GunsightAreas.lua the host hides with no target, the module stops, and it comes back with a target.

    python3 tools/gunsightdruid-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import os
import re
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
CH = ADDON / "Modules/CombatHud"
MODULE = (CH / "GunsightDruid.lua").read_text(encoding="utf-8")
STATE = (CH / "DruidState.lua").read_text(encoding="utf-8")
ARTLUA_PATH = CH / "DruidArt.lua"
ARTLUA = ARTLUA_PATH.read_text(encoding="utf-8")
GENERATOR = ROOT / "tools/assets/generate_druid_gunsight.py"
MEDIA = ADDON / "Media/Textures"
TEXTURES = ["druid_gunsight", "druid_slash_lit", "druid_slash_flare", "druid_energy_fill", "druid_rage_fill", "druid_chip_sp",
            "druid_chip_pb", "druid_chip_sm"]

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
    local o = setmetatable({ kind = kind, shown = true, parent = parent, seq = seq, level = 0, alpha = 1 }, Obj)
    __all[#__all + 1] = o
    return o
end
function Obj:SetPoint(p, rel, rp, x, y) self.pt = { p, rel, rp, x or 0, y or 0 }; self.px, self.py = x, y end
function Obj:ClearAllPoints() self.pt = nil end
function Obj:SetAllPoints(rel) self.pt = { "TOPLEFT", rel, "TOPLEFT", 0, 0 } end
function Obj:SetSize(w, h) self.w, self.h = w, h; self.sizes = (self.sizes or 0) + 1 end
function Obj:Show() self.shown = true end
function Obj:Hide() self.shown = false end
function Obj:IsShown() return self.shown end
function Obj:SetScript(n, fn) self.scripts = self.scripts or {}; self.scripts[n] = fn end
function Obj:SetTexture(p) self.tex = p end
function Obj:SetTexCoord(l, r, t, b) self.tc = { l, r, t, b }; self.flipped = l > r end
function Obj:SetVertexColor(r, g, b, a) self.color = { r, g, b, a or 1 } end
function Obj:SetFrameLevel(l) self.level = l end
function Obj:GetFrameLevel() return self.level end
function Obj:SetAlpha(a) self.alpha = a end
function Obj:CreateTexture(name, layer, inh, sub) local t = New("Texture", self); t.layer = layer; t.sub = sub or 0; return t end
function Obj:CreateFontString(name, layer) local t = New("FontString", self); t.layer = layer; return t end
function Obj:SetText(s) self.text = s end
function Obj:SetFormattedText(fmt, v)
    if v == SECRET then self.text = "<secret>"; self.secretText = true else self.text = string.format(fmt, v); self.secretText = false end
end
function Obj:SetTextColor(r, g, b, a) self.tcolor = { r, g, b, a } end
function Obj:SetStatusBarTexture(p) self.tex = p end
function Obj:SetMinMaxValues(lo, hi) self.lo, self.hi = lo, hi end
function Obj:SetValue(v) self.value = v; self.timer = nil end
function Obj:SetTimerDuration(obj, interp, dir) if NO_TIMER then error("no timer") end self.timer = obj; return true end
function Obj:RegisterEvent(e) self.events = self.events or {}; self.events[e] = true end
function Obj:RegisterUnitEvent(e, u) self.events = self.events or {}; self.events[e] = u end
function Obj:UnregisterEvent(e) if self.events then self.events[e] = nil end end
function CreateFrame(kind, name, parent)
    local f = New(kind, parent); f.name = name
    __frames[#__frames + 1] = f
    return f
end
__now = 1000
__scale = 1
function GetTime() return __now end
SECRET = setmetatable({}, { __tostring = function() return "secret" end })
Enum = { StatusBarTimerDirection = { ElapsedTime = 1 }, StatusBarInterpolation = { Immediate = 0 },
         PowerType = { Rage = 1, Energy = 3, ComboPoints = 4 } }
function fire(event, ...)
    for _, o in ipairs(__all) do
        if o.events and o.events[event] and o.scripts and o.scripts.OnEvent then o.scripts.OnEvent(o, event, ...) end
    end
end
function vis(o)
    while o do
        if not o.shown then return false end
        o = o.parent
    end
    return true
end
local Areas = { specs = {} }
function Areas.RegisterModule(id, spec) Areas.specs[#Areas.specs + 1] = { id = id, spec = spec }; return true end

-- the world the Druid is in
W = { powerType = { 0, "MANA" }, formId = nil, level = 60, name = "Boar", exists = true, canAttack = true, canAssist = false,
      power = { [1] = 0, [3] = 100, [4] = 0 }, powerMax = { [1] = 100, [3] = 100, [4] = 5 }, combat = false,
      spells = {}, known = {}, cd = {}, secretPower = false, secretName = false, secretLevel = false, secretCd = false,
      secretForm = false, spellById = { [5176] = "Wrath", [2912] = "Starfire", [774] = "Rejuvenation", [8936] = "Regrowth",
      [18562] = "Swiftmend", [33745] = "Lacerate", [22568] = "Ferocious Bite", [1079] = "Rip", [9999] = "Primal Bite",
      [8888] = "Shifting Power", [1] = "Auto Attack" } }
function UnitPowerType(u) if W.secretForm then return SECRET, SECRET end return W.powerType[1], W.powerType[2] end
function GetShapeshiftFormID() if W.secretForm then return SECRET end return W.formId end
function UnitName(u) if W.secretName then return SECRET end return W.name end
function UnitLevel(u) if W.secretLevel then return SECRET end return W.level end
function UnitExists(u) return W.exists end
function UnitCanAttack() return W.canAttack end
function UnitCanAssist() return W.canAssist end
function InCombatLockdown() return W.combat end
function UnitPower(u, t) if W.secretPower then return SECRET end return W.power[t] end
function UnitPowerMax(u, t) return W.powerMax[t] end
C_Spell = {
    GetSpellName = function(id) return W.spellById[id] end,
    GetSpellCooldown = function(name)
        if W.secretCd then return { isActive = SECRET, isOnGCD = SECRET } end
        local c = W.cd[name]
        return { isActive = c == true, isOnGCD = false }
    end,
    GetSpellCooldownDuration = function(name) return { duration = name } end,
}
SUBS = {}
FS = {
    IsSecret = function(v) return v == SECRET end,
    Gunsight = { ui = function(px) return px * __scale end, Point = function(f, p, x, y) f.pt = { p, "root", "CENTER", x, y } end },
    GunsightAreas = Areas,
    Theme = { ApplyMono = function(fs, size, color) fs.size = size; fs.tcolor = color; fs.monoSet = true end },
    LogDegradeOnce = function(k, m) __logged = __logged or {}; __logged[k] = m end,
    FrameHelpers = {
        RegisterEvent = function(f, e, unit) f.events = f.events or {}; f.events[e] = unit or true; return true end,
        ResolveSpell = function(name) for id, n in pairs(W.spellById) do if n == name then return id end end return nil end,
        IsKnownSpellId = function(id) local n = W.spellById[id]; return W.known[n] == true end,
    },
}
assert(loadstring(ARTLUA_SRC, "@DruidArt.lua"))("forever-stuwave", FS)
assert(loadstring(STATE_SRC, "@DruidState.lua"))("forever-stuwave", FS)
assert(loadstring(MODULE_SRC, "@GunsightDruid.lua"))("forever-stuwave", FS)
M, Art, St = FS.GunsightDruid, FS.DruidArt, FS.DruidState
SPEC = Areas.specs[1] and Areas.specs[1].spec
HOST = New("Frame")
function Build()
    local m = SPEC.build(HOST)
    SPEC.seat({ x = 0, y = 0, w = 200, h = 128 })
    SPEC.onShow("lower")
    return m
end
function P() return M.parts end
function Paint(t) __now = t or __now; M.Paint(__now) end
function Cast(name, t)
    __now = t or __now
    local id
    for i, n in pairs(W.spellById) do if n == name then id = i end end
    fire("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", id)
end
function Near(a, b, eps) return math.abs(a - b) <= (eps or 1e-6) end
function NoLog() for k, v in pairs(__logged or {}) do error("logged " .. k .. ": " .. tostring(v)) end end
function Cue() M.Paint(__now); return M.cue.word, M.cue.hot end
function Refresh() fire("UPDATE_SHAPESHIFT_FORM"); end
function Form(kind)
    if kind == "cat" then W.powerType = { 3, "ENERGY" }; W.formId = 1
    elseif kind == "bear" then W.powerType = { 1, "RAGE" }; W.formId = 5
    elseif kind == "travel" then W.powerType = { 0, "MANA" }; W.formId = 3
    else W.powerType = { 0, "MANA" }; W.formId = nil end
    fire("UPDATE_SHAPESHIFT_FORM")
    fire("UNIT_DISPLAYPOWER", "player")
end
function Start(kind)
    Build()
    Form(kind or "caster")
    M.Paint(__now)
end
function Lit(list, key) local n = 0 for _, m in ipairs(list) do if m[key] and m[key].fsOn then n = n + 1 end end return n end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("registers_the_class_module_for_druids_only", """
    assert(SPEC and SPEC.classes[1] == "DRUID" and #SPEC.classes == 1)
    assert(not M.frame, "nothing is built at load")
    local m = Build()
    assert(m and m.name == "ForeverSTUwaveGunsightDruid" and m.parent == HOST)
    NoLog()
""")

case("every_sprite_the_module_names_is_in_the_manifest", """
    Build()
    local missing = {}
    local function want(n) if not Art.sprites[n] then missing[#missing + 1] = tostring(n) end end
    for _, f in ipairs({ "moon", "cat", "bear", "tree" }) do
        for _, v in pairs(M.NAME.eye[f]) do want(v) end
        want(M.NAME.glyph[f])
    end
    for _, n in ipairs({ "ivy", "ivy_buds", "moon_dark", "moon_lit", "moon_dotted", "moon_glow", "halo", "slash_dark", "track_energy",
        "track_rage", "track_lane", "track_drain", "pip_dark", "pip_lit", "icon_rejuv", "icon_regrow", "letter_L", "letter_B", "letter_M",
        "chip_ring", "chip_sp", "chip_pb", "chip_sm" }) do want(n) end
    assert(#missing == 0, "missing sprites: " .. table.concat(missing, ", "))
    local seen = {}
    for _, name in ipairs({ "druid_slash_lit", "druid_slash_flare", "druid_energy_fill", "druid_rage_fill", "druid_chip_sp",
        "druid_chip_pb", "druid_chip_sm" }) do assert(Art.FILES[name], name) end
    -- the geometry the module needs
    for _, k in ipairs({ "W", "H", "EYE_Y", "EYE_L", "EYE_R", "MOON_X", "SLASH_X", "ENERGY_X", "RAGE_X", "LANE_X", "FILL_W", "FILL_BOX_W" }) do
        assert(type(Art.GEOM[k]) == "number", k)
    end
    NoLog()
""")

case("the_form_picks_the_look", """
    Start("caster")
    assert(M.data.kind == "moon", "a caster on a hostile target is the moon")
    W.canAttack, W.canAssist = false, true
    fire("PLAYER_TARGET_CHANGED")
    assert(M.data.kind == "tree", "a friend in caster form is the tree: " .. M.data.kind)
    Form("cat")
    assert(M.data.kind == "cat", "energy is the cat, friend or not")
    Form("bear")
    assert(M.data.kind == "bear")
    Form("travel")
    assert(M.data.kind == "travel")
    W.canAttack, W.canAssist = true, false
    Form("caster")
    assert(M.data.kind == "moon")
    W.secretForm = true
    Refresh()
    assert(M.data.kind == "moon", "a secret form answer is the caster")
    W.exists = true; W.canAttack = SECRET
    W.secretForm = false
    Refresh()
    assert(M.data.kind == "moon", "a secret attackable answer is not a friend")
    NoLog()
""")

case("the_eclipse_ledger_and_the_moons", """
    Start("caster")
    local w, hot = Cue()
    assert(w == "WRATH" and not hot, "no charges: WRATH, " .. w)
    assert(Lit(P().moon, "lit") == 0)
    Cast("Wrath", 1000)
    Paint(1000.5)
    w, hot = Cue()
    assert(w == "STARFIRE" and hot, "banked: STARFIRE and the eyes go hot")
    assert(Lit(P().moon, "lit") == 2, "Wrath banks two moons")
    assert(P().drainBody.fsOn and P().drainBody.fsW > 0 and P().drainSecs.text == "~15s" or P().drainSecs.text == "~14s", "the drain and its seconds: " .. tostring(P().drainSecs.text))
    Cast("Starfire", 1001)
    Paint(1001.7)
    assert(Lit(P().moon, "lit") == 1, "Starfire spends one")
    Cast("Wrath", 1002); Cast("Wrath", 1003); Cast("Wrath", 1004)
    Paint(1004.1)
    assert(Lit(P().moon, "lit") == 4, "the cap is four")
    Paint(1004 + 14); local _, ch = St.Eclipse(__now)
    assert(ch == 4, "still banked at 14 s")
    Paint(1004 + 16)
    w = Cue()
    assert(w == "WRATH" and Lit(P().moon, "lit") == 0, "gone 15 s after the last grant")
    -- amber under 3 s
    Cast("Wrath", 1100); Paint(1100 + 13)
    assert(P().drainSecs.tcolor[1] > 0.9 and P().drainSecs.tcolor[3] < 0.4, "the last seconds are amber")
    -- below level 30 the sockets are dotted
    W.level = 20; Refresh(); Paint(1200)
    w = Cue()
    assert(w == "ECLIPSE L30" and P().moon[1].dotted.fsOn and not P().moon[1].dark.fsOn, "locked under the Eclipse level")
    NoLog()
""")

case("a_reload_in_combat_leaves_the_moons_unknown_until_a_cast", """
    W.combat = true
    Start("caster")
    local w = Cue()
    assert(w == "?" and P().moon[1].dark.fsOn and Lit(P().moon, "lit") == 0, "unknown right after a reload in combat")
    Cast("Wrath", 1005)
    w = Cue()
    assert(w == "STARFIRE", "a cast tells the truth")
    NoLog()
""")

case("the_cat_gashes_and_the_flare_are_fed_the_count", """
    Start("cat")
    assert(vis(P().slash[1]) and P().slashBar[1].shown and P().flareBar[5].shown)
    for i = 1, 5 do
        assert(P().slashBar[i].lo == i - 1 and P().slashBar[i].hi == i, "gash " .. i .. " is a bar from " .. (i - 1) .. " to " .. i)
        assert(P().flareBar[i].lo == 4 and P().flareBar[i].hi == 5, "the flare is full only at five")
    end
    W.power[4] = 3; W.power[3] = 62
    fire("UNIT_POWER_FREQUENT", "player", "COMBO_POINTS")
    for i = 1, 5 do assert(P().slashBar[i].value == 3 and P().flareBar[i].value == 3) end
    assert(P().energyBar.value == 62 and P().energyNum.text == "62", "the energy bar and its number")
    assert(Near(P().energyBar.hi, 100 * Art.GEOM.FILL_BOX_W / Art.GEOM.FILL_W), "the fill's maximum is scaled to the art")
    local w = Cue()
    assert(w == "CAT", "three points: nothing to do")
    W.power[4] = 5
    fire("UNIT_POWER_FREQUENT", "player")
    w = Cue()
    assert(w == "FINISH" and M.cue.hot, "five points: FINISH and hot eyes")
    NoLog()
""")

case("a_secret_count_reaches_only_the_bars", """
    Start("cat")
    W.secretPower = true
    fire("UNIT_POWER_FREQUENT", "player")
    for i = 1, 5 do assert(P().slashBar[i].value == SECRET and P().flareBar[i].value == SECRET, "the engine is handed the secret") end
    assert(P().energyBar.value == SECRET and P().energyNum.secretText, "the number goes through SetFormattedText")
    assert(M.data.combo == nil and M.data.energyNum == nil)
    local w, hot = Cue()
    assert(w == "CAT" and not hot, "no word from a count nobody can read")
    Paint(1010)
    NoLog()
""")

case("shift_needs_a_plain_low_energy_and_a_ready_chip", """
    W.known["Shifting Power"] = true
    W.cd["Shifting Power"] = false
    Start("cat")
    W.power[4] = 1; W.power[3] = 80
    fire("UNIT_POWER_FREQUENT", "player")
    local w = Cue()
    assert(w == "CAT" and P().chipSp.status == "ready", "ready at high energy: still CAT")
    W.power[3] = 30
    fire("UNIT_POWER_FREQUENT", "player")
    w = Cue()
    assert(w == "SHIFT" and M.cue.hot, "ready and under the notch: SHIFT")
    W.cd["Shifting Power"] = true
    fire("SPELL_UPDATE_COOLDOWN")
    w = Cue()
    assert(w == "CAT" and P().chipSp.status == "cool", "cooling")
    assert(P().chipSp.bar.timer ~= nil, "the engine's duration object drives the fill")
    -- no timer API: a ledger fraction
    NO_TIMER = true
    P().chipSp.status = nil
    fire("SPELL_UPDATE_COOLDOWN")
    Cast("Shifting Power", 1000)
    Paint(1004)
    assert(P().chipSp.bar.value and Near(P().chipSp.bar.value, 0.5, 0.06), "a ledger fraction of the 8 s cooldown: " .. tostring(P().chipSp.bar.value))
    NO_TIMER = false
    W.known["Shifting Power"] = false
    fire("SPELL_UPDATE_COOLDOWN")
    assert(P().chipSp.status == "none", "not learned")
    NoLog()
""")

case("a_finisher_throws_the_streak", """
    Start("cat")
    Cast("Rip", 1000)
    Paint(1000.2)
    local n = 0
    for _, d in ipairs(P().streak) do if d.fsOn then n = n + 1 end end
    assert(n > 3, "the rake streak is drawn: " .. n)
    Paint(1001)
    n = 0
    for _, d in ipairs(P().streak) do if d.fsOn then n = n + 1 end end
    assert(n == 0, "and gone")
    NoLog()
""")

case("the_bear_rage_bar_ticks_and_cue_priority", """
    W.known["Primal Bite"] = true
    W.cd["Primal Bite"] = true
    Start("bear")
    W.power[1] = 40
    fire("UNIT_POWER_FREQUENT", "player")
    assert(P().rageBar.value == 40 and P().rageNum.text == "40")
    for i = 1, 3 do assert(P().rageTicks[i].fsOn and P().rageMarks[i].fsOn and P().letters[i].fsOn) end
    local w = Cue()
    assert(w == "LACERATE" and not M.cue.hot, "no stacks yet: build them, calmly")
    for i = 1, 5 do Cast("Lacerate", 1000 + i) end
    Paint(1006)
    assert(Lit(P().pipLit and { { l = P().pipLit[1] }, { l = P().pipLit[2] }, { l = P().pipLit[3] }, { l = P().pipLit[4] }, { l = P().pipLit[5] } }, "l") == 5, "five pips")
    w = Cue()
    assert(w == "BEAR", "five fresh stacks, Primal Bite cooling: BEAR")
    W.cd["Primal Bite"] = false
    fire("SPELL_UPDATE_COOLDOWN")
    w = Cue()
    assert(w == "BITE" and M.cue.hot, "Primal Bite ready: BITE")
    Paint(1000 + 5 + 13)
    w = Cue()
    assert(w == "LACERATE" and M.cue.hot and M.cue.blink, "five stacks about to fall: LACERATE beats BITE")
    Paint(1005 + 16)
    local s = St.Lacerate(__now)
    assert(s == 0, "the stacks fall after 15 s")
    -- another target: the ledger does not follow
    Cast("Lacerate", 1100); Cast("Lacerate", 1101)
    assert(St.Lacerate(1101.5) == 2)
    W.name = "Wolf"
    assert(St.Lacerate(1101.5) == 0, "another mob has its own stacks")
    NoLog()
""")

case("the_rage_number_is_plain_only_for_the_letters", """
    Start("bear")
    W.power[1] = 18
    fire("UNIT_POWER_FREQUENT", "player")
    Paint(1000)
    assert(P().letters[1].color[1] > 0.9, "Lacerate is affordable: its letter is bright")
    assert(P().letters[3].color[1] < 0.7, "the Maul pool is not: its letter is muted")
    W.secretPower = true
    fire("UNIT_POWER_FREQUENT", "player")
    Paint(1001)
    assert(M.data.rageNum == nil and P().rageBar.value == SECRET)
    NoLog()
""")

case("the_restoration_lanes_follow_our_own_hots_on_the_target", """
    W.canAttack, W.canAssist, W.name = false, true, "Tank"
    W.known["Swiftmend"] = true
    W.cd["Swiftmend"] = false
    Start("caster")
    assert(M.data.kind == "tree")
    local w = Cue()
    assert(w == "REJUV" and M.cue.hot, "nothing up: put Rejuvenation on")
    Cast("Rejuvenation", 1000)
    Paint(1001)
    w = Cue()
    assert(w == "REGROWTH", "Regrowth next")
    assert(P().lane[1].body.fsOn and P().lane[1].secs.text == "~11s", "the first lane drains: " .. tostring(P().lane[1].secs.text))
    assert(not P().lane[2].body.fsOn)
    Cast("Regrowth", 1002)
    fire("SPELL_UPDATE_COOLDOWN")
    Paint(1003)
    w = Cue()
    assert(w == "SWIFTMEND" and M.cue.hot and P().chipSm.status == "ready", "both up and Swiftmend ready")
    W.name = "Healer"
    Paint(1004)
    assert(not P().lane[1].body.fsOn, "another friend has none of ours")
    W.name = "Tank"
    -- the full time: it blooms
    Paint(1000 + 12.1); St.Tick(__now); Paint(__now + 0.01)
    assert(P().bloom.fsOn, "a HoT that ran out blooms")
    Paint(__now + 1)
    assert(not P().bloom.fsOn)
    NoLog()
""")

case("every_value_secret_at_once_draws_without_an_error", """
    W.secretPower, W.secretName, W.secretLevel, W.secretCd, W.secretForm = true, true, true, true, true
    W.canAttack, W.canAssist = SECRET, SECRET
    for _, k in ipairs({ "caster", "cat", "bear", "travel" }) do
        Start(k)
        for i = 0, 30 do Paint(1000 + i * 0.1) end
        fire("UNIT_POWER_FREQUENT", "player")
        fire("SPELL_UPDATE_COOLDOWN")
        Paint(1040)
    end
    NoLog()
""")

case("travel_has_no_gauge", """
    Start("travel")
    Paint(1005)
    local w = Cue()
    assert(w == "TRAVEL" and not M.cue.hot)
    assert(not P().moon[1].dark.fsOn and not P().slash[1].fsOn and not P().rageTrack.fsOn and P().travelLine.fsOn)
    assert(P().eye[1].fsName == "eye_moon_half", "the owl eyes are half shut")
    NoLog()
""")

case("the_form_switch_shuts_the_eyes_flashes_and_sparks", """
    Start("caster")
    Paint(1002)
    assert(P().eye[1].fsName == "eye_moon_open" or P().eye[1].fsName == "eye_moon_half")
    __now = 1010
    Form("cat")
    Paint(1010.05)
    assert(P().eye[1].fsName == "eye_cat_shut", "shut while the form changes: " .. tostring(P().eye[1].fsName))
    assert(P().flash[1].fsOn and P().sparks[1].fsOn, "the flash and the ring of sparks")
    Paint(1010.2)
    assert(P().eye[1].fsName == "eye_cat_half")
    Paint(1010.4)
    assert(P().eye[1].fsName:match("eye_cat_") and not P().flash[1].fsOn and not P().sparks[1].fsOn, "then open as the new form")
    assert(P().eye[2].flipped and not P().eye[1].flipped, "the right eye is the left one mirrored")
    NoLog()
""")

case("reduced_motion_holds_still", """
    ForeverSTUwaveDB = { reducedMotion = true }
    Start("cat")
    Form("cat")
    -- a blink at 4.35 s of the 4.6 s cycle would close the eyes; the clock here lands in it
    for t = 0, 4.6, 0.05 do
        Paint(1000 - 1.3 + t)
        assert(P().eye[1].fsName ~= "eye_cat_shut" and P().eye[1].fsName ~= "eye_cat_half", "no blink at " .. t)
    end
    __now = 2000
    Form("cat")
    Paint(2000.05)
    assert(not P().flash[1].fsOn and not P().sparks[1].fsOn, "no flash or sparks on the shift")
    Cast("Rip", 2010); Paint(2010.2)
    for _, d in ipairs(P().streak) do assert(not d.fsOn, "no streak") end
    Start("caster")
    Cast("Wrath", 2020); Cast("Starfire", 2020.1)
    Paint(2020.2)
    for _, d in ipairs(P().moonSparks) do assert(not d.fsOn, "no scatter") end
    ForeverSTUwaveDB = nil
    NoLog()
""")

case("a_rescale_rewrites_every_size", """
    Start("cat")
    local sizes = P().eye[1].w
    __scale = 2
    SPEC.seat({ x = 0, y = 0, w = 200, h = 128 })
    assert(P().eye[1].w == sizes * 2, "the eye was resized: " .. tostring(P().eye[1].w) .. " vs " .. tostring(sizes))
    assert(P().energyBar.w == M.C.SPX * 2 * Art.GEOM.FILL_BOX_W, "the bars follow")
    NoLog()
""")

case("onshow_subscribes_and_onhide_stops_everything", """
    Build()
    assert(M.frame.scripts.OnUpdate and M.frame.scripts.OnEvent and M.frame.events.UNIT_POWER_FREQUENT, "shown: the ticker and the power events")
    SPEC.onHide("lower")
    assert(not M.frame.scripts.OnUpdate and not M.frame.scripts.OnEvent and not M.frame.events.UNIT_POWER_FREQUENT, "hidden: all of it stopped")
    -- the ledger keeps listening while hidden
    Cast("Wrath", 1000)
    SPEC.onShow("lower")
    Paint(1001)
    assert(M.cue.word == "STARFIRE", "a cast while hidden is not lost")
    NoLog()
""")

case("the_paint_allocates_nothing_once_warm", """
    local function run(kind)
        Start(kind)
        for _, o in ipairs(__all) do
            o.SetPoint = function(self, p, rel, rp, x, y) self.px, self.py = x, y end
            o.SetTexCoord = function(self, l, r, t, b) self.tl = l end
            o.SetVertexColor = function(self, r, g, b, a) self.ca = a end
            o.SetText = function() end
            o.SetFormattedText = function() end
            o.SetTextColor = function() end
        end
        if jit then jit.off() end
        local t0 = 3000
        local function cycle()
            for i = 0, 400 do Paint(t0 + i * 0.033) end
        end
        cycle()
        collectgarbage("collect")
        collectgarbage("stop")
        local before = collectgarbage("count")
        for pass = 1, 10 do cycle() end
        local grew = collectgarbage("count") - before
        collectgarbage("restart")
        assert(grew < 2, kind .. ": the paint allocated " .. grew .. " KB over 4010 paints")
    end
    W.known["Shifting Power"], W.known["Primal Bite"], W.known["Swiftmend"] = true, true, true
    W.power[4], W.power[3], W.power[1] = 4, 70, 30
    Build()
    Form("caster"); Cast("Wrath", 3000); Cast("Starfire", 3001)
    run("caster")
    Cast("Lacerate", 3000); Cast("Rejuvenation", 3000)
    run("cat")
    run("bear")
    W.canAttack, W.canAssist = false, true
    run("caster")
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
assert(loadstring(HAS_TARGET_SRC, "@Theme.lua"))()
loadAddonFile(LAYOUT_SRC, "Core/Layout.lua")
loadAddonFile(CONFIG_SRC, "Core/Config.lua")
loadAddonFile(FRAMEHELPERS_SRC, "Core/FrameHelpers.lua")
loadAddonFile(GUNSIGHT_SRC, "Modules/CombatHud/Gunsight.lua")
TARGET = { exists = true }
UnitExists = function(u) if u == "player" then return true end return u == "target" and TARGET.exists end
UnitPowerType = function() return 0, "MANA" end
GetShapeshiftFormID = function() return nil end
UnitName = function() return "Boar" end
UnitLevel = function() return 60 end
UnitCanAttack = function() return true end
UnitCanAssist = function() return false end
UnitPower = function() return 0 end
UnitPowerMax = function() return 100 end
loadAddonFile(AREAS_SRC, "Modules/CombatHud/GunsightAreas.lua")
UnitClass = function() return "Druid", "DRUID" end
loadAddonFile(ARTLUA_SRC, "Modules/CombatHud/DruidArt.lua")
loadAddonFile(STATE_SRC, "Modules/CombatHud/DruidState.lua")
loadAddonFile(MODULE_SRC, "Modules/CombatHud/GunsightDruid.lua")
fire("ADDON_LOADED", "forever-stuwave")
fire("PLAYER_LOGIN")

local host = FS.GunsightAreas.Host("lower")
check(host, "the real areas hand out a lower host")
check(isVisible(host), "a target shows the host")
local G = FS.GunsightDruid
check(G.frame and isVisible(G.frame), "the module is built and drawn under the host")
check(onUpdateFrames() == 1, "ticking: " .. onUpdateFrames())
check(isVisible(G.parts.eye[1]) and isVisible(G.parts.moon[1].dark), "the eyes and the moons are drawn")
TARGET.exists = false
fire("PLAYER_TARGET_CHANGED")
check(not isVisible(host) and not isVisible(G.frame) and not isVisible(G.parts.eye[1]) and not isVisible(G.parts.moon[1].dark),
    "no target hides the host and everything under it")
check(onUpdateFrames() == 0, "and stops the OnUpdate")
TARGET.exists = true
fire("PLAYER_TARGET_CHANGED")
check(isVisible(host) and isVisible(G.parts.eye[1]), "a target brings it back")
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
    g.ARTLUA_SRC, g.STATE_SRC, g.MODULE_SRC = ARTLUA, STATE, MODULE
    g.HAS_TARGET_SRC = gs.theme_target_rule_lua()
    try:
        lua.execute(REAL_CASE)
    except LuaError as e:
        return str(e)
    return None


def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    g = rt.globals()
    g.ARTLUA_SRC, g.STATE_SRC, g.MODULE_SRC = ARTLUA, STATE, MODULE
    try:
        rt.execute(MOCK)
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


def static_checks() -> list[str]:
    """The committed art is exactly what the generator writes now; the toc order; the generic class module; no dashes."""
    errs: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, FS_ASSET_OUTPUT_DIR=tmp, FS_ART_LUA_OUTPUT=str(Path(tmp) / "DruidArt.lua"))
        run = subprocess.run([sys.executable, str(GENERATOR)], env=env, capture_output=True, text=True)
        if run.returncode != 0:
            return [f"the generator failed: {run.stderr.strip()[-400:]}"]
        if (Path(tmp) / "DruidArt.lua").read_text(encoding="utf-8") != ARTLUA:
            errs.append("DruidArt.lua differs from the generator's (run tools/assets/generate_druid_gunsight.py)")
        for name in TEXTURES:
            mine = MEDIA / f"{name}.tga"
            if not mine.exists():
                errs.append(f"missing texture {name}.tga")
            elif mine.read_bytes() != (Path(tmp) / f"{name}.tga").read_bytes():
                errs.append(f"{name}.tga differs from the generator's")
    toc = [line.strip() for line in (ADDON / "forever-stuwave.toc").read_text(encoding="utf-8").splitlines()]
    order = ["Modules/CombatHud/GunsightClass.lua", "Modules/CombatHud/DruidArt.lua", "Modules/CombatHud/DruidState.lua",
             "Modules/CombatHud/GunsightDruid.lua"]
    if any(o not in toc for o in order) or [toc.index(o) for o in order] != sorted(toc.index(o) for o in order):
        errs.append("the toc must load GunsightClass, DruidArt, DruidState, GunsightDruid in that order")
    cls = (CH / "GunsightClass.lua").read_text(encoding="utf-8")
    m = re.search(r'RegisterModule, "class", \{\s*classes = \{([^}]*)\}', cls)
    if not m or "DRUID" in m.group(1):
        errs.append("GunsightClass.lua still claims DRUID")
    for path in (CH / "GunsightDruid.lua", CH / "DruidState.lua", GENERATOR, HERE / "assets/druid_mockup/composer.js",
                 HERE / "assets/druid_mockup_build.py", Path(__file__)):
        if re.search("[\u2013\u2014]", path.read_text(encoding="utf-8")):
            errs.append(f"{path.name} has an em or en dash")
    for path in (CH / "GunsightDruid.lua", CH / "DruidState.lua"):
        if re.search(r"(?i)\bbot\b|automat|macro", path.read_text(encoding="utf-8")):
            pass
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
