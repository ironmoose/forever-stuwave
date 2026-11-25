-- Forever STUwave: TrackerSeat
-- Where the objectives tracker sits. The tracker is a Blizzard Edit Mode system that a secure
-- frame manager places, so addon code never anchors it. A move is written into the active Edit
-- Mode layout instead, and Blizzard applies that layout itself. A preset layout (Modern, Classic)
-- cannot be edited, so the first move copies it to an account layout named "STUwave".
-- The tracker's Height (Edit Mode's own slider, 400 to 1000) goes through the same layout: Moved, Height and SetHeight below.
-- LayoutEdit drives this through Ready, Rect, Offsets, Move and Reset. Rect and offsets describe the
-- visible panel (UIParent units, TOPRIGHT from UIParent's TOPRIGHT); Move converts that to the Blizzard
-- frame's TOPRIGHT, which is what Edit Mode stores (also in UIParent units).
-- While Questie's tracker is on, Questie hides Blizzard's frame (and STUwave's panel, which hangs from it), so
-- there is no tracker to see: no seat is reported, and /fsedit shows no handle for it.

local _, FS = ...

local Seat = FS.TrackerSeat or {}
FS.TrackerSeat = Seat

-- Module power (Core/ModuleSwitch.lua): with the Quest tracker switch off the objectives tracker is the game's own and no
-- seat of ours is reported or written. In particular nothing is saved into the "STUwave" Edit Mode layout while it is off
-- (a layout written earlier stays as it was: turning the switch off does not take it back out). Read when called, never at
-- file scope: the saved switches are not known until ADDON_LOADED.
local MS = FS.ModuleSwitch
local function Active() return MS == nil or MS.On("m.track") end

local LAYOUT_NAME = "STUwave"
local POINT = "TOPRIGHT"

local function Frame()
    return _G.ObjectiveTrackerFrame
end

-- Questie's tracker replaces the Blizzard one while it is on (Modules/Compat/Questie.lua). Asked each time: the
-- player can switch it in Questie's options.
local function QuestieHasTheTracker()
    local compat = FS.QuestieCompat
    return type(compat) == "table" and type(compat.TrackerActive) == "function" and compat.TrackerActive() == true
end

local QUESTIE_REASON = "Questie's tracker is on, so there is no objectives tracker to move"
local OFF_REASON = "the Quest tracker module is off, so the game's own tracker is left where it is"
local DEFAULT_SEAT_REASON = "the game sizes the tracker itself while it sits in its default seat"

local function SystemId()
    local systems = Enum and Enum.EditModeSystem
    return systems and systems.ObjectiveTracker
end

local function LayoutTypes()
    return Enum and Enum.EditModeLayoutType
end

-- Enum.EditModeObjectiveTrackerSetting.Height: nil on a client whose tracker has none.
local function HeightSetting()
    local settings = Enum and Enum.EditModeObjectiveTrackerSetting
    return settings and settings.Height
end

-- What Edit Mode accepts for the tracker's Height (Blizzard_EditMode EditModeSettingDisplayInfo: Slider, 400 to 1000, step
-- 10), in screen units, and the game's own default (its preset layouts store 40, which is 800). A layout stores
-- (height - min) / step, an integer from 0 to 60. The game only uses the setting while the tracker is off its default seat
-- (EditModeObjectiveTrackerSystemMixin:ShouldShowSetting hides it there, ObjectiveTrackerContainerMixin:UpdateHeight sizes
-- the tracker itself there), so a height is only written for a tracker that has been moved.
Seat.HEIGHT = { min = 400, max = 1000, step = 10, default = 800 }

-- The raw value a layout stores for a height in screen units, snapped to the step and held to the range; nil for anything
-- that is not a finite number.
local function RawHeight(value)
    if type(value) ~= "number" or value - value ~= 0 then return nil end
    local h = Seat.HEIGHT
    local raw = math.floor((value - h.min) / h.step + 0.5)
    return math.max(0, math.min((h.max - h.min) / h.step, raw))
end

function Seat.Ready()
    if not Active() or QuestieHasTheTracker() then return false end
    local frame = Frame()
    return type(frame) == "table" and frame.GetRight ~= nil
        and type(C_EditMode) == "table" and type(C_EditMode.GetLayouts) == "function"
        and type(C_EditMode.SaveLayouts) == "function" and type(C_EditMode.SetActiveLayout) == "function"
        and type(_G.EditModePresetLayoutManager) == "table" and SystemId() ~= nil and LayoutTypes() ~= nil
end

-- A frame's rect in UIParent units: left, top, width, height.
local function RectOf(frame)
    if not frame then return nil end
    local left, top, width, height = frame:GetLeft(), frame:GetTop(), frame:GetWidth(), frame:GetHeight()
    if not (left and top and width and height) then return nil end
    local s = frame:GetEffectiveScale() / UIParent:GetEffectiveScale()
    return left * s, top * s, width * s, height * s
end

-- What the player sees: the STUwave panel when it is built and shown, else Blizzard's frame.
local function Visible()
    local tracker = FS.Tracker
    local panel = type(tracker) == "table" and type(tracker.Panel) == "function" and tracker.Panel()
    if panel and panel.IsShown and panel:IsShown() and RectOf(panel) then return panel end
    return Frame()
end

-- The visible tracker's rect in UIParent units: left, top, width, height.
function Seat.Rect()
    if not Active() or QuestieHasTheTracker() then return nil end
    return RectOf(Visible())
end

-- The visible tracker's TOPRIGHT offset from UIParent's TOPRIGHT, in UIParent units.
function Seat.Offsets()
    local left, top, width = Seat.Rect()
    if not left then return nil end
    return left + width - UIParent:GetRight(), top - UIParent:GetTop()
end

-- How far the visible TOPRIGHT sits from Blizzard's frame TOPRIGHT, which is what Edit Mode anchors.
local function VisibleShift()
    local vl, vt, vw = Seat.Rect()
    local fl, ft, fw = RectOf(Frame())
    if not (vl and fl) then return 0, 0 end
    return (vl + vw) - (fl + fw), vt - ft
end

local function TrackerSystem(layout)
    local id = SystemId()
    for _, system in ipairs(layout and layout.systems or {}) do
        if system.system == id then return system end
    end
end

-- Every layout as Blizzard's own SaveLayouts hands them over: the presets first, then the saved ones.
local function AllLayouts()
    local info = C_EditMode.GetLayouts()
    if type(info) ~= "table" or type(info.layouts) ~= "table" then return nil end
    local layouts = _G.EditModePresetLayoutManager:GetCopyOfPresetLayouts()
    for _, layout in ipairs(info.layouts) do layouts[#layouts + 1] = layout end
    info.layouts = layouts
    return info
end

local function UniqueName(layouts)
    local taken = {}
    for _, layout in ipairs(layouts) do taken[layout.layoutName] = true end
    if not taken[LAYOUT_NAME] then return LAYOUT_NAME end
    for n = 2, 99 do
        local name = LAYOUT_NAME .. " " .. n
        if not taken[name] then return name end
    end
end

-- The active layout, copied out of a preset into a new account layout when the preset is active.
-- Returns info, layout or nil, reason.
local function WritableActive()
    local info = AllLayouts()
    if not info then return nil, "Edit Mode layouts are not loaded yet" end
    local types = LayoutTypes()
    local layout = info.layouts[info.activeLayout]
    if not layout then return nil, "no active Edit Mode layout" end
    if layout.layoutType ~= types.Preset then return info, layout end

    local count = 0
    for _, other in ipairs(info.layouts) do
        if other.layoutType == types.Account then count = count + 1 end
    end
    local max = Constants and Constants.EditModeConsts and Constants.EditModeConsts.EditModeMaxLayoutsPerType or 5
    local name = UniqueName(info.layouts)
    if count >= max or not name then return nil, "Edit Mode has no free account layout slot" end

    local copy = CopyTable(layout)
    copy.layoutType = types.Account
    copy.layoutName = name
    info.layouts[#info.layouts + 1] = copy
    info.activeLayout = #info.layouts
    return info, copy
end

local function Save(info)
    C_EditMode.SaveLayouts(info)
    C_EditMode.SetActiveLayout(info.activeLayout)
end

-- Puts `raw` into the system's Height entry (adding the entry, or the whole settings list, when the layout has none).
-- Returns whether the stored value changed.
local function WriteHeight(system, raw)
    local id = HeightSetting()
    if not id then return false end
    if type(system.settings) ~= "table" then system.settings = {} end
    for _, entry in ipairs(system.settings) do
        if entry.setting == id then
            if entry.value == raw then return false end
            entry.value = raw
            return true
        end
    end
    system.settings[#system.settings + 1] = { setting = id, value = raw }
    return true
end

-- The active layout's tracker system, or nil and why (and whether waiting could help: the layouts or Edit Mode itself are
-- not there yet).
local function ActiveSystem()
    local info = AllLayouts()
    if not info then return nil, "Edit Mode layouts are not loaded yet", true end
    local system = TrackerSystem(info.layouts[info.activeLayout])
    if not system then return nil, "the active layout has no objectives tracker" end
    return system, info
end

-- True once the active layout has the tracker off its default seat, false while it sits there (every preset, and an account
-- layout it was never moved in), nil when that cannot be read (the module is off, Questie has the tracker, Edit Mode is not
-- there or its layouts are not loaded yet).
function Seat.Moved()
    if not Seat.Ready() then return nil end
    local system = ActiveSystem()
    if not system or type(system.isInDefaultPosition) ~= "boolean" then return nil end
    return not system.isInDefaultPosition
end

-- The active layout's tracker Height in screen units (400 to 1000), or nil when it cannot be read.
function Seat.Height()
    local id = HeightSetting()
    if not id or not Seat.Ready() then return nil end
    local system = ActiveSystem()
    if not system then return nil end
    for _, entry in ipairs(system.settings or {}) do
        if entry.setting == id and type(entry.value) == "number" then
            return entry.value * Seat.HEIGHT.step + Seat.HEIGHT.min
        end
    end
end

-- Writes a Height (screen units; snapped to the step, held to the range) into the active layout, in place. Returns true, or
-- false, why and a third value that is true when waiting could help (combat, layouts not loaded, no Edit Mode yet). It never
-- copies a preset and never anchors a frame: a preset or a tracker still in its default seat is refused, because the game
-- does not use the setting there; the player's first move (Seat.Move) takes the tracker off it.
function Seat.SetHeight(value)
    if not Active() then return false, OFF_REASON end
    if QuestieHasTheTracker() then return false, QUESTIE_REASON end
    if not HeightSetting() then return false, "this client's Edit Mode has no tracker Height" end
    local raw = RawHeight(value)
    if not raw then return false, "a tracker height is a number from " .. Seat.HEIGHT.min .. " to " .. Seat.HEIGHT.max end
    if InCombatLockdown() then return false, "can't change the tracker in combat", true end
    if not Seat.Ready() then return false, "Edit Mode is not available", true end
    local system, info, wait = ActiveSystem()
    if not system then return false, info, wait end
    if system.isInDefaultPosition then return false, DEFAULT_SEAT_REASON end
    if WriteHeight(system, raw) then Save(info) end
    return true
end

-- Seats the visible tracker's TOPRIGHT at (x, y) from UIParent's TOPRIGHT. Returns true, or false and why.
function Seat.Move(x, y)
    if not Active() then return false, OFF_REASON end
    if QuestieHasTheTracker() then return false, QUESTIE_REASON end
    if InCombatLockdown() then return false, "can't move the tracker in combat" end
    if not Seat.Ready() then return false, "Edit Mode is not available" end
    local info, layout = WritableActive()
    if not info then return false, layout end
    local system = TrackerSystem(layout)
    if not system then return false, "the active layout has no objectives tracker" end
    local dx, dy = VisibleShift()
    system.isInDefaultPosition = false
    system.anchorInfo = { point = POINT, relativeTo = "UIParent", relativePoint = POINT, offsetX = x - dx, offsetY = y - dy }
    system.anchorInfo2 = nil
    -- A height the player set while the tracker sat elsewhere (or in another layout) goes into the same save; a setting
    -- still at its default leaves the layout's own height as it is.
    local tracker = FS.Tracker
    if type(tracker) == "table" and type(tracker.WantedHeight) == "function" then
        local ok, wanted = pcall(tracker.WantedHeight)
        local raw = ok and RawHeight(wanted) or nil
        if raw then WriteHeight(system, raw) end
    end
    Save(info)
    return true
end

-- Puts the tracker back in Blizzard's default seat in the active layout. A preset has nothing to reset.
function Seat.Reset()
    if not Active() then return false, OFF_REASON end
    if QuestieHasTheTracker() then return false, QUESTIE_REASON end
    if InCombatLockdown() then return false, "can't move the tracker in combat" end
    if not Seat.Ready() then return false, "Edit Mode is not available" end
    local info = AllLayouts()
    if not info then return false, "Edit Mode layouts are not loaded yet" end
    local layout = info.layouts[info.activeLayout]
    if not layout or layout.layoutType == LayoutTypes().Preset then return true end
    local system = TrackerSystem(layout)
    local default = TrackerSystem(info.layouts[1])
    if not (system and default) then return false, "the active layout has no objectives tracker" end
    if system.isInDefaultPosition then return true end
    system.isInDefaultPosition = true
    system.anchorInfo = CopyTable(default.anchorInfo)
    system.anchorInfo2 = default.anchorInfo2 and CopyTable(default.anchorInfo2) or nil
    Save(info)
    return true
end
