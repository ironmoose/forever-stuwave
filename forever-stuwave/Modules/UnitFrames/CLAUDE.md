# UnitFrames

Unit, party and raid frames. Settings for how a frame looks are one shape, `bars.<frame>.<suffix>`, owned by `FrameStyle.lua`; a value equal to its default is stored as nothing, so a default frame saves no keys and draws as it always did.

## Key Files
- `FrameStyle.lua` -- defaults, readers and writers, linked frame and bar heights, text formats, `OnChange`
- `FrameExtras.lua` -- elite mark, target of target, combat icon, portrait, cast bar, PvP flag, leader crown, aggro border and percent; for the group frames the corner markers (`ReadMarkers`, `PaintMarkers`, `Rehold`), the group aggro ring (`BuildGroupAggro`, `UpdateGroupAggro`) and `NewFill` (a fill that can be drawn at another opacity)
- `UnitFrames.lua` -- player, target, focus and boss frames, and the plain-frame preview the Style tab draws
- `PartyFrames.lua`, `RaidFrames.lua` -- the group frames (PartyFrames is at the 200 file-local limit: add no new file-level locals)

## Patterns
- Everything drawable is on a non-secure child, so a style change runs in combat; only the secure button's size waits for PLAYER_REGEN_ENABLED.
- Health and power are secret: text goes through `SetFormattedText`, percent through `UnitHealthPercent`, and nothing is compared or computed on them.
- Bar looks come from `FrameHelpers.SetBarLook`; a bar built in its own look is left untouched.
- A row a frame does not apply yet is listed out of `Bars.WIRED` (ConfigPageBars.lua) and shows greyed.

- Group frames (party rows, raid cells): markers, the party tray and aggro read through `FS.FrameExtras`; every aura read is gated by `FS.AurasReadable()`, so in a fight the squares and the tray hold what they showed and refresh on PLAYER_REGEN_ENABLED. Party settings are applied by `PartyFrames.ApplyStyle` (a secure width waits for regen), raid settings by `ApplyCellStyle` (the cell's secure size by `SeatCell` through `EffSpec`).
- Party bar heights and text (`PartyFrames.RowHeight`, `SeatBars`, `SeatText`, `SizeRow`, `WriteHealthText`, `WritePowerText`): the row height is the built 52.4 plus what the rail pair grows by (9 + 4 + 9 at the defaults; a power height of 0 takes the bar and its gap out and keeps a hidden 1 px stand-in so the dispel halo still hugs the health rail). Rails, box, dashes and text follow at once in combat; the secure row, the stack of rows, the pet slot and the tray wait for PLAYER_REGEN_ENABLED (`SizeRow` returns false and `sizeOwed` is set). The health text is none, percent, number, both or missing: numbers go through `AbbreviateNumbers` (a refusal latches to the raw numbers), percent through `UnitHealthPercent` / `UnitPowerPercent` with the 0 to 100 curve, and missing is `UnitHealthMissing` passed straight to `SetFormattedText` with a Step curve over the health fraction driving the text's alpha (hidden at full health); without that gate or the API the percent shows. A healer's Roles page "Health text" drives the party text unless the party Style tab's own Text was set (`PartyFrames.HealthFormat`). New party functions go on the `PartyFrames` table: the file is at the file-scope local limit.
- The party buff switches are not `bars.*` keys: they are the `ForeverSTUwaveDB.partyBuffs` values `/fsparty buff` writes, through `PartyFrames.shared.SetBuff`.

## Harnesses
`tools/bars-harness.py`, `tools/unitframes-harness.py`, `tools/partyframes-harness.py`, `tools/raidframes-harness.py`, `tools/groupstyle-harness.py` (the group frames' markers, tray, aggro, text format, heights, width, looks and fill).
