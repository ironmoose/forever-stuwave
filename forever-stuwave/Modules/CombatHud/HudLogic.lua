-- Forever STUwave: combat HUD logic layer (data and decisions only, no frames or textures).
--
-- Part of the class-agnostic combat HUD: HudSpells.lua (dictionary) -> HudProfiles.lua
-- (per class rules) -> this file. The display is a later task and consumes only:
--
--   FS.Hud.GetState()   -> { active, class, inCombat, targetEpoch,
--                            row = { { key, icon, missing, remaining, expiresAt, duration,
--                                      onCd, cdRemaining, proc, isNext }, ... },
--                            next = { key, icon, glow } | nil,
--                            buffsMissing = { { key, icon }, ... },
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
--                          is part of Signature, so a switch between two mobs with identical timers
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
--                          which are coarse (Signature floors `remaining`).
--   FS.Hud.Subscribe(fn) / Unsubscribe(fn)   fn(state) runs at once on Subscribe, then when
--                          the state changes (0.2s tick; no subscribers, no state work).
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
-- SECRECY (probe-verified on 1.60.1):
--   * issecretvalue is checked (pcall'd; a missing or throwing check counts as secret)
--     before any API result is compared, indexed or used in arithmetic.
--   * By-spell aura lookups return ZERO values in combat, and GetAuraDataByIndex throws, so
--     the aura source of procActive and every aura scan (buffs, the DoT reconcile) are
--     out-of-combat only and nil in combat. C_Secrets.ShouldAurasBeSecret() true also
--     blocks them. A scan that returns zero values at index 1 is unreadable (nil), never
--     an empty list. UNPROBED: whether an EMPTY aura list reads as one nil or as zero
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
-- COOLDOWNS AND THE GLOBAL COOLDOWN. Whether GetSpellCooldown.isActive reads true during the
-- global cooldown on 1.60.1 is UNTESTED (an in-game probe will tell), and there is no
-- isOnGCD field. Three sources, in order:
--   1. A plain isOnGCD true is honoured when a client has one.
--   2. Plain startTime and duration (out of combat) are exact: a duration of at most
--      GCD_WINDOW is the global cooldown alone (ready), a longer one is a real cooldown
--      whose remaining time is start + duration - now. The ledger is not consulted.
--   3. In combat they are secret, so the ledger stands in: for GCD_WINDOW (1.6 s) after the
--      player's last own cast (a wand shot does not count, it is off the global cooldown), a
--      spell with no cooldown of its own (dictionary cooldown absent) reads ready even when
--      isActive is true. A spell with a real cooldown (Mind Blast 8 s) keeps isActive, except
--      that inside that window it reads ready unless OUR ledger says its own last cast was
--      less than its cooldown ago. The cost: in combat, a real cooldown that started before
--      the addon loaded reads ready for up to one GCD after another cast. Our cast times
--      survive a loading screen (GetTime is monotonic), so only a /reload loses them.
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
-- Righteousness (live recon, level 7): the aura id equals the cast id 21084 and sourceUnit is "player".
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
-- the in-game probe; a plain false from the overlay API is trusted in combat, but out of
-- combat a plain aura read overrides it.
-- A proc with `ready = key` is a cooldown tracker instead (Paladin Holy Strike / Judgement): it
-- reads CooldownState, so the heuristic above keeps it lit through the global cooldown. UNVERIFIED
-- in game: isActive during the GCD on 1.60.1, and Hammer of the Righteous sharing Holy Strike's
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
local GCD_WINDOW = 1.6       -- seconds after our own cast in which isActive may be the GCD
local PENDING_TTL = 60       -- seconds a cast's captured target is kept without a verdict

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

-- true / false / nil (cannot tell) for "does the player know this spell id".
local function IsKnownId(id)
    local fns = { IsPlayerSpell, IsSpellKnown, C_SpellBook and C_SpellBook.IsSpellKnown }
    local sawFalse, unreadable = false, false
    for i = 1, 3 do
        local fn = fns[i]
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

-- key -> { id, name, icon, known }. known is true, false or nil (could not be determined,
-- not cached). A name resolves to the player's current rank; ids are the fallback.
local function ResolveSpell(key)
    local def = Spells[key]
    if not def then return nil end
    local hit = spellCache[key]
    if hit then return hit end
    local indeterminate, firstIcon = false, nil
    local function try(x)
        local name, id, icon = SpellInfo(x)
        if type(x) == "number" then id = id or x end
        if not id then return nil end
        firstIcon = firstIcon or icon
        local known = IsKnownId(id)
        if known == nil then indeterminate = true end
        if known then return { id = id, name = name, icon = icon, known = true } end
        return nil
    end
    local found
    for _, n in ipairs(def.names or {}) do
        found = try(n)
        if found then break end
    end
    if not found then
        for _, id in ipairs(def.ids or {}) do
            found = try(id)
            if found then break end
        end
    end
    if found then
        spellCache[key] = found
        return found
    end
    local res = { icon = firstIcon, known = false }
    if indeterminate then
        res.known = nil    -- could not be determined: not cached, asked again next time
        return res
    end
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
-- OPEN QUESTION (UNPROBED, needs a live /fsprobe check; behaviour left unchanged on purpose):
-- out of combat, on a unit with NO matching auras at all, does GetAuraDataByIndex(unit, 1,
-- filter) return one nil or ZERO values? If it returns zero values, the `i == 1 and n == 0`
-- rule below reads a clean list as unreadable, which would suppress the Fortitude / Inner
-- Fire reminders on an unbuffed player (exactly when they matter) and skip the DoT
-- reconcile on a clean target. The probe: out of combat, strip the buffs or target a mob
-- with no debuffs of ours, then count the values returned at index 1.
-- The SEAL reconcile alone passes `zeroIsEmpty`: Parker's live /fsrecon class run (out of combat,
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
            -- so the Signature does not move twice per cast. A disagreeing aura replaces it, and
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
-- Own cast times for the global cooldown heuristic (CooldownState). Not part of the ledger
-- reset: GetTime is monotonic across a loading screen, so a cooldown we started stays known.
local lastCastAt, lastCastOf = nil, {}

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

-- Seconds a cast of `key` lasts: by the rank actually cast when the dictionary knows it.
local function ApplySeconds(def, spellID)
    return def.applyByRank and def.applyByRank[spellID] or def.apply
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
    local seconds = spec and def and ApplySeconds(def, spellID)
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
                local expires = (a.expires and a.expires > 0) and a.expires or (now + def.apply)
                local duration = (a.duration and a.duration > 0) and a.duration or def.apply
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
        return (e.expires - now) <= spec.pandemic * def.apply
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
-- between pushes, and the pushes are coarse (Signature floors `remaining`).
local function DotTiming(key)
    if not DotSpec(key) then return nil end
    local r = ResolveSpell(key)
    if not r or r.known ~= true then return nil end
    local e = ReadEntry(key)
    if not e then return nil end
    local def = Spells[key]
    return e.expires, e.duration or (def and def.apply)
end

-- ready (true/false/nil), remaining seconds (nil unless plain). See the GLOBAL COOLDOWN
-- HEURISTIC in the file header for the isActive-during-GCD handling below.
local function CooldownState(key)
    local r = ResolveSpell(key)
    if not r or r.known == nil then return nil end
    if r.known == false then return false end
    local fn = C_Spell and C_Spell.GetSpellCooldown
    if not fn then return nil end
    local ok, cd = pcall(fn, r.id)
    if not ok or not Plain(cd) or type(cd) ~= "table" then return nil end
    local active = PlainOf(cd.isActive, "boolean")
    if active == nil then return nil end
    if not active then return true end
    -- A plain isOnGCD, when the client provides one, says the cooldown is only the GCD.
    if PlainOf(cd.isOnGCD, "boolean") == true then return true end
    local start, dur, now = PlainOf(cd.startTime, "number"), PlainOf(cd.duration, "number"), Now()
    -- Plain timing (out of combat) is exact and needs no heuristic. A duration of zero says
    -- nothing, so it falls through.
    if start and dur and now and dur > 0 then
        if dur <= GCD_WINDOW then return true end    -- only the global cooldown
        local remaining = math.max(0, start + dur - now)
        if remaining <= 0 then return true end
        return false, remaining
    end
    if now and lastCastAt and now - lastCastAt >= 0 and now - lastCastAt < GCD_WINDOW then
        local own = (Spells[key] or {}).cooldown or 0
        local last = lastCastOf[key]
        if not (last and now - last < own) then return true end
    end
    return false
end

-- Spell-activation-overlay glow by spell key, from GLOW_SHOW (true) and GLOW_HIDE (false).
local overlayGlow = {}

-- true / false / nil from the overlay source: the last glow event for the proc's spell, else
-- IsSpellOverlayed. UNVERIFIED on Forever until the in-game probe has run.
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
-- looks like out of combat (one nil or zero values, the same UNPROBED question as in
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

-- missing? true / false / nil. `auras` is the player's aura list (PlayerAuras(); nil =
-- unreadable) and is only read for an aura-kind entry. The caller fetches it ONCE: a nil
-- here means unknown and must never trigger a second scan.
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
                return (a.expires - now) < entry.warnBelow
            end
            return false
        end
    end
    return true
end

local function SelfBuffEntry(key)
    for _, entry in ipairs(profile and profile.selfBuffs or {}) do
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
    return BuffMissing(entry, auras)
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

local function ChannelView()
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
    return {
        key = channel.key, done = done, ticks = ticks,
        cut = clipAfter ~= nil and done >= clipAfter,
    }
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

-- The first matching rule: key, glow, and which spells a live proc is lighting.
local function EvalRotation()
    local procFor = {}
    local procState = {}
    for key, spec in pairs(profile.procs or {}) do
        procState[key] = ProcActive(key) == true and spec or nil
    end
    for _, rule in ipairs(profile.rotation or {}) do
        for _, cond in ipairs(rule.when or {}) do
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
            for _, cond in ipairs(rule.when or {}) do
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

local function EmptyState()
    return {
        active = false, row = {}, buffsMissing = {}, procs = {}, inCombat = InCombat(),
        targetEpoch = targetEpoch,
    }
end

function Hud.GetState()
    local state = EmptyState()
    if not profile then return state end
    state.active = true
    state.class = classToken

    local nextKey, nextGlow, procFor, nextIcon = EvalRotation()
    if nextKey then state.next = { key = nextKey, icon = nextIcon, glow = nextGlow } end

    local cooldownSet = {}
    for _, k in ipairs(profile.cooldowns or {}) do cooldownSet[k] = true end

    for _, key in ipairs(profile.row or {}) do
        local r = ResolveSpell(key)
        if r and r.known == true then
            local e = { key = key, icon = r.icon, proc = procFor[key], isNext = nextKey == key }
            if DotSpec(key) then e.missing, e.remaining, e.expiresAt, e.duration = DotView(key) end
            if cooldownSet[key] then
                local ready, cdRemaining = CooldownState(key)
                if ready ~= nil then e.onCd = not ready end
                e.cdRemaining = cdRemaining
            end
            state.row[#state.row + 1] = e
        end
    end

    local auras, fetched
    for _, entry in ipairs(profile.selfBuffs or {}) do
        if entry.kind == nil and not fetched then
            fetched = true
            auras = PlayerAuras()
        end
        if BuffMissing(entry, auras) == true then
            local r = ResolveSpell(entry.spell)
            state.buffsMissing[#state.buffsMissing + 1] = { key = entry.spell, icon = r and r.icon }
        end
    end

    local procKeys = {}
    for key in pairs(profile.procs or {}) do procKeys[#procKeys + 1] = key end
    table.sort(procKeys)
    for _, key in ipairs(procKeys) do
        local spec = profile.procs[key]
        local r = spec.ready and ResolveSpell(spec.ready)
        -- a cooldown tracker for a spell the player does not know has no rung yet
        if not spec.ready or (r and r.known == true) then
            state.procs[#state.procs + 1] = {
                key = key, glow = spec.glow, active = ProcActive(key), icon = r and r.icon or nil,
            }
        end
    end

    if profile.resource and profile.resource.shards then state.shards = ItemCount() end
    state.channel = ChannelView()
    if profile.seals then
        local s = Seal.Read()
        if s then
            state.seal = {
                key = s.key, id = s.id, expiresAt = s.expiresAt, duration = s.duration,
                castAt = s.castAt,
            }
        else
            state.seal = s    -- false (no seal) or nil (unknown)
        end
        state.judgeAt = Seal.judgeAt
        local e = Seal.ReadJudged()
        if e then
            state.judged = { key = e.key, appliedAt = e.appliedAt, expiresAt = e.expires, duration = e.duration }
        else
            state.judged = e    -- false (none) or nil (unknown)
        end
    end
    return state
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

local function Signature(state)
    local parts = {
        state.active and "A" or "a", state.inCombat and "C" or "c", "t" .. tostring(state.targetEpoch),
    }
    for _, e in ipairs(state.row) do
        parts[#parts + 1] = table.concat({
            e.key, tostring(e.missing), tostring(e.onCd), tostring(e.proc), tostring(e.isNext),
            e.remaining and tostring(math.floor(e.remaining)) or "-",
            e.cdRemaining and tostring(math.floor(e.cdRemaining)) or "-", tostring(e.icon),
        }, ":")
    end
    parts[#parts + 1] = "n" .. (state.next and state.next.key or "-")
        .. (state.next and (tostring(state.next.glow) .. tostring(state.next.icon)) or "")
    for _, b in ipairs(state.buffsMissing) do parts[#parts + 1] = "b" .. b.key end
    for _, p in ipairs(state.procs) do parts[#parts + 1] = "p" .. p.key .. tostring(p.active) end
    parts[#parts + 1] = "s" .. tostring(state.shards)
    local c = state.channel
    parts[#parts + 1] = c and ("c" .. c.key .. c.done .. tostring(c.cut)) or "c-"
    -- the seal by key and cast time only: a running timer must not push every second
    local sl = state.seal
    if sl == nil then
        parts[#parts + 1] = "kunk"
    elseif sl == false then
        parts[#parts + 1] = "knone"
    else
        parts[#parts + 1] = "k" .. sl.key .. tostring(sl.castAt)
    end
    -- Judgement by cast time and the target's debuff by seal and application time (no running timer)
    local jd = state.judged
    parts[#parts + 1] = "j" .. tostring(state.judgeAt) .. (type(jd) == "table" and (jd.key .. tostring(jd.appliedAt)) or tostring(jd))
    return table.concat(parts, "|")
end

local subscribers = {}
local lastSig, pruneAt = nil, 0

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
    if #subscribers == 1 then lastSig = Signature(state) end
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
    TryReconcile()
    if now and now >= pruneAt then
        Prune(now)
        pruneAt = now + PRUNE_EVERY
    end
    if #subscribers == 0 then return end    -- nobody to tell: no state work
    local state = Hud.GetState()
    local sig = Signature(state)
    if sig == lastSig then return end
    lastSig = sig
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
    -- any own cast may start the GCD, except the wand
    if now and not (key and Spells[key].offGcd) then lastCastAt = now end
    if not key then return end
    lastCastOf[key] = now
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
    TryReconcile()
end

local function Relearn()
    spellCache = {}
end
handlers.SPELLS_CHANGED = Relearn
handlers.PLAYER_LEVEL_UP = Relearn
handlers.LEARNED_SPELL_IN_TAB = Relearn

function handlers.PLAYER_ENTERING_WORLD()
    Relearn()
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
    "PLAYER_LEVEL_UP", "LEARNED_SPELL_IN_TAB", "SPELL_ACTIVATION_OVERLAY_GLOW_SHOW",
    "SPELL_ACTIVATION_OVERLAY_GLOW_HIDE", "PLAYER_DEAD",
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

    for _, e in ipairs(PLAIN_EVENTS) do pcall(eventFrame.RegisterEvent, eventFrame, e) end
    for _, e in ipairs(PLAYER_EVENTS) do
        pcall(eventFrame.RegisterUnitEvent, eventFrame, e, "player")
    end
    pcall(eventFrame.RegisterUnitEvent, eventFrame, "UNIT_AURA", "target", "player")

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
