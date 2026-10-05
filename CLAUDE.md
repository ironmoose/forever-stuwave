# Forever STUwave

Read [AGENTS.md](AGENTS.md) for repository rules and [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for the source and export workflow. This is a curated alpha runtime mirror, with canonical development in a private monorepo.

Change gameplay in canonical source, validate and commit it there, package committed HEAD, then explicitly export the reviewed ZIP here. Review the mirror diff before committing. Do not push or publish automatically.

The public name is Forever STUwave; runtime identities remain `ForeverSynthwave`. Keep the `.toc` load order, the shared `FS` namespace, secret value guards, combat restrictions, and `Theme.lua` / `Layout.lua` as the sources of truth.
