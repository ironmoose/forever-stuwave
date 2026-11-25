-- Forever STUwave: Config page, Class modules
-- The Gunsight class modules, a General tab and then one tab per class (all nine, in the Addon tabs strip order). Sections
-- here never fold (UI.Section forbids it on this page). General holds what every class module shares: the plate it sits on
-- (Background, Border, Opacity, GunsightAreas.lua) and the alert scale (the pop up alerts that own a frame read it through
-- Areas.AlertScale()). A class with nothing to set says so. Every row maps to a setting a module reads; the page reads each
-- module's SETTING(S) table at build time and leaves a row out when the module is absent.

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI
local Config = FS.Config

local AMMO_WARN = { min = 0, max = 400, step = 10 }   -- the count the Hunter module warns under (HunterState.AmmoWarn)

local function ClassMessage(content, name)
    UI.Note(content, "The " .. name .. " module has nothing to set yet.")
end

-- "<Class> class module" with the module's own ? tip (what each piece shows), from HelpModules.lua through FS.ClassModuleHelp.
local function ModuleSection(content, token, title, tip)
    return UI.Section(content, { title = title, tip = tip or FS.ClassModuleHelp[token] })
end

-- A part of the plate that is switched on (a stored value that is not a boolean reads as the default, on).
local function PlateOn(def)
    return Config.Get(def.key) ~= false
end

local function PlateTab(content)
    local Areas = FS.GunsightAreas
    local set = Areas and Areas.SETTINGS
    UI.Section(content, { title = "Module plate", tip = "The panel the class module sits on, in the Gunsight under your target." })
    if not set then return end
    UI.Toggle(content, { label = "Background", key = set.bg.key, tip = "The dark fill behind the module." })
    UI.Toggle(content, { label = "Border", key = set.border.key, tip = "The cyan outline and its glow." })
    UI.Slider(content, {
        label = "Opacity", key = set.background.key, min = set.background.min, max = set.background.max,
        step = set.background.step, fmt = "%d%%",
        tip = "How solid the plate is: the background and border together. 0 hides both.",
        enabled = function() return PlateOn(set.bg) or PlateOn(set.border) end,
        reason = "Requires |cffffffffBackground|r or |cffffffffBorder|r to be on.",
    })
    local alertsSec = UI.Section(content, {
        title = "Alerts",
        tip = "The pop up alerts class modules show above your character: Overpower, Revenge and Victory Rush, and Clearcasting.",
    })
    if CW.Flash and CW.Flash.AddTest then CW.Flash.AddTest(alertsSec, CW.Flash.ScaleOwner()) end
    UI.Slider(content, {
        label = "Alert scale", key = set.alertScale.key, min = set.alertScale.min, max = set.alertScale.max,
        step = set.alertScale.step, fmt = "%d%%",
        tip = "Grows or shrinks every pop up class alert together. Cues drawn inside the module keep the module's size.",
    })
end

-- Priest: the left half has nothing to set; the right half is one pick, the one line that explains the pick, and the Inner Fire
-- pulse, which only the two looks that carry Inner Fire have (PriestRight.lua holds the labels and the lines).
local function PriestTab(content)
    local shieldSec = UI.Section(content, {
        title = "Left: Power Word: Shield",
        tip = "The round shield on the left fills with light while your shield holds. The rim turns violet during Weakened Soul.",
    })
    if CW.Flash and CW.Flash.AddTest then CW.Flash.AddTest(shieldSec, "procs.placeholder") end
    UI.Note(content, "Always shown once you know the spell. Nothing to set.")
    local Right = FS.PriestRight
    if not (Right and Right.SETTING and Right.REMIND) then return end
    local S = Right.SETTING
    UI.Section(content, {
        title = "Right: what sits beside the shield",
        tip = "Pick one. A change made in a fight applies when the fight ends.",
    })
    local options = {}
    for i, value in ipairs(S.values) do options[i] = { value = value, text = S.text[value] } end
    UI.Segmented(content, { label = S.label, key = S.key, options = options })
    for _, value in ipairs(S.values) do
        if S.notes and S.notes[value] then
            UI.Note(content, { text = S.notes[value], when = function() return Right.Setting() == value end })
        end
    end
    UI.Toggle(content, {
        label = Right.REMIND.label, key = Right.REMIND.key, tip = Right.REMIND.tip,
        when = function() local v = Right.Setting() return v == "auto" or v == "spirit" end,
    })
end

local tabs = {
    { key = "general", label = "General", build = PlateTab },
    { key = "druid", label = "Druid", build = function(content)
        local CC = FS.DruidClearcasting
        if CC and CC.SETTING then
            local sec = UI.Section(content, { title = "Druid alerts", tip = "The big alert above your character when Clearcasting makes your next spell or ability free." })
            if CW.Flash and CW.Flash.AddTest then CW.Flash.AddTest(sec, "druid") end
            UI.Toggle(content, { label = CC.SETTING.label, key = CC.SETTING.key, tip = CC.SETTING.tip })
        end
    end },
    { key = "hunter", label = "Hunter", build = function(content)
        local sec = ModuleSection(content, "HUNTER", "Hunter class module")
        if CW.Flash and CW.Flash.AddTest then CW.Flash.AddTest(sec, "procs.placeholder") end
        local HS = FS.HunterState
        local warn = HS and HS.SETTINGS and HS.SETTINGS.ammoWarn
        if not warn then return ClassMessage(content, "Hunter") end
        UI.Slider(content, {
            label = "Low ammo warning below", key = warn.key, min = AMMO_WARN.min, max = AMMO_WARN.max, step = AMMO_WARN.step,
            fmt = "%d",
            tip = "The module warns when your arrows or bullets drop under this many. 0 warns only when you are out. "
                .. "The ammo tab turns amber at the same count.",
        })
    end },
    { key = "mage", label = "Mage", build = function(content)
        local sec = ModuleSection(content, "MAGE", "Mage")
        if CW.Flash and CW.Flash.AddTest then CW.Flash.AddTest(sec, "procs.placeholder") end
        ClassMessage(content, "Mage")
    end },
    { key = "paladin", label = "Paladin", build = function(content)
        local sec = ModuleSection(content, "PALADIN", "Paladin")
        if CW.Flash and CW.Flash.AddTest then CW.Flash.AddTest(sec, "procs.paladin") end
        ClassMessage(content, "Paladin")
    end },
    { key = "priest", label = "Priest", build = PriestTab },
    { key = "rogue", label = "Rogue", build = function(content)
        local sec = ModuleSection(content, "ROGUE", "Rogue")
        if CW.Flash and CW.Flash.AddTest then CW.Flash.AddTest(sec, "procs.placeholder") end
        ClassMessage(content, "Rogue")
    end },
    { key = "shaman", label = "Shaman", build = function(content)
        local sec = ModuleSection(content, "SHAMAN", "Shaman class module")
        if CW.Flash and CW.Flash.AddTest then CW.Flash.AddTest(sec, "procs.placeholder") end
        UI.Note(content, "Nothing to set. Hover the ? for what it shows.")
    end },
    { key = "warlock", label = "Warlock", build = function(content)
        -- One switch per cue (WarlockState.lua)
        local WS = FS.WarlockState
        if not (WS and WS.SETTINGS and WS.ORDER) then return end
        local sec = UI.Section(content, { title = "Warlock class module", tip = "The cues on the right of the Warlock module. The shard count and the demon stay either way." })
        if CW.Flash and CW.Flash.AddTest then CW.Flash.AddTest(sec, "procs.warlock") end
        for _, name in ipairs(WS.ORDER) do
            local def = WS.SETTINGS[name]
            UI.Toggle(content, { label = def.label, key = def.key, tip = def.tip })
        end
    end },
    { key = "warrior", label = "Warrior", build = function(content)
        -- The power-up alerts (WarriorPowerUps.lua): the master switch, and one switch per spell
        local PU = FS.WarriorPowerUps
        if not (PU and PU.SETTING and PU.SPELLS and PU.ORDER) then return end
        local sec = UI.Section(content, { title = "Warrior power-up alerts", tip = "The big alert above your character when Overpower, Revenge or Victory Rush lights up." })
        if CW.Flash and CW.Flash.AddTest then CW.Flash.AddTest(sec, "warrior") end
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

-- Module power (m.gs): the class modules are part of the Gunsight HUD module, which has no page of its own here, so the
-- off card never covers this one. With the module off for this session none of them is built and a row would change nothing:
-- every tab says so in place of its rows. Decided from the session value (what was built); the wording follows the switch.
local function GunsightOff()
    local MS = FS.ModuleSwitch
    return MS ~= nil and not MS.On("m.gs")
end

local function OffNote(content)
    local MS = FS.ModuleSwitch
    local label = MS.Label("m.gs") or "Gunsight HUD"
    UI.Note(content, { text = function()
        if MS.Wanted("m.gs") then return label .. " turns on at the next Reload UI." end
        return label .. " is off. Turning it on takes a Reload UI."
    end })
end

for _, tab in ipairs(tabs) do
    local build = tab.build
    tab.build = function(content)
        if GunsightOff() then return OffNote(content) end
        return build(content)
    end
end

CW.RegisterCategory({ key = "classmod", label = "Class modules", group = "SCREEN", order = 5, tabs = tabs })
