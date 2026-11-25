-- Forever STUwave: the Warlock summon demon tab (ticket T6), on the class tab kit (ShapeshiftTab.lua)
--
-- One secure spell button per demon the Warlock can summon, in the order Imp, Voidwalker, Succubus, Felhunter, Felguard. A
-- button casts by the spell NAME, so a click summons that demon. The Succubus button is the Incubus when that is the one the
-- Warlock knows (the same pet line, Sayaad). Forever spell ids (client data 16001): Imp 688, Voidwalker 697, Succubus 712,
-- Incubus 713, Felhunter 691; the Felguard is a bracer rune engraving and its summon id is not certain, so the three
-- candidates (427733, 427748, 431754, all named Summon Felguard) are tried and then the spell is looked up by that name.
--
-- The light (demonsLit): the demon that is out. The pet must exist and be alive (UnitExists, UnitIsDead), and its creature
-- family names the demon. A pet that is none of the five lights nothing; an answer that is secret or throws keeps the light
-- as painted.
--
-- The Soul Shard count (demonsShards, item 6265): shown on every demon that costs a shard (all but the Imp) and dimmed at 0.
-- An unreadable count shows nothing and dims nothing. It follows the bags in combat (text writes only).
--
-- Seat: a one row shoulder right of the pet panel (ClassShoulder.lua, key `warlock`, the Hunter's seat). Loads after
-- PoisonsTab.lua. UNVERIFIED in game: the Felguard summon id, the family strings, and that the light follows a demon's death.

local _, FS = ...

local Kit = FS.ClassTabKit
if not Kit then return end

local Plain = Kit.Plain

local SETTINGS = {
    demons = { key = "tabs.warlock.demons", default = true, label = "Summon demon tab" },
    demonsLit = {
        key = "tabs.warlock.demonsLit", default = true, label = "Light the demon that is out",
        tip = "Rings the button of the demon you have out.",
    },
    demonsShards = {
        key = "tabs.warlock.demonsShards", default = true, label = "Show Soul Shard count",
        tip = "Your Soul Shards on every demon that costs one. The button dims when you have none.",
    },
}

-- Demons in button order: the summon spell ids that can be it (the first known wins), whether it costs a shard, the
-- creature family fragments (lower case) that say it is out, and for the Felguard the spell name to look up when no id fits.
local DEMONS = {
    { key = "imp", ids = { 688 }, cost = false, fragments = { "imp" } },
    { key = "voidwalker", ids = { 697 }, cost = true, fragments = { "voidwalker" } },
    { key = "succubus", ids = { 712, 713 }, cost = true, fragments = { "succubus", "incubus" } },
    { key = "felhunter", ids = { 691 }, cost = true, fragments = { "felhunter" } },
    { key = "felguard", ids = { 427733, 427748, 431754 }, cost = true, fragments = { "felguard" },
        lookup = "Summon Felguard" },
}
local SOUL_SHARD = 6265

-- The summon spell id the Warlock knows for a demon, or nil.
local function KnownId(demon)
    for _, id in ipairs(demon.ids) do
        if Kit.Known(id) then return id end
    end
    if demon.lookup and FS.FrameHelpers and FS.FrameHelpers.ResolveSpell then
        local id = FS.FrameHelpers.ResolveSpell(demon.lookup)
        if id and Kit.Known(id) then return id end
    end
    return nil
end

-- A plain value of `kind` from fn("pet"), or nil when the call throws, answers secret or answers another type. Written out
-- (not `ok and v or nil`) so a plain false stays false.
local function PetRead(fn, kind)
    if type(fn) ~= "function" then return nil end
    local ok, value = pcall(fn, "pet")
    if not ok then return nil end
    return Plain(value, kind)
end

-- The key of the demon that is out; false when no demon of ours is (no pet, a dead one, another kind); nil when the client
-- will not say, so the light is left as it was.
local function DemonOut()
    local exists = PetRead(UnitExists, "boolean")
    if exists == nil then return nil end
    if exists == false then return false end
    local dead = PetRead(UnitIsDead, "boolean")
    if dead == nil then return nil end
    if dead then return false end
    local family = PetRead(UnitCreatureFamily, "string")
    if not family then return nil end
    family = family:lower()
    for _, demon in ipairs(DEMONS) do
        for _, fragment in ipairs(demon.fragments) do
            if family:find(fragment, 1, true) then return demon.key end
        end
    end
    return false
end

local function Entries()
    local lit = Kit.Setting(SETTINGS.demonsLit)
    local shards = Kit.Setting(SETTINGS.demonsShards)
    local out, count
    if lit then out = DemonOut() end
    if shards then count = Kit.ItemCount(SOUL_SHARD) end
    local list = {}
    for _, demon in ipairs(DEMONS) do
        local id = KnownId(demon)
        if id then
            local name, icon = Kit.SpellInfo(id)
            if name then
                local entry = { key = demon.key, id = id, spell = name, icon = icon }
                if lit then
                    if out == nil then entry.litUnknown = true else entry.lit = out == demon.key end
                end
                if demon.cost and count then
                    entry.count = count
                    entry.dim = count == 0
                end
                list[#list + 1] = entry
            end
        end
    end
    return list
end

local Tab = Kit.New({
    field = "DemonTab", class = "WARLOCK", shoulder = "warlock", host = "FSDemonTab", prefix = "FSDemonButton",
    slots = #DEMONS, rows = 1,
    settings = SETTINGS, master = "demons", entries = Entries,
    liveEvents = { "BAG_UPDATE_DELAYED", "PET_BAR_UPDATE" },
    unitEvents = { { "UNIT_PET", "player" } },
    config = {
        title = "Summon demon tab",
        tip = "New. One button per demon you know: Imp, Voidwalker, Succubus, Felhunter, Felguard. Click one to summon it.",
        rows = { "demons", "demonsLit", "demonsShards" },
    },
})
Tab.DEMONS = DEMONS
