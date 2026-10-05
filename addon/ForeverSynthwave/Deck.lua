-- Forever Synthwave: Control Deck
--
-- One raised panel that sits on top of the full-width XP bar and holds two
-- groups: the micro menu keys (left) and the seven bag slots (right). It is a
-- plain RECTANGLE cut at TOP-LEFT and BOTTOM-RIGHT only (the standing rule
-- for every panel), built like PetFrame.lua's panel: a two-corner cut fill tinted
-- Theme.COLOR_HUD_SCRIM and the two-corner cut 1 texel outline, here tinted
-- COLOR_POWER at alpha 0.8 so the edge is the data bar's (flat, no glow). This
-- file owns only the CHASSIS (fill, border, the `//` divider and the two empty
-- slots). MicroBars.lua builds the keys into FS.Deck.microSlot and BagBar.lua
-- builds the bag buttons into FS.Deck.bagSlot, reading both off the table at call
-- time, the same split PetFrame.lua uses for its castSlot/barSlot/statusSlot.
--
-- Contract, exported on FS.Deck (design px, multiplied by FS.Layout.Scale()):
--   frame      the chassis, 2 * PAD + microSlot + DIVIDER_W + bagSlot wide, 38 high
--   microSlot  as wide as the SHOWN keys need, 26 high. MicroBars.lua works the
--              width out (RowWidth of the shown count: nested leaning keys of
--              KEY_W x KEY_H at pitch KEY_W * (1 - LEAN_FRAC) + KEY_GAP = 25.44)
--              and calls FS.Deck.SetMicroWidth(w) from its reseat path, so the
--              keys fill the slot with no empty run. MICRO_W_MAX (314, the 12 key
--              row rounded up) is the ceiling; more keys than that shrink inside it.
--   bagSlot    206 x 26   (7 slots of BAG_SIZE with BAG_GAP between)
-- plus the constants KEY_*, BAG_*, PAD, DIVIDER_W, MICRO_W_MAX and
-- Deck.GetMicroWidth().
--
-- Everything is seated from the RIGHT edge (bag slot, divider, micro slot), so a
-- width change only moves the left edge: the deck grows and shrinks leftward and
-- the right edge, the bag slot and the divider never move.
--
-- Placement. The chassis is NOT a FS.Layout entry seated at UIParent CENTER:
-- its vertical position is "resting on the XP bar's top edge", and the XP bar's
-- height changes with /fsxp, so a fixed y would either float above it or sink
-- into it. It is anchored BOTTOMRIGHT to the XP bar's TOPRIGHT instead, which
-- also makes it ride the bar when the variant changes height. Only the right
-- margin is design-scaled. The height and that margin are read from
-- FS.Layout.deck (Layout.lua loads first), with the numbers below as fallbacks.
-- FS.Layout.deck.w is the MAX width (the micro slot at MICRO_W_MAX); the live
-- width is always the sum of the parts, and microbars-harness.py checks the two
-- agree.
--
-- Load order: after XPBar.lua (the anchor target) and before MicroBars.lua and
-- BagBar.lua (the consumers). The XP bar frame is built at PLAYER_LOGIN, so the
-- anchor is seated then, not at file scope.

local _, FS = ...

FS.Deck = FS.Deck or {}
local Deck = FS.Deck

-------------------------------------------------------------------------------
-- Geometry (design px, 2560x1440 canvas)
-------------------------------------------------------------------------------

Deck.KEY_W = 34
Deck.KEY_H = 26
Deck.KEY_GAP = 3      -- the mockup's XP CELL_GAP, measured between the leaning edges
Deck.LEAN_FRAC = 0.34 -- cell_slant.tga's lean as a fraction of the width (generate_cell_slant.py SLANT)
Deck.BAG_SIZE = 26
Deck.BAG_GAP = 4

local MICRO_COUNT = 12
local BAG_COUNT = 7
-- The micro keys NEST: each one overlaps its neighbour's box by the lean, so the
-- pitch is the key width minus the lean, plus the gap (control-deck mockup:
-- PITCH = (KW - LEAN) + 3). MicroBars.lua lays the keys out with the same
-- formula (its Pitch/RowWidth) from the same KEY_W, KEY_GAP and LEAN_FRAC.
-- 34 + 11 * 25.44 = 313.84, rounded UP to a whole design px for the MAX slot.
local MICRO_PITCH = Deck.KEY_W * (1 - Deck.LEAN_FRAC) + Deck.KEY_GAP
local MICRO_W_MAX = math.ceil(Deck.KEY_W + (MICRO_COUNT - 1) * MICRO_PITCH - 1e-9) -- 314
local BAG_W = BAG_COUNT * Deck.BAG_SIZE + (BAG_COUNT - 1) * Deck.BAG_GAP           -- 206
local SLOT_H = 26

local PAD = 12            -- chassis edge to slot, both sides
local DIVIDER_W = 28      -- between the two slots
local DECK_CFG = FS.Layout.deck or {}
local DECK_H = DECK_CFG.h or 38

Deck.MICRO_W_MAX = MICRO_W_MAX
Deck.BAG_W = BAG_W
Deck.PAD = PAD
Deck.DIVIDER_W = DIVIDER_W

-- The micro slot's CURRENT width (design px). Starts at the max so a consumer
-- that reads the slot before MicroBars.lua has counted its keys gets a sane size;
-- MicroBars.lua narrows it through Deck.SetMicroWidth.
local microW = MICRO_W_MAX

-- Offsets from the chassis' RIGHT edge. None depends on microW, so a width change
-- moves only the left edge.
local BAG_RIGHT = PAD
local MICRO_RIGHT = PAD + BAG_W + DIVIDER_W
local DIVIDER_RIGHT = PAD + BAG_W + DIVIDER_W / 2

local function DeckWidth()
    return PAD + microW + DIVIDER_W + BAG_W + PAD
end

-- Distance from the screen's right edge to the chassis' right edge. 92 puts the
-- right edge where the old bag block ended (CENTER 1073 + 230 / 2 = 1188 of a
-- 1280 half-width) and is well clear of the 24px minimum.
local RIGHT_MARGIN = DECK_CFG.rightMargin or 92

local DIVIDER_ICON = 22

-- Frame levels, all in the HIGH strata the XP and data bars use. Nothing in
-- XPBar.lua sets a frame level, so its frames sit at a handful of levels above
-- UIParent's own; the chassis starts well above that so the XP bar's leading
-- pip bloom cannot draw over it. The slots sit above the chassis' own regions.
local LEVEL_CHASSIS = 20
local LEVEL_SLOT = LEVEL_CHASSIS + 3

-------------------------------------------------------------------------------
-- Look
-------------------------------------------------------------------------------

local TEX_DIVIDER = "Interface\\AddOns\\ForeverSynthwave\\media\\deck_divider.tga"

local CYAN = FS.Theme.COLOR_POWER -- #22e0ff; Theme.lua loads before Deck.lua
local VIOLET = { 0.486, 0.227, 0.929, 1 } -- #7C3AED
local PINK = { 1, 0.180, 0.592, 1 }       -- #ff2e97

-- The border is the data bar's: a flat COLOR_POWER edge at alpha 0.8 (DataBar.lua
-- builds its two rails with SetColorTexture at the same alpha). Requested as: "the
-- border on the micro menu and bag bar i think needs just the regular cyan border.
-- It looks cool but is distracting", then "have it be the same as the border from
-- the data bar", then of the trapezoid: "the slants don't look right now and have a
-- glow. That bar should match the rest of the ui." So the outline is the two-corner
-- cut 1 texel stroke every other panel uses, tinted to that edge: no gradient, no
-- bloom, no ADD blend.
local BORDER_ALPHA = 0.8

-------------------------------------------------------------------------------
-- Frames (built at file load so the consumers can parent at PLAYER_LOGIN)
-------------------------------------------------------------------------------

local function Scale()
    return FS.Layout.Scale()
end

local chassis = CreateFrame("Frame", "ForeverSynthwaveDeck", UIParent)
chassis:SetFrameStrata("HIGH")
chassis:SetFrameLevel(LEVEL_CHASSIS)
chassis:SetSize(DeckWidth() * Scale(), DECK_H * Scale())

local microSlot = CreateFrame("Frame", "ForeverSynthwaveDeckMicroSlot", chassis)
microSlot:SetFrameLevel(LEVEL_SLOT)
local bagSlot = CreateFrame("Frame", "ForeverSynthwaveDeckBagSlot", chassis)
bagSlot:SetFrameLevel(LEVEL_SLOT)

Deck.frame = chassis
Deck.microSlot = microSlot
Deck.bagSlot = bagSlot

-------------------------------------------------------------------------------
-- Degrade handling
-------------------------------------------------------------------------------

-- FS.LogDegradeOnce does not dedupe by key, so each site latches its own flag.
local degraded = {}

local function Degrade(key, detail)
    if degraded[key] then return end
    degraded[key] = true
    if FS.LogDegradeOnce then
        FS.LogDegradeOnce("deck_" .. key,
            "|cffff4488Forever STUwave|r: control deck " .. key .. " unavailable (" .. tostring(detail) .. ")")
    end
end

-- Decoration is optional; the contract frames above are not. Each decoration
-- group builds under its own pcall so one missing API cannot take the rest of
-- the chassis with it.
local function Try(key, fn)
    local ok, err = pcall(fn)
    if not ok then Degrade(key, err) end
end

-- Paints `tex` with a two-stop gradient (orientation "VERTICAL": c1 bottom,
-- c2 top; "HORIZONTAL": c1 left, c2 right). Same feature detection as
-- XPBar.lua's ShadePip, since SetGradientAlpha does not exist on this client.
-- Falls back to a flat tint of the midpoint when the API is missing or throws.
local function Gradient(tex, orientation, c1, c2)
    if tex.SetGradient and CreateColor then
        local ok = pcall(tex.SetGradient, tex, orientation,
            CreateColor(c1[1], c1[2], c1[3], c1[4]), CreateColor(c2[1], c2[2], c2[3], c2[4]))
        if ok then return true end
    end
    tex:SetVertexColor((c1[1] + c2[1]) / 2, (c1[2] + c2[2]) / 2, (c1[3] + c2[3]) / 2, (c1[4] + c2[4]) / 2)
    return false
end

-- Everything with a fixed design size or a design-px anchor offset registers
-- here, so Apply can re-size and re-seat it from the current scale without a
-- second copy of the numbers. Sized takes design px (nil leaves that axis
-- alone, for strips whose width comes from two anchors); Seat is SetPoint with
-- design-px offsets, applied scaled now and replayed on every Apply.
local sized = {}
local seats, seatOrder = {}, {}

local function Sized(region, w, h)
    sized[#sized + 1] = { region = region, w = w, h = h }
    if w then region:SetWidth(w * Scale()) end
    if h then region:SetHeight(h * Scale()) end
end

local function Seat(region, point, rel, relPoint, x, y)
    local list = seats[region]
    if not list then
        list = {}
        seats[region] = list
        seatOrder[#seatOrder + 1] = region
    end
    x, y = x or 0, y or 0
    list[#list + 1] = { point, rel, relPoint, x, y }
    local scale = Scale()
    region:SetPoint(point, rel, relPoint, x * scale, y * scale)
end

-------------------------------------------------------------------------------
-- Chassis art
-------------------------------------------------------------------------------

-- PetFrame.lua's panel: the two-corner cut outline and, behind it, the nine-sliced
-- two-corner cut fill at inset 0 so it meets the stroke flush. The fill is the
-- Gunsight panel scrim, the same as the pet panel; the outline is
-- COLOR_POWER at BORDER_ALPHA, the data bar's edge, with no glow texture.
Try("fill", function()
    FS.Theme.AddCut2Texture(chassis, FS.Theme.SLICE_CUT2_FILL_TEXTURE, FS.Theme.COLOR_HUD_SCRIM, "BACKGROUND", nil, 0)
end)

Try("border", function()
    FS.Theme.AddCut2Texture(chassis, FS.Theme.SLICE_CUT2_OUTLINE_TEXTURE,
        { CYAN[1], CYAN[2], CYAN[3], BORDER_ALPHA }, "BORDER", nil, 0)
end)

-- The `//` between the two slots, seated from the right edge with the slots.
Try("divider", function()
    local mark = chassis:CreateTexture(nil, "ARTWORK", nil, 1)
    mark:SetTexture(TEX_DIVIDER)
    Seat(mark, "CENTER", chassis, "RIGHT", -DIVIDER_RIGHT, 0)
    Sized(mark, DIVIDER_ICON, DIVIDER_ICON)
    Gradient(mark, "VERTICAL", { VIOLET[1], VIOLET[2], VIOLET[3], 0.95 }, { PINK[1], PINK[2], PINK[3], 0.95 })
end)

-------------------------------------------------------------------------------
-- Geometry and anchoring
-------------------------------------------------------------------------------

-- Slots are seated like the decoration (design px replayed scaled), so they go
-- through the same Seat registry from here on. All three are seated from the
-- RIGHT edge; only the chassis and the micro slot change width (ApplyGeometry).
Sized(bagSlot, BAG_W, SLOT_H)
Seat(bagSlot, "RIGHT", chassis, "RIGHT", -BAG_RIGHT, 0)
Seat(microSlot, "RIGHT", chassis, "RIGHT", -MICRO_RIGHT, 0)

local function ApplyGeometry(scale)
    chassis:SetSize(DeckWidth() * scale, DECK_H * scale)
    microSlot:SetSize(microW * scale, SLOT_H * scale)
    for _, entry in ipairs(sized) do
        if entry.w then entry.region:SetWidth(entry.w * scale) end
        if entry.h then entry.region:SetHeight(entry.h * scale) end
    end
    for _, region in ipairs(seatOrder) do
        region:ClearAllPoints()
        for _, spec in ipairs(seats[region]) do
            region:SetPoint(spec[1], spec[2], spec[3], spec[4] * scale, spec[5] * scale)
        end
    end
end

-- Seats the chassis on the XP bar's top edge. Returns true once that anchor is
-- the live one; false means the XP bar frame does not exist yet and the chassis
-- is parked at the screen bottom in the meantime (a rescale or the PLAYER_LOGIN
-- retry below picks the real anchor up once XPBar.lua has built).
local function AnchorChassis(scale)
    local xp = _G["ForeverSynthwaveXPBar"]
    chassis:ClearAllPoints()
    if xp then
        chassis:SetPoint("BOTTOMRIGHT", xp, "TOPRIGHT", -RIGHT_MARGIN * scale, 0)
        return true
    end
    -- Roughly the data bar (20) plus the XP bar, in screen units.
    chassis:SetPoint("BOTTOMRIGHT", UIParent, "BOTTOMRIGHT", -RIGHT_MARGIN * scale, 36)
    return false
end

-- Re-applies everything scale-dependent. The chassis, its decoration and the two
-- slot frames are addon-owned frames anchored to another addon-owned frame, but
-- the bag slots (BagBar.lua) are SecureActionButtonTemplate buttons, which makes
-- bagSlot, the chassis and everything anchored through them protected: resizing or
-- re-anchoring them in combat is blocked (ADDON_ACTION_BLOCKED). Deck.Apply
-- itself stays unconditional; the live rescale path and the PLAYER_LOGIN seat
-- (with its retry) go through ApplyOrDefer below, which waits for
-- PLAYER_REGEN_ENABLED. The same protection reaches the frames the chassis is
-- anchored to (the XP bar, then the data bar), which defer their own resizing.
-- The micro keys are Blizzard's own buttons, which MicroBars.lua reparents and
-- re-seats out of combat only.
-- Returns true once the chassis is anchored to the XP bar (see AnchorChassis).
function Deck.Apply()
    local scale = Scale()
    local ok, err = pcall(ApplyGeometry, scale)
    if not ok then Degrade("geometry", err) end
    return AnchorChassis(scale)
end

-- The micro slot width in design px, as MicroBars.lua last set it (MICRO_W_MAX
-- until then).
function Deck.GetMicroWidth()
    return microW
end

-- MicroBars.lua's call: the micro slot is `w` design px wide (RowWidth of the
-- shown keys), and the chassis follows. The right edge, the bag slot and the
-- divider are seated from the right, so only the left edge moves. A width above
-- MICRO_W_MAX is clamped (the keys shrink inside it); a negative, NaN, secret or
-- non-number width is ignored and false returned. microSlot parents the Blizzard
-- micro buttons, so MicroBars.lua only calls this out of combat, from the reseat
-- that also seats the keys: the deck and the keys always agree.
function Deck.SetMicroWidth(w)
    if type(w) ~= "number" or FS.IsSecret(w) or w ~= w or w < 0 then return false end
    if w > MICRO_W_MAX then w = MICRO_W_MAX end
    if w == microW then return true end
    microW = w
    local ok, err = pcall(ApplyGeometry, Scale())
    if not ok then Degrade("geometry", err) end
    return true
end

-- A rescale (UI scale or display change) or the PLAYER_LOGIN seat in combat cannot move
-- the protected chassis; it is replayed at PLAYER_REGEN_ENABLED, at the scale current
-- THEN. Returns (anchored, deferred): anchored as Deck.Apply returns it, deferred true
-- when combat held the whole call back (anchored is then nil).
local pendingApply = false
local function ApplyOrDefer()
    if InCombatLockdown() then
        pendingApply = true
        return nil, true
    end
    pendingApply = false
    return Deck.Apply(), false
end

if FS.Layout.OnRescale then
    FS.Layout.OnRescale(ApplyOrDefer)
end

local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:RegisterEvent("PLAYER_REGEN_ENABLED")
events:SetScript("OnEvent", function(_, event)
    if event == "PLAYER_REGEN_ENABLED" then
        if pendingApply then ApplyOrDefer() end
        return
    end
    -- PLAYER_LOGIN. XPBar.lua registered its own PLAYER_LOGIN handler earlier
    -- (it loads first), so its frame normally exists by now. If it does not,
    -- try once more a frame later, then say so and leave the chassis parked.
    -- Both seats go through ApplyOrDefer: logging in mid-combat must wait for
    -- regen like any other seat once the bag buttons make the chassis protected.
    local anchored, deferred = ApplyOrDefer()
    if deferred then return end
    if not anchored and C_Timer and C_Timer.After then
        C_Timer.After(0, function()
            local ok, wait = ApplyOrDefer()
            if not ok and not wait then
                Degrade("anchor", "XP bar not found, parked at the screen bottom")
            end
        end)
    elseif not anchored then
        Degrade("anchor", "XP bar not found, parked at the screen bottom")
    end
end)

-- Seat once at file scope too, so consumers that read the slots' size before
-- PLAYER_LOGIN get a sane value (UIParent is not final yet, which is why the
-- real seating waits for the event above).
pcall(ApplyGeometry, Scale())
AnchorChassis(Scale())
