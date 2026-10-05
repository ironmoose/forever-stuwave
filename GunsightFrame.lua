-- Forever Synthwave: Gunsight HUD frame work (horizon, proc rungs).
--
-- Two pieces of the locked design (mockups/gunsight-hud-v2-2026-10-02/gunsight-hud-v2-2026-10-02.html)
-- built on the Gunsight core (Gunsight.lua owns the geometry and the piece registry). Every line is
-- a texture seated by mockup image coordinates through FS.Gunsight.G and FS.Gunsight.ui; nothing
-- here re-derives a number the core already has, and every number the file adds is in the constants
-- block below with its mockup name in a comment (gunsightframe-harness.py parses each back out of
-- the mockup).
--
-- HORIZON (drawYour / drawTarget / drawDots): hline(630, ...) in three short segments around the
-- character (YOU: tape inner edge to the left post, TGT: right post to the tape, DOT: past the
-- target tape to the DoT axis) plus the break ticks vline(LBRK / RBRK, 623, 637). A segment belongs
-- to the piece that draws it in the mockup: it fades with `you`, `tgt` or `dot`. RegisterPiece takes
-- one frame per key and those keys belong to the lanes that build the tapes, so the segments follow
-- the keys through FS.Gunsight.OnPieceChanged and fade on their own AnimationGroups.
-- TARGET LAYER. With no target the target side of the horizon hides: the `tgt` segment with its right
-- break tick (drawTarget owns both) and the `dot` segment (drawDots). That is a SEPARATE layer from the piece
-- toggle (Gunsight.SetPiece is the user's on/off setting and drives the console key LED, and the fade above
-- owns the part frame's Show / alpha): the segment and tick are children of `part.gate`, a plain child of the part
-- frame at the part frame's own level (so they keep the stacking they had on it, root + 1, clear of the proc rung
-- frames), shown while the part's rule says so and hidden while not. Each gate has its own rule. `tgt` follows
-- FS.HasTarget (Theme.lua, shared with GunsightTape / GunsightBoxes): the target's cast tape needs only a target.
-- `dot` follows FS.TargetTakesDots (Theme.lua, shared with GunsightDots): the segment leads into the DoT scale, so
-- it hides whenever the scale does, for a friendly or otherwise unattackable target and a dead one. A secret or
-- unreadable answer keeps a gate shown in both rules. Both are re-read on PLAYER_TARGET_CHANGED and
-- PLAYER_ENTERING_WORLD (and once at build), and the answer can also change with no target change (death, a duel,
-- mind control), so UNIT_HEALTH, UNIT_FLAGS and UNIT_FACTION are registered for the target unit only. A visible
-- segment needs the piece ON and its rule true. Show / Hide of a plain gate is legal in combat, a gate is written
-- only when its answer changes, the layer adds no OnUpdate, and a rescale re-seats and never calls Show on a gate.
-- The `you` segment and its LBRK tick have no gate (the left side stays).
--
-- PROC RUNGS (drawProc): a post at LBRK / RBRK spanning y 566..694, dashed with end ticks. An
-- inactive rung is HIDDEN (not dimmed): the rung frame shows only while its proc is active (or
-- fading out), at alpha q, and every position stays seated while hidden so a rung appearing moves
-- nothing. Lit, a solid amber post grows from the horizon (half height 16 + q * 54), with a run to
-- the tape's inner edge, 7 long end ticks, an amber glow, the label above the tape (y 494) and a 16
-- image px proc icon to the label's left (grey and amber edge only while the rung fades in or out).
-- The fade is linear: the rung frame alone carries q, so the lit group, label, icon and icon edge
-- are painted at their full (q 1) alpha and never multiply q again. Piece `prc`. Which
-- procs and which side comes from the profile's `procs` entries (`side` "left" or "right", `label`),
-- the lit state from FS.Hud's `state.procs[i].active`. A profile with no procs (priest) draws no
-- rungs at all. The growth is q eased 0 to 1 over ANIM seconds by an OnUpdate that exists ONLY
-- while q is moving (it is cleared the moment q lands), so an idle HUD runs nothing.
--
-- LINES. A mockup line is LW = 1 image px wide. It is drawn as a texture whose thickness is
-- ui(LW) rounded to a whole number of PHYSICAL pixels (never under one), when the client answers
-- what a pixel is (PixelUtil.GetPixelToUIUnitFactor, else 768 / GetPhysicalScreenSize height, both
-- feature detected); with neither it is ui(LW) as is. Dashes are short textures, not CreateLine.
-- GLOW. The mockup's halo is four nested strokes reaching 7 image px; here it is two glow_edge.tga
-- strips along the line (the texture AddOuterGlow uses, without its corner blooms), ADD blended.
--
-- UNVERIFIED in game: the look of the 1 pixel lines and whether the engine snaps them as intended
-- (SetSnapToPixelGrid / SetTexelSnappingBias are feature detected), the glow strength against the
-- mockup's halo, the label baseline offset (LABEL_DESCENT) and the icon plate at its small size.

local _, FS = ...

local Gunsight = FS.Gunsight
if type(Gunsight) ~= "table" then return end -- Gunsight.lua loads first; without it there is no root

local GunsightFrame = {}
FS.GunsightFrame = GunsightFrame

local G = Gunsight.G
local ui = Gunsight.ui

-------------------------------------------------------------------------------
-- Constants (mockup name in the comment; the harness re-reads each from the HTML)
-------------------------------------------------------------------------------

local C = {
    HZ_ALPHA = 0.85,        -- horizon hline alpha
    TICK_Y0 = 623,          -- break tick vline y0
    TICK_Y1 = 637,          -- break tick vline y1
    TICK_ALPHA = 0.9,       -- break tick alpha
    HZ_TGT_PAD = 2,         -- drawTarget: hline(630, RBRK, TR.x0 - 2)
    HZ_DOT_PAD_L = 10,      -- drawDots: hline(630, TR.x1 + 10, ...)
    PROC_Y0 = 566,          -- drawProc idle post top
    PROC_Y1 = 694,          -- drawProc idle post bottom
    DASH = 5,               -- setLineDash([5, 5]): dash
    DASH_GAP = 5,           -- setLineDash([5, 5]): gap
    IDLE_ALPHA = 0.4,       -- idle post, dashes and end ticks
    IDLE_TICK = 6,          -- idle end tick length
    RUN_PAD = 2,            -- the run stops 2 short of the tape's inner edge
    LIT_K = 1.7,            -- lit stroke width, LW * 1.7
    LABEL_Y = 494,          -- label baseline
    LABEL_SIZE = 12.5,      -- label font size
    LABEL_MIX = 0.55,       -- idle label colour: mix(violet, white, .55)
    LABEL_A0 = 0.55,        -- label alpha at q 1 is .55 + .45 (the rung frame carries q)
    LABEL_A1 = 0.45,
    ICON = 16,              -- PI: proc icon size
    ICON_Y = 482,           -- py: proc icon top
    ICON_PAD = 4,           -- gap between the icon and the label
    CHAR_HALF = 3.75,       -- half a monospace character (the mockup never measures the label)
    ICON_A0 = 0.55,         -- icon alpha at q 1 is .55 + .45 (the rung frame carries q)
    ICON_A1 = 0.45,
    EDGE_A0 = 0.35,         -- icon edge alpha at q 1 is .35 + .65 (the rung frame carries q)
    EDGE_A1 = 0.65,
    ICON_MIX = 0.4,         -- idle icon edge: mix(violet, white, .4)
    -- Not in the mockup (it draws q as a plain number):
    ANIM = 0.3,             -- seconds for q to travel 0 to 1 and back
    LABEL_DESCENT = 3,      -- image px from the text baseline down to the bottom of its box
    GLOW_REACH = 7,         -- the mockup halo's reach (HALO tops out at 7 image px)
    GLOW_PEAK = 0.585,      -- the halo's stacked alpha at the stroke edge (.26 + .17 + .10 + .055)
}
GunsightFrame.C = C

local FADE_SECONDS = 0.25   -- same fade the core gives a piece
local DASH_PITCH = C.DASH + C.DASH_GAP
local NAME = "ForeverSynthwaveGunsightFrame_"
local MEDIA = "Interface\\AddOns\\ForeverSynthwave\\media\\"

local FALLBACK_VIOLET = { 0.659, 0.333, 0.969, 1 }
local FALLBACK_AMBER = { 1, 0.7137, 0.2824, 1 }
local WHITE = { 1, 1, 1, 1 }
local PLATE = { 0.051, 0.0235, 0.1255, 0.77 }       -- rgba(13,6,32,.9) under A(.85)

-------------------------------------------------------------------------------
-- State
-------------------------------------------------------------------------------

local Theme, root
local violet, amber = FALLBACK_VIOLET, FALLBACK_AMBER
local built = false
local fades = {}          -- frame -> { group, anim, on }
local byKey = {}          -- piece key -> horizon part
local glows = {}          -- every line glow, resized on Layout
local rungs = {}          -- "left" / "right" -> rung

local horizon = {}
GunsightFrame.horizon, GunsightFrame.rungs = horizon, rungs

local function LogOnce(key, msg)
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightframe_" .. key, "|cffff4488ForeverSynthwave|r: gunsight frame: " .. tostring(msg))
    end
end

local function IsSecret(v)
    return FS.IsSecret ~= nil and FS.IsSecret(v) == true
end

local function Mix(a, b, t)
    return a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t
end

-------------------------------------------------------------------------------
-- Geometry
-------------------------------------------------------------------------------

-- UI units per physical pixel at the root's effective scale, or nil when the client will not say.
local function PixelUnit()
    local factor
    local pixelUtil = _G.PixelUtil
    local physical = _G.GetPhysicalScreenSize
    if type(pixelUtil) == "table" and type(pixelUtil.GetPixelToUIUnitFactor) == "function" then
        local ok, v = pcall(pixelUtil.GetPixelToUIUnitFactor)
        if ok then factor = v end
    elseif type(physical) == "function" then
        local ok, _, h = pcall(physical)
        if ok and type(h) == "number" and not IsSecret(h) and h > 0 then factor = 768 / h end
    end
    if type(factor) ~= "number" or IsSecret(factor) or factor ~= factor or factor <= 0 then return nil end
    local scale = 1
    if root and root.GetEffectiveScale then
        local ok, s = pcall(root.GetEffectiveScale, root)
        if ok and type(s) == "number" and not IsSecret(s) and s > 0 then scale = s end
    end
    return factor / scale
end

-- A mockup line width as UI units: whole physical pixels, at least one, when `px` is known.
local function Thick(lw, px)
    local t = ui(lw)
    if not px then return t end
    local n = math.floor(t / px + 0.5)
    if n < 1 then n = 1 end
    return n * px
end

-- Seats `region` so its `point` sits at mockup image coordinate (ix, iy) relative to the root, plus
-- an optional offset in UI units (Y up). Gunsight.Point's arithmetic with the offset it lacks.
local function Seat(region, point, ix, iy, dx, dy)
    local k = ui(1)
    region:ClearAllPoints()
    region:SetPoint(point, root, "CENTER", (ix - G.CX) * k + (dx or 0), -(iy - G.CY) * k + (dy or 0))
end

-------------------------------------------------------------------------------
-- Drawing primitives
-------------------------------------------------------------------------------

local function Crisp(tex)
    if tex.SetSnapToPixelGrid then pcall(tex.SetSnapToPixelGrid, tex, true) end
    if tex.SetTexelSnappingBias then pcall(tex.SetTexelSnappingBias, tex, 0) end
end

local function NewLine(parent, color, alpha, layer)
    local t = parent:CreateTexture(nil, layer or "ARTWORK")
    t:SetColorTexture(color[1], color[2], color[3], alpha)
    Crisp(t)
    return t
end

-- Two glow_edge strips beside a thin frame (the AddOuterGlow strips, without its corner blooms so
-- they can resize on a rescale). `vertical` lines glow left and right, horizontal ones above and
-- below. Resized in Layout.
local function AddLineGlow(frame, vertical, color, alpha)
    if not (Theme and Theme.GLOW_EDGE_TEXTURE) then return nil end
    local a = frame:CreateTexture(nil, "BACKGROUND")
    local b = frame:CreateTexture(nil, "BACKGROUND")
    for _, t in ipairs({ a, b }) do
        t:SetTexture(Theme.GLOW_EDGE_TEXTURE)
        t:SetBlendMode("ADD")
        t:SetVertexColor(color[1], color[2], color[3], alpha)
    end
    if vertical then
        a:SetPoint("TOPRIGHT", frame, "TOPLEFT", 0, 0)
        a:SetPoint("BOTTOMRIGHT", frame, "BOTTOMLEFT", 0, 0)
        a:SetTexCoord(0, 1, 0, 1, 0, 0, 0, 0)
        b:SetPoint("TOPLEFT", frame, "TOPRIGHT", 0, 0)
        b:SetPoint("BOTTOMLEFT", frame, "BOTTOMRIGHT", 0, 0)
        b:SetTexCoord(0, 0, 0, 0, 0, 1, 0, 1)
    else
        a:SetPoint("BOTTOMLEFT", frame, "TOPLEFT", 0, 0)
        a:SetPoint("BOTTOMRIGHT", frame, "TOPRIGHT", 0, 0)
        a:SetTexCoord(0, 1, 0, 0, 1, 1, 1, 0)
        b:SetPoint("TOPLEFT", frame, "BOTTOMLEFT", 0, 0)
        b:SetPoint("TOPRIGHT", frame, "BOTTOMRIGHT", 0, 0)
    end
    local glow = { a, b, vertical = vertical }
    glows[#glows + 1] = glow
    return glow
end

local function SizeGlows()
    local reach = ui(C.GLOW_REACH)
    for _, glow in ipairs(glows) do
        for i = 1, 2 do
            if glow.vertical then glow[i]:SetWidth(reach) else glow[i]:SetHeight(reach) end
        end
    end
end

-- A plain frame holding one stroke texture that fills it, plus optional line glow.
local function NewStroke(parent, name, color, alpha, vertical, glowAlpha)
    local frame = CreateFrame("Frame", NAME .. name, parent)
    local fill = NewLine(frame, color, alpha)
    fill:SetAllPoints(frame)
    if glowAlpha then AddLineGlow(frame, vertical, color, glowAlpha) end
    return frame, fill
end

-------------------------------------------------------------------------------
-- Fades (the horizon follows the owner pieces; the core fades the pieces it owns)
-------------------------------------------------------------------------------

local function Land(frame, on)
    if on then
        frame:SetAlpha(1)
        frame:Show()
    else
        frame:Hide()
        frame:SetAlpha(0)
    end
end

local function Fade(frame, on)
    local f = fades[frame]
    if not f then
        local group = frame:CreateAnimationGroup()
        local anim = group:CreateAnimation("Alpha")
        anim:SetDuration(FADE_SECONDS)
        if anim.SetSmoothing then anim:SetSmoothing("IN_OUT") end
        if group.SetToFinalAlpha then group:SetToFinalAlpha(true) end
        f = { group = group, anim = anim, on = on }
        group:SetScript("OnFinished", function() Land(frame, f.on) end)
        fades[frame] = f
    end
    f.on = on
    f.group:Stop()
    -- Fades from wherever the frame is now, so a flip mid fade does not snap alpha first.
    local from = frame:IsShown() and frame:GetAlpha() or 0
    if on then
        if not frame:IsShown() then
            frame:SetAlpha(0)
            frame:Show()
        end
    elseif not frame:IsShown() then
        Land(frame, false)
        return
    end
    -- An animation group never plays on a frame that is not VISIBLE (IsVisible counts every
    -- ancestor; IsShown is only the frame's own flag), so OnFinished would never fire and an off
    -- segment would stay at alpha 1: under a hidden root (Alt+Z) the frame lands at once instead.
    if not frame:IsVisible() then
        Land(frame, on)
        return
    end
    f.anim:SetFromAlpha(from)
    f.anim:SetToAlpha(on and 1 or 0)
    f.group:Play()
end

-------------------------------------------------------------------------------
-- Horizon
-------------------------------------------------------------------------------

local gates = {}          -- the target side parts' gates ({ gate, rule, on }), re-read on every target change

-- Each rule is looked up at call time (Theme.lua loads before this file, but a rule is never captured).
local function HasTargetRule() return FS.HasTarget() end
local function TakesDotsRule() return FS.TargetTakesDots() end

local function RefreshTargetLayer()
    for _, g in ipairs(gates) do
        local want = g.rule() and true or false
        if want ~= g.on then
            g.on = want
            if want then g.gate:Show() else g.gate:Hide() end
        end
    end
end

-- targetSide is the gate's rule: nil for the ungated left side, else HasTargetRule or TakesDotsRule.
local function BuildHorizonPart(key, x0, x1, tickX, targetSide)
    local frame = CreateFrame("Frame", NAME .. "horizon_" .. key, root)
    local part = { key = key, frame = frame, x0 = x0, x1 = x1, tickX = tickX }
    local body = frame
    if targetSide then
        -- The segment hangs off a gate under the part frame: the piece fade keeps the part frame, the
        -- player's target drives the gate.
        local gate = CreateFrame("Frame", nil, frame)
        gate:SetPoint("TOPLEFT", frame, "TOPLEFT", 0, 0)
        gate:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", 0, 0)
        gate:SetFrameLevel(frame:GetFrameLevel())     -- no extra level: the segment and tick keep root + 1
        part.gate = gate
        gates[#gates + 1] = { gate = gate, rule = targetSide }
        body = gate
    end
    part.segment = NewLine(body, violet, C.HZ_ALPHA)
    if tickX then part.tick = NewLine(body, violet, C.TICK_ALPHA) end
    horizon[key] = part
    byKey[key] = part
end

local function BuildHorizon()
    BuildHorizonPart("you", G.TL.x1 + G.HZ_PAD_L, G.LBRK, G.LBRK)
    BuildHorizonPart("tgt", G.RBRK, G.TR.x0 - C.HZ_TGT_PAD, G.RBRK, HasTargetRule)
    BuildHorizonPart("dot", G.TR.x1 + C.HZ_DOT_PAD_L, G.DOT_AX - G.HZ_PAD_R, nil, TakesDotsRule)
    RefreshTargetLayer()
    local events = CreateFrame("Frame", NAME .. "target_events", root)
    events:RegisterEvent("PLAYER_TARGET_CHANGED")
    events:RegisterEvent("PLAYER_ENTERING_WORLD")
    events:SetScript("OnEvent", RefreshTargetLayer)
    -- death, a duel and mind control change the dot rule with no target change; one frame, the target only
    local unitEvents = CreateFrame("Frame", NAME .. "target_unit_events", root)
    for _, name in ipairs({ "UNIT_HEALTH", "UNIT_FLAGS", "UNIT_FACTION" }) do
        if unitEvents.RegisterUnitEvent then pcall(unitEvents.RegisterUnitEvent, unitEvents, name, "target") end
    end
    unitEvents:SetScript("OnEvent", RefreshTargetLayer)
end

local function LayoutHorizonPart(part, T)
    local tickMid = (C.TICK_Y0 + C.TICK_Y1) / 2
    Seat(part.frame, "TOPLEFT", part.x0, C.TICK_Y0)
    part.frame:SetSize(ui(part.x1 - part.x0), ui(C.TICK_Y1 - C.TICK_Y0))
    Seat(part.segment, "LEFT", part.x0, G.CY)
    part.segment:SetSize(ui(part.x1 - part.x0), T)
    if part.tick then
        Seat(part.tick, "CENTER", part.tickX, tickMid)
        part.tick:SetSize(T, ui(C.TICK_Y1 - C.TICK_Y0))
    end
end

-------------------------------------------------------------------------------
-- Proc rungs
-------------------------------------------------------------------------------

local function PaintRung(rung)
    local q = rung.q
    local lit = q > 0.5
    local L = rung.lit
    -- Hidden until the proc is active: the whole rung (post, dashes, ticks, label, icon) is one frame
    -- whose alpha is q, and it hides the moment q lands on 0 with the proc down. This only ever hides
    -- (a rescale repaints through here and must not show a rung); SetTarget is what shows it.
    if q <= 0 and rung.target == 0 then
        rung.frame:Hide()
    else
        rung.frame:SetAlpha(q)
    end
    if q > 0.01 then
        L.frame:SetAlpha(1)   -- the rung frame carries q; no second multiply
        L.frame:Show()
        L.post:SetHeight(ui(2 * (G.PROC_BASE + q * G.PROC_GROW)))
    else
        L.frame:Hide()
    end
    if rung.litBranch ~= lit then
        rung.litBranch = lit
        local r, g, b
        if lit then r, g, b = amber[1], amber[2], amber[3] else r, g, b = Mix(violet, WHITE, C.LABEL_MIX) end
        rung.label:SetTextColor(r, g, b, 1)
        local ir, ig, ib
        if lit then ir, ig, ib = amber[1], amber[2], amber[3] else ir, ig, ib = Mix(violet, WHITE, C.ICON_MIX) end
        rung.edgeColor = { ir, ig, ib }
        rung.icon.tex:SetDesaturated(not lit)
    end
    rung.label:SetAlpha(C.LABEL_A0 + C.LABEL_A1)
    local alpha = C.ICON_A0 + C.ICON_A1
    rung.icon.tex:SetAlpha(alpha)
    rung.icon.fallback:SetAlpha(alpha)
    local e, ea = rung.edgeColor, C.EDGE_A0 + C.EDGE_A1
    if e then
        for _, edge in ipairs(rung.icon.edges) do edge:SetVertexColor(e[1], e[2], e[3], ea) end
    end
end

local function StepRung(rung, elapsed)
    local dq = elapsed / C.ANIM
    if rung.q < rung.target then
        rung.q = math.min(rung.target, rung.q + dq)
    elseif rung.q > rung.target then
        rung.q = math.max(rung.target, rung.q - dq)
    end
    PaintRung(rung)
    if rung.q == rung.target then rung.frame:SetScript("OnUpdate", nil) end
end

-- Aims q at 1 (lit) or 0. An inactive rung is hidden, so a proc going up Shows it here (at q 0, then it
-- grows) and StepRung / PaintRung hide it again when q lands on 0. Lands at once when nothing would be
-- seen (first state, or the prc piece hidden above it); otherwise one OnUpdate runs until q arrives.
-- Show / Hide / SetAlpha of this plain frame are legal in combat; `active` is a plain boolean here.
local function SetTarget(rung, active)
    rung.target = active and 1 or 0
    local parent = rung.frame:GetParent()
    if not rung.seen or (parent and not parent:IsVisible()) then
        rung.seen = true
        rung.q = rung.target
        rung.frame:SetScript("OnUpdate", nil)
        if rung.target > 0 then rung.frame:Show() end
        PaintRung(rung)
    elseif rung.q ~= rung.target then
        if rung.target > 0 and not rung.frame:IsShown() then rung.frame:Show() end
        PaintRung(rung)
        rung.frame:SetScript("OnUpdate", rung.onUpdate)
    end
end

-- Font sizes of the rung's two FontStrings (the label, and the two letter fallback inside the icon tile).
local function LabelFontSize() return math.max(8, math.floor(ui(C.LABEL_SIZE) + 0.5)) end
local function FallbackFontSize() return math.max(7, math.floor(ui(9) + 0.5)) end

-- Gives a FontString its font. The client throws "Font not set" for SetText on one without a font, so
-- this runs at creation, before any SetText: through Theme.ApplyMono, else (Theme missing or its call
-- throwing) a stock font object, so the first SetText can never be the thing that breaks the lane.
-- LayoutRung re-applies the mono font at the current size on every rescale.
local function EnsureFont(fs, size)
    if Theme and Theme.ApplyMono and pcall(Theme.ApplyMono, fs, size, WHITE) then return end
    if GameFontNormal ~= nil and fs.SetFontObject then pcall(fs.SetFontObject, fs, GameFontNormal) end
end

local function BuildRung(side, parent)
    local out = side == "left" and -1 or 1
    local bx = side == "left" and G.LBRK or G.RBRK
    local tape = side == "left" and G.TL or G.TR
    local rung = { side = side, bx = bx, out = out, tape = tape, tcx = (tape.x0 + tape.x1) / 2, q = 0, target = 0 }
    local frame = CreateFrame("Frame", NAME .. "rung_" .. side, parent)
    rung.frame = frame
    local box = Gunsight.anchors and Gunsight.anchors[side == "left" and "procL" or "procR"]
    if box then
        frame:SetPoint("TOPLEFT", box, "TOPLEFT", 0, 0)
        frame:SetPoint("BOTTOMRIGHT", box, "BOTTOMRIGHT", 0, 0)
    end
    rung.onUpdate = function(_, elapsed) StepRung(rung, elapsed) end

    -- Idle: dashed post and the two end ticks.
    rung.dashes, rung.ticks = {}, {}
    local count = math.floor((C.PROC_Y1 - C.PROC_Y0) / DASH_PITCH) + 1
    for i = 1, count do rung.dashes[i] = NewLine(frame, violet, C.IDLE_ALPHA) end
    for i = 1, 2 do rung.ticks[i] = NewLine(frame, violet, C.IDLE_ALPHA) end

    -- Lit: solid amber post and run (with glow), two end ticks hanging off the post ends.
    local lit = CreateFrame("Frame", NAME .. "lit_" .. side, frame)
    lit:Hide()
    local glowAlpha = C.GLOW_PEAK
    local post = NewStroke(lit, "post_" .. side, amber, 1, true, glowAlpha)
    local run = NewStroke(lit, "run_" .. side, amber, 1, false, glowAlpha)
    rung.lit = { frame = lit, post = post, run = run, ticks = {} }
    for i = 1, 2 do
        local tick = NewLine(lit, amber, 1)
        tick:SetPoint(out < 0 and "RIGHT" or "LEFT", post, i == 1 and "TOP" or "BOTTOM", 0, 0)
        rung.lit.ticks[i] = tick
    end

    -- Label and icon.
    rung.label = frame:CreateFontString(nil, "OVERLAY")
    EnsureFont(rung.label, LabelFontSize())
    rung.label:SetJustifyH("CENTER")
    local icon = { frame = CreateFrame("Frame", NAME .. "icon_" .. side, frame), edges = {} }
    if Theme and Theme.AddCut2Texture and Theme.SLICE_CUT2_FILL_TEXTURE then
        local ok, plate = pcall(Theme.AddCut2Texture, icon.frame, Theme.SLICE_CUT2_FILL_TEXTURE, PLATE, "BACKGROUND")
        if ok then icon.plate = plate end
    end
    icon.tex = icon.frame:CreateTexture(nil, "ARTWORK")
    icon.tex:SetTexCoord(0.08, 0.92, 0.08, 0.92)
    icon.fallback = icon.frame:CreateFontString(nil, "OVERLAY")
    EnsureFont(icon.fallback, FallbackFontSize())
    icon.fallback:SetPoint("CENTER", icon.frame, "CENTER", 0, 0)
    if Theme and Theme.AddSliceTexture then
        local ok, edge = pcall(Theme.AddSliceTexture, icon.frame, nil, violet, "OVERLAY", 1)
        if ok and edge then icon.edges[1] = edge end
    end
    rung.icon = icon

    frame:Hide()
    rungs[side] = rung
    return rung
end

local function LayoutRung(rung, T, Tl)
    local bx, out = rung.bx, rung.out
    for i, d in ipairs(rung.dashes) do
        local start = C.PROC_Y0 + (i - 1) * DASH_PITCH
        local len = math.min(C.DASH, C.PROC_Y1 - start)
        Seat(d, "TOP", bx, start)
        d:SetSize(T, ui(len))
    end
    for i, ty in ipairs({ C.PROC_Y0, C.PROC_Y1 }) do
        Seat(rung.ticks[i], "LEFT", math.min(bx, bx + out * C.IDLE_TICK), ty)
        rung.ticks[i]:SetSize(ui(C.IDLE_TICK), T)
    end

    local lit = rung.lit
    Seat(lit.post, "CENTER", bx, G.CY)
    lit.post:SetWidth(Tl)
    -- The tape's inner edge: the left tape's right side, the right tape's left side.
    local edgeX
    if rung.side == "left" then edgeX = rung.tape.x1 + C.RUN_PAD else edgeX = rung.tape.x0 - C.RUN_PAD end
    local a, b = math.min(bx, edgeX), math.max(bx, edgeX)
    Seat(lit.run, "LEFT", a, G.CY)
    lit.run:SetSize(ui(b - a), Tl)
    for i = 1, 2 do lit.ticks[i]:SetSize(ui(G.PROC_TICK), Tl) end

    -- Label above the tape, the icon to its left.
    if Theme and Theme.ApplyMono then
        pcall(Theme.ApplyMono, rung.label, LabelFontSize(), WHITE)
        pcall(Theme.ApplyMono, rung.icon.fallback, FallbackFontSize(), WHITE)
    end
    rung.litBranch = nil -- ApplyMono reset the colour
    Seat(rung.label, "BOTTOM", rung.tcx, C.LABEL_Y + C.LABEL_DESCENT)
    local icon = rung.icon
    local len = rung.labelText and #rung.labelText or 0
    Seat(icon.frame, "TOPLEFT", rung.tcx - len * C.CHAR_HALF - C.ICON - C.ICON_PAD, C.ICON_Y)
    local px = ui(C.ICON)
    icon.frame:SetSize(px, px)
    local cut = 4
    if Theme and Theme.CutSizeIcon then
        local ok, c = pcall(Theme.CutSizeIcon, px)
        if ok and type(c) == "number" and c > 0 then cut = c end
    end
    local inset = math.max(1, math.ceil(cut / 2))
    icon.tex:ClearAllPoints()
    icon.tex:SetPoint("TOPLEFT", icon.frame, "TOPLEFT", inset, -inset)
    icon.tex:SetPoint("BOTTOMRIGHT", icon.frame, "BOTTOMRIGHT", -inset, inset)
    -- The plate takes the ring's chamfer: a fixed 6 plate under a 3 or 4 ring leaves a wedge
    -- behind the ring's diagonal. Cut 6 is the base texture; 2, 3 and 4 have their own.
    if icon.plate then
        local path = cut == 6 and Theme.SLICE_CUT2_FILL_TEXTURE or (MEDIA .. "slice_cut2_fill_c" .. cut .. ".tga")
        if path then
            icon.plate:SetTexture(path)
            if Theme.ApplyNineSlice then pcall(Theme.ApplyNineSlice, icon.plate, cut) end
        end
    end
    if icon.edges[1] and Theme.Cut2ButtonSet then
        local ok, path = pcall(Theme.Cut2ButtonSet, cut)
        if ok and type(path) == "string" then
            icon.edges[1]:SetTexture(path)
            if Theme.ApplyNineSlice then pcall(Theme.ApplyNineSlice, icon.edges[1], cut) end
        end
    end
    PaintRung(rung)
end

-- The proc's spell texture, or nil. A missing function, a throw, a secret or a non texture all
-- read as "no icon" and the two letter fallback shows.
local function ResolveIcon(spec)
    if type(spec.aura) ~= "number" then return nil end
    local fn = (C_Spell and C_Spell.GetSpellTexture) or _G.GetSpellTexture
    if type(fn) ~= "function" then return nil end
    local ok, tex = pcall(fn, spec.aura)
    if not ok or IsSecret(tex) or tex == nil then return nil end
    if type(tex) == "number" or type(tex) == "string" then return tex end
    return nil
end

local function SeatIconTexture(rung, spec)
    local icon = rung.icon
    local tex = ResolveIcon(spec)
    icon.fallback:SetText(string.sub(rung.labelText or "", 1, 2))
    if tex then
        icon.tex:SetTexture(tex)
        icon.tex:Show()
        icon.fallback:Hide()
    else
        icon.tex:Hide()
        icon.fallback:Show()
    end
    rung.hasTexture = tex ~= nil
end

local function BindRung(rung, key, spec)
    if rung.key ~= key then
        rung.key = key
        rung.labelText = type(spec.label) == "string" and spec.label or string.upper(tostring(key))
        rung.label:SetText(rung.labelText)
        rung.hasTexture = nil
        rung.laidOut = false
    end
    if not rung.hasTexture then SeatIconTexture(rung, spec) end
    if not rung.laidOut then
        rung.laidOut = true
        LayoutRung(rung, rung.T or ui(1), rung.Tl or ui(C.LIT_K))
    end
end

local function UnbindRung(rung)
    rung.key = nil
    rung.seen = false
    rung.target, rung.q = 0, 0
    rung.frame:SetScript("OnUpdate", nil)
    rung.frame:Hide()
end

-- FS.Hud state to rungs: the profile says which proc sits on which side, the state says whether
-- it is up. No profile procs, no rungs.
local function ApplyState(state)
    local hud = FS.Hud
    local profile = type(hud) == "table" and type(hud.GetProfile) == "function" and hud.GetProfile() or nil
    local specs = type(profile) == "table" and type(profile.procs) == "table" and profile.procs or nil
    local active = {}
    local bound = {}
    if specs and type(state) == "table" and type(state.procs) == "table" then
        for _, p in ipairs(state.procs) do
            if type(p) == "table" and type(p.key) == "string" then
                local spec = specs[p.key]
                local rung = type(spec) == "table" and rungs[spec.side] or nil
                if rung and not bound[rung] then
                    bound[rung] = true
                    BindRung(rung, p.key, spec)
                    active[rung] = not IsSecret(p.active) and p.active == true
                end
            end
        end
    end
    for _, rung in pairs(rungs) do
        if bound[rung] then
            SetTarget(rung, active[rung])
        elseif rung.frame:IsShown() or rung.key then
            UnbindRung(rung)
        end
    end
end

-------------------------------------------------------------------------------
-- Layout, build
-------------------------------------------------------------------------------

local function Layout()
    if not built then return end
    local px = PixelUnit()
    local T, Tl = Thick(1, px), Thick(C.LIT_K, px)
    for _, part in pairs(horizon) do LayoutHorizonPart(part, T) end
    for _, rung in pairs(rungs) do
        rung.T, rung.Tl = T, Tl
        LayoutRung(rung, T, Tl)
    end
    SizeGlows()
end
GunsightFrame.Layout = Layout

local function Build()
    if built or not Gunsight.IsEnabled() then return end
    root = Gunsight.root
    Theme = FS.Theme or {}
    violet = Theme.COLOR_VIOLET or Theme.COLOR_BORDER or FALLBACK_VIOLET
    amber = Theme.COLOR_AMBER or FALLBACK_AMBER

    BuildHorizon()
    local prc = CreateFrame("Frame", NAME .. "prc", root)
    local pl, pr = Gunsight.anchors and Gunsight.anchors.procL, Gunsight.anchors and Gunsight.anchors.procR
    if pl and pr then
        prc:SetPoint("TOPLEFT", pl, "TOPLEFT", 0, 0)
        prc:SetPoint("BOTTOMRIGHT", pr, "BOTTOMRIGHT", 0, 0)
    end
    GunsightFrame.prc = prc
    BuildRung("left", prc)
    BuildRung("right", prc)
    built = true
    Layout()

    for key, part in pairs(byKey) do Land(part.frame, Gunsight.IsPieceOn(key)) end
    Gunsight.RegisterPiece("prc", { frame = prc })
    Gunsight.OnPieceChanged(function(key, on)
        local part = byKey[key]
        if part then Fade(part.frame, on) end
    end)
    if FS.Layout and FS.Layout.OnRescale then FS.Layout.OnRescale(Layout) end

    local hud = FS.Hud
    if type(hud) == "table" and type(hud.Subscribe) == "function" then
        hud.Subscribe(ApplyState)
    else
        LogOnce("no_hud", "FS.Hud is missing; the proc rungs stay hidden.")
    end
end

Gunsight.OnReady(Build)
