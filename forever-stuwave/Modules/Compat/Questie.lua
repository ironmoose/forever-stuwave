-- Forever STUwave: Questie compatibility
--
-- 1. Target frame icon. Questie draws a quest icon beside the target frame (QuestieNameplate.lua,
-- GetTargetFrameIconFrame). It parents that icon to Blizzard's TargetFrame unless it recognises another unit frame
-- addon, and STUwave keeps Blizzard's TargetFrame at alpha 0 (UnitFrames.lua, DimBlizzardFrame), so the icon would never
-- be seen. After each target change this moves Questie's icon onto ForeverSTUwaveTargetFrame, at Questie's own offsets
-- from that frame's right edge.
--
-- Questie builds a fresh icon frame each time the previous one is dropped, and keeps no global handle to it, so it is
-- found among TargetFrame's children: an unnamed plain Frame carrying an `Icon` texture at Questie's frame level 11.
-- Adopted frames leave TargetFrame, so each is moved once. Plain frames only, nothing secure, legal in combat.
--
-- 2. Quest tracker skin. Questie replaces Blizzard's tracker with Questie_BaseFrame (TrackerBaseFrame.lua), a plain
-- BackdropTemplate frame on UIParent whose backdrop Questie drives from its options. The same cut panel chrome STUwave's
-- own tracker wears (Tracker.lua, BuildContainerChrome) is put on that frame as regions of the frame itself, so it
-- sizes, moves and hides with it by anchors alone. Questie's backdrop pieces are held at region alpha 0, which leaves
-- the colour Questie stores in them untouched, and a hook on SetBackdropColor reads that colour's alpha as Questie's
-- state: 0 when its background is off or the tracker is collapsed, the configured alpha when it is on, and every step
-- between while its "background only on mouseover" fade runs. The panel takes that alpha, so it appears exactly when
-- Questie would show its own background. Panel and font only; Questie's lines keep their colours.
--
-- The frame is made late (Questie builds it in a login coroutine), so a bounded one second timer waits for it and
-- stops once the chrome is on. Questie's header row ("Questie Tracker: 12/40") gets a header band and rule behind it
-- while that row is shown at the top of the frame. Everything here is a plain frame or region, legal in combat.
--
-- 3. Tracker font. STUwave's tracker font is registered with LibSharedMedia as "STUwave", so it shows in Questie's
-- font pickers. Questie's own font settings are never written.
--
-- 4. TrackerActive tells TrackerSeat to stand down: Questie hides Blizzard's ObjectiveTrackerFrame (and with it
-- STUwave's own panel, a child of it) while its tracker is enabled.

local _, FS = ...

local QC = {}
FS.QuestieCompat = QC

local QUESTIE_ICON_LEVEL = 11
local ABOVE_FRAME = 20

local BASE_FRAME = "Questie_BaseFrame"
local HEADER_FRAME = "Questie_HeaderFrame"
local FONT_NAME = "STUwave"
local MEDIA_LIB = "LibSharedMedia-3.0"
local POLL_SECONDS, POLL_TRIES = 1, 180 -- three minutes is far past Questie's login stages
local BAND_ALPHA, RULE_ALPHA = 0.08, 0.30 -- the tracker panel's own band and rule (Tracker.lua)

-- The pieces Blizzard's BackdropTemplate draws a backdrop with (Backdrop.lua, textureUVs); Center holds the fill and
-- the colour state Questie writes.
local BACKDROP_PIECES = {
    "Center", "TopLeftCorner", "TopRightCorner", "BottomLeftCorner", "BottomRightCorner",
    "TopEdge", "BottomEdge", "LeftEdge", "RightEdge",
}

local function QuestieLoaded()
    local CA = _G.C_AddOns
    local isLoaded = CA and CA.IsAddOnLoaded or _G.IsAddOnLoaded
    if type(isLoaded) ~= "function" then return false end
    local ok, loaded = pcall(isLoaded, "Questie")
    return ok and loaded and true or false
end
QC.QuestieLoaded = QuestieLoaded

local function QuestieProfile()
    local q = _G.Questie
    local db = type(q) == "table" and q.db
    return type(db) == "table" and type(db.profile) == "table" and db.profile or nil
end
QC.Profile = QuestieProfile

-- True while Questie's tracker is on: Blizzard's tracker is hidden then, and STUwave's panel with it.
local function TrackerActive()
    local profile = QuestieProfile()
    return profile ~= nil and profile.trackerEnabled == true and QuestieLoaded()
end
QC.TrackerActive = TrackerActive

-------------------------------------------------------------------------------
-- Target frame icon
-------------------------------------------------------------------------------

local function IsQuestieIcon(child)
    return type(child) == "table" and child.GetObjectType and child:GetObjectType() == "Frame"
        and child:GetName() == nil and type(child.Icon) == "table" and child.Icon.SetTexture ~= nil
        and child:GetFrameLevel() == QUESTIE_ICON_LEVEL
end

local function Adopt()
    local ours, blizz = _G.ForeverSTUwaveTargetFrame, _G.TargetFrame
    if not (ours and blizz and blizz.GetChildren) then return end
    local profile = QuestieProfile()
    local x = profile and tonumber(profile.nameplateTargetFrameX) or -30
    local y = profile and tonumber(profile.nameplateTargetFrameY) or 25
    for _, child in ipairs({ blizz:GetChildren() }) do
        if IsQuestieIcon(child) then
            child:SetParent(ours)
            child:SetFrameStrata(ours:GetFrameStrata())
            child:SetFrameLevel(ours:GetFrameLevel() + ABOVE_FRAME)
            child:ClearAllPoints()
            child:SetPoint("RIGHT", ours, "RIGHT", x, y)
        end
    end
end
QC.Adopt = Adopt

-------------------------------------------------------------------------------
-- Tracker font
-------------------------------------------------------------------------------

-- Only with Questie loaded. Idempotent: LibSharedMedia refuses a key it already holds, and a font the client does not
-- know yet (it has not scanned the file) is refused without a trace, so each call checks first and the next event
-- tries again. The font has western glyphs only, which LibSharedMedia wants said so it is hidden on other locales.
local function RegisterFont()
    local stub = _G.LibStub
    local path = FS.Theme and FS.Theme.FONT_MONO
    if not stub or type(path) ~= "string" or not QuestieLoaded() then return false end
    local okLib, lib = pcall(stub, MEDIA_LIB, true)
    if not okLib or type(lib) ~= "table" or type(lib.Register) ~= "function" then return false end
    if type(lib.IsValid) == "function" and lib:IsValid("font", FONT_NAME) then return true end
    local okReg, registered = pcall(lib.Register, lib, "font", FONT_NAME, path, lib.LOCALE_BIT_western)
    return okReg and registered == true
end
QC.RegisterFont = RegisterFont

-------------------------------------------------------------------------------
-- Tracker skin
-------------------------------------------------------------------------------

local built = false -- set before anything is made: an error below is reported once and never retried into a second panel
local skin -- once built: frame, regions (the panel pieces, alpha-driven), band, rule, muted, alpha, bandHeight

-- A plain number, or nil: a secret is turned away before anything else touches it, NaN after.
local function Plain(value)
    if type(value) ~= "number" then return nil end
    if FS.IsSecret and FS.IsSecret(value) then return nil end
    if value ~= value then return nil end
    return value
end

local function BaseFrame()
    local frame = _G[BASE_FRAME]
    if type(frame) == "table" and type(frame.CreateTexture) == "function" and type(frame.SetBackdropColor) == "function" then
        return frame
    end
end

-- Questie's backdrop is held at region alpha 0. Questie writes vertex colours only, so what it stored is intact; a
-- piece Questie rebuilds is a new region and is caught by the next colour call.
local function MuteQuestieBackdrop()
    local frame = skin.frame
    for _, name in ipairs(BACKDROP_PIECES) do
        local piece = frame[name]
        if type(piece) == "table" and type(piece.SetAlpha) == "function" and not skin.muted[piece] then
            piece:SetAlpha(0)
            skin.muted[piece] = true
        end
    end
end

local function Follow(alpha)
    if alpha == skin.alpha then return end
    skin.alpha = alpha
    for _, region in ipairs(skin.regions) do region:SetAlpha(alpha) end
end

-- How far below the frame's top Questie's header row ends, or nil when the row is not shown at the top (header off, or
-- moved to the bottom, which is also where Questie puts it while collapsed). Read from the header's own anchor and
-- height rather than from screen rects, so it holds whether or not the engine has settled the layout yet.
local function HeaderDepth()
    local header = _G[HEADER_FRAME]
    if type(header) ~= "table" or type(header.IsShown) ~= "function" or not header:IsShown() then return nil end
    local point, relativeTo, relativePoint, _, y = header:GetPoint(1)
    if point ~= "TOPLEFT" or relativeTo ~= skin.frame or relativePoint ~= "TOPLEFT" then return nil end
    local height
    y, height = Plain(y), Plain(header:GetHeight())
    if not (y and height) then return nil end
    local depth = height - y
    return depth > 0 and depth or nil
end

-- The band runs from the panel's inset to the bottom of Questie's header row, the rule under it.
local function LayoutBand()
    local depth = HeaderDepth()
    local height = depth and math.floor(depth - skin.inset + 0.5) or nil
    if height and height < 2 then height = nil end
    if height == skin.bandHeight then return end
    skin.bandHeight = height
    skin.band:SetShown(height ~= nil)
    skin.rule:SetShown(height ~= nil)
    if height then skin.band:SetHeight(height) end
end

-- After each Questie colour call: its own backdrop stays invisible, the panel takes its alpha, the band its row.
local function OnBackdropColor(_, _, _, _, alpha)
    MuteQuestieBackdrop()
    alpha = Plain(alpha)
    if alpha then Follow(math.max(0, math.min(1, alpha))) end
    LayoutBand()
end

-- A hook's error is raised in the caller, which here is Questie's own tracker update: a throw of ours must never cut
-- that short. It is caught and handed to the error handler instead.
local function Guarded(fn)
    return function(...)
        local ok, err = pcall(fn, ...)
        if ok then return end
        local layout = FS.Layout
        if layout and layout.ForwardError then layout.ForwardError(err) end
    end
end

-- Builds the chrome once Questie's frame exists and its tracker is on. Returns true when there is nothing left to wait
-- for (built, or given up after an error), false when the frame is not there yet.
local function SkinTracker()
    if built then return true end
    local Theme = FS.Theme
    local frame = BaseFrame()
    if not (frame and Theme and Theme.AddPanelChrome and type(hooksecurefunc) == "function" and TrackerActive()) then
        return false
    end
    built = true

    -- The same cut panel chrome as the STUwave tracker panel: fill, additive glow, 1px border, header band and rule.
    local accent = Theme.COLOR_POWER
    local inset = Theme.PanelBandInset()
    local fill, glow, border = Theme.AddPanelChrome(frame, { fillColor = Theme.COLOR_BG, accent = accent })

    local band = frame:CreateTexture(nil, "ARTWORK")
    band:SetColorTexture(accent[1], accent[2], accent[3], BAND_ALPHA)
    band:SetPoint("TOPLEFT", frame, "TOPLEFT", inset, -inset)
    band:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -inset, -inset)
    band:Hide()

    local rule = frame:CreateTexture(nil, "ARTWORK")
    rule:SetColorTexture(accent[1], accent[2], accent[3], RULE_ALPHA)
    rule:SetPoint("TOPLEFT", band, "BOTTOMLEFT", 0, 0)
    rule:SetPoint("TOPRIGHT", band, "BOTTOMRIGHT", 0, 0)
    rule:SetHeight(1)
    rule:Hide()

    skin = { frame = frame, regions = { fill, glow, border, band, rule }, band = band, rule = rule,
        inset = inset, muted = {} }
    MuteQuestieBackdrop()

    -- Start from what Questie has stored in its backdrop now; an unreadable state is hidden until its next call.
    local ok, _, _, _, alpha = pcall(frame.GetBackdropColor, frame)
    alpha = ok and Plain(alpha) or 0
    Follow(math.max(0, math.min(1, alpha)))
    LayoutBand()

    hooksecurefunc(frame, "SetBackdropColor", Guarded(OnBackdropColor))
    return true
end
QC.SkinTracker = SkinTracker

-- Questie makes its frame in a login coroutine, after PLAYER_LOGIN. Wait for it on a bounded timer that ends with the
-- build, or when the tracker is off (turning it back on reloads the interface, which starts over).
local function SkinWhenReady()
    if not TrackerActive() or SkinTracker() then return end
    if not (_G.C_Timer and C_Timer.NewTicker) then return end
    local ticker
    ticker = C_Timer.NewTicker(POLL_SECONDS, function()
        if not TrackerActive() or SkinTracker() then ticker:Cancel() end
    end, POLL_TRIES)
end

-------------------------------------------------------------------------------
-- Events
-------------------------------------------------------------------------------

-- Our file normally loads before Questie's (folder order), so Questie's ADDON_LOADED reaches this frame first and the
-- font is in LibSharedMedia before Questie builds its options or draws a line. Registered again at login for a Questie
-- that loaded first, and for a file the client had not scanned yet.
RegisterFont()

local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:RegisterEvent("ADDON_LOADED")
events:SetScript("OnEvent", function(self, event, name)
    if event == "ADDON_LOADED" then
        if name == "Questie" then RegisterFont() end
        return
    end
    if event == "PLAYER_LOGIN" then
        self:UnregisterEvent("ADDON_LOADED")
        if not QuestieLoaded() then
            self:UnregisterAllEvents()
            return
        end
        RegisterFont()
        SkinWhenReady()
        self:RegisterEvent("PLAYER_TARGET_CHANGED")
        self:RegisterEvent("QUEST_LOG_UPDATE")
        return
    end
    -- Questie draws on the same events; wait a frame so its icon exists before it is moved.
    if C_Timer and C_Timer.After then C_Timer.After(0, Adopt) else Adopt() end
end)
