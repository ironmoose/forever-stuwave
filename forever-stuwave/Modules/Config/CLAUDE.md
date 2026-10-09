# Config

The `/fsconfig` window: a category nav and a content well, built from `FS.ConfigWindow.UI` builders.

## Key Files
- `ConfigWindow.lua` -- window chrome, the builders, and the Unit Frames, Gunsight HUD and Profiles pages

## Patterns
- A builder takes `(content, opts)`, stacks itself below the previous row, binds `key` to `FS.Config` (or `get`/`set`), registers one refresh with `Track`, and returns its row; `row.control` is the clickable part.
- Pages build lazily on first show and read other modules' `SETTINGS` at build time (`FS.GunsightBoxes`), so a module that is absent just leaves its group out.
- Labels and values only on a row; any explanation goes in the `tip` (a `?` icon tooltip). Player-facing text says "cast bar", never "tape".
- `UI.Dropdown` shows `tostring(get())` on its button unless it gets `text(value)`; the Gunsight page's area dropdowns use it to show module names for ids. Its Target box tags group reads `FS.GunsightTags.SETTINGS` and is left out when that is absent.
- Every page is a clipped `ScrollFrame` (`Select` makes it; builders stack into its `fsHolder`). Content past the 432 px content area gives a scroll range, the wheel and a thumb in the well's right margin move it, `Select` resets it to the top, and a page that fits shows no bar. On a scrolling page the wheel over a `UI.Slider` scrolls the page; Shift adjusts the slider. Popups (dropdown menu, dialog) are parented outside the clip.
- `UI.Slider` is built from Theme pieces on a plain Button, not a Blizzard Slider. It drags through an `OnUpdate` that exists only while the mouse is down.

## Dependencies
- Depends on: `FS.Theme`, `FS.Config`, `FS.Gunsight`, `FS.GunsightBoxes`, `FS.GunsightTags`
- Depended on by: nothing; modules expose settings, this file reads them
