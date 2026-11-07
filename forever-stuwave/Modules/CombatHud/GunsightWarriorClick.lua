-- Forever STUwave: Gunsight Warrior Class Module: CLICK A HELM TO SHOUT
--
-- A left click on the Battle Shout helm casts Battle Shout; a left click on the Demoralizing Shout helm casts Demoralizing
-- Shout. In and out of combat. The catcher covers the helm's whole sprite box (the beard included), not the rune ring.
--
-- WHY A SEPARATE FILE. Casting from a click needs a SECURE button, and GunsightWarrior.lua is plain frames only (a secure button
-- under a Gunsight host makes the host protected, and the host hides and shows with the target, which is blocked in combat).
-- So the catchers live OUTSIDE the host tree exactly as GunsightShamanDrop.lua's pole catchers do (read its header for the
-- reasons): hung from Gunsight.root through a SecureUnitButtonTemplate holder with unit = "target" and RegisterUnitWatch (the
-- engine's own [@target,exists] show; hide; state drivers and snippets do not run on this client), seated with Gunsight.Point,
-- never shown or hidden by us.
--
-- WHAT A CATCHER CASTS: type1 = "spell", spell1 = the shout's name (the client's own name read by WarriorShouts, else the
-- English one), so the highest known rank is cast. Every Alt form is an empty type. No unit attribute.
--
-- WHEN A CATCHER TAKES THE MOUSE (decided out of combat only; a change in combat sets `pending` and PLAYER_REGEN_ENABLED
-- replays it): the Warrior class module is in an area (Areas.AreaOf("class")), the Gunsight is the display
-- (Gunsight.IsActive()) and the shout is known (WarriorShouts). A shout learned in combat gets its catcher at regen.
-- Accepted limits, the Shaman pole click's: an area move, a reassigned area, or the dot piece or the master switch turned off
-- in combat leaves the catchers as they were, mouse on included, until regen, so a left click on the invisible helm still
-- shouts meanwhile. Right and middle clicks pass through where the client allows; where it cannot, the catchers keep the mouse,
-- one chat line says so, and a right drag camera turn that starts over a helm is swallowed.
--
-- Nothing here is verified in game; the harness is a strict mock.

local _, FS = ...

local Gunsight = FS.Gunsight
local Areas = FS.GunsightAreas
local Warrior = FS.GunsightWarrior
local Shouts = FS.WarriorShouts
if not (Gunsight and Gunsight.ui and Gunsight.Point and Gunsight.root and Gunsight.IsActive and Gunsight.OnActiveChanged) then return end
if not (Areas and Areas.AreaOf and Areas.OnAreaChanged) then return end
if not (Warrior and Warrior.C and Warrior.Origin and Warrior.OnSeat) then return end
if not (Shouts and Shouts.Get and Shouts.Subscribe and Shouts.DEFS) then return end

FS.GunsightWarriorClick = FS.GunsightWarriorClick or {}
local Click = FS.GunsightWarriorClick

local ui, Point = Gunsight.ui, Gunsight.Point
local W = Warrior.C

local C = {
    -- the helm's sprite box, sprite px from the module's top left: the HELM_W x HELM_H sprite seated at
    -- (cx - 13 - HELM_OX, CY - 12), one px of slack round it for the breathing lift and the roar's jump
    LEFT = -13 - W.HELM_OX - 1,
    TOP = W.CY - 12 - 1,
    W = W.HELM_W + 2,
    H = W.HELM_H + 2,
    LEVEL = 4,                  -- frame levels above the module frame
    ALT_NOOPS = { "alt-type1", "alt-shift-type1", "alt-ctrl-type1", "alt-ctrl-shift-type1" },
    NOOP = "",                  -- Blizzard's ATTRIBUTE_NOOP
    NAME = "ForeverSTUwaveGunsightShout",
    KEYS = { "battle", "demo" },
}
Click.C = C

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightwarriorclick_" .. key,
            "|cffff4488Forever STUwave|r: gunsight warrior module: " .. tostring(msg))
    end
end

local function InCombat()
    return type(InCombatLockdown) == "function" and InCombatLockdown() and true or false
end

local holder
local catchers = {}            -- key -> its secure button (built only for a known shout, out of combat)
local mouseOn = {}
local seated = {}
local pending = false
local events
Click.catchers = catchers

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
        LogOnce("nounitwatch", "the helm click is off: this client has no unit watch.")
        return false
    end
    local module = Warrior.frame
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

local function BuildCatcher(key)
    if catchers[key] then return catchers[key] end
    if not BuildHolder() then return nil end
    local button = CreateFrame("Button", C.NAME .. (key == "battle" and "Battle" or "Demo"), holder, "SecureActionButtonTemplate")
    button:RegisterForClicks("AnyUp", "AnyDown")
    button:SetFrameLevel(holder:GetFrameLevel() + 1)
    button:EnableMouse(false)
    if not PassClicksThrough(button) then
        LogOnce("passthrough", "a right or middle click that starts over a shout helm is taken by the helm: this client cannot pass them through.")
    end
    button.fsKey = key
    catchers[key] = button
    mouseOn[key] = false
    return button
end

local function SpellName(key)
    local st = Shouts.Get(key)
    return (st and st.localName) or Shouts.DEFS[key].name
end

local function Arm(key)
    local button = catchers[key]
    local name = SpellName(key)
    if button:GetAttribute("type1") ~= "spell" then button:SetAttribute("type1", "spell") end
    if button:GetAttribute("spell1") ~= name then button:SetAttribute("spell1", name) end
    for i = 1, #C.ALT_NOOPS do
        local a = C.ALT_NOOPS[i]
        if button:GetAttribute(a) ~= C.NOOP then button:SetAttribute(a, C.NOOP) end
    end
end

local function SeatCatcher(key, ox, oy)
    local button = catchers[key]
    local k = ui(1)
    local at = seated[key]
    if at and at.x == ox and at.y == oy and at.k == k then return end
    local spx = W.SPX
    Point(button, "TOPLEFT", ox + (W.RINGS[key].cx + C.LEFT) * spx, oy + C.TOP * spx)
    button:SetSize(ui(C.W * spx), ui(C.H * spx))
    if not at then
        at = {}
        seated[key] = at
    end
    at.x, at.y, at.k = ox, oy, k
end

local function Wanted(key)
    if not Gunsight.IsActive() then return false end
    if Areas.AreaOf("class") == nil then return false end
    local st = Shouts.Get(key)
    return st ~= nil and st.known == true
end

local function Apply()
    local ox, oy = Warrior.Origin()
    for i = 1, #C.KEYS do
        local key = C.KEYS[i]
        local want = Wanted(key)
        local button = catchers[key]
        if want and not button then button = BuildCatcher(key) end
        if button then
            if want then Arm(key) end
            SeatCatcher(key, ox, oy)
            local on = want and true or false
            if mouseOn[key] ~= on then
                button:EnableMouse(on)
                mouseOn[key] = on
            end
        end
    end
end

local function OnEvent(_, event)
    if event == "PLAYER_REGEN_ENABLED" and pending then Click.Sync() end
end

-- Anything that can change a catcher asks here. In combat nothing secure is touched: the ask waits for PLAYER_REGEN_ENABLED.
function Click.Sync()
    if not Warrior.frame then return end
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
        Shouts.Subscribe(function(_, reason) if reason == "learn" then Request() end end)
    end
    Click.Sync()
end

Warrior.OnSeat(Request)
Areas.OnAreaChanged(Request)
Gunsight.OnActiveChanged(Request)
