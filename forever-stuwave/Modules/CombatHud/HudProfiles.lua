-- Forever STUwave: combat HUD class profiles. DATA ONLY, plus one pure helper, FS.HudProfiles.ClassSlot,
-- the single home of the "who owns the Gunsight DoT area" rule (see below).
--
-- Keyed by the class token UnitClass("player") returns as its second value. A class with no
-- entry gets no HUD. Spell keys are HudSpells.lua keys; HudLogic.lua interprets this table.
--
--   row        spell keys shown left to right. A spell the player does not know is dropped.
--   dots       key -> { pandemic = fraction, group = name, consumedBy = { keys } }.
--              pandemic: the DoT counts as "missing" once its remaining time is at or below
--              fraction * duration (refresh early). group: members are exclusive on one
--              target (a new bane replaces the old one). consumedBy: casting any listed
--              spell removes this DoT (Conflagrate consumes Immolate).
--   cooldowns  keys whose cooldown the row reports; each must also be in `row` (a rule that
--              needs a cooldown reads it through cooldownReady, which does not use this list).
--   channels   key -> { clipAfter = ticks }. The period and tick count come from the
--              dictionary (HudSpells.lua), the single source. clipAfter: the channel may be
--              cut once that many ticks have landed.
--   procs      key -> { aura = spell id, glow = colour name, overlaySpell = spell key,
--              label = text, side = "left" | "right" }. label and side are the Gunsight HUD's
--              proc rung (GunsightFrame.lua): the post on that side of the horizon and the
--              text above its tape; a proc with no side is not drawn there, and a profile
--              with no procs (priest) gets no rungs.
--              A proc with `ready = key` (a dictionary spell) is a COOLDOWN tracker instead:
--              it is active while that spell is off cooldown (CooldownState, so the global
--              cooldown does not darken it), false when the spell is unknown, nil when the
--              cooldown is unreadable; it has no aura or overlay source. Its icon is the
--              spell's own.
--              `needsTarget = true` on a `ready` proc keeps it dark unless the target is attackable (Judgement).
--              overlaySpell is the spell whose action-bar glow marks the proc (Shadow Trance
--              lights Shadow Bolt). Two sources, in order: the overlay glow (the
--              SPELL_ACTIVATION_OVERLAY_GLOW_SHOW/HIDE events and
--              C_SpellActivationOverlay.IsSpellOverlayed), then the out-of-combat aura read
--              of `aura`. Both are UNVERIFIED until the probe has run on Forever.
--   selfBuffs  { spell = key, kind = "form" | "pet" | nil (aura), warnBelow = seconds,
--              oocOnly = true }. A buff whose spell the player does not know is not reported
--              (a Holy priest never gets a Shadowform reminder).
--   resource   shards = { item = id } enables the shard count.
--   seals      Paladin seal data: { order = { keys }, duration = seconds, judge = { key = seconds } }.
--              Having it makes HudLogic keep the seal ledger (`state.seal`, `FS.Hud.GetSeals()` and
--              the `sealMissing` primitive). `order` is the display order of the seals the player
--              knows; `duration` is the length of any seal; `judge` is the Judgement debuff length
--              per seal: HudLogic records it on the target when our own Judgement lands under that seal
--              (`state.judged`); a seal absent from `judge` (Righteousness) records none.
--   dotLabel   { n = name, d = description }: how a display names this class's DoT lane. The reader is
--              ConsoleKeys.Label (the tooltip of the console's DoT key); nothing else reads it.
--   fillerOrder  "wand" (the default) or "spell". Rotation rules tagged `filler = "wand"`
--              or `filler = "spell"` are pulled out and re-inserted, together, at the place
--              of the first filler rule: wand rules first by default, spell rules first for
--              "spell". The wand leads by default on purpose (Parker: "my wand does great
--              dmg and it costs no mana"). A priest at Shadow 40+ can set "spell" to put
--              Mind Flay ahead of the wand; the wand still sits ahead of the last spell rule
--              (Smite), so it takes over when Mind Flay is unaffordable.
--   rotation   ordered rules, data only (swap the lists, no code change): the FIRST rule
--              whose spell is known, whose every `when` primitive returns exactly true and
--              which is affordable wins. A primitive that returns nil (value unreadable
--              under secrecy) skips the rule; it is never guessed, unless it is wrapped in
--              { "orUnknown", cond }, which reads nil as true (a range gate that must not
--              hide a suggestion when the range cannot be read). Affordability is
--              implicit in every rule: a candidate is skipped when IsSpellUsable says
--              usable is plain false or notEnoughMana is plain true, so rules never need
--              a { "usable", key } of their own.
--
-- 1.60.1 secrecy facts these rules are written against (probe-verified):
--   * UnitPower/UnitHealth are secret even out of combat, so resourceBelow,
--     playerHealthAbove and targetHealthBelow return nil and the rules that use them are
--     skipped. The research rotations below do not use them: "cannot afford a Shadow Bolt"
--     (notEnoughMana) stands in for low mana, and engagedFor (fight age) stands in for
--     "the target is nearly dead". Both are heuristics, marked [HEURISTIC].
--   * By-spell aura lookups return no values in combat, so the aura source of procActive
--     is nil in combat; only the overlay glow can light a proc there.
--
-- Rotations are the 2026-10-02 research pass (wowclassicforever.info client spell tables,
-- Wowhead and Method class guides). Forever kills take 10 to 15 s at L10 to L15, so a
-- spell worth more on a long fight is gated on engagedFor. Delete the engagedFor lines to
-- fall back to cooldown-only.
--
-- Pandemic: SW:P, Corruption and Immolate tick every 3 s, so refreshing at 15% remaining
-- loses at most one tick. Bane of Agony gets none (back-loaded ticks, let it finish).

local _, FS = ...

FS.HudProfiles = {}

-- The DoT area of the Gunsight HUD (deck key 6) is a CLASS slot: a Warlock and a Priest get the DoT time
-- tape, a Paladin gets the Seal module. This is the one rule for who owns it, shared by ConsoleKeys.lua (does
-- the key show) and GunsightDots.lua (does the tape draw), so the two cannot disagree. Returns "dots" for a
-- profile with a non empty `dots` table (a profile with dots AND seals keeps the tape), "seals" for a `seals`
-- table with no dots, nil for anything else (no profile, a profile that is not a table, neither field a table).
-- Pure: it only indexes the profile and walks it with `next`.
function FS.HudProfiles.ClassSlot(profile)
    if type(profile) ~= "table" then return nil end
    if type(profile.dots) == "table" and next(profile.dots) ~= nil then return "dots" end
    if type(profile.seals) == "table" then return "seals" end
    return nil
end

-- Priest. One list covers L4 to 39 (wand priest) and 40+ (Shadowform): an unknown spell is
-- skipped (Devouring Plague L20, Shadow Word: Death L32, Mind Flay and Shadowform talents).
FS.HudProfiles.PRIEST = {
    row = { "sw_pain", "dplague", "mind_blast", "swd", "mind_flay", "smite" },
    dots = { sw_pain = { pandemic = 0.15 }, dplague = {} },
    cooldowns = { "mind_blast", "swd", "dplague" },
    channels = { mind_flay = { clipAfter = 2 } },
    procs = {},
    selfBuffs = {
        { spell = "shadowform", kind = "form" },
        { spell = "fort", warnBelow = 60, oocOnly = true },
        { spell = "inner_fire", oocOnly = true },
        -- No Power Word: Shield here: it is not a maintained buff, so a "missing" reminder
        -- would be on permanently out of combat.
    },
    fillerOrder = "wand",
    rotation = {
        -- Form first: Shadowform is known and the player is not in it.
        { cast = "shadowform", when = { { "buffMissing", "shadowform" } } },
        -- Opener (Parker's habit; matches Method and Wowhead): the hard cast first. If Mind
        -- Blast is on cooldown at the pull, or the target is out of range, this rule skips
        -- and Shadow Word: Pain opens. The range gate is orUnknown: a range that cannot be
        -- read never hides the opener. Usable and mana are the implicit affordability check.
        { cast = "mind_blast", when = { { "freshTarget" }, { "cooldownReady", "mind_blast" },
                                        { "orUnknown", { "inRange", "mind_blast" } } } },
        { cast = "sw_pain", when = { { "dotMissing", "sw_pain" } } },
        -- Devouring Plague: 60 s cooldown, 24 s, big mana. Only on a target that has lived
        -- a while. [HEURISTIC]
        { cast = "dplague", when = { { "dotMissing", "dplague" }, { "cooldownReady", "dplague" },
                                     { "engagedFor", 6 } } },
        -- Mind Blast on cooldown (8 s, 5.5 s with Improved Mind Blast): guides say it
        -- replaces Smite whenever it is off cooldown.
        { cast = "mind_blast", when = { { "cooldownReady", "mind_blast" } } },
        -- Shadow Word: Death (L32): 15 s cooldown and a 10% max health backlash when it
        -- does not kill (DB2 / 60.tools research, verified). Player and target health are
        -- secret, so the kill-shot gate is unreadable: gate on fight age instead.
        -- [HEURISTIC]
        { cast = "swd", when = { { "cooldownReady", "swd" }, { "engagedFor", 8 } } },
        -- Shadowfiend is a mana tool; "cannot afford Mind Blast" is the only readable mana
        -- signal.
        { cast = "sfiend", when = { { "cooldownReady", "sfiend" },
                                    { "notEnoughMana", "mind_blast" }, { "inCombat" } } },
        -- Filler (see fillerOrder). Shoot is an auto-repeat, so while it runs the rules
        -- above still win the moment a DoT or Mind Blast is ready.
        { cast = "shoot", filler = "wand", when = { { "wandEquipped" } } },
        { cast = "mind_flay", filler = "spell", when = {} },
        { cast = "smite", filler = "spell", when = {} },
    },
}

-- Warlock. One merged list; `known` on a talent spell selects the spec bracket:
--   wrack known                    Affliction 40+ (Immolate dropped, Wrack is the filler)
--   incinerate / conflagrate known Destruction
--   soul_fire known                Demonology 48+ (Decimation)
-- Hard cast first, then instants (the priest opener's logic). Improved Corruption 5/5 makes
-- Corruption instant; before that it is a 2.0 s hard cast like Immolate.
FS.HudProfiles.WARLOCK = {
    row = { "corruption", "bane_agony", "immolate", "siphon", "shadow_bolt" },
    dots = {
        corruption = { pandemic = 0.15 },
        bane_agony = { group = "bane" },    -- no pandemic: an early refresh loses the late ticks
        bane_doom = { group = "bane" },
        -- drop consumedBy once Shadow and Flame is 5/5
        immolate = { pandemic = 0.15, consumedBy = { "conflagrate" } },
        siphon = { pandemic = 0.1 },
        wrack = {},                          -- a 6 s channel tracked like a DoT
    },
    cooldowns = {},    -- none of the warlock row spells has a cooldown the row reports
    channels = { drain_soul = {}, drain_life = {}, wrack = {} },
    procs = {
        -- Nightfall. The aura read is out of combat only, so in combat only the overlay
        -- glow can light it.
        shadow_trance = { aura = 17941, glow = "gold", overlaySpell = "shadow_bolt", label = "TRANCE", side = "left" },
        -- Decimation (Demonology): lights Soul Fire through the first Soul Fire rule below.
        decimation = { aura = 440873, glow = "red", overlaySpell = "soul_fire", label = "DECIMATION", side = "right" },
    },
    selfBuffs = {
        { spell = "demon_armor", oocOnly = true },
        { spell = "pet", kind = "pet", oocOnly = true },
    },
    resource = { shards = { item = 6265 } },
    fillerOrder = "wand",
    rotation = {
        { cast = "shadow_bolt", when = { { "procActive", "shadow_trance" } } },
        { cast = "soul_fire", when = { { "procActive", "decimation" } } },

        -- Opener and DoT upkeep.
        { cast = "immolate", when = { { "dotMissing", "immolate" },
                                      { "not", { "known", "wrack" } } } },
        { cast = "corruption", when = { { "dotMissing", "corruption" } } },
        { cast = "bane_agony", when = { { "dotMissing", "bane_agony" },
                                        { "dotMissing", "bane_doom" } } },
        { cast = "siphon", when = { { "dotMissing", "siphon" } } },

        -- Destruction: Conflagrate (about L29) needs Immolate on the target.
        { cast = "conflagrate", when = { { "cooldownReady", "conflagrate" },
                                         { "not", { "dotMissing", "immolate" } } } },
        -- Shadowburn: instant, 15 s cooldown, one shard, refunds the shard if the mob dies
        -- within 8 s. Only worth it near death; fight age is the proxy. [HEURISTIC]
        { cast = "shadowburn", when = { { "cooldownReady", "shadowburn" },
                                        { "shardsAtLeast", 2 }, { "engagedFor", 6 } } },
        { cast = "incinerate", when = { { "not", { "dotMissing", "immolate" } } } },

        -- Demonology 48+: Soul Fire is the Decimation execute button. Its under-35% health
        -- gate is unreadable, so the fight age stands in. [HEURISTIC]
        { cast = "soul_fire", when = { { "cooldownReady", "soul_fire" }, { "engagedFor", 7 } } },

        -- Affliction 40+: Wrack once the Shadow DoTs are up (it amplifies them +10% for its
        -- 6 s).
        { cast = "wrack", when = { { "dotMissing", "wrack" },
                                   { "not", { "dotMissing", "corruption" } } } },

        -- Mana. Mana is secret, so use "cannot afford a Shadow Bolt". Out of combat always;
        -- in combat only when there is no wand to fall back on (do not Life Tap with a mob
        -- on you).
        { cast = "life_tap", when = { { "notEnoughMana", "shadow_bolt" },
                                      { "not", { "inCombat" } } } },
        { cast = "life_tap", when = { { "notEnoughMana", "shadow_bolt" },
                                      { "not", { "wandEquipped" } } } },

        -- Shards. On Forever a kill always grants a shard and Drain Soul damage can too
        -- (client tooltip). The shard top-up sits before the wand; it stops at 3 shards.
        { cast = "drain_soul", when = { { "not", { "shardsAtLeast", 3 } } } },

        -- Filler: the wand first (free, about 30% spell power, Wowhead), Shadow Bolt when
        -- there is no wand.
        { cast = "shoot", filler = "wand", when = { { "wandEquipped" } } },
        { cast = "shadow_bolt", filler = "spell", when = {} },
    },
}

-- Paladin. Two cooldown trackers (Holy Strike on the left rung, learned at 6, and Judgement on the
-- right, known from 4; each lit while off cooldown, Judgement also needing an attackable target,
-- `needsTarget`) plus a seal ledger (`seals`, HudLogic `state.seal`) and a three rule rotation,
-- first true rule wins, sourced from the 2026-10-04 paladin research (design notes
-- design record):
--   1. Seal of Righteousness while no seal is up or the one up has 5 s or less left. An unknown
--      seal state (nil) skips the rule, never guessed.
--   2. Judgement while it is ready; it is off the global cooldown, so it leads Holy Strike. The
--      procActive link makes NEXT gold and folds in the attackable-target rule.
--   3. Holy Strike while it is ready, in melee range or the range unknown.
-- NOT PORTED yet (no rules for them): the Crusader judge-and-swap detour (L10+), Seal of Command
-- on a slow two-hander (L20+), Exorcism, Consecration, Hammer of Justice. UNVERIFIED in game:
-- every seal name and id except Righteousness and the Crusader, the aura reconcile on 1.60.1,
-- Holy Strike's id, cooldown and global cooldown status, Hammer of the Righteous sharing Holy
-- Strike's cooldown (not in the ledger), isActive during the global cooldown, and Judgement
-- reading ready with no seal up or out of range.
FS.HudProfiles.PALADIN = {
    row = {},
    dots = {},
    cooldowns = {},
    channels = {},
    procs = {
        hs = { ready = "hs", glow = "gold", label = "HOLY STRIKE", side = "left" },
        jd = { ready = "jd", glow = "gold", label = "JUDGEMENT", side = "right", needsTarget = true },
    },
    selfBuffs = {},
    seals = {
        order = { "sor", "sotc", "sofu", "soc", "sol", "sow", "soj" },
        duration = 30,
        -- Judgement debuff length per seal (HudLogic `state.judged`).
        judge = { sotc = 40, sol = 40, sow = 40, soj = 10 },
    },
    -- The reader is ConsoleKeys.Label (the tooltip of the console's DoT key).
    dotLabel = { n = "Target side", d = "Target debuffs and the Seal module beside the target cast bar" },
    rotation = {
        { cast = "sor", when = { { "sealMissing", 5 } } },
        -- procActive "jd" is "Judgement is off cooldown and the target is attackable"; it is what
        -- makes NEXT gold. An unknown range (nil) still shows NEXT, like the priest opener.
        { cast = "jd", when = { { "procActive", "jd" }, { "orUnknown", { "inRange", "jd" } } } },
        -- Melee range gates Holy Strike the same way.
        { cast = "hs", when = { { "procActive", "hs" }, { "orUnknown", { "inRange", "hs" } } } },
    },
}
