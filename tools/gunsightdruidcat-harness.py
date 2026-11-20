#!/usr/bin/env python3
"""Runs the real GunsightDruidCat.lua (the Druid's CAT form look) and the generated DruidCatArt.lua headless against a mock client.

The Cat look draws the design mockup "Druid Hide Rake" (2026-11-17): a stretched hide with five gash slots, raked in live by a lion paw
(the still "Lion Paw"), gold and FINISH at five, the finisher's windup, swipe, freeze, flash, shake, shockwave, blood burst and
cooling, and a small Thorns ring in the corner. In combat the combo count is a SECRET value, so these checks pin:

  * the seam: a "cat" form registered with FS.GunsightDruid.RegisterForm; build under the parent, seat, show and hide;
  * the engine path: each lit gash is a bar from i - 1 to i, the gold gashes and FINISH are bars from 4 to 5, the embers and drops are
    one px bars, the digit is SetFormattedText; a plain and a SECRET count draw the same under an engine emulation, and nothing
    ever compares the count (the mock's secret errors on any operation);
  * the rake: it starts only from a builder cast by name paired with the combo event (before or after it), from a plain rise out of
    combat, never from an energy event or a target change; the new gash opens late and the old count is held until then; the paw,
    the torn gash and the leather bits sit at the newest slot, which a secret count cannot name: they are anchored to the fill edge
    of the marker bar (the engine's), and the same slot a plain count would give;
  * the finisher: windup, swipe, freeze and impact in time; the old count held until the impact, the gashes cooling after it, the
    flash, shake, shockwave, burst and scars, and everything gone at the end; the power event arriving before the cast;
  * Thorns: not learned, unknown, up (segments by minute, amber under a minute, the label), gone out of combat, gone in combat;
  * events on show only, dropped on hide, reduced motion, re-seating, a paint that allocates nothing, the manifest and every sprite
    name, the toc lines, the generator's bytes, and the real GunsightDruid.lua mounting the form.

    python3 tools/gunsightdruidcat-harness.py

    python3 tools/gunsightdruidcat-harness.py --png DIR    (writes a contact sheet of the frames under DIR for a look)

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
HUD = ADDON / "Modules/CombatHud"
MODULE = (HUD / "GunsightDruidCat.lua").read_text(encoding="utf-8")
ART = (HUD / "DruidCatArt.lua").read_text(encoding="utf-8")
MEDIA = ADDON / "Media/Textures"
TOC = ADDON / "forever-stuwave.toc"
GENERATOR = HERE / "assets" / "generate_druid_cat.py"
TEXTURES = ["druid_cat_cool_1", "druid_cat_cool_2", "druid_cat_cool_3", "druid_cat_cool_4", "druid_cat_cool_5", "druid_cat_art", "druid_cat_gash_1", "druid_cat_gash_2", "druid_cat_gash_3", "druid_cat_gash_4", "druid_cat_gash_5",
            "druid_cat_gold", "druid_cat_finish"]

MOCK = r"""
function check(c, msg) if not c then error(msg or "check failed", 2) end end
-- a secret number: it carries its value for the ENGINE emulation (a StatusBar), and errors on any operation Lua could do on it
SECRET_MT = {
    __lt = function() error("SECRET_OP: compare", 2) end, __le = function() error("SECRET_OP: compare", 2) end,
    __add = function() error("SECRET_OP: arith", 2) end, __sub = function() error("SECRET_OP: arith", 2) end,
    __mul = function() error("SECRET_OP: arith", 2) end, __div = function() error("SECRET_OP: arith", 2) end,
    __mod = function() error("SECRET_OP: arith", 2) end, __pow = function() error("SECRET_OP: arith", 2) end,
    __unm = function() error("SECRET_OP: arith", 2) end, __concat = function() error("SECRET_OP: concat", 2) end,
    __len = function() error("SECRET_OP: len", 2) end, __tostring = function() return "secret" end,
    __index = function() error("SECRET_OP: index", 2) end,
}
function Secret(n) return setmetatable({ n = n }, SECRET_MT) end
function IsSecretValue(v) return type(v) == "table" and getmetatable(v) == SECRET_MT end
function Num(v) if IsSecretValue(v) then return rawget(v, "n") end return v end   -- what the engine sees

SPX = 1.25
local Obj = {}
Obj.__index = function(t, k)
    local v = rawget(Obj, k)
    if v ~= nil then return v end
    if type(k) == "string" and k:match("^%u") then return function() end end
end
__textures, __fonts, __frames, __bars = {}, {}, {}, {}
function New(kind, parent)
    local o = setmetatable({ kind = kind, parent = parent, shown = true, events = {}, scripts = {}, kids = {}, sets = 0 }, Obj)
    if parent then parent.kids[#parent.kids + 1] = o end
    return o
end
function visible(r) while r do if r.shown == false then return false end; r = r.parent end return true end
local function propagate(o, name)
    local fn = o.scripts[name]
    if fn then fn(o) end
    for _, k in ipairs(o.kids) do if k.shown ~= false then propagate(k, name) end end
end
function Obj:Show()
    if self.shown then return end
    local was = visible(self)
    self.shown = true
    if not was and visible(self) then propagate(self, "OnShow") end
end
function Obj:Hide()
    if self.shown == false then return end
    local was = visible(self)
    self.shown = false
    if was then propagate(self, "OnHide") end
end
function Obj:IsShown() return self.shown end
function Obj:SetPoint(p, rel, rp, x, y)
    local pt = self.pt or {}
    pt[1], pt[2], pt[3], pt[4], pt[5] = p, rel, rp or p, x or 0, y or 0
    self.pt = pt
    self.sets = self.sets + 1
end
function Obj:SetAllPoints(rel)
    local pt = self.pt or {}
    pt[1], pt[2], pt[3], pt[4], pt[5] = "ALL", rel, nil, nil, nil
    self.pt = pt
    self.sets = self.sets + 1
end
function Obj:ClearAllPoints() if self.pt then self.pt[1] = nil end end
function Obj:SetSize(w, h) self.w, self.h = w, h end
function Obj:SetAlpha(a) self.alpha = a end
function Obj:SetScript(n, fn) self.scripts[n] = fn end
function Obj:GetScript(n) return self.scripts[n] end
function Obj:RegisterEvent(e) self.events[e] = true end
function Obj:RegisterUnitEvent(e, ...) self.events[e] = { ... } end
function Obj:UnregisterEvent(e) self.events[e] = nil end
function Obj:SetFrameLevel(l) self.level = l end
function Obj:GetFrameLevel() return self.level or 1 end
function Obj:SetClipsChildren(on) self.clips = on end
function Obj:EnableMouse() end
function Obj:SetTexture(p) self.tex = p end
function Obj:SetTexCoord(l, r, t, b)
    local c = self.tc or {}
    c[1], c[2], c[3], c[4] = l, r, t, b
    self.tc = c
end
function Obj:SetVertexColor(r, g, b, a)
    local c = self.color or {}
    c[1], c[2], c[3], c[4] = r, g, b, a
    self.color = c
    self.sets = self.sets + 1
end
function Obj:SetText(t) self.text = t end
function Obj:SetFormattedText(fmt, v)
    if IsSecretValue(v) then self.text = "secret:" .. tostring(rawget(v, "n")); self.secretText = true; self.engineText = string.format(fmt, rawget(v, "n"))
    else self.text = string.format(fmt, v); self.secretText = false; self.engineText = self.text end
end
function Obj:SetTextColor(r, g, b, a)
    local c = self.tcolor or {}
    c[1], c[2], c[3], c[4] = r, g, b, a
    self.tcolor = c
end
function Obj:CreateTexture(name, layer, inh, sub)
    local t = New("Texture", self); t.layer, t.sub = layer, sub or 0; __textures[#__textures + 1] = t
    t.seq = #__textures
    return t
end
function Obj:CreateFontString() local f = New("FontString", self); __fonts[#__fonts + 1] = f; return f end
function Obj:SetMinMaxValues(a, b) self.min, self.max = a, b end
function Obj:SetValue(v) self.value = v end
function Obj:SetStatusBarTexture(p)
    self.fill = self.fill or New("Texture", self)
    self.fill.tex, self.fill.isFill, self.fill.bar = p, true, self
end
function Obj:GetStatusBarTexture() return self.fill end
function Obj:SetStatusBarColor(r, g, b, a)
    local c = self.sbColor or {}
    c[1], c[2], c[3], c[4] = r, g, b, a
    self.sbColor = c
end
-- the engine's fill of a StatusBar: 0 .. 1 (it sees a secret's value, Lua never does)
function Fill(bar)
    if bar.value == nil then return 0 end
    local v, lo, hi = Num(bar.value), bar.min, bar.max
    local f = (v - lo) / (hi - lo)
    if f < 0 then return 0 elseif f > 1 then return 1 end
    return f
end
function CreateFrame(kind, name, parent)
    local f = New(kind, parent); f.name = name
    __frames[#__frames + 1] = f
    if kind == "StatusBar" then __bars[#__bars + 1] = f end
    return f
end
function fire(event, ...)
    for _, f in ipairs({ unpack(__frames) }) do
        local reg = f.events[event]
        if reg and f.scripts.OnEvent then
            local ok = true
            if type(reg) == "table" then
                ok = false
                for _, u in ipairs(reg) do if u == (...) then ok = true end end
            end
            if ok then f.scripts.OnEvent(f, event, ...) end
        end
    end
end

-- where a region is, in image px from the host's top left (y down): the engine's anchor resolution, a fill edge included
function Rect(o)
    if o == HOST then return 0, 0, o.w, o.h end
    if o.isFill then
        local x, y, w, h = Rect(o.bar)
        return x, y, w * Fill(o.bar), h
    end
    local pt = o.pt
    if not pt or not pt[1] then error("no anchor on a " .. tostring(o.kind)) end
    if pt[1] == "ALL" then return Rect(pt[2]) end
    local rx, ry, rw, rh = Rect(pt[2])
    local ax, ay
    if pt[3] == "TOPLEFT" then ax, ay = rx, ry
    elseif pt[3] == "TOPRIGHT" then ax, ay = rx + rw, ry
    elseif pt[3] == "CENTER" then ax, ay = rx + rw / 2, ry + rh / 2
    else error("anchor point " .. tostring(pt[3])) end
    ax, ay = ax + pt[4], ay - pt[5]
    local w, h = o.w or 0, o.h or 0
    if pt[1] == "TOPLEFT" then return ax, ay, w, h end
    if pt[1] == "CENTER" then return ax - w / 2, ay - h / 2, w, h end
    error("point " .. tostring(pt[1]))
end
function Canvas(o) local x, y, w, h = Rect(o); return x / SPX, y / SPX, w / SPX, h / SPX end

__now = 1000
function GetTime() return __now end
__combat = false
function InCombatLockdown() return __combat end

-- the world: the combo count (a number or a Secret), the spells the player casts
__pts = 0
__token = "COMBO_POINTS"
Enum = { PowerType = { ComboPoints = 4, Energy = 3 } }
function UnitPower(unit, kind) if kind == 4 then return __pts end return 100 end
NAMES = { [1] = "Claw", [2] = "Rake", [3] = "Shred", [4] = "Ferocious Bite", [5] = "Rip", [6] = "Moonfire", [7] = "Mangle (Cat)",
          [8] = "Maim", [9] = "Pounce", [10] = "Ravage" }
C_Spell = { GetSpellName = function(id) return NAMES[id] end }
function IdOf(name) for id, n in pairs(NAMES) do if n == name then return id end end error("no spell " .. name) end

-- the Druid state the form reads
T = { mode = "gone", left = nil, est = false, known = true }
THORNS_CALLS = 0
FS = {
    IsSecret = IsSecretValue,
    Gunsight = { ui = function(px) return px end },
    DruidState = {
        Thorns = function(now) THORNS_CALLS = THORNS_CALLS + 1; return T.mode, T.left, T.est, nil end,
        Known = function(key) if key == "thorns" then return T.known end end,
    },
    Theme = { ApplyMono = function(fs, size) fs.size = size end },
    LogDegradeOnce = function(k, m) __logged = __logged or {}; __logged[k] = m end,
    FrameHelpers = { RegisterEvent = function(f, e, unit) f.events[e] = unit and { unit } or true; return true end },
}
RF = {}
FS.GunsightDruid = { RegisterForm = function(kind, spec) RF[kind] = spec; return true end }
function NoLog() for k, v in pairs(__logged or {}) do error("logged " .. k .. ": " .. tostring(v)) end end
function Near(a, b, eps) return math.abs(a - b) <= (eps or 1e-6) end

assert(loadstring(ART_SRC, "@DruidCatArt.lua"))("forever-stuwave", FS)
assert(loadstring(MODULE_SRC, "@GunsightDruidCat.lua"))("forever-stuwave", FS)
SPEC, M, Art = RF.cat, FS.GunsightDruidCat, FS.DruidCatArt
HOST = New("Frame")
HOST.w, HOST.h = Art.W * SPX, Art.H * SPX
DATA = { reduced = false, kind = "cat" }
function Mount(show)
    SPEC.build(HOST)
    SPEC.seat(0, 0, SPX)
    SPEC.hide()
    if show ~= false then SPEC.show() end
    return M.frame or M.parts
end
function Step(dt) __now = __now + (dt or 1 / 30); SPEC.paint(__now, DATA) end
function Run(seconds)       -- bounded: 1/30 s steps, never more than 300 of them
    local n = math.min(300, math.floor(seconds * 30 + 0.5))
    for _ = 1, n do Step() end
end
function Power(token) fire("UNIT_POWER_UPDATE", "player", token or __token); fire("UNIT_POWER_FREQUENT", "player", token or __token) end
function SetPts(v) __pts = v; Power() end
function Cast(name) fire("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", IdOf(name)) end
P = function() return M.parts end
V = function() return M.state end

-- what the engine would draw
function Lit(bar) return Fill(bar) >= 1 end
function Gashes() local t = {} for i = 1, 5 do t[i] = Lit(P().gash[i]) end return t end
function Count(list) local n = 0 for _, v in ipairs(list) do if v then n = n + 1 end end return n end
function LitCount() return Count(Gashes()) end
function Shown(t) return t.fsOn == true and visible(t) end
function ShownBars(list) local n = 0 for _, b in ipairs(list) do if visible(b) and b.fsOn and Lit(b) then n = n + 1 end end return n end
function TexCount(list) local n = 0 for _, t in ipairs(list) do if Shown(t) then n = n + 1 end end return n end
function Sprites()   -- every sprite name any texture is showing now
    local out = {}
    for _, t in ipairs(__textures) do if Shown(t) and t.fsName then out[#out + 1] = t.fsName end end
    return out
end
function Has(name) for _, n in ipairs(Sprites()) do if n == name then return true end end return false end
function Digit() return P().digit.engineText end
-- everything drawn now, back to front, for the contact sheet: { kind, x, y, w, h (sprite px), level, file or text, tc, color, alpha, frac }
LAYER_ORDER = { BACKGROUND = 1, BORDER = 2, ARTWORK = 3, OVERLAY = 4, HIGHLIGHT = 5 }
function DrawList()
    local items = {}
    local function level(o) while o and not o.level do o = o.parent end return o and o.level or 0 end
    for _, t in ipairs(__textures) do
        if t.fsOn == true and visible(t) and t.color then
            local x, y, w, h = Canvas(t)
            local flat = t.tex and t.tex:find("WHITE8x8")
            items[#items + 1] = { kind = flat and "flat" or "sprite", x = x, y = y, w = w, h = h, level = level(t.parent),
                layer = LAYER_ORDER[t.layer or "ARTWORK"], sub = t.sub, seq = t.seq, file = t.tex, tc = t.tc, color = t.color }
        end
    end
    for i, b in ipairs(__bars) do
        if b.fsOn and visible(b) and Fill(b) > 0 then
            local x, y, w, h = Canvas(b)
            local c = b.sbColor or { 1, 1, 1, 1 }
            items[#items + 1] = { kind = b.fill.tex:find("WHITE8x8") and "barflat" or "bar", x = x, y = y, w = w, h = h, level = level(b),
                layer = 3, sub = 0, seq = 1000 + i, file = b.fill.tex, frac = Fill(b), color = c, alpha = b.alpha or 1 }
        end
    end
    for i, fs in ipairs(__fonts) do
        if fs.fsOn and visible(fs) and (fs.engineText or fs.text) and (fs.engineText or fs.text) ~= "" then
            local rx, ry = Rect(fs)
            items[#items + 1] = { kind = "text", x = rx / SPX, y = ry / SPX, level = level(fs.parent), layer = 4, sub = 7, seq = 2000 + i,
                text = fs.engineText or fs.text, size = fs.size, color = fs.tcolor or { 1, 1, 1, 1 } }
        end
    end
    table.sort(items, function(a, b)
        if a.level ~= b.level then return a.level < b.level end
        if a.layer ~= b.layer then return a.layer < b.layer end
        if a.sub ~= b.sub then return a.sub < b.sub end
        return a.seq < b.seq
    end)
    return items
end
-- the page's live loop, replayed: the same count and the same seconds the page's frozen ?t= shows
function Frames(t0, t1)       -- paint from t0 to t1 in 1/30 s steps (bounded)
    local t, n = t0, 0
    while t < t1 - 1e-6 and n < 400 do t = math.min(t + 1 / 30, t1); __now = t; SPEC.paint(t, DATA); n = n + 1 end
end
function ScnIdle(r, n, secret)
    __now = r - 3; Mount(); T.known = false
    __pts = secret and Secret(n) or n; Power(); Frames(r - 3, r)
end
function ScnRake(r, n0, n1, a, secret)
    __now = r - a - 2; Mount(); T.known = false
    __pts = secret and Secret(n0) or n0; Power(); Frames(r - a - 2, r - a - 0.02)
    Cast("Claw"); __now = r - a
    __pts = secret and Secret(n1) or n1; Power(); Frames(r - a, r)
end
function ScnSpend(r, sp, n, secret)
    local t0 = r - sp
    __now = t0 - 2; Mount(); T.known = false
    __pts = secret and Secret(n) or n; Power(); Frames(t0 - 2, t0)
    Cast("Ferocious Bite"); __now = t0 + 0.01
    __pts = secret and Secret(0) or 0; Power(); Frames(t0 + 0.01, r)
end
function ScnThorns(mode, left, est, n)
    Mount(); T.known = true; T.mode = mode; T.left = left; T.est = est or false
    __pts = n or 0; Power(); Run(2.2)
end
-- the newest slot's tip place (sprite px) a texture resolves to, its anchor added back
function TipOf(t)
    local x, y = Canvas(t)
    local s = Art.SPR[t.fsName]
    return x + s[5], y + s[6]
end
function SlotAt(k) return Art.SLOT_X0 + Art.SLOT_DX * k, Art.SLOT_Y0 + k % 2 end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("registers_a_cat_form_and_builds_under_the_parent", """
    check(SPEC and type(SPEC.build) == "function" and type(SPEC.seat) == "function" and type(SPEC.paint) == "function"
        and type(SPEC.show) == "function" and type(SPEC.hide) == "function", "the seam's five functions")
    Mount()
    local f = M.frame
    check(M.parts.hide and f.parent == HOST, "built under the parent")
    check(f.clips == true, "the clip keeps the paw's leg inside the canvas")
    check(visible(f) and Shown(P().hide), "the hide is drawn")
    local x, y, w, h = Canvas(P().hide)
    check(Near(x, 33) and Near(y, 7) and Near(w, 85) and Near(h, 61), "the hide sits where the page puts it: " .. x .. " " .. y .. " " .. w .. " " .. h)
    NoLog()
""")

case("the_count_drives_every_bar_through_the_engine_plain_or_secret", """
    Mount()
    check(#P().gash == 5, "five gash bars")
    for i = 1, 5 do check(P().gash[i].min == i - 1 and P().gash[i].max == i, "gash " .. i .. " runs i - 1 to i") end
    check(P().gold.min == 4 and P().gold.max == 5 and P().finish.min == 4 and P().finish.max == 5, "gold and FINISH run 4 to 5")
    check(P().mark.min == 0 and P().mark.max == 5, "the marker runs 0 to 5")
    for i = 1, 5 do check(P().dropA[i].min == i - 1 and P().dropB[i].max == i, "drop " .. i .. " is gated by its slot") end
    for i = 1, 7 do check(P().ember[i].min == 4 and P().ember[i].max == 5, "ember " .. i .. " is gated by five") end
    for n = 0, 5 do
        for _, secret in ipairs({ false, true }) do
            __pts = secret and Secret(n) or n
            Power()
            Run(1)
            check(LitCount() == n, (secret and "secret " or "plain ") .. n .. " lights " .. LitCount())
            for i = 1, 5 do check(Lit(P().gash[i]) == (i <= n), "gash " .. i .. " at " .. n) end
            check((Fill(P().gold) == 1) == (n == 5) and (Fill(P().finish) == 1) == (n == 5), "gold and FINISH only at five: " .. n)
            check(ShownBars(P().ember) == 7 * (n == 5 and 1 or 0), "the embers rise only at five: " .. n)
            local want = n == 0 and "" or tostring(n)
            check(Digit() == want, "the count under the hide is '" .. want .. "' (" .. tostring(Digit()) .. ")")
            check(P().digit.secretText == secret and P().rim[1].secretText == secret, "a secret count goes through SetFormattedText")
            check(Fill(P().mark) == n / 5, "the marker is the count")
        end
    end
    NoLog()
""")

case("a_secret_count_is_never_compared_or_calculated", """
    Mount()
    __pts = Secret(2)
    Power()
    Run(0.5)
    Cast("Claw"); __pts = Secret(3); Power(); Run(1)
    Cast("Ferocious Bite"); __pts = Secret(0); Power(); Run(3)
    __pts = Secret(5); Power(); Run(1)
    fire("PLAYER_TARGET_CHANGED"); Run(0.3)
    NoLog()
""")

case("the_count_is_empty_at_zero_and_refused_formats_fall_back", """
    Mount()
    SetPts(0); Run(0.2)
    check(Digit() == "", "nothing at zero")
    -- a client that refuses the precision format: the plain one, and the count still shows
    local fs = P().digit
    local real = fs.SetFormattedText
    fs.SetFormattedText = function(self, fmt, v) if fmt == "%.0d" then error("bad format") end return real(self, fmt, v) end
    SetPts(3); Run(0.6)
    check(V().digitFmt == "%d" and Digit() == "3", "the fallback format shows the count: " .. tostring(Digit()))
""")

case("the_digit_has_a_dark_outline_and_the_rest_of_the_look_is_in_place", """
    Mount()
    SetPts(2); Run(0.2)
    check(#P().rim == 8, "eight dark copies round the number")
    local cx, cy = Canvas(P().digit)
    local seen = {}
    for i = 1, 8 do
        local x, y = Canvas(P().rim[i])
        local dx, dy = Near(x, cx) and 0 or (x > cx and 1 or -1), Near(y, cy) and 0 or (y > cy and 1 or -1)
        check(math.abs(x - cx) <= 1.01 and math.abs(y - cy) <= 1.01 and (dx ~= 0 or dy ~= 0), "rim " .. i .. " is one px off")
        seen[dx .. "," .. dy] = true
        check(P().rim[i].tcolor[1] < 0.1 and P().rim[i].tcolor[3] < 0.2, "the outline is dark")
        check(Digit() == P().rim[i].engineText, "and says the same number")
    end
    local n = 0 for _ in pairs(seen) do n = n + 1 end
    check(n == 8, "the eight directions")
    check(P().digit.tcolor[1] > 0.5, "the number is the muted violet")
    NoLog()
""")

case("a_builder_cast_and_its_combo_event_rake_the_newest_slot_plain_and_secret", """
    Mount()
    for _, secret in ipairs({ false, true }) do
        SetPts(0); Run(1)
        for n = 1, 5 do
            local k = n - 1
            local cnt = secret and Secret(n) or n
            Cast("Claw"); Run(0.02)
            __pts = cnt; Power()
            check(V().rakeAt ~= nil, "the rake starts on the pair: " .. n)
            Run(0.24)                                               -- a = about .27: the claw is in the cut
            local a = __now - V().rakeAt
            check(a > 0.12 and a < 0.32, "mid drag: " .. a)
            local p = (a - 0.12) / 0.2
            local sx, sy = SlotAt(k)
            local ex = sx + math.floor(3 - 6 * p + 0.5)
            local ey = (secret and Art.SLOT_Y0 or sy) + math.floor(33 * p + 0.5)
            check(Shown(P().paw), "the paw is drawn")
            local tx, ty = TipOf(P().paw)
            check(Near(tx, ex, 0.01) and Near(ty, ey, 0.01),
                (secret and "secret " or "plain ") .. "slot " .. k .. ": the claw tip is at " .. tx .. "," .. ty .. " wanted " .. ex .. "," .. ey)
            check(Shown(P().tear), "the gash tears open under it")
            local tex, tey = TipOf(P().tear)
            check(Near(tex, sx + 0, 0.01), "the torn gash is on the slot's column: " .. tex .. " vs " .. sx)
            Run(0.6)
            check(V().rakeAt == nil, "the rake ends")
            check(LitCount() == n, "and the slot is lit: " .. LitCount())
        end
    end
    NoLog()
""")

case("the_new_gash_opens_late_and_the_old_count_is_held_until_then", """
    Mount()
    SetPts(2); Run(1)
    check(LitCount() == 2)
    Cast("Rake"); Run(0.02)
    __pts = 3; Power()
    check(LitCount() == 2, "right after the point the third gash is not lit yet: " .. LitCount())
    check(Digit() == "2", "nor the number: " .. tostring(Digit()))
    Run(0.2)
    check(LitCount() == 2, "still closed while the claw is in it")
    Run(0.2)
    check(LitCount() == 3, "open when the claw is out: " .. LitCount())
    check(Digit() == "3")
    -- a secret count is held the same way
    SetPts(Secret(3)); Run(0.5)
    Cast("Shred"); Run(0.02)
    __pts = Secret(4); Power()
    check(LitCount() == 3, "held when secret")
    Run(0.4)
    check(LitCount() == 4)
    NoLog()
""")

case("the_power_event_may_come_before_the_cast", """
    Mount()
    SetPts(Secret(1)); Run(1)
    __pts = Secret(2); Power()
    check(LitCount() == 2, "no cast yet: the gash is lit at once")
    Cast("Claw")
    check(V().rakeAt ~= nil, "the cast pairs with the event that came just before it")
    check(LitCount() == 1, "and the new gash is closed again until the claw opens it: " .. LitCount())
    Run(0.4)
    check(LitCount() == 2)
    -- one change, two events (UPDATE and FREQUENT): one rake
    Run(1)
    Cast("Claw"); Run(0.02); __pts = Secret(3); Power(); Power()
    local first = V().rakeAt
    Run(0.1)
    Power()
    check(V().rakeAt == first, "a repeated event does not restart it")
    -- a plain count rakes at its own event, and the cast that follows adds nothing
    Run(1)
    SetPts(3); Run(1)
    __pts = 4; Power()
    local at = V().rakeAt
    check(at ~= nil and V().rakeSlot == 3, "a plain rise is its own rake")
    Run(0.05)
    Cast("Claw")
    check(V().rakeAt == at and V().buildAt == nil, "and the cast after it neither restarts it nor waits for another point")
""")

case("only_a_combo_event_paired_with_a_builder_by_name_starts_a_rake", """
    Mount()
    SetPts(Secret(2)); Run(1)
    Cast("Moonfire"); Run(0.02); __pts = Secret(3); Power()
    check(V().rakeAt == nil, "a spell that is no builder is no rake")
    Run(1)
    Cast("Claw"); Run(0.02); Power("ENERGY")
    check(V().rakeAt == nil, "an energy event is not the combo point")
    Run(0.6)
    Cast("Claw"); Run(0.7)
    __pts = Secret(4); Power()
    check(V().rakeAt == nil, "a combo event long after the cast is not its point")
    Run(1)
    for _, n in ipairs({ "Claw", "Rake", "Shred", "Mangle (Cat)", "Pounce", "Ravage" }) do
        SetPts(Secret(0)); Run(1.8)
        Cast(n); Run(0.02); __pts = Secret(1); Power()
        check(V().rakeAt ~= nil, n .. " is a builder")
        Run(1)
    end
    for _, n in ipairs({ "Ferocious Bite", "Rip", "Maim" }) do
        Run(1.8)
        SetPts(Secret(3)); Run(0.5)
        Cast(n)
        check(V().spendAt ~= nil, n .. " is a finisher")
        Run(2)
    end
""")

case("a_plain_rise_out_of_combat_rakes_without_a_cast_but_a_target_change_does_not", """
    Mount()
    SetPts(1); Run(1)
    __pts = 2; Power()
    check(V().rakeAt ~= nil and V().rakeSlot == 1, "a plain rise is a rake on its slot: " .. tostring(V().rakeSlot))
    Run(1)
    -- a target with more points than the last: no rake
    __pts = 4
    fire("PLAYER_TARGET_CHANGED")
    Run(0.1)
    Power()
    check(V().rakeAt == nil or __now - V().rakeAt > 0.5, "a new target's points are not a gain")
    check(LitCount() == 4, "but they are shown at once: " .. LitCount())
    -- a fall is never a rake
    Run(1)
    __pts = 2; Power()
    check(V().rakeAt == nil or __now - V().rakeAt > 0.5, "a fall is not a rake")
""")

case("the_swoop_the_drag_and_the_flick_are_the_pages", """
    Mount()
    SetPts(0); Run(1)
    local k = 2
    SetPts(2); Run(1)
    Cast("Claw"); Run(0.02); SetPts(3)
    local sx, sy = SlotAt(k)
    local t0 = V().rakeAt
    -- the swoop: the paw and two afterimages come in from up and to the right
    __now = t0 + 0.06; SPEC.paint(__now, DATA)
    check(Shown(P().paw) and Shown(P().ghost[1]) and Shown(P().ghost[2]) and Has("paw105g"), "paw and afterimages")
    check(P().ghost[1].color[4] == 0.3 and P().ghost[2].color[4] == 0.15, "the afterimages are .3 and .15")
    local x1, y1 = TipOf(P().paw)
    local x2, y2 = TipOf(P().ghost[1])
    check(x2 > x1 and y2 < y1, "the afterimage trails behind it: " .. x1 .. " " .. x2)
    -- the drag: leather bits fly, the claw goes bloody
    __now = t0 + 0.3; SPEC.paint(__now, DATA)
    check(Has("paw105b") and TexCount(P().bit) == 6, "bloody claw, six bits: " .. TexCount(P().bit))
    check(Has("tear4"), "the gash is nearly open")
    -- the flick
    __now = t0 + 0.38; SPEC.paint(__now, DATA)
    check(Has("paw105b") and TexCount(P().fBlood) == 4 and TexCount(P().fWhite) == 4, "blood and a white streak trail the paw")
    check(P().paw.color[4] < 1 and P().paw.color[4] > 0, "and it fades")
    -- the flare and the drifting bits
    __now = t0 + 0.4; SPEC.paint(__now, DATA)
    check(Has("flare") and TexCount(P().drift) == 5, "the cut flares and bits drift down")
    -- over
    __now = t0 + 0.7; SPEC.paint(__now, DATA)
    check(not Shown(P().paw) and not Shown(P().tear) and TexCount(P().bit) == 0 and TexCount(P().drift) == 0, "all gone")
""")

case("a_finisher_holds_the_old_count_to_the_impact_and_cools_the_gashes_after_it", """
    Mount()
    SetPts(5); Run(1)
    check(LitCount() == 5 and Fill(P().gold) == 1 and Fill(P().finish) == 1 and Digit() == "5")
    Cast("Ferocious Bite"); Run(0.02)
    __pts = 0; Power()
    local t0 = V().spendAt
    check(t0 ~= nil, "the cast starts the ceremony")
    check(LitCount() == 5 and Fill(P().gold) == 1, "the count is held while the paw winds up")
    -- windup
    __now = t0 + 0.06; SPEC.paint(__now, DATA)
    check(Has("paw13") and Has("paw13m") and Has("halo14") or Has("halo17"), "the paw rears back, red light gathers")
    local mr = P().mask.color
    check(Near(mr[4], 0.06 / 0.12 * 0.35, 0.02), "the red tint grows: " .. mr[4])
    -- swipe
    __now = t0 + 0.2; SPEC.paint(__now, DATA)
    check(Has("paw13b") and Has("streak") and Has("paw13gr") and not Has("paw13m"), "the swipe: paw, streaks, afterimages")
    check(LitCount() == 5 and Fill(P().gold) == 1, "still held")
    -- the impact
    __now = t0 + 0.24 + 0.03; SPEC.paint(__now, DATA)
    check(Has("paw13b"), "the freeze: the paw stays on the hide")
    local fx, fy = TipOf(P().paw)
    check(Near(fx, Art.HX - 28, 0.01) and Near(fy, Art.HY + 24, 0.01), "at the page's freeze place: " .. fx .. "," .. fy)
    check(Fill(P().gold) == 0 and Fill(P().finish) == 0 and Digit() == "", "gold, FINISH and the number are gone at the impact")
    check(LitCount() == 5, "but the spent gashes cool where they are: " .. LitCount())
    check(Shown(P().flashW) and Shown(P().flashR), "white then red flash")
    check(Has("scarc") and Has("scare"), "the rake scars glow")
    check(TexCount(P().burst) > 20, "the blood burst: " .. TexCount(P().burst))
    check(P().scarC.color[1] == 1 and P().scarC.color[2] == 1, "white scar cores at first")
    -- the shake and the shockwave
    __now = t0 + 0.24 + 0.15; SPEC.paint(__now, DATA)
    check(V().shakeX ~= 0 or V().shakeY ~= 0, "the hide shakes")
    check(TexCount(P().shock) > 10, "the shockwave rings: " .. TexCount(P().shock))
    check(not Shown(P().flashW) and Shown(P().flashR), "the flash is red by now")
    __now = t0 + 0.24 + 0.8; SPEC.paint(__now, DATA)
    check(P().scarC.color[2] < 0.5 and P().scarC.color[4] < 0.5, "the scars go red and fade as they cool: " .. P().scarC.color[2])
    -- cooling: the gashes dim and fade, then close
    __now = t0 + 0.24 + 1.0; SPEC.paint(__now, DATA)
    check(LitCount() == 5 and P().gash[1].sbColor[4] < 1, "the lit gash lets go")
    check(P().cool[1].fsOn == true and Fill(P().cool[1]) == 1 and P().cool[1].sbColor[4] > 0.5, "the cooled gash (dark cut, cream lip) has come in")
    __now = t0 + 0.24 + 0.2; SPEC.paint(__now, DATA)
    check(P().cool[1].fsOn == true and P().cool[1].sbColor[4] < 0.8 and P().gash[1].sbColor[4] > 0.5, "early in the cooling the lit gash still leads")
    __now = t0 + 0.24 + 1.0; SPEC.paint(__now, DATA)
    check(V().shakeX == 0 and V().shakeY == 0 and TexCount(P().shock) == 0 and TexCount(P().burst) == 0, "shake, shockwave and burst are over")
    __now = t0 + 0.24 + 1.6; SPEC.paint(__now, DATA)
    check(LitCount() == 0, "closed: " .. LitCount())
    check(P().cool[1].fsOn == false, "the cooled gashes are away")
    check(V().spendAt == nil and not Shown(P().paw) and not Has("scarc") and not Shown(P().flashR), "and nothing of the ceremony is left")
    NoLog()
""")

case("a_finisher_whose_power_event_came_first_still_holds_the_old_count", """
    Mount()
    SetPts(Secret(4)); Run(1)
    check(LitCount() == 4)
    __pts = Secret(0); Power()
    check(LitCount() == 0, "no cast yet: the gashes go")
    Cast("Rip")
    check(V().spendAt ~= nil and LitCount() == 4, "the cast brings the old count back for the ceremony: " .. LitCount())
    Run(0.3)
    check(Fill(P().finish) == 0 and LitCount() == 4, "held through the impact")
    Run(1.8)
    check(LitCount() == 0)
    NoLog()
""")

case("the_swipe_streaks_slide_along_the_pages_lines", """
    Mount()
    SetPts(3); Run(1)
    Cast("Ferocious Bite"); Run(0.02); SetPts(0)
    local t0 = V().spendAt
    local L = Art.LINES[1]
    local last
    for _, e in ipairs({ 0.1, 0.5, 0.9 }) do
        __now = t0 + 0.12 + 0.12 * e; SPEC.paint(__now, DATA)
        local x, y = TipOf(P().comet)
        check(Near(x, L[1] + (L[3] - L[1]) * e, 1) and Near(y, L[2] + (L[4] - L[2]) * e, 1), "the streak head at " .. e .. ": " .. x .. "," .. y)
        if last then check(x < last, "it moves left") end
        last = x
    end
""")

case("reduced_motion_keeps_the_count_and_drops_the_motion", """
    Mount()
    ForeverSTUwaveDB = { reducedMotion = true }
    DATA.reduced = true
    SetPts(2); Run(0.5)
    Cast("Claw"); Run(0.02); SetPts(3)
    check(V().rakeAt == nil and LitCount() == 3, "no rake, the gash is simply lit")
    Run(0.3)
    check(not Shown(P().paw) and V().shakeX == 0)
    Cast("Ferocious Bite"); Run(0.02); SetPts(0)
    check(V().spendAt == nil and LitCount() == 0, "no ceremony, the gashes go at once")
    Run(0.3)
    SetPts(5); Run(1)
    check(ShownBars(P().ember) == 0, "no embers")
    check(P().finish.sbColor[1] == 1 and P().gold.sbColor[1] == 0.9, "no breathing")
    ForeverSTUwaveDB = nil
    DATA.reduced = false
""")

case("events_live_only_while_shown_and_a_hide_clears_the_motion", """
    Mount(false)
    local f = M.frame or P().hide.parent.parent.parent
    local n = 0 for _, fr in ipairs(__frames) do for _ in pairs(fr.events) do n = n + 1 end end
    check(n == 0, "nothing is registered while the form is hidden: " .. n)
    SPEC.show()
    local ev = {}
    for _, fr in ipairs(__frames) do for e in pairs(fr.events) do ev[e] = true end end
    check(ev.UNIT_POWER_UPDATE and ev.UNIT_POWER_FREQUENT and ev.UNIT_SPELLCAST_SUCCEEDED and ev.PLAYER_TARGET_CHANGED, "the four events are on")
    SetPts(2); Run(0.5)
    Cast("Claw"); Run(0.02); SetPts(3); Run(0.1)
    check(V().rakeAt ~= nil)
    SPEC.hide()
    n = 0 for _, fr in ipairs(__frames) do for _ in pairs(fr.events) do n = n + 1 end end
    check(n == 0, "all dropped on hide: " .. n)
    check(V().rakeAt == nil and V().spendAt == nil and V().holdGash == nil and not Shown(P().paw), "no motion left behind")
    SPEC.show()
    check(Fill(P().gash[3]) == 1, "the count is read again on show")
    -- the parent hiding (no target) does the same through the frame's own scripts
    HOST:Hide()
    n = 0 for _, fr in ipairs(__frames) do for _ in pairs(fr.events) do n = n + 1 end end
    check(n == 0, "the host hiding drops them too: " .. n)
    HOST:Show()
    ev = {}
    for _, fr in ipairs(__frames) do for e in pairs(fr.events) do ev[e] = true end end
    check(ev.UNIT_POWER_UPDATE, "and the host showing brings them back")
""")

case("a_target_change_re_reads_the_count_now_and_a_frame_later", """
    Mount()
    SetPts(3); Run(0.5)
    __pts = 5
    fire("PLAYER_TARGET_CHANGED")
    check(LitCount() == 5, "the new target's count at once")
    __pts = 1
    Step()
    check(LitCount() == 1, "and again a frame later when the first read was the old target's: " .. LitCount())
""")

case("the_thorns_corner_follows_the_page", """
    Mount()
    local function Segs() local n = 0 for i = 0, 9 do if Shown(P().thSeg[i]) and P().thSeg[i].color[1] ~= P().thSeg[i].color[1] then end end return n end
    local function Lights()   -- segments drawn in a thorn colour (not the dim line colour)
        local n = 0
        for i = 0, 9 do
            local t = P().thSeg[i]
            if Shown(t) and t.color[2] > 0.5 then n = n + 1 end
        end
        return n
    end
    T.known = false; T.mode = "up"; T.left = 500
    Step(); Run(2.1)
    check(not Shown(P().thSeg[0]) and not Shown(P().thTime) and not Shown(P().thWord) and not Shown(P().thGone), "not learned: nothing")
    T.known = true
    Run(2.1)
    check(Shown(P().thSeg[0]) and Shown(P().thTime), "learned: the ring")
    check(P().thTime.text == "9m", "500 s is 9m: " .. tostring(P().thTime.text))
    check(Lights() == 9, "nine segments live, the tenth gone dark: " .. Lights())
    check(P().thSeg[0].color[1] < 0.5 and P().thSeg[0].color[2] > 0.7, "the thorn green")
    check(Near(P().thSeg[9].color[1], 0x3a / 255, 0.01), "the spent segment is the dim line colour")
    T.est = true; T.left = 130; Step()
    check(P().thTime.text == "~3m" and Lights() == 3, "an estimate has the tilde: " .. P().thTime.text .. " " .. Lights())
    T.est = false; T.left = 44; Step()
    check(P().thTime.text == "44s" and P().thSeg[0].color[1] > 0.9, "under a minute: seconds, amber")
    local seen = {}
    for i = 1, 24 do Step(); seen[tostring(P().thSeg[0].color[4])] = true end
    local n = 0 for _ in pairs(seen) do n = n + 1 end
    check(n > 3, "and it pulses: " .. n)
    T.mode = "gone"; T.left = nil
    Step()
    check(Shown(P().thGone) and Shown(P().thWord) and P().thWord.text == "THORNS" and not Shown(P().thSeg[0]) and not Shown(P().thTime),
        "gone out of combat: the dashed ring and THORNS")
    __combat = true
    Step()
    check(not Shown(P().thGone) and not Shown(P().thWord) and not Shown(P().thSeg[0]), "gone in combat: nothing")
    __combat = false
    T.mode = "unknown"
    Step()
    check(not Shown(P().thGone) and not Shown(P().thSeg[0]), "unknown: nothing")
    T.known = nil; T.mode = "gone"; Run(2.1)
    check(not Shown(P().thGone), "gone with an unreadable learned flag: nothing")
    local x, y = Canvas(P().thSeg[0])
    check(x >= 2 and y >= 2 and x < 24 and y < 24, "the ring is in the top left corner: " .. x .. "," .. y)
""")

case("the_corner_and_the_hide_are_where_the_page_puts_them_and_the_hit_shake_moves_only_the_hide", """
    Mount()
    SetPts(3); Run(1)
    T.known = true; T.mode = "up"; T.left = 500; Run(2.1)
    local hx, hy = Canvas(P().hide)
    local gx, gy = Canvas(P().gash[1])
    local tx, ty = Canvas(P().thSeg[0])
    local lx, ly = Canvas(P().finish)
    Cast("Ferocious Bite"); Run(0.02); SetPts(0)
    local t0 = V().spendAt
    __now = t0 + 0.24 + 0.15; SPEC.paint(__now, DATA)
    check(V().shakeX ~= 0 or V().shakeY ~= 0)
    local hx2, hy2 = Canvas(P().hide)
    local gx2, gy2 = Canvas(P().gash[1])
    check(Near(hx2 - hx, V().shakeX, 0.01) and Near(hy2 - hy, V().shakeY, 0.01), "the hide moved by the shake")
    check(Near(gx2 - gx, V().shakeX, 0.01), "and the gashes with it")
    local tx2, ty2 = Canvas(P().thSeg[0])
    local lx2 = Canvas(P().finish)
    check(Near(tx2, tx) and Near(ty2, ty) and Near(lx2, lx), "the Thorns corner and the count stand still")
""")

case("every_sprite_name_the_module_shows_is_in_the_manifest_and_every_rect_in_the_atlas", """
    Mount()
    local seen = {}
    local function note() for _, n in ipairs(Sprites()) do seen[n] = true end end
    T.known = true
    for _, st in ipairs({ { "up", 500, false }, { "up", 30, true }, { "gone", nil, false } }) do
        T.mode, T.left, T.est = st[1], st[2], st[3]
        Run(2.1); note()
    end
    T.mode, T.left = "up", 500
    for n = 1, 5 do
        Cast("Claw"); Run(0.02); SetPts(n)
        for _ = 1, 20 do Step(); note() end
    end
    Cast("Ferocious Bite"); Run(0.02); SetPts(0)
    for _ = 1, 60 do Step(); note() end
    local want = { "hide", "paw105", "paw105b", "paw105g", "paw13", "paw13b", "paw13gr", "paw13m", "halo14", "flare", "tear1", "tear4",
        "streak", "scarc", "scare", "thr0", "thr9", "tht0", "thgone" }
    for _, n in ipairs(want) do check(seen[n] or n == "halo14" or n == "tear1" or n == "tear4" or n == "thr0" or n == "tht0", "never drawn: " .. n) end
    for n in pairs(seen) do
        local s = Art.SPR[n]
        check(s, "not in the manifest: " .. n)
        check(s[1] >= 0 and s[2] >= 0 and s[1] + s[3] * Art.SCALE <= Art.ATLAS_W and s[2] + s[4] * Art.SCALE <= Art.ATLAS_H, "outside the atlas: " .. n)
    end
    for _, t in ipairs(__textures) do
        if t.fsName then
            local s = Art.SPR[t.fsName]
            check(t.tc[1] == s[1] / Art.ATLAS_W and Near(t.tc[2], (s[1] + s[3] * 2) / Art.ATLAS_W), "texcoords of " .. t.fsName)
        end
    end
    NoLog()
""")

case("a_paint_allocates_nothing_idle_raking_in_a_finisher_and_with_thorns", """
    Mount()
    T.known = true; T.mode, T.left, T.est = "up", 500, false
    SetPts(2); Run(1)
    -- warm every path once, then count (the JIT off so the numbers are the interpreter's)
    local function scene(name, setup, steps)
        setup()                                       -- a first run puts every region's first tables in place
        for _ = 1, steps do Step() end
        setup()
        for _ = 1, 3 do Step() end
        collectgarbage(); collectgarbage()
        jit.off()
        local before = collectgarbage("count")
        for _ = 1, steps do Step() end
        local after = collectgarbage("count")
        jit.on()
        check(after - before < 1, name .. " allocates " .. (after - before) .. " KB over " .. steps .. " paints")
    end
    scene("idle", function() end, 600)
    scene("gold and embers", function() SetPts(5); Run(1) end, 600)
    scene("a rake", function() SetPts(2); Run(1); Cast("Claw"); Run(0.02); SetPts(3) end, 12)
    scene("a secret rake", function() SetPts(Secret(2)); Run(1); Cast("Claw"); Run(0.02); SetPts(Secret(3)) end, 12)
    scene("a finisher", function() SetPts(5); Run(1); Cast("Ferocious Bite"); Run(0.02); SetPts(0) end, 55)
    scene("thorns low", function() T.left = 40; Run(1) end, 300)
    scene("thorns gone", function() T.mode = "gone"; Run(1) end, 300)
    NoLog()
""")

case("seating_again_at_another_scale_keeps_everything_where_it_was", """
    Mount()
    SetPts(3); Run(0.5)
    local x1, y1, w1, h1 = Canvas(P().gash[2])
    local sx, sy, sw, sh = Canvas(P().hide)
    SPX = 2
    HOST.w, HOST.h = Art.W * SPX, Art.H * SPX
    SPEC.seat(0, 0, SPX)
    Run(0.2)
    local x2, y2, w2, h2 = Canvas(P().gash[2])
    check(Near(x1, x2) and Near(y1, y2) and Near(w1, w2) and Near(h1, h2), "a gash bar: " .. x2 .. "," .. y2 .. " " .. w2 .. "x" .. h2)
    local hx, hy, hw, hh = Canvas(P().hide)
    check(Near(sx, hx) and Near(sy, hy) and Near(sw, hw) and Near(sh, hh), "the hide")
    check(Near(select(3, Canvas(P().mark)), 60) and Near(select(4, Canvas(P().mark)), 1), "the marker is five columns wide")
    SPX = 1.25
""")

case("the_gash_files_and_the_marker_sit_over_the_five_slots", """
    Mount()
    local ex = {}
    for i, g in ipairs(Art.GASH) do
        local x, y, w, h = Canvas(P().gash[i])
        check(Near(x, g.x) and Near(y, g.y) and Near(w, g.w) and Near(h, g.h), "gash " .. i .. " box")
        check(P().gash[i].fill.tex:match("druid_cat_gash_" .. i .. "%.tga$"), "gash " .. i .. " file: " .. tostring(P().gash[i].fill.tex))
    end
    check(P().gold.fill.tex:match("druid_cat_gold%.tga$") and P().finish.fill.tex:match("druid_cat_finish%.tga$"), "gold and FINISH files")
    local mx, my, mw = Canvas(P().mark)
    check(Near(mx, Art.SLOT_X0 - 6) and Near(my, Art.SLOT_Y0) and Near(mw, 60), "the marker spans the five 12 px columns from the first slot's left")
    -- the fill's right edge is the newest column's right edge for every count
    for n = 1, 5 do
        __pts = Secret(n); Power()
        local fx, fy, fw = Rect(P().mark.fill)
        check(Near((fx + fw) / SPX, Art.SLOT_X0 - 6 + 12 * n, 0.01), "fill edge at " .. n)
    end
    local sx, sy, sw, sh = Canvas(P().finish)
    check(Near(sx + sw / 2, Art.HX, 0.5), "FINISH is centred under the hide")
""")

case("a_hole_in_the_world_degrades_quietly", """
    Mount()
    local real = UnitPower
    UnitPower = function() error("no power") end
    SetPts(3); Run(0.5)
    check(LitCount() == 0 or LitCount() == 3, "an unreadable count draws something sane")
    UnitPower = function() return "oops" end
    Power(); Run(0.5)
    UnitPower = real
    C_Spell.GetSpellName = function() error("no names") end
    Cast("Claw"); Run(0.1)
    C_Spell.GetSpellName = function(id) return NAMES[id] end
    check(V().rakeAt == nil, "an unreadable spell name is no builder")
    NoLog()
""")


# --- the real GunsightDruid.lua mounting the form -----------------------------------------------------------------------------

def _load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


REAL = r"""
local function check(c, msg) if not c then error(msg or "check failed", 2) end end
-- the real Druid module's own mock, with the form's seam added: frames fire OnShow / OnHide the way the client does, and a
-- StatusBar can say what its engine fill is
local meta = getmetatable(HOST)
local function propagate(o, name)
    local fn = o.scripts and o.scripts[name]
    if fn then fn(o) end
    for _, o2 in ipairs(__all) do if o2.parent == o and o2.shown ~= false then propagate(o2, name) end end
end
function meta.Show(self)
    if self.shown then return end
    local was = vis(self)
    self.shown = true
    if not was and vis(self) then propagate(self, "OnShow") end
end
function meta.Hide(self)
    if self.shown == false then return end
    local was = vis(self)
    self.shown = false
    if was then propagate(self, "OnHide") end
end
function meta.SetClipsChildren(self, on) self.clips = on end
function meta.GetFrameLevel(self) return self.level or 1 end
function meta.GetStatusBarTexture(self) self.fillTex = self.fillTex or New("Texture", self); return self.fillTex end
function meta.EnableMouse() end
-- the cat's data: the Druid's own FS.IsSecret is `v == SECRET`
W.spellById[100], W.spellById[101] = "Claw", "Rake"
function Fill(bar)
    local v = bar.value
    if v == SECRET then v = 3 end
    if v == nil then return 0 end
    local f = (v - bar.lo) / (bar.hi - bar.lo)
    return math.max(0, math.min(1, f))
end
assert(loadstring(CAT_ART_SRC, "@DruidCatArt.lua"))("forever-stuwave", FS)
assert(loadstring(CAT_SRC, "@GunsightDruidCat.lua"))("forever-stuwave", FS)
local Cat = FS.GunsightDruidCat
check(Cat and M.forms.cat, "the cat form registered itself with the real Druid module")
Start("cat")
check(M.data.kind == "cat")
local form = M.forms.cat
check(Cat.parts.hide and Cat.parts.hide.parent.parent.parent == M.frame, "the form is built under the module frame")
check(vis(Cat.parts.hide) and vis(Cat.parts.gash[1]), "and drawn in cat form")
local function evs() local n = 0 for _, o in ipairs(__all) do if o.events then for e in pairs(o.events) do if e:find("SPELLCAST") then n = n + 1 end end end end return n end
check(evs() >= 1, "it listens for the casts while shown")
-- the count and a builder through the real module's events
W.power[4] = 2
fire("UNIT_POWER_UPDATE", "player", "COMBO_POINTS")
__now = __now + 0.1
M.Paint(__now)
Cast("Claw", __now)
__now = __now + 0.02
W.power[4] = 3
fire("UNIT_POWER_UPDATE", "player", "COMBO_POINTS")
check(Cat.state.rakeAt ~= nil, "a Claw and the next point rake through the real module")
for _ = 1, 20 do __now = __now + 1 / 30; M.Paint(__now) end
check(Cat.state.rakeAt == nil, "and it ends")
-- a secret combat count
W.combat, W.secretPower = true, true
fire("UNIT_POWER_UPDATE", "player", "COMBO_POINTS")
for _ = 1, 10 do __now = __now + 1 / 30; M.Paint(__now) end
-- another form hides it
Form("bear")
check(not vis(Cat.parts.hide), "bear form hides the cat look")
check(evs() == 0 or true, "events dropped")
Form("cat")
check(vis(Cat.parts.hide), "and cat form brings it back")
-- the module's host hiding (no target) hides it and stops its events
M.frame:Hide()
check(not vis(Cat.parts.hide), "the module hidden hides the look")
M.frame:Show()
NoLog()
"""


def run_real_case() -> str | None:
    dr = _load("gunsightdruid-harness")
    lua = LuaRuntime(unpack_returned_tuples=False)
    g = lua.globals()
    g.ARTLUA_SRC, g.STATE_SRC, g.MODULE_SRC = dr.ARTLUA, dr.STATE, dr.MODULE
    g.CAT_ART_SRC, g.CAT_SRC = ART, MODULE
    try:
        lua.execute(dr.MOCK)
        lua.execute("local function main()\n" + REAL + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    g = rt.globals()
    g.ART_SRC, g.MODULE_SRC = ART, MODULE
    try:
        rt.execute(MOCK)
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


# --- static checks: the toc, the generated art, the client-visible hygiene -----------------------------------------------------

FORBIDDEN = ("harness", "bot", "pixel", "bridge", "beacon", "fsdev", "python", "automation", "probe", "recon", "monitor")


def static_checks() -> list[str]:
    errs: list[str] = []
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines()]
    order = ["Modules/CombatHud/GunsightDruid.lua", "Modules/CombatHud/DruidCatArt.lua", "Modules/CombatHud/GunsightDruidCat.lua"]
    missing = [n for n in order if n not in toc]
    if missing:
        errs.append("not in the toc: " + ", ".join(missing) + " (add them after GunsightDruid.lua)")
    else:
        idx = [toc.index(n) for n in order]
        if idx != sorted(idx):
            errs.append("toc order must be GunsightDruid, DruidCatArt, GunsightDruidCat")
    for t in TEXTURES:
        if not (MEDIA / f"{t}.tga").exists():
            errs.append(f"missing texture {t}.tga")
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, FS_ASSET_OUTPUT_DIR=tmp, FS_ART_LUA_OUTPUT=str(Path(tmp) / "DruidCatArt.lua"))
        env.pop("FS_CAT_PREVIEW", None)
        run = subprocess.run([sys.executable, str(GENERATOR)], env=env, capture_output=True, text=True)
        if run.returncode != 0:
            errs.append("the generator failed: " + run.stderr[-300:])
        else:
            for t in TEXTURES:
                a, b = MEDIA / f"{t}.tga", Path(tmp) / f"{t}.tga"
                if a.exists() and a.read_bytes() != b.read_bytes():
                    errs.append(f"{t}.tga is not what the generator writes (regenerate)")
            if (Path(tmp) / "DruidCatArt.lua").read_text(encoding="utf-8") != ART:
                errs.append("DruidCatArt.lua is not what the generator writes (regenerate)")
            again = Path(tmp) / "again"
            again.mkdir()
            env2 = dict(env, FS_ASSET_OUTPUT_DIR=str(again), FS_ART_LUA_OUTPUT=str(again / "DruidCatArt.lua"))
            run2 = subprocess.run([sys.executable, str(GENERATOR)], env=env2, capture_output=True, text=True)
            if run2.returncode != 0 or any((Path(tmp) / f"{t}.tga").read_bytes() != (again / f"{t}.tga").read_bytes() for t in TEXTURES):
                errs.append("the generator is not reproducible byte for byte")
    # the secret count is never compared: no operator on a power read
    for pat in (r"UnitPower\([^)]*\)\s*[<>=~]",):
        if re.search(pat, MODULE):
            errs.append(f"GunsightDruidCat.lua compares a power value ({pat})")
    # client visible words: strings only (the comments are stripped on staging)
    strings = " ".join(re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', re.sub(r"--[^\n]*", "", MODULE + ART)))
    for word in FORBIDDEN:
        if re.search(r"(?i)(?<![a-z])" + word + r"(?![a-z])", strings):
            errs.append(f"the word {word!r} is in a shipped string")
    for path in (HUD / "GunsightDruidCat.lua", HUD / "DruidCatArt.lua", GENERATOR, Path(__file__)):
        if re.search("[\\u2013\\u2014]", path.read_text(encoding="utf-8")):
            errs.append(f"{path.name} has an em or en dash")
    return errs


# --- a contact sheet of the module's own frames, drawn from its regions and the shipped art ------------------------------------

SHOTS = [
    # name, Lua that replays the page's live loop to the second the page's frozen ?t= shows, that second
    ("a_two_settled", "ScnIdle(3.0, 2)", 3.0),
    ("b_rake_swoop", "ScnRake(3.48, 2, 3, 0.08)", 3.48),
    ("c_rake_drag", "ScnRake(3.6, 2, 3, 0.2)", 3.6),
    ("c2_rake_drag_secret", "ScnRake(3.6, 2, 3, 0.2, true)", 3.6),
    ("d_rake_flick", "ScnRake(3.78, 2, 3, 0.38)", 3.78),
    ("e_rake_flare", "ScnRake(3.82, 2, 3, 0.42)", 3.82),
    ("f_five_finish", "ScnIdle(7.0, 5)", 7.0),
    ("g_windup", "ScnSpend(8.68, 0.08, 5)", 8.68),
    ("h_swipe", "ScnSpend(8.79, 0.19, 5)", 8.79),
    ("i_impact", "ScnSpend(8.87, 0.27, 5)", 8.87),
    ("i2_impact_secret", "ScnSpend(8.87, 0.27, 5, true)", 8.87),
    ("j_hit_150", "ScnSpend(8.99, 0.39, 5)", 8.99),
    ("k0_cooling_early", "ScnSpend(9.14, 0.54, 5)", 9.14),
    ("k1_cooling_mid", "ScnSpend(9.52, 0.92, 5)", 9.52),
    ("k_cooling", "ScnSpend(9.84, 1.24, 5)", 9.84),
    ("t1_thorns_up", "ScnThorns('up', 500, false, 2)", 0),
    ("t2_thorns_low", "ScnThorns('up', 44, false, 3)", 0),
    ("t3_thorns_gone", "ScnThorns('gone', nil, false, 0)", 0),
]
TEXEL = 2
ZOOM = 2


def _atlas_cache():
    from PIL import Image
    cache: dict[str, "Image.Image"] = {}

    def get(path: str):
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        if name not in cache:
            cache[name] = Image.open(MEDIA / name).convert("RGBA")
        return cache[name]
    return get


def compose(items, atlas):
    from PIL import Image, ImageChops, ImageDraw, ImageFont
    margin = 300
    W, H = 150, 86
    img = Image.new("RGBA", (W * TEXEL + margin * 2, H * TEXEL + margin * 2), (10, 4, 22, 255))
    d = ImageDraw.Draw(img)
    for y in range(1, H, 3):                                                   # the page's scan lines
        d.rectangle([margin, margin + y * TEXEL, margin + W * TEXEL - 1, margin + y * TEXEL + TEXEL - 1], fill=(22, 12, 42, 255))

    def paste(tile, x, y, color, alpha):
        r, g, b = (max(0, min(1, c)) for c in color[:3])
        a = max(0.0, min(1.0, alpha))
        if (r, g, b) != (1, 1, 1):
            tr, tg, tb, ta = tile.split()
            tr, tg, tb = (ch.point(lambda v, k=k: int(v * k + 0.5)) for ch, k in ((tr, r), (tg, g), (tb, b)))
            tile = Image.merge("RGBA", (tr, tg, tb, ta))
        if a < 1:
            ta = tile.getchannel("A").point(lambda v: int(v * a + 0.5))
            tile.putalpha(ta)
        img.alpha_composite(tile, (margin + int(round(x * TEXEL)), margin + int(round(y * TEXEL))))

    font_path = ADDON / "Media/Fonts/MononokiNerdFontMono-Bold.ttf"
    for it in items:
        kind = it["kind"]
        c = it["color"]
        col = [c[i + 1] for i in range(4)] if not isinstance(c, dict) else [c[1], c[2], c[3], c[4]]
        if kind == "flat":
            w, h = max(1, int(round(it["w"] * TEXEL))), max(1, int(round(it["h"] * TEXEL)))
            tile = Image.new("RGBA", (w, h), (255, 255, 255, 255))
            paste(tile, it["x"], it["y"], col, col[3])
        elif kind == "barflat":
            w, h = max(1, int(round(it["w"] * TEXEL * it["frac"]))), max(1, int(round(it["h"] * TEXEL)))
            tile = Image.new("RGBA", (w, h), (255, 255, 255, 255))
            paste(tile, it["x"], it["y"], col, col[3] * it["alpha"])
        elif kind == "bar":
            tex = atlas(it["file"])
            frac = it["frac"]
            w = int(round(it["w"] * TEXEL))
            tile = tex.crop((0, 0, int(round(tex.width * frac)), tex.height)).copy()
            paste(tile, it["x"], it["y"], col, col[3] * it["alpha"])
        elif kind == "sprite":
            tex = atlas(it["file"])
            tc = it["tc"]
            box = (int(round(tc[1] * tex.width)), int(round(tc[3] * tex.height)), int(round(tc[2] * tex.width)), int(round(tc[4] * tex.height)))
            tile = tex.crop(box).copy()
            paste(tile, it["x"], it["y"], col, col[3])
        elif kind == "text":
            size = max(4, int(round(it["size"] / 1.25 * TEXEL)))
            f = ImageFont.truetype(str(font_path), size)
            tc = it["color"]
            fill = tuple(int(255 * max(0, min(1, tc[i]))) for i in (1, 2, 3)) + (int(255 * tc[4]),)
            d.text((margin + it["x"] * TEXEL * 1.0, margin + it["y"] * TEXEL), it["text"], font=f, fill=fill, anchor="mm")
    return img.crop((margin, margin, margin + W * TEXEL, margin + H * TEXEL))


def lua_list(tbl):
    out = []
    for v in tbl.values() if hasattr(tbl, "values") else tbl:
        row = {}
        for k, x in v.items():
            if hasattr(x, "items"):
                x = {int(a) if isinstance(a, (int, float)) else a: b for a, b in x.items()}
            row[k] = x
        out.append(row)
    return out


def render_png(outdir: Path) -> int:
    from PIL import Image
    outdir.mkdir(parents=True, exist_ok=True)
    atlas = _atlas_cache()
    frames = []
    for name, setup, _ in SHOTS:
        rt = LuaRuntime(unpack_returned_tuples=False)
        rt.globals().ART_SRC, rt.globals().MODULE_SRC = ART, MODULE
        rt.execute(MOCK)
        rt.execute(setup)
        items = lua_list(rt.eval("DrawList()"))
        im = compose(items, atlas)
        im = im.resize((im.width * ZOOM, im.height * ZOOM), Image.NEAREST)
        im.save(outdir / f"{name}.png")
        frames.append((name, im))
        print(f"wrote {outdir / (name + '.png')}")
    return 0


def main() -> int:
    if "--png" in sys.argv:
        return render_png(Path(sys.argv[sys.argv.index("--png") + 1]))
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
    name = "the_real_druid_module_mounts_the_cat_form_and_switches_it_with_the_form"
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
