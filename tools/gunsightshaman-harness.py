#!/usr/bin/env python3
"""Runs the real GunsightShaman.lua (the Shaman Gunsight Class Module) headless.

The IMBUE and SHIELD chips that this module drew in its first slice moved to the Shaman buff tab (BuffTab.lua and
ShamanBuffs.lua; tools/buffbar-harness.py pins them). The module stays registered as the Shaman's "class" module with
FS.GunsightAreas.RegisterModule, because the totem poles, the shock trace and the Fire Nova ring come later, but today it
draws NOTHING and listens to nothing. FS.GunsightAreas is a FAKE for the registration cases and the REAL file for the
target gate cases. The checks pin:

  * registration: one "class" spec for SHAMAN, with build, seat, onShow and onHide, and nothing else registered;
  * the build makes one plain frame under the host and no texture, no font string, no event, no OnUpdate, no timer and
    no extra frame, for a Shaman and for any other class; seat, onShow and onHide change none of that, and seat takes
    a bad rect without raising;
  * under the real areas the host follows the target gate as every class module does (the registry's own rule), and
    the module draws nothing in either state;
  * the file no longer reads weapons or auras or spells, no longer listens for casts (the tab owns the imbue and shield
    data), and uses no chip textures;
  * the TOC loads it after GunsightAreas.lua.

The mock is strict. It is NOT the real client.

    python3 tools/gunsightshaman-harness.py

Exit 0 = every check passed. GUNSIGHTSHAMAN_LUA=<path> runs another file in place of GunsightShaman.lua.
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
SHAMAN = Path(os.environ.get("GUNSIGHTSHAMAN_LUA") or ADDON / "Modules/CombatHud/GunsightShaman.lua")
GUNSIGHT = ADDON / "Modules/CombatHud/Gunsight.lua"
LAYOUT = ADDON / "Core/Layout.lua"
CONFIG = ADDON / "Core/Config.lua"
TOC = ADDON / "forever-stuwave.toc"
AREAS = ADDON / "Modules/CombatHud/GunsightAreas.lua"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CLASS_HARNESS = _load("gunsightclass-harness")

# ---------------------------------------------------------------------------------------
# The mock client: the Class harness's strict mock (itself the Dots harness's)
# ---------------------------------------------------------------------------------------

MOCK = CLASS_HARNESS.MOCK

PRELUDE = r"""
RECTS = { upper = { x = 100, y = 100, w = 202, h = 60 }, lower = { x = 100, y = 700, w = 202, h = 60 } }
K = 1.28

local function fakeAreas()
    MODS, AREA_OF = {}, {}
    FS.GunsightAreas = {
        RegisterModule = function(id, spec) MODS[id] = spec; return true end,
        AreaOf = function(id) return AREA_OF[id] end,
        OnAreaChanged = function() end,
    }
end

local function boot(opts)
    opts = opts or {}
    STRICT_EVENTS = false
    TIMERS = {}
    resetKnownEvents()
    resetWorld()
    SetScreen(opts.height or 1440)
    ForeverSTUwaveDB = opts.db
    FS.IsSecret = function() return false end
    stubTheme_()
    FS.Theme.COLOR_TEXT_WHITE = { 1, 1, 1, 1 }
    stubHud_()
    assert(loadstring(HAS_TARGET_SRC, "@Theme.lua"))()
    loadAddonFile(LAYOUT_SRC, "Core/Layout.lua")
    loadAddonFile(CONFIG_SRC, "Core/Config.lua")
    loadAddonFile(GUNSIGHT_SRC, "Modules/CombatHud/Gunsight.lua")
    if opts.realAreas then
        TARGET = { exists = not opts.noTarget }
        UnitExists = function() return TARGET.exists end
        loadAddonFile(AREAS_SRC, "Modules/CombatHud/GunsightAreas.lua")
    else
        fakeAreas()
    end
    UnitClass = function() return "Shaman", opts.class or "SHAMAN" end
    -- a client call the module must not make any more: each one records itself
    CALLED = {}
    local function trap(name) _G[name] = function() CALLED[#CALLED + 1] = name end end
    for _, n in ipairs({ "GetWeaponEnchantInfo", "GetInventoryItemID", "IsPlayerSpell", "IsSpellKnown" }) do trap(n) end
    C_Spell = { GetSpellInfo = function() CALLED[#CALLED + 1] = "C_Spell.GetSpellInfo" end }
    C_TooltipInfo = { GetInventoryItem = function() CALLED[#CALLED + 1] = "C_TooltipInfo.GetInventoryItem" end }
    FS.PlayerAuras = { Get = function() CALLED[#CALLED + 1] = "PlayerAuras.Get"; return { buffs = {} } end,
        IsFrozen = function() return false end }
    local frames = #FRAMES
    FRAMES_BEFORE = frames
    loadAddonFile(SHAMAN_SRC, "Modules/CombatHud/GunsightShaman.lua")
    fire("ADDON_LOADED", "forever-stuwave")
    fire("PLAYER_LOGIN")
end

local function mount(area)
    STRICT_EVENTS = true
    local spec = MODS.class
    check(spec, "no class module registered")
    local host = CreateFrame("Frame", nil, FS.Gunsight.root)
    host:SetSize(1, 1)
    local before = #FRAMES
    local frame = spec.build(host)
    check(frame ~= nil, "build(host) returned no frame")
    BUILT_FRAMES = #FRAMES - before
    spec.seat(RECTS[area])
    if spec.onShow then spec.onShow(area) end
    return spec, host, frame
end

local function under(r, host)
    while r do if r == host then return true end; r = r.parent end
    return false
end
local function drawn(host)
    local tex, txt = {}, {}
    for _, t in ipairs(TEXTURES) do if under(t, host) then tex[#tex + 1] = t end end
    for _, s in ipairs(FONTSTRINGS) do if under(s, host) then txt[#txt + 1] = s end end
    return tex, txt
end
local function listeners()
    local n = 0
    for _, f in ipairs(FRAMES) do
        for _ in pairs(f.events) do n = n + 1 end
        if f.scripts.OnUpdate or f.scripts.OnEvent then n = n + 1 end
    end
    return n
end
local function noDegrade() check(next(DEGRADED) == nil, "a degrade was logged: " .. tostring(next(DEGRADED))) end
"""

CASES: list[tuple[str, str]] = []


def case(name: str):
    def deco(body: str):
        CASES.append((name, body))
        return body
    return deco


case("registers_one_class_module_for_shaman_only_through_the_seam")(r"""
boot({})
local spec = MODS.class
check(spec, "no module registered under the id class")
local n = 0
for _ in pairs(MODS) do n = n + 1 end
check(n == 1, "exactly the class module is registered, got " .. n)
check(#spec.classes == 1 and spec.classes[1] == "SHAMAN", "classes must be exactly SHAMAN, got " .. #spec.classes)
for _, f in ipairs({ "build", "seat", "onShow", "onHide" }) do
    check(type(spec[f]) == "function", "the module has no " .. f)
end
noDegrade()
""")

case("without_the_areas_seam_nothing_registers_and_nothing_throws")(r"""
resetWorld()
SetScreen(1440)
FS.IsSecret = function(v) return false end
stubTheme_(); stubHud_()
loadAddonFile(LAYOUT_SRC, "Core/Layout.lua"); loadAddonFile(CONFIG_SRC, "Core/Config.lua"); loadAddonFile(GUNSIGHT_SRC, "Modules/CombatHud/Gunsight.lua")
UnitClass = function() return "Shaman", "SHAMAN" end
FS.GunsightAreas = {}
loadAddonFile(SHAMAN_SRC, "Modules/CombatHud/GunsightShaman.lua")
FS.GunsightAreas = nil
loadAddonFile(SHAMAN_SRC, "Modules/CombatHud/GunsightShaman.lua")
""")

case("the_module_draws_nothing_and_listens_to_nothing_in_either_area")(r"""
for _, area in ipairs({ "upper", "lower" }) do
    boot({})
    local before = listeners()
    local spec, host = mount(area)
    check(BUILT_FRAMES == 1, "build makes one plain frame under the host, got " .. BUILT_FRAMES)
    local tex, txt = drawn(host)
    check(#tex == 0 and #txt == 0, area .. ": nothing drawn, got " .. #tex .. " textures and " .. #txt .. " strings")
    check(listeners() == before, area .. ": no event, OnEvent or OnUpdate registered, got " .. (listeners() - before))
    check(#TIMERS == 0, area .. ": no timer")
    spec.onHide(area); spec.onShow(area); spec.seat(RECTS[area]); spec.seat(nil); spec.seat({ x = "a" })
    tex, txt = drawn(host)
    check(#tex == 0 and #txt == 0 and listeners() == before, area .. ": show, hide and seat change nothing")
    fire("UNIT_AURA", "player"); fire("UNIT_INVENTORY_CHANGED", "player"); fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g", 8017)
    check(#CALLED == 0, area .. ": the module reads no weapon, spell or aura, called " .. tostring(CALLED[1]))
    noDegrade()
end
""")

case("another_class_builds_the_same_empty_frame")(r"""
boot({ class = "PRIEST" })
local spec, host = mount("lower")
check(BUILT_FRAMES == 1, "one plain frame, got " .. BUILT_FRAMES)
local tex, txt = drawn(host)
check(#tex == 0 and #txt == 0, "nothing drawn")
noDegrade()
""")

case("under_the_real_areas_the_host_follows_the_target_and_the_module_stays_empty")(r"""
boot({ realAreas = true })
local host = FS.GunsightAreas.Host("lower")
check(host, "the real areas hand out a lower host")
check(isVisible(host), "a target shows the host")
local tex, txt = drawn(host)
check(#tex == 0 and #txt == 0, "with a target the module draws nothing")
TARGET.exists = false
fire("PLAYER_TARGET_CHANGED")
check(not isVisible(host), "no target hides the host")
TARGET.exists = true
fire("PLAYER_TARGET_CHANGED")
check(isVisible(host), "a target brings the host back")
tex, txt = drawn(host)
check(#tex == 0 and #txt == 0, "and it is still empty")
check(#CALLED == 0, "no weapon, spell or aura read, called " .. tostring(CALLED[1]))
noDegrade()
""")


def static_checks() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        s, a = toc.index("Modules/CombatHud/GunsightShaman.lua"), toc.index("Modules/CombatHud/GunsightAreas.lua")
        out.append(("toc_loads_shaman_after_areas",
                    None if s > a else f"GunsightShaman.lua must load after GunsightAreas.lua (positions {a}, {s})"))
    except ValueError as e:
        out.append(("toc_loads_shaman_after_areas", f"{e}"))
    src = SHAMAN.read_text(encoding="utf-8") if SHAMAN.exists() else ""
    out.append(("no_em_or_en_dashes", None if not re.search("[–—]", src) else "GunsightShaman.lua has an em or en dash"))
    gone = r"GetWeaponEnchantInfo|C_TooltipInfo|FS\.PlayerAuras|UNIT_SPELLCAST|RegisterEvent|RegisterUnitEvent|SetScript|C_Spell|slice_cut2"
    out.append(("reads_and_listens_to_nothing_any_more",
                None if not re.search(gone, src) else "the imbue and shield data moved to ShamanBuffs.lua; this file must not touch it"))
    out.append(("registers_the_class_spec_for_shaman",
                None if re.search(r'RegisterModule,\s*"class"', src) and '"SHAMAN"' in src else "the SHAMAN class spec is gone"))
    return out


def run_case(name: str, body: str) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    g = lua.globals()
    g.LAYOUT_SRC = LAYOUT.read_text(encoding="utf-8")
    g.CONFIG_SRC = CONFIG.read_text(encoding="utf-8")
    g.GUNSIGHT_SRC = GUNSIGHT.read_text(encoding="utf-8")
    g.SHAMAN_SRC = SHAMAN.read_text(encoding="utf-8")
    g.AREAS_SRC = AREAS.read_text(encoding="utf-8")
    g.HAS_TARGET_SRC = _load("gunsight-harness").theme_target_rule_lua()
    try:
        lua.execute(PRELUDE + "\n" + body)
    except LuaError as e:
        return str(e)
    return None


def main() -> int:
    failures = 0

    def report(name: str, err: str | None) -> None:
        nonlocal failures
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      " + err.replace("\n", "\n      "))

    if not SHAMAN.exists():
        print(f"FAIL  {SHAMAN.name} is missing")
        return 1
    for name, body in CASES:
        try:
            err = run_case(name, body)
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
