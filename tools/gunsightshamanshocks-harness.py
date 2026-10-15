#!/usr/bin/env python3
"""Runs the real GunsightShamanShocks.lua (the shock trace and the Fire Nova ring) headless.

The Shaman Gunsight Class Module (GunsightShaman.lua) owns the module frame and the totem poles; this file is the second
lane of Concept A "Totem Poles" (the design mockup, poleMod): the ground trace that
charges along the shared Earth / Flame / Frost Shock cooldown with the bolt and its RDY / seconds label at the end, the
cyan ring around the Fire totem head while Fire Nova is ready with the NOVA footer tag. It draws no KICK tag: that comes
from GunsightTape.lua's class neutral tag. GunsightShaman.lua calls it through FS.GunsightShamanShocks =
{ Build(frame), Seat(section, rect, scale), OnShow(section), OnHide(section) }. The harness builds the section on a plain
frame under a fake host, as GunsightShaman.lua does. The checks pin:

  * the table holds exactly Build, Seat, OnShow and OnHide; Build hangs everything under the frame it is given, installs
    no OnUpdate and listens only to the player's own casts (a ledger that stays on through OnHide);
  * every piece at the mockup's offset from the rect's top left (numbers read out of the mockup), in the upper and the
    lower area, re-seated on a rescale, a bad rect tolerated;
  * the shock trace: nothing without a shock, RDY with the bolt lit and the trace full when the shared cooldown is off (a
    plain isActive of false, or a cooldown that is only the global one), the plain seconds out of combat, the engine fill
    (SetTimerDuration with the duration object) while it charges, "~" and the cast ledger when the timing is secret in
    combat, "?" when even isActive is secret, any rank of any shock starting the shared cooldown;
  * secret values: not one is compared or computed on (the mock's secret raises), only handed to SetTimerDuration;
  * Fire Nova: nothing before it is learned (and it appears when it is), the ring and NOVA tag lit while it is ready, the
    tag dim and the ring gone on its cooldown, both gone when the poles say the Fire totem is down, the ring following the
    head the poles report;
  * no KICK tag and no target reads: the build makes none, and only the player's own casts and the view events listen;
  * OnHide stops the ticker and every view event, a cast while hidden is still ledgered, and OnShow re-reads everything;
  * the per frame path allocates nothing on the addon side.

The mock is strict. It is NOT the real client.

    python3 tools/gunsightshamanshocks-harness.py

Exit 0 = every check passed. GUNSIGHTSHAMANSHOCKS_LUA=<path> runs another file in place of GunsightShamanShocks.lua.
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
SHOCKS = Path(os.environ.get("GUNSIGHTSHAMANSHOCKS_LUA") or ADDON / "Modules/CombatHud/GunsightShamanShocks.lua")
GUNSIGHT = ADDON / "Modules/CombatHud/Gunsight.lua"
LAYOUT = ADDON / "Core/Layout.lua"
CONFIG = ADDON / "Core/Config.lua"
FRAMEHELPERS = ADDON / "Core/FrameHelpers.lua"
TOC = ADDON / "forever-stuwave.toc"
TEXTURES = ADDON / "Media" / "Textures"
MOCKUP = HERE.parent / "mockups" / "gunsight-class-module-shaman-2026-10-08.html"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CLASS_HARNESS = _load("gunsightclass-harness")


def _m(pattern: str, text: str, what: str) -> re.Match:
    m = re.search(pattern, text, re.S)
    if not m:
        sys.exit(f"mockup: cannot find {what} (pattern {pattern!r}); the mockup changed shape")
    return m


def mockup_numbers() -> dict:
    """The numbers poleMod draws for the shock trace, the bolt, the Nova ring and the NOVA footer, in image px."""
    src = MOCKUP.read_text(encoding="utf-8")
    pole = _m(r"function poleMod\(y0,st,an\)\{(.*?)\n\}", src, "poleMod").group(1)
    ground = _m(r"gy=y0\+(\d+),x0=(\d+),x1=(\d+)", pole, "ground line")
    trace = _m(r"var sx=x0,ex=(\d+),zy=gy\+(\d+),pts=\[\],px,k2=0;.*?px\+=(\d+)\).*?\?2\.5:-2\.5", pole, "trace")
    bolt = _m(r"bolt\((\d+),gy-(\d+),([\d.]+),ready\?bcol", pole, "bolt")
    label = _m(r"txt\((\d+),gy\+(\d+),\(S\.est&&!ready\?'~':''\)\+sl,(\d+)", pole, "shock label")
    ring = _m(r"circ\(m\.cap\.x,m\.cap\.y,(\d+),null,C\.cyan,\.95,1\.4,'3 3',true\)\+circ\(m\.cap\.x,m\.cap\.y,(\d+),null,C\.cyan,\.35,1\)",
              pole, "Nova ring")
    foot = _m(r"var fy=gy\+(\d+);.*?circ\((\d+),fy\+(\d+),4,null,C\.cyan,1,1\.2,'2 2',true\)\+txt\((\d+),fy\+(\d+),'NOVA',(\d+)", pole, "NOVA footer")
    px = _m(r"var PX=\{fire:\[(\d+),(\d+)\]", src, "pole x")
    bp = _m(r"var NB=(\d+),BP=(\d+),BH=(\d+);", src, "pole blocks")
    return {
        "GY": int(ground.group(1)), "X0": int(ground.group(2)),
        "TRACE_EX": int(trace.group(1)), "TRACE_DY": int(trace.group(2)),
        "BOLT_X": int(bolt.group(1)), "BOLT_DY": -int(bolt.group(2)), "BOLT_K": float(bolt.group(3)),
        "LABEL_X": int(label.group(1)), "LABEL_DY": int(label.group(2)), "LABEL_SIZE": int(label.group(3)),
        "RING_IN": int(ring.group(1)), "RING_OUT": int(ring.group(2)),
        "FOOT_DY": int(foot.group(1)), "PIP_X": int(foot.group(2)), "PIP_DY": int(foot.group(3)),
        "NOVA_X": int(foot.group(4)), "NOVA_BASE": int(foot.group(5)), "NOVA_SIZE": int(foot.group(6)),
        "FIRE_X": int(px.group(1)) + int(px.group(2)) // 2,
        "NB": int(bp.group(1)), "BP": int(bp.group(2)),
    }


def lua_value(v) -> str:
    if isinstance(v, dict):
        return "{" + ",".join(f"{k}={lua_value(x)}" for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        return "{" + ",".join(lua_value(x) for x in v) + "}"
    if isinstance(v, str):
        return '"' + v + '"'
    return repr(v)


# ---------------------------------------------------------------------------------------
# The mock client: the Class harness's strict mock (itself the Dots harness's), plus the spell, cooldown and cast APIs
# ---------------------------------------------------------------------------------------

MOCK = CLASS_HARNESS.MOCK + r"""
do
    -- a StatusBar driven by the engine's timer: it records the object it was given
    local create = CreateFrame
    function CreateFrame(kind, name, parent, template)
        local f = create(kind, name, parent, template)
        if kind == "StatusBar" then
            function f:SetTimerDuration(obj) self.timer = obj; self.timerCalls = (self.timerCalls or 0) + 1 end
        end
        return f
    end
end
"""

PRELUDE = r"""
RECTS = { upper = { x = 1213, y = 500, w = 202, h = 128 }, lower = { x = 1213, y = 632, w = 202, h = 128 } }
NAMES = { [8042] = "Earth Shock", [25454] = "Earth Shock", [8050] = "Flame Shock", [10447] = "Flame Shock", [8056] = "Frost Shock",
    [408341] = "Fire Nova", [403] = "Lightning Bolt", [1535] = "Fire Nova Totem" }
IDOF = { ["Earth Shock"] = 8042, ["Flame Shock"] = 8050, ["Frost Shock"] = 8056, ["Fire Nova"] = 408341 }
KNOWN = {}
CD, CD_CALLS, DUR_CALLS, DUR = {}, 0, 0, {}
USABLE = {}
local RESULT, INFO = {}, {}                       -- reused: the mock's own tables are not what the cases count
SECRET_FN = function(v) return v == SECRET end

local function mockSpells()
    C_Spell = {
        GetSpellInfo = function(x)
            local id = type(x) == "number" and x or IDOF[x]
            if not id or not NAMES[id] then return nil end
            if type(x) == "string" and not KNOWN[id] then return nil end    -- by name only a spell in the book answers
            INFO.name, INFO.spellID, INFO.iconID = NAMES[id], id, 1
            return INFO
        end,
        GetSpellName = function(id) return NAMES[id] end,
        GetSpellCooldown = function(id)
            CD_CALLS = CD_CALLS + 1
            local c = CD[id]
            if not c then return nil end
            RESULT.isActive, RESULT.isOnGCD, RESULT.startTime, RESULT.duration = c.isActive, c.isOnGCD, c.startTime, c.duration
            return RESULT
        end,
        GetSpellCooldownDuration = function(id)
            DUR_CALLS = DUR_CALLS + 1
            DUR[id] = DUR[id] or { durationFor = id }
            return DUR[id]
        end,
        IsSpellUsable = function(id)
            local u = USABLE[id]
            if u == nil then return true, false end
            return u[1], u[2]
        end,
    }
    IsPlayerSpell = function(id) return KNOWN[id] == true end
    IsSpellKnown = function(id) return KNOWN[id] == true end
end

local function learn(...)
    for _, name in ipairs({ ... }) do KNOWN[IDOF[name]] = true end
end
local function setCd(id, active, onGcd, start, dur) CD[id] = { isActive = active, isOnGCD = onGcd, startTime = start, duration = dur } end
local function cdReady(id) setCd(id, false, false, 0, 0) end
local function cdPlain(id, left, total) setCd(id, true, false, NOW - (total - left), total) end   -- out of combat: plain timing
local function cdSecret(id) setCd(id, true, false, SECRET, SECRET) end                           -- in combat: isActive plain, timing secret
local function cdBlind(id) setCd(id, SECRET, SECRET, SECRET, SECRET) end
local EARTH, FLAME, FROST, NOVA = 8042, 8050, 8056, 408341
-- every spell off cooldown unless a case says otherwise
local function allReady() for _, id in ipairs({ EARTH, FLAME, FROST, NOVA }) do cdReady(id) end end

local function boot(opts)
    opts = opts or {}
    STRICT_EVENTS = false
    resetKnownEvents()
    for e in ([[SPELL_UPDATE_COOLDOWN SPELLS_CHANGED LEARNED_SPELL_IN_SKILL_LINE PLAYER_LEVEL_UP UNIT_SPELLCAST_SUCCEEDED
        SPELL_UPDATE_USABLE PLAYER_REGEN_ENABLED PLAYER_REGEN_DISABLED]]):gmatch("%S+") do
        KNOWN_EVENTS[e] = true     -- any other event (a target cast, a target change) is refused and would be logged
    end
    resetWorld()
    SetScreen(opts.height or 1440)
    KNOWN, CD, USABLE, DUR = {}, {}, {}, {}
    CD_CALLS, DUR_CALLS = 0, 0
    NOW = 5000
    FS.IsSecret = function(v) return SECRET_FN(v) end
    stubTheme_()
    local T = FS.Theme
    T.COLOR_TEXT_WHITE = { 1, 1, 1, 1 }
    T.COLOR_POWER = { 0.133, 0.878, 1, 1 }
    T.COLOR_MUTED = { 0.6157, 0.5765, 0.7686, 1 }
    T.COLOR_HUD_SCRIM = { 0.051, 0.024, 0.125, 0.4675 }
    stubHud_()
    assert(loadstring(HAS_TARGET_SRC, "@Theme.lua"))()
    loadAddonFile(LAYOUT_SRC, "Core/Layout.lua")
    loadAddonFile(CONFIG_SRC, "Core/Config.lua")
    loadAddonFile(FRAMEHELPERS_SRC, "Core/FrameHelpers.lua")
    loadAddonFile(GUNSIGHT_SRC, "Modules/CombatHud/Gunsight.lua")
    UnitExists = function() return true end
    UnitClass = function() return "Shaman", "SHAMAN" end
    mockSpells()
    if opts.known ~= false then learn("Earth Shock", "Flame Shock", "Fire Nova") end
    if opts.ready ~= false then allReady() end
    FRAMES_BEFORE = #FRAMES
    loadAddonFile(SHOCKS_SRC, "Modules/CombatHud/GunsightShamanShocks.lua")
    Shocks = FS.GunsightShamanShocks
    fire("ADDON_LOADED", "forever-stuwave")
    fire("PLAYER_LOGIN")
end

-- Builds the section the way GunsightShaman.lua does: a plain frame under a host, then Build, Seat, OnShow
local function mount(area, opts)
    opts = opts or {}
    STRICT_EVENTS = true
    HOST = CreateFrame("Frame", nil, FS.Gunsight.root)
    HOST:SetSize(1, 1)
    FRAME = CreateFrame("Frame", nil, HOST)
    FRAME:SetAllPoints(HOST)
    local before = #FRAMES
    SEC = Shocks.Build(FRAME)
    check(type(SEC) == "table", "Build(frame) returned no section")
    BUILT = before
    AREA = area or "lower"
    Shocks.Seat(SEC, RECTS[AREA], 1.28)
    if opts.show ~= false then Shocks.OnShow(SEC) end
    return SEC
end

local function under(r, frame)
    while r do if r == frame then return true end; r = r.parent end
    return false
end
local function built()           -- the frames the module made, in creation order
    local list = {}
    for i = BUILT + 1, #FRAMES do list[#list + 1] = FRAMES[i] end
    return list
end
local function listeners()
    local n = 0
    for _, f in ipairs(FRAMES) do
        for _ in pairs(f.events) do n = n + 1 end
        if f.scripts.OnUpdate then n = n + 1 end
    end
    return n
end
local function onUpdates() return onUpdateFrames() end
local function noDegrade() check(next(DEGRADED) == nil, "a degrade was logged: " .. tostring(next(DEGRADED))) end
local function vis(r) return r ~= nil and isVisible(r) end
local function cyanTint(r)
    local v = r.vertex
    return math.abs(v[1] - 0.133) < 0.01 and math.abs(v[2] - 0.878) < 0.01 and math.abs(v[3] - 1) < 0.01
end
local function mutedTint(r)
    local v = r.vertex
    return math.abs(v[1] - 0.6157) < 0.01 and math.abs(v[2] - 0.5765) < 0.01
end
local function textRgb(fs) local c = fs.textColor; return c[1], c[2], c[3] end
local function cast(id, unit) fire("UNIT_SPELLCAST_SUCCEEDED", unit or "player", "guid", id) end
local function nearRect(r, x, y, w, h, what)
    local l, t, rw, rh = imgRect(r)
    near(l, x, what .. " left", 0.02); near(t, y, what .. " top", 0.02)
    if w then near(rw, w, what .. " width", 0.02) end
    if h then near(rh, h, what .. " height", 0.02) end
end
local CAP = 325 / 1024      -- Mononoki's line centre above the baseline, as GunsightSeals.lua uses it
"""

CASES: list[tuple[str, str]] = []


def case(name: str):
    def deco(body: str):
        CASES.append((name, body))
        return body
    return deco


case("the_table_holds_exactly_the_four_functions")(r"""
boot({})
local n = 0
for k, v in pairs(Shocks) do
    n = n + 1
    check(k == "Build" or k == "Seat" or k == "OnShow" or k == "OnHide", "unexpected key " .. tostring(k))
    check(type(v) == "function", tostring(k) .. " is not a function")
end
check(n == 4, "the table must hold exactly Build, Seat, OnShow and OnHide, has " .. n)
noDegrade()
""")

case("build_hangs_everything_under_the_frame_and_installs_no_ticker")(r"""
boot({})
local texBefore, strBefore = #TEXTURES, #FONTSTRINGS
local before = listeners()
mount("lower", { show = false })
check(#built() > 0, "Build made no frame")
for _, f in ipairs(built()) do check(under(f, FRAME), "a frame is not under the module frame") end
for i = texBefore + 1, #TEXTURES do check(under(TEXTURES[i], FRAME), "a texture is not under the module frame") end
for i = strBefore + 1, #FONTSTRINGS do check(under(FONTSTRINGS[i], FRAME), "a font string is not under the module frame") end
check(onUpdates() == 0, "no OnUpdate before the first show")
check(listeners() - before == 1, "only the player's own cast ledger listens before the first show, got " .. (listeners() - before))
for _, f in ipairs(built()) do
    check(not f:IsProtected(), "no protected frame")
end
check(SEC.kick == nil and SEC.kickLabel == nil, "no KICK tag of its own: GunsightTape.lua draws it")
noDegrade()
""")

case("nothing_is_drawn_without_a_shock_or_nova_in_the_book")(r"""
boot({ known = false })
mount("lower")
check(not vis(SEC.base) and not vis(SEC.bar) and not vis(SEC.ready) and not vis(SEC.glow), "no trace without a shock")
check(not vis(SEC.boltFill) and not vis(SEC.boltLine) and not vis(SEC.boltGlow), "no bolt without a shock")
check(not vis(SEC.label), "no label without a shock")
check(not vis(SEC.ring) and not vis(SEC.pip) and not vis(SEC.novaText), "no Nova pieces before Fire Nova is learned")
check(onUpdates() == 0, "nothing ticks")
noDegrade()
""")

case("a_ready_shock_lights_the_trace_the_bolt_and_says_RDY")(r"""
boot({})
mount("lower")
check(vis(SEC.base), "the dim trace is always drawn while a shock is known")
check(vis(SEC.ready) and cyanTint(SEC.ready), "the full cyan trace when ready")
check(vis(SEC.glow), "the trace glows when ready")
check(not vis(SEC.bar), "no charging fill when ready")
check(vis(SEC.boltFill) and cyanTint(SEC.boltFill) and vis(SEC.boltLine) and cyanTint(SEC.boltLine) and vis(SEC.boltGlow), "the bolt is lit cyan with its glow")
check(vis(SEC.label) and SEC.label.text == "RDY", "the label says RDY, got " .. tostring(SEC.label.text))
local r, g, b = textRgb(SEC.label)
check(math.abs(r - 0.133) < 0.01 and math.abs(b - 1) < 0.01, "RDY is cyan")
check(onUpdates() == 0, "a ready shock needs no ticker")
noDegrade()
""")

case("a_cooldown_that_is_only_the_global_one_reads_ready")(r"""
boot({})
setCd(8042, true, true, SECRET, SECRET)
mount("lower")
check(SEC.label.text == "RDY", "isOnGCD true is ready, got " .. tostring(SEC.label.text))
setCd(8042, true, false, NOW - 0.5, 1.5)
fire("SPELL_UPDATE_COOLDOWN")
check(SEC.label.text == "RDY", "a plain cooldown no longer than the global one is ready, got " .. tostring(SEC.label.text))
noDegrade()
""")

case("a_shock_on_cooldown_out_of_combat_shows_the_plain_seconds_and_charges_through_the_engine")(r"""
boot({})
cdPlain(8042, 4, 6)
mount("lower")
check(vis(SEC.base) and vis(SEC.bar), "the charging fill is drawn")
check(not vis(SEC.ready) and not vis(SEC.glow), "not the ready trace")
check(SEC.bar.timer ~= nil and SEC.bar.timer.durationFor == 8042, "the fill runs from the cooldown's duration object")
check(not vis(SEC.boltFill) or not cyanTint(SEC.boltFill) or SEC.boltFill.vertex[4] < 1, "the bolt body is dark while charging")
check(vis(SEC.boltLine) and cyanTint(SEC.boltLine), "the bolt keeps its cyan outline")
check(not vis(SEC.boltGlow), "no bolt glow while charging")
check(SEC.label.text == "4s", "plain seconds above 3 are whole, got " .. tostring(SEC.label.text))
local r = textRgb(SEC.label)
check(r > 0.9, "the seconds are white")
check(onUpdates() >= 1, "a charging shock ticks")
tick(1)
check(SEC.label.text == "3s", "one second later, got " .. tostring(SEC.label.text))
tick(0.8)
check(SEC.label.text == "2.2s", "under 3 s the tenths show, got " .. tostring(SEC.label.text))
cdReady(8042)
tick(2.2)
check(SEC.label.text == "RDY" and vis(SEC.ready), "the trace and label flip to ready when the cooldown ends, got " .. tostring(SEC.label.text))
check(not vis(SEC.bar), "the fill goes")
check(onUpdates() == 0, "and the ticker stops with nothing left to wait for")
noDegrade()
""")

case("the_charging_fill_falls_back_to_a_number_without_the_duration_object_api")(r"""
boot({})
cdPlain(8042, 3, 6)
C_Spell.GetSpellCooldownDuration = nil
mount("lower")
check(vis(SEC.bar) and SEC.bar.timer == nil, "no timer without the API")
near(SEC.bar.value, 0.5, "the fill is the elapsed share of the cooldown", 0.02)
tick(1.5)
near(SEC.bar.value, 0.75, "and it follows the clock", 0.05)
noDegrade()
""")

case("secret_timing_in_combat_uses_the_cast_ledger_and_marks_the_estimate")(r"""
boot({})
IN_COMBAT = true
mount("lower")
cdSecret(8042)
cast(25454)                                  -- Earth Shock rank 5: the client reports the rank id, the name is the key
check(SEC.label.text == "~6s", "just cast: an estimated 6 s, got " .. tostring(SEC.label.text))
check(vis(SEC.bar) and not vis(SEC.ready), "charging")
check(SEC.bar.timer ~= nil, "the engine still draws the fill from the duration object (a secret one is handed over untouched)")
tick(3)
check(SEC.label.text == "~3s", "got " .. tostring(SEC.label.text))
tick(1.5)
check(SEC.label.text == "~1.5s", "got " .. tostring(SEC.label.text))
tick(1.6)
check(SEC.label.text == "RDY" and vis(SEC.ready), "the ledger says elapsed: ready, got " .. tostring(SEC.label.text))
check(onUpdates() == 0, "ticker off")
noDegrade()
""")

case("a_plain_false_is_trusted_over_the_ledger_in_combat")(r"""
boot({})
IN_COMBAT = true
mount("lower")
cdSecret(8042)
cast(8042)
check(SEC.label.text == "~6s", "ledger charging")
cdReady(8042)                                -- a reset (or a cooldown the ledger did not know): the client says off
fire("SPELL_UPDATE_COOLDOWN")
check(SEC.label.text == "RDY", "a plain isActive of false is ready whatever the ledger says, got " .. tostring(SEC.label.text))
noDegrade()
""")

case("secret_active_flag_reads_unknown_and_guesses_nothing")(r"""
boot({})
IN_COMBAT = true
cdBlind(8042)
mount("lower")
check(vis(SEC.base), "the dim trace stays")
check(not vis(SEC.bar) and not vis(SEC.ready) and not vis(SEC.glow), "nothing charges or lights")
check(SEC.label.text == "?", "the label says ?, got " .. tostring(SEC.label.text))
local r, g, b = textRgb(SEC.label)
check(math.abs(r - 0.6157) < 0.01, "? is muted")
check(vis(SEC.boltLine) and mutedTint(SEC.boltLine) and not vis(SEC.boltGlow), "the bolt outline is muted and unlit")
noDegrade()
""")

case("a_secret_cooldown_value_is_never_computed_on")(r"""
boot({})
IN_COMBAT = true
mount("lower")
cdSecret(8042)
cast(8042)
for i = 1, 40 do tick(0.1) end               -- the mock's secret raises on any arithmetic or comparison; a throw would be logged
cdSecret(408341)
fire("SPELL_UPDATE_COOLDOWN")
cdBlind(408341); cdBlind(8042)
fire("SPELL_UPDATE_COOLDOWN")
noDegrade()
""")

case("any_rank_of_any_shock_starts_the_shared_cooldown_and_other_spells_do_not")(r"""
boot({})
IN_COMBAT = true
learn("Frost Shock")
mount("lower")
cdSecret(8042)
cast(403)                                    -- Lightning Bolt
check(SEC.label.text == "RDY", "another spell never starts the shock cooldown, got " .. tostring(SEC.label.text))
cast(10447)                                  -- Flame Shock rank 2
check(SEC.label.text == "~6s", "Flame Shock shares the cooldown, got " .. tostring(SEC.label.text))
cdReady(8042); fire("SPELL_UPDATE_COOLDOWN")
cdSecret(8042)
cast(8056)
check(SEC.label.text == "~6s", "Frost Shock too, got " .. tostring(SEC.label.text))
cast(8042, "target")                         -- somebody else's cast
cdSecret(8042); NOW = NOW + 7; tick(0.1)
check(SEC.label.text == "RDY", "elapsed, got " .. tostring(SEC.label.text))
cast(8042, "target")
check(SEC.label.text == "RDY", "a cast by another unit is not ours, got " .. tostring(SEC.label.text))
noDegrade()
""")

case("the_cooldown_length_is_learned_from_a_plain_read_that_started_at_our_cast")(r"""
boot({})
mount("lower")
cast(8042)
cdPlain(8042, 5, 5)                          -- a talent shortens the cooldown to 5 s
fire("SPELL_UPDATE_COOLDOWN")
check(SEC.label.text == "5s", "plain 5 s, got " .. tostring(SEC.label.text))
IN_COMBAT = true
cdSecret(8042)
cast(8042)
check(SEC.label.text == "~5s", "the ledger uses the learned 5 s, got " .. tostring(SEC.label.text))
noDegrade()
""")

case("fire_nova_appears_when_it_is_learned")(r"""
boot({ known = false })
learn("Earth Shock")
mount("lower")
check(not vis(SEC.ring) and not vis(SEC.pip) and not vis(SEC.novaText), "locked")
learn("Fire Nova")
fire("SPELLS_CHANGED")
check(vis(SEC.ring) and vis(SEC.pip) and vis(SEC.novaText), "the ring and the NOVA tag show once it is in the book")
noDegrade()
""")

case("a_ready_fire_nova_lights_the_ring_and_the_NOVA_tag")(r"""
boot({})
mount("lower")
check(vis(SEC.ring) and cyanTint(SEC.ring), "the ring is cyan")
check(vis(SEC.ringGlow), "with its glow")
check(vis(SEC.pip) and cyanTint(SEC.pip) and vis(SEC.novaText) and SEC.novaText.text == "NOVA", "the footer pip and the NOVA word")
local r, g, b = textRgb(SEC.novaText)
check(math.abs(r - 0.133) < 0.01 and math.abs(b - 1) < 0.01, "NOVA is cyan")
check(onUpdates() == 0, "a ready Nova needs no ticker")
noDegrade()
""")

case("fire_nova_on_cooldown_dims_the_tag_and_drops_the_ring")(r"""
boot({})
IN_COMBAT = true
mount("lower")
cdSecret(408341)
cast(408341)
check(not vis(SEC.ring) and not vis(SEC.ringGlow), "no ring while it cools down")
check(vis(SEC.pip) and mutedTint(SEC.pip) and vis(SEC.novaText), "the footer tag stays, muted")
check(onUpdates() >= 1, "ticks until it is ready")
tick(11)
check(vis(SEC.ring) and cyanTint(SEC.ring), "ready again once the ledger says elapsed")
check(onUpdates() == 0, "ticker off")
cdBlind(408341); fire("SPELL_UPDATE_COOLDOWN")
check(not vis(SEC.ring) and vis(SEC.pip) and mutedTint(SEC.pip), "unreadable: no ring, a muted tag")
noDegrade()
""")

case("the_poles_say_whether_the_fire_totem_is_up_and_where_its_head_is")(r"""
boot({})
mount("lower")
local c0x, c0y = imgCenter(SEC.ring)
near(c0x, 1213 + MU.FIRE_X - 1213, "the default ring centre x", 0.05)
near(c0y, 632 + MU.GY - MU.NB * MU.BP - 15 + 9, "the default ring centre y (a full pole's head)", 0.05)
SEC.SetFire(true, 40)
local x, y = imgCenter(SEC.ring)
near(y, 632 + 40, "the ring follows the head the poles report", 0.05)
SEC.SetFire(false)
check(not vis(SEC.ring) and not vis(SEC.ringGlow) and not vis(SEC.pip) and not vis(SEC.novaText), "no Fire totem: no ring, no NOVA tag")
SEC.SetFire(true, 30)
check(vis(SEC.ring) and vis(SEC.novaText), "back with the totem")
SEC.SetFire(true, "bad")
SEC.SetFire(nil)
noDegrade()
""")

case("the_ring_frame_has_a_rect_of_its_own_so_the_client_draws_its_textures")(r"""
boot({})
mount("lower")
local rf = SEC.ringFrame
check(rf and (rf:GetNumPoints() > 0 or rf.allPoints ~= nil), "a frame with no points has no rect on this client and draws nothing: the ring frame needs an anchor")
check(rf.allPoints == SEC.holder, "the ring frame fills the holder")
check(SEC.ring.parent == rf and SEC.ringGlow.parent == rf, "the ring and its glow are drawn by that frame")
check(vis(SEC.ring), "and the ring shows")
noDegrade()
""")

case("a_head_that_cannot_be_placed_hides_the_ring_and_keeps_the_NOVA_tag")(r"""
boot({})
mount("lower")
check(vis(SEC.ring) and vis(SEC.ringGlow), "the ring shows on a full head")
SEC.SetFire(true, false)
check(not vis(SEC.ring) and not vis(SEC.ringGlow), "headY false: the head's place is unknown, no ring")
check(vis(SEC.pip) and vis(SEC.novaText), "the Fire totem still stands: the NOVA tag stays")
SEC.SetFire(true, 40)
check(vis(SEC.ring) and vis(SEC.ringGlow), "a head with a place brings the ring back")
local _, y = imgCenter(SEC.ring)
near(y, 632 + 40, "at that place", 0.05)
SEC.SetFire(false, false)
check(not vis(SEC.ring) and not vis(SEC.pip) and not vis(SEC.novaText), "no Fire totem: nothing")
noDegrade()
""")

case("without_a_word_from_the_poles_an_unusable_nova_reads_as_no_fire_totem")(r"""
boot({})
USABLE[408341] = { false, false }
mount("lower")
check(not vis(SEC.ring) and not vis(SEC.novaText), "unusable for a reason other than mana: no totem, nothing shown")
USABLE[408341] = { false, true }
fire("SPELL_UPDATE_USABLE")
check(vis(SEC.ring), "no mana is not a missing totem")
USABLE[408341] = { SECRET, SECRET }           -- unreadable in combat: never a verdict
fire("SPELL_UPDATE_USABLE")
check(vis(SEC.ring), "a secret usability reads as a Fire totem that stands")
noDegrade()
""")

case("a_view_event_the_client_lacks_is_skipped_without_a_chat_line_and_the_rest_still_listen")(r"""
boot({})
KNOWN_EVENTS.SPELL_UPDATE_USABLE = nil
local printed = {}
print = function(...) printed[#printed + 1] = table.concat({ ... }, " ") end
ForeverSTUwaveDB = {}
mount("lower", { show = false })
Shocks.OnShow(SEC)
check(next(DEGRADED) == nil, "no chat line through the degrade path: " .. tostring(next(DEGRADED)))
check(#printed == 0, "nothing printed")
check(ForeverSTUwaveDB.unknownEvents and ForeverSTUwaveDB.unknownEvents.SPELL_UPDATE_USABLE, "the refused event is recorded in the saved variables")
local on = false
for _, f in ipairs(FRAMES) do if f.events.SPELL_UPDATE_COOLDOWN then on = true end end
check(on, "the events the client has are still on")
""")

case("a_cast_ledger_the_client_refuses_is_recorded_quietly")(r"""
boot({})
KNOWN_EVENTS.UNIT_SPELLCAST_SUCCEEDED = nil
local printed = {}
print = function(...) printed[#printed + 1] = table.concat({ ... }, " ") end
ForeverSTUwaveDB = {}
mount("lower", { show = false })
check(next(DEGRADED) == nil, "no chat line through the degrade path: " .. tostring(next(DEGRADED)))
check(#printed == 0, "nothing printed")
check(ForeverSTUwaveDB.unknownEvents and ForeverSTUwaveDB.unknownEvents.UNIT_SPELLCAST_SUCCEEDED, "recorded in the saved variables")
""")

case("OnHide_stops_the_ticker_and_every_view_event_but_the_ledger_stays")(r"""
boot({})
IN_COMBAT = true
mount("lower", { show = false })
local ledgerOnly = listeners()
Shocks.OnShow(SEC)
local showing = listeners()
check(showing > ledgerOnly, "showing listens to more than the ledger")
cdSecret(8042)
cast(8042)
check(onUpdates() >= 1, "charging ticks")
Shocks.OnHide(SEC)
check(onUpdates() == 0, "OnHide clears the ticker")
check(listeners() == ledgerOnly, "OnHide drops every view event, back to the ledger alone: " .. listeners() .. " vs " .. ledgerOnly)
local calls = CD_CALLS
fire("SPELL_UPDATE_COOLDOWN"); fire("SPELL_UPDATE_USABLE"); tick(2)
check(CD_CALLS == calls, "nothing reads a cooldown while hidden")
cast(8042)                                    -- a shock cast while hidden: only the ledger records it
check(CD_CALLS == calls, "the ledger records without reading the client")
Shocks.OnShow(SEC)
check(onUpdates() >= 1, "OnShow starts ticking again from a re-read")
check(SEC.label.text == "~6s" or SEC.label.text == "~5.9s", "the cast made while hidden is in the ledger, got " .. tostring(SEC.label.text))
noDegrade()
""")

case("OnShow_re_reads_the_spellbook_and_the_cooldown")(r"""
boot({ known = false })
mount("lower")
check(not vis(SEC.label), "nothing known at first")
Shocks.OnHide(SEC)
learn("Earth Shock", "Fire Nova")
cdPlain(8042, 4, 6)
Shocks.OnShow(SEC)
check(vis(SEC.label) and SEC.label.text == "4s", "learned while hidden: drawn on show, got " .. tostring(SEC.label.text))
check(vis(SEC.ring), "Fire Nova too")
noDegrade()
""")

case("a_shock_that_ends_while_hidden_reads_ready_on_show")(r"""
boot({})
cdPlain(8042, 4, 6)
mount("lower")
check(SEC.label.text == "4s", "charging")
Shocks.OnHide(SEC)
cdReady(8042)
NOW = NOW + 10
Shocks.OnShow(SEC)
check(SEC.label.text == "RDY", "got " .. tostring(SEC.label.text))
check(onUpdates() == 0, "nothing to tick")
noDegrade()
""")

for area, key in (("upper", "UPPER"), ("lower", "LOWER")):
    case(f"every_piece_sits_at_the_mockups_offset_in_the_{area}_area")(rf"""
boot({{}})
cdPlain(8042, 4, 6)
mount("{area}")
local R = RECTS["{area}"]
local gy = MU.GY
local k = MU.BOLT_K
-- the trace: x0 .. EX on the centre line gy + TRACE_DY, 162 x 20.25 (the canvas), the fill the same rect
local w = MU.TRACE_EX - MU.X0
nearRect(SEC.base, R.x + MU.X0 - 1213, R.y + gy + MU.TRACE_DY - 10.125, w, 20.25, "trace")
nearRect(SEC.bar, R.x + MU.X0 - 1213, R.y + gy + MU.TRACE_DY - 10.125, w, 20.25, "fill")
nearRect(SEC.ready, R.x + MU.X0 - 1213, R.y + gy + MU.TRACE_DY - 10.125, w, 20.25, "ready trace")
nearRect(SEC.glow, R.x + MU.X0 - 1213 - 8, R.y + gy + MU.TRACE_DY - 11.125, w + 16, 22.25, "trace glow")
-- the bolt: origin (BOLT_X, gy + BOLT_DY), scaled k; its canvas is 32 px with the origin at (16, 2)
for _, name in ipairs({{ "boltFill", "boltLine", "boltGlow" }}) do
    nearRect(SEC[name], R.x + MU.BOLT_X - 1213 - 16 * k, R.y + gy + MU.BOLT_DY - 2 * k, 32 * k, 32 * k, name)
end
-- the label is centred on the bolt, its baseline GY + LABEL_DY
local lx, ly = imgCenter(SEC.label)
near(lx, R.x + MU.LABEL_X - 1213, "label x", 0.05)
near(ly, R.y + gy + MU.LABEL_DY - CAP * MU.LABEL_SIZE, "label y", 0.1)
-- the Nova ring centred on the Fire head (a full pole's)
local d = 2 * MU.RING_OUT + 8          -- the ring canvas: 4 px of margin past the outer ring each side
nearRect(SEC.ring, R.x + MU.FIRE_X - 1213 - d / 2, R.y + gy - MU.NB * MU.BP - 15 + 9 - d / 2, d, d, "ring")
nearRect(SEC.ringGlow, R.x + MU.FIRE_X - 1213 - d / 2, R.y + gy - MU.NB * MU.BP - 15 + 9 - d / 2, d, d, "ring glow")
-- the footer: the pip centred at (PIP_X, fy + PIP_DY) 10 px, NOVA from NOVA_X on the baseline fy + NOVA_BASE
local fy = gy + MU.FOOT_DY
local px, py = imgCenter(SEC.pip)
near(px, R.x + MU.PIP_X - 1213, "pip x", 0.05); near(py, R.y + fy + MU.PIP_DY, "pip y", 0.05)
local _, _, pw = imgRect(SEC.pip)
near(pw, 10, "pip size", 0.02)
check(SEC.novaText.points[1][1] == "LEFT", "NOVA is left anchored")
local cx, cy = imgCenter(SEC.novaText)
near(cx, R.x + MU.NOVA_X - 1213, "NOVA x", 0.05)
near(cy, R.y + fy + MU.NOVA_BASE - CAP * MU.NOVA_SIZE, "NOVA y", 0.1)
noDegrade()
""")

case("a_rescale_re_seats_in_place_and_a_bad_rect_changes_nothing")(r"""
boot({})
cdPlain(8042, 4, 6)
mount("lower")
local frames, texes = #FRAMES, #TEXTURES
SetScreen(1080)
Shocks.Seat(SEC, RECTS.lower, 1.28)
check(#FRAMES == frames and #TEXTURES == texes, "a seat creates nothing")
local l, t, w, h = imgRect(SEC.base)
near(w, 162, "the trace keeps its image width at another screen height", 0.05)
Shocks.Seat(SEC, nil, 1.28)
Shocks.Seat(SEC, { x = "a" }, nil)
Shocks.Seat(nil, RECTS.lower, 1.28)
Shocks.OnShow(nil); Shocks.OnHide(nil)
local l2, t2 = imgRect(SEC.base)
near(l2, l, "left", 0.001); near(t2, t, "top", 0.001)
noDegrade()
""")

case("a_rescale_keeps_the_colours_the_texts_wear")(r"""
boot({})
IN_COMBAT = true
mount("lower")
cdSecret(408341); cast(408341)               -- Fire Nova cools down: NOVA is muted at .75
local c = SEC.novaText.textColor
check(math.abs(c[1] - 0.6157) < 0.01 and math.abs(c[4] - 0.75) < 0.01, "NOVA is muted")
Shocks.Seat(SEC, RECTS.lower, 1.28)         -- ApplyMono resets a font string's colour; the seat puts the worn one back
c = SEC.novaText.textColor
check(math.abs(c[1] - 0.6157) < 0.01 and math.abs(c[4] - 0.75) < 0.01, "NOVA stays muted at .75 after a seat, got " .. c[1] .. " " .. tostring(c[4]))
c = SEC.label.textColor
check(math.abs(c[1] - 0.133) < 0.01, "RDY stays cyan after a seat")
noDegrade()
""")

case("the_per_frame_path_allocates_nothing")(r"""
jit.off()
boot({})
IN_COMBAT = true
mount("lower")
for _, t in ipairs(TEXTURES) do
    t.SetVertexColor = function(self, r, g, b, a) local v = self.vertex; v[1], v[2], v[3], v[4] = r, g, b, a == nil and 1 or a end
    t.SetColorTexture = function(self, r, g, b, a) local c = self.color or { 0, 0, 0, 0 }; self.color = c; c[1], c[2], c[3], c[4] = r, g, b, a end
end
for _, s in ipairs(FONTSTRINGS) do
    s.textColor = { 0, 0, 0, 0 }
    s.SetTextColor = function(self, r, g, b, a) local c = self.textColor; c[1], c[2], c[3], c[4] = r, g, b, a end
end
cdSecret(8042); cdSecret(408341)
cast(8042); cast(408341)
local ticker
for _, f in ipairs(built()) do if f.scripts.OnUpdate then ticker = f end end
check(ticker, "a charging shock ticks")
local fn = ticker.scripts.OnUpdate
for i = 1, 300 do NOW = NOW + 0.01; fn(ticker, 0.01) end
cast(8042); cast(408341)
collectgarbage(); collectgarbage("stop")
local before = collectgarbage("count")
for i = 1, 500 do NOW = NOW + 0.01; fn(ticker, 0.01) end           -- 5 s: whole seconds, tenths, the Nova wait
local grown = (collectgarbage("count") - before) * 1024
collectgarbage("restart")
check(grown < 512, "500 frames allocated " .. math.floor(grown) .. " bytes")
""")


def static_checks() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        s = toc.index("Modules/CombatHud/GunsightShamanShocks.lua")
        sh = toc.index("Modules/CombatHud/GunsightShaman.lua")
        a = toc.index("Modules/CombatHud/GunsightAreas.lua")
        out.append(("toc_loads_shocks_right_before_shaman",
                    None if s + 1 == sh and s > a else f"GunsightShamanShocks.lua must sit right before GunsightShaman.lua (positions {s}, {sh})"))
    except ValueError as e:
        out.append(("toc_loads_shocks_right_before_shaman", f"{e}"))
    src = SHOCKS.read_text(encoding="utf-8") if SHOCKS.exists() else ""
    out.append(("no_em_or_en_dashes", None if not re.search("[–—]", src) else "GunsightShamanShocks.lua has an em or en dash"))
    code = "\n".join(re.sub(r"--.*$", "", ln) for ln in src.splitlines())
    out.append(("player_text_never_says_tape", None if not re.search(r"\"[^\"]*\btape\b[^\"]*\"", code, re.I) else "player text says tape"))
    out.append(("draws_no_kick_tag_and_reads_no_target_cast", None if not re.search(r"\"KICK\"|UnitCastingInfo|UnitChannelInfo|SetAlphaFromBoolean", code)
                else "KICK comes from GunsightTape.lua: this file draws no tag and reads no target cast"))
    out.append(("never_touches_a_secure_template", None if "SecureActionButtonTemplate" not in src and "SecureUnitButtonTemplate" not in src
                else "a secure template under a host would make it protected"))
    out.append(("never_parents_to_uiparent_or_the_root", None if not re.search(r"CreateFrame\([^)]*(UIParent|Gunsight\.root)", src)
                else "everything hangs under the module frame"))
    for tex in ("shock_trace_line", "shock_trace_glow", "shock_bolt_fill", "shock_bolt_line", "shock_bolt_glow",
                "nova_ring", "nova_ring_glow", "nova_pip"):
        out.append((f"texture_{tex}_exists", None if (TEXTURES / f"{tex}.tga").exists() else f"{tex}.tga is missing"))
        out.append((f"texture_{tex}_is_used", None if tex + ".tga" in src else f"{tex}.tga is never used"))
    return out


def run_case(name: str, body: str, mu: dict) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    g = lua.globals()
    g.LAYOUT_SRC = LAYOUT.read_text(encoding="utf-8")
    g.CONFIG_SRC = CONFIG.read_text(encoding="utf-8")
    g.FRAMEHELPERS_SRC = FRAMEHELPERS.read_text(encoding="utf-8")
    g.GUNSIGHT_SRC = GUNSIGHT.read_text(encoding="utf-8")
    g.SHOCKS_SRC = SHOCKS.read_text(encoding="utf-8")
    g.HAS_TARGET_SRC = _load("gunsight-harness").theme_target_rule_lua()
    lua.execute("MU = " + lua_value(mu))
    try:
        lua.execute(PRELUDE + "\n" + body)
    except LuaError as e:
        return str(e)
    return None


def main() -> int:
    mu = mockup_numbers()
    failures = 0

    def report(name: str, err: str | None) -> None:
        nonlocal failures
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      " + err.replace("\n", "\n      "))

    if not SHOCKS.exists():
        print(f"FAIL  {SHOCKS.name} is missing")
        return 1
    for name, body in CASES:
        try:
            err = run_case(name, body, mu)
        except LuaError as e:
            err = f"harness error: {e}"
        report(name, err)
    statics = static_checks()
    for name, err in statics:
        report(name, err)
    total = len(CASES) + len(statics)
    print(f"\n{total - failures}/{total} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
