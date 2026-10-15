# Development

This standalone repository is the canonical Forever STUwave source. Runtime files live in `forever-stuwave/`. `tools/` contains development utilities, Lua harnesses, Python tests, support modules and fixtures; `tools/assets/` contains texture generators and the font builder. Browser design mockups live in a local, untracked `mockups/` folder (ignored by git); they are design studies, not demonstrations of shipped behavior. Harnesses that compare against a mockup are skipped, and counted in a closing summary, by `tools/check.py` when `mockups/` is absent. To get full coverage from a clean export run `FS_MOCKUPS_DIR=<checkout>/mockups uv run python tools/check.py`; the script links that directory in as `mockups/` for the run and removes the link afterwards. When `mockups/` exists or `FS_MOCKUPS_DIR` is set, a missing mockup file is a failure.

## Setup and checks

Install Git, Python 3.11 or later, and [uv](https://docs.astral.sh/uv/). From the repository root:

```sh
uv sync
uv run python tools/check.py
```

The complete check runs the Lua 5.1 parse gate, lint with HIGH findings blocking, every `tools/*-harness.py`, and pytest. Mocked checks cannot establish actual client behavior.

For focused work:

```sh
uv run python tools/parse-gate.py
uv run python tools/lua-lint.py --fail-on high
uv run python tools/sealbar-harness.py
uv run python -m pytest -q
```

Lint can optionally use a client globals dump through `FS_GLOBALS_DUMP`; keep the dump outside the repository. Missing optional global evidence must not be presented as a verified client API inventory.

Run generators with `uv run python tools/assets/<script>.py`; textures go to `forever-stuwave/Media/Textures/`. Set `FS_ASSET_OUTPUT_DIR` to generate into a scratch directory. Read each generator's inputs and outputs before running it, and inspect generated diffs. `tools/assets/make_display_font.py` produces the renamed FS Display font; preserve its OFL notice. Browser mockups, when present locally, can be opened directly.

## Changes and release artifacts

Work on `main`, review the diff, run appropriate checks, and commit the reviewed changes. Use a branch from `main` only when concurrent repository work requires one. Push reviewed commits to the canonical GitHub repository when publication is authorized. Testers pull with `git pull --ff-only` and run the deploy script again.

To create a runtime ZIP from **committed HEAD**:

```sh
uv run bash tools/package-forever-stuwave.sh
```

The script uses `python3` by default inside uv's environment (`PYTHON` can override it), and requires Git, zip, unzip and tar. It stages runtime files, validates the staged `.toc`, runs parse and HIGH lint gates, and produces `dist/ForeverSTUwave-<version>-<commit>-<date>.zip`. Its top folder is `forever-stuwave`. Uncommitted edits, tooling, mockups and generators do not enter the ZIP. Send [TESTING.md](TESTING.md) separately.

The GitHub release asset is named `ForeverSTUwave-<version>.zip`, without the commit and date. After packaging, copy the new ZIP to that name before uploading it:

```sh
cp dist/ForeverSTUwave-<version>-<commit>-<date>.zip dist/ForeverSTUwave-<version>.zip
```

## Deploying a development build

Close the game before replacing files. The deploy scripts stage runtime files only and guard against overwriting a source or Git checkout. Keep the source checkout outside `Interface/AddOns`. If you used an earlier clone, move it aside and make a fresh clone outside `AddOns` once; screenshot removal required a history cleanup.

On Linux, specify your installation root explicitly if it differs from the script's default:

```sh
WOW_ROOT="/path/to/World of Warcraft" uv run bash tools/deploy-forever-stuwave.sh
```

On Windows, after `uv sync`:

```powershell
.\tools\deploy-forever-stuwave.ps1 -WowRoot "C:\Program Files (x86)\World of Warcraft"
```

Testers using a trusted published checkout can skip the parse and lint gates: add `-SkipParseGate` to the Windows command, or `FS_SKIP_GATES=1` before the Linux command. The Linux deploy and the packaging script still need a Python with `lupa` (`uv run` supplies one): they stage the runtime files, remove comments from the staged copies (newlines kept, so line numbers match the source), verify every `.lua` compiles to the same code as its source, and scan the remaining strings and identifiers for flagged vocabulary (`tools/stage_runtime.py`). Any mismatch or hit aborts before anything is installed or zipped. The source tree keeps its comments. On Windows, use `powershell -ExecutionPolicy Bypass -File .\tools\deploy-forever-stuwave.ps1 -SkipParseGate` if script execution is restricted. After `git pull --ff-only`, run the same deployment command again.

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

Registration does not grant screen-sharing consent. Approve any portal prompt yourself. The ScreenCast restore token is kept per app in `~/.cache/wow-tbc-bots/screencast_restore_token.forever-stuwave` (other tools keep their own file, since portal tokens are bound to the app that received them). A capture that times out or is denied closes its portal session and request and does not retry. Keep captured account details, chats, and SavedVariables out of public commits.

## Runtime compatibility and client constraints

Keep the installed folder and manifest `forever-stuwave/forever-stuwave.toc`, hardcoded media paths, global frame names, and account-wide `ForeverSTUwaveDB` and `ForeverSTUwaveErrorLog` unchanged. Account-wide settings avoid a known Forever beta per-character restore problem.

Modules share the addon namespace through `local _, FS = ...`. `ErrorLog.lua` loads first. `Modules/Nameplates/Nameplates.lua` precedes `Theme.lua`, so theme reads happen at runtime. Preserve dependency order when adding `.toc` entries. `Theme.lua` owns palette, fonts, textures and chrome; `Layout.lua` owns geometry.

Feature-detect APIs and use secret guards before reading or transforming values. Protected frame and binding changes must follow existing combat deferral patterns. A shared `FS.PlayerClass` override remains future work; do not assume it exists.

## Current alpha boundary

Priest and Warlock HUD profiles ship alongside Paladin seal/aura controls, the compact Seal module and its Judgement row. Shaman has a totem tab with two totem preset cells, a buff tab, and a totem pole Class Module with a shock gauge. Every mana class has the Mana regen module, and the micro menu and class tab spell icons can be switched between Stock and Gradient. Totem presets, the Mana regen module and the micro menu icons have been played through on a live character. The rest of the Shaman work has headless checks only: the buff tab combat state (the weapon imbue half may not show yet) and one preset click casting exactly one totem in combat are not confirmed in game. The checklist in [TESTING.md](TESTING.md) still applies. Judgement does not consume the seal on Forever. Judgement and its lane, Quick Keybind, and label visuals have live signoff; seal/aura clicks, expiry/no-seal states, shoulder seam and minimap first login still need checks. Advanced Paladin level 10/20 rotation rules are incomplete. Party row mouseover casting also needs live verification. See [TESTING.md](TESTING.md).

Project code is MIT; preserve [third party notices](THIRD_PARTY_NOTICES.md) and font OFL files.
