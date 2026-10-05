# Development and the runtime mirror

Forever STUwave is the public presentation of the `ForeverSynthwave` addon. During the alpha, this repository contains a curated runtime snapshot. The canonical source, development tools, harnesses, and work in progress remain in a private monorepo.

Report bugs with the [testing guide](../TESTING.md). Gameplay patches begin in canonical source; edits to runtime Lua in this mirror would be replaced by the next export.

## Maintainer update flow

1. Implement in canonical source. Run its parse and lint gates, relevant headless harnesses, and any required client verification. Clearly distinguish harness results from observations in game.
2. Review and commit the intended canonical changes. The existing `addons/package-forever-synthwave.sh` packages **committed HEAD**, not uncommitted work. Run it with its normal gates enabled and keep the ZIP it produces.
3. From this mirror's checkout, export that existing ZIP into the local checkout:

   ```sh
   python3 tools/export_addon.py \
     --archive /path/to/ForeverSynthwave-reviewed.zip \
     --destination /path/to/forever-stuwave
   ```

4. Inspect `git diff` and `git status`, including the `.stuwave-export.json` manifest, `.toc` branding, changed runtime files, and any removals. Review the archive's canonical revision as well as its version. Separately compare compiled bytecode between the curated Lua and its packaged source as part of release review.
5. Commit the reviewed mirror update separately. Publication or pushing is a separate action requested by the maintainer.

The exporter manages runtime assets, public `.toc` branding, and public source comment cleanup using `.stuwave-export.json`. Comment cleanup removes private design records with a lexer that protects string literals and keeps line endings and line counts. Public docs, screenshots, and tooling belong to this repository and remain outside that managed runtime surface. Export is an explicit step; it is not a background sync or an automatic push after every canonical change.

## Runtime identities and load order

The installed folder and manifest remain `ForeverSynthwave/ForeverSynthwave.toc`. Hardcoded texture paths use `Interface\\AddOns\\ForeverSynthwave\\...`; changing the folder name breaks those paths. Keep the internal addon identity, global frame names, and the account SavedVariables `ForeverSynthwaveDB` and `ForeverSynthwaveErrorLog` intact.

Modules that share addon state capture the addon table with `local _, FS = ...` or `local addonName, FS = ...`. Cross module state belongs on that table, owned by its defining module and read at the appropriate runtime point. A local variable in one file is not shared with another.

`ErrorLog.lua` loads first. `ForeverSynthwave.lua` loads before `Theme.lua`, so its theme access occurs inside runtime handlers rather than at file scope. Later modules rely on `.toc` order for their helpers; preserve dependencies when adding or moving entries.

`Theme.lua` owns shared palette, font, texture, and chrome tokens. `Layout.lua` owns geometry and rescale behavior. Consume their definitions instead of introducing competing copies in components.

## Forever client constraints

Feature detect APIs and check values with the existing secret guards before arithmetic, comparison, indexing, concatenation, formatting, or conversion. Do not infer health, power, or aura state from an unreadable value. Use existing failure and diagnostic paths.

Protected frames and attributes have combat restrictions. Reuse the established deferral and secure button patterns rather than changing protected geometry or bindings in combat. Headless checks establish behavior against their mocks; mark live behavior as unverified until observed on the client.

Settings are account wide. Do not move them to per character SavedVariables without verifying the Forever beta client's restore behavior.

## Current class boundary

`HudProfiles.lua` defines Priest and Warlock profiles. Paladin has recon candidates in `Diagnostics.lua`, first login harness coverage in canonical source, and spell gated party dispel capability in `PartyFrames.lua`. Its seal, aura, and Judgement HUD is not implemented.

PartyFrames currently has a local `PlayerClass()` wrapper around `UnitClass`. A shared `FS.PlayerClass` override remains future work; do not assume that API exists. `/fsmouseover` controls a client setting, and party row casting still requires live verification.

## Public assets

Use real, dated gameplay screenshots with accurate captions. Keep browser mockups out of claims about the shipped UI. Inspect diagnostic reports before publishing; do not copy whole SavedVariables files into this repository.

Bundled fonts keep their OFL files and provenance in [fonts/README.md](../fonts/README.md). The project's code license is pending; third party font licenses remain separate.
