-- Forever STUwave: TooltipAnchor
-- FSTooltipAnchor is an invisible, mouse-disabled frame seated by the `tooltip` Layout entry
-- (/fsedit moves it). A post-hook on GameTooltip_SetDefaultAnchor re-points the default-anchored
-- tooltip to its BOTTOMRIGHT corner; tooltips anchored explicitly to a frame are never touched.

local _, FS = ...

FS.TooltipAnchor = FS.TooltipAnchor or {}
local TooltipAnchor = FS.TooltipAnchor

-- Only a tooltip left on ANCHOR_NONE is moved, so cursor tooltips stay on the cursor. Never throws into
-- Blizzard's caller: a failed re-point goes to the error handler.
function TooltipAnchor.Repoint(tooltip)
    local anchor = TooltipAnchor.frame
    if not (anchor and type(tooltip) == "table" and tooltip.SetPoint and tooltip.ClearAllPoints) then return end
    local ok, err = pcall(function()
        if tooltip.GetAnchorType and tooltip:GetAnchorType() ~= "ANCHOR_NONE" then return end
        tooltip:ClearAllPoints()
        tooltip:SetPoint("BOTTOMRIGHT", anchor, "BOTTOMRIGHT")
    end)
    if not ok then FS.Layout.ForwardError(err) end
end

-- Post-hook only: Blizzard's function is never replaced, and nothing is written to its tables.
function TooltipAnchor.Install()
    if TooltipAnchor.hooked then return end
    if type(hooksecurefunc) ~= "function" or type(_G.GameTooltip_SetDefaultAnchor) ~= "function" then return end
    TooltipAnchor.hooked = true
    hooksecurefunc("GameTooltip_SetDefaultAnchor", TooltipAnchor.Repoint)
end

-- Module power (Core/ModuleSwitch.lua): the anchor frame and the hook on the game's default tooltip anchor belong to the Window
-- skins switch. Off, tooltips sit where the game puts them and /fsedit shows no tooltip handle.
local function Start()
    -- The frame is plain and unprotected, so seating it is legal in combat.
    if not TooltipAnchor.frame then
        local anchor = CreateFrame("Frame", "FSTooltipAnchor", UIParent)
        anchor:EnableMouse(false)
        TooltipAnchor.frame = anchor
        FS.Layout.Apply(anchor, "tooltip")
    end

    TooltipAnchor.Install()
end
local MS = FS.ModuleSwitch
if MS then MS.WhenOn("m.skins", Start) else Start() end
