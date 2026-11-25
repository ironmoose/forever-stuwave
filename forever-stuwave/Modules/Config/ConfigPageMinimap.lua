-- Forever STUwave: Config page, Minimap
-- The Size section (Width, Height, Scale: FS.MinimapSettings, Minimap.lua) and the coordinates switch (MinimapCoords). A row
-- is left out when the module that owns it is absent.

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI

local function BuildSize(content)
    local size = FS.MinimapSettings
    if not size then return end
    local follows = size.heightFollowsWidth == true
    UI.Section(content, { title = "Size" })
    UI.Slider(content, {
        label = "Width", key = size.w.key, min = size.w.min, max = size.w.max, step = size.w.step, fmt = "%d px",
        tip = follows and "The map only draws square, so the height follows the width."
            or "Width and height apart need a check in game first: the map may only draw square, in which case it crops the longer side.",
    })
    UI.Slider(content, {
        label = "Height", key = size.h.key, min = size.h.min, max = size.h.max, step = size.h.step, fmt = "%d px",
        enabled = function() return not follows end, reason = "The map only draws square, so the height follows the width.",
    })
    UI.Slider(content, {
        label = "Scale", key = size.scale.key, min = size.scale.min, max = size.scale.max, step = size.scale.step, fmt = "%d%%",
        tip = "Grows or shrinks the whole minimap with its tray, buttons and text together.",
    })
end

CW.RegisterCategory({
    key = "mini", label = "Minimap", group = "PANELS", order = 2,
    tabs = { { key = "g", label = "Minimap", build = function(content)
        BuildSize(content)
        local coords = FS.MinimapCoords and FS.MinimapCoords.SETTING
        if not coords then return end
        UI.Section(content, { title = "Minimap" })
        UI.Toggle(content, { label = coords.label, key = coords.key, tip = coords.tip })
    end } },
})
