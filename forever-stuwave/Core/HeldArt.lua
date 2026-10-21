-- Forever STUwave: HeldArt
-- Keeps Blizzard's own art on a button or frame invisible while our chrome draws over it.
--
-- Clearing the art (SetTexture(nil)) is not an option: Blizzard re-asserts it on every state change
-- (ThreeSliceButtonMixin:UpdateButton re-SetAtlas on show, enable, disable and mouse down/up; the
-- UIPanelButton scripts re-SetTexture), and Hide() is undone by the same code. What survives all of it
-- is ALPHA: SetAtlas, SetTexture, Show and Hide leave a region's alpha alone. So a held region is
-- zeroed, and gets a post-hook on its own SetAlpha that writes 0 again (MicroBars.lua's recipe: a
-- per-REGION guard against our own write re-entering the hook, weak-keyed tables so nothing is kept alive).
--
-- What re-shows art is a NEW region, not a write to a held one: a button's SetNormalTexture/SetNormalAtlas
-- (and the pushed, highlight and disabled twins) can build a fresh state texture, so those methods get a
-- post-hook that re-sweeps whatever region exists now (HookSetters).
--
-- Textures and alpha only: never a script, an attribute, an anchor or a size, so it is safe on any
-- Blizzard button, including a protected one in combat.

local _, FS = ...

local HeldArt = {}
FS.HeldArt = HeldArt

local held = setmetatable({}, { __mode = "k" })     -- region -> zeroed and its SetAlpha hook installed
local zeroing = setmetatable({}, { __mode = "k" })  -- region -> our own write is in flight

local function ZeroRegion(region)
    if zeroing[region] then return end
    zeroing[region] = true
    pcall(region.SetAlpha, region, 0)
    zeroing[region] = nil
end

local function IsTexture(region)
    if type(region) ~= "table" or type(region.GetObjectType) ~= "function" then return false end
    local ok, kind = pcall(region.GetObjectType, region)
    return ok and kind == "Texture"
end

-- Holds one texture region at alpha 0. Idempotent; anything that is not a texture is ignored.
function HeldArt.Hold(region)
    if held[region] or not IsTexture(region) or type(region.SetAlpha) ~= "function" then return end
    ZeroRegion(region)
    if type(hooksecurefunc) ~= "function" then
        held[region] = true -- nothing to install, nothing to retry
        return
    end
    -- Recorded only once the hook is in, so a failed install is tried again on the next sweep.
    if pcall(hooksecurefunc, region, "SetAlpha", ZeroRegion) then held[region] = true end
end

-- Holds the button's normal texture whichever way it is reached: the NormalTexture parentKey, and
-- whatever GetNormalTexture hands back now (the engine can swap it for a new region, MoneyFrame_Update
-- does after ClearNormalTexture).
function HeldArt.HoldNormal(button)
    if type(button) ~= "table" then return end
    HeldArt.Hold(button.NormalTexture)
    if type(button.GetNormalTexture) == "function" then
        local ok, normal = pcall(button.GetNormalTexture, button)
        if ok then HeldArt.Hold(normal) end
    end
end

-- Post-hooks each of `methods` that exists on `button` with `sweep` (called with the button).
function HeldArt.HookSetters(button, methods, sweep)
    if type(hooksecurefunc) ~= "function" or type(button) ~= "table" then return end
    for _, method in ipairs(methods) do
        if type(button[method]) == "function" then pcall(hooksecurefunc, button, method, sweep) end
    end
end

local STATE_GETTERS = { "GetNormalTexture", "GetPushedTexture", "GetHighlightTexture", "GetDisabledTexture" }
local STATE_SETTERS = {
    "SetNormalTexture", "SetPushedTexture", "SetHighlightTexture", "SetDisabledTexture",
    "SetNormalAtlas", "SetPushedAtlas", "SetHighlightAtlas", "SetDisabledAtlas",
}

local function HoldStateTextures(button)
    for _, getter in ipairs(STATE_GETTERS) do
        if type(button[getter]) == "function" then
            local ok, region = pcall(button[getter], button)
            if ok then HeldArt.Hold(region) end
        end
    end
end

-- Holds ALL of a button's own art: every texture region it has now (the Left/Middle/Right slices and
-- Center of the stock templates are regions) except the ones in `keep` (a set keyed by region: our own
-- chrome, when a SkinButton ring or glow was drawn on the button first), plus its four state textures,
-- and re-sweeps the state textures when Blizzard swaps one in. Regions Blizzard creates later are not
-- swept: the region snapshot is taken once, so our textures created afterwards are never caught by it.
function HeldArt.HoldButton(button, keep)
    if type(button) ~= "table" then return end
    if type(button.GetRegions) == "function" then
        local ok, regions = pcall(function() return { button:GetRegions() } end)
        if ok then
            for _, region in ipairs(regions) do
                if not (keep and keep[region]) then HeldArt.Hold(region) end
            end
        end
    end
    HoldStateTextures(button)
    HeldArt.HookSetters(button, STATE_SETTERS, HoldStateTextures)
end
