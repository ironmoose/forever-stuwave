#!/usr/bin/env python3
"""Runs the real CharBackdrop.lua and its generated CharBgArt.lua headless.

Checks:
  * the art: the committed sheet and CharBgArt.lua are exactly what tools/assets/charbg/bake.mjs writes now, and the sheet
    the manifest names exists;
  * seating: one texture in the model well, NEAREST, between the fill and the ring, inset inside the plate, a whole number
    scale that covers the well, centred across and cropped from the top so the ground stays;
  * playback: the driver steps one cell per 1/FPS, wraps at FRAMES, allocates nothing per tick;
  * still stops the driver on the still frame, off clears the texture, reduced motion is still, a relayout and a resize.
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
MODULE = (ADDON / "Modules/Skins/CharBackdrop.lua").read_text(encoding="utf-8")
ARTLUA = (ADDON / "Modules/Skins/CharBgArt.lua").read_text(encoding="utf-8")
MEDIA = ADDON / "Media/Textures"
BAKE = ROOT / "tools/assets/charbg/bake.mjs"

failures = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  ({detail})"))
    if not ok:
        failures.append(name)


node = shutil.which("node")
if node:
    r = subprocess.run([node, str(BAKE), "check"], capture_output=True, text=True, cwd=ROOT)
    check("sheet and manifest equal a fresh bake", r.returncode == 0, (r.stdout + r.stderr).strip()[-400:])
else:
    print("skip sheet and manifest equal a fresh bake (node not installed)")

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
end
function Obj:Show() self.shown = true end
function Obj:Hide() self.shown = false end
function Obj:CreateTexture(name, layer, inh, sub) local t = New("Texture", self); t.layer = layer; t.sub = sub; return t end
function CreateFrame(kind, name, parent) local f = New("Frame", parent); LAST_FRAME = f; return f end
ForeverSTUwaveDB = {}
local store, defaults, watchers = {}, {}, {}
FS = {
    Config = {
        RegisterDefault = function(k, v) defaults[k] = v end,
        Get = function(k) if store[k] ~= nil then return store[k] end return defaults[k] end,
        OnChange = function(k, fn) watchers[k] = fn end,
    },
    ControlKit = {
        Place = function(o, ref, x, y, w, h) o.place = { ref, x, y, w, h } end,
        Snap = function(t) t.snapped = true end,
    },
    LogDegradeOnce = function(k, m) __logged = __logged or {}; __logged[k] = m; print(m) end,
}
function SetMode(v) store["character.backdrop"] = v; watchers["character.backdrop"]() end
WELL = { frame = New("Frame"), wpx = 330, hpx = 490 }
PRIOR_CALLS = 0
FS.CharacterSkin = { state = {}, OnWellLayout = function() PRIOR_CALLS = PRIOR_CALLS + 1 end }
function Layout() FS.CharacterSkin.state.well = WELL; FS.CharacterSkin.OnWellLayout(WELL) end
"""

lua = LuaRuntime(unpack_returned_tuples=True)
lua.execute(MOCK)
lua.globals().ART_SRC = ARTLUA
lua.globals().MODULE_SRC = MODULE
lua.execute('assert(loadstring(ART_SRC, "@CharBgArt.lua"))("forever-stuwave", FS)')
lua.execute('assert(loadstring(MODULE_SRC, "@CharBackdrop.lua"))("forever-stuwave", FS)')
ev = lua.eval
ex = lua.execute
check("module exported", ev("FS.CharBackdrop ~= nil"))
check("no well yet draws nothing", ev("FS.CharBackdrop.rec.tex == nil"))

name = ev("FS.CharBgArt.sheet")
p = MEDIA / (str(name) + ".tga")
check("manifest sheet exists as a 1024 x 1024 32 bit TGA", p.exists() and p.stat().st_size == 18 + 1024 * 1024 * 4, name)

ex("Layout()")
check("an earlier well hook still runs", ev("PRIOR_CALLS") == 1)
r = "FS.CharBackdrop.rec"
check("texture is the aurora sheet", ev(f"{r}.tex.tex") == "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\charbg_aurora.tga", ev(f"{r}.tex.tex"))
check("NEAREST and snapped", ev(f"{r}.tex.filter") == "NEAREST" and ev(f"{r}.tex.snapped") is True)
check("on the well, between fill and ring", ev(f"{r}.tex.parent == WELL.frame and {r}.tex.layer == 'BORDER' and {r}.tex.sub == -1"))
check("inset 5 px", ev(f"{r}.tex.place[2]") == 5 and ev(f"{r}.tex.place[3]") == 5
      and ev(f"{r}.tex.place[4]") == 320 and ev(f"{r}.tex.place[5]") == 480)
# 320 x 480 inside: scale ceil(max(320/160, 480/192)) = ceil(2.5) = 3; 106.67 x 160 texels, centred across, bottom kept
check("whole number scale 3", ev(f"{r}.scale") == 3)
l, rr, t, b = (ev(f"{r}.tex.tc[{k}]") for k in (1, 2, 3, 4))
x0, vw, vh = (160 - 320 / 3) / 2, 320 / 3, 160
check("frame 0 crop centred across, bottom kept", abs(l * 1024 - (1 + x0)) < 1e-6 and abs(rr * 1024 - (1 + x0 + vw)) < 1e-6
      and abs(t * 1024 - (1 + 192 - vh)) < 1e-6 and abs(b * 1024 - (1 + 192)) < 1e-6, (l * 1024, rr * 1024, t * 1024, b * 1024))

ex("""
D = FS.CharBackdrop.rec.tex.parent and nil
for _, f in ipairs({ LAST_FRAME }) do D = f end
function Cell()
    local rec = FS.CharBackdrop.rec
    local u = rec.tex.tc[1] * 1024 - 1 - rec.u0 * 1024
    local v = rec.tex.tc[3] * 1024 - 1 - rec.v0 * 1024
    return math.floor(u / 162 + 0.5) + 6 * math.floor(v / 194 + 0.5)
end
""")
check("driver is a child of the well with OnUpdate", ev("D.parent == WELL.frame and D:GetScript('OnUpdate') ~= nil"))
ex("D:GetScript('OnUpdate')(D, 0.1)")
check("0.1 s is still cell 0", ev("Cell()") == 0, ev("Cell()"))
ex("D:GetScript('OnUpdate')(D, 0.03)")
check("0.13 s steps to cell 1", ev("Cell()") == 1, ev("Cell()"))
ex("for i = 1, 23 do D:GetScript('OnUpdate')(D, 0.125) end")
check("24 cells later wraps to cell 0", ev("Cell()") == 0, ev("Cell()"))
ex("D:GetScript('OnUpdate')(D, 0.125 * 7)")
check("a long frame skips cells", ev("Cell()") == 7, ev("Cell()"))

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

ex("SetMode('still')")
check("still stops the driver on frame 0", ev("D:GetScript('OnUpdate') == nil") and ev("Cell()") == 0 and ev(f"{r}.tex.shown") is True)
ex("SetMode('off')")
check("off clears, hides and stops", ev(f"{r}.tex.tex == nil and not {r}.tex.shown and D:GetScript('OnUpdate') == nil"))
ex("SetMode('animated')")
check("animated again sets the sheet and runs", ev(f"{r}.tex.tex ~= nil and D:GetScript('OnUpdate') ~= nil"))
ex("ForeverSTUwaveDB.reducedMotion = true; Layout()")
check("reduced motion is still", ev(f"D:GetScript('OnUpdate') == nil and {r}.tex.shown"))
ex("ForeverSTUwaveDB.reducedMotion = nil; Layout()")

sets = ev(f"{r}.tex.texSets")
ex("Layout(); Layout()")
check("a relayout does not set the texture again", ev(f"{r}.tex.texSets") == sets)
check("one driver only", ev("LAST_FRAME == D"))
ex("WELL.wpx, WELL.hpx = 500, 700; Layout()")
check("a bigger well scales up to cover", ev(f"{r}.scale") == 4, ev(f"{r}.scale"))
ex("WELL.wpx, WELL.hpx = nil, nil; Layout()")
check("a well with no size draws nothing", ev(f"not {r}.tex.shown and D:GetScript('OnUpdate') == nil"))
check("no degrade logged", ev("__logged == nil"))

print()
if failures:
    print(f"charbg-harness: {len(failures)} FAILED")
    sys.exit(1)
print("charbg-harness: all passed")
