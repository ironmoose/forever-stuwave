#!/usr/bin/env python3
"""Runs the real PanelSkins.lua `HookInlineColorRewrite` headless against a mock button.

Blizzard writes a quest title row with an inline black color code (`NORMAL_QUEST_DISPLAY` is
`|cff000000%s|r`) BEFORE our row skin runs, so a hook that only watches FUTURE SetText calls leaves
the first-acquired row black on the dark panel (playtest 2026-10-04: all three trainer quests black
after /reload, the plain option row light). The properties pinned here:

  * text already on the target when the hook is installed is rewritten at once;
  * later SetText / SetFormattedText calls are still rewritten;
  * a bright state colour (red "can't afford") is never touched, hooked or not;
  * hooking the same target twice installs one hook (one rewrite, no recursion);
  * the emitted code is the exact parchment hex (#bfe9d6), rounded not truncated;
  * a secret current text, a number or a secret SetText argument is skipped without error;
  * a SetText that throws inside the rewrite does not leave the target stuck (it keeps rewriting);
  * a rewrite that keeps throwing logs one degrade line per session (the latch), and a missing
    FS.LogDegradeOnce neither errors nor spends the latch.

The dark-text gate is the real `IsDarkText` text lifted out of Theme.lua, so a gate change fails
here. The mock is NOT the real client. Run:

    python3 tools/panelskins-harness.py

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

ADDON = Path(__file__).resolve().parent.parent / "forever-stuwave"
PANELSKINS_SRC = (ADDON / "Core/PanelSkins.lua").read_text(encoding="utf-8")
THEME_SRC = (ADDON / "Core/Theme.lua").read_text(encoding="utf-8")


def theme_dark_text_lua() -> str:
    """The real Luma / DARK_TEXT_LUMA / IsDarkText text from Theme.lua, so the gate cannot drift."""
    luma = re.search(r"local function Luma\(.*?\nend\n", THEME_SRC, re.S)
    thresh = re.search(r"^local DARK_TEXT_LUMA = [0-9.]+$", THEME_SRC, re.M)
    gate = re.search(r"local function IsDarkText\(.*?\nend\n", THEME_SRC, re.S)
    parchment = re.search(r"^Theme\.COLOR_TEXT_PARCHMENT = \{.*?\}", THEME_SRC, re.M)
    if not (luma and thresh and gate and parchment):
        sys.exit("panelskins-harness: could not find Luma/IsDarkText/COLOR_TEXT_PARCHMENT in Theme.lua")
    return "\n".join(
        [luma.group(0), thresh.group(0), gate.group(0), parchment.group(0).replace("Theme.", "THEME.", 1)]
    )


MOCK = r"""
SlashCmdList = {}
function CreateFrame() return setmetatable({}, { __index = function() return function() end end }) end
function InCombatLockdown() return false end

-- hooksecurefunc(tbl, name, fn): the real one swaps tbl[name] for a wrapper that runs the original
-- then fn with the same arguments; a call made from inside fn goes back through the wrapper.
function hooksecurefunc(tbl, name, fn)
    local orig = tbl[name]
    tbl[name] = function(...)
        local r = orig(...)
        fn(...)
        return r
    end
end

-- A Button's text accessors. `writes` counts every underlying SetText, hook re-writes included.
function NewButton(initial)
    local b = { text = initial, writes = 0 }
    function b:SetText(t)
        self.writes = self.writes + 1
        -- failOnRewrite: throw once when the hook writes the rewritten (parchment) code back;
        -- failForever keeps throwing on every such write (what the log latch exists for).
        if self.failOnRewrite and type(t) == "string" and t:find(PARCHMENT_CODE, 1, true) then
            if not self.failForever then self.failOnRewrite = false end
            error("SetText blew up")
        end
        self.text = t
    end
    function b:SetFormattedText(fmt, ...) self.writes = self.writes + 1; self.text = string.format(fmt, ...) end
    function b:GetText() return self.text end
    return b
end

function LoadPanelSkins()
    THEME = {}
    local degraded = {}
    local FS = {
        Theme = THEME,
        degraded = degraded, -- every LogDegradeOnce call as {key, msg}; the real one does not dedupe
        LogDegradeOnce = function(key, msg) degraded[#degraded + 1] = { key, msg } end,
        -- SECRET_TEXT carries a dark code, so skipping it (not rewriting it) is observable.
        IsSecret = function(v) return v == SECRET_TEXT end,
    }
    assert(loadstring(THEME_DARK_TEXT_SRC .. "\nTHEME.IsDarkText = IsDarkText", "@Theme.lua(gate)"))()
    local chunk = assert(loadstring(PANELSKINS_SRC, "@PanelSkins.lua"))
    chunk("forever-stuwave", FS)
    return FS
end

-- The code the rewrite must emit for the parchment token, spelled out rather than recomputed so a
-- truncating format (0.749 * 255 -> be, not bf) cannot agree with itself.
PARCHMENT_CODE = "|cffbfe9d6"
function ParchmentCode() return PARCHMENT_CODE end
SECRET_TEXT = "|cff000000secret|r"
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("text_already_on_the_target_is_rewritten_when_it_is_hooked", """
    local FS = LoadPanelSkins()
    local row = NewButton("|cff000000Rattling the Rattlecages|r")
    FS.PanelSkins.HookInlineColorRewrite(row)
    assert(not row:GetText():find("|cff000000", 1, true), "dark code survived: " .. row:GetText())
    assert(row:GetText() == "|cffbfe9d6Rattling the Rattlecages|r", row:GetText())
""")

case("later_set_formatted_text_is_still_rewritten", """
    local FS = LoadPanelSkins()
    local row = NewButton("")
    FS.PanelSkins.HookInlineColorRewrite(row)
    row:SetFormattedText("|cff000000%s|r", "Coming to Terms")
    assert(row:GetText() == ParchmentCode() .. "Coming to Terms|r", row:GetText())
""")

case("a_bright_state_colour_is_left_alone", """
    local FS = LoadPanelSkins()
    local row = NewButton("|cffff2020Can't afford|r")
    FS.PanelSkins.HookInlineColorRewrite(row)
    assert(row:GetText() == "|cffff2020Can't afford|r", row:GetText())
    assert(row.writes == 0, "a bright line must not be re-written, got " .. row.writes .. " writes")
""")

case("hooking_twice_installs_one_hook_and_does_not_recurse", """
    local FS = LoadPanelSkins()
    local row = NewButton("")
    FS.PanelSkins.HookInlineColorRewrite(row)
    FS.PanelSkins.HookInlineColorRewrite(row)
    row:SetText("|cff000000Dark|r")
    assert(row:GetText() == ParchmentCode() .. "Dark|r", row:GetText())
    assert(row.writes == 2, "one write plus one rewrite expected, got " .. row.writes)
""")

case("a_secret_current_text_is_skipped_without_error", """
    local FS = LoadPanelSkins()
    local row = NewButton(SECRET_TEXT)
    FS.PanelSkins.HookInlineColorRewrite(row)
    assert(row:GetText() == SECRET_TEXT and row.writes == 0, "secret text was touched: " .. row:GetText())
""")

case("a_number_or_secret_set_text_argument_does_not_throw", """
    local FS = LoadPanelSkins()
    local row = NewButton("")
    FS.PanelSkins.HookInlineColorRewrite(row)
    row:SetText(5)
    row:SetText(SECRET_TEXT)
    assert(row:GetText() == SECRET_TEXT and row.writes == 2, "writes: " .. row.writes)
""")

case("a_set_text_that_throws_inside_the_rewrite_does_not_stick_the_target", """
    local FS = LoadPanelSkins()
    local row = NewButton("")
    FS.PanelSkins.HookInlineColorRewrite(row)
    row.failOnRewrite = true
    row:SetText("|cff000000First|r") -- the rewrite's inner SetText throws once; the hook must absorb it
    row:SetText("|cff000000Second|r")
    assert(row:GetText() == ParchmentCode() .. "Second|r", "target stopped rewriting: " .. row:GetText())
""")

case("a_rewrite_that_keeps_throwing_logs_one_degrade_line_for_the_session", """
    local FS = LoadPanelSkins()
    local loadLogs = #FS.degraded -- the module load itself may log (RequireExport); count only after it
    local row = NewButton("")
    FS.PanelSkins.HookInlineColorRewrite(row)
    row.failOnRewrite, row.failForever = true, true
    row:SetText("|cff000000First|r") -- both rewrites throw; the once-per-session latch logs only the first
    row:SetText("|cff000000Second|r")
    local logged = #FS.degraded - loadLogs
    assert(logged == 1, "expected exactly one degrade log, got " .. logged)
    local call = FS.degraded[loadLogs + 1]
    assert(call[1] == "inline_rewrite", "degrade key: " .. tostring(call[1]))
    assert(type(call[2]) == "string", "degrade message is not a string")
""")


case("a_missing_degrade_logger_does_not_error_or_spend_the_log_latch", """
    local FS = LoadPanelSkins()
    local loadLogs = #FS.degraded
    local row = NewButton("")
    FS.PanelSkins.HookInlineColorRewrite(row)
    row.failOnRewrite, row.failForever = true, true
    FS.LogDegradeOnce = nil
    row:SetText("|cff000000First|r") -- throws with no logger: must be absorbed silently
    FS.LogDegradeOnce = function(key, msg) FS.degraded[#FS.degraded + 1] = { key, msg } end
    row:SetText("|cff000000Second|r") -- the logger is back: the unspent latch lets this one log
    local logged = #FS.degraded - loadLogs
    assert(logged == 1, "expected exactly one degrade log once the logger returned, got " .. logged)
""")


def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.globals().PANELSKINS_SRC = PANELSKINS_SRC
    rt.globals().THEME_DARK_TEXT_SRC = theme_dark_text_lua()
    try:
        rt.execute(MOCK)
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


def main() -> int:
    failures = 0
    total = len(CASES)
    for name, body in CASES:
        err = run_case(body)
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}: {err}")
    print(f"{total - failures}/{total} checks passed")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
