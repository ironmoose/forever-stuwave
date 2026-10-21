-- Forever STUwave: ScrollBarSkins
-- The one scroll bar look, lifted out of the chat window (Chat.SkinChatScrollBar) so every skinned panel can
-- wear it. Blizzard's art goes invisible, one dim cyan rail runs the whole bar, and the thumb is a magenta
-- slice of the same rail texture that follows the thumb and comes up to full white under the mouse (the same
-- hover every other control in the panel has: the colour does not change, it just comes up to full).
--
-- SKIN ONLY on Blizzard's scroll bar templates (MinimalScrollBar and WowTrimScrollBar, the bars that sit
-- beside a ScrollBox). Textures, alpha and post-hooks on the thumb; never a script, an attribute, an anchor or
-- a size of a Blizzard frame, so a bar is safe to skin in combat. Where the bar sits is its owner's business:
-- the chat window seats its own bar, a panel keeps the place Blizzard gave it.
--
-- The art is held at alpha 0 (FS.HeldArt) rather than cleared: Blizzard re-asserts it on every state change
-- (the knob's atlases on hover and size changes, the WowTrim stepper Overlay on mouse-over), and its size
-- handler reads the knob's atlas back, which a cleared texture would hand it as nil. The tracks and the knob
-- are found by their atlases (every one names the scroll bar) and, for the regions that only get an atlas
-- on a state change, by their parentKeys.
--
-- THE TRACK IS A FRAME AND THE THUMB LIVES INSIDE IT, so a container is never hidden: hiding the Track would
-- take the thumb with it and the bar would look as though it had never been skinned. The steppers keep
-- their rect (the track measures against them) but stop taking clicks, because there is nothing left to see.

local _, FS = ...

local ScrollBarSkins = {}
FS.ScrollBarSkins = ScrollBarSkins

local COLOR_POWER = FS.Theme.COLOR_POWER   -- cyan: the rail
local COLOR_HEALTH = FS.Theme.COLOR_HEALTH -- magenta: the thumb, "you are away from the live edge"

-- media/scroll_rail.tga varies only ACROSS its width, so stretching it to any height is exact.
local RAIL_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\scroll_rail.tga"
local RAIL_ALPHA = 0.22
local THUMB_ALPHA = 0.95
-- The chat bar is 14 wide and that is the approved width of the rail. A wider bar (WowTrimScrollBar is 25)
-- gets a rail of this width, centred; a narrower one (MinimalScrollBar is 8) keeps its whole width.
local RAIL_MAX_WIDTH = 14

local skinned = setmetatable({}, { __mode = "k" }) -- bar -> { rail =, fill = }

local function IsTexture(region)
    if type(region) ~= "table" or type(region.GetObjectType) ~= "function" then return false end
    local ok, kind = pcall(region.GetObjectType, region)
    return ok and kind == "Texture"
end

local function Hold(region)
    if FS.HeldArt and IsTexture(region) then FS.HeldArt.Hold(region) end
end

local function ChildrenOf(obj)
    if type(obj.GetChildren) ~= "function" then return {} end
    local ok, list = pcall(function() return { obj:GetChildren() } end)
    return ok and list or {}
end

local function RegionsOf(obj)
    if type(obj.GetRegions) ~= "function" then return {} end
    local ok, list = pcall(function() return { obj:GetRegions() } end)
    return ok and list or {}
end

-- Holds every region in the subtree whose atlas names the scroll bar (the minimal-scrollbar-* and
-- UI-ScrollBar-* families), without hiding a container: the track is anchored between the steppers.
local function HoldAtlases(obj)
    for _, region in ipairs(RegionsOf(obj)) do
        if IsTexture(region) and type(region.GetAtlas) == "function" then
            local atlas = region:GetAtlas()
            if type(atlas) == "string" and atlas:lower():find("scrollbar", 1, true) then Hold(region) end
        end
    end
    for _, child in ipairs(ChildrenOf(obj)) do HoldAtlases(child) end
end

local function ThumbOf(bar)
    local track = bar.Track
    local thumb = type(track) == "table" and track.Thumb or nil
    return thumb or bar.Thumb
end

-- The regions the atlas sweep cannot see: the WowTrim backplate is a plain colour, and the knob and
-- stepper regions have no atlas until a state changes.
local function HoldKeyed(bar)
    Hold(bar.Backplate)
    local thumb = ThumbOf(bar)
    for _, owner in ipairs({ bar.Background, bar.Track, thumb }) do
        if type(owner) == "table" then
            for _, key in ipairs({ "Begin", "Middle", "End" }) do Hold(owner[key]) end
        end
    end
    for _, key in ipairs({ "Back", "Forward" }) do
        local stepper = bar[key]
        if type(stepper) == "table" then
            Hold(stepper.Texture)
            Hold(stepper.Overlay)
            if type(stepper.EnableMouse) == "function" then pcall(stepper.EnableMouse, stepper, false) end
        end
    end
end

-- The rail's horizontal extent: the bar's whole width, or RAIL_MAX_WIDTH centred on a wider bar. A bar with
-- no width yet takes the whole bar, whatever it becomes.
local function SeatRail(rail, bar)
    local width = type(bar.GetWidth) == "function" and bar:GetWidth() or 0
    if type(width) == "number" and width > RAIL_MAX_WIDTH then
        rail:SetPoint("TOP", bar, "TOP", 0, 0)
        rail:SetPoint("BOTTOM", bar, "BOTTOM", 0, 0)
        rail:SetWidth(RAIL_MAX_WIDTH)
    else
        rail:SetPoint("TOPLEFT", bar, "TOPLEFT", 0, 0)
        rail:SetPoint("BOTTOMRIGHT", bar, "BOTTOMRIGHT", 0, 0)
    end
end

-- A bar is a frame with a Track frame that holds a Thumb. Told by shape, not by name: the bars on most
-- panels are anonymous children (ChatFrame1.ScrollBar has no global). A horizontal bar needs a slice that
-- runs the other way, which nothing on a skinned panel uses, so it is not one.
function ScrollBarSkins.IsScrollBar(obj)
    if type(obj) ~= "table" or type(obj.Track) ~= "table" then return false end
    local thumb = obj.Track.Thumb
    if type(thumb) ~= "table" then return false end
    return thumb.isHorizontal ~= true
end

-- The pieces the skin drew on `bar` ({ rail, fill }), or nil when it has not been skinned.
function ScrollBarSkins.Parts(bar)
    return skinned[bar]
end

local function Build(bar, parts)
    HoldAtlases(bar)
    HoldKeyed(bar)

    -- The groove: one dim cyan line down the whole bar.
    local rail = bar:CreateTexture(nil, "BACKGROUND")
    rail:SetTexture(RAIL_TEXTURE)
    SeatRail(rail, bar)
    rail:SetVertexColor(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], RAIL_ALPHA)
    parts.rail = rail

    -- The slider: the same light in magenta at full strength, so it reads as the active thing in the
    -- groove exactly the way the live tab reads against the idle ones.
    local thumb = ThumbOf(bar)
    if type(thumb) ~= "table" or type(thumb.CreateTexture) ~= "function" then return end
    local fill = thumb:CreateTexture(nil, "ARTWORK")
    fill:SetTexture(RAIL_TEXTURE)
    -- Vertically from the THUMB, horizontally from the RAIL. The thumb keeps whatever width Blizzard gave it
    -- regardless of how wide the bar is, so anchoring all four edges to the thumb would pin the slider to
    -- that width and it would stop matching the groove. Split this way the slider is always exactly as wide
    -- as its rail and still tracks the thumb's position and length.
    fill:SetPoint("LEFT", rail, "LEFT", 0, 0)
    fill:SetPoint("RIGHT", rail, "RIGHT", 0, 0)
    fill:SetPoint("TOP", thumb, "TOP", 0, 0)
    fill:SetPoint("BOTTOM", thumb, "BOTTOM", 0, 0)
    fill:SetVertexColor(COLOR_HEALTH[1], COLOR_HEALTH[2], COLOR_HEALTH[3], THUMB_ALPHA)
    parts.fill = fill

    if type(thumb.HookScript) == "function" then
        thumb:HookScript("OnEnter", function() fill:SetVertexColor(1, 1, 1, 1) end)
        thumb:HookScript("OnLeave", function()
            fill:SetVertexColor(COLOR_HEALTH[1], COLOR_HEALTH[2], COLOR_HEALTH[3], THUMB_ALPHA)
        end)
    end
end

-- Skins one bar. Idempotent. Returns true when it skinned now, false when the bar was already skinned, is not
-- a bar it can skin, or failed part way (a bar is marked first so a failure is not retried into a second
-- rail; what was drawn before the failure stays).
function ScrollBarSkins.Skin(bar)
    if type(bar) ~= "table" or type(bar.CreateTexture) ~= "function" or skinned[bar] then return false end
    local parts = {}
    skinned[bar] = parts
    return pcall(Build, bar, parts)
end
