-- Forever Synthwave: Theme
-- Shared chrome primitives (font application, outer glow, rounded fill,
-- gradient border) and the palette/radius/texture constants they read,
-- extracted out of UnitFrames.lua so future component skins (CastBars,
-- Buffs, ActionBars) can reuse the same chrome without duplicating it.
-- Exposed on FS.Theme; loaded before any file that consumes it (see .toc).

local _, FS = ...
FS.Theme = FS.Theme or {}
local Theme = FS.Theme

-------------------------------------------------------------------------------
-- Palette
-------------------------------------------------------------------------------

-- Read directly inside ApplyFontGeneric as the default text color.
Theme.COLOR_TEXT_WHITE = { 1, 1, 1, 1 }

-- Canonical palette (locked design doc), shared so every component module
-- (UnitFrames, CastBars, Buffs, ActionBars, ...) reuses one definition
-- instead of re-declaring the hex values locally.
Theme.COLOR_BG         = { 0.102, 0.063, 0.145, 0.80 } -- #1a1025 @ 80%
-- Gunsight HUD panel fill (mockup pChromeCm: rgba(13,6,32) at .55 x .85). Lighter and far
-- more transparent than COLOR_BG so the scene shows through; the pet panel fill uses it (the party panel draws none).
Theme.COLOR_HUD_SCRIM  = { 0.051, 0.024, 0.125, 0.4675 } -- #0d0620 @ 46.75%
Theme.COLOR_BORDER     = { 0.659, 0.333, 0.969, 1 }    -- #a855f7

-- Dispel-type colours, one palette for every aura ring and halo (Buffs, PartyFrames): the
-- DebuffTypeColor global does not exist on 16001. Magic #3FC7EB, Curse #A335EE, Disease #A0522D,
-- Poison #40BF40.
Theme.DISPEL_COLORS = {
    Magic   = { 0.247, 0.780, 0.922, 1 },
    Curse   = { 0.639, 0.208, 0.933, 1 },
    Disease = { 0.627, 0.322, 0.176, 1 },
    Poison  = { 0.251, 0.749, 0.251, 1 },
}
Theme.COLOR_BAR_TRACK  = { 0.039, 0.016, 0.086, 1 }    -- #0a0416 (bar bg)
Theme.COLOR_BAR_BORDER = { 0.227, 0.129, 0.408, 1 }    -- #3a2168 (--line, 1px bar border)
Theme.COLOR_HEALTH     = { 1, 0.180, 0.592, 1 }        -- #ff2e97
Theme.COLOR_POWER      = { 0.133, 0.878, 1, 1 }        -- #22e0ff
-- Leading-edge caret colors (locked mockup values), passed as the `color`
-- argument to FrameHelpers.CreateCaret, which tints its 3px pulsing line by
-- it. UnitFrames.lua and the nameplate bars in ForeverSynthwave.lua consume
-- these tokens.
Theme.COLOR_CARET_HEALTH = { 0.224, 1, 0.078, 1 }      -- #39ff14
Theme.COLOR_CARET_POWER  = { 1, 0.302, 0.847, 1 }      -- #ff4dd8

-- Incoming-heal overlay color (UnitFrames.lua). Aliases COLOR_CARET_HEALTH
-- (same #39ff14 the mockup's --green uses), no new hex.
Theme.COLOR_HEAL = Theme.COLOR_CARET_HEALTH

-- Nameplate cast bar, ForeverSynthwave.lua's only consumer so far.
-- Interruptible aliases the existing power cyan (same #22e0ff, no new hex);
-- non-interruptible is steel grey, the same triple ForeverSynthwave.lua's
-- local COLOR_BAR_TAPPED already uses for "not yours to touch" fills.
Theme.COLOR_CAST_INTERRUPTIBLE = Theme.COLOR_POWER
Theme.COLOR_CAST_NO_INTERRUPT  = { 0.42, 0.42, 0.45, 1 }

-- Menus.lua's item text: aliases the existing power cyan (same #22e0ff, no
-- new hex), replacing Blizzard's NORMAL_FONT_COLOR gold in menu item text.
Theme.COLOR_MENU_TEXT = Theme.COLOR_POWER

-- Gunsight HUD tokens (mockups/gunsight-hud-v2-2026-10-02, :root custom properties of the same
-- names; gunsight-harness.py reads the mockup and fails if these drift). CombatHud.lua's local
-- gold/warm fallbacks carry the same triples and defer to these when present.
Theme.COLOR_GOLD  = { 1, 0.8235, 0.2471, 1 }           -- #ffd23f --gold
Theme.COLOR_STEEL = { 0.5529, 0.5765, 0.6510, 1 }      -- #8d93a6 --steel
Theme.COLOR_AMBER = { 1, 0.7137, 0.2824, 1 }           -- #ffb648 --amber
Theme.COLOR_WARM  = { 1, 0.2392, 0.1216, 1 }           -- #ff3d1f --warm
Theme.COLOR_RED   = { 1, 0.2314, 0.3059, 1 }           -- #ff3b4e --red
Theme.COLOR_MUTED = { 0.6157, 0.5765, 0.7686, 1 }      -- #9d93c4 --muted (the party pet column's PET label)
-- The party row edge of the unit the player has targeted (PartyFrames ApplyBoxEdge). An electric
-- indigo-violet, deliberately bluer than COLOR_BORDER (#a855f7, hue 271) and the Curse dispel
-- colour (#A335EE / #9933FF, hue 276-280), and far from the pinks (COLOR_HEALTH, caret power).
Theme.COLOR_TARGET = { 0.4157, 0.2980, 1, 1 }           -- #6a4cff

-------------------------------------------------------------------------------
-- Radii
-------------------------------------------------------------------------------

Theme.PANEL_RADIUS = 6 -- locked mockup corner radius (--radius); default for AddGradientBorder

-- Default uniform inset between a pill bar's shell and its neon fill StatusBar.
-- Contract: equals the chrome border thickness (1), in the same unscaled units
-- the border is drawn in. Callers must not scale it independently of the border.
Theme.BAR_FILL_INSET = 1

-- Canonical component radii (locked design doc), passed as call-site
-- arguments to the chrome helpers above.
Theme.LEVEL_RADIUS = 3 -- mock: level chip radius = radius * 0.55 (~3.3)

-- FrameLevel margin above a StatusBar's level for fill-corner mask hosts and
-- text hosts. Must clear both the heal/absorb overlay bars (bar+1) and the
-- caret host (bar+2, see FrameHelpers.lua's CreateCaret comment).
Theme.BAR_CORNER_MASK_LEVEL = 5

-------------------------------------------------------------------------------
-- Cut corners (chamfer) vs rounded
-------------------------------------------------------------------------------

-- Temporary A/B flag for the cut-corner migration (notes/cut-corners-inventory-
-- 2026-10-02.md). "cut" is the default and what ships: EVERY rectangle or square is
-- cut at TOP-LEFT and BOTTOM-RIGHT only, TOP-RIGHT and BOTTOM-LEFT stay square.
-- "round" runs the old disc/arc code path untouched. The composed-piece
-- primitives below (AddRoundedFill, AddGradientBorder, AddOuterGlow, AddCornerMask,
-- AddFillCorners, AddLeadingEdgeCorners) read it at CALL time. Delete the flag and the
-- round branches when the rounded set is retired.
Theme.CHROME_CORNERS = "cut"

-- Baked chamfer sizes in texels. Each size is its own media file because a piece is
-- drawn at native texels and never rescaled (a 64 texel triangle scaled to 3-6 px aliases).
Theme.CUT_SIZES = { 2, 3, 4, 6 }
local CUT_MEDIA = "Interface\\AddOns\\ForeverSynthwave\\media\\"
-- Every cut piece is a 16x16 canvas with the piece at the top-left, so a piece of
-- chamfer c is sampled with SetTexCoord(0, c/16, 0, c/16) at the top-left corner and
-- SetTexCoord(c/16, 0, c/16, 0) at the bottom-right (flipped both ways).
local CUT_PIECE_CANVAS = 16

Theme.FILL_CUT_TEXTURES = {}
Theme.ANTI_CUT_TEXTURES = {}
Theme.BORDER_CUT_TEXTURES = {}  -- [c][thickness]; thickness 2 is baked for c = 6 only
for _, c in ipairs(Theme.CUT_SIZES) do
    Theme.FILL_CUT_TEXTURES[c] = CUT_MEDIA .. "fill_cut_c" .. c .. ".tga"
    Theme.ANTI_CUT_TEXTURES[c] = CUT_MEDIA .. "anti_cut_c" .. c .. ".tga"
    Theme.BORDER_CUT_TEXTURES[c] = { [1] = CUT_MEDIA .. "border_cut_c" .. c .. "_t1.tga" }
end
Theme.BORDER_CUT_TEXTURES[6][2] = CUT_MEDIA .. "border_cut_c6_t2.tga"
-- One halo piece baked at chamfer:reach = 6:8 and stretched whole, the way
-- GLOW_CORNER_ROUND_TEXTURE is reused at other ratios.
Theme.GLOW_CORNER_CUT_TEXTURE = CUT_MEDIA .. "glow_corner_cut.tga"

-- Largest baked chamfer <= `requested`. 0 (square) for a request of 0 or less; a
-- positive request under 2 still gets the smallest piece, so a caller that asked for a
-- cut never silently gets none.
function Theme.SnapCut(requested)
    if not requested or requested <= 0 then return 0 end
    local best = Theme.CUT_SIZES[1]
    for _, c in ipairs(Theme.CUT_SIZES) do
        if c <= requested then best = c end
    end
    return best
end

local function SnapForHeight(h, divisor)
    if not h then return 0 end
    local want = math.min(math.max(math.floor(h / divisor), 2), 6, math.floor(h / 2))
    if want < 2 then return 0 end -- nothing in the baked set fits this short a plate
    return Theme.SnapCut(want)
end

-- Chamfer for a panel, frame, bar, plate or chip of height `h`: the largest baked size
-- <= clamp(floor(h / 3), 2, 6), also <= floor(h / 2) so the two cut corners never
-- meet. 0 (square) when h < 4. 16 -> 4, 18 or 24 -> 6, 9 -> 3, 5 -> 2.
function Theme.CutSize(h)
    return SnapForHeight(h, 3)
end

-- Same rule at h / 5 for square icon buttons, so the icon inset ceil(c / 2) keeps the
-- icon corner on the cut line. 36 and up -> 6, 24 -> 4, 18 -> 3.
function Theme.CutSizeIcon(h)
    return SnapForHeight(h, 5)
end

-- Border ring and glow textures of the two-corner button set at chamfer `c` (snapped to
-- the baked sizes, never 0), plus the chamfer actually used. c = 6 is the original
-- byte-stable pair (the SLICE_CUT2_OUTLINE / SLICE_CUT2_GLOW constants, which the action
-- bars pin);
-- 2, 3 and 4 add a _c<N> suffix. The ring's slice margin is c, the glow's is 4 + c.
function Theme.Cut2ButtonSet(c)
    c = Theme.SnapCut(c)
    if c == 0 then c = Theme.CUT_SIZES[1] end
    if c == 6 then return Theme.SLICE_CUT2_OUTLINE_TEXTURE, Theme.SLICE_CUT2_GLOW_TEXTURE, c end
    local base = "Interface\\AddOns\\ForeverSynthwave\\media\\slice_cut2_"
    return base .. "outline_c" .. c .. ".tga", base .. "glow_c" .. c .. ".tga", c
end

-- Texcoords (L, R, T, B) of a cut piece of chamfer c at TOPLEFT or BOTTOMRIGHT.
local function CutCoords(corner, c)
    local k = c / CUT_PIECE_CANVAS
    if corner == "TOPLEFT" then return 0, k, 0, k end
    return k, 0, k, 0
end

-------------------------------------------------------------------------------
-- Fonts / textures
-------------------------------------------------------------------------------

-- Bold Mononoki; see ApplyMono for the no-outline/no-shadow rendering rationale.
Theme.FONT_MONO = "Interface\\AddOns\\ForeverSynthwave\\fonts\\MononokiNerdFontMono-Bold.ttf"
-- Display face for name-row/level-chip headings (UnitFrames, PartyFrames,
-- DataBar); canonical here so every consumer shares one definition.
--
-- This is Orbitron, but it must NOT be Orbitron-VF.ttf: WoW's renderer refuses
-- VARIABLE fonts, so every SetFont on the VF failed and ApplyFontGeneric's
-- readback quietly fell back to FRIZQT. The headings were never Orbitron at
-- all. FSDisplay-Bold.ttf is that same face pinned at wght=700 by
-- fonts/make_display_font.py, renamed because "Orbitron" is an OFL Reserved
-- Font Name and a pinned instance is a Modified Version.
Theme.FONT_ORBITRON = "Interface\\AddOns\\ForeverSynthwave\\fonts\\FSDisplay-Bold.ttf"
Theme.FLAT_TEXTURE = "Interface\\Buttons\\WHITE8x8" -- flat statusbar fill, shared by every bar-style component
Theme.GLOW_EDGE_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\glow_edge.tga"
Theme.GLOW_CORNER_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\glow_corner.tga"
Theme.GLOW_CORNER_ROUND_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\glow_corner_round.tga"
-- Filled quarter-disc for the panel fill's rounded corners. Used INSTEAD of a
-- MaskTexture: CreateMaskTexture/AddMaskTexture exist on this interface-16001
-- client but do not actually clip (confirmed in-game, even with Blizzard's own
-- TempPortraitAlphaMask). Fixed-size corner pieces (not a stretched
-- rounded-rect texture) keep the fill aligned to the border/glow arcs at both
-- panel heights.
Theme.FILL_CORNER_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\fill_corner.tga"
-- Inverse of FILL_CORNER_TEXTURE: opaque outside the rounding arc, transparent
-- inside it, same top-left orientation. Used by AddCornerMask to overpaint a
-- StatusBar fill's square corners with track color, since a nine-slice fill
-- would round the FILL's own straight runs too (it's a bar, not a panel) and
-- MaskTexture does not clip on this client (see above).
Theme.ANTI_CORNER_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\anti_corner.tga"
Theme.BORDER_RAIL_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\border_rail.tga"
Theme.BORDER_CORNER_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\border_corner.tga"
-- Tiled 45-degree diagonal-stripe hatch (light gray/white on transparent),
-- UnitFrames.lua's absorb/shield overlay fill. See media/generate_hatch.py.
Theme.HATCH_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\hatch.tga"

-- NINE-SLICE chrome. One texture per element, corners drawn from it at native
-- texel resolution by the engine, straight runs stretched.
--
-- This supersedes the rails-plus-corner-quads construction above for anything
-- SMALL. That construction has no way to guarantee the rail end and the arc
-- quad meet, and at action-button size (a 4px radius on a ~22px button) they
-- did not: a pixel dump of a close-up showed two near-black pixels of the
-- button's own ground showing through the elbow, with the surviving three
-- border pixels forming a hard unantialiased staircase. Nine-slicing cannot
-- produce that seam, because there is only one quad-set and the engine emits
-- it.
--
-- SLICE_MARGIN must equal RADIUS in media/generate_slice_chrome.py, so the
-- corner slice holds exactly the arc; change the two together.
--
-- Under Theme.CHROME_CORNERS == "cut" (the default) these panel constants point at the
-- two-corner cut set instead (top-left and bottom-right chamfer 6, margin 6, glow margin
-- 10), so every SkinPanel / AddPanelChrome caller, the nameplate plate chrome, the XP
-- tooltip and the glow under BagBar / CastBars / PetCastBar gets the cut shape with no
-- caller edit. The constants resolve once, when this file LOADS (callers read them as
-- plain fields), so flipping the flag means editing the Theme.CHROME_CORNERS line near
-- the top of this file, not setting it at runtime; the composed primitives (AddRoundedFill
-- and friends) still read it per call.
-- The border is slice_cut2_border_c6 (1.0 stroke), NOT slice_cut2_outline: the outline's
-- 1.5 stroke leaks a faint line into the edge slice on a panel.
local CUT_PANEL = Theme.CHROME_CORNERS == "cut"
-- (Each constant is a self-contained single line on purpose: the headless harnesses
-- evaluate them one by one out of this file.)
Theme.SLICE_FILL_TEXTURE = Theme.CHROME_CORNERS == "cut" and "Interface\\AddOns\\ForeverSynthwave\\media\\slice_cut2_fill.tga" or "Interface\\AddOns\\ForeverSynthwave\\media\\slice_fill.tga"
Theme.SLICE_BUTTON_TEXTURE = Theme.CHROME_CORNERS == "cut" and "Interface\\AddOns\\ForeverSynthwave\\media\\slice_cut2_button.tga" or "Interface\\AddOns\\ForeverSynthwave\\media\\slice_button.tga"
Theme.SLICE_BORDER_TEXTURE = Theme.CHROME_CORNERS == "cut" and "Interface\\AddOns\\ForeverSynthwave\\media\\slice_cut2_border_c6.tga" or "Interface\\AddOns\\ForeverSynthwave\\media\\slice_border.tga"
Theme.SLICE_MARGIN = Theme.CHROME_CORNERS == "cut" and 6 or 5

-- Outer glow, same idea one layer out: the shape is the rounded rect inset by
-- SLICE_GLOW_PAD from the texture edge, alpha falling off outward over those
-- texels and HOLLOW inside. Drawn on a region overhanging the frame by
-- SLICE_GLOW_PAD on every side, so the shape boundary lands exactly on the
-- frame's own rounded edge.
--
-- Its margin is PAD + RADIUS, because the corner slice has to contain the arc
-- AND its halo. All three numbers live in media/generate_slice_chrome.py;
-- change them together. (Under "cut": slice_cut2_glow, margin PAD + 6 = 10.)
Theme.SLICE_GLOW_TEXTURE = Theme.CHROME_CORNERS == "cut" and "Interface\\AddOns\\ForeverSynthwave\\media\\slice_cut2_glow.tga" or "Interface\\AddOns\\ForeverSynthwave\\media\\slice_glow.tga"
Theme.SLICE_GLOW_PAD = 4
Theme.SLICE_GLOW_MARGIN = Theme.CHROME_CORNERS == "cut" and 10 or 9

-- Cut-corner (chamfered) outline: same nine-slice idiom as the rounded slice textures
-- above, but the corner shape baked into media/generate_cut_corner_outline.py is a
-- straight 45-degree cut instead of an arc. Locked design's "outline / cut corners"
-- backdrop -- thin stroke, hollow interior, no fill, no corner brackets, no drag-handle
-- dashes. First consumer: the pet container (Phase 2, not yet built).
--
-- SLICE_CUT_MARGIN must equal CHAMFER in generate_cut_corner_outline.py, the same
-- contract as SLICE_MARGIN/RADIUS above; change the two together. Its value (6) differs
-- from SLICE_MARGIN (5) on purpose -- the pet mockup's corner-radius family reads ~6px at
-- the design's 2560x1440 reference scale -- so it needs its own margin constant and the
-- two-call ApplyNineSlice override pattern SLICE_GLOW_MARGIN already uses below.
Theme.SLICE_CUT_OUTLINE_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\slice_cut_outline.tga"
-- Solid companion to the outline: same chamfered outer shape, full coverage inside, so a
-- tinted fill sits flush under the stroke with no gap.
Theme.SLICE_CUT_FILL_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\slice_cut_fill.tga"
Theme.SLICE_CUT_MARGIN = 6   -- tune alongside CHAMFER in the generator; Parker will check vs the artifact

-- Two-corner cut ("cut2"): only TOP-LEFT and BOTTOM-RIGHT are chamfered, TOP-RIGHT and
-- BOTTOM-LEFT stay square. The locked pet-slot plate shape, now the look of the action,
-- pet and stance bar buttons (the four-corner set above stays BagBar's). Generated by
-- the same media/generate_cut_corner_outline.py from the same CHAMFER, so it takes the
-- SAME margin (SLICE_CUT_MARGIN); there is deliberately no separate cut2 chamfer
-- constant, so retuning CHAMFER moves both sets together.
--   SLICE_CUT2_BUTTON_TEXTURE  the action-button plate: #241640 -> #160c2b gradient baked
--                              into RGB (a gradient cannot be applied to a nine-slice at
--                              runtime without banding), tint white to keep it
--   SLICE_CUT2_FILL_TEXTURE    plain white shape, for tinted/ADD washes (hover highlight)
--   SLICE_CUT2_OUTLINE_TEXTURE thin 1 texel stroke, the action button's border weight
--   SLICE_CUT2_GLOW_TEXTURE    outer glow, hollow inside, same idiom as SLICE_GLOW_*
--   MASK_CUT2_SQUARE_TEXTURE   64x64 alpha mask for icons and the cooldown swipe; its
--                              chamfer is a FRACTION of the texture (MASK_CHAMFER_FRACTION
--                              in the generator), tuned for a ~35px icon. UNUSED while
--                              masks do not clip on this client (see AddCornerMask).
-- SLICE_CUT2_GLOW_MARGIN = pad + chamfer, the same rule as SLICE_GLOW_MARGIN; all of
-- these numbers live in the generator and move together.
Theme.SLICE_CUT2_BUTTON_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\slice_cut2_button.tga"
Theme.SLICE_CUT2_FILL_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\slice_cut2_fill.tga"
Theme.SLICE_CUT2_OUTLINE_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\slice_cut2_outline.tga"
Theme.SLICE_CUT2_GLOW_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\slice_cut2_glow.tga"
Theme.SLICE_CUT2_GLOW_PAD = 4
Theme.SLICE_CUT2_GLOW_MARGIN = Theme.SLICE_CUT2_GLOW_PAD + Theme.SLICE_CUT_MARGIN
Theme.MASK_CUT2_SQUARE_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\mask_cut2_square.tga"

-- Cast bar chevrons (media/generate_cast_chevron.py, locked look in
-- mockups/castbar-v2-chevrons-locked-2026-10-01.html, card H). All five are white RGB
-- with the shape in alpha, drawn POINTING RIGHT; mirror them with SetTexCoord (swap
-- the U ends) for channels and tint with SetVertexColor.
--   CAST_CHEVRON_FILL_TEXTURE     64x64, one solid chevron segment
--   CAST_CHEVRON_OUTLINE_TEXTURE  64x64, hollow stroke of the same chevron (caret core)
--   CAST_CHEVRON_GLOW_TEXTURE     128x128, soft halo of the outline for ADD blend, tinted
--                                 cyan. The chevron box sits centred, so there are
--                                 CAST_CHEVRON_GLOW_PAD (32) texels of halo on every side:
--                                 draw it (1 + 2 * CAST_CHEVRON_GLOW_PAD_FRACTION) = 2x the
--                                 chevron's on-screen size, centred on it.
--   CAST_CHEVRON_BURST_TEXTURE    128x128, solid chevron plus soft glow edge (lock-in
--                                 burst glyph), same centred box and pad as the glow
--   CAST_CHEVRON_STRIP_TEXTURE    32x16, 2 chevrons, tiles seamlessly (secret-timing
--                                 fallback: StatusBar fill texture with SetHorizTile).
--                                 SetHorizTile repeats it at CAST_CHEVRON_STRIP_TILE_W
--                                 pixels; the strip uses a fatter arm than the segments
--                                 (see the generator), so it is a fallback look.
-- Geometry: a chevron is h tall and h wide (ASPECT 1), 45 degree arms. The gap between
-- neighbouring chevrons is 3 of an 18 high player run (1/6); the pet run uses 2 of 10.
Theme.CAST_CHEVRON_FILL_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\cast_chevron_fill.tga"
Theme.CAST_CHEVRON_OUTLINE_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\cast_chevron_outline.tga"
Theme.CAST_CHEVRON_GLOW_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\cast_chevron_glow.tga"
Theme.CAST_CHEVRON_BURST_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\cast_chevron_burst.tga"
Theme.CAST_CHEVRON_STRIP_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\cast_chevron_strip.tga"
Theme.CAST_CHEVRON_ASPECT = 1                  -- chevron width / height
Theme.CAST_CHEVRON_GAP_FRACTION = 1 / 6        -- gap between chevrons / chevron width (player run)
Theme.CAST_CHEVRON_GLOW_PAD = 32               -- texels of halo around the 64 texel chevron box
Theme.CAST_CHEVRON_GLOW_PAD_FRACTION = 0.5     -- the same pad as a fraction of the chevron box
Theme.CAST_CHEVRON_STRIP_TILE_W = 32           -- strip texture width in pixels (SetHorizTile period)
Theme.CAST_CHEVRON_STRIP_TILE_H = 16

-- Shared with Chat.lua's terminal scrim: a 4x4 tiling texture, one dark row
-- over transparent. Tiled, never stretched -- stretching it resamples the row
-- into grey mush at any size the panel happens to be.
Theme.SCANLINE_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\scanline.tga"
Theme.SCANLINE_ALPHA = 0.25   -- lower than the chat terminal's .4: a panel is
                              -- something you read, not something you glance at
Theme.PANEL_HEADER_H = 18     -- terminal title band, sized to the mono 10pt label

-- Both methods were confirmed present on this client (interface 16001) by live
-- probe, along with Enum.UITextureSliceMode.Stretched == 0 -- feature-detected
-- anyway, so a client without them degrades to a plain stretched rounded rect
-- (slightly soft corners) rather than erroring.
--
-- Warned once per session, not once per texture: a client missing this API
-- fails identically on every call, so repeating the message would just be
-- noise. Mirrors the warnedFontPaths pattern later in this file.
local warnedNoSliceMargins = false

function Theme.ApplyNineSlice(texture, margin)
    if not (texture and texture.SetTextureSliceMargins) then
        if not warnedNoSliceMargins then
            warnedNoSliceMargins = true
            local msg = "|cffff4488ForeverSynthwave|r: SetTextureSliceMargins unavailable, degrading " ..
                "nine-slice chrome to a stretched rounded rect"
            FS.LogDegradeOnce("nilslicemargins", msg)
        end
        return false
    end
    margin = margin or Theme.SLICE_MARGIN
    texture:SetTextureSliceMargins(margin, margin, margin, margin)
    if texture.SetTextureSliceMode and Enum and Enum.UITextureSliceMode then
        texture:SetTextureSliceMode(Enum.UITextureSliceMode.Stretched)
    end
    return true
end

-- One nine-sliced texture covering `frame`, at the given draw layer/sublevel.
-- `path` picks which of the three above; `color` tints it (the button texture
-- carries its own baked gradient, so tint it white to keep that).
function Theme.AddSliceTexture(frame, path, color, layer, sublevel, inset)
    local texture = frame:CreateTexture(nil, layer or "BACKGROUND", nil, sublevel)
    texture:SetTexture(path)
    Theme.ApplyNineSlice(texture)
    inset = inset or 0
    texture:SetPoint("TOPLEFT", frame, "TOPLEFT", inset, -inset)
    texture:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -inset, inset)
    if color then
        texture:SetVertexColor(color[1], color[2], color[3], color[4] or 1)
    end
    return texture
end

-- Applies the cut-corner outline primitive (see SLICE_CUT_OUTLINE_TEXTURE above) to
-- `frame`: a thin cyan stroke with chamfered corners, no fill. Default color is
-- Theme.COLOR_POWER per the locked design ("outline = thin cyan border"). Stroke
-- thickness is baked into the texture at generation time (THICKNESS in
-- generate_cut_corner_outline.py), not a runtime parameter -- the same tradeoff
-- AddSliceTexture's own border ring (slice_border.tga) already makes, since a nine-slice
-- alpha shape can't be rescaled at runtime without redrawing it. Returns the texture
-- handle so a caller can retint it later via SetVertexColor.
function Theme.AddCutCornerOutline(frame, color, layer, sublevel, inset)
    color = color or Theme.COLOR_POWER
    local texture = Theme.AddSliceTexture(frame, Theme.SLICE_CUT_OUTLINE_TEXTURE, color, layer or "BORDER", sublevel, inset)
    Theme.ApplyNineSlice(texture, Theme.SLICE_CUT_MARGIN)
    return texture
end

-- One nine-sliced texture of the two-corner cut set (SLICE_CUT2_*) covering `frame`:
-- AddSliceTexture with the chamfer margin, since the default rounded margin (5) would
-- slice the 6 texel chamfer wrongly. `path` is one of the SLICE_CUT2_*_TEXTURE
-- constants, `color` tints it.
function Theme.AddCut2Texture(frame, path, color, layer, sublevel, inset)
    local texture = Theme.AddSliceTexture(frame, path, color, layer, sublevel, inset)
    Theme.ApplyNineSlice(texture, Theme.SLICE_CUT_MARGIN)
    return texture
end

-------------------------------------------------------------------------------
-- Secret-value guard
-------------------------------------------------------------------------------

-- 12.0 "secret values": tainted addon code may store/pass secret values to
-- whitelisted engine setters, but may not compare, do arithmetic on, index,
-- or boolean-test them. Shared here so UnitFrames/PartyFrames/CastBars need
-- only one feature-detected check instead of duplicating it per file.
local HAS_ISSECRETVALUE = type(issecretvalue) == "function"
function FS.IsSecret(v)
    return HAS_ISSECRETVALUE and issecretvalue(v)
end

-- True while the player has a target. The one rule every Gunsight visibility layer shares (tape, boxes,
-- dots, horizon): a secret UnitExists answer, or a client without UnitExists, reads as "has one" so the
-- piece stays shown; the answer goes to FS.IsSecret before anything else touches it, never truth-tested.
function FS.HasTarget()
    if type(UnitExists) ~= "function" then return true end
    local exists = UnitExists("target")
    if FS.IsSecret(exists) then return true end
    return exists and true or false
end

-- true or false from a PLAIN answer of a unit predicate, nil when it cannot be read: a missing API, a throw,
-- a secret (checked before anything else touches it) or an odd type. The legacy forms read 1 as true, nil as false.
local function PlainFlag(fn, ...)
    if type(fn) ~= "function" then return nil end
    local ok, v = pcall(fn, ...)
    if not ok then return nil end
    if FS.IsSecret(v) then return nil end
    if v == nil then return false end
    if type(v) == "boolean" then return v end
    if type(v) == "number" then return v ~= 0 end
    return nil
end

-- Can a DoT of ours be on the target? The rule the DoT scale (GunsightDots) and the horizon's dot segment
-- (GunsightFrame) share. No target, a dead one (UnitIsDeadOrGhost, so an enemy ghost counts) and an
-- unattackable one (a friendly NPC) say no; anything unreadable says yes, so a piece is never hidden on a guess.
-- HudLogic keeps its own HasAttackableTarget on purpose, see the comment there.
function FS.TargetTakesDots()
    if not FS.HasTarget() then return false end
    if PlainFlag(UnitIsDeadOrGhost, "target") == true then return false end
    if PlainFlag(UnitCanAttack, "player", "target") == false then return false end
    return true
end

-- Aura reads are refused outright -- not handed back secret, REFUSED with an
-- error -- while addon-tainted code runs under combat lockdown. Gated on
-- InCombatLockdown specifically, not on being in combat: measured across a
-- fight, auras read fine at the combat-start instant (already
-- UnitAffectingCombat, not yet locked down) and again the moment lockdown
-- cleared, and were refused throughout the middle.
--
-- Callers MUST check this before scanning. A refused pcall still builds its
-- refusal string, and that is not free: Parker's FS MEM readout climbed to
-- 9.2M in a single session, which is ~30 of those long messages a second from
-- five party rows scanning on a ticker. Skipping the scan and holding the last
-- known display costs nothing and shows the same thing.
--
-- Fails closed: readable only when lockdown is off AND the client does not say auras
-- are secret. C_Secrets.ShouldAurasBeSecret() can still answer true for a moment after
-- lockdown ends, and a refused read is the expensive thing to avoid, so that answer
-- holds the gate shut. A throw, a secret or any non-boolean answer also reads as not
-- readable. Only a client without the API is decided by the lockdown test alone. Same
-- rule as HudLogic.lua's AurasReadable. (The Buffs row no longer depends on this gate to
-- SHOW auras: the engine's AuraContainer draws them in combat, and the gate only guards
-- the out-of-combat snapshot reads and the legacy rows.)
function FS.AurasReadable()
    if InCombatLockdown() then return false end
    local api = C_Secrets and C_Secrets.ShouldAurasBeSecret
    if type(api) ~= "function" then return true end
    local ok, secret = pcall(api)
    if not ok or FS.IsSecret(secret) or type(secret) ~= "boolean" then return false end
    return secret == false
end

-- FS.AurasReadable can still answer "secret" for a moment after PLAYER_REGEN_ENABLED, so a
-- module that refreshes once at regen can find the gate shut and stay stale until some later
-- aura change. FS.OnAurasReadable(fn) is the shared fix: when reads were NOT possible at regen,
-- one chain looks again a few times (AURAS_RETRY_DELAY apart, at most AURAS_RETRY_LIMIT) and
-- runs every registered fn once the first time they are. Readable at regen: nothing runs,
-- the modules' own regen refresh has already read. A newer regen retires an older chain
-- (generation check); combat starting again just burns the remaining attempts, since the gate
-- stays shut in lockdown. A throwing fn goes to the error handler and does not stop the rest.
do
    local AURAS_RETRY_DELAY = 0.5
    local AURAS_RETRY_LIMIT = 3
    local callbacks = {}
    local generation = 0
    local regenFrame

    local function RunCallbacks()
        for i = 1, #callbacks do
            local ok, err = pcall(callbacks[i])
            if not ok and type(geterrorhandler) == "function" then
                geterrorhandler()(err)
            end
        end
    end

    local function Retry(attempt, forGeneration)
        if type(C_Timer) ~= "table" or type(C_Timer.After) ~= "function" then return end
        C_Timer.After(AURAS_RETRY_DELAY, function()
            if forGeneration ~= generation then return end
            local ok, readable = pcall(FS.AurasReadable)
            if ok and readable then
                RunCallbacks()
            elseif attempt < AURAS_RETRY_LIMIT then
                Retry(attempt + 1, forGeneration)
            end
        end)
    end

    function FS.OnAurasReadable(fn)
        callbacks[#callbacks + 1] = fn
        if regenFrame then return end
        regenFrame = CreateFrame("Frame")
        regenFrame:RegisterEvent("PLAYER_REGEN_ENABLED")
        regenFrame:SetScript("OnEvent", function()
            generation = generation + 1
            local ok, readable = pcall(FS.AurasReadable)
            if not (ok and readable) then Retry(1, generation) end
        end)
    end
end
-- END aura readiness
-- ^ buffs-harness.py loads the block from `function FS.AurasReadable()` to this marker as TEXT,
-- found by those two anchors (the nameplate and partyframes harnesses mock it instead). Keep both
-- anchors in place and the block self-contained (it may use only FS and engine globals).

-------------------------------------------------------------------------------
-- Parchment text
-------------------------------------------------------------------------------

-- Blizzard's panel text is DARK ON PURPOSE: gossip, quest text, books and mail
-- are drawn on a light parchment background, so their font objects are black or
-- near-black. StripBlizzardChrome hides that parchment and SkinPanel puts a
-- near-black panel behind it instead, which leaves the text unreadable --
-- Parker, 2026-09-22, on an innkeeper: "dialogue for the inkeeper is blanked
-- out but the icons" render fine. Icons are textures and survive; the text is
-- still there, just black on black.
--
-- Retinting the shared FONT OBJECT rather than walking FontStrings is the
-- robust half of this. A FontString inherits its object's colour, so one write
-- covers every panel using it AND survives Blizzard repopulating the text,
-- which a one-shot sweep over existing FontStrings does not.
Theme.COLOR_TEXT_PARCHMENT = { 0.749, 0.914, 0.839 } -- #bfe9d6, the terminal body colour

-- Candidates read off the 16001 globals dump (every `widget:Font` whose name
-- mentions black / quest / itemtext / mail), NOT invented. A name that does not
-- exist is skipped, so this list is safe to carry across clients.
local PARCHMENT_FONTS = {
    "GameFontBlack", "GameFontBlackMedium", "GameFontBlackSmall",
    "GameFontBlackSmall2", "GameFontBlackTiny", "GameFontBlackTiny2",
    "GameFontNormalHugeBlack",
    "ItemTextFontNormal", "MailFont_Large", "MailTextFontNormal",
    "InvoiceTextFontNormal", "InvoiceFont_Med", "InvoiceFont_Small",
    "InvoiceTextFontSmall", "GameFontDarkGraySmall",
    "QuestFont", "QuestFontLeft", "QuestFontNormalSmall",
    "QuestFontNormalLarge", "QuestFontNormalHuge", "QuestFontHighlightHuge",
    "QuestFont_30", "QuestFont_39", "QuestFont_Large", "QuestFont_Huge",
    "QuestFont_Enormous", "QuestFont_Super_Huge",
    "QuestFont_Shadow_Small", "QuestFont_Shadow_Huge",
    "QuestFont_Shadow_Enormous", "QuestFont_Shadow_Super_Huge",
    "QuestMapRewardsFont", "QuestTitleFont", "QuestTitleFontBlackShadow",
    "QuestDifficulty_Header", "QuestDifficulty_Standard",
}

-- Perceived brightness. Only genuinely DARK objects are retinted, so anything
-- Blizzard already ships light (a highlight, a difficulty colour) is left as it
-- is rather than flattened into one colour. This also makes the whole pass
-- idempotent for free: a retinted object is no longer dark.
local function Luma(r, g, b)
    return 0.2126 * (r or 0) + 0.7152 * (g or 0) + 0.0722 * (b or 0)
end

local DARK_TEXT_LUMA = 0.35

-- Luma alone misreads a saturated state color as dark: RED_FONT_COLOR
-- (1, .125, .125) has luma ~0.31, below DARK_TEXT_LUMA, so a caller gating on
-- luma alone would permanently overwrite "can't learn"/"can't afford" red
-- with mint on every repaint (a hooked retint re-asserts on every SetTextColor
-- call, so this isn't a one-time miscolor -- it never lets the red back in).
-- Genuine dark parchment ink (black, Blizzard's 0.2 gray, QuestFont-style dark
-- brown) has every channel low; a state color always has at least one bright
-- channel, so this also requires the brightest channel to be under 0.5.
local function IsDarkText(r, g, b)
    return Luma(r, g, b) < DARK_TEXT_LUMA and math.max(r or 0, g or 0, b or 0) < 0.5
end

-- Exported for PanelSkins.lua's panel-guts retint helper (RetintDarkText),
-- which needs this file's own dark-text gate outside its own chunk; local
-- aliases above are kept so LightenParchmentFonts/RestoreParchmentFonts below
-- are unchanged.
Theme.Luma = Luma
Theme.DARK_TEXT_LUMA = DARK_TEXT_LUMA
Theme.IsDarkText = IsDarkText

Theme.parchmentFontsRetinted = Theme.parchmentFontsRetinted or {}

function Theme.LightenParchmentFonts()
    local c = Theme.COLOR_TEXT_PARCHMENT
    local done = Theme.parchmentFontsRetinted

    for _, name in ipairs(PARCHMENT_FONTS) do
        local font = _G[name]
        if font and not done[name] and font.GetTextColor and font.SetTextColor then
            local ok, r, g, b = pcall(font.GetTextColor, font)
            if ok and r and IsDarkText(r, g, b) then
                -- Record what it was, so this is reversible without a /reload.
                done[name] = { r, g, b }
                pcall(font.SetTextColor, font, c[1], c[2], c[3])
            end
        end
    end
end

function Theme.RestoreParchmentFonts()
    for name, rgb in pairs(Theme.parchmentFontsRetinted) do
        local font = _G[name]
        if font and font.SetTextColor then
            pcall(font.SetTextColor, font, rgb[1], rgb[2], rgb[3])
        end
    end
    Theme.parchmentFontsRetinted = {}
end

-------------------------------------------------------------------------------
-- Font application
-------------------------------------------------------------------------------

-- Paths already reported as failed, so the warning below prints once per font
-- rather than once per fontstring per update pass.
local warnedFontPaths = {}

-- Compares two font paths tolerantly: the client may hand back a different
-- slash style or case than the one we passed in, and a false mismatch here
-- would trigger the fallback on a perfectly good font.
local function SameFontPath(a, b)
    if not a or not b then return false end
    a = tostring(a):lower():gsub("/", "\\")
    b = tostring(b):lower():gsub("/", "\\")
    return a == b
end

-- Exported for Diagnostics.lua's /fsfont: a separate .lua file is a separate
-- chunk and cannot see this local, only a FS.Theme.* table field.
Theme.SameFontPath = SameFontPath

function Theme.ApplyFontGeneric(fontString, path, size, color, flags)
    if flags == nil then flags = "OUTLINE" end

    fontString:SetFont(path, size, flags)

    -- Do NOT branch on SetFont's return value. It is a boolean on a FontString
    -- but a FontInstance FRAME (e.g. ChatFrame1) returns nothing at all, so
    -- `if not ok` fired on a SUCCESSFUL call and the fallback below overwrote
    -- our font with FRIZQT. Measured on interface 16001: chat went ARIALN ->
    -- FRIZQT and never to Mononoki because of exactly this. Read it back
    -- instead, which is true for every widget type.
    local applied = fontString.GetFont and fontString:GetFont()
    if not SameFontPath(applied, path) then
        -- A real failure. Say so: the silent version of this fallback cost a
        -- full in-game verification cycle by making a failure look like it worked.
        if not warnedFontPaths[path] then
            warnedFontPaths[path] = true
            local msg = "|cffff4488ForeverSynthwave|r: SetFont failed for " .. tostring(path) .. ", using fallback"
            if DEFAULT_CHAT_FRAME and DEFAULT_CHAT_FRAME.AddMessage then
                DEFAULT_CHAT_FRAME:AddMessage(msg)
            else
                print(msg)
            end
        end
        local defaultFont, defaultSize = GameFontNormal:GetFont()
        fontString:SetFont(defaultFont or "Fonts\\FRIZQT__.TTF", size or defaultSize, flags)
    end
    local c = color or Theme.COLOR_TEXT_WHITE
    fontString:SetTextColor(c[1], c[2], c[3], c[4] or 1)
    fontString:SetShadowColor(0, 0, 0, 1)
    fontString:SetShadowOffset(1, -1)
end

function Theme.ApplyMono(fontString, size, color)
    -- Plain glyphs: no OUTLINE (renders unevenly on this font) and no shadow --
    -- the user judged this cleanest in-game. Contrast on the brightest bars is
    -- deferred for beta tuning.
    Theme.ApplyFontGeneric(fontString, Theme.FONT_MONO, size, color, "")
    fontString:SetShadowColor(0, 0, 0, 0)
end

-------------------------------------------------------------------------------
-- Outer glow / rounded fill / gradient border
-------------------------------------------------------------------------------

-- Outward, border-following halo (CSS box-shadow model): four glow_edge.tga
-- strips fade straight out from each edge plus four corner pieces, all OUTSIDE
-- the frame so the interior is never filled. `radius` selects the corner
-- shape and MUST match the frame's own corner radius:
--   radius == 0 (square frame, e.g. the level badge): edge strips run flush
--     corner-to-corner; corners are radial glow_corner.tga quads blooming from
--     the square corner point. The corner texture shares the edges' quadratic
--     falloff so the corner has no "X" seam.
--   radius >  0 (rounded frame, e.g. the panel): edge strips are inset by
--     `radius` so they cover only the straight run; corners are quarter-annulus
--     glow_corner_round.tga pieces that hug the rounded border arc. Without
--     this the glow traces the SQUARE frame corner and pokes a nub past the
--     rounded border (the "square corners over a round panel" bug).
-- The bright end (texture v=0, alpha 255) always faces the border.
--
-- Under Theme.CHROME_CORNERS == "cut" a radius > 0 is instead the REQUESTED CHAMFER
-- (snapped to the baked set) and only TOP-LEFT and BOTTOM-RIGHT are cut: those two
-- corners take one glow_corner_cut.tga piece each (same box and flip layout as the
-- annulus, the texture is baked at chamfer:size 6:8 and stretched whole), the other two
-- are the plain square glow_corner.tga bloom, and the strips are inset by the chamfer
-- only at the cut ends. Radius 0 stays fully square in either mode.
function Theme.AddOuterGlow(frame, r, g, b, size, alpha, radius)
    local rad = radius or 0 -- 0 = square corners (level badge); >0 = rounded (panel)
    local cut = Theme.CHROME_CORNERS == "cut" and rad > 0
    if cut then rad = Theme.SnapCut(rad) end
    -- Per-end strip insets: all four equal under "round", only the cut corners' ends
    -- under "cut" (the square TOP-RIGHT / BOTTOM-LEFT ends run flush to the corner).
    local insetTL, insetTR, insetBL, insetBR = rad, rad, rad, rad
    if cut then insetTR, insetBL = 0, 0 end

    -- Edge strips are INSET by `rad` at their ends so they cover only the
    -- straight portion of a rounded frame (for rad=0 this is flush, the
    -- square case). Each strip's bright edge (texture v=0) faces the panel.
    local top = frame:CreateTexture(nil, "BACKGROUND")
    top:SetTexture(Theme.GLOW_EDGE_TEXTURE)
    top:SetPoint("BOTTOMLEFT", frame, "TOPLEFT", insetTL, 0)
    top:SetPoint("BOTTOMRIGHT", frame, "TOPRIGHT", -insetTR, 0)
    top:SetHeight(size)
    top:SetTexCoord(0, 1, 0, 0, 1, 1, 1, 0)
    top:SetBlendMode("ADD")
    top:SetVertexColor(r, g, b, alpha)

    local bottom = frame:CreateTexture(nil, "BACKGROUND")
    bottom:SetTexture(Theme.GLOW_EDGE_TEXTURE)
    bottom:SetPoint("TOPLEFT", frame, "BOTTOMLEFT", insetBL, 0)
    bottom:SetPoint("TOPRIGHT", frame, "BOTTOMRIGHT", -insetBR, 0)
    bottom:SetHeight(size)
    bottom:SetBlendMode("ADD")
    bottom:SetVertexColor(r, g, b, alpha)

    -- Left/right: gradient rotated 90 degrees (alpha varies along x).
    local left = frame:CreateTexture(nil, "BACKGROUND")
    left:SetTexture(Theme.GLOW_EDGE_TEXTURE)
    left:SetPoint("TOPRIGHT", frame, "TOPLEFT", 0, -insetTL)
    left:SetPoint("BOTTOMRIGHT", frame, "BOTTOMLEFT", 0, insetBL)
    left:SetWidth(size)
    left:SetTexCoord(0, 1, 0, 1, 0, 0, 0, 0)
    left:SetBlendMode("ADD")
    left:SetVertexColor(r, g, b, alpha)

    local right = frame:CreateTexture(nil, "BACKGROUND")
    right:SetTexture(Theme.GLOW_EDGE_TEXTURE)
    right:SetPoint("TOPLEFT", frame, "TOPRIGHT", 0, -insetTR)
    right:SetPoint("BOTTOMLEFT", frame, "BOTTOMRIGHT", 0, insetBR)
    right:SetWidth(size)
    right:SetTexCoord(0, 0, 0, 0, 0, 1, 0, 1)
    right:SetBlendMode("ADD")
    right:SetVertexColor(r, g, b, alpha)

    if cut then
        local box = rad + size
        local pieces = {
            -- own point, frame corner, offset x, offset y, texcoord L,R,T,B
            { "BOTTOMRIGHT", "TOPLEFT",      rad, -rad, 0, 1, 0, 1 },
            { "TOPLEFT",     "BOTTOMRIGHT", -rad,  rad, 1, 0, 1, 0 },
        }
        for _, c in ipairs(pieces) do
            local corner = frame:CreateTexture(nil, "BACKGROUND")
            corner:SetTexture(Theme.GLOW_CORNER_CUT_TEXTURE)
            corner:SetSize(box, box)
            corner:SetPoint(c[1], frame, c[2], c[3], c[4])
            corner:SetTexCoord(c[5], c[6], c[7], c[8])
            corner:SetBlendMode("ADD")
            corner:SetVertexColor(r, g, b, alpha)
        end
        -- The square corners: the radial glow_corner.tga bloom, quadrants as in the
        -- square case below.
        local squares = {
            { "BOTTOMLEFT", "TOPRIGHT",   0.5, 0,   0.5, 0.5, 1,   0,   1,   0.5 },
            { "TOPRIGHT",   "BOTTOMLEFT", 0,   0.5, 0,   1,   0.5, 0.5, 0.5, 1   },
        }
        for _, c in ipairs(squares) do
            local corner = frame:CreateTexture(nil, "BACKGROUND")
            corner:SetTexture(Theme.GLOW_CORNER_TEXTURE)
            corner:SetSize(size, size)
            corner:SetPoint(c[1], frame, c[2], 0, 0)
            corner:SetTexCoord(c[3], c[4], c[5], c[6], c[7], c[8], c[9], c[10])
            corner:SetBlendMode("ADD")
            corner:SetVertexColor(r, g, b, alpha)
        end
    elseif rad > 0 then
        -- Rounded corners: a quarter-annulus halo (glow_corner_round.tga) that
        -- hugs the rounded border arc. Each box is (rad+size) square with its
        -- INNER point (the arc center) pinned `rad` inside the frame corner;
        -- the 4-arg SetTexCoord flips reuse the top-left-baked texture. This
        -- is what stops the glow from tracing the SQUARE frame corner and
        -- poking a square nub past the rounded border.
        local box = rad + size
        local corners = {
            -- own point, frame corner, offset x, offset y, texcoord L,R,T,B
            { "BOTTOMRIGHT", "TOPLEFT",      rad, -rad, 0, 1, 0, 1 },
            { "BOTTOMLEFT",  "TOPRIGHT",    -rad, -rad, 1, 0, 0, 1 },
            { "TOPRIGHT",    "BOTTOMLEFT",   rad,  rad, 0, 1, 1, 0 },
            { "TOPLEFT",     "BOTTOMRIGHT", -rad,  rad, 1, 0, 1, 0 },
        }
        for _, c in ipairs(corners) do
            local corner = frame:CreateTexture(nil, "BACKGROUND")
            corner:SetTexture(Theme.GLOW_CORNER_ROUND_TEXTURE)
            corner:SetSize(box, box)
            corner:SetPoint(c[1], frame, c[2], c[3], c[4])
            corner:SetTexCoord(c[5], c[6], c[7], c[8])
            corner:SetBlendMode("ADD")
            corner:SetVertexColor(r, g, b, alpha)
        end
    else
        -- Square corners: radial glow_corner.tga quads whose center (0.5,0.5)
        -- pins to the frame corner. 8-arg SetTexCoord selects the quadrant.
        local corners = {
            { "BOTTOMRIGHT", "TOPLEFT",     0,   0,    0,   0.5,  0.5, 0,    0.5, 0.5 },
            { "BOTTOMLEFT",  "TOPRIGHT",    0.5, 0,    0.5, 0.5,  1,   0,    1,   0.5 },
            { "TOPRIGHT",    "BOTTOMLEFT",  0,   0.5,  0,   1,    0.5, 0.5,  0.5, 1   },
            { "TOPLEFT",     "BOTTOMRIGHT", 0.5, 0.5,  0.5, 1,    1,   0.5,  1,   1   },
        }
        for _, c in ipairs(corners) do
            local corner = frame:CreateTexture(nil, "BACKGROUND")
            corner:SetTexture(Theme.GLOW_CORNER_TEXTURE)
            corner:SetSize(size, size)
            corner:SetPoint(c[1], frame, c[2], 0, 0)
            corner:SetTexCoord(c[3], c[4], c[5], c[6], c[7], c[8], c[9], c[10])
            corner:SetBlendMode("ADD")
            corner:SetVertexColor(r, g, b, alpha)
        end
    end
end

-- Rounded-rect background fill, radius `rad`, as a 9-slice of flat-color rects
-- (center + 4 edges) plus four fill_corner.tga quarter-discs at the corners.
-- The pieces tile without overlapping, so the translucent fill stays a uniform
-- alpha (overlapping translucent rects would darken the seams), and the corner
-- discs are FIXED size so they align with the border/glow arcs at both panel
-- heights (a single stretched rounded-rect fill misaligns on the short frame).
-- Sublevel -8 is the lowest BACKGROUND sublevel available, forcing every fill
-- piece behind anything else in this frame's BACKGROUND layer (in particular
-- Blizzard's own panel parchment/text on skinned Blizzard frames, which sit
-- at BACKGROUND with no explicit sublevel and were otherwise being washed out).
local FILL_SUBLEVEL = -8

-- own point, frame corner, 4-arg SetTexCoord flip (L, R, T, B). Shared by
-- AddRoundedFill (fill_corner.tga) and AddCornerMask (anti_corner.tga) below,
-- since both textures are baked in the same top-left orientation.
local CORNER_TEXCOORDS = {
    { "TOPLEFT",     "TOPLEFT",     0, 1, 0, 1 },
    { "TOPRIGHT",    "TOPRIGHT",    1, 0, 0, 1 },
    { "BOTTOMLEFT",  "BOTTOMLEFT",  0, 1, 1, 0 },
    { "BOTTOMRIGHT", "BOTTOMRIGHT", 1, 0, 1, 0 },
}

-- Under Theme.CHROME_CORNERS == "cut" `rad` is the REQUESTED CHAMFER (snapped to the baked
-- set) and only TOP-LEFT and BOTTOM-RIGHT are cut: three flat rects (a top run from the
-- cut to the square TOP-RIGHT corner, a full-width middle band, a bottom run from the
-- square BOTTOM-LEFT corner to the cut) plus a fill_cut_c{c} triangle at each cut corner,
-- five regions that tile without overlap so the translucent fill keeps one alpha. rad 0
-- stays on the plain path below in either mode.
function Theme.AddRoundedFill(panel, color, rad)
    local r, g, b, a = color[1], color[2], color[3], color[4] or 1

    if Theme.CHROME_CORNERS == "cut" and rad > 0 then
        local c = Theme.SnapCut(rad)
        local function cutRect()
            local t = panel:CreateTexture(nil, "BACKGROUND")
            t:SetDrawLayer("BACKGROUND", FILL_SUBLEVEL)
            t:SetColorTexture(r, g, b, a)
            return t
        end

        local top = cutRect()
        top:SetPoint("TOPLEFT", panel, "TOPLEFT", c, 0)
        top:SetPoint("TOPRIGHT", panel, "TOPRIGHT", 0, 0)
        top:SetHeight(c)

        local middle = cutRect()
        middle:SetPoint("TOPLEFT", panel, "TOPLEFT", 0, -c)
        middle:SetPoint("BOTTOMRIGHT", panel, "BOTTOMRIGHT", 0, c)

        local bottom = cutRect()
        bottom:SetPoint("BOTTOMLEFT", panel, "BOTTOMLEFT", 0, 0)
        bottom:SetPoint("BOTTOMRIGHT", panel, "BOTTOMRIGHT", -c, 0)
        bottom:SetHeight(c)

        for _, corner in ipairs({ "TOPLEFT", "BOTTOMRIGHT" }) do
            local t = panel:CreateTexture(nil, "BACKGROUND")
            t:SetDrawLayer("BACKGROUND", FILL_SUBLEVEL)
            t:SetTexture(Theme.FILL_CUT_TEXTURES[c])
            t:SetVertexColor(r, g, b, a)
            t:SetSize(c, c)
            t:SetPoint(corner, panel, corner, 0, 0)
            t:SetTexCoord(CutCoords(corner, c))
        end
        return
    end

    local function rect()
        local t = panel:CreateTexture(nil, "BACKGROUND")
        t:SetDrawLayer("BACKGROUND", FILL_SUBLEVEL)
        t:SetColorTexture(r, g, b, a)
        return t
    end

    local center = rect()
    center:SetPoint("TOPLEFT", panel, "TOPLEFT", rad, -rad)
    center:SetPoint("BOTTOMRIGHT", panel, "BOTTOMRIGHT", -rad, rad)

    local top = rect()
    top:SetPoint("TOPLEFT", panel, "TOPLEFT", rad, 0)
    top:SetPoint("TOPRIGHT", panel, "TOPRIGHT", -rad, 0)
    top:SetHeight(rad)

    local bottom = rect()
    bottom:SetPoint("BOTTOMLEFT", panel, "BOTTOMLEFT", rad, 0)
    bottom:SetPoint("BOTTOMRIGHT", panel, "BOTTOMRIGHT", -rad, 0)
    bottom:SetHeight(rad)

    local left = rect()
    left:SetPoint("TOPLEFT", panel, "TOPLEFT", 0, -rad)
    left:SetPoint("BOTTOMLEFT", panel, "BOTTOMLEFT", 0, rad)
    left:SetWidth(rad)

    local right = rect()
    right:SetPoint("TOPRIGHT", panel, "TOPRIGHT", 0, -rad)
    right:SetPoint("BOTTOMRIGHT", panel, "BOTTOMRIGHT", 0, rad)
    right:SetWidth(rad)

    for _, c in ipairs(CORNER_TEXCOORDS) do
        local t = panel:CreateTexture(nil, "BACKGROUND")
        t:SetDrawLayer("BACKGROUND", FILL_SUBLEVEL)
        t:SetTexture(Theme.FILL_CORNER_TEXTURE)
        t:SetVertexColor(r, g, b, a)
        t:SetSize(rad, rad)
        t:SetPoint(c[1], panel, c[2], 0, 0)
        t:SetTexCoord(c[3], c[4], c[5], c[6])
    end
end

-- Overpaints a StatusBar fill's square corners with `color` (normally
-- Theme.COLOR_BAR_TRACK, the color already behind the fill) so the fill
-- reads as rounded without clipping it: Theme.ANTI_CORNER_TEXTURE is opaque
-- outside the rounding arc (hides the fill's true square corner) and
-- transparent inside it (lets the fill's own rounded silhouette show
-- through). `host` is the frame the quads are created on -- its FrameLevel
-- is what has to sit above the fill and anything drawn on top of it, not the
-- draw layer chosen here; `anchorFrame` supplies the four corner points
-- (the fill's own rect, not the shell's -- the shell's corners are
-- transparent outside ITS arc, so track color placed there would draw a
-- square notch instead of a round one). Static geometry only: never reads a
-- bar's value, so it is safe on units where health/power are secret.
--
-- Under Theme.CHROME_CORNERS == "cut" `radius` is the requested chamfer (snapped to the
-- baked set) and the quads are anti_cut_c{c} erase triangles at TOP-LEFT and
-- BOTTOM-RIGHT only (leg c - 0.586, baked for a 1 unit fill inset); TOP-RIGHT and
-- BOTTOM-LEFT get no erase quad, so there are two quads, not four.
function Theme.AddCornerMask(host, anchorFrame, color, radius)
    local r, g, b, a = color[1], color[2], color[3], color[4] or 1
    local quads = {}
    if Theme.CHROME_CORNERS == "cut" and radius > 0 then
        local c = Theme.SnapCut(radius)
        for _, corner in ipairs({ "TOPLEFT", "BOTTOMRIGHT" }) do
            local t = host:CreateTexture(nil, "BACKGROUND")
            t:SetTexture(Theme.ANTI_CUT_TEXTURES[c])
            t:SetVertexColor(r, g, b, a)
            t:SetSize(c, c)
            t:SetPoint(corner, anchorFrame, corner, 0, 0)
            t:SetTexCoord(CutCoords(corner, c))
            t.fsCutCorner = corner
            quads[#quads + 1] = t
        end
        return quads
    end
    for _, c in ipairs(CORNER_TEXCOORDS) do
        local t = host:CreateTexture(nil, "BACKGROUND")
        t:SetTexture(Theme.ANTI_CORNER_TEXTURE)
        t:SetVertexColor(r, g, b, a)
        t:SetSize(radius, radius)
        t:SetPoint(c[1], anchorFrame, c[2], 0, 0)
        t:SetTexCoord(c[3], c[4], c[5], c[6])
        quads[#quads + 1] = t
    end
    return quads
end

-- Resize handle shared by AddFillCorners and AddLeadingEdgeCorners. Cut quads (tagged
-- with `fsCutCorner` by AddCornerMask / AddLeadingEdgeCorners) swap to the anti_cut file
-- of the snapped chamfer and re-sample its canvas; round quads only resize.
local function CornerQuadHandle(quads)
    return {
        quads = quads,
        SetRadius = function(radius)
            for _, t in ipairs(quads) do
                local corner = t.fsCutCorner
                if corner then
                    local c = Theme.SnapCut(radius)
                    -- c == 0 hides the quad (the round path shrinks to 0x0); c > 0 shows it again.
                    t:SetShown(c > 0)
                    if c > 0 then
                        t:SetTexture(Theme.ANTI_CUT_TEXTURES[c])
                        t:SetSize(c, c)
                        t:SetTexCoord(CutCoords(corner, c))
                    end
                else
                    t:SetSize(radius, radius)
                end
            end
        end,
    }
end

-- Erases a StatusBar fill's four static corners (the bar rect's corners) with
-- opaque track color via AddCornerMask; `eraseColor`'s alpha is forced to 1 so
-- the fill cannot bleed through. These quads only matter near a full bar, the
-- moving right end is AddLeadingEdgeCorners' job. Returns { quads, SetRadius }.
function Theme.AddFillCorners(host, anchorFrame, eraseColor, radius)
    local quads = Theme.AddCornerMask(host, anchorFrame, { eraseColor[1], eraseColor[2], eraseColor[3], 1 }, radius)
    return CornerQuadHandle(quads)
end

-- Rounds the moving right end of a StatusBar fill with two opaque erase quads
-- anchored to `bar:GetStatusBarTexture()`'s TOPRIGHT/BOTTOMRIGHT, so the engine
-- moves them and Lua never reads the (possibly secret) value. The quads live on
-- a child Frame of `host` (same level), and `host` must SetClipsChildren, which
-- clips child frames only, so a fill narrower than `radius` cannot spill them
-- past the bar's left edge. Returns { quads, SetRadius }. Under
-- Theme.CHROME_CORNERS == "cut" only the BOTTOM-RIGHT corner is cut (one anti_cut quad;
-- the TOP-RIGHT end stays square).
function Theme.AddLeadingEdgeCorners(host, bar, color, radius)
    local fillTexture = bar:GetStatusBarTexture()
    local clipChild = CreateFrame("Frame", nil, host)
    clipChild:SetAllPoints(host)
    clipChild:SetFrameLevel(host:GetFrameLevel())
    local quads = {}
    if Theme.CHROME_CORNERS == "cut" and radius > 0 then
        local c = Theme.SnapCut(radius)
        local t = clipChild:CreateTexture(nil, "BACKGROUND")
        t:SetTexture(Theme.ANTI_CUT_TEXTURES[c])
        t:SetVertexColor(color[1], color[2], color[3], 1)
        t:SetSize(c, c)
        t:SetPoint("BOTTOMRIGHT", fillTexture, "BOTTOMRIGHT", 0, 0)
        t:SetTexCoord(CutCoords("BOTTOMRIGHT", c))
        t.fsCutCorner = "BOTTOMRIGHT"
        quads[1] = t
        return CornerQuadHandle(quads)
    end
    for _, c in ipairs(CORNER_TEXCOORDS) do
        if c[1] == "TOPRIGHT" or c[1] == "BOTTOMRIGHT" then
            local t = clipChild:CreateTexture(nil, "BACKGROUND")
            t:SetTexture(Theme.ANTI_CORNER_TEXTURE)
            t:SetVertexColor(color[1], color[2], color[3], 1)
            t:SetSize(radius, radius)
            t:SetPoint(c[1], fillTexture, c[2], 0, 0)
            t:SetTexCoord(c[3], c[4], c[5], c[6])
            quads[#quads + 1] = t
        end
    end
    return CornerQuadHandle(quads)
end

-- Pill end caps for a StatusBar whose own rect is the pill's straight middle
-- (inset by `radius` each side). Each cap is two FILL_CORNER_TEXTURE quarter
-- discs, `radius` wide and `fillHeight / 2` tall, opaque side facing outward:
-- the left cap sits against the bar's left edge, the right cap rides
-- `bar:GetStatusBarTexture()`'s right edge, so the engine moves it and Lua
-- never reads the (possibly secret) value. Returns { textures, tip,
-- SetColor(r, g, b, a), SetDesaturated(bool), SetRadius(r, fillH),
-- SetShown(bool) }; `tip` is a Frame spanning the right cap, so its RIGHT
-- edge is the fill's visible tip.
local CAP_PIECES = {
    { "TOPLEFT",     "TOPRIGHT",    "TOPLEFT",     false },
    { "BOTTOMLEFT",  "BOTTOMRIGHT", "BOTTOMLEFT",  false },
    { "TOPRIGHT",    "TOPRIGHT",    "TOPRIGHT",    true },
    { "BOTTOMRIGHT", "BOTTOMRIGHT", "BOTTOMRIGHT", true },
}

function Theme.AddPillCaps(parent, bar, color, radius, fillHeight)
    local host = CreateFrame("Frame", nil, parent)
    host:SetAllPoints(parent)
    host:SetFrameLevel(bar:GetFrameLevel())

    local fillTexture = bar:GetStatusBarTexture()
    local tip = CreateFrame("Frame", nil, host)
    tip:SetPoint("TOPLEFT", fillTexture, "TOPRIGHT", 0, 0)
    tip:SetPoint("BOTTOMLEFT", fillTexture, "BOTTOMRIGHT", 0, 0)
    tip:SetWidth(radius)

    local texCoords = {}
    for _, c in ipairs(CORNER_TEXCOORDS) do
        texCoords[c[1]] = c
    end

    local textures = {}
    for _, piece in ipairs(CAP_PIECES) do
        local corner, ownPoint, relPoint, onTip = piece[1], piece[2], piece[3], piece[4]
        local c = texCoords[corner]
        local t = host:CreateTexture(nil, "ARTWORK")
        t:SetTexture(Theme.FILL_CORNER_TEXTURE)
        t:SetVertexColor(color[1], color[2], color[3], color[4] or 1)
        t:SetSize(radius, fillHeight / 2)
        t:SetPoint(ownPoint, onTip and tip or bar, relPoint, 0, 0)
        t:SetTexCoord(c[3], c[4], c[5], c[6])
        textures[#textures + 1] = t
    end

    return {
        textures = textures,
        tip = tip,
        SetColor = function(r, g, b, a)
            for _, t in ipairs(textures) do
                t:SetVertexColor(r, g, b, a or 1)
            end
        end,
        SetDesaturated = function(desaturated)
            for _, t in ipairs(textures) do
                if t.SetDesaturated then t:SetDesaturated(desaturated) end
            end
        end,
        SetRadius = function(newRadius, newFillHeight)
            tip:SetWidth(newRadius)
            for _, t in ipairs(textures) do
                t:SetSize(newRadius, newFillHeight / 2)
            end
        end,
        SetShown = function(shown)
            host:SetShown(shown)
        end,
    }
end

-- Cut variant of AddPillCaps (nothing calls it yet; DataBar's meter swaps to it
-- explicitly, it is NOT behind Theme.CHROME_CORNERS). Same arguments and same returned
-- handle, but `radius` is the requested chamfer (snapped to the baked set) and `fillHeight`
-- the full bar height. Only TOP-LEFT and BOTTOM-RIGHT are cut, so each cap is a
-- fill_cut_c{c} triangle at the cut corner plus a flat `radius` x (fillHeight - c)
-- rectangle for the square half: the left cap sits against the bar's left edge
-- (triangle on top), the right cap rides the fill tip (triangle at the bottom). All four
-- pieces are COLORED textures, so a translucent track still shows through them, and
-- SetColor / SetDesaturated keep working on every piece.
function Theme.AddCutPillCaps(parent, bar, color, radius, fillHeight)
    local host = CreateFrame("Frame", nil, parent)
    host:SetAllPoints(parent)
    host:SetFrameLevel(bar:GetFrameLevel())

    local c = Theme.SnapCut(radius)
    local fillTexture = bar:GetStatusBarTexture()
    local tip = CreateFrame("Frame", nil, host)
    tip:SetPoint("TOPLEFT", fillTexture, "TOPRIGHT", 0, 0)
    tip:SetPoint("BOTTOMLEFT", fillTexture, "BOTTOMRIGHT", 0, 0)
    tip:SetWidth(c)

    local textures = {}
    local function piece(ownPoint, relFrame, relPoint)
        local t = host:CreateTexture(nil, "ARTWORK")
        t:SetVertexColor(color[1], color[2], color[3], color[4] or 1)
        t:SetPoint(ownPoint, relFrame, relPoint, 0, 0)
        textures[#textures + 1] = t
        return t
    end
    local leftTri = piece("TOPRIGHT", bar, "TOPLEFT")
    local leftRect = piece("BOTTOMRIGHT", bar, "BOTTOMLEFT")
    local rightRect = piece("TOPRIGHT", tip, "TOPRIGHT")
    local rightTri = piece("BOTTOMRIGHT", tip, "BOTTOMRIGHT")

    local function layout(newChamfer, newFillHeight)
        local size = Theme.SnapCut(newChamfer)
        local rest = math.max(newFillHeight - size, 0.01)
        tip:SetWidth(size)
        for _, tri in ipairs({ leftTri, rightTri }) do
            tri:SetTexture(Theme.FILL_CUT_TEXTURES[size])
            tri:SetSize(size, size)
        end
        leftTri:SetTexCoord(CutCoords("TOPLEFT", size))
        rightTri:SetTexCoord(CutCoords("BOTTOMRIGHT", size))
        for _, rect in ipairs({ leftRect, rightRect }) do
            rect:SetTexture(Theme.FLAT_TEXTURE)
            rect:SetSize(size, rest)
        end
    end
    layout(c, fillHeight)

    return {
        textures = textures,
        tip = tip,
        SetColor = function(r, g, b, a)
            for _, t in ipairs(textures) do
                t:SetVertexColor(r, g, b, a or 1)
            end
        end,
        SetDesaturated = function(desaturated)
            for _, t in ipairs(textures) do
                if t.SetDesaturated then t:SetDesaturated(desaturated) end
            end
        end,
        SetRadius = function(newRadius, newFillHeight)
            layout(newRadius, newFillHeight)
        end,
        SetShown = function(shown)
            host:SetShown(shown)
        end,
    }
end

-- Panel border, rounded corners (radius PANEL_RADIUS): a 9-slice outline of
-- four straight edges plus four rounded corner arcs. Solid at the bottom
-- fading to ~31% alpha at the top. The top/bottom edges are flat
-- ColorTextures and the left/right rails carry the vertical fade as
-- border_rail.tga (a baked alpha ramp, since SetGradient does not render on
-- this client); all four are INSET by the radius at their ends so they meet
-- the arcs tangentially. Each rail is anchored top+bottom so it STRETCHES to
-- the panel's current height -- unlike the old fixed-height segment stack,
-- which was sized to a hardcoded PANEL_HEIGHT and overhung the bottom by one
-- bar whenever the panel shrank to hide the power bar (any no-power target).
-- The four arcs reuse border_corner.tga (top-left orientation) with an H/V
-- SetTexCoord flip each; top corners take the faded top alpha, bottom corners
-- solid.
--
-- Under Theme.CHROME_CORNERS == "cut" `radius` is the requested chamfer (snapped to the
-- baked set) and only TOP-LEFT and BOTTOM-RIGHT are cut: a border_cut_c{c}_t{t} diagonal
-- stroke at each (top piece 0.31 alpha, bottom piece solid, same fade), the straight runs
-- inset by the chamfer only at the cut ends and tucked under each other at the square
-- TOP-RIGHT / BOTTOM-LEFT corners so the stroke never double-draws there. Six regions,
-- not eight. Thickness 2 has a baked stroke only for c = 6; smaller chamfers fall back to
-- the 1.0 stroke piece.
function Theme.AddGradientBorder(panel, color, thickness, radius)
    local r, g, b, a = color[1], color[2], color[3], color[4] or 1
    local alphaTop = a * 0.31
    local rad = radius or Theme.PANEL_RADIUS

    if Theme.CHROME_CORNERS == "cut" and rad > 0 then
        local c = Theme.SnapCut(rad)
        local top = panel:CreateTexture(nil, "BORDER")
        top:SetPoint("TOPLEFT", panel, "TOPLEFT", c, 0)
        top:SetPoint("TOPRIGHT", panel, "TOPRIGHT", 0, 0)
        top:SetHeight(thickness)
        top:SetColorTexture(r, g, b, alphaTop)

        local bottom = panel:CreateTexture(nil, "BORDER")
        bottom:SetPoint("BOTTOMLEFT", panel, "BOTTOMLEFT", 0, 0)
        bottom:SetPoint("BOTTOMRIGHT", panel, "BOTTOMRIGHT", -c, 0)
        bottom:SetHeight(thickness)
        bottom:SetColorTexture(r, g, b, a)

        local leftRail = panel:CreateTexture(nil, "BORDER")
        leftRail:SetTexture(Theme.BORDER_RAIL_TEXTURE)
        leftRail:SetPoint("TOPLEFT", panel, "TOPLEFT", 0, -c)
        leftRail:SetPoint("BOTTOMLEFT", panel, "BOTTOMLEFT", 0, thickness)
        leftRail:SetWidth(thickness)
        leftRail:SetVertexColor(r, g, b, a)

        local rightRail = panel:CreateTexture(nil, "BORDER")
        rightRail:SetTexture(Theme.BORDER_RAIL_TEXTURE)
        rightRail:SetPoint("TOPRIGHT", panel, "TOPRIGHT", 0, -thickness)
        rightRail:SetPoint("BOTTOMRIGHT", panel, "BOTTOMRIGHT", 0, c)
        rightRail:SetWidth(thickness)
        rightRail:SetVertexColor(r, g, b, a)

        local file = Theme.BORDER_CUT_TEXTURES[c][thickness >= 2 and 2 or 1]
            or Theme.BORDER_CUT_TEXTURES[c][1]
        local strokes = {
            { "TOPLEFT",     alphaTop },
            { "BOTTOMRIGHT", a },
        }
        for _, s in ipairs(strokes) do
            local stroke = panel:CreateTexture(nil, "BORDER")
            stroke:SetTexture(file)
            stroke:SetSize(c, c)
            stroke:SetPoint(s[1], panel, s[1], 0, 0)
            stroke:SetTexCoord(CutCoords(s[1], c))
            stroke:SetVertexColor(r, g, b, s[2])
        end
        return
    end

    local top = panel:CreateTexture(nil, "BORDER")
    top:SetPoint("TOPLEFT", panel, "TOPLEFT", rad, 0)
    top:SetPoint("TOPRIGHT", panel, "TOPRIGHT", -rad, 0)
    top:SetHeight(thickness)
    top:SetColorTexture(r, g, b, alphaTop)

    local bottom = panel:CreateTexture(nil, "BORDER")
    bottom:SetPoint("BOTTOMLEFT", panel, "BOTTOMLEFT", rad, 0)
    bottom:SetPoint("BOTTOMRIGHT", panel, "BOTTOMRIGHT", -rad, 0)
    bottom:SetHeight(thickness)
    bottom:SetColorTexture(r, g, b, a)

    -- border_rail.tga already ramps alpha 0.31 -> 1.0 top -> bottom; tint it
    -- the border color at full alpha (the texture supplies the fade).
    local leftRail = panel:CreateTexture(nil, "BORDER")
    leftRail:SetTexture(Theme.BORDER_RAIL_TEXTURE)
    leftRail:SetPoint("TOPLEFT", panel, "TOPLEFT", 0, -rad)
    leftRail:SetPoint("BOTTOMLEFT", panel, "BOTTOMLEFT", 0, rad)
    leftRail:SetWidth(thickness)
    leftRail:SetVertexColor(r, g, b, a)

    local rightRail = panel:CreateTexture(nil, "BORDER")
    rightRail:SetTexture(Theme.BORDER_RAIL_TEXTURE)
    rightRail:SetPoint("TOPRIGHT", panel, "TOPRIGHT", 0, -rad)
    rightRail:SetPoint("BOTTOMRIGHT", panel, "BOTTOMRIGHT", 0, rad)
    rightRail:SetWidth(thickness)
    rightRail:SetVertexColor(r, g, b, a)

    -- A square border has no corner arcs. Some clients resolve SetSize(0, 0)
    -- to the texture's native 64x64 size instead of making it invisible; the
    -- four resulting arcs covered the minimap with large blue crescents.
    if rad <= 0 then return end

    -- Corner arcs. Each entry: the arc's own point pinned to the frame corner,
    -- the frame corner, the 4-arg SetTexCoord flip (L, R, T, B), and the tint
    -- alpha for that corner's vertical position.
    local corners = {
        { "TOPLEFT",     "TOPLEFT",     0, 1, 0, 1, alphaTop },
        { "TOPRIGHT",    "TOPRIGHT",    1, 0, 0, 1, alphaTop },
        { "BOTTOMLEFT",  "BOTTOMLEFT",  0, 1, 1, 0, a },
        { "BOTTOMRIGHT", "BOTTOMRIGHT", 1, 0, 1, 0, a },
    }
    for _, c in ipairs(corners) do
        local arc = panel:CreateTexture(nil, "BORDER")
        arc:SetTexture(Theme.BORDER_CORNER_TEXTURE)
        arc:SetSize(rad, rad)
        arc:SetPoint(c[1], panel, c[2], 0, 0)
        arc:SetTexCoord(c[3], c[4], c[5], c[6])
        arc:SetVertexColor(r, g, b, c[7])
    end
end

-------------------------------------------------------------------------------
-- Generic Blizzard-frame skinning
-------------------------------------------------------------------------------

-- Blizzard sub-objects that carry a panel's own chrome. Hidden by name as well
-- as by region sweep, because on a modern client most of a panel's art hangs off
-- the frame as child OBJECTS (NineSlice is a whole frame of textures) rather
-- than as regions of the frame itself.
local BLIZZARD_CHROME = {
    "NineSlice", "Bg", "BG", "Background", "TitleBg", "TitleContainer",
    "TopTileStreaks", "TopBorder", "BottomBorder", "LeftBorder", "RightBorder",
    "PortraitContainer", "PortraitFrame", "portrait", "PortraitOverlay",
}

-- Insets carry a second, nested set of the same art.
local BLIZZARD_INSETS = { "Inset", "InsetFrame", "ScrollFrameInset", "ListInset" }

-- THE STEP THAT WAS MISSING, and the reason every panel skin has been invisible.
--
-- SkinPanel used to draw our chrome onto a Blizzard frame and leave that frame's
-- own art alone, which gives exactly two outcomes and this project has now shipped
-- both. Drawing over the top washed out Blizzard's text (Parker reported it on the
-- gossip dialog). The fix for that pushed our fill to BACKGROUND sublevel -8,
-- explicitly "behind Blizzard's own panel textures" -- which are OPAQUE, so from
-- then on the skin rendered underneath them and every panel looked stock.
--
-- Both symptoms are one missing step. Blizzard's art has to go first; then our
-- chrome can sit at a normal layer where it is both visible AND behind the text.
--
-- Deliberately NOT recursive. A child sweep would take item icons, spell icons,
-- money frames and every button's art with it. Only the frame's own regions and
-- the named chrome objects above.
function Theme.StripBlizzardChrome(frame, preserveTexture)
    if not frame then return end

    -- Re-strip pass: hide exactly what was hidden the first time and nothing
    -- else. A second blanket sweep would hide OUR chrome too, since by then it
    -- is also a texture region of this frame -- the panel would skin itself
    -- once and then erase itself on the next open.
    if frame.fsStripped then
        for _, obj in ipairs(frame.fsStripped) do
            if obj.Hide then pcall(obj.Hide, obj) end
        end
        return
    end

    local hidden = {}
    frame.fsStripped = hidden

    -- HIDE ONLY, never SetTexture(nil). Clearing the texture would also work and
    -- would survive a Blizzard re-Show, but it is destructive: the art cannot be
    -- put back without a /reload, and a panel that breaks is then hard to even
    -- look at. Hiding is reversible, and the OnShow re-strip below covers the
    -- re-Show case anyway.
    local function hide(obj)
        if not obj or obj == preserveTexture then return end
        if obj.Hide then pcall(obj.Hide, obj) end
        hidden[#hidden + 1] = obj
    end

    for _, region in ipairs({ frame:GetRegions() }) do
        if region ~= preserveTexture and region.GetObjectType and region:GetObjectType() == "Texture" then
            hide(region)
        end
    end

    for _, key in ipairs(BLIZZARD_CHROME) do
        hide(frame[key])
    end

    for _, key in ipairs(BLIZZARD_INSETS) do
        local inset = frame[key]
        if inset then
            hide(inset.Bg)
            hide(inset.NineSlice)
            if inset.GetRegions then
                for _, region in ipairs({ inset:GetRegions() }) do
                    if region.GetObjectType and region:GetObjectType() == "Texture" then
                        hide(region)
                    end
                end
            end
        end
    end

    -- Blizzard re-asserts its art when a panel is shown again, so one pass at
    -- skin time is not enough. The re-strip above is a handful of Hide calls on
    -- already-hidden regions, and it is what keeps a panel from reverting to
    -- stock the second time it is opened.
    if frame.HookScript and not frame.fsStripHooked then
        frame.fsStripHooked = true
        frame:HookScript("OnShow", Theme.StripBlizzardChrome)
    end
end

-- Skins Blizzard's close button to match: its own art stripped, our nine-sliced
-- button chrome, and a mono X. Panels kept reading as stock even where our
-- chrome landed, partly because the one control you always look at was still
-- Blizzard's gold-and-red circle.
function Theme.SkinCloseButton(frame)
    local close = frame.CloseButton
    if not close and frame.GetName and frame:GetName() then
        close = _G[frame:GetName() .. "CloseButton"]
    end
    if not close or close.fsClose then return end
    close.fsClose = true

    for _, region in ipairs({ close:GetRegions() }) do
        if region.GetObjectType and region:GetObjectType() == "Texture" then
            pcall(region.SetTexture, region, nil)
        end
    end

    local x = close:CreateFontString(nil, "OVERLAY")
    Theme.ApplyMono(x, 12, Theme.COLOR_HEALTH)
    x:SetPoint("CENTER", close, "CENTER", 0, 0)
    x:SetText("X")

    Theme.SkinButton(close, { borderColor = Theme.COLOR_HEALTH, glowSize = 4 })

    -- The only motion on the panel: the X warms on hover, so the control reads
    -- as live rather than painted on.
    close:HookScript("OnEnter", function() x:SetTextColor(1, 1, 1, 1) end)
    close:HookScript("OnLeave", function()
        x:SetTextColor(Theme.COLOR_HEALTH[1], Theme.COLOR_HEALTH[2], Theme.COLOR_HEALTH[3], 1)
    end)
end

-- The panel chrome stack, extracted from SkinPanel so the nameplate plate and the XP
-- tooltip can share one call site: nine-sliced fill (furthest back), an additive glow
-- overhanging the frame by SLICE_GLOW_PAD (just in front of it, so it reads as light
-- coming off the panel rather than a halo behind it), then the 1px border. The shape comes
-- from the SLICE_* constants (two-corner cut under "cut", rounded under "round"), so this
-- function never names a corner. Returns fill, glow, border so a caller can retint them.
--
-- opts (all optional): fillColor (default COLOR_BG, alpha default 0.92), accent (glow and
-- border colour, default COLOR_BORDER), glowAlpha (default 0.30).
function Theme.AddPanelChrome(frame, opts)
    opts = opts or {}
    local fillColor = opts.fillColor or Theme.COLOR_BG
    local accent = opts.accent or Theme.COLOR_BORDER
    local glowAlpha = opts.glowAlpha or 0.30

    local fill = Theme.AddSliceTexture(frame, Theme.SLICE_FILL_TEXTURE,
        { fillColor[1], fillColor[2], fillColor[3], fillColor[4] or 0.92 },
        "BACKGROUND", -2)

    local glow = Theme.AddSliceTexture(frame, Theme.SLICE_GLOW_TEXTURE,
        { accent[1], accent[2], accent[3], glowAlpha },
        "BACKGROUND", -1, -Theme.SLICE_GLOW_PAD)
    Theme.ApplyNineSlice(glow, Theme.SLICE_GLOW_MARGIN)
    glow:SetBlendMode("ADD")

    local border = Theme.AddSliceTexture(frame, Theme.SLICE_BORDER_TEXTURE,
        { accent[1], accent[2], accent[3], 1 }, "BORDER", 0)

    return fill, glow, border
end

-- Turns a Blizzard panel into a synthwave terminal window, using the same
-- vocabulary as the XP bar's tooltip: nine-sliced fill, an additive glow that
-- spills past the edge, a 1px neon border, a tinted header band with a rule
-- under it, and a `synthwave://` title in mono.
--
-- opts:
--   title      header label; the band and rule are only drawn when given
--   accent     header/border colour (default violet COLOR_BORDER)
--   strip      false to skip the Blizzard-art sweep, for frames we built
--              ourselves and which therefore have no art to strip
--   preserveTexture  one direct texture region to keep through the art sweep
--   scanline   false to skip the CRT scrim
--   radius / fillColor / borderColor / glowSize / glowAlpha as before
--
-- Returns the list of chrome regions created, as before.
-- Inset of a panel's title band, rule and scanline from the frame edge: ceil(c / 2) under
-- the cut corners so their TOP-LEFT and BOTTOM-RIGHT corners land on the chamfer line,
-- 2 under "round". SkinPanel and every hand-built title band (XPBar tooltip, Professions,
-- Tracker) use this one number.
function Theme.PanelBandInset()
    return CUT_PANEL and math.ceil(Theme.SLICE_MARGIN / 2) or 2
end

function Theme.SkinPanel(frame, opts)
    if not frame then return nil end
    opts = opts or {}

    local accent = opts.accent or opts.borderColor or Theme.COLOR_BORDER

    if opts.strip ~= false then
        Theme.StripBlizzardChrome(frame, opts.preserveTexture)
        Theme.SkinCloseButton(frame)
    end

    local before = select("#", frame:GetRegions())

    Theme.AddPanelChrome(frame, {
        fillColor = opts.fillColor, accent = accent, glowAlpha = opts.glowAlpha })

    -- Scanline, band and rule sit ceil(c / 2) inside the edge so their TOP-LEFT and
    -- BOTTOM-RIGHT corners land on the chamfer line instead of poking past the cut
    -- (c = 6 -> 3; the old 2 was a rounded-corner number). Under "round" it stays 2.
    local inset = Theme.PanelBandInset()

    if opts.scanline ~= false then
        -- Tiled rather than stretched: a stretched scanline texture resamples
        -- into grey mush at any size the panel happens to be.
        local scan = frame:CreateTexture(nil, "ARTWORK", nil, 7)
        scan:SetTexture(Theme.SCANLINE_TEXTURE, "REPEAT", "REPEAT")
        scan:SetHorizTile(true)
        scan:SetVertTile(true)
        scan:SetAlpha(Theme.SCANLINE_ALPHA)
        scan:SetPoint("TOPLEFT", frame, "TOPLEFT", inset, -inset)
        scan:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -inset, inset)
    end

    if opts.title then
        local band = frame:CreateTexture(nil, "ARTWORK")
        band:SetColorTexture(accent[1], accent[2], accent[3], 0.08)
        band:SetPoint("TOPLEFT", frame, "TOPLEFT", inset, -inset)
        band:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -inset, -inset)
        band:SetHeight(Theme.PANEL_HEADER_H)

        local rule = frame:CreateTexture(nil, "ARTWORK")
        rule:SetColorTexture(accent[1], accent[2], accent[3], 0.30)
        rule:SetPoint("TOPLEFT", band, "BOTTOMLEFT", 0, 0)
        rule:SetPoint("TOPRIGHT", band, "BOTTOMRIGHT", 0, 0)
        rule:SetHeight(1)

        local label = frame:CreateFontString(nil, "OVERLAY")
        Theme.ApplyMono(label, 10, accent)
        label:SetPoint("LEFT", band, "LEFT", 10, 0)
        label:SetText("synthwave://" .. opts.title)
        frame.fsPanelTitle = label
    end

    local allRegions = { frame:GetRegions() }
    local chrome = {}
    for i = before + 1, #allRegions do
        chrome[#chrome + 1] = allRegions[i]
    end
    return chrome
end

-- Gives a square icon button (action button, bag slot, aura icon) a thin
-- neon border (two-corner cut, top-left and bottom-right, under the default
-- Theme.CHROME_CORNERS == "cut"; rounded under "round") plus a subtle outer glow, both created on OVERLAY so
-- they always draw above the button's own icon/count and never touch its
-- parent, size, or attributes -- safe on secure buttons. Idempotent via
-- `button.fsSkin`: a second call skips border/glow creation and reuses the
-- stored overlay. opts may pass `count`/`hotkey`/`name` FontString refs to
-- restyle to plain Mononoki, since Blizzard's button templates vary too
-- widely to guess region names generically.
function Theme.SkinButton(button, opts)
    if not button then return nil end
    opts = opts or {}

    local skin = button.fsSkin
    if not skin then
        local color = opts.borderColor or Theme.COLOR_BORDER
        local r, g, b = color[1], color[2], color[3]
        -- opts.radius / opts.borderThickness are still accepted (every call
        -- site passes them) but no longer read: the border is one nine-sliced
        -- ring whose radius and thickness live in slice_border.tga. Honouring
        -- them would mean scaling the corner slice, which is exactly the
        -- resampling that made the old arcs staircase.
        local glowAlpha = opts.glowAlpha or 0.35

        skin = {}

        -- Outer glow: ONE nine-sliced texture, not four edge strips plus four
        -- corner quads.
        --
        -- Those strips were flush to the button's SQUARE edge, so nothing ever
        -- covered the area the rounded corner cuts away. Reading the pixels of
        -- a button corner shows it plainly -- the arc curves correctly, the
        -- halo (164d59) stops at the square edge, and between them sits the bar
        -- panel with no glow over it:
        --
        --     row 6:  22e0ff ... 22bddd 1f93b1 | 0c0b0e 0c0b0e | 164d59
        --     row 7:              237699 22afcf | 0d0c0e        | 174e59
        --
        -- That dark notch in all four corners is what Parker kept reporting as
        -- "the corners are still not correct", through several rounds of me
        -- looking at the border instead. A single texture whose shape IS the
        -- rounded rect cannot leave that gap.
        --
        -- opts.glowSize is no longer read: the falloff distance is baked into
        -- the texture (SLICE_GLOW_PAD), and scaling a nine-slice corner is
        -- exactly the resampling this whole approach exists to avoid.
        --
        -- opts.glowTexture / opts.glowPad / opts.glowMargin / opts.borderTexture /
        -- opts.borderMargin still override the default shape with another nine-slice
        -- set, and the result always lands in skin.glow / skin.border.ring, which Buffs
        -- and TargetAuras read to retint.
        --
        -- With no texture opts the default is the two-corner cut set (what
        -- SkinCutButton used to pass), its chamfer chosen by Theme.CutSizeIcon(button
        -- height) when the height is already known, else 6: a baked size per chamfer
        -- (Theme.Cut2ButtonSet), margin c on the ring and 4 + c on the glow. The chosen
        -- chamfer is stored as skin.chamfer so FrameHelpers.SeatCutIcon can inset the
        -- icon by ceil(c / 2). Region count is unchanged (glow + ring): nameplate aura
        -- buttons are engine-built, so no child frames and no extra regions here.
        -- Under "round" the default is the old rounded pair, unless opts.cut asks for cut
        -- (SkinCutButton does, so the action bars keep their shape in the A/B).
        local cut = opts.cut or Theme.CHROME_CORNERS == "cut"
        local ringTexture, ringMargin = opts.borderTexture, opts.borderMargin
        local glowTexture, glowPad, glowMargin = opts.glowTexture, opts.glowPad, opts.glowMargin
        if cut then
            local h = button.GetHeight and button:GetHeight()
            local c = opts.chamfer or ((h and h > 0) and Theme.CutSizeIcon(h)) or 6
            local ringPath, glowPath
            ringPath, glowPath, c = Theme.Cut2ButtonSet(c)
            skin.chamfer = c
            ringTexture = ringTexture or ringPath
            ringMargin = ringMargin or c
            glowTexture = glowTexture or glowPath
            glowPad = glowPad or Theme.SLICE_CUT2_GLOW_PAD
            glowMargin = glowMargin or (Theme.SLICE_CUT2_GLOW_PAD + c)
        end
        local pad = glowPad or Theme.SLICE_GLOW_PAD
        local glow = button:CreateTexture(nil, "OVERLAY", nil, 0)
        glow:SetTexture(glowTexture or Theme.SLICE_GLOW_TEXTURE)
        Theme.ApplyNineSlice(glow, glowMargin or Theme.SLICE_GLOW_MARGIN)
        glow:SetPoint("TOPLEFT", button, "TOPLEFT", -pad, pad)
        glow:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", pad, -pad)
        glow:SetBlendMode("ADD")
        glow:SetVertexColor(r, g, b, glowAlpha)

        skin.glow = glow

        -- Rounded border: ONE nine-sliced ring (slice_border.tga), not four
        -- rails plus four corner quads.
        --
        -- The old construction is what Parker kept seeing as "corners popping
        -- out". Dumping the pixels under his close-up showed the failure
        -- exactly: the left rail ended at one row, the arc quad started two
        -- rows later, and the button's near-black ground (111015) showed
        -- through the gap; the three border pixels that did land were a hard
        -- staircase, because a 64x64 arc drawn into a 4x4 quad has nothing
        -- left to interpolate.
        --
        -- A sliced ring cannot have that seam: one texture, corners emitted by
        -- the engine at native texel resolution with the antialiasing baked in
        -- at generation time. It also drops this from nine regions to one,
        -- which matters at 72 action buttons.
        --
        local ring = Theme.AddSliceTexture(
            button, ringTexture or Theme.SLICE_BORDER_TEXTURE, { r, g, b, 1 }, "OVERLAY", 1)
        if ringMargin then Theme.ApplyNineSlice(ring, ringMargin) end
        -- fsFlat false: Buffs.lua's TintAuraBorder reads this to decide between
        -- SetColorTexture (flat rails) and SetVertexColor (file textures). A
        -- sliced file texture wants the latter, which falsy already selects.
        ring.fsFlat = false
        skin.border = { ring = ring }


        button.fsSkin = skin
    end

    if opts.count then
        local _, size = opts.count:GetFont()
        Theme.ApplyMono(opts.count, size or 11)
    end
    if opts.hotkey then
        local _, size = opts.hotkey:GetFont()
        Theme.ApplyMono(opts.hotkey, size or 11)
    end
    if opts.name then
        local _, size = opts.name:GetFont()
        Theme.ApplyMono(opts.name, size or 11)
    end

    return skin
end

-- Alias kept for the action, pet and stance bars: SkinButton's default look IS the
-- two-corner cut set now, so this only differs under Theme.CHROME_CORNERS == "round",
-- where it still forces the cut shape (opts.cut) so those bars do not change in the A/B.
-- Delete with the flag.
--
-- It also pins the chamfer to Theme.SLICE_CUT_MARGIN (6) unless the caller passes one:
-- those bars hard-code a c = 6 plate, hover wash and hover glow, so a ring derived from
-- the button height (c = 4 under 30px) would not fit them. opts is copied, never mutated.
function Theme.SkinCutButton(button, opts)
    local o = {}
    for k, v in pairs(opts or {}) do o[k] = v end
    o.cut = true
    o.chamfer = o.chamfer or Theme.SLICE_CUT_MARGIN
    return Theme.SkinButton(button, o)
end

-- Restyles a Blizzard MoneyFrame/SmallMoneyFrame's gold/silver/copper text to
-- plain Mononoki + white. Assumes the standard `<name>GoldButtonText` /
-- `SilverButtonText` / `CopperButtonText` naming (verify in-game, since
-- older/simplified layouts can omit one). Missing regions are skipped rather
-- than erroring.
function Theme.StyleMoney(moneyFrame)
    if not moneyFrame then return end
    local name = moneyFrame.GetName and moneyFrame:GetName()
    if not name then return end

    local suffixes = { "GoldButtonText", "SilverButtonText", "CopperButtonText" }
    for _, suffix in ipairs(suffixes) do
        local fs = _G[name .. suffix]
        if fs and fs.SetFont then
            local _, size = fs:GetFont()
            Theme.ApplyMono(fs, size or 12, Theme.COLOR_TEXT_WHITE)
        end
    end
end
