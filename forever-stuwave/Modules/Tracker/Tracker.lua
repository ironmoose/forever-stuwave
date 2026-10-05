-- Forever STUwave: Tracker
-- UNVALIDATED in-game: no /fstack or visual check done yet.
--
-- BROAD-STROKES SECOND PASS. The first pass (recolor the two shared Font
-- objects plus a 2px hairline) is superseded here by full panel chrome: a
-- custom backdrop behind the whole tracker, a "stuwave://objectives" title
-- band replacing the container header, and a hidden-art + cyan-rule treatment
-- on every module header (Quests, Campaign, Achievements, ...). Per-block/
-- per-line internals (POI buttons, progress bars, item buttons, line dashes)
-- are UNVERIFIED in-game and stay untouched -- out of scope, see the bottom
-- comment.
--
-- Source citations below are all against
-- ~/workspaces/reference/wow-ui-source-live-12.1.0/Interface/AddOns/
-- Blizzard_ObjectiveTracker/ (retail 12.1.0), corroborated against the 16001
-- globals dump (~/workspaces/reference/wow-api-dump-16001/globals.txt) for
-- presence on THIS client. ElvUI's ObjectiveTracker skin
-- (~/workspaces/reference/ElvUI) was read for corroboration only, not cited
-- as a primary source.

local _, FS = ...

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local Theme = FS.Theme
local ApplyFontGeneric = Theme.ApplyFontGeneric
local ApplyMono = Theme.ApplyMono
local AddOuterGlow = Theme.AddOuterGlow
local AddRoundedFill = Theme.AddRoundedFill
local AddGradientBorder = Theme.AddGradientBorder
local COLOR_POWER = Theme.COLOR_POWER -- cyan; header accent, matches Chat.lua's selected-tab tint

-- Muted line color for body text: light enough to read against the tracker's
-- dark backdrop without competing with the cyan header.
local COLOR_LINE_MUTED = { 0.827, 0.827, 0.878, 1 } -- ~#d3d3e0

local MODULE_RULE_ALPHA = 0.45

-------------------------------------------------------------------------------
-- Shared Font objects (unchanged from the first pass)
-------------------------------------------------------------------------------

-- No addon display font is exposed on FS.Theme (only FONT_MONO), so the
-- header keeps its current font file and only gets the cyan recolor;
-- ApplyFontGeneric's own SetFont result-check falls back to that same path if
-- the re-apply somehow fails. This recolors BOTH the container header font
-- (unused now that Header.Text is hidden, see BuildContainerChrome) and every
-- module header font (QuestObjectiveTracker.Header.Text etc. all inherit this
-- same shared Font object per Blizzard_ObjectiveTrackerModule.xml:22 --
-- confirmed the module header FontString template inherits
-- "ObjectiveTrackerHeaderFont", same object as the container's), so module
-- headers get their cyan recolor for free from this one call.
local function StyleHeaderFont()
    local font = ObjectiveTrackerHeaderFont
    if not (font and font.SetFont and font.SetTextColor and font.GetFont) then return end

    local path, size, flags = font:GetFont()
    ApplyFontGeneric(font, path, size, COLOR_POWER, flags)
end

-- Line text switches to the addon's body/mono font (ApplyMono), muted color.
local function StyleLineFont()
    local font = ObjectiveTrackerLineFont
    if not (font and font.SetFont and font.SetTextColor and font.GetFont) then return end

    local _, size = font:GetFont()
    ApplyMono(font, size, COLOR_LINE_MUTED)
end

-------------------------------------------------------------------------------
-- Container chrome: backdrop + title band
-------------------------------------------------------------------------------

-- Content-height RECT signal: ObjectiveTrackerFrame's own GetHeight() is NOT
-- content-sized in normal play -- ObjectiveTrackerContainerMixin:UpdateHeight
-- (Blizzard_ObjectiveTrackerContainer.lua:189-210) only recomputes height from
-- content when the container is NOT in its default anchored position (edit
-- mode); the normal case derives height from a fixed anchor to UIParent, so
-- GetHeight() reports screen space, not used space. The container's own
-- "NineSlice" child (NineSlicePanelTemplate, Blizzard_ObjectiveTrackerContainer.xml:71-80)
-- IS the real signal: every ObjectiveTrackerContainerMixin:Update pass
-- repositions its BOTTOM to the last laid-out module's bottom minus
-- bottomModulePadding (Blizzard_ObjectiveTrackerContainer.lua:100), and its
-- fixed TOPLEFT/TOPRIGHT anchors span the header too, so its rect already
-- equals exactly the region Blizzard paints as the tracker's background.
-- Anchoring OUR backdrop to NineSlice's own points, rather than computing
-- content height ourselves, means we track every future layout pass for
-- free -- WoW resolves anchors live, no hook needed for the resize.
--
-- Show/hide signal is NOT NineSlice: Container:Update only ever calls
-- NineSlice:Show() (Blizzard_ObjectiveTrackerContainer.lua:101) -- nothing in
-- the source ever Hides it. The real "has content" switch is the CONTAINER
-- itself, ObjectiveTrackerFrame:Show()/Hide() (same file, lines 102/107): no
-- module produced content this pass -> the whole container Hides, UNLESS
-- edit mode is active (lines 103-106, EditModeManagerFrame:IsEditModeActive()),
-- which keeps it Shown even with nothing to display. Either way our backdrop
-- is parented to ObjectiveTrackerFrame, so it inherits whatever Show/Hide
-- state the container ends up in via ordinary parent-visibility cascade --
-- no hook of our own needed, and no separate edit-mode case to handle.
--
-- Fallback: if a future client build ever removes ObjectiveTrackerFrame.NineSlice,
-- BuildContainerChrome below anchors to the full ObjectiveTrackerFrame instead
-- -- never traces under a header/module at an unknown inset.
local function BuildContainerChrome()
    local frame = ObjectiveTrackerFrame
    if not (frame and frame.CreateTexture) then return end
    if frame.fsTrackerChromeBuilt then return end

    local header = frame.Header
    local nineSlice = frame.NineSlice
    local usingNineSlice = nineSlice and nineSlice.SetPoint and nineSlice.SetAlpha

    -- ObjectiveTrackerFrame declares frameStrata="LOW" in
    -- Blizzard_ObjectiveTracker.xml:3. A new CreateFrame does NOT inherit its
    -- parent's strata (it defaults to MEDIUM), so without this explicit
    -- SetFrameStrata our backdrop would render ABOVE the entire tracker
    -- regardless of frame level. Frame level is set to match the container's
    -- OWN level (frame:GetFrameLevel()), the same level NineSlice itself uses
    -- via its XML `useParentLevel="true"` (Blizzard_ObjectiveTrackerContainer.xml:71) --
    -- Header and every module frame are plain children with no such
    -- override, so their default level (parent level + 1) sits above this.
    local backdrop = CreateFrame("Frame", nil, frame)
    backdrop:SetFrameStrata(frame:GetFrameStrata())
    backdrop:SetFrameLevel(frame:GetFrameLevel())

    if usingNineSlice then
        backdrop:SetPoint("TOPLEFT", nineSlice, "TOPLEFT", 0, 0)
        backdrop:SetPoint("BOTTOMRIGHT", nineSlice, "BOTTOMRIGHT", 0, 0)
    else
        backdrop:SetPoint("TOPLEFT", frame, "TOPLEFT", 0, 0)
        backdrop:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", 0, 0)
    end

    -- Same call order as Professions.lua's BuildChrome: glow -> fill -> border.
    AddOuterGlow(backdrop, COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 3, 0.25, Theme.PANEL_RADIUS)
    AddRoundedFill(backdrop, Theme.COLOR_BG, Theme.PANEL_RADIUS)
    AddGradientBorder(backdrop, COLOR_POWER, 1, Theme.PANEL_RADIUS)

    -- Title band, sized to the container Header's own rect (32px,
    -- Blizzard_ObjectiveTrackerContainer.xml:19) so the band lines up with the
    -- real header regardless of the backdrop's total height. Parented to the
    -- backdrop (not the Header) so it stays behind the Header's own
    -- MinimizeButton, which must stay clickable/visible.
    if header then
        local band = backdrop:CreateTexture(nil, "ARTWORK")
        band:SetColorTexture(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.08)
        local bandInset = Theme.PanelBandInset()
        band:SetPoint("TOPLEFT", header, "TOPLEFT", bandInset, -bandInset)
        band:SetPoint("TOPRIGHT", header, "TOPRIGHT", -bandInset, -bandInset)
        band:SetHeight(Theme.PANEL_HEADER_H)

        local rule = backdrop:CreateTexture(nil, "ARTWORK")
        rule:SetColorTexture(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.30)
        rule:SetPoint("TOPLEFT", band, "BOTTOMLEFT", 0, 0)
        rule:SetPoint("TOPRIGHT", band, "BOTTOMRIGHT", 0, 0)
        rule:SetHeight(1)

        local label = backdrop:CreateFontString(nil, "OVERLAY")
        ApplyMono(label, 10, COLOR_POWER)
        label:SetPoint("LEFT", band, "LEFT", 10, 0)
        -- Right edge pinned off the MinimizeButton's left edge (when present)
        -- so the label can never run under it, same collision-avoidance idiom
        -- Professions.lua's BuildRow uses for name-vs-value.
        if header.MinimizeButton then
            label:SetPoint("RIGHT", header.MinimizeButton, "LEFT", -6, 0)
            label:SetWordWrap(false)
        end
        label:SetText("stuwave://objectives")

        -- Stock header background art + text hidden via SetAlpha(0), not
        -- Hide(): keeps Blizzard's own Show/Hide state (and anything that
        -- reads Header.Text's content) intact, only suppresses the pixels.
        -- Text is replaced rather than kept-and-recolored: the container
        -- Header's text ("Objectives"/localized) sitting directly under our
        -- own "stuwave://objectives" label would double up two overlapping
        -- captions in the same 32px band -- one label reads cleaner than two.
        if header.Background and header.Background.SetAlpha then
            header.Background:SetAlpha(0)
        end
        if header.Text and header.Text.SetAlpha then
            header.Text:SetAlpha(0)
        end
        -- MinimizeButton is left completely untouched: stays visible, stays
        -- functional, per scope.
    end

    -- Blizzard's own NineSlice background is alpha'd out (not Hidden) so our
    -- backdrop replaces it visually. No visibility hook needed: see the
    -- show/hide note above -- the backdrop's OWN Show() state stays true
    -- always, and it disappears exactly when ObjectiveTrackerFrame itself
    -- does, via ordinary parent-visibility cascade.
    if usingNineSlice then
        nineSlice:SetAlpha(0)
    end

    backdrop:Show()

    frame.fsTrackerChromeBuilt = true
end

-------------------------------------------------------------------------------
-- Module header chrome (Quests, Campaign, Achievements, Bonus, World Quest,
-- Scenario, Adventure, Monthly Activities, Initiative Tasks, UI Widget,
-- Professions Recipe)
-------------------------------------------------------------------------------

-- Every module frame is built from ObjectiveTrackerModuleTemplate
-- (Blizzard_ObjectiveTrackerModule.xml:71-97), whose Header child
-- (ObjectiveTrackerModuleHeaderTemplate, same file lines 11-69) is identical
-- across every module: a Background atlas texture, a Text FontString sharing
-- ObjectiveTrackerHeaderFont (already recolored cyan above), and a
-- MinimizeButton -- confirmed for ProfessionsRecipeTracker too
-- (Blizzard_ProfessionsRecipeTracker.xml:3, `inherits="ObjectiveTrackerModuleTemplate"`).
-- That shared template is why one loop below can treat all eleven module
-- names identically rather than special-casing any of them.
local MODULE_NAMES = {
    "QuestObjectiveTracker",
    "CampaignQuestObjectiveTracker",
    "AchievementObjectiveTracker",
    "BonusObjectiveTracker",
    "WorldQuestObjectiveTracker",
    "ScenarioObjectiveTracker",
    "AdventureObjectiveTracker",
    "MonthlyActivitiesObjectiveTracker",
    "InitiativeTasksObjectiveTracker",
    "UIWidgetObjectiveTracker",
    "ProfessionsRecipeTracker",
}

-- Hides one module's stock header background art and adds a thin cyan rule
-- under it. Header.Text itself is left alone -- it already reads cyan from
-- the shared-Font recolor above, no per-module text replacement needed the
-- way the container header got one. Idempotent via header.fsModuleHeaderSkin;
-- feature-detected per module (a global present but with no .Header, or a
-- .Header with no .Background, is skipped rather than erroring).
--
-- SetAtlas(nil) clears the texture itself rather than just alpha-hiding it:
-- ObjectiveTrackerModuleHeaderTemplate's own AddAnim animates Background's
-- alpha 0->1 (Blizzard_ObjectiveTrackerModule.xml:56-64, setToFinalAlpha="true"),
-- and PlayAddAnimation replays it from EndLayout on every empty-to-content
-- transition (Blizzard_ObjectiveTrackerModule.lua:210-211, 779-781) -- a new
-- quest, a new world quest, entering a scenario, all routine. A plain
-- SetAlpha(0) would just get overwritten back to 1 by that animation the
-- next time it plays. Clearing the atlas is flicker-free and permanent: no
-- retail Lua ever re-sets Background's atlas, and ElvUI's own tracker skin
-- does the same thing (ElvUI/Game/Mainline/Skins/ObjectiveTracker.lua:23,
-- `header.Background:SetAtlas(nil)`). The container Header's own Background
-- (BuildContainerChrome above) does NOT need this: ObjectiveTrackerContainerHeaderTemplate
-- has no AddAnim at all (Blizzard_ObjectiveTrackerContainer.xml:18-61) and
-- ObjectiveTrackerContainerHeaderMixin never re-sets it either, so a plain
-- SetAlpha(0) there is never undone.
local function StyleModuleHeader(moduleName)
    local module = _G[moduleName]
    if not module then return end

    local header = module.Header
    if not (header and header.CreateTexture) then return end
    if header.fsModuleHeaderSkin then return end

    if header.Background then
        if header.Background.SetAtlas then
            header.Background:SetAtlas(nil)
        elseif header.Background.SetTexture then
            header.Background:SetTexture(nil)
        end
    end

    local rule = header:CreateTexture(nil, "ARTWORK")
    rule:SetColorTexture(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], MODULE_RULE_ALPHA)
    rule:SetPoint("BOTTOMLEFT", header, "BOTTOMLEFT", 0, 0)
    rule:SetPoint("BOTTOMRIGHT", header, "BOTTOMRIGHT", 0, 0)
    rule:SetHeight(1)

    header.fsModuleHeaderSkin = true
end

local function StyleModuleHeaders()
    for _, name in ipairs(MODULE_NAMES) do
        StyleModuleHeader(name)
    end
end

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

-- Font objects, CreateTexture/CreateFrame calls, and SetAlpha are all
-- non-secure, so none of this is combat-illegal; deferred anyway for
-- consistency with the rest of the addon's Init pattern. Module frames
-- (QuestObjectiveTracker etc.) exist at file-load time regardless of whether
-- they have ever displayed content, so StyleModuleHeaders needs no
-- ADDON_LOADED/load-on-demand watch the way e.g. AuctionHouse.lua's panels do.
local function Apply()
    StyleHeaderFont()
    StyleLineFont()
    BuildContainerChrome()
    StyleModuleHeaders()
end

FS.PanelSkins.RegisterRecon("Tracker", {
    { name = "ObjectiveTrackerFrame", guard = "fsTrackerChromeBuilt" },
})

FS.PanelSkins.DeferCombat(Apply)

-------------------------------------------------------------------------------
-- Left alone (out of scope this pass)
-------------------------------------------------------------------------------
-- Per-block/per-line mixin internals: POI buttons, progress bars, item
-- buttons, line dashes. These are UNVERIFIED in-game and the block/line frame
-- structure inside a module's ContentsFrame is fragile enough (pooled,
-- recycled per layout pass -- ObjectiveTrackerModuleMixin:BeginLayout/EndLayout,
-- Blizzard_ObjectiveTrackerModule.lua:169-217) that surgery there is real
-- follow-up work, not broad strokes. Progress bars specifically were left
-- alone rather than given a "trivial, clearly-confirmed field" restyle: no
-- such field was found without opening BonusObjectiveTrackerProgressBarMixin's
-- own layout, which is exactly the fragile territory this pass is avoiding.
-- Quest item buttons are additionally SECURE (per the combat/taint note
-- above) and must never be touched at all.
