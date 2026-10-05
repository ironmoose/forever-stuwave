# Standalone source migration

Forever STUwave began as an addon developed alongside other projects. This repository originally held a curated runtime snapshot. It now holds the canonical addon source and its complete development setup, with direct edits, validation and Git updates here.

## Origin

The standalone import is based on source commit `415f11d`. Its 60 root Lua modules were checked against that source with debug bytecode comparison. The import includes the `.toc`, `Bindings.xml`, runtime assets, generators, mockup sources and required references, tools, all 36 Lua harnesses, Python tests, fixtures and support modules, and independent `pyproject.toml` / `uv.lock` setup.

The original export manifest was removed because this repository no longer has a generated runtime surface. `tools/export_addon.py` remains historical tooling; do not use it to refresh the canonical source. The prior repository's addon copy has been retired in local commit `8c03ef5`, with its history and original files preserved in a verified local archive; unrelated projects remain untouched.

Excluded historical captures and private notes remain in the original Git history or local archive. They are not public source or current release evidence. The README's existing October 3, 2026 screenshots and designed masthead remain unchanged.

## Deliberate compatibility

The repository and visible product name are Forever STUwave. The installed folder, `.toc` filename, media paths, frame/global prefixes and SavedVariables identity remain `ForeverSynthwave`. This preserves texture loading and existing account settings. Testers clone this repository into a folder named `ForeverSynthwave` and update with `git pull --ff-only` while the game is closed.

## License and workflow

Project code and original project assets are MIT, copyright 2026 Parker (ironmoose). Fonts retain their separate OFL licenses. Screenshots and borrowed game icons, including those used by mockups, contain Blizzard material that this project does not license.

Development and validation now happen here using [the standalone workflow](DEVELOPMENT.md). Runtime packaging uses committed HEAD; client deployment stages runtime files only. Public updates are reviewed commits to this repository, not exports from another source tree.
