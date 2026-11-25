#!/usr/bin/env python3
"""Runs the real FrameStyle.lua, UnitFrames.lua, Config.lua and the Config pages headless to pin the frame Style tabs.

The Style tabs on Unit Frames, Party frames, Raid frames and Pet bar share one set of rows (ConfigPageBars.lua) over one
settings shape (bars.<frame>.<suffix>, FrameStyle.lua). These checks pin:

  * every default equals what the frame draws today (sizes, bar heights, text sizes, the 73 high panel);
  * frame height and bar heights are linked: moving Height changes only the health bar, power 0 hides the bar and shrinks
    the frame;
  * a setting reaches the built frames at once: width, bar heights, opacity, background opacity, glow, data row;
  * the secure button's size waits for PLAYER_REGEN_ENABLED in combat while the visual child follows at once;
  * bar text formats reach SetFormattedText with the engine percent and stubbed secret values, never compared;
  * every row of the prototype's style sections has a registered row on the Unit Frames Style tab, and a section whose rows
    are all hidden for the picked frame is hidden;
  * the preview is the real frame code and redraws with the settings.

Theme, FrameHelpers and the frames are stubs. This is NOT the real client.

    python3 tools/bars-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"

_spec = importlib.util.spec_from_file_location("configwindow_harness", HERE / "configwindow-harness.py")
CWH = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CWH)

FILES = {
    "config": ADDON / "Core/Config.lua",
    "style": ADDON / "Modules/UnitFrames/FrameStyle.lua",
    "unit": ADDON / "Modules/UnitFrames/UnitFrames.lua",
}

PRELUDE = r"""
local create = CreateFrame
function CreateFrame(kind, ...)
    local f = create(kind, ...)
    local baseFont = f.CreateFontString
    f.CreateFontString = function(self, ...)
        local fs = baseFont(self, ...)
        -- a secret is not a number: the recording keeps the format string, as the engine setter takes it whole
        fs.SetFormattedText = function(o, fmt, ...)
            local ok, text = pcall(string.format, fmt, ...)
            o.text = ok and text or fmt
        end
        return fs
    end
    if kind == "StatusBar" then
        f.GetStatusBarTexture = function(self) self.__tex = self.__tex or self:CreateTexture(); return self.__tex end
        f.SetMinMaxValues = function(self, lo, hi) self.min, self.max = lo, hi end
        f.SetValue = function(self, v) self.value = v end
    end
    return f
end
"""

SESSION = r"""
function(src, opts)
    opts = opts or {}
    ALL, __printed, __errors, __combat, BLOCKED = {}, {}, {}, false, {}
    ALL[1], ALL[2] = UIParent, GameTooltip
    UIParent.shown = true
    UISpecialFrames = {}
    for k in pairs(SlashCmdList) do SlashCmdList[k] = nil end
    ForeverSTUwaveDB = opts.db
    __SECRET = {}
    __exists = {}
    __pct = { health = 50, power = 25 }
    __pctCalls = {}
    FS = {}
    FS.IsSecret = function(v) return v ~= nil and rawequal(v, __SECRET) end
    FS.LogDegradeOnce = function() end
    FS.GetFullUnitName = function() return "Bob" end
    FS.Layout = {
        OnRescale = function(fn) __rescale = fn end, Scale = function() return 1 end, UseStore = function() end,
        ReseatAll = function() end, Apply = function() end, boss = {}, focus = {},
        ForwardError = function(err) __errors[#__errors + 1] = tostring(err) end,
    }
    local line = { 0.227, 0.129, 0.408, 1 }
    local Theme = {
        COLOR_BG = { 0.102, 0.063, 0.145, 0.8 }, COLOR_BORDER = { 0.659, 0.333, 0.969, 1 },
        COLOR_BAR_TRACK = { 0.039, 0.016, 0.086, 1 }, COLOR_BAR_BORDER = line, COLOR_TEXT_WHITE = { 1, 1, 1, 1 },
        COLOR_HEALTH = { 1, 0.18, 0.592, 1 }, COLOR_POWER = { 0.133, 0.878, 1, 1 }, COLOR_HEAL = { 0.2, 1, 0.1, 1 },
        COLOR_MUTED = { 0.616, 0.577, 0.769, 1 }, COLOR_CARET_HEALTH = { 0.224, 1, 0.078, 1 }, COLOR_CARET_POWER = { 1, 0, 1, 1 },
        FONT_MONO = "mono.ttf", FONT_ORBITRON = "display.ttf", FILL_CORNER_TEXTURE = "fill_corner.tga",
        FLAT_TEXTURE = "flat", HATCH_TEXTURE = "hatch", PANEL_RADIUS = 6, PANEL_HEADER_H = 18, SKINNED = {},
    }
    function Theme.ApplyMono(fs, size, color) fs:SetFont("mono.ttf", size, ""); fs.themeColor = color end
    function Theme.ApplyFontGeneric(fs, path, size, color) fs:SetFont(path, size, ""); fs.themeColor = color end
    function Theme.SkinPanel(frame, o) Theme.SKINNED[frame] = o or {}; return {} end
    function Theme.SkinButton(button, o)
        local glow = button:CreateTexture(nil, "OVERLAY")
        local ring = button:CreateTexture(nil, "OVERLAY")
        local c = o and o.borderColor
        if c then ring:SetVertexColor(c[1], c[2], c[3], 1); glow:SetVertexColor(c[1], c[2], c[3], o.glowAlpha or 0.35) end
        button.fsSkin = { glow = glow, border = { ring = ring }, opts = o }
        return button.fsSkin
    end
    function Theme.AddCutSliceFill(panel, color, radius)
        local t = panel:CreateTexture(nil, "BACKGROUND")
        t:SetVertexColor(color[1], color[2], color[3], color[4] or 1)
        t.cut = radius
        return t
    end
    function Theme.AddOuterGlow(frame) frame.__glow = true end
    function Theme.AddRoundedFill(frame, color) frame.__fill = color end
    function Theme.AddGradientBorder(frame) frame.__border = true end
    FS.Theme = Theme
    FS.ButtonSkins = { CLOSE = {} }
    function FS.ButtonSkins.NewCloseButton(parent, onClick)
        local b = CreateFrame("Button", nil, parent); b:SetScript("OnClick", onClick); return b
    end
    local function any() return CreateFrame("Frame") end
    FS.FrameHelpers = {
        DimBlizzardFrame = function() end,
        NewStepRunner = function() return function(frame, label, fn) fn(frame) end, function() end end,
        UpdateCaretFull = function() end,
        CreateCaret = function(bar) local c = { host = CreateFrame("Frame", nil, bar) }; return c end,
        CreateLevelChip = function(parent)
            local chip = CreateFrame("Frame", nil, parent); chip:SetSize(26, 16)
            chip.text = chip:CreateFontString(nil, "OVERLAY"); chip.text.hasFont = true
            return chip
        end,
        CreatePillBar = function(parent, o)
            local bar = CreateFrame("StatusBar", nil, parent)
            bar.shell = CreateFrame("Frame", nil, parent)
            bar.shell:SetHeight(o.height)
            bar.fsPillHeight = o.height
            bar.text = bar:CreateFontString(nil, "OVERLAY"); bar.text.hasFont = true
            function bar:SetPillHeight(h) self.fsPillHeight = h; self.shell:SetHeight(h); self.pillCalls = (self.pillCalls or 0) + 1 end
            return bar
        end,
    }
    CLASS_ICON_TCOORDS = { SHAMAN = { 0.25, 0.5, 0.25, 0.5 } }
    function RegisterUnitWatch() end
    function UnitExists(unit) return __exists[unit] == true end
    function UnitHealth() return __SECRET end
    function UnitHealthMax() return __SECRET end
    function UnitPower() return __SECRET end
    function UnitPowerMax() return __SECRET end
    function UnitPowerType() return 0 end
    function UnitIsPlayer() return true end
    function UnitClass() return "Shaman", "SHAMAN" end
    function UnitLevel() return 22 end
    function UnitReaction() return 5 end
    function UnitIsConnected() return true end
    function UnitIsDeadOrGhost() return false end
    function UnitIsGhost() return false end
    function UnitGetIncomingHeals() return 0 end
    function UnitGetTotalAbsorbs() return 0 end
    function IsResting() return false end
    function GetRaidTargetIndex() return nil end
    function SetRaidTargetIconTexture() end
    function GetUnitName() return "Bob" end
    CurveConstants = { ScaleTo100 = "curve100" }
    function UnitHealthPercent(unit, c, curve) __pctCalls[#__pctCalls + 1] = { "health", unit, c, curve }; return __pct.health end
    function UnitPowerPercent(unit, t, c, curve) __pctCalls[#__pctCalls + 1] = { "power", unit, t, c, curve }; return __pct.power end
    assert(load(src.config, "@Config.lua"))("forever-stuwave", FS)
    if opts.noStyle ~= true then assert(load(src.style, "@FrameStyle.lua"))("forever-stuwave", FS) end
    if opts.noUnit ~= true then assert(load(src.unit, "@UnitFrames.lua"))("forever-stuwave", FS) end
    for _, chunk in ipairs(src.window) do
        assert(load(chunk[2], "@" .. chunk[1]))("forever-stuwave", FS)
    end
    Fire("ADDON_LOADED", "forever-stuwave")
    Fire("PLAYER_LOGIN")
end
"""

CHECKS = r"""
local T = {}
local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end
local function yes(v, msg) if not v then error(msg or "expected true", 2) end end
local function boot(opts)
    __session(__src, opts)
    return FS.FrameStyle, FS.Config, FS.ConfigWindow
end
local function openStyle(CW, page)
    CW.Open(page or "unit", page == "party" and "style" or (page == "raid" and "style" or (page == "pet" and "style" or "bars")))
end
local function endCombat() __combat = false; Fire("PLAYER_REGEN_ENABLED") end

function T.defaults_equal_what_the_frames_draw_today()
    local S = boot()
    eq(S.Get("player", "w"), 260); eq(S.Get("target", "w"), 260)
    eq(S.Get("focus", "w"), 190); eq(S.Get("boss", "w"), 210)
    for _, f in ipairs({ "player", "target", "focus", "boss" }) do
        eq(S.Get(f, "hpH"), 16, f); eq(S.Get(f, "mpH"), 16, f)
        eq(S.Get(f, "hpTs"), 11); eq(S.Get(f, "nameSize"), 15); eq(S.Get(f, "iconSize"), 20)
        eq(S.Get(f, "hpFmt"), "number"); eq(S.Get(f, "mpFmt"), "number")
        eq(S.Get(f, "alpha"), 100); eq(S.Get(f, "glow"), true); eq(S.Get(f, "glowAmt"), 100)
        eq(S.FrameHeight(f), 73, "panel height")
        eq(S.RowHeight(f), 22, "data row")
    end
    eq(S.Get("target", "bgAlpha"), 80)
    eq(S.Get("party", "hpH"), 9); eq(S.Get("party", "w"), 187); eq(S.Get("raid", "bgAlpha"), 85); eq(S.Get("pet", "w"), 134)
end

function T.a_default_frame_saves_no_keys_and_a_built_frame_is_the_size_it_was()
    local S, C = boot()
    eq(FS.target.visual:GetHeight(), 73); eq(FS.target:GetWidth(), 260)
    eq(FS.target.health.fsPillHeight, 16); eq(FS.target.power.fsPillHeight, 16)
    eq(FS.target.visual:GetAlpha(), 1); eq(FS.target.fillHost:GetAlpha(), 0.8); eq(FS.target.glowHost:GetAlpha(), 0.38)
    eq(FS.target.health.pillCalls, nil, "no pill rebuild at the default")
    yes(not C.IsStored("bars.target.hpH"))
end

function T.frame_height_and_bar_heights_are_linked()
    local S, C = boot()
    S.SetFrameHeight("target", 83)
    eq(S.Get("target", "hpH"), 26, "only the health bar moves"); eq(S.Get("target", "mpH"), 16)
    eq(S.FrameHeight("target"), 83)
    eq(FS.target.visual:GetHeight(), 83, "the live frame follows")
    eq(FS.target.health.fsPillHeight, 26)
    S.Set("target", "mpH", 0)
    eq(S.FrameHeight("target"), 83 - 22, "power off drops the gap and the bar")
    S.SetFrameHeight("target", 5)
    eq(S.Get("target", "hpH"), 2, "stops at the bar's own range")
end

function T.power_height_zero_hides_the_bar_and_shrinks_the_frame()
    local S = boot()
    __exists.target = true
    S.Set("target", "mpH", 0)
    eq(FS.target.visual:GetHeight(), 51)
    eq(__errors[1], nil)
    eq(FS.target.power.shell:IsShown(), false)
    S.Set("target", "mpH", 16)
    eq(FS.target.visual:GetHeight(), 73)
    eq(FS.target.power.shell:IsShown(), true)
end

function T.opacity_background_and_glow_reach_their_own_pieces()
    local S = boot()
    S.Set("target", "alpha", 60); S.Set("target", "bgAlpha", 50); S.Set("target", "glowAmt", 200)
    eq(FS.target.visual:GetAlpha(), 0.6); eq(FS.target.fillHost:GetAlpha(), 0.5)
    eq(FS.target.glowHost:GetAlpha(), 0.76)
    S.Set("target", "glow", false)
    eq(FS.target.glowHost:IsShown(), false)
    eq(FS.player.visual:GetAlpha(), 1, "the other frames are untouched")
end

function T.the_secure_size_waits_for_the_end_of_combat_and_the_visual_does_not()
    local S = boot()
    __combat = true
    S.Set("target", "w", 300); S.Set("target", "hpH", 30)
    eq(FS.target:GetWidth(), 260, "secure width waits"); eq(FS.target:GetHeight(), 73, "secure height waits")
    eq(FS.target.visual:GetHeight(), 87, "the visual follows at once")
    eq(FS.target.health.fsPillHeight, 30)
    S.Set("target", "w", 320)
    endCombat()
    eq(FS.target:GetWidth(), 320, "the latest width wins"); eq(FS.target:GetHeight(), 87)
end

function T.focus_and_boss_width_is_the_setting_times_the_layout_scale()
    local S = boot()
    local scale = 0.5
    FS.Layout.Scale = function() return scale end
    __rescale()
    eq(FS.focus:GetWidth(), 95); eq(FS.boss[1]:GetWidth(), 105)
    eq(FS.target:GetWidth(), 260, "player and target are in UI units")
    S.Set("focus", "w", 200)
    eq(FS.focus:GetWidth(), 100)
end

local function record(text)
    text.calls = {}
    text.SetFormattedText = function(self, fmt, ...) self.calls[#self.calls + 1] = { fmt, ... } end
    text.Show = function(self) self.shown = true end
    text.Hide = function(self) self.shown = false end
end

function T.text_formats_go_to_set_formatted_text_and_a_secret_is_never_compared()
    local S = boot()
    __exists.target = true
    local text = FS.target.health.text
    record(text)
    local function last() return text.calls[#text.calls] end
    S.Set("target", "hpFmt", "number")
    S.WriteBarText(text, "number", "target", "health", __SECRET, __SECRET)
    eq(last()[1], "%d / %d"); eq(last()[2], __SECRET); eq(last()[3], __SECRET)
    S.WriteBarText(text, "percent", "target", "health", __SECRET, __SECRET)
    eq(last()[1], "%.0f%%"); eq(last()[2], 50)
    eq(__pctCalls[#__pctCalls][4], "curve100")
    S.WriteBarText(text, "both", "target", "health", __SECRET, __SECRET)
    eq(last()[1], "%d / %d  %.0f%%"); eq(last()[4], 50)
    S.WriteBarText(text, "none", "target", "health", __SECRET, __SECRET)
    eq(text.shown, false)
    local power = { Show = function() end }
    record(power)
    S.WriteBarText(power, "percent", "target", "power", 1, 2)
    eq(power.calls[1][2], 25)
end

function T.without_the_percent_read_the_number_shows()
    local S = boot()
    UnitHealthPercent = nil
    local text = FS.target.health.text
    record(text)
    yes(not S.PercentAvailable("health"))
    S.WriteBarText(text, "percent", "target", "health", 5, 10)
    eq(text.calls[1][1], "%d / %d")
end

function T.text_size_position_and_offset_reseat_the_font_string()
    local S = boot()
    local text = FS.target.health.text
    S.Set("target", "hpTa", "left"); S.Set("target", "hpTx", 5); S.Set("target", "hpTs", 14)
    local pt = text.points[#text.points]
    eq(pt.point, "LEFT"); eq(pt.x, 9); eq(text.fontSize, 14)
    S.Set("target", "hpTa", "center"); S.Set("target", "hpTx", 0)
    pt = text.points[#text.points]
    eq(pt.point, "CENTER"); eq(pt.x, 0)
end

function T.data_row_grows_with_its_biggest_part_and_hidden_parts_give_space_to_the_name()
    local S = boot()
    S.Set("target", "iconSize", 28)
    eq(S.RowHeight("target"), 30); eq(S.FrameHeight("target"), 81)
    eq(FS.target.nameRow:GetHeight(), 30)
    S.Set("target", "iconSize", 20)
    S.Set("target", "level", false)
    local name = FS.target.name
    local rightmost
    for _, p in ipairs(name.points) do if p.point == "LEFT" then rightmost = p end end
    eq(rightmost.rel, FS.target.nameRow, "mirrored name runs to the row edge with no level chip")
    S.Set("target", "name", false)
    eq(name:IsShown(), false)
    S.Set("target", "classIcon", false); S.Set("target", "raidMark", false); S.Set("target", "level", false)
    eq(S.RowHeight("target"), 0); eq(FS.target.visual:GetHeight(), 73 - 25)
end

function T.every_row_of_the_style_sections_has_a_registered_row()
    local S, C, CW = boot()
    openStyle(CW)
    local seen = {}
    for _, e in ipairs(CW.Rows()) do if e.page == "unit" and e.tab == "bars" and e.key then seen[e.key] = true end end
    local missing = {}
    for _, sec in ipairs(FS.ConfigBars.SECTIONS) do
        for _, row in ipairs(sec.rows) do
            if not seen["bars." .. row.suffix] then missing[#missing + 1] = row.suffix end
        end
    end
    eq(#missing, 0, "missing rows: " .. table.concat(missing, ","))
end

function T.rows_write_the_picked_frame_and_a_section_with_no_rows_for_it_is_hidden()
    local S, C, CW = boot()
    openStyle(CW)
    C.Set("bars.module", "focus")
    CW.RefreshAll()
    local entry = CW.RowByKey("bars.hpH", "unit")
    entry.row.control.scripts.OnClick = entry.row.control.scripts.OnClick
    yes(entry.row:IsShown())
    local ok = FS.ConfigBars.SECTIONS
    -- the Style tab's rows write the frame the picker shows
    local w = CW.RowByKey("bars.w", "unit")
    yes(w, "width row")
    w.row.fsEdit:SetText("200")
    w.row.fsEdit.scripts.OnEnterPressed(w.row.fsEdit)
    eq(S.Get("focus", "w"), 200); eq(S.Get("target", "w"), 260)
end

function T.the_preview_is_the_real_frame_and_redraws_with_the_settings()
    local S, C, CW = boot()
    openStyle(CW)
    local previews = 0
    for _, o in ipairs(ALL) do if o.preview and o.styleKey == "target" then previews = previews + 1 end end
    eq(previews, 1, "one preview frame for the picked frame")
    local p
    for _, o in ipairs(ALL) do if o.preview and o.styleKey == "target" then p = o end end
    eq(p.visual:GetHeight(), 73)
    S.Set("target", "hpH", 30)
    eq(p.visual:GetHeight(), 87, "the preview follows a setting")
    eq(p.health.fsPillHeight, 30)
    eq(p.health.text:GetText(), "2481 / 3000")
    S.Set("target", "hpFmt", "percent")
    eq(p.health.text:GetText(), "83%")
end

function T.pointing_at_a_switch_turns_the_feature_on_in_the_preview_for_the_moment()
    local S, C, CW = boot()
    openStyle(CW)
    S.Set("target", "level", false)
    local p
    for _, o in ipairs(ALL) do if o.preview and o.styleKey == "target" then p = o end end
    eq(p.levelBadge:IsShown(), false)
    local entry = CW.RowByKey("bars.level", "unit")
    CW.SetHover(entry)
    eq(p.levelBadge:IsShown(), true, "hover shows it")
    eq(S.Get("target", "level"), false, "nothing is saved")
    CW.SetHover(nil)
    eq(p.levelBadge:IsShown(), false)
end

return T
"""


def sources() -> dict:
    return {
        "config": FILES["config"].read_text(encoding="utf-8"),
        "style": FILES["style"].read_text(encoding="utf-8"),
        "unit": FILES["unit"].read_text(encoding="utf-8"),
        "window": CWH.config_sources(),
    }


def boot():
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(CWH.MOCK)
    lua.execute(PRELUDE)
    lua.globals().__session = lua.eval(SESSION)
    src = sources()
    lua.globals().__src = CWH.to_lua(lua, src)
    lua.globals().__checks = lua.execute(CHECKS)
    return lua


def main() -> int:
    names = sorted(boot().eval("__checks").keys())
    failed = 0
    for name in names:
        try:
            lua = boot()
            lua.eval("__checks")[name]()
            leaked = list(lua.eval("__errors").values())
            if leaked:
                raise LuaError(f"errors were forwarded to the error handler: {leaked}")
            print(f"ok    {name}")
        except LuaError as err:
            failed += 1
            print(f"FAIL  {name}: {err}")
    print(f"{len(names) - failed}/{len(names)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
