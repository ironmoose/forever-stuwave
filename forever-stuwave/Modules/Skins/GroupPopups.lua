-- Forever STUwave: Group popups
-- The ready check, the role poll, the PvP role check, the battleground invite and the raid manager pull-out restyled in place from the approved LOOT + GROUP
-- mockup (mockups/loot-group-2026-11-12.html, sections 4 and 5), over the real trees (Blizzard_FrameXML ReadyCheck.xml,
-- RolePoll.xml; Blizzard_GroupFinder PVPHelper.xml, LFGFrame.xml for the role button template):
--
--   * the ready check is one panel skin on ReadyCheckListenerFrame (the frame that carries all the stock art) with a `stuwave://ready`
--     band: the dialog background, the portrait frame and its title are held. Popups.lua also draws a panel on the OUTER
--     ReadyCheckFrame, which the stock code leaves blank and shows empty when YOU start the check, so that panel is held. The two
--     keys are cut keys over the stock buttons: READY a green key with a check, NOT READY a pink one;
--   * the role poll and the PvP role check hold the gold dialog border and the stock heading and wear a band (`stuwave://roles`,
--     `stuwave://queue`). Every role button is a key: a drawn glyph (shield, cross, blade) in the role's colour, the role word and a
--     lit line under it; hover and a checked role light the edge, a role the stock code turns off (Disable) goes steel and hatched
--     and loses its line. The radio or check box of each role is the shared control skin. Accept and Decline are keys;
--   * the raid manager pull-out wears our panel over its stock background (see SkinManager);
--   * the battleground invite is a pink panel (`stuwave://invite`): the stock background, border, divider and underline held, the
--     battleground name amber, the texts mono, Enter Battle and Leave Queue as keys. The stock role icon is the stub of the ticket.
--
-- A key is a text button the default skin (FS.ButtonSkins) has ALREADY drawn (Popups.lua's sweep got there first, or we ask for it so
-- the sweep leaves it alone): its plate, ring, halo and label are held and ours drawn over them, because the default text button has no
-- green and no glyph. Clicks, tooltips and the stock text stay stock.
--
-- Skin only, as in Commerce.lua and Loot.lua: no SetScript, no SetAttribute, no reparent, no resize or re-anchor of a Blizzard frame,
-- post-hooks and alpha holds only. Names are the real tree; each is feature-detected and a missing one is skipped.
--
-- Left out on purpose, because the mockup shows a display this client has no data for or a function the stock frame does not have:
-- the 30 second fuse and the pegs of the ready check (the mockup marks both as unconfirmed, fed by READY_CHECK_CONFIRM), the
-- initiator chip, the "not for you" and "open" notes under the role keys, the queue wait line, the segmented countdown and
-- the perforated stub of the invite ticket (the stock dialog carries no timer), and the radio's move to the key's corner (the stock
-- check box keeps its own seat).

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char, G, L = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin, FS.GroupSkin, FS.LootSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and G and L and L.Glyph and L.Card and L.BITS and Theme.ApplyMono) then return end

local P = {}
FS.GroupPopupSkin = P

local C = L.C
local RED = { 1, 0.231, 0.306 }
local Plain, Try, List = Kit.Plain, Kit.Try, Char.List
local Step = function(name, fn, ...) return G.Step("popups", name, fn, ...) end

local function Weak() return setmetatable({}, { __mode = "k" }) end
local S = { keys = Weak(), roles = Weak(), bands = Weak(), done = {} }
P.state = S

-------------------------------------------------------------------------------
-- Role glyphs: 16 x 16 bitmaps (the mockup's shield, cross and blade), drawn twice as large
-------------------------------------------------------------------------------

L.BITS.shield = {
    "................", "..############..", "..#..........#..", "..#....##....#..", "..#....##....#..", "..#..######..#..",
    "..#..######..#..", "..#....##....#..", "..#....##....#..", "...#...##...#...", "....#......#....", ".....#....#.....",
    "......#..#......", ".......##.......", "................", "................",
}
L.BITS.cross = {
    "................", "......####......", "......#..#......", "......#..#......", "......#..#......", "......#..#......",
    ".######..######.", ".#............#.", ".#............#.", ".######..######.", "......#..#......", "......#..#......",
    "......#..#......", "......#..#......", "......####......", "................",
}
L.BITS.blade = {
    "................", "............##..", "...........##...", "..........##....", ".........##.....", "........##......",
    "....#..##.......", ".....###........", ".....##.........", "....##.#........", "...##....#......", "..##............",
    ".##.............", ".#..............", "................", "................",
}

-------------------------------------------------------------------------------
-- Pieces shared by every popup
-------------------------------------------------------------------------------

-- Holds a stock FontString at alpha 0 (the heading the band label replaces): alpha survives SetText, Show and layout.
local function HoldHeadings(frame)
    for _, region in ipairs(List(frame, "GetRegions")) do
        if Kit.TypeOf(region) == "FontString" then Kit.HoldFrame(region) end
    end
end

-- A title band like Theme.SkinPanel draws for a panel with a title, for a frame Popups.lua has already given its panel (no title).
local function Band(frame, title, accent)
    if S.bands[frame] then return S.bands[frame] end
    local inset = Theme.PanelBandInset()
    local band = frame:CreateTexture(nil, "ARTWORK")
    band:SetColorTexture(accent[1], accent[2], accent[3], 0.08)
    band:SetPoint("TOPLEFT", frame, "TOPLEFT", inset, -inset)
    band:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -inset, -inset)
    band:SetHeight(Theme.PANEL_HEADER_H)
    local rule = frame:CreateTexture(nil, "ARTWORK")
    rule:SetColorTexture(accent[1], accent[2], accent[3], 0.30)
    rule:SetPoint("TOPLEFT", band, "BOTTOMLEFT", 0, 0)
    rule:SetPoint("TOPRIGHT", band, "BOTTOMRIGHT", 0, 0)
    rule:SetHeight(1)
    local label = frame:CreateFontString(nil, "OVERLAY")
    Theme.ApplyMono(label, 10, accent)
    label:SetPoint("LEFT", band, "LEFT", 10, 0)
    label:SetText("stuwave://" .. title)
    S.bands[frame] = { band = band, rule = rule, label = label }
    return S.bands[frame]
end

-- The default text button skin must already be on `btn` so the panel sweep leaves it alone (it skips a button that has one): take
-- it when it is there, ask for it when it is not, then hold its pieces; ours are drawn over the held stock art.
local function ClaimDefaultKey(btn)
    local skins = FS.ButtonSkins
    local p = skins and skins.Parts and skins.Parts(btn)
    if not p and skins and skins.SkinTextButton then p = skins.SkinTextButton(btn) end
    if type(p) == "table" then
        HeldArt.Hold(p.face)
        HeldArt.Hold(p.ring)
        HeldArt.Hold(p.halo)
        if p.fs then Kit.HoldFrame(p.fs) end
    else
        HeldArt.HoldButton(btn)
        if type(btn.GetFontString) == "function" then Kit.HoldFrame(Try(btn.GetFontString, btn)) end
    end
end

-------------------------------------------------------------------------------
-- A text key: cut plate, mono label, an optional glyph before it
-------------------------------------------------------------------------------

local KEY = { CUT = 4, GLYPH = 16, GAP = 2 }

local function PaintKey(btn)
    local k = S.keys[btn]
    if not k then return end
    local on = Kit.IsEnabled(btn)
    local hover = on and k.state and (k.state.hover or k.state.pressed)
    local col = on and k.color or C.steel
    Kit.PaintPlate(k.plate, Kit.Mix(C.ink, col, on and (hover and 0.30 or 0.16) or 0), on and 1 or 0.6, col,
        on and (hover and 1 or 0.85) or 0.55, hover and 2 or 1)
    Kit.Recolor(k.label, hover and Kit.Mix(col, C.white, 0.25) or col, on and 1 or 0.6)
    if k.glyph then k.glyph.Paint(col, on and 1 or 0.6) end
    local text = Plain(Try(btn.GetText, btn))
    if type(text) == "string" and k.label:GetText() ~= text then k.label:SetText(text) end
end

local function SkinKey(btn, color, glyph)
    if type(btn) ~= "table" or S.keys[btn] or type(btn.CreateTexture) ~= "function" then return end
    ClaimDefaultKey(btn)
    local k = { color = color }
    S.keys[btn] = k
    local text = Plain(Try(btn.GetText, btn))
    k.plate = L.Card(btn, KEY.CUT)
    k.label = Kit.Label(btn, type(text) == "string" and text or "", 11, color, "OVERLAY")
    local bw, bh = Kit.SizePx(btn)
    bw, bh = bw or 138, bh or 26
    if glyph then
        local ppu = Kit.Ppu(btn)
        local textW = math.floor((Plain(Try(k.label.GetStringWidth, k.label)) or 40) * ppu / Kit.LAYOUT_SCALE + 0.5)
        local group = KEY.GLYPH + KEY.GAP + textW
        k.glyph = L.Glyph(btn, glyph, math.floor((bw - group) / 2), math.floor((bh - KEY.GLYPH) / 2), color, "OVERLAY", 5)
        Kit.Place(k.label, btn, (KEY.GLYPH + KEY.GAP) / 2, 0, nil, nil, "CENTER", "CENTER")
    else
        Kit.Place(k.label, btn, 0, 0, nil, nil, "CENTER", "CENTER")
    end
    k.state = Kit.Track(btn, PaintKey)
    Kit.HookFunc(btn, "SetText", function() PaintKey(btn) end)
    PaintKey(btn)
end

-------------------------------------------------------------------------------
-- A role key: the role button of the role poll and the PvP role check
-------------------------------------------------------------------------------

local ROLE = {
    tank = { bits = "shield", color = C.cyan, word = "TANK" },
    healer = { bits = "cross", color = C.green, word = "HEALER" },
    dps = { bits = "blade", color = RED, word = "DAMAGER" },
}
local ROLE_LAYOUT = { GLYPH = 32, GLYPH_TOP = 0.14, WORD_TOP = 0.66, LED_TOP = 0.80, LED_W = 24, CUT = 6 }

local function PaintRole(btn)
    local r = S.roles[btn]
    if not r then return end
    local on = Kit.IsEnabled(btn)
    local checked = false
    local box = btn.checkButton
    if type(box) == "table" and type(box.GetChecked) == "function" then checked = Plain(Try(box.GetChecked, box)) and true or false end
    local hover = on and r.state and (r.state.hover or r.state.pressed)
    local col = on and r.color or C.steel
    local lit = on and (hover or checked)
    Kit.PaintPlate(r.plate, checked and on and Kit.Mix(C.ink, col, 0.16) or C.ink, on and 1 or 0.6, lit and col or (on and C.line or C.steel),
        on and 1 or 0.55, (checked and on) and 2 or 1)
    r.glyph.Paint(col, on and 1 or 0.5)
    Kit.Recolor(r.label, col, on and 1 or 0.6)
    r.led:SetColorTexture(col[1], col[2], col[3], lit and 1 or 0.7)
    r.led:SetShown(on)
    r.hatch:SetShown(not on)
end

local function SkinRole(btn, which)
    if type(btn) ~= "table" or S.roles[btn] or type(btn.CreateTexture) ~= "function" then return end
    local spec = ROLE[which]
    HeldArt.HoldButton(btn)
    HeldArt.HoldNormal(btn)
    local bw, bh = Kit.SizePx(btn)
    bw, bh = bw or 84, bh or 84
    local r = { color = spec.color }
    S.roles[btn] = r
    r.plate = L.Card(btn, ROLE_LAYOUT.CUT)
    r.glyph = L.Glyph(btn, spec.bits, math.floor((bw - ROLE_LAYOUT.GLYPH) / 2), math.floor(bh * ROLE_LAYOUT.GLYPH_TOP), spec.color, "OVERLAY", 5, nil, 2)
    local word = _G[spec.word]
    r.label = Kit.Label(btn, type(word) == "string" and word:lower() or which, 11, spec.color, "OVERLAY")
    Kit.Place(r.label, btn, 0, math.floor(bh * ROLE_LAYOUT.WORD_TOP) - 7, nil, nil, "TOP", "TOP")
    r.led = Kit.Rect(btn, math.floor((bw - ROLE_LAYOUT.LED_W) / 2), math.floor(bh * ROLE_LAYOUT.LED_TOP), ROLE_LAYOUT.LED_W, 2, spec.color, 0.7, "OVERLAY", 5)
    r.hatch = btn:CreateTexture(nil, "OVERLAY", nil, 4)
    r.hatch:SetTexture(Theme.HATCH_TEXTURE, "REPEAT", "REPEAT")
    r.hatch:SetHorizTile(true)
    r.hatch:SetVertTile(true)
    r.hatch:SetVertexColor(1, 1, 1, 0.22)
    local u = Kit.U(btn, 2)
    r.hatch:SetPoint("TOPLEFT", btn, "TOPLEFT", u, -u)
    r.hatch:SetPoint("BOTTOMRIGHT", btn, "BOTTOMRIGHT", -u, u)
    r.state = Kit.Track(btn, PaintRole)
    local box = btn.checkButton
    if type(box) == "table" then
        Kit.HookFunc(box, "SetChecked", function() PaintRole(btn) end)
        Kit.HookScript(box, "OnClick", function() PaintRole(btn) end)
    end
    PaintRole(btn)
end

-------------------------------------------------------------------------------
-- The windows
-------------------------------------------------------------------------------

local PANEL = { fillColor = Theme.COLOR_BG }
local INVITE_BAND = 12 -- units

local function PanelSkin(accent, title, bandHeight) return { fillColor = PANEL.fillColor, accent = accent, title = title, bandHeight = bandHeight } end

-- Holds what Popups.lua drew on the outer ReadyCheckFrame (a panel over a frame that has no art of its own).
local function HoldOuter(outer)
    for _, region in ipairs(List(outer, "GetRegions")) do HeldArt.Hold(region) end
end

local function SkinReadyCheck()
    local outer, l = G.Named("ReadyCheckFrame"), G.Named("ReadyCheckListenerFrame")
    if not l or S.done.ready then return end
    S.done.ready = true
    local skin = PanelSkin(C.violet, "ready")
    PanelSkins.SkinPanelCached(l, skin)
    PanelSkins.HookShowOnce(l, "fsReadyShowHooked", function(self) PanelSkins.SkinPanelCached(self, skin) end)
    HeldArt.Hold(l.Bg)
    for _, key in ipairs({ "NineSlice", "TitleContainer", "PortraitContainer" }) do Kit.HoldFrame(l[key]) end
    G.Mono(_G.ReadyCheckFrameText, l, 11, C.text)
    if outer then
        HoldOuter(outer)
        Kit.HookScript(outer, "OnShow", function() HoldOuter(outer) end)
    end
    SkinKey(_G.ReadyCheckFrameYesButton, C.green, "check")
    SkinKey(_G.ReadyCheckFrameNoButton, C.pink)
    PanelSkins.SweepOnShow(l)
end

local function SkinRolePoll(win)
    if not win or S.done.roles then return end
    S.done.roles = true
    win.fsGroupPopupSkin = true
    Kit.HoldFrame(win.Border)
    HoldHeadings(win)
    Band(win, "roles", C.violet)
    SkinRole(_G.RolePollPopupRoleButtonTank, "tank")
    SkinRole(_G.RolePollPopupRoleButtonHealer, "healer")
    SkinRole(_G.RolePollPopupRoleButtonDPS, "dps")
    SkinKey(win.acceptButton, C.cyan, "check")
    PanelSkins.SweepOnShow(win)
end

local function SkinQueueCheck(win)
    if not win or S.done.queue then return end
    S.done.queue = true
    local skin = PanelSkin(C.violet, "queue")
    HoldHeadings(win) -- before the panel skin: its title label is a FontString of the frame too
    PanelSkins.SkinPanelCached(win, skin)
    PanelSkins.HookShowOnce(win, "fsQueueShowHooked", function(self) PanelSkins.SkinPanelCached(self, skin) end)
    Kit.HoldFrame(win.Border)
    SkinRole(win.TankIcon, "tank")
    SkinRole(win.HealerIcon, "healer")
    SkinRole(win.DPSIcon, "dps")
    SkinKey(_G.PVPRoleCheckPopupAcceptButton, C.cyan, "check")
    SkinKey(_G.PVPRoleCheckPopupDeclineButton, C.pink)
    if type(win.Description) == "table" then G.Mono(win.Description.Text, win, 11, C.text) end
    PanelSkins.SweepOnShow(win)
end

local function SkinInvite(win)
    if not win or S.done.invite then return end
    S.done.invite = true
    -- a slim band: the stock heading ("Your battleground is ready", by queue type) sits 15 units under the top edge and stays readable
    local skin = PanelSkin(C.pink, "invite", INVITE_BAND)
    PanelSkins.SkinPanelCached(win, skin)
    PanelSkins.HookShowOnce(win, "fsInviteShowHooked", function(self) PanelSkins.SkinPanelCached(self, skin) end)
    Kit.HoldFrame(win.Border)
    HeldArt.Hold(win.background)
    HeldArt.Hold(win.bottomArt)
    local info = win.instanceInfo
    if type(info) == "table" then
        HeldArt.Hold(info.underline)
        G.Mono(info.name, win, 16, C.amber)
        G.Mono(info.statusText, win, 11, C.muted)
    end
    G.Mono(win.label, win, 10, C.muted)
    G.Mono(win.roleDescription, win, 9, C.muted)
    G.Mono(win.roleLabel, win, 12, C.text)
    SkinKey(win.enterButton, C.cyan)
    SkinKey(win.leaveButton, C.pink)
    PanelSkins.SweepOnShow(win)
end

-- The raid manager (CompactRaidFrameManager, the pull-out on the left edge): the stock background held and our panel drawn on the frame
-- itself, so it follows the frame's size, which the stock code sets as its option rows change. The frame's ALPHA is never held:
-- PartyFrames.lua parks the manager outside a raid with SetAlpha(0) and gives it back with SetAlpha(1), and our chrome follows it.
-- The RAID label and the member count go mono; the stock check boxes, the mode dropdown and the Leave buttons are the shared control
-- skins, found by the panel sweep. The role filter buttons, the marker buttons and the row of icon buttons keep their stock art (their
-- state is carried by the atlas they are given, which a skin cannot read), and the mockup's slim tab with live role counts is left out.
local function SkinManager(manager)
    if not manager or S.done.manager then return end
    S.done.manager = true
    manager.fsGroupManagerSkin = true
    HeldArt.Hold(manager.Background)
    Theme.AddPanelChrome(manager, { fillColor = PANEL.fillColor, accent = C.violet })
    local d = manager.displayFrame
    if type(d) == "table" then
        G.Mono(d.label, manager, 11, C.text)
        G.Mono(d.memberCountLabel, manager, 11, C.muted)
    end
    PanelSkins.SweepOnShow(manager)
end

-------------------------------------------------------------------------------
-- Drive
-------------------------------------------------------------------------------

local function Build()
    Step("manager", SkinManager, G.Named("CompactRaidFrameManager"))
    Step("ready", SkinReadyCheck)
    Step("roles", SkinRolePoll, G.Named("RolePollPopup"))
    Step("queue", SkinQueueCheck, G.Named("PVPRoleCheckPopup"))
    Step("invite", SkinInvite, G.Named("PVPReadyDialog"))
end

PanelSkins.RegisterInspect("GroupPopups", {
    { name = "ReadyCheckListenerFrame", guard = "fsSkinCache" },
    { name = "RolePollPopup", guard = "fsGroupPopupSkin" },
    { name = "PVPRoleCheckPopup", guard = "fsSkinCache" },
    { name = "PVPReadyDialog", guard = "fsSkinCache" },
    { name = "CompactRaidFrameManager", guard = "fsGroupManagerSkin" },
})

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
