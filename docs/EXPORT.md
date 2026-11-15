# Character export

Forever STUwave keeps a snapshot of each character in the account-wide SavedVariables table `ForeverSTUwaveExport`, for tools outside the game (a character sheet page, a sim). Source: [`forever-stuwave/Modules/Diagnostics/CharacterExport.lua`](../forever-stuwave/Modules/Diagnostics/CharacterExport.lua); headless checks: `tools/characterexport-harness.py`.

## Where it lands

`<WoW root>/_forever_/WTF/Account/<ACCOUNT>/SavedVariables/forever-stuwave.lua`, next to `ForeverSTUwaveDB` and `ForeverSTUwaveErrorLog`. The client writes this file only on `/reload`, logout or exit, so a reader sees the snapshot taken before the last of those.

The file is Lua: `ForeverSTUwaveExport = { ... }`. Keys are `["name"] = value`, arrays are bare `{ a, b, }`, strings use Lua escapes (item links contain `|`). Parse it as Lua or with a small Lua table reader; do not treat it as JSON.

## When it is written

On login and `/reload` (about 4 seconds after the loading screen), level up, talent changes, gear changes, profession skill changes, bag changes, opening the bank (and its changes while open), closing the bank when a write is waiting, quest log changes and quest turn-ins, currency and reputation changes, a profession's trade skill window being read (see `professions`), and logout. Events within 2 seconds of each other produce one write. Nothing is written in combat: the write waits for combat to end, and a logout in combat keeps the previous snapshot. Nothing shows in chat. After a level up a "Reload to save" button can show (out of combat; a click runs `/reload` through a secure macro button, since the reload call itself is protected; a right click hides it) so the new level reaches the file without waiting for logout. The button is off by default: turn on the "Reload button after level up" switch on the Profiles page to get it.

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
| `reason` | string | what triggered the write: `login` (also any later loading screen), `level`, `talents`, `gear`, `skills`, `bags`, `bank`, `quests`, `currencies`, `reputations`, `actionBars`, `bindings`, `macros`, `recipes`, `combat end`, `logout` |
| `statsFrom` | number | present only when `stats` were kept from an earlier write because this one read every base stat as 0 (logout and /reload can); the `savedAt` of the write that read them |
| `kept` | array of strings, optional | sections this write read empty or torn (logout and /reload can: money and xp at 0, no gear, no zone, talents unavailable, no profession, no bag slots) and so kept from the last write: any of `money`, `xp`, `gear`, `zone`, `talents`, `professions`, `bags`, `quests`, `completedQuests`, `currencies`, `reputations`, `actionBars`, `macros` (the last six only on a logout write: an empty list is otherwise real) |
| `keptFrom` | number, optional | the `savedAt` of the write the `kept` sections came from |
| `errors` | array of strings, optional | sections whose reader threw (`identity`, `spec`, `stats`, `talents`, `professions`, `gear`, `bags`, `quests`, `currencies`, `reputations`, `actionBars`, `bindings`, `macros`) |
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
| `recipeCapture` | table, optional | the outcome of the latest trade skill window read, see `professions`; absent until a window has been opened with the addon on |
| `gear` | table | below |
| `bags` | table | below |
| `quests` | table | below |
| `currencies` | table | below |
| `reputations` | table | below |
| `actionBars` | table | below |
| `bindings` | table | below |
| `macros` | table | below |
| `completedQuests` | array of numbers, optional | every quest id the character has turned in, sorted (`C_QuestLog.GetAllCompletedQuestIDs`, else the keys of `GetQuestsCompleted`); absent when neither exists |
| `bank` | table, optional | same shape as `bags`; absent until the bank has been opened once with the addon on |
| `bankFrom` | number, optional | present when `bank` was carried from an earlier write (the bank is only readable while its window is open); the `savedAt` of the write that read it |

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

`status` (`ok` or `unavailable`), then one table per learned slot: `primary1`, `primary2`, `archaeology`, `fishing`, `cooking`, `firstAid`. Each has `name`, `skill`, `max`, `skillLine` (the skill line id). An unlearned slot is absent. When `GetProfessions` gives no slot, the slots are filled from the skill list instead (`GetSkillLineInfo`, the lines under the "Professions" and "Secondary Skills" headers, English client): the first two primaries, then fishing, cooking and first aid by name. Those entries have no `skillLine`.

#### Known recipes

A slot can also carry the profession's known recipes. They are only readable while that profession's trade skill window is open, so each is read when its window opens, when the window's list updates, and when a bag changes while it is open (the craftable counts follow the bags, at most one read every 3 seconds), then carried unchanged by every later write until the window is read again. The list survives writes made with no window open, a logout teardown and a new session. A slot whose window was never opened has none of these fields, and a slot whose profession changed (dropped, another learned) starts empty. Primaries, Cooking and First Aid are covered; Fishing and Archaeology have no recipe window.

| Field | Notes |
|---|---|
| `recipes` | array of known recipes, sorted by `name`; learned recipes only. An unreadable list, or one with no known recipe in it, never replaces the last real one |
| `capturedAt` | number, Unix seconds (`GetServerTime`) of the read the list came from; its own stamp, not the write's `savedAt` |
| `capturedAtText` | string, the same time, UTC |
| `capturedSkill` | number, the profession's skill at that read; `difficulty` and `numCraftable` are as of then |
| `recipesIncomplete` | number, optional: reagents with no cached item name at that read (their names are requested and the window is read again a few times); a later read fills them in |

Each `recipes` entry:

| Field | Notes |
|---|---|
| `name` | string, optional (localized) |
| `recipeId` | number, `C_TradeSkillUI`'s recipe id. This client calls it the recipe's spell id (the API arguments are named `recipeSpellID`), so it is the crafting spell's id and there is no separate spell id field |
| `skillLineAbilityId` | number, optional: the recipe's skill line ability id |
| `difficulty` | `orange`, `yellow`, `green` or `grey`, optional: `relativeDifficulty` (Optimal, Medium, Easy, Trivial) as the recipe list colours it at `capturedSkill` |
| `difficultyId` | number, optional: the client's own value, 0 to 3 in the order above |
| `numCraftable` | number, optional: how many can be made now from what the bags hold (`C_TradeSkillUI.GetCraftableCount`), at `capturedAt` |
| `outputItemId` | number, optional: the item it makes (absent for recipes with no output item, such as an enchant) |
| `reagents` | array, optional: the needed reagents, one entry per Basic reagent slot of the recipe's schematic (the optional modifying and finishing slots are not listed); absent when the schematic could not be read |

Each `reagents` entry:

| Field | Notes |
|---|---|
| `name` | string, optional: absent while the client has not cached the item |
| `itemId` | number. When a slot accepts several items (quality tiers) this is the first and `itemIds` lists them all |
| `itemIds` | array of numbers, optional: only when the slot accepts more than one item |
| `count` | number needed per craft |
| `owned` | number, optional: how many the bags hold at `capturedAt` (the bank is not counted); summed over `itemIds` |
| `currencyId` | number, only on a reagent paid in a currency (no `itemId`, `name` or `owned`) |

Example, a Cooking slot after its window was opened (values are illustrative):

```lua
["cooking"] = {
  ["name"] = "Cooking", ["skill"] = 40, ["max"] = 75, ["skillLine"] = 185,
  ["capturedAt"] = 1793750400, ["capturedAtText"] = "2026-11-04T00:00:00Z", ["capturedSkill"] = 40,
  ["recipes"] = {
    {
      ["name"] = "Roasted Boar Meat", ["recipeId"] = 2538, ["skillLineAbilityId"] = 9538,
      ["difficulty"] = "orange", ["difficultyId"] = 0, ["numCraftable"] = 5, ["outputItemId"] = 2681,
      ["reagents"] = { { ["name"] = "Chunk of Boar Meat", ["itemId"] = 769, ["count"] = 1, ["owned"] = 5 } },
    },
  },
},
```

Which windows are read. Only this character's own: a linked profession (another player's, from a chat link), a guild member's list, an NPC's crafting window and a window whose owner the client will not say are not recorded, and neither is a window for a profession the character does not have. Nothing is read in combat (a window opened in a fight is read after it, if it is still open), or with the **Character snapshot** switch off. A read only calls query functions: no filter, tab or profession is changed.

`recipeCapture` says what the latest read did, so an empty `recipes` can be explained:

| Field | Notes |
|---|---|
| `at`, `atText` | when the read was attempted (Unix seconds, UTC text) |
| `status` | `ok` (recorded), `empty` (no known recipe read, last list kept), `unmatched` (the open profession is not one of the character's), `linked`, `guild` or `npc` (not recorded), `unverified` (the client would not say whether it is the character's own), `unavailable` (the trade skill API or its list is missing), `error` (a reader threw; see `detail`) |
| `slot`, `name`, `skillLine` | the profession slot the window matched (for `unmatched`, the open profession's name and skill line) |
| `count` | recipes recorded |
| `failed` | optional: known recipes recorded without reagents because their schematic could not be read, or skipped because reading them threw |
| `detail` | optional, on `error`: the start of the error text |

Source: `C_TradeSkillUI` (`GetAllRecipeIDs`, `GetRecipeInfo`, `GetCraftableCount`, `GetRecipeSchematic`, with `GetBaseProfessionInfo` and `GetChildProfessionInfo` to match the window to its slot, and `IsTradeSkillLinked`, `IsTradeSkillGuild`, `IsTradeSkillGuildMember`, `IsNPCCrafting` for the guard). The client's API dump has no `GetNumTradeSkills`, `GetTradeSkillInfo`, `GetNumCrafts` or other old trade skill or craft calls, so there is no fallback to them. A window is matched to its slot by skill line (the base line, the expansion line or its parent), else by profession name.

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
| `stats` | optional: `C_Item.GetItemStats` on the link, so a random suffix counts. Keys as the client gives them (`ITEM_MOD_STAMINA_SHORT`, `ITEM_MOD_INTELLECT_SHORT`, ...), values numbers; armor is `RESISTANCE0_NAME`, also copied to `armor`. Absent when the item has none |

`gear.incomplete` (optional number) counts items whose link, level or name the client had not loaded yet; the next write fills them in.

### `bags` and `bank`

`bags` covers the backpack and the four bag slots (containers 0 to 4). `bank` covers the bank's own slots (container -1) and its bag slots (5 to 11), read only while the bank window is open; every other write carries the last bank read and sets `bankFrom`.

| Field | Notes |
|---|---|
| `slots` | total slots across the containers |
| `free` | empty slots |
| `items` | array, one entry per filled slot, in container then slot order |
| `incomplete` | optional number: items whose link or name the client had not loaded yet; the next write fills them in |

Each `items` entry:

| Field | Notes |
|---|---|
| `bag`, `slot` | container id and slot within it |
| `itemId` | number |
| `name` | from `GetItemInfo` |
| `count` | stack size |
| `quality` | 0 poor to 5 legendary |
| `itemLevel` | `C_Item.GetDetailedItemLevelInfo`, else `GetItemInfo` |
| `link` | the full item link string |
| `stats` | optional, as in `gear` |

### `quests`

`status` (`ok` or `unavailable`) and `list`, one entry per quest in log order (zone headers are not entries; they become `header`). From `C_QuestLog.GetInfo` and `GetQuestObjectives`, else the old `GetQuestLogTitle` and `GetQuestLogLeaderBoard`.

| Field | Notes |
|---|---|
| `questId` | number |
| `title` | string |
| `level` | number |
| `header` | the log header above it, usually the zone |
| `isComplete` | optional, `true` when ready to turn in |
| `failed` | optional, `true` when failed |
| `objectives` | array of `text`, `type` (`item`, `monster`, `event`, ...), `finished` (optional `true`), `numFulfilled`, `numRequired` (the old API path parses the two numbers from `text`) |

### `currencies`

`status` (`ok` or `unavailable`) and `list`, in the order of the character pane's currency tab (`C_CurrencyInfo.GetCurrencyListInfo`). Currencies under a header the player has collapsed in that tab are not listed (expanding it would change their UI).

| Field | Notes |
|---|---|
| `id` | currency id (from the info table, else parsed from `GetCurrencyListLink`) |
| `name` | string, e.g. `Merchant's Favor` |
| `quantity` | number held |
| `max` | optional cap (0 or absent: none) |
| `header` | the tab header above it |

### `reputations`

`status` (`ok` or `unavailable`) and `list`, in reputation pane order (`C_Reputation.GetFactionDataByIndex`, else `GetFactionInfo`). Headers become `header`; a header that has its own reputation is listed as a faction. Factions under a collapsed header are not listed.

| Field | Notes |
|---|---|
| `id` | faction id |
| `name` | string, e.g. `Durotar Supply and Logistics` |
| `standingId` | 1 Hated to 8 Exalted |
| `standing` | the client's label for it (`Friendly`, `Honored`, ...) |
| `value`, `max` | progress within the current standing, as the bar shows (`250` of `6000`) |
| `total` | raw reputation value |
| `header` | the pane header above it |

### `actionBars`

`status` (`ok` or `unavailable`), `bonusBarOffset` (the bonus bar page at save time: a Warrior's stance, 1 Battle, 2 Defensive, 3 Berserker), and `list`: every filled action slot 1 to 180 (`GetActionInfo`), in slot order. A Warrior's stance pages are slots 73-84 (Battle), 85-96 (Defensive) and 97-108 (Berserker).

| Field | Notes |
|---|---|
| `slot` | 1 to 180 |
| `type` | `spell`, `macro`, `item`, ... as the client reports |
| `id` | spell, macro or item id |
| `subType` | optional, the client's third answer |
| `name` | the spell, macro or item name, else the slot's own text |

### `bindings`

`status`, `set` (`GetCurrentBindingSet`: 1 account, 2 character) and `setName` (`account` or `character`), then:

| Field | Notes |
|---|---|
| `actionBar` | array of `command` (`ACTIONBUTTON1`-`12`, `MULTIACTIONBAR1BUTTON1` to `MULTIACTIONBAR8BUTTON12`) and `keys` (one or two, e.g. `SHIFT-F`); unbound commands are left out |
| `other` | array of `command`, `category` and `keys` for every other command that has a key (`GetBinding`) |

### `macros`

`status` and `list`: general macros (index 1 to 120) then this character's own (121 on), from `GetMacroInfo`.

| Field | Notes |
|---|---|
| `index` | the macro index |
| `scope` | `general` or `character` |
| `name` | string |
| `icon` | icon file id (or path) |
| `body` | the macro text |

## Compatibility

New fields may be added within schema 1. A field that changes meaning or is removed bumps `schema`; readers should check it.
