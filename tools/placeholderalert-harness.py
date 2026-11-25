#!/usr/bin/env python3
"""Runs the real PlaceholderAlert.lua (with the generated art manifest) headless against a mock client.

The STAY RAD alert is a placeholder pop up in the Warrior Overpower alert's own 8 bit style (same frame, lettering, entrance, held
loop, amber, expiry exit and drain bar), with a neutral synthwave sun where the class emblem goes. It never shows in play, only as
the config window's sample for the Alert scale row on a class that has no pop up alert yet. These checks pin:

  * the preview loop (`FS.PlaceholderAlert.Preview`: Show, Hide, IsShown, Restyle): the baked entrance, the held loop while the drain
    bar empties over the whole 5 s window, amber for the last 1.5 s, the baked exit when it runs dry, a 0.6 s gap, again; out of
    combat only; it stops on hide and the moment a fight begins;
  * nothing exists until the first Show: no frame, no event, no OnUpdate; a missing art manifest shows nothing and raises nothing;
  * the seat is the Warrior alert's (`warriorpowerup`, placed with a parent so /fsedit and the hover outline never find it as a
    second piece), scaled about the middle of its canvas by the shared Alert scale (`Areas.AlertScale()`), re-seated by Restyle
    and by a layout rescale;
  * a tick allocates nothing, the texture stack keeps the baked back to front order, textures are filtered nearest;
  * REPLAY: every sampled frame of every sequence, played through the real module, composites to the same pixels as the baked
    display lists (the drain bar rows aside, which the module draws from the real remaining time);
  * the generator rewrites the committed texture and manifest byte for byte.

    python3 tools/placeholderalert-harness.py [--png debug/stayrad] [--gif debug/stayrad.gif]

`--png PREFIX` also writes PREFIX-compare.png: the Overpower alert's frames over STAY RAD's, the same instants (2 px per sprite px, over
the dark ground). `--gif PATH` writes the looping preview, Overpower beside STAY RAD, for a look. Exit 0 = every check passed.
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
CH = ROOT / "forever-stuwave/Modules/CombatHud"
ART = (CH / "PlaceholderAlertArt.lua").read_text(encoding="utf-8")
MODULE = (CH / "PlaceholderAlert.lua").read_text(encoding="utf-8")
TOC = (ROOT / "forever-stuwave/forever-stuwave.toc").read_text(encoding="utf-8")
MEDIA = ROOT / "forever-stuwave/Media/Textures"
BG = (10, 4, 22)
GW, GH, SPX = 150, 96, 2.5
SEQS = ("enter", "held", "amber", "exp")

MOCK = r"""
local Obj = {}
Obj.__index = function(t, k)
    local v = rawget(Obj, k)
    if v ~= nil then return v end
    if type(k) == "string" and k:match("^%u") then return function() end end
end
function New(kind) return setmetatable({ kind = kind, shown = true, level = 0 }, Obj) end
-- no table is made by any mock call (the allocation check counts what the module itself allocates)
function Obj:SetPoint(p, rel, rp, x, y) self.np = (self.np or 0) + 1; self.px, self.py, self.prel, self.has = x or 0, y or 0, rel, true end
function Obj:ClearAllPoints() self.has = false end
function Obj:SetAllPoints(rel) self.allpoints = rel end
function Obj:SetSize(w, h) self.w, self.h = w, h end
function Obj:Show() self.shown = true end
function Obj:Hide() self.shown = false end
function Obj:IsShown() return self.shown end
function Obj:SetFrameLevel(n) self.level = n end
function Obj:GetFrameLevel() return self.level end
function Obj:SetFrameStrata(s) self.strata = s end
function Obj:EnableMouse(b) self.mouse = b end
function Obj:SetScript(n, fn) self.scripts = self.scripts or {}; self.scripts[n] = fn end
function Obj:GetScript(n) return self.scripts and self.scripts[n] end
function Obj:RegisterEvent(e) self.events = self.events or {}; self.events[e] = true end
function Obj:UnregisterAllEvents() self.events = {} end
function Obj:SetTexture(p, ...) self.tex = p; self.filter = select(3, ...) end
function Obj:SetTexCoord(l, r, t, b) self.l, self.r, self.t, self.b = l, r, t, b end
function Obj:CreateTexture(name, layer, template, sub)
    local t = New("Texture"); t.layer, t.sub, t.parent = layer, sub or 0, self; t.shown = true
    __textures[#__textures + 1] = t
    return t
end
__textures, __frames = {}, {}
UIParent = New("Frame")
function CreateFrame(kind, name, parent)
    local f = New("Frame"); f.name = name; f.parent = parent
    __frames[#__frames + 1] = f
    if name then _G[name] = f end
    return f
end
__scale, __alert = 1, 1
__applied, __rescale = {}, {}
__logged = {}
FS = {
    LogDegradeOnce = function(k, m) __logged[k] = m end,
    Layout = {
        Scale = function() return __scale end,
        Apply = function(frame, id, parent) __applied[#__applied + 1] = { id = id, parent = parent, frame = frame }; frame.layoutId = id end,
        OnRescale = function(fn) __rescale[#__rescale + 1] = fn end,
    },
    GunsightAreas = { AlertScale = function() return __alert end },
}
function Load()
    assert(loadstring(ART_SRC, "@PlaceholderAlertArt.lua"))("forever-stuwave", FS)
    assert(loadstring(MODULE_SRC, "@PlaceholderAlert.lua"))("forever-stuwave", FS)
    PA, Art = FS.PlaceholderAlert, FS.PlaceholderAlertArt
    P = PA.Preview
end
Load()
function Driver() return P.Driver() end
function Driving() local d = Driver(); return d ~= nil and d.scripts ~= nil and d.scripts.OnUpdate ~= nil end
function Tick(dt) local d = Driver(); local fn = d and d.scripts and d.scripts.OnUpdate; if fn then fn(d, dt) end end
function TickFor(sec) local n = math.floor(sec * 30 + 0.5) for _ = 1, n do Tick(1 / 30) end end
function State() local s, i, p = PA._state(); return s, i, p end
function Root() return PA._root() end
function RootShown() local r = Root(); return r ~= nil and r.shown == true end
function VisibleCount() local n = 0 for _, t in ipairs(__textures) do if t.shown then n = n + 1 end end return n end
function Run(maxSec, pred) for _ = 1, math.floor(maxSec * 30) do Tick(1 / 30); if pred() then return true end end return false end
LAYER_IDX = { BACKGROUND = 1, BORDER = 2, ARTWORK = 3, OVERLAY = 4 }
-- the visible textures back to front, as flat rows: parent level, layer, sublevel, tc l r t b, size, position (UI units)
function Dump()
    local rows = {}
    for _, t in ipairs(__textures) do
        if t.shown and t.has and t.w then
            rows[#rows + 1] = { lvl = t.parent.level, layer = LAYER_IDX[t.layer], sub = t.sub, l = t.l, r = t.r, t = t.t, b = t.b,
                w = t.w, h = t.h, x = t.px, y = -t.py, tex = t.tex }
        end
    end
    table.sort(rows, function(a, b)
        if a.lvl ~= b.lvl then return a.lvl < b.lvl end
        if a.layer ~= b.layer then return a.layer < b.layer end
        return a.sub < b.sub
    end)
    return rows
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("nothing_exists_until_the_first_show", """
    assert(#__frames == 0 and #__textures == 0, "file scope makes no frame")
    assert(#__applied == 0 and #__rescale == 0, "and seats nothing")
    assert(P.IsShown() == false and P.Phase() == nil and Driver() == nil)
    assert(Root() == nil and not RootShown())
    P.Hide()                                   -- safe before anything was shown
    assert(#__frames == 0)
""")

case("the_preview_loops_enter_hold_amber_exit_gap_and_stops_on_hide", """
    assert(P.Show() == true, "the preview comes up")
    assert(P.IsShown() == true and RootShown())
    assert(P.Phase() == "enter", "it starts with the real enter animation")
    local d = Driver()
    assert(d and d.scripts.OnUpdate, "the loop has a driver")
    local seen, seqs = {}, {}
    local lastSeq, lastIdx = nil, 0
    local function step(sec)
        for _ = 1, math.floor(sec * 30 + 0.5) do
            d.scripts.OnUpdate(d, 1 / 30)
            if P.Phase() then seen[P.Phase()] = true end
            local s, i = State()
            if s then seqs[s] = true end
            -- the baked lists are not loops: a sequence never goes back to an earlier frame of itself
            if s and s == lastSeq then assert(i >= lastIdx, s .. " went back from frame " .. lastIdx .. " to " .. i) end
            lastSeq, lastIdx = s, i or 0
        end
    end
    step(4.8)
    assert(seen.enter and seen.hold and not seen.exit, "it holds for the real 5 s window before it exits")
    assert(seqs.enter and seqs.held and seqs.amber, "enter, then held, then amber")
    step(1.0)
    assert(seen.exit and seqs.exp, "the baked exit plays when the bar runs dry")
    step(1.2)
    assert(seen.gap, "then a gap")
    step(8)
    assert(P.Phase() ~= nil and P.IsShown(), "and it keeps repeating")
    P.Hide()
    assert(P.Phase() == nil and not d.scripts.OnUpdate, "the loop stops on hide")
    assert(P.IsShown() == false and not RootShown(), "and the alert is down")
    assert(VisibleCount() == 0, "no texture is left up")
""")

case("the_exit_is_followed_by_a_gap_of_six_tenths_of_a_second_and_then_the_entrance_again", """
    P.Show()
    assert(Run(8, function() return P.Phase() == "gap" end), "the exit ends in a gap")
    assert(not RootShown(), "nothing is up in the gap")
    local ticks = 0
    for _ = 1, 60 do
        Tick(1 / 30)
        if P.Phase() ~= "gap" then break end
        ticks = ticks + 1
    end
    assert(ticks >= 16 and ticks <= 20, "the gap was " .. ticks .. " ticks")
    assert(P.Phase() == "enter" and RootShown(), "and the entrance plays again")
    local s, i = State()
    assert(s == "enter" and i <= 2, tostring(s) .. tostring(i))
""")

case("the_last_one_and_a_half_seconds_play_amber", """
    P.Show()
    TickFor(3.2)
    assert(State() == "held", tostring(State()))
    TickFor(0.4)
    local s, i = State()
    assert(s == "amber" and i >= 1, tostring(s))
    TickFor(1.3)
    s = State()
    assert(s == "amber" or s == "exp", tostring(s))
""")

case("the_drain_bar_empties_over_the_whole_window", """
    P.Show()
    local fill = Art.SPELL.stayrad.fill
    local function width()
        for n = 1, 3 do
            local t = __textures[fill[n]]
            if not (t.shown and t.has) then return 0 end
        end
        return __textures[fill[2]].w / 2.5
    end
    TickFor(1.0)
    local w1 = width()
    TickFor(1.5)                                  -- 2.5 s of the 5 s window gone
    local w2 = width()
    local want = math.floor(((5 - 2.5) / 5) * 98 + 0.5)
    assert(math.abs(w2 - want) <= 2, w2 .. " vs " .. want)
    assert(w1 > w2 and w2 > 0, "it only shrinks")
    for n = 1, 3 do assert(math.abs(__textures[fill[n]].w - __textures[fill[1]].w) < 1e-6, "the three fill rows are one width") end
""")

case("show_twice_is_refused_and_hide_twice_is_safe", """
    assert(P.Show() == true)
    assert(P.Show() == false, "already up")
    assert(P.IsShown() == true)
    P.Hide(); P.Hide()
    assert(P.IsShown() == false and P.Phase() == nil)
    assert(P.Show() == true, "and it can come up again")
    assert(P.Phase() == "enter")
""")

case("it_never_starts_in_combat_and_a_fight_beginning_takes_it_down", """
    InCombatLockdown = function() return true end
    assert(P.Show() == false and P.Phase() == nil and not P.IsShown())
    assert(#__frames == 0, "a refused show builds nothing")
    InCombatLockdown = function() return false end
    assert(P.Show() == true)
    TickFor(0.5)
    assert(RootShown())
    InCombatLockdown = function() return true end
    TickFor(0.1)
    assert(P.IsShown() == false and P.Phase() == nil and not RootShown() and not Driving(), "the first tick of a fight ends it")
    InCombatLockdown = nil
""")

case("a_missing_art_manifest_shows_nothing_and_raises_nothing", """
    FS.PlaceholderAlertArt = nil
    PA = nil
    __textures, __frames = {}, {}
    assert(loadstring(MODULE_SRC, "@PlaceholderAlert.lua"))("forever-stuwave", FS)
    local P2 = FS.PlaceholderAlert.Preview
    assert(P2.Show() == false and P2.IsShown() == false)
    P2.Restyle(); P2.Hide()
    assert(#__textures == 0)
""")

case("the_frame_is_plain_seated_on_the_warrior_alert_seat_and_hidden_from_the_layout_editor", """
    P.Show()
    local r = Root()
    assert(r and r.name == "ForeverSTUwavePlaceholderAlert" and r.parent == UIParent)
    assert(r.strata == "MEDIUM" and r.mouse == false, "a plain frame that takes no mouse")
    assert(#__applied == 1, #__applied .. " seatings")
    local a = __applied[1]
    assert(a.id == "warriorpowerup" and a.frame == r, "the Warrior alert's seat")
    assert(a.parent == UIParent, "placed with a parent, so the layout editor and the hover outline never list it as a piece")
    assert(#__rescale == 1, "one rescale callback")
    P.Hide(); P.Show(); P.Hide(); P.Show()
    assert(#__applied == 1 and #__rescale == 1, "built once, seated once, however often it is shown")
""")

case("a_layout_rescale_seats_the_textures_again", """
    P.Show()
    TickFor(1.5)
    local n = VisibleCount()
    local before = Dump()[1].w
    __scale = 0.5
    for _, fn in ipairs(__rescale) do fn() end
    assert(VisibleCount() == n, "nothing drops out")
    local after = Dump()[1].w
    assert(math.abs(after - before / 2) < 1e-6, after .. " vs " .. before)
""")

case("the_alert_scale_grows_the_art_about_the_middle_of_its_canvas_and_restyle_follows_it", """
    P.Show()
    TickFor(1.5)
    local function box()
        local x0, y0, x1, y1 = 1e9, 1e9, -1e9, -1e9
        for _, row in ipairs(Dump()) do
            x0, y0 = math.min(x0, row.x), math.min(y0, row.y)
            x1, y1 = math.max(x1, row.x + row.w), math.max(y1, row.y + row.h)
        end
        return x0, y0, x1, y1
    end
    local ax0, ay0, ax1, ay1 = box()
    __alert = 2
    P.Restyle()
    local bx0, by0, bx1, by1 = box()
    local cw, ch = Art.GW * 2.5, Art.GH * 2.5
    assert(math.abs((bx1 - bx0) - 2 * (ax1 - ax0)) < 1e-6, "twice as wide")
    assert(math.abs((by1 - by0) - 2 * (ay1 - ay0)) < 1e-6, "twice as tall")
    assert(math.abs(((bx0 + bx1) / 2 - cw / 2) - 2 * ((ax0 + ax1) / 2 - cw / 2)) < 1e-6, "grown about the canvas middle, not its corner")
    __alert = 0.5
    P.Restyle()
    local cx0, _, cx1 = box()
    assert(math.abs((cx1 - cx0) - 0.5 * (ax1 - ax0)) < 1e-6, "and half")
    for _, junk in ipairs({ 0, -1, "big", 1 / 0, 0 / 0 }) do
        __alert = junk
        P.Restyle()
        local jx0, _, jx1 = box()
        assert(math.abs((jx1 - jx0) - (ax1 - ax0)) < 1e-6, "a junk scale reads as 1: " .. tostring(junk))
    end
    __alert = 1
""")

case("restyle_does_nothing_unless_the_preview_is_up", """
    P.Restyle()
    assert(#__textures == 0)
    P.Show(); P.Hide()
    __alert = 2
    P.Restyle()
    assert(VisibleCount() == 0 and not RootShown())
""")

case("the_onupdate_is_set_only_while_the_preview_plays", """
    assert(not Driving())
    P.Show()
    assert(Driving())
    TickFor(12)
    assert(Driving(), "it keeps looping")
    P.Hide()
    assert(not Driving())
""")

case("a_tick_allocates_nothing", """
    if jit then jit.off() end                 -- trace compiling allocates, and it is not the module
    P.Show()
    TickFor(8)                                 -- a whole window and the exit warm every slot (the mock grows a field on a first seat)
    collectgarbage("collect"); collectgarbage("stop")
    local a = collectgarbage("count")
    for _ = 1, 150 do Tick(1 / 30) end        -- five more seconds: the loop restarts and plays its entrance again
    local b = collectgarbage("count")
    collectgarbage("restart")
    assert(P.IsShown() and P.Phase() ~= nil)
    assert(b - a < 1, "a tick allocated " .. (b - a) .. " KB over 150 ticks")
""")

case("the_texture_stack_keeps_the_baked_order", """
    P.Show()
    local lastKey = -1
    for i, t in ipairs(__textures) do
        local key = t.parent.level * 1000 + LAYER_IDX[t.layer] * 20 + (t.sub + 8)
        assert(key > lastKey, "slot " .. i .. " is not above slot " .. (i - 1))
        assert(t.sub >= -8 and t.sub <= 7)
        lastKey = key
    end
    assert(#__textures == Art.SPELL.stayrad.slots, #__textures .. " textures for " .. Art.SPELL.stayrad.slots .. " slots")
    local idle = 0
    for _, t in ipairs(__textures) do
        if t.tex == nil then
            assert(t.shown == false, "a texture with no file is hidden")
            idle = idle + 1
        end
    end
    assert(idle > 0, "no texture is given a file before it shows")
""")

case("textures_are_filtered_nearest_and_sized_in_ui_units", """
    P.Show()
    TickFor(1.0)
    local n = 0
    for _, row in ipairs(Dump()) do
        assert(row.tex:find("placeholder_alert_%d+%.tga$"), row.tex)
        assert(row.w > 0 and row.h > 0 and row.l < row.r and row.t < row.b)
        assert(math.abs(row.w / 2.5 - math.floor(row.w / 2.5 + 0.5)) < 1e-6 or row.h == 2.5)
        n = n + 1
    end
    assert(n > 10)
    local filtered = 0
    for _, t in ipairs(__textures) do if t.tex and t.filter == "NEAREST" then filtered = filtered + 1 end end
    assert(filtered > 10, "SetTexture asked for NEAREST")
""")


def static_checks() -> list[str]:
    errs: list[str] = []
    toc = [line.strip() for line in TOC.splitlines()]
    needed = ["Core/Layout.lua", "Modules/CombatHud/GunsightAreas.lua",
              "Modules/CombatHud/PlaceholderAlertArt.lua", "Modules/CombatHud/PlaceholderAlert.lua"]
    try:
        order = [toc.index(n) for n in needed]
        if order != sorted(order):
            errs.append("the toc must load Layout, GunsightAreas, PlaceholderAlertArt, PlaceholderAlert in that order")
    except ValueError:
        errs.append("the toc does not list PlaceholderAlertArt.lua and PlaceholderAlert.lua after GunsightAreas.lua")
    for needle in ("COMBAT_LOG_EVENT_UNFILTERED", "RegisterEvent", 'CreateFrame("Button"', "SecureActionButton", "SecureHandler",
                   "hooksecurefunc", "FS.Config"):
        for line in MODULE.splitlines():
            if needle in line and not line.lstrip().startswith("--"):
                errs.append(f"PlaceholderAlert.lua must not use {needle}: it shows only as a config preview")
    for word in ("bot", "automation", "macro"):
        if re.search(rf"\b{word}\b", MODULE.lower()) or re.search(rf"\b{word}\b", ART.lower()):
            errs.append(f"client visible text mentions '{word}'")
    if chr(0x2014) in MODULE or chr(0x2014) in ART:
        errs.append("an em dash in the module or the manifest")
    atlas = re.findall(r'\{ file = "(\w+)", w = (\d+), h = (\d+) \}', ART)
    if not atlas:
        errs.append("the manifest lists no atlas")
    for name, w, h in atlas:
        path = MEDIA / f"{name}.tga"
        if not path.exists():
            errs.append(f"missing texture {name}.tga (run tools/assets/generate_placeholder_alert.py)")
        elif path.stat().st_size != 18 + int(w) * int(h) * 4:
            errs.append(f"{name}.tga is {path.stat().st_size} bytes, the manifest says {w} x {h}")
        if not (int(w) & (int(w) - 1) == 0 and int(h) & (int(h) - 1) == 0):
            errs.append(f"{name}.tga is {w} x {h}: the client draws no texture whose sides are not powers of two")
    return errs


def generator_is_deterministic() -> list[str]:
    errs: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, FS_ASSET_OUTPUT_DIR=tmp, FS_ART_LUA_OUTPUT=str(Path(tmp) / "PlaceholderAlertArt.lua"))
        run = subprocess.run([sys.executable, str(ROOT / "tools/assets/generate_placeholder_alert.py")], env=env, capture_output=True, text=True)
        if run.returncode != 0:
            return [f"the generator failed: {run.stderr.strip().splitlines()[-1:]}"]
        if (Path(tmp) / "PlaceholderAlertArt.lua").read_bytes() != (CH / "PlaceholderAlertArt.lua").read_bytes():
            errs.append("PlaceholderAlertArt.lua is not what the generator writes (regenerate it)")
        tgas = sorted(Path(tmp).glob("placeholder_alert_*.tga"))
        if not tgas:
            errs.append("the generator wrote no texture")
        for tga in tgas:
            committed = MEDIA / tga.name
            if not committed.exists() or committed.read_bytes() != tga.read_bytes():
                errs.append(f"{tga.name} is not what the generator writes (regenerate it)")
    return errs


def generator_leaves_the_warrior_art_alone() -> list[str]:
    """The font gained a D for this alert; the Warrior bake must not move (its own harness holds the full byte check)."""
    errs: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, FS_ASSET_OUTPUT_DIR=tmp, FS_ART_LUA_OUTPUT=str(Path(tmp) / "WarriorPowerUpArt.lua"))
        run = subprocess.run([sys.executable, str(ROOT / "tools/assets/generate_warrior_powerups.py")], env=env, capture_output=True, text=True)
        if run.returncode != 0:
            return [f"the Warrior generator failed: {run.stderr.strip().splitlines()[-1:]}"]
        if (Path(tmp) / "WarriorPowerUpArt.lua").read_bytes() != (CH / "WarriorPowerUpArt.lua").read_bytes():
            errs.append("the Warrior manifest changed")
        if (Path(tmp) / "warrior_powerups_1.tga").read_bytes() != (MEDIA / "warrior_powerups_1.tga").read_bytes():
            errs.append("the Warrior atlas changed")
    return errs


def new_runtime() -> LuaRuntime:
    rt = LuaRuntime(unpack_returned_tuples=False)
    g = rt.globals()
    g.ART_SRC, g.MODULE_SRC = ART, MODULE
    rt.execute(MOCK)
    return rt


def run_case(body: str) -> str | None:
    try:
        rt = new_runtime()
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


# ----------------------------------------------------------------------------------------------------------------------
# Replay: the real module against the baked lists
# ----------------------------------------------------------------------------------------------------------------------
def _warrior_harness():
    spec = importlib.util.spec_from_file_location("warriorpowerups_harness", HERE / "warriorpowerups-harness.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_manifest(art_src: str, global_name: str, names: tuple[str, ...], seqs: tuple[str, ...], media: Path):
    """(sprites, spells, atlases) of a generated art manifest, read through a Lua runtime."""
    import numpy as np
    from PIL import Image
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.execute("function load(src, name) local FS = {}; assert(loadstring(src, '@art'))('x', FS); return FS[name] end")
    art = rt.eval("load")(art_src, global_name)
    sprites = [tuple(int(art.SPRITE[i][k]) for k in range(1, 6)) for i in range(1, len(art.SPRITE) + 1)]
    spells = {}
    for name in names:
        sp = art.SPELL[name]
        spells[name] = dict(slots=int(sp.slots), fill=[int(v) for v in sp.fill.values()], win=int(sp.win),
                            seqs={seq: [[int(v) for v in sp.seqs[seq][i].values()] for i in range(1, len(sp.seqs[seq]) + 1)] for seq in seqs})
    atlases = [np.asarray(Image.open(media / f"{str(art.ATLAS[i].file)}.tga").convert("RGBA")) for i in range(1, len(art.ATLAS) + 1)]
    return sprites, spells, atlases


SAMPLE_HELD = 3


def sampled(seq: str, idx: int, total: int) -> bool:
    if seq in ("held", "amber"):
        return idx <= 3 or idx == total or idx % SAMPLE_HELD == 0
    return True


def replay_checks(keep: dict | None = None) -> list[str]:
    """Plays the preview for two whole loops and compares sampled frames of the real module with the baked lists."""
    import numpy as np
    wp = _warrior_harness()
    sprites, spells, atlases = load_manifest(ART, "PlaceholderAlertArt", ("stayrad",), SEQS, MEDIA)
    spell = spells["stayrad"]
    errs: list[str] = []
    compared = 0
    rt = new_runtime()
    rt.execute("P.Show()")
    state, tick, dump = rt.eval("State"), rt.eval("Tick"), rt.eval("Dump")
    seen: set = set()
    for _ in range(14 * 30):
        seq, idx, _p = state()
        if seq is not None and (str(seq), int(idx)) not in seen:
            seen.add((str(seq), int(idx)))
            if sampled(str(seq), int(idx), len(spell["seqs"][str(seq)])):
                rows = dump()
                rows = [{key: rows[i][key] for key in ("l", "r", "t", "b", "w", "h", "x", "y", "tex")} for i in range(1, len(rows) + 1)]
                want = wp.expected_image(sprites, spell, atlases, str(seq), int(idx), 98)
                got = actual_image(rows, atlases)
                d = np.abs(want - got).max(axis=2)
                d[82:92, :] = 0                      # the drain bar: its fill is drawn from the real remaining time
                compared += 1
                if int((d > 1).sum()) > 0:
                    errs.append(f"{seq} frame {idx}: {int((d > 1).sum())} px differ")
                if keep is not None:
                    keep[(str(seq), int(idx))] = got
        tick(1 / 30)
    for seq in SEQS:
        if not any(s == seq for s, _ in seen):
            errs.append(f"the loop never played {seq}")
    if compared < 80:
        errs.append(f"only {compared} frames were compared")
    print(f"      replay compared {compared} frames")
    return errs


def actual_image(rows, atlases):
    import numpy as np
    wp = _warrior_harness()
    canvas = np.zeros((GH, GW, 3)) + BG
    for row in rows:
        n = int(re.search(r"placeholder_alert_(\d+)\.tga$", row["tex"]).group(1))
        atlas = atlases[n - 1]
        aw, ah = atlas.shape[1], atlas.shape[0]
        tx, ty = round(row["l"] * aw), round(row["t"] * ah)
        w, h = round((row["r"] - row["l"]) * aw), round((row["b"] - row["t"]) * ah)
        x, y = round(row["x"] / SPX), round(row["y"] / SPX)
        wp.blit(canvas, atlas, (n, tx, ty, w, h), x, y, round(row["w"] / SPX) if w == 1 else None)
    return canvas


# ----------------------------------------------------------------------------------------------------------------------
# A look: Overpower over STAY RAD, and the looping preview side by side
# ----------------------------------------------------------------------------------------------------------------------
SHEET = [("enter", 3, "entrance 0.08 s"), ("enter", 7, "impact 0.20 s"), ("enter", 13, "entrance 0.40 s"), ("held", 34, "held 1.6 s"),
         ("held", 76, "held 3.0 s"), ("amber", 19, "amber 4.1 s"), ("exp", 10, "expiry exit 0.30 s"), ("exp", 19, "expiry exit 0.60 s")]
TILE_W, TILE_H = 2 * GW, 2 * GH


def _tile(img, scale=2):
    from PIL import Image
    return Image.fromarray(img.round().clip(0, 255).astype("uint8")).resize((GW * scale, GH * scale), Image.NEAREST)


def png(prefix: str) -> None:
    """Two rows of frame pairs: the Overpower alert on top, STAY RAD under it, the same instant in each column."""
    from PIL import Image, ImageDraw
    wp = _warrior_harness()
    w_sprites, w_spells, w_atlases = wp.load_manifest()
    sprites, spells, atlases = load_manifest(ART, "PlaceholderAlertArt", ("stayrad",), SEQS, MEDIA)
    cols = 4
    groups = [SHEET[:4], SHEET[4:]]
    sheet = Image.new("RGB", (cols * TILE_W, len(groups) * 2 * (TILE_H + 18)), (30, 20, 50))
    draw = ImageDraw.Draw(sheet)
    for g, frames in enumerate(groups):
        for n, (seq, idx, cap) in enumerate(frames):
            for row, (name, sp, spr, atl) in enumerate((("Overpower", w_spells["overpower"], w_sprites, w_atlases),
                                                        ("STAY RAD", spells["stayrad"], sprites, atlases))):
                img = wp.expected_image(spr, sp, atl, seq, idx, 98)
                x, y = n * TILE_W, (g * 2 + row) * (TILE_H + 18)
                sheet.paste(_tile(img), (x, y + 16))
                draw.text((x + 4, y + 2), f"{name}: {cap}", fill=(200, 190, 230))
    out = f"{prefix}-compare.png"
    sheet.save(out)
    print("wrote", out)


def gif(path: str) -> None:
    """The looping preview of both alerts side by side: enter, held and amber over the 5 s window, the exit, a 0.6 s gap."""
    from PIL import Image
    wp = _warrior_harness()
    w_sprites, w_spells, w_atlases = wp.load_manifest()
    sprites, spells, atlases = load_manifest(ART, "PlaceholderAlertArt", ("stayrad",), SEQS, MEDIA)
    plan = [("enter", i) for i in range(1, len(spells["stayrad"]["seqs"]["enter"]) + 1)]
    plan += [("held", i) for i in range(1, len(spells["stayrad"]["seqs"]["held"]) + 1)]
    plan += [("amber", i) for i in range(1, len(spells["stayrad"]["seqs"]["amber"]) + 1)]
    plan += [("exp", i) for i in range(1, len(spells["stayrad"]["seqs"]["exp"]) + 1)]
    plan += [("gap", 0)] * 18
    scale, gap = 3, 12
    frames = []
    for n, (seq, idx) in enumerate(plan):
        rem = max(0.0, 5.0 - n / 30)
        fill = round(min(1.0, rem / 5.0) * 98)
        pair = []
        for sp, spr, atl, key in ((w_spells["overpower"], w_sprites, w_atlases, "ov"), (spells["stayrad"], sprites, atlases, "sr")):
            if seq == "gap":
                import numpy as np
                img = np.zeros((GH, GW, 3)) + BG
            else:
                img = wp.expected_image(spr, sp, atl, seq, idx, fill)
            pair.append(_tile(img, scale))
        frame = Image.new("RGB", (GW * scale * 2 + gap, GH * scale), (30, 20, 50))
        frame.paste(pair[0], (0, 0))
        frame.paste(pair[1], (GW * scale + gap, 0))
        frames.append(frame)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=33, loop=0, optimize=False)
    print("wrote", path, f"({len(frames)} frames)")


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
    total = len(CASES)
    errs = replay_checks()
    for e in errs:
        failures += 1
        print(f"FAIL  replay: {e}")
    if not errs:
        print("ok    replay_matches_the_baked_lists")
    total += 1
    for label, check in (("generator_is_deterministic", generator_is_deterministic),
                         ("generator_leaves_the_warrior_art_alone", generator_leaves_the_warrior_art_alone)):
        errs = check()
        for e in errs:
            failures += 1
            print(f"FAIL  {label}: {e}")
        if not errs:
            print(f"ok    {label}")
        total += 1
    print(f"{total - min(failures, total)}/{total} checks passed")
    if "--png" in sys.argv:
        prefix = sys.argv[sys.argv.index("--png") + 1]
        Path(prefix).parent.mkdir(parents=True, exist_ok=True)
        png(prefix)
    if "--gif" in sys.argv:
        path = sys.argv[sys.argv.index("--gif") + 1]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        gif(path)
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
