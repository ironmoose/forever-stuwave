-- Forever STUwave: Gunsight Class Module for the Shaman (empty for now)
--
-- Registers the module "class" for SHAMAN with FS.GunsightAreas, which hosts it in the upper or lower area and calls
-- seat(rect) again on every rescale. The totem poles, the shock trace and the Fire Nova ring of Concept A
-- (mockups/gunsight-class-module-shaman-2026-10-08.html) are not drawn yet and get their own sections here when they
-- come. The first slice, the IMBUE and SHIELD chips, moved to the Shaman buff tab on the Console's top edge
-- (BuffTab.lua, with its data in ShamanBuffs.lua): they are a self buff reminder and belong on the player side, not
-- on the target side that hides with no target.
--
-- Until then the module is REGISTERED but draws nothing and listens to nothing: the registry still counts the Shaman as
-- having a class module, so the "coming soon" plate (GunsightClass.lua) does not show for it, and an area set to the Class
-- Module is simply empty. Anything added later follows the show/hide checklist in CombatHud/CLAUDE.md, and starts its
-- listeners only after a build that succeeded.

local _, FS = ...

local Gunsight = FS.Gunsight
local Areas = FS.GunsightAreas
if not (Gunsight and Gunsight.ui and Gunsight.Point and Gunsight.G) then return end
if not (Areas and Areas.RegisterModule) then return end

local function Build(host)
    local frame = CreateFrame("Frame", nil, host)
    frame:SetAllPoints(host)
    return frame
end

local function Seat() end
local function OnShow() end
local function OnHide() end

local ok, result = pcall(Areas.RegisterModule, "class", {
    classes = { "SHAMAN" },
    build = Build, seat = Seat, onShow = OnShow, onHide = OnHide,
})
if not ok or not result then
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightshaman_register",
            "|cffff4488Forever STUwave|r: gunsight shaman module: FS.GunsightAreas.RegisterModule refused the class module ("
            .. tostring(result) .. ")")
    end
end
