# Agent guidance

This repo is the curated runtime mirror for Forever STUwave. During the alpha, the canonical development source stays in a private monorepo. Read [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) before changing anything.

- Make gameplay and Lua changes in canonical source, run its gates and relevant harnesses, then commit there before packaging. Do not patch generated runtime Lua here.
- Refresh the mirror explicitly with `tools/export_addon.py` from an existing gated ZIP. The exporter manages runtime assets, public `.toc` branding, and public source comment cleanup; its lexer protects string literals and keeps line endings and line counts. During release review, separately compare compiled bytecode between the curated Lua and its packaged source, and inspect the export diff before committing. Exporting does not authorize publication or pushing.
- Preserve `ForeverSynthwave` as the installed folder, `.toc` filename, internal addon identity, global frame prefix, and SavedVariables prefix. Texture paths rely on the folder name.
- Share addon state through `local _, FS = ...`. Respect the `.toc` load order: `ErrorLog.lua` is first; `ForeverSynthwave.lua` loads before `Theme.lua` and reads theme exports only at runtime.
- Use `Theme.lua` for shared visual tokens and chrome helpers, and `Layout.lua` for geometry. Do not duplicate those definitions in component modules.
- Check secret values before arithmetic, comparison, indexing, formatting, or string conversion. Use existing guards and feature detection; unavailable data must stay unavailable.
- Defer protected frame changes during combat. Follow the established secure button and combat deferral patterns; a headless harness cannot establish live client behavior.
- Describe class support from shipped profiles and recorded client evidence. Paladin recon infrastructure is built; its class HUD and live verification are still pending. `FS.PlayerClass` is a future seam, not an existing shared API.
- Keep public docs free of private identifiers, local machine paths, SavedVariables dumps, and unpublished mockups presented as working UI.
- Work on `main` unless concurrent work requires an explicitly assigned branch. Do not push, publish, or merge without a user request.

The code license is pending. Preserve bundled font notices and licenses when updating assets.
