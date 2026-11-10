-- Forever STUwave: the Priest's right slot, as plain state for the Gunsight Priest module
--
-- The right side of the Priest module is Prayer of Mending, a level 40 Holy talent, so until then it was a locked heart. This
-- file decides what lives there (the setting "Right side shows" and the group) and keeps the plain facts about the two watchers
-- that fill it while leveling: Spirit Tap (a Shadow talent: a killing blow on a mob that gives experience doubles Spirit for 15 s)
-- and Inner Fire (the self buff, 20 charges). The approved design is the mockup "Priest right slot, Spirit Tap and Inner Fire"
-- (2026-11-10), variant A (two round medallions), a plain skull in spirit green and the flame shield in gold.
--
-- WHAT THIS FILE NEVER DOES: the numbers on the medallions (Spirit Tap's time left, Inner Fire's charges) are the ENGINE's own
-- text, drawn through an aura slot (GunsightPriest.lua, the same route as the Shaman buff tab). They are secret in combat, so
-- nothing here reads, compares or counts them; this file only keeps what is plain: the setting, the group, which spells the
-- player knows, whether an aura is there OUT OF COMBAT (a plain read), and the player's own kills.
--
-- THE SETTING `gunsight.priest.rightside`: "auto" (default), "spirit" (Spirit Tap + Inner Fire), "pom" (Prayer of Mending), "off".
-- Auto shows Spirit Tap + Inner Fire on your own or in a small group out in the world, and Prayer of Mending in a dungeon or a
-- raid group once it is learned (else Spirit Tap + Inner Fire). The mode that is DRAWN (Mode) changes out of combat only: a change
-- in combat waits for PLAYER_REGEN_ENABLED, so nothing swaps mid fight.
--
-- SPELLS BY NAME AND RANK. A rank id is a guess from the Classic data (UNVERIFIED on Forever), so every spell is also resolved by
-- NAME (FS.FrameHelpers.ResolveSpell answers the highest rank the player knows) and Known() asks every spellbook API the client
-- has. Ids(which) is what the engine slot filters on (includeSpellIDs): every rank id, the buff's own id and the id the name
-- resolves to today.
--
-- THE KILL LEDGER. PARTY_KILL (attacker GUID, target GUID) with the player as the attacker stamps `killAt`. It drives only the
-- amber "pull now" cue, and only OUT OF COMBAT: the cue breathes while the window the kill opened (15 s) is still running, a plain
-- aura read says Spirit Tap is up (a kill on a grey mob gives no experience and no buff), and combat is over.
--
-- API: Start(), Subscribe(fn), Unsubscribe(fn), Applies(), Setting(), Remind(), Wanted(), Apply(), Mode() -> "medallions" | "pom" | "off",
-- Known(which) -> true / false, Ids(which), AllIds(), PlainUp(which) -> true / false / nil (nil in combat or unreadable),
-- KillAt(), Cue(now) -> boolean, DEFS, SETTING, REMIND. A listener is called fn(reason): "mode", "known", "aura", "kill",
-- "combat", "remind".

local _, FS = ...

FS.PriestRight = FS.PriestRight or {}
local Right = FS.PriestRight

local IsSecret = FS.IsSecret or function() return false end

Right.SETTING = {
    key = "gunsight.priest.rightside", default = "auto", label = "Right side shows",
    values = { "auto", "spirit", "pom", "off" },
    text = { auto = "Auto", spirit = "Spirit Tap + Inner Fire", pom = "Prayer of Mending", off = "Off" },
    tip = "What the right side of the Priest module shows. Auto shows Spirit Tap and Inner Fire on your own or in a small group "
        .. "out in the world, and Prayer of Mending in a dungeon or a raid group once you have learned it. The other choices "
        .. "fix it. A change made in combat applies when the fight ends.",
}
local SETTING = Right.SETTING

-- The reminder: Inner Fire missing breathes amber on its medallion. Every alert has its own off switch.
Right.REMIND = {
    key = "gunsight.priest.firenudge", default = true, label = "Remind me when Inner Fire is missing",
    tip = "The Inner Fire medallion breathes amber while the buff is not on you. Off leaves it calm and dim. It never "
        .. "shows before you have learned the spell.",
}

if FS.Config and FS.Config.RegisterDefault then
    FS.Config.RegisterDefault(SETTING.key, SETTING.default)
    FS.Config.RegisterDefault(Right.REMIND.key, Right.REMIND.default)
end

-- Classic data from memory, UNVERIFIED on Forever: the names resolve the real ids at run time (Ids).
local DEFS = {
    spirit = { name = "Spirit Tap", ids = { 15270, 15335, 15336, 15337, 15338 }, auras = { 15271 }, duration = 15 },
    fire = { name = "Inner Fire", ids = { 588, 7128, 602, 1006, 10951, 10952, 25431 }, auras = {}, level = 12, charges = 20 },
}
Right.DEFS = DEFS
Right.KILL_WINDOW = DEFS.spirit.duration

local applied                    -- the mode that is drawn: "medallions" | "pom" | "off"
local pending = false            -- a change that waited for the end of combat
local known = { spirit = false, fire = false }
local resolved = {}              -- the id each name resolves to now: a new rank changes it
local up = { spirit = nil, fire = nil }
local killAt
local listeners = {}
local started = false

local function Now() return GetTime() end

local function InCombat()
    return type(InCombatLockdown) == "function" and InCombatLockdown() and true or false
end

local function Notify(reason)
    for i = 1, #listeners do
        local ok, err = pcall(listeners[i], reason)
        if not ok and FS.LogDegradeOnce then
            pcall(FS.LogDegradeOnce, "priestright_listener", "|cffff4488Forever STUwave|r: priest right slot listener: " .. tostring(err))
        end
    end
end

local function PlainOf(v, kind)
    if IsSecret(v) then return nil end
    if type(v) == kind then return v end
    return nil
end

function Right.Applies()
    if type(UnitClass) ~= "function" then return false end
    local ok, _, token = pcall(UnitClass, "player")
    return ok and not IsSecret(token) and token == "PRIEST"
end

-------------------------------------------------------------------------------
-- Spells: known, and the ids the engine slot filters on
-------------------------------------------------------------------------------

local function Helpers() return FS.FrameHelpers end

-- The id the client resolves the spell's name to (the highest rank the player knows), plain or nil.
local function ResolvedId(def)
    local FH = Helpers()
    if not (FH and FH.ResolveSpell) then return nil end
    local ok, id = pcall(FH.ResolveSpell, def.name)
    if ok then return PlainOf(id, "number") end
    return nil
end

local function ReadKnown(def)
    local FH = Helpers()
    if not (FH and FH.IsKnownSpellId) then return false end
    for _, id in ipairs(def.ids) do
        local ok, k = pcall(FH.IsKnownSpellId, id, false)
        if ok and not IsSecret(k) and k then return true end
    end
    local id = ResolvedId(def)
    if id then
        local ok, k = pcall(FH.IsKnownSpellId, id, false)
        if ok and not IsSecret(k) and k then return true end
    end
    return false
end

-- true when the player knows the spell (Spirit Tap: the talent is taken; Inner Fire: any rank is in the book).
function Right.Known(which) return known[which] == true end

-- the includeSpellIDs map of the engine slot: every rank id, the buff's own id and the id the name resolves to now
function Right.Ids(which)
    local def = DEFS[which]
    local set = {}
    if not def then return set end
    for _, id in ipairs(def.ids) do set[id] = true end
    for _, id in ipairs(def.auras) do set[id] = true end
    local id = ResolvedId(def)
    if id then set[id] = true end
    return set
end

function Right.AllIds()
    local set = Right.Ids("spirit")
    for id in pairs(Right.Ids("fire")) do set[id] = true end
    return set
end

local function RefreshKnown()
    if InCombat() then return end            -- the spellbook APIs answer an error in combat: never forget a spell there
    local changed = false
    for which, def in pairs(DEFS) do
        local k = ReadKnown(def)
        if known[which] ~= k then known[which] = k; changed = true end
        local id = ResolvedId(def)
        if resolved[which] ~= id then resolved[which] = id; changed = true end     -- a new rank: the slot filter needs it
    end
    if changed then Notify("known") end
end

-------------------------------------------------------------------------------
-- Plain aura reads, out of combat only
-------------------------------------------------------------------------------

local function Readable() return FS.AurasReadable and FS.AurasReadable() or false end

-- true when the aura is there, false when it is readably absent, nil when it cannot be read.
local function ReadUp(def)
    if InCombat() or not Readable() then return nil end
    local byName = C_UnitAuras and C_UnitAuras.GetAuraDataBySpellName
    if type(byName) ~= "function" then return nil end
    local ok, aura = pcall(byName, "player", def.name, "HELPFUL")
    if not ok or IsSecret(aura) then return nil end
    return type(aura) == "table"
end

-- Out of combat only. An answer that cannot be read leaves the aura "unknown" (nil), never the last answer.
local function RefreshAuras()
    if InCombat() then return end
    local changed = false
    for which, def in pairs(DEFS) do
        local v = ReadUp(def)
        if up[which] ~= v then up[which] = v; changed = true end
    end
    if changed then Notify("aura") end
end

-- the plain answer out of combat; nil in combat (the last read is stale there) or when it has never been readable
function Right.PlainUp(which)
    if InCombat() then return nil end
    return up[which]
end

-------------------------------------------------------------------------------
-- The kill ledger and the pull now cue
-------------------------------------------------------------------------------

function Right.KillAt() return killAt end

-- true while the cue breathes: out of combat, the window a kill of the player's own opened still runs, and a plain read says
-- Spirit Tap is up
function Right.Cue(now)
    if InCombat() or killAt == nil then return false end
    if (now or Now()) - killAt >= Right.KILL_WINDOW then return false end
    return up.spirit == true
end

local function OnKill(attacker)
    if IsSecret(attacker) or type(attacker) ~= "string" then return end
    local ok, me = pcall(UnitGUID, "player")
    if not ok or IsSecret(me) or type(me) ~= "string" or me ~= attacker then return end
    killAt = Now()
    Notify("kill")
end

-------------------------------------------------------------------------------
-- The setting and the group: what is drawn
-------------------------------------------------------------------------------

-- true unless the player switched the Inner Fire reminder off
function Right.Remind()
    local v = FS.Config and FS.Config.Get and FS.Config.Get(Right.REMIND.key)
    return v ~= false
end

function Right.Setting()
    local v = FS.Config and FS.Config.Get and FS.Config.Get(SETTING.key)
    if v == "spirit" or v == "pom" or v == "off" then return v end
    return "auto"
end

-- A dungeon or a raid group: in a raid, or inside a party or raid instance.
local function InDungeonOrRaid()
    if type(IsInRaid) == "function" then
        local ok, raid = pcall(IsInRaid)
        if ok and not IsSecret(raid) and raid then return true end
    end
    if type(IsInInstance) == "function" then
        local ok, inside, kind = pcall(IsInInstance)
        if ok and not IsSecret(inside) and not IsSecret(kind) and inside and (kind == "party" or kind == "raid") then return true end
    end
    return false
end

local function MendingKnown()
    local PS = FS.PriestShields
    local m = PS and PS.Mending and PS.Mending()
    return type(m) == "table" and m.known == true
end

-- What the setting and the group ask for right now.
function Right.Wanted()
    local s = Right.Setting()
    if s == "spirit" then return "medallions" end
    if s == "pom" then return "pom" end
    if s == "off" then return "off" end
    if InDungeonOrRaid() and MendingKnown() then return "pom" end
    return "medallions"
end

-- Applies what is wanted, out of combat only: in combat the change waits for PLAYER_REGEN_ENABLED. The first call always applies.
function Right.Apply()
    if applied ~= nil and InCombat() then
        pending = true
        return false
    end
    pending = false
    local want = Right.Wanted()
    if want ~= applied then
        applied = want
        Notify("mode")
    end
    return true
end

function Right.Mode()
    if applied == nil then Right.Apply() end
    return applied
end

function Right.Pending() return pending end

-------------------------------------------------------------------------------
-- Events
-------------------------------------------------------------------------------

local function Guard(tag, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok and FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "priestright_" .. tag, "|cffff4488Forever STUwave|r: priest right slot " .. tag .. ": " .. tostring(err))
    end
end

local function Register(f, event, ...)
    local FH = Helpers()
    if FH and FH.RegisterEvent then return FH.RegisterEvent(f, event, ...) end
    if select("#", ...) > 0 then return pcall(f.RegisterUnitEvent, f, event, ...) end
    return pcall(f.RegisterEvent, f, event)
end

local EVENTS = { "PLAYER_ENTERING_WORLD", "ZONE_CHANGED_NEW_AREA", "GROUP_ROSTER_UPDATE", "SPELLS_CHANGED",
    "LEARNED_SPELL_IN_SKILL_LINE", "PLAYER_LEVEL_UP", "PLAYER_TALENT_UPDATE", "PLAYER_REGEN_ENABLED", "PLAYER_REGEN_DISABLED" }

local function Refresh()
    RefreshKnown()
    RefreshAuras()
    Right.Apply()
end

function Right.Start()
    if started then return end
    started = true
    if FS.Config and FS.Config.OnChange then
        FS.Config.OnChange(SETTING.key, function() Guard("setting", Right.Apply) end)
        FS.Config.OnChange(Right.REMIND.key, function() Notify("remind") end)
    end
    local frame = CreateFrame("Frame")
    frame:SetScript("OnEvent", function(_, event, a1, a2)
        if event == "PARTY_KILL" then
            Guard("kill", OnKill, a1, a2)
        elseif event == "UNIT_AURA" then
            if not InCombat() then Guard("aura", RefreshAuras) end
        elseif event == "PLAYER_REGEN_DISABLED" then
            Notify("combat")
        else
            Guard("refresh", Refresh)
            if event == "PLAYER_REGEN_ENABLED" then Notify("combat") end
        end
    end)
    Register(frame, "PARTY_KILL")
    Register(frame, "UNIT_AURA", "player")
    for _, e in ipairs(EVENTS) do Register(frame, e) end
    Guard("refresh", Refresh)
end

function Right.Subscribe(fn)
    if type(fn) ~= "function" then return end
    for i = 1, #listeners do if listeners[i] == fn then return end end
    listeners[#listeners + 1] = fn
end

function Right.Unsubscribe(fn)
    for i = #listeners, 1, -1 do
        if listeners[i] == fn then table.remove(listeners, i) end
    end
end

-- for the harness
Right._OnKill, Right._Refresh = OnKill, Refresh
