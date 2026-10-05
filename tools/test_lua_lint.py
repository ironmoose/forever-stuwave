"""Tests for addons/lua-lint.py, the compiler-backed Lua lint.

lua-lint.py has a hyphenated filename and lives in a directory with no
package __init__.py, so it is loaded by file path via importlib (same pattern as
test_fsdev.py). It is driven through its real main() with argv, so the exit-code
contract the deploy gate depends on is what gets tested.

The headline check is CHECK 1 (use-before-local-declaration): a function
compiled above a later `local NAME` binds NAME as a nil global. Fixtures are
real files under testdata/lua_lint/ rather than inline Lua strings.

Run with::

    python3 -m pytest tools/test_lua_lint.py -q
"""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path

import pytest

pytest.importorskip("lupa")

HERE = Path(__file__).resolve().parent
LINT_PATH = HERE / "lua-lint.py"
FIXTURES = HERE / "testdata" / "lua_lint"


def _load_lint() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("lua_lint", LINT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def lint() -> types.ModuleType:
    return _load_lint()


def _run(lint, monkeypatch, capsys, *args: str) -> tuple[int, str]:
    monkeypatch.setattr("sys.argv", ["lua-lint.py", *args])
    code = lint.main()
    return code, capsys.readouterr().out


@pytest.mark.parametrize(
    ("fixture", "name"),
    [
        ("bad_file_scope_constant.lua", "INSET"),
        ("bad_function_above_local_function.lua", "Helper"),
    ],
)
def test_use_before_local_is_flagged_high(lint, monkeypatch, capsys, fixture, name) -> None:
    code, out = _run(lint, monkeypatch, capsys, "--only=1", str(FIXTURES / fixture))
    assert code != 0
    assert "1 high" in out
    assert f"`{name}` compiles to a GLOBAL read" in out


@pytest.mark.parametrize("fixture", ["good_forward_declared.lua", "good_declared_first.lua"])
def test_correct_declaration_order_is_clean(lint, monkeypatch, capsys, fixture) -> None:
    code, out = _run(lint, monkeypatch, capsys, "--only=1", str(FIXTURES / fixture))
    assert code == 0
    assert "0 high" in out


def test_real_addon_tree_has_no_high_findings(lint, monkeypatch, capsys) -> None:
    """Regression guard: a false positive here would block the deploy loop."""
    code, out = _run(lint, monkeypatch, capsys, "--only=1")
    assert code == 0, out
    assert "0 high" in out


def test_fail_on_high_ignores_non_high_findings(lint, monkeypatch, capsys) -> None:
    """Default exit counts every finding; --fail-on high counts only HIGH."""
    low = str(FIXTURES / "low_global_write.lua")
    default_code, _ = _run(lint, monkeypatch, capsys, "--only=3", low)
    gated_code, out = _run(lint, monkeypatch, capsys, "--only=3", "--fail-on", "high", low)
    assert default_code != 0
    assert gated_code == 0
    assert "1 low" in out


def test_global_write_check_allows_addon_saved_variables_but_reports_accidental_globals(
    lint, monkeypatch, capsys, tmp_path,
) -> None:
    source = tmp_path / "saved_globals.lua"
    source.write_text(
        "ForeverSTUwaveDB = {}\nForeverSTUwaveErrorLog = {}\naccidentalGlobal = {}\n",
        encoding="utf-8",
    )
    code, out = _run(lint, monkeypatch, capsys, "--only=3", str(source))

    assert code == 1, out
    assert "1 low" in out
    assert "`accidentalGlobal`" in out
    assert "`ForeverSTUwaveDB`" not in out
    assert "`ForeverSTUwaveErrorLog`" not in out


def test_fail_on_high_still_fails_on_high(lint, monkeypatch, capsys) -> None:
    bad = str(FIXTURES / "bad_function_above_local_function.lua")
    code, _ = _run(lint, monkeypatch, capsys, "--only=1", "--fail-on", "high", bad)
    assert code != 0


def test_globals_dump_env_override(lint, monkeypatch, tmp_path) -> None:
    dump = tmp_path / "globals.txt"
    dump.write_text("SomeApi\nOtherApi\textra\n", encoding="utf-8")
    monkeypatch.setenv("FS_GLOBALS_DUMP", str(dump))
    assert lint.resolve_globals_dump() == dump
    assert lint.load_client_globals(dump) == {"SomeApi", "OtherApi"}


def test_globals_dump_missing_returns_none(lint, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FS_GLOBALS_DUMP", str(tmp_path / "nope.txt"))
    monkeypatch.setattr(lint, "GLOBALS_DUMP_CANDIDATES", [tmp_path / "also-nope.txt"])
    assert lint.resolve_globals_dump() is None


def test_globals_dump_missing_override_does_not_fall_through(lint, monkeypatch, tmp_path) -> None:
    """A set-but-missing override must not silently use a real candidate."""
    real = tmp_path / "real-globals.txt"
    real.write_text("SomeApi\n", encoding="utf-8")
    monkeypatch.setattr(lint, "GLOBALS_DUMP_CANDIDATES", [real])
    monkeypatch.setenv("FS_GLOBALS_DUMP", str(tmp_path / "nope.txt"))
    assert lint.resolve_globals_dump() is None
    monkeypatch.delenv("FS_GLOBALS_DUMP")
    assert lint.resolve_globals_dump() == real


def test_missing_override_note_names_the_override_path(lint, monkeypatch, capsys, tmp_path) -> None:
    missing = tmp_path / "nope.txt"
    monkeypatch.setenv("FS_GLOBALS_DUMP", str(missing))
    _, out = _run(lint, monkeypatch, capsys, "--only=2", str(FIXTURES / "good_declared_first.lua"))
    assert str(missing) in out
    assert "skipping check 2" in out


def test_fail_on_equals_form(lint, monkeypatch, capsys) -> None:
    low = str(FIXTURES / "low_global_write.lua")
    code, _ = _run(lint, monkeypatch, capsys, "--only=3", "--fail-on=high", low)
    assert code == 0
    bad = str(FIXTURES / "bad_function_above_local_function.lua")
    code, _ = _run(lint, monkeypatch, capsys, "--only=1", "--fail-on=high", bad)
    assert code != 0


@pytest.mark.parametrize("argv", [["--fail-on"], ["--fail-on="], ["--fail-on", "bogus"]])
def test_fail_on_bad_value_errors(lint, monkeypatch, capsys, argv) -> None:
    with pytest.raises(SystemExit) as exc:
        _run(lint, monkeypatch, capsys, *argv)
    assert exc.value.code not in (0, None)
    assert "--fail-on" in str(exc.value.code)


def test_exit_code_clamped_to_255(lint, monkeypatch, capsys, tmp_path) -> None:
    """256 findings must not wrap to exit 0 (process exit codes are mod 256)."""
    many = tmp_path / "many.lua"
    many.write_text("".join(f"leak{i} = {i}\n" for i in range(256)), encoding="utf-8")
    code, out = _run(lint, monkeypatch, capsys, "--only=3", str(many))
    assert "256 low" in out
    assert code == 255
