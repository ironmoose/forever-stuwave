#!/usr/bin/env python3
"""Runs the real QuestTimer.lua headless against a mock client.

QuestTimer draws the quest timer as a drawer under the minimap's control strip and hides Blizzard's
QuestTimerFrame. These checks pin:

  * MM:SS digits and the cyan / amber / pink ramp at 60 and 15 seconds;
  * timers are read from GetQuestTimers into deadlines, named from the quest log, soonest first;
  * the drawer hangs from the minimap bezel, shows only while a timer runs, and Blizzard's timer is hidden;
  * every row's name and gauge stay inside the drawer (the name is one clipped line);
  * the switch off hides the drawer and gives Blizzard's timer back.

    python3 tools/questtimer-module-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

SRC = (Path(__file__).resolve().parent.parent / "forever-stuwave/Modules/Tracker/QuestTimer.lua").read_text(encoding="utf-8")

MOCK = r"""
local Obj = {}
Obj.__index = function(t, k)
    local v = rawget(Obj, k)
    if v ~= nil then return v end
    if type(k) == "string" and k:match("^%u") then return function() end end
end
function Obj:SetPoint(p, rel, rp, x, y) self.points = self.points or {}; self.points[#self.points + 1] = { p, rel, rp, x or 0, y or 0 } end
function Obj:ClearAllPoints() self.points = {} end
function Obj:SetSize(w, h) self.w, self.h = w, h end
function Obj:SetWidth(w) self.w = w end
function Obj:SetHeight(h) self.h = h end
function Obj:GetWidth() return self.w or 0 end
function Obj:Show() self.shown = true end
function Obj:Hide() self.shown = false; if self.scripts and self.scripts.OnHide then end end
function Obj:SetShown(v) self.shown = not not v end
function Obj:IsShown() return self.shown ~= false end
function Obj:GetEffectiveScale() return 1 end
function Obj:GetFrameLevel() return 5 end
function Obj:SetScript(n, fn) self.scripts = self.scripts or {}; self.scripts[n] = fn end
function Obj:HookScript(n, fn) self.hooks = self.hooks or {}; self.hooks[n] = fn end
function Obj:RegisterEvent(e) self.events = self.events or {}; self.events[e] = true end
function Obj:SetText(t) self.text = t end
function Obj:SetVertexColor(r, g, b, a) self.color = { r, g, b, a } end
function Obj:CreateTexture() return New("Texture") end
function Obj:CreateFontString() local f = New("FontString"); __fonts[#__fonts + 1] = f; return f end
function New(kind) return setmetatable({ kind = kind, shown = true }, Obj) end
__fonts = {}
__frames = {}
function CreateFrame(kind, name, parent)
    local f = New("Frame"); f.name = name; f.parent = parent
    __frames[#__frames + 1] = f
    if name then _G[name] = f end
    return f
end
Minimap = New("Frame")
Minimap.fsBezel = New("Frame"); Minimap.fsBezel.w = 250
QuestTimerFrame = New("Frame")
__now = 100
function GetTime() return __now end
__timers = {}
function GetQuestTimers() return unpack(__timers) end
__names = {}
function GetQuestIndexForTimer(i) return 10 + i end
C_QuestLog = { GetTitleForLogIndex = function(i) return __names[i - 10] end }
PixelUtil = { GetPixelToUIUnitFactor = function() return 1 end }
C_Timer = { NewTicker = function(_, fn) return { Cancel = function() end } end }
__cfg = {}
FS = {
    Config = {
        RegisterDefault = function(k, v) if __cfg[k] == nil then __cfg[k] = v end end,
        Get = function(k) return __cfg[k] end,
        OnChange = function(k, fn) __onchange = fn end,
    },
    Layout = { Scale = function() return 1 end },
    Theme = {
        COLOR_POWER = { 0, 1, 1 }, COLOR_AMBER = { 1, 0.7, 0.3 }, COLOR_HEALTH = { 1, 0.2, 0.6 },
        COLOR_BG = { 0, 0, 0, 1 }, COLOR_BAR_TRACK = { 0, 0, 0, 1 }, COLOR_BORDER = { 0.6, 0.3, 1, 1 },
        COLOR_TEXT_WHITE = { 1, 1, 1, 1 }, COLOR_MUTED = { 0.6, 0.6, 0.8, 1 },
        SLICE_CUT2_FILL_TEXTURE = "f", SLICE_CUT2_OUTLINE_TEXTURE = "o",
        AddCut2Texture = function(f) return New("Texture") end,
        AddPanelChrome = function(f) return New("Texture"), New("Texture"), New("Texture") end,
        ApplyMono = function() end,
    },
}
assert(loadstring(SRC, "@QuestTimer.lua"))("forever-stuwave", FS)
QT = FS.QuestTimer
function Fire(e) for _, f in ipairs(__frames) do if f.scripts and f.scripts.OnEvent and f.events and f.events[e] then f.scripts.OnEvent(f, e) end end end
function Drawer() return _G.ForeverSTUwaveQuestTimer end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("digits_and_colour_ramp", """
    local m, s = QT.Digits(595); assert(m == "09" and s == "55", m .. s)
    m, s = QT.Digits(0.2); assert(m == "00" and s == "01", "a part second rounds up")
    m, s = QT.Digits(-3); assert(m == "00" and s == "00")
    m, s = QT.Digits(9999); assert(m == "99" and s == "59", "clamped")
    assert(QT.Color(61) == FS.Theme.COLOR_POWER)
    assert(QT.Color(59) == FS.Theme.COLOR_AMBER)
    assert(QT.Color(14) == FS.Theme.COLOR_HEALTH)
""")

case("timers_are_read_named_and_sorted_soonest_first", """
    __timers = { 1100, 371 }
    __names = { "Escort: Kodo Roundup", "Grace of An'she and Mu'sha" }
    local list = QT.Read(100)
    assert(#list == 2)
    assert(list[1].name == "Grace of An'she and Mu'sha" and list[1].deadline == 471, list[1].name)
    assert(list[2].most == 1100)
    QT.Read(200)
    __timers = { 900, 271 }
    list = QT.Read(300)
    assert(list[2].most == 1100, "the gauge keeps the most seen")
""")

case("the_drawer_hangs_from_the_bezel_and_hides_blizzards_timer", """
    __timers = { 595 }; __names = { "Grace" }
    Fire("QUEST_LOG_UPDATE")
    local d = Drawer()
    assert(d and d.shown, "drawer not shown")
    assert(d.parent == Minimap.fsBezel)
    local p = d.points
    assert(p[1][1] == "TOPLEFT" and p[1][2] == Minimap.fsBezel and p[1][3] == "BOTTOMLEFT")
    assert(p[2][1] == "TOPRIGHT" and p[2][3] == "BOTTOMRIGHT")
    assert(QuestTimerFrame.shown == false, "Blizzard's timer still shows")
    QuestTimerFrame:Show(); QuestTimerFrame.hooks.OnShow(QuestTimerFrame)
    assert(QuestTimerFrame.shown == false, "Blizzard's timer came back on show")
    __timers = {}
    Fire("QUEST_LOG_UPDATE")
    assert(d.shown == false, "drawer stays with no timer")
""")

case("text_and_gauge_stay_inside_the_drawer", """
    __timers = { 595, 30 }; __names = { "A very long quest name that would never fit in the drawer", "B" }
    Fire("QUEST_LOG_UPDATE")
    local d = Drawer()
    local W = Minimap.fsBezel.w
    for _, fs in ipairs(__fonts) do
        if fs.points and fs.points[1] then
            local x = fs.points[1][4]
            assert(fs.w and fs.w > 0, "a font string has no width, so it would not clip")
            assert(x + fs.w <= W - 4 + 1e-6, "text runs past the drawer: " .. (x + fs.w) .. " > " .. (W - 4))
        end
    end
    assert(d.h >= 5 + 2 * 26 + 3, "two rows do not fit: " .. tostring(d.h))
""")

case("the_switch_off_hides_the_drawer_and_returns_blizzards_timer", """
    __timers = { 595 }; __names = { "Grace" }
    Fire("QUEST_LOG_UPDATE")
    __cfg["questTimer.shown"] = false
    __onchange()
    assert(Drawer().shown == false)
    assert(QuestTimerFrame.shown == true, "Blizzard's timer did not come back")
    QuestTimerFrame.hooks.OnShow(QuestTimerFrame)
    assert(QuestTimerFrame.shown == true, "the hook still hides it with the switch off")
""")


def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.globals().SRC = SRC
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
