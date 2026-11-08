-- Forever STUwave: Gunsight Mage Class Module: CLICK THE WARD TO CAST IT
--
-- A left click on the ward casts Ice Barrier when the Mage knows it, else Mana Shield (the same pick the ward draws, MageState's
-- WardKind). Both are self spells. In and out of combat. The catcher covers the ward's oval and its pink buff ring, not the
-- label under it and not the spec piece on the left.
--
-- WHY A SEPARATE FILE. Casting from a click needs a SECURE button, and GunsightMage.lua is plain frames only (a secure button
-- under a Gunsight host makes the host protected, and the host hides and shows with the target, which is blocked in combat).
-- So the catcher lives OUTSIDE the host tree exactly as GunsightPriestClick.lua's does (read GunsightShamanDrop.lua's header
-- for the reasons): hung from Gunsight.root through a SecureUnitButtonTemplate holder with unit = "target" and
-- RegisterUnitWatch (the engine's own [@target,exists] show; hide; state drivers and snippets do not run on this client),
-- seated with Gunsight.Point, never shown or hidden by us.
--
-- NO ATTRIBUTE WRITE IN COMBAT. The catcher carries unit = "player", type1 = "spell" and spell1 = the ward's name, all written
-- out of combat. A ward learned in combat, or the other one coming into use (Ice Barrier learned while Mana Shield was the
-- ward), is written at PLAYER_REGEN_ENABLED. Alt forms of the left click are empty types (the Warrior helm's rule); other
-- modifiers find no attribute and do nothing.
--
-- WHEN THE CATCHER TAKES THE MOUSE (decided out of combat only; a change in combat sets `pending` and PLAYER_REGEN_ENABLED
-- replays it): the Mage class module is in an area (Areas.AreaOf("class")), the Gunsight is the display (Gunsight.IsActive())
-- and one of the two wards is known (MageState). Accepted limits, the Shaman pole click's: an area move, a reassigned area, or
-- the dot piece or the master switch turned off in combat leaves the catcher as it was, mouse on included, until regen, so a
-- left click on the invisible ward still casts meanwhile. Right and middle clicks pass through where the client allows; where
-- it cannot, the catcher keeps the mouse, one chat line says so, and a right drag camera turn that starts over the ward is
-- swallowed.
--
-- Nothing here is verified in game; the harness is a strict mock.

local _, FS = ...

local Gunsight = FS.Gunsight
local Areas = FS.GunsightAreas
local Mage = FS.GunsightMage
local Data = FS.MageState
if not (Gunsight and Gunsight.ui and Gunsight.Point and Gunsight.root and Gunsight.IsActive and Gunsight.OnActiveChanged) then return end
if not (Areas and Areas.AreaOf and Areas.OnAreaChanged) then return end
if not (Mage and Mage.C and Mage.Origin and Mage.OnSeat) then return end
if not (Data and Data.WardKind and Data.Subscribe and Data.DEFS) then return end

FS.GunsightMageClick = FS.GunsightMageClick or {}
local Click = FS.GunsightMageClick

local ui, Point = Gunsight.ui, Gunsight.Point
local MC = Mage.C

local C = {
    -- the ward's oval plus the buff ring, sprite px from the module's top left, one px of slack for the hit shake
    LEFT = MC.WARD.x - 21,
    TOP = MC.WARD.y - 26,
    W = 42, H = 52,
    LEVEL = 4,                  -- frame levels above the module frame
    ALT_NOOPS = { "alt-type1", "alt-shift-type1", "alt-ctrl-type1", "alt-ctrl-shift-type1" },
    NOOP = "",                  -- Blizzard's ATTRIBUTE_NOOP
    NAME = "ForeverSTUwaveGunsightWard",
}
Click.C = C

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightmageclick_" .. key,
            "|cffff4488Forever STUwave|r: gunsight mage module: " .. tostring(msg))
    end
end

local function InCombat()
    return type(InCombatLockdown) == "function" and InCombatLockdown() and true or false
end

local holder, catcher
local mouseOn = false
local seated
local pending = false
local events

local function PassClicksThrough(button)
    if type(button.SetPassThroughButtons) ~= "function" then return false end
    if not pcall(button.SetPassThroughButtons, button, "RightButton", "MiddleButton") then return false end
    if type(button.ShouldButtonPassThrough) ~= "function" then return true end
    local ok, right = pcall(button.ShouldButtonPassThrough, button, "RightButton")
    return ok and right == true
end

local function BuildCatcher()
    if catcher then return catcher end
    if type(RegisterUnitWatch) ~= "function" then
        LogOnce("nounitwatch", "the ward click is off: this client has no unit watch.")
        return nil
    end
    local module = Mage.frame
    holder = CreateFrame("Button", C.NAME .. "Holder", Gunsight.root, "SecureUnitButtonTemplate")
    holder:SetSize(1, 1)
    holder:SetPoint("CENTER", Gunsight.root, "CENTER", 0, 0)
    if module and module.GetFrameLevel then holder:SetFrameLevel(module:GetFrameLevel() + C.LEVEL) end
    holder:EnableMouse(false)
    holder:SetAttribute("unit", "target")
    RegisterUnitWatch(holder)
    local button = CreateFrame("Button", C.NAME, holder, "SecureActionButtonTemplate")
    button:RegisterForClicks("AnyUp", "AnyDown")
    button:SetFrameLevel(holder:GetFrameLevel() + 1)
    button:EnableMouse(false)
    if not PassClicksThrough(button) then
        LogOnce("passthrough", "a right or middle click that starts over the ward is taken by the ward: this client cannot pass them through.")
    end
    catcher = button
    Click.catcher = button
    return button
end

-- the spell the click casts: Ice Barrier when known, else Mana Shield (nil when neither)
local function SpellName()
    local kind = Data.WardKind()
    local d = kind == "barrier" and Data.DEFS.icebarrier or (kind == "mana" and Data.DEFS.manashield or nil)
    if not d then return nil end
    return d.localName or d.name
end
Click.SpellName = SpellName

local function Set(button, key, value)
    if button:GetAttribute(key) ~= value then button:SetAttribute(key, value) end
end

local function Arm(name)
    Set(catcher, "unit", "player")
    Set(catcher, "type1", "spell")
    Set(catcher, "spell1", name)
    for i = 1, #C.ALT_NOOPS do Set(catcher, C.ALT_NOOPS[i], C.NOOP) end
end

local function SeatCatcher(ox, oy)
    local k = ui(1)
    if seated and seated.x == ox and seated.y == oy and seated.k == k then return end
    local spx = MC.SPX
    Point(catcher, "TOPLEFT", ox + C.LEFT * spx, oy + C.TOP * spx)
    catcher:SetSize(ui(C.W * spx), ui(C.H * spx))
    seated = seated or {}
    seated.x, seated.y, seated.k = ox, oy, k
end

local function Wanted()
    if not Gunsight.IsActive() then return false end
    if Areas.AreaOf("class") == nil then return false end
    return SpellName() ~= nil
end

local function Apply()
    local want = Wanted()
    if want and not catcher then BuildCatcher() end
    if not catcher then return end
    if want then Arm(SpellName()) end
    SeatCatcher(Mage.Origin())
    if mouseOn ~= want then
        catcher:EnableMouse(want)
        mouseOn = want
    end
end

local function OnEvent(_, event)
    if event == "PLAYER_REGEN_ENABLED" and pending then Click.Sync() end
end

-- Anything that can change the catcher asks here. In combat nothing secure is touched: the ask waits for PLAYER_REGEN_ENABLED.
function Click.Sync()
    if not Mage.frame then return end
    if InCombat() then
        pending = true
        return
    end
    pending = false
    local ok, err = pcall(Apply)
    if not ok then
        pending = true
        LogOnce("apply", err)
    end
end

local subscribed = false
local function Request()
    if not events then
        events = CreateFrame("Frame")
        events:SetScript("OnEvent", OnEvent)
        events:RegisterEvent("PLAYER_REGEN_ENABLED")
    end
    if not subscribed then
        subscribed = true
        Data.Subscribe(function(reason) if reason == "learn" then Request() end end)
    end
    Click.Sync()
end

Mage.OnSeat(Request)
Areas.OnAreaChanged(Request)
Gunsight.OnActiveChanged(Request)
