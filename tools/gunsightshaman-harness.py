#!/usr/bin/env python3
"""Runs the real GunsightShaman.lua (the Shaman Gunsight Class Module, first slice: the IMBUE and SHIELD chips) headless.

GunsightShaman.lua registers the module "class" for SHAMAN through FS.GunsightAreas.RegisterModule. Concept A, Totem
Poles (mockups/gunsight-class-module-shaman-2026-10-08.html, poleMod and reminders), puts two 14 px self reminder
chips in the footer of the area: weapon imbue and Lightning Shield. The totem poles, the shock trace and the Fire Nova
ring are NOT drawn yet. FS.GunsightAreas is a FAKE here with the same API as the real one (its own harness covers it).
The checks pin:

  * registration: one "class" spec for SHAMAN, with build, seat, onShow and onHide;
  * geometry: the chips, their codes and their words at the mockup's offsets inside the area rect (read from the
    mockup), in the upper and lower area, re-seated in place on a rescale;
  * chip states: up (quiet, the time or the orb count), expiring (an imbue at five minutes or less, a design addition
    the mockup does not draw), missing (amber, the word), unknown (hollow, "?");
  * the imbue's time and secrets: a plain read stores the expiry, a secret read in combat keeps counting down from
    it, and with nothing stored the chip says "?"; the imbue is named by the enchant id, else by our own cast;
  * dual wield: both hands are read, the chip shows the least time, and a bare second weapon is asked for (a shield, an
    empty hand, a two hander or a frill never is);
  * identity: an enchant id names an imbue only after a cast of ours confirmed it (the Classic id table is unverified
    and unused); a pending cast outlasts FRESH_S, an id seen behind a cast is not taught, a zero id is no id;
  * the shield: the orb count from the player aura snapshot, a frozen snapshot in combat read as a cached estimate that
    is believed for at most ten minutes, and a Water Shield hides the chip;
  * secrets: a secret boolean and a secret number report their real type(), so only IsSecret keeps them out; the checks
    prove each guard by the state a missed one would change (a Lua table is always truthy, so a boolean test cannot raise);
  * the spell book is asked about an unlearned spell once, not at every tick;
  * a spell the player has not learned draws no chip at all (no nagging "missing").

The mock is strict (a widget method it does not define fails as a nil call, an aura API read fails the case); Layout.lua,
Config.lua and Gunsight.lua are the real files. It is NOT the real client.

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
MOCKUP = HERE.parent / "mockups" / "gunsight-class-module-shaman-2026-10-08.html"
TEXTURES = ADDON / "Media" / "Textures"


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


def _hex(h: str) -> list[float]:
    return [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]


def _mix(a: str, b: str, t: float) -> list[float]:
    x, y = _hex(a), _hex(b)
    return [x[i] + (y[i] - x[i]) * t for i in range(3)]


def mockup_numbers() -> dict:
    """The numbers poleMod, reminders and mchip draw, in image px, read out of the Shaman mockup."""
    src = MOCKUP.read_text(encoding="utf-8")
    pole = _m(r"function poleMod\(y0,st,an\)\{(.*?)\n\}", src, "poleMod").group(1)
    gy = _m(r"gy=y0\+(\d+)", pole, "ground line").group(1)
    fy = _m(r"var fy=gy\+(\d+);", pole, "footer line").group(1)
    rem = _m(r"o\+=reminders\((\d+),(\d+),fy,st,false\)", pole, "reminders call")
    mchip = _m(r"function mchip\(x,y,ab,col,mode\)\{(.*?)\n\}", src, "mchip").group(1)
    chip = _m(r"ch\(x,y,(\d+),(\d+),(\d+)\)", mchip, "chip size")
    abpx = _m(r"font-size=\"(\d+)\" fill=\"'\+sc", mchip, "chip code size")
    abbase = _m(r"y=\"'\+\(y\+([\d.]+)\)", mchip, "chip code baseline")
    fns = _m(r"function reminders\(xi,xl,y,st,vertical\)\{(.*?)\n\}", src, "reminders").group(1)
    tdx = _m(r"tx=vertical\?x\+7:x\+(\d+)", fns, "word x")
    tbase = _m(r"ty=vertical\?y\+\d+:y\+([\d.]+)", fns, "word baseline")
    tpx = _m(r"txt\(tx,ty,s,(\d+),fill,", fns, "word size")
    upalpha = _m(r"op:r\.s==='up'\?([\d.]+):1", fns, "up text alpha")
    upk = _m(r"var UPK='(#[0-9a-fA-F]{6})'", src, "chip colour").group(1)
    warn = _m(r"mix\(C\.bg,C\.amber,([\d.]+)\)", mchip, "warn fill mix").group(1)
    on = _m(r"mix\(C\.bg,col,([\d.]+)\)", mchip, "on fill mix").group(1)
    hol = _m(r"'rgba\(13,6,32,([\d.]+)\)'", mchip, "hollow fill alpha").group(1)
    hstroke = _m(r"mix\(C\.muted,'#ffffff',([\d.]+)\)", mchip, "hollow stroke mix").group(1)
    cm = CLASS_HARNESS.mockup_class()
    pal = _m(r"var C=\{(.*?)\};", src, "palette").group(1)
    fg = _m(r"fg:'(#[0-9a-fA-F]{6})'", pal, "fg")
    bg = _m(r"bg:'(#[0-9a-fA-F]{6})'", pal, "bg")
    amber = _m(r"amber:'(#[0-9a-fA-F]{6})'", pal, "amber")
    muted = _m(r"muted:'(#[0-9a-fA-F]{6})'", pal, "muted")
    bgc, ambc, mutc = bg.group(1), amber.group(1), muted.group(1)
    return {
        "AREA_X": cm["AREA_X"], "UPPER_Y": cm["UPPER_Y"], "LOWER_Y": cm["LOWER_Y"], "AREA_H": cm["AREA_H"],
        "XI": int(rem.group(1)), "XL": int(rem.group(2)), "DY": int(gy) + int(fy),
        "CHIP": int(chip.group(1)), "CHAMFER": int(chip.group(3)),
        "AB_PX": int(abpx.group(1)), "AB_DX": int(chip.group(1)) / 2, "AB_BASE": float(abbase.group(1)),
        "TXT_DX": int(tdx.group(1)), "TXT_BASE": float(tbase.group(1)), "TXT_PX": int(tpx.group(1)),
        "UP_ALPHA": float(upalpha.group(1)),
        "UPK": _hex(upk), "FG": _hex(fg.group(1)), "AMBER": _hex(ambc), "MUTED": _hex(mutc),
        "ON_FILL": _mix(bgc, upk, float(on)), "WARN_FILL": _mix(bgc, ambc, float(warn)),
        "HOLLOW_FILL_ALPHA": float(hol), "HOLLOW_STROKE": _mix(mutc, "#ffffff", float(hstroke)),
        "BG": _hex(bgc),
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
# The mock client: the Class harness's strict mock (itself the Dots harness's) plus the world a Shaman reads
# ---------------------------------------------------------------------------------------

MOCK = CLASS_HARNESS.MOCK

PRELUDE = r"""
local AREA_X, AREA_H = MU.AREA_X, MU.AREA_H
RECTS = { upper = { x = AREA_X, y = MU.UPPER_Y, w = 202, h = AREA_H }, lower = { x = AREA_X, y = MU.LOWER_Y, w = 202, h = AREA_H } }
-- Secrets that report their REAL kind through type(), as the client's do: a secret boolean says "boolean" and a secret
-- number says "number", so a `type(v) == "number"` check alone lets them through and only IsSecret keeps them out. Any
-- arithmetic, comparison, concatenation or length of one raises. A Lua table is always truthy, so a boolean test of a
-- secret boolean cannot raise here: the guard on one is pinned by the state a missed guard would change.
local realType = type
local function secretOf()
    local function boom(what) return function() error("SECRET_OP: " .. what, 2) end end
    return setmetatable({}, { __lt = boom("compare"), __le = boom("compare"), __add = boom("arith"), __sub = boom("arith"),
        __mul = boom("arith"), __div = boom("arith"), __mod = boom("arith"), __pow = boom("arith"), __unm = boom("arith"),
        __concat = boom("concat"), __len = boom("len") })
end
SBOOL, SNUM = secretOf(), secretOf()
function type(v)
    if rawequal(v, SBOOL) then return "boolean" end
    if rawequal(v, SNUM) then return "number" end
    return realType(v)
end
SECRET_FN = function(v) return v == SECRET or rawequal(v, SBOOL) or rawequal(v, SNUM) end
LEAKED = {}            -- API calls a secret reached: none may
K = 1.28
TEXT_MID = 0.35        -- a line's visual centre sits this fraction of its size above the baseline (the Class module's TEXT_MID)

local function fakeAreas()
    MODS, AREA_OF = {}, {}
    FS.GunsightAreas = {
        RegisterModule = function(id, spec) MODS[id] = spec; return true end,
        AreaOf = function(id) return AREA_OF[id] end,
        OnAreaChanged = function() end,
    }
end

-- The spells: id -> name (every rank of an imbue is the same name, as on the client).
SPELL_NAMES = {
    [8017] = "Rockbiter Weapon", [10399] = "Rockbiter Weapon",
    [8024] = "Flametongue Weapon", [8033] = "Frostbrand Weapon", [8232] = "Windfury Weapon",
    [324] = "Lightning Shield", [10432] = "Lightning Shield", [403] = "Lightning Bolt", [24398] = "Water Shield",
}
BASE_ID = { ["Rockbiter Weapon"] = 8017, ["Flametongue Weapon"] = 8024, ["Frostbrand Weapon"] = 8033,
    ["Windfury Weapon"] = 8232, ["Lightning Shield"] = 324, ["Lightning Bolt"] = 403 }
KNOWN = {}             -- spell name -> true once learned
BOOK_CALLS, INFO_CALLS = 0, 0   -- spellbook and spell info questions asked
EQUIP, LOC_OF = {}, {}          -- slot -> item id, item id -> equip location
WEAPON, WEAPON_CALLS = nil, 0
SNAP, FROZEN = { buffs = {} }, false
function learn(...) for _, n in ipairs({ ... }) do KNOWN[n] = true end end
function setWeapon(has, ms, id, charges)
    WEAPON = { has, ms or 0, charges or 0, id or 0, false, 0, 0, 0 }
end
-- main / off: nil for no enchant, else { ms, enchantId }
function setHands(main, off)
    WEAPON = { main ~= nil, main and main[1] or 0, 0, main and main[2] or 0, off ~= nil, off and off[1] or 0, 0, off and off[2] or 0 }
end
function equip(slot, loc) ITEMS_N = (ITEMS_N or 0) + 1; EQUIP[slot] = 100 + ITEMS_N; LOC_OF[EQUIP[slot]] = loc end
function secretWeapon() WEAPON = { SECRET, SECRET, SECRET, SECRET, SECRET, SECRET, SECRET, SECRET } end
function setShield(count, expires)
    SNAP = { buffs = { { name = "Lightning Shield", count = count, expirationTime = expires or (NOW + 600), spellId = 324 } } }
end
function noShield() SNAP = { buffs = { { name = "Mark of the Wild", count = 0, expirationTime = 0 } } } end
function waterShield(nameless)
    SNAP = { buffs = { { name = (not nameless) and "Water Shield" or nil, count = 3, expirationTime = NOW + 600, spellId = 24398 } } }
end
function enterCombat() IN_COMBAT = true; FROZEN = true end
function leaveCombat() IN_COMBAT = false; FROZEN = false end

local function boot(opts)
    opts = opts or {}
    STRICT_EVENTS = false
    TIMERS = {}
    resetKnownEvents()
    for e in ([[UNIT_AURA UNIT_INVENTORY_CHANGED PLAYER_EQUIPMENT_CHANGED UNIT_SPELLCAST_SUCCEEDED SPELLS_CHANGED PLAYER_LEVEL_UP LEARNED_SPELL_IN_SKILL_LINE LEARNED_SPELL_IN_TAB]]):gmatch("%S+") do KNOWN_EVENTS[e] = true end
    resetWorld()
    SetScreen(opts.height or 1440)
    ForeverSTUwaveDB = opts.db
    FS.IsSecret = function(v) return SECRET_FN(v) end
    stubTheme_()
    FS.Theme.COLOR_TEXT_WHITE = { 1, 1, 1, 1 }
    FS.Theme.COLOR_MUTED = { MU.MUTED[1], MU.MUTED[2], MU.MUTED[3], 1 }
    FS.Theme.COLOR_AMBER = { MU.AMBER[1], MU.AMBER[2], MU.AMBER[3], 1 }
    function FS.Theme.ApplyMono(fs, size, color)
        fs.monoSize, fs.hasFont = size, true
        fs.textColor = { color[1], color[2], color[3], color[4] or 1 }
    end
    -- the baked cut-corner set for a chamfer: outline, glow, the chamfer used (Theme.Cut2ButtonSet)
    function FS.Theme.Cut2ButtonSet(c)
        local base = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\slice_cut2_"
        return base .. "outline_c" .. c .. ".tga", base .. "glow_c" .. c .. ".tga", c
    end
    FS.Theme.SLICE_CUT2_GLOW_PAD = 4
    stubHud_()
    assert(loadstring(HAS_TARGET_SRC, "@Theme.lua"))()
    loadAddonFile(LAYOUT_SRC, "Core/Layout.lua")
    loadAddonFile(CONFIG_SRC, "Core/Config.lua")
    loadAddonFile(GUNSIGHT_SRC, "Modules/CombatHud/Gunsight.lua")
    if opts.realAreas then
        -- the REAL registry, so the target side rules apply: a target is a flag the case flips (UnitExists)
        TARGET = { exists = not opts.noTarget }
        UnitExists = function() return TARGET.exists end
        loadAddonFile(AREAS_SRC, "Modules/CombatHud/GunsightAreas.lua")
    else
        fakeAreas()
    end
    UnitClass = function() return "Shaman", opts.classToken ~= nil and opts.classToken or (opts.class or "SHAMAN") end
    KNOWN, WEAPON_CALLS, SNAP, FROZEN, BOOK_CALLS, INFO_CALLS, LEAKED = {}, 0, { buffs = {} }, false, 0, 0, {}
    EQUIP, LOC_OF = {}, {}
    if opts.learn ~= false then learn("Rockbiter Weapon", "Lightning Shield") end
    for _, n in ipairs(opts.learned or {}) do learn(n) end
    if opts.unlearn then for _, n in ipairs(opts.unlearn) do KNOWN[n] = nil end end
    setWeapon(false)
    C_Spell = {
        GetSpellInfo = function(x)
            INFO_CALLS = INFO_CALLS + 1
            if SECRET_FN(x) then LEAKED[#LEAKED + 1] = "GetSpellInfo" end
            if type(x) == "number" then
                local n = SPELL_NAMES[x]
                return n and { name = n, spellID = x, iconID = 100 } or nil
            end
            if KNOWN[x] then return { name = x, spellID = BASE_ID[x], iconID = 100 } end
            return nil
        end,
    }
    IsPlayerSpell = function(id)
        BOOK_CALLS = BOOK_CALLS + 1
        return SPELL_NAMES[id] ~= nil and KNOWN[SPELL_NAMES[id]] == true
    end
    GetInventoryItemID = function(_, slot) return EQUIP[slot] end
    C_Item = { GetItemInfoInstant = function(id) return id, "Weapon", "Sword", LOC_OF[id], 1 end }
    IsSpellKnown, GetSpellInfo = nil, nil
    if not opts.noWeaponApi then
        GetWeaponEnchantInfo = function()
            WEAPON_CALLS = WEAPON_CALLS + 1
            if WEAPON_THROWS then error("GetWeaponEnchantInfo refused") end
            return unpack(WEAPON, 1, 8)
        end
    else
        GetWeaponEnchantInfo = nil
    end
    WEAPON_THROWS = false
    if not opts.noAuras then
        FS.PlayerAuras = { Get = function() return SNAP end, IsFrozen = function() return FROZEN end }
    end
    STATE = opts.state
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
    local frame = spec.build(host)
    check(frame ~= nil, "build(host) returned no frame")
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
    for _, t in ipairs(TEXTURES) do if under(t, host) and isVisible(t) then tex[#tex + 1] = t end end
    for _, s in ipairs(FONTSTRINGS) do if under(s, host) and isVisible(s) then txt[#txt + 1] = s end end
    return tex, txt
end
local function texWith(host, name)
    local out = {}
    local tex = drawn(host)
    for _, t in ipairs(tex) do if t.path and t.path:find(name, 1, true) then out[#out + 1] = t end end
    return out
end
local function textOf(host, str)
    local _, txt = drawn(host)
    for _, s in ipairs(txt) do if s.text == str then return s end end
    return nil
end
local function cx(r) local x, y = imgCenter(r); return x, y end
local function near3(a, b, what) near(a, b, what, 1e-2) end
local function fsPx(s) return s.monoSize / (K * FS.Layout.Scale()) end
local function colorIs(c, want, what)
    for i = 1, 3 do near(c[i], want[i], what .. " channel " .. i, 1e-3) end
end

-- The chip whose left edge is at image x (MU.XI for the imbue, MU.XL for the shield): its drawn pieces.
local function chip(host, x)
    local out = {}
    for _, kind in ipairs({ "fill", "outline", "glow" }) do
        for _, t in ipairs(texWith(host, "slice_cut2_" .. kind .. "_c")) do
            local px = cx(t)
            if math.abs(px - (x + MU.CHIP / 2)) < 0.5 then out[kind] = t end
        end
    end
    local _, txt = drawn(host)
    for _, s in ipairs(txt) do
        local sx = cx(s)
        if math.abs(sx - (x + MU.AB_DX)) < 0.5 then out.code = s
        elseif sx > x + MU.CHIP and sx < x + MU.CHIP + 50 and math.abs(sx - (x + MU.TXT_DX)) < 0.5 then out.word = s end
    end
    return out
end
local function imbueChip(host) return chip(host, MU.XI) end
local function shieldChip(host) return chip(host, MU.XL) end
local function shown(c) return c.fill ~= nil end

-- A fresh Shaman with the module mounted in the lower area; `weapon` / `shield` set the world before the first read.
local function up(opts)
    boot(opts)
    return mount((opts or {}).area or "lower")
end
-- Rank ids the client reports on a cast: the cast event carries the rank id.
local function cast(spellId) fire("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", spellId) end
local function codeOf(host) return imbueChip(host).code.text end
local function wordOf(host) return imbueChip(host).word.text end
local function noDegrade() check(next(DEGRADED) == nil, "a degrade was logged: " .. tostring(next(DEGRADED))) end
local MIN = 60
"""

CASES: list[tuple[str, str]] = []


def case(name: str):
    def deco(body: str):
        CASES.append((name, body))
        return body
    return deco


# --------------------------------------------------------------------------------- registration and geometry

case("registers_one_class_module_for_shaman_only_through_the_seam")(r"""
boot({})
local spec = MODS.class
check(spec, "no module registered under the id class")
check(#spec.classes == 1 and spec.classes[1] == "SHAMAN", "classes must be exactly SHAMAN, got " .. #spec.classes)
for _, f in ipairs({ "build", "seat", "onShow", "onHide" }) do
    check(type(spec[f]) == "function", "the module has no " .. f)
end
check(next(DEGRADED) == nil, "a degrade was logged: " .. tostring(next(DEGRADED)))
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

case("a_shaman_with_both_spells_draws_two_chips_and_nothing_else")(r"""
local spec, host = up({})
setWeapon(true, 52 * MIN * 1000, 0); setShield(3)
spec.onHide("lower"); spec.onShow("lower")
local tex, txt = drawn(host)
check(#texWith(host, "slice_cut2_fill_c") == 2, "two chip fills, got " .. #texWith(host, "slice_cut2_fill_c"))
check(#texWith(host, "slice_cut2_outline_c") == 2, "two chip outlines")
check(#tex == 6, "two chips of three pieces and nothing else (totem poles, shock, Nova come later), got " .. #tex)
check(#txt == 4, "two codes and two words, got " .. #txt)
check(shown(imbueChip(host)) and shown(shieldChip(host)), "both chips are where the mockup puts them")
""")

case("chips_sit_at_the_mockups_offsets_with_the_codes_and_words")(r"""
local spec, host = up({})
setWeapon(true, 52 * MIN * 1000, 0); setShield(3)
spec.onHide("lower"); spec.onShow("lower")
local k = K * FS.Layout.Scale()
for _, w in ipairs({ { MU.XI, "imbue", "52m" }, { MU.XL, "shield", "3" } }) do
    local c = chip(host, w[1])
    check(c.fill and c.outline and c.code and c.word, w[2] .. " chip is missing a piece")
    local fx, fy = cx(c.fill)
    near3(fx, w[1] + MU.CHIP / 2, w[2] .. " chip x")
    near3(fy, MU.LOWER_Y + MU.DY + MU.CHIP / 2, w[2] .. " chip y")
    near3(c.fill.w, MU.CHIP * k, w[2] .. " chip width")
    near3(c.fill.h, MU.CHIP * k, w[2] .. " chip height")
    check(c.fill.margin == MU.CHAMFER and c.outline.margin == MU.CHAMFER, w[2] .. " chip is cut at the mockup chamfer " .. MU.CHAMFER)
    local ax, ay = cx(c.code)
    near3(ax, w[1] + MU.AB_DX, w[2] .. " code x (centred)")
    near3(ay, MU.LOWER_Y + MU.DY + MU.AB_BASE - TEXT_MID * MU.AB_PX, w[2] .. " code y")
    near3(fsPx(c.code), MU.AB_PX, w[2] .. " code size")
    local wx, wy = cx(c.word)
    near3(wx, w[1] + MU.TXT_DX, w[2] .. " word x (left edge)")
    near3(wy, MU.LOWER_Y + MU.DY + MU.TXT_BASE - TEXT_MID * MU.TXT_PX, w[2] .. " word y")
    near3(fsPx(c.word), MU.TXT_PX, w[2] .. " word size")
    check(c.word.text == w[3], w[2] .. " word is " .. w[3] .. ", got " .. tostring(c.word.text))
end
check(imbueChip(host).code.text == "RB", "a Rockbiter weapon with no id read yet is named from the spell you know")
check(shieldChip(host).code.text == "LS", "the shield chip says LS")
""")

case("chips_follow_the_area_and_a_rescale")(r"""
local spec, host = up({ area = "upper" })
setWeapon(true, 52 * MIN * 1000, 0); setShield(3)
spec.onHide("upper"); spec.onShow("upper")
local _, fy = cx(imbueChip(host).fill)
near3(fy, MU.UPPER_Y + MU.DY + MU.CHIP / 2, "chip y in the upper area")
local frames, texes, strs = #FRAMES, #TEXTURES, #FONTSTRINGS
SetScreen(1200)
fire("UI_SCALE_CHANGED")
spec.seat(RECTS.lower)
local k = K * 1200 / 1440
local c = imbueChip(host)
near3(c.fill.w, MU.CHIP * k, "chip width follows the scale")
local x, y = cx(c.fill)
near3(x, MU.XI + MU.CHIP / 2, "chip x after the rescale")
near3(y, MU.LOWER_Y + MU.DY + MU.CHIP / 2, "seat to another rect moves it")
near3(fsPx(c.word), MU.TXT_PX, "word size after the rescale")
check(#FRAMES == frames and #TEXTURES == texes and #FONTSTRINGS == strs, "a rescale built regions")
""")

# --------------------------------------------------------------------------------- imbue chip states

case("imbue_up_is_a_quiet_chip_with_the_minutes_left")(r"""
local spec, host = up({})
setWeapon(true, 52 * MIN * 1000 + 30000, 0)
tick(1.5)
local c = imbueChip(host)
check(c.word.text == "52m", "52 minutes and 30 seconds reads 52m, got " .. tostring(c.word.text))
colorIs(c.outline.vertex, MU.UPK, "an imbue that is up has the gold outline")
colorIs(c.fill.vertex, MU.ON_FILL, "and the gold wash")
check(c.glow ~= nil, "the up chip glows")
colorIs(c.code.textColor, { 1, 1, 1 }, "the code is white")
colorIs(c.word.textColor, MU.FG, "the time is the soft foreground")
near3(c.word.textColor[4], MU.UP_ALPHA, "the time is quiet")
tick(1.5)
check(imbueChip(host).word.text == "52m", "it does not flicker while nothing changes")
""")

case("imbue_time_switches_to_seconds_under_a_minute")(r"""
local spec, host = up({})
setWeapon(true, 59 * 1000, 0)
tick(1.5)
check(imbueChip(host).word.text == "59s", "under a minute shows seconds, got " .. tostring(imbueChip(host).word.text))
setWeapon(true, 60 * 1000, 0)
tick(1.5)
check(imbueChip(host).word.text == "1m", "a full minute shows 1m, got " .. tostring(imbueChip(host).word.text))
""")

case("imbue_at_five_minutes_or_less_turns_to_the_expiring_colour")(r"""
local spec, host = up({})
local PINK = { 0.925, 0.286, 0.600 }
setWeapon(true, 301 * 1000, 0)
tick(1.5)
local c = imbueChip(host)
colorIs(c.outline.vertex, MU.UPK, "above five minutes the chip stays quiet")
colorIs(c.word.textColor, MU.FG, "and so does the time")
setWeapon(true, 300 * 1000, 0)
tick(1.5)
c = imbueChip(host)
colorIs(c.outline.vertex, PINK, "at five minutes the outline turns to the aura expiring colour")
colorIs(c.word.textColor, PINK, "and the time with it")
check(c.word.textColor[4] == 1, "the expiring time is not dimmed")
check(c.word.text == "5m", "and still reads the time, got " .. tostring(c.word.text))
setWeapon(true, 3600 * 1000, 0)
tick(1.5)
colorIs(imbueChip(host).outline.vertex, MU.UPK, "a fresh imbue is quiet again")
""")

case("imbue_missing_is_an_amber_hollow_chip_with_the_word")(r"""
local spec, host = up({})
setWeapon(false)
tick(1.5)
local c = imbueChip(host)
check(c.word.text == "IMBUE", "the word is IMBUE, got " .. tostring(c.word.text))
colorIs(c.outline.vertex, MU.AMBER, "amber outline")
colorIs(c.fill.vertex, MU.WARN_FILL, "amber wash")
colorIs(c.word.textColor, MU.AMBER, "amber word")
check(c.word.textColor[4] == 1, "the missing word is not dimmed")
check(c.glow ~= nil, "the amber chip glows")
check(c.code.text == "RB", "the code is the best imbue you know, got " .. tostring(c.code.text))
""")

case("imbue_with_nothing_read_in_combat_is_a_question_mark")(r"""
boot({})
secretWeapon(); enterCombat()
local spec, host = mount("lower")
tick(1.5)
local c = imbueChip(host)
check(c.word and c.word.text == "?", "nothing readable and nothing stored reads ?, got " .. tostring(c.word and c.word.text))
colorIs(c.word.textColor, MU.MUTED, "muted ?")
colorIs(c.outline.vertex, MU.HOLLOW_STROKE, "the hollow outline")
check(c.glow == nil, "the unknown chip does not glow")
near3(c.fill.vertex[4], MU.HOLLOW_FILL_ALPHA, "hollow wash alpha")
""")

case("imbue_keeps_counting_down_from_the_stored_expiry_when_the_read_is_secret")(r"""
local spec, host = up({})
setWeapon(true, 52 * MIN * 1000, 0)
tick(1.5)
check(imbueChip(host).word.text == "52m", "read out of combat")
secretWeapon(); enterCombat()
tick(10 * MIN)
check(imbueChip(host).word.text == "42m", "ten minutes into the fight it reads 42m, got " .. tostring(imbueChip(host).word.text))
tick(37 * MIN + 30)
check(imbueChip(host).word.text == "4m", "and 4m near the end, got " .. tostring(imbueChip(host).word.text))
colorIs(imbueChip(host).outline.vertex, { 0.925, 0.286, 0.600 }, "the countdown reaches the expiring colour in combat")
tick(5 * MIN)
check(imbueChip(host).word.text == "IMBUE", "past the stored expiry the imbue has fallen off, got " .. tostring(imbueChip(host).word.text))
""")

case("imbue_goes_back_to_the_live_read_when_combat_ends")(r"""
local spec, host = up({})
setWeapon(true, 52 * MIN * 1000, 0); tick(1.5)
secretWeapon(); enterCombat(); tick(10 * MIN)
leaveCombat(); setWeapon(true, 41 * MIN * 1000 + 5000, 0)
tick(1.5)
check(imbueChip(host).word.text == "41m", "the live read wins again")
""")

case("a_plain_read_in_combat_is_used_and_a_plain_none_is_missing")(r"""
local spec, host = up({})
setWeapon(true, 52 * MIN * 1000, 0); tick(1.5)
IN_COMBAT = true
setWeapon(false)
tick(1.5)
check(imbueChip(host).word.text == "IMBUE", "a readable no enchant in combat is missing")
""")

case("a_secret_time_with_a_known_enchant_keeps_the_stored_expiry_and_a_secret_flag_with_none_stored_is_unknown")(r"""
local spec, host = up({})
WEAPON = { true, SECRET, 0, 0, false, 0, 0, 0 }
tick(1.5)
check(imbueChip(host).word.text == "?", "an enchant that is there but whose time is secret, with nothing stored, reads ?")
setWeapon(true, 20 * MIN * 1000, 0); tick(1.5)
WEAPON = { true, SECRET, 0, 0, false, 0, 0, 0 }
tick(5 * MIN)
check(imbueChip(host).word.text == "15m", "with a stored expiry it counts down, got " .. tostring(imbueChip(host).word.text))
""")

case("every_weapon_field_secret_throws_nothing_and_reaches_no_comparison")(r"""
local spec, host = up({})
secretWeapon()
spec.onHide("lower"); spec.onShow("lower")
for _ = 1, 3 do tick(1.5) end
fire("UNIT_INVENTORY_CHANGED", "player")
fire("PLAYER_EQUIPMENT_CHANGED", 16, false)
check(next(DEGRADED) == nil, "a degrade was logged: " .. tostring(next(DEGRADED)))
""")

case("a_throwing_or_missing_weapon_api_is_a_question_mark_not_a_crash")(r"""
boot({})
WEAPON_THROWS = true
local spec, host = mount("lower")
tick(1.5)
check(imbueChip(host).word.text == "?", "a refused read is unknown")
local spec2, host2 = up({ noWeaponApi = true })
tick(1.5)
check(imbueChip(host2).word.text == "?", "a client with no GetWeaponEnchantInfo is unknown")
""")

# --------------------------------------------------------------------------------- imbue identity

case("an_enchant_id_is_never_named_from_an_unverified_table")(r"""
local spec, host = up({})
setWeapon(true, 50 * MIN * 1000, 5)       -- 5 is Flametongue in the Classic data, unverified on Forever
tick(1.5)
check(codeOf(host) == "RB", "with one imbue known the guess is that imbue, not the table's Flametongue, got " .. codeOf(host))
local spec2, host2 = up({ learned = { "Flametongue Weapon", "Frostbrand Weapon", "Windfury Weapon" } })
for _, id in ipairs({ 29, 503, 5, 523, 2, 524, 283, 525 }) do
    setWeapon(true, 50 * MIN * 1000, id)
    tick(1.5)
    check(codeOf(host2) == "IM", "enchant " .. id .. " is not named before a cast confirmed it, got " .. codeOf(host2))
end
""")

case("imbue_is_named_by_our_own_cast_when_the_id_is_unknown_or_secret")(r"""
local spec, host = up({ learned = { "Flametongue Weapon" } })
setWeapon(true, 59 * MIN * 1000, 99999)
cast(8024)
tick(1.5)
check(imbueChip(host).code.text == "FT", "a Flametongue cast names an enchant id the table does not know")
secretWeapon(); enterCombat(); tick(1.5)
check(imbueChip(host).code.text == "FT", "and still does when the id turns secret in combat")
""")

case("a_cast_teaches_the_id_it_produced")(r"""
local spec, host = up({ learned = { "Frostbrand Weapon" } })
setWeapon(true, 59 * MIN * 1000, 5)
cast(8033)
tick(1.5)
check(codeOf(host) == "FB", "what you just cast is what you have, got " .. codeOf(host))
setWeapon(true, 58 * MIN * 1000, 5)
tick(1.5)
check(codeOf(host) == "FB", "and enchant 5 stays learned as Frostbrand")
setWeapon(false); tick(3)
setWeapon(true, 30 * MIN * 1000, 5); tick(1.5)
check(codeOf(host) == "FB", "even after it fell off and the same id came back with no cast, got " .. codeOf(host))
""")

case("a_cast_stands_past_fresh_seconds_until_the_id_shows_and_then_teaches_it")(r"""
local spec, host = up({ learned = { "Flametongue Weapon" } })
secretWeapon(); enterCombat()
cast(8024)
tick(15)                                  -- far past FRESH_S with no readable id
check(codeOf(host) == "FT", "the cast still names it, got " .. codeOf(host))
leaveCombat(); setWeapon(true, 50 * MIN * 1000, 29)
tick(1.5)
check(codeOf(host) == "FT", "the first plain id after the cast is the cast's imbue, got " .. codeOf(host))
setWeapon(false); tick(3)
setWeapon(true, 40 * MIN * 1000, 29); tick(1.5)
check(codeOf(host) == "FT", "and it is taught, got " .. codeOf(host))
""")

case("a_confirmed_different_id_beats_a_pending_cast")(r"""
local spec, host = up({ learned = { "Flametongue Weapon", "Frostbrand Weapon" } })
setWeapon(true, 59 * MIN * 1000, 8); cast(8033)      -- 8 = Frostbrand
setWeapon(true, 58 * MIN * 1000, 7); cast(8017)      -- 7 = Rockbiter
tick(1.5)
check(codeOf(host) == "RB", "taught: " .. codeOf(host))
cast(8024)                                           -- Flametongue is cast, the weapon still says 7
tick(1.5)
check(codeOf(host) == "FT", "behind the cast the cast names it, got " .. codeOf(host))
setWeapon(true, 3599 * 1000, 8); tick(1.5)           -- but it now shows 8, already known as Frostbrand
check(codeOf(host) == "FB", "a different confirmed id wins over the cast, got " .. codeOf(host))
""")

case("an_id_seen_behind_a_cast_is_not_taught_as_the_cast")(r"""
local spec, host = up({ learned = { "Flametongue Weapon" } })
setWeapon(true, 59 * MIN * 1000, 29); cast(8017)     -- Rockbiter, id 29
setWeapon(true, 58 * MIN * 1000, 29); cast(8024)     -- Flametongue over it; the weapon still shows 29
tick(0.5)
check(codeOf(host) == "FT", "named by the cast while behind it")
setWeapon(true, 3599 * 1000, 5); tick(1.5)
check(codeOf(host) == "FT", "named when 5 shows")
setWeapon(false); tick(3)
setWeapon(true, 40 * MIN * 1000, 29); tick(1.5)      -- Rockbiter again, no cast seen
check(codeOf(host) == "RB", "29 was never taught as Flametongue, got " .. codeOf(host))
""")

case("a_zero_enchant_id_is_no_id_and_teaches_nothing")(r"""
local spec, host = up({ learned = { "Flametongue Weapon" } })
setWeapon(true, 59 * MIN * 1000, 0); cast(8024); tick(1.5)
check(codeOf(host) == "FT", "named by the cast")
setWeapon(false); tick(3)
setWeapon(true, 40 * MIN * 1000, 0); tick(1.5)
check(codeOf(host) == "IM", "an enchant with no id and no cast is not Flametongue, got " .. codeOf(host))
""")

case("a_cast_over_an_imbue_keeps_the_sixty_minutes_until_the_weapon_catches_up")(r"""
local spec, host = up({ learned = { "Flametongue Weapon" } })
setWeapon(true, 20 * MIN * 1000, 29); tick(1.5)
check(wordOf(host) == "20m", "read first")
cast(8024)                                  -- the immediate read still shows the OLD enchant: 20 minutes, id 29
check(wordOf(host) == "60m", "the cast's sixty minutes survive the old enchant's read, got " .. wordOf(host))
tick(0.5)
check(wordOf(host) == "60m", "and the next one, got " .. wordOf(host))
setWeapon(true, 3599 * 1000, 5)
fire("UNIT_INVENTORY_CHANGED", "player")
check(wordOf(host) == "59m", "then the new enchant's own time takes over, got " .. wordOf(host))
""")

case("imbue_with_no_name_to_be_had_is_the_generic_code")(r"""
local spec, host = up({ learned = { "Flametongue Weapon" } })
setWeapon(true, 40 * MIN * 1000, 123456)
tick(1.5)
check(imbueChip(host).code.text == "IM", "an unknown enchant with two imbues known and no cast is IM, got " .. tostring(imbueChip(host).code.text))
""")

case("with_one_imbue_known_an_unnamed_enchant_is_that_imbue")(r"""
local spec, host = up({})
setWeapon(true, 40 * MIN * 1000, 123456)
tick(1.5)
check(imbueChip(host).code.text == "RB", "the one imbue you know is the honest guess, got " .. tostring(imbueChip(host).code.text))
""")

case("a_cast_in_combat_sets_a_sixty_minute_imbue_when_the_read_is_secret")(r"""
local spec, host = up({ learned = { "Windfury Weapon" } })
setWeapon(false); tick(1.5)
check(imbueChip(host).word.text == "IMBUE", "missing first")
secretWeapon(); enterCombat()
cast(8232)
check(imbueChip(host).word.text == "60m", "a cast in combat reads 60m at once, got " .. tostring(imbueChip(host).word.text))
check(imbueChip(host).code.text == "WF", "named by the cast")
""")

case("a_cast_does_not_flash_missing_before_the_weapon_updates")(r"""
local spec, host = up({})
setWeapon(false); tick(1.5)
cast(10399)
tick(0.5)
check(imbueChip(host).word.text == "60m", "the cast stands while the weapon has not caught up")
setWeapon(true, 3599 * 1000, 0)
fire("UNIT_INVENTORY_CHANGED", "player")
check(imbueChip(host).word.text == "59m", "then the weapon's own time takes over")
setWeapon(false)
tick(2)
check(imbueChip(host).word.text == "IMBUE", "a weapon that really lost it is missing once the grace is over")
""")

case("the_weapons_own_read_ends_the_cast_grace_so_a_real_loss_shows_at_once")(r"""
local spec, host = up({})
setWeapon(false); tick(1.5)
cast(10399)
tick(0.3)
setWeapon(true, 3599 * 1000, 0)
fire("UNIT_INVENTORY_CHANGED", "player")
check(wordOf(host) == "59m", "the weapon caught up")
setWeapon(false)
tick(0.3)                                   -- 0.6 s after the cast, inside its 1.5 s grace
fire("UNIT_INVENTORY_CHANGED", "player")
check(wordOf(host) == "IMBUE", "a weapon that has shown the enchant and lost it is missing now, got " .. wordOf(host))
""")

case("an_imbue_that_is_gone_is_forgotten_and_the_next_one_is_named_afresh")(r"""
local spec, host = up({ learned = { "Flametongue Weapon" } })
cast(8024); setWeapon(true, 3600 * 1000, 5); tick(1.5)
check(imbueChip(host).code.text == "FT", "named")
setWeapon(false); tick(3)
check(imbueChip(host).word.text == "IMBUE", "gone")
setWeapon(true, 1800 * 1000, 123456); tick(1.5)
check(imbueChip(host).code.text == "IM", "a new unknown enchant is not called Flametongue, got " .. tostring(imbueChip(host).code.text))
""")

case("an_off_hand_imbue_counts_when_the_main_hand_has_none")(r"""
local spec, host = up({})
WEAPON = { false, 0, 0, 0, true, 30 * MIN * 1000, 0, 29 }
tick(1.5)
check(imbueChip(host).word.text == "30m", "the off hand's imbue is shown, got " .. tostring(imbueChip(host).word.text))
""")

case("with_both_hands_enchanted_the_chip_shows_the_one_with_the_least_time")(r"""
local spec, host = up({})
setHands({ 50 * MIN * 1000, 0 }, { 20 * MIN * 1000, 0 }); tick(1.5)
check(wordOf(host) == "20m", "off hand has less: " .. wordOf(host))
setHands({ 12 * MIN * 1000, 0 }, { 20 * MIN * 1000, 0 }); tick(1.5)
check(wordOf(host) == "12m", "main hand has less: " .. wordOf(host))
check(imbueChip(host).outline.vertex[1] == MU.UPK[1], "both are quiet above five minutes")
setHands({ 4 * MIN * 1000, 0 }, { 50 * MIN * 1000, 0 }); tick(1.5)
check(wordOf(host) == "4m", "and the expiring colour follows the least")
secretWeapon(); enterCombat(); tick(2 * MIN)
check(wordOf(host) == "2m", "in combat it counts down from that one, got " .. wordOf(host))
""")

case("the_imbue_named_is_the_one_of_the_hand_with_the_least_time")(r"""
local spec, host = up({ learned = { "Windfury Weapon", "Flametongue Weapon" } })
setHands({ 59 * MIN * 1000, 7 }, nil); cast(8232)                    -- Windfury on the main hand: id 7
setHands({ 58 * MIN * 1000, 7 }, { 59 * MIN * 1000, 9 }); cast(8024)  -- Flametongue on the off hand: id 9
tick(1.5)
check(codeOf(host) == "WF" and wordOf(host) == "58m", "main hand is the least: " .. codeOf(host) .. " " .. wordOf(host))
setHands({ 58 * MIN * 1000, 7 }, { 20 * MIN * 1000, 9 }); tick(1.5)
check(codeOf(host) == "FT" and wordOf(host) == "20m", "off hand is the least: " .. codeOf(host) .. " " .. wordOf(host))
""")

case("a_dual_wielder_with_one_bare_weapon_is_asked_for_the_other_imbue")(r"""
local spec, host = up({})
equip(16, "INVTYPE_WEAPONMAINHAND"); equip(17, "INVTYPE_WEAPONOFFHAND")
setHands({ 50 * MIN * 1000, 0 }, nil); tick(1.5)
check(wordOf(host) == "IMBUE", "off hand holds a weapon with no imbue: " .. wordOf(host))
colorIs(imbueChip(host).outline.vertex, MU.AMBER, "amber")
setHands({ 50 * MIN * 1000, 0 }, { 40 * MIN * 1000, 0 }); tick(1.5)
check(wordOf(host) == "40m", "imbued on both hands is quiet again: " .. wordOf(host))
setHands(nil, { 40 * MIN * 1000, 0 }); tick(1.5)
check(wordOf(host) == "IMBUE", "a bare main hand weapon is asked for too: " .. wordOf(host))
secretWeapon(); enterCombat(); tick(1.5)
check(wordOf(host) == "IMBUE", "a secret read in combat keeps what the last plain one said")
""")

case("a_shield_or_an_empty_or_two_handed_off_hand_is_not_a_missing_imbue")(r"""
local spec, host = up({})
equip(16, "INVTYPE_WEAPONMAINHAND"); equip(17, "INVTYPE_SHIELD")
setHands({ 50 * MIN * 1000, 0 }, nil); tick(1.5)
check(wordOf(host) == "50m", "a shield: " .. wordOf(host))
EQUIP[17] = nil; tick(1.5)
check(wordOf(host) == "50m", "nothing in the off hand: " .. wordOf(host))
equip(16, "INVTYPE_2HWEAPON"); tick(1.5)
check(wordOf(host) == "50m", "a two hander: " .. wordOf(host))
equip(17, "INVTYPE_HOLDABLE"); tick(1.5)
check(wordOf(host) == "50m", "a held in off hand frill: " .. wordOf(host))
GetInventoryItemID = function() error("refused") end
tick(1.5)
check(wordOf(host) == "50m", "an item API that raises asks for nothing: " .. wordOf(host))
noDegrade()
""")

case("a_bare_second_weapon_asks_nothing_of_a_shaman_who_knows_no_imbue")(r"""
local spec, host = up({ unlearn = { "Rockbiter Weapon" } })
equip(16, "INVTYPE_WEAPONMAINHAND"); equip(17, "INVTYPE_WEAPONOFFHAND")
setHands({ 50 * MIN * 1000, 0 }, nil); tick(1.5)
check(wordOf(host) == "50m", "an oil on one weapon, no imbue known: " .. wordOf(host))
""")

case("a_cast_answers_the_missing_hand_reminder_until_the_weapon_says_otherwise")(r"""
local spec, host = up({})
equip(16, "INVTYPE_WEAPONMAINHAND"); equip(17, "INVTYPE_WEAPONOFFHAND")
setHands({ 50 * MIN * 1000, 29 }, nil); tick(1.5)
check(wordOf(host) == "IMBUE", "asked first")
cast(10399)
check(wordOf(host) == "60m", "the cast clears the ask at once, got " .. wordOf(host))
setHands({ 50 * MIN * 1000, 29 }, { 3599 * 1000, 31 }); fire("UNIT_INVENTORY_CHANGED", "player")
check(wordOf(host) == "50m", "and both hands are now imbued, got " .. wordOf(host))
""")

# --------------------------------------------------------------------------------- secrets that say what they are

case("a_secret_main_flag_is_unreadable_and_changes_nothing")(r"""
local spec, host = up({})
setWeapon(false); tick(1.5)
check(wordOf(host) == "IMBUE", "missing first")
WEAPON = { SBOOL, SNUM, SNUM, SNUM, SBOOL, SNUM, SNUM, SNUM }
tick(1.5)
check(wordOf(host) == "IMBUE", "a secret flag is not a read, got " .. wordOf(host))
noDegrade()
""")

case("a_secret_off_hand_flag_with_no_main_enchant_is_unreadable")(r"""
local spec, host = up({})
setWeapon(false); tick(1.5)
WEAPON = { false, 0, 0, 0, SBOOL, SNUM, SNUM, SNUM }
tick(1.5)
check(wordOf(host) == "IMBUE", "a secret off hand flag is not an enchant, got " .. wordOf(host))
noDegrade()
""")

case("a_plain_enchant_with_a_secret_time_and_id_is_used_without_touching_them")(r"""
local spec, host = up({})
setWeapon(true, 20 * MIN * 1000, 0); tick(1.5)
WEAPON = { true, SNUM, 0, SNUM, false, 0, 0, 0 }
tick(5 * MIN)
check(wordOf(host) == "15m", "the stored expiry counts down, got " .. wordOf(host))
WEAPON = { true, SNUM, 0, SNUM, SBOOL, SNUM, 0, SNUM }
tick(1)
check(wordOf(host) == "14m", "a secret off hand beside it changes nothing, got " .. wordOf(host))
WEAPON = { true, 10 * MIN * 1000, 0, 5, true, SNUM, 0, SNUM }
tick(1)
check(wordOf(host) == "10m", "one readable time of two is used, got " .. wordOf(host))
noDegrade()
""")

case("a_secret_spell_id_on_a_cast_asks_the_spell_book_nothing")(r"""
local spec, host = up({})
setWeapon(false); tick(1.5)
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", SNUM)
check(#LEAKED == 0, "a secret spell id reached " .. tostring(LEAKED[1]))
check(wordOf(host) == "IMBUE", "and nothing changed")
noDegrade()
""")

# --------------------------------------------------------------------------------- events and throttle

case("the_weapon_is_read_on_the_events_and_a_one_second_tick_and_not_more")(r"""
local spec, host = up({})
local n = WEAPON_CALLS
tick(0.3); tick(0.3); tick(0.3)
check(WEAPON_CALLS == n, "no read inside a second, got " .. (WEAPON_CALLS - n))
tick(0.3)
check(WEAPON_CALLS == n + 1, "one read at the second, got " .. (WEAPON_CALLS - n))
fire("UNIT_INVENTORY_CHANGED", "player")
check(WEAPON_CALLS == n + 2, "UNIT_INVENTORY_CHANGED of the player reads")
fire("UNIT_INVENTORY_CHANGED", "party1")
check(WEAPON_CALLS == n + 2, "another unit's inventory does not")
fire("PLAYER_EQUIPMENT_CHANGED", 16, false)
check(WEAPON_CALLS == n + 3, "PLAYER_EQUIPMENT_CHANGED reads")
""")

case("a_cast_of_another_spell_or_unit_changes_nothing")(r"""
local spec, host = up({})
setWeapon(false); tick(1.5)
local n = WEAPON_CALLS
cast(403)
fire("UNIT_SPELLCAST_SUCCEEDED", "target", "guid", 8017)
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", SECRET)
check(WEAPON_CALLS == n, "none of them read the weapon, got " .. (WEAPON_CALLS - n))
check(imbueChip(host).word.text == "IMBUE", "still missing")
check(shieldChip(host).word.text == "SHIELD", "and the shield is not claimed to be cast")
""")

case("events_and_the_tick_stop_while_hidden_and_return_when_shown")(r"""
local spec, host = up({})
tick(1.5)
spec.onHide("lower")
local n = WEAPON_CALLS
tick(5)
fire("UNIT_INVENTORY_CHANGED", "player")
check(WEAPON_CALLS == n, "a hidden module reads nothing, got " .. (WEAPON_CALLS - n))
spec.onShow("lower")
check(WEAPON_CALLS > n, "showing it reads at once")
local m = WEAPON_CALLS
spec.onShow("lower")
fire("UNIT_INVENTORY_CHANGED", "player")
check(WEAPON_CALLS == m + 2, "a second onShow reads once and does not double the events, got " .. (WEAPON_CALLS - m))
""")

# --------------------------------------------------------------------------------- shield chip

case("shield_up_shows_the_orb_count")(r"""
local spec, host = up({})
setShield(3); tick(1.5)
local c = shieldChip(host)
check(c.word.text == "3", "three orbs, got " .. tostring(c.word.text))
colorIs(c.outline.vertex, MU.UPK, "gold outline")
colorIs(c.word.textColor, MU.FG, "quiet text")
near3(c.word.textColor[4], MU.UP_ALPHA, "quiet alpha")
setShield(2); fire("UNIT_AURA", "player")
check(shieldChip(host).word.text == "2", "an orb spent reads 2 on the aura event, got " .. tostring(shieldChip(host).word.text))
""")

case("shield_missing_is_the_amber_word")(r"""
local spec, host = up({})
noShield(); tick(1.5)
local c = shieldChip(host)
check(c.word.text == "SHIELD", "the word is SHIELD, got " .. tostring(c.word.text))
colorIs(c.outline.vertex, MU.AMBER, "amber outline")
colorIs(c.word.textColor, MU.AMBER, "amber word")
check(c.code.text == "LS", "the code stays LS")
""")

case("shield_up_without_a_readable_count_says_on")(r"""
local spec, host = up({})
setShield(0); tick(1.5)
check(shieldChip(host).word.text == "ON", "an aura with no applications says ON, got " .. tostring(shieldChip(host).word.text))
""")

case("shield_in_combat_reads_the_cached_snapshot_as_an_estimate")(r"""
local spec, host = up({})
setShield(3); tick(1.5)
setShield(1)                        -- the frozen snapshot is not refreshed in combat; whatever it holds is stale
enterCombat(); noShield()
tick(1.5)
check(shieldChip(host).word.text == "~3", "frozen: the last live count, marked as an estimate, got " .. tostring(shieldChip(host).word.text))
tick(11 * MIN)
check(shieldChip(host).word.text == "SHIELD", "past the cached expiry it has fallen off, got " .. tostring(shieldChip(host).word.text))
""")

case("shield_missing_before_combat_stays_missing_in_combat_until_cast")(r"""
local spec, host = up({})
noShield(); tick(1.5)
enterCombat(); tick(1.5)
check(shieldChip(host).word.text == "SHIELD", "still missing in combat")
cast(10432)
check(shieldChip(host).word.text == "~3", "a cast in combat shows a fresh shield as an estimate, got " .. tostring(shieldChip(host).word.text))
leaveCombat(); setShield(3); tick(1.5)
check(shieldChip(host).word.text == "3", "and the real count when combat ends")
""")

case("a_shield_cast_in_combat_is_believed_for_ten_minutes_and_no_longer")(r"""
local spec, host = up({})
noShield(); tick(1.5)
enterCombat(); tick(1.5)
cast(10432)
check(shieldChip(host).word.text == "~3", "cast in combat")
tick(9 * MIN)
check(shieldChip(host).word.text == "~3", "still believed at nine minutes, got " .. shieldChip(host).word.text)
tick(2 * MIN)
check(shieldChip(host).word.text == "SHIELD", "gone after its ten minutes, got " .. shieldChip(host).word.text)
colorIs(shieldChip(host).outline.vertex, MU.AMBER, "amber")
cast(10432)
check(shieldChip(host).word.text == "~3", "and a new cast is believed again")
""")

case("a_shield_cast_over_an_older_one_in_combat_outlives_the_older_expiry")(r"""
local spec, host = up({})
setShield(3, NOW + 120); tick(1.5)
enterCombat(); tick(100)
check(shieldChip(host).word.text == "~3", "the old shield is still there")
cast(324)
tick(300)
check(shieldChip(host).word.text == "~3", "the recast shield is not judged by the old expiry, got " .. shieldChip(host).word.text)
""")

case("a_shield_seen_before_combat_with_no_expiry_is_believed_for_ten_minutes_from_the_last_read")(r"""
local spec, host = up({})
setShield(3, 0); tick(1.5)
check(shieldChip(host).word.text == "3", "up with no expiry the aura told")
enterCombat(); tick(1.5)
check(shieldChip(host).word.text == "~3", "estimate in combat")
tick(8 * MIN)
check(shieldChip(host).word.text == "~3", "still believed, got " .. shieldChip(host).word.text)
tick(2 * MIN)
check(shieldChip(host).word.text == "SHIELD", "not forever: it lasts ten minutes, got " .. shieldChip(host).word.text)
""")

case("a_water_shield_up_hides_the_shield_chip_instead_of_nagging")(r"""
local spec, host = up({})
waterShield(); tick(1.5)
check(not shown(shieldChip(host)), "a Water Shield is not a missing Lightning Shield")
check(shown(imbueChip(host)), "the imbue chip stays")
waterShield(true); fire("UNIT_AURA", "player")
check(not shown(shieldChip(host)), "found by spell id when the aura has no name")
enterCombat(); tick(1.5)
check(not shown(shieldChip(host)), "and in combat from the last live read")
cast(324)
check(shown(shieldChip(host)) and shieldChip(host).word.text == "~3", "a Lightning Shield cast in combat shows")
leaveCombat(); noShield(); tick(2)
check(shieldChip(host).word.text == "SHIELD", "with neither up it asks again, got " .. tostring(shieldChip(host).word.text))
""")

case("lightning_shield_up_beside_nothing_else_is_unaffected_by_the_water_shield_rule")(r"""
local spec, host = up({})
SNAP = { buffs = { { name = "Lightning Shield", count = 2, expirationTime = NOW + 600, spellId = 324 } } }
tick(1.5)
check(shieldChip(host).word.text == "2", "unchanged")
""")

case("shield_with_nothing_ever_read_is_a_question_mark")(r"""
local spec, host = up({ noAuras = true })
tick(1.5)
check(shieldChip(host).word.text == "?", "no aura snapshot at all reads ?, got " .. tostring(shieldChip(host).word.text))
colorIs(shieldChip(host).outline.vertex, MU.HOLLOW_STROKE, "hollow")
boot({})
enterCombat()
local spec2, host2 = mount("lower")
tick(1.5)
check(shieldChip(host2).word.text == "?", "frozen on the first read with no cache reads ?, got " .. tostring(shieldChip(host2).word.text))
""")

# --------------------------------------------------------------------------------- not learned

case("an_unlearned_spell_is_asked_about_once_until_the_spellbook_changes")(r"""
local spec, host = up({ unlearn = { "Lightning Shield" } })
tick(1.5)
local book, info = BOOK_CALLS, INFO_CALLS
for _ = 1, 5 do tick(1.5) end
check(BOOK_CALLS == book and INFO_CALLS == info, "five ticks asked the spell book " .. (BOOK_CALLS - book) .. " and spell info " .. (INFO_CALLS - info) .. " times")
fire("UNIT_INVENTORY_CHANGED", "player"); fire("UNIT_AURA", "player")
check(BOOK_CALLS == book and INFO_CALLS == info, "and so did the events")
learn("Lightning Shield"); fire("LEARNED_SPELL_IN_TAB")
check(shown(shieldChip(host)), "LEARNED_SPELL_IN_TAB asks again")
local spec2, host2 = up({ unlearn = { "Lightning Shield" } })
learn("Lightning Shield"); fire("PLAYER_LEVEL_UP", 9)
check(shown(shieldChip(host2)), "PLAYER_LEVEL_UP asks again")
""")

case("showing_the_module_again_asks_the_spell_book_again")(r"""
local spec, host = up({ unlearn = { "Lightning Shield" } })
tick(1.5)
check(not shown(shieldChip(host)), "not learned")
learn("Lightning Shield")
tick(1.5)
check(not shown(shieldChip(host)), "a tick alone does not ask")
spec.onHide("lower"); spec.onShow("lower")
check(shown(shieldChip(host)), "a show does")
""")

case("a_shield_you_have_not_learned_draws_no_chip")(r"""
local spec, host = up({ unlearn = { "Lightning Shield" } })
noShield(); tick(1.5)
check(not shown(shieldChip(host)), "no shield chip before Lightning Shield is learned")
check(shown(imbueChip(host)), "the imbue chip is still there")
local _, txt = drawn(host)
for _, s in ipairs(txt) do check(s.text ~= "SHIELD" and s.text ~= "LS", "a word of the shield chip is drawn: " .. tostring(s.text)) end
learn("Lightning Shield"); fire("SPELLS_CHANGED")
check(shown(shieldChip(host)), "the chip appears when the spell is learned")
check(shieldChip(host).word.text == "SHIELD", "and then it asks for it")
""")

case("an_imbue_you_have_not_learned_draws_no_chip")(r"""
local spec, host = up({ unlearn = { "Rockbiter Weapon" } })
setWeapon(false); tick(1.5)
check(not shown(imbueChip(host)), "no imbue chip before any imbue is learned")
check(shown(shieldChip(host)), "the shield chip is still there")
learn("Rockbiter Weapon"); fire("PLAYER_LEVEL_UP", 2)
check(shown(imbueChip(host)), "the chip appears when Rockbiter is learned")
""")

case("an_enchant_on_the_weapon_shows_even_with_no_imbue_learned")(r"""
local spec, host = up({ unlearn = { "Rockbiter Weapon" } })
setWeapon(true, 20 * MIN * 1000, 0); tick(1.5)
check(shown(imbueChip(host)) and imbueChip(host).word.text == "20m", "an oil or a stone on the weapon is still shown")
setWeapon(false); tick(1.5)
check(not shown(imbueChip(host)), "and hidden again when it is gone")
""")

case("a_shaman_who_knows_nothing_yet_draws_nothing")(r"""
local spec, host = up({ learn = false })
tick(1.5)
local tex, txt = drawn(host)
check(#tex == 0 and #txt == 0, "nothing to remind about, got " .. #tex .. " textures and " .. #txt .. " strings")
""")

case("any_other_class_draws_nothing_and_a_secret_class_token_too")(r"""
for _, tok in ipairs({ "MAGE", "WARLOCK" }) do
    local spec, host = up({ classToken = tok })
    tick(1.5)
    local tex, txt = drawn(host)
    check(#tex == 0 and #txt == 0, tok .. " draws " .. #tex .. " textures")
end
local spec, host = up({ classToken = SECRET })
tick(1.5)
local tex = drawn(host)
check(#tex == 0, "a secret class token draws nothing")
""")


# --------------------------------------------------------------------------------- the target side rule, with the real areas

case("no_chip_is_drawn_with_no_target_and_the_module_stops_with_it")(r"""
-- Parker, live: a Shaman with no target saw the IMBUE chip floating alone while the rest of the target side was hidden.
-- The real GunsightAreas gates the class host on the target and calls onHide / onShow on that edge.
boot({ realAreas = true })
local Areas = FS.GunsightAreas
local host = Areas.Host("lower")
check(host ~= nil and Areas.AreaOf("class") == "lower", "the Shaman module sits in the lower area")
local function chipsShown()
    local n = 0
    local tex, txt = drawn(host)
    for _, t in ipairs(tex) do if t.path and t.path:find("slice_cut2_", 1, true) then n = n + 1 end end
    return n + #txt
end
tick(1.5)
check(chipsShown() > 0, "with a target the imbue chip is drawn")
local reads = WEAPON_CALLS
TARGET.exists = false
fire("PLAYER_TARGET_CHANGED")
check(not isVisible(host), "no target: the class host is not visible")
check(chipsShown() == 0, "no target: no chip texture or text is visible, got " .. chipsShown())
tick(5)
fire("UNIT_INVENTORY_CHANGED", "player")
check(WEAPON_CALLS == reads, "no target: the module stopped reading, got " .. (WEAPON_CALLS - reads) .. " reads")
TARGET.exists = true
fire("PLAYER_TARGET_CHANGED")
check(isVisible(host) and chipsShown() > 0, "a target brings the chips back")
check(WEAPON_CALLS > reads, "and the module reads again at once")
noDegrade()
""")

case("an_imbue_cast_with_no_target_is_remembered_when_a_target_brings_the_chip_back")(r"""
-- The normal flow: buff up before the pull. With no target the module is hidden and its full event set is off, but the
-- cast is still heard, so the imbue is named by it (and taught) when the chip returns.
boot({ realAreas = true, noTarget = true, learned = { "Flametongue Weapon" } })
local host = FS.GunsightAreas.Host("lower")
setWeapon(true, 59 * MIN * 1000, 33)       -- 33: an enchant id nobody taught yet
local reads = WEAPON_CALLS
cast(8024)                                 -- Flametongue, hidden
cast(324)                                  -- and the shield
check(WEAPON_CALLS == reads, "a hidden cast reads nothing, got " .. (WEAPON_CALLS - reads) .. " reads")
TARGET.exists = true
fire("PLAYER_TARGET_CHANGED")
check(isVisible(host), "the target brings the host back")
check(codeOf(host) == "FT", "the imbue cast with no target names it, got " .. codeOf(host))
check(wordOf(host) ~= "IMBUE", "and it is not asked for again, got " .. wordOf(host))
TARGET.exists = false
fire("PLAYER_TARGET_CHANGED")
setWeapon(false); tick(2)
setWeapon(true, 40 * MIN * 1000, 33)       -- later, no cast seen: id 33 was taught as Flametongue
TARGET.exists = true
fire("PLAYER_TARGET_CHANGED")
check(codeOf(host) == "FT", "the id was taught by the hidden cast, got " .. codeOf(host))
noDegrade()
""")

case("the_shaman_chip_stays_hidden_when_it_is_built_with_no_target")(r"""
boot({ realAreas = true, noTarget = true })
local host = FS.GunsightAreas.Host("lower")
tick(3)
local tex, txt = drawn(host)
check(#tex == 0 and #txt == 0, "nothing drawn with no target, got " .. #tex .. " textures and " .. #txt .. " strings")
local reads = WEAPON_CALLS
tick(5)
check(WEAPON_CALLS == reads, "and the module never started reading")
TARGET.exists = true
fire("PLAYER_TARGET_CHANGED")
tex, txt = drawn(host)
check(#tex > 0 and #txt > 0, "a target brings the chips")
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
    out.append(("player_text_never_says_tape", None if not re.search(r"\"[^\"]*\btape\b[^\"]*\"", src, re.I) else "player text says tape"))
    out.append(("reads_no_aura_api_directly", None if not re.search(r"C_UnitAuras|UnitAura|UnitBuff|GetAuraDataBy", src)
                else "the shield reads FS.PlayerAuras only, never an aura API"))
    for tex in ("slice_cut2_fill_c3", "slice_cut2_outline_c3", "slice_cut2_glow_c3"):
        out.append((f"texture_{tex}_exists", None if (TEXTURES / f"{tex}.tga").exists() else f"{tex}.tga is missing"))
    return out


def run_case(name: str, body: str, mu: dict) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    g = lua.globals()
    g.LAYOUT_SRC = LAYOUT.read_text(encoding="utf-8")
    g.CONFIG_SRC = CONFIG.read_text(encoding="utf-8")
    g.GUNSIGHT_SRC = GUNSIGHT.read_text(encoding="utf-8")
    g.SHAMAN_SRC = SHAMAN.read_text(encoding="utf-8")
    g.AREAS_SRC = AREAS.read_text(encoding="utf-8")
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

    if not SHAMAN.exists():
        print(f"FAIL  {SHAMAN.name} is missing")
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
