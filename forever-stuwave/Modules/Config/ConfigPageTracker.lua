-- Forever STUwave: Config page, Quest tracker
-- The Size section (FS.Tracker.SIZE, Tracker.lua) and the quest timer under the minimap (QuestTimer.lua). Width and Height are
-- on the page with the prototype's keys and ranges but locked: the game's own tracker owns both (see Tracker.lua).

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI

local function Locked() return false end

local function BuildSize(content)
    local size = FS.Tracker and FS.Tracker.SIZE
    if not size then return end
    local why = FS.Tracker.SIZE_LOCKED
    UI.Section(content, { title = "Size" })
    UI.Slider(content, {
        label = "Width", key = size.w.key, min = size.w.min, max = size.w.max, step = size.w.step, fmt = "%d px",
        enabled = Locked, reason = why,
    })
    UI.Slider(content, {
        label = "Height", key = size.h.key, min = size.h.min, max = size.h.max, step = size.h.step, fmt = "%d px",
        enabled = Locked, reason = why,
    })
    UI.Slider(content, {
        label = "Scale", key = size.scale.key, min = size.scale.min, max = size.scale.max, step = size.scale.step,
        fmt = "%d%%", tip = "Grows or shrinks the text and the panel together.",
    })
    UI.Slider(content, {
        label = "Opacity", key = size.alpha.key, min = size.alpha.min, max = size.alpha.max, step = size.alpha.step,
        fmt = "%d%%", tip = "The whole tracker, text included.",
    })
    UI.Slider(content, {
        label = "Background opacity", key = size.bgAlpha.key, min = size.bgAlpha.min, max = size.bgAlpha.max,
        step = size.bgAlpha.step, fmt = "%d%%", tip = "Only the dark panel behind the quests.",
    })
end

CW.RegisterCategory({
    key = "track", label = "Quest tracker", group = "PANELS", order = 4,
    tabs = { { key = "g", label = "Quest tracker", build = function(content)
        BuildSize(content)
        local timer = FS.QuestTimer and FS.QuestTimer.SETTING
        if not timer then return end
        UI.Section(content, { title = "Quest tracker" })
        UI.Toggle(content, { label = timer.label, key = timer.key, tip = timer.tip })
    end } },
})
