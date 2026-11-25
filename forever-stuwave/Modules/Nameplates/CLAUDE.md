# Nameplates

STUwave's own plates drawn over the game's, the combo pips under the target's plate, and the role threat view. The Nameplates page (`Config/ConfigPagePlates.lua`) and the Roles page (`Config/ConfigPageRoles.lua`) read the settings tables here; nothing in this folder reads a config page.

## Key Files
- `Nameplates.lua` -- the plates themselves, exported as `FS.Nameplates` (`Plates`). Loads before `Theme.lua` and reads theme exports at runtime. It sits near the parse gate's file scope local limit (183, the gate fails at 190): add to the `Plates` table, never a new file scope local.
- `NameplateCombo.lua` -- five combo pips under the target's plate (Rogue, and a Druid in Cat Form); the pips sit below the cast bar slot, which follows `plates.castH`.
- `PlateThreat.lua` -- `FS.PlateThreat`, the threat view for the role in use (colours, Aggro % or Lead text, alerts, range dim). Loads after `Core/Role.lua`; without `FS.Role` it does nothing.

## Settings (Nameplates.lua)
- `Plates.SETTINGS` is one table of `{ key, default, min, max, step | options }` for width, health, power and cast bar heights, name size, level, health text, quest marker, auras, raid marker and friendly plates (`plates.*`); `Plates.S` is the values in use, read once at login and on every change (`Plates.ReadSettings`), so plate code never reads the config on a hot path. A bad stored value reads as the default or the end of its range.
- `Plates.ApplySettings()` diffs `S` and applies what moved to the plates that are up and to the pooled ones (a pooled plate is laid out there, so its next acquire needs nothing). It touches only this file's own frames, so it is safe in combat.
- `Plates.GEOMETRY` and `Plates.PALETTE` are what the page's preview band draws from; change a measure there and the preview follows.
- Power height 0 closes the strip and the plate shrinks; cast height 0 never shows the bar.
- Friendly plates: Same as enemy, Smaller (the root scales to `GEOMETRY.SMALL_SCALE` around its centre), Off (no STUwave plate is built, the game's own stays hidden). A friendly is a unit the player cannot attack and that is a friend; a secret answer counts as not friendly. A duel or flag change refits the plate (`Plates.Refit`).
- Health text is written by `SetFormattedText` only; the percent is `UnitHealthPercent(unit, false, CurveConstants.ScaleTo100)`, feature detected. Nothing here compares a secret.
- `nameplates.enabled` (`Plates.SETTING`) turns the whole module off live; off leaves the game's plates as they are.

## Provider hooks (for PlateThreat, or any later view)
- `Plates.SetColorProvider(fn)`: `fn(unit)` answers a colour table (three plain numbers, alpha ignored) or nil to keep the plate's own fill. Asked whenever a plate's fill is worked out, on the threat events, and once for every plate that is up when the provider is set. A tap denied plate keeps its grey. Hand back the same table each time: the plate skips a fill it already wears by table identity.
- `Plates.SetTextProvider(fn)`: `fn(unit)` answers a string (a secret string is fine, it goes to `SetText`) and optionally a colour table for the small threat text inside the health bar; anything else hides it.
- No provider is the default (today's look). `nil` removes one. A provider that throws is swallowed and logged once (`plate_color_provider`, `plate_text_provider`); the plate keeps its own look.

## Role threat (PlateThreat.lua)
- `PT.Apply()` installs or removes the two providers for the role in use and the settings, and starts or stops the range check. It runs on login, on entering the world, on `FS.Role.OnChange` and on every `FS.Role.KEYS` setting change, so switching the role changes the plates at once. Only Tank, Melee and Ranged colour plates; only Tank gets the text provider.
- Role gating: every setting is read through `FS.Role` and acts only while its role is the one in use (`Role.Active`); the settings of the other roles keep their values and do nothing. The same switches read as the default when the value is secret or bad.
- Colours: tank on me cyan, slipping amber, not on me pink; melee and ranged on me pink, close amber (share at or above `<role>.pct`, else status 1 when the share is secret), safe cyan. The three colours are `PT.PALETTE`; `PT.SWATCHES` is what the page shows under "Colours".
- Alerts (`ALERTS`, each with its own switch; the sound has another): tank "lost aggro" (was mine, now other, sound `RAID_WARNING`), healer "a mob turns to me" (was other, now mine, sound `TELL_MESSAGE`), melee and ranged "warn" (was safe, now close, no sound). A mob alerts at most once per `TUNING.ALERT_GAP`; a state is read before it can change, so a mob first seen already on someone does not alert. The flash is a texture over the health bar (`root.threatFlash`) fading over `TUNING.FLASH_TIME`.
- Range dim: the target plate's health bar at `TUNING.DIM_ALPHA` out of range, checked every `TUNING.RANGE_EVERY` seconds. Melee uses the class's melee spell and the duel distance (`TUNING.NEAR_INTERACT`) together, ranged the class's spell; a secret answer goes to `SetAlphaFromBoolean`. The bar is put back to 1 when the role, the setting, the target or the plate changes.
- Secret text round trip: a secret percent cannot be formatted by Lua, so `SecretText` formats it through a hidden scratch font string and hands the resulting string to the plate's `SetText`. When the client will not format it the text simply stays hidden. A plain number is rounded and formatted directly (Lead gets a plus sign).
- Every threat read is feature detected, wrapped in `pcall` and checked with `FS.IsSecret` before a compare; a read that cannot be trusted answers nil and nil leaves the plate with its own colour. The threat APIs were never probed on this client (which returns are secret in a group, in combat), so each read has a plain fallback.

## Harnesses
`tools/nameplates-harness.py` (every default recorded against the original file, each setting live on up, pooled and later built plates, the providers, the health text secret path, the page and the preview), `tools/platethreat-harness.py` (providers per role and setting, colours with plain and secret reads, text, alerts, range dim, events), `tools/nameplatecombo-harness.py`, `tools/nameplate-auras-harness.py`, and the Roles page checks inside `tools/role-harness.py`.
