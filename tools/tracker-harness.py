#!/usr/bin/env python3
"""Runs the real Tracker.lua headless against a mock objective tracker.

Pins the one-header layout and the quest markers: the band reads the quest count over the first module's header row, that header's own text
and the modules' gold minus are hidden, and collapsed the panel is a compact bar whose whole width clicks the
tracker's own collapse button.
"""
import sys
from pathlib import Path

from lupa.luajit21 import LuaRuntime

ADDON = Path(__file__).resolve().parent.parent / "forever-stuwave"
SRC = (ADDON / "Modules/Tracker/Tracker.lua").read_text(encoding="utf-8")

LUA = r'''
local frames = {}
local Obj = {}
local function new(kind)
  local o = setmetatable({kind=kind, pts={}, alpha=1, shown=true, hooks={}}, {__index=function(t,k)
    if Obj[k] then return Obj[k] end
    if type(k) == "string" and (k:find("^fs") or k == "Background" or k == "Text" or k == "IsCollapsed"
      or k == "modules" or k == "topModulePadding" or k == "hit" or k == "w" or k == "h" or k == "text") then return nil end
    return function() end end})
  frames[#frames+1]=o
  return o
end
function Obj:SetPoint(...) self.pts[#self.pts+1]={...} end
function Obj:ClearAllPoints() self.pts={} end
function Obj:SetHeight(h) self.h=h end
function Obj:SetSize(w,h) self.w=w; self.h=h end
function Obj:GetWidth() return self.w or 14 end
function Obj:SetAlpha(a) self.alpha=a end
function Obj:Hide() self.shown=false end
function Obj:Show() self.shown=true end
function Obj:SetShown(v) self.shown=v and true or false end
function Obj:SetText(t) self.text=t end
function Obj:SetVertexColor(r,g,b,a) self.vc={r,g,b,a} end
function Obj:SetColorTexture(r,g,b,a) self.ct={r,g,b,a} end
function Obj:SetTextColor(r,g,b,a) self.tc={r,g,b,a} end
function Obj:HookScript(k, fn) self.hooks[k] = fn end
function Obj:GetText() return self.text end
function Obj:GetStringWidth() return #(self.text or "") * 6 end
function Obj:SetHitRectInsets(l,r,t,b) self.hit={l,r,t,b} end
function Obj:GetHitRectInsets() if self.hit then return unpack(self.hit) end return -3,-3,-2,-3 end
function Obj:CreateTexture() return new("Texture") end
function Obj:CreateFontString() return new("FontString") end
function Obj:GetFrameStrata() return "LOW" end
function Obj:GetFrameLevel() return 1 end
function Obj:SetScript(k,f) self[k]=f end
function Obj:GetFont() return "x", 12, "" end
CreateFrame = function(kind) return new(kind) end
hooksecurefunc = function(t, k, fn) local old=t[k]; t[k]=function(...) local r={old(...)}; fn(...); return unpack(r) end end
local collapsed = false
local tracker = new("Frame")
ObjectiveTrackerFrame = tracker
tracker.NineSlice = new("Frame")
tracker.Header = new("Frame")
tracker.Header.Text = new("FontString")
tracker.Header.MinimizeButton = new("Button")
tracker.Header.SetCollapsed = function(self, c) end
tracker.IsCollapsed = function() return collapsed end
tracker.Update = function() end
tracker.topModulePadding = 38
local function module(title, height)
  local m = new("Frame"); m.Header = new("Frame"); m.Header.Text = new("FontString"); m.Header.Text.text = title
  m.Header.MinimizeButton = new("Button"); m.height = height
  m.GetContentsHeight = function(self) return self.height end
  return m
end
QuestObjectiveTracker = module("Quests", 120)
AchievementObjectiveTracker = module("Achievements", 0)
tracker.modules = { AchievementObjectiveTracker, QuestObjectiveTracker }
C_QuestLog = { GetNumQuestLogEntries = function() return 3, 2 end, GetMaxNumQuestsCanAccept = function() return 40 end }
InCombatLockdown = function() return false end
POIButtonUtil = { Style = { QuestInProgress = 2, QuestComplete = 3, QuestDisabled = 4 } }
local function poi(style)
  local b = new("Button"); b.Display = new("Frame"); b.style = style; b.selected = false
  b.GetStyle = function(self) return self.style end
  b.IsSelected = function(self) return self.selected end
  b.SetSelected = function(self, v) self.selected = v end
  b.UpdateButtonStyle = function() end
  return b
end
local done, todo = poi(3), poi(2)
QuestObjectiveTracker.usedBlocks = { Block = { [1] = { poiButton = done }, [2] = { poiButton = todo } } }
QuestObjectiveTracker.EndLayout = function() end
local FS = { Theme = setmetatable({PANEL_HEADER_H=18, COLOR_AMBER={1,0.7,0.3,1}, COLOR_HEALTH={1,0.2,0.6,1},
  COLOR_BUTTON_INK={0.1,0.05,0.2,1}, SLICE_CUT2_GLOW_PAD=4,
  AddCut2Texture=function(f) local t = new("Texture"); t.owner = f; return t end, COLOR_BG={0,0,0,1}, COLOR_POWER={0,1,1,1},
  PanelBandInset=function() return 3 end}, {__index=function() return function() end end}),
  PanelSkins = setmetatable({DeferCombat=function(fn) fn() end}, {__index=function() return function() end end}),
  ButtonSkins = setmetatable({}, {__index=function() return function() end end}) }
assert(loadstring(SRC))("forever-stuwave", FS)

local label, backdrop
for _, o in ipairs(frames) do if o.kind == "FontString" and o.text and o.text:find("^quests") then label = o end end
for _, o in ipairs(frames) do if o.kind == "Frame" and o.pts[1] and o.pts[1][1] == "TOPLEFT" and o.pts[1][4] == 0 and o.pts[1][5] == -38 then backdrop = o end end
local results = {}
local function case(name, ok) results[#results+1] = (ok and "PASS " or "FAIL ") .. name end

local qh = QuestObjectiveTracker.Header
case("one_header_reads_the_quest_count", label and label.text == "quests (2/40)")
case("panel_starts_at_the_first_module_header_row", backdrop ~= nil)
case("first_module_header_text_is_hidden_under_the_band", qh.Text.alpha == 0)
case("other_module_headers_keep_their_text", AchievementObjectiveTracker.Header.Text.alpha == 1)
case("module_gold_minus_is_hidden_and_stays_hidden", (function()
  local b = qh.MinimizeButton; if b.shown then return false end; b:Show(); return b.shown == false end)())

collapsed = true
tracker.Header:SetCollapsed(true)
local btn = tracker.Header.MinimizeButton
case("collapsed_bar_is_compact_on_the_right", backdrop and backdrop.pts[1][1] == "TOPRIGHT" and #backdrop.pts == 1
  and backdrop.w and backdrop.w < 140 and backdrop.h == 24)
case("collapsed_bar_clicks_anywhere_through_the_button", btn.hit and btn.hit[1] <= -(backdrop.w - 14 - 4))
case("collapsed_restores_the_hidden_header_text", qh.Text.alpha == 1)

collapsed = false
tracker.Header:SetCollapsed(false)
case("expanded_restores_the_button_hit_rect", btn.hit and btn.hit[1] == -3 and btn.hit[2] == -3)
case("expanded_panel_spans_the_tracker_again", #backdrop.pts == 2 and backdrop.pts[2][1] == "BOTTOMRIGHT")

AchievementObjectiveTracker.height = 40
tracker:Update()
case("a_different_first_module_names_the_band", label.text == "achievements" and qh.Text.alpha == 1
  and AchievementObjectiveTracker.Header.Text.alpha == 0)
local function plate(b) for _, o in ipairs(frames) do if o.kind == "Frame" and o.pts[1] and o.pts[1][2] == b then return o end end end
local function text(b) local f = plate(b); for _, o in ipairs(frames) do if o.kind == "FontString" and o.pts[1] and o.pts[1][2] == f then return o end end end
local function dots(b) local f = plate(b); local n = 0; for _, o in ipairs(frames) do if o.kind == "Texture" and o.ct and o.pts[1] and o.pts[1][2] == f and o.shown then n = n + 1 end end; return n end
case("turn_in_marker_is_an_amber_question_plate", plate(done) and text(done).text == "?" and text(done).shown
  and text(done).tc[1] == 1 and text(done).tc[2] == 0.7)
case("in_progress_marker_is_three_cyan_dots", plate(todo) and not text(todo).shown and dots(todo) == 3)
case("marker_art_is_held_and_display_hidden", done.Display.alpha == 0)
local before = text(done).tc[2]
done.hooks.OnEnter(done)
case("hover_lifts_the_marker_glyph", text(done).tc[2] > before)
done.hooks.OnMouseDown(done)
case("pressed_nudges_the_glyph_a_pixel", text(done).pts[1][4] == 1 and text(done).pts[1][5] == -1)
done.hooks.OnLeave(done)
case("leave_clears_hover_and_pressed", text(done).tc[2] == before and text(done).pts[1][4] == 0)
done:SetSelected(true)
case("the_followed_quest_wears_pink", text(done).tc[3] == 0.6)
return table.concat(results, "\n")
'''


def main() -> int:
    rt = LuaRuntime(unpack_returned_tuples=True)
    rt.globals().SRC = SRC
    out = rt.execute(LUA)
    print(out)
    lines = out.splitlines()
    failed = [line for line in lines if line.startswith("FAIL")]
    print(f"{len(lines) - len(failed)}/{len(lines)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
