"""Tests for addons/fsdev.py's platform-independent logic.

fsdev.py is a standalone script under addons/, which has no package
__init__.py, so it is loaded by file path via importlib -- same pattern as
addons/ForeverSynthwave/media/test_tga_generators.py. Only the PURE,
platform-independent pieces are exercised here: the Linux char -> key
decomposition table, and the find_saved_vars()/saved_vars() path resolution.
Linux window lookup and focus are tested with a fake process tree and stubbed
subprocess calls; no live client, uinput device, or D-Bus session is touched.
send_text()'s Linux pre-flight validation uses a stubbed _linux_kbd().

Run with::

    cd core && poetry run python -m pytest ../addons/test_fsdev.py -v
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import time
import types
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

FSDEV_PATH = Path(__file__).resolve().parent / "fsdev.py"


def _load_fsdev() -> types.ModuleType:
    """Load fsdev.py as a module without running its __main__ block."""
    spec = importlib.util.spec_from_file_location("fsdev", FSDEV_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fsdev() -> types.ModuleType:
    return _load_fsdev()


# ---------------------------------------------------------------------------
# Module import sanity (the whole point of the platform-dispatch port: this
# must not raise ctypes.WinDLL / other Windows-only errors on Linux)
# ---------------------------------------------------------------------------


def test_module_imports_on_this_platform(fsdev: types.ModuleType) -> None:
    if sys.platform != "win32":
        assert fsdev.user32 is None
    assert fsdev.WTF_ACCOUNTS.name == "Account"


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only uinput timing")
def test_linux_return_has_a_real_key_hold(
    fsdev: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    class _StubKeyboard:
        def key_down(self, name: str) -> None:
            calls.append(f"down:{name}")

        def key_up(self, name: str) -> None:
            calls.append(f"up:{name}")

    monkeypatch.setattr(fsdev, "_linux_kbd", lambda: _StubKeyboard())
    monkeypatch.setattr(fsdev.time, "sleep", lambda seconds: calls.append(f"sleep:{seconds}"))

    fsdev.tap_key(0, fsdev.VK_RETURN)

    assert calls == ["down:enter", "sleep:0.05", "up:enter", "sleep:0.05"]


# ---------------------------------------------------------------------------
# char_to_key -- the Linux char -> (uinput key_name, needs_shift) table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ch", "expected"),
    [
        ("a", ("a", False)),
        ("z", ("z", False)),
        ("A", ("a", True)),
        ("Z", ("z", True)),
        ("0", ("0", False)),
        ("9", ("9", False)),
        (" ", ("space", False)),
        ("/", ("/", False)),
        ("(", ("9", True)),
        (")", ("0", True)),
        ('"', ("'", True)),
        ("_", ("-", True)),
        ("=", ("=", False)),
        (".", (".", False)),
        # Full-ASCII coverage (2026-09-23): every printable-ASCII symbol, not
        # just the handful the reload strings happened to use. The live bug
        # was a WoW colour code ("|cff22e0ff...|r") hard-exiting on "|".
        ("!", ("1", True)),
        ("@", ("2", True)),
        ("#", ("3", True)),
        ("$", ("4", True)),
        ("%", ("5", True)),
        ("^", ("6", True)),
        ("&", ("7", True)),
        ("*", ("8", True)),
        ("+", ("=", True)),
        ("{", ("[", True)),
        ("}", ("]", True)),
        ("|", ("\\", True)),  # the actual live trigger
        (":", (";", True)),
        ("<", (",", True)),
        (">", (".", True)),
        ("?", ("/", True)),
        ("~", ("`", True)),
        ("-", ("-", False)),
        ("[", ("[", False)),
        ("]", ("]", False)),
        ("`", ("`", False)),
        ("\\", ("\\", False)),
        (";", (";", False)),
        ("'", ("'", False)),
        (",", (",", False)),
    ],
)
def test_char_to_key_mappings(
    fsdev: types.ModuleType, ch: str, expected: tuple[str, bool]
) -> None:
    assert fsdev.char_to_key(ch) == expected


def test_char_to_key_unmapped_raises(fsdev: types.ModuleType) -> None:
    """A non-ASCII character has no uinput key mapping and stays a hard error
    -- the loud-fail philosophy applies to genuinely untypable input, not to
    printable ASCII symbols like WoW colour-code pipes."""
    with pytest.raises(ValueError):
        fsdev.char_to_key("•")  # bullet: no uinput key resolves this


def test_char_to_key_rejects_multi_char_input(fsdev: types.ModuleType) -> None:
    with pytest.raises(ValueError):
        fsdev.char_to_key("ab")


def test_char_to_key_covers_full_printable_ascii(fsdev: types.ModuleType) -> None:
    """Every printable ASCII character (0x20-0x7E) must resolve -- this is
    the whole point of the extension: no --run/--cmd line hard-exits on an
    unmapped character anymore."""
    for code in range(0x20, 0x7F):
        fsdev.char_to_key(chr(code))  # raises on failure


def test_char_to_key_emits_only_known_uinput_keys(fsdev: types.ModuleType) -> None:
    """Every base key name char_to_key can emit must exist in
    uinput_keyboard._KEY_NAME_MAP, or the tap would fail at runtime on a live
    device despite passing this pure/unit-tested function."""
    import importlib.util

    kbd_path = (
        FSDEV_PATH.parent / "fsdev_support" / "uinput_keyboard.py"
    )
    spec = importlib.util.spec_from_file_location("test_fsdev_uinput_keyboard", kbd_path)
    assert spec is not None and spec.loader is not None
    kbd_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kbd_module)

    for code in range(0x20, 0x7F):
        key_name, _ = fsdev.char_to_key(chr(code))
        assert key_name in kbd_module._KEY_NAME_MAP, (
            f"char_to_key emits key name {key_name!r} for {chr(code)!r}, "
            "which is not in uinput_keyboard._KEY_NAME_MAP"
        )


def test_char_to_key_resolves_wow_colour_code_string(fsdev: types.ModuleType) -> None:
    """The live trigger: a WoW colour-code string ('|cff22e0ff...|r') must
    resolve every character with no ValueError."""
    for ch in "|cff22e0ffhello|r":
        fsdev.char_to_key(ch)  # raises on failure


def test_inline_reload_and_guarded_reload_chars_all_resolve(
    fsdev: types.ModuleType,
) -> None:
    """Every character fsdev actually sends must resolve -- a silent drop here
    would mean a real /reload attempt truncates mid-command on Linux."""
    for ch in fsdev.GUARDED_RELOAD + fsdev.INLINE_RELOAD:
        fsdev.char_to_key(ch)  # raises on failure


def test_reload_strings_stay_under_max_chat_input(fsdev: types.ModuleType) -> None:
    """WoW's chat box silently truncates past MAX_CHAT_INPUT with no error --
    a future hand-edit growing INLINE_RELOAD past the limit would break the
    addon's own reload mechanism with nothing to catch it until a live client."""
    assert len(fsdev.GUARDED_RELOAD) <= fsdev.MAX_CHAT_INPUT
    assert len(fsdev.INLINE_RELOAD) <= fsdev.MAX_CHAT_INPUT


# ---------------------------------------------------------------------------
# send_text() Linux pre-flight -- an unmapped character must abort the WHOLE
# send before the first keystroke goes out, not partway through. Uses a
# stubbed _linux_kbd() so this never touches a real uinput device.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only send_text branch")
def test_send_text_linux_unmapped_char_exits_before_any_keystroke(
    fsdev: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A string with one unmapped character (partway through) must exit
    cleanly via sys.exit and never call the keyboard at all -- proving the
    pre-flight scan runs before typing starts, not that it merely stops
    partway through an already-live send."""

    class _StubKeyboard:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def key_down(self, name: str) -> None:
            self.calls.append(f"key_down:{name}")

        def key_up(self, name: str) -> None:
            self.calls.append(f"key_up:{name}")

        def tap(self, name: str) -> None:
            self.calls.append(f"tap:{name}")

    stub = _StubKeyboard()
    monkeypatch.setattr(fsdev, "_linux_kbd", lambda: stub)

    with pytest.raises(SystemExit):
        fsdev.send_text(hwnd=0, text="ok \U0001f600 not sent")

    assert stub.calls == []


# ---------------------------------------------------------------------------
# send_text() MAX_CHAT_INPUT guard -- WoW's chat edit box silently TRUNCATES
# anything past 255 characters (no error, just a cut-off string), so a
# too-long --run/--cmd/reload line must be rejected loudly before the first
# keystroke, on EITHER platform. The check sits before the sys.platform
# dispatch, so unlike the Linux-only tests above these run unconditionally.
# ---------------------------------------------------------------------------


def test_send_text_over_max_length_exits_before_platform_dispatch(
    fsdev: types.ModuleType,
) -> None:
    """A string over MAX_CHAT_INPUT must raise SystemExit immediately -- the
    check runs before the sys.platform branch, so this never touches a real
    device or window on either OS and needs no stub/skipif."""
    text = "x" * (fsdev.MAX_CHAT_INPUT + 1)
    with pytest.raises(SystemExit):
        fsdev.send_text(hwnd=0, text=text)


def test_send_text_run_prefix_composition_overflow_rejected(
    fsdev: types.ModuleType,
) -> None:
    """The Lua BODY alone can be <=255 chars and still overflow once main()
    prepends '/run ' before calling send_slash -- this is the actual bug
    class fsdev hit live, so the check must catch the COMPOSED line, not
    just a bare --run body checked in isolation."""
    body = "x" * 252  # <=255 alone
    text = "/run " + body  # 257 chars once composed -- over the limit
    assert len(body) <= fsdev.MAX_CHAT_INPUT
    assert len(text) > fsdev.MAX_CHAT_INPUT
    with pytest.raises(SystemExit):
        fsdev.send_text(hwnd=0, text=text)


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only send_text branch")
def test_send_text_at_max_length_proceeds_to_type(
    fsdev: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A string AT exactly MAX_CHAT_INPUT must NOT be rejected for length --
    it should pass the guard and proceed to actually type, proven by the
    stubbed keyboard receiving calls rather than by the absence of a raise."""

    class _StubKeyboard:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def key_down(self, name: str) -> None:
            self.calls.append(f"key_down:{name}")

        def key_up(self, name: str) -> None:
            self.calls.append(f"key_up:{name}")

        def tap(self, name: str) -> None:
            self.calls.append(f"tap:{name}")

    stub = _StubKeyboard()
    monkeypatch.setattr(fsdev, "_linux_kbd", lambda: stub)

    text = "x" * fsdev.MAX_CHAT_INPUT
    fsdev.send_text(hwnd=0, text=text, fast=True)

    assert stub.calls  # proceeded past the length guard and actually typed


# ---------------------------------------------------------------------------
# find_saved_vars() / saved_vars() -- unaffected by the platform split in
# logic, but WTF_ACCOUNTS's base path is now platform-dependent, so confirm
# the dual-layout search and the "resolve once, cache" behavior still hold.
# ---------------------------------------------------------------------------


def test_find_saved_vars_returns_none_when_wtf_missing(
    fsdev: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fsdev, "WTF_ACCOUNTS", tmp_path / "does-not-exist")
    assert fsdev.find_saved_vars() is None


def test_find_saved_vars_finds_account_wide_layout(
    fsdev: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fsdev, "WTF_ACCOUNTS", tmp_path)
    target = tmp_path / "12345" / "SavedVariables" / "ForeverSynthwave.lua"
    target.parent.mkdir(parents=True)
    target.write_text("ForeverSynthwaveDB = {}\n", encoding="utf-8")

    found = fsdev.find_saved_vars()

    assert found == target


def test_find_saved_vars_finds_per_character_layout(
    fsdev: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fsdev, "WTF_ACCOUNTS", tmp_path)
    target = (
        tmp_path / "12345" / "Realm" / "CharName" / "SavedVariables" / "ForeverSynthwave.lua"
    )
    target.parent.mkdir(parents=True)
    target.write_text("ForeverSynthwaveDB = {}\n", encoding="utf-8")

    found = fsdev.find_saved_vars()

    assert found == target


def test_find_saved_vars_prefers_newest_mtime_across_layouts(
    fsdev: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fsdev, "WTF_ACCOUNTS", tmp_path)
    old = tmp_path / "12345" / "Realm" / "CharName" / "SavedVariables" / "ForeverSynthwave.lua"
    new = tmp_path / "12345" / "SavedVariables" / "ForeverSynthwave.lua"
    old.parent.mkdir(parents=True)
    new.parent.mkdir(parents=True)
    old.write_text("old", encoding="utf-8")
    new.write_text("new", encoding="utf-8")

    old_time = time.time() - 100
    os.utime(old, (old_time, old_time))

    assert fsdev.find_saved_vars() == new


def test_saved_vars_reresolves_when_none_at_import(
    fsdev: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "12345" / "SavedVariables" / "ForeverSynthwave.lua"
    target.parent.mkdir(parents=True)
    target.write_text("ForeverSynthwaveDB = {}\n", encoding="utf-8")
    monkeypatch.setattr(fsdev, "WTF_ACCOUNTS", tmp_path)
    monkeypatch.setattr(fsdev, "SAVED_VARS", None)

    assert fsdev.saved_vars() == target
    assert fsdev.SAVED_VARS == target


# ---------------------------------------------------------------------------
# Linux X11 display discovery. Fake /proc entries and xdotool results keep
# these tests independent of the user's active desktop and WoW client.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only process discovery")
def test_wow_process_displays_reads_only_wow_environment(
    fsdev: types.ModuleType, tmp_path: Path
) -> None:
    wow = tmp_path / "101"
    wow.mkdir()
    (wow / "comm").write_text("WowB.exe\n", encoding="utf-8")
    (wow / "environ").write_bytes(b"HOME=/tmp\0DISPLAY=:2\0WAYLAND_DISPLAY=wayland-0\0")
    other = tmp_path / "102"
    other.mkdir()
    (other / "comm").write_text("terminal\n", encoding="utf-8")
    (other / "environ").write_bytes(b"DISPLAY=:9\0")

    assert fsdev._wow_process_displays(tmp_path) == [":2"]


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only process discovery")
def test_wow_process_displays_is_empty_without_wow(
    fsdev: types.ModuleType, tmp_path: Path
) -> None:
    other = tmp_path / "102"
    other.mkdir()
    (other / "comm").write_text("terminal\n", encoding="utf-8")
    (other / "environ").write_bytes(b"DISPLAY=:9\0")

    assert fsdev._wow_process_displays(tmp_path) == []


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only process discovery")
def test_wow_process_displays_reports_unreadable_wow_environment(
    fsdev: types.ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    wow = tmp_path / "101"
    wow.mkdir()
    (wow / "comm").write_text("WowB.exe\n", encoding="utf-8")
    (wow / "environ").mkdir()

    assert fsdev._wow_process_displays(tmp_path) == []
    assert "environ" in capsys.readouterr().err


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only display routing")
def test_window_discovery_uses_client_display_for_later_xdotool_calls(
    fsdev: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[list[str], str | None]] = []

    def fake_run(
        command: list[str], *, capture_output: bool, text: bool, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        assert capture_output and text
        display = env.get("DISPLAY")
        calls.append((command, display))
        output = "4242\n" if command[1] == "search" and display == ":2" else ""
        if command[1] == "getactivewindow":
            output = "4242\n"
        success = bool(output) or command[1] == "windowactivate"
        return subprocess.CompletedProcess(command, 0 if success else 1, output, "")

    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(fsdev, "_wow_process_displays", lambda: [":2"], raising=False)
    monkeypatch.setattr(fsdev.subprocess, "run", fake_run)
    monkeypatch.setattr(fsdev, "seconds_since_input", lambda: 1.0)
    monkeypatch.setattr(fsdev.time, "sleep", lambda _seconds: None)

    hwnd = fsdev.find_wow_window()
    assert hwnd == 4242
    assert fsdev.user_is_playing(hwnd)
    fsdev.focus(hwnd)

    assert calls == [
        (["xdotool", "search", "--name", "World of Warcraft"], ":0"),
        (["xdotool", "search", "--name", "World of Warcraft"], ":2"),
        (["xdotool", "getactivewindow"], ":2"),
        (["xdotool", "windowactivate", "4242"], ":2"),
    ]


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only display routing")
def test_window_discovery_exits_when_no_display_has_wow(
    fsdev: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str | None] = []

    def fake_run(
        command: list[str], *, capture_output: bool, text: bool, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        assert command == ["xdotool", "search", "--name", "World of Warcraft"]
        assert capture_output and text
        calls.append(env.get("DISPLAY"))
        return subprocess.CompletedProcess(command, 1, "", "no matching window")

    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(fsdev, "_wow_process_displays", lambda: [":2"], raising=False)
    monkeypatch.setattr(fsdev.subprocess, "run", fake_run)

    with pytest.raises(SystemExit, match="WoW window not found"):
        fsdev.find_wow_window()

    assert calls == [":0", ":2"]


# ---------------------------------------------------------------------------
# Gamescope: a nested X display needs an explicit host desktop point before
# any uinput typing. The pointer and xdotool are stubbed throughout.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only Gamescope focus")
def test_nested_display_requires_focus_point_before_typing(
    fsdev: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(fsdev, "_selected_x_env", {"DISPLAY": ":2"})
    monkeypatch.setattr(fsdev, "find_wow_window", lambda: 4242)
    monkeypatch.setattr(fsdev, "user_is_playing", lambda _hwnd: False)
    monkeypatch.setattr(fsdev, "send_slash", lambda *_args, **_kwargs: sent.append("typed"))
    monkeypatch.setattr(sys, "argv", ["fsdev.py", "--no-deploy", "--run", "print(1)"])

    with pytest.raises(SystemExit, match="focus-point"):
        fsdev.main()

    assert sent == []


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only Gamescope focus")
def test_activity_guard_refuses_before_gamescope_host_click(
    fsdev: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(fsdev, "_selected_x_env", {"DISPLAY": ":2"})
    monkeypatch.setattr(fsdev, "find_wow_window", lambda: 4242)
    monkeypatch.setattr(fsdev, "user_is_playing", lambda _hwnd: events.append("guard") or True)
    monkeypatch.setattr(fsdev, "seconds_since_input", lambda: 1.0)
    monkeypatch.setattr(fsdev, "_linux_abs_mouse", lambda: events.append("mouse"), raising=False)
    monkeypatch.setattr(fsdev, "send_slash", lambda *_args, **_kwargs: events.append("typed"))
    monkeypatch.setattr(
        sys, "argv", ["fsdev.py", "--no-deploy", "--focus-point", "100,200", "--run", "x"]
    )

    assert fsdev.main() == 2
    assert events == ["guard"]


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only supervised tap")
def test_tap_once_spaces_after_guard_and_focus_without_later_work(
    fsdev: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    class StubMouse:
        def move_abs(self, x: int, y: int) -> None:
            events.append(f"move:{x},{y}")

        def click(self, button: str) -> None:
            events.append(f"click:{button}")

        def close(self) -> None:
            events.append("close")

        def __enter__(self) -> StubMouse:
            return self

        def __exit__(self, *_args: object) -> None:
            self.close()

    class StubKeyboard:
        def tap(self, key: str) -> None:
            events.append(f"tap:{key}")

        def key_down(self, key: str) -> None:
            events.append(f"down:{key}")

        def key_up(self, key: str) -> None:
            events.append(f"up:{key}")

    def fake_run(
        command: list[str], *, capture_output: bool, text: bool, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        assert capture_output and text
        assert command == ["xdotool", "windowactivate", "4242"]
        events.append(f"activate:{env['DISPLAY']}")
        return subprocess.CompletedProcess(command, 0, "", "")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("tap-once reached deploy, reload, log, or slash input")

    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(fsdev, "_selected_x_env", {"DISPLAY": ":2"})
    monkeypatch.setattr(fsdev, "find_wow_window", lambda: 4242)
    monkeypatch.setattr(fsdev, "user_is_playing", lambda _hwnd: events.append("guard") or False)
    monkeypatch.setattr(fsdev, "_linux_abs_mouse", StubMouse)
    monkeypatch.setattr(fsdev, "_linux_kbd", StubKeyboard)
    monkeypatch.setattr(fsdev.subprocess, "run", fake_run)
    monkeypatch.setattr(fsdev.time, "sleep", lambda _seconds: None)
    for name in ("deploy", "reload_ui", "read_log", "send_slash", "send_text"):
        monkeypatch.setattr(fsdev, name, forbidden)
    monkeypatch.setattr(
        sys, "argv", ["fsdev.py", "--tap-once", "space", "--focus-point", "100,200"]
    )

    assert fsdev.main() == 0
    assert events[:5] == ["guard", "move:100,200", "click:left", "close", "activate::2"]
    assert events[5:] in (["tap:space"], ["down:space", "up:space"])


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only supervised tap")
def test_tap_once_rejects_other_keys_before_input(
    fsdev: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("unsupported tap key reached client or input")

    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(fsdev, "_selected_x_env", {"DISPLAY": ":2"})
    monkeypatch.setattr(fsdev, "find_wow_window", lambda: 4242)
    monkeypatch.setattr(fsdev, "user_is_playing", lambda _hwnd: False)
    for name in ("deploy", "focus", "_linux_kbd", "reload_ui", "send_slash"):
        monkeypatch.setattr(fsdev, name, forbidden)
    monkeypatch.setattr(
        sys, "argv", ["fsdev.py", "--tap-once", "enter", "--focus-point", "100,200"]
    )

    with pytest.raises(SystemExit, match="space"):
        fsdev.main()


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only supervised tap")
@pytest.mark.parametrize("other_args", [["--shot-only", "unused.png"], ["--read-only"]])
def test_tap_once_rejects_modes_that_would_skip_the_tap(
    fsdev: types.ModuleType, monkeypatch: pytest.MonkeyPatch, other_args: list[str]
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("conflicting tap mode reached capture, log, client, or input")

    for name in (
        "screenshot", "read_log", "find_wow_window", "user_is_playing", "focus",
        "_linux_kbd", "deploy",
    ):
        monkeypatch.setattr(fsdev, name, forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        ["fsdev.py", "--tap-once", "space", "--focus-point", "100,200", *other_args],
    )

    with pytest.raises(SystemExit, match="tap-once"):
        fsdev.main()


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only supervised tap")
def test_tap_once_activity_refusal_never_focuses_or_types(
    fsdev: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("activity refusal reached host focus or keyboard")

    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(fsdev, "_selected_x_env", {"DISPLAY": ":2"})
    monkeypatch.setattr(fsdev, "find_wow_window", lambda: 4242)
    monkeypatch.setattr(fsdev, "user_is_playing", lambda _hwnd: True)
    monkeypatch.setattr(fsdev, "seconds_since_input", lambda: 1.0)
    for name in ("_linux_abs_mouse", "focus", "_linux_kbd", "deploy"):
        monkeypatch.setattr(fsdev, name, forbidden)
    monkeypatch.setattr(
        sys, "argv", ["fsdev.py", "--tap-once", "space", "--focus-point", "100,200"]
    )

    assert fsdev.main() == 2


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only supervised tap")
def test_tap_once_releases_space_when_hold_is_interrupted(
    fsdev: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    keys: list[str] = []

    class StubKeyboard:
        def key_down(self, key: str) -> None:
            keys.append(f"down:{key}")

        def key_up(self, key: str) -> None:
            keys.append(f"up:{key}")

    def interrupted_hold(seconds: float) -> None:
        assert seconds == 0.05
        raise RuntimeError("interrupted hold")

    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(fsdev, "_selected_x_env", {"DISPLAY": ":2"})
    monkeypatch.setattr(fsdev, "find_wow_window", lambda: 4242)
    monkeypatch.setattr(fsdev, "user_is_playing", lambda _hwnd: False)
    monkeypatch.setattr(fsdev, "focus", lambda _hwnd: None)
    monkeypatch.setattr(fsdev, "_linux_kbd", StubKeyboard)
    monkeypatch.setattr(fsdev.time, "sleep", interrupted_hold)
    monkeypatch.setattr(
        sys, "argv", ["fsdev.py", "--tap-once", "space", "--focus-point", "100,200"]
    )

    with pytest.raises(RuntimeError, match="interrupted hold"):
        fsdev.main()

    assert keys == ["down:space", "up:space"]


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only Gamescope focus")
def test_gamescope_host_click_and_activation_precede_typing(
    fsdev: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    class StubMouse:
        def move_abs(self, x: int, y: int) -> None:
            events.append(f"move:{x},{y}")

        def click(self, button: str) -> None:
            events.append(f"click:{button}")

        def close(self) -> None:
            events.append("close")

        def __enter__(self) -> StubMouse:
            return self

        def __exit__(self, *_args: object) -> None:
            self.close()

    def fake_run(
        command: list[str], *, capture_output: bool, text: bool, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        assert capture_output and text
        assert command == ["xdotool", "windowactivate", "4242"]
        events.append(f"activate:{env['DISPLAY']}")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(fsdev, "_selected_x_env", {"DISPLAY": ":2"})
    monkeypatch.setattr(fsdev, "find_wow_window", lambda: 4242)
    monkeypatch.setattr(fsdev, "user_is_playing", lambda _hwnd: events.append("guard") or False)
    monkeypatch.setattr(fsdev, "_linux_abs_mouse", StubMouse, raising=False)
    monkeypatch.setattr(fsdev.subprocess, "run", fake_run)
    monkeypatch.setattr(fsdev, "tap_key", lambda _hwnd, _key: events.append("key:enter"))
    monkeypatch.setattr(fsdev, "send_text", lambda _hwnd, line, **_kwargs: events.append(line))
    monkeypatch.setattr(fsdev.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["fsdev.py", "--no-deploy", "--focus-point", "100,200", "--run", "print(1)"],
    )

    assert fsdev.main() == 0
    assert events[:5] == ["guard", "move:100,200", "click:left", "close", "activate::2"]
    assert events[5:] == ["key:enter", "/run print(1)", "key:enter"]
    assert events.count("click:left") == 1
    assert events.count("activate::2") == 1


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only nested reload")
def test_nested_reload_failure_stops_after_one_command_without_reading_old_log(
    fsdev: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[str] = []
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(fsdev, "_selected_x_env", {"DISPLAY": ":2"})
    monkeypatch.setattr(fsdev, "find_wow_window", lambda: 4242)
    monkeypatch.setattr(fsdev, "user_is_playing", lambda _hwnd: False)
    monkeypatch.setattr(fsdev, "saved_vars", lambda: None)
    monkeypatch.setattr(fsdev, "reload_ui", lambda _hwnd, command: commands.append(command))
    monkeypatch.setattr(fsdev, "wait_for_flush", lambda _before: False)
    monkeypatch.setattr(fsdev, "read_log", lambda: pytest.fail("stale log was read"))
    monkeypatch.setattr(fsdev.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        sys, "argv", ["fsdev.py", "--no-deploy", "--focus-point", "100,200"]
    )

    assert fsdev.main() != 0
    assert commands == [fsdev.GUARDED_RELOAD]


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only nested reload")
def test_nested_reload_success_does_not_send_a_second_command(
    fsdev: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[str] = []
    logs: list[str] = []
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(fsdev, "_selected_x_env", {"DISPLAY": ":2"})
    monkeypatch.setattr(fsdev, "find_wow_window", lambda: 4242)
    monkeypatch.setattr(fsdev, "user_is_playing", lambda _hwnd: False)
    monkeypatch.setattr(fsdev, "saved_vars", lambda: None)
    monkeypatch.setattr(fsdev, "reload_ui", lambda _hwnd, command: commands.append(command))
    monkeypatch.setattr(fsdev, "wait_for_flush", lambda _before: True)
    monkeypatch.setattr(fsdev, "read_log", lambda: logs.append("read"))
    monkeypatch.setattr(fsdev.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        sys, "argv", ["fsdev.py", "--no-deploy", "--focus-point", "100,200"]
    )

    assert fsdev.main() == 0
    assert commands == [fsdev.GUARDED_RELOAD]
    assert logs == ["read"]


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only legacy reload")
def test_legacy_reload_flush_failure_stops_without_stale_success(
    fsdev: types.ModuleType, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    commands: list[str] = []
    logs: list[str] = []
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(fsdev, "_selected_x_env", {"DISPLAY": ":0"})
    monkeypatch.setattr(fsdev, "find_wow_window", lambda: 4242)
    monkeypatch.setattr(fsdev, "user_is_playing", lambda _hwnd: False)
    monkeypatch.setattr(fsdev, "saved_vars", lambda: None)
    monkeypatch.setattr(fsdev, "reload_ui", lambda _hwnd, command: commands.append(command))
    monkeypatch.setattr(fsdev, "wait_for_flush", lambda _before: False)
    monkeypatch.setattr(fsdev, "read_log", lambda: logs.append("read"))
    monkeypatch.setattr(fsdev.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(sys, "argv", ["fsdev.py", "--no-deploy"])

    assert fsdev.main() != 0
    assert commands == [fsdev.GUARDED_RELOAD, fsdev.INLINE_RELOAD]
    assert logs == []
    assert "SavedVariables flushed." not in capsys.readouterr().out


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only nested command")
def test_nested_cmd_once_sends_one_command_without_deploy_or_reload(
    fsdev: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[str] = []

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("single command mode reached deploy, reload, or log read")

    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(fsdev, "_selected_x_env", {"DISPLAY": ":2"})
    monkeypatch.setattr(fsdev, "find_wow_window", lambda: 4242)
    monkeypatch.setattr(fsdev, "user_is_playing", lambda _hwnd: False)
    monkeypatch.setattr(fsdev, "deploy", forbidden)
    monkeypatch.setattr(fsdev, "reload_ui", forbidden)
    monkeypatch.setattr(fsdev, "read_log", forbidden)
    monkeypatch.setattr(fsdev, "send_slash", lambda _hwnd, line, **_kwargs: commands.append(line))
    monkeypatch.setattr(
        sys, "argv", ["fsdev.py", "--focus-point", "100,200", "--cmd-once", "/fsfont"]
    )

    assert fsdev.main() == 0
    assert commands == ["/fsfont"]


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only nested command")
def test_nested_legacy_cmd_is_rejected_before_input(
    fsdev: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(fsdev, "_selected_x_env", {"DISPLAY": ":2"})
    monkeypatch.setattr(fsdev, "find_wow_window", lambda: 4242)
    monkeypatch.setattr(fsdev, "user_is_playing", lambda _hwnd: False)
    monkeypatch.setattr(fsdev, "reload_ui", lambda _hwnd, command: sent.append(command))
    monkeypatch.setattr(fsdev, "send_slash", lambda _hwnd, line, **_kwargs: sent.append(line))
    monkeypatch.setattr(fsdev, "saved_vars", lambda: None)
    monkeypatch.setattr(fsdev, "wait_for_flush", lambda _before: True)
    monkeypatch.setattr(fsdev, "read_log", lambda: None)
    monkeypatch.setattr(fsdev.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        sys, "argv", ["fsdev.py", "--no-deploy", "--focus-point", "100,200", "--cmd", "/a"]
    )

    with pytest.raises(SystemExit, match="--cmd"):
        fsdev.main()

    assert sent == []


# ---------------------------------------------------------------------------
# screenshot() Linux capture with a fake Wayland frame and no portal session.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only Wayland capture")
def test_linux_screen_capture_disables_consent_keys_before_module_load(
    fsdev: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str | None] = []

    class FakeLoader:
        def create_module(self, _spec: object) -> None:
            return None

        def exec_module(self, module: types.ModuleType) -> None:
            seen.append(os.environ.get("PRIMAL_FARMER_CONSENT_KEYS"))
            module.WaylandScreenCast = object

    monkeypatch.delenv("PRIMAL_FARMER_CONSENT_KEYS", raising=False)
    monkeypatch.setattr(
        importlib.util, "spec_from_file_location",
        lambda _name, _path: importlib.machinery.ModuleSpec("fake_capture", FakeLoader()),
    )

    fsdev._linux_screen_capture()

    assert seen == [""]


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only Wayland capture")
def test_invalid_linux_crop_is_rejected_before_capture_opens(
    fsdev: types.ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        fsdev, "_linux_screen_capture",
        lambda: pytest.fail("invalid crop opened the portal"),
    )

    with pytest.raises(ValueError, match="--crop"):
        fsdev.screenshot(0, str(tmp_path / "bad.png"), crop="-1,0,2,2")


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only Wayland capture")
def test_screenshot_linux_explicit_host_crop_saves_exact_rgb_and_closes_capture(
    fsdev: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = np.array(
        [
            [[1, 2, 3, 255], [10, 20, 30, 255], [40, 50, 60, 255]],
            [[4, 5, 6, 255], [70, 80, 90, 255], [100, 110, 120, 255]],
        ],
        dtype=np.uint8,
    )
    events: list[str] = []

    class StubCapture:
        def __enter__(self) -> StubCapture:
            return self

        def __exit__(self, *_args: object) -> None:
            events.append("closed")

        def capture_full_screen_to_array(self) -> np.ndarray:
            return frame.copy()

        def capture_region(self, x: int, y: int, w: int, h: int) -> np.ndarray:
            events.append(f"region:{x},{y},{w},{h}")
            return frame[y : y + h, x : x + w].copy()

    monkeypatch.setattr(fsdev, "_linux_screen_capture", StubCapture, raising=False)
    out = tmp_path / "crop.png"

    assert fsdev.screenshot(4242, str(out), crop="1,0,2,2") == str(out)

    with Image.open(out) as image:
        assert image.mode == "RGB"
        assert image.size == (2, 2)
        assert list(image.getdata()) == [
            (30, 20, 10), (60, 50, 40),
            (90, 80, 70), (120, 110, 100),
        ]
    assert events[-1] == "closed"


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only --shot routing")
def test_main_linux_run_keeps_shot_request(
    fsdev: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shot = tmp_path / "probe.png"
    calls: list[tuple[int, str, str, str | None]] = []
    events: list[str] = []

    def fake_screenshot(hwnd: int, out: str, region: str, crop: str | None) -> str:
        events.append("screenshot")
        calls.append((hwnd, out, region, crop))
        return out

    monkeypatch.setattr(fsdev, "find_wow_window", lambda: 4242)
    monkeypatch.setattr(fsdev, "user_is_playing", lambda _hwnd: False)
    monkeypatch.setattr(fsdev, "send_slash", lambda *_args, **_kwargs: events.append("command"))
    monkeypatch.setattr(fsdev.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(fsdev, "screenshot", fake_screenshot)
    monkeypatch.setattr(
        sys,
        "argv",
        ["fsdev.py", "--no-deploy", "--run", "print(1)", "--shot", str(shot), "--crop", "1,0,2,2"],
    )

    assert fsdev.main() == 0
    assert events == ["command", "screenshot"]
    assert calls == [(4242, str(shot), "bars", "1,0,2,2")]


@pytest.mark.skipif(sys.platform == "win32", reason="Linux-only capture preflight")
def test_main_shot_only_captures_without_client_or_input(
    fsdev: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shot = tmp_path / "desktop.png"
    calls: list[tuple[str, str, str | None]] = []

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("capture-only mode touched the client or input")

    def fake_screenshot(_hwnd: int, out: str, region: str, crop: str | None) -> str:
        calls.append((out, region, crop))
        return out

    for name in (
        "deploy", "find_wow_window", "user_is_playing", "focus", "reload_ui",
        "send_slash", "tap_key", "send_text", "_linux_kbd",
    ):
        monkeypatch.setattr(fsdev, name, forbidden)
    monkeypatch.setattr(fsdev, "screenshot", fake_screenshot)
    monkeypatch.setattr(
        sys,
        "argv",
        ["fsdev.py", "--shot-only", str(shot), "--region", "full", "--crop", "1,2,3,4"],
    )

    assert fsdev.main() == 0
    assert calls == [(str(shot), "full", "1,2,3,4")]
