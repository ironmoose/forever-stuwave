#!/usr/bin/env python3
"""Runs the real GunsightDruidBear.lua (the Druid's Bear form look) on top of the real GunsightDruid.lua, DruidState.lua and the
generated DruidBearArt.lua, headless.

The Bear look is the Demoralizing Roar tracker (design mockup "Druid Roar Bear Animated", 2026-11-17: a roaring bear head with an
animated jaw in a floating storm aura, five sound arcs a side as the 30 s timer) and a small Thorns corner (design mockup "Druid
Gunsight Module: One Layout Per Form", 2026-11-16). These checks pin:

  * the art: the committed DruidBearArt.lua and druid_bear_1.tga are exactly what the generator writes now, every sprite name the
    module can ask for is in the manifest, the toc loads art then look after the generic Druid module;
  * the mockup: the numbers the look shares with the page (the eye points, the arc rings and 3 s pieces, the jaw frame times, the
    lunge, the label places) are pinned against the page's own source, so the port cannot drift;
  * the seam: the look registers as "bear", is built with the module, shown only in Bear form and hidden in every other;
  * the data: the roar clock is the player's own cast by NAME (any rank, 30 s, "~"), ignores other spells and a secret id, keeps
    listening while the host is hidden; out of combat the target's debuff by name is read (a plain expiry is exact, a readable
    "not there" ends the ledger, a secret answer or a friendly target says nothing, in combat nothing is read);
  * not learned draws nothing of the roar, Thorns draws its own corner independently;
  * the arcs (ten, outer first, one per 3 s, amber for the last 5 s, flicker when one runs out, lit ring by ring after a roar);
  * the states: running, last 5 s, down in combat (shut jaw, grey, the cloud still, ROAR), down out of combat (dim, no cloud);
  * the roar: the jaw frames by time, the lunge and bob, the eyes' flare, the shake, the lightning and its flash, the shock rings;
  * the Thorns corner: segments by minute, amber and the seconds in the last minute, "~" for the ledger, gone out of combat only,
    unknown and not learned draw nothing;
  * reduced motion, every value secret at once, a rescale, and a paint that allocates nothing once warm;
  * under the REAL GunsightAreas.lua the host hides with no target, the look stops, and it comes back with a target.

    python3 tools/gunsightdruidbear-harness.py [--png debug/druid-bear]

`--png PREFIX` also writes PREFIX-roar.png and PREFIX-thorns.png: the states of the look played through the real module and
composited from the baked atlas (4 px per sprite px, over the dark ground). Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import os
import re
import struct
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
MODULE = (CH / "GunsightDruidBear.lua").read_text(encoding="utf-8")
DRUID = (CH / "GunsightDruid.lua").read_text(encoding="utf-8")
STATE = (CH / "DruidState.lua").read_text(encoding="utf-8")
DRUIDART = (CH / "DruidArt.lua").read_text(encoding="utf-8")
ARTLUA_PATH = CH / "DruidBearArt.lua"
ARTLUA = ARTLUA_PATH.read_text(encoding="utf-8")
GENERATOR = ROOT / "tools/assets/generate_druid_bear.py"
MEDIA = ADDON / "Media/Textures"
MOCKUP = ROOT / "mockups/gunsight-druid-roar-bear-anim-2026-11-17.html"
SPX = 1.25
BG = (10, 4, 22)

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
function Obj:GetParent() return self.parent end
function Obj:SetScript(n, fn) self.scripts = self.scripts or {}; self.scripts[n] = fn end
function Obj:SetTexture(p, ...) self.tex = p; self.filter = select(3, ...) end
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
function Obj:SetShadowColor(r, g, b, a) self.shadow = { r, g, b, a } end
function Obj:SetShadowOffset(x, y) self.shadowOff = { x, y } end
function Obj:SetStatusBarTexture(p) self.tex = p end
function Obj:SetMinMaxValues(lo, hi) self.lo, self.hi = lo, hi end
function Obj:SetValue(v) self.value = v; self.timer = nil end
function Obj:SetTimerDuration(obj, interp, dir) self.timer = obj; return true end
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
W = { powerType = { 1, "RAGE" }, formId = 5, level = 60, name = "Boar", exists = false, canAttack = true, canAssist = false,
      power = { [1] = 0, [3] = 100, [4] = 0 }, powerMax = { [1] = 100, [3] = 100, [4] = 5 }, combat = false,
      known = { ["Demoralizing Roar"] = true, ["Thorns"] = true }, cd = {}, secretPower = false, secretName = false,
      secretLevel = false, secretCd = false, secretForm = false, secretAura = false, secretKnown = false,
      spellById = { [5176] = "Wrath", [467] = "Thorns", [6807] = "Maul", [9898] = "Demoralizing Roar", [99] = "Demoralizing Roar",
                    [11556] = "Demoralizing Shout", [33745] = "Lacerate" },
      auras = {}, targetAuras = {} }
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
        return { isActive = W.cd[name] == true, isOnGCD = false }
    end,
    GetSpellCooldownDuration = function(name) return { duration = name } end,
}
C_UnitAuras = {
    GetAuraDataBySpellName = function(unit, name, filter)
        if W.combat or W.secretAura then return SECRET end
        if unit == "target" then return W.targetAuras[name] end
        return W.auras[name]
    end,
}
TIMERS = {}
C_Timer = { After = function(d, fn) TIMERS[#TIMERS + 1] = fn end }
function Timers() local list = TIMERS; TIMERS = {}; for _, fn in ipairs(list) do fn() end end
FS = {
    AurasReadable = function() return not W.combat end,
    IsSecret = function(v) return v == SECRET end,
    Gunsight = { ui = function(px) return px * __scale end, Point = function(f, p, x, y) f.pt = { p, "root", "CENTER", x, y } end },
    GunsightAreas = Areas,
    Theme = { ApplyMono = function(fs, size, color) fs.size = size; fs.tcolor = color; fs.monoSet = true end },
    LogDegradeOnce = function(k, m) __logged = __logged or {}; __logged[k] = m end,
    FrameHelpers = {
        RegisterEvent = function(f, e, unit) f.events = f.events or {}; f.events[e] = unit or true; return true end,
        ResolveSpell = function(name) for id, n in pairs(W.spellById) do if n == name then return id end end return nil end,
        IsKnownSpellId = function(id) if W.secretKnown then return false end local n = W.spellById[id]; return W.known[n] == true end,
    },
}
assert(loadstring(DRUIDART_SRC, "@DruidArt.lua"))("forever-stuwave", FS)
assert(loadstring(STATE_SRC, "@DruidState.lua"))("forever-stuwave", FS)
assert(loadstring(DRUID_SRC, "@GunsightDruid.lua"))("forever-stuwave", FS)
assert(loadstring(BEARART_SRC, "@DruidBearArt.lua"))("forever-stuwave", FS)
assert(loadstring(MODULE_SRC, "@GunsightDruidBear.lua"))("forever-stuwave", FS)
M, St, Art, B = FS.GunsightDruid, FS.DruidState, FS.DruidBearArt, FS.GunsightDruidBear
SPEC = Areas.specs[1] and Areas.specs[1].spec
HOST = New("Frame")
function Build()
    local m = SPEC.build(HOST)
    SPEC.seat({ x = 0, y = 0, w = 200, h = 128 })
    SPEC.onShow("lower")
    return m
end
function P() return B.parts end
function Paint(t) __now = t or __now; M.Paint(__now) end
function Cast(name, t)
    __now = t or __now
    local id
    for i, n in pairs(W.spellById) do if n == name then id = i end end
    fire("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", id)
end
function Near(a, b, eps) return math.abs(a - b) <= (eps or 1e-6) end
function NoLog() for k, v in pairs(__logged or {}) do error("logged " .. k .. ": " .. tostring(v)) end end
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
    Form(kind or "bear")
    M.Paint(__now)
end
function Aura() fire("UNIT_AURA", "player") end
function Hit(t) return t.fsOn == true and vis(t) end
function Name(t) if Hit(t) then return t.fsName end return nil end
function Word(fs) if Hit(fs) then return fs.fsWord end return nil end
function ArcsUp()
    local n = 0
    for p = 0, 9 do if Hit(P().arcB[p]) then n = n + 1 end end
    return n
end
function Streaks()
    local n = 0
    for e = 1, 2 do for i = 1, 4 do for k = 1, 2 do if Hit(P().eye[e].streak[i][k]) then n = n + 1 end end end end
    return n
end
function AnyRoar()
    local p = P()
    if Hit(p.aura) or Hit(p.head) or Hit(p.halo) or Hit(p.num) or Hit(p.word) then return true end
    for i = 0, 9 do if Hit(p.arcA[i]) or Hit(p.arcB[i]) or Hit(p.arcC[i]) then return true end end
    for e = 1, 2 do if Hit(p.eye[e].centre) then return true end end
    for s = 1, 3 do if Hit(p.ring[s]) then return true end end
    return false
end
function Segs()
    local live, amber, dry = 0, 0, 0
    for i = 1, 10 do
        local n = Name(P().thSeg[i])
        if n then
            if n:match("_live$") then live = live + 1 elseif n:match("_amber$") then amber = amber + 1 else dry = dry + 1 end
        end
    end
    return live, amber, dry
end
function AnyThorns()
    for i = 1, 10 do if Hit(P().thSeg[i]) then return true end end
    return Hit(P().thGhost) or Hit(P().thText) or Hit(P().thWord)
end
-- a roar cast at `t0`, looked at `ca` seconds later
function RoarAt(t0, ca)
    Cast("Demoralizing Roar", t0)
    Paint(t0 + ca)
end

-- every region the look shows, in paint order, for the picture: texture rows and text rows with their place on the canvas (ui px)
function Dump()
    local order = { BACKGROUND = 1, BORDER = 2, ARTWORK = 3, OVERLAY = 4, HIGHLIGHT = 5 }
    local function abs(o)
        if type(o) ~= "table" or o.name == "ForeverSTUwaveGunsightDruid" then return 0, 0 end
        local pt = o.pt
        if not pt then return 0, 0 end
        local rx, ry = abs(pt[2])
        return rx + pt[4], ry - pt[5]
    end
    local rows = {}
    for _, o in ipairs(__all) do
        if (o.kind == "Texture" or o.kind == "FontString") and o.fsOn == true and vis(o) and o.parent and vis(o.parent) then
            local x, y = abs(o)
            local c = o.color
            rows[#rows + 1] = { kind = o.kind, tex = o.tex, l = o.tc and o.tc[1], r = o.tc and o.tc[2], t = o.tc and o.tc[3],
                b = o.tc and o.tc[4], w = o.w, h = o.h, x = x, y = y, cr = c and c[1] or 1, cg = c and c[2] or 1, cb = c and c[3] or 1,
                ca = c and c[4] or 1, level = o.parent.level or 0, layer = order[o.layer or "ARTWORK"] or 3, sub = o.sub or 0,
                seq = o.seq, text = o.text, size = o.size, tr = o.tcolor and o.tcolor[1], tg = o.tcolor and o.tcolor[2],
                tb = o.tcolor and o.tcolor[3], ta = o.tcolor and o.tcolor[4] }
        end
    end
    table.sort(rows, function(a, b)
        if a.level ~= b.level then return a.level < b.level end
        if a.layer ~= b.layer then return a.layer < b.layer end
        if a.sub ~= b.sub then return a.sub < b.sub end
        return a.seq < b.seq
    end)
    return rows
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("registers_the_bear_form_and_shows_it_only_in_bear_form", """
    assert(M.forms.bear, "the look registers as bear")
    assert(not B.frame, "nothing is built at load")
    Build()
    assert(B.frame and B.frame.name == "ForeverSTUwaveDruidBear" and B.frame.parent == M.frame, "built with the module, under it")
    Form("bear"); Paint(1000)
    assert(vis(B.frame) and AnyRoar(), "Bear form draws it")
    for _, kind in ipairs({ "caster", "cat", "travel", "bear" }) do
        Form(kind); Paint(1001)
        assert(vis(B.frame) == (kind == "bear"), kind .. ": " .. tostring(vis(B.frame)))
    end
    NoLog()
""")

case("every_sprite_the_look_names_is_in_the_manifest", """
    Build()
    local missing = {}
    local function want(n) if not Art.sprites[n] then missing[#missing + 1] = tostring(n) end end
    for _, tbl in ipairs({ B.NAME.aura, B.NAME.light[35], B.NAME.light[121], B.NAME.ring, B.NAME.thLive, B.NAME.thAmber, B.NAME.thDry,
                           B.NAME.head, B.NAME.bolt }) do
        for _, n in pairs(tbl) do want(n) end
    end
    for _, a in pairs(B.NAME.arc) do want(a.a); want(a.b); want(a.c) end
    want("halo"); want("th_ghost")
    assert(#missing == 0, "missing sprites: " .. table.concat(missing, ", "))
    for n = 0, Art.AURA_FRAMES - 1 do assert(Art.sprites["aura_" .. n], "aura " .. n) end
    for name, s in pairs(Art.sprites) do
        assert(s[1] >= 0 and s[2] >= 0 and s[1] + s[3] <= Art.AW and s[2] + s[4] <= Art.AH, name .. " is inside the atlas")
        if name ~= "head_open" and not name:match("^head_") then
            assert(s[5] >= 0 and s[6] >= 0 and s[5] + s[3] <= Art.GW and s[6] + s[4] <= Art.GH, name .. " is inside the canvas")
        end
    end
    NoLog()
""")

case("the_roar_clock_is_the_players_own_cast_by_name", """
    Start("bear")
    local left = B.RoarLeft(1000)
    assert(left == 0 and not B.RoarCastAt(), "nothing cast: down")
    Cast("Demoralizing Shout", 1000); Cast("Maul", 1000); Cast("Lacerate", 1000)
    fire("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", SECRET)
    fire("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", nil)
    assert(B.RoarLeft(1000) == 0, "other spells, a secret id and a missing id are ignored")
    Cast("Demoralizing Roar", 1000)
    local l, est = B.RoarLeft(1000)
    assert(l == 30 and est, "30 s from the cast, an estimate")
    l = B.RoarLeft(1010.5)
    assert(Near(l, 19.5), "it runs: " .. l)
    assert(B.RoarLeft(1030) == 0 and B.RoarLeft(1031) == 0, "and ends at 30 s")
    __now = 1031
    fire("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", 99)           -- another rank, the same name
    l = B.RoarLeft(1031)
    assert(Near(l, 30), "another rank restarts it too: " .. l)
    Cast("Demoralizing Roar", 1040)
    l = B.RoarLeft(1041)
    assert(Near(l, 29), "a new cast restarts it: " .. l)
    NoLog()
""")

case("another_rank_counts_and_a_cast_while_the_host_is_hidden_is_not_lost", """
    Build()
    Form("bear")
    SPEC.onHide("lower")
    W.spellById[9747] = "Demoralizing Roar"
    __now = 1000
    fire("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", 9747)
    assert(Near(B.RoarLeft(1005), 25), "rank by name, stamped while hidden")
    SPEC.onShow("lower")
    Paint(1005)
    assert(Word(P().num) == "~25", "shown with the estimate mark: " .. tostring(Word(P().num)))
    NoLog()
""")

case("out_of_combat_the_target_debuff_is_read_and_is_exact", """
    Start("bear")
    W.exists, W.canAttack = true, true
    Cast("Demoralizing Roar", 1000)
    W.targetAuras["Demoralizing Roar"] = { expirationTime = 1000 + 24 }
    Paint(1000.1)
    local _, est = B.RoarLeft(1000.1)
    assert(est, "before the first read (0.3 s after the cast) it is the ledger")
    Paint(1000.4)
    local l
    l, est = B.RoarLeft(1000.4)
    assert(Near(l, 23.6) and not est, "a plain expiry replaces the estimate: " .. l .. " " .. tostring(est))
    assert(Word(P().num) == "24", "no mark: " .. tostring(Word(P().num)))
    -- a readable "not there" ends it, after the grace
    W.targetAuras["Demoralizing Roar"] = nil
    Paint(1002)
    assert(B.RoarLeft(1002) == 0, "the debuff is readably absent: down")
    NoLog()
""")

case("in_combat_nothing_is_read_and_secret_or_friendly_answers_say_nothing", """
    Start("bear")
    W.exists, W.canAttack = true, true
    W.combat = true
    Cast("Demoralizing Roar", 1000)
    W.targetAuras["Demoralizing Roar"] = { expirationTime = 1000 + 5 }
    for t = 1000.5, 1004, 0.5 do Paint(t) end
    local l, est = B.RoarLeft(1004)
    assert(est and Near(l, 26), "in combat only the ledger: " .. l)
    W.combat = false
    W.secretAura = true
    for t = 1005, 1009, 0.5 do Paint(t) end
    l, est = B.RoarLeft(1009)
    assert(est and Near(l, 21), "a secret answer says nothing")
    W.secretAura = false
    W.targetAuras["Demoralizing Roar"] = nil
    W.canAttack, W.canAssist = false, true
    for t = 1010, 1014, 0.5 do Paint(t) end
    assert(B.RoarLeft(1014) > 0, "a friendly target is not read")
    W.canAttack, W.canAssist = true, false
    W.exists = SECRET
    for t = 1015, 1019, 0.5 do Paint(t) end
    assert(B.RoarLeft(1019) > 0, "a secret target answer says nothing")
    NoLog()
""")

case("a_roar_not_learned_draws_nothing_but_thorns_keeps_its_corner", """
    W.known["Demoralizing Roar"] = false
    W.auras["Thorns"] = { expirationTime = 1000 + 300 }
    Start("bear")
    Aura()
    Paint(1000)
    assert(B.RoarKnown() == false and not AnyRoar(), "not learned: no head, no cloud, no arcs, no label")
    assert(AnyThorns(), "Thorns is its own corner")
    W.combat = true
    Paint(1001)
    assert(not AnyRoar(), "not even ROAR in combat")
    W.combat = false
    W.known["Demoralizing Roar"] = true
    fire("SPELLS_CHANGED")
    Paint(1002)
    assert(B.RoarKnown() == true and Hit(P().head), "learned: it appears")
    NoLog()
""")

case("a_cast_makes_the_roar_known_and_an_unreadable_book_keeps_what_we_knew", """
    W.known["Demoralizing Roar"] = false
    Start("bear")
    assert(B.RoarKnown() == false)
    Cast("Demoralizing Roar", 1000)
    assert(B.RoarKnown() == true, "we cast it, so it is known")
    W.secretKnown = true
    fire("SPELLS_CHANGED")
    assert(B.RoarKnown() == true, "a refused read does not forget it")
    NoLog()
""")

case("the_ten_arcs_go_one_per_three_seconds_outer_first_and_the_last_five_are_amber", """
    Start("bear")
    Cast("Demoralizing Roar", 1000)
    Paint(1002.5)
    assert(ArcsUp() == 10, "28 s: all ten (the first is almost gone): " .. ArcsUp())
    Paint(1004)
    assert(ArcsUp() == 9 and not Hit(P().arcB[0]) and Hit(P().arcB[1]), "26 s: the outermost right arc has gone first")
    Paint(1010)
    assert(ArcsUp() == 7, "20 s left: 7")
    for p = 0, 2 do assert(not Hit(P().arcB[p]), "arc " .. p .. " is gone") end
    for p = 3, 9 do assert(Hit(P().arcB[p]), "arc " .. p .. " stands") end
    local side = {}
    for p = 0, 9 do
        local s = Art.sprites["arc_" .. p .. "_b"]
        side[p] = (s[5] + s[3] / 2) > 75 and "R" or "L"
    end
    for p = 0, 9 do assert(side[p] == (p % 2 == 0 and "R" or "L"), "arc " .. p .. " is on the " .. side[p]) end
    local r0, r8 = Art.sprites["arc_0_b"], Art.sprites["arc_8_b"]
    assert(r0[4] > r8[4], "the outer arc is the longer one")
    local c1 = P().arcB[3].color
    assert(c1[1] > 0.9 and c1[2] < 0.5, "ROAR orange while it runs")
    Paint(1027)
    assert(ArcsUp() == 1 and Hit(P().arcB[9]), "3 s: one left")
    local ca = P().arcA[9].color
    assert(ca[1] > 0.9 and ca[2] > 0.65 and ca[2] < 0.8 and ca[3] < 0.4, "the arc is amber in the last 5 s: " .. ca[1] .. " " .. ca[2] .. " " .. ca[3])
    local cb = P().arcB[9].color
    assert(cb[1] > 0.9 and cb[2] > 0.65 and cb[3] < 0.7, "and its wave is amber or its highlight: " .. cb[1] .. " " .. cb[2] .. " " .. cb[3])
    local h = P().halo.color
    assert(h[1] > 0.9 and h[2] > 0.65, "the halo is amber too")
    Paint(1031)
    assert(ArcsUp() == 0, "down: no arc")
    NoLog()
""")

case("an_arc_about_to_go_flickers_and_a_roar_lights_the_rings_one_by_one", """
    Start("bear")
    Cast("Demoralizing Roar", 1000)
    local seen = {}
    for k = 0, 20 do Paint(1002.5 + k * 0.011); seen[P().arcB[0].color[4]] = true end
    assert(seen[1] == nil or seen[0.4], "the last third of an arc flickers between full and 0.4")
    local lows, highs = 0, 0
    for k = 0, 40 do Paint(1002.5 + k * 0.013); if P().arcB[0].color[4] < 1 then lows = lows + 1 else highs = highs + 1 end end
    assert(lows > 3 and highs > 3, "both: " .. lows .. " / " .. highs)
    -- ring by ring after the cast, the inner pair (arcs 8 and 9) first and the outer pair (0 and 1) last, at 0.2 + 0.08 s a ring
    Cast("Demoralizing Roar", 2000)
    Paint(2000.05)
    assert(ArcsUp() == 0, "0.05 s: nothing lit yet")
    Paint(2000.22)
    assert(ArcsUp() == 2 and Hit(P().arcB[8]) and Hit(P().arcB[9]) and not Hit(P().arcB[0]), "0.22 s: only the inner pair is lit: " .. ArcsUp())
    Paint(2000.4)
    assert(ArcsUp() == 6 and Hit(P().arcB[4]) and not Hit(P().arcB[2]), "0.4 s: three rings: " .. ArcsUp())
    Paint(2000.6)
    assert(ArcsUp() == 10, "0.6 s: all ten: " .. ArcsUp())
    NoLog()
""")

case("down_in_combat_is_a_shut_grey_bear_the_still_cloud_and_roar", """
    W.combat = true
    Start("bear")
    Paint(1000)
    local p = P()
    assert(Name(p.head) == "head_dim_combat", "the greyed bear: " .. tostring(Name(p.head)))
    assert(Name(p.aura) == "aura_0" and Hit(p.aura), "the cloud stands still on its first frame")
    assert(not Hit(p.light) and not Hit(p.bolt) and not Hit(p.halo) and ArcsUp() == 0, "no light, no halo, no arcs")
    assert(Word(p.word) == "ROAR" and not Hit(p.num), "ROAR")
    local seen = {}
    for k = 0, 40 do Paint(1000 + k * 0.05); seen[p.word.fsA] = true end
    local n = 0 for _ in pairs(seen) do n = n + 1 end
    assert(n > 3, "ROAR pulses: " .. n .. " alphas")
    assert(Hit(p.eye[1].centre) and p.eye[1].centre.color[1] > 0.9 and p.eye[1].centre.color[3] < 0.4, "an amber eye pulse")
    assert(not Hit(p.eye[1].side[1]) and Streaks() == 0, "no glow, no flare")
    NoLog()
""")

case("down_out_of_combat_rests_dim_with_no_cloud_and_no_word", """
    Start("bear")
    Paint(1000)
    local p = P()
    assert(Name(p.head) == "head_dim_ooc", "the dim bear: " .. tostring(Name(p.head)))
    assert(not Hit(p.aura) and not Hit(p.light) and not Hit(p.bolt), "no cloud")
    assert(not Hit(p.word) and not Hit(p.num) and ArcsUp() == 0 and not Hit(p.eye[1].centre), "no word, no arcs, no eyes")
    NoLog()
""")

case("running_shows_the_seconds_amber_in_the_last_five_and_the_snarl_breathes", """
    Start("bear")
    Cast("Demoralizing Roar", 1000)
    Paint(1009)
    local p = P()
    assert(Word(p.num) == "~21", "21 s, an estimate: " .. tostring(Word(p.num)))
    assert(p.num.fsCol[1] < 0.9 and p.num.fsCol[3] > 0.9, "violet while it runs")
    local frames = {}
    for k = 0, 400 do Paint(1009 + k * 0.02); frames[Name(p.head)] = true end
    for _, f in ipairs({ "head_rest", "head_k11", "head_k12", "head_k13" }) do assert(frames[f], "the jaw breathes through " .. f) end
    assert(not frames.head_open and not frames.head_mid, "the roar frames only on the cast")
    assert(Hit(p.aura) and Name(p.aura):match("^aura_%d+$"), "the cloud")
    local seen = {}
    for k = 0, 200 do Paint(1009 + k * 0.1); seen[Name(p.aura)] = true end
    local n = 0 for _ in pairs(seen) do n = n + 1 end
    assert(n == Art.AURA_FRAMES, "the cloud loops through every frame: " .. n)
    Paint(1026)
    assert(Word(p.num) == "~4" and p.num.fsCol[1] > 0.9 and p.num.fsCol[3] < 0.4, "amber for the last 5 s")
    local e = p.eye[1].centre.color
    assert(e[1] > 0.9 and e[2] > 0.65 and e[3] < 0.5, "the eyes go amber")
    assert(Hit(p.halo) and p.halo.color[2] > 0.65, "and the halo")
    NoLog()
""")

case("the_roar_snaps_the_jaw_open_lunges_the_head_and_flares_the_eyes", """
    Start("bear")
    local p = P()
    RoarAt(5000, 0.03)
    assert(Name(p.head) == "head_mid", "0.03 s: the jaw halfway: " .. tostring(Name(p.head)))
    RoarAt(5100, 0.5)
    assert(Name(p.head) == "head_open", "0.5 s: the full roar")
    RoarAt(5200, 0.95)
    assert(Name(p.head) == "head_mid", "0.95 s: closing")
    RoarAt(5300, 1.2)
    assert(Name(p.head) == "head_rest" or Name(p.head):match("^head_k1%d$"), "1.2 s: the snarl: " .. tostring(Name(p.head)))
    -- lunge: up 3 px at 0.08 s, back by 0.5 s
    RoarAt(5400, 0.08); assert(p.head.parent.fsY == 0, "0.08 s: 3 px up: " .. tostring(p.head.parent.fsY))
    RoarAt(5500, 0.3); assert(p.head.parent.fsY == 2, "0.3 s: coming back: " .. tostring(p.head.parent.fsY))
    RoarAt(5600, 0.6); assert(p.head.parent.fsY == 3 or p.head.parent.fsY == 2, "0.6 s: nearly down: " .. tostring(p.head.parent.fsY))
    -- the eyes: a white centre and four streaks a side at the start, none after 0.4 s
    RoarAt(5700, 0.1)
    local e = p.eye[1]
    assert(e.centre.color[1] > 0.99 and e.centre.color[3] > 0.99, "the eye flares white")
    assert(Streaks() == 16, "four streaks a side, both eyes: " .. Streaks())
    local a1, a4 = e.streak[1][1].color[4], e.streak[4][1].color[4]
    assert(a1 > a4 and a4 > 0, "the streaks fade outward: " .. a1 .. " " .. a4)
    RoarAt(5800, 0.45)
    assert(Streaks() == 0 and e.centre.color[3] < 0.9, "0.45 s: pink again, no streaks")
    NoLog()
""")

case("the_side_glows_are_dithered_on_the_pages_even_pixels", """
    Start("bear")
    local p = P()
    -- a roar lifts the head by a whole number of px each tick; the two eyes alternate as the page's parity does
    local drawn = {}
    for k = 0, 80 do
        RoarAt(6000 + k * 10, 0.01 * k)
        local hy = p.head.parent.fsY
        local l, r = Hit(p.eye[1].side[1]), Hit(p.eye[2].side[1])
        assert(l ~= r, "one eye's glow draws and the other's does not (hy " .. hy .. ")")
        assert(l == ((43 + 23 - 1 + hy + 13) % 2 == 0), "the page's parity for the left eye at hy " .. hy)
        drawn[hy] = true
    end
    NoLog()
""")

case("the_roar_shakes_the_module_for_four_tenths_and_throws_shock_rings", """
    Start("bear")
    local p = P()
    local shk = p.head.parent.parent
    RoarAt(7000, 0.1)
    assert(shk.fsDX == 1 and shk.fsDY == 1, "0.1 s: the page's jolt (" .. tostring(shk.fsDX) .. ", " .. tostring(shk.fsDY) .. ")")
    local moved = false
    for k = 0, 12 do RoarAt(7100 + k * 10, k * 0.03); if shk.fsDX ~= 0 or shk.fsDY ~= 0 then moved = true end end
    assert(moved, "it jolts")
    RoarAt(7300, 0.45)
    assert(shk.fsDX == 0 and shk.fsDY == 0, "and settles after 0.4 s")
    -- the rings: three, each 0.1 s behind the one before; the first white, the others ROAR
    RoarAt(7400, 0.19)
    assert(Name(p.ring[1]) == "ring_5" and Name(p.ring[2]) == "ring_2" and not Hit(p.ring[3]), "0.19 s: two rings: " ..
        tostring(Name(p.ring[1])) .. " " .. tostring(Name(p.ring[2])))
    assert(p.ring[1].color[2] > 0.99 and p.ring[2].color[2] < 0.5, "white, then ROAR orange")
    RoarAt(7500, 0.5)
    assert(Hit(p.ring[1]) and Hit(p.ring[2]) and Hit(p.ring[3]), "0.5 s: all three")
    RoarAt(7600, 0.7)
    assert(not Hit(p.ring[1]) and Hit(p.ring[3]), "0.7 s: the first is out, the last still goes")
    RoarAt(7700, 0.95)
    assert(not Hit(p.ring[1]) and not Hit(p.ring[2]) and not Hit(p.ring[3]), "0.95 s: no rings")
    NoLog()
""")

case("lightning_forks_through_the_cloud_on_the_roar_and_flickers_now_and_then", """
    Start("bear")
    local p = P()
    RoarAt(8000, 0.03)
    assert(Name(p.light) and Name(p.light):match("^light35_") and p.light.color[4] == 1, "the cast's flash at full: " .. tostring(Name(p.light)))
    assert(Name(p.bolt) == "bolt35" and p.bolt.color[4] == 1, "and its bolt")
    RoarAt(8100, 0.3)
    assert(Hit(p.light) and p.light.color[4] < 1 and p.light.color[4] > 0.4, "it fades: " .. p.light.color[4])
    RoarAt(8200, 0.53)
    assert(Hit(p.light) and not Hit(p.bolt), "a weak flash has no bolt (under 0.15)")
    -- the idle flicker: every 5.3 s for 0.25 s, from the right; none while the roar is down
    local t = 5.3 * 400 + 0.05
    Cast("Demoralizing Roar", t - 20)
    Paint(t)
    assert(Name(p.light) and Name(p.light):match("^light121_") and Name(p.bolt) == "bolt121", "the flicker is the right bolt")
    Paint(t + 0.3)
    assert(not Hit(p.light) and not Hit(p.bolt), "and is over")
    Paint(t + 40)
    assert(not Hit(p.light) and not Hit(p.bolt), "down: none")
    NoLog()
""")

case("thorns_corner_is_a_segment_per_minute_and_the_seconds_in_the_last", """
    W.auras["Thorns"] = { expirationTime = 1000 + 265 }
    Start("bear")
    Aura()
    Paint(1000)
    local live, amber, dry = Segs()
    assert(live == 5 and amber == 0 and dry == 5, "265 s: 5 minutes left: " .. live .. "/" .. amber .. "/" .. dry)
    assert(Name(P().thSeg[1]) == "th_seg_0_live" and Name(P().thSeg[6]) == "th_seg_5_dry", "clockwise from 12 o'clock")
    assert(Word(P().thText) == "5M" and not Hit(P().thGhost) and not Hit(P().thWord), "the minutes: " .. tostring(Word(P().thText)))
    W.auras["Thorns"] = { expirationTime = 1000 + 40 }
    Aura(); Paint(1001)
    live, amber, dry = Segs()
    assert(live == 0 and amber == 1 and dry == 9, "the last minute: one amber segment: " .. live .. "/" .. amber .. "/" .. dry)
    assert(Word(P().thText) == "39S" and P().thText.fsCol[1] > 0.9 and P().thText.fsCol[3] < 0.5, "seconds, amber")
    local seen = {}
    for k = 0, 40 do Paint(1001 + k * 0.025); seen[P().thSeg[1].color[4]] = true end
    local n = 0 for _ in pairs(seen) do n = n + 1 end
    assert(n > 3, "the amber segment pulses")
    assert(P().thSeg[2].color[4] == 1, "a dry segment does not")
    NoLog()
""")

case("thorns_cast_in_combat_is_a_ledger_with_a_mark", """
    W.combat = true
    Start("bear")
    assert(St.Thorns(1000) == "unknown" and not AnyThorns(), "a reload in combat: unknown, nothing drawn")
    Cast("Thorns", 1000)
    Paint(1001)
    local live, amber, dry = Segs()
    assert(live == 10 and dry == 0, "fresh: ten segments: " .. live)
    assert(Word(P().thText) == "~10M", "the estimate mark: " .. tostring(Word(P().thText)))
    Paint(1000 + 601)
    assert(not AnyThorns(), "run out in combat: nothing")
    NoLog()
""")

case("thorns_gone_is_a_reminder_out_of_combat_only_and_not_learned_draws_nothing", """
    Start("bear")
    Aura()
    Paint(1000)
    assert(St.Thorns(1000) == "gone")
    assert(Hit(P().thGhost) and Word(P().thWord) == "THORNS" and not Hit(P().thText) and Segs() == 0, "the dashed ring and THORNS")
    assert(P().thWord.fsCol[1] > 0.9 and P().thWord.fsCol[3] < 0.5, "amber")
    W.combat = true
    fire("PLAYER_REGEN_DISABLED")
    Paint(1001)
    assert(not AnyThorns(), "in combat nothing is drawn")
    W.combat = false
    W.known["Thorns"] = false
    fire("SPELLS_CHANGED")
    Paint(1002)
    assert(not AnyThorns(), "not learned: no reminder: " .. tostring(B.ThornsKnown()))
    NoLog()
""")

case("reduced_motion_holds_the_scene_but_the_jaw_still_opens_on_the_cast", """
    ForeverSTUwaveDB = { reducedMotion = true }
    FS.ReducedMotion = function() return true end
    Start("bear")
    M.data.reduced = true
    local p = P()
    RoarAt(9000, 0.03)
    M.data.reduced = true
    Paint(9000.03)
    assert(Name(p.head) == "head_mid", "the jaw still opens")
    local shk = p.head.parent.parent
    assert(shk.fsDX == 0 and shk.fsDY == 0, "no shake")
    assert(not Hit(p.light) and not Hit(p.bolt) and not Hit(p.ring[1]) and Streaks() == 0, "no flash, bolt, rings or flare")
    assert(p.head.parent.fsY == 3, "no lunge")
    assert(Name(p.aura) == "aura_0", "a still cloud")
    local frames = {}
    for k = 0, 200 do Paint(9003 + k * 0.05); frames[Name(p.head)] = true end
    assert(frames.head_rest and not frames.head_k11 and not frames.head_k12, "no breathing")
    assert(Word(p.num) ~= nil and ArcsUp() > 0, "the time is still told")
    NoLog()
""")

case("every_value_secret_at_once_draws_without_an_error", """
    Start("bear")
    Cast("Demoralizing Roar", 1000)
    W.secretPower, W.secretName, W.secretLevel, W.secretCd, W.secretForm, W.secretAura, W.secretKnown = true, true, true, true, true, true, true
    W.exists, W.canAttack, W.canAssist = SECRET, SECRET, SECRET
    for _, combat in ipairs({ false, true }) do
        W.combat = combat
        for t = 1001, 1040, 0.37 do Paint(t) end
        fire("UNIT_AURA", "player"); fire("SPELLS_CHANGED"); fire("PLAYER_TARGET_CHANGED")
        for t = 1041, 1050, 0.37 do Paint(t) end
    end
    NoLog()
""")

case("a_rescale_resizes_and_reseats_every_region", """
    Start("bear")
    Cast("Demoralizing Roar", 1000)
    Paint(1010)
    local p = P()
    local w1, h1 = p.head.w, p.head.h
    local x1 = p.arcB[4].px
    __scale = 2
    SPEC.seat({ x = 0, y = 0, w = 200, h = 128 })
    Paint(1010.1)
    assert(Near(p.head.w, w1 * 2) and Near(p.head.h, h1 * 2), "the head doubles: " .. p.head.w)
    assert(Near(p.arcB[4].px, x1 * 2), "the arcs move with it")
    assert(p.num.size == 9 * 1.25 * 2, "the font follows: " .. tostring(p.num.size))
    __scale = 1
    NoLog()
""")

case("the_paint_allocates_nothing_once_warm", """
    local function quiet()
        for _, o in ipairs(__all) do
            o.SetPoint = function(self, p, rel, rp, x, y) self.px, self.py = x, y end
            o.SetTexCoord = function(self, l, r, t, b) self.tl = l end
            o.SetVertexColor = function(self, r, g, b, a) self.ca = a end
            o.SetText = function() end
            o.SetFormattedText = function() end
            o.SetTextColor = function() end
            o.SetShadowColor = function() end
            o.SetShadowOffset = function() end
        end
    end
    local function run(label, setup)
        setup()
        quiet()
        if jit then jit.off() end
        local t0 = 100000
        local function cycle(base)
            for i = 0, 400 do Paint(base + i * 0.033) end
        end
        cycle(t0)
        collectgarbage("collect")
        collectgarbage("stop")
        local before = collectgarbage("count")
        for pass = 1, 10 do cycle(t0 + pass * 14) end
        local grew = collectgarbage("count") - before
        collectgarbage("restart")
        assert(grew < 2, label .. ": the paint allocated " .. grew .. " KB over 4010 paints")
    end
    W.auras["Thorns"] = { expirationTime = 100000 + 700 }
    Start("bear")
    Aura()
    -- the roar cast just before the measured window: the whole anim, the running look, the last 5 s and the down look follow
    run("roar then down, in combat", function() W.combat = true; Cast("Demoralizing Roar", 100000 - 0.001) end)
    run("down out of combat, Thorns gone", function() W.combat = false; W.auras["Thorns"] = nil; Aura() end)
    run("roar out of combat, Thorns last minute", function()
        W.auras["Thorns"] = { expirationTime = 100000 + 3000 }; Aura()
        Cast("Demoralizing Roar", 100000 - 0.001)
    end)
    NoLog()
""")

CASE_COUNT = len(CASES)


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
IsPlayerSpell = function() return true end
C_Spell = C_Spell or {}
C_Spell.GetSpellInfo = function(name) return { spellID = 9898, iconID = 1 } end
loadAddonFile(AREAS_SRC, "Modules/CombatHud/GunsightAreas.lua")
UnitClass = function() return "Druid", "DRUID" end
loadAddonFile(DRUIDART_SRC, "Modules/CombatHud/DruidArt.lua")
loadAddonFile(STATE_SRC, "Modules/CombatHud/DruidState.lua")
loadAddonFile(DRUID_SRC, "Modules/CombatHud/GunsightDruid.lua")
loadAddonFile(BEARART_SRC, "Modules/CombatHud/DruidBearArt.lua")
loadAddonFile(MODULE_SRC, "Modules/CombatHud/GunsightDruidBear.lua")
fire("ADDON_LOADED", "forever-stuwave")
fire("PLAYER_LOGIN")

local host = FS.GunsightAreas.Host("lower")
check(host, "the real areas hand out a lower host")
local Bear = FS.GunsightDruidBear
check(Bear and Bear.frame, "the look is built with the module")
check(isVisible(host) and isVisible(Bear.frame), "a target shows the host and the look under it")
check(onUpdateFrames() == 1, "ticking: " .. onUpdateFrames())
local P = Bear.parts
local function shown(t) return t.fsOn == true and isVisible(t) end
function Hit_name(t) return t.fsName end
check(shown(P.head) and Hit_name(P.head) == "head_dim_ooc" and not shown(P.aura), "a learned roar that is down draws the dim bear and no cloud")
check(Bear.RoarKnown() == true, "the real spellbook helpers read it as known")
TARGET.exists = false
fire("PLAYER_TARGET_CHANGED")
check(not isVisible(host) and not isVisible(Bear.frame) and not isVisible(P.head), "no target hides the host and the look under it")
check(onUpdateFrames() == 0, "and stops the OnUpdate")
TARGET.exists = true
fire("PLAYER_TARGET_CHANGED")
check(isVisible(host) and isVisible(Bear.frame), "a target brings it back")
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
    g.DRUIDART_SRC, g.STATE_SRC, g.DRUID_SRC, g.BEARART_SRC, g.MODULE_SRC = DRUIDART, STATE, DRUID, ARTLUA, MODULE
    g.HAS_TARGET_SRC = gs.theme_target_rule_lua()
    try:
        lua.execute(REAL_CASE)
    except LuaError as e:
        return str(e)
    return None


def new_runtime():
    rt = LuaRuntime(unpack_returned_tuples=False)
    g = rt.globals()
    g.DRUIDART_SRC, g.STATE_SRC, g.DRUID_SRC, g.BEARART_SRC, g.MODULE_SRC = DRUIDART, STATE, DRUID, ARTLUA, MODULE
    rt.execute(MOCK)
    return rt


def run_case(body: str) -> str | None:
    rt = new_runtime()
    try:
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


# ----------------------------------------------------------------------------------------------------------------------
# Static checks
# ----------------------------------------------------------------------------------------------------------------------
def mockup_pins() -> list[str] | None:
    """The numbers the look shares with the approved page, pinned against the page's own source."""
    if not MOCKUP.exists():
        # check.py's rule: with no mockups/ and no FS_MOCKUPS_DIR (a public clone) the page cannot be read and the pins are skipped;
        # with either present a missing page is a real failure.
        if (ROOT / "mockups").exists() or os.environ.get("FS_MOCKUPS_DIR"):
            return [f"the approved mockup is missing: {MOCKUP}"]
        print("skip  the mockup pins: no mockups/ in this checkout")
        return None
    page = MOCKUP.read_text(encoding="utf-8")
    errs: list[str] = []
    want = {
        "the eye points on the 64 px sprite": "const EYES=[[23,13],[40,13]];",
        "ten pieces of 3 s, outer first": "const hi=30-3*p, lo=27-3*p",
        "the ring and side of a piece": "ring=j>>1, side=(j&1)?1:-1, r=35+ring*4.2",
        "the ring by ring lighting": "if(ca<.2+ring*.08) continue;",
        "the wave": "const wave=.5+.5*Math.sin(st.now*7-ring*1.2)",
        "the jaw frame times": "fr = ca<.05 ? 'mid' : ca<.9 ? 'open' : ca<1.02 ? 'mid' : 'rest';",
        "the breath frames": "fr = b>.75 ? 'k11' : b>.25 ? 'k12' : b>-.25 ? 'k13' : 'rest'",
        "the lunge": "lift = ca<.08 ? -3*ca/.08 : ca<.5 ? -3*(1-(ca-.08)/.42) : (Math.sin(st.now*2.2)>.3?-1:0);",
        "the head's place": "const bxp=Math.round(cx-32), byp=Math.round(cy-31+lift);",
        "the halo": "halo(g,cx,cy,18,40,low?AMBER:'#ff3aa0'",
        "the shake": "if(st.castAge<.4){ const d=1-st.castAge/.4;",
        "the eyes' flare": "const fl = ca<.4 ? 1-ca/.4 : 0, pu=.5+.5*Math.sin(st.now*3), ec = low?AMBER:'#ff4ab8';",
        "the shock rings": "const kk=clamp((ca-s*.1)/.6,0,1); if(kk<=0||kk>=1) continue; const r=20+kk*70;",
        "the cast's flash": "flash = ca<.08 ? 1 : Math.max(0,1-(ca-.08)/.5); bx=CX-40;",
        "the idle flicker": "const ph=(st.now%5.3); if(ph<.25){ flash=.5*(1-ph/.25)*(Math.sin(ph*80)>0?1:.4); bx=CX+46;",
        "the label places": "const lx=down?CX:CX+44, ly=down?LABEL_Y+4:LABEL_Y-2;",
        "the canvas and the head's centre": "const W=150, H=86, CX=75, CY=36, LABEL_Y=74;",
    }
    squashed = re.sub(r"\s+", " ", page)
    for what, snippet in want.items():
        if re.sub(r"\s+", " ", snippet) not in squashed:
            # the page writes some of these a little differently; accept a copy with the spaces removed
            if re.sub(r"\s+", "", snippet) not in re.sub(r"\s+", "", page):
                errs.append(f"the mockup no longer says {what}: {snippet}")
    return errs


def lua_const_pins() -> list[str]:
    """The module's own numbers against the page's (a Lua run of the module's table)."""
    rt = new_runtime()
    out = rt.eval("""function()
        local C = FS.GunsightDruidBear.C
        local errs = {}
        local function eq(a, b, what) if a ~= b then errs[#errs + 1] = what .. ": " .. tostring(a) .. " vs " .. tostring(b) end end
        eq(C.SW, 150, "canvas width"); eq(C.SH, 86, "canvas height")
        eq(C.HX, 75 - 32, "head left"); eq(C.HCY - 31, 3, "head top")
        eq(C.NUM_X, 75 + 44, "number x"); eq(C.WORD_X, 75, "word x")
        eq(C.ROAR_S, 30, "roar seconds"); eq(C.PIECE_S, 3, "arc seconds"); eq(C.WARN_S, 5, "amber seconds")
        eq(C.ROAR_LEN, 1.02, "roar jaw length")
        eq(FS.DruidBearArt.GW, 150, "art canvas"); eq(FS.DruidBearArt.CX, 75, "art cx")
        return table.concat(errs, "; ")
    end""")()
    return [str(out)] if out else []


def static_checks() -> list[str]:
    errs: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, FS_ASSET_OUTPUT_DIR=tmp, FS_ART_LUA_OUTPUT=str(Path(tmp) / "DruidBearArt.lua"))
        run = subprocess.run([sys.executable, str(GENERATOR)], env=env, capture_output=True, text=True)
        if run.returncode != 0:
            return [f"the generator failed: {run.stderr.strip()[-400:]}"]
        if (Path(tmp) / "DruidBearArt.lua").read_text(encoding="utf-8") != ARTLUA:
            errs.append("DruidBearArt.lua differs from the generator's (run tools/assets/generate_druid_bear.py)")
        mine = MEDIA / "druid_bear_1.tga"
        if not mine.exists():
            errs.append("missing texture druid_bear_1.tga")
        elif mine.read_bytes() != (Path(tmp) / "druid_bear_1.tga").read_bytes():
            errs.append("druid_bear_1.tga differs from the generator's")
    if (MEDIA / "druid_bear_1.tga").exists():
        head = (MEDIA / "druid_bear_1.tga").read_bytes()[:18]
        w, h = struct.unpack_from("<HH", head, 12)
        if w & (w - 1) or h & (h - 1):
            errs.append(f"druid_bear_1.tga is {w}x{h}: not powers of two")
    toc = [line.strip() for line in (ADDON / "forever-stuwave.toc").read_text(encoding="utf-8").splitlines()]
    order = ["Modules/CombatHud/GunsightDruid.lua", "Modules/CombatHud/DruidBearArt.lua", "Modules/CombatHud/GunsightDruidBear.lua"]
    if any(o not in toc for o in order) or [toc.index(o) for o in order] != sorted(toc.index(o) for o in order):
        errs.append("the toc must load GunsightDruid, DruidBearArt, GunsightDruidBear in that order")
    for path in (CH / "GunsightDruidBear.lua", ARTLUA_PATH, GENERATOR, Path(__file__)):
        text = path.read_text(encoding="utf-8")
        if re.search("[" + chr(0x2013) + chr(0x2014) + "]", text):
            errs.append(f"{path.name} has an em or en dash")
    for path in (CH / "GunsightDruidBear.lua", ARTLUA_PATH):
        if re.search(r"(?i)\bbots?\b|automat|macro", path.read_text(encoding="utf-8")):
            errs.append(f"{path.name} names something the client must not see")
    errs += lua_const_pins()
    return errs


# ----------------------------------------------------------------------------------------------------------------------
# The picture: the real module's regions composited from the baked atlas
# ----------------------------------------------------------------------------------------------------------------------
def atlas_image():
    import numpy as np
    from PIL import Image
    return np.asarray(Image.open(MEDIA / "druid_bear_1.tga").convert("RGBA")).astype(float)


def compose(rows, atlas, zoom=4, text=True, ground=BG):
    """The canvas (150 x 86 sprite px, `zoom` px each) with every row composited in order, texture rows from the atlas."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    gw, gh = 150, 86
    canvas = np.zeros((gh, gw, 3)) + np.array(ground, float)
    aw, ah = atlas.shape[1], atlas.shape[0]
    for r in rows:
        if r["kind"] != "Texture":
            continue
        if r["l"] is None:                         # a flat dot
            sx, sy, sw, sh = round(r["x"] / SPX), round(r["y"] / SPX), max(1, round(r["w"] / SPX)), max(1, round(r["h"] / SPX))
            src = np.zeros((sh, sw, 4)) + np.array([255, 255, 255, 255.0])
        else:
            tx, ty = round(r["l"] * aw), round(r["t"] * ah)
            sw, sh = round((r["r"] - r["l"]) * aw), round((r["b"] - r["t"]) * ah)
            sx, sy = round(r["x"] / SPX), round(r["y"] / SPX)
            src = atlas[ty:ty + sh, tx:tx + sw].copy()
        src[..., 0] *= r["cr"]
        src[..., 1] *= r["cg"]
        src[..., 2] *= r["cb"]
        src[..., 3] *= r["ca"]
        x0, y0, x1, y1 = max(sx, 0), max(sy, 0), min(sx + sw, gw), min(sy + sh, gh)
        if x1 <= x0 or y1 <= y0:
            continue
        s = src[y0 - sy:y1 - sy, x0 - sx:x1 - sx]
        a = s[..., 3:4] / 255
        canvas[y0:y1, x0:x1] = s[..., :3] * a + canvas[y0:y1, x0:x1] * (1 - a)
    img = Image.fromarray(canvas.round().clip(0, 255).astype("uint8")).resize((gw * zoom, gh * zoom), Image.NEAREST)
    if text:
        draw = ImageDraw.Draw(img)
        font_file = ADDON / "Media/Fonts/MononokiNerdFontMono-Bold.ttf"
        for r in rows:
            if r["kind"] != "FontString" or not r.get("text"):
                continue
            size = max(6, round(r["size"] / SPX * zoom))
            font = ImageFont.truetype(str(font_file), size)
            cx, cy = r["x"] / SPX * zoom, r["y"] / SPX * zoom
            for dx, dy in ((zoom, zoom), (0, zoom), (zoom, 0)):
                draw.text((cx + dx, cy + dy), r["text"], font=font, fill=(4, 4, 12), anchor="mm")
            col = tuple(round(255 * (r.get(k) or 0)) for k in ("tr", "tg", "tb"))
            draw.text((cx, cy), r["text"], font=font, fill=col, anchor="mm")
    return img


ROAR_SHEET = [
    ("roar 0.03 s", "Cast('Demoralizing Roar', 5000); Paint(5000.03)"), ("roar 0.12 s", "Cast('Demoralizing Roar', 5000); Paint(5000.12)"),
    ("roar 0.30 s", "Cast('Demoralizing Roar', 5000); Paint(5000.30)"), ("roar 0.60 s", "Cast('Demoralizing Roar', 5000); Paint(5000.60)"),
    ("roar 1.00 s", "Cast('Demoralizing Roar', 5000); Paint(5001.00)"), ("21 s, snarling", "Cast('Demoralizing Roar', 5000); Paint(5009)"),
    ("12 s", "Cast('Demoralizing Roar', 5000); Paint(5018)"), ("last 5 s", "Cast('Demoralizing Roar', 5000); Paint(5026)"),
    ("down, in combat", "W.combat = true; Paint(5100)"), ("down, out of combat", "W.combat = false; Paint(5100)"),
]
THORNS_SHEET = [
    ("10 min, in combat (ledger)", "W.combat = true; Cast('Thorns', 5000); Paint(5001)"),
    ("5 min", "W.combat = false; W.auras['Thorns'] = { expirationTime = 5000 + 265 }; Aura(); Paint(5000)"),
    ("2 min", "W.combat = false; W.auras['Thorns'] = { expirationTime = 5000 + 100 }; Aura(); Paint(5000)"),
    ("last minute, amber", "W.combat = false; W.auras['Thorns'] = { expirationTime = 5000 + 40 }; Aura(); Paint(5000.2)"),
    ("gone, out of combat", "W.combat = false; W.auras['Thorns'] = nil; Aura(); Paint(5000.2)"),
]


def sheet(name: str, states, prefix: str, with_roar: bool) -> None:
    from PIL import Image, ImageDraw
    atlas = atlas_image()
    cols = 3
    rows_n = (len(states) + cols - 1) // cols
    zoom = 4
    img = Image.new("RGB", (cols * 150 * zoom, rows_n * (86 * zoom + 18)), (30, 20, 50))
    draw = ImageDraw.Draw(img)
    for n, (cap, code) in enumerate(states):
        rt = new_runtime()
        rt.execute("W.known['Thorns'] = true; Start('bear'); __now = 5000")
        if not with_roar:
            rt.execute("W.known['Demoralizing Roar'] = false; fire('SPELLS_CHANGED')")
        rt.execute(code)
        rows = rt.eval("Dump")()
        rows = [{k: rows[i][k] for k in ("kind", "tex", "l", "r", "t", "b", "w", "h", "x", "y", "cr", "cg", "cb", "ca", "text", "size",
                                          "tr", "tg", "tb", "ta")} for i in range(1, len(rows) + 1)]
        tile = compose(rows, atlas, zoom)
        x, y = (n % cols) * 150 * zoom, (n // cols) * (86 * zoom + 18)
        img.paste(tile, (x, y + 16))
        draw.text((x + 4, y + 2), cap, fill=(200, 190, 230))
    out = f"{prefix}-{name}.png"
    img.save(out)
    print("wrote", out)


def png(prefix: str) -> None:
    sheet("roar", ROAR_SHEET, prefix, True)
    sheet("thorns", THORNS_SHEET, prefix, False)


def main() -> int:
    failures = 0
    for err in static_checks():
        failures += 1
        print(f"FAIL  static: {err}")
    pins = mockup_pins()
    for err in pins or []:
        failures += 1
        print(f"FAIL  mockup: {err}")
    if pins == []:
        print("ok    the_numbers_the_look_shares_with_the_approved_page_are_the_pages")
    for name, body in CASES:
        err = run_case(body)
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}: {err}")
    err = run_real_case()
    name = "under_the_real_areas_the_host_follows_the_target_and_the_look_stops_with_it"
    if err is None:
        print(f"ok    {name}")
    else:
        failures += 1
        print(f"FAIL  {name}: {err}")
    total = len(CASES) + 2
    print(f"{total - min(failures, total)}/{total} checks passed")
    if "--png" in sys.argv:
        prefix = sys.argv[sys.argv.index("--png") + 1]
        Path(prefix).parent.mkdir(parents=True, exist_ok=True)
        png(prefix)
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
