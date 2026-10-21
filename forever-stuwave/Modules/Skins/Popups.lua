-- Forever STUwave: Popups
-- FIRST PASS synthwave PANEL skin for system popups/menus: StaticPopup1..4
-- (feature-detected, StaticPopup1 confirmed present at login on interface
-- 16001), GameMenuFrame (the ESC menu), ReadyCheckFrame/RolePollPopup/the LFG
-- invite popup (all feature-detected; group-invite prompts route through
-- StaticPopup on this client so a dedicated invite frame may not exist), and
-- TutorialFrame (feature-detected; skipped cleanly if this client's help
-- system uses a different frame name). UIDropDownMenu list frames are
-- deliberately out of scope (Blizzard rebuilds them constantly).

local _, FS = ...

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local SkinPanel = FS.Theme.SkinPanel
local SkinButton = FS.Theme.SkinButton
local COLOR_BG = FS.Theme.COLOR_BG
local COLOR_BORDER = FS.Theme.COLOR_BORDER

if not FS.PanelSkins.RequireExport(SkinPanel, "Popups.lua disabled: FS.Theme.SkinPanel missing") then return end

-------------------------------------------------------------------------------
-- Target list
-------------------------------------------------------------------------------

-- Global frame name; StaticPopup1 is confirmed present at login (interface
-- 16001), the rest of this list is feature-detected the same way Panels.lua
-- treats its load-on-demand entries.
local POPUP_FRAMES = {
    { name = "StaticPopup1" },
    { name = "StaticPopup2" },
    { name = "StaticPopup3" },
    { name = "StaticPopup4" },
    -- The Game Menu (Esc): Blizzard's gold inner Border and its gold Header plate are child frames, which
    -- the panel's art sweep never reaches, so they are hidden by name; a taller title band stands in for
    -- the plate (the menu keeps 48 units of padding above its first button for it); `menu` skins its
    -- buttons (below).
    { name = "GameMenuFrame", title = "menu", bandHeight = 30, menu = true,
      hide = { { name = "GameMenuFrame.Border" }, { name = "GameMenuFrame.Header" } } },
    { name = "ReadyCheckFrame" },
    { name = "RolePollPopup" },
    { name = "LFGInvitePopup" },
    { name = "TutorialFrame" },
}

-- StaticPopup button globals follow the <name>ButtonN convention; up to 4
-- buttons per popup on this client.
local STATIC_POPUP_BUTTON_COUNT = 4

-------------------------------------------------------------------------------
-- Game Menu buttons
-------------------------------------------------------------------------------

-- SKIN ONLY. The eight buttons are Blizzard's own and several run secure-adjacent flows (Log Out, Exit Game,
-- Options): they are pooled (MainMenuFrameMixin builds them with CreateFramePool, and InitButtons re-sets
-- the whole list up on every show), their OnClick closures are Blizzard's, and nothing here ever replaces,
-- re-parents, re-anchors or SetScripts one. FS.ButtonSkins.SkinTextButton adds textures and font objects and
-- post-hooks, with its state in weak tables, so a recycled button is never tainted by a field of ours.
--
-- Accent by what the button says: Return to Game is cyan, Log Out and Exit Game pink, the rest violet. The
-- pool hands the same button a different label as the list changes, so the accent is re-read on every
-- InitButtons. A client without the pool falls back to the named GameMenuButton* globals.
local MENU_ACCENT_BY_TEXT = { LOG_OUT = "pink", EXIT_GAME = "pink", RETURN_TO_GAME = "cyan" } -- global string names
local MENU_ACCENT_BY_NAME = { GameMenuButtonLogout = "pink", GameMenuButtonQuit = "pink", GameMenuButtonContinue = "cyan" }
local MENU_BUTTON_NAMES = {
    "GameMenuButtonHelp", "GameMenuButtonWhatsNew", "GameMenuButtonStore", "GameMenuButtonOptions",
    "GameMenuButtonSettings", "GameMenuButtonUIOptions", "GameMenuButtonKeybindings", "GameMenuButtonMacros",
    "GameMenuButtonAddons", "GameMenuButtonEditMode", "GameMenuButtonRatings", "GameMenuButtonLogout",
    "GameMenuButtonQuit", "GameMenuButtonContinue",
}

local function MenuAccent(frame, button, name)
    local text = button.GetText and button:GetText()
    if type(text) == "string" and not (FS.IsSecret and FS.IsSecret(text)) then
        for globalName, accent in pairs(MENU_ACCENT_BY_TEXT) do
            if _G[globalName] == text then return accent end
        end
        -- the logout button reads "Camp" or "Log Out" by situation (GameMenuFrameMixin:GetLogoutText)
        if type(frame.GetLogoutText) == "function" then
            local ok, logout = pcall(frame.GetLogoutText, frame)
            if ok and logout == text then return "pink" end
        end
    end
    return MENU_ACCENT_BY_NAME[name or ""] or "violet"
end

local function SkinMenuButtons(frame)
    local skin = FS.ButtonSkins and FS.ButtonSkins.SkinTextButton
    if not skin then return end
    local seen = {}
    local pool = frame.buttonPool
    if type(pool) == "table" and type(pool.EnumerateActive) == "function" then
        pcall(function()
            for button in pool:EnumerateActive() do
                if not seen[button] then
                    seen[button] = true
                    skin(button, { accent = MenuAccent(frame, button) })
                end
            end
        end)
    end
    for _, name in ipairs(MENU_BUTTON_NAMES) do
        local button = _G[name]
        if type(button) == "table" and not seen[button] then
            seen[button] = true
            skin(button, { accent = MenuAccent(frame, button, name) })
        end
    end
end

local menuHooked = setmetatable({}, { __mode = "k" }) -- frame -> its InitButtons / OnShow hooks are in

-- Re-skins after Blizzard re-sets the list up (InitButtons, from OnShow and on store events), and on show
-- for a client whose menu has no InitButtons.
local function HookMenuButtons(frame)
    if menuHooked[frame] then return end
    menuHooked[frame] = true
    local function again() SkinMenuButtons(frame) end
    if type(hooksecurefunc) == "function" and type(frame.InitButtons) == "function" then
        pcall(hooksecurefunc, frame, "InitButtons", again)
    end
    if type(frame.HookScript) == "function" then pcall(frame.HookScript, frame, "OnShow", again) end
end

-------------------------------------------------------------------------------
-- Skin pass
-------------------------------------------------------------------------------

-- Applies SkinPanel (and, for StaticPopups, SkinButton on each ButtonN) to one
-- entry's frame if present; guarded by frame.fsPopupSkin so the OnShow re-hook
-- and repeated login-time rescans never stack a second set of chrome
-- textures. Missing frames (feature-detected, e.g. no LFG invite popup or a
-- differently-named tutorial system on this client) are skipped silently.
local function SkinOne(entry)
    local frame = _G[entry.name]
    if not frame or frame.fsPopupSkin then return end

    SkinPanel(frame, {
        fillColor = COLOR_BG,
        borderColor = COLOR_BORDER,
        title = entry.title,
        bandHeight = entry.bandHeight,
    })
    frame.fsPopupSkin = true

    if entry.hide then FS.PanelSkins.HideNamed(entry.hide) end
    if entry.menu then
        SkinMenuButtons(frame)
        HookMenuButtons(frame)
    end

    if SkinButton and entry.name:match("^StaticPopup%d$") then
        for i = 1, STATIC_POPUP_BUTTON_COUNT do
            local button = _G[entry.name .. "Button" .. i]
            if button then
                SkinButton(button)
            end
        end
    end
end

-------------------------------------------------------------------------------
-- Init + OnShow re-apply
-------------------------------------------------------------------------------

-- Forward-declared so the driver's onWatch closure below captures this as a
-- local upvalue rather than a not-yet-declared global -- the same ordering
-- trap MicroBars.lua's ReseatBags and IssueReporter.lua's xAtAddonLoaded
-- comments document.
local ApplyAndHook

-- Re-scans on PLAYER_ENTERING_WORLD (covers ReadyCheckFrame/RolePollPopup
-- login timing) and whenever a Blizzard_* module loads (covers a load-on-
-- demand LFG/tutorial frame, if this client has one under a different name).
-- Wired through ApplyAndHook (Apply + HookShowRescan) rather than the plain
-- scan, so a newly-appeared frame also gets its OnShow re-hook.
local ScanAndSkin, _ = FS.PanelSkins.CreateSkinDriver({
    entries = POPUP_FRAMES,
    skinEntry = SkinOne,
    onWatch = function() ApplyAndHook() end,
})

FS.PanelSkins.RegisterInspectFromList("Popups", POPUP_FRAMES, "fsPopupSkin", "name")

-- None of these frames are secure, so none of this is combat-illegal;
-- deferred anyway for consistency with the rest of the addon's Init pattern.
local function Apply()
    ScanAndSkin()
end

-- StaticPopups are a pooled/reused set of fixed frames (StaticPopup1..4);
-- Blizzard re-shows the same frame with new text/buttons rather than creating
-- a fresh one, so a login-time skin covers every future dialog. The OnShow
-- hook below is a cheap belt-and-suspenders re-apply (SkinOne is idempotent
-- via fsPopupSkin) rather than a functional requirement.
local function HookShowRescan()
    for _, entry in ipairs(POPUP_FRAMES) do
        local frame = _G[entry.name]
        if frame and frame.HookScript and not frame.fsPopupShowHook then
            frame:HookScript("OnShow", ScanAndSkin)
            frame.fsPopupShowHook = true
        end
    end
end

ApplyAndHook = function()
    Apply()
    HookShowRescan()
end

FS.PanelSkins.DeferCombat(ApplyAndHook)
