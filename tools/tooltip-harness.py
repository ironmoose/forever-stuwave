#!/usr/bin/env python3
"""Runs the real Layout.lua and TooltipAnchor.lua headless against a small mock WoW API.

TooltipAnchor.lua owns FSTooltipAnchor, an invisible mouse-disabled frame seated by the
`tooltip` Layout entry, and a post-hook on GameTooltip_SetDefaultAnchor that re-points the
tooltip to that frame's BOTTOMRIGHT. These checks pin that:

  * a tooltip placed by the default anchor ends on the anchor frame, and one placed by an
    explicit SetOwner anchor is never touched;
  * the seat defaults to where Blizzard's default container sits (BOTTOMRIGHT of UIParent,
    9 units from the right edge and 85 from the bottom) and follows a Layout override and
    a rescale;
  * the hook installs once and never replaces the Blizzard function;
  * a missing global (or a missing hooksecurefunc) degrades without an error;
  * a re-point that throws goes to the error handler instead of into Blizzard's caller;
  * nothing the hook touches is protected, in or out of combat.

Layout.lua and TooltipAnchor.lua are the real files; the frames are a recording mock with a
tiny anchor solver, and GameTooltip_SetDefaultAnchor is a stand-in that mirrors Blizzard's
SetOwner(ANCHOR_NONE) plus a corner SetPoint. This is NOT the real client.

    python3 tools/tooltip-harness.py

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
LAYOUT_FILE = ADDON / "Core/Layout.lua"
ANCHOR_FILE = Path(os.environ.get("TOOLTIPANCHOR_LUA", ADDON / "Modules/Skins/TooltipAnchor.lua"))   # a mutant copy for mutation checks

MOCK = r"""
__combat = false
__blocked = 0
__frames = {}
__errors = {}
__hooks = {}

local function noop() end
local function fx(p) if p:find("LEFT") then return 0 elseif p:find("RIGHT") then return 1 end return 0.5 end
local function fy(p) if p:find("BOTTOM") then return 0 elseif p:find("TOP") then return 1 end return 0.5 end

local Frame = {}
Frame.__index = function(_, k)
    local v = Frame[k]
    if v ~= nil then return v end
    -- Unknown methods are no-ops; data fields, Edit Mode's *Base originals and the tooltip-only
    -- GetAnchorType stay absent unless set.
    if type(k) == "string" and (k:sub(1, 1) == "_" or k:find("Base$") or k == "GetAnchorType") then return nil end
    return noop
end
local function guarded(self)
    if __combat and self._protected then __blocked = __blocked + 1; return true end
end
function Frame:ClearAllPoints()
    if guarded(self) then return end
    self._clears = (self._clears or 0) + 1
    self._points = {}
end
function Frame:SetPoint(point, rel, relPoint, x, y)
    if guarded(self) then return end
    self._points[#self._points + 1] = { point = point, rel = rel, relPoint = relPoint or point, x = x or 0, y = y or 0 }
end
function Frame:SetSize(w, h) if guarded(self) then return end; self._w, self._h = w, h end
function Frame:SetHeight(h) self._h = h end
function Frame:GetHeight() return self._h end
function Frame:GetWidth() return self._w end
function Frame:EnableMouse(v) self._mouse = v and true or false end
function Frame:RegisterEvent(e) self._events[e] = true end
function Frame:UnregisterEvent(e) self._events[e] = nil end
function Frame:SetScript(k, fn) self._scripts[k] = fn end
function Frame:IsProtected() return self._protected or false end
function Frame:CreateTexture() self._textures = (self._textures or 0) + 1; return setmetatable({}, { __index = function() return noop end }) end
function Frame:_rect()
    if self == UIParent then return 0, 0, self._w, self._h end
    local p = self._points[1]
    if not (p and self._w and self._h) then return end
    local rel = p.rel or UIParent
    local rl, rb, rw, rh = rel:_rect()
    if not rl then return end
    local px = rl + rw * fx(p.relPoint) + p.x
    local py = rb + rh * fy(p.relPoint) + p.y
    return px - self._w * fx(p.point), py - self._h * fy(p.point), self._w, self._h
end
function Frame:GetLeft() local l = self:_rect(); return l end
function Frame:GetBottom() local _, b = self:_rect(); return b end
function Frame:GetRight() local l, _, w = self:_rect(); return l and l + w end
function Frame:GetTop() local _, b, _, h = self:_rect(); return b and b + h end
function Frame:GetCenter() local l, b, w, h = self:_rect(); if l then return l + w / 2, b + h / 2 end end

function CreateFrame(kind, name, parent, template)
    local f = setmetatable({ _points = {}, _events = {}, _scripts = {}, _kind = kind, _name = name, _parent = parent, _template = template }, Frame)
    __frames[#__frames + 1] = f
    if name then _G[name] = f end
    return f
end
function InCombatLockdown() return __combat end
function __fire(event, ...)
    for _, f in ipairs(__frames) do
        if f._events[event] and f._scripts.OnEvent then f._scripts.OnEvent(f, event, ...) end
    end
end
function print() end
function geterrorhandler() return function(e) __errors[#__errors + 1] = tostring(e) end end

UIParent = CreateFrame()
UIParent._w, UIParent._h = 1200 * 16 / 9, 1200

function __newTooltip()
    local tt = CreateFrame("Frame")
    function tt:SetOwner(owner, anchorType) self._owner, self._anchorType = owner, anchorType end
    function tt:GetAnchorType() return self._anchorType end
    return tt
end

-- Blizzard's shape: SetOwner with ANCHOR_NONE, then one corner SetPoint on the default container.
__container = CreateFrame()
function __blizzardDefaultAnchor(tooltip, parent)
    tooltip:SetOwner(parent, "ANCHOR_NONE")
    tooltip:SetPoint("BOTTOMRIGHT", __container)
end
-- The "tooltip anchor: cursor" option: Blizzard leaves the tooltip on the cursor, no corner SetPoint.
function __cursorDefaultAnchor(tooltip, parent)
    tooltip:SetOwner(parent, "ANCHOR_CURSOR")
end
"""

SESSION = r"""
function(layoutSrc, anchorSrc, opts)
    opts = opts or {}
    __frames, __errors, __hooks, __blocked, __combat = { UIParent }, {}, {}, 0, opts.combat == true
    UIParent._w, UIParent._h = 1200 * 16 / 9, 1200
    FSTooltipAnchor = nil
    GameTooltip = __newTooltip()
    if opts.noAnchorType then GameTooltip.GetAnchorType = nil end
    GameTooltip_SetDefaultAnchor = (not opts.noDefaultAnchor) and (opts.cursor and __cursorDefaultAnchor or __blizzardDefaultAnchor) or nil
    __blizzardFn = GameTooltip_SetDefaultAnchor
    if opts.noHook then
        hooksecurefunc = nil
    else
        hooksecurefunc = function(name, fn)
            if type(name) ~= "string" then error("this harness only models the global form") end
            __hooks[name] = (__hooks[name] or 0) + 1
            local orig = _G[name]
            _G[name] = function(...) local r = { orig(...) }; fn(...); return unpack(r) end
        end
    end
    FS = {}
    assert(load(layoutSrc, "@Layout.lua"))("forever-stuwave", FS)
    assert(load(anchorSrc, "@TooltipAnchor.lua"))("forever-stuwave", FS)
end
"""

CHECKS = r"""
local T = {}
local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end
local function near(a, b, tol, msg)
    if a == nil or b == nil or math.abs(a - b) > (tol or 1e-6) then
        error((msg or "not near") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2)
    end
end
local function anchor() return FS.TooltipAnchor and FS.TooltipAnchor.frame end
local function boot(opts)
    __session(__layoutSrc, __anchorSrc, opts)
    __fire("PLAYER_LOGIN")
end

function T.the_anchor_is_an_invisible_mouse_disabled_frame_named_for_the_addon()
    boot()
    local a = anchor()
    eq(a ~= nil, true, "anchor frame exists")
    eq(a._name, "FSTooltipAnchor")
    eq(a._kind, "Frame")
    eq(a._mouse, false, "mouse disabled")
    eq(a._template, nil, "a plain frame: no secure template")
    eq(a._protected, nil, "not protected")
    eq(a._parent, UIParent)
    eq(a._textures, nil, "draws nothing")
end

function T.the_tooltip_seat_is_a_bottom_right_corner_entry_in_raw_ui_units()
    boot()
    local L = FS.Layout.tooltip
    eq(L.point, "BOTTOMRIGHT"); eq(L.relPoint, "BOTTOMRIGHT")
    eq(L.unscaled, true, "raw UI units, like Blizzard's own offsets")
    eq(L.x, -9); eq(L.y, 85)
    eq(anchor()._w, L.w, "sized by the seat, unscaled")
    eq(anchor()._h, L.h)
    local p = anchor()._points[1]
    eq(p.point, "BOTTOMRIGHT"); eq(p.rel, UIParent); eq(p.relPoint, "BOTTOMRIGHT")
    eq(p.x, -9); eq(p.y, 85)
end

-- Blizzard's default container: BOTTOMRIGHT of UIParent, 9 units in and 85 up. Layout.lua measures
-- UIParent at 1200 tall once the login pass has run (768 is only the load-time transient).
function T.the_default_seat_hugs_the_corner_at_the_measured_ui_size_and_at_other_shapes()
    boot()
    near(anchor():GetRight(), UIParent._w - 9, 1e-6, "9 units in from the right edge at 1200 tall")
    near(anchor():GetBottom(), 85, 1e-6, "85 units up from the bottom edge")
    for _, shape in ipairs({ { 1200 * 32 / 9, 1200 }, { 1200 * 4 / 3, 1200 }, { 768 * 16 / 9, 768 } }) do
        UIParent._w, UIParent._h = shape[1], shape[2]
        __fire("UI_SCALE_CHANGED")
        near(anchor():GetRight(), UIParent._w - 9, 1e-6, "right gap at " .. shape[1] .. "x" .. shape[2])
        near(anchor():GetBottom(), 85, 1e-6, "bottom gap at " .. shape[1] .. "x" .. shape[2])
    end
end

-- The professions panel is a CENTER seat in design px; at the 16:9 reference the anchor box must clear it.
function T.the_default_box_does_not_overlap_the_professions_seat_at_the_reference_resolution()
    boot()
    local s = FS.Layout.Scale()
    local P = FS.Layout.professions
    local cx, cy = UIParent._w / 2 + P.x * s, UIParent._h / 2 + P.y * s
    local pLeft, pRight = cx - P.w * s / 2, cx + P.w * s / 2
    local pBottom, pTop = cy - P.h * s / 2, cy + P.h * s / 2
    local a = anchor()
    local apart = a:GetLeft() >= pRight or a:GetRight() <= pLeft or a:GetBottom() >= pTop or a:GetTop() <= pBottom
    eq(apart, true, "anchor " .. a:GetLeft() .. ".." .. a:GetRight() .. " x " .. a:GetBottom() .. ".." .. a:GetTop()
        .. " vs professions " .. pLeft .. ".." .. pRight .. " x " .. pBottom .. ".." .. pTop)
end

function T.a_default_anchored_tooltip_is_repointed_to_the_anchor_corner_in_or_out_of_combat()
    boot()
    GameTooltip_SetDefaultAnchor(GameTooltip, UIParent)
    eq(#GameTooltip._points, 1, "exactly one anchor: Blizzard's was cleared")
    local p = GameTooltip._points[1]
    eq(p.point, "BOTTOMRIGHT"); eq(p.rel, anchor()); eq(p.relPoint, "BOTTOMRIGHT")
    eq(p.x, 0); eq(p.y, 0)
    eq(GameTooltip._anchorType, "ANCHOR_NONE", "Blizzard's SetOwner is untouched")
    -- In combat, with a secure action button as the owner: the hook must not call anything on it.
    local secure = CreateFrame("Button", nil, UIParent, "SecureActionButtonTemplate")
    secure._protected = true
    __combat = true
    GameTooltip_SetDefaultAnchor(GameTooltip, secure)
    eq(GameTooltip._points[1].rel, anchor(), "re-pointed in combat")
    eq(#GameTooltip._points, 1)
    eq(__blocked, 0, "no protected operation was attempted")
    eq(secure._clears, nil, "the secure owner was not touched")
end

function T.the_hook_is_a_post_hook_that_keeps_blizzards_function_running()
    boot()
    local owner = {}
    GameTooltip_SetDefaultAnchor(GameTooltip, owner)
    eq(GameTooltip._owner, owner, "Blizzard's body still ran")
    eq(__hooks.GameTooltip_SetDefaultAnchor, 1)
end

function T.a_cursor_anchored_tooltip_is_not_moved()
    boot({ cursor = true })
    GameTooltip_SetDefaultAnchor(GameTooltip, UIParent)
    eq(GameTooltip._anchorType, "ANCHOR_CURSOR")
    eq(GameTooltip._clears, nil, "nothing cleared")
    eq(#GameTooltip._points, 0, "nothing anchored to the box")
end

function T.without_a_get_anchor_type_method_the_tooltip_is_still_repointed()
    boot({ noAnchorType = true })
    GameTooltip_SetDefaultAnchor(GameTooltip, UIParent)
    eq(GameTooltip._points[1].rel, anchor())
end

function T.an_explicitly_anchored_tooltip_is_left_alone()
    boot()
    local button = CreateFrame()
    GameTooltip:SetOwner(button, "ANCHOR_RIGHT")
    GameTooltip:SetPoint("LEFT", button, "RIGHT", 4, 0)
    eq(GameTooltip._clears, nil, "nothing cleared")
    eq(#GameTooltip._points, 1)
    eq(GameTooltip._points[1].rel, button, "still on the button")
end

function T.the_seat_moves_with_a_layout_override_and_the_tooltip_follows_the_anchor()
    boot()
    FS.Layout.UseStore({ v = 1, frames = {} })
    eq(FS.Layout.SetOverride("tooltip", -300, 400), true)
    FS.Layout.ReseatAll()
    local p = anchor()._points[1]
    eq(p.point, "BOTTOMRIGHT", "still corner anchored")
    near(p.x, -300, 1e-6, "anchor x"); near(p.y, 400, 1e-6, "anchor y")
    near(anchor():GetRight(), UIParent._w - 300, 1e-6, "the box moved")
    GameTooltip_SetDefaultAnchor(GameTooltip, UIParent)
    eq(GameTooltip._points[1].rel, anchor(), "still anchored to the one anchor frame")
    FS.Layout.ClearOverride("tooltip")
    FS.Layout.ReseatAll()
    near(anchor():GetRight(), UIParent._w - 9, 1e-6, "reset puts it back")
    near(anchor():GetBottom(), 85, 1e-6)
end

function T.the_hook_installs_once_however_often_install_runs()
    boot()
    FS.TooltipAnchor.Install()
    FS.TooltipAnchor.Install()
    eq(__hooks.GameTooltip_SetDefaultAnchor, 1)
    GameTooltip_SetDefaultAnchor(GameTooltip, UIParent)
    eq(GameTooltip._clears, 1, "re-pointed once per call, not once per hook")
end

function T.a_missing_default_anchor_global_degrades_cleanly()
    boot({ noDefaultAnchor = true })
    eq(GameTooltip_SetDefaultAnchor, nil)
    eq(__hooks.GameTooltip_SetDefaultAnchor, nil, "nothing hooked")
    eq(anchor() ~= nil, true, "the seat still exists")
    eq(#__errors, 0)
end

function T.a_missing_hooksecurefunc_degrades_cleanly()
    boot({ noHook = true })
    eq(GameTooltip_SetDefaultAnchor, __blizzardFn, "Blizzard's function was not replaced")
    eq(anchor() ~= nil, true, "the seat still exists")
    eq(#__errors, 0)
end

function T.a_repoint_that_throws_goes_to_the_error_handler_not_to_blizzards_caller()
    boot()
    function GameTooltip:ClearAllPoints() error("clear failed") end
    local ok = pcall(GameTooltip_SetDefaultAnchor, GameTooltip, UIParent)
    eq(ok, true, "the hook did not throw")
    eq(#__errors, 1)
    eq(__errors[1]:find("clear failed", 1, true) ~= nil, true)
end

function T.repointing_a_tooltip_without_setpoint_is_a_quiet_no_op()
    boot()
    local ok = pcall(FS.TooltipAnchor.Repoint, {})
    eq(ok, true, "no throw")
    eq(#__errors, 0, "nothing reported")
    ok = pcall(FS.TooltipAnchor.Repoint, nil)
    eq(ok, true, "nil is fine too")
end

function T.loading_in_combat_still_creates_and_seats_the_anchor()
    boot({ combat = true })
    eq(anchor() ~= nil, true)
    eq(#anchor()._points, 1)
end

__checks = T
"""


def boot() -> "LuaRuntime":
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.globals().__layoutSrc = LAYOUT_FILE.read_text(encoding="utf-8")
    lua.globals().__anchorSrc = ANCHOR_FILE.read_text(encoding="utf-8") if ANCHOR_FILE.exists() else "error('TooltipAnchor.lua missing')"
    lua.globals().__session = lua.eval(SESSION)
    lua.execute(CHECKS)
    return lua


def main() -> int:
    names = sorted(k for k in boot().eval("__checks").keys())
    failed = 0
    for name in names:
        # A fresh client per check: the combat flag, hooks and applied frames must not leak between them.
        try:
            boot().eval("__checks")[name]()
            print(f"ok    {name}")
        except LuaError as err:
            failed += 1
            print(f"FAIL  {name}: {err}")
    print(f"{len(names) - failed}/{len(names)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
