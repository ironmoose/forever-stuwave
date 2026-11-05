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

-- One header row (playtest 2026-11-05: the stuwave band over a separate gold "Quests" header read as a double header,
-- and two sets of collapse buttons were confusing). Expanded, our panel starts at the first shown module's header row:
-- the band sits over it, reads "quests (2/40)" (or that module's own name when quests are not first), and that
-- header's own text is held invisible. The container's empty header strip above is left outside the panel.
-- Collapsed, the panel is a compact bar on the tracker's right edge, just wide enough for the count and the button,
-- and a click anywhere on it expands: the collapse button's own hit rect is widened over the bar, so the click is
-- Blizzard's own (no call into its code from ours).
-- Our own frames are re-anchored and re-texted; the only Blizzard writes are alpha, hit rect insets and the button's
-- seat. Blizzard's layout values are never written (they are fields its layout code reads, the classic tracker taint
-- path); topModulePadding is only read.
local chrome = {} -- frame, header, nineSlice, backdrop, band, label, button, collapsed
local moduleRules = setmetatable({}, { __mode = "k" }) -- module header -> our cyan rule

local MODULE_NAMES -- set below, with the module header skin

local function QuestCount()
    local q = C_QuestLog
    local n
    if q and type(q.GetNumQuestLogEntries) == "function" then
        local ok, _, quests = pcall(q.GetNumQuestLogEntries)
        if ok and type(quests) == "number" then n = quests end
    end
    if not n then return nil end
    local max
    if q and type(q.GetMaxNumQuestsCanAccept) == "function" then
        local ok, m = pcall(q.GetMaxNumQuestsCanAccept)
        if ok and type(m) == "number" and m > 0 then max = m end
    end
    if not max and type(_G.MAX_QUESTS) == "number" then max = _G.MAX_QUESTS end
    return n, max
end

local function CollapsedText()
    local ok, n, max = pcall(QuestCount)
    if not ok or not n then return "quests" end
    if max then return ("quests (%d/%d)"):format(n, max) end
    return ("quests (%d)"):format(n)
end

-- The first module the container laid out (it places them in self.modules order, skipping empty ones). Read only.
local function FirstModule(frame)
    local modules = frame and frame.modules
    if type(modules) ~= "table" then return nil end
    for _, module in ipairs(modules) do
        local ok, height = pcall(module.GetContentsHeight, module)
        if ok and type(height) == "number" and height > 0 then return module end
    end
    return nil
end

local function TitleFor(module)
    if not module or module == _G.QuestObjectiveTracker then return CollapsedText() end
    local text = module.Header and module.Header.Text and module.Header.Text.GetText and module.Header.Text:GetText()
    if type(text) ~= "string" or text == "" then return CollapsedText() end
    return text:lower()
end

-- Shows every module header's own text and rule except the one our band covers.
local function MarkCovered(covered)
    for _, name in ipairs(MODULE_NAMES) do
        local module = _G[name]
        local header = module and module.Header
        if header then
            local hide = header == covered
            if header.Text and header.Text.SetAlpha then header.Text:SetAlpha(hide and 0 or 1) end
            local rule = moduleRules[header]
            if rule then rule:SetShown(not hide) end
        end
    end
end

local BAR_PAD = 10 -- label inset from the band's left, and gap to the button

local function SetBarHit(button, width)
    if not (button and button.SetHitRectInsets) then return end
    if not chrome.hit and button.GetHitRectInsets then
        chrome.hit = { button:GetHitRectInsets() }
    end
    if width then
        local bw = button:GetWidth() or 0
        button:SetHitRectInsets(-(width - bw - 4), -6, -4, -6)
    elseif chrome.hit then
        button:SetHitRectInsets(chrome.hit[1], chrome.hit[2], chrome.hit[3], chrome.hit[4])
    end
end

local function Relayout()
    local frame, backdrop = chrome.frame, chrome.backdrop
    if not backdrop then return end
    local top = chrome.nineSlice or frame
    local inset = Theme.PanelBandInset()
    backdrop:ClearAllPoints()
    if chrome.collapsed then
        local label = chrome.label
        label:SetText(CollapsedText())
        local bw = chrome.button and chrome.button:GetWidth() or 14
        local width = math.ceil(BAR_PAD + (label.GetStringWidth and label:GetStringWidth() or 0) + BAR_PAD + bw + 6 + inset)
        backdrop:SetPoint("TOPRIGHT", top, "TOPRIGHT", 0, 0)
        backdrop:SetSize(width, Theme.PANEL_HEADER_H + inset * 2)
        SetBarHit(chrome.button, width)
        MarkCovered(nil)
    else
        local first = FirstModule(frame)
        local pad = first and tonumber(frame.topModulePadding) or 0
        backdrop:SetPoint("TOPLEFT", top, "TOPLEFT", 0, -pad)
        backdrop:SetPoint("BOTTOMRIGHT", top, "BOTTOMRIGHT", 0, 0)
        chrome.label:SetText(TitleFor(first))
        SetBarHit(chrome.button, nil)
        MarkCovered(first and first.Header or nil)
    end
end

local function ApplyCollapsed(collapsed)
    chrome.collapsed = collapsed == true
    Relayout()
end

-- Keeps the count current; made with the chrome, so a file load builds no frame.
local function WatchQuestCount()
    if chrome.countEvents or type(CreateFrame) ~= "function" then return end
    local f = CreateFrame("Frame")
    for _, event in ipairs({ "QUEST_LOG_UPDATE", "QUEST_ACCEPTED", "QUEST_REMOVED" }) do
        pcall(f.RegisterEvent, f, event)
    end
    f:SetScript("OnEvent", Relayout)
    chrome.countEvents = f
end

local function SkinCollapseButton(frame, header, backdrop)
    local skins = FS.ButtonSkins
    local button = header and header.MinimizeButton
    if not (skins and skins.SkinCloseButton and button) then return end
    local collapsed = false
    if type(frame.IsCollapsed) == "function" then
        local ok, value = pcall(frame.IsCollapsed, frame)
        collapsed = ok and value == true
    end
    -- Seated on our backdrop, so it rides the band in both states.
    skins.SkinCloseButton(button, { anchor = backdrop, glyph = collapsed and "plus" or "minus" })
    chrome.button = button
    if type(hooksecurefunc) == "function" and type(header.SetCollapsed) == "function" then
        hooksecurefunc(header, "SetCollapsed", function(_, nowCollapsed)
            skins.SetGlyph(button, nowCollapsed == true and "plus" or "minus")
            ApplyCollapsed(nowCollapsed == true)
        end)
    end
end

-- Our backdrop follows the container's own NineSlice child: every container layout pass moves its BOTTOM to the last
-- module's bottom (Blizzard_ObjectiveTrackerContainer.lua:100) and its TOPLEFT/TOPRIGHT are fixed, so anchoring to it
-- tracks every resize with no hook. The container itself Shows/Hides with content, and our backdrop is its child, so
-- visibility cascades. Without a NineSlice the backdrop anchors to the container frame.
local function BuildContainerChrome()
    local frame = ObjectiveTrackerFrame
    if not (frame and frame.CreateTexture) then return end
    if frame.fsTrackerChromeBuilt then return end

    local header = frame.Header
    local nineSlice = frame.NineSlice
    local usingNineSlice = nineSlice and nineSlice.SetPoint and nineSlice.SetAlpha

    -- A new frame does not inherit its parent's LOW strata; set it, and sit at the container's own level (as its
    -- NineSlice does) so the header and modules draw above.
    local backdrop = CreateFrame("Frame", nil, frame)
    backdrop:SetFrameStrata(frame:GetFrameStrata())
    backdrop:SetFrameLevel(frame:GetFrameLevel())

    -- The same cut panel chrome every other STUwave panel wears.
    Theme.AddPanelChrome(backdrop, { fillColor = Theme.COLOR_BG, accent = COLOR_POWER })

    local inset = Theme.PanelBandInset()
    local band = backdrop:CreateTexture(nil, "ARTWORK")
    band:SetColorTexture(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.08)
    band:SetPoint("TOPLEFT", backdrop, "TOPLEFT", inset, -inset)
    band:SetPoint("TOPRIGHT", backdrop, "TOPRIGHT", -inset, -inset)
    band:SetHeight(Theme.PANEL_HEADER_H)

    local rule = backdrop:CreateTexture(nil, "ARTWORK")
    rule:SetColorTexture(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.30)
    rule:SetPoint("TOPLEFT", band, "BOTTOMLEFT", 0, 0)
    rule:SetPoint("TOPRIGHT", band, "BOTTOMRIGHT", 0, 0)
    rule:SetHeight(1)

    local label = backdrop:CreateFontString(nil, "OVERLAY")
    ApplyMono(label, 10, COLOR_POWER)
    label:SetPoint("LEFT", band, "LEFT", BAR_PAD, 0)
    label:SetWordWrap(false)
    label:SetText(CollapsedText())

    chrome.backdrop, chrome.frame, chrome.header, chrome.band, chrome.label = backdrop, frame, header, band, label
    chrome.nineSlice = usingNineSlice and nineSlice or nil

    if header then
        -- Stock header art and text held at alpha 0 (not Hidden), so Blizzard's own show state is untouched.
        if header.Background and header.Background.SetAlpha then header.Background:SetAlpha(0) end
        if header.Text and header.Text.SetAlpha then header.Text:SetAlpha(0) end
        SkinCollapseButton(frame, header, backdrop)
    end

    if usingNineSlice then nineSlice:SetAlpha(0) end
    backdrop:Show()

    local collapsed = false
    if type(frame.IsCollapsed) == "function" then
        local ok, value = pcall(frame.IsCollapsed, frame)
        collapsed = ok and value == true
    end
    -- After each layout pass: which module is first can change (a new quest type, a recipe tracked).
    if type(hooksecurefunc) == "function" and type(frame.Update) == "function" then
        hooksecurefunc(frame, "Update", Relayout)
    end
    ApplyCollapsed(collapsed)
    WatchQuestCount()

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
MODULE_NAMES = {
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

    moduleRules[header] = rule

    -- One collapse control: the tracker's own. Each module's stock gold minus is hidden, and kept hidden: its header's
    -- add animation fades it back in, so an alpha of 0 did not hold (playtest 2026-11-05). Nothing in Blizzard's
    -- tracker code Shows it; the Show hook is a guard.
    local minimize = header.MinimizeButton
    if minimize and minimize.Hide then
        minimize:Hide()
        if type(hooksecurefunc) == "function" then hooksecurefunc(minimize, "Show", minimize.Hide) end
    end

    header.fsModuleHeaderSkin = true
end

local function StyleModuleHeaders()
    for _, name in ipairs(MODULE_NAMES) do
        StyleModuleHeader(name)
    end
end

-------------------------------------------------------------------------------
-- Quest markers (the POI buttons beside each quest title)
-------------------------------------------------------------------------------

-- Blizzard's gold "?" (ready to turn in) and "..." (in progress) discs, playtest 2026-11-05: still stock art. Each
-- marker gets a small cut plate of our own drawn over it, its Blizzard art held at alpha 0 (HeldArt), with the
-- shared button looks: hover lifts the ring and washes the face, pressed nudges the glyph a pixel, and the quest
-- being followed (selected) wears pink. The button, its click, its place and its pool are Blizzard's; markers are
-- found after each module layout by reading the module's block list. Textures and alpha only, so safe in combat.
local MARKER_SIZE = 16
local poiSkins = setmetatable({}, { __mode = "k" }) -- POI button -> our pieces and hover/pressed state

local function Lift(c, t)
    return { c[1] + (1 - c[1]) * t, c[2] + (1 - c[2]) * t, c[3] + (1 - c[3]) * t }
end

local function MarkerKind(button)
    local styles = POIButtonUtil and POIButtonUtil.Style
    local ok, style = pcall(button.GetStyle, button)
    if not ok or not styles then return "dots" end
    if style == styles.QuestComplete then return "ask" end
    if style == styles.QuestInProgress then return "dots" end
    if style == styles.QuestDisabled then return "none" end
    return "bang"
end

local function PaintMarker(button)
    local m = poiSkins[button]
    if not m then return end
    local kind = MarkerKind(button)
    m.frame:SetShown(kind ~= "none")
    if kind == "none" then return end
    local okSel, selected = pcall(button.IsSelected, button)
    selected = okSel and selected == true
    local accent = selected and Theme.COLOR_HEALTH or (kind == "ask" and Theme.COLOR_AMBER or COLOR_POWER)
    local hover, pressed = m.hover, m.pressed
    local wash = pressed and 0.40 or (hover and 0.25 or (selected and 0.15 or 0))
    local ink = Theme.COLOR_BUTTON_INK
    m.fill:SetVertexColor(ink[1] + (accent[1] - ink[1]) * wash, ink[2] + (accent[2] - ink[2]) * wash,
        ink[3] + (accent[3] - ink[3]) * wash, 1)
    m.ring:SetVertexColor(accent[1], accent[2], accent[3], (hover or pressed or selected) and 1 or 0.75)
    m.glow:SetVertexColor(accent[1], accent[2], accent[3], (hover or pressed) and 0.65 or (selected and 0.45 or 0.2))
    local g = (hover or pressed) and Lift(accent, 0.55) or accent
    local dx, dy = pressed and 1 or 0, pressed and -1 or 0
    m.text:ClearAllPoints()
    m.text:SetPoint("CENTER", m.frame, "CENTER", dx, dy)
    m.text:SetTextColor(g[1], g[2], g[3], 1)
    m.text:SetText(kind == "ask" and "?" or "!")
    m.text:SetShown(kind ~= "dots")
    for i, dot in ipairs(m.dots) do
        dot:ClearAllPoints()
        dot:SetPoint("CENTER", m.frame, "CENTER", (i - 2) * 4 + dx, dy)
        dot:SetColorTexture(g[1], g[2], g[3], 1)
        dot:SetShown(kind == "dots")
    end
end

local function SkinMarker(button)
    if poiSkins[button] or type(button) ~= "table" or type(button.CreateTexture) ~= "function" then return end
    if FS.HeldArt then FS.HeldArt.HoldButton(button) end
    local display = button.Display
    if display and display.SetAlpha then
        display:SetAlpha(0)
        if type(hooksecurefunc) == "function" then
            local zeroing = false
            hooksecurefunc(display, "SetAlpha", function(self)
                if zeroing then return end
                zeroing = true
                self:SetAlpha(0)
                zeroing = false
            end)
        end
    end

    local f = CreateFrame("Frame", nil, button)
    f:SetSize(MARKER_SIZE, MARKER_SIZE)
    f:SetPoint("CENTER", button, "CENTER", 0, 0)
    if f.EnableMouse then f:EnableMouse(false) end
    local m = { frame = f, dots = {}, hover = false, pressed = false }
    m.glow = Theme.AddCut2Texture(f, Theme.SLICE_CUT2_GLOW_TEXTURE, COLOR_POWER, "BACKGROUND", 1,
        -Theme.SLICE_CUT2_GLOW_PAD)
    m.fill = Theme.AddCut2Texture(f, Theme.SLICE_CUT2_FILL_TEXTURE, Theme.COLOR_BUTTON_INK, "ARTWORK", 1)
    m.ring = Theme.AddCut2Texture(f, Theme.SLICE_CUT2_OUTLINE_TEXTURE, COLOR_POWER, "ARTWORK", 2)
    m.text = f:CreateFontString(nil, "OVERLAY")
    ApplyMono(m.text, 11, COLOR_POWER)
    for i = 1, 3 do
        local dot = f:CreateTexture(nil, "OVERLAY")
        dot:SetSize(2, 2)
        m.dots[i] = dot
    end
    poiSkins[button] = m

    local function set(field, value)
        return function(self)
            local s = poiSkins[self]
            if s then s[field] = value; PaintMarker(self) end
        end
    end
    if button.HookScript then
        button:HookScript("OnEnter", set("hover", true))
        button:HookScript("OnLeave", function(self)
            local s = poiSkins[self]
            if s then s.hover, s.pressed = false, false; PaintMarker(self) end
        end)
        button:HookScript("OnMouseDown", set("pressed", true))
        button:HookScript("OnMouseUp", set("pressed", false))
    end
    if type(hooksecurefunc) == "function" then
        for _, method in ipairs({ "UpdateButtonStyle", "SetStyle", "SetSelected", "UpdateSelected" }) do
            if type(button[method]) == "function" then pcall(hooksecurefunc, button, method, PaintMarker) end
        end
    end
    PaintMarker(button)
end

local function SkinModuleMarkers(module)
    local used = type(module) == "table" and module.usedBlocks
    if type(used) ~= "table" then return end
    for _, blocks in pairs(used) do
        if type(blocks) == "table" then
            for _, block in pairs(blocks) do
                local poi = type(block) == "table" and block.poiButton
                if poi then
                    SkinMarker(poi)
                    PaintMarker(poi)
                end
            end
        end
    end
end

local function WatchMarkers()
    if type(hooksecurefunc) ~= "function" then return end
    for _, name in ipairs(MODULE_NAMES) do
        local module = _G[name]
        if module and not poiSkins[module] and type(module.EndLayout) == "function" then
            hooksecurefunc(module, "EndLayout", SkinModuleMarkers)
            poiSkins[module] = true
            SkinModuleMarkers(module)
        end
    end
end

-------------------------------------------------------------------------------
-- Quest timers
-------------------------------------------------------------------------------

-- Blizzard_QuestTimer's QuestTimerFrame (Blizzard_QuestTimer.xml) is a BackdropTemplate dialog with a gold header on
-- the BACKGROUND strata, laid out by RightManagedFrameContainer into the gap the tracker leaves at its top. Our
-- backdrop sits on the tracker's LOW strata, so the stock timer drew behind it (playtest 2026-11-04). Skin and raise
-- only, never moved: the container owns its anchor, and ignoreFramePositionManager, the one way out, is a field its
-- layout code reads.

-- Puts the timer on the tracker's strata, above the tracker. The container's UpdateFrame reparents the timer, which
-- resets its level, so this runs again after every re-layout and show.
-- The 12.1 source names its lines QuestTimer1Text..QuestTimer25Text, but the 16001 globals dump has none of those
-- names, so the Forever build is not that file. The lines are found by shape instead: every font string on a child
-- frame of the timer. Run again on each show, so a line made after the skin is set too.
local function StyleQuestTimerLines(timer)
    local ok, children = pcall(function() return { timer:GetChildren() } end)
    if not ok then return end
    for _, child in ipairs(children) do
        if type(child) == "table" and type(child.GetRegions) == "function" then
            for _, region in ipairs({ child:GetRegions() }) do
                if region.GetObjectType and region:GetObjectType() == "FontString" then
                    ApplyMono(region, 10, COLOR_LINE_MUTED)
                end
            end
        end
    end
end

local function RaiseQuestTimer()
    local timer, tracker = QuestTimerFrame, ObjectiveTrackerFrame
    if not (timer and timer.SetFrameStrata and tracker and tracker.GetFrameStrata) then return end
    timer:SetFrameStrata(tracker:GetFrameStrata())
    timer:SetFrameLevel(tracker:GetFrameLevel() + 10)
    StyleQuestTimerLines(timer)
end

local function SkinQuestTimer()
    local timer = QuestTimerFrame
    if not (timer and timer.GetRegions) then return end
    if not timer.fsQuestTimerSkin then
        Theme.SkinPanel(timer, { fillColor = Theme.COLOR_BG, borderColor = COLOR_POWER, title = "timers" })
        -- Blizzard's "Quest Timers" label; the band carries the title now
        for _, region in ipairs({ timer:GetRegions() }) do
            if region ~= timer.fsPanelTitle and region.GetObjectType and region:GetObjectType() == "FontString" then
                region:Hide()
            end
        end
        FS.PanelSkins.HookShowOnce(timer, "fsQuestTimerHook", RaiseQuestTimer)
        local container = RightManagedFrameContainer
        if container and type(container.UpdateFrame) == "function" then
            hooksecurefunc(container, "UpdateFrame", RaiseQuestTimer)
        end
        timer.fsQuestTimerSkin = true
    end
    RaiseQuestTimer()
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
    WatchMarkers()
    SkinQuestTimer()
end

FS.PanelSkins.RegisterInspect("Tracker", {
    { name = "ObjectiveTrackerFrame", guard = "fsTrackerChromeBuilt" },
    { name = "QuestTimerFrame", guard = "fsQuestTimerSkin" },
})

FS.PanelSkins.DeferCombat(Apply)

-- Blizzard_QuestTimer is its own addon and may load after this file.
FS.PanelSkins.WatchAddonLoad(SkinQuestTimer, function(name) return name == "Blizzard_QuestTimer" end)

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
