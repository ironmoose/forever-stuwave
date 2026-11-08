#!/usr/bin/env python3
"""Runs the real Modules/Compat/Questie.lua headless against a stub Questie.

The Questie compat module skins the Questie quest tracker to match STUwave. These checks pin:

  * nothing is built, registered or hooked without Questie, and no panel without its tracker enabled;
  * the cut panel chrome (fill, glow, border, header band, rule) is built once on Questie_BaseFrame, from the
    Theme helpers, and sizes by anchors alone: no resize script, no poll once built;
  * Questie's own backdrop pieces are held at region alpha 0 while its colour state stays intact;
  * the panel follows Questie's backdrop colour alpha (the fade, the off switch, a hide), ignoring secret and
    non-numeric values;
  * a frame Questie makes after login is picked up by a bounded timer that stops once built;
  * the header band sits behind Questie's header row only when that row is shown at the top, read from the
    header's own anchor and height;
  * an error in the hook is handed to the error handler and never reaches Questie's own update;
  * the STUwave font is registered with LibSharedMedia under a neutral name, once, without touching
    Questie's own font settings;
  * the existing target frame icon adoption still moves Questie's icon onto the STUwave target frame.

    python3 tools/questie-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

SRC = (Path(__file__).resolve().parent.parent / "forever-stuwave/Modules/Compat/Questie.lua").read_text(encoding="utf-8")

MOCK = r"""
local Obj = {}
Obj.__index = Obj
function Obj:SetPoint(p, rel, rp, x, y)
    self.points = self.points or {}
    self.points[#self.points + 1] = { p, rel, rp, x or 0, y or 0 }
end
function Obj:ClearAllPoints() self.points = {} end
function Obj:GetPoint(i)
    local pt = self.points and self.points[i or 1]
    if pt then return pt[1], pt[2], pt[3], pt[4], pt[5] end
end
function Obj:SetHeight(h) self.h = h end
function Obj:SetWidth(w) self.w = w end
function Obj:SetSize(w, h) self.w, self.h = w, h end
function Obj:GetHeight() return self.h or 0 end
function Obj:GetWidth() return self.w or 0 end
function Obj:GetTop() return self._top end
function Obj:GetBottom() return self._bottom end
function Obj:SetAlpha(a) self.alpha = a end
function Obj:GetAlpha() return self.alpha end
function Obj:Show() self.shown = true end
function Obj:Hide() self.shown = false end
function Obj:SetShown(v) self.shown = not not v end
function Obj:IsShown() return self.shown ~= false end
function Obj:SetColorTexture(r, g, b, a) self.ct = { r, g, b, a } end
function Obj:SetVertexColor(r, g, b, a) self.vc = { r, g, b, a } end
function Obj:GetVertexColor() local c = self.vc or { 1, 1, 1, 1 }; return c[1], c[2], c[3], c[4] end
function Obj:SetScript(n, fn) self.scripts = self.scripts or {}; self.scripts[n] = fn end
function Obj:RegisterEvent(e) self.events = self.events or {}; self.events[e] = true end
function Obj:UnregisterEvent(e) if self.events then self.events[e] = nil end end
function Obj:UnregisterAllEvents() self.events = {} end
function Obj:CreateTexture(_, layer) local t = New("Texture"); t.parent = self; t.layer = layer; __textures[#__textures + 1] = t; return t end
function Obj:GetObjectType() return self.kind end
function Obj:GetName() return self.name end
function Obj:GetChildren() return unpack(self.children or {}) end
function Obj:SetParent(p) self.parent = p end
function Obj:GetFrameStrata() return self.strata or "MEDIUM" end
function Obj:SetFrameStrata(s) self.strata = s end
function Obj:GetFrameLevel() return self.level or 1 end
function Obj:SetFrameLevel(l) self.level = l end
function Obj:SetTexture(t) self.texture = t end

function New(kind) return setmetatable({ kind = kind }, Obj) end
__frames, __textures, __chrome, __hooked, __tickers, __registered = {}, {}, {}, {}, {}, {}

function CreateFrame(kind, name, parent)
    local f = New(kind); f.name = name; f.parent = parent
    __frames[#__frames + 1] = f
    if name then _G[name] = f end
    return f
end
function Fire(event, ...)
    for _, f in ipairs(__frames) do
        if f.events and f.events[event] and f.scripts and f.scripts.OnEvent then f.scripts.OnEvent(f, event, ...) end
    end
end
function Tick() for _, t in ipairs(__tickers) do if not t.cancelled then t.fn() end end end
function LiveTickers() local n = 0; for _, t in ipairs(__tickers) do if not t.cancelled then n = n + 1 end end; return n end

function hooksecurefunc(t, name, fn)
    local orig = t[name]
    __hooked[#__hooked + 1] = name
    t[name] = function(...) local r = { orig(...) }; fn(...); return unpack(r) end
end
C_Timer = {
    After = function(_, fn) fn() end,
    NewTicker = function(sec, fn, n)
        local t = { sec = sec, fn = fn, n = n, cancelled = false }
        function t:Cancel() self.cancelled = true end
        __tickers[#__tickers + 1] = t
        return t
    end,
}

-- Blizzard's BackdropTemplate keeps its colour state in the Center piece's vertex colour, and the border in the others.
local PIECES = { "Center", "TopLeftCorner", "TopRightCorner", "BottomLeftCorner", "BottomRightCorner",
    "TopEdge", "BottomEdge", "LeftEdge", "RightEdge" }
function MakeBase()
    local base = CreateFrame("Frame", "Questie_BaseFrame", UIParent)
    base._top = 800
    for _, name in ipairs(PIECES) do base[name] = New("Texture") end
    base.Center:SetVertexColor(0, 0, 0, 1)
    function base:SetBackdropColor(r, g, b, a) self.Center:SetVertexColor(r, g, b, a) end
    function base:SetBackdropBorderColor(r, g, b, a)
        for _, name in ipairs(PIECES) do if name ~= "Center" then self[name]:SetVertexColor(r, g, b, a) end end
    end
    function base:GetBackdropColor() return self.Center:GetVertexColor() end
    return base
end
function MakeHeader(base, height)
    local header = CreateFrame("Button", "Questie_HeaderFrame", base)
    header:SetPoint("TOPLEFT", base, "TOPLEFT", 0, -10)   -- where Questie seats it (TrackerHeaderFrame.lua)
    header:SetHeight(height)
    return header
end

UIParent = New("Frame")
__loaded = { Questie = true }
C_AddOns = { IsAddOnLoaded = function(n) return __loaded[n] == true end }
Questie = { db = { profile = { trackerEnabled = true, trackerFontQuest = "Friz Quadrata TT", trackerFontHeader = "Friz Quadrata TT" } } }

__known = true
LSM = { LOCALE_BIT_western = 128, fonts = {} }
function LSM:Register(kind, key, path, mask)
    __registered[#__registered + 1] = { kind, key, path, mask }
    if not __known or self.fonts[key] then return false end
    self.fonts[key] = path
    return true
end
function LSM:IsValid(kind, key) return self.fonts[key] ~= nil end
LibStub = function(name, silent) if name == "LibSharedMedia-3.0" then return LSM end end

__secret = 0.123
__errors = {}
FS = {
    Layout = { ForwardError = function(e) __errors[#__errors + 1] = e end },
    IsSecret = function(v) return v == __secret end,
    Theme = {
        COLOR_BG = { 0.102, 0.063, 0.145, 0.80 }, COLOR_POWER = { 0.133, 0.878, 1, 1 },
        FONT_MONO = "Interface\\AddOns\\forever-stuwave\\Media\\Fonts\\MononokiNerdFontMono-Bold.ttf",
        PanelBandInset = function() return 3 end,
        AddPanelChrome = function(frame, opts)
            local fill, glow, border = frame:CreateTexture(nil, "BACKGROUND"), frame:CreateTexture(nil, "BACKGROUND"), frame:CreateTexture(nil, "BORDER")
            __chrome[#__chrome + 1] = { frame = frame, opts = opts, fill = fill, glow = glow, border = border }
            return fill, glow, border
        end,
    },
}
function Load() assert(loadstring(SRC, "@Questie.lua"))("forever-stuwave", FS); QC = FS.QuestieCompat end
function Chrome() return __chrome[1] end
function Band() return __textures[#__textures - 1] end
function Rule() return __textures[#__textures] end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("nothing_happens_without_questie", """
    __loaded.Questie = false
    Load()
    local events = __frames[#__frames]
    MakeBase()
    Fire("ADDON_LOADED", "Questie"); Fire("PLAYER_LOGIN")
    assert(#__chrome == 0, "chrome built without Questie")
    assert(#__registered == 0, "font registered without Questie")
    assert(#__hooked == 0, "hook installed without Questie")
    assert(LiveTickers() == 0, "timer started without Questie")
    assert(next(events.events) == nil, "events still listened to")
""")

case("no_panel_when_the_questie_tracker_is_off", """
    Questie.db.profile.trackerEnabled = false
    MakeBase()
    Load(); Fire("PLAYER_LOGIN")
    assert(#__chrome == 0, "chrome built with the tracker off")
    assert(#__hooked == 0 and LiveTickers() == 0, "hook or timer with the tracker off")
    assert(QC.TrackerActive() == false)
""")

case("tracker_active_needs_questie_and_its_tracker_enabled", """
    Load()
    assert(QC.TrackerActive() == true)
    Questie.db.profile.trackerEnabled = false
    assert(QC.TrackerActive() == false)
    Questie.db.profile.trackerEnabled = true
    __loaded.Questie = false
    assert(QC.TrackerActive() == false)
    Questie = nil; __loaded.Questie = true
    assert(QC.TrackerActive() == false, "no Questie table")
""")

case("chrome_is_the_cut_panel_on_the_base_frame", """
    local base = MakeBase()
    Load(); Fire("PLAYER_LOGIN")
    assert(#__chrome == 1, "chrome not built once: " .. #__chrome)
    local c = Chrome()
    assert(c.frame == base, "chrome not on Questie_BaseFrame")
    assert(c.opts.fillColor == FS.Theme.COLOR_BG, "fill is not Theme.COLOR_BG")
    assert(c.opts.accent == FS.Theme.COLOR_POWER, "accent is not Theme.COLOR_POWER")
    local band, rule = Band(), Rule()
    assert(band.ct[1] == 0.133 and band.ct[4] == 0.08, "band tint")
    assert(rule.ct[1] == 0.133 and rule.ct[4] == 0.30, "rule tint")
    assert(rule.h == 1)
""")

case("chrome_is_built_once", """
    MakeBase()
    Load(); Fire("PLAYER_LOGIN")
    QC.SkinTracker(); QC.SkinTracker(); Fire("PLAYER_LOGIN"); Tick()
    assert(#__chrome == 1, "built again: " .. #__chrome)
    local n = 0
    for _, name in ipairs(__hooked) do if name == "SetBackdropColor" then n = n + 1 end end
    assert(n == 1, "hooked " .. n .. " times")
""")

case("size_follows_by_anchors_not_scripts_or_polling", """
    local base = MakeBase()
    Load(); Fire("PLAYER_LOGIN")
    local band = Band()
    assert(band.points[1][1] == "TOPLEFT" and band.points[1][2] == base, "band left anchor")
    assert(band.points[2][1] == "TOPRIGHT" and band.points[2][2] == base, "band right anchor")
    assert(band.points[1][4] == 3 and band.points[1][5] == -3, "band inset")
    assert(Rule().points[1][2] == band, "rule hangs from the band")
    assert(base.scripts == nil, "a script on Questie's frame: resize or update handler")
    assert(LiveTickers() == 0, "still polling after the build")
""")

case("questie_backdrop_is_held_invisible_and_its_state_kept", """
    local base = MakeBase()
    base:SetBackdropColor(0.2, 0.3, 0.4, 0.9)
    Load(); Fire("PLAYER_LOGIN")
    local pieces = { "Center", "TopLeftCorner", "TopRightCorner", "BottomLeftCorner", "BottomRightCorner",
        "TopEdge", "BottomEdge", "LeftEdge", "RightEdge" }
    for _, name in ipairs(pieces) do assert(base[name].alpha == 0, name .. " still visible") end
    local r, g, b, a = base:GetBackdropColor()
    assert(r == 0.2 and g == 0.3 and b == 0.4 and a == 0.9, "Questie's colour state was changed")
    base:SetBackdropColor(0.5, 0.5, 0.5, 0.6)
    local _, _, _, a2 = base:GetBackdropColor()
    assert(a2 == 0.6, "Questie's own call no longer lands")
    assert(base.Center.alpha == 0)
""")

case("a_backdrop_piece_questie_rebuilds_is_muted_on_its_next_colour_call", """
    local base = MakeBase()
    Load(); Fire("PLAYER_LOGIN")
    base.Center = New("Texture"); base.TopEdge = New("Texture")
    base:SetBackdropColor(0, 0, 0, 0.5)
    assert(base.Center.alpha == 0 and base.TopEdge.alpha == 0, "a rebuilt piece shows")
""")

case("the_panel_follows_questies_backdrop_alpha", """
    local base = MakeBase()
    Load(); Fire("PLAYER_LOGIN")
    local c = Chrome()
    local function all(a)
        for _, r in ipairs({ c.fill, c.glow, c.border, Band(), Rule() }) do
            if r.alpha ~= a then return false end
        end
        return true
    end
    base:SetBackdropColor(0, 0, 0, 0);   assert(all(0), "backdrop off: panel still shows")
    base:SetBackdropColor(0, 0, 0, 0.3); assert(all(0.3), "fade in")
    base:SetBackdropColor(0, 0, 0, 1);   assert(all(1), "fully shown")
    base:SetBackdropColor(0, 0, 0, 7);   assert(all(1), "an alpha above 1 is clamped")
    base:SetBackdropColor(0, 0, 0, -2);  assert(all(0), "an alpha below 0 is clamped")
    base:SetBackdropColor(0, 0, 0, 0.5)
    base:SetBackdropColor(0, 0, 0, nil); assert(all(0.5), "a missing alpha leaves the panel")
    base:SetBackdropColor(0, 0, 0, "x"); assert(all(0.5), "a string alpha leaves the panel")
    base:SetBackdropColor(0, 0, 0, __secret); assert(all(0.5), "a secret alpha is never read")
""")

case("the_first_state_is_read_from_the_frame", """
    local base = MakeBase()
    base:SetBackdropColor(0, 0, 0, 0.7)
    Load(); Fire("PLAYER_LOGIN")
    assert(Chrome().fill.alpha == 0.7, "got " .. tostring(Chrome().fill.alpha))
    __frames, __textures, __chrome, __hooked = {}, {}, {}, {}
    local base2 = MakeBase()
    base2:SetBackdropColor(0, 0, 0, 0)
    Load(); Fire("PLAYER_LOGIN")
    assert(Chrome().fill.alpha == 0, "a backdrop Questie keeps off starts hidden")
""")

case("the_band_sits_behind_a_header_row_at_the_top", """
    local base = MakeBase()
    local header = MakeHeader(base, 17)     -- Questie's 12pt header: 12 + 5 tall, seated 10 down
    Load(); Fire("PLAYER_LOGIN")
    base:SetBackdropColor(0, 0, 0, 1)
    local band, rule = Band(), Rule()
    assert(band.shown == true and rule.shown == true, "band hidden behind a top header")
    assert(band.h == 24, "band runs from the inset to the header's bottom: " .. tostring(band.h))
    header:SetHeight(21)                    -- a bigger header font
    base:SetBackdropColor(0, 0, 0, 1)
    assert(band.h == 28, "band did not follow the header: " .. tostring(band.h))
    header:ClearAllPoints(); header:SetPoint("BOTTOMLEFT", base, "BOTTOMLEFT", 0, 5)
    base:SetBackdropColor(0, 0, 0, 1)
    assert(band.shown == false and rule.shown == false, "band drawn with the header at the bottom")
    header:ClearAllPoints(); header:SetPoint("TOPLEFT", base, "TOPLEFT", 0, -10)
    base:SetBackdropColor(0, 0, 0, 1)
    assert(band.shown == true and rule.shown == true)
    header.shown = false
    base:SetBackdropColor(0, 0, 0, 1)
    assert(band.shown == false, "band drawn with the header hidden")
    header.shown = true
    header:ClearAllPoints(); header:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 0, -10)
    base:SetBackdropColor(0, 0, 0, 1)
    assert(band.shown == false, "band drawn for a header seated on another frame")
""")

case("no_header_frame_means_no_band", """
    local base = MakeBase()
    Load(); Fire("PLAYER_LOGIN")
    base:SetBackdropColor(0, 0, 0, 1)
    assert(Band().shown == false and Rule().shown == false)
""")

case("an_error_in_the_hook_never_reaches_questies_update", """
    local base = MakeBase()
    local header = MakeHeader(base, 17)
    Load(); Fire("PLAYER_LOGIN")
    header.GetHeight = function() error("boom") end
    base:SetBackdropColor(0.5, 0.5, 0.5, 0.6)        -- Questie's call must come back
    local _, _, _, a = base:GetBackdropColor()
    assert(a == 0.6, "Questie's own call was lost")
    assert(#__errors == 1 and tostring(__errors[1]):find("boom"), "the error was not handed on")
""")

case("a_frame_made_after_login_is_picked_up_and_the_timer_stops", """
    Load(); Fire("PLAYER_LOGIN")
    assert(#__chrome == 0 and LiveTickers() == 1, "no wait for the late frame")
    assert(__tickers[1].sec == 1 and __tickers[1].n and __tickers[1].n > 0, "timer is not bounded")
    Tick(); Tick()
    assert(#__chrome == 0 and LiveTickers() == 1)
    MakeBase()
    Tick()
    assert(#__chrome == 1, "late frame not skinned")
    assert(LiveTickers() == 0, "timer still running after the build")
""")

case("the_wait_stops_when_the_tracker_is_turned_off", """
    Load(); Fire("PLAYER_LOGIN")
    assert(LiveTickers() == 1)
    Questie.db.profile.trackerEnabled = false
    Tick()
    assert(LiveTickers() == 0 and #__chrome == 0)
    MakeBase(); Tick()
    assert(#__chrome == 0, "skinned with the tracker off")
""")

case("the_font_is_registered_under_a_neutral_name_and_questies_choice_is_left_alone", """
    Load(); Fire("ADDON_LOADED", "Questie")
    assert(#__registered == 1, "registered " .. #__registered)
    local r = __registered[1]
    assert(r[1] == "font" and r[2] == "STUwave", "name: " .. tostring(r[2]))
    assert(r[3] == FS.Theme.FONT_MONO, "path")
    assert(r[4] == LSM.LOCALE_BIT_western, "the font only has western glyphs")
    Fire("PLAYER_LOGIN")
    assert(#__registered == 1, "registered again after it took: " .. #__registered)
    assert(Questie.db.profile.trackerFontQuest == "Friz Quadrata TT", "Questie's quest font was changed")
    assert(Questie.db.profile.trackerFontHeader == "Friz Quadrata TT", "Questie's header font was changed")
""")

case("an_unknown_file_is_retried_until_the_client_knows_it", """
    __known = false
    Load(); Fire("ADDON_LOADED", "Questie")
    assert(LSM.fonts.STUwave == nil)
    __known = true
    Fire("PLAYER_LOGIN")
    assert(LSM.fonts.STUwave == FS.Theme.FONT_MONO, "never registered once the file was known")
""")

case("another_addons_load_does_not_try_the_font_again", """
    __known = false              -- every attempt is recorded, none takes
    Load()
    local tries = #__registered
    Fire("ADDON_LOADED", "SomethingElse")
    assert(#__registered == tries, "another addon's load triggered a registration")
    Fire("ADDON_LOADED", "Questie")
    assert(#__registered == tries + 1, "Questie's own load did not")
""")

case("a_missing_media_library_is_not_an_error", """
    LibStub = nil
    MakeBase()
    Load(); Fire("ADDON_LOADED", "Questie"); Fire("PLAYER_LOGIN")
    assert(#__registered == 0)
    assert(#__chrome == 1, "the panel needs no media library")
""")

case("the_target_frame_icon_is_still_moved_onto_the_stuwave_target_frame", """
    local blizz, ours = New("Frame"), New("Frame")
    ours.strata, ours.level = "LOW", 4
    TargetFrame, ForeverSTUwaveTargetFrame = blizz, ours
    local icon = New("Frame"); icon.Icon = New("Texture"); icon.level = 11; icon.parent = blizz
    blizz.children = { icon }
    Load(); Fire("PLAYER_LOGIN")
    Fire("PLAYER_TARGET_CHANGED")
    assert(icon.parent == ours, "icon not adopted")
    local p = icon.points[1]
    assert(p[1] == "RIGHT" and p[2] == ours and p[3] == "RIGHT" and p[4] == -30 and p[5] == 25, "icon offsets")
    assert(icon.level == 24 and icon.strata == "LOW")
""")


def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.globals().SRC = SRC
    try:
        rt.execute(MOCK)
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
