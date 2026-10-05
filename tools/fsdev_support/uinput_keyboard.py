"""Linux keyboard via the kernel uinput subsystem.

Provides a virtual keyboard that Wine reads as genuine raw HID key
events (``EV_KEY`` press/release + ``SYN_REPORT``).  This is the Linux
equivalent of the Windows ``SendInput KEYEVENTF`` path.

Why this exists: WoW under Wine reads keyboard state from real HID
devices (DirectInput / raw input), NOT from X synthetic events.  Live
in-game testing proved that ``xdotool`` -- both with ``--window``
(XSendEvent) and without (global XTEST) -- fails to move the character:
``W`` held for 21 s produced no movement and no xdotool error.  Emitting
kernel-level ``EV_KEY`` events through a virtual ``uinput`` device
bypasses that entirely, exactly as the ``uinput`` mouse fixed mouselook.

Importing this module on a non-Linux platform raises ``ImportError`` at
``evdev`` import time, mirroring ``uinput_mouse``'s platform guard.
"""

from __future__ import annotations

import logging
from types import TracebackType

from evdev import UInput, ecodes

logger = logging.getLogger(__name__)

_DEVICE_NAME = "wow-bot-virtual-keyboard"

# Key-name -> evdev ecode map.  Covers EVERY key the facade can emit:
# the union of ``InputSimulator._KEY_MAP`` and the linux backend's
# ``_XDOTOOL_KEYSYM_MAP``.  Letters and digits are added programmatically
# below.  Modifiers use the LEFT variants (the convention WoW keybinds
# expect).  An unmapped key name is a hard error (see :meth:`resolve`) --
# a silently-dropped keystroke is exactly the bug class this device fixes.
_KEY_NAME_MAP: dict[str, int] = {
    # Letters a-z -> KEY_A .. KEY_Z
    **{chr(c): getattr(ecodes, f"KEY_{chr(c).upper()}") for c in range(ord("a"), ord("z") + 1)},
    # Digits: note KEY_0 is the '0' key, not the head of the KEY_1.. row.
    "1": ecodes.KEY_1,
    "2": ecodes.KEY_2,
    "3": ecodes.KEY_3,
    "4": ecodes.KEY_4,
    "5": ecodes.KEY_5,
    "6": ecodes.KEY_6,
    "7": ecodes.KEY_7,
    "8": ecodes.KEY_8,
    "9": ecodes.KEY_9,
    "0": ecodes.KEY_0,
    # Whitespace / control keys
    "space": ecodes.KEY_SPACE,
    "enter": ecodes.KEY_ENTER,
    "return": ecodes.KEY_ENTER,
    "escape": ecodes.KEY_ESC,
    "esc": ecodes.KEY_ESC,
    "tab": ecodes.KEY_TAB,
    "backspace": ecodes.KEY_BACKSPACE,
    # Modifiers -- LEFT variants by convention.
    "shift": ecodes.KEY_LEFTSHIFT,
    "ctrl": ecodes.KEY_LEFTCTRL,
    "alt": ecodes.KEY_LEFTALT,
    "super": ecodes.KEY_LEFTMETA,
    # Function keys F1-F12 (referenced lower-case after resolve() lowers).
    **{f"f{n}": getattr(ecodes, f"KEY_F{n}") for n in range(1, 13)},
    # Punctuation, keyed by the literal symbol to match "-"/"=" above so
    # config strings (e.g. a "[" keybind) resolve without a name lookup.
    "-": ecodes.KEY_MINUS,
    "=": ecodes.KEY_EQUAL,
    "[": ecodes.KEY_LEFTBRACE,
    "]": ecodes.KEY_RIGHTBRACE,
    "`": ecodes.KEY_GRAVE,
    "\\": ecodes.KEY_BACKSLASH,
    ";": ecodes.KEY_SEMICOLON,
    "'": ecodes.KEY_APOSTROPHE,
    ",": ecodes.KEY_COMMA,
    ".": ecodes.KEY_DOT,
    "/": ecodes.KEY_SLASH,
}

# All distinct ecodes the device must declare as capabilities.
_DEVICE_EVENTS: dict[int, list[int]] = {
    ecodes.EV_KEY: sorted(set(_KEY_NAME_MAP.values())),
}


class UinputKeyboard:
    """A lazily-created virtual keyboard that emits true HID key events.

    The underlying :class:`evdev.UInput` device is not created until the
    first key event (or an explicit :meth:`open`).  Use as a context
    manager, or call :meth:`close` explicitly, to release the kernel
    device handle.

    Device creation failure is logged at ERROR and re-raised - never
    swallowed.  An unmapped key name raises :class:`KeyError`; a silent
    no-op would re-introduce the dropped-keystroke bug this device fixes.
    """

    def __init__(self) -> None:
        self._device: UInput | None = None

    def resolve(self, key_name: str) -> int:
        """Return the evdev ecode for ``key_name`` (case-insensitive).

        Raises :class:`KeyError` for an unmapped key -- we fail loud
        rather than silently drop the keystroke.
        """
        lower = key_name.lower()
        try:
            return _KEY_NAME_MAP[lower]
        except KeyError:
            raise KeyError(
                f"No uinput ecode for key {key_name!r}; add it to "
                f"core.backends.uinput_keyboard._KEY_NAME_MAP"
            ) from None

    def open(self) -> None:
        """Create the virtual uinput device if it does not already exist.

        Idempotent: a second call is a no-op while the device is open.
        Raises (after logging at ERROR) if ``/dev/uinput`` is unwritable
        or device creation otherwise fails.
        """
        if self._device is not None:
            return
        try:
            self._device = UInput(events=_DEVICE_EVENTS, name=_DEVICE_NAME)
        except Exception:
            logger.error(
                "Failed to create uinput virtual keyboard %r - is /dev/uinput writable "
                "(ACL/udev)? Refusing to fall back to the broken xdotool key path.",
                _DEVICE_NAME,
            )
            raise
        logger.debug("Created uinput virtual keyboard %r", _DEVICE_NAME)

    def key_down(self, key_name: str) -> None:
        """Press ``key_name``: write EV_KEY value 1, then SYN_REPORT.

        Resolves the ecode before forcing device creation, so an
        unmapped key raises without leaving a half-open device.
        """
        code = self.resolve(key_name)
        if self._device is None:
            self.open()
        assert self._device is not None  # narrowed by open()
        self._device.write(ecodes.EV_KEY, code, 1)
        self._device.syn()

    def key_up(self, key_name: str) -> None:
        """Release ``key_name``: write EV_KEY value 0, then SYN_REPORT."""
        code = self.resolve(key_name)
        if self._device is None:
            self.open()
        assert self._device is not None  # narrowed by open()
        self._device.write(ecodes.EV_KEY, code, 0)
        self._device.syn()

    def tap(self, key_name: str) -> None:
        """Press then release ``key_name``.

        Kept deliberately simple (no internal sleep); callers that need a
        hold duration should sequence :meth:`key_down` / :meth:`key_up`.
        """
        self.key_down(key_name)
        self.key_up(key_name)

    def close(self) -> None:
        """Release the underlying uinput device handle.

        Idempotent and safe to call when the device was never opened.
        """
        if self._device is None:
            return
        self._device.close()
        self._device = None

    def __enter__(self) -> UinputKeyboard:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
