#!/usr/bin/env python3
"""Runs the real GunsightFrame.lua (horizon and proc rungs of the Gunsight HUD)
headless against the same mock WoW API gunsight-harness.py uses, plus the real Layout.lua,
Gunsight.lua and HudProfiles.lua.

GunsightFrame.lua draws two of the locked mockup's pieces
(mockups/gunsight-hud-v2-2026-10-02/gunsight-hud-v2-2026-10-02.html):

  * the HORIZON: hline(630, ...) split into three short segments around the character, plus the
    break ticks vline(LBRK/RBRK, 623, 637). The left segment belongs to YOU, the right one to
    TGT, the DoT one to DOT: each fades with its owner's piece key;
  * the PROC RUNGS (drawProc): a dashed post at LBRK / RBRK when idle, a solid amber post that
    grows from the horizon when lit, the run to the tape's inner edge, the end ticks, the label
    above the tape and a 16 px proc icon. Piece `prc`. A profile with no procs hides them.

  * the TARGET LAYER: with no target the tgt and dot segments (and the RBRK tick) hide; the you segment stays.

The checks pin: every geometry number the file owns is parsed back out of the mockup; each line
lands where the mockup's own arithmetic puts it at two screen heights and across a rescale;
thickness is a whole number of physical pixels when the client says what a pixel is; the horizon
segments follow YOU / TGT / DOT, the rungs follow `prc`, nothing registers a `frame` piece; the
rungs are hidden for a profile with no procs; a lit proc shows the solid post, grows over 0.3 s
and turns the label and icon edge amber; a secret icon texture is never used; and NO OnUpdate is
left running when nothing animates.

The mock is strict (a widget method it does not define fails as a nil call) and is NOT the
real client.

    python3 tools/gunsightframe-harness.py

Exit 0 = every check passed. GUNSIGHTFRAME_LUA=<path> runs another file in place of
GunsightFrame.lua.
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
sys.path.insert(0, str(HERE))
import spelltip_support as tips  # noqa: E402

_spec = importlib.util.spec_from_file_location("gunsight_harness", HERE / "gunsight-harness.py")
gh = importlib.util.module_from_spec(_spec)
sys.modules["gunsight_harness"] = gh
_spec.loader.exec_module(gh)

ADDON = HERE.parent / "forever-stuwave"
FRAME_LUA = Path(os.environ.get("GUNSIGHTFRAME_LUA") or ADDON / "Modules/CombatHud/GunsightFrame.lua")
GUNSIGHT = ADDON / "Modules/CombatHud/Gunsight.lua"
PROFILES = ADDON / "Modules/CombatHud/HudProfiles.lua"
THEME = ADDON / "Core/Theme.lua"
TOC = ADDON / "forever-stuwave.toc"
MOCKUP = gh.MOCKUP


# ---------------------------------------------------------------------------------------
# Numbers the mockup owns and GunsightFrame.lua repeats. Read, never retyped.
# ---------------------------------------------------------------------------------------

def frame_constants() -> dict:
    src = MOCKUP.read_text(encoding="utf-8")
    m = gh._m

    def g(pattern: str, what: str) -> re.Match:
        pattern = "(?s)" + pattern
        return m(pattern, src, what)

    hz = g(r"function drawYour\(vv\)\{.*?hline\(630,TL\.x1\+\d+,LBRK,K\.violet,(?P<alpha>[\d.]+)\);vline\(LBRK,(?P<y0>\d+),(?P<y1>\d+),K\.violet,(?P<talpha>[\d.]+)\)", "horizon")
    tgt_pad = g(r"hline\(630,RBRK,TR\.x0-(\d+),K\.violet", "target horizon end").group(1)
    dot_pad = g(r"hline\(630,TR\.x1\+(\d+),DOT_AX-\d+", "dot horizon start").group(1)
    idle = g(r"setLineDash\(\[(?P<dash>\d+),(?P<gap>\d+)\]\);vline\(bx,(?P<y0>\d+),(?P<y1>\d+),K\.violet,(?P<alpha>[\d.]+)\)", "idle post")
    idle_tick = g(r"hline\(566,bx,bx\+out\*(\d+),K\.violet", "idle end tick").group(1)
    run_pad = g(r"lineTo\(ia\+\(side<0\?(\d+):-\d+\),630\)", "run pad").group(1)
    lit_k = g(r"ctx\.strokeStyle=K\.amber;ctx\.lineWidth=LW\*([\d.]+);", "lit stroke width").group(1)
    label = g(r"text\(label,tcx,(?P<y>\d+),(?P<size>[\d.]+),q>\.5\?K\.amber:mix\(K\.violet,K\.white,(?P<mix>[\d.]+)\),(?P<a0>[\d.]+)\+(?P<a1>[\d.]+)\*q", "label")
    icon = g(r"var PI=(?P<pi>\d+),PC=\d+,px=tcx-label\.length\*(?P<half>[\d.]+)-PI-(?P<pad>\d+),py=(?P<py>\d+);", "proc icon")
    tex = g(r"seatIcon\(PRK\[CLS\]\[side<0\?0:1\],px,py,PI,PC,(?P<a0>[\d.]+)\+(?P<a1>[\d.]+)\*q,q<\.5\)", "proc icon texture alpha")
    g(r"var PRK=\{wl:\['trance','backlash'\],", "warlock proc pair (trance, backlash)")
    edge = g(r"A\((?P<a0>[\d.]+)\+(?P<a1>[\d.]+)\*q\);ctx\.strokeStyle=q>\.5\?K\.amber:mix\(K\.violet,K\.white,(?P<mix>[\d.]+)\)", "icon edge")
    return dict(
        HZ_ALPHA=float(hz["alpha"]), TICK_Y0=int(hz["y0"]), TICK_Y1=int(hz["y1"]), TICK_ALPHA=float(hz["talpha"]),
        HZ_TGT_PAD=int(tgt_pad), HZ_DOT_PAD_L=int(dot_pad),
        PROC_Y0=int(idle["y0"]), PROC_Y1=int(idle["y1"]), DASH=int(idle["dash"]), DASH_GAP=int(idle["gap"]),
        IDLE_ALPHA=float(idle["alpha"]), IDLE_TICK=int(idle_tick), RUN_PAD=int(run_pad), LIT_K=float(lit_k),
        LABEL_Y=int(label["y"]), LABEL_SIZE=float(label["size"]), LABEL_MIX=float(label["mix"]),
        LABEL_A0=float(label["a0"]), LABEL_A1=float(label["a1"]),
        ICON=int(icon["pi"]), ICON_Y=int(icon["py"]), ICON_PAD=int(icon["pad"]), CHAR_HALF=float(icon["half"]),
        ICON_A0=float(tex["a0"]), ICON_A1=float(tex["a1"]),
        EDGE_A0=float(edge["a0"]), EDGE_A1=float(edge["a1"]), ICON_MIX=float(edge["mix"]),
    )


# ---------------------------------------------------------------------------------------
# Extra mock on top of gunsight-harness.py's: texture and font string setters, a Theme stub,
# a controllable FS.Hud, the real HudProfiles.lua.
# ---------------------------------------------------------------------------------------

EXTRA = r"""
local FrameMT = getmetatable(UIParent)
__HOOKMOCK__
function FrameMT:GetEffectiveScale() return 1 end
-- RegisterUnitEvent: the client only delivers the event for the listed units, so fire() filters by arg 1.
function FrameMT:RegisterUnitEvent(e, ...)
    self.events[e] = true
    self.unitOnly = self.unitOnly or {}
    self.unitOnly[e] = { ... }
end
function fire(event, ...)
    local list = {}
    for _, f in ipairs(FRAMES) do
        local only = f.unitOnly and f.unitOnly[event]
        local wanted = true
        if only then
            wanted = false
            for _, u in ipairs(only) do if u == (...) then wanted = true end end
        end
        if wanted and f.events[event] and f.scripts.OnEvent then list[#list + 1] = f end
    end
    for _, f in ipairs(list) do f.scripts.OnEvent(f, event, ...) end
end
-- IsVisible is true only while every ancestor is shown (IsShown is the frame's own flag).
function FrameMT:IsVisible()
    local f = self
    while f do
        if not f.shown then return false end
        f = f.parent
    end
    return true
end

-- The client stacks a new frame one level above its parent; the shared mock leaves every frame at 1.
local baseCreateFrame = CreateFrame
function CreateFrame(kind, name, parent, template)
    local f = baseCreateFrame(kind, name, parent, template)
    if parent and parent.level then f.level = parent.level + 1 end
    return f
end

local baseTexture = FrameMT.CreateTexture
function FrameMT:CreateTexture(name, layer, template, sublevel)
    local t = baseTexture(self, name, layer)
    t.sublevel = sublevel
    function t:SetColorTexture(r, g, b, a) self.color = { r, g, b, a } end
    function t:SetTexture(p) self.tex = p end
    function t:SetVertexColor(r, g, b, a) self.vcolor = { r, g, b, a } end
    function t:SetBlendMode(m) self.blend = m end
    function t:SetTexCoord(...) self.coords = { ... } end
    function t:SetDesaturated(v) self.desat = v and true or false end
    function t:SetSnapToPixelGrid(v) self.snap = v end
    function t:SetTexelSnappingBias(v) self.bias = v end
    return t
end

local baseFontString = FrameMT.CreateFontString
function FrameMT:CreateFontString(name, layer, template)
    -- SetText / SetFormattedText stay the shared mock's, which throw "Font not set" for a FontString
    -- with no font (the client does): only GetText and the setters below are added here.
    local s = baseFontString(self, name, layer, template)
    function s:GetText() return self.text end
    function s:SetTextColor(r, g, b, a) self.tcolor = { r, g, b, a } end
    function s:SetJustifyH(j) self.justify = j end
    return s
end

-- Mock Theme: only what GunsightFrame.lua is allowed to read; theme_contract in the harness
-- checks the real Theme.lua still defines each of these names.
function MakeTheme()
    local T = {
        COLOR_BORDER = { 0.659, 0.333, 0.969, 1 },
        COLOR_AMBER = { 1, 0.7137, 0.2824, 1 },
        FLAT_TEXTURE = "flat", GLOW_EDGE_TEXTURE = "glow_edge", FONT_MONO = "mono",
        SLICE_CUT2_FILL_TEXTURE = "cut2_fill",
        THEME_CALLS = {},
    }
    function T.ApplyMono(fs, size, color)
        fs.fontSize, fs.fontColor = size, color
        fs.hasFont = true   -- the real ApplyMono calls SetFont
        T.THEME_CALLS[#T.THEME_CALLS + 1] = "ApplyMono"
    end
    function T.SnapCut(r)
        if not r or r <= 0 then return 0 end
        local best = 2
        for _, c in ipairs({ 2, 3, 4, 6 }) do if c <= r then best = c end end
        return best
    end
    function T.CutSizeIcon(h)
        local want = math.min(math.max(math.floor(h / 5), 2), 6, math.floor(h / 2))
        if want < 2 then return 0 end
        return T.SnapCut(want)
    end
    function T.Cut2ButtonSet(c)
        c = T.SnapCut(c); if c == 0 then c = 2 end
        return "outline_c" .. c, "glow_c" .. c, c
    end
    function T.ApplyNineSlice(tex, margin) tex.slice = margin; return true end
    function T.AddSliceTexture(frame, path, color, layer, sublevel, inset)
        local t = frame:CreateTexture(nil, layer or "BACKGROUND", nil, sublevel)
        t:SetTexture(path)
        t:SetPoint("TOPLEFT", frame, "TOPLEFT", inset or 0, -(inset or 0))
        t:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -(inset or 0), inset or 0)
        if color then t:SetVertexColor(color[1], color[2], color[3], color[4] or 1) end
        return t
    end
    function T.AddCut2Texture(frame, path, color, layer, sublevel, inset)
        local t = T.AddSliceTexture(frame, path, color, layer, sublevel, inset)
        T.ApplyNineSlice(t, 6)
        return t
    end
    return T
end

SECRET = setmetatable({}, { __tostring = function() return "<secret>" end })
SPELL_TEXTURES = {}
C_Spell = { GetSpellTexture = function(id) return SPELL_TEXTURES[id] end }

HUD_SUBS = {}
function MakeHud(profileToken)
    local Hud = { state = { active = false, row = {}, buffsMissing = {}, procs = {} } }
    function Hud.Subscribe(fn)
        HUD_SUBS[#HUD_SUBS + 1] = fn
        fn(Hud.state)
        return fn
    end
    function Hud.GetProfile() return Hud.profile end
    Hud.profile = profileToken and FS.HudProfiles[profileToken] or nil
    return Hud
end

-- A state shaped like HudLogic's: procs sorted by key, { key, glow, active }.
function StateFor(profile, active)
    local st = { active = profile ~= nil, row = {}, buffsMissing = {}, procs = {} }
    local keys = {}
    for k in pairs(profile and profile.procs or {}) do keys[#keys + 1] = k end
    table.sort(keys)
    for _, k in ipairs(keys) do
        st.procs[#st.procs + 1] = { key = k, glow = profile.procs[k].glow, active = active and active[k] or false }
    end
    return st
end
function Push(state)
    FS.Hud.state = state
    for _, fn in ipairs(HUD_SUBS) do fn(state) end
end
function OnUpdates()
    local n = 0
    for _, f in ipairs(FRAMES) do if f.scripts.OnUpdate then n = n + 1 end end
    return n
end
function RunUpdate(f, elapsed)
    local fn = f.scripts.OnUpdate
    check(fn, "no OnUpdate is running on " .. tostring(f.name))
    fn(f, elapsed)
end
function FramesNamed(prefix)
    local n = 0
    for _, f in ipairs(FRAMES) do if f.name and f.name:sub(1, #prefix) == prefix then n = n + 1 end end
    return n
end
"""

EXTRA = EXTRA.replace("__HOOKMOCK__", tips.HOOK_MOCK.format(cls="FrameMT")) + tips.LUA

PRELUDE = r"""
local function boot(opts)
    opts = opts or {}
    SetScreen(opts.height or 1440)
    ForeverSTUwaveDB = opts.db or {}
    HUD_SUBS = {}
    if opts.pixel then
        PixelUtil = { GetPixelToUIUnitFactor = function() return 768 / opts.pixel end }
    else
        PixelUtil = nil
    end
    -- (not `opts.noTheme and nil or MakeTheme()`: that always yields MakeTheme(), `and nil` is falsy)
    if opts.noTheme then FS.Theme = nil else FS.Theme = MakeTheme() end
    if opts.themeHook and FS.Theme then opts.themeHook(FS.Theme) end
    FS.IsSecret = function(v) return v == SECRET end
    loadSpellTips(HELPERS_SRC)
    assert(loadstring(HAS_TARGET_SRC, "@Theme.lua"))()      -- the real FS.HasTarget / FS.TargetTakesDots out of Theme.lua
    loadAddonFile(LAYOUT_SRC, "Core/Layout.lua")
    loadAddonFile(CONFIG_SRC, "Core/Config.lua")
    loadAddonFile(GUNSIGHT_SRC, "Modules/CombatHud/Gunsight.lua")
    loadAddonFile(PROFILES_SRC, "Modules/CombatHud/HudProfiles.lua")
    if not opts.noHud then
        FS.Hud = MakeHud(opts.profile)
        if opts.state then FS.Hud.state = opts.state(FS.Hud.profile) end
    else
        FS.Hud = nil
    end
    loadAddonFile(FRAME_SRC, "Modules/CombatHud/GunsightFrame.lua")
    fire("ADDON_LOADED", "forever-stuwave")
    fire("PLAYER_LOGIN")
    return FS.GunsightFrame, FS.Gunsight
end

-- Image px to UI units / UI coordinates from the UIParent centre, straight from the mockup's
-- canvas centre (the root is the character centre; no root arithmetic is repeated here).
local function mk(height)
    local gridUi = 1.28 * height / 1440
    return {
        grid = gridUi,
        x = function(ix) return (ix - MU.W / 2) * gridUi end,
        y = function(iy) return -(iy - MU.H / 2) * gridUi end,
        ui = function(v) return v * gridUi end,
    }
end
local function eq(a, b, what) near(a, b, what) end
-- centre x / y of a region
local function cx(f) return (centerOf(f)) end
local function cy(f) local _, y = centerOf(f); return y end
local function edges(f)
    local l, b, w, h = rect(f)
    return l, l + w, b + h, b      -- left, right, top, bottom
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str):
    def deco(body: str):
        CASES.append((name, body))
        return body
    return deco


# ---------------------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------------------

case("constants_match_the_mockup")(r"""
local GF = boot({ profile = "WARLOCK" })
local C = GF.C
check(type(C) == "table", "FS.GunsightFrame.C (the constants table) is missing")
local function same(k) near(C[k], FC[k], k .. " (GunsightFrame has " .. tostring(C[k]) .. ", mockup has " .. tostring(FC[k]) .. ")") end
for k in pairs(FC) do same(k) end
""")

# ---------------------------------------------------------------------------------------
# Horizon
# ---------------------------------------------------------------------------------------

LAYOUT_CHECK = r"""
local function layoutChecks(GF, H)
    local m = mk(H)
    local T = m.ui(1)
    local G = FS.Gunsight.G
    local hz = GF.horizon
    check(hz and hz.you and hz.tgt and hz.dot, "horizon.you / tgt / dot are missing")
    local function seg(part, x0, x1, what)
        local l, r, top, bot = edges(part.segment)
        near(l, m.x(x0), what .. " segment left"); near(r, m.x(x1), what .. " segment right")
        near((top + bot) / 2, m.y(MU.CY), what .. " segment sits on the horizon y")
        near(top - bot, T, what .. " segment is one line wide")
    end
    local function tick(part, ix, what)
        local l, r, top, bot = edges(part.tick)
        near((l + r) / 2, m.x(ix), what .. " tick x"); near(r - l, T, what .. " tick width")
        near(top, m.y(FC.TICK_Y0), what .. " tick top"); near(bot, m.y(FC.TICK_Y1), what .. " tick bottom")
    end
    seg(hz.you, G.TL.x1 + G.HZ_PAD_L, G.LBRK, "you");   tick(hz.you, G.LBRK, "you")
    seg(hz.tgt, G.RBRK, G.TR.x0 - FC.HZ_TGT_PAD, "tgt"); tick(hz.tgt, G.RBRK, "tgt")
    seg(hz.dot, G.TR.x1 + FC.HZ_DOT_PAD_L, G.DOT_AX - G.HZ_PAD_R, "dot")
    check(hz.dot.tick == nil, "the DoT segment has no break tick in the mockup")
end
"""

case("horizon_lands_where_the_mockup_says")(LAYOUT_CHECK + r"""
local GF = boot({ profile = "WARLOCK", height = 1440 })
layoutChecks(GF, 1440)
""")

case("layout_at_1200")(LAYOUT_CHECK + r"""
local GF = boot({ profile = "WARLOCK", height = 1200 })
layoutChecks(GF, 1200)
""")

case("layout_follows_a_rescale")(LAYOUT_CHECK + r"""
local GF = boot({ profile = "WARLOCK", height = 1440 })
layoutChecks(GF, 1440)
SetScreen(1200); fire("UI_SCALE_CHANGED")
layoutChecks(GF, 1200)
SetScreen(1080); fire("DISPLAY_SIZE_CHANGED")
layoutChecks(GF, 1080)
""")

case("lines_are_whole_physical_pixels_when_the_client_says_so")(r"""
local GF = boot({ profile = "WARLOCK", height = 1440, pixel = 1440 })
local px = 768 / 1440
local want = math.floor(1.28 / px + 0.5) * px            -- ui(1) rounded to whole pixels
local function whole(v, what)
    local n = v / px
    check(math.abs(n - math.floor(n + 0.5)) < 1e-6 and n > 0.5, what .. " is not a whole number of physical pixels (" .. n .. ")")
end
local _, _, w, h = rect(GF.horizon.you.segment)
near(h, want, "horizon thickness is ui(1) snapped"); whole(h, "horizon thickness")
local _, _, tw = rect(GF.horizon.you.tick); whole(tw, "tick width")
-- the thinnest a line may get is one pixel, however small the scale
SetScreen(240); fire("UI_SCALE_CHANGED")
local _, _, _, h2 = rect(GF.horizon.you.segment)
check(h2 >= px - 1e-6, "a line thinner than one physical pixel: " .. h2)
-- a lit rung's thicker stroke snaps too
Push(StateFor(FS.Hud.profile, { shadow_trance = true }))
for _, d in ipairs({ 0.4 }) do if OnUpdates() > 0 then for _, f in ipairs(FRAMES) do if f.scripts.OnUpdate then f.scripts.OnUpdate(f, d) end end end end
local post = GF.rungs.left.lit.post
local _, _, pw = rect(post); whole(pw, "lit post width")
""")

case("lines_use_the_ui_size_without_a_pixel_api")(r"""
local GF = boot({ profile = "WARLOCK", height = 1440 })
local _, _, _, h = rect(GF.horizon.you.segment)
near(h, FS.Gunsight.ui(1), "no pixel API: thickness is ui(1), never zero")
""")

case("horizon_segments_follow_their_owner_keys")(r"""
local GF, Gs = boot({ profile = "WARLOCK" })
local hz = GF.horizon
for _, k in ipairs({ "you", "tgt", "dot" }) do
    check(hz[k].frame:IsShown() and hz[k].frame:GetAlpha() == 1, k .. " segment should start on")
end
Gs.SetPiece("you", false)
check(Gs.IsPieceOn("you") == false, "SetPiece did not take")
check(hz.you.frame:IsShown(), "the segment fades, it does not vanish at once")
local g = hz.you.frame.groups and hz.you.frame.groups[1]
check(g and g.playing, "the segment fade must run as an AnimationGroup")
finishAnims()
check(not hz.you.frame:IsShown() and hz.you.frame:GetAlpha() == 0, "YOU off must hide the left segment")
check(hz.tgt.frame:IsShown() and hz.dot.frame:IsShown(), "YOU off must not touch the other segments")
Gs.SetPiece("tgt", false); finishAnims()
check(not hz.tgt.frame:IsShown() and hz.dot.frame:IsShown(), "TGT off hides only the right segment")
Gs.SetPiece("dot", false); finishAnims()
check(not hz.dot.frame:IsShown(), "DOT off hides the DoT segment")
Gs.SetPiece("you", true); finishAnims()
check(hz.you.frame:IsShown() and hz.you.frame:GetAlpha() == 1, "YOU back on shows the segment at alpha 1")
-- a flip mid fade lands in the CURRENT state
Gs.SetPiece("you", false); Gs.SetPiece("you", true); finishAnims()
check(hz.you.frame:IsShown() and hz.you.frame:GetAlpha() == 1, "an off then on mid fade must end on")
Gs.SetPiece("you", false); Gs.SetPiece("you", true); Gs.SetPiece("you", false); finishAnims()
check(not hz.you.frame:IsShown(), "on, off, on, off must end off")
-- unrelated keys never touch the horizon
Gs.SetPiece("tgt", true); Gs.SetPiece("dot", true); finishAnims()
check(hz.tgt.frame:IsShown() and hz.dot.frame:IsShown(), "TGT and DOT back on")
Gs.SetPiece("shard", false); Gs.SetPiece("buff", false); finishAnims()
check(hz.tgt.frame:IsShown() and hz.dot.frame:IsShown(), "unrelated pieces must not move the horizon")
""")

case("horizon_fade_lands_at_once_under_a_hidden_root")(r"""
-- an animation group never plays on a frame that is not visible, so OnFinished never fires: the
-- off segment would keep alpha 1 and the on segment would stay at alpha 0.
local GF, Gs = boot({ profile = "WARLOCK" })
local hz = GF.horizon
Gs.root:Hide()
check(not hz.you.frame:IsVisible() and hz.you.frame:IsShown(), "setup: shown segment under a hidden root")
Gs.SetPiece("you", false)
check(not hz.you.frame:IsShown(), "off under a hidden root hides at once")
near(hz.you.frame:GetAlpha(), 0, "off alpha under a hidden root")
Gs.SetPiece("you", true)
check(hz.you.frame:IsShown(), "on under a hidden root shows at once")
near(hz.you.frame:GetAlpha(), 1, "on alpha is not stranded at 0")
for _, grp in ipairs(hz.you.frame.groups or {}) do check(not grp.playing, "no fade is left playing") end
Gs.root:Show()
check(hz.you.frame:IsVisible() and hz.you.frame:GetAlpha() == 1, "visible at full alpha once the root shows")
""")

case("horizon_fade_starts_from_the_current_alpha")(r"""
local GF, Gs = boot({ profile = "WARLOCK" })
local f = GF.horizon.tgt.frame
Gs.SetPiece("tgt", false)                   -- fade out starts
f:SetAlpha(0.4)                             -- the fade is 40% up when the user flips back
Gs.SetPiece("tgt", true)
local g
for _, grp in ipairs(f.groups or {}) do if grp.playing then g = grp end end
check(g, "fade in is not playing")
near(g.anims[1].from, 0.4, "fade in starts from the current alpha")
near(g.anims[1].to, 1, "fade in to")
near(f:GetAlpha(), 0.4, "the flip must not snap alpha before the fade")
Gs.SetPiece("tgt", false)
near(g.anims[1].from, 0.4, "fade out starts from the current alpha")
near(g.anims[1].to, 0, "fade out to")
finishAnims()
check(not f:IsShown(), "ended off")
""")

# ---------------------------------------------------------------------------------------
# Target layer: with no target the target side of the horizon (tgt segment + its right break tick,
# dot segment) hides. A separate layer from the piece toggles (visible = piece on AND has target).
# ---------------------------------------------------------------------------------------

TARGET_LAYER_PRELUDE = r"""
HAS = true
UnitExists = function(unit) check(unit == "target", "UnitExists asked about " .. tostring(unit)); return HAS end
-- a region draws only while it and every ancestor frame is shown
local function drawn(r)
    while r do
        if r.shown == false then return false end
        r = r.parent
    end
    return true
end
local function targetSideDrawn(hz)
    return drawn(hz.tgt.segment) or drawn(hz.tgt.tick) or drawn(hz.dot.segment)
end
local function targetSideAllDrawn(hz)
    return drawn(hz.tgt.segment) and drawn(hz.tgt.tick) and drawn(hz.dot.segment)
end
"""

case("target_side_horizon_hides_with_no_target")(TARGET_LAYER_PRELUDE + r"""
HAS = false
local GF = boot({ profile = "WARLOCK" })
local hz = GF.horizon
check(not targetSideDrawn(hz), "no target at build: tgt segment, its RBRK tick and the dot segment must not draw")
check(hz.tgt.gate and hz.dot.gate, "the target side parts expose their gate")
check(hz.you.gate == nil, "the you segment has no target gate")
for _, k in ipairs({ "tgt", "dot" }) do
    local part = hz[k]
    check(part.gate:GetFrameLevel() == part.frame:GetFrameLevel(),
        k .. ": the gate takes the part frame's level (no extra stacking level)")
    check(part.segment:GetParent() == part.gate
        and part.segment:GetParent():GetFrameLevel() == part.frame:GetFrameLevel(),
        k .. ": the gated segment draws at the level it had on the part frame")
end
check(hz.tgt.tick:GetParent():GetFrameLevel() == hz.tgt.frame:GetFrameLevel(),
    "the gated RBRK tick keeps the part frame's level")
check(hz.tgt.frame:GetFrameLevel() == FS.Gunsight.root:GetFrameLevel() + 1,
    "the part frame is one above the root, as before the gate")
check(drawn(hz.you.segment) and drawn(hz.you.tick), "the you segment and its LBRK tick stay drawn with no target")
HAS = true; fire("PLAYER_TARGET_CHANGED")
check(targetSideAllDrawn(hz), "a target shows the tgt segment, its tick and the dot segment")
HAS = false; fire("PLAYER_TARGET_CHANGED")
check(not targetSideDrawn(hz), "target gone: hidden again")
HAS = true; fire("PLAYER_ENTERING_WORLD")
check(targetSideAllDrawn(hz), "PLAYER_ENTERING_WORLD re-reads the target (shown)")
HAS = false; fire("PLAYER_ENTERING_WORLD")
check(not targetSideDrawn(hz), "PLAYER_ENTERING_WORLD re-reads the target (hidden)")
check(drawn(hz.you.segment) and drawn(hz.you.tick), "you segment unaffected throughout")
""")

case("target_gates_are_written_only_when_their_answer_changes")(TARGET_LAYER_PRELUDE + r"""
HAS = false
local GF = boot({ profile = "WARLOCK" })
local hz = GF.horizon
local function writes(k) return (hz[k].gate.calls.Show or 0) + (hz[k].gate.calls.Hide or 0) end
local base = { tgt = writes("tgt"), dot = writes("dot") }
check(not targetSideDrawn(hz), "setup: no target, hidden")
fire("PLAYER_TARGET_CHANGED"); fire("UNIT_HEALTH", "target"); fire("UNIT_HEALTH", "target")
check(writes("tgt") == base.tgt and writes("dot") == base.dot,
    "an unchanged hidden answer writes no gate: tgt +" .. (writes("tgt") - base.tgt) .. ", dot +" .. (writes("dot") - base.dot))
HAS = true; fire("PLAYER_TARGET_CHANGED")
check(targetSideAllDrawn(hz), "a target shows the side")
local shown = { tgt = writes("tgt"), dot = writes("dot") }
check(shown.tgt == base.tgt + 1 and shown.dot == base.dot + 1, "a changed answer is written exactly once per gate")
fire("PLAYER_TARGET_CHANGED"); fire("UNIT_HEALTH", "target"); fire("UNIT_HEALTH", "target")
check(writes("tgt") == shown.tgt and writes("dot") == shown.dot,
    "an unchanged shown answer writes no gate: tgt +" .. (writes("tgt") - shown.tgt) .. ", dot +" .. (writes("dot") - shown.dot))
""")

case("target_layer_composes_with_the_piece_toggles")(TARGET_LAYER_PRELUDE + r"""
local GF, Gs = boot({ profile = "WARLOCK" })
local hz = GF.horizon
HAS = true; fire("PLAYER_TARGET_CHANGED")
Gs.SetPiece("tgt", false); finishAnims()
check(not drawn(hz.tgt.segment) and not drawn(hz.tgt.tick), "piece off with a target stays off")
check(drawn(hz.dot.segment), "TGT off leaves the dot segment alone")
Gs.SetPiece("dot", false); finishAnims()
check(not drawn(hz.dot.segment), "DOT off with a target stays off")
HAS = false; fire("PLAYER_TARGET_CHANGED")
Gs.SetPiece("tgt", true); Gs.SetPiece("dot", true); finishAnims()
check(not targetSideDrawn(hz), "piece back on with no target stays hidden")
HAS = true; fire("PLAYER_TARGET_CHANGED")
check(targetSideAllDrawn(hz), "piece on and a target: drawn")
check(hz.tgt.frame:GetAlpha() == 1 and hz.dot.frame:GetAlpha() == 1, "the piece fade still lands at alpha 1")
-- the target flipping never touches the piece (it is the user's setting, not this layer's)
Gs.SetPiece("tgt", false); finishAnims()
HAS = false; fire("PLAYER_TARGET_CHANGED"); HAS = true; fire("PLAYER_TARGET_CHANGED")
check(Gs.IsPieceOn("tgt") == false and not drawn(hz.tgt.segment), "a target change never re-shows a piece that is off")
check(drawn(hz.you.segment), "you untouched")
""")

case("target_layer_secret_unitexists_keeps_shown")(TARGET_LAYER_PRELUDE + r"""
HAS = false
local GF = boot({ profile = "WARLOCK" })
local hz = GF.horizon
check(not targetSideDrawn(hz), "setup: hidden")
-- the mock calls the plain false UnitExists returns "secret": a truth test would keep it hidden (the rule
-- itself is pinned once in theme-harness.py; this proves the horizon goes through it)
FS.IsSecret = function(v) return v == false end
fire("PLAYER_TARGET_CHANGED")
check(targetSideAllDrawn(hz), "a value IsSecret flags keeps the target side shown (never truth-tested)")
""")

case("the_dot_segment_hides_for_a_friendly_target_but_the_target_tape_side_stays")(TARGET_LAYER_PRELUDE + r"""
-- The scale (GunsightDots) hides for a target no DoT can be on; the dot segment that leads into it must follow,
-- while the tgt segment and its tick belong to the target's cast tape and only need a target.
ATTACK = true
UnitCanAttack = function(a, b)
    check(a == "player" and b == "target", "UnitCanAttack asked about " .. tostring(a) .. ", " .. tostring(b))
    return ATTACK
end
local GF = boot({ profile = "WARLOCK" })
local hz = GF.horizon
check(targetSideAllDrawn(hz), "setup: an attackable target draws all three")
ATTACK = false; fire("PLAYER_TARGET_CHANGED")
check(not drawn(hz.dot.segment), "a friendly target: the dot segment is hidden with the scale")
check(drawn(hz.tgt.segment) and drawn(hz.tgt.tick), "the tgt segment and its tick still draw for a friendly target")
ATTACK = true; fire("PLAYER_TARGET_CHANGED")
check(targetSideAllDrawn(hz), "an attackable target again: the dot segment is back")
-- a duel or mind control flips attackability with no target change
ATTACK = false; fire("UNIT_FACTION", "target")
check(not drawn(hz.dot.segment), "UNIT_FACTION on the target re-reads attackability")
ATTACK = true; fire("UNIT_FLAGS", "target")
check(drawn(hz.dot.segment), "UNIT_FLAGS on the target re-reads attackability")
ATTACK = false; fire("PLAYER_ENTERING_WORLD")
check(not drawn(hz.dot.segment), "PLAYER_ENTERING_WORLD re-reads it too")
-- and the piece toggle stays the user's: the dot piece is never touched by this layer
check(FS.Gunsight.IsPieceOn("dot"), "the dot piece is still on")
""")

case("the_dot_segment_hides_for_a_dead_target_or_ghost_and_the_events_are_target_only")(TARGET_LAYER_PRELUDE + r"""
DEAD, GHOST = false, false
UnitIsDeadOrGhost = function(unit) check(unit == "target", "UnitIsDeadOrGhost asked about " .. tostring(unit)); return DEAD or GHOST end
UnitCanAttack = function() return true end
local GF = boot({ profile = "WARLOCK" })
local hz = GF.horizon
check(targetSideAllDrawn(hz), "setup: a live target draws all three")
DEAD = true; fire("UNIT_HEALTH", "target")
check(not drawn(hz.dot.segment), "the target died: the dot segment is hidden")
check(drawn(hz.tgt.segment) and drawn(hz.tgt.tick), "the tgt side still draws for a corpse (the tape needs only a target)")
DEAD = false; fire("UNIT_HEALTH", "target")
check(drawn(hz.dot.segment), "alive again: back")
GHOST = true; fire("PLAYER_TARGET_CHANGED")
check(not drawn(hz.dot.segment), "an enemy ghost counts as dead")
GHOST = false; fire("PLAYER_TARGET_CHANGED")
check(drawn(hz.dot.segment), "a live target again: back")
-- the unit events are for the target only (no all-units UNIT_HEALTH spam)
for _, name in ipairs({ "UNIT_HEALTH", "UNIT_FLAGS", "UNIT_FACTION" }) do
    local only
    for _, f in ipairs(FRAMES) do
        if f.events[name] then only = f.unitOnly and f.unitOnly[name] end
    end
    check(only and #only == 1 and only[1] == "target", name .. " is registered for the target unit only")
end
-- another unit's health never re-reads the layer
DEAD = true; fire("UNIT_HEALTH", "party1")
check(drawn(hz.dot.segment), "UNIT_HEALTH for another unit is not delivered")
""")

case("an_unreadable_target_flag_keeps_the_dot_segment_shown")(TARGET_LAYER_PRELUDE + r"""
UnitCanAttack = function() return false end
UnitIsDeadOrGhost = function() return true end
local GF = boot({ profile = "WARLOCK" })
local hz = GF.horizon
check(not drawn(hz.dot.segment), "setup: plain friendly and dead answers hide it")
-- a secret answer (FS.IsSecret, checked before anything touches the value) reads as "can take a DoT"
FS.IsSecret = function(v) return v == false or v == true end
fire("PLAYER_TARGET_CHANGED")
check(drawn(hz.dot.segment), "secret answers keep the dot segment shown")
FS.IsSecret = function() return false end
UnitCanAttack = function() error("hidden API") end
UnitIsDeadOrGhost = function() return "odd" end
fire("PLAYER_TARGET_CHANGED")
check(drawn(hz.dot.segment), "a throwing or odd answer keeps it shown")
""")

case("target_layer_in_combat_rescale_and_no_onupdate")(TARGET_LAYER_PRELUDE + r"""
HAS = true
local GF = boot({ profile = "WARLOCK" })
local hz = GF.horizon
IN_COMBAT = true
HAS = false; fire("PLAYER_TARGET_CHANGED")
check(not targetSideDrawn(hz), "hides in combat")
HAS = true; fire("PLAYER_TARGET_CHANGED")
check(targetSideAllDrawn(hz), "shows in combat")
check(#BLOCKED == 0, "Show/Hide in combat touched a protected frame")
HAS = false; fire("PLAYER_TARGET_CHANGED")
local shows = { tgt = hz.tgt.gate.calls.Show or 0, dot = hz.dot.gate.calls.Show or 0 }
SetScreen(1200); fire("UI_SCALE_CHANGED")
SetScreen(1080); fire("DISPLAY_SIZE_CHANGED")
check(not targetSideDrawn(hz), "a rescale never re-shows a hidden target side")
check((hz.tgt.gate.calls.Show or 0) == shows.tgt and (hz.dot.gate.calls.Show or 0) == shows.dot,
    "a rescale never calls Show on a gate")
IN_COMBAT = false
check(OnUpdates() == 0, "the target layer adds no OnUpdate, found " .. OnUpdates())
""")

case("horizon_starts_in_the_saved_state")(r"""
local db = { gunsight = { pieces = { you = false, dot = false } } }
local GF = boot({ profile = "WARLOCK", db = db })
check(not GF.horizon.you.frame:IsShown(), "saved YOU off: the left segment must start hidden")
check(GF.horizon.tgt.frame:IsShown(), "saved TGT on: the right segment must start shown")
check(not GF.horizon.dot.frame:IsShown(), "saved DOT off: the DoT segment must start hidden")
""")

# ---------------------------------------------------------------------------------------
# No HUD Frame
# ---------------------------------------------------------------------------------------

case("the_hud_frame_is_gone")(r"""
local GF, Gs = boot({ profile = "WARLOCK" })
check(GF.brackets == nil, "the corner brackets are gone (no FS.GunsightFrame.brackets)")
check(FC.BRK_ARM == nil and GF.C.BRK_ARM == nil, "no bracket constants")
check(Gs.anchors.frame == nil, "the bracket box anchor is gone")
for _, f in ipairs(FRAMES) do
    check(not (f.name and f.name:find("brackets", 1, true)), "a brackets frame exists: " .. tostring(f.name))
end
-- a saved value for the retired piece does not break the build and registers nothing
local GF2, Gs2 = boot({ profile = "WARLOCK", db = { gunsight = { pieces = { frame = false } } } })
check(GF2.horizon.you.frame:IsShown(), "a stale saved frame value must not disturb the rest")
""")

# ---------------------------------------------------------------------------------------
# Rungs
# ---------------------------------------------------------------------------------------

case("rungs_are_hidden_for_a_profile_without_procs")(r"""
local GF, Gs = boot({ profile = "PRIEST", state = function(p) return StateFor(p) end })
check(GF.rungs.left.frame:IsShown() == false and GF.rungs.right.frame:IsShown() == false,
    "a priest has no procs: both rungs must be hidden")
check(GF.prc ~= nil, "the prc container must still exist")
Push(StateFor(FS.Hud.profile, {}))
check(not GF.rungs.left.frame:IsShown() and not GF.rungs.right.frame:IsShown(), "still hidden after a push")
""")

case("class_without_a_profile_has_no_proc_rungs_and_no_error")(r"""
-- HudProfiles has no ROGUE entry: the Hud resolves no profile and pushes an inactive state
local GF = boot({ profile = "ROGUE", state = function(p) return StateFor(p) end })
check(FS.Hud.profile == nil, "setup: ROGUE resolves to no profile")
check(not GF.rungs.left.frame:IsShown() and not GF.rungs.right.frame:IsShown(), "a rogue has no procs: both rungs hidden")
Push(StateFor(nil, {}))
Push({ active = false, row = {}, buffsMissing = {}, procs = {} })
check(not GF.rungs.left.frame:IsShown() and not GF.rungs.right.frame:IsShown(), "still hidden after pushes")
check(GF.horizon.you.frame:IsShown(), "the horizon still draws")
check(OnUpdates() == 0, "nothing animates")
""")

case("paladin_ready_rungs_take_the_spell_icon_from_the_state")(r"""
-- Holy Strike (left) and Judgement (right) are `ready` procs: no aura, so the icon is the spell icon
-- HudLogic puts on the state entry. A secret or missing one falls back to the two letters.
local GF = boot({ profile = "PALADIN", state = function(p) return StateFor(p, {}) end })
check(FS.Hud.profile ~= nil and FS.Hud.profile.procs.hs.ready == "hs", "setup: the paladin profile is loaded")
local function procs(hsIcon, jdIcon, hsOn)
    return { active = true, row = {}, buffsMissing = {}, procs = {
        { key = "hs", glow = "gold", active = hsOn, icon = hsIcon },
        { key = "jd", glow = "gold", active = true, icon = jdIcon },
    } }
end
Push(procs(135971, 135959, true))
local L, R = GF.rungs.left, GF.rungs.right
check(L.frame:IsShown() and R.frame:IsShown(), "both rungs bound")
check(L.key == "hs" and R.key == "jd", "Holy Strike left, Judgement right")
check(L.icon.tex.tex == 135971 and R.icon.tex.tex == 135959, "icons come from the state entry")
check(L.icon.tex:IsShown() and not L.icon.fallback:IsShown(), "a real texture hides the abbreviation")
Push(procs(135971, 135959, false))
check(L.target == 0 and R.target ~= 0, "Holy Strike on cooldown aims its rung down, Judgement stays up")
check(L.icon.tex.tex == 135971, "the icon survives the rung going dark")
local GF2 = boot({ profile = "PALADIN", state = function(p) return StateFor(p, {}) end })
Push(procs(SECRET, nil, true))
check(GF2.rungs.left.icon.tex.tex ~= SECRET, "a secret icon never reaches SetTexture")
check(GF2.rungs.left.icon.fallback:IsShown() and GF2.rungs.left.icon.fallback:GetText() == "HO", "secret icon: the two letter fallback")
check(GF2.rungs.right.icon.fallback:IsShown() and GF2.rungs.right.icon.fallback:GetText() == "JU", "no icon: the two letter fallback")
Push({ active = true, row = {}, buffsMissing = {}, procs = { { key = "jd", glow = "gold", active = true, icon = 135959 } } })
check(not GF2.rungs.left.frame:IsShown(), "an unknown spell sends no entry, so its rung hides")
""")

case("a_proc_rung_icon_shows_its_spell_on_hover")(r"""
-- Shadow Trance is an aura proc (spec.aura is the spell id); Judgement is a `ready` proc (the id comes from its name).
local GF = boot({ profile = "WARLOCK", state = function(p) return StateFor(p, {}) end })
Push(StateFor(FS.Hud.profile, { shadow_trance = true }))
local rung = GF.rungs[FS.Hud.profile.procs.shadow_trance.side]
check(hoverOnly(rung.icon.frame), "the icon is motion only and never click enabled")
hover(rung.icon.frame)
check(tip() and tip().spellID == 17941 and GameTooltip.setOwner == 1, "the aura proc shows spell 17941 once, got " .. tostring(tip() and tip().spellID))
unhover(rung.icon.frame)
FS.Gunsight.IsActive = function() return false end
hover(rung.icon.frame)
check(tip() == nil, "an inactive Gunsight shows no tooltip")

local GF2 = boot({ profile = "PALADIN", state = function(p) return StateFor(p, {}) end })
FS.HudSpells = { hs = { names = { "Holy Strike" } }, jd = { names = { "Judgement" } } }
C_Spell.GetSpellInfo = function(n) return { spellID = ({ ["Holy Strike"] = 20473, Judgement = 20271 })[n] } end
Push({ active = true, row = {}, buffsMissing = {}, procs = {
    { key = "hs", glow = "gold", active = false, icon = 135971 }, { key = "jd", glow = "gold", active = true, icon = 135959 } } })
local L, R = GF2.rungs.left, GF2.rungs.right
hover(R.icon.frame)
check(tip() and tip().spellID == 20271, "a ready proc resolves its spell by name: " .. tostring(tip() and tip().spellID))
unhover(R.icon.frame)
check(not L.frame:IsShown(), "setup: the dark rung is hidden")
FS.Gunsight.IsActive = function() return true end
hover(L.icon.frame)
check(tip() == nil, "a hidden rung gives no tooltip")
""")


case("a_proc_rung_tooltip_already_up_comes_down_when_the_master_switch_goes_off_in_combat")(r"""
local GF = boot({ profile = "WARLOCK", state = function(p) return StateFor(p, {}) end })
Push(StateFor(FS.Hud.profile, { shadow_trance = true }))
local rung = GF.rungs[FS.Hud.profile.procs.shadow_trance.side]
hover(rung.icon.frame)
check(tip() and tip().spellID == 17941, "setup: the tip is up")
FS.Config.Set("gunsight.enabled", false)
check(FS.Gunsight.IsActive() == false and tip() == nil, "the open tooltip comes down with the switch")
""")


case("rungs_are_hidden_with_no_hud_at_all")(r"""
local GF = boot({ noHud = true })
check(not GF.rungs.left.frame:IsShown() and not GF.rungs.right.frame:IsShown(), "no FS.Hud: no rungs")
check(GF.horizon.you.frame:IsShown(), "the horizon does not need FS.Hud")
""")

case("rungs_are_hidden_with_an_inactive_hud")(r"""
local GF = boot({ profile = "WARLOCK", state = function() return { active = false, row = {}, buffsMissing = {}, procs = {} } end })
check(not GF.rungs.left.frame:IsShown() and not GF.rungs.right.frame:IsShown(), "an empty procs list hides the rungs")
Push(StateFor(FS.Hud.profile, {}))
check(not GF.rungs.left.frame:IsShown() and not GF.rungs.right.frame:IsShown(), "procs the Hud lists but are all idle stay hidden")
Push(StateFor(FS.Hud.profile, { shadow_trance = true, decimation = true }))
check(GF.rungs.left.frame:IsShown() and GF.rungs.right.frame:IsShown(), "rungs appear when their procs are active")
Push({ active = false, row = {}, buffsMissing = {}, procs = {} })
check(not GF.rungs.left.frame:IsShown() and not GF.rungs.right.frame:IsShown(), "and go again when it empties")
""")

case("profile_data_carries_the_rung_label_and_side")(r"""
boot({ profile = "WARLOCK" })
local p = FS.HudProfiles.WARLOCK.procs
check(p.shadow_trance.side == "left" and p.shadow_trance.label == "TRANCE", "Nightfall is the left rung, TRANCE")
check(p.decimation.side == "right" and type(p.decimation.label) == "string" and p.decimation.label ~= "", "Decimation is the right rung")
check(next(FS.HudProfiles.PRIEST.procs) == nil, "the priest profile has no procs")
for k, spec in pairs(p) do
    check(spec.side == "left" or spec.side == "right", k .. ": side must be left or right")
end
""")

case("idle_rungs_are_dashed_posts")(r"""
local H = 1440
local m = mk(H)
local GF = boot({ profile = "WARLOCK", height = H, state = function(p) return StateFor(p, {}) end })
local G = FS.Gunsight.G
local T = m.ui(1)
for side, bx in pairs({ left = G.LBRK, right = G.RBRK }) do
    local r = GF.rungs[side]
    check(not r.frame:IsShown(), side .. ": an idle rung is hidden until its proc is active")
    check(r.key ~= nil and r.labelText ~= nil, side .. ": the rung is still bound and seated while hidden")
    check(not r.lit.frame:IsShown(), side .. ": the solid post is for the lit state only")
    local want = math.floor((FC.PROC_Y1 - FC.PROC_Y0) / (FC.DASH + FC.DASH_GAP)) + 1
    check(#r.dashes == want, side .. ": want " .. want .. " dashes, have " .. #r.dashes)
    for k, d in ipairs(r.dashes) do
        local start = FC.PROC_Y0 + (k - 1) * (FC.DASH + FC.DASH_GAP)
        local len = math.min(FC.DASH, FC.PROC_Y1 - start)
        local l, rr, top, bot = edges(d)
        near((l + rr) / 2, m.x(bx), side .. " dash " .. k .. " x"); near(rr - l, T, side .. " dash width")
        near(top, m.y(start), side .. " dash " .. k .. " top"); near(top - bot, m.ui(len), side .. " dash " .. k .. " length")
        near(d.color[4], FC.IDLE_ALPHA, "dash alpha")
    end
    local out = (side == "left") and -1 or 1
    for i, ty in ipairs({ FC.PROC_Y0, FC.PROC_Y1 }) do
        local t = r.ticks[i]
        local l, rr, top, bot = edges(t)
        local a, b = bx, bx + out * FC.IDLE_TICK
        near(l, m.x(math.min(a, b)), side .. " end tick left"); near(rr, m.x(math.max(a, b)), side .. " end tick right")
        near((top + bot) / 2, m.y(ty), side .. " end tick y"); near(top - bot, T, side .. " end tick thickness")
    end
end
""")

case("labels_and_icons_sit_above_the_tapes")(r"""
local H = 1440
local m = mk(H)
local GF = boot({ profile = "WARLOCK", height = H, state = function(p) return StateFor(p, {}) end })
local G = FS.Gunsight.G
for side, tape in pairs({ left = G.TL, right = G.TR }) do
    local r = GF.rungs[side]
    local spec = FS.Hud.profile.procs[r.key]
    check(spec and spec.side == side, "rung " .. side .. " is bound to the proc on that side")
    check(r.label:GetText() == spec.label, side .. " label text " .. tostring(r.label:GetText()))
    local tcx = (tape.x0 + tape.x1) / 2
    local p, rel, rp, x, y = r.label:GetPoint(1)
    check(p == "BOTTOM", "label is bottom-anchored on the baseline")
    near(cx(r.label), m.x(tcx), side .. " label centred on the tape")
    near(select(2, rect(r.label)), m.y(FC.LABEL_Y + FS.GunsightFrame.C.LABEL_DESCENT), side .. " label baseline (bottom of its box)")
    check(r.label.fontSize and r.label.fontSize >= 8, "label font size set through Theme.ApplyMono")
    -- the icon's left edge is label.length * 3.75 + 16 + 4 left of the tape centre
    local ix = tcx - #spec.label * FC.CHAR_HALF - FC.ICON - FC.ICON_PAD
    local l, rr, top, bot = edges(r.icon.frame)
    near(l, m.x(ix), side .. " icon left"); near(rr - l, m.ui(FC.ICON), side .. " icon size")
    near(top, m.y(FC.ICON_Y), side .. " icon top"); near(top - bot, m.ui(FC.ICON), side .. " icon height")
end
""")

LIT_BODY = r"""
local H = 1440
local m = mk(H)
local GF, Gs = boot({ profile = "WARLOCK", height = H, state = function(p) return StateFor(p, {}) end })
local G = Gs.G
local r = GF.rungs.left
local Tl = m.ui(FC.LIT_K)
local violet, amber = MakeTheme().COLOR_BORDER, MakeTheme().COLOR_AMBER
local function mix(a, b, t) return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t } end
local function colorIs(c, want, what)
    check(c, what .. ": no colour set")
    near(c[1], want[1], what .. " r"); near(c[2], want[2], what .. " g"); near(c[3], want[3], what .. " b")
end
local function litGeometry(q, what)
    local half = FC_PROC_BASE + q * FC_PROC_GROW
    local l, rr, top, bot = edges(r.lit.post)
    near((l + rr) / 2, m.x(G.LBRK), what .. " post x"); near(rr - l, Tl, what .. " post thickness")
    near(top, m.y(G.CY - half), what .. " post top"); near(bot, m.y(G.CY + half), what .. " post bottom")
    -- the run to the tape's inner edge
    local rl, rr2, rt, rb = edges(r.lit.run)
    near(rl, m.x(G.TL.x1 + FC.RUN_PAD), what .. " run left"); near(rr2, m.x(G.LBRK), what .. " run right")
    near((rt + rb) / 2, m.y(G.CY), what .. " run y")
    -- end ticks hang off the post ends, 7 long, out from the post
    for i, ty in ipairs({ G.CY - half, G.CY + half }) do
        local tl, tr, tt, tb = edges(r.lit.ticks[i])
        near((tt + tb) / 2, m.y(ty), what .. " tick " .. i .. " y")
        near(tl, m.x(G.LBRK - G.PROC_TICK), what .. " tick " .. i .. " left"); near(tr, m.x(G.LBRK), what .. " tick " .. i .. " right")
        near(tt - tb, Tl, what .. " tick thickness")
    end
end
"""
LIT_BODY = LIT_BODY.replace("FC_PROC_BASE", "FS.Gunsight.G.PROC_BASE").replace("FC_PROC_GROW", "FS.Gunsight.G.PROC_GROW")

case("a_lit_proc_shows_the_solid_amber_post_and_grows_over_a_third_of_a_second")(LIT_BODY + r"""
check(OnUpdates() == 0, "idle: no OnUpdate may run")
check(not r.lit.frame:IsShown() and r.q == 0, "idle rung is unlit")
check(not r.frame:IsShown() and not r.frame:IsVisible(), "idle rung is hidden, not dimmed")
colorIs(r.label.tcolor, mix(violet, { 1, 1, 1 }, FC.LABEL_MIX), "idle label colour")
check(r.icon.tex.desat == true, "an idle icon is grey")
Push(StateFor(FS.Hud.profile, { shadow_trance = true }))
check(r.frame:IsShown() and r.frame:GetAlpha() == 0, "the rung appears the moment its proc goes active, at alpha 0")
check(OnUpdates() == 1, "growing needs exactly one OnUpdate, has " .. OnUpdates())
RunUpdate(r.frame, 0.1)
near(r.q, 0.1 / FS.GunsightFrame.C.ANIM, "q after 0.1 s")
near(r.frame:GetAlpha(), r.q, "the whole rung fades in with q")
check(r.lit.frame:IsShown(), "lit group is shown while growing")
near(r.lit.frame:GetAlpha(), 1, "the amber group carries no q of its own: the rung frame does")
near(r.label:GetAlpha(), FC.LABEL_A0 + FC.LABEL_A1, "label alpha is its full value, not multiplied by q again")
near(r.icon.tex:GetAlpha(), FC.ICON_A0 + FC.ICON_A1, "icon alpha is its full value, not multiplied by q again")
litGeometry(r.q, "q 1/3")
colorIs(r.label.tcolor, mix(violet, { 1, 1, 1 }, FC.LABEL_MIX), "label below half is still the idle colour")
RunUpdate(r.frame, 0.1)
litGeometry(r.q, "q 2/3")
colorIs(r.label.tcolor, amber, "label above half turns amber")
near(r.frame:GetAlpha(), r.q, "the fade is linear in q: one alpha, on the rung frame")
near(r.label:GetAlpha(), 1, "label alpha at full value")
check(r.icon.tex.desat == false, "a lit icon is in colour")
colorIs(r.icon.edges[1].vcolor, amber, "icon edge above half is amber")
RunUpdate(r.frame, 0.2)
near(r.q, 1, "q reaches 1"); litGeometry(1, "q 1")
check(r.frame:IsVisible() and r.frame:GetAlpha() == 1, "the active rung is fully opaque, the look it always had")
check(OnUpdates() == 0, "growth done: the OnUpdate must be cleared, " .. OnUpdates() .. " left")
-- an update after the end must not run (handler gone) and the frame stays put
local wasFull = FS.Gunsight.ui(2 * (FS.Gunsight.G.PROC_BASE + FS.Gunsight.G.PROC_GROW))
near(select(4, rect(r.lit.post)), wasFull, "full post height")
""")

case("a_proc_that_ends_shrinks_and_goes_quiet")(LIT_BODY + r"""
Push(StateFor(FS.Hud.profile, { shadow_trance = true }))
RunUpdate(r.frame, 0.5)
near(r.q, 1, "full"); check(OnUpdates() == 0, "no OnUpdate at rest")
Push(StateFor(FS.Hud.profile, {}))
check(OnUpdates() == 1, "shrinking needs one OnUpdate")
RunUpdate(r.frame, 0.15)
near(r.q, 0.5, "half way down"); litGeometry(0.5, "q 1/2 down")
check(r.frame:IsShown(), "the rung stays up while it fades out")
RunUpdate(r.frame, 0.3)
near(r.q, 0, "q back to 0")
check(not r.lit.frame:IsShown(), "the lit group hides at q 0")
check(not r.frame:IsShown(), "on expiry the whole rung hides, it does not dim")
check(OnUpdates() == 0, "no OnUpdate left after the shrink")
colorIs(r.label.tcolor, mix(violet, { 1, 1, 1 }, FC.LABEL_MIX), "label back to idle")
check(r.icon.tex.desat == true, "icon back to grey")
""")

case("a_reversal_mid_growth_turns_around_from_where_it_is")(LIT_BODY + r"""
Push(StateFor(FS.Hud.profile, { shadow_trance = true }))
RunUpdate(r.frame, 0.15)
local q = r.q
Push(StateFor(FS.Hud.profile, {}))
near(r.q, q, "q is not reset by a flip")
RunUpdate(r.frame, 0.06)
near(r.q, q - 0.06 / FS.GunsightFrame.C.ANIM, "q shrinks from where it was")
Push(StateFor(FS.Hud.profile, { shadow_trance = true }))
RunUpdate(r.frame, 0.03)
near(r.q, q - 0.03 / FS.GunsightFrame.C.ANIM, "and grows again")
check(OnUpdates() == 1, "still exactly one OnUpdate")
""")

case("a_proc_already_up_at_login_is_drawn_at_once")(LIT_BODY + r"""
local GF2 = boot({ profile = "WARLOCK", height = H, state = function(p) return StateFor(p, { shadow_trance = true }) end })
local r2 = GF2.rungs.left
near(r2.q, 1, "no growth animation for a proc that was already lit")
check(r2.lit.frame:IsShown(), "lit")
check(r2.frame:IsShown() and r2.frame:GetAlpha() == 1, "and the rung itself is up at full alpha")
check(not GF2.rungs.right.frame:IsShown(), "the idle right rung stays hidden")
check(OnUpdates() == 0, "no OnUpdate at login")
""")

case("each_side_follows_its_own_proc")(LIT_BODY + r"""
Push(StateFor(FS.Hud.profile, { decimation = true }))
check(OnUpdates() == 1, "only the right rung animates")
RunUpdate(GF.rungs.right.frame, 0.5)
near(GF.rungs.right.q, 1, "right rung lit"); near(r.q, 0, "left rung untouched")
check(not r.lit.frame:IsShown(), "left stays dashed")
local rr = GF.rungs.right
local tcx = (G.TR.x0 + G.TR.x1) / 2
near(cx(rr.label), m.x(tcx), "right label centred on the target tape")
local l, ri = edges(rr.lit.run)
near(l, m.x(G.RBRK), "right run starts at the post"); near(ri, m.x(G.TR.x0 - FC.RUN_PAD), "right run ends at the tape's inner edge")
check(not (r.lit.frame:IsShown()), "no bleed")
""")

case("the_prc_piece_hides_every_rung")(r"""
local GF, Gs = boot({ profile = "WARLOCK", state = function(p) return StateFor(p, {}) end })
check(GF.prc:IsShown(), "prc starts on")
Gs.SetPiece("prc", false, true)
check(not GF.prc:IsShown(), "prc off hides the rung container")
Gs.SetPiece("prc", true, true)
check(GF.prc:IsShown() and not GF.rungs.left.frame:IsShown(), "prc on shows the container; an idle rung under it stays hidden")
Push(StateFor(FS.Hud.profile, { shadow_trance = true }))
RunUpdate(GF.rungs.left.frame, 1)
check(GF.prc:IsShown() and GF.rungs.left.frame:IsVisible(), "an active rung under prc is visible")
Gs.SetPiece("prc", false, true)
check(not GF.rungs.left.frame:IsVisible(), "prc off hides an active rung too")
local GF2 = boot({ profile = "WARLOCK", db = { gunsight = { pieces = { prc = false } } }, state = function(p) return StateFor(p, {}) end })
check(not GF2.prc:IsShown(), "saved prc off: starts hidden")
""")

case("a_state_pushed_while_hidden_snaps_instead_of_animating")(r"""
local GF, Gs = boot({ profile = "WARLOCK", state = function(p) return StateFor(p, {}) end })
Gs.SetPiece("prc", false, true)
Push(StateFor(FS.Hud.profile, { shadow_trance = true }))
near(GF.rungs.left.q, 1, "hidden: the proc state lands at once")
check(OnUpdates() == 0, "hidden: no OnUpdate (it would never fire anyway)")
check(GF.rungs.left.frame:IsShown() and not GF.rungs.left.frame:IsVisible(), "shown but not visible while prc is off")
Gs.SetPiece("prc", true, true)
check(GF.rungs.left.frame:IsVisible() and GF.rungs.left.frame:GetAlpha() == 1, "the snapped rung is there, fully up, when the parent comes back")""")

case("an_inactive_proc_rung_is_hidden_appears_when_active_and_hides_on_expiry")(r"""
local GF, Gs = boot({ profile = "WARLOCK", state = function(p) return StateFor(p, {}) end })
local L, R = GF.rungs.left, GF.rungs.right
-- hidden, not dimmed: nothing of the rung can be seen while its proc is down
for side, r in pairs({ left = L, right = R }) do
    check(not r.frame:IsShown() and not r.frame:IsVisible(), side .. ": idle rung hidden")
    check(not r.lit.frame:IsShown(), side .. ": lit group hidden")
end
check(OnUpdates() == 0, "idle: nothing runs")
-- active: only that side appears
Push(StateFor(FS.Hud.profile, { shadow_trance = true }))
check(L.frame:IsVisible(), "TRANCE active: the left rung appears")
check(not R.frame:IsShown(), "the right rung stays hidden")
RunUpdate(L.frame, 1)
check(L.frame:IsVisible() and L.frame:GetAlpha() == 1 and L.lit.frame:IsShown(), "fully up once the proc has grown")
-- a repeated active state changes nothing
Push(StateFor(FS.Hud.profile, { shadow_trance = true }))
check(L.frame:IsVisible() and OnUpdates() == 0, "a repeated active state starts nothing")
-- expiry: it fades out, then hides again
Push(StateFor(FS.Hud.profile, {}))
check(L.frame:IsShown(), "it fades out first, still shown")
RunUpdate(L.frame, 1)
check(not L.frame:IsShown() and OnUpdates() == 0, "back to hidden on expiry, nothing left running")
-- and it can come back
Push(StateFor(FS.Hud.profile, { shadow_trance = true }))
check(L.frame:IsShown(), "it appears again on the next proc")
RunUpdate(L.frame, 1)
-- Hud state that drops the proc entry hides the rung too
Push({ active = false, row = {}, buffsMissing = {}, procs = {} })
check(not L.frame:IsShown(), "no proc entry: hidden")
""")

case("showing_and_hiding_a_rung_moves_nothing_and_stays_off_protected_frames")(r"""
local function snap()
    local out = {}
    for _, f in ipairs(FRAMES) do
        local pts = {}
        for i = 1, f:GetNumPoints() do
            local p, rel, rp, x, y = f:GetPoint(i)
            pts[#pts + 1] = tostring(p) .. ":" .. tostring(rel and rel.name) .. ":" .. tostring(rp) .. ":" .. tostring(x) .. ":" .. tostring(y)
        end
        out[f] = table.concat(pts, "|") -- anchors only: a lit stroke frame legitimately resizes with q
    end
    return out
end
local GF, Gs = boot({ profile = "WARLOCK", state = function(p) return StateFor(p, {}) end })
local before = snap()
Push(StateFor(FS.Hud.profile, { shadow_trance = true, decimation = true }))
RunUpdate(GF.rungs.left.frame, 1); RunUpdate(GF.rungs.right.frame, 1)
Push(StateFor(FS.Hud.profile, {}))
RunUpdate(GF.rungs.left.frame, 1); RunUpdate(GF.rungs.right.frame, 1)
local after = snap()
for f, v in pairs(before) do
    check(after[f] == v, "a rung showing or hiding moved " .. tostring(f.name) .. ": " .. v .. " -> " .. tostring(after[f]))
end
-- the horizon, the tapes' neighbours and the prc container are untouched in alpha and visibility
check(GF.prc:IsShown() and GF.prc:GetAlpha() == 1, "the prc container is not touched by a rung appearing")
check(GF.horizon.you.frame:IsShown(), "the horizon is untouched")
-- every rung frame is a plain Frame: no secure template, never protected, parented under the prc piece
for side, r in pairs(GF.rungs) do
    check(r.frame.template == nil, side .. ": rung frame has no template (not secure)")
    check(not (r.frame.IsProtected and r.frame:IsProtected()), side .. ": rung frame is not protected")
    check(r.frame:GetParent() == GF.prc, side .. ": rung frame is a child of the prc frame")
    for _, kid in ipairs({ r.lit.frame, r.icon.frame }) do
        check(kid.template == nil and kid:GetParent() == r.frame, side .. ": rung children are plain frames under the rung")
    end
end
-- Show / Hide / SetAlpha are legal in combat: a proc going active and expiring with InCombatLockdown true
local GF2 = boot({ profile = "WARLOCK", state = function(p) return StateFor(p, {}) end })
IN_COMBAT = true
local ok = pcall(Push, StateFor(FS.Hud.profile, { shadow_trance = true }))
check(ok and GF2.rungs.left.frame:IsShown(), "a rung appears in combat")
RunUpdate(GF2.rungs.left.frame, 1)
ok = pcall(Push, StateFor(FS.Hud.profile, {}))
RunUpdate(GF2.rungs.left.frame, 1)
check(ok and not GF2.rungs.left.frame:IsShown(), "and hides in combat")
IN_COMBAT = false
""")

case("a_proc_rung_never_flashes_at_full_alpha_when_it_first_appears")(r"""
local GF = boot({ profile = "WARLOCK", state = function(p) return StateFor(p, {}) end })
local r = GF.rungs.left
Push(StateFor(FS.Hud.profile, {}))
Push(StateFor(FS.Hud.profile, { shadow_trance = true }))
check(r.frame:IsShown(), "setup: the rung is up")
check(r.frame:GetAlpha() == 0, "alpha is 0 before any update runs (no one frame flash), is " .. tostring(r.frame:GetAlpha()))
""")

case("a_rescale_keeps_a_hidden_rung_hidden_and_never_shows_one_mid_fade")(r"""
local GF = boot({ profile = "WARLOCK", state = function(p) return StateFor(p, {}) end })
local r = GF.rungs.left
SetScreen(1200); fire("UI_SCALE_CHANGED")
check(not r.frame:IsShown(), "rescale while hidden: still hidden")
check((r.frame.calls.Show or 0) == 0, "rescale while hidden: Show never called")
Push(StateFor(FS.Hud.profile, { shadow_trance = true }))
RunUpdate(r.frame, 0.1)
local shows = r.frame.calls.Show or 0
local q = r.q
check(q > 0 and q < 1, "setup: mid fade")
SetScreen(1080); fire("DISPLAY_SIZE_CHANGED")
check((r.frame.calls.Show or 0) == shows, "rescale mid fade: no Show")
check(r.frame:IsShown(), "rescale mid fade: still shown")
near(r.q, q, "rescale mid fade: q untouched")
near(r.frame:GetAlpha(), q, "rescale mid fade: alpha follows q")
""")

case("a_proc_that_ends_while_prc_is_hidden_leaves_the_rung_hidden_when_prc_returns")(r"""
local GF, Gs = boot({ profile = "WARLOCK", state = function(p) return StateFor(p, {}) end })
local r = GF.rungs.left
Push(StateFor(FS.Hud.profile, { shadow_trance = true }))
RunUpdate(r.frame, 1)
check(r.frame:IsVisible(), "setup: rung up")
Gs.SetPiece("prc", false, true)
Push(StateFor(FS.Hud.profile, {}))
Gs.SetPiece("prc", true, true)
check(not r.frame:IsShown(), "proc ended while prc was off: the rung is hidden when prc returns")
check(OnUpdates() == 0, "nothing animates")
""")

case("a_secret_proc_state_never_reaches_a_comparison_and_leaves_the_rung_hidden")(r"""
local GF = boot({ profile = "WARLOCK", state = function(p) return StateFor(p, {}) end })
local asked = 0
local base = FS.IsSecret
FS.IsSecret = function(v) if v == SECRET then asked = asked + 1 end return base(v) end
local ok = pcall(Push, { procs = { { key = "shadow_trance", active = SECRET }, { key = "decimation", active = SECRET } } })
check(ok, "a secret active flag must not throw")
check(asked >= 2, "each secret flag is classified through IsSecret before any use, asked " .. asked)
for side, r in pairs(GF.rungs) do
    check(not r.frame:IsShown(), side .. ": a secret flag never shows the rung")
    check(r.target == 0 and r.q == 0, side .. ": and never aims it up")
end
check(OnUpdates() == 0, "nothing animates for a secret flag")
-- a rung that was up and then goes secret falls back to hidden through the same path
Push(StateFor(FS.Hud.profile, { shadow_trance = true }))
RunUpdate(GF.rungs.left.frame, 1)
check(GF.rungs.left.frame:IsShown(), "setup: rung up")
Push({ procs = { { key = "shadow_trance", active = SECRET } } })
RunUpdate(GF.rungs.left.frame, 1)
check(not GF.rungs.left.frame:IsShown(), "a secret flag reads as idle, so it hides")
""")

case("icon_texture_comes_from_the_proc_aura_and_a_secret_is_never_used")(r"""
SPELL_TEXTURES[17941] = 136183
local GF = boot({ profile = "WARLOCK", state = function(p) return StateFor(p, {}) end })
local r = GF.rungs.left
check(r.icon.tex.tex == 136183, "icon texture is C_Spell.GetSpellTexture(aura): " .. tostring(r.icon.tex.tex))
check(r.icon.tex:IsShown() and not r.icon.fallback:IsShown(), "a real texture hides the abbreviation")
SPELL_TEXTURES[17941] = SECRET
local GF2 = boot({ profile = "WARLOCK", state = function(p) return StateFor(p, {}) end })
local r2 = GF2.rungs.left
check(r2.icon.tex.tex ~= SECRET, "a secret texture must never reach SetTexture")
check(not r2.icon.tex:IsShown() and r2.icon.fallback:IsShown(), "no usable texture: the two letter fallback shows")
check(r2.icon.fallback:GetText() == "TR", "fallback is the label's first two letters, got " .. tostring(r2.icon.fallback:GetText()))
SPELL_TEXTURES[17941] = nil
local GF3 = boot({ profile = "WARLOCK", state = function(p) return StateFor(p, {}) end })
check(GF3.rungs.left.icon.fallback:IsShown(), "a missing texture shows the fallback")
""")

case("icon_plate_chamfer_matches_the_ring_at_every_scale")(r"""
-- the ring is Cut2ButtonSet(CutSizeIcon(px)); a plate with a fixed chamfer 6 leaves a wedge under
-- the ring's diagonal at 3 and 4, so the plate must cut like the ring (texture and slice margin).
local seen = {}
for _, h in ipairs({ 480, 1080, 1440, 2160 }) do
    local GF = boot({ profile = "WARLOCK", height = h, state = function(p) return StateFor(p, {}) end })
    for _, side in ipairs({ "left", "right" }) do
        local icon = GF.rungs[side].icon
        local ring = icon.edges[1]
        local cut = tonumber(string.match(ring.tex, "_c(%d+)$"))
        check(cut, "the ring texture names its cut at height " .. h .. ": " .. tostring(ring.tex))
        check(icon.plate, "the icon plate exists at height " .. h)
        check(icon.plate.slice == cut, "plate slice margin " .. tostring(icon.plate.slice) .. " must equal the ring cut " .. cut .. " at height " .. h)
        local want = cut == 6 and "cut2_fill" or ("Interface\\AddOns\\forever-stuwave\\Media\\Textures\\slice_cut2_fill_c" .. cut .. ".tga")
        check(icon.plate.tex == want, "plate texture " .. tostring(icon.plate.tex) .. " must be " .. want .. " at height " .. h)
        seen[cut] = true
    end
end
check(seen[3] and seen[4], "the sweep must cover the 3 and 4 cuts that the old fixed 6 plate got wrong")
-- a rescale re-cuts the plate along with the ring
local GF = boot({ profile = "WARLOCK", height = 1440, state = function(p) return StateFor(p, {}) end })
local icon = GF.rungs.left.icon
check(icon.plate.slice == 4, "1440 plate cut 4, got " .. tostring(icon.plate.slice))
SetScreen(1080); fire("UI_SCALE_CHANGED")
check(icon.plate.slice == 3 and icon.edges[1].tex == "outline_c3", "1080 plate and ring both cut 3, got " .. tostring(icon.plate.slice))
""")

# ---------------------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------------------

case("no_onupdate_is_left_running_when_idle")(r"""
local GF, Gs = boot({ profile = "WARLOCK", state = function(p) return StateFor(p, { shadow_trance = true }) end })
check(OnUpdates() == 0, "at login: " .. OnUpdates())
Push(StateFor(FS.Hud.profile, {}))
RunUpdate(GF.rungs.left.frame, 1)
Push(StateFor(FS.Hud.profile, { shadow_trance = true, decimation = true }))
RunUpdate(GF.rungs.left.frame, 1); RunUpdate(GF.rungs.right.frame, 1)
check(OnUpdates() == 0, "after growth: " .. OnUpdates())
Gs.SetPiece("you", false); finishAnims(); Gs.SetPiece("you", true); finishAnims()
SetScreen(1200); fire("UI_SCALE_CHANGED")
check(OnUpdates() == 0, "after fades and a rescale: " .. OnUpdates())
-- a repeated identical state starts nothing
Push(StateFor(FS.Hud.profile, { shadow_trance = true, decimation = true }))
check(OnUpdates() == 0, "an unchanged state must not start an OnUpdate")
""")

case("a_disabled_gunsight_builds_nothing")(r"""
local GF = boot({ profile = "WARLOCK", db = { gunsight = { enabled = false } } })
check(FramesNamed("ForeverSTUwaveGunsightFrame") == 0, "disabled: no frames may be built")
check(#HUD_SUBS == 0, "disabled: no FS.Hud subscription")
""")

case("subscribes_to_the_hud_once")(r"""
boot({ profile = "WARLOCK" })
check(#HUD_SUBS == 1, "want exactly one FS.Hud subscription, have " .. #HUD_SUBS)
""")

case("a_throwing_hud_state_does_not_kill_the_frame")(r"""
local GF = boot({ profile = "WARLOCK", state = function(p) return StateFor(p, {}) end })
local ok = pcall(Push, { procs = { { key = "shadow_trance", active = SECRET }, { key = "nope", active = true }, "junk" } })
check(ok, "a secret or malformed proc entry must not throw")
near(GF.rungs.left.q, 0, "a secret active flag reads as idle")
check(not GF.rungs.left.frame:IsShown(), "and a secret active flag leaves the rung hidden")
local ok2 = pcall(Push, {})
check(ok2, "a state with no procs table must not throw")
check(not GF.rungs.left.frame:IsShown(), "and hides the rungs")
""")

case("missing_theme_helpers_degrade_without_throwing")(r"""
local GF = boot({ profile = "WARLOCK", noTheme = true, state = function(p) return StateFor(p, {}) end })
check(GF ~= nil and GF.horizon.you.frame:IsShown(), "the horizon draws without Theme")
""")

# The client throws "Font not set" for SetText on a FontString without a font. The rung label and the icon's
# fallback letters used to get theirs only in LayoutRung through a pcall'd Theme.ApplyMono, so a failing or
# missing ApplyMono left the first SetText to throw. They now get a font at creation (the stock font object
# when ApplyMono cannot).
case("a_failing_apply_mono_still_gives_every_rung_font_string_a_font_before_its_first_settext")(r"""
GameFontNormal = {}
local GF = boot({ profile = "WARLOCK", state = function(p) return StateFor(p, {}) end,
    themeHook = function(T) T.ApplyMono = function() error("ApplyMono failed") end end })
local n = 0
for side, r in pairs(GF.rungs) do
    n = n + 1
    local spec = FS.Hud.profile.procs[r.key]
    check(spec, side .. ": the rung is bound")
    check(r.label.hasFont, side .. ": the label has a font")
    check(r.icon.fallback.hasFont, side .. ": so does the icon's fallback text")
    check(r.label:GetText() == spec.label, side .. ": the label text was written, got " .. tostring(r.label:GetText()))
    check(r.icon.fallback:GetText() == string.sub(spec.label, 1, 2), side .. ": and the fallback letters")
end
check(n == 2, "both rungs exist")
""")

case("without_theme_the_rung_text_still_gets_a_stock_font")(r"""
GameFontNormal = {}
local GF = boot({ profile = "WARLOCK", noTheme = true, state = function(p) return StateFor(p, {}) end })
for side, r in pairs(GF.rungs) do
    local spec = FS.Hud.profile.procs[r.key]
    check(r.label.hasFont and r.icon.fallback.hasFont, side .. ": fonts without Theme")
    check(r.label:GetText() == spec.label, side .. ": label text " .. tostring(r.label:GetText()))
end
""")


def static_checks() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []

    raw = TOC.read_bytes()
    lines = raw.split(b"\r\n")
    bare = [i + 1 for i, ln in enumerate(lines) if b"\n" in ln]
    out.append(("toc_is_crlf", None if not bare else f"bare LF at toc lines {bare[:5]}"))
    entries = [ln.strip() for ln in raw.decode("utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        g, f = entries.index("Modules/CombatHud/Gunsight.lua"), entries.index("Modules/CombatHud/GunsightFrame.lua")
        # GunsightFrame needs FS.Gunsight at load (Gunsight.lua first); FS.Hud is read at Build time,
        # after OnReady, so CombatHud.lua may sit on either side. GunsightDots may sit between.
        out.append(("toc_order", None if g < f else f"Gunsight.lua must load before GunsightFrame.lua (positions {g}, {f})"))
    except ValueError as e:
        out.append(("toc_order", f"{e}"))

    theme = THEME.read_text(encoding="utf-8")
    need = [r"^Theme\.COLOR_BORDER\s*=", r"^Theme\.COLOR_AMBER\s*=", r"^Theme\.FLAT_TEXTURE\s*=", r"^Theme\.GLOW_EDGE_TEXTURE\s*=",
            r"^Theme\.FONT_MONO\s*=", r"^Theme\.SLICE_CUT2_FILL_TEXTURE\s*=", r"^function Theme\.ApplyMono\(", r"^function Theme\.SnapCut\(",
            r"^function Theme\.CutSizeIcon\(", r"^function Theme\.Cut2ButtonSet\(", r"^function Theme\.AddSliceTexture\(",
            r"^function Theme\.AddCut2Texture\(", r"^function Theme\.ApplyNineSlice\("]
    missing = [p for p in need if not re.search(p, theme, re.M)]
    out.append(("theme_contract", None if not missing else f"Theme.lua no longer defines: {missing}"))
    glow = (ADDON / "Media" / "Textures" / "glow_edge.tga").exists()
    out.append(("glow_edge_texture_exists", None if glow else "media/glow_edge.tga is missing"))
    return out


def run_case(body: str, mu: dict, fc: dict, expect: dict, srcs: dict) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(gh.MOCK)
    lua.execute(EXTRA)
    lua.execute(f"MU = {gh.lua_value(mu)}; FC = {gh.lua_value(fc)}; EXPECT = {gh.lua_value(expect)}")
    g = lua.globals()
    g.LAYOUT_SRC = gh.LAYOUT.read_text(encoding="utf-8")
    g.CONFIG_SRC = gh.CONFIG.read_text(encoding="utf-8")
    g.GUNSIGHT_SRC = srcs["gunsight"]
    g.PROFILES_SRC = srcs["profiles"]
    g.FRAME_SRC = srcs["frame"]
    g.HELPERS_SRC = tips.HELPERS.read_text(encoding="utf-8")
    g.HAS_TARGET_SRC = gh.theme_target_rule_lua()
    runner = lua.eval("function(src) local f, e = loadstring(src, '=case'); if not f then return false, e end; local ok, err = pcall(f); if ok then return true, '' end; return false, tostring(err) end")
    ok, err = runner(PRELUDE + "\n" + body)
    return None if ok else str(err)


def main() -> int:
    mu = gh.mockup_constants()
    fc = frame_constants()
    expect = gh.expected_rects(mu)
    failures = 0

    def report(name: str, err: str | None) -> None:
        nonlocal failures
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      " + err.replace("\n", "\n      "))

    if not FRAME_LUA.exists():
        report("gunsightframe_file", f"{FRAME_LUA} does not exist")
        for name, _ in CASES:
            report(name, "GunsightFrame.lua is missing")
        for name, err in static_checks():
            report(name, err)
        print(f"\n{failures} failed")
        return 1

    srcs = {
        "gunsight": GUNSIGHT.read_text(encoding="utf-8"),
        "profiles": PROFILES.read_text(encoding="utf-8"),
        "frame": FRAME_LUA.read_text(encoding="utf-8"),
    }
    for name, body in CASES:
        try:
            err = run_case(body, mu, fc, expect, srcs)
        except LuaError as e:  # a mock or harness bug, not a pass
            err = f"harness error: {e}"
        report(name, err)
    statics = static_checks()
    for name, err in statics:
        report(name, err)

    total = len(CASES) + len(statics)
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
