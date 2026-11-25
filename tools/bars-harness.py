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
import os
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
MOCKUPS = Path(os.environ.get("FS_MOCKUPS_DIR", HERE.parent / "mockups"))

_spec = importlib.util.spec_from_file_location("configwindow_harness", HERE / "configwindow-harness.py")
CWH = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CWH)

FILES = {
    "config": ADDON / "Core/Config.lua",
    "style": ADDON / "Modules/UnitFrames/FrameStyle.lua",
    "extras": ADDON / "Modules/UnitFrames/FrameExtras.lua",
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
    __looks = {}
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
        SetBarLook = function(bar, look) __looks[#__looks + 1] = { bar, look } end,
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
    if opts.noStyle ~= true then assert(load(src.extras, "@FrameExtras.lua"))("forever-stuwave", FS) end
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
            if row.suffix and not seen["bars." .. row.suffix] then missing[#missing + 1] = row.suffix end
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

function T.bar_looks_reach_the_bars_and_the_dropdown_offers_only_what_a_frame_can_wear()
    local S = boot()
    yes(S.LookAvailable("cut", "player")); yes(not S.LookAvailable("laser", "player"))
    yes(S.LookAvailable("laser", "party")); yes(not S.LookAvailable("cut", "party"))
    for _, v in ipairs({ "flat", "led", "slant", "chevron", "stock" }) do
        yes(S.LookAvailable(v, "player") and S.LookAvailable(v, "pet"), v)
    end
    __looks = {}
    local frame = FS.UnitFrames.NewPreview(CreateFrame("Frame"), "player")
    yes(#__looks >= 2, "the build applies a look to both bars")
    for _, l in ipairs(__looks) do eq(l[2], "cut", "default look is the stock cut") end
    S.Set("player", "hpStyle", "led")
    local sawLed = false
    for _, l in ipairs(__looks) do if l[2] == "led" then sawLed = true end end
    yes(sawLed, "a changed hpStyle restyles the bar")
end

function T.extras_and_aggro_show_in_the_preview_only_when_their_switch_is_on()
    local S = boot()
    local f = FS.UnitFrames.NewPreview(CreateFrame("Frame"), "target")
    local x = f.extras
    yes(x, "the frame builds its extras")
    for _, k in ipairs({ "elite", "tot", "pvp", "leader", "portrait" }) do yes(not x[k]:IsShown(), k .. " is off by default") end
    yes(not x.cast:IsShown() and not x.threat:IsShown())
    for _, k in ipairs({ "elite", "tot", "pvp", "cast", "threat", "threatPct" }) do S.Set("target", k, true) end
    f.Restyle()
    yes(x.tot:IsShown() and x.pvp:IsShown() and x.cast:IsShown() and x.threat:IsShown() and x.pct:IsShown())
    S.Set("target", "threat", false)
    f.Restyle()
    yes(not x.threat:IsShown())
    local p = FS.UnitFrames.NewPreview(CreateFrame("Frame"), "player")
    S.Set("player", "threat", true); S.Set("player", "threatPct", true)
    p.Restyle()
    yes(p.extras.threat:IsShown() and not p.extras.pct:IsShown(), "the player frame has no percent")
end

function T.a_secret_threat_reading_is_never_compared()
    local S = boot()
    local f = FS.UnitFrames.NewPreview(CreateFrame("Frame"), "target")
    f.preview = nil; f.unit = "target"
    S.Set("target", "threat", true)
    __exists.target = true
    UnitDetailedThreatSituation = function() return false, __SECRET, __SECRET end
    FS.FrameExtras.Update(f)
    yes(not f.extras.threat:IsShown(), "a hidden reading draws nothing")
    UnitDetailedThreatSituation = function() return true, 3, 100 end
    FS.FrameExtras.Update(f)
    yes(f.extras.threat:IsShown(), "tanking draws the border")
end

function T.the_raid_style_tab_has_its_layout_rows_and_the_size_picker_in_the_preview_header()
    local S, C, CW = boot()
    local pv = { KEY = "raid.previewSize", SIZES = { 5, 10, 15, 20, 25, 40 } }
    C.RegisterDefault(pv.KEY, 10)
    function pv.Size() return C.Get(pv.KEY) end
    FS.RaidFrames = { Preview = pv, NewStylePreview = function(stage)
        local f = CreateFrame("Frame", nil, stage); f:SetSize(100, 60); return { frame = f, Restyle = function() end }
    end }
    CW.Open("raid", "style")
    yes(CW.RowByKey("raid.scale", "raid"), "scale")
    yes(CW.RowByKey("raid.arrange", "raid"), "arrange")
    local perRow = CW.RowByKey("raid.perRow", "raid")
    yes(perRow, "perRow")
    yes(not perRow.row:IsShown(), "frames per row waits for Grid")
    C.Set("raid.arrange", "grid"); CW.RefreshAll()
    yes(perRow.row:IsShown(), "frames per row shows with Grid")
end

function T.rows_a_frame_does_not_apply_yet_say_so_and_the_raid_rows_it_does_apply_stay_live()
    local S, C, CW = boot()
    yes(FS.ConfigBars.IsWired("player", "hpH") and FS.ConfigBars.IsWired("raid", "w") and FS.ConfigBars.IsWired("party", "alpha"))
    yes(not FS.ConfigBars.IsWired("raid", "hpFmt") and not FS.ConfigBars.IsWired("party", "hpH"))
end

-- The pet frame, as far as the config page can reach it: a dock state and a preview that is a plain frame.
local function stubPet(docked)
    local made = {}
    FS.PetFrame = {
        IsDocked = function() return docked.on end,
        NewStylePreview = function(stage)
            local f = CreateFrame("Frame", nil, stage); f:SetSize(348, 68)
            made[#made + 1] = f
            return { frame = f, Restyle = function() end }
        end,
    }
    return made
end

-- Every shared row the pet frame applies (Bars.WIRED.pet): all live, none greyed.
local PET_APPLIED = { "w", "fh", "alpha", "bgAlpha", "hpStyle", "hpH", "hpFmt", "hpTs", "hpTa", "hpTx",
    "mpStyle", "mpH", "mpFmt", "mpTs", "mpTa", "mpTx", "name", "nameSize", "nameX", "level", "levelSize", "levelX" }

function T.the_pet_style_tab_has_the_cast_bar_rows_the_preview_and_the_rows_the_pet_frame_applies()
    local S, C, CW = boot()
    local docked = { on = false }
    local made = stubPet(docked)
    CW.Open("pet", "style")
    for _, key in ipairs({ "pet.cast", "pet.castShow", "pet.castFree", "pet.castIcon", "pet.castName", "pet.castTimer" }) do
        yes(CW.RowByKey(key, "pet"), key)
    end
    eq(#made, 1, "the preview is the pet frame's own drawing")
    local free = CW.RowByKey("pet.castFree", "pet")
    yes(not free.row:IsShown(), "When hidden waits for a cast bar that is not always shown")
    C.Set("pet.castShow", "casting"); CW.RefreshAll()
    yes(free.row:IsShown(), "When hidden shows once the bar can hide")
    for _, suffix in ipairs(PET_APPLIED) do
        local e = CW.RowByKey("bars." .. suffix, "pet")
        yes(e, "shared row bars." .. suffix)
        yes(not e.row.fsRowOff, "bars." .. suffix .. " is applied to the pet frame, so it is not greyed")
        yes(FS.ConfigBars.IsWired("pet", suffix), suffix .. " is on the applied list")
    end
    for _, suffix in ipairs({ "glow", "glowAmt" }) do
        local e = CW.RowByKey("bars." .. suffix, "pet")
        yes(e and e.row.fsRowOff, "bars." .. suffix .. " is not applied to the pet frame yet, so it is greyed")
    end
end

function T.the_pet_kind_picker_sits_in_the_preview_header_and_switches_the_preview_kind()
    local S, C, CW = boot()
    stubPet({ on = false })
    CW.Open("pet", "style")
    eq(C.Get("pet.previewKind"), "hunter")
    yes(CW.RowByKey("pet.previewKind", "pet") == nil, "the picker is in the header, not a row")
    local picked
    for _, b in ipairs(ALL) do
        if b.fsLabel and b.fsLabel.GetText and b.fsLabel:GetText() == "Warlock demon" and b.GetScript and b:GetScript("OnClick") then picked = b end
    end
    yes(picked, "a Warlock demon button in the header")
    picked:GetScript("OnClick")(picked)
    eq(C.Get("pet.previewKind"), "demon")
end

function T.docked_beside_the_console_the_pet_size_rows_are_greyed_with_a_reason_and_float_frees_them()
    local S, C, CW = boot()
    local docked = { on = true }
    stubPet(docked)
    CW.Open("pet", "style")
    for _, key in ipairs({ "bars.w", "bars.fh", "bars.hpH", "bars.mpH" }) do
        local e = CW.RowByKey(key, "pet")
        yes(e.row.fsRowOff, key .. " is locked while docked")
        yes(e.why and e.why:find("Console", 1, true), key .. " says the Console sets the size")
        yes(not e.why:find("not applied", 1, true), key .. " is not the not-applied line")
    end
    yes(not CW.RowByKey("bars.hpTs", "pet").row.fsRowOff, "text size is not the dock's to set")
    yes(not CW.RowByKey("bars.alpha", "pet").row.fsRowOff, "opacity is not the dock's to set")
    docked.on = false; CW.RefreshAll()
    for _, key in ipairs({ "bars.w", "bars.fh", "bars.hpH", "bars.mpH" }) do
        yes(not CW.RowByKey(key, "pet").row.fsRowOff, key .. " is free once the bar floats")
    end
end

function T.the_pet_size_rows_stay_live_when_the_pet_frame_is_missing()
    local S, C, CW = boot()
    FS.PetFrame = nil
    CW.Open("pet", "style")
    yes(not CW.RowByKey("bars.w", "pet").row.fsRowOff, "no pet frame, no dock to lock the row")
end

-- Criterion 6: every row of the prototype's three Pet tabs has its row here.
function T.every_row_of_the_prototype_pet_tabs_is_registered_on_the_pet_page()
    local S, C, CW = boot()
    stubPet({ on = false })
    local seen = {}
    for tab, keys in pairs(__protoPet) do
        CW.Open("pet", tab)
        for _, key in pairs(keys) do
            if key ~= "pet.previewKind" then
                yes(CW.RowByKey(key, "pet"), "prototype row " .. key .. " on the " .. tab .. " tab")
            end
        end
        seen[tab] = true
    end
    yes(seen.style and seen.hunter and seen.warlock, "three tabs parsed from the prototype")
    local swatches = 0
    for _, e in ipairs(CW.Rows()) do
        if e.page == "pet" and e.tab == "hunter" and e.kind == "swatch" then swatches = swatches + 1 end
    end
    eq(swatches, 1, "the happiness colour swatch")
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
        "extras": FILES["extras"].read_text(encoding="utf-8"),
        "unit": FILES["unit"].read_text(encoding="utf-8"),
        "window": CWH.config_sources(),
    }


def proto_pet_rows() -> dict[str, list[str]]:
    """The prototype's Pet bar tabs: tab key -> the setting keys of its rows (proto-pages.js)."""
    src = (MOCKUPS / "proto-src-2026-11-25" / "proto-pages.js").read_text(encoding="utf-8")
    start = src.index(" {key:'pet',label:'Pet bar',tabs:[")
    end = src.index(" {key:'profiles'", start)
    tabs: dict[str, list[str]] = {}
    for chunk in re.split(r"\n  \{key:'", src[start:end])[1:]:
        tabs[chunk.split("'", 1)[0]] = re.findall(r"\bk:'(pet\.[A-Za-z]+)'", chunk)
    return tabs


def boot():
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(CWH.MOCK)
    lua.execute(PRELUDE)
    lua.globals().__session = lua.eval(SESSION)
    src = sources()
    lua.globals().__src = CWH.to_lua(lua, src)
    lua.globals().__protoPet = CWH.to_lua(lua, proto_pet_rows())
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
