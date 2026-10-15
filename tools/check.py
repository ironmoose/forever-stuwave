#!/usr/bin/env python3
"""Run standalone parse/lint gates, mocked Lua harnesses and Python tests."""

import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# Browser mockups are local and untracked. A harness that compares the addon with a mockup
# crashes on the missing file in a clean checkout; that is a skip, not a failure.
MISSING_MOCKUP = re.compile(r"No such file or directory: '([^']*[/\\]mockups[/\\][^']*)'")


def missing_mockup(output: str) -> str | None:
    """The mockup path a harness failed to open, or None when the failure is something else."""
    match = MISSING_MOCKUP.search(output)
    if match and not Path(match.group(1)).exists():
        return match.group(1)
    return None


def main() -> int:
    """Stop on the first failed gate, harness, or Python test suite."""
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
            if absent and command[1].endswith("-harness.py"):
                print(f"SKIPPED {Path(command[1]).name}: mockup not present ({absent})", flush=True)
                continue
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
