-- Forever Synthwave: Menus
-- FIRST PASS synthwave chrome for every Blizzard dropdown/context menu on this
-- client (interface 16001, the Forever beta client): the chat term-bar's
-- Say/Party/Raid/etc chat-type selector, unit right-click context menus, and
-- everything else, on BOTH menu systems this client ships:
--   - the modern `Menu`/`MenuUtil` system (globals.txt:32749/32760), hooked at
--     its shared manager entry points (below) so every caller that routes
--     through it is caught generically -- the chat term-bar's Say/Party/Raid
--     selector is CONFIRMED to be one of them: `ChatFrameMenuButtonMixin`
--     (retail ~/workspaces/reference/wow-ui-source-live-12.1.0/
--     Interface/AddOns/Blizzard_ChatFrameBase/Mainline/ChatFrameMenuButton.lua,
--     ~line 155/161's self:GenerateMenu()/self:IsMenuOpen()) is a
--     DropdownButtonMixin descendant driving `Menu`, not UIDropDownMenu.
--   - the legacy `UIDropDownMenu` system (DropDownList1..3, confirmed present
--     at login, globals.txt:14841/14854/14867).
-- Unit right-click context menus (`CompactUnitFrame_OpenMenu`, globals.txt:
-- 12716) and every other caller (ChatTabs.lua's right-click, which this
-- addon's own comment already notes has no dedicated `*TabDropDown` global and
-- delegates to `FCF_Tab_OnClick`) are NOT individually hooked for chrome --
-- whichever of the two systems above a given caller resolves to, the hooks
-- below catch it, so the chrome never needs to know or enumerate its callers.
-- The one per-menu exception is InitUnitMenuTitles, which registers
-- `Menu.ModifyMenu` callbacks on the MENU_UNIT_* tags to show a unit menu's
-- title as the full first + surname.
--
-- TAINT: every hook below is hooksecurefunc-only, except InitUnitMenuTitles'
-- Menu.ModifyMenu callback, which only enumerates element descriptions and
-- calls AddInitializer, and the initializer, which only calls SetText/
-- SetTextToFit on the title FontString. Every texture we create
-- (2026-09-24: now built on our own plain child chrome frame, `chromeByMenu`
-- below -- see ApplyMenuChrome's own comment for why direct `frame:CreateTexture`
-- calls on the menu frame itself throw on this client) is our own, never a
-- direct region of any Blizzard menu frame, and never touching a Blizzard
-- region's SetPoint/SetSize/SetParent or any secure attribute. Spot-checked for secure
-- templates rather than assumed: `Menu.xml:3`'s `MenuTemplateBase` inherits
-- `ResizeLayoutFrame`, not any `Secure*Template`, and no `SetForbidden` call
-- exists anywhere in `Menu.xml`/`Mainline/MenuTemplates.xml` -- the menu
-- content frame itself is a plain Frame/Button family. `CompactUnitFrame_
-- OpenMenu`'s protected actions (promote, kick, ...) are wired into individual
-- menu ITEM responders by Blizzard's own code when a row is clicked; this file
-- never touches item rows or their responders, only the menu frame's own
-- background chrome and the title text noted above.
--
-- TEXT/FONT: modern-system item text is now handled (this pass). Legacy
-- DropDownList text is still deliberately left alone, matching Popups.lua's
-- own SkinButton calls (which never pass font args). Investigated, not
-- guessed: legacy `DropDownListNButtonNNormalText` (a per-BUTTON FontString
-- instance, confirmed globals.txt:14851/14864/14877) gets its actual
-- font/color from `UIDropDownMenuButtonTemplate`'s
-- `<NormalFont style="GameFontHighlightSmallLeft"/>` /
-- `<DisabledFont style="GameFontDisableSmallLeft"/>` (retail
-- Blizzard_SharedXML/Mainline/UIDropDownMenuTemplates.xml:112-114) -- a real
-- SHARED font-object pair, the same mechanism ObjectiveTrackerHeaderFont/
-- ObjectiveTrackerLineFont use elsewhere in this addon, and it has no
-- separate shortcut-column FontString to target either. `GameFontHighlightSmallLeft`/
-- `GameFontDisableSmallLeft` are generic, addon-wide-shared font objects
-- (unlike the tracker's own Objective-Tracker-scoped fonts), so retinting
-- them would repaint unrelated UI far outside menus. Left alone.
--
-- The modern Menu system's row FontString (`parentKey="Text"`,
-- Mainline/MenuTemplates.lua's `ButtonFinalInitializer` ->
-- `RecurseSetupFontString`) instead gets its color from a plain per-call
-- `SetTextColor`, not a shared font-object link, so it IS safe to retint: item
-- text is remapped from Blizzard's `NORMAL_FONT_COLOR` gold to
-- `Theme.COLOR_MENU_TEXT` cyan by walking each menu-item frame's FontString
-- regions and matching on exact color value (not field names). Native menu
-- fonts, including shortcut text, are left intact. Full rationale in
-- CLAUDE.md's Menus.lua entry.
--
-- UNVALIDATED in-game: no /fstack or visual check of the color pass done
-- yet, same as the rest of this file.

local _, FS = ...

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local SkinPanel = FS.Theme.SkinPanel
local COLOR_BG = FS.Theme.COLOR_BG
local COLOR_BORDER = FS.Theme.COLOR_BORDER
local COLOR_MENU_TEXT = FS.Theme.COLOR_MENU_TEXT

if not FS.PanelSkins.RequireExport(SkinPanel, "Menus.lua disabled: FS.Theme.SkinPanel missing") then return end

FS.Menus = FS.Menus or {}

-------------------------------------------------------------------------------
-- Shared chrome (both menu systems land here)
-------------------------------------------------------------------------------

-- Diagnostics-only counters, read back by FS.Menus.GetDiagnostics() below.
local skinnedMenuCount = 0
local legacyListsHooked = 0
local modernHookInstalled = false

-- Full rationale in CLAUDE.md; short pointers only below.
-- CONFIRMED against the live client's own error (2026-09-24 fix): every menu
-- frame the modern `Menu`/`MenuUtil` system hands out is COMPOSITOR-MANAGED --
-- `ConfigureMetatable` (retail ~/workspaces/reference/wow-ui-source-live-
-- 12.1.0/Interface/AddOns/Blizzard_Menu/Compositor.lua ~239-287) installs a
-- metatable whose `__index` (Compositor.lua:254-283) raises
-- `assertsafe(false, "Use of function '%s' is disallowed. (Index)")` for any
-- key in `frameDisallowedFunctions` (built via `tInvert{...}` ~177-185):
-- `CreateTexture`/`CreateMaskTexture`/`CreateFontString`/`CreateAnimationGroup`/
-- `CreateLine`/`SetForbidden`. Calling `frame:CreateTexture(...)` directly on a
-- menu frame (the OLD `ApplyMenuChrome`, via `Theme.AddSliceTexture`) therefore
-- always throws on this client -- that IS the live in-game bug this rewrite
-- fixes (`Use of function 'CreateTexture' is disallowed. (Index)`, thrown from
-- Compositor.lua:256, called via Theme.lua:170 AddSliceTexture <- Theme.lua:863
-- SkinPanel <- this file's old ApplyMenuChrome). `SetFrameLevel`/`Hide` are NOT
-- in `frameDisallowedFunctions` and remain legal to call on a menu frame.
--
-- The SAME metatable's `__newindex = values` (Compositor.lua:286) redirects
-- every NEW field write on the frame into a per-acquire local `values` table
-- (declared fresh inside `ConfigureMetatable`, line 250) instead of onto the
-- frame itself -- and `ConfigureMetatable` re-runs on every attach/acquire
-- (Compositor.lua:313/333/364), so that `values` table is a brand-new, empty
-- table each time. A guard field written directly on the menu frame (the OLD
-- `frame.fsMenuSkin`) was therefore never actually surviving reuse the way the
-- old comment here claimed -- it silently discarded into that throwaway table
-- on every acquire, it just never got exercised enough in testing to notice
-- before the CreateTexture throw started masking the whole skin pass (chrome
-- AND the text-styling pass that used to run after it -- see the pcall
-- isolation in InitModernMenus below for why that stopped happening too).
--
-- Fix (ElvUI's pattern, confirmed via ~/workspaces/reference/ElvUI/ElvUI/
-- Game/Mainline/Skins/Menu.lua ~10-25's `SkinFrame`, and
-- Game/Shared/General/Toolkit.lua's `CreateBackdrop`/`OffsetFrameLevel`/
-- `BackdropFrameLower`): never call Create*/store state directly ON a
-- compositor-managed frame. Build a plain CHILD frame via the GLOBAL
-- `CreateFrame` function (a free function, not a method call on the menu
-- frame -- the compositor metatable never intercepts it, and the child frame
-- it returns is a plain Frame with no metatable of its own, so nothing about
-- it is subject to `frameDisallowedFunctions` either), and key persistent
-- state off a table keyed BY the menu frame (`chromeByMenu` below) rather than
-- a field ON it, so a `values`-table discard on the next acquire can't erase
-- it the way it erased `frame.fsMenuSkin`. Weak-keyed (`{ __mode = "k" }`) so
-- a menu frame that stops existing (never actually happens for a pooled
-- frame, but matches ElvUI's own `backdrops` table discipline) doesn't pin an
-- entry here forever.
local chromeByMenu = setmetatable({}, { __mode = "k" })

-- Re-sweeps EVERY call, not cached: the modern menu system's pooled
-- compositor background isn't guaranteed to be the same Lua object across
-- opens, so a cached hide list (Theme.StripBlizzardChrome's own idiom) can't
-- be trusted here the way it can for a fixed, always-existing frame. No
-- `.fsMenuChrome`-tag check needed any more (2026-09-24): our own chrome
-- textures now live on `chromeByMenu[frame]`, a SEPARATE sibling frame, never
-- as a direct Texture region of `frame` itself, so every direct Texture
-- region `frame:GetRegions()` returns here is guaranteed to be Blizzard's.
local function HideForeignTextures(frame)
    for _, region in ipairs({ frame:GetRegions() }) do
        if region.GetObjectType and region:GetObjectType() == "Texture" then
            if region.Hide then region:Hide() end
        end
    end
end

-- Full rationale in CLAUDE.md; short pointers only below.
-- Builds a plain child chrome frame ONCE per menu frame (looked up in
-- `chromeByMenu` above), re-levels it on EVERY call since frame level can
-- drift across reacquires (mirrors ElvUI's own `OffsetFrameLevel` call inside
-- `SkinFrame`, which re-asserts unconditionally every call rather than only
-- on first build), then re-sweeps foreign textures same as before.
-- `strip = false`: our chrome frame is our own plain frame with nothing
-- Blizzard-owned on it to strip -- `Theme.StripBlizzardChrome`/
-- `Theme.SkinCloseButton` would have nothing to find on it regardless (see
-- CLAUDE.md's Menus.lua entry for the confirmed CloseButton-is-always-nil
-- citation chain on both menu template families, unchanged by this rewrite).
-- `opts.scanline = false`: menus are small popups: the CRT scanline scrim
-- this addon's other panels use reads as noise at this size, not texture.
-- No `opts.title`: menus carry no title band in this addon's design.
-- `chromeFrame:SetAllPoints(frame)` (zero inset), matching how chrome
-- previously sat flush with the menu frame's own edges when it was drawn
-- directly on `frame` -- SkinPanel's AddSliceTexture fill/glow/border anchor
-- TOPLEFT/BOTTOMRIGHT to ITS OWN frame's edges (Theme.lua:178-179), so
-- `chromeFrame` re-stretching together with `frame` via SetAllPoints carries
-- that same free per-resize re-stretch behavior forward with no extra hook.
-- Frame level: `chromeFrame` is pinned to `frame:GetFrameLevel()` (no `-1`)
-- because item-row children are EXPLICITLY raised well above the menu frame's
-- own level -- `childFrame:SetFrameLevel(menuFrame:GetFrameLevel() + 20)`, Menu.lua:1188 -- not an engine default.
local function ApplyMenuChrome(frame)
    if not frame then return end

    local chromeFrame = chromeByMenu[frame]
    if not chromeFrame then
        chromeFrame = CreateFrame("Frame", nil, frame)
        chromeFrame:SetAllPoints(frame)
        SkinPanel(chromeFrame, {
            fillColor = COLOR_BG,
            borderColor = COLOR_BORDER,
            scanline = false,
            strip = false,
        })
        chromeByMenu[frame] = chromeFrame
        skinnedMenuCount = skinnedMenuCount + 1

        -- Recon-only marker (see Init below / PanelSkins.RegisterRecon): a
        -- plain field write on `frame` is silently discarded by the modern
        -- system's compositor `__newindex` (see the `chromeByMenu` comment
        -- above) -- a harmless no-op there -- but DOES stick on the legacy
        -- DropDownList1..N frames, which are real, non-compositor-managed
        -- frames (confirmed: not part of Menu.GetManager()'s pool), so
        -- `/fsrecon skins` can still read it back for the legacy path. Not
        -- read by any logic in this file, unlike the old `frame.fsMenuSkin`
        -- guard -- `chromeByMenu[frame]` above is the sole guard now.
        frame.fsMenuChromeBuilt = true
    end

    chromeFrame:SetFrameLevel(frame:GetFrameLevel())
    HideForeignTextures(frame)
end

-------------------------------------------------------------------------------
-- Legacy UIDropDownMenu (DropDownList1..N)
-------------------------------------------------------------------------------

-- N = UIDROPDOWNMENU_MAXLEVELS if present (confirmed present, a plain number,
-- globals.txt:50516) and sane, else 3 -- all three DropDownList1/2/3 are
-- confirmed present in the 16001 globals dump regardless (globals.txt:
-- 14841/14854/14867), so 3 is a safe floor even if the constant were ever
-- missing or malformed.
local function LegacyDropDownCount()
    local n = tonumber(UIDROPDOWNMENU_MAXLEVELS)
    if not n or n < 1 then n = 3 end
    return n
end

-- DropDownListNBackdrop (widget:Frame, inherits DialogBorderDarkTemplate) and
-- DropDownListNMenuBackdrop (widget:Frame, inherits TooltipBackdropTemplate)
-- are the list's real chrome -- confirmed via retail Blizzard_SharedXML/
-- Mainline/UIDropDownMenuTemplates.xml's UIDropDownListTemplate
-- (`$parentBackdrop` parentKey="Border", `$parentMenuBackdrop`), and by exact
-- name in the 16001 dump (globals.txt:14842/14853, mirrored per list at
-- :14855/14866 and :14868/14879). Neither is a direct Texture region of
-- DropDownListN itself (UIDropDownListTemplate declares no <Layers> of its
-- own -- both are separate child FRAMES), so ApplyMenuChrome's
-- HideForeignTextures sweep above can't reach them; they need their own
-- explicit Hide() here. Re-hidden on EVERY OnShow rather than once-and-cached:
-- `UIDropDownMenu_OnShow` re-initializes list content on every open (a
-- different dropdown every time this pooled frame is reused), and nothing in
-- the retail source rules out it re-Show()ing one or both of these depending
-- on the new content's displayMode -- Hide() is idempotent, so doing it
-- unconditionally on every show is cheap and safe either way.
local function HideLegacyBackdrops(index)
    local backdrop = _G["DropDownList" .. index .. "Backdrop"]
    local menuBackdrop = _G["DropDownList" .. index .. "MenuBackdrop"]
    if backdrop and backdrop.Hide then backdrop:Hide() end
    if menuBackdrop and menuBackdrop.Hide then menuBackdrop:Hide() end
end

local function SkinLegacyList(frame, index)
    HideLegacyBackdrops(index)
    ApplyMenuChrome(frame)
end

-- Hooked directly on each DropDownListN's own OnShow rather than
-- ToggleDropDownMenu (confirmed present, globals.txt:49927) or
-- UIDropDownMenu_Initialize (confirmed present, globals.txt:50553):
-- ToggleDropDownMenu is only ONE of several internal paths that can end up
-- showing a list, UIDropDownMenu_Initialize is the CONTENT builder rather than
-- a show-time hook, and this addon has no reliable way to enumerate every
-- caller. The list frame's own OnShow fires exactly once per real display
-- regardless of which internal path triggered it (UIDropDownListTemplate's own
-- `<OnShow>UIDropDownMenu_OnShow(self)</OnShow>` script), so hooking it
-- directly is simpler and strictly more reliable than chasing every trigger.
local function InitLegacyMenus(count)
    for i = 1, count do
        local frame = _G["DropDownList" .. i]
        if frame and frame.HookScript and not frame.fsMenuShowHooked then
            frame.fsMenuShowHooked = true
            frame:HookScript("OnShow", function() SkinLegacyList(frame, i) end)
            legacyListsHooked = legacyListsHooked + 1
            if frame:IsShown() then SkinLegacyList(frame, i) end
        end
    end
end

-------------------------------------------------------------------------------
-- Modern Menu system (Menu.GetManager())
-------------------------------------------------------------------------------

-- Full rationale in CLAUDE.md; short pointers only below.
-- Compares a live FontString color against a Blizzard global ColorMixin
-- (NORMAL_FONT_COLOR) with float tolerance, since GetTextColor() readback
-- isn't guaranteed to compare == by table identity.
local function ColorMatches(r, g, b, blizzColor)
    if not blizzColor then return false end
    local br, bg, bb = blizzColor:GetRGB()
    return math.abs(r - br) < 0.01 and math.abs(g - bg) < 0.01 and math.abs(b - bb) < 0.01
end

-- Restyles one menu-item FontString region, generic over field name (button.
-- fontString / .Text / an anonymous AttachFontString region -- see CLAUDE.md).
-- Re-run on every menu open, never cached: pooled/reused frames, different
-- content per open.
local function StyleMenuFontString(fontString)
    if not fontString or not fontString.GetTextColor then return end

    -- Only remap Blizzard's plain "enabled" gold; HIGHLIGHT/DISABLED colors
    -- are left exactly as Blizzard set them -- see CLAUDE.md.
    local r, g, b, a = fontString:GetTextColor()
    if ColorMatches(r, g, b, NORMAL_FONT_COLOR) then
        fontString:SetTextColor(COLOR_MENU_TEXT[1], COLOR_MENU_TEXT[2], COLOR_MENU_TEXT[3], a or 1)
    end
end

-- Walks one menu-item element frame's own FontString regions plus one level
-- of its children's regions -- bounded, not a deep recursive walk; see
-- CLAUDE.md.
local function StyleMenuItemFrame(child)
    if not child or not child.GetRegions then return end
    for _, region in ipairs({ child:GetRegions() }) do
        if region.GetObjectType and region:GetObjectType() == "FontString" then
            StyleMenuFontString(region)
        end
    end
    if child.GetChildren then
        for _, grandchild in ipairs({ child:GetChildren() }) do
            if grandchild.GetRegions then
                for _, region in ipairs({ grandchild:GetRegions() }) do
                    if region.GetObjectType and region:GetObjectType() == "FontString" then
                        StyleMenuFontString(region)
                    end
                end
            end
        end
    end
end

-- Walks the open menu frame's own item children -- real, persistent child
-- frames (not a virtualized ScrollBox-recycled row pool); see CLAUDE.md.
local function ApplyMenuItemTextStyle(frame)
    if not frame or not frame.GetChildren then return end
    for _, child in ipairs({ frame:GetChildren() }) do
        StyleMenuItemFrame(child)
    end
end

-- `Menu.GetManager()` (Menu.lua:2584) returns a cached proxy created once at
-- file load (`local menuManagerProxy = CreateMenuManager()`, Menu.lua:2582)
-- and stable across the whole session -- same pattern ElvUI hooks once at
-- Blizzard_Menu ADDON_LOADED, though this addon defers to PLAYER_REGEN_ENABLED
-- instead (see Init below) since Blizzard_Menu is confirmed always-loaded, not
-- load-on-demand.
-- Once-per-session dedupe flags for SkinCurrentMenu's two pcall'd stages,
-- local to this file per FS.LogDegradeOnce's own contract (ErrorLog.lua:108:
-- it persists/prints every call, it does NOT dedupe by key itself -- callers
-- own their guard). These two flags gate ONLY the FS.LogDegradeOnce call
-- below, unlike FrameHelpers.lua's `curveHideBroken`/`warnedNoCaretFullHide`
-- pair (FrameHelpers.lua:276-321), where the latched boolean gates BOTH the
-- log AND the retry -- once `curveHideBroken` is true, every later call
-- skips the pcall'd curve/percent path entirely and falls straight to the
-- cheap cur/max fallback. Here, `pcall(ApplyMenuChrome, frame)` and
-- `pcall(ApplyMenuItemTextStyle, frame)` below are retried IN FULL on every
-- subsequent menu open regardless of these flags -- there is no substituted
-- degraded path to skip to, just the same risky call run again. That is the
-- right tradeoff for this call site, not an oversight: `UpdateCaretFull`'s
-- curve path is a per-frame-per-tick hot path (its power-bar caller,
-- `UpdatePowerValue`, fires on every `UNIT_POWER_UPDATE`), so repeatedly
-- pcall'ing a known-broken API call there is real, recurring cost.
-- `ApplyMenuChrome`/`ApplyMenuItemTextStyle` instead run once per menu
-- OPEN -- a low-frequency, user-driven event -- so retrying a possibly
-- transient failure every open is cheap and gives the code a chance to
-- self-heal if whatever caused the one-off throw wasn't structural; jumping
-- straight to a permanent degraded state the way `curveHideBroken` does
-- would trade away that self-heal for savings that don't exist here.
local loggedMenuChromeFailure = false
local loggedMenuTextFailure = false

local function InitModernMenus()
    if type(Menu) ~= "table" or type(Menu.GetManager) ~= "function" then return end
    local manager = Menu.GetManager()
    if not manager or type(manager.GetOpenMenu) ~= "function" then return end

    -- GetOpenMenu() (private MenuManagerMixin:GetOpenMenu, Menu.lua:1917;
    -- proxy-exposed MenuManagerProxyMixin:GetOpenMenu, Menu.lua:2539) is the
    -- one CONFIRMED way to get the just-acquired menu frame from inside a
    -- hook. Both hooksecurefunc's own call args AND
    -- menuDescription:AddMenuAcquiredCallback's callback args are of
    -- UNVERIFIED shape (the evidence gathered for this file never pinned down
    -- AddMenuAcquiredCallback's parameter list), so every path below
    -- deliberately ignores whatever arguments it is handed and re-derives the
    -- frame through this one confirmed accessor instead of guessing at them.
    --
    -- Chrome and text-styling are pcall-ISOLATED from each other (2026-09-24
    -- fix): before this, a throw inside ApplyMenuChrome (the live
    -- disallowed-`CreateTexture` bug -- see ApplyMenuChrome's own comment
    -- above) propagated straight out of SkinCurrentMenu and aborted
    -- ApplyMenuItemTextStyle too, even though the two passes are otherwise
    -- independent -- the chat menu's item text never got restyled either, not
    -- just its chrome. Each stage now fails on its own: a chrome failure
    -- degrades this session to unstyled-but-legible Blizzard chrome, a text
    -- failure degrades to unstyled-but-legible Blizzard gold text, and
    -- neither can take the other down with it.
    local function SkinCurrentMenu()
        local frame = manager:GetOpenMenu()
        if not frame then return end

        local chromeOk, chromeErr = pcall(ApplyMenuChrome, frame)
        if not chromeOk and not loggedMenuChromeFailure then
            loggedMenuChromeFailure = true
            FS.LogDegradeOnce("menu_chrome_failure",
                "|cffff4488ForeverSynthwave|r: menu chrome build failed (" .. tostring(chromeErr) ..
                "), degrading to unstyled Blizzard chrome for this session")
        end

        local textOk, textErr = pcall(ApplyMenuItemTextStyle, frame)
        if not textOk and not loggedMenuTextFailure then
            loggedMenuTextFailure = true
            FS.LogDegradeOnce("menu_text_failure",
                "|cffff4488ForeverSynthwave|r: menu item text styling failed (" .. tostring(textErr) ..
                "), degrading to unstyled Blizzard item text for this session")
        end
    end

    -- menuDescription:AddMenuAcquiredCallback (SharedMenuPropertiesMixin,
    -- Menu.lua:180; proxy-exposed per RootMenuDescriptionProxyMixin's Funcs
    -- list ~line 557) fires for every submenu a given root menu acquires, so
    -- registering it here is what catches SUBMENUS (e.g. a unit-frame context
    -- menu's "Set Focus" flyout) with the SAME skin function as the root --
    -- ApplyMenuChrome is written generically over "a menu frame" for exactly
    -- this reuse, matching both root and nested menus with one function.
    -- Registered fresh on every OpenMenu/OpenContextMenu call rather than
    -- guarded by a per-description flag: each call is expected to hand a
    -- newly-built root menuDescription (the caller's own generator function
    -- constructs one per invocation, e.g. a fresh right-click menu every
    -- right-click), not a reused object, so there is no repeat-registration
    -- risk to guard against here.
    local function OnMenuOpened(menuDescription)
        if menuDescription and type(menuDescription.AddMenuAcquiredCallback) == "function" then
            menuDescription:AddMenuAcquiredCallback(SkinCurrentMenu)
        end
        SkinCurrentMenu()
    end

    -- MenuManagerMixin:OpenMenu(ownerRegion, menuDescription, anchor)
    -- (Menu.lua:2496; proxy wrapper Menu.lua:2561) and :OpenContextMenu
    -- (ownerRegion, menuDescription) (Menu.lua:2510; proxy wrapper Menu.lua:
    -- 2568) are the two entry points every caller funnels through, including
    -- the chat term-bar's Say/Party/Raid selector (ChatFrameMenuButtonMixin,
    -- see file header) and unit right-click menus -- hooking these two catches
    -- every modern-system menu generically, with no per-caller wiring needed.
    if type(manager.OpenMenu) == "function" then
        hooksecurefunc(manager, "OpenMenu", function(_, _, menuDescription)
            OnMenuOpened(menuDescription)
        end)
        modernHookInstalled = true
    end

    if type(manager.OpenContextMenu) == "function" then
        hooksecurefunc(manager, "OpenContextMenu", function(_, _, menuDescription)
            OnMenuOpened(menuDescription)
        end)
        modernHookInstalled = true
    end
end

-- UnitPopup titles a menu with UnitNameUnmodified, which drops this server's
-- surname. Each tag below is "MENU_UNIT_" .. a UnitPopupMenus key that can
-- carry a real unit (Blizzard_UnitPopupShared/UnitPopupShared.lua:106).
local UNIT_MENU_TAGS = {
    "MENU_UNIT_SELF", "MENU_UNIT_PARTY", "MENU_UNIT_PLAYER",
    "MENU_UNIT_RAID_PLAYER", "MENU_UNIT_TARGET", "MENU_UNIT_FOCUS",
    "MENU_UNIT_FRIEND", "MENU_UNIT_ENEMY_PLAYER", "MENU_UNIT_RAID",
}

local loggedUnitTitleFailure = false

-- Logs only the first failure (LogDegradeOnce does not dedupe by key); every
-- menu open still retries, so a transient throw self-heals.
local function LogUnitTitleFailure(err)
    if loggedUnitTitleFailure then return end
    loggedUnitTitleFailure = true
    FS.LogDegradeOnce("menus-unit-title",
        "|cffff4488ForeverSynthwave|r: unit menu full-name title failed (" ..
        tostring(err) .. "), leaving Blizzard's title for that open")
end

-- Runs from the title element's initializer, after Blizzard's own. Rewrites
-- only a title that is exactly the bare name and whose full name extends it,
-- so non-name titles (e.g. the raid-marker menu) are never touched.
local function ApplyFullNameTitle(frame, contextData)
    local unit = contextData.unit
    local name = contextData.name
    if FS.IsSecret(unit) or type(unit) ~= "string" then return end
    if FS.IsSecret(name) or type(name) ~= "string" then return end
    local fontString = frame.fontString
    if not fontString or not FS.GetFullUnitName then return end

    local full = FS.GetFullUnitName(unit)
    if FS.IsSecret(full) or type(full) ~= "string" then return end
    local text = fontString:GetText()
    if FS.IsSecret(text) then return end
    if type(text) ~= "string" or text == "" or text ~= name or text == full then return end
    if full:sub(1, #text + 1) ~= text .. " " then return end

    if type(fontString.SetTextToFit) == "function" then
        fontString:SetTextToFit(full)
    else
        fontString:SetText(full)
    end
end

local function InitUnitMenuTitles()
    if type(Menu) ~= "table" or type(Menu.ModifyMenu) ~= "function" then return end

    -- Menu.ModifyMenu (Menu.lua:2639) calls back (owner, rootDescription,
    -- contextData) after the menu's generator has run, so the title created
    -- by UnitPopupManager:OpenMenu (UnitPopupShared.lua:108) is already the
    -- first element description, with its own initializer already queued.
    local function ModifyUnitMenu(_, rootDescription, contextData)
        local ok, err = pcall(function()
            if type(contextData) ~= "table" or FS.IsSecret(contextData.unit) or contextData.unit == nil then return end
            local title
            for _, description in rootDescription:EnumerateElementDescriptions() do
                title = description
                break
            end
            if not title then return end
            title:AddInitializer(function(frame)
                local initOk, initErr = pcall(ApplyFullNameTitle, frame, contextData)
                if not initOk then LogUnitTitleFailure(initErr) end
            end)
        end)
        if not ok then LogUnitTitleFailure(err) end
    end

    for _, tag in ipairs(UNIT_MENU_TAGS) do
        local ok, err = pcall(Menu.ModifyMenu, tag, ModifyUnitMenu)
        if not ok then LogUnitTitleFailure(err) end
    end
end

-------------------------------------------------------------------------------
-- Diagnostics
-------------------------------------------------------------------------------

-- Modern menu frames have no stable _G name (pooled, per Menu.lua ~2099/2116),
-- so they don't fit PanelSkins.RegisterRecon's `{ name, guard } -> _G[name]`
-- lookup shape the way the legacy DropDownList1..N entries below do -- that
-- shape is built for a registry of NAMED globals, not an anonymous pool.
-- Rather than skip recon silently for the modern half of this file, it is
-- exposed here instead: whether the modern hook installed at all, and a
-- running count of pooled menu frames (both systems) this file has actually
-- built chrome on so far.
function FS.Menus.GetDiagnostics()
    return {
        modernHookInstalled = modernHookInstalled,
        legacyListsHooked = legacyListsHooked,
        skinnedMenuCount = skinnedMenuCount,
    }
end

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

-- Blizzard_Menu is confirmed NOT load-on-demand: its own .toc
-- (~/workspaces/reference/wow-ui-source-live-12.1.0/Interface/AddOns/
-- Blizzard_Menu/Blizzard_Menu.toc) carries "## LoadFirst: 1", meaning the
-- client loads it before other addons on every login rather than behind an
-- ADDON_LOADED gate the way e.g. Blizzard_TrainerUI is -- and the 16001
-- globals dump corroborates Menu/MenuUtil/MenuStyleMixin/DropdownButtonMixin/
-- CompositorMixin all being present at login (see file header). A bare
-- `PanelSkins.DeferCombat(Init)` call, the same pattern Popups.lua uses for
-- its own always-present frames, is therefore sufficient; no
-- `PanelSkins.WatchAddonLoad` ADDON_LOADED fallback is needed. None of this
-- file's work is combat-illegal either (hooksecurefunc, Menu.ModifyMenu and
-- our own texture creation are all always legal) -- deferred anyway for consistency with the
-- rest of the addon's Init pattern.
local function Init()
    local legacyCount = LegacyDropDownCount()
    InitLegacyMenus(legacyCount)
    InitModernMenus()
    InitUnitMenuTitles()

    local legacyEntries = {}
    for i = 1, legacyCount do
        legacyEntries[i] = { name = "DropDownList" .. i, guard = "fsMenuChromeBuilt" }
    end
    FS.PanelSkins.RegisterRecon("Menus", legacyEntries)
end

FS.PanelSkins.DeferCombat(Init)
