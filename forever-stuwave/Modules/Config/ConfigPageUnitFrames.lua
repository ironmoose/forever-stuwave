-- Forever STUwave: Config page, Unit Frames (Player, Target, Focus and Boss)
-- Frames tab: the four Show switches. The Style tab shell is filled by the Style ticket (C1).

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI

CW.RegisterCategory({
    key = "unit", label = "Unit Frames", group = "FRAMES", order = 1,
    tabs = {
        { key = "frames", label = "Frames", build = function(content)
            UI.Section(content, { title = "Frames", tip = "A frame that is off stays click-through and invisible." })
            -- The saved keys hold a hide flag (unitFrames.hidePlayer / hideTarget): the row shows and writes the inverse,
            -- so a player who hid a frame before still sees its switch off.
            UI.Toggle(content, { label = "Show player frame", key = "unitFrames.hidePlayer", inverted = true })
            UI.Toggle(content, { label = "Show target frame", key = "unitFrames.hideTarget", inverted = true })
            UI.Toggle(content, { label = "Show focus frame", key = "unitFrames.showFocus" })
            UI.Toggle(content, { label = "Show boss frames", key = "unitFrames.showBoss" })
        end },
        { key = "bars", label = "Style", build = function() end },   -- C1: frame picker and the shared style blocks
    },
})
