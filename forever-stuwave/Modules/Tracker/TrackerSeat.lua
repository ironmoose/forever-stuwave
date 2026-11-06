-- Forever STUwave: TrackerSeat
-- Where the objectives tracker sits. The tracker is a Blizzard Edit Mode system that a secure
-- frame manager places, so addon code never anchors it. A move is written into the active Edit
-- Mode layout instead, and Blizzard applies that layout itself. A preset layout (Modern, Classic)
-- cannot be edited, so the first move copies it to an account layout named "STUwave".
-- LayoutEdit drives this through Ready, Rect, Offsets, Move and Reset. Rect and offsets describe the
-- visible panel (UIParent units, TOPRIGHT from UIParent's TOPRIGHT); Move converts that to the Blizzard
-- frame's TOPRIGHT, which is what Edit Mode stores (also in UIParent units).

local _, FS = ...

local Seat = FS.TrackerSeat or {}
FS.TrackerSeat = Seat

local LAYOUT_NAME = "STUwave"
local POINT = "TOPRIGHT"

local function Frame()
    return _G.ObjectiveTrackerFrame
end

local function SystemId()
    local systems = Enum and Enum.EditModeSystem
    return systems and systems.ObjectiveTracker
end

local function LayoutTypes()
    return Enum and Enum.EditModeLayoutType
end

function Seat.Ready()
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

-- Seats the visible tracker's TOPRIGHT at (x, y) from UIParent's TOPRIGHT. Returns true, or false and why.
function Seat.Move(x, y)
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
    Save(info)
    return true
end

-- Puts the tracker back in Blizzard's default seat in the active layout. A preset has nothing to reset.
function Seat.Reset()
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
