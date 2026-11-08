# Changelog

## 1.0.0-beta.2 (2026-11-08)

Class modules for four more classes, Questie support, and a round of minimap and HUD polish.

### New
- Class modules beside the Gunsight for Warrior, Priest, Mage and Hunter:
  - Warrior: a roaring helm with a rune ring for Battle Shout and Demoralizing Shout. A missing shout in combat or on an attackable target pulses its runes and glows the helm amber. Left click a helm to shout.
  - Priest: a round frost shield follows your Power Word: Shield (absorb light, Weakened Soul rim, click to shield), with Prayer of Mending beads and a party strip for the shields you keep on others.
  - Mage: a spec piece (Frost snowflake with Fingers of Frost, Arcane sigil with Arcane Blast stacks, Fire flame with Scorch stacks and the Fire Blast comet) and a ward for Ice Barrier or Mana Shield, click to cast.
  - Hunter: a lock-on scope with the auto shot swing on its rim, a gold plant zone for the last half second of the swing, range bands around your target, and a trap tracker.
- Class module background: a dark plate with the party box border behind the class module, so it reads on bright ground. "Class module background" on the Gunsight HUD page sets its opacity; 0 turns it off.
- Questie support:
  - Questie's quest tracker wears the STUwave panel (turn on its background in Questie's tracker options), and "STUwave" is offered in Questie's font pickers.
  - Questie's quest icon shows beside the STUwave target frame, and on STUwave nameplates it sits just left of the health bar. Our own "!" steps aside while Questie's nameplate icons are on.
  - The layout editor leaves the tracker alone while Questie's tracker is in use.
- "STUwave nameplates" switch (Unit Frames, Nameplates): turn our plates off to use the game's own. Applies live.
- A Settings key on the minimap opens the STUwave settings window.
- Hover the time on the data bar to see local and realm time.

### Changes
- Shaman: the shock tracker is a carved rune disc with a lightning rune, raised level with the totem heads. The zig-zag line under the poles is gone.
- The minimap shows coordinates only, in the bezel row beside the keys. The time lives on the data bar.

### Fixes
- The nameplate quest "!" no longer shows on players who share your quest.
- The quest timer keeps the game's own timer when the drawer has nothing to show.
- Tracker quest markers no longer blow up during the add animation.
- The error log records every blocked action with the addon blamed.

### Known issues
- Using an item from your bags is sometimes blocked with "forever-stuwave has been blocked from an action". Use the item from an action bar until this is fixed.
- The Hunter, Mage and Priest modules are new and lightly tested in game. Reports welcome.

## 1.0.0-beta.1 (2026-11-05)

First build for the WoW Forever release client. Beta until 1.0, which ships with the CurseForge listing.

### Release client
- Targets the release client: the `_forever_` folder and `Wow.exe`, interface 16001.
- Panel skins skip forbidden frames, so login no longer throws on one.
- The Shaman buff tab no longer warns "a combat state slot cannot be located" at login with no weapon imbue up.
- Reloads go through a secure `/reload` button, since this client blocks reloads started by addon code. The settings window's Reload button works again; `/fsreload` now points you to `/reload`.

### New
- Character snapshot: a silent per-character record (level, stats, professions, talents) in the `ForeverSTUwaveExport` saved variable, with an off switch. See [docs/EXPORT.md](docs/EXPORT.md).
- After a level up, an optional "Reload to save" button writes the snapshot to disk. It is off by default; turn it on with "Reload button after level up" on the Profiles page.
- The objectives tracker moves in the layout editor (`/fsedit`, or Layout in settings). The position is saved in Blizzard's Edit Mode layout; if a preset layout (Modern or Classic) is active, the first move copies it to an account layout named "STUwave".
- Two new keys on the console's shoulder: Quests opens or collapses the quest tracker, Chat opens or minimises the chat. While a key is on screen, its closed tracker or chat draws nothing at all. Both keys stay with the HUD off.
- Nameplate quest marker: an amber "!" on a mob your quests need, including classic quests the game's own check misses.

### Skins
- Close and text buttons: one STUwave X and one text button style across panels, popups, the Game Menu and the Looking For Group window.
- A shared scroll bar skin on every skinned panel.
- Looking For Group window skin.
- Cooldowns draw as a violet fill that recedes upward.
- Bag slots are ringed by item quality, with a dark violet ring on empty and Common slots.
- Quest timers hang under the minimap as a STUwave drawer: an LED countdown and a draining gauge per timer, cyan, then amber under a minute and pink under 15 seconds. The game's own timer window is hidden while it is on (switch: "Quest timer under the minimap").
- An opened mail letter gets its own panel instead of floating as bare text.
- The group finder eye sits beside the minimap on a STUwave key, drawn as our own neon eye that pulses while you are queued.
- The loss of control alert (stuns, fears, silences) is the Gunsight jam: target brackets snap closed on the spell icon, a ring of ticks runs down with the effect, and the word and seconds sit centred on a plate under it. The colour follows the effect type. The snap in has its own switch.
- Objectives tracker: one STUwave header reading the quest count, "quests (12/20)", with the chat's minus to collapse it; collapsed, it is a small bar you click anywhere to open. STUwave quest markers with hover and pressed looks.
- The "World refresh in N Minutes" notice is a STUwave panel.
- Tutorial tips and the Battle.net friend toast are STUwave panels.

### Fixes
- Buff reminders show when a buff is removed in combat.
- Target Debuffs can keep a fallen-off debuff as a red reapply reminder (on by default).
- The character snapshot keeps the last real stats when a logout or reload reads them all as 0.
- Long quest text in the map's quest log no longer shows through the rewards box.
- Chatting in a battleground no longer throws an error or repeats "players have joined the battle". Inside a match the chat tags fall back to the game's own look.
- The target's health and power bars no longer come up short under a long name.
- Player names and class badges on the unit frames no longer throw errors in a battleground.

### Known issues
- A bag item clicked in combat was blocked once (ADDON_ACTION_FORBIDDEN on UseContainerItem). The cause is not found yet. Keep potions on an action bar.
- The spellbook and the character window still show stock Blizzard art (the spellbook title is also cut off). Skins for both are next.
