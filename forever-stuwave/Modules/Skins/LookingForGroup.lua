-- Forever STUwave: Looking For Group
-- SKIN ONLY. Blizzard's group finder window (the eye window with the Listing, Browse and Who pages), built
-- by the load-on-demand Blizzard_GroupFinder_VanillaStyle: LFGParentFrame holds LFGListingFrame (the role
-- row, the Dungeons / Quests & Zones / Custom category buttons, Back and List Self), LFGBrowseFrame (the
-- category and activity dropdowns, the results list, Send Message and Group Invite) and LFGWhoListFrame (the
-- search box and the Filter button). The names below are the ones in the 16001 globals dump; the window's
-- source is not among the reference trees, so anything reached through a field key is feature-detected and
-- the rest is found by its global name or its label.
--
-- Its buttons run protected group flows (list yourself, apply, invite, message), so nothing here ever
-- replaces, re-parents, re-anchors, SetScripts or SetAttributes a Blizzard object: the panel chrome is
-- Theme.SkinPanel (art held hidden, our fill, border, title band and the shared X), the text buttons are
-- FS.ButtonSkins.SkinTextButton (textures, font objects and post-hooks), and the rest is Hide() on the
-- art of the three pages, re-hidden by PanelSkins.HideNamed when a page is shown again.
--
-- The Browse page's results scroll bar wears the shared scroll bar skin (FS.ScrollBarSkins). The Listing page's
-- activity list bar (LFGListingFrameActivityViewScrollBar) is left stock on purpose: ElvUI's TBC skin of this
-- window has a skin on that one commented out as confirmed to taint the group finder, and nothing here can show
-- ours would not.
--
-- NOT skinned here, because no shared skin for them exists yet (tracked by the UI audit): the Category,
-- Filter by activity and role dropdown buttons, the Who page's search box, the refresh, options and search icon
-- buttons, the role buttons' check boxes, and the three side tabs. They keep their Blizzard look, as do the
-- role, tab and category icons.

local _, FS = ...

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local SkinPanel = FS.Theme.SkinPanel
local COLOR_BG = FS.Theme.COLOR_BG
local COLOR_BORDER = FS.Theme.COLOR_BORDER

if not FS.PanelSkins.RequireExport(SkinPanel, "LookingForGroup.lua disabled: FS.Theme.SkinPanel missing") then return end

-------------------------------------------------------------------------------
-- Targets
-------------------------------------------------------------------------------

local WINDOW = "LFGParentFrame"
local PAGES = { "LFGListingFrame", "LFGBrowseFrame", "LFGWhoListFrame" }

-- The art of the window that sits OVER the panel fill: the pages' own backgrounds (opaque, they would hide our
-- fill), the Browse page's silhouette, the role row's band, the Listing divider bars, the round portraits and
-- the centred "Looking For Group" titles (the title band carries ours). Each page also has Normal, Hover,
-- Pressed, Disabled and Active textures: those are left alone (they are not chrome of the window, and the
-- side tab icons may be among them), as is every child frame.
local PAGE_CHROME = {
    "LFGParentFramePortrait",
    "LFGListingFrameBg", "LFGBrowseFrameBg", "LFGWhoListFrameBg",
    "LFGBrowseFrameBackgroundArt",
    "LFGListingFrameRoleBackground",
    "LFGListingFrameActivityViewBarMiddle",
    "LFGListingFramePortrait", "LFGBrowseFramePortrait", "LFGWhoListFramePortrait",
    "LFGListingFrameTitleText", "LFGBrowseFrameTitleText", "LFGWhoListFrameTitleText",
}

-- Labelled buttons that become the shared STUwave text button. Cyan for what commits (list yourself,
-- invite, accept), pink for what declines, violet for the rest.
local TEXT_BUTTONS = {
    { name = "LFGBrowseFrameSendMessageButton" },
    { name = "LFGBrowseFrameGroupInviteButton", accent = "cyan" },
    { name = "LFGListingFrameBackButton" },
    { name = "LFGListingFramePostButton", accent = "cyan" },
    { name = "LFGListingFrameGroupRoleButtonsInitiateRolePoll" },
    { name = "LFGInvitePopupAcceptButton", accent = "cyan" },
    { name = "LFGInvitePopupDeclineButton", accent = "pink" },
}

-------------------------------------------------------------------------------
-- Pieces
-------------------------------------------------------------------------------

local function SkinWindow()
    local frame = _G[WINDOW]
    if not frame or frame.fsLFGSkin then return end
    SkinPanel(frame, {
        fillColor = COLOR_BG,
        borderColor = COLOR_BORDER,
        title = "lfg",
    })
    frame.fsLFGSkin = true
end

-- Hides the window's own art by name. A name that is not there on this client is skipped quietly (the page
-- art differs between the classic and the modern style); PanelSkins.HideNamed re-hides it when its page is shown.
local function HidePageChrome()
    local present = {}
    for _, name in ipairs(PAGE_CHROME) do
        if _G[name] then present[#present + 1] = { name = name } end
    end
    if #present > 0 then FS.PanelSkins.HideNamed(present) end
end

local function SkinTextButtons()
    local skin = FS.ButtonSkins and FS.ButtonSkins.SkinTextButton
    if not skin then return end
    for _, entry in ipairs(TEXT_BUTTONS) do
        local button = _G[entry.name]
        if button then skin(button, { accent = entry.accent }) end
    end
end

-- The Browse results list's scroll bar, found by name and told by shape, so an old style slider (no Track) keeps
-- its Blizzard look. The shared skin is idempotent; asking first keeps a rescan from handing it the bar again.
local function SkinResultsScrollBar()
    local skins = FS.ScrollBarSkins
    local bar = _G.LFGBrowseFrameScrollBar
    if not (skins and skins.IsScrollBar and skins.Skin and skins.IsScrollBar(bar)) then return end
    if not (skins.Parts and skins.Parts(bar)) then skins.Skin(bar) end
end

-- The Who page's Filter button has no global name and its key is not known, so it is found by what it says:
-- a Button whose label is the client's FILTER string, among the page's children or theirs.
local function LabelOf(button)
    local text = type(button.GetText) == "function" and button:GetText() or nil
    if (text == nil or text == "") and type(button.Text) == "table" and type(button.Text.GetText) == "function" then
        text = button.Text:GetText()
    end
    if FS.IsSecret and FS.IsSecret(text) then return nil end
    return text
end

local function IsButton(obj)
    return type(obj) == "table" and type(obj.GetObjectType) == "function" and obj:GetObjectType() == "Button"
end

local function FindFilterButton()
    local page = _G.LFGWhoListFrame
    local label = _G.FILTER
    if not (page and type(page.GetChildren) == "function" and type(label) == "string") then return nil end
    local queue, found = { page }, nil
    for _ = 1, 2 do
        local nextQueue = {}
        for _, parent in ipairs(queue) do
            if type(parent.GetChildren) == "function" then
                for _, child in ipairs({ parent:GetChildren() }) do
                    if IsButton(child) and LabelOf(child) == label then found = found or child end
                    nextQueue[#nextQueue + 1] = child
                end
            end
        end
        if found then return found end
        queue = nextQueue
    end
    return nil
end

local function SkinFilterButton()
    local skin = FS.ButtonSkins and FS.ButtonSkins.SkinTextButton
    local button = skin and FindFilterButton()
    if button then skin(button, {}) end
end

-- The category buttons (art with a label) get the ring and halo of every skinned button; their art, cover,
-- label and hover highlight stay Blizzard's. They are built as the Listing page needs them, so they are
-- caught both as they are added and when already there. State lives in a weak table, not on the button.
local ringed = setmetatable({}, { __mode = "k" })

local function SkinCategoryButton(button)
    if type(button) ~= "table" or ringed[button] or type(button.CreateTexture) ~= "function" then return end
    ringed[button] = true
    FS.Theme.SkinButton(button, { borderColor = COLOR_BORDER })
end

local function SkinCategoryButtons()
    local view = _G.LFGListingFrameCategoryView
    local buttons = type(view) == "table" and view.CategoryButtons
    if type(buttons) ~= "table" then return end
    for _, button in pairs(buttons) do SkinCategoryButton(button) end
end

local categoryHooked = false
local function HookCategoryButtons()
    if categoryHooked or type(hooksecurefunc) ~= "function" or type(_G.LFGListingCategorySelection_AddButton) ~= "function" then
        return
    end
    categoryHooked = true
    hooksecurefunc("LFGListingCategorySelection_AddButton", function(frame, index)
        local buttons = type(frame) == "table" and frame.CategoryButtons
        if type(buttons) == "table" then pcall(SkinCategoryButton, buttons[index]) end
    end)
end

-------------------------------------------------------------------------------
-- Skin pass
-------------------------------------------------------------------------------

local ScanAndSkin

-- Blizzard re-asserts page art and builds buttons as a page is shown, so each page and the window rescan on
-- show (every piece above is idempotent). One hook per frame, whichever scan installs it.
local function HookShow()
    local frame = _G[WINDOW]
    if frame then FS.PanelSkins.HookShowOnce(frame, "fsLFGShowHook", ScanAndSkin) end
    for _, name in ipairs(PAGES) do
        local page = _G[name]
        if page then FS.PanelSkins.HookShowOnce(page, "fsLFGShowHook", ScanAndSkin) end
    end
end

local function MatchesGroupFinder(loadedAddonName)
    return loadedAddonName ~= nil and loadedAddonName:find("^Blizzard_GroupFinder") ~= nil
end

local function Scan()
    SkinWindow()
    HidePageChrome()
    SkinTextButtons()
    SkinResultsScrollBar()
    SkinFilterButton()
    HookCategoryButtons()
    SkinCategoryButtons()
    HookShow()
end

ScanAndSkin = FS.PanelSkins.CreateSkinDriver({
    entries = { WINDOW },
    skinEntry = Scan,
    matchesAddon = MatchesGroupFinder,
})

FS.PanelSkins.RegisterInspect("LookingForGroup", { { name = WINDOW, guard = "fsLFGSkin" } })

-- None of these frames are secure, so none of this is combat-illegal; deferred anyway for consistency with
-- the rest of the addon's Init pattern.
FS.PanelSkins.DeferCombat(ScanAndSkin)
