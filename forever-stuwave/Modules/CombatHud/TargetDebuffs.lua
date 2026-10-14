-- Forever STUwave: data service for the player's own debuffs on the target (FS.TargetDebuffs).
-- Entries are { id, name, icon, expires, duration, count, order }: an aura snapshot out of combat, an own-cast
-- ledger in combat. IN COMBAT it is an estimate: a resisted cast still counts, refreshes that are not casts (poison
-- procs, Deep Wounds, talents) are invisible, and a cast is timed from the last snapshot of that spell id or name,
-- else the SPELL_SECONDS / HudSpells tables (an unknown one has no expiry); out of combat the snapshot is exact.

local _, FS = ...

local TD = {}
FS.TargetDebuffs = TD

local MAX_AURAS = 40
local SCAN_DELAY = 0.1       -- UNIT_AURA bursts coalesce into one scan this long after the first
local PENDING_TTL = 60       -- seconds a SENT cast is remembered without a verdict
local STALE_AFTER = 30       -- a ledger target whose debuffs all ended this long ago is dropped
local NO_EXPIRY_AGE = 120    -- an entry with no known expiry is believed this long after it was written

-- The debuffs worth a row for each class, in display order. A name listed here is tracked from its first cast in
-- combat even with no SPELL_SECONDS length (it then shows "?" until a snapshot measures it); a name seen in any
-- snapshot is tracked whatever the class. A debuff is worth tracking when it is a damage over time, a slow or root,
-- an armor / attack power / spell vulnerability debuff, or a crowd control of 4 s or more that the player cast.
-- Left out on purpose: taunts (Taunt, Growl, Mocking Blow, Challenging Shout / Roar), interrupt lockouts (Earth
-- Shock, Kick, Counterspell, Shield Bash: they leave no aura), effects shorter than 4 s (Bash, Chastise, Confounding
-- Flash), ground and trap areas (Flamestrike, Blizzard, Rain of Fire, Freezing / Immolation Trap: the aura is
-- named after the trap or the target is not the one aimed at), pet abilities, weapon and talent procs with no cast
-- (Frostbrand Attack, Deep Wounds' refreshes, poisons), and Paladin Judgement, which the Seal module owns.
-- Priest and Warlock DoTs (Shadow Word: Pain, Devouring Plague, Corruption, Immolate, the banes, Siphon Life) are
-- timed by FS.HudSpells and are not repeated here. Rupture, Kidney Shot (the length follows the combo points) and
-- Fire Vulnerability (no length in the Forever tooltip) are listed WITHOUT a length: unverified.
local CLASS_DEBUFFS = {
    WARRIOR = { "Rend", "Deep Wounds", "Thunder Clap", "Sunder Armor", "Demoralizing Shout", "Hamstring", "Disarm",
        "Intimidating Shout" },
    ROGUE = { "Deadly Poison", "Crippling Poison", "Rupture", "Garrote", "Expose Armor", "Kidney Shot", "Cheap Shot",
        "Gouge", "Sap" },
    DRUID = { "Rake", "Rip", "Moonfire", "Faerie Fire", "Entangling Roots", "Demoralizing Roar", "Hibernate" },
    SHAMAN = { "Flame Shock", "Frost Shock" },
    HUNTER = { "Serpent Sting", "Hunter's Mark", "Scorpid Sting", "Concussive Shot", "Wing Clip", "Lacerate",
        "Scare Beast" },
    MAGE = { "Fireball", "Frostbolt", "Frost Nova", "Cone of Cold", "Polymorph", "Fire Vulnerability" },
    PALADIN = { "Hammer of Justice", "Turn Undead" },
    PRIEST = { "Holy Fire", "Starshards", "Hex of Weakness", "Psychic Scream", "Shackle Undead" },
    WARLOCK = { "Curse of the Elements", "Curse of Recklessness", "Curse of Weakness", "Curse of Tongues", "Fear",
        "Banish" },
}

-- Seconds a debuff lasts when the player casts it, so the FIRST cast in combat is timed before any snapshot has
-- taught the session. `apply` is the top rank (or the only length); `byRank` maps a cast rank id to its length for a
-- spell whose length follows the rank (a rank id it does not list is timed at `apply`, the top rank). Every length
-- below is read off the Forever spell pages (WoW Forever beta client build 1.60.1.70338) and checked 2026-10-14;
-- the pages are https://foreverdb.net/spell/<id>, the learn levels come from https://foreverdb.net/data/classes.json.
-- The cap is level 30, so ranks above it are listed only to keep the table complete. Nothing here is from classic
-- Wowhead. Rank ids are the classic ones the client reports on a cast.
--
-- Warrior: Rend 9/12/15/18/21 s and Thunder Clap 10/14/18/22/26/30 s by rank (Thunder Clap rank pages 6343, 8198,
--   8204, 8205, 11580, 11581), Sunder Armor 30 s, Hamstring 15 s (1715), Demoralizing Shout 45 s (all five ranks,
--   30 s in classic; 11556), Disarm 10 s (676), Intimidating Shout 8 s (5246; Improved Intimidating Shout adds
--   1 or 2 s, learned from the first snapshot). Checked 2026-10-08, the rest 2026-10-14.
-- Shaman: Flame Shock DoT 12 s on all six ranks (8050, 8052, 8053, 10447, 10448, 29228), Frost Shock slow 8 s on
--   all four (8056, 8058, 10472, 10473).
-- Hunter: Serpent Sting 15 s on all nine ranks (1978, 13549 to 13555, 25295), Hunter's Mark 2 min (1130, 14323,
--   14324, 14325), Concussive Shot 4 s (5116), Wing Clip 10 s (2974, 14267, 14268), Scorpid Sting 20 s (3043),
--   Lacerate bleed 21 s (24118 to 24120, 1299332; learned at level 30), Scare Beast 10/15/20 s (1513, 14326, 14327).
--   A second set of Serpent Sting ids (425728 to 425737, 12 s) has no class on its page; the class pages above
--   are the trainer ranks and are used here.
-- Mage: Frostbolt slow 5/6/6/7/7/8/8/9/9/9/9 s (116, 205, 837, 7322, 8406, 8407, 8408, 10179, 10180, 10181,
--   25304), Fireball DoT 4/6/6/8 s from rank 4 up (133, 143, 145, 3140, 8400, ...), Polymorph 20/30/40/50 s
--   (118, 12824, 12825, 12826), Frost Nova root 8 s on all four ranks (122, 865, 6131, 10230), Cone of Cold slow
--   6 s on all five (120, 8492, 10159, 10160, 10161).
-- Druid: Moonfire 9 s on rank 1 (8921), 12 s on ranks 2 to 10 (8924 to 9835), Rake 9 s on all four ranks (1822,
--   1823, 1824, 9904), Rip 12 s on all six (1079, 9492, 9493, 9752, 9894, 9896), Faerie Fire armor 40 s (770, 778,
--   9749, 9907), Entangling Roots 12/15/18/21/24/27 s (339, 1062, 5195, 5196, 9852, 9853), Hibernate 20/30/40 s
--   (2637, 18657, 18658), Demoralizing Roar 30 s on all five ranks (99, 1735, 9490, 9747, 9898).
-- Rogue: Garrote bleed 18 s on all six ranks (703, 8631, 8632, 8633, 11289, 11290), Expose Armor 30 s (8647, 8649,
--   8650, 11197, 11198), Gouge 4 s (1776, 1777, 8629, 11285, 11286), Sap 25/35/45 s (6770, 2070, 11297), Cheap Shot
--   4 s (1833).
-- Paladin: Hammer of Justice 3/4/5/6 s (853, 5588, 5589, 10308), Turn Undead 10/15/20 s (2878, 5627, 10326).
-- Priest: Holy Fire DoT 10 s on all eight ranks (14914, 15262, 15263, ..., 15261), Psychic Scream fear 8 s
--   (8122, 8124, 10888, 10890), Starshards DoT 6 s (10797, 19296, 19299, ...), Hex of Weakness 2 min (9035, 19281,
--   19282), Shackle Undead 30/40/50 s (9484, 9485, 10955).
-- Warlock: Curse of Weakness 2 min (702, 1108, 6205, ...), Curse of Recklessness 2 min (704, 7658, 7659, 11717),
--   Curse of the Elements 5 min (440892, 1311676, 1311677, 1311680), Curse of Tongues 30 s (1714, 11719), Fear
--   10/15/20 s (5782, 6213, 6215), Banish 20/30 s (710, 18647).
-- Deep Wounds has no cast, so no entry. Nothing here repeats a HudSpells entry.
local SPELL_SECONDS = {
    -- Warrior
    ["Rend"] = { apply = 21, byRank = { [772] = 9, [6546] = 12, [6547] = 15, [6548] = 18, [11572] = 21, [11573] = 21, [11574] = 21 } },
    ["Thunder Clap"] = { apply = 30, byRank = { [6343] = 10, [8198] = 14, [8204] = 18, [8205] = 22, [11580] = 26, [11581] = 30 } },
    ["Sunder Armor"] = { apply = 30 },
    ["Hamstring"] = { apply = 15 },
    ["Demoralizing Shout"] = { apply = 45 },
    ["Disarm"] = { apply = 10 },
    ["Intimidating Shout"] = { apply = 8 },
    -- Shaman
    ["Flame Shock"] = { apply = 12 },
    ["Frost Shock"] = { apply = 8 },
    -- Hunter
    ["Serpent Sting"] = { apply = 15 },
    ["Hunter's Mark"] = { apply = 120 },
    ["Concussive Shot"] = { apply = 4 },
    ["Wing Clip"] = { apply = 10 },
    ["Scorpid Sting"] = { apply = 20 },
    ["Lacerate"] = { apply = 21 },
    ["Scare Beast"] = { apply = 20, byRank = { [1513] = 10, [14326] = 15, [14327] = 20 } },
    -- Mage
    ["Frostbolt"] = { apply = 9, byRank = { [116] = 5, [205] = 6, [837] = 6, [7322] = 7, [8406] = 7, [8407] = 8, [8408] = 8 } },
    ["Fireball"] = { apply = 8, byRank = { [133] = 4, [143] = 6, [145] = 6 } },
    ["Polymorph"] = { apply = 50, byRank = { [118] = 20, [12824] = 30, [12825] = 40, [12826] = 50 } },
    ["Frost Nova"] = { apply = 8 },
    ["Cone of Cold"] = { apply = 6 },
    -- Druid
    ["Moonfire"] = { apply = 12, byRank = { [8921] = 9 } },
    ["Rake"] = { apply = 9 },
    ["Rip"] = { apply = 12 },
    ["Faerie Fire"] = { apply = 40 },
    ["Entangling Roots"] = { apply = 27, byRank = { [339] = 12, [1062] = 15, [5195] = 18, [5196] = 21, [9852] = 24, [9853] = 27 } },
    ["Hibernate"] = { apply = 40, byRank = { [2637] = 20, [18657] = 30, [18658] = 40 } },
    ["Demoralizing Roar"] = { apply = 30 },
    -- Rogue
    ["Garrote"] = { apply = 18 },
    ["Expose Armor"] = { apply = 30 },
    ["Gouge"] = { apply = 4 },
    ["Sap"] = { apply = 45, byRank = { [6770] = 25, [2070] = 35, [11297] = 45 } },
    ["Cheap Shot"] = { apply = 4 },
    -- Paladin
    ["Hammer of Justice"] = { apply = 6, byRank = { [853] = 3, [5588] = 4, [5589] = 5, [10308] = 6 } },
    ["Turn Undead"] = { apply = 20, byRank = { [2878] = 10, [5627] = 15, [10326] = 20 } },
    -- Priest
    ["Holy Fire"] = { apply = 10 },
    ["Psychic Scream"] = { apply = 8 },
    ["Starshards"] = { apply = 6 },
    ["Hex of Weakness"] = { apply = 120 },
    ["Shackle Undead"] = { apply = 50, byRank = { [9484] = 30, [9485] = 40, [10955] = 50 } },
    -- Warlock
    ["Curse of Weakness"] = { apply = 120 },
    ["Curse of Recklessness"] = { apply = 120 },
    ["Curse of the Elements"] = { apply = 300 },
    ["Curse of Tongues"] = { apply = 30 },
    ["Fear"] = { apply = 20, byRank = { [5782] = 10, [6213] = 15, [6215] = 20 } },
    ["Banish"] = { apply = 30, byRank = { [710] = 20, [18647] = 30 } },
}

local EMPTY = {}
local list = EMPTY                  -- the current entries, sorted; replaced (never edited) by Rebuild
local subs, subCount = {}, 0
local enabled, suppress, scanQueued, areaHooked, readableHooked, hudOn = false, false, false, false, false, false
local epoch = 0                     -- bumped on every target change
local lastTakes                    -- the last FS.TargetTakesDots answer
local ledger = {}                   -- target key -> { [name] = entry }
local pending = {}                  -- castGUID -> { key, at }
local hudEntries, hudNames          -- the Hud's DoT rows as entries, and every name those DoTs go by
local learnedDuration, maxStack, known, seenOrder, seenCount = {}, {}, {}, {}, 0
local learnedById = {}                  -- spell id -> seconds, from a readable snapshot (session only)
local hudSeconds                    -- name -> HudSpells def, built on first use
local classToken, classSet, classOrder
local plainFrame, targetFrame, playerFrame

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "targetdebuffs_" .. key, "|cffff4488Forever STUwave|r: target debuffs: " .. tostring(msg))
    end
end

local function Plain(v)
    local f = FS.IsSecret
    return not (f and f(v))
end

local function PlainOf(v, kind)
    if not Plain(v) then return nil end
    if type(v) ~= kind or v ~= v then return nil end
    return v
end

local function OnPlayer(unit) return PlainOf(unit, "string") == "player" end

-------------------------------------------------------------------------------
-- Lookups
-------------------------------------------------------------------------------

local function Class()
    if classToken then return classToken end
    if type(UnitClass) ~= "function" then return nil end
    local ok, _, token = pcall(UnitClass, "player")
    token = ok and PlainOf(token, "string") or nil
    if not token then return nil end
    classToken, classSet, classOrder = token, {}, {}
    for i, n in ipairs(CLASS_DEBUFFS[token] or EMPTY) do classSet[n], classOrder[n] = true, i end
    return classToken
end

local function OrderOf(name)
    Class()
    if classOrder and classOrder[name] then return classOrder[name] end
    if not seenOrder[name] then
        seenCount = seenCount + 1
        seenOrder[name] = seenCount
    end
    return 100 + seenOrder[name]
end

local function HudDef(name)
    if not hudSeconds then
        hudSeconds = {}
        for _, def in pairs(FS.HudSpells or EMPTY) do
            if def.apply and not def.self then
                for _, n in ipairs(def.names or EMPTY) do hudSeconds[n] = def end
            end
        end
    end
    return hudSeconds[name]
end

-- Seconds a cast of `spellID` lasts, best source first: what a snapshot measured for this exact id, the rank table
-- for this exact id, what a snapshot measured for the name (another rank, the player's talents), then the top rank.
-- For a spell with a rank table, an id the table does not list is taken for a newer rank: the name's measurement
-- (it may be a lower rank's, or lengthened by a talent) never goes below the top rank.
local function DurationOf(name, spellID)
    if spellID and learnedById[spellID] then return learnedById[spellID] end
    local def, own = HudDef(name), SPELL_SECONDS[name]
    local byRank = spellID and (def and def.applyByRank and def.applyByRank[spellID] or own and own.byRank and own.byRank[spellID])
    if byRank then return byRank end
    local top = def and def.apply or own and own.apply or nil
    local learned = learnedDuration[name]
    if learned and top and ((def and def.applyByRank) or (own and own.byRank)) then return math.max(learned, top) end
    return learned or top
end

local function Tracks(name)
    Class()
    return known[name] or (classSet and classSet[name]) or SPELL_SECONDS[name] ~= nil or HudDef(name) ~= nil
end

-- name, icon of a spell id; plain values only.
local function SpellInfo(id)
    local fn = C_Spell and C_Spell.GetSpellInfo
    if fn then
        local ok, info = pcall(fn, id)
        if ok and Plain(info) and type(info) == "table" then
            return PlainOf(info.name, "string"), PlainOf(info.iconID, "number")
        end
        return nil
    end
    if GetSpellInfo then
        local ok, name, _, icon = pcall(GetSpellInfo, id)
        if ok then return PlainOf(name, "string"), PlainOf(icon, "number") end
    end
    return nil
end

-- The ledger key of the current target: its GUID, or the epoch when the GUID is secret; nil with no target.
local function TargetKey()
    if FS.HasTarget and not FS.HasTarget() then return nil end
    local ok, g = pcall(UnitGUID, "target")
    if not ok then return nil end
    if not Plain(g) then return "e" .. epoch end
    if type(g) == "string" then return g end
    return nil
end

local function TakesDots()
    if FS.TargetTakesDots then return FS.TargetTakesDots() end
    return true
end

local function IsJudgement(e)
    for _, def in pairs(FS.HudSpells or EMPTY) do
        if def.judgement then
            for _, id in ipairs(def.ids or EMPTY) do
                if id == e.id then return true end
            end
        end
    end
    return e.name:find("^Judg") ~= nil      -- English fallback: aura ids differ from the cast id
end

-- The Seal module carries Judgement while the Class Module area is in use.
local function Excluded(e)
    if Class() ~= "PALADIN" or not IsJudgement(e) then return false end
    local areas = FS.GunsightAreas
    return areas ~= nil and areas.AreaOf ~= nil and areas.AreaOf("class") ~= nil
end

-------------------------------------------------------------------------------
-- The list
-------------------------------------------------------------------------------

local function ByOrder(a, b)
    if a.order ~= b.order then return a.order < b.order end
    return a.name < b.name
end

local function Rebuild()
    if suppress then return end
    local out = {}
    lastTakes = TakesDots()
    if lastTakes then
        for _, e in ipairs(hudEntries or EMPTY) do out[#out + 1] = e end
        local key = TargetKey()
        for name, e in pairs(key and ledger[key] or EMPTY) do
            if not (hudNames and hudNames[name]) and not Excluded(e) then out[#out + 1] = e end
        end
        table.sort(out, ByOrder)
    end
    list = out
    for i = 1, #subs do
        local ok, err = pcall(subs[i], out, epoch)
        if not ok then LogOnce("subscriber", err) end
    end
end

-- Source 1: the player's harmful auras on the target, read only while auras are readable.
local function Report(label, err) LogOnce("read", tostring(label) .. ": " .. tostring(err)) end

local function ScanInto(bucket, prevBucket)
    local read = FS.FrameHelpers and FS.FrameHelpers.ReadAuraSlot
    if not read then error("FrameHelpers.ReadAuraSlot is missing") end
    for i = 1, MAX_AURAS do
        local a = read("target", i, "HARMFUL", Report)
        if not (a and Plain(a) and type(a) == "table") then break end
        local name = PlainOf(a.name, "string")
        if name and PlainOf(a.caster, "string") == "player" then
            local duration, expires = PlainOf(a.duration, "number"), PlainOf(a.expirationTime, "number")
            local count = math.floor(PlainOf(a.count, "number") or 0)
            if count < 1 then count = 1 end
            local entry = { id = PlainOf(a.spellId, "number"), name = name, icon = PlainOf(a.icon, "number") or PlainOf(a.icon, "string"),
                count = count, order = OrderOf(name), at = GetTime() }
            if duration and duration > 0 then
                entry.duration = duration
                learnedDuration[name] = duration
                if entry.id then learnedById[entry.id] = duration end
                if expires and expires > 0 then entry.expires = expires end
            end
            if not entry.duration then
                -- no usable duration (zero or secret): keep what the ledger believed while it still holds, and the tables
                -- only when the ledger never saw this aura. An expired ledger entry with the aura still up means an
                -- untracked refresh, so it stays unknown ("?") rather than getting a fresh full-length timer. A plain
                -- duration with a secret expiry stays unknown too (the expiry is the secret, not guessed).
                local prev = prevBucket and prevBucket[name]
                if prev then
                    if prev.expires and prev.expires > entry.at then
                        entry.expires, entry.duration = prev.expires, prev.duration
                    end
                else
                    local d = DurationOf(name, entry.id)
                    if d then entry.duration, entry.expires = d, entry.at + d end
                end
            end
            if count > (maxStack[name] or 0) then maxStack[name] = count end
            known[name] = true
            bucket[name] = entry
        end
    end
end

-- true when the ledger of the current target was replaced by a snapshot.
local function Scan()
    local key = TargetKey()
    if not key or not (FS.AurasReadable and FS.AurasReadable()) then return false end
    local bucket = {}
    local ok, err = pcall(ScanInto, bucket, ledger[key])
    if not ok then LogOnce("scan", err); return false end
    ledger[key] = bucket
    return true
end

local function ScanAndRebuild()
    Scan()
    Rebuild()
end

local function FlushScan()
    scanQueued = false
    if enabled then ScanAndRebuild() end
end

local function QueueScan()
    if scanQueued or not (FS.AurasReadable and FS.AurasReadable()) then return end
    if not (C_Timer and C_Timer.After) then ScanAndRebuild(); return end
    scanQueued = true
    C_Timer.After(SCAN_DELAY, FlushScan)
end

-- Drops targets that no longer matter; `keepKey` stays whatever its age.
local function Prune(keepKey)
    local now = GetTime()
    for key, bucket in pairs(ledger) do
        if key ~= keepKey then
            local live = false
            for _, e in pairs(bucket) do
                local believed = e.expires and e.expires > now - STALE_AFTER
                    or not e.expires and now - (e.at or 0) < math.max(NO_EXPIRY_AGE, e.duration or 0)
                if believed then live = true end
            end
            if not live then ledger[key] = nil end
        end
    end
    for id, p in pairs(pending) do
        if now - p.at > PENDING_TTL then pending[id] = nil end
    end
end

-------------------------------------------------------------------------------
-- Source 2: the own-cast ledger
-------------------------------------------------------------------------------

-- A cast aimed at a unit whose name differs from the target's ([@mouseover], [@focus]) is not attributed.
local function AimedElsewhere(targetName)
    local sent = PlainOf(targetName, "string")
    if not sent or sent == "" then return false end
    local ok, current = pcall(UnitName, "target")
    current = ok and PlainOf(current, "string") or nil
    return current ~= nil and current ~= "" and current ~= sent
end

local function OnSent(unit, targetName, castGUID)
    if not OnPlayer(unit) then return end
    local guid = PlainOf(castGUID, "string")
    if not guid then return end
    pending[guid] = { key = (not AimedElsewhere(targetName)) and TargetKey() or nil, at = GetTime() }
end

local function DropPending(unit, castGUID)
    local guid = PlainOf(castGUID, "string")
    if OnPlayer(unit) and guid then pending[guid] = nil end
end

local function OnSucceeded(unit, castGUID, spellID)
    if not OnPlayer(unit) then return end
    local id = PlainOf(spellID, "number")
    local guid = PlainOf(castGUID, "string")
    local p = guid and pending[guid]
    if guid then pending[guid] = nil end
    if not id then return end
    local key
    if p then key = p.key else key = TargetKey() end
    if not key then return end
    local name, icon = SpellInfo(id)
    if not (name and Tracks(name)) then return end
    local now = GetTime()
    local bucket = ledger[key]
    if not bucket then bucket = {}; ledger[key] = bucket end
    local prev = bucket[name]
    local count = 1
    if prev and prev.count and (not prev.expires or prev.expires > now) then
        count = math.min(prev.count + 1, maxStack[name] or prev.count)
    end
    local duration = DurationOf(name, id)
    bucket[name] = { id = id, name = name, icon = icon, count = count, order = OrderOf(name),
        duration = duration, expires = duration and now + duration or nil, at = now }
    if key == TargetKey() then
        Rebuild()
        QueueScan()                 -- readable: the snapshot corrects a resisted cast
    end
end

-------------------------------------------------------------------------------
-- The Hud's DoT ledger (Priest, Warlock): better than either source for a profile DoT
-------------------------------------------------------------------------------

local function HudDots()
    local Hud = FS.Hud
    if type(Hud) ~= "table" or type(Hud.GetProfile) ~= "function" then return nil end
    local ok, profile = pcall(Hud.GetProfile)
    if not ok or type(profile) ~= "table" then return nil end
    local dots = profile.dots
    if type(dots) == "table" and next(dots) ~= nil then return dots end
    return nil
end

local function OnHud(state)
    local dots = HudDots()
    hudEntries, hudNames = nil, nil
    if dots and type(state) == "table" and state.active and type(state.row) == "table" then
        hudEntries, hudNames = {}, {}
        local now = GetTime()
        for key in pairs(dots) do
            for _, n in ipairs(FS.HudSpells and FS.HudSpells[key] and FS.HudSpells[key].names or EMPTY) do hudNames[n] = true end
        end
        for _, e in ipairs(state.row) do
            local key = type(e) == "table" and PlainOf(e.key, "string")
            local remaining = key and dots[key] and PlainOf(e.remaining, "number")
            if remaining then
                local expires = PlainOf(e.expiresAt, "number")
                if not expires and remaining > 0 then expires = now + remaining end
                local live = expires ~= nil and expires > now
                local def = FS.HudSpells and FS.HudSpells[key]
                local name = def and def.names and def.names[1] or key
                local FH = FS.FrameHelpers
                hudEntries[#hudEntries + 1] = {
                    name = name,
                    id = FH and FH.SpellIDForName and FH.SpellIDForName(name) or nil,   -- plain: the dot's tooltip spell
                    icon = PlainOf(e.icon, "number") or PlainOf(e.icon, "string"),
                    expires = live and expires or 0, duration = live and PlainOf(e.duration, "number") or nil,
                    count = 1, order = #hudEntries + 1,
                }
            end
        end
    end
    Rebuild()
end

local function SyncHud()
    local want = enabled and HudDots() ~= nil
    if want and not hudOn then
        hudOn = true
        FS.Hud.Subscribe(OnHud)
    elseif not want and hudOn then
        hudOn = false
        if FS.Hud and FS.Hud.Unsubscribe then FS.Hud.Unsubscribe(OnHud) end
        hudEntries, hudNames = nil, nil
    end
end

-------------------------------------------------------------------------------
-- Events
-------------------------------------------------------------------------------

local handlers = {}

function handlers.PLAYER_TARGET_CHANGED()
    epoch = epoch + 1
    hudEntries = nil                -- the Hud has not pushed for this target yet
    Prune(TargetKey())
    ScanAndRebuild()
end

function handlers.PLAYER_ENTERING_WORLD()
    epoch = epoch + 1
    ledger, pending = {}, {}
    SyncHud()
    ScanAndRebuild()
end

function handlers.PLAYER_REGEN_ENABLED()
    if Scan() then Prune(TargetKey()) end
    Rebuild()
end

function handlers.UNIT_AURA(unit)
    if PlainOf(unit, "string") == "target" then QueueScan() end
end

local function OnTargetState(unit)
    if PlainOf(unit, "string") ~= "target" then return end
    if TakesDots() ~= lastTakes then Rebuild() end
end
handlers.UNIT_HEALTH, handlers.UNIT_FLAGS, handlers.UNIT_FACTION = OnTargetState, OnTargetState, OnTargetState

handlers.UNIT_SPELLCAST_SENT = OnSent
handlers.UNIT_SPELLCAST_SUCCEEDED = OnSucceeded
handlers.UNIT_SPELLCAST_FAILED = DropPending
handlers.UNIT_SPELLCAST_INTERRUPTED = DropPending

local function OnEvent(_, event, ...)
    local h = handlers[event]
    if not h then return end
    local ok, err = pcall(h, ...)
    if not ok then LogOnce("event_" .. event, err) end
end

local PLAIN_EVENTS = { "PLAYER_TARGET_CHANGED", "PLAYER_ENTERING_WORLD", "PLAYER_REGEN_ENABLED" }
local TARGET_EVENTS = { "UNIT_AURA", "UNIT_HEALTH", "UNIT_FLAGS", "UNIT_FACTION" }
local PLAYER_EVENTS = { "UNIT_SPELLCAST_SENT", "UNIT_SPELLCAST_SUCCEEDED", "UNIT_SPELLCAST_FAILED", "UNIT_SPELLCAST_INTERRUPTED" }

local function Register(frame, events, unit)
    for _, e in ipairs(events) do
        if unit and frame.RegisterUnitEvent then
            pcall(frame.RegisterUnitEvent, frame, e, unit)
        else
            frame:RegisterEvent(e)
        end
    end
end

local function Unregister(frame, events)
    for _, e in ipairs(events) do frame:UnregisterEvent(e) end
end

local function Enable()
    enabled = true
    if not plainFrame then
        plainFrame, targetFrame, playerFrame = CreateFrame("Frame"), CreateFrame("Frame"), CreateFrame("Frame")
        for _, f in ipairs({ plainFrame, targetFrame, playerFrame }) do f:SetScript("OnEvent", OnEvent) end
    end
    Register(plainFrame, PLAIN_EVENTS)
    Register(targetFrame, TARGET_EVENTS, "target")
    Register(playerFrame, PLAYER_EVENTS, "player")
    if FS.OnAurasReadable and not readableHooked then
        readableHooked = true
        FS.OnAurasReadable(function() if enabled then ScanAndRebuild() end end)
    end
    local areas = FS.GunsightAreas
    if not areaHooked and areas and areas.OnAreaChanged then
        areaHooked = true
        -- a "gate" edge (a class host hid or showed with the target) changes no assignment, and the target handler rescans anyway
        areas.OnAreaChanged(function(reason) if enabled and reason ~= "gate" then Rebuild() end end)
    end
    suppress = true
    SyncHud()
    Scan()
    suppress = false
    Rebuild()
end

local function Disable()
    enabled = false
    Unregister(plainFrame, PLAIN_EVENTS)
    Unregister(targetFrame, TARGET_EVENTS)
    Unregister(playerFrame, PLAYER_EVENTS)
    SyncHud()
    ledger, pending, list = {}, {}, EMPTY
end

-------------------------------------------------------------------------------
-- API
-------------------------------------------------------------------------------

-- fn(list, epoch) runs at once and after every change; the list is shared and read only.
function TD.Subscribe(fn)
    if type(fn) ~= "function" then return end
    subs[#subs + 1] = fn
    subCount = subCount + 1
    if subCount == 1 then
        Enable()
    else
        local ok, err = pcall(fn, list, epoch)
        if not ok then LogOnce("subscriber", err) end
    end
end

function TD.Unsubscribe(fn)
    for i = #subs, 1, -1 do
        if subs[i] == fn then
            table.remove(subs, i)
            subCount = subCount - 1
        end
    end
    if subCount == 0 and enabled then Disable() end
end

function TD.Get() return list end

function TD.Epoch() return epoch end
