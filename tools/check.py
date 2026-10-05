#!/usr/bin/env python3
"""Run standalone parse/lint gates, mocked Lua harnesses and Python tests."""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def main() -> int:
    """Stop on the first failed gate, harness, or Python test suite."""
    commands = [
        [sys.executable, str(HERE / "parse-gate.py")],
        [sys.executable, str(HERE / "lua-lint.py"), "--fail-on", "high"],
    ]
    commands.extend(
        [sys.executable, str(path)] for path in sorted(HERE.glob("*-harness.py"))
    )
    commands.append([sys.executable, "-m", "pytest", "-q"])
    for command in commands:
        print("Running", " ".join(command), flush=True)
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
