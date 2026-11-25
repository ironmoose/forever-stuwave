-- The Forever STUwave plate under the Game Menu (Esc): one click closes the menu and opens /fsconfig.
--
-- It is our own plain Button parented to GameMenuFrame and docked under its bottom edge, never a button from the
-- menu's pool: MainMenuFrameMixin rebuilds the pooled list on every open and its buttons run Blizzard's own flows
-- (Log Out, Exit Game), so nothing of ours goes into that pool. Anchored to the frame, it follows every resize the
-- menu's layout makes. The chrome is the STUwave text button (FS.ButtonSkins.SkinTextButton, cyan) so hover, press
-- and focus look like the menu's own buttons; the title is the display font with the logo's pink drop shadow and
-- the addon emblem sits on the left.
local _, FS = ...
if type(FS) ~= "table" then return end

local Theme = FS.Theme
local CW = FS.ConfigWindow

FS.MenuButton = FS.MenuButton or {}
local MB = FS.MenuButton

MB.HEIGHT = 34          -- a touch taller than the menu's buttons: it is the addon's own door, not one more row
MB.GAP = 6              -- space between the menu's bottom edge and the plate
MB.INSET = 0            -- the plate is as wide as the menu
MB.ICON = 26            -- the emblem's side (the 64 px art scaled down, so the default filter, not NEAREST)
MB.ICON_X = 6           -- the emblem's left inset
MB.TITLE_SIZE = 13
MB.ICON_PATH = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\addon_icon"
MB.PINK = { 1, 0.180, 0.592 }  -- #ff2e97, the logo's shadow

local function Log(key, msg)
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "menubutton_" .. key, "|cffff4488Forever STUwave|r: menu button: " .. tostring(msg))
    end
end

local function OnClick()
    if type(PlaySound) == "function" and SOUNDKIT and SOUNDKIT.IG_MAINMENU_OPTION then
        pcall(PlaySound, SOUNDKIT.IG_MAINMENU_OPTION)
    end
    local menu = _G.GameMenuFrame
    if menu and menu:IsShown() then
        if type(HideUIPanel) == "function" then HideUIPanel(menu) else menu:Hide() end
    end
    if CW and CW.Open then CW.Open() end
end

-- One font object for all three states: SkinTextButton paints the colour per state, the face stays the display font.
local function TitleFont()
    if MB.font then return MB.font end
    if type(CreateFont) ~= "function" then return nil end
    local f = CreateFont("ForeverSTUwaveMenuButtonFont")
    local path = Theme and Theme.FONT_ORBITRON
    if not (path and f:SetFont(path, MB.TITLE_SIZE, "")) then
        f:SetFont(STANDARD_TEXT_FONT, MB.TITLE_SIZE, "")
        Log("font", "the display font did not load, using the client font")
    end
    f:SetShadowColor(MB.PINK[1], MB.PINK[2], MB.PINK[3], 1)
    f:SetShadowOffset(1, -1)
    MB.font = f
    return f
end

function MB.Build()
    if MB.button then return MB.button end
    local menu = _G.GameMenuFrame
    if not (menu and type(CreateFrame) == "function") then return nil end
    local b = CreateFrame("Button", "ForeverSTUwaveMenuButton", menu)
    MB.button = b
    b:SetHeight(MB.HEIGHT)
    b:SetPoint("TOPLEFT", menu, "BOTTOMLEFT", MB.INSET, -MB.GAP)
    b:SetPoint("TOPRIGHT", menu, "BOTTOMRIGHT", -MB.INSET, -MB.GAP)
    b:SetText("FOREVER STUWAVE")
    b:RegisterForClicks("LeftButtonUp")
    b:SetScript("OnClick", OnClick)

    if FS.ButtonSkins and FS.ButtonSkins.SkinTextButton then
        local ok, err = pcall(FS.ButtonSkins.SkinTextButton, b, { accent = "cyan", size = MB.TITLE_SIZE })
        if not ok then Log("skin", err) end
    end
    local font = TitleFont()
    if font then
        b:SetNormalFontObject(font)
        b:SetHighlightFontObject(font)
        b:SetDisabledFontObject(font)
    end

    -- the emblem, and the title nudged right of it so the pair reads centred
    local icon = b:CreateTexture(nil, "OVERLAY")
    icon:SetTexture(MB.ICON_PATH)
    icon:SetSize(MB.ICON, MB.ICON)
    icon:SetPoint("LEFT", b, "LEFT", MB.ICON_X, 0)
    MB.icon = icon
    local fs = b:GetFontString()
    if fs then
        fs:ClearAllPoints()
        fs:SetPoint("CENTER", b, "CENTER", math.floor((MB.ICON_X + MB.ICON) / 2), 0)
    end
    return b
end

local function Hook()
    local menu = _G.GameMenuFrame
    if not (menu and menu.HookScript) then return end
    menu:HookScript("OnShow", function()
        local ok, err = pcall(MB.Build)
        if not ok then Log("build", err) end
    end)
    if menu:IsShown() then pcall(MB.Build) end
end

Hook()
