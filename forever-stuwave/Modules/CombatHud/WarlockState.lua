-- Forever STUwave: the Warlock's demon, Life Tap cue and summon ledger, as plain state for the Gunsight Warlock module
--
-- FACTS (every number the module guesses with sits in TUNING; class tuning moves between builds, sources are on each line):
--   * Soul shards are an item (id 6265) and the Hud already pushes their count (state.shards); this file does not read them.
--   * Every demon except the Imp costs one shard to summon (wowfdb Warlock utility, updated 2026-11-15). The Succubus and the
--     Incubus are one line, "Sayaad" in the class guides. Felguard is not in Forever.
--   * Shadow Trance and Decimation last 10 s (Wowhead Forever spell pages 17941 and 440873). Their windows are started by the
--     Hud's procs (FS.Hud state.procs), not here.
--   * Life Tap has no mana cost and no cooldown (spell 11689 flags); it is a plain cast of the player's own.
--
-- WHAT THE CLIENT LETS US READ (12.0 engine; see the wow-addon-secret-values notes). NONE of the Warlock reads below has been
-- probed on this client (the probes were a Priest), so every one is guarded and falls back to "unknown", never to a guess:
--   * Is a demon out: UnitExists("pet") and UnitIsDead("pet"), a plain boolean when readable. Anything else is "unknown".
--   * Which demon: UnitCreatureFamily("pet") when it is a plain string, else the name of the last Summon the player cast
--     (UNIT_SPELLCAST_SUCCEEDED, a plain spell id of the player's own cast).
--   * A summon in progress: UNIT_SPELLCAST_START of a Summon spell, until its STOP, FAILED, INTERRUPTED or SUCCEEDED.
--   * "A Shadow Bolt cannot be paid": the second return of C.Spell.IsSpellUsable (insufficient power), when it is a plain
--     boolean. A secret answer is nil and shows no cue. The player's own mana is never read.
--   * Drain Soul and Life Tap known: C_Spell.GetSpellInfo by name returns a table only for a spell in the book.
--
-- API: Start(), Refresh(), Tick(now), Get() (the live table, never written by a caller), Subscribe(fn) / Unsubscribe(fn),
-- Cue(key) -> boolean (the player's switch for a cue family), DEMON_OF(name) -> key | nil, COST[key], SETTINGS.
--   data.pet     "alive" | "none" | "unknown"
--   data.demon   "imp" | "voidwalker" | "sayaad" | "felhunter" | nil (nothing known yet)
--   data.casting true while a Summon cast bar is up, else false
--   data.noMana  true | false | nil (nil = cannot tell)
--   data.summonAt GetTime of the player's last Summon cast, nil before one; data.tapAt the same for Life Tap
--   data.dead    true while the player is a corpse or a ghost (no cue is drawn)
--   data.drainKnown, data.tapKnown   true | false
--   data.summonKnown   true | false: any Summon in the book (a new Warlock has none until the level 4 Imp quest)
-- A listener is called fn(reason) with "pet", "cast", "tap", "mana", "dead", "learn".

local _, FS = ...

FS.WarlockState = FS.WarlockState or {}
local State = FS.WarlockState

local IsSecret = FS.IsSecret or function() return false end

local TUNING = {
    POLL = 0.25,                         -- s between pet and mana re-reads
    SUMMON_GRACE = 4,                    -- s after a Summon cast in which a shard that vanishes is the demon binding
}
State.TUNING = TUNING

local DEMONS = { "imp", "voidwalker", "sayaad", "felhunter" }
State.DEMONS = DEMONS
-- shards a summon costs (wowfdb Warlock utility, 2026-11-15)
State.COST = { imp = 0, voidwalker = 1, sayaad = 1, felhunter = 1 }
-- creature family or spell name fragment (lower case) -> demon key
local FRAGMENTS = { { "imp", "imp" }, { "voidwalker", "voidwalker" }, { "succubus", "sayaad" }, { "incubus", "sayaad" },
    { "sayaad", "sayaad" }, { "felhunter", "felhunter" } }

-- the player's switches (the Gunsight page shows them for a Warlock); every cue and sub-part is optional
local SETTINGS = {
    summon = { key = "gunsight.warlock.cue.summon", default = true, label = "Demon cue",
        tip = "SUMMON on the Warlock module when no demon is out, with the shard it costs. Turn it off for a build that keeps no demon (Demonic Sacrifice)." },
    procs = { key = "gunsight.warlock.cue.procs", default = true, label = "Proc cues",
        tip = "BOLT for a free instant Shadow Bolt (Nightfall) and FIRE for a free fast Soul Fire (Decimation), each with a bar for the 10 s window." },
    tap = { key = "gunsight.warlock.cue.tap", default = true, label = "Life Tap cue",
        tip = "TAP when your next Shadow Bolt cannot be paid. It does not know your health: look at the bar before you tap." },
    drain = { key = "gunsight.warlock.cue.drain", default = true, label = "Drain Soul cue",
        tip = "DRAIN when you hold fewer than three soul shards, and REAPING while the channel runs. The shard count stays either way." },
}
State.SETTINGS = SETTINGS
State.ORDER = { "summon", "procs", "tap", "drain" }
if FS.Config and FS.Config.RegisterDefault then
    for _, name in ipairs(State.ORDER) do FS.Config.RegisterDefault(SETTINGS[name].key, SETTINGS[name].default) end
end

-- True for a Warlock (a readable class token), the Gunsight page shows the switches only then.
function State.Applies()
    if type(UnitClass) ~= "function" then return false end
    local ok, _, token = pcall(UnitClass, "player")
    return ok and not IsSecret(token) and token == "WARLOCK"
end

function State.Cue(name)
    local def = SETTINGS[name]
    if not def then return true end
    local cfg = FS.Config
    if cfg and cfg.Get then
        local v = cfg.Get(def.key)
        if v == false then return false end
    end
    return true
end

local data = {
    pet = "unknown", demon = nil, casting = false, noMana = nil, summonAt = nil, tapAt = nil, dead = false,
    drainKnown = false, tapKnown = false, summonKnown = false,
}
State.data = data
function State.Get() return data end

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "warlockstate_" .. key, "|cffff4488Forever STUwave|r: warlock state: " .. tostring(msg))
    end
end

local listeners = {}
local function Notify(reason)
    for i = 1, #listeners do
        local ok, err = pcall(listeners[i], reason)
        if not ok then LogOnce("listener", err) end
    end
end

function State.Subscribe(fn)
    for i = 1, #listeners do if listeners[i] == fn then return end end
    listeners[#listeners + 1] = fn
end

function State.Unsubscribe(fn)
    for i = #listeners, 1, -1 do if listeners[i] == fn then table.remove(listeners, i) end end
end

-- A plain string, else nil (a secret, a number or a missing value).
local function PlainString(v)
    if IsSecret(v) or type(v) ~= "string" or v == "" then return nil end
    return v
end

local function PlainBool(v)
    if IsSecret(v) or type(v) ~= "boolean" then return nil end
    return v
end

-- A demon key from a creature family or a spell name, by fragment; nil when it is none of ours.
function State.DEMON_OF(name)
    local s = PlainString(name)
    if not s then return nil end
    s = string.lower(s)
    for i = 1, #FRAGMENTS do
        if string.find(s, FRAGMENTS[i][1], 1, true) then return FRAGMENTS[i][2] end
    end
    return nil
end

-- The name of a spell id: the string, or nil.
local function SpellName(id)
    if IsSecret(id) or type(id) ~= "number" then return nil end
    local api = C_Spell
    if api and api.GetSpellName then
        local ok, name = pcall(api.GetSpellName, id)
        if ok then return PlainString(name) end
    elseif type(GetSpellInfo) == "function" then
        local ok, name = pcall(GetSpellInfo, id)
        if ok then return PlainString(name) end
    end
    return nil
end

-- A spell in the player's book by name: its id, or nil.
local function BookId(name)
    local api = C_Spell
    if not (api and api.GetSpellInfo) then return nil end
    local ok, info = pcall(api.GetSpellInfo, name)
    if not ok or IsSecret(info) or type(info) ~= "table" then return nil end
    local id = info.spellID
    if IsSecret(id) or type(id) ~= "number" then return nil end
    return id
end

local boltId
local SUMMONS = { "Summon Imp", "Summon Voidwalker", "Summon Succubus", "Summon Incubus", "Summon Felhunter" }

-- Re-reads what the book says: Drain Soul, Life Tap, any Summon, and the Shadow Bolt id the mana read uses.
local function ReadBook()
    local drain, tap = BookId("Drain Soul") ~= nil, BookId("Life Tap") ~= nil
    local summon = false
    for i = 1, #SUMMONS do
        if BookId(SUMMONS[i]) then summon = true; break end
    end
    boltId = BookId("Shadow Bolt")
    if drain ~= data.drainKnown or tap ~= data.tapKnown or summon ~= data.summonKnown then
        data.drainKnown, data.tapKnown, data.summonKnown = drain, tap, summon
        Notify("learn")
    end
end

local function ReadDead()
    local dead = false
    if type(UnitIsDeadOrGhost) == "function" then
        local ok, v = pcall(UnitIsDeadOrGhost, "player")
        dead = ok and PlainBool(v) == true
    end
    if dead ~= data.dead then
        data.dead = dead
        Notify("dead")
    end
end

-- Whether a demon is out, and which. "unknown" when the client will not say.
local function ReadPet()
    local pet = "unknown"
    if type(UnitExists) == "function" then
        local ok, exists = pcall(UnitExists, "pet")
        if ok then exists = PlainBool(exists) else exists = nil end      -- not `and/or`: a plain false must stay false
        if exists == false then
            pet = "none"
        elseif exists == true then
            pet = "alive"
            if type(UnitIsDead) == "function" then
                local okd, dead = pcall(UnitIsDead, "pet")
                if okd and PlainBool(dead) == true then pet = "none" end
            end
        end
    end
    if pet == "alive" and type(UnitCreatureFamily) == "function" then
        local ok, family = pcall(UnitCreatureFamily, "pet")
        local key = ok and State.DEMON_OF(family) or nil
        if key then data.demon = key end
    end
    if pet ~= data.pet then
        data.pet = pet
        Notify("pet")
    end
end

local function ReadMana()
    local v
    if boltId and C_Spell and C_Spell.IsSpellUsable then
        local ok, _, noMana = pcall(C_Spell.IsSpellUsable, boltId)
        if ok then v = PlainBool(noMana) end
    end
    if v ~= data.noMana then
        data.noMana = v
        Notify("mana")
    end
end

local lastPoll
function State.Refresh()
    ReadBook()
    ReadDead()
    ReadPet()
    ReadMana()
    lastPoll = nil
end

-- One throttled pass; the module's ticker calls it.
function State.Tick(now)
    if type(now) ~= "number" then return end
    if lastPoll and now - lastPoll < TUNING.POLL then return end
    lastPoll = now
    ReadDead()
    ReadPet()
    ReadMana()
end

local frame
local started = false

local function OnEvent(_, event, unit, _, spellID)
    if event == "UNIT_PET" or event == "PLAYER_ENTERING_WORLD" or event == "PET_BAR_UPDATE" then
        ReadPet()
        return
    end
    if event == "PLAYER_DEAD" or event == "PLAYER_ALIVE" or event == "PLAYER_UNGHOST" then
        ReadDead()
        ReadPet()
        return
    end
    if event == "SPELLS_CHANGED" or event == "LEARNED_SPELL_IN_SKILL_LINE" then
        ReadBook()
        return
    end
    if not IsSecret(unit) and unit ~= "player" then return end
    local name = SpellName(spellID)
    if event == "UNIT_SPELLCAST_START" then
        if State.DEMON_OF(name) and string.find(string.lower(name), "summon", 1, true) then
            data.casting = true
            Notify("cast")
        end
    elseif event == "UNIT_SPELLCAST_SUCCEEDED" then
        if name then
            local lower = string.lower(name)
            if string.find(lower, "summon", 1, true) then
                local key = State.DEMON_OF(name)
                if key then
                    data.demon = key
                    data.summonAt = GetTime()
                    data.casting = false
                    data.pet = "alive"      -- until the next read says otherwise; the demon arrives with the cast
                    Notify("cast")
                end
            elseif lower == "life tap" then
                data.tapAt = GetTime()
                Notify("tap")
            end
        end
    elseif event == "UNIT_SPELLCAST_STOP" or event == "UNIT_SPELLCAST_FAILED" or event == "UNIT_SPELLCAST_INTERRUPTED"
        or event == "UNIT_SPELLCAST_FAILED_QUIET" then
        if data.casting then
            data.casting = false
            Notify("cast")
        end
    end
end

-- The listeners run from Start() on and never stop: a Summon cast while the module is hidden (no target) cannot be read back.
function State.Start()
    if started then return end
    local fh = FS.FrameHelpers
    if not (fh and fh.RegisterEvent) or type(CreateFrame) ~= "function" then
        LogOnce("noframe", "FrameHelpers.RegisterEvent is missing, the demon is never read")
        return
    end
    started = true
    frame = CreateFrame("Frame")
    for _, event in ipairs({ "UNIT_SPELLCAST_START", "UNIT_SPELLCAST_SUCCEEDED", "UNIT_SPELLCAST_STOP",
        "UNIT_SPELLCAST_FAILED", "UNIT_SPELLCAST_INTERRUPTED" }) do
        fh.RegisterEvent(frame, event, "player")
    end
    fh.RegisterEvent(frame, "UNIT_PET", "player")
    for _, event in ipairs({ "PLAYER_ENTERING_WORLD", "PLAYER_DEAD", "PLAYER_ALIVE", "PLAYER_UNGHOST", "SPELLS_CHANGED",
        "LEARNED_SPELL_IN_SKILL_LINE", "PET_BAR_UPDATE" }) do
        fh.RegisterEvent(frame, event)
    end
    frame:SetScript("OnEvent", function(...)
        local ok, err = pcall(OnEvent, ...)
        if not ok then LogOnce("event", err) end
    end)
    State.Refresh()
end
