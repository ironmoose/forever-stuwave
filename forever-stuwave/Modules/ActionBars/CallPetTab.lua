-- Forever STUwave: the Hunter call pet tab (ticket T2), on the class tab kit (ShapeshiftTab.lua)
--
-- One secure button per tamed pet, so the player picks which one comes, then Revive Pet and Dismiss Pet. It shows only once the
-- client lists MORE THAN ONE callable pet: with none or one there is nothing to pick, so the shoulder does not stand.
--
-- WHAT THE CLIENT GIVES. The pet list is C_StableInfo.GetActivePetList (the retail shape: a list of { name, icon, slotID }), and
-- pet N in it is called by the Call Pet spell of that slot: Call Pet (883), then 83242 to 83245 for slots 2 to 5, the ids the
-- P1 probe lists (FSCheck CALL_PET_IDS). A pet whose slot spell is not learned (or has no name on this client) is left out,
-- so a client that teaches only Call Pet lists one pet and the tab stays hidden. Forever's client data (16001) has Call Pet and
-- no Call Pet 2 to 5, so this tab is expected to stay hidden there until it gains more pet slots; the feature check is the
-- point (the ticket allows it), and a Hunter sees nothing wrong. Every read is plain-guarded; a missing API, a secret or
-- throwing answer shows no tab.
--
-- The light is the pet that is out: UnitName("pet") against the listed name (plain strings only; an unreadable name keeps the
-- last light). Revive Pet (982) and Dismiss Pet (2641) are macro-free spell buttons after the pets, while their switch is on
-- and the spell is learned. A pet button casts its Call Pet spell by name; its tooltip is the pet's name over the spell's.
--
-- Seat: a one row shoulder right of the pet panel (ClassShoulder.lua seats a Hunter's shoulders after PetDock).
-- Loads after ShapeshiftTab.lua (the kit). UNVERIFIED in game: the pet list's fields, and whether a second pet is ever listed.

local _, FS = ...

local Kit = FS.ClassTabKit
if not Kit then return end

local MAX_PETS = 5
local CALL_PET = { 883, 83242, 83243, 83244, 83245 }
local REVIVE_PET, DISMISS_PET = 982, 2641

local SETTINGS = {
    pets = { key = "tabs.hunter.pets", default = true, label = "Call pet tab" },
    petsLit = { key = "tabs.hunter.petsLit", default = true, label = "Light the pet that is out" },
    petsExtra = { key = "tabs.hunter.petsExtra", default = true, label = "Add Revive Pet and Dismiss Pet" },
}

-- The pet list as { { name, icon, slot } }, in list order, plain values only; nil when the client has no such list or
-- answers badly.
local function ReadPets()
    local api = C_StableInfo and C_StableInfo.GetActivePetList
    if type(api) ~= "function" then return nil end
    local ok, list = pcall(api)
    if not ok or FS.IsSecret(list) or type(list) ~= "table" then return nil end
    local pets = {}
    for i = 1, math.min(#list, MAX_PETS) do
        local pet = list[i]
        if type(pet) == "table" and not FS.IsSecret(pet) then
            local name = Kit.Plain(pet.name, "string")
            if name and name ~= "" then
                local icon = Kit.Plain(pet.icon, "number") or Kit.Plain(pet.icon, "string")
                pets[#pets + 1] = { name = name, icon = icon, slot = Kit.Plain(pet.slotID, "number") or i }
            end
        end
    end
    return pets
end

-- The name of the pet that is out: a string, false when none is, nil when it cannot be told.
local function PetOut()
    if type(UnitName) ~= "function" then return nil end
    local ok, name = pcall(UnitName, "pet")
    if not ok or FS.IsSecret(name) then return nil end
    if name == nil then return false end
    return Kit.Plain(name, "string")
end

local function Entries()
    local pets = ReadPets()
    if not pets then return {} end
    local list = {}
    for _, pet in ipairs(pets) do
        local id = CALL_PET[pet.slot]
        if id and Kit.Known(id) then
            local spell, spellIcon = Kit.SpellInfo(id)
            if spell then
                list[#list + 1] = { key = "pet" .. pet.slot, cd = id, spell = spell, icon = pet.icon or spellIcon,
                    tipText = pet.name, tipLine = spell, petName = pet.name }
            end
        end
    end
    -- fewer than two callable pets: nothing to pick between
    if #list < 2 then return {} end
    if Kit.Setting(SETTINGS.petsLit) then
        local out = PetOut()
        for _, entry in ipairs(list) do
            if out == nil then entry.litUnknown = true else entry.lit = out ~= false and entry.petName == out end
        end
    end
    if Kit.Setting(SETTINGS.petsExtra) then
        for _, extra in ipairs({ { "revive", REVIVE_PET }, { "dismiss", DISMISS_PET } }) do
            if Kit.Known(extra[2]) then
                local name, icon = Kit.SpellInfo(extra[2])
                if name then list[#list + 1] = { key = extra[1], id = extra[2], spell = name, icon = icon } end
            end
        end
    end
    return list
end

local Tab = Kit.New({
    field = "CallPetTab", class = "HUNTER", shoulder = "hunter", host = "FSCallPetTab", prefix = "FSCallPetButton",
    slots = MAX_PETS + 2, rows = 1,
    settings = SETTINGS, master = "pets", entries = Entries,
    syncEvents = { "PET_STABLE_UPDATE", "PET_STABLE_CLOSED" },
    liveEvents = { "PET_BAR_UPDATE" },
    unitEvents = { { "UNIT_PET", "player" } },
    config = {
        title = "Call pet tab",
        tip = "New. One button per tamed pet, so you pick which one comes. It only shows once you have more than one pet.",
        rows = { "pets", "petsLit", "petsExtra" },
    },
})
Tab.CALL_PET = CALL_PET
