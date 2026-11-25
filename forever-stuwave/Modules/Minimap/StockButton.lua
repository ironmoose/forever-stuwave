-- Forever STUwave: the STU button on the game's own minimap
-- With the Minimap module switched off (Core/ModuleSwitch.lua, m.mini) the key row of Minimap.lua is never built, and the STU key
-- that opens the config window lives in that row. This file gives the key a place on the stock round minimap instead: a button
-- built the way LibDBIcon-1.0 builds an addon's minimap button, so it reads as every other addon's button on the map. It is placed
-- the way LibDBIcon places one too (an angle round the map, the button's centre half the map's width plus 5 out from its centre),
-- dragged round the rim with the left button, the angle saved in the profile (minimap.buttonAngle). A left click opens the config
-- window, the action of the STU key.
--
-- With the module on this file builds nothing: the key row has the STU key, and the addon tray collects the addons' buttons. With
-- the module off the tray is not built either, so every other addon's button stays where its addon put it, on the stock map.
--
-- Nothing of Blizzard's is moved, hidden, hooked or masked here. The button is our own frame, a child of Minimap (so it hides,
-- fades and scales with the map like every addon's button); Minimap is only read (its size, its centre, its scale).

local _, FS = ...

local MS = FS.ModuleSwitch

local B = {}
FS.MinimapStockButton = B

B.NAME = "ForeverSTUwaveMinimapButton"
B.KEY = "minimap.buttonAngle"
-- Degrees counter-clockwise from the right, as the cursor math gives them. 135 is the map's upper left: clear of the stock
-- expansion button (lower left, about 217) and the zoom buttons (lower right), and of the quest timer under the map.
B.DEFAULT_ANGLE = 135
-- How far the button's centre sits outside the map's edge (LibDBIcon's default radius), in UI units.
B.RIM = 5
-- LibDBIcon's button size, in UI units.
B.SIZE = 31

-- The look is LibDBIcon-1.0's (minor 56), texture for texture, so the button matches every other addon's: the tracking ring over
-- everything, the map's dark disc behind, the icon between them, and the zoom button's glow on hover. The icon is the addon's own
-- (the same file the toc's IconTexture names), a little inside its edge so the ring does not cover it.
B.BORDER = 136430      -- Interface\Minimap\MiniMap-TrackingBorder
B.BACKGROUND = 136467  -- Interface\Minimap\UI-Minimap-Background
B.HIGHLIGHT = 136477   -- Interface\Minimap\UI-Minimap-ZoomButton-Highlight
B.ICON = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\addon_icon"
-- The icon's texcoord inset at rest; pressed shows the whole texture, which is the little step back LibDBIcon gives a press.
B.ICON_INSET = 0.05

local Stock = {}
B.state = Stock

-------------------------------------------------------------------------------
-- Small helpers
-------------------------------------------------------------------------------

local function Log(what, err)
    if FS.LogDegradeOnce then
        FS.LogDegradeOnce("minimap_stock_button",
            "|cffff4488Forever STUwave|r: minimap button degraded (" .. tostring(what) .. "): " .. tostring(err))
    end
end

-- A usable plain number: never a secret (FS.IsSecret is read at call time and asked before anything compares the value),
-- never NaN or infinite.
local function Num(v)
    if type(v) ~= "number" then return false end
    if FS.IsSecret and FS.IsSecret(v) then return false end
    return v == v and v > -math.huge and v < math.huge
end

-- True when the Minimap module is off for this session (the switch store is there and says so). Read when it is asked, never at
-- file scope: the saved switches are not in before ADDON_LOADED. No store at all counts as on, as everywhere else.
function B.Applies()
    return MS ~= nil and MS.On("m.mini") == false
end

-- Where the three textures sit, by the client's project, as LibDBIcon lays them out: { size, point, x, y } each. The retail
-- project's (the Forever client shares it) has the ring 50 across and the disc and the icon centred; the other projects' ring is
-- 53 across with the disc and the icon set in from the top left to meet the ring's hole.
function B.Geometry()
    if _G.WOW_PROJECT_ID == _G.WOW_PROJECT_MAINLINE then
        return {
            border = { 50, "TOPLEFT", 0, 0 },
            background = { 24, "CENTER", 0, 0 },
            icon = { 18, "CENTER", 0, 0 },
        }
    end
    return {
        border = { 53, "TOPLEFT", 0, 0 },
        background = { 20, "TOPLEFT", 7, -5 },
        icon = { 17, "TOPLEFT", 7, -6 },
    }
end

-------------------------------------------------------------------------------
-- Where the button sits: the angle, and the ring placement
-------------------------------------------------------------------------------

-- Which quarters of the map GetMinimapShape calls round (bottom right, bottom left, top right, top left). The map is round unless
-- another addon defines GetMinimapShape and says otherwise; then the button follows the shape like any addon's button does.
local ROUND_QUARTERS = {
    ROUND = { true, true, true, true },
    SQUARE = { false, false, false, false },
    ["CORNER-TOPLEFT"] = { false, false, false, true },
    ["CORNER-TOPRIGHT"] = { false, false, true, false },
    ["CORNER-BOTTOMLEFT"] = { false, true, false, false },
    ["CORNER-BOTTOMRIGHT"] = { true, false, false, false },
    ["SIDE-LEFT"] = { false, true, false, true },
    ["SIDE-RIGHT"] = { true, false, true, false },
    ["SIDE-TOP"] = { false, false, true, true },
    ["SIDE-BOTTOM"] = { true, true, false, false },
    ["TRICORNER-TOPLEFT"] = { false, true, true, true },
    ["TRICORNER-TOPRIGHT"] = { true, false, true, true },
    ["TRICORNER-BOTTOMLEFT"] = { true, true, false, true },
    ["TRICORNER-BOTTOMRIGHT"] = { true, true, true, false },
}

local function MapShape()
    if type(_G.GetMinimapShape) ~= "function" then return "ROUND" end
    local ok, shape = pcall(_G.GetMinimapShape)
    if not ok or type(shape) ~= "string" or not ROUND_QUARTERS[shape] then return "ROUND" end
    return shape
end

-- The button's centre as an offset from the map's centre, for `angle` degrees, a map `halfW` by `halfH` UI units from its centre to
-- its edge and the shape name GetMinimapShape gives. On a round quarter the button rides the circle `RIM` outside the edge; on
-- a square one it rides the square, the diagonal pulled in so the corner does not stick out (LibDBIcon's placement).
function B.Offset(angle, halfW, halfH, shape)
    local rad = math.rad(angle)
    local x, y = math.cos(rad), math.sin(rad)
    local quarter = 1
    if x < 0 then quarter = quarter + 1 end
    if y > 0 then quarter = quarter + 2 end
    local w, h = halfW + B.RIM, halfH + B.RIM
    if (ROUND_QUARTERS[shape] or ROUND_QUARTERS.ROUND)[quarter] then return x * w, y * h end
    local diagW, diagH = math.sqrt(2 * w * w) - 10, math.sqrt(2 * h * h) - 10
    return math.max(-w, math.min(x * diagW, w)), math.max(-h, math.min(y * diagH, h))
end

-- The angle from a map's centre to a point, 0 to 360 degrees (the cursor, while the button is dragged).
function B.AngleTo(centerX, centerY, x, y)
    return math.deg(math.atan2(y - centerY, x - centerX)) % 360
end

-- The saved angle, or the default when the setting holds anything but a number. A refused save (read-only settings) is held for
-- the session so the button stays where it was dropped.
function B.Angle()
    if Stock.held then return Stock.held end
    local C = FS.Config
    local value = C and C.Get and C.Get(B.KEY)
    if not Num(value) then return B.DEFAULT_ANGLE end
    return value % 360
end

if FS.Config and FS.Config.RegisterDefault then FS.Config.RegisterDefault(B.KEY, B.DEFAULT_ANGLE) end

-- The centre on the map's rim for the angle now (the drag's while it runs, else the saved one).
local function Place()
    local button, map = Stock.button, _G.Minimap
    if not (button and map) then return end
    local width, height = map:GetWidth(), map:GetHeight()
    if not (Num(width) and Num(height) and width > 0 and height > 0) then return end
    local x, y = B.Offset(Stock.dragAngle or B.Angle(), width / 2, height / 2, MapShape())
    button:ClearAllPoints()
    button:SetPoint("CENTER", map, "CENTER", x, y)
end

-- Seats the button on the rim. A throw is logged once and never reaches the client's handler.
function B.Seat()
    if not Stock.button then return end
    local ok, err = pcall(Place)
    if not ok then Log("seat", err) end
end

-- The icon's texcoords: inset at rest, the whole texture while pressed or dragged (LibDBIcon's UpdateCoord).
local function SeatIcon()
    if not Stock.icon then return end
    local d = (Stock.down or Stock.dragging) and 0 or B.ICON_INSET
    Stock.icon:SetTexCoord(d, 1 - d, d, 1 - d)
end

-------------------------------------------------------------------------------
-- The mouse: tooltip, click, drag
-------------------------------------------------------------------------------

-- Where the tooltip goes: on the side of the screen the button is not, like every addon's button.
local function TipAnchors(owner)
    local x, y = owner:GetCenter()
    local ownScale, screenScale = owner:GetEffectiveScale(), UIParent:GetEffectiveScale()
    local width, height = UIParent:GetWidth(), UIParent:GetHeight()
    if not (Num(x) and Num(y) and Num(ownScale) and Num(screenScale) and screenScale > 0 and Num(width) and Num(height)) then
        return "TOPRIGHT", owner, "BOTTOMRIGHT"
    end
    local scale = ownScale / screenScale
    x, y = x * scale, y * scale
    local side = x > width * 2 / 3 and "RIGHT" or (x < width / 3 and "LEFT" or "")
    local top = y > height / 2
    return (top and "TOP" or "BOTTOM") .. side, owner, (top and "BOTTOM" or "TOP") .. side
end

local function ShowTip(owner)
    if not GameTooltip then return end
    pcall(function()
        GameTooltip:SetOwner(owner, "ANCHOR_NONE")
        GameTooltip:ClearAllPoints()
        GameTooltip:SetPoint(TipAnchors(owner))
        GameTooltip:SetText("Forever STUwave")
        GameTooltip:AddLine("Click to open the settings.", 1, 1, 1)
        GameTooltip:AddLine("Drag to move this button.", 1, 1, 1)
        GameTooltip:Show()
    end)
end

local function HideTip()
    if GameTooltip then pcall(function() GameTooltip:Hide() end) end
end

-- The cursor's angle round the map's centre, or nil when the map or the cursor cannot be read.
local function CursorAngle()
    local map = _G.Minimap
    if not (map and GetCursorPosition) then return nil end
    local cx, cy = map:GetCenter()
    local scale = map:GetEffectiveScale()
    local mx, my = GetCursorPosition()
    if not (Num(cx) and Num(cy) and Num(scale) and scale > 0 and Num(mx) and Num(my)) then return nil end
    return B.AngleTo(cx, cy, mx / scale, my / scale)
end

local function EndDrag()
    local button = Stock.button
    if not (button and Stock.dragging) then return end
    Stock.dragging, Stock.down = false, false
    button:SetScript("OnUpdate", nil)
    button:UnlockHighlight()
    local angle = Stock.dragAngle
    Stock.dragAngle = nil
    if angle then
        angle = math.floor(angle * 10 + 0.5) / 10 % 360
        Stock.held = nil
        local C = FS.Config
        local saved = C and C.Set and C.Set(B.KEY, angle)
        if not saved then Stock.held = angle end
    end
    B.Seat()
    SeatIcon()
end

local function DragUpdate()
    -- A drag whose release the client never reported (the mouse let go over another window) ends here, not on the next click.
    if IsMouseButtonDown and not IsMouseButtonDown("LeftButton") then
        EndDrag()
        return
    end
    local angle = CursorAngle()
    if not angle then return end
    Stock.dragAngle = angle
    B.Seat()
end

local function StartDrag()
    Stock.dragging = true
    HideTip()
    local button = Stock.button
    button:LockHighlight()
    button:SetScript("OnUpdate", DragUpdate)
    SeatIcon()
end

local function OnClick()
    local window = FS.ConfigWindow
    if window and window.Toggle then window.Toggle() end
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local function Lay(region, spec)
    region:ClearAllPoints()
    region:SetSize(spec[1], spec[1])
    region:SetPoint(spec[2], spec[3], spec[4])
end

local function Build()
    if Stock.button then return end
    local map = _G.Minimap
    if not map then
        Log("build", "the minimap frame is missing")
        return
    end
    local button = CreateFrame("Button", B.NAME, map)
    -- An addon's button on the stock map: its own strata and level, pinned so a change to the map's does not shuffle it.
    pcall(button.SetFrameStrata, button, "MEDIUM")
    pcall(button.SetFrameLevel, button, 8)
    if button.SetFixedFrameStrata then pcall(button.SetFixedFrameStrata, button, true) end
    if button.SetFixedFrameLevel then pcall(button.SetFixedFrameLevel, button, true) end
    button:RegisterForClicks("LeftButtonUp")
    button:RegisterForDrag("LeftButton")
    button:SetHighlightTexture(B.HIGHLIGHT, "ADD")
    button:SetSize(B.SIZE, B.SIZE)

    local geometry = B.Geometry()
    local border = button:CreateTexture(nil, "OVERLAY")
    border:SetTexture(B.BORDER)
    Lay(border, geometry.border)
    local background = button:CreateTexture(nil, "BACKGROUND")
    background:SetTexture(B.BACKGROUND)
    Lay(background, geometry.background)
    local icon = button:CreateTexture(nil, "ARTWORK")
    icon:SetTexture(B.ICON)
    Lay(icon, geometry.icon)
    Stock.border, Stock.background, Stock.icon = border, background, icon
    SeatIcon()

    button:SetScript("OnEnter", function()
        if not Stock.dragging then ShowTip(button) end
    end)
    button:SetScript("OnLeave", function()
        Stock.down = false
        SeatIcon()
        HideTip()
    end)
    button:SetScript("OnMouseDown", function()
        Stock.down = true
        SeatIcon()
    end)
    button:SetScript("OnMouseUp", function()
        Stock.down = false
        SeatIcon()
    end)
    button:SetScript("OnDragStart", StartDrag)
    button:SetScript("OnDragStop", EndDrag)
    button:SetScript("OnClick", OnClick)
    -- A button hidden with the mouse on it gets no OnLeave; a map shown again may have another size.
    button:SetScript("OnHide", function()
        Stock.down = false
        EndDrag()
        SeatIcon()
        HideTip()
    end)
    button:SetScript("OnShow", function() B.Seat() end)

    Stock.button = button
    B.Seat()
end

-- Builds the button once, when the module is off, then keeps it seated: a new UI scale, display size or Edit Mode layout can change
-- the map's size, so the rim position is laid again (and once more a frame later, when the map's own size is final).
local watcher = CreateFrame("Frame")
watcher:RegisterEvent("PLAYER_LOGIN")
watcher:SetScript("OnEvent", function(self, event)
    if event == "PLAYER_LOGIN" then
        self:UnregisterEvent("PLAYER_LOGIN")
        if not B.Applies() then return end
        local ok, err = pcall(Build)
        if not ok then
            Log("build", err)
            return
        end
        self:RegisterEvent("UI_SCALE_CHANGED")
        self:RegisterEvent("DISPLAY_SIZE_CHANGED")
        self:RegisterEvent("EDIT_MODE_LAYOUTS_UPDATED")
        return
    end
    B.Seat()
    if C_Timer and C_Timer.After then C_Timer.After(0, B.Seat) end
end)

-- A profile switch, import or reset can carry another angle; a held (unsaved) angle belongs to the profile it was dropped in.
if FS.Config and FS.Config.OnChange then
    FS.Config.OnChange(B.KEY, function()
        Stock.held = nil
        B.Seat()
    end)
end
