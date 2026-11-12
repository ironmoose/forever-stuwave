-- Forever STUwave: SliderSkins
-- The slider of the shared controls kit (mockups/shared-controls-2026-11-12.html, section 3).
--
-- A slider is a cast bar you aim: a row of 6 x 8 cells on a pitch of 8 fills left to right, the lit ones violet with
-- 18 % white chevrons marching along them (one pitch every 0.6 s), the head cell cyan (pink while the thumb is held),
-- and the thumb is a pair of lock-on brackets around the head cell. Under the hand, or while dragged, the value floats
-- above the brackets in a cut tag with a 4 px stem, over a faint wash on the head cell. Disabled, the lit cells and the
-- brackets fall to the dim edge colour and nothing marches.
--
-- The stepper variant (MinimalSliderWithSteppersTemplate: a Slider between a Back and a Forward button) gets two 20 px
-- keys, a minus and a plus, centred on the stock buttons, and the track keeps its cells at least 8 px clear of them.
--
-- Skin only. The stock slider keeps its rect, its scripts, its value and its range: its art (the thumb, the track
-- pieces, the NineSlice frame of the labelled template) is held at alpha 0 (FS.HeldArt, Kit.HoldFrame), our cells and
-- brackets live on a child frame laid over the stock rect, and we follow it by post-hooks (OnValueChanged,
-- OnMinMaxChanged, OnEnter, OnLeave, OnMouse*, OnEnable, OnDisable, OnShow, OnSizeChanged, SetValue, SetMinMaxValues,
-- SetValueStep, Enable, Disable). Nothing here resizes, reparents or hides a Blizzard frame. A value the client hands
-- back is read through Kit.Plain, so a secret one reads as the start and shows no tag.
--
-- Told by shape: an object of type Slider that runs horizontally, has a thumb texture and is not a scroll bar. The keys
-- are the Back and Forward buttons of a frame whose `Slider` key is a slider. UISliderTemplate,
-- UISliderTemplateWithLabels, MinimalSliderTemplate and MinimalSliderWithSteppersTemplate are XML templates, never
-- globals, so the 16001 globals dump cannot confirm them; their shapes are read from the 12.1.0 Blizzard_SharedXML
-- source and detected at runtime.

local _, FS = ...

local Theme, HeldArt, Kit = FS.Theme, FS.HeldArt, FS.ControlKit
if not (Theme and HeldArt and Kit and FS.Layout and FS.Layout.Controls and Theme.COLOR_CTRL_INK) then return end

local SliderSkins = {}
FS.SliderSkins = SliderSkins

local K = FS.Layout.Controls
local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local CHEVRON = MEDIA .. "ctl_chevron_h8.tga"

local C = {
    ink = Theme.COLOR_CTRL_INK, dim = Theme.COLOR_CTRL_DIM, cell = Theme.COLOR_CTRL_CELL, dis = Theme.COLOR_CTRL_DIS,
    disFill = Theme.COLOR_CTRL_DISFILL, disEdge = Theme.COLOR_CTRL_DISEDGE, text = Theme.COLOR_CTRL_TEXT,
    pink = Theme.COLOR_HEALTH, cyan = Theme.COLOR_POWER, violet = Theme.COLOR_BORDER, muted = Theme.COLOR_MUTED,
}
local WHITE = { 1, 1, 1, 1 }

local parts = setmetatable({}, { __mode = "k" })     -- slider -> what we drew on it
local keyParts = setmetatable({}, { __mode = "k" })  -- stepper button -> what we drew on it

-- The text a stepper frame keeps beside its slider, and how each reads: a title, the value, an end label.
local FRAME_TEXT = {
    TopText = { px = K.LABEL_TEXT, color = C.text }, LeftText = { px = K.LABEL_TEXT, color = C.text },
    RightText = { px = K.LABEL_TEXT, color = C.cyan },
    MinText = { px = K.SMALL_TEXT, color = C.muted }, MaxText = { px = K.SMALL_TEXT, color = C.muted },
}

local function Round(v) return math.floor(v + 0.5) end

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

local function IsScrollBar(widget)
    if widget.ScrollUpButton or widget.ScrollDownButton then return true end
    local bars = FS.ScrollBarSkins
    return bars and bars.IsScrollBar and bars.IsScrollBar(widget) or false
end

-- "slider" or nil.
function SliderSkins.Kind(widget)
    if Kit.TypeOf(widget) ~= "Slider" then return nil end
    if Kit.Try(widget.GetOrientation, widget) ~= "HORIZONTAL" then return nil end
    if not Region(widget, "GetThumbTexture") or IsScrollBar(widget) then return nil end
    return "slider"
end

-- "minus", "plus" or nil: the Back and Forward buttons of a frame whose `Slider` is a slider.
function SliderSkins.KeyKind(widget)
    if Kit.TypeOf(widget) ~= "Button" then return nil end
    local parent = Kit.Try(widget.GetParent, widget)
    if type(parent) ~= "table" or Kit.TypeOf(parent.Slider) ~= "Slider" then return nil end
    if parent.Back == widget then return "minus" end
    if parent.Forward == widget then return "plus" end
    return nil
end

function SliderSkins.Parts(widget) return parts[widget] end
function SliderSkins.KeyParts(widget) return keyParts[widget] end

-------------------------------------------------------------------------------
-- Value
-------------------------------------------------------------------------------

-- value, min, max, step as plain numbers (nil for what the client will not say, or hides).
local function Read(widget)
    local value = Kit.Plain(Kit.Try(widget.GetValue, widget))
    local min, max = Kit.Try(widget.GetMinMaxValues, widget)
    min, max = Kit.Plain(min), Kit.Plain(max)
    local step = Kit.Plain(Kit.Try(widget.GetValueStep, widget))
    if type(value) ~= "number" then value = nil end
    if type(min) ~= "number" or type(max) ~= "number" then min, max = nil, nil end
    if type(step) ~= "number" then step = nil end
    return value, min, max, step
end

local function Fraction(value, min, max)
    if not (value and min and max) or max <= min then return 0 end
    local f = (value - min) / (max - min)
    if f < 0 then return 0 end
    if f > 1 then return 1 end
    return f
end

-- Digits after the point: the step's own (0.25 is two), or by the size of the range when it is continuous.
local function Decimals(step, min, max)
    if step and step > 0 then
        if step >= 1 then return 0 end
        local text = ("%.4f"):format(step):gsub("0+$", "")
        return math.min(3, #(text:match("%.(%d*)$") or ""))
    end
    local range = (min and max) and (max - min) or 100
    if range <= 1 then return 2 end
    if range <= 10 then return 1 end
    return 0
end

-- A range of 0 to 1 reads as a percent; anything else as a number to the digits its step has.
local function FormatValue(value, min, max, step)
    if min == 0 and max == 1 then return ("%d%%"):format(Round(value * 100)) end
    local pattern = "%." .. Decimals(step, min, max) .. "f"
    local text = pattern:format(value)
    if tonumber(text) == 0 then text = pattern:format(0) end -- never "-0.00"
    return text
end

local function Dragging(widget, p)
    if type(widget.IsDraggingThumb) == "function" and Kit.Plain(Kit.Try(widget.IsDraggingThumb, widget)) == true then
        return true
    end
    return p.state ~= nil and p.state.pressed or false
end

-------------------------------------------------------------------------------
-- Paint
-------------------------------------------------------------------------------

local function Paint(rect, color, alpha)
    rect:SetColorTexture(color[1], color[2], color[3], alpha or 1)
end

local function SeatBrackets(p)
    local hx, cy, b = p.hx, p.cy, p.brackets
    local sw = K.STROKE
    local arm = K.BRACKET_ARM + sw / 2
    local top = cy - K.BRACKET_HALF - sw / 2
    local tall = 2 * K.BRACKET_HALF + sw
    local bottom = cy + K.BRACKET_HALF - sw / 2
    local leftX = hx - K.BRACKET_SPINE - sw / 2
    local rightX = hx + K.BRACKET_SPINE - sw / 2
    local rightArmX = hx + K.BRACKET_SPINE - K.BRACKET_ARM
    Kit.Move(b.leftSpine, leftX, top, sw, tall)
    Kit.Move(b.leftTop, leftX, top, arm, sw)
    Kit.Move(b.leftBottom, leftX, bottom, arm, sw)
    Kit.Move(b.rightSpine, rightX, top, sw, tall)
    Kit.Move(b.rightTop, rightArmX, top, arm, sw)
    Kit.Move(b.rightBottom, rightArmX, bottom, arm, sw)
end

local function ApplyMarch(p)
    local phase = p.phase or 0
    p.chev:SetTexCoord(-phase, -phase + (p.chevW or 0) / K.CHEV_PITCH, 0, 1)
end

local function StartMarch(p)
    if Kit.IsAnimating(p.host, "march") then return end
    p.phase = 0
    ApplyMarch(p)
    Kit.Animate(p.host, "march", function(_, elapsed)
        p.phase = (elapsed % K.MARCH_PERIOD) / K.MARCH_PERIOD
        ApplyMarch(p)
    end)
end

local function ShowTag(p, accent, value, min, max, step)
    local tag = p.tag
    local text = FormatValue(value, min, max, step)
    if tag.text ~= text then
        tag.text = text
        tag.label:SetText(text)
    end
    local w = math.ceil((#text * K.TAG_CHAR + K.TAG_PAD) / K.TAG_ROUND - 1e-9) * K.TAG_ROUND
    Kit.Move(tag.frame, p.hx - w / 2, p.cy - K.TAG_TOP, w, K.TAG_H)
    Kit.Move(tag.label, w / 2, K.TAG_LABEL_Y)
    Kit.PaintPlate(tag.plate, C.ink, 1, accent, 1, 1)
    Kit.Recolor(tag.label, accent)
    Kit.Move(tag.stem, p.hx, p.cy - K.TAG_STEM_TOP, 1, K.TAG_STEM)
    Paint(tag.stem, accent)
    Kit.Move(p.wash, p.hx - K.WASH_W / 2, p.cy - K.WASH_H / 2, K.WASH_W, K.WASH_H)
    Paint(p.wash, accent, K.WASH_ALPHA)
    tag.frame:Show()
    tag.stem:Show()
    p.wash:Show()
end

local function HideTag(p)
    p.tag.frame:Hide()
    p.tag.stem:Hide()
    p.wash:Hide()
end

-- Repaints one slider from its value, range and state: the lit cells and the head, the brackets, the tag and the strip.
local function Update(widget)
    local p = parts[widget]
    if not (p and p.built and p.n) then return end
    local value, min, max, step = Read(widget)
    local lit = math.max(1, math.min(p.n, Round(Fraction(value, min, max) * p.n)))
    local enabled = Kit.IsEnabled(widget)
    local drag = enabled and Dragging(widget, p)
    local accent = (not enabled and C.disEdge) or (drag and C.pink) or C.cyan
    local body = enabled and C.violet or C.disEdge

    p.lit = lit
    for i = 1, p.n do
        local color = (i < lit and body) or (i == lit and accent) or C.cell
        if p.cellColor[i] ~= color then
            p.cellColor[i] = color
            Paint(p.cells[i], color)
        end
    end

    p.hx = p.x0 + (lit - 1) * K.CELL_PITCH + K.CELL_W / 2
    SeatBrackets(p)
    for _, rect in pairs(p.brackets) do Paint(rect, accent) end

    if enabled and value and (p.state.hover or drag) then ShowTag(p, accent, value, min, max, step) else HideTag(p) end

    -- the strip runs over the lit cells before the head, from the first cell to the right edge of the one before it
    if enabled and lit > 1 then
        p.chevW = (lit - 1) * K.CELL_PITCH - (K.CELL_PITCH - K.CELL_W)
        Kit.Move(p.chev, p.x0, p.cy - K.CELL_H / 2, p.chevW, K.CELL_H)
        p.chev:Show()
        if Kit.IsAnimating(p.host, "march") then ApplyMarch(p) else StartMarch(p) end
    else
        p.chev:Hide()
        Kit.StopAnimate(p.host, "march")
    end

    if p.title then Kit.Recolor(p.title, enabled and C.text or C.dis) end
end

-------------------------------------------------------------------------------
-- Layout
-------------------------------------------------------------------------------

-- How far in the track starts from each end of the stock rect: with stepper keys beside it, far enough that the key
-- plates (centred on their stock buttons, so wider than them) leave K.KEY_GAP before the first and after the last cell.
local function Insets(widget)
    local parent = Kit.Try(widget.GetParent, widget)
    if type(parent) ~= "table" or parent.Slider ~= widget then return 0, 0 end
    local ppu = Kit.Ppu(widget)
    local sliderLeft = Kit.Plain(Kit.Try(widget.GetLeft, widget))
    local sliderRight = Kit.Plain(Kit.Try(widget.GetRight, widget))
    if type(sliderLeft) ~= "number" or type(sliderRight) ~= "number" then return 0, 0 end

    -- the left edge, in pixels, of the key plate that sits on `button`
    local function keyLeft(button)
        if type(button) ~= "table" then return nil end
        local left = Kit.Plain(Kit.Try(button.GetLeft, button))
        local w = Kit.SizePx(button)
        if type(left) ~= "number" or not w then return nil end
        return left * ppu + math.floor((w - K.KEY) / 2)
    end

    local left, right = 0, 0
    local backLeft, forwardLeft = keyLeft(parent.Back), keyLeft(parent.Forward)
    if backLeft then left = math.max(0, K.KEY_GAP - (sliderLeft * ppu - (backLeft + K.KEY))) end
    if forwardLeft then right = math.max(0, K.KEY_GAP - (forwardLeft - sliderRight * ppu)) end
    return Round(left), Round(right)
end

local function Layout(widget)
    local p = parts[widget]
    if not (p and p.built) then return end
    local w, h = Kit.SizePx(widget)
    if not w then return end
    local left, right = Insets(widget)
    local avail = w - left - right
    local gap = K.CELL_PITCH - K.CELL_W
    local n = math.max(2, math.floor((avail + gap) / K.CELL_PITCH))
    local track = n * K.CELL_PITCH - gap
    p.n, p.x0, p.cy = n, left + math.floor((avail - track) / 2), math.floor(h / 2)
    for i = 1, n do
        local cell = p.cells[i]
        if not cell then
            cell = Kit.Rect(p.host, 0, 0, K.CELL_W, K.CELL_H, C.cell, 1, "ARTWORK", 0)
            p.cells[i] = cell
        end
        Kit.Move(cell, p.x0 + (i - 1) * K.CELL_PITCH, p.cy - K.CELL_H / 2, K.CELL_W, K.CELL_H)
        cell:Show()
    end
    for i = n + 1, #p.cells do p.cells[i]:Hide() end
    Update(widget)
end

Kit.OnReseat(function()
    for widget in pairs(parts) do Layout(widget) end
end)

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local function HoldArt(widget)
    HeldArt.HoldButton(widget)
    local function holdThumb() HeldArt.Hold(Region(widget, "GetThumbTexture")) end
    holdThumb()
    HeldArt.HookSetters(widget, { "SetThumbTexture" }, holdThumb)
    Kit.HoldFrame(widget.NineSlice)
end

local function RestyleText(widget)
    local p = parts[widget]
    p.title = widget.Text
    if type(p.title) == "table" then Kit.RestyleLabel(p.title, widget, K.LABEL_TEXT, C.text) else p.title = nil end
    for _, key in ipairs({ "Low", "High" }) do
        if type(widget[key]) == "table" then Kit.RestyleLabel(widget[key], widget, K.SMALL_TEXT, C.muted) end
    end
    local parent = Kit.Try(widget.GetParent, widget)
    if type(parent) == "table" and parent.Slider == widget then
        for key, look in pairs(FRAME_TEXT) do
            if type(parent[key]) == "table" then Kit.RestyleLabel(parent[key], widget, look.px, look.color) end
        end
    end
end

local function BuildBrackets(p)
    local function bracket() return Kit.Rect(p.host, 0, 0, 1, 1, C.cyan, 1, "OVERLAY", 1) end
    p.brackets = {
        leftSpine = bracket(), leftTop = bracket(), leftBottom = bracket(),
        rightSpine = bracket(), rightTop = bracket(), rightBottom = bracket(),
    }
end

local function BuildTag(p)
    local frame = CreateFrame("Frame", nil, p.host)
    local w = K.TAG_ROUND * 5
    Kit.Place(frame, p.host, 0, 0, w, K.TAG_H)
    local tag = { frame = frame, w = w }
    tag.plate = Kit.Plate(frame, K.TAG_CUT, w, K.TAG_H)
    tag.label = Kit.Label(frame, "", K.TAG_TEXT, C.cyan, "OVERLAY")
    Kit.Place(tag.label, frame, w / 2, K.TAG_LABEL_Y, nil, nil, "CENTER", "TOPLEFT")
    tag.stem = Kit.Rect(p.host, 0, 0, 1, K.TAG_STEM, C.cyan, 1, "OVERLAY", 2)
    frame:Hide()
    tag.stem:Hide()
    p.tag = tag
    p.wash = Kit.Rect(p.host, 0, 0, K.WASH_W, K.WASH_H, C.cyan, K.WASH_ALPHA, "OVERLAY", 0)
    p.wash:Hide()
end

local function BuildStrip(p)
    p.chev = Kit.Glyph(p.host, CHEVRON, 0, 0, K.CELL_PITCH, K.CELL_H, WHITE, K.CHEV_ALPHA, "OVERLAY", 0)
    p.chev:SetTexture(CHEVRON, "REPEAT", "REPEAT")
    p.chev:Hide()
end

local function Build(widget)
    local p = { widget = widget, cells = {}, cellColor = {} }
    parts[widget] = p -- marked first, so a failure part way is not retried into a second host

    HoldArt(widget)
    local host = CreateFrame("Frame", nil, widget)
    host:SetAllPoints(widget)
    p.host = host
    RestyleText(widget)
    BuildBrackets(p)
    BuildTag(p)
    BuildStrip(p)
    p.built = true

    p.state = Kit.Track(widget, Update)
    for _, script in ipairs({ "OnValueChanged", "OnMinMaxChanged" }) do Kit.HookScript(widget, script, Update) end
    for _, method in ipairs({ "SetValue", "SetMinMaxValues", "SetValueStep" }) do Kit.HookFunc(widget, method, Update) end
    local function relayout() Layout(widget) end
    Kit.HookScript(widget, "OnSizeChanged", relayout)
    Kit.HookScript(widget, "OnShow", relayout)
    Layout(widget)
    Kit.Later(relayout)
end

-- Skins one stock slider. Idempotent; returns true when it skinned now. A slider met in combat is skinned when combat
-- ends.
function SliderSkins.Skin(widget)
    if type(widget) ~= "table" or parts[widget] or not SliderSkins.Kind(widget) then return false end
    if type(InCombatLockdown) == "function" and InCombatLockdown() then
        Kit.Defer(function() SliderSkins.Skin(widget) end)
        return false
    end
    local ok, err = pcall(Build, widget)
    if not ok then Kit.Fail("slider", err) end
    return ok and parts[widget] ~= nil
end

-------------------------------------------------------------------------------
-- Stepper keys
-------------------------------------------------------------------------------

local function PaintKey(widget)
    local p = keyParts[widget]
    if not (p and p.built) then return end
    local fill, edge, glyph = C.ink, C.dim, C.muted
    if not Kit.IsEnabled(widget) then
        fill, edge, glyph = C.disFill, C.disEdge, C.dis
    elseif p.state.hover or p.state.pressed then
        edge, glyph = C.cyan, C.cyan
    end
    Kit.PaintPlate(p.plate, fill, 1, edge, 1, 1)
    Paint(p.bar, glyph)
    if p.upright then Paint(p.upright, glyph) end
end

-- Centres the 20 px key on the stock button, on whole pixels.
local function SeatKey(widget)
    local p = keyParts[widget]
    if not p then return end
    local w, h = Kit.SizePx(widget)
    Kit.Move(p.plateFrame, w and math.floor((w - K.KEY) / 2) or 0, h and math.floor((h - K.KEY) / 2) or 0, K.KEY, K.KEY)
end

Kit.OnReseat(function()
    for widget in pairs(keyParts) do SeatKey(widget) end
end)

local function BuildKey(widget)
    local kind = SliderSkins.KeyKind(widget)
    if not kind then return end
    local p = { kind = kind }
    keyParts[widget] = p

    HeldArt.HoldButton(widget)
    local frame = CreateFrame("Frame", nil, widget)
    p.plateFrame = frame
    Kit.Place(frame, widget, 0, 0, K.KEY, K.KEY, "TOPLEFT", "TOPLEFT", widget)
    SeatKey(widget)
    p.plate = Kit.Plate(frame, K.KEY_CUT, K.KEY, K.KEY)
    local bar = K.KEY_MINUS
    p.bar = Kit.Rect(frame, bar[1], bar[2], bar[3], bar[4], C.muted, 1, "OVERLAY", 1)
    if kind == "plus" then
        local upright = K.KEY_PLUS_UPRIGHT
        p.upright = Kit.Rect(frame, upright[1], upright[2], upright[3], upright[4], C.muted, 1, "OVERLAY", 1)
    end
    p.built = true

    p.state = Kit.Track(widget, PaintKey)
    local function reseat() SeatKey(widget) end
    Kit.HookScript(widget, "OnSizeChanged", reseat)
    Kit.HookScript(widget, "OnShow", reseat)
    PaintKey(widget)
end

function SliderSkins.SkinKey(widget)
    if type(widget) ~= "table" or keyParts[widget] or not SliderSkins.KeyKind(widget) then return false end
    if type(InCombatLockdown) == "function" and InCombatLockdown() then
        Kit.Defer(function() SliderSkins.SkinKey(widget) end)
        return false
    end
    local ok, err = pcall(BuildKey, widget)
    if not ok then Kit.Fail("slider key", err) end
    return ok and keyParts[widget] ~= nil
end

Kit.Register("slider", {
    match = function(widget) return SliderSkins.Kind(widget) ~= nil end,
    skin = SliderSkins.Skin, parts = SliderSkins.Parts,
})
Kit.Register("slider key", {
    match = function(widget) return SliderSkins.KeyKind(widget) ~= nil end,
    skin = SliderSkins.SkinKey, parts = SliderSkins.KeyParts,
})
