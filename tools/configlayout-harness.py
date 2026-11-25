#!/usr/bin/env python3
"""Layout and structure checks for the rebuilt /fsconfig window (ticket A1).

The mock frame tree of tools/configwindow-harness.py does no anchor layout, so this harness adds an anchor solver
(Lua, run inside the same mock) and uses it at the default, minimum and maximum window sizes on every page and tab:

  * the window, nav, well and tab page rects follow the size; the nav fits its column
  * every visible row sits inside its page, no two rows overlap, the holder reaches the last row
  * two column sections pair their rows on one line, each half wide enough to use at the smallest size
  * every page and tab of the prototype (mockups/proto-src-2026-11-25/proto-pages.js) exists, or is owned by a stub file
  * ConfigSpec.lua matches the SPEC const of mockups/config-window-2026-11-25.html name for name
  * the extension points other lanes use exist and work (RegisterCategory, ExtendTab, Open, On, slots, registry, folds)
  * the saved settings of the old window are all still reachable (no key lost)

Everything the window draws is pending Parker review: this proves geometry, not looks.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MOCKUPS = Path(os.environ.get("FS_MOCKUPS_DIR", ROOT / "mockups"))

spec = importlib.util.spec_from_file_location("configwindow_harness", HERE / "configwindow-harness.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
LuaError = base.LuaError

SOLVER = r"""
-- ---- anchor solver: y goes up (top > bottom), the mock's UIParent is 2560 x 1440 ------------------------------------
local function solveAll()
    local cache, depth = {}, 0
    local rect
    local function anchorXY(rel, relPoint)
        local r = rect(rel)
        local x = relPoint:find("LEFT") and r.l or relPoint:find("RIGHT") and r.r or (r.l + r.r) / 2
        local y = relPoint:find("TOP") and r.t or relPoint:find("BOTTOM") and r.b or (r.t + r.b) / 2
        return x, y
    end
    function rect(f)
        if cache[f] then return cache[f] end
        depth = depth + 1
        if depth > 60 then error("anchor chain too deep at " .. tostring(f.name or f.kind)) end
        local r
        if f == UIParent then
            r = { l = 0, r = f.w, t = f.h, b = 0 }
        else
            local parent = f.parent or UIParent
            local left, right, cx, top, bottom, cy
            local all
            for _, p in ipairs(f.points) do
                if p.point == "ALL" then
                    all = rect(p.rel or parent)
                else
                    local ax, ay = anchorXY(p.rel or parent, p.relPoint or p.point)
                    local px, py = ax + (p.x or 0), ay + (p.y or 0)
                    if p.point:find("LEFT") then left = px elseif p.point:find("RIGHT") then right = px else cx = px end
                    if p.point:find("TOP") then top = py elseif p.point:find("BOTTOM") then bottom = py else cy = py end
                end
            end
            if all then
                r = { l = all.l, r = all.r, t = all.t, b = all.b }
            else
                local w, h = f.w or 0, f.h or 0
                local pr = rect(parent)
                local l, rr, t, b
                if left and right then l, rr = left, right
                elseif left then l, rr = left, left + w
                elseif right then l, rr = right - w, right
                elseif cx then l, rr = cx - w / 2, cx + w / 2
                else l, rr = pr.l, pr.l + w end
                if top and bottom then t, b = top, bottom
                elseif top then t, b = top, top - h
                elseif bottom then t, b = bottom + h, bottom
                elseif cy then t, b = cy + h / 2, cy - h / 2
                else t, b = pr.t, pr.t - h end
                r = { l = l, r = rr, t = t, b = b }
            end
        end
        depth = depth - 1
        cache[f] = r
        return r
    end
    return rect
end

local function winFrame() return _G.ForeverSTUwaveConfig end

local function tabPage(catKey)
    local page
    for _, o in ipairs(ALL) do
        if o.kind == "ScrollFrame" and o:IsVisible() and o.fsPageKey == catKey then page = o end
    end
    return page
end

local function near(a, b, tol) return math.abs(a - b) <= (tol or 0.51) end

local function checkSize(W, w, h)
    W.SetSize(w, h, false)
    local D = W.D
    local rect = solveAll()
    local win = rect(winFrame())
    eq(win.r - win.l, w, "window width"); eq(win.t - win.b, h, "window height")
    eq(D.WIN_W, w); eq(D.WIN_H, h)
    local seen = 0
    for _, cat in ipairs(W.Categories()) do
        for _, tab in ipairs(cat.tabs) do
            W.Open(cat.key, tab.key)
            local where = ("%s/%s @ %dx%d"):format(cat.key, tab.key, w, h)
            local page = tabPage(cat.key)
            yes(page, where .. ": the tab page is showing")
            rect = solveAll()
            local win2 = rect(winFrame())
            local pr, hr = rect(page), rect(page.fsHolder)
            yes(pr.l >= win2.l - 9 and pr.r <= win2.r + 9, where .. ": the page sits in the window")
            yes(near(hr.r - hr.l, D.CONTENT_W), where .. ": the holder is CONTENT_W wide, got " .. (hr.r - hr.l))
            yes(hr.l >= win2.l and hr.r <= win2.r, where .. ": the holder is inside the window")
            local boxes = {}
            for _, item in ipairs(page.fsHolder.fsFlow or {}) do
                if item.frame:IsShown() then
                    local r = rect(item.frame)
                    yes(r.l >= hr.l - 0.51 and r.r <= hr.r + 0.51, where .. ": a row is inside the page width: "
                        .. tostring(item.frame.fsEntry and item.frame.fsEntry.label or item.frame.name or item.kind))
                    yes(r.t <= hr.t + 0.51, where .. ": a row starts below the holder top")
                    boxes[#boxes + 1] = r
                    seen = seen + 1
                end
            end
            for i = 1, #boxes do
                for j = i + 1, #boxes do
                    local a, b = boxes[i], boxes[j]
                    local across = math.min(a.r, b.r) - math.max(a.l, b.l)
                    local down = math.min(a.t, b.t) - math.max(a.b, b.b)
                    yes(not (across > 1 and down > 1), where .. ": two rows overlap")
                end
            end
            local lowest = hr.t
            for _, r in ipairs(boxes) do if r.b < lowest then lowest = r.b end end
            yes(page.fsHolder:GetHeight() >= hr.t - lowest - 0.51, where .. ": the holder reaches the last row")
        end
    end
    yes(seen > 50, "rows were measured: " .. seen)
    -- the nav: every entry inside the window, none on top of another
    local rect2 = solveAll()
    local win3 = rect2(winFrame())
    local navBoxes = {}
    for _, o in ipairs(ALL) do
        if o.fsCategory and o:IsShown() then
            local r = rect2(o)
            yes(r.l >= win3.l and r.r - r.l <= 200, "a nav entry fits the column")
            navBoxes[#navBoxes + 1] = r
        end
    end
    yes(#navBoxes >= 20, "the nav lists every page: " .. #navBoxes)
    for i = 1, #navBoxes do
        for j = i + 1, #navBoxes do
            local a, b = navBoxes[i], navBoxes[j]
            yes(not (math.min(a.t, b.t) - math.max(a.b, b.b) > 1 and math.min(a.r, b.r) - math.max(a.l, b.l) > 1),
                "two nav entries overlap")
        end
    end
end

function T.the_window_lays_out_at_the_default_size()
    local W = boot()
    W.Open()
    local S = W.Spec
    checkSize(W, S.WIN_W, S.WIN_H)
end

function T.the_window_lays_out_at_the_minimum_size()
    local W = boot()
    W.Open()
    local S = W.Spec
    checkSize(W, S.WIN_MIN_W, S.WIN_MIN_H)
    yes(W.D.HALF_W >= 180, "a half column is still wide enough at the smallest size: " .. W.D.HALF_W)
end

function T.the_window_lays_out_at_the_maximum_size()
    local W = boot()
    W.Open()
    local S = W.Spec
    checkSize(W, S.WIN_MAX_W, S.WIN_MAX_H)
end

function T.the_size_is_clamped_to_the_minimum_and_maximum()
    local W = boot()
    W.Open()
    local S = W.Spec
    W.SetSize(10, 10, false)
    eq(winFrame():GetWidth(), S.WIN_MIN_W); eq(winFrame():GetHeight(), S.WIN_MIN_H)
    W.SetSize(99999, 99999, false)
    eq(winFrame():GetWidth(), S.WIN_MAX_W); eq(winFrame():GetHeight(), S.WIN_MAX_H)
end

function T.two_column_sections_pair_their_rows_on_one_line()
    local W = boot()
    W.Open("gunsight", "pieces")
    local rect = solveAll()
    local left, right = row("Your cast bar"), row("Target cast bar")
    yes(left and right, "the first pair exists")
    local a, b = rect(left), rect(right)
    eq(a.t, b.t, "a pair shares a line")
    yes(a.r <= b.l, "left then right, no overlap")
    yes(near(a.r - a.l, W.D.HALF_W) and near(b.r - b.l, W.D.HALF_W), "each half is HALF_W wide")
end

function T.every_page_has_a_tab_and_a_known_group()
    local W = boot()
    local groups = { FRAMES = true, SCREEN = true, PANELS = true, GENERAL = true }
    for _, c in ipairs(W.Categories()) do
        yes(groups[c.group], c.key .. ": a known nav group, got " .. tostring(c.group))
        yes(#c.tabs >= 1, c.key .. ": at least one tab")
    end
end
"""

EXT_CHECKS = r"""
function T.register_category_with_tabs_and_extend_tab_adds_a_section_in_order()
    local W = boot()
    local built = {}
    W.RegisterCategory({ key = "x1", label = "X1", group = "FRAMES", order = 50, tabs = {
        { key = "a", label = "A", build = function(c) built[#built + 1] = "base"; W.UI.Section(c, { title = "Base" }) end },
        { key = "b", label = "B", build = function() end },
    } })
    yes(W.ExtendTab("x1", "a", "Before", function(c) built[#built + 1] = "before" end, -5))
    yes(W.ExtendTab("x1", "a", "After", function(c) built[#built + 1] = "after" end))
    yes(W.ExtendTab("x1", "a", { title = "Late", fold = true }, function(c) built[#built + 1] = "late" end, 500))
    W.Open("x1", "a")
    eq(table.concat(built, ","), "before,base,after,late", "extension order: below 0, the base, then by order")
    no(W.ExtendTab(nil, "a", "x", function() end)); no(W.ExtendTab("x1", "a", "x", "nope"))
    -- a tab already built gets a late extension at its end
    W.ExtendTab("x1", "a", "Last", function(c) built[#built + 1] = "last" end, 900)
    eq(built[#built], "last")
end

function T.open_takes_a_page_a_tab_and_a_row_key()
    local W = boot()
    W.Open("gunsight", "target")
    local page, tab = W.Current()
    eq(page, "gunsight"); eq(tab, "target")
    W.Open("profiles")
    eq((W.Current()), "profiles")
    W.Open("gunsight", "player", "gunsight.pieces.next")
    local _, t2 = W.Current()
    eq(t2, "player", "the tab of the row")
end

function T.on_events_fire_for_show_hide_select_and_jump()
    local W = boot()
    local log = {}
    for _, ev in ipairs({ "show", "hide", "select", "jump" }) do W.On(ev, function(...) log[#log + 1] = ev end) end
    no(W.On("show", "nope"), "a bad handler is refused")
    W.Open("unit"); W.Open("gunsight", "target"); W.Close()
    local text = table.concat(log, ",")
    yes(text:find("show", 1, true), text); yes(text:find("select", 1, true), text); yes(text:find("hide", 1, true), text)
    W.Open("unit", "frames", "unitFrames.hidePlayer")
    yes(table.concat(log, ","):find("jump", 1, true), "Open with a row key fires jump")
end

function T.the_registry_lists_every_built_row_with_its_page_tab_and_key()
    local W = boot()
    W.Open("unit", "frames")
    local entry = W.RowByKey("unitFrames.hidePlayer")
    yes(entry, "the inverted row is in the registry")
    eq(entry.page, "unit"); eq(entry.tab, "frames"); eq(entry.label, "Show player frame"); eq(entry.inverted, true)
    yes(#W.Rows() >= 4)
end

function T.a_when_predicate_hides_a_row_and_reflow_closes_the_gap()
    local W = boot()
    local on = true
    W.RegisterCategory({ key = "wh", label = "Wh", group = "GENERAL", order = 60, build = function(c)
        W.UI.Toggle(c, { label = "One", get = function() return true end, set = function() end })
        W.UI.Toggle(c, { label = "Two", get = function() return true end, set = function() end, when = function() return on end })
        W.UI.Toggle(c, { label = "Three", get = function() return true end, set = function() end })
    end })
    W.Open("wh")
    local rect = solveAll()
    local y3 = rect(row("Three")).t
    on = false
    W.RefreshAll()
    no(row("Two"), "the hidden row is not visible")
    rect = solveAll()
    yes(rect(row("Three")).t > y3, "the row below moved up: " .. rect(row("Three")).t .. " vs " .. y3)
    on = true
    W.RefreshAll()
    yes(row("Two"), "back again")
end

function T.a_folded_section_hides_its_rows_and_the_fold_is_kept_account_wide()
    local W = boot()
    local function build(W)
        W.RegisterCategory({ key = "fo", label = "Fo", group = "GENERAL", order = 61, build = function(c)
            W.UI.Section(c, { title = "Fold me", fold = true })
            W.UI.Toggle(c, { label = "Inside", get = function() return true end, set = function() end })
        end })
    end
    build(W)
    W.Open("fo")
    no(row("Inside"), "a foldable section starts folded")
    local id
    for k in pairs(ForeverSTUwaveDB.ui and ForeverSTUwaveDB.ui.folds or {}) do id = k end
    W.SetFolded("fo/main/Fold me", false)
    eq(ForeverSTUwaveDB.ui.folds["fo/main/Fold me"], false, "kept in the account state, not a profile")
    local W2 = reload()
    build(W2)
    W2.Open("fo")
    yes(row("Inside"), "the open fold came back after a reload")
end

function T.the_slots_for_other_lanes_exist()
    local W = boot()
    W.Open()
    for _, name in ipairs({ "NavSlot", "NavRows", "FooterSlot", "SearchSlot", "JumpHighlight", "PageBody", "RowByKey", "Rows",
        "On", "Open", "ExtendTab", "RegisterCategory", "SetFolded", "IsFolded" }) do
        yes(type(W[name]) == "function", name .. " is a function")
    end
    yes(W.SearchSlot(), "the search slot is a frame")
    yes(W.FooterSlot("left") and W.FooterSlot("right"), "both footer slots are frames")
    yes(type(W.NavRows()) == "table", "NavRows lists the nav entries")
end

function T.zz_dump()
    local W = boot()
    return W
end

function T.opening_the_window_with_every_stub_loaded_forwards_no_error()
    local W = boot()
    W.Open()
    eq(#__errors, 0, "no error forwarded while opening")
end
"""

LAYOUT_NAMES: set[str] = set()


def run_lua_checks() -> int:
    global LAYOUT_NAMES
    LAYOUT_NAMES = {n for n in re.findall(r"^function T\.([a-z0-9_]+)\(", SOLVER + EXT_CHECKS, re.M) if not n.startswith("zz_")}
    base.CHECKS = base.CHECKS.replace("__checks = T", SOLVER + EXT_CHECKS + "\n__checks = T")
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

def spec_from_mockup() -> dict[str, float]:
    html = (MOCKUPS / "config-window-2026-11-25.html").read_text(encoding="utf-8")
    block = html.split("const SPEC=[", 1)[1].split("\n];", 1)[0]
    out = {}
    for name, value in re.findall(r"\['([A-Z0-9_]+)',(-?[0-9.]+)", block):
        out[name] = float(value)
    return out


def check_spec_matches_the_mockup() -> list[str]:
    problems = []
    want = spec_from_mockup()
    if len(want) < 70:
        problems.append(f"only {len(want)} SPEC names read from the mockup")
    lua = base.boot()
    spec_table = lua.eval("__checks")["zz_dump"]().Spec
    for name, value in want.items():
        got = spec_table[name]
        if got is None:
            problems.append(f"{name} missing from ConfigSpec.lua")
        elif float(got) != value:
            problems.append(f"{name}: mockup {value}, ConfigSpec.lua {got}")
    return problems


def proto_pages() -> dict[str, list[str]]:
    src = (MOCKUPS / "proto-src-2026-11-25" / "proto-pages.js").read_text(encoding="utf-8")
    start = src.index("const PAGES = [")
    end = src.index("const ROWS=", start)
    block = src[start:end]
    pages: dict[str, list[str]] = {}
    for chunk in re.split(r"\n \{key:'", block)[1:]:
        key = chunk.split("'", 1)[0]
        pages[key] = re.findall(r"\{key:'([a-zA-Z0-9]+)',label:'[^']*',secs:", chunk)
    return pages


# Prototype pages that a later ticket registers (a stub file owns the page until then).
OWNED_BY_STUB = {"modules": "Modules/Config/ConfigModules.lua"}


def check_every_prototype_page_and_tab_exists() -> list[str]:
    problems = []
    lua = base.boot()
    cats = lua.eval("__checks")["zz_dump"]().Categories()
    have = {c["key"]: [t["key"] for t in c["tabs"].values()] for c in cats.values()}
    expected = proto_pages()
    if len(expected) < 20:
        problems.append(f"only {len(expected)} prototype pages parsed")
    for key, tabs in expected.items():
        if key not in have:
            owner = OWNED_BY_STUB.get(key)
            if owner and (ROOT / "forever-stuwave" / owner).exists():
                continue
            problems.append(f"page {key} is not registered")
            continue
        for tab in tabs:
            if tab not in have[key]:
                problems.append(f"page {key}: tab {tab} is missing (have {have[key]})")
    return problems


STUBS = [
    "Core/ProfileCodec.lua", "Core/ModuleSwitch.lua", "Core/Role.lua", "Modules/Nameplates/PlateThreat.lua",
    "Modules/ActionBars/ShapeshiftTab.lua", "Modules/ActionBars/CallPetTab.lua", "Modules/ActionBars/PortalsTab.lua",
    "Modules/ActionBars/ConjureTab.lua", "Modules/ActionBars/PoisonsTab.lua", "Modules/ActionBars/DemonTab.lua",
    "Modules/Config/ConfigSearch.lua", "Modules/Config/ConfigFooter.lua", "Modules/Config/ConfigFlash.lua",
    "Modules/Config/ConfigTargets.lua", "Modules/Config/ConfigShare.lua", "Modules/Config/ConfigModules.lua",
    "Modules/Config/ConfigPageBars.lua",
]


def check_stub_files_are_in_the_toc_after_the_window() -> list[str]:
    problems = []
    toc = [ln.strip() for ln in (ROOT / "forever-stuwave" / "forever-stuwave.toc").read_text(encoding="utf-8").splitlines()
           if ln.strip() and not ln.startswith("##")]
    for stub in STUBS:
        path = ROOT / "forever-stuwave" / stub
        if not path.exists():
            problems.append(f"{stub} does not exist")
        elif stub not in toc:
            problems.append(f"{stub} is not in the toc")
        elif "local _, FS = ..." not in path.read_text(encoding="utf-8"):
            problems.append(f"{stub} lacks the standard header")
    needed = ["Modules/Config/ConfigSpec.lua", "Modules/Config/ConfigWindow.lua", "Modules/Config/ConfigBuilders.lua",
              "Modules/Config/ConfigPageUnitFrames.lua"]
    if all(name in toc for name in needed):
        order = [toc.index(n) for n in needed]
        if order != sorted(order):
            problems.append(f"Spec, Window, Builders, pages must load in that order: {order}")
        window = toc.index("Modules/Config/ConfigWindow.lua")
        for stub in STUBS:
            if stub.startswith("Modules/Config/") and stub in toc and toc.index(stub) < window:
                problems.append(f"{stub} loads before ConfigWindow.lua")
    else:
        problems.append("a core Config file is not in the toc")
    return problems


# What the first release's window referenced: every module group still has a home, and the four literal saved keys
# still exist. A module that is not in this list was never on the old window.
OLD_KEYS = ["actionbars.grid", "professions.shown", "unitFrames.hidePlayer", "unitFrames.hideTarget"]
OLD_MODULES = [
    "AmmoTab", "BuffTab", "CharBackdrop", "CharacterExport", "ChatFormat", "ClassModuleHelp", "DamageMeterSkin",
    "DruidClearcasting", "FiveSecondTab", "Gunsight", "GunsightAreas", "GunsightBoxes", "GunsightDots", "GunsightTags",
    "HudAlerts", "LossOfControl", "MicroBars", "MinimapCoords", "NameplateCombo", "Nameplates", "PartyFrames",
    "PriestRight", "QuestSkin", "QuestTimer", "RaidFrames", "SpellArt", "TalentBackdrops", "ThunderClapTab",
    "TotemPresets", "WarlockState", "WarriorPowerUps",
]


def check_no_saved_setting_lost() -> list[str]:
    problems = []
    cfg = ROOT / "forever-stuwave" / "Modules" / "Config"
    text = "\n".join(p.read_text(encoding="utf-8") for p in cfg.glob("*.lua"))
    for key in OLD_KEYS:
        if f'"{key}"' not in text:
            problems.append(f"saved key {key} is not used by any Config file")
    for mod in OLD_MODULES:
        if not re.search(rf"\b{mod}\b", text):
            problems.append(f"module {mod} has no Config row any more")
    return problems


def check_no_em_dash_or_tape_in_config_files() -> list[str]:
    problems = []
    cfg = ROOT / "forever-stuwave" / "Modules" / "Config"
    for path in list(cfg.glob("*.lua")) + [ROOT / "forever-stuwave" / s for s in STUBS]:
        text = path.read_text(encoding="utf-8")
        if "—" in text or "–" in text:
            problems.append(f"{path.name}: an em or en dash")
        if re.search(r"\btape\b", text, re.I) and path.name != "HelpModules.lua":
            problems.append(f"{path.name}: the word tape")
    return problems


def main() -> int:
    failed = run_lua_checks()
    py_checks = [
        ("spec_matches_the_mockup", check_spec_matches_the_mockup),
        ("every_prototype_page_and_tab_exists", check_every_prototype_page_and_tab_exists),
        ("stub_files_are_in_the_toc_after_the_window", check_stub_files_are_in_the_toc_after_the_window),
        ("no_saved_setting_lost", check_no_saved_setting_lost),
        ("no_em_dash_or_tape_in_config_files", check_no_em_dash_or_tape_in_config_files),
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
