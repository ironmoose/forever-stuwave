-- Forever STUwave: the threat view on the nameplates (the Roles page).
--
-- Reads what the player's role cares about and hands it to the plates through the two hooks Nameplates.lua offers
-- (Plates.SetColorProvider / Plates.SetTextProvider); nothing here edits a plate except two small things of its own, a flash
-- texture over the health bar and the bar's alpha for the range dim.
--
--   tank    Aggro colours (on me cyan, slipping amber, not on me pink), Threat text (Aggro % or Lead), Lost aggro alert
--   healer  the A mob turns to me alert
--   melee   Aggro colours (on me pink, close amber, safe cyan), Warn near the tank, Dim target out of melee range
--   ranged  the same, Dim target out of spell range
--
-- Every threat read is feature detected, wrapped in pcall and checked with FS.IsSecret before it is compared. A read that
-- cannot be trusted answers nil, and nil leaves the plate with its own colour. Nothing here compares a secret value: a
-- secret percent is handed to the plate with a format and the plate's own text field formats it (SetFormattedText), a
-- secret range answer goes to SetAlphaFromBoolean. On this client the threat VALUES (UnitDetailedThreatSituation's
-- percents, UnitThreatPercentageOfLead) are secret when asked of a nameplate token and plain for "target", while the
-- threat STATE (UnitThreatSituation) is plain for both; every read has a plain fallback.
local _, FS = ...

local PT = {}
FS.PlateThreat = PT

-------------------------------------------------------------------------------
-- Data
-------------------------------------------------------------------------------

-- The three threat colours of the prototype (#22e0ff, #ffb648, #ff2e97). The tables are handed to the plates as they are:
-- a plate skips a fill it already wears by table identity.
local CYAN = { 0.133, 0.878, 1, 1 }
local AMBER = { 1, 0.714, 0.282, 1 }
local PINK = { 1, 0.180, 0.592, 1 }
PT.PALETTE = { cyan = CYAN, amber = AMBER, pink = PINK }

-- What the Roles page shows under "Colours": { colour, word } in the order of the prototype.
PT.SWATCHES = {
    tank = { { CYAN, "on me" }, { AMBER, "slipping" }, { PINK, "not on me" } },
    melee = { { PINK, "on me" }, { AMBER, "close" }, { CYAN, "safe" } },
    ranged = { { PINK, "on me" }, { AMBER, "close" }, { CYAN, "safe" } },
}

PT.TUNING = {
    DIM_ALPHA = 0.45,       -- the target's health bar out of range
    FLASH_ALPHA = 0.85,     -- the alert flash at its brightest, fading to nothing
    FLASH_TIME = 0.8,       -- seconds one flash lasts
    ALERT_GAP = 1,          -- seconds between two alerts on one mob
    RANGE_EVERY = 0.2,      -- seconds between two range reads
    NEAR_INTERACT = 3,      -- CheckInteractDistance index told apart from "too far": the duel distance, about 10 yd
}

-- Spells by name whose range stands for the role's range: the first one the client answers for wins. Unknown spells answer
-- nil and are skipped. Melee classes with no melee spell (Paladin, Shaman, Hunter without Raptor Strike) fall back to the
-- duel distance.
local MELEE_SPELLS = {
    WARRIOR = { "Heroic Strike", "Rend", "Hamstring" },
    ROGUE = { "Sinister Strike", "Backstab", "Eviscerate" },
    PALADIN = { "Crusader Strike", "Holy Strike" },
    DRUID = { "Claw", "Rake", "Maul" },
    SHAMAN = { "Stormstrike" },
    HUNTER = { "Raptor Strike", "Mongoose Bite" },
}
local RANGED_SPELLS = {
    PRIEST = { "Smite", "Shadow Word: Pain", "Shoot" },
    SHAMAN = { "Lightning Bolt", "Earth Shock", "Flame Shock" },
    MAGE = { "Fireball", "Frostbolt", "Arcane Missiles", "Fire Blast" },
    WARLOCK = { "Shadow Bolt", "Corruption", "Immolate" },
    DRUID = { "Wrath", "Moonfire" },
    HUNTER = { "Auto Shot", "Arcane Shot" },
    PALADIN = { "Judgement", "Hammer of Justice" },
    ROGUE = { "Throw" },
    WARRIOR = { "Throw" },
}

-------------------------------------------------------------------------------
-- Reads
-------------------------------------------------------------------------------

local function PlainNumber(v)
    if FS.IsSecret(v) or type(v) ~= "number" or v ~= v or v == math.huge or v == -math.huge then return nil end
    return v
end

local function PlainBool(v)
    if FS.IsSecret(v) or type(v) ~= "boolean" then return nil end
    return v
end

local function RoleNow()
    local role = FS.Role
    if not role then return nil end
    return (role.Current())
end

local function Setting(key)
    local role = FS.Role
    return role and role.Get(key)
end

-- What the player's threat on `unit` says: tanking (plain boolean or nil), status (0 to 3 or nil), pct (the scaled percent as
-- a plain number or nil), raw (that percent as the client gave it, possibly secret, for the text) and listed (whether the
-- game has the player on the mob's threat table: true, false, or nil when that cannot be told). A piece that is secret or
-- missing is nil. tanking is worked out from the status, else from a percent of 100, when the client does not say. A mob
-- that does not list the player answers nothing from the detailed read and nil from the plain state (nil, never 0); any
-- answer at all, a secret one too, means it does.
local function ReadThreat(unit)
    local tanking, status, pct, raw, listed
    local detailed = _G.UnitDetailedThreatSituation
    if type(detailed) == "function" then
        local ok, isTanking, st, scaled = pcall(detailed, "player", unit)
        if ok then
            tanking, status, pct, raw = PlainBool(isTanking), PlainNumber(st), PlainNumber(scaled), scaled
            if type(isTanking) ~= "nil" then listed = true end
        end
    end
    if status == nil then
        local plain = _G.UnitThreatSituation
        if type(plain) == "function" then
            local ok, st = pcall(plain, "player", unit)
            if ok then
                status = PlainNumber(st)
                if status ~= nil then
                    listed = true
                elseif type(st) == "nil" and listed == nil then
                    listed = false
                end
            end
        end
    end
    if tanking == nil then
        if status ~= nil then
            tanking = status >= 2
        elseif pct ~= nil then
            tanking = pct >= 100
        end
    end
    return tanking, status, pct, raw, listed
end

-- The game's own lead number for the player on `unit` (UnitThreatPercentageOfLead), possibly secret, or nil.
local function ReadLead(unit)
    local fn = _G.UnitThreatPercentageOfLead
    if type(fn) ~= "function" then return nil end
    local ok, value = pcall(fn, "player", unit)
    if ok then return value end
    return nil
end

-- "mine" or "other" for the tank and the healer; "mine", "close" or "safe" for the damage roles; nil when it cannot be told.
local function StateOf(role, unit)
    local tanking, status, pct = ReadThreat(unit)
    if tanking == nil then return nil end
    if role == "tank" or role == "healer" then return tanking and "mine" or "other" end
    if tanking then return "mine" end
    local warn = Setting(role .. ".pct")
    if pct ~= nil and warn then return pct >= warn and "close" or "safe" end
    if status == 1 then return "close" end
    if status == 0 then return "safe" end
    return nil
end

-------------------------------------------------------------------------------
-- The two providers
-------------------------------------------------------------------------------

local function ColorProvider(unit)
    local role = RoleNow()
    if role ~= "tank" and role ~= "melee" and role ~= "ranged" then return nil end
    local tanking, status, pct = ReadThreat(unit)
    if tanking == nil then return nil end
    if role == "tank" then
        if tanking then return status == 2 and AMBER or CYAN end
        return PINK
    end
    if tanking then return PINK end
    local warn = Setting(role .. ".pct")
    if pct ~= nil and warn then return pct >= warn and AMBER or CYAN end
    if status == 1 then return AMBER end
    if status == 0 then return CYAN end
    return nil
end

-- What the plate's text field is given for a percent. A plain number comes back as the finished string, rounded. A secret
-- one has no text Lua can make, so it comes back as itself with the format the field applies to it: the plate calls
-- SetFormattedText on its own field, the call the health text makes with a secret percent. Nil when there is no number.
local PERCENT_FORMAT = "%.0f%%"
local function PercentAnswer(value)
    if FS.IsSecret(value) then return value, nil, PERCENT_FORMAT end
    local n = PlainNumber(value)
    if n == nil then return nil end
    return string.format("%d%%", math.floor(n + 0.5))
end

-- Aggro % is the player's share of the mob's threat, Lead the game's own lead number (UnitThreatPercentageOfLead). The game
-- answers Lead 0 for a mob that does not list the player at all, so a mob it says is not fighting the player gets no text
-- (a state that cannot be read does not count as "not listed"). The sign is not added: the number is the game's, shown the
-- way its own target frame shows it, and a secret one cannot be signed anyway.
local function TextProvider(unit)
    if RoleNow() ~= "tank" then return nil end
    local mode = Setting("tank.threat")
    if mode ~= "pct" and mode ~= "lead" then return nil end
    local _, _, _, raw, listed = ReadThreat(unit)
    if listed == false then return nil end
    if mode == "pct" then return PercentAnswer(raw) end
    return PercentAnswer(ReadLead(unit))
end

-------------------------------------------------------------------------------
-- Alerts: a flash over the health bar and a sound, each with its switch
-------------------------------------------------------------------------------

local flashes = {}          -- unit -> { root, t }: the flashes running
local last = {}             -- unit -> the state last read, to see a change
local lastAt = {}           -- unit -> when it last alerted
local driver = CreateFrame("Frame")
PT.driver = driver
local running, broken = false, false
local rangeOn = false
local dimmedRoot, dimmedUnit

local function Now()
    if type(GetTime) == "function" then return GetTime() end
    return 0
end

local function Chime(name)
    if type(PlaySound) ~= "function" then return end
    local kit = _G.SOUNDKIT
    local id = type(kit) == "table" and (kit[name] or kit.TELL_MESSAGE) or nil
    if type(id) ~= "number" then return end
    pcall(PlaySound, id)
end

-- The driver runs only while something needs it: a flash, or the range check.
local OnUpdate
local function Sync()
    local want = not broken and (next(flashes) ~= nil or rangeOn)
    if want and not running then
        running = true
        driver:SetScript("OnUpdate", OnUpdate)
    elseif not want and running then
        running = false
        driver:SetScript("OnUpdate", nil)
    end
end

local function StartFlash(unit, root, color)
    local tex = root.threatFlash
    if not tex then
        local bar = root.healthBar
        if not bar then return end
        local ok, made = pcall(bar.CreateTexture, bar, nil, "OVERLAY", nil, 6)
        if not ok or not made then return end
        pcall(made.SetAllPoints, made, bar)
        root.threatFlash = made
        tex = made
    end
    tex:SetColorTexture(color[1], color[2], color[3], 1)
    tex:SetAlpha(PT.TUNING.FLASH_ALPHA)
    tex:Show()
    flashes[unit] = { root = root, t = 0 }
    Sync()
end

local function StepFlashes(dt)
    for unit, flash in pairs(flashes) do
        flash.t = flash.t + dt
        local tex = flash.root.threatFlash
        if flash.t >= PT.TUNING.FLASH_TIME or FS.framesByUnit[unit] ~= flash.root then
            if tex then tex:Hide() end
            flashes[unit] = nil
        elseif tex then
            tex:SetAlpha(PT.TUNING.FLASH_ALPHA * (1 - flash.t / PT.TUNING.FLASH_TIME))
        end
    end
end

function PT.Flashing(unit)
    return flashes[unit] ~= nil
end

-- What each role is told about, and when: rule(was, now) on a change from a state that was read before.
local ALERTS = {
    tank = { switch = "tank.lost", sound = "tank.lost.snd", kit = "RAID_WARNING", color = PINK,
        rule = function(was, now) return was == "mine" and now == "other" end },
    healer = { switch = "heal.aggro", sound = "heal.aggro.snd", kit = "TELL_MESSAGE", color = PINK,
        rule = function(was, now) return was == "other" and now == "mine" end },
}
for _, name in ipairs({ "melee", "ranged" }) do
    ALERTS[name] = { switch = name .. ".warn", color = AMBER,
        rule = function(was, now) return was == "safe" and now == "close" end }
end

local function Alert(unit, def)
    local root = FS.framesByUnit[unit]
    if not root then return end
    local now = Now()
    local at = lastAt[unit]
    if at and now >= at and now - at < PT.TUNING.ALERT_GAP then return end
    lastAt[unit] = now
    StartFlash(unit, root, def.color)
    if def.sound and Setting(def.sound) then Chime(def.kit) end
end

local function OnThreat(unit)
    if type(unit) ~= "string" or not FS.framesByUnit[unit] then return end
    local role = RoleNow()
    local def = role and ALERTS[role]
    if not def or not Setting(def.switch) then
        last[unit] = nil
        return
    end
    local state = StateOf(role, unit)
    if state == nil then return end
    local was = last[unit]
    last[unit] = state
    if def.rule(was, state) then Alert(unit, def) end
end

-------------------------------------------------------------------------------
-- Range: the target's bar dims when the target is out of melee or spell range
-------------------------------------------------------------------------------

local classToken
local function ClassToken()
    if classToken then return classToken end
    if type(UnitClass) ~= "function" then return nil end
    local ok, _, token = pcall(UnitClass, "player")
    if ok and not FS.IsSecret(token) and type(token) == "string" then classToken = token end
    return classToken
end

-- true, false or a secret boolean from the first spell of the list the client answers for; the second result says the answer
-- is secret. Nil when no spell answered.
local function SpellRange(names)
    if type(names) ~= "table" then return nil end
    local spell = _G.C_Spell
    local modern = type(spell) == "table" and spell.IsSpellInRange or nil
    local legacy = _G.IsSpellInRange
    for _, name in ipairs(names) do
        local ok, answer
        if type(modern) == "function" then
            ok, answer = pcall(modern, name, "target")
        elseif type(legacy) == "function" then
            ok, answer = pcall(legacy, name, "target")
        end
        if ok then
            if FS.IsSecret(answer) then return answer, true end
            if answer == true or answer == 1 then return true, false end
            if answer == false or answer == 0 then return false, false end
        end
    end
    return nil
end

local function NearTarget()
    if type(CheckInteractDistance) ~= "function" then return nil end
    local ok, answer = pcall(CheckInteractDistance, "target", PT.TUNING.NEAR_INTERACT)
    if not ok or FS.IsSecret(answer) then return nil end
    if answer == true or answer == 1 then return true end
    if answer == false or answer == 0 then return false end
    return nil
end

-- Melee range: the class's melee spell, and the duel distance must agree (Raptor Strike answers true at any distance on
-- this client); with no spell answer the duel distance alone.
local function MeleeRange()
    local answer, secret = SpellRange(MELEE_SPELLS[ClassToken() or ""])
    if secret then return answer, true end
    local near = NearTarget()
    if answer == true then return near ~= false, false end
    if answer == false then return false, false end
    if near == nil then return nil end
    return near, false
end

local function Undim()
    if dimmedRoot then
        local bar = dimmedRoot.healthBar
        if bar then bar:SetAlpha(1) end
    end
    dimmedRoot, dimmedUnit = nil, nil
end

local function TargetPlate()
    for unit, root in pairs(FS.framesByUnit) do
        local ok, same = pcall(UnitIsUnit, unit, "target")
        if ok and not FS.IsSecret(same) and same == true then return unit, root end
    end
    return nil
end

local function RangeStep()
    local role = RoleNow()
    if not rangeOn or (role ~= "melee" and role ~= "ranged") then Undim() return end
    local exists = type(UnitExists) == "function" and UnitExists("target")
    if FS.IsSecret(exists) or not exists then Undim() return end
    local unit, root = TargetPlate()
    if not root or not root.healthBar then Undim() return end
    local okAttack, attackable = pcall(UnitCanAttack, "player", unit)
    if not okAttack or FS.IsSecret(attackable) or not attackable then Undim() return end
    local inRange, secret
    if role == "melee" then
        inRange, secret = MeleeRange()
    else
        inRange, secret = SpellRange(RANGED_SPELLS[ClassToken() or ""])
    end
    if inRange == nil then Undim() return end
    if dimmedRoot and dimmedRoot ~= root then Undim() end
    local bar = root.healthBar
    if secret then
        if type(bar.SetAlphaFromBoolean) ~= "function" then Undim() return end
        bar:SetAlphaFromBoolean(inRange, 1, PT.TUNING.DIM_ALPHA)
    else
        bar:SetAlpha(inRange and 1 or PT.TUNING.DIM_ALPHA)
    end
    dimmedRoot, dimmedUnit = root, unit
end

-------------------------------------------------------------------------------
-- The driver, and applying the role
-------------------------------------------------------------------------------

local since = 0
local function Step(dt)
    StepFlashes(dt)
    if rangeOn then
        since = since + dt
        if since >= PT.TUNING.RANGE_EVERY then
            since = 0
            RangeStep()
        end
    end
    Sync()
end

OnUpdate = function(_, dt)
    local ok, err = pcall(Step, dt)
    if not ok then
        -- one broken read must not repeat every frame: stop until the next role or setting change
        broken = true
        Sync()
        if FS.Layout and FS.Layout.ForwardError then FS.Layout.ForwardError(err) end
    end
end

-- Installs or removes the providers for the role in use and the settings, and starts or stops the range check. Safe to call
-- at any time; every role or setting change calls it, so a change shows at once.
function PT.Apply()
    broken = false
    local role = RoleNow()
    local colours = role ~= nil and role ~= "healer" and Setting(role .. ".aggro") == true
    local text = role == "tank" and Setting("tank.threat") ~= "off"
    rangeOn = (role == "melee" or role == "ranged") and Setting(role .. ".range") == true
    local plates = FS.Nameplates
    if plates then
        if type(plates.SetColorProvider) == "function" then plates.SetColorProvider(colours and ColorProvider or nil) end
        if type(plates.SetTextProvider) == "function" then plates.SetTextProvider(text and TextProvider or nil) end
    end
    if rangeOn then RangeStep() else Undim() end
    Sync()
end

local function Forget(unit)
    last[unit], lastAt[unit] = nil, nil
    local flash = flashes[unit]
    if flash then
        if flash.root.threatFlash then flash.root.threatFlash:Hide() end
        flashes[unit] = nil
    end
    if dimmedUnit == unit then Undim() end
    Sync()
end

if FS.Role and FS.Role.OnChange then
    FS.Role.OnChange(function()
        for unit in pairs(last) do last[unit] = nil end
        PT.Apply()
    end)
end
if FS.Role and FS.Config and FS.Config.OnChange then
    for _, key in ipairs(FS.Role.KEYS) do
        FS.Config.OnChange(key, function() PT.Apply() end)
    end
end

-------------------------------------------------------------------------------
-- Events
-------------------------------------------------------------------------------

local LATER_EVENTS = { "PLAYER_ENTERING_WORLD", "UNIT_THREAT_SITUATION_UPDATE", "UNIT_THREAT_LIST_UPDATE",
    "NAME_PLATE_UNIT_REMOVED", "PLAYER_REGEN_ENABLED", "PLAYER_TARGET_CHANGED" }

local frame = CreateFrame("Frame")
PT.frame = frame
frame:RegisterEvent("PLAYER_LOGIN")
frame:SetScript("OnEvent", function(self, event, unit)
    local ok, err = pcall(function()
        if event == "PLAYER_LOGIN" then
            local helpers = FS.FrameHelpers
            if helpers and type(helpers.RegisterEvents) == "function" then
                helpers.RegisterEvents(self, LATER_EVENTS)
            else
                for _, name in ipairs(LATER_EVENTS) do pcall(self.RegisterEvent, self, name) end
            end
            PT.Apply()
        elseif event == "PLAYER_ENTERING_WORLD" then
            PT.Apply()
        elseif event == "UNIT_THREAT_SITUATION_UPDATE" or event == "UNIT_THREAT_LIST_UPDATE" then
            OnThreat(unit)
        elseif event == "NAME_PLATE_UNIT_REMOVED" then
            Forget(unit)
        elseif event == "PLAYER_REGEN_ENABLED" then
            for key in pairs(last) do last[key] = nil end
        elseif event == "PLAYER_TARGET_CHANGED" then
            if rangeOn then RangeStep() end
        end
    end)
    if not ok and FS.Layout and FS.Layout.ForwardError then FS.Layout.ForwardError(err) end
end)
