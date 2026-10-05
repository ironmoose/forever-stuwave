-- Forever STUwave: Panels
-- FIRST PASS synthwave PANEL skin for the standard Blizzard windows: applies
-- the shared FS.Theme.SkinPanel backdrop/border/glow treatment to a list of
-- feature-detected frames. Confirmed present at login on this client
-- (interface 16001): CharacterFrame, PaperDollFrame, MerchantFrame, MailFrame,
-- BankFrame, TradeFrame, QuestFrame, FriendsFrame, WorldMapFrame,
-- ItemTextFrame, ChannelFrame, SettingsPanel, CollectionsJournal,
-- CommunitiesFrame, AddonList, TimeManagerFrame, TaxiFrame, FlightMapFrame,
-- GuildRegistrarFrame, PetitionFrame (2026-09-24 coverage sweep; see CLAUDE.md
-- for the 6 frames deliberately excluded from this sweep). The rest are
-- load-on-demand (nil until their Blizzard_* module loads) and picked up by
-- the ADDON_LOADED/PLAYER_ENTERING_WORLD re-scan below; every name is
-- feature-detected, so a missing frame silently no-ops rather than erroring.

local _, FS = ...

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local SkinPanel = FS.Theme.SkinPanel
local StyleMoney = FS.Theme.StyleMoney
local ApplyMono = FS.Theme.ApplyMono
local COLOR_BG = FS.Theme.COLOR_BG
local COLOR_BORDER = FS.Theme.COLOR_BORDER
local COLOR_POWER = FS.Theme.COLOR_POWER
local COLOR_TEXT_PARCHMENT = FS.Theme.COLOR_TEXT_PARCHMENT

if not FS.PanelSkins.RequireExport(SkinPanel, "Panels.lua disabled: FS.Theme.SkinPanel missing") then return end

-------------------------------------------------------------------------------
-- Target list
-------------------------------------------------------------------------------

-- Global frame name, plus an optional money-frame global to restyle alongside
-- the panel skin (StyleMoney no-ops if that name doesn't exist either).
local PANEL_FRAMES = {
    -- Confirmed present at login (interface 16001).
    { name = "CharacterFrame", title = "character" },
    { name = "PaperDollFrame" },
    { name = "MerchantFrame", money = "MerchantMoneyFrame", title = "vendor" },
    { name = "MailFrame", title = "mail" },
    { name = "BankFrame", title = "bank" },
    { name = "TradeFrame", title = "trade" },
    { name = "QuestFrame", title = "quest" },
    { name = "FriendsFrame", title = "social" },
    { name = "WorldMapFrame", title = "map" },
    { name = "ItemTextFrame", title = "manuscript" },

    -- 2026-09-24 coverage sweep -- also confirmed present at login (16001
    -- globals dump); retail template citations for each live in CLAUDE.md.
    { name = "ChannelFrame", title = "channels" },
    { name = "SettingsPanel", title = "settings" },
    { name = "CollectionsJournal", title = "collections" },
    { name = "CommunitiesFrame", title = "communities" },
    { name = "AddonList", title = "addons" },
    { name = "TimeManagerFrame", title = "clock" },
    -- Full rationale in CLAUDE.md; short pointers only below.
    -- TaxiFrame: its direct InsetBg is the taxi map texture; preserve it
    -- while stripping the rest of BasicFrameTemplateWithInset's chrome.
    -- FlightMapFrame: MapCanvasFrameTemplate, border chrome on a nested
    -- parentKey BorderFrame child unreached by the non-recursive strip (same
    -- accepted limitation as WorldMapFrame).
    { name = "TaxiFrame", title = "taxi" },
    { name = "FlightMapFrame", title = "flightmap" },
    { name = "GuildRegistrarFrame", title = "charter" },
    { name = "PetitionFrame", title = "petition" },

    -- Load-on-demand: nil until the owning Blizzard_* module loads. Picked up
    -- by the re-scan in the Init section below.
    { name = "SpellBookFrame", title = "spellbook" },
    { name = "PlayerSpellsFrame", title = "spellbook" },
    { name = "QuestMapFrame", title = "questlog" },
    { name = "QuestLogPopupDetailFrame", title = "quest.detail" },
    { name = "PlayerTalentFrame", title = "talents" },
    { name = "TalentFrame", title = "talents" },
    { name = "InspectFrame", title = "inspect" },
    { name = "TradeSkillFrame", title = "profession" },
    { name = "ProfessionsFrame", title = "profession" },
    { name = "GossipFrame", title = "dialog" },
    { name = "PVPFrame", title = "pvp" },
    { name = "MacroFrame", title = "macro" },
    { name = "ClassTrainerFrame", title = "trainer" },
}

-- DELIBERATELY EXCLUDED from PANEL_FRAMES (2026-09-24 sweep).
-- Full rationale in CLAUDE.md; short pointers only below.
-- CalendarFrame -- bespoke ad hoc corner/edge Texture chrome, no
-- NineSlice/Inset/Bg field (Blizzard_Calendar.xml); template-family mismatch.
-- AchievementFrame -- same bespoke chrome family as CalendarFrame
-- (Blizzard_AchievementUI.xml); same exclusion reason.
-- DressUpFrame -- ModelBackground is a direct Texture region
-- (DressUpFrames.xml:432), hidden by the generic strip along with the model
-- backdrop.
-- TabardFrame -- TabardFrameEmblemTopLeft/TopRight/BottomLeft/BottomRight are
-- direct alphaMode="ADD" Texture regions (TabardFrame.xml:152-176) Blizzard
-- only ever SetAlpha()s, never Show()s -- no re-show event to recover a Hide().
-- ItemSocketingFrame -- bespoke parchment/border art layered on
-- ButtonFrameTemplate (Blizzard_ItemSocketingUI.xml:143-242+), same bespoke
-- family as Calendar/Achievement.
-- LFGParentFrame -- template unverified against the retail 12.1.0 source tree
-- (absent entirely); excluded on the unverified-template bar, unlike
-- Calendar/Achievement, which ARE verified.

-- Content-child strip/hide/retint specs (FS.PanelSkins.ApplyGuts), one entry
-- per PANEL_FRAMES parent that leaves leftover parchment on its own children.
-- MailItem1..7 are the ROW frames, never MailItemNButton: that CheckButton's
-- Texture regions include the item icon, which StripBlizzardChrome's region
-- sweep would hide right along with the row's own chrome.
local MAIL_ITEM_NAMES = {
    "MailItem1", "MailItem2", "MailItem3", "MailItem4", "MailItem5",
    "MailItem6", "MailItem7",
}

-- Mail's strip list: the panel-level content children plus every MailItemN
-- row, built from MAIL_ITEM_NAMES so the row list has one source (also read
-- by the mail-list-repopulation watcher below).
local MAIL_STRIP_NAMES = {
    "InboxFrame", "MailFrameInset", "OpenMailFrame", "OpenMailFrameInset",
    "OpenMailScrollFrame", "SendMailFrame", "SendMailMoneyInset",
}
for _, name in ipairs(MAIL_ITEM_NAMES) do
    MAIL_STRIP_NAMES[#MAIL_STRIP_NAMES + 1] = name
end

-- QuestFrame's four NPC-dialog sub-panels (detail/greeting/progress/reward)
-- plus their scroll frames. Action buttons (Accept/Decline/Complete/Goodbye)
-- and reward item buttons are NOT stripped -- their Texture regions carry the
-- button art and item icon, which StripBlizzardChrome's region sweep would
-- hide right along with the parchment. QuestInfoItemHighlight is a highlight
-- frame, left alone for the same reason. QuestInfoRewardsFrame's own
-- header/choose/receive text are parentKey fields, not globals, so they
-- resolve through ApplyGuts' "Frame.field" path support rather than a second
-- `_G` lookup, and are feature-detected the same as every other name here.
local QUEST_GUTS = {
    parent = "QuestFrame",
    strip = {
        "QuestFrameDetailPanel", "QuestFrameGreetingPanel", "QuestFrameProgressPanel",
        "QuestFrameRewardPanel", "QuestDetailScrollFrame", "QuestDetailScrollChildFrame",
        "QuestGreetingScrollFrame", "QuestRewardScrollFrame", "QuestRewardScrollChildFrame",
        "QuestProgressScrollFrame",
    },
    retint = {
        { name = "QuestInfoTitleHeader" },
        { name = "QuestInfoObjectivesHeader" },
        { name = "QuestInfoDescriptionText" },
        { name = "QuestInfoObjectivesText" },
        { name = "QuestInfoRewardText" },
        { name = "QuestProgressTitleText" },
        { name = "QuestProgressText" },
        { name = "QuestProgressRequiredItemsText" },
        { name = "QuestProgressRequiredMoneyText" },
        { name = "GreetingText" },
        { name = "CurrentQuestsText" },
        { name = "AvailableQuestsText" },
        { name = "QuestInfoRewardsFrame.Header" },
        { name = "QuestInfoRewardsFrame.ItemChooseText" },
        { name = "QuestInfoRewardsFrame.ItemReceiveText" },
    },
}

-- QuestMapFrame's map-embedded quest log. QuestMapFrame is already in
-- PANEL_FRAMES, so its own direct-region chrome is free via the generic
-- SkinPanel/StripBlizzardChrome sweep; QUESTMAP_GUTS covers only nested
-- frames that non-recursive sweep can't reach: QuestScrollFrame (the quest
-- list) and its BorderFrame, and QuestMapFrame.DetailsFrame plus its own
-- BorderFrame/BackFrame/RewardsFrameContainer.RewardsFrame. StoryHeader
-- (the active-campaign banner) gets a targeted `hide` on just its
-- `Background` region rather than a `strip` on the whole frame --
-- StoryHeader also carries a `HighlightTexture` hover-highlight region
-- toggled by its own OnEnter/OnLeave, which a blanket strip would have
-- permanently suppressed. No retint entry: DetailsFrame's text reuses the
-- same shared QuestInfo_* fontstrings QUEST_GUTS already retints.
-- QuestLogPopupDetailFrame gets no entry -- already covered by
-- PANEL_FRAMES and those same shared fontstrings.
local QUESTMAP_GUTS = {
    parent = "QuestMapFrame",
    strip = {
        "QuestScrollFrame",
        "QuestScrollFrame.BorderFrame",
        "QuestMapFrame.DetailsFrame",
        "QuestMapFrame.DetailsFrame.BorderFrame",
        "QuestMapFrame.DetailsFrame.BackFrame",
        "QuestMapFrame.DetailsFrame.RewardsFrameContainer.RewardsFrame",
    },
    hide = {
        { name = "QuestScrollFrame.Contents.StoryHeader.Background" },
    },
}

-- One-time per-row setup for a gossip ScrollBox row (FS.PanelSkins.ApplyGuts'
-- `rows.perRow`, called on every acquired row); guarded by
-- `button.fsGossipRowSkinned` since the ScrollBox reuses row frames across
-- passes, row icons untouched either way. Row templates are fixed per
-- `buttonType` (GossipGreetingTextTemplate / GossipTitleOptionButtonTemplate /
-- GossipTitleActiveQuestButtonTemplate / GossipTitleAvailableQuestButtonTemplate
-- / GossipSpacerFrameTemplate), so a greeting row always carries `.GreetingText`
-- and every other text-bearing row always exposes `GetFontString` -- the
-- divider template matches neither branch, which is correct, since it carries
-- no text. Both branches retint AND install `FS.PanelSkins.HookInlineColorRewrite`
-- (ElvUI's Gossip.lua fixes the same dark-inline-code problem with a fixed
-- swatch; the shared luma-gated helper here catches any dark code, not just
-- the two hardcoded ones, and is also what ClassTrainerFrame's rows use).
-- This runs after Blizzard already set the row text, so the helper also
-- rewrites the text the row holds when it is installed.
local function GossipRowUpdateChild(button)
    if button.fsGossipRowSkinned then return end
    button.fsGossipRowSkinned = true

    if button.GreetingText then
        FS.PanelSkins.RetintDarkText(button.GreetingText)
        FS.PanelSkins.HookInlineColorRewrite(button.GreetingText)
        return
    end

    local fontString = button.GetFontString and button:GetFontString()
    if fontString then
        FS.PanelSkins.RetintDarkText(fontString)
        FS.PanelSkins.HookInlineColorRewrite(button)
    end
end

-- GossipFrame's NPC dialog panel (GreetingPanel): strips its own parchment
-- chrome only -- ScrollBox/ScrollBar/GoodbyeButton are child FRAMES, not
-- Texture regions, so StripBlizzardChrome's non-recursive sweep leaves them
-- alone and functional. Row text (title/option/quest buttons, the greeting
-- text itself) is handled through `rows`, since Blizzard rebuilds the
-- ScrollBox's data provider -- and therefore its row text -- on every dialog
-- page, long after this spec's own strip pass has already run once.
local GOSSIP_GUTS = {
    parent = "GossipFrame",
    strip = { "GossipFrame.GreetingPanel" },
    rows = {
        scrollBox = "GossipFrame.GreetingPanel.ScrollBox",
        perRow = GossipRowUpdateChild,
    },
}

-- One-time per-row setup for a ClassTrainerFrame ScrollBox row; ROWS OF
-- DIFFERENT TEMPLATES ARE POOLED SEPARATELY, so `button.fsTrainerRowSkinned`
-- stays a valid one-time guard even though a skill-service row and a
-- CATEGORY-header row (`ClassTrainerCategoryButtonMixin`, confirmed on 16001
-- but in neither reference FrameXML) both reach this same function -- every
-- field below is feature-detected rather than assumed, and a bare
-- `GetFontString`/`.Text`/`.Label` fallback covers a category row's own
-- label, which carries none of `.disabledBG`/`.selectedTex`/`.name`/
-- `.subText`/`.money`. Row money (`.money`/`.GoldButton` etc.) is left
-- untouched: Blizzard's own money-button text defaults to white, not dark
-- parchment ink, so there is nothing to retint, and hooking it would only
-- risk fighting the same red "can't afford" `SetMoneyFrameColor` the
-- `Theme.IsDarkText` fix below protects elsewhere.
local function TrainerRowUpdateChild(button)
    if button.fsTrainerRowSkinned then return end
    button.fsTrainerRowSkinned = true

    -- Clears the texture (ElvUI's own fix, `button.disabledBG:SetTexture()`)
    -- rather than :Hide(): retail Blizzard_TrainerUI.lua's InitServiceButton
    -- calls disabledBG:Show()/Hide() on every row repopulation, so a Hide()
    -- here would only last until Blizzard's own next repopulation reverses
    -- it, while an emptied texture draws nothing regardless of Show state.
    if button.disabledBG and button.disabledBG.SetTexture then button.disabledBG:SetTexture(nil) end
    if button.selectedTex and COLOR_POWER then
        button.selectedTex:SetVertexColor(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3])
    end

    if button.name then
        FS.PanelSkins.RetintDarkText(button.name)
        -- Retail Blizzard_TrainerUI.lua embeds GRAY_FONT_COLOR_CODE (luma
        -- ~0.5, above the dark-text gate) into a "used"/on-cooldown row's own
        -- `.name`, the same inline-code pattern GossipFrame's rows use.
        FS.PanelSkins.HookInlineColorRewrite(button.name)
    elseif not button.subText then
        -- Neither field exists: likely a category-header row, a different
        -- template entirely. `GetFontString` covers a plain Button-derived
        -- label; `.Text`/`.Label` cover a Frame-based category header that
        -- carries no button methods at all.
        local label = (button.GetFontString and button:GetFontString()) or button.Text or button.Label
        if label then FS.PanelSkins.RetintDarkText(label) end
    end
    if button.subText then
        FS.PanelSkins.RetintDarkText(button.subText)
    end
end

-- ClassTrainerStatusBar (skill-rank progress meter): strips its own
-- Left/Middle/Right border chrome and the flat blue `Background` tint (all
-- confirmed 16001 globals), then repaints the fill with `Theme.FLAT_TEXTURE`
-- + the same cyan token the rows' selection highlight uses, and retints the
-- rank text. Feature-detected as a whole; skipped entirely if the bar itself
-- is absent.
local function SkinTrainerStatusBar()
    local bar = _G.ClassTrainerStatusBar
    if not bar then return end

    FS.PanelSkins.HideNamed({
        { name = "ClassTrainerStatusBarLeft" },
        { name = "ClassTrainerStatusBarMiddle" },
        { name = "ClassTrainerStatusBarRight" },
        { name = "ClassTrainerStatusBarBackground" },
    })

    if bar.SetStatusBarTexture then bar:SetStatusBarTexture(FS.Theme.FLAT_TEXTURE) end
    if bar.SetStatusBarColor and COLOR_POWER then
        bar:SetStatusBarColor(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], COLOR_POWER[4] or 1)
    end
end

-- ClassTrainerFrame's NPC-trainer window: the main body inset resolves
-- generically through `Theme.StripBlizzardChrome`'s own `frame.Inset` sweep
-- once `ClassTrainerFrame` is in `PANEL_FRAMES` (no entry needed here);
-- `ClassTrainerFrameBottomInset` is a separate, secondary inset (present on
-- 16001) the generic sweep doesn't reach, stripped explicitly, and
-- `ClassTrainerFrameMoneyBg` gets the same `alpha0` treatment as ItemText's
-- corner materials, since Blizzard re-Shows it outside our own OnShow.
-- `ClassTrainerFrameName`/`NameSubText`/`SubText`/`GoldButtonText`/
-- `SilverButtonText`/`CopperButtonText` are DELIBERATELY not retinted here:
-- ScrollBox rows are anonymous, and `$parentName` etc. in the retail row
-- template (`ClassTrainerSkillButtonTemplate`) resolves through the nearest
-- NAMED ancestor when the immediate parent has none, which is `ClassTrainerFrame`
-- itself -- those globals are really "whichever row was built last", not a
-- frame-level field, and retinting them would only ever touch one arbitrary
-- row rather than every row (`rows`' `perRow`, below, is what actually
-- reaches every row). The SkillStepButton's Name/SubText are a REAL named
-- button's own fields (not pooled), so they are retinted directly and
-- safely; its Gold/Silver/CopperButtonText are NOT retinted -- money text
-- defaults to white, never dark parchment ink, so there is nothing to fix,
-- and `Theme.StyleMoney(ClassTrainerFrameSkillStepButton)` (below) already
-- owns that text without a hook that could fight Blizzard's own red
-- "can't afford" `SetMoneyFrameColor`.
local TRAINER_GUTS = {
    parent = "ClassTrainerFrame",
    strip = { "ClassTrainerFrameBottomInset" },
    hide = {
        { name = "ClassTrainerFrameMoneyBg", alpha0 = true },
    },
    retint = {
        { name = "ClassTrainerFrameTitleText" },
        { name = "ClassTrainerFrameTrainingPointsLabel" },
        { name = "ClassTrainerFrameSkillStepButtonName" },
        { name = "ClassTrainerFrameSkillStepButtonNameSubText" },
        { name = "ClassTrainerFrameSkillStepButtonSubText" },
        { name = "ClassTrainerStatusBarSkillRank" },
        { name = "ClassTrainerTrainButtonText" },
    },
    rows = {
        scrollBox = "ClassTrainerFrame.ScrollBox",
        perRow = TrainerRowUpdateChild,
    },
}

-- ProfessionsFrame.CraftingPage: retail Blizzard_ProfessionsFrame.xml:14
-- (parentKey page, built the moment ProfessionsFrame itself is). Full
-- path-by-path rationale lives in CLAUDE.md; short pointers only below.
-- UNVERIFIED in-game: no /fstack or visual check done yet.
--
-- RecipeList: strips its own `Background` (Blizzard_ProfessionsRecipeList.xml:9-11)
-- and `BackgroundNineSlice` (xml:15-23 -- named that, not "NineSlice", so the
-- generic chrome sweep can't reach it on its own).
-- SchematicForm.NineSlice: named "NineSlice" (Blizzard_ProfessionsCrafting.xml:184-186),
-- so a plain strip clears it.
-- SchematicForm.Background/.MinimalBackground: `alpha0` -- Blizzard toggles
-- them with plain Show()/Hide() (Blizzard_ProfessionsCrafting.lua:926-939,
-- not an animated alpha), and SetAlpha(0) is independent of shown state, so
-- it survives every later Show()/Hide() toggle with no hook needed.
-- SchematicForm.Details: strips its three BackgroundTop/Middle/Bottom atlas
-- textures (Blizzard_ProfessionsRecipeCrafterDetails.xml:85-108); non-recursive,
-- so its child stat-line frames are untouched.
--
-- No `retint` entry: SchematicForm's own text and the reagent-container
-- `.Label` fields are all gold/white by default (Blizzard_Fonts_Shared
-- Shared/FontStyles.xml:50-62,281, Mainline/FontStyles.xml:275), well outside
-- `Theme.IsDarkText`'s gate -- this page was never a parchment surface.
local function ApplyProfessionsCategoryFont(label)
    if not ApplyMono then return end
    local _, size = label:GetFont()
    ApplyMono(label, size or 12)
end

-- One-time per-row setup for a RecipeList ScrollBox row
-- (FS.PanelSkins.ApplyGuts' `rows.perRow`); category rows (`.CollapseIcon`)
-- vs recipe rows (`.Count`), pooled separately, neither exposing the other's
-- fields (Blizzard_ProfessionsRecipeList.xml:96-138/200-215). `.Label`/`.Count`
-- color is `SetVertexColor`, never `SetTextColor` (Blizzard_ProfessionsRecipeList.lua:198,
-- :347-348), which `ApplyMono`'s own `SetTextColor` never touches, so a
-- one-time guarded font pass is safe forever on a reused pooled row -- full
-- reasoning in CLAUDE.md. Category rows also swap FontObject on hover (same
-- file:179/187), so `.Label`'s `SetFontObject` is hooked to re-assert Mono;
-- recipe rows have no such call. `.SelectedOverlay`/`.HighlightOverlay` and
-- the category row's own rank StatusBar are untouched (state, not chrome).
local function ProfessionsRowUpdateChild(button)
    if not ApplyMono then return end
    if button.fsProfessionsRowSkinned or not button.Label then return end
    button.fsProfessionsRowSkinned = true

    if button.CollapseIcon then
        -- Category header row.
        ApplyProfessionsCategoryFont(button.Label)
        hooksecurefunc(button.Label, "SetFontObject", ApplyProfessionsCategoryFont)
    elseif button.Count then
        -- Recipe row.
        local _, size = button.Label:GetFont()
        ApplyMono(button.Label, size or 12)
        local _, countSize = button.Count:GetFont()
        ApplyMono(button.Count, countSize or 12)
    end
end

local PROFESSIONS_CRAFTING_GUTS = {
    parent = "ProfessionsFrame",
    strip = {
        "ProfessionsFrame.CraftingPage.RecipeList",
        "ProfessionsFrame.CraftingPage.RecipeList.BackgroundNineSlice",
        "ProfessionsFrame.CraftingPage.SchematicForm.NineSlice",
        "ProfessionsFrame.CraftingPage.SchematicForm.Details",
    },
    hide = {
        { name = "ProfessionsFrame.CraftingPage.SchematicForm.Background", alpha0 = true },
        { name = "ProfessionsFrame.CraftingPage.SchematicForm.MinimalBackground", alpha0 = true },
    },
    rows = {
        scrollBox = "ProfessionsFrame.CraftingPage.RecipeList.ScrollBox",
        perRow = ProfessionsRowUpdateChild,
    },
}

local PANEL_GUTS = {
    {
        parent = "ItemTextFrame",
        strip = { "ItemTextScrollFrame" },
        hide = {
            { name = "ItemTextMaterialTopLeft", alpha0 = true },
            { name = "ItemTextMaterialTopRight", alpha0 = true },
            { name = "ItemTextMaterialBotLeft", alpha0 = true },
            { name = "ItemTextMaterialBotRight", alpha0 = true },
        },
        retint = {
            { name = "ItemTextPageText", opts = { simpleHTML = true, textTypes = { "P", "H1", "H2", "H3" } } },
            { name = "ItemTextCurrentPage" },
        },
    },
    {
        parent = "MailFrame",
        strip = MAIL_STRIP_NAMES,
        hide = {
            { name = "SendStationeryBackgroundLeft" },
            { name = "SendStationeryBackgroundRight" },
        },
    },
    QUEST_GUTS,
    QUESTMAP_GUTS,
    GOSSIP_GUTS,
    TRAINER_GUTS,
    PROFESSIONS_CRAFTING_GUTS,
}

-------------------------------------------------------------------------------
-- Mail list repopulation
-------------------------------------------------------------------------------

-- Classic InboxFrame_Update does not exist on this client, so there is
-- nothing to hook there. MAIL_INBOX_UPDATE and InboxFrame's own OnShow are
-- what actually fire when the mail list repopulates; StripNamed is cheap
-- (StripBlizzardChrome self-guards per frame), so re-running it on both costs
-- nothing.
local function RestripMailItems()
    FS.PanelSkins.StripNamed(MAIL_ITEM_NAMES)
end

local mailWatcher = CreateFrame("Frame")
if pcall(mailWatcher.RegisterEvent, mailWatcher, "MAIL_INBOX_UPDATE") then
    mailWatcher:SetScript("OnEvent", RestripMailItems)
end

-- InboxFrame is confirmed present at login on this client, but the attempt is
-- retried from afterScan (below) rather than once at file load, in case that
-- ever isn't true; `inboxHookAttempted` stops HookShowOnce's own call from
-- being retried once InboxFrame has been found.
local inboxHookAttempted = false
local function TryHookInboxOnShow()
    if inboxHookAttempted then return end
    local inboxFrame = _G.InboxFrame
    if inboxFrame then
        FS.PanelSkins.HookShowOnce(inboxFrame, "fsInboxRestripHooked", RestripMailItems)
        inboxHookAttempted = true
    end
end

-------------------------------------------------------------------------------
-- Quest dialog repopulation
-------------------------------------------------------------------------------

-- QuestInfoObjective1..N are created on demand inside QuestInfo_Display, so
-- they carry no static QUEST_GUTS retint entry; the dump confirms
-- QuestInfoObjective1 exists, so a bounded loop covers whatever count a given
-- quest actually populates.
local QUEST_OBJECTIVE_MAX = 10

local function RetintQuestObjectives()
    for i = 1, QUEST_OBJECTIVE_MAX do
        local objective = _G["QuestInfoObjective" .. i]
        if objective then FS.PanelSkins.RetintDarkText(objective) end
    end
end

-- Recolors QuestProgressRequiredMoneyText by affordability. Blizzard's own
-- two colors here (Mainline QuestFrame.lua:228-233) are both dark, so
-- RetintDarkText above lifts both states to the same parchment color -- this
-- re-derives the cue from the live API instead. See CLAUDE.md's Panels.lua
-- entry for the full derivation (hook ordering, why 0.6 gray survives the
-- RetintDarkText hook unchanged).
local function ApplyMoneyAffordabilityColor()
    if type(GetQuestMoneyToGet) ~= "function" or type(GetMoney) ~= "function" then return end

    local moneyText = _G.QuestProgressRequiredMoneyText
    if not moneyText or not moneyText.SetTextColor then return end

    local moneyToGet = GetQuestMoneyToGet()
    local playerMoney = GetMoney()
    if FS.IsSecret(moneyToGet) or FS.IsSecret(playerMoney) then return end
    if not moneyToGet or moneyToGet <= 0 then return end -- label is only shown above 0
    if not playerMoney then return end

    if moneyToGet > playerMoney then
        moneyText:SetTextColor(0.6, 0.6, 0.6)
    else
        moneyText:SetTextColor(COLOR_TEXT_PARCHMENT[1], COLOR_TEXT_PARCHMENT[2], COLOR_TEXT_PARCHMENT[3])
    end
end

-- QuestInfo_Display/QuestFrameProgressItems_Update/QuestFrameGreetingPanel_OnShow
-- repopulate the detail/progress/greeting panels' text on every NPC dialog
-- page. RetintDarkText's own SetTextColor hook re-asserts on regions it has
-- already seen, but the dynamic objective lines above have no such hook until
-- they exist, so re-running the Quest guts retint from here is what catches
-- them. Feature-detected per name, installed once each.
local questRepopulationHooked = false
local function HookQuestRepopulation()
    if questRepopulationHooked then return end
    questRepopulationHooked = true

    if type(_G.QuestInfo_Display) == "function" then
        hooksecurefunc("QuestInfo_Display", function()
            FS.PanelSkins.ApplyGuts({ QUEST_GUTS })
            RetintQuestObjectives()
        end)
    end
    if type(_G.QuestFrameProgressItems_Update) == "function" then
        hooksecurefunc("QuestFrameProgressItems_Update", function()
            FS.PanelSkins.ApplyGuts({ QUEST_GUTS })
            ApplyMoneyAffordabilityColor()
        end)
    end
    if type(_G.QuestFrameGreetingPanel_OnShow) == "function" then
        hooksecurefunc("QuestFrameGreetingPanel_OnShow", function()
            FS.PanelSkins.ApplyGuts({ QUEST_GUTS })
        end)
    end
end

-------------------------------------------------------------------------------
-- Gossip dialog goodbye button
-------------------------------------------------------------------------------

-- GreetingPanel.GoodbyeButton is a real Button, not one of ApplyGuts'
-- strip/hide/retint/rows primitives; Theme.SkinButton is idempotent via
-- `button.fsSkin`, so calling it every afterScan pass alongside GOSSIP_GUTS
-- is a cheap no-op once skinned.
local function SkinGossipGoodbyeButton()
    local gossipFrame = _G.GossipFrame
    local goodbye = gossipFrame and gossipFrame.GreetingPanel and gossipFrame.GreetingPanel.GoodbyeButton
    if goodbye and FS.Theme.SkinButton then
        FS.Theme.SkinButton(goodbye)
    end
end

-------------------------------------------------------------------------------
-- Trainer button + money
-------------------------------------------------------------------------------

-- ClassTrainerTrainButton is a real Button, same reasoning as the Gossip
-- goodbye button above. `ClassTrainerFrameSkillStepButton` is a REAL named
-- button whose own Gold/Silver/CopperButtonText hang directly off its own
-- frame name, so `Theme.StyleMoney` is called on it DIRECTLY rather than
-- through `FS.PanelSkins.TryStyleMoney` -- that resolver's three strategies
-- (parentKey `.MoneyFrame`, a `<name>MoneyFrame` global, a child-scan
-- fingerprint) all miss here, since there is no separate MoneyFrame object to
-- find at all. `Theme.StyleMoney(ClassTrainerFrame)` is deliberately NOT
-- called: `ClassTrainerFrameGoldButtonText` etc. are ScrollBox-row children
-- whose `$parent`-derived global happens to resolve to `ClassTrainerFrame`
-- (see `TRAINER_GUTS`'s own comment), so that call would only ever style
-- ONE arbitrary row's money, not every row -- moot anyway, since row money
-- text is Blizzard's own white by default and needs no styling at all.
local function SkinTrainerButtons()
    local trainButton = _G.ClassTrainerTrainButton
    if trainButton and FS.Theme.SkinButton then
        FS.Theme.SkinButton(trainButton, { name = _G.ClassTrainerTrainButtonText })
    end

    if StyleMoney then
        StyleMoney(_G.ClassTrainerFrameSkillStepButton)
    end
end

-------------------------------------------------------------------------------
-- Skin pass
-------------------------------------------------------------------------------

-- Applies SkinPanel to one entry's frame if present and not already skinned;
-- guarded by frame.fsPanelSkin so repeated scans (ADDON_LOADED,
-- PLAYER_ENTERING_WORLD) never stack a second set of chrome textures.
local function SkinOne(entry)
    local frame = _G[entry.name]
    if not frame or frame.fsPanelSkin then return end

    SkinPanel(frame, {
        fillColor = COLOR_BG,
        borderColor = COLOR_BORDER,
        title = entry.title,
        preserveTexture = entry.name == "TaxiFrame" and frame.InsetBg or nil,
    })
    frame.fsPanelSkin = true

    if entry.money and StyleMoney then
        StyleMoney(_G[entry.money])
    end
end

-- Drives the scan/skin/watch cycle over PANEL_FRAMES: re-scans whenever a
-- Blizzard_* module loads (covers every load-on-demand panel in the list)
-- and once more on PLAYER_ENTERING_WORLD as a light catch-all.
--
-- Every panel here loses its parchment to StripBlizzardChrome and gains a
-- near-black terminal fill instead, which leaves Blizzard's deliberately DARK
-- body text unreadable -- gossip, quest text, books, mail. Retinting the
-- shared font objects is what fixes that, and it runs as afterScan rather
-- than inside SkinOne because those font objects are shared across all of
-- them. Idempotent and name-guarded, so re-running on every Blizzard_* load
-- costs nothing.
local ScanAndSkin = FS.PanelSkins.CreateSkinDriver({
    entries = PANEL_FRAMES,
    skinEntry = SkinOne,
    afterScan = function()
        if FS.Theme and FS.Theme.LightenParchmentFonts then
            FS.Theme.LightenParchmentFonts()
        end
        FS.PanelSkins.ApplyGuts(PANEL_GUTS)
        TryHookInboxOnShow()
        HookQuestRepopulation()
        SkinGossipGoodbyeButton()
        SkinTrainerButtons()
        SkinTrainerStatusBar()
    end,
})

FS.PanelSkins.RegisterReconFromList("Panels", PANEL_FRAMES, "fsPanelSkin", "name")
FS.PanelSkins.RegisterRecon("PanelGuts", {
    { name = "ItemTextFrame", guard = "fsGutsApplied" },
    { name = "MailFrame", guard = "fsGutsApplied" },
    { name = "QuestFrame", guard = "fsGutsApplied" },
    { name = "QuestMapFrame", guard = "fsGutsApplied" },
    { name = "GossipFrame", guard = "fsGutsApplied" },
    { name = "ClassTrainerFrame", guard = "fsGutsApplied" },
    { name = "ProfessionsFrame", guard = "fsGutsApplied" },
})

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

-- None of these frames are secure, so none of this is combat-illegal;
-- deferred anyway for consistency with the rest of the addon's Init pattern.
local function Apply()
    ScanAndSkin()
end

FS.PanelSkins.DeferCombat(Apply)
