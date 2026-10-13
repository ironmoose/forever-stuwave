"""stage_runtime.py: comment stripping keeps code and newlines, and the scan catches flagged vocabulary."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_runtime as sr  # noqa: E402

TOOL = Path(__file__).resolve().parent / "stage_runtime.py"

SAMPLE = '''-- header
local a = 1 -- trailing
--[[ block
spanning ]] local b = "x -- not a comment"
--[==[ level two ]] still comment ]==]
local c = [[long -- string
with --[[ markers ]]
local d = 'it' .. "q\\"--" --[[inline]]local e = 2
return a --[=[x]=]+b
'''


def test_strips_comments_keeps_strings_and_every_newline() -> None:
    out, strings, _ = sr.strip_lua(SAMPLE)
    assert out.count("\n") == SAMPLE.count("\n")
    assert "header" not in out and "trailing" not in out and "spanning" not in out
    assert "level two" not in out and "inline" not in out
    assert 'local b = "x -- not a comment"' in out
    assert "long -- string\nwith --[[ markers ]]" in out
    assert [text for _, text in strings][:2] == ["x -- not a comment", "long -- string\nwith --[[ markers "]
    assert "local d = 'it' .." in out and "local e = 2" in out
    assert not any(line != line.rstrip() for line in out.splitlines() if "long" not in line)


def test_block_comment_between_tokens_does_not_join_them() -> None:
    out, _, _ = sr.strip_lua("local a=1 b=a--[[x]]c=2\nreturn a--[[x]]\n")
    assert "a c" in out.replace("  ", " ")


def test_toc_drops_hash_comments_but_keeps_directives() -> None:
    out = sr.strip_toc("## Title: X\n# note\nCore/A.lua\n")
    assert out == "## Title: X\n\nCore/A.lua\n"


def _run(tmp_path: Path, lua: str) -> subprocess.CompletedProcess[str]:
    (tmp_path / "A.lua").write_text(lua)
    return subprocess.run([sys.executable, str(TOOL), str(tmp_path)], capture_output=True, text=True, check=False)


def test_cli_rewrites_verifies_and_passes_clean_source(tmp_path: Path) -> None:
    result = _run(tmp_path, "-- note\nlocal t = { a = 1, b = 2 } -- more\nreturn t\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "A.lua").read_text() == "\nlocal t = { a = 1, b = 2 }\nreturn t\n"
    assert "verified" in result.stdout


def test_cli_fails_on_flagged_strings_and_identifiers_but_not_comments(tmp_path: Path) -> None:
    clean = _run(tmp_path, "-- fsdev harness bot bridge\nlocal x = FILL_BOT\n")
    assert clean.returncode == 0, clean.stdout + clean.stderr
    for source in ('print("sent by fsdev")', 'local s = "pixel bridge"', "local harnessMode = 1",
                   'local s = [[typed  by hand]]'):
        bad = _run(tmp_path, source + "\n")
        assert bad.returncode == 1 and "A.lua:1" in bad.stderr, source


def test_cli_fails_when_the_source_does_not_compile(tmp_path: Path) -> None:
    result = _run(tmp_path, "local = = 1\n")
    assert result.returncode == 1 and "compile" in result.stderr
