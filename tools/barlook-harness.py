#!/usr/bin/env python3
"""Runs the real FrameHelpers.SetBarLook against a StatusBar fill texture that tiles the way the client's does.

Why this exists: bars-harness stubs SetBarLook, and the action bar mock's Texture:SetTexture swallowed its wrap
arguments and SetHorizTile did nothing, so nothing could tell that the led, slant and chevron looks drew a flat bar in
the game. In the client a texture only repeats when it was loaded with the REPEAT wrap mode; SetHorizTile(true) on a
CLAMP texture asks for coordinates past 1 and the engine smears the tile's last column across the bar.

What is pinned: each tiled look (led, slant, chevron) loads its file with REPEAT horizontally and sets the tile flag,
so it really repeats; flat, stock and a return to cut load with CLAMP and no tile; the files named exist; looks can be
swapped in any order.

It is NOT a rendering test: the tile shapes are checked in the tile generator's pixels, and the real draw is an in-game
check (docs/TESTING.md).

    python3 tools/barlook-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"

spec = importlib.util.spec_from_file_location("actionbars_harness", HERE / "actionbars-harness.py")
abh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(abh)


def _theme_chevron_strip() -> str:
    src = (ADDON / "Core/Theme.lua").read_text(encoding="utf-8")
    m = re.search(r'^Theme\.CAST_CHEVRON_STRIP_TEXTURE\s*=\s*("[^"]*")', src, re.M)
    if not m:
        sys.exit("Theme.CAST_CHEVRON_STRIP_TEXTURE not found in Theme.lua")
    return m.group(1)


CHECKS = r"""
local T = {}
local H = FS.FrameHelpers

local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end

-- The fill texture as the client treats it: SetTexture(path, horizWrap, vertWrap) with CLAMP the default, and the
-- tile flag only repeating a texture whose wrap mode is REPEAT.
local function fill()
    local t = { _h = "CLAMP", _v = "CLAMP", _tile = false }
    function t:SetTexture(path, h, v) self._path, self._h, self._v = path, h or "CLAMP", v or "CLAMP" end
    function t:SetHorizTile(on) self._tile = on and true or false end
    function t:Repeats() return self._tile and self._h == "REPEAT" end
    return t
end

local function newBar()
    local f = CreateFrame("Frame", nil, UIParent)
    local tex = fill()
    local bar = CreateFrame("StatusBar", nil, f)
    bar.shell = f
    bar.fsRail = nil
    bar.fsPillOpts = nil
    bar.GetStatusBarTexture = function() return tex end
    return bar, tex
end

H.BAR_LOOK_TILES.chevron = H.BAR_LOOK_TILES.chevron or __CHEVRON
FS.Theme.COLOR_BAR_TRACK = FS.Theme.COLOR_BAR_TRACK or { 0, 0, 0, 1 }
FS.Theme.COLOR_BAR_BORDER = FS.Theme.COLOR_BAR_BORDER or { 1, 1, 1, 1 }

function T.the_tiled_looks_load_their_file_with_the_repeat_wrap()
    for _, look in ipairs({ "led", "slant", "chevron" }) do
        local bar, tex = newBar()
        H.SetBarLook(bar, look)
        eq(tex._path, H.BAR_LOOK_TILES[look], look .. " uses its own tile file")
        eq(tex._tile, true, look .. " asks for the tile")
        eq(tex:Repeats(), true, look .. " really repeats (REPEAT wrap, not a clamped smear)")
    end
end

function T.the_untiled_looks_and_a_return_to_cut_do_not_repeat()
    for _, look in ipairs({ "flat", "stock" }) do
        local bar, tex = newBar()
        H.SetBarLook(bar, "slant")
        H.SetBarLook(bar, look)
        eq(tex._tile, false, look .. " after slant: no tile")
        eq(tex._h, "CLAMP", look .. " after slant: clamped again")
    end
end

function T.looks_swap_in_any_order()
    local bar, tex = newBar()
    for _, look in ipairs({ "led", "stock", "chevron", "flat", "slant", "led" }) do
        H.SetBarLook(bar, look)
        local tiled = H.BAR_LOOK_TILES[look] ~= nil
        eq(tex:Repeats(), tiled, look)
    end
end

return T
"""


def boot():
    lua = abh.boot()
    lua.execute("__CHEVRON = " + _theme_chevron_strip())
    return lua


def main() -> int:
    for name in ("bar_led_tile.tga", "bar_slant_tile.tga", "cast_chevron_strip.tga"):
        if not (ADDON / "Media/Textures" / name).is_file():
            print(f"FAIL  missing texture {name}")
            return 1
    names = sorted(boot().execute(CHECKS).keys())
    failed = 0
    for name in names:
        try:
            boot().execute(CHECKS)[name]()
            print(f"ok    {name}")
        except LuaError as err:
            failed += 1
            print(f"FAIL  {name}: {err}")
    print(f"{len(names) - failed}/{len(names)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
