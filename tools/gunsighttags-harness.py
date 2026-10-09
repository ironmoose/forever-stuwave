#!/usr/bin/env python3
"""Runs the real GunsightTags.lua (the KICK style tags on the target box) headless against a mock WoW API.

GunsightTags.lua draws three tags on the target info box of the Gunsight HUD, in the shape of the KICK tag
(mockups/gunsight-modules-concepts-v7-2026-10-08.html, tag() and tags()): level and class on the top edge, health
percent and target of target on the bottom edge. This harness reuses the gunsightboxes-harness world (REAL
CastBars.lua, ChevronCastBar.lua, Layout.lua, Config.lua, Gunsight.lua, GunsightBoxes.lua and GunsightTape.lua)
and adds the real GunsightTags.lua, a mock secure button (a frame made from a Secure template is protected and
every Show, Hide, SetPoint, SetSize and EnableMouse on it, or on the frame it hangs from, throws in combat) and the
unit APIs the tags read. It pins:

  * settings: the three FS.Config keys default on and pin nothing, a change applies live (profile switch too);
  * geometry: the seats, sizes, chamfer, fill and text size are parsed back out of the mockup, at two UI heights,
    and the tags ride the box top (so the numbers' growth moves them with KICK);
  * level tag: the digits alone (no "L", no classification word: the icon is a later concept), "??" for level
    below 1, the plate sized to the text (5 pad, [icon, 3 gap], digits, 5 pad, 15 minimum, pinned in LEVEL_TAG), growing right from the same seat; a secret level goes only through SetFormattedText and reserves two
    digits without measuring; the width follows a target change and a font that lands a frame late;
  * health: the percent goes through the box's own WritePercent (the engine's percent, a secret never divided) and
    follows UNIT_HEALTH, and nothing is written with the tag off;
  * target of target: a SecureUnitButtonTemplate button with type1 = target and unit = targettarget set from plain
    Lua, the name alone (a secret name goes straight to SetText), a leaf seat of its own anchored to the box
    anchor (never to the box frame), only SetAlpha in combat, the deferred pieces applied at PLAYER_REGEN_ENABLED,
    and a build in combat that waits for the end of it.

The mock is strict and is NOT the real client.

    python3 tools/gunsighttags-harness.py

Exit 0 = every check passed. GUNSIGHTTAGS_LUA=<path> runs another file in place of GunsightTags.lua.
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
TAGS = Path(os.environ.get("GUNSIGHTTAGS_LUA") or ADDON / "Modules/CombatHud/GunsightTags.lua")
TOC = ADDON / "forever-stuwave.toc"
MOCKUP = HERE.parent / "mockups" / "gunsight-modules-concepts-v7-2026-10-08.html"
# The level plate's geometry, pinned here: pad 5, icon gap 3, minimum width 15, Mononoki's digit advance 575/1024 em.
# These came from mockups/gunsight-level-tag-2026-10-08.html (var PAD, GAP, MINW, ADV); the mockup is disposable,
# so the harness no longer reads it.
LEVEL_TAG = dict(ADV=575 / 1024, PAD=5, GAP=3, MINW=15)


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BH = _load("gunsightboxes_harness", "gunsightboxes-harness.py")
TH, CB, CHEV = BH.TH, BH.CB, BH.CHEV


def _m(pattern: str, text: str, what: str) -> re.Match:
    m = re.search(pattern, text)
    if not m:
        sys.exit(f"mockup: cannot find {what} (pattern {pattern!r}); the mockup changed shape")
    return m


def mockup_tags() -> dict:
    """Everything tag() and tags() own in the v7 mockup."""
    src = MOCKUP.read_text(encoding="utf-8")
    h, chamfer = _m(r"points=\"'\+ch\(x,y,w,(\d+),(\d+)\)\+'\" fill=\"rgba\(13,6,32,\.95\)\"", src, "tag shape").groups()
    fill_a = _m(r"fill=\"rgba\(13,6,32,(\.\d+)\)\" stroke=\"'\+C\.pink\+'\"", src, "tag fill").group(1)
    text_y, size = _m(r"<text x=\"'\+\(x\+w/2\)\+'\" y=\"'\+\(y\+(\d+)\)\+'\" font-size=\"(\d+)\"", src, "tag text").groups()
    level = _m(r"tag\((\d+),(\d+),(\d+),'L62 <tspan fill=\"'\+C\.gold\+'\">ELITE</tspan>',C\.white\)", src, "level tag").groups()
    health = _m(r"tag\((\d+),(\d+),(\d+),'62%',C\.green\)", src, "health tag").groups()
    tot = _m(r"tag\((\d+),(\d+),(\d+),'ToT <tspan fill=\"'\+C\.cyan\+'\">KERRA</tspan>',C\.white\)", src, "target of target tag").groups()
    boxes = BH.mockup_boxes()
    return dict(
        H=int(h), CHAMFER=int(chamfer), FILL_A=float(fill_a), TEXT_Y=int(text_y), TEXT_SIZE=int(size),
        LEVEL=dict(x=int(level[0]), y=int(level[1]), w=int(level[2])),
        HEALTH=dict(x=int(health[0]), y=int(health[1]), w=int(health[2])),
        TOT=dict(x=int(tot[0]), y=int(tot[1]), w=int(tot[2])),
        LT=LEVEL_TAG,
        BOXR=boxes["base"]["BOXR"], TB_GROW=boxes["TB_GROW"],
    )


TAGS_MOCK = r"""
local Region = getmetatable(UIParent)
__combat = false
function InCombatLockdown() return __combat end
-- The units the tags read.
__units.targettarget = { exists = true, name = "Kerra" }
__units.target.level, __units.target.class = 62, "elite"
function UnitLevel(u) return __units[u].level end
function UnitClassification(u) return __units[u].class end
-- Widget methods a secure unit button needs, and a record of what SetFormattedText was handed.
function Region:SetAttribute(k, v) self._attrs = self._attrs or {}; self._attrs[k] = v end
function Region:GetAttribute(k) return self._attrs and self._attrs[k] end
function Region:EnableMouse(v) self._mouse = v and true or false end
function Region:IsMouseEnabled() return self._mouse == true end
function Region:RegisterForClicks(...) self._clicks = { ... } end
function Region:IsProtected() return self._protected == true end
do
    local real = Region.SetFormattedText
    function Region:SetFormattedText(fmt, ...)
        self._fmt, self._args = fmt, { n = select("#", ...), ... }
        return real(self, fmt, ...)
    end
end
-- A frame made from a Secure template is protected.
__secure = {}
do
    local origCreate = CreateFrame
    function CreateFrame(kind, name, parent, tmpl)
        local f = origCreate(kind, name, parent, tmpl)
        f._template = tmpl
        if type(tmpl) == "string" and tmpl:find("Secure") then
            f._protected = true
            __secure[#__secure + 1] = f
        end
        return f
    end
end
-- In combat a protected frame, and a frame a protected frame hangs from, takes no Show, Hide, SetPoint,
-- ClearAllPoints, SetSize, SetWidth, SetHeight, SetAttribute or EnableMouse; the walk runs up through Gunsight's own
-- anchor frames and its root, so a reseat in combat is caught.
local function hangsFrom(p, f, seen)
    for _, pt in pairs(p._points) do
        local r = pt.rel
        if type(r) == "table" and not seen[r] then
            if r == f then return true end
            seen[r] = true
            if hangsFrom(r, f, seen) then return true end
        end
    end
    return false
end
function __restricted(f)
    if f._protected then return true end
    for _, p in ipairs(__secure) do
        if hangsFrom(p, f, {}) then return true end
    end
    return false
end
-- Every frame a protected frame hangs from, all the way up (Gunsight's anchors included): the anchor family.
function __family(p)
    local out, seen = {}, {}
    local function walk(f)
        for _, pt in pairs(f._points) do
            local r = pt.rel
            if type(r) == "table" and not seen[r] then seen[r] = true; out[#out + 1] = r; walk(r) end
        end
    end
    walk(p)
    return out
end
-- A frame that is a parent (at any depth) of a protected frame: hiding it in combat is blocked too.
function __parentsProtected(f)
    for _, p in ipairs(__secure) do
        local a = p._parent
        while a do
            if a == f then return true end
            a = a._parent
        end
    end
    return false
end
local hides = { Show = true, Hide = true, SetShown = true }
__blocked = {}
for _, name in ipairs({ "Show", "Hide", "SetShown", "SetPoint", "ClearAllPoints", "SetSize", "SetWidth", "SetHeight",
                        "SetAttribute", "EnableMouse" }) do
    local real = Region[name]
    Region[name] = function(self, ...)
        if __combat and self._kind ~= "FontString" and self._kind ~= "Texture"
            and (__restricted(self) or (hides[name] and __parentsProtected(self))) then
            __blocked[#__blocked + 1] = name
            error("ADDON_ACTION_BLOCKED: " .. name .. " on a protected frame in combat", 2)
        end
        return real(self, ...)
    end
end
"""

CHECKS_BODY = r"""
local function rgb(c) return string.format("%02x%02x%02x", math.floor(c[1] * 255 + 0.5), math.floor(c[2] * 255 + 0.5), math.floor(c[3] * 255 + 0.5)) end
local function K() return 1.28 * FS.Layout.Scale() end
local function target(name) __units.target.name = name; __fireEvent("PLAYER_TARGET_CHANGED") end
local function noFails(msg)
    if #__pcallFails > 0 then error((msg or "a pcall failed") .. ": " .. __pcallFails[1], 2) end
end
local function Tg() return FS.GunsightTags end
local function setTag(name, value) FS.Config.Set(Tg().SETTINGS[name].key, value) end
local function flush() FS.GunsightBoxes.Flush() end
-- Plate width in image px for n digits, from the level-tag mockup (digit advance 6.2 px at size 11), at the
-- font size the tag is drawn at: 2 * pad + digits, rounded up, never under the minimum.
local function digitsW(n)
    local fs = math.max(Tg().C.MIN_FONT, math.floor(FS.Gunsight.ui(Tg().C.TEXT_SIZE) + 0.5))
    return n * 6.2 * fs / 11 / K()   -- the mock's 6.2 px a digit at size 11, scaled with the font, in image px
end
local function wantW(n, icon)
    local L = Tg().C.LEVEL
    return math.max(L.minW, math.ceil(2 * L.pad + (icon or 0) + digitsW(n) - 1e-6))
end
local function levelW() return Tg().level._w / K() end

local function levelText() return Tg().level.label._text end
local function setUnit(level, class)
    __units.target.level, __units.target.class = level, class
    __fireUnit("UNIT_LEVEL", "target")
end
local function fireTot() __fireUnit("UNIT_TARGET", "target") end
local function regen() __combat = false; __fireEvent("PLAYER_REGEN_ENABLED") end
local function textureWith(frame, pred)
    for _, r in ipairs(frame._regions or {}) do if pred(r) then return r end end
end

-- ---- settings --------------------------------------------------------------------------

function T.the_three_tag_settings_default_on_and_pin_nothing()
    local W = world()
    local s = Tg().SETTINGS
    eq(s.level.key, "gunsight.tags.level"); eq(s.health.key, "gunsight.tags.health"); eq(s.tot.key, "gunsight.tags.tot")
    local n = 0
    for name, def in pairs(s) do
        n = n + 1
        eq(def.default, true, name .. " defaults on")
        eq(FS.Config.Get(def.key), true, name .. " reads on")
        ok(not FS.Config.IsStored(def.key), name .. " pins nothing")
    end
    eq(n, 3, "exactly the three the config window builds its toggles from")
    W.clean(); noFails()
end

-- ---- geometry --------------------------------------------------------------------------

function T.constants_match_the_mockup()
    local W = world()
    local C = Tg().C
    eq(C.H, MT.H); eq(C.CHAMFER, MT.CHAMFER); near(C.FILL_A, MT.FILL_A, 1e-9)
    eq(C.TEXT_SIZE, MT.TEXT_SIZE)
    eq(C.LEVEL.dx, MT.LEVEL.x - MT.BOXR.x, "level tag x from the box")
    eq(C.LEVEL.pad, MT.LT.PAD); eq(C.LEVEL.gap, MT.LT.GAP); eq(C.LEVEL.minW, MT.LT.MINW); near(C.LEVEL.advance, MT.LT.ADV, 1e-9)
    eq(C.LEVEL.w, nil, "the level plate has no fixed width")
    eq(C.HEALTH.dx, MT.HEALTH.x - MT.BOXR.x); eq(C.HEALTH.w, MT.HEALTH.w)
    eq(C.TOT.dx, MT.TOT.x - MT.BOXR.x); eq(C.TOT.w, MT.TOT.w)
    eq(C.RISE, MT.BOXR.y - MT.TB_GROW - MT.LEVEL.y, "the level tag stands this far above the grown box top")
    eq(C.OVERLAP, MT.BOXR.y + MT.BOXR.h - MT.HEALTH.y, "the bottom tags reach this far above the box bottom")
    eq(MT.HEALTH.y, MT.TOT.y, "both bottom tags share a row")
    ok(MT.LEVEL.x + MT.LEVEL.w <= MT.BOXR.x + MT.BOXR.w - FS.GunsightTape.C.KICK_DX, "the level tag ends before KICK")
    eq(rgb(FS.GunsightBoxes.colors.gold), "ffd23f")
    W.clean(); noFails()
end

function T.the_tags_are_kick_style_plates_with_a_tone_framed_outline()
    local W = world()
    local C = Tg().C
    local pink = rgb(FS.GunsightBoxes.colors.pink)
    for _, frame in ipairs({ Tg().level, Tg().health, Tg().tot }) do
        local fill = textureWith(frame, function(r) return r._cutOutline == nil and r._texture ~= nil and r._vc[4] == C.FILL_A end)
        ok(fill, "a 0.95 fill")
        eq(rgb(fill._vc), "0d0620", "in the plate colour")
        local outline = textureWith(frame.tones.pink, function(r) return r._cutOutline == true end)
        ok(outline, "a pink outline in the pink tone frame"); eq(rgb(outline._vc), pink, "in pink")
        eq(frame.label._fontSize, math.max(6, math.floor(C.TEXT_SIZE * K() + 0.5)), "the KICK text size")
    end
    W.clean(); noFails()
end

function T.the_level_and_health_tags_draw_above_every_piece_of_the_box_so_the_border_cannot_cross_their_text()
    -- The tags straddle the box edge on purpose (the mockup draws them after the box, so their .95 plate masks
    -- the edge line). On the client frames of equal level have no promised order, so the tags carry their own
    -- level, above the box's tone frames (the edge strokes, level +1) and the bars' deepest StatusBar (+3).
    local W = world()
    local C = Tg().C
    local box = W.tgt.box
    ok(C.FRAME_LEVEL > 3, "the offset clears the bars' nesting (bars +1, rail host +2, StatusBar +3)")
    for _, frame in ipairs({ Tg().level, Tg().health }) do
        eq(frame:GetParent(), box.frame, "still a child of the box")
        eq(frame:GetFrameLevel(), box.frame:GetFrameLevel() + C.FRAME_LEVEL)
        for key, tone in pairs(box.tones) do
            ok(frame:GetFrameLevel() > tone:GetFrameLevel() + 3, "above the " .. key .. " edge stroke frame")
        end
        ok(frame:GetFrameLevel() > box.bars.frame:GetFrameLevel() + 2, "above the bars (rail host +1, StatusBar +2 inside their frame)")
        local fill = textureWith(frame, function(r) return r._cutOutline == nil and r._texture ~= nil and r._vc[4] == C.FILL_A end)
        ok(fill and fill._layer == "BACKGROUND", "the plate is in the tag's own frame, under its text")
        eq(frame.label._layer, "OVERLAY", "and the text is over the plate")
    end
    W.clean(); noFails()
end

function T.the_tag_level_survives_a_rescale_and_the_target_of_target_button_is_left_alone()
    local W = world()
    local C = Tg().C
    local box = W.tgt.box
    UIParent._h = 1080; UIParent._w = 1080 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED")
    eq(Tg().level:GetFrameLevel(), box.frame:GetFrameLevel() + C.FRAME_LEVEL, "a rescale keeps it")
    ok(Tg().holder:GetFrameLevel() > box.bars.frame:GetFrameLevel() + 2, "the target of target holder already clears the bars (rail host +1, StatusBar +2)")
    W.clean(); noFails()
end

function T.the_tags_sit_at_the_mockup_seats_at_two_heights()
    local W = world()
    __charW = 6.2
    local C = Tg().C
    local box = W.tgt.box
    local boxR = W.Gun.anchors.boxR
    for _, h in ipairs({ 1440, 1080 }) do
        UIParent._h = h; UIParent._w = h * 16 / 9
        __fireEvent("UI_SCALE_CHANGED")
        local k = K()
        local lp = Tg().level._points.TOPLEFT
        eq(lp.rel, box.frame, "the level tag rides the box top"); eq(lp.relPoint, "TOPLEFT")
        near(lp.x, (MT.LEVEL.x - MT.BOXR.x) * k, 1e-6, "x")
        near(lp.y, C.RISE * k, 1e-6, "y: above the box top")
        near(Tg().level._w, wantW(#levelText(), 11 + C.LEVEL.gap) * k, 1e-6, "the plate fits the crown and the text at every height"); near(Tg().level._h, MT.H * k, 1e-6)
        local hp = Tg().health._points.TOPLEFT
        eq(hp.rel, box.frame); eq(hp.relPoint, "BOTTOMLEFT")
        near(hp.x, (MT.HEALTH.x - MT.BOXR.x) * k, 1e-6); near(hp.y, C.OVERLAP * k, 1e-6, "its top is above the box bottom")
        near(Tg().health._w, MT.HEALTH.w * k, 1e-6); near(Tg().health._h, MT.H * k, 1e-6)
        local sp = Tg().seat._points.TOPLEFT
        eq(sp.rel, boxR, "the target of target seat hangs from the box anchor"); eq(sp.relPoint, "BOTTOMLEFT")
        near(sp.x, (MT.TOT.x - MT.BOXR.x) * k, 1e-6); near(sp.y, C.OVERLAP * k, 1e-6)
        near(Tg().seat._w, MT.TOT.w * k, 1e-6); near(Tg().seat._h, MT.H * k, 1e-6)
        eq(Tg().level:GetParent(), box.frame, "children of the box: they go with the target and the piece")
        eq(Tg().health:GetParent(), box.frame)
    end
    W.clean(); noFails()
end

function T.the_level_and_health_tags_ride_the_grown_box_top_with_kick()
    local W = world()
    local C = Tg().C
    target("Kurak")
    local box = W.tgt.box
    local function top(frame) return box.frame._points.TOPLEFT.y + frame._points.TOPLEFT.y end
    local k = K()
    near(top(Tg().level), (FS.GunsightBoxes.C.TGT_GROW + C.RISE) * k, 1e-6, "numbers off: 8 above the option B box top")
    near(W.tgt.kick._points.TOPLEFT.y, top(Tg().level), 1e-6, "KICK and the level tag share a top")
    FS.Config.Set(FS.GunsightBoxes.SETTINGS.numbers.key, true); flush()
    ok(box.grow > FS.GunsightBoxes.C.TGT_GROW, "the numbers grew the box")
    near(top(Tg().level), (box.grow + C.RISE) * k, 1e-6, "the level tag rose with the top")
    near(W.tgt.kick._points.TOPLEFT.y, top(Tg().level), 1e-6, "and still shares it with KICK")
    local bottom = Tg().health._points.TOPLEFT
    near(bottom.y, C.OVERLAP * k, 1e-6, "the bottom edge tags do not move")
    near(Tg().seat._points.TOPLEFT.y, C.OVERLAP * k, 1e-6)
    W.clean(); noFails()
end

-- ---- toggles ---------------------------------------------------------------------------

function T.the_toggles_apply_live_and_the_tags_follow_the_target()
    local W = world()
    target("Kurak")
    for _, name in ipairs({ "level", "health" }) do
        local frame = Tg()[name]
        eq(frame:IsVisible(), true, name .. " shows by default")
        setTag(name, false)
        eq(frame:IsShown(), false, name .. " hides with its toggle")
        setTag(name, true)
        eq(frame:IsShown(), true, name .. " is back")
    end
    __units.target.exists = false; __fireEvent("PLAYER_TARGET_CHANGED")
    eq(Tg().level:IsVisible(), false, "no target: the box hides and takes the level tag along")
    eq(Tg().health:IsVisible(), false)
    eq(Tg().tot:GetAlpha(), 0, "the button is invisible by alpha: it is shown and clickable so a target of target can appear in combat")
    __units.target.exists = true
    W.clean(); noFails()
end

function T.a_profile_switch_applies_the_toggles_live()
    local W = world({ beforeLoad = function() UnitGUID = function() return "Player-1-AAAA" end end })
    target("Kurak")
    FS.Config.NewProfile("Raid")
    ok(FS.Config.SetActiveProfile("Raid"), "the character is known")
    setTag("level", false); setTag("health", false); setTag("tot", false)
    eq(Tg().level:IsShown(), false); eq(Tg().health:IsShown(), false); eq(Tg().tot:IsShown(), false)
    FS.Config.SetActiveProfile("Default")
    eq(Tg().level:IsShown(), true, "Default still has them on"); eq(Tg().health:IsShown(), true); eq(Tg().tot:IsShown(), true)
    FS.Config.SetActiveProfile("Raid")
    eq(Tg().level:IsShown(), false); eq(Tg().health:IsShown(), false); eq(Tg().tot:IsShown(), false)
    W.clean(); noFails()
end

-- ---- level and class -------------------------------------------------------------------

function T.the_level_tag_shows_the_digits_alone_and_the_plate_fits_them()
    local W = world()
    __charW = 6.2
    target("Kurak")
    for _, row in ipairs({ { 9, "9", 17 }, { 30, "30", 23 }, { 62, "62", 23 } }) do
        setUnit(row[1], "normal")
        eq(levelText(), row[2], "level " .. row[1] .. " reads its digits")
        near(levelW(), row[3], 1e-6, "level " .. row[1] .. " plate width in image px")
        near(levelW(), wantW(#row[2]), 1e-6, "and it is the mockup formula")
    end
    for _, class in ipairs({ "normal", "elite", "rare", "rareelite", "trivial", "minus" }) do
        setUnit(62, class)
        eq(levelText(), "62", class .. ": no word and no L")
        ok(Tg().level.label._fmt == nil or Tg().level.label._fmt == "%d", class .. ": the format is the bare number")
    end
    eq(Tg().level.label._monoColor ~= nil and rgb(Tg().level.label._monoColor), rgb(FS.GunsightBoxes.colors.white), "the level is white")
    W.clean(); noFails()
end

function T.a_level_below_one_reads_two_question_marks()
    local W = world()
    __charW = 6.2
    target("Kurak")
    for _, level in ipairs({ -1, 0 }) do
        setUnit(level, "normal")
        eq(levelText(), "??", "level " .. level)
        near(levelW(), wantW(2), 1e-6, "two characters wide")
    end
    setUnit(nil, nil)
    eq(levelText(), "", "no level, no text")
    W.clean(); noFails()
end

function T.the_level_plate_never_shrinks_under_the_minimum()
    local W = world()
    __charW = 0.5
    target("Kurak")
    setUnit(9, "normal")
    near(levelW(), Tg().C.LEVEL.minW, 1e-6, "a hair of text still gets the 15 px plate")
    near(Tg().level._h / K(), Tg().C.H, 1e-6)
    W.clean(); noFails()
end

function T.the_level_plate_grows_to_the_right_from_the_same_seat()
    local W = world()
    __charW = 6.2
    target("Kurak")
    setUnit(9, "normal")
    local p = Tg().level._points.TOPLEFT
    local x, y, rel, w = p.x, p.y, p.rel, Tg().level._w
    setUnit(30, "normal")
    local q = Tg().level._points.TOPLEFT
    ok(Tg().level._w > w + 1e-6, "the plate got wider")
    eq(q.rel, rel); near(q.x, x, 1e-9, "the left edge stays"); near(q.y, y, 1e-9, "and the top")
    local count = 0
    for _ in pairs(Tg().level._points) do count = count + 1 end
    eq(count, 1, "one point only: the width is a size, not a second anchor")
    W.clean(); noFails()
end

function T.a_secret_level_reserves_two_digits_without_measuring()
    local W = world()
    __charW = 6.2
    local measured = 0
    for _, name in ipairs({ "GetStringWidth", "GetUnboundedStringWidth" }) do
        local real = getmetatable(UIParent)[name]
        getmetatable(UIParent)[name] = function(self, ...)
            if self == Tg().level.label then measured = measured + 1 end
            return real(self, ...)
        end
    end
    target("Kurak")
    measured = 0
    setUnit(__SECRET, "normal")
    local label = Tg().level.label
    eq(label._secretText, true, "the secret level reached SetFormattedText")
    ok(rawequal(label._args[1], __SECRET), "untouched")
    eq(label._fmt, "%d", "the level is the only thing in the format: no L, no word")
    eq(measured, 0, "a secret string is never measured")
    near(levelW(), math.ceil(2 * Tg().C.LEVEL.pad + 2 * Tg().C.LEVEL.advance * Tg().C.TEXT_SIZE - 1e-6), 1e-6, "two digits reserved")
    near(levelW(), 23, 1e-6)
    setUnit(__SECRET, __SECRET_NAME)
    eq(measured, 0); near(levelW(), 23, 1e-6, "a secret classification changes nothing")
    setUnit(9, "normal")
    near(levelW(), 17, 1e-6, "a plain level afterwards measures again")
    setUnit(__SECRET, "normal")
    near(levelW(), 23, 1e-6, "and a secret one widens it back")
    W.clean(); noFails("a secret was compared, formatted or measured inside a pcall")
end

function T.the_level_width_follows_the_target_and_level_events()
    local W = world()
    __charW = 6.2
    __units.target.level, __units.target.class = 9, "normal"
    target("Kurak")
    eq(levelText(), "9", "read on a target change"); near(levelW(), 17, 1e-6)
    __units.target.level = 30
    __fireEvent("PLAYER_TARGET_CHANGED")
    eq(levelText(), "30"); near(levelW(), 23, 1e-6, "a new target widens the plate")
    __units.target.level = 8
    __fireUnit("UNIT_LEVEL", "target")
    eq(levelText(), "8"); near(levelW(), 17, 1e-6, "and a level event narrows it")
    __units.target.level = 70
    __fireUnit("UNIT_LEVEL", "player")
    eq(levelText(), "8", "another unit's level is ignored"); near(levelW(), 17, 1e-6)
    __units.target.level, __units.target.class = 8, "elite"
    __fireUnit("UNIT_CLASSIFICATION_CHANGED", "target")
    eq(levelText(), "8", "a classification change leaves the digits alone")
    W.clean(); noFails()
end

function T.the_level_icon_slot_is_empty_and_costs_no_width()
    local W = world()
    __charW = 6.2
    target("Kurak")
    setUnit(62, "normal")
    local icon = Tg().level.icon
    ok(icon ~= nil, "the slot exists")
    eq(icon:IsShown(), false, "hidden with no icon")
    near(icon._w or 0, 0, 1e-9, "zero wide")
    near(levelW(), wantW(2), 1e-6, "a normal mob costs no width")
    -- the seam: its width and one gap join the content
    Tg().SetLevelIcon(8)
    near(levelW(), wantW(2, 8 + Tg().C.LEVEL.gap), 1e-6, "an 8 px icon adds itself and a 3 px gap")
    Tg().SetLevelIcon(0)
    near(levelW(), wantW(2), 1e-6, "and removing it gives the width back")
    W.clean(); noFails()
end

function T.the_label_and_icon_sit_in_the_plate_content_pad_icon_gap_digits_pad()
    local W = world()
    __charW = 6.2
    target("Kurak")
    setUnit(62, "elite")
    local L, k = Tg().C.LEVEL, K()
    local tw = digitsW(2)
    Tg().SetLevelIcon(8, 6)
    local icon, label = Tg().level.icon, Tg().level.label
    local lead = 8 + L.gap
    local w = levelW()
    local ip, lp = icon._points.LEFT, label._points.CENTER
    eq(ip.rel, Tg().level); eq(ip.relPoint, "LEFT")
    near(ip.x, (w - (lead + tw)) / 2 * k, 1e-6, "the icon starts where the centred content starts")
    ok(ip.x > 1e-6, "inside the plate, not on its edge")
    near(icon._w, 8 * k, 1e-6, "icon width"); near(icon._h, 6 * k, 1e-6, "icon height")
    eq(icon:IsShown(), true)
    eq(lp.rel, Tg().level); eq(lp.relPoint, "CENTER")
    near(lp.x, lead / 2 * k, 1e-6, "the digits are pushed right by half the icon and gap")
    Tg().SetLevelIcon(0)
    lp = label._points.CENTER
    near(lp.x, 0, 1e-9, "no icon: the digits are centred")
    eq(icon:IsShown(), false)
    near(icon._w, 0, 1e-9)
    W.clean(); noFails()
end

-- The production table: the harness reads it, so a size or token change there is not copied here by hand.
local function ICONS() return Tg().C.ICONS end
local function vc(r) local v = r._vc; return v and { v[1], v[2], v[3], v[4] } end

function T.each_classification_draws_its_texture_at_its_size_in_its_tint()
    local W = world()
    __charW = 6.2
    local k = K()
    for class, spec in pairs(ICONS()) do
        target("Kurak")
        setUnit(30, class)
        local icon = Tg().level.icon
        eq(icon:IsShown(), true, class .. ": shown")
        eq(icon._texture, FS.Theme[spec.tex], class .. ": texture")
        near(icon._w, spec.size * k, 1e-6, class .. ": width"); near(icon._h, spec.size * k, 1e-6, class .. ": height")
        local want = spec.tint and FS.Theme[spec.tint] or { 1, 1, 1, 1 }
        local got = vc(icon)
        ok(got ~= nil, class .. ": tinted")
        for n = 1, 4 do near(got[n], want[n], 1e-6, class .. ": tint channel " .. n) end
    end
    eq(FS.Theme.LEVEL_CROWN_TEXTURE:match("[^\\]+$"), "level_crown.tga")
    eq(FS.Theme.LEVEL_STAR_TEXTURE:match("[^\\]+$"), "level_star.tga")
    eq(FS.Theme.LEVEL_CROWN_STAR_TEXTURE:match("[^\\]+$"), "level_crown_star.tga")
    eq(FS.Theme.LEVEL_SKULL_TEXTURE:match("[^\\]+$"), "level_skull.tga")
    W.clean(); noFails()
end

function T.every_icon_texture_resolves_to_a_file_in_the_media_folder()
    local W = world()
    local n = 0
    for class, spec in pairs(ICONS()) do
        n = n + 1
        local path = FS.Theme[spec.tex]
        ok(type(path) == "string", class .. ": " .. spec.tex .. " is a Theme token")
        ok(__fileExists(path), class .. ": " .. tostring(path) .. " is a file under forever-stuwave/Media/Textures/")
        if spec.tint then ok(type(FS.Theme[spec.tint]) == "table", class .. ": " .. spec.tint .. " is a Theme colour") end
    end
    ok(n >= 4, "the table was walked")
    W.clean(); noFails()
end

function T.a_classification_whose_texture_token_is_missing_falls_back_to_the_digits()
    local W = world()
    __charW = 6.2
    target("Kurak")
    FS.Theme.LEVEL_SKULL_TEXTURE = nil
    setUnit(-1, "worldboss")
    eq(Tg().level.icon:IsShown(), false, "no texture: no icon")
    eq(levelText(), "??", "the digits show instead of a blank plate")
    near(levelW(), wantW(2), 1e-6, "and the plate fits them")
    W.clean(); noFails()
end

function T.the_plate_grows_by_the_icon_width_and_a_three_px_gap()
    local W = world()
    __charW = 6.2
    local gap = Tg().C.LEVEL.gap
    eq(gap, 3)
    for _, class in ipairs({ "elite", "rare", "rareelite" }) do
        target("Kurak")
        setUnit(62, class)
        near(levelW(), wantW(2, ICONS()[class].size + gap), 1e-6, class .. ": icon + 3 + digits")
        eq(levelText(), "62", class .. ": the digits stay")
        local lp = Tg().level.label._points.CENTER
        near(lp.x, (ICONS()[class].size + gap) / 2 * K(), 1e-6, class .. ": the digits are shifted right")
    end
    W.clean(); noFails()
end

function T.normal_trivial_and_minus_draw_no_icon_and_clear_one()
    local W = world()
    __charW = 6.2
    target("Kurak")
    setUnit(62, "elite")
    eq(Tg().level.icon:IsShown(), true)
    for _, class in ipairs({ "normal", "trivial", "minus" }) do
        setUnit(62, "elite")
        setUnit(62, class)
        eq(Tg().level.icon:IsShown(), false, class .. ": no icon on the same target")
        near(levelW(), wantW(2), 1e-6, class .. ": no width for one")
        near(Tg().level.label._points.CENTER.x, 0, 1e-9, class .. ": digits centred")
    end
    setUnit(62, "elite")
    __units.target.class = "somethingnew"
    __fireUnit("UNIT_CLASSIFICATION_CHANGED", "target")
    eq(Tg().level.icon:IsShown(), false, "an unknown word draws nothing")
    __units.target.class = nil
    __fireUnit("UNIT_CLASSIFICATION_CHANGED", "target")
    eq(Tg().level.icon:IsShown(), false, "and so does no value")
    W.clean(); noFails()
end

function T.a_world_boss_is_a_skull_with_no_digits_like_the_mockup()
    local W = world()
    __charW = 6.2
    local L = Tg().C.LEVEL
    target("Kurak")
    setUnit(-1, "worldboss")
    eq(levelText(), "", "the mockup draws the skull alone: no digits, not even ??")
    eq(Tg().level.icon:IsShown(), true)
    near(levelW(), math.max(L.minW, 2 * L.pad + 11), 1e-6, "pad, skull, pad: no gap without digits")
    setUnit(__SECRET, "worldboss")
    eq(levelText(), "", "a secret level is not written beside a skull")
    setUnit(63, "worldboss")
    eq(levelText(), "", "nor a plain one")
    W.clean(); noFails()
end

function T.an_unknown_level_keeps_its_question_marks_next_to_a_classification_icon()
    local W = world()
    __charW = 6.2
    target("Kurak")
    setUnit(-1, "elite")
    eq(levelText(), "??")
    eq(Tg().level.icon._texture, FS.Theme.LEVEL_CROWN_TEXTURE)
    near(levelW(), wantW(2, 11 + Tg().C.LEVEL.gap), 1e-6, "crown, gap, two characters")
    setUnit(-1, "normal")
    eq(levelText(), "??"); eq(Tg().level.icon:IsShown(), false, "a plain mob of unknown level: ?? and no icon")
    W.clean(); noFails()
end

function T.a_secret_classification_keeps_the_icon_on_the_same_target_and_shows_none_on_a_new_one()
    local W = world()
    __charW = 6.2
    target("Kurak")
    setUnit(30, "rare")
    local before = levelW()
    setUnit(30, __SECRET_NAME)
    eq(Tg().level.icon:IsShown(), true, "same target: the icon stays")
    eq(Tg().level.icon._texture, FS.Theme.LEVEL_STAR_TEXTURE)
    near(levelW(), before, 1e-6)
    __fireUnit("UNIT_CLASSIFICATION_CHANGED", "target")
    eq(Tg().level.icon:IsShown(), true, "a classification event with a secret value keeps it too")
    -- a skull stays a skull (digits stay hidden) while the classification is unreadable
    setUnit(-1, "worldboss")
    setUnit(-1, __SECRET_NAME)
    eq(Tg().level.icon._texture, FS.Theme.LEVEL_SKULL_TEXTURE); eq(levelText(), "")
    -- a new target starts empty and a secret classification leaves it empty
    target("Other")
    eq(Tg().level.icon:IsShown(), false, "a new target: no icon")
    near(levelW(), wantW(#levelText()), 1e-6)
    __fireEvent("PLAYER_ENTERING_WORLD")
    eq(Tg().level.icon:IsShown(), false, "a world load too")
    -- and a plain one on the new target fills it
    setUnit(30, "elite")
    eq(Tg().level.icon:IsShown(), true)
    W.clean(); noFails("a secret classification was compared or indexed inside a pcall")
end

function T.a_classification_event_repaints_the_icon()
    local W = world()
    __charW = 6.2
    target("Kurak")
    setUnit(30, "normal")
    eq(Tg().level.icon:IsShown(), false)
    __units.target.class = "elite"
    __fireUnit("UNIT_CLASSIFICATION_CHANGED", "target")
    eq(Tg().level.icon:IsShown(), true, "gained")
    eq(Tg().level.icon._texture, FS.Theme.LEVEL_CROWN_TEXTURE)
    near(levelW(), wantW(2, 11 + Tg().C.LEVEL.gap), 1e-6)
    __units.target.class = "rareelite"
    __fireUnit("UNIT_CLASSIFICATION_CHANGED", "target")
    eq(Tg().level.icon._texture, FS.Theme.LEVEL_CROWN_STAR_TEXTURE, "changed")
    __fireUnit("UNIT_CLASSIFICATION_CHANGED", "player")
    __units.target.class = "normal"
    __fireUnit("UNIT_CLASSIFICATION_CHANGED", "player")
    eq(Tg().level.icon:IsShown(), true, "another unit's event is ignored")
    __fireUnit("UNIT_CLASSIFICATION_CHANGED", "target")
    eq(Tg().level.icon:IsShown(), false, "lost")
    -- a target change reads the classification at once
    __units.target.class = "worldboss"
    target("Boss")
    eq(Tg().level.icon._texture, FS.Theme.LEVEL_SKULL_TEXTURE)
    -- no target: nothing
    __units.target.exists = false
    __fireEvent("PLAYER_TARGET_CHANGED")
    eq(Tg().level.icon:IsShown(), false)
    W.clean(); noFails()
end

function T.a_level_event_for_another_unit_leaves_the_icon_and_digits_alone()
    local W = world()
    __charW = 6.2
    target("Kurak")
    setUnit(30, "elite")
    __units.target.level, __units.target.class = 8, "normal"
    __fireUnit("UNIT_LEVEL", "player")
    eq(levelText(), "30", "the digits stay"); eq(Tg().level.icon:IsShown(), true, "the icon stays")
    eq(Tg().level.icon._texture, FS.Theme.LEVEL_CROWN_TEXTURE)
    W.clean(); noFails()
end

function T.the_icon_repaints_in_combat_because_the_level_tag_is_a_plain_frame()
    local W = world()
    __charW = 6.2
    target("Kurak")
    setUnit(30, "normal")
    __combat = true
    setUnit(30, "elite")
    eq(Tg().level.icon:IsShown(), true)
    eq(#__blocked, 0)
    __combat = false
    W.clean(); noFails()
end

function T.the_level_plate_is_re_measured_a_frame_after_a_rescale_when_the_font_lands_late()
    local W = world()
    __charW = 6.2
    target("Kurak")
    setUnit(30, "normal")
    __fontLag = true
    UIParent._h = 1080; UIParent._w = 1080 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED")
    __flushTimers()
    near(levelW(), wantW(2), 1e-6, "measured at the new font, not the stale one")
    eq(Tg().level._h > 0, true)
    W.clean(); noFails()
end

function T.the_level_plate_resizes_in_combat_because_it_is_a_plain_frame()
    local W = world()
    __charW = 6.2
    target("Kurak")
    setUnit(9, "normal")
    eq(Tg().level:IsProtected(), false)
    eq(__restricted(Tg().level), false, "nothing protected hangs from it")
    __combat = true
    setUnit(30, "normal")
    near(levelW(), 23, 1e-6, "the width follows the target in combat")
    eq(#__blocked, 0)
    __combat = false
    W.clean(); noFails()
end

-- ---- health percent --------------------------------------------------------------------

function T.the_health_tag_writes_the_engine_percent_in_green_and_follows_unit_health()
    local W = world()
    target("Kurak")
    local label = Tg().health.label
    eq(label._text, "62%", "read on the target change")
    eq(rgb(label._monoColor), rgb(FS.GunsightBoxes.colors.green), "green")
    __units.target.pct = 0.41
    __fireUnit("UNIT_HEALTH", "target")
    eq(label._text, "41%", "UNIT_HEALTH moves it")
    __curveSecret = true
    __fireUnit("UNIT_HEALTH", "target")
    eq(label._secretText, true, "a secret percent goes straight to SetFormattedText")
    __curveSecret = false
    W.clean(); noFails()
end

function T.the_health_tag_reuses_the_boxes_percent_and_writes_nothing_with_the_toggle_off()
    local W = world()
    target("Kurak")
    local label = Tg().health.label
    local before = __curveCalls
    __fireUnit("UNIT_HEALTH", "target")
    local withTag = __curveCalls - before
    setTag("health", false)
    eq(W.tgt.box.healthTag, nil, "the box is told to stop")
    eq(label._text, "", "the text is cleared")
    before = __curveCalls
    __units.target.pct = 0.5
    __fireUnit("UNIT_HEALTH", "target")
    eq(__curveCalls - before, withTag - 1, "one engine percent call less per health event: the tag's")
    eq(label._text, "", "nothing written while off")
    setTag("health", true)
    eq(label._text, "50%", "turning it on reads the target at once")
    W.clean(); noFails()
end

-- ---- target of target ------------------------------------------------------------------

function T.the_target_of_target_is_a_secure_unit_button_with_attributes_set_from_plain_lua()
    local W = world()
    local b = Tg().tot
    ok(b, "the button was built")
    eq(b._template, "SecureUnitButtonTemplate"); eq(b._kind, "Button"); eq(b:IsProtected(), true)
    eq(b:GetAttribute("type1"), "target"); eq(b:GetAttribute("unit"), "targettarget")
    ok(b._clicks and #b._clicks >= 1, "registered for clicks")
    eq(b.label._text, "Kerra", "JUST the name: no ToT prefix")
    eq(rgb(b.label._monoColor), rgb(FS.GunsightBoxes.colors.white), "white")
    eq(b:GetParent(), Tg().holder, "parented to the always-shown holder")
    local snippet = false
    for _, o in ipairs(__all) do if o._attrs and o._attrs._onattributechanged then snippet = true end end
    eq(snippet, false, "no secure snippet: they do not run on this client")
    W.clean(); noFails()
end

function T.the_button_hangs_from_a_leaf_seat_and_never_from_the_box_frame()
    local W = world()
    local box, b, seat = W.tgt.box, Tg().tot, Tg().seat
    ok(seat and seat ~= box.frame, "a seat of its own")
    local n = 0
    for _, pt in pairs(b._points) do n = n + 1; eq(pt.rel, seat, "every button point is on the seat") end
    ok(n >= 1, "the button is anchored")
    for _, pt in pairs(seat._points) do eq(pt.rel, W.Gun.anchors.boxR, "the seat is on the box anchor") end
    for _, o in ipairs(__all) do
        for _, pt in pairs(o._points or {}) do
            if pt.rel == seat then eq(o, b, "nothing but the button hangs from the seat: a leaf") end
        end
    end
    for _, f in ipairs(__family(b)) do ok(f ~= box.frame, "the box frame is not in the button's anchor family") end
    for _, p in ipairs(__secure) do
        for _, pt in pairs(p._points) do ok(pt.rel ~= box.frame, "no protected frame is anchored to the box frame") end
    end
    eq(__restricted(box.frame), false, "so the box frame stays movable in combat")
    W.clean(); noFails()
end

function T.the_buttons_parent_chain_holds_only_frames_that_are_never_shown_or_hidden_in_combat()
    local W = world()
    target("Kurak")
    local b, box = Tg().tot, W.tgt.box
    local a = b._parent
    local n = 0
    while a do
        n = n + 1
        ok(a ~= box.frame and a ~= W.tgt.piece and a ~= W.tgt.gate, "no box, piece or gate frame above the button")
        a = a._parent
    end
    ok(n >= 2, "the chain was walked")
    eq(Tg().seat._parent, Tg().holder, "the seat is a leaf under the same holder")
    eq(Tg().holder:IsShown(), true, "the holder stays shown")
    __combat = true
    __units.target.exists = false; __fireEvent("PLAYER_TARGET_CHANGED")
    eq(box.frame:IsShown(), false, "the box hid in combat")
    eq(#__blocked, 0, "nothing was blocked")
    eq(b:GetAlpha(), 0, "the button is invisible by alpha alone")
    __units.target.exists = true; __fireEvent("PLAYER_TARGET_CHANGED")
    eq(box.frame:IsShown(), true); eq(b:GetAlpha(), 1, "and back")
    W.Gun.SetPiece("tgt", false, true)
    eq(#__blocked, 0, "a piece fade in combat blocks nothing")
    eq(b:GetAlpha(), 0, "the tgt piece off: invisible")
    W.Gun.SetPiece("tgt", true, true)
    eq(b:GetAlpha(), 1)
    eq(#__blocked, 0); W.clean(); noFails()
end

function T.out_of_combat_the_button_follows_the_target_of_target_and_the_toggle()
    local W = world()
    target("Kurak")
    local b = Tg().tot
    eq(b:IsShown(), true); eq(b:GetAlpha(), 1); eq(b:IsMouseEnabled(), true, "a target of target: clickable")
    __units.targettarget = { exists = false }
    fireTot()
    eq(b.label._text, "", "no target of target: no text"); eq(b:GetAlpha(), 0, "invisible")
    eq(b:IsShown(), true, "still shown"); eq(b:IsMouseEnabled(), true, "and clickable, so one that appears in combat works (a click on nothing is UNVERIFIED)")
    __units.targettarget = { exists = true, name = "Zed" }
    fireTot()
    eq(b.label._text, "Zed"); eq(b:GetAlpha(), 1); eq(b:IsMouseEnabled(), true)
    setTag("tot", false)
    eq(b:IsShown(), false, "toggled off: hidden"); eq(b:IsMouseEnabled(), false); eq(b.label._text, "")
    setTag("tot", true)
    eq(b:IsShown(), true); eq(b.label._text, "Zed", "and back")
    W.clean(); noFails()
end

function T.a_target_of_target_that_appears_after_combat_starts_is_visible_and_clickable()
    local W = world()
    __units.target.exists = false
    __units.targettarget = { exists = false }
    __fireEvent("PLAYER_TARGET_CHANGED")
    local b = Tg().tot
    eq(b:IsShown(), true, "no target at pull: the button is still shown"); eq(b:GetAlpha(), 0)
    eq(b:IsMouseEnabled(), true, "and has its mouse on")
    __combat = true
    __units.target.exists = true; __units.target.name = "Kurak"
    __units.targettarget = { exists = true, name = "Zed" }
    __fireEvent("PLAYER_TARGET_CHANGED")
    eq(b.label._text, "Zed"); eq(b:GetAlpha(), 1, "visible")
    eq(b:IsShown(), true); eq(b:IsMouseEnabled(), true, "clickable: nothing had to be enabled in combat")
    eq(b:GetAttribute("type1"), "target"); eq(b:GetAttribute("unit"), "targettarget")
    eq(#__blocked, 0, "nothing was blocked")
    W.clean(); noFails()
end

-- Forever characters have a surname: UnitName gives the first name only, GetUnitName(unit, true) gives "First Surname".
-- The REAL resolver (FS.GetFullUnitName in UnitFrames.lua, loaded before CombatHud) is installed from its source here.
local function withFullNames(extra)
    return function()
        UnitName = function(u) return __units[u].name end
        GetUnitName = function(u, withRealm)
            assert(withRealm == true, "the surname only comes through with the realm flag")
            return __units[u].full
        end
        local sys = function(v) return FS.IsSecret and FS.IsSecret(v) end
        local chunk = assert(load("local FS, IsSecret = ...\nlocal HAS_GET_UNIT_NAME = type(GetUnitName) == 'function'\n" ..
            __fullNameSrc, "@GetFullUnitName"))
        chunk(FS, sys)
        if extra then extra() end
    end
end

function T.the_target_of_target_shows_the_first_name_and_surname()
    local W = world({ beforeLoad = withFullNames() })
    target("Kurak")
    __units.targettarget = { exists = true, name = "Father", full = "Father Stu" }
    fireTot()
    eq(Tg().tot.label._text, "Father Stu", "GetUnitName(unit, true) carries the surname UnitName drops")
    __units.targettarget = { exists = true, name = "Father", full = "Father Stu-" }
    fireTot()
    eq(Tg().tot.label._text, "Father Stu", "a stray trailing separator is stripped")
    __units.targettarget = { exists = true, name = "Father", full = nil }
    fireTot()
    eq(Tg().tot.label._text, "Father", "no full name: falls back to UnitName")
    __units.targettarget = { exists = true, name = __SECRET_NAME, full = __SECRET_NAME }
    fireTot()
    ok(rawequal(Tg().tot.label._text, __SECRET_NAME), "a secret full name goes straight to SetText")
    W.clean(); noFails("a secret was compared inside a pcall")
end

-- The label is 63 image px wide (geometry locked): a longer full name shrinks to the floor, then the first names
-- shorten to initials, and only what still does not fit is left to the FontString's ellipsis.
function T.a_long_target_of_target_name_shrinks_then_abbreviates_to_fit_the_label()
    local W = world({ beforeLoad = withFullNames() })
    target("Kurak")
    local label = Tg().tot.label
    local wmax = (Tg().C.TOT.w - 2 * Tg().C.TOT_PAD) * K()
    local base = label._fontSize
    __units.targettarget = { exists = true, name = "Father", full = "Father Stu" }
    fireTot()
    eq(label._text, "Father Stu"); eq(label._fontSize, base, "a name that fits keeps the base size")
    __units.targettarget = { exists = true, name = "Father", full = "Father Stuart" }
    fireTot()
    eq(label._text, "Father Stuart", "a slightly long name shrinks first, not abbreviated")
    ok(label._fontSize < base, "smaller than the base size")
    ok(label:GetUnboundedStringWidth() <= wmax + 1e-6, "and fits the 63 px label")
    __units.targettarget = { exists = true, name = "Bartholomew", full = "Bartholomew Oldlight" }
    fireTot()
    eq(label._text, "B. Oldlight", "too long even at the floor: the first name shortens to an initial")
    ok(label:GetUnboundedStringWidth() <= wmax + 1e-6, "and fits the 63 px label")
    eq(label:GetWidth(), wmax, "the label's width is untouched")
    __units.targettarget = { exists = true, name = "Father", full = "Father Stu" }
    fireTot()
    eq(label._text, "Father Stu", "the next name is not stuck abbreviated"); eq(label._fontSize, base, "and grows back")
    W.clean(); noFails()
end

function T.a_rescale_fits_the_target_of_target_name_again_at_the_new_size()
    local W = world({ beforeLoad = withFullNames() })
    target("Kurak")
    __units.targettarget = { exists = true, name = "Bartholomew", full = "Bartholomew Oldlight" }
    fireTot()
    local label = Tg().tot.label
    UIParent._h = 1080; UIParent._w = 1080 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED")
    local wmax = (Tg().C.TOT.w - 2 * Tg().C.TOT_PAD) * K()
    eq(label:GetWidth(), wmax, "the new width")
    eq(label._text, "B. Oldlight")
    ok(label:GetUnboundedStringWidth() <= wmax + 1e-6, "fits at the new size")
    W.clean(); noFails()
end

function T.a_secret_target_of_target_name_between_two_plain_ones_does_not_stick_in_the_cache()
    local W = world({ beforeLoad = withFullNames() })
    target("Kurak")
    local label = Tg().tot.label
    __units.targettarget = { exists = true, name = "Father", full = "Father Stu" }
    fireTot()
    eq(label._text, "Father Stu")
    __units.targettarget = { exists = true, name = __SECRET_NAME, full = __SECRET_NAME }
    fireTot()
    ok(rawequal(label._text, __SECRET_NAME), "the secret replaced it")
    __units.targettarget = { exists = true, name = "Father", full = "Father Stu" }
    fireTot()
    eq(label._text, "Father Stu", "the same plain name after a secret is written again, not taken for cached")
    W.clean(); noFails()
end

-- The real client errors on ANY comparison of a secret string; the mock's __eq only runs between two tables of the
-- same metamethod. So the previous plain name is a table sharing the secret's erroring __eq (it reports itself a
-- string and prints as "Father"): a comparison against the secret then throws, and the cache must not make one.
function T.the_target_of_target_cache_never_compares_a_secret_name()
    local plain = setmetatable({}, { __eq = getmetatable(__SECRET_NAME).__eq, __tostring = function() return "Father" end })
    local realType = type
    type = function(v) if rawequal(v, plain) then return "string" end return realType(v) end
    local W = world({ beforeLoad = withFullNames(function() FS.GetFullUnitName = function(u) return __units[u].full end end) })
    target("Kurak")
    __units.targettarget = { exists = true, name = "Father", full = plain }
    fireTot()
    eq(tostring(Tg().tot.label._text), "Father", "the stand in plain name was written")
    __units.targettarget = { exists = true, name = __SECRET_NAME, full = __SECRET_NAME }
    fireTot()
    type = realType
    ok(rawequal(Tg().tot.label._text, __SECRET_NAME), "the secret reached SetText")
    W.clean(); noFails("a secret name was compared against the cached name")
end

function T.a_target_of_target_name_on_a_client_that_applies_the_font_late_is_decided_from_the_full_name()
    local W = world({ beforeLoad = withFullNames() })
    target("Kurak")
    local label = Tg().tot.label
    local wmax = (Tg().C.TOT.w - 2 * Tg().C.TOT_PAD) * K()
    local base = label._fontSize
    __fontLag = true
    __units.targettarget = { exists = true, name = "Father", full = "Father Stuart" }
    fireTot()
    -- a second name before the first font landed: its width is measured at a font that is not the one asked for
    __units.targettarget = { exists = true, name = "Father", full = "Father Stu" }
    fireTot()
    for _ = 1, 3 do __flushTimers() end
    eq(label._text, "Father Stu"); eq(label._fontSize, base, "back at the base size once the font landed")
    __units.targettarget = { exists = true, name = "Bartholomew", full = "Bartholomew Oldlight" }
    fireTot()
    for _ = 1, 3 do __flushTimers() end
    eq(label._text, "B. Oldlight")
    ok(label:GetUnboundedStringWidth() <= wmax + 1e-6, "fits at the landed font")
    __units.targettarget = { exists = true, name = "Father", full = "Father Stuart" }
    fireTot()
    for _ = 1, 3 do __flushTimers() end
    eq(label._text, "Father Stuart", "an abbreviated name is not stuck: the full name is decided again")
    ok(label:GetUnboundedStringWidth() <= wmax + 1e-6)
    W.clean(); noFails()
end

function T.a_target_of_target_name_written_before_the_late_font_landed_is_decided_again_from_the_full_name()
    local W = world({ beforeLoad = withFullNames() })
    target("Kurak")
    local label = Tg().tot.label
    __fontLag = true
    __units.targettarget = { exists = true, name = "Bartholomew", full = "Bartholomew Oldlight" }
    fireTot()
    -- the next name arrives before the font of the last one landed: it is measured at the wrong font and abbreviated
    __units.targettarget = { exists = true, name = "Father", full = "Father Stuart" }
    fireTot()
    for _ = 1, 3 do __flushTimers() end
    eq(label._text, "Father Stuart", "the abbreviated stand in is replaced once the font landed")
    eq(label._fontSize, 11, "at the size that fits it")
    ok(label:GetUnboundedStringWidth() <= (Tg().C.TOT.w - 2 * Tg().C.TOT_PAD) * K() + 1e-6)
    W.clean(); noFails()
end

function T.each_late_font_write_in_its_own_frame_gets_its_own_re_decision()
    local W = world({ beforeLoad = withFullNames() })
    target("Kurak")
    local label = Tg().tot.label
    __fontLag = true
    local function settle() for _ = 1, 3 do __flushTimers() end end
    local function pair(first, second, want, size)
        __units.targettarget = { exists = true, name = "x", full = first }
        fireTot()
        __units.targettarget = { exists = true, name = "x", full = second }
        fireTot()
        settle()
        eq(label._text, want, "after " .. first .. " then " .. second)
        eq(label._fontSize, size)
    end
    pair("Bartholomew Oldlight", "Father Stuart", "Father Stuart", 11)
    pair("Father Stu", "Father Stu", "Father Stu", 14)
    -- the first write's refit has run; a later write in a later frame needs its own
    pair("Bartholomew Oldlight", "Father Stuart", "Father Stuart", 11)
    W.clean(); noFails()
end

function T.a_late_font_that_keeps_changing_the_fit_is_re_decided_a_bounded_number_of_times()
    local W = world({ beforeLoad = withFullNames() })
    target("Kurak")
    local label = Tg().tot.label
    -- the label measures wide, then narrow, then wide again, frame after frame: every re-decision changes the size
    __wfactor = 1
    local R = getmetatable(UIParent)
    local realWidth = R.GetUnboundedStringWidth
    R.GetUnboundedStringWidth = function(self) return realWidth(self) * (self == label and __wfactor or 1) end
    __fontLag = true
    __units.targettarget = { exists = true, name = "x", full = "Father Stuart" }
    fireTot()
    local function frame(n) for _ = 1, n do __wfactor = (__wfactor == 1) and 0.4 or 1; __flushTimers() end end
    frame(4)
    local calls = __applyMonoCalls
    frame(40)
    eq(__applyMonoCalls, calls, "after the third step nothing is scheduled: no more SetFont, however many frames pass")
    W.clean(); noFails()
end

-- The calibration for the "Sneaky Toots" cases: a character width that makes a 12 character name take 0.98 of the label
-- at the floor size (so it fits there, shrunk to exactly the floor) and more than the label at the base size.
-- Returns wmax, floor, base.
local function calibrateSneaky(label)
    local wmax = (Tg().C.TOT.w - 2 * Tg().C.TOT_PAD) * K()
    local floor = math.max(Tg().C.MIN_FONT, math.floor(FS.Gunsight.ui(Tg().C.TOT_FLOOR) + 0.5))
    __charW = 0.98 * wmax * 11 / (12 * floor)
    return wmax, floor, label._fontSize
end

function T.a_target_of_target_name_is_measured_against_the_font_the_label_really_has()
    local W = world({ beforeLoad = withFullNames() })
    target("Kurak")
    local label = Tg().tot.label
    label.GetFont = function(self) return "mono", self._fontSize, "" end
    local wmax, floor, base = calibrateSneaky(label)
    __units.targettarget = { exists = true, name = "x", full = "Sneaky Toots" }
    fireTot()
    eq(label._text, "Sneaky Toots"); eq(label._fontSize, floor, "the first name shrank to the floor")
    -- a font retry puts the base size back on the label alone; the line still believes in the floor size
    label._fontSize = base
    ok(label:GetUnboundedStringWidth() > wmax, "at the base size the next name is wider than the label")
    __units.targettarget = { exists = true, name = "x", full = "Sleepy Toots" }
    fireTot()
    for _ = 1, 3 do __flushTimers() end
    eq(label._text, "Sleepy Toots", "the whole name fits once shrunk: not shortened")
    ok(label._fontSize >= floor, "and not under the floor")
    ok(label:GetUnboundedStringWidth() <= wmax + 1e-6, "at a size that fits the label")
    W.clean(); noFails()
end

function T.an_abbreviated_target_of_target_name_is_decided_again_from_the_full_name_on_the_next_frame()
    local W = world({ beforeLoad = withFullNames() })
    target("Kurak")
    local label = Tg().tot.label
    local wmax, floor = calibrateSneaky(label)
    -- the decision is measured on the probe: its first measurement is wrong (a font not applied yet reads wide); the
    -- next frame measures the real font
    local probe = Tg().totProbe
    __wfactor = 2
    local R = getmetatable(UIParent)
    local realWidth = R.GetUnboundedStringWidth
    R.GetUnboundedStringWidth = function(self)
        local f = (self == probe) and __wfactor or 1
        if self == probe then __wfactor = 1 end   -- only the first measurement (the decision) is wrong
        return realWidth(self) * f
    end
    __units.targettarget = { exists = true, name = "x", full = "Sneaky Toots" }
    fireTot()
    eq(label._text, "S. Toots", "the wrong first measurement abbreviated it")
    for _ = 1, 3 do __flushTimers() end
    eq(label._text, "Sneaky Toots", "the next frame decided again from the full name")
    ok(label:GetUnboundedStringWidth() <= wmax + 1e-6, "and it fits the label")
    ok(label._fontSize >= floor)
    W.clean(); noFails()
end

function T.a_target_of_target_name_too_long_at_the_floor_stays_abbreviated_and_the_re_decision_is_bounded()
    local W = world({ beforeLoad = withFullNames() })
    target("Kurak")
    local label = Tg().tot.label
    local wmax = (Tg().C.TOT.w - 2 * Tg().C.TOT_PAD) * K()
    __units.targettarget = { exists = true, name = "x", full = "Bartholomew Oldlight" }
    fireTot()
    eq(label._text, "B. Oldlight")
    for _ = 1, 3 do __flushTimers() end
    eq(label._text, "B. Oldlight", "decided again from the full name, still too long at the floor")
    ok(label:GetUnboundedStringWidth() <= wmax + 1e-6)
    local R = getmetatable(UIParent)
    local realSet, sets = R.SetText, 0
    R.SetText = function(self, t) if self == label then sets = sets + 1 end return realSet(self, t) end
    local calls = __applyMonoCalls
    for _ = 1, 40 do __flushTimers() end
    eq(sets, 0, "after the third step nothing is scheduled: the label is not written again")
    eq(__applyMonoCalls, calls, "and no SetFont")
    W.clean(); noFails()
end

-- A monospace font at small sizes does not scale linearly (live: "Sneaky Toots" = 80.83 px at size 12, 70.0 at size 9,
-- where linear scaling predicts 60.6). Every FontString here measures #text * perChar(size), perChar interpolated
-- between the floor and the base size. Returns wmax, floor, base.
local function nonLinearWidths(label, perCharFloor, perCharBase)
    local floor = math.max(Tg().C.MIN_FONT, math.floor(FS.Gunsight.ui(Tg().C.TOT_FLOOR) + 0.5))
    local base = label._fontSize
    local R = getmetatable(UIParent)
    R.GetUnboundedStringWidth = function(self)
        local size = self._fontSize or base
        local t = (base > floor) and (size - floor) / (base - floor) or 0
        return #tostring(self._text) * (perCharFloor + (perCharBase - perCharFloor) * t)
    end
    return (Tg().C.TOT.w - 2 * Tg().C.TOT_PAD) * K(), floor, base
end

local function recordWrites(label)
    local R = getmetatable(UIParent)
    local realSet, writes = R.SetText, {}
    R.SetText = function(self, t) if self == label then writes[#writes + 1] = t end return realSet(self, t) end
    return writes
end

function T.a_target_of_target_name_too_wide_at_the_floor_is_abbreviated_on_the_first_write_whatever_linear_scaling_says()
    local W = world({ beforeLoad = withFullNames() })
    target("Kurak")
    local label = Tg().tot.label
    local wmax, floor, base = nonLinearWidths(label, 0, 0)
    -- 12 characters: wider than the label at the floor (1.04), yet linear scaling from the base size says it fits (0.99)
    nonLinearWidths(label, 1.04 * wmax / 12, 0.99 * wmax * base / (12 * floor))
    local writes = recordWrites(label)
    __units.targettarget = { exists = true, name = "x", full = "Sneaky Toots" }
    fireTot()
    eq(label._text, "S. Toots", "abbreviated with no timer flushed")
    ok(#writes > 0 and writes[1] == "S. Toots", "the label was never written full first: " .. tostring(writes[1]))
    for _, t in ipairs(writes) do ok(t ~= "Sneaky Toots", "the full name reached the label") end
    ok(label:GetUnboundedStringWidth() <= wmax + 1e-6, "and fits the label")
    W.clean(); noFails()
end

function T.a_target_of_target_name_that_fits_at_the_floor_is_shown_whole_on_the_first_write_whatever_linear_scaling_says()
    local W = world({ beforeLoad = withFullNames() })
    target("Kurak")
    local label = Tg().tot.label
    local wmax, floor, base = nonLinearWidths(label, 0, 0)
    -- fits the label at the floor (0.97), yet linear scaling from the base size says it does not (1.1)
    nonLinearWidths(label, 0.97 * wmax / 12, 1.1 * wmax * base / (12 * floor))
    local writes = recordWrites(label)
    __units.targettarget = { exists = true, name = "x", full = "Sneaky Toots" }
    fireTot()
    eq(label._text, "Sneaky Toots", "shown whole with no timer flushed")
    eq(writes[1], "Sneaky Toots", "and the first write was the whole name")
    eq(label._fontSize, floor, "shrunk to the floor")
    ok(label:GetUnboundedStringWidth() <= wmax + 1e-6, "and fits the label")
    W.clean(); noFails()
end

function T.a_target_of_target_probe_that_cannot_measure_falls_back_to_the_label_width_scaled_to_the_floor()
    local W = world({ beforeLoad = withFullNames() })
    target("Kurak")
    local label, probe = Tg().tot.label, Tg().totProbe
    local wmax, floor, base = nonLinearWidths(label, 0, 0)
    -- the label at its own size scaled to the floor is 1.1 of the label width: too wide, so abbreviated
    local perChar = 1.1 * wmax * base / (12 * floor)
    nonLinearWidths(label, perChar, perChar)
    local measure = getmetatable(UIParent).GetUnboundedStringWidth
    getmetatable(UIParent).GetUnboundedStringWidth = function(self)
        if self == probe then return nil end
        return measure(self)
    end
    __units.targettarget = { exists = true, name = "x", full = "Sneaky Toots" }
    fireTot()
    eq(label._text, "S. Toots", "the label's own width decided it, as the probe measured nothing")
    W.clean(); noFails()
end

function T.a_rescale_sets_the_target_of_target_measuring_font_once_and_a_name_write_never_does()
    local per = {}
    local W = world({ beforeLoad = withFullNames(function()
        local real = FS.Theme.ApplyMono
        FS.Theme.ApplyMono = function(fs, ...) per[fs] = (per[fs] or 0) + 1; return real(fs, ...) end
    end) })
    target("Kurak")
    local probe = Tg().totProbe
    ok(probe, "the target of target owns a measuring FontString")
    eq(probe:IsShown(), false, "never shown")
    local floor0 = math.max(Tg().C.MIN_FONT, math.floor(FS.Gunsight.ui(Tg().C.TOT_FLOOR) + 0.5))
    eq(probe._fontSize, floor0, "set to the floor size")
    local built = per[probe]
    for _, full in ipairs({ "Sneaky Toots", "Father Stu", "Bartholomew Oldlight", "Zed" }) do
        __units.targettarget = { exists = true, name = "x", full = full }
        fireTot()
    end
    eq(per[probe], built, "no SetFont on the probe per name write")
    UIParent._h = 1080; UIParent._w = 1080 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED")
    local floor1 = math.max(Tg().C.MIN_FONT, math.floor(FS.Gunsight.ui(Tg().C.TOT_FLOOR) + 0.5))
    ok(floor1 ~= floor0, "the rescale moves the floor size")
    eq(probe._fontSize, floor1, "the probe follows the new floor")
    eq(per[probe], built + 1, "one SetFont for the rescale")
    __units.targettarget = { exists = true, name = "x", full = "Another Name" }
    fireTot()
    eq(per[probe], built + 1, "and none after it")
    W.clean(); noFails()
end

function T.a_name_whose_fit_throws_is_not_left_cached_as_fitted()
    local W = world({ beforeLoad = withFullNames() })
    target("Kurak")
    local label = Tg().tot.label
    __units.targettarget = { exists = true, name = "x", full = "Father Stu" }
    fireTot()
    eq(label._text, "Father Stu")
    local R = getmetatable(UIParent)
    local realSetText = R.SetText
    __boom = true
    R.SetText = function(self, t)
        if __boom and self == label and t == "Another Name" then error("SetText refused") end
        return realSetText(self, t)
    end
    __units.targettarget = { exists = true, name = "x", full = "Another Name" }
    fireTot()
    eq(label._text, "Father Stu", "the failed write changed nothing")
    __pcallFails = {}
    __boom = false
    fireTot()
    eq(label._text, "Another Name", "the same name is fitted again, not skipped as already done")
    W.clean(); noFails()
end

function T.the_target_of_target_label_is_built_with_one_font_and_a_fitting_name_sets_no_more()
    local per = {}
    local W = world({ beforeLoad = withFullNames(function()
        local real = FS.Theme.ApplyMono
        FS.Theme.ApplyMono = function(fs, ...) per[fs] = (per[fs] or 0) + 1; return real(fs, ...) end
    end) })
    target("Kurak")
    local label = Tg().tot.label
    __units.targettarget = { exists = true, name = "Father", full = "Father Stu" }
    fireTot()
    eq(per[label], 1, "NewTag's font only: the fit starts from the size the label was built at")
    W.clean(); noFails()
end

function T.target_of_target_name_fit_does_not_set_the_font_per_event()
    local W = world({ beforeLoad = withFullNames() })
    target("Kurak")
    __units.targettarget = { exists = true, name = "Bartholomew", full = "Bartholomew Oldlight" }
    fireTot()
    local calls = __applyMonoCalls
    for _ = 1, 10 do fireTot() end
    eq(__applyMonoCalls, calls, "ten identical events: no SetFont")
    W.clean(); noFails()
end

function T.a_secret_target_of_target_name_is_not_measured_or_abbreviated()
    local W = world({ beforeLoad = withFullNames() })
    target("Kurak")
    __units.targettarget = { exists = true, name = __SECRET_NAME, full = __SECRET_NAME }
    fireTot()
    ok(rawequal(Tg().tot.label._text, __SECRET_NAME), "SetText took it untouched")
    W.clean(); noFails("a secret was measured or compared")
end

function T.the_target_of_target_falls_back_to_unit_name_without_the_shared_resolver()
    local W = world()
    target("Kurak")
    FS.GetFullUnitName = nil
    __units.targettarget = { exists = true, name = "Zed" }
    fireTot()
    eq(Tg().tot.label._text, "Zed", "UnitFrames.lua not loaded: UnitName")
    W.clean(); noFails()
end

function T.a_secret_target_of_target_name_goes_straight_to_set_text()
    local W = world()
    target("Kurak")
    __units.targettarget = { exists = true, name = __SECRET_NAME }
    fireTot()
    ok(rawequal(Tg().tot.label._text, __SECRET_NAME), "the name sink took it untouched")
    eq(Tg().tot:GetAlpha(), 1)
    __units.targettarget = { exists = __SECRET_BOOL, name = __SECRET_NAME }
    fireTot()
    eq(Tg().tot:GetAlpha(), 1, "an unreadable UnitExists keeps it shown")
    W.clean(); noFails("a secret was compared inside a pcall")
end

function T.in_combat_the_button_only_takes_alpha_and_text()
    local W = world()
    target("Kurak")
    local b = Tg().tot
    __combat = true
    __units.targettarget = { exists = false }
    fireTot()
    eq(b:GetAlpha(), 0, "no target of target: alpha 0"); eq(b.label._text, "")
    eq(b:IsShown(), true, "never hidden in combat"); eq(b:IsMouseEnabled(), true, "and its mouse stays on")
    __units.targettarget = { exists = true, name = "Zed" }
    fireTot()
    eq(b:GetAlpha(), 1); eq(b.label._text, "Zed", "a target of target that shows up mid fight")
    target("Other")
    setTag("tot", false)
    eq(b:GetAlpha(), 0, "toggled off in combat: alpha only")
    eq(b:IsShown(), true, "still shown until the fight ends")
    setTag("tot", true)
    eq(b:GetAlpha(), 1)
    eq(#__blocked, 0, "no protected call was attempted")
    setTag("tot", false)
    regen()
    eq(b:IsShown(), false, "the end of combat reconciles the toggle"); eq(b:IsMouseEnabled(), false)
    W.clean(); noFails()
end

function T.in_combat_the_box_still_grows_and_the_tags_move_because_only_the_seat_is_restricted()
    local W = world()
    target("Kurak")
    ok(Tg().tot and #__secure == 1, "the secure button exists, so a restricted family exists")
    __combat = true
    FS.Config.Set(FS.GunsightBoxes.SETTINGS.numbers.key, true); flush()
    local box = W.tgt.box
    ok(box.grow > FS.GunsightBoxes.C.TGT_GROW, "the box grew in combat")
    near(box.frame._points.TOPLEFT.y, box.grow * K(), 1e-6)
    eq(#__blocked, 0, "no protected call was attempted")
    W.clean(); noFails()
end

function T.a_rescale_in_combat_waits_for_the_seat_and_the_button()
    local W = world()
    target("Kurak")
    local seat = Tg().seat
    local oldW, oldK = seat._w, K()
    local boxR, root = W.Gun.anchors.boxR, W.Gun.root
    local anchorW, rootX = boxR._w, root._points.CENTER.x
    __combat = true
    UIParent._h = 1080; UIParent._w = 1080 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED")
    local k = K()
    ok(k ~= oldK, "the scale changed")
    eq(boxR._w, anchorW, "Gunsight's anchor waits for the end of combat: the button hangs from it")
    eq(root._points.CENTER.x, rootX, "and so does its root")
    near(Tg().level._h, MT.H * k, 1e-6, "the plain tags resized at once")
    ok(Tg().level._w >= MT.LT.MINW * k - 1e-6, "and the level plate kept its fitted width")
    near(seat._w, oldW, 1e-9, "the seat waits")
    eq(#__blocked, 0)
    regen()
    near(boxR._w, MT.BOXR.w * k, 1e-6, "Gunsight reseated once combat ended")
    near(seat._w, MT.TOT.w * k, 1e-6, "applied at the end of combat")
    near(seat._points.TOPLEFT.x, (MT.TOT.x - MT.BOXR.x) * k, 1e-6)
    near(Tg().tot.label._fontSize, math.max(6, math.floor(Tg().C.TEXT_SIZE * k + 0.5)), 1e-9)
    W.clean(); noFails()
end

function T.a_build_in_combat_makes_the_button_at_the_end_of_it()
    local W = world({ beforeLoad = function() __combat = true end })
    eq(Tg().tot, nil, "no secure frame is made in combat")
    eq(#__secure, 0)
    ok(Tg().level and Tg().health, "the plain tags are built")
    __units.target.name = "Kurak"
    regen()
    ok(Tg().tot, "built when combat ends")
    eq(Tg().tot:GetAttribute("type1"), "target"); eq(Tg().tot:GetAttribute("unit"), "targettarget")
    eq(Tg().tot.label._text, "Kerra")
    eq(#__blocked, 0)
    W.clean(); noFails()
end

function T.the_button_is_never_touched_by_a_target_change_in_combat()
    local W = world()
    target("Kurak")
    ok(Tg().tot, "the secure button exists")
    __combat = true
    target("Other"); target("Third")
    __units.target.exists = false; __fireEvent("PLAYER_TARGET_CHANGED")
    __units.target.exists = true; __fireEvent("PLAYER_TARGET_CHANGED")
    eq(#__blocked, 0, "only the box frame was shown and hidden")
    W.clean(); noFails()
end

function T.a_box_that_failed_to_build_leaves_no_tags_and_never_throws()
    local W = world({ noLogin = true })
    FS.GunsightBoxes.Build = function() return nil, "boom" end
    __fireEvent("ADDON_LOADED", "forever-stuwave")
    __fireEvent("PLAYER_LOGIN")
    eq(FS.GunsightTags.level, nil, "no box, no tags"); eq(FS.GunsightTags.tot, nil); eq(#__secure, 0)
    ok(degraded("gunsighttags_nobox"), "logged once")
    target("Kurak")
    noFails()
end

function T.with_the_gunsight_off_nothing_is_built_logged_or_listened_for()
    local W = world({ db = { gunsight = { enabled = false } } })
    eq(W.Gun.IsEnabled(), false)
    eq(FS.GunsightTags.level, nil, "no level tag"); eq(FS.GunsightTags.health, nil); eq(FS.GunsightTags.tot, nil)
    eq(#__secure, 0, "no secure frame")
    eq(#__degrades, 0, "no log, so no chat line either")
    W.clean()
    eq(#__printed, 0)
    local listeners = 0
    for _, f in ipairs(__all) do
        if f._events and (f._events.UNIT_LEVEL or f._events.UNIT_CLASSIFICATION_CHANGED or f._unitEvents.UNIT_TARGET) and f._scripts.OnEvent then
            listeners = listeners + 1
        end
    end
    eq(listeners, 0, "no tags listener")
    noFails()
end

-- ---- the tags' outlines follow the box's kick state ------------------------------------------
-- The box edge is steel at rest and while the cast cannot be kicked, pink while it can, red for INTERRUPTED. The three
-- tags wear the same tone frames (GunsightBoxes.NewChrome), so the one flag write that tints the box tints them.

local function tagList() return { level = Tg().level, health = Tg().health, tot = Tg().tot } end
local function outlineOf(f) return textureWith(f, function(r) return r._cutOutline == true end) end
local function startCast(W, notInt)
    W.tgt.S.stripOnly = nil   -- the run path, the one a plain cast can be interrupted on (the boxes harness does the same)
    __units.target.name = "Kurak"; __fireEvent("PLAYER_TARGET_CHANGED")
    W.cast("target", "Fear", "T1", 100, 2, notInt)
    W.fire(W.tgt.S, "UNIT_SPELLCAST_START")
    W.stepTo(W.tgt.S, 100, 100.5)
end
-- Which outline a viewer sees: the tone frames shown whose alpha is up (a plain flag resolves in the mock).
local function lit(f)
    local out = {}
    for key, tone in pairs(f.tones) do
        if tone._shown and tone._alpha ~= 0 then out[#out + 1] = key end
    end
    table.sort(out)
    return table.concat(out, ",")
end

function T.at_rest_the_tag_outlines_are_steel()
    local W = world()
    local colors = FS.GunsightBoxes.colors
    for name, f in pairs(tagList()) do
        eq(outlineOf(f), nil, name .. ": no outline of its own, only the tone frames carry one")
        eq(lit(f), "steel", name .. ": steel at rest")
        for _, key in ipairs({ "pink", "steel", "red" }) do
            eq(f.tones[key]:GetParent(), f, name .. ": " .. key .. " tone is a child of the tag")
            eq(rgb(outlineOf(f.tones[key])._vc), rgb(colors[key]), name .. ": " .. key .. " outline colour")
        end
    end
    W.clean(); noFails()
end

function T.an_interruptible_cast_turns_every_tag_outline_pink()
    local W = world()
    startCast(W, false)
    for name, f in pairs(tagList()) do eq(lit(f), "pink", name .. ": kickable is pink") end
    W.clean(); noFails()
end

function T.a_cast_that_cannot_be_interrupted_keeps_every_tag_outline_steel()
    local W = world()
    startCast(W, true)
    for name, f in pairs(tagList()) do eq(lit(f), "steel", name .. ": not kickable is steel") end
    W.clean(); noFails()
end

function T.the_interrupted_verdict_turns_every_tag_outline_red_and_the_next_write_clears_it()
    local W = world()
    local box = W.tgt.box
    startCast(W, false)
    W.endCast("target"); W.fire(W.tgt.S, "UNIT_SPELLCAST_INTERRUPTED", "T1")
    eq(box.verdict, true, "the box shows the verdict")
    for name, f in pairs(tagList()) do eq(lit(f), "red", name .. ": red while INTERRUPTED") end
    startCast(W, false)
    for name, f in pairs(tagList()) do eq(lit(f), "pink", name .. ": the next kickable cast clears the verdict to pink") end
    W.endCast("target"); W.fire(W.tgt.S, "UNIT_SPELLCAST_STOP", "T1")
    W.stepTo(W.tgt.S, 100.5, 104)
    eq(lit({ tones = { pink = box.tones.pink, steel = box.tones.steel } }), "steel", "the box edge is at rest")
    for name, f in pairs(tagList()) do eq(lit(f), "steel", name .. ": back to rest after the cast ends") end
    W.clean(); noFails()
end

function T.a_secret_flag_reaches_the_tag_outlines_only_through_set_alpha_from_boolean()
    local W = world()
    -- Anything but the whitelisted setter that touches the flag must fail loudly.
    local mt = getmetatable(__SECRET_BOOL)
    for _, ev in ipairs({ "__lt", "__le", "__concat", "__unm", "__len", "__call" }) do
        mt[ev] = function() error("secret flag used in " .. ev, 2) end
    end
    __units.target.name = "Kurak"; __fireEvent("PLAYER_TARGET_CHANGED")
    W.tgt.S.stripOnly = nil
    W.secretCast("target")
    W.fire(W.tgt.S, "UNIT_SPELLCAST_START")
    for name, f in pairs(tagList()) do
        ok(rawequal(f.tones.steel._fromBool, __SECRET_BOOL), name .. ": steel got the flag untouched")
        eq(f.tones.steel._fromT, 1); eq(f.tones.steel._fromF, 0)
        ok(rawequal(f.tones.pink._fromBool, __SECRET_BOOL), name .. ": pink got the same flag")
        eq(f.tones.pink._fromT, 0); eq(f.tones.pink._fromF, 1)
    end
    W.at(W.tgt.S, __now + 0.3)
    for name, f in pairs(tagList()) do eq(f.tones.red._shown, false, name .. ": no red without a verdict") end
    W.endCast("target"); W.fire(W.tgt.S, "UNIT_SPELLCAST_STOP", __SECRET_ID)
    W.clean(); noFails("a secret operation was swallowed by a pcall")
end

local function onceIn(list, v)
    local n = 0
    for _, r in ipairs(list) do if r == v then n = n + 1 end end
    return n
end
local function assertEachToneOnce(W, msg)
    for name, f in pairs(tagList()) do
        for _, key in ipairs({ "pink", "steel" }) do
            eq(onceIn(W.tgt.box.fb[key], f.tones[key]), 1, name .. " " .. key .. " once in the box's list " .. msg)
            eq(onceIn(W.tgt.fb[key], f.tones[key]), 1, name .. " " .. key .. " once in the tape's list " .. msg)
            eq(onceIn(W.tgt.box.fb[key], f.tones.red) + onceIn(W.tgt.fb[key], f.tones.red), 0, name .. " red is not flag driven (" .. key .. " lists) " .. msg)
        end
    end
end

function T.a_rescale_and_the_master_switch_keep_the_same_tag_tone_frames()
    local W = world()
    local before = {}
    for name, f in pairs(tagList()) do before[name] = { f.tones.pink, f.tones.steel, f.tones.red } end
    local frames = #__all
    assertEachToneOnce(W, "after build")
    UIParent._h = 1080; UIParent._w = 1080 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED")
    assertEachToneOnce(W, "after a rescale")
    FS.Config.Set("gunsight.enabled", false); FS.Config.Set("gunsight.enabled", true)
    assertEachToneOnce(W, "after master off and on")
    UIParent._h = 1440; UIParent._w = 1440 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED")
    eq(#__all, frames, "nothing is built again")
    for name, f in pairs(tagList()) do
        eq(f.tones.pink, before[name][1]); eq(f.tones.steel, before[name][2]); eq(f.tones.red, before[name][3])
    end
    startCast(W, false)
    for name, f in pairs(tagList()) do eq(lit(f), "pink", name .. ": still driven after both") end
    W.clean(); noFails()
end

function T.the_target_of_target_outline_follows_the_flag_and_the_verdict_in_combat()
    local W = world()
    __combat = true
    startCast(W, false)
    eq(lit(Tg().tot), "pink", "pink in combat")
    W.endCast("target"); W.fire(W.tgt.S, "UNIT_SPELLCAST_INTERRUPTED", "T1")
    eq(lit(Tg().tot), "red", "red in combat: only plain child frames of the protected button are shown or hidden")
    eq(#__blocked, 0, "nothing protected was touched")
    W.clean(); noFails()
end

function T.a_retired_box_takes_no_new_tag_tone_frames_into_its_lists()
    local W = world({ noLogin = true })
    local seen
    local build = FS.GunsightBoxes.Build
    FS.GunsightBoxes.Build = function(spec)
        local box, err = build(spec)
        if box and spec.isTarget then seen = box end
        return box, err
    end
    __fireEvent("ADDON_LOADED", "forever-stuwave"); __fireEvent("PLAYER_LOGIN")
    ok(seen, "the target box was built")
    local pink, steel = #seen.fb.pink, #seen.fb.steel
    FS.GunsightBoxes.Retire(seen)
    local set = FS.GunsightBoxes.NewChrome(seen, seen.frame, function() end)
    eq(#seen.fb.pink, pink, "a retired box's pink list does not grow"); eq(#seen.fb.steel, steel)
    ok(set and set.pink, "the caller still gets frames to hold")
    noFails()
end

-- A target of target built at the end of combat (a load in combat) joins a cast that is already live: it adopts the
-- tape's last flag write, handed on to SetAlphaFromBoolean untouched, instead of the neutral steel seed.
local function lateTot(castFn)
    local W = world({ beforeLoad = function() __combat = true end })
    __units.target.name = "Kurak"; __fireEvent("PLAYER_TARGET_CHANGED")
    W.tgt.S.stripOnly = nil
    castFn(W)
    W.fire(W.tgt.S, "UNIT_SPELLCAST_START")
    eq(Tg().tot, nil, "not built yet")
    regen()
    ok(Tg().tot, "built when combat ends")
    return W
end

function T.a_target_of_target_built_after_combat_joins_a_live_kickable_cast_as_pink()
    local W = lateTot(function(W) W.cast("target", "Fear", "T1", 100, 2, false) end)
    eq(lit(Tg().tot), "pink", "pink, as the level tag built earlier")
    eq(lit(Tg().level), "pink")
    W.clean(); noFails()
end

function T.a_target_of_target_built_after_combat_joins_a_live_unkickable_cast_as_steel()
    local W = lateTot(function(W) W.cast("target", "Fear", "T1", 100, 2, true) end)
    eq(lit(Tg().tot), "steel")
    W.clean(); noFails()
end

function T.a_target_of_target_built_after_combat_takes_a_secret_flag_untouched()
    local W = lateTot(function(W) W.secretCast("target") end)
    local f = Tg().tot
    ok(rawequal(f.tones.steel._fromBool, __SECRET_BOOL), "steel got the live flag"); eq(f.tones.steel._fromT, 1); eq(f.tones.steel._fromF, 0)
    ok(rawequal(f.tones.pink._fromBool, __SECRET_BOOL), "pink got it too"); eq(f.tones.pink._fromT, 0); eq(f.tones.pink._fromF, 1)
    assertEachToneOnce(W, "with the late button")
    W.clean(); noFails("a secret operation was swallowed by a pcall")
end

function T.a_target_of_target_built_after_the_cast_ended_starts_at_rest()
    local W2 = world({ beforeLoad = function() __combat = true end })
    __units.target.name = "Kurak"; __fireEvent("PLAYER_TARGET_CHANGED")
    W2.tgt.S.stripOnly = nil
    W2.cast("target", "Fear", "T1", 100, 2, false); W2.fire(W2.tgt.S, "UNIT_SPELLCAST_START")
    W2.endCast("target"); W2.fire(W2.tgt.S, "UNIT_SPELLCAST_STOP", "T1"); W2.stepTo(W2.tgt.S, 100.5, 104)
    regen()
    eq(lit(Tg().tot), "steel", "the last write was the neutral one")
    W2.clean(); noFails()
end

__checks = T
"""



def static_checks() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        t, g, m = (toc.index(n) for n in ("Modules/CombatHud/GunsightTape.lua", "Modules/CombatHud/GunsightTags.lua",
                                          "Modules/CombatHud/GunsightMyBuffs.lua"))
        b = toc.index("Modules/CombatHud/GunsightBoxes.lua")
        out.append(("toc_order", None if b < t < g < m else
                    f"GunsightTags.lua loads after GunsightBoxes.lua and GunsightTape.lua (it reads their boxes): {b}, {t}, {g}"))
    except ValueError as e:
        out.append(("toc_order", f"{e}"))
    src = TAGS.read_text(encoding="utf-8") if TAGS.exists() else ""
    code = "\n".join(ln.split("--", 1)[0] for ln in src.splitlines())
    out.append(("tags_install_no_onupdate", None if "OnUpdate" not in code else "GunsightTags.lua must not run an OnUpdate"))
    out.append(("tags_use_no_secure_snippet", None if not re.search(r"SetAttribute\(\s*[\"']_on", code) and "WrapScript" not in code and
                "SecureHandler" not in code else "secure snippets do not run on this client; set attributes from plain Lua"))
    strings = re.findall(r'"([^"\n]*)"', code)
    out.append(("tags_player_text_never_says_tape", None if not any("tape" in s.lower() for s in strings) else
                "player text says cast bar, never tape"))
    out.append(("tags_never_see_the_interruptible_flag",
                None if not re.search(r"notInterruptible|SetAlphaFromBoolean|UnitCastingInfo|UnitChannelInfo|notInt", code) else
                "the interruptible flag may be secret; the tags take their tone from GunsightBoxes.NewChrome and never touch it"))
    out.append(("tags_have_no_em_dash", None if "—" not in src else "no em dashes"))
    out.append(("tags_never_branch_on_a_unit_value_directly",
                None if not re.search(r"\bif\s+(not\s+)?(name|level|class|classification)\s+(then|and|or)\b", code) else
                "a unit value must not be truth tested (it may be secret)"))
    return out


def texture_exists(path: str) -> bool:
    """A WoW texture path ("Interface\\AddOns\\forever-stuwave\\Media\\Textures\\x.tga") names a real file in the addon (case sensitive here)."""
    prefix = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
    if not isinstance(path, str) or not path.startswith(prefix):
        return False
    name = path[len(prefix):]
    return "\\" not in name and name in os.listdir(ADDON / "Media" / "Textures")


def run_case(name: str, mu: dict, mb: dict, mt: dict) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(CHEV.MOCK)
    lua.execute(CB.MOCK)
    theme_src = (ADDON / "Core/Theme.lua").read_text(encoding="utf-8")
    consts = [CHEV._extract_theme_constant(theme_src, n) for n in
              TH.THEME_CONSTANTS + ("COLOR_CARET_HEALTH", "COLOR_HEAL", "COLOR_GOLD", "COLOR_SILVER", "COLOR_RED", "FLAT_TEXTURE",
                                  "LEVEL_CROWN_TEXTURE", "LEVEL_STAR_TEXTURE", "LEVEL_CROWN_STAR_TEXTURE", "LEVEL_SKULL_TEXTURE")]
    lua.eval("__load_theme_constants")(lua.table_from(consts))
    lua.execute(CB.WIRE)
    lua.execute(TH.MOCK)
    lua.execute(TH.GS.theme_has_target_lua())
    lua.execute(BH.EXTRA_MOCK)
    lua.execute(TAGS_MOCK)
    lua.eval("__loadChevron")("Core/ChevronCastBar.lua", (ADDON / "Core/ChevronCastBar.lua").read_text(encoding="utf-8"))
    g = lua.globals()
    g.__fileExists = texture_exists
    g.__castSrc = TH.CASTBARS.read_text(encoding="utf-8")
    g.__layoutSrc = TH.LAYOUT.read_text(encoding="utf-8")
    g.__configSrc = TH.CONFIG.read_text(encoding="utf-8")
    g.__gunsightSrc = TH.GUNSIGHT.read_text(encoding="utf-8")
    g.__tapeSrc = TH.TAPE.read_text(encoding="utf-8")
    g.__boxSrc = BH.BOXES.read_text(encoding="utf-8")
    g.__fullNameSrc = full_name_source()
    g.__tagsSrc = TAGS.read_text(encoding="utf-8") if TAGS.exists() else "error('GunsightTags.lua is missing')"
    lua.execute("MU = " + TH.lua_value(mu))
    lua.execute("MB = " + TH.lua_value(mb))
    lua.execute("MT = " + TH.lua_value(mt))
    try:
        lua.execute(checks_source())
        lua.eval("__checks")[name]()
    except LuaError as e:
        return str(e)
    return None


def full_name_source() -> str:
    """The real FS.GetFullUnitName block of UnitFrames.lua (the shared resolver), cut out so the tags run against it."""
    text = (ADDON / "Modules/UnitFrames/UnitFrames.lua").read_text(encoding="utf-8")
    m = _m(r"(?s)local function GetFullUnitName\(unit\)\n.*?\nend\nFS\.GetFullUnitName = GetFullUnitName\n", text,
           "the GetFullUnitName resolver in UnitFrames.lua")
    return m.group(0)


def checks_source() -> str:
    prefix = TH.CHECKS.split("-- ---- constants", 1)[0]
    needle = '__load("Modules/CombatHud/GunsightTape.lua", __tapeSrc)'
    if needle not in prefix:
        sys.exit("gunsighttape-harness.py changed shape: its world() no longer loads GunsightTape.lua the way this harness patches")
    patched = prefix.replace(
        needle,
        '__load("Modules/CombatHud/GunsightBoxes.lua", __boxSrc)\n    ' + needle +
        '\n    __load("Modules/CombatHud/GunsightTags.lua", __tagsSrc)')
    return patched + CHECKS_BODY


def main() -> int:
    mu, mb, mt = TH.mockup_tape(), BH.mockup_boxes(), mockup_tags()
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
        err = run_case(name, mu, mb, mt)
        if err:
            failed += 1
            print(f"FAIL  {name}: {err}")
        else:
            print(f"ok    {name}")
    print(f"\n{total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
