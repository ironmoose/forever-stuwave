-- Forever STUwave: Config page, Raid frames
-- Frames tab: the raid grid's own switch (RaidFrames.lua). Its reload line says when the game's raid frames were dimmed
-- this session and only a reload gives them back. The Style tab is the shared style blocks (ConfigPageBars.lua) with the raid layout size picker in the preview header
-- (it sets which size the layout editor previews too) and the raid's own Layout section.

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
            local Bars = FS.ConfigBars
            if not (preview and Bars) then return end
            local Config = FS.Config
            Bars.BuildStyleTab(content, {
                page = "raid", tab = "style", frames = { "raid" },
                previewTip = "A few raid frames as they are drawn with the settings below, for the layout size picked here. Pointing at a setting turns that feature on here for a moment.",
                -- the raid layout size, in the preview header
                header = function(band)
                    local buttons, prev = {}, nil
                    for index = #preview.SIZES, 1, -1 do
                        local size = preview.SIZES[index]
                        local b = Bars.PickerButton(band, tostring(size))
                        if prev then b:SetPoint("RIGHT", prev, "LEFT", -CW.Spec.SEG_GAP, 0) else b:SetPoint("TOPRIGHT", band, "TOPRIGHT", 0, -2) end
                        b:SetScript("OnClick", function() Config.Set(preview.KEY, size); CW.RefreshAll() end)
                        buttons[size] = b
                        prev = b
                    end
                    local label = CW.I.Label(band, "Raid layout", CW.Spec.TEXT, CW.C.muted)
                    label:SetPoint("RIGHT", prev, "LEFT", -CW.Spec.CTL_GAP, 0)
                    CW.I.Track(function()
                        for size, b in pairs(buttons) do Bars.MarkPicker(b, preview.Size() == size) end
                    end)
                    local tip = UI.HelpIcon(band, TIPS.size)
                    tip:SetPoint("RIGHT", label, "LEFT", -CW.Spec.Q_GAP, 0)
                end,
                before = function(body)
                    UI.Section(body, { title = "Layout", tip = "How the raid is drawn as a whole." })
                    UI.Slider(body, { label = "Scale", key = "raid.scale", min = 50, max = 150, step = 5, fmt = "%s%%",
                        tip = "Shrinks or grows the whole raid together. Width and Height under Frame still set the shape of each frame." })
                    UI.Segmented(body, { label = "Arrange", key = "raid.arrange",
                        options = { { value = "columns", text = "Group columns" }, { value = "grid", text = "Grid" } } })
                    UI.Slider(body, { label = "Frames per row", key = "raid.perRow", min = 2, max = 10, step = 1, sub = true,
                        when = function() return Config.Get("raid.arrange") == "grid" end })
                    UI.Segmented(body, { label = "Sort by", key = "raid.sort", sub = true,
                        when = function() return Config.Get("raid.arrange") == "grid" end,
                        tip = "Group keeps raid order. Role puts tanks, then healers, then damage.",
                        options = { { value = "group", text = "Group" }, { value = "role", text = "Role" }, { value = "class", text = "Class" }, { value = "name", text = "Name" } } })
                end,
            })
        end },
    },
})
