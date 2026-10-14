# ActionBars

The Console, its bars and the class shoulders on its top edge. This file covers the shoulder tabs; the bars themselves are documented in their file headers.

## Key Files
- `ClassShoulder.lua` -- the shoulder chrome and the seats. `OWNERS` lists the class tabs (Paladin, Warrior, Shaman and the Shaman's `also` buff tab); `FIVE` is the five second rule tab, a shoulder of every mana class that is NOT an owner entry
- `BuffTab.lua` + `ShamanBuffs.lua` -- the Shaman IMBUE and SHIELD tab and its data
- `FiveSecondTab.lua` -- the five second rule tab (mockups/five-second-rule-module-2026-10-14.html, concept C, CELLS)

## Five second rule tab (`FS.FiveSecondTab`)
- Two 38 px tiles on a second shoulder (92.8 x 49): CELLS (five cells that drain one a second, `~N.N` text, cyan REGEN at 0.0 with one rim pulse, a dim idle look a few seconds later) and RATE (mana per second plus a retention chip). Display only: plain frames `FSFiveSecondTab`, `FSFiveSecondCells`, `FSFiveSecondRate`, no secure button, no binding, no target gate.
- Who: Priest, Mage, Warlock, Hunter, Druid, Shaman, Paladin; never Warrior or Rogue. A Druid shows it in a mana form only (`UnitPowerType`, an unreadable answer shows it). The ledger keeps listening while it is hidden.
- Seat: `ClassShoulder.lua` works the x out on every Refresh, 16 design px right of the last class tab that stands (Paladin: after the 306.8 px seal block; Shaman: after the buff tab, at 424.8), 36 when the class has no tab. A moved seat tells the tab (`changed` -> `Sync`) like a shown or hidden one. No Console, no tab.
- Ledger (the whole truth is an ESTIMATE): `UNIT_SPELLCAST_SUCCEEDED` for `"player"` with a plain type 0 cost above 0 in `C_Spell.GetSpellPowerCost` starts five seconds; a re-cast restarts them; a cost that cannot be read plainly starts nothing; mana is never read (`UnitPower` on mana is always secret). A mana channel holds the window at the full five seconds until `UNIT_SPELLCAST_CHANNEL_STOP` (or `UnitChannelInfo` saying nothing channels), then the five seconds run. Unverified on Forever: channels, cancelled casts, free casts from procs.
- Rate: `GetPowerRegen()` is plain out of combat only. It is read once a second and at regen, kept in combat, and the RATE underline is dashed while the numbers on show are the kept ones. Casting rate shows while the window runs, the full rate otherwise. Retention is `casting / full` as a percent (cyan at 1% or more, a hollow `0%` below).
- Settings (`FS.FiveSecondTab.SETTINGS`, read by `ConfigWindow.lua`'s Unit Frames page): `fivesecond.enabled` (default on), `fivesecond.pulse` (on), `fivesecond.sound` (off). Each is explained by its `tip`; the client text says only "five second rule" and "regen".
- Nothing here is protected, so building, painting, the master toggle and the Druid hide are legal in combat; the host's anchor onto the Console waits for `PLAYER_REGEN_ENABLED` inside `Sync`. A hidden Druid form or a master toggle flipped in combat leaves the shoulder art until the next out of combat Refresh.
- Guesses to probe live: the sound (`SOUNDKIT.TELL_MESSAGE`), the channel default, `UnitPowerType` being plain for a Druid, and whether `GetPowerRegen` is secret in combat outside instances.
- `tools/fivesecond-harness.py` pins it (window, pulse, fade, rate cache, chip, tooltips, settings, seats for Priest, Paladin and Shaman, secrets, combat).

## Dependencies
- `FiveSecondTab.lua` depends on: `FS.Theme`, `FS.FrameHelpers`, `FS.Layout`, `FS.Config`, `FS.ClassShoulder`; it loads after `BuffTab.lua` and before `ConfigWindow.lua`
- Depended on by: `ClassShoulder.lua` (`OwnsShoulder`, `Sync`), `ConfigWindow.lua` (`SETTINGS`, `Applies`)
