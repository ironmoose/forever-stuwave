# Development

This standalone repository is the canonical Forever STUwave source. Lua runtime files live at the root. `tools/` contains development utilities, Lua harnesses, Python tests, support modules and fixtures; `media/` and `fonts/` include asset generators. `mockups/` contains browser design sources and their required reference assets. Mockups are design studies, not demonstrations of shipped behavior.

## Setup and checks

Install Git, Python 3.11 or later, and [uv](https://docs.astral.sh/uv/). From the repository root:

```sh
uv sync
uv run python tools/check.py
```

The complete check runs the Lua 5.1 parse gate, lint with HIGH findings blocking, every `tools/*-harness.py`, and pytest. Mocked checks cannot establish actual client behavior. At the standalone migration checkpoint, 60 root Lua files parsed, HIGH lint passed, all 36 harnesses passed, and 288 Python tests passed (one Pillow deprecation warning).

For focused work:

```sh
uv run python tools/parse-gate.py
uv run python tools/lua-lint.py --fail-on high
uv run python tools/sealbar-harness.py
uv run python -m pytest -q
```

Lint can optionally use a client globals dump through `FS_GLOBALS_DUMP`; keep the dump outside the repository. Missing optional global evidence must not be presented as a verified client API inventory.

Generators can be run with `uv run python` and their script path. Read each generator's inputs and outputs before running it, and inspect generated diffs. `fonts/make_display_font.py` produces the renamed FS Display font; preserve its OFL notice. Browser mockups can be opened locally; their references remain design assets.

## Changes and release artifacts

Work on `main`, review the diff, run appropriate checks, and commit the reviewed changes. Use a branch from `main` only when concurrent repository work requires one. Push reviewed commits to the canonical GitHub repository when publication is authorized. Testers update with `git pull --ff-only`; no mirror export step is needed.

To create a runtime ZIP from **committed HEAD**:

```sh
uv run bash tools/package-forever-synthwave.sh
```

The script uses `python3` by default inside uv's environment (`PYTHON` can override it), and requires Git, zip, unzip and tar. It stages runtime files, validates the staged `.toc`, runs parse and HIGH lint gates, and produces `dist/ForeverSTUwave-<version>-<commit>-<date>.zip`. Its top folder remains `ForeverSynthwave`. Uncommitted edits, tooling, mockups and generators do not enter the ZIP. Send [TESTING.md](../TESTING.md) separately.

## Deploying a development build

Close the game before replacing files. The deploy scripts stage runtime files only and guard against overwriting a source or Git checkout. A clone installed in `Interface/AddOns` should be updated with Git instead.

On Linux, specify your installation root explicitly if it differs from the script's default:

```sh
WOW_ROOT="/path/to/World of Warcraft" uv run bash tools/deploy-forever-synthwave.sh
```

On Windows, after `uv sync`:

```powershell
.\tools\deploy-forever-synthwave.ps1 -WowRoot "C:\Program Files (x86)\World of Warcraft"
```

Both default to `_classic_beta_`; override the flavor only for a client you intend to test. Fully restart for added files, bindings, or textures. Deploying is a separate action from running headless checks.

## Optional live client tools

For the optional `fsdev` tools:

```sh
uv sync --extra fsdev
uv run --extra fsdev python tools/fsdev.py --help
```

Linux capture needs system GStreamer with PipeWire support, a working desktop ScreenCast portal, and `xdotool` for the applicable Gamescope input path; uv does not install these system components. Consult the tool's options before using it. `--shot-only` captures without sending client input. Input, focus changes and capture should be supervised and explicitly authorized.

An optional desktop identity allows the portal to recognize Forever STUwave. Install it manually if wanted:

```sh
mkdir -p ~/.local/share/applications
cp tools/fsdev_support/forever-stuwave.desktop ~/.local/share/applications/
```

Registration does not grant screen-sharing consent. Approve any portal prompt yourself. Keep captured account details, chats, and SavedVariables out of public commits.

## Runtime compatibility and client constraints

Keep the installed folder and manifest `ForeverSynthwave/ForeverSynthwave.toc`, hardcoded media paths, global frame names, and account-wide `ForeverSynthwaveDB` and `ForeverSynthwaveErrorLog` unchanged. Account-wide settings avoid a known Forever beta per-character restore problem.

Modules share the addon namespace through `local _, FS = ...`. `ErrorLog.lua` loads first. `ForeverSynthwave.lua` precedes `Theme.lua`, so theme reads happen at runtime. Preserve dependency order when adding `.toc` entries. `Theme.lua` owns palette, fonts, textures and chrome; `Layout.lua` owns geometry.

Feature-detect APIs and use secret guards before reading or transforming values. Protected frame and binding changes must follow existing combat deferral patterns. A shared `FS.PlayerClass` override remains future work; do not assume it exists.

## Current alpha boundary

Priest and Warlock HUD profiles ship alongside Paladin seal/aura controls, the Seal Chamber and Judgement lane. Judgement does not consume the seal on Forever. Judgement and its lane, Quick Keybind, and label visuals have live signoff; seal/aura clicks, expiry/no-seal states, shoulder seam and minimap first login still need checks. Advanced Paladin level 10/20 rotation rules are incomplete. Party row mouseover casting also needs live verification. See [TESTING.md](../TESTING.md).

Project code is MIT; preserve [third party notices](../THIRD_PARTY_NOTICES.md) and font OFL files. See [migration notes](MIGRATION.md) for provenance.
