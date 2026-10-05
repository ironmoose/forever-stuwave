#!/usr/bin/env python3
"""Exercise the REAL Theme.lua chrome primitives against a recording region mock.

Every other harness stubs Theme's primitives or reads only its constants; this one
loads the whole file and inspects which textures, texcoords, anchors and tints
AddRoundedFill / AddGradientBorder / AddOuterGlow / AddCornerMask / AddFillCorners /
AddLeadingEdgeCorners / AddCutPillCaps actually emit (and, for the nine-slice chrome,
which textures and margins the SLICE_* constants, AddPanelChrome, SkinPanel, SkinButton and
FrameHelpers.SeatCutIcon resolve to), under both
Theme.CHROME_CORNERS settings ("cut" is the default, "round" is the untouched old
path kept for the A/B). Cut chrome is two-corner: TOP-LEFT and BOTTOM-RIGHT are cut,
TOP-RIGHT and BOTTOM-LEFT stay square.

    python3 tools/theme-harness.py
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

ADDON = Path(__file__).resolve().parent.parent
THEME_SRC = Path(os.environ.get("THEME_LUA") or ADDON / "Theme.lua").read_text(encoding="utf-8")
FRAMEHELPERS_SRC = (ADDON / "FrameHelpers.lua").read_text(encoding="utf-8")
PETDOCK_SRC = (ADDON / "PetDock.lua").read_text(encoding="utf-8")  # the pet panel fill moved here in ac8662e
MOCKUP_HTML = ADDON / "mockups" / "gunsight-hud-v2-2026-10-02" / "gunsight-hud-v2-2026-10-02.html"
# The SLICE_* constants and the SkinButton default read the flag when Theme.lua LOADS, so the
# "round" cases load a copy of the real file with only the flag line changed.
ROUND_THEME_SRC = THEME_SRC.replace('Theme.CHROME_CORNERS = "cut"', 'Theme.CHROME_CORNERS = "round"', 1)
assert ROUND_THEME_SRC != THEME_SRC, "Theme.CHROME_CORNERS flag line not found"


def mockup_scrim() -> tuple[float, float, float, float]:
    """The panel fill the design owner approved (the pet panel's), parsed from the mockup's pChromeCm:
    A(<a1>) then fillStyle rgba(<r>,<g>,<b>,<a2>); the effective alpha is a1 * a2."""
    html = MOCKUP_HTML.read_text(encoding="utf-8")
    fn = html[html.index("function pChromeCm()"):]
    m = re.search(r"A\(([\d.]+)\);\s*ctx\.fillStyle='rgba\((\d+),(\d+),(\d+),([\d.]+)\)'", fn)
    assert m, "pChromeCm fill line (A(a);ctx.fillStyle='rgba(r,g,b,a)') not found in the mockup"
    a1, r, g, b, a2 = m.groups()
    return int(r) / 255, int(g) / 255, int(b) / 255, float(a1) * float(a2)


MOCK = r"""
local mediaPrefix = "Interface\\AddOns\\ForeverSynthwave\\media\\"

local Region = {}
Region.__index = Region
local function newRegion(kind, parent)
    return setmetatable({kind = kind, parent = parent, points = {}, texcoord = nil,
        regions = {}, children = {}, shown = true, level = 1}, Region)
end
function Region:SetTexture(p) self.texture = p end
function Region:SetColorTexture(r, g, b, a) self.color = { r, g, b, a } end
function Region:SetVertexColor(r, g, b, a) self.tint = { r, g, b, a } end
function Region:SetTexCoord(...) self.texcoord = { ... } end
function Region:SetBlendMode(m) self.blend = m end
function Region:SetDrawLayer(l, s) self.layer, self.sublevel = l, s end
function Region:SetDesaturated(v) self.desaturated = v end
function Region:SetSize(w, h) self.w, self.h = w, h end
function Region:SetWidth(w) self.w = w end
function Region:SetHeight(h) self.h = h end
function Region:SetPoint(p, rel, rp, x, y)
    self.points[p] = { rel = rel, rp = rp or p, x = x or 0, y = y or 0 }
end
function Region:ClearAllPoints() self.points = {} end
function Region:SetAllPoints(rel) self.allPoints = rel or self.parent end
function Region:SetShown(v) self.shown = v end
function Region:SetFrameLevel(l) self.level = l end
function Region:GetFrameLevel() return self.level end
function Region:SetClipsChildren() end
function Region:GetHeight() return self.h end
function Region:RegisterEvent() end
function Region:RegisterUnitEvent() end
function Region:SetScript() end
function Region:HookScript() end
function Region:SetAlpha(a) self.alpha = a end
function Region:SetHorizTile() end
function Region:SetVertTile() end
function Region:SetTextureSliceMargins(l, r, t, b) self.slice = { l, r, t, b } end
function Region:SetTextureSliceMode(m) self.sliceMode = m end
function Region:GetRegions() return unpack(self.regions) end
function Region:CreateFontString()
    local t = newRegion("fontstring", self)
    t.SetFont = function() return true end
    t.GetFont = function() return "font", 10 end
    t.SetText = function() end
    t.SetTextColor = function() end
    t.SetShadowOffset = function() end
    t.SetJustifyH = function() end
    t.SetShadowColor = function() end
    self.regions[#self.regions + 1] = t
    return t
end
function Region:CreateTexture(_, layer)
    local t = newRegion("texture", self)
    t.layer = layer
    self.regions[#self.regions + 1] = t
    return t
end
function Region:SetStatusBarTexture(p) self.statusTexture = p end
function Region:SetMinMaxValues(lo, hi) self.minMax = { lo, hi } end
function Region:SetValue(v) self.value = v end
function Region:GetStatusBarTexture()
    self.fillTexture = self.fillTexture or newRegion("texture", self)
    return self.fillTexture
end

function CreateFrame(_, _, parent)
    local f = newRegion("frame", parent)
    if parent then parent.children[#parent.children + 1] = f end
    return f
end
function NewFrame() return CreateFrame("Frame") end

FS = { LogDegradeOnce = function() end }
Enum = { UITextureSliceMode = { Stretched = 1 } }
assert(loadstring(THEME_SRC, "@Theme.lua"))("ForeverSynthwave", FS)
Theme = FS.Theme

-- FrameHelpers.lua on the same FS, loaded only by the cases that need it.
function LoadFrameHelpers()
    assert(loadstring(FRAMEHELPERS_SRC, "@FrameHelpers.lua"))("ForeverSynthwave", FS)
    return FS.FrameHelpers
end

function Media(name) return mediaPrefix .. name end

-- Regions of `frame` whose texture is the given media file.
function WithTexture(frame, name)
    local out = {}
    for _, t in ipairs(frame.regions) do
        if t.texture == Media(name) then out[#out + 1] = t end
    end
    return out
end

function Eq(a, b)
    if type(a) ~= type(b) then return false end
    if type(a) ~= "table" then return a == b end
    for k, v in pairs(a) do if not Eq(v, b[k]) then return false end end
    for k in pairs(b) do if a[k] == nil then return false end end
    return true
end

function Near(a, b) return math.abs(a - b) < 1e-9 end

function CoordIs(t, ...)
    local want = { ... }
    if not t.texcoord or #t.texcoord ~= #want then return false end
    for i = 1, #want do
        if not Near(t.texcoord[i], want[i]) then return false end
    end
    return true
end

function PointIs(t, point, relPoint, x, y)
    local p = t.points[point]
    return p ~= nil and p.rp == relPoint and p.x == x and p.y == y
end

-- Anchor offsets of a region at one point, or nil.
function Anchor(t, point) return t.points[point] end

function Round() Theme.CHROME_CORNERS = "round" end
function Cut() Theme.CHROME_CORNERS = "cut" end
"""

# Each case is Lua that asserts; it runs in a fresh runtime so flag state never leaks.
CASES: list[tuple[str, str, bool]] = []


def case(name: str, body: str, round_load: bool = False) -> None:
    """round_load: Theme.lua is loaded with the flag set to "round" (constants resolve at load)."""
    CASES.append((name, body, round_load))


# ---------------------------------------------------------------------------
# Flag and size rule
# ---------------------------------------------------------------------------

case("the_flag_defaults_to_cut", """
    assert(Theme.CHROME_CORNERS == "cut", tostring(Theme.CHROME_CORNERS))
""")

case("cutsize_snaps_height_over_three_into_the_baked_set", """
    local want = { [3] = 0, [4] = 2, [5] = 2, [9] = 3, [14] = 4, [16] = 4, [18] = 6, [24] = 6, [250] = 6, [40] = 6 }
    for h, c in pairs(want) do
        assert(Theme.CutSize(h) == c, "CutSize(" .. h .. ") = " .. tostring(Theme.CutSize(h)) .. ", want " .. c)
    end
""")

case("cutsize_never_exceeds_half_the_height_and_is_square_when_nothing_fits", """
    for h = 0, 60 do
        local c = Theme.CutSize(h)
        assert(c == 0 or c <= math.floor(h / 2), "CutSize(" .. h .. ") = " .. c)
        assert(c == 0 or c == 2 or c == 3 or c == 4 or c == 6, "off the baked set at h=" .. h)
    end
    assert(Theme.CutSize(3) == 0 and Theme.CutSize(0) == 0 and Theme.CutSize(nil) == 0)
""")

case("cutsize_icon_uses_height_over_five", """
    assert(Theme.CutSizeIcon(36) == 6 and Theme.CutSizeIcon(24) == 4 and Theme.CutSizeIcon(18) == 3)
    assert(Theme.CutSizeIcon(10) == 2)
""")

case("snapcut_picks_the_largest_baked_size_at_or_below_the_request", """
    local want = { [0] = 0, [1] = 2, [2] = 2, [3] = 3, [4] = 4, [5] = 4, [6] = 6, [7] = 6, [12] = 6 }
    for req, c in pairs(want) do
        assert(Theme.SnapCut(req) == c, "SnapCut(" .. req .. ") = " .. tostring(Theme.SnapCut(req)))
    end
""")

# ---------------------------------------------------------------------------
# AddRoundedFill
# ---------------------------------------------------------------------------

case("fill_cut_is_five_regions_two_triangles_at_top_left_and_bottom_right", """
    local f = NewFrame()
    Theme.AddRoundedFill(f, { 0.1, 0.2, 0.3, 0.8 }, 6)
    assert(#f.regions == 5, "regions " .. #f.regions)
    local tris = WithTexture(f, "fill_cut_c6.tga")
    assert(#tris == 2, "triangles " .. #tris)
    local tl, br
    for _, t in ipairs(tris) do
        if t.points.TOPLEFT then tl = t end
        if t.points.BOTTOMRIGHT then br = t end
    end
    assert(tl and br, "need a TOPLEFT and a BOTTOMRIGHT piece")
    assert(CoordIs(tl, 0, 6 / 16, 0, 6 / 16), "TL texcoord")
    assert(CoordIs(br, 6 / 16, 0, 6 / 16, 0), "BR texcoord")
    assert(tl.w == 6 and tl.h == 6 and br.w == 6 and br.h == 6)
    assert(PointIs(tl, "TOPLEFT", "TOPLEFT", 0, 0) and PointIs(br, "BOTTOMRIGHT", "BOTTOMRIGHT", 0, 0))
    assert(Eq(tl.tint, { 0.1, 0.2, 0.3, 0.8 }), "tint")
    assert(tl.layer == "BACKGROUND" and tl.sublevel == -8, "fill sublevel")
""")

case("cutslicefill_is_one_nine_slice_of_the_c4_fill_file_over_the_whole_frame_with_roundedfills_look", """
    local f = NewFrame()
    local t = Theme.AddCutSliceFill(f, { 0.051, 0.024, 0.125, 0.765 }, 4)
    assert(t and #f.regions == 1 and f.regions[1] == t, "one texture")
    assert(t.texture == Media("slice_cut2_fill_c4.tga"), tostring(t.texture))
    assert(Eq(t.slice, { 4, 4, 4, 4 }), "slice margin is the chamfer")
    -- the same rect, colour, alpha and layer AddRoundedFill's pieces have
    assert(t.points.TOPLEFT.rel == f and t.points.BOTTOMRIGHT.rel == f)
    assert(PointIs(t, "TOPLEFT", "TOPLEFT", 0, 0) and PointIs(t, "BOTTOMRIGHT", "BOTTOMRIGHT", 0, 0))
    assert(Eq(t.tint, { 0.051, 0.024, 0.125, 0.765 }), "tint carries the alpha")
    assert(t.layer == "BACKGROUND" and t.sublevel == -8, "fill sublevel")
""")

case("cutslicefill_c6_uses_the_c6_fill_file_and_unbaked_or_zero_chamfers_build_nothing", """
    local f = NewFrame()
    local t = Theme.AddCutSliceFill(f, { 1, 1, 1, 1 }, 6)
    assert(t.texture == Media("slice_cut2_fill.tga") and Eq(t.slice, { 6, 6, 6, 6 }))
    local g = NewFrame()
    assert(Theme.AddCutSliceFill(g, { 1, 1, 1, 1 }, 0) == nil and #g.regions == 0, "radius 0 stays flat")
""")

case("cutslicefill_is_nil_under_round_and_builds_nothing", """
    Round()
    local f = NewFrame()
    assert(Theme.AddCutSliceFill(f, { 1, 1, 1, 1 }, 4) == nil and #f.regions == 0)
""")

case("cutslicefill_without_nine_slice_support_returns_nil_and_hides_what_it_made", """
    local f = NewFrame()
    local realCreate = f.CreateTexture
    local made = {}
    f.CreateTexture = function(self, ...)
        local t = realCreate(self, ...)
        t.SetTextureSliceMargins = false
        made[#made + 1] = t
        return t
    end
    assert(Theme.AddCutSliceFill(f, { 1, 1, 1, 1 }, 4) == nil, "an unsliced file would stretch whole")
    assert(#made == 1 and made[1].shown == false, "the unsliced texture was left shown")
""")

case("fill_cut_top_right_and_bottom_left_are_square_flat_rects", """
    local f = NewFrame()
    Theme.AddRoundedFill(f, { 1, 1, 1, 1 }, 6)
    local top, bottom, middle
    for _, t in ipairs(f.regions) do
        if t.color then
            if t.points.TOPRIGHT and t.points.TOPRIGHT.y == 0 and t.points.TOPLEFT and t.points.TOPLEFT.x == 6 then top = t end
            if t.points.BOTTOMLEFT and t.points.BOTTOMLEFT.x == 0 and t.points.BOTTOMRIGHT and t.points.BOTTOMRIGHT.x == -6 then bottom = t end
            if t.points.TOPLEFT and t.points.TOPLEFT.x == 0 and t.points.TOPLEFT.y == -6 then middle = t end
        end
    end
    -- top runs from the TL cut to the TOP-RIGHT corner (square: x offset 0), bottom runs from the
    -- BOTTOM-LEFT corner (square: x offset 0) to the BR cut, the middle spans the full width.
    assert(top and top.points.TOPRIGHT.x == 0 and top.h == 6, "top strip")
    assert(bottom and bottom.points.BOTTOMLEFT.x == 0 and bottom.h == 6, "bottom strip")
    assert(middle and middle.points.BOTTOMRIGHT.x == 0 and middle.points.BOTTOMRIGHT.y == 6, "middle band")
""")

case("fill_cut_snaps_the_requested_radius", """
    local f = NewFrame()
    Theme.AddRoundedFill(f, { 1, 1, 1, 1 }, 5)
    assert(#WithTexture(f, "fill_cut_c4.tga") == 2)
    local g = NewFrame()
    Theme.AddRoundedFill(g, { 1, 1, 1, 1 }, 7)
    assert(#WithTexture(g, "fill_cut_c6.tga") == 2)
    local h = NewFrame()
    Theme.AddRoundedFill(h, { 1, 1, 1, 1 }, 3)
    assert(#WithTexture(h, "fill_cut_c3.tga") == 2)
""")

case("fill_radius_zero_stays_fully_square_under_cut", """
    local f = NewFrame()
    Theme.AddRoundedFill(f, { 1, 1, 1, 1 }, 0)
    for _, t in ipairs(f.regions) do
        assert(not (t.texture and t.texture:find("fill_cut", 1, true)), "cut piece at radius 0")
    end
""")

case("fill_round_flag_keeps_the_nine_region_disc_path", """
    Round()
    local f = NewFrame()
    Theme.AddRoundedFill(f, { 0.1, 0.2, 0.3, 0.8 }, 6)
    assert(#f.regions == 9, "regions " .. #f.regions)
    local discs = WithTexture(f, "fill_corner.tga")
    assert(#discs == 4, "discs " .. #discs)
    for _, d in ipairs(discs) do assert(d.w == 6 and d.h == 6) end
    local flips = {}
    for _, d in ipairs(discs) do
        for p in pairs(d.points) do flips[p] = d.texcoord end
    end
    assert(Eq(flips.TOPLEFT, { 0, 1, 0, 1 }) and Eq(flips.TOPRIGHT, { 1, 0, 0, 1 }))
    assert(Eq(flips.BOTTOMLEFT, { 0, 1, 1, 0 }) and Eq(flips.BOTTOMRIGHT, { 1, 0, 1, 0 }))
    for _, t in ipairs(f.regions) do
        assert(not (t.texture and t.texture:find("cut", 1, true)), "cut texture on the round path")
    end
""")

# ---------------------------------------------------------------------------
# AddGradientBorder
# ---------------------------------------------------------------------------

case("border_cut_uses_diagonal_strokes_at_top_left_and_bottom_right_only", """
    local f = NewFrame()
    Theme.AddGradientBorder(f, { 0.5, 0.25, 1, 1 }, 2, 6)
    assert(#f.regions == 6, "regions " .. #f.regions)
    local strokes = WithTexture(f, "border_cut_c6_t2.tga")
    assert(#strokes == 2, "strokes " .. #strokes)
    local tl, br
    for _, t in ipairs(strokes) do
        if t.points.TOPLEFT then tl = t end
        if t.points.BOTTOMRIGHT then br = t end
    end
    assert(tl and br)
    assert(CoordIs(tl, 0, 6 / 16, 0, 6 / 16) and CoordIs(br, 6 / 16, 0, 6 / 16, 0))
    assert(tl.w == 6 and tl.h == 6 and br.w == 6 and br.h == 6)
    -- the vertical fade survives: top piece 0.31 alpha, bottom piece solid
    assert(Near(tl.tint[4], 0.31) and Near(br.tint[4], 1), "alpha " .. tl.tint[4] .. " / " .. br.tint[4])
    assert(#WithTexture(f, "border_corner.tga") == 0, "no arcs under cut")
""")

case("border_cut_straight_runs_start_after_the_cut_and_run_flush_at_the_square_corners", """
    local f = NewFrame()
    Theme.AddGradientBorder(f, { 1, 1, 1, 1 }, 2, 6)
    local top, bottom, left, right
    for _, t in ipairs(f.regions) do
        if t.color and t.color[4] < 0.5 then top = t end
        if t.color and t.color[4] == 1 then bottom = t end
        if t.texture == Media("border_rail.tga") then
            if t.points.TOPLEFT then left = t end
            if t.points.TOPRIGHT then right = t end
        end
    end
    assert(top and Near(top.color[4], 0.31) and top.h == 2)
    assert(top.points.TOPLEFT.x == 6 and top.points.TOPRIGHT.x == 0, "top: cut at TL, flush at TR")
    assert(bottom.points.BOTTOMLEFT.x == 0 and bottom.points.BOTTOMRIGHT.x == -6, "bottom: flush at BL, cut at BR")
    assert(left.points.TOPLEFT.y == -6 and left.points.BOTTOMLEFT.y == 2, "left rail: cut at TL, tucked under the bottom run")
    assert(right.points.TOPRIGHT.y == -2 and right.points.BOTTOMRIGHT.y == 6, "right rail: tucked under the top run, cut at BR")
    assert(left.w == 2 and right.w == 2)
""")

case("border_cut_picks_the_stroke_file_by_chamfer_and_thickness", """
    local f = NewFrame()
    Theme.AddGradientBorder(f, { 1, 1, 1, 1 }, 1, 6)
    assert(#WithTexture(f, "border_cut_c6_t1.tga") == 2)
    local g = NewFrame()
    Theme.AddGradientBorder(g, { 1, 1, 1, 1 }, 1, 4)
    assert(#WithTexture(g, "border_cut_c4_t1.tga") == 2)
    local h = NewFrame()
    Theme.AddGradientBorder(h, { 1, 1, 1, 1 }, 2, 3) -- no t2 file below c6: falls back to t1
    assert(#WithTexture(h, "border_cut_c3_t1.tga") == 2)
""")

case("border_default_radius_is_the_panel_radius_snapped", """
    local f = NewFrame()
    Theme.AddGradientBorder(f, { 1, 1, 1, 1 }, 2)
    assert(#WithTexture(f, "border_cut_c6_t2.tga") == 2)
""")

case("border_radius_zero_is_four_straight_regions_under_cut", """
    local f = NewFrame()
    Theme.AddGradientBorder(f, { 1, 1, 1, 1 }, 1, 0)
    assert(#f.regions == 4, "regions " .. #f.regions)
""")

case("border_round_flag_keeps_the_four_arcs", """
    Round()
    local f = NewFrame()
    Theme.AddGradientBorder(f, { 0.5, 0.25, 1, 1 }, 2, 6)
    assert(#f.regions == 8, "regions " .. #f.regions)
    local arcs = WithTexture(f, "border_corner.tga")
    assert(#arcs == 4)
    local alphas = {}
    for _, a in ipairs(arcs) do
        for p in pairs(a.points) do alphas[p] = a.tint[4] end
    end
    assert(Near(alphas.TOPLEFT, 0.31) and Near(alphas.TOPRIGHT, 0.31))
    assert(alphas.BOTTOMLEFT == 1 and alphas.BOTTOMRIGHT == 1)
    for _, t in ipairs(f.regions) do
        assert(not (t.texture and t.texture:find("cut", 1, true)), "cut texture on the round path")
    end
""")

# ---------------------------------------------------------------------------
# AddOuterGlow
# ---------------------------------------------------------------------------

case("glow_cut_has_cut_pieces_at_top_left_and_bottom_right_and_square_glow_at_the_others", """
    local f = NewFrame()
    Theme.AddOuterGlow(f, 1, 0.5, 0.25, 8, 0.45, 6)
    assert(#f.regions == 8, "regions " .. #f.regions)
    local cuts = WithTexture(f, "glow_corner_cut.tga")
    assert(#cuts == 2, "cut glow pieces " .. #cuts)
    local tl, br
    for _, t in ipairs(cuts) do
        if t.points.BOTTOMRIGHT then tl = t end
        if t.points.TOPLEFT then br = t end
    end
    assert(tl and br)
    assert(PointIs(tl, "BOTTOMRIGHT", "TOPLEFT", 6, -6) and CoordIs(tl, 0, 1, 0, 1), "TL piece")
    assert(PointIs(br, "TOPLEFT", "BOTTOMRIGHT", -6, 6) and CoordIs(br, 1, 0, 1, 0), "BR piece")
    assert(tl.w == 14 and tl.h == 14 and br.w == 14 and br.h == 14, "box = chamfer + size")
    local square = WithTexture(f, "glow_corner.tga")
    assert(#square == 2, "square glow corners " .. #square)
    local tr, bl
    for _, t in ipairs(square) do
        if t.points.BOTTOMLEFT then tr = t end
        if t.points.TOPRIGHT then bl = t end
    end
    assert(tr and PointIs(tr, "BOTTOMLEFT", "TOPRIGHT", 0, 0), "TR square corner")
    assert(bl and PointIs(bl, "TOPRIGHT", "BOTTOMLEFT", 0, 0), "BL square corner")
    assert(#WithTexture(f, "glow_corner_round.tga") == 0)
""")

case("glow_cut_strips_are_inset_only_at_the_cut_corners", """
    local f = NewFrame()
    Theme.AddOuterGlow(f, 1, 1, 1, 8, 0.5, 6)
    local strips = WithTexture(f, "glow_edge.tga")
    assert(#strips == 4)
    local top, bottom, left, right
    for _, s in ipairs(strips) do
        if s.points.BOTTOMLEFT and s.points.BOTTOMRIGHT then top = s end
        if s.points.TOPLEFT and s.points.TOPRIGHT then bottom = s end
        if s.points.TOPRIGHT and s.points.BOTTOMRIGHT then left = s end
        if s.points.TOPLEFT and s.points.BOTTOMLEFT and not s.points.TOPRIGHT then right = s end
    end
    assert(top.points.BOTTOMLEFT.x == 6 and top.points.BOTTOMRIGHT.x == 0, "top")
    assert(bottom.points.TOPLEFT.x == 0 and bottom.points.TOPRIGHT.x == -6, "bottom")
    assert(left.points.TOPRIGHT.y == -6 and left.points.BOTTOMRIGHT.y == 0, "left")
    assert(right.points.TOPLEFT.y == 0 and right.points.BOTTOMLEFT.y == 6, "right")
""")

case("glow_cut_snaps_the_chamfer_and_keeps_the_tint", """
    local f = NewFrame()
    Theme.AddOuterGlow(f, 1, 0.5, 0.25, 3, 0.6, 5)
    local cuts = WithTexture(f, "glow_corner_cut.tga")
    assert(#cuts == 2 and cuts[1].w == 7, "box " .. tostring(cuts[1].w)) -- snap(5)=4, +3
    assert(Eq(cuts[1].tint, { 1, 0.5, 0.25, 0.6 }) and cuts[1].blend == "ADD")
""")

case("glow_radius_zero_is_the_square_four_corner_path_under_cut", """
    local f = NewFrame()
    Theme.AddOuterGlow(f, 1, 1, 1, 8, 0.5, 0)
    assert(#f.regions == 8)
    assert(#WithTexture(f, "glow_corner.tga") == 4)
    assert(#WithTexture(f, "glow_corner_cut.tga") == 0)
""")

case("glow_round_flag_keeps_the_four_annulus_corners", """
    Round()
    local f = NewFrame()
    Theme.AddOuterGlow(f, 1, 1, 1, 8, 0.5, 6)
    assert(#f.regions == 8)
    assert(#WithTexture(f, "glow_corner_round.tga") == 4)
    assert(#WithTexture(f, "glow_corner_cut.tga") == 0)
""")

# ---------------------------------------------------------------------------
# Erase quads
# ---------------------------------------------------------------------------

case("cornermask_cut_erases_only_top_left_and_bottom_right", """
    local host, anchor = NewFrame(), NewFrame()
    local quads = Theme.AddCornerMask(host, anchor, { 0.1, 0.1, 0.2, 1 }, 4)
    assert(#quads == 2 and #host.regions == 2, "quads " .. #quads)
    local tl, br
    for _, q in ipairs(quads) do
        assert(q.texture == Media("anti_cut_c4.tga"))
        if q.points.TOPLEFT then tl = q end
        if q.points.BOTTOMRIGHT then br = q end
    end
    assert(tl and br)
    assert(CoordIs(tl, 0, 4 / 16, 0, 4 / 16) and CoordIs(br, 4 / 16, 0, 4 / 16, 0))
    assert(tl.w == 4 and tl.h == 4 and PointIs(tl, "TOPLEFT", "TOPLEFT", 0, 0))
    assert(tl.points.TOPLEFT.rel == anchor and br.points.BOTTOMRIGHT.rel == anchor)
    assert(Eq(tl.tint, { 0.1, 0.1, 0.2, 1 }))
""")

case("cornermask_cut_snaps_the_radius", """
    local host, anchor = NewFrame(), NewFrame()
    local quads = Theme.AddCornerMask(host, anchor, { 0, 0, 0, 1 }, 7)
    assert(quads[1].texture == Media("anti_cut_c6.tga") and quads[1].w == 6)
""")

case("fillcorners_cut_handle_swaps_the_texture_when_the_radius_changes", """
    local host, anchor = NewFrame(), NewFrame()
    local handle = Theme.AddFillCorners(host, anchor, { 0.1, 0.1, 0.2, 0.3 }, 4)
    assert(#handle.quads == 2)
    assert(handle.quads[1].tint[4] == 1, "erase alpha forced to 1")
    handle.SetRadius(3)
    for _, q in ipairs(handle.quads) do
        assert(q.texture == Media("anti_cut_c3.tga"), "texture " .. tostring(q.texture))
        assert(q.w == 3 and q.h == 3)
    end
    for _, q in ipairs(handle.quads) do
        if q.points.TOPLEFT then assert(CoordIs(q, 0, 3 / 16, 0, 3 / 16)) end
        if q.points.BOTTOMRIGHT then assert(CoordIs(q, 3 / 16, 0, 3 / 16, 0)) end
    end
""")

case("fillcorners_cut_handle_hides_the_quads_at_radius_zero_and_restores_them", """
    local host, anchor = NewFrame(), NewFrame()
    local handle = Theme.AddFillCorners(host, anchor, { 0.1, 0.1, 0.2, 0.3 }, 4)
    assert(#handle.quads == 2)
    handle.SetRadius(0)
    for _, q in ipairs(handle.quads) do assert(q.shown == false, "cut quad still shown at r=0") end
    handle.SetRadius(6)
    for _, q in ipairs(handle.quads) do
        assert(q.shown == true, "cut quad not restored")
        assert(q.texture == Media("anti_cut_c6.tga") and q.w == 6 and q.h == 6)
    end
""")

case("cutfillerase_nine_slices_a_wedge_per_cut_corner_over_the_plate_root", """
    local host, plate = NewFrame(), NewFrame()
    local handle = Theme.AddCutFillErase(host, plate, { 0.04, 0.02, 0.09, 0.5 })
    assert(handle and handle.texture and handle.frame, "no handle")
    -- the texture lives on a child frame of the host: SetClipsChildren clips child frames, and the
    -- host is the bar's clipping mask, so the parts of the root-sized wedge outside the bar rect go
    assert(#host.children == 1 and host.children[1] == handle.frame, "one clip child frame")
    assert(handle.frame.allPoints == host, "clip child covers the host")
    assert(handle.frame.level == host.level, "clip child at the host's level")
    local t = handle.texture
    assert(#WithTexture(handle.frame, "slice_cut2_erase_c6.tga") == 1 and t.texture == Media("slice_cut2_erase_c6.tga"))
    assert(t.layer == "BACKGROUND")
    assert(Eq(t.slice, { 6, 6, 6, 6 }), "slice margins are the plate stroke's own (SLICE_MARGIN)")
    assert(Eq(t.tint, { 0.04, 0.02, 0.09, 1 }), "erase alpha forced to 1")
    -- anchored to the PLATE (the stroke's own rect), not to the bar: no bar-inset window
    assert(PointIs(t, "TOPLEFT", "TOPLEFT", 0, 0) and PointIs(t, "BOTTOMRIGHT", "BOTTOMRIGHT", 0, 0))
    assert(t.points.TOPLEFT.rel == plate and t.points.BOTTOMRIGHT.rel == plate)
""")

case("cutfillerase_default_chamfer_is_the_c6_nameplate_wedge_unchanged", """
    -- no chamfer argument, and an explicit 6, both draw the nameplate's wedge at SLICE_MARGIN
    for _, explicit in ipairs({ false, true }) do
        local host, plate = NewFrame(), NewFrame()
        local handle
        if explicit then
            handle = Theme.AddCutFillErase(host, plate, { 0.04, 0.02, 0.09, 1 }, 6)
        else
            handle = Theme.AddCutFillErase(host, plate, { 0.04, 0.02, 0.09, 1 })
        end
        assert(handle and handle.texture.texture == Media("slice_cut2_erase_c6.tga"), "texture")
        assert(Eq(handle.texture.slice, { 6, 6, 6, 6 }), "margin " .. tostring(explicit))
    end
""")

case("cutfillerase_chamfer_4_slices_the_c4_wedge_at_the_c4_rings_margin_over_the_edge_rect", """
    local host, edgeRect = NewFrame(), NewFrame()
    local handle = Theme.AddCutFillErase(host, edgeRect, { 0.051, 0.024, 0.125, 0.765 }, 4)
    assert(handle and handle.texture and handle.frame, "no handle")
    local t = handle.texture
    assert(t.texture == Media("slice_cut2_erase_c4.tga"), tostring(t.texture))
    -- the c4 ring (Cut2ButtonSet(4), margin c) is sliced at 4: the wedge is sliced at 4 over the same rect
    assert(Eq(t.slice, { 4, 4, 4, 4 }), "slice margins are the c4 ring's own")
    assert(t.points.TOPLEFT.rel == edgeRect and t.points.BOTTOMRIGHT.rel == edgeRect)
    assert(PointIs(t, "TOPLEFT", "TOPLEFT", 0, 0) and PointIs(t, "BOTTOMRIGHT", "BOTTOMRIGHT", 0, 0))
    assert(Eq(t.tint, { 0.051, 0.024, 0.125, 1 }), "erase alpha forced to 1")
    assert(#host.children == 1 and host.children[1] == handle.frame and handle.frame.allPoints == host)
    assert(handle.frame.level == host.level and t.layer == "BACKGROUND")
""")

case("cutfillerase_chamfer_without_a_baked_erase_file_builds_nothing", """
    -- only c4 and c6 are baked: a c3 request must not stretch the wrong file
    for _, c in ipairs({ 2, 3 }) do
        local host = NewFrame()
        assert(Theme.AddCutFillErase(host, NewFrame(), { 0, 0, 0, 1 }, c) == nil, "c" .. c)
        assert(#host.children == 0 and #host.regions == 0, "c" .. c .. " built something")
    end
""")

case("cutfillerase_chamfer_4_is_nil_under_round", """
    Round()
    local host = NewFrame()
    assert(Theme.AddCutFillErase(host, NewFrame(), { 0, 0, 0, 1 }, 4) == nil)
    assert(#host.children == 0 and #host.regions == 0)
""")

case("cutfillerase_is_nil_under_round", """
    Round()
    local host = NewFrame()
    assert(Theme.AddCutFillErase(host, NewFrame(), { 0, 0, 0, 1 }) == nil, "round has no cut wedge")
    assert(#host.children == 0 and #host.regions == 0, "round built something")
""")

case("cutfillerase_without_nine_slice_support_is_nil_and_leaves_at_most_one_hidden_orphan_per_session", """
    local function Unsliceable()
        local host = NewFrame()
        local realCreate = host.CreateTexture
        local texturesMade = {}
        local realFrame = host
        -- the clip child is a plain frame; make ITS textures lack SetTextureSliceMargins
        local realCF = CreateFrame
        CreateFrame = function(...)
            local f = realCF(...)
            local create = f.CreateTexture
            f.CreateTexture = function(self, ...)
                local t = create(self, ...)
                t.SetTextureSliceMargins = false
                texturesMade[#texturesMade + 1] = t
                return t
            end
            return f
        end
        return host, texturesMade, function() CreateFrame = realCF end
    end
    local host, made, restore = Unsliceable()
    local handle = Theme.AddCutFillErase(host, NewFrame(), { 0, 0, 0, 1 })
    assert(handle == nil, "without SetTextureSliceMargins the stretched file would draw huge corners")
    assert(#made == 1 and made[1].shown == false, "the unsliced probe texture was left shown")
    assert(host.children[1].shown == false, "the unsliced clip frame was left shown")
    -- the failure is latched: later bars create nothing at all
    local host2 = NewFrame()
    assert(Theme.AddCutFillErase(host2, NewFrame(), { 0, 0, 0, 1 }) == nil)
    assert(#host2.children == 0 and #host2.regions == 0, "a second call after a known failure built something")
    restore()
""")

case("gatedcutcorner_is_a_statusbar_whose_fill_is_the_bottom_right_wedge_file", """
    local host, bar = NewFrame(), NewFrame()
    local gate = Theme.AddGatedCutCorner(host, bar, { 0.04, 0.02, 0.09, 0.5 }, 6)
    assert(gate and host.children[1] == gate, "a StatusBar child of the host")
    assert(gate.level == host.level, "at the mask host's level")
    assert(gate.w == 16 and gate.h == 16, "the 16 texel canvas at one unit per texel, the old quad's scale")
    assert(PointIs(gate, "BOTTOMRIGHT", "BOTTOMRIGHT", 0, 0) and gate.points.BOTTOMRIGHT.rel == bar)
    assert(gate.statusTexture == Media("anti_cut_br_c6.tga"), tostring(gate.statusTexture))
    -- the fill file is shown unflipped and unsampled: no texcoord is ever set on it
    local fill = gate:GetStatusBarTexture()
    assert(fill.texcoord == nil, "a texcoord on a StatusBar fill is overwritten by the engine")
    assert(Eq(fill.tint, { 0.04, 0.02, 0.09, 1 }), "erase alpha forced to 1")
    -- closed until the caller feeds it the plate's growth value (sizer range, sub-pixel when empty)
    assert(Eq(gate.minMax, { -0.001, 1 }) and gate.value == 0, "not closed at build")
""")

case("gatedcutcorner_hides_its_half_built_bar_and_rethrows_when_a_step_throws", """
    local realCF = CreateFrame
    local host, bar = NewFrame(), NewFrame()
    CreateFrame = function(...)
        local f = realCF(...)
        f.SetStatusBarTexture = function() error("boom: SetStatusBarTexture") end
        return f
    end
    local ok, err = pcall(Theme.AddGatedCutCorner, host, bar, { 0, 0, 0, 1 }, 6)
    CreateFrame = realCF
    assert(not ok and tostring(err):find("boom", 1, true), "the throw was swallowed: " .. tostring(err))
    assert(#host.children == 1 and host.children[1].shown == false, "a half built StatusBar was left shown")
""")

case("gatedcutcorner_snaps_the_chamfer_and_is_nil_under_round", """
    local host, bar = NewFrame(), NewFrame()
    assert(Theme.AddGatedCutCorner(host, bar, { 0, 0, 0, 1 }, 5).statusTexture == Media("anti_cut_br_c4.tga"))
    Round()
    assert(Theme.AddGatedCutCorner(NewFrame(), NewFrame(), { 0, 0, 0, 1 }, 6) == nil)
""")

case("baked_cut_texture_paths_resolve_to_real_files", """
    local paths = { Theme.GLOW_CORNER_CUT_TEXTURE, Theme.SLICE_CUT2_ERASE_TEXTURE }
    for _, set in ipairs({ Theme.FILL_CUT_TEXTURES, Theme.ANTI_CUT_TEXTURES, Theme.ANTI_CUT_BR_TEXTURES }) do
        for _, p in pairs(set) do paths[#paths + 1] = p end
    end
    for _, byThickness in pairs(Theme.BORDER_CUT_TEXTURES) do
        for _, p in pairs(byThickness) do paths[#paths + 1] = p end
    end
    assert(#paths >= 14, "only " .. #paths .. " paths collected")
    for _, p in ipairs(paths) do ASSERT_FILE(p) end
""")

case("leadingedge_cut_is_one_bottom_right_quad_on_the_fill_tip", """
    local host, bar = NewFrame(), NewFrame()
    local handle = Theme.AddLeadingEdgeCorners(host, bar, { 0, 0, 0, 1 }, 4)
    assert(#handle.quads == 1, "quads " .. #handle.quads)
    local q = handle.quads[1]
    assert(q.texture == Media("anti_cut_c4.tga") and q.points.BOTTOMRIGHT, "BR on the tip")
    assert(q.points.BOTTOMRIGHT.rel == bar:GetStatusBarTexture())
    assert(CoordIs(q, 4 / 16, 0, 4 / 16, 0))
    assert(#host.children == 1, "one clip child frame, as before")
    handle.SetRadius(6)
    assert(q.texture == Media("anti_cut_c6.tga") and q.w == 6 and CoordIs(q, 6 / 16, 0, 6 / 16, 0))
""")

case("erase_quads_round_flag_keeps_four_and_two_disc_quads_resized_in_place", """
    Round()
    local host, anchor, bar = NewFrame(), NewFrame(), NewFrame()
    local mask = Theme.AddCornerMask(host, anchor, { 0, 0, 0, 1 }, 7)
    assert(#mask == 4)
    for _, q in ipairs(mask) do assert(q.texture == Media("anti_corner.tga") and q.w == 7) end
    local fc = Theme.AddFillCorners(host, anchor, { 0, 0, 0, 1 }, 5)
    assert(#fc.quads == 4)
    fc.SetRadius(3)
    for _, q in ipairs(fc.quads) do assert(q.w == 3 and q.texture == Media("anti_corner.tga")) end
    local le = Theme.AddLeadingEdgeCorners(host, bar, { 0, 0, 0, 1 }, 5)
    assert(#le.quads == 2)
    for _, q in ipairs(le.quads) do assert(q.points.TOPRIGHT or q.points.BOTTOMRIGHT) end
""")

# ---------------------------------------------------------------------------
# Pill caps
# ---------------------------------------------------------------------------

case("cutpillcaps_is_four_colored_pieces_with_two_triangles", """
    local parent, bar = NewFrame(), NewFrame()
    local caps = Theme.AddCutPillCaps(parent, bar, { 0.2, 0.4, 0.6, 0.5 }, 4, 16)
    assert(#caps.textures == 4 and caps.tip)
    local tris = {}
    for _, t in ipairs(caps.textures) do
        assert(Eq(t.tint, { 0.2, 0.4, 0.6, 0.5 }), "colored, so translucent tracks keep working")
        if t.texture == Media("fill_cut_c4.tga") then tris[#tris + 1] = t end
    end
    assert(#tris == 2, "triangles " .. #tris)
    local tl, br
    for _, t in ipairs(tris) do
        if t.points.TOPRIGHT then tl = t end
        if t.points.BOTTOMRIGHT then br = t end
    end
    assert(tl.points.TOPRIGHT.rel == bar and tl.points.TOPRIGHT.rp == "TOPLEFT", "left cap TL cut sits against the bar's left edge")
    assert(CoordIs(tl, 0, 4 / 16, 0, 4 / 16))
    assert(br.points.BOTTOMRIGHT.rel == caps.tip and br.points.BOTTOMRIGHT.rp == "BOTTOMRIGHT", "right cap BR cut rides the tip")
    assert(CoordIs(br, 4 / 16, 0, 4 / 16, 0))
    assert(tl.w == 4 and tl.h == 4 and br.w == 4 and br.h == 4)
    for _, t in ipairs(caps.textures) do
        if t.texture ~= Media("fill_cut_c4.tga") then
            assert(t.w == 4 and t.h == 12, "square half: " .. tostring(t.w) .. "x" .. tostring(t.h))
        end
    end
    assert(caps.tip.w == 4)
""")

case("cutpillcaps_handle_recolors_desaturates_and_resizes", """
    local parent, bar = NewFrame(), NewFrame()
    local caps = Theme.AddCutPillCaps(parent, bar, { 1, 1, 1, 1 }, 4, 16)
    caps.SetColor(0.3, 0.2, 0.1, 0.9)
    for _, t in ipairs(caps.textures) do assert(Eq(t.tint, { 0.3, 0.2, 0.1, 0.9 })) end
    caps.SetDesaturated(true)
    for _, t in ipairs(caps.textures) do assert(t.desaturated == true) end
    caps.SetRadius(6, 20)
    assert(caps.tip.w == 6)
    for _, t in ipairs(caps.textures) do
        if t.texture == Media("fill_cut_c6.tga") then
            assert(t.w == 6 and t.h == 6)
        else
            assert(t.texture == Theme.FLAT_TEXTURE and t.w == 6 and t.h == 14, "square half after resize")
        end
    end
    caps.SetShown(false)
""")

case("roundpillcaps_is_untouched_by_the_flag", """
    local parent, bar = NewFrame(), NewFrame()
    local caps = Theme.AddPillCaps(parent, bar, { 1, 1, 1, 1 }, 7, 14)
    assert(#caps.textures == 4)
    for _, t in ipairs(caps.textures) do assert(t.texture == Media("fill_corner.tga")) end
""")

# ---------------------------------------------------------------------------
# Nine-slice chrome (L2): SLICE_* constants, AddPanelChrome, SkinPanel, SkinButton, SeatCutIcon
# ---------------------------------------------------------------------------

case("slice_constants_resolve_to_the_2c_c6_set_under_cut", """
    local want = {
        SLICE_FILL_TEXTURE = Media("slice_cut2_fill.tga"),
        SLICE_BORDER_TEXTURE = Media("slice_cut2_border_c6.tga"),
        SLICE_GLOW_TEXTURE = Media("slice_cut2_glow.tga"),
        SLICE_BUTTON_TEXTURE = Media("slice_cut2_button.tga"),
    }
    for k, v in pairs(want) do
        assert(Theme[k] == v, k .. " = " .. tostring(Theme[k]) .. ", want " .. v)
        ASSERT_FILE(Theme[k])
    end
    assert(Theme.SLICE_MARGIN == 6, tostring(Theme.SLICE_MARGIN))
    assert(Theme.SLICE_GLOW_PAD == 4, tostring(Theme.SLICE_GLOW_PAD))
    assert(Theme.SLICE_GLOW_MARGIN == 10, tostring(Theme.SLICE_GLOW_MARGIN))
""")

case("slice_constants_keep_the_old_rounded_files_under_round", """
    assert(Theme.CHROME_CORNERS == "round")
    local want = {
        SLICE_FILL_TEXTURE = "slice_fill.tga", SLICE_BORDER_TEXTURE = "slice_border.tga",
        SLICE_GLOW_TEXTURE = "slice_glow.tga", SLICE_BUTTON_TEXTURE = "slice_button.tga",
    }
    for k, v in pairs(want) do
        assert(Theme[k] == Media(v), k .. " = " .. tostring(Theme[k]))
        ASSERT_FILE(Theme[k])
    end
    assert(Theme.SLICE_MARGIN == 5 and Theme.SLICE_GLOW_MARGIN == 9 and Theme.SLICE_GLOW_PAD == 4)
""", round_load=True)

case("the_c6_cut2_files_the_action_bars_pin_are_unchanged", """
    assert(Theme.SLICE_CUT2_OUTLINE_TEXTURE == Media("slice_cut2_outline.tga"))
    assert(Theme.SLICE_CUT2_GLOW_TEXTURE == Media("slice_cut2_glow.tga"))
    assert(Theme.SLICE_CUT2_BUTTON_TEXTURE == Media("slice_cut2_button.tga"))
    assert(Theme.SLICE_CUT_MARGIN == 6 and Theme.SLICE_CUT2_GLOW_MARGIN == 10)
""")

case("addpanelchrome_returns_fill_glow_border_in_the_2c_set", """
    local frame = NewFrame()
    local fill, glow, border = Theme.AddPanelChrome(frame, {
        fillColor = { 0.1, 0.2, 0.3, 0.5 }, accent = { 1, 0, 0 }, glowAlpha = 0.4 })
    assert(fill and glow and border, "three textures returned")
    assert(#frame.regions == 3, "exactly three regions, got " .. #frame.regions)
    assert(fill.texture == Media("slice_cut2_fill.tga") and Eq(fill.slice, { 6, 6, 6, 6 }))
    assert(Eq(fill.tint, { 0.1, 0.2, 0.3, 0.5 }))
    assert(glow.texture == Media("slice_cut2_glow.tga") and Eq(glow.slice, { 10, 10, 10, 10 }))
    assert(glow.blend == "ADD" and Eq(glow.tint, { 1, 0, 0, 0.4 }))
    assert(PointIs(glow, "TOPLEFT", "TOPLEFT", -4, 4) and PointIs(glow, "BOTTOMRIGHT", "BOTTOMRIGHT", 4, -4))
    assert(border.texture == Media("slice_cut2_border_c6.tga") and Eq(border.slice, { 6, 6, 6, 6 }))
    assert(Eq(border.tint, { 1, 0, 0, 1 }))
    assert(fill.layer == "BACKGROUND" and glow.layer == "BACKGROUND" and border.layer == "BORDER")
""")

case("addpanelchrome_defaults_match_what_skinpanel_always_drew", """
    local frame = NewFrame()
    local fill, glow = Theme.AddPanelChrome(frame)
    assert(Eq(fill.tint, { Theme.COLOR_BG[1], Theme.COLOR_BG[2], Theme.COLOR_BG[3], Theme.COLOR_BG[4] }))
    assert(Eq(glow.tint, { Theme.COLOR_BORDER[1], Theme.COLOR_BORDER[2], Theme.COLOR_BORDER[3], 0.30 }))
""")

case("addpanelchrome_under_round_uses_the_old_textures_and_margins", """
    local frame = NewFrame()
    local fill, glow, border = Theme.AddPanelChrome(frame)
    assert(fill.texture == Media("slice_fill.tga") and Eq(fill.slice, { 5, 5, 5, 5 }))
    assert(glow.texture == Media("slice_glow.tga") and Eq(glow.slice, { 9, 9, 9, 9 }))
    assert(border.texture == Media("slice_border.tga") and Eq(border.slice, { 5, 5, 5, 5 }))
""", round_load=True)

SKINPANEL_BODY = """
    Theme.ApplyMono = function() end -- font plumbing is not under test here
    local frame = NewFrame()
    local chrome = Theme.SkinPanel(frame, { title = "x", strip = false })
    -- fill, glow, border, scanline, band, rule, label
    assert(#chrome == 7, "region count " .. #chrome)
    local scan, band, rule
    for _, t in ipairs(frame.regions) do
        if t.texture == Theme.SCANLINE_TEXTURE then scan = t end
        if t.color and t.h == Theme.PANEL_HEADER_H then band = t end
        if t.color and t.h == 1 then rule = t end
    end
    assert(scan and band and rule, "scanline, band and rule exist")
    local I = %d
    assert(PointIs(scan, "TOPLEFT", "TOPLEFT", I, -I) and PointIs(scan, "BOTTOMRIGHT", "BOTTOMRIGHT", -I, I))
    assert(PointIs(band, "TOPLEFT", "TOPLEFT", I, -I) and PointIs(band, "TOPRIGHT", "TOPRIGHT", -I, -I))
    -- the rule hangs off the band, so it inherits the inset
    assert(band.points.TOPLEFT.rel == frame and rule.points.TOPLEFT.rel == band)
"""

case("skinpanel_band_rule_and_scanline_inset_ceil_c_over_two_under_cut", SKINPANEL_BODY % 3 + """
    local fill, glow, border = frame.regions[1], frame.regions[2], frame.regions[3]
    assert(fill.texture == Media("slice_cut2_fill.tga") and border.texture == Media("slice_cut2_border_c6.tga"))
    assert(glow.texture == Media("slice_cut2_glow.tga"))
""")

case("skinpanel_inset_stays_two_under_round", SKINPANEL_BODY % 2 + """
    assert(frame.regions[1].texture == Media("slice_fill.tga"))
""", round_load=True)

case("panelbandinset_is_the_inset_skinpanel_uses_ceil_c_over_two_under_cut", """
    assert(Theme.PanelBandInset() == 3)
""")

case("panelbandinset_stays_two_under_round", """
    assert(Theme.PanelBandInset() == 2)
""", round_load=True)

case("skinpanel_still_returns_only_its_own_regions", """
    local frame = NewFrame()
    local pre = frame:CreateTexture()
    local chrome = Theme.SkinPanel(frame, { strip = false, scanline = false })
    assert(#chrome == 3, "fill, glow, border only: " .. #chrome)
    for _, t in ipairs(chrome) do assert(t ~= pre) end
""")

case("skinbutton_default_is_the_2c_c6_set_when_the_height_is_unknown", """
    local b = NewFrame()
    local skin = Theme.SkinButton(b, { borderColor = { 1, 0, 0 }, glowAlpha = 0.5 })
    assert(#b.regions == 2, "same region count as before: " .. #b.regions)
    assert(skin.border.ring.texture == Media("slice_cut2_outline.tga"))
    assert(Eq(skin.border.ring.slice, { 6, 6, 6, 6 }))
    assert(skin.glow.texture == Media("slice_cut2_glow.tga"))
    assert(Eq(skin.glow.slice, { 10, 10, 10, 10 }))
    assert(PointIs(skin.glow, "TOPLEFT", "TOPLEFT", -4, 4) and PointIs(skin.glow, "BOTTOMRIGHT", "BOTTOMRIGHT", 4, -4))
    assert(skin.glow.blend == "ADD" and Eq(skin.glow.tint, { 1, 0, 0, 0.5 }))
    assert(Eq(skin.border.ring.tint, { 1, 0, 0, 1 }) and skin.border.ring.fsFlat == false)
    assert(skin.chamfer == 6)
""")

case("skinbutton_picks_the_chamfer_from_the_button_height", """
    local want = { [37] = 6, [36] = 6, [32] = 6, [24] = 4, [18] = 3, [10] = 2 }
    for h, c in pairs(want) do
        local b = NewFrame()
        b:SetSize(h, h)
        local skin = Theme.SkinButton(b)
        local suffix = c == 6 and "" or ("_c" .. c)
        assert(skin.chamfer == c, "chamfer for " .. h .. " = " .. tostring(skin.chamfer))
        assert(skin.border.ring.texture == Media("slice_cut2_outline" .. suffix .. ".tga"), h .. " ring " .. skin.border.ring.texture)
        assert(skin.glow.texture == Media("slice_cut2_glow" .. suffix .. ".tga"), h .. " glow")
        ASSERT_FILE(skin.border.ring.texture); ASSERT_FILE(skin.glow.texture)
        assert(Eq(skin.border.ring.slice, { c, c, c, c }), h .. " ring margin")
        local g = 4 + c
        assert(Eq(skin.glow.slice, { g, g, g, g }), h .. " glow margin")
        assert(#b.regions == 2, h .. " region count")
    end
""")

case("skincutbutton_is_the_same_look_as_skinbutton_at_icon_sizes_that_snap_to_c6", """
    local a, b = NewFrame(), NewFrame()
    a:SetSize(40, 40); b:SetSize(40, 40)
    local sa, sb = Theme.SkinButton(a), Theme.SkinCutButton(b)
    assert(sa.border.ring.texture == sb.border.ring.texture and sa.glow.texture == sb.glow.texture)
    assert(Eq(sa.border.ring.slice, sb.border.ring.slice) and sa.chamfer == sb.chamfer and sb.chamfer == 6)
    assert(#b.regions == 2)
""")

case("skincutbutton_stays_c6_below_30px_and_does_not_mutate_opts", """
    -- the action/stance/pet bars hard-code a c = 6 plate, wash and hover glow, so the
    -- ring must stay c = 6 however short the button is (SkinButton alone gives c = 4 at 24)
    local a, b = NewFrame(), NewFrame()
    a:SetSize(24, 24); b:SetSize(24, 24)
    assert(Theme.SkinButton(a).chamfer == 4)
    local opts = {}
    local sb = Theme.SkinCutButton(b, opts)
    assert(sb.chamfer == 6 and sb.border.ring.texture == Media("slice_cut2_outline.tga"))
    assert(Eq(sb.border.ring.slice, { 6, 6, 6, 6 }) and Eq(sb.glow.slice, { 10, 10, 10, 10 }))
    assert(opts.cut == nil and opts.chamfer == nil, "caller opts table was mutated")
    local c = NewFrame()
    c:SetSize(24, 24)
    assert(Theme.SkinCutButton(c, { chamfer = 4 }).chamfer == 4, "explicit chamfer still wins")
""")

case("skinbutton_is_idempotent_and_keeps_the_first_skin", """
    local b = NewFrame()
    local s1 = Theme.SkinButton(b)
    local s2 = Theme.SkinButton(b)
    assert(s1 == s2 and #b.regions == 2)
""")

case("skinbutton_explicit_texture_opts_still_win", """
    local b = NewFrame()
    local skin = Theme.SkinButton(b, { borderTexture = "x_ring", borderMargin = 3,
        glowTexture = "x_glow", glowPad = 2, glowMargin = 5 })
    assert(skin.border.ring.texture == "x_ring" and Eq(skin.border.ring.slice, { 3, 3, 3, 3 }))
    assert(skin.glow.texture == "x_glow" and Eq(skin.glow.slice, { 5, 5, 5, 5 }))
    assert(PointIs(skin.glow, "TOPLEFT", "TOPLEFT", -2, 2))
""")

case("skinbutton_default_is_rounded_under_round_but_skincutbutton_stays_cut", """
    local a, b = NewFrame(), NewFrame()
    local sa, sb = Theme.SkinButton(a), Theme.SkinCutButton(b)
    assert(sa.border.ring.texture == Media("slice_border.tga") and Eq(sa.border.ring.slice, { 5, 5, 5, 5 }))
    assert(sa.glow.texture == Media("slice_glow.tga") and Eq(sa.glow.slice, { 9, 9, 9, 9 }))
    assert(#a.regions == 2)
    assert(sb.border.ring.texture == Media("slice_cut2_outline.tga") and sb.glow.texture == Media("slice_cut2_glow.tga"))
""", round_load=True)

case("seatcuticon_insets_ceil_c_over_two_from_the_button_chamfer", """
    local H = LoadFrameHelpers()
    local want = { [6] = 3, [4] = 2, [3] = 2, [2] = 1 }
    for c, inset in pairs(want) do
        local b = NewFrame()
        b.icon = NewFrame()
        b.fsSkin = { chamfer = c }
        H.SeatCutIcon(b)
        assert(PointIs(b.icon, "TOPLEFT", "TOPLEFT", inset, -inset), "c=" .. c .. " TL")
        assert(PointIs(b.icon, "BOTTOMRIGHT", "BOTTOMRIGHT", -inset, inset), "c=" .. c .. " BR")
    end
""")

case("seatcuticon_default_at_c6_is_the_old_three_pixels", """
    local H = LoadFrameHelpers()
    local b = NewFrame()
    b.icon = NewFrame()
    H.SeatCutIcon(b) -- no skin recorded: the c = 6 default
    assert(PointIs(b.icon, "TOPLEFT", "TOPLEFT", 3, -3) and PointIs(b.icon, "BOTTOMRIGHT", "BOTTOMRIGHT", -3, 3))
    -- and a button actually skinned at an unknown height records c = 6 too
    local b2 = NewFrame()
    b2.icon = NewFrame()
    Theme.SkinButton(b2)
    H.SeatCutIcon(b2)
    assert(PointIs(b2.icon, "TOPLEFT", "TOPLEFT", 3, -3))
""")

case("seatcuticon_follows_a_real_small_skinned_button", """
    local H = LoadFrameHelpers()
    local b = NewFrame()
    b.icon = NewFrame()
    b:SetSize(18, 18)
    Theme.SkinButton(b) -- c = 3
    H.SeatCutIcon(b)
    assert(PointIs(b.icon, "TOPLEFT", "TOPLEFT", 2, -2) and PointIs(b.icon, "BOTTOMRIGHT", "BOTTOMRIGHT", -2, 2))
""")


# ---------------------------------------------------------------------------
# DimBlizzardFrame: the child bars register their own events
# ---------------------------------------------------------------------------

# A frame double that records event registrations and REJECTS everything DimBlizzardFrame
# must not do to a Blizzard bar: SetScript/HookScript/Hide/SetAlpha calls and any field write.
DIM_MOCK = """
local function newBar(fields, events)
    local rec = { events = {}, unregisterCalls = 0 }
    for _, e in ipairs(events or {}) do rec.events[e] = true end
    local t = {}
    function t:UnregisterAllEvents() rec.unregisterCalls = rec.unregisterCalls + 1; rec.events = {} end
    function t:SetAlpha() rec.touched = "SetAlpha" end
    function t:EnableMouse() end
    function t:GetChildren() return end
    function t:SetScript() error("SetScript on a Blizzard bar") end
    function t:HookScript() error("HookScript on a Blizzard bar") end
    function t:Hide() error("Hide on a Blizzard bar") end
    for k, v in pairs(fields or {}) do t[k] = v end
    local proxy = setmetatable({}, { __index = t, __newindex = function(_, k) error("write to field " .. tostring(k)) end })
    return proxy, rec
end
function EventCount(rec) local n = 0 for _ in pairs(rec.events) do n = n + 1 end return n end
"""

case("dimblizzardframe_unregisters_the_child_bars_events", DIM_MOCK + """
    local H = LoadFrameHelpers()
    local hb, hbR = newBar(nil, { "UNIT_MAXHEALTH", "UNIT_HEALTH", "VARIABLES_LOADED" })
    local mb, mbR = newBar(nil, { "UNIT_MAXPOWER", "UNIT_DISPLAYPOWER" })
    local sb, sbR = newBar(nil, { "CVAR_UPDATE", "UNIT_SPELLCAST_START" })
    local thb, thbR = newBar(nil, { "UNIT_MAXHEALTH" })
    local tmb, tmbR = newBar(nil, { "UNIT_MAXPOWER" })
    local tot, totR = newBar({ healthbar = thb, manabar = tmb }, { "UNIT_AURA" })
    local pet, petR = newBar(nil, { "UNIT_PET" })
    local alt, altR = newBar(nil, { "UNIT_POWER_BAR_SHOW" })
    local root, rootR = newBar({ healthbar = hb, manabar = mb, spellbar = sb, totFrame = tot,
        petFrame = pet, powerBarAlt = alt }, { "UNIT_NAME_UPDATE" })
    H.DimBlizzardFrame(root)
    for name, rec in pairs({ root = rootR, healthbar = hbR, manabar = mbR, spellbar = sbR,
        totFrame = totR, totHealth = thbR, totMana = tmbR, petFrame = petR, powerBarAlt = altR }) do
        assert(EventCount(rec) == 0, name .. " still has events registered")
        assert(rec.unregisterCalls == 1, name .. " unregistered " .. rec.unregisterCalls .. " times")
    end
""")

case("dimblizzardframe_unregisters_a_child_reachable_by_two_fields_only_once", DIM_MOCK + """
    local H = LoadFrameHelpers()
    local shared, sharedR = newBar(nil, { "UNIT_AURA" })
    local root, rootR = newBar({ totFrame = shared, petFrame = shared }, {})
    H.DimBlizzardFrame(root)
    assert(EventCount(sharedR) == 0, "shared child still has events registered")
    assert(sharedR.unregisterCalls == 1, "shared child unregistered " .. sharedR.unregisterCalls .. " times")
    assert(rootR.unregisterCalls == 1, "root unregistered " .. rootR.unregisterCalls .. " times")
""")

case("dimblizzardframe_child_pass_is_feature_detected_and_pcall_safe", DIM_MOCK + """
    local H = LoadFrameHelpers()
    -- a frame with none of the fields (BuffFrame, PetActionBar, PlayerCastingBarFrame shape)
    local plain, plainR = newBar(nil, { "UNIT_AURA" })
    H.DimBlizzardFrame(plain)
    assert(EventCount(plainR) == 0 and plainR.unregisterCalls == 1)
    -- non-table fields and a child whose UnregisterAllEvents throws must not stop the pass
    local bad = setmetatable({}, { __index = { UnregisterAllEvents = function() error("boom") end } })
    local mb, mbR = newBar(nil, { "UNIT_MAXPOWER" })
    local root = newBar({ healthbar = 5, spellbar = "x", petFrame = bad, manabar = mb }, {})
    H.DimBlizzardFrame(root)
    assert(EventCount(mbR) == 0, "a throwing sibling stopped the pass")
""")

case("dimblizzardframe_never_scripts_hides_or_writes_the_child_bars", DIM_MOCK + """
    local H = LoadFrameHelpers()
    local hb, hbR = newBar(nil, { "UNIT_MAXHEALTH" })
    local root = newBar({ healthbar = hb }, {})
    H.DimBlizzardFrame(root)           -- any SetScript/HookScript/Hide/field write on hb errors
    assert(hbR.touched == nil, "child bar was alpha-touched: " .. tostring(hbR.touched))
""")

# ---------------------------------------------------------------------------
# HUD scrim: the pet panel fill
# ---------------------------------------------------------------------------

case("hud_scrim_matches_the_mockup_pet_panel_fill", """
    local want, got = MOCKUP_SCRIM, Theme.COLOR_HUD_SCRIM
    assert(got, "Theme.COLOR_HUD_SCRIM missing")
    for i = 1, 4 do
        assert(math.abs(got[i] - want[i]) <= 0.002, "channel " .. i .. ": " .. tostring(got[i]) .. " vs mockup " .. want[i])
    end
""")

case("pet_container_fill_uses_the_hud_scrim", """
    local call = PETDOCK_SRC:match("[^\\n]*AddCut2Texture%([^\\n]*SLICE_CUT2_FILL_TEXTURE[^\\n]*")
    assert(call, "pet container fill call not found")
    assert(call:find("COLOR_HUD_SCRIM", 1, true) and not call:find("COLOR_BG", 1, true), call)
    assert(call:find("Theme.COLOR_HUD_SCRIM", 1, true), call)
""")


case("has_target_asks_issecret_about_the_unitexists_value_before_using_it", """
    -- A fresh Theme load with a client that has issecretvalue (the preamble's load has none). The spy
    -- records every value IsSecret is asked about; secretFalse makes it call a plain false "secret", the
    -- one input a Lua truth test would answer wrongly (the client's real secrets cannot be mocked as false).
    local calls, secretFalse = {}, false
    local SECRET = {}
    issecretvalue = function(v)
        calls[#calls + 1] = v
        return rawequal(v, SECRET) or (secretFalse and rawequal(v, false))
    end
    local FS2 = { LogDegradeOnce = function() end }
    assert(loadstring(THEME_SRC, "@Theme.lua"))("ForeverSynthwave", FS2)
    local answer
    UnitExists = function(unit)
        assert(unit == "target", "asked about " .. tostring(unit))
        return answer
    end
    answer = true;  assert(FS2.HasTarget() == true, "a target")
    answer = false; assert(FS2.HasTarget() == false, "no target")
    answer = nil;   assert(FS2.HasTarget() == false, "nil is no target")
    answer = 1;     assert(FS2.HasTarget() == true, "a truthy answer is normalised to true")
    -- a secret answer: IsSecret gets the exact value UnitExists returned (and only that), and the result is true
    answer, calls = SECRET, {}
    assert(FS2.HasTarget() == true, "a secret keeps it shown")
    assert(#calls == 1 and rawequal(calls[1], SECRET), "IsSecret was asked about the UnitExists value, once")
    -- the value IsSecret flags wins over its truthiness: a flagged false is shown, an unflagged false is not
    answer, secretFalse, calls = false, true, {}
    assert(FS2.HasTarget() == true, "a flagged value is never truth-tested")
    assert(#calls == 1 and rawequal(calls[1], false), "IsSecret saw the value before it was used")
    secretFalse = false
    assert(FS2.HasTarget() == false, "the same false, unflagged, reads as no target")
    -- no UnitExists on the client: shown, and nothing asked
    calls, UnitExists = {}, nil
    assert(FS2.HasTarget() == true, "a client without UnitExists keeps it shown")
    assert(#calls == 0, "nothing to ask about")
    UnitExists = "not a function"
    assert(FS2.HasTarget() == true, "a non-function UnitExists is the same as missing")
""")


case("target_takes_dots_is_the_shared_live_hostile_target_rule", """
    -- The rule GunsightDots (the scale) and GunsightFrame (the horizon's dot segment) share: a target that
    -- exists, is not dead or a ghost and can be attacked. Anything unreadable keeps it true, never a guess.
    local SECRET = {}
    local secretFalse = false
    issecretvalue = function(v)
        return rawequal(v, SECRET) or (secretFalse and (rawequal(v, false) or rawequal(v, true)))
    end
    local FS2 = { LogDegradeOnce = function() end }
    assert(loadstring(THEME_SRC, "@Theme.lua"))("ForeverSynthwave", FS2)
    assert(type(FS2.TargetTakesDots) == "function", "FS.TargetTakesDots is missing")
    local exists, dead, ghost, attack = true, false, false, true
    UnitExists = function(u) assert(u == "target"); return exists end
    UnitIsDead = function(u) assert(u == "target"); return dead end
    UnitIsDeadOrGhost = function(u) assert(u == "target"); return dead or ghost end
    UnitCanAttack = function(a, b) assert(a == "player" and b == "target", "asked " .. tostring(a) .. "," .. tostring(b)); return attack end
    local function reset() exists, dead, ghost, attack, secretFalse = true, false, false, true, false end

    assert(FS2.TargetTakesDots() == true, "a live hostile target takes dots")
    exists = false
    assert(FS2.TargetTakesDots() == false, "no target")
    reset(); dead = true
    assert(FS2.TargetTakesDots() == false, "a dead target")
    reset(); ghost = true
    assert(UnitIsDead("target") == false)
    assert(FS2.TargetTakesDots() == false, "an enemy ghost counts as dead (UnitIsDeadOrGhost)")
    reset(); attack = false
    assert(FS2.TargetTakesDots() == false, "a friendly / unattackable target")
    reset(); attack = nil
    assert(FS2.TargetTakesDots() == false, "a plain nil UnitCanAttack is false")
    reset(); attack = 1
    assert(FS2.TargetTakesDots() == true, "a plain legacy 1 is true")
    reset(); dead = 1
    assert(FS2.TargetTakesDots() == false, "a plain legacy 1 from the dead check is true")

    -- secret answers keep it true and are checked before anything else touches them
    reset(); attack, dead, secretFalse = false, true, true
    assert(FS2.TargetTakesDots() == true, "secret dead / attack answers (flagged, never truth-tested) keep it true")
    reset(); exists = SECRET
    assert(FS2.TargetTakesDots() == true, "a secret UnitExists keeps it true")
    reset(); attack = SECRET
    assert(FS2.TargetTakesDots() == true, "a secret UnitCanAttack keeps it true")
    reset(); dead = SECRET
    assert(FS2.TargetTakesDots() == true, "a secret dead answer keeps it true")

    -- throwing, odd and missing answers keep it true
    reset(); UnitCanAttack = function() error("hidden") end; UnitIsDeadOrGhost = function() error("hidden") end
    assert(FS2.TargetTakesDots() == true, "throwing predicates keep it true")
    UnitCanAttack = function() return "odd" end; UnitIsDeadOrGhost = function() return {} end
    assert(FS2.TargetTakesDots() == true, "odd types keep it true")
    UnitCanAttack, UnitIsDeadOrGhost = nil, nil
    assert(FS2.TargetTakesDots() == true, "missing predicates keep it true")
    UnitExists = nil
    assert(FS2.TargetTakesDots() == true, "a client without UnitExists keeps it true, like HasTarget")
""")


def assert_media_file(path) -> None:
    """Resolve an Interface\\AddOns\\ForeverSynthwave\\ path the way the client does (.tga) to the repo dir."""
    prefix = "Interface\\AddOns\\ForeverSynthwave\\"
    assert path.startswith(prefix), f"unexpected prefix: {path}"
    assert path.endswith(".tga"), f"not a .tga: {path}"
    target = ADDON.joinpath(*path[len(prefix):].split("\\"))
    assert target.is_file(), f"missing media file: {target}"


def run_case(name: str, body: str, round_load: bool = False) -> str | None:
    """Return None on pass, or the failure text."""
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.globals().THEME_SRC = ROUND_THEME_SRC if round_load else THEME_SRC
    rt.globals().FRAMEHELPERS_SRC = FRAMEHELPERS_SRC
    rt.globals().ASSERT_FILE = assert_media_file
    rt.globals().PETDOCK_SRC = PETDOCK_SRC
    if "MOCKUP_SCRIM" in body:
        rt.globals().MOCKUP_SCRIM = rt.table_from(list(mockup_scrim()))
    try:
        rt.execute(MOCK)
        rt.execute("local function main()\n" + body + "\nend\nmain()")
    except (LuaError, AssertionError) as exc:
        return str(exc)
    return None


def main() -> int:
    failures = 0
    for name, body, round_load in CASES:
        err = run_case(name, body, round_load)
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}: {err}")
    print(f"{len(CASES) - failures}/{len(CASES)} checks passed")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
