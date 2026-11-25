-- Forever STUwave: Config page, Party frames
-- Frames tab: the party frames' own switch (PartyFrames.lua). The Style tab shell is filled by the party style ticket (C1b).
-- Move and Reset position are not here: moving and resetting happen in the layout editor (/fsedit).

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI

local TIP = "The party frames have their own switch. They follow it with the Gunsight HUD on or off, and the Party Frame key "
    .. "on the Console moves it too."

CW.RegisterCategory({
    key = "party", label = "Party frames", group = "FRAMES", order = 2,
    tabs = {
        { key = "frames", label = "Frames", build = function(content)
            local party = FS.PartyFrames
            UI.Section(content, { title = "Party frames" })
            if party and party.CONFIG_KEY then
                UI.Toggle(content, { label = "Show party frames", key = party.CONFIG_KEY, tip = TIP })
            end
        end },
        { key = "style", label = "Style", build = function() end },   -- C1b: the shared style blocks for Party
    },
})
