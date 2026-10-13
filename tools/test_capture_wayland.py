"""Offline tests for fsdev_support/capture_wayland.py token and dialog cleanup.

No D-Bus session, portal, GStreamer or WoW client is touched: the jeepney
connection and the portal client are replaced with fakes.
"""

from __future__ import annotations

import importlib.util
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
    def __init__(self, body: tuple = (), error: bool = False) -> None:
        self.body = body
        self.header = types.SimpleNamespace(
            message_type="error" if error else "method_return", fields={4: "err"}
        )


class FakeConn:
    """Stand-in for a jeepney connection; records every method call by member."""

    def __init__(self, cw: types.ModuleType, receive: object, close_raises: bool = False) -> None:
        self._receive = receive
        self._close_raises = close_raises
        self.calls: list[tuple[str, str]] = []  # (member, object path)

    def send_and_get_reply(self, msg: object, timeout: float | None = None) -> FakeReply:
        fields = msg.header.fields  # type: ignore[attr-defined]
        member = fields[HeaderFields.member]
        path = fields[HeaderFields.path]
        self.calls.append((member, path))
        if member == "Close" and self._close_raises:
            raise OSError("bus gone")
        if member in {"AddMatch", "RemoveMatch", "Close"}:
            return FakeReply()
        return FakeReply(body=("/req/path",))

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
    return [m for m, _ in conn.calls]


def test_response_timeout_closes_the_pending_request(cw: types.ModuleType) -> None:
    conn = FakeConn(cw, TimeoutError())
    client = _client(cw, conn)

    with pytest.raises(cw._PortalTimeoutError):
        client._call_and_wait("Start", "o", ("/s",), "/req/path", "Start")

    assert [c for c in conn.calls if c[0] == "Close"] == [("Close", "/req/path")]


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


class FakePortal:
    """_PortalClient replacement whose Start times out."""

    instances: list[FakePortal] = []

    def __init__(self) -> None:
        self.events: list[str] = []
        FakePortal.instances.append(self)

    def create_session(self) -> str:
        self.events.append("create")
        return "/session/1"

    def select_sources(self, session_handle: str, restore_token: str = "") -> None:
        self.events.append(f"select:{restore_token}")

    def start(self, session_handle: str) -> None:
        self.events.append("start")
        raise RuntimeError("Start: timed out waiting for portal Response")

    def close_session(self, session_handle: str) -> None:
        self.events.append("close_session")

    def close(self) -> None:
        self.events.append("close")


def test_failed_start_closes_session_and_does_not_retry(
    cw: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    FakePortal.instances = []
    monkeypatch.setattr(cw, "_PortalClient", FakePortal)
    monkeypatch.setattr(cw, "_check_gst_launch_available", lambda: None)
    monkeypatch.setattr(cw, "_spawn_consent_autoaccept", lambda: None)
    cast = cw.WaylandScreenCast()

    with pytest.raises(RuntimeError, match="timed out"):
        cast.capture_full_screen_to_array()

    assert len(FakePortal.instances) == 1
    events = FakePortal.instances[0].events
    assert events.count("start") == 1
    assert events[-2:] == ["close_session", "close"]
    assert cast._portal is None and cast._session_handle is None
