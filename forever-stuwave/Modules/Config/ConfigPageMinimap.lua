-- Forever STUwave: Config page, Minimap
-- Today's row: the coordinates switch (MinimapCoords). The panels ticket (C5) owns the page from here and adds the size.

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI

CW.RegisterCategory({
    key = "mini", label = "Minimap", group = "PANELS", order = 2,
    tabs = { { key = "g", label = "Minimap", build = function(content)
        local coords = FS.MinimapCoords and FS.MinimapCoords.SETTING
        if not coords then return end
        UI.Section(content, { title = "Minimap" })
        UI.Toggle(content, { label = coords.label, key = coords.key, tip = coords.tip })
    end } },
})
