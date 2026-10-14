#!/usr/bin/env python3
"""Runs the real FrameHelpers.lua event registration helpers headless.

Some events do not exist on this client (LEARNED_SPELL_IN_TAB is one: registering it raises). Every module registers its
spell and learn events through FS.FrameHelpers.RegisterEvent / RegisterEvents, which must skip an unknown event without a
chat line, record it once in ForeverSTUwaveDB.unknownEvents, and never create or replace the saved table.

The checks pin: a known event registers; an unknown one is skipped with no print and no AddMessage; it is recorded once;
C_EventUtils.IsEventValid is asked first when the client has it and RegisterEvent is then never called for a refused name;
without it a refused registration is the signal; unit events; a read-only profile and a missing saved table record nothing
and a table that appears later receives the record; and a source scan that fails if LEARNED_SPELL_IN_TAB comes back.

The mock is strict. It is NOT the real client.

    python3 tools/eventregister-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
HELPERS = ADDON / "Core/FrameHelpers.lua"
BANNED_EVENT = "LEARNED_SPELL_IN_TAB"

MOCK = r"""
function check(c, msg) if not c then error(msg or "check failed", 2) end end

PRINTS, ADDED = {}, {}
function print(...) PRINTS[#PRINTS + 1] = table.concat({ ... }, " ") end
DEFAULT_CHAT_FRAME = { AddMessage = function(_, m) ADDED[#ADDED + 1] = m end }
function time() return 1700000000 end

KNOWN_EVENTS = {}
for e in ([[SPELLS_CHANGED PLAYER_LEVEL_UP PLAYER_ENTERING_WORLD PLAYER_REGEN_ENABLED LEARNED_SPELL_IN_SKILL_LINE UNIT_SPELLCAST_SUCCEEDED]]):gmatch("%S+") do
    KNOWN_EVENTS[e] = true
end
REGISTER_CALLS = 0
local FrameMT = {}
FrameMT.__index = FrameMT
function FrameMT:RegisterEvent(e)
    REGISTER_CALLS = REGISTER_CALLS + 1
    if not KNOWN_EVENTS[e] then
        error("Frame:RegisterEvent(): Attempt to register unknown event \"" .. tostring(e) .. "\"", 2)
    end
    self.events[e] = true
end
function FrameMT:RegisterUnitEvent(e, ...)
    REGISTER_CALLS = REGISTER_CALLS + 1
    if not KNOWN_EVENTS[e] then
        error("Frame:RegisterUnitEvent(): Attempt to register unknown event \"" .. tostring(e) .. "\"", 2)
    end
    self.events[e] = true
    self.units = { ... }
end
function FrameMT:SetScript(n, fn) self.scripts[n] = fn end
FRAMES = {}
function CreateFrame()
    local f = setmetatable({ events = {}, scripts = {} }, FrameMT)
    FRAMES[#FRAMES + 1] = f
    return f
end
function fire(event, ...)
    for _, f in ipairs({ unpack(FRAMES) }) do
        if f.events[event] and f.scripts.OnEvent then f.scripts.OnEvent(f, event, ...) end
    end
end

READ_ONLY = false
SECRET = setmetatable({}, {
    __index = function() error("SECRET_OP: index", 2) end, __newindex = function() error("SECRET_OP: write", 2) end,
    __pairs = function() error("SECRET_OP: pairs", 2) end,
})
FS = { IsSecret = function(v) return v == SECRET end, Theme = {}, Config = { IsReadOnly = function() return READ_ONLY end } }
ForeverSTUwaveDB = { profiles = {} }

function load()
    local fn = assert(loadstring(HELPERS_SRC, "@FrameHelpers.lua"))
    fn("forever-stuwave", FS)
    return FS.FrameHelpers
end
function frame() return CreateFrame("Frame") end
"""

CASES: list[tuple[str, str]] = []


def case(name: str):
    def deco(body: str):
        CASES.append((name, body))
        return body
    return deco


case("a_known_event_registers")(r"""
local H = load()
local f = frame()
check(H.RegisterEvent(f, "SPELLS_CHANGED") == true, "reports success")
check(f.events.SPELLS_CHANGED, "registered")
check(ForeverSTUwaveDB.unknownEvents == nil, "nothing recorded for a known event")
""")

case("an_unknown_event_is_skipped_silently_and_recorded")(r"""
local H = load()
local f = frame()
check(H.RegisterEvent(f, "LEARNED_SPELL_IN_TAB") == false, "reports the skip")
check(not f.events.LEARNED_SPELL_IN_TAB, "not registered")
check(#PRINTS == 0 and #ADDED == 0, "no chat line: " .. tostring(PRINTS[1] or ADDED[1]))
local rec = ForeverSTUwaveDB.unknownEvents and ForeverSTUwaveDB.unknownEvents.LEARNED_SPELL_IN_TAB
check(rec, "recorded in the saved table")
check(ForeverSTUwaveDB.profiles ~= nil, "the saved table was not replaced")
""")

case("registering_a_list_skips_only_the_unknown_ones")(r"""
local H = load()
local f = frame()
local n = H.RegisterEvents(f, { "SPELLS_CHANGED", "LEARNED_SPELL_IN_TAB", "PLAYER_LEVEL_UP", "LEARNED_SPELL_IN_SKILL_LINE" })
check(n == 3, "three registered, got " .. tostring(n))
check(f.events.SPELLS_CHANGED and f.events.PLAYER_LEVEL_UP and f.events.LEARNED_SPELL_IN_SKILL_LINE, "the known ones are on")
check(#PRINTS == 0 and #ADDED == 0, "silent")
""")

case("an_unknown_event_is_recorded_once")(r"""
local H = load()
H.RegisterEvent(frame(), "LEARNED_SPELL_IN_TAB")
ForeverSTUwaveDB.unknownEvents.LEARNED_SPELL_IN_TAB.time = 1
H.RegisterEvent(frame(), "LEARNED_SPELL_IN_TAB")
check(ForeverSTUwaveDB.unknownEvents.LEARNED_SPELL_IN_TAB.time == 1, "the first record stands")
""")

case("event_utils_is_asked_first_and_a_refused_name_is_never_registered")(r"""
C_EventUtils = { IsEventValid = function(e) return KNOWN_EVENTS[e] == true end }
local H = load()
REGISTER_CALLS = 0
local f = frame()
check(H.RegisterEvent(f, "LEARNED_SPELL_IN_TAB") == false, "skipped")
check(REGISTER_CALLS == 0, "RegisterEvent was not called for a name the client calls invalid")
check(ForeverSTUwaveDB.unknownEvents.LEARNED_SPELL_IN_TAB, "recorded")
check(H.RegisterEvent(f, "SPELLS_CHANGED") == true and f.events.SPELLS_CHANGED, "a valid name still registers")
""")

case("a_throwing_event_utils_falls_back_to_the_registration_itself")(r"""
C_EventUtils = { IsEventValid = function() error("boom") end }
local H = load()
local f = frame()
check(H.RegisterEvent(f, "SPELLS_CHANGED") == true and f.events.SPELLS_CHANGED, "valid name registers")
check(H.RegisterEvent(f, "LEARNED_SPELL_IN_TAB") == false, "unknown is refused by the client")
check(#PRINTS == 0 and #ADDED == 0, "silent")
""")

case("unit_events_use_register_unit_event")(r"""
local H = load()
local f = frame()
check(H.RegisterEvent(f, "UNIT_SPELLCAST_SUCCEEDED", "player") == true, "registered")
check(f.units and f.units[1] == "player", "filtered to the player")
check(H.RegisterEvent(f, "NO_SUCH_UNIT_EVENT", "player") == false, "an unknown unit event is skipped")
check(#PRINTS == 0 and #ADDED == 0, "silent")
check(ForeverSTUwaveDB.unknownEvents.NO_SUCH_UNIT_EVENT, "recorded")
""")

case("a_read_only_profile_records_nothing")(r"""
READ_ONLY = true
local H = load()
H.RegisterEvent(frame(), "LEARNED_SPELL_IN_TAB")
check(ForeverSTUwaveDB.unknownEvents == nil, "read only: the saved table is untouched")
check(#PRINTS == 0 and #ADDED == 0, "silent")
""")

case("a_missing_saved_table_is_not_created_and_the_record_lands_once_it_exists")(r"""
ForeverSTUwaveDB = nil
local H = load()
H.RegisterEvent(frame(), "LEARNED_SPELL_IN_TAB")
check(ForeverSTUwaveDB == nil, "the helper never creates the saved table")
ForeverSTUwaveDB = { profiles = {} }
fire("PLAYER_ENTERING_WORLD")
check(ForeverSTUwaveDB.unknownEvents and ForeverSTUwaveDB.unknownEvents.LEARNED_SPELL_IN_TAB, "flushed when the table exists")
check(ForeverSTUwaveDB.profiles ~= nil, "not replaced")
""")

case("an_event_that_registers_fine_clears_its_stale_record")(r"""
local H = load()
ForeverSTUwaveDB.unknownEvents = { SPELLS_CHANGED = { time = 5 }, OTHER_EVENT = { time = 6 } }
check(H.RegisterEvent(frame(), "SPELLS_CHANGED") == true, "registered")
check(ForeverSTUwaveDB.unknownEvents.SPELLS_CHANGED == nil, "the old refusal is dropped")
check(ForeverSTUwaveDB.unknownEvents.OTHER_EVENT, "other records stay")
H.RegisterEvent(frame(), "UNIT_SPELLCAST_SUCCEEDED", "player")
check(ForeverSTUwaveDB.unknownEvents.OTHER_EVENT, "a unit event clears only its own record")
ForeverSTUwaveDB.unknownEvents.UNIT_SPELLCAST_SUCCEEDED = { time = 7 }
H.RegisterEvent(frame(), "UNIT_SPELLCAST_SUCCEEDED", "player")
check(ForeverSTUwaveDB.unknownEvents.UNIT_SPELLCAST_SUCCEEDED == nil, "a unit registration clears it too")
""")

case("a_read_only_profile_keeps_a_stale_record_and_a_pending_one_is_dropped_on_success")(r"""
READ_ONLY = true
local H = load()
ForeverSTUwaveDB.unknownEvents = { SPELLS_CHANGED = { time = 5 } }
H.RegisterEvent(frame(), "SPELLS_CHANGED")
check(ForeverSTUwaveDB.unknownEvents.SPELLS_CHANGED, "read only: nothing is written or removed")
READ_ONLY = false
ForeverSTUwaveDB = nil
H.RegisterEvent(frame(), "LEARNED_SPELL_IN_TAB")
KNOWN_EVENTS.LEARNED_SPELL_IN_TAB = true
H.RegisterEvent(frame(), "LEARNED_SPELL_IN_TAB")
ForeverSTUwaveDB = { profiles = {} }
fire("PLAYER_ENTERING_WORLD")
check(ForeverSTUwaveDB.unknownEvents == nil or ForeverSTUwaveDB.unknownEvents.LEARNED_SPELL_IN_TAB == nil,
    "an event that registered fine is not written as refused")
""")

case("a_success_before_the_saved_table_exists_clears_the_stale_record_once_it_does")(r"""
ForeverSTUwaveDB = nil
local H = load()
check(H.RegisterEvent(frame(), "SPELLS_CHANGED") == true, "registered while the table is not there yet")
ForeverSTUwaveDB = { unknownEvents = { SPELLS_CHANGED = { time = 5 }, OTHER_EVENT = { time = 6 } } }
fire("PLAYER_ENTERING_WORLD")
check(ForeverSTUwaveDB.unknownEvents.SPELLS_CHANGED == nil, "the old refusal is dropped once the table exists")
check(ForeverSTUwaveDB.unknownEvents.OTHER_EVENT, "other records stay")
""")

case("a_read_only_profile_keeps_the_stale_record_a_late_success_would_have_cleared")(r"""
ForeverSTUwaveDB = nil
local H = load()
H.RegisterEvent(frame(), "SPELLS_CHANGED")
READ_ONLY = true
ForeverSTUwaveDB = { unknownEvents = { SPELLS_CHANGED = { time = 5 } } }
fire("PLAYER_ENTERING_WORLD")
check(ForeverSTUwaveDB.unknownEvents.SPELLS_CHANGED, "read only: not removed")
""")

case("records_say_why_and_a_plain_success_clears_only_a_name_record")(r"""
local H = load()
H.RegisterEvent(frame(), "NO_SUCH_UNIT_EVENT", "player")
check(ForeverSTUwaveDB.unknownEvents.NO_SUCH_UNIT_EVENT.why == "unit", "a refused unit registration says unit")
H.RegisterEvent(frame(), "NO_SUCH_EVENT")
check(ForeverSTUwaveDB.unknownEvents.NO_SUCH_EVENT.why == "invalid", "a refused plain registration says invalid")
ForeverSTUwaveDB.unknownEvents.UNIT_SPELLCAST_SUCCEEDED = { time = 5, why = "unit" }
check(H.RegisterEvent(frame(), "UNIT_SPELLCAST_SUCCEEDED") == true, "the plain registration works")
check(ForeverSTUwaveDB.unknownEvents.UNIT_SPELLCAST_SUCCEEDED, "a plain success does not erase a bad unit token record")
check(H.RegisterEvent(frame(), "UNIT_SPELLCAST_SUCCEEDED", "player") == true, "the unit registration works")
check(ForeverSTUwaveDB.unknownEvents.UNIT_SPELLCAST_SUCCEEDED == nil, "a unit success clears it")
ForeverSTUwaveDB.unknownEvents.SPELLS_CHANGED = { time = 5, why = "invalid" }
H.RegisterEvent(frame(), "SPELLS_CHANGED")
check(ForeverSTUwaveDB.unknownEvents.SPELLS_CHANGED == nil, "a plain success clears a name record")
C_EventUtils = { IsEventValid = function(e) return KNOWN_EVENTS[e] == true end }
H = load()
H.RegisterEvent(frame(), "NO_SUCH_EVENT_2")
check(ForeverSTUwaveDB.unknownEvents.NO_SUCH_EVENT_2.why == "invalid", "an event the client calls invalid says invalid")
""")

case("a_legacy_refused_record_is_cleared_by_a_plain_success")(r"""
local H = load()
ForeverSTUwaveDB.unknownEvents = { SPELLS_CHANGED = { time = 5, why = "refused" }, PLAYER_LEVEL_UP = { time = 5, why = "unit" } }
H.RegisterEvent(frame(), "SPELLS_CHANGED")
H.RegisterEvent(frame(), "PLAYER_LEVEL_UP")
check(ForeverSTUwaveDB.unknownEvents.SPELLS_CHANGED == nil, "the legacy record is cleared")
check(ForeverSTUwaveDB.unknownEvents.PLAYER_LEVEL_UP, "a unit record is still kept by a plain success")
""")

case("a_saved_record_table_that_is_not_plain_is_never_written_to")(r"""
local H = load()
ForeverSTUwaveDB.unknownEvents = "oops"
check(H.RegisterEvent(frame(), "SPELLS_CHANGED") == true, "a string in the way is no error")
check(ForeverSTUwaveDB.unknownEvents == "oops", "left alone")
ForeverSTUwaveDB.unknownEvents = SECRET
check(H.RegisterEvent(frame(), "PLAYER_LEVEL_UP") == true, "a secret in the way is no error")
ForeverSTUwaveDB.unknownEvents = { SPELLS_CHANGED = "oops", PLAYER_LEVEL_UP = SECRET }
H.RegisterEvent(frame(), "SPELLS_CHANGED")
H.RegisterEvent(frame(), "PLAYER_LEVEL_UP")
check(ForeverSTUwaveDB.unknownEvents.SPELLS_CHANGED == nil, "a record that is not a table is dropped by a success")
check(ForeverSTUwaveDB.unknownEvents.PLAYER_LEVEL_UP == SECRET or ForeverSTUwaveDB.unknownEvents.PLAYER_LEVEL_UP == nil, "a secret record is not read")
""")

case("safe_register_unit_event_skips_an_invalid_name_silently_and_reports_other_failures")(r"""
C_EventUtils = { IsEventValid = function(e) return KNOWN_EVENTS[e] == true end }
local H = load()
local reports = {}
local function onFail(event, err) reports[#reports + 1] = event end
REGISTER_CALLS = 0
local f = frame()
H.SafeRegisterUnitEvent(f, "RETAIL_ONLY_EVENT", "player", onFail)
check(#reports == 0, "an invalid name never reaches onFail")
check(REGISTER_CALLS == 0, "and is never registered")
check(ForeverSTUwaveDB.unknownEvents.RETAIL_ONLY_EVENT, "it is recorded")
check(#PRINTS == 0 and #ADDED == 0, "silent")
H.SafeRegisterUnitEvent(f, "UNIT_SPELLCAST_SUCCEEDED", "player", onFail)
check(#reports == 0 and f.units[1] == "player", "a valid one registers")
f.RegisterUnitEvent = function() error("bad unit token") end
H.SafeRegisterUnitEvent(f, "UNIT_SPELLCAST_SUCCEEDED", "nobody", onFail)
check(#reports == 1 and reports[1] == "UNIT_SPELLCAST_SUCCEEDED", "another failure keeps today's onFail")
""")

case("a_frame_without_the_method_or_a_nil_frame_is_not_an_error")(r"""
local H = load()
check(H.RegisterEvent(nil, "SPELLS_CHANGED") == false, "nil frame")
check(H.RegisterEvent({}, "SPELLS_CHANGED") == false, "no RegisterEvent method")
check(H.RegisterEvents(nil, { "SPELLS_CHANGED" }) == 0, "nil frame list")
""")


def static_checks() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    hits = []
    for path in sorted(ADDON.rglob("*")):
        if path.suffix.lower() not in (".lua", ".toc", ".xml", ".md", ".txt") or not path.is_file():
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if BANNED_EVENT in line:
                hits.append(f"{path.relative_to(ADDON.parent)}:{n}")
    out.append(("the_dead_learn_event_is_not_named_anywhere_in_the_addon",
                None if not hits else f"{BANNED_EVENT} is not an event on this client: " + ", ".join(hits)))
    chat = []
    for path in sorted(ADDON.rglob("*.lua")):
        src = path.read_text(encoding="utf-8", errors="replace")
        for n, line in enumerate(src.splitlines(), 1):
            if "cannot be registered on this client" in line:
                chat.append(f"{path.relative_to(ADDON.parent)}:{n}")
    out.append(("no_module_words_a_refused_registration_for_the_chat_frame",
                None if not chat else "a refused registration must go through FrameHelpers.RegisterEvent: " + ", ".join(chat)))
    for rel, needle in (("Modules/CombatHud/GunsightShamanShocks.lua", "the cast ledger cannot listen"),
                        ("Modules/CastBars/CastBars.lua", 'ReportRegisterFailure("PLAYER_ENTERING_WORLD"'),
                        ("Modules/Pet/PetCastBar.lua", 'ReportRegisterFailure("PLAYER_ENTERING_WORLD"')):
        text = (ADDON / rel).read_text(encoding="utf-8")
        out.append((f"{Path(rel).stem}_does_not_print_a_refused_registration",
                    None if needle not in text else f"{rel} still reports a refused registration: {needle}"))
    src = HELPERS.read_text(encoding="utf-8")
    code = re.sub(r"--.*", "", src)
    body = re.search(r"function Helpers\.RegisterEvent\b.*?\nend\n", code, re.S)
    out.append(("the_register_helper_never_prints",
                None if body and not re.search(r"\bprint\b|AddMessage|LogDegradeOnce", body.group(0))
                else "RegisterEvent must not print or call LogDegradeOnce"))
    return out


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

    def report(name: str, err: str | None) -> None:
        nonlocal failures
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      " + err.replace("\n", "\n      "))

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
