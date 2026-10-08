# Forever STUwave: alpha testing

Use the [README installation and update instructions](../README.md). Close the game before deploying an update, and fully restart for newly added files, bindings or textures. The visible addon name is **Forever STUwave**; its folder is `forever-stuwave` and manifest is `forever-stuwave.toc`.

Judgement behavior and its HUD lane, Quick Keybind, and the current key label visuals have been checked in game. Seal/aura clicks, chamber expiry and no-seal states, the shoulder seam, and minimap placement on a new character's first login still need checks. Advanced Paladin level 10/20 rotation rules remain incomplete. The checklist below also helps catch regressions in checked features.

## Report a bug: /fsbug

Inspect reports before posting them publicly. Use [GitHub issues](https://github.com/ironmoose/forever-stuwave/issues/new) or send the report directly to the maintainer. Include the build's version or Git commit when you know it.

Type this in chat the moment something looks wrong:

    /fsbug what you were doing and what looked wrong

The note is optional. A window opens with the report in it.

1. Click inside the window.
2. Press Ctrl+A, then Ctrl+C.
3. Paste into a new .txt file and send it to the maintainer.

It is safe to run in combat. Escape or the Close button closes the window.

Other commands:

- `/fsbug all` shows every stored report (the last 20 are kept).
- `/fsbug clear` deletes the stored reports.

## Minimap on a new character's first login

The minimap may sit in the wrong place on a character's very first login only.

1. Create a new character and log in. Do NOT type /reload.
2. Look at the minimap: it should sit in its usual seat at the top right.
3. Type `/fsbug minimap first login`, copy the window as above and send it to the maintainer, whether the minimap looked right or not.

The log is account wide: if another character already logged in with this build, send the /fsbug before your next login or /reload, or this login's log is lost.

Optional developer diagnostics: `/fsprobe` records what this client exposes in and out of combat.

## Paladin: seals, auras, Seal Chamber, chat font

Use a Paladin that has learned at least one seal. Step 6 works on any class.

1. Install this build and do a FULL client restart, not /reload. This build
   adds new files (.toc lines, Bindings.xml, .tga images) that only load on
   a restart.
2. Seal and aura buttons, on the Console's top-left shoulder:
   - Top row is seals. Each seal you have learned shows, packed from the
     left. Slots for seals you have not learned stay hidden.
   - Bottom row is auras. They are your Paladin's forms. The active one is
     highlighted. Switch aura and check the highlight follows (needs two
     auras, skip otherwise).
   - Click a button: it casts. After you cast, the swipe shows on the button.
   - If you turn the Console off (`/fsconsole off`), the buttons sit above
     the stance bar spot instead. Then `/fsconsole on` before step 4 (the
     switch waits for combat to end).
3. Quick Keybind (button names are Blizzard's wording and may vary):
   - Open Blizzard's Quick Keybind mode: Esc > Options > Keybindings, then the
     "Quick Keybind Mode" button.
   - Hover a seal button, press a key, then click Okay.
   - Leave the mode and press the key: it casts that seal.
   - Type /reload and press the key again: the binding is still there.
   - Check the labels: white text on dark backing, matching the action bars.
     Middle Mouse displays as `MM`; Mouse Button 4 as `MB4`, and so on.
     Modified labels stay compact, such as `C-MB4` and `S-MM`.
   - If Quick Keybind won't take, bind the key through Key Bindings > AddOns
     instead, and say so in your report.
   - Open Key Bindings > AddOns. The "Forever STUwave" header lists the seal
     names ("Seal of Righteousness" and so on).
   - Turn the "Cast on key down" option on, test, then turn it off and test
     again. It must be one cast per press either way. (Wording varies. It is
     in Options > Combat; some clients put it under Gameplay > Controls.)
   - Optional, needs a level-up: bind a key to a seal, then learn a new seal.
     The buttons repack, but the key still casts the same seal.
   - Aura keys use the game's own stance bindings, so learning a new aura can
     move a key to the neighbouring aura, the same as Blizzard's stance bar.
4. Seal Chamber, in the Gunsight's DoT area. Hover the keys on the Console's
   shoulder tab until one reads "Seal Chamber". If its tooltip says it is off,
   click it to turn it on (a click toggles it). Seals last 30 s (the ruler
   runs 0 to 30). Then:
   - Cast a seal. It shows the glyph in the seal's colour, a quick
     strike-up flicker, the drain, and the countdown.
   - In the last 5 s it flickers and reads EXPIRING.
   - At 3 s or less the RESEAL band lights.
   - At expiry it reads NO SEAL. "IN COMBAT" shows under it only while you
     are in combat, and in combat it pulses.
   - Cast a seal again, then cast Judgement. A ring pulses out from the
     glyph. The seal stays up after Judgement: the chamber keeps draining
     and does not drop to NO SEAL.
   - Judgement lane (the JUDGED side). Judge a target while a Crusader,
     Light, Wisdom or Justice seal is up:
     - The lane shows a bar and a chip with the Judgement icon, counting down
       40 s (10 s for Justice). It is coloured like the chamber: the current
       seal, red under NO SEAL. A white flash shows when it lands.
     - Judging under Righteousness, Command or Fury puts no bar up.
     - Switch target: the lane follows the new target at once. If that
       target is not judged, it shows the muted stacked letters NOT JUDGED
       (or NO DEBUFF), with a seal up. Under NO SEAL the empty lane shows no
       letters.
     - A dead target hides the lane. A revived target relights it without a
       flash.
     - After a loading screen the lane reads NOT JUDGED until you judge
       again. That is expected.
5. Look at the shoulder where it meets the Console's top line. It should look
   like part of the Console, with no notch and no bright seam.
6. Chat font. Chat text defaults to 14 pt. `/fschat size` prints the size and
   `/fschat size N` sets it (whole numbers, 10 to 24). A chat window where you
   picked a size earlier in Blizzard's font menu is left alone: use
   `/fschat size 14` to force it.
7. Send back: `/fsbug` with a note on what you were doing, sent as above, plus
   a screenshot of anything that looks off.

## Layout editor: /fsedit

Out of combat only. Close Blizzard Edit Mode first.

1. Type `/fsedit`. A cyan box with a name appears over each movable piece.
2. Drag a box. On release the piece moves there and snaps to the grid.
3. Click a box, then press the arrow keys: 1 unit per press, Shift+arrow moves one grid step. (Keys that are not arrows or Esc should still reach the game; report it if movement keys stop working.)
4. Right-click a box: that piece goes back to its default seat.
5. Esc leaves. Starting a fight leaves too and drops a drag in progress.
6. Check the minimap moves with its addon tray, the chat keeps its minimised and maximised states, and the pet panel (floating, not on the Console) follows the box.
7. `/reload`: every position holds. `/fsedit reset all`, then `/fsedit reset all confirm` puts everything back.
8. The Layout page of `/fsconfig` has the same controls: EDIT LAYOUT, snap on/off, grid size 4/8/16/32, and Reset all positions.

## Settings window: /fsconfig

Safe in combat. Esc, the X, or `/fsconfig` again closes it; with a menu or confirm box open, Esc closes only that. `/fsconfig profiles` opens a page directly.

1. Unit Frames: turn "Hide player frame" on. The player frame goes invisible and click-through at once (in combat it waits until combat ends). Turn it off again, then do the same for the target frame.
2. Gunsight HUD: switch "Your cast bar" off, then on. The piece fades with the console key light following. Check each of the eight pieces the same way: Your cast bar, Target cast bar, Next cast tile, DoT time axis, Soul shards, Proc posts, Buff reminders, Party frames. `/fsgun piece shard off` must flip the same switch while the window is open.
3. Gunsight HUD master switch: turn it off, `/reload`, and no Gunsight piece builds. Turn it back on and `/reload`.
4. Profiles: type a name under "New profile". It is created and switched to. Switch between profiles with "Profile in use": every switch in the other pages and every Gunsight piece follows. "This character" shows your name and realm.
5. Rename and Delete: Rename is off on Default. Delete lists only profiles that are neither Default nor the active one, and asks before deleting. "Copy from..." and "Reset profile" also ask first.
6. Hover each small ? icon: the explanation shows in the addon's tooltip. No settings text mentions the word "tape".
7. After `/reload`, the profile and every switch you set are still in place.

## Professions panel: /fsprof

Not yet checked in game. `/fsprof` shows or hides the panel and the choice survives `/reload`.

1. Click each profession row once (an Alchemy, Blacksmithing, Cooking or First Aid row, for example). That profession's window opens. Hovering a row names the profession and, on those rows, adds "Click to open".
2. A Mining row opens the Smelting window.
3. Herbalism, Skinning and Fishing rows do nothing when clicked: no window, no cast, no bobber. Their tooltip shows the name only.
4. In combat, type `/fsprof`. It prints that the change applies after combat, the panel stays as it is, and it flips when combat ends. Learn or drop a profession in combat (if you can) and the rows catch up after combat.
5. `/reload` with the panel hidden: it stays hidden. Mouse-down or mouse-up clicking should both work (the Interface action-button "on key down" option decides which).

## If the window does not open

Every report is also saved in the SavedVariables file. It is written on
`/reload` or logout. Send that file instead:

    World of Warcraft\_classic_beta_\WTF\Account\<ACCOUNT>\SavedVariables\forever-stuwave.lua

`<ACCOUNT>` is your account folder name.

## The "error was thrown and logged" line

If you see this in chat:

    Forever STUwave: error was thrown and logged (/fsbug to report)

the addon hit a Lua error, caught it, and kept the game running. No Lua error
popup is shown for it. It prints at most once every 10 seconds, with `(x3)`
style counts if it repeated. Run `/fsbug` right then so the report includes it.
You do not need `/console scriptErrors 1` for any of this.

If chat says "error log full, /fserr clear", new errors are counted but not stored, so run /fsbug, send it, then /fserr clear.

That only covers Lua errors. Blizzard's own "forever-stuwave has been blocked
from an action only available to the Blizzard UI" popup can still appear, and
the same chat line prints when it does. Run `/fsbug` for that too.

Errors from other addons are not hidden. They are left to the game's normal
handling, which under the default settings may mean no popup at all.

## What to send

- The .txt from `/fsbug`, or the SavedVariables file.
- One line on what you were doing (target, combat or not, which frame).
- A screenshot only if the problem is how something looks.

The report holds your class, level, zone, addon list, settings and recent
errors. Share the focused report first; inspect any larger SavedVariables file
before sharing it. The SavedVariables file holds more: the addon's settings, its probe
results and every stored report. Neither one holds chat text, and neither holds
your login or password.
