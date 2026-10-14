-- The runtime icon style: the game's OWN icon textures restyled live in the STUwave colours, so no art derived from
-- the game is shipped (the micro keys and the class tab spell tiles use it).
--
-- A styled icon is a stack of textures over the same rectangle, bottom to top:
--
--   base   the game's texture, desaturated (the client does that; SetDesaturated)
--   boost  an ADD copy of the same texture, as bright as the icon needs (data: boost, 0 plain to 1 twice as bright)
--   mod    one of our own ramp textures (iconramp_<family>.tga) in blend mode MOD: it multiplies the grey icon by a
--          gradient from the family's hot colour to its mid colour
--   lift   a flat low ADD of the family's weak colour, which tints the shadows
--
-- It is a gradient map the client can run: grey in, colour out. The baked look it replaces had per icon local contrast and
-- a six stop ramp, which the client cannot do, so this is flatter; the family colours and the idea are the same.
--
-- The stack is a "chain" (NewChain). Dress points it at an icon, Sync copies a state onto it: the tint (vertex colour),
-- the alpha, whether the icon is desaturated (the disabled look), shown or hidden. The data (family, boost) is generated
-- into Core/IconStyleData.lua by tools/assets/synthwave_icons.py --gen-runtime.
local _, FS = ...

local IconStyle = {}
FS.IconStyle = IconStyle

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local FALLBACK_FAMILY = "house_cyan"
-- draw sublevels above the base, in blend order: the ADD copy, the MOD ramp, the ADD lift
local BOOST_OFFSET, MOD_OFFSET, LIFT_OFFSET = 1, 2, 3
IconStyle.TOP_OFFSET = LIFT_OFFSET  -- how many sublevels a chain needs above its base (the harness reads it)
local MAX_SUBLEVEL = 7
-- below this the ADD copy is not worth a draw
local MIN_BOOST = 0.02

local function Ramps()
    local data = FS.IconStyleData
    return data and data.ramps
end

-- The ramp entry ({ file, lift }) of a family; an unknown one gets the house cyan.
function IconStyle.Ramp(family)
    local ramps = Ramps()
    if not ramps then return nil end
    return ramps[family] or ramps[FALLBACK_FAMILY]
end

-- The highest sublevel `base` may sit at so the chain still fits under the engine's limit (7).
function IconStyle.ClampSublevel(sub)
    return math.min(sub or 0, MAX_SUBLEVEL - LIFT_OFFSET)
end

-- Builds the overlay textures over `base`, in `parent` at `layer` and sublevels above `sub`. They follow the base's
-- rectangle (SetAllPoints on it) and start hidden. `sub` must already be clamped (ClampSublevel).
function IconStyle.NewChain(base, parent, layer, sub)
    local function overlay(offset, blend)
        local tex = parent:CreateTexture(nil, layer, nil, sub + offset)
        tex:SetBlendMode(blend)
        tex:SetAllPoints(base)
        tex:Hide()
        return tex
    end
    return {
        base = base,
        boost = overlay(BOOST_OFFSET, "ADD"),
        mod = overlay(MOD_OFFSET, "MOD"),
        lift = overlay(LIFT_OFFSET, "ADD"),
        look = nil, wantDesat = false, active = false,
    }
end

-- Points the chain at a game texture and a look ({ fam = family, boost = 0 to 1 }). `file` is what the base draws (a file
-- id or a path); `coords` (optional) the window of it, { left, right, top, bottom }. The base itself is not written here.
function IconStyle.Dress(chain, file, coords, look)
    local ramp = IconStyle.Ramp(look and look.fam)
    if not ramp then return false end
    chain.look = look
    chain.boost:SetTexture(file)
    chain.boost:SetDesaturated(true)
    if coords then chain.boost:SetTexCoord(coords[1], coords[2], coords[3], coords[4]) end
    chain.mod:SetTexture(MEDIA .. ramp.file)
    chain.mod:SetTexCoord(0, 1, 0, 1)
    local lift = ramp.lift
    chain.lift:SetColorTexture(lift[1], lift[2], lift[3], 1)
    chain.active = true
    return true
end

-- Copies a state onto the overlays. st = { r, g, b, a, desat, shown }: the tint and alpha the base wears, whether the
-- look is desaturated (the ramp then draws grey) and whether the icon is shown. The base itself is the caller's.
function IconStyle.Sync(chain, st)
    local look = chain.look
    if not look or not chain.active then return end
    local r, g, b, a = st.r or 1, st.g or 1, st.b or 1, st.a or 1
    local shown = st.shown ~= false
    local boost = look.boost or 0
    chain.boost:SetVertexColor(r * boost, g * boost, b * boost, a)
    chain.boost:SetShown(shown and boost >= MIN_BOOST)
    chain.mod:SetDesaturated(st.desat and true or false)
    chain.mod:SetShown(shown)
    local mean = (r + g + b) / 3
    chain.lift:SetVertexColor(1, 1, 1, a * mean)
    chain.lift:SetShown(shown)
end

-- Hides the overlays: the icon is plain again (the base's own desaturation is the caller's to restore).
function IconStyle.Release(chain)
    chain.active = false
    chain.boost:Hide()
    chain.mod:Hide()
    chain.lift:Hide()
end
