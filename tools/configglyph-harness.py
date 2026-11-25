#!/usr/bin/env python3
"""The config window's section chevrons and dropdown caret are drawn, not typed.

The window's font (Theme.FONT_MONO) has no triangle glyphs, so a typed ">" or "v" reads as a greater-than sign and a
letter, not as the prototype's small triangles (U+25B8 and U+25BE). The glyph helper the data bar arrows already use
(I.NewArrowGlyph, ConfigBuilders.lua) draws them from rects instead. These checks run the real window and pin:

  * the premise: the window's font file lacks U+25B8 and U+25BE (read with fontTools), so a typed triangle cannot work;
  * the helper draws all four directions on whole units, centred on its host (left and right 4 by 8, up and down 8 by 4);
  * a folding section's chevron is a pixel triangle in an 8 by 8 cell in the gutter the page leaves left of the content:
    a 4 by 8 right triangle while folded, an 8 by 4 down triangle while open, no typed character anywhere on the header;
  * its looks (the prototype's .chev): dim violet while folded, cyan while the header is hovered, gone while open and
    idle; a click flips the glyph and keeps the hover look; a search jump that opens a section repaints it; a section
    that does not fold has none;
  * the dropdown's caret is a cyan 8 by 4 down triangle in an 8 by 8 cell 8 units from the button's right edge, a child
    of the button so a disabled control dims it with itself.

    python3 tools/configglyph-harness.py

Exit 0 = every check passed. The mock draws nothing; the look in the client is pending the owner's review.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ADDON = ROOT / "forever-stuwave"
BUILDERS_FILE = Path(os.environ.get("CONFIGBUILDERS_LUA", ADDON / "Modules/Config/ConfigBuilders.lua"))
THEME_FILE = ADDON / "Core/Theme.lua"


def load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load("configwindow_harness", "configwindow-harness.py")
LuaError = base.LuaError

_config_files = base.config_files


def config_files():
    return [BUILDERS_FILE if p.name == "ConfigBuilders.lua" else p for p in _config_files()]


base.config_files = config_files

CHECKS = r"""
local function eqc(a, b, msg)
    for i = 1, 3 do
        if math.abs((a[i] or 0) - (b[i] or 0)) > 0.002 then
            error((msg or "colour") .. ": got " .. table.concat(a, ",") .. ", want " .. table.concat(b, ","), 2)
        end
    end
end
local function same(a, c) for i = 1, 3 do if math.abs(a[i] - c[i]) > 0.002 then return false end end return true end

-- The rect extents of a glyph on its host, in units from the host's centre: l, r, t, b and the columns left to right.
local function glyphBox(glyph, host)
    yes(glyph and #glyph.textures > 0, "the glyph is made of rects")
    local l, r, t, b = math.huge, -math.huge, -math.huge, math.huge
    local rects = {}
    for _, tex in ipairs(glyph.textures) do
        local p = tex.points[1]
        eq(p.point, "TOPLEFT"); eq(p.rel, host, "anchored to its host"); eq(p.relPoint, "CENTER")
        eq(p.x, math.floor(p.x), "whole unit x"); eq(p.y, math.floor(p.y), "whole unit y")
        eq(tex.w, math.floor(tex.w), "whole unit wide"); eq(tex.h, math.floor(tex.h), "whole unit tall")
        l, r = math.min(l, p.x), math.max(r, p.x + tex.w)
        t, b = math.max(t, p.y), math.min(b, p.y - tex.h)
        rects[#rects + 1] = { x = p.x, y = p.y, w = tex.w, h = tex.h }
    end
    table.sort(rects, function(a, c) if a.x ~= c.x then return a.x < c.x end return a.y > c.y end)
    return l, r, t, b, rects
end

-- One page with two folding sections, one folded and one open, and one that never folds.
local function foldPage(W)
    local made = {}
    W.RegisterCategory({ key = "gl", label = "Glyphs", group = "GENERAL", order = 71, build = function(c)
        made.folded = W.UI.Section(c, { title = "Closed", fold = true })
        W.UI.Toggle(c, { label = "Inside", key = "gl.inside" })
        made.open = W.UI.Section(c, { title = "Opened", fold = true })
        W.UI.Toggle(c, { label = "Inside too", key = "gl.inside2" })
        made.plain = W.UI.Section(c, { title = "Plain" })
        W.UI.Toggle(c, { label = "Inside plain", key = "gl.inside3" })
    end })
    FS.Config.RegisterDefault("gl.inside", false)
    FS.Config.RegisterDefault("gl.inside2", false)
    FS.Config.RegisterDefault("gl.inside3", false)
    return made
end

local function openFoldPage(W)
    local made = foldPage(W)
    W.Open("gl")
    -- sections start folded; the second one is opened by its click, as a player would
    local open = made.open
    open.header.scripts.OnClick(open.header)
    return made
end

local function shownPieces(glyph)
    local n = 0
    for _, t in ipairs(glyph.textures) do if t:IsVisible() then n = n + 1 end end
    return n
end

-- Which of a chevron's two glyphs is on screen: "right", "down" or nil.
local function chevronShows(sec)
    local cell = sec.chevron
    local out
    for name, glyph in pairs(cell.fsGlyphs) do
        if shownPieces(glyph) == #glyph.textures then
            eq(out, nil, "only one triangle shows at a time")
            out = name
        else
            eq(shownPieces(glyph), 0, name .. " triangle is whole or gone")
        end
    end
    return out
end

local function chevronColor(sec)
    local glyph = sec.chevron.fsGlyphs[chevronShows(sec)]
    local c = glyph.textures[1].color
    for _, t in ipairs(glyph.textures) do eqc(t.color, c, "one colour across the glyph") end
    return c
end

-- ---- the glyph helper ------------------------------------------------------------------------------------------------

function T.the_glyph_helper_draws_all_four_directions_on_whole_units_centred_on_its_host()
    local W = boot()
    local host = CreateFrame("Frame", nil, UIParent)
    local want = {
        left = { 4, 8, { 1, 2 }, { 1, 4 }, { 1, 6 }, { 1, 8 } },
        right = { 4, 8, { 1, 8 }, { 1, 6 }, { 1, 4 }, { 1, 2 } },
        up = { 8, 4, { 2, 1 }, { 4, 1 }, { 6, 1 }, { 8, 1 } },
        down = { 8, 4, { 8, 1 }, { 6, 1 }, { 4, 1 }, { 2, 1 } },
    }
    for direction, spec in pairs(want) do
        local glyph = W.I.NewArrowGlyph(host, direction)
        eq(glyph.direction, direction)
        local l, r, t, b, rects = glyphBox(glyph, host)
        if direction == "up" or direction == "down" then   -- listed top to bottom; the others left to right
            table.sort(rects, function(a, c) return a.y > c.y end)
        end
        eq(r - l, spec[1], direction .. " width"); eq(t - b, spec[2], direction .. " height")
        eq(l + r, 0, direction .. " centred across"); eq(t + b, 0, direction .. " centred up and down")
        eq(#rects, 4, direction .. " is four rects")
        for i = 1, 4 do
            eq(rects[i].w, spec[2 + i][1], direction .. " rect " .. i .. " width")
            eq(rects[i].h, spec[2 + i][2], direction .. " rect " .. i .. " height")
        end
    end
end

function T.the_horizontal_arrow_size_the_tab_mark_frame_takes_is_still_exported()
    local W = boot()
    eq(W.I.ARROW_W, 4); eq(W.I.ARROW_H, 8)
end

-- ---- section chevrons ------------------------------------------------------------------------------------------------

function T.a_folding_section_header_has_no_typed_chevron_and_a_cell_for_a_pixel_one()
    local W = boot()
    local made = openFoldPage(W)
    for _, sec in ipairs({ made.folded, made.open }) do
        for _, t in ipairs(texts(sec.header)) do
            no(t == ">" or t == "v" or t == "^" or t == "<", "a typed arrow '" .. t .. "' is left on the header")
        end
        local cell = sec.chevron
        yes(cell and cell.isFrame, "the chevron is a frame of pixel rects")
        eq(cell.parent, sec.header)
        eq(cell.w, 8); eq(cell.h, 8)
        local p = cell.points[1]
        eq(p.point, "LEFT"); eq(p.rel, sec.header); eq(p.relPoint, "LEFT")
        eq(p.x, -8, "the cell fills the 8 unit gutter the page clips left of the content, never past it")
        eq(p.y, 0)
    end
end

function T.a_section_that_does_not_fold_has_no_chevron()
    local W = boot()
    local made = openFoldPage(W)
    eq(made.plain.chevron, nil)
    eq(made.plain.PaintChevron, nil)
end

function T.a_folded_chevron_is_a_4_by_8_triangle_pointing_right_and_an_open_one_8_by_4_pointing_down()
    local W = boot()
    local made = openFoldPage(W)
    local cell = made.folded.chevron
    local l, r, t, b, rects = glyphBox(cell.fsGlyphs.right, cell)
    eq(r - l, 4); eq(t - b, 8)
    eq(l + r, 0, "centred across the cell"); eq(t + b, 0, "centred up and down")
    for i = 1, 4 do eq(rects[i].h, 10 - 2 * i, "the columns shrink toward the point on the right") end
    l, r, t, b, rects = glyphBox(cell.fsGlyphs.down, cell)
    eq(r - l, 8); eq(t - b, 4)
    eq(l + r, 0); eq(t + b, 0)
    for i = 1, 4 do eq(rects[i].w, 10 - 2 * i, "the rows shrink toward the point at the bottom") end
    eq(chevronShows(made.folded), "right", "a folded section shows the right triangle")
    eq(chevronShows(made.open), nil, "an open idle one shows nothing")
    made.open.header.scripts.OnEnter(made.open.header)
    eq(chevronShows(made.open), "down", "an open section shows the down triangle while it is hovered")
end

function T.a_chevron_is_dim_violet_while_folded_cyan_while_hovered_and_gone_when_open_and_idle()
    local W = boot()
    local made = openFoldPage(W)
    local f, o = made.folded, made.open
    -- folded, idle: the window's dim violet, never the cyan of a lit control
    local dim = chevronColor(f)
    no(same(dim, W.C.cyan), "folded idle is not cyan")
    yes(dim[1] > 0.3 and dim[1] < 0.45 and dim[3] > 0.45 and dim[3] < 0.55, "folded idle is the window's dim violet")
    f.header.scripts.OnEnter(f.header)
    eqc(chevronColor(f), W.C.cyan, "hovered: cyan")
    eq(chevronShows(f), "right", "hovering a folded section keeps the right triangle")
    f.header.scripts.OnLeave(f.header)
    eqc(chevronColor(f), dim, "left: dim again")
    -- open, idle: nothing; hovered: a cyan down triangle
    eq(chevronShows(o), nil)
    no(o.chevron:IsShown(), "the cell hides with it")
    o.header.scripts.OnEnter(o.header)
    eqc(chevronColor(o), W.C.cyan)
    o.header.scripts.OnLeave(o.header)
    eq(chevronShows(o), nil, "gone again when the mouse leaves")
end

function T.the_header_text_still_lights_with_the_chevron_on_hover()
    local W = boot()
    local made = openFoldPage(W)
    local f = made.folded
    eqc(f.text.themeColor, W.C.violet, "idle: the title is violet")
    f.header.scripts.OnEnter(f.header)
    eqc(f.text.themeColor, W.C.cyan, "hovered: the title is cyan")
    f.header.scripts.OnLeave(f.header)
    eqc(f.text.themeColor, W.C.violet)
end

function T.a_click_flips_the_glyph_keeps_the_hover_look_and_saves_the_fold()
    local W = boot()
    local made = openFoldPage(W)
    local f = made.folded
    f.header.scripts.OnEnter(f.header)
    f.header.scripts.OnClick(f.header)
    no(f.folded, "the click opened it")
    eq(chevronShows(f), "down", "the glyph flips to the open triangle")
    eqc(chevronColor(f), W.C.cyan, "and stays lit under the mouse")
    no(W.IsFolded(f.id, true), "the fold state is saved")
    f.header.scripts.OnLeave(f.header)
    eq(chevronShows(f), nil, "an open section goes quiet when the mouse leaves")
    f.header.scripts.OnClick(f.header)
    yes(f.folded, "a second click folds it again")
    eq(chevronShows(f), "right", "a folded section shows its triangle even with the mouse away")
    yes(W.IsFolded(f.id, false))
end

function T.a_search_jump_that_opens_a_section_repaints_its_chevron()
    local W = boot()
    local made = foldPage(W)
    W.Open("gl")
    yes(made.folded.folded)
    eq(chevronShows(made.folded), "right")
    W.Open("gl", nil, "gl.inside")
    no(made.folded.folded, "the jump opened the section")
    eq(chevronShows(made.folded), nil, "the chevron followed: open and idle shows nothing")
    no(made.folded.chevron:IsShown())
end

function T.a_section_built_open_shows_nothing_until_it_is_hovered()
    local W = boot()
    local made = foldPage(W)
    W.Open("gl")
    made.folded.header.scripts.OnClick(made.folded.header)
    W = reload()
    made = foldPage(W)
    W.Open("gl")
    no(made.folded.folded, "the saved fold state was open")
    eq(chevronShows(made.folded), nil)
    no(made.folded.chevron:IsShown())
end

-- ---- the dropdown caret ----------------------------------------------------------------------------------------------

local function dropdownFixture(W)
    W.RegisterCategory({ key = "gd", label = "Drop", group = "GENERAL", order = 72, build = function(c)
        W.UI.Dropdown(c, { label = "Pick", key = "gd.pick", get = function() return "a" end,
            items = function() return { { value = "a", text = "A" }, { value = "b", text = "B" } } end,
            set = function() end })
    end })
    FS.Config.RegisterDefault("gd.pick", "a")
    W.Open("gd")
    return row("Pick").control
end

function T.the_dropdown_caret_is_a_pixel_triangle_not_a_typed_v()
    local W = boot()
    local b = dropdownFixture(W)
    eq(b.w, 200)
    for _, t in ipairs(texts(b)) do eq(t == "v" or t == ">" or t == "^", false, "a typed arrow '" .. t .. "' is left on the dropdown") end
    local caret = b.fsCaret
    yes(caret and caret.textures and #caret.textures == 4, "the caret is a glyph of four rects")
    local cell = caret.textures[1].points[1].rel
    eq(cell.parent, b, "the cell is a child of the button, so the button's alpha dims it")
    eq(cell.w, 8); eq(cell.h, 8)
    local p = cell.points[1]
    eq(p.point, "RIGHT"); eq(p.rel, b); eq(p.relPoint, "RIGHT"); eq(p.x, -8, "its right edge 8 units from the button's"); eq(p.y, 0)
    eq(caret.direction, "down")
    local l, r, t, bt = glyphBox(caret, cell)
    eq(r - l, 8); eq(t - bt, 4)
    eq(l + r, 0, "centred across the cell"); eq(t + bt, 0, "centred up and down")
    for _, tex in ipairs(caret.textures) do eqc(tex.color, W.C.cyan, "cyan") end
end

function T.the_dropdown_caret_keeps_its_place_and_colour_across_a_pick_and_a_refresh()
    local W = boot()
    local b = dropdownFixture(W)
    local function where()
        local out = {}
        for _, tex in ipairs(b.fsCaret.textures) do
            local p = tex.points[1]
            out[#out + 1] = p.x .. "," .. p.y .. "," .. tex.w .. "," .. tex.h
        end
        return table.concat(out, ";")
    end
    local before = where()
    b.scripts.OnClick(b)
    W.RefreshAll()
    eq(where(), before, "the rects stay where the helper put them")
    eqc(b.fsCaret.textures[1].color, W.C.cyan)
    b.scripts.OnEnter(b)
    eqc(b.fsCaret.textures[1].color, W.C.cyan, "hovering the button leaves the caret cyan")
end

function T.a_read_only_dropdown_dims_its_caret_with_the_button()
    local W = boot({ db = "junk" })
    local b = dropdownFixture(W)
    no(b.enabled, "read only disables the dropdown")
    eq(b.alpha, 0.4, "the button dims")
    eq(b.fsCaret.textures[1].points[1].rel.parent, b, "and the caret is its child, so it dims with it")
end
"""

LAYOUT_NAMES: set[str] = set()


def run_lua_checks() -> int:
    global LAYOUT_NAMES
    LAYOUT_NAMES = {n for n in re.findall(r"^function T\.([a-z0-9_]+)\(", CHECKS, re.M)}
    base.CHECKS = base.CHECKS.replace("__checks = T", CHECKS + "\n__checks = T")
    failed = 0
    for name in sorted(LAYOUT_NAMES):
        try:
            lua = base.boot()
            lua.eval("__checks")[name]()
            leaked = list(lua.eval("__errors").values())
            if leaked:
                raise LuaError(f"errors were forwarded to the error handler: {leaked}")
            print(f"ok    {name}")
        except LuaError as err:
            failed += 1
            print(f"FAIL  {name}: {' '.join(str(err).splitlines()[:2])[:400]}")
    return failed


# ---- python level checks --------------------------------------------------------------------------------------------


def window_font() -> Path:
    m = re.search(r'Theme\.FONT_MONO\s*=\s*"Interface\\\\AddOns\\\\forever-stuwave\\\\Media\\\\Fonts\\\\([^"]+)"', THEME_FILE.read_text(encoding="utf-8"))
    if not m:
        raise AssertionError("Theme.FONT_MONO is not a bundled font path")
    return ADDON / "Media/Fonts" / m.group(1)


def check_the_window_font_has_no_triangle_glyphs() -> list[str]:
    """The premise for drawing the arrows: if the window's font ever gains the prototype's triangles the chevrons may be text."""
    from fontTools.ttLib import TTFont

    font = window_font()
    if not font.exists():
        return [f"{font} is missing"]
    cmap = TTFont(font).getBestCmap()
    problems = []
    for code, name in ((0x25B8, "small right triangle"), (0x25BE, "small down triangle")):
        if code in cmap:
            problems.append(f"{font.name} now has U+{code:04X} ({name}): the chevrons and the caret could be typed again")
    for code in (0x3E, 0x76):
        if code not in cmap:
            problems.append(f"{font.name} lacks U+{code:04X}")
    return problems


def check_the_builders_type_no_arrow_characters() -> list[str]:
    text = BUILDERS_FILE.read_text(encoding="utf-8")
    code = "\n".join(line.split("--", 1)[0] for line in text.splitlines())
    problems = []
    for pattern in (r'Label\([^)]*"[<>^v]"', r'SetText\([^)]*"[<>^v]"', r'folded and ">"', r'"v" or'):
        if re.search(pattern, code):
            problems.append(f"a typed arrow remains ({pattern})")
    return problems


def check_no_em_or_en_dash_in_the_builders() -> list[str]:
    text = BUILDERS_FILE.read_text(encoding="utf-8")
    return ["an em or en dash"] if "—" in text or "–" in text else []


def main() -> int:
    failed = run_lua_checks()
    py_checks = [
        ("the_window_font_has_no_triangle_glyphs", check_the_window_font_has_no_triangle_glyphs),
        ("the_builders_type_no_arrow_characters", check_the_builders_type_no_arrow_characters),
        ("no_em_or_en_dash_in_the_builders", check_no_em_or_en_dash_in_the_builders),
    ]
    total = len(LAYOUT_NAMES) + len(py_checks)
    for name, fn in py_checks:
        try:
            problems = fn()
        except Exception as err:  # noqa: BLE001 (report the failure, keep going)
            problems = [f"{type(err).__name__}: {err}"]
        if problems:
            failed += 1
            print(f"FAIL  {name}: {'; '.join(problems)[:600]}")
        else:
            print(f"ok    {name}")
    print(f"{total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
