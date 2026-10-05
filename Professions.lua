-- Forever Synthwave: Professions
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
-- UNVALIDATED in-game (no /fstack or visual check done yet).

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
-- itself (it rereads/rewrites ForeverSynthwaveDB.degradeLog[key] every call),
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
                "|cffff4488ForeverSynthwave|r: GetProfessions threw on first call, professions panel disabled")
        end
        return false
    end

    if prof1 then
        local ok2 = pcall(GetProfessionInfo, prof1)
        if not ok2 then
            if not loggedInitFailureProfessionInfo then
                loggedInitFailureProfessionInfo = true
                FS.LogDegradeOnce("professions_init",
                    "|cffff4488ForeverSynthwave|r: GetProfessionInfo threw on first call, professions panel disabled")
            end
            return false
        end
    end

    return true
end

-- IsSecret-guarded before any compare/format, same secret-first-then-nil-check
-- ordering as ForeverSynthwave.lua's GetReactionColor / FrameHelpers.lua's
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

-- One row: 20x20 icon, Mononoki name (left), Mononoki skill/max (right).
-- Text only, no pill/progress bar, per the design brief. All MAX_PROFESSIONS
-- rows are pre-built once and hidden/shown per refresh rather than
-- created/destroyed on demand -- WoW frames can't be destroyed anyway (see
-- XPBar.lua's SetVariant comment), and a fixed 6-row pool is cheap.
local function BuildRow(panel, index)
    local row = CreateFrame("Frame", nil, panel)
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
    row:Hide()
    return row
end

local panel
local rows

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
    label:SetText("synthwave://professions")
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

    panel = CreateFrame("Frame", "ForeverSynthwaveProfessions", UIParent)
    FS.Layout.Apply(panel, "professions")
    BuildChrome(panel)

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

-- Safe to call repeatedly (rebuild-in-place): re-reads GetProfessions/
-- GetProfessionInfo and re-populates/shows/hides the pre-built row pool.
-- Skips nil/unlearned slots entirely rather than rendering an empty row for
-- them.
local function RefreshRows()
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
                "|cffff4488ForeverSynthwave|r: GetProfessions threw on refresh, professions panel disabled")
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
                row:Show()
            elseif not ok2 and not loggedSlotFailure then
                -- A genuine throw for one specific occupied slot (as opposed
                -- to a merely-nil name, which just means "nothing to show
                -- for this slot yet" and is not logged) -- own guard so a
                -- second bad slot in the same refresh, or a later refresh
                -- hitting the same slot again, doesn't spam the saved log.
                loggedSlotFailure = true
                FS.LogDegradeOnce("professions_slot",
                    "|cffff4488ForeverSynthwave|r: GetProfessionInfo threw for slot " .. tostring(slotIndex))
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

-- ForeverSynthwaveDB.professionsHidden persists across sessions -- toggling
-- with /fsprof sticks on relog, same pattern as XPBar.lua's
-- ForeverSynthwaveDB.xpVariant / ActionBars.lua's barHideStrategy.
SLASH_FSPROF1 = "/fsprof"
SlashCmdList["FSPROF"] = function()
    local p = EnsurePanel()
    local wasShown = p:IsShown()

    ForeverSynthwaveDB = ForeverSynthwaveDB or {}
    ForeverSynthwaveDB.professionsHidden = wasShown

    if wasShown then
        p:Hide()
    else
        p:Show()
    end

    print(("|cff22e0ffForeverSynthwave|r: professions panel %s"):format(wasShown and "hidden" or "shown"))
end

-------------------------------------------------------------------------------
-- Recon
-------------------------------------------------------------------------------

FS.PanelSkins.RegisterRecon("Professions", {
    { name = "ForeverSynthwaveProfessions", guard = "fsBuilt" },
})

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

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

events:SetScript("OnEvent", function(_, event)
    if event == "SKILL_LINES_CHANGED" then
        if panel then RefreshRows() end
        return
    end

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
    -- XPBar.lua's login handler restoring ForeverSynthwaveDB.xpVariant
    -- before its first Build() -- guarded so a later PLAYER_ENTERING_WORLD
    -- (a later loading screen, or the second of the two login events) can't
    -- re-apply a stale saved value over a mid-session manual toggle.
    if not p.fsRestoredVisibility then
        p.fsRestoredVisibility = true
        local hidden = type(ForeverSynthwaveDB) == "table" and ForeverSynthwaveDB.professionsHidden
        if hidden then
            p:Hide()
        else
            p:Show()
        end
    end
end)
