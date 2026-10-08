-- Forever STUwave: Data Bar
-- Custom full-width bar pinned to the very bottom of the screen: at-a-glance
-- time/gold/rested/FPS/latency/durability/free-bag-slot readouts. Nearly
-- everything here is plain global API (no unit tokens, no secret values), so
-- it is built CUSTOM with the shared Theme panel chrome rather than skinning
-- a Blizzard frame. Non-secure throughout; no SecureUnitButtonTemplate, no
-- protected attributes, so building it needs no InCombatLockdown defer --
-- matches CastBars.lua's reasoning for the same omission. RESIZING it does: the XP
-- bar is anchored to this bar and the control deck chassis to the XP bar, and the
-- deck's bag slots are secure buttons, so this bar is RESTRICTED in combat (see
-- Rescale below).

local addonName, FS = ...

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local ApplyFontGeneric = FS.Theme.ApplyFontGeneric
local ApplyMono = FS.Theme.ApplyMono
local AddRoundedFill = FS.Theme.AddRoundedFill
local AddGradientBorder = FS.Theme.AddGradientBorder
local COLOR_TEXT_WHITE = FS.Theme.COLOR_TEXT_WHITE
local COLOR_BG = FS.Theme.COLOR_BG
local COLOR_POWER = FS.Theme.COLOR_POWER -- cyan; doubles as the segment divider/border/label tint
local FONT_ORBITRON = FS.Theme.FONT_ORBITRON

local function ApplyOrbitron(fontString, size, color)
    ApplyFontGeneric(fontString, FONT_ORBITRON, size, color)
end

-------------------------------------------------------------------------------
-- Layout constants
-------------------------------------------------------------------------------

local BAR_HEIGHT = 20 -- mock: full-ui-layout.html databar h:20
-- Derived, never hardcoded: it was a literal 7 and adding the two perf
-- segments silently pushed DUR and BAGS off the right edge of the screen,
-- because the slot width was still being divided nine ways into seven slots'
-- worth of room. Set from #SEGMENT_DEFS at build time instead (see Build).
-- Existing shipped asset (Chat.lua declares the same path for its termbar
-- status dots): a radial soft-glow disc, ADD blend, white with a cosine
-- falloff -- tinted here per currency.
local GLOW_ROUND_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\glow_round.tga"

local SEGMENT_COUNT
-- Built once by Init; resized/repositioned in place by LayoutSegments on
-- every rescale rather than recreated.
local segments = {}
local DIVIDER_WIDTH = 1
local PAD_X = 8
local LABEL_GAP = 6
local REFRESH_THROTTLE = 1.0 -- seconds; every-frame updates are wasted work for these values

-- DEBUG segment: the optional ForeverDebugBridge dev strip (a small state lattice) drawn INSIDE
-- this bar. Coupling is by global frame name only, in both directions, and neither addon needs
-- the other: this file builds the slot `ForeverSTUwaveDataBarLink` (and `FS.dataBar.linkSlot`)
-- but shows it only while `_G.ForeverDebugBridgeFrame` exists and is shown;
-- ForeverDebugBridge.lua anchors itself to the slot's recess when it finds it. The lattice is a
-- fixed number of PHYSICAL pixels (it is read off the screen as pixels), so the slot width is
-- converted into bar units at runtime from the bar's effective scale;
-- nothing here assumes a scale of 1.
local UI_REFERENCE_HEIGHT = 768 -- effective scale 1.0 spans 768 units of physical screen height
local LINK_FOOTPRINT_W = 228    -- fallback when the bridge frame does not publish `footprint`
local LINK_FOOTPRINT_H = 18     -- ((23 - 1) * 10 + 8 by (2 - 1) * 10 + 8, ForeverDebugBridge Layout.lua)
local LINK_RECESS_PAD_PX = 4    -- the recess frame is 4 px wider than the cells each side
local LINK_END_PAD_PX = 4       -- the recess to the slot's right edge, before TIME's own divider
local LINK_LABEL_FALLBACK_W = 32

-------------------------------------------------------------------------------
-- Feature detection (module scope, checked once)
-------------------------------------------------------------------------------

local HAS_GET_GAME_TIME = type(GetGameTime) == "function"
local HAS_DATE = type(date) == "function"
local HAS_GET_MONEY = type(GetMoney) == "function"

-- UnitXPMax is a plain, callable, non-secret function on this client (XPBar.lua
-- renders live progress from UnitXP/UnitXPMax; see its header), so the rested
-- segment is computed as GetXPExhaustion over UnitXPMax and only
-- GetXPExhaustion needs a feature gate here.
local HAS_XP_EXHAUSTION = type(GetXPExhaustion) == "function"
local HAS_GET_FRAMERATE = type(GetFramerate) == "function"
local HAS_GET_NET_STATS = type(GetNetStats) == "function"
local HAS_DURABILITY = type(GetInventoryItemDurability) == "function"

-- C_Container.GetContainerNumFreeSlots replaced the global GetContainerNumFreeSlots
-- on modern clients; feature-detect both and pick whichever exists once, rather
-- than branching on every tick.
local GetFreeSlotsForBag
if type(C_Container) == "table" and type(C_Container.GetContainerNumFreeSlots) == "function" then
    GetFreeSlotsForBag = C_Container.GetContainerNumFreeSlots
elseif type(GetContainerNumFreeSlots) == "function" then
    GetFreeSlotsForBag = GetContainerNumFreeSlots
end

local BAG_IDS = { 0, 1, 2, 3, 4 }

-------------------------------------------------------------------------------
-- Segment update functions
-- Each takes the segment table (frame/labelText/valueText) and either sets
-- valueText or throws; TryUpdate (below) pcalls these and hides the segment
-- on failure, so a client-specific API gap only omits that one readout.
-------------------------------------------------------------------------------

-- LOCAL time, on Parker's call -- "can we make it my local time. Not server
-- time?".
--
-- The two are different functions, and the naming is the trap: GetGameTime()
-- returns the REALM's clock, not the machine's, so the obvious-looking call is
-- the wrong one. Lua's date() reads the operating system.
--
-- GetGameTime is kept only as a fallback for a client without date(), which is
-- theoretical here but costs one line.
-- 12-hour, on Parker's call ("can you make it non-military time").
--
-- The hour is run back through tonumber to drop %I's leading zero -- "1:05 AM"
-- rather than "01:05 AM" -- since a padded 12-hour clock reads like the
-- 24-hour one it is meant to replace.
local function UpdateTime(segment)
    local text
    if HAS_DATE then
        text = ("%d:%s %s"):format(tonumber(date("%I")) or 12, date("%M"), date("%p"))
    elseif HAS_GET_GAME_TIME then
        -- Realm clock fallback: 24-hour, so convert by hand.
        local hour, minute = GetGameTime()
        local suffix = hour >= 12 and "PM" or "AM"
        local display = hour % 12
        if display == 0 then display = 12 end
        text = ("%d:%02d %s"):format(display, minute, suffix)
    end
    segment.valueText:SetText(text or "--")
end

-- Standard Blizzard money-text colors (gold/silver/copper), matching the hex
-- values Theme.StyleMoney's target MoneyFrame templates use.
local function FormatMoney(copper)
    local gold = math.floor(copper / 10000)
    local silver = math.floor((copper % 10000) / 100)
    local bronze = copper % 100
    return string.format("|cffffd700%d|rg |cffc7c7cf%d|rs |cffeda55f%d|rc", gold, silver, bronze)
end

-- Currency as three small neon coins instead of "g/s/c" letters. The disc is
-- the existing glow_round.tga (a soft radial, already shipped for the termbar
-- status dots) tinted per denomination and drawn ADD, so each reads as a lit
-- orb rather than a flat dot -- on-theme with the bezel keys and the term bar.
--
-- Palette picked to stay inside the synthwave set rather than mimic Blizzard's
-- metallic coins: amber for gold (the theme's existing amber), pale cyan for
-- silver, pink for copper.
local COIN_GOLD   = { 1, 0.714, 0.282 }   -- --amber
local COIN_SILVER = { 0.78, 0.93, 1 }     -- pale cyan-white
local COIN_COPPER = { 1, 0.42, 0.55 }     -- warm pink

local COIN_SIZE = 9
local COIN_TEXT_GAP = 2
local COIN_GROUP_GAP = 7

local function UpdateGold(segment)
    local copper = GetMoney()
    if type(copper) ~= "number" then error("GetMoney returned a non-number") end

    if not segment.coins then
        segment.valueText:SetText(FormatMoney(copper))
        return
    end

    local g = math.floor(copper / 10000)
    local sv = math.floor((copper % 10000) / 100)
    local c = copper % 100

    segment.coins.gold.text:SetText(g)
    segment.coins.silver.text:SetText(sv)
    segment.coins.copper.text:SetText(c)

    -- Hide leading denominations the player does not have, so a broke
    -- character shows "12c" rather than "0 0 12".
    segment.coins.gold.text:SetShown(g > 0)
    segment.coins.gold.icon:SetShown(g > 0)
    segment.coins.silver.text:SetShown(g > 0 or sv > 0)
    segment.coins.silver.icon:SetShown(g > 0 or sv > 0)
end

-- Sets a meter's fill and hides its pill caps at exactly 0, where the two
-- caps would otherwise pair into a dot. `fraction` is a plain Lua number here.
local function SetMeterFraction(meter, fraction)
    meter.fill:SetValue(fraction)
    meter.caps.SetShown(fraction > 0)
end

-- Colors the left and right end caps separately. AddPillCaps and AddCutPillCaps return their
-- textures left pair first, then right pair.
local function SetMeterCapColors(caps, left, right)
    local textures = caps.textures
    for index = 1, 2 do
        textures[index]:SetVertexColor(left[1], left[2], left[3], left[4] or 1)
        textures[index + 2]:SetVertexColor(right[1], right[2], right[3], right[4] or 1)
    end
end

-- Rested XP as a percentage of one level's XP (GetXPExhaustion over
-- UnitXPMax, see the note above HAS_XP_EXHAUSTION). Lit cyan "NN%" when
-- GetXPExhaustion reports any banked rested XP, dim "--" otherwise.
local function UpdateRested(segment)
    local exhaustion = GetXPExhaustion()
    local maximum = UnitXPMax and UnitXPMax("player") or 0

    -- Rested is expressed as a fraction of a level's XP, which is how the
    -- mockup's RESTED meter reads. UnitXPMax is not secret on this client (see
    -- XPBar.lua), so the division is safe.
    local fraction = 0
    if type(exhaustion) == "number" and exhaustion > 0 and maximum > 0 then
        fraction = math.min(exhaustion / maximum, 1)
    end

    if segment.meter then
        SetMeterFraction(segment.meter, fraction)
        segment.meter.track:SetShown(true)
    end

    if fraction > 0 then
        segment.valueText:SetTextColor(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 1)
        segment.valueText:SetFormattedText("%d%%", fraction * 100)
    else
        segment.valueText:SetTextColor(COLOR_TEXT_WHITE[1], COLOR_TEXT_WHITE[2], COLOR_TEXT_WHITE[3], 0.35)
        segment.valueText:SetText("--")
    end
end

local function UpdateFPS(segment)
    local fps = GetFramerate()
    segment.valueText:SetFormattedText("%d", math.floor(fps + 0.5))
end

local function UpdateLatency(segment)
    local _, _, latencyHome, latencyWorld = GetNetStats()
    segment.valueText:SetFormattedText("%d", latencyWorld or latencyHome or 0)
end

-- Sums current/max durability over every equipped slot that reports it
-- (rings/trinkets/necklace return nil for both and are skipped); an empty
-- equipped set (fresh character) reports 100%, matching Blizzard's own
-- character-frame convention rather than a divide-by-zero.
local function UpdateDurability(segment)
    local firstSlot = INVSLOT_FIRST_EQUIPPED or 1
    local lastSlot = INVSLOT_LAST_EQUIPPED or 19
    local totalCur, totalMax = 0, 0
    for slot = firstSlot, lastSlot do
        local cur, max = GetInventoryItemDurability(slot)
        if cur and max and max > 0 then
            totalCur = totalCur + cur
            totalMax = totalMax + max
        end
    end
    local pct = (totalMax > 0) and (totalCur / totalMax * 100) or 100
    if segment.meter then
        SetMeterFraction(segment.meter, pct / 100)
    end
    segment.valueText:SetFormattedText("%.0f%%", pct)
end

-- Bag fullness thresholds. The meter fills as the bags FILL, so a long bar is
-- bad news, and the colour shifts before it becomes a problem rather than only
-- once it already is.
local BAGS_WARN = 0.75
local BAGS_FULL = 0.90
local BAGS_COLOR_OK = { 0.133, 1, 0.463 }    -- --green
local BAGS_COLOR_WARN = { 1, 0.714, 0.282 }  -- --amber
local BAGS_COLOR_FULL = { 1, 0.180, 0.592 }  -- --pink

-- Perf segments. Parker is seeing 25 fps in Undercity and wants to know whether
-- this addon is the cause, so the bar reports OUR cost specifically rather than
-- a global number that cannot answer the question.
--
-- GetAddOnCPUUsage only returns anything when the scriptProfile CVar is on, and
-- that needs a client restart to take effect, so CPU degrades to "--" with a
-- hint rather than silently reading zero.
local ADDON_NAME = addonName

local function UpdateMemory(segment)
    if not UpdateAddOnMemoryUsage then return end
    UpdateAddOnMemoryUsage()

    local kb = GetAddOnMemoryUsage(ADDON_NAME) or 0
    -- Total Lua heap for context: a big addon number matters much less if the
    -- whole UI is small.
    local totalKb = collectgarbage and collectgarbage("count") or 0

    if kb >= 1024 then
        segment.valueText:SetFormattedText("%.1fM", kb / 1024)
    else
        segment.valueText:SetFormattedText("%.0fK", kb)
    end

    if segment.meter and totalKb > 0 then
        SetMeterFraction(segment.meter, math.min(kb / totalKb, 1))
    end
end

-- Previous cumulative reading, so UpdateCPU can turn it into a rate.
local lastCPUTotal, lastCPUAt, cpuRate

local function UpdateCPU(segment)
    if not (GetAddOnCPUUsage and UpdateAddOnCPUUsage) then
        segment.valueText:SetText("--")
        return
    end

    -- scriptProfile off => every addon reads 0.
    local profiling = GetCVar and GetCVar("scriptProfile") == "1"
    if not profiling then
        segment.valueText:SetTextColor(COLOR_TEXT_WHITE[1], COLOR_TEXT_WHITE[2], COLOR_TEXT_WHITE[3], 0.35)
        segment.valueText:SetText("off")
        return
    end

    UpdateAddOnCPUUsage()
    local total = GetAddOnCPUUsage(ADDON_NAME) or 0
    local now = GetTime()

    -- GetAddOnCPUUsage is CUMULATIVE milliseconds since profiling started, not
    -- a per-frame cost. Printed raw it only ever goes up, which reads like a
    -- runaway (19ms looked alarming next to a 50ms frame; it was the whole
    -- session's total). The useful number is the RATE: milliseconds of CPU per
    -- second of wall clock, i.e. what share of one core we are eating.
    -- 10ms/s = 1%.
    if lastCPUTotal and now > lastCPUAt then
        cpuRate = (total - lastCPUTotal) / (now - lastCPUAt)
    end
    lastCPUTotal, lastCPUAt = total, now

    segment.valueText:SetTextColor(COLOR_TEXT_WHITE[1], COLOR_TEXT_WHITE[2], COLOR_TEXT_WHITE[3], 1)
    if cpuRate then
        -- Shown as a percentage of one core, because "is this addon the reason
        -- my frames are bad" is a share-of-a-frame question, not a totals one.
        segment.valueText:SetFormattedText("%.1f%%", cpuRate / 10)
    else
        segment.valueText:SetText("...")
    end
end

-- One CreateColor object per meter colour, built on first use: UpdateBags runs
-- every tick and SetGradient copies the values, so a fresh pair each call is churn.
local bagsGradientColors = {}
local function BagsGradientColor(color)
    local created = bagsGradientColors[color]
    if not created then
        created = CreateColor(color[1], color[2], color[3], 1)
        bagsGradientColors[color] = created
    end
    return created
end

local function UpdateBags(segment)
    local free, total = 0, 0
    for _, bagID in ipairs(BAG_IDS) do
        local slots = GetFreeSlotsForBag(bagID)
        if type(slots) == "number" then free = free + slots end

        -- C_Container namespace, NOT the old global: the 16001 dump lists
        -- C_Container.GetContainerNumSlots and no bare GetContainerNumSlots, so
        -- the first attempt silently returned nothing and the meter sat empty
        -- with a bare free count.
        local getSlots = C_Container and C_Container.GetContainerNumSlots
        local size = getSlots and getSlots(bagID)
        if type(size) == "number" then total = total + size end
    end

    -- free/total, as asked -- but the METER shows USED, so a filling bar reads
    -- as "running out of room" at a glance without having to read the numbers.
    local used = math.max(0, total - free)
    local fraction = (total > 0) and (used / total) or 0

    if segment.meter then
        SetMeterFraction(segment.meter, fraction)

        local color = BAGS_COLOR_OK
        if fraction >= BAGS_FULL then
            color = BAGS_COLOR_FULL
        elseif fraction >= BAGS_WARN then
            color = BAGS_COLOR_WARN
        end
        -- A solid colour here, not the shared gradient: the whole point is that
        -- the colour itself carries the warning.
        segment.meter.fill:SetStatusBarColor(color[1], color[2], color[3], 1)
        SetMeterCapColors(segment.meter.caps, color, color)
        local texture = segment.meter.fill:GetStatusBarTexture()
        if texture and texture.SetGradient and CreateColor then
            local gradientColor = BagsGradientColor(color)
            texture:SetGradient("HORIZONTAL", gradientColor, gradientColor)
        end
    end

    if total > 0 then
        segment.valueText:SetFormattedText("%d/%d", free, total)
    else
        segment.valueText:SetFormattedText("%d", free)
    end
end

-------------------------------------------------------------------------------
-- Segment definitions
-------------------------------------------------------------------------------

-- .dbar from the mockup: 64x9, radius 5, rgba(6,3,18,.9) ground,
-- 1px rgba(34,224,255,.4) border, green -> cyan gradient fill.
local METER_WIDTH = 64
local METER_HEIGHT = 9
local METER_RADIUS = 5
local METER_TRACK_FILL = { 0.024, 0.012, 0.071, 0.90 }
local METER_TRACK_BORDER = { COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.40 }
local METER_FILL_LEFT = { 0.133, 1, 0.463, 1 }   -- --green
local METER_FILL_RIGHT = { COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 1 }
-- The fill is a pill: Theme.AddPillCaps end caps of METER_FILL_RADIUS sit
-- outside a StatusBar inset by the border plus that radius on each side.
local METER_INSET = 1
local METER_FILL_HEIGHT = METER_HEIGHT - 2 * METER_INSET
local METER_FILL_RADIUS = METER_FILL_HEIGHT / 2
-- Under Theme.CHROME_CORNERS == "cut" the whole meter chamfers TOP-LEFT and BOTTOM-RIGHT
-- only: the track and its border at Theme.CutSize(METER_HEIGHT) = 3, the fill's colored
-- Theme.AddCutPillCaps at that same chamfer. The fill sits METER_INSET inside the track,
-- so its diagonals run parallel to the track's, one border width further in. Colored
-- caps (not erase quads) because the track alpha is 0.90 and erase quads would replace
-- the 10% bleed.

local SEGMENT_DEFS = {
    { key = "fps", label = "FPS", available = HAS_GET_FRAMERATE, update = UpdateFPS },
    { key = "mem", label = "FS MEM", available = (UpdateAddOnMemoryUsage ~= nil), update = UpdateMemory, meter = true },
    { key = "cpu", label = "FS CPU", available = (GetAddOnCPUUsage ~= nil), update = UpdateCPU },
    { key = "latency", label = "MS", available = HAS_GET_NET_STATS, update = UpdateLatency },
    { key = "rested", label = "REST", available = HAS_XP_EXHAUSTION, update = UpdateRested, meter = true },
    { key = "durability", label = "DUR", available = HAS_DURABILITY, update = UpdateDurability, meter = true },
    { key = "bags", label = "BAGS", available = (GetFreeSlotsForBag ~= nil), update = UpdateBags, meter = true },
    { key = "time", label = "TIME", available = HAS_DATE or HAS_GET_GAME_TIME, update = UpdateTime },
    { key = "gold", label = "GOLD", available = HAS_GET_MONEY, update = UpdateGold, coins = true },
}

-------------------------------------------------------------------------------
-- Frame assembly
-------------------------------------------------------------------------------

-- One equal-width slot: an optional left divider (skipped on the first
-- segment, which sits flush against the panel's own border), an Orbitron
-- label, and a Mononoki value anchored to its right. Size and position are
-- applied separately by LayoutSegments, so a rescale can redo them without
-- recreating these regions.
local function CreateSegment(bar, index, def)
    local seg = CreateFrame("Frame", nil, bar)

    if index > 1 then
        local divider = seg:CreateTexture(nil, "OVERLAY")
        divider:SetColorTexture(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.5)
        divider:SetPoint("TOPLEFT", seg, "TOPLEFT", 0, 0)
        divider:SetPoint("BOTTOMLEFT", seg, "BOTTOMLEFT", 0, 0)
        divider:SetWidth(DIVIDER_WIDTH)
    end

    local labelText = seg:CreateFontString(nil, "OVERLAY")
    labelText:SetPoint("LEFT", seg, "LEFT", PAD_X, 0)
    ApplyOrbitron(labelText, 9, COLOR_POWER)
    labelText:SetText(def.label)

    local valueText = seg:CreateFontString(nil, "OVERLAY")
    valueText:SetPoint("LEFT", labelText, "RIGHT", LABEL_GAP, 0)
    ApplyMono(valueText, 11, COLOR_TEXT_WHITE)

    -- Segments flagged `coins` swap the single value string for three
    -- coin+number pairs, laid left to right and anchored off the label like
    -- any other value.
    local coins
    if def.coins then
        valueText:Hide()
        coins = {}
        local previous
        for _, spec in ipairs({
            { key = "gold", color = COIN_GOLD },
            { key = "silver", color = COIN_SILVER },
            { key = "copper", color = COIN_COPPER },
        }) do
            local icon = seg:CreateTexture(nil, "OVERLAY")
            icon:SetTexture(GLOW_ROUND_TEXTURE)
            icon:SetBlendMode("ADD")
            icon:SetVertexColor(spec.color[1], spec.color[2], spec.color[3], 1)
            icon:SetSize(COIN_SIZE, COIN_SIZE)
            if previous then
                icon:SetPoint("LEFT", previous, "RIGHT", COIN_GROUP_GAP, 0)
            else
                icon:SetPoint("LEFT", labelText, "RIGHT", LABEL_GAP, 0)
            end

            local text = seg:CreateFontString(nil, "OVERLAY")
            ApplyMono(text, 11, spec.color)
            text:SetPoint("LEFT", icon, "RIGHT", COIN_TEXT_GAP, 0)

            coins[spec.key] = { icon = icon, text = text }
            previous = text
        end
    end

    -- Segments flagged `meter` get the mockup's .dbar instead of a number:
    -- 64x9, radius 5, rgba(6,3,18,.9) ground with a 40% cyan border, filled by
    -- a green -> cyan gradient with pill-rounded ends. The mockup draws RESTED
    -- and DURA this way and everything else as text.
    local meter
    if def.meter then
        local track = CreateFrame("Frame", nil, seg)
        track:SetSize(METER_WIDTH, METER_HEIGHT)
        track:SetPoint("LEFT", labelText, "RIGHT", LABEL_GAP, 0)
        local cut = FS.Theme.CHROME_CORNERS == "cut" and FS.Theme.AddCutPillCaps ~= nil
        local chamfer = cut and FS.Theme.CutSize(METER_HEIGHT) or 0
        AddRoundedFill(track, METER_TRACK_FILL, cut and chamfer or METER_RADIUS)
        AddGradientBorder(track, METER_TRACK_BORDER, 1, cut and chamfer or METER_RADIUS)

        local fill = CreateFrame("StatusBar", nil, track)
        local fillInset = METER_INSET + (cut and chamfer or METER_FILL_RADIUS)
        fill:SetPoint("TOPLEFT", track, "TOPLEFT", fillInset, -METER_INSET)
        fill:SetPoint("BOTTOMRIGHT", track, "BOTTOMRIGHT", -fillInset, METER_INSET)
        fill:SetStatusBarTexture(FS.Theme.FLAT_TEXTURE)
        fill:SetMinMaxValues(0, 1)
        fill:SetValue(0)

        local caps
        if cut then
            caps = FS.Theme.AddCutPillCaps(track, fill, METER_FILL_RIGHT, chamfer, METER_FILL_HEIGHT)
        else
            caps = FS.Theme.AddPillCaps(track, fill, METER_FILL_RIGHT, METER_FILL_RADIUS, METER_FILL_HEIGHT)
        end
        caps.SetShown(false)

        local texture = fill:GetStatusBarTexture()
        if texture and texture.SetGradient and CreateColor then
            texture:SetGradient("HORIZONTAL",
                CreateColor(METER_FILL_LEFT[1], METER_FILL_LEFT[2], METER_FILL_LEFT[3], 1),
                CreateColor(METER_FILL_RIGHT[1], METER_FILL_RIGHT[2], METER_FILL_RIGHT[3], 1))
            SetMeterCapColors(caps, METER_FILL_LEFT, METER_FILL_RIGHT)
        else
            fill:SetStatusBarColor(unpack(METER_FILL_RIGHT))
        end

        meter = { track = track, fill = fill, caps = caps }
        -- The number moves to the right of the meter so both read at a glance.
        valueText:ClearAllPoints()
        valueText:SetPoint("LEFT", track, "RIGHT", LABEL_GAP, 0)
    end

    return {
        key = def.key,
        frame = seg,
        labelText = labelText,
        valueText = valueText,
        meter = meter,
        coins = coins,
        available = def.available,
        update = def.update,
    }
end

-- The DEBUG slot: the bar's own divider, an Orbitron "DEBUG" label like its neighbours, then a
-- bare recess frame (no fill, the bar background shows through) that the debug lattice is
-- centred in (`frame.recess`, read by ForeverDebugBridge.lua).
-- Built once, hidden; LayoutSegments sizes, seats and shows it only while a bridge is shown.
local link

local function CreateLink(bar)
    local frame = CreateFrame("Frame", "ForeverSTUwaveDataBarLink", bar)

    local divider = frame:CreateTexture(nil, "OVERLAY")
    divider:SetColorTexture(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.5)
    divider:SetPoint("TOPLEFT", frame, "TOPLEFT", 0, 0)
    divider:SetPoint("BOTTOMLEFT", frame, "BOTTOMLEFT", 0, 0)
    divider:SetWidth(DIVIDER_WIDTH)

    local label = frame:CreateFontString(nil, "OVERLAY")
    label:SetPoint("LEFT", frame, "LEFT", PAD_X, 0)
    ApplyOrbitron(label, 9, COLOR_POWER)
    label:SetText("DEBUG")

    -- No fill of its own: the lattice sits directly on the data bar's background.
    local recess = CreateFrame("Frame", nil, frame)
    recess:SetPoint("LEFT", label, "RIGHT", LABEL_GAP, 0)

    frame.recess = recess
    frame:Hide()
    return { frame = frame, label = label, recess = recess }
end

local linkShortWarned = false

-- Physical pixels per bar unit, or nil when the client cannot say (then there is no DEBUG slot:
-- a unit would not be a pixel and the lattice could not be sized).
local function PixelsPerUnit(bar)
    if type(GetPhysicalScreenSize) ~= "function" then return nil end
    local _, physH = GetPhysicalScreenSize()
    local eff = bar:GetEffectiveScale()
    if type(physH) ~= "number" or physH <= 0 or type(eff) ~= "number" or eff <= 0 then return nil end
    return eff * physH / UI_REFERENCE_HEIGHT
end

-- The slot's width and its recess width in bar units, or nil when there is no DEBUG: no slot
-- built, no bridge frame, the bridge hidden (/fdebug hide), or no pixel scale.
local function LinkSize(bar)
    if not link then return nil end
    local bridge = _G.ForeverDebugBridgeFrame
    if type(bridge) ~= "table" or not bridge.IsShown or not bridge:IsShown() then return nil end
    local ppu = PixelsPerUnit(bar)
    if not ppu then return nil end

    local footprint = type(bridge.footprint) == "table" and bridge.footprint or nil
    local cellsW = footprint and footprint.w or LINK_FOOTPRINT_W
    local cellsH = footprint and footprint.h or LINK_FOOTPRINT_H
    -- The 0.01 keeps float noise at the exact pixel-perfect scale (20 units = 20.0 px) from warning.
    if BAR_HEIGHT * ppu + 0.01 < cellsH + 2 and not linkShortWarned then
        linkShortWarned = true
        FS.LogDegradeOnce("databar_link_short", ("|cff22e0ffForever STUwave|r data bar: at this UI scale it is " ..
            "%.1f px tall, shorter than the %d px debug strip plus its rails; the DEBUG cells overhang the bar."):format(
            BAR_HEIGHT * ppu, cellsH))
    end

    local labelW = link.label:GetStringWidth()
    if type(labelW) ~= "number" or labelW <= 0 then labelW = LINK_LABEL_FALLBACK_W end
    local recessW = (cellsW + 2 * LINK_RECESS_PAD_PX) / ppu
    return PAD_X + labelW + LABEL_GAP + recessW + LINK_END_PAD_PX / ppu, recessW
end

-- Runs one segment's update under pcall; a throwing call (a present-but-
-- differently-shaped API on this client) disables and hides that segment
-- rather than spamming the tick, printing once so the cause is visible.
local function TryUpdate(segment)
    if not segment.available then return end
    local ok, err = pcall(segment.update, segment)
    if not ok then
        segment.available = false
        segment.frame:Hide()
        print("|cff22e0ffForever STUwave|r databar segment '" .. segment.key ..
            "' failed: " .. tostring(err) .. " (hidden)")
    end
end

-- Re-seats every segment across `bar`. Called once from Init, right after the segments are
-- built, and again from Rescale and whenever the bridge is shown or hidden, so the build-time
-- and rescale-time formulas can never drift apart. Without a DEBUG slot every segment gets an
-- equal share, exactly as before; with one, DEBUG takes its fixed width just before TIME (so
-- between BAGS and TIME) and the others share the remainder equally.
local function LayoutSegments(bar, screenWidth)
    if #segments == 0 then return end
    local linkWidth, recessWidth = LinkSize(bar)
    local segWidth = (screenWidth - (linkWidth or 0)) / SEGMENT_COUNT
    local x = 0   -- running offset, used only while a DEBUG slot is being seated
    local function placeLink()
        link.frame:SetSize(linkWidth, BAR_HEIGHT)
        link.frame:ClearAllPoints()
        link.frame:SetPoint("TOPLEFT", bar, "TOPLEFT", x, 0)
        link.recess:SetSize(recessWidth, BAR_HEIGHT - 2)
        link.frame:Show()
        x = x + linkWidth
    end
    local linkPlaced = linkWidth == nil
    for index, segment in ipairs(segments) do
        if not linkPlaced and segment.key == "time" then
            placeLink()
            linkPlaced = true
        end
        segment.frame:SetSize(segWidth, BAR_HEIGHT)
        segment.frame:ClearAllPoints()
        -- No DEBUG: the original `(index - 1) * segWidth`, bit for bit; the running offset
        -- only exists to step past the DEBUG slot.
        segment.frame:SetPoint("TOPLEFT", bar, "TOPLEFT", linkWidth and x or (index - 1) * segWidth, 0)
        x = x + segWidth
    end
    if not linkPlaced then placeLink() end
    if linkWidth == nil and link then link.frame:Hide() end
end

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

local function Init()
    local bar = CreateFrame("Frame", "ForeverSTUwaveDataBar", UIParent)
    -- GetScreenWidth() at addon-load time reports a PRE-SETTLE value: the
    -- region dump caught this bar at 1377 wide on a 2151-wide screen, so it was
    -- a centred strip with visible gaps at both ends rather than a full-width
    -- bar. Same UIParent timing trap as the rest of the layout -- take the
    -- width live instead of caching it at load.
    local screenWidth = UIParent:GetWidth()
    if not screenWidth or screenWidth <= 0 then
        screenWidth = GetScreenWidth() or 1024
    end
    bar:SetSize(screenWidth, BAR_HEIGHT)
    bar:SetPoint("BOTTOM", UIParent, "BOTTOM", 0, 0)

    -- Non-secure, screen-pinned frame: raise above Blizzard's default MEDIUM
    -- strata so the bar clears the bottom action-bar art it otherwise renders
    -- behind. HIGH sits below TOOLTIP/FULLSCREEN_DIALOG, so tooltips/menus
    -- still draw over it.
    bar:SetFrameStrata("HIGH")

    -- Square-cornered panel chrome (radius 0 -- a full-width strip has no
    -- corners to round), same primitives BuildUnitFrame/BuildCastBar use.
    -- Chrome drawn directly rather than via the shared helpers.
    --
    -- Those helpers were producing a large cyan quarter-disc at each END of the
    -- bar -- confirmed by toggling this frame and diffing the same screen
    -- region: arc present when shown, gone when hidden. All three calls passed
    -- radius 0, which is meant to skip every corner piece, so something in that
    -- path still emits one at this frame's proportions. A full-width strip has
    -- no corners to round, so it needs none of that machinery: a flat fill plus
    -- four 1px rails is the whole design and cannot grow an arc.
    local fill = bar:CreateTexture(nil, "BACKGROUND")
    fill:SetAllPoints(bar)
    fill:SetColorTexture(COLOR_BG[1], COLOR_BG[2], COLOR_BG[3], COLOR_BG[4] or 1)

    for _, edge in ipairs({
        { "TOPLEFT", "TOPRIGHT", "h" },
        { "BOTTOMLEFT", "BOTTOMRIGHT", "h" },
    }) do
        local rail = bar:CreateTexture(nil, "BORDER")
        rail:SetColorTexture(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.8)
        rail:SetPoint(edge[1], bar, edge[1], 0, 0)
        rail:SetPoint(edge[2], bar, edge[2], 0, 0)
        rail:SetHeight(1)
    end

    -- Only segments this client can actually populate get a slot, so an
    -- unavailable API leaves the others wider rather than leaving a gap.
    SEGMENT_COUNT = 0
    for _, def in ipairs(SEGMENT_DEFS) do
        if def.available then SEGMENT_COUNT = SEGMENT_COUNT + 1 end
    end
    if SEGMENT_COUNT < 1 then SEGMENT_COUNT = #SEGMENT_DEFS end

    -- Slots are handed out by POSITION AMONG THE SHOWN segments, not by index
    -- in SEGMENT_DEFS. Using the def index meant an unavailable API still
    -- reserved its slot and left a hole in the bar; this way the segments that
    -- do exist simply divide the full width between them.
    segments = {}
    local slot = 0
    for _, def in ipairs(SEGMENT_DEFS) do
        if def.available then
            slot = slot + 1
            segments[#segments + 1] = CreateSegment(bar, slot, def)
        end
    end
    link = CreateLink(bar)
    bar.linkSlot = link.frame
    LayoutSegments(bar, screenWidth)

    local function UpdateAllSegments()
        for _, segment in ipairs(segments) do
            TryUpdate(segment)
        end
    end

    UpdateAllSegments()

    local elapsedSinceTick = 0
    bar:SetScript("OnUpdate", function(_, elapsed)
        elapsedSinceTick = elapsedSinceTick + elapsed
        if elapsedSinceTick < REFRESH_THROTTLE then return end
        elapsedSinceTick = 0
        UpdateAllSegments()
    end)

    FS.dataBar = bar
end

-- Re-measures for a new screen width. XPBar docks flush to this bar's top
-- edge and re-derives its own width on the same callback, so a stale width
-- here would desync the "one console strip" the two bars are meant to be.
-- Also the DEBUG refresh: the slot's width depends on the bar's effective scale.
--
-- In combat this is DEFERRED to PLAYER_REGEN_ENABLED: the XP bar is anchored to this bar,
-- the deck chassis to the XP bar and the chassis hosts secure buttons, so this bar is
-- restricted then and SetSize on it would be blocked. The segments are children of the
-- restricted bar, so they are deferred alongside its width only to keep the two consistent.
-- The replay re-reads the screen width, the UI scale and the bridge state current THEN.
-- A /fdebug show|hide in combat therefore moves DEBUG after combat. Replay order against
-- XPBar.lua and Deck.lua does not matter: all three are anchored to each other, not sized
-- from each other.
local pendingRescale = false
local function Rescale()
    if not FS.dataBar then return end
    if InCombatLockdown() then
        pendingRescale = true
        return
    end
    pendingRescale = false
    local screenWidth = UIParent:GetWidth()
    if not screenWidth or screenWidth <= 0 then
        screenWidth = GetScreenWidth() or 1024
    end
    FS.dataBar:SetSize(screenWidth, BAR_HEIGHT)
    LayoutSegments(FS.dataBar, screenWidth)
end

-- /fdebug hide|show flips the bridge frame; relayout so DEBUG appears or goes and the other
-- segments close up. Hooked once, as soon as the frame exists (it may load after us).
local hookedBridge
local function HookBridge()
    local bridge = _G.ForeverDebugBridgeFrame
    if type(bridge) ~= "table" or bridge == hookedBridge or not bridge.HookScript then return end
    hookedBridge = bridge
    bridge:HookScript("OnShow", Rescale)
    bridge:HookScript("OnHide", Rescale)
end

-- PLAYER_LOGIN, not file scope: UIParent:GetWidth() is the whole point of the
-- fix above, and at load it still reports the pre-settle value. PLAYER_ENTERING_WORLD
-- is the second look for a bridge that was not there (or not yet shown) at login.
local loader = CreateFrame("Frame")
loader:RegisterEvent("PLAYER_LOGIN")
loader:RegisterEvent("PLAYER_ENTERING_WORLD")
loader:RegisterEvent("PLAYER_REGEN_ENABLED")
loader:SetScript("OnEvent", function(self, event)
    if event == "PLAYER_REGEN_ENABLED" then
        if pendingRescale then Rescale() end
    elseif event == "PLAYER_LOGIN" then
        Init()
        HookBridge()

        if FS.Layout.OnRescale then
            FS.Layout.OnRescale(Rescale)
        end
    elseif FS.dataBar then
        HookBridge()
        Rescale()
    end
end)
