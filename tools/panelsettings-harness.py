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
  * the Quest tracker height (tracker.h) is Edit Mode's own Height (400 to 1000 by 10, default 800), written into the
    active layout through TrackerSeat out of combat, only for a tracker that has been moved off its default seat; the
    row is greyed until then; Width stays locked with its reason;
  * every row of the three prototype pages is registered under the prototype's key, label, range, format and parent
    switch (parsed from proto-pages.js, FS_MOCKUPS_DIR names its folder); a row that cannot be applied says why.

    python3 tools/panelsettings-harness.py          (--keys lists the prototype row keys of the three pages)

Exit 0 = every check passed.
"""

from __future__ import annotations

import os
import re
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

# Edit Mode in the tracker world: one preset (Modern) and the saved layouts; EM_WRITES keeps a copy of every SaveLayouts.
EDIT_MODE_MOCK = r"""
Enum = { EditModeSystem = { ObjectiveTracker = 12 }, EditModeLayoutType = { Preset = 0, Account = 1 },
    EditModeObjectiveTrackerSetting = { Height = 0, Opacity = 1, TextSize = 2 } }
Constants = { EditModeConsts = { EditModeMaxLayoutsPerType = 5 } }
function CopyTable(t)
    local c = {}
    for k, v in pairs(t) do c[k] = type(v) == "table" and CopyTable(v) or v end
    return c
end
local function trackerSystem(default)
    return { system = 12, isInDefaultPosition = default,
        anchorInfo = { point = "TOPRIGHT", relativeTo = "UIParent", relativePoint = "TOPRIGHT", offsetX = -110, offsetY = -260 },
        settings = { { setting = 0, value = 40 }, { setting = 1, value = 0 }, { setting = 2, value = 0 } } }
end
EditModePresetLayoutManager = { GetCopyOfPresetLayouts = function()
    return { { layoutName = "Modern", layoutType = 0, systems = { trackerSystem(true) } } }
end }
EM_SAVED, EM_ACTIVE, EM_WRITES, EM_LOADED = {}, 1, {}, true
C_EditMode = {
    GetLayouts = function()
        if not EM_LOADED then return nil end
        return { activeLayout = EM_ACTIVE, layouts = CopyTable(EM_SAVED) }
    end,
    SaveLayouts = function(info)
        EM_WRITES[#EM_WRITES + 1] = CopyTable(info)
        EM_SAVED = {}
        for _, l in ipairs(info.layouts) do if l.layoutType ~= 0 then EM_SAVED[#EM_SAVED + 1] = CopyTable(l) end end
    end,
    SetActiveLayout = function(i) EM_ACTIVE = i end,
}
-- An account layout with the tracker moved off its default seat, active (index 2: the preset is 1).
function EM_Move(height)
    local system = trackerSystem(false)
    system.settings[1].value = height or 40
    EM_SAVED = { { layoutName = "Mine", layoutType = 1, systems = { system } } }
    EM_ACTIVE = 2
end
-- The raw Height the active saved layout holds.
function EM_Height() return EM_SAVED[EM_ACTIVE - 1].systems[1].settings[1].value end
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

    h = Harness({"Tracker": "Modules/Tracker/Tracker.lua", "TrackerSeat": "Modules/Tracker/TrackerSeat.lua"},
                tsk.BLIZZARD + TRACKER_EXTRA + EDIT_MODE_MOCK)
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
    -- Height is Edit Mode's own (400 to 1000 by 10, the game's default 800), not the prototype's 120 to 800 by 1 at 320.
    local want = { ['tracker.w'] = 270, ['tracker.h'] = 800, ['tracker.scale'] = 100, ['tracker.alpha'] = 100, ['tracker.bgAlpha'] = 80 }
    for key, default in pairs(want) do assert(FS.Config.Get(key) == default, key .. ' default ' .. tostring(FS.Config.Get(key))) end
    local z = FS.Tracker.SIZE
    assert(z.w.min == 180 and z.w.max == 500, 'width range')
    assert(z.h.min == 400 and z.h.max == 1000 and z.h.step == 10 and z.h.default == 800, 'height is the range Edit Mode accepts')
    local e = FS.TrackerSeat.HEIGHT
    assert(e.min == z.h.min and e.max == z.h.max and e.step == z.h.step and e.default == z.h.default, 'the setting and TrackerSeat agree')
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

    case("tracker_height_default_writes_nothing_to_edit_mode_even_for_a_moved_tracker", r"""
    EM_Move(30)   -- the player's own Edit Mode height (700) is not ours to touch
    Fire('PLAYER_LOGIN'); Fire('PLAYER_ENTERING_WORLD'); Fire('EDIT_MODE_LAYOUTS_UPDATED')
    assert(#EM_WRITES == 0, 'a default profile saved the layout ' .. #EM_WRITES .. ' times')
    assert(EM_Height() == 30, 'the height changed')
    assert(FS.Tracker.WantedHeight() == nil, 'nothing is wanted while the setting holds its default')
    assert(OVERRIDES == 0, 'an Edit Mode override ran')
""")

    case("tracker_height_is_written_into_the_active_edit_mode_layout_as_the_raw_value", r"""
    EM_Move()
    setting('tracker.h', 900)
    assert(#EM_WRITES == 1, 'saves ' .. #EM_WRITES)
    assert(EM_Height() == 50, 'raw ' .. tostring(EM_Height()) .. ' for 900')
    assert(#EM_WRITES[1].layouts == 2 and EM_WRITES[1].activeLayout == 2, 'edited in place, the same layout stays active')
    assert(OVERRIDES == 0, 'an Edit Mode override ran: the layout is the only way in')
    setting('tracker.h', 1000); assert(EM_Height() == 60, 'the top of the range')
    setting('tracker.h', 400); assert(EM_Height() == 0, 'the bottom of the range')
    setting('tracker.h', 9999); assert(EM_Height() == 60, 'above the range holds at 1000')
""")

    case("tracker_height_moved_back_to_the_default_puts_the_layout_back", r"""
    EM_Move()
    setting('tracker.h', 900)
    assert(EM_Height() == 50)
    setting('tracker.h', 800)   -- the default: stored as nothing, but it is still a choice of the player
    assert(EM_Height() == 40, 'back to 800 in the layout, got raw ' .. tostring(EM_Height()))
    assert(#EM_WRITES == 2, 'saves ' .. #EM_WRITES)
    assert(FS.Tracker.WantedHeight() == nil)
""")

    case("tracker_height_waits_for_combat_to_end", r"""
    EM_Move()
    __combat = true
    setting('tracker.h', 900)
    assert(#EM_WRITES == 0, 'the layout was saved in combat')
    Fire('PLAYER_REGEN_ENABLED')
    assert(#EM_WRITES == 0, 'still in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED')
    assert(EM_Height() == 50, 'applied when combat ended')
    Fire('PLAYER_REGEN_ENABLED')
    assert(#EM_WRITES == 1, 'applied once, not again')
    -- a choice of the default made in combat is held too, and wins after it
    __combat = true
    setting('tracker.h', 800)
    __combat = false
    Fire('PLAYER_REGEN_ENABLED')
    assert(EM_Height() == 40, 'the default chosen in combat was put back')
""")

    case("tracker_height_in_the_default_seat_writes_nothing_and_a_move_carries_it", r"""
    -- on a preset, the tracker in its default seat: the game ignores a height there, so nothing is copied for it
    setting('tracker.h', 900)
    assert(#EM_WRITES == 0, 'saved a layout for a tracker that is in its default seat')
    assert(FS.Tracker.WantedHeight() == 900)
    local ok = FS.TrackerSeat.Move(-20, -300)
    assert(ok == true, 'the move')
    assert(#EM_WRITES == 1, 'one save for the seat and the height: ' .. #EM_WRITES)
    assert(EM_Height() == 50, 'the move carried the height the setting asks for')
""")

    case("tracker_saved_height_is_applied_at_login_once_the_layouts_can_be_read", r"""
    Reset()
    EM_LOADED = false
    local FS2 = Load({ 'PanelConfig', 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'Tracker', 'TrackerSeat' })
    EM_Move()
    __cfg['tracker.h'] = 900
    Fire('PLAYER_LOGIN')
    assert(#EM_WRITES == 0, 'the layouts could not be read yet')
    Fire('PLAYER_ENTERING_WORLD')
    assert(#EM_WRITES == 0, 'still not readable')
    EM_LOADED = true
    Fire('EDIT_MODE_LAYOUTS_UPDATED')
    assert(EM_Height() == 50 and #EM_WRITES == 1, 'applied once they could be read')
    -- from here the player may use Edit Mode's own slider: the saved setting does not fight it
    EM_SAVED[1].systems[1].settings[1].value = 20
    Fire('EDIT_MODE_LAYOUTS_UPDATED'); Fire('PLAYER_ENTERING_WORLD')
    assert(#EM_WRITES == 1 and EM_Height() == 20, 'the login sync ran again')
""")

    case("tracker_saved_height_is_applied_at_login_itself_when_the_layouts_are_readable", r"""
    EM_Move()
    __cfg['tracker.h'] = 700
    Fire('PLAYER_LOGIN')
    assert(#EM_WRITES == 1 and EM_Height() == 30, 'login alone applied it: saves ' .. #EM_WRITES)
""")

    case("tracker_saved_height_at_login_with_a_tracker_in_its_default_seat_is_left_for_the_move", r"""
    __cfg['tracker.h'] = 900
    Fire('PLAYER_LOGIN')
    assert(#EM_WRITES == 0, 'a preset was copied at login')
    Fire('EDIT_MODE_LAYOUTS_UPDATED')
    assert(#EM_WRITES == 0)
""")

    case("tracker_height_does_nothing_while_the_module_has_no_seat", r"""
    FS.TrackerSeat = nil
    setting('tracker.h', 900)
    Fire('PLAYER_LOGIN')
    assert(#EM_WRITES == 0)
""")
    return cases


# ---------------------------------------------------------------------------------------------------------------------
# The three pages against the prototype's rows
# ---------------------------------------------------------------------------------------------------------------------

PROTO = Path(os.environ.get("FS_MOCKUPS_DIR", ADDON.parent / "mockups")) / "proto-src-2026-11-25/proto-pages.js"

# Rows whose words differ from the prototype's on purpose, and why.
# Rows whose range or default differ from the prototype's on purpose: the prototype's tracker height (120 to 800 by 1, 320) is
# not something Edit Mode accepts; the game's own Height is 400 to 1000 by 10 and its default is 800.
RANGE_DEVIATIONS = {"tracker.h": (400, 1000, 10)}
DEFAULT_DEVIATIONS = {"tracker.h": 800}

TIP_DEVIATIONS = {
    "tracker.w": "locked: the page gives the reason in place of the layout editor tip",
    "tracker.h": "real now: the tip says it is Edit Mode's own Height (the prototype's tip is about the list scrolling)",
    "chat.band.raid": "the prototype's tip is the one word 'New.'",
}


def js_value(text: str, i: int):
    """One JS literal at text[i:]: a quoted string, a number, a bool or a flat array. Returns (value, next index)."""
    if text[i] == "'":
        out, i = [], i + 1
        while text[i] != "'":
            if text[i] == "\\":
                i += 1
            out.append(text[i])
            i += 1
        return "".join(out), i + 1
    if text[i] == "[":
        items, i = [], i + 1
        while text[i] != "]":
            if text[i] == ",":
                i += 1
                continue
            value, i = js_value(text, i)
            items.append(value)
        return items, i + 1
    j = i
    while j < len(text) and text[j] not in ",}]":
        j += 1
    word = text[i:j].strip()
    if word in ("true", "false"):
        return word == "true", j
    try:
        return (int(word) if word.lstrip("-").isdigit() else float(word)), j
    except ValueError:
        return word, j


def proto_rows(page: str) -> list[dict]:
    """The rows of one prototype page ({key:'<page>', ...} up to the next page), in order, as dicts."""
    text = PROTO.read_text(encoding="utf-8")
    start = text.index(f" {{key:'{page}',label:")
    end = text.index("\n {key:", start + 5)
    block = text[start:end]
    rows = []
    for m in re.finditer(r"\{ty:'(\w+)'", block):
        i, row = m.start() + 1, {}
        while block[i] != "}":
            if block[i] in ", ":
                i += 1
                continue
            j = block.index(":", i)
            name = block[i:j]
            value, i = js_value(block, j + 1)
            row[name] = value
        rows.append(row)
    return rows


def dump(obj):
    """A Lua table as plain Python (a function becomes the string '<function>')."""
    if hasattr(obj, "items"):
        items = dict(obj.items())
        if items and all(isinstance(k, int) for k in items):
            return [dump(items[k]) for k in sorted(items)]
        return {k: dump(v) for k, v in items.items()}
    return "<function>" if callable(obj) else obj


PAGE_RECORDER = r"""
-- A recorder in place of the window: every builder call is kept as a row, in order.
__rows, __sections, __cat = {}, {}, nil
local function add(kind, o)
    __rows[#__rows + 1] = { kind = kind, o = o }
    return {}
end
local UI = {
    Section = function(_, o) __sections[#__sections + 1] = o end,
    Toggle = function(_, o) return add("switch", o) end,
    Segmented = function(_, o) return add("segmented", o) end,
    Slider = function(_, o) return add("slider", o) end,
}
FS.ConfigWindow = { UI = UI, RegisterCategory = function(c) __cat = c end }
"""


def page_world(fixtures: dict, page_file: str, setup: str = "") -> "LuaRuntime":
    """One real page file loaded on a recorder and the given module fixtures, built; `setup` is Lua run before it loads."""
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute("FS = {}")
    for name, value in fixtures.items():
        lua.globals().__fixture = lua.table_from(to_lua_deep(lua, value)) if isinstance(value, (dict, list)) else value
        lua.execute(f"FS[{name!r}] = __fixture")
    lua.execute(setup)
    lua.execute(PAGE_RECORDER)
    src = (ADDON / "Modules/Config" / page_file).read_text(encoding="utf-8")
    lua.execute("function __load(src) return assert(loadstring(src, '=page'))('forever-stuwave', FS) end")
    lua.eval("__load")(src)
    lua.execute("__cat.tabs[1].build({})")
    return lua


def page_rows(fixtures: dict, page_file: str) -> list[dict]:
    """Loads one real page file on a recorder and the given module fixtures; returns what its build asked for."""
    lua = page_world(fixtures, page_file)
    out = []
    for row in dump(lua.eval("__rows")):
        o = dict(row["o"])
        o["kind"] = row["kind"]
        out.append(o)
    return out


def to_lua_deep(lua, value):
    if isinstance(value, dict):
        return lua.table_from({k: (lua.table_from(to_lua_deep(lua, v)) if isinstance(v, (dict, list)) else v) for k, v in value.items()})
    if isinstance(value, list):
        return lua.table_from([(lua.table_from(to_lua_deep(lua, v)) if isinstance(v, (dict, list)) else v) for v in value])
    return value


def lua_data(lua, expr: str):
    return dump(lua.eval(expr))


def module_fixtures(mh) -> tuple[dict, dict]:
    """The real modules' specs and registered defaults, read from their own worlds: (fixtures by FS name, defaults by key)."""
    fixtures: dict = {}
    defaults: dict = {}

    # Chat: the size from ChatWindowState (the chat reseat world), the fill from ChatFrameSkin, the tint from ChatFormat.
    rs = load_module("chatreseat-harness.py", "chatreseat_harness")
    lua = rs.boot()
    chat = {"SIZE": lua_data(lua, "FS.Chat.SIZE")}
    defaults.update({"chat.w": chat["SIZE"]["w"]["default"], "chat.h": chat["SIZE"]["h"]["default"]})
    skin = chat_boot()
    chat["BG"] = lua_data(skin, "FS.Chat.BG")
    defaults["chat.bgAlpha"] = skin.eval("FS.Config.Get('chat.bgAlpha')")
    fixtures["Chat"] = chat
    cf = load_module("chatformat-harness.py", "chatformat_harness")
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.globals().SRC, rt.globals().CORE = cf.SRC, cf.CORE
    rt.execute(cf.MOCK)
    fixtures["ChatFormat"] = {
        "BAND_SPEC": dump(rt.eval("FS.ChatFormat.BAND_SPEC")),
        "BAND_SETTING": dump(rt.eval("FS.ChatFormat.BAND_SETTING")),
    }
    defaults.update(dump(rt.eval("__config")))
    # Minimap and the coords switch.
    lua, g = mm_seated(mh)
    fixtures["MinimapSettings"] = lua_data(lua, "FS.MinimapSettings")
    fixtures["MinimapCoords"] = lua_data(lua, "FS.MinimapCoords")
    for key in ("minimap.w", "minimap.h", "minimap.scale", "minimap.coords"):
        defaults[key] = lua.eval(f"FS.Config.Get({key!r})")
    return fixtures, defaults


def tracker_fixture() -> tuple[dict, dict]:
    tsk = load_module("trackerskin-harness.py", "trackerskin_harness")
    from charskin_support import Harness

    h = Harness({"Tracker": "Modules/Tracker/Tracker.lua"}, tsk.BLIZZARD + TRACKER_EXTRA)
    h.sources["PanelConfig"] = "local _, FS = ...\n" + CONFIG_STUB
    h.extra_names.insert(0, "PanelConfig")
    rt = h.runtime()
    rt.execute(h.load_line() + "\nfunction __out() return FS.Tracker.SIZE, FS.Tracker.SIZE_LOCKED end")
    size, locked = rt.eval("__out()")
    size = dump(size)
    return {"Tracker": {"SIZE": size, "SIZE_LOCKED": locked}}, {v["key"]: v["default"] for v in size.values()}


UNITS = {"px": "%d px", "%": "%d%%"}
KINDS = {"sl": "slider", "sw": "switch", "seg": "segmented"}


def page_cases(mh) -> list[tuple[str, "callable"]]:
    out = []
    fixtures, defaults = module_fixtures(mh)
    tracker, tracker_defaults = tracker_fixture()
    defaults.update(tracker_defaults)
    timer = {"QuestTimer": {"SETTING": {"label": "Quest timer under the minimap", "key": "questTimer.shown",
                                       "tip": "Shows quest timers in a strip under the minimap, in place of the game's own timer window."}}}

    def check_page(page: str, file: str, extra: dict) -> None:
        wanted = [r for r in proto_rows(page) if r["ty"] in KINDS]
        got = page_rows({**fixtures, **tracker, **timer, **extra}, file)
        by_key = {r.get("key"): r for r in got}
        need(len(by_key) == len(got), "a key is registered twice")
        need(set(by_key) == {r["k"] for r in wanted},
             f"keys differ: missing {sorted({r['k'] for r in wanted} - set(by_key))}, extra {sorted(set(by_key) - {r['k'] for r in wanted})}")
        for row in wanted:
            key, mine = row["k"], by_key[row["k"]]
            where = f"{key}"
            need(mine["kind"] == KINDS[row["ty"]], f"{where}: a {mine['kind']} for a {row['ty']}")
            need(mine["label"] == row["l"], f"{where}: label {mine['label']!r} want {row['l']!r}")
            if row["ty"] == "sl":
                want_range = RANGE_DEVIATIONS.get(key, (row["min"], row["max"], row["st"]))
                need((mine["min"], mine["max"], mine["step"]) == want_range,
                     f"{where}: range {mine['min']}-{mine['max']} by {mine['step']}, want {want_range}")
                need(mine.get("fmt") == UNITS[row["u"]], f"{where}: format {mine.get('fmt')!r}")
            if row["ty"] == "seg":
                need([o["value"] for o in mine["options"]] == row["o"], f"{where}: options")
            if key in defaults:
                want = DEFAULT_DEVIATIONS.get(key, row["d"])
                if row["ty"] == "seg" or isinstance(want, bool) or not isinstance(want, str):
                    need(defaults[key] == want, f"{where}: default {defaults[key]!r}, prototype {want!r}")
            need(bool(mine.get("sub")) == bool(row.get("sub")), f"{where}: sub")
            need(mine.get("needs") == row.get("needs"), f"{where}: needs {mine.get('needs')!r}")
            if row.get("needs"):
                need(mine.get("nl") == row.get("nl"), f"{where}: nl {mine.get('nl')!r} want {row.get('nl')!r}")
            if key not in TIP_DEVIATIONS and row.get("tip") is not None:
                need(mine.get("tip") == row["tip"], f"{where}: tip {mine.get('tip')!r}")

    def make(page, file, extra=None):
        def run():
            check_page(page, file, extra or {})
        return run

    out.append(("page_chat_registers_every_prototype_row", make("chat", "ConfigPageChat.lua")))
    out.append(("page_minimap_registers_every_prototype_row", make("mini", "ConfigPageMinimap.lua")))
    out.append(("page_tracker_registers_every_prototype_row", make("track", "ConfigPageTracker.lua")))

    def width_locked():
        rows = {r["key"]: r for r in page_rows({**tracker, **timer}, "ConfigPageTracker.lua")}
        row = rows["tracker.w"]
        need(row.get("reason") and row.get("enabled") is not None, "tracker.w is not locked with a reason")
        need(row["reason"] == tracker["Tracker"]["SIZE_LOCKED"], "tracker.w reason")
        need("Width" in row["reason"] and "Edit Mode" in row["reason"], f"the reason names the cause: {row['reason']!r}")
        lua = page_world({**tracker, **timer}, "ConfigPageTracker.lua", "FS.TrackerSeat = { Moved = function() return true end }")
        need(lua.eval("__rows[1].o.enabled()") is False, "the width row is live")

    out.append(("page_tracker_width_says_why_it_is_locked", width_locked))

    def height_row():
        rows = {r["key"]: r for r in page_rows({**tracker, **timer}, "ConfigPageTracker.lua")}
        row = rows["tracker.h"]
        need(row["kind"] == "slider" and row["label"] == "Height" and row["fmt"] == "%d px", "a Height slider in px")
        need((row["min"], row["max"], row["step"]) == (400, 1000, 10), "the range Edit Mode accepts")
        tip = row.get("tip", "")
        for words in ("Edit Mode", "400 to 1000", "default seat", "after combat"):
            need(words in tip, f"the tip says {words!r}: {tip!r}")
        need(row.get("enabled") is not None and row.get("reason"), "the row greys out with a reason while it cannot apply")
        reason = row.get("reason") or ""
        for words in ("default seat", "/fsedit"):
            need(words in reason, f"the reason says {words!r}: {reason!r}")
        need("\u2014" not in tip + reason and "\u2013" not in tip + reason, "no em or en dash")

    out.append(("page_tracker_height_is_edit_modes_own_with_a_tip_and_a_reason", height_row))

    def height_enabled_follows_the_seat():
        def enabled(setup: str):
            lua = page_world({**tracker, **timer}, "ConfigPageTracker.lua", setup)
            return lua.eval("__rows[2].o.enabled()")

        need(enabled("FS.TrackerSeat = { Moved = function() return true end }") is True, "a moved tracker enables Height")
        need(enabled("FS.TrackerSeat = { Moved = function() return false end }") is False, "a tracker in its default seat does not")
        need(enabled("FS.TrackerSeat = { Moved = function() return nil end }") is False, "an unreadable layout does not")
        need(enabled("FS.TrackerSeat = { Moved = function() error('boom') end }") is False, "a throwing seat does not")
        need(enabled("FS.TrackerSeat = nil") is False, "no seat module does not")
        need(enabled("FS.TrackerSeat = {}") is False, "a seat without Moved does not")

    out.append(("page_tracker_height_is_live_only_for_a_tracker_that_has_been_moved", height_enabled_follows_the_seat))

    def tint_rows():
        rows = {r["key"]: r for r in page_rows(fixtures, "ConfigPageChat.lua")}
        for kind in ("guild", "party", "whisper", "raid"):
            on, colour = rows[f"chat.band.{kind}"], rows[f"chat.band.{kind}C"]
            need(on.get("needs") == "chat.lineBands", f"{kind}: the switch needs the master")
            need(colour.get("needs") == f"chat.band.{kind}", f"{kind}: the colour needs its own switch")
        need(rows["chat.bandAlpha"].get("needs") == "chat.lineBands", "strength needs the master")
        need(defaults["chat.band.raid"] is False, "the raid kind is off by default")

    out.append(("page_chat_tint_rows_chain_the_master_the_kind_and_the_colour", tint_rows))

    def height_row():
        spec = dict(fixtures["MinimapSettings"], heightFollowsWidth=True)
        rows = {r["key"]: r for r in page_rows({**fixtures, "MinimapSettings": spec}, "ConfigPageMinimap.lua")}
        need(rows["minimap.h"]["enabled"] is not None and rows["minimap.h"].get("reason"), "locked with a reason")

    out.append(("page_minimap_height_row_locks_when_the_map_can_only_draw_square", height_row))

    def missing_modules():
        for file in ("ConfigPageChat.lua", "ConfigPageMinimap.lua", "ConfigPageTracker.lua"):
            need(page_rows({}, file) == [], f"{file}: rows without their module")

    out.append(("pages_leave_a_row_out_when_its_module_is_absent", missing_modules))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------------------------------------------------

def run_lua_group(boot) -> list[tuple[str, "callable"]]:
    names = sorted(k for k in boot().eval("__checks").keys())
    return [(name, (lambda n=name: boot().eval("__checks")[n]())) for name in names]


def main() -> int:
    if "--keys" in sys.argv:
        for page in ("chat", "mini", "track"):
            print(page, " ".join(r["k"] for r in proto_rows(page) if r["ty"] in KINDS))
        return 0
    cases = run_lua_group(chat_boot)
    mh = load_minimap_harness()
    cases += minimap_cases(mh)
    cases += tracker_cases()
    cases += page_cases(mh)
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
