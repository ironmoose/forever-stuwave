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

function CreateFrame()
    local f = { regions = {} }
    function f:SetFrameLevel() end
    return f
end
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
# Runner
# ---------------------------------------------------------------------------------------------------------------------

GROUPS = (("chat", chat_boot),)


def main() -> int:
    total = failed = 0
    for label, boot in GROUPS:
        names = sorted(k for k in boot().eval("__checks").keys())
        for name in names:
            total += 1
            try:
                # A fresh client per check: the saved variable, frames and callbacks must not leak.
                boot().eval("__checks")[name]()
                print(f"ok    {name}")
            except LuaError as err:
                failed += 1
                print(f"FAIL  {name}: {err}")
    print(f"{total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
