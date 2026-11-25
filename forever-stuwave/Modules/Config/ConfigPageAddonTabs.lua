-- Forever STUwave: Config page, Addon tabs
-- One page, one tab, no top tabs. The sections every class can use come first: Mana regen (its effect switches sit in the same section), the Ammo
-- tab, Icon style. Then Class tabs: a strip of the nine classes (a view choice kept in the account window state, not in
-- the profile, so it has no changed dot) and, under it, one set of sections per class, shown by `when` on the strip. The
-- tickets that add a class tab (shapeshift, call pet, portals, food and water, poisons, demons) add their section with
-- CW.ExtendTab("tabs", "general", { title = ..., when = CW.ClassWhen("DRUID") }, build). Class only sections never fold
-- and carry no CLASS ONLY tag: the strip picks the class.

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI
local Config = FS.Config

-- The nine classes in strip order: token and shown name.
local CLASSES = {
    { "DRUID", "Druid" }, { "HUNTER", "Hunter" }, { "MAGE", "Mage" }, { "PALADIN", "Paladin" }, { "PRIEST", "Priest" },
    { "ROGUE", "Rogue" }, { "SHAMAN", "Shaman" }, { "WARLOCK", "Warlock" }, { "WARRIOR", "Warrior" },
}
CW.CLASS_STRIP = CLASSES

local function OwnClass()
    if type(UnitClass) == "function" then
        local _, token = UnitClass("player")
        if type(token) == "string" then return token end
    end
end

-- The class the strip shows: the saved choice, else the player's own class, else the first.
function CW.ClassView()
    local saved = CW.UIState("tabsCls")
    for _, c in ipairs(CLASSES) do
        if c[1] == saved then return saved end
    end
    local own = OwnClass()
    for _, c in ipairs(CLASSES) do
        if c[1] == own then return own end
    end
    return CLASSES[1][1]
end

-- A `when` predicate for a section that belongs to one class.
function CW.ClassWhen(token)
    return function() return CW.ClassView() == token end
end

-- A module's SETTINGS table when it has the shape a section needs, else nil (a client without the module leaves it out).
local function Module(name, ...)
    local mod = FS[name]
    if type(mod) ~= "table" then return nil end
    for _, field in ipairs({ ... }) do
        if mod[field] == nil then return nil end
    end
    return mod
end

local function Applies(mod)
    return function()
        local ok, value = pcall(mod.Applies)
        return ok and value == true
    end
end

local function Toggles(content, tab, names, subs)
    for _, name in ipairs(names) do
        local def = tab.SETTINGS[name]
        if def then
            UI.Toggle(content, {
                label = def.label, key = def.key, tip = def.tip, sub = subs and name ~= names[1] or nil,
                needs = subs and name ~= names[1] and tab.SETTINGS[names[1]].key or nil,
                nl = subs and name ~= names[1] and tab.SETTINGS[names[1]].label or nil,
            })
        end
    end
end

-- The icon style dropdowns' texts (MicroBars.lua and SpellArt.lua both use gradient and stock).
local STYLE_TEXT = { gradient = "Gradient", stock = "Stock" }

CW.RegisterCategory({
    key = "tabs", label = "Addon tabs", group = "SCREEN", order = 4,
    tabs = { { key = "general", label = "Addon tabs", build = function(content)
        -- Mana regen (FiveSecondTab.lua), for the classes whose power is mana
        local regen = Module("FiveSecondTab", "SETTINGS", "Applies")
        if regen then
            UI.Section(content, { title = "Mana regen", tip = "The LED tab that counts down to full mana regen after a cast.", when = Applies(regen) })
            Toggles(content, regen, { "enabled", "pulse", "sound", "motion" }, true)
            if regen.FT and regen.FT.FX_NAMES then
                for _, name in ipairs(regen.FT.FX_NAMES) do
                    local def = regen.SETTINGS[name]
                    UI.Toggle(content, { label = def.label, key = def.key, tip = def.tip })
                end
            end
        end
        -- The ammo tab (AmmoTab.lua): Warriors, Hunters and Rogues
        local ammo = Module("AmmoTab", "SETTINGS", "Applies")
        if ammo then
            UI.Section(content, { title = "Ammo tab", when = Applies(ammo) })
            Toggles(content, ammo, { "enabled", "lowwarn", "motion" }, true)
        end
        -- Icon style: the class tab spell icons (SpellArt.lua), a row only once a tab has drawn a spell icon
        local art = Module("SpellArt", "SETTING", "Applies", "STYLES", "Style")
        if art then
            UI.Section(content, { title = "Icon style", when = Applies(art) })
            local def = art.SETTING
            local options = {}
            for i, value in ipairs(art.STYLES) do options[i] = { value = value, text = STYLE_TEXT[value] or tostring(value) } end
            UI.Segmented(content, {
                label = def.label, tip = def.tip, options = options,
                get = function() return art.Style() end,
                set = function(value) return Config.Set(def.key, value) end,
                regKey = def.key,
            })
        end
        -- Class tabs
        UI.Section(content, { title = "Class tabs", tip = "The tabs only one class gets. Pick a class to see its settings." })
        local options = {}
        for i, c in ipairs(CLASSES) do options[i] = { value = c[1], text = c[2] } end
        UI.Segmented(content, {
            label = "Class", options = options, regKey = "tabs.cls", nodot = true,
            get = CW.ClassView,
            set = function(value) CW.UIState("tabsCls", value) return true end,
        })
        -- Paladin
        UI.Section(content, {
            title = "Seal and aura block", when = CW.ClassWhen("PALADIN"),
            tip = "The tall block on the action bars: your seals on the top row and your auras on the bottom row, 7 each, "
                .. "learned ones packed left. The lit one glows. Bind keys to them with Quick Keybind.",
        })
        UI.Note(content, "No settings in the addon yet. It shows once you know a seal.")
        -- Priest
        UI.Section(content, { title = "Priest tab", when = CW.ClassWhen("PRIEST") })
        UI.Note(content, "No Priest tab yet.")
        -- Shaman
        UI.Section(content, { title = "Totem tab", when = CW.ClassWhen("SHAMAN"), tip = "Your totems on the action bars, one button per element." })
        UI.Note(content, "No settings in the addon yet. The presets below set the 1 and 2 buttons.")
        local buff = Module("BuffTab", "SETTINGS")
        if buff and buff.SETTINGS.combatstate then
            UI.Section(content, { title = "Shaman buff tab", when = CW.ClassWhen("SHAMAN") })
            local def = buff.SETTINGS.combatstate
            UI.Toggle(content, { label = def.label, key = def.key, tip = def.tip })
        end
        local presets = Module("TotemPresets", "SETTINGS")
        if presets then
            local P = presets.SETTINGS
            UI.Section(content, { title = "Totem presets", when = CW.ClassWhen("SHAMAN") })
            UI.Toggle(content, { label = P.preset1.label, key = P.preset1.key, tip = P.preset1.tip })
            UI.Toggle(content, { label = P.preset2.label, key = P.preset2.key, tip = P.preset2.tip })
            UI.Toggle(content, { label = P.plate.label, key = P.plate.key, tip = P.plate.tip, sub = true,
                needs = P.preset1.key, nl = P.preset1.label })
            UI.Toggle(content, { label = P.set2.label, key = P.set2.key, tip = P.set2.tip, sub = true,
                needs = P.preset2.key, nl = P.preset2.label })
        end
        -- Warrior
        UI.Section(content, {
            title = "Stance tab", when = CW.ClassWhen("WARRIOR"),
            tip = "Battle, Defensive and Berserker stance as three buttons on the action bars; the active one lights.",
        })
        UI.Note(content, "No settings in the addon yet.")
        local clap = Module("ThunderClapTab", "SETTINGS")
        if clap then
            UI.Section(content, { title = "Thunder Clap tab", when = CW.ClassWhen("WARRIOR") })
            Toggles(content, clap, { "enabled", "motion" }, true)
        end
    end } },
})
