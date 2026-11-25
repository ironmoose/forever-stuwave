-- Forever STUwave: Config page, Quest tracker
-- Today's row: the quest timer under the minimap (QuestTimer.lua). The panels ticket (C5) owns the page from here and adds
-- the size.

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI

CW.RegisterCategory({
    key = "track", label = "Quest tracker", group = "PANELS", order = 4,
    tabs = { { key = "g", label = "Quest tracker", build = function(content)
        local timer = FS.QuestTimer and FS.QuestTimer.SETTING
        if not timer then return end
        UI.Section(content, { title = "Quest tracker" })
        UI.Toggle(content, { label = timer.label, key = timer.key, tip = timer.tip })
    end } },
})
