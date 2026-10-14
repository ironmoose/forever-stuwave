-- Forever STUwave: Shaman totem state (data only, no drawing)
--
-- One record per totem slot (Fire 1, Earth 2, Water 3, Air 4): is a totem up, its name, icon and spell when readable, the
-- duration object, and plain seconds when they are knowable. The Gunsight Shaman module (GunsightShaman.lua) draws it; a totem
-- gone alert and Next Cast are meant to read the same records, so this file draws nothing and keeps listening while that
-- module is hidden (it only records data).
--
-- WHAT THE CLIENT SAYS (measured on this client; mocked checks only pin the logic below, tools/shamantotems-harness.py):
--   * Out of combat, PLAYER_TOTEM_UPDATE and GetTotemInfo(slot) are fully plain: haveTotem, name, start, duration, icon,
--     modRate, spellID. But haveTotem is TRUE with a blank name when no totem stands (it follows the totem item in the bags), so
--     "up" is a non empty name or a duration above zero, never haveTotem alone.
--   * In combat EVERY GetTotemInfo return is secret in all four slots, and GetTotemTimeLeft is secret for a live slot.
--     C_Secrets.ShouldTotemSlotBeSecret is unreliable and is not used. Nothing below compares, adds or concatenates a value
--     before FS.IsSecret has said it is plain.
--   * GetTotemDuration(slot) answers a plain duration object only while that slot has a live totem (nil when empty), in and out
--     of combat. Every method on the object returns secrets, but Cooldown:SetCooldownFromDurationObject and
--     StatusBar:SetTimerDuration accept it in combat. So the in combat "is it up" test is: the object is not nil.
--   * UNIT_SPELLCAST_SUCCEEDED for "player" is plain in combat (spell id and name).
--
-- WHERE A NUMBER COMES FROM (the `source` field of a record):
--   "read"  a plain GetTotemInfo read out of combat (start + duration). Kept through the fight that follows: the totem is the
--           same one, so its start and duration do not change (fallback A).
--   "cast"  a drop seen in combat: GetTime() at UNIT_SPELLCAST_SUCCEEDED of a totem spell plus the base duration from DEFS below
--           (fallback B). The next plain read replaces it (the first PLAYER_REGEN_ENABLED, or any out of combat update).
--   nil     up (the duration object says so) but no number is knowable, for example after a /reload in combat. The pole then
--           runs on the duration object alone and the block count is not available.
--
-- FAR (a totem you walked away from). UnitPosition("player") is stamped at the drop, because a totem drops at the player's feet:
-- y, x and the instance id, taken at the player's UNIT_SPELLCAST_SUCCEEDED of a totem spell (a set drop stamps every element its
-- multi-cast slots hold, see OnCast). While the totem is up, a throttled Tick compares the stamp with the current position and sets `far` when the distance
-- passes the totem's range (DEFS, 20 yd by default). FAR is only ever set from two PLAIN numbers with the same instance id: a nil
-- position (instances), a secret one, a different instance id or no stamp leaves it false, never a guess. The stamp is dropped
-- with the slot, and a cast of Totemic Projection (matched by id or localized name, see ResolveNames) drops every stamp because it
-- moves the totems somewhere this addon cannot see. The ranges are mostly unmeasured (see DEFS). FAR source: verified live: pending probe.
--
-- RECORD FIELDS (read only for callers; one table per slot, reused, nothing is allocated after load):
--   up, far, unlocked        booleans
--   name, icon, spellID      plain, nil when unknown
--   start, duration, expires plain GetTime based numbers (expires = start + duration), nil when unknown
--   source                   "read" | "cast" | nil
--   obj                      the duration object (plain), nil when down or unreadable
--
-- Nothing here is verified in game beyond the facts quoted above.

local _, FS = ...

local T = {}
FS.ShamanTotems = T

local floor, ceil, sqrt, huge = math.floor, math.ceil, math.sqrt, math.huge

local NSLOTS = 4
local BLOCKS = 8                    -- the pole's block count: ceil(remaining / duration * 8)
local GRACE = 1.5                   -- seconds a drop stamp may run ahead of the slot reading as up
local EXPIRY_SLACK = 0.25           -- seconds past the expected end before the slot is asked again
local RECHECK = 0.5                 -- seconds between those asks
local FAR_EVERY = 0.25              -- seconds between position reads while a stamped totem stands
local FAR_HYSTERESIS = 1            -- yards inside the range before FAR clears again
local DEFAULT_RANGE = 20            -- yards: the aura / buff totem default

T.NSLOTS, T.BLOCKS = NSLOTS, BLOCKS
T.ELEMENTS = { "fire", "earth", "water", "air" }
T.UNLOCK = { 10, 4, 20, 30 }        -- the level each element opens at (Fire 10, Earth 4, Water 20, Air 30)

-- One row per totem up to level 30: slot, rank 1 spell id (the same ids as TotemBar.lua), English name, base duration in seconds,
-- how sure that duration is, and the range in yards (nil = DEFAULT_RANGE).
--   "m" measured on this client      Stoneskin 300 s.
--   "r" reported by a Forever source Strength of Earth, Healing Stream, Mana Spring, Nature Resistance 5 min (the persistent buff
--                                    totem change of 2026-10-07), Searing 30 s rank 1 (35 s rank 2; rank 3 not confirmed: a drop of
--                                    a higher rank reads short here until the next plain read corrects it), Magma 20 s, Grounding 45 s.
--   "u" unmeasured                   Classic values or a guess. The buff totems that are not in the "r" list are assumed to be
--                                    persistent too (300 s): a duration guessed too long only keeps the pole full a little longer,
--                                    one guessed too short would raise a false last block, so the long side is the safe one.
-- Ranges: Searing 20 yd (attack range, reported), Magma 8 yd (reported), Earthbind 10 yd and Stoneclaw 8 yd (Classic, unmeasured);
-- every other range is the 20 yd default and unmeasured.
local DEFS = {
    { slot = 1, id = 3599, name = "Searing Totem", dur = 30, sure = "r", range = 20 },
    { slot = 1, id = 8181, name = "Frost Resistance Totem", dur = 300, sure = "u" },
    { slot = 1, id = 8190, name = "Magma Totem", dur = 20, sure = "r", range = 8 },
    { slot = 1, id = 8227, name = "Flametongue Totem", dur = 300, sure = "u" },
    { slot = 2, id = 8071, name = "Stoneskin Totem", dur = 300, sure = "m" },
    { slot = 2, id = 2484, name = "Earthbind Totem", dur = 45, sure = "u", range = 10 },
    { slot = 2, id = 5730, name = "Stoneclaw Totem", dur = 15, sure = "u", range = 8 },
    { slot = 2, id = 8075, name = "Strength of Earth Totem", dur = 300, sure = "r" },
    { slot = 2, id = 8143, name = "Tremor Totem", dur = 300, sure = "u" },
    { slot = 3, id = 5394, name = "Healing Stream Totem", dur = 300, sure = "r" },
    { slot = 3, id = 8166, name = "Poison Cleansing Totem", dur = 300, sure = "u" },
    { slot = 3, id = 5675, name = "Mana Spring Totem", dur = 300, sure = "r" },
    { slot = 3, id = 8184, name = "Fire Resistance Totem", dur = 300, sure = "u" },
    { slot = 4, id = 8177, name = "Grounding Totem", dur = 45, sure = "r" },
    { slot = 4, id = 10595, name = "Nature Resistance Totem", dur = 300, sure = "r" },
}
T.DEFS = DEFS

-- The set drops (they put four totems down in one event, so only the position can be stamped) and Totemic Projection.
local SET_IDS = { [66842] = "Call of the Elements", [66843] = "Call of the Ancestors", [66844] = "Call of the Spirits" }
-- Totemic Projection has no id measured on this client (FSCheck probes it by name). Ids to list here when one is: they resolve to the
-- localized name like the others. Meanwhile ResolveNames asks the spell book for the English name and learns the id and the
-- localized name from the answer (an English client, or any client where the book answers to that name).
local PROJECTION_IDS = {}
local PROJECTION = "Totemic Projection"
local PROJECTION_DEF = { projection = true }
local SET_INDEX = { [66842] = 1, [66843] = 2, [66844] = 3 }       -- the set number each set drop spell stands for
local SET_DEFS = {}                                                -- spell id -> { set = true, index = n }
for id, index in pairs(SET_INDEX) do SET_DEFS[id] = { set = true, index = index } end

local BY_ID, BY_NAME, NAME_ID = {}, {}, {}
for _, def in ipairs(DEFS) do
    BY_ID[def.id] = def
    BY_NAME[def.name] = def
end
for id, name in pairs(SET_IDS) do
    BY_ID[id] = SET_DEFS[id]
    BY_NAME[name] = SET_DEFS[id]
end
BY_NAME[PROJECTION] = PROJECTION_DEF
for _, id in ipairs(PROJECTION_IDS) do BY_ID[id] = PROJECTION_DEF end

local S = {}                        -- slot -> record
for slot = 1, NSLOTS do
    S[slot] = {
        slot = slot, element = T.ELEMENTS[slot],
        up = false, far = false, unlocked = true,
        checkAt = 0, farAt = 0, stampAt = nil, posY = nil, posX = nil, posInst = nil, range = nil,
    }
end
local subs = {}
local started = false

-------------------------------------------------------------------------------
-- Plain readers: FS.IsSecret first, always
-------------------------------------------------------------------------------

local function Secret(v)
    local guard = FS.IsSecret
    return guard ~= nil and guard(v) == true
end

local function PlainNum(v)
    if Secret(v) then return nil end
    if type(v) ~= "number" or v ~= v or v == huge or v == -huge then return nil end
    return v
end

local function PlainStr(v)
    if Secret(v) then return nil end
    if type(v) ~= "string" then return nil end
    return v
end

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "shamantotems_" .. key, "|cffff4488Forever STUwave|r: shaman totems: " .. tostring(msg))
    end
end

-------------------------------------------------------------------------------
-- Subscribers
-------------------------------------------------------------------------------

-- fn(slot, record) after a slot's record changed (up, far, unlocked, spell, numbers, source or duration object).
function T.Subscribe(fn)
    if type(fn) ~= "function" then return end
    for i = 1, #subs do if subs[i] == fn then return end end
    subs[#subs + 1] = fn
end

function T.Unsubscribe(fn)
    for i = #subs, 1, -1 do
        if subs[i] == fn then table.remove(subs, i) end
    end
end

local function Notify(slot)
    local st = S[slot]
    for i = #subs, 1, -1 do
        local fn = subs[i]
        if fn then
            local ok, err = pcall(fn, slot, st)
            if not ok then LogOnce("subscriber", err) end
        end
    end
end

-------------------------------------------------------------------------------
-- Reading a slot
-------------------------------------------------------------------------------

-- The duration object: known (the call answered), and the object or nil. A throw or a secret answer is "not known".
local function ReadObject(slot)
    if type(GetTotemDuration) ~= "function" then return false end
    local ok, obj = pcall(GetTotemDuration, slot)
    if not ok or Secret(obj) then return false end
    return true, obj
end

local function ClearStamp(st)
    st.stampAt, st.posY, st.posX, st.posInst, st.range = nil, nil, nil, nil, nil
end

local function ClearNumbers(st)
    st.name, st.icon, st.spellID = nil, nil, nil
    st.start, st.duration, st.expires, st.source = nil, nil, nil, nil
    ClearStamp(st)
end

-- The player's position as three plain numbers (y, x, instance id), or nil: UnitPosition answers nothing in instances and may
-- answer a secret in combat. Returns the values, so nothing is allocated.
local function ReadPosition()
    if type(UnitPosition) ~= "function" then return nil end
    local ok, y, x, _, inst = pcall(UnitPosition, "player")
    if not ok then return nil end
    y, x, inst = PlainNum(y), PlainNum(x), PlainNum(inst)
    if y == nil or x == nil or inst == nil then return nil end
    return y, x, inst
end

-- Sets st.far from the stamp and the player's position now; returns true when it changed.
local function EvalFar(st)
    local far = false
    if st.up and st.posY ~= nil then
        local y, x, inst = ReadPosition()
        if y ~= nil and inst == st.posInst then
            local dy, dx = y - st.posY, x - st.posX
            local range = st.range or DEFAULT_RANGE
            if st.far then range = range - FAR_HYSTERESIS end
            far = dy * dy + dx * dx > range * range
        end
    end
    if far == st.far then return false end
    st.far = far
    return true
end

-- Reads one slot and updates its record; notifies when anything a caller can see changed.
local function RefreshSlot(slot, now, force)
    local st = S[slot]
    now = now or GetTime()
    local wasUp, wasFar, wasSpell, wasExpires, wasSource, wasObj, wasDur, wasOpen =
        st.up, st.far, st.spellID, st.expires, st.source, st.obj, st.duration, st.unlocked

    local readable, plainUp = false, false
    local nameP, startP, durP, iconP, idP
    if type(GetTotemInfo) == "function" then
        local ok, _, name, start, dur, icon, _, spellID = pcall(GetTotemInfo, slot)
        if ok and not Secret(name) and not Secret(start) and not Secret(dur) then
            readable = true
            nameP, startP, durP = PlainStr(name), PlainNum(start), PlainNum(dur)
            iconP, idP = icon, spellID
            plainUp = (nameP ~= nil and nameP ~= "") or (durP ~= nil and durP > 0)
        end
    end
    local known, obj = ReadObject(slot)

    local up
    if readable then
        up = plainUp or (known and obj ~= nil)
    elseif known then
        up = obj ~= nil
    else
        return                                  -- nothing can say: leave the record as it was
    end

    if up then
        st.up = true
        st.obj = known and obj or nil
        if readable then
            if nameP ~= nil and nameP ~= "" then st.name = nameP end
            if not Secret(iconP) and iconP ~= nil then st.icon = iconP end
            idP = PlainNum(idP)
            if idP ~= nil and idP > 0 then st.spellID = idP end
            if startP ~= nil and durP ~= nil and startP > 0 and durP > 0 then
                st.start, st.duration, st.expires, st.source = startP, durP, startP + durP, "read"
            end
        end
        st.unlocked = true
    else
        st.up, st.obj = false, nil
        -- a drop stamp made a moment ago may simply be ahead of the totem appearing: keep it, drop everything else
        if not (st.stampAt ~= nil and now - st.stampAt <= GRACE) then ClearNumbers(st) end
    end

    EvalFar(st)

    if force or st.up ~= wasUp or st.far ~= wasFar or st.spellID ~= wasSpell or st.expires ~= wasExpires
        or st.source ~= wasSource or st.obj ~= wasObj or st.duration ~= wasDur or st.unlocked ~= wasOpen then
        Notify(slot)
    end
end

-- force: nil, true (every slot notifies) or a slot number (only that one does)
local function RefreshAll(now, force)
    now = now or GetTime()
    for slot = 1, NSLOTS do RefreshSlot(slot, now, force == true or force == slot) end
end

-------------------------------------------------------------------------------
-- Unlocked: is the element open for this character
-------------------------------------------------------------------------------

local BOOK_FNS = { "IsPlayerSpell", "IsSpellKnown" }
local function KnowsSpell(id)
    for i = 1, #BOOK_FNS do
        local f = _G[BOOK_FNS[i]]
        if type(f) == "function" then
            local ok, known = pcall(f, id)
            if ok and not Secret(known) and known == true then return true end
        end
    end
    return false
end

-- Open when a totem of the element is known or stands, or when the level reaches the element's. A locked verdict needs a plain
-- level below the unlock and no known totem: a wrong "open" only draws an empty pole, a wrong "locked" would hide a real one.
local function EvalUnlocked(st)
    if st.up then return true end
    for _, def in ipairs(DEFS) do
        if def.slot == st.slot and KnowsSpell(def.id) then return true end
    end
    local level
    if type(UnitLevel) == "function" then
        local ok, v = pcall(UnitLevel, "player")
        if ok then level = PlainNum(v) end
    end
    if level == nil then return true end
    return level >= T.UNLOCK[st.slot]
end

function T.RefreshUnlocked()
    for slot = 1, NSLOTS do
        local st = S[slot]
        local open = EvalUnlocked(st)
        if open ~= st.unlocked then
            st.unlocked = open
            Notify(slot)
        end
    end
end

-------------------------------------------------------------------------------
-- Casts
-------------------------------------------------------------------------------

local function SpellName(id)
    local modern = C_Spell and C_Spell.GetSpellName
    if type(modern) == "function" then
        local ok, name = pcall(modern, id)
        if ok then return PlainStr(name) end
        return nil
    end
    if type(GetSpellInfo) == "function" then
        local ok, name = pcall(GetSpellInfo, id)
        if ok then return PlainStr(name) end
    end
    return nil
end

local function SpellIcon(id)
    local modern = C_Spell and C_Spell.GetSpellTexture
    if type(modern) ~= "function" then return nil end
    local ok, tex = pcall(modern, id)
    if ok and not Secret(tex) and (type(tex) == "number" or type(tex) == "string") then return tex end
    return nil
end

-- The totem definition a plain spell id stands for: a rank 1 id directly, any other rank through the spell's name. Cached by id once
-- the name is known (a spell that is not a totem is remembered as such; an id with no name yet is not).
local ID_CACHE = {}
local function DefOf(id)
    local def = BY_ID[id]
    if def then return def end
    local cached = ID_CACHE[id]
    if cached == nil then
        local name = SpellName(id)
        if name == nil then return nil end      -- the client has no name for it (yet): ask again next time, remember nothing
        cached = BY_NAME[name] or false
        ID_CACHE[id] = cached
    end
    return cached or nil
end

local function Stamp(st, def, id, now, y, x, inst)
    st.stampAt = now
    st.far = false
    st.posY, st.posX, st.posInst = y, x, inst
    if def then
        st.name, st.spellID, st.icon = def.name, id, SpellIcon(id)
        st.start, st.duration, st.expires, st.source = now, def.dur, now + def.dur, "cast"
        st.range = def.range
    else                                        -- a set drop whose totem is not knowable here
        st.name, st.spellID, st.icon = nil, nil, nil
        st.start, st.duration, st.expires, st.source = nil, nil, nil, nil
        st.range = nil
    end
end

-- The multi-cast page: C_ActionBar.GetMultiCastBarIndex, else the older global. nil when neither answers a plain whole number.
local function MultiCastBar()
    local api = type(C_ActionBar) == "table" and C_ActionBar.GetMultiCastBarIndex or GetMultiCastBarIndex
    if type(api) ~= "function" then return nil end
    local ok, bar = pcall(api)
    bar = ok and PlainNum(bar) or nil
    if bar and bar >= 1 and floor(bar) == bar then return bar end
    return nil
end

-- Does a set's slot (Fire 1, Earth 2, Water 3, Air 4) hold a spell: true and the spell id (nil when the action is not a plain
-- spell), false (plainly empty) or nil (HasAction is missing, raised or answered a secret). The action id of the slot is
-- (bar - 1) * 12 + (set - 1) * 4 + slot; both HasAction and GetActionInfo are plain.
local function SetSlotHolds(bar, set, slot)
    if type(HasAction) ~= "function" or type(set) ~= "number" then return nil end
    local id = (bar - 1) * 12 + (set - 1) * 4 + slot
    local ok, has = pcall(HasAction, id)
    if not ok or Secret(has) then return nil end
    if not has then return false end
    local spell
    if type(GetActionInfo) == "function" then
        local okInfo, kind, sid = pcall(GetActionInfo, id)
        if okInfo and not Secret(kind) and kind == "spell" then spell = PlainNum(sid) end
    end
    return true, spell
end

local function OnCast(id)
    id = PlainNum(id)
    if id == nil then return end
    local def = DefOf(id)
    if not def then return end
    local now = GetTime()
    if def.projection then
        -- the totems move to a spot this addon cannot see: FAR is off until the next drop
        for slot = 1, NSLOTS do
            local st = S[slot]
            st.posY, st.posX, st.posInst = nil, nil, nil
            if st.far then
                st.far = false
                Notify(slot)
            end
        end
        return
    end
    local y, x, inst = ReadPosition()
    local force
    if def.set then
        -- The set casts the totems its four multi-cast slots hold. Where that is readable, every element whose slot holds a spell is
        -- stamped again (numbers from the static table through that spell, and the position of this drop) whether or not it was up:
        -- the set replaces a standing totem of the element. An element with an empty slot is left as it is. Where it is not readable
        -- (no bar index, no HasAction, a secret answer) a totem already standing keeps its name, numbers and drop position until
        -- PLAYER_TOTEM_UPDATE says otherwise and only an empty slot is stamped (with the position the set dropped it at).
        local bar = MultiCastBar()
        for slot = 1, NSLOTS do
            local held, spell
            if bar then held, spell = SetSlotHolds(bar, def.index, slot) end
            if held == true then
                local totem = spell and DefOf(spell) or nil
                if totem and (totem.set or totem.projection or totem.slot ~= slot) then totem = nil end
                Stamp(S[slot], totem, totem and spell or nil, now, y, x, inst)
            elseif held == nil and not S[slot].up then
                Stamp(S[slot], nil, nil, now, y, x, inst)
            end
        end
        force = true
    else
        Stamp(S[def.slot], def, id, now, y, x, inst)
        force = def.slot
    end
    -- forced: the stamp rewrote the record before the read, so a plain before / after compare would see no change
    RefreshAll(now, force)
end

-------------------------------------------------------------------------------
-- Public reads
-------------------------------------------------------------------------------

function T.Get(slot) return S[slot] end

function T.IsUp(slot)
    local st = S[slot]
    return st ~= nil and st.up
end

function T.DurationObject(slot)
    local st = S[slot]
    return st and st.up and st.obj or nil
end

-- Plain seconds left, or nil when the slot is down or no number is knowable. Never below 0.
function T.Remaining(slot, now)
    local st = S[slot]
    if not (st and st.up and st.expires) then return nil end
    local rem = st.expires - (now or GetTime())
    if rem < 0 then rem = 0 end
    return rem
end

function T.Duration(slot)
    local st = S[slot]
    return st and st.up and st.duration or nil
end

-- 1 for a full totem down to 0.
function T.Fraction(slot, now)
    local rem, dur = T.Remaining(slot, now), T.Duration(slot)
    if rem == nil or dur == nil or dur <= 0 then return nil end
    local f = rem / dur
    if f > 1 then f = 1 end
    return f
end

-- The block count of the pole: ceil(remaining / duration * 8), 1 to 8 while the totem stands (the last block stays lit until the
-- totem is gone). nil when down or when no number is knowable.
function T.Blocks(slot, now)
    local f = T.Fraction(slot, now)
    if f == nil then return nil end
    local n = ceil(f * BLOCKS)
    if n < 1 then n = 1 end
    if n > BLOCKS then n = BLOCKS end
    return n
end

function T.IsFar(slot)
    local st = S[slot]
    return st ~= nil and st.up and st.far
end

function T.IsUnlocked(slot)
    local st = S[slot]
    return st ~= nil and st.unlocked
end

function T.AnyUp()
    for slot = 1, NSLOTS do if S[slot].up then return true end end
    return false
end

function T.Refresh()
    RefreshAll(GetTime())
    T.RefreshUnlocked()
end

-- Called by whoever draws, from its OnUpdate and only while a totem stands: asks a slot again once its expected end has passed
-- (an end that is only an estimate must not keep a gone totem up), and re-reads the position for FAR. Both are throttled, so a
-- frame that has nothing due does arithmetic only.
function T.Tick(now)
    for slot = 1, NSLOTS do
        local st = S[slot]
        if st.up then
            if st.expires ~= nil and now > st.expires + EXPIRY_SLACK and now - st.checkAt >= RECHECK then
                st.checkAt = now
                RefreshSlot(slot, now)
            end
            if st.up and st.posY ~= nil and now - st.farAt >= FAR_EVERY then
                st.farAt = now
                if EvalFar(st) then Notify(slot) end
            end
        end
    end
end

-------------------------------------------------------------------------------
-- Events
-------------------------------------------------------------------------------

-- The localized names of the totems and sets (so a higher rank or a localized client still finds its definition), and Projection's
-- id and localized name from the spell book. Cheap and idempotent; run at Start and again when the book changes (Projection is
-- learned at level 22).
local function ResolveNames()
    for _, def in ipairs(DEFS) do
        local name = SpellName(def.id)
        if name and not BY_NAME[name] then BY_NAME[name] = def end
    end
    for id, english in pairs(SET_IDS) do
        local name = SpellName(id)
        if name and not BY_NAME[name] then BY_NAME[name] = SET_DEFS[id] end
        NAME_ID[english] = id
    end
    for _, id in ipairs(PROJECTION_IDS) do
        local name = SpellName(id)
        if name and not BY_NAME[name] then BY_NAME[name] = PROJECTION_DEF end
    end
    local info = C_Spell and C_Spell.GetSpellInfo
    if type(info) == "function" then
        local ok, rec = pcall(info, PROJECTION)
        if ok and type(rec) == "table" and not Secret(rec) then
            local name, id = PlainStr(rec.name), PlainNum(rec.spellID)
            if name and not BY_NAME[name] then BY_NAME[name] = PROJECTION_DEF end
            if id and not BY_ID[id] then BY_ID[id] = PROJECTION_DEF end
        end
    end
end

local events

local function OnEvent(_, event, arg1, arg2, arg3)
    if event == "UNIT_SPELLCAST_SUCCEEDED" then
        if not Secret(arg1) and arg1 == "player" then
            local ok, err = pcall(OnCast, arg3)
            if not ok then LogOnce("cast", err) end
        end
    elseif event == "PLAYER_TOTEM_UPDATE" then
        local slot = PlainNum(arg1)
        local ok, err
        if slot and slot >= 1 and slot <= NSLOTS and floor(slot) == slot then
            ok, err = pcall(RefreshSlot, slot, GetTime())
        else
            ok, err = pcall(RefreshAll, GetTime())
        end
        if not ok then LogOnce("update", err) end
    elseif event == "SPELLS_CHANGED" or event == "PLAYER_LEVEL_UP" or event == "LEARNED_SPELL_IN_SKILL_LINE" then
        if event ~= "PLAYER_LEVEL_UP" then pcall(ResolveNames) end
        local ok, err = pcall(T.RefreshUnlocked)
        if not ok then LogOnce("unlocked", err) end
    else
        -- PLAYER_REGEN_DISABLED (still plain: numbers are taken just before the fight), PLAYER_REGEN_ENABLED (plain again:
        -- the estimates are replaced), PLAYER_ENTERING_WORLD
        local ok, err = pcall(T.Refresh)
        if not ok then LogOnce("refresh", err) end
    end
end

-- Idempotent. Registers the listeners that stay on whether or not anything is drawing.
function T.Start()
    if started then return end
    started = true
    events = CreateFrame("Frame")
    events:SetScript("OnEvent", OnEvent)
    -- a client without an event refuses it: FrameHelpers skips it quietly, it is not an error
    FS.FrameHelpers.RegisterEvents(events, { "PLAYER_TOTEM_UPDATE", "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED",
        "PLAYER_ENTERING_WORLD", "SPELLS_CHANGED", "PLAYER_LEVEL_UP", "LEARNED_SPELL_IN_SKILL_LINE" })
    if not FS.FrameHelpers.RegisterEvent(events, "UNIT_SPELLCAST_SUCCEEDED", "player") then
        FS.FrameHelpers.RegisterEvent(events, "UNIT_SPELLCAST_SUCCEEDED")
    end
    ResolveNames()
    pcall(T.Refresh)
end

function T.IsStarted() return started end

-- A Shaman starts it at login; GunsightShaman.lua also calls Start when it builds (Start is idempotent).
local boot = CreateFrame("Frame")
boot:RegisterEvent("PLAYER_LOGIN")
boot:SetScript("OnEvent", function(self)
    self:UnregisterEvent("PLAYER_LOGIN")
    local ok, _, token = pcall(UnitClass, "player")
    if ok and not Secret(token) and token == "SHAMAN" then T.Start() end
end)
