-- Forever STUwave: combat HUD spell dictionary. DATA ONLY.
-- Published spell IDs: https://www.wowhead.com/forever ; name resolution stays first.
--
-- Part of the class-agnostic combat HUD (HudSpells -> HudProfiles -> HudLogic). A profile
-- (HudProfiles.lua) names spells by KEY ("sw_pain", "corruption"); this table says what a
-- key is made of. HudLogic resolves a key to the player's own spell at runtime.
--
--   names     spell names, tried FIRST. A name resolves to whatever rank the player has,
--             and it is how own-cast events and aura scans are matched back to a key (the
--             client reports the cast RANK id, e.g. Shadow Word: Pain as 594, never the
--             589 a dictionary would pin). Never match a rank by a single id.
--   ids       fallback spell ids, highest rank first, used only when no name resolves.
--             Lists are fallback samples unless a complete rank range is stated. Published
--             Forever spell records are accepted; a key without `ids` resolves by name.
--   apply     seconds a DoT or buff lasts when applied (the ledger's duration). Verified
--             on Forever unless a comment says otherwise.
--   applyByRank  cast spell id -> seconds, for a spell whose duration depends on the rank
--             actually cast (Corruption); any other id uses `apply` (the top rank).
--   cooldown  the spell's own cooldown in seconds. HudLogic uses it only to tell a real
--             cooldown from the global cooldown (see CooldownState in HudLogic.lua).
--   cast      cast time in seconds (informational, the display may show it).
--   period, ticks  channel data: seconds between ticks and tick count. The single source
--             for it: a profile's `channels` entry names the key and adds only `clipAfter`.
--   self      true for a spell cast on the player or with no target (buffs, Life Tap,
--             Vampiric Embrace, summons). Casting one never marks the target as engaged.
--   offGcd    true for a spell that does not start the global cooldown (the wand). It also
--             never counts as a cast on the target (no fresh-target or fight-age effect).
--   seal      true for a Paladin seal. Casting one is a `self` cast (never a cast on the target)
--             that HudLogic additionally records as the active seal (`state.seal`, a ledger
--             of our own casts); `apply` is the seal's length in seconds.
--   judgement true for Paladin Judgement. HudLogic stamps `state.judgeAt` on each own cast and, when
--             the active seal has a `seals.judge` length in the profile, records the Judgement debuff
--             on the target (`state.judged`).
--
-- Spells that are exclusive on one target (the banes) are declared in the profile's `dots`
-- (`group`), not here.
--
-- ASCII only. Keep durations in seconds.

local _, FS = ...

FS.HudSpells = {
    -- Priest -----------------------------------------------------------------------------
    sw_pain    = { names = { "Shadow Word: Pain" }, ids = { 10894, 589 }, apply = 18 },
    dplague    = { names = { "Devouring Plague" }, apply = 24, cooldown = 60 },
    mind_blast = { names = { "Mind Blast" }, ids = { 10947, 8092 }, cast = 1.5, cooldown = 8 },
    swd        = { names = { "Shadow Word: Death" },
                   ids = { 1309636, 1309635, 1309633, 1309595 }, cooldown = 15 },
    mind_flay  = { names = { "Mind Flay" }, ids = { 18807, 15407 }, period = 1, ticks = 3 },
    smite      = { names = { "Smite" }, ids = { 585 } },
    sfiend     = { names = { "Shadowfiend" }, ids = { 401977 }, cooldown = 300 },
    ve         = { names = { "Vampiric Embrace" }, apply = 30, cooldown = 60, self = true },
    fort       = { names = { "Power Word: Fortitude", "Prayer of Fortitude" },
                   ids = { 1243, 21562 }, apply = 3600, self = true },
    inner_fire = { names = { "Inner Fire" }, ids = { 588 }, apply = 600, self = true },
    -- https://www.wowhead.com/forever/spell=17
    pw_shield  = { names = { "Power Word: Shield" }, ids = { 17 }, self = true },
    -- Shoot (wand): the no-mana filler; an auto-repeat with no cooldown, off the global
    -- cooldown. Resolved by name; the id is what the client reports for the cast.
    shoot      = { names = { "Shoot" }, ids = { 5019 }, offGcd = true },
    shadowform = { names = { "Shadowform" }, ids = { 15473 }, self = true },

    -- Warlock ----------------------------------------------------------------------------
    -- Corruption lasts 12/15/18 s for ranks 1/2/3+. The rank ids 172 (r1) and 25311 (r7)
    -- are the verified ends of the rank range; 6222 (r2) is from classic spell data and
    -- NOT verified on Forever (6223, 7648, 11671 and 11672 are ranks 3 to 6, all 18 s, so
    -- they need no entry). The out-of-combat aura reconcile corrects a wrong guess.
    corruption  = { names = { "Corruption" }, ids = { 25311, 172 }, cast = 2.0, apply = 18,
                    applyByRank = { [172] = 12, [6222] = 15 } },
    -- Not in the verified list: Agony, Doom and Siphon Life carry their classic durations.
    -- If Forever differs, the out-of-combat aura reconcile corrects the live expiration.
    bane_agony  = { names = { "Bane of Agony" }, ids = { 980 }, apply = 24 },
    bane_doom   = { names = { "Bane of Doom" }, ids = { 603 }, apply = 60 },
    bane_havoc  = { names = { "Bane of Havoc" }, ids = { 1225228 } },
    immolate    = { names = { "Immolate" }, ids = { 25309, 348 }, apply = 15 },
    conflagrate = { names = { "Conflagrate" }, ids = { 1293817 }, cooldown = 10 },
    siphon      = { names = { "Siphon Life" }, ids = { 18265 }, apply = 30 },
    shadow_bolt = { names = { "Shadow Bolt" }, ids = { 25307, 686 }, cast = 3.0 },
    -- https://www.wowhead.com/forever/spell=1454
    life_tap    = { names = { "Life Tap" }, ids = { 1454 }, self = true },
    -- https://www.wowhead.com/forever/spell=1120
    drain_soul  = { names = { "Drain Soul" }, ids = { 1120 }, period = 3, ticks = 5 },
    -- https://www.wowhead.com/forever/spell=689
    drain_life  = { names = { "Drain Life" }, ids = { 689 }, period = 1, ticks = 5 },
    -- https://www.wowhead.com/forever/spell=706
    demon_armor = { names = { "Demon Armor", "Demon Skin" }, ids = { 706, 687 }, self = true },
    -- Names only (the ids are NOT verified on Forever). Wrack is a 6 s Affliction channel,
    -- tracked as a DoT (apply) and shown as a channel (period, ticks).
    wrack        = { names = { "Wrack" }, apply = 6, period = 1, ticks = 6 },
    incinerate   = { names = { "Incinerate" } },
    shadowburn   = { names = { "Shadowburn" }, cooldown = 15 },
    soul_fire    = { names = { "Soul Fire" } },
    searing_pain = { names = { "Searing Pain" } },
    -- Pseudo entry for the "summon a pet" reminder: known when any summon is known.
    pet         = { names = { "Summon Imp", "Summon Voidwalker", "Summon Succubus",
                              "Summon Felhunter" }, self = true },

    -- Paladin ----------------------------------------------------------------------------
    -- Holy Strike ranks through level 30 (6/12/20/28); cooldown behavior is separate client evidence.
    -- https://www.wowhead.com/forever/spell=680
    hs = { names = { "Holy Strike" }, ids = { 680, 1866, 678, 679 }, cooldown = 10 },
    -- Judgement (spelled that way on Forever): id 20271 is verified in game; a 10 s cooldown
    -- that does not consume the seal. Not marked offGcd: that is unverified.
    jd = { names = { "Judgement" }, ids = { 20271 }, cooldown = 10, judgement = true },
    -- Seals last 30 seconds; name matching follows the learned rank. Wisdom is above the level-30 beta cap.
    sor  = { names = { "Seal of Righteousness" }, ids = { 21084 }, apply = 30, self = true, seal = true },
    sotc = { names = { "Seal of the Crusader" }, ids = { 21082 }, apply = 30, self = true, seal = true },
    -- https://www.wowhead.com/forever/spell=20163
    sofu = { names = { "Seal of Fury" }, ids = { 20163 }, apply = 30, self = true, seal = true },
    -- https://www.wowhead.com/forever/spell=20375
    soc  = { names = { "Seal of Command" }, ids = { 20375 }, apply = 30, self = true, seal = true },
    -- https://www.wowhead.com/forever/spell=20165
    sol  = { names = { "Seal of Light" }, ids = { 20165 }, apply = 30, self = true, seal = true },
    sow  = { names = { "Seal of Wisdom" }, apply = 30, self = true, seal = true },
    -- https://www.wowhead.com/forever/spell=20164
    soj  = { names = { "Seal of Justice" }, ids = { 20164 }, apply = 30, self = true, seal = true },
}
