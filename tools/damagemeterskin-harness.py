#!/usr/bin/env python3
"""Runs the real Modules/Skins/DamageMeter.lua headless against a mock of Blizzard's built-in damage meter.

The meter's values are secret in combat and Blizzard's own code handles them, so the skin must stay out of Blizzard's
state: every Blizzard object in the mock is a proxy that throws on any new field write, and SetScript throws. Pinned:

  * a session window gets the panel chrome on its body, Blizzard's background becomes the nine sliced fill (still
    Blizzard's region, so the opacity setting drives it), the header bar art goes, a band and rule replace it;
  * header text and entry names and numbers get the mono font;
  * a row becomes the XP bar's gauge: name and number on top, an 10 physical px gauge below it whose flat fill carries
    the class ramp (found from the RAID_CLASS_COLORS object Blizzard hands SetStatusBarColor) under a repeating cell
    tile, one texel per physical pixel; the player's own name is pink;
  * Blizzard's UpdateStyle (re-anchor, re-atlas) and SetStatusBarColor are followed;
  * the gold header art is held invisible: STUwave keys on the session and settings dropdowns, a minus or plus plate
    on the minimize button that follows SetMinimized;
  * rows built later are skinned through the SetupEntry hook, the source window's through its Refresh hook;
  * windows made after load are skinned through DamageMeter:SetupSessionWindow;
  * nothing is skinned twice, and no field is written on any Blizzard object.

    python3 tools/damagemeterskin-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

SRC = (Path(__file__).resolve().parent.parent / "forever-stuwave/Modules/Skins/DamageMeter.lua").read_text(encoding="utf-8")

MOCK = r"""
__writes = {}
local function Region(kind)
    local r = { kind = kind, alpha = 1, shown = true, points = 0 }
    function r:SetTexture(t, h, v, f) self.tex = t; self.wrap = h end
    function r:SetAtlas(a) self.tex = "atlas:" .. a end
    function r:SetColorTexture(cr, cg, cb, ca) self.tex = "color"; self.color = { cr, cg, cb, ca } end
    function r:SetVertexColor(cr, cg, cb, ca) self.vc = { cr, cg, cb, ca }; self.grad = nil end
    function r:GetVertexColor() local v = self.vc or { 1, 1, 1, 1 }; return v[1], v[2], v[3], v[4] end
    function r:SetGradient(o, a, b) self.grad = { o, a, b } end
    function r:SetTexCoord(...) self.tc = { ... } end
    function r:SetAlpha(a) self.alpha = a end
    function r:SetPoint(...) self.points = self.points + 1; self.lastPoint = { ... } end
    function r:ClearAllPoints() self.points = 0 end
    function r:SetAllPoints() self.points = 2 end
    function r:SetHeight(h) self.h = h end
    function r:SetWidth(w) self.w = w end
    function r:SetSize(w, h) self.w, self.h = w, h end
    function r:Hide() self.shown = false end
    function r:Show() self.shown = true end
    function r:SetBlendMode() end
    function r:SetSnapToPixelGrid() end
    function r:SetTexelSnappingBias() end
    function r:SetTextureSliceMargins() end
    function r:SetTextureSliceMode() end
    function r:SetFont(path, size, flags) self.font = path; self.size = size end
    function r:SetTextColor(cr, cg, cb) self.textColor = { cr, cg, cb } end
    return r
end
-- A Blizzard frame: holds its children by key; any NEW key written from outside is recorded as a taint write.
local function Blizzard(name, fields)
    local raw = fields or {}
    raw.made = {}
    raw.scripts = {}
    raw.points = 0
    function raw:CreateTexture() local t = Region("texture"); self.made[#self.made + 1] = t; return t end
    function raw:SetScript() error("SetScript on a Blizzard frame") end
    function raw:HookScript(s, fn) self.scripts[s] = fn end
    function raw:SetPoint() raw.points = raw.points + 1 end
    function raw:ClearAllPoints() raw.points = 0 end
    function raw:SetHeight(h) raw.h = h end
    function raw:GetWidth() return 200 end
    function raw:GetFrameLevel() return 3 end
    return setmetatable({}, {
        __index = raw,
        __newindex = function(_, k, v)
            if type(v) == "function" and __hooking then rawset(raw, k, v) return end
            __writes[#__writes + 1] = name .. "." .. tostring(k); raw[k] = v
        end,
    })
end
function hooksecurefunc(obj, name, fn)
    local orig = obj[name]
    __hooking = true
    obj[name] = function(...) local r = { orig(...) }; fn(...); return unpack(r) end
    __hooking = false
    __hooks = (__hooks or 0) + 1
end
function CreateColor(r, g, b, a) return { r, g, b, a } end
local function Color(r, g, b) return { r = r, g = g, b = b, GetRGB = function(self) return self.r, self.g, self.b end } end
RAID_CLASS_COLORS = { SHAMAN = Color(0, 0.44, 0.87), WARRIOR = Color(0.78, 0.61, 0.43) }
CREATURE_COLOR = Color(0.5, 0.5, 0.5)
function MakeEntry(name, isMe)
    local fillTex = Region("bar"); fillTex.vc = { 0.0, 0.44, 0.87, 1 }
    local bar = Blizzard(name .. ".StatusBar", {
        Background = Region("bg"), BackgroundEdge = Region("edge"), Name = Region("font"), Value = Region("font"),
    })
    local rawbar = getmetatable(bar).__index
    function rawbar:SetStatusBarTexture(t) fillTex.tex = t end
    function rawbar:GetStatusBarTexture() return fillTex end
    local icon = Blizzard(name .. ".Icon", {})
    local e = Blizzard(name, { StatusBar = bar, Icon = icon, statusBarColor = RAID_CLASS_COLORS.SHAMAN, isLocalPlayer = isMe })
    local rawe = getmetatable(e).__index
    rawe.fill = fillTex
    function rawe:UpdateStyle() self.StatusBar.Background:SetAtlas("ui-damagemeters-bar-shadowbg"); self.StatusBar:ClearAllPoints() end
    function rawe:SetStyle() self:UpdateStyle() end
    function rawe:GetIconAttachmentAnchor() return "LEFT", self.Icon, "RIGHT", 0, 0 end
    function rawe:SetStatusBarColor(c) self.StatusBar:GetStatusBarTexture():SetVertexColor(c:GetRGB()) end
    return e
end
function MakeWindow(name, nEntries)
    local list = {}
    for i = 1, nEntries do list[i] = MakeEntry(name .. ".Entry" .. i, i == 2) end
    local source = Blizzard(name .. ".SourceWindow", { Background = Region("bg"), list = {} })
    local rs = getmetatable(source).__index
    function rs:ForEachEntryFrame(fn) for _, e in ipairs(self.list) do fn(e) end end
    function rs:Refresh() end
    local container = Blizzard(name .. ".MinimizeContainer", {
        Background = Region("bg"), NotActive = Region("font"), LocalPlayerEntry = MakeEntry(name .. ".Local", true),
        SourceWindow = source,
    })
    local w = Blizzard(name, {
        Header = Region("header"), SessionTimer = Region("font"), MinimizeContainer = container,
        DamageMeterTypeDropdown = Blizzard(name .. ".Type", { TypeName = Region("font"), Arrow = Region("arrow") }),
        SessionDropdown = Blizzard(name .. ".Session", { SessionName = Region("font"), Background = Region("sbg"), Arrow = Region("sarrow") }),
        SettingsDropdown = Blizzard(name .. ".Settings", { Icon = Region("gear") }),
        MinimizeButton = Blizzard(name .. ".Minimize", {}),
        list = list,
    })
    local rw = getmetatable(w).__index
    function rw:ForEachEntryFrame(fn) for _, e in ipairs(self.list) do fn(e) end end
    function rw:SetupEntry() end
    function rw:IsMinimized() return false end
    function rw:SetMinimized(m) end
    return w
end
DamageMeterSessionWindow1 = MakeWindow("W1", 2)
local rawowner = {}
function rawowner:SetupSessionWindow(index, data) end
DamageMeter = rawowner
watcher = nil
function CreateFrame()
    local f = { points = 0 }
    function f:RegisterEvent() end
    function f:SetScript(_, fn) self.fn = fn end
    function f:SetSize() end
    function f:SetPoint() end
    function f:SetAllPoints() end
    function f:EnableMouse() end
    function f:SetFrameLevel() end
    function f:GetFrameLevel() return 1 end
    function f:CreateTexture() return setmetatable({}, { __index = function() return function() end end }) end
    watcher = f
    return f
end
__chrome = 0
__held = {}
__glyph = {}
FS = {
    IsSecret = function() return false end,
    FrameHelpers = { PixelsPerUnit = function() return 1.25 end },
    HeldArt = { Hold = function(r) r:SetAlpha(0); __held[#__held + 1] = r end },
    ButtonSkins = {
        SkinCloseButton = function(b, o) __glyph[b] = o.glyph end,
        SetGlyph = function(b, k) __glyph[b] = k end,
    },
    Theme = {
        FONT_MONO = "MONO", FLAT_TEXTURE = "FLAT", SLICE_FILL_TEXTURE = "SLICE_FILL", SLICE_MARGIN = 6,
        COLOR_POWER = { 0.13, 0.88, 1 }, COLOR_BG = { 0.05, 0.02, 0.12 }, COLOR_BAR_BORDER = { 0.23, 0.13, 0.41 },
        COLOR_MUTED = { 0.6, 0.57, 0.77 }, COLOR_TEXT_WHITE = { 1, 1, 1, 1 }, COLOR_BORDER = { 0.66, 0.33, 0.97 },
        COLOR_HEALTH = { 1, 0.18, 0.59 }, COLOR_AMBER = { 1, 0.71, 0.28 }, COLOR_BUTTON_INK = { 0.09, 0.05, 0.17 },
        ApplyNineSlice = function(t) t.sliced = true end,
        PanelBandInset = function() return 3 end,
        AddPanelChrome = function(frame) __chrome = __chrome + 1; return frame:CreateTexture(), frame:CreateTexture(), frame:CreateTexture() end,
        AddCutSliceFill = function() return {} end,
        SkinButton = function() __keys = (__keys or 0) + 1; return { border = { ring = Region("ring") } } end,
    },
}
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("a_window_wears_the_panel_and_header_band", """
    local w = DamageMeterSessionWindow1
    local c = w.MinimizeContainer
    assert(c.Background.tex == "SLICE_FILL" and c.Background.sliced, "background is not the nine sliced fill")
    assert(c.Background.vc[1] == 0.05, "fill not tinted COLOR_BG")
    assert(__chrome == 2, "body and source window chrome: " .. __chrome)
    assert(w.Header.alpha == 0, "Blizzard header art still showing")
    assert(#w.made == 2, "band and rule on the window")
    assert(w.SessionTimer.font == "MONO" and w.DamageMeterTypeDropdown.TypeName.font == "MONO"
        and w.SessionDropdown.SessionName.font == "MONO" and c.NotActive.font == "MONO", "header text not mono")
    assert(w.DamageMeterTypeDropdown.TypeName.textColor[1] == 0.13, "meter type not cyan")
""")

case("rows_are_xp_gauges_in_their_class_ramp", """
    local e = DamageMeterSessionWindow1.list[1]
    local bar = e.StatusBar
    assert(e.fill.tex == "FLAT", "bar fill not flat")
    local g = e.fill.grad
    assert(g and g[1] == "HORIZONTAL", "no class gradient on the fill")
    local ramp = FS.DamageMeterSkin.RAMPS.SHAMAN
    assert(g[2][1] == ramp[1][1] and g[3][3] == ramp[2][3], "shaman row not on the shaman ramp")
    assert(bar.Background.color and math.abs(bar.Background.color[1] - 0.086) < 1e-6, "track not the XP bar's unlit cell")
    assert(bar.BackgroundEdge.color[4] == 0, "shadow edge not cleared")
    assert(math.abs(bar.h - 10 / 1.25) < 1e-6, "gauge not 10 physical px tall")
    local cells
    for _, t in ipairs(bar.made) do if t.tex and tostring(t.tex):find("dm_cell_tile") then cells = t end end
    assert(cells and cells.wrap == "REPEAT", "no repeating cell tile")
    assert(cells.tc and cells.tc[2] == 200 * 1.25 / 16 and cells.tc[4] == 10 / 16, "cell tile not one texel per physical pixel")
    assert(bar.Name.font == "MONO" and bar.Value.font == "MONO", "row text not mono")
    assert(bar.Name.textColor[1] == 1 and bar.Name.textColor[2] == 1, "another player's name not white")
    local me = DamageMeterSessionWindow1.list[2]
    assert(me.StatusBar.Name.textColor[2] == 0.18, "own name not pink")
    assert(DamageMeterSessionWindow1.MinimizeContainer.LocalPlayerEntry.fill.grad, "pinned local row not skinned")
""")

case("blizzard_restyles_and_recolours_are_followed", """
    local e = DamageMeterSessionWindow1.list[1]
    e:SetStyle()
    assert(e.StatusBar.Background.tex == "color", "UpdateStyle re-atlas not followed")
    assert(e.StatusBar.points == 2, "gauge layout not re-applied after UpdateStyle")
    e:SetStatusBarColor(RAID_CLASS_COLORS.WARRIOR)
    local ramp = FS.DamageMeterSkin.RAMPS.WARRIOR
    assert(e.fill.grad and e.fill.grad[3][1] == ramp[2][1], "recolour not re-ramped")
    e:SetStatusBarColor(CREATURE_COLOR)
    assert(e.fill.grad and e.fill.grad[3][1] > 0.5, "a non class colour gets no ramp")
""")

case("header_buttons_become_stuwave_keys", """
    local w = DamageMeterSessionWindow1
    assert(w.DamageMeterTypeDropdown.Arrow.alpha == 0 and w.SessionDropdown.Background.alpha == 0
        and w.SessionDropdown.Arrow.alpha == 0 and w.SettingsDropdown.Icon.alpha == 0, "gold Blizzard art still showing")
    assert(__keys == 2, "session and settings keys: " .. tostring(__keys))
    assert(__glyph[w.MinimizeButton] == "minus", "minimize not a minus key")
    w:SetMinimized(true)
    assert(__glyph[w.MinimizeButton] == "plus", "minimized window not a plus key")
""")

case("later_rows_windows_and_source_rows_are_skinned", """
    local w = DamageMeterSessionWindow1
    local late = MakeEntry("Late")
    w:SetupEntry(late)
    assert(late.fill.grad, "a row set up later is not skinned")
    local src = w.MinimizeContainer.SourceWindow
    local spell = MakeEntry("Spell"); src.list[1] = spell
    src:Refresh()
    assert(spell.fill.grad, "source window rows not skinned on refresh")
    local w2 = MakeWindow("W2", 1)
    DamageMeter:SetupSessionWindow(2, { sessionWindow = w2 })
    assert(w2.list[1].fill.grad and w2.Header.alpha == 0, "a window made later is not skinned")
""")

case("nothing_twice_and_no_blizzard_field_written", """
    local w = DamageMeterSessionWindow1
    local hooks, chrome = __hooks, __chrome
    watcher.fn(watcher, "PLAYER_LOGIN")
    w:SetupEntry(w.list[1])
    assert(__hooks == hooks and __chrome == chrome, "skinned twice")
    assert(#__writes == 0, "wrote Blizzard fields: " .. table.concat(__writes, ", "))
""")


def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    try:
        rt.execute(MOCK)
        rt.globals().SRC = SRC
        rt.execute('assert(loadstring(SRC, "@DamageMeter.lua"))("forever-stuwave", FS)')
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


def main() -> int:
    failures = 0
    for name, body in CASES:
        err = run_case(body)
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}: {err}")
    print(f"{len(CASES) - failures}/{len(CASES)} checks passed")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
