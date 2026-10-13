"""Offline tests for fsdev_support/capture_wayland.py token and dialog cleanup.

No D-Bus session, portal, GStreamer or WoW client is touched: the jeepney
connection and the portal client are replaced with fakes.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest
from jeepney import HeaderFields

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux-only Wayland capture")

MODULE_PATH = Path(__file__).resolve().parent / "fsdev_support" / "capture_wayland.py"
LEGACY_TOKEN_NAME = "screencast_restore_token"


@pytest.fixture
def cw(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """Load the module with HOME redirected so the cache dir is a temp dir."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PRIMAL_FARMER_CONSENT_KEYS", "")
    spec = importlib.util.spec_from_file_location("cw_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Per-app restore token file
# ---------------------------------------------------------------------------


def test_token_file_is_per_app_and_not_the_legacy_shared_file(
    cw: types.ModuleType, tmp_path: Path
) -> None:
    cache = tmp_path / ".cache" / "wow-tbc-bots"
    assert cw._RESTORE_TOKEN_PATH == cache / f"{LEGACY_TOKEN_NAME}.{cw._APP_ID}"
    assert cw._RESTORE_TOKEN_PATH.name == "screencast_restore_token.forever-stuwave"


def test_legacy_shared_token_is_never_read_or_overwritten(
    cw: types.ModuleType, tmp_path: Path
) -> None:
    cache = tmp_path / ".cache" / "wow-tbc-bots"
    cache.mkdir(parents=True)
    legacy = cache / LEGACY_TOKEN_NAME
    legacy.write_text("bot-token", encoding="utf-8")

    assert cw._load_restore_token() == ""

    cw._save_restore_token("fsdev-token")

    assert cw._load_restore_token() == "fsdev-token"
    assert (cache / "screencast_restore_token.forever-stuwave").read_text() == "fsdev-token"
    assert legacy.read_text() == "bot-token"


# ---------------------------------------------------------------------------
# Dialog cleanup on timeout / denial
# ---------------------------------------------------------------------------


class FakeReply:
    def __init__(self, body: tuple = (), message_type: object = "method_return") -> None:
        self.body = body
        self.header = types.SimpleNamespace(message_type=message_type, fields={4: "err"})


class FakeConn:
    """Stand-in for a jeepney connection; records every method call."""

    def __init__(
        self,
        cw: types.ModuleType,
        receive: object,
        close_raises: bool = False,
        close_error_reply: bool = False,
        returned_path: str = "/req/path",
        send_raises: str = "",
    ) -> None:
        self._cw = cw
        self._receive = receive
        self._close_raises = close_raises
        self._close_error_reply = close_error_reply
        self._returned_path = returned_path
        self._send_raises = send_raises  # member whose call raises (e.g. "Start")
        self.calls: list[tuple[str, str, str]] = []  # (member, object path, interface)

    def send_and_get_reply(self, msg: object, timeout: float | None = None) -> FakeReply:
        fields = msg.header.fields  # type: ignore[attr-defined]
        member = fields[HeaderFields.member]
        path = fields[HeaderFields.path]
        self.calls.append((member, path, fields[HeaderFields.interface]))
        if member == "Close" and self._close_raises:
            raise OSError("bus gone")
        if member == "Close" and self._close_error_reply:
            return FakeReply(message_type=self._cw.MessageType.error)
        if member == self._send_raises:
            raise TimeoutError("no reply")
        if member in {"AddMatch", "RemoveMatch", "Close"}:
            return FakeReply()
        return FakeReply(body=(self._returned_path,))

    def receive(self, timeout: float | None = None) -> object:
        if isinstance(self._receive, Exception):
            raise self._receive
        return self._receive


def _client(cw: types.ModuleType, conn: FakeConn) -> object:
    client = cw._PortalClient.__new__(cw._PortalClient)
    client._conn = conn
    client._unique = ":1.99"
    client._registered = True
    return client


def _members(conn: FakeConn) -> list[str]:
    return [m for m, _, _ in conn.calls]


def _closes(conn: FakeConn) -> list[tuple[str, str]]:
    """(object path, interface) of every Close call."""
    return [(p, i) for m, p, i in conn.calls if m == "Close"]


def test_response_timeout_closes_the_pending_request(cw: types.ModuleType) -> None:
    conn = FakeConn(cw, TimeoutError())
    client = _client(cw, conn)

    with pytest.raises(cw._PortalTimeoutError):
        client._call_and_wait("Start", "o", ("/s",), "/req/path", "Start")

    assert _closes(conn) == [("/req/path", "org.freedesktop.portal.Request")]


def test_timeout_closes_the_returned_path_when_it_differs_from_the_predicted_one(
    cw: types.ModuleType,
) -> None:
    conn = FakeConn(cw, TimeoutError(), returned_path="/req/actual")
    client = _client(cw, conn)

    with pytest.raises(cw._PortalTimeoutError):
        client._call_and_wait("Start", "o", ("/s",), "/req/predicted", "Start")

    assert _closes(conn) == [("/req/actual", "org.freedesktop.portal.Request")]


def test_failed_send_closes_the_predicted_request(cw: types.ModuleType) -> None:
    conn = FakeConn(cw, TimeoutError(), send_raises="Start")
    client = _client(cw, conn)

    with pytest.raises(TimeoutError, match="no reply"):  # the send error, not the close
        client._call_and_wait("Start", "o", ("/s",), "/req/predicted", "Start")

    assert _closes(conn) == [("/req/predicted", "org.freedesktop.portal.Request")]


def test_denied_response_raises_without_closing_a_finished_request(cw: types.ModuleType) -> None:
    signal = types.SimpleNamespace(
        header=types.SimpleNamespace(
            message_type=cw.MessageType.signal,
            fields={
                HeaderFields.path: "/req/path",
                HeaderFields.interface: cw._REQUEST_IFACE,
                HeaderFields.member: "Response",
            },
        ),
        body=(1, {}),
    )
    conn = FakeConn(cw, signal)
    client = _client(cw, conn)

    with pytest.raises(RuntimeError, match="user cancelled"):
        client._call_and_wait("Start", "o", ("/s",), "/req/path", "Start")

    assert "Close" not in _members(conn)


def test_close_failures_are_logged_and_swallowed(
    cw: types.ModuleType, caplog: pytest.LogCaptureFixture
) -> None:
    conn = FakeConn(cw, TimeoutError(), close_raises=True)
    client = _client(cw, conn)

    with caplog.at_level("WARNING"):
        with pytest.raises(cw._PortalTimeoutError):  # the timeout, not the close error
            client._call_and_wait("Start", "o", ("/s",), "/req/path", "Start")
        client.close_session("/org/freedesktop/portal/desktop/session/x")

    assert "Request.Close failed" in caplog.text
    assert "Session.Close failed" in caplog.text


def test_close_error_reply_is_logged_and_swallowed(
    cw: types.ModuleType, caplog: pytest.LogCaptureFixture
) -> None:
    conn = FakeConn(cw, TimeoutError(), close_error_reply=True)
    client = _client(cw, conn)

    with caplog.at_level("WARNING"):
        with pytest.raises(cw._PortalTimeoutError):
            client._call_and_wait("Start", "o", ("/s",), "/req/path", "Start")

    assert "Request.Close returned an error" in caplog.text


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


class FakePortal:
    """_PortalClient replacement; subclasses override the failing step."""

    instances: list[FakePortal] = []

    def __init__(self) -> None:
        self.events: list[str] = []
        FakePortal.instances.append(self)

    def create_session(self) -> str:
        self.events.append("create")
        return "/session/1"

    def select_sources(self, session_handle: str, restore_token: str = "") -> None:
        self.events.append(f"select:{restore_token}")

    def start(self, session_handle: str) -> object:
        self.events.append("start")
        raise RuntimeError("Start: timed out waiting for portal Response")

    def close_session(self, session_handle: str) -> None:
        self.events.append("close_session")

    def close(self) -> None:
        self.events.append("close")


def _cast(cw: types.ModuleType, monkeypatch: pytest.MonkeyPatch, portal_cls: type) -> object:
    FakePortal.instances = []
    monkeypatch.setattr(cw, "_PortalClient", portal_cls)
    monkeypatch.setattr(cw, "_check_gst_launch_available", lambda: None)
    monkeypatch.setattr(cw, "_spawn_consent_autoaccept", lambda: None)
    return cw.WaylandScreenCast()


def test_failed_start_closes_session_and_does_not_retry(
    cw: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    cast = _cast(cw, monkeypatch, FakePortal)

    with pytest.raises(RuntimeError, match="timed out"):
        cast.capture_full_screen_to_array()

    assert len(FakePortal.instances) == 1
    events = FakePortal.instances[0].events
    assert events.count("start") == 1
    assert events[-2:] == ["close_session", "close"]
    assert cast._portal is None and cast._session_handle is None


class StaleTokenPortal(FakePortal):
    """SelectSources rejects any non-empty restore_token with a code-2 failure."""

    def select_sources(self, session_handle: str, restore_token: str = "") -> None:
        super().select_sources(session_handle, restore_token)
        if restore_token:
            raise RuntimeError("SelectSources: portal returned code 2")


def test_stale_token_is_unlinked_and_retried_once_without_it(
    cw: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    cw._save_restore_token("stale")
    cast = _cast(cw, monkeypatch, StaleTokenPortal)

    with pytest.raises(RuntimeError, match="timed out"):  # Start still fails afterwards
        cast.capture_full_screen_to_array()

    events = FakePortal.instances[0].events
    assert [e for e in events if e.startswith("select")] == ["select:stale", "select:"]
    assert not cw._RESTORE_TOKEN_PATH.exists()
    assert events[-2:] == ["close_session", "close"]


class AlwaysRejectingPortal(FakePortal):
    """SelectSources fails with code 2 even without a token."""

    def select_sources(self, session_handle: str, restore_token: str = "") -> None:
        super().select_sources(session_handle, restore_token)
        raise RuntimeError("SelectSources: portal returned code 2")


def test_failing_token_retry_tears_the_session_down(
    cw: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    cw._save_restore_token("stale")
    cast = _cast(cw, monkeypatch, AlwaysRejectingPortal)

    with pytest.raises(RuntimeError, match="code 2"):
        cast.capture_full_screen_to_array()

    events = FakePortal.instances[0].events
    assert [e for e in events if e.startswith("select")] == ["select:stale", "select:"]
    assert "start" not in events
    assert events[-2:] == ["close_session", "close"]
    assert cast._portal is None


class StartedPortal(FakePortal):
    """Start succeeds and hands back a real fd, so a later failure has one to leak."""

    fds: list[int] = []

    def start(self, session_handle: str) -> object:
        self.events.append("start")
        return [(7, {"size": (4, 4)})], ""

    def open_pipewire_remote(self, session_handle: str) -> int:
        read_fd, write_fd = os.pipe()
        os.close(write_fd)
        StartedPortal.fds.append(read_fd)
        return read_fd


class ExplodingReader:
    def __init__(self, *args: object) -> None:
        pass

    def start(self, **kwargs: object) -> None:
        raise RuntimeError("gst-launch died")

    def stop(self) -> None:
        pass


def test_failure_after_start_releases_everything_and_next_call_restarts(
    cw: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    StartedPortal.fds = []
    cast = _cast(cw, monkeypatch, StartedPortal)
    monkeypatch.setattr(cw, "_GstFrameReader", ExplodingReader)

    with pytest.raises(RuntimeError, match="gst-launch died"):
        cast.capture_full_screen_to_array()

    (fd,) = StartedPortal.fds
    with pytest.raises(OSError):  # EBADF: the PipeWire fd was closed
        os.fstat(fd)
    assert cast._reader is None and cast._pw_fd is None
    assert cast._portal is None and cast._session_handle is None
    assert FakePortal.instances[0].events[-2:] == ["close_session", "close"]

    with pytest.raises(RuntimeError, match="gst-launch died"):
        cast.capture_full_screen_to_array()

    assert len(FakePortal.instances) == 2  # the second call started a fresh session
