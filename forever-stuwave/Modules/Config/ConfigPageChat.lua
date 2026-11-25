-- Forever STUwave: Config page, Chat
-- Today's row: the line tint switch (ChatFormat.lua). The panels ticket (C5) owns the page from here and adds the window
-- size and the per kind tints.

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI

CW.RegisterCategory({
    key = "chat", label = "Chat", group = "PANELS", order = 1,
    tabs = { { key = "g", label = "Chat", build = function(content)
        local bands = FS.ChatFormat and FS.ChatFormat.BAND_SETTING
        if not bands then return end
        UI.Section(content, {
            title = "Line tint",
            tip = "A faint band behind each line of that kind, with a brighter edge on the left, so a conversation reads as one block.",
        })
        UI.Toggle(content, { label = bands.label, key = bands.key, tip = bands.tip })
    end } },
})
