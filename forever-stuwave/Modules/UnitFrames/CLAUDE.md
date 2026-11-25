# UnitFrames

Unit, party and raid frames. Settings for how a frame looks are one shape, `bars.<frame>.<suffix>`, owned by `FrameStyle.lua`; a value equal to its default is stored as nothing, so a default frame saves no keys and draws as it always did.

## Key Files
- `FrameStyle.lua` -- defaults, readers and writers, linked frame and bar heights, text formats, `OnChange`
- `FrameExtras.lua` -- elite mark, target of target, combat icon, portrait, cast bar, PvP flag, leader crown, aggro border and percent
- `UnitFrames.lua` -- player, target, focus and boss frames, and the plain-frame preview the Style tab draws
- `PartyFrames.lua`, `RaidFrames.lua` -- the group frames (PartyFrames is at the 200 file-local limit: add no new file-level locals)

## Patterns
- Everything drawable is on a non-secure child, so a style change runs in combat; only the secure button's size waits for PLAYER_REGEN_ENABLED.
- Health and power are secret: text goes through `SetFormattedText`, percent through `UnitHealthPercent`, and nothing is compared or computed on them.
- Bar looks come from `FrameHelpers.SetBarLook`; a bar built in its own look is left untouched.
- A row a frame does not apply yet is listed out of `Bars.WIRED` (ConfigPageBars.lua) and shows greyed.

## Harnesses
`tools/bars-harness.py`, `tools/unitframes-harness.py`, `tools/partyframes-harness.py`, `tools/raidframes-harness.py`.
