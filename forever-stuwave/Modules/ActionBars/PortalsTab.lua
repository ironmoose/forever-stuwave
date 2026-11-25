-- Forever STUwave: the Mage portals and teleports tab (ticket T3), on the class tab kit (ShapeshiftTab.lua)
--
-- A two row shoulder: Teleports on the top row, Portals on the bottom row, learned ones only, each button a secure spell
-- button on its spell's NAME (a click casts). The rows pack left, and a row that is empty or switched off leaves the other on
-- the bottom row, the one against the Console chassis (ClassShoulder rows are fixed per shoulder, so the block stays two rows
-- tall).
--
-- Forever spell ids (client data 16001, SpellReagents: each teleport takes a Rune of Teleportation, item 17031, each portal a
-- Rune of Portals, item 17032): the six city teleports 3561 Stormwind, 3562 Ironforge, 3565 Darnassus, 3567 Orgrimmar,
-- 3566 Thunder Bluff, 3563 Undercity, and Dalaran 1297659 (Forever has a Dalaran teleport and no Dalaran portal); the six city
-- portals 10059, 11416, 11419, 11417, 11420, 11418 in the same order. A Mage learns only her faction's.
--
-- The rune count (its switch, on by default) is the carried count of the row's rune (C_Item.GetItemCount, plain values only)
-- on every button of that row, so "7" on a teleport says seven casts left; a stack of 0 dims the row. An unreadable count
-- shows nothing and dims nothing. The count follows the bags in combat (text writes only).
--
-- Loads after CallPetTab.lua. UNVERIFIED in game: whether the carried count sees the reagent runes in the bags, and the look.

local _, FS = ...

local Kit = FS.ClassTabKit
if not Kit then return end

local RUNE_TELEPORT, RUNE_PORTAL = 17031, 17032

local SETTINGS = {
    travel = { key = "tabs.mage.travel", default = true, label = "Portals and teleports tab" },
    travelTele = { key = "tabs.mage.travelTele", default = true, label = "Teleports" },
    travelPortal = { key = "tabs.mage.travelPortal", default = true, label = "Portals" },
    travelRunes = {
        key = "tabs.mage.travelRunes", default = true, label = "Show rune count",
        tip = "How many Runes of Teleportation and Runes of Portals you carry.",
    },
}

-- Stormwind, Ironforge, Darnassus, Orgrimmar, Thunder Bluff, Undercity (then Dalaran for teleports)
local TELEPORTS = { 3561, 3562, 3565, 3567, 3566, 3563, 1297659 }
local PORTALS = { 10059, 11416, 11419, 11417, 11420, 11418 }

-- The learned spells of a list as { id, name, icon }, in list order.
local function Learned(ids)
    local out = {}
    for _, id in ipairs(ids) do
        if Kit.Known(id) then
            local name, icon = Kit.SpellInfo(id)
            if name then out[#out + 1] = { id = id, name = name, icon = icon } end
        end
    end
    return out
end

-- One row's entries on `row`, each wearing the row's rune count (nil when it is not to be shown or cannot be read).
local function RowEntries(list, row, prefix, count)
    local out = {}
    for col, spell in ipairs(list) do
        out[#out + 1] = { key = prefix .. spell.id, id = spell.id, spell = spell.name, icon = spell.icon, row = row, col = col,
            count = count, dim = count == 0 or nil }
    end
    return out
end

local function Entries()
    local tele = Kit.Setting(SETTINGS.travelTele) and Learned(TELEPORTS) or {}
    local portal = Kit.Setting(SETTINGS.travelPortal) and Learned(PORTALS) or {}
    local runes = Kit.Setting(SETTINGS.travelRunes)
    local teleCount = runes and Kit.ItemCount(RUNE_TELEPORT) or nil
    local portalCount = runes and Kit.ItemCount(RUNE_PORTAL) or nil
    -- two rows when both stand, else the one row against the chassis
    local teleRow = #portal > 0 and 1 or 2
    local list = RowEntries(tele, teleRow, "tele", teleCount)
    for _, entry in ipairs(RowEntries(portal, 2, "portal", portalCount)) do list[#list + 1] = entry end
    return list
end

local Tab = Kit.New({
    field = "PortalsTab", class = "MAGE", shoulder = "mage", host = "FSPortalsTab", prefix = "FSPortalsButton",
    slots = #TELEPORTS + #PORTALS, rows = 2,
    settings = SETTINGS, master = "travel", entries = Entries,
    liveEvents = { "BAG_UPDATE_DELAYED" },
    config = {
        title = "Portals and teleports tab",
        tip = "New. Teleports on the top row and portals on the bottom row, learned ones only.",
        rows = { "travel", "travelTele", "travelPortal", "travelRunes" },
    },
})
Tab.TELEPORTS, Tab.PORTALS = TELEPORTS, PORTALS
