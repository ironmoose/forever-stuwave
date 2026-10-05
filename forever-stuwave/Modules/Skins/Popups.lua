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
    { name = "GameMenuFrame" },
    { name = "ReadyCheckFrame" },
    { name = "RolePollPopup" },
    { name = "LFGInvitePopup" },
    { name = "TutorialFrame" },
}

-- StaticPopup button globals follow the <name>ButtonN convention; up to 4
-- buttons per popup on this client.
local STATIC_POPUP_BUTTON_COUNT = 4

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
    })
    frame.fsPopupSkin = true

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

FS.PanelSkins.RegisterReconFromList("Popups", POPUP_FRAMES, "fsPopupSkin", "name")

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
