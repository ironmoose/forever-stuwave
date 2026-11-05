-- Forever STUwave: HudText
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
-- Zone / subzone / PvP status text (design notes)
-------------------------------------------------------------------------------

local ZONE_TEXT_NAMES = { "ZoneTextString", "SubZoneTextString", "PVPInfoTextString" }

local function StyleZoneText()
    for _, name in ipairs(ZONE_TEXT_NAMES) do
        StyleAccentText(_G[name])
    end
end

-------------------------------------------------------------------------------
-- Errors / raid warning / boss banner (design notes)
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
-- Combat text (design notes)
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

    -- Read back and retried if the bundled face is not loaded yet (cold client start);
    -- keepFace: until then the shared object keeps the face it already has.
    Theme.SetFontChecked(font, FONT_MONO, size, flags, true)
end

-------------------------------------------------------------------------------
-- Loss of control (the stun / fear / silence alert in the middle of the screen)
-------------------------------------------------------------------------------

-- LossOfControlFrame (Blizzard_FrameXML/LossOfControlFrame.xml): a dark smoke texture (blackBg), two red
-- rails (RedLineTop/Bottom) that an AnimationGroup flicks open, the spell Icon with a Cooldown, the
-- AbilityName ("Stunned") and a TimeLeft frame holding NumberText + SecondsText. The mixin only ever
-- sets their text, texture and anchors, never their alpha, so SetAlpha(0) on the stock art holds.
--
-- It is an Edit Mode system frame, so nothing is written to it as a Lua field: our plate is our own
-- child frame drawn one level BELOW it (a child normally draws over its parent's regions, which would
-- bury the icon and text), and what we track lives in this file's locals.
local LOC_PAD_X, LOC_PAD_Y, LOC_ICON_RING = 12, 8, 2
local locPlate

local function LocRegion(frame, ...)
    local o = frame
    for i = 1, select("#", ...) do
        if type(o) ~= "table" then return nil end
        o = o[select(i, ...)]
    end
    return o
end

-- The content block (icon + the longer of the two text lines) is centred on the frame by the mixin,
-- so the plate is centred too and only its width follows the icon's left edge.
local function SizeLocPlate(frame, plate, icon)
    local ok = pcall(function()
        local left = icon:GetLeft()
        local cx = frame:GetCenter()
        if not left or not cx then return end
        local half = cx - left + LOC_PAD_X
        if half < 40 then half = 40 end
        plate:SetWidth(math.floor(half * 2 + 0.5))
    end)
    return ok
end

local function StyleLossOfControl()
    local frame = _G.LossOfControlFrame
    if type(frame) ~= "table" or locPlate or type(frame.CreateTexture) ~= "function" then return end

    for _, key in ipairs({ "blackBg", "RedLineTop", "RedLineBottom" }) do
        local region = frame[key]
        if region and region.SetAlpha then region:SetAlpha(0) end
    end

    local plate = CreateFrame("Frame", nil, frame)
    plate:SetFrameStrata(frame:GetFrameStrata())
    plate:SetFrameLevel(math.max(0, frame:GetFrameLevel() - 1))
    plate:SetPoint("CENTER", frame, "CENTER", 0, 0)
    plate:SetSize(256, 58 + LOC_PAD_Y)
    Theme.AddCut2Texture(plate, Theme.SLICE_CUT2_GLOW_TEXTURE, { Theme.COLOR_HEALTH[1], Theme.COLOR_HEALTH[2],
        Theme.COLOR_HEALTH[3], 0.45 }, "BACKGROUND", -8, -Theme.SLICE_CUT2_GLOW_PAD)
    Theme.AddCut2Texture(plate, Theme.SLICE_CUT2_FILL_TEXTURE, { 0.051, 0.024, 0.125, 0.86 }, "BACKGROUND", -6)
    Theme.AddCut2Texture(plate, Theme.SLICE_CUT2_OUTLINE_TEXTURE, Theme.COLOR_HEALTH, "BORDER", 0)
    locPlate = plate

    local icon = frame.Icon
    if icon and icon.SetTexCoord then
        icon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
        -- A pink ring one icon-width wide behind the icon: the icon covers its middle.
        local ring = plate:CreateTexture(nil, "ARTWORK")
        ring:SetColorTexture(Theme.COLOR_HEALTH[1], Theme.COLOR_HEALTH[2], Theme.COLOR_HEALTH[3], 1)
        ring:SetPoint("TOPLEFT", icon, "TOPLEFT", -LOC_ICON_RING, LOC_ICON_RING)
        ring:SetPoint("BOTTOMRIGHT", icon, "BOTTOMRIGHT", LOC_ICON_RING, -LOC_ICON_RING)
        plate:SetScript("OnUpdate", function(self) SizeLocPlate(frame, self, icon) end)
    end

    local name = frame.AbilityName
    if name and name.SetFont and name.GetFont then
        local _, size = name:GetFont()
        ApplyFontGeneric(name, Theme.FONT_ORBITRON, size or 22, Theme.COLOR_HEALTH, "")
    end
    local number = LocRegion(frame, "TimeLeft", "NumberText")
    local seconds = LocRegion(frame, "TimeLeft", "SecondsText")
    if number and number.SetFont and number.GetFont then
        local _, size = number:GetFont()
        ApplyMono(number, size or 20, Theme.COLOR_TEXT_WHITE)
    end
    if seconds and seconds.SetFont and seconds.GetFont then
        local _, size = seconds:GetFont()
        ApplyMono(seconds, size or 20, Theme.COLOR_MUTED)
        -- Stock seats "seconds" at a fixed offset sized for its own number font; the mono digits are
        -- wider, so it follows the number instead. The mixin never re-anchors it.
        if number and seconds.ClearAllPoints then
            seconds:ClearAllPoints()
            seconds:SetPoint("LEFT", number, "RIGHT", 6, 0)
        end
    end
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
    pcall(StyleLossOfControl)
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
