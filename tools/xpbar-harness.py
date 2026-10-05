#!/usr/bin/env python3
"""Runs XPBar.lua headless against a mock WoW API and exercises every /fsxp
variant at several XP levels.

Why this exists: the parse gate proves a file compiles and lua-lint proves its
names resolve, but neither RUNS a line of it. The XP bar now carries thirteen
looks whose differences are geometry and colour maths -- width profiles, height
profiles, colour models, chase distances -- and the only other way to find a nil
index in one of them is to ship it to Parker and have his bar disappear.

So this stubs enough of the widget API to load the real file, fires
PLAYER_LOGIN, then switches through every variant at five XP levels, checking
after each that the cells still lie inside the bar and that every colour is in
range.

The combat checks pin the restricted bar: no size, anchor or show/hide in
combat, a variant chosen in combat is saved and listed at once but rendered
only once applied, a saved variant is restored at login, and the /fsxp text
names the choice.

It is NOT a rendering test. It cannot tell you whether a look is nice. It tells
you the look does not error, does not lay out off-screen, and does not emit a
colour the engine would clamp.

    tools/.venv-lua/Scripts/python.exe addons/xpbar-harness.py

Exit 0 = every variant laid out cleanly at every XP level.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ADDON = Path(__file__).resolve().parent.parent / "addon" / "ForeverSynthwave"
XPBAR = Path(os.environ.get("XPBAR_LUA", ADDON / "XPBar.lua"))   # XPBAR_LUA: a mutated scratch copy
SCREEN_W = 2560.0

# A mock only has to be as deep as the code under test actually reaches. Every
# method here is one XPBar.lua calls; anything it does not call is absent on
# purpose, so an untested call path fails loudly rather than passing silently.
MOCK = r"""
local SCREEN_W = ...
__frames = {}
-- COMBAT: a frame flagged `restricted` (the control deck's secure bag buttons depend on the bar through the anchors)
-- refuses size, anchor and show/hide in combat. Each refusal is logged in __blocked and does nothing, like the client's
-- ADDON_ACTION_BLOCKED.
__combat, __blocked, __ops, __sizeOps, __printed = false, {}, 0, 0, {}
local function refused(self, what)
    if __combat and self.restricted then
        __blocked[#__blocked + 1] = tostring(self.name) .. ":" .. what
        return true
    end
    return false
end

local Anim = {}
Anim.__index = Anim
function Anim:SetFromAlpha() end
function Anim:SetToAlpha() end
function Anim:SetDuration(d) self.duration = d end
function Anim:SetOrder() end
function Anim:SetOffset(x) self.offset = x end
function Anim:SetStartDelay(d) self.delay = d end
function Anim:SetScript(k, fn) self.scripts = self.scripts or {}; self.scripts[k] = fn end

local Group = {}
Group.__index = Group
function Group:CreateAnimation()
    local a = setmetatable({}, Anim)
    self.anims[#self.anims + 1] = a
    return a
end
function Group:SetLooping(m) self.looping = m end
function Group:Play() self.playing = true end
function Group:Stop() self.playing = false end

local Region = {}
Region.__index = Region
local function newRegion(kind, parent)
    return setmetatable({ kind = kind, parent = parent, shown = true,
                          w = 0, h = 0, alpha = 1, anchorX = 0 }, Region)
end
function Region:SetSize(w, h)
    if self.restricted then __sizeOps = __sizeOps + 1 end   -- counts relayouts of the restricted bar, refused or not
    if refused(self, "SetSize") then return end
    self.w, self.h = w, h
end
function Region:SetWidth(w) if refused(self, "SetWidth") then return end self.w = w end
function Region:SetHeight(h) if refused(self, "SetHeight") then return end self.h = h end
function Region:GetWidth() return self.w end
function Region:GetHeight() return self.h end
function Region:SetPoint(p, rel, relp, x, y) if refused(self, "SetPoint") then return end self.anchorX = x or 0 end
function Region:ClearAllPoints() if refused(self, "ClearAllPoints") then return end end
function Region:SetAllPoints(other) self.anchorX = 0 self.w = (other and other.w) or self.w end
function Region:Show() if self.restricted then __ops = __ops + 1 end; if refused(self, "Show") then return end self.shown = true end
function Region:Hide() if self.restricted then __ops = __ops + 1 end; if refused(self, "Hide") then return end self.shown = false end
function Region:SetShown(v) if refused(self, "SetShown") then return end self.shown = v and true or false end
function Region:IsShown() return self.shown end
function Region:SetAlpha(a) self.alpha = a end
function Region:GetAlpha() return self.alpha end
function Region:SetTexture(t) self.texture = t end
function Region:SetColorTexture(r, g, b, a) self.color = { r, g, b, a } end
function Region:SetVertexColor(r, g, b, a) self.color = { r, g, b, a or 1 } end
function Region:SetGradient(o, c1, c2)
    -- Record the gradient ENDPOINTS as the colour: those are what the engine
    -- would clamp, and a variant that forgets `flat` still gets range-checked.
    self.color = { c1.r, c1.g, c1.b, c1.a or 1 }
    self.color2 = { c2.r, c2.g, c2.b, c2.a or 1 }
end
function Region:SetBlendMode(m) self.blend = m end
function Region:SetTexCoord() end
function Region:CreateAnimationGroup() return setmetatable({ anims = {} }, Group) end
function Region:SetParent(p) self.parent = p end
function Region:GetParent() return self.parent end

local Frame = setmetatable({}, { __index = Region })
Frame.__index = Frame
function Frame:CreateTexture()
    local t = newRegion("texture", self)
    self.regions[#self.regions + 1] = t
    return t
end
function Frame:CreateFontString() return newRegion("fontstring", self) end
function Frame:SetScript(which, fn) self.scripts[which] = fn end
function Frame:HookScript() end
function Frame:RegisterEvent(e) self.events = self.events or {}; self.events[e] = true end
function Frame:UnregisterAllEvents() end
function Frame:EnableMouse() end
function Frame:SetFrameStrata() end
function Frame:SetFrameLevel() end
function Frame:SetPropagateMouseClicks() end
function Frame:GetChildren() return nil end

function CreateFrame(kind, name, parent)
    local f = setmetatable(newRegion("frame", parent), Frame)
    f.regions, f.scripts = {}, {}
    f.w, f.h = SCREEN_W, 40
    f.name = name
    __frames[#__frames + 1] = f
    if name then _G[name] = f end
    return f
end

UIParent = CreateFrame("Frame", "UIParent")
UIParent.w, UIParent.h = SCREEN_W, 1440

function GetScreenWidth() return SCREEN_W end
function GetScreenHeight() return 1440 end
function InCombatLockdown() return __combat end
function IsXPUserDisabled() return false end
function GetMaxPlayerLevel() return 60 end
function UnitLevel() return __level or 42 end
function GetXPExhaustion() return __rested end
function UnitXP() return __xp end
function UnitXPMax() return __xpmax end
function CreateColor(r, g, b, a) return { r = r, g = g, b = b, a = a } end
function wipe(t) for k in pairs(t) do t[k] = nil end return t end
function hooksecurefunc() end
function GetTime() return 0 end
SlashCmdList = {}
print = function(...)
    local t = {}
    for i = 1, select("#", ...) do t[i] = tostring((select(i, ...))) end
    __printed[#__printed + 1] = table.concat(t, " ")
end

for _, n in ipairs({ "StatusTrackingBarManager", "MainStatusTrackingBarContainer",
                     "SecondaryStatusTrackingBarContainer" }) do
    CreateFrame("Frame", n)
end
"""

THEME = r"""
return {
    Theme = {
        FLAT_TEXTURE = "Interface\\Buttons\\WHITE8x8",
        COLOR_POWER = { 0.133, 0.878, 1 },
    },
    Layout = { Scale = function() return 1 end, OnRescale = function(fn) __rescale = fn end },
}
"""

# Checks run after every switch. Each returns a problem string or nil.
CHECKS = r"""
function(screenW)
    local bar = _G.ForeverSynthwaveXPBar
    if not bar then return "no bar frame was built" end
    if not bar.regions or #bar.regions == 0 then return "bar has no regions" end

    local worst, shown = nil, 0
    for _, r in ipairs(bar.regions) do
        if r.shown then
            shown = shown + 1
            -- Cells are anchored LEFT with an x offset, so anchorX + w is the
            -- right edge. A couple of px of slack for the head bloom, which is
            -- deliberately allowed to spill.
            if r.w and r.anchorX and (r.anchorX + r.w) > screenW + 40 then
                worst = string.format("a region runs to %.0f on a %.0f screen",
                                      r.anchorX + r.w, screenW)
            end
            if r.w and r.w < 0 then worst = "a region has negative width" end
            if r.h and r.h < 0 then worst = "a region has negative height" end
            for _, key in ipairs({ "color", "color2" }) do
                local c = r[key]
                if c then
                    for i = 1, 4 do
                        local v = c[i]
                        if v and (v < -0.001 or v > 1.001) then
                            worst = string.format("colour channel %d out of range: %.3f", i, v)
                        end
                    end
                end
            end
        end
    end
    if shown == 0 then return "nothing is shown" end
    return worst
end
"""


# Lua snippets kept as whole blocks. Assembling them from adjacent Python string
# literals silently glues the last token of one line to the first of the next
# ("return nil" + "end" -> "nilend"), which is a Lua syntax error a long way from
# where it looks like it came from.
LOAD_ADDON = """
function(src, name, fs)
    local chunk, e = loadstring(src, name)
    if not chunk then return tostring(e) end
    local ok, e2 = pcall(chunk, name, fs)
    if not ok then return tostring(e2) end
    return nil
end
"""

LOGIN = """
function(xp, xpmax, rested)
    __xp, __xpmax, __rested = xp, xpmax, rested
    local target
    for _, f in ipairs(__frames) do
        if f.scripts and f.scripts.OnEvent then target = f end
    end
    if not target then return 'no frame registered an OnEvent handler' end
    local ok, e = pcall(target.scripts.OnEvent, target, 'PLAYER_LOGIN')
    if not ok then return tostring(e) end
    return nil
end
"""

SWITCH = """
function(i, xp, xpmax, rested)
    __xp, __xpmax, __rested = xp, xpmax, rested
    local fn = SlashCmdList['FSXP']
    if not fn then return 'no /fsxp handler registered' end
    local ok, e = pcall(fn, tostring(i))
    if not ok then return tostring(e) end
    return nil
end
"""


COMBAT_FAILS: list[str] = []
COMBAT_CHECKS = 0


def combat_check(name: str, ok: bool, detail: str = "") -> None:
    global COMBAT_CHECKS
    COMBAT_CHECKS += 1
    if not ok:
        COMBAT_FAILS.append(f"{name}: {detail}" if detail else name)
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))


# Dispatches an event the way the client does: only to a frame that REGISTERED it. Calling the OnEvent script directly
# would let a deleted RegisterEvent entry pass unnoticed. Returns an error string, or nil when the handler ran clean.
FIRE = """
function(event)
    local target
    for _, f in ipairs(__frames) do if f.scripts and f.scripts.OnEvent then target = f end end
    if not target then return "no frame registered an OnEvent handler" end
    if not (target.events and target.events[event]) then return "event not registered: " .. event end
    local ok, e = pcall(target.scripts.OnEvent, target, event)
    if not ok then return tostring(e) end
end
"""

# Every cell's colour, in order, as one string: two renders of the same variant at the same XP must match exactly.
CELL_COLOURS = """
function()
    local out = {}
    for i, c in ipairs(_G.ForeverSynthwaveXPBar.cells) do
        local a, b = c.color or {}, c.color2 or {}
        out[#out + 1] = string.format("%d:%.4f,%.4f,%.4f,%.4f/%.4f,%.4f,%.4f,%.4f", i,
            a[1] or -1, a[2] or -1, a[3] or -1, a[4] or -1, b[1] or -1, b[2] or -1, b[3] or -1, b[4] or -1)
    end
    return table.concat(out, ";")
end
"""

# The right edge of the furthest shown cell, and whether every cell has its specular extra (variant 3).
RIGHT_EDGE = """
function()
    local right = 0
    for _, c in ipairs(_G.ForeverSynthwaveXPBar.cells) do
        if c.shown and c.anchorX + c.w > right then right = c.anchorX + c.w end
    end
    return right
end
"""
ALL_HAVE_SPECULAR = """
function()
    for _, c in ipairs(_G.ForeverSynthwaveXPBar.cells) do if not c.spec then return false end end
    return true
end
"""
ANY_HAS_SPECULAR = """
function()
    for _, c in ipairs(_G.ForeverSynthwaveXPBar.cells) do if c.spec then return true end end
    return false
end
"""


def printed_lines(g) -> list[str]:
    return [str(x) for x in g.__printed.values()]


def combat_session(in_combat: bool = False, saved_variant: int | None = None):
    """A fresh runtime with the addon logged in (in combat if asked, with a saved /fsxp choice if given) and the bar
    flagged restricted, as the deck's secure bag buttons make it. Returns (rt, fs, g, bar, fire), or None when the addon
    fails to load."""
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.eval("function(src, w) assert(loadstring(src))(w) end")(MOCK, SCREEN_W)
    fs = rt.eval("function(src) return assert(loadstring(src))() end")(THEME)
    err = rt.eval(LOAD_ADDON)(XPBAR.read_text(encoding="utf-8"), "@XPBar.lua", fs)
    if err:
        combat_check("combat.XPBar_loads", False, str(err))
        return None
    if in_combat:
        rt.execute("__combat = true")
    if saved_variant is not None:
        rt.execute(f"ForeverSynthwaveDB = {{ xpVariant = {saved_variant} }}")
    err = rt.eval(LOGIN)(370, 1000, 0)
    combat_check("combat.login_runs_clean", not err, str(err))
    g = rt.globals()
    bar = g.ForeverSynthwaveXPBar
    bar.restricted = True            # the deck's chassis is anchored to it, and the chassis hosts secure buttons
    return rt, fs, g, bar, rt.eval(FIRE)


def combat_checks() -> None:
    """The bar is RESTRICTED in combat (the control deck's secure bag buttons depend on it through the anchors): no size,
    anchor, show or hide on it while in combat, and whatever arrived in combat lands at PLAYER_REGEN_ENABLED."""
    print("\ncombat: the restricted bar is never resized, re-anchored, shown or hidden in combat")
    session = combat_session()
    if session is None:
        return
    rt, fs, g, bar, fire = session
    v = fs["xpVariants"]
    start_w, start_h = bar.w, bar.h
    start_ops = g.__ops

    # 1. XP events in combat (every kill fires one): no Show/Hide at all while the state is unchanged, no block.
    g.__combat = True
    for xp in (400, 450, 500):
        g.__xp = xp
        combat_check("combat.xp_event_runs_clean", not fire("PLAYER_XP_UPDATE"))
    combat_check("combat.xp_events_do_not_touch_the_restricted_bar", len(g.__blocked) == 0, str(list(g.__blocked.values())))
    combat_check("combat.xp_events_call_no_show_or_hide_on_the_bar_when_the_state_is_unchanged", g.__ops == start_ops,
                 f"{g.__ops - start_ops} Show/Hide calls")

    # 2. A UI scale change and a live variant switch in combat: nothing moves, the choice is remembered.
    rt.execute("UIParent.w = 1920")
    rt.execute("__rescale()")
    combat_check("combat.rescale_does_not_resize_the_bar", bar.w == start_w and bar.h == start_h, f"{bar.w}x{bar.h}")
    err = rt.eval(SWITCH)(3, 500, 1000, 0)
    combat_check("combat.variant_switch_runs_clean", not err, str(err))
    combat_check("combat.variant_switch_does_not_resize_the_bar", bar.w == start_w and bar.h == start_h, f"{bar.w}x{bar.h}")
    combat_check("combat.variant_choice_is_saved_at_once", g.ForeverSynthwaveDB.xpVariant == 3)
    combat_check("combat.variant_extras_wait_for_regen", not rt.eval(ANY_HAS_SPECULAR)())
    combat_check("combat.nothing_blocked_by_rescale_or_variant_switch", len(g.__blocked) == 0, str(list(g.__blocked.values())))

    # 3. Reaching max level in combat: the bar is not hidden mid-fight.
    g.__level = 60
    combat_check("combat.level_up_to_max_runs_clean", not fire("PLAYER_LEVEL_UP"))
    combat_check("combat.the_bar_is_not_hidden_in_combat", bar.shown is True and len(g.__blocked) == 0,
                 f"shown={bar.shown} {list(g.__blocked.values())}")

    # 4. Regen: the rescale, the variant and the hide all land, from the state current then.
    g.__level = 42
    g.__combat = False
    combat_check("combat.regen_runs_clean", not fire("PLAYER_REGEN_ENABLED"))
    combat_check("combat.regen_resizes_to_the_new_width_and_the_chosen_variant_height",
                 bar.w == 1920 and bar.h == v[3]["barHeight"], f"{bar.w}x{bar.h}, want 1920x{v[3]['barHeight']}")
    combat_check("combat.regen_keeps_the_bar_shown_once_the_level_is_back_below_max", bar.shown is True)
    combat_check("combat.regen_blocks_nothing", len(g.__blocked) == 0, str(list(g.__blocked.values())))
    right = max(c.anchorX + c.w for _, c in bar.cells.items() if c.shown)
    combat_check("combat.regen_lays_the_cells_out_across_the_new_width", 1800 < right <= 1920, f"rightmost cell ends at {right}")
    combat_check("combat.regen_builds_the_variant_chosen_in_combat_extras", rt.eval(ALL_HAVE_SPECULAR)())

    # 5. A hide that arrived in combat lands at regen, and a replay with nothing pending does nothing.
    g.__combat = True
    g.__level = 60
    fire("PLAYER_LEVEL_UP")
    combat_check("combat.hide_is_held_back_in_combat", bar.shown is True and len(g.__blocked) == 0)
    g.__combat = False
    fire("PLAYER_REGEN_ENABLED")
    combat_check("combat.regen_applies_the_held_hide", bar.shown is False, f"shown={bar.shown}")
    ops, sizes = g.__ops, g.__sizeOps
    err = fire("PLAYER_REGEN_ENABLED")
    combat_check("combat.second_regen_runs_clean", not err, str(err))
    combat_check("combat.a_regen_with_nothing_pending_touches_nothing",
                 g.__ops == ops and g.__sizeOps == sizes and len(g.__blocked) == 0,
                 f"{g.__ops - ops} Show/Hide, {g.__sizeOps - sizes} SetSize")
    # Showing again out of combat still works (the state test is not stuck on the old value).
    g.__level = 42
    fire("PLAYER_LEVEL_UP")
    combat_check("combat.out_of_combat_show_still_works", bar.shown is True)
    ops = g.__ops
    fire("PLAYER_XP_UPDATE")
    combat_check("combat.out_of_combat_xp_event_does_not_re_show_a_shown_bar", g.__ops == ops, f"{g.__ops - ops} calls")


def login_in_combat_checks() -> None:
    """Logging in or reloading mid-fight: Build's first layout is of a brand-new frame nothing depends on yet, so it must
    NOT be deferred (a deferred one leaves 80 zero-width cells until the fight ends). Also the /fsxp message."""
    print("\ncombat: login in combat, and the /fsxp message")
    session = combat_session(in_combat=True)
    if session is None:
        return
    rt, fs, g, bar, fire = session
    right = rt.eval(RIGHT_EDGE)()
    combat_check("combat.login_in_combat_lays_the_cells_out_at_once", right > SCREEN_W * 0.9, f"rightmost cell ends at {right}")

    rt.execute("__printed = {}")
    err = rt.eval(SWITCH)(3, 370, 1000, 0)
    printed = " | ".join(str(x) for x in g.__printed.values())
    combat_check("combat.fsxp_in_combat_runs_clean", not err, str(err))
    combat_check("combat.fsxp_in_combat_says_it_applies_after_combat", "applies after combat" in printed, printed)
    chosen = fs["xpVariants"][3]["label"]
    combat_check("combat.fsxp_in_combat_announces_the_chosen_variant_not_the_applied_one", f"3 {chosen}" in printed, printed)

    # The list form in combat names the CHOSEN variant (3), not the one whose layout is still on the bar (1).
    rt.execute("__printed = {}")
    rt.eval(SWITCH)("", 370, 1000, 0)
    lines = printed_lines(g)
    now = [ln for ln in lines if ln.lstrip().startswith("now:")]
    combat_check("combat.fsxp_list_in_combat_now_line_is_the_chosen_variant",
                 len(now) == 1 and f"now: |cffff2e97{chosen}|r" in now[0], str(now))
    combat_check("combat.fsxp_list_in_combat_highlights_the_chosen_variant",
                 any(f"|cffff2e973 {chosen}|r" in ln for ln in lines) and not any(
                     f"|cffff2e971 {fs['xpVariants'][1]['label']}|r" in ln for ln in lines), " | ".join(lines))

    g.__combat = False
    fire("PLAYER_REGEN_ENABLED")
    rt.execute("__printed = {}")
    rt.eval(SWITCH)(2, 370, 1000, 0)
    printed = " | ".join(str(x) for x in g.__printed.values())
    combat_check("combat.fsxp_out_of_combat_does_not_say_it", fs["xpVariants"][2]["label"] in printed and "applies after combat" not in printed, printed)


def applied_variant_checks() -> None:
    """A variant chosen in combat is SAVED at once but only APPLIED at regen. Until then every XP event must keep
    rendering the variant whose layout is on screen, not the new one over the old geometry."""
    print("\ncombat: a variant chosen in combat renders only once its layout is applied")
    session = combat_session()
    if session is None:
        return
    rt, fs, g, bar, fire = session
    colours = rt.eval(CELL_COLOURS)
    g.__xp = 450
    fire("PLAYER_XP_UPDATE")
    before = colours()

    g.__combat = True
    err = rt.eval(SWITCH)(9, 450, 1000, 0)                  # 9 = capacitor bank: 28 cells, zone colours, flat
    combat_check("combat.applied_variant_switch_runs_clean", not err, str(err))
    err = fire("PLAYER_XP_UPDATE")
    combat_check("combat.applied_variant_xp_event_runs_clean", not err, str(err))
    combat_check("combat.xp_event_in_combat_keeps_rendering_the_applied_variant", colours() == before,
                 "cells were recoloured with the variant chosen in combat over the old layout")

    # A world entry in combat must not apply the pending switch either (zone change or death across a fight).
    err = fire("PLAYER_ENTERING_WORLD")
    combat_check("combat.entering_world_with_a_pending_switch_in_combat_runs_clean", not err, str(err))
    err = fire("PLAYER_XP_UPDATE")
    combat_check("combat.xp_event_after_entering_world_in_combat_runs_clean", not err, str(err))
    combat_check("combat.entering_world_in_combat_does_not_apply_the_pending_variant", colours() == before,
                 "cells were recoloured after PLAYER_ENTERING_WORLD in combat")

    g.__combat = False
    fire("PLAYER_REGEN_ENABLED")
    combat_check("combat.regen_renders_the_chosen_variant", colours() != before, "regen left the old variant's colours")
    after = colours()
    fire("PLAYER_XP_UPDATE")
    combat_check("combat.xp_event_after_regen_keeps_the_chosen_variant", colours() == after)


def saved_variant_login_checks() -> None:
    """A variant saved in ForeverSynthwaveDB is restored at PLAYER_LOGIN, before the first Build: the bar is laid out at
    that variant's height at once, and /fsxp lists it as the current one."""
    print("\nlogin: a saved variant is restored")
    session = combat_session(saved_variant=3)
    if session is None:
        return
    rt, fs, g, bar, fire = session
    v = fs["xpVariants"]
    combat_check("login.variant_3_height_differs_from_the_default", v[3]["barHeight"] != v[1]["barHeight"])
    combat_check("login.saved_variant_lays_the_bar_out_at_its_height", bar.h == v[3]["barHeight"],
                 f"height {bar.h}, want {v[3]['barHeight']}")
    rt.execute("__printed = {}")
    rt.eval(SWITCH)("", 370, 1000, 0)
    lines = printed_lines(g)
    now = [ln for ln in lines if ln.lstrip().startswith("now:")]
    combat_check("login.saved_variant_is_the_one_listed_as_now", len(now) == 1 and f"now: |cffff2e97{v[3]['label']}|r" in now[0],
                 str(now))


def out_of_combat_switch_checks() -> None:
    """An /fsxp switch out of combat builds the new variant's per-cell extras at once (the bar was built as variant 1,
    which has none)."""
    print("\nswitch: out of combat")
    session = combat_session()
    if session is None:
        return
    rt, fs, g, bar, fire = session
    combat_check("switch.default_variant_has_no_specular_extras", not rt.eval(ANY_HAS_SPECULAR)())
    err = rt.eval(SWITCH)(3, 370, 1000, 0)
    combat_check("switch.variant_switch_runs_clean", not err, str(err))
    combat_check("switch.out_of_combat_switch_builds_every_cells_specular_extra", rt.eval(ALL_HAVE_SPECULAR)())


def entering_world_checks() -> None:
    """A missed PLAYER_REGEN_ENABLED must not strand a pending replay: the next PLAYER_ENTERING_WORLD out of combat
    applies it, and one in combat touches nothing."""
    print("\ncombat: PLAYER_ENTERING_WORLD heals a missed regen")
    session = combat_session()
    if session is None:
        return
    rt, fs, g, bar, fire = session
    start_w = bar.w
    g.__combat = True
    rt.execute("UIParent.w = 1920")
    rt.execute("__rescale()")
    err = fire("PLAYER_ENTERING_WORLD")
    combat_check("combat.entering_world_in_combat_runs_clean", not err, str(err))
    combat_check("combat.entering_world_in_combat_does_not_resize", bar.w == start_w and len(g.__blocked) == 0,
                 f"{bar.w}, blocked {list(g.__blocked.values())}")
    g.__combat = False                                       # regen never arrives
    err = fire("PLAYER_ENTERING_WORLD")
    combat_check("combat.entering_world_out_of_combat_runs_clean", not err, str(err))
    combat_check("combat.entering_world_applies_the_pending_rescale", bar.w == 1920, f"width {bar.w}")
    sizes = g.__sizeOps
    fire("PLAYER_ENTERING_WORLD")
    combat_check("combat.entering_world_with_nothing_pending_does_not_relayout", g.__sizeOps == sizes,
                 f"{g.__sizeOps - sizes} SetSize")


def main() -> int:
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.eval("function(src, w) assert(loadstring(src))(w) end")(MOCK, SCREEN_W)
    fs = rt.eval("function(src) return assert(loadstring(src))() end")(THEME)

    src = XPBAR.read_text(encoding="utf-8")
    err = rt.eval(LOAD_ADDON)(src, "@XPBar.lua", fs)
    if err:
        print(f"FAIL: XPBar.lua raised at load: {err}")
        return 1
    print("loaded XPBar.lua against the mock")

    login = rt.eval(LOGIN)
    err = login(370, 1000, 120)
    if err:
        print(f"FAIL: PLAYER_LOGIN raised: {err}")
        return 1
    print("PLAYER_LOGIN ran clean")

    variants = fs["xpVariants"]
    count = len(variants)
    check = rt.eval(CHECKS)

    switch = rt.eval(SWITCH)

    levels = [(0, 1000), (10, 1000), (370, 1000), (990, 1000), (1000, 1000)]
    problems: list[str] = []

    print(f"\nexercising {count} variants x {len(levels)} XP levels\n")
    for i in range(1, count + 1):
        label = variants[i]["label"]
        bad = []
        for xp, xpmax in levels:
            err = switch(i, xp, xpmax, 0)
            if err:
                bad.append(f"{xp * 100 // xpmax}%: {err}")
                continue
            problem = check(SCREEN_W)
            if problem:
                bad.append(f"{xp * 100 // xpmax}%: {problem}")
        status = "ok" if not bad else "FAIL"
        print(f"  {i:2d}  {label:26s} {status}")
        for b in bad:
            print(f"        {b}")
        problems += [f"{label}: {b}" for b in bad]

    combat_checks()
    login_in_combat_checks()
    applied_variant_checks()
    entering_world_checks()
    saved_variant_login_checks()
    out_of_combat_switch_checks()
    print(f"\n{COMBAT_CHECKS} combat checks, {len(COMBAT_FAILS)} failed")

    if problems or COMBAT_FAILS:
        print(f"\n{len(problems) + len(COMBAT_FAILS)} problem(s)")
        return min(len(problems) + len(COMBAT_FAILS), 255)

    print("\nall variants laid out cleanly at every XP level")
    return 0


if __name__ == "__main__":
    sys.exit(main())
