#!/usr/bin/env python3
"""Runs the real TalentBackdrops.lua and its generated TalentBgArt.lua headless.

Checks:
  * the art: the committed sheets and TalentBgArt.lua are exactly what tools/assets/talentbg/bake.mjs writes now, every class
    has three scenes, and every sheet named by the manifest exists;
  * seating: one texture per tree panel, the player's class sheet in tree order, NEAREST, inset inside the plate, a whole
    number scale that covers the panel and a centred crop;
  * playback: the driver steps one cell per 1/FPS, wraps at FRAMES, allocates nothing per tick;
  * still stops the driver on the still frame, off clears the textures, reduced motion is still, the inspect view and a class
    with no sheets draw nothing.
"""

import shutil
import subprocess
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ADDON = ROOT / "forever-stuwave"
MODULE = (ADDON / "Modules/Skins/TalentBackdrops.lua").read_text(encoding="utf-8")
ARTLUA = (ADDON / "Modules/Skins/TalentBgArt.lua").read_text(encoding="utf-8")
MEDIA = ADDON / "Media/Textures"
BAKE = ROOT / "tools/assets/talentbg/bake.mjs"

failures = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  ({detail})"))
    if not ok:
        failures.append(name)


# ---- the art is current ----
node = shutil.which("node")
if node:
    r = subprocess.run([node, str(BAKE), "check"], capture_output=True, text=True, cwd=ROOT)
    check("sheets and manifest equal a fresh bake", r.returncode == 0, (r.stdout + r.stderr).strip()[-400:])
else:
    print("skip sheets and manifest equal a fresh bake (node not installed)")

MOCK = r"""
local Obj = {}
Obj.__index = function(t, k)
    local v = rawget(Obj, k)
    if v ~= nil then return v end
    if type(k) == "string" and k:match("^%u") then return function() end end
end
function New(kind, parent)
    return setmetatable({ kind = kind, shown = true, parent = parent, scripts = {} }, Obj)
end
function Obj:SetScript(n, fn) self.scripts[n] = fn end
function Obj:GetScript(n) return self.scripts[n] end
function Obj:SetTexture(p, h, v, filter) self.tex = p; self.filter = filter; self.texSets = (self.texSets or 0) + 1 end
function Obj:SetTexCoord(l, r, t, b)
    local tc = self.tc or {}
    tc[1], tc[2], tc[3], tc[4] = l, r, t, b
    self.tc = tc
    self.tcSets = (self.tcSets or 0) + 1
end
function Obj:Show() self.shown = true end
function Obj:Hide() self.shown = false end
function Obj:CreateTexture(name, layer, inh, sub) local t = New("Texture", self); t.layer = layer; t.sub = sub; return t end
function CreateFrame(kind, name, parent) return New("Frame", parent) end
function hooksecurefunc(t, k, fn)
    local orig = t[k]
    t[k] = function(...) local r = orig(...); fn(...); return r end
end
CLASS = "WARRIOR"
function UnitClass() return "Warrior", CLASS end
ForeverSTUwaveDB = {}
local store, defaults, watchers = {}, {}, {}
FS = {
    Config = {
        RegisterDefault = function(k, v) defaults[k] = v end,
        Get = function(k) if store[k] ~= nil then return store[k] end return defaults[k] end,
        OnChange = function(k, fn) watchers[k] = fn end,
    },
    ControlKit = {
        SizePx = function(f) if not f.pw then return nil end return f.pw, f.ph end,
        Place = function(o, ref, x, y, w, h) o.place = { ref, x, y, w, h } end,
        Snap = function(t) t.snapped = true end,
    },
    LogDegradeOnce = function(k, m) __logged = __logged or {}; __logged[k] = m; print(m) end,
}
function SetMode(v) store["talents.backdrop"] = v; watchers["talents.backdrop"]() end
TF = New("Frame")
COLS = {}
for i = 1, 3 do COLS[i] = { frame = New("Frame", TF) }; COLS[i].frame.pw, COLS[i].frame.ph = 470, 712 end
FS.TalentsSkin = { state = { tf = TF, cols = COLS } }
FS.TalentsSkin.Layout = function() end
"""

lua = LuaRuntime(unpack_returned_tuples=True)
lua.execute(MOCK)
lua.globals().ART_SRC = ARTLUA
lua.globals().MODULE_SRC = MODULE
lua.execute('assert(loadstring(ART_SRC, "@TalentBgArt.lua"))("forever-stuwave", FS)')
lua.execute('assert(loadstring(MODULE_SRC, "@TalentBackdrops.lua"))("forever-stuwave", FS)')
ev = lua.eval
ex = lua.execute
check("module exported", ev("FS.TalentBackdrops ~= nil"))

# ---- manifest shape ----
classes = ["WARRIOR", "PALADIN", "HUNTER", "ROGUE", "PRIEST", "SHAMAN", "MAGE", "WARLOCK", "DRUID"]
for cls in classes:
    names = [ev(f'FS.TalentBgArt.sheets.{cls} and FS.TalentBgArt.sheets.{cls}[{i}]') for i in (1, 2, 3)]
    check(f"{cls} has three sheets", all(isinstance(n, str) for n in names), names)
    for n in names:
        if isinstance(n, str):
            p = MEDIA / (n + ".tga")
            check(f"{n}.tga exists and is a 1024 x 1024 32 bit TGA", p.exists() and p.stat().st_size == 18 + 1024 * 1024 * 4)

# ---- seating ----
ex("FS.TalentsSkin.Layout()")
recs = "FS.TalentBackdrops.recs"
for i, spec in enumerate(["warrior_arms", "warrior_fury", "warrior_protection"], start=1):
    r = f"{recs}[{i}]"
    check(f"tree {i} shows {spec}", ev(f"{r}.tex.tex") == f"Interface\\AddOns\\forever-stuwave\\Media\\Textures\\talentbg_{spec}.tga", ev(f"{r}.tex.tex"))
    check(f"tree {i} NEAREST and snapped", ev(f"{r}.tex.filter") == "NEAREST" and ev(f"{r}.tex.snapped") is True)
    check(f"tree {i} between fill and ring", ev(f"{r}.tex.layer") == "BORDER" and ev(f"{r}.tex.sub") == -1)
    check(f"tree {i} inset 4 px", ev(f"{r}.tex.place[2]") == 4 and ev(f"{r}.tex.place[3]") == 4
          and ev(f"{r}.tex.place[4]") == 462 and ev(f"{r}.tex.place[5]") == 704)
# 462 x 704 inside: scale ceil(max(462/156, 704/236)) = ceil(2.98) = 3; 154 x 234.67 texels shown, centred
check("whole number scale 3", ev(f"{recs}[1].scale") == 3)
l, r_, t, b = (ev(f"{recs}[1].tex.tc[{k}]") for k in (1, 2, 3, 4))
check("frame 0 crop centred in cell 0", abs(l * 1024 - (1 + 1)) < 1e-6 and abs(r_ * 1024 - (1 + 1 + 154)) < 1e-6
      and abs(t * 1024 - (1 + (236 - 704 / 3) / 2)) < 1e-6 and abs(b * 1024 - (1 + (236 - 704 / 3) / 2 + 704 / 3)) < 1e-6,
      (l * 1024, r_ * 1024, t * 1024, b * 1024))
# The driver is local to the module; read it through the upvalue of M.Seat.
ex("""
function GetDriver()
    local i = 1
    while true do
        local name, val = debug.getupvalue(FS.TalentBackdrops.Seat, i)
        if not name then return nil end
        if name == "Driver" then
            local j = 1
            while true do
                local n2, v2 = debug.getupvalue(val, j)
                if not n2 then return nil end
                if n2 == "driver" then return v2 end
                j = j + 1
            end
        end
        i = i + 1
    end
end
D = GetDriver()
function U(rec) return math.floor(rec.tex.tc[1] * 1024 - 1 - 1 + 0.5) end
function Cell(rec)
    local u = rec.tex.tc[1] * 1024 - 2
    local v = rec.tex.tc[3] * 1024 - 1 - (236 - 704 / 3) / 2
    return math.floor(u / 158 + 0.5) + 6 * math.floor(v / 238 + 0.5)
end
""")
check("driver found with OnUpdate", ev("D ~= nil and D:GetScript('OnUpdate') ~= nil"))
ex("D:GetScript('OnUpdate')(D, 0.1)")
check("0.1 s is one cell later", ev("Cell(FS.TalentBackdrops.recs[1])") == 0, ev("Cell(FS.TalentBackdrops.recs[1])"))
ex("D:GetScript('OnUpdate')(D, 0.03)")
check("0.13 s total steps to cell 1", ev("Cell(FS.TalentBackdrops.recs[1])") == 1, ev("Cell(FS.TalentBackdrops.recs[1])"))
check("all three trees step together", ev("Cell(FS.TalentBackdrops.recs[2]) == 1 and Cell(FS.TalentBackdrops.recs[3]) == 1"))
ex("for i = 1, 23 do D:GetScript('OnUpdate')(D, 0.125) end")
check("24 cells later wraps to cell 0", ev("Cell(FS.TalentBackdrops.recs[1])") == 0, ev("Cell(FS.TalentBackdrops.recs[1])"))
ex("D:GetScript('OnUpdate')(D, 0.125 * 7)")
check("a long frame skips cells", ev("Cell(FS.TalentBackdrops.recs[1])") == 7, ev("Cell(FS.TalentBackdrops.recs[1])"))
check("cell 7 is column 1 row 1", abs(ev("FS.TalentBackdrops.recs[1].tex.tc[1]") * 1024 - (158 + 2)) < 1e-6)

alloc = ev("""(function()
    local f = D:GetScript('OnUpdate')
    for i = 1, 200 do f(D, 0.016) end
    collectgarbage('collect'); collectgarbage('stop')
    local before = collectgarbage('count')
    for i = 1, 5000 do f(D, 0.016) end
    local after = collectgarbage('count')
    collectgarbage('restart')
    return (after - before) * 1024
end)()""")
check("no allocation per tick", alloc < 4096, f"{alloc} bytes over 5000 ticks")

# ---- still / off / reduced motion ----
ex("SetMode('still')")
check("still stops the driver", ev("D:GetScript('OnUpdate') == nil"))
check("still shows frame 0", ev("Cell(FS.TalentBackdrops.recs[1])") == 0 and ev("FS.TalentBackdrops.recs[1].tex.shown") is True)
ex("SetMode('off')")
check("off clears and hides", ev("FS.TalentBackdrops.recs[1].tex.tex == nil and not FS.TalentBackdrops.recs[1].tex.shown"))
check("off stops the driver", ev("D:GetScript('OnUpdate') == nil"))
ex("SetMode('animated')")
check("animated again sets the sheet and runs", ev("FS.TalentBackdrops.recs[1].tex.tex ~= nil and D:GetScript('OnUpdate') ~= nil"))
ex("ForeverSTUwaveDB.reducedMotion = true; FS.TalentsSkin.Layout()")
check("reduced motion is still", ev("D:GetScript('OnUpdate') == nil and FS.TalentBackdrops.recs[1].tex.shown"))
ex("ForeverSTUwaveDB.reducedMotion = nil; FS.TalentsSkin.Layout()")

sets = ev("FS.TalentBackdrops.recs[1].tex.texSets")
ex("FS.TalentsSkin.Layout(); FS.TalentsSkin.Layout()")
check("a relayout does not set the texture again", ev("FS.TalentBackdrops.recs[1].tex.texSets") == sets)

# ---- resize ----
ex("for i = 1, 3 do COLS[i].frame.pw, COLS[i].frame.ph = 640, 980 end; FS.TalentsSkin.Layout()")
check("a bigger panel scales up to cover", ev("FS.TalentBackdrops.recs[1].scale") == 5, ev("FS.TalentBackdrops.recs[1].scale"))
ex("for i = 1, 3 do COLS[i].frame.pw, COLS[i].frame.ph = 200, 300 end; FS.TalentsSkin.Layout()")
check("a small panel stays at scale 2 or less", ev("FS.TalentBackdrops.recs[1].scale") <= 2)
ex("for i = 1, 3 do COLS[i].frame.pw, COLS[i].frame.ph = 470, 712 end; FS.TalentsSkin.Layout()")

# ---- inspect and unknown class ----
ex("TF.IsInspecting = function() return true end; FS.TalentsSkin.Layout()")
check("inspect view draws nothing", ev("not FS.TalentBackdrops.recs[1].tex.shown and D:GetScript('OnUpdate') == nil"))
ex("TF.IsInspecting = nil; CLASS = 'MONK'; FS.TalentsSkin.Layout()")
check("a class with no sheets draws nothing", ev("not FS.TalentBackdrops.recs[2].tex.shown"))
ex("CLASS = 'SHAMAN'; FS.TalentsSkin.Layout()")
check("class sheets follow the player", ev("FS.TalentBackdrops.recs[2].tex.tex") ==
      "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\talentbg_shaman_enhancement.tga", ev("FS.TalentBackdrops.recs[2].tex.tex"))
check("no degrade logged", ev("__logged == nil"))

print()
if failures:
    print(f"talentbg-harness: {len(failures)} FAILED")
    sys.exit(1)
print("talentbg-harness: all passed")
