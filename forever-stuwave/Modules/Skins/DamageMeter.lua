-- Forever STUwave: Damage Meter
-- SKIN ONLY. Blizzard's built-in damage meter (Blizzard_DamageMeter): the DamageMeter owner frame makes one
-- DamageMeterSessionWindow<N> per meter window (DamageMeter:SetupSessionWindow). Each window has a 32 px header
-- texture (`Header`), the session timer, the meter type dropdown (`DamageMeterTypeDropdown.TypeName`), the session
-- dropdown (`SessionDropdown.SessionName`), the settings and minimize buttons, and a `MinimizeContainer` (the
-- body, hidden while minimized) with the background (`MinimizeContainer.Background`, whose alpha is the player's
-- own background opacity setting), the scroll box of entries, the pinned local player entry and the source window
-- (the per spell breakdown).
--
-- Player: "we also need to skin the damage meters." Read off the 12.1 reference source, every name is
-- feature-detected so a client whose meter differs keeps the stock look rather than erroring.
--
-- TAINT. In combat the meter's values are secret and Blizzard's own code handles them, so nothing here writes a
-- field on a Blizzard table or registers a callback in one of its registries; the only Blizzard method called is
-- ForEachEntryFrame, to walk the rows already built. Every other reach in is hooksecurefunc on an instance method
-- (SetupSessionWindow, SetupEntry, Refresh, SetStyle) and region level visuals (textures, fonts, colours) on
-- regions Blizzard already made. Our own state lives in weak tables
-- keyed by the Blizzard object. No value is ever read from an entry, so no secret is touched.
--
-- WHAT IT LOOKS LIKE. The body wears the STUwave cut panel: Blizzard's background texture becomes our nine sliced
-- fill (so the opacity setting still drives it), with the additive glow and the 1 px border on top, and a cyan
-- header band with its rule where Blizzard's header bar was. Bars are flat fills (the class colour Blizzard sets
-- still applies) over a dark recess with a 1 px border and a light top edge; names and numbers are Mononoki with an
-- outline. The settings, session and minimize buttons keep their Blizzard art for now.

local _, FS = ...

local Theme = FS.Theme
if not (Theme and Theme.AddPanelChrome and Theme.SLICE_FILL_TEXTURE and Theme.ApplyNineSlice) then return end
if type(hooksecurefunc) ~= "function" then return end

local FONT = Theme.FONT_MONO
local FLAT = Theme.FLAT_TEXTURE
local ACCENT = Theme.COLOR_POWER
local COLOR_BG = Theme.COLOR_BG
local LINE = Theme.COLOR_BAR_BORDER
local MUTED = Theme.COLOR_MUTED
local WHITE = Theme.COLOR_TEXT_WHITE

local MAX_WINDOWS = 8
local BAND_ALPHA = 0.14
local RULE_ALPHA = 0.55
local RECESS = { 0.039, 0.016, 0.086, 0.85 }   -- #0a0416, the module ink, behind each bar
local SHEEN_ALPHA = 0.22                        -- the light 1 px top edge of a bar's fill
local TEXT_SIZE = 11                            -- Blizzard's own text scale setting multiplies this
local HEADER_SIZE = 11

local windows = setmetatable({}, { __mode = "k" })
local entries = setmetatable({}, { __mode = "k" })

local function SetFont(fs, size, color)
    if not (fs and fs.SetFont) then return end
    if Theme.SetFontChecked then
        Theme.SetFontChecked(fs, FONT, size, "OUTLINE")
    else
        fs:SetFont(FONT, size, "OUTLINE")
    end
    if color and fs.SetTextColor then fs:SetTextColor(color[1], color[2], color[3], color[4] or 1) end
end

local function Edge(parent, layer, sub, color, a)
    local t = parent:CreateTexture(nil, layer, nil, sub)
    t:SetColorTexture(color[1], color[2], color[3], a or 1)
    return t
end

-------------------------------------------------------------------------------
-- Entries (one bar row)
-------------------------------------------------------------------------------

-- Re-applied after each of Blizzard's SetStyle calls, which re-atlas the row's background.
local function ApplyEntryArt(entry)
    local bar = entry.StatusBar
    if not bar then return end
    local bg, edge = bar.Background, bar.BackgroundEdge
    if bg and bg.SetColorTexture then bg:SetColorTexture(RECESS[1], RECESS[2], RECESS[3], RECESS[4]) end
    if edge and edge.SetColorTexture then edge:SetColorTexture(0, 0, 0, 0) end
end

local function SkinEntry(entry)
    if not entry or entries[entry] then return end
    local bar = entry.StatusBar
    if not (bar and bar.SetStatusBarTexture and bar.GetStatusBarTexture) then return end
    entries[entry] = true

    -- Flat fill. Blizzard colours the bar through GetStatusBarTexture():SetVertexColor and caches the colour it set,
    -- so the colour it already gave this row is carried onto the new art here; later changes land on it directly.
    local before = bar:GetStatusBarTexture()
    local r, g, b, a = 1, 1, 1, 1
    if before and before.GetVertexColor then r, g, b, a = before:GetVertexColor() end
    bar:SetStatusBarTexture(FLAT)
    local fill = bar:GetStatusBarTexture()
    if fill and fill.SetVertexColor and not (FS.IsSecret and (FS.IsSecret(r) or FS.IsSecret(g) or FS.IsSecret(b))) then
        fill:SetVertexColor(r, g, b, a)
    end

    if fill then
        local sheen = Edge(bar, "ARTWORK", 2, WHITE, SHEEN_ALPHA)
        sheen:SetPoint("TOPLEFT", fill, "TOPLEFT")
        sheen:SetPoint("TOPRIGHT", fill, "TOPRIGHT")
        sheen:SetHeight(1)
    end

    -- 1 px border round the row's bar, under the text
    local top = Edge(bar, "OVERLAY", -8, LINE)
    top:SetPoint("TOPLEFT", bar, "TOPLEFT", -1, 1); top:SetPoint("TOPRIGHT", bar, "TOPRIGHT", 1, 1); top:SetHeight(1)
    local bottom = Edge(bar, "OVERLAY", -8, LINE)
    bottom:SetPoint("BOTTOMLEFT", bar, "BOTTOMLEFT", -1, -1); bottom:SetPoint("BOTTOMRIGHT", bar, "BOTTOMRIGHT", 1, -1); bottom:SetHeight(1)
    local left = Edge(bar, "OVERLAY", -8, LINE)
    left:SetPoint("TOPLEFT", top, "BOTTOMLEFT"); left:SetPoint("BOTTOMLEFT", bottom, "TOPLEFT"); left:SetWidth(1)
    local right = Edge(bar, "OVERLAY", -8, LINE)
    right:SetPoint("TOPRIGHT", top, "BOTTOMRIGHT"); right:SetPoint("BOTTOMRIGHT", bottom, "TOPRIGHT"); right:SetWidth(1)

    -- the class or spell icon gets the same 1 px frame
    local icon = entry.Icon
    if icon and icon.CreateTexture then
        local frame = Edge(icon, "BACKGROUND", -8, LINE)
        frame:SetPoint("TOPLEFT", icon, "TOPLEFT", -1, 1)
        frame:SetPoint("BOTTOMRIGHT", icon, "BOTTOMRIGHT", 1, -1)
    end

    SetFont(bar.Name, TEXT_SIZE, WHITE)
    SetFont(bar.Value, TEXT_SIZE, WHITE)

    ApplyEntryArt(entry)
    if type(entry.SetStyle) == "function" then hooksecurefunc(entry, "SetStyle", ApplyEntryArt) end
end

local function SkinEntriesOf(owner)
    if type(owner.ForEachEntryFrame) ~= "function" then return end
    pcall(owner.ForEachEntryFrame, owner, SkinEntry)
end

-------------------------------------------------------------------------------
-- Windows
-------------------------------------------------------------------------------

local function SkinBody(container)
    local bg = container.Background
    if bg and bg.SetTexture then
        bg:SetTexture(Theme.SLICE_FILL_TEXTURE)
        Theme.ApplyNineSlice(bg, Theme.SLICE_MARGIN)
        bg:SetVertexColor(COLOR_BG[1], COLOR_BG[2], COLOR_BG[3], 1)
        bg:ClearAllPoints()
        bg:SetAllPoints(container)
    end
    local fill = Theme.AddPanelChrome(container, { fillColor = COLOR_BG, accent = ACCENT })
    if fill then fill:Hide() end   -- Blizzard's own background is the fill: the opacity setting keeps working
end

local function SkinHeader(window)
    local header = window.Header
    if not header then return end
    header:SetAlpha(0)
    local inset = Theme.PanelBandInset and Theme.PanelBandInset() or 3
    local band = Edge(window, "BACKGROUND", 2, ACCENT, BAND_ALPHA)
    band:SetPoint("TOPLEFT", header, "TOPLEFT", inset, -inset)
    band:SetPoint("BOTTOMRIGHT", header, "BOTTOMRIGHT", -inset, 4)
    local rule = Edge(window, "BACKGROUND", 3, ACCENT, RULE_ALPHA)
    rule:SetPoint("TOPLEFT", band, "BOTTOMLEFT")
    rule:SetPoint("TOPRIGHT", band, "BOTTOMRIGHT")
    rule:SetHeight(1)
end

local function SkinSourceWindow(source)
    if not source or windows[source] then return end
    windows[source] = true
    local bg = source.Background
    if bg and bg.SetTexture then
        bg:SetTexture(Theme.SLICE_FILL_TEXTURE)
        Theme.ApplyNineSlice(bg, Theme.SLICE_MARGIN)
        bg:SetVertexColor(COLOR_BG[1], COLOR_BG[2], COLOR_BG[3], 1)
    end
    local fill = Theme.AddPanelChrome(source, { fillColor = COLOR_BG, accent = ACCENT })
    if fill then fill:Hide() end
    SkinEntriesOf(source)
    if type(source.Refresh) == "function" then
        hooksecurefunc(source, "Refresh", function(self) SkinEntriesOf(self) end)
    end
end

local function SkinWindow(window)
    if not window or windows[window] then return end
    windows[window] = true

    local container = window.MinimizeContainer
    if container then
        SkinBody(container)
        SetFont(container.NotActive, HEADER_SIZE, MUTED)
        SkinEntry(container.LocalPlayerEntry)
        SkinSourceWindow(container.SourceWindow)
    end
    SkinHeader(window)

    SetFont(window.SessionTimer, HEADER_SIZE, WHITE)
    local typeDropdown = window.DamageMeterTypeDropdown
    if typeDropdown then SetFont(typeDropdown.TypeName, HEADER_SIZE + 1, ACCENT) end
    local session = window.SessionDropdown
    if session then SetFont(session.SessionName, HEADER_SIZE, WHITE) end

    SkinEntriesOf(window)
    if type(window.SetupEntry) == "function" then
        hooksecurefunc(window, "SetupEntry", function(_, frame) SkinEntry(frame) end)
    end
end

local function SkinExisting()
    for i = 1, MAX_WINDOWS do
        local window = _G["DamageMeterSessionWindow" .. i]
        if window then SkinWindow(window) end
    end
end

local owner = _G.DamageMeter
if type(owner) == "table" and type(owner.SetupSessionWindow) == "function" then
    hooksecurefunc(owner, "SetupSessionWindow", function(_, _, windowData)
        local window = type(windowData) == "table" and windowData.sessionWindow
        if window then SkinWindow(window) end
    end)
end
SkinExisting()

local watcher = CreateFrame("Frame")
watcher:RegisterEvent("PLAYER_LOGIN")
watcher:SetScript("OnEvent", SkinExisting)

FS.DamageMeterSkin = { SkinWindow = SkinWindow, SkinEntry = SkinEntry }
