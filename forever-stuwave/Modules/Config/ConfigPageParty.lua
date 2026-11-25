-- Forever STUwave: Config page, Party frames
-- Frames tab: the party frames' own switch (PartyFrames.lua). The Style tab is the shared style blocks (ConfigPageBars.lua).
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
        { key = "style", label = "Style", build = function(content)
            if FS.ConfigBars then
                FS.ConfigBars.BuildStyleTab(content, { page = "party", tab = "style", frames = { "party" },
                    previewTip = "A party row as it is drawn with the settings below. Pointing at a setting turns that feature on here for a moment." })
            end
        end },
    },
})
