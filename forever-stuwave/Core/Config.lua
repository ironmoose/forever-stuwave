-- Forever STUwave: Config
-- FS.Config: account-wide settings with named profiles, kept in ForeverSTUwaveDB because
-- per-character SavedVariables do not restore on this client. Each character is keyed by its
-- GUID (names carry surnames here) and the active profile's layout table is Layout's store.
-- Loads after Layout.lua; consumers register defaults at file scope and read with Get.

local addonName, FS = ...

local Config = FS.Config or {}
FS.Config = Config

-------------------------------------------------------------------------------
-- Schema
--
-- ForeverSTUwaveDB.profiles       = { [name] = { settings = {}, layout = { v = 1, frames = {} } } }
-- ForeverSTUwaveDB.profileKeys    = { [guid] = name }
-- ForeverSTUwaveDB.profileLabels  = { [guid] = "Name-Realm" }, for display only
-- ForeverSTUwaveDB.profilesVersion = 1
-------------------------------------------------------------------------------

local PROFILES_VERSION = 1
local DEFAULT_NAME = "Default"
local NAME_MAX = 32
local LABEL_MAX = 64

Config.DEFAULT_PROFILE = DEFAULT_NAME
Config.NAME_MAX = NAME_MAX

local defaults = {}
local keyCallbacks = {}
local anyCallbacks = {}

-- db is the saved table once it is loaded and writable; nil before ADDON_LOADED and in
-- read-only mode, where every read answers from `detached` (defaults only) and every write is refused.
local db = nil
local loaded = false
local readOnly = false
local warned = false
local detached = nil

local activeName = DEFAULT_NAME
local activeGuid = nil

local function NewProfileTable()
    return { settings = {}, layout = { v = 1, frames = {} } }
end

local function DeepCopy(value, seen)
    if type(value) ~= "table" then return value end
    seen = seen or {}
    if seen[value] then return seen[value] end
    local copy = {}
    seen[value] = copy
    for k, v in pairs(value) do copy[k] = DeepCopy(v, seen) end
    return copy
end

local function ActiveTable()
    if db then
        local profile = db.profiles[activeName]
        if profile then return profile end
    end
    detached = detached or NewProfileTable()
    return detached
end

-- The active profile when writes are allowed, else nil.
local function Writable()
    if db and not readOnly then return ActiveTable() end
end

local function Warn(text)
    if warned then return end
    warned = true
    print(("|cff22e0ffstuwave://config|r  %s"):format(text))
end

-------------------------------------------------------------------------------
-- Callbacks
-------------------------------------------------------------------------------

local function Call(fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok then FS.Layout.ForwardError(err) end
end

local function Fire(key, new, old)
    local list = keyCallbacks[key]
    if list then
        for i = 1, #list do Call(list[i], new, old, key) end
    end
    for i = 1, #anyCallbacks do Call(anyCallbacks[i], key, new, old) end
end

local function Effective(settings, key)
    local value = settings[key]
    if value == nil then return defaults[key] end
    return value
end

-- Fires the callbacks of every key whose effective value differs between two settings tables.
local function FireDifferences(oldSettings, newSettings)
    local keys, list = {}, {}
    for _, source in ipairs({ defaults, oldSettings, newSettings }) do
        for key in pairs(source) do
            if type(key) == "string" and not keys[key] then
                keys[key] = true
                list[#list + 1] = key
            end
        end
    end
    table.sort(list)
    for _, key in ipairs(list) do
        local old, new = Effective(oldSettings, key), Effective(newSettings, key)
        if old ~= new then Fire(key, new, old) end
    end
end

-- Points Layout at the active profile's layout table (nil when nothing may be written).
local function BindLayout(reseat)
    local layout = FS.Layout
    if not (layout and layout.UseStore) then return end
    layout.UseStore(Writable() and ActiveTable().layout or nil)
    if reseat and layout.ReseatAll then layout.ReseatAll() end
end

-- Call after the active profile's contents or identity changed; `oldSettings` is the table it replaced.
local function Reapply(oldSettings)
    BindLayout(true)
    FireDifferences(oldSettings, ActiveTable().settings)
end

local function SwitchTo(name)
    local oldSettings = ActiveTable().settings
    activeName = name
    Reapply(oldSettings)
end

-------------------------------------------------------------------------------
-- Names
-------------------------------------------------------------------------------

local function CleanName(name)
    if type(name) ~= "string" then return nil, "the name must be text" end
    name = name:match("^%s*(.-)%s*$")
    if name == "" then return nil, "the name is empty" end
    local _, chars = name:gsub("[^\128-\191]", "")
    if chars > NAME_MAX then return nil, ("the name is longer than %d characters"):format(NAME_MAX) end
    if name:find("%c") or name:find("|", 1, true) then return nil, "the name has characters that are not allowed" end
    return name
end

local function NameTaken(name, except)
    local lowered = name:lower()
    for existing in pairs(db.profiles) do
        if existing ~= except and existing:lower() == lowered then return true end
    end
    return false
end

local function RemapKeys(from, to)
    for guid, name in pairs(db.profileKeys) do
        if name == from then db.profileKeys[guid] = to end
    end
end

-------------------------------------------------------------------------------
-- Loading
-------------------------------------------------------------------------------

local function Plain(value)
    local isSecret = _G.issecretvalue
    if isSecret and isSecret(value) then return nil end
    return value
end

local function PlayerGuid()
    if type(UnitGUID) ~= "function" then return nil end
    local ok, guid = pcall(UnitGUID, "player")
    guid = ok and Plain(guid) or nil
    if type(guid) == "string" and guid ~= "" then return guid end
end

local function PlayerLabel()
    local name = type(UnitName) == "function" and Plain(UnitName("player")) or nil
    if type(name) ~= "string" or name == "" then return nil end
    local realm
    if type(_G.GetNormalizedRealmName) == "function" then
        realm = Plain(_G.GetNormalizedRealmName())
    elseif type(GetRealmName) == "function" then
        realm = Plain(GetRealmName())
    end
    if type(realm) == "string" and realm ~= "" then name = name .. "-" .. realm end
    return name:sub(1, LABEL_MAX)
end

-- Repairs the saved tables in place without discarding anything that is still usable.
local function Normalize()
    db.profilesVersion = PROFILES_VERSION
    if type(db.profiles) ~= "table" then db.profiles = {} end
    for name, profile in pairs(db.profiles) do
        if type(name) ~= "string" or type(profile) ~= "table" then
            db.profiles[name] = nil
        else
            if type(profile.settings) ~= "table" then profile.settings = {} end
            if type(profile.layout) ~= "table" then profile.layout = { v = 1, frames = {} } end
        end
    end
    if type(db.profiles[DEFAULT_NAME]) ~= "table" then db.profiles[DEFAULT_NAME] = NewProfileTable() end
    if type(db.profileKeys) ~= "table" then db.profileKeys = {} end
    if type(db.profileLabels) ~= "table" then db.profileLabels = {} end
end

-- The pre-profile ForeverSTUwaveDB.layout becomes Default's layout, unless Default already
-- holds positions of its own or a layout this addon cannot read. In that case the old key stays
-- and is marked, so a later reset of Default never re-imports stale positions.
local function MigrateLayout()
    local old = db.layout
    if old == nil or db.layoutMigrated == true then return end
    if type(old) ~= "table" then
        db.layout = nil
        return
    end
    local default = db.profiles[DEFAULT_NAME]
    local version, frames = default.layout.v, default.layout.frames
    local readable = type(version) ~= "number" or version <= 1
    if readable and (type(frames) ~= "table" or next(frames) == nil) then
        default.layout = old
        db.layout = nil
    else
        db.layoutMigrated = true
    end
end

local function ResolveCharacter()
    local guid = PlayerGuid()
    if not guid then return nil end
    local name = db.profileKeys[guid]
    if type(name) ~= "string" or type(db.profiles[name]) ~= "table" then
        name = DEFAULT_NAME
        db.profileKeys[guid] = name
    end
    local label = PlayerLabel()
    if label then db.profileLabels[guid] = label end
    activeGuid = guid
    return name
end

local function Load()
    loaded = true
    local saved = ForeverSTUwaveDB
    if saved == nil then
        saved = {}
        ForeverSTUwaveDB = saved
    end
    if type(saved) ~= "table" then
        readOnly = true
        Warn("saved settings are unreadable; settings and profiles are read-only this session")
        BindLayout(false)
        return
    end
    local version = saved.profilesVersion
    if type(version) == "number" and version > PROFILES_VERSION then
        readOnly = true
        Warn(("saved profiles are version %s, newer than this addon (%d); settings and profiles are read-only this session")
            :format(tostring(version), PROFILES_VERSION))
        BindLayout(false)
        return
    end
    db = saved
    Normalize()
    MigrateLayout()
    activeName = ResolveCharacter() or DEFAULT_NAME
    BindLayout(false)
end

local loader = CreateFrame("Frame")
loader:RegisterEvent("ADDON_LOADED")
loader:RegisterEvent("PLAYER_LOGIN")
loader:SetScript("OnEvent", function(self, event, name)
    if event == "ADDON_LOADED" then
        if name ~= addonName or loaded then return end
        self:UnregisterEvent("ADDON_LOADED")
        Load()
    elseif loaded and db and not readOnly and not activeGuid then
        -- The GUID was not readable at ADDON_LOADED, so Default was in use meanwhile.
        local resolved = ResolveCharacter()
        if resolved and resolved ~= activeName then SwitchTo(resolved) end
    end
end)

-------------------------------------------------------------------------------
-- Settings
-------------------------------------------------------------------------------

function Config.RegisterDefault(key, value)
    if type(key) ~= "string" or key == "" then return end
    defaults[key] = value
end

function Config.Get(key)
    if type(key) ~= "string" then return nil end
    return Effective(ActiveTable().settings, key)
end

-- Stores the value in the active profile and fires callbacks when the effective value changed.
-- A value equal to the default (or nil) is stored as nothing so the default is not pinned.
-- Until the character's GUID resolves the active profile is Default, so earlier writes land there.
function Config.Set(key, value)
    if type(key) ~= "string" or key == "" then return false end
    local profile = Writable()
    if not profile then return false end
    local old = Effective(profile.settings, key)
    if value == defaults[key] then value = nil end
    profile.settings[key] = value
    local new = Effective(profile.settings, key)
    if old ~= new then Fire(key, new, old) end
    return true
end

-- fn(new, old, key)
function Config.OnChange(key, fn)
    if type(key) ~= "string" or type(fn) ~= "function" then return end
    keyCallbacks[key] = keyCallbacks[key] or {}
    table.insert(keyCallbacks[key], fn)
end

-- fn(key, new, old)
function Config.OnAnyChange(fn)
    if type(fn) ~= "function" then return end
    anyCallbacks[#anyCallbacks + 1] = fn
end

-------------------------------------------------------------------------------
-- Profiles
--
-- Every mutator returns true (plus the cleaned name where one is made) or false and a reason.
-------------------------------------------------------------------------------

function Config.IsReadOnly()
    return readOnly
end

function Config.ActiveProfile()
    return activeName
end

function Config.ListProfiles()
    local list = {}
    if db then
        for name in pairs(db.profiles) do
            if name ~= DEFAULT_NAME then list[#list + 1] = name end
        end
        table.sort(list, function(a, b)
            local la, lb = a:lower(), b:lower()
            if la ~= lb then return la < lb end
            return a < b
        end)
    end
    table.insert(list, 1, DEFAULT_NAME)
    return list
end

function Config.NewProfile(name, copyFrom)
    if not Writable() then return false, "settings are read-only" end
    local clean, err = CleanName(name)
    if not clean then return false, err end
    if NameTaken(clean) then return false, "a profile with that name exists" end
    local source
    if copyFrom ~= nil then
        source = type(copyFrom) == "string" and db.profiles[copyFrom] or nil
        if not source then return false, "the profile to copy does not exist" end
    end
    db.profiles[clean] = source and DeepCopy(source) or NewProfileTable()
    return true, clean
end

-- Replaces the active profile's settings and layout with a copy of `from`'s.
function Config.CopyProfile(from)
    local active = Writable()
    if not active then return false, "settings are read-only" end
    local source = type(from) == "string" and db.profiles[from] or nil
    if not source then return false, "the profile to copy does not exist" end
    if from == activeName then return false, "that is the active profile" end
    local oldSettings = active.settings
    local copy = DeepCopy(source)
    active.settings, active.layout = copy.settings, copy.layout
    Reapply(oldSettings)
    return true
end

function Config.RenameProfile(old, new)
    if not Writable() then return false, "settings are read-only" end
    if type(old) ~= "string" or not db.profiles[old] then return false, "no such profile" end
    if old == DEFAULT_NAME then return false, "the Default profile cannot be renamed" end
    local clean, err = CleanName(new)
    if not clean then return false, err end
    if clean == old then return true, clean end
    if NameTaken(clean, old) then return false, "a profile with that name exists" end
    db.profiles[clean], db.profiles[old] = db.profiles[old], nil
    RemapKeys(old, clean)
    if activeName == old then activeName = clean end
    return true, clean
end

function Config.DeleteProfile(name)
    if not Writable() then return false, "settings are read-only" end
    if type(name) ~= "string" or not db.profiles[name] then return false, "no such profile" end
    if name == DEFAULT_NAME then return false, "the Default profile cannot be deleted" end
    if name == activeName then return false, "the active profile cannot be deleted" end
    db.profiles[name] = nil
    RemapKeys(name, DEFAULT_NAME)
    return true
end

-- Returns the active profile to the registered defaults and an empty layout.
function Config.ResetProfile()
    local active = Writable()
    if not active then return false, "settings are read-only" end
    local oldSettings = active.settings
    active.settings, active.layout = {}, { v = 1, frames = {} }
    Reapply(oldSettings)
    return true
end

function Config.SetActiveProfile(name)
    if not Writable() then return false, "settings are read-only" end
    if type(name) ~= "string" or not db.profiles[name] then return false, "no such profile" end
    if not activeGuid then return false, "the character is not known yet" end
    if name == activeName then return true end
    db.profileKeys[activeGuid] = name
    SwitchTo(name)
    return true
end
