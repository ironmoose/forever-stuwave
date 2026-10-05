"""Verify the real installer against an isolated client tree."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RUNTIME = REPO / "forever-stuwave"
INSTALLER = REPO / "tools" / "deploy-forever-stuwave.sh"
# Frozen from the pre-reorganization manifest: dependency order must survive moves.
LOAD_ORDER = (
    "ErrorLog.lua", "Nameplates.lua", "Theme.lua", "Layout.lua", "FrameHelpers.lua",
    "ChevronCastBar.lua", "PanelSkins.lua", "Tracker.lua", "ChatCore.lua", "ChatTabs.lua",
    "ChatEditBox.lua", "ChatTermBar.lua", "ChatWindowState.lua", "ChatFrameSkin.lua",
    "ChatSlashCommands.lua", "ChatFormat.lua", "UnitFrames.lua", "TargetAuras.lua",
    "PartyFrames.lua", "CastBars.lua", "Buffs.lua", "Professions.lua", "ActionBars.lua",
    "Console.lua", "StanceBar.lua", "PetFrame.lua", "PetDock.lua", "PetActionBar.lua",
    "PetCastBar.lua", "Minimap.lua", "Panels.lua", "Tooltip.lua", "Popups.lua", "Menus.lua",
    "Bags.lua", "Loot.lua", "DataBar.lua", "XPBar.lua", "Deck.lua", "MicroBars.lua",
    "BagBar.lua", "HudText.lua", "IssueReporter.lua", "AuctionHouse.lua", "Diagnostics.lua",
    "HudSpells.lua", "HudProfiles.lua", "HudLogic.lua", "Gunsight.lua", "GunsightDots.lua",
    "GunsightSeals.lua", "GunsightFrame.lua", "GunsightBoxes.lua", "GunsightTape.lua",
    "ConsoleKeys.lua", "ClassShoulder.lua", "SealBar.lua", "CombatHud.lua", "FSProbe.lua",
    "BugReport.lua",
)


@pytest.fixture
def client(tmp_path: Path) -> Path:
    path = tmp_path / "WoW" / "_classic_beta_"
    (path / "Interface" / "AddOns").mkdir(parents=True)
    return path


def _install(client: Path, installer: Path = INSTALLER) -> subprocess.CompletedProcess[str]:
    assert installer.is_file(), f"Installer not implemented: {installer}"
    return subprocess.run(
        ["bash", str(installer)], cwd=installer.parent.parent,
        env=os.environ | {"WOW_ROOT": str(client.parent), "WOW_FLAVOR": client.name,
                          "FS_SKIP_GATES": "1"},
        capture_output=True, text=True, check=False,
    )


def _write(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents)


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*") if path.is_file()
    }


def _runtime_snapshot(root: Path, directory: str) -> dict[str, bytes]:
    files = _snapshot(root / directory)
    if directory in {"Core", "Modules"}:
        return {name: contents for name, contents in files.items() if name.endswith(".lua")}
    return {
        name: contents for name, contents in files.items()
        if name.endswith((".tga", ".ttf"))
        or (Path(name).name.startswith(("OFL", "LICENSE", "COPYING")) and name.endswith(".txt"))
    }


def test_module_manifest_preserves_dependency_order_and_loads_every_runtime_module() -> None:
    toc = RUNTIME / "forever-stuwave.toc"
    assert toc.is_file()
    lines = toc.read_text(encoding="utf-8").splitlines()
    entries = [line.strip().replace("\\", "/") for line in lines
               if line.strip() and not line.lstrip().startswith("#")]
    modules = [Path(entry) for entry in entries if entry.endswith(".lua")]

    assert tuple(path.name for path in modules) == LOAD_ORDER
    assert len(set(modules)) == 60
    assert all((RUNTIME / entry).is_file() for entry in entries)
    assert all(path.parts[0] in {"Core", "Modules"} for path in modules)
    assert not list(RUNTIME.glob("*.lua"))
    discovered = {path.relative_to(RUNTIME) for directory in ("Core", "Modules")
                  for path in (RUNTIME / directory).rglob("*.lua")}
    assert discovered == set(modules)
    assert "## SavedVariables: ForeverSTUwaveDB, ForeverSTUwaveErrorLog" in lines
    assert not (REPO / "addon").exists()


def test_install_stages_runtime_and_prunes_stale_files_without_creating_saved_data(client: Path) -> None:
    installed = client / "Interface" / "AddOns" / "forever-stuwave"
    _write(installed / "obsolete.lua", b"old runtime")
    result = _install(client)

    assert result.returncode == 0, result.stdout + result.stderr
    assert not (installed / "obsolete.lua").exists()
    assert (installed / "forever-stuwave.toc").read_bytes() == (RUNTIME / "forever-stuwave.toc").read_bytes()
    assert (installed / "Bindings.xml").read_bytes() == (RUNTIME / "Bindings.xml").read_bytes()
    assert (installed / "LICENSE").read_bytes() == (REPO / "LICENSE").read_bytes()
    for directory in ("Core", "Modules", "Media"):
        assert _snapshot(installed / directory) == _runtime_snapshot(RUNTIME, directory)
    assert not (installed / "tools").exists()
    assert not (client / "WTF").exists()
    before = _snapshot(installed)
    repeated = _install(client)
    assert repeated.returncode == 0, repeated.stdout + repeated.stderr
    assert _snapshot(installed) == before


def test_install_excludes_development_files_and_python_cache_from_runtime_payload(
    client: Path, tmp_path: Path,
) -> None:
    checkout = tmp_path / "checkout"
    installer = checkout / "tools" / INSTALLER.name
    installer.parent.mkdir(parents=True)
    shutil.copyfile(INSTALLER, installer)
    runtime = checkout / "forever-stuwave"
    payload = {
        "Core/Theme.lua": b"local theme = {}\n",
        "Modules/Chat/Chat.lua": b"local chat = {}\n",
        "forever-stuwave.toc": b"Core/Theme.lua\nModules/Chat/Chat.lua\n",
        "Bindings.xml": b"<Bindings/>\n",
        "Media/Textures/panel.tga": b"runtime texture",
        "Media/Fonts/Orbitron.ttf": b"runtime font",
        "Media/Fonts/OFL.txt": b"font license",
    }
    development = {
        "Core/diagnostic.py": b"development script",
        "Modules/Chat/test_chat.py": b"development test",
        "Media/Textures/__pycache__/generate.cpython-313.pyc": b"cached Python bytecode",
        "Media/Textures/generate.py": b"texture generator",
        "Media/Textures/screenshot.png": b"private development capture",
        "Media/Fonts/notes.md": b"development notes",
    }
    for name, contents in (payload | development).items():
        _write(runtime / name, contents)
    _write(checkout / "LICENSE", b"MIT license")
    result = _install(client, installer)

    assert result.returncode == 0, result.stdout + result.stderr
    installed = client / "Interface" / "AddOns" / "forever-stuwave"
    assert _snapshot(installed) == payload | {"LICENSE": b"MIT license"}
    assert _snapshot(runtime) == payload | development


def test_install_migrates_saved_settings_and_backup_without_changing_originals(client: Path) -> None:
    saved = client / "WTF" / "Account" / "TEST_ACCOUNT" / "SavedVariables"
    original = b'ForeverSynthwaveDB = { ["scale"] = 0.8 }\nForeverSynthwaveErrorLog = {}\n'
    backup = b'ForeverSynthwaveDB = { ["scale"] = 0.7 }\n'
    _write(saved / "ForeverSynthwave.lua", original)
    _write(saved / "ForeverSynthwave.lua.bak", backup)
    result = _install(client)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (saved / "forever-stuwave.lua").read_bytes() == original.replace(b"ForeverSynthwave", b"ForeverSTUwave")
    assert (saved / "forever-stuwave.lua.bak").read_bytes() == backup.replace(b"ForeverSynthwave", b"ForeverSTUwave")
    assert (saved / "ForeverSynthwave.lua").read_bytes() == original
    assert (saved / "ForeverSynthwave.lua.bak").read_bytes() == backup


@pytest.mark.parametrize("existing", ["forever-stuwave.lua", "forever-stuwave.lua.bak"])
def test_migration_preserves_each_existing_new_saved_file_independently(client: Path, existing: str) -> None:
    saved = client / "WTF" / "Account" / "TEST_ACCOUNT" / "SavedVariables"
    legacy = b'ForeverSynthwaveDB = { ["scale"] = 0.8 }\n'
    current = b'ForeverSTUwaveDB = { ["scale"] = 1.2 }\n'
    for filename in ("ForeverSynthwave.lua", "ForeverSynthwave.lua.bak"):
        _write(saved / filename, legacy)
    _write(saved / existing, current)
    result = _install(client)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (saved / existing).read_bytes() == current
    other = "forever-stuwave.lua.bak" if existing.endswith(".lua") else "forever-stuwave.lua"
    assert (saved / other).read_bytes() == legacy.replace(b"ForeverSynthwave", b"ForeverSTUwave")


def test_migration_updates_legacy_click_bindings_once_and_keeps_original_backup(client: Path) -> None:
    account = client / "WTF" / "Account" / "TEST_ACCOUNT"
    cache = account / "Realm" / "Character" / "bindings-cache.wtf"
    original = (b'bind "F" "CLICK ForeverSynthwavePanelButton:LeftButton"\n'
                b'bind "G" "CLICK FSSealButton1:LeftButton"\n'
                b'bind "1" "ACTIONBUTTON1"\n')
    _write(cache, original)
    _write(account / "bindings-cache.wtf", b'bind "1" "ACTIONBUTTON1"\n')
    result = _install(client)

    assert result.returncode == 0, result.stdout + result.stderr
    assert cache.read_bytes() == original.replace(b"ForeverSynthwavePanel", b"ForeverSTUwavePanel")
    assert (account / "bindings-cache.wtf").read_bytes() == b'bind "1" "ACTIONBUTTON1"\n'
    backups = [path for path in cache.parent.iterdir() if path != cache and path.is_file()]
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    before = _snapshot(account)
    repeated = _install(client)
    assert repeated.returncode == 0, repeated.stdout + repeated.stderr
    assert _snapshot(account) == before


def test_migration_preserves_an_existing_binding_backup(client: Path) -> None:
    cache = client / "WTF" / "Account" / "TEST_ACCOUNT" / "bindings-cache.wtf"
    backup = cache.with_name("bindings-cache.wtf.forever-stuwave.bak")
    _write(cache, b'bind "F" "CLICK ForeverSynthwavePanelButton:LeftButton"\n')
    _write(backup, b'bind "1" "ACTIONBUTTON1"\n')
    result = _install(client)

    assert result.returncode == 0, result.stdout + result.stderr
    assert cache.read_bytes() == b'bind "F" "CLICK ForeverSTUwavePanelButton:LeftButton"\n'
    assert backup.read_bytes() == b'bind "1" "ACTIONBUTTON1"\n'


def test_install_retires_old_runtime_outside_addons_without_losing_files(client: Path) -> None:
    old = client / "Interface" / "AddOns" / "ForeverSynthwave"
    _write(old / "ForeverSynthwave.lua", b"legacy runtime")
    _write(old / "local-notes" / "keep.txt", b"preserve local file")
    before = _snapshot(old)
    result = _install(client)

    assert result.returncode == 0, result.stdout + result.stderr
    assert not old.exists()
    retired = list((client / "Interface" / "RetiredAddOns").glob("ForeverSynthwave-*"))
    assert len(retired) == 1
    assert _snapshot(retired[0]) == before
    assert (client / "Interface" / "AddOns" / "forever-stuwave").is_dir()


@pytest.mark.parametrize("folder", ["ForeverSynthwave", "forever-stuwave"])
def test_install_refuses_either_git_checkout_before_modifying_client_files(client: Path, folder: str) -> None:
    checkout = client / "Interface" / "AddOns" / folder
    _write(checkout / ".git" / "config", b"git checkout marker")
    _write(checkout / "keep.lua", b"local development")
    saved = client / "WTF" / "Account" / "TEST_ACCOUNT" / "SavedVariables"
    _write(saved / "ForeverSynthwave.lua", b"ForeverSynthwaveDB = {}\n")
    before = _snapshot(client)
    result = _install(client)

    assert result.returncode != 0
    assert "Git" in result.stdout + result.stderr or "git" in result.stdout + result.stderr
    assert _snapshot(client) == before
