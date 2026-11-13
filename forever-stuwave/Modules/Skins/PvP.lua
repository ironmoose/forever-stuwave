-- Forever STUwave: PvP match windows
-- The match scoreboard (PVPMatchScoreboard) and the end of match window (PVPMatchResults), both Blizzard_PVPMatch, from the approved
-- PVP SCOREBOARD mockup (mockups/social-group-2026-11-12.html, section 5):
--
--   * the window: the stock faction coloured nine slice border and background art held (the border pieces are made when a match starts,
--     so they are held again after the stock Init and SetupArtwork), the panel chrome and a band title in their place, the close key
--     in the STUwave close key, the table well and the tab bar art held and an ink ring drawn;
--   * the table: each score row is an ink card with a left bar in the colour of the stock team wash (read from it: blue is cyan, red is
--     pink, the gold and purple of an arena match are amber and violet), the stock wash held, every cell label in mono (the stock cell
--     colours, your own row white and the class icons stay as they are, so sorting and the tooltips stay stock), the column headings in
--     small muted mono;
--   * the end of match window: the result line in large mono, the faction decoration and the earnings art held, the reward headings and
--     the honor, conquest and rating lines in mono, Requeue a cyan key and Leave a pink one, the tabs, scroll bar and text buttons by the
--     shared sweep.
--
-- Skin only, as in Commerce.lua: no SetScript, no SetAttribute, no reparent, no resize or re-anchor of a Blizzard frame, alpha holds
-- (FS.HeldArt) and post-hooks only, so every sort click, tab, requeue and leave flow stays stock. Rows are pooled by a ScrollBox and
-- repopulated by the stock code, so each is painted again after every update of the list and after its own Populate. Feature-detected: a
-- missing frame is skipped (the addon is not load on demand, but a client may lack it).
--
-- Left out on purpose, because the mockup shows a computed display and the rule for this pass is "keep the functionality the same as
-- vanilla": the tug of war score bar and its seam, the faction group bands with their totals, the inline damage and healing bars with
-- the crown for the best of a column, the class shields, the flag counters, the "your row is locked on" brackets, the details key, the
-- result banner card with its shine and the honor, mark and time chips. The queue window (PVPUIFrame) is not in the mockup and keeps
-- its stock look.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char, G = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin, FS.GroupSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and G and G.Card and PanelSkins.RequireExport(
    Theme.SkinPanel and Theme.ApplyMono,
    "PvP.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit, FS.CharacterSkin or FS.GroupSkin missing")) then return end

local Pvp = {}
FS.PvPSkin = Pvp

local C, Weak, Region, Named, Mono = G.C, G.Weak, G.Region, G.Named, G.Mono
local Try, List = Kit.Try, Char.List
local function Step(name, fn, ...) return G.Step("pvp", name, fn, ...) end

local S = { windows = Weak(), keep = Weak(), rows = Weak(), labels = Weak() }
Pvp.state = S

-- Where each window keeps its parts (the two XML files spell them with different capitals).
local WINDOWS = {
    { name = "PVPMatchScoreboard", title = "scoreboard", content = "Content", box = "ScrollBox", heads = "ScrollCategories",
      tabs = "TabContainer", matchmaking = "MatchmakingText" },
    { name = "PVPMatchResults", title = "match results", content = "content", box = "scrollBox", heads = "scrollCategories",
      tabs = "tabContainer", matchmaking = "matchmakingText", results = true },
}

-------------------------------------------------------------------------------
-- Rows
-------------------------------------------------------------------------------

local ROW_ART = { "backgroundLeft", "backgroundRight", "backgroundCenter" }

-- The colour of a row's left bar, told from the stock team wash (its vertex colour): blue is the alliance (cyan), red the horde
-- (pink); an arena match uses gold and purple (amber and violet). A wash that cannot be read gives the quiet edge colour.
local function RowTint(row)
    local wash = Region(row, "backgroundLeft")
    local r, g, b = Try(wash and wash.GetVertexColor, wash)
    r, g, b = Kit.Plain(r), Kit.Plain(g), Kit.Plain(b)
    if type(r) ~= "number" or type(g) ~= "number" or type(b) ~= "number" then return C.dim end
    if g >= r * 0.6 and g > b then return C.amber end
    if b > r and r < b * 0.4 then return C.cyan end
    if b > g and r >= b * 0.4 then return C.violet end
    return C.pink
end

-- Every label of a row's cells (the name and stat cells keep theirs under `text`; the class and honor cells are only an icon).
local function SkinCells(row)
    for _, cell in ipairs(List(row, "GetChildren")) do
        local text = Region(cell, "text")
        if text and not S.labels[text] then
            S.labels[text] = true
            Mono(text, cell, 12, C.text)
        end
    end
end

local function SkinRow(row)
    if type(row) ~= "table" or Kit.TypeOf(row) ~= "Frame" then return end
    if not S.rows[row] then
        G.HoldKeys(row, ROW_ART)
        local rec = G.Card(row, { accent = C.cyan, hold = {}, px = 12, led = function() return RowTint(row) end })
        if not rec then return end
        S.rows[row] = rec
        Kit.HookFunc(row, "Populate", function() G.PaintCard(row) end)
    end
    SkinCells(row)
    G.PaintCard(row)
end

-- The column headings are made by the table builder when a match starts, as buttons that carry a `text` label (or an icon).
local function SkinHeadings(container)
    for _, head in ipairs(List(container, "GetChildren")) do
        local text = Region(head, "text")
        if text and not S.labels[text] then
            S.labels[text] = true
            Mono(text, head, 10, C.muted)
        end
    end
end

-------------------------------------------------------------------------------
-- Windows
-------------------------------------------------------------------------------

-- Holds the art the stock code makes late (the nine slice pieces of the faction border) and the headings the table builder makes.
local function Refresh(frame, spec)
    local keep = S.keep[frame]
    if keep then G.HoldRegions(frame, keep) end
    local content = Region(frame, spec.content)
    if content then SkinHeadings(Region(content, spec.heads)) end
end

local function SkinContent(frame, spec)
    local content = Region(frame, spec.content)
    if not content then return end
    G.HoldRegions(content)
    local well = Char.Box(content, "BORDER")
    Char.PaintBox(well, C.ink, 0.6, C.dim, 1, 1)
    local box = Region(content, spec.box)
    if box then
        HeldArt.Hold(box.Background or box.background)
        G.Rows(box, SkinRow)
    end
    local tabs = Region(content, spec.tabs)
    if tabs then
        G.HoldRegions(tabs)
        Mono(tabs[spec.matchmaking], tabs, 11, C.muted)
    end
end

-- The end of match window: the result line, the faction decoration, the earnings art and text, the two keys.
local function SkinResults(frame)
    Mono(frame.header, frame, 34, C.text)
    local overlay = Region(frame, "overlay")
    if overlay then HeldArt.Hold(overlay.decorator) end
    local content = Region(frame, "content")
    local art = content and Region(content, "earningsArt")
    if art then G.HoldRegions(art) end
    local earn = content and Region(content, "earningsContainer")
    if earn then
        local rewards, progress = Region(earn, "rewardsContainer"), Region(earn, "progressContainer")
        if rewards then Mono(rewards.header, rewards, 11, C.muted) end
        if progress then
            Mono(progress.header, progress, 11, C.muted)
            for _, key in ipairs({ "honor", "conquest", "rating" }) do
                local line = Region(progress, key)
                if line then Mono(line.text, line, 12, C.text) end
            end
        end
    end
    local keys = Region(frame, "buttonContainer")
    local skin = FS.ButtonSkins and FS.ButtonSkins.SkinTextButton
    if keys and skin then
        if keys.requeueButton then skin(keys.requeueButton, { accent = "cyan" }) end
        if keys.leaveButton then skin(keys.leaveButton, { accent = "pink" }) end
    end
end

local function SkinWindow(spec)
    local frame = Named(spec.name)
    if not frame then return end
    if not S.windows[frame] then
        S.windows[frame] = true
        G.HoldRegions(frame)
        local chrome = Theme.SkinPanel(frame, { strip = false, fillColor = Theme.COLOR_BG, accent = C.violet, title = spec.title })
        local keep = {}
        for _, region in ipairs(chrome or {}) do keep[region] = true end
        S.keep[frame] = keep
        Theme.SkinCloseButton(frame)
        for _, method in ipairs({ "SetupArtwork", "Init", "UpdateTable" }) do
            Kit.HookFunc(frame, method, function() Refresh(frame, spec) end)
        end
        Step("content", SkinContent, frame, spec)
        if spec.results then Step("results", SkinResults, frame) end
        PanelSkins.SweepOnShow(frame)
        Kit.HookScript(frame, "OnShow", function() Kit.Later(function() PanelSkins.DeferCombat(Pvp.Build) end) end)
        frame.fsPvPSkin = true
    end
    Refresh(frame, spec)
end

local function Build()
    for _, spec in ipairs(WINDOWS) do Step(spec.name, SkinWindow, spec) end
end
Pvp.Build = Build

PanelSkins.RegisterInspect("PvP", { { name = "PVPMatchScoreboard", guard = "fsPvPSkin" }, { name = "PVPMatchResults", guard = "fsPvPSkin" } })

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
