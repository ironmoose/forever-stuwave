-- Forever Synthwave: Micro Menu keys
--
-- The micro menu is a row of slanted synthwave "keys" in the control deck. Each
-- key is one of Blizzard's own micro buttons, seated into FS.Deck.microSlot and
-- left as the click target, with our own keycap, glyph and LED drawn on a child
-- frame above all of Blizzard's art.
--
-- Why cover instead of restyle: a micro button's behaviour is Blizzard C code
-- bound to that frame (open the spellbook, the collections journal, the store),
-- with no attribute equivalent, so the buttons stay. Their art is a different
-- story. Blizzard rewrites normal/pushed/highlight/flash/portrait regions on
-- every state change, and restyling them lost to it (the talents button showed
-- stock art on hover and click). So the overlay draws the whole key and the
-- button's own art is only kept INVISIBLE (TameButtonArt, alpha 0, re-asserted
-- from post-hooks): the plate is a leaning parallelogram, so its two corner
-- triangles are transparent and would show Blizzard's art through them. The
-- keys nest (each overlaps its neighbour's box by the lean, see Pitch), so the
-- deck chassis shows through those triangles, as in the mockup. Full rationale
-- in CLAUDE.md.
--
-- Rules the code below keeps:
--   * Blizzard's own art stays invisible without touching the button: its big
--     fade fields get alpha 0, its own texture regions (normal, pushed, disabled,
--     highlight, portrait) are faded and held there by post-hooks on each region's
--     SetAlpha and on the button's atlas/texture setters, and its flash regions
--     (UIFrameFlash owns their alpha) are hidden by vertex colour alpha.
--   * the button itself is never SetAlpha'd or SetScript'd (Blizzard writes its
--     alpha on enable/disable and owns its handlers); we only HookScript and
--     hooksecurefunc. The overlay ignores the button's alpha (a disabled button
--     is 0.5), so the disabled look is painted by us.
--   * every overlay frame is EnableMouse(false). The Mainline tooltip gate asks
--     IsMouseMotionFocus, so a mouse-enabled child would kill the tooltip.
--   * reparenting, sizing and anchoring happen out of combat only (except the LFG eye, see PlaceQueueEye); combat sets
--     applyPending and PLAYER_REGEN_ENABLED finishes the job.
--   * MicroMenuContainer is left alone (it owns the LFG eye and the level-up
--     handlers that refresh the buttons); only MicroMenu is dimmed.

local _, FS = ...

if not FS.PanelSkins.RequireExport(FS.Layout, "MicroBars.lua disabled: FS.Layout missing") then return end

local MEDIA = "Interface\\AddOns\\ForeverSynthwave\\media\\"
local TEX_PLATE = MEDIA .. "cell_slant.tga"
local TEX_EDGE = MEDIA .. "deck_key_slant_outline.tga"
local TEX_GLOW = MEDIA .. "cell_slant_glow.tga"
local TEX_LED = MEDIA .. "deck_led.tga"
local TEX_DOT = MEDIA .. "glow_round.tga"
local GLYPH_DIR = MEDIA .. "glyph_"

-- Design px defaults, replaced at Apply by FS.Deck's own numbers when present.
local KEY_W, KEY_H, KEY_GAP = 34, 26, 3
-- cell_slant.tga's lean as a fraction of the key width (11 of its 32 px, the
-- generator's SLANT 0.34); the keys nest by this much.
local LEAN_FRAC = 0.34

local GLYPH_SIZE = 16
local LED_W, LED_H = 20, 5
local LED_X, LED_Y = -4, 1      -- LED rides the slanted bottom edge, left of centre
local PIP_SIZE = 7              -- active dot above the key
local PIP_X, PIP_Y = 5, 3
local FLASH_PIP_SIZE = 9        -- notification dot, top right
local FLASH_PIP_X, FLASH_PIP_Y = -6, -3
local HOVER_GLOW_W, HOVER_GLOW_H = 1.45, 1.7   -- of the key; cell_slant_glow's core is about 69% x 62%
local FLASH_GLOW_W, FLASH_GLOW_H = 1.3, 1.45
local LIFT = 1                  -- glyph travel on hover (up) and press (down)

-- Overlay frame level above its button. Blizzard's NotificationOverlay child sits
-- at button + 100, so 120 keeps our key (and the fx/flash hosts above it) on top.
local OV_LEVEL = 120
local OV_SPAN = 20                -- the fx and flash hosts sit within this above the overlay; the help ticket clears it

-- LFG eye placement: gap left of the deck chassis (design px) and its frame level
-- above the chassis, which has to clear the keys' overlays.
local EYE_GAP = 8
local EYE_LEVEL = OV_LEVEL + 80

local PLATE_NORMAL = { 0.078, 0.039, 0.141, 0.95 }    -- #140a24
local PLATE_PRESSED = { 0.227, 0.059, 0.165, 0.95 }   -- #3a0f2a

local CYAN = { 0.133, 0.878, 1.0 }     -- #22e0ff
local VIOLET = { 0.486, 0.227, 0.929 } -- #7C3AED
local PINK = { 1.0, 0.180, 0.592 }     -- #ff2e97
local ACCENTS = { CYAN, VIOLET, PINK }

local GLYPH_NORMAL = { 0.812, 0.769, 0.937 }  -- #cfc4ef
local GLYPH_HOT = { 1, 1, 1 }
local GLYPH_OFF = { 0.353, 0.314, 0.439 }     -- #5a5070

local LATENCY_GREEN = { 0.224, 1.0, 0.078 }   -- #39ff14
local LATENCY_YELLOW = { 1.0, 0.882, 0.302 }
local LATENCY_RED = { 1.0, 0.302, 0.302 }

-- Button name (minus "MicroButton") to glyph file. Mainline and Classic names
-- both appear because this client ships both families.
local GLYPHS = {
    Character = "character", Profession = "professions", Spellbook = "spellbook",
    PlayerSpells = "spellbook", Talent = "talents", Legacy = "legacy",
    QuestLog = "questlog", Guild = "guild", LFD = "lfd", LFG = "lfd",
    Collections = "collections", Help = "help", Store = "store", MainMenu = "mainmenu",
    Achievement = "achievement", EJ = "ej", Housing = "housing",
    PVP = "pvp", Socials = "socials", WorldMap = "worldmap",
}
local GLYPH_GENERIC = "help"

-- Window frames whose visibility mirrors a button's "open" state, as a fallback
-- beside SetButtonState. Only one-to-one mappings: PlayerSpellsFrame hosts both
-- the spellbook and talents, so it would light both keys and is left out.
-- Store and WorldMap matter on the Classic family: its UpdateMicroButtons only
-- refreshes those two while the button's parent is MicroMenuContainer, which
-- ours no longer is, so their state comes from the window instead.
local WINDOW_FRAMES = {
    Character = { "CharacterFrame" },
    Spellbook = { "SpellBookFrame" },
    Talent = { "TalentFrame", "PlayerTalentFrame" },
    QuestLog = { "QuestLogFrame" },
    Guild = { "GuildFrame", "CommunitiesFrame" },
    Collections = { "CollectionsJournal" },
    Achievement = { "AchievementFrame" },
    EJ = { "EncounterJournal" },
    Profession = { "ProfessionsBookFrame" },
    MainMenu = { "GameMenuFrame" },
    Store = { "StoreFrame" },
    WorldMap = { "WorldMapFrame" },
    Socials = { "FriendsFrame" },
}

-- Micro buttons, left to right, shown or not. Filled in place by DeriveMicroOrder
-- on first Apply from MicroMenu's own children (Blizzard's game-rule filter and
-- order); one table identity, because the recon list is refilled from it. Which
-- of them are laid out is decided per reseat by IsShown, since Blizzard shows and
-- hides some (Help, Talent, Housing) after the list is built.
local MICRO_ORDER = {}

-- Blizzard's Camelot candidate order, used only when MicroMenu yields nothing.
-- Global existence is not membership here: this client defines both families.
local MICRO_FALLBACK = {
    "Character", "Profession", "Spellbook", "PlayerSpells", "Talent", "Legacy",
    "Achievement", "QuestLog", "Housing", "Guild", "LFD", "Collections", "EJ",
    "Help", "Store", "MainMenu",
}

-- State keyed by button, never stored on Blizzard's tables.
local keys = setmetatable({}, { __mode = "k" })
local keyList = {}
local pulseState = setmetatable({}, { __mode = "k" })
local pulseToken = setmetatable({}, { __mode = "k" })   -- latest pulse per button, so a stale timer cannot clear a newer pulse

-- Set when a reseat, build or eye placement was blocked by combat lockdown.
local applyPending = false

-- Set while SeatAndStyle runs, so the show/hide hooks its own reparenting can
-- trigger do not start a nested reseat. Assigned below, used by InstallHooks.
local seating = false
local OnShownChanged

local warned = {}
local function Degrade(tag, msg)
    if warned[tag] then return end
    warned[tag] = true
    if FS.LogDegradeOnce then
        FS.LogDegradeOnce("microbars-" .. tag, "|cffff4488ForeverSynthwave|r: " .. msg)
    end
end

local function Scale()
    return FS.Layout.Scale and FS.Layout.Scale() or 1
end

local function BaseName(name)
    return (name:gsub("MicroButton$", ""))
end

-- A forbidden frame (StoreMicroButton and StoreFrame on this client) throws on
-- every method call from addon code except IsForbidden, which every frame has
-- and is safe to ask. A throw there counts as forbidden. Such a frame is skipped
-- outright: no key, no hooks, no reparent, no layout slot, no chat line.
local function IsForbidden(frame)
    if type(frame) ~= "table" or type(frame.IsForbidden) ~= "function" then return false end
    local ok, forbidden = pcall(frame.IsForbidden, frame)
    return not ok or forbidden == true
end

-------------------------------------------------------------------------------
-- Derived list
-------------------------------------------------------------------------------

local microRecon = {}

local function SyncRecon(names)
    for i = #microRecon, 1, -1 do microRecon[i] = nil end
    for _, name in ipairs(names) do
        microRecon[#microRecon + 1] = { name = name, guard = "fsMicroKey" }
    end
end

local microDerived = false

-- Runs once, before any reparent: afterwards the buttons are no longer
-- MicroMenu children, so every later reseat reuses the cached list. Shown state
-- is ignored on purpose: a child is a real micro button when Blizzard's own
-- AddButton gave it a layoutIndex (the game-rule filter already ran), and a
-- button hidden now (Help, Talent, Housing) can be shown later, so every one
-- gets a key and the layout picks the shown ones per reseat.
local function DeriveMicroOrder()
    if microDerived then return end
    microDerived = true

    local found = {}
    local menu = _G.MicroMenu
    if menu and type(menu.GetChildren) == "function" then
        pcall(function()
            for _, child in ipairs({ menu:GetChildren() }) do
                local ok, name, index = pcall(function()
                    if IsForbidden(child) then return nil end
                    return child:GetName(), child.layoutIndex
                end)
                if ok and not FS.IsSecret(name) and not FS.IsSecret(index)
                    and type(name) == "string" and type(index) == "number"
                    and name:find("MicroButton$")
                then
                    found[#found + 1] = { name = name, index = index }
                end
            end
        end)
    end

    table.sort(found, function(a, b)
        if a.index ~= b.index then return a.index < b.index end
        return a.name < b.name
    end)

    for _, entry in ipairs(found) do
        MICRO_ORDER[#MICRO_ORDER + 1] = entry.name
    end

    if #MICRO_ORDER == 0 then
        for _, base in ipairs(MICRO_FALLBACK) do
            local name = base .. "MicroButton"
            if _G[name] and not IsForbidden(_G[name]) then MICRO_ORDER[#MICRO_ORDER + 1] = name end
        end
        Degrade("list-fallback", "MicroMenu children unavailable, micro bar using Blizzard's default button order")
    end

    SyncRecon(MICRO_ORDER)
end

-------------------------------------------------------------------------------
-- Visual state
-------------------------------------------------------------------------------

-- Pure: flags in, a description of every layer out. Painting is separate so the
-- state table can be checked without a renderer.
local function ComputeVisual(f, accent, ledTint)
    local v = {
        plate = PLATE_NORMAL,
        edgeColor = accent, edgeA = 0.35,
        glyph = GLYPH_NORMAL, glyphA = 1,
        glowColor = accent, glowA = 0,
        ledColor = ledTint or accent, ledA = 0.6,
        lift = 0, pip = false, flash = false,
    }

    if f.disabled then
        v.glyph, v.glyphA = GLYPH_OFF, 0.6
        v.edgeA = 0.15
        v.ledA = 0
    else
        if f.active then
            v.edgeA = 1
            v.ledA = 1
            v.glyph = GLYPH_HOT
            v.pip = true
        end
        if f.hover then
            v.edgeA = math.max(v.edgeA, 0.9)
            v.glowA = 0.5
            v.glyph = GLYPH_HOT
            v.ledA = 1
            v.lift = LIFT
        end
        if f.pressed then
            v.plate = PLATE_PRESSED
            v.edgeColor, v.edgeA = PINK, 1
            v.glyph = GLYPH_HOT
            v.glowColor, v.glowA = PINK, 0.35
            v.ledColor, v.ledA = PINK, 1
            v.lift = -LIFT
        end
    end

    -- A pulse is the button asking to be opened; once it is open it stops.
    v.flash = (f.flash and not f.active) and true or false
    return v
end

local function Tint(tex, c, a)
    tex:SetVertexColor(c[1], c[2], c[3], a or c[4] or 1)
end

local function PlaceGlyph(key)
    local s = key.scale or 1
    key.glyph:ClearAllPoints()
    key.glyph:SetPoint("CENTER", key.ov, "CENTER", 0, (key.lift or 0) * s)
end

local function Paint(key, v)
    Tint(key.plate, v.plate)
    Tint(key.edge, v.edgeColor, v.edgeA)
    Tint(key.glyph, v.glyph, v.glyphA)
    Tint(key.hoverGlow, v.glowColor, v.glowA)
    key.hoverGlow:SetShown(v.glowA > 0)
    Tint(key.led, v.ledColor, v.ledA)
    key.led:SetShown(v.ledA > 0)
    key.pip:SetShown(v.pip)

    if key.lift ~= v.lift then
        key.lift = v.lift
        PlaceGlyph(key)
    end

    if v.flash then
        key.flashHost:Show()
        if not key.pulsing then
            key.pulsing = true
            if key.pulse then key.pulse:Play() end
        end
    else
        if key.pulsing then
            key.pulsing = false
            if key.pulse then key.pulse:Stop() end
        end
        key.flashHost:Hide()
    end
end

local function ApplyKeyState(key)
    if not key.plate then return end
    Paint(key, ComputeVisual(key.flags, key.accent, key.ledTint))
end

local function SetFlag(key, name, value)
    value = value and true or false
    if key.flags[name] == value then return end
    key.flags[name] = value
    ApplyKeyState(key)
end

-------------------------------------------------------------------------------
-- Key construction
-------------------------------------------------------------------------------

-- `keyW` is the design width the layout settled on (KEY_W, or less when more keys
-- are shown than the slot holds); the overlay itself follows its button.
local function SizeKey(key, s, keyW)
    key.scale = s
    local w, h = (keyW or KEY_W) * s, KEY_H * s

    key.glyph:SetSize(GLYPH_SIZE * s, GLYPH_SIZE * s)
    PlaceGlyph(key)

    key.hoverGlow:SetSize(w * HOVER_GLOW_W, h * HOVER_GLOW_H)
    key.hoverGlow:ClearAllPoints()
    key.hoverGlow:SetPoint("CENTER", key.ov, "CENTER", 0, 0)

    key.flashGlow:SetSize(w * FLASH_GLOW_W, h * FLASH_GLOW_H)
    key.flashGlow:ClearAllPoints()
    key.flashGlow:SetPoint("CENTER", key.ov, "CENTER", 0, 0)

    key.led:SetSize(LED_W * s, LED_H * s)
    key.led:ClearAllPoints()
    key.led:SetPoint("BOTTOM", key.ov, "BOTTOM", LED_X * s, LED_Y * s)

    key.pip:SetSize(PIP_SIZE * s, PIP_SIZE * s)
    key.pip:ClearAllPoints()
    key.pip:SetPoint("CENTER", key.ov, "TOP", PIP_X * s, PIP_Y * s)

    key.flashPip:SetSize(FLASH_PIP_SIZE * s, FLASH_PIP_SIZE * s)
    key.flashPip:ClearAllPoints()
    key.flashPip:SetPoint("CENTER", key.ov, "TOPRIGHT", FLASH_PIP_X * s, FLASH_PIP_Y * s)
end

-- Creates the overlay frames and textures. Frames are created with the mouse
-- already off; the plate sits on `ov` (nothing under it: the triangles outside
-- the parallelogram are transparent so the deck shows through), everything lit
-- sits on `fx`, one level higher, so a neighbour's glow is not cut by this key's
-- plate.
local function PopulateKey(key, button, glyphFile)
    local ov = key.ov
    ov:SetAllPoints(button)

    key.plate = ov:CreateTexture(nil, "ARTWORK", nil, 0)
    key.plate:SetTexture(TEX_PLATE)
    key.plate:SetAllPoints(ov)

    local fx = CreateFrame("Frame", nil, ov)
    fx:EnableMouse(false)
    fx:SetFrameLevel(ov:GetFrameLevel() + 5)
    fx:SetAllPoints(ov)
    key.fx = fx

    key.hoverGlow = fx:CreateTexture(nil, "BACKGROUND", nil, 0)
    key.hoverGlow:SetTexture(TEX_GLOW)
    key.hoverGlow:SetBlendMode("ADD")

    key.edge = fx:CreateTexture(nil, "ARTWORK", nil, 0)
    key.edge:SetTexture(TEX_EDGE)
    key.edge:SetAllPoints(ov)

    key.glyph = fx:CreateTexture(nil, "OVERLAY", nil, 0)
    key.glyph:SetTexture(glyphFile)

    key.led = fx:CreateTexture(nil, "OVERLAY", nil, 1)
    key.led:SetTexture(TEX_LED)

    key.pip = fx:CreateTexture(nil, "OVERLAY", nil, 2)
    key.pip:SetTexture(TEX_DOT)
    key.pip:SetBlendMode("ADD")
    Tint(key.pip, key.accent, 1)

    -- Notification layers live on their own host so one alpha animation pulses
    -- the glow and the dot together.
    local flashHost = CreateFrame("Frame", nil, fx)
    flashHost:EnableMouse(false)
    flashHost:SetFrameLevel(fx:GetFrameLevel() + 1)
    flashHost:SetAllPoints(ov)
    flashHost:Hide()
    key.flashHost = flashHost

    key.flashGlow = flashHost:CreateTexture(nil, "BACKGROUND", nil, 0)
    key.flashGlow:SetTexture(TEX_GLOW)
    key.flashGlow:SetBlendMode("ADD")
    Tint(key.flashGlow, PINK, 0.8)

    key.flashPip = flashHost:CreateTexture(nil, "OVERLAY", nil, 3)
    key.flashPip:SetTexture(TEX_DOT)
    key.flashPip:SetBlendMode("ADD")
    Tint(key.flashPip, PINK, 1)

    if flashHost.CreateAnimationGroup then
        local group = flashHost:CreateAnimationGroup()
        group:SetLooping("BOUNCE")
        local alpha = group:CreateAnimation("Alpha")
        alpha:SetFromAlpha(0.3)
        alpha:SetToAlpha(1)
        alpha:SetDuration(0.8)
        alpha:SetSmoothing("IN_OUT")
        key.pulse = group
    end

    SizeKey(key, Scale(), KEY_W)
end

-- Latency tint for the main-menu key's LED, only while that button is shown.
local function LatencyColor(ms)
    if ms < 100 then return LATENCY_GREEN end
    if ms < 250 then return LATENCY_YELLOW end
    return LATENCY_RED
end

local function RefreshLatency(key)
    if type(GetNetStats) ~= "function" then return end
    local ok, _, _, home = pcall(GetNetStats)
    if not ok or FS.IsSecret(home) or type(home) ~= "number" then return end
    local color = LatencyColor(home)
    if key.ledTint ~= color then
        key.ledTint = color
        ApplyKeyState(key)
    end
end

local function StartLatency(key)
    if key.ticker or not (C_Timer and C_Timer.NewTicker) then return end
    RefreshLatency(key)
    key.ticker = C_Timer.NewTicker(5, function() RefreshLatency(key) end)
end

local function StopLatency(key)
    if key.ticker then
        key.ticker:Cancel()
        key.ticker = nil
    end
end

-- Calls cb whenever `region` is shown or hidden. A Frame also gets its script
-- hooks, since a parent's show cascades without calling the Lua :Show().
local function WatchShown(region, cb)
    if type(hooksecurefunc) ~= "function" then return end
    for _, method in ipairs({ "Show", "Hide", "SetShown" }) do
        if type(region[method]) == "function" then
            pcall(hooksecurefunc, region, method, cb)
        end
    end
    if region.HookScript and region.HasScript then
        for _, script in ipairs({ "OnShow", "OnHide" }) do
            if region:HasScript(script) then pcall(region.HookScript, region, script, cb) end
        end
    end
end

local function WindowOpen(key)
    for _, name in ipairs(key.windows) do
        local frame = _G[name]
        if frame and not IsForbidden(frame) and frame.IsShown and frame:IsShown() then return true end
    end
    return false
end

-- Open means the button is held pushed (SetButtonState "PUSHED", lock) or its
-- window is up.
local function RefreshActive(key)
    local f = key.flags
    SetFlag(key, "active", f.pushedLock or f.window)
end

local function SyncWindow(key)
    key.flags.window = WindowOpen(key)
    RefreshActive(key)
end

-- Frames can be load-on-demand, so this runs at build and on ADDON_LOADED.
-- Returns true when it hooked a window it had not hooked before.
local function HookWindows(key)
    local hookedNew = false
    for _, name in ipairs(key.windows) do
        local frame = _G[name]
        if frame and not key.windowHooked[name] and not IsForbidden(frame) and frame.HookScript then
            local ok = pcall(function()
                frame:HookScript("OnShow", function() SyncWindow(key) end)
                frame:HookScript("OnHide", function() SyncWindow(key) end)
            end)
            if ok then
                key.windowHooked[name] = true
                hookedNew = true
            end
        end
    end
    key.flags.window = WindowOpen(key)
    return hookedNew
end

-- Keeps GameTooltip above the deck: the deck is at the screen bottom, and
-- Blizzard anchors micro tooltips to the button's right.
local function ReanchorTooltip(button)
    local tip = _G.GameTooltip
    if not tip or not tip.IsOwned then return end
    local ok, owned = pcall(tip.IsOwned, tip, button)
    if not ok or owned ~= true then return end
    if type(tip.SetAnchorType) == "function" then
        if pcall(tip.SetAnchorType, tip, "ANCHOR_TOP", 0, 8) then return end
    end
    pcall(function()
        tip:ClearAllPoints()
        tip:SetPoint("BOTTOM", button, "TOP", 0, 8)
    end)
end

local function InstallHooks(key, button)
    button:HookScript("OnEnter", function(self)
        SetFlag(key, "hover", true)
        ReanchorTooltip(self)
    end)
    button:HookScript("OnLeave", function()
        SetFlag(key, "pressed", false)
        SetFlag(key, "hover", false)
    end)
    button:HookScript("OnMouseDown", function() SetFlag(key, "pressed", true) end)
    button:HookScript("OnMouseUp", function() SetFlag(key, "pressed", false) end)

    -- Enable and disable fire the handlers even for a disabled button's motion
    -- scripts, and IsEnabled is the source of truth either way.
    local function SyncEnabled()
        local ok, enabled = pcall(button.IsEnabled, button)
        if ok then SetFlag(key, "disabled", enabled == false) end
    end
    pcall(button.HookScript, button, "OnEnable", SyncEnabled)
    pcall(button.HookScript, button, "OnDisable", SyncEnabled)
    SyncEnabled()

    button:HookScript("OnHide", function()
        key.flags.hover, key.flags.pressed = false, false
        ApplyKeyState(key)
        OnShownChanged()
    end)
    -- Blizzard shows and hides some buttons after the bar is built; the layout
    -- only counts shown ones, so it has to follow.
    button:HookScript("OnShow", function() OnShownChanged() end)

    -- Blizzard re-anchors the tooltip to ANCHOR_RIGHT on every enable, disable and
    -- hover re-evaluation, and the main menu button's OnUpdate re-runs the
    -- performance tooltip (default anchor) while hovered. Each snaps it off our
    -- ANCHOR_TOP placement, so each is hooked to put it back. Once per button.
    if type(hooksecurefunc) == "function" and type(button.EvaluateTooltipVisibility) == "function" then
        pcall(hooksecurefunc, button, "EvaluateTooltipVisibility", function() ReanchorTooltip(button) end)
    end

    if type(hooksecurefunc) == "function" and type(button.SetButtonState) == "function" then
        pcall(hooksecurefunc, button, "SetButtonState", function(_, state, lock)
            if state == "PUSHED" and lock then
                key.flags.pushedLock = true
            elseif state == "NORMAL" then
                key.flags.pushedLock = false
            end
            RefreshActive(key)
        end)
    end
    if type(button.GetButtonState) == "function" then
        local ok, state = pcall(button.GetButtonState, button)
        if ok and state == "PUSHED" then key.flags.pushedLock = true end
    end

    HookWindows(key)
    RefreshActive(key)

    -- Flash is a Lua-driven pulse (MicroButtonPulse, hooked below) or, on
    -- Mainline-style buttons, a shown NotificationOverlay.
    key.syncFlash = function()
        local on = pulseState[button] == true
        local overlay = button.NotificationOverlay
        if overlay and type(overlay.IsShown) == "function" then
            on = on or overlay:IsShown() == true
        end
        SetFlag(key, "flash", on)
    end
    if button.NotificationOverlay then
        pcall(WatchShown, button.NotificationOverlay, key.syncFlash)
    end
    key.syncFlash()

    if key.baseName == "MainMenu" then
        button:HookScript("OnShow", function() StartLatency(key) end)
        button:HookScript("OnHide", function() StopLatency(key) end)
        if button:IsVisible() then StartLatency(key) end
    end
end

-- Blizzard art bigger than the 34x26 key pokes out past the overlay: the
-- atlas-sized Background and PushedBackground (~32x41), the Character button's
-- portrait shadows, the main menu button's performance bar (19x39, 2 below) and,
-- on Mainline, the NotificationOverlay bell (6 above the key). Blizzard only
-- Shows and Hides these, never SetAlpha, so alpha 0 sticks. IsShown ignores
-- alpha, so the NotificationOverlay still reads shown, which syncFlash relies on.
local FADE_FIELDS = { "Background", "PushedBackground", "Shadow", "PushedShadow", "MainMenuBarPerformanceBar" }
-- The flash regions are the exception: UIFrameFlash writes their alpha every
-- frame (FlashContent atlas-sized on Mainline, Classic's Flash 64x64), so alpha
-- cannot hold them. They are pinned to the button's own rect (so an atlas-sized
-- one cannot spill past the key) and hidden through their vertex colour alpha
-- instead (HideFlashRegion), which UIFrameFlash never writes; our own flashHost
-- (flashGlow + flashPip) paints the pulse. Without the vertex hide they would
-- show in the plate's transparent corner triangles for the whole pulse.
local PIN_FIELDS = { "FlashContent", "Flash" }

-- The button's OWN texture regions are the other half: the plate is a leaning
-- parallelogram with transparent corner triangles, so the button's normal,
-- pushed, disabled and highlight textures (and the Character portrait, the guild
-- emblem) would show through them. Unlike the fields above, Blizzard WRITES
-- these regions' alpha (MainMenuBarMicroButtonMixin:OnEnter/OnLeave toggle the
-- normal texture, SetPushed/SetNormal the highlight's) and re-points them with
-- Set<State>Atlas on state changes (LoadMicroButtonTextures, the main menu
-- button's latency art), so alpha 0 alone does not stick. Two re-assertions:
-- a post-hook on each region's own SetAlpha (whoever writes it, it ends at 0),
-- and post-hooks on the button's atlas/texture setters, which can create a
-- region that did not exist at build time. The button itself is never touched.
-- The flash regions are NOT in this set: UIFrameFlash owns their alpha (above).
-- Mainline buttons also inherit QuickKeybindButtonTemplate's
-- QuickKeybindHighlightTexture (shown only in quick-keybind mode, alpha written
-- by Blizzard_QuickKeybind); it is a direct Texture region, so this sweep fades
-- it too. That costs nothing: the cue would sit under our plate anyway (the
-- overlay is a frame above the button), so the sweep deliberately does not
-- exclude it and keybind mode shows no highlight on the keys.
local ART_ACCESSORS = { "GetNormalTexture", "GetPushedTexture", "GetDisabledTexture", "GetHighlightTexture" }
local ART_SETTERS = {
    "SetNormalAtlas", "SetPushedAtlas", "SetDisabledAtlas", "SetHighlightAtlas",
    "SetNormalTexture", "SetPushedTexture", "SetDisabledTexture", "SetHighlightTexture",
}
local FLASH_FIELDS = { "FlashContent", "Flash", "FlashBorder" }

local artRegions = setmetatable({}, { __mode = "k" })   -- region -> its SetAlpha is hooked
local artButtons = setmetatable({}, { __mode = "k" })   -- button -> its setters are hooked
-- region -> true while our own SetAlpha(0) on it runs. Per region, never one
-- shared flag: Blizzard code can SetAlpha a DIFFERENT region from inside this
-- one's write, and that nested write must still be zeroed by its own hook.
local fading = setmetatable({}, { __mode = "k" })

local function ZeroRegion(region)
    if fading[region] then return end
    fading[region] = true
    pcall(region.SetAlpha, region, 0)
    fading[region] = nil
end

-- Hide a flash region by vertex colour alpha (UIFrameFlash writes the region's
-- alpha, not its vertex colour). Every field is a Texture in the 12.1 source
-- (FlashBorder, FlashContent, Classic Flash); a Frame would get its Texture
-- regions instead.
local function HideFlashRegion(region)
    if type(region) ~= "table" then return end
    if type(region.SetVertexColor) == "function" then
        pcall(region.SetVertexColor, region, 1, 1, 1, 0)
    elseif type(region.GetRegions) == "function" then
        local ok, kids = pcall(function() return { region:GetRegions() } end)
        if ok then
            for _, kid in ipairs(kids) do
                if type(kid) == "table" and type(kid.SetVertexColor) == "function" then
                    pcall(kid.SetVertexColor, kid, 1, 1, 1, 0)
                end
            end
        end
    end
end

local function FadeRegion(region)
    if type(region) ~= "table" or type(region.SetAlpha) ~= "function" then return end
    ZeroRegion(region)
    if not artRegions[region] and type(hooksecurefunc) == "function" then
        if pcall(hooksecurefunc, region, "SetAlpha", ZeroRegion) then artRegions[region] = true end
    end
end

local function IsTexture(region)
    if type(region) ~= "table" or type(region.GetObjectType) ~= "function" then return false end
    local ok, kind = pcall(region.GetObjectType, region)
    return ok and kind == "Texture"
end

-- Every direct Texture region of the button except the ones with their own
-- handling (the fade fields, the flash regions), plus whatever the state
-- accessors return (a region SetNormalAtlas just made may not be listed yet).
local function FadeButtonRegions(button)
    local skip = {}
    for _, list in ipairs({ FADE_FIELDS, FLASH_FIELDS }) do
        for _, field in ipairs(list) do
            local region = button[field]
            if type(region) == "table" then skip[region] = true end
        end
    end
    for _, accessor in ipairs(ART_ACCESSORS) do
        if type(button[accessor]) == "function" then
            local ok, region = pcall(button[accessor], button)
            if ok and not skip[region] then FadeRegion(region) end
        end
    end
    if type(button.GetRegions) == "function" then
        local ok, regions = pcall(function() return { button:GetRegions() } end)
        if ok then
            for _, region in ipairs(regions) do
                if IsTexture(region) and not skip[region] then FadeRegion(region) end
            end
        end
    end
end

local function TameButtonArt(button)
    for _, field in ipairs(FADE_FIELDS) do
        local region = button[field]
        if type(region) == "table" and region.SetAlpha then pcall(region.SetAlpha, region, 0) end
    end
    local notify = button.NotificationOverlay
    if type(notify) == "table" and notify.SetAlpha then pcall(notify.SetAlpha, notify, 0) end
    for _, field in ipairs(PIN_FIELDS) do
        local region = button[field]
        if type(region) == "table" and region.SetAllPoints then
            pcall(function()
                region:ClearAllPoints()
                region:SetAllPoints(button)
            end)
        end
    end

    for _, field in ipairs(FLASH_FIELDS) do HideFlashRegion(button[field]) end

    FadeButtonRegions(button)
    if not artButtons[button] and type(hooksecurefunc) == "function" then
        artButtons[button] = true
        for _, method in ipairs(ART_SETTERS) do
            if type(button[method]) == "function" then
                pcall(hooksecurefunc, button, method, function() FadeButtonRegions(button) end)
            end
        end
    end
end

local function EnsureKey(button, index)
    local existing = keys[button]
    if existing then return existing end

    local name = button:GetName() or ""
    local base = BaseName(name)
    local glyphFile = GLYPH_DIR .. (GLYPHS[base] or GLYPH_GENERIC) .. ".tga"

    local ov = CreateFrame("Frame", nil, button)
    ov:EnableMouse(false)
    ov:SetFrameLevel(button:GetFrameLevel() + OV_LEVEL)
    -- Mainline OnDisable does button:SetAlpha(0.5), which would turn a disabled
    -- key translucent; the disabled look is painted in ComputeVisual instead. The
    -- chain above the button (slot, deck) is never faded by alpha, only shown or
    -- hidden, and visibility still cascades to an ignore-parent-alpha child.
    if ov.SetIgnoreParentAlpha then ov:SetIgnoreParentAlpha(true) end

    local key = {
        button = button, ov = ov, baseName = base,
        accent = ACCENTS[(index - 1) % #ACCENTS + 1],
        windows = WINDOW_FRAMES[base] or {}, windowHooked = {},
        flags = { flash = pulseState[button] == true },
    }

    local ok, err = pcall(PopulateKey, key, button, glyphFile)
    if not ok then
        -- A half-built overlay would cover the button with nothing on it.
        ov:Hide()
        Degrade("key-build-" .. name, ("micro key for %s failed to build, leaving Blizzard's art: %s"):format(name, tostring(err)))
        return nil
    end

    -- Only now that the overlay exists: faded art with no key over it would leave
    -- the button blank.
    pcall(TameButtonArt, button)

    keys[button] = key
    keyList[#keyList + 1] = key
    -- /fsrecon skins guard; the only field this file assigns on a Blizzard frame.
    -- hooksecurefunc on a method (SetButtonState, EvaluateTooltipVisibility, the
    -- eye's UpdatePosition), on Show/Hide/SetShown, on the art setters (TameButtonArt)
    -- and on an art region's SetAlpha also leaves a wrapper in that field, which the
    -- engine writes, not our code.
    button.fsMicroKey = true

    local hooked, herr = pcall(InstallHooks, key, button)
    if not hooked then
        Degrade("key-hooks-" .. name, ("micro key for %s: state hooks failed: %s"):format(name, tostring(herr)))
    end
    ApplyKeyState(key)
    return key
end

-------------------------------------------------------------------------------
-- Seating
-------------------------------------------------------------------------------

local fallbackSlot

-- FS.Deck.microSlot normally. If the deck never loaded the row still has to
-- exist, so a bare container is made at the bottom centre.
local function GetSlot()
    local deck = FS.Deck
    if deck and deck.microSlot then
        KEY_W = deck.KEY_W or KEY_W
        KEY_H = deck.KEY_H or KEY_H
        KEY_GAP = deck.KEY_GAP or KEY_GAP
        LEAN_FRAC = deck.LEAN_FRAC or LEAN_FRAC
        return deck.microSlot, false
    end

    Degrade("no-deck", "FS.Deck missing, micro keys using a standalone container")
    if not fallbackSlot then
        fallbackSlot = CreateFrame("Frame", "ForeverSynthwaveMicroBar", UIParent)
        fallbackSlot:SetFrameStrata("LOW")
    end
    return fallbackSlot, true
end

-- Every micro button, in order, whether or not it is currently shown.
local function SeatedButtons()
    local list = {}
    for _, name in ipairs(MICRO_ORDER) do
        local button = _G[name]
        if button and button.SetParent and not IsForbidden(button) then list[#list + 1] = button end
    end
    return list
end

-- Blizzard's own layout leaves hidden buttons out, and so does ours.
local function ShownButtons(buttons)
    local list = {}
    for _, button in ipairs(buttons) do
        local ok, shown = pcall(button.IsShown, button)
        if ok and not FS.IsSecret(shown) and shown == true then list[#list + 1] = button end
    end
    return list
end

-- The keys nest: each leaning key overlaps its neighbour's box by the lean, so
-- the step from one key's centre to the next is the key width minus the lean,
-- plus the gap measured between the leaning edges (the mockup's PITCH = (KW -
-- LEAN) + 3). This is the ONE place that formula lives; the layout, the
-- standalone container's size and Deck.lua's slot width (its own copy of the
-- same arithmetic, rounded up) all agree on it. keyW and gap scale together
-- (the lean is a fraction of keyW), so a shrunk row keeps its shape.
local function Pitch(keyW, gap)
    return keyW * (1 - LEAN_FRAC) + gap
end

-- Natural width of `count` nested keys: one full key plus a pitch for each other.
local function RowWidth(count, keyW, gap)
    if count <= 0 then return 0 end
    keyW, gap = keyW or KEY_W, gap or KEY_GAP
    return keyW + (count - 1) * Pitch(keyW, gap)
end

-- The width (design px) the keys are laid out in. With FS.Deck it is the shown
-- keys' natural width, capped at the deck's own maximum (more keys than the deck
-- holds shrink instead of overflowing); FitDeck makes the slot that wide, so the
-- keys fill it with no empty run. The standalone container is sized to its keys,
-- so it never shrinks. A deck without SetMicroWidth keeps its fixed slot and the
-- keys fill what it has.
local function LayoutWidth(slot, natural, s)
    if slot == fallbackSlot then return natural end
    local deck = FS.Deck
    if deck and deck.SetMicroWidth and type(deck.MICRO_W_MAX) == "number" then
        return math.min(natural, deck.MICRO_W_MAX)
    end
    local w = slot:GetWidth()
    if type(w) == "number" and not FS.IsSecret(w) and w > 0 and s > 0 then return w / s end
    return natural
end

-- Tells the deck how wide its micro slot has to be for `count` shown keys. The
-- deck resizes its chassis with it, leftward (its right edge is fixed). Called
-- from the same reseat that seats the keys, so out of combat only and the deck
-- width and the keys always agree. No FS.Deck: nothing to tell (standalone). No
-- shown key (login, before Blizzard shows its buttons): the deck keeps its width
-- rather than collapsing to nothing for a moment.
local function FitDeck(count)
    local deck = FS.Deck
    if count > 0 and deck and deck.SetMicroWidth then deck.SetMicroWidth(RowWidth(count)) end
end

-- Width of each key, the screen offset of each key's centre from the slot's
-- centre, and the gap, for `count` shown keys. The keys sit right-aligned in the
-- slot, the rightmost box flush with the slot's right edge, against the divider
-- that separates it from the bag bar (Deck.lua puts the micro slot on the left
-- and the divider on its right). The slot is as wide as the keys need, so the
-- leftmost box is flush with its left edge too; more keys than the slot can hold
-- shrink, gaps and lean included, by one common factor instead of overflowing.
local function KeyLayout(slot, count, s)
    local natural = RowWidth(count)
    local slotW = LayoutWidth(slot, natural, s)

    local f = (natural > slotW and natural > 0) and slotW / natural or 1
    local keyW, gap = KEY_W * f, KEY_GAP * f
    local pitch = Pitch(keyW, gap)
    local offsets = {}
    for i = 1, count do
        offsets[i] = (slotW / 2 - keyW / 2 - (count - i) * pitch) * s
    end
    return keyW, offsets, gap
end

-- Known limit: the hit rect is an axis-aligned box, so its vertical edges cut
-- across the slanted plates. A click on a key's top-right or bottom-left corner
-- (the part of the plate that lies past the cut) lands on its neighbour's rect.
-- The inset below only makes the rects tile at mid height; no rectangle can
-- follow a parallelogram.
--
-- Hit rect inset per side. Neighbouring boxes overlap by w - pitch = lean - gap
-- (design px), so the rectangles would fight over the strip where two leaning
-- plates sit side by side. The gap between two plates is the same at every
-- height (their edges are parallel), and at mid height the gap's middle lies
-- (lean - gap) / 2 inside each box's near edge: A's right edge is at w - lean / 2,
-- B's left edge at pitch + lean / 2 = w - lean / 2 + gap, so the middle is at
-- w - lean / 2 + gap / 2 and A's inset is w - that = (lean - gap) / 2. With that
-- inset on both sides A's hit rect ends where B's begins, with neither an
-- overlap nor an uncovered strip. Screen units.
local function HitInset(keyW, gap, s)
    return math.max((keyW * LEAN_FRAC - gap) / 2, 0) * s
end

local function SeatPositionOk(button, slot, offset, s, keyW)
    if button:GetParent() ~= slot then return false end
    local point, relativeTo, relPoint, x = button:GetPoint(1)
    if point ~= "CENTER" or relativeTo ~= slot or relPoint ~= "CENTER" then return false end
    if type(x) ~= "number" or math.abs(x - offset) > 1 then return false end
    local w, h = button:GetWidth(), button:GetHeight()
    if type(w) ~= "number" or type(h) ~= "number" then return false end
    return math.abs(w - keyW * s) < 1 and math.abs(h - KEY_H * s) < 1
end

-- True when any shown button left the slot, lost its anchor, moved or was
-- resized, or the shown set changed what its place should be. Reads only; safe in
-- combat.
local function Drifted()
    if #keyList == 0 then return false end
    local slot = (FS.Deck and FS.Deck.microSlot) or fallbackSlot
    if not slot then return false end
    local s = Scale()
    local list = ShownButtons(SeatedButtons())
    local deck = FS.Deck
    if #list > 0 and deck and deck.SetMicroWidth and deck.GetMicroWidth and type(deck.MICRO_W_MAX) == "number" then
        -- The deck's micro slot has to be as wide as the shown keys need (FitDeck
        -- leaves it alone when no key is shown).
        local want = math.min(RowWidth(#list), deck.MICRO_W_MAX)
        if math.abs(deck.GetMicroWidth() - want) > 1e-6 then return true end
    end
    local keyW, offsets = KeyLayout(slot, #list, s)
    for i, button in ipairs(list) do
        if keys[button] and not SeatPositionOk(button, slot, offsets[i], s, keyW) then return true end
    end
    return false
end

-- MicroMenu is dimmed rather than Hide()'d (a Hide plus hook taints Blizzard's
-- secure layout path), and only MicroMenu. MicroMenuContainer is left alone: it
-- parents the LFG eye (QueueStatusButton), which a dim or mouse sweep would make
-- invisible and unclickable, and it registers PLAYER_LEVEL_UP and
-- TRIAL_STATUS_UPDATE to refresh the buttons, which UnregisterAllEvents would
-- cut. MicroMenu itself registers no events, so no DimBlizzardFrame here. Runs
-- after the buttons have left it; the child sweep catches any that did not.
local function HideBlizzardMenu()
    local menu = _G.MicroMenu
    if not menu then return end
    local ok = pcall(function()
        menu:SetAlpha(0)
        if menu.EnableMouse then menu:EnableMouse(false) end
        for _, child in ipairs({ menu:GetChildren() }) do
            if not IsForbidden(child) and child.EnableMouse then child:EnableMouse(false) end
        end
    end)
    if not ok then Degrade("dim-MicroMenu", "could not dim MicroMenu") end
end

local eyeBusy = false

-- Blizzard anchors the LFG eye to MicroMenu, which is now an empty frame in the
-- bottom right corner, under the XP bar's strata. Seats it just left of the deck
-- chassis, vertically centred, and above the deck's frame levels. Runs from the
-- eye's own UpdatePosition post-hook, which Blizzard calls on every MicroMenu
-- layout. It never calls UpdatePosition itself, and eyeBusy covers any re-entry.
-- No combat gate: QueueStatusButton is unprotected and Blizzard's own
-- UpdatePosition re-anchors it in combat, so the post-hook must re-place it in
-- combat too (a queue pop mid-fight would otherwise leave it under the XP bar).
local function PlaceQueueEye()
    local eye = _G.QueueStatusButton
    local chassis = FS.Deck and FS.Deck.frame
    if not eye or not chassis or eyeBusy then return end

    eyeBusy = true
    local ok = pcall(function()
        local scale = eye:GetScale()
        if type(scale) ~= "number" or scale <= 0 then scale = 1 end
        eye:ClearAllPoints()
        eye:SetPoint("RIGHT", chassis, "LEFT", -EYE_GAP * Scale() / scale, 0)
        if eye:GetFrameStrata() ~= "HIGH" then eye:SetFrameStrata("HIGH") end
        local level = chassis:GetFrameLevel() + EYE_LEVEL
        if eye:GetFrameLevel() ~= level then eye:SetFrameLevel(level) end
    end)
    eyeBusy = false
    if not ok then Degrade("eye", "could not seat the LFG eye beside the deck") end
end

-- The web ticket button is a child of the Character button, one level above it,
-- so it would sit under that key's overlay. Blizzard's anchor for it now gets a
-- nil relativeTo (its edge button is no longer a MicroMenu child), which should
-- fall back to its parent, the Character button (UNVERIFIED in game), so the
-- anchor stays as it was and only the level needs lifting.
local function RaiseHelpTicket()
    local ticket = _G.HelpOpenWebTicketButton
    local charKey = _G.CharacterMicroButton and keys[_G.CharacterMicroButton]
    if not ticket or not charKey then return end
    pcall(function()
        local want = charKey.ov:GetFrameLevel() + OV_SPAN
        if ticket:GetFrameLevel() < want then ticket:SetFrameLevel(want) end
    end)
end

local lastReseatAt = -math.huge

-- Parents, anchors and sizes every micro button, shown or not, and builds
-- missing keys. Only shown buttons take a place in the row; a hidden one parks
-- at the slot centre until it is shown and the layout is rerun.
local function SeatButtons(buttons, shown, slot, s, keyW, offsets, gap)
    local place = {}
    for i, button in ipairs(shown) do place[button] = i end

    local placed = 0
    for i, button in ipairs(buttons) do
        local ok, err = pcall(function()
            if button:GetParent() ~= slot then button:SetParent(slot) end
            button:ClearAllPoints()
            button:SetPoint("CENTER", slot, "CENTER", place[button] and offsets[place[button]] or 0, 0)
            button:SetSize(keyW * s, KEY_H * s)
            if button.SetHitRectInsets then
                local inset = HitInset(keyW, gap, s)
                button:SetHitRectInsets(inset, inset, 0, 0)
            end
            if button.IsMouseEnabled and not button:IsMouseEnabled() then
                button:EnableMouse(true)
            end
        end)
        if ok then
            placed = placed + 1
            local key = EnsureKey(button, i)
            if key then SizeKey(key, s, keyW) end
        else
            Degrade("seat-" .. (button:GetName() or i), "could not seat a micro button: " .. tostring(err))
        end
    end
    return placed
end

-- Seats every micro button into the slot, builds missing keys, resizes all of
-- them. Idempotent; the post-hook, rescale and regen paths all end here.
local function SeatAndStyle()
    local slot, standalone = GetSlot()
    local s = Scale()
    local buttons = SeatedButtons()
    if #buttons == 0 then return 0 end

    lastReseatAt = GetTime()

    local shown = ShownButtons(buttons)
    FitDeck(#shown)
    local keyW, offsets, gap = KeyLayout(slot, #shown, s)

    if standalone then
        slot:SetSize(RowWidth(math.max(#shown, 1)) * s, KEY_H * s)
        slot:ClearAllPoints()
        slot:SetPoint("BOTTOM", UIParent, "BOTTOM", 0, 40 * s)
        slot:Show()
    end

    seating = true
    local ok, placed = pcall(SeatButtons, buttons, shown, slot, s, keyW, offsets, gap)
    seating = false
    if not ok then
        Degrade("seat-all", "micro bar seating failed: " .. tostring(placed))
        return 0
    end

    if placed > 0 then
        HideBlizzardMenu()
        PlaceQueueEye()
        RaiseHelpTicket()
    end
    return placed
end

-------------------------------------------------------------------------------
-- Reseat scheduling
-------------------------------------------------------------------------------

-- Blizzard re-lays-out MicroMenu after our handlers run, and a synchronous
-- reseat gets undone. Passes at 0 and 0.15s force a reseat, 0.5 and 1.0s only
-- verify. Coalesced to one schedule per frame; a newer generation supersedes
-- older passes, and pendingForce keeps an owed forced pass alive across
-- supersession so an event burst cannot starve it.
local RESEAT_SETTLE = 0.25
local RESEAT_DELAYS = { 0, 0.15, 0.5, 1.0 }
local RESEAT_VERIFY_FROM = 0.5
local reseatGen, lastScheduleAt, pendingForce = 0, nil, false

local function ReseatMicro(onlyIfDrifted)
    if InCombatLockdown() then
        applyPending = true
        return
    end
    if onlyIfDrifted and not Drifted() then return end
    SeatAndStyle()
end

-- A micro button was shown or hidden (Blizzard does this for Help, Talent and
-- Housing after the bar is built): the shown set is what gets laid out, so rerun
-- the layout if it no longer matches. Drifted notices the new set, a no-op
-- otherwise, so the show/hide churn Blizzard causes costs only a few reads.
OnShownChanged = function()
    if seating then return end
    ReseatMicro(true)
end

local function ScheduleReseat()
    if InCombatLockdown() then
        applyPending = true
        return
    end
    if not (C_Timer and C_Timer.After) then
        ReseatMicro()
        return
    end

    local now = GetTime()
    if now == lastScheduleAt then return end
    lastScheduleAt = now

    reseatGen = reseatGen + 1
    pendingForce = true
    local gen = reseatGen
    for _, delay in ipairs(RESEAT_DELAYS) do
        C_Timer.After(delay, function()
            local current = gen == reseatGen
            if delay >= RESEAT_VERIFY_FROM then
                if current then ReseatMicro(true) end
            elseif current or (pendingForce and GetTime() - lastReseatAt >= RESEAT_SETTLE) then
                pendingForce = false
                ReseatMicro()
            end
        end)
    end
end

-- Settle window: our own reseat can make Blizzard queue a Layout, which would
-- reschedule forever. The verify passes catch anything dropped here.
local function OnBlizzardLayout()
    if InCombatLockdown() then
        applyPending = true
        return
    end
    if GetTime() - lastReseatAt < RESEAT_SETTLE then return end
    ScheduleReseat()
end

-- Hooks on the cause: MicroMenu and its container re-Layout for edit mode,
-- input-device and resolution changes. Post-hooks cannot taint the caller. No
-- SetParent hook (our own SetParent would loop into it); Drifted covers
-- re-parents. Tracked per target so one missing at login is hooked later.
local hooked = {}
local HOOK_TARGETS = {
    { name = "MicroMenu", method = "Layout" },
    { name = "MicroMenu", method = "Show" },
    { name = "MicroMenuContainer", method = "Layout" },
    { name = "MicroMenuContainer", method = "Show" },
}

local eyeHooked = false

local function InstallReseatHooks()
    if type(hooksecurefunc) ~= "function" then return end
    for _, target in ipairs(HOOK_TARGETS) do
        local id = target.name .. ":" .. target.method
        local frame = _G[target.name]
        if not hooked[id] and frame and type(frame[target.method]) == "function" then
            if pcall(hooksecurefunc, frame, target.method, OnBlizzardLayout) then
                hooked[id] = true
            end
        end
    end

    -- MicroMenu:Layout calls the eye's UpdatePosition, which re-anchors it to
    -- MicroMenu; the post-hook puts it back beside the deck.
    local eye = _G.QueueStatusButton
    if not eyeHooked and eye and type(eye.UpdatePosition) == "function" then
        if pcall(hooksecurefunc, eye, "UpdatePosition", PlaceQueueEye) then
            eyeHooked = true
            PlaceQueueEye()
        end
    end
end

-- Flash state for a micro button. Mainline drives the flash with
-- MicroButtonPulse(button, duration); Classic's talent level-up uses
-- SetButtonPulse(button, duration, rate) and stops with a duration of 0 or
-- ButtonPulse_StopPulse. A timed pulse ends on its own with no Stop call (the
-- flash region just stops), so a duration schedules ONE bounded timer that
-- clears the state; the token keeps a stale timer from clearing a newer pulse.
local function IsMicroButton(button)
    if type(button) ~= "table" then return false end
    if keys[button] or pulseState[button] ~= nil then return true end
    if type(button.GetName) ~= "function" then return false end
    local ok, name = pcall(button.GetName, button)
    return ok and not FS.IsSecret(name) and type(name) == "string" and name:find("MicroButton$") ~= nil
end

local function SetPulse(button, on, duration)
    if not IsMicroButton(button) then return end
    local token = (pulseToken[button] or 0) + 1
    pulseToken[button] = token
    pulseState[button] = on or nil
    local key = keys[button]
    if key and key.syncFlash then key.syncFlash() end

    if on and type(duration) == "number" and not FS.IsSecret(duration) and duration > 0
        and C_Timer and C_Timer.After
    then
        C_Timer.After(duration, function()
            if pulseToken[button] ~= token then return end
            pulseState[button] = nil
            local current = keys[button]
            if current and current.syncFlash then current.syncFlash() end
        end)
    end
end

-- Global functions hooked once each, retried while any is missing (a
-- load-on-demand Blizzard addon can define one after login).
local GLOBAL_HOOKS = {
    -- Blizzard's MicroButtonPulse returns early while micro button alerts are
    -- locked off (MainMenuMicroButton_AreAlertsEnabled() false), so no flash runs.
    { name = "MicroButtonPulse", fn = function(button, duration)
        local enabled = _G.MainMenuMicroButton_AreAlertsEnabled
        if type(enabled) == "function" and not enabled() then return end
        SetPulse(button, true, duration)
    end },
    { name = "MicroButtonPulseStop", fn = function(button) SetPulse(button, false) end },
    { name = "SetButtonPulse", fn = function(button, duration)
        SetPulse(button, type(duration) == "number" and not FS.IsSecret(duration) and duration > 0, duration)
    end },
    { name = "ButtonPulse_StopPulse", fn = function(button) SetPulse(button, false) end },
    -- The main menu button's OnUpdate re-runs this every interval while hovered,
    -- and its default anchor snaps the tooltip off our placement.
    { name = "MainMenuBarPerformanceBarFrame_OnEnter", fn = function(button) ReanchorTooltip(button) end },
}
local globalsLeft = #GLOBAL_HOOKS

local function InstallGlobalHooks()
    if globalsLeft == 0 or type(hooksecurefunc) ~= "function" then return end
    for _, entry in ipairs(GLOBAL_HOOKS) do
        if not entry.done and type(_G[entry.name]) == "function" then
            if pcall(hooksecurefunc, entry.name, entry.fn) then
                entry.done = true
                globalsLeft = globalsLeft - 1
            end
        end
    end
end

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

local function Apply()
    if InCombatLockdown() then
        applyPending = true
        return
    end
    applyPending = false

    -- Derive before any reparent, while MicroMenu still owns its buttons.
    DeriveMicroOrder()
    SeatAndStyle()
    InstallReseatHooks()
end

-- PLAYER_LOGIN, not file scope: UIParent is not fully sized during load (see
-- Theme.lua's FS.Layout notes). The rescale callback re-seats and resizes.
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function(self, event, arg1)
    if event == "ADDON_LOADED" then
        -- Only a Blizzard addon can bring in a window frame, a hook target or the
        -- ticket button, and each load costs a handful of lookups at most.
        if type(arg1) ~= "string" or not arg1:find("^Blizzard_") then return end
        for _, key in ipairs(keyList) do
            local ok, hookedNew = pcall(HookWindows, key)
            if ok and hookedNew then RefreshActive(key) end
        end
        InstallReseatHooks()
        InstallGlobalHooks()
        if not InCombatLockdown() then RaiseHelpTicket() else applyPending = true end
        return
    end

    if event ~= "PLAYER_LOGIN" then
        if applyPending and not InCombatLockdown() then Apply() end
        InstallReseatHooks()
        ScheduleReseat()
        return
    end

    self:UnregisterEvent("PLAYER_LOGIN")
    for _, e in ipairs({ "PLAYER_REGEN_ENABLED", "PLAYER_ENTERING_WORLD", "ADDON_LOADED" }) do
        pcall(self.RegisterEvent, self, e)
    end
    InstallGlobalHooks()
    Apply()

    if FS.Layout.OnRescale then
        -- The deck's own rescale defers to PLAYER_REGEN_ENABLED too (Deck.lua's
        -- ApplyOrDefer: its bag slots are secure buttons, so the chassis is
        -- protected), as does this key reseat, so after an in-combat UI scale or
        -- window change both keep their old geometry until combat ends. Deliberate:
        -- it keeps Blizzard button reparenting and resizing out of combat. The
        -- deck's WIDTH follows the shown key count only from the reseat (FitDeck
        -- in SeatAndStyle), so it never changes ahead of the keys.
        FS.Layout.OnRescale(function()
            if InCombatLockdown() then
                applyPending = true
                return
            end
            SeatAndStyle()
        end)
    end
end)

-- Exported for the headless smoke test and /dump, not for other modules.
FS.MicroBars = {
    keys = keyList, ComputeVisual = ComputeVisual, Apply = Apply,
    KeyLayout = KeyLayout, Pitch = Pitch, RowWidth = RowWidth,
}

-- Verifies the micro buttons actually landed in the deck and picked up their
-- key overlay. Entries fill in at Apply.
FS.PanelSkins.RegisterRecon("MicroMenu", microRecon)
