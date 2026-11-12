-- Forever STUwave: ItemSlotSkins
-- The item slot of the shared controls kit (mockups/shared-controls-2026-11-12.html, section 6), as a layer over a slot that
-- already wears the cut plate and ring (Modules/Bags/Bags.lua's SkinItemButton exports its base skin and calls Decorate):
--
--   quality   a 24 x 2 LED under the icon in the quality colour; Uncommon and up also take a 2 px quality edge (the slot's
--             ring, drawn again over it in the kit's colours, and an inner ring); Poor and Common keep the dim ring
--   glint     Epic and up: a 6 px white band at 0.35 crosses the icon in the first 0.6 of a 3.4 s loop (one switch:
--             FS.Layout.Controls.SLOT_GLINT, or ItemSlotSkins.SetGlint at run time)
--   hover     a 4 px cyan wash outside the slot, a cyan 2 px edge, and lock-on brackets (pad 4, arms 6) that breathe by 0.1
--   cooldown  an ink scrim at 0.78 that drains down the icon behind a 2 px cyan front, run by the ENGINE (see below)
--   locked    an ink scrim at 0.55, amber tape at 0.4 and a 16 square lock glyph, and the LED goes to the dim edge colour
--
-- The overlays sit on the mockup's icon area, the slot's rect less 8 wide and 10 tall at (4, 3) (32 x 30 of a 40 square), not on
-- the icon region itself: a bag slot's icon fills the whole button and the plate's corner wedge covers its two cut corners.
--
-- Where the slot's state comes from. The caller hands over a reader, read(button) -> { quality, empty, locked } (any field may
-- be missing; an answer that is not a table, is secret or throws reads as a filled Common slot), because a bag slot, an
-- equipment slot and a merchant slot each learn it a different way. Refresh(button) asks again. The stock icon's SetDesaturated
-- (the lock state, ItemButtonUtil) and the slot's own show, hover and enable changes ask as well.
--
-- Cooldown, without reading a number. A cooldown the client draws is a Cooldown frame whose SetCooldown, SetCooldownFromDurationObject,
-- SetCooldownFromExpirationTime and Clear we follow by post-hooks. The start and duration it was given go straight into a
-- duration object (C_DurationUtil.CreateDuration, SetTimeFromStart / SetTimeFromEnd) and a vertical StatusBar filling from the
-- top is run from it by the engine (StatusBar:SetTimerDuration, remaining time direction), so the scrim is the remaining
-- fraction of the icon. A secret number is never compared or added to: only a PLAIN zero or less says "no cooldown". The stock
-- swipe is switched off only while the drain runs; if this client has no timer enums, no duration object or refuses the
-- numbers, the stock swipe is left exactly as it was. The scrim is a StatusBar child of the button (same frame level as the
-- stock cooldown, one above), so a stack count is covered by it like it is by the stock swipe.
--
-- Skin only. Nothing on the button is resized, reparented, attributed or hidden: our regions and one StatusBar child, post-hooks
-- (HookScript, hooksecurefunc) and weak-keyed state. A slot met in combat is decorated when combat ends.

local _, FS = ...

local Theme, Kit = FS.Theme, FS.ControlKit
if not (Theme and Kit and FS.Layout and FS.Layout.Controls and Theme.COLOR_QUALITY and Theme.AddSliceTexture) then return end

local ItemSlotSkins = {}
FS.ItemSlotSkins = ItemSlotSkins

local K = FS.Layout.Controls
local TEXTURES = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local GLINT, HAZARD, LOCK = TEXTURES .. "ctl_glint.tga", TEXTURES .. "ctl_hazard.tga", TEXTURES .. "ctl_lock.tga"
local CHAMFER = 6 -- the slot plate's cut (Bags.lua: slice_cut2_button at 6)

local C = {
    ink = Theme.COLOR_CTRL_INK, disEdge = Theme.COLOR_CTRL_DISEDGE, cyan = Theme.COLOR_POWER, amber = Theme.COLOR_AMBER,
    white = { 1, 1, 1, 1 },
}

local function Weak() return setmetatable({}, { __mode = "k" }) end

local parts = Weak()     -- item button -> what we drew on it
local readers = Weak()   -- item button -> the caller's read(button)
local glintSwitch        -- nil = the Layout constant, true / false = set at run time

local function Round(v) return math.floor(v + 0.5) end

-------------------------------------------------------------------------------
-- The glint's switch and path
-------------------------------------------------------------------------------

function ItemSlotSkins.GlintEnabled()
    if glintSwitch ~= nil then return glintSwitch end
    return K.SLOT_GLINT == true
end

-- Where the glint's band is, in pixels right of its resting place, `elapsed` seconds into the loop; nil while it rests. 44 left
-- of the icon at the start, 64 right of it at the end of the sweep, eased in and out (the mockup's CSS ease-in-out).
function ItemSlotSkins.GlintOffset(elapsed)
    local sweep = K.SLOT_GLINT_PERIOD * K.SLOT_GLINT_SWEEP
    local e = elapsed % K.SLOT_GLINT_PERIOD
    if e > sweep then return nil end
    return K.SLOT_GLINT_FROM + (K.SLOT_GLINT_TO - K.SLOT_GLINT_FROM) * Kit.Ease.inOutSine(e / sweep)
end

-------------------------------------------------------------------------------
-- The slot's state
-------------------------------------------------------------------------------

local function QualityIndex(value)
    value = Kit.Plain(value)
    if type(value) ~= "number" or value < 0 then return 1 end
    return math.min(math.floor(value), K.SLOT_QUALITY_TOP)
end

-- { quality = 0..5 (Common when unknown), empty, locked } of `button`, always a table.
local function Read(button)
    local state
    local read = readers[button]
    if read then
        local ok, answer = pcall(read, button)
        if ok then state = Kit.Plain(answer) end
    end
    if type(state) ~= "table" then state = {} end
    return {
        quality = QualityIndex(state.quality),
        empty = Kit.Plain(state.empty) == true,
        locked = Kit.Plain(state.locked) == true,
    }
end

local function Colour(index) return Theme.COLOR_QUALITY[index] or Theme.COLOR_QUALITY[1] end

-------------------------------------------------------------------------------
-- Drawing
-------------------------------------------------------------------------------

local function SetColour(region, color, alpha)
    region:SetColorTexture(color[1], color[2], color[3], alpha or color[4] or 1)
end

local function Tint(region, color)
    region:SetVertexColor(color[1], color[2], color[3], 1)
end

local function AnimateGlint(button, p)
    Kit.Animate(button, "glint", function(_, elapsed)
        local t = ItemSlotSkins.GlintOffset(elapsed)
        if t == nil or t + K.SLOT_GLINT_BAND <= 0 or t >= p.iw then
            p.glint:Hide()
            return
        end
        local sheet = K.SLOT_GLINT_SHEET
        p.glint:SetTexCoord(-t / sheet, (p.iw - t) / sheet, 0, p.ih / sheet)
        p.glint:Show()
    end)
end

-- The brackets breathe: the whole box grows by SLOT_RETICLE_GROW about its centre and back over SLOT_RETICLE_PERIOD (the
-- mockup scales the group), rounded to whole pixels, arms scaled with it.
local function BreatheReticle(button, p)
    Kit.Animate(button, "reticle", function(_, elapsed)
        local phase = (elapsed % K.SLOT_RETICLE_PERIOD) / K.SLOT_RETICLE_PERIOD
        local down = phase < 0.5 and phase * 2 or (1 - phase) * 2
        local scale = 1 + K.SLOT_RETICLE_GROW * Kit.Ease.inOutSine(down)
        local pad = Round(K.SLOT_RETICLE_PAD + (p.w / 2 + K.SLOT_RETICLE_PAD) * (scale - 1))
        Kit.SeatReticle(p.reticle, 0, 0, p.w, p.h, pad, Round(K.SLOT_RETICLE_LEN * scale))
    end)
end

local function Paint(button)
    local p = parts[button]
    if not (p and p.built) then return end
    local s = Read(button)
    local hover = p.state.hover
    local filled = not s.empty
    local q = s.quality

    p.led:SetShown(filled)
    if filled then SetColour(p.led, s.locked and C.disEdge or Colour(q)) end

    -- the 2 px edge: cyan under the hand, else the quality colour from Uncommon up, else the slot's own ring alone
    local edge = hover and C.cyan or (filled and q >= K.SLOT_EDGE_FROM and Colour(q)) or nil
    p.edge:SetShown(edge ~= nil)
    p.edge2:SetShown(edge ~= nil)
    if edge then
        Tint(p.edge, edge)
        Tint(p.edge2, edge)
    end

    for _, bar in pairs(p.wash) do bar:SetShown(hover) end
    Kit.ShowReticle(p.reticle, hover)
    if hover then
        Kit.SeatReticle(p.reticle, 0, 0, p.w, p.h, K.SLOT_RETICLE_PAD, K.SLOT_RETICLE_LEN)
        if not Kit.IsAnimating(button, "reticle") then BreatheReticle(button, p) end
    else
        Kit.StopAnimate(button, "reticle")
    end

    if filled and q >= K.SLOT_GLINT_MIN and ItemSlotSkins.GlintEnabled() then
        if not Kit.IsAnimating(button, "glint") then AnimateGlint(button, p) end
    else
        Kit.StopAnimate(button, "glint")
        p.glint:Hide()
    end

    local locked = filled and s.locked
    p.scrim:SetShown(locked)
    p.hazard:SetShown(locked)
    p.lock:SetShown(locked)
end

local function Layout(button)
    local p = parts[button]
    if not (p and p.built) then return end
    local w, h = Kit.SizePx(button)
    if not w then return end
    local iw, ih = w - K.SLOT_ICON_TRIM_W, h - K.SLOT_ICON_TRIM_H
    p.w, p.h, p.iw, p.ih = w, h, iw, ih
    local x, y = K.SLOT_ICON_X, K.SLOT_ICON_Y

    -- the rings follow the stock rect exactly (the slot's own ring does), the inner one a pixel in
    local u = Kit.U(button, 1)
    p.edge2:ClearAllPoints()
    p.edge2:SetPoint("TOPLEFT", button, "TOPLEFT", u, -u)
    p.edge2:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", -u, u)

    Kit.Move(p.led, math.floor((w - K.SLOT_LED_W) / 2), h - K.SLOT_LED_UP, K.SLOT_LED_W, K.SLOT_LED_H)
    Kit.Move(p.glint, x, y, iw, ih)
    Kit.Move(p.scrim, x, y, iw, ih)
    Kit.Move(p.hazard, x, y, iw, ih)
    p.hazard:SetTexCoord(0, iw / K.SLOT_HAZARD_SHEET, 0, ih / K.SLOT_HAZARD_SHEET)
    Kit.Move(p.lock, x + math.floor((iw - K.SLOT_LOCK) / 2), y + math.floor((ih - K.SLOT_LOCK) / 2), K.SLOT_LOCK, K.SLOT_LOCK)

    local pad = K.SLOT_WASH_PAD
    Kit.Move(p.wash.top, -pad, -pad, w + 2 * pad, pad)
    Kit.Move(p.wash.bottom, -pad, h, w + 2 * pad, pad)
    Kit.Move(p.wash.left, -pad, 0, pad, h)
    Kit.Move(p.wash.right, w, 0, pad, h)
    Kit.SeatReticle(p.reticle, 0, 0, w, h, K.SLOT_RETICLE_PAD, K.SLOT_RETICLE_LEN)

    if p.bar then
        Kit.Move(p.bar, x, y, iw, ih)
        p.front:SetHeight(Kit.U(button, K.SLOT_COOLDOWN_FRONT))
    end
end

Kit.OnReseat(function()
    for button in pairs(parts) do
        Layout(button)
        Paint(button)
    end
end)

-------------------------------------------------------------------------------
-- Cooldown
-------------------------------------------------------------------------------

-- The remaining time direction and immediate interpolation (the same pair FrameHelpers' cooldown fill uses), or nil.
local function TimerOptions()
    local E = _G.Enum
    if type(E) ~= "table" then return nil, nil end
    local dirs, interps = E.StatusBarTimerDirection, E.StatusBarInterpolation
    return type(dirs) == "table" and dirs.RemainingTime or nil, type(interps) == "table" and interps.Immediate or nil
end

local function FindCooldown(button)
    local cd = button.Cooldown
    if type(cd) ~= "table" then cd = button.cooldown end
    if type(cd) ~= "table" and type(button.GetName) == "function" then
        local name = Kit.Try(button.GetName, button)
        if type(name) == "string" then cd = _G[name .. "Cooldown"] end
    end
    if type(cd) == "table" and type(cd.SetCooldown) == "function" then return cd end
    return nil
end

local function FindIcon(button)
    local icon = button.Icon
    if type(icon) ~= "table" then icon = button.icon end
    if type(icon) ~= "table" and type(button.GetName) == "function" then
        local name = Kit.Try(button.GetName, button)
        if type(name) == "string" then icon = _G[name .. "IconTexture"] end
    end
    return type(icon) == "table" and icon or nil
end

local function StopDrain(button)
    local p = parts[button]
    if not (p and p.bar) then return end
    p.bar:Hide()
    if p.draining then
        p.draining = false
        if p.cd and type(p.cd.SetDrawSwipe) == "function" then pcall(p.cd.SetDrawSwipe, p.cd, p.swipeBefore ~= false) end
    end
end

-- Runs the scrim from `obj`, the duration object of this cooldown. False when the client would not take it (the stock swipe
-- stays as it was).
local function RunDrain(button, p, obj)
    local dir, interp = TimerOptions()
    if obj == nil or dir == nil or interp == nil or type(p.bar.SetTimerDuration) ~= "function" then
        StopDrain(button)
        return false
    end
    if not pcall(p.bar.SetTimerDuration, p.bar, obj, interp, dir) then
        StopDrain(button)
        return false
    end
    if not p.draining then
        p.swipeBefore = Kit.Plain(Kit.Try(p.cd.GetDrawSwipe, p.cd))
        p.draining = true
        if type(p.cd.SetDrawSwipe) == "function" then pcall(p.cd.SetDrawSwipe, p.cd, false) end
    end
    p.bar:Show()
    return true
end

local function NewDuration()
    local util = _G.C_DurationUtil
    if type(util) ~= "table" or type(util.CreateDuration) ~= "function" then return nil end
    local ok, obj = pcall(util.CreateDuration)
    return ok and type(obj) == "table" and obj or nil
end

-- A cooldown set from numbers (start and duration, or the end and duration): the numbers are handed to a duration object
-- untouched. Only a plain zero or less is told apart (no cooldown).
local function DrainFromNumbers(button, setter, first, duration, modRate)
    local p = parts[button]
    if not (p and p.bar) then return end
    local a, b = Kit.Plain(first), Kit.Plain(duration)
    if type(a) == "number" and type(b) == "number" and (a <= 0 or b <= 0) then return StopDrain(button) end
    local obj = NewDuration()
    if not (obj and type(obj[setter]) == "function" and pcall(obj[setter], obj, first, duration, modRate)) then
        return StopDrain(button)
    end
    RunDrain(button, p, obj)
end

local function BuildDrain(button, p)
    local cd = FindCooldown(button)
    if not cd then return end
    local ok, bar = pcall(CreateFrame, "StatusBar", nil, button)
    if not ok or type(bar) ~= "table" or type(bar.SetStatusBarTexture) ~= "function" then return end
    p.cd, p.bar = cd, bar
    Kit.Place(bar, button, K.SLOT_ICON_X, K.SLOT_ICON_Y, 1, 1)
    bar:EnableMouse(false)
    bar:SetStatusBarTexture(Theme.FLAT_TEXTURE)
    if bar.SetOrientation then bar:SetOrientation("VERTICAL") end
    if bar.SetReverseFill then bar:SetReverseFill(true) end
    bar:SetMinMaxValues(0, 1)
    bar:SetValue(0)
    local scrim = bar:GetStatusBarTexture()
    if bar.SetStatusBarColor then bar:SetStatusBarColor(C.ink[1], C.ink[2], C.ink[3], K.SLOT_COOLDOWN_ALPHA) end
    if bar.SetClipsChildren then bar:SetClipsChildren(true) end
    bar:SetFrameLevel((Kit.Try(cd.GetFrameLevel, cd) or Kit.Try(button.GetFrameLevel, button) or 0) + 1)

    -- the front is the last rows of the scrim, so an empty bar shows no stray line (the bar clips its children)
    local host = CreateFrame("Frame", nil, bar)
    host:SetAllPoints(bar)
    host:EnableMouse(false)
    local front = host:CreateTexture(nil, "OVERLAY", nil, 2)
    SetColour(front, C.cyan)
    front:SetPoint("BOTTOMLEFT", scrim, "BOTTOMLEFT")
    front:SetPoint("BOTTOMRIGHT", scrim, "BOTTOMRIGHT")
    front:SetHeight(Kit.U(button, K.SLOT_COOLDOWN_FRONT))
    p.front = front
    bar:Hide()

    local function guard(fn)
        return function(...)
            local done, err = pcall(fn, ...)
            if not done then Kit.Fail("itemslot cooldown", err) end
        end
    end
    Kit.HookFunc(cd, "SetCooldown", guard(function(_, start, duration, modRate)
        DrainFromNumbers(button, "SetTimeFromStart", start, duration, modRate)
    end))
    Kit.HookFunc(cd, "SetCooldownFromExpirationTime", guard(function(_, finish, duration, modRate)
        DrainFromNumbers(button, "SetTimeFromEnd", finish, duration, modRate)
    end))
    Kit.HookFunc(cd, "SetCooldownFromDurationObject", guard(function(_, obj) RunDrain(button, p, obj) end))
    Kit.HookFunc(cd, "Clear", guard(function() StopDrain(button) end))
    Kit.HookScript(cd, "OnCooldownDone", guard(function() StopDrain(button) end))
    Kit.HookScript(cd, "OnHide", guard(function() StopDrain(button) end))
end

-------------------------------------------------------------------------------
-- Building
-------------------------------------------------------------------------------

local function Build(button)
    local p = { w = 0, h = 0, iw = 0, ih = 0 }
    parts[button] = p -- marked first, so a failure part way is not retried into a second set of layers

    local ring = Theme.Cut2ButtonSet(CHAMFER)
    p.edge = Theme.AddSliceTexture(button, ring, C.white, "OVERLAY", 2)
    Theme.ApplyNineSlice(p.edge, CHAMFER)
    p.edge2 = Theme.AddSliceTexture(button, Theme.Cut2ButtonSet(Theme.SnapCut(CHAMFER - 1)), C.white, "OVERLAY", 2)
    Theme.ApplyNineSlice(p.edge2, Theme.SnapCut(CHAMFER - 1))
    p.edge:Hide()
    p.edge2:Hide()

    p.wash = {}
    for _, side in ipairs({ "top", "bottom", "left", "right" }) do
        p.wash[side] = Kit.Rect(button, 0, 0, 1, 1, C.cyan, K.SLOT_WASH_ALPHA, "BACKGROUND", -7)
        p.wash[side]:Hide()
    end
    p.led = Kit.Rect(button, 0, 0, K.SLOT_LED_W, K.SLOT_LED_H, Colour(1), 1, "OVERLAY", 3)
    p.glint = Kit.Glyph(button, GLINT, 0, 0, 1, 1, C.white, K.SLOT_GLINT_ALPHA, "OVERLAY", 4)
    p.glint:Hide()
    p.scrim = Kit.Rect(button, 0, 0, 1, 1, C.ink, K.SLOT_LOCK_ALPHA, "OVERLAY", 5)
    p.hazard = Kit.Glyph(button, HAZARD, 0, 0, 1, 1, C.amber, K.SLOT_HAZARD_ALPHA, "OVERLAY", 6)
    p.lock = Kit.Glyph(button, LOCK, 0, 0, K.SLOT_LOCK, K.SLOT_LOCK, C.amber, 1, "OVERLAY", 7)
    p.scrim:Hide()
    p.hazard:Hide()
    p.lock:Hide()
    p.reticle = Kit.Reticle(button, "OVERLAY", 7)
    Kit.ShowReticle(p.reticle, false)
    p.built = true

    p.state = Kit.Track(button, Paint)
    local icon = FindIcon(button)
    if icon then Kit.HookFunc(icon, "SetDesaturated", function() Paint(button) end) end
    local function relayout()
        Layout(button)
        Paint(button)
    end
    Kit.HookScript(button, "OnSizeChanged", relayout)
    BuildDrain(button, p)
    Layout(button)
    Paint(button)
    Kit.Later(relayout)
end

-- Decorates a slot that already wears the cut plate and ring. `read(button)` answers { quality, empty, locked } (see the file
-- header). Idempotent; returns true when the slot is decorated, false when it waits for combat to end.
function ItemSlotSkins.Decorate(button, read)
    if type(button) ~= "table" then return false end
    if read ~= nil then readers[button] = read end
    if parts[button] then return true end
    if type(InCombatLockdown) == "function" and InCombatLockdown() then
        Kit.Defer(function() ItemSlotSkins.Decorate(button, read) end)
        return false
    end
    local ok, err = pcall(Build, button)
    if not ok then Kit.Fail("itemslot", err) end
    return ok and parts[button] ~= nil
end

-- Reads the slot again and repaints it.
function ItemSlotSkins.Refresh(button)
    if parts[button] then Paint(button) end
end

function ItemSlotSkins.Parts(button) return parts[button] end

-- Turns the glint on or off at run time; nil goes back to FS.Layout.Controls.SLOT_GLINT.
function ItemSlotSkins.SetGlint(on)
    if on == nil then glintSwitch = nil else glintSwitch = on and true or false end
    for button in pairs(parts) do Paint(button) end
end
