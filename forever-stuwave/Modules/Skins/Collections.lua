-- Forever STUwave: Collections
-- The collections journal (CollectionsJournal, Blizzard_Collections) past its shell, from the approved COLLECTIONS mockup
-- (mockups/collections-misc-2026-11-12.html, sections 1 to 4: mounts, pets, toys, heirlooms). The window shell, the five tabs, the
-- search boxes, the filter dropdowns, the text buttons, the scroll bars and the model buttons already wear the shared skins
-- (Panels.lua, FieldSkins, the controls sweep); this file adds the parts that were still stock:
--
--   * the journal wells: every inset (the mount and pet lists, the model display, the toy and heirloom shelves) has its stock frame
--     art held and a ring of ours over the same rect;
--   * the mount and pet lists: every row is an ink card (the stock row art held, the name in mono with its colour kept to the stock
--     collected / not collected state, an LED edge that is cyan while the mount or pet is out, pink when the mount cannot be used
--     here or the pet is dead, and a cyan edge on hover and for the chosen row), the icon in a ring box;
--   * the count chips and the collection progress bars (a flat cyan bar in an ink ring, the text in mono);
--   * the mount model display and info block, the summon spell keys, the pet card (stock art held, text in mono);
--   * the toy and heirloom slots: the stock slot frames held, a ring box over the slot, an LED along its bottom edge (cyan ready,
--     amber while the toy cools down, dim when not collected), the name colour mapped from the stock write; the heirloom entries and
--     headers are made as a page is laid out, so they are caught after every layout;
--   * the page keys of the toy and heirloom pagers (cut corner keys with a chevron).
--
-- Skin only, as in Commerce.lua: no SetScript, no SetAttribute, no reparent, no resize or re-anchor of a Blizzard frame, alpha holds
-- (FS.HeldArt) and post-hooks only, so every click, drag, favourite, summon and toy use flow stays stock. Rows are pooled by a
-- ScrollBox, so each is painted again after every update of its list. Every frame is feature-detected by name or key; a missing
-- one is skipped (the journal loads on demand, and the pet journal on this client may be the companion only one).
--
-- Left out on purpose, because the mockup shows a computed display and the rule for this pass is "keep the functionality the same as
-- vanilla": the garage bay floor, spotlight, turntable ring and scan line behind the mount model, the terrain chips, the ready /
-- cannot mount here lamp and the ignition summon button, the source coloured row edges, the paw print collection meter and the card
-- foil sweep of the pets, the rising signal bars of the heirloom upgrade level and the toy quick filter chips, the header switch that
-- replaces the five tabs. The model scenes, the dynamic flight flyout, the mount equipment slot, the battle pet loadout and abilities,
-- the appearances tab (the wardrobe) and the warband scenes keep their stock look.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char, G = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin, FS.GroupSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and G and G.Card and G.HoldInset and Char.Box and Char.PaintBox and PanelSkins.RequireExport(
    Theme.ApplyMono and Theme.AddPanelChrome,
    "Collections.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit, FS.CharacterSkin or FS.GroupSkin missing")) then return end

local Col = {}
FS.CollectionsSkin = Col

local C, Weak, Region, Named = G.C, G.Weak, G.Region, G.Named
local Try, Plain, List = Kit.Try, Kit.Plain, Char.List
local function Step(name, fn, ...) return G.Step("collections", name, fn, ...) end

local S = {
    rows = Weak(), wells = Weak(), rings = Weak(), slots = Weak(), bars = Weak(), pagers = Weak(), pins = Weak(), pages = Weak(),
    done = {},
}
Col.state = S

local function Shown(region)
    return type(region) == "table" and Try(region.IsShown, region) == true
end

-------------------------------------------------------------------------------
-- Text: mono, with the colour of the stock state kept
-------------------------------------------------------------------------------

local function ReadColor(fs)
    if type(fs) ~= "table" or type(fs.GetTextColor) ~= "function" then return nil end
    local r, g, b = Try(fs.GetTextColor, fs)
    r, g, b = Plain(r), Plain(g), Plain(b)
    if type(r) == "number" and type(g) == "number" and type(b) == "number" then return r, g, b end
    return nil
end

-- The stock colour of a name, mapped onto ours: the gold of a collected entry and anything bright reads as text, the grey and brown
-- of an uncollected one as muted, and a saturated colour (a red state, a quality) is data and is kept.
local function Pick(r, g, b)
    if type(r) ~= "number" or type(g) ~= "number" or type(b) ~= "number" then return C.text end
    if r >= 0.8 and g >= 0.6 and g <= 0.9 and b <= 0.3 then return C.text end
    if (r + g + b) / 3 >= 0.8 then return C.text end
    if math.max(r, g, b) - math.min(r, g, b) >= 0.35 then return { r, g, b, 1 } end
    return C.muted
end

local function Fixed(color) return function() return color end end
local Text, Muted, Cyan, Amber = Fixed(C.text), Fixed(C.muted), Fixed(C.cyan), Fixed(C.amber)
local function Keep(r, g, b)
    if type(r) ~= "number" or type(g) ~= "number" or type(b) ~= "number" then return C.text end
    return { r, g, b, 1 }
end

-- Restyles a stock label in mono and keeps it that way: the stock code resets the font (SetFontObject) and writes the colour
-- (SetTextColor) again on every update, so both are post-hooked and the label is put back, its colour mapped by `map` (Pick by
-- default). The seed colour is the stock colour at skin time, read by the caller before anything else restyled the label.
local function Pin(fs, host, px, map, r, g, b)
    if type(fs) ~= "table" or Kit.TypeOf(fs) ~= "FontString" or S.pins[fs] then return end
    S.pins[fs] = true
    map = map or Pick
    if r == nil then r, g, b = ReadColor(fs) end
    local busy = false
    pcall(Kit.RestyleLabel, fs, host, px, map(r, g, b))
    Kit.HookFunc(fs, "SetTextColor", function(_, cr, cg, cb)
        if busy then return end
        busy = true
        pcall(Kit.Recolor, fs, map(Plain(cr), Plain(cg), Plain(cb)))
        busy = false
    end)
    Kit.HookFunc(fs, "SetFontObject", function()
        if busy then return end
        busy = true
        pcall(Kit.RestyleLabel, fs, host, px, map(ReadColor(fs)))
        busy = false
    end)
end

-- Every label a frame has, in mono at `px`, the stock colour kept (a level on its plate, a count).
local function PinAll(frame, px, map)
    for _, region in ipairs(List(frame, "GetRegions")) do
        if Kit.TypeOf(region) == "FontString" then Pin(region, frame, px, map or Keep) end
    end
end

-------------------------------------------------------------------------------
-- Wells and rings
-------------------------------------------------------------------------------

-- An inset or panel of the journal: its stock frame art held (FIRST, the box would be held with the rest), then our ring over it.
local function Well(frame, fill, fa, edge, ea)
    if type(frame) ~= "table" or S.wells[frame] or type(frame.CreateTexture) ~= "function" then return nil end
    G.HoldInset(frame)
    local box = Char.Box(frame, "BORDER")
    S.wells[frame] = box
    Char.PaintBox(box, fill or C.ink, fa or 0.6, edge or C.dim, ea or 1, 1)
    return box
end

-- A ring box on the rect of `icon` (a texture of `host`), drawn over the icon's edge.
local function IconRing(host, icon)
    if type(host) ~= "table" or type(icon) ~= "table" or S.rings[icon] or type(host.CreateTexture) ~= "function" then return nil end
    local box = Char.Box(host, "OVERLAY", icon)
    Char.PaintBox(box, C.ink, 1, C.dim, 1, 1)
    S.rings[icon] = box
    return box
end

-- A strip `h` pixels high along the bottom edge of `host`, `inset` pixels in from its left, right and bottom: the LED of a slot.
local strips = {}
Kit.OnReseat(function() for _, rec in ipairs(strips) do rec.apply() end end)

local function Strip(host, h, inset)
    local t = host:CreateTexture(nil, "OVERLAY", nil, 7)
    local rec = { t = t }
    function rec.apply()
        local u = Kit.U(host, 1)
        t:ClearAllPoints()
        t:SetPoint("BOTTOMLEFT", host, "BOTTOMLEFT", inset * u, inset * u)
        t:SetPoint("BOTTOMRIGHT", host, "BOTTOMRIGHT", -inset * u, inset * u)
        t:SetHeight(h * u)
    end
    function rec.Paint(c, a) t:SetColorTexture(c[1], c[2], c[3], a or c[4] or 1) end
    strips[#strips + 1] = rec
    rec.apply()
    return rec
end

-- The count chip (Mounts: 11 / 24): the inset held, a band ring, the label muted and the count cyan.
local function SkinCount(chip)
    if type(chip) ~= "table" or S.wells[chip] then return end
    Well(chip, C.band, 1, C.dim, 1)
    Pin(chip.Label, chip, 11, Muted)
    Pin(chip.Count, chip, 11, Cyan)
end

-- A collection progress bar: the stock bar border and backdrop held, a flat cyan bar in an ink ring, the text in mono.
local function SkinBar(bar)
    if type(bar) ~= "table" or S.bars[bar] or type(bar.CreateTexture) ~= "function" then return end
    G.HoldRegions(bar)
    if type(bar.SetStatusBarTexture) == "function" and Theme.FLAT_TEXTURE then pcall(bar.SetStatusBarTexture, bar, Theme.FLAT_TEXTURE) end
    if type(bar.SetStatusBarColor) == "function" then pcall(bar.SetStatusBarColor, bar, C.cyan[1], C.cyan[2], C.cyan[3], 1) end
    local box = Char.Box(bar, "OVERLAY")
    Char.PaintBox(box, C.ink, 1, C.dim, 1, 1)
    S.bars[bar] = box
    Pin(bar.text, bar, 11, Text)
end

-------------------------------------------------------------------------------
-- Page keys (the toy box and the heirlooms)
-------------------------------------------------------------------------------

-- A cut corner key PAGER px across centred on the stock page button, a cyan chevron of cells centred in it. Idle ink with a violet
-- edge, hover lights the edge and glyph, disabled dims all. The stock art is held FIRST. dir is "<" or ">".
local PAGER = { SIZE = 26, CUT = 5, STEP = 2, ROWS = 9, THICK = 2 }

local function PaintPager(btn)
    local s = S.pagers[btn]
    if not s then return end
    local on = Kit.IsEnabled(btn)
    local hover = on and s.state and (s.state.hover or s.state.pressed)
    local edge = not on and C.dim or (hover and C.cyan or C.violet)
    Kit.PaintPlate(s.key, C.ink, 1, edge, on and 1 or 0.6, hover and 2 or 1)
    local g = hover and C.text or C.cyan
    for _, t in ipairs(s.glyph) do
        t:SetColorTexture(g[1], g[2], g[3], 1)
        t:SetAlpha(on and 1 or 0.35)
    end
end

local function PagerKey(btn, dir)
    if type(btn) ~= "table" or S.pagers[btn] or type(btn.CreateTexture) ~= "function" then return end
    HeldArt.HoldButton(btn)
    local bw, bh = Kit.SizePx(btn)
    bw, bh = bw or 32, bh or 32
    local P = PAGER
    local x, y = math.floor((bw - P.SIZE) / 2), math.floor((bh - P.SIZE) / 2)
    local s = { key = Kit.Plate(btn, P.CUT, P.SIZE, P.SIZE), glyph = {} }
    Kit.Place(s.key.fill, btn, x, y, P.SIZE, P.SIZE)
    Kit.Place(s.key.ring, btn, x, y, P.SIZE, P.SIZE)
    if s.key.ring2 then Kit.Place(s.key.ring2, btn, x + 1, y + 1, P.SIZE - 2, P.SIZE - 2) end
    local half = (P.ROWS - 1) / 2
    local gw, gh = half * P.STEP + P.THICK, P.ROWS * P.THICK
    local gx, gy = x + math.floor((P.SIZE - gw) / 2), y + math.floor((P.SIZE - gh) / 2)
    for row = 0, P.ROWS - 1 do
        local d = math.abs(row - half)
        local cx = dir == "<" and d * P.STEP or (half - d) * P.STEP
        s.glyph[#s.glyph + 1] = Kit.Rect(btn, gx + cx, gy + row * P.THICK, P.THICK, P.THICK, C.cyan, 1, "OVERLAY", 7)
    end
    S.pagers[btn] = s
    s.state = Kit.Track(btn, PaintPager)
    for _, script in ipairs({ "OnEnable", "OnDisable", "OnShow" }) do Kit.HookScript(btn, script, PaintPager) end
    for _, m in ipairs({ "Enable", "Disable", "SetEnabled" }) do Kit.HookFunc(btn, m, function() PaintPager(btn) end) end
    PaintPager(btn)
end

local function SkinPaging(paging)
    if type(paging) ~= "table" then return end
    PagerKey(paging.PrevPageButton, "<")
    PagerKey(paging.NextPageButton, ">")
    Pin(paging.PageText, paging, 12, Muted)
end

-------------------------------------------------------------------------------
-- List rows (mounts and pets)
-------------------------------------------------------------------------------

local function PaintRow(row)
    local rec = S.rows[row]
    if not rec then return end
    rec.selected = Shown(row.selectedTexture)
    G.PaintCard(row)
end

-- The mount LED: cyan while it is the summoned mount, pink when the stock code tints the row red (cannot be used here).
local function MountLed(row)
    return function()
        if Shown(Region(row.DragButton, "ActiveTexture")) then return C.cyan end
        local bg = row.background
        if type(bg) == "table" and type(bg.GetVertexColor) == "function" then
            local r, g, b = Try(bg.GetVertexColor, bg)
            r, g, b = Plain(r), Plain(g), Plain(b)
            if type(r) == "number" and r > 0.9 and g < 0.3 and b < 0.3 then return C.pink end
        end
        return C.dim
    end
end

-- The pet LED: cyan while it is the summoned pet, pink while it is dead.
local function PetLed(row)
    return function()
        if Shown(Region(row.dragButton, "ActiveTexture")) then return C.cyan end
        if Shown(row.isDead) then return C.pink end
        return C.dim
    end
end

local ROW_ART = { "^background$", "^selectedTexture$", "^newGlow$" }

-- `spec.led(row)` gives the LED colour function, `spec.button` the key of the row's drag button (its labels are the level).
local function SkinListRow(row, spec)
    if type(row) ~= "table" or Kit.TypeOf(row) ~= "Button" then return end
    if S.rows[row] then PaintRow(row) return end
    local nr, ng, nb = ReadColor(row.name)
    local rec = G.Card(row, { accent = C.cyan, hold = ROW_ART, px = 11, led = spec.led(row) })
    if not rec then return end
    S.rows[row] = rec
    for _, getter in ipairs({ "GetNormalTexture", "GetHighlightTexture", "GetPushedTexture", "GetDisabledTexture" }) do
        HeldArt.Hold(Try(row[getter], row))
    end
    IconRing(row, row.icon)
    Pin(row.name, row, 12, Pick, nr, ng, nb)
    Pin(row.subName, row, 10, Muted)
    Pin(row.SteadyFlightLabel, row, 10, Muted)
    local drag = Region(row, spec.button)
    if drag then PinAll(drag, 10, Keep) end
    local function again() PaintRow(row) end
    for _, region in ipairs({ row.selectedTexture or false, row.isDead or false, Region(drag, "ActiveTexture") or false }) do
        if region then
            for _, m in ipairs({ "Show", "Hide", "SetShown" }) do Kit.HookFunc(region, m, again) end
        end
    end
    Kit.HookFunc(row.background, "SetVertexColor", again)
    PaintRow(row)
end

local MOUNT_ROW = { led = MountLed, button = "DragButton" }
local PET_ROW = { led = PetLed, button = "dragButton" }

-------------------------------------------------------------------------------
-- The key of a spell frame (the summon random favourite mount / pet keys)
-------------------------------------------------------------------------------

-- A square key whose own icon is the picture: the stock frame art held (the icon and the unavailable cover kept), a ring box over the
-- rect. The ring is drawn over the icon's edge, which G.Square's is not.
local function IconKey(btn, keep)
    if type(btn) ~= "table" or type(btn.CreateTexture) ~= "function" or G.squares[btn] then return end
    HeldArt.HoldButton(btn, keep)
    local s = { box = Char.Box(btn, "OVERLAY"), icon = btn.Icon, accent = C.violet }
    G.squares[btn] = s
    s.state = Kit.Track(btn, G.PaintSquare)
    G.PaintSquare(btn)
end

local function SkinSpellFrame(frame)
    if type(frame) ~= "table" then return end
    local btn = Region(frame, "Button")
    if btn then IconKey(btn, { [btn.Icon or false] = true, [btn.BlackCover or false] = true }) end
    Pin(frame.Label, frame, 11, Text)
end

-------------------------------------------------------------------------------
-- Mounts
-------------------------------------------------------------------------------

local function SkinMountDisplay(display)
    if type(display) ~= "table" or S.done[display] then return end
    S.done[display] = true
    G.HoldKeys(display, { "YesMountsTex", "NoMountsTex", "ShadowOverlay" })
    Pin(display.NoMounts, display, 14, Muted)
    local info = Region(display, "InfoButton")
    if not info then return end
    G.HoldKeys(info, { "NewGlow" })
    IconRing(info, info.Icon)
    Pin(info.Name, info, 15, Text)
    Pin(info.Source, info, 11, Text)
    Pin(info.Lore, info, 11, Muted)
    Pin(info.New, info, 10, Cyan)
end

-- The journal page frame itself: the flag the inspector reads, and a rebuild when it is shown (idempotent, so a late row is caught).
local function Mark(frame)
    if S.pages[frame] then return end
    S.pages[frame] = true
    frame.fsCollectionsSkin = true
    Kit.HookScript(frame, "OnShow", function() Kit.Later(function() PanelSkins.DeferCombat(Col.Build) end) end)
end

local function SkinMounts()
    local m = Named("MountJournal")
    if not m then return end
    Well(Region(m, "LeftInset"), C.ink, 0.6, C.dim, 1)
    Well(Region(m, "BottomLeftInset"), C.ink, 0.6, C.dim, 1)
    Well(Region(m, "RightInset"), C.ink, 0.9, C.dim, 1)
    SkinCount(Region(m, "MountCount"))
    SkinMountDisplay(Region(m, "MountDisplay"))
    SkinSpellFrame(Region(m, "SummonRandomFavoriteSpellFrame"))
    G.Rows(Region(m, "ScrollBox"), function(row) SkinListRow(row, MOUNT_ROW) end)
    Mark(m)
end

-------------------------------------------------------------------------------
-- Pets
-------------------------------------------------------------------------------

local function SkinPetCard(card)
    if type(card) ~= "table" or S.done[card] then return end
    S.done[card] = true
    G.HoldNamed(card, { "^AbilitiesBG", "^shadows$" })
    local info = Region(card, "PetInfo")
    if info then
        IconRing(info, info.icon)
        Pin(info.name, info, 14, Pick)
        Pin(info.subName, info, 11, Muted)
        Pin(info.new, info, 10, Cyan)
        PinAll(info, 10, Keep)
    end
    Pin(Region(card, "TypeInfo") and card.TypeInfo.type, card, 11, Text)
    for _, spec in ipairs({ { "HealthFrame", "health" }, { "PowerFrame", "power" }, { "SpeedFrame", "speed" }, { "QualityFrame", "quality" } }) do
        local frame = Region(card, spec[1])
        if frame then Pin(frame[spec[2]], frame, 11, Text) end
    end
    Pin(card.CannotBattleText, card, 12, Keep)
end

local function SkinPets()
    local p = Named("PetJournal")
    if not p then return end
    Well(Region(p, "LeftInset"), C.ink, 0.6, C.dim, 1)
    Well(Region(p, "RightInset"), C.ink, 0.9, C.dim, 1)
    Well(Region(p, "PetCardInset"), C.ink, 0.9, C.dim, 1)
    SkinCount(Region(p, "PetCount"))
    SkinPetCard(Region(p, "PetCard"))
    SkinSpellFrame(Region(p, "SummonRandomPetSpellFrame"))
    SkinSpellFrame(Region(p, "HealPetSpellFrame"))
    G.Rows(Region(p, "ScrollBox"), function(row) SkinListRow(row, PET_ROW) end)
    Mark(p)
end

-------------------------------------------------------------------------------
-- Toys and heirlooms: the slots
-------------------------------------------------------------------------------

local SLOT_ART = { "slotFrameCollected", "slotFrameUncollected", "slotFrameUncollectedInnerGlow", "newGlow", "HighlightTexture" }

-- A slot reads its state from the stock art: the collected frame shown means collected, the cooldown frame shown means cooling.
local function PaintSlot(btn)
    local s = S.slots[btn]
    if not s then return end
    local collected = Shown(btn.slotFrameCollected)
    local hover = s.state and (s.state.hover or s.state.pressed)
    Char.PaintBox(s.box, collected and C.row or C.ink, 1, hover and C.cyan or C.dim, collected and 1 or 0.55, hover and 2 or 1)
    if not collected then s.led.Paint(C.dim, 0.35)
    elseif Shown(btn.cooldown) then s.led.Paint(C.amber, 1)
    else s.led.Paint(C.cyan, 1) end
end

local function SkinSlot(btn)
    if type(btn) ~= "table" or S.slots[btn] or type(btn.CreateTexture) ~= "function" then return end
    local kind = Kit.TypeOf(btn)
    if kind ~= "CheckButton" and kind ~= "Button" then return end
    G.HoldKeys(btn, SLOT_ART)
    HeldArt.Hold(Try(btn.GetHighlightTexture, btn))
    local s = { box = Char.Box(btn, "OVERLAY"), led = Strip(btn, 2, 3) }
    S.slots[btn] = s
    Pin(btn.special, btn, 10, Amber)
    Pin(btn.name, btn, 12, Pick)
    PinAll(btn, 10, Keep)
    s.state = Kit.Track(btn, PaintSlot)
    local function again() PaintSlot(btn) end
    for _, region in ipairs({ btn.slotFrameCollected or false, btn.cooldown or false }) do
        if region then
            for _, m in ipairs({ "Show", "Hide", "SetShown" }) do Kit.HookFunc(region, m, again) end
        end
    end
    Kit.HookScript(btn.cooldown, "OnCooldownDone", again)
    PaintSlot(btn)
end

local function SkinShelf(page)
    if type(page) ~= "table" then return end
    SkinBar(page.progressBar)
    Well(Region(page, "iconsFrame"), C.ink, 0.6, C.dim, 1)
    SkinPaging(Region(page, "PagingFrame"))
end

-------------------------------------------------------------------------------
-- Toys
-------------------------------------------------------------------------------

local TOY_SLOTS = 18

local function SkinToys()
    local tb = Named("ToyBox")
    if not tb then return end
    SkinShelf(tb)
    local icons = Region(tb, "iconsFrame")
    if icons then
        for i = 1, TOY_SLOTS do SkinSlot(icons["spellButton" .. i]) end
    end
    Mark(tb)
end

-------------------------------------------------------------------------------
-- Heirlooms
-------------------------------------------------------------------------------

local function SkinHeader(header)
    if type(header) ~= "table" or S.done[header] then return end
    S.done[header] = true
    G.HoldRegions(header)
    Pin(header.text, header, 13, Cyan)
    G.Rule(header, C.dim, 1, -2, 24)
end

-- The entries and headers are made by LayoutCurrentPage as the pages are laid out, so they are skinned from the arrays it fills.
local function SweepHeirlooms()
    local hj = Named("HeirloomsJournal")
    if not hj then return end
    for _, slot in ipairs(type(hj.heirloomEntryFrames) == "table" and hj.heirloomEntryFrames or {}) do Step("heirloom slot", SkinSlot, slot) end
    for _, header in ipairs(type(hj.heirloomHeaderFrames) == "table" and hj.heirloomHeaderFrames or {}) do Step("heirloom header", SkinHeader, header) end
end

local function SkinHeirlooms()
    local hj = Named("HeirloomsJournal")
    if not hj then return end
    SkinShelf(hj)
    SweepHeirlooms()
    if not S.done.heirloomHooks then
        S.done.heirloomHooks = true
        for _, method in ipairs({ "LayoutCurrentPage", "RefreshView" }) do Kit.HookFunc(hj, method, SweepHeirlooms) end
    end
    Mark(hj)
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local function Build()
    Step("mounts", SkinMounts)
    Step("pets", SkinPets)
    Step("toys", SkinToys)
    Step("heirlooms", SkinHeirlooms)
end
Col.Build = Build

-- The label, well and ring helpers, for Charters.lua (loaded after this file).
Col.Pin, Col.Pick, Col.Well, Col.IconRing = Pin, Pick, Well, IconRing
Col.Maps = { Text = Text, Muted = Muted, Cyan = Cyan, Amber = Amber, Keep = Keep }

PanelSkins.RegisterInspect("Collections", {
    { name = "MountJournal", guard = "fsCollectionsSkin" },
    { name = "PetJournal", guard = "fsCollectionsSkin" },
    { name = "ToyBox", guard = "fsCollectionsSkin" },
    { name = "HeirloomsJournal", guard = "fsCollectionsSkin" },
})

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
