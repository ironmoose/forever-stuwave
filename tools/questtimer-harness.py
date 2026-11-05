#!/usr/bin/env python3
"""Runs the real Tracker.lua headless against a mock Blizzard_QuestTimer frame.

QuestTimerFrame (Blizzard_QuestTimer.xml) is a BackdropTemplate dialog on the BACKGROUND strata that
RightManagedFrameContainer lays out into the gap at the top of the objective tracker. Our tracker backdrop is on
the tracker's LOW strata, so the stock timer drew behind it, unskinned (playtest 2026-11-04). Pinned here:

  * the timer gets the STUwave panel chrome with a `timers` title, and Blizzard's own "Quest Timers" label is hidden;
  * every timer line (a font string on a child frame, found by shape) is set in the mono font, again on each show;
  * it is raised to the tracker's strata, above the tracker, and raised again each time the managed frame
    container re-lays it out (that reparents it) or it is shown;
  * it is never moved or given a field Blizzard's layout reads (no point, no ignoreFramePositionManager);
  * skinning twice builds the chrome once, and a timer that loads after the tracker is skinned when it loads.

The mock is NOT the real client. Run:

    python3 tools/questtimer-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ADDON = Path(__file__).resolve().parent.parent / "forever-stuwave"
TRACKER_SRC = (ADDON / "Modules/Tracker/Tracker.lua").read_text(encoding="utf-8")

MOCK = r"""
function Region(kind)
    local r = { kind = kind, shown = true, points = 0 }
    function r:GetObjectType() return self.kind end
    function r:Hide() self.shown = false end
    function r:Show() self.shown = true end
    return r
end

function Frame(strata, level)
    local f = { regions = {}, hooks = {}, strata = strata, level = level, setPoints = 0, shown = true }
    function f:GetRegions() return unpack(self.regions) end
    function f:CreateTexture() local t = Region("Texture"); table.insert(self.regions, t); return t end
    function f:CreateFontString() local t = Region("FontString"); table.insert(self.regions, t); return t end
    function f:GetFrameStrata() return self.strata end
    function f:SetFrameStrata(s) self.strata = s end
    function f:GetFrameLevel() return self.level end
    function f:SetFrameLevel(l) self.level = l end
    function f:SetPoint() self.setPoints = self.setPoints + 1 end
    function f:ClearAllPoints() self.setPoints = self.setPoints + 1 end
    function f:HookScript(script, fn) self.hooks[script] = self.hooks[script] or {}; table.insert(self.hooks[script], fn) end
    return f
end

__watchers = {}
__skinned = {}
__mono = {}
FS = {
    Theme = {
        COLOR_POWER = { 0.13, 0.88, 1 }, COLOR_BG = { 0, 0, 0 }, PANEL_RADIUS = 6,
        ApplyFontGeneric = function() end, AddOuterGlow = function() end, AddRoundedFill = function() end,
        AddGradientBorder = function() end, PanelBandInset = function() return 3 end,
        ApplyMono = function(fs, size) __mono[fs] = size end,
        SkinPanel = function(frame, opts)
            __skinned[#__skinned + 1] = { frame = frame, opts = opts }
            for _, r in ipairs({ frame:GetRegions() }) do if r.kind == "Texture" then r:Hide() end end
            frame.fsPanelTitle = frame:CreateFontString()
        end,
    },
    PanelSkins = {
        RegisterInspect = function() end,
        DeferCombat = function(fn) fn() end,
        WatchAddonLoad = function(cb, matches) __watchers[#__watchers + 1] = { cb = cb, matches = matches } end,
        HookShowOnce = function(frame, guard, fn)
            if frame[guard] then return end
            frame:HookScript("OnShow", fn); frame[guard] = true
        end,
    },
}
__hooks = {}
function hooksecurefunc(t, name, fn)
    if type(t) == "string" then t, name, fn = _G, t, name end
    __hooks[#__hooks + 1] = { t = t, name = name }
    local orig = t[name]
    t[name] = function(...) local a, b, c = orig(...); fn(...); return a, b, c end
end

-- the managed frame container: UpdateFrame reparents the frame, which on the client resets its level
RightManagedFrameContainer = { level = 3 }
function RightManagedFrameContainer:UpdateFrame(frame) frame.level = self.level + 1 end

function MakeTimer()
    local f = Frame("BACKGROUND", 2)
    table.insert(f.regions, Region("Texture"))       -- backdrop pieces
    table.insert(f.regions, Region("Texture"))       -- QuestTimerHeader
    f.blizzLabel = Region("FontString")              -- "Quest Timers"
    table.insert(f.regions, f.blizzLabel)
    -- the lines: font strings on child buttons, found by shape (the 16001 client has no QuestTimerNText names)
    f.children = {}
    function f:GetChildren() return unpack(self.children) end
    AddLine(f)
    QuestTimerFrame = f
    return f
end

function AddLine(timer)
    local button = Frame("BACKGROUND", 3)
    button.text = Region("FontString")
    table.insert(button.regions, button.text)
    table.insert(timer.children, button)
    return button.text
end

function LoadTracker()
    -- strata and level only: the backdrop build (Tracker.lua's own chrome) is not what this harness pins
    ObjectiveTrackerFrame = ObjectiveTrackerFrame or {
        strata = "LOW", level = 5,
        GetFrameStrata = function(self) return self.strata end,
        GetFrameLevel = function(self) return self.level end,
    }
    assert(loadstring(TRACKER_SRC, "@Tracker.lua"))("forever-stuwave", FS)
end

function FireWatchers(addon)
    for _, w in ipairs(__watchers) do
        if addon == nil or w.matches == nil or w.matches(addon) then w.cb() end
    end
end

function Above(timer)
    return timer.strata == ObjectiveTrackerFrame.strata and timer.level > ObjectiveTrackerFrame.level
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("the_timer_wears_the_panel_chrome_with_a_timers_title_and_loses_blizzards_label", """
    local timer = MakeTimer()
    LoadTracker()
    assert(#__skinned == 1 and __skinned[1].frame == timer, "the timer was not skinned")
    assert(__skinned[1].opts.title == "timers", "title: " .. tostring(__skinned[1].opts.title))
    assert(timer.blizzLabel.shown == false, "Blizzard's Quest Timers label still shows")
    assert(timer.fsPanelTitle.shown == true, "our own title was hidden")
    assert(__mono[timer.children[1].text], "the timer line is not mono")
    assert(not __mono[timer.blizzLabel], "the hidden stock label was restyled")
    local late = AddLine(timer)                      -- a second timer starts after the skin
    for _, fn in ipairs(timer.hooks.OnShow or {}) do fn(timer) end
    assert(__mono[late], "a line made after the skin is not mono after a show")
""")

case("the_timer_draws_above_the_tracker_and_is_never_moved", """
    local timer = MakeTimer()
    LoadTracker()
    assert(Above(timer), "timer at " .. timer.strata .. " " .. timer.level)
    assert(timer.setPoints == 0, "the timer was re-anchored")
    assert(timer.ignoreFramePositionManager == nil, "a field the managed frame layout reads was written")
""")

case("a_re_layout_or_a_show_raises_it_again", """
    local timer = MakeTimer()
    LoadTracker()
    RightManagedFrameContainer:UpdateFrame(timer)
    assert(Above(timer), "after a re-layout the timer sat at level " .. timer.level)
    timer.level = 1
    for _, fn in ipairs(timer.hooks.OnShow or {}) do fn(timer) end
    assert(Above(timer), "after a show the timer sat at level " .. timer.level)
    FireWatchers()
    FireWatchers("Blizzard_QuestTimer")
    assert(#__skinned == 1, "skinned " .. #__skinned .. " times")
    assert(#(timer.hooks.OnShow or {}) == 1, "OnShow hooked more than once")
""")

case("a_timer_that_loads_after_the_tracker_is_skinned_when_its_addon_loads", """
    QuestTimerFrame = nil
    LoadTracker()
    assert(#__skinned == 0)
    local timer = MakeTimer()
    FireWatchers("Blizzard_QuestTimer")
    assert(#__skinned == 1 and Above(timer), "the late timer was not skinned and raised")
""")


def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.globals().TRACKER_SRC = TRACKER_SRC
    try:
        rt.execute(MOCK)
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


def main() -> int:
    failures = 0
    for name, body in CASES:
        err = run_case(body)
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}: {err}")
    print(f"{len(CASES) - failures}/{len(CASES)} checks passed")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
