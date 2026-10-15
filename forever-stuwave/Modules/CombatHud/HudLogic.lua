-- Forever STUwave: combat HUD logic layer (data and decisions only, no frames or textures).
--
-- Part of the class-agnostic combat HUD: HudSpells.lua (dictionary) -> HudProfiles.lua
-- (per class rules) -> this file. The display is a later task and consumes only:
--
--   FS.Hud.GetState()   -> { active, class, inCombat, targetEpoch,
--                            row = { { key, icon, missing, remaining, expiresAt, duration,
--                                      onCd, cdRemaining, proc, isNext }, ... },
--                            next = { key, icon, glow } | nil,
--                            buffsMissing = { { key, icon, expiring }, ... },
--                            aurasKnown = true | false,
--                            procs = { { key, glow, active }, ... },
--                            shards = n | nil,
--                            channel = { key, done, ticks, cut } | nil,
--                            seal = nil | false | { key, id, expiresAt, duration, castAt },
--                            judgeAt = number | nil,
--                            judged = nil | false | { key, appliedAt, expiresAt, duration } }
--                          Every status field is nil when it is UNKNOWN (never a guess).
--                          `seal` (profiles with a `seals` table, i.e. the Paladin) is the active
--                          seal: nil = unknown, false = no seal, else the seal and its absolute
--                          GetTime times; see SEALS below.
--                          `judgeAt` (same profiles) is the GetTime of our last own Judgement cast, nil
--                          before one (it survives death and a loading screen, like a cooldown).
--                          `judged` is the Judgement debuff on the CURRENT target: nil = unknown (also
--                          after a reset, until a Judgement is seen), false = none, else the seal it was
--                          cast under and its absolute times; see JUDGEMENT below.
--                          `targetEpoch` is a plain integer bumped on every PLAYER_TARGET_CHANGED:
--                          a consumer compares it between pushes to tell a target switch from a
--                          change on the same target (never the GUID, which stays file-local). It
--                          is part of the change detector, so a switch between two mobs with identical timers
--                          still pushes.
--                          `missing` and `remaining` of a DoT are an ESTIMATE from the
--                          own-cast ledger, not the target's real aura: a DoT that was
--                          resisted or missed stays "up" until it expires, because a
--                          successful cast event is all the client gives us in combat (the
--                          combat log and aura reads are secret). The out-of-combat aura
--                          reconcile corrects it once combat ends or the target changes.
--                          `expiresAt` (an absolute GetTime) and `duration` (the full length
--                          of the cast made) are set only on a DoT row that is up: the DoT
--                          scale moves a chip from expiresAt - GetTime() between pushes,
--                          which are coarse (the change detector floors `remaining`).
--   FS.Hud.Subscribe(fn) / Unsubscribe(fn)   fn(state) runs at once on Subscribe, then when
--                          the state changes (0.2s tick; no subscribers, no state work). A pushed
--                          state is a table the subscriber owns: it is never written again.
--   FS.Hud.Tick()       one throttled pass (the hidden OnUpdate frame calls it).
--   FS.Hud.Eval(cond) / FS.Hud.Primitives     the rule primitives (the harness uses them).
--   FS.Hud.GetProfile() the active profile table, or nil.
--   FS.Hud.GetSeals()   the profile's seals the player knows, in profile order, as plain
--                          { key, name, id } entries ({} for a class without seals).
--   FS.Hud.GetJudgement()  { judgeAt, remaining, key }: the last own Judgement cast time, and the
--                          seconds left and seal key of the current target's Judgement debuff.
--                          remaining is nil when unknown (secret target, no target), 0 with key nil
--                          when the target carries none. All plain numbers from our own cast times.
--
-- PRIMITIVES (dotMissing dotRemaining cooldownReady procActive buffMissing resourceBelow
-- shardsAtLeast playerHealthAbove targetHealthBelow wandEquipped freshTarget engagedFor
-- inCombat notEnoughMana inRange known sealMissing, and the wrappers `not` and `orUnknown` around any of
-- them) return true, false or nil. nil means "cannot be read right now" (secret value,
-- missing API, no target) and a rotation rule with any nil primitive is SKIPPED, never
-- guessed. `not` keeps nil as nil; `orUnknown` is the one explicit way to say that an
-- unreadable answer must NOT skip the rule (it reads nil as true, and passes true and false
-- through). The first rule whose spell is known, whose primitives are all true and which is
-- AFFORDABLE wins: every candidate is also skipped when IsSpellUsable says usable is plain
-- false or notEnoughMana is plain true (an unreadable answer never skips), so rules carry no
-- usable checks of their own. freshTarget is true until our first harmful own cast on the
-- target (a wand shot does not count); engagedFor(sec) is true once that first cast is at
-- least sec seconds old (a fight-age proxy for "the mob is durable", since health is secret).
-- A target found carrying our DoT out of combat counts from that aura's application time.
--
-- SECRECY (check-verified on 1.60.1):
--   * issecretvalue is checked (pcall'd; a missing or throwing check counts as secret)
--     before any API result is compared, indexed or used in arithmetic.
--   * By-spell aura lookups return ZERO values in combat, and GetAuraDataByIndex throws, so
--     the aura source of procActive and every aura scan (buffs, the DoT reconcile) are
--     out-of-combat only and nil in combat. C_Secrets.ShouldAurasBeSecret() true also
--     blocks them. A scan that returns zero values at index 1 is unreadable (nil), never
--     an empty list. UNCHECKED: whether an EMPTY aura list reads as one nil or as zero
--     values out of combat (see the open question in ScanAuras).
--   * GetSpellCooldown.isActive is plain in combat. startTime and duration are secret in
--     combat and plain out of it.
--   * UnitPower and UnitHealth are secret even out of combat, so resourceBelow,
--     playerHealthAbove and targetHealthBelow are nil on this client; they work unchanged
--     on a client that answers plain.
--   * DoT state comes from an own-cast LEDGER, not from auras: UNIT_SPELLCAST_SUCCEEDED for
--     the player plus the target GUID captured when the cast was SENT or STARTED (so a
--     retarget during a cast cannot move the DoT onto the new target).
--   * Ranks: casts report the rank id actually cast, so everything is matched by spell NAME
--     (or any dictionary id), never by one pinned rank id.
--
-- COOLDOWNS. Sources, in order (CooldownState):
--   1. A plain isActive of false is trusted: ready. A plain isOnGCD true is honoured: ready.
--   2. Plain startTime and duration (out of combat) are exact: a duration of at most GCD_WINDOW is
--      the global cooldown alone (ready), a longer one is a real cooldown whose remaining time is
--      start + duration - now. Such a read also LEARNS two things: the spell's cooldown length (so a
--      talent like Improved Mind Blast is the client's number, not the dictionary's; skipped when the
--      cooldown did not start at our own cast, e.g. a lockout) and the cooldown's end (kept for combat).
--   3. In combat (VERIFIED on 1.60.1, priest check 2026-10-09, two runs) startTime and duration are
--      secret while isActive stays plain. Run 1 saw a plain true for every spell (taken between wand
--      shots, unexplained); run 2 saw a plain FALSE for 16 of 18 spells and a true only for the Mind
--      Blast just cast. So a plain false is trustworthy evidence of "ready" (step 1, whatever the ledger
--      says), while a plain true is not (it may be stuck, or only the global cooldown): with a plain true
--      the CAST LEDGER decides. A secret isActive is unreadable (nil), never guessed from the ledger.
--      The player's own spell ids and cast times are plain (UNIT_SPELLCAST_SUCCEEDED, lastCastOf). A spell is ready
--      unless now is before the later of (our last cast + its cooldown length) and any end learned in
--      a plain read; the remaining time is that difference. The length is the learned one, else the
--      dictionary `cooldown`, else 0 (a spell with no cooldown of its own is always ready). The global
--      cooldown needs no special case: the ledger says "elapsed", so such a spell stays ready through
--      the GCD of another cast, and a wand shot or a different spell never frees one we cast.
--      The cost: a cast the ledger did not see (a /reload mid-fight, a cooldown started before the
--      addon loaded and never seen in a plain read, an item or macro effect that resets it) reads
--      READY. That fails toward suggesting the spell; if it is really down the cast simply does not
--      go off. Our cast times survive a loading screen (GetTime is monotonic), only a /reload loses them.
--
-- SEALS (Paladin, a profile with `seals`). The active seal is a LEDGER of our own casts, because
-- aura reads are blocked in combat: UNIT_SPELLCAST_SUCCEEDED for the player carries a plain spell id
-- (the dictionary marks a seal `self` AND `seal`; the seal is recorded BEFORE the self-spell early
-- return, and a seal is never a cast on the target). A new seal replaces the old one and lasts
-- `profile.seals.duration` (30 s) from the cast. A seal past its expiry reads false, computed on
-- read from our own plain numbers. Out of combat, when auras are readable, a reconcile scans the
-- player's HELPFUL auras (the cached PlayerAuras scan, dirtied by UNIT_AURA("player"),
-- PLAYER_ENTERING_WORLD and PLAYER_REGEN_ENABLED) and takes the seal aura's own expiry and duration
-- when plain; a readable scan with no seal aura is false; an UNREADABLE scan (zero values, combat,
-- secret) changes nothing, but ZERO values at index 1 of the seal's own scan read as an EMPTY list (a
-- buffless paladin is false, not unknown). A seal we cast under 1 s ago survives a readable scan that
-- does not list it (aura lag, an unknown name), and an aura of the same seal whose expiry is within 1 s
-- of the ledger's keeps the cast entry (castAt and the cast's rank id), so a cast pushes once; a
-- disagreeing aura replaces it and the id becomes the aura's. A seal aura whose timing is secret is
-- present but unknowable: the ledger entry of the same seal is kept, otherwise the state is unknown.
-- PLAYER_DEAD sets false; the next UNIT_AURA or PLAYER_REGEN_ENABLED rescans. PLAYER_ENTERING_WORLD
-- and a /reload leave it unknown (nil) until the reconcile reads it.
-- `sealMissing(sec)` is true with no seal or at most `sec` left, false with more left, nil when
-- unknown (a rotation rule on it is then skipped, never guessed). VERIFIED in game for Seal of
-- Righteousness (live inspect, level 7): the aura id equals the cast id 21084 and sourceUnit is "player".
-- UNVERIFIED: the other seal names and ids.
--
-- JUDGEMENT (a dictionary spell with `judgement`). Judgement is a cast on the target, so it runs the
-- normal own-cast path; it does NOT consume the seal (the seal ledger is untouched). Every own cast
-- stamps `judgeAt` (even with no target); like lastCastOf it survives death and a loading screen, since
-- a spell cooldown does. When the
-- active seal is a plain ledger entry whose key has a `profile.seals.judge` length (sotc, sol, sow,
-- soj; Righteousness has none), the landed debuff goes into the per-target ledger under the key
-- "judged": { expires, duration, key = the seal at cast time, appliedAt }, written through the same
-- SetEntryAt as a DoT (so it lands on the target the cast was sent at, and a retarget cannot move it).
-- An unknown, absent or expired seal records judgeAt only. Like a DoT it is an ESTIMATE (a resisted
-- Judgement reads as up), survives the player's death, and is dropped with the ledger on
-- PLAYER_ENTERING_WORLD. After that reset `judged` is UNKNOWN (nil) until a Judgement cast is seen: the
-- aura reconcile never writes it, so a mob may still carry ours; "none" (false) needs a cast seen since.
-- The debuff itself is never read from an aura. The only aura read is the seal's own guarded
-- out-of-combat reconcile, which Seal.OnJudge triggers through Seal.Read when the seal is dirty.
--
-- PROCS have two sources, tried in order: the spell-activation overlay glow (the
-- SPELL_ACTIVATION_OVERLAY_GLOW_SHOW/HIDE events with a plain spell id, then
-- C_SpellActivationOverlay.IsSpellOverlayed), then the out-of-combat aura read. A profile
-- proc names the spell that glows in `overlaySpell`. The overlay data is UNVERIFIED until
-- the in-game check; a plain false from the overlay API is trusted in combat, but out of
-- combat a plain aura read overrides it.
-- A proc with `ready = key` is a cooldown tracker instead (Paladin Holy Strike / Judgement): it
-- reads CooldownState, so the cast ledger above keeps it lit through the global cooldown. UNVERIFIED
-- in game: Hammer of the Righteous sharing Holy Strike's
-- cooldown (not in the ledger, so casting it does not darken the rung).

local _, FS = ...

local Hud = {}
FS.Hud = Hud

local Spells = FS.HudSpells or {}
local Profiles = FS.HudProfiles or {}

local TICK = 0.2             -- seconds between passes of the hidden OnUpdate frame
local PRUNE_EVERY = 10       -- seconds between sweeps of expired ledger entries
local MAX_AURAS = 40         -- aura index scan limit
local CHANNEL_GRACE = 0.5    -- a channel with no STOP event expires this long after its end
local MAX_CHANNEL = 60       -- a re-read channel end further out than this is not believed
local GCD_WINDOW = 1.6       -- a cooldown no longer than this is the global cooldown alone
local PENDING_TTL = 60       -- seconds a cast's captured target is kept without a verdict

local EMPTY = {}    -- read-only stand-in for an absent list, so the tick never builds one
local profile, classToken
local setupDone = false
local Prims = {}

-- Secret-safe helpers -------------------------------------------------------------------

-- True when v may be touched. A missing or throwing issecretvalue counts as secret.
local function Plain(v)
    local ok, secret = pcall(issecretvalue, v)
    return ok and secret == false
end

local function PlainOf(v, kind)
    if Plain(v) and type(v) == kind then return v end
    return nil
end

local warned = {}
local function LogOnce(key, msg)
    if warned[key] then return end
    warned[key] = true
    if FS.LogDegradeOnce then pcall(FS.LogDegradeOnce, "hud_" .. key, tostring(msg)) end
end

local function Now()
    local ok, t = pcall(GetTime)
    if ok then return PlainOf(t, "number") end
    return nil
end

-- pcall's results as (ok, number of values returned, first value): lets a caller tell a
-- function that returned nothing from one that returned nil.
local function pack(ok, ...) return ok, select("#", ...), (...) end

-- Fails closed: a throwing or secret answer counts as "in combat".
local function InCombat()
    local ok, r = pcall(InCombatLockdown)
    if not ok or not Plain(r) then return true end
    return r and true or false
end

-- Aura reads are allowed only out of combat and when the client does not say they are secret.
local function AurasReadable()
    if InCombat() then return false end
    local fn = C_Secrets and C_Secrets.ShouldAurasBeSecret
    if fn then
        local ok, r = pcall(fn)
        if not ok or not Plain(r) or r ~= false then return false end
    end
    return true
end

-- Spell dictionary lookups -------------------------------------------------------------

local nameKey, idSet = {}, {}
for key, def in pairs(Spells) do
    for _, n in ipairs(def.names or {}) do nameKey[n] = key end
    for _, id in ipairs(def.ids or {}) do idSet[id] = key end
end

-- name, id, icon of a spell given its name or id; plain values only.
local function SpellInfo(x)
    local fn = C_Spell and C_Spell.GetSpellInfo
    if fn then
        local ok, info = pcall(fn, x)
        if ok and Plain(info) and type(info) == "table" then
            return PlainOf(info.name, "string"), PlainOf(info.spellID, "number"),
                PlainOf(info.iconID, "number")
        end
        return nil
    end
    if GetSpellInfo then
        local ok, name, _, icon, _, _, _, id = pcall(GetSpellInfo, x)
        if ok then
            return PlainOf(name, "string"), PlainOf(id, "number"), PlainOf(icon, "number")
        end
    end
    return nil
end

-- The three "is this spell id known" APIs, in order; a client without one skips it.
local function KnownFn(i)
    if i == 1 then return IsPlayerSpell end
    if i == 2 then return IsSpellKnown end
    return C_SpellBook and C_SpellBook.IsSpellKnown
end

-- true / false / nil (cannot tell) for "does the player know this spell id".
local function IsKnownId(id)
    local sawFalse, unreadable = false, false
    for i = 1, 3 do
        local fn = KnownFn(i)
        if fn then
            local ok, r = pcall(fn, id)
            if ok and Plain(r) then
                if r then return true end
                sawFalse = true
            else
                unreadable = true
            end
        end
    end
    if unreadable then return nil end
    if sawFalse then return false end
    return nil
end

local spellCache = {}
local idKey = {}
-- A spell that cannot be told known or not is never cached (asked again next tick), but its result
-- table is kept per key and refilled, so asking again does not allocate.
local unknownRes = {}
local resIndeterminate, resFirstIcon

local function TryResolve(x)
    local name, id, icon = SpellInfo(x)
    if type(x) == "number" then id = id or x end
    if not id then return nil end
    resFirstIcon = resFirstIcon or icon
    local known = IsKnownId(id)
    if known == nil then resIndeterminate = true end
    if known then return { id = id, name = name, icon = icon, known = true } end
    return nil
end

-- key -> { id, name, icon, known }. known is true, false or nil (could not be determined,
-- not cached). A name resolves to the player's current rank; ids are the fallback.
local function ResolveSpell(key)
    local def = Spells[key]
    if not def then return nil end
    local hit = spellCache[key]
    if hit then return hit end
    resIndeterminate, resFirstIcon = false, nil
    local found
    for _, n in ipairs(def.names or EMPTY) do
        found = TryResolve(n)
        if found then break end
    end
    if not found then
        for _, id in ipairs(def.ids or EMPTY) do
            found = TryResolve(id)
            if found then break end
        end
    end
    if found then
        spellCache[key] = found
        return found
    end
    if resIndeterminate then
        local res = unknownRes[key]
        if not res then res = {}; unknownRes[key] = res end
        res.icon, res.known = resFirstIcon, nil
        return res
    end
    local res = { icon = resFirstIcon, known = false }
    spellCache[key] = res
    return res
end

-- Any rank of a dictionary spell -> its key. Matches by dictionary id, else by name.
local function KeyForSpellID(id)
    if not PlainOf(id, "number") then return nil end
    local k = idKey[id]
    if k ~= nil then return k or nil end
    k = idSet[id]
    if not k then
        local name = SpellInfo(id)
        if not name then return nil end   -- undetermined: do not cache a miss
        k = nameKey[name]
    end
    idKey[id] = k or false
    return k
end

-- Aura scans (out of combat only) ------------------------------------------------------

-- A list of { name, id, expires, duration, source } for plain auras, or nil when auras cannot be
-- read. A scan whose first index returns ZERO values is unreadable (nil), not an empty list:
-- an empty list would read every buff and DoT as missing.
--
-- OPEN QUESTION (UNCHECKED, needs a live /fscheck check; behaviour left unchanged on purpose):
-- out of combat, on a unit with NO matching auras at all, does GetAuraDataByIndex(unit, 1,
-- filter) return one nil or ZERO values? If it returns zero values, the `i == 1 and n == 0`
-- rule below reads a clean list as unreadable, which would suppress the Fortitude / Inner
-- Fire reminders on an unbuffed player (exactly when they matter) and skip the DoT
-- reconcile on a clean target. The check: out of combat, strip the buffs or target a mob
-- with no debuffs of ours, then count the values returned at index 1.
-- The SEAL reconcile alone passes `zeroIsEmpty`: the player's live /fsinspect class run (out of combat,
-- level 7) showed the player HELPFUL read works, and a buffless paladin must read "no seal" so the
-- seal rule can fire, so there zero values at index 1 are an EMPTY list. Every other caller keeps
-- the unreadable reading above.
local function ScanAuras(unit, filter, zeroIsEmpty)
    if not AurasReadable() then return nil end
    local fn = C_UnitAuras and C_UnitAuras.GetAuraDataByIndex
    if not fn then return nil end
    local out = {}
    for i = 1, MAX_AURAS do
        local ok, n, a = pack(pcall(fn, unit, i, filter))
        if not ok or not Plain(a) then return nil end
        if i == 1 and n == 0 then
            if zeroIsEmpty then return out end
            return nil
        end
        if a == nil then break end
        if type(a) == "table" then
            out[#out + 1] = {
                name = PlainOf(a.name, "string"),
                id = PlainOf(a.spellId, "number"),
                expires = PlainOf(a.expirationTime, "number"),
                duration = PlainOf(a.duration, "number"),
                source = PlainOf(a.sourceUnit, "string"),
            }
        end
    end
    return out
end

local function AuraKey(a)
    return (a.name and nameKey[a.name]) or (a.id and KeyForSpellID(a.id)) or nil
end

-- The player's own buffs, scanned out of combat and kept until UNIT_AURA("player") (or
-- entering the world, or leaving combat) says they may have changed. nil = unreadable.
local playerAuras, playerDirty = nil, true

local function PlayerAuras()
    if not AurasReadable() then return nil end
    if playerDirty then
        local list = ScanAuras("player", "HELPFUL")
        if not list then return nil end
        playerAuras, playerDirty = list, false
    end
    return playerAuras
end

-- The active seal (Paladin). ledger: nil unknown, false no seal, else { key, id, expiresAt,
-- duration, castAt } with absolute GetTime values. `dirty` asks the next read to reconcile it
-- against the player's auras (out of combat only). One table, to stay under the local limit.
local Seal = { ledger = nil, dirty = true, judgeAt = nil, judgeSeen = false }

-- Our own cast of a seal landed: it replaces whatever was up. A cast is fresher than any pending
-- reconcile, so it also clears `dirty` (the UNIT_AURA the cast causes sets it again).
function Seal.OnCast(key, spellID)
    local seals = profile and profile.seals
    local now = Now()
    if not (seals and now) then return end
    local seconds = seals.duration or (Spells[key] and Spells[key].apply)
    if not seconds then return end
    Seal.ledger = {
        key = key, id = PlainOf(spellID, "number"), expiresAt = now + seconds,
        duration = seconds, castAt = now,
    }
    Seal.dirty = false
end

-- Our own Judgement cast landed at `now`: stamp it. Returns { key, seconds } for the debuff it puts on
-- the target when the active seal is known and has a Judgement length, else nil. The seal is only read.
function Seal.OnJudge(now)
    local seals = profile and profile.seals
    if not (seals and now) then return nil end
    Seal.judgeAt, Seal.judgeSeen = now, true
    local s = Seal.Read()
    local seconds = type(s) == "table" and seals.judge and seals.judge[s.key]
    if seconds then return { key = s.key, seconds = seconds } end
end

-- A seal we cast less than this many seconds ago survives a readable scan that does not list it
-- (the aura can lag the cast event, and a seal name we do not know never matches).
local SEAL_LAG = 1.0
-- A listed seal whose expiry is within this many seconds of the ledger's is the same cast.
local SEAL_AGREE = 1.0

-- Replace the ledger from a readable aura list. Nothing here compares a secret: AuraKey and the
-- scan entries carry plain values only.
function Seal.Reconcile(list)
    local seals = profile.seals
    local found
    for _, a in ipairs(list) do
        local key = AuraKey(a)
        if key and Spells[key].seal and (a.source == nil or a.source == "player") then
            found = { key = key, a = a }
            break
        end
    end
    local old = Seal.ledger
    if not found then
        local now = Now()
        if type(old) == "table" and now and now - old.castAt < SEAL_LAG then return end
        Seal.ledger = false
        return
    end
    local a = found.a
    if a.expires and a.expires > 0 then
        if type(old) == "table" and old.key == found.key and math.abs(old.expiresAt - a.expires) <= SEAL_AGREE then
            -- the aura of the cast we already hold: keep the entry (castAt and the cast's rank id),
            -- so the change detector does not move twice per cast. A disagreeing aura replaces it, and
            -- then the id becomes the aura's spell id.
            return
        end
        local duration = (a.duration and a.duration > 0) and a.duration
            or seals.duration or Spells[found.key].apply
        Seal.ledger = {
            key = found.key, id = a.id, expiresAt = a.expires, duration = duration,
            castAt = a.expires - duration,
        }
    elseif not (type(Seal.ledger) == "table" and Seal.ledger.key == found.key) then
        -- the seal is up but its timing is unreadable: keep our own cast's entry for the same
        -- seal, otherwise it is unknown
        Seal.ledger = nil
    end
end

-- nil unknown, false no seal, else the ledger entry (still unexpired).
function Seal.Read()
    if not (profile and profile.seals) then return nil end
    if Seal.dirty and AurasReadable() then
        -- its own scan (not the cached PlayerAuras): zero values mean an empty list here only
        local list = ScanAuras("player", "HELPFUL", true)
        if list then
            Seal.Reconcile(list)
            Seal.dirty = false
        end
    end
    local s = Seal.ledger
    if s then
        local now = Now()
        if now and now >= s.expiresAt then return false end
    end
    return s
end

-- The own-cast ledger -------------------------------------------------------------------

-- byGuid[guid][key] = { expires } | false (known missing). cur mirrors the CURRENT target and
-- is the only store used while target GUIDs are secret: entries[key] likewise, and
-- unknownAll means a retarget happened that cannot be told apart from the old target, so
-- anything not cast or reconciled since is unknown.
local byGuid = {}
local cur = { entries = {}, unknownAll = true, engaged = nil }
-- engaged[guid] = when our first harmful own cast landed on that target this combat (a
-- time), or true when it is known to carry our DoT but the time is not (freshTarget and
-- engagedFor). cur.engaged mirrors it for the current target.
local engaged = {}
-- pendingCast[castGUID] = { guid, st, epoch, at }: the target when a cast was SENT or
-- STARTED, so a retarget before SUCCEEDED cannot move the cast onto the new target.
local pendingCast = {}
local targetEpoch = 0      -- bumped on every PLAYER_TARGET_CHANGED
-- Own cast times per spell key, the cooldown ledger (CooldownState). Not part of the DoT ledger
-- reset: GetTime is monotonic across a loading screen, so a cooldown we started stays known.
local lastCastOf = {}

local function ResetLedger()
    byGuid = {}
    engaged = {}
    pendingCast = {}
    cur = { entries = {}, unknownAll = true, engaged = nil }
end

-- guid, "plain" | nil, "none" (no target) | nil, "secret"
local function TargetGuid()
    local ok, g = pcall(UnitGUID, "target")
    if not ok or not Plain(g) then return nil, "secret" end
    if g == nil then return nil, "none" end
    if type(g) ~= "string" then return nil, "secret" end
    return g, "plain"
end

-- Where a ledger write lands: { guid = plain guid | nil, current = writes `cur` too }, or
-- nil when there is no target.
local function CurrentCtx()
    local guid, st = TargetGuid()
    if st == "none" then return nil end
    return { guid = guid, current = true }
end

local function SetEntryAt(ctx, key, entry)
    if ctx.guid then
        local b = byGuid[ctx.guid]
        if not b then b = {}; byGuid[ctx.guid] = b end
        b[key] = entry
    end
    if ctx.current then cur.entries[key] = entry end
end

-- A harmful cast landed: remember when the first one did. `at` true = time unknown.
local function MarkEngaged(ctx, at)
    if at == nil then at = Now() or true end
    if ctx.guid and not engaged[ctx.guid] then engaged[ctx.guid] = at end
    if ctx.current and not cur.engaged then cur.engaged = at end
end

-- entry table | false (known missing) | nil (unknown)
local function ReadEntry(key)
    local guid, st = TargetGuid()
    if st == "none" then return nil end
    local now = Now()
    if not now then return nil end
    local e
    if st == "plain" then
        local b = byGuid[guid]
        e = b and b[key]
    else
        e = cur.entries[key]
        if e == nil and cur.unknownAll then return nil end
    end
    if e and e.expires > now then return e end
    return false
end

-- The current target changed: mirror it into `cur`, or mark it unknown when its GUID is secret.
local function OnTargetChanged()
    local guid, st = TargetGuid()
    targetEpoch = targetEpoch + 1
    cur = { entries = {}, unknownAll = false, engaged = nil }
    if st == "plain" then
        cur.engaged = engaged[guid]
        for k, e in pairs(byGuid[guid] or {}) do cur.entries[k] = e end
    elseif st == "secret" then
        cur.unknownAll = true
    end
end

local function Prune(now)
    for guid, b in pairs(byGuid) do
        for k, e in pairs(b) do
            if e == false or e.expires <= now then b[k] = nil end
        end
        if next(b) == nil then byGuid[guid] = nil end
    end
    for id, p in pairs(pendingCast) do
        if now - p.at > PENDING_TTL then pendingCast[id] = nil end
    end
end

local function DotSpec(key) return profile and profile.dots and profile.dots[key] or nil end

-- Talent ranks -------------------------------------------------------------------------------
-- A DoT whose dictionary entry has `applyTalent` (Improved Shadow Word: Pain) lasts apply + perRank * rank.
-- The rank is read OUT OF COMBAT only (in combat the answer is not trusted and the read waits for
-- PLAYER_REGEN_ENABLED) and by talent NAME, never by a guessed id, from a plain answer of:
--   1. the trait system, which is what Forever's own talent frame reads (Blizzard_SharedTalentUI on the
--      Gethe/wow-ui-source `forever` branch): C_ClassTalents.GetActiveConfigID -> C_Traits.GetConfigInfo
--      (treeIDs) -> GetTreeNodes -> GetNodeInfo (activeRank) -> GetEntryInfo (definitionID) ->
--      GetDefinitionInfo (spellID / overrideName) -> the spell's name;
--   2. else C_SpecializationInfo.GetTalentInfo({ specializationIndex, talentIndex }), the Classic style
--      per tab scan, which carries name and rank directly (it is in the 16001 API dump).
-- UNVERIFIED on the live client: neither route has been run there (the API shapes come from the Forever UI
-- source and the dump). A scan that read every node (or every tab to its end) and did not find the talent
-- means rank 0, but a rank 0 is believed only when a SECOND read agrees (a talent frame that has not loaded
-- can answer all zeros, and a believed 0 would block the re-read); the first one retries after
-- TALENT_RETRY seconds. A read that finds every wanted talent above rank 0 is done at once, whatever else
-- in the tree was unreadable. Anything unreadable (secret, missing API, an error, a tree longer than
-- MAX_TREES / MAX_NODES) leaves the last good rank, or none: a respec to rank 0 that is only ever read
-- incompletely keeps the old rank until a complete read agrees.
-- A plain out of combat aura duration for the DoT (learnedApply, kept when it lies within what the talent
-- allows) is the ground truth where the rank cannot be: it stands in while the rank is unknown, and it
-- overrides a rank that gives a shorter time (a localized client names the talent differently and reads 0).
-- Reads are deferred to the 0.2 s tick, so a burst of events costs one walk.
local talentRank = {}            -- talent name -> rank
local zeroSeen = {}              -- talent name -> true after one complete read that did not find it
local learnedApply = {}          -- key -> seconds seen on a plain target aura
local talentWanted               -- talent name -> true, for the profile's talent timed DoTs; nil when none
local talentDirty, talentTries, talentNextAt = false, 0, 0
local TALENT_RETRY = 5           -- seconds between tries of a read that failed
local TALENT_MAX_TRIES = 4       -- tries per request; a later event asks again
local MAX_TREES, MAX_NODES, MAX_TABS, MAX_TALENTS = 4, 200, 3, 60

local function PlainTable(fn, ...)
    local ok, v = pcall(fn, ...)
    if ok and Plain(v) and type(v) == "table" then return v end
    return nil
end

local function TraitName(def)
    local name = PlainOf(def.overrideName, "string")
    if name and name ~= "" then return name end
    local id = PlainOf(def.spellID, "number")
    if not id then return nil end
    local fn = C_Spell and C_Spell.GetSpellName
    if fn then
        local ok, n = pcall(fn, id)
        if ok then return PlainOf(n, "string") end
        return nil
    end
    return (SpellInfo(id))
end

-- Route 1. nil = this route cannot answer; true = every node was read; false = some were not.
-- Fills found[name] = rank for the wanted names that have a rank above 0.
local function ReadTraitRanks(want, found)
    local cfgFn = C_ClassTalents and C_ClassTalents.GetActiveConfigID
    local T = C_Traits
    if not (cfgFn and T and T.GetConfigInfo and T.GetTreeNodes and T.GetNodeInfo and T.GetEntryInfo
            and T.GetDefinitionInfo) then
        return nil
    end
    local ok, cfg = pcall(cfgFn)
    cfg = ok and PlainOf(cfg, "number") or nil
    if not cfg then return nil end
    local info = PlainTable(T.GetConfigInfo, cfg)
    local trees = info and Plain(info.treeIDs) and type(info.treeIDs) == "table" and info.treeIDs or nil
    if not trees then return nil end
    local seen, complete = 0, #trees <= MAX_TREES
    for ti = 1, math.min(#trees, MAX_TREES) do
        local treeID = PlainOf(trees[ti], "number")
        local nodes = treeID and PlainTable(T.GetTreeNodes, treeID)
        if not nodes then
            complete = false
        else
            if #nodes > MAX_NODES then complete = false end
            for ni = 1, math.min(#nodes, MAX_NODES) do
                local nodeID = PlainOf(nodes[ni], "number")
                local node = nodeID and PlainTable(T.GetNodeInfo, cfg, nodeID)
                local rank = node and (PlainOf(node.activeRank, "number") or PlainOf(node.currentRank, "number")
                    or PlainOf(node.ranksPurchased, "number"))
                if not rank then
                    complete = false
                else
                    seen = seen + 1
                    if rank > 0 then
                        local active = node.activeEntry
                        local entryID = Plain(active) and type(active) == "table" and PlainOf(active.entryID, "number")
                        if not entryID and Plain(node.entryIDs) and type(node.entryIDs) == "table" then
                            entryID = PlainOf(node.entryIDs[1], "number")
                        end
                        local entry = entryID and PlainTable(T.GetEntryInfo, cfg, entryID)
                        local defID = entry and PlainOf(entry.definitionID, "number")
                        local def = defID and PlainTable(T.GetDefinitionInfo, defID)
                        local name = def and TraitName(def)
                        if not name then
                            complete = false
                        elseif want[name] then
                            found[name] = rank
                        end
                    end
                end
            end
        end
    end
    if seen == 0 then return nil end
    return complete
end

-- Route 2, same contract.
local function ReadSpecRanks(want, found)
    local fn = C_SpecializationInfo and C_SpecializationInfo.GetTalentInfo
    if not fn then return nil end
    local seen, complete = 0, true
    for tab = 1, MAX_TABS do
        local ended = false
        for index = 1, MAX_TALENTS do
            local ok, t = pcall(fn, { specializationIndex = tab, talentIndex = index, isInspect = false, isPet = false })
            if not ok or not Plain(t) then break end
            if t == nil then ended = true; break end
            if type(t) ~= "table" then break end
            seen = seen + 1
            local name, rank = PlainOf(t.name, "string"), PlainOf(t.rank, "number")
            if not (name and rank) then
                complete = false
            elseif want[name] then
                found[name] = rank
            end
        end
        if not ended then complete = false end
    end
    if seen == 0 then return nil end
    return complete
end

-- A believed rank. A change from an earlier believed rank drops the aura durations learned under it.
local function SetTalentRank(name, rank)
    local before = talentRank[name]
    if before ~= nil and before ~= rank then
        for key in pairs(learnedApply) do
            local t = Spells[key] and Spells[key].applyTalent
            if t and t.name == name then learnedApply[key] = nil end
        end
    end
    talentRank[name] = rank
end

-- One read of every wanted talent. true when nothing more is needed from it: every wanted talent is
-- found above rank 0, or confirmed at rank 0 by a second complete read that did not find it.
local function ReadTalents()
    local found = {}
    local complete = ReadTraitRanks(talentWanted, found)
    if complete == nil then complete = ReadSpecRanks(talentWanted, found) end
    if complete == nil then return false end
    local done = true
    for name in pairs(talentWanted) do
        local rank = found[name]
        if rank ~= nil and rank > 0 then
            zeroSeen[name] = nil
            SetTalentRank(name, rank)
        elseif complete then
            if zeroSeen[name] or talentRank[name] == 0 then
                SetTalentRank(name, 0)
            else
                zeroSeen[name] = true
                done = false
            end
        else
            done = false
        end
    end
    return done
end

-- Runs a pending read when out of combat and not waiting between tries.
local function TalentTick()
    if not talentDirty or InCombat() then return end
    local now = Now()
    if not now or now < talentNextAt then return end
    if ReadTalents() then
        talentDirty = false
        return
    end
    talentTries = talentTries + 1
    talentNextAt = now + TALENT_RETRY
    if talentTries >= TALENT_MAX_TRIES then talentDirty = false end
end

-- A talent, spellbook or level event: read again at the next tick that is out of combat. Only marks the
-- read pending, so a burst of events (SPELLS_CHANGED comes in bursts) costs one walk of the tree.
local function RequestTalentRead()
    if not talentWanted then return end
    talentDirty, talentTries, talentNextAt = true, 0, 0
end

local function TalentsUnknown()
    if not talentWanted then return false end
    for name in pairs(talentWanted) do
        if talentRank[name] == nil then return true end
    end
    return false
end

-- Seconds a talent timed DoT lasts: the read rank (a longer plain aura duration wins), else the aura, else the base.
local function TalentSeconds(key, def)
    local t = def.applyTalent
    local rank = talentRank[t.name]
    local learned = learnedApply[key]
    if rank then
        if rank > t.maxRank then rank = t.maxRank end
        local seconds = def.apply + t.perRank * rank
        if learned and learned > seconds then return learned end
        return seconds
    end
    return learned or def.apply
end

-- Seconds a cast of `key` lasts: by the rank actually cast when the dictionary knows it, else the talent
-- adjusted length, else `apply`. spellID may be nil (an aura found out of combat).
local function ApplySeconds(def, spellID, key)
    local byRank = def.applyByRank and def.applyByRank[spellID]
    if byRank then return byRank end
    if def.applyTalent and def.apply then return TalentSeconds(key, def) end
    return def.apply
end

-- A tracked spell was cast on the target `ctx` describes.
local function OnOwnCast(key, spellID, ctx)
    local def, spec = Spells[key], DotSpec(key)
    for dotKey, s in pairs(profile.dots or {}) do
        for _, consumer in ipairs(s.consumedBy or {}) do
            if consumer == key then SetEntryAt(ctx, dotKey, false) end
        end
        if spec and spec.group and s.group == spec.group and dotKey ~= key then
            SetEntryAt(ctx, dotKey, false)
        end
    end
    local seconds = spec and def and ApplySeconds(def, spellID, key)
    if seconds then
        local now = Now()
        if now then SetEntryAt(ctx, key, { expires = now + seconds, duration = seconds }) end
    end
end

-- Record the Judgement debuff `j` (from Seal.OnJudge) on the target `ctx` describes.
function Seal.RecordJudged(ctx, j, now)
    SetEntryAt(ctx, "judged", { expires = now + j.seconds, duration = j.seconds, key = j.key, appliedAt = now })
end

-- The Judgement debuff on the current target, like ReadEntry, except that "none" (false) needs a
-- Judgement cast seen since the ledger was last reset: nothing else writes the "judged" key (the aura
-- reconcile only knows the DoTs), so before that the target may still carry one from before the reset.
-- `judgeSeen` is global, not per target, on purpose: tracking it per target is not worth it, and the
-- worst case is a "none" on a mob that still carries an old Judgement, which only prompts an early re-judge.
function Seal.ReadJudged()
    local e = ReadEntry("judged")
    if e == false and not Seal.judgeSeen then return nil end
    return e
end

-- The target a cast landed on. A cast whose SENT or START we saw lands on the target of that
-- moment; otherwise (an instant on a client that sends neither) on the current target.
-- Returns a ledger context, or nil when it is unknown or there was no target.
local function ResolveCastTarget(castGUID)
    local p = Plain(castGUID) and type(castGUID) == "string" and pendingCast[castGUID] or nil
    if not p then return CurrentCtx() end
    pendingCast[castGUID] = nil
    if p.st == "none" then return nil end
    local guid, st = TargetGuid()
    local current
    if p.st == "plain" and st == "plain" then
        current = guid == p.guid
    else
        current = p.epoch == targetEpoch    -- the same target as when it was sent
    end
    if p.st ~= "plain" and not current then return nil end    -- secret, then retargeted
    return { guid = p.guid, current = current }
end

local function CapturePending(castGUID, spellID)
    if not (Plain(castGUID) and type(castGUID) == "string") then return end
    local key = KeyForSpellID(spellID)
    if not key or Spells[key].self or Spells[key].offGcd or pendingCast[castGUID] then return end
    local guid, st = TargetGuid()
    pendingCast[castGUID] = { guid = guid, st = st, epoch = targetEpoch, at = Now() or 0 }
end

-- Out of combat, when auras are plain: replace the ledger for the current target with what
-- the target actually carries from us. Returns true when it ran (or nothing needed it).
local function Reconcile()
    local ctx = CurrentCtx()
    if not ctx then return true end
    local auras = ScanAuras("target", "HARMFUL|PLAYER")
    if not auras then return false end
    local now = Now()
    if not now then return false end
    local found = {}
    for _, a in ipairs(auras) do
        local key = AuraKey(a)
        if key and DotSpec(key) then found[key] = a end
    end
    -- It already carries our DoT: not a fresh target. Our first cast was no later than the
    -- oldest aura's application (expires - duration), which bounds the fight age from below,
    -- so engagedFor counts from there. With no readable duration the time stays unknown
    -- (true), and engagedFor answers nil rather than guess.
    if next(found) then
        local oldest
        for _, a in pairs(found) do
            if a.expires and a.duration and a.expires > 0 and a.duration > 0 then
                local applied = a.expires - a.duration
                if not oldest or applied < oldest then oldest = applied end
            end
        end
        MarkEngaged(ctx, oldest or true)
    end
    for key in pairs(profile.dots or {}) do
        local def = Spells[key]
        local r = ResolveSpell(key)
        if def and def.apply and r and r.known == true then
            local a = found[key]
            if a then
                local t = def.applyTalent
                if t and a.duration and a.duration >= def.apply and a.duration <= def.apply + t.perRank * t.maxRank then
                    learnedApply[key] = a.duration
                end
                local base = ApplySeconds(def, nil, key)
                local expires = (a.expires and a.expires > 0) and a.expires or (now + base)
                local duration = (a.duration and a.duration > 0) and a.duration or base
                SetEntryAt(ctx, key, { expires = expires, duration = duration })
            else
                SetEntryAt(ctx, key, false)
            end
        end
    end
    cur.unknownAll = false
    return true
end

local dirty = true
local function TryReconcile()
    if not dirty or not profile then return end
    if not AurasReadable() then return end
    if Reconcile() then dirty = false end
end

-- Primitives ----------------------------------------------------------------------------

local function DotMissing(key)
    local spec = DotSpec(key)
    if not spec then return nil end
    local r = ResolveSpell(key)
    if not r or r.known == nil then return nil end
    if r.known == false then return true end    -- cannot be up if the player cannot cast it
    local def = Spells[key]
    if not def or not def.apply then return nil end
    local e = ReadEntry(key)
    if e == nil then return nil end
    if e == false then return true end
    if spec.pandemic then
        local now = Now()
        if not now then return nil end
        return (e.expires - now) <= spec.pandemic * (e.duration or def.apply)
    end
    return false
end

local function DotRemaining(key)
    if not DotSpec(key) then return nil end
    local r = ResolveSpell(key)
    if not r or r.known ~= true then return nil end
    local e = ReadEntry(key)
    if e == nil then return nil end
    if e == false then return 0 end
    local now = Now()
    if not now then return nil end
    return math.max(0, e.expires - now)
end

-- expiresAt (an absolute GetTime) and the full duration of a DoT that is up, else nil. The ledger
-- entry is the only combat-safe source; the gunsight DoT scale moves a chip from expiresAt - now
-- between pushes, and the pushes are coarse (the change detector floors `remaining`).
local function DotTiming(key)
    if not DotSpec(key) then return nil end
    local r = ResolveSpell(key)
    if not r or r.known ~= true then return nil end
    local e = ReadEntry(key)
    if not e then return nil end
    local def = Spells[key]
    return e.expires, e.duration or (def and def.apply)
end

-- GetSpellCooldown answers with a fresh client table on every call. During a state build each
-- spell is asked once (cdReads, wiped around the build); outside a build every call goes through.
local cdReads, cdOpen = {}, false

local function CooldownInfo(fn, id)
    if cdOpen then
        local hit = cdReads[id]
        if hit ~= nil then return hit or nil end
    end
    local ok, cd = pcall(fn, id)
    if not ok or not Plain(cd) or type(cd) ~= "table" then cd = false end
    if cdOpen and id ~= nil then cdReads[id] = cd end
    return cd or nil
end

-- Cooldown lengths learned from plain reads (key -> seconds) and cooldown ends seen in a plain read
-- (key -> GetTime). Both are written only out of combat, when the client answers plain.
local learnedCd, plainEnd = {}, {}

-- The length of a spell's own cooldown: what a plain out-of-combat read showed (so a talent such as
-- Improved Mind Blast is captured as the client reports it), else the static dictionary value, else 0.
local function CooldownLength(key)
    return learnedCd[key] or (Spells[key] or {}).cooldown or 0
end

-- ready (true/false/nil), remaining seconds (nil when unknown). See COOLDOWNS in the file header.
local function CooldownState(key)
    local r = ResolveSpell(key)
    if not r or r.known == nil then return nil end
    if r.known == false then return false end
    local fn = C_Spell and C_Spell.GetSpellCooldown
    if not fn then return nil end
    local cd = CooldownInfo(fn, r.id)
    if not cd then return nil end
    local active = PlainOf(cd.isActive, "boolean")
    if active == nil then return nil end
    if not active then
        plainEnd[key] = nil
        return true
    end
    -- A plain isOnGCD, when the client provides one, says the cooldown is only the GCD.
    if PlainOf(cd.isOnGCD, "boolean") == true then return true end
    local start, dur, now = PlainOf(cd.startTime, "number"), PlainOf(cd.duration, "number"), Now()
    -- Plain timing (out of combat) is exact. A duration of zero says nothing, so it falls through.
    if start and dur and now and dur > 0 then
        if dur <= GCD_WINDOW then    -- only the global cooldown: no cooldown of its own is running
            plainEnd[key] = nil
            return true
        end
        -- Learn the length only from a cooldown that started at our own cast of this spell. Any other
        -- (a lockout, a cooldown shared with another spell, one begun before we saw a cast) says
        -- nothing about this spell's own length.
        local last = lastCastOf[key]
        if last and math.abs(start - last) <= GCD_WINDOW then learnedCd[key] = dur end
        plainEnd[key] = start + dur
        local remaining = math.max(0, start + dur - now)
        if remaining <= 0 then return true end
        return false, remaining
    end
    -- Timing unreadable (in combat startTime and duration are secret while isActive stays plain). A plain
    -- false returned above (ready); a plain true may be stuck or only the global cooldown, so the cast
    -- ledger decides. Ready unless our own last cast, or a cooldown end seen in a plain read, is still ahead.
    if not now then return nil end
    local ends = plainEnd[key]
    local last = lastCastOf[key]
    if last and now >= last then
        local e = last + CooldownLength(key)
        if not ends or e > ends then ends = e end
    end
    if ends and now < ends then return false, ends - now end
    return true
end

-- Spell-activation-overlay glow by spell key, from GLOW_SHOW (true) and GLOW_HIDE (false).
local overlayGlow = {}

-- true / false / nil from the overlay source: the last glow event for the proc's spell, else
-- IsSpellOverlayed. UNVERIFIED on Forever until the in-game check has run.
local function OverlayState(spec)
    local sk = spec.overlaySpell
    if not sk then return nil end
    local ev = overlayGlow[sk]
    if ev ~= nil then return ev end
    local r = ResolveSpell(sk)
    local api = _G.C_SpellActivationOverlay
    local fn = api and api.IsSpellOverlayed
    if not r or r.known ~= true or not r.id or not fn then return nil end
    local ok, v = pcall(fn, r.id)
    if not ok then return nil end
    return PlainOf(v, "boolean")
end

-- true / false / nil from the player's aura. By-spell lookups return no values in combat on
-- 1.60.1: that is unknown, not "absent". The `n == 0` check is NOT redundant behind
-- AurasReadable: that gate only says the client allows the read, not what an absent aura
-- looks like out of combat (one nil or zero values, the same UNCHECKED question as in
-- ScanAuras), and zero values must never read as "the proc is absent".
local function AuraProcState(spec)
    if not spec.aura or not AurasReadable() then return nil end
    local fn = (C_UnitAuras and C_UnitAuras.GetPlayerAuraBySpellID) or _G.GetPlayerAuraBySpellID
    if not fn then return nil end
    local ok, n, r = pack(pcall(fn, spec.aura))
    if not ok or n == 0 or not Plain(r) then return nil end
    return r ~= nil
end

-- Deliberately NOT FS.TargetTakesDots (Theme.lua), which asks the same three questions for the DoT scale and the
-- horizon segment. Both treat an enemy ghost as dead (UnitIsDeadOrGhost), but they still differ, so delegating
-- would change this rule: (1) Plain() above reads unknown as attackable through its own pcall'd issecretvalue (a
-- client without it reads every answer as unknown, so the target counts as attackable); FS.IsSecret reads a
-- missing issecretvalue as "never secret". (2) A plain 0 from a predicate is truthy here and false in the shared
-- rule's legacy number reading. hud-harness.py runs this file with a bare FS (no Theme), so it also could not
-- reach the shared rule.
local function HasAttackableTarget()
    local ok, e = pcall(UnitExists, "target")
    if ok and Plain(e) and not e then return false end
    local ok2, c = pcall(UnitCanAttack, "player", "target")
    if ok2 and Plain(c) and not c then return false end
    local ok3, d = pcall(UnitIsDeadOrGhost, "target")
    if ok3 and Plain(d) and d == true then return false end
    return true
end

local function ProcActive(key)
    local spec = profile and profile.procs and profile.procs[key]
    if not spec then return nil end
    -- A cooldown tracker: ready (true), on cooldown or unknown spell (false), unreadable (nil).
    if spec.ready then
        local ready = CooldownState(spec.ready)
        -- needsTarget (Judgement): only a hostile target can take the cast, so no, friendly or dead target
        -- hides the rung. A ready of false or nil (unreadable) passes through; an unreadable target reads
        -- as attackable (HasAttackableTarget), so the rung is never hidden on a guess.
        if spec.needsTarget and ready == true and not HasAttackableTarget() then return false end
        return ready
    end
    local glow = OverlayState(spec)
    if glow == true then return true end
    local aura = AuraProcState(spec)
    if aura ~= nil then return aura end
    return glow
end

local function PowerFraction(unit)
    local okp, p = pcall(UnitPower, unit)
    local okm, m = pcall(UnitPowerMax, unit)
    p, m = okp and PlainOf(p, "number"), okm and PlainOf(m, "number")
    if not p or not m or m <= 0 then return nil end
    return p / m
end

local function HealthFraction(unit)
    local okp, p = pcall(UnitHealth, unit)
    local okm, m = pcall(UnitHealthMax, unit)
    p, m = okp and PlainOf(p, "number"), okm and PlainOf(m, "number")
    if not p or not m or m <= 0 then return nil end
    return p / m
end

local function ItemCount()
    local item = profile and profile.resource and profile.resource.shards
        and profile.resource.shards.item
    if not item then return nil end
    local fn = (C_Item and C_Item.GetItemCount) or _G.GetItemCount
    if not fn then return nil end
    local ok, n = pcall(fn, item)
    if not ok then return nil end
    return PlainOf(n, "number")
end

-- missing? true / false / nil, then `expiring`: true when the buff is present but inside its
-- warnBelow window (so "missing" is only a refresh warning, not an absent buff). `auras` is the
-- player's aura list (PlayerAuras(); nil = unreadable) and is only read for an aura-kind entry.
-- The caller fetches it ONCE: a nil here means unknown and must never trigger a second scan.
local function BuffMissing(entry, auras)
    local r = ResolveSpell(entry.spell)
    if not r or r.known ~= true then return nil end
    if entry.oocOnly and InCombat() then return nil end
    if entry.kind == "form" then
        local ok, n = pcall(GetShapeshiftForm)
        n = ok and PlainOf(n, "number")
        if not n then return nil end
        return n == 0
    elseif entry.kind == "pet" then
        local ok, e = pcall(UnitExists, "pet")
        if not ok or not Plain(e) then return nil end
        return not e
    end
    if not auras then return nil end
    local now = Now()
    for _, a in ipairs(auras) do
        if AuraKey(a) == entry.spell then
            if entry.warnBelow and a.expires and a.expires > 0 then
                if not now then return nil end
                local low = (a.expires - now) < entry.warnBelow
                return low, low
            end
            return false
        end
    end
    return true
end

local function SelfBuffEntry(key)
    for _, entry in ipairs(profile and profile.selfBuffs or EMPTY) do
        if entry.spell == key then return entry end
    end
    return nil
end

-- Is a wand equipped (Shoot usable)? HasWandEquipped when the client has it, else
-- C_Spell.IsSpellUsable on the resolved Shoot id. true / false / nil.
local function WandEquipped()
    local r = ResolveSpell("shoot")
    if not r or r.known == nil then return nil end
    if r.known == false then return false end
    if HasWandEquipped then
        local ok, v = pcall(HasWandEquipped)
        if ok and Plain(v) then return v and true or false end
        return nil
    end
    local fn = C_Spell and C_Spell.IsSpellUsable
    if not fn then return nil end
    local ok, usable = pcall(fn, r.id)
    if not ok then return nil end
    return PlainOf(usable, "boolean")
end

-- true / false / nil: does the spell cost more mana than the player has. Unknowable for a
-- spell the player does not have.
local function NotEnoughMana(key)
    local r = ResolveSpell(key)
    if not r or r.known ~= true then return nil end
    local fn = C_Spell and C_Spell.IsSpellUsable
    if not fn then return nil end
    local ok, _, noMana = pcall(fn, r.id)
    if not ok then return nil end
    return PlainOf(noMana, "boolean")
end

-- The implicit check every rotation candidate passes: not skipped unless the client plainly
-- says it is unusable or lacks the mana. `r` is the resolved, known spell.
local function Affordable(r)
    local fn = C_Spell and C_Spell.IsSpellUsable
    if not fn then return true end
    local ok, usable, noMana = pcall(fn, r.id)
    if not ok then return true end
    return PlainOf(usable, "boolean") ~= false and PlainOf(noMana, "boolean") ~= true
end

-- A live attackable target we have not cast on yet this combat (the opener).
local function FreshTarget()
    local ok, e = pcall(UnitExists, "target")
    if not ok or not Plain(e) then return nil end
    if not e then return false end
    local okc, c = pcall(UnitCanAttack, "player", "target")
    if not okc or not Plain(c) then return nil end
    if not c then return false end
    local okd, d = pcall(UnitIsDead, "target")
    if okd and Plain(d) and d then return false end
    local guid, st = TargetGuid()
    if st == "plain" then return not engaged[guid] end
    if st == "secret" then return not cur.engaged end
    return false
end

-- True once our first harmful own cast on this target is at least `sec` seconds old. For a
-- target the reconcile found already carrying our DoT, the clock starts at that aura's
-- application (a lower bound on the fight age). nil when there is no target, or when the
-- target carries our DoT but its application time is unreadable (the age is unknown).
local function EngagedFor(sec)
    if not PlainOf(sec, "number") then return nil end
    local guid, st = TargetGuid()
    local e
    if st == "plain" then
        e = engaged[guid]
    elseif st == "secret" then
        e = cur.engaged
    else
        return nil
    end
    if not e then return false end
    if e == true then return nil end
    local now = Now()
    if not now then return nil end
    return now - e >= sec
end

local function InCombatPrim()
    local sawFalse = false
    local ok1, r1 = pcall(InCombatLockdown)
    if ok1 and Plain(r1) then
        if r1 then return true end
        sawFalse = true
    end
    local ok2, r2 = pcall(UnitAffectingCombat, "player")
    if ok2 and Plain(r2) then
        if r2 then return true end
        sawFalse = true
    end
    if sawFalse then return false end
    return nil
end

Prims.dotMissing = DotMissing
Prims.dotRemaining = DotRemaining
Prims.cooldownReady = function(key) return (CooldownState(key)) end
Prims.procActive = ProcActive
Prims.wandEquipped = WandEquipped
Prims.freshTarget = FreshTarget
Prims.engagedFor = EngagedFor
Prims.inCombat = InCombatPrim
Prims.notEnoughMana = NotEnoughMana
Prims.inRange = function(key)
    local r = ResolveSpell(key)
    if not r or r.known ~= true then return nil end
    local fn = C_Spell and C_Spell.IsSpellInRange
    if not fn then return nil end
    local ok, v = pcall(fn, r.id, "target")
    if not ok then return nil end
    return PlainOf(v, "boolean")
end
Prims.sealMissing = function(sec)
    if not PlainOf(sec, "number") then return nil end
    local s = Seal.Read()
    if s == nil then return nil end
    if s == false then return true end
    local now = Now()
    if not now then return nil end
    return s.expiresAt - now <= sec
end
Prims.known = function(key)
    local r = ResolveSpell(key)
    return r and r.known
end
Prims.buffMissing = function(key)
    local entry = SelfBuffEntry(key)
    if not entry then return nil end
    local auras = nil
    if entry.kind == nil then auras = PlayerAuras() end
    local missing = BuffMissing(entry, auras)
    return missing
end
Prims.resourceBelow = function(percent)
    local f = PowerFraction("player")
    if not f or not PlainOf(percent, "number") then return nil end
    return f * 100 < percent
end
Prims.shardsAtLeast = function(n)
    local count = ItemCount()
    if not count or not PlainOf(n, "number") then return nil end
    return count >= n
end
Prims.playerHealthAbove = function(percent)
    local f = HealthFraction("player")
    if not f or not PlainOf(percent, "number") then return nil end
    return f * 100 > percent
end
Prims.targetHealthBelow = function(percent)
    local ok, e = pcall(UnitExists, "target")
    if not ok or not Plain(e) or not e then return nil end
    local f = HealthFraction("target")
    if not f or not PlainOf(percent, "number") then return nil end
    return f * 100 < percent
end

-- cond = { name, arg } or { "not", cond } or { "orUnknown", cond }; nil stays nil, except
-- under orUnknown, which reads an unreadable answer as true (the rule is not skipped for it).
local function Eval(cond)
    if type(cond) ~= "table" then return nil end
    local name = cond[1]
    if name == "not" then
        local v = Eval(cond[2])
        if v == nil then return nil end
        return not v
    end
    if name == "orUnknown" then
        local v = Eval(cond[2])
        if v == nil then return true end
        return v
    end
    local fn = Prims[name]
    if not fn then return nil end
    return fn(cond[2])
end

Hud.Primitives = Prims
Hud.Eval = Eval

-- Channels --------------------------------------------------------------------------------

local channel   -- { key, start, finish }

-- period, ticks, clipAfter of a channel: the dictionary is the single source of period and
-- ticks (a profile may still override them), the profile adds clipAfter.
local function ChannelData(key)
    local own = profile and profile.channels and profile.channels[key]
    if not own then return nil end
    local def = Spells[key] or {}
    local period, ticks = own.period or def.period, own.ticks or def.ticks
    if not period or not ticks or period <= 0 then return nil end
    return period, ticks, own.clipAfter
end

-- Fills and returns `into` (a reused table), or nil when no channel is up.
local function ChannelView(into)
    if not channel then return nil end
    local period, ticks, clipAfter = ChannelData(channel.key)
    local now = Now()
    if not period or not now then return nil end
    if now > channel.finish + CHANNEL_GRACE then
        channel = nil    -- a dropped STOP event cannot leave the channel up
        return nil
    end
    local done = math.floor((now - channel.start) / period + 0.001)
    done = math.max(0, math.min(ticks, done))
    into.key, into.done, into.ticks = channel.key, done, ticks
    into.cut = clipAfter ~= nil and done >= clipAfter
    return into
end

-- State -------------------------------------------------------------------------------------

-- The rotation in evaluation order. Rules tagged filler = "wand" or "spell" are pulled out
-- and re-inserted together at the first filler rule's place: wand rules first by default. With
-- fillerOrder = "spell" the spell rules lead but the LAST spell rule (the unconditional
-- fallback, e.g. Smite) moves behind the wand rules, so the wand takes over when the leading
-- spell (Mind Flay) is unaffordable. Cached per profile and order.
local orderedFor, orderedMode, orderedList
local function OrderedRules()
    local mode = profile.fillerOrder == "spell" and "spell" or "wand"
    if orderedFor == profile and orderedMode == mode then return orderedList end
    local out, wand, spell, slot = {}, {}, {}, nil
    for _, rule in ipairs(profile.rotation or {}) do
        if rule.filler then
            local group = rule.filler == "wand" and wand or spell
            group[#group + 1] = rule
            if not slot then out[#out + 1] = false; slot = #out end
        else
            out[#out + 1] = rule
        end
    end
    local fillers = {}
    if mode == "spell" then
        for i = 1, #spell - 1 do fillers[#fillers + 1] = spell[i] end
        for _, f in ipairs(wand) do fillers[#fillers + 1] = f end
        if #spell > 0 then fillers[#fillers + 1] = spell[#spell] end
    else
        for _, f in ipairs(wand) do fillers[#fillers + 1] = f end
        for _, f in ipairs(spell) do fillers[#fillers + 1] = f end
    end
    local list = {}
    for _, rule in ipairs(out) do
        if rule then
            list[#list + 1] = rule
        else
            for _, f in ipairs(fillers) do list[#list + 1] = f end
        end
    end
    orderedFor, orderedMode, orderedList = profile, mode, list
    return list
end

-- Wipe/Trim reuse the tables of an unpushed scratch.
local function Wipe(t)
    for k in pairs(t) do t[k] = nil end
end

-- Clears the tail of an array that held more than `n` entries.
local function Trim(list, n)
    local i = n + 1
    while list[i] ~= nil do list[i] = nil; i = i + 1 end
end

local procFor, procState, cooldownSet, procKeys = {}, {}, {}, {}

-- The first matching rule: key, glow, and which spells a live proc is lighting. The third result
-- is the shared procFor scratch, valid until the next call.
local function EvalRotation()
    Wipe(procFor)
    Wipe(procState)
    for key, spec in pairs(profile.procs or EMPTY) do
        procState[key] = ProcActive(key) == true and spec or nil
    end
    for _, rule in ipairs(profile.rotation or EMPTY) do
        for _, cond in ipairs(rule.when or EMPTY) do
            if cond[1] == "procActive" and procState[cond[2]] then
                procFor[rule.cast] = procState[cond[2]].glow
            end
        end
    end
    if not HasAttackableTarget() then return nil, nil, procFor end
    for _, rule in ipairs(OrderedRules()) do
        local r = ResolveSpell(rule.cast)
        if r and r.known == true then
            local match = true
            for _, cond in ipairs(rule.when or EMPTY) do
                if Eval(cond) ~= true then match = false; break end
            end
            if match and Affordable(r) then
                return rule.cast, procFor[rule.cast], procFor, r.icon
            end
        end
    end
    return nil, nil, procFor
end

-- missing, remaining, expiresAt, duration of a DoT; a grouped slot (banes) reads as the whole
-- group. expiresAt and duration are nil unless the DoT is up.
local function DotView(key)
    local spec = DotSpec(key)
    local missing, remaining = DotMissing(key), DotRemaining(key)
    if spec and spec.group and missing ~= false then
        for other, o in pairs(profile.dots) do
            if other ~= key and o.group == spec.group and DotMissing(other) == false then
                local expiresAt, duration = DotTiming(other)
                return false, DotRemaining(other), expiresAt, duration
            end
        end
    end
    local expiresAt, duration = DotTiming(key)
    return missing, remaining, expiresAt, duration
end

-- One state under construction plus the entry tables it points at. The tick builds into a single
-- scratch; a state that changed is handed to the subscribers WITH its buffer and a new scratch
-- takes over, so a state a subscriber holds is never written again.
local function NewBuf()
    return {
        state = { row = {}, buffsMissing = {}, procs = {} },
        rows = {}, buffs = {}, procRows = {},
        next = {}, channel = {}, seal = {}, judged = {},
    }
end
local scratch = NewBuf()

local function Entry(pool, i)
    local e = pool[i]
    if e then Wipe(e) else e = {}; pool[i] = e end
    return e
end

local function FillState(buf)
    local state = buf.state
    state.active, state.inCombat, state.targetEpoch = false, InCombat(), targetEpoch
    state.class, state.next, state.shards, state.channel = nil, nil, nil, nil
    state.seal, state.judgeAt, state.judged = nil, nil, nil
    local row, buffsMissing, procs = state.row, state.buffsMissing, state.procs
    state.aurasKnown = false
    if not profile then
        Trim(row, 0); Trim(buffsMissing, 0); Trim(procs, 0)
        return state
    end
    state.active = true
    state.class = classToken

    local nextKey, nextGlow, procForKey, nextIcon = EvalRotation()
    if nextKey then
        local nx = buf.next
        nx.key, nx.icon, nx.glow = nextKey, nextIcon, nextGlow
        state.next = nx
    end

    Wipe(cooldownSet)
    for _, k in ipairs(profile.cooldowns or EMPTY) do cooldownSet[k] = true end

    local nRow = 0
    for _, key in ipairs(profile.row or EMPTY) do
        local r = ResolveSpell(key)
        if r and r.known == true then
            nRow = nRow + 1
            local e = Entry(buf.rows, nRow)
            e.key, e.icon, e.proc, e.isNext = key, r.icon, procForKey[key], nextKey == key
            if DotSpec(key) then e.missing, e.remaining, e.expiresAt, e.duration = DotView(key) end
            if cooldownSet[key] then
                local ready, cdRemaining = CooldownState(key)
                if ready ~= nil then e.onCd = not ready end
                e.cdRemaining = cdRemaining
            end
            row[nRow] = e
        end
    end
    Trim(row, nRow)

    local nBuff = 0
    local auras, fetched
    for _, entry in ipairs(profile.selfBuffs or EMPTY) do
        if entry.kind == nil and not fetched then
            fetched = true
            auras = PlayerAuras()
        end
        local missing, expiring = BuffMissing(entry, auras)
        if missing == true then
            local r = ResolveSpell(entry.spell)
            nBuff = nBuff + 1
            local b = Entry(buf.buffs, nBuff)
            b.key, b.icon, b.expiring = entry.spell, r and r.icon, expiring and true or false
            buffsMissing[nBuff] = b
        end
    end
    Trim(buffsMissing, nBuff)
    -- true only when the player's aura list was actually read this tick (readable AND the scan
    -- succeeded): a buff absent from buffsMissing then really is up. False = the aura buffs are
    -- UNKNOWN, so a consumer holding a last verdict must leave it alone.
    state.aurasKnown = auras ~= nil

    local nKeys = 0
    for key in pairs(profile.procs or EMPTY) do nKeys = nKeys + 1; procKeys[nKeys] = key end
    Trim(procKeys, nKeys)
    table.sort(procKeys)
    local nProc = 0
    for _, key in ipairs(procKeys) do
        local spec = profile.procs[key]
        local r = spec.ready and ResolveSpell(spec.ready)
        -- a cooldown tracker for a spell the player does not know has no rung yet
        if not spec.ready or (r and r.known == true) then
            nProc = nProc + 1
            local p = Entry(buf.procRows, nProc)
            p.key, p.glow, p.active, p.icon = key, spec.glow, ProcActive(key), r and r.icon or nil
            procs[nProc] = p
        end
    end
    Trim(procs, nProc)

    if profile.resource and profile.resource.shards then state.shards = ItemCount() end
    state.channel = ChannelView(buf.channel)
    if profile.seals then
        local s = Seal.Read()
        if s then
            local sl = buf.seal
            sl.key, sl.id, sl.expiresAt, sl.duration, sl.castAt = s.key, s.id, s.expiresAt, s.duration, s.castAt
            state.seal = sl
        else
            state.seal = s    -- false (no seal) or nil (unknown)
        end
        state.judgeAt = Seal.judgeAt
        local e = Seal.ReadJudged()
        if e then
            local jd = buf.judged
            jd.key, jd.appliedAt, jd.expiresAt, jd.duration = e.key, e.appliedAt, e.expires, e.duration
            state.judged = jd
        else
            state.judged = e    -- false (none) or nil (unknown)
        end
    end
    return state
end

-- Builds `buf`'s state with the cooldown reads shared; an error closes the share before it rises.
local function BuildState(buf)
    Wipe(cdReads)
    cdOpen = true
    local ok, state = pcall(FillState, buf)
    cdOpen = false
    Wipe(cdReads)
    if not ok then error(state, 0) end
    return state
end

-- A fresh, caller-owned state. The tick builds in its private scratch through BuildState instead.
function Hud.GetState()
    return BuildState(NewBuf())
end

function Hud.GetProfile() return profile end

-- The profile's seals the player knows, in profile order: plain { key, name, id } entries.
function Hud.GetSeals()
    local out = {}
    local order = profile and profile.seals and profile.seals.order
    for _, key in ipairs(order or {}) do
        local r = ResolveSpell(key)
        if r and r.known == true then
            out[#out + 1] = { key = key, name = r.name or Spells[key].names[1], id = r.id }
        end
    end
    return out
end

-- Judgement for a Paladin: the last own cast time, and the current target's debuff left and seal key.
function Hud.GetJudgement()
    local out = { judgeAt = Seal.judgeAt }
    if not (profile and profile.seals) then return out end
    local e = Seal.ReadJudged()
    local now = Now()
    if e and now then
        out.remaining, out.key = math.max(0, e.expires - now), e.key
    elseif e == false then
        out.remaining = 0
    end
    return out
end

-- Change notification ---------------------------------------------------------------------

-- The change detector: a flat list of every field a subscriber redraws on, filled into a reused
-- buffer and compared slot by slot with the last pushed one. Counts precede the variable-length
-- sections so two different states never flatten to the same list.
local NIL = {}    -- a nil, kept in the list so slots stay put

local function Put(buf, n, v)
    if v == nil then v = NIL end
    n = n + 1
    buf[n] = v
    return n
end

-- A DoT's seconds are floored: a running timer must not push every tick.
local function Whole(v)
    if v then return math.floor(v) end
    return nil
end

local function SigFill(state, buf)
    local n = Put(buf, 0, state.active and true or false)
    n = Put(buf, n, state.inCombat and true or false)
    n = Put(buf, n, state.targetEpoch)
    local row = state.row
    n = Put(buf, n, #row)
    for i = 1, #row do
        local e = row[i]
        n = Put(buf, n, e.key)
        n = Put(buf, n, e.missing)
        n = Put(buf, n, e.onCd)
        n = Put(buf, n, e.proc)
        n = Put(buf, n, e.isNext)
        n = Put(buf, n, Whole(e.remaining))
        n = Put(buf, n, Whole(e.cdRemaining))
        n = Put(buf, n, e.icon)
    end
    local nx = state.next
    n = Put(buf, n, nx and nx.key)
    n = Put(buf, n, nx and nx.glow)
    n = Put(buf, n, nx and nx.icon)
    local buffs = state.buffsMissing
    n = Put(buf, n, #buffs)
    for i = 1, #buffs do n = Put(buf, n, buffs[i].key); n = Put(buf, n, buffs[i].expiring) end
    n = Put(buf, n, state.aurasKnown)
    local procs = state.procs
    n = Put(buf, n, #procs)
    for i = 1, #procs do
        n = Put(buf, n, procs[i].key)
        n = Put(buf, n, procs[i].active)
    end
    n = Put(buf, n, state.shards)
    local c = state.channel
    n = Put(buf, n, c and c.key)
    n = Put(buf, n, c and c.done)
    n = Put(buf, n, c and c.cut)
    -- the seal by key and cast time only: a running timer must not push every second
    local sl = state.seal
    if type(sl) == "table" then
        n = Put(buf, n, "set")
        n = Put(buf, n, sl.key)
        n = Put(buf, n, sl.castAt)
    else
        n = Put(buf, n, sl == false and "none" or "unknown")
    end
    -- Judgement by cast time and the target's debuff by seal and application time (no running timer)
    n = Put(buf, n, state.judgeAt)
    local jd = state.judged
    if type(jd) == "table" then
        n = Put(buf, n, "set")
        n = Put(buf, n, jd.key)
        n = Put(buf, n, jd.appliedAt)
    else
        n = Put(buf, n, jd == false and "none" or "unknown")
    end
    return n
end

local subscribers = {}
local lastSig, lastLen = {}, nil    -- lastLen nil: nothing seeded yet
local nextSig = {}
local pruneAt = 0

local function SameAsLast(n)
    if n ~= lastLen then return false end
    for i = 1, n do
        if nextSig[i] ~= lastSig[i] then return false end
    end
    return true
end

local function Push(fn, state)
    local ok, err = pcall(fn, state)
    if not ok then LogOnce("subscriber", err) end
end

-- Pushes the current state to fn at once. The first subscriber also seeds the change
-- detector, so the next tick does not repeat what it was just given.
function Hud.Subscribe(fn)
    if type(fn) ~= "function" then return fn end
    subscribers[#subscribers + 1] = fn
    local state = Hud.GetState()
    if #subscribers == 1 then lastLen = SigFill(state, lastSig) end
    Push(fn, state)
    return fn
end

function Hud.Unsubscribe(fn)
    for i = #subscribers, 1, -1 do
        if subscribers[i] == fn then table.remove(subscribers, i) end
    end
end

function Hud.Tick()
    if not profile then return end
    local now = Now()
    if talentDirty then TalentTick() end
    TryReconcile()
    if now and now >= pruneAt then
        Prune(now)
        pruneAt = now + PRUNE_EVERY
    end
    if #subscribers == 0 then return end    -- nobody to tell: no state work
    local state = BuildState(scratch)
    local n = SigFill(state, nextSig)
    if SameAsLast(n) then return end
    nextSig, lastSig, lastLen = lastSig, nextSig, n
    scratch = NewBuf()    -- published: the buffer is theirs now
    for i = 1, #subscribers do Push(subscribers[i], state) end
end

-- Events -----------------------------------------------------------------------------------

local handlers = {}

local function OnPlayer(unit) return Plain(unit) and unit == "player" end

-- UNIT_SPELLCAST_SENT(unit, targetName, castGUID, spellID) and _START(unit, castGUID,
-- spellID): remember where the cast was aimed, keyed by castGUID, until SUCCEEDED.
function handlers.UNIT_SPELLCAST_SENT(unit, _, castGUID, spellID)
    if OnPlayer(unit) then CapturePending(castGUID, spellID) end
end

function handlers.UNIT_SPELLCAST_START(unit, castGUID, spellID)
    if OnPlayer(unit) then CapturePending(castGUID, spellID) end
end

local function DropPending(unit, castGUID)
    if OnPlayer(unit) and Plain(castGUID) and type(castGUID) == "string" then
        pendingCast[castGUID] = nil
    end
end
handlers.UNIT_SPELLCAST_FAILED = DropPending
handlers.UNIT_SPELLCAST_INTERRUPTED = DropPending

function handlers.UNIT_SPELLCAST_SUCCEEDED(unit, castGUID, spellID)
    if not OnPlayer(unit) then return end
    local key = KeyForSpellID(spellID)
    local now = Now()
    if not key then return end
    if now then lastCastOf[key] = now end    -- no clock: keep the earlier cast time, never erase it
    -- a seal is a self cast too, but it is also the active seal: record it before the early return
    if Spells[key].seal then Seal.OnCast(key, spellID) end
    -- Judgement: stamp it now (even with no target); the debuff is recorded once the target is known
    local judged = Spells[key].judgement and Seal.OnJudge(now) or nil
    -- a cast on the player (a buff, Life Tap, Vampiric Embrace) is not a cast on the target,
    -- and neither is the wand: a first shot must not end the fresh-target opener or start
    -- the fight clock
    if Spells[key].self or Spells[key].offGcd then return end
    local ctx = ResolveCastTarget(castGUID)
    if not ctx then return end
    MarkEngaged(ctx)
    OnOwnCast(key, spellID, ctx)
    if judged then Seal.RecordJudged(ctx, judged, now) end
end

function handlers.UNIT_SPELLCAST_CHANNEL_START(unit, _, spellID)
    if not OnPlayer(unit) then return end
    channel = nil
    local key = KeyForSpellID(spellID)
    local now = Now()
    if not (key and now) then return end
    local period, ticks = ChannelData(key)
    if period then channel = { key = key, start = now, finish = now + ticks * period } end
end

-- A pushback or a clip moves the end: take the real one from UnitChannelInfo when it is
-- plain, else keep the old one.
function handlers.UNIT_SPELLCAST_CHANNEL_UPDATE(unit)
    if not (OnPlayer(unit) and channel) then return end
    local ok, _, _, _, _, endMs = pcall(UnitChannelInfo, "player")
    endMs = ok and PlainOf(endMs, "number")
    if not endMs then return end
    local finish = endMs / 1000
    if finish > channel.start and finish < channel.start + MAX_CHANNEL then
        channel.finish = finish
    end
end

function handlers.UNIT_SPELLCAST_CHANNEL_STOP(unit)
    if OnPlayer(unit) then channel = nil end
end

local function OnOverlay(spellID, glowing)
    local key = KeyForSpellID(spellID)    -- nil for a secret or unknown id
    if key then overlayGlow[key] = glowing end
end
function handlers.SPELL_ACTIVATION_OVERLAY_GLOW_SHOW(spellID) OnOverlay(spellID, true) end
function handlers.SPELL_ACTIVATION_OVERLAY_GLOW_HIDE(spellID) OnOverlay(spellID, false) end

function handlers.PLAYER_TARGET_CHANGED()
    OnTargetChanged()
    dirty = true
    TryReconcile()
end

function handlers.UNIT_AURA(unit)
    if not Plain(unit) then return end
    if unit == "target" then dirty = true end
    if unit == "player" then playerDirty = true; Seal.dirty = true end
end

-- Death strips the seal. The aura list may still show it for a moment, so no reconcile runs until
-- the next UNIT_AURA or PLAYER_REGEN_ENABLED (leaving combat after a death rescans, and a seal
-- still listed then is read back).
function handlers.PLAYER_DEAD()
    Seal.ledger = false
    Seal.dirty = false
end

function handlers.PLAYER_REGEN_ENABLED()
    engaged = {}
    cur.engaged = nil
    dirty = true
    playerDirty = true
    Seal.dirty = true
    TalentTick()
    TryReconcile()
end

local function Relearn()
    spellCache = {}
end

-- A respec or a new rank can change a cooldown's length: forget the lengths learned from plain reads
-- (the static dictionary value answers until the next plain read). Not done on PLAYER_ENTERING_WORLD,
-- a loading screen changes nothing about the talents.
local function ForgetLearnedCooldowns()
    for k in pairs(learnedCd) do learnedCd[k] = nil end
end
function handlers.SPELLS_CHANGED() Relearn(); ForgetLearnedCooldowns(); RequestTalentRead() end
handlers.PLAYER_LEVEL_UP = handlers.SPELLS_CHANGED
handlers.LEARNED_SPELL_IN_SKILL_LINE = handlers.SPELLS_CHANGED
-- Talent changes (only with a talent timed DoT in the profile): the rank is read again out of combat.
function handlers.PLAYER_TALENT_UPDATE() RequestTalentRead() end
handlers.CHARACTER_POINTS_CHANGED = handlers.PLAYER_TALENT_UPDATE
handlers.TRAIT_CONFIG_UPDATED = handlers.PLAYER_TALENT_UPDATE
handlers.ACTIVE_TALENT_GROUP_CHANGED = handlers.PLAYER_TALENT_UPDATE

function handlers.PLAYER_ENTERING_WORLD()
    Relearn()
    if TalentsUnknown() then RequestTalentRead() end
    channel = nil
    overlayGlow = {}
    ResetLedger()
    OnTargetChanged()
    dirty = true
    playerDirty = true
    -- a loading screen strips no aura: unknown until the reconcile reads it again
    Seal.ledger, Seal.dirty = nil, true
    Seal.judgeSeen = false
    TryReconcile()
end

local PLAIN_EVENTS = {
    "PLAYER_TARGET_CHANGED", "PLAYER_REGEN_ENABLED", "PLAYER_ENTERING_WORLD", "SPELLS_CHANGED",
    "PLAYER_LEVEL_UP", "LEARNED_SPELL_IN_SKILL_LINE", "SPELL_ACTIVATION_OVERLAY_GLOW_SHOW",
    "SPELL_ACTIVATION_OVERLAY_GLOW_HIDE", "PLAYER_DEAD",
}
local TALENT_EVENTS = {
    "PLAYER_TALENT_UPDATE", "CHARACTER_POINTS_CHANGED", "TRAIT_CONFIG_UPDATED", "ACTIVE_TALENT_GROUP_CHANGED",
}
local PLAYER_EVENTS = {
    "UNIT_SPELLCAST_SENT", "UNIT_SPELLCAST_START", "UNIT_SPELLCAST_SUCCEEDED",
    "UNIT_SPELLCAST_FAILED", "UNIT_SPELLCAST_INTERRUPTED", "UNIT_SPELLCAST_CHANNEL_START",
    "UNIT_SPELLCAST_CHANNEL_UPDATE", "UNIT_SPELLCAST_CHANNEL_STOP",
}

local eventFrame = CreateFrame("Frame")
eventFrame:RegisterEvent("PLAYER_LOGIN")

local function Setup()
    if setupDone then return end
    local ok, _, token = pcall(UnitClass, "player")
    token = ok and PlainOf(token, "string") or nil
    if not token then return end
    setupDone = true
    classToken = token
    profile = Profiles[token]
    if not profile then return end

    FS.FrameHelpers.RegisterEvents(eventFrame, PLAIN_EVENTS)
    for key in pairs(profile.dots or EMPTY) do
        local t = Spells[key] and Spells[key].applyTalent
        if t then
            talentWanted = talentWanted or {}
            talentWanted[t.name] = true
        end
    end
    if talentWanted then
        FS.FrameHelpers.RegisterEvents(eventFrame, TALENT_EVENTS)
    end
    FS.FrameHelpers.RegisterEvents(eventFrame, PLAYER_EVENTS, "player")
    FS.FrameHelpers.RegisterEvent(eventFrame, "UNIT_AURA", "target", "player")

    -- A shown, parentless, region-less frame still gets OnUpdate (a HIDDEN frame does not),
    -- and draws nothing. Throttled to TICK seconds.
    local tickFrame = CreateFrame("Frame")
    local acc = 0
    tickFrame:SetScript("OnUpdate", function(_, elapsed)
        acc = acc + (elapsed or 0)
        if acc < TICK then return end
        acc = 0
        local ok2, err = pcall(Hud.Tick)
        if not ok2 then LogOnce("tick", err) end
    end)
    OnTargetChanged()
    dirty = true
    playerDirty = true
    Seal.ledger, Seal.dirty = nil, true
    RequestTalentRead()
end

eventFrame:SetScript("OnEvent", function(_, event, ...)
    if event == "PLAYER_LOGIN" then
        local ok, err = pcall(Setup)
        if not ok then LogOnce("setup", err) end
        return
    end
    if not profile then return end
    local fn = handlers[event]
    if fn then
        local ok, err = pcall(fn, ...)
        if not ok then LogOnce(event, err) end
    end
end)

pcall(Setup)
