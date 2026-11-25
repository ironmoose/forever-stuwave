-- Forever STUwave: Chat settings
-- The chat settings window (ChatConfigFrame, Blizzard_ChatFrame) as a STUwave dialog, from the approved CHAT SETTINGS mockup
-- (mockups/social-group-2026-11-12.html, section 4): the panel chrome and a band title in place of the stock border and header, every
-- backdrop well of the pages (the category list, the page well, the message type boxes, the channel and other boxes, the combat filter
-- list) an ink well with a dim ring, every message type row and colour row an ink card, the category buttons and the combat filter
-- rows cards with the chosen one lit by the stock highlight lock, the box headings in mono. The text buttons (Defaults, Redock,
-- Cancel, Okay and the combat ones), the scroll bars and the check boxes wear the shared skins through PanelSkins.SweepOnShow.
--
-- Skin only, as in Commerce.lua: no SetScript, no SetAttribute, no reparent, no resize or re-anchor of a Blizzard frame, alpha holds
-- (FS.HeldArt, Kit.HoldFrame) and post-hooks only, so every message type switch, colour swatch and filter flow stays stock; the colour
-- swatch IS the colour lamp of the mockup and is left as it is. The stock code makes the rows of a page as it loads and again when the
-- channel list is built (ChatConfig_CreateCheckboxes, ChatConfig_CreateTieredCheckboxes, ChatConfig_CreateColorSwatches), so the window
-- is walked again after each of those and each frame is skinned once. Feature-detected: a missing frame or global is skipped.
--
-- Left out on purpose, because the mockup shows a computed display and the rule for this pass is "keep the functionality the same as
-- vanilla": the live preview pane that re-colours as a type is clicked, the typing line, the "this page" counters (on, off, types),
-- the corner reticle on the clicked row, the drag to reorder note and the add tab key, and the pink close key (the stock window has
-- none). The chat window tab strip (ChatConfigFrameChatTabManager) and the text to speech page keep their stock look.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char, G = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin, FS.GroupSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and G and G.Card and PanelSkins.RequireExport(
    Theme.SkinPanel and Theme.ApplyMono,
    "ChatSettings.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit, FS.CharacterSkin or FS.GroupSkin missing")) then return end

local Cfg = {}
FS.ChatSettingsSkin = Cfg

local C, Weak, Region, Named, Mono = G.C, G.Weak, G.Region, G.Named, G.Mono
local Try, List = Kit.Try, Char.List
local function Step(name, fn, ...) return G.Step("chatsettings", name, fn, ...) end

local S = { boxes = Weak(), cards = Weak(), buttons = Weak(), done = {} }
Cfg.state = S

local MAX_DEPTH = 7

-- Calls fn(frame) on every sub frame of `root` down to MAX_DEPTH (the pages are nested boxes in boxes).
local function Walk(root, fn, depth)
    depth = depth or 1
    if depth > MAX_DEPTH then return end
    for _, child in ipairs(List(root, "GetChildren")) do
        if type(child) == "table" then
            fn(child)
            Walk(child, fn, depth + 1)
        end
    end
end

-- A message type row (ChatConfigCheckboxTemplate): a frame that carries the check button, its label and, for most, a colour swatch.
-- The colour rows of the other page (ChatConfigSwatchTemplate) have no check button but draw their border box the same way, and
-- ChatConfigBorderBoxTemplate marks that with a clear backdrop (backdropColorAlpha 0), where the wells have a filled one.
local function IsRow(frame)
    if Kit.TypeOf(frame) ~= "Frame" then return false end
    return type(frame.CheckButton) == "table" or (type(frame.NineSlice) == "table" and frame.backdropColorAlpha == 0)
end

-- A well the stock code draws with a backdrop (TooltipBackdropTemplate): it carries a NineSlice child. The dialog border and the
-- NineSlice frame itself are never such a frame (they ARE the pieces), so the window border is not drawn over.
local function IsBox(frame)
    return Kit.TypeOf(frame) == "Frame" and type(frame.NineSlice) == "table"
end

local function SkinRow(row)
    if S.cards[row] then return end
    G.HoldRegions(row)
    Kit.HoldFrame(row.NineSlice)
    S.cards[row] = G.Card(row, { accent = C.cyan, hold = {}, px = 12 })
    local check = row.CheckButton
    if check then Mono(check.Text, check, 12, C.text) end
end

local function SkinBox(box)
    if S.boxes[box] then return end
    G.HoldRegions(box)
    Kit.HoldFrame(box.NineSlice)
    S.boxes[box] = Char.Box(box, "BORDER")
    Char.PaintBox(S.boxes[box], C.ink, 0.5, C.dim, 1, 1)
    Mono(box.header, box, 12, C.cyan)
    local name = Try(box.GetName, box)
    if type(name) == "string" then Mono(_G[name .. "ColorHeader"], box, 11, C.muted) end
end

-- A category button (Chat, Combat, Channels, Other, Settings ...): a card, the stock highlight held, the chosen one lit by the stock
-- LockHighlight.
local function SkinCategory(button)
    if type(button) ~= "table" or S.buttons[button] then return end
    S.buttons[button] = G.Card(button, { accent = C.cyan, hold = { "^Highlight$" }, px = 12 })
    HeldArt.Hold(Try(button.GetHighlightTexture, button))
    Mono(button.NormalText, button, 12, C.text)
end

local function SkinPages(frame)
    Walk(frame, function(child)
        if IsRow(child) then Step("row", SkinRow, child)
        elseif IsBox(child) then Step("box", SkinBox, child) end
    end)
    for i = 1, 7 do Step("category", SkinCategory, Named("ChatConfigCategoryFrameButton" .. i)) end
    local filters = Named("ChatConfigCombatSettingsFilters")
    if filters then G.Rows(filters.ScrollBox, SkinCategory) end
end

local function SkinWindow(frame)
    if S.done.window then return end
    S.done.window = true
    Kit.HoldFrame(frame.Border)
    G.HoldRegions(frame)
    -- The stock header plate and its title are replaced by the band title the panel skin draws; the header frame is only held (alpha), so
    -- the stock code that sets its text keeps working.
    Kit.HoldFrame(Region(frame, "Header"))
    Theme.SkinPanel(frame, { strip = false, fillColor = Theme.COLOR_BG, accent = C.violet, title = "chat settings" })
end

-- The pages make their rows when the window loads and the channel rows each time it is shown or the channel list changes, so the
-- walk runs again after each stock builder (one pass per frame, however many rows it made).
local pending = false

local function Rebuild()
    if pending then return end
    pending = true
    Kit.Later(function()
        pending = false
        PanelSkins.DeferCombat(Cfg.Build)
    end)
end

local function Build()
    local frame = Named("ChatConfigFrame")
    if not frame then return end
    Step("window", SkinWindow, frame)
    Step("pages", SkinPages, frame)
    if not S.done.sweep then
        S.done.sweep = true
        PanelSkins.SweepOnShow(frame)
        Kit.HookScript(frame, "OnShow", Rebuild)
        for _, builder in ipairs({ "ChatConfig_CreateCheckboxes", "ChatConfig_CreateTieredCheckboxes", "ChatConfig_CreateColorSwatches" }) do
            if type(_G[builder]) == "function" and type(hooksecurefunc) == "function" then pcall(hooksecurefunc, builder, Rebuild) end
        end
        frame.fsChatSettingsSkin = true
    end
end
Cfg.Build = Build

PanelSkins.RegisterInspect("ChatSettings", { { name = "ChatConfigFrame", guard = "fsChatSettingsSkin" } })

-- Module power: the chat settings window is the Chat module's own look as well as a window skin, so it is skinned only with
-- both switches on (Window skins and Chat). Started at this addon's ADDON_LOADED, where both are known; with either off the
-- window is not listened for, hooked or touched.
local function Start()
    if FS.Chat and FS.Chat.ModuleOff and FS.Chat.ModuleOff() then return end
    PanelSkins.DeferCombat(Build)
    PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
end
local MS = FS.ModuleSwitch
if MS then MS.WhenOn("m.skins", Start) else Start() end
