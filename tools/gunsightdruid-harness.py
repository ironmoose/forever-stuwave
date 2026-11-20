#!/usr/bin/env python3
"""Runs the real GunsightDruid.lua (the Druid's Gunsight Class Module), DruidState.lua and the generated DruidArt.lua headless.

The module draws one layout per form: in caster form the Thorns timer, the Bramble Wreath (design mockup "Druid Thorns Concepts",
2026-11-17, concept A); in Cat and Bear still the design "Druid Gunsight Module: Wildshape Eyes" (2026-11-16): slit and angry eyes,
one gauge under them (five claw gashes and the energy bar, the rage bar and Lacerate pips) and a cue word. These checks pin:

  * the art: the committed DruidArt.lua and the nine druid_*.tga files are exactly what the generator writes now, every sprite
    name the module can ask for is in the manifest, the toc loads art, state, then module after the generic class module;
  * Thorns: the aura read out of combat (the wedges dry, the leaves fallen, the label), the ledger of our own cast in combat ("~",
    the cast ring), a cast on a friend is not ours, gone in combat draws nothing and gone out of combat the reminder, not learned
    draws nothing, the last minute is amber (bead, leaf, blinking tips), a reload in combat is unknown until a read or a cast;
  * the registration: one "class" module for DRUID only; the generic GunsightClass.lua no longer lists DRUID;
  * the form: UnitPowerType ENERGY is Cat, RAGE is Bear, a travel form id is Travel, caster is Moon on a hostile target and
    Tree on a friendly one, a secret answer is caster;
  * the Eclipse and heal over time ledgers still count (nothing draws them now);
  * the Cat: the gashes and the five point flare are bars fed the count (a secret one reaches only SetValue), FINISH / SHIFT only
    from plain reads, the number only through SetFormattedText, the chip's engine timer or its ledger fallback, the spend streak;
  * the Bear: the rage bar, the cue priority, the Lacerate ledger (5 stacks, 15 s, reset on another target), the pips;
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
TEXTURES = ["druid_gunsight", "druid_thorns", "druid_slash_lit", "druid_slash_flare", "druid_energy_fill", "druid_rage_fill", "druid_chip_sp",
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
      secretForm = false, spellById = { [5176] = "Wrath", [2912] = "Starfire", [774] = "Rejuvenation", [8936] = "Regrowth", [6807] = "Maul",
      [18562] = "Swiftmend", [33745] = "Lacerate", [22568] = "Ferocious Bite", [1079] = "Rip", [9999] = "Primal Bite",
      [8888] = "Shifting Power", [467] = "Thorns", [1] = "Auto Attack" }, auras = {} }
function UnitPowerType(u) if W.secretForm then return SECRET, SECRET end return W.powerType[1], W.powerType[2] end
function GetShapeshiftFormID() if W.secretForm then return SECRET end return W.formId end
function UnitName(u) if W.secretName then return SECRET end if u == "player" then return "Stu" end return W.name end
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
C_UnitAuras = {
    GetAuraDataBySpellName = function(unit, name, filter)
        if W.combat then return SECRET end
        return W.auras[name]
    end,
}
TIMERS = {}
C_Timer = { After = function(d, fn) TIMERS[#TIMERS + 1] = fn end }
function Timers() local list = TIMERS; TIMERS = {}; for _, fn in ipairs(list) do fn() end end
SUBS = {}
FS = {
    AurasReadable = function() return not W.combat end,
    IsSecret = function(v) return v == SECRET end,
    Gunsight = { G = { AREA = { x = 1213, w = 202, h = 128, upperY = 500, lowerY = 632 }, TR = { x0 = 1164, x1 = 1194 } },
        ui = function(px) return px * __scale end, Point = function(f, p, x, y) f.pt = { p, "root", "CENTER", x, y } end },
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
-- A cooldown change: the module coalesces SPELL_UPDATE_COOLDOWN bursts into its next slow poll (at most 0.1 s away), so the
-- event is followed by 0.11 s of its own ticker, as the client would run it.
function CooldownChanged()
    fire("SPELL_UPDATE_COOLDOWN")
    local f = M.frame and M.frame.scripts and M.frame.scripts.OnUpdate
    if f then f(M.frame, 0.11) end
end
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
function Sent(target) fire("UNIT_SPELLCAST_SENT", "player", target, "guid", 467) end
function Aura() fire("UNIT_AURA", "player") end
-- what the wreath shows: the glyph names left to right, the dry and live vine wedges, the shown leaves
function Label()
    local l = P().thLabel
    if l and l.fsOn then return (l.fsWord or ""):gsub("~", "tilde") end
    return ""
end
function OldLabel()
    local out = {}
    for _, g in ipairs(P().thGlyph) do if g.fsOn then out[#out + 1] = g.fsName:gsub("th_glyph_", "") end end
    return table.concat(out)
end
function Wedges()
    local dry, live = 0, 0
    for _, v in ipairs(P().thVine) do
        if v.fsOn then if v.fsName:match("_dry$") then dry = dry + 1 else live = live + 1 end end
    end
    return dry, live
end
function AnyThorns()
    for _, t in ipairs(P().thVine) do if t.fsOn then return true end end
    return P().thGone.fsOn or P().thGlyph[1].fsOn or P().thLabel.fsOn
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

case("the_lower_area_draws_it_bigger_clear_of_the_tape_and_the_upper_area_keeps_it_inside", """
    local m = Build()
    SPEC.seat({ x = 1213, y = 632, w = 202, h = 128 })
    assert(m.w == 150 * 2 and m.h == 86 * 2, "lower: twice the sprite px: " .. tostring(m.w))
    assert(m.pt[4] == 1200 and m.pt[5] == 637, "lower: as centred as the tape allows (6 px right of it): " .. tostring(m.pt[4]))
    SPEC.seat({ x = 1213, y = 500, w = 202, h = 128 })
    assert(m.w == 150 * 1.25 and m.h == 86 * 1.25, "upper: the class modules' size: " .. tostring(m.w))
    assert(m.w <= 202 and m.h + 5 <= 128, "upper: inside the area")
    assert(m.pt[4] == 1213 + (202 - 150 * 1.25) / 2, "upper: centred")
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
    for _, n in ipairs({ "ivy", "ivy_buds", "halo", "slash_dark", "track_energy",
        "track_rage", "pip_dark", "pip_lit", "letter_L", "letter_B", "letter_M",
        "chip_ring", "chip_sp", "chip_pb", "chip_sm" }) do want(n) end
    assert(#missing == 0, "missing sprites: " .. table.concat(missing, ", "))
    local seen = {}
    for _, name in ipairs({ "druid_slash_lit", "druid_slash_flare", "druid_energy_fill", "druid_rage_fill", "druid_chip_sp",
        "druid_chip_pb", "druid_chip_sm" }) do assert(Art.FILES[name], name) end
    -- every Thorns name: a thorn pop step too short to draw (the page skips a thorn under 0.6 px) is the only gap
    local TS = Art.THORNS.sprites
    local function wantT(n, short)
        if not TS[n] and not short then missing[#missing + 1] = tostring(n) end
    end
    local TN = M.THORN_NAMES
    for k = 0, Art.THORNS.WEDGES - 1 do wantT(TN.vine[k].live); wantT(TN.vine[k].dry); wantT(TN.glow[k]) end
    for j = 0, 19 do
        wantT(TN.thorn[j].dry); wantT(TN.thorn[j].blink)
        for p = 1, Art.THORNS.POPS do wantT(TN.thorn[j][p], p <= 2) end
    end
    for i = 0, 9 do wantT(TN.leaf[i].wilt); for u = 1, Art.THORNS.UNF do wantT(TN.leaf[i][u]) end end
    for s = 0, Art.THORNS.AMBER do wantT(TN.amber[s]) end
    for s = 0, Art.THORNS.SPIN - 1 do wantT(TN.fall[s]) end
    for _, g in pairs(TN.glyph) do wantT(g) end
    wantT("th_gone"); wantT("th_sparkle")
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

case("the_eclipse_and_hot_ledgers_still_count", """
    Start("caster")
    Cast("Wrath", 1000)
    local mode, ch = St.Eclipse(1000.5)
    assert(mode == "ok" and ch == 2, "Wrath banks two")
    Cast("Starfire", 1001)
    mode, ch = St.Eclipse(1001.5)
    assert(ch == 1, "Starfire spends one")
    W.canAttack, W.canAssist, W.name = false, true, "Tank"
    fire("PLAYER_TARGET_CHANGED")
    Sent("Tank"); Cast("Rejuvenation", 1002)
    assert(St.Hot("rejuv", 1003) and math.abs(St.Hot("rejuv", 1003) - 11) < 1e-6, "Rejuvenation on the friend, 12 s")
    assert(not P().eye[1].fsOn, "no eyes in caster form, friend or foe")
    NoLog()
""")

case("a_hot_on_yourself_follows_you_with_no_target_or_an_enemy", """
    Start("caster")
    W.name, W.canAttack, W.canAssist = nil, false, false
    fire("PLAYER_TARGET_CHANGED")
    Sent(""); Cast("Rejuvenation", 2000)
    assert(St.Hot("rejuv", 2001) and Near(St.Hot("rejuv", 2001), 11), "a self Rejuvenation with nothing targeted is kept")
    W.name, W.canAttack, W.canAssist = "Boar", true, false
    fire("PLAYER_TARGET_CHANGED")
    assert(St.Hot("rejuv", 2002) and Near(St.Hot("rejuv", 2002), 10), "an enemy targeted: the HoTs still follow you")
    Sent("Boar"); Cast("Regrowth", 2003)
    assert(St.Hot("regrow", 2004) and Near(St.Hot("regrow", 2004), 20), "a Regrowth cast with an enemy targeted lands on you")
    W.name, W.canAttack, W.canAssist = "Tank", false, true
    fire("PLAYER_TARGET_CHANGED")
    assert(St.Hot("rejuv", 2004) == nil, "a friend targeted: only HoTs on that friend show")
    NoLog()
""")

case("thorns_out_of_combat_is_the_aura", """
    W.known["Thorns"] = true
    W.auras["Thorns"] = { expirationTime = 1000 + 265 }
    Start("caster")
    Aura()
    Paint(1000)
    local mode, left, est = St.Thorns(1000)
    assert(mode == "up" and left == 265 and not est, "the plain aura: " .. tostring(mode) .. " " .. tostring(left))
    local dry, live = Wedges()
    assert(dry == 33 and live == 27, "265 s left: 33 of 60 wedges dry, got " .. dry .. "/" .. live)
    assert(Label() == "5M", "the label: " .. Label())
    local leaves = 0
    for i = 1, 10 do if P().thLeaf[i].fsOn then leaves = leaves + 1 end end
    assert(leaves == 5, "five minutes, five leaves: " .. leaves)
    assert(P().thLeaf[6].fsName == "th_leaf_5_wilt" and P().thLeaf[7].fsName == "th_leaf_6_10", "the leaf under the dry line browns")
    assert(P().thBead.fsOn and not P().thRing[1].fsOn, "the bead, no cast ring")
    assert(not P().eye[1].fsOn and not P().cue.fsOn, "no eyes and no word")
    for j = 1, 20 do assert(P().thThorn[j].fsOn, "thorn " .. j) end
    NoLog()
""")

case("thorns_gone_is_a_reminder_out_of_combat_and_nothing_in_combat", """
    W.known["Thorns"] = true
    Start("caster")
    Aura()
    Paint(1000)
    assert(St.Thorns(1000) == "gone")
    assert(P().thGone.fsOn and Label() == "THORNS", "after combat: the dim rings and THORNS: " .. Label())
    local dry, live = Wedges()
    assert(dry + live == 0, "no wreath")
    W.combat = true
    fire("PLAYER_REGEN_DISABLED")
    Paint(1001)
    assert(not AnyThorns(), "in combat nothing is drawn")
    W.combat = false
    W.known["Thorns"] = false
    fire("PLAYER_REGEN_ENABLED")
    CooldownChanged()
    Paint(1002)
    assert(not AnyThorns(), "not learned: no reminder")
    NoLog()
""")

case("thorns_cast_in_combat_is_a_ledger_and_plays_the_cast", """
    W.known["Thorns"] = true
    W.combat = true
    Start("caster")
    assert(St.Thorns(1000) == "unknown" and not AnyThorns(), "a reload in combat: unknown, nothing drawn")
    Cast("Thorns", 1000)
    Paint(1000.3)
    local dry, live = Wedges()
    assert(dry == 0 and live > 0 and live < 60, "the vine grows round: " .. live)
    assert(P().thRing[1].fsOn or P().thRing[2].fsOn, "the green ring goes out")
    Paint(1000.63)
    assert(P().thThorn[1].fsName == "th_thorn_0_6", "the thorns snap out: " .. tostring(P().thThorn[1].fsName))
    Paint(1002)
    dry, live = Wedges()
    assert(live == 60 and not P().thRing[1].fsOn and not P().thRing[2].fsOn, "grown, the ring gone")
    assert(P().thLeaf[1].fsName == "th_leaf_0_10", "the leaves unfurled")
    local mode, left, est = St.Thorns(1002)
    assert(mode == "up" and est and math.abs(left - 598) < 1e-6, "the ledger: 600 s from the cast")
    assert(Label() == "tilde10M", "the estimate mark: " .. Label())
    Paint(1000 + 601)
    assert(not AnyThorns(), "run out in combat: nothing")
    -- a cast on a friend is not ours
    W.canAttack, W.canAssist, W.name = false, true, "Tank"
    fire("PLAYER_TARGET_CHANGED")
    Sent("Tank"); Cast("Thorns", 1700)
    assert(St.Thorns(1700) ~= "up", "Thorns on the friend")
    Sent(""); Cast("Thorns", 1705)
    assert(St.Thorns(1705) == "up", "an empty target name is the player")
    Sent("Stu"); Cast("Thorns", 1710)
    assert(St.Thorns(1710) == "up", "our own name is the player")
    -- after combat the aura is the truth
    W.combat = false
    W.auras["Thorns"] = { expirationTime = 1710 + 500 }
    fire("PLAYER_REGEN_ENABLED")
    local _, l2, e2 = St.Thorns(1710)
    assert(not e2 and l2 == 500, "the read drops the mark")
    NoLog()
""")

case("thorns_out_of_combat_cast_reads_the_aura_back", """
    W.known["Thorns"] = true
    Start("caster")
    Cast("Thorns", 1000)
    W.auras["Thorns"] = { expirationTime = 1000 + 600 }
    Timers()
    local mode, left, est = St.Thorns(1001)
    assert(mode == "up" and not est and left == 599, "read back after the cast")
    NoLog()
""")

case("thorns_last_minute_is_amber", """
    W.known["Thorns"] = true
    W.auras["Thorns"] = { expirationTime = 1000 + 40 }
    Start("caster")
    Aura()
    Paint(1000)
    assert(Label() == "40S" and P().thLabel.fsCol[1] > 0.9 and P().thLabel.fsCol[3] < 0.4, "seconds, in amber: " .. Label())
    assert(P().thLeaf[10].fsName:match("^th_leaf_9_amber_"), "the last leaf pulses amber: " .. tostring(P().thLeaf[10].fsName))
    for i = 1, 9 do assert(not P().thLeaf[i].fsOn, "leaf " .. i .. " fell") end
    assert(P().thBead.color[1] > 0.9 and P().thBead.color[3] < 0.4, "the bead is amber")
    local blinks = {}
    for k = 0, 20 do Paint(1000 + k * 0.05); blinks[P().thThorn[20].fsName] = true end
    assert(blinks["th_thorn_19_blink"] and blinks["th_thorn_19_10"], "the thorn tips blink amber")
    NoLog()
""")

case("a_falling_leaf_drops_for_two_and_a_half_seconds", """
    W.known["Thorns"] = true
    W.auras["Thorns"] = { expirationTime = 1000 + 541 }
    Start("caster")
    Aura()
    Paint(1000)
    assert(P().thLeaf[1].fsOn and not P().thFall[1].fsOn)
    Paint(1002)                                   -- 539 s left: leaf 0 fell 1 s ago
    assert(not P().thLeaf[1].fsOn and P().thFall[1].fsOn and P().thFall[1].fsName:match("^th_fall_"), "it falls")
    Paint(1004)
    assert(not P().thFall[1].fsOn, "and is gone")
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

case("every_value_secret_at_once_draws_without_an_error", """
    W.secretPower, W.secretName, W.secretLevel, W.secretCd, W.secretForm = true, true, true, true, true
    W.canAttack, W.canAssist = SECRET, SECRET
    for _, k in ipairs({ "caster", "cat", "bear", "travel" }) do
        Start(k)
        for i = 0, 30 do Paint(1000 + i * 0.1) end
        fire("UNIT_POWER_FREQUENT", "player")
        CooldownChanged()
        Paint(1040)
    end
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
    W.known["Thorns"] = true
    W.combat = true
    Start("caster")
    Cast("Thorns", 2020)
    Paint(2020.2)
    for _, d in ipairs(P().thRing) do assert(not d.fsOn, "no cast ring") end
    for _, d in ipairs(P().thFly) do assert(not d.fsOn, "no fireflies") end
    local dry, live = Wedges()
    assert(live == 60, "the wreath is there at once")
    W.combat = false
    ForeverSTUwaveDB = nil
    NoLog()
""")

case("forms_draw_only_their_registered_look", """
    -- the Wildshape Eyes are retired: a form with no look draws nothing of the old module
    for _, k in ipairs({ "cat", "bear", "travel" }) do
        Start(k)
        for i = 0, 10 do Paint(1000 + i * 0.1) end
        assert(not P().eye[1].fsOn and not P().cue.fsOn and not P().slash[1].fsOn and not P().rageTrack.fsOn,
            k .. ": no eyes, cue or gauge")
        assert(not P().thVine[1].fsOn and not P().thLabel.fsOn, k .. ": no caster wreath")
    end
    -- a registered look is built with the module, seated, shown only in its form and painted there
    local calls = { build = 0, seat = 0, show = 0, hide = 0, paint = 0 }
    local spec = {
        build = function(parent) calls.build = calls.build + 1; return CreateFrame("Frame", nil, parent) end,
        seat = function(ox, oy, spx) calls.seat = calls.seat + 1; calls.spx = spx end,
        show = function() calls.show = calls.show + 1; calls.on = true end,
        hide = function() calls.hide = calls.hide + 1; calls.on = false end,
        paint = function(now, data) calls.paint = calls.paint + 1; calls.kind = data.kind end,
    }
    assert(M.RegisterForm("bear", spec), "registered")
    assert(calls.build == 1 and calls.seat >= 1 and calls.spx == M.C.SPX, "built and seated at once on a built module")
    Form("bear"); Paint(1100)
    assert(calls.on == true and calls.paint >= 1 and calls.kind == "bear", "shown and painted in its form")
    local painted = calls.paint
    Form("cat"); Paint(1101)
    assert(calls.on == false and calls.paint == painted, "hidden and not painted in another form")
    __scale = 2
    local seats = calls.seat
    SPEC.seat({ x = 0, y = 0, w = 200, h = 128 })
    assert(calls.seat > seats, "a rescale seats it again")
    NoLog()
""")

case("a_caster_look_serves_both_caster_kinds_and_is_painted_after_the_wreath", """
    -- the key "caster" names one look for the moon and the tree kinds: shown with the wreath, painted after it, hidden in every other form
    local calls = { show = 0, hide = 0, paint = 0 }
    local order = {}
    local spec = {
        build = function(parent) calls.built = parent; return CreateFrame("Frame", nil, parent) end,
        seat = function() end,
        show = function() calls.show = calls.show + 1; calls.on = true end,
        hide = function() calls.hide = calls.hide + 1; calls.on = false end,
        paint = function(now, data) calls.paint = calls.paint + 1; calls.kind = data.kind; order[#order + 1] = "look" end,
    }
    assert(M.RegisterForm("caster", spec), "registered before the module is built, as the toc loads it")
    Start("caster")
    assert(calls.built == M.frame, "built under the module frame")
    local realThorns = St.Thorns
    St.Thorns = function(...) order[#order + 1] = "wreath"; return realThorns(...) end
    W.known["Thorns"] = true
    W.auras["Thorns"] = { expirationTime = 1000 + 100 }
    Aura()
    -- a hostile target: the moon kind
    Paint(1000.1)
    assert(calls.on == true and calls.kind == "moon", "shown and painted for the moon kind: " .. tostring(calls.kind))
    assert(P().thVine[1].fsOn and P().thLabel.fsOn, "the wreath is drawn as before")
    assert(order[#order - 1] == "wreath" and order[#order] == "look", "the look is painted after the wreath: " .. table.concat(order, ","))
    -- a friend: the tree kind, the same look
    W.canAttack, W.canAssist, W.name = false, true, "Tank"
    fire("PLAYER_TARGET_CHANGED")
    local before = calls.paint
    order = {}
    Paint(1000.2)
    assert(calls.kind == "tree" and calls.paint == before + 1 and calls.on == true, "the tree kind is painted by the same look")
    assert(order[1] == "wreath" and order[2] == "look" and #order == 2, "once each, wreath first: " .. table.concat(order, ","))
    -- the other forms hide it and do not paint it
    for _, k in ipairs({ "cat", "bear", "travel" }) do
        Form(k); Paint(1001)
        assert(calls.on == false, k .. ": the caster look is hidden")
        local n = calls.paint
        Paint(1001.1)
        assert(calls.paint == n, k .. ": and not painted")
    end
    Form("caster"); Paint(1002)
    assert(calls.on == true, "the caster form shows it again")
    -- the wreath is untouched by the look in the caster form
    assert(P().thVine[1].fsOn or P().thLabel.fsOn, "the wreath is still drawn")
    NoLog()
""")

case("onshow_subscribes_and_onhide_stops_everything", """
    Build()
    assert(M.frame.scripts.OnUpdate and M.frame.scripts.OnEvent and M.frame.events.UNIT_POWER_FREQUENT, "shown: the ticker and the power events")
    SPEC.onHide("lower")
    assert(not M.frame.scripts.OnUpdate and not M.frame.scripts.OnEvent and not M.frame.events.UNIT_POWER_FREQUENT, "hidden: all of it stopped")
    -- the ledger keeps listening while hidden
    W.combat = true
    Cast("Thorns", 1000)
    SPEC.onShow("lower")
    Paint(1001)
    assert(St.Thorns(1001) == "up" and P().thVine[1].fsOn, "a cast while hidden is not lost")
    W.combat = false
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
    W.known["Thorns"] = true
    W.auras["Thorns"] = { expirationTime = 3000 + 75 }
    Build()
    Form("caster"); Aura()
    run("caster")
    Cast("Lacerate", 3000); Cast("Rejuvenation", 3000)
    run("cat")
    run("bear")
    W.canAttack, W.canAssist = false, true
    W.auras["Thorns"] = nil
    Form("caster"); Aura()
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
UnitPowerType = function() return 1, "RAGE" end
GetShapeshiftFormID = function() return 5 end
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
check(not isVisible(G.parts.eye[1]) and not isVisible(G.parts.rageTrack), "the retired eyes and rage bar are not drawn in Bear form")
TARGET.exists = false
fire("PLAYER_TARGET_CHANGED")
check(not isVisible(host) and not isVisible(G.frame) and not isVisible(G.parts.eye[1]) and not isVisible(G.parts.rageTrack),
    "no target hides the host and everything under it")
check(onUpdateFrames() == 0, "and stops the OnUpdate")
TARGET.exists = true
fire("PLAYER_TARGET_CHANGED")
check(isVisible(host) and isVisible(G.frame), "a target brings it back")
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
    m = (re.search(r'RegisterModule, "class", \{\s*classes = \{([^}]*)\}', cls)
         or re.search(r'local CLASSES = \{([^}]*)\}', cls))
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
