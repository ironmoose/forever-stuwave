-- Forever STUwave: Shaman buff data (weapon imbue and Lightning Shield) for the buff tab (BuffTab.lua)
--
-- The data model of the IMBUE and SHIELD tiles, moved here from the Gunsight Class Module (GunsightShaman.lua, which
-- no longer draws or listens to anything). It draws nothing: BuffTab.lua asks for `Update(now)` once a second and
-- paints the view it gets back, and `OnChange(fn)` says when an event moved the data between two ticks.
--
-- IMBUE. GetWeaponEnchantInfo answers false/nil on this client even with Rockbiter up (live, 2026-10-12), and the
-- imbue is not a player aura. What works is the weapon's tooltip: C_TooltipInfo.GetInventoryItem("player", 16 or 17)
-- carries a line with leftText "Rockbiter 1 (56 min)" (type 0). ParseImbueLine reads that line: the name before the
-- rank is matched against the imbue spell names (resolved from the spell ids, so a localized client works), the
-- time in the brackets comes from Blizzard's own ITEM_ENCHANT_TIME_LEFT_* strings (a generic "(N unit)" is the
-- fallback). Each hand keeps its own record { state = "imbue" | "none" | "unknown", code, expiry }, and the tile shows
-- the hand with the LEAST time left. The tooltip is read OUT OF COMBAT ONLY (what it answers in combat is
-- unverified): on inventory, equipment and cast events, at regen, and on a slow tick. In combat the expiry counts
-- down from the last read, and a cast of an imbue starts a fresh hour on the hand it most likely went to (the first
-- weapon hand without one, the main hand first; the next read out of combat corrects a wrong guess). A weapon change
-- in combat forgets that hand (it shows "?" rather than a stale time). GetWeaponEnchantInfo stays as a secondary
-- source and is believed only when it answers a plain true.
--
-- A tooltip says "56 min" for anything from 56 to 57 minutes (or 55 to 56): a new read replaces a stored expiry only
-- when it differs by a whole unit or more, so the countdown does not stair-step under the reads.
--
-- SHIELD. Lightning Shield and its orb count come from the FS.PlayerAuras snapshot Buffs.lua keeps (plain values,
-- frozen in combat), so no aura API is read here. In combat the last live answer is an estimate (a "~" before the
-- count). Its end is the aura's own expirationTime; with none, the moment it was applied (our cast, else the first
-- sighting) plus the aura's duration or ten minutes, never the last read plus ten minutes. A Water Shield (up, or cast
-- in combat) is "other": the tile is quiet, not amber. A spell not learned is "locked" (the tab draws its mold).
--
-- Listeners start only from Start(), which BuffTab.lua calls after its tiles were built for a Shaman, so a failed or
-- non-Shaman build never leaves one mutating state for a tab that does not draw.
--
-- Loads before BuffTab.lua. Nothing here is verified in game except the tooltip line quoted above.

local _, FS = ...

local ShamanBuffs = {}
FS.ShamanBuffs = ShamanBuffs

local FH = FS.FrameHelpers

local M = {
    IMBUE_S = 3600, SHIELD_ORBS = 3,        -- a fresh imbue, a fresh Lightning Shield
    SHIELD_S = 600,                         -- Lightning Shield lasts ten minutes
    EXPIRING_S = 300,                       -- five minutes or less turns the tile to the expiring colour
    CAST_GRACE = 1.5,                       -- seconds a cast stands before the weapon or the aura has caught up
    READ_EVERY = 5,                         -- seconds between tooltip reads out of combat
    AFTER_CAST = { 0.5, 2.0 },              -- reads after an imbue cast: the weapon catches up a moment later
    SHIELD_UNLOCK = 8,                      -- Lightning Shield opens at level 8
    MAIN = 16, OFF = 17,                    -- the weapon slots
    REGEN_HOLD = 0.5,                       -- seconds after regen the aura snapshot may still lag: stay an estimate
}
ShamanBuffs.M = M
local SLOTS = { M.MAIN, M.OFF }     -- walked every tick: one table, never built per call

-- The four imbues, in the order they are learned. `base` is a rank id used to read the spell's localized name;
-- `short` is the English name the weapon tooltip uses (before its rank).
local IMBUES = {
    { code = "RB", name = "Rockbiter Weapon", short = "Rockbiter", base = 8017 },
    { code = "FT", name = "Flametongue Weapon", short = "Flametongue", base = 8024 },
    { code = "FB", name = "Frostbrand Weapon", short = "Frostbrand", base = 8033 },
    { code = "WF", name = "Windfury Weapon", short = "Windfury", base = 8232 },
}
local SHIELD = { name = "Lightning Shield", base = 324 }
local WATER = { name = "Water Shield", base = 24398 }
ShamanBuffs.IMBUES = IMBUES
-- Item equip locations that are a weapon (a shield is INVTYPE_SHIELD, a held-in-off-hand frill INVTYPE_HOLDABLE).
local WEAPON_LOC = {
    INVTYPE_WEAPON = true, INVTYPE_WEAPONMAINHAND = true, INVTYPE_WEAPONOFFHAND = true, INVTYPE_2HWEAPON = true,
}
-- The enchant time strings Blizzard formats a weapon tooltip line with, as { global, English default, seconds }.
local TIME_FORMATS = {
    { "ITEM_ENCHANT_TIME_LEFT_SEC", "%s (%d sec)", 1 },
    { "ITEM_ENCHANT_TIME_LEFT_MIN", "%s (%d min)", 60 },
    { "ITEM_ENCHANT_TIME_LEFT_HOURS", "%s (%d hour)", 3600 },
    { "ITEM_ENCHANT_TIME_LEFT_DAYS", "%s (%d day)", 86400 },
}

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "shamanbuffs_" .. key, "|cffff4488Forever STUwave|r: shaman buffs: " .. tostring(msg))
    end
end

local function IsSecret(v) return FS.IsSecret and FS.IsSecret(v) or false end
local function PlainOf(v, kind)
    if IsSecret(v) or type(v) ~= kind then return nil end
    return v
end

local function Now()
    local ok, t = pcall(GetTime)
    return ok and PlainOf(t, "number") or 0
end

local function InCombat()
    return InCombatLockdown and InCombatLockdown() and true or false
end

-------------------------------------------------------------------------------
-- Spells: names, what the player has learned
-------------------------------------------------------------------------------

local nameById = {}
local function SpellNameById(id)
    local hit = nameById[id]
    if hit then return hit end
    local name = FH.SpellById(id)
    if name then nameById[id] = name end
    return name
end

-- Whether a spell name is this definition's (English, or the client's own language through the rank id).
local function NameIs(name, def)
    if type(name) ~= "string" then return false end
    return name == def.name or name == SpellNameById(def.base)
end

local function SpellKnown(def)
    local id = FH.ResolveSpell(def.name)
    if id and FH.IsKnownSpellId(id) then return true end
    return def.base ~= id and FH.IsKnownSpellId(def.base) or false
end

-- Learned spells: a yes sticks until the spellbook changes (which clears everything); a no is asked again whenever
-- RefreshKnown runs (start, regen, entering the world), so a spell the first look missed is not locked out for good.
local known = {}
local function RefreshKnown()
    for _, def in ipairs(IMBUES) do
        if known[def.code] ~= true then known[def.code] = SpellKnown(def) end
    end
    if known.shield ~= true then known.shield = SpellKnown(SHIELD) end
end

local function KnownImbues()
    local n, only = 0, nil
    for _, def in ipairs(IMBUES) do
        if known[def.code] then n = n + 1; only = def.code end
    end
    return n, only
end

local function BestKnownImbue()
    for i = #IMBUES, 1, -1 do
        if known[IMBUES[i].code] then return IMBUES[i].code end
    end
    return nil
end

local function DefOf(code)
    for _, def in ipairs(IMBUES) do
        if def.code == code then return def end
    end
end

-- The name a spell attribute casts for an imbue code: the localized name, else the English one.
local function CastName(code)
    local def = DefOf(code)
    if not def then return nil end
    return SpellNameById(def.base) or def.name
end

-------------------------------------------------------------------------------
-- The tooltip line
-------------------------------------------------------------------------------

-- The names a weapon tooltip may call an imbue, lower case, longest first: the spell name, the spell name without
-- its last word ("Rockbiter Weapon" -> "Rockbiter"), its first word, and the English short name.
local candidates = {}
local function Candidates(def)
    local hit = candidates[def.code]
    if hit then return hit end
    local full = SpellNameById(def.base)
    local list, seen = {}, {}
    local function add(text)
        if type(text) ~= "string" then return end
        text = text:lower()
        if #text >= 4 and not seen[text] then
            seen[text] = true
            list[#list + 1] = text
        end
    end
    if full then
        add(full)
        add(full:match("^(.-)%s+%S+$"))
        add(full:match("^(%S+)"))
    end
    add(def.name)
    add(def.short)
    table.sort(list, function(a, b) return #a > #b end)
    if full then candidates[def.code] = list end      -- an unresolved name is asked again next time
    return list
end

-- The imbue code a tooltip name part ("Rockbiter 1") names, or nil. Only a rank (digits or a Roman numeral) may
-- follow the name.
local function CodeOfName(part)
    part = part:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):lower()
    for _, def in ipairs(IMBUES) do
        for _, cand in ipairs(Candidates(def)) do
            if part:sub(1, #cand) == cand and part:sub(#cand + 1):match("^%s*[%dxiv]*%s*$") then
                return def.code
            end
        end
    end
    return nil
end

-- A Lua pattern for one of Blizzard's format strings: %s is the name, %d the count, a |4one:many; plural is skipped.
local function PatternOf(fmt)
    local out, i = { "^" }, 1
    while i <= #fmt do
        local c = fmt:sub(i, i)
        local two = fmt:sub(i, i + 1)
        if two == "%s" then
            out[#out + 1] = "(.-)"
            i = i + 2
        elseif two == "%d" then
            out[#out + 1] = "(%d+)"
            i = i + 2
        elseif two == "|4" then
            local close = fmt:find(";", i, true)
            out[#out + 1] = "[^%)]-"
            i = (close or #fmt) + 1
        elseif c:find("[%(%)%.%+%-%*%?%[%]%^%$%%]") then
            out[#out + 1] = "%" .. c
            i = i + 1
        else
            out[#out + 1] = c
            i = i + 1
        end
    end
    out[#out + 1] = "$"
    return table.concat(out)
end

local timePatterns
local function TimePatterns()
    if timePatterns then return timePatterns end
    timePatterns = {}
    for _, def in ipairs(TIME_FORMATS) do
        local fmt = _G[def[1]]
        if type(fmt) ~= "string" or IsSecret(fmt) or not fmt:find("%s", 1, true) then fmt = def[2] end
        timePatterns[#timePatterns + 1] = { PatternOf(fmt), def[3] }
    end
    return timePatterns
end

local function UnitSeconds(unit)
    unit = unit:lower()
    if unit:find("^s") then return 1 end
    if unit:find("^m") then return 60 end
    if unit:find("^h") then return 3600 end
    if unit:find("^d") then return 86400 end
    return nil
end

-- "Rockbiter 1 (56 min)" -> "RB", 3360, 60: the imbue code, the seconds the line says and the size of one unit of
-- its clock (60 for minutes), or nil when the line is not an imbue line. Hours and days are read as well.
function ShamanBuffs.ParseImbueLine(text)
    if IsSecret(text) or type(text) ~= "string" or text == "" then return nil end
    for _, entry in ipairs(TimePatterns()) do
        local name, n = text:match(entry[1])
        n = tonumber(n)
        if name and n then
            local code = CodeOfName(name)
            if code then return code, n * entry[2], entry[2] end
        end
    end
    local name, n, unit = text:match("^(.-)%s*%((%d+)%s*([^%)%s]+)%.?%)%s*$")
    local secs = unit and UnitSeconds(unit)
    if name and secs then
        local code = CodeOfName(name)
        if code then return code, tonumber(n) * secs, secs end
    end
    return nil
end

-- "imbue", code, seconds, unit | "none" | "unreadable" for one weapon slot's tooltip. Out of combat only (the caller).
local function ReadTooltip(slot)
    local api = C_TooltipInfo and C_TooltipInfo.GetInventoryItem
    if type(api) ~= "function" then return "unreadable" end
    local ok, data = pcall(api, "player", slot)
    if not ok or IsSecret(data) or type(data) ~= "table" then return "unreadable" end
    local lines = data.lines
    if IsSecret(lines) or type(lines) ~= "table" or #lines == 0 then return "unreadable" end
    local sawSecret = false
    for i = 1, #lines do
        local line = lines[i]
        if IsSecret(line) or type(line) ~= "table" then
            sawSecret = true
        else
            local text = line.leftText
            if IsSecret(text) then
                sawSecret = true
            elseif type(text) == "string" then
                local code, secs, unit = ShamanBuffs.ParseImbueLine(text)
                if code then return "imbue", code, secs, unit end
            end
        end
    end
    return sawSecret and "unreadable" or "none"
end
ShamanBuffs.ReadTooltip = ReadTooltip

-------------------------------------------------------------------------------
-- Imbue data
-------------------------------------------------------------------------------

local function NewHand(slot)
    -- weapon: true, false (a shield, a frill, an empty hand) or nil (not readable); state: "imbue", "none" or "unknown"
    return { slot = slot, weapon = nil, state = "unknown", code = nil, expiry = nil, unit = 1, castAt = nil,
        estimated = false }
end
local hands = { [M.MAIN] = NewHand(M.MAIN), [M.OFF] = NewHand(M.OFF) }
local lastCode          -- the last imbue seen or cast, kept for the missing tile
local nextRead = 0      -- GetTime() of the next slow read

local weaponLoc = {}      -- item id -> true when it is a weapon, false when it is not

-- true when the item in this equipment slot is a weapon, false when it plainly is not (empty, shield, frill), nil
-- when it cannot be told (a refusal or a secret answer).
local function HandHoldsWeapon(slot)
    if type(GetInventoryItemID) ~= "function" then return nil end
    local ok, itemId = pcall(GetInventoryItemID, "player", slot)
    if not ok or IsSecret(itemId) then return nil end
    if itemId == nil then return false end
    itemId = PlainOf(itemId, "number")
    if not itemId then return nil end
    local isWeapon = weaponLoc[itemId]
    if isWeapon == nil then
        local info = (C_Item and C_Item.GetItemInfoInstant) or GetItemInfoInstant
        if type(info) ~= "function" then return nil end
        local ok2, _, _, _, equipLoc = pcall(info, itemId)
        equipLoc = ok2 and PlainOf(equipLoc, "string") or nil
        if not equipLoc then return nil end
        isWeapon = WEAPON_LOC[equipLoc] or false
        weaponLoc[itemId] = isWeapon
    end
    return isWeapon
end

local function ClearHand(h)
    h.state, h.code, h.expiry, h.unit, h.castAt, h.estimated = "none", nil, nil, 1, nil, false
end

-- A read said "imbue": the expiry is now + the line's time, except that a stored expiry within one unit of it stays
-- (the tooltip rounds to its unit), and an estimate from a cast is replaced outright.
local function ApplyImbue(h, code, secs, unit, now)
    local candidate = now + secs
    if h.state == "imbue" and h.expiry and not h.estimated and h.code == code and unit > 1
        and math.abs(candidate - h.expiry) < unit then
        candidate = h.expiry
    end
    h.state, h.code, h.expiry, h.unit, h.estimated, h.castAt = "imbue", code, candidate, unit, false, nil
    lastCode = code
end

-- GetWeaponEnchantInfo, believed only when it answers a plain true: ms main, ms off (nil when not plain-true).
local function ReadEnchantInfo()
    if type(GetWeaponEnchantInfo) ~= "function" then return nil, nil end
    local ok, hasMain, msMain, _, _, hasOff, msOff = pcall(GetWeaponEnchantInfo)
    if not ok then return nil, nil end
    local main, off
    if not IsSecret(hasMain) and hasMain == true then main = PlainOf(msMain, "number") end
    if not IsSecret(hasOff) and hasOff == true then off = PlainOf(msOff, "number") end
    if main and main <= 0 then main = nil end
    if off and off <= 0 then off = nil end
    return main, off
end

-- A plain true from GetWeaponEnchantInfo for a hand that holds no imbue of ours yet: believed.
local function TakeEnchantMs(h, ms, now)
    if ms and h.weapon ~= false and h.state ~= "imbue" then
        local n, only = KnownImbues()
        ApplyImbue(h, lastCode or (n == 1 and only) or "IM", ms / 1000, 1, now)
    end
end

-- Both hands, from the weapon tooltips (and, secondarily, GetWeaponEnchantInfo). Out of combat only.
local function ReadHands(now)
    if InCombat() then return end
    for i = 1, #SLOTS do
        local slot = SLOTS[i]
        local h = hands[slot]
        h.weapon = HandHoldsWeapon(slot)
        if h.weapon == false then
            ClearHand(h)
        elseif h.weapon == true then
            -- a weapon that has not caught up with a cast of ours keeps the cast until the grace is over: it is
            -- neither "none" yet, nor another imbue than the one just cast
            local fresh = h.castAt and now < h.castAt + M.CAST_GRACE
            local status, code, secs, unit = ReadTooltip(slot)
            if status == "imbue" then
                if not (fresh and code ~= h.code) then ApplyImbue(h, code, secs, unit, now) end
            elseif status == "none" then
                if not fresh then ClearHand(h) end
            end
        end
    end
    local mainMs, offMs = ReadEnchantInfo()
    TakeEnchantMs(hands[M.MAIN], mainMs, now)
    TakeEnchantMs(hands[M.OFF], offMs, now)
end

-- The hand an imbue cast most likely went to: the first weapon hand without a live imbue, the main hand first;
-- with both imbued the main hand is replaced.
local function CastTarget(now)
    local main, off = hands[M.MAIN], hands[M.OFF]
    local function lacks(h) return h.state ~= "imbue" or not h.expiry or h.expiry <= now end
    if main.weapon ~= false and lacks(main) then return main end
    if off.weapon == true and lacks(off) then return off end
    return main
end

local changeFns = {}
function ShamanBuffs.OnChange(fn)
    changeFns[#changeFns + 1] = fn
end
local function Changed()
    for _, fn in ipairs(changeFns) do
        local ok, err = pcall(fn)
        if not ok then LogOnce("change", err) end
    end
end

local function ReadSoon(delay)
    if C_Timer and C_Timer.After then
        C_Timer.After(delay, function()
            local ok, err = pcall(function()
                ReadHands(Now())
                nextRead = Now() + M.READ_EVERY
            end)
            if not ok then LogOnce("read", err) end
            Changed()
        end)
    end
end

local function OnImbueCast(def, now)
    local h = CastTarget(now)
    h.state, h.code, h.expiry, h.unit, h.estimated, h.castAt = "imbue", def.code, now + M.IMBUE_S, 60, true, now
    lastCode = def.code
    for _, delay in ipairs(M.AFTER_CAST) do ReadSoon(delay) end
end

-------------------------------------------------------------------------------
-- Shield data
-------------------------------------------------------------------------------

local shield = {
    seen = nil,           -- the last live answer: "up", "missing" or nil (none yet)
    count = nil,          -- its orb count
    expiry = nil,         -- the aura's own end (expirationTime), if it told
    duration = nil,       -- the aura's duration, if it told
    appliedAt = nil,      -- when it was applied: our cast, else the first sighting
    castAt = nil,         -- a cast the snapshot has not confirmed yet
    other = false,        -- a Water Shield instead (up, or cast in combat): nothing to remind about
    frozen = false,       -- the snapshot cannot refresh (combat)
    available = false,    -- FS.PlayerAuras exists
    holdUntil = 0,        -- GetTime() until which the snapshot is not read (just after regen it may lag)
}

local function AuraIs(aura, def)
    if type(aura) ~= "table" then return false end
    if NameIs(aura.name, def) then return true end
    if aura.name == nil and type(aura.spellId) == "number" then return NameIs(SpellNameById(aura.spellId), def) end
    return false
end

local function ReadShield(now)
    local auras = FS.PlayerAuras
    if type(auras) ~= "table" or type(auras.Get) ~= "function" then
        shield.available = false
        return
    end
    shield.available = true
    if now < shield.holdUntil then
        shield.frozen = true
        return
    end
    local frozen = true
    if type(auras.IsFrozen) == "function" then
        local ok, answer = pcall(auras.IsFrozen)
        if ok and not IsSecret(answer) and answer == false then frozen = false end
    end
    shield.frozen = frozen
    if frozen then return end
    local ok, snap = pcall(auras.Get)
    local list = ok and type(snap) == "table" and snap.buffs or nil
    if type(list) ~= "table" then return end
    local other = false
    for i = 1, #list do
        local aura = list[i]
        if AuraIs(aura, SHIELD) then
            local wasUp = shield.seen == "up"
            shield.seen = "up"
            shield.count = PlainOf(aura.count, "number")
            local expires = PlainOf(aura.expirationTime, "number")
            shield.expiry = expires and expires > 0 and expires or nil
            local duration = PlainOf(aura.duration, "number")
            shield.duration = duration and duration > 0 and duration or nil
            if not wasUp or shield.castAt then shield.appliedAt = shield.castAt or now end
            shield.castAt, shield.other = nil, false
            return
        elseif AuraIs(aura, WATER) then
            other = true
        end
    end
    shield.other = other
    if shield.castAt and now < shield.castAt + M.CAST_GRACE then return end
    shield.seen, shield.count, shield.expiry, shield.duration, shield.appliedAt, shield.castAt =
        "missing", nil, nil, nil, nil, nil
end

-- When the shield falls off: the aura's own end, else the moment it was applied plus its duration or ten minutes.
local function ShieldEnd()
    if shield.expiry then return shield.expiry end
    if shield.appliedAt then return shield.appliedAt + (shield.duration or M.SHIELD_S) end
    return nil
end

local function OnShieldCast(now)
    shield.castAt, shield.other = now, false
end

-- A Water Shield cast replaces the Lightning Shield: no cast of ours is pending and nothing is missing.
local function OnWaterCast()
    shield.castAt, shield.other = nil, true
    shield.seen, shield.count, shield.expiry, shield.duration, shield.appliedAt = "missing", nil, nil, nil, nil
end

-------------------------------------------------------------------------------
-- The view the tiles paint
-------------------------------------------------------------------------------

-- 52 minutes read "52m", under a minute "45s".
local function FormatTime(remaining)
    if remaining >= 60 then return string.format("%dm", math.floor(remaining / 60)) end
    return string.format("%ds", math.max(0, math.floor(remaining)))
end
ShamanBuffs.FormatTime = FormatTime

local view = {
    imbue = {}, shield = {},
}

local function EvaluateImbue(now)
    local v = view.imbue
    v.mode, v.code, v.text, v.remaining, v.hand, v.lackHand, v.spell = nil, nil, nil, nil, nil, nil, nil
    local nKnown, onlyKnown = KnownImbues()
    local best -- the imbued hand with the least time left
    local lacking
    for i = 1, #SLOTS do
        local h = hands[SLOTS[i]]
        if h.state == "imbue" and h.expiry and h.expiry > now then
            if not best or h.expiry < best.expiry then best = h end
        elseif h.weapon == true and (h.state == "none" or h.state == "imbue") then
            lacking = lacking or h
        end
    end
    if not (nKnown > 0 or best) then return end          -- no imbue known and none on: the tile is absent
    local code
    if lacking then
        v.mode, v.text = "warn", "IMBUE"
        code = (best and best.code) or lastCode or BestKnownImbue()
        v.lackHand = lacking.slot == M.MAIN and "main" or "off"
    elseif best then
        local remaining = best.expiry - now
        v.mode = remaining <= M.EXPIRING_S and "exp" or "on"
        v.text, v.remaining, code = FormatTime(remaining), remaining, best.code
        v.hand = best.slot == M.MAIN and "main" or "off"
    else
        v.mode, v.text = "hollow", "?"
        code = lastCode or BestKnownImbue()
    end
    if not code and nKnown == 1 then code = onlyKnown end
    v.code = code or "IM"
    local def = DefOf(code)
    v.spell = (def and known[code] and CastName(code)) or (BestKnownImbue() and CastName(BestKnownImbue())) or nil
end

local function EvaluateShield(now)
    local v = view.shield
    v.mode, v.text, v.count, v.remaining, v.estimate, v.other = nil, nil, nil, nil, false, false
    v.code, v.unlock, v.spell = "LS", M.SHIELD_UNLOCK, SpellNameById(SHIELD.base) or SHIELD.name
    if not known.shield then
        v.mode = "locked"
        return
    end
    local count = shield.count
    local up = shield.seen == "up"
    local estimate
    local at = shield.castAt
    local ends
    if at and (now < at + M.CAST_GRACE or (shield.frozen and now < at + M.SHIELD_S)) then
        up, estimate, count, ends = true, true, M.SHIELD_ORBS, at + M.SHIELD_S
    elseif up then
        ends = ShieldEnd()
        if shield.frozen then
            estimate = true
            if ends and ends <= now then up = false end
        end
    end
    if not up and shield.other then
        v.mode, v.text, v.other = "hollow", "WS", true
        return
    end
    if shield.seen == nil and not up then
        v.mode, v.text = "hollow", "?"
    elseif up then
        local remaining = ends and ends - now or nil
        v.count, v.remaining, v.estimate = count, remaining, estimate or false
        if remaining and remaining <= M.EXPIRING_S then
            v.mode, v.text = "exp", FormatTime(remaining)
        else
            v.mode = "on"
            v.text = (count and count >= 1) and tostring(math.floor(count)) or "ON"
        end
        if estimate and (v.mode == "exp" or (count and count >= 1)) then v.text = "~" .. v.text end
    else
        v.mode, v.text = "warn", "SHIELD"
    end
end

-- Reads the slow sources when they are due and returns the view: { imbue = {...}, shield = {...} }. The tables are
-- reused; a field is nil when it does not apply. imbue.mode: nil (absent), "on", "exp", "warn", "hollow"; shield.mode
-- adds "locked".
function ShamanBuffs.Update(now)
    now = now or Now()
    if now >= nextRead and not InCombat() then
        nextRead = now + M.READ_EVERY
        ReadHands(now)
    end
    ReadShield(now)       -- cheap: in combat it only notes that the snapshot is frozen, so the "~" appears at once
    EvaluateImbue(now)
    EvaluateShield(now)
    return view
end

function ShamanBuffs.View()
    return view
end

-- What the spellbook gives the tab to decide locks with.
function ShamanBuffs.Known()
    RefreshKnown()
    local n = KnownImbues()
    return { imbue = n > 0, shield = known.shield and true or false }
end

-- The imbue the tile should cast right now: the displayed one, else the best known; nil with none known.
function ShamanBuffs.ImbueSpell()
    local v = view.imbue
    if v.spell then return v.spell end
    local best = BestKnownImbue()
    return best and CastName(best) or nil
end

-------------------------------------------------------------------------------
-- Events
-------------------------------------------------------------------------------

-- Records a cast of an imbue or of a shield and says which it was ("imbue", "shield", "water" or nil).
local function NoteCast(spellId, now)
    local id = PlainOf(spellId, "number")
    if not id then return nil end
    local name = SpellNameById(id)
    if not name then return nil end
    for _, def in ipairs(IMBUES) do
        if NameIs(name, def) then
            OnImbueCast(def, now)
            return "imbue"
        end
    end
    -- The orb procs of Lightning Shield carry its name and may report a cast: only an id the player knows counts.
    if NameIs(name, SHIELD) and FH.IsKnownSpellId(id) then
        OnShieldCast(now)
        return "shield"
    end
    if NameIs(name, WATER) and FH.IsKnownSpellId(id) then
        OnWaterCast()
        return "water"
    end
    return nil
end
ShamanBuffs.NoteCast = function(spellId) return NoteCast(spellId, Now()) end

local SPELLBOOK_EVENTS = {
    SPELLS_CHANGED = true, PLAYER_LEVEL_UP = true, LEARNED_SPELL_IN_SKILL_LINE = true, LEARNED_SPELL_IN_TAB = true,
}

local function OnEvent(_, event, unit, _, spellId)
    local now = Now()
    if event == "UNIT_SPELLCAST_SUCCEEDED" then
        if not IsSecret(unit) and unit ~= "player" then return end
        if not NoteCast(spellId, now) then return end       -- not ours: nothing moved, nobody is told
    elseif event == "UNIT_AURA" then
        if not IsSecret(unit) and unit ~= "player" then return end
        ReadShield(now)
    elseif event == "UNIT_INVENTORY_CHANGED" then
        if not IsSecret(unit) and unit ~= "player" then return end
        ReadHands(now)
    elseif event == "PLAYER_EQUIPMENT_CHANGED" then
        -- unit is the slot here. A weapon swapped in combat cannot be read: that hand is forgotten, not guessed.
        local slot = PlainOf(unit, "number")
        if InCombat() then
            local h = slot and hands[slot]
            if h then
                h.weapon, h.state, h.code, h.expiry, h.estimated, h.castAt = nil, "unknown", nil, nil, false, nil
            end
        else
            ReadHands(now)
        end
    elseif SPELLBOOK_EVENTS[event] or event == "PLAYER_ENTERING_WORLD" then
        known = {}
        RefreshKnown()
        ReadHands(now)
        ReadShield(now)
    else           -- PLAYER_REGEN_ENABLED
        -- the aura snapshot (Buffs.lua) may not have caught up yet: keep the last answer an estimate for a moment and
        -- let a later tick read it
        RefreshKnown()
        ReadHands(now)
        shield.holdUntil = now + M.REGEN_HOLD
        shield.frozen = true
    end
    nextRead = now + M.READ_EVERY
    Changed()
end

local events
-- Starts listening; BuffTab.lua calls it once its tiles are built for a Shaman. Idempotent. A failed build never
-- calls it, so nothing runs for a tab that does not draw.
function ShamanBuffs.Start()
    if events then return true end
    events = CreateFrame("Frame")
    local function reg(event, unitOnly, optional)
        local ok, err
        if unitOnly then
            ok, err = pcall(events.RegisterUnitEvent, events, event, "player")
        else
            ok, err = pcall(events.RegisterEvent, events, event)
        end
        if not ok and not optional then LogOnce("event_" .. event, event .. " cannot be registered (" .. tostring(err) .. ")") end
    end
    reg("UNIT_SPELLCAST_SUCCEEDED", true)
    reg("UNIT_INVENTORY_CHANGED", true)
    reg("UNIT_AURA", true)
    reg("PLAYER_EQUIPMENT_CHANGED")
    reg("PLAYER_REGEN_ENABLED")
    reg("PLAYER_ENTERING_WORLD")
    for event in pairs(SPELLBOOK_EVENTS) do reg(event, false, true) end
    events:SetScript("OnEvent", function(...)
        local ok, err = pcall(OnEvent, ...)
        if not ok then LogOnce("event", err) end
    end)
    RefreshKnown()
    local now = Now()
    pcall(ReadHands, now)
    pcall(ReadShield, now)
    nextRead = now + M.READ_EVERY
    return true
end

-- Forgets everything the model holds (a new session in a test, or a character change).
function ShamanBuffs.Reset()
    for slot in pairs(hands) do hands[slot] = NewHand(slot) end
    lastCode, nextRead, known, candidates, timePatterns = nil, 0, {}, {}, nil
    shield.seen, shield.count, shield.expiry, shield.duration, shield.appliedAt, shield.castAt = nil, nil, nil, nil, nil, nil
    shield.other, shield.frozen, shield.available, shield.holdUntil = false, false, false, 0
end
