-- Forever STUwave: Gunsight Priest Class Module: CLICK THE SHIELD TO SHIELD
--
-- A left click on the big shield casts Power Word: Shield on the unit it watches: the friendly target, else the player. In and
-- out of combat. The catcher covers the shield's disc (rim included), not the Prayer of Mending half.
--
-- WHY A SEPARATE FILE. Casting from a click needs a SECURE button, and GunsightPriest.lua is plain frames only (a secure button
-- under a Gunsight host makes the host protected, and the host hides and shows with the target, which is blocked in combat).
-- So the catcher lives OUTSIDE the host tree exactly as GunsightWarriorClick.lua's do (read GunsightShamanDrop.lua's header for
-- the reasons): hung from Gunsight.root through a SecureUnitButtonTemplate holder with unit = "target" and RegisterUnitWatch
-- (the engine's own [@target,exists] show; hide; state drivers and snippets do not run on this client), seated with
-- Gunsight.Point, never shown or hidden by us.
--
-- FRIENDLY TARGET OR SELF, WITH NO ATTRIBUTE WRITE IN COMBAT. The decision is the secure template's own, made at click time
-- (SecureTemplates.lua, GetConvertedButtonUnitAndActionType, read from a 12.1 FrameXML copy; the Forever client's copy is
-- assumed to match): the catcher carries unit = "target", and "harmbutton1" remaps the left button to the virtual button
-- "fsself" when UnitCanAttack("player", unit). So:
--   * a target we can assist:      type1 = "spell", spell1 = the shield's name, cast on "target";
--   * a target we can attack:      harmbutton1 -> "fsself": type-fsself = "spell", spell-fsself = the name, unit-fsself = "player";
--   * a target that is neither (a neutral we cannot assist, an unflagged enemy player): the template leaves the button alone
--     and casts on "target"; the client refuses it (or, with autoSelfCast, may shield the player). The module itself watches
--     the player then. UNPROVEN LIVE: that neutral case, and that this client's SecureTemplates parse harmbutton like 12.1's.
-- Every attribute is written out of combat; nothing changes per target, so a target switch in combat needs no write. Alt forms
-- of the left click are empty types (the Warrior helm's rule); other modifiers find no attribute and do nothing.
--
-- WHEN THE CATCHER TAKES THE MOUSE (decided out of combat only; a change in combat sets `pending` and PLAYER_REGEN_ENABLED
-- replays it): the Priest class module is in an area (Areas.AreaOf("class")), the Gunsight is the display (Gunsight.IsActive())
-- and Power Word: Shield is known (PriestShields). A shield learned in combat gets its catcher at regen. Accepted limits, the
-- Shaman pole click's: an area move, a reassigned area, or the dot piece or the master switch turned off in combat leaves the
-- catcher as it was, mouse on included, until regen, so a left click on the invisible shield still casts meanwhile. Right and
-- middle clicks pass through where the client allows; where it cannot, the catcher keeps the mouse, one chat line says so, and
-- a right drag camera turn that starts over the shield is swallowed.
--
-- Nothing here is verified in game; the harness is a strict mock.

local _, FS = ...

local Gunsight = FS.Gunsight
local Areas = FS.GunsightAreas
local Priest = FS.GunsightPriest
local Data = FS.PriestShields
if not (Gunsight and Gunsight.ui and Gunsight.Point and Gunsight.root and Gunsight.IsActive and Gunsight.OnActiveChanged) then return end
if not (Areas and Areas.AreaOf and Areas.OnAreaChanged) then return end
if not (Priest and Priest.C and Priest.Origin and Priest.OnSeat) then return end
if not (Data and Data.ShieldKnown and Data.Subscribe and Data.DEFS) then return end

FS.GunsightPriestClick = FS.GunsightPriestClick or {}
local Click = FS.GunsightPriestClick

local ui, Point = Gunsight.ui, Gunsight.Point
local PC = Priest.C

local C = {
    -- the shield's disc, sprite px from the module's top left, one px of slack round it for the hit shake
    LEFT = PC.SHIELD.cx - PC.SHIELD.r - 1,
    TOP = PC.SHIELD.cy - PC.SHIELD.r - 1,
    SIZE = 2 * PC.SHIELD.r + 3,
    LEVEL = 4,                  -- frame levels above the module frame
    SELF = "fsself",            -- the virtual button a hostile target remaps the left click to
    ALT_NOOPS = { "alt-type1", "alt-shift-type1", "alt-ctrl-type1", "alt-ctrl-shift-type1" },
    NOOP = "",                  -- Blizzard's ATTRIBUTE_NOOP
    NAME = "ForeverSTUwaveGunsightShield",
}
Click.C = C

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightpriestclick_" .. key,
            "|cffff4488Forever STUwave|r: gunsight priest module: " .. tostring(msg))
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
        LogOnce("nounitwatch", "the shield click is off: this client has no unit watch.")
        return nil
    end
    local module = Priest.frame
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
        LogOnce("passthrough", "a right or middle click that starts over the shield is taken by the shield: this client cannot pass them through.")
    end
    catcher = button
    Click.catcher = button
    return button
end

local function SpellName()
    local d = Data.DEFS.shield
    return d.localName or d.name
end

local function Set(button, key, value)
    if button:GetAttribute(key) ~= value then button:SetAttribute(key, value) end
end

local function Arm()
    local name = SpellName()
    Set(catcher, "unit", "target")
    Set(catcher, "type1", "spell")
    Set(catcher, "spell1", name)
    Set(catcher, "harmbutton1", C.SELF)
    Set(catcher, "type-" .. C.SELF, "spell")
    Set(catcher, "spell-" .. C.SELF, name)
    Set(catcher, "unit-" .. C.SELF, "player")
    for i = 1, #C.ALT_NOOPS do Set(catcher, C.ALT_NOOPS[i], C.NOOP) end
end

local function SeatCatcher(ox, oy)
    local k = ui(1)
    if seated and seated.x == ox and seated.y == oy and seated.k == k then return end
    local spx = PC.SPX
    Point(catcher, "TOPLEFT", ox + C.LEFT * spx, oy + C.TOP * spx)
    catcher:SetSize(ui(C.SIZE * spx), ui(C.SIZE * spx))
    seated = seated or {}
    seated.x, seated.y, seated.k = ox, oy, k
end

local function Wanted()
    if not Gunsight.IsActive() then return false end
    if Areas.AreaOf("class") == nil then return false end
    return Data.ShieldKnown() == true
end

local function Apply()
    local want = Wanted()
    if want and not catcher then BuildCatcher() end
    if not catcher then return end
    if want then Arm() end
    SeatCatcher(Priest.Origin())
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
    if not Priest.frame then return end
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

Priest.OnSeat(Request)
Areas.OnAreaChanged(Request)
Gunsight.OnActiveChanged(Request)
