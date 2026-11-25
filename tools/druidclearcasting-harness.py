#!/usr/bin/env python3
"""Runs the real DruidClearcasting.lua (with the generated art manifest) headless against a mock client.

The Druid Clearcasting alert (design mockup "Druid Clearcasting alert", 2026-11-17: a seer's orb with the omen of the form, the
CLEARCASTING title and a drain bar) is a set of baked frame lists replayed by the module. These checks pin:

  * the data: out of combat the aura (by id, else by name) opens and closes it with its plain expiry; in combat a probe spell's
    plain cost reading 0 (after a plain cost above 0) opens it and a cost above 0 closes it; a secret cost or aura says nothing;
    an own cast just before it goes is the cast exit, Wrath is not; an omen gone at its end is the expiry exit; Omen of Clarity
    readably not known reads and draws nothing;
  * the flows per form (bear, cat, the moon for every other form): enter then held, the last 3 s amber, the exits, a form
    change while it is up plays the new form's entrance, the drain bar's fill follows the remaining time;
  * the switch and Gunsight.IsActive() false hide it; other classes build nothing; the /fsedit seat and static preview;
  * the OnUpdate runs only while an alert plays or in combat with the omen known, nothing allocates per tick, the texture stack
    keeps the baked back to front order;
  * REPLAY: sampled frames of every sequence, played through the real module, composite to the same pixels as the baked lists;
  * the generator rewrites the committed texture and manifest byte for byte.

    python3 tools/druidclearcasting-harness.py [--png debug/druid-clearcasting]

`--png PREFIX` also writes PREFIX-<kind>.png, the mockup's strip frames of each form played through the module (2 px per
sprite px, over the dark ground). Exit 0 = every check passed.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ROOT = Path(__file__).resolve().parent.parent
CH = ROOT / "forever-stuwave/Modules/CombatHud"
ART = (CH / "DruidClearcastingArt.lua").read_text(encoding="utf-8")
MODULE = (CH / "DruidClearcasting.lua").read_text(encoding="utf-8")
TOC = (ROOT / "forever-stuwave/forever-stuwave.toc").read_text(encoding="utf-8")
LAYOUT = (ROOT / "forever-stuwave/Core/Layout.lua").read_text(encoding="utf-8")
LAYOUTEDIT = (ROOT / "forever-stuwave/Core/LayoutEdit.lua").read_text(encoding="utf-8")
CONFIGWINDOW = (ROOT / "forever-stuwave/Modules/Config/ConfigPageClassModules.lua").read_text(encoding="utf-8")
MEDIA = ROOT / "forever-stuwave/Media/Textures"
BG = (10, 4, 22)
GW, GH, SPX = 150, 96, 2.5
KINDS = ("bear", "cat", "moon")
FORM = {"bear": "bear", "cat": "cat", "moon": "caster"}

MOCK = r"""
local Obj = {}
Obj.__index = function(t, k)
    local v = rawget(Obj, k)
    if v ~= nil then return v end
    if type(k) == "string" and k:match("^%u") then return function() end end
end
function New(kind) return setmetatable({ kind = kind, shown = true, level = 0 }, Obj) end
function Obj:SetPoint(p, rel, rp, x, y) self.np = (self.np or 0) + 1; self.px, self.py, self.prel, self.has = x or 0, y or 0, rel, true end
function Obj:ClearAllPoints() self.has = false end
function Obj:SetAllPoints(rel) self.allpoints = rel end
function Obj:SetSize(w, h) self.w, self.h = w, h end
function Obj:Show() self.shown = true end
function Obj:Hide() self.shown = false end
function Obj:IsShown() return self.shown end
function Obj:SetFrameLevel(n) self.level = n end
function Obj:GetFrameLevel() return self.level end
function Obj:SetFrameStrata(s) self.strata = s end
function Obj:EnableMouse(b) self.mouse = b end
function Obj:SetScript(n, fn) self.scripts = self.scripts or {}; self.scripts[n] = fn end
function Obj:GetScript(n) return self.scripts and self.scripts[n] end
function Obj:RegisterEvent(e) self.events = self.events or {}; self.events[e] = true end
function Obj:UnregisterAllEvents() self.events = {} end
function Obj:SetTexture(p, ...) self.tex = p; self.filter = select(3, ...) end
function Obj:SetTexCoord(l, r, t, b) self.l, self.r, self.t, self.b = l, r, t, b end
function Obj:CreateTexture(name, layer, template, sub)
    local t = New("Texture"); t.layer, t.sub, t.parent = layer, sub or 0, self; t.shown = true
    __textures[#__textures + 1] = t
    return t
end
__textures, __frames = {}, {}
UIParent = New("Frame")
function CreateFrame(kind, name, parent)
    local f = New("Frame"); f.name = name; f.parent = parent
    __frames[#__frames + 1] = f
    if name then _G[name] = f end
    return f
end
__now = 1000
function GetTime() return __now end
__class = "DRUID"
function UnitClass() return "Druid", __class, 11 end
__combat = false
function InCombatLockdown() return __combat end
local Deny = function() error("a secret value was used") end
SECRET = setmetatable({}, { __lt = Deny, __le = Deny, __add = Deny, __sub = Deny, __mul = Deny, __div = Deny, __concat = Deny,
    __len = Deny, __index = Deny, __call = Deny, __eq = Deny })
-- the player's Clearcasting aura: nil (none), a table, or SECRET; readable only out of combat
__aura = nil
__byIdWorks = true
__names = { [5176] = "Wrath", [6807] = "Maul", [5221] = "Shred", [8921] = "Moonfire" }
-- each probe's cost entry is built once, so a read allocates nothing in the module's tick
__costs = { Maul = 15, Swipe = 20, Shred = 60, Claw = 45, Rake = 40, Moonfire = 25, ["Healing Touch"] = 55, Rejuvenation = 25, Starfire = 95 }
__costTables = {}
for name in pairs(__costs) do __costTables[name] = { { type = 0, cost = 0 } } end
C_Spell = {
    GetSpellName = function(id) return __names[id] end,
    GetSpellPowerCost = function(name)
        local v = __costs[name]
        if v == nil then return nil end
        if v == SECRET then return SECRET end
        local t = __costTables[name]; t[1].cost = v; return t
    end,
}
C_UnitAuras = {
    GetPlayerAuraBySpellID = function(id) if not __byIdWorks then return nil end assert(id == 16870); return __aura end,
    GetAuraDataBySpellName = function(unit, name) assert(name == "Clearcasting"); return __aura end,
}
__timers = {}
C_Timer = { After = function(s, fn) __timers[#__timers + 1] = fn end }
function RunTimers() local t = __timers; __timers = {}; for _, fn in ipairs(t) do fn() end end
__known = { ["Omen of Clarity"] = true }
__form = "bear"
__dsfn = {}
__cfg, __cfgfn = {}, {}
__gun = true
__gunfn, __ready = {}, nil
__edit, __editfn = false, {}
__applied, __rescale = {}, {}
__readfn = {}
FS = {
    IsSecret = function(v) return v == SECRET end,
    LogDegradeOnce = function(k, m) __logged = __logged or {}; __logged[k] = m end,
    AurasReadable = function() return not __combat end,
    OnAurasReadable = function(fn) __readfn[#__readfn + 1] = fn end,
    FrameHelpers = {
        ResolveSpell = function(name) if not __known[name] then return nil end return 1 end,
        IsKnownSpellId = function() return true end,
        RegisterEvent = function(f, e) f.events = f.events or {}; f.events[e] = true end,
    },
    DruidState = {
        Start = function() __dsStarted = true end,
        Form = function() return __form end,
        Subscribe = function(fn) __dsfn[#__dsfn + 1] = fn end,
    },
    Config = {
        defaults = {},
        RegisterDefault = function(k, v) FS.Config.defaults[k] = v end,
        Get = function(k) local v = __cfg[k]; if v == nil then return FS.Config.defaults[k] end return v end,
        Set = function(k, v) __cfg[k] = v; for _, fn in ipairs(__cfgfn[k] or {}) do fn() end end,
        OnChange = function(k, fn) __cfgfn[k] = __cfgfn[k] or {}; table.insert(__cfgfn[k], fn) end,
    },
    Gunsight = {
        IsActive = function() return __gun end,
        OnActiveChanged = function(fn) __gunfn[#__gunfn + 1] = fn end,
        OnReady = function(fn) __ready = fn end,
    },
    Layout = {
        Scale = function() return __scale or 1 end,
        Apply = function(frame, id) __applied[#__applied + 1] = id; frame.layoutId = id end,
        OnRescale = function(fn) __rescale[#__rescale + 1] = fn end,
    },
    LayoutEdit = {
        IsEditing = function() return __edit end,
        OnEditChanged = function(fn) __editfn[#__editfn + 1] = fn end,
    },
}
function SetGun(v) __gun = v; for _, fn in ipairs(__gunfn) do fn(v) end end
function SetEdit(v) __edit = v; for _, fn in ipairs(__editfn) do fn(v) end end
assert(loadstring(ART_SRC, "@DruidClearcastingArt.lua"))("forever-stuwave", FS)
assert(loadstring(MODULE_SRC, "@DruidClearcasting.lua"))("forever-stuwave", FS)
CC, Art = FS.DruidClearcasting, FS.DruidClearcastingArt
BOOT = __frames[#__frames]
function Boot() BOOT.scripts.OnEvent(BOOT, "PLAYER_LOGIN"); return CC.Init() end
function Ev(e, ...) CC._OnEvent(e, ...) end
function Driver() return CC._driver() end
function Driving() local d = Driver(); return d ~= nil and d.scripts ~= nil and d.scripts.OnUpdate ~= nil end
function Tick(dt) __now = __now + dt; local d = Driver(); local fn = d and d.scripts and d.scripts.OnUpdate; if fn then fn(d, dt) end end
function TickFor(sec) local n = math.floor(sec * 30 + 0.5) for _ = 1, n do Tick(1 / 30) end end
function State() local k, s, i, p, d = CC._state(); return k, s, i, p end
function Root() return CC._root() end
function RootShown() local r = Root(); return r ~= nil and r.shown == true end
function VisibleCount() local n = 0 for _, t in ipairs(__textures) do if t.shown then n = n + 1 end end return n end
function Form(f) __form = f; for _, fn in ipairs(__dsfn) do fn("form") end; Ev("UPDATE_SHAPESHIFT_FORM") end
-- out of combat: the aura appears (15 s) or goes, then the client's UNIT_AURA
__auraT = { expirationTime = 0 }
function Proc(sec) __auraT.expirationTime = __now + (sec or 15); __aura = __auraT; Ev("UNIT_AURA", "player") end
function Gone() __aura = nil; Ev("UNIT_AURA", "player") end
function Cast(id) Ev("UNIT_SPELLCAST_SUCCEEDED", "player", "x", id) end
function Fight(on) __combat = on; Ev(on and "PLAYER_REGEN_DISABLED" or "PLAYER_REGEN_ENABLED") end
function Run(maxSec, pred) for _ = 1, math.floor(maxSec * 30) do Tick(1 / 30); if pred() then return true end end return false end
LAYER_IDX = { BACKGROUND = 1, BORDER = 2, ARTWORK = 3, OVERLAY = 4 }
function Dump()
    local rows = {}
    for _, t in ipairs(__textures) do
        if t.shown and t.has and t.w then
            rows[#rows + 1] = { lvl = t.parent.level, layer = LAYER_IDX[t.layer], sub = t.sub, l = t.l, r = t.r, t = t.t, b = t.b,
                w = t.w, h = t.h, x = t.px, y = -t.py, tex = t.tex }
        end
    end
    table.sort(rows, function(a, b)
        if a.lvl ~= b.lvl then return a.lvl < b.lvl end
        if a.layer ~= b.layer then return a.layer < b.layer end
        return a.sub < b.sub
    end)
    return rows
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("the_config_preview_loops_enter_hold_exit_gap_and_stops_on_hide_and_in_combat", """
    assert(Boot() == true)
    local P = CC.Preview
    assert(P.Show() == true, "the preview comes up")
    assert(P.Phase() == "enter", "it starts with the real enter animation")
    local d = P.Driver()
    assert(d and d.scripts.OnUpdate, "the loop has a driver")
    local seen, shownAtHold = {}, nil
    local function step(sec)
        for _ = 1, math.floor(sec * 30 + 0.5) do
            local ph = P.Phase()
            if d.scripts.OnUpdate then d.scripts.OnUpdate(d, 1 / 30) end
            if P.Phase() then seen[P.Phase()] = true end
        end
    end
    step(4)
    assert(seen.enter and seen.hold and seen.exit and seen.gap, "ignite, hold, exit and gap all ran")
    step(6)
    assert(P.Phase() ~= nil, "and it keeps repeating")
    P.Hide()
    assert(P.Phase() == nil and not d.scripts.OnUpdate, "the loop stops on hide")
    assert(not RootShown(), "and the alert is down")
    InCombatLockdown = function() return true end
    assert(P.Show() == false and P.Phase() == nil, "nothing loops in combat")
    InCombatLockdown = nil
""")

case("builds_for_druids_only", """
    __class = "WARRIOR"
    assert(Boot() == false)
    assert(Root() == nil and #__applied == 0 and #__textures == 0 and #__editfn == 0)
    __class = SECRET
    assert(CC.Applies() == false)
""")

case("a_druid_builds_a_hidden_plain_frame_seated_by_the_layout", """
    assert(Boot() == true)
    local r = Root()
    assert(r and r.name == "ForeverSTUwaveDruidClearcasting" and r.parent == UIParent and r.layoutId == "druidclearcasting")
    assert(r.shown == false and r.strata == "MEDIUM" and r.mouse == false)
    assert(#__applied == 1 and VisibleCount() == 0 and not Driving())
    assert(__dsStarted and #__editfn == 1 and #__rescale == 1)
""")

for _kind in KINDS:
    case(f"{_kind}_the_aura_opens_enter_then_held_and_the_bar_drains", f"""
        __form = "{FORM[_kind]}"
        Boot()
        Proc(15)
        local k, s, i = State()
        assert(k == "{_kind}" and s == "enter" and i == 1, tostring(k) .. tostring(s))
        assert(RootShown() and Driving() and VisibleCount() > 3)
        TickFor(2)
        k, s = State()
        assert(k == "{_kind}" and s == "held", tostring(s))
        local want = math.floor(13 / 15 * 98 + 0.5)
        local fill = Art.KIND.{_kind}.fill
        for n = 1, 3 do
            local t = __textures[fill[n]]
            assert(t.shown and t.has, "fill slot " .. n)
            assert(math.abs(t.w / 2.5 - want) <= 1, t.w / 2.5 .. " vs " .. want)
        end
    """)

case("travel_and_other_forms_show_the_moon", """
    __form = "travel"
    Boot()
    Proc(15)
    assert(State() == "moon")
""")

case("the_last_three_seconds_are_amber_and_the_end_plays_the_expiry_exit", """
    Boot()
    Proc(15)
    TickFor(11.8)
    assert(select(2, State()) == "held")
    assert(Run(0.4, function() return select(2, State()) == "amber" end))
    TickFor(2.9)
    Gone()
    assert(select(2, State()) == "exp", tostring(select(2, State())))
    TickFor(1)
    assert(State() == nil and not RootShown() and not Driving())
""")

case("the_omen_runs_out_by_its_clock_when_no_event_comes", """
    Boot()
    Proc(15)
    TickFor(14.9)
    __aura = nil                                 -- gone without a UNIT_AURA: the 0.2 s read finds it
    assert(Run(0.5, function() return select(2, State()) == "exp" end))
""")

case("an_own_cast_spends_it_and_plays_the_cast_exit", """
    Boot()
    Proc(15)
    TickFor(3)
    Cast(6807)
    Gone()
    assert(select(2, State()) == "cast", tostring(select(2, State())))
    TickFor(1)
    assert(State() == nil and not Driving())
""")

case("a_free_spell_gone_early_with_no_cast_seen_is_spent_too", """
    Boot()
    Proc(15)
    TickFor(5)
    Gone()
    assert(select(2, State()) == "cast")
""")

case("wrath_does_not_spend_it", """
    __form = "caster"
    Boot()
    Proc(15)
    TickFor(4)
    Cast(5176)
    RunTimers()
    TickFor(0.5)
    assert(State() == "moon" and select(2, State()) == "held")
""")

case("a_refreshed_aura_restarts_the_entrance", """
    Boot()
    Proc(15)
    TickFor(6)
    Proc(15)
    assert(select(2, State()) == "enter")
    assert(math.abs(CC.Remaining(__now) - 15) < 0.01)
""")

case("in_combat_a_zero_cost_opens_it_and_a_cost_closes_it", """
    Boot()
    Ev("PLAYER_ENTERING_WORLD")                  -- out of combat: the probes' costs are learned
    Fight(true)
    assert(Driving(), "in combat with the omen known: the read poll runs")
    assert(State() == nil)
    __costs.Maul = 0
    assert(Run(0.3, function() return State() == "bear" end))
    assert(math.abs(CC.Remaining(__now) - 15) < 0.3)
    TickFor(4)
    Cast(6807)
    __costs.Maul = 15
    assert(Run(0.3, function() return select(2, State()) == "cast" end))
    TickFor(1)
    assert(State() == nil and Driving(), "still in combat: the poll goes on")
    Fight(false)
    assert(not Driving())
""")

case("in_combat_a_zero_cost_never_seen_with_a_price_says_nothing", """
    __costs.Maul, __costs.Swipe = 0, 0           -- free before any cost was ever seen
    Boot()
    Fight(true)
    TickFor(1)
    assert(State() == nil)
""")

case("secret_costs_and_auras_are_never_compared", """
    Boot()
    Ev("PLAYER_ENTERING_WORLD")
    __aura = SECRET
    Ev("UNIT_AURA", "player")
    assert(State() == nil)
    __aura = nil
    Fight(true)
    for k in pairs(__costs) do __costs[k] = SECRET end
    TickFor(1)
    assert(State() == nil and __logged == nil, tostring(__logged and next(__logged)))
""")

case("a_secret_cost_keeps_an_open_omen_until_its_clock_ends", """
    Boot()
    Ev("PLAYER_ENTERING_WORLD")
    Fight(true)
    __costs.Maul = 0
    TickFor(0.3)
    assert(State() == "bear")
    __costs.Maul, __costs.Swipe = SECRET, SECRET
    TickFor(10)
    assert(State() == "bear")
    assert(Run(6, function() return select(2, State()) == "exp" end))
""")

case("not_learned_reads_and_draws_nothing", """
    __known["Omen of Clarity"] = false
    Boot()
    Proc(15)
    assert(State() == nil and not RootShown())
    Fight(true)
    assert(not Driving(), "no poll without the talent")
""")

case("the_aura_by_name_when_the_id_read_has_none", """
    __byIdWorks = false
    Boot()
    Proc(15)
    assert(State() == "bear")
""")

case("a_form_change_plays_the_new_forms_entrance_with_the_time_left", """
    Boot()
    Proc(15)
    TickFor(5)
    Form("cat")
    local k, s = State()
    assert(k == "cat" and s == "enter", tostring(k) .. tostring(s))
    TickFor(2)
    assert(math.abs(CC.Remaining(__now) - 8) < 0.1)
""")

case("the_switch_and_the_gunsight_hide_it", """
    Boot()
    Proc(15)
    TickFor(0.5)
    FS.Config.Set("gunsight.druid.clearcasting", false)
    assert(State() == nil and not RootShown())
    FS.Config.Set("gunsight.druid.clearcasting", true)
    assert(State() == "bear")
    SetGun(false)
    assert(State() == nil and not RootShown())
    SetGun(true)
    assert(State() == "bear" and RootShown())
""")

case("the_layout_editor_shows_a_static_bear_frame", """
    Boot()
    SetEdit(true)
    assert(RootShown() and VisibleCount() > 20)
    assert(State() == nil and not Driving())
    local before = VisibleCount()
    TickFor(1)
    assert(VisibleCount() == before)
    Proc(15)
    assert(State() == nil, "no live alert while the editor is on")
    SetEdit(false)
    assert(State() == "bear" and RootShown())
""")

case("a_tick_allocates_nothing", """
    if jit then jit.off() end
    Boot()
    Proc(15)
    TickFor(9)                                  -- the 1.6 s entrance and more than one 6.8 s loop warm every slot
    collectgarbage("collect"); collectgarbage("stop")
    local a = collectgarbage("count")
    for _ = 1, 60 do Tick(1 / 30) end
    local b = collectgarbage("count")
    collectgarbage("restart")
    assert(select(2, State()) == "held")
    assert(b - a < 1, "a tick allocated " .. (b - a) .. " KB over 60 ticks")
    Fight(true)
    Gone()
    TickFor(1)
    collectgarbage("collect"); collectgarbage("stop")
    a = collectgarbage("count")
    for _ = 1, 60 do Tick(1 / 30) end            -- the in combat cost poll
    b = collectgarbage("count")
    collectgarbage("restart")
    assert(b - a < 1, "the combat poll allocated " .. (b - a) .. " KB")
""")

case("the_texture_stack_keeps_the_baked_order_and_filters_nearest", """
    Boot()
    local lastKey = -1
    for i, t in ipairs(__textures) do
        local key = t.parent.level * 1000 + LAYER_IDX[t.layer] * 20 + (t.sub + 8)
        assert(key > lastKey, "slot " .. i)
        lastKey = key
    end
    local most = 0
    for _, s in pairs(Art.KIND) do most = math.max(most, s.slots) end
    assert(#__textures == most)
    Proc(15)
    TickFor(1)
    for _, t in ipairs(__textures) do
        if t.tex then assert(t.tex:find("druid_clearcasting_%d+%.tga$") and t.filter == "NEAREST", tostring(t.tex)) end
    end
""")


def static_checks() -> list[str]:
    errs: list[str] = []
    toc = [line.strip() for line in TOC.splitlines()]
    try:
        order = [toc.index(f"Modules/CombatHud/{n}.lua") for n in ("DruidState", "DruidClearcastingArt", "DruidClearcasting")]
        if order != sorted(order):
            errs.append("the toc must load DruidState, DruidClearcastingArt, DruidClearcasting in that order")
    except ValueError:
        errs.append("the toc does not list DruidClearcastingArt.lua and DruidClearcasting.lua")
    if not re.search(r'id = "druidclearcasting",\s+label = "[^"]+"', LAYOUTEDIT):
        errs.append("LayoutEdit.lua has no MOVABLE entry for druidclearcasting")
    m = re.search(r'druidclearcasting = \{ point = "CENTER", relPoint = "CENTER", x = (-?\d+), y = (-?\d+), w = (\d+), h = (\d+)', LAYOUT)
    if not m:
        errs.append("Layout.lua has no druidclearcasting entry")
    elif (int(m.group(3)), int(m.group(4))) != (375, 240):
        errs.append("the druidclearcasting entry must be 375 x 240 (150 x 96 sprite px at 2.5)")
    if "FS.DruidClearcasting" not in CONFIGWINDOW or "CC.SETTING.key" not in CONFIGWINDOW:
        errs.append("ConfigPageClassModules.lua does not build the Druid alert group")
    for needle in ("COMBAT_LOG_EVENT_UNFILTERED", "CreateFrame(\"Button\"", "SecureActionButton", "SecureHandler"):
        for line in MODULE.splitlines():
            if needle in line and not line.lstrip().startswith("--"):
                errs.append(f"DruidClearcasting.lua must not use {needle}")
    for word in ("bot", "automation", "macro"):
        if re.search(rf"\b{word}\b", MODULE.lower()) or re.search(rf"\b{word}\b", ART.lower()):
            errs.append(f"client visible text mentions '{word}'")
    for name, w, h in re.findall(r'\{ file = "(\w+)", w = (\d+), h = (\d+) \}', ART):
        path = MEDIA / f"{name}.tga"
        if not path.exists():
            errs.append(f"missing texture {name}.tga (run tools/assets/generate_druid_clearcasting.py)")
        elif path.stat().st_size != 18 + int(w) * int(h) * 4:
            errs.append(f"{name}.tga is {path.stat().st_size} bytes, the manifest says {w} x {h}")
    return errs


def generator_is_deterministic() -> list[str]:
    errs: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, FS_ASSET_OUTPUT_DIR=tmp, FS_ART_LUA_OUTPUT=str(Path(tmp) / "DruidClearcastingArt.lua"))
        run = subprocess.run([sys.executable, str(ROOT / "tools/assets/generate_druid_clearcasting.py")], env=env,
                             capture_output=True, text=True)
        if run.returncode != 0:
            return [f"the generator failed: {run.stderr.strip().splitlines()[-1:]}"]
        if (Path(tmp) / "DruidClearcastingArt.lua").read_bytes() != (CH / "DruidClearcastingArt.lua").read_bytes():
            errs.append("DruidClearcastingArt.lua is not what the generator writes (regenerate it)")
        for tga in sorted(Path(tmp).glob("druid_clearcasting_*.tga")):
            committed = MEDIA / tga.name
            if not committed.exists() or committed.read_bytes() != tga.read_bytes():
                errs.append(f"{tga.name} is not what the generator writes (regenerate it)")
    return errs


def new_runtime():
    rt = LuaRuntime(unpack_returned_tuples=False)
    g = rt.globals()
    g.ART_SRC, g.MODULE_SRC = ART, MODULE
    rt.execute(MOCK)
    return rt


def run_case(body: str) -> str | None:
    try:
        rt = new_runtime()
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


# ----------------------------------------------------------------------------------------------------------------------
# Replay: the real module against the baked lists
# ----------------------------------------------------------------------------------------------------------------------
def load_manifest():
    import numpy as np
    from PIL import Image
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.execute("function load(src) local FS = {}; assert(loadstring(src, '@art'))('x', FS); return FS.DruidClearcastingArt end")
    art = rt.eval("load")(ART)
    sprites = [tuple(int(art.SPRITE[i][k]) for k in range(1, 6)) for i in range(1, len(art.SPRITE) + 1)]
    kinds = {}
    for name in KINDS:
        sp = art.KIND[name]
        seqs = {}
        for seq in ("enter", "held", "amber", "cast", "exp"):
            seqs[seq] = [[int(v) for v in sp.seqs[seq][i].values()] for i in range(1, len(sp.seqs[seq]) + 1)]
        kinds[name] = dict(slots=int(sp.slots), fill=[int(v) for v in sp.fill.values()], seqs=seqs)
    atlases = [np.asarray(Image.open(MEDIA / f"{art.ATLAS[i].file}.tga").convert("RGBA")) for i in range(1, len(art.ATLAS) + 1)]
    return sprites, kinds, atlases


def blit(canvas, atlas, sprite, x, y, width=None):
    import numpy as np
    _, tx, ty, w, h = sprite
    src = atlas[ty:ty + h, tx:tx + w].astype(float)
    if width is not None:
        src = np.repeat(src[:, :1], width, axis=1)
        w = width
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, GW), min(y + h, GH)
    if x1 <= x0 or y1 <= y0:
        return
    src = src[y0 - y:y1 - y, x0 - x:x1 - x]
    a = src[..., 3:4] / 255
    canvas[y0:y1, x0:x1] = src[..., :3] * a + canvas[y0:y1, x0:x1] * (1 - a)


def expected_image(sprites, kind, atlases, seq, idx):
    import numpy as np
    state: dict[int, tuple[int, int, int]] = {}
    frames = kind["seqs"][seq]
    for i in range(idx):
        flat = frames[i]
        for k in range(0, len(flat), 4):
            s, sid, x, y = flat[k:k + 4]
            if sid == 0:
                state.pop(s, None)
            else:
                state[s] = (sid, x, y)
    canvas = np.zeros((GH, GW, 3)) + BG
    for s in sorted(state):
        if s in kind["fill"]:
            continue
        sid, x, y = state[s]
        sp = sprites[sid - 1]
        blit(canvas, atlases[sp[0] - 1], sp, x, y)
    return canvas


def actual_image(rows, atlases, fill_tex=True):
    import numpy as np
    canvas = np.zeros((GH, GW, 3)) + BG
    for row in rows:
        n = int(re.search(r"druid_clearcasting_(\d+)\.tga$", row["tex"]).group(1))
        atlas = atlases[n - 1]
        aw, ah = atlas.shape[1], atlas.shape[0]
        tx, ty = round(row["l"] * aw), round(row["t"] * ah)
        w, h = round((row["r"] - row["l"]) * aw), round((row["b"] - row["t"]) * ah)
        x, y = round(row["x"] / SPX), round(row["y"] / SPX)
        if w == 1 and h == 1 and x == 26 and 90 <= y <= 92 and not fill_tex:
            continue                                   # the drain fill, drawn from the real remaining time
        wide = round(row["w"] / SPX) if w == 1 else None
        blit(canvas, atlas, (n, tx, ty, w, h), x, y, wide)
    return canvas


SAMPLE = 5
SHEET = [("enter", 5, "entrance 0.13 s"), ("enter", 11, "entrance 0.33 s"), ("enter", 17, "roar 0.53 s"), ("enter", 31, "title 1.0 s"),
         ("held", 7, "held 1.8 s"), ("held", 76, "held 4.1 s"), ("amber", 40, "amber"), ("cast", 4, "cast exit 0.10 s"),
         ("cast", 10, "cast exit 0.30 s"), ("exp", 7, "expiry exit 0.20 s"), ("exp", 13, "expiry exit 0.40 s")]
SHEET_WANT = {(seq, idx) for seq, idx, _ in SHEET}


def replay_checks(keep: dict | None = None) -> list[str]:
    """Plays each form's whole life (and one with a cast) and compares sampled frames of the real module with the baked lists
    (the drain fill aside: the module draws it from the real remaining time)."""
    import numpy as np
    sprites, kinds, atlases = load_manifest()
    errs: list[str] = []
    compared = 0
    for name in KINDS:
        kind = kinds[name]
        for mode in ("life", "cast"):
            rt = new_runtime()
            rt.execute(f'__form = "{FORM[name]}"; Boot(); Proc(15)')
            state, tick, dump = rt.eval("State"), rt.eval("Tick"), rt.eval("Dump")
            seen = set()
            for n in range(18 * 30):
                if mode == "cast" and n == 120:
                    rt.execute("Cast(6807); Gone()")
                if mode == "life" and n == 451:
                    rt.execute("Gone()")
                k, seq, idx, _ = state()
                if k is not None and (seq, idx) not in seen:
                    seq, idx = str(seq), int(idx)
                    seen.add((seq, idx))
                    if (seq, idx) in SHEET_WANT or seq not in ("held", "amber") or idx % SAMPLE == 0:
                        rows = dump()
                        rows = [{key: rows[i][key] for key in ("l", "r", "t", "b", "w", "h", "x", "y", "tex")} for i in range(1, len(rows) + 1)]
                        want = expected_image(sprites, kind, atlases, seq, idx)
                        got = actual_image(rows, atlases, fill_tex=False)
                        d = np.abs(want - got).max(axis=2)
                        compared += 1
                        if int((d > 1).sum()) > 0:
                            errs.append(f"{name} {mode} {seq} frame {idx}: {int((d > 1).sum())} px differ")
                        if keep is not None and (name, seq, idx) not in keep:
                            keep[(name, seq, idx)] = actual_image(rows, atlases)
                if k is None and n > 60:
                    break
                tick(1 / 30)
    if compared < 300:
        errs.append(f"only {compared} frames were compared")
    print(f"      replay compared {compared} frames")
    return errs


def png(prefix: str) -> None:
    from PIL import Image, ImageDraw
    keep: dict = {}
    replay_checks(keep)
    for name in KINDS:
        cols = 6
        rows = (len(SHEET) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * 300, rows * 210), (30, 20, 50))
        draw = ImageDraw.Draw(sheet)
        for n, (seq, idx, cap) in enumerate(SHEET):
            img = keep.get((name, seq, idx))
            if img is None:
                near = [k for k in keep if k[0] == name and k[1] == seq]
                if not near:
                    continue
                pick = min(near, key=lambda k: abs(k[2] - idx))
                img, cap = keep[pick], cap + f" (frame {pick[2]})"
            tile = Image.fromarray(img.round().clip(0, 255).astype("uint8")).resize((300, 192), Image.NEAREST)
            x, y = (n % cols) * 300, (n // cols) * 210
            sheet.paste(tile, (x, y + 16))
            draw.text((x + 4, y + 2), cap, fill=(200, 190, 230))
        out = f"{prefix}-{name}.png"
        sheet.save(out)
        print("wrote", out)


def main() -> int:
    failures = 0
    for err in static_checks():
        failures += 1
        print(f"FAIL  static: {err}")
    for name, body in CASES:
        err = run_case(body)
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}: {err}")
    total = len(CASES)
    errs = replay_checks()
    for e in errs[:20]:
        print(f"FAIL  replay: {e}")
    failures += len(errs)
    if not errs:
        print("ok    replay_matches_the_baked_lists")
    total += 1
    errs = generator_is_deterministic()
    for e in errs:
        print(f"FAIL  generator: {e}")
    failures += len(errs)
    if not errs:
        print("ok    generator_is_deterministic")
    total += 1
    print(f"{total - min(failures, total)}/{total} checks passed")
    if "--png" in sys.argv:
        prefix = sys.argv[sys.argv.index("--png") + 1]
        Path(prefix).parent.mkdir(parents=True, exist_ok=True)
        png(prefix)
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
