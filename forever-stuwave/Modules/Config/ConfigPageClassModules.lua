-- Forever STUwave: Config page, Class modules
-- The Gunsight class modules, one tab each for all nine classes in the Addon tabs strip order, after a General tab. Sections
-- here never fold. An empty class says so. The rows that exist today live here; the class modules ticket (C4) adds the
-- module plate switches, the alert scale and the new class rows.

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI
local Config = FS.Config

local function ClassMessage(content, name)
    UI.Note(content, "The " .. name .. " module has nothing to set yet.")
end

-- "<Class> class module" with the module's own ? tip (what each piece shows), from HelpModules.lua through FS.ClassModuleHelp.
local function ModuleSection(content, token, title, tip)
    UI.Section(content, { title = title, tip = tip or FS.ClassModuleHelp[token] })
end

local tabs = {
    { key = "general", label = "General", build = function(content)
        UI.Section(content, { title = "Module plate", tip = "The panel the class module sits on, in the Gunsight under your target." })
        local Areas = FS.GunsightAreas
        local plate = Areas and Areas.SETTINGS and Areas.SETTINGS.background
        if plate then
            UI.Slider(content, {
                label = "Opacity", key = plate.key, min = plate.min, max = plate.max, step = plate.step, fmt = "%d%%",
                tip = "A dark plate behind your class module, so it stays readable on bright ground. "
                    .. "Higher is more solid; 0 removes the plate.",
            })
        end
    end },
    { key = "druid", label = "Druid", build = function(content)
        local CC = FS.DruidClearcasting
        if CC and CC.SETTING then
            UI.Section(content, { title = "Druid alerts", tip = "The big alert above your character when Clearcasting makes your next spell or ability free." })
            UI.Toggle(content, { label = CC.SETTING.label, key = CC.SETTING.key, tip = CC.SETTING.tip })
        end
    end },
    { key = "hunter", label = "Hunter", build = function(content)
        ModuleSection(content, "HUNTER", "Hunter class module")
        ClassMessage(content, "Hunter")
    end },
    { key = "mage", label = "Mage", build = function(content)
        ModuleSection(content, "MAGE", "Mage")
        ClassMessage(content, "Mage")
    end },
    { key = "paladin", label = "Paladin", build = function(content)
        ModuleSection(content, "PALADIN", "Paladin")
        ClassMessage(content, "Paladin")
    end },
    { key = "priest", label = "Priest", build = function(content)
        -- What the right side of the Priest module shows, and the Inner Fire reminder (PriestRight.lua)
        local Right = FS.PriestRight
        if not (Right and Right.SETTING and Right.REMIND) then return end
        local S = Right.SETTING
        UI.Section(content, { title = "Priest class module", tip = "What the right side of the Priest module shows beside the shield." })
        UI.Dropdown(content, {
            label = S.label, tip = S.tip, key = S.key,
            get = function() return Right.Setting() end,
            text = function(value) return S.text[value] or tostring(value) end,
            items = function()
                local items = {}
                for i, value in ipairs(S.values) do items[i] = { value = value, text = S.text[value] } end
                return items
            end,
            set = function(value) Config.Set(S.key, value) end,
        })
        UI.Toggle(content, { label = Right.REMIND.label, key = Right.REMIND.key, tip = Right.REMIND.tip, sub = true })
    end },
    { key = "rogue", label = "Rogue", build = function(content)
        ModuleSection(content, "ROGUE", "Rogue")
        ClassMessage(content, "Rogue")
    end },
    { key = "shaman", label = "Shaman", build = function(content)
        ModuleSection(content, "SHAMAN", "Shaman class module")
        UI.Note(content, "Nothing to set. Hover the ? for what it shows.")
    end },
    { key = "warlock", label = "Warlock", build = function(content)
        -- One switch per cue (WarlockState.lua)
        local WS = FS.WarlockState
        if not (WS and WS.SETTINGS and WS.ORDER) then return end
        UI.Section(content, { title = "Warlock class module", tip = "The cues on the right of the Warlock module. The shard count and the demon stay either way." })
        for _, name in ipairs(WS.ORDER) do
            local def = WS.SETTINGS[name]
            UI.Toggle(content, { label = def.label, key = def.key, tip = def.tip })
        end
    end },
    { key = "warrior", label = "Warrior", build = function(content)
        -- The power-up alerts (WarriorPowerUps.lua): the master switch, and one switch per spell
        local PU = FS.WarriorPowerUps
        if not (PU and PU.SETTING and PU.SPELLS and PU.ORDER) then return end
        UI.Section(content, { title = "Warrior power-up alerts", tip = "The big alert above your character when Overpower, Revenge or Victory Rush lights up." })
        UI.Toggle(content, { label = PU.SETTING.label, key = PU.SETTING.key, tip = PU.SETTING.tip })
        for _, key in ipairs(PU.ORDER) do
            local def = PU.SPELLS[key]
            UI.Toggle(content, {
                label = def.label, key = def.key, sub = true, needs = PU.SETTING.key, nl = PU.SETTING.label,
                tip = "Play the alert for " .. def.label .. ". Off leaves the other alerts as they are.",
            })
        end
    end },
}

CW.RegisterCategory({ key = "classmod", label = "Class modules", group = "SCREEN", order = 5, tabs = tabs })
