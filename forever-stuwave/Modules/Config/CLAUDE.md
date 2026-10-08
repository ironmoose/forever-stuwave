# Config

The `/fsconfig` window: a category nav and a content well, built from `FS.ConfigWindow.UI` builders.

## Key Files
- `ConfigWindow.lua` -- window chrome, the builders, and the Unit Frames, Gunsight HUD and Profiles pages

## Patterns
- A builder takes `(content, opts)`, stacks itself below the previous row, binds `key` to `FS.Config` (or `get`/`set`), registers one refresh with `Track`, and returns its row; `row.control` is the clickable part.
- Pages build lazily on first show and read other modules' `SETTINGS` at build time (`FS.GunsightBoxes`), so a module that is absent just leaves its group out.
- Labels and values only on a row; any explanation goes in the `tip` (a `?` icon tooltip). Player-facing text says "cast bar", never "tape".
- `UI.Slider` is built from Theme pieces on a plain Button, not a Blizzard Slider. It drags through an `OnUpdate` that exists only while the mouse is down.

## Dependencies
- Depends on: `FS.Theme`, `FS.Config`, `FS.Gunsight`, `FS.GunsightBoxes`
- Depended on by: nothing; modules expose settings, this file reads them
