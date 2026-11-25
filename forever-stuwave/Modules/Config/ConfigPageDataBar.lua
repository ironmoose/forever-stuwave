-- Forever STUwave: Config page, Data bar
-- One tab, "Segments": a pinned preview band over one row per segment.
--
-- The band draws the bar as the settings make it: the segments that are on, in order, each under its title (an empty title
-- leaves only the value), with sample values. Its measures are the ones DataBar.lua keeps to itself, copied here under the
-- same names (tools/databarpage-harness.py reads them back out of DataBar.lua, so a change there fails the check).
--
-- Each row is UI.Order (the switch, a title box, the two arrows) with what the segment ticket adds on top: the live rename
-- while typing, the box letting go of the keyboard (Enter, Esc, Tab, a click elsewhere, the window or tab hiding), the
-- ON / OFF word, the changed dot and reset, a disabled switch with its reason in the ? tip, and the rows re-seating in the
-- bar's order after a move. Every change goes through FS.DataBarSegments, so the bar re-lays out live and the band follows
-- the same refresh. Everything drawn here is pending owner review.

local _, FS = ...

local CW = FS.ConfigWindow
local UI, I, C, S, D = CW.UI, CW.I, CW.C, CW.Spec, CW.D
local Theme = FS.Theme

local PREVIEW_TIP = "The bar along the bottom of your screen, in the order and with the segments set below."
local SEGMENTS_TIP = "The box is the title shown on the bar: type to rename it, clear it to show only the value. "
    .. "Arrows move a segment left or right. At least one stays on."
local NOT_LOADED = "The data bar is not loaded."
local ORDER_LABEL = "Segment order"

-------------------------------------------------------------------------------
-- The band: the bar, drawn from DataBar.lua's own measures
-------------------------------------------------------------------------------

-- Copied from DataBar.lua, same names (the harness compares them).
local BAR_HEIGHT = 20
local PAD_X = 8
local LABEL_GAP = 6
local DIVIDER_WIDTH = 1
local METER_WIDTH = 64
local METER_HEIGHT = 9
local COIN_SIZE = 9
local COIN_TEXT_GAP = 2
local COIN_GROUP_GAP = 7
local METER_TRACK_FILL = { 0.024, 0.012, 0.071, 0.90 }
local METER_FILL_LEFT = { 0.133, 1, 0.463, 1 }   -- --green
local COIN_GOLD   = { 1, 0.714, 0.282 }   -- --amber
local COIN_SILVER = { 0.78, 0.93, 1 }     -- pale cyan-white
local COIN_COPPER = { 1, 0.42, 0.55 }     -- warm pink

-- DataBar.lua types these inline: the rails and dividers are COLOR_POWER at these alphas, the meter edge at the second.
local RAIL_ALPHA, DIVIDER_ALPHA, METER_EDGE_ALPHA = 0.8, 0.5, 0.40
local LABEL_SIZE, VALUE_SIZE = 9, 11
local GLOW_ROUND = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\glow_round.tga"

-- The band's own layout: the PREVIEW tag row, the gap to the bar, the room under it. The meter shrinks to this width before
-- the segment clips it (the real bar is a whole screen wide and never has to).
local TITLE_H = 20
local TITLE_GAP = 8
local PAD_BOTTOM = 4
local BAND_H = TITLE_H + TITLE_GAP + BAR_HEIGHT + PAD_BOTTOM
local METER_MIN_W = 16
local STAGE_FILL = { 0.075, 0.035, 0.14, 1 }   -- what the plates preview stands on

local WHITE = Theme.COLOR_TEXT_WHITE or { 1, 1, 1, 1 }
local COIN_COLORS = { COIN_GOLD, COIN_SILVER, COIN_COPPER }

-- What each segment reads in the sample: its text and, for the ones with a meter, the fraction; `cyan` is the lit value
-- (rested XP banked), `solid` a meter that does not take the gradient (bags), `coins` the three amounts of money.
local SAMPLE = {
    fps = { value = "118" },
    mem = { value = "2.1M", meter = 0.12 },
    cpu = { value = "0.1%" },
    latency = { value = "24" },
    rested = { value = "62%", meter = 0.62, cyan = true },
    durability = { value = "87%", meter = 0.87 },
    bags = { value = "18/32", meter = 0.44, solid = METER_FILL_LEFT },
    time = { value = "9:14 PM" },
    gold = { coins = { "12", "40", "7" } },
    rep = { value = "Thunder", meter = 0.40 },
    prof = { value = "BS 142  MIN 150" },
}
local SAMPLE_OTHER = { value = "--" }

local function Fill(frame, color, layer, sub)
    local t = frame:CreateTexture(nil, layer or "BACKGROUND", nil, sub)
    t:SetColorTexture(color[1], color[2], color[3], color[4] or 1)
    return t
end

-- One segment of the band, built once for a key and seated by Seat every render.
local function NewSegment(rec)
    local cyan = Theme.COLOR_POWER
    local frame = CreateFrame("Frame", nil, rec.bar)
    if frame.SetClipsChildren then frame:SetClipsChildren(true) end
    local seg = { frame = frame, coins = {} }
    seg.divider = Fill(frame, { cyan[1], cyan[2], cyan[3], DIVIDER_ALPHA }, "OVERLAY")
    seg.divider:SetWidth(DIVIDER_WIDTH)
    seg.divider:SetPoint("TOPLEFT", frame, "TOPLEFT", 0, 0)
    seg.divider:SetPoint("BOTTOMLEFT", frame, "BOTTOMLEFT", 0, 0)
    seg.label = frame:CreateFontString(nil, "OVERLAY")
    Theme.ApplyFontGeneric(seg.label, Theme.FONT_ORBITRON, LABEL_SIZE, cyan)
    if seg.label.SetWordWrap then seg.label:SetWordWrap(false) end
    seg.value = frame:CreateFontString(nil, "OVERLAY")
    Theme.ApplyMono(seg.value, VALUE_SIZE, WHITE)
    seg.track = CreateFrame("Frame", nil, frame)
    seg.track:SetHeight(METER_HEIGHT)
    Fill(seg.track, METER_TRACK_FILL, "BACKGROUND"):SetAllPoints(seg.track)
    I.Outline(seg.track, cyan, METER_EDGE_ALPHA)
    seg.fill = seg.track:CreateTexture(nil, "ARTWORK")
    seg.fill:SetPoint("TOPLEFT", seg.track, "TOPLEFT", 1, -1)
    for k = 1, 3 do
        local color = COIN_COLORS[k]
        local icon = frame:CreateTexture(nil, "OVERLAY")
        icon:SetTexture(GLOW_ROUND)
        if icon.SetBlendMode then icon:SetBlendMode("ADD") end
        icon:SetVertexColor(color[1], color[2], color[3], 1)
        icon:SetSize(COIN_SIZE, COIN_SIZE)
        local text = frame:CreateFontString(nil, "OVERLAY")
        Theme.ApplyMono(text, VALUE_SIZE, color)
        text:SetPoint("LEFT", icon, "RIGHT", COIN_TEXT_GAP, 0)
        seg.coins[k] = { icon = icon, text = text }
    end
    return seg
end

-- The meter's fill: the green to cyan gradient where the client has SetGradient, a flat cyan where it does not.
local function PaintFill(fill, solid)
    local right = Theme.COLOR_POWER
    if solid then
        fill:SetColorTexture(solid[1], solid[2], solid[3], 1)
    elseif fill.SetGradient and CreateColor then
        fill:SetColorTexture(1, 1, 1, 1)
        fill:SetGradient("HORIZONTAL", CreateColor(METER_FILL_LEFT[1], METER_FILL_LEFT[2], METER_FILL_LEFT[3], 1),
            CreateColor(right[1], right[2], right[3], 1))
    else
        fill:SetColorTexture(right[1], right[2], right[3], 1)
    end
end

-- Seats one segment in its slot [x, x + w): the divider (not on the first), the title (hidden when empty, the body then
-- starts at PAD_X), then the meter and value, the value alone, or the coins.
local function Seat(seg, row, index, x, w)
    local frame = seg.frame
    local sample = SAMPLE[row.key] or SAMPLE_OTHER
    frame:ClearAllPoints()
    frame:SetPoint("TOPLEFT", seg.bar, "TOPLEFT", x, 0)
    frame:SetSize(w, BAR_HEIGHT)
    frame:Show()
    seg.divider:SetShown(index > 1)

    local title = type(row.title) == "string" and row.title or ""
    local hasTitle = title ~= ""
    seg.label:SetText(title)
    seg.label:ClearAllPoints()
    seg.label:SetPoint("LEFT", frame, "LEFT", PAD_X, 0)
    seg.label:SetShown(hasTitle)
    local from, point, gap = frame, "LEFT", PAD_X
    if hasTitle then from, point, gap = seg.label, "RIGHT", LABEL_GAP end

    local showValue = sample.value ~= nil
    seg.value:SetShown(showValue)
    if showValue then
        seg.value:SetText(sample.value)
        local c = sample.cyan and Theme.COLOR_POWER or WHITE
        seg.value:SetTextColor(c[1], c[2], c[3], 1)
    end

    seg.track:SetShown(sample.meter ~= nil)
    if sample.meter then
        local used = hasTitle and (PAD_X + (seg.label:GetStringWidth() or 0) + LABEL_GAP) or PAD_X
        local room = w - used - LABEL_GAP - (seg.value:GetStringWidth() or 0) - 2
        local meterW = math.max(METER_MIN_W, math.min(METER_WIDTH, math.floor(room)))
        seg.track:SetWidth(meterW)
        seg.track:ClearAllPoints()
        seg.track:SetPoint("LEFT", from, point, gap, 0)
        local inner = math.max(0, math.floor((meterW - 2) * sample.meter + 0.5))
        seg.fill:SetSize(math.max(1, inner), METER_HEIGHT - 2)
        PaintFill(seg.fill, sample.solid)
        seg.value:ClearAllPoints()
        seg.value:SetPoint("LEFT", seg.track, "RIGHT", LABEL_GAP, 0)
    elseif showValue then
        seg.value:ClearAllPoints()
        seg.value:SetPoint("LEFT", from, point, gap, 0)
    end

    for k, coin in ipairs(seg.coins) do
        local amount = sample.coins and sample.coins[k]
        coin.icon:SetShown(amount ~= nil)
        coin.text:SetShown(amount ~= nil)
        if amount then
            coin.text:SetText(amount)
            coin.icon:ClearAllPoints()
            if k == 1 then
                coin.icon:SetPoint("LEFT", from, point, gap, 0)
            else
                coin.icon:SetPoint("LEFT", seg.coins[k - 1].text, "RIGHT", COIN_GROUP_GAP, 0)
            end
        end
    end
end

-- Draws the bar from the model: only the segments that are on, in order, sharing the width in whole units.
local function Render(rec)
    local shown = {}
    for _, row in ipairs(rec.list) do
        if row.on then shown[#shown + 1] = row end
    end
    local count = #shown
    rec.count:SetText(count .. " SHOWN")
    for _, seg in pairs(rec.segs) do seg.frame:Hide() end
    local width = D.CONTENT_W
    for index, row in ipairs(shown) do
        local seg = rec.segs[row.key]
        if not seg then
            seg = NewSegment(rec)
            seg.bar = rec.bar
            rec.segs[row.key] = seg
        end
        local x0 = math.floor((index - 1) * width / count)
        local x1 = math.floor(index * width / count)
        Seat(seg, row, index, x0, x1 - x0)
    end
end

-- The band on top of the tab: the PREVIEW tag with its ?, how many segments show, the bar.
local function BuildBand(content, rec)
    local band = UI.Band(content, BAND_H)
    if not band then return false end
    local title = I.Label(band, "PREVIEW", S.SMALL, C.muted)
    title:SetPoint("TOPLEFT", band, "TOPLEFT", 0, -4)
    local icon = UI.HelpIcon(band, PREVIEW_TIP)
    icon:SetPoint("LEFT", title, "RIGHT", S.Q_GAP, 0)
    rec.count = I.Label(band, "", S.SMALL, C.muted)
    rec.count:SetPoint("TOPRIGHT", band, "TOPRIGHT", 0, -4)
    rec.count:SetJustifyH("RIGHT")

    local bar = CreateFrame("Frame", nil, band)
    bar:SetPoint("TOPLEFT", band, "TOPLEFT", 0, -(TITLE_H + TITLE_GAP))
    bar:SetPoint("TOPRIGHT", band, "TOPRIGHT", 0, -(TITLE_H + TITLE_GAP))
    bar:SetHeight(BAR_HEIGHT)
    Fill(bar, STAGE_FILL, "BACKGROUND"):SetAllPoints(bar)
    local bg = Theme.COLOR_BG
    Fill(bar, bg, "BACKGROUND", 1):SetAllPoints(bar)
    local cyan = Theme.COLOR_POWER
    for _, edge in ipairs({ "TOP", "BOTTOM" }) do
        local rail = Fill(bar, { cyan[1], cyan[2], cyan[3], RAIL_ALPHA }, "BORDER")
        rail:SetPoint(edge .. "LEFT", bar, edge .. "LEFT", 0, 0)
        rail:SetPoint(edge .. "RIGHT", bar, edge .. "RIGHT", 0, 0)
        rail:SetHeight(1)
    end
    rec.band, rec.bar, rec.segs = band, bar, {}
    band:SetScript("OnSizeChanged", function() Render(rec) end)
    return true
end

-------------------------------------------------------------------------------
-- The rows
-------------------------------------------------------------------------------

-- A tooltip for a small control: the text, at the right of it. A disabled control says nothing.
local function Hint(button, text)
    button:HookScript("OnEnter", function(self)
        if not self:IsEnabled() then return end
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetText(text, 1, 1, 1, 1, true)
        GameTooltip:Show()
    end)
    button:HookScript("OnLeave", function() GameTooltip:Hide() end)
end

-- What UI.Order does not do on its own. `edit` is the title box.
--   * typing renames the title on the bar at once (userInput only: the refresh that puts text back is not a keystroke)
--   * focus: the box shows a cyan edge, selects its text, and is the one box with the keyboard (I.SliderFocused: a click
--     anywhere else, a click on the window and hiding the window let go of it); Enter and Esc are UI.Order's, Tab leaves too,
--     and so does the box hiding (another page, another tab)
--   * letting go refreshes, so the box shows the title as stored (cut to ten, bars and control characters gone)
--   * the ON / OFF word, the changed dot and reset, hints on the arrows
--   * the switch is disabled while the model says `lock` (the last one on, or a segment this client cannot show) and the
--     title box follows the row's state
local function Dress(row, rec, key)
    local Seg = rec.Seg
    local edit, up, down, toggle = row.fsTitleBox, row.fsUp, row.fsDown, row.control
    local holder = edit:GetParent()

    local state = I.Label(row, "OFF", S.SMALL, C.line)
    state:SetWidth(S.STATE_W)
    state:SetJustifyH("RIGHT")
    state:SetPoint("RIGHT", toggle, "LEFT", -S.CTL_GAP, 0)
    down:ClearAllPoints()
    down:SetPoint("RIGHT", state, "LEFT", -S.CTL_GAP, 0)

    local edges = I.Outline(holder, C.cyan, 1)
    for _, edge in ipairs(edges) do edge:Hide() end
    edit:HookScript("OnTextChanged", function(self, userInput)
        if userInput then Seg.SetTitle(key, self:GetText()) end
    end)
    edit:HookScript("OnEditFocusGained", function(self)
        for _, edge in ipairs(edges) do edge:Show() end
        self:HighlightText()
        I.SliderFocused(self)
    end)
    edit:HookScript("OnEditFocusLost", function(self)
        for _, edge in ipairs(edges) do edge:Hide() end
        self:HighlightText(0, 0)
        I.SliderFocused(nil, self)
        CW.RefreshAll()
    end)
    edit:HookScript("OnHide", function(self) self:ClearFocus() end)
    edit:SetScript("OnTabPressed", function(self) self:ClearFocus() end)
    row.fsReleaseFocus = function() edit:ClearFocus() end

    Hint(up, "Move left")
    Hint(down, "Move right")

    I.AttachChanged(row, holder)

    I.Track(function()
        local r = rec.byKey[key]
        local on = r ~= nil and r.on == true
        state:SetText(on and "ON" or "OFF")
        Theme.ApplyMono(state, S.SMALL, on and C.cyan or C.line)
        if r and r.lock then
            toggle:Disable()
            toggle:SetAlpha(0.4)
        end
        local usable = I.Writable() and not I.RowOff(edit)
        edit:SetEnabled(usable)
        if not usable then edit:ClearFocus() end
        holder:SetAlpha(usable and 1 or 0.4)
    end)
end

local function SegmentRow(content, rec, m)
    local Seg, Config = rec.Seg, FS.Config
    local key = m.key
    local switchKey, titleKey = Seg.SwitchKey(key), Seg.TitleKey(key)
    local function now() return rec.byKey[key] end
    local o
    o = {
        label = m.label, tip = m.tip, regKey = switchKey, maxLetters = Seg.TITLE_MAX, reason = m.reason or "",
        get = function()
            local r = now()
            return r ~= nil and r.on == true
        end,
        set = function(on) return (Seg.SetEnabled(key, on == true)) end,
        getTitle = function()
            local r = now()
            return r and r.title or ""
        end,
        setTitle = function(text) Seg.SetTitle(key, text) end,
        canUp = function()
            local r = now()
            return r ~= nil and r.canUp == true
        end,
        canDown = function()
            local r = now()
            return r ~= nil and r.canDown == true
        end,
        onUp = function() Seg.Move(key, -1) end,
        onDown = function() Seg.Move(key, 1) end,
        -- The row is off while this client cannot show the segment; its reason (and, for the last switch on, the lock
        -- sentence) go into the ? tip. UI.Order reads `reason` and `tip` right after this runs, so they are set here.
        enabled = function()
            local r = now()
            if not r then return false end
            o.reason = r.reason or o.reason
            o.tip = (r.available and r.lock) and (r.tip .. "\n" .. r.lock) or r.tip
            return r.available == true
        end,
        isChanged = function() return Config.IsStored(switchKey) or Config.IsStored(titleKey) end,
        reset = function()
            Config.Set(switchKey, nil)
            Config.Set(titleKey, nil)
        end,
    }
    local row = UI.Order(content, o)
    Dress(row, rec, key)
    return row
end

-- The order is one setting for the whole list, so it gets one registry entry of its own, on the section header: the changed
-- count, the page reset and the search all see it, and no row shows a dot for a neighbour having moved.
local function RegisterOrder(sec, rec)
    local Seg, Config = rec.Seg, FS.Config
    if not (sec and sec.header and I.Register) then return end
    I.Register(sec.header, {
        regKey = Seg.ORDER_KEY, label = ORDER_LABEL,
        isChanged = function() return Config.IsStored(Seg.ORDER_KEY) end,
        reset = function() Seg.SetOrder(nil) end,
    }, "order")
end

-- The rows were built in the order the bar had then; after a move they stand in the bar's order again. The rows keep their
-- own frames (and keys, registry entries, tips); only their places in the tab's flow change.
local function SeatRows(content, rec)
    local owner = I.FlowOwner(content)
    local flow = owner and owner.fsFlow
    if not flow then return end
    local mine = {}
    for _, row in pairs(rec.rows) do mine[row] = true end
    local slots = {}
    for index, item in ipairs(flow) do
        if mine[item.frame] then slots[#slots + 1] = index end
    end
    local want = {}
    for _, r in ipairs(rec.list) do
        local row = rec.rows[r.key]
        if row and row.fsItem then want[#want + 1] = row.fsItem end
    end
    if #want ~= #slots then return end
    local moved = false
    for k, index in ipairs(slots) do
        if flow[index] ~= want[k] then
            flow[index] = want[k]
            moved = true
        end
    end
    if moved then
        I.Reflow(owner)
        CW.RefreshScroll()
    end
end

local function Build(content)
    local Seg = FS.DataBarSegments
    if not (Seg and Seg.Model and Seg.SetEnabled and Seg.Move and Seg.SetTitle) then
        UI.Note(content, NOT_LOADED)
        return
    end
    local rec = { Seg = Seg, list = {}, byKey = {}, rows = {} }
    -- One model read per refresh pass, before any row reads it (states run ahead of the controls).
    local function Fresh()
        local ok, list = pcall(Seg.Model)
        if not (ok and type(list) == "table") then
            I.Forward(list)
            return
        end
        rec.list, rec.byKey = list, {}
        for _, row in ipairs(list) do rec.byKey[row.key] = row end
    end
    Fresh()
    I.TrackState(Fresh)

    if BuildBand(content, rec) then I.Track(function() Render(rec) end) end
    local sec = UI.Section(content, { title = "Segments", tip = SEGMENTS_TIP })
    for _, m in ipairs(rec.list) do rec.rows[m.key] = SegmentRow(content, rec, m) end
    RegisterOrder(sec, rec)
    I.Track(function() SeatRows(content, rec) end)
end

CW.RegisterCategory({
    key = "data", label = "Data bar", group = "PANELS", order = 5,
    tabs = { { key = "g", label = "Segments", build = Build } },
})
