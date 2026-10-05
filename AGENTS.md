# Agent guidance

This is the canonical Forever STUwave source repository. Read [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for setup, checks, packaging, and optional client tooling.

- Work directly on `main`. Use a branch from `main` only when another agent is editing this repository concurrently; coordinate ownership first. Do not push, publish, or merge without a user request.
- Run `uv sync`, then `uv run python tools/check.py` for the complete parse/lint, Lua harness, and Python test suite. Run appropriate focused checks while editing. Keep client observations distinct from mocked checks.
- Preserve `ForeverSynthwave` as the installed folder, `.toc` filename, internal addon identity, global frame prefix, and SavedVariables prefix. Texture paths rely on the folder name.
- Share addon state through `local _, FS = ...`. Preserve `.toc` order: `ErrorLog.lua` loads first; `ForeverSynthwave.lua` loads before `Theme.lua` and reads theme exports at runtime.
- Use `Theme.lua` for shared visual tokens and chrome helpers, and `Layout.lua` for geometry. Consume existing definitions instead of duplicating them.
- Guard secret values before arithmetic, comparison, indexing, formatting, concatenation, or conversion. Feature-detect APIs and retain unavailable data as unavailable.
- Defer protected frame and binding changes during combat. Reuse established secure button and combat deferral patterns.
- Describe support from shipped code and recorded client evidence. Paladin seals, auras, Seal Chamber and Judgement lane are implemented; advanced level 10/20 rotation work remains incomplete. A shared `FS.PlayerClass` override is future work.
- Commit reviewed source and checks before making a tester ZIP: packaging reads committed HEAD. Deploy only when client changes are authorized; use the runtime staging scripts rather than copying a development tree over an installed addon.
- Keep public files free of private machine paths, account dumps, credentials, and private project identifiers. Label mockups as design references and gameplay captures with their actual dates and classes.
- Preserve MIT and third-party notices. Fonts remain under OFL, and borrowed game imagery is not project-owned.

The historical ZIP importer is not the development or update workflow. See [migration notes](docs/MIGRATION.md) for origin and compatibility decisions.
