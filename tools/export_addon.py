#!/usr/bin/env python3
"""Export the curated runtime from a package prepared by the private source gates."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import stat
import subprocess
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile

PACKAGE_ROOT = "ForeverSynthwave"
TOC_NAME = "ForeverSynthwave.toc"
MANIFEST_NAME = ".stuwave-export.json"
PUBLIC_TITLE = "Forever STUwave"
PUBLIC_NOTES = (
    "Alpha neon UI for the Forever client, "
    "with synthwave frames, bars, chat, and HUD styling."
)
HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
PRIVATE_COMMENT = re.compile(rb"\badze\b|\b01[A-Z0-9]{8,24}\b", re.IGNORECASE)
LONG_BRACKET = re.compile(rb"\[(=*)\[")
COMMENT_BLOCKS = {
    "CastBars.lua": [(
        b"-- Forever Synthwave: Cast Bars (",
        b"-- are plain non-secure frames, so no combat defer is needed.",
        (
            b"-- Forever Synthwave: Player and Target Cast Bars",
            b"--",
            b"-- PLAYER and TARGET cast bars use the shared chevron engine (ChevronCastBar.lua):",
            b"-- two chamfered bars of the same width, target above player, 18 units apart on a",
            b"-- fixed seat (see STACK PLACEMENT). The ForeverBridge pixel bridge lives in the",
            b"-- data bar, so nothing here reads it. PlayerCastingBarFrame is the player cast",
            b"-- bar on this client (CastingBarFrame is nil); TargetFrameSpellBar is the target",
            b"-- bar. Both Blizzard bars are dimmed with DimBlizzardFrame. Both custom bars are",
            b"-- plain non-secure frames, so no combat defer is needed.",
        ),
    )],
    "ChatCore.lua": [(
        b"-- Interim default: force the comms tab active at login when chatSelectedTab",
        b"-- persisted-order/selection feature this stands in for).",
        (
            b"-- Interim default: force the comms tab active at login when chatSelectedTab",
            b"-- is unset. The Forever beta client does not restore per-character",
            b"-- SavedVariables across /reload, so this default accompanies ChatTabs.lua's",
            b"-- comms-first pill ordering. Once persistence works, a saved tab selection",
            b"-- should take precedence over the default.",
        ),
    )],
    "ChatTabs.lua": [
        (
            b"-- A real drag-to-reorder feature is deferred",
            b"-- by a persisted user order, and this function goes away.",
            (
                b"-- Drag-to-reorder is deferred because the Forever beta client does not",
                b"-- restore per-character SavedVariables across /reload. Keep comms first",
                b"-- until a user-selected dock order can persist. Replace this default",
                b"-- with saved user ordering when client persistence works.",
            ),
        ),
        (
            b"-- Interim hardcoded default-active-tab: force comms active at login when",
            b"-- the pendingSelectedTab block above.",
            (
                b"-- Select comms once at login when ChatCore.lua set pendingDefaultComms",
                b"-- because there was no saved tab to restore. This accompanies",
                b"-- OrderedDockedFrames' comms-first ordering while the client cannot",
                b"-- restore per-character SavedVariables across /reload. Revisit these",
                b"-- defaults when persisted order/selection works. Clear the flag now",
                b"-- so it cannot fire twice or override a later manual tab switch.",
            ),
        ),
    ],
}


def _lua_comments(contents: bytes) -> list[tuple[int, int]]:
    comments: list[tuple[int, int]] = []
    index = 0
    while index < len(contents):
        if contents[index] in (ord("'"), ord('"')):
            quote = contents[index]
            index += 1
            while index < len(contents) and contents[index] != quote:
                index += 2 if contents[index] == ord("\\") else 1
            if index >= len(contents):
                raise ValueError("Unterminated quoted Lua string")
            index += 1
            continue
        comment = contents.startswith(b"--", index)
        opening = index + 2 if comment else index
        bracket = LONG_BRACKET.match(contents, opening)
        if bracket:
            closing = b"]" + bracket[1] + b"]"
            end = contents.find(closing, bracket.end())
            if end < 0:
                raise ValueError("Unterminated Lua long string or comment")
            end += len(closing)
            if comment:
                comments.append((index, end))
            index = end
        elif comment:
            end = index + 2
            while end < len(contents) and contents[end] not in (10, 13):
                end += 1
            comments.append((index, end))
            index = end
        else:
            index += 1
    return comments


def _curate_lua(name: str, contents: bytes) -> bytes:
    comments = _lua_comments(contents)
    replacements: dict[int, bytes] = {}
    for anchor, final_line, public_lines in COMMENT_BLOCKS.get(name, []):
        starts = [i for i, (start, end) in enumerate(comments)
                  if contents[start:end].startswith(anchor)]
        if len(starts) > 1:
            raise ValueError(f"Duplicate curated comment anchor in {name}")
        for first in starts:
            last = first
            while last < min(first + 12, len(comments)):
                start, end = comments[last]
                line_start = max(contents.rfind(b"\n", 0, start),
                                 contents.rfind(b"\r", 0, start)) + 1
                if contents[line_start:start].strip(b" \t"):
                    raise ValueError(f"Curated comment is not a standalone line in {name}")
                if last > first:
                    gap = contents[comments[last - 1][1]:start]
                    if not re.fullmatch(rb"(?:\r\n|\n\r|\r|\n)[ \t]*", gap):
                        raise ValueError(f"Curated comment block is interrupted in {name}")
                if contents[start:end] == final_line:
                    break
                last += 1
            else:
                raise ValueError(f"Curated comment block changed in {name}")
            if len(public_lines) > last - first + 1:
                raise ValueError(f"Curated comment would change Lua line counts in {name}")
            for offset, record in enumerate(range(first, last + 1)):
                replacements[record] = public_lines[offset] if offset < len(public_lines) else b"--"
    for index, (start, end) in enumerate(comments):
        comment = replacements.get(index, contents[start:end])
        if name == "HudText.lua" and comment.startswith((
            b"-- Zone / subzone / PvP status text",
            b"-- Errors / raid warning / boss banner",
            b"-- Combat text (",
        )):
            comment = re.sub(rb"[ \t]+\(adze[ \t]+01[A-Z0-9]{8,24}\)", b"", comment)
        elif name == "IssueReporter.lua" and comment.startswith(
            b"-- the boot-counter probe above;"
        ):
            comment = re.sub(rb";[ \t]+adze[ \t]+01[A-Z0-9]{8,24}(?=\))", b"", comment)
        if PRIVATE_COMMENT.search(comment):
            raise ValueError(f"Unhandled private reference in a Lua comment in {name}")
        if comment != contents[start:end]:
            replacements[index] = comment
    output: list[bytes] = []
    previous = 0
    for index, (start, end) in enumerate(comments):
        output.extend((contents[previous:start], replacements.get(index, contents[start:end])))
        previous = end
    output.append(contents[previous:])
    return b"".join(output)


def _safe_parts(name: str) -> tuple[str, ...]:
    if not name or "\\" in name or ":" in name or any(ord(c) < 32 for c in name):
        raise ValueError(f"Unsafe relative path: {name!r}")
    parts = tuple(name.split("/"))
    if any(part in ("", ".", "..") or part.endswith((" ", ".")) for part in parts):
        raise ValueError(f"Unsafe relative path: {name!r}")
    return parts


def _is_runtime(name: str) -> bool:
    parts = _safe_parts(name)
    if len(parts) == 1:
        return name == TOC_NAME or (not name.startswith(".") and name.endswith(".lua"))
    if len(parts) != 2 or parts[1].startswith("."):
        return False
    if parts[0] == "media":
        return parts[1].endswith(".tga")
    if parts[0] == "fonts":
        return parts[1].endswith(".ttf") or bool(
            re.fullmatch(r"(?:OFL|LICENSE|COPYING)(?:[-_][^/]+)?\.txt", parts[1], re.IGNORECASE)
        )
    return False


def _rewrite_toc(contents: bytes, payload: dict[str, bytes]) -> bytes:
    text = contents.decode("utf-8")
    metadata: dict[str, str] = {}
    entries: list[str] = []
    output: list[str] = []
    required = {"Interface", "Title", "Notes", "Version", "SavedVariables"}
    for index, line in enumerate(text.splitlines(keepends=True)):
        stripped = line.strip()
        if index == 0:
            stripped = stripped.removeprefix("\ufeff")
        header = re.fullmatch(r"##\s*([^:]+):\s*(.*)", stripped)
        if header:
            key, value = header.groups()
            key = key.strip()
            if key in required:
                if key in metadata or not value.strip():
                    raise ValueError(f"Invalid or duplicate TOC metadata: {key}")
                metadata[key] = value
            if key in ("Title", "Notes"):
                replacement = PUBLIC_TITLE if key == "Title" else PUBLIC_NOTES
                line = re.sub(
                    r"(##[ \t]*[^:]+:[ \t]*)[^\r\n]*",
                    lambda match: f"{match[1]}{replacement}",
                    line,
                    count=1,
                )
        elif stripped.startswith("#") and not stripped.startswith("##"):
            continue
        elif stripped and not stripped.startswith("#"):
            entry = stripped.replace("\\", "/")
            _safe_parts(entry)
            if entry not in payload or entry == TOC_NAME:
                raise ValueError(f"TOC load entry is absent from the curated payload: {entry}")
            if entry in entries:
                raise ValueError(f"Duplicate TOC load entry: {entry}")
            entries.append(entry)
        output.append(line)
    missing = sorted(required - metadata.keys())
    if missing or not entries:
        raise ValueError(f"Incomplete TOC: missing metadata {missing} or no load entries")
    return "".join(output).encode("utf-8")


def _read_payload(archive: Path) -> tuple[dict[str, bytes], str]:
    _safe_parts(archive.name)
    archive_bytes = archive.read_bytes()
    payload: dict[str, bytes] = {}
    seen: set[str] = set()
    with ZipFile(io.BytesIO(archive_bytes)) as zipped:
        for member in zipped.infolist():
            name = member.orig_filename
            directory = member.is_dir()
            parts = _safe_parts(name[:-1] if directory else name)
            if parts[0] != PACKAGE_ROOT or (len(parts) == 1 and not directory):
                raise ValueError(f"Archive member is outside {PACKAGE_ROOT}/: {name}")
            collision_key = "/".join(parts).casefold()
            if collision_key in seen:
                raise ValueError(f"Duplicate archive member: {name}")
            seen.add(collision_key)
            file_type = stat.S_IFMT(member.external_attr >> 16)
            allowed_types = (0, stat.S_IFDIR) if directory else (0, stat.S_IFREG)
            if file_type not in allowed_types:
                raise ValueError(f"Archive member is not a regular file or directory: {name}")
            if not directory:
                relative = "/".join(parts[1:])
                if _is_runtime(relative):
                    contents = zipped.read(member)
                    payload[relative] = (
                        _curate_lua(relative, contents) if relative.endswith(".lua") else contents
                    )
    if TOC_NAME not in payload:
        raise ValueError(f"Archive is missing {TOC_NAME}")
    payload[TOC_NAME] = _rewrite_toc(payload[TOC_NAME], payload)
    return payload, hashlib.sha256(archive_bytes).hexdigest()


def _repository_root(destination: Path) -> Path:
    root = destination.resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"Destination is not a directory: {destination}")
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or Path(result.stdout.strip()).resolve() != root:
        raise ValueError(f"Destination must be an existing Git repository root: {destination}")
    return root


def _preflight_path(root: Path, name: str) -> Path:
    parts = _safe_parts(name)
    target = root
    for index, part in enumerate(parts):
        target /= part
        if target.is_symlink():
            raise ValueError(f"Destination path contains a symlink: {name}")
        if target.exists():
            expected_directory = index < len(parts) - 1
            if expected_directory and not target.is_dir():
                raise ValueError(f"Destination parent is not a directory: {name}")
            if not expected_directory and not target.is_file():
                raise ValueError(f"Destination target is not a regular file: {name}")
            if not expected_directory and target.stat().st_nlink > 1:
                raise ValueError(f"Destination target has multiple hard links: {name}")
    return target


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate manifest key: {key}")
        result[key] = value
    return result


def _read_manifest(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    manifest = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(manifest, dict) or set(manifest) != {"version", "archive", "files"}:
        raise ValueError("Invalid export manifest structure")
    if type(manifest["version"]) is not int or manifest["version"] != 1:
        raise ValueError("Unsupported export manifest version")
    archive = manifest["archive"]
    files = manifest["files"]
    if not isinstance(archive, dict) or set(archive) != {"name", "sha256"}:
        raise ValueError("Invalid archive metadata in export manifest")
    if (
        not isinstance(archive["name"], str)
        or len(_safe_parts(archive["name"])) != 1
        or not isinstance(archive["sha256"], str)
        or not HASH_PATTERN.fullmatch(archive["sha256"])
        or not isinstance(files, dict)
        or TOC_NAME not in files
    ):
        raise ValueError("Invalid export manifest metadata or managed files")
    managed: dict[str, str] = {}
    seen: set[str] = set()
    for name, digest in files.items():
        if (
            not isinstance(name, str)
            or not _is_runtime(name)
            or not isinstance(digest, str)
            or not HASH_PATTERN.fullmatch(digest)
            or name.casefold() in seen
        ):
            raise ValueError(f"Invalid managed runtime file in export manifest: {name!r}")
        seen.add(name.casefold())
        managed[name] = digest
    return managed


def export_addon(archive: Path, destination: Path) -> tuple[int, int]:
    """Mirror curated package bytes after validating the complete export operation."""
    root = _repository_root(destination)
    payload, archive_hash = _read_payload(archive)
    manifest_path = _preflight_path(root, MANIFEST_NAME)
    previous = _read_manifest(manifest_path)
    obsolete = sorted(previous.keys() - payload.keys())
    targets = {name: _preflight_path(root, name) for name in payload.keys() | previous.keys()}
    for name in obsolete:
        target = targets[name]
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != previous[name]:
            raise ValueError(f"Obsolete managed file changed since its export: {name}")
    manifest = {
        "version": 1,
        "archive": {"name": archive.name, "sha256": archive_hash},
        "files": {name: hashlib.sha256(contents).hexdigest() for name, contents in payload.items()},
    }
    manifest_bytes = f"{json.dumps(manifest, indent=2, sort_keys=True)}\n".encode()
    for name, contents in sorted(payload.items()):
        target = targets[name]
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_bytes() != contents:
            target.write_bytes(contents)
    removed = 0
    for name in obsolete:
        if targets[name].exists():
            targets[name].unlink()
            removed += 1
    if not manifest_path.exists() or manifest_path.read_bytes() != manifest_bytes:
        manifest_path.write_bytes(manifest_bytes)
    return len(payload), removed


def main() -> int:
    """Run the export command and report concise success or validation errors."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    try:
        exported, removed = export_addon(args.archive, args.destination)
    except (OSError, ValueError, BadZipFile, RuntimeError, NotImplementedError) as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
        return 1
    print(f"Exported {exported} runtime files; removed {removed} obsolete managed files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
