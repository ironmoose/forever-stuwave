-- Forever STUwave: the Mage food and water tab (ticket T4), on the class tab kit (ShapeshiftTab.lua)
--
-- Two secure spell buttons, Conjure Food then Conjure Water, always the highest rank. A button casts by the spell NAME, which
-- the client resolves to the highest rank the player knows at click time; its icon, tooltip and cooldown are the highest KNOWN
-- rank id (the last learned id of the rank list below), rebound out of combat whenever the spellbook changes. A button stands
-- only for a spell some rank of which is known, so a Mage under level 4 has no tab.
--
-- Forever spell ids (client data 16001, ranks in learning order) and the conjured item each rank makes:
--   Food:  587 (5349), 597 (1113), 990 (1114), 6129 (1487), 10144 (8075), 10145 (8076), 28612 (22895)
--   Water: 5504 (5350), 5505 (2288), 5506 (2136), 6127 (3772), 10138 (8077), 10139 (8078), 10140 (8079), 468766 (231778)
--
-- The count (its switch, on by default) is every rank's item carried, added together (C_Item.GetItemCount, plain values). An
-- unreadable answer shows nothing, 0 shows 0, and an empty stack does not dim the button (it is the one to click). The count
-- follows the bags in combat (text writes only).
--
-- Seat: a one row shoulder, the Mage's second (ClassShoulder.lua seats it 16 design px right of the portals tab, or first at
-- 36 when that tab does not stand). Loads after PortalsTab.lua.
-- UNVERIFIED in game: the item ids, and how the tab looks.

local _, FS = ...

local Kit = FS.ClassTabKit
if not Kit then return end

local SETTINGS = {
    conjure = { key = "tabs.mage.conjure", default = true, label = "Food and water tab" },
    conjureCount = { key = "tabs.mage.conjureCount", default = true, label = "Show how many you carry" },
}

-- name of the spell family (the secure attribute), ranks in learning order, the conjured items
local FAMILIES = {
    { key = "food", ranks = { 587, 597, 990, 6129, 10144, 10145, 28612 },
        items = { 5349, 1113, 1114, 1487, 8075, 8076, 22895 } },
    { key = "water", ranks = { 5504, 5505, 5506, 6127, 10138, 10139, 10140, 468766 },
        items = { 5350, 2288, 2136, 3772, 8077, 8078, 8079, 231778 } },
}

-- The highest known rank id of a family, or nil.
local function HighestKnown(family)
    for i = #family.ranks, 1, -1 do
        if Kit.Known(family.ranks[i]) then return family.ranks[i] end
    end
    return nil
end

-- The carried items of a family added up, or nil when any one of them cannot be read plainly.
local function Carried(family)
    local total = 0
    for _, item in ipairs(family.items) do
        local n = Kit.ItemCount(item)
        if n == nil then return nil end
        total = total + n
    end
    return total
end

local function Entries()
    local counts = Kit.Setting(SETTINGS.conjureCount)
    local list = {}
    for _, family in ipairs(FAMILIES) do
        local id = HighestKnown(family)
        if id then
            local name, icon = Kit.SpellInfo(id)
            if name then
                list[#list + 1] = { key = family.key, id = id, spell = name, icon = icon,
                    count = counts and Carried(family) or nil }
            end
        end
    end
    return list
end

local Tab = Kit.New({
    field = "ConjureTab", class = "MAGE", shoulder = "mageconjure", host = "FSConjureTab", prefix = "FSConjureButton",
    slots = #FAMILIES, rows = 1,
    settings = SETTINGS, master = "conjure", entries = Entries,
    liveEvents = { "BAG_UPDATE_DELAYED" },
    config = {
        title = "Food and water tab",
        tip = "New. Conjure Food and Conjure Water as two buttons, always your highest rank.",
        rows = { "conjure", "conjureCount" },
    },
})
Tab.FAMILIES = FAMILIES
