-- Forever STUwave: Social
-- The friends window (FriendsFrame) past its shell, from the approved SOCIAL mockup (mockups/social-group-2026-11-12.html,
-- section 1): the friends list rows, the pending request rows and header, the Battle.net banner, the ignore list window, the
-- Who page and the Raid page. The window shell, the tabs, the text buttons, the scroll bars, the dropdown, the search box and the
-- check boxes already wear the shared skins (Panels.lua, the controls sweep); this file adds the parts that were still stock.
--
--   * Friends: every row is an ink card with a 3 px LED bar down its left edge (cyan online, amber away, pink busy, dim offline,
--     read from the status icon the stock code set), the name and info lines in mono with the stock name colour kept, a cyan edge
--     on hover, and the mockup's lock-on reticle on the selected row. The stock row wash, status icon and highlight are held;
--     the game icon, the favourite star and the invite and summon keys stay as they are.
--   * Requests: the header is an amber card (its arrows tinted amber, the stock flash held), each request an amber card with the
--     stock Accept key as a cyan text key and Decline a pink square key.
--   * The Battle.net banner is a band card in mono, the contacts menu button a square key.
--   * Ignored: the window is the panel skin with a pink title band, rows are small cards, the selected one lit.
--   * Who: the four column headings are band keys (the stock sort arrow and clicks kept), the list inset a ring, rows cards in mono.
--   * Raid: the group outlines, group slots and class buttons are cards; the Raid Info window is a dialog.
--
-- Skin only, as in Commerce.lua: no SetScript, no SetAttribute, no reparent, no resize or re-anchor of a Blizzard frame, alpha
-- holds (FS.HeldArt) and post-hooks only, so every click, drag, tooltip, whisper and invite flow stays stock. The rows are pooled by
-- a ScrollBox that hands them to stock code after we run, so each row is painted again after every update of its list. Every frame
-- is feature-detected by name or key; a missing one is skipped. Raid buttons are secure: only textures and post-hooks, built
-- out of combat.
--
-- Left out on purpose, because the mockup shows a computed display and the rule for this pass is "keep the functionality the
-- same as vanilla": the presence trace and the last seen pips of a friend row, the Battle.net hex glyph and game chips, the redacted
-- ignored names and unmute key, the Who radar histogram, the raid role gauges and group dock, the draining lockout bars and the
-- three way switch that would replace the tabs. The Quick Join tab, the broadcast pop up and the add friend dialogs keep their
-- stock look.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char, G = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin, FS.GroupSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and G and Char.Box and Char.PaintBox and PanelSkins.RequireExport(
    Theme.SkinPanel and Theme.ApplyMono,
    "Social.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit, FS.CharacterSkin or FS.GroupSkin missing")) then return end

local Soc = {}
FS.SocialSkin = Soc

local C, Weak, Region, Named, Mono = G.C, G.Weak, G.Region, G.Named, G.Mono
local Plain, Try, List = Kit.Plain, Kit.Try, Char.List
local function Step(name, fn, ...) return G.Step("social", name, fn, ...) end

local S = { rows = Weak(), cards = Weak(), headers = Weak(), dividers = Weak(), done = {}, hooked = Weak() }
Soc.state = S

-- A row's size in physical pixels, for seating a reticle on it (the stock friend row is 298 x 34 units).
local function SizeOf(frame, wUnits, hUnits)
    local w, h = Kit.SizePx(frame)
    if w and h then return w, h end
    local ppu = Kit.Ppu(frame)
    return math.floor(wUnits * ppu + 0.5), math.floor(hUnits * ppu + 0.5)
end

-- Runs `fn` after `frame` is shown (once per frame; a plain post-hook, no field is written on the Blizzard frame).
local function OnShowOnce(frame, key, fn)
    if type(frame) ~= "table" then return end
    S.hooked[frame] = S.hooked[frame] or {}
    if S.hooked[frame][key] then return end
    S.hooked[frame][key] = true
    Kit.HookScript(frame, "OnShow", function() Kit.Later(fn) end)
end

-------------------------------------------------------------------------------
-- Friends list rows
-------------------------------------------------------------------------------

-- The LED colour of a friend row, told from the status icon the stock code last set (compared with the stock constants).
local function PresenceColor(row)
    local icon = row.status
    local path = type(icon) == "table" and Plain(Try(icon.GetTexture, icon)) or nil
    if path == nil then return C.dim, true end
    if _G.FRIENDS_TEXTURE_OFFLINE ~= nil and path == _G.FRIENDS_TEXTURE_OFFLINE then return C.dim, true end
    if _G.FRIENDS_TEXTURE_AFK ~= nil and path == _G.FRIENDS_TEXTURE_AFK then return C.amber, false end
    if _G.FRIENDS_TEXTURE_DND ~= nil and path == _G.FRIENDS_TEXTURE_DND then return C.pink, false end
    return C.cyan, false
end

local function PaintFriend(row)
    local rec = S.rows[row]
    if not rec then return end
    local color, offline = PresenceColor(row)
    local hover = rec.state and rec.state.hover
    local edge = (rec.selected or hover) and C.cyan or C.dim
    Char.PaintBox(rec.box, offline and C.row or C.ink, 1, edge, offline and not (rec.selected or hover) and 0.6 or 1, rec.selected and 2 or 1)
    rec.led.Paint(color, offline and 0.55 or 1)
    Kit.PaintReticle(rec.reticle, C.cyan, 1)
    Kit.ShowReticle(rec.reticle, rec.selected and true or false)
end

local function SkinFriendRow(row)
    if S.rows[row] then return PaintFriend(row) end
    local keep = {}
    for _, key in ipairs({ "gameIcon", "Favorite" }) do if type(row[key]) == "table" then keep[row[key]] = true end end
    HeldArt.HoldButton(row, keep)
    HeldArt.Hold(row.background)
    HeldArt.Hold(row.status)
    HeldArt.Hold(row.highlight)
    local rec = { box = Char.Box(row, "BORDER"), led = G.Bar(row, C.dim, 3, 0), reticle = Kit.Reticle(row, "OVERLAY", 6) }
    S.rows[row] = rec
    local w, h = SizeOf(row, 298, 34)
    Kit.SeatReticle(rec.reticle, 0, 0, w, h, 2, 8)
    Mono(row.name, row, 12, C.text)
    Mono(row.info, row, 10, C.muted)
    rec.state = Kit.Track(row, PaintFriend)
    Kit.HookFunc(row, "LockHighlight", function() rec.selected = true; PaintFriend(row) end)
    Kit.HookFunc(row, "UnlockHighlight", function() rec.selected = false; PaintFriend(row) end)
    PaintFriend(row)
end

-- A request row (a Battle.net or a party invite): an amber card, Accept a cyan text key, Decline a pink square key.
local function PaintInvite(row)
    local rec = S.cards[row]
    if not rec then return end
    local hover = rec.state and rec.state.hover
    Char.PaintBox(rec.box, C.row, 1, hover and C.cyan or C.amber, 1, 1)
end

local function SkinInviteRow(row)
    if S.cards[row] then return end
    HeldArt.Hold(row.Background)
    local rec = { box = Char.Box(row, "BORDER"), led = G.Bar(row, C.amber, 3, 0) }
    S.cards[row] = rec
    Mono(row.Name, row, 12, C.text)
    local skin = FS.ButtonSkins and FS.ButtonSkins.SkinTextButton
    if skin and type(row.AcceptButton) == "table" then skin(row.AcceptButton, { accent = "cyan" }) end
    local decline = row.DeclineButton
    if type(decline) == "table" then
        local icon = Region(decline, "Icon")
        G.Square(decline, { icon = icon, accent = C.pink })
        if icon and icon.SetVertexColor then pcall(icon.SetVertexColor, icon, C.pink[1], C.pink[2], C.pink[3], 1) end
    end
    rec.state = Kit.Track(row, PaintInvite)
    PaintInvite(row)
end

-- The "Friend requests" header: a collapsible button, so an amber key with its two arrows tinted amber.
local function PaintHeaderCard(btn)
    local rec = S.cards[btn]
    if not rec then return end
    local hover = rec.state and (rec.state.hover or rec.state.pressed)
    Char.PaintBox(rec.box, C.band, 1, hover and C.cyan or C.amber, 1, 1)
end

local function SkinInviteHeader(btn)
    if S.cards[btn] then return end
    local keep = {}
    for _, key in ipairs({ "RightArrow", "DownArrow" }) do
        local arrow = Region(btn, key)
        if arrow then
            keep[arrow] = true
            if arrow.SetVertexColor then pcall(arrow.SetVertexColor, arrow, C.amber[1], C.amber[2], C.amber[3], 1) end
        end
    end
    HeldArt.HoldButton(btn, keep)
    local rec = { box = Char.Box(btn, "BORDER") }
    S.cards[btn] = rec
    local label = type(btn.GetFontString) == "function" and Try(btn.GetFontString, btn) or nil
    Mono(label, btn, 12, C.amber)
    rec.state = Kit.Track(btn, PaintHeaderCard)
    PaintHeaderCard(btn)
end

-- A divider line (the stock "online / offline" rule) and a section header (Ignored, Blocked): the art held, one rule of ours.
local function SkinDivider(row)
    if S.dividers[row] then return end
    S.dividers[row] = true
    G.HoldRegions(row)
    G.MidRule(row, C.dim, 1, 4)
end

local function SkinSectionHeader(row)
    if S.dividers[row] then return end
    S.dividers[row] = true
    G.HoldRegions(row)
    Mono(row.Title, row, 11, C.muted)
    G.Rule(row, C.dim, 1, -1, 2)
end

-- A row of the friends ScrollBox, told by the keys the stock template gives it.
local function SkinListRow(row)
    if type(row) ~= "table" then return end
    local kind = Kit.TypeOf(row)
    if type(row.AcceptButton) == "table" and type(row.DeclineButton) == "table" then
        Step("invite", SkinInviteRow, row)
    elseif kind == "Button" and type(row.RightArrow) == "table" and type(row.DownArrow) == "table" then
        Step("invite-header", SkinInviteHeader, row)
    elseif kind == "Button" and type(row.status) == "table" and type(row.name) == "table" then
        Step("friend", SkinFriendRow, row)
    elseif type(row.Title) == "table" then
        Step("section", SkinSectionHeader, row)
    elseif kind == "Frame" and #List(row, "GetChildren") == 0 and #List(row, "GetRegions") == 1 then
        Step("divider", SkinDivider, row)
    end
end

local function SkinFriendsList()
    local list = Named("FriendsListFrame")
    if not list then return end
    G.Rows(list.ScrollBox, SkinListRow)
    -- the disabled message the friends list shows over its rows
    Mono(list.FriendsDisabledText, list, 12, C.muted)
end

-------------------------------------------------------------------------------
-- Battle.net banner
-------------------------------------------------------------------------------

local function SkinBanner()
    local banner = Named("FriendsFrameBattlenetFrame")
    if not banner or S.done.banner then return end
    S.done.banner = true
    G.HoldRegions(banner)
    local box = Char.Box(banner, "BORDER")
    Char.PaintBox(box, C.band, 1, C.violet, 1, 1)
    G.Bar(banner, C.cyan, 3, 0)
    Mono(banner.Tag, banner, 12, C.cyan)
    Mono(banner.UnavailableLabel, banner, 11, C.amber)
    local menu = banner.ContactsMenuButton
    if type(menu) == "table" then G.Square(menu, { icon = Region(menu, "Icon") }) end
end

-------------------------------------------------------------------------------
-- Ignore list window
-------------------------------------------------------------------------------

local function PaintIgnoreRow(row)
    local rec = S.rows[row]
    if not rec then return end
    local hover = rec.state and rec.state.hover
    Char.PaintBox(rec.box, rec.selected and C.band or C.row, 1, (rec.selected or hover) and C.pink or C.dim, 1, 1)
end

local function SkinIgnoreRow(row)
    if type(row) ~= "table" or S.rows[row] then return end
    if Kit.TypeOf(row) ~= "Button" or type(row.name) ~= "table" then
        if type(row) == "table" and type(row.Title) == "table" then Step("ignore-header", SkinSectionHeader, row) end
        return
    end
    HeldArt.HoldButton(row)
    local rec = { box = Char.Box(row, "BORDER") }
    S.rows[row] = rec
    Mono(row.name, row, 11, C.text)
    rec.state = Kit.Track(row, PaintIgnoreRow)
    Kit.HookFunc(row, "LockHighlight", function() rec.selected = true; PaintIgnoreRow(row) end)
    Kit.HookFunc(row, "UnlockHighlight", function() rec.selected = false; PaintIgnoreRow(row) end)
    PaintIgnoreRow(row)
end

local function SkinIgnoreWindow()
    local win = Region(Named("FriendsFrame"), "IgnoreListWindow")
    if not win or S.done.ignore then return end
    S.done.ignore = true
    Theme.SkinPanel(win, { fillColor = Theme.COLOR_BG, accent = C.pink, title = "ignored" })
    local skin = FS.ButtonSkins and FS.ButtonSkins.SkinTextButton
    if skin and type(win.UnignorePlayerButton) == "table" then skin(win.UnignorePlayerButton, { accent = "pink" }) end
    G.Rows(win.ScrollBox, SkinIgnoreRow)
end

-------------------------------------------------------------------------------
-- Who page
-------------------------------------------------------------------------------

local function PaintWhoRow(row)
    local rec = S.rows[row]
    if not rec then return end
    local hover = rec.state and rec.state.hover
    Char.PaintBox(rec.box, rec.selected and C.band or C.row, 1, (rec.selected or hover) and C.cyan or C.dim, rec.selected and 1 or 0.7, 1)
end

local function SkinWhoRow(row)
    if type(row) ~= "table" or S.rows[row] or Kit.TypeOf(row) ~= "Button" then return end
    HeldArt.HoldButton(row)
    local rec = { box = Char.Box(row, "BORDER") }
    S.rows[row] = rec
    for _, key in ipairs({ "Name", "Variable", "Level", "Class" }) do Mono(row[key], row, 11, C.text) end
    rec.state = Kit.Track(row, PaintWhoRow)
    Kit.HookFunc(row, "LockHighlight", function() rec.selected = true; PaintWhoRow(row) end)
    Kit.HookFunc(row, "UnlockHighlight", function() rec.selected = false; PaintWhoRow(row) end)
    PaintWhoRow(row)
end

local function SkinWho()
    local who = Named("WhoFrame")
    if not who then return end
    if not S.done.who then
        S.done.who = true
        for i = 1, 4 do G.Header(Named("WhoFrameColumnHeader" .. i), 11) end
        local inset = Named("WhoFrameListInset") or Region(who, "WhoFrameListInset")
        if inset then
            Kit.HoldFrame(inset.NineSlice)
            HeldArt.Hold(inset.Bg)
            G.HoldRegions(inset)
            Char.PaintBox(Char.Box(who, "BORDER", inset), C.ink, 0.6, C.dim, 1, 1)
            Mono(inset.WhoFrameTotals or Named("WhoFrameTotals"), inset, 11, C.muted)
        end
        local edit = who.EditBox or Named("WhoFrameEditBox")
        if type(edit) == "table" then HeldArt.Hold(edit.Backdrop) end
    end
    G.Rows(who.ScrollBox, SkinWhoRow)
end

-------------------------------------------------------------------------------
-- Raid page
-------------------------------------------------------------------------------

local function PaintCell(btn)
    local rec = S.cards[btn]
    if not rec then return end
    local hover = rec.state and rec.state.hover
    Char.PaintBox(rec.box, C.row, 1, hover and C.cyan or C.dim, 1, 1)
end

local function SkinCell(btn)
    if type(btn) ~= "table" or S.cards[btn] or type(btn.CreateTexture) ~= "function" then return end
    HeldArt.HoldButton(btn)
    local rec = { box = Char.Box(btn, "BORDER") }
    S.cards[btn] = rec
    local name = Try(btn.GetName, btn)
    if type(name) == "string" then
        Mono(_G[name .. "Name"], btn, 11, C.text)
        Mono(_G[name .. "Level"], btn, 10, C.muted)
        Mono(_G[name .. "Class"], btn, 10, C.muted)
        Mono(_G[name .. "Count"], btn, 10, C.text)
    end
    rec.state = Kit.Track(btn, PaintCell)
    PaintCell(btn)
end

local function SkinRaidGroup(group, i)
    if type(group) ~= "table" or S.cards[group] then return end
    G.HoldRegions(group)
    S.cards[group] = { box = Char.Box(group, "BORDER") }
    Char.PaintBox(S.cards[group].box, C.row, 0.6, C.dim, 1, 1)
    local label = group.Label or Named("RaidGroup" .. i .. "Label")
    if type(label) == "table" then
        local fs = type(label.GetFontString) == "function" and Try(label.GetFontString, label) or label
        Mono(fs, group, 11, C.cyan)
        if Kit.TypeOf(label) == "Button" then HeldArt.HoldButton(label) end
    end
end

local function SkinRaid()
    if S.done.raid then return end
    local raid = Named("RaidFrame")
    if not raid then return end
    S.done.raid = true
    for i = 1, 8 do SkinRaidGroup(Named("RaidGroup" .. i), i) end
    for i = 1, 40 do SkinCell(Named("RaidGroupButton" .. i)) end
    for i = 1, 16 do SkinCell(Named("RaidClassButton" .. i)) end
    Mono(Named("RaidFrameNotInRaid") and Named("RaidFrameNotInRaid").Text, raid, 12, C.muted)
    local skin = FS.ButtonSkins and FS.ButtonSkins.SkinTextButton
    if skin then
        skin(Named("RaidFrameConvertToRaidButton"), { accent = "cyan" })
        skin(Named("RaidFrameRaidInfoButton"), {})
    end
end

local function SkinRaidInfo()
    local info = Named("RaidInfoFrame")
    if not info or S.done.raidinfo then return end
    S.done.raidinfo = true
    local Com = FS.CommerceSkin
    if Com and Com.Dialog then Com.Dialog(info, C.violet) end
    for _, name in ipairs({ "RaidInfoInstanceLabel", "RaidInfoIDLabel" }) do G.Header(Named(name), 11) end
    for _, name in ipairs({ "RaidInfoExtendButton", "RaidInfoCancelButton" }) do
        local skin = FS.ButtonSkins and FS.ButtonSkins.SkinTextButton
        if skin and Named(name) then skin(Named(name), { accent = name == "RaidInfoCancelButton" and "pink" or "cyan" }) end
    end
    local scroll = Region(info, "ScrollBox")
    if scroll then
        G.Rows(scroll, function(row)
            G.HoldRegions(row)
            for _, key in ipairs({ "name", "difficulty", "reset", "extended" }) do Mono(Region(row, key), row, 11, C.text) end
        end)
    end
end

-------------------------------------------------------------------------------
-- Drive
-------------------------------------------------------------------------------

local function Build()
    Step("banner", SkinBanner)
    Step("friends", SkinFriendsList)
    Step("ignore", SkinIgnoreWindow)
    Step("who", SkinWho)
    Step("raid", SkinRaid)
    Step("raidinfo", SkinRaidInfo)
    -- the marker /fsinspect skins reads (a plain boolean, written only on a frame that has been skinned)
    for name, field in pairs({ FriendsFrame = "fsSocialSkin", WhoFrame = "fsSocialWhoSkin", RaidFrame = "fsSocialRaidSkin" }) do
        local frame = Named(name)
        if frame and S.done[field] == nil then
            S.done[field] = true
            frame[field] = true
        end
    end
    -- pages that appear as their tab is chosen are built when first shown
    for _, name in ipairs({ "FriendsFrame", "WhoFrame", "RaidFrame", "RaidInfoFrame" }) do
        OnShowOnce(Named(name), "build", function() PanelSkins.DeferCombat(Soc.Build) end)
    end
    OnShowOnce(Region(Named("FriendsFrame"), "IgnoreListWindow"), "build", function() PanelSkins.DeferCombat(Soc.Build) end)
end
Soc.Build = Build

PanelSkins.RegisterInspect("Social", { { name = "FriendsFrame", guard = "fsSocialSkin" }, { name = "WhoFrame", guard = "fsSocialWhoSkin" },
    { name = "RaidFrame", guard = "fsSocialRaidSkin" } })

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
