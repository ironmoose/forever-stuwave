-- Forever STUwave: Gunsight Shaman Class Module, lane 3: CLICK A POLE TO DROP ITS TOTEM
--
-- A left click anywhere on an element's pole column casts exactly what that element's button on the totem tab casts (the
-- picked totem), in and out of combat. The column is the whole pole from above the tallest crown to under the label, so a
-- click on a pole whose totem already stands drops it again (a refresh): a secure button cannot follow "totem up or down"
-- in combat, and the DROP head only matters to the eye.
--
-- WHY A SEPARATE FILE. Casting from a click needs a SECURE button, and GunsightShaman.lua is plain frames only (a secure
-- button under a Gunsight host would make the host protected, and the host hides and shows with the target, which is
-- blocked in combat). So the catchers live OUTSIDE the host tree, hung from Gunsight.root the way GunsightTags.lua's target
-- menu button is: a holder that is never shown or hidden by us, Gunsight.Point seats, nothing anchored to a frame that moves.
--
-- WHAT DOES NOT WORK HERE, and what is used instead (both measured on this client, ActionBars.lua / TotemBar.lua):
--   * No state driver and no secure snippet: neither runs on this client. The visibility rule "the poles are on screen while
--     there is a target" is the client's own unit watch: the holder carries unit = "target" and RegisterUnitWatch, the
--     equivalent of the macro conditional [@target,exists] show; hide, applied by the engine in and out of combat. The poles
--     hide on FS.HasTarget (UnitExists("target")), which is the same test.
--   * No type = "click" with a clickbutton on the tab's button: SECURE_ACTIONS.click calls delegate:Click(button), an
--     addon-originated click with down = false, and SecureActionButton_OnClick ignores that whenever the ActionButtonUseKeyDown
--     CVar is on (TotemBar.lua builds its destroy buttons with useOnKeyDown = false for this very reason). The tab's own
--     buttons cannot take that attribute without changing their key binding behaviour. So each catcher is a real secure action
--     button of its own, taking real clicks like the tab's, and carries a COPY of the tab button's type1 / action1 / spell1.
--     TotemBar.lua stays the only place that decides what a pick casts: it announces (TotemBar.OnAttributes) after every
--     out of combat settle, and the copy is made then. Nothing is ever written to the tab's buttons from here.
--
-- WHEN A CATCHER TAKES THE MOUSE (all decided out of combat; EnableMouse, SetPoint, SetSize and SetAttribute on a secure
-- frame are refused in combat, so a change made in combat sets `pending` and PLAYER_REGEN_ENABLED replays it):
--   * the Shaman class module is in an area (Areas.AreaOf("class"), which also answers for the dot piece being on), and
--   * the Gunsight is the display (Gunsight.IsActive()), and
--   * the element is open (ShamanTotems.IsUnlocked) and its tab button has a castable type1 (a locked or not learned element
--     has none, and then no catcher is even built).
--   With no target the holder is hidden by the unit watch whatever the mouse says.
--   Accepted limits, like the target menu button's: a module moved to the other area, an element learned, the dot piece
--   switched off, an area reassigned, or the Gunsight switched off while in combat leaves the catchers where and as they were,
--   mouse on included, until PLAYER_REGEN_ENABLED (EnableMouse on a secure frame is refused in combat, and the root only
--   fades), so a left click on the now invisible column still casts meanwhile.
--
-- Left click only. Right and middle clicks are passed through to the world when the client lets us (SetPassThroughButtons,
-- as the target menu does). Accepted limit: on a client that cannot, the catchers keep the mouse (the left click is the
-- feature), one chat line says so, and a right drag that starts over a pole, the camera turn, is swallowed.
-- Alt-click does nothing (on the tab it opens the picker). Nothing is drawn: no texture, no region, no tooltip, no script.
--
-- Nothing here is verified in game; the harness is a strict mock.

local _, FS = ...

local Gunsight = FS.Gunsight
local Areas = FS.GunsightAreas
local Shaman = FS.GunsightShaman
local TotemBar = FS.TotemBar
if not (Gunsight and Gunsight.ui and Gunsight.Point and Gunsight.root and Gunsight.IsActive and Gunsight.OnActiveChanged) then return end
if not (Areas and Areas.AreaOf and Areas.OnAreaChanged) then return end
if not (Shaman and Shaman.C and Shaman.Origin and Shaman.OnSeat) then return end
if not (TotemBar and TotemBar.OnAttributes) then return end

FS.GunsightShamanDrop = FS.GunsightShamanDrop or {}
local Drop = FS.GunsightShamanDrop

local ui, Point = Gunsight.ui, Gunsight.Point
local K = Shaman.C
local POLES = K.POLES

local C = {
    -- the column, image px from the module's top: from above the tallest crown (a full pole's head at GY - NB * BP - HEAD_H, the
    -- crown CROWN_UP above it and up to 8 px of glyph) to under the label (baseline GY + LABEL_Y, a few px of descender)
    TOP = K.GY - K.NB * K.BP - K.HEAD_H - K.CROWN_UP - 8,
    BOTTOM = K.GY + K.LABEL_Y + 4,
    LEVEL = 4,                  -- frame levels above the module frame: over the heads (+2) and the Nova ring (+3)
    -- copied from the tab's element button; the alt forms are an empty type so an Alt click casts nothing (Blizzard builds the
    -- modifier prefix in the order alt-ctrl-shift-)
    ATTRS = { "type1", "action1", "spell1" },
    ALT_NOOPS = { "alt-type1", "alt-shift-type1", "alt-ctrl-type1", "alt-ctrl-shift-type1" },
    NOOP = "",                  -- Blizzard's ATTRIBUTE_NOOP
    NAME = "ForeverSTUwaveGunsightTotemDrop",
    TAB = "FSTotemButton",      -- the totem tab's buttons, FSTotemButton1..4 for Fire, Earth, Water, Air (the binding names)
}
Drop.C = C

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightshamandrop_" .. key,
            "|cffff4488Forever STUwave|r: gunsight shaman module: " .. tostring(msg))
    end
end

local function InCombat()
    return type(InCombatLockdown) == "function" and InCombatLockdown() and true or false
end

local holder                   -- the unit watched parent of every catcher
local catchers = {}            -- pole slot -> its secure button (built only for an open element, out of combat)
local mouseOn = {}             -- slot -> whether EnableMouse(true) was last written
local seated = {}              -- slot -> { x, y, k }: the origin and scale the catcher was last seated for
local pending = false
local events
local subscribed = false
Drop.catchers = catchers

-------------------------------------------------------------------------------
-- Build (out of combat only)
-------------------------------------------------------------------------------

-- Left clicks are the catcher's; right and middle fall through to the world when the client says so.
local function PassClicksThrough(button)
    if type(button.SetPassThroughButtons) ~= "function" then return false end
    if not pcall(button.SetPassThroughButtons, button, "RightButton", "MiddleButton") then return false end
    if type(button.ShouldButtonPassThrough) ~= "function" then return true end
    local ok, right = pcall(button.ShouldButtonPassThrough, button, "RightButton")
    return ok and right == true
end

local function BuildHolder()
    if holder then return true end
    if type(RegisterUnitWatch) ~= "function" then
        LogOnce("nounitwatch", "the pole click is off: this client has no unit watch.")
        return false
    end
    local module = Shaman.frame
    local frame = CreateFrame("Button", C.NAME, Gunsight.root, "SecureUnitButtonTemplate")
    frame:SetSize(1, 1)
    frame:SetPoint("CENTER", Gunsight.root, "CENTER", 0, 0)
    if module and module.GetFrameLevel then frame:SetFrameLevel(module:GetFrameLevel() + C.LEVEL) end
    frame:EnableMouse(false)
    frame:SetAttribute("unit", "target")
    holder = frame
    RegisterUnitWatch(frame)
    return true
end

local function BuildCatcher(slot)
    if catchers[slot] then return catchers[slot] end
    if not BuildHolder() then return nil end
    local button = CreateFrame("Button", C.NAME .. slot, holder, "SecureActionButtonTemplate")
    button:RegisterForClicks("AnyUp", "AnyDown")
    button:SetFrameLevel(holder:GetFrameLevel() + 1)
    button:EnableMouse(false)
    if not PassClicksThrough(button) then
        LogOnce("passthrough", "a right or middle click that starts over a totem pole is taken by the pole: this client cannot pass them through.")
    end
    button.fsSlot = slot
    catchers[slot] = button
    mouseOn[slot] = false
    return button
end

-------------------------------------------------------------------------------
-- Attributes: a copy of what the tab's button casts
-------------------------------------------------------------------------------

local function TabButton(slot)
    local button = _G[C.TAB .. slot]
    if type(button) == "table" and type(button.GetAttribute) == "function" then return button end
    return nil
end

-- true when the tab's element button has something to cast (a locked or not learned element carries no type1)
local function TabCasts(slot)
    local tab = TabButton(slot)
    return tab ~= nil and tab:GetAttribute("type1") ~= nil
end

local function Mirror(slot)
    local button, tab = catchers[slot], TabButton(slot)
    if not (button and tab) then return end
    for i = 1, #C.ATTRS do
        local name = C.ATTRS[i]
        local value = tab:GetAttribute(name)
        if button:GetAttribute(name) ~= value then button:SetAttribute(name, value) end
    end
    local noop = tab:GetAttribute("type1") ~= nil and C.NOOP or nil
    for i = 1, #C.ALT_NOOPS do
        local name = C.ALT_NOOPS[i]
        if button:GetAttribute(name) ~= noop then button:SetAttribute(name, noop) end
    end
end

-------------------------------------------------------------------------------
-- Seat and mouse
-------------------------------------------------------------------------------

local function SeatCatcher(slot, ox, oy)
    local button, def = catchers[slot], POLES[slot]
    local k = ui(1)
    local at = seated[slot]
    if at and at.x == ox and at.y == oy and at.k == k then return end
    Point(button, "TOPLEFT", ox + def.x, oy + C.TOP)
    button:SetSize(ui(def.w), ui(C.BOTTOM - C.TOP))
    if not at then
        at = {}
        seated[slot] = at
    end
    at.x, at.y, at.k = ox, oy, k
end

local function Wanted(slot)
    if not Gunsight.IsActive() then return false end
    if Areas.AreaOf("class") == nil then return false end
    local totems = FS.ShamanTotems
    if totems and totems.IsUnlocked and not totems.IsUnlocked(slot) then return false end
    return TabCasts(slot)
end

-- Out of combat only. Idempotent and allocation free once built.
local function Apply()
    local ox, oy = Shaman.Origin()
    for slot = 1, #POLES do
        local want = Wanted(slot)
        local button = catchers[slot]
        if want and not button then button = BuildCatcher(slot) end
        if button then
            Mirror(slot)
            SeatCatcher(slot, ox, oy)
            local on = want and true or false
            if mouseOn[slot] ~= on then
                button:EnableMouse(on)
                mouseOn[slot] = on
            end
        end
    end
end

local function OnEvent(_, event)
    if event == "PLAYER_REGEN_ENABLED" and pending then Drop.Sync() end
end

-- Anything that can change a catcher asks here. In combat nothing secure is touched: the ask is remembered and replayed at
-- PLAYER_REGEN_ENABLED.
function Drop.Sync()
    if not Shaman.frame then return end
    if InCombat() then
        pending = true
        return
    end
    pending = false
    local ok, err = pcall(Apply)
    if not ok then
        pending = true              -- PLAYER_REGEN_ENABLED tries again
        LogOnce("apply", err)
    end
end

local function Request()
    if not events then
        events = CreateFrame("Frame")
        events:SetScript("OnEvent", OnEvent)
        events:RegisterEvent("PLAYER_REGEN_ENABLED")
    end
    if not subscribed and FS.ShamanTotems and FS.ShamanTotems.Subscribe then
        subscribed = true
        FS.ShamanTotems.Subscribe(Request)       -- an element opening or closing (level up, a learned totem)
    end
    Drop.Sync()
end

Shaman.OnSeat(Request)
Areas.OnAreaChanged(Request)
Gunsight.OnActiveChanged(Request)
TotemBar.OnAttributes(Request)
