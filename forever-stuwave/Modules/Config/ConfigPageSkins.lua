-- Forever STUwave: Config page, Window skins
-- Windows tab: the panels, the backgrounds and the damage meter rows. Alerts tab: the stun alert and the toasts. Each row
-- reads its module's setting; a module that is absent leaves its row out.

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI
local Config = FS.Config

local function StyleOptions(bd)
    local options = {}
    for i, value in ipairs(bd.STYLES) do options[i] = { value = value, text = bd.STYLE_TEXT[value] } end
    return options
end

local tabs = {
    { key = "win", label = "Windows", build = function(content)
        UI.Section(content, { title = "Panels" })
        UI.Toggle(content, { label = "Professions panel", key = "professions.shown" })
        local speed = FS.QuestSkin and FS.QuestSkin.SPEED_SETTING
        if speed then UI.Segmented(content, { label = speed.label, key = speed.key, tip = speed.tip, options = speed.options }) end
        -- The talent spec backgrounds (Skins/TalentBackdrops.lua) and the character window background (CharBackdrop.lua):
        -- animated, still or off.
        local talents, char = FS.TalentBackdrops, FS.CharBackdrop
        local hasTalents = talents and talents.SETTING and talents.STYLES
        local hasChar = char and char.SETTING and char.STYLES
        if hasTalents or hasChar then
            UI.Section(content, { title = "Backgrounds" })
            if hasTalents then
                local def = talents.SETTING
                UI.Segmented(content, { label = def.label, tip = def.tip, key = def.key, options = StyleOptions(talents) })
            end
            if hasChar then
                local def = char.SETTING
                UI.Segmented(content, { label = def.label, tip = def.tip, key = def.key, options = StyleOptions(char) })
            end
        end
        -- The damage meter's row style (Skins/DamageMeter.lua), neon plates or the ladder, relaid live
        local skin = FS.DamageMeterSkin
        if skin and skin.SETTING and skin.Style then
            local def = skin.SETTING
            UI.Section(content, { title = "Damage meter" })
            UI.Dropdown(content, {
                label = def.label, tip = def.tip, regKey = def.key,
                get = function() return skin.Style() end,
                text = function(value) return skin.STYLE_TEXT[value] or tostring(value) end,
                items = function()
                    local items = {}
                    for i, value in ipairs(skin.STYLES) do items[i] = { value = value, text = skin.STYLE_TEXT[value] } end
                    return items
                end,
                set = function(value) Config.Set(def.key, value) end,
            })
        end
    end },
    { key = "alerts", label = "Alerts", build = function(content)
        UI.Section(content, { title = "Alerts" })
        local snap = FS.LossOfControl and FS.LossOfControl.SNAP_SETTING
        if snap then UI.Toggle(content, { label = snap.label, key = snap.key, tip = snap.tip }) end
        local alerts = FS.HudAlerts and FS.HudAlerts.SETTINGS
        if alerts then
            for _, name in ipairs({ "low", "fuse", "flash" }) do
                local setting = alerts[name]
                if setting then UI.Toggle(content, { label = setting.label, key = setting.key, tip = setting.tip }) end
            end
        end
    end },
}

CW.RegisterCategory({ key = "skins", label = "Window skins", group = "PANELS", order = 6, tabs = tabs })
