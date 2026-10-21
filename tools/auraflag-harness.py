#!/usr/bin/env python3
"""Runs the real FrameHelpers.lua engine drawn aura flag helpers headless.

On this client the player's aura data is SECRET in combat: it cannot be read, compared or branched on. The engine
still knows. An AuraContainer slot (AddAuraSlot) is shown by the engine exactly while its aura is present, so
slot:IsShown() is a boolean that means "the aura is up" and is secret in combat. The one sanctioned consumer of a
secret boolean is Region:SetAlphaFromBoolean(flag, alphaIfTrue, alphaIfFalse). FS.FrameHelpers.AuraFlag wraps that:

  * Ready(region, slot)           both engine methods exist (nothing is called);
  * Drive(region, slot, up, down) hands slot:IsShown() straight to region:SetAlphaFromBoolean, never reading it;
  * Agrees(slot, up)              out of combat only: does the slot's PLAIN flag match what the aura read says;
  * MayHaveRemoved(info)          can this UNIT_AURA payload mean an aura was removed (secret lists are only typed).

The checks pin: the secret flag reaches the setter untouched (the mock records any index, compare, arithmetic or
truth test as SECRET_OP and a case fails on one), the polarity, every failure mode (a missing or throwing setter or
IsShown) answering false or nil instead of raising, and the payload classification table.

The mock is strict. It is NOT the real client.

    python3 tools/auraflag-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
HELPERS = ADDON / "Core/FrameHelpers.lua"

MOCK = r"""
local realType, realPcall, realTostring = type, pcall, tostring
function check(c, msg) if not c then error(msg or "check failed", 2) end end

-- Secret sentinels: type() still reports the pretended type, but every operation raises SECRET_OP.
SENT, TRUTH, TOUCHES = {}, setmetatable({}, { __mode = "k" }), {}
local function sentinel(kind, truth)
    local function bad(what) return function() error("SECRET_OP " .. what, 2) end end
    local s = setmetatable({}, {
        __index = bad("index"), __newindex = bad("newindex"), __call = bad("call"), __concat = bad("concat"),
        __add = bad("add"), __sub = bad("sub"), __mul = bad("mul"), __div = bad("div"), __mod = bad("mod"),
        __pow = bad("pow"), __unm = bad("unm"), __lt = bad("lt"), __le = bad("le"), __eq = bad("eq"),
        __len = bad("len"), __tostring = bad("tostring"),
    })
    SENT[s] = kind
    if truth ~= nil then TRUTH[s] = truth end
    return s
end
function type(v) return SENT[v] or realType(v) end
local function noted(...)
    local ok, err = ...
    if not ok and realType(err) == "string" and err:find("SECRET_OP", 1, true) then TOUCHES[#TOUCHES + 1] = err end
    return ...
end
function pcall(f, ...) return noted(realPcall(f, ...)) end
function secretBool(truth) return sentinel("boolean", truth and true or false) end
ST, SB = sentinel("table"), sentinel("boolean", true)

-- A region with the engine setter; `got` records exactly what the setter was handed.
function region()
    local r = { got = nil, alpha = nil }
    function r:SetAlphaFromBoolean(flag, whenTrue, whenFalse)
        self.got = flag
        local truth = TRUTH[flag]
        if truth == nil then
            if realType(flag) ~= "boolean" then error("bad boolean argument", 2) end
            truth = flag
        end
        self.alpha = truth and whenTrue or whenFalse
    end
    return r
end
-- A slot whose IsShown answers `flag` (a plain boolean or a secret one).
function slot(flag) return { IsShown = function() return flag end } end

function print() end
function CreateFrame() return { RegisterEvent = function() end, SetScript = function() end } end
FS = { IsSecret = function(v) return SENT[v] ~= nil end, Theme = {}, Config = { IsReadOnly = function() return false end } }
ForeverSTUwaveDB = { profiles = {} }

function load()
    local fn = assert(loadstring(HELPERS_SRC, "@FrameHelpers.lua"))
    fn("forever-stuwave", FS)
    local F = FS.FrameHelpers.AuraFlag
    check(F, "FS.FrameHelpers.AuraFlag is missing")
    return F
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str):
    def deco(body: str):
        CASES.append((name, body))
        return body
    return deco


case("ready_needs_both_engine_methods_and_calls_neither")(r"""
local F = load()
local r, s = region(), slot(true)
check(F.Ready(r, s) == true, "a region with the setter and a slot with IsShown")
check(F.Ready(nil, s) == false and F.Ready(r, nil) == false and F.Ready(nil, nil) == false, "a missing frame")
check(F.Ready({}, s) == false, "no SetAlphaFromBoolean on the region")
r.SetAlphaFromBoolean = false
check(F.Ready(r, s) == false, "a setter that is not a function")
check(F.Ready(region(), {}) == false, "no IsShown on the slot")
check(r.got == nil, "Ready never calls the setter")
check(#TOUCHES == 0, "no secret touched")
""")

case("drive_hands_the_secret_flag_to_the_setter_untouched")(r"""
local F = load()
local r = region()
local flag = secretBool(true)
check(F.Drive(r, slot(flag), 0, 1) == true, "reports that the setter ran")
check(rawequal(r.got, flag), "the setter received the secret itself, not a copy or a derived value")
check(r.alpha == 0, "aura up: the up alpha")
local down = secretBool(false)
F.Drive(r, slot(down), 0, 1)
check(rawequal(r.got, down) and r.alpha == 1, "aura down: the down alpha")
check(#TOUCHES == 0, "no secret touched: " .. tostring(TOUCHES[1]))
""")

case("drive_polarity_follows_its_arguments_with_a_plain_flag_too")(r"""
local F = load()
local r = region()
F.Drive(r, slot(true), 0.25, 0.75); check(r.alpha == 0.25, "plain up")
F.Drive(r, slot(false), 0.25, 0.75); check(r.alpha == 0.75, "plain down")
F.Drive(r, slot(true), 1, 0); check(r.alpha == 1, "reversed pair, up")
F.Drive(r, slot(false), 1, 0); check(r.alpha == 0, "reversed pair, down")
""")

case("drive_never_raises_and_says_false_when_it_cannot")(r"""
local F = load()
check(F.Drive(nil, slot(true), 0, 1) == false, "no region")
check(F.Drive(region(), nil, 0, 1) == false, "no slot")
check(F.Drive({}, slot(true), 0, 1) == false, "no setter")
check(F.Drive(region(), {}, 0, 1) == false, "no IsShown")
check(F.Drive(region(), { IsShown = function() error("boom: IsShown") end }, 0, 1) == false, "IsShown throws")
local r = region()
function r:SetAlphaFromBoolean() error("boom: setter") end
check(F.Drive(r, slot(true), 0, 1) == false, "the setter throws")
check(F.Drive(region(), slot(nil), 0, 1) == false, "IsShown answers nothing: the setter refuses it")
check(#TOUCHES == 0, "no secret touched")
""")

case("agrees_compares_only_a_plain_flag")(r"""
local F = load()
check(F.Agrees(slot(true), true) == true and F.Agrees(slot(false), false) == true, "equal")
check(F.Agrees(slot(true), false) == false and F.Agrees(slot(false), true) == false, "different")
check(F.Agrees(slot(secretBool(true)), true) == nil, "a secret flag says nothing")
check(F.Agrees(slot(nil), true) == nil and F.Agrees(slot("yes"), true) == nil, "a non boolean says nothing")
check(F.Agrees({}, true) == nil and F.Agrees(nil, true) == nil, "no IsShown, no slot")
check(F.Agrees({ IsShown = function() error("boom") end }, true) == nil, "a throwing IsShown says nothing")
check(#TOUCHES == 0, "no secret touched: " .. tostring(TOUCHES[1]))
""")

case("may_have_removed_classifies_a_unit_aura_payload")(r"""
local F = load()
local function want(label, info, expected)
    check(F.MayHaveRemoved(info) == expected, label .. ": expected " .. tostring(expected))
end
-- possible removal, or a payload that cannot say
want("no payload", nil, true)
want("empty payload", {}, true)
want("secret payload", ST, true)
want("secret boolean payload", SB, true)
want("string payload", "x", true)
want("secret removed list", { removedAuraInstanceIDs = ST }, true)
want("plain removed list", { removedAuraInstanceIDs = { 5 } }, true)
want("removed beside added", { addedAuras = { {} }, removedAuraInstanceIDs = { 9 } }, true)
want("empty lists only", { removedAuraInstanceIDs = {}, addedAuras = {}, updatedAuraInstanceIDs = {} }, true)
-- adds and refreshes only
want("plain added", { addedAuras = { {} } }, false)
want("secret added", { addedAuras = ST }, false)
want("secret updated", { updatedAuraInstanceIDs = ST }, false)
want("plain updated", { updatedAuraInstanceIDs = { 4 } }, false)
want("secret adds and updates, secret full update flag", { addedAuras = ST, updatedAuraInstanceIDs = ST, isFullUpdate = SB }, false)
check(#TOUCHES == 0, "no secret touched: " .. tostring(TOUCHES[1]))
""")

case("may_have_removed_survives_a_payload_that_raises_on_access")(r"""
local F = load()
local hostile = setmetatable({}, { __index = function() error("boom: payload field") end })
check(F.MayHaveRemoved(hostile) == true, "an unreadable payload may hide a removal")
""")


def run_case(name: str, body: str) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.globals().HELPERS_SRC = HELPERS.read_text(encoding="utf-8")
    try:
        lua.execute(body)
    except LuaError as e:
        return str(e)
    return None


def main() -> int:
    failures = 0
    for name, body in CASES:
        err = run_case(name, body)
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      " + err.replace("\n", "\n      "))
    print(f"\n{len(CASES) - failures}/{len(CASES)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
