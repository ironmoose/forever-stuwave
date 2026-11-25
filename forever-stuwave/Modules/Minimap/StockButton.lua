-- Forever STUwave: the STU button on the game's own minimap
-- With the Minimap module switched off (Core/ModuleSwitch.lua, m.mini) the key row of Minimap.lua is never built, and the STU key
-- that opens the config window lives in that row. This file gives the key a place on the stock round minimap instead: a small
-- round STUwave button on the map's rim, placed the way LibDBIcon places an addon's minimap button (an angle round the map, the
-- button's centre half the map's width plus 5 out from its centre), dragged round the rim with the left button, the angle saved in
-- the profile (minimap.buttonAngle). A left click opens the config window, the action of the STU key.
--
-- With the module on this file builds nothing: the key row has the STU key, and the addon tray collects the addons' buttons. With
-- the module off the tray is not built either, so every other addon's button stays where its addon put it, on the stock map.
--
-- Nothing of Blizzard's is moved, hidden, hooked or masked here. The button is our own frame, a child of Minimap (so it hides,
-- fades and scales with the map like every addon's button); Minimap is only read (its size, its centre, its scale). The
-- ring is a stack of flat rows, one run of whole physical pixels per row, so the circle has hard pixel edges at any scale.

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
-- The button's width, in UI units: a little under the 31 an addon button takes, whole physical pixels from PixelUnit.
B.SIZE = 28
-- The STU mark's canvas is 32 texels with the art 22 of them (generate_icon_stu.py); the texels are laid 1 : 1 at SIZE. Its solid
-- texels reach 12.9 texels from the canvas centre (the harness measures it), so 13 is what the face has to hold.
local STU_TEXELS = 32
local STU_INK_RADIUS = 13
local STU_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\icon_stu.tga"

-- The rim is one pixel; the face is the Theme's button ink, so the mark reads as on the key row. Hot (mouse over, dragging) turns
-- the rim pink and full strength, as the STU key's outline does; pressed darkens the face.
local THEME = FS.Theme or {}
local RING_COLOR = THEME.COLOR_POWER or { 0.133, 0.878, 1, 1 }
local RING_HOT = THEME.COLOR_HEALTH or { 1, 0.180, 0.592, 1 }
local FACE_COLOR = THEME.COLOR_BUTTON_INK or { 0.090, 0.047, 0.165, 1 }
local FACE_DOWN = THEME.COLOR_BAR_TRACK or { 0.039, 0.016, 0.086, 1 }
local RING_REST_ALPHA = 0.75

local Stock = {
    ring = {},      -- the rim's rows (a flat texture each), the outer disc
    face = {},      -- the face's rows, the inner disc on top of the rim
    pixels = nil,   -- UI units per physical pixel the rows were laid for
    diameter = nil, -- the disc's width in physical pixels
}
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

local function Crisp(texture)
    if texture.SetSnapToPixelGrid then pcall(texture.SetSnapToPixelGrid, texture, true) end
    if texture.SetTexelSnappingBias then pcall(texture.SetTexelSnappingBias, texture, 0) end
    return texture
end

-- UI units per physical pixel at `frame`; 1 when the client will not say (every edge then sits on a whole UI unit).
local function PixelUnit(frame)
    local helpers = FS.FrameHelpers
    local px = helpers and helpers.PixelUnit and helpers.PixelUnit(frame)
    if not Num(px) or px <= 0 then return 1 end
    return px
end

-- True when the Minimap module is off for this session (the switch store is there and says so). Read when it is asked, never at
-- file scope: the saved switches are not in before ADDON_LOADED. No store at all counts as on, as everywhere else.
function B.Applies()
    return MS ~= nil and MS.On("m.mini") == false
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

-------------------------------------------------------------------------------
-- The disc: flat rows of whole pixels
-------------------------------------------------------------------------------

-- One run per row of a disc of `diameter` pixels and `radius` pixels: the pixels whose centres lie inside the circle. Returns
-- { { y = row, x0 = first pixel, x1 = last pixel }, ... } with rows and columns counted from the top left from 0, empty rows left out.
function B.DiscRuns(diameter, radius)
    local runs = {}
    local centre, limit = diameter / 2, radius * radius + 1e-9
    for y = 0, diameter - 1 do
        local dy = y + 0.5 - centre
        local first, last
        for x = 0, diameter - 1 do
            local dx = x + 0.5 - centre
            if dx * dx + dy * dy <= limit then
                first = first or x
                last = x
            end
        end
        if first then runs[#runs + 1] = { y = y, x0 = first, x1 = last } end
    end
    return runs
end

-- The disc's width in physical pixels for the pixel size at the button: B.SIZE UI units, never fewer than 12 pixels.
function B.Diameter(px)
    return math.max(12, math.floor(B.SIZE / px + 0.5))
end

-- The mark's canvas in pixels: the texels scaled with the disc, never so large that the ink reaches past the face (a very small
-- disc), and of the disc's parity so the canvas centres on whole pixels.
function B.Canvas(diameter)
    local canvas = math.floor(STU_TEXELS * diameter / B.SIZE + 0.5)
    canvas = math.min(canvas, math.floor(STU_TEXELS * (diameter / 2 - 0.5) / STU_INK_RADIUS))
    if (canvas - diameter) % 2 ~= 0 then canvas = canvas - 1 end
    return canvas
end

-- Lays rows `runs` out on `list` (flat textures made as needed, on `sublevel` of BACKGROUND); rows past the last run hide.
local function SeatRows(button, list, runs, sublevel, px)
    for i, run in ipairs(runs) do
        local row = list[i]
        if not row then
            row = Crisp(button:CreateTexture(nil, "BACKGROUND", nil, sublevel))
            list[i] = row
        end
        row:ClearAllPoints()
        row:SetPoint("TOPLEFT", button, "TOPLEFT", run.x0 * px, -run.y * px)
        row:SetSize((run.x1 - run.x0 + 1) * px, px)
        row:Show()
    end
    for i = #runs + 1, #list do list[i]:Hide() end
end

local function Paint()
    local button = Stock.button
    if not button then return end
    local hot = Stock.over or Stock.dragging
    local ring = hot and RING_HOT or RING_COLOR
    local alpha = hot and 1 or RING_REST_ALPHA
    for _, row in ipairs(Stock.ring) do row:SetColorTexture(ring[1], ring[2], ring[3], alpha) end
    local face = Stock.down and FACE_DOWN or FACE_COLOR
    for _, row in ipairs(Stock.face) do row:SetColorTexture(face[1], face[2], face[3], 1) end
end

-- The rows, the face's size and the mark for the pixel size at the button now. Cheap when nothing changed.
local function SeatLook()
    local button = Stock.button
    local px = PixelUnit(button)
    if Stock.pixels == px and Stock.diameter then return end
    local diameter = B.Diameter(px)
    local radius = diameter / 2
    button:SetSize(diameter * px, diameter * px)
    SeatRows(button, Stock.ring, B.DiscRuns(diameter, radius), 1, px)
    SeatRows(button, Stock.face, radius > 1 and B.DiscRuns(diameter, radius - 1) or {}, 2, px)
    local canvas = B.Canvas(diameter)
    local inset = (diameter - canvas) / 2
    Stock.icon:ClearAllPoints()
    Stock.icon:SetPoint("TOPLEFT", button, "TOPLEFT", inset * px, -inset * px)
    Stock.icon:SetSize(canvas * px, canvas * px)
    Stock.pixels, Stock.diameter = px, diameter
    Paint()
end

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

-- Both, for a new angle, a new map size or a new pixel size. A throw is logged once and never reaches the client's handler.
function B.Seat()
    if not Stock.button then return end
    local ok, err = pcall(function()
        SeatLook()
        Place()
    end)
    if not ok then Log("seat", err) end
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
    Stock.dragging = false
    button:SetScript("OnUpdate", nil)
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
    Paint()
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
    Stock.button:SetScript("OnUpdate", DragUpdate)
    Paint()
end

local function OnClick()
    local window = FS.ConfigWindow
    if window and window.Toggle then window.Toggle() end
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

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

    Stock.icon = Crisp(button:CreateTexture(nil, "ARTWORK", nil, 1))
    Stock.icon:SetTexture(STU_TEXTURE)

    button:SetScript("OnEnter", function()
        Stock.over = true
        Paint()
        if not Stock.dragging then ShowTip(button) end
    end)
    button:SetScript("OnLeave", function()
        Stock.over, Stock.down = false, false
        Paint()
        HideTip()
    end)
    button:SetScript("OnMouseDown", function()
        Stock.down = true
        Paint()
    end)
    button:SetScript("OnMouseUp", function()
        Stock.down = false
        Paint()
    end)
    button:SetScript("OnDragStart", StartDrag)
    button:SetScript("OnDragStop", EndDrag)
    button:SetScript("OnClick", OnClick)
    -- A button hidden with the mouse on it gets no OnLeave; a map shown again may have another pixel size.
    button:SetScript("OnHide", function()
        Stock.over, Stock.down = false, false
        EndDrag()
        Paint()
        HideTip()
    end)
    button:SetScript("OnShow", function() B.Seat() end)

    Stock.button = button
    B.Seat()
end

-- Builds the button once, when the module is off, then keeps it seated: a new UI scale or display size changes the pixel and
-- the map's size, so the rows and the rim position are laid again (and once more a frame later, when the map's own size is final).
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
