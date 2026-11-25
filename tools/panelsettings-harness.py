#!/usr/bin/env python3
"""Chat, Minimap and Quest tracker settings: the keys, the defaults, the live apply, the pages.

The Chat, Minimap and Quest tracker pages of /fsconfig carry the rows of the prototype
(mockups/proto-src-2026-11-25/proto-pages.js). This harness runs the real module files headless and pins:

  * Chat background opacity (chat.bgAlpha, percent) retints the panel's dark fill and nothing else; 85 is today's alpha
    exactly, so an untouched profile paints what it always did;
  * the Minimap size (minimap.w, minimap.h) and scale (minimap.scale): defaults leave the seat exactly as it was, a
    slider moves the map live and survives the Edit Mode reseat, and scale grows the map, the key row, the tray and the
    text together (one Minimap:SetScale), keeping the map's centre where the layout put it;
  * the Quest tracker opacity (tracker.alpha), background opacity (tracker.bgAlpha) and scale (tracker.scale);
  * every row of the three prototype pages is registered under the prototype's key (a row that cannot be built says why).

    python3 tools/panelsettings-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ADDON = Path(__file__).resolve().parent.parent / "forever-stuwave"

# ---------------------------------------------------------------------------------------------------------------------
# Chat: the background fill
# ---------------------------------------------------------------------------------------------------------------------

CHAT_MOCK = r"""
local DB = {}
__config, __changed = {}, {}
FS = { IsSecret = function() return false end }
FS.Config = {
    RegisterDefault = function(k, v) DB[k] = { default = v } end,
    Get = function(k) local e = DB[k]; if not e then return nil end; if e.value ~= nil then return e.value end; return e.default end,
    Set = function(k, v)
        local e = DB[k]; local old = FS.Config.Get(k); e.value = v
        for _, fn in ipairs(__changed[k] or {}) do fn(v, old, k) end
    end,
    OnChange = function(k, fn) __changed[k] = __changed[k] or {}; table.insert(__changed[k], fn) end,
}

-- A texture region that remembers what it was last tinted.
local function region(texture)
    local r = { tex = texture, tint = nil, tints = 0 }
    function r:GetTexture() return self.tex end
    function r:SetVertexColor(...) self.tint = { ... }; self.tints = self.tints + 1 end
    return r
end
__region = region

local FILL = "fill.tga"
FS.Theme = {
    SLICE_FILL_TEXTURE = FILL, SLICE_MARGIN = 6, COLOR_POWER = { 0, 0.9, 1, 1 },
    StripBlizzardChrome = function() end,
    -- Theme.SkinPanel: the fill, the glow and the border, in that order, tinted the way AddPanelChrome does.
    SkinPanel = function(frame, opts)
        local fill, glow, border = region(FILL), region("glow.tga"), region("border.tga")
        local c = opts.fillColor
        fill.tint = { c[1], c[2], c[3], c[4] }
        glow.tint = { 0, 0.9, 1, opts.glowAlpha }
        border.tint = { 0, 0.9, 1, 1 }
        frame.chrome = { fill, glow, border }
        return frame.chrome
    end,
    AddRoundedFill = function(frame, color) frame.wash = region("wash.tga"); frame.wash.tint = color; return frame.wash end,
}
local noop = function() end
FS.Chat = setmetatable({
    COLOR_TERM_BG = { 0.027, 0.012, 0.102, 0.85 }, LEVEL_BACKDROP = 0, skinnedChatFrames = {},
    termPanel = { GetFrameLevel = function() return 1 end },
    AnchorBackdrop = noop,
}, { __index = function() return noop end })

__frames = {}
function CreateFrame()
    local f = { regions = {}, events = {} }
    function f:SetFrameLevel() end
    function f:RegisterEvent(e) self.events[e] = true end
    function f:SetScript(name, fn) self[name] = fn end
    __frames[#__frames + 1] = f
    return f
end
function __fire(event)
    for _, f in ipairs(__frames) do
        if f.events[event] and f.OnEvent then f.OnEvent(f, event) end
    end
end
-- The profile loading after the files ran: a stored value with no callback, as the loader does it.
function __stored(k, v) DB[k].value = v end
function ___frame()
    local f = { GetHeight = function() return 373 end, GetChildren = function() end }
    return f
end
"""

CHAT_CHECKS = r"""
local T = {}
local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end
local function near(a, b, msg)
    if math.abs(a - b) > 1e-9 then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end

local function skin()
    local frame = ___frame()
    FS.Chat.SkinChatFrame(frame, 1)
    return frame, frame.fsBackdrop
end

function T.chat_background_default_is_todays_fill_exactly()
    local _, backdrop = skin()
    local fill = backdrop.chrome[1]
    eq(fill.tint[4], FS.Chat.COLOR_TERM_BG[4], "the fill alpha at the default")
    eq(fill.tint[1], FS.Chat.COLOR_TERM_BG[1]); eq(fill.tint[2], FS.Chat.COLOR_TERM_BG[2]); eq(fill.tint[3], FS.Chat.COLOR_TERM_BG[3])
    eq(FS.Chat.BG.default, 85)
end

function T.chat_background_slider_retints_the_fill_live()
    local frame, backdrop = skin()
    FS.Config.Set("chat.bgAlpha", 40)
    near(backdrop.chrome[1].tint[4], 0.40, "the fill alpha at 40")
    FS.Config.Set("chat.bgAlpha", 0)
    near(backdrop.chrome[1].tint[4], 0, "the fill alpha at 0")
    FS.Config.Set("chat.bgAlpha", 100)
    near(backdrop.chrome[1].tint[4], 1, "the fill alpha at 100")
    FS.Config.Set("chat.bgAlpha", 85)
    eq(backdrop.chrome[1].tint[4], FS.Chat.COLOR_TERM_BG[4], "back to the default is today's alpha exactly")
end

function T.chat_background_touches_only_the_fill()
    local _, backdrop = skin()
    local glow, border, wash = backdrop.chrome[2], backdrop.chrome[3], backdrop.wash
    local g, b, w = glow.tints, border.tints, wash.tints
    FS.Config.Set("chat.bgAlpha", 30)
    eq(glow.tints, g, "the glow was retinted"); eq(border.tints, b, "the border was retinted"); eq(wash.tints, w, "the wash was retinted")
    eq(glow.tint[4], 0.3); eq(border.tint[4], 1); eq(wash.tint[4], 0.04)
end

function T.chat_background_reaches_a_window_skinned_later()
    FS.Config.Set("chat.bgAlpha", 55)
    local _, backdrop = skin()
    near(backdrop.chrome[1].tint[4], 0.55, "a window skinned after the setting was changed")
end

function T.chat_background_saved_value_is_painted_at_login()
    local _, backdrop = skin()
    __stored("chat.bgAlpha", 25)
    eq(backdrop.chrome[1].tint[4], FS.Chat.COLOR_TERM_BG[4], "nothing repaints before PLAYER_LOGIN")
    __fire("PLAYER_LOGIN")
    near(backdrop.chrome[1].tint[4], 0.25, "the saved opacity at PLAYER_LOGIN")
end

function T.chat_background_clamps_and_ignores_junk()
    local _, backdrop = skin()
    FS.Config.Set("chat.bgAlpha", 250)
    near(backdrop.chrome[1].tint[4], 1, "above the range")
    FS.Config.Set("chat.bgAlpha", -5)
    near(backdrop.chrome[1].tint[4], 0, "below the range")
    FS.Config.Set("chat.bgAlpha", "high")
    eq(backdrop.chrome[1].tint[4], FS.Chat.COLOR_TERM_BG[4], "a string falls back to the default alpha")
    FS.Config.Set("chat.bgAlpha", 0 / 0)
    eq(backdrop.chrome[1].tint[4], FS.Chat.COLOR_TERM_BG[4], "NaN falls back to the default alpha")
end

__checks = T
"""


def chat_boot() -> "LuaRuntime":
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(CHAT_MOCK)
    # CHATSKIN_LUA points the harness at a mutant or an older copy (mutation checks).
    src = Path(os.environ.get("CHATSKIN_LUA", ADDON / "Modules/Chat/ChatFrameSkin.lua")).read_text(encoding="utf-8")
    lua.execute("function __load(src, fs) return assert(loadstring(src, '=ChatFrameSkin'))('forever-stuwave', fs) end")
    lua.eval("__load")(src, lua.eval("FS"))
    lua.execute(CHAT_CHECKS)
    return lua


# ---------------------------------------------------------------------------------------------------------------------
# Minimap: size and scale
# ---------------------------------------------------------------------------------------------------------------------

def load_module(filename: str, name: str):
    """A sibling harness imported by file name (they have hyphens), for its worlds and mocks."""
    import importlib.util
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    spec = importlib.util.spec_from_file_location(name, here / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_minimap_harness():
    """The minimap harness's worlds (the real Theme, FrameHelpers, Layout and Minimap on a mock client)."""
    return load_module("minimap-harness.py", "minimap_harness")


CONFIG_STUB = r"""
__cfg, __cfgDefault, __cfgWatch = __cfg or {}, {}, {}
FS.Config = {
    RegisterDefault = function(k, v) __cfgDefault[k] = v end,
    Get = function(k) if __cfg[k] ~= nil then return __cfg[k] end; return __cfgDefault[k] end,
    IsStored = function(k) return __cfg[k] ~= nil end,
    Set = function(k, v)
        local old = FS.Config.Get(k)
        if v == __cfgDefault[k] then v = nil end
        __cfg[k] = v
        for _, fn in ipairs(__cfgWatch[k] or {}) do fn(FS.Config.Get(k), old, k) end
    end,
    OnChange = function(k, fn) __cfgWatch[k] = __cfgWatch[k] or {}; table.insert(__cfgWatch[k], fn) end,
}
"""

MM_TOL = 0.01


def mm_seated(mh, extra: str = "", pixel: float | None = None, config: bool = True):
    """A geometry world (Edit Mode shaped cluster) that has logged in and settled; the real Config API when asked."""
    setup = (CONFIG_STUB if config else "") + extra
    if pixel is not None:
        setup += mh.pixel_setup(pixel)
    lua = mh.geo_world(setup)
    lua.execute('FireEvent("PLAYER_LOGIN")')
    lua.execute("__frames(4, false)")
    return lua, lua.globals()


def mm_set(lua, key, value, frames: int = 4):
    lua.execute(f"FS.Config.Set({key!r}, {value!r}) __frames({frames}, false)")


MM_ON_TARGET = r"""
-- The map's top-left corner and centre against the layout seat for the minimap scale `m` (a CENTER seat).
function __mmCenter()
    local l, b, w, h = __rect(Minimap)
    return l + w / 2, b + h / 2, w, h
end
function __mmSeat()
    local L, s = FS.Layout.minimap, FS.Layout.Scale()
    return UIParent.w / 2 + L.x * s, UIParent.h / 2 + L.y * s
end
"""


def need(ok: bool, msg: str) -> None:
    if not ok:
        raise AssertionError(msg)


def near(a, b, tol: float = MM_TOL) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol


def minimap_cases(mh) -> list[tuple[str, "callable"]]:
    out = []

    def case(fn):
        out.append((fn.__name__, fn))
        return fn

    @case
    def minimap_keys_register_with_the_prototype_defaults():
        lua, g = mm_seated(mh)
        for key, default in (("minimap.w", 250), ("minimap.h", 252), ("minimap.scale", 100)):
            need(lua.eval(f"FS.Config.Get({key!r})") == default, f"{key} default")
        spec = g.FS.MinimapSettings
        need((spec.w.min, spec.w.max, spec.h.min, spec.h.max) == (150, 400, 150, 400), "width and height range")
        need((spec.scale.min, spec.scale.max, spec.scale.step) == (50, 200, 5), "scale range and step")

    @case
    def minimap_defaults_leave_today_s_seat_untouched():
        lua, g = mm_seated(mh)
        L, s = g.FS.Layout.minimap, g.FS.Layout.Scale()
        need((L.w, L.h) == (250, 252), f"layout entry {L.w}x{L.h}")
        need(near(g.Minimap.w, 250 * s) and near(g.Minimap.h, 252 * s), f"map size {g.Minimap.w}x{g.Minimap.h}")
        need(g.Minimap.scale is None, f"a default profile wrote a scale ({g.Minimap.scale})")

    @case
    def minimap_width_slider_resizes_the_map_live_and_keeps_its_centre():
        lua, g = mm_seated(mh)
        lua.execute(MM_ON_TARGET)
        cx0, cy0, _, h0 = g.__mmCenter()
        mm_set(lua, "minimap.w", 320)
        s = g.FS.Layout.Scale()
        cx, cy, w, h = g.__mmCenter()
        need(g.FS.Layout.minimap.w == 320, "the layout entry follows the slider")
        need(near(g.Minimap.w, 320 * s), f"Minimap width {g.Minimap.w} want {320 * s}")
        need(near(w, 320 * s) and near(h, h0), f"on screen {w}x{h}")
        sx, sy = g.__mmSeat()
        need(near(cx, sx) and near(cy, sy), f"centre {cx:.2f},{cy:.2f} want {sx:.2f},{sy:.2f}")

    @case
    def minimap_height_slider_is_independent_of_width():
        lua, g = mm_seated(mh)
        mm_set(lua, "minimap.h", 190)
        s = g.FS.Layout.Scale()
        need(g.FS.Layout.minimap.h == 190 and g.FS.Layout.minimap.w == 250, "only the height moved")
        need(near(g.Minimap.h, 190 * s) and near(g.Minimap.w, 250 * s), f"{g.Minimap.w}x{g.Minimap.h}")

    @case
    def minimap_size_survives_an_edit_mode_reseat_and_a_ui_rescale():
        lua, g = mm_seated(mh)
        lua.execute(MM_ON_TARGET)
        mm_set(lua, "minimap.w", 300)
        mm_set(lua, "minimap.h", 210)
        lua.execute("EditModeManagerFrame:UpdateLayoutInfo(); MinimapCluster:MarkDirty(); __frames(5, false)")
        s = g.FS.Layout.Scale()
        need(near(g.Minimap.w, 300 * s) and near(g.Minimap.h, 210 * s), f"after the reseat {g.Minimap.w}x{g.Minimap.h}")
        lua.execute("UIParent.h = 1080; UIParent.w = 1080 * 16 / 9; FireEvent('UI_SCALE_CHANGED'); __frames(4, false)")
        s = g.FS.Layout.Scale()
        need(near(g.Minimap.w, 300 * s) and near(g.Minimap.h, 210 * s), f"after the rescale {g.Minimap.w}x{g.Minimap.h}")
        cx, cy, _, _ = g.__mmCenter()
        sx, sy = g.__mmSeat()
        need(near(cx, sx) and near(cy, sy), "centre after the rescale")

    @case
    def minimap_size_is_applied_from_the_saved_value_at_login():
        lua = mh.geo_world(CONFIG_STUB + 'FS.Config.Set("minimap.w", 330) FS.Config.Set("minimap.scale", 125)')
        lua.execute('FireEvent("PLAYER_LOGIN")')
        lua.execute("__frames(4, false)")
        g = lua.globals()
        s = g.FS.Layout.Scale()
        need(g.FS.Layout.minimap.w == 330 and near(g.Minimap.w, 330 * s), f"width {g.Minimap.w}")
        need(near(g.Minimap.scale, 1.25), f"scale {g.Minimap.scale}")

    @case
    def minimap_size_is_clamped_and_junk_reads_as_the_default():
        lua, g = mm_seated(mh)
        mm_set(lua, "minimap.w", 9999)
        need(g.FS.Layout.minimap.w == 400, f"above the range gave {g.FS.Layout.minimap.w}")
        mm_set(lua, "minimap.w", 3)
        need(g.FS.Layout.minimap.w == 150, f"below the range gave {g.FS.Layout.minimap.w}")
        mm_set(lua, "minimap.w", "wide")
        need(g.FS.Layout.minimap.w == 250, f"a string gave {g.FS.Layout.minimap.w}")
        mm_set(lua, "minimap.scale", 999)
        need(near(g.Minimap.scale, 2.0), f"scale above the range gave {g.Minimap.scale}")
        mm_set(lua, "minimap.scale", 1)
        need(near(g.Minimap.scale, 0.5), f"scale below the range gave {g.Minimap.scale}")

    @case
    def minimap_scale_grows_the_whole_map_about_its_centre():
        lua, g = mm_seated(mh)
        lua.execute(MM_ON_TARGET)
        s = g.FS.Layout.Scale()
        mm_set(lua, "minimap.scale", 150)
        need(near(g.Minimap.scale, 1.5), f"Minimap scale {g.Minimap.scale}")
        cx, cy, w, h = g.__mmCenter()
        need(near(w, 250 * s * 1.5) and near(h, 252 * s * 1.5), f"on screen {w}x{h}")
        sx, sy = g.__mmSeat()
        need(near(cx, sx) and near(cy, sy), f"centre {cx:.2f},{cy:.2f} want {sx:.2f},{sy:.2f}")
        mm_set(lua, "minimap.scale", 100)
        need(near(g.Minimap.scale, 1.0), f"back to the default left scale {g.Minimap.scale}")
        cx, cy, w, h = g.__mmCenter()
        need(near(w, 250 * s) and near(cx, sx) and near(cy, sy), "back at the default size and place")

    @case
    def minimap_scale_grows_the_key_row_with_the_map():
        lua, g = mm_seated(mh, pixel=1.0)
        # Physical pixels: the row's height in the map's own units over the pixel the map's scale leaves.
        def row_px() -> tuple[float, float]:
            px = lua.eval("FS.FrameHelpers.PixelUnit(Minimap)")
            return g.Minimap.fsBezel.h / px, g.Minimap.fsSTUKey.w / px
        row0, key0 = row_px()
        mm_set(lua, "minimap.scale", 150)
        row1, key1 = row_px()
        need(row1 > row0 * 1.35, f"the key row is {row1:g} px tall at 150% against {row0:g} px at 100%")
        need(key1 > key0 * 1.35, f"a key is {key1:g} px wide at 150% against {key0:g} px at 100%")

    @case
    def minimap_furniture_sized_at_login_follows_a_new_width():
        lua, g = mm_seated(mh)
        s = g.FS.Layout.Scale()
        need(near(g.Minimap.fsHighlight.w, 250 * s * 0.55), f"highlight at login {g.Minimap.fsHighlight.w}")
        mm_set(lua, "minimap.w", 350)
        need(near(g.Minimap.fsHighlight.w, 350 * s * 0.55), f"the highlight glow is {g.Minimap.fsHighlight.w}")
        need(near(g.Minimap.fsZoneLabel.w, 350 * s - 18), f"the zone label is {g.Minimap.fsZoneLabel.w} wide")

    @case
    def minimap_height_follows_width_when_the_map_can_only_draw_square():
        src = mh.MINIMAP_SRC
        need("HEIGHT_FOLLOWS_WIDTH = false" in src, "the fallback switch is in the file, off")
        mh.MINIMAP_SRC = src.replace("HEIGHT_FOLLOWS_WIDTH = false", "HEIGHT_FOLLOWS_WIDTH = true")
        try:
            lua, g = mm_seated(mh)
            mm_set(lua, "minimap.w", 300)
            need(g.FS.Layout.minimap.h == round(300 * 252 / 250), f"height {g.FS.Layout.minimap.h} follows width 300")
            mm_set(lua, "minimap.h", 150)
            need(g.FS.Layout.minimap.h == round(300 * 252 / 250), "the height slider is ignored while it follows")
            need(g.FS.MinimapSettings.heightFollowsWidth is True, "the page can read why the height row is locked")
        finally:
            mh.MINIMAP_SRC = src

    @case
    def minimap_size_in_combat_waits_for_regen():
        lua, g = mm_seated(mh)
        lua.execute("MinimapCluster.protected = true; __combat = true")
        mm_set(lua, "minimap.w", 310)
        s = g.FS.Layout.Scale()
        need(near(g.Minimap.w, 250 * s), f"a protected cluster was resized in combat ({g.Minimap.w})")
        lua.execute("__combat = false; FireEvent('PLAYER_REGEN_ENABLED'); __frames(4, false)")
        need(near(g.Minimap.w, 310 * s), f"after combat {g.Minimap.w} want {310 * s}")

    return out


# ---------------------------------------------------------------------------------------------------------------------
# Quest tracker: opacity, background opacity, scale (the real Tracker.lua on the tracker skin harness's mock container)
# ---------------------------------------------------------------------------------------------------------------------

TRACKER_EXTRA = r"""
-- What the engine lacks: a frame scale and the anchors read back. ObjectiveTrackerFrame is an Edit Mode system frame, so
-- (as OnSystemLoad does) its SetScale / SetPoint / ClearAllPoints are overrides that keep the originals as *Base: a
-- call to an override is counted, because addon code must go through the Base ones.
function Obj:SetScale(s) self.scale = s end
function Obj:GetScale() return self.scale or 1 end
function Obj:GetPoint(i)
    local p = self.points[i or 1]
    if p then return p.point, p.rel, p.relPoint, p.x, p.y end
end
local buildWithoutEditMode = BuildBlizzard
function BuildBlizzard()
    buildWithoutEditMode()
    local f = ObjectiveTrackerFrame
    OVERRIDES, ALPHA_WRITES = 0, 0
    f.SetAlpha = function(self, a) ALPHA_WRITES = ALPHA_WRITES + 1; Obj.SetAlpha(self, a) end
    f.SetScaleBase, f.SetPointBase, f.ClearAllPointsBase = Obj.SetScale, Obj.SetPoint, Obj.ClearAllPoints
    f.SetScale = function() OVERRIDES = OVERRIDES + 1 end
    f.SetPoint = function() OVERRIDES = OVERRIDES + 1 end
    f.ClearAllPoints = function() OVERRIDES = OVERRIDES + 1 end
end
"""

TRACKER_PRE = r"""
    local S = FS.Tracker.state
    local C = S.chrome
    local T = ObjectiveTrackerFrame
    local COLOR_BG = FS.Theme.COLOR_BG
    local function setting(k, v) FS.Config.Set(k, v) end
    local function fillAlpha() return C.fill.vertex[4] end
    local function near(a, b) assert(a and math.abs(a - b) < 1e-9, tostring(a) .. ' want ' .. tostring(b)) end
"""


def tracker_cases() -> list[tuple[str, "callable"]]:
    tsk = load_module("trackerskin-harness.py", "trackerskin_harness")
    from charskin_support import Harness

    h = Harness({"Tracker": "Modules/Tracker/Tracker.lua"}, tsk.BLIZZARD + TRACKER_EXTRA)
    h.sources["PanelConfig"] = "local _, FS = ...\n" + CONFIG_STUB
    h.extra_names.insert(0, "PanelConfig")
    cases: list[tuple[str, "callable"]] = []

    def case(name: str, body: str) -> None:
        def run() -> None:
            err = h.run_case(TRACKER_PRE + body + "\n    Clean()")
            if err is not None:
                raise AssertionError(err)

        cases.append((name, run))

    case("tracker_keys_register_with_the_prototype_defaults", r"""
    local want = { ['tracker.w'] = 270, ['tracker.h'] = 320, ['tracker.scale'] = 100, ['tracker.alpha'] = 100, ['tracker.bgAlpha'] = 80 }
    for key, default in pairs(want) do assert(FS.Config.Get(key) == default, key .. ' default ' .. tostring(FS.Config.Get(key))) end
    local z = FS.Tracker.SIZE
    assert(z.w.min == 180 and z.w.max == 500 and z.h.min == 120 and z.h.max == 800, 'width and height range')
    assert(z.scale.min == 50 and z.scale.max == 200 and z.scale.step == 5, 'scale range')
    assert(z.alpha.min == 10 and z.alpha.max == 100 and z.alpha.step == 5, 'opacity range')
    assert(z.bgAlpha.min == 0 and z.bgAlpha.max == 100, 'background range')
""")

    case("tracker_defaults_write_nothing_to_the_container", r"""
    assert(T.scale == nil, 'a default profile wrote a scale ' .. tostring(T.scale))
    assert(ALPHA_WRITES == 0, 'a default profile wrote the container alpha ' .. ALPHA_WRITES .. ' times')
    assert(OVERRIDES == 0, 'an Edit Mode override ran')
    assert(C.fill.vertex[4] == COLOR_BG[4], 'the fill alpha is not today\'s ' .. tostring(C.fill.vertex[4]))
""")

    case("tracker_background_opacity_retints_only_the_panel_fill", r"""
    local glow, border = C.glow.vertex[4], C.border.vertex[4]
    setting('tracker.bgAlpha', 40)
    near(fillAlpha(), 0.40)
    assert(C.glow.vertex[4] == glow and C.border.vertex[4] == border, 'glow or border retinted')
    assert(T.NineSlice.alpha == 0, 'the stock art was woken')
    setting('tracker.bgAlpha', 100)
    near(fillAlpha(), 1)
    setting('tracker.bgAlpha', 0)
    near(fillAlpha(), 0)
    setting('tracker.bgAlpha', 80)
    assert(fillAlpha() == COLOR_BG[4], 'back at the default the fill is today\'s alpha exactly')
    setting('tracker.bgAlpha', 'x')
    assert(fillAlpha() == COLOR_BG[4], 'junk reads as the default')
""")

    case("tracker_opacity_fades_the_whole_container", r"""
    setting('tracker.alpha', 60)
    near(T.alpha, 0.6)
    setting('tracker.alpha', 5)
    near(T.alpha, 0.1)
    setting('tracker.alpha', 100)
    assert(T.alpha == 1, 'back to the default leaves the container solid')
    assert(OVERRIDES == 0, 'an override ran')
""")

    case("tracker_scale_goes_through_the_base_call_and_keeps_the_corner", r"""
    local point, rel, relPoint, x, y = T:GetPoint(1)
    assert(point == 'TOPRIGHT', 'the mock seat is TOPRIGHT, got ' .. tostring(point))
    setting('tracker.scale', 125)
    near(T.scale, 1.25)
    assert(OVERRIDES == 0, 'an Edit Mode override ran: addon code must use the Base calls')
    local p2, rel2, rp2, x2, y2 = T:GetPoint(1)
    assert(p2 == point and rel2 == rel and rp2 == relPoint, 'the anchor moved to another point')
    near(x2, x / 1.25); near(y2, y / 1.25)
    setting('tracker.scale', 100)
    near(T.scale, 1)
    local _, _, _, x3, y3 = T:GetPoint(1)
    near(x3, x); near(y3, y)
    assert(#T.points == 1, 'points ' .. #T.points)
""")

    case("tracker_scale_waits_for_combat_to_end", r"""
    __combat = true
    setting('tracker.scale', 150)
    assert(T.scale == nil, 'the container was scaled in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED')
    near(T.scale, 1.5)
""")

    case("tracker_scale_clamps_and_ignores_junk", r"""
    setting('tracker.scale', 999)
    near(T.scale, 2)
    setting('tracker.scale', 1)
    near(T.scale, 0.5)
    setting('tracker.scale', 'big')
    assert(T.scale == 1, 'junk reads as the default scale ' .. tostring(T.scale))
""")

    case("tracker_saved_values_are_applied_at_login", r"""
    -- The skin is built while the files run (defaults), the profile loads after them, PLAYER_LOGIN comes last.
    Reset()
    local FS2 = Load({ 'PanelConfig', 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'Tracker' })
    local T2, fill = ObjectiveTrackerFrame, FS2.Tracker.state.chrome.fill
    assert(T2.scale == nil and ALPHA_WRITES == 0, 'written before the profile was readable')
    __cfg['tracker.alpha'], __cfg['tracker.bgAlpha'], __cfg['tracker.scale'] = 70, 30, 120
    Fire('PLAYER_LOGIN')
    near(T2.alpha, 0.7); near(fill.vertex[4], 0.3); near(T2.scale, 1.2)
""")
    return cases


# ---------------------------------------------------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------------------------------------------------

def run_lua_group(boot) -> list[tuple[str, "callable"]]:
    names = sorted(k for k in boot().eval("__checks").keys())
    return [(name, (lambda n=name: boot().eval("__checks")[n]())) for name in names]


def main() -> int:
    cases = run_lua_group(chat_boot)
    mh = load_minimap_harness()
    cases += minimap_cases(mh)
    cases += tracker_cases()
    failed = 0
    for name, fn in cases:
        try:
            fn()
            print(f"ok    {name}")
        except (LuaError, AssertionError, TypeError, AttributeError) as err:
            failed += 1
            print(f"FAIL  {name}: {err}")
    print(f"{len(cases) - failed}/{len(cases)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
