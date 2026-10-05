#!/usr/bin/env python3
"""Static checks for the ForeverSynthwave addon, aimed at the bug classes that
have actually cost this project time. Complements `parse-gate.py`: that one
answers "does it parse", this one answers "does it parse and still mean what
you think".

luacheck is the conventional tool, but it is a Lua rock and this box has no
Lua, no luarocks, and an antivirus that fights installers. This needs neither:
it asks LuaJIT (already vendored via lupa for the parse gate) what the compiler
actually resolved.

HOW IT WORKS
    Every name in Lua resolves at COMPILE time to a local, an upvalue, or a
    global. We compile each file with LuaJIT and walk the bytecode of every
    prototype, recording each GGET (global read) and GSET (global write) with
    its line. Because the compiler did the scope analysis, there is no
    guesswork: if a name shows up here, it really is a global at runtime.

    Opcode numbers are calibrated at startup against this exact LuaJIT build
    rather than hardcoded, so a lupa upgrade cannot silently break the checks.

CHECK 1 -- use-before-local-declaration  (HIGH: silently dead code)
    A closure binds names when it is COMPILED. A function written ABOVE a later
    `local function NAME` compiles its reference to NAME as a global, and that
    binding is permanent: nil at runtime no matter what order things run in.
    The file parses, the addon loads, the feature is just silently dead.

    This bit the project twice in one night (`ReseatBags` in MicroBars.lua,
    `xAtAddonLoaded` in IssueReporter.lua, 2026-09-20/21), which is why it is
    check number one. A global read whose name is ALSO declared `local`
    somewhere in the same file is this bug.

    The correct pattern -- forward-declare `local Helper` first, assign later --
    produces an upvalue, not a global, so it is never flagged.

CHECK 2 -- globals that do not exist on this client  (MEDIUM: silent no-op)
    Cross-references every global READ against a dump of all globals taken from
    the live 16001 client (api-dump-16001/globals.txt). A read of something
    absent from that list is a typo, or an API this client does not have: the
    `SpellBookFrame` / `ActionButton_Update` failure mode where a hook silently
    no-ops because the global is nil.

CHECK 3 -- accidental globals  (LOW: leaks into the shared table)
    A global WRITE is almost always a missing `local`.

Usage:
    tools/.venv-lua/Scripts/python.exe addons/lua-lint.py             # whole addon
    tools/.venv-lua/Scripts/python.exe addons/lua-lint.py FILE...
    tools/.venv-lua/Scripts/python.exe addons/lua-lint.py --self-test
    ... --only=1,2      restrict to given check numbers
    ... --fail-on high  (or =high) exit non-zero only for HIGH findings (the deploy gate
                        uses this so medium/low noise never blocks a deploy)

check 2 reads a dump of client globals: $FS_GLOBALS_DUMP if set, else the first
existing of the Fedora reference copy and the Windows path (see
GLOBALS_DUMP_CANDIDATES). With none present, check 2 is skipped with a note.

Exit 0 = clean. Non-zero = number of findings, capped at 255 (HIGH only under
--fail-on high; also accepts --fail-on=high).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaRuntime
except ImportError:
    sys.exit(
        "lupa is missing. Create the tooling venv:\n"
        '  "C:/Python312/python.exe" -m venv tools/.venv-lua\n'
        "  UV_LINK_MODE=copy uv pip install --python tools/.venv-lua/Scripts/python.exe lupa\n"
        "Then run this with tools/.venv-lua/Scripts/python.exe"
    )

ADDON_DIR = Path(__file__).resolve().parent.parent / "addon" / "ForeverSynthwave"
# Dump of every global on the live 16001 client, used by check 2. Resolution
# order: $FS_GLOBALS_DUMP (explicit override; if set it is the only candidate),
# then the first existing path below (Fedora reference copy, then Windows).
GLOBALS_DUMP_CANDIDATES = [Path(__file__).resolve().parent.parent / "reference" / "globals.txt"]


def resolve_globals_dump() -> Path | None:
    override = os.environ.get("FS_GLOBALS_DUMP")
    candidates = [Path(override)] if override else GLOBALS_DUMP_CANDIDATES
    return next((c for c in candidates if c.exists()), None)


KEYWORDS = {
    "and", "break", "do", "else", "elseif", "end", "false", "for", "function",
    "goto", "if", "in", "local", "nil", "not", "or", "repeat", "return",
    "then", "true", "until", "while",
}
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# Globals the addon legitimately creates or that exist only at runtime.
ADDON_OWNED = {"ForeverSynthwave", "ForeverSynthwaveDB", "FS", "AAAFSRecon"}

# Global WRITES that are intentional, not a missing `local`:
#   SLASH_*        WoW's slash-command API only reads these from _G
#   BINDING_*      likewise for key bindings
#   GetMinimapShape  a community contract other addons call on us
#   ForeverSynthwave*  our own diagnostic tables, deliberately global so they
#                      can be read with /dump in game
INTENTIONAL_GLOBAL_WRITE = re.compile(
    r"^(SLASH_[A-Z0-9_]+|BINDING_[A-Z0-9_]+|ForeverSynthwave\w*|GetMinimapShape)$"
)

_LUA_EXTRACT = r"""
function(src, chunkname, OP_GET, OP_SET)
  local u = require('jit.util')
  local chunk, err = loadstring(src, chunkname)
  if not chunk then return nil, err end
  local res, seen = {}, {}
  local function walk(fn)
    if seen[tostring(fn)] then return end
    seen[tostring(fn)] = true
    local pc = 1
    while true do
      local ok, ins = pcall(u.funcbc, fn, pc)
      if not ok or ins == nil then break end
      local op = bit.band(ins, 0xff)
      if op == OP_GET or op == OP_SET then
        local name = u.funck(fn, -(bit.rshift(ins, 16) + 1))
        local info = u.funcinfo(fn, pc)
        res[#res+1] = (op == OP_GET and 'R' or 'W')
                      .. '\t' .. tostring(name)
                      .. '\t' .. tostring(info and info.currentline or 0)
      end
      pc = pc + 1
    end
    local i = -1
    while true do
      local ok, v = pcall(u.funck, fn, i)
      if not ok or v == nil then break end
      if type(v) == 'proto' then walk(v) end
      i = i - 1
    end
  end
  walk(chunk)
  return table.concat(res, '\n'), nil
end
"""

_LUA_CALIBRATE = r"""
function()
  local u = require('jit.util')
  local function first_op(src)
    local f = assert(loadstring(src))
    local pc = 1
    while true do
      local ok, ins = pcall(u.funcbc, f, pc)
      if not ok or ins == nil then return nil end
      local op = bit.band(ins, 0xff)
      local d  = bit.rshift(ins, 16)
      local ok2, k = pcall(u.funck, f, -(d + 1))
      if ok2 and k == 'ZZ_PROBE_NAME' then return op end
      pc = pc + 1
    end
  end
  return first_op('return ZZ_PROBE_NAME'), first_op('ZZ_PROBE_NAME = 1')
end
"""


class LuaGlobals:
    def __init__(self) -> None:
        self.rt = LuaRuntime()
        op_get, op_set = self.rt.eval(_LUA_CALIBRATE)()
        if not op_get or not op_set or op_get == op_set:
            raise SystemExit(
                f"could not calibrate GGET/GSET opcodes (got {op_get}/{op_set}). "
                "This LuaJIT build may differ; the checks would be meaningless."
            )
        self.op_get, self.op_set = int(op_get), int(op_set)
        self._extract = self.rt.eval(_LUA_EXTRACT)

    def globals_in(self, src: str, chunkname: str):
        """-> (list of (kind, name, line), error_or_None)."""
        out, err = self._extract(src, "@" + chunkname, self.op_get, self.op_set)
        if err:
            return [], str(err)
        rows = []
        for line in (out or "").split("\n"):
            if not line:
                continue
            kind, name, ln = line.split("\t")
            rows.append((kind, name, int(ln)))
        return rows, None


def blank_comments_and_strings(src: str) -> str:
    """Comments and string literals -> spaces, preserving offsets and lines.
    Only used to find `local` declarations for cross-referencing."""
    out = list(src)
    i, n = 0, len(src)

    def blank(a: int, b: int) -> None:
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    def long_bracket(start: int):
        j, eq = start + 1, 0
        while j < n and src[j] == "=":
            eq += 1
            j += 1
        if j >= n or src[j] != "[":
            return None
        close = "]" + "=" * eq + "]"
        k = src.find(close, j + 1)
        return n if k == -1 else k + len(close)

    while i < n:
        c = src[i]
        if src.startswith("--", i):
            if i + 2 < n and src[i + 2] == "[":
                end = long_bracket(i + 2)
                if end is not None:
                    blank(i, end)
                    i = end
                    continue
            end = src.find("\n", i)
            end = n if end == -1 else end
            blank(i, end)
            i = end
            continue
        if c in "\"'":
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == c or src[j] == "\n":
                    j += 1
                    break
                j += 1
            blank(i, j)
            i = j
            continue
        if c == "[":
            end = long_bracket(i)
            if end is not None:
                blank(i, end)
                i = end
                continue
        i += 1
    return "".join(out)


def local_decls(code: str) -> dict[str, int]:
    """name -> line of its first `local` declaration."""
    decls: dict[str, int] = {}

    def line_at(pos: int) -> int:
        return code.count("\n", 0, pos) + 1

    for m in re.finditer(r"\blocal\s+(function\s+)?", code):
        j = m.end()
        if m.group(1):
            im = IDENT.match(code, j)
            if im and im.group() not in KEYWORDS:
                decls.setdefault(im.group(), line_at(im.start()))
            continue
        while j < len(code):
            im = IDENT.match(code, j)
            if not im or im.group() in KEYWORDS:
                break
            decls.setdefault(im.group(), line_at(im.start()))
            j = im.end()
            sep = re.match(r"\s*,\s*", code[j:])
            if not sep:
                break
            j += sep.end()
    return decls


def guarded_names(code: str) -> set[str]:
    """Names the file demonstrably guards before use.

    This codebase's rule is feature-detect at the call site, so a read of a
    global that does not exist on this client is CORRECT when it is guarded --
    it is the fallback arm for another client. Only a wholly unguarded read is
    a finding. Recognised guards:

        type(NAME) == ...        explicit feature detection
        pcall(NAME, ...)         call that is allowed to fail
        if NAME then / NAME and  short-circuit nil check
        HideIfExists(NAME)       the addon's own nil-safe helpers
    """
    guarded = set()
    for pat in (
        r"\btype\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",
        r"\bpcall\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)",
        r"\bif\s+([A-Za-z_][A-Za-z0-9_]*)\s+(?:then|and)\b",
        r"\b([A-Za-z_][A-Za-z0-9_]*)\s+and\s+\1\b",
        r"\bHide(?:IfExists|BlizzardFrame)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",
    ):
        guarded |= {m.group(1) for m in re.finditer(pat, code)}
    return guarded


def load_client_globals(dump: Path | None) -> set[str] | None:
    if dump is None:
        return None
    names = set()
    for line in dump.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            names.add(line.split("\t", 1)[0].strip())
    return names


SELF_TEST_CASES = [
    ("use-before-local is caught", """
local function Outer() return Helper() end
local function Helper() return 1 end
""", 1),
    ("correct order is clean", """
local function Helper() return 1 end
local function Outer() return Helper() end
""", 0),
    ("forward declaration is clean", """
local Helper
local function Outer() return Helper() end
Helper = function() return 1 end
""", 0),
    ("name in a comment or string does not count", """
-- Helper() here is a comment
local s = "Helper()"
local function Helper() return 1 end
local function Use() return Helper() end
""", 0),
    ("a field access is not a global", """
local t = {}
local function Use() return t.Helper end
local function Helper() return 1 end
""", 0),
    ("a parameter sharing a later local's name is clean", """
local function Paint(color) return color end
local function Other() local color = 1 return color end
""", 0),
]


def self_test(lg: LuaGlobals) -> int:
    print(f"calibrated opcodes: GGET={lg.op_get} GSET={lg.op_set}\n")
    failures = 0
    for i, (label, src, expected) in enumerate(SELF_TEST_CASES, 1):
        rows, err = lg.globals_in(src, f"case{i}.lua")
        if err:
            print(f"  case {i} ({label}): FAIL - did not compile: {err}")
            failures += 1
            continue
        decls = local_decls(blank_comments_and_strings(src))
        hits = [(n, ln) for k, n, ln in rows if k == "R" and n in decls]
        ok = len(hits) == expected
        print(f"  case {i}: {'ok  ' if ok else 'FAIL'} {label} "
              f"(expected {expected}, got {len(hits)})")
        for n, ln in hits:
            print(f"        line {ln}: {n}")
        failures += 0 if ok else 1
    print(f"\nself-test: {len(SELF_TEST_CASES) - failures}/{len(SELF_TEST_CASES)} passed")
    return failures


def main() -> int:
    argv = list(sys.argv[1:])
    only = {1, 2, 3}
    fail_on = "any"
    for a in list(argv):
        if a.startswith("--only="):
            only = {int(x) for x in a.split("=", 1)[1].split(",")}
            argv.remove(a)
    for a in list(argv):
        if a.startswith("--fail-on="):
            fail_on = a.split("=", 1)[1]
            argv.remove(a)
            break
    else:
        if "--fail-on" in argv:
            i = argv.index("--fail-on")
            fail_on = argv[i + 1] if i + 1 < len(argv) else ""
            del argv[i:i + 2]
    if fail_on not in ("any", "high"):
        sys.exit("--fail-on takes 'any' (default) or 'high' (--fail-on high or --fail-on=high)")

    lg = LuaGlobals()

    if "--self-test" in argv:
        return self_test(lg)

    files = [Path(a).resolve() for a in argv] or sorted(ADDON_DIR.glob("*.lua"))
    if not files:
        print(f"no .lua files under {ADDON_DIR}")
        return 1

    dump = resolve_globals_dump()
    client = load_client_globals(dump)
    if client is None and 2 in only:
        override = os.environ.get("FS_GLOBALS_DUMP")
        where = (f"FS_GLOBALS_DUMP points at a missing file: {override}" if override else
                 f"set FS_GLOBALS_DUMP, or place it at {GLOBALS_DUMP_CANDIDATES[0]}")
        print(f"note: no client globals dump found ({where}); skipping check 2\n")

    # First pass: every global the addon WRITES anywhere. Reading one of these
    # back is reading our own runtime state, not a missing client API, so it
    # must not be reported by check 2. (The client dump was taken without this
    # addon loaded, so none of them appear in it.)
    parsed: dict[Path, tuple[str, list, str | None]] = {}
    self_written: set[str] = set()
    for p in files:
        src = p.read_text(encoding="utf-8", errors="replace")
        rows, err = lg.globals_in(src, p.name)
        parsed[p] = (src, rows, err)
        if not err:
            self_written |= {n for k, n, _ in rows if k == "W"}

    high, med, low = [], [], []
    for p in files:
        src, rows, err = parsed[p]
        if err:
            high.append(f"{p.name}: DOES NOT COMPILE: {err}")
            continue
        code = blank_comments_and_strings(src)
        decls = local_decls(code)
        guards = guarded_names(code)

        reported: set[tuple[str, str]] = set()
        for kind, name, line in rows:
            if kind == "R" and 1 in only and name in decls:
                high.append(
                    f"{p.name}:{line}: `{name}` compiles to a GLOBAL read, but the same "
                    f"name is declared `local` at line {decls[name]}. Permanently nil. "
                    f"Move the declaration above this use, or forward-declare it."
                )
            elif kind == "R" and 2 in only and client and name not in client \
                    and name not in ADDON_OWNED and name not in decls \
                    and name not in self_written and name not in guards:
                if ("u", name) not in reported:
                    reported.add(("u", name))
                    med.append(
                        f"{p.name}:{line}: `{name}` is read as a global but is not "
                        f"present on the 16001 client, and is not guarded by a type()/pcall/nil "
                        f"check (typo, or an unguarded use of an API this client lacks)"
                    )
            elif kind == "W" and 3 in only and name not in ADDON_OWNED \
                    and not INTENTIONAL_GLOBAL_WRITE.match(name):
                if ("w", name) not in reported:
                    reported.add(("w", name))
                    low.append(f"{p.name}:{line}: writes global `{name}` (missing `local`?)")

    for label, group in (("HIGH  -- silently dead code", high),
                         ("MED   -- global absent on this client", med),
                         ("LOW   -- accidental global write", low)):
        if group:
            print(f"\n=== {label} ({len(group)}) ===")
            for f in group:
                print("  " + f)

    total = len(high) + len(med) + len(low)
    print(f"\n{len(files)} files checked: {len(high)} high, {len(med)} med, {len(low)} low")
    # Process exit codes wrap mod 256, so 256 findings would read as success.
    return min(len(high) if fail_on == "high" else total, 255)


if __name__ == "__main__":
    sys.exit(main())
