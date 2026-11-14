-- Forever STUwave: Charters, invite, rename and death recap
-- The small windows of the collections and misc mockup (mockups/collections-misc-2026-11-12.html, sections 6 to 8), restyled in place:
-- the guild registrar and the petition (the charter windows), the guild invite, the guild rename window and the death recap. The window
-- shells of the registrar, the petition and the rename window, the text buttons, the scroll bars and the plain edit boxes already wear
-- the shared panel and control skins (Panels.lua and the controls sweep); this file adds the parts that were still stock:
--
--   * registrar and petition: the parchment held, the greeting, purchase and member texts in mono (titles cyan, body text, a muted
--     cost label and note), the two greeting options as ink cards with the stock quest icon kept, the guild name edit box a ring
--     box with its chat border art held, the cost in the mono money style;
--   * the guild invite: the stock frame art, the stock backdrop and the gold ring held, the guild crest (tabard, emblem and its
--     colour border) kept, panel chrome and a cyan LED edge of ours, the texts in mono with the guild name in cyan;
--   * the guild rename window: the panel skin, the parchment held, the texts in mono, the two options as cards, the status line in
--     mono with its stock red kept, the costs in the mono money style;
--   * the death recap: the eight stock border pieces, backdrop, inner glow and divider held, panel chrome and a pink LED edge of
--     ours, every row of the list an ink card whose LED edge turns pink on the killing blow, the amounts in mono with their stock red
--     kept, the spell name and caster in mono, the spell icon in a ring box.
--
-- Skin only, as in Commerce.lua: no SetScript, no SetAttribute, no reparent, no resize or re-anchor of a Blizzard frame, alpha holds
-- (FS.HeldArt) and post-hooks only, so every purchase, signature, invite, rename and tooltip flow stays stock. Every frame is
-- feature-detected by name or key; a missing one is skipped (the rename window and the death recap load on demand).
--
-- Left out on purpose, because the mockup shows a computed display and the rule for this pass is "keep the functionality the same as
-- vanilla": the scroll header that fills as the guild name is typed, the nine neon signature lines and the signed meter of the
-- petition, the crest medallion drawn for the invite, the struck through old name of the rename window, and the health chart and
-- time line the death recap mockup computes from the combat log. The window shell of the registrar and the petition, the guild
-- crest of the invite and the quest icon of the options keep their stock look. The toasts of the same mockup (quick join, event
-- banner, bonus roll) are not skinned here: see the report of this pass.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char, G, Col = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin, FS.GroupSkin, FS.CollectionsSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and G and G.Card and G.Bar and Col and Col.Pin and Col.Maps and Col.IconRing
    and PanelSkins.RequireExport(Theme.SkinPanel and Theme.AddPanelChrome and Theme.StyleMoney,
        "Charters.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit, FS.CharacterSkin, FS.GroupSkin or FS.CollectionsSkin missing")) then return end

local Chart = {}
FS.CharterSkin = Chart

local C, Weak, Region, Named = G.C, G.Weak, G.Region, G.Named
local Try = Kit.Try
local Pin, Maps = Col.Pin, Col.Maps
local function Step(name, fn, ...) return G.Step("charters", name, fn, ...) end

local S = { cards = G.cards, edits = Weak(), chrome = Weak(), leds = Weak(), panels = Weak(), marks = Weak(), rings = Col.state.rings }
Chart.state = S

local function Shown(region)
    return type(region) == "table" and Try(region.IsShown, region) == true
end

-- A global label by name, nil when this client has none.
local function Label(name)
    local fs = _G[name]
    return type(fs) == "table" and fs or nil
end

local function Mark(frame)
    if S.marks[frame] then return end
    S.marks[frame] = true
    frame.fsCharterSkin = true
    Kit.HookScript(frame, "OnShow", function() Kit.Later(function() PanelSkins.DeferCombat(Chart.Build) end) end)
end

-------------------------------------------------------------------------------
-- Shared pieces
-------------------------------------------------------------------------------

-- A gossip style option button (QuestTitleButtonTemplate, GossipTitleButtonTemplate): an ink card with the stock highlight held, the
-- quest icon and the click kept, the label in mono.
local function SkinOption(btn)
    if type(btn) ~= "table" or Kit.TypeOf(btn) ~= "Button" or S.cards[btn] then return end
    local rec = G.Card(btn, { accent = C.cyan, px = 12 })
    if not rec then return end
    for _, getter in ipairs({ "GetNormalTexture", "GetHighlightTexture", "GetPushedTexture", "GetDisabledTexture" }) do
        HeldArt.Hold(Try(btn[getter], btn))
    end
    local label = type(btn.GetFontString) == "function" and Try(btn.GetFontString, btn) or nil
    Pin(label, btn, 12, Maps.Text)
end

-- A bare edit box (the guild name): the chat border art held first, a ring box over its rect, the text in mono.
local function SkinEdit(box)
    if type(box) ~= "table" or S.edits[box] or type(box.CreateTexture) ~= "function" then return end
    G.HoldRegions(box)
    Kit.HoldFrame(box.NineSlice or box.Border)
    local ring = Char.Box(box, "BORDER")
    Char.PaintBox(ring, C.ink, 1, C.violet, 1, 1)
    S.edits[box] = ring
    Kit.RestyleLabel(box, box, 12, C.text)
    Char.PinColor(box, C.text)
end

-------------------------------------------------------------------------------
-- The registrar and the petition
-------------------------------------------------------------------------------

local function SkinRegistrar()
    local win = Named("GuildRegistrarFrame")
    if not win then return end
    HeldArt.Hold(win.Bg)
    HeldArt.Hold(Label("GuildRegistrarFrameBg"))
    Pin(Label("GuildRegistrarText"), win, 12, Maps.Text)
    Pin(Label("GuildRegistrarFrameNpcNameText"), win, 12, Maps.Text)
    Pin(Label("AvailableServicesText"), win, 13, Maps.Cyan)
    SkinOption(_G.GuildRegistrarButton1)
    SkinOption(_G.GuildRegistrarButton2)
    Pin(Label("GuildRegistrarPurchaseText"), win, 12, Maps.Text)
    Pin(Label("GuildRegistrarCostLabel"), win, 11, Maps.Muted)
    Theme.StyleMoney(_G.GuildRegistrarMoneyFrame)
    SkinEdit(_G.GuildRegistrarFrameEditBox)
    Mark(win)
end

local PETITION_TITLES = { "PetitionFrameCharterTitle", "PetitionFrameMasterTitle", "PetitionFrameMemberTitle" }
local PETITION_NAMES = { "PetitionFrameCharterName", "PetitionFrameMasterName" }

local function SkinPetition()
    local win = Named("PetitionFrame")
    if not win then return end
    HeldArt.Hold(win.Bg)
    HeldArt.Hold(Label("PetitionFrameBg"))
    for _, name in ipairs(PETITION_TITLES) do Pin(Label(name), win, 13, Maps.Cyan) end
    for _, name in ipairs(PETITION_NAMES) do Pin(Label(name), win, 12, Maps.Text) end
    for i = 1, 9 do Pin(Label("PetitionFrameMemberName" .. i), win, 12, Maps.Text) end
    Pin(Label("PetitionFrameInstructions"), win, 11, Maps.Muted)
    Pin(Label("PetitionFrameNpcNameText"), win, 12, Maps.Text)
    Mark(win)
end

-------------------------------------------------------------------------------
-- The guild invite
-------------------------------------------------------------------------------

local function SkinInvite()
    local f = Named("GuildInviteFrame")
    if not f then return end
    if not S.chrome[f] then
        S.chrome[f] = true
        Kit.HoldFrame(f.NineSlice)
        Kit.HoldFrame(f.Border)
        HeldArt.Hold(f.Bg)
        HeldArt.Hold(Label("GuildInviteFrameBackground"))
        HeldArt.Hold(Label("GuildInviteFrameTabardRing"))
        Theme.AddPanelChrome(f, { accent = C.violet, fillColor = Theme.COLOR_BG, glowAlpha = 0.35 })
        S.leds[f] = G.Bar(f, C.cyan, 3, 9, 3)
    end
    Pin(Label("GuildInviteFrameInviterName"), f, 11, Maps.Muted)
    Pin(Label("GuildInviteFrameInviteText"), f, 11, Maps.Muted)
    Pin(Label("GuildInviteFrameGuildName"), f, 14, Maps.Cyan)
    Pin(Label("GuildInviteFrameWarningText"), f, 11, Maps.Muted)
    local points = Region(f, "Points")
    if points then
        Pin(points.Title, points, 10, Maps.Muted)
        Pin(points.Text, points, 15, Maps.Keep)
    end
    Mark(f)
end

-------------------------------------------------------------------------------
-- The guild rename window
-------------------------------------------------------------------------------

local function SkinRename()
    local f = Named("GuildRenameFrame")
    if not f then return end
    if not S.panels[f] then
        S.panels[f] = true
        Theme.SkinPanel(f, { fillColor = Theme.COLOR_BG, accent = C.violet, title = "rename" })
    end
    HeldArt.Hold(f.Background)
    local flow = Region(f, "TitleFlow")
    if flow then
        Pin(flow.Description, flow, 12, Maps.Text)
        SkinOption(flow.RenameOption)
        SkinOption(flow.RefundOption)
    end
    local rename = Region(f, "RenameFlow")
    if rename then
        Pin(rename.Description, rename, 12, Maps.Text)
        Pin(rename.StatusText, rename, 11, Maps.Keep)
        Pin(rename.CostLabel, rename, 11, Maps.Muted)
        Theme.StyleMoney(rename.CostFrame)
    end
    Theme.StyleMoney(f.MoneyFrame)
    Mark(f)
end

-------------------------------------------------------------------------------
-- The death recap
-------------------------------------------------------------------------------

-- The recap LED: pink on the row that carries the tombstone (the killing blow), dim on the rest.
local function RecapLed(row)
    return function()
        if Shown(Region(Region(row, "DamageInfo"), "TombstoneIcon")) then return C.pink end
        return C.dim
    end
end

local function SkinRecapRow(row)
    if type(row) ~= "table" then return end
    if S.cards[row] then G.PaintCard(row) return end
    local rec = G.Card(row, { accent = C.cyan, px = 11, led = RecapLed(row) })
    if not rec then return end
    local damage, spell = Region(row, "DamageInfo"), Region(row, "SpellInfo")
    if damage then
        Pin(damage.Amount, damage, 12, Maps.Keep)
        Pin(damage.AmountLarge, damage, 15, Maps.Keep)
        local function again() G.PaintCard(row) end
        local tomb = Region(damage, "TombstoneIcon")
        if tomb then
            for _, m in ipairs({ "Show", "Hide", "SetShown" }) do Kit.HookFunc(tomb, m, again) end
        end
    end
    if spell then
        HeldArt.Hold(spell.IconBorder)
        Col.IconRing(spell, spell.Icon)
        Pin(spell.Name, spell, 12, Maps.Text)
        Pin(spell.Caster, spell, 10, Maps.Muted)
    end
    G.PaintCard(row)
end

local function SkinRecap()
    local f = Named("DeathRecapFrame")
    if not f then return end
    if not S.chrome[f] then
        S.chrome[f] = true
        G.HoldRegions(f)
        Theme.AddPanelChrome(f, { accent = C.violet, fillColor = Theme.COLOR_BG, glowAlpha = 0.35 })
        G.Rule(f, C.dim, 1, 24, 8)
        S.leds[f] = G.Bar(f, C.pink, 3, 9, 3)
    end
    Pin(f.Title, f, 12, Maps.Cyan)
    Pin(f.Unavailable, f, 12, Maps.Muted)
    G.Rows(Region(f, "ScrollBox"), SkinRecapRow)
    Mark(f)
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local function Build()
    Step("registrar", SkinRegistrar)
    Step("petition", SkinPetition)
    Step("invite", SkinInvite)
    Step("rename", SkinRename)
    Step("recap", SkinRecap)
end
Chart.Build = Build

PanelSkins.RegisterInspect("Charters", {
    { name = "GuildRegistrarFrame", guard = "fsCharterSkin" },
    { name = "PetitionFrame", guard = "fsCharterSkin" },
    { name = "GuildInviteFrame", guard = "fsCharterSkin" },
    { name = "GuildRenameFrame", guard = "fsCharterSkin" },
    { name = "DeathRecapFrame", guard = "fsCharterSkin" },
})

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
