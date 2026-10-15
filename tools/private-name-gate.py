#!/usr/bin/env python3
"""Fail when a personal name, local machine detail or private email fragment appears in a tracked file.

The repository is public. Authorship is credited to the GitHub handle only, and design
history is written neutrally ("the player", "seen in game"). This gate keeps a person's
name or mail account from creeping back into code comments, docs, mockups or file names.

Inside a git checkout it scans `git ls-files`; in a plain export (an archive of HEAD) it
walks the tree. Binary files are skipped. Exit 0 = clean, otherwise the count of hits.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Every pattern is assembled from pieces so this file does not contain what it forbids.
# Names are case-insensitive; the personal first name and surname match whole words only.
PATTERNS = {
    "personal name": "(?<![a-z])park" + "er(?![a-z])",
    "legal first name": r"(?<![a-z])pa" + r"ul(?![a-z])",
    "mail account": "air" + "ete",
    "local user name": "khil" + "drak",
    "home directory": "/ho" + "me/",
    "mail domain": "gma" + r"il\.com",
    "windows user path": r"c:\\+us" + "ers",
}
FORBIDDEN = {label: re.compile(pattern, re.IGNORECASE) for label, pattern in PATTERNS.items()}
SKIP_DIRS = {"mockups", ".git", ".venv", ".venv-lua", "__pycache__", ".pytest_cache", "dist", "debug"}


def candidate_files() -> list[Path]:
    """Tracked files when git can list them, otherwise every file under the root."""
    try:
        listed = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z"],
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        listed = b""
    if listed:
        return [ROOT / name for name in listed.decode().split("\0") if name]
    return [
        path
        for path in sorted(ROOT.rglob("*"))
        if path.is_file() and not SKIP_DIRS.intersection(path.relative_to(ROOT).parts)
    ]


def find_hits(path: Path) -> list[str]:
    """One `file:line: text` entry per offending line, plus one if the name is a path."""
    rel = path.relative_to(ROOT).as_posix()
    hits = []
    if any(rx.search(rel) for rx in FORBIDDEN.values()):
        hits.append(f"{rel}: file name")
    try:
        data = path.read_bytes()
    except OSError:
        return hits
    if b"\0" in data:
        return hits
    for number, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
        labels = [label for label, rx in FORBIDDEN.items() if rx.search(line)]
        if labels:
            hits.append(f"{rel}:{number}: [{', '.join(labels)}] {line.strip()[:120]}")
    return hits


def main() -> int:
    hits = [hit for path in candidate_files() if path.is_file() for hit in find_hits(path)]
    for hit in hits:
        print(hit)
    if hits:
        print(f"private-name-gate: {len(hits)} forbidden occurrence(s); use the GitHub handle or neutral wording")
    else:
        print("private-name-gate: clean")
    return len(hits)


if __name__ == "__main__":
    sys.exit(min(main(), 255))
