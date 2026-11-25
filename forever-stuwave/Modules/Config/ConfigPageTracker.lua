-- Forever STUwave: Config page, Quest tracker
-- The Size section (FS.Tracker.SIZE, Tracker.lua) and the quest timer under the minimap (QuestTimer.lua). Height is the
-- game's own Edit Mode Height for the tracker (400 to 1000; the prototype's range is not one Edit Mode accepts), written into
-- the active Edit Mode layout by Tracker.lua through TrackerSeat; it is live only once the tracker has been moved off its
-- default seat, which is also the only time the game shows or uses it. Width is on the page with the prototype's key and range
-- but locked: Edit Mode has no width setting for this tracker (see Tracker.lua).

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI

local function Locked() return false end

-- True once the active Edit Mode layout has the tracker off its default seat; false for anything else, a seat that cannot
-- answer included.
local function HeightLive()
    local seat = FS.TrackerSeat
    if type(seat) ~= "table" or type(seat.Moved) ~= "function" then return false end
    local ok, moved = pcall(seat.Moved)
    return ok and moved == true
end

local HEIGHT_TIP = "The tracker's height in the game's own Edit Mode, 400 to 1000 in steps of 10. It is saved in your active "
    .. "Edit Mode layout, and the game only uses it once the tracker has been moved off its default seat. Applies after combat."
local HEIGHT_REASON = "The game sizes the tracker itself while it sits in its default seat. Move it in the layout editor "
    .. "(/fsedit) first. Needs the game's Edit Mode."

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
        tip = HEIGHT_TIP, enabled = HeightLive, reason = HEIGHT_REASON,
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
