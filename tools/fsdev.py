#!/usr/bin/env python3
"""Drive ForeverSTUwave development against the user's own WoW client.

Windows retains the legacy two-reload SavedVariables loop; Linux discovers the
Gamescope DISPLAY from WowB.exe, sends at most one slash command per nested run,
and left-clicks the explicit --focus-point selected from a fresh capture.
From the repo root on Fedora, run
`uv run --extra fsdev python tools/fsdev.py`; --shot-only captures
without client input, while supervised --tap-once space cleared Away in a live
check and has no background timer.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wintypes
import math
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fsdev_support.uinput_abs_mouse import UinputAbsMouse
    from fsdev_support.uinput_keyboard import UinputKeyboard
    from fsdev_support.capture_wayland import WaylandScreenCast

if sys.platform == "win32":
    WOW_ROOT = Path(r"C:\Program Files (x86)\World of Warcraft")
else:
    # Native-Linux-under-Wine install (Battle.net via ~/Games), distinct from
    # the /mnt/windows dual-boot NTFS path deploy-forever-stuwave.sh
    # defaults to -- see deploy() below.
    WOW_ROOT = (
        Path.home() / "Games" / "battlenet" / "drive_c"
        / "Program Files (x86)" / "World of Warcraft"
    )
FLAVOR = "_classic_beta_"
WTF_ACCOUNTS = WOW_ROOT / FLAVOR / "WTF" / "Account"


def find_saved_vars() -> Path | None:
    """Locate the live forever-stuwave.lua, newest write wins.

    This was hardcoded to the PER-CHARACTER path
    (Account/<id>/<realm>/<char>/SavedVariables/). The addon then moved to an
    account-wide ## SavedVariables to dodge the client's broken per-character
    restore, which put the real file at Account/<id>/SavedVariables/ and left
    only a stale .bak behind at the old one.

    Nothing announced that. Every flush check silently watched a file that no
    longer existed, so a WORKING /fsreload was judged "did not take" on every
    pass and the 120-character inline fallback got typed into his chat box
    each time, and read_log ended on "no SavedVariables yet" while the client
    was writing the file perfectly well one directory up.

    So: search, do not assume. Both layouts are legal and the addon may move
    between them again.
    """
    if not WTF_ACCOUNTS.is_dir():
        return None
    found = list(WTF_ACCOUNTS.glob("*/SavedVariables/forever-stuwave.lua"))
    found += list(WTF_ACCOUNTS.glob("*/*/*/SavedVariables/forever-stuwave.lua"))
    if not found:
        return None
    return max(found, key=lambda p: p.stat().st_mtime)


SAVED_VARS = find_saved_vars()


def saved_vars() -> Path | None:
    """SAVED_VARS, re-resolved if it was missing at import.

    The file does not exist until the client has unloaded the addon once, so a
    first run on a fresh install would otherwise cache None forever.
    """
    global SAVED_VARS
    if SAVED_VARS is None:
        SAVED_VARS = find_saved_vars()
    return SAVED_VARS


DEPLOY_SCRIPT = Path(__file__).resolve().parent / "deploy-forever-stuwave.ps1"
DEPLOY_SCRIPT_SH = Path(__file__).resolve().parent / "deploy-forever-stuwave.sh"

if sys.platform == "win32":
    user32 = ctypes.WinDLL("user32", use_last_error=True)
else:
    # Never touched on Linux -- every user32.* call site below is gated by
    # its own sys.platform == "win32" branch. Kept as a plain None (rather
    # than lazily constructed) so an accidental un-gated use fails loudly
    # with AttributeError instead of silently doing nothing.
    user32 = None

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
VK_RETURN = 0x0D


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def seconds_since_input() -> float:
    """Wall-clock seconds since the last REAL keyboard or mouse event.

    GetLastInputInfo tracks hardware input (and SendInput). This script drives
    the client with PostMessage instead, and posted messages do not update it --
    which is what makes this usable as a guard at all: it never sees its own
    keystrokes and lock itself out.

    Linux: GNOME Mutter's IdleMonitor D-Bus interface (GetIdletime) reports
    milliseconds since the last real input event system-wide -- the same
    semantics as GetLastInputInfo above. Unlike PostMessage, a Linux uinput
    keystroke IS real input and resets this clock; see user_is_playing() and
    its call site in main() for why that means this can only be checked once,
    up front, per run.
    """
    if sys.platform == "win32":
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not user32.GetLastInputInfo(ctypes.byref(info)):
            return 1e9  # unreadable: assume idle rather than block the tool forever
        return max((ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0, 0.0)

    from jeepney import DBusAddress, new_method_call
    from jeepney.io.blocking import open_dbus_connection

    addr = DBusAddress(
        "/org/gnome/Mutter/IdleMonitor/Core",
        bus_name="org.gnome.Mutter.IdleMonitor",
        interface="org.gnome.Mutter.IdleMonitor",
    )
    conn = open_dbus_connection()
    try:
        reply = conn.send_and_get_reply(new_method_call(addr, "GetIdletime"))
    finally:
        conn.close()
    idle_ms: int = reply.body[0]
    return idle_ms / 1000.0


def user_is_playing(hwnd: int, grace: float = 4.0) -> bool:
    """True when Parker is at the keyboard AND WoW is the window he is in.

    Parker's idea, after I interrupted him twice: "in your python script you
    should check if i am using the keyboard or mouse".

    Both halves matter. Idle time alone is useless here, because he types to me
    in the terminal immediately before saying "go" -- every deploy would be
    refused. Foreground alone is not enough either, since WoW can sit focused
    and untouched for minutes. Together they say the thing worth knowing: the
    game has his attention right now.

    The in-game combat/movement check in reload_ui stays as the second line of
    defence. This one runs first, before anything is sent, and catches cases
    that one cannot -- reading quest text, browsing a vendor, typing in chat.
    """
    if sys.platform == "win32":
        if user32.GetForegroundWindow() != hwnd:
            return False
        return seconds_since_input() < grace

    # Linux: xdotool reports the active window's X11 id directly on stdout.
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow"], capture_output=True, text=True,
            env=_selected_x_env or os.environ.copy(),
        )
    except FileNotFoundError:
        sys.exit(
            "xdotool not found -- install it (sudo dnf install xdotool) "
            "to drive the client on Linux."
        )
    if result.returncode != 0:
        # Unreadable: "not playing" is the safe default here (unlike
        # seconds_since_input()'s "assume idle" default, which exists so a
        # read failure never blocks the tool -- here a read failure should
        # never manufacture a false "he's playing" refusal either, so False
        # is the same fail-safe direction from the opposite side). Printed
        # rather than swallowed, though: a persistently failing xdotool would
        # otherwise make this guard silently never refuse anything.
        print(f"xdotool getactivewindow failed ({result.returncode}): {result.stderr.strip()}")
        return False
    try:
        active_hwnd = int(result.stdout.strip())
    except ValueError:
        return False
    if active_hwnd != hwnd:
        return False
    return seconds_since_input() < grace


_selected_x_env: dict[str, str] | None = None
_focus_point: tuple[int, int] | None = None
_host_focus_done = False


def _wow_process_displays(proc_root: Path = Path("/proc")) -> list[str]:
    """Find local X11 displays advertised by running WowB.exe processes."""
    displays: list[str] = []
    try:
        processes = sorted(
            (path for path in proc_root.iterdir() if path.name.isdecimal()),
            key=lambda path: int(path.name),
        )
    except OSError as exc:
        print(f"Cannot inspect {proc_root}: {exc}", file=sys.stderr)
        return displays

    for process in processes:
        try:
            if (process / "comm").read_text(encoding="utf-8").strip() != "WowB.exe":
                continue
        except (OSError, UnicodeError):
            continue
        try:
            environment = (process / "environ").read_bytes()
        except OSError as exc:
            print(f"Cannot read WowB.exe {process / 'environ'}: {exc}", file=sys.stderr)
            continue
        for entry in environment.split(b"\0"):
            if not entry.startswith(b"DISPLAY="):
                continue
            try:
                display = entry.removeprefix(b"DISPLAY=").decode("ascii")
            except UnicodeError:
                continue
            if re.fullmatch(r":[0-9]+(?:\.[0-9]+)?", display) and display not in displays:
                displays.append(display)
    return displays


def find_wow_window() -> int:
    """HWND of the running client, matched on window title."""
    if sys.platform == "win32":
        matches: list[int] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if buf.value.strip().lower().startswith("world of warcraft"):
                matches.append(hwnd)
            return True

        user32.EnumWindows(callback, 0)
        if not matches:
            sys.exit("WoW window not found -- is the client running?")
        return matches[0]

    # xdotool by window name, NOT core.wow_window: importing anything from the
    # core package runs core/__init__.py, which eagerly imports pyautogui ->
    # python-xlib, and this box's core venv ships an xlib too old to auth to
    # XWayland (it dies at import). fsdev only needs the window id for focus,
    # so a subprocess query sidesteps the whole chain.
    global _selected_x_env
    _selected_x_env = None
    host_env = os.environ.copy()
    candidates = [host_env.get("DISPLAY")]
    candidates.extend(display for display in _wow_process_displays() if display not in candidates)
    found: list[tuple[int, dict[str, str]]] = []
    for display in candidates:
        env = host_env.copy()
        if display is not None:
            env["DISPLAY"] = display
        try:
            result = subprocess.run(
                ["xdotool", "search", "--name", "World of Warcraft"],
                capture_output=True, text=True, env=env,
            )
        except FileNotFoundError:
            sys.exit(
                "xdotool not found -- install it (sudo dnf install xdotool) "
                "to drive the client on Linux."
            )
        if result.returncode != 0:
            print(
                f"xdotool search failed on {display} ({result.returncode}): "
                f"{result.stderr.strip()}", file=sys.stderr,
            )
            continue
        try:
            found.extend((int(window_id), env) for window_id in result.stdout.split())
        except ValueError as exc:
            raise SystemExit(
                f"xdotool search returned an invalid window id on {display}: {exc}"
            ) from exc
    if not found:
        sys.exit("WoW window not found -- is the client running?")
    if len(found) != 1:
        sys.exit("Ambiguous WoW windows found across X11 displays")
    hwnd, _selected_x_env = found[0]
    return hwnd


def focus(hwnd: int) -> None:
    if sys.platform == "win32":
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.5)
        return

    # uinput is a GLOBAL device with no notion of a target window, so the
    # window must actually be focused before any keystroke is sent.
    global _host_focus_done
    if (
        _focus_point is not None and not _host_focus_done
        and _selected_x_env is not None
        and _selected_x_env.get("DISPLAY") != os.environ.get("DISPLAY")
    ):
        with _linux_abs_mouse() as mouse:
            mouse.move_abs(*_focus_point)
            mouse.click("left")
        _host_focus_done = True
    try:
        result = subprocess.run(
            ["xdotool", "windowactivate", str(hwnd)], capture_output=True, text=True,
            env=_selected_x_env or os.environ.copy(),
        )
    except FileNotFoundError:
        sys.exit(
            "xdotool not found -- install it (sudo dnf install xdotool) "
            "to drive the client on Linux."
        )
    if result.returncode != 0:
        sys.exit(
            f"xdotool windowactivate {hwnd} failed ({result.returncode}): "
            f"{result.stderr.strip()}"
        )
    time.sleep(0.5)


def _parse_focus_point(value: str) -> tuple[int, int]:
    """Parse an explicit desktop pixel coordinate."""
    if not re.fullmatch(r"[0-9]+,[0-9]+", value):
        raise argparse.ArgumentTypeError("--focus-point must be X,Y with nonnegative integers")
    x, y = (int(part) for part in value.split(","))
    return x, y


def _linux_abs_mouse() -> UinputAbsMouse:
    """Create an absolute pointer sized for the host X11 desktop."""
    import importlib.util

    host_env = os.environ.copy()
    if not host_env.get("DISPLAY"):
        sys.exit("Host DISPLAY is missing; cannot place --focus-point")
    try:
        result = subprocess.run(
            ["xdotool", "getdisplaygeometry"], capture_output=True, text=True, env=host_env,
        )
    except FileNotFoundError as exc:
        raise SystemExit(
            "xdotool not found -- cannot measure the host desktop for --focus-point"
        ) from exc
    if result.returncode != 0:
        sys.exit(f"Cannot measure host desktop: {result.stderr.strip()}")
    try:
        width, height = (int(part) for part in result.stdout.split())
    except ValueError as exc:
        raise SystemExit(f"Invalid host desktop geometry: {result.stdout.strip()!r}") from exc
    if width <= 0 or height <= 0:
        sys.exit(f"Invalid host desktop geometry: {width}x{height}")
    if _focus_point is None or not (0 <= _focus_point[0] < width and 0 <= _focus_point[1] < height):
        sys.exit(f"--focus-point must be within host desktop {width}x{height}")

    module_path = (
        Path(__file__).resolve().parent / "fsdev_support" / "uinput_abs_mouse.py"
    )
    spec = importlib.util.spec_from_file_location("fsdev_uinput_abs_mouse", module_path)
    if spec is None or spec.loader is None:
        sys.exit(f"Cannot load absolute mouse module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.UinputAbsMouse(width, height)


def _lparam(scan: int, keyup: bool) -> int:
    """lParam for WM_KEYDOWN/WM_KEYUP.

    Copied from core/backends/win32_backend.py, which is the version proven
    against this client. A bare WM_CHAR does NOT reach WoW -- the first version
    of this script used it and the reload silently never happened. WoW wants a
    real key message with the scan code packed into bits 16-23.
    """
    value = 1                              # repeat count
    value |= (scan & 0xFF) << 16           # scan code
    if keyup:
        value |= (1 << 30) | (1 << 31)     # previous state + transition
    return value


_linux_kbd_instance: UinputKeyboard | None = None


def _linux_kbd() -> UinputKeyboard:
    """Process-wide lazily-created Linux uinput keyboard.

    uinput is a GLOBAL device, not window-targeted -- every caller MUST
    focus() the WoW window first. One instance is reused for the whole run;
    fsdev.py is function-based with no classes, so a cached module-level
    instance stands in for the composition LinuxKeyboardBackend uses in
    core/backends/linux_backend.py.
    """
    global _linux_kbd_instance
    if _linux_kbd_instance is None:
        # Load the standalone uinput_keyboard module DIRECTLY by file, not as
        # core.backends.uinput_keyboard: the package import runs core/__init__.py,
        # which eagerly pulls pyautogui -> python-xlib and dies at import on this
        # box's XWayland (old venv xlib). uinput_keyboard.py depends only on
        # evdev, so loading it in isolation avoids that chain entirely.
        import importlib.util

        kbd_path = (
            Path(__file__).resolve().parent / "fsdev_support" / "uinput_keyboard.py"
        )
        spec = importlib.util.spec_from_file_location("fsdev_uinput_keyboard", kbd_path)
        if spec is None or spec.loader is None:
            sys.exit(f"cannot load uinput keyboard module from {kbd_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _linux_kbd_instance = module.UinputKeyboard()
    return _linux_kbd_instance


def tap_key(hwnd: int, vk: int) -> None:
    """Tap a single key in the WoW window. Only ever called with VK_RETURN
    in this script (open chat / submit)."""
    if sys.platform == "win32":
        scan = user32.MapVirtualKeyW(vk, 0)
        user32.PostMessageW(hwnd, WM_KEYDOWN, vk, _lparam(scan, False))
        time.sleep(0.05)
        user32.PostMessageW(hwnd, WM_KEYUP, vk, _lparam(scan, True))
        time.sleep(0.05)
        return

    if vk != VK_RETURN:
        raise ValueError(f"tap_key: no Linux mapping for vk={vk:#x} (only VK_RETURN is used)")
    # Gamescope/Wine can miss a press and release delivered in the same
    # uinput sync interval. Keep Return down for a frame so opening/submitting
    # chat cannot leave successive slash commands concatenated in the box.
    kbd = _linux_kbd()
    kbd.key_down("enter")
    try:
        time.sleep(0.05)
    finally:
        kbd.key_up("enter")
    time.sleep(0.05)


# Typing cadence. The old flat 0.03s was ~400wpm, which reads as a script
# driving the box. A uniform random delay replaced it and still did not look
# right -- Parker, watching it on his own screen: "it still doesn't look like i
# am typing."
#
# Uniform jitter is the problem. Real inter-key gaps are not evenly spread
# between a floor and a ceiling; they cluster tightly around a mode with a long
# tail to the right, and the variation is STRUCTURED rather than random:
#
#   * Alternating hands is faster than same-hand, because the next finger is
#     already travelling while the current key is struck. Same-hand digraphs
#     are measurably slower. This is the single biggest source of the rhythm
#     people recognise as human.
#   * A repeated character is faster than either.
#   * Hesitation happens at WORD BOUNDARIES, not uniformly, and it is occasional
#     and long rather than constant and small.
#   * A shifted character costs the shift.
#
# So the base draw is lognormal (mode near the median, tail to the right) and
# the rest is modelled per digraph. Same average speed, completely different
# texture.
TYPE_MEDIAN = 0.085         # seconds; median gap, about 70wpm
TYPE_SIGMA = 0.42           # lognormal spread; the right tail is the realism
TYPE_MIN = 0.028
TYPE_MAX = 0.50
TYPE_SAME_HAND = 0.022      # penalty when consecutive keys share a hand
TYPE_ALT_HAND = -0.012      # bonus when they alternate
TYPE_REPEAT = 0.045         # a doubled letter is quicker than either
TYPE_SHIFT = 0.035          # cost of reaching for shift
TYPE_PAUSE_AFTER = " ,.:;/"
TYPE_PAUSE_EXTRA = 0.06
TYPE_HESITATE_CHANCE = 0.06  # per word boundary
TYPE_HESITATE = (0.18, 0.55)

# Rough hand split on a QWERTY board. Only used to tell "same hand" from
# "alternating", so the exact boundary matters far less than having one.
_LEFT_HAND = set("qwertasdfgzxcvb12345`")
_RIGHT_HAND = set(r"yuiophjklnm67890-=[]\;',./")
_SHIFTED = set('~!@#$%^&*()_+{}|:"<>?')


def _hand(ch: str) -> str | None:
    lowered = ch.lower()
    if lowered in _LEFT_HAND:
        return "L"
    if lowered in _RIGHT_HAND:
        return "R"
    return None


def _key_delay(ch: str, prev: str | None) -> float:
    """Inter-key gap before typing `ch`, given the character before it."""
    if prev is not None and ch == prev:
        delay = random.uniform(TYPE_REPEAT * 0.8, TYPE_REPEAT * 1.3)
    else:
        delay = random.lognormvariate(math.log(TYPE_MEDIAN), TYPE_SIGMA)
        hand, prev_hand = _hand(ch), _hand(prev) if prev else None
        if hand and prev_hand:
            delay += TYPE_SAME_HAND if hand == prev_hand else TYPE_ALT_HAND

    if ch.isupper() or ch in _SHIFTED:
        delay += TYPE_SHIFT
    if ch in TYPE_PAUSE_AFTER:
        delay += TYPE_PAUSE_EXTRA
    # Hesitation belongs at the start of a word, which is where a person is
    # deciding what comes next rather than executing a sequence they know.
    if prev == " " and random.random() < TYPE_HESITATE_CHANCE:
        delay += random.uniform(*TYPE_HESITATE)

    return max(TYPE_MIN, min(TYPE_MAX, delay))


# Linux character -> uinput key decomposition. UinputKeyboard._KEY_NAME_MAP has
# no entries for shifted symbols themselves (only the unshifted base key), so
# typing punctuation on Linux means holding shift around the base key's tap.
# An unmapped character is a hard error -- never silently dropped, matching
# uinput_keyboard.py's own stated philosophy ("a silently-dropped keystroke is
# exactly the bug class this device fixes").
#
# Covers every printable-ASCII symbol (US QWERTY), not just the handful the
# reload strings happened to use -- extended 2026-09-23 after a WoW colour
# code ("|cff22e0ff...|r", sent while probing a live client) hard-exited
# --run/--cmd on the unmapped "|". Every value here is a base key name that
# must exist in uinput_keyboard._KEY_NAME_MAP; see test_char_to_key_emits_
# only_known_uinput_keys for the cross-check.
_LINUX_SHIFT_SYMBOLS: dict[str, str] = {
    "!": "1",   # shift+1
    "@": "2",   # shift+2
    "#": "3",   # shift+3
    "$": "4",   # shift+4
    "%": "5",   # shift+5
    "^": "6",   # shift+6
    "&": "7",   # shift+7
    "*": "8",   # shift+8
    "(": "9",   # shift+9
    ")": "0",   # shift+0
    "_": "-",   # shift+minus
    "+": "=",   # shift+equal
    "{": "[",   # shift+left bracket
    "}": "]",   # shift+right bracket
    "|": "\\",  # shift+backslash -- the live trigger
    ":": ";",   # shift+semicolon
    '"': "'",   # shift+apostrophe
    "<": ",",   # shift+comma
    ">": ".",   # shift+dot
    "?": "/",   # shift+slash
    "~": "`",   # shift+backtick
}
_LINUX_PLAIN_SYMBOLS: dict[str, str] = {
    " ": "space",
    "-": "-",
    "=": "=",
    "[": "[",
    "]": "]",
    "`": "`",
    "\\": "\\",
    ";": ";",
    "'": "'",
    ",": ",",
    ".": ".",
    "/": "/",
}


def char_to_key(ch: str) -> tuple[str, bool]:
    """Map one character to a (uinput key_name, needs_shift) pair.

    Pure and platform-independent so it can be unit tested without a live
    uinput device. Covers the full printable-ASCII range (0x20-0x7E); raises
    ValueError for anything outside it (control characters, non-ASCII) -- a
    silently-dropped keystroke is exactly the bug class
    core.backends.uinput_keyboard's own design guards against, but genuinely
    untypable input still fails loud rather than being coerced into a guess.
    """
    if len(ch) != 1:
        raise ValueError(f"char_to_key expects a single character, got {ch!r}")
    if not (0x20 <= ord(ch) <= 0x7E):
        raise ValueError(f"No Linux key mapping for character {ch!r} (not printable ASCII)")
    if ch.isalpha():
        return ch.lower(), ch.isupper()
    if ch.isdigit():
        return ch, False
    if ch in _LINUX_SHIFT_SYMBOLS:
        return _LINUX_SHIFT_SYMBOLS[ch], True
    if ch in _LINUX_PLAIN_SYMBOLS:
        return _LINUX_PLAIN_SYMBOLS[ch], False
    # Unreachable: 0x20-0x7E is fully covered by the branches above.
    raise ValueError(f"No Linux key mapping for character {ch!r}")


# WoW's chat edit box silently TRUNCATES any input beyond 255 characters --
# no error, just a cut-off string. A truncated --run/--cmd line reaches the
# client broken (a confusing Lua syntax error, or a silent no-op), so this is
# checked in send_text() BEFORE anything is typed rather than discovered live
# in-game. See GUARDED_RELOAD/INLINE_RELOAD below, which is the same 255
# figure this was sized against.
MAX_CHAT_INPUT = 255


def send_text(hwnd: int, text: str, fast: bool = False) -> None:
    """Type into the open chat edit box.

    Once the edit box holds keyboard focus WM_CHAR is the right message for
    text -- it is only the Enter that has to be a real key event, because that
    is handled by the game's key bindings rather than the edit box.

    Paced like a person by default. `fast` restores the old flat cadence for
    when nobody is watching the screen.

    Linux has no WM_CHAR text-injection equivalent, so every character is a
    real key tap (with a shift hold around it for anything the base key alone
    does not produce); see char_to_key() for the decomposition. The pacing
    loop shape is identical to the Windows one below -- only the OS primitive
    that emits one character changes.
    """
    if len(text) > MAX_CHAT_INPUT:
        sys.exit(
            f"send_text: {len(text)} chars exceeds WoW's {MAX_CHAT_INPUT}-char "
            f"chat box limit -- would be typed truncated/broken: {text!r}. "
            "Shorten it, or move the logic into the addon and trigger it via "
            "a short slash command instead."
        )
    if sys.platform == "win32":
        prev = None
        for ch in text:
            user32.PostMessageW(hwnd, WM_CHAR, ord(ch), 0)
            if fast:
                time.sleep(0.03)
                continue
            # The gap goes AFTER the character, but it is computed from the pair --
            # the cost of a keystroke belongs to the transition into it.
            time.sleep(_key_delay(ch, prev))
            prev = ch
        return

    # Resolve every character BEFORE typing any of it. char_to_key() raises on
    # the first unmapped character, and by then any earlier characters would
    # already be sitting in the live, focused chat box -- a pre-flight pass
    # over the whole string is what keeps a bad character from leaving a
    # partial command typed into the client instead of failing cleanly.
    for ch in text:
        try:
            char_to_key(ch)
        except ValueError as exc:
            sys.exit(f"send_text: cannot type {text!r} on Linux -- {exc}")

    kbd = _linux_kbd()
    prev = None
    for ch in text:
        key_name, needs_shift = char_to_key(ch)
        if needs_shift:
            kbd.key_down("shift")
        kbd.tap(key_name)
        if needs_shift:
            kbd.key_up("shift")
        if fast:
            time.sleep(0.03)
        else:
            time.sleep(_key_delay(ch, prev))
        prev = ch


def reload_ui(hwnd: int, command: str = "/fsreload") -> None:
    """Open chat and reload -- but ONLY if the player is out of combat.

    This sends a self-guarding statement rather than a bare /reload:

        /run if not InCombatLockdown()
                and (GetUnitSpeed and GetUnitSpeed("player") or 0) == 0
             then ReloadUI() end

    On 2026-09-20 a reload fired while Parker was mid-fight. Opening the chat
    box captures the keyboard, so he could not use an ability, and he burned
    his only healing potion to survive it. It happened AGAIN an hour later
    while he was running -- combat alone was not a wide enough guard, because
    losing the keyboard mid-run is its own problem.

    So the test is combat OR movement. The client decides, not this script: if
    either is true the statement is a no-op, wait_for_flush times out, and the
    caller reports that nothing happened instead of yanking the UI away.

    This is a backstop, not a licence. Permission to take the client is spent
    by the action it was given for -- ask again for the next one.
    """
    focus(hwnd)
    tap_key(hwnd, VK_RETURN)   # open chat
    time.sleep(0.5)
    send_text(hwnd, command)
    time.sleep(0.3)
    tap_key(hwnd, VK_RETURN)   # submit


# The addon's own guarded reload (ErrorLog.lua). Nine characters instead of a
# ~100-character /run, which matters because the chat box caps input at 255.
GUARDED_RELOAD = "/fsreload"

# Identical logic inline, for when the addon is not loaded. That case is not
# hypothetical: if a bad deploy stops the addon loading, /fsreload would not
# exist, and without this there would be no way to reload in order to FIX it.
INLINE_RELOAD = ('/run if not InCombatLockdown() and '
                 '(GetUnitSpeed and GetUnitSpeed("player") or 0)==0 '
                 'then ReloadUI() end')


def send_slash(hwnd: int, line: str, fast: bool = False) -> None:
    """Type one slash command into the client's chat box and send it.

    Enter opens the box, Enter sends. Shared by --run and --cmd so there is one
    place that knows the sequence.
    """
    focus(hwnd)
    tap_key(hwnd, VK_RETURN)
    time.sleep(0.4)
    send_text(hwnd, line, fast=fast)
    time.sleep(0.3)
    tap_key(hwnd, VK_RETURN)


def _linux_screen_capture() -> WaylandScreenCast:
    """Load the Wayland capture backend without importing the core package."""
    import importlib.util

    module_path = (
        Path(__file__).resolve().parent / "fsdev_support" / "capture_wayland.py"
    )
    spec = importlib.util.spec_from_file_location("fsdev_capture_wayland", module_path)
    if spec is None or spec.loader is None:
        sys.exit(f"Cannot load Wayland capture module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    prior_consent_keys = os.environ.get("PRIMAL_FARMER_CONSENT_KEYS")
    os.environ["PRIMAL_FARMER_CONSENT_KEYS"] = ""
    try:
        spec.loader.exec_module(module)
    finally:
        if prior_consent_keys is None:
            os.environ.pop("PRIMAL_FARMER_CONSENT_KEYS", None)
        else:
            os.environ["PRIMAL_FARMER_CONSENT_KEYS"] = prior_consent_keys
    return module.WaylandScreenCast()


def screenshot(hwnd: int, out: str, region: str = "full", crop: str | None = None) -> str:
    """Save a screenshot as RGB PNG.

    Windows captures the WoW client and interprets crop in client pixels; Linux captures
    the host Wayland monitor and interprets crop in host screen pixels. An explicit
    crop bypasses resizing on both platforms.
    """
    if sys.platform == "win32":
        import mss
        from PIL import Image

        rect = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(rect))
        point = wintypes.POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(point))

        left, top = point.x, point.y
        width, height = rect.right, rect.bottom

        if crop:
            cx, cy, cw, ch = (int(v) for v in crop.split(","))
            left, top, width, height = left + cx, top + cy, cw, ch
        elif region == "bars":
            top = top + int(height * 0.62)
            height = int(height * 0.38)

        with mss.mss() as sct:
            raw = sct.grab({"left": left, "top": top, "width": width, "height": height})
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

        # Keep it under ~1600px wide; full-res 2560 shots are needlessly large.
        # An explicit crop is always returned at native resolution.
        if crop is None and img.width > 1600:
            img = img.resize((1600, int(img.height * 1600 / img.width)), Image.LANCZOS)
        img.save(out)
        return out

    from PIL import Image

    crop_rect: tuple[int, int, int, int] | None = None
    if crop is not None:
        if not re.fullmatch(r"[0-9]+,[0-9]+,[1-9][0-9]*,[1-9][0-9]*", crop):
            raise ValueError("--crop must be X,Y,W,H with positive width and height")
        crop_rect = tuple(int(part) for part in crop.split(","))

    with _linux_screen_capture() as capture:
        if crop_rect is not None:
            x, y, width, height = crop_rect
            frame = capture.capture_region(x, y, width, height)
            if frame.shape[:2] != (height, width):
                raise ValueError("--crop extends outside the captured host monitor")
        else:
            frame = capture.capture_full_screen_to_array()
            if region == "bars":
                top = int(frame.shape[0] * 0.62)
                frame = frame[top:, :, :]

    height, width = frame.shape[:2]
    image = Image.frombytes("RGB", (width, height), frame.tobytes(), "raw", "BGRX")
    if crop is None and image.width > 1600:
        image = image.resize((1600, int(image.height * 1600 / image.width)), Image.LANCZOS)
    image.save(out, format="PNG")
    return out


def deploy() -> None:
    if sys.platform == "win32":
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(DEPLOY_SCRIPT)],
            capture_output=True, text=True,
        )
        tail = [ln for ln in result.stdout.splitlines() if ln.strip()][-3:]
        print("\n".join(tail))
        if result.returncode != 0:
            print(result.stderr)
            sys.exit(f"deploy failed ({result.returncode})")
        return

    # deploy-forever-stuwave.sh's own baked-in WOW_ROOT default targets a
    # DIFFERENT workflow (the /mnt/windows NTFS-mounted native-Windows beta
    # client, for a dual-boot Wine-freeze workaround). This is the
    # native-Linux-under-Wine install, so WOW_ROOT/WOW_FLAVOR are always
    # passed explicitly -- the script's own default must never apply here.
    env = dict(os.environ)
    env["WOW_ROOT"] = str(WOW_ROOT)
    env["WOW_FLAVOR"] = FLAVOR
    result = subprocess.run(
        ["bash", str(DEPLOY_SCRIPT_SH)],
        capture_output=True, text=True, env=env,
    )
    tail = [ln for ln in result.stdout.splitlines() if ln.strip()][-3:]
    print("\n".join(tail))
    if result.returncode != 0:
        print(result.stderr)
        sys.exit(f"deploy failed ({result.returncode})")


def wait_for_flush(before_mtime: float, timeout: float = 45.0) -> bool:
    """SavedVariables are written during the reload, so watch for the mtime to
    move rather than sleeping a fixed guess."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        path = saved_vars()
        if path and path.exists() and path.stat().st_mtime > before_mtime:
            time.sleep(1.0)  # let the write finish
            return True
        time.sleep(0.5)
    return False


def read_log() -> None:
    path = saved_vars()
    if path is None:
        print("NO SavedVariables file anywhere under")
        print(f"  {WTF_ACCOUNTS}")
        print("The addon has never unloaded, or it is not enabled in the client.")
        return

    print(f"reading {path}")
    text = path.read_text(encoding="utf-8", errors="replace")

    # The error log only reaches disk if the .toc DECLARES it. It is easy to
    # drop from that line (it has been), and the symptom is indistinguishable
    # from a clean run -- "no errors" and "errors not being saved" both print
    # nothing. Say which one this is.
    if "ForeverSTUwaveErrorLog" not in text:
        print("\n  WARNING: ForeverSTUwaveErrorLog is absent from the file.")
        print("  Check '## SavedVariables' in forever-stuwave.toc -- an")
        print("  undeclared global is never written, so this reads as 'no")
        print("  errors' forever.")

    probe = re.search(r"ForeverSTUwaveProbe = \{(.*?)\n\}", text, re.S)
    if probe:
        print("\n=== PROBE ===")
        for line in probe.group(1).splitlines():
            line = line.strip().rstrip(",")
            if line:
                print("  " + line)

    # ForeverSTUwaveDB carries whatever the in-addon probes last wrote
    # (/fsfont, /fschat levels). Those probes live in the addon rather than in
    # a long --run line because the chat box truncates at 255 characters, and
    # they write here rather than only printing because a chat line is legible
    # to whoever is sitting at the client and to nobody else.
    db = re.search(r"ForeverSTUwaveDB = \{(.*?)\n\}", text, re.S)
    if db and db.group(1).strip():
        print("\n=== ForeverSTUwaveDB ===")
        for line in db.group(1).splitlines():
            if line.strip():
                print("  " + line.rstrip())

    entries = re.findall(
        r'\["message"\] = "(.*?)",\s*\n\["count"\] = (\d+).*?\["stack"\] = "(.*?)",\s*\n',
        text, re.S,
    )
    if not entries:
        print("\n=== ERRORS ===\n  none captured")
        return

    print(f"\n=== ERRORS ({len(entries)} distinct) ===")
    for i, (msg, count, stack) in enumerate(entries, 1):
        print(f"\n[{i}] x{count}  {msg}")
        for frame in stack.split("\\n"):
            frame = frame.strip()
            if frame:
                print(f"      {frame}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-deploy", action="store_true")
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="take the client even if it looks like he is playing; "
                             "only with explicit go-ahead in his latest message")
    parser.add_argument("--focus-point", type=_parse_focus_point, metavar="X,Y",
                        help="host point inside WoW; moves pointer and LEFT CLICKS once")
    parser.add_argument("--shot", metavar="PATH",
                        help="save a PNG afterwards (host monitor on Linux)")
    parser.add_argument("--shot-only", metavar="PATH",
                        help="capture a PNG and exit without deploy or client input")
    parser.add_argument("--region", default="bars", choices=["full", "bars"])
    parser.add_argument("--crop", metavar="X,Y,W,H",
                        help="native-resolution crop in client pixels on Windows, "
                             "host pixels on Linux")
    parser.add_argument("--fast-type", action="store_true",
                        help="type at the old machine cadence instead of human speed")
    parser.add_argument("--run", metavar="LUA",
                        help="send a /run command instead of reloading (for live probing)")
    parser.add_argument("--cmd-once", metavar="SLASH",
                        help="send one slash command without deploy, reload, or log read")
    parser.add_argument("--tap-once", metavar="KEY",
                        help="Linux: focus WoW and press Space once, then exit")
    parser.add_argument("--cmd", metavar="SLASH", action="append",
                        help="slash command to send BEFORE reloading, repeatable "
                             "(e.g. --cmd '/fsfont' --cmd '/fschat levels'). The "
                             "reload is what flushes whatever it wrote to disk.")
    args = parser.parse_args()
    global _focus_point, _host_focus_done
    _focus_point = args.focus_point
    _host_focus_done = False

    if args.tap_once is not None and args.tap_once != "space":
        sys.exit("--tap-once supports only space")
    if args.tap_once is not None and sys.platform == "win32":
        sys.exit("--tap-once space is available only on Linux")
    if args.tap_once is not None and _focus_point is None:
        sys.exit("--tap-once space requires --focus-point X,Y")
    if args.tap_once is not None and (args.shot_only is not None or args.read_only):
        sys.exit("--tap-once cannot be combined with --shot-only or --read-only")

    if args.shot_only:
        hwnd = find_wow_window() if sys.platform == "win32" else 0
        print(f"screenshot: {screenshot(hwnd, args.shot_only, args.region, args.crop)}")
        return 0

    if args.read_only:
        read_log()
        return 0

    if not args.no_deploy and args.cmd_once is None and args.tap_once is None:
        deploy()

    hwnd = find_wow_window()
    print(f"WoW window: {hwnd}")

    # Checked BEFORE focus(): this script raises the window itself, so asking
    # afterwards would always answer "foreground".
    #
    # The guard decision (user_is_playing, which itself reads idle time) is
    # made ONCE here, before anything is sent. seconds_since_input() is read
    # a second time two lines below, but only on the immediate-refusal path,
    # to print the idle figure in the message -- that is still safe because
    # the run returns 2 right after and never goes on to send a keystroke.
    # The rule that must never be broken is: no re-check AFTER a keystroke
    # has been sent this run. On Windows that would be harmless anyway
    # (PostMessage input is invisible to GetLastInputInfo); on Linux it is a
    # correctness requirement, because a uinput tap is real HID input and
    # DOES reset the Mutter idle clock this guard reads -- a later re-check
    # would see the tool's own typing as "Parker is active" and the tool
    # would never be able to lock itself out.
    if not args.force and user_is_playing(hwnd):
        idle = seconds_since_input()
        print("")
        print(f"REFUSED: WoW is focused and there was input {idle:.1f}s ago --")
        print("         Parker appears to be playing. Ask before taking the")
        print("         client, or pass --force if he has just said go.")
        return 2

    nested_display = (
        sys.platform != "win32" and _selected_x_env is not None
        and _selected_x_env.get("DISPLAY") != os.environ.get("DISPLAY")
    )
    if nested_display and args.cmd:
        sys.exit("--cmd is unavailable with nested Gamescope; use --cmd-once")
    if nested_display and _focus_point is None:
        sys.exit("Nested WoW display requires --focus-point X,Y before keyboard input")

    if args.tap_once is not None:
        focus(hwnd)
        keyboard = _linux_kbd()
        keyboard.key_down("space")
        try:
            time.sleep(0.05)
        finally:
            keyboard.key_up("space")
        return 0

    if args.cmd_once is not None:
        if not args.cmd_once.startswith("/") or len(args.cmd_once) == 1:
            sys.exit("--cmd-once requires one slash command")
        send_slash(hwnd, args.cmd_once, fast=args.fast_type)
        return 0

    # Live probe: run one statement and screenshot, no reload. Bisecting which
    # frame owns a stray visual is far faster this way than adding a flag to
    # the addon and doing a full deploy-reload cycle per guess.
    if args.run:
        send_slash(hwnd, "/run " + args.run, fast=args.fast_type)
        time.sleep(1.0)
        if args.shot:
            print("screenshot:", screenshot(hwnd, args.shot, args.region, args.crop))
        return 0

    if nested_display:
        sv = saved_vars()
        before = sv.stat().st_mtime if sv and sv.exists() else 0.0
        reload_ui(hwnd, GUARDED_RELOAD)
        if not wait_for_flush(before):
            print("SavedVariables did not advance after one reload; refusing retry or stale log.",
                  file=sys.stderr)
            return 1
        read_log()
        if args.shot:
            print("screenshot:", screenshot(hwnd, args.shot, args.region, args.crop))
        return 0


    # TWO reloads, and the reason is easy to get wrong: SavedVariables are
    # written when the UI UNLOADS, so the first reload flushes the session that
    # was running with the OLD code, and only then does the freshly deployed
    # code load. The second reload is what captures the new code's results.
    # (--no-deploy still reloads twice; harmless, and keeps one mental model.)
    for pass_number in (1, 2):
        sv = saved_vars()
        before = sv.stat().st_mtime if sv and sv.exists() else 0.0
        label = "loading new code" if pass_number == 1 else "capturing results"
        print(f"  reload {pass_number}/2 ({label})")
        reload_ui(hwnd, GUARDED_RELOAD)

        # Fall back to the inline form before believing the refusal: a missing
        # /fsreload and a genuine "he is busy" look identical from out here.
        flushed = wait_for_flush(before)
        if not flushed:
            print("  /fsreload did not take -- retrying inline")
            reload_ui(hwnd, INLINE_RELOAD)
            flushed = wait_for_flush(before)

        if not flushed:
            print("SavedVariables did not change; stopping without reading stale log.",
                  file=sys.stderr)
            return 1
        # The client needs a moment to finish re-running addon load before the
        # next Enter reaches a live chat box.
        time.sleep(3.0)

        # BETWEEN the two reloads, and the position is the whole point. A probe
        # sent before reload 1 runs against the code that is still loaded, i.e.
        # the version WITHOUT the probe in it -- a brand-new slash command is
        # simply an unknown command, and it fails by writing nothing, which
        # looks exactly like a probe that ran and found nothing. Here, reload 1
        # has loaded the new code and reload 2 is what flushes what the probe
        # writes.
        #
        # In-addon probes rather than --run lines because the chat box
        # truncates a typed line at 255 characters.
        if pass_number == 1:
            for command in args.cmd or []:
                print(f"  probe {command}")
                send_slash(hwnd, command, fast=args.fast_type)
                time.sleep(1.0)

    print("SavedVariables flushed.")

    read_log()

    if args.shot:
        path = screenshot(hwnd, args.shot, args.region, args.crop)
        print("")
        print(f"screenshot: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
