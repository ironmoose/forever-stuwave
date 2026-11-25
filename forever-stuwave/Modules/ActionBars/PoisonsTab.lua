-- Forever STUwave: the Rogue poisons tab (ticket T5), on the class tab kit (ShapeshiftTab.lua)
--
-- One secure macro button per poison family the Rogue knows or carries, in the order Instant, Deadly, Crippling,
-- Mind-numbing, Wound, then a Main hand button and (while a weapon is in it) an Off hand button. A poison button is
-- `/use item:<id>` of the highest rank carried (else the highest rank learned, dimmed), with the carried count on it. A
-- weapon button is `/use 16` or `/use 17`: click a poison, then the weapon to coat. The poison items and the recipe spell
-- ids (icon only) are the classic ones; the level 54 to 60 poisons Forever adds are not on the tab (questions file).
--
-- What is on a hand. GetWeaponEnchantInfo is believed only when it answers a plain true (this client answers false for an
-- imbue that is up, ShamanBuffs notes, live 2026-10-12): it gives the time and charges left. Anything else falls back to the
-- weapon's tooltip line ("Instant Poison VI (30 min)"), read out of combat only, on equipment and inventory changes and
-- every few seconds while the API cannot say; between reads the time counts down from the clock. A secret answer, an
-- unreadable tooltip or any answer in combat that is not a plain true is "unknown": the light stays as painted, no time is
-- shown and nothing pulses. Nothing is guessed.
--
-- The pulse (poisonsNudge): a hand KNOWN to hold no poison pulses until one lands or the switch goes off. The time and
-- charges (poisonsLeft) go on the weapon button: time bottom right, charges top right.
--
-- Seat: a one row shoulder (ClassShoulder.lua, key `rogue`), the Console's top edge. Loads after ConjureTab.lua.
-- UNVERIFIED in game: that a click on the weapon button after a poison applies it, what the weapon tooltip says on Forever,
-- and whether GetWeaponEnchantInfo reads plain in combat.

local _, FS = ...

local Kit = FS.ClassTabKit
if not Kit then return end

local IsSecret = FS.IsSecret
local Plain = Kit.Plain

local SETTINGS = {
    poisons = { key = "tabs.rogue.poisons", default = true, label = "Poisons tab" },
    poisonsLeft = {
        key = "tabs.rogue.poisonsLeft", default = true, label = "Show time and charges left",
        tip = "The time left, and the charges when the poison has them, on each weapon button.",
    },
    poisonsNudge = {
        key = "tabs.rogue.poisonsNudge", default = true, label = "Pulse when a weapon has no poison",
        tip = "A soft pulse on a weapon button while that weapon has no poison on it. It stops when you apply one.",
    },
}

-- Poison families in button order; ranks in learning order as { recipe spell id (icon), item id (what is used) }.
local FAMILIES = {
    { key = "instant", label = "Instant Poison", ranks = {
        { 8681, 6947 }, { 8687, 6949 }, { 8691, 6950 }, { 11341, 8926 }, { 11342, 8927 }, { 11343, 8928 } } },
    { key = "deadly", label = "Deadly Poison", ranks = {
        { 2835, 2892 }, { 2837, 2893 }, { 11357, 8984 }, { 11358, 8985 }, { 25347, 20844 } } },
    { key = "crippling", label = "Crippling Poison", ranks = { { 3420, 3775 }, { 3421, 3776 } } },
    { key = "mindnumbing", label = "Mind-numbing Poison", ranks = { { 5763, 5237 }, { 8694, 6951 }, { 11400, 9186 } } },
    { key = "wound", label = "Wound Poison", ranks = {
        { 13220, 10918 }, { 13228, 10920 }, { 13229, 10921 }, { 13230, 10922 } } },
}
local HANDS = {
    { key = "mh", slot = 16, label = "Main hand" },
    { key = "oh", slot = 17, label = "Off hand" },
}
local READ_EVERY = 10   -- seconds between tooltip reads while the API cannot say what is on a hand

local function Now()
    local ok, t = pcall(GetTime)
    return ok and Plain(t, "number") or 0
end

local function InCombat()
    return InCombatLockdown and InCombatLockdown() and true or false
end

-------------------------------------------------------------------------------
-- The weapons
-------------------------------------------------------------------------------

-- Item equip locations that are a weapon (a shield is INVTYPE_SHIELD, a held-in-off-hand frill INVTYPE_HOLDABLE).
local WEAPON_LOC = {
    INVTYPE_WEAPON = true, INVTYPE_WEAPONMAINHAND = true, INVTYPE_WEAPONOFFHAND = true, INVTYPE_2HWEAPON = true,
}
local weaponLoc = {}    -- item id -> true when it is a weapon, false when it is not

-- true when the item in this equipment slot is a weapon; false for empty, a shield, a frill or anything unreadable.
local function HandHoldsWeapon(slot)
    if type(GetInventoryItemID) ~= "function" then return false end
    local ok, itemId = pcall(GetInventoryItemID, "player", slot)
    itemId = ok and Plain(itemId, "number") or nil
    if not itemId then return false end
    local isWeapon = weaponLoc[itemId]
    if isWeapon == nil then
        local info = (C_Item and C_Item.GetItemInfoInstant) or _G.GetItemInfoInstant
        if type(info) ~= "function" then return false end
        local ok2, _, _, _, equipLoc = pcall(info, itemId)
        equipLoc = ok2 and Plain(equipLoc, "string") or nil
        if not equipLoc then return false end
        isWeapon = WEAPON_LOC[equipLoc] or false
        weaponLoc[itemId] = isWeapon
    end
    return isWeapon
end

local function HandIcon(slot)
    if type(GetInventoryItemTexture) ~= "function" then return nil end
    local ok, tex = pcall(GetInventoryItemTexture, "player", slot)
    if not ok or IsSecret(tex) then return nil end
    if type(tex) == "number" or type(tex) == "string" then return tex end
    return nil
end

-- The icon of an item, for a poison carried without its recipe; plain values only.
local function ItemIcon(item)
    local info = (C_Item and C_Item.GetItemInfoInstant) or _G.GetItemInfoInstant
    if type(info) ~= "function" then return nil end
    local ok, _, _, _, _, icon = pcall(info, item)
    if not ok or IsSecret(icon) then return nil end
    if type(icon) == "number" or type(icon) == "string" then return icon end
    return nil
end

-------------------------------------------------------------------------------
-- What is on a hand
-------------------------------------------------------------------------------

-- true, ms, charges when GetWeaponEnchantInfo answers a plain true for the slot, else nil. A false (or anything secret) is
-- not believed.
local function ApiRead(slot)
    if type(GetWeaponEnchantInfo) ~= "function" then return nil end
    local ok, hasMain, mainMs, mainCh, _, hasOff, offMs, offCh = pcall(GetWeaponEnchantInfo)
    if not ok then return nil end
    local has, ms, charges = hasMain, mainMs, mainCh
    if slot ~= 16 then has, ms, charges = hasOff, offMs, offCh end
    if Plain(has, "boolean") ~= true then return nil end
    return true, Plain(ms, "number"), Plain(charges, "number")
end

local function UnitSeconds(unit)
    unit = unit:lower()
    if unit:find("^s") then return 1 end
    if unit:find("^m") then return 60 end
    if unit:find("^h") then return 3600 end
    if unit:find("^d") then return 86400 end
    return nil
end

-- "Instant Poison VI (30 min) (45 charges)" -> "Instant Poison VI", 1800000, 45; nil for a line that is not one.
local function ParseLine(text)
    text = text:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")
    local name = text:match("^(.-)%s*%(")
    if not name or name == "" then return nil end
    local ms, charges
    for n, unit in text:gmatch("%((%d+)%s*([^%)%s]+)%)") do
        local count = tonumber(n)
        if unit:lower():find("^c") then
            charges = count
        else
            local secs = UnitSeconds(unit)
            if secs then ms = (ms or 0) + count * secs * 1000 end
        end
    end
    if not (ms or charges) then return nil end
    return name, ms, charges
end

-- "line", name, ms, charges | "none" | nil (unreadable) for one weapon slot's tooltip. Out of combat only (the caller).
local function ReadTooltip(slot)
    local api = C_TooltipInfo and C_TooltipInfo.GetInventoryItem
    if type(api) ~= "function" then return nil end
    local ok, data = pcall(api, "player", slot)
    if not ok or IsSecret(data) or type(data) ~= "table" then return nil end
    local lines = data.lines
    if IsSecret(lines) or type(lines) ~= "table" or #lines == 0 then return nil end
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
                local name, ms, charges = ParseLine(text)
                if name then return "line", name, ms, charges end
            end
        end
    end
    if sawSecret then return nil end
    return "none"
end

local reads, names = {}, {}     -- slot -> the last tooltip read { has, ms, charges, at }; slot -> the poison's name

local function RefreshHand(slot)
    if InCombat() then return end
    local kind, name, ms, charges = ReadTooltip(slot)
    if kind == "line" then
        reads[slot] = { has = true, ms = ms, charges = charges, at = Now() }
        names[slot] = name
    elseif kind == "none" then
        reads[slot] = { has = false, at = Now() }
        names[slot] = nil
    else
        reads[slot], names[slot] = nil, nil
    end
end

-- Both hands, or with `slow` only the ones the API cannot say anything about.
local function RefreshHands(slow)
    for _, hand in ipairs(HANDS) do
        if not (slow and ApiRead(hand.slot)) then RefreshHand(hand.slot) end
    end
end

-- has (true, false, or nil when it cannot be told), ms, charges, poison name for a hand. In combat only the API is asked.
local function HandState(slot)
    local has, ms, charges = ApiRead(slot)
    if has then return true, ms, charges, names[slot] end
    if InCombat() then return nil end
    local read = reads[slot]
    if not read then return nil end
    if not read.has then return false end
    local left = read.ms and math.max(read.ms - (Now() - read.at) * 1000, 1000) or nil
    return true, left, read.charges, names[slot]
end

local function TimeText(ms)
    if not ms then return nil end
    local secs = math.ceil(ms / 1000)
    if secs < 60 then return secs .. "s" end
    if secs < 3600 then return math.floor(secs / 60) .. "m" end
    return math.floor(secs / 3600) .. "h"
end

-------------------------------------------------------------------------------
-- Entries
-------------------------------------------------------------------------------

-- One entry per poison family known or carried; the rank is the highest carried, else the highest learned.
local function Poisons()
    local list = {}
    for _, family in ipairs(FAMILIES) do
        local counts, carried, learned = {}, nil, nil
        for i, rank in ipairs(family.ranks) do
            counts[i] = Kit.ItemCount(rank[2])
            if counts[i] and counts[i] > 0 then carried = i end
            if Kit.Known(rank[1]) then learned = i end
        end
        local pick = carried or learned
        if pick then
            local spellId, item = family.ranks[pick][1], family.ranks[pick][2]
            local _, icon = Kit.SpellInfo(spellId)
            local n = counts[pick]
            list[#list + 1] = { key = family.key, macro = "/use item:" .. item, icon = icon or ItemIcon(item), item = item,
                tipText = family.label, count = n, dim = n == 0 }
        end
    end
    return list
end

local function Entries()
    local list = Poisons()
    if #list == 0 then return {} end
    local left, nudge = Kit.Setting(SETTINGS.poisonsLeft), Kit.Setting(SETTINGS.poisonsNudge)
    for _, hand in ipairs(HANDS) do
        if HandHoldsWeapon(hand.slot) then
            local has, ms, charges, name = HandState(hand.slot)
            local entry = { key = hand.key, macro = "/use " .. hand.slot, icon = HandIcon(hand.slot), tipText = hand.label,
                tipLine = has and name or nil }
            if has == nil then entry.litUnknown = true else entry.lit = has end
            if has and left then
                entry.count = TimeText(ms)
                entry.top = charges and charges > 0 and tostring(charges) or nil
            end
            entry.nudge = has == false and nudge
            list[#list + 1] = entry
        end
    end
    return list
end

-- What the poison buttons are (their macros): when this changes the buttons are rewritten, not just repainted.
local lastSig = ""
local function Signature()
    local parts = {}
    for _, entry in ipairs(Poisons()) do parts[#parts + 1] = entry.macro end
    return table.concat(parts, ",")
end

local function OnEvent(Tab, event, ...)
    if event == "UNIT_INVENTORY_CHANGED" then
        RefreshHands()
    elseif event == "PLAYER_EQUIPMENT_CHANGED" then
        local slot = ...
        if slot == 16 or slot == 17 then
            reads[slot], names[slot] = nil, nil
            RefreshHand(slot)
        end
    elseif event == "BAG_UPDATE_DELAYED" then
        local sig = Signature()
        if sig ~= lastSig then
            lastSig = sig
            Tab.Relearn()
        end
    end
end

-- The clock: once a second the times are repainted, and out of combat the hands the API cannot read are asked again.
local function Post(Tab)
    RefreshHands()
    lastSig = Signature()
    local ticker = CreateFrame("Frame")
    local lastTick, lastRead, wasInCombat = 0, Now(), false
    ticker:SetScript("OnUpdate", function()
        local now = Now()
        if now - lastTick < 1 then return end
        lastTick = now
        if not Tab.Enabled() then return end
        if InCombat() then
            wasInCombat = true
        elseif wasInCombat or now - lastRead >= READ_EVERY then
            wasInCombat, lastRead = false, now
            RefreshHands(true)
        end
        Tab.Paint()
    end)
end

local Tab = Kit.New({
    field = "PoisonsTab", class = "ROGUE", shoulder = "rogue", host = "FSPoisonsTab", prefix = "FSPoisonsButton",
    slots = #FAMILIES + #HANDS, rows = 1,
    settings = SETTINGS, master = "poisons", entries = Entries,
    syncEvents = { "PLAYER_EQUIPMENT_CHANGED" },
    liveEvents = { "BAG_UPDATE_DELAYED" },
    unitEvents = { { "UNIT_INVENTORY_CHANGED", "player" } },
    onEvent = OnEvent, post = Post,
    config = {
        title = "Poisons tab",
        tip = "New. Your poisons as buttons. Click one, then pick the weapon to coat. Main hand and off hand show what is "
            .. "on them and how long is left.",
        rows = { "poisons", "poisonsLeft", "poisonsNudge" },
    },
})
Tab.FAMILIES = FAMILIES
