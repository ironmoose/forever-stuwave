-- Forever STUwave: the Rogue's combo points, energy costs, Slice and Dice and stealth, as plain state for the Gunsight Rogue module
--
-- FACTS (every number the module guesses with sits in TUNING or DEFS, because class tuning moved between Forever builds):
--   * Combo points: at most 5, kept on the target they were built on until points are built on another enemy.
--   * Slice and Dice: 25 energy, 6 + 3 x points seconds (9, 12, 15, 18, 21 for 1 to 5 points; Improved Slice and Dice lengthens it, a talent
--     this file does not read). Sources and dates are in the adze research doc "Rogue stock-UI pain points (research 2026-11-16)".
--   * Finishers: Eviscerate, Envenom, Rupture, Kidney Shot, Expose Armor, Death Mark; builders: Sinister Strike, Backstab, Hemorrhage,
--     Mutilate, Ambush, Cheap Shot, Garrote, Shank.
--
-- WHAT THE CLIENT LETS US READ (12.0 engine, see the wow-addon-secret-values notes; every Rogue API here is UNPROBED on a Rogue):
--   * The combo count and the current energy are secret in combat (UnitPower), so they never reach a comparison here: the module
--     feeds them to engine bars. A count that happens to read plain is remembered (LastPoints) to size the Slice and Dice ledger.
--   * The player's own casts arrive as plain UNIT_SPELLCAST_SUCCEEDED spell ids and are matched by NAME (any rank counts).
--   * Spell costs are GetSpellPowerCost (plain), read out of combat and cached.
--   * Stealth is IsStealthed() when it answers a plain boolean (UPDATE_STEALTH is the event); nothing else claims it.
--   * Auras can be read only while FS.AurasReadable(): Slice and Dice's real time is taken then, with no estimate mark.
--
-- WHAT IS A GUESS AND HOW IT IS CORRECTED
--   * In combat Slice and Dice is a ledger: the cast stamp plus 6 + 3 x points. The points are the last plain count seen (the
--     count is gone by the time the cast event arrives); a secret count means TUNING.SND_ASSUME_POINTS. It is shown with "~".
--   * Out of combat the aura corrects the ledger and clears the mark; a plain read of "no aura" ends it at once.
--
-- API: Start(), Refresh(), Subscribe(fn), Unsubscribe(fn), Tick(now), Known(key), Snd(now) -> up, left, dur, exact | nil,
-- SndKnown(), Stealthed() -> true / false / nil, BuilderCost(), FinisherCost(), Energy max is read by the module (plain),
-- LastPoints(), SpendAt(), SpendPoints(), BuilderAt(), InCombat(), DEFS, TUNING. A listener is called fn(reason, key) with reason
-- "cast", "spend", "snd", "stealth", "combat", "learn", "cost", "change".

local _, FS = ...

FS.RogueState = FS.RogueState or {}
local State = FS.RogueState

local IsSecret = FS.IsSecret or function() return false end

local TUNING = {
    SND_BASE = 6, SND_PER_POINT = 3,          -- Slice and Dice lasts 6 + 3 x points seconds (Forever, 2026-11 sources)
    SND_ASSUME_POINTS = 5,                    -- the points spent when the count was never readable
    POINTS_FRESH = 45,                        -- s a remembered plain count stays usable for the ledger
    AURA_EVERY = 0.5,                         -- s between aura re-reads while they can be read
    COMBO_POWER = 4,                          -- Enum.PowerType.ComboPoints, when the enum is missing
    ENERGY_POWER = 3,
}
State.TUNING = TUNING

-- ids are the Classic ranks (UNPROBED here); a spell is found by id when one is known and by its name otherwise
local DEFS = {
    snd = { name = "Slice and Dice", ids = { 6774, 5171 }, role = "snd" },
    sinister = { name = "Sinister Strike", ids = { 1752 }, role = "builder" },
    backstab = { name = "Backstab", ids = { 53 }, role = "builder" },
    hemorrhage = { name = "Hemorrhage", ids = { 16511 }, role = "builder" },
    mutilate = { name = "Mutilate", ids = { 1329 }, role = "builder" },
    ambush = { name = "Ambush", ids = { 8676 }, role = "builder" },
    cheapshot = { name = "Cheap Shot", ids = { 1833 }, role = "builder" },
    garrote = { name = "Garrote", ids = { 703 }, role = "builder" },
    shank = { name = "Shank", ids = {}, role = "builder" },
    eviscerate = { name = "Eviscerate", ids = { 2098 }, role = "finisher" },
    envenom = { name = "Envenom", ids = { 32645 }, role = "finisher" },
    rupture = { name = "Rupture", ids = { 1943 }, role = "finisher" },
    kidney = { name = "Kidney Shot", ids = { 408 }, role = "finisher" },
    expose = { name = "Expose Armor", ids = { 8647 }, role = "finisher" },
    deathmark = { name = "Death Mark", ids = {}, role = "finisher" },
}
State.DEFS = DEFS
local KEYS = { "snd", "sinister", "backstab", "hemorrhage", "mutilate", "ambush", "cheapshot", "garrote", "shank", "eviscerate", "envenom",
    "rupture", "kidney", "expose", "deathmark" }
-- the order a cost is read from when nothing was cast yet (the plain staples first)
local BUILDER_ORDER = { "sinister", "backstab", "hemorrhage", "mutilate" }
local FINISHER_ORDER = { "eviscerate", "envenom", "rupture", "kidney", "expose" }

local known = {}                    -- key -> true / false (nil = never resolved)
local castAt = {}
local listeners = {}
local started = false
local frame
local lastPoints, lastPointsAt = nil, nil
local spend = { at = nil, points = nil, key = nil }
local builderAt, builderKey, finisherKey = nil, nil, nil
local snd = { up = false, at = nil, dur = nil, exact = false, points = nil }
local costs = { builder = nil, finisher = nil }
local stealth = nil
local auraAt = -100

local function Now() return GetTime() end

local function Notify(reason, key)
    for i = 1, #listeners do
        local ok, err = pcall(listeners[i], reason, key)
        if not ok and FS.LogDegradeOnce then
            pcall(FS.LogDegradeOnce, "rogue_listener", "|cffff4488Forever STUwave|r: rogue state listener: " .. tostring(err))
        end
    end
end

local function PlainOf(v, kind)
    if IsSecret(v) then return nil end
    if type(v) == kind then return v end
    return nil
end

local function Call(fn, ...)
    if type(fn) ~= "function" then return nil end
    local ok, a, b = pcall(fn, ...)
    if not ok then return nil end
    return a, b
end

local nameCache = {}
local function SpellNameOf(id)
    local hit = nameCache[id]
    if hit then return hit end
    local name = PlainOf(Call(C_Spell and C_Spell.GetSpellName, id), "string")
    if not name then name = PlainOf(Call(GetSpellInfo, id), "string") end
    if name then nameCache[id] = name end
    return name
end

-- true / false / nil (cannot tell) for "does the player know this spell id"
local function IsKnownId(id)
    local sawFalse, unreadable = false, false
    local fns = { IsPlayerSpell, IsSpellKnown, C_SpellBook and C_SpellBook.IsSpellKnown }
    for i = 1, 3 do
        local fn = fns[i]
        if fn then
            local ok, r = pcall(fn, id)
            if ok and not IsSecret(r) then
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

-- known (true / false / nil unreadable), the known id, the client's own name
local function ResolveSpell(d)
    local unknown = false
    for _, id in ipairs(d.ids) do
        local k = IsKnownId(id)
        if k == true then return true, id, SpellNameOf(id) end
        if k == nil then unknown = true end
    end
    local info = Call(C_Spell and C_Spell.GetSpellInfo, d.name)
    local id = type(info) == "table" and not IsSecret(info) and PlainOf(info.spellID, "number") or nil
    if id then
        local k = IsKnownId(id)
        if k == true then return true, id, PlainOf(info.name, "string") or d.name end
        if k == nil then unknown = true end
    end
    if unknown then return nil end
    return false
end

local function KeyOfSpell(name)
    if not name then return nil end
    for i = 1, #KEYS do
        local d = DEFS[KEYS[i]]
        if name == d.name or (d.localName ~= nil and name == d.localName) then return KEYS[i] end
    end
    return nil
end

local function SpellRef(d) return d.id or d.localName or d.name end

-------------------------------------------------------------------------------
-- Costs
-------------------------------------------------------------------------------

local function CostOf(key)
    if known[key] ~= true then return nil end
    local fn = C_Spell and C_Spell.GetSpellPowerCost
    local list
    if type(fn) == "function" then
        local ok, r = pcall(fn, SpellRef(DEFS[key]))
        if ok and type(r) == "table" and not IsSecret(r) then list = r end
    end
    if not list then return nil end
    local best
    for i = 1, #list do
        local e = list[i]
        if type(e) == "table" and not IsSecret(e) then
            local cost = PlainOf(e.cost, "number")
            if cost and cost > 0 then
                local t = PlainOf(e.type, "number")
                if t == nil or t == TUNING.ENERGY_POWER or (Enum and Enum.PowerType and t == Enum.PowerType.Energy) then best = cost break end
                best = best or cost
            end
        end
    end
    return best
end

local function PickKey(last, order)
    if last and known[last] == true then return last end
    for i = 1, #order do
        if known[order[i]] == true then return order[i] end
    end
    return nil
end

local function ReadCosts()
    local b = CostOf(PickKey(builderKey, BUILDER_ORDER) or "")
    local f = CostOf(PickKey(finisherKey, FINISHER_ORDER) or "")
    -- a read in combat may fail: keep the last good number
    local changed = false
    if b and b ~= costs.builder then costs.builder, changed = b, true end
    if f and f ~= costs.finisher then costs.finisher, changed = f, true end
    if changed then Notify("cost") end
end

function State.BuilderCost() return costs.builder end
function State.FinisherCost() return costs.finisher end

-------------------------------------------------------------------------------
-- Learn, stealth, points
-------------------------------------------------------------------------------

local function Learn()
    local changed = false
    for _, key in ipairs(KEYS) do
        local d = DEFS[key]
        local k, id, name = ResolveSpell(d)
        if k ~= nil then
            if k then d.id, d.localName = id, name or d.localName end
            if known[key] ~= k then known[key] = k; changed = true end
        end
    end
    return changed
end

function State.Known(key) return known[key] end
function State.SndKnown() return known.snd end
function State.CastAt(key) return castAt[key] end
function State.LastPoints(now)
    if lastPoints and lastPointsAt and ((now or Now()) - lastPointsAt) <= TUNING.POINTS_FRESH then return lastPoints end
    return nil
end
function State.SpendAt() return spend.at end
function State.SpendPoints() return spend.points end
function State.BuilderAt() return builderAt end
function State.InCombat() return type(InCombatLockdown) == "function" and InCombatLockdown() and true or false end

local function ReadStealth()
    local r = Call(IsStealthed)
    local new
    if IsSecret(r) or r == nil then new = nil else new = r and true or false end
    if new ~= stealth then
        stealth = new
        Notify("stealth")
    end
end

-- true / false when the client answered a plain boolean, nil otherwise
function State.Stealthed() return stealth end

-- The player's own combo count when it reads plain (remembered for the ledger); a secret returns nil.
local function NotePoints()
    local power = (Enum and Enum.PowerType and Enum.PowerType.ComboPoints) or TUNING.COMBO_POWER
    local v = Call(UnitPower, "player", power)
    if IsSecret(v) or type(v) ~= "number" or v ~= v or v < 0 then return end
    if v > 0 then lastPoints, lastPointsAt = math.floor(v), Now() else lastPoints = nil end   -- a plain 0: nothing built now
end
State.NotePoints = NotePoints

-------------------------------------------------------------------------------
-- Slice and Dice
-------------------------------------------------------------------------------

local function SndDuration(points)
    return TUNING.SND_BASE + TUNING.SND_PER_POINT * points
end

function State.Snd(now)
    if not snd.up then return nil end
    now = now or Now()
    local left = snd.at + snd.dur - now
    if left <= 0 then return nil end
    return true, left, snd.dur, snd.exact
end

-- The aura, when it can be read: the real time left and no estimate mark; a plain "no aura" ends it.
local function ReadSndAura(now)
    if known.snd ~= true then return end
    if not (FS.AurasReadable and FS.AurasReadable()) then return end
    local get = C_UnitAuras and C_UnitAuras.GetAuraDataBySpellName
    if type(get) ~= "function" then return end
    local ok, data = pcall(get, "player", DEFS.snd.localName or DEFS.snd.name, "HELPFUL")
    if not ok or IsSecret(data) then return end
    if data == nil then
        if snd.up then snd.up = false; Notify("snd") end
        return
    end
    if type(data) ~= "table" then return end
    local exp, dur = PlainOf(data.expirationTime, "number"), PlainOf(data.duration, "number")
    if not exp or not dur or dur <= 0 then return end
    snd.up, snd.dur, snd.at, snd.exact = true, dur, exp - dur, true
    Notify("snd")
end

-- Expiry of the ledger and the aura re-read. Called from the module's ticker.
function State.Tick(now)
    now = now or Now()
    if snd.up and snd.at + snd.dur <= now then
        snd.up = false
        Notify("snd")
    end
    if now - auraAt >= TUNING.AURA_EVERY then
        auraAt = now
        ReadSndAura(now)
    end
end

-------------------------------------------------------------------------------
-- The cast ledger
-------------------------------------------------------------------------------

local function OnCast(spellID)
    if IsSecret(spellID) or type(spellID) ~= "number" then return end
    local key = KeyOfSpell(SpellNameOf(spellID))
    if not key then return end
    local now = Now()
    local role = DEFS[key].role
    castAt[key] = now
    if known[key] ~= true then known[key] = true end
    if role == "snd" then
        local points = State.LastPoints(now) or TUNING.SND_ASSUME_POINTS
        local exact = false
        snd.up, snd.at, snd.dur, snd.points, snd.exact = true, now, SndDuration(points), points, exact
        spend.at, spend.points, spend.key = now, points, key
        Notify("snd", key)
        Notify("spend", key)
    elseif role == "finisher" then
        spend.at, spend.points, spend.key = now, State.LastPoints(now) or TUNING.SND_ASSUME_POINTS, key
        finisherKey = key
        lastPoints = nil
        Notify("spend", key)
        ReadCosts()
    elseif role == "builder" then
        builderAt, builderKey = now, key
        Notify("cast", key)
        ReadCosts()
    end
    if role == "snd" then lastPoints = nil end
end

function State.Refresh()
    local learned = Learn()
    ReadStealth()
    if not State.InCombat() then ReadCosts() end
    ReadSndAura(Now())
    if learned then Notify("learn") end
    Notify("change")
end

local EVENTS = { "PLAYER_ENTERING_WORLD", "SPELLS_CHANGED", "LEARNED_SPELL_IN_SKILL_LINE", "PLAYER_LEVEL_UP", "PLAYER_TARGET_CHANGED",
    "PLAYER_REGEN_ENABLED", "PLAYER_REGEN_DISABLED", "UPDATE_STEALTH", "ACTIVE_TALENT_GROUP_CHANGED", "CHARACTER_POINTS_CHANGED" }

local function Guard(tag, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok and FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "rogue_" .. tag, "|cffff4488Forever STUwave|r: rogue state " .. tag .. ": " .. tostring(err))
    end
end

local function Register(f, event, ...)
    local FH = FS.FrameHelpers
    if FH and FH.RegisterEvent then return FH.RegisterEvent(f, event, ...) end
    if select("#", ...) > 0 then return pcall(f.RegisterUnitEvent, f, event, ...) end
    return pcall(f.RegisterEvent, f, event)
end

-- The listeners run from Start() on and never stop: a cast while the module is hidden (no target) cannot be read back later.
function State.Start()
    if started then return end
    started = true
    frame = CreateFrame("Frame")
    frame:SetScript("OnEvent", function(_, event, a1, a2, a3)
        if event == "UNIT_SPELLCAST_SUCCEEDED" then
            Guard("cast", OnCast, a3)
        elseif event == "UNIT_POWER_UPDATE" or event == "UNIT_POWER_FREQUENT" then
            Guard("points", NotePoints)
        elseif event == "UPDATE_STEALTH" then
            Guard("stealth", ReadStealth)
        elseif event == "PLAYER_REGEN_DISABLED" or event == "PLAYER_REGEN_ENABLED" then
            if event == "PLAYER_REGEN_DISABLED" then
                -- a fight starts: a count remembered from before it is no guide to what this fight builds; read it again now
                -- (it may still be plain at this instant) and otherwise let Slice and Dice assume SND_ASSUME_POINTS
                lastPoints = nil
                Guard("points", NotePoints)
            end
            Notify("combat")
            if event == "PLAYER_REGEN_ENABLED" then Guard("refresh", State.Refresh) end
        elseif event == "PLAYER_TARGET_CHANGED" then
            Notify("change")
        else
            Guard("refresh", State.Refresh)
        end
    end)
    Register(frame, "UNIT_SPELLCAST_SUCCEEDED", "player")
    Register(frame, "UNIT_POWER_UPDATE", "player")
    for _, e in ipairs(EVENTS) do Register(frame, e) end
    Guard("refresh", State.Refresh)
end

function State.Subscribe(fn)
    if type(fn) ~= "function" then return end
    for i = 1, #listeners do if listeners[i] == fn then return end end
    listeners[#listeners + 1] = fn
end

function State.Unsubscribe(fn)
    for i = #listeners, 1, -1 do
        if listeners[i] == fn then table.remove(listeners, i) end
    end
end

-- for the harness
State._OnCast = OnCast
