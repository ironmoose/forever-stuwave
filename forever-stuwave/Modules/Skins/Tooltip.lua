-- Forever STUwave: Tooltip
-- FIRST PASS synthwave skin for GameTooltip and its ShoppingTooltip1/2 and
-- ItemRefTooltip siblings (interface 16001), plus a GameTooltipStatusBar
-- retint. Every name is feature-detected; OnShow hooks re-apply the chrome
-- since Blizzard's own tooltip backdrop redraws each time a tooltip shows.

local _, FS = ...

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local SkinPanel = FS.Theme.SkinPanel
local COLOR_BG = FS.Theme.COLOR_BG
local COLOR_BORDER = FS.Theme.COLOR_BORDER
local COLOR_HEALTH = FS.Theme.COLOR_HEALTH

if not FS.PanelSkins.RequireExport(SkinPanel, "Tooltip.lua disabled: FS.Theme.SkinPanel missing") then return end

-- Confirmed present on this client: GameTooltip. The rest are feature-detected
-- at apply time since ShoppingTooltip1/2 and ItemRefTooltip may not exist yet
-- (ItemRefTooltip in particular is unconfirmed at addon-load time).
local TOOLTIP_NAMES = { "GameTooltip", "ShoppingTooltip1", "ShoppingTooltip2", "ItemRefTooltip" }

-------------------------------------------------------------------------------
-- Tooltip backdrop skin
-------------------------------------------------------------------------------

-- Creates the panel chrome once and re-shows the stored regions on every call
-- after that, so the OnShow hook below can call this repeatedly without
-- stacking a new set of textures per show.
local function SkinTooltip(tt)
    FS.PanelSkins.SkinPanelCached(tt, {
        fillColor = COLOR_BG,
        borderColor = COLOR_BORDER,
        radius = 4,
        borderThickness = 1,
        glowSize = 6,
        glowAlpha = 0.3,
    })
end

-- Re-applies the skin on every OnShow so Blizzard's own backdrop redraw never
-- leaves our chrome hidden underneath it. Guarded separately from
-- fsSkinCache so the hook itself is only ever registered once per tooltip.
local function HookTooltipShow(tt)
    FS.PanelSkins.HookShowOnce(tt, "fsTooltipHooked", SkinTooltip)
end

-------------------------------------------------------------------------------
-- Health bar retint
-------------------------------------------------------------------------------

-- Sets GameTooltipStatusBar to the Theme health color. Hooked on both OnShow
-- and OnValueChanged (when the widget supports it) since Blizzard recolors
-- the bar itself on every health update while the tooltip stays open.
local function RetintStatusBar(bar)
    if not bar or not bar.SetStatusBarColor then return end
    local c = COLOR_HEALTH
    bar:SetStatusBarColor(c[1], c[2], c[3], c[4] or 1)
end

local function HookStatusBar(bar)
    if not bar or bar.fsTooltipBarHooked then return end
    if not bar.HookScript then return end

    bar:HookScript("OnShow", RetintStatusBar)
    if bar.HasScript and bar:HasScript("OnValueChanged") then
        bar:HookScript("OnValueChanged", RetintStatusBar)
    end
    bar.fsTooltipBarHooked = true
end

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

-- Tooltips are plain non-secure frames, so none of this is combat-illegal;
-- deferred anyway for consistency with the rest of the addon's Init pattern.
local function Apply()
    for _, name in ipairs(TOOLTIP_NAMES) do
        local tt = _G[name]
        if tt then
            SkinTooltip(tt)
            HookTooltipShow(tt)
        end
    end

    HookStatusBar(GameTooltipStatusBar)
end

FS.PanelSkins.RegisterReconFromList("Tooltip", TOOLTIP_NAMES, "fsSkinCache")

FS.PanelSkins.DeferCombat(Apply)
