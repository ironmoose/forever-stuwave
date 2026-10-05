# Forever STUwave

Read [AGENTS.md](AGENTS.md) for repository rules and [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for setup and validation. This standalone repository is the canonical source; edit and test here, then commit on `main`. Publishing and client interaction require authorization from the task.

Runtime source is in `forever-stuwave/`, asset tooling in `tools/assets/`, and tester documentation in `docs/TESTING.md`. The public name is Forever STUwave; the runtime folder is `forever-stuwave`, and global/frame names use `ForeverSTUwave`. Preserve `.toc` load order, the shared `FS` namespace, secret guards, combat restrictions, and `Theme.lua` / `Layout.lua` as sources of truth.

Run `uv sync` and `uv run python tools/check.py`. Package committed HEAD with `uv run bash tools/package-forever-stuwave.sh`.
