"""tools/taint-watch.py keeps a blocked-action taint log across the truncation a /reload causes."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("taint_watch", Path(__file__).with_name("taint-watch.py"))
taint_watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(taint_watch)

BLOCK_LINE = "11/10 11:53:41.100  An action was blocked because of taint from forever-stuwave - UseContainerItem()\n"
NOISE = "11/10 11:54:42.497  Execution tainted by Questie while reading global Questie - Keybindings.lua:221\n"


def test_noise_only_is_not_saved(tmp_path: Path) -> None:
    log, out = tmp_path / "taint.log", tmp_path / "out"
    log.write_text(NOISE)
    assert taint_watch.Watcher(log, out).poll() is None
    assert not out.exists()


def test_a_block_is_saved_and_survives_the_reload_truncation(tmp_path: Path) -> None:
    log, out = tmp_path / "taint.log", tmp_path / "out"
    w = taint_watch.Watcher(log, out)
    log.write_text(NOISE)
    w.poll()
    with open(log, "a") as f:
        f.write(BLOCK_LINE)
    first = w.poll()
    assert first is not None and BLOCK_LINE in first.read_text() and NOISE in first.read_text()

    # /reload: the client truncates and starts over with login noise only.
    log.write_text(NOISE)
    assert w.poll() is None
    assert BLOCK_LINE in first.read_text()


def test_growth_after_a_block_rewrites_the_same_capture(tmp_path: Path) -> None:
    log, out = tmp_path / "taint.log", tmp_path / "out"
    w = taint_watch.Watcher(log, out)
    log.write_text(BLOCK_LINE)
    first = w.poll()
    with open(log, "a") as f:
        f.write(NOISE)
    assert w.poll() == first
    assert first.read_text() == BLOCK_LINE + NOISE
    assert w.poll() is None  # nothing new, nothing rewritten
