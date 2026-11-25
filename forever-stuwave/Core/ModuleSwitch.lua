-- Forever STUwave: module power switches
-- FS.ModuleSwitch: one on / off switch per part of the addon (Unit frames, Cast bars, Chat ...), kept account wide in
-- ForeverSTUwaveDB.modules ({ [key] = false } for a module that is off; on is stored as nothing). It is not a profile
-- setting: a module is built before the character's profile is known (Config.lua falls back to Default until PLAYER_LOGIN).
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

local addonName, FS = ...

local MS = FS.ModuleSwitch or {}
FS.ModuleSwitch = MS

local mods = {}           -- key -> { key, label, live, page, requires = { key, ... } }
local order = {}          -- the keys in registration order
local session = {}        -- key -> bool: the switch as this session loaded it (a live module's follows Set)
local built = {}          -- key -> true once the module called MarkBuilt
local queue = {}          -- WhenOn calls made before ADDON_LOADED: { key, fn }
local keyCallbacks = {}   -- key -> { fn(new, old, key) }
local anyCallbacks = {}   -- { fn(key, new, old) }
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

-- The account wide table of switches that are off, or nil when the saved settings hold none (or it is not a table).
local function Store()
    local db = _G.ForeverSTUwaveDB
    if type(db) ~= "table" then return nil end
    local store = db.modules
    if type(store) ~= "table" then return nil end
    return store
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

-- The switch as the next reload will see it: what the store holds now. Only the value false turns a module off, so a
-- damaged saved value leaves the module on.
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

-- True when a Set will be kept: the saved variables are in and Config did not put the settings in read-only mode.
function MS.IsWritable()
    if not loaded or type(_G.ForeverSTUwaveDB) ~= "table" then return false end
    local config = FS.Config
    if config and config.IsReadOnly and config.IsReadOnly() then return false end
    return true
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

-- Writes one switch. Returns true, or false and the reason. A normal module marks a reload pending (Pending); a live
-- module's session value follows. Setting the value it already has changes nothing and calls nothing.
function MS.Set(key, on)
    local m = mods[key]
    if not m then return false, "no such module" end
    if type(on) ~= "boolean" then return false, "a module is on or off" end
    if not MS.IsWritable() then return false, "settings are read-only" end
    local old = MS.Wanted(key)
    if old == on then return true end
    local db = _G.ForeverSTUwaveDB
    if type(db.modules) ~= "table" then db.modules = {} end
    if on then db.modules[key] = nil else db.modules[key] = false end
    if m.live then session[key] = on end
    local list = keyCallbacks[key]
    if list then
        for i = 1, #list do Call(list[i], on, old, key) end
    end
    for i = 1, #anyCallbacks do Call(anyCallbacks[i], key, on, old) end
    return true
end

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

-- Every switch back on. Returns how many were off. A switch this version does not know is left alone.
function MS.TurnAllOn()
    local count = 0
    for _, key in ipairs(order) do
        if not MS.Wanted(key) and MS.Set(key, true) then count = count + 1 end
    end
    return count
end
