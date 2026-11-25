-- Forever STUwave: Config page, Raid frames
-- Frames tab: the raid grid's own switch (RaidFrames.lua). Its reload line says when the game's raid frames were dimmed
-- this session and only a reload gives them back. The Style tab holds the raid layout size picker for now (it sets which
-- size the layout editor previews); the raid style ticket (C1b) builds the rest around it.

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI

local TIPS = {
    show = "In a raid, shows the raid as group columns, in place of the game's raid frames. Each raid size has its own "
        .. "seat, set in the layout editor. Turned off, the grid hides at once and the game's raid frames come back after /reload.",
    size = "Each raid size has its own seat. Pick the size the layout editor previews; its panel switches size too. In a "
        .. "raid the grid uses the seat of the smallest size that fits the group.",
}

CW.RegisterCategory({
    key = "raid", label = "Raid frames", group = "FRAMES", order = 3,
    tabs = {
        { key = "frames", label = "Frames", build = function(content)
            local raid = FS.RaidFrames
            UI.Section(content, { title = "Raid frames" })
            if raid and raid.CONFIG_KEY then
                UI.Toggle(content, { label = "Show raid frames", key = raid.CONFIG_KEY, tip = TIPS.show, reload = raid.NeedsReload })
            end
        end },
        { key = "style", label = "Style", build = function(content)
            local raid = FS.RaidFrames
            local preview = raid and type(raid.Preview) == "table" and raid.Preview
            if not preview then return end
            UI.Section(content, { title = "Raid" })
            local options = {}
            for index, size in ipairs(preview.SIZES) do options[index] = { value = size, text = tostring(size) } end
            UI.Segmented(content, { label = "Raid layout", tip = TIPS.size, key = preview.KEY, options = options })
        end },
    },
})
