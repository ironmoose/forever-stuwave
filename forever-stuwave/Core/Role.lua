-- Forever STUwave: the player role (tank, healer, melee, ranged) and its per character store
-- FS.Role answers "which role am I playing" for the Roles page, the nameplate threat view (PlateThreat.lua) and the party
-- frames. The answer is Auto unless the player picked one by hand:
--
--   * Auto, in order: the assigned group role when one is set (a damage role is told melee from ranged by the talent tree,
--     then the class); else the talent tree with the most points (FS.CharBackdrop.TreePoints, ties to the leftmost tree)
--     through TREES; else the class default. With no FS.CharBackdrop (skins off) or points that cannot be read, the class
--     decides and the ? tip says so (Role.Why).
--   * TREES lists each class's three trees left to right, in the order and under the names of the client's own talent art
--     (FS.TalentBgArt.sheets, which role-harness.py compares); the role of a tree is what its spec plays.
--   * The pick is saved per character in ForeverSTUwaveCharDB.role, and copied account wide by GUID in
--     ForeverSTUwaveDB.roleByChar, because this client does not restore per character saved variables (the same reason
--     FS.Config lives in ForeverSTUwaveDB). It is never part of a profile, so a profile string does not carry it.
--   * The group role and the talent points are read when their events say they moved, never per call: Role.Current is a
--     cached answer. OnChange listeners hear every change of role or of where the role came from.
--   * The role settings (SETTINGS) are plain profile keys. A setting acts only while its role is the one in use: ask
--     Role.Active / Role.Value / Role.Disabled instead of reading the key, so the settings of the roles you are not
--     playing keep their values and do nothing.

local _, FS = ...

local Role = FS.Role or {}
FS.Role = Role

Role.NAMES = { "tank", "healer", "melee", "ranged" }
Role.PICKS = { "auto", "tank", "healer", "melee", "ranged" }
Role.TEXT = { tank = "Tank", healer = "Healer", melee = "Melee", ranged = "Ranged" }
Role.SOURCE_TEXT = { group = "from group", talents = "from talents", class = "from class", pick = "set by hand" }

-- Each class's trees left to right: `name` is the tree's key in the client's talent art, `text` its name, `role` what it plays.
-- A Druid's Feral tree reads as melee; a Druid who tanks is told apart by the group role.
Role.TREES = {
    WARRIOR = { { name = "arms", text = "Arms", role = "melee" }, { name = "fury", text = "Fury", role = "melee" },
        { name = "protection", text = "Protection", role = "tank" } },
    PALADIN = { { name = "holy", text = "Holy", role = "healer" }, { name = "protection", text = "Protection", role = "tank" },
        { name = "retribution", text = "Retribution", role = "melee" } },
    HUNTER = { { name = "beastmastery", text = "Beast Mastery", role = "ranged" },
        { name = "marksmanship", text = "Marksmanship", role = "ranged" }, { name = "survival", text = "Survival", role = "ranged" } },
    ROGUE = { { name = "assassination", text = "Assassination", role = "melee" }, { name = "combat", text = "Combat", role = "melee" },
        { name = "subtlety", text = "Subtlety", role = "melee" } },
    PRIEST = { { name = "discipline", text = "Discipline", role = "healer" }, { name = "holy", text = "Holy", role = "healer" },
        { name = "shadow", text = "Shadow", role = "ranged" } },
    SHAMAN = { { name = "elemental", text = "Elemental", role = "ranged" }, { name = "enhancement", text = "Enhancement", role = "melee" },
        { name = "restoration", text = "Restoration", role = "healer" } },
    MAGE = { { name = "arcane", text = "Arcane", role = "ranged" }, { name = "fire", text = "Fire", role = "ranged" },
        { name = "frost", text = "Frost", role = "ranged" } },
    WARLOCK = { { name = "affliction", text = "Affliction", role = "ranged" }, { name = "demonology", text = "Demonology", role = "ranged" },
        { name = "destruction", text = "Destruction", role = "ranged" } },
    DRUID = { { name = "balance", text = "Balance", role = "ranged" }, { name = "feral", text = "Feral", role = "melee" },
        { name = "restoration", text = "Restoration", role = "healer" } },
}

-- What a class plays with no talent points to go by (the first nine levels, or points that cannot be read).
Role.CLASS_ROLE = {
    WARRIOR = "melee", PALADIN = "melee", HUNTER = "ranged", ROGUE = "melee", PRIEST = "ranged",
    SHAMAN = "melee", MAGE = "ranged", WARLOCK = "ranged", DRUID = "ranged",
}
local FALLBACK_ROLE = "melee"

-- Group roles the client assigns, as the roles they mean. DAMAGER does not say melee or ranged.
local GROUP_ROLES = { TANK = "tank", HEALER = "healer", DAMAGER = "damage" }

-------------------------------------------------------------------------------
-- Settings: the keys of the Roles page, each tied to the one role it acts for
-------------------------------------------------------------------------------

local SWITCH, CHOICE, SLIDER = "switch", "choice", "slider"
local DEFS = {
    { "tank.aggro", "tank", SWITCH, true },
    { "tank.threat", "tank", CHOICE, "off",
        options = { { value = "off", text = "Off" }, { value = "pct", text = "Aggro %" }, { value = "lead", text = "Lead" } } },
    { "tank.lost", "tank", SWITCH, true },
    { "tank.lost.snd", "tank", SWITCH, true },
    { "heal.incoming", "healer", SWITCH, true },
    { "heal.range", "healer", SWITCH, true },
    { "heal.dispel", "healer", SWITCH, true },
    { "heal.hp", "healer", CHOICE, "missing",
        options = { { value = "none", text = "None" }, { value = "percent", text = "Percent" }, { value = "missing", text = "Missing" } } },
    { "heal.aggro", "healer", SWITCH, true },
    { "heal.aggro.snd", "healer", SWITCH, true },
    { "melee.warn", "melee", SWITCH, true },
    { "melee.pct", "melee", SLIDER, 90, min = 70, max = 100, step = 5 },
    { "melee.aggro", "melee", SWITCH, true },
    { "melee.range", "melee", SWITCH, true },
    { "ranged.warn", "ranged", SWITCH, true },
    { "ranged.pct", "ranged", SLIDER, 90, min = 70, max = 100, step = 5 },
    { "ranged.aggro", "ranged", SWITCH, true },
    { "ranged.range", "ranged", SWITCH, true },
}

Role.SETTINGS = {}
Role.KEYS = {}
for _, def in ipairs(DEFS) do
    local s = { key = def[1], role = def[2], kind = def[3], default = def[4], options = def.options,
        min = def.min, max = def.max, step = def.step }
    Role.SETTINGS[s.key] = s
    Role.KEYS[#Role.KEYS + 1] = s.key
    if FS.Config and FS.Config.RegisterDefault then FS.Config.RegisterDefault(s.key, s.default) end
end

-- The value of a setting as stored, made clean: a bad value reads as the default, a number is held to its range and step.
function Role.Get(key)
    local s = Role.SETTINGS[key]
    if not s then return nil end
    local value = s.default
    if FS.Config and FS.Config.Get then
        local ok, got = pcall(FS.Config.Get, key)
        if ok then value = got end
    end
    if FS.IsSecret(value) then return s.default end
    if s.kind == SWITCH then
        if type(value) ~= "boolean" then return s.default end
        return value
    elseif s.kind == CHOICE then
        for _, option in ipairs(s.options) do
            if option.value == value then return value end
        end
        return s.default
    end
    if type(value) ~= "number" or value ~= value then return s.default end
    value = math.min(s.max, math.max(s.min, value))
    return s.min + math.floor((value - s.min) / s.step + 0.5) * s.step
end

-------------------------------------------------------------------------------
-- Reads: the class, the talent tree, the group role. Nothing here compares a value before FS.IsSecret has seen it.
-------------------------------------------------------------------------------

local function ClassToken()
    if type(UnitClass) ~= "function" then return nil end
    local ok, _, token = pcall(UnitClass, "player")
    if ok and not FS.IsSecret(token) and type(token) == "string" then return token end
    return nil
end

local function ClassRole()
    return Role.CLASS_ROLE[ClassToken() or ""] or FALLBACK_ROLE
end

-- The group role as one of tank, healer, damage; nil for none, unset, secret or unknown.
local function GroupRole()
    if type(UnitGroupRolesAssigned) ~= "function" then return nil end
    local ok, assigned = pcall(UnitGroupRolesAssigned, "player")
    if not ok or FS.IsSecret(assigned) or type(assigned) ~= "string" then return nil end
    return GROUP_ROLES[assigned]
end

-- The tree with the most points: { role, name, text } or nil. Points must be three plain numbers, none negative.
local function TreeRole()
    local backdrop = FS.CharBackdrop
    if type(backdrop) ~= "table" or type(backdrop.TreePoints) ~= "function" then return nil end
    local ok, points = pcall(backdrop.TreePoints)
    if not ok or FS.IsSecret(points) or type(points) ~= "table" then return nil end
    local best, top = 0, nil
    for i = 1, 3 do
        local n = points[i]
        if FS.IsSecret(n) or type(n) ~= "number" or n ~= n or n < 0 then return nil end
        if n > best then best, top = n, i end
    end
    local trees = Role.TREES[ClassToken() or ""]
    return top and trees and trees[top] or nil
end

-------------------------------------------------------------------------------
-- The pick, per character
-------------------------------------------------------------------------------

local pick, loaded = "auto", false

local function CleanPick(value)
    if FS.IsSecret(value) or type(value) ~= "string" then return nil end
    for _, name in ipairs(Role.PICKS) do
        if name == value then return value end
    end
    return nil
end

local function Guid()
    if type(UnitGUID) ~= "function" then return nil end
    local ok, guid = pcall(UnitGUID, "player")
    if ok and not FS.IsSecret(guid) and type(guid) == "string" and guid ~= "" then return guid end
    return nil
end

local function ConfigReadOnly()
    local config = FS.Config
    return config and type(config.IsReadOnly) == "function" and config.IsReadOnly() == true or false
end

-- ForeverSTUwaveDB.roleByChar: the account wide copy. Never creates or replaces the database itself.
local function AccountTable(create)
    local db = _G.ForeverSTUwaveDB
    if type(db) ~= "table" then return nil end
    if type(db.roleByChar) ~= "table" then
        if not create then return nil end
        db.roleByChar = {}
    end
    return db.roleByChar
end

local function Load()
    loaded = true
    local char = _G.ForeverSTUwaveCharDB
    local value = type(char) == "table" and CleanPick(char.role) or nil
    if not value then
        local account, guid = AccountTable(false), Guid()
        value = account and guid and CleanPick(account[guid]) or nil
    end
    pick = value or "auto"
end

-- Writes the pick to both stores. The account copy waits for a GUID and a profile that may be written.
local function Store()
    local stored = pick ~= "auto" and pick or nil
    if type(_G.ForeverSTUwaveCharDB) ~= "table" then _G.ForeverSTUwaveCharDB = {} end
    _G.ForeverSTUwaveCharDB.role = stored
    local guid = Guid()
    if guid and not ConfigReadOnly() then
        local account = AccountTable(stored ~= nil)
        if account then account[guid] = stored end
    end
end

function Role.Pick()
    if not loaded then Load() end
    return pick
end

-------------------------------------------------------------------------------
-- The answer in use: cached, recomputed by the events that move it
-------------------------------------------------------------------------------

local state = { role = nil, source = nil, detail = nil }
local cache = { ready = false, tree = nil, group = nil }
local listeners = {}

local function Resolve()
    local chosen = Role.Pick()
    if chosen ~= "auto" then return chosen, "pick", nil end
    local group, tree = cache.group, cache.tree
    if group == "tank" or group == "healer" then return group, "group", nil end
    if group == "damage" then
        if tree and (tree.role == "melee" or tree.role == "ranged") then return tree.role, "group", tree end
        local class = ClassRole()
        return class == "ranged" and "ranged" or "melee", "group", nil
    end
    if tree then return tree.role, "talents", tree end
    return ClassRole(), "class", nil
end

local function Notify(role, source, was)
    for _, fn in ipairs(listeners) do
        local ok, err = pcall(fn, role, source, was)
        if not ok and FS.Layout and FS.Layout.ForwardError then FS.Layout.ForwardError(err) end
    end
end

-- `what` is "tree", "group" or "all" to read those again first, or nil to only resolve from what was read.
local function Refresh(what)
    if what == "all" or what == "tree" or not cache.ready then cache.tree = TreeRole() end
    if what == "all" or what == "group" or not cache.ready then cache.group = GroupRole() end
    cache.ready = true
    local role, source, detail = Resolve()
    local was, wasSource = state.role, state.source
    state.role, state.source, state.detail = role, source, detail
    if was ~= nil and (role ~= was or source ~= wasSource) then Notify(role, source, was) end
end

-- The role in use and where it came from: "pick", "group", "talents" or "class".
function Role.Current()
    if not cache.ready then Refresh() end
    return state.role, state.source
end

-- fn(role, source, previousRole) after the role or its source changed.
function Role.OnChange(fn)
    if type(fn) ~= "function" then return false end
    listeners[#listeners + 1] = fn
    return true
end

-- A hand pick, or "auto". False for anything else. The role is worked out again and the listeners hear a change at once.
function Role.SetPick(value)
    local clean = CleanPick(value)
    if not clean then return false end
    if not loaded then Load() end
    pick = clean
    Store()
    Refresh()
    return true
end

-- "MELEE, FROM TALENTS" for the label of the pinned bar, or nil when a pick is in use.
function Role.Summary()
    local role, source = Role.Current()
    if source == "pick" then return nil end
    return (Role.TEXT[role] .. ", " .. Role.SOURCE_TEXT[source]):upper()
end

-- One sentence for the ? tip: why Auto chose what it chose.
function Role.Why()
    local role, source = Role.Current()
    local text = Role.TEXT[role]
    if source == "pick" then return "You picked " .. text .. " by hand." end
    if source == "group" then return "Your group role makes you " .. text .. "." end
    if source == "talents" then
        local tree = state.detail
        return "Most of your talent points are in " .. (tree and tree.text or "one tree") .. ", which plays " .. text .. "."
    end
    local class = ClassToken()
    local line = "No talent points could be read, so your class decides."
    if class then line = line .. " " .. class:sub(1, 1) .. class:sub(2):lower() .. " plays " .. text .. "." end
    return line
end

-- The settings that depend on the role in use. Active: the key belongs to the role in use. Value: its clean value then,
-- else nil. Disabled: a switch of the role in use that is off, the one question a feature asks before it draws.
function Role.Active(key)
    local s = Role.SETTINGS[key]
    return s ~= nil and s.role == (Role.Current()) or false
end

function Role.Value(key)
    if not Role.Active(key) then return nil end
    return Role.Get(key)
end

function Role.Disabled(key)
    local s = Role.SETTINGS[key]
    if not s or s.kind ~= SWITCH or not Role.Active(key) then return false end
    return Role.Get(key) == false
end

-------------------------------------------------------------------------------
-- The party frames follow a role change or a healer switch at once
-------------------------------------------------------------------------------

-- PartyFrames.lua repaints a row from its own event handler (rows[i].events), so running it with an event that repaints the
-- whole row shows a changed switch now instead of at the next health or aura event. Nothing of PartyFrames is changed.
local function RepaintParty()
    local party = FS.PartyFrames
    local rows = party and party.rows
    if type(rows) ~= "table" then return end
    for _, row in ipairs(rows) do
        local frame = type(row) == "table" and row.events
        local run = type(frame) == "table" and type(frame.GetScript) == "function" and frame:GetScript("OnEvent")
        if type(run) == "function" then pcall(run, frame, "PLAYER_REGEN_ENABLED") end
    end
end
Role.RepaintParty = RepaintParty
Role.OnChange(RepaintParty)
if FS.Config and FS.Config.OnChange then
    for _, key in ipairs({ "heal.incoming", "heal.range", "heal.dispel", "heal.hp" }) do FS.Config.OnChange(key, RepaintParty) end
end

-------------------------------------------------------------------------------
-- Events
-------------------------------------------------------------------------------

local TREE_EVENTS = { "PLAYER_TALENT_UPDATE", "CHARACTER_POINTS_CHANGED", "TRAIT_CONFIG_UPDATED", "ACTIVE_TALENT_GROUP_CHANGED",
    "PLAYER_SPECIALIZATION_CHANGED" }
local GROUP_EVENTS = { "GROUP_ROSTER_UPDATE", "PLAYER_ROLES_ASSIGNED" }
local WORLD_EVENT = "PLAYER_ENTERING_WORLD"

local function RegisterAll(frame)
    local helpers = FS.FrameHelpers
    local lists = { { WORLD_EVENT }, TREE_EVENTS, GROUP_EVENTS }
    for _, list in ipairs(lists) do
        if helpers and type(helpers.RegisterEvents) == "function" then
            helpers.RegisterEvents(frame, list)
        else
            for _, event in ipairs(list) do pcall(frame.RegisterEvent, frame, event) end
        end
    end
end

local function Is(list, event)
    for _, name in ipairs(list) do
        if name == event then return true end
    end
    return false
end

local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function(_, event)
    local ok, err = pcall(function()
        if event == "PLAYER_LOGIN" then
            Load()
            RegisterAll(events)
            cache.ready = false
            Refresh("all")
        elseif event == WORLD_EVENT then
            -- a GUID that was not readable at login is by now: copy the pick account wide
            if pick ~= "auto" then Store() end
            Refresh("all")
        elseif Is(TREE_EVENTS, event) then
            Refresh("tree")
        elseif Is(GROUP_EVENTS, event) then
            Refresh("group")
        end
    end)
    if not ok and FS.Layout and FS.Layout.ForwardError then FS.Layout.ForwardError(err) end
end)
