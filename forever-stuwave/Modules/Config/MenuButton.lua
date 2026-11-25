-- The Forever STUwave button in the Game Menu (Esc), right above AddOns: one click closes the menu and opens /fsconfig.
--
-- It is our own plain Button, never one from the menu's pool: MainMenuFrameMixin rebuilds that pool on every open and
-- its buttons run Blizzard's own flows (Log Out, Exit Game), and a pooled button comes back next open with another
-- label, so an emblem or font set on one would land on someone else's button. The menu is a VerticalLayoutFrame that
-- lays out every shown child with a layoutIndex (BaseLayoutMixin:AddLayoutChildren), so our child of GameMenuFrame
-- takes a place in the list by its index alone: after each InitButtons it gets AddOns' index minus a half, and the
-- section gap above AddOns (its topPadding) moves onto ours so the pair reads as one section. No Blizzard method is
-- replaced and no pooled button is anchored, sized or scripted. Without an AddOns row it sits above Log Out the same
-- way; with neither it hides. The chrome is the cyan STUwave text button (FS.ButtonSkins.SkinTextButton), the title the
-- display font with the logo's pink drop shadow, the addon emblem on the left.
local _, FS = ...
if type(FS) ~= "table" then return end

local Theme = FS.Theme
local CW = FS.ConfigWindow

FS.MenuButton = FS.MenuButton or {}
local MB = FS.MenuButton

MB.ICON = 22            -- the emblem's side (the 64 px art scaled down, so the default filter, not NEAREST)
MB.ICON_X = 6           -- the emblem's left inset
MB.TITLE_SIZE = 12
MB.TITLE = "Forever STUwave"
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
-- SetFont on a font object returns nothing, so the readback is the only proof the face took.
local function TitleFont()
    if MB.font then return MB.font end
    if type(CreateFont) ~= "function" then return nil end
    local f = CreateFont("ForeverSTUwaveMenuButtonFont")
    local path = Theme and Theme.FONT_ORBITRON
    if path then pcall(f.SetFont, f, path, MB.TITLE_SIZE, "") end
    local got = f.GetFont and f:GetFont()
    if not (path and type(got) == "string" and got:lower():find("fsdisplay", 1, true)) then
        pcall(f.SetFont, f, STANDARD_TEXT_FONT, MB.TITLE_SIZE, "")
        Log("font", "the display font did not load (" .. tostring(got) .. "), using the client font")
    end
    f:SetShadowColor(MB.PINK[1], MB.PINK[2], MB.PINK[3], 1)
    f:SetShadowOffset(1, -1)
    MB.font = f
    return f
end

function MB.Build(menu)
    if MB.button then return MB.button end
    local b = CreateFrame("Button", "ForeverSTUwaveMenuButton", menu)
    MB.button = b
    b:SetText(MB.TITLE)
    b:RegisterForClicks("LeftButtonUp")
    b:SetScript("OnClick", OnClick)
    b:Hide()

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

    local icon = b:CreateTexture(nil, "OVERLAY")
    icon:SetTexture(MB.ICON_PATH)
    icon:SetSize(MB.ICON, MB.ICON)
    icon:SetPoint("LEFT", b, "LEFT", MB.ICON_X, 0)
    MB.icon = icon
    return b
end

-- The pooled row whose label is `text`, or nil.
local function RowOf(menu, text)
    local pool = menu.buttonPool
    if type(text) ~= "string" or type(pool) ~= "table" or type(pool.EnumerateActive) ~= "function" then return nil end
    for button in pool:EnumerateActive() do
        if button.GetText and button:GetText() == text then return button end
    end
    return nil
end

-- After InitButtons: our button takes the slot right above AddOns (else Log Out), with that row's section gap.
function MB.Place(menu)
    local b = MB.Build(menu)
    if not b then return end
    local logout = type(menu.GetLogoutText) == "function" and select(2, pcall(menu.GetLogoutText, menu)) or nil
    local anchor = RowOf(menu, _G.ADDONS) or RowOf(menu, logout)
    if not (anchor and type(anchor.layoutIndex) == "number") then
        b.layoutIndex = nil
        b:Hide()
        return
    end
    b.layoutIndex = anchor.layoutIndex - 0.5
    b.topPadding, anchor.topPadding = anchor.topPadding, nil
    local w, h = anchor:GetSize()
    if w and w > 0 then b:SetSize(w, h) end
    b:Show()
    if type(menu.MarkDirty) == "function" then menu:MarkDirty() end
end

local function Hook()
    local menu = _G.GameMenuFrame
    if not (menu and type(hooksecurefunc) == "function" and type(menu.InitButtons) == "function") then
        Log("hook", "the game menu has no InitButtons on this client, so there is no button in it")
        return
    end
    hooksecurefunc(menu, "InitButtons", function(self)
        local ok, err = pcall(MB.Place, self)
        if not ok then Log("place", err) end
    end)
    if menu:IsShown() then pcall(MB.Place, menu) end
end

Hook()
