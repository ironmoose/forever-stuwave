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

## Paladin: seals, auras, Seal module, chat font

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
4. Seal module, in the Gunsight's upper or lower area (pick "Class Module" for
   an area in the config window; the "Seal module" section at the end of this
   file has the full check). Cast a seal:
   - The tile shows the seal's icon (two letters only if the game gives no
     icon), its name and SEAL ACTIVE. The time left is large on the right and
     the bar drains left to right over 30 s.
   - At 3 s or less the amber RESEAL end of the bar lights, the fill and time
     go amber and the caption reads EXPIRING.
   - At expiry it reads NO SEAL and CAST A SEAL. In combat it pulses.
   - Cast Judgement on a target under Crusader, Light, Wisdom or Justice. The
     bottom row (Judgement icon chip, bar, time) counts down 40 s (10 s for
     Justice). Switch to an unjudged target and it dims and reads NOT JUDGED
     (NO DEBUFF under Righteousness, Fury or Command). A dead target empties
     it. The seal stays up after Judgement.
5. Look at the shoulder where it meets the Console's top line. It should look
   like part of the Console, with no notch and no bright seam.
6. Chat font. Chat text defaults to 14 pt. `/fschat size` prints the size and
   `/fschat size N` sets it (whole numbers, 10 to 24). A chat window where you
   picked a size earlier in Blizzard's font menu is left alone: use
   `/fschat size 14` to force it.
7. Send back: `/fsbug` with a note on what you were doing, sent as above, plus
   a screenshot of anything that looks off.

## Warrior: stance shoulder and stance keys

Use a Warrior with at least Battle Stance. Defensive and Berserker stance
slots stay empty until learned. Do a FULL client restart, not /reload.

1. Stance shoulder: with the Console on, the stances stand on the Console's
   top-left shoulder, the same place as the Paladin's seals, in the order
   Battle, Defensive, Berserker. A stance you have not learned leaves its
   slot empty. The block should look like part of the Console, with no seam.
2. Click a stance: it casts, and the active one is highlighted. Quick Keybind
   (Esc > Options > Keybindings) binds each stance button; the key follows the
   stance, not the slot.
3. Stance keys: bind a key to a stance, switch stance, `/reload` and zone
   through a loading screen. Each button shows ONE key label, never two drawn
   over each other. Report it with `/fsbug` if a second label
   returns, and say when it came back.
4. `/fsconsole off`: the stances go back to their own row (the old stance bar
   seat), `/fsconsole on` returns them to the shoulder. The switch waits for
   combat to end. `/fsedit` offers a box for the stance bar only while it is
   on its own row.
5. Other classes keep their stance bar as before (Druid forms, Rogue stealth).

## Layout editor: /fsedit

Out of combat only. Close Blizzard Edit Mode first.

1. Type `/fsedit`. A cyan box with a name appears over each movable piece.
2. Drag a box. On release the piece moves there and snaps to the grid.
3. Click a box, then press the arrow keys: 1 unit per press, Shift+arrow moves one grid step. (Keys that are not arrows or Esc should still reach the game; report it if movement keys stop working.)
4. Right-click a box: that piece goes back to its default seat.
5. A small LAYOUT EDIT panel with a DONE button sits top-centre while editing. DONE or Esc leaves; positions are already saved as you drop. Starting a fight leaves too and drops a drag in progress.
   The DONE bar can cover a box seated under it (buffs, minimap): a box is selected only by clicking it, so click its visible part, then use the arrow keys.
6. Check the minimap moves with its addon tray, the chat keeps its minimised and maximised states, and the pet panel (floating, not on the Console) follows the box.
7. `/reload`: every position holds. `/fsedit reset all`, then `/fsedit reset all confirm` puts everything back.
8. The Layout page of `/fsconfig` has the same controls: EDIT LAYOUT, snap on/off, grid size 4/8/16/32, and Reset all positions.
9. EDIT LAYOUT closes the settings window; DONE or Esc reopens it on the Layout page. Leaving after `/fsedit`, by a fight, or by Blizzard Edit Mode does not open it.

## Moving the tooltip

Out of combat for the editing; the tooltip itself follows in combat too.

1. Type `/fsedit` and drag the Tooltip box (bottom right, above the control deck) somewhere else, then DONE.
2. Hover a unit, an item and an action button: the tooltip shows there, growing up and left from the box's bottom right corner.
3. Open `/fsconfig` and hover a `?` icon: its tooltip still shows beside its icon, not at the Tooltip box.
4. `/reload`: the Tooltip box and the tooltip stay where you put them.
5. In `/fsedit`, right-click the Tooltip box (or run `/fsedit reset all`, then `/fsedit reset all confirm`): the tooltip returns to the bottom right.

## Settings window: /fsconfig

Safe in combat. Esc, the X, or `/fsconfig` again closes it; with a menu or confirm box open, Esc closes only that. `/fsconfig profiles` opens a page directly.

1. Unit Frames: turn "Hide player frame" on. The player frame goes invisible and click-through at once (in combat it waits until combat ends). Turn it off again, then do the same for the target frame.
2. Gunsight HUD: switch "Your cast bar" off, then on. The piece fades with the console key light following. Check each piece the same way: Your cast bar, Target cast bar, Target side areas, Soul shards, Proc posts, Buff reminders, Party frames, and under Player side My buffs and Next cast. `/fsgun piece shard off` must flip the same switch while the window is open.
3. Gunsight HUD master switch: turn it off, `/reload`, and no Gunsight piece builds. Turn it back on and `/reload`.
4. Profiles: type a name under "New profile". It is created and switched to. Switch between profiles with "Profile in use": every switch in the other pages and every Gunsight piece follows. "This character" shows your name and realm.
5. Rename and Delete: Rename is off on Default. Delete lists only profiles that are neither Default nor the active one, and asks before deleting. "Copy from..." and "Reset profile" also ask first.
6. Hover each small ? icon: the explanation shows in the addon's tooltip. No settings text mentions the word "tape".
7. After `/reload`, the profile and every switch you set are still in place.
8. Unit Frames, Panels: turn "Background grid" off. The perspective grid at the bottom of the screen disappears at once, in or out of combat, and the action bars stay. Turn it on and it returns. Switch to a profile with the opposite setting and it follows. With `/fsbars blizz` it stays hidden whatever the switch says; `/fsbars fs` brings it back only if the switch is on.

## Target bars and numbers: /fsconfig, Gunsight HUD page

Not yet checked in game. Mocked checks cover the sizes, the secret-safe numbers and the combat rules, not how it looks. With every control left alone the target box has a taller health rule than before (11 px, was 6), a 4 px resource rule, the bars as wide as the old 120% setting drew them, and no numbers.

1. Target a mob. Drag "Health bar height" and "Resource bar height": the two rules under the unit name get thicker and thinner live, the resource rule always one step under the health rule. Dragging, the mouse wheel and clicking the track all work, and the number to the right of the slider follows. At the top of the range, check the rules do not touch the divider or the spell line badly.
2. "Bar width": the default 100% is as wide as the old 120% was; 50% is about half of that, and 150% stretches the rules to at most the box text width. Use a short and a long unit name. A width you had saved before this change converts once per profile to the same look (old 120 reads 100, old 150 reads 125).
3. Turn "Show numbers" on. A health number and a resource number appear inside the target box, on one row under the two rules (health at the left end, resource at the right end); the box grows upward to make room. Try "Current", "Current / max" and "Percent" (the choice is dimmed while Show numbers is off). Check them in combat on a hostile target, where the values are hidden by the game: they must still show and update, and `/fsbug` should report no error. Say if Percent stays blank in combat, for either number.
4. A target with no resource (a mob with no mana) shows only the health number.
5. Switch profile, then `/reload`: every control and the look hold per profile. Do it all once during combat: the bars are plain frames, so each change applies at once and nothing is blocked.
6. Reset to the starting look: health 11 px, resource 4 px, width 100%, numbers off.

## Gunsight target side: /fsconfig, Gunsight HUD page

Not yet checked in game. Mocked checks cover which module sits in which area, the swap rule and the combat rules, not how it looks. Beside the target cast bar the horizon line splits two areas: upper (Target Debuffs Horizontal by default) and lower (Class Module by default). The design is `mockups/gunsight-modules-concepts-v7-2026-10-08.html`.

1. Open /fsconfig, Gunsight HUD. The page starts with Target side (Upper area, Lower area), then Target box tags, then Player side (My buffs, Next cast). Each group header has a ? icon; Target side's says Target debuffs shows only the debuffs you applied and the Class Module shows your class's own resource.
2. Each area dropdown offers Target Debuffs Horizontal, Target Debuffs Vertical, Class Module, Empty, in that order. Pick Class Module for the upper area: the lower area takes Target Debuffs Horizontal at once (the swap), and both modules move on screen. Pick Target Debuffs Vertical for the lower area while the upper holds the Class Module: no swap, the lower area changes style.
3. Pick Empty for an area: nothing draws there, no outline either (only `/fsgun debug` outlines the areas). Both areas Empty with the tags and My buffs off should look like the box did before this change.
4. Switch "Target side areas" in the Pieces list off, or press the Console's key 6: both areas hide together. The key now shows for every class, including one with no class module yet (a Mage shows Target debuffs only).
5. With no target, or a friendly or dead one, the Target Debuffs area is hidden; the Class Module stays. Retarget a hostile mob and it returns.
6. Switch profile, then `/reload`: both dropdowns and the modules in the areas hold per profile. Do it once in combat: the areas are plain frames and nothing is blocked.

### Target debuffs: rows, axis, time and stacks

Not yet checked in game. Mocked checks cover the layout, the time text, the combat rules and the data rules, not how it looks or what this client reports in combat. It is available to every class and shows only debuffs you applied.

1. Horizontal: Warrior on a hostile mob, cast Rend and Sunder Armor. Each debuff gets a row (icon, time, drain bar), at most five rows. Time reads whole seconds above 3 s ("13s") and tenths below ("2.6s"); the bar drains 30 s to 0 and turns amber at 3 s or less. Sunder Armor shows "x2", "x3" as it stacks.
2. Vertical: pick Target Debuffs Vertical. The existing time axis shows compressed (about 3.7 px a second), 26 px right of the target cast bar, with TARGET DEBUFFS above it. A Priest or Warlock chip slides down toward the amber band; a DoT that is not on the target shows dim at 0 only in combat.
3. In combat the numbers are an estimate: a cast that is resisted still counts, and refreshes that are not casts (a Rogue's poison procs, Deep Wounds) do not show until combat ends. A row with "--" has no known duration yet; it fills in after one fight on any mob with that debuff. Report a row that stays wrong after combat ends.
4. Paladin: with the Class Module (Seal) in an area, Judgement is not listed in Target debuffs; Holy Vengeance and Hammer of Justice are. Retarget: the list restarts for the new target.

### Class Module: shards and combo points

Not yet checked in game. Mocked checks cover the layout and the events, not how it looks. Design: `mockups/gunsight-modules-concepts-v7-2026-10-08.html`, states A, B, D and F.

1. Warlock: the Class Module area shows one shard glyph, the count and the caption SOUL SHARDS. At 0 shards the glyph is dim and the count reads 0. Create or delete a shard and the count follows.
2. Warlock: with the Class Module in an area, the count under your cast bar is gone. Set both areas to Empty and the glyph and count return under your cast bar; at 0 shards they show a dim glyph and a muted 0.
3. Rogue: the Class Module area shows five yellow pips, the lit count and the caption COMBO POINTS. Build combo points on a hostile target and the pips and the count follow; with no target, or a friendly or dead one, the area stays empty. Report it if the pips never light (the combo events are unverified on this client).
4. Druid: the same combo display appears in cat form only. Shift to caster or bear form and it clears; report it if it stays up or never appears in cat form (the form check reads the power type and is unverified on this client).
5. Any other class: the Class Module draws nothing.

## Professions panel: /fsprof

Not yet checked in game. `/fsprof` shows or hides the panel and the choice survives `/reload`. The "Professions panel" switch on the Unit Frames page of `/fsconfig` is the same setting, saved per profile. A hidden panel from before this update stays hidden once (it is copied into the active profile on first load, unless that profile already stores its own choice).

1. Click each profession row once (an Alchemy, Blacksmithing, Cooking or First Aid row, for example). That profession's window opens. Hovering a row names the profession and, on those rows, adds "Click to open".
2. A Mining row opens the Smelting window.
3. Herbalism, Skinning and Fishing rows do nothing when clicked: no window, no cast, no bobber. Their tooltip shows the name only. Unknown or non-English profession names are not clickable.
4. In combat, type `/fsprof`. It prints that the change applies after combat, the panel stays as it is, and it flips when combat ends. Learn or drop a profession in combat (if you can) and the rows catch up after combat.
5. `/reload` with the panel hidden: it stays hidden. A click opens the window once (it does not open and immediately close), with the action-button "on key down" option both on and off.
6. Open `/fsconfig`, Unit Frames: "Professions panel" shows the same state as the panel. Flip it, and `/fsprof` flips it back. In combat it waits until combat ends, like `/fsprof`.
7. Click the small pink glyph at the right end of the panel's title bar (hover: "Minimise"). The rows fold away and the panel collapses down: the title bar ends up where the panel's bottom edge was, like the chat's minimise. Hover again: "Restore"; click it and the full list grows back upward from the same bottom edge. `/fsprof` twice keeps the panel minimised. `/reload` keeps it minimised, and each profile keeps its own state.
8. In combat, click the glyph. It prints that the change applies after combat, the panel stays as it is, and it folds or unfolds when combat ends. Drag the panel in `/fsedit` while minimised: its bottom edge follows the drag and it stays minimised after Done.

## Nameplate quest icon

1. Accept a quest with kill or collect objectives and find its mobs: the "!" shows beside their names, and goes when the objective is done or the quest is turned in.
2. Collapse a zone header in the quest log; quest mobs under it should still show the !

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

## Seal module (Paladin class module, upper or lower area)

Needs a full client restart.
Pick the class module for the upper or lower Gunsight area in the config window, then check in BOTH areas:

1. The module fits the area: the seal tile (the seal's icon) and name with SEAL ACTIVE, the time left large on the right, a bar with 0, 15 and 30 under it, and the Judgement row (Judgement icon chip, bar, time) at the bottom. Nothing spills over the area's edges.
2. Cast a seal: the bar fills left to right and drains, the time counts down (whole seconds, tenths from 5 s). The amber RESEAL band is the 0 to 3 s end of the bar.
3. At 3 s or less the fill, the time and the caption go amber and read EXPIRING, and the band breathes. At expiry it reads NO SEAL and CAST A SEAL; in combat the tile and name pulse.
4. Judge a target under Crusader, Light, Wisdom or Justice: the row's bar and time count down from 40 s (10 s for Justice). Switch to an unjudged target: the row dims and says NOT JUDGED (NO DEBUFF under Righteousness, Fury or Command). A dead target empties the row.
5. Move the module to the other area (and change the screen scale): it re-seats inside the new area.

## Box tags: level and class, health percent, target of target

Not yet checked in game. Mocked checks cover the seats, the secret-safe text and the combat rules, not how it looks. Design: `mockups/gunsight-modules-concepts-v7-2026-10-08.html`, states A to F. The three tags (Level and class, Health percent, Target of target) are switches on the Gunsight HUD page under Target box tags, all on by default.

1. Target a hostile elite: a small tag on the top edge, left of KICK, reads L plus the level in white and ELITE in gold. A normal mob shows only the level, a rare shows RARE, a boss BOSS, a skull-level mob `??`. Switch target and the tag follows; level up on a target dummy of another level and it updates.
2. A tag on the bottom edge, left, shows the target's health percent in green and follows hits and heals, in combat too (the value is hidden by the game there; say if it stays blank).
3. A tag on the bottom edge, right, shows just the name of the target's target in white, no "ToT" prefix. Click it: you target that unit. With no target of target the tag is invisible and does nothing. Say what happens if you click the empty spot (not verified in game).
4. In combat: the target of target tag fades in and out and changes its name as the mob switches target, and a click on it targets that unit, including a mob that only turned on you after the pull started. The button is always there (shown and clickable) while its switch is on, so only its fade changes in combat; `/fsbug` should report no blocked action. Changing the screen scale in combat takes effect when combat ends.
5. Turn each switch off: its tag goes at once and the others stay. Turn "Show numbers" on (Target bars): the box grows upward, KICK and the level tag ride the new top, and the bottom tags stay put.
6. Switch profile, then `/reload`: the three switches hold per profile.

## Target bar numbers inside the box

Not yet checked in game. With numbers off the target box is exactly as before.

1. Turn "Show numbers" on: the box grows upward by about 9 px. Line 1, the rules, KICK and the level tag rise with the top edge; the divider, the spell line and the cast tile keep their place on screen. Health reads at the left end of the new row under the rules, the resource at the right end.
2. Change the rule heights: the box grows or shrinks to match. Turn numbers off: the box returns to exactly its old size and place.
3. Check "Current / max" with a large health pool: a long value is cut at the half row, not run into the other number. Say if it overlaps or looks too tight.
4. Toggle numbers during combat: the box grows at once and nothing is blocked.

## My buffs: /fsconfig, Gunsight HUD page

Not yet checked in game. Mocked checks cover the seats, the order, the pip rule and the combat rule, not how it looks. The plate sits outboard of the Next cast tile; the switch is My buffs under Player side. A buff you gave yourself has no pip; a buff cast by a party or raid member has a cyan pip.

1. With a few buffs up: a 164 px plate shows up to four of them as tiles with the time left under each (47m, 14s, 2h). Buffs without a timer show no time. The order is the order of the game's own buff row, not by time left.
2. Get a buff from a party member (for example Arcane Intellect from a mage): its tile gets a cyan pip at the top right. Your own buffs have none. If every buff shows a pip, or a party buff shows none, report it: the pip needs the buff's source, which the aura snapshot has to carry.
3. Enter combat with a short buff running: the times keep counting down (they are worked out from the stored end time), and a buff that runs out is dropped and the next one moves up. Report it if a new buff gained in combat does not appear until combat ends (expected: the list is frozen then).
4. Remove every buff: the plate disappears. Switch My buffs off: the plate goes; on, it returns.
5. Change the screen scale: the plate and its tiles re-seat.
