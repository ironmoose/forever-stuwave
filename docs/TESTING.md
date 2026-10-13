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

### Priest probe (developer diagnostic)

Log in on a priest. This records what a priest UI could read on this client, out of combat and in combat, side by side. It only reads; it casts and clicks nothing.

1. Out of combat, type `/fsprobe priest`. It saves an out-of-combat snapshot and starts logging.
2. Play normally for a few minutes: pull a mob (the in-combat snapshot saves about 4 seconds into the fight), cast and wand, drink, shield yourself and a party member if you have one, and kill a mob or two. Typing `/fsprobe priest` again re-snapshots the state you are in, and keeps the logs. If you start it in combat, the out-of-combat snapshot follows when the fight ends.
   Run 2 setup: a party member in your group (the party1 rows are void without one), you holding Inner Fire and a Power Word: Shield (so Weakened Soul is up), Renew cast on the party member, and about 30 seconds idle after a mana cast (no casts, mana below max) so the five second rule and the tick phase show up in the power log. Also target a mob in combat: the snapshot records its classification and level to see how durable it reads. The logs now carry `powerFrequent` sampled to about one entry a second (`total` is the raw event count, `sampledOut` what was skipped) and `powerOther` for non-mana power events; the power logs hold 300 entries (about five minutes of the sampled ones), the others 50; a cost call that returns nothing is read as a free spell (`costAssumption` in the saved meta); every spell id in the snapshot records the name the client resolves it to (`spellName`). The AuraContainer matrix is not part of this probe.
3. `/fsprobe priest off` stops the logging (it stops by itself after 20 minutes). Then `/reload` or log out to save.
4. Send the `fsprobe.priest` table from `ForeverSTUwaveDB` in `WTF/Account/<id>/SavedVariables/forever-stuwave.lua`. It holds the account's settings too: strip those first.

The plain `/fsprobe` run adds the same snapshot part to its own out-of-combat and in-combat snapshots when the character is a priest. `/fsprobe reset` clears all of it.

### Shaman probe (developer diagnostic)

Make a fresh Shaman and level it a little. This records what a Shaman totem bar could read and do on this client. Do it at level 4 or higher, once the first Earth totem (Stoneskin) is learned; the other elements and Call of the Elements / Totemic Recall come later, so run it again as you learn them. Whatever cannot be checked yet because a spell is not known is listed by name in the chat and in `checks.notRun`; it is skipped, not failed. The snapshot and the logs read Blizzard's totem state and never change Blizzard's frames, but the snapshot does write to two hidden throwaway frames of its own (a Cooldown and a StatusBar, handed the totem duration object to see whether the client accepts it), so it is not strictly read only. The test strip below and `setslot` / `destroy` are the only things that click or call anything protected, and only when you type or click them. Recommended order: `/fsprobe shaman` first (steps 1 and 2), then `buttons` (step 3).

1. Out of combat, drop an Earth totem (keep the totem in the bags), then type `/fsprobe shaman`. It saves an out-of-combat snapshot (including a live totem), prints which spells it knows and which checks could not run, and starts 30 minutes of logging.
2. Fight a mob with the totem down (the in-combat snapshot saves about 4 seconds into the pull; the totem must still be up). Drop and let expire or dismiss a totem a couple of times; each `PLAYER_TOTEM_UPDATE` is logged with a readout. Typing `/fsprobe shaman` again while it is logging re-snapshots the state you are in and keeps the logs; typing it after `off` or the timeout starts a fresh record (new snapshots and logs) but keeps the earlier strip, `setslot` and `destroy` runs. If a totem slot reads secret in combat the chat and `checks.notRun` say "N of 4 totem slots unreadable (secret)" instead of claiming no totem was down. If the native totem bar is on screen at your level, leave it there.
3. Out of combat, type `/fsprobe shaman buttons`. A small purple "FSPROBE SHAMAN TEST STRIP (temporary)" appears just below screen centre, above the target cast bar, with three buttons: dismiss (left-click slot 1, right-click slot 2, shift-left-click slot 3, shift-right-click slot 4), a castsequence through your first two known totems (click it repeatedly; with only one totem known it repeats that one, for example Stoneskin twice; the sequence resets after 15 seconds or when you leave combat), and Totemic Recall once known. If the probe is not logging (after `off` or the timeout) the command re-arms the logging over your saved record and never replaces it. With a totem down click the dismiss button for the slot it sits in (Earth should be slot 2, but that is one of the things this records), and click the castsequence button. Do it out of combat, then again in a fight (the strip stays clickable in combat; it cannot be built or changed there). Each click is logged with the totem state before and after and the events that followed. `/fsprobe shaman buttons off` hides it, out of combat. In combat it can only fade the strip (alpha 0): the buttons stay clickable, invisible, until combat ends, and then they hide by themselves. The same holds for `/fsprobe shaman off`, the 30 minute timeout and `/fsprobe reset` typed or reached in combat.
4. If the native totem bar shows at your level, run `/fsprobe shaman setslot` yourself in combat (it picks another known totem for the Earth slot, using the native bar button's own action id when that button exists, and puts the old one back when the slot held a plain spell). If the slot was empty, held something else or could not be read, or if only one totem is known so the pick is the current one (a no-op that only shows whether the call is blocked), nothing is restored and the chat line says so: when it says the slot was left changed, set it back by hand. The chat line prints first. If the client prints ADDON_ACTION_BLOCKED, that is the result; note it. `/fsprobe shaman destroy` (optionally with a slot 1 to 4) calls `DestroyTotem` from addon code with a totem down; try it out of combat and once in combat the same way.
5. `/fsprobe shaman off` stops the logging (it stops by itself after 30 minutes) and hides the strip out of combat; in combat the strip is only faded and hides when combat ends. Then `/reload` or log out to save.
6. Send the `fsprobe.shaman` table from `ForeverSTUwaveDB` in `WTF/Account/<id>/SavedVariables/forever-stuwave.lua`. It holds the account's settings too: strip those first.

`/fsprobe reset` clears it too.

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

## Shaman: totem tab

Use a Shaman who knows at least one totem (Stoneskin is level 4). This adds
new files (an addon file, key bindings and textures), so do a FULL client
restart, not /reload. If your Shaman has the Call of the Elements spell
(level 20), check the set drop too.

1. The tab: with the Console on, six buttons stand on the Console's top-left
   shoulder, the same place as the Paladin's seals: Fire, Earth, Water, Air,
   Set drop, Recall. Totems you cannot use yet show a dotted outline with the
   level they open at (Earth 4, Fire 10, Water 20, Air 30, Set drop and Recall
   20) and are dimmed. The tab should look like part of the Console, with no
   seam. Ghost Wolf is still on the stance bar.
2. Left click an element button: it drops the totem shown on the button. Right
   click it: the totem goes away at once. Hover for the reminder text.
3. Change totem: click the small arrow above the button, or Alt-click the
   button (Alt-click must NOT drop a totem). A list of the totems you know for
   that element appears. Click one: the button now shows it and drops it. Try
   it in combat too: a pick made in combat is applied when the fight ends, and
   the button keeps showing the old totem until then. Alt-modified keybinds on
   the totem buttons (Alt, Alt+Shift, Alt+Ctrl) open this list instead of
   dropping a totem. Note if a pick ever does not stick (the button switching
   back, or a chat line saying the slot did not take the pick). Before you have
   Call of the Elements (under level 20) there is no totem bar to fill: the
   button casts the totem by name, a pick only takes effect out of combat, and
   no chat line is expected. Learning Call of the Elements, or a new totem,
   makes the tab try the totem bar once.
4. Log out and in: each element remembers its totem. If you also use the
   stock Totem Bar, a pick made there shows up on the tab.
5. Set drop (Call of the Elements, level 20): drops your set. At level 30,
   Shift-click drops the Call of the Ancestors set. Recall (level 20) takes
   your totems back.
6. Totem timer: with a totem down, its button fills with the element colour
   and drains. The cooldown swipe runs on the button after a drop. Report it
   with `/fsbug` if the timer never shows in combat.
7. Quick Keybind (Esc > Options > Keybindings) binds each of the six buttons.
   Bound keys show as the button's key label.
8. `/fsconsole off`: the tab goes back to sit above the stance bar, and
   `/fsconsole on` returns it to the shoulder. Other classes see no tab.

## Shaman: imbue and shield chips

Use a Shaman who knows Rockbiter Weapon and, from level 8, Lightning Shield. The Gunsight Class Module shows two small chips at its bottom edge: IMBUE on the left and SHIELD on the right. They live in the Class Module area beside the target cast bar (the lower area by default; `/fsconfig`, Gunsight HUD, picks it). Only the chips are drawn so far: the totem poles come later. This adds a new file, so do a FULL client restart, not /reload.

1. With no imbue on your weapon the left chip is amber and says IMBUE. With no Lightning Shield the right chip is amber and says SHIELD. A spell you have not learned yet shows no chip at all, not an amber one.
2. Cast Rockbiter Weapon on your weapon. The chip turns quiet gold, shows RB and the minutes left, for example 59m. Flametongue shows FT, Frostbrand FB and Windfury Weapon WF. The addon learns which letters go with which weapon enchant from your own casts, so after a restart an imbue you did not cast this session may show IM (or the one imbue you know) until you cast it once. Report any imbue that shows the wrong letters.
3. Cast Lightning Shield. The right chip turns quiet gold, shows LS and the number of orbs left. Get hit: the number should go down, and the chip should go amber when the last orb is gone.
4. Under five minutes left on the imbue, the chip and its time turn pink (the same pink as a buff about to expire). Under one minute the time counts in seconds. Let it run out: the chip turns amber and says IMBUE again.
5. In combat: the imbue time should keep counting down and never show a wrong value. The shield count may show a "~" in front (an estimate, because the game hides auras in combat); it should be right again once the fight ends. A "?" means the chip has nothing to go on yet. Cast an imbue or the shield in the middle of a fight and check the chip updates at once. A shield cast in combat stops showing after its ten minutes if nothing confirms it, and the chip then asks for the shield again.
6. Dual wield (two weapons): with imbues on both, the chip shows the one with less time left. With an imbue on only one weapon while the other hand holds a weapon, the chip is amber IMBUE until both are imbued. A shield or an empty off hand never triggers it.
7. With a Water Shield up instead of Lightning Shield, the right chip is not drawn (it does not nag).
8. Type `/reload` out of combat: the chips should come back with the right time. Report with `/fsbug` if a chip is wrong, and say what was on your weapon.

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
2. Gunsight HUD: switch "Your cast bar" off, then on. The piece fades with the console key light following. Check each piece the same way: Your cast bar, Target cast bar, Target side areas, Soul shards, Proc posts, Buff reminders, Party frames, and under Player side Next cast. `/fsgun piece shard off` must flip the same switch while the window is open.
3. Gunsight HUD master switch (not yet checked in game; mocked checks only): turn it off with a spell cast in progress. The whole Gunsight HUD disappears at once and the standard player and target cast bars (the pair below the character) take over, showing that cast. A "Reload to restore the classic HUD" line with a Reload button appears on the row; the classic combat HUD itself only returns after `/reload`. Turn it on: the HUD and its cast bars return and the standard pair goes quiet. Never two player cast bars, never none. Repeat the toggle several times, and once during combat: in combat the HUD fades by alpha and the final hide lands when combat ends. Log in with the master switch off and turn it on: the row asks for a `/reload` to build the HUD. `/fsedit` lists "Player cast bar" and "Target cast bar" handles only while the Gunsight is off.
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

1. Open /fsconfig, Gunsight HUD. The page starts with Target side (Upper area, Lower area), then Target box tags, then Player side (Next cast only; My buffs is deferred to the next release). Each group header has a ? icon; Target side's says Target debuffs shows only the debuffs you applied and the Class Module shows your class's own resource.
2. Each area dropdown offers Target Debuffs Horizontal, Target Debuffs Vertical, Class Module, Empty, in that order. Pick Class Module for the upper area: the lower area takes Target Debuffs Horizontal at once (the swap), and both modules move on screen. Pick Target Debuffs Vertical for the lower area while the upper holds the Class Module: no swap, the lower area changes style.
3. Pick Empty for an area: nothing draws there, no outline either (only `/fsgun debug` outlines the areas). Both areas Empty with the tags off should look like the box did before this change.
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

## Nameplate Target Mark: /stu targetmark

Not yet checked in game. An optional high-contrast mark above your current target's nameplate. Off by default; with it off the plates are unchanged.

Spec: three solid blocks side by side with no gaps, yellow (255,255,0), blue (0,0,255), yellow (255,255,0). Each block is 6 x 4 UI units, so the mark is 18 x 4, centered horizontally on the plate and sitting above the name, raid marker and debuff rows. The colors are flat: no glow, transparency or theme tint. It is drawn on the topmost level of the plate so nothing covers it. Only the plate of your current target shows it. The setting is saved per profile as `nameplates.targetMark`.

Commands: `/stu targetmark` toggles it, `/stu targetmark on` and `/stu targetmark off` set it, each printing the new state. `/fsplate targetmark [on|off]` does the same.

1. With the setting off, target a mob: no mark on any plate.
2. `/stu targetmark`: chat says "Target Mark on" and the mark shows above the target's plate. A plate that is not your target shows none.
3. Switch targets: the mark moves to the new target's plate. Clear the target: it goes.
4. Pull a mob so you are in combat, then switch targets and toggle the command. The mark follows and the command works in combat.
5. With a raid marker on the target and several debuffs on it, the mark stays clear of both, above them.
6. `/stu targetmark off`: the mark goes at once. `/reload` after turning it on: it is still on.

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
7. Right click the target box (the unit frames off): the standard target menu opens (Invite, Inspect, Whisper, Trade, Follow, Set Focus), the same as on Blizzard's target frame. Left click and left drag over the box still target, click to move and turn the camera; the mouse wheel still zooms; the box's cast icon still shows its tooltip. With no target a right click over the empty spot does nothing and a right drag still turns the camera. With a target, a right drag that STARTS over the box does not turn the camera (the right button is the menu there; left and middle pass through): start the drag outside the box. Check that this is the only place it happens, and say if it bothers you in play. In combat: acquire a target after the pull starts and right click it; turn the Target piece off mid fight and the invisible box keeps taking right clicks until combat ends (the mouse cannot be switched in combat); `/fsbug` should report no blocked action. Not verified in game: that left clicks really pass through (if they do not, the button stays off and one chat line says the right click menu is off), and that the client hides the button with no target.

## Target bar numbers inside the box

Not yet checked in game. With numbers off the target box is exactly as before.

1. Turn "Show numbers" on: the box grows upward by about 9 px. Line 1, the rules, KICK and the level tag rise with the top edge; the divider, the spell line and the cast tile keep their place on screen. Health reads at the left end of the new row under the rules, the resource at the right end.
2. Change the rule heights: the box grows or shrinks to match. Turn numbers off: the box returns to exactly its old size and place.
3. Check "Current / max" with a large health pool: a long value is cut at the half row, not run into the other number. Say if it overlaps or looks too tight.
4. Toggle numbers during combat: the box grows at once and nothing is blocked.

## My buffs: DEFERRED to the next release, skip these steps

The plate is hidden behind `FS.Features.myBuffs` (false by default, set at the top of `GunsightMyBuffs.lua`), and the My buffs row is not in /fsconfig. Do not test it this release; the steps stay for when the flag goes on. Nothing of it shows in game, and a saved "on" setting does nothing.

Not yet checked in game. Mocked checks cover the seats, the order, the pip rule and the combat rule, not how it looks. The plate sits outboard of the Next cast tile; the switch is My buffs under Player side. A buff you gave yourself has no pip; a buff cast by a party or raid member has a cyan pip.

1. With a few buffs up: a 164 px plate shows up to four of them as tiles with the time left under each (47m, 14s, 2h). Buffs without a timer show no time. The order is the order of the game's own buff row, not by time left.
2. Get a buff from a party member (for example Arcane Intellect from a mage): its tile gets a cyan pip at the top right. Your own buffs have none. If every buff shows a pip, or a party buff shows none, report it: the pip needs the buff's source, which the aura snapshot has to carry.
3. Enter combat with a short buff running: the times keep counting down (they are worked out from the stored end time), and a buff that runs out is dropped and the next one moves up. Report it if a new buff gained in combat does not appear until combat ends (expected: the list is frozen then).
4. Remove every buff: the plate disappears. Switch My buffs off: the plate goes; on, it returns.
5. Change the screen scale: the plate and its tiles re-seat.
