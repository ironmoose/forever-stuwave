#!/usr/bin/env python3
"""Lua 5.1 parse gate for the ForeverSynthwave addon -- the Windows equivalent
of Fedora's `luajit -bl` check.

WoW runs Lua 5.1. A syntax error in one .lua file makes the client skip that
whole file silently -- the addon "loads" and the component just never appears.
That has already cost this project a session (CastBars.lua shipped with a raw
UTF-8 en dash inside a Lua pattern, which embeds newlines and produced
"unfinished string near ..."; the file never loaded and the cast bars were
simply absent).

This compiles every file with a real LuaJIT 2.1 runtime (Lua 5.1 semantics) via
lupa, so the check matches what the game's parser will do. Compile only -- it
never executes addon code, so WoW globals being absent is irrelevant.

Usage:
    tools/.venv-lua/Scripts/python.exe addons/parse-gate.py
    tools/.venv-lua/Scripts/python.exe addons/parse-gate.py path/to/file.lua ...

Exit 0 = every file parses. Non-zero = the count of files that failed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaRuntime
except ImportError:
    sys.exit(
        "lupa is missing. Create the tooling venv:\n"
        '  "C:/Python312/python.exe" -m venv tools/.venv-lua\n'
        "  UV_LINK_MODE=copy uv pip install --python tools/.venv-lua/Scripts/python.exe lupa"
    )

ADDON_DIR = Path(__file__).resolve().parent.parent

# Lua allows 200 local variables per function, and a file is one function: at 200 the file
# stops compiling ("too many local variables"; luac 5.4 refuses it, LuaJIT has zero headroom
# left at exactly 200). CombatHud.lua reached 200 without a single warning, so the gate fails a
# file at 190 and leaves room for one more change to be made calmly.
LOCAL_LIMIT_FAIL = 190
_LOCAL_FUNCTION = re.compile(r"local\s+function\s+\w+")
_LOCAL_NAMES = re.compile(r"local\s+([A-Za-z_][\w\s,]*?)\s*(?:=|$)")


def count_file_scope_locals(source: str) -> int:
    """Locals declared at file scope: statements that start in column 0 (indented ones live
    in a block or function). `local a, b = ...` counts two, `local function f` one. A
    line-based count, so it can be off by a name or two; the threshold leaves slack for that."""
    total = 0
    for line in source.splitlines():
        if _LOCAL_FUNCTION.match(line):
            total += 1
            continue
        match = _LOCAL_NAMES.match(line)
        if match:
            total += len([n for n in match.group(1).split(",") if n.strip()])
    return total


def lua_files(argv: list[str]) -> list[Path]:
    if argv:
        return [Path(a).resolve() for a in argv]
    return sorted(ADDON_DIR.glob("*.lua"))


def toc_order(addon_dir: Path) -> list[str]:
    """File list the .toc actually loads, so a file left out is visible."""
    toc = addon_dir / "ForeverSynthwave.toc"
    if not toc.exists():
        return []
    names = []
    for raw in toc.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not line.lower().endswith((".lua", ".xml")):
            continue
        # .toc paths use backslashes and may point into subdirectories
        # (libs/...), so normalise before comparing against the filesystem.
        names.append(line.replace("\\", "/"))
    return names


def display_name(path: Path, addon_dir: Path) -> str:
    """Return path relative to addon_dir if under it, else the full path."""
    try:
        return str(path.relative_to(addon_dir))
    except ValueError:
        # path is not under addon_dir
        return str(path)


def main() -> int:
    paths = lua_files(sys.argv[1:])
    if not paths:
        print(f"no .lua files found under {ADDON_DIR}")
        return 1

    runtime = LuaRuntime()
    # Wrap in Lua so success and failure both come back as a fixed 2-tuple;
    # bare loadstring returns ONE value on success, which unpacks badly.
    load = runtime.eval(
        "function(src, name)"
        "  local chunk, err = loadstring(src, name)"
        "  return (chunk ~= nil), err "
        "end"
    )

    failures = 0
    for path in paths:
        source = path.read_bytes().decode("utf-8", errors="surrogateescape")
        ok, err = load(source, f"@{path.name}")
        if not ok:
            failures += 1
            print(f"FAIL  {display_name(path, ADDON_DIR)}: {err}")
        else:
            locals_used = count_file_scope_locals(source)
            if locals_used >= LOCAL_LIMIT_FAIL:
                failures += 1
                print(f"FAIL  {display_name(path, ADDON_DIR)}: {locals_used} file-scope locals "
                      f"(limit 200, gate fails at {LOCAL_LIMIT_FAIL}); fold constants into a table")
            else:
                print(f"ok    {display_name(path, ADDON_DIR)} ({locals_used} file-scope locals)")

    # A file that parses but was never added to the .toc is a silent no-op.
    if not sys.argv[1:]:
        listed = toc_order(ADDON_DIR)
        listed_roots = {n for n in listed if "/" not in n}
        on_disk = {p.name for p in paths}
        for name in sorted(on_disk - listed_roots):
            print(f"WARN  {name} parses but is NOT listed in ForeverSynthwave.toc")
        # Resolve every listed entry against the addon dir, so subdirectory
        # entries (the vendored libs) are checked for real rather than assumed
        # missing just because the top-level glob did not pick them up.
        for name in listed:
            if not (ADDON_DIR / name).exists():
                print(f"WARN  ForeverSynthwave.toc lists {name}, which does not exist")

    print(f"\n{len(paths) - failures}/{len(paths)} files parse as Lua 5.1")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
