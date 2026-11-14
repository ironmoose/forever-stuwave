-- Forever STUwave: FieldSkins
-- The edit box and the search box of the shared controls kit (mockups/shared-controls-2026-11-12.html, section 4).
--
-- An edit box is a console line: an ink face with a dim violet 1 px edge and a cut corner at the top left and bottom
-- right, a 24 px prompt cell (a chevron, a rule at its edge) and the mono text 34 px in. Under the hand the edge goes cyan;
-- focused it also gets a faint 3 px glow, a block caret that blinks and a cyan LED underline that breathes. A search box
-- swaps the prompt for a lens, and while it has focus the lens becomes a radar: a ring, an inner ring, a sweep arm that
-- turns once every 1.6 s and a pink dot that breathes. A count chip ("7 found") sits in the right of a search box that has
-- a count source and some text; the clear key is a cross.
--
--   idle     ink face, 1 px dim edge, muted glyph         hover     the edge turns cyan
--   focus    cyan edge, glow, LED underline, caret        disabled  darkest ink, dim edge, dim text, no glow
--
-- Skin only. The stock box keeps its rect, its scripts, its text and its focus: its art (Left, Middle, Right, the search
-- icon, the clear key's icon) is held at alpha 0 (FS.HeldArt), our face and edge are regions of the box itself (under the
-- engine's text) sized in whole pixels, everything that sits over the text is on a child frame, and we follow the box by
-- post-hooks (OnEnter, OnLeave, OnEditFocusGained, OnEditFocusLost, OnTextChanged, OnCursorChanged, OnEnable, OnDisable,
-- OnShow, OnSizeChanged, Enable, Disable). The text is restyled to the kit's mono (12 px, #e9e2ff; #5c5480 disabled), the
-- placeholder to #6c6396, and the text insets are set so the text clears the prompt cell and the clear zone, as the Bags
-- search box already does. The caret is ours (the engine's own cannot be restyled): a block 7 x 14 at the cursor, solid
-- at the end of the line, dimmed over a glyph so the text stays readable, hidden where the text scrolls under the
-- engine's own caret. The text is read through Kit.Plain, so a secret one reads as empty.
--
-- Told by shape: an EditBox that is not multi-line, between FIELD_MIN_W by FIELD_MIN_H and FIELD_MAX_H in pixels, with the
-- Left, Middle and Right art of InputBoxTemplate, or a search icon or clear key (SearchBoxTemplate), or a placeholder
-- (InputBoxInstructionsTemplate); a box whose art something else already holds is that skin's. InputBoxTemplate,
-- SearchBoxTemplate, BagSearchBoxTemplate and InputBoxInstructionsTemplate are XML templates, never globals, so the 16001
-- globals dump cannot confirm them; their shapes are read from the 12.1.0 Blizzard_SharedXML source and detected at
-- runtime.
--
-- A text area (InputScrollFrameTemplate: a multi-line box inside a scroll frame, the report and macro bodies) is the same face without
-- the prompt cell, the LED and our caret: the engine's multi-line caret stays. Its nine Common-Input-Border pieces are held and our
-- face and edge reach AREA_PAD (5 units) past the frame, where the stock border sat; the scroll frame and the box inside it both
-- follow the hand, the box's focus lights the edge and the glow, and the text, the placeholder and the char count take the kit's
-- mono. Told by shape: a ScrollFrame with a multi-line EditBox and all nine border pieces, whose art nothing else holds.
--
-- The count chip needs a count: FieldSkins.SetCount(box, n) sets it by hand and FieldSkins.AddCountSource(fn) adds a
-- function fn(box) -> number or nil that is asked on every text change and on show. The collections journals (mounts, toys,
-- heirlooms) have one built in; every other search box shows no chip.

local _, FS = ...

local Theme, HeldArt, Kit = FS.Theme, FS.HeldArt, FS.ControlKit
if not (Theme and HeldArt and Kit and FS.Layout and FS.Layout.Controls and Theme.COLOR_CTRL_HAIR) then return end

local FieldSkins = {}
FS.FieldSkins = FieldSkins

local K = FS.Layout.Controls
local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local PROMPT, LENS, CROSS = MEDIA .. "ctl_prompt.tga", MEDIA .. "ctl_lens.tga", MEDIA .. "ctl_cross.tga"
local RADAR, ARM = MEDIA .. "ctl_radar.tga", MEDIA .. "ctl_radar_arm.tga"

local C = {
    ink = Theme.COLOR_CTRL_INK, dim = Theme.COLOR_CTRL_DIM, dis = Theme.COLOR_CTRL_DIS, disFill = Theme.COLOR_CTRL_DISFILL,
    disEdge = Theme.COLOR_CTRL_DISEDGE, text = Theme.COLOR_CTRL_TEXT, hair = Theme.COLOR_CTRL_HAIR,
    hint = Theme.COLOR_CTRL_HINT, pink = Theme.COLOR_HEALTH, cyan = Theme.COLOR_POWER, muted = Theme.COLOR_MUTED,
}
local HIGHLIGHT_ALPHA = 0.35

local parts = setmetatable({}, { __mode = "k" })       -- box -> what we drew on it
local crossParts = setmetatable({}, { __mode = "k" })  -- clear button -> its cross
local countSources = {}

local function Round(v) return math.floor(v + 0.5) end

-------------------------------------------------------------------------------
-- Detection
-------------------------------------------------------------------------------

local function IsTable(v) return type(v) == "table" end

-- True when something already holds this art at alpha 0.
local function Held(region)
    if not IsTable(region) then return false end
    return Kit.Plain(Kit.Try(region.GetAlpha, region)) == 0
end

-- "edit", "search" or nil.
function FieldSkins.Kind(widget)
    if Kit.TypeOf(widget) ~= "EditBox" then return nil end
    if Kit.Plain(Kit.Try(widget.IsMultiLine, widget)) == true then return nil end
    local w, h = Kit.SizePx(widget)
    if w and (w < K.FIELD_MIN_W or h < K.FIELD_MIN_H or h > K.FIELD_MAX_H) then return nil end
    local template = IsTable(widget.Left) and IsTable(widget.Middle) and IsTable(widget.Right)
    local search = IsTable(widget.searchIcon) or IsTable(widget.clearButton)
    if not (template or search or IsTable(widget.Instructions)) then return nil end
    if not parts[widget] and template and Held(widget.Left) then return nil end
    return search and "search" or "edit"
end

function FieldSkins.Parts(widget) return parts[widget] end
function FieldSkins.CrossParts(button) return crossParts[button] end

-------------------------------------------------------------------------------
-- Reading the box
-------------------------------------------------------------------------------

local function TextOf(widget)
    local text = Kit.Plain(Kit.Try(widget.GetDisplayText or widget.GetText, widget))
    if type(text) ~= "string" then
        text = Kit.Plain(Kit.Try(widget.GetText, widget))
    end
    return type(text) == "string" and text or ""
end

local function HasFocus(widget)
    return Kit.Plain(Kit.Try(widget.HasFocus, widget)) == true
end

local function IsShownNow(region)
    return IsTable(region) and Kit.Plain(Kit.Try(region.IsShown, region)) == true
end

-------------------------------------------------------------------------------
-- Count chip
-------------------------------------------------------------------------------

-- Adds fn(box) -> number or nil: how many things the search in `box` found. Asked on every text change and on show.
function FieldSkins.AddCountSource(fn)
    if type(fn) == "function" then countSources[#countSources + 1] = fn end
end

local function RefreshCount(widget, p)
    for _, source in ipairs(countSources) do
        local ok, n = pcall(source, widget)
        if ok and type(n) == "number" and not (FS.IsSecret and FS.IsSecret(n)) then
            p.count, p.sourced = n, true
            return
        end
    end
    if p.sourced then p.count, p.sourced = nil, false end
end

-------------------------------------------------------------------------------
-- Layout
-------------------------------------------------------------------------------

-- The chip sits in the right of the box, ending CHIP_INSET before the clear key's zone when that is showing, else before
-- the edge; a box too narrow to leave the text CHIP_MIN_TEXT px has none.
local function LayoutChip(widget, p)
    local chip = p.chip
    if not chip then return end
    if p.count == nil or TextOf(widget) == "" then
        chip.frame:Hide()
        p.chipX = nil
        return
    end
    local text = ("%d found"):format(p.count)
    local w = math.ceil((#text * K.TAG_CHAR + K.CHIP_PAD) / K.TAG_ROUND - 1e-9) * K.TAG_ROUND
    local zone = IsShownNow(widget.clearButton) and K.FIELD_CLEAR or 0
    local x = p.w - zone - w - K.CHIP_INSET
    -- a box too narrow to leave the text its room has no chip (the clear key stays, the text matters more)
    if x - K.CHIP_INSET - K.FIELD_TEXT_X < K.CHIP_MIN_TEXT then
        chip.frame:Hide()
        p.chipX = nil
        return
    end
    Kit.Move(chip.frame, x, math.floor((p.h - K.CHIP_H) / 2), w, K.CHIP_H)
    Kit.Move(chip.label, w / 2, K.CHIP_TEXT_Y)
    if chip.text ~= text then
        chip.text = text
        chip.label:SetText(text)
    end
    Kit.PaintPlate(chip.plate, C.ink, 0, C.cyan, 1, 1)
    chip.frame:Show()
    p.chipX = x
end

-- The text starts at the prompt cell's edge plus the gap and stops short of the clear zone or the chip; the placeholder
-- follows it.
local function SeatText(widget, p)
    local left = K.FIELD_TEXT_X
    local right = p.kind == "search" and K.FIELD_CLEAR or K.FIELD_RIGHT
    if p.chipX then right = math.max(right, p.w - p.chipX + K.CHIP_INSET) end
    p.right = right
    local ppu = Kit.Ppu(widget)
    if type(widget.SetTextInsets) == "function" then pcall(widget.SetTextInsets, widget, left / ppu, right / ppu, 0, 0) end
    local hint = widget.Instructions
    if IsTable(hint) and type(hint.ClearAllPoints) == "function" and type(hint.SetPoint) == "function" then
        hint:ClearAllPoints()
        hint:SetPoint("TOPLEFT", widget, "TOPLEFT", left / ppu, 0)
        hint:SetPoint("BOTTOMRIGHT", widget, "BOTTOMRIGHT", -right / ppu, 0)
    end
end

local function SeatPlate(widget, p)
    local w, h = p.w, p.h
    Kit.Place(p.plate.fill, widget, 0, 0, w, h)
    Kit.Place(p.plate.ring, widget, 0, 0, w, h)
    if p.plate.ring2 then Kit.Place(p.plate.ring2, widget, 1, 1, w - 2, h - 2) end
end

local function SeatCross(button)
    local c = crossParts[button]
    if not c then return end
    local w, h = Kit.SizePx(button)
    Kit.Move(c.glyph, w and math.floor((w - K.FIELD_GLYPH) / 2) or 0, h and math.floor((h - K.FIELD_GLYPH) / 2) or 0)
end

-------------------------------------------------------------------------------
-- Caret
-------------------------------------------------------------------------------

local function StartBlink(p)
    if Kit.IsAnimating(p.over, "blink") then return end
    Kit.Animate(p.over, "blink", function(_, elapsed)
        local on = (elapsed % K.CARET_BLINK) < K.CARET_BLINK / 2
        p.caret:SetAlpha(on and p.caretAlpha or 0)
    end)
end

local function UpdateCaret(widget, p)
    if not (p.built and p.w) then return end
    if not (Kit.IsEnabled(widget) and HasFocus(widget)) then
        p.caret:Hide()
        Kit.StopAnimate(p.over, "blink")
        return
    end
    local text = TextOf(widget)
    local pos = Kit.Plain(Kit.Try(widget.GetUTF8CursorPosition, widget))
    if type(pos) ~= "number" or pos > #text then pos = #text end
    local ppu = Kit.Ppu(widget)
    p.measure:SetText(text:sub(1, pos))
    local before = Round(p.measure:GetStringWidth() * ppu)
    p.measure:SetText(text)
    local full = Round(p.measure:GetStringWidth() * ppu)
    -- at the end of the line the block stands CARET_GAP clear of the last glyph, as drawn; mid-line it sits over the next glyph
    local atEnd = pos >= #text
    local gap = atEnd and K.CARET_GAP or 0
    -- text wider than the line scrolls under the engine's caret, where ours would be in the wrong place
    if full + gap + K.CARET_W > p.w - K.FIELD_TEXT_X - (p.right or K.FIELD_RIGHT) then
        p.caret:Hide()
        Kit.StopAnimate(p.over, "blink")
        return
    end
    Kit.Move(p.caret, K.FIELD_TEXT_X + before + gap, math.floor((p.h - K.CARET_H) / 2), K.CARET_W, K.CARET_H)
    p.caretAlpha = atEnd and 1 or K.CARET_DIM
    p.caret:SetAlpha(p.caretAlpha)
    p.caret:Show()
    StartBlink(p)
end

-------------------------------------------------------------------------------
-- Paint
-------------------------------------------------------------------------------

local function StartLed(p)
    if Kit.IsAnimating(p.over, "led") then return end
    Kit.Animate(p.over, "led", function(_, elapsed)
        p.led:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], Kit.Pulse(elapsed, K.LED_PULSE, K.LED_FLOOR))
    end)
end

local function StartSweep(p)
    if Kit.IsAnimating(p.over, "sweep") then return end
    Kit.Animate(p.over, "sweep", function(_, elapsed)
        local turn = (elapsed % K.RADAR_PERIOD) / K.RADAR_PERIOD
        if type(p.arm.SetRotation) == "function" then p.arm:SetRotation(-2 * math.pi * turn) end
        p.dot:SetColorTexture(C.pink[1], C.pink[2], C.pink[3], Kit.Pulse(elapsed, K.LED_PULSE, K.LED_FLOOR))
    end)
end

local function Paint(widget)
    local p = parts[widget]
    if not (p and p.built) then return end
    local enabled = Kit.IsEnabled(widget)
    local focus = enabled and HasFocus(widget)
    local fill, edge, glyph, text, rule = C.ink, C.dim, C.muted, C.text, C.hair
    if not enabled then
        fill, edge, glyph, text, rule = C.disFill, C.disEdge, C.dis, C.dis, C.disEdge
    elseif focus then
        edge, glyph = C.cyan, C.cyan
    elseif p.state.hover then
        edge = C.cyan
    end
    Kit.PaintPlate(p.plate, fill, 1, edge, 1, 1)
    p.rule:SetColorTexture(rule[1], rule[2], rule[3], 1)
    Kit.Recolor(widget, text)
    if IsTable(widget.Instructions) then Kit.Recolor(widget.Instructions, enabled and C.hint or C.dis) end

    p.glow:SetShown(focus)
    if focus then
        p.led:Show()
        StartLed(p)
    else
        p.led:Hide()
        Kit.StopAnimate(p.over, "led")
    end

    if p.kind == "search" then
        local radar = focus
        p.glyph:SetShown(not radar)
        p.radar:SetShown(radar)
        p.arm:SetShown(radar)
        p.dot:SetShown(radar)
        if radar then StartSweep(p) else Kit.StopAnimate(p.over, "sweep") end
    end
    p.glyph:SetVertexColor(glyph[1], glyph[2], glyph[3], 1)
    UpdateCaret(widget, p)
end

local function PaintCross(button)
    local c = crossParts[button]
    if not c then return end
    local color = (Kit.IsEnabled(button) and (c.state.hover or c.state.pressed)) and C.pink or C.muted
    c.glyph:SetVertexColor(color[1], color[2], color[3], 1)
end

-------------------------------------------------------------------------------
-- Layout, then the whole box
-------------------------------------------------------------------------------

local function Layout(widget)
    local p = parts[widget]
    if not (p and p.built) then return end
    local w, h = Kit.SizePx(widget)
    if not w then return end
    p.w, p.h = w, h
    SeatPlate(widget, p)
    local gy = math.floor((h - K.FIELD_GLYPH) / 2)
    Kit.Move(p.glow, -K.FIELD_GLOW, -K.FIELD_GLOW, w + 2 * K.FIELD_GLOW, h + 2 * K.FIELD_GLOW)
    Kit.Move(p.rule, K.FIELD_CELL, K.FIELD_RULE_PAD, 1, h - 2 * K.FIELD_RULE_PAD)
    Kit.Move(p.led, 1, h - K.FIELD_LED_UP, w - 2, K.FIELD_LED_H)
    Kit.Move(p.glyph, K.FIELD_GLYPH_X, gy, K.FIELD_GLYPH, K.FIELD_GLYPH)
    if p.kind == "search" then
        Kit.Move(p.radar, K.FIELD_GLYPH_X, gy, K.FIELD_GLYPH, K.FIELD_GLYPH)
        Kit.Move(p.arm, K.FIELD_GLYPH_X, gy, K.FIELD_GLYPH, K.FIELD_GLYPH)
        Kit.Move(p.dot, K.FIELD_CELL / 2 + K.RADAR_DOT_X, gy + K.FIELD_GLYPH / 2 + K.RADAR_DOT_Y, K.RADAR_DOT, K.RADAR_DOT)
        SeatCross(widget.clearButton)
    end
    LayoutChip(widget, p)
    SeatText(widget, p)
    UpdateCaret(widget, p)
end

Kit.OnReseat(function()
    for widget in pairs(parts) do Layout(widget) end
end)

-- The text, the count or the clear key changed: the chip and the text insets follow.
local function Changed(widget)
    local p = parts[widget]
    if not (p and p.built) then return end
    RefreshCount(widget, p)
    LayoutChip(widget, p)
    SeatText(widget, p)
    UpdateCaret(widget, p)
end

-- Sets the number a search box found by hand; nil removes the chip.
function FieldSkins.SetCount(widget, n)
    local p = parts[widget]
    if not p then return end
    if type(n) ~= "number" or (FS.IsSecret and FS.IsSecret(n)) then n = nil end
    p.count, p.sourced = n, false
    LayoutChip(widget, p)
    SeatText(widget, p)
    UpdateCaret(widget, p)
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local function BuildSearchParts(widget, p)
    local over = p.over
    p.radar = Kit.Glyph(over, RADAR, K.FIELD_GLYPH_X, 0, K.FIELD_GLYPH, K.FIELD_GLYPH, C.cyan, 1, "ARTWORK", 2)
    p.arm = Kit.Glyph(over, ARM, K.FIELD_GLYPH_X, 0, K.FIELD_GLYPH, K.FIELD_GLYPH, C.cyan, 1, "ARTWORK", 3)
    if type(p.arm.SetSnapToPixelGrid) == "function" then pcall(p.arm.SetSnapToPixelGrid, p.arm, false) end -- it turns
    p.dot = Kit.Rect(over, 0, 0, K.RADAR_DOT, K.RADAR_DOT, C.pink, 1, "ARTWORK", 4)
    p.radar:Hide()
    p.arm:Hide()
    p.dot:Hide()

    local frame = CreateFrame("Frame", nil, over)
    Kit.Place(frame, over, 0, 0, K.CHIP_PAD * 2, K.CHIP_H)
    local chip = { frame = frame }
    chip.plate = Kit.Plate(frame, K.CHIP_CUT, K.CHIP_PAD * 2, K.CHIP_H)
    chip.label = Kit.Label(frame, "", K.CHIP_TEXT, C.cyan, "OVERLAY")
    Kit.Place(chip.label, frame, K.CHIP_PAD, K.CHIP_TEXT_Y, nil, nil, "CENTER", "TOPLEFT")
    frame:Hide()
    p.chip = chip

    local clear = widget.clearButton
    if IsTable(clear) and Kit.TypeOf(clear) == "Button" then
        HeldArt.HoldButton(clear)
        local c = { widget = clear }
        c.glyph = Kit.Glyph(clear, CROSS, 0, 0, K.FIELD_GLYPH, K.FIELD_GLYPH, C.muted, 1, "OVERLAY", 1)
        crossParts[clear] = c
        c.state = Kit.Track(clear, PaintCross)
        local function again() Changed(widget) end
        Kit.HookScript(clear, "OnShow", again)
        Kit.HookScript(clear, "OnHide", again)
        Kit.HookScript(clear, "OnSizeChanged", function() SeatCross(clear) end)
        PaintCross(clear)
    end
end

local function Build(widget)
    local kind = FieldSkins.Kind(widget)
    if not kind then return end
    local p = { kind = kind, w = 0, h = 0 }
    parts[widget] = p -- marked first, so a failure part way is not retried into a second set of layers

    HeldArt.HoldButton(widget)
    Kit.RestyleLabel(widget, widget, K.FIELD_TEXT, C.text)
    if IsTable(widget.Instructions) then Kit.RestyleLabel(widget.Instructions, widget, K.FIELD_TEXT, C.hint) end
    if type(widget.SetHighlightColor) == "function" then
        pcall(widget.SetHighlightColor, widget, C.cyan[1], C.cyan[2], C.cyan[3], HIGHLIGHT_ALPHA)
    end

    p.plate = Kit.Plate(widget, K.FIELD_CUT, K.FIELD_GLYPH, K.FIELD_GLYPH)
    p.glow = Kit.Rect(widget, -K.FIELD_GLOW, -K.FIELD_GLOW, 1, 1, C.cyan, K.FIELD_GLOW_ALPHA, "BACKGROUND", -8)
    p.glow:Hide()

    local over = CreateFrame("Frame", nil, widget)
    over:SetAllPoints(widget)
    p.over = over
    p.rule = Kit.Rect(over, K.FIELD_CELL, K.FIELD_RULE_PAD, 1, 1, C.hair, 1, "ARTWORK", 0)
    p.led = Kit.Rect(over, 1, 0, 1, K.FIELD_LED_H, C.cyan, 1, "ARTWORK", 1)
    p.led:Hide()
    p.glyph = Kit.Glyph(over, kind == "search" and LENS or PROMPT, K.FIELD_GLYPH_X, 0, K.FIELD_GLYPH, K.FIELD_GLYPH, C.muted, 1,
        "ARTWORK", 2)
    p.caret = Kit.Rect(over, K.FIELD_TEXT_X, 0, K.CARET_W, K.CARET_H, C.cyan, 1, "OVERLAY", 5)
    p.caret:Hide()
    p.caretAlpha = 1
    p.measure = Kit.Label(over, "", K.FIELD_TEXT, C.text)
    Kit.Place(p.measure, over, 0, 0)
    p.measure:Hide()
    if kind == "search" then BuildSearchParts(widget, p) end
    p.built = true

    p.state = Kit.Track(widget, Paint)
    for _, script in ipairs({ "OnEditFocusGained", "OnEditFocusLost" }) do Kit.HookScript(widget, script, Paint) end
    Kit.HookScript(widget, "OnTextChanged", function() Changed(widget) end)
    Kit.HookScript(widget, "OnCursorChanged", function() UpdateCaret(widget, p) end)
    local function relayout()
        RefreshCount(widget, p)
        Layout(widget)
    end
    Kit.HookScript(widget, "OnSizeChanged", relayout)
    Kit.HookScript(widget, "OnShow", relayout)
    RefreshCount(widget, p)
    Layout(widget)
    Paint(widget)
    Kit.Later(relayout)
end

-- Skins one stock edit or search box. Idempotent; returns true when it skinned now. A box met in combat is skinned when
-- combat ends.
function FieldSkins.Skin(widget)
    if type(widget) ~= "table" or parts[widget] or not FieldSkins.Kind(widget) then return false end
    if type(InCombatLockdown) == "function" and InCombatLockdown() then
        Kit.Defer(function() FieldSkins.Skin(widget) end)
        return false
    end
    local ok, err = pcall(Build, widget)
    if not ok then Kit.Fail("field", err) end
    return ok and parts[widget] ~= nil
end

Kit.Register("field", {
    match = function(widget) return parts[widget] ~= nil or FieldSkins.Kind(widget) ~= nil end,
    skin = FieldSkins.Skin, parts = FieldSkins.Parts,
})

-------------------------------------------------------------------------------
-- Text area
-------------------------------------------------------------------------------

local areaParts = setmetatable({}, { __mode = "k" }) -- scroll frame -> what we drew on it
local AREA_ART = { "TopLeftTex", "TopRightTex", "TopTex", "BottomLeftTex", "BottomRightTex", "BottomTex", "LeftTex", "RightTex",
    "MiddleTex" }

-- True for a stock text area that nothing else owns.
function FieldSkins.IsArea(widget)
    if Kit.TypeOf(widget) ~= "ScrollFrame" then return false end
    local edit = widget.EditBox
    if not (IsTable(edit) and Kit.TypeOf(edit) == "EditBox" and Kit.Plain(Kit.Try(edit.IsMultiLine, edit)) == true) then return false end
    for _, key in ipairs(AREA_ART) do
        if not IsTable(widget[key]) then return false end
    end
    if not areaParts[widget] and Held(widget.TopLeftTex) then return false end
    return true
end

function FieldSkins.AreaParts(widget) return areaParts[widget] end

local function PaintArea(widget)
    local p = areaParts[widget]
    if not (p and p.built) then return end
    local edit = widget.EditBox
    local enabled = Kit.IsEnabled(edit)
    local focus = enabled and HasFocus(edit)
    local fill, edge, text = C.ink, C.dim, C.text
    if not enabled then
        fill, edge, text = C.disFill, C.disEdge, C.dis
    elseif focus or p.state.hover or p.editState.hover then
        edge = C.cyan
    end
    Kit.PaintPlate(p.plate, fill, 1, edge, 1, 1)
    Kit.Recolor(edit, text)
    if IsTable(edit.Instructions) then Kit.Recolor(edit.Instructions, enabled and C.hint or C.dis) end
    p.glow:SetShown(focus)
end

local function LayoutArea(widget)
    local p = areaParts[widget]
    if not (p and p.built) then return end
    local w, h = Kit.SizePx(widget)
    if not w then return end
    -- the stock border overshoots the frame by AREA_PAD units, so the face does too (whole pixels at any scale)
    local pad = Round(K.AREA_PAD * Kit.Ppu(widget))
    local x, y, fw, fh = -pad, -pad, w + 2 * pad, h + 2 * pad
    Kit.Place(p.plate.fill, widget, x, y, fw, fh)
    Kit.Place(p.plate.ring, widget, x, y, fw, fh)
    if p.plate.ring2 then Kit.Place(p.plate.ring2, widget, x + 1, y + 1, fw - 2, fh - 2) end
    Kit.Move(p.glow, x - K.FIELD_GLOW, y - K.FIELD_GLOW, fw + 2 * K.FIELD_GLOW, fh + 2 * K.FIELD_GLOW)
end

Kit.OnReseat(function()
    for widget in pairs(areaParts) do LayoutArea(widget) end
end)

local function BuildArea(widget)
    local p = {}
    areaParts[widget] = p -- marked first, so a failure part way is not retried into a second set of layers
    local edit = widget.EditBox

    for _, key in ipairs(AREA_ART) do HeldArt.Hold(widget[key]) end
    Kit.RestyleLabel(edit, widget, K.FIELD_TEXT, C.text)
    if IsTable(edit.Instructions) then Kit.RestyleLabel(edit.Instructions, widget, K.FIELD_TEXT, C.hint) end
    if IsTable(widget.CharCount) then Kit.RestyleLabel(widget.CharCount, widget, K.AREA_COUNT_TEXT, C.muted) end
    if type(edit.SetHighlightColor) == "function" then
        pcall(edit.SetHighlightColor, edit, C.cyan[1], C.cyan[2], C.cyan[3], HIGHLIGHT_ALPHA)
    end

    p.plate = Kit.Plate(widget, K.AREA_CUT, 1, 1)
    p.glow = Kit.Rect(widget, 0, 0, 1, 1, C.cyan, K.FIELD_GLOW_ALPHA, "BACKGROUND", -8)
    p.glow:Hide()
    p.built = true

    p.state = Kit.Track(widget, PaintArea)
    local function repaint() PaintArea(widget) end
    p.editState = Kit.Track(edit, repaint)
    for _, script in ipairs({ "OnEditFocusGained", "OnEditFocusLost" }) do Kit.HookScript(edit, script, repaint) end
    local function relayout() LayoutArea(widget) end
    Kit.HookScript(widget, "OnSizeChanged", relayout)
    Kit.HookScript(widget, "OnShow", relayout)
    LayoutArea(widget)
    PaintArea(widget)
    Kit.Later(relayout)
end

-- Skins one stock text area. Idempotent; returns true when it skinned now. One met in combat is skinned when combat ends.
function FieldSkins.SkinArea(widget)
    if type(widget) ~= "table" or areaParts[widget] or not FieldSkins.IsArea(widget) then return false end
    if type(InCombatLockdown) == "function" and InCombatLockdown() then
        Kit.Defer(function() FieldSkins.SkinArea(widget) end)
        return false
    end
    local ok, err = pcall(BuildArea, widget)
    if not ok then Kit.Fail("textarea", err) end
    return ok and areaParts[widget] ~= nil
end

Kit.Register("textarea", {
    match = function(widget) return areaParts[widget] ~= nil or FieldSkins.IsArea(widget) end,
    skin = FieldSkins.SkinArea, parts = FieldSkins.AreaParts,
})

-------------------------------------------------------------------------------
-- Count sources: the collections journals filter as the text changes, and say how many they show
-------------------------------------------------------------------------------

local function Journal(frameName, key, namespace, method)
    FieldSkins.AddCountSource(function(box)
        local frame = _G[frameName]
        if type(frame) ~= "table" or frame[key] ~= box then return nil end
        local api = _G[namespace]
        if type(api) ~= "table" or type(api[method]) ~= "function" then return nil end
        return Kit.Plain(api[method]())
    end)
end

Journal("MountJournal", "searchBox", "C_MountJournal", "GetNumDisplayedMounts")
Journal("ToyBox", "searchBox", "C_ToyBox", "GetNumFilteredToys")
Journal("HeirloomsJournal", "SearchBox", "C_Heirloom", "GetNumDisplayedHeirlooms")
