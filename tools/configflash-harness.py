#!/usr/bin/env python3
"""Checks for the /fsconfig hover flash (ticket B3).

Runs the real ConfigWindow.lua, every page file, ConfigTargets.lua and ConfigFlash.lua over the mock frames of
tools/configwindow-harness.py and pins:

  * ConfigTargets maps a setting to the frame it changes: unit frames, party, raid, pet dock, cast bars, the target's
    nameplate, the Gunsight pieces, the class tabs (mana regen, buff tab, ammo, thunder clap, totem presets, the six
    class kits), the data bar, minimap, chat, quest tracker, open bags and the action bar console. A lookup is a function
    run when the row is hovered, a missing module answers nothing, and a row can name its own target
  * hovering a row for 150 ms draws one pooled overlay per target that is on screen, at the target's rect plus FLASH_OUT,
    with FLASH_CORNER brackets, the outline pulsing twice for 1.1 s and then holding; leaving the row removes it
  * a target that is not on screen draws nothing and the row's ? tip says "Not on screen right now."
  * the overlays are plain insecure frames on UIParent (never parented to or anchored on a secure frame), so the flash
    works in combat; unreadable, secret and degenerate rects are skipped
  * Profiles > Window has the "Flash frames on hover" switch (config.flash, on); off draws nothing
  * every key prefix and page in the target map names a key or page the addon really has

The mock does no anchor layout and has no real geometry: a check gives a stand-in frame the rect the client would report.
Everything drawn is pending owner review.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ADDON = ROOT / "forever-stuwave"
CONFIG_DIR = ADDON / "Modules" / "Config"
FLASH_FILE = CONFIG_DIR / "ConfigFlash.lua"
TARGETS_FILE = CONFIG_DIR / "ConfigTargets.lua"
TOC_FILE = ADDON / "forever-stuwave.toc"
MOCKUP = ROOT / "mockups" / "config-window-2026-11-25.html"


def load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load("configwindow_harness", "configwindow-harness.py")
LuaError = base.LuaError

CHECKS = r"""
-- ---- fixtures and helpers --------------------------------------------------------------------------------------------

-- A plain frame the lookups can find by name, with the rect the client would report (left, bottom, width, height).
local function target(name, l, b, w, h)
    local f = CreateFrame("Frame", name, UIParent)
    local r = { l, b, w, h }
    f.rect = r
    function f:GetRect() return r[1], r[2], r[3], r[4] end
    return f
end

local function seat(id, frame, parent)
    FS.Layout._applied = FS.Layout._applied or {}
    FS.Layout._applied[frame] = { id = id, parent = parent }
    return frame
end

local function entryOf(W, page, tab, key)
    W.Open(page, tab)
    local e = W.RowByKey(key, page)
    if not e then error("no row " .. tostring(key) .. " on " .. page, 2) end
    return e
end

local function tick(W, dt)
    local d = W.Flash.driver
    if not (d and d.scripts.OnUpdate) then error("the flash driver is not running", 2) end
    d.scripts.OnUpdate(d, dt)
end

local function overlays(W)
    local out = {}
    for _, o in ipairs(W.Flash.Overlays()) do if o:IsShown() then out[#out + 1] = o end end
    return out
end

-- Hover a row and run the 150 ms wait, so an overlay is up.
local function flashOn(W, entry)
    W.SetHover(entry)
    tick(W, W.Flash.DELAY + 0.01)
end

local function near(a, b, msg)
    if math.abs(a - b) > 0.0001 then error((msg or "number") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end

local function names(list)
    local out = {}
    for _, name in ipairs(list or {}) do out[#out + 1] = name end
    table.sort(out)
    return table.concat(out, ",")
end

local function tipText(owner)
    local from = #TOOLTIP.history
    owner.scripts.OnEnter(owner)
    local lines = {}
    for i = from + 1, #TOOLTIP.history do lines[#lines + 1] = TOOLTIP.history[i] end
    return table.concat(lines, "\n")
end

local function rectOf(o)
    -- the overlay's seat: BOTTOMLEFT of UIParent and its size
    local p = o.points[1]
    return p.x, p.y, o.w, o.h
end

local NOT_SHOWN = "Not on screen right now."

-- ---- the target map --------------------------------------------------------------------------------------------------

local GROUPS = {
    "player", "target", "focus", "boss", "party", "raid", "pet", "pcast", "tcast", "plate", "regen", "bufftab", "ammo",
    "thunderclap", "totem1", "totem2", "forms", "callpet", "portals", "conjure", "poisons", "demons", "databar", "minimap",
    "chat", "tracker", "bags", "console", "grid", "gs.you", "gs.tgt", "gs.class",
}

function T.every_setting_group_the_ticket_names_has_a_lookup()
    local W = boot()
    local Tg = W.Targets
    yes(Tg, "CW.Targets exists")
    for _, name in ipairs(GROUPS) do
        eq(type(Tg.PROVIDERS[name]), "function", "provider " .. name .. " is a function")
    end
end

function T.a_lookup_with_its_module_or_frame_missing_answers_nothing()
    local W = boot()
    local Tg = W.Targets
    for name, fn in pairs(Tg.PROVIDERS) do
        local ok, list = pcall(fn)
        yes(ok, "provider " .. name .. " does not throw with nothing built: " .. tostring(list))
        eq(#Tg.Resolve({ key = "x", target = name }), 0, "provider " .. name .. " has nothing on screen")
    end
    local rects = Tg.Resolve({ key = "unitFrames.hidePlayer", page = "unit", tab = "frames" })
    yes(rects, "a mapped row with nothing on screen is known")
    eq(#rects, 0)
end

function T.a_lookup_is_run_when_asked_so_a_frame_built_later_is_found()
    local W = boot()
    local entry = { key = "chat.w", page = "chat", tab = "g" }
    eq(#W.Targets.Resolve(entry), 0)
    target("ChatFrame1", 100, 200, 600, 300)
    seat("chat", _G.ChatFrame1)
    local rects = W.Targets.Resolve(entry)
    eq(#rects, 1)
    eq(rects[1].left, 100); eq(rects[1].bottom, 200); eq(rects[1].width, 600); eq(rects[1].height, 300)
end

function T.a_key_prefix_picks_the_frame_and_the_longest_prefix_wins()
    local W = boot()
    local Tg = W.Targets
    eq(names(Tg.Providers({ key = "unitFrames.hidePlayer" })), "player")
    eq(names(Tg.Providers({ key = "unitFrames.hideTarget" })), "target")
    eq(names(Tg.Providers({ key = "unitFrames.showFocus" })), "focus")
    eq(names(Tg.Providers({ key = "unitFrames.showBoss" })), "boss")
    eq(names(Tg.Providers({ key = "totems.dial" })), "totem1")
    eq(names(Tg.Providers({ key = "totems.dialPlate" })), "totems")
    eq(names(Tg.Providers({ key = "totems.gnarly" })), "totem2")
    eq(names(Tg.Providers({ key = "totems.gnarlySet2" })), "totem2")
    eq(names(Tg.Providers({ key = "tabs.mage.conjureCount" })), "conjure")
    eq(names(Tg.Providers({ key = "tabs.mage.travelRunes" })), "portals")
    eq(names(Tg.Providers({ key = "tabs.druid.formsLit" })), "forms")
    eq(names(Tg.Providers({ key = "tabs.hunter.petsExtra" })), "callpet")
    eq(names(Tg.Providers({ key = "tabs.rogue.poisonsLeft" })), "poisons")
    eq(names(Tg.Providers({ key = "tabs.warlock.demonsShards" })), "demons")
    eq(names(Tg.Providers({ key = "fivesecond.fx.flash" })), "regen")
    eq(names(Tg.Providers({ key = "ammotab.lowwarn" })), "ammo")
    eq(names(Tg.Providers({ key = "thunderclap.motion" })), "thunderclap")
    eq(names(Tg.Providers({ key = "buffs.combatstate" })), "bufftab")
    eq(names(Tg.Providers({ key = "actionbars.grid" })), "grid")
    eq(names(Tg.Providers({ key = "gunsight.pieces.you" })), "gs.you")
    eq(names(Tg.Providers({ key = "gunsight.pieces.tgt" })), "gs.tgt")
    eq(names(Tg.Providers({ key = "gunsight.classModule.bg" })), "gs.class")
    eq(names(Tg.Providers({ key = "gunsight.warrior.powerups" })), "warriorpowerup")
    eq(names(Tg.Providers({ key = "gunsight.druid.clearcasting" })), "druidclearcasting")
    eq(names(Tg.Providers({ key = "nameplates.comboPips" })), "plate")
end

function T.a_page_stands_in_for_rows_with_no_key_rule_and_a_row_with_neither_has_no_target()
    local W = boot()
    local Tg = W.Targets
    eq(names(Tg.Providers({ key = "plates.hpH", page = "plates", tab = "size" })), "plate")
    eq(names(Tg.Providers({ key = "bars.w", page = "party", tab = "style" })), "party")
    eq(names(Tg.Providers({ key = "bars.w", page = "raid", tab = "style" })), "raid")
    eq(names(Tg.Providers({ key = "bars.w", page = "pet", tab = "style" })), "pet")
    eq(names(Tg.Providers({ key = "databar.seg.fps", page = "data", tab = "g" })), "databar")
    eq(names(Tg.Providers({ key = "bags.anything", page = "bags", tab = "g" })), "bags")
    eq(Tg.Providers({ key = "prof", page = "profiles", tab = "p" }), nil, "Profiles rows change no frame")
    eq(Tg.Resolve({ key = "prof", page = "profiles", tab = "p" }), nil, "an unmapped row is not 'known'")
    eq(Tg.Providers({ key = "config.flash", page = "profiles", tab = "p" }), nil)
end

function T.a_row_can_name_its_own_target_by_provider_name_function_or_frame()
    local W = boot()
    local Tg = W.Targets
    target("ForeverSTUwaveDataBar", 0, 0, 2560, 20)
    eq(#Tg.Resolve({ key = "x.y", target = "databar" }), 1, "by provider name")
    eq(#Tg.Resolve({ key = "unitFrames.hidePlayer", target = "databar" }), 1, "the row's own target beats the key rule")
    local mine = target("MyOwn", 5, 6, 7, 8)
    local byFn = Tg.Resolve({ key = "x.y", target = function() return { mine } end })
    eq(#byFn, 1); eq(byFn[1].left, 5)
    local byFrame = Tg.Resolve({ key = "x.y", target = mine })
    eq(#byFrame, 1); eq(byFrame[1].width, 7)
    eq(Tg.Resolve({ key = "x.y", target = "no such provider" }), nil, "an unknown name is no target")
    local throws = Tg.Resolve({ key = "x.y", target = function() error("boom") end })
    eq(#throws, 0, "a lookup that throws answers nothing and is not forwarded")
end

function T.unit_frames_party_pet_cast_bars_chat_and_minimap_are_found_by_their_layout_seat()
    local W = boot()
    local Tg = W.Targets
    local pf = seat("player", target("PF", 20, 1300, 260, 73))
    seat("target", target("TF", 300, 1300, 260, 73))
    seat("focus", target("FF", 10, 900, 190, 66))
    seat("boss", target("BF", 2300, 900, 210, 210))
    seat("party", target("PartyF", 40, 700, 231, 294))
    seat("petcontainer", target("PetF", 90, 300, 348, 68))
    seat("pcast", target("PC", 1000, 400, 268, 22))
    seat("tcast", target("TC", 1000, 440, 268, 22))
    seat("minimap", target("MM", 2300, 1100, 250, 252))
    for _, c in ipairs({
        { "unitFrames.hidePlayer", 20 }, { "unitFrames.hideTarget", 300 }, { "unitFrames.showFocus", 10 },
        { "unitFrames.showBoss", 2300 },
    }) do
        local r = Tg.Resolve({ key = c[1] })
        eq(#r, 1, c[1]); eq(r[1].left, c[2], c[1])
    end
    eq(Tg.Resolve({ key = "x", page = "party" })[1].left, 40)
    eq(Tg.Resolve({ key = "x", page = "pet" })[1].left, 90)
    eq(#Tg.Resolve({ key = "x", page = "cast" }), 2, "the cast bars page flashes both bars")
    eq(Tg.Resolve({ key = "minimap.scale" })[1].left, 2300)
    -- a frame seated on another parent is not the seat; a shown seat is preferred over a hidden one
    local hidden = seat("player", target("PF2", 1, 1, 1, 1)); hidden.shown = false
    eq(Tg.Resolve({ key = "unitFrames.hidePlayer" })[1].left, 20, "the shown seat wins")
    pf.shown = false; hidden.shown = true
    eq(Tg.Resolve({ key = "unitFrames.hidePlayer" })[1].left, 1)
    seat("player", target("PF3", 7, 7, 7, 7), UIParent)
    hidden.shown = false
    eq(#Tg.Resolve({ key = "unitFrames.hidePlayer" }), 0, "a seat on another parent is not the unit frame")
end

function T.the_raid_is_its_grid_or_nothing_out_of_a_raid()
    local W = boot()
    local Tg = W.Targets
    eq(#Tg.Resolve({ key = "x", page = "raid" }), 0)
    local grid = target("ForeverSTUwaveRaidContainer", 50, 500, 300, 224)
    eq(#Tg.Resolve({ key = "x", page = "raid" }), 1)
    grid.shown = false
    eq(#Tg.Resolve({ key = "x", page = "raid" }), 0, "a hidden grid is not on screen")
end

function T.style_rows_on_the_unit_frames_page_follow_the_picked_frame()
    local W = boot()
    local Tg = W.Targets
    FS.Config.RegisterDefault("bars.module", "player")
    seat("player", target("PF", 20, 1300, 260, 73))
    seat("focus", target("FF", 10, 900, 190, 66))
    local entry = { key = "bars.w", page = "unit", tab = "bars" }
    eq(Tg.Resolve(entry)[1].left, 20, "the first frame until another is picked")
    FS.Config.Set("bars.module", "focus")
    eq(Tg.Resolve(entry)[1].left, 10, "the picked frame")
    FS.Config.Set("bars.module", "nonsense")
    eq(Tg.Resolve(entry)[1].left, 20, "a value that is not a frame falls back to the first")
end

function T.the_nameplate_target_is_the_plate_of_the_unit_that_is_your_target()
    local W = boot()
    local Tg = W.Targets
    local entry = { key = "nameplates.comboPips" }
    eq(#Tg.Resolve(entry), 0, "no plates")
    FS.framesByUnit = { nameplate1 = target("Plate1", 100, 100, 110, 30), nameplate2 = target("Plate2", 400, 120, 110, 30) }
    UnitIsUnit = function(unit, other) return other == "target" and unit == "nameplate2" end
    local r = Tg.Resolve(entry)
    eq(#r, 1); eq(r[1].left, 400, "the target's plate only")
    local fields = 0
    for k, v in pairs(r[1]) do fields = fields + 1; eq(type(v), "number", "a rect holds numbers only, never the frame (" .. k .. ")") end
    eq(fields, 4)
    eq(Tg.Resolve({ key = "plates.hpH", page = "plates", tab = "size" })[1].left, 400, "every Nameplates row follows it")
    UnitIsUnit = function() return false end
    eq(#Tg.Resolve(entry), 0, "no plate for a target that has none")
    UnitIsUnit = function() error("boom") end
    eq(#Tg.Resolve(entry), 0, "an unreadable answer shows nothing")
    UnitIsUnit = nil
    eq(#Tg.Resolve(entry), 0, "no UnitIsUnit shows nothing")
end

function T.gunsight_rows_map_to_their_anchors_and_the_class_module_to_the_area_it_sits_in()
    local W = boot()
    local Tg = W.Targets
    local anchors = {}
    for i, n in ipairs({ "tapeL", "tapeR", "boxL", "boxR", "dotAxis", "next", "shards", "buff", "procL", "procR", "areaU",
        "areaL", "mybuffs" }) do
        anchors[n] = target("GA_" .. n, i * 100, 50, 40, 40)
    end
    FS.Gunsight.anchors = anchors
    FS.Gunsight.IsActive = function() return true end
    FS.Gunsight.IsPieceOn = function() return true end
    eq(Tg.Resolve({ key = "gunsight.pieces.you" })[1].left, 100)
    eq(Tg.Resolve({ key = "gunsight.pieces.tgt" })[1].left, 200)
    eq(Tg.Resolve({ key = "gunsight.pieces.next" })[1].left, 600)
    eq(Tg.Resolve({ key = "gunsight.pieces.shard" })[1].left, 700)
    eq(Tg.Resolve({ key = "gunsight.pieces.buff" })[1].left, 800)
    eq(#Tg.Resolve({ key = "gunsight.pieces.prc" }), 2, "both proc posts")
    eq(Tg.Resolve({ key = "gunsight.pieces.mybuffs" })[1].left, 1300)
    eq(#Tg.Resolve({ key = "gunsight.pieces.dot" }), 2, "the target side areas")
    eq(Tg.Resolve({ key = "gunsight.area.upper" })[1].left, 1100)
    eq(Tg.Resolve({ key = "gunsight.area.lower" })[1].left, 1200)
    eq(Tg.Resolve({ key = "gunsight.tags.level" })[1].left, 400, "the target info box")
    -- the class module is the area the area dropdowns gave it
    local areas = { upper = "debuffsH", lower = "class" }
    FS.Gunsight.GetArea = function(which) return areas[which] end
    eq(Tg.Resolve({ key = "gunsight.classModule.bg" })[1].left, 1200)
    areas.upper, areas.lower = "class", "empty"
    eq(Tg.Resolve({ key = "gunsight.classModule.bg" })[1].left, 1100)
    areas.upper = "empty"
    eq(#Tg.Resolve({ key = "gunsight.classModule.bg" }), 0, "no class module area, nothing on screen")
    -- the master switch points at the HUD's main pieces
    eq(#Tg.Resolve({ key = "gunsight.enabled" }), 4)
    -- a piece that is switched off is not on screen, though its anchor frame stays shown
    FS.Gunsight.IsPieceOn = function(key) return key ~= "shard" end
    eq(#Tg.Resolve({ key = "gunsight.pieces.shard" }), 0)
    eq(#Tg.Resolve({ key = "gunsight.pieces.you" }), 1)
    -- a Gunsight that is off has nothing on screen even though its anchors exist
    FS.Gunsight.IsActive = function() return false end
    eq(#Tg.Resolve({ key = "gunsight.pieces.you" }), 0)
end

function T.the_class_tabs_are_found_by_their_frame_names()
    local W = boot()
    local Tg = W.Targets
    local want = {
        { "fivesecond.enabled", "FSFiveSecondTab" }, { "ammotab.enabled", "FSAmmoTab" },
        { "thunderclap.enabled", "FSThunderClapTab" }, { "buffs.combatstate", "FSBuffTab" },
        { "totems.dial", "FSTotemButton7" }, { "totems.gnarly", "FSTotemButton8" },
        { "tabs.druid.forms", "FSShapeshiftTab" }, { "tabs.hunter.pets", "FSCallPetTab" },
        { "tabs.mage.travel", "FSPortalsTab" }, { "tabs.mage.conjure", "FSConjureTab" },
        { "tabs.rogue.poisons", "FSPoisonsTab" }, { "tabs.warlock.demons", "FSDemonTab" },
    }
    for i, c in ipairs(want) do
        eq(#Tg.Resolve({ key = c[1] }), 0, c[1] .. " before " .. c[2] .. " exists")
        target(c[2], i * 10, 5, 90, 49)
        local r = Tg.Resolve({ key = c[1] })
        eq(#r, 1, c[1]); eq(r[1].left, i * 10, c[1])
    end
    eq(#Tg.Resolve({ key = "totems.dialPlate" }), 2, "the name plates sit on both preset cells")
    eq(#Tg.Resolve({ key = "icons.spellstyle" }), 12 - 2, "the spell icon style lights every class tab that stands")
end

function T.console_grid_data_bar_chat_tracker_and_bags_have_their_frames()
    local W = boot()
    local Tg = W.Targets
    target("FSConsole", 600, 20, 1100, 180)
    eq(Tg.Resolve({ key = "x", page = "ab" })[1].left, 600)
    target("FSActionGrid", 10, 10, 2560, 180)
    eq(Tg.Resolve({ key = "actionbars.grid" })[1].left, 10)
    target("ForeverSTUwaveMicroBar", 1700, 20, 200, 30)
    eq(Tg.Resolve({ key = "icons.microstyle" })[1].left, 1700)
    target("ForeverSTUwaveDataBar", 0, 0, 2560, 20)
    eq(Tg.Resolve({ key = "x", page = "data" })[1].width, 2560)
    seat("chat", target("ChatFrame1", 30, 30, 600, 300))
    eq(Tg.Resolve({ key = "chat.w" })[1].left, 30)
    eq(#Tg.Resolve({ key = "tracker.w" }), 0, "no tracker")
    FS.TrackerSeat = { Rect = function() return 2200, 900, 270, 320 end }   -- left, top, width, height
    local r = Tg.Resolve({ key = "tracker.w" })
    eq(#r, 1); eq(r[1].left, 2200); eq(r[1].bottom, 580, "the seat answers its top, the rect is from the bottom")
    eq(r[1].width, 270); eq(r[1].height, 320)
    FS.TrackerSeat = { Rect = function() return nil end }
    eq(#Tg.Resolve({ key = "tracker.w" }), 0)
    FS.TrackerSeat = { Rect = function() error("boom") end }
    eq(#Tg.Resolve({ key = "tracker.w" }), 0)
end

function T.bags_are_on_screen_only_while_one_is_open()
    local W = boot()
    local Tg = W.Targets
    local entry = { key = "x", page = "bags", tab = "g" }
    local bar = target("ForeverSTUwaveBagBar", 2200, 20, 200, 30)
    eq(#Tg.Resolve(entry), 0, "the bag bar alone is not an open bag")
    local one = target("ContainerFrame1", 2000, 300, 250, 300); one.shown = false
    local two = target("ContainerFrame2", 1700, 300, 250, 300); two.shown = false
    eq(#Tg.Resolve(entry), 0)
    one.shown = true; two.shown = true
    eq(#Tg.Resolve(entry), 2, "every open bag")
    two.shown = false
    eq(#Tg.Resolve(entry), 1)
end

function T.a_rect_is_given_in_uiparent_units()
    local W = boot()
    local Tg = W.Targets
    local f = target("ForeverSTUwaveDataBar", 100, 200, 400, 20)
    function f:GetEffectiveScale() return 0.5 end
    local r = Tg.Resolve({ key = "databar.x", page = "data" })[1]
    near(r.left, 50); near(r.bottom, 100); near(r.width, 200); near(r.height, 10)
    function UIParent:GetEffectiveScale() return 2 end
    r = Tg.Resolve({ key = "databar.x", page = "data" })[1]
    near(r.left, 25); near(r.width, 100)
end

function T.unreadable_secret_and_degenerate_rects_are_skipped()
    local W = boot()
    local Tg = W.Targets
    local entry = { key = "x", page = "data" }
    local f = target("ForeverSTUwaveDataBar", 0, 0, 100, 20)
    local function with(l, b, w, h) f.rect[1], f.rect[2], f.rect[3], f.rect[4] = l, b, w, h; return #Tg.Resolve(entry) end
    eq(with(0, 0, 100, 20), 1)
    eq(with(nil, nil, nil, nil), 0, "a frame with no rect yet")
    eq(with(0, 0, 0, 20), 0, "no width")
    eq(with(0, 0, 100, 0), 0, "no height")
    eq(with(0, 0, -5, 20), 0, "negative size")
    eq(with(0 / 0, 0, 100, 20), 0, "NaN")
    eq(with(0, 0, 1 / 0, 20), 0, "infinity")
    -- stand-ins for secret values: a number the guard names, and a table
    FS.IsSecret = function(v) return v == 777.5 or (type(v) == "table" and v.secret == true) end
    eq(with(777.5, 0, 100, 20), 0, "a secret number is skipped before it is compared")
    eq(with(0, 0, 777.5, 20), 0)
    eq(with({ secret = true }, 0, 100, 20), 0, "a secret number is never compared")
    eq(with(0, 0, 100, { secret = true }), 0)
    function f:GetRect() error("ADDON_ACTION_FORBIDDEN") end
    eq(#Tg.Resolve(entry), 0, "a rect that throws (a protected frame in combat) is skipped")
    function f:GetRect() return 0, 0, 100, 20 end
    function f:IsVisible() error("boom") end
    eq(#Tg.Resolve(entry), 0)
end

function T.a_frame_that_is_hidden_or_under_a_hidden_parent_is_not_on_screen()
    local W = boot()
    local Tg = W.Targets
    local entry = { key = "x", page = "data" }
    local f = target("ForeverSTUwaveDataBar", 0, 0, 100, 20)
    eq(#Tg.Resolve(entry), 1)
    f.shown = false
    eq(#Tg.Resolve(entry), 0)
    f.shown = true
    local holder = CreateFrame("Frame", nil, UIParent)
    f.parent = holder
    holder.shown = false
    eq(#Tg.Resolve(entry), 0, "IsVisible is false when a parent is hidden")
end

function T.the_page_and_key_names_are_unique_and_the_lists_are_plain_arrays()
    local W = boot()
    local Tg = W.Targets
    local seen = {}
    for _, p in ipairs(Tg.Prefixes()) do
        yes(type(p) == "string" and #p > 0, "a prefix is a string")
        yes(not seen[p], "prefix " .. p .. " is listed once"); seen[p] = true
    end
    for _, p in ipairs(Tg.Prefixes()) do
        local name = Tg.Providers({ key = p })[1]
        eq(type(Tg.PROVIDERS[name]), "function", "prefix " .. p .. " names a provider that exists (" .. tostring(name) .. ")")
    end
    local pages = {}
    for _, cat in ipairs(W.Categories()) do pages[cat.key] = true end
    for _, page in ipairs(Tg.Pages()) do
        yes(pages[page], "page " .. page .. " is a registered page")
        local name = Tg.Providers({ page = page })[1]
        eq(type(Tg.PROVIDERS[name]), "function", "page " .. page .. " names a provider that exists (" .. tostring(name) .. ")")
    end
end

-- ---- the flash -------------------------------------------------------------------------------------------------------

local function unitRow(W)
    local entry = entryOf(W, "unit", "frames", "unitFrames.hidePlayer")
    return entry
end

function T.hovering_a_row_waits_150_ms_before_drawing_anything()
    local W = boot()
    seat("player", target("PF", 20, 1300, 260, 73))
    local entry = unitRow(W)
    eq(W.Flash.DELAY, 0.15)
    W.SetHover(entry)
    eq(#overlays(W), 0, "nothing at once")
    tick(W, 0.1)
    eq(#overlays(W), 0, "not after 100 ms")
    tick(W, 0.04)
    eq(#overlays(W), 0, "not after 140 ms")
    tick(W, 0.02)
    eq(#overlays(W), 1, "up after 160 ms")
end

function T.one_overlay_per_target_on_screen_at_its_rect_plus_the_outset()
    local W = boot()
    local S = W.Spec
    seat("player", target("PF", 20, 1300, 260, 73))
    flashOn(W, unitRow(W))
    local o = overlays(W)[1]
    local x, y, w, h = rectOf(o)
    eq(x, 20 - S.FLASH_OUT); eq(y, 1300 - S.FLASH_OUT)
    eq(w, 260 + 2 * S.FLASH_OUT); eq(h, 73 + 2 * S.FLASH_OUT)
    eq(o.points[1].point, "BOTTOMLEFT"); eq(o.points[1].rel, UIParent); eq(o.points[1].relPoint, "BOTTOMLEFT")
    eq(#o.points, 1, "one anchor, on UIParent")
    -- two targets, two overlays
    W.SetHover(nil)
    eq(#overlays(W), 0)
    seat("party", target("PartyF", 40, 700, 231, 294))
    local gs = entryOf(W, "gunsight", "pieces", "gunsight.pieces.dot")
    FS.Gunsight.anchors = { areaU = target("AU", 1000, 800, 100, 50), areaL = target("AL", 1000, 700, 100, 50) }
    flashOn(W, gs)
    eq(#overlays(W), 2, "one per visible target")
end

function T.leaving_the_row_removes_the_overlay_and_the_pool_is_reused()
    local W = boot()
    seat("player", target("PF", 20, 1300, 260, 73))
    local entry = unitRow(W)
    flashOn(W, entry)
    local first = overlays(W)[1]
    local made = #W.Flash.Overlays()
    W.SetHover(nil)
    eq(#overlays(W), 0, "gone when the pointer leaves the row")
    eq(W.Flash.driver.scripts.OnUpdate, nil, "no OnUpdate while idle")
    flashOn(W, entry)
    eq(overlays(W)[1], first, "the same frame comes back")
    eq(#W.Flash.Overlays(), made, "nothing new was made")
    -- the pointer leaving before the wait is up draws nothing at all
    W.SetHover(nil)
    W.SetHover(entry)
    tick(W, 0.1)
    W.SetHover(nil)
    eq(#overlays(W), 0)
    eq(W.Flash.driver.scripts.OnUpdate, nil)
end

function T.the_overlay_is_a_cyan_outline_with_four_corner_brackets()
    local W = boot()
    local S, C = W.Spec, W.C
    seat("player", target("PF", 20, 1300, 260, 73))
    flashOn(W, unitRow(W))
    local o = overlays(W)[1]
    eq(#o.fsBrackets, 8, "two arms on each of four corners")
    local at = { TOPLEFT = 0, TOPRIGHT = 0, BOTTOMLEFT = 0, BOTTOMRIGHT = 0 }
    for _, t in ipairs(o.fsBrackets) do
        at[t.points[1].point] = at[t.points[1].point] + 1
        eq(t.points[1].x, 0); eq(t.points[1].y, 0)
        local long, thin = math.max(t.w, t.h), math.min(t.w, t.h)
        eq(long, S.FLASH_CORNER, "an arm is FLASH_CORNER long"); eq(thin, 2, "and 2 thick")
        near(t.color[1], C.cyan[1]); near(t.color[2], C.cyan[2]); near(t.color[3], C.cyan[3]); eq(t.color[4], 1)
    end
    for point, n in pairs(at) do eq(n, 2, point .. " has two arms") end
    eq(#o.fsEdges, 4, "the outline is four 1 unit edges")
    for _, e in ipairs(o.fsEdges) do
        near(e.color[1], C.cyan[1]); near(e.color[3], C.cyan[3]); near(e.color[4], 0.8, "outline alpha")
    end
    eq(o.fsPulse.parent, o, "the outline and glow sit on the pulsing child")
end

function T.the_outline_pulses_twice_for_1_1_seconds_each_and_then_holds()
    local W = boot()
    local F = W.Flash
    eq(F.PULSE, 1.1); eq(F.PULSES, 2)
    near(F.Envelope(0), 0)
    near(F.Envelope(0.44), 1, "the first key frame, 40 percent in")
    near(F.Envelope(0.77), 0.35, "70 percent in")
    near(F.Envelope(1.099), 1, "the end of the first pulse")
    near(F.Envelope(1.1), 0, "the second pulse starts from nothing")
    near(F.Envelope(1.1 + 0.44), 1)
    near(F.Envelope(2.2), 1, "then it holds")
    near(F.Envelope(5), 1)
    local mid = F.Envelope(0.22)
    yes(mid > 0 and mid < 1, "ease between the key frames")
    -- driven by the tick
    seat("player", target("PF", 20, 1300, 260, 73))
    flashOn(W, unitRow(W))
    local o = overlays(W)[1]
    near(o.fsPulse:GetAlpha(), F.Envelope(0.01), "alpha starts where the envelope does")
    tick(W, 0.43)
    near(o.fsPulse:GetAlpha(), F.Envelope(0.44))
    tick(W, 0.33)
    near(o.fsPulse:GetAlpha(), F.Envelope(0.77))
    tick(W, 2)
    near(o.fsPulse:GetAlpha(), 1, "held after the second pulse")
    eq(o.alpha, 1, "the brackets never pulse")
end

function T.a_target_that_is_not_on_screen_draws_nothing_and_the_tip_says_so()
    local W = boot()
    local entry = unitRow(W)     -- the player frame does not exist
    W.SetHover(entry)
    tick(W, 0.2)
    eq(#overlays(W), 0)
    local icon = entry.row.fsHelp
    yes(icon and icon:IsShown(), "a row with no tip gets its ? while it is pointed at")
    eq(tipText(icon), NOT_SHOWN)
    W.SetHover(nil)
    no(icon:IsShown(), "and loses it again afterwards")
    -- a row that already has a tip keeps it and gains the line
    local gs = entryOf(W, "gunsight", "target", "gunsight.targetBars.numbers")
    local before = gs.row.fsHelp and gs.row.fsHelp.fsTip
    W.SetHover(gs)
    tick(W, 0.2)
    local tip = tipText(gs.row.fsHelp)
    yes(tip:find(NOT_SHOWN, 1, true), "the line is added: " .. tip)
    if before and before ~= "" then yes(tip:find(before, 1, true), "the row's own tip is still there") end
    W.SetHover(nil)
    eq(gs.row.fsHelp and gs.row.fsHelp.fsTip or "", before or "", "the tip is back as it was")
end

function T.a_target_that_is_on_screen_adds_no_tip_line()
    local W = boot()
    seat("player", target("PF", 20, 1300, 260, 73))
    local entry = unitRow(W)
    W.SetHover(entry)
    tick(W, 0.2)
    local icon = entry.row.fsHelp
    no(icon and icon:IsShown(), "no ? for a row with nothing to say")
end

function T.the_tip_line_goes_when_the_target_appears_while_the_row_is_pointed_at()
    local W = boot()
    local entry = unitRow(W)
    W.SetHover(entry)
    tick(W, 0.2)
    yes(entry.row.fsHelp:IsShown())
    seat("player", target("PF", 20, 1300, 260, 73))
    tick(W, 0.1)
    eq(#overlays(W), 1, "it starts drawing")
    no(entry.row.fsHelp:IsShown(), "and the line is gone")
end

function T.a_refresh_of_the_row_tip_keeps_the_line_while_the_target_is_missing()
    local W = boot()
    local entry = unitRow(W)
    W.SetHover(entry)
    tick(W, 0.2)
    W.I.RefreshTip(entry.row)
    yes(entry.row.fsHelp:IsShown())
    eq(tipText(entry.row.fsHelp), NOT_SHOWN)
    W.RefreshAll()
    yes(entry.row.fsHelp:IsShown(), "RefreshAll keeps it")
    eq(tipText(entry.row.fsHelp), NOT_SHOWN)
end

function T.a_row_with_no_target_gets_no_overlay_and_no_tip_line()
    local W = boot()
    W.Open("profiles", "p")
    local entry = W.RowByKey("config.flash", "profiles")
    yes(entry, "the switch row exists")
    W.SetHover(entry)
    eq(W.Flash.driver.scripts.OnUpdate, nil, "a row with no target starts nothing")
    eq(#overlays(W), 0)
    local icon = entry.row.fsHelp
    yes(icon, "it has its own tip")
    no(tipText(icon):find(NOT_SHOWN, 1, true), "and no line about the screen")
end

function T.the_switch_lives_in_profiles_window_defaults_on_and_turns_the_flash_off()
    local W = boot()
    W.Open("profiles", "p")
    local entry = W.RowByKey("config.flash", "profiles")
    yes(entry, "Profiles has config.flash")
    eq(entry.label, "Flash frames on hover")
    eq(entry.section, "Window")
    eq(entry.kind, "switch")
    eq(FS.Config.Get("config.flash"), true, "on by default")
    yes(W.Flash.Enabled())
    local saved = W.RowByKey("export.enabled", "profiles")
    -- the Window section is built before Saved data (order 1000)
    local order = {}
    for _, e in ipairs(W.Rows()) do if e.page == "profiles" and (e.section == "Window" or e.section == "Saved data") then order[#order + 1] = e.section end end
    if saved then eq(order[#order], "Saved data", "Window sits above Saved data") end
    -- off: nothing drawn, no tip line
    seat("player", target("PF", 20, 1300, 260, 73))
    press("Flash frames on hover")
    eq(FS.Config.Get("config.flash"), false)
    no(W.Flash.Enabled())
    W.Open("unit", "frames")
    local player = W.RowByKey("unitFrames.hidePlayer", "unit")
    W.SetHover(player)
    local d = W.Flash.driver
    if d.scripts.OnUpdate then d.scripts.OnUpdate(d, 0.3) end
    eq(#overlays(W), 0, "switch off draws nothing")
    W.SetHover(nil)
    -- missing target and the switch off: no line either
    _G.PF.shown = false
    W.SetHover(player)
    no(player.row.fsHelp and player.row.fsHelp:IsShown(), "no tip line with the switch off")
    W.SetHover(nil)
    -- back on
    W.Open("profiles", "p")
    press("Flash frames on hover")
    eq(FS.Config.Get("config.flash"), true)
end

function T.turning_the_switch_off_while_a_flash_is_up_clears_it()
    local W = boot()
    seat("player", target("PF", 20, 1300, 260, 73))
    local entry = unitRow(W)
    flashOn(W, entry)
    eq(#overlays(W), 1)
    FS.Config.Set("config.flash", false)
    eq(#overlays(W), 0, "gone as soon as the switch flips")
    eq(W.Flash.driver.scripts.OnUpdate, nil)
end

function T.the_overlays_are_plain_insecure_frames_on_uiparent_so_the_flash_works_in_combat()
    local W = boot()
    local pf = seat("player", target("PF", 20, 1300, 260, 73))
    pf.protected = true
    __combat = true
    local entry = unitRow(W)
    flashOn(W, entry)
    local o = overlays(W)[1]
    yes(o, "drawn in combat over a protected frame")
    eq(o.protected, false, "the overlay is not protected")
    eq(o.parent, UIParent, "parented to UIParent")
    eq(o.strata, "FULLSCREEN_DIALOG")
    eq(o.mouse, false, "mouse disabled")
    for _, p in ipairs(o.points) do eq(p.rel, UIParent, "anchored on UIParent only") end
    for _, child in ipairs(ALL) do
        if child.parent == o or child.parent == o.fsPulse then
            for _, p in ipairs(child.points) do
                yes(p.rel == o or p.rel == o.fsPulse, "a piece is anchored inside the overlay")
            end
        end
    end
    eq(#BLOCKED, 0, "nothing protected was touched")
    local anchoredOnTarget = false
    for _, f in ipairs(ALL) do
        for _, p in ipairs(f.points or {}) do if p.rel == pf then anchoredOnTarget = true end end
    end
    no(anchoredOnTarget, "nothing is anchored on the target")
    __combat = false
end

function T.the_overlay_follows_a_target_that_moves_or_is_resized_while_the_row_is_pointed_at()
    local W = boot()
    local S = W.Spec
    local pf = seat("player", target("PF", 20, 1300, 260, 73))
    flashOn(W, unitRow(W))
    pf.rect[1], pf.rect[3] = 500, 300
    tick(W, 0.06)
    local x, y, w = rectOf(overlays(W)[1])
    eq(x, 500 - S.FLASH_OUT); eq(w, 300 + 2 * S.FLASH_OUT)
end

function T.at_most_twelve_overlays_are_drawn_for_one_row()
    local W = boot()
    for i = 1, 20 do
        target("ContainerFrame" .. i, i * 10, 10, 8, 8)
    end
    local entry = { key = "x", page = "bags", tab = "g", row = CreateFrame("Frame", nil, UIParent) }
    W.Flash.Show(entry)
    eq(#overlays(W), W.Flash.MAX)
    eq(W.Flash.MAX, 12)
end

function T.closing_the_window_or_changing_page_clears_the_flash()
    local W = boot()
    seat("player", target("PF", 20, 1300, 260, 73))
    local entry = unitRow(W)
    flashOn(W, entry)
    eq(#overlays(W), 1)
    W.Open("profiles", "p")
    eq(#overlays(W), 0, "a page change clears it")
    W.Open("unit", "frames")
    W.SetHover(nil)
    flashOn(W, W.RowByKey("unitFrames.hidePlayer", "unit"))
    eq(#overlays(W), 1)
    W.Close()
    eq(#overlays(W), 0, "closing the window clears it")
    eq(W.Flash.driver.scripts.OnUpdate, nil)
end

function T.nothing_breaks_when_the_targets_file_is_missing()
    local W = boot()
    seat("player", target("PF", 20, 1300, 260, 73))
    local entry = unitRow(W)
    local saved = W.Targets
    W.Targets = nil
    W.SetHover(entry)
    eq(#overlays(W), 0)
    if W.Flash.driver.scripts.OnUpdate then tick(W, 0.3) end
    eq(#overlays(W), 0)
    W.SetHover(nil)
    W.Targets = saved
end

function T.a_lookup_that_returns_junk_never_breaks_the_flash()
    local W = boot()
    local entry = unitRow(W)
    for _, junk in ipairs({ 5, "text", true, { 1, 2, 3 }, { {} }, { { left = "a" } } }) do
        entry.target = function() return junk end
        W.SetHover(entry)
        tick(W, 0.3)
        eq(#overlays(W), 0, "junk draws nothing")
        W.SetHover(nil)
    end
end

function T.a_read_only_config_still_flashes()
    local W = boot({ db = "junk" })
    seat("player", target("PF", 20, 1300, 260, 73))
    local entry = unitRow(W)
    flashOn(W, entry)
    eq(#overlays(W), 1, "the flash reads settings and writes none")
end

function T.the_flash_never_writes_a_setting_or_calls_anything_protected()
    local W = boot()
    local sets = 0
    local set = FS.Config.Set
    FS.Config.Set = function(...) sets = sets + 1; return set(...) end
    seat("player", target("PF", 20, 1300, 260, 73))
    flashOn(W, unitRow(W))
    tick(W, 3)
    W.SetHover(nil)
    eq(sets, 0, "hovering writes nothing")
    FS.Config.Set = set
end

-- Plain data for the python level checks (the real files, booted once).
__helpers = {
    prefixes = function()
        local W = boot()
        return W.Targets.Prefixes()
    end,
    pulse = function()
        local W = boot()
        return { pulse = W.Flash.PULSE, pulses = W.Flash.PULSES, env = W.Flash.ENVELOPE }
    end,
}
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


def lua_files() -> list[Path]:
    return sorted(ADDON.rglob("*.lua"))


def check_no_dash_or_automation_word_in_the_two_files() -> list[str]:
    problems = []
    for path in (FLASH_FILE, TARGETS_FILE):
        text = path.read_text(encoding="utf-8")
        if "—" in text or "–" in text:
            problems.append(f"{path.name} has an em or en dash")
        for line in text.splitlines():
            if line.strip().startswith("--"):
                continue
            # a string with a space in it is text a player can read; the rest are frame and key names
            for lit in re.findall(r'"([^"]* [^"]*)"', line):
                for word in ("tape", "bot", "macro", "automat", "script"):
                    if re.search(r"\b" + word, lit, re.I):
                        problems.append(f"{path.name}: player-visible text with '{word}': {lit[:60]}")
    return problems


def check_the_toc_loads_flash_then_targets_after_the_footer() -> list[str]:
    toc = [ln.strip() for ln in TOC_FILE.read_text(encoding="utf-8").splitlines()]
    order = [toc.index(f"Modules/Config/{name}.lua") for name in ("ConfigFooter", "ConfigFlash", "ConfigTargets")]
    return [] if order == sorted(order) else [f"toc order is {order}"]


def check_the_flash_never_parents_or_anchors_on_a_target() -> list[str]:
    text = FLASH_FILE.read_text(encoding="utf-8")
    problems = []
    code = "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith("--"))
    if re.search(r"CreateFrame\([^)]*,\s*[^)]*\b(frame|target|thing)\b\s*\)", code):
        problems.append("an overlay is created on a target")
    if "ReloadUI" in code:
        problems.append("ReloadUI in the flash")
    return problems


def check_the_pulse_is_the_mockups_animation() -> list[str]:
    css = MOCKUP.read_text(encoding="utf-8")
    problems = []
    anim = re.search(r"\.flash:after\{[^\n]*animation:fl ([0-9.]+)s ease-in-out (\d+) forwards", css)
    start = css.index("@keyframes fl")
    frames = re.findall(r"(\d+)%\{opacity:([0-9.]+)\}", css[start:css.index("\n", start)])
    if not anim:
        return ["the mockup has no .flash animation"]
    lua = base.boot()
    data = lua.eval("__helpers")["pulse"]()
    pulse = float(data["pulse"])
    pulses = int(data["pulses"])
    if abs(pulse - float(anim.group(1))) > 1e-9:
        problems.append(f"pulse {pulse} != mockup {anim.group(1)}")
    if pulses != int(anim.group(2)):
        problems.append(f"pulses {pulses} != mockup {anim.group(2)}")
    env = data["env"]
    got = [(round(float(env[i][1]) * 100), float(env[i][2])) for i in range(1, len(env) + 1)]
    want = [(int(p), float(o)) for p, o in frames]
    if got != want:
        problems.append(f"envelope {got} != mockup {want}")
    if "FLASH_OUT" not in FLASH_FILE.read_text(encoding="utf-8") or "FLASH_CORNER" not in FLASH_FILE.read_text(encoding="utf-8"):
        problems.append("the flash does not read FLASH_OUT and FLASH_CORNER from the spec")
    return problems


def check_every_prefix_and_page_in_the_map_is_real() -> list[str]:
    lua = base.boot()
    prefixes = [str(p) for p in lua.eval("__helpers")["prefixes"]().values()]
    problems = []
    literals: dict[Path, set[str]] = {}
    for path in lua_files():
        if path == TARGETS_FILE or path.name == "ConfigFlash.lua":
            continue
        literals[path] = set(re.findall(r'"([A-Za-z][A-Za-z0-9_.]*)"', path.read_text(encoding="utf-8")))
    for prefix in prefixes:
        found = False
        for path, lits in literals.items():
            if any(lit.startswith(prefix) for lit in lits):
                found = True
                break
            for lit in lits:
                if lit.endswith(".") and prefix.startswith(lit) and len(lit) >= 4:
                    tail = prefix[len(lit):].split(".")[0]
                    if not tail or any(l2 == tail or l2.startswith(tail) for l2 in lits):
                        found = True
                        break
            if found:
                break
        if not found:
            problems.append(f"no key in the addon starts with '{prefix}'")
    return problems


def main() -> int:
    failed = run_lua_checks()
    py_checks = [
        ("no_dash_or_automation_word_in_the_two_files", check_no_dash_or_automation_word_in_the_two_files),
        ("the_toc_loads_flash_then_targets_after_the_footer", check_the_toc_loads_flash_then_targets_after_the_footer),
        ("the_flash_never_parents_or_anchors_on_a_target", check_the_flash_never_parents_or_anchors_on_a_target),
        ("the_pulse_is_the_mockups_animation", check_the_pulse_is_the_mockups_animation),
        ("every_prefix_and_page_in_the_map_is_real", check_every_prefix_and_page_in_the_map_is_real),
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
