-- Forever STUwave: Config page, Nameplates
-- Four tab shells (Size, Text, Parts, Friendly); the Nameplates ticket (C2) fills them. Today's rows live on Parts: the
-- STUwave nameplates switch (Nameplates.lua; off gives the game's own nameplates back, live) and the combo points switch.
-- Out of the page when the client has no nameplate API, where Nameplates.lua exports nothing.

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI

CW.RegisterCategory({
    key = "plates", label = "Nameplates", group = "FRAMES", order = 6,
    tabs = {
        { key = "size", label = "Size", build = function() end },
        { key = "text", label = "Text", build = function() end },
        { key = "parts", label = "Parts", build = function(content)
            local setting = FS.Nameplates and FS.Nameplates.SETTING
            if not (setting and setting.key) then return end
            UI.Section(content, { title = "What shows" })
            UI.Toggle(content, { label = setting.label, key = setting.key, tip = setting.tip })
            local combo = FS.NameplateCombo and FS.NameplateCombo.SETTING
            if combo and combo.key then
                UI.Toggle(content, { label = combo.label, key = combo.key, tip = combo.tip })
            end
        end },
        { key = "friendly", label = "Friendly", build = function() end },
    },
})
