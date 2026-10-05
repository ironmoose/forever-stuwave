"""Linux absolute-pointer mouse via the kernel uinput subsystem.

Provides a TRUE absolute pointing device (``EV_ABS`` ``ABS_X``/``ABS_Y``
+ ``SYN_REPORT``) declared with ``INPUT_PROP_POINTER`` and an axis range
of ``0..screen-1``.  libinput maps such a device's absolute coordinates
straight to the desktop with NO pointer acceleration, so writing
``(x, y)`` places the OS cursor at desktop pixel ``(x, y)`` exactly.
This was proven live on GNOME Wayland + WoW-under-Wine: the absolute
device positions the cursor accurately where ``pyautogui.moveTo`` (an
absolute warp swallowed by Wine's relative pointer grab) does not.

This is the cursor-positioning half of the Linux input split.  The
relative device (:mod:`core.backends.uinput_mouse`) keeps owning camera
mouselook deltas (``EV_REL``) and button-hold ownership; this device
owns where the OS cursor IS.  Because we write every absolute point, the
current cursor position is simply the last point we wrote -- no need to
read it back (``pyautogui.position()`` is frozen under Wayland anyway).

Mirrors :class:`core.backends.uinput_mouse.UinputRelativeMouse` in
structure, lifecycle, and no-silent-fallback philosophy.  Importing this
module on a non-Linux platform raises ``ImportError`` at ``evdev``
import time, matching the relative device's platform guard.
"""

from __future__ import annotations

import logging
from types import TracebackType

from evdev import AbsInfo, UInput, ecodes

logger = logging.getLogger(__name__)

_DEVICE_NAME = "wow-bot-abs-pointer"

# Button-name -> evdev key code.  Only the two declared capabilities are
# mappable; anything else fails loud (no BTN_MIDDLE is declared), matching
# the relative device.
_BUTTON_CODES: dict[str, int] = {
    "left": ecodes.BTN_LEFT,
    "right": ecodes.BTN_RIGHT,
}


class UinputAbsMouse:
    """A lazily-created virtual absolute pointer that positions the cursor.

    Constructed with the desktop size ``(screen_w, screen_h)``; the
    ``ABS_X``/``ABS_Y`` axes span ``0..screen_w-1`` / ``0..screen_h-1`` so
    a written absolute value is a literal desktop pixel.  The underlying
    :class:`evdev.UInput` device is not created until the first
    :meth:`move_abs` (or an explicit :meth:`open`).  Use as a context
    manager, or call :meth:`close` explicitly, to release the kernel
    device handle.

    Device creation failure is logged at ERROR and re-raised - never
    swallowed.  A silent fallback to the broken absolute-warp path is
    exactly what hid the original "cursor won't move" bug.
    """

    def __init__(self, screen_w: int, screen_h: int) -> None:
        self._screen_w = screen_w
        self._screen_h = screen_h
        self._device: UInput | None = None

    def open(self) -> None:
        """Create the virtual uinput device if it does not already exist.

        Idempotent: a second call is a no-op while the device is open.
        Declares ``ABS_X``/``ABS_Y`` (range ``0..screen-1``) plus
        ``BTN_LEFT``/``BTN_RIGHT`` and the ``INPUT_PROP_POINTER`` property
        so libinput binds it as a flat, unaccelerated pointer.  Raises
        (after logging at ERROR) if ``/dev/uinput`` is unwritable or
        device creation otherwise fails.
        """
        if self._device is not None:
            return
        events = {
            ecodes.EV_KEY: [ecodes.BTN_LEFT, ecodes.BTN_RIGHT],
            ecodes.EV_ABS: [
                (
                    ecodes.ABS_X,
                    AbsInfo(
                        value=0,
                        min=0,
                        max=self._screen_w - 1,
                        fuzz=0,
                        flat=0,
                        resolution=0,
                    ),
                ),
                (
                    ecodes.ABS_Y,
                    AbsInfo(
                        value=0,
                        min=0,
                        max=self._screen_h - 1,
                        fuzz=0,
                        flat=0,
                        resolution=0,
                    ),
                ),
            ],
        }
        try:
            self._device = UInput(
                events=events,
                name=_DEVICE_NAME,
                input_props=[ecodes.INPUT_PROP_POINTER],
            )
        except Exception:
            logger.error(
                "Failed to create uinput abs pointer %r - is /dev/uinput writable "
                "(ACL/udev)? Refusing to fall back to absolute pointer warp.",
                _DEVICE_NAME,
            )
            raise
        logger.debug(
            "Created uinput abs pointer %r (%dx%d)",
            _DEVICE_NAME,
            self._screen_w,
            self._screen_h,
        )

    def move_abs(self, x: int, y: int) -> None:
        """Position the cursor at desktop pixel ``(x, y)``.

        Writes ``ABS_X x``, ``ABS_Y y``, then a ``SYN_REPORT`` to flush
        the batch.  Never emits ``EV_REL`` - this device is absolute only.
        ``x`` is clamped to ``[0, screen_w-1]`` and ``y`` to
        ``[0, screen_h-1]``.  Creates the device lazily on first use.
        """
        cx = max(0, min(int(x), self._screen_w - 1))
        cy = max(0, min(int(y), self._screen_h - 1))
        if self._device is None:
            self.open()
        assert self._device is not None  # narrowed by open()
        self._device.write(ecodes.EV_ABS, ecodes.ABS_X, cx)
        self._device.write(ecodes.EV_ABS, ecodes.ABS_Y, cy)
        self._device.syn()

    def _button_code(self, button: str) -> int:
        """Map a button name to its evdev key code, or fail loud.

        Mirrors :meth:`open`'s no-silent-fallback philosophy: an unknown
        button name is logged at ERROR and raises ``ValueError`` rather
        than guessing a code.  Only "left" and "right" are declared
        capabilities on this device.
        """
        try:
            return _BUTTON_CODES[button]
        except KeyError:
            logger.error(
                "Unknown mouse button %r - expected 'left' or 'right'. "
                "Refusing to guess a button code.",
                button,
            )
            raise ValueError(f"Unknown mouse button: {button!r}") from None

    def press(self, button: str) -> None:
        """Emit a button-down (``EV_KEY`` value 1) and flush with a SYN.

        ``button`` is "left" or "right"; anything else raises
        ``ValueError`` (after logging at ERROR).  Creates the device
        lazily on first use, matching :meth:`move_abs`.
        """
        code = self._button_code(button)
        if self._device is None:
            self.open()
        assert self._device is not None  # narrowed by open()
        self._device.write(ecodes.EV_KEY, code, 1)
        self._device.syn()

    def release(self, button: str) -> None:
        """Emit a button-up (``EV_KEY`` value 0) and flush with a SYN.

        ``button`` is "left" or "right"; anything else raises
        ``ValueError`` (after logging at ERROR).  Creates the device
        lazily on first use, matching :meth:`move_abs`.
        """
        code = self._button_code(button)
        if self._device is None:
            self.open()
        assert self._device is not None  # narrowed by open()
        self._device.write(ecodes.EV_KEY, code, 0)
        self._device.syn()

    def click(self, button: str) -> None:
        """Emit a single down-then-up for ``button`` at the current spot.

        A :meth:`press` immediately followed by a :meth:`release` - no
        artificial dwell.  The caller is responsible for positioning the
        cursor (via :meth:`move_abs`) onto the target before clicking;
        this method clicks wherever the cursor currently is.
        """
        self.press(button)
        self.release(button)

    def close(self) -> None:
        """Release the underlying uinput device handle.

        Idempotent and safe to call when the device was never opened.
        """
        if self._device is None:
            return
        self._device.close()
        self._device = None

    def __enter__(self) -> UinputAbsMouse:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
