#!/usr/bin/env python3
"""Runs the real GunsightMyBuffs.lua (the My buffs flank plate of the Gunsight HUD) headless against a mock WoW API.

GunsightMyBuffs.lua draws the concept B plate of mockups/gunsight-modules-concepts-v7-2026-10-08.html (buffs()): a
plate outboard of the next cast tile with up to four of the player's buffs as cut tiles, the time left under each and
a cyan pip when a party or raid member cast the buff. The mockup draws it 164 x 56 with 24 px tiles; playtest found
that large, so the plate is sized from ONE tunable (Gunsight.lua's MYBUFFS tile, the Target Debuffs row chip) and
only has to stay no larger than the mockup. This harness reuses the gunsighttags
world (REAL CastBars.lua, ChevronCastBar.lua, Layout.lua, Config.lua, Gunsight.lua, GunsightBoxes.lua and
GunsightTape.lua, plus the secure frame mock) and adds the real GunsightMyBuffs.lua over a stand-in
FS.PlayerAuras (Buffs.lua is not loaded). It pins:

  * constants: cut, fill and stroke alpha, the pip and the colours parsed back out of the mockup; the tile is the
    Target Debuffs chip, the time text no smaller than the Target Debuffs time, the plate smaller than the mockup's
    and on its right edge and vertical centre, all derived from the single tunable;
  * seats: the plate fills the "mybuffs" anchor (Gunsight's rect when it has none), tiles, time text and pips sit
    at the derived offsets at two UI heights, and a rescale re-seats in place;
  * content: at most four tiles in the snapshot's own order (the Buffs.lua slot order, not by time left), the
    spell icon, the time left as 47m / 14s / 2h, nothing for a buff with no expiry;
  * time labels: each is a child of its own tile and hangs on it by real anchors (a pitch wide, centred on the tile), so it
    is centred under that tile for one to four tiles, at two UI heights and at other tile sizes; a tile that hides takes its
    time with it (no stale time under an empty slot); the widest time (three characters) fits its pitch;
  * pip: a party or raid unit other than the player; a missing, secret, player, pet or target source has none;
  * combat: the snapshot is frozen, so the time left is extrapolated from the stored expiry, a buff that ran out is
    dropped, and no aura API is read;
  * piece: the "mybuffs" piece toggle hides the plate and its ticker, and the plate hides its body with no buffs;
  * tooltip: only the tiles take the mouse, hover only (clicks pass through to the world; never the plate or body);
    hovering one shows the standard aura tooltip for
    its snapshot slot (the real FrameHelpers.ShowAuraTooltip), in combat the cached name only, a secret or a throwing
    setter shows nothing and never errors, the tooltip follows its tile when the slot or buff changes, and it goes when the tile, the body or the piece does
    (a hover during the piece's fade out shows nothing).

The mock is strict and is NOT the real client.

    python3 tools/gunsightmybuffs-harness.py

Exit 0 = every check passed. GUNSIGHTMYBUFFS_LUA=<path> runs another file in place of GunsightMyBuffs.lua.
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
MYBUFFS = Path(os.environ.get("GUNSIGHTMYBUFFS_LUA") or ADDON / "Modules/CombatHud/GunsightMyBuffs.lua")
TOC = ADDON / "forever-stuwave.toc"
MOCKUP = HERE.parent / "mockups" / "gunsight-modules-concepts-v7-2026-10-08.html"


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TG = _load("gunsighttags_harness", "gunsighttags-harness.py")
BH, TH, CB, CHEV = TG.BH, TG.TH, TG.CB, TG.CHEV


def _m(pattern: str, text: str, what: str) -> re.Match:
    m = re.search(pattern, text)
    if not m:
        sys.exit(f"mockup: cannot find {what} (pattern {pattern!r}); the mockup changed shape")
    return m


def mockup_buffs() -> dict:
    """Everything buffs() owns in the v7 mockup."""
    src = MOCKUP.read_text(encoding="utf-8")
    x0, w = _m(r"x0=(\d+),w=(\d+);\s*o\+='<polygon", src, "plate x and width").groups()
    y, h, chamfer = _m(r"ch\(x0,(\d+),w,(\d+),(\d+)\)", src, "plate rect").groups()
    fill_a = _m(r"ch\(x0,\d+,w,\d+,\d+\)\+'\" fill=\"rgba\(13,6,32,(\.\d+)\)\"", src, "plate fill").group(1)
    stroke_a = _m(r"ch\(x0,\d+,w,\d+,\d+\)\+'\" fill=\"none\" stroke=\"'\+C\.cyan\+'\" stroke-opacity=\"(\.\d+)\"", src, "plate stroke").group(1)
    inset, pitch = _m(r"var x=x0\+(\d+)\+i\*(\d+);", src, "tile pitch").groups()
    tile_dx, tile_y, size = _m(r"o\+='<g>'\+chipIcon\(x\+(\d+),(\d+),(\d+),", src, "tile").groups()
    pip_dx, pip_y, pip_r = _m(r"cx=\"'\+\(x\+(\d+)\)\+'\" cy=\"(\d+)\" r=\"([\d.]+)\"", src, "pip").groups()
    text_dx, text_y, text_size = _m(r"txt\(x\+(\d+),(\d+),d\.t,(\d+),", src, "time text").groups()
    dots_chip = _m(r"o\+=chipIcon\(1220,cy-10,(\d+),d,abs\)", src, "the Target Debuffs row chip").group(1)
    dots_time = _m(r"txt\(1246,cy\+4\.5,\(d\.rem<3\?d\.rem\.toFixed\(1\):Math\.round\(d\.rem\)\)\+'s',(\d+),", src, "the Target Debuffs time").group(1)
    count = len(re.findall(r"\{k:'", _m(r"(?s)var BUFFS_WL=\[(.*?)\];", src, "a buff list").group(1)))
    return dict(
        X=int(x0), W=int(w), Y=int(y), H=int(h), CHAMFER=int(chamfer), FILL_A=float(fill_a), STROKE_A=float(stroke_a),
        TILE_DX=int(inset) + int(tile_dx), TILE_DY=int(tile_y) - int(y), TILE=int(size), PITCH=int(pitch),
        PIP_DX=int(pip_dx) - int(tile_dx), PIP_DY=int(pip_y) - int(tile_y), PIP_R=float(pip_r),
        TEXT_DX=int(text_dx) - int(tile_dx), TEXT_Y=int(text_y) - int(y), TEXT_SIZE=int(text_size), MAX=count,
        DOTS_CHIP=int(dots_chip), DOTS_TIME=int(dots_time),
    )


MOCK = r"""
-- A stand-in for Buffs.lua's snapshot: plain values, replaced (never mutated) like the real one.
__snapshot = { buffs = {}, debuffs = {} }
__gets = 0
FS.PlayerAuras = { Get = function() __gets = __gets + 1; return __snapshot end }
-- Aura reads are refused in combat: this plate must never make one.
__auraReads = 0
function UnitAura() __auraReads = __auraReads + 1 end
C_UnitAuras = { GetAuraDataByIndex = function() __auraReads = __auraReads + 1 end }
function UnitIsUnit(a, b) return a == b or (__alias and __alias[a] == b) or false end
-- The aura read gate the real FrameHelpers.ShowAuraTooltip asks.
function FS.AurasReadable() return not InCombatLockdown() end
-- Hover-only mouse: a widget takes hover (OnEnter/OnLeave) and clicks separately. EnableMouse(v) sets both, as in the client.
do
    local Region = getmetatable(UIParent)
    local enable = Region.EnableMouse
    function Region:EnableMouse(v) enable(self, v); self._motion = v and true or false; self._click = v and true or false end
    function Region:SetMouseMotionEnabled(v) self._motion = v and true or false end
    function Region:SetMouseClickEnabled(v) self._click = v and true or false end
    function Region:IsMouseMotionEnabled() return self._motion == true end
    function Region:IsMouseClickEnabled() return self._click == true end
end
-- GameTooltip as the tooltip dispatch uses it. SetUnitAura is an aura read: refused in combat, and __tipThrows makes it throw.
-- The setters record what they were handed; a tooltip is shown by SetUnitAura or Show, as in the client.
__tip = { owner = nil, shown = false, lines = {}, aura = nil, auraCalls = 0 }
__tipThrows = false
GameTooltip = {
    SetOwner = function(self, owner, anchor) __tip.owner, __tip.anchor, __tip.shown, __tip.lines, __tip.aura = owner, anchor, false, {}, nil end,
    GetOwner = function() return __tip.owner end,
    SetUnitAura = function(self, unit, index, filter)
        __tip.auraCalls = __tip.auraCalls + 1
        if __combat or __tipThrows then error("SetUnitAura refused") end
        __tip.aura = { unit, index, filter }; __tip.shown = true
    end,
    SetText = function(self, text) __tip.lines[#__tip.lines + 1] = text end,
    AddLine = function(self, text) __tip.lines[#__tip.lines + 1] = text end,
    Show = function() __tip.shown = true end,
    Hide = function() __tip.shown = false end,
    IsShown = function() return __tip.shown end,
}
"""

CHECKS_BODY = r"""
local function rgb(c) return string.format("%02x%02x%02x", math.floor(c[1] * 255 + 0.5), math.floor(c[2] * 255 + 0.5), math.floor(c[3] * 255 + 0.5)) end
local function K() return 1.28 * FS.Layout.Scale() end
local function noFails(msg)
    if #__pcallFails > 0 then error((msg or "a pcall failed") .. ": " .. __pcallFails[1], 2) end
end
local function My() return FS.GunsightMyBuffs end
local function aura(icon, remaining, source, name)
    return { name = name or ("Buff" .. tostring(icon)), icon = icon, count = 0, dispelType = nil,
             duration = remaining and 1800 or 0, expirationTime = remaining and (__now + remaining) or 0, sourceUnit = source }
end
local function snapshot(...) __snapshot = { buffs = { ... }, debuffs = {} } end
local function refresh() My().Refresh() end
local function tick() My().plate._scripts.OnUpdate(My().plate, 0.5) end
local function shown() local n = 0; for _, t in ipairs(My().tiles) do if t.frame:IsShown() then n = n + 1 end end; return n end

-- A horizontal solver over the anchors the mock recorded: a region's left and right edge in px from the body's left edge, from the
-- REAL anchor targets, points and offsets (never the numbers the module keeps), so a label hung on the wrong target or the wrong
-- offset moves. A region with two side points spans them; one point seats its stored width around or from that point.
local function hfrac(name) if name:find("LEFT") then return 0 elseif name:find("RIGHT") then return 1 end return 0.5 end
local function edges(r)
    if r == My().body then return 0, My().anchor._w end
    local left, right, mid
    for name, p in pairs(r._points) do
        local rl, rr = edges(p.rel)
        local x = rl + hfrac(p.relPoint) * (rr - rl) + p.x
        if name:find("LEFT") then left = x elseif name:find("RIGHT") then right = x else mid = x end
    end
    if left and right then return left, right end
    ok(r._w, "a region seated by one point needs a width")
    if left then return left, left + r._w end
    if right then return right - r._w, right end
    return mid - r._w / 2, mid + r._w / 2
end
local function centre(r) local l, rt = edges(r); return (l + rt) / 2 end
-- Mononoki Bold's advance is 0.6 em: the widest a string of n characters can be at a type size.
local function textWidth(label) return #label._text * 0.6 * label._fontSize end
local function visibleText(label) return label:IsVisible() and label._text ~= "" end

-- ---- constants ---------------------------------------------------------------------

function T.constants_match_the_mockup_and_the_size_is_one_tunable_smaller_than_the_mockups()
    local W = world()
    local C = My().C
    local M = W.Gun.G.MYBUFFS
    eq(C.CHAMFER, MY.CHAMFER, "the plate cut")
    near(C.FILL[4], MY.FILL_A, 1e-9); near(C.STROKE_A, MY.STROKE_A, 1e-9)
    eq(rgb(C.FILL), "0d0620", "the plate colour")
    near(C.PIP_R, MY.PIP_R, 1e-9); eq(C.PIP_DY, MY.PIP_DY)
    eq(C.MAX, MY.MAX, "four tiles, as the mockup draws")
    -- Size: Gunsight.lua's MYBUFFS tile is the one tunable, the plate and everything in it read from it.
    eq(M.tile, MY.DOTS_CHIP, "the tile is the Target Debuffs row chip")
    ok(M.tile <= MY.TILE, "no bigger than the mockup's tile")
    eq(C.TILE, M.tile); eq(C.PITCH, M.pitch); eq(C.TILE_DX, M.padX); eq(C.TILE_DY, M.padY); eq(C.MAX, M.max)
    eq(C.X, M.x); eq(C.Y, M.y); eq(C.W, M.w); eq(C.H, M.h)
    near(M.w, 2 * M.padX + (M.max - 1) * M.pitch + M.tile, 1e-9, "the width follows from the tile and pitch")
    ok(M.pitch > M.tile, "tiles do not touch")
    ok(M.w < MY.W and M.h < MY.H, "smaller than the mockup's 164 x 56")
    near(M.x + M.w, MY.X + MY.W, 1e-9, "still ends where the mockup ends, short of the next cast tile")
    near(M.y + M.h / 2, MY.Y + MY.H / 2, 1e-9, "still centred on the mockup's band, with the info boxes and the next tile")
    ok(C.TEXT_SIZE >= MY.DOTS_TIME, "the time is no smaller than the Target Debuffs time")
    eq(C.PIP_DX, C.TILE, "the pip sits on the tile's right edge")
    ok(C.TEXT_Y > C.TILE_DY + C.TILE and C.TEXT_Y + C.TEXT_SIZE * C.DESCENT <= C.H, "the time fits inside the plate under the tile")
    W.clean(); noFails()
end

function T.changing_the_one_tunable_resizes_the_plate_and_its_tiles()
    local tile0 = tonumber(__gunsightSrc:match("local MYB_TILE = (%d+)"))
    ok(tile0, "the tunable is one `local MYB_TILE = <px>` in Gunsight.lua")
    local src, n = __gunsightSrc:gsub("local MYB_TILE = %d+", "local MYB_TILE = 16")
    eq(n, 1)
    __gunsightSrc = src
    local W = world()
    local M = W.Gun.G.MYBUFFS
    ok(16 < tile0, "the probe is smaller than the shipped tile")
    eq(M.tile, 16)
    near(M.w, 2 * M.padX + (M.max - 1) * M.pitch + 16, 1e-9, "the width follows the tile")
    eq(My().C.TILE, 16); eq(My().C.W, M.w); eq(My().C.H, M.h)
    near(My().tiles[1].frame._w, 16 * K(), 1e-6, "the tile frame")
    near((W.Gun.anchors.mybuffs or My().anchor)._w, M.w * K(), 1e-6, "and the anchor the plate fills")
    W.clean(); noFails()
end

-- ---- build and seats --------------------------------------------------------------

function T.the_plate_fills_the_mybuffs_anchor_or_the_mockup_numbers_when_gunsight_has_none()
    local W = world()
    local C = My().C
    local k = K()
    local anchor = W.Gun.anchors.mybuffs or My().anchor
    local plate = My().plate
    ok(anchor, "an anchor to fill (Gunsight's own, else the module's)")
    eq(plate._points.TOPLEFT.rel, anchor); eq(plate._points.BOTTOMRIGHT.rel, anchor)
    near(anchor._w, C.W * k, 1e-6); near(anchor._h, C.H * k, 1e-6)
    local p = anchor._points.TOPLEFT
    eq(p.rel, W.Gun.root); eq(p.relPoint, "CENTER")
    near(p.x, (C.X - W.Gun.G.CX) * k, 1e-6, "image x498 from the character centre")
    near(p.y, -(C.Y - W.Gun.G.CY) * k, 1e-6, "image y424")
    eq(plate:GetParent(), W.Gun.root)
    W.clean(); noFails()
end

function T.tiles_time_text_and_pips_sit_at_the_mockup_offsets_at_two_heights()
    local W = world()
    local C = My().C
    snapshot(aura(1, 600, "party1"), aura(2, 600), aura(3, 600), aura(4, 600, "party2"))
    refresh()
    for _, h in ipairs({ 1440, 1080 }) do
        UIParent._h = h; UIParent._w = h * 16 / 9
        __fireEvent("UI_SCALE_CHANGED")
        local k = K()
        for i = 1, 4 do
            local t = My().tiles[i]
            local left = C.TILE_DX + (i - 1) * C.PITCH
            local tp = t.frame._points.TOPLEFT
            eq(tp.rel, My().body); eq(tp.relPoint, "TOPLEFT")
            near(tp.x, left * k, 1e-6, "tile " .. i .. " x"); near(tp.y, -C.TILE_DY * k, 1e-6, "tile y")
            near(t.frame._w, C.TILE * k, 1e-6); near(t.frame._h, C.TILE * k, 1e-6)
            near(centre(t.label), centre(t.frame), 1e-6, "time centred under its own tile " .. i)
            for name, lp in pairs(t.label._points) do
                eq(lp.rel, t.frame, "the time hangs on its own tile (" .. name .. ")"); eq(lp.relPoint, name)
                near(lp.y, -(C.TEXT_Y + C.TEXT_SIZE * C.DESCENT - C.TILE_DY - C.TILE) * k, 1e-6, "time baseline")
            end
            local l, r = edges(t.label)
            near(r - l, C.PITCH * k, 1e-6, "the time's room is one pitch, centred on the tile")
            eq(t.label._justifyH, "CENTER")
            eq(t.label._fontSize, math.max(6, math.floor(C.TEXT_SIZE * k + 0.5)), "time type size")
            local pp = t.pip.dot._points.CENTER
            eq(pp.rel, t.frame); eq(pp.relPoint, "TOPLEFT")
            near(pp.x, C.PIP_DX * k, 1e-6, "pip on the tile's right edge"); near(pp.y, -C.PIP_DY * k, 1e-6, "pip just under its top")
            near(t.pip.dot._w, 2 * C.PIP_R * k, 1e-6)
        end
    end
    W.clean(); noFails()
end

function T.the_plate_art_is_a_cut_plate_with_a_cyan_outline()
    local W = world()
    local C = My().C
    local function find(pred) for _, r in ipairs(My().body._regions or {}) do if pred(r) then return r end end end
    local fill = find(function(r) return r._cutOutline == nil and r._vc[4] == C.FILL[4] end)
    ok(fill, "a fill at the mockup alpha"); eq(rgb(fill._vc), "0d0620")
    local outline = find(function(r) return r._cutOutline == true end)
    ok(outline, "an outline"); eq(rgb(outline._vc), rgb(FS.GunsightBoxes.colors.cyan)); near(outline._vc[4], C.STROKE_A, 1e-9)
    W.clean(); noFails()
end

-- ---- content ----------------------------------------------------------------------

function T.at_most_four_tiles_in_the_snapshots_own_order()
    local W = world()
    snapshot(aura(11, 100), aura(12, 4000), aura(13, 30), aura(14, 700), aura(15, 5), aura(16, 9))
    refresh()
    eq(#My().tiles, 4, "four tiles exist")
    eq(shown(), 4, "four shown of six")
    for i = 1, 4 do eq(My().tiles[i].icon._texture, 10 + i, "slot order, not time order: tile " .. i) end
    snapshot(aura(21, 100), aura(22, 100))
    refresh()
    eq(shown(), 2, "fewer buffs, fewer tiles")
    eq(My().tiles[3].frame:IsShown(), false); eq(My().tiles[4].frame:IsShown(), false)
    eq(My().tiles[1].icon._texture, 21)
    W.clean(); noFails()
end

function T.the_time_left_reads_hours_minutes_and_seconds_and_a_buff_with_no_expiry_reads_blank()
    local W = world()
    snapshot(aura(1, 47 * 60 + 5), aura(2, 14.6), aura(3, 2 * 3600 + 30), aura(4, nil))
    refresh()
    local t = My().tiles
    eq(t[1].label._text, "47m"); eq(t[2].label._text, "14s", "floored"); eq(t[3].label._text, "2h")
    eq(t[4].label._text, "", "no expiry: no time")
    eq(t[4].frame:IsShown(), true, "but the buff is there")
    eq(rgb(t[1].label._monoColor), rgb(FS.GunsightBoxes.colors.white), "white")
    W.clean(); noFails()
end

function T.a_buff_with_no_icon_still_draws_its_tile_and_never_throws()
    local W = world()
    snapshot({ name = nil, icon = nil, count = 0, duration = 60, expirationTime = __now + 60 })
    refresh()
    eq(shown(), 1)
    eq(My().tiles[1].label._text, "1m")
    W.clean(); noFails()
end

function T.the_body_hides_with_no_buffs_and_a_missing_snapshot_is_not_an_error()
    local W = world()
    snapshot()
    refresh()
    eq(My().body:IsShown(), false, "an empty plate is not drawn")
    snapshot(aura(1, 60))
    refresh()
    eq(My().body:IsShown(), true)
    FS.PlayerAuras = nil
    refresh(); tick()
    eq(My().body:IsShown(), false, "no Buffs module: nothing to draw")
    W.clean(); noFails()
end

-- ---- time labels ------------------------------------------------------------------

local function timed(n) local t = {}; for i = 1, n do t[i] = aura(i, 3500 + i * 60) end; return t end

function T.each_time_is_centred_under_its_own_tile_for_one_to_four_tiles_at_two_heights()
    local W = world()
    for _, h in ipairs({ 1440, 1080 }) do
        UIParent._h = h; UIParent._w = h * 16 / 9
        __fireEvent("UI_SCALE_CHANGED")
        for n = 1, 4 do
            __snapshot = { buffs = timed(n), debuffs = {} }
            refresh()
            eq(shown(), n)
            for i = 1, n do
                local t = My().tiles[i]
                ok(visibleText(t.label), "tile " .. i .. " of " .. n .. " shows its time")
                near(centre(t.label), centre(t.frame), 1e-6, "tile " .. i .. " of " .. n .. " at " .. h)
            end
            for i = 1, 3 do
                near(centre(My().tiles[i + 1].label) - centre(My().tiles[i].label), My().C.PITCH * K(), 1e-6, "labels step by the pitch")
            end
        end
    end
    W.clean(); noFails()
end

function T.a_time_hangs_on_its_own_tile_so_it_hides_and_moves_with_it()
    local W = world()
    snapshot(aura(1, 3500), aura(2, 3560))
    refresh()
    for i, t in ipairs(My().tiles) do
        eq(t.label:GetParent(), t.frame, "time " .. i .. " is a child of its tile")
        for _, p in pairs(t.label._points) do eq(p.rel, t.frame) end
    end
    local before = centre(My().tiles[1].label)
    My().tiles[1].frame._points.TOPLEFT.x = My().tiles[1].frame._points.TOPLEFT.x + 50
    near(centre(My().tiles[1].label), before + 50, 1e-6, "move the tile, the time follows")
    W.clean(); noFails()
end

function T.a_tile_that_hides_takes_its_time_with_it_and_a_returning_tile_shows_the_right_one()
    local W = world()
    snapshot(aura(1, 3500), aura(2, 3560), aura(3, 3590))
    refresh()
    eq(My().tiles[3].label._text, "59m")
    snapshot(aura(1, 3500), aura(2, 3560))
    refresh()
    eq(visibleText(My().tiles[3].label), false, "the third buff is gone: no stale 59m left under an empty slot")
    eq(My().tiles[3].label._text, "", "and the text is cleared, not only hidden")
    snapshot()
    refresh()
    for i = 1, 4 do eq(visibleText(My().tiles[i].label), false, "no buffs, no times: " .. i) end
    snapshot(aura(1, 3500), aura(2, 3560), aura(3, 3590))
    refresh()
    eq(visibleText(My().tiles[3].label), true, "a buff back in the slot shows its time again")
    eq(My().tiles[3].label._text, "59m")
    W.clean(); noFails()
end

function T.a_buff_with_no_time_leaves_a_gap_and_the_next_time_stays_under_its_own_tile()
    local W = world()
    snapshot(aura(1, nil), aura(2, 3500))
    refresh()
    eq(visibleText(My().tiles[1].label), false, "no expiry: nothing under tile 1")
    ok(visibleText(My().tiles[2].label))
    near(centre(My().tiles[2].label), centre(My().tiles[2].frame), 1e-6, "58m is under the second icon, not the first")
    W.clean(); noFails()
end

function T.the_widest_time_fits_its_pitch_so_neighbours_never_overlap()
    local W = world()
    local widest, longest = 0, ""
    local samples = { 0.5, 1, 9, 10, 59, 60, 599, 600, 3599, 3600, 7199, 7200, 35999, 36000, 86399, 86400, 8639999, 30 * 86400, 99 * 86400, 365 * 86400 }
    for _, h in ipairs({ 1440, 1080 }) do
        UIParent._h = h; UIParent._w = h * 16 / 9
        __fireEvent("UI_SCALE_CHANGED")
        for _, secs in ipairs(samples) do
            snapshot(aura(1, secs), aura(2, secs))
            refresh()
            local a, b = My().tiles[1].label, My().tiles[2].label
            ok(#a._text >= 2 and #a._text <= 3, secs .. " reads as " .. a._text .. ": two or three characters")
            local l, r = edges(a)
            ok(textWidth(a) <= r - l, a._text .. " fits its own room")
            ok(centre(b) - centre(a) >= textWidth(a) - 1e-6, a._text .. " and " .. b._text .. " do not overlap")
            if #a._text > #longest then longest = a._text end
        end
    end
    eq(#longest, 3, "the sweep reached a three character time")
    W.clean(); noFails()
end

local function alignmentAt(tile)
    __gunsightSrc = __gunsightSrc:gsub("local MYB_TILE = %d+", "local MYB_TILE = " .. tile)
    local W = world()
    eq(W.Gun.G.MYBUFFS.tile, tile)
    for n = 1, 4 do
        __snapshot = { buffs = timed(n), debuffs = {} }
        refresh()
        for i = 1, n do
            local t = My().tiles[i]
            near(centre(t.label), centre(t.frame), 1e-6, "tile " .. tile .. ", " .. n .. " buffs, label " .. i)
        end
    end
    snapshot(aura(1, 3500), aura(2, 3500))
    refresh()
    local a, b = My().tiles[1].label, My().tiles[2].label
    return W, centre(b) - centre(a) >= textWidth(a)
end

function T.time_alignment_holds_when_the_one_tunable_shrinks()
    local W = alignmentAt(16)
    W.clean(); noFails()
end

function T.time_alignment_and_fit_hold_when_the_one_tunable_grows()
    local W, fits = alignmentAt(26)
    ok(fits, "58m and 58m do not overlap")
    W.clean(); noFails()
end

-- ---- pip --------------------------------------------------------------------------

function T.a_cyan_pip_marks_a_buff_from_a_party_or_raid_member_other_than_the_player()
    local W = world()
    __alias = { raid5 = "player" }
    snapshot(aura(1, 60, "party1"), aura(2, 60, "raid7"), aura(3, 60, "player"), aura(4, 60, nil))
    refresh()
    local t = My().tiles
    eq(t[1].pip.dot:IsShown(), true, "party1"); eq(t[2].pip.dot:IsShown(), true, "raid7")
    eq(t[3].pip.dot:IsShown(), false, "your own buff"); eq(t[4].pip.dot:IsShown(), false, "no source: no pip")
    eq(rgb(t[1].pip.dot._colorTexture), rgb(FS.GunsightBoxes.colors.cyan), "cyan")
    snapshot(aura(1, 60, "raid5"), aura(2, 60, "target"), aura(3, 60, "partypet1"), aura(4, 60, "pet"))
    refresh()
    eq(t[1].pip.dot:IsShown(), false, "you as raid5 are still you")
    eq(t[2].pip.dot:IsShown(), false, "the target is not a party member")
    eq(t[3].pip.dot:IsShown(), false, "a party pet is not a party member"); eq(t[4].pip.dot:IsShown(), false)
    snapshot(aura(1, 60, __SECRET_NAME), aura(2, 60, 7))
    refresh()
    eq(t[1].pip.dot:IsShown(), false, "a secret source is never inspected: no pip")
    eq(t[2].pip.dot:IsShown(), false, "nor a source that is not a string")
    __alias = nil
    W.clean(); noFails("a secret source was compared inside a pcall")
end

function T.the_pip_follows_the_tile_not_the_slot()
    local W = world()
    snapshot(aura(1, 60, "party1"), aura(2, 60))
    refresh()
    snapshot(aura(2, 60), aura(1, 60, "party1"))
    refresh()
    eq(My().tiles[1].pip.dot:IsShown(), false); eq(My().tiles[2].pip.dot:IsShown(), true)
    W.clean(); noFails()
end

-- ---- combat -----------------------------------------------------------------------

function T.in_combat_the_frozen_expiries_are_extrapolated_and_no_aura_is_read()
    local W = world()
    snapshot(aura(1, 300, "party1"), aura(2, 90))
    refresh()
    eq(My().tiles[1].label._text, "5m"); eq(My().tiles[2].label._text, "1m")
    __combat = true
    local frozen = __snapshot
    __now = __now + 60
    tick()
    eq(__snapshot, frozen, "the snapshot did not change: it is frozen")
    eq(My().tiles[1].label._text, "4m", "four minutes left, from the stored expiry")
    eq(My().tiles[2].label._text, "30s", "thirty seconds")
    eq(My().tiles[1].pip.dot:IsShown(), true, "the pip survives")
    __now = __now + 40
    tick()
    eq(shown(), 1, "the 90 second buff ran out: dropped")
    eq(My().tiles[1].label._text, "3m", "the other one has 200 seconds left")
    eq(__auraReads, 0, "no aura API call in combat")
    W.clean(); noFails()
end

function T.a_buff_that_runs_out_in_combat_drops_and_the_next_one_takes_its_place()
    local W = world()
    snapshot(aura(1, 20), aura(2, 600), aura(3, 600), aura(4, 600), aura(5, 600))
    refresh()
    eq(My().tiles[1].icon._texture, 1)
    __combat = true
    __now = __now + 25
    tick()
    eq(shown(), 4, "four still shown: the fifth moved up")
    eq(My().tiles[1].icon._texture, 2, "the expired buff is gone, the rest keep their order")
    eq(My().tiles[4].icon._texture, 5)
    W.clean(); noFails()
end

function T.the_ticker_throttles_and_aura_events_refresh_at_once()
    local W = world()
    snapshot(aura(1, 120))
    refresh()
    eq(My().tiles[1].label._text, "2m")
    local gets = __gets
    My().plate._scripts.OnUpdate(My().plate, 0.1)
    eq(__gets, gets, "a short frame reads nothing")
    My().plate._scripts.OnUpdate(My().plate, 0.45)
    eq(__gets, gets + 1, "half a second later it refreshes")
    snapshot(aura(7, 30))
    __fireUnit("UNIT_AURA", "player")
    eq(My().tiles[1].icon._texture, 7, "UNIT_AURA refreshes at once")
    __fireUnit("UNIT_AURA", "target")
    eq(My().tiles[1].icon._texture, 7)
    W.clean(); noFails()
end

-- ---- tooltip ---------------------------------------------------------------------

local function enter(i) local f = My().tiles[i].frame; f._scripts.OnEnter(f) end
local function leave(i) local f = My().tiles[i].frame; f._scripts.OnLeave(f) end

function T.only_the_tiles_take_hover_and_no_clicks_so_the_world_gets_them()
    local W = world()
    for _, f in ipairs({ My().plate, My().body }) do
        eq(f:IsMouseEnabled(), false, "the plate and body let everything through")
        eq(f:IsMouseMotionEnabled(), false); eq(f:IsMouseClickEnabled(), false)
    end
    for i, t in ipairs(My().tiles) do
        eq(t.frame:IsMouseMotionEnabled(), true, "tile " .. i .. " takes hover for its tooltip")
        eq(t.frame:IsMouseClickEnabled(), false, "tile " .. i .. " takes no click: mouselook and targeting start over it")
        ok(t.frame._scripts.OnEnter and t.frame._scripts.OnLeave, "tile " .. i .. " has hover scripts")
    end
    eq(My().plate._scripts.OnEnter, nil); eq(My().body._scripts.OnEnter, nil)
    W.clean(); noFails()
end

function T.a_client_without_the_split_mouse_calls_gets_no_mouse_on_the_tiles_rather_than_click_eating_ones()
    local Region = getmetatable(UIParent)
    Region.SetMouseMotionEnabled = nil; Region.SetMouseClickEnabled = nil
    local W = world()
    for i, t in ipairs(My().tiles) do
        eq(t.frame:IsMouseEnabled(), false, "tile " .. i .. ": no tooltip beats eating clicks")
        eq(t.frame:IsMouseClickEnabled(), false)
    end
    W.clean(); noFails()
end

function T.hovering_a_tile_shows_the_aura_tooltip_for_its_snapshot_slot_and_leaving_hides_it()
    local W = world()
    snapshot(aura(1, 600), aura(2, 600), aura(3, 600), aura(4, nil))
    __snapshot.buffs[2].expirationTime = __now - 5   -- ran out: dropped from the plate, but it still holds slot 2
    refresh()
    eq(shown(), 3, "slot 2 is not drawn")
    enter(2)
    eq(__tip.owner, My().tiles[2].frame, "the tooltip belongs to the hovered tile")
    eq(__tip.shown, true)
    eq(__tip.aura[1], "player"); eq(__tip.aura[2], 3, "the tile shows the buff in slot 3, so the tooltip asks for slot 3")
    eq(__tip.aura[3], "HELPFUL")
    leave(2)
    eq(__tip.shown, false, "leaving hides it")
    enter(1)
    eq(__tip.aura[2], 1)
    W.clean(); noFails()
end

function T.in_combat_the_tooltip_is_the_cached_name_and_no_aura_is_read_for_it()
    local W = world()
    snapshot(aura(1, 600, nil, "Mark of the Wild"))
    refresh()
    __combat = true
    enter(1)
    eq(__tip.auraCalls, 0, "the tooltip setters are aura reads: not asked in combat")
    eq(__tip.lines[1], "Mark of the Wild")
    eq(__tip.shown, true)
    leave(1)
    eq(__tip.shown, false)
    W.clean(); noFails()
end

function T.a_secret_aura_name_or_a_throwing_tooltip_shows_nothing_and_never_errors()
    local W = world()
    snapshot(aura(1, 600, nil, __SECRET_NAME), aura(2, 600, nil, "Fine"))
    refresh()
    __combat = true
    enter(1)
    eq(__tip.shown, false, "a secret name is not shown, compared or kept")
    eq(#__tip.lines, 0)
    noFails("a secret was compared inside a pcall")
    __combat = false
    __tipThrows = true
    enter(2)
    eq(__tip.auraCalls, 1, "the setter was tried")
    eq(__tip.shown, false, "a refused setter shows nothing")
    __tipThrows = false
    W.clean()
    eq(#__degrades, 0, "and nothing was logged")
end

function T.the_tooltip_goes_with_its_tile_the_body_and_the_piece()
    local W = world()
    snapshot(aura(1, 600), aura(2, 600))
    refresh()
    enter(2)
    eq(__tip.shown, true)
    snapshot(aura(1, 600))
    refresh()
    eq(__tip.shown, false, "the hovered tile hid: its tooltip does not stay")
    enter(1)
    eq(__tip.shown, true)
    snapshot()
    refresh()
    eq(__tip.shown, false, "no buffs left: the body hides and the tooltip with it")
    snapshot(aura(1, 600))
    refresh()
    enter(1)
    W.Gun.SetPiece("mybuffs", false, true)
    eq(__tip.shown, false, "piece off hides the tooltip")
    W.clean(); noFails()
end

function T.a_hovered_tooltip_follows_its_tile_when_the_slot_or_the_buff_changes_and_only_then()
    local W = world()
    snapshot(aura(1, 600), aura(2, 600))
    refresh()
    enter(1)
    eq(__tip.aura[2], 1)
    local calls = __tip.auraCalls
    refresh()
    eq(__tip.auraCalls, calls, "an unchanged repaint does not rebuild the tooltip")
    -- Same buff, new slot: an earlier buff ran out and dropped from the plate, so the snapshot position moved.
    snapshot(aura(9, 600), aura(1, 600), aura(2, 600))
    __snapshot.buffs[1].expirationTime = __now - 5
    refresh()
    eq(My().tiles[1].icon._texture, 1, "the tile still shows buff 1")
    eq(__tip.aura[2], 2, "and the open tooltip moved to its new slot")
    eq(__tip.owner, My().tiles[1].frame)
    -- Different buff under the cursor.
    snapshot(aura(5, 600), aura(1, 600))
    refresh()
    eq(My().tiles[1].icon._texture, 5)
    eq(__tip.aura[2], 1, "the tooltip asks for the buff the tile shows now")
    -- Left the tile: a later change must not pop a tooltip up.
    leave(1)
    snapshot(aura(6, 600))
    refresh()
    eq(__tip.shown, false, "not hovered, no tooltip")
    W.clean(); noFails()
end

function T.in_combat_a_hovered_tooltip_follows_a_changed_cached_name()
    local W = world()
    snapshot(aura(1, 600, nil, "Old"))
    refresh()
    __combat = true
    enter(1)
    eq(__tip.lines[1], "Old")
    snapshot(aura(1, 600, nil, "New"))
    refresh()
    eq(__tip.lines[1], "New")
    eq(__tip.shown, true)
    W.clean(); noFails()
end

function T.a_tooltip_cannot_outlive_a_fading_or_hidden_piece()
    local W = world()
    snapshot(aura(1, 600), aura(2, 600))
    refresh()
    enter(1)
    eq(__tip.shown, true)
    for _, f in ipairs({ My().body, My().plate }) do
        ok(f._scripts.OnHide, "the body and the plate release the tooltip when they hide")
        enter(1)
        eq(__tip.shown, true)
        f._scripts.OnHide(f)
        eq(__tip.shown, false, "hiding releases the tile's tooltip")
    end
    -- A fade runs 0.25 s with the frame still shown: the tile can be hovered in that window.
    enter(2)
    W.Gun.SetPiece("mybuffs", false)
    eq(__tip.shown, false, "piece off releases the tooltip at once")
    enter(2)
    eq(__tip.shown, false, "and a hover during the fade shows nothing")
    W.Gun.SetPiece("mybuffs", true, true)
    enter(2)
    eq(__tip.shown, true, "back on, hover works again")
    W.clean(); noFails()
end

-- ---- piece ------------------------------------------------------------------------

function T.the_mybuffs_piece_toggle_hides_the_plate_and_its_ticker()
    local W = world()
    snapshot(aura(1, 60))
    refresh()
    eq(W.Gun.IsPieceOn("mybuffs"), true, "on by default")
    eq(My().plate:IsVisible(), true)
    local before = __countOnUpdates()
    ok(before >= 1, "the ticker runs while the piece is on")
    W.Gun.SetPiece("mybuffs", false, true)
    eq(My().plate:IsVisible(), false, "piece off hides the plate")
    eq(__countOnUpdates(), before - 1, "and its ticker stops with it")
    W.Gun.SetPiece("mybuffs", true, true)
    eq(My().plate:IsVisible(), true)
    W.clean(); noFails()
end

function T.a_rescale_reseats_in_place_and_builds_nothing()
    local W = world()
    snapshot(aura(1, 60, "party1"))
    refresh()
    local frames = countFrames()
    UIParent._h = 1080; UIParent._w = 1080 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED")
    eq(countFrames(), frames, "nothing was created again")
    near(My().tiles[1].frame._w, My().C.TILE * K(), 1e-6)
    W.clean(); noFails()
end

function T.in_a_release_build_the_deferred_plate_is_never_built_shown_or_logged()
    __myBuffsFlag = "release"
    local W = world()
    eq(FS.Features.myBuffs, false, "the release default is off")
    eq(W.Gun.IsEnabled(), true, "the rest of the Gunsight is up")
    eq(My(), nil, "the module did not install")
    snapshot(aura(1, 60))
    W.clean()
    eq(#__degrades, 0, "no log")
    eq(#__printed, 0, "no chat line")
    eq(find(function(o) return o._name == "ForeverSTUwaveGunsightMyBuffs" end), nil, "no plate frame")
    eq(__countOnUpdates(), 0, "no ticker")
    eq(W.Gun.IsPieceOn("mybuffs"), true, "a saved true setting stays harmless")
    W.Gun.SetPiece("mybuffs", false, true)
    W.Gun.SetPiece("mybuffs", true, true)
    __myBuffsFlag = nil
    noFails()
end

function T.with_the_gunsight_off_nothing_is_built_logged_or_ticking()
    local W = world({ db = { gunsight = { enabled = false } } })
    eq(W.Gun.IsEnabled(), false)
    eq(My().plate, nil, "no plate"); eq(My().tiles, nil)
    eq(#__degrades, 0, "no log")
    W.clean()
    eq(#__printed, 0, "no chat line")
    eq(__countOnUpdates(), 0, "no ticker")
    eq(find(function(o) return o._name == "ForeverSTUwaveGunsightMyBuffs" end), nil)
    noFails()
end

__checks = T
"""


def gunsight_source() -> str:
    """Gunsight.lua as the harness loads it: with the "mybuffs" piece key when the file does not have it yet."""
    src = TH.GUNSIGHT.read_text(encoding="utf-8")
    if '"mybuffs"' not in src:
        patched = src.replace('local PIECE_KEYS = { "you",', 'local PIECE_KEYS = { "mybuffs", "you",', 1)
        if patched == src:
            sys.exit("Gunsight.lua changed shape: PIECE_KEYS no longer starts with \"you\"")
        src = patched
    return src


def static_checks() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        g, m = toc.index("Modules/CombatHud/Gunsight.lua"), toc.index("Modules/CombatHud/GunsightMyBuffs.lua")
        b = toc.index("Modules/Auras/Buffs.lua")
        out.append(("toc_order", None if g < m else "GunsightMyBuffs.lua must load after Gunsight.lua"))
        out.append(("toc_buffs_before_mybuffs", None if b < m else "FS.PlayerAuras must exist when the plate builds: Buffs.lua loads first"))
    except ValueError as e:
        out.append(("toc_order", f"{e}"))
    src = MYBUFFS.read_text(encoding="utf-8") if MYBUFFS.exists() else ""
    out.append(("release_flag_defaults_off", None if "if FS.Features.myBuffs == nil then FS.Features.myBuffs = false end" in src else
                "GunsightMyBuffs.lua must default FS.Features.myBuffs to false for this release"))
    code = "\n".join(ln.split("--", 1)[0] for ln in src.splitlines())
    reads = [n for n in ("UnitAura", "UnitBuff", "C_UnitAuras", "GetPlayerAuraBySpellID") if n in code]
    out.append(("mybuffs_never_reads_auras_itself", None if not reads else
                f"GunsightMyBuffs.lua reads the FS.PlayerAuras snapshot only, it mentions {reads}"))
    strings = re.findall(r'"([^"\n]*)"', code)
    out.append(("mybuffs_player_text_never_says_tape", None if not any("tape" in s.lower() for s in strings) else
                "player text says cast bar, never tape"))
    out.append(("mybuffs_have_no_em_dash", None if "—" not in src else "no em dashes"))
    return out


def run_case(name: str, mu: dict, mb: dict, mm: dict) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(CHEV.MOCK)
    lua.execute(CB.MOCK)
    theme_src = (ADDON / "Core/Theme.lua").read_text(encoding="utf-8")
    consts = [CHEV._extract_theme_constant(theme_src, n) for n in
              TH.THEME_CONSTANTS + ("COLOR_CARET_HEALTH", "COLOR_HEAL", "COLOR_GOLD", "FLAT_TEXTURE")]
    lua.eval("__load_theme_constants")(lua.table_from(consts))
    lua.execute(CB.WIRE)
    lua.execute(TH.MOCK)
    lua.execute(TH.GS.theme_has_target_lua())
    lua.execute(BH.EXTRA_MOCK)
    lua.execute(TG.TAGS_MOCK)
    lua.execute(MOCK)
    lua.eval("__loadChevron")("Core/ChevronCastBar.lua", (ADDON / "Core/ChevronCastBar.lua").read_text(encoding="utf-8"))
    g = lua.globals()
    g.__castSrc = TH.CASTBARS.read_text(encoding="utf-8")
    g.__layoutSrc = TH.LAYOUT.read_text(encoding="utf-8")
    g.__configSrc = TH.CONFIG.read_text(encoding="utf-8")
    g.__gunsightSrc = gunsight_source()
    g.__tapeSrc = TH.TAPE.read_text(encoding="utf-8")
    g.__boxSrc = BH.BOXES.read_text(encoding="utf-8")
    g.__helpersSrc = (ADDON / "Core/FrameHelpers.lua").read_text(encoding="utf-8")
    g.__myBuffsSrc = MYBUFFS.read_text(encoding="utf-8") if MYBUFFS.exists() else "error('GunsightMyBuffs.lua is missing')"
    lua.execute("MU = " + TH.lua_value(mu))
    lua.execute("MB = " + TH.lua_value(mb))
    lua.execute("MY = " + TH.lua_value(mm))
    try:
        lua.execute(checks_source())
        lua.eval("__checks")[name]()
    except LuaError as e:
        return str(e)
    return None


def checks_source() -> str:
    prefix = TH.CHECKS.split("-- ---- constants", 1)[0]
    needle = '__load("Modules/CombatHud/GunsightTape.lua", __tapeSrc)'
    if needle not in prefix:
        sys.exit("gunsighttape-harness.py changed shape: its world() no longer loads GunsightTape.lua the way this harness patches")
    patched = prefix.replace(
        needle,
        '__load("Modules/CombatHud/GunsightBoxes.lua", __boxSrc)\n    ' + needle +
        '\n    __load("Core/FrameHelpers.lua", __helpersSrc)' +
        # The plate ships behind FS.Features.myBuffs (false by default); this harness forces it on so the code does not rot,
        # except where a case sets __myBuffsFlag = "release" to load the file as a release build does.
        '\n    FS.Features = FS.Features or {}' +
        '\n    if __myBuffsFlag ~= "release" then FS.Features.myBuffs = true end' +
        '\n    __load("Modules/CombatHud/GunsightMyBuffs.lua", __myBuffsSrc)')
    return patched + CHECKS_BODY


def main() -> int:
    mu, mb, mm = TH.mockup_tape(), BH.mockup_boxes(), mockup_buffs()
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(checks_source().replace("__checks = T", "__names = T"))
    names = sorted(k for k in lua.eval("__names").keys())
    failed = 0
    total = 0
    for name, problem in static_checks():
        total += 1
        if problem:
            failed += 1
            print(f"FAIL  {name}: {problem}")
        else:
            print(f"ok    {name}")
    for name in names:
        total += 1
        err = run_case(name, mu, mb, mm)
        if err:
            failed += 1
            print(f"FAIL  {name}: {err}")
        else:
            print(f"ok    {name}")
    print(f"\n{total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
