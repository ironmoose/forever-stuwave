-- Forever STUwave: Config page, Pet bar
-- Three tab shells: Style, Hunter and Warlock. The pet style ticket (C1c) fills them.

local _, FS = ...

local CW = FS.ConfigWindow

CW.RegisterCategory({
    key = "pet", label = "Pet bar", group = "FRAMES", order = 4,
    tabs = {
        { key = "style", label = "Style", build = function() end },
        { key = "hunter", label = "Hunter", build = function() end },
        { key = "warlock", label = "Warlock", build = function() end },
    },
})
