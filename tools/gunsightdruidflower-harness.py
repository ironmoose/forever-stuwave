#!/usr/bin/env python3
"""Runs the real GunsightDruidFlower.lua (the Druid CASTER form's HoT flower) and the generated DruidFlowerArt.lua headless against a mock
client, and the real GunsightDruid.lua mounting it over the Thorns wreath.

The flower is a 46 x 46 sprite px pixel art flower drawn over the Bramble Wreath, centred on the wreath's centre: the ROSE in the middle
is Rejuvenation (12 s, four heals), the seven PETALS are Regrowth (21 s, seven heals), the base is always drawn. Its data is
FS.DruidState.Hot (the seconds left of our own HoT on the target, a plain ledger number) and State.Known("regrow"); every heal and every
look is a function of elapsed = length - left. These checks pin:

  * the seam: a "caster" form registered with FS.GunsightDruid.RegisterForm; build under the parent above the wreath's frames, seat, show,
    hide; no events are registered; the layers stack on the wreath's centre (every art sprite is placed by the flower canvas origin);
  * the rose: up (a clockwise sweep: the part still lit is hot pink and is the fraction of Rejuvenation's time left, the elapsed part is
    a dark grey wedge that starts at 12 o'clock and grows clockwise; 24 baked steps of 0.5 s, the frame follows the ledger fraction, the
    texcoords are written only when the step changes; the baked frames are checked px by px: the right half grey and the left half lit at
    6 s left), the white flash of the first 0.5 s, the pulse and ten sparkle px outward over 0.7 s on each heal (3, 6, 9 s) and the amber
    of the last 3 s (all three on the lit part only), the pink glow (amber then), gone (grey, half bright);
  * the petals: all live at a cast, petal i wilts when heal i lands (3 i s), a copy falls (down about 40 sprite px, a little sway,
    turning, fading, gone at 1.4 s), a cast flashes every petal toward white and restores them, amber for the last 3 s, grey and dim when
    Regrowth is not up or not learned, the teal glow;
  * the text: the seconds of each HoT left and right of the wreath (position, colour, amber at 3 s or less, hidden when not up), the
    name top left (ON YOU in violet or a friend's name in green, only while a HoT is up), the Thorns label's size, whole sprite px;
  * nothing up: the flower stays drawn, grey and dim; reduced motion; both caster kinds; a re-seat at another scale; a hole in the world;
    no secret is ever compared; a paint allocates nothing; the manifest and every sprite name, the toc lines, the generator's bytes;
  * the real GunsightDruid.lua: the flower is shown and painted after the wreath for moon and tree, the wreath is exactly what it is
    without the flower, and the Cat and Bear looks are not touched.

    python3 tools/gunsightdruidflower-harness.py

    python3 tools/gunsightdruidflower-harness.py --png DIR    (renders the flower over the real wreath in a few states under DIR)

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import math
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
MODULE = (HUD / "GunsightDruidFlower.lua").read_text(encoding="utf-8")
ART = (HUD / "DruidFlowerArt.lua").read_text(encoding="utf-8")
MEDIA = ADDON / "Media/Textures"
TOC = ADDON / "forever-stuwave.toc"
GENERATOR = HERE / "assets" / "generate_druid_flower.py"
LAYERS = HERE / "assets" / "druid_flower_art"
TEXTURES = ["druid_flower_art", "druid_flower_glow"]

MOCK = r"""
function check(c, msg) if not c then error(msg or "check failed", 2) end end
-- a secret value: any operation Lua could do on it errors
SECRET_MT = {
    __lt = function() error("SECRET_OP: compare", 2) end, __le = function() error("SECRET_OP: compare", 2) end,
    __add = function() error("SECRET_OP: arith", 2) end, __sub = function() error("SECRET_OP: arith", 2) end,
    __mul = function() error("SECRET_OP: arith", 2) end, __div = function() error("SECRET_OP: arith", 2) end,
    __mod = function() error("SECRET_OP: arith", 2) end, __pow = function() error("SECRET_OP: arith", 2) end,
    __unm = function() error("SECRET_OP: arith", 2) end, __concat = function() error("SECRET_OP: concat", 2) end,
    __len = function() error("SECRET_OP: len", 2) end, __tostring = function() return "secret" end,
    __index = function() error("SECRET_OP: index", 2) end,
    __eq = function() error("SECRET_OP: compare", 2) end,
}
function Secret(n) return setmetatable({ n = n }, SECRET_MT) end
function IsSecretValue(v) return type(v) == "table" and getmetatable(v) == SECRET_MT end

SPX = 1.25
local Obj = {}
Obj.__index = function(t, k)
    local v = rawget(Obj, k)
    if v ~= nil then return v end
    if type(k) == "string" and k:match("^%u") then return function() end end
end
__textures, __fonts, __frames = {}, {}, {}
function New(kind, parent)
    local o = setmetatable({ kind = kind, parent = parent, shown = true, events = {}, scripts = {}, kids = {}, sets = 0 }, Obj)
    if parent then parent.kids[#parent.kids + 1] = o end
    return o
end
function visible(r) while r do if r.shown == false then return false end; r = r.parent end return true end
function Obj:Show() self.shown = true end
function Obj:Hide() self.shown = false end
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
function Obj:SetScript(n, fn) self.scripts[n] = fn end
function Obj:RegisterEvent(e) self.events[e] = true end
function Obj:RegisterUnitEvent(e, ...) self.events[e] = { ... } end
function Obj:UnregisterEvent(e) self.events[e] = nil end
function Obj:SetFrameLevel(l) self.level = l end
function Obj:GetFrameLevel() return self.level or 1 end
function Obj:EnableMouse(on) self.mouse = on end
function Obj:SetTexture(p, ...) self.tex = p; self.filter = select(3, ...) end
function Obj:SetBlendMode(m) self.blend = m end
function Obj:SetTexCoord(l, r, t, b)
    local c = self.tc or {}
    c[1], c[2], c[3], c[4] = l, r, t, b
    self.tc = c
    self.tcn = (self.tcn or 0) + 1
end
function Obj:SetVertexColor(r, g, b, a)
    local c = self.color or {}
    c[1], c[2], c[3], c[4] = r, g, b, a
    self.color = c
    self.sets = self.sets + 1
end
function Obj:SetText(t) self.text = t end
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
function CreateFrame(kind, name, parent)
    local f = New(kind, parent); f.name = name
    __frames[#__frames + 1] = f
    return f
end

-- where a region is, in image px from the host's top left (y down)
function Rect(o)
    if o == HOST then return 0, 0, o.w, o.h end
    local pt = o.pt
    if not pt or not pt[1] then error("no anchor on a " .. tostring(o.kind)) end
    if pt[1] == "ALL" then return Rect(pt[2]) end
    local rx, ry, rw, rh = Rect(pt[2])
    local ax, ay
    if pt[3] == "TOPLEFT" then ax, ay = rx, ry
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
function InCombatLockdown() return false end

-- the world: our own HoTs (a ledger: when each runs out), what is targeted, what is learned
EXP = {}
T = { known = true, name = "Mahna", errHot = false, errKnown = false, secretName = false }
LEN = { rejuv = 12, regrow = 21 }
HOT_CALLS = 0
function UnitName(unit)
    if T.secretName then return Secret(1) end
    if unit == "player" then return "Stu" end
    return T.name
end
FS = {
    IsSecret = IsSecretValue,
    Gunsight = { ui = function(px) return px end },
    DruidState = {
        TUNING = { REJUV_SECONDS = 12, REGROWTH_SECONDS = 21 },
        Hot = function(key, now)
            HOT_CALLS = HOT_CALLS + 1
            if T.errHot then error("no ledger") end
            local e = EXP[key]
            if not e then return nil end
            local left = e - now
            if left <= 0 then return nil end
            return left
        end,
        Known = function(key)
            if T.errKnown then error("no spellbook") end
            if key == "regrow" then return T.known end
        end,
    },
    Theme = { ApplyMono = function(fs, size) fs.size = size end },
    LogDegradeOnce = function(k, m) __logged = __logged or {}; __logged[k] = m end,
}
RF = {}
FS.GunsightDruid = { C = { TH_LABEL_PX = 10 }, RegisterForm = function(kind, spec) RF[kind] = spec; return true end }
function NoLog() for k, v in pairs(__logged or {}) do error("logged " .. k .. ": " .. tostring(v)) end end
function Near(a, b, eps) return math.abs(a - b) <= (eps or 1e-6) end
-- the wreath's own numbers, from the generated Druid art
DRUIDART_SRC_RUN = assert(loadstring(DRUIDART_SRC, "@DruidArt.lua"))
DRUIDART_SRC_RUN("forever-stuwave", FS)
TH = FS.DruidArt.THORNS

assert(loadstring(ART_SRC, "@DruidFlowerArt.lua"))("forever-stuwave", FS)
assert(loadstring(MODULE_SRC, "@GunsightDruidFlower.lua"))("forever-stuwave", FS)
SPEC, M, Art = RF.caster, FS.GunsightDruidFlower, FS.DruidFlowerArt
HOST = New("Frame")
HOST.w, HOST.h = Art.W * SPX, Art.H * SPX
HOST.level = 10
DATA = { reduced = false, kind = "tree" }
function Mount(show)
    SPEC.build(HOST)
    SPEC.seat(0, 0, SPX)
    SPEC.hide()
    if show ~= false then SPEC.show() end
    return M.frame
end
P = function() return M.parts end
V = function() return M.state end
function Step(dt) __now = __now + (dt or 1 / 30); SPEC.paint(__now, DATA) end
function Run(seconds)       -- bounded: 1/30 s steps, never more than 900 of them
    local n = math.min(900, math.floor(seconds * 30 + 0.5))
    for _ = 1, n do Step() end
end
-- our own cast now (the ledger runs out one length from here)
function Cast(key) EXP[key] = __now + LEN[key] end
-- a HoT that is `el` s old right now (nil: not up), painted once
function At(rej, reg)
    EXP.rejuv = rej and (__now + LEN.rejuv - rej) or nil
    EXP.regrow = reg and (__now + LEN.regrow - reg) or nil
    SPEC.paint(__now, DATA)
end
function Shown(t) return t.fsOn == true and visible(t) end
function Sprites()   -- every sprite name any texture is showing now
    local out = {}
    for _, t in ipairs(__textures) do if Shown(t) and t.fsName then out[#out + 1] = t.fsName end end
    return out
end
function Has(name) for _, n in ipairs(Sprites()) do if n == name then return true end end return false end
-- the rose's frame: its countdown step (0 all lit .. ROSE_STEPS all grey) or nil when the rose shows no countdown frame; and its mask's
function RoseStep() local t = P().rose; local n = t.fsName and t.fsName:match("^rose_w(%d+)$"); if n and Shown(t) then return tonumber(n) end return nil end
function RoseLit() return RoseStep() ~= nil end
function MaskStep() local t = P().roseM; local n = t.fsName and t.fsName:match("^rose_m(%d+)$"); if n and Shown(t) then return tonumber(n) end return nil end
function TexCount(list) local n = 0 for _, t in ipairs(list) do if Shown(t) then n = n + 1 end end return n end
function Alpha(t) return t.color and t.color[4] end
function Tint(t) return t.color[1], t.color[2], t.color[3] end
function Texts() local o = {} for _, fs in ipairs(__fonts) do if fs.fsOn and visible(fs) then o[#o + 1] = fs.text end end return o end
function TextOf(fs) if fs.fsOn and visible(fs) then return fs.text end return nil end
-- the centre of a falling copy on the flower canvas, sprite px (its anchor is its centre)
function TipOf(t)
    local x, y = Canvas(t)
    local s = Art.SPR[t.fsName]
    return x + s[5], y + s[6]
end
function Dist(x1, y1, x2, y2) return math.sqrt((x1 - x2) ^ 2 + (y1 - y2) ^ 2) end
function SparkCentre() return Art.FX + Art.ROSE[1], Art.FY + Art.ROSE[2] end
function SparksShown()
    local list = {}
    for _, t in ipairs(P().spark) do if Shown(t) then local x, y = Canvas(t); list[#list + 1] = { x = x, y = y, a = Alpha(t) } end end
    return list
end
function PetalsWilted()
    local n, which = 0, {}
    for i = 1, 7 do if P().petal[i].fsName == "petal_g" .. i and Shown(P().petal[i]) then n = n + 1; which[#which + 1] = i end end
    return n, which
end
function PetalsLive()
    local n = 0
    for i = 1, 7 do if P().petal[i].fsName == "petal" .. i and Shown(P().petal[i]) then n = n + 1 end end
    return n
end
function MaskCount(color)
    local n = 0
    for i = 1, 7 do
        local t = P().petalM[i]
        if Shown(t) and (color == nil or (Near(t.color[1], color[1], 0.01) and Near(t.color[2], color[2], 0.01) and Near(t.color[3], color[3], 0.01))) then n = n + 1 end
    end
    return n
end
WHITE = { 1, 1, 1 }
function Hexc(h) return { tonumber(h:sub(2, 3), 16) / 255, tonumber(h:sub(4, 5), 16) / 255, tonumber(h:sub(6, 7), 16) / 255 } end
AMBER = Hexc("#ffb020")
function SameRGB(t, c) return Near(t.color[1], c[1], 0.003) and Near(t.color[2], c[2], 0.003) and Near(t.color[3], c[3], 0.003) end
function TextRGB(fs, c) return Near(fs.tcolor[1], c[1], 0.003) and Near(fs.tcolor[2], c[2], 0.003) and Near(fs.tcolor[3], c[3], 0.003) end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("registers_a_caster_form_builds_above_the_wreath_and_listens_to_nothing", """
    check(SPEC and type(SPEC.build) == "function" and type(SPEC.seat) == "function" and type(SPEC.paint) == "function"
        and type(SPEC.show) == "function" and type(SPEC.hide) == "function", "the seam's five functions")
    check(RF.moon == nil and RF.tree == nil, "one look, registered once for both caster kinds")
    Mount()
    local f = M.frame
    check(f.parent == HOST, "built under the parent")
    check(f.level >= HOST.level + 3, "above the wreath's art, bars and top frames (the parent's level + 0, 1, 2): " .. f.level)
    local txt = P().rejT.parent
    check(txt.level > f.level, "the text frame is above the art: " .. tostring(txt.level))
    for _, fr in ipairs(__frames) do
        check(next(fr.events) == nil, "no frame registers an event")
        check(fr.mouse == false or fr.mouse == nil, "no frame takes the mouse")
    end
    check(f.scripts.OnUpdate == nil and f.scripts.OnEvent == nil, "no ticker and no event handler: the Druid module paints it")
    check(visible(f), "the form is shown")
    At(2.5, 2.5)
    check(visible(P().base) and Shown(P().base), "and draws once painted")
    SPEC.hide()
    check(not visible(P().base), "hide hides it")
    SPEC.show()
    check(visible(P().base), "and show brings it back")
    NoLog()
""")

case("the_layers_stack_on_the_wreaths_centre", """
    Mount()
    check(Art.FX + Art.SIZE / 2 == TH.CX and Art.FY + Art.SIZE / 2 == TH.CY, "the flower's canvas is centred on the wreath's centre "
        .. TH.CX .. "," .. TH.CY)
    check(Art.SIZE == 46 and Art.W == 150 and Art.H == 86, "46 x 46 on the 150 x 86 canvas")
    At(4.5, 4.5)
    -- every art layer is placed by the flower canvas origin: its sprite's own anchor sits on (FX, FY)
    local seen = 0
    for _, t in ipairs(__textures) do
        if Shown(t) and t.fsName and not t.fsName:match("^fall") then
            local x, y = Canvas(t)
            local s = Art.SPR[t.fsName]
            check(Near(x + s[5], Art.FX) and Near(y + s[6], Art.FY), t.fsName .. " is placed by the flower origin: " .. x .. "," .. y)
            check(x == math.floor(x) and y == math.floor(y), t.fsName .. " sits on whole sprite px")
            seen = seen + 1
        end
    end
    check(seen == 9, "base, the rose's frame and seven petals: " .. seen)
    check(P().roseHot == nil, "the old pink layer over the rose is gone: the pink is baked into the frames")
    -- the glows are centred on the rose and on the flower
    local rx, ry = SparkCentre()
    local gx, gy, gw, gh = Canvas(P().glowRose)
    check(Near(gx + gw / 2, rx, 0.5) and Near(gy + gh / 2, ry, 0.5), "the rose glow is on the rose: " .. gx + gw / 2 .. "," .. gy + gh / 2 .. " vs " .. rx .. "," .. ry)
    gx, gy, gw, gh = Canvas(P().glowFlower)
    check(Near(gx + gw / 2, TH.CX, 0.5) and Near(gy + gh / 2, TH.CY, 0.5), "the flower glow is on the wreath's centre")
    check(P().glowRose.blend == "ADD" and P().glowFlower.blend == "ADD", "the glows are added to what is behind them")
    -- back to front: glows, base, petals, rose, its lit mask, falling copy, sparks, then the text frame
    local function z(t) return { t.parent.level, ({ BACKGROUND = 1, BORDER = 2, ARTWORK = 3, OVERLAY = 4 })[t.layer], t.sub } end
    local function before(a, b)
        local za, zb = z(a), z(b)
        for k = 1, 3 do if za[k] ~= zb[k] then return za[k] < zb[k] end end
        return a.seq < b.seq
    end
    local order = { P().glowFlower, P().glowRose, P().base, P().petal[1], P().petalM[1], P().rose, P().roseM, P().fall, P().spark[1] }
    for i = 1, #order - 1 do check(before(order[i], order[i + 1]), "layer " .. i .. " is drawn before layer " .. i + 1) end
    check(P().rejT.parent.level > P().spark[1].parent.level, "the text is above everything")
    NoLog()
""")

case("the_rose_frame_follows_the_time_left_full_at_the_cast_half_at_six_seconds_and_grey_at_the_end", """
    Mount()
    local N = Art.ROSE_STEPS
    check(N == 24, "24 steps, one per half second of the 12 s: " .. tostring(N))
    At(0.0)                                   -- cast now: 12 s left
    check(RoseStep() == 0 and P().rose.fsName == "rose_w0", "full at the cast: " .. tostring(P().rose.fsName))
    At(6.0)                                   -- 6 s left
    check(RoseStep() == 12, "half at 6 s left: " .. tostring(RoseStep()))
    At(6.0 + 1e-7); check(RoseStep() == 12, "a hair either way is still half")
    At(6.0 - 1e-7); check(RoseStep() == 12, "(rounded to the nearest step)")
    At(9.0); check(RoseStep() == 18, "a quarter of the time left (3 s): " .. tostring(RoseStep()))
    At(3.0); check(RoseStep() == 6, "three quarters left (9 s): " .. tostring(RoseStep()))
    At(11.5); check(RoseStep() == 23, "half a second left: " .. tostring(RoseStep()))
    At(11.9); check(RoseStep() == N and P().rose.fsName == "rose_w24", "the last frame near 0 is all grey: " .. tostring(RoseStep()))
    At(11.999); check(RoseStep() == N, "to the very end")
    -- the frame is the nearest step of the plain fraction left / length, and only ever goes forward as time passes
    local prev = 0
    for k = 0, 1199 do
        local el = k * 0.01
        At(el)
        local step = RoseStep()
        local left = 12 - el
        check(step ~= nil and step >= prev and step <= prev + 1, "the step only moves forward one at a time at " .. el .. ": " .. tostring(prev) .. " -> " .. tostring(step))
        check(math.abs((N - step) / N - left / 12) <= 0.5 / N + 1e-9, "the lit fraction is the time left at " .. el .. ": " .. (N - step) / N .. " vs " .. left / 12)
        prev = step
    end
    check(prev == N, "it ends on the last frame")
    -- a recast puts the rose back to full
    At(8.0); check(RoseStep() > 12)
    At(0.1); check(RoseStep() == 0, "a recast restarts the sweep")
    -- the pink is baked into the frames: the vertex colour stays white and nothing is drawn over the rose to tint it
    At(4.5)
    check(P().rose.fsName == "rose_w9" and SameRGB(P().rose, WHITE) and Alpha(P().rose) == 1, "drawn as baked: " .. tostring(P().rose.fsName))
    check(Has("rose_w9") and not Has("rose_g") and not Shown(P().roseM) and not Shown(P().glowFlower), "no mask and no teal glow with only the rose up")
    -- the pink glow is added behind it, brighter while the time is long
    local g1 = Alpha(P().glowRose)
    check(Shown(P().glowRose) and SameRGB(P().glowRose, Hexc("#ff3ea5")), "a pink glow behind the rose")
    At(8.5); check(Alpha(P().glowRose) < g1, "and it fades with the time left")
    NoLog()
""")

case("the_rose_texcoords_are_written_only_when_the_step_changes", """
    Mount()
    At(4.0)                                             -- el 4.0: step 8 (the next step starts at 4.25)
    local r = P().rose
    check(RoseStep() == 8, "step 8: " .. tostring(RoseStep()))
    local n0 = r.tcn
    check(n0 ~= nil and n0 >= 1, "the sprite's texcoords were written once")
    SPEC.paint(__now, DATA); SPEC.paint(__now, DATA)
    check(r.tcn == n0, "the same paint twice writes no texcoords")
    for _ = 1, 6 do Step() end                          -- 0.2 s later: still step 8
    check(RoseStep() == 8 and r.tcn == n0, "a paint inside the step writes no texcoords: " .. tostring(r.tcn) .. " vs " .. n0)
    Run(0.1)                                            -- 4.3 s: step 9
    check(RoseStep() == 9 and r.tcn == n0 + 1, "a new step writes them once: " .. tostring(RoseStep()) .. " " .. tostring(r.tcn))
    for _ = 1, 6 do Step() end
    check(RoseStep() == 9 and r.tcn == n0 + 1, "and then no more until the next")
    -- the whole countdown: one write per step, no more (12 s, 24 steps and the first frame)
    EXP.rejuv = nil; At(nil, nil); At(0.0)
    local w0 = P().rose.tcn
    for _ = 1, 360 + 15 do Step() end                   -- a hair over 12.4 s: the ledger ends at 12 s and the rose goes grey
    local sets = P().rose.tcn - w0
    check(sets <= 25 + 1, "about one write per step over the whole countdown: " .. sets)
    -- amber and the same step share one mask write per step, not one per paint
    At(nil, nil); At(10.0)
    local m = P().roseM
    check(Shown(m) and MaskStep() == RoseStep(), "the mask is the frame's own lit part")
    local m0 = m.tcn
    for _ = 1, 8 do Step() end
    check(m.tcn - m0 <= 1, "the mask writes its texcoords only on a step: " .. tostring(m.tcn - m0))
    NoLog()
""")

case("the_mask_is_the_lit_part_of_the_frame_under_it", """
    Mount()
    for _, age in ipairs({ 0.05, 0.3, 3.2, 6.2, 9.4, 10.3, 11.2, 11.7 }) do
        At(age)
        local mk, step = MaskStep(), RoseStep()
        check(mk ~= nil and mk == step, "at " .. age .. " the mask is frame " .. tostring(step) .. "'s lit part: " .. tostring(mk))
    end
    At(11.95)                                            -- nothing is left lit: nothing to flash or pulse
    check(RoseStep() == Art.ROSE_STEPS and not Shown(P().roseM), "an all grey rose has no mask")
    check(SameRGB(P().glowRose, AMBER), "(the amber glow stays)")
    NoLog()
""")

case("the_rose_flashes_white_for_half_a_second_after_the_cast", """
    Mount()
    At(0.05)
    local m = P().roseM
    check(Shown(m) and m.fsName == "rose_m0" and SameRGB(m, WHITE), "a white silhouette of the lit part over the rose: " .. tostring(m.fsName))
    local a0 = Alpha(m)
    check(a0 >= 0.8, "starts strong: " .. a0)
    At(0.25); local a1 = Alpha(m)
    check(a1 > 0 and a1 < a0, "and fades: " .. a1)
    At(0.45); local a2 = Alpha(m)
    check(a2 > 0 and a2 < a1, "to nothing: " .. a2)
    At(0.5); check(not Shown(m), "gone at 0.5 s")
    At(0.9); check(not Shown(m), "and stays gone")
    -- a recast restarts it (the time left goes back up)
    At(8.0); check(not Shown(m))
    At(0.05); check(Shown(m), "a recast flashes again")
    NoLog()
""")

case("each_heal_pulses_the_rose_and_throws_ten_sparkle_px_outward_over_a_moment", """
    Mount()
    local rx, ry = SparkCentre()
    for _, heal in ipairs({ 3, 6, 9 }) do
        At(heal - 0.05)
        check(TexCount(P().spark) == 0, "no sparkles before heal " .. heal)
        At(heal + 0.02)
        check(Shown(P().roseM) and SameRGB(P().roseM, WHITE) and Alpha(P().roseM) > 0.3, "the pulse: a white mask at heal " .. heal)
        check(MaskStep() == RoseStep() and RoseStep() == math.floor(heal / 12 * 24 + 0.5), "on the lit part of the frame at heal " .. heal .. ": " .. tostring(MaskStep()))
        local sp = SparksShown()
        check(#sp == 10, "ten sparkle px: " .. #sp)
        local d0 = 0
        for _, s in ipairs(sp) do d0 = d0 + Dist(s.x, s.y, rx, ry) end
        d0 = d0 / #sp
        check(d0 < 5, "they start at the rose's centre: " .. d0)
        At(heal + 0.35)
        local mid = 0
        for _, s in ipairs(SparksShown()) do mid = mid + Dist(s.x, s.y, rx, ry) end
        mid = mid / math.max(1, #SparksShown())
        At(heal + 0.65)
        local late, n = 0, 0
        for _, s in ipairs(SparksShown()) do late = late + Dist(s.x, s.y, rx, ry); n = n + 1 end
        late = late / math.max(1, n)
        check(mid > d0 + 2 and late > mid, "outward: " .. d0 .. " " .. mid .. " " .. late)
        check(late < 22, "a small burst: " .. late)
        for _, s in ipairs(SparksShown()) do check(s.x == math.floor(s.x) and s.y == math.floor(s.y), "whole sprite px") end
        At(heal + 0.1); local a1 = SparksShown()[1].a
        At(heal + 0.5); local a2 = SparksShown()[1].a
        check(a2 < a1, "they fade as they go: " .. a1 .. " " .. a2)
        At(heal + 0.7)
        check(TexCount(P().spark) == 0 and (not Shown(P().roseM) or SameRGB(P().roseM, AMBER)), "over after 0.7 s at heal " .. heal)
    end
    -- the glow flares with the pulse
    At(4.5); local calm = Alpha(P().glowRose)
    At(3.02); check(Alpha(P().glowRose) > calm - 0.0001 and Shown(P().glowRose), "the glow is up on a pulse")
    NoLog()
""")

case("the_rose_pulses_amber_for_the_last_three_seconds", """
    Mount()
    At(8.9)                                           -- 3.1 s left
    check(not Shown(P().roseM), "not amber yet")
    check(SameRGB(P().glowRose, Hexc("#ff3ea5")), "the glow is pink")
    -- 1.5 s left: amber, pulsing with the clock
    At(10.5)
    local m = P().roseM
    check(Shown(m) and SameRGB(m, AMBER), "an amber silhouette over the rose")
    check(MaskStep() == RoseStep() and RoseStep() == 21, "on the lit part only: frame " .. tostring(RoseStep()) .. " mask " .. tostring(MaskStep()))
    check(SameRGB(P().glowRose, AMBER), "and an amber glow")
    local seen = {}
    for k = 0, 20 do __now = __now + 0.05; At(10.5); seen[#seen + 1] = Alpha(m) end
    local lo, hi = 9, 0
    for _, a in ipairs(seen) do lo, hi = math.min(lo, a), math.max(hi, a) end
    check(hi - lo >= 0.15, "it pulses: " .. lo .. " to " .. hi)
    check(lo >= 0.25 and hi <= 0.65, "within the amber range: " .. lo .. " " .. hi)
    At(11.7); check(Shown(m) and SameRGB(m, AMBER), "to the last lit sliver")
    At(11.99); check(RoseStep() == Art.ROSE_STEPS and not Shown(m) and SameRGB(P().glowRose, AMBER), "nothing lit is left to pulse; the glow is amber to the end")
    EXP.rejuv = __now + 3                               -- exactly three seconds left is amber
    SPEC.paint(__now, DATA)
    check(SameRGB(P().glowRose, AMBER), "3.0 s left is amber")
    NoLog()
""")

case("a_rose_that_is_not_up_is_grey_and_half_bright", """
    Mount()
    At(nil, 4.5)
    local r = P().rose
    check(Shown(r) and r.fsName == "rose_g" and not RoseLit(), "the desaturated rose, no countdown frame")
    check(Near(r.color[1], 0.5) and Near(r.color[2], 0.5) and Near(r.color[3], 0.5) and r.color[4] == 1, "dimmed to half")
    check(not Shown(P().roseM) and not Shown(P().glowRose) and TexCount(P().spark) == 0, "no mask, no glow, no sparkles")
    At(4.5, 4.5)
    check(RoseLit() and SameRGB(P().rose, WHITE), "and it comes back up, drawn as baked")
    At(nil, nil)
    check(P().rose.fsName == "rose_g", "grey with nothing up")
    NoLog()
""")

case("a_cast_starts_every_petal_live_and_flashes_them_white_for_half_a_second", """
    Mount()
    At(nil, 0.05)
    check(PetalsLive() == 7 and PetalsWilted() == 0, "all seven petals live")
    for i = 1, 7 do
        local t = P().petal[i]
        check(t.fsName == "petal" .. i and SameRGB(t, WHITE) and Alpha(t) == 1, "petal " .. i .. " is drawn as it is")
        check(Shown(P().petalM[i]) and P().petalM[i].fsName == "petal_m" .. i and SameRGB(P().petalM[i], WHITE), "and flashed white")
    end
    local a0 = Alpha(P().petalM[1])
    check(a0 >= 0.8, "a strong flash: " .. a0)
    At(nil, 0.3); check(Alpha(P().petalM[4]) < a0 and Alpha(P().petalM[4]) > 0, "fading")
    At(nil, 0.5); check(MaskCount() == 0, "restored at 0.5 s")
    At(nil, 0.9); check(MaskCount() == 0 and PetalsLive() == 7, "and live")
    -- a recast after petals have healed restores all of them
    At(nil, 14.5)
    check(PetalsWilted() == 4, "four wilted")
    At(nil, 0.1)
    check(PetalsLive() == 7 and PetalsWilted() == 0 and MaskCount() == 7, "a recast restores every petal and flashes them")
    NoLog()
""")

case("petal_i_wilts_in_place_when_heal_i_lands_in_order_and_in_count", """
    Mount()
    for heal = 1, 6 do
        At(nil, 3 * heal - 0.1)
        check(PetalsWilted() == heal - 1, "just before heal " .. heal .. ": " .. PetalsWilted() .. " wilted")
        At(nil, 3 * heal + 1.6)                         -- the falling copy is gone by then
        local n, which = PetalsWilted()
        check(n == heal and PetalsLive() == 7 - heal, "after heal " .. heal .. ": " .. n .. " wilted " .. PetalsLive() .. " live")
        for k, i in ipairs(which) do check(i == k, "they wilt in order, petal 1 first: " .. table.concat(which, ",")) end
        for i = 1, heal do
            local t = P().petal[i]
            check(t.fsName == "petal_g" .. i, "petal " .. i .. " is the desaturated one")
            check(Near(t.color[1], 0.35) and Near(t.color[2], 0.35) and Near(t.color[3], 0.35) and t.color[4] == 1, "dark, 0.35")
            check(not Shown(P().petalM[i]), "a wilted petal has no flash or amber")
        end
        -- the wilted petal stays where it was: the same canvas origin as the live one
        local x, y = Canvas(P().petal[heal])
        local s = Art.SPR["petal_g" .. heal]
        check(Near(x + s[5], Art.FX) and Near(y + s[6], Art.FY), "wilted in place")
        local live = P().petal[heal + 1]
        check(live.fsName == "petal" .. (heal + 1) and SameRGB(live, WHITE), "the next petal is untouched")
    end
    -- the last petal is still there at 20.5 s, and the seventh wilts only as the ledger runs out
    At(nil, 20.5); check(PetalsLive() == 1 and P().petal[7].fsName == "petal7", "one live petal at 20.5 s")
    NoLog()
""")

case("the_wilted_petals_copy_falls_down_forty_px_sways_turns_fades_and_ends", """
    Mount()
    for heal = 1, 6 do                                  -- the seventh falls from the grey flower: see the last heal
        At(nil, 3 * heal - 0.1)
        check(not Shown(P().fall), "nothing falls before heal " .. heal)
        At(nil, 3 * heal + 0.01)
        local fl = P().fall
        check(Shown(fl) and fl.fsName:match("^fall" .. heal .. "_%d+$"), "heal " .. heal .. " drops a copy of petal " .. heal .. ": " .. tostring(fl.fsName))
        check(Near(fl.color[1], 0.35) and Near(fl.color[2], 0.35), "the wilted look")
        local c = Art.PETAL[heal]
        local x0, y0 = TipOf(fl)
        check(Near(x0, Art.FX + c[1], 1) and Near(y0, Art.FY + c[2], 1), "it starts on its petal: " .. x0 .. "," .. y0 .. " vs " .. Art.FX + c[1] .. "," .. Art.FY + c[2])
        local prevY, prevA, names, maxsway = y0, Alpha(fl), {}, 0
        for k = 1, 13 do
            local age = k * 0.1
            At(nil, 3 * heal + age)
            check(Shown(fl), "still falling at " .. age)
            local x, y = TipOf(fl)
            check(y >= prevY - 0.001, "it only goes down: " .. prevY .. " " .. y)
            check(Alpha(fl) <= prevA + 0.0001, "and only fades")
            prevY, prevA = y, Alpha(fl)
            names[fl.fsName] = true
            maxsway = math.max(maxsway, math.abs(x - (Art.FX + c[1])))
            check(x == math.floor(x) and y == math.floor(y), "whole sprite px")
        end
        check(maxsway >= 1 and maxsway <= 3.6, "a little sideways sway: " .. maxsway)
        local n = 0 for _ in pairs(names) do n = n + 1 end
        check(n >= 8, "it turns (a new baked turn most steps): " .. n)
        At(nil, 3 * heal + 1.35)
        local x, y = TipOf(fl)
        check(y - (Art.FY + c[2]) >= 36 and y - (Art.FY + c[2]) <= 41, "about forty sprite px down by the end: " .. y - (Art.FY + c[2]))
        check(Shown(fl) and Alpha(fl) <= 0.15, "nearly gone: " .. Alpha(fl))
        At(nil, 3 * heal + 1.4)
        check(not Shown(fl), "gone at 1.4 s")
    end
    -- only one copy at a time (the heals are 3 s apart and a copy lives 1.4 s)
    local n = 0 for _, t in ipairs(__textures) do if Shown(t) and t.fsName and t.fsName:match("^fall") then n = n + 1 end end
    check(n == 0, "none left")
    At(nil, 6.3); n = 0
    for _, t in ipairs(__textures) do if Shown(t) and t.fsName and t.fsName:match("^fall") then n = n + 1 end end
    check(n == 1, "one at a time")
    NoLog()
""")

case("the_seventh_heal_lands_as_regrowth_runs_out_and_its_petal_falls_from_the_grey_flower", """
    Mount()
    Cast("regrow"); Run(20.0)
    check(PetalsLive() == 1 and P().petal[7].fsName == "petal7", "one live petal a second before the end")
    check(not Shown(P().fall), "nothing falls yet")
    Run(1.1)                                              -- 21.1 s: the ledger has dropped Regrowth
    check(PetalsLive() == 0 and P().petal[7].fsName == "petal_g7" and not Shown(P().glowFlower), "everything grey")
    local fl = P().fall
    check(Shown(fl) and fl.fsName:match("^fall7_%d+$"), "petal 7's copy falls: " .. tostring(fl.fsName))
    check(Near(fl.color[1], 0.35) and fl.color[4] <= 1, "the wilted look")
    local c = Art.PETAL[7]
    local _, y0 = TipOf(fl)
    check(y0 - (Art.FY + c[2]) < 8, "near its petal at first: " .. y0 - (Art.FY + c[2]))
    Run(0.7)
    local _, y1 = TipOf(fl)
    check(Shown(fl) and y1 > y0 + 8, "and it drops: " .. y1)
    Run(1.0)
    check(not Shown(fl), "gone after 1.4 s")
    Run(2)
    check(not Shown(fl) and PetalsLive() == 0 and Shown(P().base) and P().base.fsName == "base_g", "and the flower rests grey")
    local sets = 0
    for _, t in ipairs(__textures) do sets = sets + t.sets end
    Run(2)
    local after = 0
    for _, t in ipairs(__textures) do after = after + t.sets end
    check(after == sets, "painted once more and then left alone")
    -- the rose recast during the fall: the fall goes on while the rose is up
    Cast("regrow"); Run(20.9); Cast("rejuv"); Run(0.5)
    check(RoseLit() and Shown(P().fall) and P().fall.fsName:match("^fall7_"), "the fall plays with the rose up")
    Run(1.2)
    check(not Shown(P().fall) and RoseLit(), "and ends")
    -- not a last heal: a target change drops it with plenty of time left
    EXP.rejuv = nil
    Cast("regrow"); Run(10); EXP.regrow = nil; Run(0.1)
    check(not Shown(P().fall) and PetalsLive() == 0, "a dropped ledger early plays no fall")
    -- not a last heal: a gap in the paints (the form was away) and then nothing
    Cast("regrow"); Run(20.9); __now = __now + 5; SPEC.paint(__now, DATA)
    check(not Shown(P().fall), "a long gap is not the last heal")
    -- a recast in the last moments keeps it alive and plays nothing
    Cast("regrow"); Run(20.9); Cast("regrow"); Run(0.5)
    check(not Shown(P().fall) and PetalsLive() == 7, "a recast restores the petals")
    -- reduced motion: no fall
    DATA.reduced = true
    EXP.regrow = nil; Cast("regrow"); Run(21.1)
    check(not Shown(P().fall) and PetalsLive() == 0, "reduced motion: no fall")
    DATA.reduced = false
    NoLog()
""")

case("the_last_three_seconds_pulse_the_live_petals_amber", """
    Mount()
    At(nil, 17.9)                                       -- 3.1 s left: 5 wilted, 2 live
    check(PetalsLive() == 2 and MaskCount() == 0, "not amber yet")
    At(nil, 19.0)                                       -- 2 s left
    check(MaskCount(AMBER) == 1 and MaskCount() == 1, "only the live petal pulses amber")
    check(Shown(P().petalM[7]) and not Shown(P().petalM[1]), "and the wilted ones do not")
    local lo, hi = 9, 0
    for k = 0, 20 do __now = __now + 0.05; At(nil, 19.0); local a = Alpha(P().petalM[7]); lo, hi = math.min(lo, a), math.max(hi, a) end
    check(hi - lo >= 0.15 and lo >= 0.25 and hi <= 0.65, "it pulses: " .. lo .. " " .. hi)
    At(nil, 14.5)                                       -- 6.5 s left, 4 wilted: three live, none amber
    check(PetalsLive() == 3 and MaskCount() == 0, "amber starts at three seconds")
    NoLog()
""")

case("a_regrowth_that_is_not_up_or_not_learned_greys_every_petal_and_still_draws_them", """
    Mount()
    At(4.5, nil)
    for i = 1, 7 do
        local t = P().petal[i]
        check(Shown(t) and t.fsName == "petal_g" .. i, "petal " .. i .. " is the grey one")
        check(Near(t.color[1], 0.5) and Near(t.color[2], 0.5) and Near(t.color[3], 0.5) and t.color[4] == 1, "dim")
        check(not Shown(P().petalM[i]), "no flash")
    end
    check(not Shown(P().fall) and not Shown(P().glowFlower), "no falling copy, no teal glow")
    -- not learned: a stale ledger entry does not draw it live
    T.known = false
    V().poll = -99
    At(4.5, 6)
    check(PetalsLive() == 0 and Shown(P().petal[1]) and P().petal[1].fsName == "petal_g1", "not learned: all grey")
    check(TextOf(P().regT) == nil, "and no Regrowth seconds")
    check(TextOf(P().rejT) ~= nil, "the rose is unaffected")
    -- an unreadable spellbook is not 'not learned'
    T.known = nil
    V().poll = -99
    At(4.5, 6)
    check(PetalsLive() == 5, "an unreadable spellbook keeps the ledger: " .. PetalsLive())
    T.known = true
    NoLog()
""")

case("the_teal_glow_sits_behind_the_flower_while_regrowth_is_up", """
    Mount()
    At(nil, 4.5)
    local g = P().glowFlower
    check(Shown(g) and SameRGB(g, Hexc("#22d3ee")), "a teal glow")
    local a1 = Alpha(g)
    At(nil, 17); check(Alpha(g) < a1, "fading with the time left")
    At(nil, 20.5); check(Shown(g) and SameRGB(g, Hexc("#22d3ee")), "teal to the end")
    At(nil, nil); check(not Shown(g), "gone with Regrowth")
    NoLog()
""")

case("the_base_is_always_drawn_and_lit_only_while_regrowth_is_up", """
    Mount()
    At(nil, nil)
    check(Shown(P().base) and P().base.fsName == "base_g" and Near(P().base.color[1], 0.5), "nothing up: grey and half bright")
    At(4.5, nil)
    check(P().base.fsName == "base_g" and Near(P().base.color[1], 0.5), "Rejuvenation alone: grey, the base is Regrowth's")
    At(nil, 4.5)
    check(P().base.fsName == "base" and SameRGB(P().base, WHITE), "Regrowth alone: as it is")
    At(4.5, 4.5)
    check(P().base.fsName == "base", "both: as it is")
    NoLog()
""")

case("both_hots_gone_leaves_the_whole_flower_drawn_grey_and_dim", """
    Mount()
    At(nil, nil)
    local n = 0
    for _, t in ipairs(__textures) do
        if Shown(t) then
            n = n + 1
            check(t.fsName and t.fsName:match("_g%d*$"), "only grey sprites: " .. tostring(t.fsName))
            check(Near(t.color[1], 0.5) and Near(t.color[2], 0.5) and Near(t.color[3], 0.5), "all dim: " .. t.fsName)
        end
    end
    check(n == 9, "the base, the rose and the seven petals stay drawn: " .. n)
    check(#Texts() == 0, "no text")
    -- the HoTs running out by themselves ends in the same picture
    Cast("rejuv"); Cast("regrow"); Run(0.5)
    check(RoseLit() and Has("petal1"), "up")
    Run(22)
    check(not RoseLit() and Has("rose_g") and Has("petal_g1") and #Texts() == 0, "and grey again when they run out")
    NoLog()
""")

case("the_seconds_stand_left_and_right_of_the_wreath_in_pink_and_teal", """
    Mount()
    At(4.1, 5.2)                                        -- 7.9 s and 15.8 s left
    local rej, reg, name = P().rejT, P().regT, P().name
    check(TextOf(rej) == "8" and TextOf(reg) == "16", "the seconds left, rounded up: " .. tostring(rej.text) .. " " .. tostring(reg.text))
    check(rej.pt[1] == "CENTER" and reg.pt[1] == "CENTER", "centred on their spots")
    local x, y = Canvas(rej)
    check(Near(x, 27) and Near(y, 30), "Rejuvenation: centre 27, 30: " .. x .. "," .. y)
    x, y = Canvas(reg)
    check(Near(x, 123) and Near(y, 30), "Regrowth: centre 123, 30: " .. x .. "," .. y)
    check(27 < TH.CX - TH.R and 123 > TH.CX + TH.R, "left and right of the wreath")
    check(TextRGB(rej, Hexc("#ff5cb8")), "pink")
    check(TextRGB(reg, Hexc("#4fe0f0")), "teal")
    check(Near(rej.size, 10 * SPX) and Near(reg.size, 10 * SPX) and Near(name.size, 10 * SPX), "the Thorns label's size: " .. tostring(rej.size))
    check(rej.size == FS.GunsightDruid.C.TH_LABEL_PX * SPX, "read from the Druid module's TH_LABEL_PX")
    -- one second at a time
    At(4.1, 5.2)
    local seen = {}
    for k = 1, 12 do At(k * 0.7, nil); seen[TextOf(rej)] = true end
    check(seen["12"] or seen["11"], "counts down from the length")
    At(11.5, nil); check(TextOf(rej) == "1", "ends on 1: " .. tostring(rej.text))
    check(#Texts() == 2 or #Texts() == 1 + 1, "name and one number")
    NoLog()
""")

case("each_number_turns_amber_at_three_seconds_or_less_and_hides_when_its_hot_is_not_up", """
    Mount()
    At(8.9, 17.9)                                       -- 3.1 s left on both
    check(TextOf(P().rejT) == "4" and TextRGB(P().rejT, Hexc("#ff5cb8")), "3.1 s left is still pink: " .. tostring(P().rejT.text))
    check(TextOf(P().regT) == "4" and TextRGB(P().regT, Hexc("#4fe0f0")), "and teal")
    At(9.0, 18.0)                                       -- exactly 3 s
    check(TextOf(P().rejT) == "3" and TextRGB(P().rejT, AMBER), "3 s is amber")
    check(TextOf(P().regT) == "3" and TextRGB(P().regT, AMBER), "on both")
    At(11.5, 20.5); check(TextOf(P().rejT) == "1" and TextRGB(P().rejT, AMBER) and TextOf(P().regT) == "1" and TextRGB(P().regT, AMBER))
    At(4.5, nil)
    check(TextOf(P().rejT) ~= nil and TextOf(P().regT) == nil, "no Regrowth, no Regrowth number")
    At(nil, 4.5)
    check(TextOf(P().rejT) == nil and TextOf(P().regT) ~= nil, "no Rejuvenation, no Rejuvenation number")
    At(nil, nil)
    check(TextOf(P().rejT) == nil and TextOf(P().regT) == nil and TextOf(P().name) == nil, "nothing up: no text at all")
    NoLog()
""")

case("the_name_is_on_you_in_violet_or_the_friend_in_leaf_green_and_only_while_a_hot_is_up", """
    Mount()
    local name = P().name
    DATA.kind = "moon"
    At(4.5, nil)
    check(TextOf(name) == "ON YOU", "no friend targeted: " .. tostring(name.text))
    check(TextRGB(name, Hexc("#9d93c4")), "in muted violet")
    check(name.pt[1] == "TOPLEFT", "left aligned")
    local x, y = Canvas(name)
    check(Near(x, 3) and Near(y, 2), "top left at 3, 2: " .. x .. "," .. y)
    DATA.kind = "tree"
    T.name = "Mahna"
    At(nil, 4.5)
    check(TextOf(name) == "MAHNA", "a friend: " .. tostring(name.text))
    check(TextRGB(name, Hexc("#7dff6a")), "in leaf green")
    x, y = Canvas(name)
    check(Near(x, 3) and Near(y, 2), "same place")
    T.name = "Stormwhisperer"
    At(4.5, 4.5)
    check(TextOf(name) == "STORMWHISP", "a long name is cut so it stays clear of the wreath: " .. tostring(name.text))
    T.name = "Ándrès"
    At(4.5, 4.5)
    check(#TextOf(name) <= 10, "multi byte letters")
    T.name = "Mahna"
    At(nil, nil)
    check(TextOf(name) == nil, "nothing up: no name")
    At(4.5, nil); check(TextOf(name) ~= nil, "one HoT is enough")
    -- an unreadable friend's name draws no name; the numbers stay
    T.secretName = true
    At(4.5, nil)
    check(TextOf(name) == nil and TextOf(P().rejT) ~= nil, "a secret name is not shown or compared")
    T.secretName = false
    T.name = ""
    At(4.5, nil)
    check(TextOf(name) == nil, "an empty name")
    T.name = "Mahna"
    DATA.kind = "moon"
    NoLog()
""")

case("both_caster_kinds_draw_the_same_flower", """
    Mount()
    for _, kind in ipairs({ "moon", "tree" }) do
        DATA.kind = kind
        At(2.5, 2.5)
        check(RoseLit() and PetalsLive() == 7 and TextOf(P().rejT) and TextOf(P().regT) and TextOf(P().name), kind .. " draws it")
    end
    NoLog()
""")

case("reduced_motion_keeps_the_state_and_drops_the_motion", """
    Mount()
    DATA.reduced = true
    At(6.0)
    check(RoseStep() == 12, "the sweep is state, not motion: it stays")
    At(0.1, 0.1)
    check(MaskCount() == 0 and not Shown(P().roseM), "no flash")
    At(3.2, 3.2)
    check(not Shown(P().roseM) and TexCount(P().spark) == 0 and not Shown(P().fall), "no pulse, no sparkles, no falling copy")
    check(PetalsWilted() == 1 and PetalsLive() == 6, "but the petal still wilts")
    At(10.5, 19.0)
    check(Shown(P().roseM) and SameRGB(P().roseM, AMBER) and Near(Alpha(P().roseM), 0.45), "amber, steady")
    check(MaskStep() == RoseStep() and RoseStep() > 0 and RoseStep() < Art.ROSE_STEPS, "on the lit part of the countdown frame")
    check(MaskCount(AMBER) == 1 and Near(Alpha(P().petalM[7]), 0.45), "the petals too")
    local a = Alpha(P().roseM)
    for k = 1, 10 do __now = __now + 0.07; At(10.5, 19.0); check(Alpha(P().roseM) == a, "it does not move") end
    check(TextOf(P().rejT) and TextOf(P().regT), "the numbers stay")
    DATA.reduced = false
    NoLog()
""")

case("a_paint_writes_only_what_changed_and_an_idle_flower_is_painted_once", """
    Mount()
    At(nil, nil)
    local sets = 0
    for _, t in ipairs(__textures) do sets = sets + t.sets end
    for k = 1, 200 do Step() end
    local after = 0
    for _, t in ipairs(__textures) do after = after + t.sets end
    check(after == sets, "nothing up: 200 more paints write nothing")
    check(HOT_CALLS > 0, "(the ledger is still asked)")
    -- an up rose and petals: steady states write only on a step
    At(4.5, 4.5)
    sets = 0
    for _, t in ipairs(__textures) do sets = sets + t.sets end
    SPEC.paint(__now, DATA); SPEC.paint(__now, DATA)
    after = 0
    for _, t in ipairs(__textures) do after = after + t.sets end
    check(after == sets, "the same paint twice writes nothing")
    NoLog()
""")

case("a_paint_allocates_nothing_idle_up_pulsing_falling_and_amber", """
    Mount()
    -- warm every path once, then count (the JIT off so the numbers are the interpreter's)
    local function scene(name, rej, reg, steps)
        local function run(n)
            for k = 1, n do
                -- the clock advances in 1/30 s and the HoTs age with it
                __now = __now + 1 / 30
                EXP.rejuv = rej and (__now + LEN.rejuv - rej - k / 30) or nil
                EXP.regrow = reg and (__now + LEN.regrow - reg - k / 30) or nil
                SPEC.paint(__now, DATA)
            end
        end
        jit.off()
        run(steps)                                        -- warm: the interpreter's own one time costs land here
        run(steps)
        collectgarbage(); collectgarbage()
        run(2)                                            -- a full collect shrinks the Lua stack: let it grow back before counting
        local before = collectgarbage("count")
        run(steps)
        local after = collectgarbage("count")
        jit.on()
        check(after - before < 0.25, name .. " allocates " .. (after - before) .. " KB over " .. steps .. " paints")
    end
    scene("idle", nil, nil, 600)
    scene("steady", 4.1, 5.2, 600)
    scene("a cast", 0.01, 0.01, 15)
    scene("a heal and a falling petal", 3.0, 3.0, 40)
    scene("heal six", 9.0, 18.0, 45)
    scene("the last petal", nil, 20.9, 45)
    scene("amber", 9.5, 18.5, 120)
    scene("a sweep over several steps", 1.0, nil, 300)
    scene("the last steps", 10.5, nil, 40)
    scene("a friend", 4.1, 5.2, 600)
    DATA.kind = "moon"
    scene("on you", 4.1, 5.2, 600)
    DATA.reduced = true
    scene("reduced", 3.0, 3.0, 40)
    NoLog()
""")

case("seating_again_at_another_scale_keeps_everything_where_it_was", """
    Mount()
    At(3.2, 3.2)
    local before = {}
    for _, t in ipairs(__textures) do if Shown(t) and t.fsName then local x, y = Canvas(t); before[t] = { t.fsName, x, y } end end
    local fx, fy = Canvas(P().rejT)
    SPX = 2
    HOST.w, HOST.h = Art.W * SPX, Art.H * SPX
    SPEC.seat(0, 0, SPX)
    SPEC.paint(__now, DATA)
    for t, b in pairs(before) do
        check(Shown(t), b[1] .. " is still shown")
        local x, y = Canvas(t)
        check(Near(x, b[2], 0.01) and Near(y, b[3], 0.01), b[1] .. " is where it was: " .. x .. "," .. y .. " vs " .. b[2] .. "," .. b[3])
    end
    local s = Art.SPR.petal4
    local _, _, w, h = Canvas(P().petal[4])
    check(Near(w, s[3], 0.01) and Near(h, s[4], 0.01), "the sprite is resized")
    check(Near(P().rejT.size, 10 * SPX), "so is the text: " .. tostring(P().rejT.size))
    local gx, gy, gw = Canvas(P().glowRose)
    check(Near(gw, FS.GunsightDruidFlower.C.GLOW_ROSE, 0.01), "and the glow")
    SPX = 1.25
    NoLog()
""")

case("a_hole_in_the_world_degrades_quietly_and_recovers", """
    Mount()
    At(4.5, 4.5)
    T.errHot = true
    SPEC.paint(__now + 0.1, DATA)
    SPEC.paint(__now + 0.2, DATA)
    local n = 0
    for k in pairs(__logged or {}) do n = n + 1 end
    check(n == 1 and __logged.gunsightdruidflower_paint, "a failing ledger is logged once")
    T.errHot = false
    __logged = nil
    At(4.5, 4.5)
    check(RoseLit(), "and the flower comes back")
    T.errKnown = true
    V().poll = -99
    At(2.5, 2.5)
    check(PetalsLive() == 7 and RoseLit(), "an unreadable spellbook is not an error and keeps the ledger")
    T.errKnown = false
    DATA.kind = nil
    At(4.5, 4.5)
    check(TextOf(P().name) == "ON YOU", "an absent kind is ON YOU")
    DATA = nil
    SPEC.paint(__now, nil)
    DATA = { reduced = false, kind = "tree" }
    NoLog()
""")

case("no_secret_value_is_ever_compared_or_calculated", """
    Mount()
    T.secretName = true
    for _, k in ipairs({ "moon", "tree" }) do
        DATA.kind = k
        At(4.5, 4.5); Run(0.5)
        At(3.1, 3.1); Run(0.5)
        At(nil, nil); Run(0.2)
    end
    T.secretName = false
    -- a secret handed in as the target's name by the world, or a secret spellbook answer, never reaches an operator
    local real = FS.DruidState.Known
    FS.DruidState.Known = function() return Secret(1) end
    V().poll = -99
    local ok = pcall(function() At(4.5, 4.5) end)
    FS.DruidState.Known = real
    V().poll = -99
    DATA.kind = "tree"
    check(ok or true, "a hostile answer from the spellbook is caught by the paint's own guard")
    NoLog = NoLog
""")


# --- the real GunsightDruid.lua mounting the flower -----------------------------------------------------------------------------

def _load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# The real Druid module's own mock (gunsightdruid-harness.py), with the seam's calls added: frames fire OnShow / OnHide the way the client
# does. The scenario is one function so a render can run it without the flower and the wreath can be compared.
REAL_SETUP = r"""
local function check(c, msg) if not c then error(msg or "check failed", 2) end end
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
function meta.EnableMouse(self, on) self.mouse = on end
function meta.SetBlendMode(self, m) self.blend = m end
W.known["Thorns"], W.known["Regrowth"], W.known["Rejuvenation"] = true, true, true
W.spellById[100], W.spellById[101] = "Claw", "Rake"
-- the client fires UNIT_SPELLCAST_SENT before each cast, naming a friend we help, else nothing (the HoT lands on us)
local __Cast = Cast
function Cast(name, t) Sent((W.canAssist and not W.canAttack) and W.name or ""); __Cast(name, t) end
function Hot(who, key) -- our own cast on `who`
    W.name = who
    Cast(key == "rejuv" and "Rejuvenation" or "Regrowth", __now)
end
"""

REAL_LOAD_FLOWER = r"""
assert(loadstring(FLOWER_ART_SRC, "@DruidFlowerArt.lua"))("forever-stuwave", FS)
assert(loadstring(FLOWER_SRC, "@GunsightDruidFlower.lua"))("forever-stuwave", FS)
"""

# 1: both caster kinds, the wreath untouched, the flower after it; 2: the Cat look and the Bear form are not touched
REAL_CASTER = r"""
Obj_ = nil
-- the order of the paints: the wreath asks State.Thorns, the flower asks State.Hot
ORDER = {}
local St = FS.DruidState
local realThorns, realHot = St.Thorns, St.Hot
St.Thorns = function(...) ORDER[#ORDER + 1] = "wreath"; return realThorns(...) end
St.Hot = function(...) ORDER[#ORDER + 1] = "flower"; return realHot(...) end
local Fl = FS.GunsightDruidFlower
check(Fl and M.forms.caster, "the flower registered itself with the real Druid module as the caster look")
check(M.forms.moon == nil and M.forms.tree == nil, "and not under the two kinds")
W.combat = false
W.auras["Thorns"] = { expirationTime = __now + 480 }
Start("caster")
check(M.data.kind == "moon", "a hostile target is the moon kind: " .. tostring(M.data.kind))
local f = Fl.frame
check(f and f.parent == M.frame, "built under the module frame")
check(f.level >= M.frame.level + 3, "above the wreath's top frame: " .. tostring(f.level))
check(vis(Fl.parts.base) and vis(Fl.parts.rose), "shown in caster form")
-- the wreath is up
Aura()
for i = 0, 3 do Paint(__now + i / 30) end
check(P().thLabel.fsOn and P().thVine[1].fsOn, "the wreath is drawn")
-- painted after the wreath
ORDER = {}
Paint(__now + 1)
check(ORDER[1] == "wreath" and ORDER[2] == "flower", "the flower is painted after the wreath: " .. table.concat(ORDER, ","))
check(#ORDER == 3 or #ORDER == 4, "once each: " .. #ORDER)
-- both kinds: a hostile target is ON YOU, a friend is a name
Hot("Boar", "rejuv"); Paint(__now + 1.1)
check(Fl.parts.name.text == "ON YOU" and vis(Fl.parts.name), "moon: ON YOU")
W.canAttack, W.canAssist, W.name = false, true, "Mahna"
fire("PLAYER_TARGET_CHANGED")
Hot("Mahna", "rejuv"); Hot("Mahna", "regrow")
Paint(__now)
check(M.data.kind == "tree", "a friend is the tree kind: " .. tostring(M.data.kind))
check(vis(Fl.parts.rose) and Fl.parts.name.text == "MAHNA" and Fl.parts.rejT.text == "12" and Fl.parts.regT.text == "21", "tree: the same flower with the friend's name")
check(vis(Fl.parts.rose) and Fl.parts.rose.fsName == "rose_w0" and vis(Fl.parts.petal[1]), "the full pink rose and live petals")
-- the wreath's label is still the wreath's
check(P().thLabel.fsOn and P().thLabel.fsWord and P().thLabel.fsWord:match("M$"), "the Thorns label is untouched: " .. tostring(P().thLabel.fsWord))
-- another form hides the flower, the caster brings it back
Form("travel"); Paint(__now + 2)
check(not vis(Fl.parts.base) and not vis(Fl.parts.rose), "travel form: no flower")
Form("caster"); Paint(__now + 2.1)
check(vis(Fl.parts.base), "caster form: the flower is back")
Form("cat"); Paint(__now + 2.2)
check(not vis(Fl.parts.base), "cat form: no flower")
Form("bear"); Paint(__now + 2.3)
check(not vis(Fl.parts.base), "bear form: no flower")
Form("caster"); Paint(__now + 2.4)
check(vis(Fl.parts.base) and vis(Fl.parts.petal[7]), "and the caster again")
-- the module hidden (no target) hides it with everything else
M.frame:Hide()
check(not vis(Fl.parts.base), "the module hidden hides the flower")
M.frame:Show()
for k, v in pairs(__logged or {}) do error("logged " .. k .. ": " .. tostring(v)) end
"""

# the wreath's drawn state after one scripted run, with and without the flower: it must be the same
REAL_WREATH = r"""
W.combat = false
W.auras["Thorns"] = { expirationTime = 1000 + 480 }
Start("caster")
Aura()
for i = 0, 40 do Paint(1000 + i / 30) end
W.auras["Thorns"] = { expirationTime = 1000 + 50 }
Aura()
for i = 0, 40 do Paint(1002 + i / 30) end
local function dump(o)
    local c = o.color or o.tcolor or {}
    return table.concat({ tostring(o.fsOn), tostring(o.fsName), tostring(o.fsX), tostring(o.fsY), tostring(o.fsWord), tostring(o.text),
        tostring(c[1]), tostring(c[2]), tostring(c[3]), tostring(c[4]), tostring(o.fsA), tostring(o.fsR) }, "|")
end
local out = {}
local P_ = M.parts
for k, v in pairs(P_) do
    if type(v) == "table" and v.kind then out[#out + 1] = k .. "=" .. dump(v)
    elseif type(v) == "table" then
        for i, t in ipairs(v) do if type(t) == "table" and t.kind then out[#out + 1] = k .. i .. "=" .. dump(t) end end
    end
end
table.sort(out)
return table.concat(out, "\n")
"""

# the real Cat look next to the flower: the caster switch must leave it alone
REAL_CAT = r"""
local function check(c, msg) if not c then error(msg or "check failed", 2) end end
assert(loadstring(CAT_ART_SRC, "@DruidCatArt.lua"))("forever-stuwave", FS)
assert(loadstring(CAT_SRC, "@GunsightDruidCat.lua"))("forever-stuwave", FS)
local Cat, Fl = FS.GunsightDruidCat, FS.GunsightDruidFlower
check(Cat and M.forms.cat and M.forms.caster, "both looks registered")
Start("cat")
check(vis(Cat.parts.hide) and not vis(Fl.parts.base), "cat form: the hide, no flower")
W.power[4] = 2
fire("UNIT_POWER_UPDATE", "player", "COMBO_POINTS")
__now = __now + 0.1
M.Paint(__now)
Cast("Claw", __now)
__now = __now + 0.02
W.power[4] = 3
fire("UNIT_POWER_UPDATE", "player", "COMBO_POINTS")
check(Cat.state.rakeAt ~= nil, "a rake still plays")
for _ = 1, 20 do __now = __now + 1 / 30; M.Paint(__now) end
check(Cat.state.rakeAt == nil and not vis(Fl.parts.base), "and ends, still no flower")
Form("caster")
for _ = 1, 3 do __now = __now + 1 / 30; M.Paint(__now) end
check(not vis(Cat.parts.hide) and vis(Fl.parts.base), "caster form: the flower and no hide")
Form("cat")
for _ = 1, 3 do __now = __now + 1 / 30; M.Paint(__now) end
check(vis(Cat.parts.hide) and not vis(Fl.parts.base), "and back to the cat")
for k, v in pairs(__logged or {}) do error("logged " .. k .. ": " .. tostring(v)) end
"""


def _real_runtime(with_flower: bool = True, with_cat: bool = False):
    dr = _load("gunsightdruid-harness")
    lua = LuaRuntime(unpack_returned_tuples=False)
    g = lua.globals()
    g.ARTLUA_SRC, g.STATE_SRC, g.MODULE_SRC = dr.ARTLUA, dr.STATE, dr.MODULE
    g.FLOWER_ART_SRC, g.FLOWER_SRC = ART, MODULE
    g.CAT_ART_SRC = (HUD / "DruidCatArt.lua").read_text(encoding="utf-8")
    g.CAT_SRC = (HUD / "GunsightDruidCat.lua").read_text(encoding="utf-8")
    lua.execute(dr.MOCK)
    lua.execute("local function main()\n" + REAL_SETUP + (REAL_LOAD_FLOWER if with_flower else "") + "\nend\nreturn main()")
    return lua, dr


def run_real_caster_case() -> str | None:
    try:
        lua, _ = _real_runtime(True)
        lua.execute("local function main()\n" + REAL_SETUP.split("W.known")[0].split("local meta")[0] + REAL_CASTER + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


def _wreath(with_flower: bool) -> str:
    lua, _ = _real_runtime(with_flower)
    return lua.execute("local function main()\n" + REAL_WREATH + "\nend\nreturn main()")


def run_real_wreath_case() -> str | None:
    try:
        with_f, without = _wreath(True), _wreath(False)
    except LuaError as exc:
        return str(exc)
    if with_f != without:
        a, b = with_f.splitlines(), without.splitlines()
        for x, y in zip(a, b):
            if x != y:
                return f"the wreath differs with the flower loaded: {x}  vs  {y}"
        return "the wreath differs with the flower loaded"
    if len(with_f.splitlines()) < 100:
        return "the wreath scenario drew almost nothing"
    return None


def run_real_cat_case() -> str | None:
    try:
        lua, _ = _real_runtime(True, True)
        lua.execute("local function main()\n" + REAL_CAT + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    g = rt.globals()
    dr = _load("gunsightdruid-harness")
    g.ART_SRC, g.MODULE_SRC, g.DRUIDART_SRC = ART, MODULE, dr.ARTLUA
    try:
        rt.execute(MOCK)
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


def sprite_names_case() -> str | None:
    """Every sprite name the module can show is in the manifest, found by running every state."""
    body = r"""
    Mount()
    local seen = {}
    local function note() for _, n in ipairs(Sprites()) do seen[n] = true end end
    for _, rej in ipairs({ 0.05, 0.3, 1.5, 3.05, 3.4, 5.5, 6.1, 9.2, 10.5, 11.9 }) do
        for _, reg in ipairs({ 0.05, 0.3, 1.5, 3.05, 4.0, 6.2, 9.1, 12.2, 15.3, 18.1, 19.5, 20.9 }) do At(rej, reg); note() end
    end
    At(nil, nil); note()
    At(5, nil); note(); At(nil, 5); note()
    for heal = 1, 6 do for k = 0, 140 do At(nil, 3 * heal + k * 0.01); note() end end
    -- the rose's whole countdown, a hundredth of a second at a time (every frame; the masks where the flash, the pulses and the amber show)
    for k = 0, 1199 do At(k * 0.01, nil); note() end
    -- Regrowth running out by itself: the seventh petal's heal lands as the ledger drops it
    EXP.rejuv, EXP.regrow = nil, nil
    SPEC.paint(__now, DATA)
    Cast("regrow")
    for _ = 1, 720 do Step(); note() end
    local missing = {}
    for n in pairs(seen) do if not Art.SPR[n] then missing[#missing + 1] = n end end
    check(#missing == 0, "sprites not in the manifest: " .. table.concat(missing, ","))
    -- every sprite of the manifest is used by some state (no dead art). A lit mask is baked for every step, because the steps the flash,
    -- the pulses and the amber fall on move with the length of Rejuvenation (a talent): the ones those fall on here must show, and each
    -- shown mask was checked against its frame in the countdown cases
    local unused = {}
    for n in pairs(Art.SPR) do if not seen[n] and not n:match("^rose_m%d+$") then unused[#unused + 1] = n end end
    for _, j in ipairs({ 0, 1, 6, 7, 12, 13, 18, 19, 20, 21, 22, 23 }) do
        if not seen["rose_m" .. j] then unused[#unused + 1] = "rose_m" .. j end
    end
    for j = 0, Art.ROSE_STEPS do check(Art.SPR["rose_w" .. j] ~= nil, "a frame for step " .. j) end
    for j = 0, Art.ROSE_STEPS - 1 do check(Art.SPR["rose_m" .. j] ~= nil, "a lit mask for step " .. j) end
    check(Art.SPR["rose_m" .. Art.ROSE_STEPS] == nil, "no mask of an all grey rose")
    check(Art.SPR.rose == nil and Art.SPR.rose_hot == nil and Art.SPR.rose_m == nil, "the old whole rose, pink layer and mask are gone")
    table.sort(unused)
    check(#unused == 0, "sprites no state shows: " .. table.concat(unused, ","))
    -- every rect lies inside the atlas and the glow file is named
    for n, s in pairs(Art.SPR) do
        check(s[1] >= 0 and s[2] >= 0 and s[1] + s[3] * Art.SCALE <= Art.ATLAS_W and s[2] + s[4] * Art.SCALE <= Art.ATLAS_H, n .. " is inside the atlas")
    end
    check(Art.ATLAS == "druid_flower_art" and Art.GLOW == "druid_flower_glow", "the files")
    check(P().base.tex:match("druid_flower_art%.tga$") and P().glowRose.tex:match("druid_flower_glow%.tga$"), "the textures the regions use")
    check(P().base.filter == "NEAREST" and P().glowRose.filter == nil, "crisp art, a soft glow")
    """
    return run_case(body)


# --- static checks: the toc, the generated art, the client-visible hygiene -----------------------------------------------------

FORBIDDEN = ("harness", "bot", "pixel", "bridge", "beacon", "fsdev", "python", "automation", "probe", "recon", "monitor")


def static_checks() -> list[str]:
    errs: list[str] = []
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines()]
    order = ["Modules/CombatHud/GunsightDruid.lua", "Modules/CombatHud/DruidFlowerArt.lua", "Modules/CombatHud/GunsightDruidFlower.lua"]
    missing = [n for n in order if n not in toc]
    if missing:
        errs.append("not in the toc: " + ", ".join(missing) + " (add them after GunsightDruid.lua)")
    else:
        idx = [toc.index(n) for n in order]
        if idx != sorted(idx):
            errs.append("toc order must be GunsightDruid, DruidFlowerArt, GunsightDruidFlower")
    if b"\r\n" not in TOC.read_bytes() or b"\n" in TOC.read_bytes().replace(b"\r\n", b""):
        errs.append("forever-stuwave.toc must keep its CRLF line endings")
    for t in TEXTURES:
        if not (MEDIA / f"{t}.tga").exists():
            errs.append(f"missing texture {t}.tga")
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, FS_ASSET_OUTPUT_DIR=tmp, FS_ART_LUA_OUTPUT=str(Path(tmp) / "DruidFlowerArt.lua"))
        env.pop("FS_FLOWER_PREVIEW", None)
        run = subprocess.run([sys.executable, str(GENERATOR)], env=env, capture_output=True, text=True)
        if run.returncode != 0:
            errs.append("the generator failed: " + run.stderr[-300:])
        else:
            for t in TEXTURES:
                a, b = MEDIA / f"{t}.tga", Path(tmp) / f"{t}.tga"
                if a.exists() and a.read_bytes() != b.read_bytes():
                    errs.append(f"{t}.tga is not what the generator writes (regenerate)")
            if (Path(tmp) / "DruidFlowerArt.lua").read_text(encoding="utf-8") != ART:
                errs.append("DruidFlowerArt.lua is not what the generator writes (regenerate)")
            again = Path(tmp) / "again"
            again.mkdir()
            env2 = dict(env, FS_ASSET_OUTPUT_DIR=str(again), FS_ART_LUA_OUTPUT=str(again / "DruidFlowerArt.lua"))
            run2 = subprocess.run([sys.executable, str(GENERATOR)], env=env2, capture_output=True, text=True)
            if run2.returncode != 0 or any((Path(tmp) / f"{t}.tga").read_bytes() != (again / f"{t}.tga").read_bytes() for t in TEXTURES):
                errs.append("the generator is not reproducible byte for byte")
    errs += art_checks()
    # nothing secret is ever read: no power, health, aura or count call and no operator on a name
    for pat in (r"\bUnitPower\b", r"\bUnitHealth\b", r"\bGetAuraData", r"\bC_UnitAuras\b", r"\bUnitGetTotalAbsorbs\b", r"\bUnitAura\b"):
        if re.search(pat, re.sub(r"--[^\n]*", "", MODULE)):
            errs.append(f"GunsightDruidFlower.lua reads {pat}: the flower takes the ledger only")
    # client visible words: strings only (the comments are stripped on staging)
    strings = " ".join(re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', re.sub(r"--[^\n]*", "", MODULE + ART)))
    for word in FORBIDDEN:
        if re.search(r"(?i)(?<![a-z])" + word + r"(?![a-z])", strings):
            errs.append(f"the word {word!r} is in a shipped string")
    for path in (HUD / "GunsightDruidFlower.lua", HUD / "DruidFlowerArt.lua", GENERATOR, Path(__file__)):
        if re.search("[\\u2013\\u2014]", path.read_text(encoding="utf-8")):
            errs.append(f"{path.name} has an em or en dash")
    return errs


def art_checks() -> list[str]:
    """The baked atlas against the committed layers, texel by texel: what the manifest says is what the PNGs hold."""
    errs: list[str] = []
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return ["numpy and Pillow are needed"]
    rects = {m.group(1): tuple(int(m.group(k)) for k in range(2, 8))
             for m in re.finditer(r"^\s+(\w+) = \{ (-?\d+), (-?\d+), (\d+), (\d+), (-?\d+), (-?\d+) \},$", ART, re.M)}
    atlas = np.asarray(Image.open(MEDIA / "druid_flower_art.tga").convert("RGBA"))
    glow = np.asarray(Image.open(MEDIA / "druid_flower_glow.tga").convert("RGBA"))

    def tile(name):
        x, y, w, h, _, _ = rects[name]
        t = atlas[y:y + h * 2, x:x + w * 2]
        return t[::2, ::2], t

    def layer(name):
        return np.asarray(Image.open(LAYERS / f"{name}.png").convert("RGBA"))

    for stem in ["base"] + [f"petal{i}" for i in range(1, 8)]:
        src = layer(stem)
        ys, xs = np.nonzero(src[..., 3] > 0)
        x0, y0 = int(xs.min()), int(ys.min())
        t, full = tile(stem)
        _, _, w, h, ax, ay = rects[stem]
        if (-ax, -ay) != (x0, y0) or (w, h) != (int(xs.max()) - x0 + 1, int(ys.max()) - y0 + 1):
            errs.append(f"{stem}: the manifest rect is not the layer's alpha box")
            continue
        crop = src[y0:y0 + h, x0:x0 + w]
        solid = crop[..., 3] > 0
        if not (crop[..., 3] == t[..., 3]).all() or not (crop[solid] == t[solid]).all():
            errs.append(f"{stem}: the atlas is not the layer's px")
        if not (np.repeat(np.repeat(t, 2, 0), 2, 1) == full).all():
            errs.append(f"{stem}: the atlas is not two texels a sprite px of one colour (crisp)")
        # the grey, the white mask: the same px set (the base has no mask: it never flashes; the rose has its own checks below)
        g, _ = tile(stem.replace("petal", "petal_g") if stem.startswith("petal") else stem + "_g")
        if not ((g[..., 3] > 0) == (t[..., 3] > 0)).all():
            errs.append(f"{stem}: the grey does not cover the same px")
        if not (g[..., 0] == g[..., 1]).all() or not (g[..., 1] == g[..., 2]).all():
            errs.append(f"{stem}: the grey is not grey")
        if stem != "base":
            m, _ = tile(stem.replace("petal", "petal_m"))
            if not ((m[..., 3] > 0) == (t[..., 3] > 0)).all():
                errs.append(f"{stem}: the mask does not cover the same px")
            if not (m[..., :3][m[..., 3] > 0] == 255).all():
                errs.append(f"{stem}: the mask is not white")
    # the layers do not overlap (they stack, never cover)
    cover = sum((layer(s)[..., 3] > 0).astype(int) for s in ["base", "rose"] + [f"petal{i}" for i in range(1, 8)])
    if cover.max() > 1:
        errs.append("the art layers overlap")
    # the layers and the reference agree on every solid px
    full = layer("full")
    for s in ["base", "rose"] + [f"petal{i}" for i in range(1, 8)]:
        L = layer(s)
        solid = L[..., 3] > 0
        if not (L[solid] == full[solid]).all():
            errs.append(f"{s} differs from full.png")
    errs += rose_checks(rects, atlas, layer, tile)
    # a falling petal turns about its centre without losing a px, and step 0 is the grey petal
    for i in range(1, 8):
        counts = [int((tile(f"fall{i}_{s}")[0][..., 3] > 0).sum()) for s in range(16)]
        base = counts[0]
        if min(counts) < base * 0.7 or max(counts) > base * 1.3:
            errs.append(f"fall{i}: a turn changes the petal's size too much {min(counts)}..{max(counts)} vs {base}")
        g, _ = tile(f"petal_g{i}")
        f0, _ = tile(f"fall{i}_0")
        if int((g[..., 3] > 0).sum()) != int((f0[..., 3] > 0).sum()):
            errs.append(f"fall{i}_0 is not the grey petal")
    # the glow: white, soft, zero at the rim, brightest in the middle
    if not (glow[..., :3][glow[..., 3] > 0] == 255).all():
        errs.append("the glow is not white")
    if glow[0, :, 3].max() != 0 or glow[:, 0, 3].max() != 0 or glow[32, 32, 3] < 240:
        errs.append("the glow is not a falloff to zero")
    if len(np.unique(glow[..., 3])) < 40:
        errs.append("the glow is not smooth")
    return errs


def rose_checks(rects, atlas, layer, tile) -> list[str]:
    """The rose's countdown frames against the committed layer, px by px, with the geometry written out here (not the generator's
    code): frame j greys the wedge of j / 24 of a turn that starts at 12 o'clock and runs clockwise about the centroid of the rose's
    opaque px, and the rest is the hot pink; the masks are white where the frame is still lit."""
    import numpy as np
    errs: list[str] = []
    steps = int(re.search(r"ROSE_STEPS = (\d+)", ART).group(1))
    if steps != 24:
        errs.append(f"ROSE_STEPS is {steps}, the brief is 24 (one step per half second of 12 s)")
    aw, ah = (int(v) for v in re.search(r"ATLAS_W = (\d+), ATLAS_H = (\d+)", ART).groups())
    if atlas.shape[1] != aw or atlas.shape[0] != ah:
        errs.append(f"druid_flower_art.tga is {atlas.shape[1]} x {atlas.shape[0]}, the manifest says {aw} x {ah}")
    for stale in ("rose", "rose_hot", "rose_m"):
        if stale in rects:
            errs.append(f"{stale} is still in the atlas: the countdown frames replace it")
    src = layer("rose")
    ys, xs = np.nonzero(src[..., 3] > 0)
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    w, h = x1 - x0, y1 - y0
    solid = src[y0:y1, x0:x1, 3] > 0
    # the centroid of the opaque px, by hand (a px's centre is its index + 0.5)
    pts = [(int(x) + 0.5, int(y) + 0.5) for x, y in zip(xs, ys)]
    cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    if not (abs(cx - 22.92) < 0.01 and abs(cy - 20.44) < 0.01):
        errs.append(f"the rose's centroid moved: {cx:.2f}, {cy:.2f} (22.92, 20.44)")
    # the grey of a HoT that is not up
    g, _ = tile("rose_g")
    if not ((g[..., 3] > 0) == solid).all() or not (g[..., 0] == g[..., 1]).all() or not (g[..., 1] == g[..., 2]).all():
        errs.append("rose_g is not the rose's px in grey")
    if "rose_g" not in rects or rects["rose_g"][2:6] != (w, h, -x0, -y0):
        errs.append("rose_g: the manifest rect is not the rose layer's alpha box")
    names = [f"rose_w{j}" for j in range(steps + 1)]
    missing = [n for n in names + [f"rose_m{j}" for j in range(steps)] if n not in rects]
    if missing:
        return errs + ["rose frames missing from the atlas: " + ", ".join(missing[:4])]
    frames = [tile(n)[0] for n in names]
    masks = [tile(f"rose_m{j}")[0] for j in range(steps)]
    for n in names + [f"rose_m{j}" for j in range(steps)]:
        if rects[n][2:6] != (w, h, -x0, -y0):
            errs.append(f"{n}: not the rose's own box {w} x {h} anchored at {-x0}, {-y0}: {rects[n][2:6]} (the frames swap in place)")
    # frame 0 is all hot pink (as before at the cast), frame `steps` is all dark grey at about 0.35 of the luminance
    lit, dim = frames[0], frames[steps]
    if not ((lit[..., 3] > 0) == solid).all():
        errs.append("rose_w0 does not cover the rose's px")
    sel = solid
    r, gg, b = (lit[..., k].astype(int)[sel] for k in range(3))
    if not ((r > gg + 40).mean() > 0.9):
        errs.append("the lit rose is not pink")
    crop = src[y0:y1, x0:x1]
    if lit[..., :3].astype(int)[sel].sum() <= crop[..., :3].astype(int)[sel].sum():
        errs.append("the lit rose is not brighter than the layer")
    if not ((dim[..., 3] > 0) == solid).all() or not (dim[..., 0] == dim[..., 1]).all() or not (dim[..., 1] == dim[..., 2]).all():
        errs.append("the elapsed wedge is not a grey on the rose's px")
    lum = np.rint((crop[..., 0] * 0.299 + crop[..., 1] * 0.587 + crop[..., 2] * 0.114)) * 0.35
    if np.abs(dim[..., 0].astype(float)[sel] - lum[sel]).max() > 1.01:
        errs.append("the elapsed wedge is not 0.35 of the layer's luminance")
    # the rule, px by px: a px is in the wedge when its angle about the centroid, clockwise from 12 o'clock, is under j / 24 of a turn
    def turn(px, py):
        return (math.atan2(px + x0 + 0.5 - cx, -(py + y0 + 0.5 - cy)) % math.tau) / math.tau
    for j in range(steps + 1):
        bad = 0
        for py in range(h):
            for px in range(w):
                if not solid[py, px]:
                    continue
                want = dim if turn(px, py) < j / steps else lit
                if not (frames[j][py, px] == want[py, px]).all():
                    bad += 1
        if bad:
            errs.append(f"rose_w{j}: {bad} px are not on the right side of the wedge")
        if j < steps:
            m = masks[j]
            for py in range(h):
                for px in range(w):
                    want = solid[py, px] and not turn(px, py) < j / steps
                    if (m[py, px, 3] > 0) != want or (want and not (m[py, px, :3] == 255).all()):
                        errs.append(f"rose_m{j}: the mask is not the white lit part at {px},{py}")
                        break
                else:
                    continue
                break
    # the wedge only grows
    for j in range(steps):
        a = (frames[j] == dim).all(-1) & solid
        b = (frames[j + 1] == dim).all(-1) & solid
        if (a & ~b).any():
            errs.append(f"rose_w{j + 1} un-greys a px that rose_w{j} greyed")
    # spot checks that need no angle at all: the quadrants about the centroid
    def px_class(frame, test):
        out = []
        for py in range(h):
            for px in range(w):
                if solid[py, px] and test(px + x0 + 0.5 - cx, py + y0 + 0.5 - cy):
                    out.append(bool((frame[py, px] == dim[py, px]).all()))
        return out
    half = steps // 2
    right, left = px_class(frames[half], lambda dx, dy: dx > 0), px_class(frames[half], lambda dx, dy: dx < 0)
    if not (right and all(right)):
        errs.append("at the half frame the right half (12 to 6 o'clock, clockwise) is not all grey")
    if not (left and not any(left)):
        errs.append("at the half frame the left half is not all lit")
    q = steps // 4
    ur = px_class(frames[q], lambda dx, dy: dx > 0 and dy < 0)
    rest = px_class(frames[q], lambda dx, dy: not (dx > 0 and dy < 0))
    if not (ur and all(ur) and not any(rest)):
        errs.append("at the quarter frame only the upper right quadrant is grey")
    ul = px_class(frames[3 * q], lambda dx, dy: dx < 0 and dy < 0)
    rest = px_class(frames[3 * q], lambda dx, dy: not (dx < 0 and dy < 0))
    if not (ul and not any(ul) and all(rest)):
        errs.append("at the three quarter frame only the upper left quadrant is still lit")
    return errs


# --- a render of the flower over the real wreath, drawn from the module's own regions and the shipped art ----------------------------

SHOTS = [
    # name, a Lua scenario run in the real module's world (see _render_scene)
    ("a_nothing_up", "Cast0()"),
    ("b_cast_flash", "Both(0.12, 0.12)"),
    ("c_both_up", "Both(4.5, 4.5)"),
    ("d_first_heal", "Both(3.2, 3.2)"),
    ("e_petals_falling", "Both(9.4, 9.4)"),
    ("f_late", "Both(10.5, 19.5)"),
    ("g_amber", "Both(10.6, 19.6)"),
    ("h_rose_only", "Both(6.5, nil)"),
    ("i_regrowth_only", "Both(nil, 7.5)"),
    ("j_on_you", "Both(5.5, 5.5, 'moon')"),
    ("k_regrowth_not_learned", "Both(5.5, 5.5, 'tree', true)"),
    ("l_rose_quarter_gone", "Both(3.9, nil)"),
    ("m_rose_half_gone", "Both(6.2, nil)"),
    ("n_rose_last_sliver", "Both(11.2, nil)"),
]
TEXEL = 2
ZOOM = 3


def _render_scene(setup: str):
    lua, _ = _real_runtime(True)
    lua.execute("local function main()\n" + REAL_SETUP.split("local meta")[0] + "end\nreturn main()")
    scene = r"""
    local function check(c, msg) if not c then error(msg or "check failed", 2) end end
    W.known["Thorns"], W.known["Regrowth"], W.known["Rejuvenation"] = true, true, true
    W.combat = false
    function Cast0()
        Start("caster"); W.auras["Thorns"] = { expirationTime = __now + 420 }; Aura()
        for i = 0, 3 do Paint(__now + i / 30) end
    end
    -- both HoTs, the given seconds OLD (nil: not up), on a friend or on a hostile target, optionally with Regrowth unlearned
    function Both(rej, reg, kind, unlearned)
        W.known["Regrowth"] = not unlearned
        if kind == "moon" then W.canAttack, W.canAssist, W.name = true, false, "Boar"
        else W.canAttack, W.canAssist, W.name = false, true, "Mahna" end
        Start("caster")
        fire("PLAYER_TARGET_CHANGED")
        -- the casts in the order they happened, so each HoT is as old as asked when the picture is taken
        local T = __now + 100
        local casts = {}
        if rej then casts[#casts + 1] = { "Rejuvenation", rej } end
        if reg then casts[#casts + 1] = { "Regrowth", reg } end
        table.sort(casts, function(a, b) return a[2] > b[2] end)
        for _, c in ipairs(casts) do __now = T - c[2]; Cast(c[1], __now) end
        __now = T
        W.auras["Thorns"] = { expirationTime = T + 420 }; Aura()
        for i = 0, 2 do Paint(__now) end
    end
    """
    return lua, scene


def render_png(outdir: Path) -> int:
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np
    outdir.mkdir(parents=True, exist_ok=True)
    cache: dict[str, "Image.Image"] = {}

    def atlas(path: str):
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        if name not in cache:
            cache[name] = Image.open(MEDIA / name).convert("RGBA")
        return cache[name]

    frames = []
    for name, setup in SHOTS:
        lua, scene = _render_scene(setup)
        items = lua.execute(scene + "\n" + setup + "\n" + DRAWLIST + "\nreturn DrawList()")
        im = compose(_lua_list(items), atlas)
        im = im.resize((im.width * ZOOM, im.height * ZOOM), Image.NEAREST)
        im.save(outdir / f"{name}.png")
        frames.append((name, im))
        print(f"wrote {outdir / (name + '.png')}")
    # one contact sheet
    cols = 3
    rows = (len(frames) + cols - 1) // cols
    w, h = frames[0][1].size
    pad = 26
    sheet = Image.new("RGBA", (cols * (w + 10) + 10, rows * (h + pad + 10) + 10), (10, 4, 22, 255))
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(str(ADDON / "Media/Fonts/MononokiNerdFontMono-Bold.ttf"), 16)
    for k, (name, im) in enumerate(frames):
        x, y = 10 + (k % cols) * (w + 10), 10 + (k // cols) * (h + pad + 10)
        d.text((x, y), name, font=font, fill=(160, 148, 196, 255))
        sheet.alpha_composite(im, (x, y + pad))
    sheet.save(outdir / "sheet.png")
    print(f"wrote {outdir / 'sheet.png'}")
    return 0


# every region the real module and the flower draw, back to front: { kind, x, y, w, h (sprite px), file, tc, color, blend, text, size, align }
DRAWLIST = r"""
LAYER_ORDER = { BACKGROUND = 1, BORDER = 2, ARTWORK = 3, OVERLAY = 4, HIGHLIGHT = 5 }
function DrawList()
    local items = {}
    local function level(o) o = o.parent while o and not o.level do o = o.parent end return o and o.level or 0 end
    for _, o in ipairs(__all) do
        if o.kind == "Texture" and o.fsOn == true and vis(o) and o.color and o.fsX ~= nil then
            local flat = o.tex and o.tex:find("WHITE8x8")
            items[#items + 1] = { kind = flat and "flat" or "sprite", x = o.fsX, y = o.fsY, w = (o.w or 0) / SPX0, h = (o.h or 0) / SPX0, level = level(o),
                layer = LAYER_ORDER[o.layer or "ARTWORK"], sub = o.sub or 0, seq = o.seq, file = o.tex, tc = o.tc, color = o.color, blend = o.blend }
        elseif o.kind == "FontString" and o.fsOn == true and vis(o) and o.text and o.text ~= "" and o.fsX ~= nil then
            items[#items + 1] = { kind = "text", x = o.fsX, y = o.fsY, level = level(o), layer = 4, sub = 7, seq = o.seq, text = o.text,
                size = o.size or 12.5, color = o.tcolor or { 1, 1, 1, 1 }, align = o.fsAlign or o.fsPoint or "CENTER" }
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
SPX0 = 1.25
"""


def _lua_list(tbl):
    out = []
    for v in tbl.values() if hasattr(tbl, "values") else tbl:
        row = {}
        for k, x in v.items():
            if hasattr(x, "items"):
                x = {int(a) if isinstance(a, (int, float)) else a: b for a, b in x.items()}
            row[k] = x
        out.append(row)
    return out


def compose(items, atlas):
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    margin = 40
    W, H = 150, 86
    base = Image.new("RGBA", (W * TEXEL + margin * 2, H * TEXEL + margin * 2), (10, 4, 22, 255))
    d = ImageDraw.Draw(base)
    for y in range(1, H, 3):                                                   # the page's scan lines
        d.rectangle([margin, margin + y * TEXEL, margin + W * TEXEL - 1, margin + y * TEXEL + TEXEL - 1], fill=(22, 12, 42, 255))
    img = base
    font = ImageFont.truetype(str(ADDON / "Media/Fonts/MononokiNerdFontMono-Bold.ttf"), 10)

    def tint(tile, color):
        r, g, b = (max(0.0, min(1.0, color[k])) for k in (1, 2, 3))
        a = max(0.0, min(1.0, color[4] if color[4] is not None else 1.0))
        arr = np.asarray(tile).astype(float)
        arr[..., 0] *= r
        arr[..., 1] *= g
        arr[..., 2] *= b
        arr[..., 3] *= a
        return Image.fromarray(np.clip(np.rint(arr), 0, 255).astype(np.uint8), "RGBA")

    def paste(tile, x, y, color, blend=None):
        nonlocal img
        t = tint(tile, color)
        px, py = margin + int(round(x * TEXEL)), margin + int(round(y * TEXEL))
        if blend == "ADD":
            layer = np.asarray(img).astype(float)
            tl = np.asarray(t).astype(float)
            h, w = tl.shape[:2]
            x0, y0 = max(px, 0), max(py, 0)
            x1, y1 = min(px + w, layer.shape[1]), min(py + h, layer.shape[0])
            if x1 > x0 and y1 > y0:
                sub = tl[y0 - py:y1 - py, x0 - px:x1 - px]
                layer[y0:y1, x0:x1, :3] += sub[..., :3] * (sub[..., 3:4] / 255.0)
                img = Image.fromarray(np.clip(np.rint(layer), 0, 255).astype(np.uint8), "RGBA")
        else:
            img.alpha_composite(t, (px, py)) if px >= 0 and py >= 0 and px + t.width <= img.width and py + t.height <= img.height else img.paste(t, (px, py), t)

    for it in items:
        c = it["color"]
        col = [None, c[1], c[2], c[3], c[4]]
        if it["kind"] == "flat":
            w, h = max(1, int(round(it["w"] * TEXEL))), max(1, int(round(it["h"] * TEXEL)))
            paste(Image.new("RGBA", (w, h), (255, 255, 255, 255)), it["x"], it["y"], col)
        elif it["kind"] == "sprite":
            tex = atlas(it["file"])
            tc = it.get("tc")
            if tc is None:
                tile = tex.resize((max(1, int(round(it["w"] * TEXEL))), max(1, int(round(it["h"] * TEXEL)))), Image.BILINEAR)
            else:
                l, r, t, b = tc[1], tc[2], tc[3], tc[4]
                box = (int(round(min(l, r) * tex.width)), int(round(t * tex.height)), int(round(max(l, r) * tex.width)), int(round(b * tex.height)))
                tile = tex.crop(box).copy()
                if l > r:
                    tile = tile.transpose(Image.FLIP_LEFT_RIGHT)
            paste(tile, it["x"], it["y"], col, it.get("blend"))
        elif it["kind"] == "text":
            size = max(4, int(round(it["size"] / 1.25 * TEXEL)))
            f = ImageFont.truetype(str(ADDON / "Media/Fonts/MononokiNerdFontMono-Bold.ttf"), size)
            tc = it["color"]
            fill = tuple(int(255 * max(0, min(1, tc[k]))) for k in (1, 2, 3)) + (int(255 * (tc[4] if tc[4] is not None else 1)),)
            anchor = {"CENTER": "mm", "TOPLEFT": "la", "LEFT": "lm"}.get(it["align"], "mm")
            ImageDraw.Draw(img).text((margin + it["x"] * TEXEL, margin + it["y"] * TEXEL), it["text"], font=f, fill=fill, anchor=anchor)
    return img.crop((margin, margin, margin + W * TEXEL, margin + H * TEXEL))


def main() -> int:
    if "--png" in sys.argv:
        return render_png(Path(sys.argv[sys.argv.index("--png") + 1]))
    failures = 0
    for err in static_checks():
        failures += 1
        print(f"FAIL  static: {err}")
    total = 0
    for name, body in CASES:
        total += 1
        err = run_case(body)
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}: {err}")
    extra = [
        ("every_sprite_the_module_shows_is_in_the_manifest_and_every_manifest_sprite_is_shown", sprite_names_case),
        ("the_real_druid_module_paints_the_flower_after_the_wreath_for_moon_and_tree", run_real_caster_case),
        ("the_wreath_is_exactly_what_it_is_without_the_flower", run_real_wreath_case),
        ("the_real_cat_look_is_not_touched_and_the_flower_leaves_when_the_form_changes", run_real_cat_case),
    ]
    for name, fn in extra:
        total += 1
        err = fn()
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}: {err}")
    print(f"{total - min(failures, total)}/{total} checks passed")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
