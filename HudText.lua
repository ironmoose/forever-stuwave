-- Forever Synthwave: HudText
-- FIRST PASS synthwave restyle of on-screen HUD text: zone/subzone/PvP status
-- text, error/raid-warning/boss-banner text, and floating combat text.
-- Font/color only, no repositioning or resizing; every name and Font object
-- is feature-detected, so a missing one silently no-ops. BossBanner's
-- internal region names are UNVERIFIED on this client (interface 16001) --
-- pending an in-game check, see report.

local _, FS = ...

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local Theme = FS.Theme
local ApplyFontGeneric = Theme.ApplyFontGeneric
local ApplyMono = Theme.ApplyMono
local FONT_MONO = Theme.FONT_MONO
local COLOR_POWER = Theme.COLOR_POWER -- cyan; the addon's established accent color (Chat.lua tabs, Tracker.lua header)

-------------------------------------------------------------------------------
-- Small helpers
-------------------------------------------------------------------------------

-- Neon-accent restyle: Theme mono font, cyan accent color. Used for zone-type
-- text where a full recolor was explicitly requested.
local function StyleAccentText(obj)
    if not (obj and obj.SetFont and obj.GetFont) then return end
    local _, size = obj:GetFont()
    if not size then return end
    ApplyMono(obj, size, COLOR_POWER)
end

-- Font-only restyle: swaps the font family to Theme mono but preserves the
-- object's existing size, outline flag, and text color -- used for
-- error/warning/banner text, where the existing color often carries
-- game-state meaning (e.g. red errors, yellow raid warnings) and must stay
-- legible rather than being overridden.
local function StyleFontOnly(obj)
    if not (obj and obj.SetFont and obj.GetFont) then return end
    local _, size, flags = obj:GetFont()
    if not size then return end

    local color
    if obj.GetTextColor then
        local r, g, b, a = obj:GetTextColor()
        color = { r, g, b, a }
    end

    ApplyFontGeneric(obj, FONT_MONO, size, color, flags)
end

-------------------------------------------------------------------------------
-- Zone / subzone / PvP status text
-------------------------------------------------------------------------------

local ZONE_TEXT_NAMES = { "ZoneTextString", "SubZoneTextString", "PVPInfoTextString" }

local function StyleZoneText()
    for _, name in ipairs(ZONE_TEXT_NAMES) do
        StyleAccentText(_G[name])
    end
end

-------------------------------------------------------------------------------
-- Errors / raid warning / boss banner
-------------------------------------------------------------------------------

-- UIErrorsFrame is confirmed present on this client; RaidWarningFrame and its
-- message slot are feature-detected the same way. RaidWarningFrameSlot1 was
-- measured absent on this client and is not in this list.
local ERROR_WARNING_NAMES = { "UIErrorsFrame", "RaidWarningFrame", "RaidWarningFrameSlot2" }

local function StyleErrorsAndRaidWarning()
    for _, name in ipairs(ERROR_WARNING_NAMES) do
        StyleFontOnly(_G[name])
    end
end

-- BossBanner's internal text region name is UNVERIFIED on this client; the
-- candidate list covers the field names used across known Blizzard boss-
-- banner implementations. Only fields that behave like a FontInstance
-- (SetFont/GetFont present) are touched.
local BOSS_BANNER_FIELDS = { "Title", "Name", "Text", "TitleText", "NameText", "BossName" }

local function StyleBossBanner()
    local banner = BossBanner
    if not banner then return end

    StyleFontOnly(banner)
    for _, field in ipairs(BOSS_BANNER_FIELDS) do
        StyleFontOnly(banner[field])
    end
end

-------------------------------------------------------------------------------
-- Combat text
-------------------------------------------------------------------------------

-- Floating combat text (hit/miss/crit/heal numbers) on this client is driven
-- by one shared Font object, CombatTextFont, rather than individual frames --
-- restyling it once restyles every instance. Color is deliberately left
-- untouched: each instance sets its own color at draw time (e.g. crit red,
-- heal green), and a Font object's color would flatten that signal.
-- CombatFeedback and PlayerHitIndicator were measured absent on this client;
-- do not reintroduce per-frame checks for them here.
local function StyleCombatText()
    local font = CombatTextFont
    if not (type(font) == "table" and type(font.SetFont) == "function" and type(font.GetFont) == "function") then
        return
    end

    local _, size, flags = font:GetFont()
    if not size then return end

    font:SetFont(FONT_MONO, size, flags)
end

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

-- All of the above are plain non-secure FontString/FontInstance regions, so
-- none of this is combat-illegal; deferred anyway for consistency with the
-- rest of the addon's Init pattern. One-shot at login is acceptable for this
-- first pass -- these elements are frequently reset by the game, but a light
-- re-apply is deferred to a later pass.
local function Apply()
    StyleZoneText()
    StyleErrorsAndRaidWarning()
    StyleBossBanner()
    StyleCombatText()
end

if InCombatLockdown() then
    local regen = CreateFrame("Frame")
    regen:RegisterEvent("PLAYER_REGEN_ENABLED")
    regen:SetScript("OnEvent", function(self)
        self:UnregisterEvent("PLAYER_REGEN_ENABLED")
        Apply()
    end)
else
    Apply()
end
