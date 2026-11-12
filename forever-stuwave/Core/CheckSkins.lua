-- Forever STUwave: CheckSkins
-- The checkbox and the radio of the shared controls kit (mockups/shared-controls-2026-11-12.html, section 2).
--
-- A checkbox is a breaker: a 16 px cut box (chamfer 4, top left and bottom right) that, switched on, takes a pink 2 px
-- edge on the pink wash, lights a 3 px power LED in its corner that breathes, and draws its tick in stroke by stroke. A
-- radio is a 16 px rhombus, so the two never read alike: the selection is a 6 px node, the rhombus's pink ring grows
-- out of it in a loop, and the options of one group hang on a thin rail the node jumps along.
--
--   off      ink face, 1 px dim violet edge            hover    the edge turns cyan, a cyan LED stub (check)
--   on       pink wash, 2 px pink edge, pink mark      on+hover the 2 px edge turns cyan
--   disabled darkest ink, 1 px dim edge, no LED        disabled on   the mark stays, in the disabled grey
--
-- Skin only. The stock CheckButton keeps its rect, its scripts and its checked state; its art (normal, pushed,
-- highlight, checked, disabled checked) is held at alpha 0 (FS.HeldArt) and our plate, a child frame centred in the stock
-- rect, draws over it. We follow the widget by post-hooks (OnEnter, OnLeave, OnMouse*, OnEnable, OnDisable, OnShow,
-- OnSizeChanged, SetChecked, Enable, Disable). The label is restyled to the kit's mono (12 px, #e9e2ff; #5c5480 when
-- disabled). Nothing here resizes or reparents a Blizzard frame.
--
-- Told by shape, never by name: a CheckButton with a checked texture, no icon, count, cooldown or hot key (so not an action
-- or item button) and no larger than a checkbox (so not a list row). The radio is the one whose textures say radio or
-- radial, or the small one with a lower case `text` label (UIRadioButtonTemplate, whose label key is `text`).
-- UICheckButtonTemplate, OptionsBaseCheckButtonTemplate, MinimalCheckboxTemplate and UIRadioButtonTemplate are XML
-- templates, never globals, so the 16001 globals dump cannot confirm them; their shapes are read from the 12.1.0
-- Blizzard_SharedXML source and detected at runtime.

local _, FS = ...

local Theme, HeldArt, Kit = FS.Theme, FS.HeldArt, FS.ControlKit
if not (Theme and HeldArt and Kit and FS.Layout and FS.Layout.Controls and Theme.COLOR_CTRL_INK) then return end

local CheckSkins = {}
FS.CheckSkins = CheckSkins

local K = FS.Layout.Controls
local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local DIAMOND_FILL, DIAMOND_RING1, DIAMOND_RING2 = MEDIA .. "ctl_diamond_fill.tga", MEDIA .. "ctl_diamond_ring1.tga",
    MEDIA .. "ctl_diamond_ring2.tga"
local NODE, TICK = MEDIA .. "ctl_diamond_node.tga", MEDIA .. "ctl_tick.tga"

local C = {
    ink = Theme.COLOR_CTRL_INK, dim = Theme.COLOR_CTRL_DIM, sel = Theme.COLOR_CTRL_SEL, dis = Theme.COLOR_CTRL_DIS,
    disFill = Theme.COLOR_CTRL_DISFILL, disEdge = Theme.COLOR_CTRL_DISEDGE, text = Theme.COLOR_CTRL_TEXT,
    pink = Theme.COLOR_HEALTH, cyan = Theme.COLOR_POWER, violet = Theme.COLOR_BORDER,
}

local LABEL_PX = 12
local MAX_BOX = 40       -- a checkbox is never larger than this on either side, in UI units
local MAX_SKEW = 8       -- and never more than this far from square
local RADIO_MAX = 20     -- the small square a UIRadioButtonTemplate is (16 x 16, a radial one 18 x 18)

local parts = setmetatable({}, { __mode = "k" })    -- widget -> what we drew on it
local chosen = setmetatable({}, { __mode = "k" })   -- parent -> the radio last switched on there

-------------------------------------------------------------------------------
-- Detection
-------------------------------------------------------------------------------

local function Region(widget, getter)
    local fn = widget[getter]
    if type(fn) ~= "function" then return nil end
    local ok, region = pcall(fn, widget)
    if ok and type(region) == "table" then return region end
    return nil
end

local function SizeOf(widget)
    local w, h = Kit.Plain(Kit.Try(widget.GetWidth, widget)), Kit.Plain(Kit.Try(widget.GetHeight, widget))
    if type(w) == "number" and type(h) == "number" then return w, h end
    return nil, nil
end

-- True when a texture's file or atlas names a radio.
local function NamesRadio(region)
    if not region then return false end
    for _, getter in ipairs({ "GetTexture", "GetAtlas" }) do
        local value = Kit.Try(region[getter], region)
        if type(value) == "string" then
            value = value:lower()
            if value:find("radio", 1, true) or value:find("radial", 1, true) then return true end
        end
    end
    return false
end

-- "check", "radio" or nil.
function CheckSkins.Kind(widget)
    if Kit.TypeOf(widget) ~= "CheckButton" then return nil end
    if widget.icon or widget.Icon or widget.IconTexture or widget.Count or widget.cooldown or widget.Cooldown
        or widget.HotKey or widget.hotKey then return nil end
    if not Region(widget, "GetCheckedTexture") then return nil end
    local w, h = SizeOf(widget)
    if not w or w > MAX_BOX or h > MAX_BOX or math.abs(w - h) > MAX_SKEW then return nil end
    if NamesRadio(Region(widget, "GetNormalTexture")) or NamesRadio(Region(widget, "GetCheckedTexture")) then return "radio" end
    if w <= RADIO_MAX and h <= RADIO_MAX and type(widget.text) == "table" and widget.Text == nil then return "radio" end
    return "check"
end

function CheckSkins.Parts(widget) return parts[widget] end

local function LabelOf(widget)
    local label = widget.Text or widget.text
    if type(label) == "table" and Kit.TypeOf(label) == "FontString" then return label end
    local name = Kit.Try(widget.GetName, widget)
    if type(name) == "string" then
        label = _G[name .. "Text"]
        if type(label) == "table" and Kit.TypeOf(label) == "FontString" then return label end
    end
    return nil
end

-------------------------------------------------------------------------------
-- State
-------------------------------------------------------------------------------

local function IsChecked(widget)
    local v = Kit.Plain(Kit.Try(widget.GetChecked, widget))
    return v ~= nil and v ~= false and v ~= 0
end

local SQRT1_2 = math.sqrt(0.5)
local TICK_SEG1, TICK_SEG2 = 3 * math.sqrt(2), 5 * math.sqrt(2)

-- How far along the tick's x axis a draw-in of fraction f (0 to 1 of the polyline's length) has reached, in box pixels.
local function TickReveal(f)
    if f >= 1 then return K.CHECK end
    local s = f * (TICK_SEG1 + TICK_SEG2)
    local x = s <= TICK_SEG1 and 3 + s * SQRT1_2 or 6 + (s - TICK_SEG1) * SQRT1_2
    return math.min(K.CHECK, x + 1) -- the stroke is 2 wide, so the leading edge is a pixel past the axis
end

local function ShowTick(p, f)
    local x = TickReveal(f)
    if f <= 0 then
        p.tick:Hide()
        return
    end
    p.tick:SetTexCoord(0, x / K.CHECK, 0, 1)
    Kit.Move(p.tick, 0, 0, x, K.CHECK)
    p.tick:Show()
end

local function StartDrawIn(p)
    ShowTick(p, 0)
    Kit.Animate(p.plateFrame, "tick", function(_, elapsed)
        local f = math.min(1, elapsed / K.TICK_DRAW)
        ShowTick(p, f)
        if f >= 1 then Kit.StopAnimate(p.plateFrame, "tick") end
    end)
end

local function StartLed(p, color)
    Kit.Animate(p.plateFrame, "led", function(_, elapsed)
        local a = Kit.Pulse(elapsed, K.LED_PULSE, K.LED_FLOOR)
        p.led:SetColorTexture(color[1], color[2], color[3], a)
    end)
end

local function StartRing(p)
    Kit.Animate(p.plateFrame, "ring", function(_, elapsed)
        local t = (elapsed % K.RING_PERIOD) / K.RING_PERIOD
        local e = Kit.Ease.outQuad(t)
        local s = K.RING_FROM + (K.RING_TO - K.RING_FROM) * e
        local size = K.CHECK * s
        Kit.Move(p.ring, K.CHECK / 2 - size / 2, K.CHECK / 2 - size / 2, size, size)
        p.ring:SetVertexColor(C.pink[1], C.pink[2], C.pink[3], K.RING_ALPHA * (1 - e))
    end)
end

local function Stop(p)
    Kit.StopAnimate(p.plateFrame, "led")
    Kit.StopAnimate(p.plateFrame, "tick")
    Kit.StopAnimate(p.plateFrame, "ring")
    Kit.StopAnimate(p.plateFrame, "slide")
end

-- The vertical distance in pixels from `widget`'s centre up to `other`'s (positive when `other` is above), nil unknown.
local function CentreDelta(widget, other)
    local a, b = Kit.Plain(Kit.Try(widget.GetTop, widget)), Kit.Plain(Kit.Try(other.GetTop, other))
    if type(a) ~= "number" or type(b) ~= "number" then return nil end
    return (b - a) * Kit.Ppu(widget)
end

local function SlideNode(widget, p, fromWidget)
    local delta = CentreDelta(widget, fromWidget)
    if not delta or math.abs(delta) < 1 then return end
    local base = K.NODE_OFFSET
    Kit.Animate(p.plateFrame, "slide", function(_, elapsed)
        local f = math.min(1, elapsed / K.NODE_SLIDE)
        Kit.Move(p.node, base, base - delta * (1 - Kit.Ease.outQuad(f)), K.NODE, K.NODE)
        if f >= 1 then Kit.StopAnimate(p.plateFrame, "slide") end
    end)
end

local function PaintCheck(widget, p, st)
    local on, enabled, lit = st.on, st.enabled, st.hover or st.pressed
    local fill, edge, px, mark = C.ink, C.dim, 1, nil
    if not enabled then
        fill, edge = C.disFill, C.disEdge
        if on then mark = C.dis end
    elseif on then
        fill, edge, px, mark = C.sel, lit and C.cyan or C.pink, 2, C.pink
    elseif lit then
        edge = C.cyan
    end
    Kit.PaintPlate(p.plate, fill, 1, edge, 1, px)

    -- the mark: drawn in when it first lights, held when it was already on
    if mark then
        p.tick:SetVertexColor(mark[1], mark[2], mark[3], 1)
        if not p.wasOn and p.seen and enabled and widget:IsVisible() then
            StartDrawIn(p)
        elseif not Kit.IsAnimating(p.plateFrame, "tick") then
            ShowTick(p, 1)
        end
    else
        Kit.StopAnimate(p.plateFrame, "tick")
        p.tick:Hide()
    end

    -- the LED: a breathing pink one while on, a cyan stub under the hand, none otherwise
    if enabled and on then
        p.led:Show()
        if not Kit.IsAnimating(p.plateFrame, "led") then StartLed(p, C.pink) end
    else
        Kit.StopAnimate(p.plateFrame, "led")
        if enabled and lit then
            p.led:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], K.HOVER_LED_ALPHA)
            p.led:Show()
        else
            p.led:Hide()
        end
    end
end

local function PaintRadio(widget, p, st)
    local on, enabled, lit = st.on, st.enabled, st.hover or st.pressed
    local fill, edge, px, mark = C.ink, C.dim, 1, nil
    if not enabled then
        fill, edge = C.disFill, C.disEdge
        if on then mark = C.dis end
    elseif on then
        fill, edge, px, mark = C.sel, lit and C.cyan or C.pink, 2, C.pink
    elseif lit then
        edge = C.cyan
    end
    p.fill:SetVertexColor(fill[1], fill[2], fill[3], 1)
    p.ring1:SetVertexColor(edge[1], edge[2], edge[3], 1)
    p.ring2:SetVertexColor(edge[1], edge[2], edge[3], 1)
    p.ring1:SetShown(px == 1)
    p.ring2:SetShown(px == 2)

    if mark then
        p.node:SetVertexColor(mark[1], mark[2], mark[3], 1)
        p.node:Show()
        if not p.wasOn and p.seen and enabled then
            local parent = Kit.Try(widget.GetParent, widget)
            local from = parent and chosen[parent]
            if from and from ~= widget and parts[from] then SlideNode(widget, p, from) end
        end
    else
        Kit.StopAnimate(p.plateFrame, "slide")
        p.node:Hide()
    end
    if enabled and on then
        if not Kit.IsAnimating(p.plateFrame, "ring") then StartRing(p) end
        p.ring:Show()
        local parent = Kit.Try(widget.GetParent, widget)
        if parent then chosen[parent] = widget end
    else
        Kit.StopAnimate(p.plateFrame, "ring")
        p.ring:Hide()
    end
end

local function Paint(widget)
    local p = parts[widget]
    if not p or not p.built then return end
    local st = { on = IsChecked(widget), enabled = Kit.IsEnabled(widget), hover = p.state.hover, pressed = p.state.pressed }
    if p.kind == "radio" then PaintRadio(widget, p, st) else PaintCheck(widget, p, st) end
    p.wasOn, p.seen = st.on and st.enabled, true
    if p.label then Kit.Recolor(p.label, st.enabled and C.text or C.dis) end
end

-------------------------------------------------------------------------------
-- The radio's rail
-------------------------------------------------------------------------------

-- The radios of `widget`'s group: its siblings (same parent) that are skinned radios in the same column, top first.
local function GroupOf(widget)
    local parent = Kit.Try(widget.GetParent, widget)
    local left = Kit.Plain(Kit.Try(widget.GetLeft, widget))
    if not parent or type(left) ~= "number" or type(parent.GetChildren) ~= "function" then return { widget } end
    local ok, kids = pcall(function() return { parent:GetChildren() } end)
    if not ok then return { widget } end
    local ppu, list = Kit.Ppu(widget), {}
    for _, kid in ipairs(kids) do
        local other = parts[kid]
        local kidLeft = other and other.kind == "radio" and Kit.Plain(Kit.Try(kid.GetLeft, kid))
        if type(kidLeft) == "number" and math.abs(kidLeft - left) * ppu < 1.5
            and type(Kit.Plain(Kit.Try(kid.GetTop, kid))) == "number" then
            list[#list + 1] = kid
        end
    end
    table.sort(list, function(a, b) return Kit.Try(a.GetTop, a) > Kit.Try(b.GetTop, b) end)
    return list
end

-- The head of a group (its top radio) owns the rail: one pixel column through the diamond centres, behind them.
local function RefreshRail(widget)
    local p = parts[widget]
    if not (p and p.kind == "radio") then return end
    local group = GroupOf(widget)
    if #group > 1 and group[1] == widget then
        local last = group[#group]
        local span = CentreDelta(last, widget)
        if span and span > 0 then
            Kit.Move(p.rail, K.CHECK / 2, K.CHECK / 2, 1, math.floor(span + 0.5))
            p.rail:Show()
            return
        end
    end
    p.rail:Hide()
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

-- Seats the plate centred in the stock rect, on whole pixels.
local function Seat(widget)
    local p = parts[widget]
    if not p then return end
    local w, h = Kit.SizePx(widget)
    local x = w and math.floor((w - K.CHECK) / 2) or 0
    local y = h and math.floor((h - K.CHECK) / 2) or 0
    Kit.Move(p.plateFrame, x, y, K.CHECK, K.CHECK)
end

Kit.OnReseat(function()
    for widget in pairs(parts) do
        Seat(widget)
        RefreshRail(widget)
    end
end)

local function HoldArt(widget)
    HeldArt.HoldButton(widget)
    local function holdChecked()
        HeldArt.Hold(Region(widget, "GetCheckedTexture"))
        HeldArt.Hold(Region(widget, "GetDisabledCheckedTexture"))
        HeldArt.Hold(Region(widget, "GetHighlightTexture"))
    end
    holdChecked()
    HeldArt.HookSetters(widget, { "SetCheckedTexture", "SetDisabledCheckedTexture", "SetCheckedAtlas",
        "SetDisabledCheckedAtlas" }, holdChecked)
end

local function BuildCheck(widget, p)
    local frame = p.plateFrame
    p.plate = Kit.Plate(frame, K.CHECK_CUT, K.CHECK, K.CHECK)
    p.tick = Kit.Glyph(frame, TICK, 0, 0, K.CHECK, K.CHECK, C.pink, 1, "OVERLAY", 1)
    p.tick:Hide()
    p.led = Kit.Rect(frame, K.LED_X, K.LED_Y, K.LED, K.LED, C.pink, 1, "OVERLAY", 2)
    p.led:Hide()
end

local function BuildRadio(widget, p)
    local frame = p.plateFrame
    local function diamond(path, layer, sub, color)
        return Kit.Glyph(frame, path, 0, 0, K.CHECK, K.CHECK, color, 1, layer, sub)
    end
    p.rail = Kit.Rect(frame, K.CHECK / 2, K.CHECK / 2, 1, 1, C.violet, K.RAIL_ALPHA, "BACKGROUND", -8)
    p.rail:Hide()
    p.ring = diamond(DIAMOND_RING1, "BACKGROUND", -7, C.pink)
    p.ring:Hide()
    p.fill = diamond(DIAMOND_FILL, "BACKGROUND", -6, C.ink)
    p.ring1 = diamond(DIAMOND_RING1, "BORDER", 1, C.dim)
    p.ring2 = diamond(DIAMOND_RING2, "BORDER", 1, C.pink)
    p.ring2:Hide()
    p.node = Kit.Glyph(frame, NODE, K.NODE_OFFSET, K.NODE_OFFSET, K.NODE, K.NODE, C.pink, 1, "OVERLAY", 1)
    p.node:SetTexCoord(0, K.NODE / 8, 0, K.NODE / 8)
    p.node:Hide()
end

local function Build(widget)
    local kind = CheckSkins.Kind(widget)
    if not kind then return end
    local p = { kind = kind }
    parts[widget] = p -- marked first, so a failure part way is not retried into a second plate

    HoldArt(widget)
    p.label = LabelOf(widget)
    if p.label then Kit.RestyleLabel(p.label, widget, LABEL_PX, C.text) end

    local frame = CreateFrame("Frame", nil, widget)
    p.plateFrame = frame
    Kit.Place(frame, widget, 0, 0, K.CHECK, K.CHECK, "TOPLEFT", "TOPLEFT", widget)
    Seat(widget)
    if kind == "radio" then BuildRadio(widget, p) else BuildCheck(widget, p) end
    p.built = true

    p.state = Kit.Track(widget, Paint)
    Kit.HookFunc(widget, "SetChecked", Paint)
    Kit.HookScript(widget, "OnClick", Paint)
    Kit.HookScript(widget, "OnSizeChanged", function()
        Seat(widget)
        RefreshRail(widget)
    end)
    Kit.HookScript(widget, "OnShow", function()
        Seat(widget)
        RefreshRail(widget)
    end)
    Paint(widget)
    Kit.Later(function() RefreshRail(widget) end)
end

-- Skins one stock check button or radio. Idempotent; returns true when it skinned now. A widget met in combat is skinned
-- when combat ends.
function CheckSkins.Skin(widget)
    if type(widget) ~= "table" or parts[widget] or not CheckSkins.Kind(widget) then return false end
    if type(InCombatLockdown) == "function" and InCombatLockdown() then
        Kit.Defer(function() CheckSkins.Skin(widget) end)
        return false
    end
    local ok, err = pcall(Build, widget)
    if not ok then Kit.Fail("check", err) end
    return ok and parts[widget] ~= nil
end

local function Match(kind)
    return function(widget) return CheckSkins.Kind(widget) == kind end
end

Kit.Register("check", { match = Match("check"), skin = CheckSkins.Skin, parts = CheckSkins.Parts })
Kit.Register("radio", { match = Match("radio"), skin = CheckSkins.Skin, parts = CheckSkins.Parts })
