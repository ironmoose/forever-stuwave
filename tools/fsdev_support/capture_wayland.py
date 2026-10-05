"""Wayland screen capture via the XDG ScreenCast portal + PipeWire.

The existing :mod:`core.capture` uses ``mss``, which calls ``XGetImage()``
under the hood.  On GNOME 50 + Wayland + NVIDIA that path is broken
(``XGetImage() failed``).  This module is the Wayland-native replacement:
it opens an ``org.freedesktop.portal.ScreenCast`` session, asks the
portal for a PipeWire node carrying the primary monitor, then consumes
frames from that stream via a ``gst-launch-1.0`` subprocess piped into
this process.

Design notes (deliberate deviations from the task brief, recorded so the
next maintainer doesn't re-litigate them):

* The portal handshake is done with :mod:`jeepney` (pure-Python blocking
  D-Bus), **not** :mod:`gi.repository.Gio`.  The bot's Poetry venv is
  Python 3.13; Fedora 44 only ships ``python3-gobject`` for the system
  Python 3.14.  Building PyGObject for 3.13 in the venv pulls a chain of
  ``-devel`` packages (cairo-devel, glib2-devel, gobject-introspection-
  devel, python3.13-devel, ...) that aren't installed and require sudo.
  ``jeepney`` is ``pip install``-able, supports UNIX-fd messages, and is
  enough for the portal dance.
* PipeWire frame consumption runs in a ``gst-launch-1.0`` child process
  rather than an in-process ``Gst.Pipeline``, for the same reason: no
  PyGObject means no in-process GStreamer.  We hand the portal's
  PipeWire fd to the child via ``subprocess`` fd inheritance, then read
  raw BGRA frames from the child's stdout.  Same data, one extra
  process.

Public API mirrors :class:`core.capture.ScreenCapture` so it can be
swapped in by the Linux backend.

Linux-only -- importing this module on any other platform raises
``ImportError``.
"""

from __future__ import annotations

import json
import logging
import os
import select
import struct
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import numpy as np

if sys.platform != "linux":  # pragma: no cover - import-time guard
    raise ImportError("core.capture_wayland can only be imported on Linux")

try:
    from jeepney import DBusAddress, MatchRule, MessageType, new_method_call
    from jeepney.io.blocking import open_dbus_connection
except ImportError as exc:  # pragma: no cover - dependency guard
    raise ImportError(
        "jeepney is required for Wayland portal capture; "
        "install with `poetry add jeepney` (pure-Python, no compile)."
    ) from exc

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PORTAL_BUS = "org.freedesktop.portal.Desktop"
_PORTAL_PATH = "/org/freedesktop/portal/desktop"
_SCREENCAST_IFACE = "org.freedesktop.portal.ScreenCast"
_SESSION_IFACE = "org.freedesktop.portal.Session"
_REQUEST_IFACE = "org.freedesktop.portal.Request"
# Host Registry portal (xdg-desktop-portal >= 1.21). Registering a stable
# app_id lets the portal match a saved screen-share permission grant back to
# this process, so the GNOME consent picker is skipped on subsequent launches.
_REGISTRY_IFACE = "org.freedesktop.host.portal.Registry"
# Must match the basename of the installed desktop entry
# (~/.local/share/applications/forever-stuwave.desktop) so the grant resolves.
_APP_ID = "forever-stuwave"

# Portal Response codes (see XDG portal spec)
_RESPONSE_SUCCESS = 0
_RESPONSE_CANCELLED = 1
_RESPONSE_FAILED = 2

_TYPE_MONITOR = 1  # SelectSources.types bit for MONITOR sources
_CURSOR_MODE_EMBEDDED = 2

_PORTAL_TIMEOUT_S = 30.0
_FRAME_TIMEOUT_S = 1.0
_FRAME_CACHE_MAX_AGE_S = 0.016  # ~60Hz; reuse cached frame within this window

_CACHE_DIR = Path.home() / ".cache" / "wow-tbc-bots"
_RESTORE_TOKEN_PATH = _CACHE_DIR / "screencast_restore_token"

# Auto-accept the GNOME screencast consent dialog by tapping a key through the
# uinput virtual keyboard while the dialog holds keyboard focus. On mutter 50
# the restore-token suppression is unreliable, so the dialog appears on most
# launches; tapping Enter dismisses it without the user touching anything.
# Tunable live without code edits:
#   PRIMAL_FARMER_CONSENT_KEYS  comma-separated key taps, default "enter"
#                               (e.g. "tab,enter" or "space"); empty/"none" disables
#   PRIMAL_FARMER_CONSENT_DELAY seconds to wait for the dialog to render, default 1.5
_CONSENT_KEYS: list[str] = [
    k.strip()
    for k in os.environ.get("PRIMAL_FARMER_CONSENT_KEYS", "enter").split(",")
    if k.strip() and k.strip().lower() != "none"
]
_CONSENT_DELAY_S: float = float(os.environ.get("PRIMAL_FARMER_CONSENT_DELAY", "1.5"))

# Feature flag: exact-RGB capture pipeline (Fix 1 -- capture exactness).
#
# When truthy ("1", "true", or "yes"), the GStreamer pipeline constrains the
# pipewiresrc SOURCE PAD to packed BGRx and passes explicit
# ``dither=none chroma-mode=none matrix-mode=full-range`` options to
# videoconvert. This prevents the compositor (GNOME 50 + NVIDIA at 5120×1440)
# from delivering a YUV / subsampled / limited-range buffer that videoconvert
# then corrupts with:
#   - lossy chroma upsampling (neighbor-blend)
#   - limited->full range matrix remap
#   - Bayer dithering (videoconvert default)
# All three stages corrupt the exact RGB bytes that WA indicator pixels encode,
# causing the observed ±1..4 LSB high-byte flicker in decoded position while
# the character stands still.
#
# Safety: if the hardened pipeline fails to produce a warm-up frame (compositor
# cannot deliver packed RGB), the code logs a WARNING and falls back to the
# legacy unconstrained pipeline automatically, so capture never bricks.
#
# Flag: set WOW_CAPTURE_EXACT_RGB=1 (or "true"/"yes") to enable.
# Default: OFF (legacy pipeline, preserving current behavior).
_EXACT_RGB: bool = os.environ.get("WOW_CAPTURE_EXACT_RGB", "").strip().lower() in (
    "1",
    "true",
    "yes",
)

# Feature flag: drain-to-newest frame on every read (Fix 2 -- staleness).
#
# Under load (~7 fps bot loop vs ~60 fps PipeWire source) frames accumulate in
# gst-launch's stdout pipe.  Without draining, ``read_frame`` always returns
# the OLDEST buffered frame, introducing up to several hundred milliseconds of
# latency that the SensorJumpFilter sees as impossible positional jumps.
#
# When ON:
#   - ``read_frame`` calls FIONREAD after each complete-frame read.  If
#     ``bytes_available >= frame_bytes`` (at least one more complete frame is
#     buffered), it reads the next frame and discards the previous one, looping
#     up to 240 times.  The LAST (newest) complete frame is returned.
#   - The GStreamer pipeline inserts a ``queue leaky=downstream
#     max-size-buffers=3`` element before ``fdsink`` so the GStreamer graph
#     never back-pressures the PipeWire source when the consumer is slow.
#   - Confirmation log: ``logger.info("capture drained %d stale frame(s) this
#     sec (backlog)", n)`` throttled to ~once/sec when any frames were skipped.
#     Observing n > 0 under load CONFIRMS the staleness hypothesis.
#
# When OFF (set WOW_CAPTURE_FRESH_FRAMES=0 / "false" / "no"):
#   - Byte-identical to the pre-fix single-read behaviour; no drain, no queue.
#
# Default: ON (unset / "" / "1" / "true" / "yes" all evaluate to True).
# Only "0", "false", "no" (case-insensitive) disable it.
_FRESH_FRAMES: bool = os.environ.get("WOW_CAPTURE_FRESH_FRAMES", "").strip().lower() not in (
    "0",
    "false",
    "no",
)


def _build_gst_pipeline(
    pw_fd: int,
    node_id: int,
    width: int,
    height: int,
    exact_rgb: bool = False,
    fresh_frames: bool = False,
) -> str:
    """Build the GStreamer pipeline string for PipeWire screen capture.

    This is a pure function (no I/O, no side effects) extracted so tests can
    assert on the pipeline string without launching a real subprocess.

    ``exact_rgb=False`` (default)
        Legacy unconstrained pipeline -- byte-identical to the string that was
        previously hardcoded in ``_GstFrameReader.start()``:

        ``pipewiresrc fd=N path=M do-timestamp=true ! videoconvert !
        video/x-raw,format=BGRA,width=W,height=H ! fdsink fd=1 sync=false``

    ``exact_rgb=True``  (WOW_CAPTURE_EXACT_RGB=1)
        Hardened pipeline that constrains the SOURCE PAD to packed BGRx and
        disables the three videoconvert stages that corrupt WA pixel bytes:

        ``pipewiresrc fd=N path=M do-timestamp=true ! video/x-raw,format=BGRx !
        videoconvert dither=none chroma-mode=none matrix-mode=full-range !
        video/x-raw,format=BGRA,width=W,height=H ! fdsink fd=1 sync=false``

        - ``format=BGRx`` on the source cap: forces the compositor to deliver
          packed 4-byte-aligned RGB instead of YUV.
        - ``dither=none``: suppresses Bayer dithering (videoconvert default).
        - ``chroma-mode=none``: disables lossy chroma upsampling.
        - ``matrix-mode=full-range``: skips the limited→full range remap.

    ``fresh_frames=True``  (WOW_CAPTURE_FRESH_FRAMES on; default)
        Inserts ``queue leaky=downstream max-size-buffers=3 max-size-bytes=0
        max-size-time=0`` immediately before ``fdsink``.  The leaky queue
        prevents the GStreamer graph from back-pressuring the PipeWire source
        when the bot consumer loop is slow (~7 fps): the queue silently drops
        the oldest buffered frame so gst never stalls waiting for the pipe
        write to drain.  Works for both ``exact_rgb=False`` and ``True``.
    """
    bgra_caps = f"video/x-raw,format=BGRA,width={width},height={height}"
    src = f"pipewiresrc fd={pw_fd} path={node_id} do-timestamp=true"
    _fdsink = "fdsink fd=1 sync=false"
    _leaky_queue = "queue leaky=downstream max-size-buffers=3 max-size-bytes=0 max-size-time=0"
    sink = f"{_leaky_queue} ! {_fdsink}" if fresh_frames else _fdsink

    if exact_rgb:
        return (
            f"{src} ! "
            "video/x-raw,format=BGRx ! "
            "videoconvert dither=none chroma-mode=none matrix-mode=full-range ! "
            f"{bgra_caps} ! "
            f"{sink}"
        )
    return f"{src} ! " "videoconvert ! " f"{bgra_caps} ! " f"{sink}"


class _ConsentHandle:
    """Cancellable handle for the consent auto-accept background thread.

    Call :meth:`cancel` after a successful portal ``Start`` to prevent the
    background worker from tapping Enter into the now-focused WoW window when
    the restore-token skipped the consent dialog entirely.
    """

    def __init__(self, thread: threading.Thread, cancel_event: threading.Event) -> None:
        self._thread = thread
        self._cancel = cancel_event

    def cancel(self) -> None:
        """Signal the worker to abort before tapping any key."""
        self._cancel.set()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _request_path_for(unique_name: str, handle_token: str) -> str:
    """Derive the portal Request object path from sender unique name + token.

    Per the XDG portal spec, the portal will emit ``Response`` on a path
    determined deterministically by the caller's bus name and the
    ``handle_token`` option.  Subscribing to that path BEFORE making the
    method call avoids the race where the portal replies before our
    signal subscription is in place.
    """
    sender_clean = unique_name.lstrip(":").replace(".", "_")
    return f"/org/freedesktop/portal/desktop/request/{sender_clean}/{handle_token}"


def _new_handle_token(prefix: str) -> str:
    """Generate a unique handle_token for a portal call."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _load_restore_token() -> str:
    """Read the cached restore_token (empty string if none saved)."""
    try:
        return _RESTORE_TOKEN_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
    except OSError as exc:
        logger.warning("Failed to read restore_token from %s: %s", _RESTORE_TOKEN_PATH, exc)
        return ""


def _save_restore_token(token: str) -> None:
    """Persist a new restore_token so future runs skip the consent dialog."""
    if not token:
        return
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _RESTORE_TOKEN_PATH.write_text(token, encoding="utf-8")
        logger.info("Saved ScreenCast restore_token to %s", _RESTORE_TOKEN_PATH)
    except OSError as exc:
        logger.warning("Failed to save restore_token: %s", exc)


def _spawn_consent_autoaccept() -> _ConsentHandle | None:
    """Arm a background tap of the consent dialog's accept key.

    Returns a :class:`_ConsentHandle` (started daemon thread + cancel token),
    or ``None`` when disabled (empty ``_CONSENT_KEYS``).

    The worker waits ``_CONSENT_DELAY_S`` for the GNOME screencast dialog to
    render, then taps each configured key through the uinput virtual keyboard
    -- which is the ONLY input path that reaches the focused portal dialog
    (X synthetic events do not).

    Call ``handle.cancel()`` immediately after a successful portal ``Start``
    returns: if the restore-token caused ``Start`` to return before the delay
    expires the cancel will wake the worker early so it exits without tapping
    anything.  If the dialog was dismissed by the tap before ``Start``
    returned, the cancel is a harmless no-op.

    Fail-soft: any error is logged at WARNING and swallowed so capture still
    proceeds (the user can always click the dialog manually).
    """
    if not _CONSENT_KEYS:
        return None

    cancel_event = threading.Event()

    def _worker() -> None:
        # Block for _CONSENT_DELAY_S; returns True early if cancel() was called.
        if cancel_event.wait(_CONSENT_DELAY_S):
            logger.debug("Consent auto-accept cancelled (Start succeeded; no dialog shown)")
            return
        try:
            # Lazy import: keeps evdev out of the import path when disabled and
            # isolates the Linux-only backend to the thread that uses it.
            from fsdev_support.uinput_keyboard import UinputKeyboard

            kb = UinputKeyboard()
            kb.open()
            try:
                for i, key in enumerate(_CONSENT_KEYS):
                    logger.info("Consent auto-accept: tapping %r", key)
                    kb.tap(key)
                    if i < len(_CONSENT_KEYS) - 1:
                        time.sleep(0.25)
            finally:
                kb.close()
        except Exception as exc:  # noqa: BLE001 - fail-soft by design
            logger.warning("Consent auto-accept failed (dismiss the dialog manually): %s", exc)

    thread = threading.Thread(target=_worker, name="consent-autoaccept", daemon=True)
    thread.start()
    logger.info("Consent auto-accept armed: keys=%s delay=%.1fs", _CONSENT_KEYS, _CONSENT_DELAY_S)
    return _ConsentHandle(thread, cancel_event)


def _check_gst_launch_available() -> None:
    """Raise RuntimeError early if gst-launch-1.0 or pipewiresrc isn't usable."""
    try:
        subprocess.run(
            ["gst-launch-1.0", "--version"],
            check=True,
            capture_output=True,
            timeout=5,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "gst-launch-1.0 not on PATH; install gstreamer1 (dnf install gstreamer1)"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"gst-launch-1.0 failed --version probe: {exc}") from exc

    try:
        result = subprocess.run(
            ["gst-inspect-1.0", "pipewiresrc"],
            check=True,
            capture_output=True,
            timeout=5,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("gst-inspect-1.0 not found; install gstreamer1") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        raise RuntimeError(
            "pipewiresrc element not available -- install "
            "gstreamer1-plugins-good (Fedora) / gstreamer1.0-plugins-good (Debian). "
            f"gst-inspect-1.0 stderr: {stderr.strip()}"
        ) from exc
    if b"pipewiresrc" not in result.stdout:
        raise RuntimeError("gst-inspect-1.0 pipewiresrc returned unexpected output")


def _available_bytes(fd: int) -> int:
    """Return the number of bytes currently buffered and readable from *fd*.

    Uses the POSIX ``FIONREAD`` ioctl, which on Linux returns the exact count
    of bytes that a subsequent ``os.read`` can consume without blocking.
    Applicable to pipes (the gst-launch stdout path) as well as sockets.

    Imported lazily so the module stays importable-for-inspection on non-Linux
    hosts (``fcntl`` / ``termios`` are Unix-only stdlib).
    """
    import array
    import fcntl
    import termios

    buf = array.array("i", [0])
    try:
        fcntl.ioctl(fd, termios.FIONREAD, buf)
        return buf[0]
    except OSError as exc:
        logger.debug("FIONREAD failed on fd %d, treating as 0 bytes: %s", fd, exc)
        return 0


# ---------------------------------------------------------------------------
# Portal client
# ---------------------------------------------------------------------------


class _PortalClient:
    """Minimal blocking ScreenCast portal client built on jeepney.

    One instance per session.  Owns the D-Bus connection and the
    Request-signal subscription dance.  Not thread-safe; the bot uses
    it from a single thread.
    """

    def __init__(self) -> None:
        # enable_fds=True is REQUIRED so the connection negotiates the
        # UNIX_FD authentication line; without it the daemon rejects the
        # fd-bearing OpenPipeWireRemote reply with ECONNRESET.
        self._conn = open_dbus_connection(enable_fds=True)
        self._unique = self._conn.unique_name
        if not self._unique:
            self._conn.close()
            raise RuntimeError("D-Bus connection has no unique name")
        self._registered = False
        # Register the app_id as the FIRST portal interaction, before any
        # CreateSession/SelectSources/Start call, so the saved screen-share
        # grant can be matched back to this app.
        self._register_app_id()

    def _register_app_id(self) -> None:
        """Register a stable app_id with the host Registry portal.

        This is a best-effort enhancement: a terminal-launched, non-sandboxed
        process otherwise presents an empty app_id, so xdg-desktop-portal
        cannot match the persisted screen-share permission grant back to the
        app and falls back to the consent picker on every launch.  Registering
        ``_APP_ID`` (which resolves to the installed ``.desktop`` entry) lets
        the portal reuse the grant silently from the second launch onward.

        Fail-soft: if the Registry interface is unavailable (older portal),
        the capture still works -- the consent dialog just keeps reappearing --
        so a failure here is logged and swallowed rather than raised.  Called
        at most once per connection.
        """
        if self._registered:
            return
        self._registered = True
        registry_addr = DBusAddress(
            _PORTAL_PATH,
            bus_name=_PORTAL_BUS,
            interface=_REGISTRY_IFACE,
        )
        # Empty options dict; values, if any, would be variant ('sig', value)
        # tuples per this module's a{sv} convention.
        options: dict[str, tuple[str, object]] = {}
        msg = new_method_call(registry_addr, "Register", "sa{sv}", (_APP_ID, options))
        try:
            reply = self._conn.send_and_get_reply(msg)
        except Exception as exc:
            logger.warning(
                "host Registry portal unavailable; screen-share consent " "dialog may reappear: %s",
                exc,
            )
            return
        if reply.header.message_type == MessageType.error:
            logger.warning(
                "host Registry portal unavailable; screen-share consent " "dialog may reappear: %s",
                reply.header.fields.get(4),
            )
            return
        logger.info("Registered app_id '%s' with host Registry portal", _APP_ID)

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception as exc:
            logger.debug("Error closing D-Bus connection: %s", exc, exc_info=True)

    def _screencast_addr(self) -> DBusAddress:
        return DBusAddress(_PORTAL_PATH, bus_name=_PORTAL_BUS, interface=_SCREENCAST_IFACE)

    def _request_addr(self, request_path: str) -> DBusAddress:
        return DBusAddress(request_path, bus_name=_PORTAL_BUS, interface=_REQUEST_IFACE)

    def _add_match(self, rule: MatchRule) -> None:
        msg_bus = DBusAddress(
            "/org/freedesktop/DBus",
            bus_name="org.freedesktop.DBus",
            interface="org.freedesktop.DBus",
        )
        msg = new_method_call(msg_bus, "AddMatch", "s", (rule.serialise(),))
        reply = self._conn.send_and_get_reply(msg)
        if reply.header.message_type == MessageType.error:
            raise RuntimeError(f"AddMatch failed: {reply.body}")

    def _remove_match(self, rule: MatchRule) -> None:
        msg_bus = DBusAddress(
            "/org/freedesktop/DBus",
            bus_name="org.freedesktop.DBus",
            interface="org.freedesktop.DBus",
        )
        msg = new_method_call(msg_bus, "RemoveMatch", "s", (rule.serialise(),))
        try:
            self._conn.send_and_get_reply(msg)
        except Exception as exc:
            logger.debug("RemoveMatch failed (ignored): %s", exc)

    def _wait_for_response(
        self, request_path: str, step_name: str, timeout: float = _PORTAL_TIMEOUT_S
    ) -> dict:
        """Block until the portal emits Response on request_path.

        Returns the results dict.  Raises RuntimeError on
        non-success Response code or timeout.
        """
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"{step_name}: timed out waiting for portal Response")
            try:
                msg = self._conn.receive(timeout=remaining)
            except TimeoutError as exc:
                raise RuntimeError(f"{step_name}: timed out waiting for portal Response") from exc
            if msg is None:
                continue
            if msg.header.message_type != MessageType.signal:
                continue
            hdr = msg.header.fields
            # Field 3 = PATH, 2 = INTERFACE, 4 = MEMBER (jeepney HeaderFields enum values)
            path = hdr.get(1)  # PATH
            interface = hdr.get(2)  # INTERFACE
            member = hdr.get(3)  # MEMBER
            if path == request_path and interface == _REQUEST_IFACE and member == "Response":
                code, results = msg.body
                if code == _RESPONSE_SUCCESS:
                    return dict(results)
                if code == _RESPONSE_CANCELLED:
                    raise RuntimeError(f"{step_name}: user cancelled (code 1)")
                if code == _RESPONSE_FAILED:
                    raise RuntimeError(
                        f"{step_name}: portal reported failure (code 2); "
                        f"results={dict(results)}"
                    )
                raise RuntimeError(f"{step_name}: unknown Response code {code}")

    # ------------------------------------------------------------------
    # ScreenCast method wrappers
    # ------------------------------------------------------------------

    def _call_and_wait(
        self,
        method: str,
        signature: str,
        body: tuple,
        request_path: str,
        step_name: str,
    ) -> dict:
        """Subscribe to the Response signal, send the method call, wait for Response."""
        match_rule = MatchRule(
            type="signal",
            interface=_REQUEST_IFACE,
            member="Response",
            path=request_path,
        )
        self._add_match(match_rule)
        try:
            msg = new_method_call(self._screencast_addr(), method, signature, body)
            reply = self._conn.send_and_get_reply(msg)
            if reply.header.message_type == MessageType.error:
                raise RuntimeError(
                    f"{step_name}: D-Bus error: {reply.header.fields.get(4)} {reply.body}"
                )
            returned_path = reply.body[0] if reply.body else None
            if returned_path and returned_path != request_path:
                # The portal may return a different path than the one we predicted.
                # Re-subscribe on the actual path.
                logger.debug(
                    "%s: portal returned path %s, predicted %s -- re-subscribing",
                    step_name,
                    returned_path,
                    request_path,
                )
                self._remove_match(match_rule)
                match_rule = MatchRule(
                    type="signal",
                    interface=_REQUEST_IFACE,
                    member="Response",
                    path=returned_path,
                )
                self._add_match(match_rule)
                request_path = returned_path
            return self._wait_for_response(request_path, step_name)
        finally:
            self._remove_match(match_rule)

    def create_session(self) -> str:
        """Run CreateSession and return the session handle."""
        handle_token = _new_handle_token("session")
        session_token = _new_handle_token("sess")
        request_path = _request_path_for(self._unique, handle_token)
        options = {
            "handle_token": ("s", handle_token),
            "session_handle_token": ("s", session_token),
        }
        result = self._call_and_wait(
            "CreateSession",
            "a{sv}",
            (options,),
            request_path,
            "CreateSession",
        )
        session_handle = result.get("session_handle")
        if isinstance(session_handle, tuple):  # variant ('s', value)
            session_handle = session_handle[1] if len(session_handle) == 2 else session_handle[0]
        if not isinstance(session_handle, str):
            raise RuntimeError(f"CreateSession: missing session_handle in results: {result}")
        logger.info("ScreenCast session created: %s", session_handle)
        return session_handle

    def select_sources(self, session_handle: str, restore_token: str = "") -> None:
        handle_token = _new_handle_token("select")
        request_path = _request_path_for(self._unique, handle_token)
        options = {
            "handle_token": ("s", handle_token),
            "types": ("u", _TYPE_MONITOR),
            "multiple": ("b", False),
            "cursor_mode": ("u", _CURSOR_MODE_EMBEDDED),
            # persist_mode=2 means "permanent until revoked" -- pairs with restore_token
            "persist_mode": ("u", 2),
        }
        if restore_token:
            options["restore_token"] = ("s", restore_token)
        self._call_and_wait(
            "SelectSources",
            "oa{sv}",
            (session_handle, options),
            request_path,
            "SelectSources",
        )
        logger.debug("SelectSources complete (restore_token=%s)", "yes" if restore_token else "no")

    def start(self, session_handle: str) -> tuple[list[tuple[int, dict]], str]:
        """Run Start, return (streams, new_restore_token).

        ``streams`` is the list returned by the portal: each entry is
        ``(node_id, properties_dict)``.
        """
        handle_token = _new_handle_token("start")
        request_path = _request_path_for(self._unique, handle_token)
        options = {"handle_token": ("s", handle_token)}
        result = self._call_and_wait(
            "Start",
            "osa{sv}",
            (session_handle, "", options),
            request_path,
            "Start",
        )
        streams_variant = result.get("streams")
        if streams_variant is None:
            raise RuntimeError(f"Start: no streams in result: {result}")
        # streams is variant 'a(ua{sv})'
        if isinstance(streams_variant, tuple) and len(streams_variant) == 2:
            _, streams_value = streams_variant
        else:
            streams_value = streams_variant
        streams: list[tuple[int, dict]] = []
        for entry in streams_value:
            node_id = int(entry[0])
            props = dict(entry[1]) if len(entry) > 1 else {}
            streams.append((node_id, props))
        if not streams:
            raise RuntimeError("Start: stream list is empty")
        restore_token_variant = result.get("restore_token")
        if isinstance(restore_token_variant, tuple) and len(restore_token_variant) == 2:
            new_restore_token = restore_token_variant[1]
        else:
            new_restore_token = restore_token_variant or ""
        if not isinstance(new_restore_token, str):
            new_restore_token = ""
        logger.info(
            "ScreenCast Start: %d stream(s), restore_token=%s",
            len(streams),
            "received" if new_restore_token else "none",
        )
        return streams, new_restore_token

    def open_pipewire_remote(self, session_handle: str) -> int:
        """Call OpenPipeWireRemote and return the inherited UNIX fd."""
        msg = new_method_call(
            self._screencast_addr(),
            "OpenPipeWireRemote",
            "oa{sv}",
            (session_handle, {}),
        )
        reply = self._conn.send_and_get_reply(msg)
        if reply.header.message_type == MessageType.error:
            raise RuntimeError(
                f"OpenPipeWireRemote: D-Bus error: {reply.header.fields.get(4)} {reply.body}"
            )
        # jeepney inlines received UNIX_FDS into the body as FileDescriptor
        # wrapper objects.  Calling .to_raw_fd() transfers ownership of the
        # raw int to us so it doesn't get auto-closed by the wrapper's
        # __del__.
        if not reply.body:
            raise RuntimeError(
                "OpenPipeWireRemote: reply body was empty. "
                "Is the D-Bus connection negotiating UNIX_FD support?"
            )
        wrapper = reply.body[0]
        if hasattr(wrapper, "to_raw_fd"):
            fd = wrapper.to_raw_fd()
        else:
            fd = int(wrapper)
        if fd < 0:
            raise RuntimeError(f"OpenPipeWireRemote: invalid fd {fd}")
        logger.info("OpenPipeWireRemote: got fd=%d", fd)
        return fd

    def close_session(self, session_handle: str) -> None:
        """Call Session.Close on the session handle."""
        addr = DBusAddress(session_handle, bus_name=_PORTAL_BUS, interface=_SESSION_IFACE)
        msg = new_method_call(addr, "Close")
        try:
            self._conn.send_and_get_reply(msg)
        except Exception as exc:
            logger.debug("Session.Close failed (ignored): %s", exc)


# ---------------------------------------------------------------------------
# GStreamer frame reader
# ---------------------------------------------------------------------------


class _GstFrameReader:
    """Reads BGRA frames from a gst-launch-1.0 subprocess.

    Pipeline: ``pipewiresrc fd=N path=NODE ! videoconvert !
    video/x-raw,format=BGRA ! fdsink fd=1``.  We launch gst-launch with
    ``pass_fds`` so the PipeWire fd is inherited, and read raw bytes
    from the child's stdout.

    The frame format (width / height) is parsed once by running a tiny
    probe pipeline (``pipewiresrc num-buffers=1 ! videoconvert !
    video/x-raw,format=BGRA ! fakesink dump=false`` with caps logging)
    before the main loop starts.  Cheaper alternative: ask the portal
    Stream properties for ``size`` -- which is what we do here.
    """

    def __init__(self, pw_fd: int, node_id: int, width: int, height: int) -> None:
        self._pw_fd = pw_fd
        self._node_id = node_id
        self._width = width
        self._height = height
        self._frame_bytes = width * height * 4
        self._proc: subprocess.Popen | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_lines: list[str] = []
        # Drain-to-newest state (WOW_CAPTURE_FRESH_FRAMES)
        self._fresh_frames: bool = False
        self._last_drain_log_at: float = 0.0

    def start(self, exact_rgb: bool = False, fresh_frames: bool = False) -> None:
        if self._proc is not None:
            return
        self._fresh_frames = fresh_frames
        # Note: pipewiresrc reads from `fd` which is interpreted in its own
        # process.  Because we pass_fds=[pw_fd], the fd number is preserved
        # in the child.  fdsink fd=1 = the child's stdout, which we pipe.
        pipeline = _build_gst_pipeline(
            self._pw_fd,
            self._node_id,
            self._width,
            self._height,
            exact_rgb=exact_rgb,
            fresh_frames=fresh_frames,
        )
        argv = ["gst-launch-1.0", "-q", *pipeline.split()]
        logger.info("Launching: %s", " ".join(argv))
        self._proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            pass_fds=(self._pw_fd,),
            bufsize=0,
        )
        # Drain stderr in the background so a slow PipeWire warning doesn't
        # eventually fill the pipe and stall the child.
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr, name="gst-stderr-drain", daemon=True
        )
        self._stderr_thread.start()

    def _drain_stderr(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        try:
            for raw in self._proc.stderr:
                line = raw.decode("utf-8", errors="replace").rstrip()
                self._stderr_lines.append(line)
                logger.debug("gst stderr: %s", line)
                if len(self._stderr_lines) > 200:
                    self._stderr_lines = self._stderr_lines[-200:]
        except Exception as exc:
            logger.debug("gst stderr drain ended: %s", exc)

    def _read_one_frame(self, stdout_fd: int, deadline: float, timeout: float) -> bytes:
        """Read exactly ``self._frame_bytes`` bytes from *stdout_fd*.

        Blocks until the full frame is available, the deadline expires, or EOF
        is reached.  Returns the raw bytes.  Raises ``RuntimeError`` on
        timeout or EOF -- the caller decides what to do with the result.

        This helper is factored out of :meth:`read_frame` so the drain-to-
        newest loop can call it multiple times without duplicating the
        select/read bookkeeping.
        """
        buf = bytearray()
        while len(buf) < self._frame_bytes:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                err_tail = "\n".join(self._stderr_lines[-10:])
                raise RuntimeError(
                    f"Timed out reading frame from gst-launch after {timeout}s "
                    f"(got {len(buf)}/{self._frame_bytes} bytes); "
                    f"stderr tail:\n{err_tail}"
                )
            ready, _, _ = select.select([stdout_fd], [], [], remaining)
            if not ready:
                continue
            chunk = os.read(stdout_fd, self._frame_bytes - len(buf))
            if not chunk:
                err_tail = "\n".join(self._stderr_lines[-10:])
                raise RuntimeError(
                    f"gst-launch closed stdout after {len(buf)}/{self._frame_bytes} "
                    f"bytes; stderr tail:\n{err_tail}"
                )
            buf.extend(chunk)
        return bytes(buf)

    def read_frame(self, timeout: float = _FRAME_TIMEOUT_S) -> np.ndarray:
        """Read the newest available BGRA frame from the GStreamer subprocess.

        When ``WOW_CAPTURE_FRESH_FRAMES`` is ON (the default), drains any
        backlog of complete frames from the pipe before returning: after
        reading the first complete frame it checks ``FIONREAD``; if at least
        one more full frame is buffered it reads the next, discards the
        previous, and repeats -- up to 240 times.  The last (newest) complete
        frame is returned.  Stale frames drained are counted and logged (once
        per second) at INFO level to confirm the staleness hypothesis live.

        When ``WOW_CAPTURE_FRESH_FRAMES`` is OFF the behaviour is byte-
        identical to the original single-read: exactly one frame is consumed
        regardless of how many are buffered.

        Returns a numpy array of shape ``(height, width, 4)`` dtype
        ``uint8``.  Raises ``RuntimeError`` on timeout, EOF, or short read.
        """
        if self._proc is None or self._proc.stdout is None:
            raise RuntimeError("GStreamer reader not started")
        if self._proc.poll() is not None:
            err_tail = "\n".join(self._stderr_lines[-20:])
            raise RuntimeError(
                f"gst-launch died (exit={self._proc.returncode}); " f"stderr tail:\n{err_tail}"
            )

        deadline = time.monotonic() + timeout
        stdout_fd = self._proc.stdout.fileno()
        frame_data = self._read_one_frame(stdout_fd, deadline, timeout)

        if self._fresh_frames:
            n_skipped = 0
            for _ in range(240):
                if _available_bytes(stdout_fd) < self._frame_bytes:
                    break
                frame_data = self._read_one_frame(stdout_fd, deadline, timeout)
                n_skipped += 1
            if n_skipped > 0:
                now = time.monotonic()
                if now - self._last_drain_log_at >= 1.0:
                    self._last_drain_log_at = now
                    logger.info("capture drained %d stale frame(s) this sec (backlog)", n_skipped)

        arr = np.frombuffer(frame_data, dtype=np.uint8).reshape(self._height, self._width, 4)
        return arr

    def stop(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                logger.warning("gst-launch did not terminate in 2s, killing")
                self._proc.kill()
                self._proc.wait(timeout=1.0)
        except Exception as exc:
            logger.warning("Error stopping gst-launch: %s", exc)
        finally:
            self._proc = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _extract_stream_size(props: dict) -> tuple[int, int] | None:
    """Pull (width, height) out of a portal stream properties dict.

    The size variant is ``(ii)``.  Different portal versions sometimes
    omit it; the caller falls back to a probe in that case.
    """
    size = props.get("size")
    if size is None:
        return None
    if isinstance(size, tuple) and len(size) == 2 and isinstance(size[0], str):
        # variant: ('(ii)', (w, h))
        value = size[1]
    else:
        value = size
    try:
        w, h = int(value[0]), int(value[1])
        if w > 0 and h > 0:
            return (w, h)
    except (TypeError, ValueError, IndexError):
        return None
    return None


def _probe_stream_size(pw_fd: int, node_id: int) -> tuple[int, int]:
    """Fallback: run gst-launch once with a caps-querying sink to learn size.

    Without PyGObject we can't use appsink directly; instead we let gst-launch
    -v print caps to stderr after the convert, and regex out width/height.
    """
    pipeline_dbg = (
        f"pipewiresrc fd={pw_fd} path={node_id} num-buffers=1 ! "
        "videoconvert ! video/x-raw,format=BGRA ! fakesink"
    )
    proc = subprocess.Popen(
        ["gst-launch-1.0", "-v", *pipeline_dbg.split()],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        pass_fds=(pw_fd,),
    )
    try:
        stdout, stderr = proc.communicate(timeout=15)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        proc.wait(timeout=2)
        raise RuntimeError("Probe pipeline timed out trying to determine stream size") from exc
    blob = (stdout + stderr).decode("utf-8", errors="replace")
    # Caps lines look like:
    #   /GstPipeline:pipeline0/GstCapsFilter:capsfilter0.GstPad:src:
    #     caps = video/x-raw, format=(string)BGRA, width=(int)5120, height=(int)1440, ...
    import re

    match_w = re.search(r"width=\(int\)(\d+)", blob)
    match_h = re.search(r"height=\(int\)(\d+)", blob)
    if match_w and match_h:
        return int(match_w.group(1)), int(match_h.group(1))
    raise RuntimeError(
        "Could not parse stream size from gst-launch probe output; " f"stderr tail: {blob[-500:]}"
    )


class WaylandScreenCast:
    """Wayland-native screen capture via ScreenCast portal + PipeWire.

    Public API mirrors :class:`core.capture.ScreenCapture` (BGRA arrays
    out, ``capture_region``, ``capture_full_screen_to_array``,
    ``capture_to_array``, ``close``).

    Frames are pulled from a GStreamer subprocess; the most recent frame
    is cached for ``_FRAME_CACHE_MAX_AGE_S`` seconds so back-to-back
    ``capture_region`` calls (the bot does several per tick: pixel
    bridge, YOLO, mob detection) only spend one PipeWire pull per tick.
    """

    def __init__(self) -> None:
        _check_gst_launch_available()
        self._portal: _PortalClient | None = None
        self._session_handle: str | None = None
        self._pw_fd: int | None = None
        self._reader: _GstFrameReader | None = None
        self._width: int = 0
        self._height: int = 0
        self._cached_frame: np.ndarray | None = None
        self._cached_at: float = 0.0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _ensure_started(self) -> None:
        if self._reader is not None:
            return
        self._portal = _PortalClient()
        self._session_handle = self._portal.create_session()

        restore_token = _load_restore_token()
        try:
            self._portal.select_sources(self._session_handle, restore_token=restore_token)
        except RuntimeError as exc:
            # If the cached restore_token has been revoked the portal will
            # surface a failure on SelectSources.  Retry once without it so
            # the user gets a fresh consent dialog.
            if restore_token and "code 2" in str(exc):
                logger.warning(
                    "SelectSources failed with cached restore_token; retrying "
                    "without it (consent dialog will appear): %s",
                    exc,
                )
                try:
                    _RESTORE_TOKEN_PATH.unlink(missing_ok=True)
                except OSError:
                    pass
                self._portal.select_sources(self._session_handle, restore_token="")
            else:
                raise

        # Arm auto-accept just before Start blocks on the consent dialog.
        # Cancel immediately after Start returns: if the restore-token caused
        # Start to return fast (no dialog), the cancel wakes the worker before
        # it taps Enter into the now-focused WoW window.  If the dialog was
        # already dismissed by the tap, the cancel is a harmless no-op.
        _consent_handle = _spawn_consent_autoaccept()
        try:
            streams, new_restore_token = self._portal.start(self._session_handle)
        finally:
            if _consent_handle is not None:
                _consent_handle.cancel()
        if new_restore_token:
            _save_restore_token(new_restore_token)

        node_id, props = streams[0]
        size = _extract_stream_size(props)
        self._pw_fd = self._portal.open_pipewire_remote(self._session_handle)

        if size is None:
            logger.info("Stream properties did not include size; probing pipeline")
            size = _probe_stream_size(self._pw_fd, node_id)
        self._width, self._height = size
        logger.info("ScreenCast stream: node=%d size=%dx%d", node_id, self._width, self._height)

        self._reader = _GstFrameReader(self._pw_fd, node_id, self._width, self._height)

        if _EXACT_RGB:
            # Hardened pipeline: constrain source to BGRx and disable the three
            # videoconvert stages that corrupt WA indicator pixel bytes on
            # GNOME 50 + NVIDIA (dither, chroma-upsampling, range-remap).
            logger.info(
                "WOW_CAPTURE_EXACT_RGB=1: starting GStreamer with exact-RGB pipeline "
                "(BGRx source, dither=none chroma-mode=none matrix-mode=full-range)"
            )
            self._reader.start(exact_rgb=True, fresh_frames=_FRESH_FRAMES)
            try:
                # Warm-up: pull one frame to confirm the hardened pipeline negotiates
                # successfully with the compositor before declaring it active.
                self._cached_frame = self._reader.read_frame(timeout=5.0)
                logger.info("Exact-RGB pipeline active and producing frames")
            except RuntimeError as exc:
                # Compositor cannot deliver packed BGRx (YUV-only source): fall back
                # to the legacy unconstrained pipeline so capture never bricks.
                logger.warning(
                    "Exact-RGB pipeline failed to produce a warm-up frame (%s); "
                    "falling back to legacy pipeline (set WOW_CAPTURE_EXACT_RGB= to "
                    "suppress this warning).",
                    exc,
                )
                self._reader.stop()
                self._reader.start(exact_rgb=False, fresh_frames=_FRESH_FRAMES)
                try:
                    self._cached_frame = self._reader.read_frame(timeout=5.0)
                    logger.info("Legacy pipeline active after exact-RGB fallback")
                except RuntimeError:
                    self._reader.stop()
                    self._reader = None
                    raise
        else:
            logger.info("Starting GStreamer with legacy pipeline (WOW_CAPTURE_EXACT_RGB not set)")
            self._reader.start(exact_rgb=False, fresh_frames=_FRESH_FRAMES)
            # Warm-up: first frame can take ~100ms while pipewire negotiates.  Pull
            # one frame eagerly so subsequent calls don't pay that cost.
            self._cached_frame = self._reader.read_frame(timeout=5.0)

        self._cached_at = time.monotonic()

    def _current_frame(self) -> np.ndarray:
        """Return a fresh-enough BGRA full-screen frame."""
        with self._lock:
            self._ensure_started()
            assert self._reader is not None
            now = time.monotonic()
            if self._cached_frame is not None and (now - self._cached_at) < _FRAME_CACHE_MAX_AGE_S:
                return self._cached_frame
            frame = self._reader.read_frame()
            self._cached_frame = frame
            self._cached_at = time.monotonic()
            return frame

    # ------------------------------------------------------------------
    # Public capture API (matches ScreenCapture)
    # ------------------------------------------------------------------

    def capture_full_screen_to_array(self) -> np.ndarray:
        """Return BGRA numpy array of the entire monitor, shape (H, W, 4)."""
        # Return a copy so callers can mutate without poisoning the cache.
        return self._current_frame().copy()

    def capture_to_array(self) -> np.ndarray:
        """Alias for :meth:`capture_full_screen_to_array`."""
        return self.capture_full_screen_to_array()

    def capture_region(self, x: int, y: int, w: int, h: int) -> np.ndarray:
        """Return BGRA numpy array of the absolute screen region (x..x+w, y..y+h)."""
        if w <= 0 or h <= 0:
            raise ValueError(f"Invalid region dimensions: w={w}, h={h}")
        frame = self._current_frame()
        fh, fw, _ = frame.shape
        x1 = max(0, min(int(x), fw))
        y1 = max(0, min(int(y), fh))
        x2 = max(0, min(int(x) + int(w), fw))
        y2 = max(0, min(int(y) + int(h), fh))
        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"Region ({x},{y},{w},{h}) lies entirely outside frame {fw}x{fh}")
        return frame[y1:y2, x1:x2].copy()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        with self._lock:
            if self._reader is not None:
                try:
                    self._reader.stop()
                except Exception as exc:
                    logger.warning("Error stopping GStreamer reader: %s", exc)
                self._reader = None
            if self._pw_fd is not None:
                try:
                    os.close(self._pw_fd)
                except OSError as exc:
                    logger.debug("Error closing PipeWire fd %d: %s", self._pw_fd, exc)
                self._pw_fd = None
            if self._portal is not None:
                if self._session_handle is not None:
                    try:
                        self._portal.close_session(self._session_handle)
                    except Exception as exc:
                        logger.debug("Error closing portal session: %s", exc)
                try:
                    self._portal.close()
                except Exception as exc:
                    logger.debug("Error closing portal client: %s", exc)
                self._portal = None
            self._session_handle = None
            self._cached_frame = None
            self._cached_at = 0.0

    def __enter__(self) -> WaylandScreenCast:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()


# Re-export for convenience
__all__ = ["WaylandScreenCast"]


# Module is only useful at runtime, but expose a few internals for unit tests.
# The leading-underscore names signal these are not stable API.
_internal_test_hooks = {
    "_APP_ID": _APP_ID,
    "_REGISTRY_IFACE": _REGISTRY_IFACE,
    "_PortalClient": _PortalClient,
    "_GstFrameReader": _GstFrameReader,
    "_extract_stream_size": _extract_stream_size,
    "_request_path_for": _request_path_for,
    "_load_restore_token": _load_restore_token,
    "_save_restore_token": _save_restore_token,
    "_ConsentHandle": _ConsentHandle,
    "_spawn_consent_autoaccept": _spawn_consent_autoaccept,
    "_build_gst_pipeline": _build_gst_pipeline,
    "_EXACT_RGB": _EXACT_RGB,
    "_FRESH_FRAMES": _FRESH_FRAMES,
    "_available_bytes": _available_bytes,
}

# Quiet the unused-import warnings for symbols only used in type hints / tests.
_ = (json, struct)  # reserved; will be wired into the probe path if portal omits size
