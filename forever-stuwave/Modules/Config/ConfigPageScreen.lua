-- Forever STUwave: Config pages, the screen pieces with little to set: Cast bars, Action bars, Buffs and debuffs, Bags.
-- Cast bars and Buffs and debuffs are note pages (the power button in the page list turns each off). Action bars
-- holds the background grid and the micro menu icon style; Bags holds the bag bar's special bag right click.

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI
local Config = FS.Config

local function NotePage(key, label, group, order, text)
    CW.RegisterCategory({
        key = key, label = label, group = group, order = order,
        tabs = { { key = "g", label = label, build = function(content)
            UI.Section(content, { title = label })
            UI.Note(content, text)
        end } },
    })
end

NotePage("cast", "Cast bars", "FRAMES", 5, "No settings yet. The power button in the list turns cast bars off.")
NotePage("auras", "Buffs and debuffs", "SCREEN", 3, "No settings yet. The power button in the list turns buffs and debuffs off.")

-- The bag bar's right click on a quiver, ammo pouch or soul bag (BagBar.lua registers the key, default on).
local SPECIAL_BAG_KEY = "bagbar.specialRight"
local SPECIAL_BAG_TIP = "Covers quivers, ammo pouches and soul bags: a right click on one in the bag bar opens that bag alone, "
    .. "in a window of its own. Every other bag, and every bag while the game's combined bags option is off, keeps its stock click."

CW.RegisterCategory({
    key = "bags", label = "Bags", group = "PANELS", order = 3,
    tabs = { { key = "g", label = "Bags", build = function(content)
        UI.Section(content, { title = "Bag bar" })
        UI.Toggle(content, { label = "Right click opens only that bag", key = SPECIAL_BAG_KEY, tip = SPECIAL_BAG_TIP })
    end } },
})

-- Gradient or stock icons for the micro menu (MicroBars.lua), repainted live and explained by its ? tip.
local STYLE_TEXT = { gradient = "Gradient", stock = "Stock" }

CW.RegisterCategory({
    key = "ab", label = "Action bars", group = "SCREEN", order = 2,
    tabs = { { key = "g", label = "Action bars", build = function(content)
        UI.Section(content, { title = "Action bars" })
        UI.Toggle(content, { label = "Background grid", key = "actionbars.grid" })
        local micro = FS.MicroBars
        if micro and micro.SETTING and micro.Style then
            local def = micro.SETTING
            UI.Section(content, { title = "Micro menu" })
            local options = {}
            for i, value in ipairs(micro.STYLES) do options[i] = { value = value, text = STYLE_TEXT[value] or tostring(value) } end
            UI.Segmented(content, {
                label = def.label, tip = def.tip, options = options,
                get = function() return micro.Style() end,
                set = function(value) return Config.Set(def.key, value) end,
                regKey = def.key,
            })
        end
    end } },
})
