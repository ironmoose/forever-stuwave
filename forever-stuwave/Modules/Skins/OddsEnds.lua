-- Forever STUwave: odds and ends
-- The queue ticket list, the clock page and the stopwatch, the battlefield map and the hunter pet stable, restyled in place from
-- the ODDS AND ENDS mockup (mockups/odds-ends-2026-11-12.html). The window chrome of the clock page, the text buttons, the scroll
-- bars, the check boxes, the edit boxes and the drop downs already wear the shared panel and control skins (Panels.lua and the
-- controls sweep); this file adds the parts that were still stock. One section per window below.
--
-- Skin only, as in Commerce.lua: no SetScript, no SetAttribute, no reparent, no resize or re-anchor of a Blizzard frame, post-hooks
-- and alpha holds (FS.HeldArt) only, so every click, drag, queue, alarm and stable flow stays stock. Every frame is feature
-- detected by name or key and a missing one is skipped; the queue entries are pooled, so each is skinned the moment the stock code
-- sets it up. The close keys of the stopwatch and the map bezel go through FS.ButtonSkins like every panel close key.
--
-- Left out on purpose, because the mockup shows a computed display and the rule for this pass is "keep the functionality the same
-- as vanilla": the ticket stubs with their wait gauge and the average wait tick, the role pips and the ready pulse of the queue
-- list; the clock dial with its alarm wedge and the 60 tick strip of the stopwatch; the carrier ring, the off view arrow, the
-- cursor coordinates and the opacity bar of the battlefield map; the loyalty segments, the happiness LEDs, the diet chips and the
-- family silhouettes of the pet stable. The queue eye is not touched here: Modules/ActionBars/MicroBars.lua already holds the stock
-- flipbook and seats its own eye on a key. The talking head is skipped: its art is faded by Blizzard's own alpha animations, which a
-- hold cannot pin, and the mockup asks to wait until it is seen firing on this client.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char, G, Commerce = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin,
    FS.GroupSkin, FS.CommerceSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and G and Commerce and Commerce.Dialog and Char.Box and Char.PaintBox
    and Char.PinColor and G.Rule and PanelSkins.RequireExport(Theme.SkinPanel and Theme.ApplyMono and Theme.StyleMoney,
    "OddsEnds.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit, FS.CharacterSkin, FS.GroupSkin or FS.CommerceSkin missing")) then return end

local Odd = {}
FS.OddsEndsSkin = Odd

local C, Weak, Region, Named, Mono, HoldRegions = G.C, G.Weak, G.Region, G.Named, G.Mono, G.HoldRegions
local Try, List = Kit.Try, Char.List
local function Step(name, fn, ...) return G.Step("odds", name, fn, ...) end

local S = { panels = Weak(), entries = Weak(), keys = Weak(), tabs = Weak(), bezels = Weak(), done = {} }
Odd.state = S

-- A stock label in mono with its colour pinned against the stock code.
local function Pin(fs, host, px, color)
    if type(fs) ~= "table" or Kit.TypeOf(fs) ~= "FontString" then return end
    Mono(fs, host, px, color)
    Char.PinColor(fs, color)
end

-------------------------------------------------------------------------------
-- Shared: a ring key for a button whose own picture is its normal texture
-------------------------------------------------------------------------------

local function PaintKey(btn)
    local k = S.keys[btn]
    if not k then return end
    local on = Kit.IsEnabled(btn)
    local hover = on and k.state and (k.state.hover or k.state.pressed)
    local sel = k.selected and k.selected() or false
    local edge = sel and C.cyan or (not on and C.dim) or (hover and C.cyan or k.accent)
    Char.PaintBox(k.box, sel and C.band or C.ink, 1, edge, (on or sel) and 1 or 0.6, (sel or hover) and 2 or 1)
end

-- Draws a ring box (ink face behind the picture, an edge over it) on `btn` and holds the stock hover, pressed and checked washes,
-- which the ring replaces. The normal texture is the button's picture for the stopwatch keys, so it is held only when
-- opts.holdNormal says it is slot art. opts.selected is a function that says it is the chosen one (a cyan edge and band).
local function RingKey(btn, opts)
    if type(btn) ~= "table" or S.keys[btn] or type(btn.CreateTexture) ~= "function" then return nil end
    opts = opts or {}
    if opts.holdNormal then HeldArt.HoldNormal(btn) end
    for _, getter in ipairs({ "GetHighlightTexture", "GetPushedTexture", "GetCheckedTexture", "GetDisabledCheckedTexture" }) do
        if type(btn[getter]) == "function" then HeldArt.Hold(Try(btn[getter], btn)) end
    end
    local k = { box = Char.Box(btn, "OVERLAY"), accent = opts.accent or C.violet, selected = opts.selected }
    S.keys[btn] = k
    k.state = Kit.Track(btn, PaintKey)
    Kit.HookFunc(btn, "SetChecked", function() PaintKey(btn) end)
    PaintKey(btn)
    return k
end
Odd.RingKey = RingKey

-------------------------------------------------------------------------------
-- The queue ticket list (QueueStatusFrame and its pooled QueueStatusEntryTemplate frames)
-------------------------------------------------------------------------------

local ENTRY_TEXT = { { "Title", 12, "text" }, { "Status", 11, "amber" }, { "SubTitle", 11, "muted" }, { "TimeInQueue", 11, "text" },
    { "AverageWait", 11, "muted" }, { "ExtraText", 10, "muted" } }
local ROLE_COUNTS = { "TanksFound", "HealersFound", "DamagersFound" }

-- The rule between two tickets follows the stock separator (the stock code hides it on the first entry).
local function PaintEntry(entry)
    local rec = S.entries[entry]
    if not rec then return end
    local sep = entry.EntrySeparator
    rec.rule:SetShown(type(sep) ~= "table" or Try(sep.IsShown, sep) ~= false)
end

local function SkinEntry(entry)
    if type(entry) ~= "table" or type(entry.CreateTexture) ~= "function" then return end
    if not S.entries[entry] then
        local rec = {}
        S.entries[entry] = rec
        HeldArt.Hold(entry.EntrySeparator)
        rec.rule = G.Rule(entry, C.dim, 1, 0, 8)
        for _, spec in ipairs(ENTRY_TEXT) do Pin(entry[spec[1]], entry, spec[2], C[spec[3]]) end
        for _, key in ipairs(ROLE_COUNTS) do
            local role = entry[key]
            if type(role) == "table" then Pin(role.Count, role, 11, C.text) end
        end
        if type(entry.AssignedSpec) == "table" then HeldArt.Hold(entry.AssignedSpec.Border) end
    end
    PaintEntry(entry)
end

local function SweepQueue()
    local frame = Named("QueueStatusFrame")
    local pool = frame and frame.statusEntriesPool
    if type(pool) ~= "table" or type(pool.EnumerateActive) ~= "function" then return end
    for entry in pool:EnumerateActive() do SkinEntry(entry) end
end

local function SkinQueue()
    local frame = Named("QueueStatusFrame")
    if not frame or S.panels[frame] then return end
    S.panels[frame] = true
    frame.fsOddsQueueSkin = true
    Kit.HoldFrame(frame.NineSlice)
    Commerce.Dialog(frame, C.cyan)
    Kit.HookScript(frame, "OnShow", function() Kit.Later(function() Step("queue.entries", SweepQueue) end) end)
    for _, name in ipairs({ "QueueStatusEntry_SetMinimalDisplay", "QueueStatusEntry_SetFullDisplay" }) do
        Kit.HookFunc(_G, name, function(entry) Step("queue.entry", SkinEntry, entry) end)
    end
    Kit.HookFunc(_G, "QueueStatusFrame_SortAndAnchorEntries", function() Step("queue.entries", SweepQueue) end)
    SweepQueue()
end

-------------------------------------------------------------------------------
-- The clock page (TimeManagerFrame) and the stopwatch (StopwatchFrame)
-------------------------------------------------------------------------------

-- The chrome of the page, the alarm drop downs, the edit box and the check boxes come from Panels.lua and the controls sweep; the
-- ticker, the labels and the stopwatch toggle are what is left.
local function SkinClock()
    local win = Named("TimeManagerFrame")
    if not win or S.done.clock then return end
    S.done.clock = true
    win.fsOddsClockSkin = true
    Pin(Named("TimeManagerFrameTicker"), win, 26, C.cyan)
    for _, name in ipairs({ "TimeManagerStopwatchFrameText", "TimeManagerAlarmTimeLabel", "TimeManagerAlarmMessageLabel" }) do
        Pin(Named(name), win, 11, C.muted)
    end
    local check = Named("TimeManagerStopwatchCheck")
    if check then RingKey(check, { selected = function() return Try(check.GetChecked, check) == true end }) end
end

local function SkinStopwatch()
    local sw = Named("StopwatchFrame")
    if not sw or S.done.stopwatch then return end
    S.done.stopwatch = true
    sw.fsOddsStopwatchSkin = true
    S.panels[sw] = true
    Commerce.Dialog(sw, C.cyan)
    local tab = Named("StopwatchTabFrame")
    if tab then
        HoldRegions(tab)
        Char.PaintBox(Char.Box(tab, "BORDER"), C.band, 1, C.dim, 1, 1)
        Pin(Named("StopwatchTitle"), tab, 10, C.cyan)
    end
    local ticker = Named("StopwatchTicker")
    if ticker then
        for _, region in ipairs(List(ticker, "GetRegions")) do Pin(region, ticker, 16, C.muted) end
    end
    for _, name in ipairs({ "StopwatchTickerHour", "StopwatchTickerMinute", "StopwatchTickerSecond" }) do
        Pin(Named(name), ticker or sw, 16, C.text)
    end
    RingKey(Named("StopwatchResetButton"), { accent = C.violet })
    RingKey(Named("StopwatchPlayPauseButton"), { accent = C.violet })
    local close, skins = Named("StopwatchCloseButton"), FS.ButtonSkins
    if close and skins and skins.SkinCloseButton and not (skins.Parts and skins.Parts(close)) then
        skins.SkinCloseButton(close, { anchor = tab or sw })
    end
end

-------------------------------------------------------------------------------
-- The battlefield map (BattlefieldMapTab and BattlefieldMapFrame)
-------------------------------------------------------------------------------

local BEZEL_ART = { "TopLeft", "TopRight", "BottomLeft", "BottomRight", "Top", "Bottom", "Left", "Right" }
local RETICLE = { PAD = 2, LEN = 12 }

local function PaintTab(tab)
    local t = S.tabs[tab]
    if type(t) ~= "table" then return end
    local hover = t.state and (t.state.hover or t.state.pressed)
    Char.PaintBox(t.box, C.band, 1, hover and C.cyan or C.dim, 1, 1)
end

local function SkinMapTab(tab)
    if not tab or S.tabs[tab] then return end
    HeldArt.HoldButton(tab)
    local t = { box = Char.Box(tab, "BORDER") }
    S.tabs[tab] = t
    t.state = Kit.Track(tab, PaintTab)
    local label = Region(tab, "Text") or (type(tab.GetFontString) == "function" and Try(tab.GetFontString, tab)) or nil
    Pin(label, tab, 10, C.text)
    PaintTab(tab)
end

-- The bezel art is held and a ring with lock on corners drawn over the same rect; the map canvas inside is never touched. The
-- close key sits in the top right corner, where the fourth bracket would be.
local function SkinMapBezel(map)
    local border = Region(map, "BorderFrame")
    if not border or S.bezels[border] then return end
    G.HoldKeys(border, BEZEL_ART)
    local rec = { box = Char.Box(border, "OVERLAY"), reticle = Kit.Reticle(border, "OVERLAY", 7) }
    S.bezels[border] = rec
    Char.PaintBox(rec.box, C.ink, 0, C.violet, 1, 1)
    Kit.PaintReticle(rec.reticle, C.cyan, 0.9)
    local function seat()
        local w, h = Kit.SizePx(border)
        if w then Kit.SeatReticle(rec.reticle, 0, 0, w, h, RETICLE.PAD, RETICLE.LEN) end
    end
    rec.seat = seat
    Kit.HookScript(border, "OnSizeChanged", seat)
    Kit.HookScript(map, "OnShow", function() Kit.Later(seat) end)
    Kit.OnReseat(seat)
    seat()
    local close, skins = border.CloseButton, FS.ButtonSkins
    if type(close) == "table" and skins and skins.SkinCloseButton and not (skins.Parts and skins.Parts(close)) then
        skins.SkinCloseButton(close, { anchor = map })
        -- the close key takes the top right corner, so that corner's bracket is left off
        rec.reticle.trH:Hide()
        rec.reticle.trV:Hide()
    end
end

local function SkinMap()
    SkinMapTab(Named("BattlefieldMapTab"))
    local map = Named("BattlefieldMapFrame")
    if not map or S.done.map then return end
    S.done.map = true
    map.fsOddsMapSkin = true
    SkinMapBezel(map)
end

-------------------------------------------------------------------------------
-- The hunter pet stable (PetStableFrame; names from the 16001 globals dump, the frame has no reference source)
-------------------------------------------------------------------------------

local STABLE_ART = { "PetStableFrameBg", "PetStableFrameTop", "PetStableFrameBottom", "PetStableFrameLeft", "PetStableFrameRight",
    "PetStableFrameTopLeft", "PetStableFrameTopRight", "PetStableFrameBottomLeft", "PetStableFrameBottomRight" }
local STABLE_TEXT = { { "PetStableFrameTitleText", 12, "text" }, { "PetStableFrameText", 11, "muted" }, { "PetStableLevelText", 12, "text" },
    { "PetStableLoyaltyText", 12, "amber" }, { "PetStableSlotText", 11, "muted" }, { "PetStableCostLabel", 11, "muted" } }
local MAX_STABLE_SLOTS = 30

local function SkinStableSlots()
    local function slot(btn)
        if btn then RingKey(btn, { holdNormal = true, selected = function() return Try(btn.GetChecked, btn) == true end }) end
    end
    slot(Named("PetStableCurrentPet"))
    for i = 1, MAX_STABLE_SLOTS do
        local btn = Named("PetStableStabledPet" .. i)
        if not btn then break end
        slot(btn)
    end
end

local function SkinStable()
    local win = Named("PetStableFrame")
    if not win then return end
    if not S.panels[win] then
        S.panels[win] = true
        win.fsOddsStableSkin = true
        Theme.SkinPanel(win, { title = "stable", fillColor = Theme.COLOR_BG, accent = C.violet })
        for _, name in ipairs(STABLE_ART) do HeldArt.Hold(Named(name)) end
        for _, spec in ipairs(STABLE_TEXT) do Pin(Named(spec[1]), win, spec[2], C[spec[3]]) end
        Theme.StyleMoney(Named("PetStableMoneyFrame"))
        Theme.StyleMoney(Named("PetStableCostMoneyFrame"))
        if PanelSkins.SweepOnShow then PanelSkins.SweepOnShow(win) end
    end
    SkinStableSlots()
end

-------------------------------------------------------------------------------
-- Drive
-------------------------------------------------------------------------------

local function Build()
    Step("queue", SkinQueue)
    Step("clock", SkinClock)
    Step("stopwatch", SkinStopwatch)
    Step("map", SkinMap)
    Step("stable", SkinStable)
end
Odd.Build = Build

PanelSkins.RegisterInspect("OddsEnds", { { name = "QueueStatusFrame", guard = "fsOddsQueueSkin" },
    { name = "TimeManagerFrame", guard = "fsOddsClockSkin" }, { name = "StopwatchFrame", guard = "fsOddsStopwatchSkin" },
    { name = "BattlefieldMapFrame", guard = "fsOddsMapSkin" }, { name = "PetStableFrame", guard = "fsOddsStableSkin" } })

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
