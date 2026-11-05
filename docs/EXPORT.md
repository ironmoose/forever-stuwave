# Character export

Forever STUwave keeps a snapshot of each character in the account-wide SavedVariables table `ForeverSTUwaveExport`, for tools outside the game (a character sheet page, a sim). Source: [`forever-stuwave/Modules/Diagnostics/CharacterExport.lua`](../forever-stuwave/Modules/Diagnostics/CharacterExport.lua); headless checks: `tools/characterexport-harness.py`.

## Where it lands

`<WoW root>/_forever_/WTF/Account/<ACCOUNT>/SavedVariables/forever-stuwave.lua`, next to `ForeverSTUwaveDB` and `ForeverSTUwaveErrorLog`. The client writes this file only on `/reload`, logout or exit, so a reader sees the snapshot taken before the last of those.

The file is Lua: `ForeverSTUwaveExport = { ... }`. Keys are `["name"] = value`, arrays are bare `{ a, b, }`, strings use Lua escapes (item links contain `|`). Parse it as Lua or with a small Lua table reader; do not treat it as JSON.

## When it is written

On login and `/reload` (about 4 seconds after the loading screen), level up, talent changes, gear changes, profession skill changes, and logout. Events within 2 seconds of each other produce one write. Nothing is written in combat: the write waits for combat to end, and a logout in combat keeps the previous snapshot. Nothing shows in chat. After a level up a "Reload to save" button shows (out of combat; a click runs `/reload` through a secure macro button, since the reload call itself is protected; a right click hides it) so the new level reaches the file without waiting for logout; the "Reload button after level up" switch on the Profiles page turns it off.

Settings, Profiles, Saved data, **Character snapshot** turns it off (setting `export.enabled`, default on). Turning it off stops new writes and leaves existing snapshots in place.

## Shape (schema 1)

```lua
ForeverSTUwaveExport = {
  schema = 1,
  characters = {
    ["Viktor Oldlight"] = { ... },   -- key: GetUnitName("player", true), first name plus surname
  },
}
```

A value the client did not give in plain form (a secret value, a missing API, an error) is absent, never zero. Optional means "may be absent".

### Character

| Field | Type | Notes |
|---|---|---|
| `schema` | number | 1 |
| `addonVersion` | string | `## Version` from the `.toc` |
| `savedAt` | number | Unix seconds (`GetServerTime`) |
| `savedAtText` | string | the same time, UTC, `2026-11-04T00:00:00Z` |
| `reason` | string | what triggered the write: `login` (also any later loading screen), `level`, `talents`, `gear`, `skills`, `combat end`, `logout` |
| `statsFrom` | number | present only when `stats` were kept from an earlier write because this one read every base stat as 0 (logout and /reload can); the `savedAt` of the write that read them |
| `errors` | array of strings, optional | sections whose reader threw (`identity`, `spec`, `stats`, `talents`, `professions`, `gear`) |
| `name` | string | full name, same as the key |
| `realm` | string | `GetRealmName()` |
| `guid` | string | player GUID |
| `race`, `raceToken` | string | `"Tauren"`, `"Tauren"` (`"Scourge"` for Undead) |
| `class`, `classToken` | string | `"Shaman"`, `"SHAMAN"` |
| `sex` | number | 2 male, 3 female |
| `level` | number | |
| `xp`, `xpMax` | number | current and needed for the level |
| `restedXp` | number, optional | absent when not rested |
| `money` | number | copper |
| `zone` | table | `name`, `subzone` (optional), `mapId` |
| `specIndex`, `specId`, `spec` | number, number, string | as the client reports. Forever has one talent tree per class and answers with the class name here, so the build lives in `talents`. |
| `stats` | table | below |
| `talents` | table | below |
| `professions` | table | below |
| `gear` | table | below |

### `stats`

| Field | Notes |
|---|---|
| `base.str/agi/sta/int/spi` | first return of `UnitStat` |
| `effective.str/agi/sta/int/spi` | second return of `UnitStat` (what the character sheet shows) |
| `attackPower`, `attackPowerBase` | `UnitAttackPower` base + buffs + debuffs, and base alone |
| `rangedAttackPower` | the same from `UnitRangedAttackPower` |
| `spellPower` | highest of `spellPowerBySchool` |
| `spellPowerBySchool` | `holy`, `fire`, `nature`, `frost`, `shadow`, `arcane` (`GetSpellBonusDamage` 2 to 7) |
| `healingPower` | `GetSpellBonusHealing` |
| `crit.melee`, `crit.ranged` | percent |
| `crit.spell`, `crit.spellBySchool` | percent; highest school, and each school |
| `hit.melee`, `hit.ranged`, `hit.spell` | percent: rating bonus plus modifier |
| `hit.meleeRating`, `hit.rangedRating`, `hit.spellRating` | raw ratings |
| `hit.meleeModifier`, `hit.spellModifier` | `GetHitModifier`, `GetSpellHitModifier` (talents and gear) |
| `armor`, `armorBase` | effective and base (`UnitArmor`) |
| `dodge`, `parry`, `block`, `blockValue`, `expertise`, `haste` | as the client reports |
| `attackSpeed.mainhand`, `attackSpeed.offhand` | seconds; offhand absent without one |
| `mp5`, `mp5Casting` | mana per 5 seconds out of and while casting (`GetManaRegen` x 5) |
| `healthMax`, `manaMax` | maximums; `manaMax` is power type 0 |
| `powerType`, `powerToken`, `powerMax` | the character's main resource (`MANA`, `RAGE`, `ENERGY`) |

### `talents`

| Field | Notes |
|---|---|
| `status` | `ok`, `partial` (some nodes unreadable, see `unread`), or `unavailable` |
| `configId` | `C_ClassTalents.GetActiveConfigID()` |
| `treeIds` | array of trait tree ids |
| `pointsSpent` | sum of `rank` over `list` |
| `list` | array, one entry per node with a rank above 0, in tree order |

Each `list` entry: `name`, `spellId`, `rank`, `maxRank`, `nodeId`, `entryId`, `definitionId`, `treeId`, `posX`, `posY` (node position in the talent frame). Ids are the stable key; `name` is localized and may be absent when the client gives no name.

### `professions`

`status` (`ok` or `unavailable`), then one table per learned slot: `primary1`, `primary2`, `archaeology`, `fishing`, `cooking`, `firstAid`. Each has `name`, `skill`, `max`, `skillLine` (the skill line id). An unlearned slot is absent.

### `gear`

One table per filled slot, keyed by slot name: `head`, `neck`, `shoulder`, `shirt`, `chest`, `waist`, `legs`, `feet`, `wrist`, `hands`, `finger1`, `finger2`, `trinket1`, `trinket2`, `back`, `mainhand`, `offhand`, `ranged`, `tabard`. An empty slot is absent.

| Field | Notes |
|---|---|
| `slot` | inventory slot id (1 to 19) |
| `itemId` | number |
| `link` | the full item link string |
| `enchantId` | optional, from the link |
| `gems` | optional array of gem item ids, from the link |
| `suffixId` | optional, random suffix from the link (can be negative) |
| `itemLevel` | `C_Item.GetDetailedItemLevelInfo`, else `GetItemInfo` |
| `name`, `quality` | from `GetItemInfo` |

`gear.incomplete` (optional number) counts items whose link, level or name the client had not loaded yet; the next write fills them in.

## Compatibility

New fields may be added within schema 1. A field that changes meaning or is removed bumps `schema`; readers should check it.
