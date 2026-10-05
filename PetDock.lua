-- PetDock.lua: the pet panel's CHROME (fill, stroke, halo, and the red low-HP edge twin) in two
-- modes, split out of PetFrame.lua (step S6 of the pet console dock port).
--
--   "float" (what a build with no drawn Console shows): the closed cut box PetFrame drew itself
--     before this file existed, the same two AddCut2Texture calls (the nine-sliced outline in
--     COLOR_POWER, the nine-sliced COLOR_HUD_SCRIM fill), pixel identical.
--   "dock": the open shoulder of the approved Gunsight mockup, option C (drawPet's dc branch,
--     peTrace with open = true). Top-left cut 6, a straight left side, the right foot flaring 10 px
--     at 45 degrees, the BOTTOM OPEN (the Console chassis closes it: no stroke, no halo), the fill
--     running 1.2 below the stroke so it merges into the chassis.
--
-- WHAT THE DOCK IS MADE OF (design px, art-local, y down, 1 unit = 1 design px because the art
-- frame is scaled by FS.Layout.Scale(), like Console.lua's art):
--   fill    COLOR_HUD_SCRIM, flat rects plus the baked TL c6 cut piece, and for the flare the
--           media/tab_slant.tga wedge flipped horizontally (solid bottom left, a "\" hypotenuse):
--           CastBars.lua's trick for a leaning edge, since a rect cannot lean.
--   stroke  Console.lua's recipe: plain 1 texel lines (top, left, right) plus the baked TL c6
--           corner piece (Theme.BORDER_CUT_TEXTURES[6][1]); the flare band is its own baked piece
--           (media/pet_dock_flare_line.tga). The literal "stroke wedge under the fill wedge" of
--           CastBars.lua does not work here: that fill is translucent, so a solid violet wedge under
--           it would tint the whole triangle. Baking just the 1 px band avoids that.
--   halo    DECOMPOSED strips, never a nine-slice (a nine-slice would light the open bottom and
--           the interior): glow_edge.tga along the top, left and right runs, glow_corner.tga at the
--           top right, glow_corner_cut.tga at the top left, and media/pet_dock_flare_glow.tga for the
--           last C.REACH px of the right run plus the flare (a 45 degree edge cannot be a strip).
--           Nothing is drawn below y = H.
-- The two baked pieces come from media/generate_pet_dock_flare.py; every number it uses is in the C
-- table below and petdock-harness.py rasterizes the REAL files against the mockup.
--
-- SetMode only Shows and Hides non-secure CHILD frames of the pet container. The container is
-- implicitly protected (it parents the secure pet buttons: no Show, Hide, SetPoint or SetSize in
-- combat), so this file never calls any method on it: it only parents frames to it.
--
-- DOCKING (S8): Refresh decides between the two. While Console.IsDrawn() the panel is DOCKED: the
-- container's BOTTOMLEFT on FSConsole's TOPLEFT at (DOCK_X * scale, 0) (FS.PetFrame.SeatDocked, which
-- owns the container), the dock chrome, and the Console's top outline and halo opened under the panel
-- and its flare (Console.SetDockGap) for as long as the panel is shown. Otherwise (/fsconsole off, the
-- Console style off, /fsbars blizz, a build with no Console, or a dock chrome that failed to build)
-- it FLOATS: back on UIParent at its float seat (FS.PetFrame.SeatFloat), the closed float chrome, the
-- gap closed. Everything that touches the protected container or the Console's frames waits for
-- PLAYER_REGEN_ENABLED in combat (pendingDock); the Console is never anchored to the pet (the pet
-- anchors to the Console, one way). Refresh runs from FS.ActionBars.OnGeometry (every Console
-- seat, toggle and /fsbars switch, the Console's own callback having run first), from the pet
-- panel's visibility gate (SetPetShown), from PetFrame's rescale and at regen.
--
-- LOW HP (S7): the pet's health is secret in combat, so the low look is driven by ALPHA through
-- FS.PetFrame.SetLowHealthEdge(redEdge, { normalEdge }, pulseGroup): the red edge host takes the
-- Step curve's alpha, the normal edge frame the inverse, so a low pet shows red only (no cyan or
-- violet showing through the pulse trough). Each mode has its own red twin (same geometry, in
-- COLOR_RED); SetMode hands PetFrame the active mode's pair. PetFrame calls
-- FS.PetDock.AttachLowHealth() right after it builds the low-HP layer.
-- FS.PetDock.edge is the active mode's { host, pulseFrame, group, normal, base } hook;
-- FS.PetDock.edges.<mode> are both.
--
-- Headless check: python3 addons/petdock-harness.py

local _, FS = ...
FS.PetDock = FS.PetDock or {}
local PetDock = FS.PetDock

local Theme = FS.Theme

-------------------------------------------------------------------------------
-- Constants (design px). The mockup names are in the comments; the harness parses them back out
-- of the mockup HTML, so a mockup move fails there.
-------------------------------------------------------------------------------

local MEDIA = "Interface\\AddOns\\ForeverSynthwave\\media\\"
local FLARE_LINE_TEXTURE = MEDIA .. "pet_dock_flare_line.tga"
local FLARE_GLOW_TEXTURE = MEDIA .. "pet_dock_flare_glow.tga"
local WEDGE_TEXTURE = MEDIA .. "tab_slant.tga"

local C = {
    W = 348,             -- PE_G.dc.W, replaced at build by FS.Layout.petcontainer.w
    H = 68,              -- PE_G.dc.H, replaced at build by FS.Layout.petcontainer.h
    CUT = 6,             -- peTrace's c: the top-left cut
    FLARE = 10,          -- drawPet's f: the right foot's flare
    FILL_OVER = 1.2,     -- the fill polygon's overrun below the stroke (H + 1.2)
    -- Docked: the dock's left edge, design px right of the Console chassis' left edge (the mockup's
    -- PE_X less the chassis left, drawPet's open branch; the harness derives it). The Console's top
    -- line opens from DOCK_X - 1 to DOCK_X + W + FLARE + 1: one px of line either side of the panel
    -- and its right foot.
    DOCK_X = 24,
    LINE = 1,            -- the stroke is 1 texel, like Console.lua's (LINE)
    REACH = 7,           -- the mockup HALO table's widest radius
    STROKE_ALPHA = 0.9,  -- A(.9) on the stroke
    -- The red twin's stroke: the mockup's low stroke is A(.6 + .4 * pulse), which PEAKS at 1.0. The
    -- twin's Alpha animation (PULSE_TOP down to PULSE_FLOOR) multiplies this vertex alpha, so it
    -- must be 1.0 for the stroke to reach the mockup's peak (the normal stroke stays at .9).
    LOW_STROKE_ALPHA = 1.0,
    HALO_ALPHA = 0.76,   -- the HALO table's stacked alpha (.585) x the pet panel's glow factor 1.3
    -- Mirrors PetFrame.lua's LOW_PULSE_* and LOW_EDGE_GLOW_ALPHA (the harness compares them).
    PULSE_TOP = 1.0,
    PULSE_FLOOR = 0.6,
    PULSE_LEG = 0.55,
    LOW_GLOW_ALPHA = 0.5,
    -- The baked pieces: a 128 canvas with the piece at its top left, k texels per design px.
    CANVAS = 128,
    LINE_K = 10,         -- pet_dock_flare_line.tga
    GLOW_K = 7,          -- pet_dock_flare_glow.tga
    CUT_CANVAS = 16,     -- Theme's cut pieces: a 16 canvas, the piece at the top left
}
PetDock.C = C

-------------------------------------------------------------------------------
-- State
-------------------------------------------------------------------------------

local container
local built = false
local lowReady = false          -- PetFrame built its low-HP layer
local mode = "float"
local pendingScale = false
local pendingDock = false          -- a Refresh waits for regen (combat, or the Console refused the gap)
local petShown = false             -- the pet panel's visibility gate says shown (PetFrame.Apply)
local gapOpen = false              -- the Console's top line is open under the panel (SetDockGap)

local frames = {}               -- frames.float, frames.dock: the chrome roots (the only things Shown / Hidden)
local edges = {}                -- edges.float, edges.dock: { host, pulseFrame, group, normal, base }
local function NewDockParts()
    return { fill = {}, stroke = {}, halo = {}, red = { stroke = {}, halo = {} } }
end
local parts = {                 -- texture handles, for the harness and the retint hook
    float = {},
    dock = NewDockParts(),
}
PetDock.frames, PetDock.edges, PetDock.parts = frames, edges, parts

-------------------------------------------------------------------------------
-- Helpers
-------------------------------------------------------------------------------

-- Seats a texture at design px (x, y down) of `art`, w x h.
local function Place(art, tex, x, y, w, h)
    tex:ClearAllPoints()
    tex:SetPoint("TOPLEFT", art, "TOPLEFT", x, -y)
    tex:SetSize(w, h)
end

local function NewTexture(frame, layer, texture, blend)
    local tex = frame:CreateTexture(nil, layer)
    tex:SetTexture(texture)
    if blend then tex:SetBlendMode(blend) end
    return tex
end

-- A plain frame filling `parent`, at an explicit level (a chrome frame must not take the child
-- default of parent + 1 at the roots: the slots sit strictly higher by frame level, SLOT_LEVEL_OFFSET = 2).
local function NewLayer(parent, level)
    local frame = CreateFrame("Frame", nil, parent)
    frame:SetAllPoints(parent)
    frame:SetFrameLevel(level)
    return frame
end

-- The pulse of the red edge: the mockup's .6 + .4 * pulse on a 1.1 s period, as a bouncing Alpha
-- animation on a CHILD of the curve driven host, so the two alphas multiply.
local function NewPulse(frame)
    local group = frame:CreateAnimationGroup()
    group:SetLooping("BOUNCE")
    local pulse = group:CreateAnimation("Alpha")
    pulse:SetFromAlpha(C.PULSE_TOP)
    pulse:SetToAlpha(C.PULSE_FLOOR)
    pulse:SetDuration(C.PULSE_LEG)
    pulse:SetSmoothing("IN_OUT")
    return group
end

local function Tint(tex, color, alpha)
    tex:SetVertexColor(color[1], color[2], color[3], alpha)
end

-------------------------------------------------------------------------------
-- Dock chrome
-------------------------------------------------------------------------------

-- Texcoord of a baked cut piece sitting at the top left of its 16 canvas.
local function CutPieceCoord(c)
    local u = c / C.CUT_CANVAS
    return 0, u, 0, u
end

-- The fill: scrim flat rects plus the baked TL cut piece, and the flipped tab_slant wedge for
-- the flare. The wedge's hypotenuse lies on the stroke's centreline.
local function BuildDockFill(art)
    local W, H, c, f, over = C.W, C.H, C.CUT, C.FLARE, C.FILL_OVER
    local fx = W - C.LINE / 2          -- where the flare's centreline leaves the right line
    local scrim = Theme.COLOR_HUD_SCRIM
    local list = parts.dock.fill
    local function piece(texture, x, y, w, h, l, r, t, b)
        local tex = NewTexture(art, "BACKGROUND", texture)
        Tint(tex, scrim, scrim[4])
        if l then tex:SetTexCoord(l, r, t, b) end
        Place(art, tex, x, y, w, h)
        list[#list + 1] = tex
        return tex
    end
    piece(Theme.FILL_CUT_TEXTURES[c], 0, 0, c, c, CutPieceCoord(c))
    piece(Theme.FLAT_TEXTURE, c, 0, W - c, c)
    piece(Theme.FLAT_TEXTURE, 0, c, W, H - f - c)
    piece(Theme.FLAT_TEXTURE, 0, H - f, fx, f + over)
    piece(WEDGE_TEXTURE, fx, H - f, f + over, f + over, 1, 0, 0, 1)
end

-- The stroke: 1 texel lines, the baked TL corner, the baked flare band. Built into `frame`.
local function BuildDockStroke(art, frame, color, list, alpha)
    local W, H, c, f, line = C.W, C.H, C.CUT, C.FLARE, C.LINE
    local function piece(texture, x, y, w, h, l, r, t, b)
        local tex = NewTexture(frame, "BORDER", texture)
        Tint(tex, color, alpha)
        if l then tex:SetTexCoord(l, r, t, b) end
        Place(art, tex, x, y, w, h)
        list[#list + 1] = tex
    end
    piece(Theme.BORDER_CUT_TEXTURES[c][1], 0, 0, c, c, CutPieceCoord(c))
    piece(Theme.FLAT_TEXTURE, c, 0, W - c, line)                 -- top
    piece(Theme.FLAT_TEXTURE, 0, c, line, H - c)                 -- left
    piece(Theme.FLAT_TEXTURE, W - line, 0, line, H - f)          -- right, down to the flare
    -- The flare band: 12 x 10 px from (W - 2, H - f), a 1 px stroke along (W - .5, H - f) to the foot.
    local bandW = f + 2
    piece(FLARE_LINE_TEXTURE, W - 2, H - f, bandW, f,
        0, bandW * C.LINE_K / C.CANVAS, 0, f * C.LINE_K / C.CANVAS)
end

-- The halo: strips only, nothing below y = H. Built into `frame`.
local function BuildDockHalo(art, frame, color, list)
    local W, H, c, f, r = C.W, C.H, C.CUT, C.FLARE, C.REACH
    local function piece(texture, x, y, w, h, ...)
        local tex = NewTexture(frame, "BACKGROUND", texture, "ADD")
        Tint(tex, color, C.HALO_ALPHA)
        tex:SetTexCoord(...)
        Place(art, tex, x, y, w, h)
        list[#list + 1] = tex
    end
    -- The same orientations Theme.AddOuterGlow gives its strips: the bright end faces the stroke.
    piece(Theme.GLOW_CORNER_CUT_TEXTURE, -r, -r, c + r, c + r, 0, 1, 0, 1)                 -- around the TL cut
    piece(Theme.GLOW_EDGE_TEXTURE, c, -r, W - c, r, 0, 1, 0, 0, 1, 1, 1, 0)               -- top
    piece(Theme.GLOW_CORNER_TEXTURE, W, -r, r, r, 0.5, 0, 0.5, 0.5, 1, 0, 1, 0.5)         -- the square TR corner
    piece(Theme.GLOW_EDGE_TEXTURE, W, 0, r, H - f - r, 0, 0, 0, 0, 0, 1, 0, 1)            -- right, down to the flare zone
    local zone = f + r
    local u = zone * C.GLOW_K / C.CANVAS
    piece(FLARE_GLOW_TEXTURE, W, H - f - r, zone, zone, 0, u, 0, u)                         -- the vertex and the flare
    piece(Theme.GLOW_EDGE_TEXTURE, -r, c, r, H - c, 0, 1, 0, 1, 0, 0, 0, 0)               -- left
end

local function FillEdge(art, frame, color, strokeList, haloList, strokeAlpha)
    BuildDockHalo(art, frame, color, haloList)
    BuildDockStroke(art, frame, color, strokeList, strokeAlpha)
end

local function BuildDock()
    local W, H = C.W, C.H
    local level = container:GetFrameLevel()
    local art = CreateFrame("Frame", nil, container)
    art:SetFrameLevel(level)
    art:SetPoint("TOPLEFT", container, "TOPLEFT", 0, 0)
    art:SetSize(W, H)
    art:SetScale(FS.Layout.Scale())
    frames.dock = art
    BuildDockFill(art)

    -- The normal edge (violet, the mockup's `col`), one frame so the inverse curve can fade it.
    local normal = NewLayer(art, level)
    FillEdge(art, normal, Theme.COLOR_BORDER, parts.dock.stroke, parts.dock.halo, C.STROKE_ALPHA)

    -- The red twin: host (the curve alpha) > pulse child (the Alpha animation) > the same geometry in red.
    local host = NewLayer(art, level + 1)
    host:SetAlpha(0)
    local pulseFrame = NewLayer(host, level + 1)
    FillEdge(art, pulseFrame, Theme.COLOR_RED, parts.dock.red.stroke, parts.dock.red.halo, C.LOW_STROKE_ALPHA)
    edges.dock = { host = host, pulseFrame = pulseFrame, group = NewPulse(pulseFrame), normal = normal,
        base = { normal } }
end

-- The dock chrome is built in its OWN pcall, so a throw in the unused dock art can never take the
-- approved default float look (or the rest of the pet UI) down with it: PetFrame calls Build inside
-- its own pcall, and one throw here used to abort the whole container. A failure is logged once, the
-- half built art is hidden and forgotten, and the panel stays in "float" (SetMode("dock") then
-- refuses). Built eagerly rather than lazily on the first SetMode("dock"): Build runs out of combat
-- (PetFrame defers its init to PLAYER_REGEN_ENABLED), and everything that parents to the protected
-- container has to happen there.
local function TryBuildDock()
    local ok, err = pcall(BuildDock)
    if ok then return true end
    if frames.dock then pcall(frames.dock.Hide, frames.dock) end   -- the art is a child of the container
    frames.dock, edges.dock = nil, nil
    parts.dock = NewDockParts()
    FS.LogDegradeOnce("petdock_dock_build",
        "|cffff4488ForeverSynthwave|r: pet dock chrome failed to build (" .. tostring(err)
            .. "); the floating pet panel is used instead.")
    return false
end

-------------------------------------------------------------------------------
-- Float chrome: exactly what PetFrame built before the move
-------------------------------------------------------------------------------

local function BuildFloat()
    local level = container:GetFrameLevel()
    local root = NewLayer(container, level)
    frames.float = root

    -- The outline on its own frame so the inverse curve can fade it; it draws below every slot.
    local outline = NewLayer(root, level)
    parts.float.outline = Theme.AddCut2Texture(outline, Theme.SLICE_CUT2_OUTLINE_TEXTURE, Theme.COLOR_POWER, "BORDER")

    -- Dark interior fill: a nine-sliced chamfer texture at inset 0 so it meets the stroke flush,
    -- BACKGROUND, behind every slot. COLOR_HUD_SCRIM is the Gunsight panel fill.
    parts.float.fill = Theme.AddCut2Texture(root, Theme.SLICE_CUT2_FILL_TEXTURE, Theme.COLOR_HUD_SCRIM,
        "BACKGROUND", nil, 0)

    -- The red twin: PetFrame's own default recipe (ring plus glow on the panel rect).
    local host = NewLayer(root, level + 1)
    host:SetAlpha(0)
    local pulseFrame = NewLayer(host, level + 1)
    Theme.SkinButton(pulseFrame, {
        chamfer = Theme.SLICE_CUT_MARGIN,
        glowAlpha = C.LOW_GLOW_ALPHA,
        borderColor = Theme.COLOR_RED,
    })
    local skin = pulseFrame.fsSkin
    if skin then
        local red = Theme.COLOR_RED
        skin.border.ring:SetVertexColor(red[1], red[2], red[3], 1)
        skin.glow:SetVertexColor(red[1], red[2], red[3], C.LOW_GLOW_ALPHA)
    end
    edges.float = { host = host, pulseFrame = pulseFrame, group = NewPulse(pulseFrame), normal = outline,
        base = { outline } }
end

-------------------------------------------------------------------------------
-- Mode
-------------------------------------------------------------------------------

-- Hands PetFrame the active mode's red edge and normal edge (the low-HP layer drives their alphas).
-- SetLowHealthEdge hides the previous red host, so the new one is shown first.
local function AttachLow()
    local petFrame = FS.PetFrame
    if not (lowReady and built and petFrame and petFrame.SetLowHealthEdge) then return end
    local edge = edges[mode]
    edge.host:Show()
    if petFrame.SetLowHealthEdge(edge.host, edge.base, edge.group) then
        petFrame.lowEdgePulse = edge.pulseFrame
    end
end

local function Apply()
    local other = mode == "dock" and "float" or "dock"
    frames[mode]:Show()
    if frames[other] then frames[other]:Hide() end   -- no dock frame when the dock build failed
    PetDock.edge = edges[mode]
    AttachLow()
end

-- "dock" or "float". Remembers the mode before the panel is built and applies it then. Only Shows and
-- Hides this file's own non-secure frames, so it is legal in combat; the container is never touched.
-- False (and nothing changes) for any other value, and for "dock" once the dock chrome failed to build
-- (the floating panel stays).
function PetDock.SetMode(newMode)
    if newMode ~= "dock" and newMode ~= "float" then return false end
    if newMode == "dock" and built and not frames.dock then return false end
    mode = newMode
    if built then Apply() end
    return true
end

function PetDock.GetMode()
    return mode
end

-- Returns true only after Build when the dock chrome built successfully.
function PetDock.HasDock()
    return frames.dock ~= nil
end

-------------------------------------------------------------------------------
-- Docking onto the Console
-------------------------------------------------------------------------------

-- The Console, only when this build has the whole API this file uses (IsDrawn, SetDockGap, the root
-- frame) and the chassis is drawn right now. Feature-detected: a missing Console or ActionBars file
-- leaves the panel floating.
local function DrawnConsole()
    local console = FS.Console
    if type(console) ~= "table" or type(console.IsDrawn) ~= "function"
        or type(console.SetDockGap) ~= "function" then
        return nil
    end
    local ok, drawn = pcall(console.IsDrawn)
    if ok and drawn == true and console.root then return console end
    return nil
end

local function CanSeat(pet)
    return type(pet) == "table" and pet.SeatDocked and pet.SeatFloat and pet.IsDocked
end

-- Docks the panel while the Console is drawn, floats it otherwise, and keeps the Console's top line
-- open exactly while a docked panel is shown. `force` re-seats a docked panel even when nothing
-- changed (a rescale moved the offset and the size). In combat (the container is protected, and the
-- Console refuses SetDockGap there) nothing is touched: pendingDock replays it at regen. Returns
-- true when it ran. A dock chrome that failed to build means float forever (no Refresh at all).
local function RefreshBody(force)
    if not (built and frames.dock) then return false end
    if InCombatLockdown() then
        pendingDock = true
        return false
    end
    local pet = FS.PetFrame
    if not CanSeat(pet) then return false end
    pendingDock = false

    local console = DrawnConsole()
    local wantGap = false
    if console then
        if force or not pet.IsDocked() then
            if not pet.SeatDocked(console.root, C.DOCK_X * FS.Layout.Scale()) then
                pendingDock = true
                return false
            end
        end
        if mode ~= "dock" then PetDock.SetMode("dock") end
        wantGap = petShown
    else
        -- Only an actual undock changes the chrome: a mode a caller picked with no Console to dock
        -- onto (SetMode before the build, say) is theirs and stays.
        if pet.IsDocked() then
            if not pet.SeatFloat() then
                pendingDock = true
                return false
            end
            PetDock.SetMode("float")
        end
    end

    -- The Console's top line: nil, nil closes it. Asked of whatever Console exists (the one that was
    -- drawn a moment ago may have just hidden), only when the wish changed or a forced re-dock.
    local api = FS.Console
    if type(api) == "table" and type(api.SetDockGap) == "function" and (wantGap ~= gapOpen or (force and wantGap)) then
        local ok
        if wantGap then
            ok = api.SetDockGap(C.DOCK_X - 1, C.DOCK_X + C.W + C.FLARE + 1)
        else
            ok = api.SetDockGap(nil, nil)
        end
        if ok then
            gapOpen = wantGap
        else
            pendingDock = true
        end
    end
    return true
end

-- Refresh runs from event handlers nothing else guards (the regen replay, SetPetShown, PetFrame's
-- ApplyRescale), and SeatDocked clears the container's points before it anchors, so a throw partway
-- would leave the panel unseated. A throw falls back to the float seat: the container re-seated by
-- SeatFloat, float chrome, the Console's top line closed. The error is run through xpcall so the
-- chained error handler (ErrorLog.lua: /fserr, /fsbug) still gets it with its stack, EVERY time; the
-- chat line is once per distinct message (FS.LogDegradeOnce does not dedupe), capped, so a second
-- different failure is not hidden behind the first. A float seat that did not land keeps pendingDock
-- set, so the next trigger (regen) tries again instead of leaving the panel unseated for good, and
-- the line says so.
local REFRESH_LOG_MAX = 3
local refreshLogged, refreshLoggedCount = {}, 0

local function ForwardError(err)
    local ok, handler = pcall(geterrorhandler)
    if ok and type(handler) == "function" then pcall(handler, err) end
    return err
end

local function LogRefreshFailure(err, floatErr)
    local key = tostring(err)
    if refreshLogged[key] or refreshLoggedCount >= REFRESH_LOG_MAX then return end
    refreshLogged[key] = true
    refreshLoggedCount = refreshLoggedCount + 1
    local tail
    if floatErr == nil then
        tail = "); the floating pet panel is used instead."
    else
        tail = "); the float seat failed too (" .. tostring(floatErr) .. "), retrying at the next trigger."
    end
    FS.LogDegradeOnce("petdock_dock_refresh",
        "|cffff4488ForeverSynthwave|r: docking the pet panel failed (" .. key .. tail)
end

function PetDock.Refresh(force)
    local ok, ran = xpcall(function() return RefreshBody(force) end, ForwardError)
    if ok then return ran end

    local pet = FS.PetFrame
    local landed, floatErr = false, "no float seat"
    if type(pet) == "table" and pet.SeatFloat then
        local called, result = xpcall(pet.SeatFloat, ForwardError)
        if called and result == true then
            landed, floatErr = true, nil
        elseif not called then
            floatErr = result
        else
            floatErr = "refused"
        end
    end
    pendingDock = not landed
    if landed then pcall(PetDock.SetMode, "float") end
    local api = FS.Console
    if type(api) == "table" and type(api.SetDockGap) == "function" then
        local closed, done = pcall(api.SetDockGap, nil, nil)
        gapOpen = not (closed and done)
    else
        gapOpen = false
    end
    LogRefreshFailure(ran, floatErr)
    return false
end

-- PetFrame.Apply calls this with the visibility gate's answer, out of combat only. A class with no
-- pet keeps the panel docked and hidden and the Console's top line whole.
function PetDock.SetPetShown(show)
    petShown = show and true or false
    PetDock.Refresh()
end

-------------------------------------------------------------------------------
-- Retint hook for the NORMAL edge (the red twins are never retinted)
-------------------------------------------------------------------------------

local function TintNormal(color, strokeAlpha, haloAlpha, floatColor, floatAlpha)
    for _, tex in ipairs(parts.dock.stroke) do Tint(tex, color, strokeAlpha) end
    for _, tex in ipairs(parts.dock.halo) do Tint(tex, color, haloAlpha) end
    if parts.float.outline then
        Tint(parts.float.outline, floatColor, floatAlpha)
    end
end

-- r, g, b of the normal edge; the optional alphas default to the mockup's stroke and halo (the float
-- outline's alpha stays 1 unless a stroke alpha is given). False for a non-number colour.
function PetDock.SetEdgeColor(r, g, b, strokeAlpha, haloAlpha)
    if type(r) ~= "number" or type(g) ~= "number" or type(b) ~= "number" then return false end
    if not built then return false end
    local color = { r, g, b }
    TintNormal(color, strokeAlpha or C.STROKE_ALPHA, haloAlpha or C.HALO_ALPHA, color, strokeAlpha or 1)
    return true
end

-- Back to the violet dock edge and the cyan float outline.
function PetDock.ResetEdgeColor()
    if not built then return false end
    local power = Theme.COLOR_POWER
    TintNormal(Theme.COLOR_BORDER, C.STROKE_ALPHA, C.HALO_ALPHA, power, power[4] or 1)
    return true
end

-------------------------------------------------------------------------------
-- Assembly
-------------------------------------------------------------------------------

-- PetFrame.Build calls this where it used to build the chrome, right after the container exists.
function PetDock.Build(frame)
    if built then return end
    container = frame
    local layout = FS.Layout and FS.Layout.petcontainer
    if type(layout) == "table" and type(layout.w) == "number" and type(layout.h) == "number" then
        C.W, C.H = layout.w, layout.h
    end
    BuildFloat()
    TryBuildDock()
    if not frames.dock then mode = "float" end   -- a "dock" remembered before the build cannot be honoured
    built = true
    Apply()
    if not frames.dock then return end           -- nothing to rescale

    -- The dock art is scaled by the layout scale. A rescale in combat waits for regen, like the
    -- container's own (the chrome frames are non-secure, but the container they hang from is not,
    -- and the two must agree).
    local function Rescale()
        pendingScale = false
        frames.dock:SetScale(FS.Layout.Scale())
    end
    if FS.Layout.OnRescale then
        FS.Layout.OnRescale(function()
            if InCombatLockdown() then
                pendingScale = true
                return
            end
            Rescale()
        end)
    end
    local watcher = CreateFrame("Frame")
    watcher:RegisterEvent("PLAYER_REGEN_ENABLED")
    watcher:SetScript("OnEvent", function()
        if pendingScale and not InCombatLockdown() then Rescale() end
        if pendingDock and not InCombatLockdown() then PetDock.Refresh(true) end
    end)

    -- Dock now if the Console is already drawn; every later Console seat, toggle and /fsbars switch
    -- comes through OnGeometry (replayed at once when a seat already happened, so load order is
    -- free). Only after the dock chrome built: without it the panel stays floating.
    if FS.ActionBars and type(FS.ActionBars.OnGeometry) == "function" then
        FS.ActionBars.OnGeometry(function() PetDock.Refresh() end)
    end
    PetDock.Refresh()
end

-- PetFrame calls this right after BuildLowHealth(): from then on SetMode keeps the low-HP layer
-- pointed at the active mode's edge.
function PetDock.AttachLowHealth()
    lowReady = true
    AttachLow()
end
