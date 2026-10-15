#!/usr/bin/env python3
"""Run standalone parse/lint gates, mocked Lua harnesses and Python tests."""

import os
import re
import signal
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# Browser mockups are local and untracked. Several harnesses compare the addon with a mockup.
# A clean export has no mockups/, so FS_MOCKUPS_DIR can name a directory to link in for the run.
# With no mockups/ and no FS_MOCKUPS_DIR (a public clone) those harnesses are skipped and counted;
# with either present, a missing mockup file is a real failure.
MISSING_MOCKUP = re.compile(r"No such file or directory: '([^']*[/\\]mockups[/\\][^']*)'")
MOCKUPS_ENV = "FS_MOCKUPS_DIR"


def missing_mockup(output: str) -> str | None:
    """The mockup path a harness failed to open, or None when the failure is something else."""
    match = MISSING_MOCKUP.search(output)
    if match and not Path(match.group(1)).exists():
        return match.group(1)
    return None


def link_mockups() -> None:
    """Symlink ROOT/mockups to $FS_MOCKUPS_DIR when mockups/ is absent."""
    link = ROOT / "mockups"
    source = os.environ.get(MOCKUPS_ENV)
    if link.exists() or link.is_symlink() or not source or not Path(source).is_dir():
        return
    link.symlink_to(Path(source).resolve(), target_is_directory=True)


def unlink_mockups() -> None:
    """Remove ROOT/mockups only when it is a symlink that resolves to $FS_MOCKUPS_DIR."""
    link = ROOT / "mockups"
    source = os.environ.get(MOCKUPS_ENV)
    if source and link.is_symlink() and link.resolve() == Path(source).resolve():
        link.unlink()


def main() -> int:
    """Stop on the first failed gate, harness, or Python test suite."""
    source = os.environ.get(MOCKUPS_ENV)
    if source and not Path(source).is_dir():
        print(f"{MOCKUPS_ENV} is set to {source!r}, which is not an existing directory")
        return 2
    # A link that was already there is the caller's own: only a link made below is removed.
    own_link = not ((ROOT / "mockups").exists() or (ROOT / "mockups").is_symlink())
    # SIGTERM raises SystemExit so the finally block below still removes the link; the handler
    # goes in first so no signal can arrive between creating the link and the try.
    previous = signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(128 + signum))
    try:
        link_mockups()
        return run_all()
    finally:
        signal.signal(signal.SIGTERM, previous)
        if own_link:
            unlink_mockups()


def run_all() -> int:
    """Run every gate in order; skipped harnesses are counted and reported at the end."""
    can_skip = not (ROOT / "mockups").exists() and not os.environ.get(MOCKUPS_ENV)
    skipped = 0
    commands = [
        [sys.executable, str(HERE / "private-name-gate.py")],
        [sys.executable, str(HERE / "parse-gate.py")],
        [sys.executable, str(HERE / "lua-lint.py"), "--fail-on", "high"],
    ]
    commands.extend(
        [sys.executable, str(path)] for path in sorted(HERE.glob("*-harness.py"))
    )
    commands.append([sys.executable, "-m", "pytest", "-q"])
    for command in commands:
        print("Running", " ".join(command), flush=True)
        result = subprocess.run(
            command, cwd=ROOT, check=False, text=True, errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        sys.stdout.write(result.stdout)
        if result.returncode:
            absent = missing_mockup(result.stdout)
            if can_skip and absent and command[1].endswith("-harness.py"):
                print(f"SKIPPED {Path(command[1]).name}: mockup not present ({absent})", flush=True)
                skipped += 1
                continue
            return result.returncode
    if skipped:
        print(f"{skipped} harnesses SKIPPED (no mockups/; set {MOCKUPS_ENV} for full coverage)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
