#!/usr/bin/env python3
"""Headless check of DataBar.lua's STATUS segment (the ForeverStatusStrip lattice drawn inside the bar).

Runs the real addons/forever-stuwave/DataBar.lua under lupa against a small mock WoW API (a
layout harness: widgets record size, anchors, shown state and HookScript lists; every other
widget method is a no-op). It pins the behaviour the bar promises:

  * no ForeverStatusStripFrame, or one that is hidden: the segments share the full width equally,
    no gap, STATUS hidden (the bar lays out exactly as it did before STATUS existed);
  * bridge shown: STATUS sits between BAGS and TIME, takes the label + the bridge's PHYSICAL
    footprint converted to bar units at the bar's effective scale, and the other segments share
    the remainder equally; /fsstrip hide|show (the bridge's OnHide/OnShow) flips it live;
  * the width follows a UI scale change, and a bar too short for the lattice logs once;
  * COMBAT: the bar is restricted (the XP bar is anchored to it, the control deck chassis to the XP bar, and the deck
    hosts secure buttons), so a rescale or a /fsstrip show|hide in combat resizes, re-anchors, shows and hides nothing,
    and PLAYER_REGEN_ENABLED replays it from the state current then;
  * TIME tooltip: hovering the TIME segment (and only it) shows a GameTooltip headed "Time" with a "Local" line (the
    text the bar shows) and a "Realm" line (GetGameTime, 12-hour like the bar), anchored at the mouse (ANCHOR_CURSOR),
    refreshed when a minute rolls over, hidden on leave and on hide, never taking a tooltip another frame owns.

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
LABEL_W = 39.0          # the mock's GetStringWidth for "STATUS"
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
function Region:GetStringWidth() return #(self.text or "") * 6.5 end   -- "STATUS" = 39
function Region:GetStatusBarTexture() return new("texture", self) end

UIParent = new("frame", nil, "UIParent")
UIParent.w = W
function CreateFrame(kind, name, parent)
    local f = new(kind, parent, name)
    if name then _G[name] = f end
    return f
end
function Region:EnableMouse(v) self.mouse = v and true or false end
function __setUiScale(s) UIParent.scale = s end
function __setScreenH(h) H = h end
function GetPhysicalScreenSize() return W, H end
function GetScreenWidth() return W end
function InCombatLockdown() return __combat end
-- A fixed local clock where a test asks for one (__date["%I"] = "03" ...), the real one otherwise.
__date = {}
date = function(fmt) return __date[fmt] or os.date(fmt) end
-- The realm clock: GetGameTime answers 24-hour (hour, minute); __realm = false takes the function away.
__realm = { 16, 12 }
function GetGameTime() return __realm[1], __realm[2] end
-- GameTooltip, recording what was put in it and who owns it.
GameTooltip = { lines = {}, shown = false, owner = nil, clears = 0, hides = 0 }
function GameTooltip:SetOwner(o, anchor) self.owner, self.anchor, self.lines, self.shown = o, anchor, {}, false end
function GameTooltip:IsOwned(o) return self.owner == o end
function GameTooltip:ClearLines() self.lines = {}; self.clears = self.clears + 1 end
function GameTooltip:SetText(t, r, g, b) self.lines = { { left = t, color = { r, g, b } } } end
function GameTooltip:AddDoubleLine(l, r, lr, lg, lb, rr, rg, rb)
    self.lines[#self.lines + 1] = { left = l, right = r, leftColor = { lr, lg, lb }, rightColor = { rr, rg, rb } }
end
function GameTooltip:Show() self.shown = true end
function GameTooltip:Hide() self.shown = false; self.hides = self.hides + 1 end
-- Stands in for FrameHelpers.AnchorTooltip: puts the tooltip on the owner and records who asked.
__anchored = {}
GetFramerate = function() return 60 end
GetMoney = function() return 0 end
C_Container = { GetContainerNumFreeSlots = function() return __bagFree or 10 end, GetContainerNumSlots = function() return 20 end }
unpack = unpack or table.unpack

local noop = function() end
local FS = {
    IsSecret = function(v) return v == 99 end,   -- 99 stands in for a secret number
    FrameHelpers = { AnchorTooltip = function(owner) __anchored[#__anchored + 1] = owner; GameTooltip:SetOwner(owner, "ANCHOR_NONE") end },
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
-- The STATUS slot's own parts: its label, its recess, and where each is anchored.
function __linkParts()
    local link = _G.ForeverSTUwaveDataBarStatus
    local label, recess
    for _, f in ipairs(__frames) do
        if f.parent == link and f.kind == "fontstring" and f.text == "STATUS" then label = f end
        if f.parent == link and f.kind == "Frame" then recess = f end
    end
    return { link = link, label = label, recess = recess,
             labelAnchored = label.pt.point == "LEFT" and label.pt.rel == link and label.pt.relPoint == "LEFT"
                 and label.pt.x == 8 and label.pt.y == 0,
             recessAnchored = recess.pt.point == "LEFT" and recess.pt.rel == label and recess.pt.relPoint == "RIGHT"
                 and recess.pt.x == 6 and recess.pt.y == 0 }
end
-- A segment's frame and its value text, found by the label it was built with ("TIME"): the frame is the label's parent,
-- the value is the next font string created in that frame.
function __segment(label)
    local frame, value
    for _, f in ipairs(__frames) do
        if f.kind == "fontstring" and f.text == label and f.parent and f.parent.parent == _G.ForeverSTUwaveDataBar then
            frame = f.parent
        end
    end
    for _, f in ipairs(__frames) do
        if frame and f.kind == "fontstring" and f.parent == frame and f.text ~= label and not value then value = f end
    end
    return frame, value
end
function __makeBridge(shown, footprint)
    local b = CreateFrame("Frame", "ForeverStatusStripFrame", UIParent)
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
    def __init__(self, ui_scale: float = 0.5333, phys_h: int = PHYS_H, corners: str = "cut", pre: str = "") -> None:
        """`pre` is Lua run after the mock and before DataBar.lua loads (the module reads the client's API at load)."""
        self.rt = LuaRuntime(unpack_returned_tuples=False)
        self.rt.eval("function(src, ...) assert(loadstring(src))(...) end")(MOCK, SCREEN_W, phys_h)
        self.rt.execute(f'__FS.Theme.CHROME_CORNERS = "{corners}"')
        self.rt.execute(f"__setUiScale({ui_scale})")
        if pre:
            self.rt.execute(pre)
        self.rt.eval("__load")(DATABAR.read_text(encoding="utf-8"))

    def run(self, code: str):
        return self.rt.execute(code)

    def login(self) -> None:
        self.rt.execute('__event("PLAYER_LOGIN")')

    def layout(self) -> list[dict]:
        """Bar children left to right as {key, x, w}; key is 'link' or the segment's SEGMENT_DEFS order."""
        kids = [dict(x=c["x"], w=c["w"], name=c["name"], shown=c["shown"])
                for c in self.rt.eval("__children()").values()]
        segs = [k for k in kids if k["name"] != "ForeverSTUwaveDataBarStatus"]
        for key, k in zip(("fps", "bags", "time", "gold"), segs):
            k["key"] = key
        for k in kids:
            if k["name"] == "ForeverSTUwaveDataBarStatus":
                k["key"] = "link"
        return sorted((k for k in kids if k["name"] != "ForeverSTUwaveDataBarStatus" or k["shown"]),
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
    check(keys(lay) == ["fps", "bags", "time", "gold"], "no bridge: four segments, no STATUS", str(keys(lay)))
    check(all(abs(k["w"] - SCREEN_W / 4) < 1e-6 for k in lay) and contiguous(lay),
          "no bridge: equal widths filling the bar with no gap", str([(k["key"], k["w"]) for k in lay]))
    seg_w = SCREEN_W / 4
    check(all(k["x"] == i * seg_w for i, k in enumerate(lay)),
          "no bridge: segment i sits at exactly (i - 1) * segWidth (no tolerance, the original formula)",
          str([(k["key"], k["x"]) for k in lay]))
    check(b.rt.eval("ForeverSTUwaveDataBar.linkSlot == ForeverSTUwaveDataBarStatus")
          and not b.rt.eval("ForeverSTUwaveDataBarStatus:IsShown()"), "STATUS slot is built but hidden, exported as linkSlot")

    b.run("__makeBridge(false)")
    b.rt.execute('__event("PLAYER_ENTERING_WORLD")')
    check(keys(b.layout()) == ["fps", "bags", "time", "gold"], "bridge present but hidden: still no STATUS")


def test_link_between_bags_and_time() -> None:
    print("\n== bridge shown: STATUS between BAGS and TIME, then back with /fsstrip hide|show")
    for ui, phys_h in ((0.5333, 1440), (0.64, 1440), (1.1, 1080)):
        ppu = ui * phys_h / 768
        tag = f"ui {ui} at {phys_h} high (px per unit {ppu:.3f})"
        b = Bar(ui_scale=ui, phys_h=phys_h)
        b.run("__makeBridge(true)")          # exists before the bar is built, as when both addons load
        b.login()
        lay = b.layout()
        check(keys(lay) == ["fps", "bags", "link", "time", "gold"], f"{tag}: STATUS between BAGS and TIME", str(keys(lay)))
        link = next(k for k in lay if k["key"] == "link")
        check(abs(link["w"] - link_width(ppu)) < 1e-6, f"{tag}: STATUS width is label + recess + pads from physical pixels",
              f"{link['w']} want {link_width(ppu)}")
        others = [k for k in lay if k["key"] != "link"]
        want = (SCREEN_W - link["w"]) / 4
        check(all(abs(k["w"] - want) < 1e-6 for k in others) and contiguous(lay),
              f"{tag}: the other segments share the remainder equally", str([(k["key"], round(k["w"], 2)) for k in lay]))

    b = Bar()
    b.login()                                  # bar first, bridge appears later
    b.run("__makeBridge(true)")
    b.rt.execute('__event("PLAYER_ENTERING_WORLD")')
    check("link" in keys(b.layout()), "bridge created after login: STATUS appears on PLAYER_ENTERING_WORLD")
    b.run("ForeverStatusStripFrame:Hide()")
    lay = b.layout()
    check(keys(lay) == ["fps", "bags", "time", "gold"] and all(abs(k["w"] - SCREEN_W / 4) < 1e-6 for k in lay),
          "bridge hidden (OnHide): equal segments again", str(keys(lay)))
    b.run("ForeverStatusStripFrame:Show()")
    check(keys(b.layout()) == ["fps", "bags", "link", "time", "gold"], "bridge shown again (OnShow): STATUS back")


def test_recess_geometry() -> None:
    print("\n== STATUS recess: anchored after the label, sized footprint + 4 px each side, so the cells centre in it")
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
    n = b.rt.eval("function() local h = ForeverStatusStripFrame.hooks; return { #(h.OnShow or {}), #(h.OnHide or {}) } end")()
    check((n[1], n[2]) == (1, 1), "OnShow and OnHide hooked once across login and repeated PLAYER_ENTERING_WORLD",
          f"OnShow {n[1]}, OnHide {n[2]}")


def test_rescale_and_footprint() -> None:
    print("\n== rescale, published footprint, short bar")
    b = Bar(ui_scale=0.64)
    b.run("__makeBridge(true, { w = 300, h = 18 })")
    b.login()
    link = next(k for k in b.layout() if k["key"] == "link")
    check(abs(link["w"] - link_width(0.64 * PHYS_H / 768, 300)) < 1e-6, "STATUS uses the footprint the bridge publishes",
          str(link["w"]))
    b.run("__setUiScale(0.5333333333); for _, fn in ipairs(__rescale) do fn() end")
    link = next(k for k in b.layout() if k["key"] == "link")
    check(abs(link["w"] - link_width(0.5333333333 * PHYS_H / 768, 300)) < 1e-6, "UI scale change: STATUS width recomputed on rescale",
          str(link["w"]))
    check(b.logs() == [], "a bar tall enough for the lattice logs nothing")

    b = Bar(ui_scale=0.4)                       # 20 units = 15 px < 18 + 2
    b.run("__makeBridge(true)")
    b.login()
    b.run("for _, fn in ipairs(__rescale) do fn() end")
    check("link" in keys(b.layout()), "short bar: STATUS is still placed (it may overhang)")
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
    check(keys(before) == ["fps", "bags", "link", "time", "gold"], "combat: set up with STATUS shown", str(keys(before)))
    width = b.rt.eval("ForeverSTUwaveDataBar.w")

    b.run("__combat = true")
    b.run("UIParent.w = 1920; __setUiScale(0.64); for _, fn in ipairs(__rescale) do fn() end")
    b.run("ForeverStatusStripFrame:Hide()")           # /fsstrip hide in combat: the OnHide hook runs Rescale
    b.rt.execute('__event("PLAYER_ENTERING_WORLD")')   # a zone change in combat: Rescale again
    check(b.rt.eval("#__blocked") == 0, "combat: a rescale, a /fsstrip hide and a zone change block nothing",
          str(list(b.rt.eval("__blocked").values())))
    check(b.rt.eval("ForeverSTUwaveDataBar.w") == width, "combat: the bar keeps its width", str(b.rt.eval("ForeverSTUwaveDataBar.w")))
    after = b.layout()
    check([(k["key"], k["x"], k["w"]) for k in after] == [(k["key"], k["x"], k["w"]) for k in before],
          "combat: the segments (and STATUS) keep their seats and widths", str([(k["key"], k["x"]) for k in after]))

    b.run("__combat = false")
    b.rt.execute('__event("PLAYER_REGEN_ENABLED")')
    check(b.rt.eval("#__blocked") == 0, "regen: replaying blocks nothing", str(list(b.rt.eval("__blocked").values())))
    check(b.rt.eval("ForeverSTUwaveDataBar.w") == 1920, "regen: the bar takes the screen width current now",
          str(b.rt.eval("ForeverSTUwaveDataBar.w")))
    lay = b.layout()
    check(keys(lay) == ["fps", "bags", "time", "gold"], "regen: the bridge hidden in combat takes STATUS away", str(keys(lay)))
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


def lines(b: Bar) -> list[tuple]:
    """GameTooltip's lines as (left, right) python strings, header first."""
    return [(str(v["left"]), str(v["right"]) if v["right"] is not None else None)
            for v in b.rt.eval("GameTooltip.lines").values()]


def hover(b: Bar, label: str = "TIME") -> None:
    b.run(f'local f = __segment("{label}"); f.scripts.OnEnter(f)')


def test_time_tooltip() -> None:
    print("\n== TIME tooltip: local and realm time in GameTooltip on hover, only on the TIME segment")
    b = Bar()
    b.run('__date["%I"], __date["%M"], __date["%p"] = "03", "12", "PM"; __realm = { 16, 12 }')
    b.login()
    frame = b.rt.eval('(__segment("TIME"))')
    assert frame is not None, "no TIME segment was built"
    check(b.rt.eval('select(2, __segment("TIME")).text') == "3:12 PM",
          "the bar shows the local time, 12-hour, no leading zero", str(b.rt.eval('select(2, __segment("TIME")).text')))
    check(b.rt.eval('(__segment("TIME")).mouse') is True and callable(b.rt.eval('(__segment("TIME")).scripts.OnEnter')),
          "the TIME segment takes the mouse and has an OnEnter")
    others = [b.rt.eval(f'(__segment("{lbl}")).mouse') for lbl in ("FPS", "BAGS", "GOLD")]
    check(all(m in (None, False) for m in others)
          and all(b.rt.eval(f'(__segment("{lbl}")).scripts == nil') for lbl in ("FPS", "BAGS", "GOLD")),
          "no other segment takes the mouse or has scripts (click-through as before)", str(others))
    check(b.rt.eval("GameTooltip.shown") is False, "nothing shows before the mouse is on the segment")

    hover(b)
    got = lines(b)
    check(got == [("Time", None), ("Local", "3:12 PM"), ("Realm", "4:12 PM")],
          'hover: header "Time", then "Local 3:12 PM" and "Realm 4:12 PM"', str(got))
    check(b.rt.eval("GameTooltip.shown") is True and b.rt.eval('GameTooltip.owner == (__segment("TIME"))'),
          "hover: the tooltip is shown and owned by the TIME segment")
    check(b.rt.eval('GameTooltip.anchor') == "ANCHOR_CURSOR" and b.rt.eval('#__anchored == 0'),
          "hover: the tooltip sits at the mouse (ANCHOR_CURSOR), not at the tooltip seat")
    check(got[1][1] == str(b.rt.eval('select(2, __segment("TIME")).text')),
          "hover: the Local line is exactly the text the bar shows", str(got))
    cols = b.rt.eval("GameTooltip.lines[2].leftColor[1] == 0.60 and GameTooltip.lines[2].rightColor[1] == 1 "
                     "and GameTooltip.lines[1].color[2] == 1")
    check(cols is True, "hover: header cyan, labels muted, times white")
    texts = " ".join(f"{l} {r or ''}" for l, r in got).lower()
    check(not any(w in texts for w in ("bot", "automat", "macro", "macros")), "client text stays neutral", texts)

    b.run('local f = __segment("TIME"); f.scripts.OnLeave(f)')
    check(b.rt.eval("GameTooltip.shown") is False, "leave: the tooltip hides")
    b.run('GameTooltip:SetOwner(UIParent, "ANCHOR_CURSOR"); GameTooltip:Show(); local f = __segment("TIME"); f.scripts.OnLeave(f)')
    check(b.rt.eval("GameTooltip.shown") is True, "leave: another frame's tooltip is left alone")

    hover(b)
    b.run('local f = __segment("TIME"); f.scripts.OnHide(f)')
    check(b.rt.eval("GameTooltip.shown") is False, "hide with the mouse on it (no OnLeave comes): the tooltip hides")


def test_time_tooltip_formats() -> None:
    print("\n== TIME tooltip: realm time is 12-hour, the way the bar formats local time")
    cases = [((0, 5), "12:05 AM"), ((1, 0), "1:00 AM"), ((9, 30), "9:30 AM"), ((12, 0), "12:00 PM"),
             ((13, 7), "1:07 PM"), ((16, 12), "4:12 PM"), ((23, 59), "11:59 PM")]
    for (hour, minute), want in cases:
        b = Bar()
        b.run(f'__date["%I"], __date["%M"], __date["%p"] = "03", "12", "PM"; __realm = {{ {hour}, {minute} }}')
        b.login()
        hover(b)
        got = lines(b)
        check(len(got) == 3 and got[2] == ("Realm", want), f"realm {hour:02d}:{minute:02d} reads {want}", str(got))
    # local: %I's leading zero goes, midnight and noon read 12, the same call the bar makes
    for (i, m, p), want in ((("01", "05", "AM"), "1:05 AM"), (("12", "00", "AM"), "12:00 AM"), (("11", "45", "PM"), "11:45 PM")):
        b = Bar()
        b.run(f'__date["%I"], __date["%M"], __date["%p"] = "{i}", "{m}", "{p}"')
        b.login()
        hover(b)
        bar_text = str(b.rt.eval('select(2, __segment("TIME")).text'))
        got = lines(b)
        check(got[1] == ("Local", want) and bar_text == want, f"local {i}:{m} {p}: tooltip and bar both read {want}",
              f"{got} bar {bar_text}")
    # no realm clock, or a secret or odd one: the Realm line says so and nothing throws
    for name, pre, setup in (("no GetGameTime", "GetGameTime = nil", ""), ("nil hour", "", "__realm = { nil, 5 }"),
                             ("a secret hour", "", "__realm = { 99, 5 }"), ("a string minute", "", '__realm = { 4, "x" }')):
        b = Bar(pre=pre)
        b.run('__date["%I"], __date["%M"], __date["%p"] = "03", "12", "PM"; ' + setup)
        b.login()
        hover(b)
        got = lines(b)
        check(got == [("Time", None), ("Local", "3:12 PM"), ("Realm", "--")], f"{name}: Local still reads, Realm shows --", str(got))


def test_time_tooltip_refresh() -> None:
    print("\n== TIME tooltip: stays right while the mouse is on it, and never takes another frame's tooltip")
    b = Bar()
    b.run('__date["%I"], __date["%M"], __date["%p"] = "03", "12", "PM"; __realm = { 16, 12 }')
    b.login()
    hover(b)
    clears = b.rt.eval("GameTooltip.clears")
    b.run("local bar = ForeverSTUwaveDataBar; bar.scripts.OnUpdate(bar, 100)")
    check(lines(b)[1:] == [("Local", "3:12 PM"), ("Realm", "4:12 PM")] and b.rt.eval("GameTooltip.clears") == clears,
          "a tick in the same minute rewrites nothing", str(lines(b)))
    b.run('__date["%M"] = "13"; __realm = { 16, 13 }; local bar = ForeverSTUwaveDataBar; bar.scripts.OnUpdate(bar, 100)')
    got = lines(b)
    check(got == [("Time", None), ("Local", "3:13 PM"), ("Realm", "4:13 PM")] and b.rt.eval("GameTooltip.shown") is True,
          "a minute rolling over while hovering updates both lines", str(got))
    check(b.rt.eval('GameTooltip.owner == (__segment("TIME"))') and b.rt.eval("#__anchored") == 0,
          "the refresh keeps the tooltip where it was (no new anchor)")
    b.run('GameTooltip:SetOwner(UIParent, "ANCHOR_CURSOR"); GameTooltip:SetText("Other"); GameTooltip:Show()')
    b.run('__date["%M"] = "14"; __realm = { 16, 14 }; local bar = ForeverSTUwaveDataBar; bar.scripts.OnUpdate(bar, 100)')
    check(lines(b) == [("Other", None)] and b.rt.eval("GameTooltip.owner == UIParent"),
          "another frame's tooltip is never overwritten by the tick", str(lines(b)))
    b.run('__date["%M"] = "15"; __realm = { 16, 15 }; local bar = ForeverSTUwaveDataBar; bar.scripts.OnUpdate(bar, 100)')
    check(lines(b) == [("Other", None)], "and the segment forgets the hover until the mouse comes back")
    hover(b)
    check(lines(b) == [("Time", None), ("Local", "3:15 PM"), ("Realm", "4:15 PM")], "hovering again shows it afresh", str(lines(b)))

    # no FrameHelpers: the tooltip still sits at the mouse
    b = Bar()
    b.run('__FS.FrameHelpers = nil; __date["%I"], __date["%M"], __date["%p"] = "03", "12", "PM"')
    b.login()
    hover(b)
    check(b.rt.eval("GameTooltip.anchor") == "ANCHOR_CURSOR" and b.rt.eval('GameTooltip.owner == (__segment("TIME"))')
          and len(lines(b)) == 3, "without FrameHelpers the tooltip is still shown, at the mouse")


def test_time_tooltip_unavailable() -> None:
    print("\n== TIME tooltip: a client without GameTooltip loses the tooltip and nothing else")
    b = Bar()
    b.run("GameTooltip = nil")
    b.login()
    try:
        hover(b)
        b.run('local f = __segment("TIME"); f.scripts.OnLeave(f); f.scripts.OnHide(f)')
        ok = True
    except Exception as exc:   # noqa: BLE001 - the check is that nothing throws
        ok = False
        print(f"    raised {exc}")
    check(ok, "hover, leave and hide without a GameTooltip raise nothing")


DUR_PRE = """
__dur = { [1] = { 40, 50 }, [5] = { 30, 100 }, [16] = { 9, 60 } }
function GetInventoryItemDurability(slot) local d = __dur[slot]; if d then return d[1], d[2] end end
function GameTooltip:AddLine(t, r, g, b) self.lines[#self.lines + 1] = { left = t, color = { r, g, b } } end
"""


def test_durability_tooltip() -> None:
    print("\n== DUR tooltip: each equipped piece's durability percent on hover, at the mouse")
    b = Bar(pre=DUR_PRE)
    b.login()
    check(b.rt.eval('(__segment("DUR")).mouse') is True, "the DUR segment takes the mouse")
    hover(b, "DUR")
    got = lines(b)
    check(got == [("Durability", None), ("Head", "80%"), ("Chest", "30%"), ("Main Hand", "15%")],
          "header, then one line per piece in slot order with its percent", str(got))
    check(b.rt.eval('GameTooltip.anchor') == "ANCHOR_CURSOR" and b.rt.eval('GameTooltip.owner == (__segment("DUR"))'),
          "at the mouse, owned by the DUR segment")
    cols = b.rt.eval("GameTooltip.lines[2].rightColor[2] == 1 and GameTooltip.lines[3].rightColor[3] < 0.3 "
                     "and GameTooltip.lines[4].rightColor[2] < 0.2")
    check(cols is True, "white when fine, amber under half, pink under a fifth")
    clears = b.rt.eval("GameTooltip.clears")
    b.run("local bar = ForeverSTUwaveDataBar; bar.scripts.OnUpdate(bar, 100)")
    check(b.rt.eval("GameTooltip.clears") == clears, "a tick with nothing changed rewrites nothing")
    b.run("__dur[16] = { 60, 60 }; local bar = ForeverSTUwaveDataBar; bar.scripts.OnUpdate(bar, 100)")
    check(lines(b)[3] == ("Main Hand", "100%"), "a repair while hovering updates the line", str(lines(b)))
    b.run('local f = __segment("DUR"); f.scripts.OnLeave(f)')
    check(b.rt.eval("GameTooltip.shown") is False, "leave: the tooltip hides")
    b.run("__dur = {}")
    hover(b, "DUR")
    check(lines(b) == [("Durability", None), ("Nothing equipped wears down.", None)], "no gear: one muted line",
          str(lines(b)))


def main() -> int:
    test_equal_without_bridge()
    test_link_between_bags_and_time()
    test_recess_geometry()
    test_hooks_installed_once()
    test_rescale_and_footprint()
    test_meter_corners()
    test_combat()
    test_bags_gradient_colors_are_reused()
    test_time_tooltip()
    test_time_tooltip_formats()
    test_time_tooltip_refresh()
    test_time_tooltip_unavailable()
    test_durability_tooltip()
    print(f"\n{CHECKS} checks, {len(FAILURES)} failed")
    for f in FAILURES:
        print(f"  - {f}")
    return min(len(FAILURES), 255)


if __name__ == "__main__":
    sys.exit(main())
