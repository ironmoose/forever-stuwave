#!/usr/bin/env python3
"""Runs the real Modules/Skins/DamageMeter.lua headless against a mock of Blizzard's built-in damage meter.

The meter's values are secret in combat and Blizzard's own code handles them, so the skin must stay out of Blizzard's
state: every Blizzard object in the mock is a proxy that throws on any new field write, and SetScript throws. Pinned:

  * a session window gets the chat terminal's body (panel chrome, inner wash, scanlines kept out of the cut corners) and
    its term bar (a wash stepped in along the top-left chamfer, a rule under it); Blizzard's header art goes;
  * header text and entry names and numbers get the mono font;
  * rows default to neon plates: a class ramp fill (found from the RAID_CLASS_COLORS object Blizzard hands
    SetStatusBarColor) in an ink well with a rim, gloss and bloom, the icon as tall as the plate, the player's own rim pink;
  * the ladder style (the setting, switched live) lays the text on a top line and the XP bar's pips under it, a
    repeating gap tile one texel per physical pixel, the pip height from the row, a pink rail on the player's row;
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
    function r:GetHeight() return self.h or 32 end
    function r:GetStringHeight() return 11 end
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
    function raw:SetSize(w, h) raw.w, raw.h = w, h end
    function raw:GetHeight() return raw.rowH or 20 end
    function raw:IsShown() return true end
    function raw:GetRegions() return unpack(raw.made) end
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
__cfg, __cfgcb = {}, {}
FS = {
    IsSecret = function() return false end,
    Config = {
        RegisterDefault = function(k, v) __cfgdefault = v end,
        Get = function(k) return __cfg[k] end,
        Set = function(k, v) __cfg[k] = v; for _, f in ipairs(__cfgcb[k] or {}) do f() end end,
        OnChange = function(k, f) __cfgcb[k] = __cfgcb[k] or {}; table.insert(__cfgcb[k], f) end,
    },
    FrameHelpers = { PixelsPerUnit = function() return 1.25 end },
    HeldArt = { Hold = function(r) r:SetAlpha(0); __held[#__held + 1] = r end,
                HoldButton = function(b) __heldButtons = (__heldButtons or 0) + 1 end },
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
        SnapCut = function() return 6 end,
        FILL_CUT_TEXTURES = { [6] = "fill_cut_c6" },
        AddPanelChrome = function(frame) __chrome = __chrome + 1; return frame:CreateTexture(), frame:CreateTexture(), frame:CreateTexture() end,
        AddCutSliceFill = function() return {} end,
        AddRoundedFill = function(frame) __wash = (__wash or 0) + 1 end,
        SkinButton = function() __keys = (__keys or 0) + 1; return { border = { ring = Region("ring") } } end,
    },
}
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("a_window_wears_the_chat_terminal_inside_its_cut_corners", """
    local w = DamageMeterSessionWindow1
    local c = w.MinimizeContainer
    assert(c.Background.alpha == 0, "Blizzard's background not held: the body is the chat terminal's fill")
    assert(__chrome == 2, "body and source window chrome: " .. __chrome)
    assert(__wash == 1, "the chat terminal's inner wash on the body")
    local scans = {}
    for _, t in ipairs(c.made) do if t.tex and tostring(t.tex):find("scanline") then scans[#scans + 1] = t end end
    assert(#scans == 3 and scans[1].alpha == 0.4, "scanlines not three pieces clear of the cut corners")
    assert(scans[1].h == 6 and scans[3].h == 6, "the corner runs are one chamfer tall")
    assert(scans[2].tc[3] == 6 / 4 and scans[3].tc[3] == (20 - 6) / 4, "scanline pieces do not share one 4 px grid")
    assert(w.Header.alpha == 0, "Blizzard header art still showing")
    assert(#w.made == 4, "term bar: corner, run, band and rule: " .. #w.made)
    local corner, run, band, rule = w.made[1], w.made[2], w.made[3], w.made[4]
    assert(corner.tex == "fill_cut_c6" and corner.w == 6 and corner.tc[2] == 6 / 16, "no cut triangle in the top-left")
    assert(math.abs(corner.vc[4] - 0.08) < 1e-6 and math.abs(run.color[4] - 0.08) < 1e-6, "corner and run not the chat wash")
    assert(run.h == 6 and band.h == 31 - 6, "wash does not fill the header: " .. tostring(band.h))
    assert(rule.h == 1 and math.abs(rule.color[4] - 0.30) < 1e-6, "no term bar rule")
    assert(w.SessionTimer.font == "MONO" and w.DamageMeterTypeDropdown.TypeName.font == "MONO"
        and w.SessionDropdown.SessionName.font == "MONO" and c.NotActive.font == "MONO", "header text not mono")
    assert(w.DamageMeterTypeDropdown.TypeName.textColor[1] == 0.13, "meter type not cyan")
""")

case("rows_default_to_neon_plates", """
    assert(__cfgdefault == "plates", "plates is not the default")
    local e = DamageMeterSessionWindow1.list[1]
    local bar = e.StatusBar
    assert(e.fill.tex == "FLAT", "bar fill not flat")
    local g = e.fill.grad
    assert(g and g[1] == "VERTICAL", "fill not one vertical gradient")
    local ramp = FS.DamageMeterSkin.RAMPS.SHAMAN
    assert(g[2][1] == ramp[1][1] and g[3][3] == ramp[2][3], "shaman row not on the shaman ramp")
    assert(bar.Background.color and math.abs(bar.Background.color[1] - 0.039) < 1e-3, "plate well not ink")
    assert(bar.BackgroundEdge.color[4] == 0, "shadow edge not cleared")
    assert(e.Icon.w == 18 and e.Icon.h == 18, "icon not as tall as the plate in a 20 unit row: " .. tostring(e.Icon.w))
    assert(bar.points == 2, "plate not laid out")
    local cells, rims, gloss = nil, 0, nil
    for _, t in ipairs(bar.made) do
        if t.tex and tostring(t.tex):find("dm_cell_tile") then cells = t end
        if t.tex == "color" and t.shown and t.h and math.abs(t.h - 1 / 1.25) < 1e-6 and t.color[4] < 1 then gloss = t end
    end
    assert(cells and not cells.shown, "the ladder's gap tile shows on a plate")
    assert(gloss and math.abs(gloss.color[4] - 0.45) < 1e-6, "no one px gloss on the fill")
    assert(bar.Name.font == "MONO" and bar.Value.font == "MONO", "row text not mono")
    assert(bar.Name.textColor[1] == 1 and bar.Name.textColor[2] == 1, "another player's name not white")
    local me = DamageMeterSessionWindow1.list[2]
    assert(math.abs(me.StatusBar.Name.textColor[2] - 0.816) < 1e-3, "own name not the light pink on its plate")
    local pinkRim = 0
    for _, t in ipairs(me.StatusBar.made) do if t.tex == "color" and t.color[2] == 0.18 and t.shown then pinkRim = pinkRim + 1 end end
    assert(pinkRim == 4, "own plate rim not pink: " .. pinkRim)
    assert(DamageMeterSessionWindow1.MinimizeContainer.LocalPlayerEntry.fill.grad, "pinned local row not skinned")
""")

case("the_ladder_is_the_xp_bar_gauge_and_switches_live", """
    FS.Config.Set("skins.damageMeterRows", "ladder")
    assert(FS.DamageMeterSkin.Style() == "ladder", "style not switched")
    local e = DamageMeterSessionWindow1.list[1]
    local bar = e.StatusBar
    local cells, rims = nil, 0
    for _, t in ipairs(bar.made) do
        if t.tex and tostring(t.tex):find("dm_cell_tile") then cells = t end
        if t.tex == "color" and t.shown and t.color[4] == 1 then rims = rims + 1 end
    end
    assert(cells and cells.shown and cells.wrap == "REPEAT", "no repeating gap tile in the ladder")
    assert(rims == 0, "plate rim still showing in the ladder")
    assert(bar.Background.grad and bar.Background.grad[1] == "VERTICAL", "unlit pips not the slot gradient")
    assert(e.Icon.w == 14, "ladder icon not on the top line")
    assert(math.abs(bar.h - 4 / 1.25) < 1e-6, "a 20 unit row: pips at the 4 px floor: " .. tostring(bar.h * 1.25))
    getmetatable(e).__index.rowH = 30
    e:SetStyle()
    assert(math.abs(bar.h - 10 / 1.25) < 1e-6, "a tall row: pips capped at 10 px")
    assert(cells.tc and cells.tc[2] == 200 * 1.25 / 16 and cells.tc[3] == 6 / 16 and cells.tc[4] == 1,
        "gap tile not one texel per physical pixel from its bottom rows")
    local me = DamageMeterSessionWindow1.list[2]
    local function rail(entry) for _, t in ipairs(entry.made) do if t.tex == "color" and t.w == 2 then return t end end end
    assert(rail(me) and rail(me).shown, "no pink rail on the player's own row")
    assert(rail(e) and not rail(e).shown, "a rail on another player's row")
    assert(me.StatusBar.Name.textColor[2] == 0.18, "own name not pink in the ladder")
    FS.Config.Set("skins.damageMeterRows", "plates")
    assert(not cells.shown and not rail(me).shown, "switching back leaves ladder pieces up")
""")

case("blizzard_restyles_and_recolours_are_followed", """
    local e = DamageMeterSessionWindow1.list[1]
    e:SetStyle()
    assert(e.StatusBar.Background.tex == "color", "UpdateStyle re-atlas not followed")
    assert(e.StatusBar.points == 2, "row layout not re-applied after UpdateStyle")
    e:SetStatusBarColor(RAID_CLASS_COLORS.WARRIOR)
    local ramp = FS.DamageMeterSkin.RAMPS.WARRIOR
    assert(e.fill.grad and e.fill.grad[3][1] == ramp[2][1], "recolour not re-ramped")
    e:SetStatusBarColor(CREATURE_COLOR)
    assert(e.fill.grad and e.fill.grad[3][1] > 0.5, "a non class colour gets no ramp")
""")

case("header_buttons_are_the_chat_bar_glyphs_on_one_line", """
    local w = DamageMeterSessionWindow1
    assert(w.DamageMeterTypeDropdown.Arrow.alpha == 0 and w.SessionDropdown.Background.alpha == 0
        and w.SessionDropdown.Arrow.alpha == 0 and w.SettingsDropdown.Icon.alpha == 0, "gold Blizzard art still showing")
    assert(__heldButtons == 1, "minimise button art not held")
    local function glyph(b, name)
        for _, t in ipairs(b.made) do if t.tex and tostring(t.tex):find(name) then return t end end
    end
    local gear, mini = glyph(w.SettingsDropdown, "icon_gear"), glyph(w.MinimizeButton, "icon_minimize")
    assert(gear and gear.vc[4] == 0.85, "settings not a quiet gear glyph")
    assert(mini and mini.vc[2] == 0.18, "minimise not the pink chat glyph")
    w.MinimizeButton.scripts.OnEnter()
    assert(mini.vc[4] == 1, "glyph does not come up on hover")
    w:SetMinimized(true)
    assert(tostring(mini.tex):find("icon_maximize") and mini.vc[2] == 1, "minimised window not the green restore glyph")
    assert(w.MinimizeButton.w == 16 and w.SettingsDropdown.w == 16 and w.SessionDropdown.h == 16, "controls not 16 high")
    assert(w.MinimizeButton.points == 1 and w.SettingsDropdown.points == 1 and w.SessionDropdown.points == 1,
        "controls not re-seated on one line")
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
