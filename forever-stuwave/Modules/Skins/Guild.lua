-- Forever STUwave: Guild
-- The guild window (CommunitiesFrame, Blizzard_Communities) past its shell, from the approved GUILD mockup
-- (mockups/social-group-2026-11-12.html, section 2). The window shell, the text buttons, the scroll bars, the dropdowns, the search
-- and edit boxes and the check boxes already wear the shared skins (Panels.lua, the controls sweep); this file adds the parts that
-- were still stock:
--
--   * the roster: every member row is an ink card (the stock row wash and highlight held, the labels in mono, a cyan edge on hover
--     and selection; the class icon, rank icon, presence icon and the mute keys stay stock), the column headings are band keys with
--     their stock art held (sorting stays stock), the column display and its inset are held so only a ring shows;
--   * the community list down the left side: the stock bluemenu frame art, filigree and inset held, each entry a card whose edge
--     lights cyan when it is the chosen community (the stock selection is followed, not replaced);
--   * the guild pages (the info page and its news, the benefits page) lose their inset border art;
--   * the guild log, the message of the day editor and the news filter pop ups wear the panel skin.
--
-- Skin only, as in Commerce.lua: no SetScript, no SetAttribute, no reparent, no resize or re-anchor of a Blizzard frame, alpha holds
-- (FS.HeldArt) and post-hooks only, so every click, invite, promotion and whisper flow stays stock. Rows are pooled by a
-- ScrollBox, so each is painted again after every update of its list. Every frame is feature-detected by name or key; a missing
-- one is skipped (the window loads on demand).
--
-- Left out on purpose, because the mockup shows a computed display and the rule for this pass is "keep the functionality the same as
-- vanilla": the rank insignia (chevrons told from the rank index), the crest with the online arc gauge, the slide out dossier with its
-- 14 day activity comb, the live message of the day ticker, the segmented challenge bars, and the three way switch for the side tabs.
-- The four round side tabs (chat, roster, benefits, info), the avatar picker, the settings and ticket dialogs, the tabard and the
-- voice chat keys keep their stock look.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char, G = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin, FS.GroupSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and G and G.Card and PanelSkins.RequireExport(
    Theme.SkinPanel and Theme.ApplyMono,
    "Guild.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit, FS.CharacterSkin or FS.GroupSkin missing")) then return end

local Gld = {}
FS.GuildSkin = Gld

local C, Weak, Region, Named, Mono = G.C, G.Weak, G.Region, G.Named, G.Mono
local Try, List = Kit.Try, Char.List
local function Step(name, fn, ...) return G.Step("guild", name, fn, ...) end

local S = { rows = Weak(), done = {}, panels = Weak(), columns = Weak() }
Gld.state = S

-------------------------------------------------------------------------------
-- Rows
-------------------------------------------------------------------------------

local MEMBER_ART = { "^Background", "^Bg$", "Highlight", "^Selected", "^Selection", "^Stripe" }

local function SkinMemberRow(row)
    if type(row) ~= "table" or S.rows[row] or Kit.TypeOf(row) ~= "Button" then return end
    local rec = G.Card(row, { accent = C.cyan, hold = MEMBER_ART, px = 11 })
    if not rec then return end
    S.rows[row] = rec
    for _, getter in ipairs({ "GetNormalTexture", "GetHighlightTexture", "GetPushedTexture", "GetDisabledTexture" }) do
        HeldArt.Hold(Try(row[getter], row))
    end
    local frame = Region(row, "NameFrame")
    if frame then Mono(frame.Name, row, 12, C.text) end
end

-- A community of the list: the stock Selection texture marks the chosen one, and it is followed (its Show and Hide) to light the card.
local ENTRY_ART = { "^Background", "^Selection", "^NewCommunityFlash", "Highlight" }

local function PaintEntry(row)
    local rec = S.rows[row]
    if not rec then return end
    local sel = Region(row, "Selection")
    rec.selected = sel ~= nil and Try(sel.IsShown, sel) == true
    G.PaintCard(row)
end

local function SkinCommunityRow(row)
    if type(row) ~= "table" or S.rows[row] or Kit.TypeOf(row) ~= "Button" then return end
    local rec = G.Card(row, { accent = C.cyan, hold = ENTRY_ART, px = 12 })
    if not rec then return end
    S.rows[row] = rec
    for _, getter in ipairs({ "GetNormalTexture", "GetHighlightTexture", "GetPushedTexture", "GetDisabledTexture" }) do
        HeldArt.Hold(Try(row[getter], row))
    end
    local sel = Region(row, "Selection")
    if sel then
        for _, m in ipairs({ "Show", "Hide", "SetShown" }) do Kit.HookFunc(sel, m, function() PaintEntry(row) end) end
    end
    Mono(row.Name, row, 12, C.text)
    PaintEntry(row)
end

-------------------------------------------------------------------------------
-- Column headings
-------------------------------------------------------------------------------

local function SkinColumns(display)
    if type(display) ~= "table" then return end
    for _, child in ipairs(List(display, "GetChildren")) do
        if Kit.TypeOf(child) == "Button" then G.Header(child, 11) end
    end
end

local function SkinColumnDisplay(display)
    if type(display) ~= "table" or S.columns[display] then return end
    S.columns[display] = true
    G.HoldInset(display)
    G.HoldNamed(display, { "^TopTileStreaks", "^InsetBorder" })
    Char.PaintBox(Char.Box(display, "BORDER"), C.ink, 0.6, C.dim, 1, 1)
    for _, method in ipairs({ "LayoutColumns", "SetColumns", "Update" }) do
        Kit.HookFunc(display, method, function() SkinColumns(display) end)
    end
    Kit.HookScript(display, "OnShow", function() Kit.Later(function() SkinColumns(display) end) end)
end

-------------------------------------------------------------------------------
-- Windows and pages
-------------------------------------------------------------------------------

local function SkinRoster(frame)
    local list = Region(frame, "MemberList")
    if not list then return end
    G.HoldInset(Region(list, "InsetFrame"))
    G.HoldNamed(list, { "^InsetBorder" })
    SkinColumnDisplay(Region(list, "ColumnDisplay"))
    SkinColumns(Region(list, "ColumnDisplay"))
    G.Rows(Region(list, "ScrollBox"), SkinMemberRow)
    Mono(list.MemberCount, list, 11, C.muted)
end

local function SkinCommunityList(frame)
    local list = Region(frame, "CommunitiesList")
    if not list then return end
    G.HoldInset(Region(list, "InsetFrame"))
    G.HoldNamed(list, { "^Bg$", "Filigree" })
    Kit.HoldFrame(Region(list, "FilligreeOverlay"))
    G.Rows(Region(list, "ScrollBox"), SkinCommunityRow)
end

local function SkinPages(frame)
    for _, key in ipairs({ "GuildDetailsFrame", "GuildBenefitsFrame" }) do
        local page = Region(frame, key)
        if page then
            G.HoldNamed(page, { "^InsetBorder" })
            for _, sub in ipairs({ "Info", "News", "Perks", "Rewards" }) do G.HoldNamed(Region(page, sub), { "^InsetBorder" }) end
        end
    end
end

-- The three pop ups that are a TranslucentFrameTemplate window: the panel skin, once each.
local POPUPS = { { "CommunitiesGuildLogFrame", "guild log" }, { "CommunitiesGuildTextEditFrame", "guild text" },
    { "CommunitiesGuildNewsFiltersFrame", "news filter" } }

local function SkinPopups()
    for _, spec in ipairs(POPUPS) do
        local frame = Named(spec[1])
        if frame and not S.panels[frame] then
            S.panels[frame] = true
            Theme.SkinPanel(frame, { fillColor = Theme.COLOR_BG, accent = C.violet, title = spec[2] })
        end
    end
end

local function Build()
    local frame = Named("CommunitiesFrame")
    Step("popups", SkinPopups)
    if not frame then return end
    Step("roster", SkinRoster, frame)
    Step("list", SkinCommunityList, frame)
    Step("pages", SkinPages, frame)
    if not S.done.shown then
        S.done.shown = true
        Kit.HookScript(frame, "OnShow", function() Kit.Later(function() PanelSkins.DeferCombat(Gld.Build) end) end)
        frame.fsGuildSkin = true
    end
end
Gld.Build = Build

PanelSkins.RegisterInspect("Guild", { { name = "CommunitiesFrame", guard = "fsGuildSkin" } })

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
