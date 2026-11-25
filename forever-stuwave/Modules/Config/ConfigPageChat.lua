-- Forever STUwave: Config page, Chat
-- The window (Chat.SIZE, Chat.BG: ChatWindowState.lua, ChatFrameSkin.lua) and the line tint (ChatFormat.BAND_SPEC). Every
-- row is read from the module that owns it and left out when the module is absent. The rows and keys are the prototype's.

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI

-- The prototype's words for the rows that carry one.
local TIPS = {
    whisper = "Both directions, yours and theirs.",
    raid = "Raid chat, raid leader and raid warning lines. Off until you turn it on.",
}

local function ColourOptions(names)
    local options = {}
    for _, name in ipairs(names) do options[#options + 1] = { value = name, text = name } end
    return options
end

local function BuildWindow(content)
    local size, background = FS.Chat and FS.Chat.SIZE, FS.Chat and FS.Chat.BG
    if not (size or background) then return end
    UI.Section(content, { title = "Window" })
    if size then
        UI.Slider(content, {
            label = "Width", key = size.w.key, min = size.w.min, max = size.w.max, step = size.w.step, fmt = "%d px",
            tip = "Same as dragging the chat corner in the layout editor (/fsedit).",
        })
        UI.Slider(content, {
            label = "Height", key = size.h.key, min = size.h.min, max = size.h.max, step = size.h.step, fmt = "%d px",
        })
    end
    if background then
        UI.Slider(content, {
            label = "Background opacity", key = background.key, min = background.min, max = background.max,
            step = background.step, fmt = "%d%%", tip = "Only the dark fill. Text, tabs and the border stay solid.",
        })
    end
end

local function BuildLineTint(content)
    local spec = FS.ChatFormat and FS.ChatFormat.BAND_SPEC
    local bands = FS.ChatFormat and FS.ChatFormat.BAND_SETTING
    if not bands then return end
    UI.Section(content, {
        title = "Line tint",
        tip = "A faint band behind each line of that kind, with a brighter edge on the left, so a conversation reads as one block.",
    })
    -- A chat module that only has the one switch (no per kind spec) gets just that switch, under its own label.
    UI.Toggle(content, { label = spec and "Line tint" or bands.label, key = bands.key, tip = not spec and bands.tip or nil })
    if not spec then return end
    local strength = spec.strength
    UI.Slider(content, {
        label = "Strength", key = strength.key, min = strength.min, max = strength.max, step = strength.step, fmt = "%d%%",
        sub = true, needs = bands.key, nl = "Line tint",
        tip = ("How strong the band is. Today %d%%."):format(strength.default),
    })
    local colours = ColourOptions(spec.colors)
    for _, kind in ipairs(spec.kinds) do
        UI.Toggle(content, {
            label = kind.label, key = kind.key, sub = true, needs = bands.key, nl = "Line tint", tip = TIPS[kind.id],
        })
        UI.Segmented(content, {
            label = "Colour", key = kind.colorKey, options = colours, sub = true, needs = kind.key, nl = kind.label,
        })
    end
end

CW.RegisterCategory({
    key = "chat", label = "Chat", group = "PANELS", order = 1,
    tabs = { { key = "g", label = "Chat", build = function(content)
        BuildWindow(content)
        BuildLineTint(content)
    end } },
})
