-- Forever STUwave: Gunsight cast tapes (piece keys "you" and "tgt").
--
-- The two cast tapes of the Gunsight HUD (mockups/gunsight-hud-v2-2026-10-02/
-- gunsight-hud-v2-2026-10-02.html, drawTape, and the KICK tag and padlock of drawTarget): YOUR cast
-- on a 30 wide vertical tape left of the character (anchor tapeL), the TARGET's on an identical one right
-- of it (anchor tapeR). Both carry the SAME chevron track, half width C.HW (10: 20 across, 5 inset from each
-- side edge): the target used to run the mockup's wider hw 14 and its chevrons reached the plate edge while
-- yours stopped short (Parker, in game: they should look the same). Both are runs of the shared chevron engine
-- (ChevronCastBar.lua, vertical, TEXTURES_UP): 20 chevrons nested at the mockup pitch, dim at rest,
-- lit from the bottom as the cast fills. gunsight-hud pieces only; the info boxes (boxL / boxR) are
-- GunsightBoxes.lua's: BuildTape asks it for the box and hands the box's members to CastBars (see EXPORTS).
--
-- NO STATE MACHINE HERE. CastBars.lua owns every cast rule (events, verdicts, secrets, the strip
-- fallback); this file builds two bar tables with the members that state machine drives and hands them
-- over through FS.CastBars.SetView (the VIEW SEAM in CastBars.lua). With the Gunsight off none of this
-- is built and Stack A runs untouched; `/fsgun off` is the fallback.
--
-- A TAPE (BuildTape), all of it children of one piece frame that fills the anchor:
--   plate     the chamfered fill, rgba(13,6,32,.55) under A(.3)
--   layers    the frame stroke and the 11 outer edge ticks (BOT - k * (BOT - TOP) / 10, 5 long, 10 at
--             k = 5, alpha .7), one layer per colour: base (cyan, yours), or pink and steel (target's:
--             pink while the cast can be kicked, steel while it cannot). Stroke alpha .55, and the pink
--             stroke pulses .55 to 1 on the mockup's sin(clock * 7) while a cast is live (an alpha
--             animation, never an OnUpdate).
--   host      the cast host (= the bar's frame, never hidden): the engine run, seated TOP-to-TOP from the
--             anchor 8 image px below the frame top, always on its idle row of dim chevrons (alpha .2)
--   strips    the engine-timed StatusBars of the secret path (run:CreateStrip, vertical), anchored over
--             the run: pink and steel for the target, cyan for you. YOURS (and the target's degrade, below)
--             draw the strip tile and carry a dim copy of it, so the tape is not blank while the strip (and
--             not the run) is on screen.
--   reveals   the target only (BuildReveal, SeatReveal): the strips are the CLOCK and draw nothing (fill
--             alpha 0, still shown and timer driven); a clipped frame anchored from the strip's bottom to
--             its fill's TOP edge shows a column of the run's own lit chevrons at the run's segment rects,
--             with a dim row under it and the outline caret ON TOP of its top edge (the caret's bottom sits
--             on the edge, it caps the fill and does not hang into it), tinted pink and steel. The caret
--             lives on its own clipping frame that spans the run, so it never pokes past the run's top at
--             the end of a cast. The tone alpha (SetAlphaFromBoolean) lands on the reveal frames. A channel
--             fills up (StatusBar has no reverse fill on this client), the reveal edge is smooth, not a
--             chevron at a time.
--   cast tag  the target only: the KICK tag (pink) and the padlock (steel), seated off the boxR anchor
--             as the mockup does (kx = BOXR.x + BOXR.w - 40, ky = BOXR.y - 8, then up by the built target
--             box's own `grow` (GunsightBoxes' C.TGT_GROW; 0 when the box fell back to sinks)), shown only
--             with a live cast
--
-- TARGET LAYER. With no target the whole target tape hides (plate, edges, ticks, chevrons, strips, reveals,
-- KICK and padlock; its info box applies the same rule itself, see GunsightBoxes.lua). That is a SEPARATE
-- layer from the piece toggle (Gunsight.SetPiece is the user's on/off setting and drives the console key
-- LED): the target tape's drawing hangs off `t.gate`, a plain child of the piece frame, shown while the player
-- has a target and hidden while not, driven by PLAYER_TARGET_CHANGED and PLAYER_ENTERING_WORLD (and read once
-- at build). A visible tape needs the piece ON and a target. A secret or unreadable UnitExists keeps it shown.
-- Only visuals hide: CastBars keeps its own state machine, and the layer adds no OnUpdate. Show/Hide of the
-- gate is legal in combat (plain frames, nothing protected). Your tape is never gated. A rescale re-seats
-- and never calls Show on the gate. A rescale that lands while the tape is not visible (gate hidden, or the
-- tgt piece off or fading) marks it dirty; the gate showing or the tgt piece showing lays it out again.
--
-- THE TARGET IS ALWAYS ENGINE TIMED (the mockup's "engine: true"): the bar carries stripOnly, so CastBars
-- starts the strip (UnitCastingDuration + StatusBar:SetTimerDuration) for every target cast, secret or
-- not, and never starts the run on it. Nothing here reads a time, a castID or a flag: the interruptible
-- flag reaches SetAlphaFromBoolean through the shield stand-in and nowhere else (pink regions get
-- (flag, 0, 1), steel regions (flag, 1, 0)); a client without the method keeps the neutral steel look
-- and the tag and padlock are not shown.
--
-- DEGRADES (each logs once through FS.LogDegradeOnce, none ever throws): no vertical strip support
-- (SupportsVerticalStrip false, or CreateStrip returned nil) leaves the run without a strip and the
-- target fill hidden during a secret cast, plain casts still use the run; no Frame:SetClipsChildren
-- (gunsighttape_noclip) keeps today's visible strip tile on the target, no reveal; no FS.CastBars.SetView
-- leaves Stack A drawing and the tapes idle; a failed build hides whatever was built and registers nothing.
--
-- RESCALE. Everything is built once; FS.Layout.OnRescale re-seats and resizes in place (Gunsight's own
-- re-seat runs first). The run is given its chevron box, pitch and a length of whole physical pixels
-- (the engine's own rounding) so it always holds exactly 20 chevrons.
--
-- EXPORTS. FS.GunsightTape = { C (constants), colors, you, tgt }. A tape table holds key, anchor, piece,
-- gate (the target's visibility layer, nil on yours), dirty (set by a rescale that landed while the tape was not
-- visible, cleared by the re-layout that runs once it is), host, run, S (the bar table handed to CastBars), layers,
-- ticks, strips, castFrame, kick, padlock, fb,
-- pulse, box (the info box, nil when it did not build) and icon (Texture), timer, name, tabTicks (the
-- real regions CastBars' writes land in: the box's own, else alpha 0 sinks; the name may hold a secret
-- and goes to SetText only, and the target box has no timer region).
--
-- UNVERIFIED IN GAME (needs an eyeball): the reveal (a clip frame whose TOP rides a vertical StatusBar's
-- fill texture, and that fill texture having a rect at value 0), the strip's tile phase and scale on a
-- vertical bar (the degrade path), vertical SetTimerDuration, SetAlphaFromBoolean on frames, the pulse,
-- the chamfer (the baked cut is 6, the mockup 8 image px), the rectangular padlock shackle (the
-- mockup's is an arc).

local _, FS = ...

local Gunsight = FS.Gunsight
if type(Gunsight) ~= "table" or type(Gunsight.OnReady) ~= "function" then return end

local GunsightTape = {}
FS.GunsightTape = GunsightTape

local G = Gunsight.G
local ui = Gunsight.ui
local NAME = "ForeverSTUwaveGunsightTape_"

-------------------------------------------------------------------------------
-- Constants (mockup name in the comment; gunsighttape-harness.py re-reads every one from the HTML)
-------------------------------------------------------------------------------

local N = 20                                          -- N: chevrons per tape
local C = {
    N = N,
    PITCH = (G.BOT - G.TOP) / N,                      -- PITCH = (BOT - TOP) / N
    HW = 10,                                          -- hw: half the chevron width, BOTH tapes (your approved look)
    CHEV_D = 8, CHEV_T = 5.5,                         -- d, tk: chevron depth (box d + tk deep)
    TICKS = 10, TICK_DIV = 10, TICK_MID = 5,          -- k = 0 .. 10 at BOT - k * (BOT - TOP) / 10
    TICK_MID_LEN = 10, TICK_LEN = 5, TICK_A = 0.7,    -- k === 5 ? 10 : 5, alpha .7
    LW = 1,                                           -- LW: a line, one image px
    FRAME_CHAMFER = 8,                                -- chamfer(x0, FR_T, ..., 8) (the baked cut is 6)
    FRAME_FILL = { 13 / 255, 6 / 255, 32 / 255, 0.55 * 0.3 },  -- rgba(13,6,32,.55) under A(.3)
    EDGE_A0 = 0.55, EDGE_A1 = 0.45,                   -- edge = .55 + .45 * pulse
    DIM = 0.2,                                        -- unlit chevrons, A(.2)
    PULSE_HZ = 7 / (2 * math.pi),                     -- pulse = .5 + .5 * sin(clock * 7)
    KICK_W = 36, KICK_H = 15, KICK_CHAMFER = 5,       -- kickTag: w, h, chamfer
    KICK_TEXT_Y = 11, KICK_TEXT_SIZE = 11,            -- text('KICK', x + w / 2, y + 11, 11)
    KICK_DX = 40, KICK_DY = 8,                        -- kx = BOXR.x + BOXR.w - 40, ky = BOXR.y - 8
    KICK_FILL_A = 0.95,                               -- rgba(13,6,32,.95)
    LOCK_DX = 11, LOCK_DY = 0.5, LOCK_W = 14, LOCK_H = 16,  -- padlock(kx + 11, ky - .5), 14 x 16
    LOCK_BODY = { 1, 7, 12, 9 },                      -- fillRect(x + 1, y + 7, 12, 9)
    LOCK_HOLE = { 6, 10, 2, 3.5 },                    -- fillRect(x + 6, y + 10, 2, 3.5) in --bg
    LOCK_SHACKLE = { x0 = 3.5, x1 = 10.5, y0 = 0.5, y1 = 7 },  -- arc centre (7, 4) r 3.5, legs down to y + 7
    LOCK_LINE = 1.1,                                  -- lineWidth = LW * 1.1
}
GunsightTape.C = C

local BG = { 13 / 255, 6 / 255, 32 / 255, 1 }          -- --bg #0d0620
local colors = {
    cyan = (FS.Theme and FS.Theme.COLOR_POWER) or { 0.133, 0.878, 1, 1 },    -- --cyan #22e0ff
    pink = (FS.Theme and FS.Theme.COLOR_HEALTH) or { 1, 0.18, 0.592, 1 },    -- --pink #ff2e97
    steel = (FS.Theme and FS.Theme.COLOR_STEEL) or { 0.5529, 0.5765, 0.651, 1 }, -- --steel #8d93a6
    bg = BG,
}
GunsightTape.colors = colors

local GLOW_BURST_EXPAND = 5
local KICK_FONT_MIN = 6

-------------------------------------------------------------------------------
-- Small helpers
-------------------------------------------------------------------------------

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsighttape_" .. key, "|cffff4488Forever STUwave|r: gunsight tape: " .. tostring(msg))
    end
end

local function HasMethod(obj, name)
    return obj ~= nil and type(obj[name]) == "function"
end

-- A mockup line width as UI units: whole physical pixels, at least one, when `px` is known.
local function Thick(lw, px)
    local t = ui(lw)
    if not px or px <= 0 then return t end
    local n = math.floor(t / px + 0.5)
    if n < 1 then n = 1 end
    return n * px
end

-- The engine's own rounding of a length to whole pixels (at least one).
local function RoundPx(v, px)
    local n = math.floor(v / px + 0.5 + 1e-6)
    if n < 1 then n = 1 end
    return n
end

local function Crisp(tex)
    if tex.SetSnapToPixelGrid then pcall(tex.SetSnapToPixelGrid, tex, true) end
    if tex.SetTexelSnappingBias then pcall(tex.SetTexelSnappingBias, tex, 0) end
end

local function SolidTexture(parent, color, alpha, layer)
    local tex = parent:CreateTexture(nil, layer or "ARTWORK")
    tex:SetColorTexture(color[1], color[2], color[3], alpha or color[4] or 1)
    Crisp(tex)
    return tex
end

local function FillParent(frame, parent)
    frame:SetPoint("TOPLEFT", parent, "TOPLEFT", 0, 0)
    frame:SetPoint("BOTTOMRIGHT", parent, "BOTTOMRIGHT", 0, 0)
end

-------------------------------------------------------------------------------
-- Pieces of a tape
-------------------------------------------------------------------------------

-- A dedicated nine-sliced halo (ADD). The engine's lock-in burst and hold glow must be separate regions.
local function BuildGlow(parent, color)
    local Theme = FS.Theme
    local pad = Theme.SLICE_GLOW_PAD
    local glow = Theme.AddSliceTexture(parent, Theme.SLICE_GLOW_TEXTURE, color, "BACKGROUND", -1, -pad)
    Theme.ApplyNineSlice(glow, Theme.SLICE_GLOW_MARGIN)
    glow:SetBlendMode("ADD")
    return glow
end

-- One edge layer: a frame over the anchor holding the stroke (inside a pulse host: that is where the
-- pulse and the stroke alpha live, so the layer frame's own alpha stays free for SetAlphaFromBoolean)
-- and the 11 outer edge ticks. Returns { frame, stroke, ticks, edgeHost }.
local function BuildLayer(parent, color)
    local Theme = FS.Theme
    local layer = CreateFrame("Frame", nil, parent)
    FillParent(layer, parent)
    local edgeHost = CreateFrame("Frame", nil, layer)
    FillParent(edgeHost, layer)
    edgeHost:SetAlpha(C.EDGE_A0)
    local stroke = Theme.AddCut2Texture(edgeHost, Theme.SLICE_CUT2_OUTLINE_TEXTURE, color, "BORDER")
    local ticks = {}
    for i = 1, C.TICKS + 1 do
        ticks[i] = SolidTexture(layer, color, C.TICK_A)
    end
    return { frame = layer, stroke = stroke, ticks = ticks, edgeHost = edgeHost }
end

-- The pulse: .55 to 1 and back at the mockup's rate, an Alpha animation on the stroke's host. nil when
-- the client has no looping animation (the stroke then rests at the mean).
local function BuildPulse(edgeHost)
    if not (HasMethod(edgeHost, "CreateAnimationGroup")) then return nil end
    local group = edgeHost:CreateAnimationGroup()
    if not HasMethod(group, "SetLooping") then return nil end
    local half = 0.5 / C.PULSE_HZ
    local a = group:CreateAnimation("Alpha")
    a:SetOrder(1)
    a:SetDuration(half)
    a:SetFromAlpha(1)
    a:SetToAlpha(C.EDGE_A0)
    local b = group:CreateAnimation("Alpha")
    b:SetOrder(2)
    b:SetDuration(half)
    b:SetFromAlpha(C.EDGE_A0)
    b:SetToAlpha(1)
    for _, anim in ipairs({ a, b }) do
        if anim.SetSmoothing then anim:SetSmoothing("IN_OUT") end
    end
    group:SetLooping("REPEAT")
    edgeHost:SetAlpha(C.EDGE_A0 + C.EDGE_A1 * 0.5)
    return group
end

-- A strip bar over the run, in `color`. With `tile` (the plain look: the fill is the visible tile) it
-- also carries its own dim copy of the tile; without it (the chevron reveal draws the picture and the
-- dim row, see BuildReveal) the strip is only the engine clock. nil when the engine cannot build one
-- (the run reports why).
local function BuildStrip(run, parent, color, tile)
    local strip = run:CreateStrip(parent)
    if not strip then return nil end
    strip:SetPoint("TOPLEFT", run.frame, "TOPLEFT", 0, 0)
    strip:SetPoint("BOTTOMRIGHT", run.frame, "BOTTOMRIGHT", 0, 0)
    strip:SetStatusBarColor(color[1], color[2], color[3], 1)
    if tile then
        local dim = strip:CreateTexture(nil, "BACKGROUND")
        dim:SetTexture(run.textures.strip)
        if HasMethod(dim, "SetVertTile") then dim:SetVertTile(true) end
        dim:SetAllPoints(strip)
        dim:SetVertexColor(color[1], color[2], color[3], C.DIM)
    end
    return strip
end

-- THE CHEVRON REVEAL (target tape). The target's cast times are secret, so the engine run cannot light
-- its chevrons; the strip StatusBar (SetTimerDuration) is the clock instead. Its own fill draws nothing
-- (texture alpha 0, the bar stays shown so it keeps updating); a clipped frame is anchored from the
-- strip's bottom up to the strip FILL's top edge (pure anchor geometry, nothing secret is read, the same
-- idea as FrameHelpers.CreateCaret riding a fill edge) and shows a full column of the run's own lit
-- chevron art, seated at the run's segment rects (SeatReveal), so the target fills with the same
-- chevrons as yours. One reveal per strip colour: the frame carries the tone alpha (SetAlphaFromBoolean),
-- a dim chevron row sits under the clip, and the outline caret sits ON TOP of the clip's top edge (its
-- bottom on that edge). The raised caret cannot live under the fill's clip (the clip would cut it away),
-- so it has its own clipping frame, a child of the reveal frame spanning the run vertically and widened
-- across by the caret width on each side, the way the engine clips its own caret (ChevronCastBar.lua
-- layoutVertical). That keeps the caret inside the run at the end of a cast.
--   { frame, clip, host, caretClip, caretHost, strip, fill, color, lit = {}, dim = {}, caret }
-- nil when the strip has no fill texture to ride (BuildTape then degrades like a missing
-- SetClipsChildren). The caller zeroes the fill's alpha once every reveal built, so a half built pair
-- never leaves one strip invisible.
local function BuildReveal(run, parent, strip, color)
    local fill = strip:GetStatusBarTexture()
    if not fill then return nil end
    local art = run.textures
    local rv = CreateFrame("Frame", nil, parent)
    FillParent(rv, run.frame)
    rv:Hide()
    local clip = CreateFrame("Frame", nil, rv)
    clip:SetClipsChildren(true)
    -- SetClipsChildren clips child frames, so the chevrons and the caret sit on a child of the clip.
    local host = CreateFrame("Frame", nil, clip)
    FillParent(host, rv)
    local reveal = { frame = rv, clip = clip, host = host, strip = strip, color = color, lit = {}, dim = {} }
    for i = 1, N do
        local dim = rv:CreateTexture(nil, "BACKGROUND")
        dim:SetTexture(art.fill)
        dim:SetVertexColor(color[1], color[2], color[3], C.DIM)
        local lit = host:CreateTexture(nil, "ARTWORK")
        lit:SetTexture(art.lit or art.fill)
        lit:SetVertexColor(color[1], color[2], color[3], 1)
        reveal.dim[i], reveal.lit[i] = dim, lit
    end
    -- The caret has its own clip (a child of the reveal frame, so it hides with it and takes its tone
    -- alpha). SetClipsChildren clips child frames, not the clipping frame's own regions, so the caret
    -- texture sits on a child frame of that clip (see the CARET CLIP note in ChevronCastBar.lua). It is
    -- seated in SeatReveal, which creates nothing.
    local caretClip = CreateFrame("Frame", nil, rv)
    caretClip:SetClipsChildren(true)
    local caretHost = CreateFrame("Frame", nil, caretClip)
    FillParent(caretHost, caretClip)
    local caret = caretHost:CreateTexture(nil, "OVERLAY")
    caret:SetTexture(art.outline)
    caret:SetVertexColor(color[1], color[2], color[3], 1)
    reveal.caretClip, reveal.caretHost, reveal.caret = caretClip, caretHost, caret
    reveal.fill = fill
    return reveal
end

-- The bar's `strip` as the state machine sees it: one object over every real strip. SetTimerDuration is
-- there only when every strip has it (the state machine feature-detects it). With no strips every call
-- is a no-op and there is no SetTimerDuration.
local function StripProxy(strips, reveals)
    local proxy = {}
    reveals = reveals or {}
    function proxy.Show()
        for _, s in ipairs(strips) do s:Show() end
        for _, r in ipairs(reveals) do r.frame:Show() end
    end
    function proxy.Hide()
        for _, s in ipairs(strips) do s:Hide() end
        for _, r in ipairs(reveals) do r.frame:Hide() end
    end
    function proxy.SetMinMaxValues(_, lo, hi) for _, s in ipairs(strips) do s:SetMinMaxValues(lo, hi) end end
    function proxy.SetValue(_, v) for _, s in ipairs(strips) do s:SetValue(v) end end
    local timed = #strips > 0
    for _, s in ipairs(strips) do
        if not HasMethod(s, "SetTimerDuration") then timed = false end
    end
    if timed then
        function proxy.SetTimerDuration(_, d) for _, s in ipairs(strips) do s:SetTimerDuration(d) end end
    end
    return proxy
end

-- The shield stand-in of the target tape. `SetAlpha` (any value) is the neutral look, steel up and pink
-- down: the state machine calls it between casts and for a flag it cannot read. SetAlphaFromBoolean
-- (flag, 1, 0) is "flag true = not interruptible = steel": steel regions get it as is, pink regions the
-- inverse. The method exists only when every region has it, so the state machine's own feature
-- detection reads it right.
local function BuildShield(fb)
    local shield = {}
    local function neutral()
        for _, r in ipairs(fb.steel) do r:SetAlpha(1) end
        for _, r in ipairs(fb.pink) do r:SetAlpha(0) end
    end
    function shield.SetAlpha() neutral() end
    local canBool = true
    for _, list in pairs(fb) do
        for _, r in ipairs(list) do
            if not HasMethod(r, "SetAlphaFromBoolean") then canBool = false end
        end
    end
    if canBool then
        function shield.SetAlphaFromBoolean(_, flag, whenTrue, whenFalse)
            for _, r in ipairs(fb.steel) do r:SetAlphaFromBoolean(flag, whenTrue, whenFalse) end
            for _, r in ipairs(fb.pink) do r:SetAlphaFromBoolean(flag, whenFalse, whenTrue) end
        end
    end
    neutral()
    return shield, canBool
end

-- The padlock (14 x 16): body, keyhole and a rectangular shackle, in steel. Children seat from the
-- frame's top left in image px (LayoutPadlock).
local function BuildPadlock(parent)
    local lock = CreateFrame("Frame", nil, parent)
    lock.body = SolidTexture(lock, colors.steel, 1)
    lock.hole = SolidTexture(lock, BG, 1, "OVERLAY")
    lock.legL = SolidTexture(lock, colors.steel, 1)
    lock.legR = SolidTexture(lock, colors.steel, 1)
    lock.bar = SolidTexture(lock, colors.steel, 1)
    return lock
end

local function SeatRect(tex, parent, x, y, w, h)
    tex:ClearAllPoints()
    tex:SetPoint("TOPLEFT", parent, "TOPLEFT", x, -y)
    tex:SetSize(w, h)
end

local function LayoutPadlock(lock, px)
    local k = ui(1)
    lock:SetSize(C.LOCK_W * k, C.LOCK_H * k)
    local b, h, s = C.LOCK_BODY, C.LOCK_HOLE, C.LOCK_SHACKLE
    SeatRect(lock.body, lock, b[1] * k, b[2] * k, b[3] * k, b[4] * k)
    SeatRect(lock.hole, lock, h[1] * k, h[2] * k, h[3] * k, h[4] * k)
    local w = Thick(C.LOCK_LINE * C.LW, px)
    local legH = (s.y1 - s.y0) * k + w / 2
    SeatRect(lock.legL, lock, s.x0 * k - w / 2, s.y0 * k - w / 2, w, legH)
    SeatRect(lock.legR, lock, s.x1 * k - w / 2, s.y0 * k - w / 2, w, legH)
    SeatRect(lock.bar, lock, s.x0 * k - w / 2, s.y0 * k - w / 2, (s.x1 - s.x0) * k + w, w)
end

-- The KICK tag: a chamfered plate, a pink stroke and the word.
local function BuildKick(parent)
    local Theme = FS.Theme
    local kick = CreateFrame("Frame", nil, parent)
    local fill = { BG[1], BG[2], BG[3], C.KICK_FILL_A }
    Theme.AddCut2Texture(kick, Theme.SLICE_CUT2_FILL_TEXTURE, fill, "BACKGROUND", 0)
    Theme.AddCut2Texture(kick, Theme.SLICE_CUT2_OUTLINE_TEXTURE, colors.pink, "BORDER")
    local label = kick:CreateFontString(nil, "OVERLAY")
    -- A font first: SetText on a FontString with none throws "Font not set" (LayoutKick sets the real size).
    Theme.ApplyMono(label, KICK_FONT_MIN, colors.pink)
    label:SetPoint("CENTER", kick, "CENTER", 0, 0)
    label:SetText("KICK")
    kick.label = label
    return kick
end

-- How far the target's info box now grows above its anchor (mockup option B: `ky += BR.y - BOXR.y`, the tag
-- rides the grown box's top right corner). It is the built box's own `grow`: a box that failed to build
-- (the hidden-sink fallback) has none, and the tag then stays at the anchor.
local function BoxGrow(t)
    local box = t.box
    local grow = type(box) == "table" and box.grow
    if type(grow) == "number" then return grow end
    return 0
end

local function LayoutKick(t, anchor)
    local kick, lock = t.kick, t.padlock
    local k = ui(1)
    kick:ClearAllPoints()
    kick:SetPoint("TOPLEFT", anchor, "TOPRIGHT", -C.KICK_DX * k, (C.KICK_DY + BoxGrow(t)) * k)
    kick:SetSize(C.KICK_W * k, C.KICK_H * k)
    local size = math.max(KICK_FONT_MIN, math.floor(ui(C.KICK_TEXT_SIZE) + 0.5))
    FS.Theme.ApplyMono(kick.label, size, colors.pink)
    lock:ClearAllPoints()
    lock:SetPoint("TOPLEFT", kick, "TOPLEFT", C.LOCK_DX * k, C.LOCK_DY * k)
end

-------------------------------------------------------------------------------
-- Layout (build and every rescale: re-seats and resizes, creates nothing)
-------------------------------------------------------------------------------

local function LayoutTicks(t, px)
    local k = ui(1)
    local thick = Thick(C.LW, px)
    local B = G
    local left = t.key == "you"
    for layerKey, list in pairs(t.ticks) do
        local layer = t.layers[layerKey]
        for i, tex in ipairs(list) do
            local step = i - 1
            local len = step == C.TICK_MID and C.TICK_MID_LEN or C.TICK_LEN
            local ty = B.BOT - step * (B.BOT - B.TOP) / C.TICK_DIV
            tex:ClearAllPoints()
            if left then
                tex:SetPoint("RIGHT", layer, "TOPLEFT", 0, -(ty - B.FR_T) * k)
            else
                tex:SetPoint("LEFT", layer, "TOPRIGHT", 0, -(ty - B.FR_T) * k)
            end
            tex:SetSize(len * k, thick)
        end
    end
end

-- Seats and sizes the run: the chevron box and pitch from the mockup, a length of whole physical pixels
-- (so it holds exactly N chevrons), seated TOP to TOP below the frame top. The first Layout, a pixel
-- long, only learns the pixel size the engine will use.
local function LayoutRun(t)
    local run = t.run
    run.frame:ClearAllPoints()
    run.frame:SetPoint("TOP", t.anchor, "TOP", 0, -ui(G.TOP - G.FR_T))
    run.chevW, run.chevH, run.pitchOpt = ui(2 * t.hw), ui(C.CHEV_D + C.CHEV_T), ui(C.PITCH)
    run:Layout(run.chevW, ui(1))
    local px = run.px
    if type(px) ~= "number" or px <= 0 then return nil end
    local wPx = RoundPx(run.chevW, px)
    local hPx = RoundPx(run.chevH, px)
    local pitchPx = RoundPx(run.pitchOpt, px)
    run:Layout((wPx + 0.25) * px, ((N - 1) * pitchPx + hPx + 0.25) * px)
    return px
end

-- Seats one chevron texture (dim or lit) at the run's segment rect: whole pixel pitch and origin.
local function SeatChevron(tex, frame, run, seg)
    if seg then
        tex:ClearAllPoints()
        tex:SetPoint("BOTTOMLEFT", frame, "BOTTOMLEFT", run.xOff, seg.x0)
        tex:SetSize(run.segW, run.segLen)
    end
    tex:SetShown(seg ~= nil)
end

-- Seats the target's reveal from the run's own layout (plain numbers the engine just computed): the
-- strips span exactly the chevron run (origin to origin + span, so the top chevron is reached at the end
-- of the cast; no tile scale, the tile is not drawn), each clip runs from its strip's bottom to its fill
-- top (the TOP anchor is static, and the bottom corners are widened across by the caret width like the
-- engine's own clip), the caret sits on top of that fill edge (its bottom on the edge, so it is raised by
-- its own height) under a clip spanning the run vertically, and every lit and dim chevron takes the very
-- seat of the run's segment (whole pixel pitch and origin). Creates nothing: called from the run's
-- onLayout (every relayout, the engine's own rescale watcher included) and from LayoutTape.
local function SeatReveal(t)
    local run = t.run
    local origin, span = run.origin, run.span
    if type(origin) ~= "number" or type(span) ~= "number" then return end
    for _, strip in ipairs(t.strips) do
        strip:ClearAllPoints()
        strip:SetPoint("BOTTOMLEFT", run.frame, "BOTTOMLEFT", 0, origin)
        strip:SetPoint("TOPRIGHT", run.frame, "BOTTOMRIGHT", 0, origin + span)
    end
    local m = run.capW or 0
    for _, rv in ipairs(t.reveals) do
        rv.clip:ClearAllPoints()
        rv.clip:SetPoint("BOTTOMLEFT", rv.strip, "BOTTOMLEFT", -m, 0)
        rv.clip:SetPoint("BOTTOMRIGHT", rv.strip, "BOTTOMRIGHT", m, 0)
        rv.clip:SetPoint("TOP", rv.fill, "TOP", 0, 0)
        for i = 1, #rv.lit do
            local seg = i <= run.count and run.segs[i] or nil
            SeatChevron(rv.dim[i], rv.frame, run, seg)
            SeatChevron(rv.lit[i], rv.frame, run, seg)
        end
        if run.capW and run.capH then
            -- Same widened span as the fill's clip, but the full run height, so the raised caret is
            -- trimmed at the run's top instead of poking onto the plate and ticks.
            rv.caretClip:ClearAllPoints()
            rv.caretClip:SetPoint("TOPLEFT", run.frame, "TOPLEFT", -m, 0)
            rv.caretClip:SetPoint("BOTTOMRIGHT", run.frame, "BOTTOMRIGHT", m, 0)
            -- capX already includes the widening m, and the fill clip's left edge is widened by the same m.
            rv.caret:ClearAllPoints()
            rv.caret:SetPoint("BOTTOMLEFT", rv.clip, "TOPLEFT", run.capX, 0)
            rv.caret:SetSize(run.capW, run.capH)
        end
    end
end

local function LayoutTape(t)
    local px = LayoutRun(t)
    LayoutTicks(t, px)
    if t.kick and t.padlock then
        LayoutKick(t, Gunsight.anchors.boxR)
        LayoutPadlock(t.padlock, px)
    end
    if t.reveals then
        SeatReveal(t)
    else
        for _, strip in ipairs(t.strips) do t.run:ApplyStripScale(strip) end
    end
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local built = {}      -- every tape frame built so far, hidden again if a later step fails
local builtBoxes = {} -- every info box built so far, retired again if a later step fails
local gateEvents      -- the target layer's listener, taken down again if a later build step fails

-- The gate follows FS.HasTarget (Theme.lua: a secret or missing UnitExists reads as "has one"). A rescale that
-- lands while the tape is not VISIBLE (IsVisible counts the gate and every ancestor: the gate hidden, or the tgt
-- piece frame off or fading) marks the tape dirty (see the rescale callback in Build), because the client has no
-- rect for such a frame and the chevron pixel snap cannot run. A dirty tape is laid out again by the first
-- moment it is actually visible (the gate shows, or the tgt piece shows) and only that clears the mark.
local function RelayoutIfDirty(t)
    if t and t.dirty and t.gate and t.gate:IsVisible() then
        t.dirty = nil
        LayoutTape(t)
    end
end

local function RefreshGate(t)
    if not (t and t.gate) then return end
    t.gate:SetShown(FS.HasTarget())
    RelayoutIfDirty(t)
end

-- The bar table's icon / name / timer / tick members. With GunsightBoxes.lua they come from the info
-- box built on the tape's box anchor (t.box; its colour frames join the tape's pink / steel lists, so the
-- one flag that tints the tape tints the box); a failed or missing box leaves the alpha 0 sinks the
-- tape always had (logged once, never an error). t.icon, t.timer, t.name and t.tabTicks stay the real
-- Texture / FontStrings the writes land in.
local function BuildSinks(t, host)
    local textHost = CreateFrame("Frame", nil, host)
    FillParent(textHost, host)
    textHost:SetAlpha(0)
    t.icon = textHost:CreateTexture(nil, "ARTWORK")
    t.icon:SetSize(1, 1)
    t.timer = textHost:CreateFontString(nil, "OVERLAY")
    t.name = textHost:CreateFontString(nil, "OVERLAY")
    t.tabTicks = textHost:CreateFontString(nil, "OVERLAY")
    for _, fs in ipairs({ t.timer, t.name, t.tabTicks }) do
        FS.Theme.ApplyMono(fs, 11, colors.cyan)
        fs:SetText("")
    end
    return { icon = t.icon, timer = t.timer, tabName = t.name, tabTicks = t.tabTicks }
end

local function BuildMembers(t, piece, host)
    local Boxes = FS.GunsightBoxes
    if type(Boxes) ~= "table" or type(Boxes.Build) ~= "function" then
        LogOnce("noboxes", "GunsightBoxes.lua is missing; the info boxes are not drawn.")
        return BuildSinks(t, host)
    end
    local anchors = Gunsight.anchors
    local ok, box, err = pcall(Boxes.Build, {
        key = t.key, parent = piece, anchor = t.isTarget and anchors.boxR or anchors.boxL, isTarget = t.isTarget,
    })
    if not ok then box, err = nil, box end
    if not box then
        LogOnce("box_" .. t.key, "the info box failed to build, using hidden sinks: " .. tostring(err))
        return BuildSinks(t, host)
    end
    t.box = box
    builtBoxes[#builtBoxes + 1] = box
    t.icon, t.timer, t.name, t.tabTicks = box.regions.icon, box.regions.timer, box.regions.name, box.regions.ticks
    for _, side in ipairs({ "pink", "steel" }) do
        for _, region in ipairs(box.fb[side]) do t.fb[side][#t.fb[side] + 1] = region end
    end
    return box.members
end

local function BuildTape(key, anchor, isTarget)
    local Theme = FS.Theme
    local t = {
        key = key, anchor = anchor, hw = C.HW, isTarget = isTarget,
        layers = {}, ticks = {}, strips = {}, fb = { pink = {}, steel = {} },
    }

    local piece = CreateFrame("Frame", NAME .. key, Gunsight.root)
    FillParent(piece, anchor)
    built[#built + 1] = piece
    t.piece = piece

    -- Everything the tape draws hangs off `body`: the piece frame itself, or (the target's) the gate under it,
    -- the visibility layer the player's target drives. The info box stays a child of the piece (it has its own rule).
    local body = piece
    if isTarget then
        local gate = CreateFrame("Frame", nil, piece)
        FillParent(gate, piece)
        if HasMethod(gate, "SetFrameLevel") and HasMethod(piece, "GetFrameLevel") then
            gate:SetFrameLevel(piece:GetFrameLevel())      -- the same stacking its children had on the piece
        end
        t.gate = gate
        body = gate
    end

    -- Plate and edge layers.
    Theme.AddCut2Texture(body, Theme.SLICE_CUT2_FILL_TEXTURE, C.FRAME_FILL, "BACKGROUND", 0)
    local flareStroke
    if isTarget then
        local pink = BuildLayer(body, colors.pink)
        local steel = BuildLayer(body, colors.steel)
        t.layers.pink, t.layers.steel = pink.frame, steel.frame
        t.ticks.pink, t.ticks.steel = pink.ticks, steel.ticks
        t.pulse = BuildPulse(pink.edgeHost)
        t.fb.pink[#t.fb.pink + 1] = pink.frame
        t.fb.steel[#t.fb.steel + 1] = steel.frame
    else
        local cyan = BuildLayer(body, colors.cyan)
        t.layers.base, t.ticks.base = cyan.frame, cyan.ticks
        flareStroke = cyan.stroke
    end

    -- The cast host and the engine run.
    local host = CreateFrame("Frame", nil, body)
    FillParent(host, body)
    t.host = host
    local tint = isTarget and colors.steel or colors.cyan
    local run = FS.ChevronCastBar.Create(host, {
        vertical = true,
        textures = FS.ChevronCastBar.TEXTURES_UP,
        chevronWidth = ui(2 * C.HW),
        chevronHeight = ui(C.CHEV_D + C.CHEV_T),
        pitch = ui(C.PITCH),
        colors = { base = tint, flareBase = tint },
        flareTarget = flareStroke,
        glowBurst = BuildGlow(host, tint),
        glowBurstExpand = GLOW_BURST_EXPAND,
        holdGlow = BuildGlow(host, tint),
    })
    t.run = run

    -- Strips (the engine-timed secret path), or a logged degrade without vertical support.
    -- The target's strip path needs BOTH strips (pink and steel, one alpha-managed against the other):
    -- a lone one would stay pink whatever the interruptible flag says, so a partial build is hidden and
    -- treated as no strip support at all.
    local supported = FS.ChevronCastBar.SupportsVerticalStrip()
    -- The target shows the real chevrons over its engine clock (BuildReveal) when frames can clip; without
    -- SetClipsChildren it keeps the plain strip tile (logged once below).
    local canReveal = isTarget and HasMethod(host, "SetClipsChildren")
    if supported then
        local colorsFor = isTarget and { colors.pink, colors.steel } or { colors.cyan }
        for _, color in ipairs(colorsFor) do
            local strip = BuildStrip(run, host, color, not canReveal)
            if not strip then break end
            t.strips[#t.strips + 1] = strip
        end
        if #t.strips < #colorsFor then
            for _, strip in ipairs(t.strips) do strip:Hide() end
            t.strips = {}
        end
    end
    if #t.strips == 0 then
        LogOnce("nostrip", "no vertical StatusBar support here; a secret target cast shows no fill on the tapes.")
    elseif isTarget then
        t.fb.pink[#t.fb.pink + 1] = t.strips[1]
        t.fb.steel[#t.fb.steel + 1] = t.strips[2]
        local pinkReveal, steelReveal
        if canReveal then
            pinkReveal = BuildReveal(run, host, t.strips[1], colors.pink)
            steelReveal = pinkReveal and BuildReveal(run, host, t.strips[2], colors.steel)
        end
        if pinkReveal and steelReveal then
            t.reveals = { pinkReveal, steelReveal }
            for _, rv in ipairs(t.reveals) do rv.fill:SetAlpha(0) end
            t.fb.pink[#t.fb.pink + 1] = pinkReveal.frame
            t.fb.steel[#t.fb.steel + 1] = steelReveal.frame
        else
            LogOnce("noclip", "Frame:SetClipsChildren or the strip fill texture is missing; the target tape "
                .. "fills with the plain strip tile, not the chevron reveal.")
        end
    end
    run.onLayout = function()
        if t.reveals then
            SeatReveal(t)
        else
            for _, strip in ipairs(t.strips) do run:ApplyStripScale(strip) end
        end
    end

    -- The members CastBars writes the icon, name, timer and tick counter to, and the cast-only frame.
    -- They are the info box's own (GunsightBoxes.lua, seated on boxL / boxR, children of the piece so
    -- the piece toggles fade it); without the box they are alpha 0 sinks, so the state machine always
    -- has somewhere to write and the tape never depends on the box.
    local members = BuildMembers(t, piece, host)

    local castFrame = CreateFrame("Frame", nil, host)
    castFrame:Hide()
    t.castFrame = castFrame
    local shield, canBool
    if isTarget then
        t.kick = BuildKick(castFrame)
        t.padlock = BuildPadlock(castFrame)
        t.fb.pink[#t.fb.pink + 1] = t.kick
        t.fb.steel[#t.fb.steel + 1] = t.padlock
        shield, canBool = BuildShield(t.fb)
        if not canBool then
            LogOnce("nobool", "SetAlphaFromBoolean is missing; the target tape stays steel and shows no KICK tag.")
            t.kick:Hide()
            t.padlock:Hide()
        end
    else
        shield = { SetAlpha = function() end }
    end

    local pulse = t.pulse
    local tab = {}
    function tab.Show()
        castFrame:Show()
        if pulse then pulse:Play() end
    end
    function tab.Hide()
        castFrame:Hide()
        if pulse then pulse:Stop() end
    end
    function tab.SetWidth() end

    t.S = {
        frame = host, run = run, strip = StripProxy(t.strips, t.reveals), icon = members.icon, shield = shield,
        timer = members.timer, tab = tab, tabName = members.tabName, tabTicks = members.tabTicks,
        alwaysIdle = true, idleDim = C.DIM,
        stripOnly = (isTarget and #t.strips > 0) or nil,
        -- CastBars calls this (pcall'd) on an interrupt; the info box's red look. nil on the sink fallback.
        onVerdict = members.onVerdict,
    }

    LayoutTape(t)
    return t
end

-- A build that fails part way hides what it built and retires the boxes: a box keeps a Layout.OnRescale
-- callback and (the target's) a unit-name listener that nothing else would ever take down.
local function HideBuilt()
    for _, frame in ipairs(built) do frame:Hide() end
    if gateEvents then pcall(gateEvents.UnregisterAllEvents, gateEvents) end
    for _, box in ipairs(builtBoxes) do
        pcall(function() FS.GunsightBoxes.Retire(box) end)   -- the lookup is inside the pcall too
    end
end

local function Build()
    if not Gunsight.IsEnabled() then return end
    local you = BuildTape("you", Gunsight.anchors.tapeL, false)
    local tgt = BuildTape("tgt", Gunsight.anchors.tapeR, true)
    GunsightTape.you, GunsightTape.tgt = you, tgt
    Gunsight.RegisterPiece("you", { frame = you.piece })
    Gunsight.RegisterPiece("tgt", { frame = tgt.piece, onShow = function() RelayoutIfDirty(tgt) end })

    -- The state machine: CastBars drives these two bar tables instead of Stack A.
    local castBars = FS.CastBars
    if type(castBars) == "table" and type(castBars.SetView) == "function" then
        if not castBars.SetView({ player = you.S, target = tgt.S }) then
            LogOnce("viewrefused", "FS.CastBars.SetView refused the view; Stack A keeps drawing the casts.")
        end
    else
        LogOnce("noview", "FS.CastBars.SetView is missing; Stack A keeps drawing the casts.")
    end
    -- The dim idle paint only where no cast is live: the seam already re-read both units, and ShowIdle
    -- on a run it just started would end it while the state machine still says "run".
    for _, t in ipairs({ you, tgt }) do
        if t.S.mode == nil then t.run:ShowIdle(C.DIM) end
    end

    -- The target layer: read once now, then on every target change (and on entering the world).
    RefreshGate(tgt)
    gateEvents = CreateFrame("Frame", nil, tgt.piece)
    built[#built + 1] = gateEvents
    gateEvents:RegisterEvent("PLAYER_TARGET_CHANGED")
    gateEvents:RegisterEvent("PLAYER_ENTERING_WORLD")
    gateEvents:SetScript("OnEvent", function() RefreshGate(tgt) end)

    if FS.Layout and FS.Layout.OnRescale then
        FS.Layout.OnRescale(function()
            LayoutTape(you)
            LayoutTape(tgt)
            -- Not visible: no rect, so the snap above did nothing and a re-layout is owed.
            -- Visible: it just ran, nothing is owed.
            if tgt.gate then tgt.dirty = (not tgt.gate:IsVisible()) or nil end
        end)
    end
end

Gunsight.OnReady(function()
    local ok, err = pcall(Build)
    if not ok then
        HideBuilt()
        GunsightTape.you, GunsightTape.tgt = nil, nil
        LogOnce("build", "build failed: " .. tostring(err))
    end
end)
