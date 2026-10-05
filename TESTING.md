# Trying the alpha

Forever STUwave targets the WoW Forever beta client, interface 16001. The current layout is centered on 16:9. Priest and Warlock have combat HUD profiles; Paladin testing is gathering the evidence for its own HUD.

## First login

1. Close the game and install the folder as described in the [README](README.md#install).
2. Confirm the file is at `Interface/AddOns/ForeverSynthwave/ForeverSynthwave.toc`, with no extra wrapper folder.
3. Restart the client and enable Forever STUwave at character selection.
4. Check the player frame, action deck, chat, minimap, and quest tracker. Note your resolution and any overlaps or missing elements.
5. Try selecting a friendly and hostile target, entering and leaving combat, opening bags, and joining or leaving a party when convenient. Record anything that changes unexpectedly.

The addon folder is named `ForeverSynthwave` even though the displayed project name is Forever STUwave. `/reload` cannot discover a newly installed addon or newly added files; restart for those.

## Report a problem

Run this as soon as something looks wrong:

```text
/fsbug what you were doing and what looked wrong
```

The note is optional. The command is designed to run in combat. A copy window opens: click inside, press Ctrl+A then Ctrl+C, and paste into a `.txt` file. Escape or the Close button closes it. If the window itself misbehaves, record that too.

Send the maintainer the report and a sentence describing the expected result. Include a screenshot when the problem is visual. Once the public repo exists, a [new issue](https://github.com/ironmoose/forever-stuwave/issues/new) is another place to report it.

**Read the report before posting it publicly.** It includes class, level, zone, addon list, settings, recent errors and, when available, class recon. Remove anything you do not want shared.

| Command | Use |
| --- | --- |
| `/fsbug all` | Show stored reports; the last 20 are kept. |
| `/fsbug clear` | Delete stored reports, after saving the ones you need. |
| `/fserr` | Inspect captured errors. |
| `/fserr clear` | Clear the error log, after saving a report. |

If chat says `error was thrown and logged (/fsbug to report)`, capture a report then. The addon suppresses popups for its captured Lua errors; protected action warnings can still appear and should also be reported. If chat says the error log is full, save a report before using `/fserr clear`.

## Paladin recon: level 1, then around level 10

The Paladin seal, aura, and Judgement HUD has not been implemented. These runs tell us what the Forever client exposes on your character; a missing HUD profile is expected.

1. If you know a seal, aura, or blessing, activate the ones available to you. A blessing can be on yourself or a party member.
2. Select a suitable enemy and attack it. If you have learned Judgement, use it and observe what happens to your seal and the target. Record the behavior without assuming whether the seal is consumed.
3. Stop attacking and let combat end. Keep the target selected. If practical, choose an encounter where the target survives and its effects can still be inspected afterward.
4. Note the state of your seal, aura, and blessing. Restore available effects for the snapshot if needed, and mention what you restored in the report.
5. Promptly run `/fsrecon class` out of combat, with the target still selected.
6. Look for chat lines beginning `synthwave://class`. If an aura section says `skipped` or `no target`, retry out of combat with your target selected. If it remains unavailable, report that result too.
7. Immediately run `/fsbug Paladin recon, level and observations here`, then copy and save the report.

Only the first successful `/fsbug` after a recon includes the full run; later reports carry a reference to it. If the copy window did not open, run `/fsbug` again. Do not clear reports until you have saved and sent the full one.

The most recent class recon is shared across the account. Capture the report before switching characters or running another recon.

## Mouseover experiment

`/fsmouseover [on|off] [alt|ctrl|shift|none]` controls the client mouseover casting setting. Party row behavior has not been verified in game. If you try it, record which row you hovered, the spell and modifier, the actual recipient, and whether you were in combat; include `/fsbug` if it behaves unexpectedly.

## If the report window will not open

Reports are also stored in the account SavedVariables file, written on `/reload` or logout:

```text
WTF/Account/<ACCOUNT>/SavedVariables/ForeverSynthwave.lua
```

Use the `WTF` folder for the same client where you installed the addon. This file contains settings, diagnostic probes, and multiple reports. Ask the maintainer for a private way to share it if needed; inspect it first and avoid posting the entire file in a public issue by default.
