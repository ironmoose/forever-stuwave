# Changelog

## 1.0.0-beta.1 (2026-11-05)

First build for the WoW Forever release client. Beta until 1.0, which ships with the CurseForge listing.

### Release client
- Targets the release client: the `_forever_` folder and `Wow.exe`, interface 16001.
- Panel skins skip forbidden frames, so login no longer throws on one.
- The Shaman buff tab no longer warns "a combat state slot cannot be located" at login with no weapon imbue up.
- Reloads go through a secure `/reload` button, since this client blocks reloads started by addon code. The settings window's Reload button works again; `/fsreload` now points you to `/reload`.

### New
- Character snapshot: a silent per-character record (level, stats, professions, talents) in the `ForeverSTUwaveExport` saved variable, with an off switch. See [docs/EXPORT.md](docs/EXPORT.md).
- After a level up, a "Reload to save" button writes the snapshot to disk. It has its own off switch.
- Nameplate quest marker: an amber "!" on a mob your quests need, including classic quests the game's own check misses.

### Skins
- Close and text buttons: one STUwave X and one text button style across panels, popups, the Game Menu and the Looking For Group window.
- A shared scroll bar skin on every skinned panel.
- Looking For Group window skin.
- Cooldowns draw as a violet fill that recedes upward.
- Bag slots are ringed by item quality, with a dark violet ring on empty and Common slots.
- The quest timer wears the panel skin and draws above the objectives panel.
- An opened mail letter gets its own panel instead of floating as bare text.
- The loss of control alert (stuns, fears) is a STUwave plate.
- Tutorial tips and the Battle.net friend toast are STUwave panels.

### Fixes
- Buff reminders show when a buff is removed in combat.
- Target Debuffs can keep a fallen-off debuff as a red reapply reminder (on by default).
- The character snapshot keeps the last real stats when a logout or reload reads them all as 0.

### Known issues
- A bag item clicked in combat was blocked once (ADDON_ACTION_FORBIDDEN on UseContainerItem). The cause is not found yet. Keep potions on an action bar.
- The objectives tracker collapses to an empty panel rather than a small bar. A redesign is planned.
