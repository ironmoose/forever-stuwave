#!/usr/bin/env python3
"""Headless check of DataBar.lua's DEBUG segment (the ForeverDebugBridge lattice drawn inside the bar).

Runs the real addons/forever-stuwave/DataBar.lua under lupa against a small mock WoW API (a
layout harness: widgets record size, anchors, shown state and HookScript lists; every other
widget method is a no-op). It pins the behaviour the bar promises:

  * no ForeverDebugBridgeFrame, or one that is hidden: the segments share the full width equally,
    no gap, DEBUG hidden (the bar lays out exactly as it did before DEBUG existed);
  * bridge shown: DEBUG sits between BAGS and TIME, takes the label + the bridge's PHYSICAL
    footprint converted to bar units at the bar's effective scale, and the other segments share
    the remainder equally; /fdebug hide|show (the bridge's OnHide/OnShow) flips it live;
  * the width follows a UI scale change, and a bar too short for the lattice logs once;
  * COMBAT: the bar is restricted (the XP bar is anchored to it, the control deck chassis to the XP bar, and the deck
    hosts secure buttons), so a rescale or a /fdebug show|hide in combat resizes, re-anchors, shows and hides nothing,
    and PLAYER_REGEN_ENABLED replays it from the state current then.

    python3 tools/databar-harness.py

Exit 0 = every check passed; otherwise the number of failures.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ADDON = Path(__file__).resolve().parent.parent / "forever-stuwave"
DATABAR = Path(os.environ.get("DATABAR_LUA", ADDON / "Modules/DataBars/DataBar.lua"))   # DATABAR_LUA: a mutated scratch copy
SCREEN_W, PHYS_H = 2560, 1440
LABEL_W = 32.5          # the mock's GetStringWidth for "DEBUG"
PAD_X, LABEL_GAP, LINK_END_PAD_PX, RECESS_PAD_PX = 8, 6, 4, 4

MOCK = r"""
local W, H = ...
__frames, __logs, __rescale, __themeCalls = {}, {}, {}, {}
__combat, __blocked = false, {}
-- A frame flagged `restricted` refuses size, anchor and show/hide in combat, logged in __blocked (ADDON_ACTION_BLOCKED).
local function refused(self, what)
    if __combat and self.restricted then
        __blocked[#__blocked + 1] = tostring(self.name) .. ":" .. what
        return true
    end
    return false
end
local Region = {}
-- Unlisted widget METHODS (capitalised) are no-ops; plain fields read as nil.
Region.__index = function(t, k)
    if Region[k] then return Region[k] end
    if type(k) == "string" and k:match("^%u") then return function() end end
end
local function new(kind, parent, name)
    local r = setmetatable({ kind = kind, parent = parent, name = name, shown = true, w = 0, h = 0, scale = 1, hooks = {} }, Region)
    __frames[#__frames + 1] = r
    return r
end
local function runHooks(self, which) for _, fn in ipairs(self.hooks[which] or {}) do fn(self) end end
function Region:SetSize(w, h) if refused(self, "SetSize") then return end self.w, self.h = w, h end
function Region:SetWidth(w) if refused(self, "SetWidth") then return end self.w = w end
function Region:SetHeight(h) self.h = h end
function Region:GetWidth() return self.w end
function Region:SetPoint(point, rel, relPoint, x, y)
    if refused(self, "SetPoint") then return end
    self.pt = { point = point, rel = rel, relPoint = relPoint or point, x = x or 0, y = y or 0 }
    self.pts = self.pts or {}; self.pts[point] = { x = x or 0, y = y or 0 }   -- every anchor, for the meter fill inset
end
function Region:ClearAllPoints() if refused(self, "ClearAllPoints") then return end self.pt = nil; self.pts = nil end
function Region:Show() if refused(self, "Show") then return end local was = self.shown; self.shown = true; if not was then runHooks(self, "OnShow") end end
function Region:Hide() if refused(self, "Hide") then return end local was = self.shown; self.shown = false; if was then runHooks(self, "OnHide") end end
function Region:SetShown(v) if v then self:Show() else self:Hide() end end
function Region:IsShown() return self.shown end
function Region:HookScript(which, fn) self.hooks[which] = self.hooks[which] or {}; table.insert(self.hooks[which], fn) end
function Region:SetScript(which, fn) self.scripts = self.scripts or {}; self.scripts[which] = fn end
function Region:RegisterEvent(e) self.events = self.events or {}; self.events[e] = true end
function Region:GetEffectiveScale() return self.scale * (self.parent and self.parent:GetEffectiveScale() or 1) end
function Region:CreateTexture() return new("texture", self) end
function Region:CreateFontString() return new("fontstring", self) end
function Region:SetText(t) self.text = t end
function Region:GetStringWidth() return #(self.text or "") * 6.5 end   -- "DEBUG" = 32.5
function Region:GetStatusBarTexture() return new("texture", self) end

UIParent = new("frame", nil, "UIParent")
UIParent.w = W
function CreateFrame(kind, name, parent)
    local f = new(kind, parent, name)
    if name then _G[name] = f end
    return f
end
function __setUiScale(s) UIParent.scale = s end
function __setScreenH(h) H = h end
function GetPhysicalScreenSize() return W, H end
function GetScreenWidth() return W end
function InCombatLockdown() return __combat end
date = os.date
GetFramerate = function() return 60 end
GetMoney = function() return 0 end
C_Container = { GetContainerNumFreeSlots = function() return __bagFree or 10 end, GetContainerNumSlots = function() return 20 end }
unpack = unpack or table.unpack

local noop = function() end
local FS = {
    Layout = { OnRescale = function(fn) __rescale[#__rescale + 1] = fn end },
    LogDegradeOnce = function(key, msg) __logs[#__logs + 1] = key end,
    Theme = {
        ApplyFontGeneric = noop, ApplyMono = noop,
        AddRoundedFill = function(_, _, rad) __themeCalls[#__themeCalls + 1] = { fn = "AddRoundedFill", rad = rad } end,
        AddGradientBorder = function(_, _, _, rad) __themeCalls[#__themeCalls + 1] = { fn = "AddGradientBorder", rad = rad } end,
        AddPillCaps = function(_, _, _, rad, height)
            __themeCalls[#__themeCalls + 1] = { fn = "AddPillCaps", rad = rad, height = height }
            return { textures = { new("texture"), new("texture"), new("texture"), new("texture") }, SetShown = noop }
        end,
        AddCutPillCaps = function(_, _, _, rad, height)
            __themeCalls[#__themeCalls + 1] = { fn = "AddCutPillCaps", rad = rad, height = height }
            return { textures = { new("texture"), new("texture"), new("texture"), new("texture") }, SetShown = noop }
        end,
        CHROME_CORNERS = "cut",
        -- SnapCut / CutSize mirror Theme.SnapCut / Theme.CutSize in Theme.lua.
        SnapCut = function(r) if not r or r <= 0 then return 0 end; local best = 2; for _, c in ipairs({ 2, 3, 4, 6 }) do if c <= r then best = c end end; return best end,
        CutSize = function(h) return __FS.Theme.SnapCut(math.min(math.max(math.floor(h / 3), 2), 6, math.floor(h / 2))) end,
        COLOR_TEXT_WHITE = { 1, 1, 1 }, COLOR_BG = { 0, 0, 0, 1 }, COLOR_POWER = { 0, 1, 1 },
        FONT_ORBITRON = "orbitron", FLAT_TEXTURE = "flat",
    },
}
__FS = FS

function __load(src)
    local chunk = assert(loadstring(src, "@DataBar.lua"))
    chunk("forever-stuwave", FS)
end
function __event(e)
    for _, f in ipairs(__frames) do
        if f.events and f.events[e] and f.scripts and f.scripts.OnEvent then f.scripts.OnEvent(f, e) end
    end
end
-- The bar's direct children in creation order, as { name, x, w, shown }.
function __children()
    local out = {}
    for _, f in ipairs(__frames) do
        if f.parent == _G.ForeverSTUwaveDataBar and f.kind ~= "texture" and f.kind ~= "fontstring" and f.pt then
            out[#out + 1] = { name = f.name, x = f.pt.x, w = f.w, shown = f.shown }
        end
    end
    return out
end
-- The DEBUG slot's own parts: its label, its recess, and where each is anchored.
function __linkParts()
    local link = _G.ForeverSTUwaveDataBarLink
    local label, recess
    for _, f in ipairs(__frames) do
        if f.parent == link and f.kind == "fontstring" and f.text == "DEBUG" then label = f end
        if f.parent == link and f.kind == "Frame" then recess = f end
    end
    return { link = link, label = label, recess = recess,
             labelAnchored = label.pt.point == "LEFT" and label.pt.rel == link and label.pt.relPoint == "LEFT"
                 and label.pt.x == 8 and label.pt.y == 0,
             recessAnchored = recess.pt.point == "LEFT" and recess.pt.rel == label and recess.pt.relPoint == "RIGHT"
                 and recess.pt.x == 6 and recess.pt.y == 0 }
end
function __makeBridge(shown, footprint)
    local b = CreateFrame("Frame", "ForeverDebugBridgeFrame", UIParent)
    b.shown = shown
    b.footprint = footprint
    return b
end
"""

FAILURES: list[str] = []
CHECKS = 0


def check(cond: bool, label: str, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not cond:
        FAILURES.append(f"{label}: {detail}" if detail else label)
        print(f"    FAIL  {label}" + (f"  [{detail}]" if detail else ""))


class Bar:
    def __init__(self, ui_scale: float = 0.5333, phys_h: int = PHYS_H, corners: str = "cut") -> None:
        self.rt = LuaRuntime(unpack_returned_tuples=False)
        self.rt.eval("function(src, ...) assert(loadstring(src))(...) end")(MOCK, SCREEN_W, phys_h)
        self.rt.execute(f'__FS.Theme.CHROME_CORNERS = "{corners}"')
        self.rt.execute(f"__setUiScale({ui_scale})")
        self.rt.eval("__load")(DATABAR.read_text(encoding="utf-8"))

    def run(self, code: str):
        return self.rt.execute(code)

    def login(self) -> None:
        self.rt.execute('__event("PLAYER_LOGIN")')

    def layout(self) -> list[dict]:
        """Bar children left to right as {key, x, w}; key is 'link' or the segment's SEGMENT_DEFS order."""
        kids = [dict(x=c["x"], w=c["w"], name=c["name"], shown=c["shown"])
                for c in self.rt.eval("__children()").values()]
        segs = [k for k in kids if k["name"] != "ForeverSTUwaveDataBarLink"]
        for key, k in zip(("fps", "bags", "time", "gold"), segs):
            k["key"] = key
        for k in kids:
            if k["name"] == "ForeverSTUwaveDataBarLink":
                k["key"] = "link"
        return sorted((k for k in kids if k["name"] != "ForeverSTUwaveDataBarLink" or k["shown"]),
                      key=lambda k: k["x"])

    def theme_calls(self) -> list[dict]:
        """Meter chrome calls (track fill, track border, fill caps) in order, as plain dicts."""
        return [{k: (str(v) if isinstance(v, str) else v) for k, v in c.items()}
                for c in self.rt.eval("__themeCalls").values()]

    def meter_fill_points(self) -> dict:
        """Anchor offsets {POINT: (x, y)} recorded on the meter fill (the StatusBar frame)."""
        pts = self.rt.eval("function() for _, f in ipairs(__frames) do if f.kind == 'StatusBar' then return f.pts end end end")()
        return {str(k): (v["x"], v["y"]) for k, v in pts.items()}

    def logs(self) -> list[str]:
        return [str(v) for v in self.rt.eval("__logs").values()]


def keys(layout: list[dict]) -> list[str]:
    return [k["key"] for k in layout]


def contiguous(layout: list[dict]) -> bool:
    return all(abs(a["x"] + a["w"] - b["x"]) < 1e-6 for a, b in zip(layout, layout[1:])) \
        and abs(layout[-1]["x"] + layout[-1]["w"] - SCREEN_W) < 1e-6 and layout[0]["x"] == 0


def link_width(ppu: float, cells_w: float = 228) -> float:
    return PAD_X + LABEL_W + LABEL_GAP + (cells_w + 2 * RECESS_PAD_PX) / ppu + LINK_END_PAD_PX / ppu


def test_equal_without_bridge() -> None:
    print("\n== no bridge: the bar lays out exactly as before")
    b = Bar()
    b.login()
    lay = b.layout()
    check(keys(lay) == ["fps", "bags", "time", "gold"], "no bridge: four segments, no DEBUG", str(keys(lay)))
    check(all(abs(k["w"] - SCREEN_W / 4) < 1e-6 for k in lay) and contiguous(lay),
          "no bridge: equal widths filling the bar with no gap", str([(k["key"], k["w"]) for k in lay]))
    seg_w = SCREEN_W / 4
    check(all(k["x"] == i * seg_w for i, k in enumerate(lay)),
          "no bridge: segment i sits at exactly (i - 1) * segWidth (no tolerance, the original formula)",
          str([(k["key"], k["x"]) for k in lay]))
    check(b.rt.eval("ForeverSTUwaveDataBar.linkSlot == ForeverSTUwaveDataBarLink")
          and not b.rt.eval("ForeverSTUwaveDataBarLink:IsShown()"), "DEBUG slot is built but hidden, exported as linkSlot")

    b.run("__makeBridge(false)")
    b.rt.execute('__event("PLAYER_ENTERING_WORLD")')
    check(keys(b.layout()) == ["fps", "bags", "time", "gold"], "bridge present but hidden: still no DEBUG")


def test_link_between_bags_and_time() -> None:
    print("\n== bridge shown: DEBUG between BAGS and TIME, then back with /fdebug hide|show")
    for ui, phys_h in ((0.5333, 1440), (0.64, 1440), (1.1, 1080)):
        ppu = ui * phys_h / 768
        tag = f"ui {ui} at {phys_h} high (px per unit {ppu:.3f})"
        b = Bar(ui_scale=ui, phys_h=phys_h)
        b.run("__makeBridge(true)")          # exists before the bar is built, as when both addons load
        b.login()
        lay = b.layout()
        check(keys(lay) == ["fps", "bags", "link", "time", "gold"], f"{tag}: DEBUG between BAGS and TIME", str(keys(lay)))
        link = next(k for k in lay if k["key"] == "link")
        check(abs(link["w"] - link_width(ppu)) < 1e-6, f"{tag}: DEBUG width is label + recess + pads from physical pixels",
              f"{link['w']} want {link_width(ppu)}")
        others = [k for k in lay if k["key"] != "link"]
        want = (SCREEN_W - link["w"]) / 4
        check(all(abs(k["w"] - want) < 1e-6 for k in others) and contiguous(lay),
              f"{tag}: the other segments share the remainder equally", str([(k["key"], round(k["w"], 2)) for k in lay]))

    b = Bar()
    b.login()                                  # bar first, bridge appears later
    b.run("__makeBridge(true)")
    b.rt.execute('__event("PLAYER_ENTERING_WORLD")')
    check("link" in keys(b.layout()), "bridge created after login: DEBUG appears on PLAYER_ENTERING_WORLD")
    b.run("ForeverDebugBridgeFrame:Hide()")
    lay = b.layout()
    check(keys(lay) == ["fps", "bags", "time", "gold"] and all(abs(k["w"] - SCREEN_W / 4) < 1e-6 for k in lay),
          "bridge hidden (OnHide): equal segments again", str(keys(lay)))
    b.run("ForeverDebugBridgeFrame:Show()")
    check(keys(b.layout()) == ["fps", "bags", "link", "time", "gold"], "bridge shown again (OnShow): DEBUG back")


def test_recess_geometry() -> None:
    print("\n== DEBUG recess: anchored after the label, sized footprint + 4 px each side, so the cells centre in it")
    for ui, phys_h in ((0.5333, 1440), (0.64, 1440), (1.1, 1080)):
        ppu = ui * phys_h / 768
        tag = f"ui {ui} at {phys_h} high"
        b = Bar(ui_scale=ui, phys_h=phys_h)
        b.run("__makeBridge(true, { w = 228, h = 18 })")
        b.login()
        parts = b.rt.eval("__linkParts()")
        link, label, recess = parts["link"], parts["label"], parts["recess"]
        check(parts["labelAnchored"], f"{tag}: label anchors LEFT to the slot's LEFT, PAD_X in, vertically centred")
        check(parts["recessAnchored"],
              f"{tag}: recess anchors LEFT to the label's RIGHT, LABEL_GAP away, vertically centred")
        want_w = (228 + 2 * RECESS_PAD_PX) / ppu           # footprint + 4 physical px each side, in bar units
        check(abs(recess.w - want_w) < 1e-9 and recess.h == 18,
              f"{tag}: recess is footprint + 4 px each side wide, bar height minus the 1 unit rails tall",
              f"{recess.w} x {recess.h} want {want_w} x 18")
        # The recess ends END_PAD short of the slot's right edge, so its centre is a fixed offset from the
        # slot edge: the cell field (centred on the recess) has the same 4 px of ground each side.
        right_gap = link.w - (PAD_X + LABEL_W + LABEL_GAP + recess.w)
        check(abs(right_gap - LINK_END_PAD_PX / ppu) < 1e-9, f"{tag}: slot ends END_PAD past the recess", str(right_gap))


def test_hooks_installed_once() -> None:
    print("\n== the bridge's OnShow/OnHide are hooked exactly once")
    b = Bar()
    b.run("__makeBridge(true)")
    b.login()
    for _ in range(3):
        b.rt.execute('__event("PLAYER_ENTERING_WORLD")')
    n = b.rt.eval("function() local h = ForeverDebugBridgeFrame.hooks; return { #(h.OnShow or {}), #(h.OnHide or {}) } end")()
    check((n[1], n[2]) == (1, 1), "OnShow and OnHide hooked once across login and repeated PLAYER_ENTERING_WORLD",
          f"OnShow {n[1]}, OnHide {n[2]}")


def test_rescale_and_footprint() -> None:
    print("\n== rescale, published footprint, short bar")
    b = Bar(ui_scale=0.64)
    b.run("__makeBridge(true, { w = 300, h = 18 })")
    b.login()
    link = next(k for k in b.layout() if k["key"] == "link")
    check(abs(link["w"] - link_width(0.64 * PHYS_H / 768, 300)) < 1e-6, "DEBUG uses the footprint the bridge publishes",
          str(link["w"]))
    b.run("__setUiScale(0.5333333333); for _, fn in ipairs(__rescale) do fn() end")
    link = next(k for k in b.layout() if k["key"] == "link")
    check(abs(link["w"] - link_width(0.5333333333 * PHYS_H / 768, 300)) < 1e-6, "UI scale change: DEBUG width recomputed on rescale",
          str(link["w"]))
    check(b.logs() == [], "a bar tall enough for the lattice logs nothing")

    b = Bar(ui_scale=0.4)                       # 20 units = 15 px < 18 + 2
    b.run("__makeBridge(true)")
    b.login()
    b.run("for _, fn in ipairs(__rescale) do fn() end")
    check("link" in keys(b.layout()), "short bar: DEBUG is still placed (it may overhang)")
    check(b.logs() == ["databar_link_short"], "short bar: logged once under databar_link_short", str(b.logs()))


def test_meter_corners() -> None:
    print("\n== meter chrome: cut path chamfers the track and uses cut caps, round path is unchanged")
    b = Bar(corners="cut")
    b.login()
    calls = b.theme_calls()
    names = [c["fn"] for c in calls]
    check(names == ["AddRoundedFill", "AddGradientBorder", "AddCutPillCaps"],
          "cut: BAGS meter builds track fill, track border, then AddCutPillCaps (no AddPillCaps)", str(names))
    tracks = [c for c in calls if c["fn"] in ("AddRoundedFill", "AddGradientBorder")]
    check(tracks and all(c["rad"] == 3 for c in tracks),
          "cut: track fill and border chamfer is CutSize(9) = 3", str(tracks))
    caps = [c for c in calls if c["fn"] == "AddCutPillCaps"]
    check(caps and caps[0]["rad"] == 3 and caps[0]["height"] == 7,
          "cut: fill caps chamfer 3 (matches the track) at fill height 7", str(caps))
    pts = b.meter_fill_points()
    check(pts.get("TOPLEFT") == (4, -1) and pts.get("BOTTOMRIGHT") == (-4, 1),
          "cut: fill inset is METER_INSET + chamfer = 4 on each side (x +4 left, -4 right)", str(pts))

    b = Bar(corners="round")
    b.login()
    calls = b.theme_calls()
    names = [c["fn"] for c in calls]
    check(names == ["AddRoundedFill", "AddGradientBorder", "AddPillCaps"],
          "round: BAGS meter still builds AddPillCaps, never AddCutPillCaps", str(names))
    tracks = [c for c in calls if c["fn"] in ("AddRoundedFill", "AddGradientBorder")]
    check(all(c["rad"] == 5 for c in tracks), "round: track radius stays 5", str(tracks))
    caps = [c for c in calls if c["fn"] == "AddPillCaps"]
    check(caps and caps[0]["rad"] == 3.5 and caps[0]["height"] == 7,
          "round: pill caps radius 3.5 at fill height 7 (today's call)", str(caps))
    pts = b.meter_fill_points()
    check(pts.get("TOPLEFT") == (4.5, -1) and pts.get("BOTTOMRIGHT") == (-4.5, 1),
          "round: fill inset stays METER_INSET + pill radius = 4.5 on each side", str(pts))


def test_combat() -> None:
    print("\n== combat: the restricted bar is not resized, re-anchored, shown or hidden; regen replays it")
    b = Bar()
    b.run("__makeBridge(true, { w = 228, h = 18 })")
    b.login()
    b.run("ForeverSTUwaveDataBar.restricted = true")     # the XP bar -> deck chassis -> secure bag buttons chain
    before = b.layout()
    check(keys(before) == ["fps", "bags", "link", "time", "gold"], "combat: set up with DEBUG shown", str(keys(before)))
    width = b.rt.eval("ForeverSTUwaveDataBar.w")

    b.run("__combat = true")
    b.run("UIParent.w = 1920; __setUiScale(0.64); for _, fn in ipairs(__rescale) do fn() end")
    b.run("ForeverDebugBridgeFrame:Hide()")           # /fdebug hide in combat: the OnHide hook runs Rescale
    b.rt.execute('__event("PLAYER_ENTERING_WORLD")')   # a zone change in combat: Rescale again
    check(b.rt.eval("#__blocked") == 0, "combat: a rescale, a /fdebug hide and a zone change block nothing",
          str(list(b.rt.eval("__blocked").values())))
    check(b.rt.eval("ForeverSTUwaveDataBar.w") == width, "combat: the bar keeps its width", str(b.rt.eval("ForeverSTUwaveDataBar.w")))
    after = b.layout()
    check([(k["key"], k["x"], k["w"]) for k in after] == [(k["key"], k["x"], k["w"]) for k in before],
          "combat: the segments (and DEBUG) keep their seats and widths", str([(k["key"], k["x"]) for k in after]))

    b.run("__combat = false")
    b.rt.execute('__event("PLAYER_REGEN_ENABLED")')
    check(b.rt.eval("#__blocked") == 0, "regen: replaying blocks nothing", str(list(b.rt.eval("__blocked").values())))
    check(b.rt.eval("ForeverSTUwaveDataBar.w") == 1920, "regen: the bar takes the screen width current now",
          str(b.rt.eval("ForeverSTUwaveDataBar.w")))
    lay = b.layout()
    check(keys(lay) == ["fps", "bags", "time", "gold"], "regen: the bridge hidden in combat takes DEBUG away", str(keys(lay)))
    check(all(abs(k["w"] - 1920 / 4) < 1e-6 for k in lay) and abs(lay[-1]["x"] + lay[-1]["w"] - 1920) < 1e-6,
          "regen: the segments share the new width equally", str([(k["key"], round(k["w"], 2)) for k in lay]))

    # With nothing pending, a regen leaves the bar alone (no resize per combat end).
    b.run("ForeverSTUwaveDataBar.w = 1234")
    b.rt.execute('__event("PLAYER_REGEN_ENABLED")')
    check(b.rt.eval("ForeverSTUwaveDataBar.w") == 1234, "regen with nothing pending does not re-run the layout")

    # Out of combat a rescale is still immediate.
    b.run("UIParent.w = 1600; for _, fn in ipairs(__rescale) do fn() end")
    check(b.rt.eval("ForeverSTUwaveDataBar.w") == 1600, "out of combat a rescale still applies at once")


def test_bags_gradient_colors_are_reused() -> None:
    print("\n== bags meter: the per-tick gradient reuses its colour objects")
    b = Bar()
    b.login()
    b.run("""
__colors = 0
CreateColor = function(r, g, bl, a) __colors = __colors + 1; return { r = r, g = g, b = bl, a = a } end
__gradients, __lastGradient = 0, nil
for _, f in ipairs(__frames) do
    if f.kind == "StatusBar" then
        f.GetStatusBarTexture = function()
            return { SetGradient = function(_, dir, left, right)
                __gradients = __gradients + 1; __lastGradient = { dir = dir, left = left, right = right }
            end }
        end
    end
end
local bar = ForeverSTUwaveDataBar
function __tick(free) __bagFree = free; bar.scripts.OnUpdate(bar, 100); return __lastGradient end
-- 20 slots per bag: free 10 = half used (OK), 4 = 80% (WARN, from 75%), 1 = 95% (FULL, from 90%)
__ok1, __warn1, __full1 = __tick(10), __tick(4), __tick(1)
__colors = 0
__ok2, __warn2, __full2 = __tick(10), __tick(4), __tick(1)
""")
    for label, var, rgb in (("OK", "ok", (0.133, 1, 0.463)), ("WARN", "warn", (1, 0.714, 0.282)),
                            ("FULL", "full", (1, 0.180, 0.592))):
        got = [b.rt.eval(f"__{var}1.left.{k}") for k in ("r", "g", "b", "a")]
        check(got == [*rgb, 1], f"bags {label}: gradient colour is the state's colour", str(got))
        check(b.rt.eval(f"__{var}1.dir") == "HORIZONTAL", f"bags {label}: gradient runs HORIZONTAL")
        check(b.rt.eval(f"__{var}1.left == __{var}1.right"), f"bags {label}: both gradient ends are the same object")
        check(b.rt.eval(f"__{var}2.left == __{var}1.left"), f"bags {label}: revisiting the state returns the same object")
    check(b.rt.eval("__ok1.left ~= __warn1.left and __warn1.left ~= __full1.left"), "bags: each state has its own colour object")
    check(b.rt.eval("__colors") == 0, "revisiting every state created no new colour objects", str(b.rt.eval("__colors")))


def main() -> int:
    test_equal_without_bridge()
    test_link_between_bags_and_time()
    test_recess_geometry()
    test_hooks_installed_once()
    test_rescale_and_footprint()
    test_meter_corners()
    test_combat()
    test_bags_gradient_colors_are_reused()
    print(f"\n{CHECKS} checks, {len(FAILURES)} failed")
    for f in FAILURES:
        print(f"  - {f}")
    return min(len(FAILURES), 255)


if __name__ == "__main__":
    sys.exit(main())
