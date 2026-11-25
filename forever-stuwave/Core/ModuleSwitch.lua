-- Forever STUwave: module power switches
-- FS.ModuleSwitch: one on / off switch per part of the addon (Unit frames, Cast bars, Chat ...), kept in the PROFILE
-- (profile.modules, { [key] = false } for a module that is off; on is stored as nothing; Config.ModuleStore hands over the
-- active profile's table). Config.lua resolves the character's profile at its own ADDON_LOADED, before this file reads it, so
-- the session loads the switches of the profile in use. A later profile change (switch, copy, reset, or the character's
-- profile resolving at PLAYER_LOGIN when its GUID was not readable earlier) is compared with what this session loaded: a
-- module that differs waits for a Reload UI (Pending) and OnProfileChange hears about it; a live module follows at once.
-- Loads after Config.lua and before every module, so a module can gate itself at file scope.
--
-- Gating a module (one call):
--   local MS = FS.ModuleSwitch
--   MS.WhenOn("m.cast", function() Build() MS.MarkBuilt("m.cast") end)   -- instead of Build() at file scope
-- or, inside an event handler that already runs after this addon loaded (PLAYER_LOGIN ...):
--   if not MS.On("m.cast") then return end
-- Needs another module? Add MS.Register({ key = "m.party", requires = { "m.uf" } }) once; it merges into the registration.
-- A live module (turns off at once, today only Nameplates) subscribes with MS.OnChange("m.np", function(on) ... end).
-- Do not read On() at file scope: before ADDON_LOADED the saved value is not known and every switch answers on.
--
-- Keys, labels and the config page each switch sits on come from the prototype's NAV (mockups/proto-src-2026-11-25).

local _, FS = ...
local addonName = (...)   -- this addon's folder name: the ADDON_LOADED event names it

local MS = FS.ModuleSwitch or {}
FS.ModuleSwitch = MS

local mods = {}           -- key -> { key, label, live, page, requires = { key, ... } }
local order = {}          -- the keys in registration order
local session = {}        -- key -> bool: the switch as this session loaded it (a live module's follows Set)
local built = {}          -- key -> true once the module called MarkBuilt
local queue = {}          -- WhenOn calls made before ADDON_LOADED: { key, fn }
local keyCallbacks = {}   -- key -> { fn(new, old, key) }
local anyCallbacks = {}   -- { fn(key, new, old) }
local profileCallbacks = {}   -- { fn(pendingCount, movedKeys) }
local loaded = false

local function Forward(err)
    local layout = FS.Layout
    if layout and layout.ForwardError then
        layout.ForwardError(err)
    elseif type(geterrorhandler) == "function" then
        geterrorhandler()(err)
    end
end

local function Call(fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok then Forward(err) end
end

-- The active profile's table of switches that are off, or nil while nothing may be written (before the saved settings are
-- in, read-only mode): every switch reads as on then.
local function Store()
    local config = FS.Config
    if not (config and config.ModuleStore) then return nil end
    return config.ModuleStore()
end

-------------------------------------------------------------------------------
-- Registration
-------------------------------------------------------------------------------

-- Register{ key, label, live, page, requires = { key, ... } }. Registering a key again changes only the fields given, so a
-- module can add its `requires` without repeating the label. `page` is the /fsconfig page the switch sits on.
function MS.Register(def)
    if type(def) ~= "table" or type(def.key) ~= "string" or def.key == "" then return false end
    local m = mods[def.key]
    if not m then
        m = { key = def.key, label = def.key, live = false, requires = {} }
        mods[def.key] = m
        order[#order + 1] = def.key
        if loaded then session[def.key] = MS.Wanted(def.key) end
    end
    if def.label ~= nil then m.label = tostring(def.label) end
    if def.live ~= nil then m.live = def.live == true end
    if def.page ~= nil then m.page = tostring(def.page) end
    if type(def.requires) == "table" then
        m.requires = {}
        for _, key in ipairs(def.requires) do
            if type(key) == "string" then m.requires[#m.requires + 1] = key end
        end
    end
    return true
end

-- The sixteen switches of the prototype, in its order. Only Nameplates turns off at once (ApplyPlatesSetting); every
-- other module builds at file scope or PLAYER_LOGIN and dims, reparents or unregisters Blizzard frames, which only a
-- reload undoes.
local DEFINITIONS = {
    { "m.uf", "Unit frames", "unit" }, { "m.party", "Party frames", "party" }, { "m.raid", "Raid frames", "raid" },
    { "m.pet", "Pet bar", "pet" }, { "m.cast", "Cast bars", "cast" }, { "m.np", "Nameplates", "plates", true },
    { "m.gs", "Gunsight HUD", "gunsight" }, { "m.ab", "Action bars", "ab" }, { "m.auras", "Buffs and debuffs", "auras" },
    { "m.class", "Addon tabs", "tabs" }, { "m.chat", "Chat", "chat" }, { "m.mini", "Minimap", "mini" },
    { "m.bags", "Bags", "bags" }, { "m.track", "Quest tracker", "track" }, { "m.data", "Data bar", "data" },
    { "m.skins", "Window skins", "skins" },
}
for _, d in ipairs(DEFINITIONS) do
    MS.Register({ key = d[1], label = d[2], page = d[3], live = d[4] == true })
end

function MS.Keys()
    local list = {}
    for i, key in ipairs(order) do list[i] = key end
    return list
end

function MS.Label(key) local m = mods[key]; return m and m.label or nil end
function MS.Page(key) local m = mods[key]; return m and m.page or nil end
function MS.IsLive(key) local m = mods[key]; return m ~= nil and m.live == true end

function MS.Requires(key)
    local list = {}
    local m = mods[key]
    if m then
        for i, k in ipairs(m.requires) do list[i] = k end
    end
    return list
end

-------------------------------------------------------------------------------
-- Reading
-------------------------------------------------------------------------------

function MS.Loaded() return loaded end

-- The switch as the next reload will see it: what the active profile holds now. Only the value false turns a module off, so
-- a damaged saved value leaves the module on.
function MS.Wanted(key)
    local store = Store()
    if store and store[key] == false then return false end
    return true
end

-- The switch as this session loaded it. A live module follows Set at once; every other module keeps this value until a
-- reload. Before ADDON_LOADED (and for a key that was never registered) it answers on.
function MS.On(key)
    local value = session[key]
    if value == nil then return true end
    return value
end

-- A change that waits for a reload: the module is not live and the store differs from what loaded.
function MS.Pending(key)
    local m = mods[key]
    return m ~= nil and not m.live and MS.Wanted(key) ~= MS.On(key)
end

function MS.PendingKeys()
    local list = {}
    for _, key in ipairs(order) do
        if MS.Pending(key) then list[#list + 1] = key end
    end
    return list
end

function MS.PendingCount()
    return #MS.PendingKeys()
end

-- { [key] = on } for every registered switch: what an export carries.
function MS.Snapshot()
    local snap = {}
    for _, key in ipairs(order) do snap[key] = MS.Wanted(key) end
    return snap
end

-- True when a Set will be kept: the saved variables are in and the active profile may be written (not read-only mode).
function MS.IsWritable()
    return loaded and Store() ~= nil
end

-------------------------------------------------------------------------------
-- The load gate
-------------------------------------------------------------------------------

-- Runs fn once at this addon's ADDON_LOADED (after the saved variables, before PLAYER_LOGIN) when the module is on. A call
-- made after that runs at once. A key nobody registered is reported and runs anyway, so a typo cannot turn a module off.
function MS.WhenOn(key, fn)
    if type(fn) ~= "function" then return false end
    if not mods[key] then Forward("ModuleSwitch.WhenOn: no module is registered as " .. tostring(key)) end
    if loaded then
        if MS.On(key) then Call(fn) end
    else
        queue[#queue + 1] = { key = key, fn = fn }
    end
    return true
end

function MS.MarkBuilt(key) built[key] = true end
function MS.Built(key) return built[key] == true end

local function Load()
    loaded = true
    -- the switches are the profile's: have Config read the saved profiles first, whichever loader runs first
    if FS.Config and FS.Config.EnsureLoaded then FS.Config.EnsureLoaded() end
    for _, key in ipairs(order) do session[key] = MS.Wanted(key) end
    local list = queue
    queue = {}
    for _, item in ipairs(list) do
        if MS.On(item.key) then Call(item.fn) end
    end
end

local loader = CreateFrame("Frame")
loader:RegisterEvent("ADDON_LOADED")
loader:SetScript("OnEvent", function(self, _, name)
    if name ~= addonName or loaded then return end
    self:UnregisterEvent("ADDON_LOADED")
    Load()
end)

-------------------------------------------------------------------------------
-- Writing
-------------------------------------------------------------------------------

-- fn(new, old, key), called after the store changed (a live module applies the change here).
function MS.OnChange(key, fn)
    if type(key) ~= "string" or type(fn) ~= "function" then return false end
    keyCallbacks[key] = keyCallbacks[key] or {}
    table.insert(keyCallbacks[key], fn)
    return true
end

-- fn(key, new, old): the config window repaints from this.
function MS.OnAnyChange(fn)
    if type(fn) ~= "function" then return false end
    anyCallbacks[#anyCallbacks + 1] = fn
    return true
end

-- Writes one switch into the active profile. Returns true, or false and the reason. A normal module marks a reload pending
-- (Pending); a live module's session value follows. Setting the value it already has changes nothing and calls nothing.
function MS.Set(key, on)
    local m = mods[key]
    if not m then return false, "no such module" end
    if type(on) ~= "boolean" then return false, "a module is on or off" end
    if not MS.IsWritable() then return false, "settings are read-only" end
    local old = MS.Wanted(key)
    if old == on then return true end
    local store = Store()
    if on then store[key] = nil else store[key] = false end
    if m.live then session[key] = on end
    local list = keyCallbacks[key]
    if list then
        for i = 1, #list do Call(list[i], on, old, key) end
    end
    for i = 1, #anyCallbacks do Call(anyCallbacks[i], key, on, old) end
    return true
end

-- fn(pendingCount, movedKeys), called once after the active profile changed (a switch, a copy, a reset, the character's
-- profile resolving at login): `movedKeys` are the modules whose switch differs between the profile that was in use and the
-- one in use now, `pendingCount` how many modules wait for a reload as a result (PendingCount: the profile's switches against
-- what this session loaded, so it also counts what an earlier change left waiting). The config window says so once from here.
function MS.OnProfileChange(fn)
    if type(fn) ~= "function" then return false end
    profileCallbacks[#profileCallbacks + 1] = fn
    return true
end

-- Config.OnProfileChange: the switches of the new profile are read now. A live module follows its new value at once (its
-- change callbacks apply it); every other module keeps what this session loaded and shows as Pending when they differ.
local function ProfileChanged(oldModules)
    if not loaded then return end
    local moved, changes = {}, {}
    for _, key in ipairs(order) do
        local old = not (type(oldModules) == "table" and oldModules[key] == false)
        local new = MS.Wanted(key)
        if old ~= new then
            moved[#moved + 1] = key
            changes[#changes + 1] = { key = key, new = new, old = old }
            if mods[key].live then session[key] = new end
        end
    end
    for _, change in ipairs(changes) do
        local list = keyCallbacks[change.key]
        if list then
            for i = 1, #list do Call(list[i], change.new, change.old, change.key) end
        end
        for i = 1, #anyCallbacks do Call(anyCallbacks[i], change.key, change.new, change.old) end
    end
    local pending = MS.PendingCount()
    for i = 1, #profileCallbacks do Call(profileCallbacks[i], pending, moved) end
end
if FS.Config and FS.Config.OnProfileChange then FS.Config.OnProfileChange(ProfileChanged) end

-- The modules that are on and need `key`, directly or through another module, in registration order.
function MS.Dependents(key)
    local found, list = { [key] = true }, {}
    local grew = true
    while grew do
        grew = false
        for _, k in ipairs(order) do
            if not found[k] and MS.Wanted(k) then
                for _, need in ipairs(mods[k].requires) do
                    if found[need] then
                        found[k] = true
                        grew = true
                        break
                    end
                end
            end
        end
    end
    for _, k in ipairs(order) do
        if k ~= key and found[k] then list[#list + 1] = k end
    end
    return list
end

-- Turning a module on first turns on the modules it requires (through theirs too); turning it off first turns off the
-- modules that need it. Returns the keys that changed, in the order they were written, or nil and the reason.
function MS.SetWithDeps(key, on)
    if not mods[key] then return nil, "no such module" end
    if not MS.IsWritable() then return nil, "settings are read-only" end
    local changed = {}
    local function put(k, value)
        if MS.Wanted(k) ~= value and MS.Set(k, value) then changed[#changed + 1] = k end
    end
    if on then
        local seen = {}
        local function need(k)
            if seen[k] then return end
            seen[k] = true
            for _, r in ipairs(MS.Requires(k)) do
                if mods[r] then need(r) end
            end
            put(k, true)
        end
        need(key)
    else
        for _, k in ipairs(MS.Dependents(key)) do put(k, false) end
        put(key, false)
    end
    return changed
end

-- Every switch of the active profile back on. Returns how many were off. A switch this version does not know is left alone.
function MS.TurnAllOn()
    local count = 0
    for _, key in ipairs(order) do
        if not MS.Wanted(key) and MS.Set(key, true) then count = count + 1 end
    end
    return count
end
