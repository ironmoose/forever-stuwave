-- Forever STUwave: Config page, Profiles
-- Active profile (the one in use, this character), Manage (new, copy, rename, delete, reset: each asks first where it
-- destroys), then Saved data. The Share section (profile export and import) and the Modules section (all modules back on)
-- come from their own tickets through CW.ExtendTab("profiles", "p", ...) and land before Saved data, which is built last.

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI
local I = CW.I
local Config = FS.Config

local function CharacterLabel()
    local db = _G.ForeverSTUwaveDB
    local guid
    if type(UnitGUID) == "function" then
        local ok, value = pcall(UnitGUID, "player")
        if ok and not (FS.IsSecret and FS.IsSecret(value)) then guid = value end
    end
    local label = type(db) == "table" and type(db.profileLabels) == "table" and guid and db.profileLabels[guid]
    if type(label) == "string" and label ~= "" then return label end
    local name = type(UnitName) == "function" and UnitName("player") or nil
    if type(name) == "string" and not (FS.IsSecret and FS.IsSecret(name)) then return name end
    return "unknown"
end

local function ProfileItems(...)
    local skip, items = {}, {}
    for _, name in ipairs({ ... }) do skip[name] = true end
    for _, name in ipairs(Config.ListProfiles()) do
        if not skip[name] then items[#items + 1] = { value = name, text = name } end
    end
    return items
end

local function Check(ok, err)
    if ok == false then I.Say(err) end
end

local function Build(content)
    local default = Config.DEFAULT_PROFILE
    UI.Section(content, {
        title = "Active profile",
        tip = "A profile holds layout positions and every setting in this window. Bug reports and logs stay account-wide.",
    })
    UI.Dropdown(content, {
        label = "Profile in use", regKey = "prof", nodot = true,
        get = Config.ActiveProfile,
        items = function() return ProfileItems() end,
        set = function(name) Check(Config.SetActiveProfile(name)) end,
    })
    UI.Info(content, { label = "This character", value = CharacterLabel })
    UI.Section(content, { title = "Manage" })
    UI.Acts(content, {
        label = "Profiles",
        buttons = {
            { text = "NEW PROFILE", onClick = function()
                UI.Prompt("Name the new profile.", "", function(name)
                    local ok, made = Config.NewProfile(name)
                    if not ok then return false, made end
                    Check(Config.SetActiveProfile(made))
                end)
            end },
            { text = "COPY FROM...", enabled = function() return #ProfileItems(Config.ActiveProfile()) > 0 end,
              reason = "There is no other profile to copy from.",
              onClick = function(b)
                  I.OpenMenu(b, ProfileItems(Config.ActiveProfile()), function(from)
                      local active = Config.ActiveProfile()
                      UI.Confirm(("Replace the settings and layout of %s with a copy of %s?"):format(active, from),
                          function() Check(Config.CopyProfile(from)) end)
                  end)
              end },
            { text = "RENAME", enabled = function() return Config.ActiveProfile() ~= default end,
              reason = "The Default profile cannot be renamed.", onClick = function()
                local active = Config.ActiveProfile()
                UI.Prompt(("Rename the profile %s."):format(active), active, function(name)
                    local ok, err = Config.RenameProfile(active, name)
                    if not ok then return false, err end
                end)
            end },
        },
    })
    UI.Button(content, {
        label = "Delete a profile", tip = "Default and the active profile cannot be deleted. Cannot be undone.",
        text = "DELETE", warn = true,
        enabled = function() return #ProfileItems(default, Config.ActiveProfile()) > 0 end,
        reason = "Default and the active profile cannot be deleted, and there is no other.",
        onClick = function(b)
            I.OpenMenu(b, ProfileItems(default, Config.ActiveProfile()), function(name)
                UI.Confirm(("Delete the profile %s?"):format(name), function() Check(Config.DeleteProfile(name)) end)
            end)
        end,
    })
    UI.Button(content, {
        label = "Put this profile back to the defaults", tip = "Cannot be undone.",
        text = "RESET", warn = true,
        confirm = function()
            return ("Put %s back to the defaults? Its layout positions are cleared too."):format(Config.ActiveProfile())
        end,
        onClick = function() Check(Config.ResetProfile()) end,
    })
end

CW.RegisterCategory({
    key = "profiles", label = "Profiles", group = "GENERAL", order = 2,
    tabs = { { key = "p", label = "Profiles", build = Build } },
})

-- Saved data builds after every other extension (order 1000), so Share and Modules sit above it.
local function HasExport()
    return FS.CharacterExport ~= nil and FS.CharacterExport.SETTING ~= nil
end

CW.ExtendTab("profiles", "p", { title = "Saved data", when = HasExport }, function(content)
    local export = FS.CharacterExport
    if not (export and export.SETTING) then return end
    UI.Toggle(content, { label = export.SETTING.label, key = export.SETTING.key, tip = export.SETTING.tip })
    local reload = export.RELOAD_SETTING
    if reload then
        UI.Toggle(content, {
            label = reload.label, key = reload.key, tip = reload.tip, sub = true,
            needs = export.SETTING.key, nl = export.SETTING.label,
        })
    end
end, 1000)
