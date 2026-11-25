# Data bars

The strip pinned to the bottom of the screen: the data bar (time, gold, rested, FPS, latency, durability, bag slots, optional reputation and professions) with the XP bar stacked flush on top of it. Together they are "one console strip, split in two"; the control deck stands on the XP bar.

## Key Files
- `DataBar.lua` -- `ForeverSTUwaveDataBar` (height `Segments.BAR_HEIGHT`, 20), the segment list, `FS.DataBarSegments` (the door the Data bar page uses), the gold record other characters read.
- `XPBar.lua` -- `ForeverSTUwaveXPBar` (docked on the data bar), the look variants (`FS.xpVariants`, `/fsxp`), the stock bar hide, `FS.xpBarHeight()` (the saved look's height).

## Module power
One switch, `m.data` (`Core/ModuleSwitch.lua`; the store and the gate shape are in `Modules/Config/CLAUDE.md` "Module power"), covers both bars. Decision (B5d): there is no separate XP bar switch, the XP bar is built to stand on the data bar and is drawn as its second half, so keeping it alone would leave a 20 unit hole under it and make the XP bar impossible to turn off. Off, neither bar exists and the game's own XP and reputation tracking bar is left as the game has it.
- Start: each file makes its login frame from `MS.WhenOn("m.data", Start)` (the data bar's first, so its PLAYER_LOGIN seat still comes before the XP bar's). `MS.MarkBuilt("m.data")` at the end of the data bar's `Init`. `HideBlizzardBars` (`UnregisterAllEvents`, `Hide` and an OnShow re-hide on `StatusTrackingBarManager` and its two containers) runs only from that login handler, so off never runs it.
- Stays defined while off: `FS.DataBarSegments` (the order, the segment switches, the titles and `Segments.BAR_HEIGHT`), `FS.xpVariants`, `FS.xpBarHeight()`. `/fsxp` says the module is off and saves nothing. The gold segment's record of this character's gold stops with the bar (nothing listens for `PLAYER_MONEY` while off).
- The control deck must not move (`Deck.lua`, `AnchorChassis`): with the module off it anchors to the screen bottom right at the height the two bars made, the data bar's height plus `FS.xpBarHeight()` (32 with the default look), at the same distance from the right edge, and reports nothing. With it on the chassis stands on the XP bar's top right as before; because both bars now start at ADDON_LOADED, after the deck's own file scope login handler, that handler's first try finds no XP bar and the retry a frame later seats it (the retry was written for an XP bar that is late).
- `tools/moduleswitch-harness.py` (B5d rows): the data bar off and on, the deck's seat on and off for the default and a saved look, and the listening of both files.
