#!/usr/bin/env python3
"""Prepare a staged copy of the runtime addon for installing or packaging.

Usage: stage_runtime.py STAGE_DIR

STAGE_DIR is a scratch copy of the runtime files (never the source tree). Every .lua file in it is
rewritten without comments, every .toc without `#` comment lines, and every .xml without XML comments.
Each removal keeps every newline, so line numbers in the client's error reports still match the source.

Lua is handled by a small lexer, not a regex: `--`, `--[[ ]]` and `--[==[ ]==]` comments are removed, and
a `--` inside a quoted or long string is left alone. Each rewritten .lua file is then proven equivalent:
the compiled form of the original and of the rewrite (instructions, constants, nested functions) must be
identical (LuaJIT through lupa, the same engine as tools/parse-gate.py), otherwise this exits non-zero and nothing should be installed.

Finally the staged text is scanned: string literals (and .toc / .xml text) for developer-tool vocabulary,
and identifiers for the same list minus "pixel" (PixelUtil is a Blizzard API) and the secret-value phrase
(issecretvalue is one too). File names are scanned as well. Words such as probe, recon and monitor, and the
phrase "test strip", are matched by whole word (camelCase and underscores split), so "reconcile" passes.
Any hit is printed with file and line and the exit status is non-zero.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Word-ish patterns, matched case-insensitively.
STRING_TERMS = {
    "fsdev": r"fsdev",
    "harness": r"harness",
    "bot": r"(?<![a-z])bots?(?![a-z])",
    "pixel": r"pixel",
    "bridge": r"bridge",
    "beacon": r"beacon",
    "python": r"python",
    "automation": r"automation|automated",
    "typed by": r"typed\s+by",
}
CODE_TERMS = {k: v for k, v in STRING_TERMS.items() if k != "pixel"}

# Developer-instrumentation vocabulary matched by WORD, not substring: text (and identifiers) are split
# into words on punctuation, digits and camelCase humps, so "FSProbe", "probe_run" and "RunPetProbe" hit
# "probe" while "reconcile", "improbable" and "issecretvalue" (a Blizzard API) do not.
WORD_TERMS = {
    "probe": {"probe", "probes", "probed", "probing", "fsprobe"},
    "recon": {"recon", "fsrecon"},
    "monitor": {"monitor", "monitors", "monitored", "monitoring"},
}
# Phrases. Text is matched with a separator between the words ("secret-value", "Secret value",
# "test_strip"); a camelCase run such as the Blizzard method name HasSecretValues is not text. An
# identifier is checked for the camelCase form of "test strip" only (issecretvalue and friends are
# Blizzard APIs and stay legal).
TEXT_PHRASES = {
    "secret-value": r"(?<![a-z])secret[\s_-]+values?(?![a-z])",
    "test strip": r"(?<![a-z])test[\s_-]+strip(?![a-z])",
}

_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")
_LONG_OPEN = re.compile(r"\[(=*)\[")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class StripError(Exception):
    pass


def _keep_newlines(text: str) -> str:
    return "".join(ch for ch in text if ch in "\r\n")


def strip_lua(src: str) -> tuple[str, list[tuple[int, str]], list[tuple[int, str]]]:
    """Return (stripped source, [(line, string literal text)], [(line, identifier)])."""
    out: list[str] = []
    strings: list[tuple[int, str]] = []
    idents: list[tuple[int, str]] = []
    n = len(src)
    i = 0
    line = 1

    def emit(text: str) -> None:
        nonlocal line
        out.append(text)
        line += text.count("\n")

    while i < n:
        c = src[i]
        if c == "-" and src.startswith("--", i):
            m = _LONG_OPEN.match(src, i + 2)
            if m:
                close = "]" + "=" * len(m.group(1)) + "]"
                j = src.find(close, m.end())
                if j < 0:
                    raise StripError(f"line {line}: unterminated long comment")
                end = j + len(close)
                body = src[i:end]
                nl = _keep_newlines(body)
                if nl:
                    emit(nl)
                else:
                    prev = out[-1][-1:] if out else ""
                    nxt = src[end:end + 1]
                    if prev and nxt and not prev.isspace() and not nxt.isspace():
                        emit(" ")
                i = end
                continue
            j = i
            while j < n and src[j] not in "\r\n":
                j += 1
            # drop the whitespace the comment was trailing
            while out and out[-1] in (" ", "\t"):
                out.pop()
            i = j
            continue
        if c == "'" or c == '"':
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == c:
                    break
                if src[j] in "\r\n":
                    raise StripError(f"line {line}: unterminated string")
                j += 1
            else:
                raise StripError(f"line {line}: unterminated string")
            lit = src[i:j + 1]
            strings.append((line, lit[1:-1]))
            emit(lit)
            i = j + 1
            continue
        if c == "[":
            m = _LONG_OPEN.match(src, i)
            if m:
                close = "]" + "=" * len(m.group(1)) + "]"
                j = src.find(close, m.end())
                if j < 0:
                    raise StripError(f"line {line}: unterminated long string")
                lit = src[i:j + len(close)]
                strings.append((line, lit[m.end() - i:-len(close)]))
                emit(lit)
                i = j + len(close)
                continue
        m = _IDENT.match(src, i)
        if m:
            idents.append((line, m.group(0)))
            emit(m.group(0))
            i = m.end()
            continue
        emit(c)
        i += 1
    return "".join(out), strings, idents


def strip_toc(text: str) -> str:
    kept = []
    for raw in text.splitlines(keepends=True):
        body = raw.strip()
        if body.startswith("#") and not body.startswith("##"):
            kept.append(_keep_newlines(raw))
        else:
            kept.append(raw)
    return "".join(kept)


def strip_xml(text: str) -> str:
    return re.sub(r"<!--.*?-->", lambda m: _keep_newlines(m.group(0)), text, flags=re.S)


_CANON = r"""
function(s)
  local util = require("jit.util")
  local out = {}
  local function show(v)
    return type(v) == "table" and "T" or type(v) .. ":" .. tostring(v)
  end
  -- Table-constant templates list their keys in an order that varies between runs, so sort them.
  local function ser(t)
    local keys = {}
    for k in pairs(t) do keys[#keys + 1] = show(k) .. "=" .. show(t[k]) end
    table.sort(keys)
    return "{" .. table.concat(keys, ",") .. "}"
  end
  local function canon(p)
    local info = util.funcinfo(p)
    out[#out + 1] = ("P %d %d %d %d %d %s"):format(info.params, info.stackslots, info.nconsts,
      info.gcconsts, info.bytecodes, tostring(info.isvararg))
    for i = 1, info.bytecodes do out[#out + 1] = tostring((util.funcbc(p, i))) end
    for i = 0, info.nconsts - 1 do out[#out + 1] = "N" .. tostring(util.funck(p, i)) end
    for i = 1, info.gcconsts do
      local k = util.funck(p, -i)
      if type(k) == "proto" then canon(k)
      elseif type(k) == "table" then out[#out + 1] = "T" .. ser(k)
      else out[#out + 1] = "G" .. show(k) end
    end
  end
  local fn, err = loadstring(s, "=x")
  if not fn then return nil, err end
  canon(fn)
  return table.concat(out, "\n")
end
"""


def _runtime():
    """Returns f(source bytes) -> canonical bytecode text, or (None, error).

    The text lists every function's instructions, numeric constants, string constants and table
    templates (keys sorted), so two sources compile to the same text exactly when LuaJIT would run
    them identically. Line numbers and names of locals are not part of it. (string.dump is not used:
    its table-constant order is not repeatable from one dump to the next.)
    """
    from lupa.luajit21 import LuaRuntime

    return LuaRuntime(encoding=None, register_eval=False).eval(_CANON)


def word_hits(text: str, kind: str) -> list[str]:
    """Names of the WORD_TERMS / phrases found in text (see the tables above)."""
    words = [w.lower() for w in _WORD.findall(text)]
    found = [name for name, forms in WORD_TERMS.items() if forms.intersection(words)]
    if kind == "identifier":
        if any(a == "test" and b == "strip" for a, b in zip(words, words[1:])):
            found.append("test strip")
    else:
        found += [name for name, pattern in TEXT_PHRASES.items() if re.search(pattern, text, re.I)]
    return found


def scan(rel: str, kind: str, items: list[tuple[int, str]], terms: dict[str, str]) -> list[str]:
    hits = []
    for line, text in items:
        for name in word_hits(text, kind):
            shown = text if len(text) <= 90 else text[:87] + "..."
            hits.append(f"{rel}:{line}: {kind} matches '{name}': {shown!r}")
        for name, pattern in terms.items():
            if kind == "identifier" and name == "bot" and text.isupper():
                continue  # BOT / FILL_BOT are "bottom"
            if re.search(pattern, text, re.I):
                shown = text if len(text) <= 90 else text[:87] + "..."
                hits.append(f"{rel}:{line}: {kind} matches '{name}': {shown!r}")
    return hits


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    stage = Path(argv[1])
    if not stage.is_dir():
        print(f"ERROR: not a directory: {stage}", file=sys.stderr)
        return 2
    dump = _runtime()
    failures: list[str] = []
    hits: list[str] = []
    luas = tocs = xmls = 0
    removed = 0

    for path in sorted(stage.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(stage).as_posix()
        suffix = path.suffix.lower()
        for part in rel.rsplit(".", 1)[0].split("/"):
            for name in word_hits(part, "file name"):
                hits.append(f"{rel}: file name matches '{name}'")
        if suffix == ".lua":
            original = path.read_bytes().decode("latin-1")
            try:
                stripped, strings, idents = strip_lua(original)
            except StripError as err:
                failures.append(f"{rel}: {err}")
                continue
            a = dump(original.encode("latin-1"))
            b = dump(stripped.encode("latin-1"))
            if isinstance(a, tuple):
                failures.append(f"{rel}: original does not compile: {a[1]}")
                continue
            if isinstance(b, tuple):
                failures.append(f"{rel}: stripped copy does not compile: {b[1]}")
                continue
            if a != b:
                failures.append(f"{rel}: stripped bytecode differs from the original")
                continue
            if stripped.count("\n") != original.count("\n"):
                failures.append(f"{rel}: newline count changed")
                continue
            removed += len(original) - len(stripped)
            path.write_bytes(stripped.encode("latin-1"))
            luas += 1
            hits += scan(rel, "string", strings, STRING_TERMS)
            hits += scan(rel, "identifier", idents, CODE_TERMS)
        elif suffix == ".toc":
            original = path.read_bytes().decode("latin-1")
            stripped = strip_toc(original)
            removed += len(original) - len(stripped)
            path.write_bytes(stripped.encode("latin-1"))
            tocs += 1
            hits += scan(rel, "text", [(n, t) for n, t in enumerate(stripped.splitlines(), 1)], STRING_TERMS)
        elif suffix == ".xml":
            original = path.read_bytes().decode("latin-1")
            stripped = strip_xml(original)
            try:
                same = ET.tostring(ET.fromstring(original)) == ET.tostring(ET.fromstring(stripped))
            except ET.ParseError as err:
                failures.append(f"{rel}: {err}")
                continue
            if not same:
                failures.append(f"{rel}: stripped XML differs from the original")
                continue
            removed += len(original) - len(stripped)
            path.write_bytes(stripped.encode("latin-1"))
            xmls += 1
            hits += scan(rel, "text", [(n, t) for n, t in enumerate(stripped.splitlines(), 1)], STRING_TERMS)

    print(f"strip: {luas} lua, {tocs} toc, {xmls} xml rewritten; {removed} bytes of comments removed")
    if failures:
        print("strip: VERIFICATION FAILED", file=sys.stderr)
        for f in failures:
            print("  " + f, file=sys.stderr)
        return 1
    print(f"strip: {luas} lua files verified (stripped bytecode identical to the original)")
    if hits:
        print(f"scan: {len(hits)} hit(s) in the staged text", file=sys.stderr)
        for h in hits:
            print("  " + h, file=sys.stderr)
        return 1
    print("scan: clean (no flagged terms in strings, identifiers, .toc or .xml)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
