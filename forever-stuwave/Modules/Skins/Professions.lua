-- Forever STUwave: Professions
-- Always-visible custom panel listing the player's learned professions
-- (name, icon, skill/max). Built CUSTOM (own CreateFrame chrome, not
-- Theme.SkinPanel) since there is no Blizzard frame here to strip -- same
-- reasoning as DataBar.lua's custom bottom strip.
--
-- API: GetProfessions()/GetProfessionInfo(index) are the LEGACY global pair
-- (confirmed present in the 16001 globals dump, lines ~24274-24275), not the
-- modern namespaced Professions.GetProfessionInfo() table call, which is a
-- different, newer API. Retail FrameXML corroborates the legacy signature:
-- ~/workspaces/reference/wow-ui-source-live-12.1.0/Interface/AddOns/
-- Blizzard_ArchaeologyUI/Blizzard_ArchaeologyUI.lua ~line 159-161:
--   local _, _, arch = GetProfessions();
--   local name, texture, rank, maxRank = GetProfessionInfo(arch);
-- GetProfessions() returns up to 6 slot indices (prof1, prof2, archaeology,
-- fishing, cooking, and POSSIBLY a 6th first-aid slot) -- the 6th slot is
-- UNVERIFIED, since retail 12.1.0 FrameXML only clearly corroborates 5; a nil
-- slot means that profession type is unlearned. GetProfessionInfo(index)'s
-- first four returns are named name/texture/rank/maxRank by retail source;
-- this file uses name/icon/skillLevel/maxSkillLevel instead, matching this
-- addon's own field-naming style (UnitFrames.lua's skillLevel-style fields).
--
-- No skill-line-scan fallback: GetNumSkillLines/GetSkillLineInfo are both
-- ABSENT from the 16001 globals dump (checked, zero hits), so there is no
-- alternate path to enumerate professions on this client if the legacy pair
-- above is ever unavailable -- the panel just renders empty in that case.
--
-- No CHAT_MSG_SKILL or TRADE_SKILL_UPDATE anywhere in this file.
--
-- UNVALIDATED in-game (no /fstack or visual check done yet), including that casting
-- each profession name (and Smelting for Mining) opens its window on this client.

local _, FS = ...

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local Theme = FS.Theme
local ApplyMono = Theme.ApplyMono
local AddOuterGlow = Theme.AddOuterGlow
local AddRoundedFill = Theme.AddRoundedFill
local AddGradientBorder = Theme.AddGradientBorder
local IsSecret = FS.IsSecret
local Config = FS.Config

-- Whether the panel is shown is a profile setting; /fsprof and the config window both write it.
local CFG_SHOWN = "professions.shown"
Config.RegisterDefault(CFG_SHOWN, true)

-- Minimised folds the rows into the title band; also a profile setting.
local CFG_MINIMIZED = "professions.minimized"
Config.RegisterDefault(CFG_MINIMIZED, false)

local function IsMinimized()
    return Config.Get(CFG_MINIMIZED) == true
end

-- Cyan, matching Tracker.lua's header accent (the closest analog -- a simple
-- read-only info panel) rather than the generic violet Theme.COLOR_BORDER
-- other panel chrome defaults to. Judgment call, not a design-doc token.
local ACCENT = Theme.COLOR_POWER

-------------------------------------------------------------------------------
-- Layout constants
-------------------------------------------------------------------------------

local MAX_PROFESSIONS = 6

local BAND_INSET = Theme.PanelBandInset() -- same inset as Theme.SkinPanel's title band (3 cut, 2 round)
local ROW_START_GAP = 8 -- gap below the title rule before the first row
local PAD_TOP = BAND_INSET + Theme.PANEL_HEADER_H + 1 + ROW_START_GAP
local ROW_HEIGHT = 28
local ROW_PAD_X = 10
local ICON_SIZE = 20
local ICON_TEXT_GAP = 6
local NAME_VALUE_GAP = 6

-- Minimised height: the title band, its rule, and the same inset below as above.
local COLLAPSED_H = BAND_INSET + Theme.PANEL_HEADER_H + 1 + BAND_INSET

-- The chat term bar's minimise glyph (pink, COLOR_HEALTH): same texture, size, edge gap and idle/hover alphas.
local GLYPH_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\icon_minimize.tga"
local GLYPH_SIZE = 16
local GLYPH_GAP = 4
local GLYPH_ALPHA = 0.85
local GLYPH_ALPHA_HOVER = 1.00
local GLYPH_COLOR = Theme.COLOR_HEALTH

-- Click action per row: an ALLOWLIST of English profession names mapped to the spell
-- whose cast opens that profession's window (Mining opens Smelting). Any other name,
-- including gatherers, Archaeology, localized and unknown names, gets no type attribute,
-- so a click does nothing and can never cast something unintended such as Fishing.
local SPELL_FOR_PROFESSION = {
    Alchemy = "Alchemy",
    Blacksmithing = "Blacksmithing",
    Enchanting = "Enchanting",
    Engineering = "Engineering",
    Leatherworking = "Leatherworking",
    Tailoring = "Tailoring",
    Cooking = "Cooking",
    ["First Aid"] = "First Aid",
    Jewelcrafting = "Jewelcrafting",
    Inscription = "Inscription",
    Mining = "Smelting",
}

-------------------------------------------------------------------------------
-- Feature detection + one-time API usability check
-------------------------------------------------------------------------------

local HAS_GET_PROFESSIONS = type(GetProfessions) == "function"
local HAS_GET_PROFESSION_INFO = type(GetProfessionInfo) == "function"

-- Whether the panel is allowed to try reading professions at all this
-- session. Starts false; ValidateProfessionsAPI flips it on once, at Init,
-- after proving both calls actually run rather than merely type-checking as
-- functions -- this addon's "hidden API" trap: a global can type-check as
-- callable and still throw when invoked ("X unavailable (hidden)").
local professionsUsable = false

-- Each failure site gets its OWN once-per-session guard boolean, checked
-- before calling FS.LogDegradeOnce -- that function does not dedupe by
-- itself (it rereads/rewrites ForeverSTUwaveDB.degradeLog[key] every call),
-- so without this a repeated failure (e.g. a later SKILL_LINES_CHANGED
-- refresh) would spam the saved log. Same idiom as every other
-- FS.LogDegradeOnce caller in this addon (see ErrorLog.lua's comment above
-- the function, or Diagnostics.lua's /fsfont).
local loggedInitFailureProfessions = false
local loggedInitFailureProfessionInfo = false
local loggedRefreshFailure = false
local loggedSlotFailure = false

-- Proves the API works rather than trusting the type() check: pcalls
-- GetProfessions() itself, then (only if a real slot came back) pcalls
-- GetProfessionInfo on that first slot too. A character with zero learned
-- professions has nothing to validate GetProfessionInfo against -- that is
-- not a failure, just an empty panel, so professionsUsable stays true and
-- RefreshRows below simply shows no rows.
local function ValidateProfessionsAPI()
    if not (HAS_GET_PROFESSIONS and HAS_GET_PROFESSION_INFO) then
        return false
    end

    local ok, prof1 = pcall(GetProfessions)
    if not ok then
        if not loggedInitFailureProfessions then
            loggedInitFailureProfessions = true
            FS.LogDegradeOnce("professions_init",
                "|cffff4488Forever STUwave|r: GetProfessions threw on first call, professions panel disabled")
        end
        return false
    end

    if prof1 then
        local ok2 = pcall(GetProfessionInfo, prof1)
        if not ok2 then
            if not loggedInitFailureProfessionInfo then
                loggedInitFailureProfessionInfo = true
                FS.LogDegradeOnce("professions_init",
                    "|cffff4488Forever STUwave|r: GetProfessionInfo threw on first call, professions panel disabled")
            end
            return false
        end
    end

    return true
end

-- IsSecret-guarded before any compare/format, same secret-first-then-nil-check
-- ordering as Nameplates.lua's GetReactionColor / FrameHelpers.lua's
-- UpdateCaretFull. Profession skill numbers are NOT expected to be secret in
-- practice -- this is precautionary/unverified insurance, not a known
-- secrecy case, same as everywhere else in this addon that touches a number
-- off a unit-adjacent API.
local function FormatSkill(skillLevel, maxSkillLevel)
    if IsSecret(skillLevel) or IsSecret(maxSkillLevel) then
        return "?/?"
    end
    if type(skillLevel) ~= "number" or type(maxSkillLevel) ~= "number" then
        return "?/?"
    end
    return ("%d/%d"):format(skillLevel, maxSkillLevel)
end

-------------------------------------------------------------------------------
-- Frame assembly
-------------------------------------------------------------------------------

local function ShowRowTooltip(row)
    local tip = GameTooltip
    if not tip or not row.fsProfession then return end
    tip:SetOwner(row, "ANCHOR_LEFT")
    tip:SetText(row.fsProfession, 1, 1, 1)
    if row.fsClickable then tip:AddLine("Click to open") end
    tip:Show()
end

local function HideRowTooltip(row)
    local tip = GameTooltip
    if tip and tip.GetOwner and tip:GetOwner() == row then tip:Hide() end
end

-- One row: 20x20 icon, Mononoki name (left), Mononoki skill/max (right). The row is a
-- secure button (AnyUp+AnyDown, the pairing every action button here uses) so a click
-- casts its profession; SetAttribute, Show and Hide on it are refused in combat.
-- Text only, no pill/progress bar, per the design brief. All MAX_PROFESSIONS
-- rows are pre-built once and hidden/shown per refresh rather than
-- created/destroyed on demand -- WoW frames can't be destroyed anyway (see
-- XPBar.lua's SetVariant comment), and a fixed 6-row pool is cheap.
local function BuildRow(panel, index)
    local row = CreateFrame("Button", nil, panel, "SecureActionButtonTemplate")
    row:RegisterForClicks("AnyUp", "AnyDown")
    row:SetHeight(ROW_HEIGHT)
    local y = -(PAD_TOP + (index - 1) * ROW_HEIGHT)
    row:SetPoint("TOPLEFT", panel, "TOPLEFT", ROW_PAD_X, y)
    row:SetPoint("TOPRIGHT", panel, "TOPRIGHT", -ROW_PAD_X, y)

    local icon = row:CreateTexture(nil, "ARTWORK")
    icon:SetSize(ICON_SIZE, ICON_SIZE)
    icon:SetPoint("LEFT", row, "LEFT", 0, 0)

    local value = row:CreateFontString(nil, "OVERLAY")
    ApplyMono(value, 11, ACCENT)
    value:SetJustifyH("RIGHT")
    value:SetPoint("RIGHT", row, "RIGHT", 0, 0)

    local name = row:CreateFontString(nil, "OVERLAY")
    ApplyMono(name, 11, Theme.COLOR_TEXT_WHITE)
    name:SetJustifyH("LEFT")
    -- Right edge pinned to the value text's left edge (not just anchored
    -- LEFT off the icon) so a long profession name can't overrun the
    -- skill/max reading -- same overlap concern UnitFrames.lua/PartyFrames.lua
    -- note for name FontStrings, cheaper here since there is no space-in-name
    -- wrap trap to also guard against (profession names are short, single or
    -- two-word strings, e.g. "First Aid").
    name:SetPoint("LEFT", icon, "RIGHT", ICON_TEXT_GAP, 0)
    name:SetPoint("RIGHT", value, "LEFT", -NAME_VALUE_GAP, 0)
    name:SetWordWrap(false)

    row.icon = icon
    row.name = name
    row.value = value
    row:HookScript("OnEnter", ShowRowTooltip)
    row:HookScript("OnLeave", HideRowTooltip)
    row:Hide()
    return row
end

local panel
local rows

-- Work that touched a secure button while in combat, replayed on PLAYER_REGEN_ENABLED.
local pendingInit = false
local pendingRefresh = false
local pendingVisible = nil -- nil, or the shown state a combat /fsprof asked for
local pendingMinimized = false -- the minimised setting changed in combat; the panel catches up at regen

local function GlyphText()
    return IsMinimized() and "Restore" or "Minimise"
end

-- The chat term bar's tooltip placement, so both minimise glyphs read alike; nil when the chat is not loaded.
local function ChatPlacer()
    return FS.Chat and FS.Chat.PlaceTermBarTooltip
end

local function ShowGlyphTooltip(button)
    local tip = GameTooltip
    if not tip then return end
    button.icon:SetVertexColor(GLYPH_COLOR[1], GLYPH_COLOR[2], GLYPH_COLOR[3], GLYPH_ALPHA_HOVER)
    local place = ChatPlacer()
    tip:SetOwner(button, place and "ANCHOR_NONE" or "ANCHOR_TOPRIGHT")
    tip:SetText(GlyphText(), GLYPH_COLOR[1], GLYPH_COLOR[2], GLYPH_COLOR[3])
    if place then place(button) end
    tip:Show()
end

local function HideGlyphTooltip(button)
    button.icon:SetVertexColor(GLYPH_COLOR[1], GLYPH_COLOR[2], GLYPH_COLOR[3], GLYPH_ALPHA)
    if GameTooltip then GameTooltip:Hide() end
end

-- A click or profile switch changes the state without firing OnEnter again, so an open tooltip is
-- rewritten in place.
local function RefreshGlyphTooltip()
    local tip = GameTooltip
    local button = panel and panel.fsMinimizeButton
    if not (button and tip and tip.GetOwner and tip:GetOwner() == button) then return end
    tip:SetText(GlyphText(), GLYPH_COLOR[1], GLYPH_COLOR[2], GLYPH_COLOR[3])
    local place = ChatPlacer()
    if place then place(button) end
end

local function OnGlyphClick()
    local alreadyParked = pendingMinimized
    local minimized = not IsMinimized()
    if not Config.Set(CFG_MINIMIZED, minimized) then
        print("|cff22e0ffForever STUwave|r: settings are read-only this session")
        return
    end
    -- Only the first click that parks a change says so; later clicks in the same fight stay quiet.
    if pendingMinimized and not alreadyParked then
        print(("|cff22e0ffForever STUwave|r: professions panel will be %s after combat"):format(minimized and "minimised" or "restored"))
    end
end

-- Chrome built directly on `panel` itself (it IS the shell -- there is no
-- separate inner fill StatusBar the way FrameHelpers.CreatePillBar's shell
-- wraps one): AddOuterGlow -> AddRoundedFill -> AddGradientBorder, in that
-- call order, matching CreatePillBar's shell assembly. Theme.PANEL_RADIUS (6)
-- is the panel-chrome radius token.
--
-- Title band/rule/label idiom copied from Theme.lua's SkinPanel title code
-- (~line 888-906) rather than calling SkinPanel itself, since SkinPanel skins
-- an EXISTING Blizzard frame and this panel has no Blizzard frame to strip.
local function BuildChrome(p)
    AddOuterGlow(p, ACCENT[1], ACCENT[2], ACCENT[3], 3, 0.25, Theme.PANEL_RADIUS)
    AddRoundedFill(p, Theme.COLOR_BG, Theme.PANEL_RADIUS)
    AddGradientBorder(p, ACCENT, 1, Theme.PANEL_RADIUS)

    local band = p:CreateTexture(nil, "ARTWORK")
    band:SetColorTexture(ACCENT[1], ACCENT[2], ACCENT[3], 0.08)
    band:SetPoint("TOPLEFT", p, "TOPLEFT", BAND_INSET, -BAND_INSET)
    band:SetPoint("TOPRIGHT", p, "TOPRIGHT", -BAND_INSET, -BAND_INSET)
    band:SetHeight(Theme.PANEL_HEADER_H)

    local rule = p:CreateTexture(nil, "ARTWORK")
    rule:SetColorTexture(ACCENT[1], ACCENT[2], ACCENT[3], 0.30)
    rule:SetPoint("TOPLEFT", band, "BOTTOMLEFT", 0, 0)
    rule:SetPoint("TOPRIGHT", band, "BOTTOMRIGHT", 0, 0)
    rule:SetHeight(1)

    local label = p:CreateFontString(nil, "OVERLAY")
    ApplyMono(label, 10, ACCENT)
    label:SetPoint("LEFT", band, "LEFT", 8, 0)
    label:SetText("stuwave://professions")

    return band
end

-- The minimise glyph: a plain Button (never secure) at the band's right end; the label keeps the left.
local function BuildGlyph(p, band)
    local button = CreateFrame("Button", nil, p)
    button:SetSize(GLYPH_SIZE, GLYPH_SIZE)
    button:SetPoint("RIGHT", band, "RIGHT", -GLYPH_GAP, 0)
    button:RegisterForClicks("LeftButtonUp")
    button:SetScript("OnClick", OnGlyphClick)
    button:SetScript("OnEnter", ShowGlyphTooltip)
    button:SetScript("OnLeave", HideGlyphTooltip)

    local icon = button:CreateTexture(nil, "ARTWORK")
    icon:SetTexture(GLYPH_TEXTURE)
    icon:SetAllPoints(button)
    icon:SetVertexColor(GLYPH_COLOR[1], GLYPH_COLOR[2], GLYPH_COLOR[3], GLYPH_ALPHA)
    button.icon = icon
    return button
end

-- Folds a seated panel to the title band, keeping its top edge where the full seat has it. The seat is
-- CENTER on CENTER, so the top sits h/2 above the seat's centre; another anchor only gets the height.
local function CollapseToBand(p)
    local L = FS.Layout.professions
    p:SetHeight(COLLAPSED_H)
    if not (L and L.point == "CENTER" and L.relPoint == "CENTER") then return end
    local scale = L.unscaled and 1 or FS.Layout.Scale()
    p:ClearAllPoints()
    p:SetPoint("TOP", UIParent, L.relPoint, L.x * scale, (L.y + L.h / 2) * scale)
end

local function SeatPanel(p)
    FS.Layout.Apply(p, "professions")
    if IsMinimized() then CollapseToBand(p) end
end

-- Idempotent via the `panel` upvalue: a second call (PLAYER_LOGIN and
-- PLAYER_ENTERING_WORLD can both fire at login) is a no-op past the first.
-- Fixed frame size from FS.Layout.professions -- this addon's other fixed-
-- height panels (TargetAuras.lua's aura containers, the chat terminal)
-- likewise accept that content can render past or short of the nominal box
-- rather than resizing the frame to the live profession count, so rows here
-- are top-anchored inside a fixed box too, never grown/shrunk to fit.
local function EnsurePanel()
    if panel then return panel end

    panel = CreateFrame("Frame", "ForeverSTUwaveProfessions", UIParent)
    SeatPanel(panel)
    local band = BuildChrome(panel)
    panel.fsMinimizeButton = BuildGlyph(panel, band)

    rows = {}
    for i = 1, MAX_PROFESSIONS do
        rows[i] = BuildRow(panel, i)
    end

    panel.fsBuilt = true
    return panel
end

-------------------------------------------------------------------------------
-- Refresh (initial build + SKILL_LINES_CHANGED)
-------------------------------------------------------------------------------

-- Writes the row's click action: the allowlisted spell, or no type at all.
local function ConfigureRowAction(row, name)
    local label = type(name) == "string" and not IsSecret(name) and name or nil
    local spell = label and SPELL_FOR_PROFESSION[label] or nil
    row.fsProfession = label
    row.fsClickable = spell ~= nil
    row:SetAttribute("type", spell and "spell" or nil)
    row:SetAttribute("spell", spell)
end

-- Safe to call repeatedly (rebuild-in-place): re-reads GetProfessions/
-- GetProfessionInfo and re-populates/shows/hides the pre-built row pool.
-- Skips nil/unlearned slots entirely rather than rendering an empty row for
-- them.
local function RefreshRows()
    -- Attributes, Show and Hide are all refused on the row buttons in combat, and a
    -- label that disagrees with its click is worse than a stale one, so all of it waits.
    if InCombatLockdown() then
        pendingRefresh = true
        return
    end
    pendingRefresh = false

    if not professionsUsable then
        for i = 1, MAX_PROFESSIONS do rows[i]:Hide() end
        return
    end

    local ok, prof1, prof2, archaeology, fishing, cooking, firstAid = pcall(GetProfessions)
    if not ok then
        -- A later throw this session, past the Init-time check above --
        -- degrade permanently rather than retry a call already proven
        -- broken (same reasoning as FrameHelpers.lua's curveHideBroken
        -- latch). The `professionsUsable = false` latch means this branch
        -- can only ever be entered once per session (every later RefreshRows
        -- call returns at the top, above), so loggedRefreshFailure never
        -- actually gets a SECOND failure to dedupe -- it is kept anyway for
        -- the same reason curveHideBroken's own report guard is: matching
        -- this addon's one-guard-boolean-per-FS.LogDegradeOnce-call-site
        -- idiom rather than special-casing this call site as the one that
        -- doesn't need it.
        professionsUsable = false
        if not loggedRefreshFailure then
            loggedRefreshFailure = true
            FS.LogDegradeOnce("professions_refresh",
                "|cffff4488Forever STUwave|r: GetProfessions threw on refresh, professions panel disabled")
        end
        for i = 1, MAX_PROFESSIONS do rows[i]:Hide() end
        return
    end

    -- Fixed-index table, not built via ipairs-friendly append: a plain
    -- numeric 1..MAX_PROFESSIONS loop below reads slots[i] directly, since
    -- ipairs would stop at the FIRST nil hole (e.g. prof1 unlearned but
    -- prof2 learned) rather than walking every slot.
    local slots = { prof1, prof2, archaeology, fishing, cooking, firstAid }

    local shown = 0
    local minimized = IsMinimized()
    for i = 1, MAX_PROFESSIONS do
        local slotIndex = slots[i]
        if slotIndex then
            local ok2, name, icon, skillLevel, maxSkillLevel = pcall(GetProfessionInfo, slotIndex)
            if ok2 and name then
                shown = shown + 1
                local row = rows[shown]
                row.icon:SetTexture(icon)
                row.name:SetText(name)
                row.value:SetText(FormatSkill(skillLevel, maxSkillLevel))
                ConfigureRowAction(row, name)
                if minimized then row:Hide() else row:Show() end
            elseif not ok2 and not loggedSlotFailure then
                -- A genuine throw for one specific occupied slot (as opposed
                -- to a merely-nil name, which just means "nothing to show
                -- for this slot yet" and is not logged) -- own guard so a
                -- second bad slot in the same refresh, or a later refresh
                -- hitting the same slot again, doesn't spam the saved log.
                loggedSlotFailure = true
                FS.LogDegradeOnce("professions_slot",
                    "|cffff4488Forever STUwave|r: GetProfessionInfo threw for slot " .. tostring(slotIndex))
            end
        end
    end

    for i = shown + 1, MAX_PROFESSIONS do
        rows[i]:Hide()
    end
end

-------------------------------------------------------------------------------
-- Slash command + persisted visibility
-------------------------------------------------------------------------------

-- Copies the legacy ForeverSTUwaveDB.professionsHidden into the active profile unless that profile stores a value,
-- then drops it so the next load cannot import it again. A profile pinned to the default (true) stores nothing, so
-- it can still take the legacy value. A read-only Config keeps it for a later session.
local function MigrateLegacy()
    local db = ForeverSTUwaveDB
    if type(db) ~= "table" or db.professionsHidden == nil then return end
    -- Setting a key to its current value changes nothing and answers whether settings are writable yet.
    if not Config.Set(CFG_SHOWN, Config.Get(CFG_SHOWN)) then return end
    if type(db.professionsHidden) == "boolean" and not Config.IsStored(CFG_SHOWN) then
        Config.Set(CFG_SHOWN, not db.professionsHidden)
    end
    db.professionsHidden = nil
end

local function ApplyVisible(p, visible)
    if visible then p:Show() else p:Hide() end
end

-- The state /fsprof toggles from: a request parked for combat wins, then the live
-- panel, then (panel not built yet) the setting.
local function CurrentlyVisible()
    if pendingVisible ~= nil then return pendingVisible end
    if panel then return panel:IsShown() end
    return Config.Get(CFG_SHOWN) == true
end

-- The one path every visibility change takes: the panel parents secure buttons, so Show and Hide on it are
-- refused in combat and wait for PLAYER_REGEN_ENABLED. Returns false when it was parked.
local function RequestVisible(visible)
    if InCombatLockdown() then
        pendingVisible = visible
        return false
    end
    pendingVisible = nil
    ApplyVisible(EnsurePanel(), visible)
    return true
end

-- A change from the config window or a profile switch. Until Setup has run, Setup reads the setting itself.
Config.OnChange(CFG_SHOWN, function(value)
    if not (panel and panel.fsRestoredVisibility) then return end
    RequestVisible(value == true)
end)

SLASH_FSPROF1 = "/fsprof"
SlashCmdList["FSPROF"] = function()
    local visible = not CurrentlyVisible()

    if not Config.Set(CFG_SHOWN, visible) then
        print("|cff22e0ffForever STUwave|r: settings are read-only this session")
        return
    end

    if not RequestVisible(visible) then
        print(("|cff22e0ffForever STUwave|r: professions panel will be %s after combat"):format(visible and "shown" or "hidden"))
        return
    end
    print(("|cff22e0ffForever STUwave|r: professions panel %s"):format(visible and "shown" or "hidden"))
end

-------------------------------------------------------------------------------
-- Minimise glyph + persisted minimised state
-------------------------------------------------------------------------------

-- The one path every minimise change takes. The panel parents secure rows, so resizing it and showing
-- or hiding them are refused in combat and wait for PLAYER_REGEN_ENABLED. Returns false when parked.
local function RequestMinimized()
    if not panel then return true end
    if InCombatLockdown() then
        pendingMinimized = true
        return false
    end
    pendingMinimized = false
    SeatPanel(panel)
    RefreshRows()
    return true
end

Config.OnChange(CFG_MINIMIZED, function()
    RefreshGlyphTooltip()
    RequestMinimized()
end)

-- A reseat (UI scale, resolution, /fsedit move or reset) re-applies the full seat first; this folds it again.
FS.Layout.OnRescale(function()
    if not (panel and IsMinimized()) then return end
    if InCombatLockdown() then
        pendingMinimized = true
        return
    end
    CollapseToBand(panel)
end)

-------------------------------------------------------------------------------
-- Recon
-------------------------------------------------------------------------------

FS.PanelSkins.RegisterRecon("Professions", {
    { name = "ForeverSTUwaveProfessions", guard = "fsBuilt" },
})

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

local function Setup()
    local p = EnsurePanel()

    -- Validated exactly once (first successful login event), regardless of
    -- which of PLAYER_LOGIN/PLAYER_ENTERING_WORLD fires first or whether
    -- both fire the same login -- `p.fsValidated` guards it the same way
    -- `p.fsRestoredVisibility` below guards the one-time visibility restore.
    if not p.fsValidated then
        p.fsValidated = true
        professionsUsable = ValidateProfessionsAPI()
    end

    RefreshRows()

    -- Restore the saved hidden state BEFORE the first Show, same idiom as
    -- XPBar.lua's login handler restoring ForeverSTUwaveDB.xpVariant
    -- before its first Build() -- guarded so a later PLAYER_ENTERING_WORLD
    -- (a later loading screen, or the second of the two login events) can't
    -- re-apply a stale saved value over a mid-session manual toggle.
    if not p.fsRestoredVisibility then
        p.fsRestoredVisibility = true
        ApplyVisible(p, Config.Get(CFG_SHOWN) == true)
    end
end

-- One event frame for both login-time events (per UnitFrames.lua's
-- WireEvents precedent for registering PLAYER_ENTERING_WORLD alongside other
-- events on a single frame) plus SKILL_LINES_CHANGED for the life of the
-- session. Neither event is unregistered after firing: EnsurePanel/
-- fsRestoredVisibility below are idempotent, so a PLAYER_ENTERING_WORLD that
-- fires again on every later loading screen just re-runs RefreshRows
-- harmlessly rather than double-building.
local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:RegisterEvent("PLAYER_ENTERING_WORLD")
events:RegisterEvent("SKILL_LINES_CHANGED")
events:RegisterEvent("PLAYER_REGEN_ENABLED")

events:SetScript("OnEvent", function(_, event)
    if event == "PLAYER_REGEN_ENABLED" then
        if pendingInit then
            pendingInit = false
            Setup()
        elseif pendingRefresh and panel then
            RefreshRows()
        end
        if pendingMinimized and panel then RequestMinimized() end
        if pendingVisible ~= nil then
            local visible = pendingVisible
            pendingVisible = nil
            ApplyVisible(EnsurePanel(), visible)
        end
        return
    end

    if event == "SKILL_LINES_CHANGED" then
        if panel then RefreshRows() end
        return
    end

    MigrateLegacy()

    -- The first build creates secure buttons and shows the panel, neither of which is
    -- allowed in combat (a /reload mid-fight), so it waits for PLAYER_REGEN_ENABLED.
    if InCombatLockdown() then
        pendingInit = true
        return
    end
    Setup()
end)
