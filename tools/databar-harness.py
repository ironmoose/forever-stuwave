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

  * REP and PROF (E2): the watched faction as a meter plus its short name ("none" when nothing is watched), the two
    primary professions as "BS 142  MIN 150", their tooltips, both off by default, refreshed on UPDATE_FACTION and
    SKILL_LINES_CHANGED; a left click opens the window for DUR, TIME, GOLD, REP and PROF (out of combat only, in combat
    nothing happens and the tooltip says so), BAGS delegates to the stock backpack button through a secure overlay.
  * SETTINGS (E1): databar.order, databar.seg.<key> and databar.title.<key> pick, order and rename the segments; a
    change re-lays the bar out live (no reload), hidden segments stop updating, the STATUS slot keeps its rule (before
    TIME, at the end without TIME), defaults leave the bar as it was (minus MEM and CPU, which start off), at least one
    segment always stays on, titles are at most 10 characters, an empty one shows only the value, a long one is clipped
    before the value, a change in combat waits for regen; FS.DataBarSegments is the API the config page calls.

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
function Region:Hide()
    if refused(self, "Hide") then return end
    local was = self.shown
    self.shown = false
    if was then
        runHooks(self, "OnHide")
        if self.scripts and self.scripts.OnHide then self.scripts.OnHide(self) end
    end
end
function Region:SetShown(v) if v then self:Show() else self:Hide() end end
function Region:IsShown() return self.shown end
function Region:HookScript(which, fn) self.hooks[which] = self.hooks[which] or {}; table.insert(self.hooks[which], fn) end
function Region:SetScript(which, fn) self.scripts = self.scripts or {}; self.scripts[which] = fn end
function Region:RegisterEvent(e) self.events = self.events or {}; self.events[e] = true end
function Region:GetEffectiveScale() return self.scale * (self.parent and self.parent:GetEffectiveScale() or 1) end
function Region:CreateTexture() return new("texture", self) end
function Region:CreateFontString() return new("fontstring", self) end
function Region:SetText(t) self.text = t end
function Region:SetValue(v) self.value = v end
function Region:SetAttribute(k, v) self.attrs = self.attrs or {}; self.attrs[k] = v end
function Region:RegisterForClicks(...) self.clicks = { ... } end
function Region:SetFormattedText(f, ...) self.text = string.format(f, ...) end
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
-- FS.Config as Config.lua behaves: defaults, a value equal to its default stored as nothing, key callbacks (new, old, key)
-- when the effective value changes (tables compare by reference), Set refused while __cfgReadOnly.
local cfgDefaults, cfgSettings, cfgCallbacks = {}, {}, {}
__cfg = { defaults = cfgDefaults, settings = cfgSettings }
local function cfgEffective(key) local v = cfgSettings[key]; if v == nil then return cfgDefaults[key] end return v end
local Config = {
    RegisterDefault = function(key, value) cfgDefaults[key] = value end,
    Get = cfgEffective,
    Set = function(key, value)
        if __cfgReadOnly then return false end
        local old = cfgEffective(key)
        if value == cfgDefaults[key] then value = nil end
        cfgSettings[key] = value
        local new = cfgEffective(key)
        if old ~= new then for _, fn in ipairs(cfgCallbacks[key] or {}) do fn(new, old, key) end end
        return true
    end,
    OnChange = function(key, fn) cfgCallbacks[key] = cfgCallbacks[key] or {}; table.insert(cfgCallbacks[key], fn) end,
}
local FS = {
    Config = Config,
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
-- The segment keys this client's globals can build, in SEGMENT_DEFS order (mirrors each def's `available`).
function __createdKeys()
    local has = {
        fps = GetFramerate ~= nil, mem = UpdateAddOnMemoryUsage ~= nil, cpu = GetAddOnCPUUsage ~= nil,
        latency = GetNetStats ~= nil, rested = GetXPExhaustion ~= nil, durability = GetInventoryItemDurability ~= nil,
        bags = (C_Container and C_Container.GetContainerNumFreeSlots) ~= nil, time = date ~= nil or GetGameTime ~= nil,
        gold = GetMoney ~= nil, rep = (C_Reputation and C_Reputation.GetWatchedFactionData) ~= nil,
        prof = GetProfessions ~= nil and GetProfessionInfo ~= nil,
    }
    local out = {}
    for _, k in ipairs({ "fps", "mem", "cpu", "latency", "rested", "durability", "bags", "time", "gold", "rep", "prof" }) do
        if has[k] then out[#out + 1] = k end
    end
    return out
end
-- The bar's segment frames (every built segment, placed or parked) in creation order, then the STATUS slot, as
-- { name, key, x, w, shown, placed } with the parts a settings test reads: divider shown, label text/shown/width and
-- the anchor of what follows the title.
function __children()
    local out, keys, n = {}, __createdKeys(), 0
    for _, f in ipairs(__frames) do
        if f.parent == _G.ForeverSTUwaveDataBar and f.kind ~= "texture" and f.kind ~= "fontstring" then
            local row = { name = f.name, shown = f.shown, placed = f.pt ~= nil, x = f.pt and f.pt.x, w = f.w }
            if f.name ~= "ForeverSTUwaveDataBarStatus" then
                n = n + 1
                row.key = keys[n]
                local textures, fonts, frames = {}, {}, {}
                for _, c in ipairs(__frames) do
                    if c.parent == f then
                        if c.kind == "texture" then textures[#textures + 1] = c
                        elseif c.kind == "fontstring" then fonts[#fonts + 1] = c
                        else frames[#frames + 1] = c end
                    end
                end
                local label, value, divider = fonts[1], fonts[2], textures[1]
                row.dividerShown = divider and divider.shown or false
                row.label, row.labelShown, row.labelW = label.text, label.shown, label.w
                local first = value                       -- what follows the title: the value, the meter, or the first coin
                if frames[1] then first = frames[1] elseif keys[n] == "gold" then first = textures[2] end
                row.firstPt = first.pt and { point = first.pt.point, rel = first.pt.rel == label and "label"
                    or (first.pt.rel == f and "segment" or "other"), relPoint = first.pt.relPoint, x = first.pt.x, y = first.pt.y }
                row.value = value.text
            end
            out[#out + 1] = row
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
    def __init__(self, ui_scale: float = 0.5333, phys_h: int = PHYS_H, corners: str = "cut", pre: str = "",
                 config: bool = True) -> None:
        """`pre` is Lua run after the mock and before DataBar.lua loads (the module reads the client's API at load);
        `config` False loads the module without FS.Config."""
        self.rt = LuaRuntime(unpack_returned_tuples=False)
        self.rt.eval("function(src, ...) assert(loadstring(src))(...) end")(MOCK, SCREEN_W, phys_h)
        self.rt.execute(f'__FS.Theme.CHROME_CORNERS = "{corners}"')
        self.rt.execute(f"__setUiScale({ui_scale})")
        if not config:
            self.rt.execute("__FS.Config = nil")
        if pre:
            self.rt.execute(pre)
        self.rt.eval("__load")(DATABAR.read_text(encoding="utf-8"))

    def run(self, code: str):
        return self.rt.execute(code)

    def login(self) -> None:
        self.rt.execute('__event("PLAYER_LOGIN")')

    def children(self) -> list[dict]:
        """Every segment frame (placed or parked, in creation order) then the STATUS slot, as plain dicts."""
        out = []
        for c in self.rt.eval("__children()").values():
            row = {k: (str(v) if isinstance(v, bytes) else v) for k, v in dict(c).items()}
            if row.get("firstPt") is not None:
                row["firstPt"] = {k: (str(v) if isinstance(v, bytes) else v) for k, v in dict(row["firstPt"]).items()}
            row["key"] = "link" if row.get("name") == "ForeverSTUwaveDataBarStatus" else row.get("key")
            out.append(row)
        return out

    def layout(self) -> list[dict]:
        """The placed segments (and STATUS while shown) left to right as {key, x, w, ...}; key is 'link' or the
        segment's SEGMENT_DEFS key."""
        return sorted((k for k in self.children() if k["placed"] and (k["key"] != "link" or k["shown"])),
                      key=lambda k: k["x"])

    def seg(self, key: str) -> dict:
        return next(k for k in self.children() if k["key"] == key)

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
    others = [b.rt.eval(f'(__segment("{lbl}")).mouse') for lbl in ("FPS", "BAGS")]
    check(all(m in (None, False) for m in others)
          and all(b.rt.eval(f'(__segment("{lbl}")).scripts == nil') for lbl in ("FPS", "BAGS")),
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


GOLD_PRE = """
__money = 1234567
GetMoney = function() return __money end
function UnitGUID() return "Player-91-AAA" end
function GetUnitName() return "Stu Shockalaka" end
function GetRealmName() return "Forever" end
function UnitClass() return "Shaman", "SHAMAN" end
function time() return 1000 end
RAID_CLASS_COLORS = { SHAMAN = { r = 0, g = 0.44, b = 0.87 }, WARRIOR = { r = 0.78, g = 0.61, b = 0.43 } }
ForeverSTUwaveDB = { gold = { ["Player-91-BBB"] = { name = "Stu Moolah", class = "WARRIOR", copper = 50000 },
                              ["Player-91-CCC"] = { name = "Stu Bank", copper = 9999999 } } }
"""


def test_gold_tooltip() -> None:
    print("\n== GOLD tooltip: every character's gold, richest first, with a total")
    b = Bar(pre=GOLD_PRE)
    b.login()
    b.run("local bar = ForeverSTUwaveDataBar; bar.scripts.OnUpdate(bar, 100)")
    row = b.rt.eval('ForeverSTUwaveDB.gold["Player-91-AAA"]')
    check(row is not None and row["copper"] == 1234567 and str(row["name"]) == "Stu Shockalaka"
          and str(row["class"]) == "SHAMAN", "the character on is recorded by GUID with full name and class")
    hover(b, "GOLD")
    got = lines(b)
    names = [g[0] for g in got]
    check(names[0] == "Gold" and names[1] == "Stu Bank" and names[2].startswith("Stu Shockalaka")
          and names[3] == "Stu Moolah" and names[4] == "Total", "header, richest first, then a total", str(got))
    check("<" in names[2], "the character you are on is marked", names[2])
    check("999" in got[1][1] and "g" in got[1][1] and "5" in got[3][1], "money text per row", str(got))
    check("1128" in got[4][1], "total of all rows (1128g)", got[4][1])
    col = b.rt.eval("GameTooltip.lines[4].leftColor")
    check(col is not None and abs(col[1] - 0.78) < 1e-6, "names in class colour")
    clears = b.rt.eval("GameTooltip.clears")
    b.run("local bar = ForeverSTUwaveDataBar; bar.scripts.OnUpdate(bar, 100)")
    check(b.rt.eval("GameTooltip.clears") == clears, "a tick with nothing changed rewrites nothing")
    b.run("__money = 20000000; local bar = ForeverSTUwaveDataBar; bar.scripts.OnUpdate(bar, 100)")
    check(lines(b)[1][0].startswith("Stu Shockalaka"), "new money while hovering re-sorts", str(lines(b)))


# ---------------------------------------------------------------------------------------------------------------
# Settings (E1): which segments show, in what order, under what title
# ---------------------------------------------------------------------------------------------------------------

NINE = ["fps", "mem", "cpu", "latency", "rested", "durability", "bags", "time", "gold"]   # what FULL_PRE builds
ALL = NINE + ["rep", "prof"]                                                              # every row of the page
DEFAULT_SHOWN = ["fps", "latency", "rested", "durability", "bags", "time", "gold"]   # MEM and CPU start off
LABELS = {"fps": "FPS", "mem": "FS MEM", "cpu": "FS CPU", "latency": "MS", "rested": "REST", "durability": "DUR",
          "bags": "BAGS", "time": "TIME", "gold": "GOLD", "rep": "REP", "prof": "PROF"}
TIPS = {
    "fps": "Frames per second.",
    "mem": "Memory this addon uses. For bug reports; most players leave it off.",
    "cpu": "Share of one CPU core this addon uses. For bug reports.",
    "latency": "Home and world latency.",
    "rested": "Rested XP as a meter.",
    "durability": "Durability across all your gear, as one percent. Hover for each piece.",
    "bags": "Free bag slots.",
    "time": "Realm and local time.",
    "gold": "Gold on this character; the tooltip lists your other characters.",
    "rep": "Your watched faction and its standing.",
    "prof": "Profession skill levels.",
}
LOCK = "At least one segment stays on."

# Every API the nine segments read, so all nine can be built.
FULL_PRE = """
GetNetStats = function() return 0, 0, 40, 55 end
GetXPExhaustion = function() return nil end
UnitXPMax = function() return 1000 end
__dur = { [1] = { 40, 50 }, [5] = { 30, 100 } }
function GetInventoryItemDurability(slot) local d = __dur[slot]; if d then return d[1], d[2] end end
__fpsCalls, __memCalls, __cpuCalls = 0, 0, 0
GetFramerate = function() __fpsCalls = __fpsCalls + 1; return 60 end
UpdateAddOnMemoryUsage = function() __memCalls = __memCalls + 1 end
GetAddOnMemoryUsage = function() return 2048 end
UpdateAddOnCPUUsage = function() __cpuCalls = __cpuCalls + 1 end
GetAddOnCPUUsage = function() return 0 end
GetCVar = function() return "0" end
GetTime = function() return 1000 end
GetMoney = function() return 1234567 end
function GameTooltip:AddLine(t, r, g, b) self.lines[#self.lines + 1] = { left = t, color = { r, g, b } } end
"""


def full(pre: str = "", **kw) -> Bar:
    return Bar(pre=FULL_PRE + pre, **kw)


def placed(b: Bar) -> list[str]:
    """The segment keys on the bar, left to right (STATUS left out)."""
    return [k["key"] for k in b.layout() if k["key"] != "link"]


def tick(b: Bar) -> None:
    b.run("local bar = ForeverSTUwaveDataBar; bar.scripts.OnUpdate(bar, 100)")


def api(b: Bar, call: str) -> tuple:
    """Calls FS.DataBarSegments.<call> and answers (ok, reason-or-second-value)."""
    t = b.rt.eval(f"function() local a, b = __FS.DataBarSegments.{call}; return {{ a, b }} end")()
    return t[1], t[2]


def model(b: Bar) -> list[dict]:
    return [dict(r) for r in b.rt.eval("__FS.DataBarSegments.Model()").values()]


def stored(b: Bar, key: str):
    return b.rt.eval(f'__cfg.settings["{key}"]')


def shares_equally(lay: list[dict], width: float = SCREEN_W) -> bool:
    segs = [k for k in lay if k["key"] != "link"]
    return bool(segs) and all(abs(k["w"] - segs[0]["w"]) < 1e-9 for k in segs) and (
        "link" in keys(lay) or contiguous(lay) or abs(segs[-1]["x"] + segs[-1]["w"] - width) < 1e-6)


def test_settings_defaults() -> None:
    print("\n== settings: defaults leave today's bar (minus MEM and CPU, which start off)")
    b = full()
    b.login()
    lay = b.layout()
    check(keys(lay) == DEFAULT_SHOWN, "default order and visibility", str(keys(lay)))
    want_w = SCREEN_W / len(DEFAULT_SHOWN)
    check(all(abs(k["w"] - want_w) < 1e-9 for k in lay) and contiguous(lay),
          "the seven share the width equally (widths re-shared as before), no gap", str([(k["key"], k["w"]) for k in lay]))
    check(all(k["x"] == i * want_w for i, k in enumerate(lay)), "segment i sits at exactly (i - 1) * segWidth",
          str([(k["key"], k["x"]) for k in lay]))
    check([b.seg(k)["dividerShown"] for k in DEFAULT_SHOWN] == [False] + [True] * 6,
          "the first segment has no divider, every other one has", str([b.seg(k)["dividerShown"] for k in DEFAULT_SHOWN]))
    for key in ("mem", "cpu"):
        seg = b.seg(key)
        check(seg["shown"] is False and seg["placed"] is False, f"{key} is built but parked (hidden, no anchors)", str(seg))
    check(all(b.seg(k)["label"] == LABELS[k] for k in NINE), "every default title is today's label",
          str({k: b.seg(k)["label"] for k in NINE}))
    check(all(b.seg(k)["labelShown"] for k in DEFAULT_SHOWN) and all(b.seg(k)["labelW"] == 0 for k in DEFAULT_SHOWN),
          "default titles are shown at their natural width (no clip)")
    check(all(b.seg(k)["firstPt"] == {"point": "LEFT", "rel": "label", "relPoint": "RIGHT", "x": 6, "y": 0}
              for k in DEFAULT_SHOWN), "what follows each title is anchored LABEL_GAP right of it, as always",
          str({k: b.seg(k)["firstPt"] for k in DEFAULT_SHOWN}))
    check(stored(b, "databar.order") is None and stored(b, "databar.seg.fps") is None
          and stored(b, "databar.title.fps") is None, "defaults store nothing")

    # hidden segments are not read, shown ones are
    tick(b)
    tick(b)
    check(b.rt.eval("__memCalls") == 0 and b.rt.eval("__cpuCalls") == 0,
          "MEM and CPU (off) are never read", f"mem {b.rt.eval('__memCalls')} cpu {b.rt.eval('__cpuCalls')}")
    check(b.rt.eval("__fpsCalls") >= 2, "FPS (on) is read every tick")


def test_settings_model() -> None:
    print("\n== settings: Model() rows for the config page")
    b = full()
    b.login()
    rows = model(b)
    check([r["key"] for r in rows] == ALL, "one row per segment in default order, REP and PROF last",
          str([r["key"] for r in rows]))
    check(all(r["label"] == LABELS[r["key"]] and r["title"] == LABELS[r["key"]] and r["titleIsDefault"] for r in rows),
          "label and title are today's label")
    check(all(r["tip"] == TIPS[r["key"]] for r in rows), "tips are the row texts (no click sentence without the toggles)",
          str([r["tip"] for r in rows]))
    check([r["on"] for r in rows] == [k in DEFAULT_SHOWN for k in ALL], "on follows the defaults", str([r["on"] for r in rows]))
    check(all(r["available"] and r.get("reason") is None and r.get("lock") is None for r in rows[:9]),
          "the nine this mock can build are available and unlocked")
    check([r["available"] for r in rows[9:]] == [False, False] and all(r["lock"] == r["reason"] for r in rows[9:]),
          "REP and PROF are unavailable here (no reputation or profession API): disabled with the reason")
    check([r["canUp"] for r in rows] == [False] + [True] * 10 and [r["canDown"] for r in rows] == [True] * 10 + [False],
          "the first row cannot go up and the last cannot go down")
    texts = " ".join(r["tip"] for r in rows).lower()
    check(not any(w in texts for w in ("bot", "automat", "macro")), "tips stay neutral", texts)

    # an unavailable segment: row disabled with a reason, not built, never shown
    b = Bar()                                   # the base mock has no latency, rested, durability, mem or cpu API
    b.login()
    rows = {r["key"]: r for r in model(b)}
    check([k for k in rows] == ALL, "unavailable segments still have a row", str(list(rows)))
    for key in ("mem", "cpu", "latency", "rested", "durability", "rep", "prof"):
        r = rows[key]
        check(r["available"] is False and r["on"] is False and r["reason"] and r["lock"] == r["reason"],
              f"{key}: unavailable, off, and the lock text names why", str(r))
    check("report" in rows["latency"]["reason"], "the reason says what the client lacks", rows["latency"]["reason"])
    check(api(b, 'SetEnabled("latency", true)')[0] is False and stored(b, "databar.seg.latency") is None,
          "switching an unavailable segment on is refused and stores nothing")
    check(len([c for c in b.children() if c["key"] not in (None, "link")]) == 4, "only the four available segments were built")


def test_settings_order_live() -> None:
    print("\n== settings: order changes re-lay the bar out at once")
    b = full()
    b.login()
    ok, _ = api(b, 'SetOrder({"gold", "fps"})')
    check(ok is True, "SetOrder accepts a partial list")
    check(placed(b) == ["gold", "fps", "latency", "rested", "durability", "bags", "time"],
          "named keys first, the rest in default order, no reload", str(placed(b)))
    lay = b.layout()
    check(all(abs(k["w"] - SCREEN_W / 7) < 1e-9 for k in lay) and contiguous(lay), "widths unchanged by a reorder")
    check(b.seg("gold")["dividerShown"] is False and b.seg("fps")["dividerShown"] is True,
          "the divider follows the position: GOLD first has none, FPS now has one")
    check(len(stored(b, "databar.order")) == 11, "the stored order lists every segment")
    check([r["key"] for r in model(b)][:3] == ["gold", "fps", "mem"], "Model follows the order", str([r["key"] for r in model(b)]))

    ok, _ = api(b, 'SetOrder(__FS.DataBarSegments.Order())')
    check(ok is True and placed(b)[0] == "gold", "SetOrder(Order()) changes nothing")
    api(b, 'SetOrder({"fps","mem","cpu","latency","rested","durability","bags","time","gold","rep","prof"})')
    check(placed(b) == DEFAULT_SHOWN and stored(b, "databar.order") is None,
          "the default order is stored as nothing and comes back as it was", str(placed(b)))

    b = full()
    b.login()
    check(api(b, 'Move("gold", -1)')[0] is True and placed(b)[-2:] == ["gold", "time"], "Move left swaps with the neighbour",
          str(placed(b)))
    check(api(b, 'Move("fps", -1)')[0] is False, "Move refuses at the left end")
    ok, why = api(b, 'Move("prof", 1)')
    check(ok is False, "Move refuses at the right end", str(why))
    check(api(b, 'Move("nope", 1)')[0] is False, "Move refuses an unknown key")
    # hidden segments move too: MEM sits between FPS and CPU even though it is off
    api(b, 'Move("mem", 1)')
    check([r["key"] for r in model(b)][:3] == ["fps", "cpu", "mem"], "a hidden segment moves in the full list",
          str([r["key"] for r in model(b)]))
    check("mem" not in placed(b), "and stays off the bar")


def test_settings_visibility_live() -> None:
    print("\n== settings: switches show and hide segments live; a hidden segment stops updating")
    b = full()
    b.login()
    tick(b)
    ok, _ = api(b, 'SetEnabled("fps", false)')
    lay = b.layout()
    check(ok is True and keys(lay) == DEFAULT_SHOWN[1:], "FPS off: gone from the bar at once", str(keys(lay)))
    check(all(abs(k["w"] - SCREEN_W / 6) < 1e-9 for k in lay) and contiguous(lay),
          "the six left share the width", str([(k["key"], round(k["w"], 1)) for k in lay]))
    check(b.seg("latency")["dividerShown"] is False, "MS is first now and loses its divider")
    seg = b.seg("fps")
    check(seg["shown"] is False and seg["placed"] is False, "the hidden segment is hidden and parked", str(seg))
    before = b.rt.eval("__fpsCalls")
    tick(b)
    tick(b)
    check(b.rt.eval("__fpsCalls") == before, "a hidden segment is not read", f"{before} -> {b.rt.eval('__fpsCalls')}")

    api(b, 'SetEnabled("fps", true)')
    check(placed(b) == DEFAULT_SHOWN and b.rt.eval("__fpsCalls") == before + 1,
          "switched back on: back in its place and read at once, not on the next tick", str(placed(b)))
    check(b.seg("fps").get("value") == "60", "its value is on the bar", str(b.seg("fps").get("value")))

    api(b, 'SetEnabled("mem", true)')
    check(placed(b)[:2] == ["fps", "mem"] and b.rt.eval("__memCalls") == 1, "MEM on: between FPS and MS, read once",
          f"{placed(b)} {b.rt.eval('__memCalls')}")
    check(b.seg("mem").get("value") == "2.0M", "MEM shows its value", str(b.seg("mem").get("value")))
    api(b, 'SetEnabled("mem", false)')
    check("mem" not in placed(b), "MEM off again")

    # a tooltip held by a segment that goes off the bar is let go (the OnHide script runs)
    hover(b, "DUR")
    check(b.rt.eval("GameTooltip.shown") is True, "DUR tooltip is up")
    api(b, 'SetEnabled("durability", false)')
    check(b.rt.eval("GameTooltip.shown") is False, "DUR switched off with the mouse on it: the tooltip hides")


def test_settings_last_segment_stays() -> None:
    print("\n== settings: at least one segment always stays on")
    b = Bar()                                   # fps, bags, time, gold available
    b.login()
    for key in ("fps", "bags", "time"):
        check(api(b, f'SetEnabled("{key}", false)')[0] is True, f"{key} can go off while others stay")
    check(placed(b) == ["gold"], "one left", str(placed(b)))
    ok, why = api(b, 'SetEnabled("gold", false)')
    check(ok is False and why == LOCK, "the last one refuses to go off, and says why", f"{ok} {why}")
    check(stored(b, "databar.seg.gold") is None and placed(b) == ["gold"], "it stays on the bar")
    rows = {r["key"]: r for r in model(b)}
    check(rows["gold"]["on"] is True and rows["gold"]["lock"] == LOCK, "Model locks the last switch with the text",
          str(rows["gold"]))
    check(rows["fps"].get("lock") is None and rows["fps"]["on"] is False, "the others stay free to switch on")
    check(shares_equally(b.layout()) and abs(b.layout()[0]["w"] - SCREEN_W) < 1e-9, "the one left takes the whole bar")
    api(b, 'SetEnabled("fps", true)')
    check(api(b, 'SetEnabled("gold", false)')[0] is True and placed(b) == ["fps"], "with a second one on, the first may go")

    # a save that has every switch off (or turned off by hand) still shows one
    b = full()
    b.run('for _, k in ipairs({"fps","mem","cpu","latency","rested","durability","bags","time","gold"}) do '
          '__cfg.settings["databar.seg." .. k] = false end')
    b.login()
    check(placed(b) == ["fps"] and abs(b.layout()[0]["w"] - SCREEN_W) < 1e-9,
          "every switch off in the save: the first segment in order shows", str(placed(b)))
    row = {r["key"]: r for r in model(b)}["fps"]
    check(row["on"] is True and row["lock"] == LOCK, "Model shows what the bar shows: FPS on and locked", str(row))


def test_settings_bad_saves() -> None:
    print("\n== settings: a hand edited save is read safely")
    b = full()
    b.run('__cfg.settings["databar.order"] = { "gold", "gold", "bogus", 7, "fps" }')
    b.login()
    check(placed(b) == ["gold", "fps", "latency", "rested", "durability", "bags", "time"],
          "repeats, unknown keys and non-text entries are dropped; the rest follow in default order", str(placed(b)))
    b = full()
    b.run('__cfg.settings["databar.order"] = "gold"; __cfg.settings["databar.seg.fps"] = "yes"; '
          '__cfg.settings["databar.title.fps"] = 123; __cfg.settings["databar.title.time"] = "ABCDEFGHIJKLMNO"')
    b.login()
    check(placed(b) == DEFAULT_SHOWN, "an order that is not a list is the default; a switch that is not a boolean is its default",
          str(placed(b)))
    check(b.seg("fps")["label"] == "FPS", "a title that is not text is the default label")
    check(b.seg("time")["label"] == "ABCDEFGHIJ", "a saved title longer than ten characters shows its first ten",
          b.seg("time")["label"])
    # no FS.Config at all: defaults, and the setters say so
    b = full(config=False)
    b.login()
    check(placed(b) == DEFAULT_SHOWN and model(b)[0]["title"] == "FPS", "without FS.Config the bar and the model use the defaults")
    check(api(b, 'SetEnabled("fps", false)')[0] is False and api(b, 'SetTitle("fps", "X")')[0] is False
          and api(b, 'SetOrder({"gold"})')[0] is False and placed(b) == DEFAULT_SHOWN,
          "and the setters refuse without changing anything")
    b = full()
    b.login()
    b.run("__cfgReadOnly = true")
    check(api(b, 'SetEnabled("fps", false)')[0] is False and api(b, 'SetTitle("fps", "X")')[0] is False
          and api(b, 'Move("gold", -1)')[0] is False and placed(b) == DEFAULT_SHOWN, "read only settings: every setter refuses")


def test_settings_titles() -> None:
    print("\n== settings: segment titles (default, custom, empty, at most 10 characters)")
    b = full()
    b.login()
    ok, clean = api(b, 'SetTitle("time", "CLOCK")')
    check(ok is True and clean == "CLOCK" and b.seg("time")["label"] == "CLOCK", "typing renames the title live",
          f"{ok} {clean} {b.seg('time')['label']}")
    check(stored(b, "databar.title.time") == "CLOCK", "stored per segment under databar.title.<seg>")
    row = {r["key"]: r for r in model(b)}["time"]
    check(row["title"] == "CLOCK" and row["label"] == "TIME" and row["titleIsDefault"] is False,
          "Model: the title is CLOCK, the label (the row's own name) stays TIME", str(row))
    check(b.seg("gold")["label"] == "GOLD", "other segments keep theirs")
    check(keys(b.layout()) == DEFAULT_SHOWN, "a rename does not move anything")

    ok, clean = api(b, 'SetTitle("time", "ABCDEFGHIJKLMN")')
    check(clean == "ABCDEFGHIJ" and b.seg("time")["label"] == "ABCDEFGHIJ", "at most ten characters", clean)
    ok, clean = api(b, 'SetTitle("time", "ééééééééééXYZ")')
    check(clean == "é" * 10, "ten characters means ten letters, an accented one counts once", clean)
    ok, clean = api(b, 'SetTitle("time", "|cffff0000HI|r")')
    check("|" not in clean and clean == "cffff0000H", "escape bars are stripped (then cut to ten)", clean)

    # empty: only the value, which moves up to PAD_X
    for key in ("fps", "bags", "gold"):                # a plain value, a meter, and the coins
        api(b, f'SetTitle("{key}", "")')
        seg = b.seg(key)
        check(seg["labelShown"] is False and seg["label"] == "", f"{key}: an empty title hides the label", str(seg))
        check(seg["firstPt"] == {"point": "LEFT", "rel": "segment", "relPoint": "LEFT", "x": 8, "y": 0},
              f"{key}: and the value starts at PAD_X in the segment", str(seg["firstPt"]))
    check(b.seg("fps").get("value") == "60", "the value is untouched")
    check(model(b)[0]["title"] == "" and model(b)[0]["titleIsDefault"] is False, "Model: empty is a title of its own")
    check(stored(b, "databar.title.fps") == "", "an empty title is stored as empty, not as nothing")
    api(b, 'SetTitle("fps", "   ")')
    check(b.seg("fps")["labelShown"] is False, "spaces only count as empty")
    ok, clean = api(b, 'SetTitle("fps", "FPS")')
    check(b.seg("fps")["labelShown"] is True and stored(b, "databar.title.fps") is None
          and b.seg("fps")["firstPt"]["rel"] == "label", "typing the default label back stores nothing and seats the title again",
          str(b.seg("fps")))
    check(api(b, "SetTitle(\"fps\", nil)")[0] is False and api(b, 'SetTitle("nope", "X")')[0] is False,
          "a title that is not text, or for an unknown segment, is refused")

    # a hidden segment keeps its title for when it comes back
    api(b, 'SetTitle("mem", "RAM")')
    check(b.seg("mem")["label"] == "RAM" and "mem" not in placed(b), "a hidden segment is retitled and stays off the bar")
    api(b, 'SetEnabled("mem", true)')
    check(b.seg("mem")["label"] == "RAM" and b.seg("mem")["labelShown"] is True, "and shows the new title when switched on")

    # saved titles apply at login
    b = full()
    b.run('__cfg.settings["databar.title.fps"] = "FRAMES"; __cfg.settings["databar.title.bags"] = ""')
    b.login()
    check(b.seg("fps")["label"] == "FRAMES" and b.seg("bags")["labelShown"] is False, "saved titles are on the bar at login")


def test_settings_title_clipped() -> None:
    print("\n== settings: a long title is clipped before the value, never over it")
    # four segments on a 450 wide bar: 112.5 each; a 10 character title is 65 wide in the mock (6.5 a letter)
    b = Bar(pre="UIParent.w = 450")
    b.login()
    room = 112.5 - 8 - 6 - 40 - 4                      # plain value segment: title room beside a 40 wide value
    api(b, 'SetTitle("fps", "WWWWWWWWWW")')
    seg = b.seg("fps")
    check(seg["labelShown"] is True and abs(seg["labelW"] - room) < 1e-9,
          "a title wider than the room is cut to the room", f"{seg['labelW']} want {room}")
    check(seg["firstPt"]["rel"] == "label", "the value stays anchored to the (clipped) label, so it cannot be overlapped")
    api(b, 'SetTitle("fps", "AB")')
    check(b.seg("fps")["labelW"] == 0, "a title that fits goes back to its natural width", str(b.seg("fps")["labelW"]))
    api(b, 'SetTitle("fps", "WWWWWWWWWW")')
    b.run("UIParent.w = 2560; for _, fn in ipairs(__rescale) do fn() end")
    check(b.seg("fps")["labelW"] == 0, "more room (a rescale): clip lifted")
    b.run("UIParent.w = 450; for _, fn in ipairs(__rescale) do fn() end")
    check(abs(b.seg("fps")["labelW"] - room) < 1e-9, "less room (a rescale): clipped again")

    # a meter has less room still: no room at all drops the title and the value moves up to PAD_X
    api(b, 'SetTitle("bags", "WW")')
    seg = b.seg("bags")
    check(seg["labelShown"] is False and seg["firstPt"]["rel"] == "segment",
          "no room beside the meter and its value: the typed title is dropped, the meter starts at PAD_X", str(seg))
    # but a default title is never touched, at any width (a bar at its defaults lays out as it always did)
    check(b.seg("time")["labelShown"] is True and b.seg("gold")["labelShown"] is True
          and b.seg("time")["labelW"] == 0 and b.seg("gold")["labelW"] == 0,
          "default titles are never clipped or dropped", str((b.seg("time"), b.seg("gold"))))
    api(b, 'SetTitle("bags", "BAGS")')
    check(b.seg("bags")["labelShown"] is True, "typing the default back brings it back at this width too")


def test_settings_link_slot() -> None:
    print("\n== settings: the STATUS slot keeps its rule (before TIME, or at the end without TIME)")
    b = full()
    b.run("__makeBridge(true)")
    b.login()
    check(keys(b.layout()) == ["fps", "latency", "rested", "durability", "bags", "link", "time", "gold"],
          "defaults: STATUS before TIME", str(keys(b.layout())))
    api(b, 'SetOrder({"time", "gold", "fps"})')
    check(keys(b.layout())[:2] == ["link", "time"], "TIME first: STATUS before it, at the left end", str(keys(b.layout())))
    api(b, 'SetOrder({"fps", "time", "gold"})')
    check(keys(b.layout())[:3] == ["fps", "link", "time"], "TIME second: STATUS between FPS and TIME", str(keys(b.layout())))
    api(b, 'SetEnabled("time", false)')
    lay = b.layout()
    check(keys(lay)[-1] == "link" and "time" not in keys(lay), "TIME off: STATUS goes to the end", str(keys(lay)))
    segs = [k for k in lay if k["key"] != "link"]
    check(all(abs(k["w"] - segs[0]["w"]) < 1e-9 for k in segs) and contiguous(lay),
          "the others share the remainder equally and the bar is full", str([(k["key"], round(k["w"], 1)) for k in lay]))
    api(b, 'SetEnabled("time", true)')
    check("link" in keys(b.layout()) and keys(b.layout()).index("link") == keys(b.layout()).index("time") - 1,
          "TIME back: STATUS before it again", str(keys(b.layout())))
    b.run("ForeverStatusStripFrame:Hide()")
    check("link" not in keys(b.layout()) and shares_equally(b.layout()), "strip hidden: no STATUS, equal shares again")


def test_settings_combat() -> None:
    print("\n== settings: in combat a layout change waits for regen (titles are text and apply)")
    b = full()
    b.login()
    b.run("ForeverSTUwaveDataBar.restricted = true")
    before = [(k["key"], k["x"], k["w"]) for k in b.layout()]
    b.run("__combat = true")
    api(b, 'SetEnabled("fps", false)')
    api(b, 'Move("gold", -1)')
    api(b, 'SetTitle("gold", "COIN")')
    check(b.rt.eval("#__blocked") == 0, "nothing restricted is touched in combat", str(list(b.rt.eval("__blocked").values())))
    check([(k["key"], k["x"], k["w"]) for k in b.layout()] == before, "the segments keep their seats until combat ends")
    check(b.seg("gold")["label"] == "COIN", "a retitle (text only) shows at once")
    b.run("__combat = false")
    b.rt.execute('__event("PLAYER_REGEN_ENABLED")')
    check(placed(b) == ["latency", "rested", "durability", "bags", "gold", "time"] and b.rt.eval("#__blocked") == 0,
          "regen replays both changes", str(placed(b)))
    check(shares_equally(b.layout()), "and the six share the width")


def test_settings_failed_segment() -> None:
    print("\n== settings: a segment whose read throws drops off the bar at the next layout")
    b = full("function GetNetStats() error('boom') end")
    b.run("print = function() end")      # the module says once that the segment failed
    b.login()
    lay_before = placed(b)
    check("latency" in lay_before, "MS still has its slot until the layout runs again", str(lay_before))
    b.run("for _, fn in ipairs(__rescale) do fn() end")
    check(placed(b) == [k for k in DEFAULT_SHOWN if k != "latency"] and shares_equally(b.layout()),
          "the next layout closes the gap and re-shares the width", str(placed(b)))
    row = {r["key"]: r for r in model(b)}["latency"]
    check(row["available"] is False and row["on"] is False and row["lock"], "Model shows it unavailable", str(row))
    check(api(b, 'SetEnabled("latency", true)')[0] is False, "and it cannot be switched on")


def test_settings_gold_record_off_bar() -> None:
    print("\n== settings: this character's gold is still recorded with GOLD off the bar")
    b = full(GOLD_PRE)
    b.login()
    tick(b)
    api(b, 'SetEnabled("gold", false)')
    b.run("__money = 777777")
    b.rt.execute('__event("PLAYER_MONEY")')
    row = b.rt.eval('ForeverSTUwaveDB.gold["Player-91-AAA"]')
    check(row is not None and row["copper"] == 777777, "PLAYER_MONEY records the new total", str(row))
    b.run("__money = 888888")
    tick(b)
    check(b.rt.eval('ForeverSTUwaveDB.gold["Player-91-AAA"].copper') == 777777, "a hidden segment is not read by the tick")
    api(b, 'SetEnabled("gold", true)')
    check(b.rt.eval('ForeverSTUwaveDB.gold["Player-91-AAA"].copper') == 888888, "back on the bar it is read at once")
    b.run("__money = 999999")
    b.rt.execute('__event("PLAYER_MONEY")')
    check(b.rt.eval('ForeverSTUwaveDB.gold["Player-91-AAA"].copper') == 888888,
          "on the bar, PLAYER_MONEY leaves the recording to the segment (no second path)")


# ---------------------------------------------------------------------------------------------------------------
# REP and PROF segments, click to open (E2)
# ---------------------------------------------------------------------------------------------------------------

REPPROF_PRE = """
FACTION_STANDING_LABEL4, FACTION_STANDING_LABEL5, FACTION_STANDING_LABEL8 = "Neutral", "Friendly", "Exalted"
__repCalls = 0
__watched = { name = "Thunder Bluff", factionID = 81, reaction = 4, currentReactionThreshold = 0,
              nextReactionThreshold = 3000, currentStanding = 1250 }
C_Reputation = { GetWatchedFactionData = function() __repCalls = __repCalls + 1; return __watched end }
-- GetProfessions answers slot numbers (nil where the character has none); GetProfessionInfo(slot) the details.
__profSlots = { 1, 2, 3, 4 }
__profInfo = { { "Blacksmithing", 142, 150, 164 }, { "Mining", 150, 150, 186 }, { "Cooking", 75, 150, 185 },
               { "First Aid", 40, 150, 129 } }
__profCalls = 0
function GetProfessions() __profCalls = __profCalls + 1; return __profSlots[1], __profSlots[2], __profSlots[3], __profSlots[4], __profSlots[5], __profSlots[6] end
function GetProfessionInfo(i) local p = __profInfo[i]; return p[1], "icon", p[2], p[3], 0, 0, p[4] end
"""

OPEN_PRE = """
__opened = {}
function ToggleCharacter(tab) __opened[#__opened + 1] = tab end
function ToggleCalendar() __opened[#__opened + 1] = "calendar" end
function ToggleProfessionsBook() __opened[#__opened + 1] = "professions" end
"""

ADD_LINE = "function GameTooltip:AddLine(t, r, g, bl) self.lines[#self.lines + 1] = { left = t, color = { r, g, bl } } end"
CLICK_TIPS = {
    "durability": " Click opens the character window.", "bags": " Click opens your bags.", "time": " Click opens the calendar.",
    "gold": " Click opens currencies.", "rep": " Click opens reputation.", "prof": " Click opens the profession book.",
}


def rep_pro(extra: str = "", **kw) -> Bar:
    """A bar with every API, REP and PROF switched on and the open calls defined; `extra` is more Lua before the load."""
    b = Bar(pre=FULL_PRE + REPPROF_PRE + OPEN_PRE + extra, **kw)
    b.run('__cfg.settings["databar.seg.rep"] = true; __cfg.settings["databar.seg.prof"] = true')
    return b


def meter_value(b: Bar, label: str):
    return b.rt.eval('function() local f = __segment("%s"); for _, c in ipairs(__frames) do '
                     'if c.kind == "StatusBar" and c.parent and c.parent.parent == f then return c.value end end end' % label)()


def value_of(b: Bar, label: str) -> str:
    return str(b.rt.eval(f'select(2, __segment("{label}")).text'))


def click(b: Bar, label: str, button: str = "LeftButton") -> None:
    b.run(f'local f = __segment("{label}"); f.scripts.OnMouseUp(f, "{button}")')


def test_rep_segment() -> None:
    print("\n== REP: the watched faction as a meter and its short name")
    b = rep_pro()
    b.login()
    check(placed(b)[-2:] == ["rep", "prof"] and len(placed(b)) == 9, "REP and PROF on (set in the save): last on the bar", str(placed(b)))
    check(value_of(b, "REP") == "Thunder", "the value is the faction's short name, whole words that fit in ten letters",
          value_of(b, "REP"))
    check(abs(meter_value(b, "REP") - 1250 / 3000) < 1e-9, "the meter is progress within the standing (1250 / 3000)",
          str(meter_value(b, "REP")))
    for name, want in (("Stormwind", "Stormwind"), ("Honor Hold", "Honor Hold"), ("Argent Dawn", "Argent"),
                       ("Bloodsail Buccaneers", "Bloodsail"), ("Gadgetzanwolfpack", "Gadgetzanw")):
        b.run(f'__watched.name = "{name}"')
        tick(b)
        check(value_of(b, "REP") == want, f"short name of {name}", value_of(b, "REP"))
    b.run('__watched = nil')
    tick(b)
    check(value_of(b, "REP") == "none" and meter_value(b, "REP") == 0, "nothing watched: the value reads none, the meter is empty")
    b.run('__watched = { name = "Orgrimmar", factionID = 76, reaction = 8, currentReactionThreshold = 42000, '
          'nextReactionThreshold = 42000, currentStanding = 42999 }')
    tick(b)
    check(meter_value(b, "REP") == 1 and value_of(b, "REP") == "Orgrimmar", "at the top standing the meter is full")
    b.run('__watched = { name = "Orgrimmar", factionID = 76, reaction = 4, currentReactionThreshold = 0, '
          'nextReactionThreshold = 3000, currentStanding = 99 }')      # 99 stands in for a secret number
    tick(b)
    check(meter_value(b, "REP") == 0 and value_of(b, "REP") == "Orgrimmar", "a secret standing shows an empty meter, no error")
    b.run('__watched = { name = "x", factionID = 0 }')
    tick(b)
    check(value_of(b, "REP") == "none", "a faction id of 0 is nothing watched")
    b.run('__watched = "junk"')
    tick(b)
    check(value_of(b, "REP") == "none" and b.seg("rep")["shown"] is True, "an answer that is not a table reads as nothing, nothing throws")

    # off by default: not on the bar, not read
    b = Bar(pre=FULL_PRE + REPPROF_PRE)
    b.login()
    tick(b)
    check("rep" not in placed(b) and b.rt.eval("__repCalls") == 0 and b.rt.eval("__profCalls") == 0,
          "REP and PROF are off until switched on, and are not read", str(placed(b)))
    api(b, 'SetEnabled("rep", true)')
    check(placed(b)[-1] == "rep" and value_of(b, "REP") == "Thunder", "switched on: read at once", str(placed(b)))
    check(stored(b, "databar.seg.rep") is True, "stored under databar.seg.rep")


def hover_lines(b: Bar, label: str) -> list[tuple]:
    hover(b, label)
    return lines(b)


def test_rep_tooltip() -> None:
    print("\n== REP tooltip: faction, standing, current / max")
    b = rep_pro(ADD_LINE)
    b.login()
    got = hover_lines(b, "REP")
    check(got[:3] == [("Thunder Bluff", None), ("Standing", "Neutral"), ("Progress", "1250 / 3000")],
          "header the faction, then its standing and progress", str(got))
    check(b.rt.eval("GameTooltip.anchor") == "ANCHOR_CURSOR" and b.rt.eval('GameTooltip.owner == (__segment("REP"))'),
          "at the mouse, owned by the segment")
    clears = b.rt.eval("GameTooltip.clears")
    tick(b)
    check(b.rt.eval("GameTooltip.clears") == clears, "a tick with nothing changed rewrites nothing")
    b.run("__watched.currentStanding = 1500")
    b.rt.execute('__event("UPDATE_FACTION")')
    check(lines(b)[2] == ("Progress", "1500 / 3000"), "a reputation gain while hovering updates the line", str(lines(b)))
    b.run('__watched = { name = "Orgrimmar", factionID = 76, reaction = 8, currentReactionThreshold = 42000, '
          'nextReactionThreshold = 42000, currentStanding = 42999 }')
    b.rt.execute('__event("UPDATE_FACTION")')
    check(lines(b) == [("Orgrimmar", None), ("Standing", "Exalted"), ("Progress", "Max")], "the top standing reads Max", str(lines(b)))
    b.run("__watched = nil")
    b.rt.execute('__event("UPDATE_FACTION")')
    check(lines(b) == [("Reputation", None), ("No faction is watched.", None)], "nothing watched says so", str(lines(b)))
    b.run('local f = __segment("REP"); f.scripts.OnLeave(f)')
    check(b.rt.eval("GameTooltip.shown") is False, "leave hides it")
    texts = " ".join(f"{l} {r or ''}" for l, r in got).lower()
    check(not any(w in texts for w in ("bot", "automat", "macro")), "client text stays neutral", texts)


def test_prof_segment_and_tooltip() -> None:
    print("\n== PROF: the two primary professions on the bar, every profession in the tooltip")
    b = rep_pro(ADD_LINE)
    b.login()
    check(value_of(b, "PROF") == "BS 142  MIN 150", "the bar reads BS 142  MIN 150", value_of(b, "PROF"))
    got = hover_lines(b, "PROF")
    check(got == [("Professions", None), ("Blacksmithing", "142 / 150"), ("Mining", "150 / 150"), ("Cooking", "75 / 150"),
                  ("First Aid", "40 / 150")], "the tooltip lists all of them with their max, primaries first", str(got))
    b.run("__profInfo[1][2] = 143")
    b.rt.execute('__event("SKILL_LINES_CHANGED")')
    check(value_of(b, "PROF") == "BS 143  MIN 150" and lines(b)[1] == ("Blacksmithing", "143 / 150"),
          "a skill up (SKILL_LINES_CHANGED) updates the bar and the open tooltip at once", f"{value_of(b, 'PROF')} {lines(b)}")
    b.run('__profSlots = { 1 }')
    tick(b)
    check(value_of(b, "PROF") == "BS 143", "one profession reads as one", value_of(b, "PROF"))
    b.run('__profSlots = {}')
    tick(b)
    check(value_of(b, "PROF") == "none", "none learned reads none", value_of(b, "PROF"))
    check(lines(b) == [("Professions", None), ("No professions learned.", None)], "and the tooltip says so", str(lines(b)))
    b.run('__profInfo = { { "Herbalism", 300, 300, 182 }, { "Zzzz Craft", 12, 75, 0 } }; __profSlots = { 1, 2 }')
    tick(b)
    check(value_of(b, "PROF") == "HERB 300  ZZZZ 12", "an unknown profession shows its first four letters", value_of(b, "PROF"))
    b.run('GetProfessionInfo = function() return "Mining", "icon", 98, 150 end; __profSlots = { 1 }')   # no skill line
    tick(b)
    check(value_of(b, "PROF") == "MIN 98", "the name stands in when the skill line is missing", value_of(b, "PROF"))
    b.run('GetProfessionInfo = function() return "Mining", "icon", 98, nil end')
    tick(b)
    hover(b, "PROF")
    check(lines(b)[1] == ("Mining", "98"), "a missing max shows the skill alone", str(lines(b)))
    b.run('GetProfessionInfo = function() return "Mining", "icon", 99, 150 end')       # 99 is the mock's secret number
    tick(b)
    check(value_of(b, "PROF") == "none" and b.seg("prof")["shown"] is True, "a secret skill reads as nothing, no throw",
          value_of(b, "PROF"))


def test_event_refresh() -> None:
    print("\n== REP and PROF: refreshed on their events only while on the bar")
    b = Bar(pre=FULL_PRE + REPPROF_PRE + OPEN_PRE)
    b.login()                                    # REP and PROF are off
    check(b.rt.eval("__repCalls") == 0 and b.rt.eval("__profCalls") == 0, "off: nothing read at login")
    b.rt.execute('__event("UPDATE_FACTION")')
    b.rt.execute('__event("SKILL_LINES_CHANGED")')
    check(b.rt.eval("__repCalls") == 0 and b.rt.eval("__profCalls") == 0, "off: the events read nothing")
    registered = b.rt.eval("function() local out = {} for _, f in ipairs(__frames) do if f.events then "
                           "for e in pairs(f.events) do out[#out + 1] = e end end end return out end")()
    registered = [str(v) for v in registered.values()]
    check("UPDATE_FACTION" in registered and "SKILL_LINES_CHANGED" in registered, "both events are registered", str(registered))
    api(b, 'SetEnabled("rep", true)')
    n = b.rt.eval("__repCalls")
    b.run("__watched.currentStanding = 2000")
    b.rt.execute('__event("UPDATE_FACTION")')
    check(b.rt.eval("__repCalls") == n + 1 and abs(meter_value(b, "REP") - 2000 / 3000) < 1e-9,
          "on: UPDATE_FACTION reads it once and moves the meter", f"{n} -> {b.rt.eval('__repCalls')}")
    check(b.rt.eval("__profCalls") == 0, "and does not read PROF")
    # a client that refuses the event names: the bar still loads
    b = Bar(pre=FULL_PRE + REPPROF_PRE + "local real = __FS.FrameHelpers; __FS.FrameHelpers = { RegisterEvent = function() return false end }")
    b.login()
    check(placed(b) == DEFAULT_SHOWN, "a refused event name is skipped and the bar loads as usual")


def test_click_opens() -> None:
    print("\n== click: DUR, TIME, GOLD, REP and PROF open their window out of combat")
    b = rep_pro(ADD_LINE)
    b.login()
    for label, want in (("DUR", "PaperDollFrame"), ("TIME", "calendar"), ("GOLD", "TokenFrame"), ("REP", "ReputationFrame"),
                        ("PROF", "professions")):
        b.run("__opened = {}")
        click(b, label)
        got = [str(v) for v in b.rt.eval("__opened").values()]
        check(got == [want], f"{label}: a left click calls {want}", str(got))
        b.run("__opened = {}")
        click(b, label, "RightButton")
        check(len(b.rt.eval("__opened")) == 0, f"{label}: a right click does nothing")
    check(b.rt.eval('(__segment("FPS")).scripts == nil'), "FPS stays click-through, no scripts")
    rows = {r["key"]: r for r in model(b)}
    check(all(rows[k]["tip"] == TIPS[k] + CLICK_TIPS[k] for k in ("durability", "time", "gold", "rep", "prof")),
          "the row tips end with the click sentence", str({k: rows[k]["tip"] for k in ("durability", "time", "gold", "rep", "prof")}))
    check(rows["bags"]["tip"] == TIPS["bags"], "BAGS has no click sentence while there is no stock backpack button")

    # a toggle that throws, or is missing, is harmless
    b.run('function ToggleCalendar() error("nope") end')
    try:
        click(b, "TIME")
        ok = True
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"    raised {exc}")
    check(ok, "a toggle that throws never throws out of the click")
    b = rep_pro("ToggleCalendar = nil; ToggleCharacter = nil")
    b.login()
    for label in ("TIME", "DUR", "GOLD", "REP"):
        click(b, label)
    check(len(b.rt.eval("__opened")) == 0, "a client without the toggles: the click does nothing")
    rows = {r["key"]: r for r in model(b)}
    check(all(rows[k]["tip"] == TIPS[k] for k in ("durability", "time", "gold", "rep")),
          "and the row tips drop the click sentence", str({k: rows[k]["tip"] for k in ("durability", "time", "gold", "rep")}))
    b = rep_pro("ToggleProfessionsBook = nil; BOOKTYPE_PROFESSION = 7; function ToggleSpellBook(t) __opened[#__opened + 1] = 'book' .. t end")
    b.login()
    click(b, "PROF")
    check([str(v) for v in b.rt.eval("__opened").values()] == ["book7"], "no professions book: the spell book's profession page")


def test_click_in_combat() -> None:
    print("\n== click in combat: nothing opens, the tooltip says when")
    b = rep_pro(ADD_LINE)
    b.login()
    b.run("__combat = true")
    for label in ("DUR", "TIME", "GOLD", "REP", "PROF"):
        click(b, label)
    check(len(b.rt.eval("__opened")) == 0, "no window is opened in combat")
    for label, head in (("TIME", "Time"), ("DUR", "Durability"), ("GOLD", "Gold"), ("REP", "Thunder Bluff"), ("PROF", "Professions")):
        got = hover_lines(b, label)
        check(got[0][0] == head and got[-1] == ("Opens after combat.", None), f"{label}: the tooltip's last line says it opens after combat",
              str(got))
    # leaving combat while the mouse stays on it: the next tick drops the line and the click works
    hover(b, "TIME")
    b.run("__combat = false")
    tick(b)
    check(all(l[0] != "Opens after combat." for l in lines(b)), "combat over: the line goes at the next tick", str(lines(b)))
    click(b, "TIME")
    check([str(v) for v in b.rt.eval("__opened").values()] == ["calendar"], "and the click opens it")
    # no AddLine on the tooltip (an old client): no throw
    b = rep_pro()
    b.login()
    b.run("__combat = true")
    try:
        hover(b, "TIME")
        ok = True
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"    raised {exc}")
    check(ok, "a tooltip without AddLine takes no note and throws nothing")


def test_bags_secure_click() -> None:
    print("\n== BAGS: the click is a secure delegate to the stock backpack button, never an addon call")
    stock = 'MainMenuBarBackpackButton = { Click = function() end }'
    b = Bar(pre=stock + "\nfunction ToggleAllBags() __opened = (__opened or 0) + 1 end")
    b.login()
    btn = b.rt.eval('function() for _, f in ipairs(__frames) do if f.kind == "Button" then return f end end end')()
    check(btn is not None, "a secure button is laid over the BAGS segment")
    attrs = b.rt.eval('function() for _, f in ipairs(__frames) do if f.kind == "Button" then return f.attrs end end end')()
    check(attrs["type"] == "click" and attrs["useOnKeyDown"] is False
          and b.rt.eval('function() for _, f in ipairs(__frames) do if f.kind == "Button" then return f.attrs.clickbutton == MainMenuBarBackpackButton end end end')(),
          "type click, clickbutton the stock backpack button, up clicks", str(dict(attrs)))
    check(b.rt.eval('function() for _, f in ipairs(__frames) do if f.kind == "Button" then return f.parent == (__segment("BAGS")) end end end')(),
          "it is a child of the BAGS segment")
    check(b.rt.eval('(__segment("BAGS")).scripts == nil') and b.rt.eval("__opened") is None,
          "the segment itself keeps no script and no addon call opens a bag")
    check({r["key"]: r for r in model(b)}["bags"]["tip"] == TIPS["bags"] + CLICK_TIPS["bags"], "the row tip carries the click sentence")

    # no stock button: no overlay, no sentence
    b = Bar()
    b.login()
    check(b.rt.eval('function() for _, f in ipairs(__frames) do if f.kind == "Button" then return true end end return false end')() is False,
          "without the stock button there is no overlay")

    # login in combat: SetAttribute is protected, so the overlay is bound once combat ends
    b = Bar(pre=stock + "\n__combat = true")
    b.login()
    bound = b.rt.eval('function() for _, f in ipairs(__frames) do if f.kind == "Button" and f.attrs then return true end end return false end')()
    check(bound is False, "in combat nothing is bound")
    b.run("__combat = false")
    b.rt.execute('__event("PLAYER_REGEN_ENABLED")')
    check(b.rt.eval('function() for _, f in ipairs(__frames) do if f.kind == "Button" and f.attrs and f.attrs.type == "click" then return true end end return false end')(),
          "PLAYER_REGEN_ENABLED binds it")
    b.run("local n = 0; for _, f in ipairs(__frames) do if f.kind == 'Button' then n = n + 1 end end; __buttons = n")
    b.rt.execute('__event("PLAYER_ENTERING_WORLD")')
    b.run("local n = 0; for _, f in ipairs(__frames) do if f.kind == 'Button' then n = n + 1 end end; __buttons2 = n")
    check(b.rt.eval("__buttons") == 1 and b.rt.eval("__buttons2") == 1, "binding again makes no second overlay")


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
    test_gold_tooltip()
    test_settings_defaults()
    test_settings_model()
    test_settings_order_live()
    test_settings_visibility_live()
    test_settings_last_segment_stays()
    test_settings_bad_saves()
    test_settings_titles()
    test_settings_title_clipped()
    test_settings_link_slot()
    test_settings_combat()
    test_settings_failed_segment()
    test_settings_gold_record_off_bar()
    test_rep_segment()
    test_rep_tooltip()
    test_prof_segment_and_tooltip()
    test_event_refresh()
    test_click_opens()
    test_click_in_combat()
    test_bags_secure_click()
    print(f"\n{CHECKS} checks, {len(FAILURES)} failed")
    for f in FAILURES:
        print(f"  - {f}")
    return min(len(FAILURES), 255)


if __name__ == "__main__":
    sys.exit(main())
