"""Verify the public addon export through its real command line."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

EXPORTER = Path(__file__).with_name("export_addon.py")
TOC = (
    "## Interface: 16001\n"
    "## Title: Forever Synthwave\n"
    "## Notes: Legacy package notes\n"
    "## Version: 0.1.0\n"
    "## SavedVariables: ForeverSynthwaveDB\n"
    "\nForeverSynthwave.lua\nDataBar.lua\n"
)
RUNTIME = {
    "ForeverSynthwave.toc": TOC.encode(),
    "ForeverSynthwave.lua": b"ForeverSynthwave = {}\n",
    "DataBar.lua": b"local addon = ForeverSynthwave\n",
    "media/panel.tga": b"synthetic TGA fixture",
    "media/retired.tga": b"obsolete texture",
    "fonts/Orbitron.ttf": b"synthetic font fixture",
    "fonts/OFL.txt": b"SIL OPEN FONT LICENSE Version 1.1\n",
}


@pytest.fixture
def package() -> dict[str, bytes]:
    return RUNTIME | {
        "libs/LibStub/LibStub.lua": b"private unused library\n",
        "tools/local_dev.py": b"private development script\n",
        "test_dev.py": b"private tests\n",
        ".env": b"PRIVATE_TOKEN=synthetic\n",
        "mockups/preview.png": b"private mockup",
        "media/preview.png": b"development image",
        "README.md": b"obsolete source README\n",
        "CLAUDE.md": b"private development instructions\n",
        "docs/old-plan.md": b"obsolete source plan\n",
    }


@pytest.fixture
def destination(tmp_path: Path) -> Path:
    repo = tmp_path / "public-repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    return repo


def _archive(tmp_path: Path, files: dict[str, bytes]) -> Path:
    archive = tmp_path / "gated-addon.zip"
    with ZipFile(archive, "w") as zipped:
        for name, contents in files.items():
            zipped.writestr(f"ForeverSynthwave/{name}", contents)
    return archive


def _export(archive: Path, destination: Path) -> subprocess.CompletedProcess[str]:
    assert EXPORTER.is_file(), f"Exporter not implemented: {EXPORTER}"
    return subprocess.run(
        [
            sys.executable, str(EXPORTER), "--archive", str(archive),
            "--destination", str(destination),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_export_curates_runtime_payload_at_repository_root(
    tmp_path: Path, destination: Path, package: dict[str, bytes],
) -> None:
    result = _export(_archive(tmp_path, package), destination)

    assert result.returncode == 0, result.stderr
    exported = _snapshot(destination)
    public_files = {name for name in exported if not name.startswith(".git/")}
    assert public_files == set(RUNTIME) | {".stuwave-export.json"}
    assert {name: exported[name] for name in RUNTIME if not name.endswith(".toc")} == {
        name: contents for name, contents in RUNTIME.items() if not name.endswith(".toc")
    }
    assert json.loads(exported[".stuwave-export.json"])


def test_export_changes_display_metadata_and_preserves_runtime_identity(
    tmp_path: Path, destination: Path, package: dict[str, bytes],
) -> None:
    result = _export(_archive(tmp_path, package), destination)

    assert result.returncode == 0, result.stderr
    lines = (destination / "ForeverSynthwave.toc").read_text(encoding="utf-8").splitlines()
    metadata = dict(line[3:].split(": ", 1) for line in lines if line.startswith("## "))
    assert metadata["Title"] == "Forever STUwave"
    assert metadata["Notes"].strip()
    assert metadata["Notes"] != "Legacy package notes"
    assert metadata["Interface"] == "16001"
    assert metadata["Version"] == "0.1.0"
    assert metadata["SavedVariables"] == "ForeverSynthwaveDB"
    assert [line for line in lines if line and not line.startswith("#")] == [
        "ForeverSynthwave.lua", "DataBar.lua",
    ]


def test_export_keeps_toc_bindings_xml_without_exporting_other_xml(
    tmp_path: Path, destination: Path, package: dict[str, bytes],
) -> None:
    bindings = (
        b'<?xml version="1.0" encoding="UTF-8"?>\r\n'
        b'<Bindings>\r\n'
        b'  <Binding name="CLICK FSSealButton1:LeftButton" '
        b'header="FOREVERSYNTHWAVE"/>\r\n'
        b'</Bindings>\r\n'
    )
    package["ForeverSynthwave.toc"] += b"Bindings.xml\n"
    package["Bindings.xml"] = bindings
    package["Preview.xml"] = b"<Ui>private preview</Ui>\n"
    package["tools/Bindings.xml"] = b"<Bindings>private tooling</Bindings>\n"
    package["mockups/Private.xml"] = b"<Ui>private mockup</Ui>\n"

    result = _export(_archive(tmp_path, package), destination)

    assert result.returncode == 0, result.stderr
    exported = _snapshot(destination)
    public_files = {name for name in exported if not name.startswith(".git/")}
    assert public_files == set(RUNTIME) | {"Bindings.xml", ".stuwave-export.json"}
    assert exported["Bindings.xml"] == bindings
    assert exported["ForeverSynthwave.lua"] == RUNTIME["ForeverSynthwave.lua"]
    lines = exported["ForeverSynthwave.toc"].decode("utf-8").splitlines()
    assert "## SavedVariables: ForeverSynthwaveDB" in lines
    assert [line for line in lines if line and not line.startswith("#")] == [
        "ForeverSynthwave.lua", "DataBar.lua", "Bindings.xml",
    ]


def test_export_curates_private_comment_rationale_without_changing_lua_strings_or_lines(
    tmp_path: Path, destination: Path, package: dict[str, bytes],
) -> None:
    private_comment = (
        b"-- Interim default: force the comms tab active at login when chatSelectedTab\r\n"
        b"-- is unset, so a persisted user choice still wins once the client's\r\n"
        b"-- SavedVariables bug is fixed. The Forever beta client never restores\r\n"
        b"-- per-character SavedVariables across a /reload (adze 01M00TEST001), so this\r\n"
        b"-- default always fires today -- Parker's interim call, companion to\r\n"
        b"-- ChatTabs.lua's comms-first pill hardcode (adze 01M00TEST002 tracks the real\r\n"
        b"-- persisted-order/selection feature this stands in for).\r\n"
    )
    prefix = (
        b"Chat = {}\r\nlocal marker = 'adze 01M00TEST001'\r\nlocal decoy = [=[\r\n"
        + private_comment
        + b"]=]\r\nChat.pendingSelectedTab = ForeverSynthwaveDB "
        b"and ForeverSynthwaveDB.chatSelectedTab\r\n"
    )
    suffix = (
        b"Chat.pendingDefaultComms = not (ForeverSynthwaveDB "
        b"and ForeverSynthwaveDB.chatSelectedTab)\r\n"
    )
    source = prefix + private_comment + suffix
    package["ChatCore.lua"] = source
    package["ForeverSynthwave.toc"] += b"ChatCore.lua\n"

    result = _export(_archive(tmp_path, package), destination)

    assert result.returncode == 0, result.stderr
    curated = (destination / "ChatCore.lua").read_bytes()
    assert curated.startswith(prefix)
    assert curated.endswith(suffix)
    rationale = curated[len(prefix):-len(suffix)]
    assert b"adze" not in rationale.lower()
    assert b"01M00TEST" not in rationale
    assert b"comms" in rationale.lower() and b"persist" in rationale.lower()
    assert all(
        not line.strip() or line.lstrip().startswith(b"--") for line in rationale.splitlines()
    )
    assert curated.count(b"\r\n") == source.count(b"\r\n")
    assert b"\n" not in curated.replace(b"\r\n", b"")


def test_export_preserves_git_and_existing_public_documentation_and_tools(
    tmp_path: Path, destination: Path, package: dict[str, bytes],
) -> None:
    (destination / "README.md").write_text("Public project README\n", encoding="utf-8")
    (destination / "docs").mkdir()
    (destination / "docs" / "install.md").write_text("Install notes\n", encoding="utf-8")
    (destination / "tools").mkdir()
    (destination / "tools" / "check.py").write_text("public_tool = True\n", encoding="utf-8")
    before = _snapshot(destination)

    result = _export(_archive(tmp_path, package), destination)

    assert result.returncode == 0, result.stderr
    after = _snapshot(destination)
    assert {name: after[name] for name in before} == before


@pytest.mark.parametrize("entry", ["Missing.lua", "libs/LibStub/LibStub.lua"])
def test_export_rejects_toc_entries_absent_from_curated_payload_before_writing(
    tmp_path: Path, destination: Path, package: dict[str, bytes], entry: str,
) -> None:
    package["ForeverSynthwave.toc"] += f"{entry}\n".encode()
    (destination / "ForeverSynthwave.lua").write_bytes(b"existing runtime\n")
    before = _snapshot(destination)

    result = _export(_archive(tmp_path, package), destination)

    assert result.returncode != 0
    assert Path(entry).name in result.stdout + result.stderr
    assert _snapshot(destination) == before


def test_export_rejects_archive_traversal_before_writing(
    tmp_path: Path, destination: Path, package: dict[str, bytes],
) -> None:
    package["../escape.lua"] = b"must never be extracted\n"
    before = _snapshot(destination)

    result = _export(_archive(tmp_path, package), destination)

    assert result.returncode != 0
    assert _snapshot(destination) == before
    assert not (tmp_path / "escape.lua").exists()


def test_repeated_exports_are_idempotent_and_remove_only_obsolete_managed_files(
    tmp_path: Path, destination: Path, package: dict[str, bytes],
) -> None:
    archive = _archive(tmp_path, package)
    first = _export(archive, destination)
    assert first.returncode == 0, first.stderr
    first_snapshot = _snapshot(destination)

    repeated = _export(archive, destination)
    assert repeated.returncode == 0, repeated.stderr
    assert _snapshot(destination) == first_snapshot

    (destination / "Local.lua").write_bytes(b"unmanaged user file\n")
    (destination / "docs").mkdir()
    (destination / "docs" / "notes.md").write_bytes(b"public notes\n")
    del package["media/retired.tga"]
    updated = _export(_archive(tmp_path, package), destination)

    assert updated.returncode == 0, updated.stderr
    assert not (destination / "media" / "retired.tga").exists()
    assert (destination / "Local.lua").read_bytes() == b"unmanaged user file\n"
    assert (destination / "docs" / "notes.md").read_bytes() == b"public notes\n"
    assert (destination / "media" / "panel.tga").read_bytes() == RUNTIME["media/panel.tga"]
