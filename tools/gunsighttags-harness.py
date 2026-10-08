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
  * level text: L62 with ELITE / RARE / BOSS in gold, nothing for a normal mob, ?? for level -1, a secret level
    only through SetFormattedText, a secret classification leaves the word out;
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
local function gold() return "|cff" .. rgb(FS.GunsightBoxes.colors.gold) end
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
    eq(C.LEVEL.dx, MT.LEVEL.x - MT.BOXR.x, "level tag x from the box"); eq(C.LEVEL.w, MT.LEVEL.w)
    eq(C.HEALTH.dx, MT.HEALTH.x - MT.BOXR.x); eq(C.HEALTH.w, MT.HEALTH.w)
    eq(C.TOT.dx, MT.TOT.x - MT.BOXR.x); eq(C.TOT.w, MT.TOT.w)
    eq(C.RISE, MT.BOXR.y - MT.TB_GROW - MT.LEVEL.y, "the level tag stands this far above the grown box top")
    eq(C.OVERLAP, MT.BOXR.y + MT.BOXR.h - MT.HEALTH.y, "the bottom tags reach this far above the box bottom")
    eq(MT.HEALTH.y, MT.TOT.y, "both bottom tags share a row")
    ok(MT.LEVEL.x + MT.LEVEL.w <= MT.BOXR.x + MT.BOXR.w - FS.GunsightTape.C.KICK_DX, "the level tag ends before KICK")
    eq(rgb(FS.GunsightBoxes.colors.gold), "ffd23f")
    W.clean(); noFails()
end

function T.the_tags_are_kick_style_plates_with_a_pink_outline()
    local W = world()
    local C = Tg().C
    local pink = rgb(FS.GunsightBoxes.colors.pink)
    for _, frame in ipairs({ Tg().level, Tg().health, Tg().tot }) do
        local fill = textureWith(frame, function(r) return r._cutOutline == nil and r._texture ~= nil and r._vc[4] == C.FILL_A end)
        ok(fill, "a 0.95 fill")
        eq(rgb(fill._vc), "0d0620", "in the plate colour")
        local outline = textureWith(frame, function(r) return r._cutOutline == true end)
        ok(outline, "an outline"); eq(rgb(outline._vc), pink, "in pink")
        eq(frame.label._fontSize, math.max(6, math.floor(C.TEXT_SIZE * K() + 0.5)), "the KICK text size")
    end
    W.clean(); noFails()
end

function T.the_tags_sit_at_the_mockup_seats_at_two_heights()
    local W = world()
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
        near(Tg().level._w, MT.LEVEL.w * k, 1e-6); near(Tg().level._h, MT.H * k, 1e-6)
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

function T.the_level_tag_reads_level_and_classification()
    local W = world()
    target("Kurak")
    local function check(level, class, want, msg)
        setUnit(level, class)
        eq(levelText(), want, msg)
    end
    check(62, "normal", "L62", "a normal mob: no word")
    check(62, "elite", "L62 " .. gold() .. "ELITE|r", "elite")
    check(62, "rare", "L62 " .. gold() .. "RARE|r", "rare")
    check(62, "rareelite", "L62 " .. gold() .. "RARE|r", "a rare elite reads as the rarer")
    check(-1, "worldboss", "?? " .. gold() .. "BOSS|r", "a boss of unknown level")
    check(63, "worldboss", "L63 " .. gold() .. "BOSS|r", "a boss with a level")
    check(-1, "normal", "??", "level -1 shows ??")
    check(5, "trivial", "L5", "trivial: no word")
    check(5, "minus", "L5", "minus: no word")
    check(nil, nil, "", "no level, no text")
    eq(Tg().level.label._monoColor ~= nil and rgb(Tg().level.label._monoColor), rgb(FS.GunsightBoxes.colors.white), "the level is white")
    W.clean(); noFails()
end

function T.a_secret_level_goes_only_through_set_formatted_text_and_a_secret_class_loses_its_word()
    local W = world()
    target("Kurak")
    setUnit(__SECRET, "elite")
    local label = Tg().level.label
    eq(label._secretText, true, "the secret level reached SetFormattedText")
    ok(rawequal(label._args[1], __SECRET), "untouched")
    ok(label._fmt:find("ELITE", 1, true), "the plain word rides the format")
    ok(label._fmt:find("L%d", 1, true), "the level is a %d argument")
    setUnit(62, __SECRET_NAME)
    eq(levelText(), "L62", "a secret classification: the word is left out")
    setUnit(__SECRET, __SECRET_NAME)
    eq(label._secretText, true); ok(not label._fmt:find("ELITE", 1, true) and not label._fmt:find("BOSS", 1, true))
    W.clean(); noFails("a secret was compared, formatted or tested inside a pcall")
end

function T.the_level_tag_follows_the_target_and_level_events()
    local W = world()
    __units.target.level, __units.target.class = 61, "normal"
    target("Kurak")
    eq(levelText(), "L61", "read on a target change")
    __units.target.level = 62
    __fireUnit("UNIT_LEVEL", "target")
    eq(levelText(), "L62", "and on UNIT_LEVEL")
    __units.target.class = "elite"
    __fireUnit("UNIT_CLASSIFICATION_CHANGED", "target")
    eq(levelText(), "L62 " .. gold() .. "ELITE|r", "and on a classification change")
    __units.target.level = 70
    __fireUnit("UNIT_LEVEL", "player")
    eq(levelText(), "L62 " .. gold() .. "ELITE|r", "another unit's level is ignored")
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
    near(Tg().level._w, MT.LEVEL.w * k, 1e-6, "the plain tags resized at once")
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
    out.append(("tags_have_no_em_dash", None if "—" not in src else "no em dashes"))
    out.append(("tags_never_branch_on_a_unit_value_directly",
                None if not re.search(r"\bif\s+(not\s+)?(name|level|class|classification)\s+(then|and|or)\b", code) else
                "a unit value must not be truth tested (it may be secret)"))
    return out


def run_case(name: str, mu: dict, mb: dict, mt: dict) -> str | None:
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
    lua.execute(TAGS_MOCK)
    lua.eval("__loadChevron")("Core/ChevronCastBar.lua", (ADDON / "Core/ChevronCastBar.lua").read_text(encoding="utf-8"))
    g = lua.globals()
    g.__castSrc = TH.CASTBARS.read_text(encoding="utf-8")
    g.__layoutSrc = TH.LAYOUT.read_text(encoding="utf-8")
    g.__configSrc = TH.CONFIG.read_text(encoding="utf-8")
    g.__gunsightSrc = TH.GUNSIGHT.read_text(encoding="utf-8")
    g.__tapeSrc = TH.TAPE.read_text(encoding="utf-8")
    g.__boxSrc = BH.BOXES.read_text(encoding="utf-8")
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
