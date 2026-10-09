-- Forever STUwave: Frame Helpers
-- Shared secure-frame scaffolding factored out of UnitFrames/PartyFrames/
-- CastBars/Buffs.lua by the 2026-09-23 secure-frame consolidation audit: each
-- of those files had independently re-derived the same handful of helpers
-- (in three cases with small, unnoticed drift between the copies -- see the
-- per-helper notes below). Exposed on FS.FrameHelpers. Loaded right after
-- Layout.lua, before every component module that consumes it (UnitFrames,
-- PartyFrames, CastBars, Buffs; see the .toc).
--
-- ActionBars.lua does NOT use HideBlizzardFrame (it hides Blizzard's own bars
-- via a different stash/dim mechanism, see its header), but it, StanceBar.lua
-- and PetActionBar.lua do share the button helpers at the end of this file
-- (SeatButtonCooldown, SeatButtonText, AttachQuickKeybind).

local _, FS = ...
FS.FrameHelpers = FS.FrameHelpers or {}
local Helpers = FS.FrameHelpers
local Theme = FS.Theme
local IsSecret = FS.IsSecret

-------------------------------------------------------------------------------
-- Hide a Blizzard default frame
-------------------------------------------------------------------------------

-- Byte-identical across UnitFrames/PartyFrames/CastBars/Buffs before this
-- extraction. Kills events, hides the frame, and re-hides it if anything
-- tries to Show it again -- HookScript (not SetScript) so the hook doesn't
-- taint the frame's own handlers. Must run out of combat (enforced by callers).
function Helpers.HideBlizzardFrame(frame)
    if not frame then return end
    frame:UnregisterAllEvents()
    frame:Hide()
    frame:HookScript("OnShow", frame.Hide)
end

-- Child bars and sub-frames of a Blizzard unit frame that register THEIR OWN
-- events. UnitFrameHealthBar_Initialize / UnitFrameManaBar_Initialize put
-- RegisterUnitEvent("UNIT_MAXHEALTH"/"UNIT_MAXPOWER", ...) plus an OnEvent script on
-- the bar itself, and the target spellbar and the ToT sub-frame do the same
-- (Blizzard_UnitFrame UnitFrame.lua ~603-621 and ~848-875, TargetFrame.lua ~708-714).
-- The root's UnregisterAllEvents never reached them, so for an invisible frame they
-- kept running UnitFrameHealthBar_Update -> HealthBar_OnValueChanged and
-- UnitFrameHealPredictionBars_Update on secret health values, which throw
-- "execution tainted by 'forever-stuwave'". The heal prediction/absorb bars are
-- plain textures/status bars with no event registration of their own, so they are
-- not listed.
-- petFrame: in 12.1 only the deprecated arena frames carry a `petFrame` field. The
-- global PetFrame is dimmed directly and covers its own healthbar/manabar, so the
-- field is harmless here and kept only to future-proof a frame that has one.
-- OnUpdate is deliberately left alone: SetScript(nil) on a Blizzard frame would
-- itself taint. UnitFrameHealthBar_OnUpdate (UnitFrame.lua:772-795) is still live on
-- an invisible bar (alpha 0, still shown) because frequentUpdates is true, and it hits the same sinks as
-- OnEvent. Every error captured so far came through the OnEvent path
-- (UnitFrame.lua:653 and :250) (live client line numbers). If OnUpdate errors ever show up in /fserr, the fix
-- is finding the taint source, not silencing the handler.
-- Re-arm: UnitFrame_SetUnit re-registers UNIT_MAXHEALTH and the mana-bar events
-- when a frame's unit string changes (vehicle enter/exit on PlayerFrame/PetFrame;
-- PlayerFrame_UpdateArt is reachable through the alt-power-bar callbacks). Those
-- triggers are mostly dead because the root frame is silenced, so this is a
-- one-shot that rarely decays. If it ever shows up, the remedy is a
-- hooksecurefunc("UnitFrame_SetUnit") post-hook that re-unregisters, filtered to
-- the frames we dimmed. Not implemented.
-- "PowerBarAlt" (capital P) is the PartyMemberFrameTemplate parentKey (Blizzard_UnitFrame
-- Mainline/PartyFrameTemplates.xml), whose UNIT_POWER_BAR_* / GROUP_ROSTER_UPDATE handlers
-- would otherwise stay live; the lowercase "powerBarAlt" is the other frames' field.
local DIM_CHILD_FIELDS = { "healthbar", "manabar", "spellbar", "totFrame", "petFrame", "powerBarAlt",
    "PowerBarAlt" }
local DIM_NESTED_BARS = { "healthbar", "manabar" }

-- Read-only field reads and one pcall'd UnregisterAllEvents per child: no
-- SetScript/Hide/HookScript and no write to any Blizzard table, so no new taint.
local function UnregisterChildEvents(frame)
    local seen = { [frame] = true }
    local function silence(child)
        if type(child) ~= "table" or seen[child] then return false end
        seen[child] = true
        if type(child.UnregisterAllEvents) ~= "function" then return false end
        pcall(child.UnregisterAllEvents, child)
        return true
    end
    for _, field in ipairs(DIM_CHILD_FIELDS) do
        local ok, child = pcall(function() return frame[field] end)
        if ok and silence(child) then
            -- ToT (and petFrame, where present) own a healthbar/manabar of their own
            for _, nested in ipairs(DIM_NESTED_BARS) do
                local ok2, bar = pcall(function() return child[nested] end)
                if ok2 then silence(bar) end
            end
        end
    end
end

-- Alpha-only sibling of HideBlizzardFrame for a Blizzard frame that is ALSO an
-- Edit Mode system (BuffFrame/DebuffFrame/TemporaryEnchantFrame -- see
-- Buffs.lua's entry). No Hide()/HookScript/method replacement: SetAlpha(0)
-- survives Blizzard's own Show() calls on its own, so unlike HideBlizzardFrame
-- this needs no re-assert hook. Full rationale in CLAUDE.md.
function Helpers.DimBlizzardFrame(frame)
    if not frame then return end
    frame:UnregisterAllEvents()
    UnregisterChildEvents(frame)
    frame:SetAlpha(0)
    if frame.EnableMouse then
        frame:EnableMouse(false)
    end
    -- Alpha is inherited by children, but EnableMouse is not, so a pooled aura
    -- button child could still eat clicks while invisible. UNVERIFIED IN-GAME
    -- whether UnregisterAllEvents is sufficient to stop new children spawning
    -- after this one-time sweep.
    for _, child in ipairs({ frame:GetChildren() }) do
        if child.EnableMouse then
            child:EnableMouse(false)
        end
    end
end

-- The frames BELOW a Blizzard action bar that DimBlizzardFrame's one-level child
-- sweep would miss. An ActionBarMixin bar's children are its
-- ActionBarButtonContainerN frames, NOT the buttons: each container holds one
-- stock button, and the bar keeps the same buttons in its `actionButtons` table
-- (Blizzard_ActionBar/Shared/ActionBar.lua, ActionBar_OnLoad). EnableMouse does
-- not inherit, so a sweep that stops at the containers leaves 12 real buttons per
-- bar clickable at alpha 0. Read-only: nothing here writes a Blizzard table or
-- calls a Blizzard method, so it cannot taint. Deduplicated, because a button is
-- reachable both through its container and through `actionButtons`.
function Helpers.CollectActionBarFrames(bar)
    local out, seen = {}, {}
    local function add(frame)
        if type(frame) ~= "table" or seen[frame] then return end
        seen[frame] = true
        out[#out + 1] = frame
    end
    local function addChildren(frame)
        if not frame.GetChildren then return end
        local ok, children = pcall(function() return { frame:GetChildren() } end)
        if not ok then return end
        for _, child in ipairs(children) do
            add(child)
            -- One level more: container -> its stock button. Guarded per child, some
            -- children are forbidden.
            pcall(function()
                for _, grandchild in ipairs({ child:GetChildren() }) do add(grandchild) end
            end)
        end
    end
    addChildren(bar)
    if type(bar.actionButtons) == "table" then
        for _, button in ipairs(bar.actionButtons) do add(button) end
    end
    return out
end

-- Dim a Blizzard ACTION BAR (an Edit Mode system: StanceBar, MultiBarN, ...) and
-- everything on it, touching nothing but SetAlpha and EnableMouse. Neither runs a
-- line of Blizzard Lua. What it deliberately does NOT do, each one a taint source
-- on an Edit Mode bar: Hide/Show (the instance method is Blizzard's HideOverride,
-- so our call would run its visibility code and the OnHide cascade into every stock
-- button under our taint), SetParent, SetScript/HookScript, writing the bar's or the
-- button dispatchers' tables, and UnregisterAllEvents (stock buttons register no
-- events of their own, the ActionBarButtonEventsFrame dispatcher drives them, and
-- unregistering the bar's own events is not needed once it is invisible). Not for
-- combat: the caller gates, since EnableMouse on a secure button is protected.
function Helpers.DimActionBar(bar)
    if not bar then return end
    bar:SetAlpha(0)
    if bar.EnableMouse then bar:EnableMouse(false) end
    for _, frame in ipairs(Helpers.CollectActionBarFrames(bar)) do
        pcall(function()
            frame:SetAlpha(0)
            if frame.EnableMouse then frame:EnableMouse(false) end
        end)
    end
end

-------------------------------------------------------------------------------
-- Step runner: this addon used THREE separate idioms for resilient pcall
-- wrapping (TryStep in UnitFrames/PartyFrames/CastBars, ReportOnce in
-- PartyFrames/Buffs, PartyFrames using both, each with ITS OWN message
-- wording). One factory now backs both idioms:
--   RunStep(frame, label, fn)  -- pcall fn(frame); prints on EVERY failure.
--   ReportOnce(label, err)     -- prints only the FIRST failure for `label`,
--                                 for a caller doing its own pcall (e.g.
--                                 Buffs' weapon-enchant refresh, which needs
--                                 the pcall's other return value) and just
--                                 wanting deduped reporting.
-- `describeStep`/`describeOnce` each return the text printed before
-- " failed: <err>" for a given label. They are SEPARATE because at least one
-- caller (PartyFrames) uses different wording for its TryStep call sites
-- ("... step 'label'") than for its ReportOnce call sites ("... label", no
-- "step", no quotes) -- describeOnce defaults to describeStep for callers
-- that only need one idiom and don't care.
-------------------------------------------------------------------------------

function Helpers.NewStepRunner(describeStep, describeOnce)
    describeOnce = describeOnce or describeStep
    local reported = {}

    local function ReportOnce(label, err)
        if reported[label] then return end
        reported[label] = true
        print(describeOnce(label) .. " failed: " .. tostring(err))
    end

    local function RunStep(frame, label, fn)
        local ok, err = pcall(fn, frame)
        if not ok then
            print(describeStep(label) .. " failed: " .. tostring(err))
        end
    end

    return RunStep, ReportOnce
end

-------------------------------------------------------------------------------
-- pcall-wrapped RegisterUnitEvent
-------------------------------------------------------------------------------

-- RegisterUnitEvent throws on an event name the client doesn't recognize;
-- pcall-guarded so one missing/renamed event can't stop the rest of
-- registration. `onFail(event, err)` is the caller's own reporter (CastBars
-- prints every failure; Buffs dedups through its ReportOnce), so each
-- module's exact wording is preserved. Dup in CastBars/Buffs before this
-- extraction.
function Helpers.SafeRegisterUnitEvent(events, event, unit, onFail)
    local ok, err = pcall(events.RegisterUnitEvent, events, event, unit)
    if not ok then
        onFail(event, err)
    end
end

-------------------------------------------------------------------------------
-- Pill bar (rounded track/border/glow shell + inset neon-fill StatusBar)
-------------------------------------------------------------------------------

local function FillHeight(height, inset)
    return math.max(2, height - 2 * inset)
end

local function FillRadius(height, inset)
    return FillHeight(height, inset) / 2
end

local function IsCut()
    return Theme.CHROME_CORNERS == "cut"
end

-- Chamfer or radius the shell chrome (glow, track, border) AND the fill's erase quads
-- share, so the mask follows the stroke exactly. Cut: Theme.CutSize(height) (16px ->
-- 4), the baked erase triangle already accounts for the 1px fill inset. Round: the old
-- pill radii, untouched.
local function ChromeRadius(height)
    if IsCut() then return Theme.CutSize(height) end
    return height / 2
end

local function MaskRadius(height, inset)
    if IsCut() then return Theme.CutSize(height) end
    return FillRadius(height, inset)
end

-- Seats the StatusBar inside the shell.
local function SeatBar(bar, shell, inset)
    bar:ClearAllPoints()
    bar:SetPoint("TOPLEFT", shell, "TOPLEFT", inset, -inset)
    bar:SetPoint("BOTTOMRIGHT", shell, "BOTTOMRIGHT", -inset, inset)
end

-- Frame level of the cut border host: one above the corner mask (bar = shell + 1,
-- mask = bar + BAR_CORNER_MASK_LEVEL), so the diagonal stroke is never overpainted by
-- the opaque erase quads. The text host sits one level above this (TextLevel), so the
-- value text never ties with the border and creation order does not matter.
local function BorderLevel(shell)
    return shell:GetFrameLevel() + 1 + Theme.BAR_CORNER_MASK_LEVEL + 1
end

-- Builds glow, track and border on a fresh child Frame of `shell`, sitting at the
-- shell's own level so the fill StatusBar (one level up) draws above it. Returns the
-- host, and under "cut" a second host carrying only the border: the erase quads sit
-- above the track host, so a border drawn there loses its diagonal stroke to them
-- (where the fill rect overlaps it), and the cut stroke is instead drawn on its own
-- frame ABOVE the corner mask. Round keeps the border on the one host (second return
-- nil).
local function BuildPillChrome(shell, opts, height)
    local host = CreateFrame("Frame", nil, shell)
    host:SetAllPoints(shell)
    host:SetFrameLevel(shell:GetFrameLevel())

    local radius = ChromeRadius(height)
    local bc = Theme.COLOR_BORDER
    Theme.AddOuterGlow(host, bc[1], bc[2], bc[3], opts.glowSize or 3, opts.glowAlpha or 0.25, radius)
    Theme.AddRoundedFill(host, Theme.COLOR_BAR_TRACK, radius)

    local borderColor = opts.borderColor or Theme.COLOR_BAR_BORDER
    if IsCut() then
        local borderHost = CreateFrame("Frame", nil, shell)
        borderHost:SetAllPoints(shell)
        borderHost:SetFrameLevel(BorderLevel(shell))
        Theme.AddGradientBorder(borderHost, borderColor, 1, radius)
        return host, borderHost
    end
    Theme.AddGradientBorder(host, borderColor, 1, radius)
    return host
end

-- Shared shape behind UnitFrames' CreateStatBar: an
-- outer `shell` Frame hosts the pill chrome (glow, track fill, border at
-- the chamfer Theme.CutSize(height), or radius height / 2 under the "round"
-- A/B flag) on a child frame (see BuildPillChrome) and the neon fill
-- is an inset child StatusBar (`bar.shell` points back to it). The fill's
-- corners are cut by opaque track-colored quads on `bar.cornerMask`: static
-- ones at the bar rect's corners, plus (round chrome only) two riding the fill
-- texture's right edge. See CLAUDE.md "Pill bars"; CastBars' bars deliberately
-- do not use this builder.
--
-- opts:
--   height        required
--   fillColor     required; {r,g,b[,a]}, the StatusBar's initial color
--   fillInset     inset between shell and the inner StatusBar
--                 (default Theme.BAR_FILL_INSET, which must equal the
--                 unscaled border thickness BuildPillChrome draws)
--   glowSize      AddOuterGlow size (default 3)
--   glowAlpha     AddOuterGlow alpha (default 0.25)
--   borderColor   AddGradientBorder color (default Theme.COLOR_BAR_BORDER)
--   styleText     function(fontString) to add + style a centered value
--                 FontString (sets bar.text); omit to skip it entirely. The
--                 FontString lives on a child Frame of `shell` above the
--                 corner quads.
--   cornerMaskColor override for the corner-quad tint (default
--                 Theme.COLOR_BAR_TRACK, the track color already behind the
--                 fill; always painted fully opaque)
--
-- Returns the StatusBar, carrying .shell, .text (if styleText),
-- :SetPillHeight(height[, inset]), .cornerMask, .fsFillCorners,
-- .fsLeadingCorners (round only; nil under cut) and (cut only) .fsBorderHost.
-- SetPillHeight resizes the shell, fill inset and corner quads, and on a height
-- change rebuilds the shell chrome at the new chamfer (the old chrome and
-- border hosts are hidden and abandoned, a frame or two per rescale, which is
-- rare).
function Helpers.CreatePillBar(parent, opts)
    local shell = CreateFrame("Frame", nil, parent)
    shell:SetHeight(opts.height)

    local chromeHost, borderHost = BuildPillChrome(shell, opts, opts.height)

    local bar = CreateFrame("StatusBar", nil, shell)
    bar:SetFrameLevel(shell:GetFrameLevel() + 1)
    local inset = opts.fillInset or Theme.BAR_FILL_INSET
    local fillRadius = MaskRadius(opts.height, inset)
    SeatBar(bar, shell, inset)
    bar:SetStatusBarTexture(Theme.FLAT_TEXTURE)
    local fc = opts.fillColor
    bar:SetStatusBarColor(fc[1], fc[2], fc[3], fc[4] or 1)
    bar:SetMinMaxValues(0, 1)
    bar:SetValue(0)
    bar.shell = shell
    bar.fsPillInset = inset
    bar.fsPillHeight = opts.height
    bar.fsPillOpts = opts
    bar.fsChromeHost = chromeHost
    bar.fsBorderHost = borderHost

    -- MaskTexture does not clip on this client, so the fill's square
    -- corners are hidden by opaque track-colored quads instead. The host
    -- is a child Frame of `shell` at bar + Theme.BAR_CORNER_MASK_LEVEL so
    -- the quads composite above the heal/absorb overlays and caret host
    -- stacked on `bar`. The static quads (Theme.AddCornerMask) sit at the bar
    -- rect's corners, so they cannot spill past it. The round-only leading
    -- quads ride the fill's right edge and sit on a clipping child frame, so
    -- they cannot spill past the bar's left edge when the fill is narrow.
    local cornerMask = CreateFrame("Frame", nil, shell)
    cornerMask:SetAllPoints(bar)
    cornerMask:SetFrameLevel(bar:GetFrameLevel() + Theme.BAR_CORNER_MASK_LEVEL)
    if cornerMask.SetClipsChildren then
        cornerMask:SetClipsChildren(true)
    end
    local maskColor = opts.cornerMaskColor or Theme.COLOR_BAR_TRACK
    bar.cornerMask = cornerMask
    -- Under cut a chamfer of 0 (height < 4) must still build CUT quads (Theme builds round
    -- ones at radius 0, which SetRadius could later resize), so build at the smallest baked
    -- chamfer and hide them via the handle, the same path SetPillHeight takes.
    local buildRadius = (IsCut() and fillRadius <= 0) and 2 or fillRadius
    bar.fsFillCorners = Theme.AddFillCorners(cornerMask, bar, maskColor, buildRadius)
    -- No leading-edge quad under cut (Parker, playtest 2026-10-04: a diagonal notch cut
    -- into the fill and the caret whenever HP or mana was below 100%): a quad riding the
    -- fill's moving right edge is right for a rounded pill end, but under cut it carves a
    -- travelling bottom-right notch into the fill and the caret at every mid-bar level, and
    -- at full value doubles the static BOTTOM-RIGHT quad. The cut is a fixed shape: the
    -- static quads only. Same rule and rationale as the nameplate bars (AddRoundedFillMask
    -- in Nameplates.lua); round keeps the leading quads.
    if not IsCut() then
        bar.fsLeadingCorners = Theme.AddLeadingEdgeCorners(cornerMask, bar, maskColor, buildRadius)
    end
    if buildRadius ~= fillRadius then
        bar.fsFillCorners.SetRadius(fillRadius)
        if bar.fsLeadingCorners then bar.fsLeadingCorners.SetRadius(fillRadius) end
    end

    -- Creates frames (BuildPillChrome): must only run out of combat (no caller today).
    bar.SetPillHeight = function(self, height, newInset)
        local pillInset = newInset or self.fsPillInset
        self.fsPillInset = pillInset
        shell:SetHeight(height)
        if height ~= self.fsPillHeight then
            self.fsPillHeight = height
            self.fsChromeHost:Hide()
            if self.fsBorderHost then self.fsBorderHost:Hide() end
            self.fsChromeHost, self.fsBorderHost = BuildPillChrome(shell, self.fsPillOpts, height)
        end
        local newRadius = MaskRadius(height, pillInset)
        SeatBar(self, shell, pillInset)
        self.fsFillCorners.SetRadius(newRadius)
        if self.fsLeadingCorners then self.fsLeadingCorners.SetRadius(newRadius) end
    end

    if opts.styleText then
        local textHost = CreateFrame("Frame", nil, shell)
        textHost:SetAllPoints(bar)
        textHost:SetFrameLevel(BorderLevel(shell) + 1)
        local text = textHost:CreateFontString(nil, "OVERLAY", nil, 7)
        text:SetPoint("CENTER", bar, "CENTER", 0, 0)
        opts.styleText(text)
        bar.text = text
    end

    return bar
end

-------------------------------------------------------------------------------
-- Static leading-edge caret (health/power bar fill's right edge)
-------------------------------------------------------------------------------

-- Extracted out of UnitFrames.lua's local CreateCaret (2026-09-24 caret-glow
-- pass) so UnitFrames, Nameplates.lua's nameplate bars (and, until the
-- chevron cast bar replaced it, PetCastBar) share one builder. Static geometry: rides
-- bar:GetStatusBarTexture()'s RIGHT edge, a LIVE anchor the engine
-- repositions from the (secret) value, so no cur/max fraction is ever
-- computed here -- same technique UnitFrames.lua's CreateOverlayBar uses.
-- Hosted on its own child frame at bar+2 rather than drawn as a plain region
-- of `bar`: a region's OVERLAY sublevel only orders it against OTHER REGIONS
-- of the same frame, not against child FRAMES (which composite above all of
-- a parent's own regions regardless of sublevel). See Theme.BAR_CORNER_MASK_LEVEL
-- and CreatePillBar's cornerMask above for why bar+2 stays safely below it.
--
-- RESTORED 2026-09-25: the 2026-09-25 static-tick rewrite went too far the
-- other way (Parker: "we had the pulse nailed down, why did it go to
-- shit?"). Back to a 3px line, tinted per bar via the `color` argument
-- ({r,g,b,a}), with a gentle alpha pulse -- no glow texture, no scale
-- animation, just the line's own alpha bouncing.
--
-- `host` still exists solely for the 0-value case: at 0 value (dead units,
-- empty-resource power bars) the fill's right edge sits at the bar's LEFT
-- edge, and without clipping the tick would hang half outside the bar to the
-- left. `host:SetClipsChildren` (a scissor clip, a different mechanism from
-- the MaskTexture this addon already found doesn't clip on this client --
-- see Theme.lua's AddCornerMask) fixes that, but it clips child FRAMES, so the
-- caret texture sits on a child Frame of `host` at the same level.
--
-- `caret.host` is still what `Helpers.UpdateCaretFull` (below) and
-- UnitFrames.lua's dead/offline branch hide/show -- do not rename or remove
-- it, both callers reach the caret only through this field.
function Helpers.CreateCaret(bar, color)
    local tipAnchor = bar:GetStatusBarTexture()
    local host = CreateFrame("Frame", nil, bar)
    host:SetAllPoints(bar)
    host:SetFrameLevel(bar:GetFrameLevel() + 2)
    if host.SetClipsChildren then
        host:SetClipsChildren(true)
    end

    local clipChild = CreateFrame("Frame", nil, host)
    clipChild:SetAllPoints(host)
    clipChild:SetFrameLevel(host:GetFrameLevel())

    local caret = clipChild:CreateTexture(nil, "OVERLAY")
    caret:SetColorTexture(color[1], color[2], color[3], color[4] or 1)
    caret:SetWidth(3)
    caret:ClearAllPoints()
    caret:SetPoint("TOP", tipAnchor, "TOPRIGHT", 0, 0)
    caret:SetPoint("BOTTOM", tipAnchor, "BOTTOMRIGHT", 0, 0)

    local ag = caret:CreateAnimationGroup()
    ag:SetLooping("BOUNCE")
    local pulse = ag:CreateAnimation("Alpha")
    pulse:SetFromAlpha(1)
    pulse:SetToAlpha(0.5)
    pulse:SetDuration(0.75)
    pulse:SetSmoothing("IN_OUT")
    ag:Play()
    caret.anim = ag

    caret.host = host

    return caret
end

-------------------------------------------------------------------------------
-- Caret hide-at-full (health/power)
-------------------------------------------------------------------------------

-- One shared step curve for every caret (health or power, any consumer):
-- three breakpoints instead of two, since the caret needs to hide at BOTH
-- ends of the bar, not just at full. AddPoint(0,0) then AddPoint(EPSILON,1)
-- then AddPoint(1,0) reads alpha 0 at true empty (x=0), alpha 1 for any
-- meaningfully-nonzero fraction, and alpha 0 again at exactly 100% -- a step
-- curve returns the y of the last point <= x, per ElvUI's
-- Game/Shared/General/API.lua (CreateCurve/SetType/AddPoint usage,
-- ~line 581-640).
local HAS_CURVE_API = type(C_CurveUtil) == "table" and type(C_CurveUtil.CreateCurve) == "function"
    and type(Enum) == "table" and type(Enum.LuaCurveType) == "table"

-- The near-empty breakpoint above: without it, a step curve with only
-- AddPoint(0,1)/AddPoint(1,0) reads alpha 1 for every fraction from 0 up to
-- just below 1, so a dead unit (0% HP) still shows the pulsing caret at full
-- alpha. Parker may need to tune this in-game -- too large hides the caret
-- at low-but-real HP, too small may miss the point due to float rounding on
-- 0/max health or power.
local EPSILON = 0.0005

-- SetType/AddPoint can throw exactly like CreateCurve itself, so all five
-- calls live in ONE pcall'd function: an unguarded throw here would abort
-- the rest of this file's definitions (CreateLevelChip, ReadAuraSlot,
-- ShowAuraTooltip are all declared below this point).
local function BuildFullHideCurve()
    local curve = C_CurveUtil.CreateCurve()
    curve:SetType(Enum.LuaCurveType.Step)
    curve:AddPoint(0, 0)          -- truly empty / dead: hidden
    curve:AddPoint(EPSILON, 1)    -- any nonzero value: visible
    curve:AddPoint(1, 0)          -- full: hidden (existing behavior)
    return curve
end

local FULL_HIDE_CURVE
if HAS_CURVE_API then
    local ok, curve = pcall(BuildFullHideCurve)
    if ok then FULL_HIDE_CURVE = curve end
end

local HAS_UNIT_HEALTH_PERCENT = type(UnitHealthPercent) == "function"
local HAS_UNIT_POWER_PERCENT = type(UnitPowerPercent) == "function"
local warnedNoCaretFullHide = false

-- Latched the first time the curve/percent path fails (a refused setter
-- argument, or a throwing percent call). Every later call then skips
-- straight to the plain cur/max fallback instead of retrying a path already
-- proven to error -- UpdatePowerValue is a hot UNIT_POWER_UPDATE handler, and
-- a failing pcall there would allocate every tick.
local curveHideBroken = false

-- Hides `caret.host` (line + glow's shared clip frame) when the bar is at
-- 100%, per Parker's direction that the caret be disabled at a full bar.
-- `kind` is "health" or "power", selecting which secret-safe percent API to
-- read. Two SEPARATE fallbacks: the curve/percent path erroring latches
-- `curveHideBroken` for every later call, while the curve/percent APIs being
-- absent from the start goes straight to a plain cur/max compare, itself
-- only legal when neither value is secret.
function Helpers.UpdateCaretFull(caret, unit, kind)
    local host = caret and caret.host
    if not host then return end

    local hasPercentAPI = (kind == "health" and HAS_UNIT_HEALTH_PERCENT)
        or (kind == "power" and HAS_UNIT_POWER_PERCENT)

    if FULL_HIDE_CURVE and hasPercentAPI and not curveHideBroken then
        local ok, alpha
        if kind == "health" then
            ok, alpha = pcall(UnitHealthPercent, unit, false, FULL_HIDE_CURVE)
        else
            ok, alpha = pcall(UnitPowerPercent, unit, nil, false, FULL_HIDE_CURVE)
        end
        -- `alpha` is type-checked, not truth-tested: `type(v) == "number"` is
        -- legal on any value including a secret (type() never throws),
        -- whereas a bare truth-test risks the illegal secret-boolean case
        -- PartyFrames.lua's ApplyRangeAlpha note documents.
        local applied = ok and type(alpha) == "number" and pcall(host.SetAlpha, host, alpha)
        if applied then return end

        curveHideBroken = true
        if not warnedNoCaretFullHide then
            warnedNoCaretFullHide = true
            FS.LogDegradeOnce("caret_full_hide",
                "|cffff4488Forever STUwave|r: caret full-value hide setter refused, falling back to plain compare")
        end
        host:SetAlpha(1)
        host:SetShown(true)
        return
    end

    -- No curve/percent API on this client, or the curve path already proved
    -- broken this session: a plain cur/max compare, legal only when neither
    -- value is secret. SetAlpha(1) first so a previous alpha-0 full-hide
    -- can't linger under a SetShown(true).
    local cur, max
    if kind == "power" then
        cur, max = UnitPower(unit), UnitPowerMax(unit)
    else
        cur, max = UnitHealth(unit), UnitHealthMax(unit)
    end
    host:SetAlpha(1)
    -- IsSecret checked BEFORE any nil check: per Theme.lua's secret-value
    -- guard (~line 185-188), a secret may not be boolean-tested at all, so
    -- `cur and max` (a boolean test) is illegal if either is secret and has
    -- to run after, not before, the IsSecret guard. type() never throws on a
    -- secret, so it is what stands in for the nil check here instead.
    if not IsSecret(cur) and not IsSecret(max) and type(cur) == "number" and type(max) == "number" then
        host:SetShown(not (max > 0 and cur >= max))
    else
        host:SetShown(true)
    end
end

-------------------------------------------------------------------------------
-- Power host: hide at an empty power bar
-------------------------------------------------------------------------------

-- Used for chrome that would read as a stray dot at value 0 (PartyFrames'
-- power rail glow host). Lua cannot compare the secret value, so this Step
-- curve (alpha 0 at empty, 1 from EPSILON up, including full) is evaluated
-- engine-side, the same way FULL_HIDE_CURVE is.
local function BuildEmptyHideCurve()
    local curve = C_CurveUtil.CreateCurve()
    curve:SetType(Enum.LuaCurveType.Step)
    curve:AddPoint(0, 0)
    curve:AddPoint(EPSILON, 1)
    return curve
end

local EMPTY_HIDE_CURVE
if HAS_CURVE_API then
    local ok, curve = pcall(BuildEmptyHideCurve)
    if ok then EMPTY_HIDE_CURVE = curve end
end

local emptyHideBroken = false

-- Sets the alpha of `host` (any frame) to 0 at an empty power bar and 1 above
-- it. Without the curve/percent API, or after the first refused call (logged
-- once), the host is left fully visible.
function Helpers.UpdatePowerHostEmpty(host, unit)
    if not host then return end

    if EMPTY_HIDE_CURVE and HAS_UNIT_POWER_PERCENT and not emptyHideBroken then
        local ok, alpha = pcall(UnitPowerPercent, unit, nil, false, EMPTY_HIDE_CURVE)
        if ok and type(alpha) == "number" and pcall(host.SetAlpha, host, alpha) then return end

        emptyHideBroken = true
        FS.LogDegradeOnce("power_empty_hide",
            "|cffff4488Forever STUwave|r: power empty-hide setter refused, leaving power rail glow visible")
    end
    host:SetAlpha(1)
end

-- Power rail tint by UnitPowerType() (stable across power tokens), shared by
-- PartyFrames and PetFrame. Unlisted/unknown types (including Mana, 0) use the
-- theme's cyan COLOR_POWER, the same color the player power bar always wears.
Helpers.POWER_COLORS = {
    [1] = { 0.77, 0.12, 0.23, 1 }, -- Rage
    [2] = { 0.71, 0.43, 0.27, 1 }, -- Focus
    [3] = { 1.00, 1.00, 0.00, 1 }, -- Energy
    [4] = { 0.00, 0.66, 0.11, 1 }, -- Happiness (hunter pet)
}

-------------------------------------------------------------------------------
-- Laser rail (shared builder: PartyFrames' health and power rails)
-------------------------------------------------------------------------------

-- A thin neon beam with a soft bloom, no border or shell pill. Moved here
-- verbatim from PartyFrames.lua so another module can build the same user-
-- approved rail; every geometry value is passed in by the caller's spec, and
-- only the alphas have defaults. Textures are local to this section:
-- glow_round (the spark) has no Theme token, so its path is declared here.
local RAIL_FLAT_TEXTURE = Theme.FLAT_TEXTURE
local RAIL_GLOW_EDGE_TEXTURE = Theme.GLOW_EDGE_TEXTURE
local RAIL_GLOW_ROUND_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\glow_round.tga"

-- Default alphas; a spec may override each (tailAlpha, trackAlpha,
-- bloomAlpha, sparkAlpha). PartyFrames passes the same values explicitly.
Helpers.RAIL_TAIL_ALPHA  = 0.35  -- core gradient alpha at the fill's left end (1 at the tip)
Helpers.RAIL_TRACK_ALPHA = 0.18  -- dim track alpha at its center (0 at both outer ends)
Helpers.RAIL_BLOOM_ALPHA = 0.45
Helpers.RAIL_SPARK_ALPHA = 0.9

-- Horizontal alpha gradient in one color on a flat-white texture, pcall'd
-- (SetGradient is feature-dependent on this client). The first failure latches
-- railGradientBroken and is logged once; every rail retint then takes the flat
-- fallback without retrying a call already proven to throw. Returns true when
-- the gradient was applied. Exported because PartyFrames' dispel halo uses the
-- same gradient-or-flat fallback.
local railGradientBroken = false
function Helpers.SetRailGradient(tex, r, g, b, alphaFrom, alphaTo)
    if railGradientBroken or not (tex and tex.SetGradient and CreateColor) then
        return false
    end
    local ok = pcall(tex.SetGradient, tex, "HORIZONTAL",
        CreateColor(r, g, b, alphaFrom), CreateColor(r, g, b, alphaTo))
    if not ok then
        railGradientBroken = true
        FS.LogDegradeOnce("rail_gradient",
            "|cffff4488Forever STUwave|r: rail SetGradient failed, using flat tint")
    end
    return ok
end
local SetRailGradient = Helpers.SetRailGradient

-- Retints a whole laser rail (core fill, track, bloom, spark) in one color.
-- The core's gradient lives on the StatusBar texture, so SetStatusBarColor
-- would clobber it; it is only the fallback when the gradient is unavailable.
-- Cached on the last color APPLIED (callers retint on every power/health
-- event): a repeat of the same color is a no-op, so a steady state does no work.
function Helpers.SetLaserRailColor(bar, r, g, b)
    local rail = bar.fsRail
    if rail.r == r and rail.g == g and rail.b == b then return end
    rail.r, rail.g, rail.b = r, g, b

    if not SetRailGradient(bar:GetStatusBarTexture(), r, g, b, rail.tailAlpha, 1) then
        bar:SetStatusBarColor(r, g, b, 1)
    end
    -- Each half fades from 0 at its outer end to the track alpha at the center.
    if not (SetRailGradient(rail.trackLeft, r, g, b, 0, rail.trackAlpha)
        and SetRailGradient(rail.trackRight, r, g, b, rail.trackAlpha, 0)) then
        rail.trackLeft:SetVertexColor(r, g, b, rail.trackAlpha)
        rail.trackRight:SetVertexColor(r, g, b, rail.trackAlpha)
    end
    rail.bloomTop:SetVertexColor(r, g, b, rail.bloomAlpha)
    rail.bloomBottom:SetVertexColor(r, g, b, rail.bloomAlpha)
    rail.spark:SetVertexColor(r, g, b, rail.sparkAlpha)
end

-- SetDesaturated is a Texture method, not a global, so this is a per-call
-- existence check rather than a module-level HAS_ flag (mirrors the
-- caution about assuming a texture API always behaves the same on every
-- build). Covers the rail's core fill, spark and bloom (the list
-- CreateLaserRail caches as rail.desatTextures); the track is tinted
-- directly, not desaturated. rail.desaturated is the last state applied, so
-- repeat calls in a steady state do no work.
function Helpers.SetLaserRailDesaturated(bar, desaturated)
    local rail = bar.fsRail
    if rail.desaturated == desaturated then return end
    rail.desaturated = desaturated
    for _, tex in ipairs(rail.desatTextures) do
        if tex.SetDesaturated then tex:SetDesaturated(desaturated) end
    end
end

-- Builds the rail. Returns the core StatusBar (the value API target) with
-- `.shell` (the plain container Frame the caller anchors and shows/hides/dims)
-- and `.fsRail` (the regions SetLaserRailColor retints, plus `.host`, the bloom
-- and spark frame: a caller can drive its alpha to 0 at an empty power bar via
-- Helpers.UpdatePowerHostEmpty, or hide it while dead/offline).
--   spec.coreHeight   core fill and track line thickness; also the shell's height
--   spec.bloomSize    glow_edge strip thickness above and below the fill
--   spec.sparkWidth   glow_round spark size (width, height) at the fill's tip
--   spec.sparkHeight
--   spec.color        initial {r, g, b}
--   spec.styleText    optional function(fontString): adds a centered value
--                     FontString (bar.text) on a host above bloom and spark
--   spec.tailAlpha, trackAlpha, bloomAlpha, sparkAlpha
--                     optional; default to Helpers.RAIL_*_ALPHA
--   * track: a dim full-width line, two gradient halves fading out at both ends
--   * core:  the StatusBar, its texture gradient-brightening toward the tip
--   * bloom: two glow_edge strips hugging the fill texture's top and bottom
--   * spark: a glow_round flare centered on the fill texture's RIGHT edge
-- MaskTexture does not clip on this client, so nothing is masked: bloom and
-- spark anchor to bar:GetStatusBarTexture() and the engine moves them, so the
-- (secret) fill width never enters Lua.
function Helpers.CreateLaserRail(parent, spec)
    local shell = CreateFrame("Frame", nil, parent)
    shell:SetHeight(spec.coreHeight)

    local trackLeft = shell:CreateTexture(nil, "BACKGROUND")
    trackLeft:SetTexture(RAIL_FLAT_TEXTURE)
    trackLeft:SetHeight(spec.coreHeight)
    trackLeft:SetPoint("LEFT", shell, "LEFT", 0, 0)
    trackLeft:SetPoint("RIGHT", shell, "CENTER", 0, 0)
    local trackRight = shell:CreateTexture(nil, "BACKGROUND")
    trackRight:SetTexture(RAIL_FLAT_TEXTURE)
    trackRight:SetHeight(spec.coreHeight)
    trackRight:SetPoint("LEFT", shell, "CENTER", 0, 0)
    trackRight:SetPoint("RIGHT", shell, "RIGHT", 0, 0)

    local bar = CreateFrame("StatusBar", nil, shell)
    bar:SetFrameLevel(shell:GetFrameLevel() + 1)
    bar:SetHeight(spec.coreHeight)
    bar:SetPoint("LEFT", shell, "LEFT", 0, 0)
    bar:SetPoint("RIGHT", shell, "RIGHT", 0, 0)
    bar:SetStatusBarTexture(RAIL_FLAT_TEXTURE)
    bar:SetMinMaxValues(0, 1)
    bar:SetValue(0)
    bar.shell = shell
    local fill = bar:GetStatusBarTexture()

    -- Bloom and spark share one host so a single alpha hides both at empty.
    local host = CreateFrame("Frame", nil, shell)
    host:SetAllPoints(shell)
    host:SetFrameLevel(bar:GetFrameLevel() + 2)

    -- glow_edge is bright at v=0; the default coords put the bright side at the
    -- strip's top (the bottom bloom touches the core), the flipped coords at its
    -- bottom (the top bloom), the same orientations Theme.AddOuterGlow uses.
    local bloomTop = host:CreateTexture(nil, "ARTWORK")
    bloomTop:SetTexture(RAIL_GLOW_EDGE_TEXTURE)
    bloomTop:SetPoint("BOTTOMLEFT", fill, "TOPLEFT", 0, 0)
    bloomTop:SetPoint("BOTTOMRIGHT", fill, "TOPRIGHT", 0, 0)
    bloomTop:SetHeight(spec.bloomSize)
    bloomTop:SetTexCoord(0, 1, 0, 0, 1, 1, 1, 0)
    bloomTop:SetBlendMode("ADD")
    local bloomBottom = host:CreateTexture(nil, "ARTWORK")
    bloomBottom:SetTexture(RAIL_GLOW_EDGE_TEXTURE)
    bloomBottom:SetPoint("TOPLEFT", fill, "BOTTOMLEFT", 0, 0)
    bloomBottom:SetPoint("TOPRIGHT", fill, "BOTTOMRIGHT", 0, 0)
    bloomBottom:SetHeight(spec.bloomSize)
    bloomBottom:SetBlendMode("ADD")

    local spark = host:CreateTexture(nil, "OVERLAY")
    spark:SetTexture(RAIL_GLOW_ROUND_TEXTURE)
    spark:SetSize(spec.sparkWidth, spec.sparkHeight)
    spark:SetPoint("CENTER", fill, "RIGHT", 0, 0)
    spark:SetBlendMode("ADD")

    bar.fsRail = {
        trackLeft = trackLeft, trackRight = trackRight, host = host,
        bloomTop = bloomTop, bloomBottom = bloomBottom, spark = spark,
        desaturated = false,
        desatTextures = { fill, spark, bloomTop, bloomBottom },
        tailAlpha = spec.tailAlpha or Helpers.RAIL_TAIL_ALPHA,
        trackAlpha = spec.trackAlpha or Helpers.RAIL_TRACK_ALPHA,
        bloomAlpha = spec.bloomAlpha or Helpers.RAIL_BLOOM_ALPHA,
        sparkAlpha = spec.sparkAlpha or Helpers.RAIL_SPARK_ALPHA,
    }

    if spec.styleText then
        -- Above the glow host (bar + 2) so the value reads over bloom and spark.
        local textHost = CreateFrame("Frame", nil, shell)
        textHost:SetAllPoints(bar)
        textHost:SetFrameLevel(host:GetFrameLevel() + 1)
        local text = textHost:CreateFontString(nil, "OVERLAY", nil, 7)
        text:SetPoint("CENTER", bar, "CENTER", 0, 0)
        spec.styleText(text)
        bar.text = text
    end

    Helpers.SetLaserRailColor(bar, spec.color[1], spec.color[2], spec.color[3])
    return bar
end

-- Re-applies every size CreateLaserRail baked from its spec, for a caller that
-- rescales (CreateLaserRail's literals are scaled pixels and do not follow a UI
-- Scale change by themselves). Same four arguments as the spec's coreHeight,
-- bloomSize, sparkWidth, sparkHeight. Sets exactly the regions and values
-- CreateLaserRail sized; the width-less anchors are untouched. Party never
-- calls this, its rails are built once at fixed design size.
function Helpers.SetLaserRailSize(bar, coreHeight, bloomSize, sparkWidth, sparkHeight)
    local rail = bar.fsRail
    bar.shell:SetHeight(coreHeight)
    rail.trackLeft:SetHeight(coreHeight)
    rail.trackRight:SetHeight(coreHeight)
    bar:SetHeight(coreHeight)
    rail.bloomTop:SetHeight(bloomSize)
    rail.bloomBottom:SetHeight(bloomSize)
    rail.spark:SetSize(sparkWidth, sparkHeight)
end

-------------------------------------------------------------------------------
-- Level/rank chip (small rounded chip + centered Orbitron number)
-------------------------------------------------------------------------------

-- Shared shape behind UnitFrames' CreateLevelBadge and PartyFrames'
-- CreatePartyLevelChip: outward glow + cut (or, under "round", rounded) fill + 1px
-- border at the chamfer Theme.CutSize(opts.height) (Theme.LEVEL_RADIUS under
-- "round"), Orbitron text centered on it. The two originals
-- differed only in chip size (UnitFrames' badge is bigger, sitting in the
-- unit-frame name row) and UnitFrames' stronger drop-shadow on the number.
--
-- opts: width, height (both required), shadowOffset = {x, y} to override the
-- default 1,-1 drop shadow Theme.ApplyFontGeneric applies (nil keeps it).
--
-- Returns the chip Frame; chip.text is the centered FontString.
function Helpers.CreateLevelChip(parent, opts)
    local chip = CreateFrame("Frame", nil, parent)
    chip:SetSize(opts.width, opts.height)

    local bc = Theme.COLOR_BORDER
    local radius = IsCut() and Theme.CutSize(opts.height) or Theme.LEVEL_RADIUS
    Theme.AddOuterGlow(chip, bc[1], bc[2], bc[3], 4, 0.38, radius)
    Theme.AddRoundedFill(chip, { Theme.COLOR_BG[1], Theme.COLOR_BG[2], Theme.COLOR_BG[3], 0.95 }, radius)
    Theme.AddGradientBorder(chip, bc, 1, radius)

    local text = chip:CreateFontString(nil, "OVERLAY")
    text:SetPoint("CENTER", chip, "CENTER", 0, 0)
    text:SetJustifyH("CENTER")
    text:SetJustifyV("MIDDLE")
    Theme.ApplyFontGeneric(text, Theme.FONT_ORBITRON, 11, bc)
    if opts.shadowOffset then
        text:SetShadowOffset(opts.shadowOffset[1], opts.shadowOffset[2])
    end
    chip.text = text

    return chip
end

-------------------------------------------------------------------------------
-- Aura-slot reader
-------------------------------------------------------------------------------

local HAS_C_UNITAURAS = type(C_UnitAuras) == "table" and type(C_UnitAuras.GetAuraDataByIndex) == "function"

-- Reads one aura slot via C_UnitAuras.GetAuraDataByIndex (modern engine) or
-- the positional UnitAura fallback, normalized to ONE shape covering every
-- field either of this addon's two callers reads (PartyFrames wants
-- name/dispelType/caster for cleanse-matching and the maintenance-buff scan;
-- Buffs wants name/icon/count/dispelType/duration/expirationTime for the
-- icon display; ForeverSTUwave's nameplates also read nameplateShowPersonal).
-- Returns nil on a refused/failed/empty read.
--
-- Does NOT tag the result with index/filter, and does NOT rename any field
-- to a caller-specific name (e.g. PartyFrames' `expiration` vs this table's
-- `expirationTime`) -- callers already have index/filter as call arguments
-- and build their own returned shape from this one, same as before.
--
-- `report(label, err)` is the caller's own reporter (RunStep's ReportOnce,
-- or an ad-hoc one), so each module's message wording/dedup is preserved.
function Helpers.ReadAuraSlot(unit, index, filter, report)
    if not FS.AurasReadable() then return nil end

    if HAS_C_UNITAURAS then
        local ok, data = pcall(C_UnitAuras.GetAuraDataByIndex, unit, index, filter)
        if not ok then
            report("read aura (C_UnitAuras)", data)
            return nil
        end
        if not data then return nil end
        return {
            name = data.name,
            icon = data.icon,
            count = data.applications or 0,
            dispelType = data.dispelName,
            duration = data.duration or 0,
            expirationTime = data.expirationTime or 0,
            caster = data.sourceUnit,
            -- Only the C_UnitAuras data carries this (Blizzard's nameplate
            -- own-aura flag); nil on the legacy UnitAura path. May be secret.
            nameplateShowPersonal = data.nameplateShowPersonal,
            -- Lets a caller ask C_Spell.IsSpellCrowdControl; nil on the legacy
            -- path. May be secret.
            spellId = data.spellId,
            -- Blizzard's other crowd control route (IsAuraCrowdControl): the
            -- aura is flagged to show for everyone. nil on the legacy path.
            -- May be secret.
            nameplateShowAll = data.nameplateShowAll,
        }
    end

    -- Positional order: name, icon, count, dispelType, duration,
    -- expirationTime, source (caster) -- do not reorder these locals.
    local ok, name, icon, count, dispelType, duration, expirationTime, caster = pcall(UnitAura, unit, index, filter)
    if not ok then
        report("read aura (UnitAura)", name)
        return nil
    end
    if not name then return nil end
    return {
        name = name,
        icon = icon,
        count = count or 0,
        dispelType = dispelType,
        duration = duration or 0,
        expirationTime = expirationTime or 0,
        caster = caster,
    }
end

-------------------------------------------------------------------------------
-- Aura tooltip OnEnter (lockdown fallback + dispatch)
-------------------------------------------------------------------------------

local HAS_TOOLTIP_SETUNITAURA = type(GameTooltip) == "table" and type(GameTooltip.SetUnitAura) == "function"
local HAS_TOOLTIP_SETUNITDEBUFF = type(GameTooltip) == "table" and type(GameTooltip.SetUnitDebuff) == "function"
local HAS_TOOLTIP_SETUNITBUFF = type(GameTooltip) == "table" and type(GameTooltip.SetUnitBuff) == "function"

-- Plain-value validators for the cached tooltip fields. IsSecret first: nothing
-- else may touch a secret (type() is the only call that never throws on one).
local function ValidSpellID(v)
    return not IsSecret(v) and type(v) == "number" and v > 0
end

local function ValidName(v)
    return not IsSecret(v) and type(v) == "string" and v ~= ""
end

-- Fills GameTooltip with the spell's own tooltip. SetSpellByID is not an aura
-- read, so it should work in combat, but that is unverified on this client:
-- feature-detected at call time and pcall'd, and false tells the caller to fall
-- back to the cached name.
local function ShowSpellByID(spellID)
    if type(GameTooltip) ~= "table" or type(GameTooltip.SetSpellByID) ~= "function" then return false end
    if not pcall(GameTooltip.SetSpellByID, GameTooltip, spellID) then return false end
    GameTooltip:Show()
    return true
end

-- Shared OnEnter body for an aura icon showing (self.unit, self.auraIndex,
-- self.filter): the normal tooltip dispatch (SetUnitAura, falling back to
-- the filter-specific SetUnitDebuff/SetUnitBuff setter), or the cached
-- self.fsSpellID's spell tooltip (else self.fsName plus a "Details unavailable
-- in combat" line) when aura reads are refused. The tooltip setters ARE aura reads wearing a different hat,
-- so they refuse identically under combat lockdown -- see Buffs.lua's
-- original AuraButton_OnEnter comment for the exact error this avoids.
--
-- CORRECTNESS FIX folded into this extraction: the HELPFUL/SetUnitBuff
-- branch was PRESENT in Buffs' copy but MISSING from PartyFrames' copy, even
-- though PartyFrames' alert icons can carry filter="HELPFUL" (the
-- maintenance-buff alert) -- on a client with SetUnitBuff but not
-- SetUnitAura, that alert showed no tooltip at all. Unifying the dispatch
-- here means both callers now get all three branches.
--
-- `enchantFallback(self)` is an optional extra branch tried when there is no
-- self.auraIndex (Buffs' weapon-enchant icons, which have no aura index and
-- fall through to GameTooltip:SetInventoryItem instead); PartyFrames has no
-- such icons and passes nil.
-- The live-slot half of ShowAuraTooltip: true when a tooltip was filled, false when the slot
-- is gone or refused (a stale index) or no setter exists. Never hides the tooltip itself.
local function TryAuraSlot(self, enchantFallback)
    local shown = false
    if self.auraIndex and self.unit then
        if HAS_TOOLTIP_SETUNITAURA then
            shown = pcall(GameTooltip.SetUnitAura, GameTooltip, self.unit, self.auraIndex, self.filter)
        elseif self.filter == "HARMFUL" and HAS_TOOLTIP_SETUNITDEBUFF then
            shown = pcall(GameTooltip.SetUnitDebuff, GameTooltip, self.unit, self.auraIndex)
        elseif self.filter == "HELPFUL" and HAS_TOOLTIP_SETUNITBUFF then
            shown = pcall(GameTooltip.SetUnitBuff, GameTooltip, self.unit, self.auraIndex)
        end
    elseif enchantFallback then
        shown = enchantFallback(self)
    end
    return shown
end

function Helpers.ShowAuraTooltip(self, enchantFallback)
    if self.auraIndex and not FS.AurasReadable() then
        -- Cached spell id first (SetTipSpell): the spell's real tooltip, no aura read.
        if ValidSpellID(self.fsSpellID) and ShowSpellByID(self.fsSpellID) then return end
        if self.fsName then
            GameTooltip:SetText(self.fsName)
            GameTooltip:AddLine("Details unavailable in combat.", 0.6, 0.6, 0.6)
            GameTooltip:Show()
        else
            GameTooltip:Hide()
        end
        return
    end

    if not TryAuraSlot(self, enchantFallback) then GameTooltip:Hide() end
end

-------------------------------------------------------------------------------
-- Spell tooltips for icon surfaces (hover-only, cached, combat-safe)
-------------------------------------------------------------------------------

-- Hover, no clicks: a centre-HUD icon must pass clicks through (a click-taking frame
-- there would block right-click-drag mouselook and left-click targeting that start
-- over it), so this is motion-only and never EnableMouse(true). Each call is
-- feature-detected and pcall'd; where the client lacks either call there is no mouse
-- at all (no tooltip) rather than a click-eating icon. Call at BUILD time only: the
-- mouse state is never toggled in combat (the Gunsight root parents a protected button).
function Helpers.HoverOnly(frame)
    if type(frame.SetMouseMotionEnabled) ~= "function" or type(frame.SetMouseClickEnabled) ~= "function" then return end
    pcall(frame.SetMouseClickEnabled, frame, false)
    pcall(frame.SetMouseMotionEnabled, frame, true)
end

-- Caches what the tooltip needs on the frame: fsSpellID (a plain number > 0) and fsName
-- (a plain non-empty string). Anything else, secret included, CLEARS that field, so a
-- secret is never stored. Allocation-free: safe to call every tick. When the frame is
-- hovered and the id or name changed, the open tooltip is redrawn.
-- WARNING: SealBar.lua uses button.fsSpellID as its own business data (cooldown and
-- tooltip source), and SetTipSpell would clear it. Never attach this helper to SealBar
-- buttons.
function Helpers.SetTipSpell(frame, spellID, name)
    local id = ValidSpellID(spellID) and spellID or nil
    local nm = ValidName(name) and name or nil
    local oldName = frame.fsName
    -- A secret fsName written by other code cannot be compared; it counts as changed.
    local changed = frame.fsSpellID ~= id or IsSecret(oldName) or oldName ~= nm
    frame.fsSpellID, frame.fsName = id, nm
    if changed and frame.fsHover then Helpers.RefreshSpellTooltip(frame) end
end

-- Spell id for a spell name. C_Spell.GetSpellInfo(name) resolves names in combat; the global
-- GetSpellInfo is the fallback on a client without C_Spell. Three caches, all dropped together:
--   * a hit (name -> id) and a miss out of combat (name -> false) are kept until SPELLS_CHANGED, which
--     wipes the lot (a new rank trained or a spell learned shows up). Fired in combat, the wipe is owed to
--     PLAYER_REGEN_ENABLED (no allocation or churn mid fight);
--   * a miss IN combat is not trusted (the lookup may fail transiently, a secret or withheld result), so it
--     is not kept as a miss for good; it is remembered for the rest of that combat only, so a render per tick
--     does not repeat the lookup (a pcall and a result table each time). Cleared at PLAYER_REGEN_ENABLED and
--     on SPELLS_CHANGED.
-- SpellCacheEpoch() moves on every wipe, so a caller that caches what these return can tell it went stale.
local spellIDByName = {}
local combatMisses = {}
local cacheDirty = false
local cacheEpoch = 0

local function ClearTable(t)
    for k in pairs(t) do t[k] = nil end
end

-- Made on the first cached lookup, not at load: nothing to wipe until then, and a frame registered at load
-- would sit ahead of every module's own SPELLS_CHANGED listener.
local spellsEvents
local function WatchSpellsChanged()
    if spellsEvents then return end
    spellsEvents = CreateFrame("Frame")
    pcall(spellsEvents.RegisterEvent, spellsEvents, "SPELLS_CHANGED")
    pcall(spellsEvents.RegisterEvent, spellsEvents, "PLAYER_REGEN_ENABLED")
    spellsEvents:SetScript("OnEvent", function(_, event)
        ClearTable(combatMisses)
        if event == "SPELLS_CHANGED" then
            if InCombatLockdown() then
                cacheDirty = true
                return
            end
        elseif not cacheDirty then
            return
        end
        ClearTable(spellIDByName)
        cacheDirty = false
        cacheEpoch = cacheEpoch + 1
    end)
end

function Helpers.SpellCacheEpoch()
    return cacheEpoch
end

function Helpers.SpellIDForName(name)
    if not ValidName(name) then return nil end
    local cached = spellIDByName[name]
    if cached then return cached end
    if cached == false or combatMisses[name] then return nil end
    local id
    if type(C_Spell) == "table" and type(C_Spell.GetSpellInfo) == "function" then
        local ok, info = pcall(C_Spell.GetSpellInfo, name)
        if ok and type(info) == "table" and not IsSecret(info) then id = info.spellID end
    elseif type(GetSpellInfo) == "function" then
        local ok, _, _, _, _, _, _, spellID = pcall(GetSpellInfo, name)
        if ok then id = spellID end
    end
    WatchSpellsChanged()
    if ValidSpellID(id) then
        spellIDByName[name] = id
        return id
    end
    if InCombatLockdown() then
        combatMisses[name] = true
    else
        spellIDByName[name] = false
    end
    return nil
end

local function OwnsTooltip(frame)
    if type(GameTooltip) ~= "table" then return false end
    if type(GameTooltip.IsOwned) == "function" then return GameTooltip:IsOwned(frame) and true or false end
    return type(GameTooltip.GetOwner) == "function" and GameTooltip:GetOwner() == frame
end

-- Takes the tooltip down if this frame has it; clears the hover flag. Public: a frame that hides or
-- is gated off under the cursor gets no OnLeave of its own.
local function ReleaseSpellTip(frame)
    frame.fsHover = nil
    if OwnsTooltip(frame) then GameTooltip:Hide() end
end
Helpers.ReleaseSpellTip = ReleaseSpellTip

-- Takes the tooltip down when its owner is an AttachSpellTooltip frame whose gate now says no. For the
-- listener of a switch that hides icons without an OnLeave (the Gunsight master switch, off in combat:
-- the root only fades, so the icon stays "hovered" under an invisible plate).
function Helpers.ReleaseGatedTips()
    if type(GameTooltip) ~= "table" or type(GameTooltip.GetOwner) ~= "function" then return end
    local owner = GameTooltip:GetOwner()
    local opts = type(owner) == "table" and owner.fsSpellTip
    if type(opts) ~= "table" or type(opts.gate) ~= "function" then return end
    local ok, open = pcall(opts.gate, owner)
    if not ok or not open then ReleaseSpellTip(owner) end
end

-- The OnEnter body (also the refresh): the first branch that applies wins.
local function ShowSpellTip(frame, opts)
    if type(GameTooltip) ~= "table" then return end
    if opts.gate and not opts.gate(frame) then
        if OwnsTooltip(frame) then GameTooltip:Hide() end
        return
    end
    GameTooltip:SetOwner(frame, opts.anchor or "ANCHOR_TOP")
    -- a. a live aura slot, while the client lets us read it. A stale or refused slot falls
    -- through to the cached spell rather than hiding a tooltip we can still draw.
    if frame.unit and frame.auraIndex and frame.filter and FS.AurasReadable() then
        local ok, shown = pcall(TryAuraSlot, frame)
        if ok and shown then return end
    end
    -- b. the spell's own tooltip from the cached id.
    if ValidSpellID(frame.fsSpellID) and ShowSpellByID(frame.fsSpellID) then return end
    -- c. the cached name; in combat, say why there is no more.
    if ValidName(frame.fsName) then
        GameTooltip:SetText(frame.fsName)
        if InCombatLockdown() then GameTooltip:AddLine("Details unavailable in combat.", 0.6, 0.6, 0.6) end
        GameTooltip:Show()
        return
    end
    -- d. nothing to show.
    GameTooltip:Hide()
end

-- Gives `frame` a tooltip from what SetTipSpell cached (or, out of combat, its aura slot).
-- Installs once per frame (HookScript, so the frame's own handlers are untouched).
--   opts.anchor  tooltip anchor, default "ANCHOR_TOP"
--   opts.clicks  true if the frame takes clicks and the caller owns its mouse state
--   opts.gate    function(frame); returning false suppresses the tooltip
function Helpers.AttachSpellTooltip(frame, opts)
    if frame.fsSpellTip then return end
    opts = opts or {}
    frame.fsSpellTip = opts
    if not opts.clicks then Helpers.HoverOnly(frame) end
    frame:HookScript("OnEnter", function(self)
        self.fsHover = true
        ShowSpellTip(self, opts)
    end)
    frame:HookScript("OnLeave", ReleaseSpellTip)
    frame:HookScript("OnHide", ReleaseSpellTip)
end

-- Redraws the tooltip if the frame is hovered and still owns it (the cursor stays put
-- while the icon underneath changes).
function Helpers.RefreshSpellTooltip(frame)
    local opts = frame.fsSpellTip
    if not (opts and frame.fsHover and OwnsTooltip(frame)) then return end
    ShowSpellTip(frame, opts)
end

-------------------------------------------------------------------------------
-- Button cooldown swipe
-------------------------------------------------------------------------------

-- Blizzard's own swipe is black at 0.64 (<SwipeTexture><Color r="0" g="0" b="0"
-- a="0.64"/> in CooldownFrameTemplate and ActionButtonTemplate).
local COOLDOWN_SWIPE_ALPHA = 0.64

-- Seats `button.icon` inside a two-corner cut button (top-left and bottom-right
-- chamfered): inset-only, no mask.
--
-- The icon is inset ceil(c / 2) on every side, c being the button's chamfer: the
-- chamfer Theme.SkinButton recorded in button.fsSkin.chamfer (chosen from the button
-- height, 2 / 3 / 4 / 6), else Theme.SLICE_CUT_MARGIN (6). CreateMaskTexture and
-- AddMaskTexture exist on this interface-16001 client but do NOT clip (verified in game
-- 2026-09-17: see the FILL_CORNER_TEXTURE note in Theme.lua and
-- notes/wow-classic-ui-kb/01-versions-and-api-matrix.md), and Lua cannot tell a
-- clipping mask from a dead one, so no mask is created: it would be a dead region on
-- every one of 72+ buttons. The outer cut line is x + y = c from the button's corner;
-- an inset of ceil(c / 2) puts the icon's corner at (i, i) with 2i >= c, on or inside
-- that line, where the border stroke hides it (c = 6 -> 3, the original fixed inset,
-- so the action, stance and pet bars are unchanged). At the old 1px inset the corner sat
-- at (1, 1) and poked past a 6 chamfer.
--
-- (media/mask_cut2_square.tga, Theme.MASK_CUT2_SQUARE_TEXTURE and
-- SeatButtonCooldown's opts.swipeTexture are kept for a client where masks clip;
-- all three are unused while they do not.)
local DEFAULT_CUT_CHAMFER = 6

function Helpers.SeatCutIcon(button)
    local icon = button.icon
    if not icon then return end

    local skin = button.fsSkin
    local chamfer = (skin and skin.chamfer) or (Theme and Theme.SLICE_CUT_MARGIN) or DEFAULT_CUT_CHAMFER
    local inset = math.ceil(chamfer / 2)

    icon:ClearAllPoints()
    icon:SetPoint("TOPLEFT", button, "TOPLEFT", inset, -inset)
    icon:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", -inset, inset)
end

-- Dark label plate colour, the action button keybind plate's (rgba(6,3,18,.78)).
local LABEL_PLATE = { 0.024, 0.012, 0.071, 0.78 }

-- One dark plate behind `fontString`, on the button so it draws above the icon (ARTWORK) and the
-- border ring (OVERLAY 1) and below the text (OVERLAY 4). Hidden until Helpers.SetAuraLabel gives
-- the label text; auto-sized to the glyphs, so it hugs "3m" as well as "22m".
local function AddLabelPlate(button, fontString, anchor, x, y)
    fontString:ClearAllPoints()
    fontString:SetPoint(anchor, button.icon, anchor, x, y)
    fontString:SetDrawLayer("OVERLAY", 4)
    local plate = button:CreateTexture(nil, "OVERLAY", nil, 3)
    plate:SetColorTexture(LABEL_PLATE[1], LABEL_PLATE[2], LABEL_PLATE[3], LABEL_PLATE[4])
    plate:SetPoint("TOPLEFT", fontString, "TOPLEFT", -2, 0)
    plate:SetPoint("BOTTOMRIGHT", fontString, "BOTTOMRIGHT", 2, 0)
    plate:Hide()
    fontString.fsPlate = plate
end

-- Finishes an aura tile (player buffs/debuffs, target auras) the way the action buttons are
-- finished: a cut2 plate behind the icon so the gap between icon and 1 texel border stroke is
-- dark plate instead of see-through (that gap is what read as a hollow outline), the icon seated
-- by SeatCutIcon and cropped 0.07 like the action buttons, and a dark plate behind the stack
-- count (top right) and the duration (bottom right) so white text stays legible on any icon.
-- Call after Theme.SkinButton (needs button.fsSkin.chamfer). Both label corners sit inside the
-- chamfer line: the plate corner is at icon inset + 1 on each axis, 2 * (inset + 1) > chamfer.
function Helpers.SeatAuraTile(button)
    if not (button and button.icon) then return end
    local skin = button.fsSkin
    local c = (skin and skin.chamfer) or DEFAULT_CUT_CHAMFER

    if not button.fsAuraPlate then
        local path = Theme.SLICE_CUT2_BUTTON_TEXTURE
        if c ~= 6 then
            path = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\slice_cut2_button_c" .. c .. ".tga"
        end
        local plate = Theme.AddSliceTexture(button, path, { 1, 1, 1, 1 }, "BACKGROUND", -8)
        Theme.ApplyNineSlice(plate, c)
        button.fsAuraPlate = plate
    end

    Helpers.SeatCutIcon(button)
    button.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)

    -- Vertical offset of both plates from their icon corner. The count plate is about 10 units
    -- tall and the duration plate about 9, so with a 1 unit gap between them they need 20 icon
    -- rows; 2 more for a 1 unit margin at each corner makes 22. A 24 tile has a 20 row icon
    -- (inset 2), so there both plates sit flush (0), leaving 20 - 19 = 1 unit between them; a 32
    -- tile (28 rows) keeps the 1 unit margin. Flush stays inside the chamfer: the duration plate
    -- corner is inset + 1 from the right and inset from the bottom, 2 * inset + 1 > chamfer.
    local iconH = (button:GetHeight() or 0) - 2 * math.ceil(c / 2)
    local pad = (iconH >= 22 or iconH <= 0) and 1 or 0
    if button.count and not button.count.fsPlate then
        AddLabelPlate(button, button.count, "TOPRIGHT", -3, -pad)
    end
    if button.duration and not button.duration.fsPlate then
        AddLabelPlate(button, button.duration, "BOTTOMRIGHT", -3, pad)
    end
end

-- Sets an aura label's text and shows its plate only while there is text, so an empty label
-- leaves no dark sliver. `text` nil or "" clears it.
function Helpers.SetAuraLabel(fontString, text)
    -- A 12.0 secret string cannot be compared (text ~= "" throws), so treat it as non-empty.
    if issecretvalue and issecretvalue(text) then
        fontString:SetText(text)
        if fontString.fsPlate then fontString.fsPlate:Show() end
        return
    end
    local has = text ~= nil and text ~= ""
    fontString:SetText(has and text or "")
    local plate = fontString.fsPlate
    if plate then
        if has then plate:Show() else plate:Hide() end
    end
end

-- Seats `button.cooldown` over the button's ICON, edge to edge, and fixes its
-- draw flags.
--
-- Why this exists (Parker: "the GCD ... covers the button and doesn't extend to
-- the edge"): ActionButtonTemplate anchors its cooldown to the icon with a 3px
-- inset on every side (ActionButtonTemplate.xml, the <Cooldown ... parentKey=
-- "cooldown"> block: TOPLEFT +3,-3 / BOTTOMRIGHT -3,3 relative to the icon).
-- That inset is authored for Blizzard's 45px button and is a fixed pixel count,
-- so on our ~37px button, whose icon is already 1px inside the border, the swipe
-- stopped 4px short of the border all the way round. Nothing in StyleButton
-- ever re-anchored it, so the template's anchors survived untouched.
--
-- Anchored to the ICON rather than the button because the icon is the visible
-- face: it sits exactly inside the 1px border ring, so a swipe the same size as
-- the icon covers the whole face without painting over the border or the glow,
-- which are outside that rectangle and keep drawing under their own OVERLAY
-- layers untouched. (The template's cooldown frame is a child at the button's
-- own level, so it draws above the button's regions; confining it to the icon
-- rectangle is what keeps it off the border, rather than a frame-level trick.)
--
-- opts.swipeTexture: texture path to sample for the swipe (a Cooldown draws its swipe
-- by sampling this texture, so the shape in its alpha is the swipe's shape; a Cooldown
-- cannot take a MaskTexture). Meant for an icon that a mask really clips, with
-- Theme.MASK_CUT2_SQUARE_TEXTURE (mask_cut2_square.tga). No caller passes it today:
-- masks do not clip on this client (SeatCutIcon), so the icon is square and the swipe
-- must be too. Leave it nil for a square swipe: a shaped swipe over a square icon
-- leaves undimmed icon corners showing.
--
-- Edge and bling are switched off to match Blizzard's own action button
-- (drawBling="false" drawEdge="false" in that same template block): the edge is
-- a bright line along the sweep and the bling a flash at the end, neither of
-- which belongs on a GCD sweep over a bar of twelve buttons.
--
-- The template's two other cooldown frames, `lossOfControlCooldown` (a stun's
-- swipe) and `chargeCooldown` (a recharge's countdown and edge), carry the same
-- fixed inset (3px and 2px respectively, same XML) and are re-seated to the same
-- rectangle when the button has them, or a stun would still stop short of the
-- edge. Each otherwise keeps what Blizzard set: draw flags and edge texture are
-- untouched (the loss-of-control edge is its own art, and the charge cooldown
-- draws no swipe at all, so there is nothing to shape or colour on it). The one
-- change is the loss-of-control SWIPE: its colour is always set to the template's own
-- dark red (0.17, 0, 0, 0.64), not the GCD's black, so we never rely on the 16001
-- template supplying it (and a texture call under opts.swipeTexture resets the
-- colour, so it must follow). That colour is copied from ActionButtonTemplate.xml
-- (retail 12.1); the 16001 template is not in the reference tree, so a different red
-- there is overwritten by this one. Under opts.swipeTexture the loss-of-control swipe
-- also takes that texture so it does not poke past the icon's corners.
local LOSS_OF_CONTROL_SWIPE = { 0.17, 0, 0, COOLDOWN_SWIPE_ALPHA }

function Helpers.SeatButtonCooldown(button, opts)
    local cooldown, icon = button.cooldown, button.icon
    if not (cooldown and icon) then return end
    opts = opts or {}

    cooldown:ClearAllPoints()
    cooldown:SetAllPoints(icon)

    -- Not an ipairs over the two: a missing first one would end the loop.
    local loc, charge = button.lossOfControlCooldown, button.chargeCooldown
    if charge then charge:ClearAllPoints(); charge:SetAllPoints(icon) end
    if loc then
        loc:ClearAllPoints(); loc:SetAllPoints(icon)
        if opts.swipeTexture and loc.SetSwipeTexture then
            loc:SetSwipeTexture(opts.swipeTexture)
        end
        -- Always, after any texture call (which resets the colour).
        if loc.SetSwipeColor then loc:SetSwipeColor(unpack(LOSS_OF_CONTROL_SWIPE)) end
    end

    if cooldown.SetDrawEdge then cooldown:SetDrawEdge(false) end
    if cooldown.SetDrawBling then cooldown:SetDrawBling(false) end

    if opts.swipeTexture and cooldown.SetSwipeTexture then
        cooldown:SetSwipeTexture(opts.swipeTexture)
    end
    -- Always, after the texture: whichever texture is in use must still be
    -- black at 0.64, and SetSwipeTexture's own colour arguments are optional.
    if cooldown.SetSwipeColor then
        cooldown:SetSwipeColor(0, 0, 0, COOLDOWN_SWIPE_ALPHA)
    end
end

-------------------------------------------------------------------------------
-- Button text above the swipe
-------------------------------------------------------------------------------

-- A swipe that covers the whole button face (SeatButtonCooldown) would dim any
-- keybind or count text drawn UNDER it. Text drawn directly on a button is: the
-- Cooldown is a child frame, and a child frame draws above its parent's own
-- regions whatever their draw layer. Returns the frame the given text regions
-- (and any plate texture the caller wants behind them) must live on.
--
-- KNOWN, from the retail 12.1 reference tree: ActionButtonTemplate.xml already
-- keeps HotKey, Count and Name in a `TextOverlayContainer` child at frameLevel
-- 500, far above the cooldown, so on a button that has it nothing needs moving.
-- Moving them to a host of our own would even be a step down: the host sits just
-- one level over the cooldown, which can be under other overlays (the
-- AutoCastOverlay) the container stays above.
--
-- UNVERIFIED for 16001: whether this client's ActionButtonTemplate has the
-- container at all (the 16001 template is not in the reference tree; the dump
-- only lists its mixin, ActionButtonTextOverlayContainerMixin) and at what
-- level. So it is feature-detected: a `TextOverlayContainer` whose frame level is
-- above the cooldown's is used as is; anything else (no container, a lower one,
-- or the bare SecureActionButtonTemplate buttons of the stance and pet bars,
-- which have none) gets one click-through host frame a level above whichever is
-- higher, the button or its cooldown. Click-through because a mouse-enabled
-- child would take the hover and the click from the secure button underneath.
--
-- Call after SeatButtonCooldown. Text regions already on the returned frame stay
-- where they are; the others are re-parented to it (their anchors, which are
-- relative to the button, are unaffected).
function Helpers.SeatButtonText(button, ...)
    local container, cooldown = button.TextOverlayContainer, button.cooldown
    local host
    if container and container.GetFrameLevel and cooldown
        and container:GetFrameLevel() > cooldown:GetFrameLevel() then
        host = container
    else
        host = button.fsTextHost
        if not host then
            host = CreateFrame("Frame", nil, button)
            host:SetAllPoints(button)
            host:EnableMouse(false)
            button.fsTextHost = host
        end
        local cooldownLevel = cooldown and cooldown:GetFrameLevel() or 0
        host:SetFrameLevel(math.max(button:GetFrameLevel(), cooldownLevel) + 1)
    end
    for i = 1, select("#", ...) do
        local region = select(i, ...)
        if region and region:GetParent() ~= host then region:SetParent(host) end
    end
    return host
end

-- Mouse labels use raw binding tokens so localization cannot change their identity.
-- Keyboard and gamepad labels keep Blizzard's abbreviated text.
local MOUSE_MODIFIER_TEXT = { SHIFT = "S-", CTRL = "C-", ALT = "A-" }
function Helpers.FormatBindingText(key)
    if not key or key == "" then return "" end
    local modifiers, number = key:match("^(.-)BUTTON(%d+)$")
    if not number then return GetBindingText(key, 1) end

    local prefix = ""
    while modifiers ~= "" do
        local modifier, rest = modifiers:match("^(%a+)%-(.*)$")
        local text = modifier and MOUSE_MODIFIER_TEXT[modifier]
        if not text then return GetBindingText(key, 1) end
        prefix = prefix .. text
        modifiers = rest
    end
    return prefix .. (number == "3" and "MM" or "MB" .. number)
end

-------------------------------------------------------------------------------
-- Quick Keybind support
-------------------------------------------------------------------------------

-- Blizzard's Quick Keybind mode (Settings > Keybindings > Quick Keybind, or Edit
-- Mode) lets the player hover an action button and press a key, or click it with
-- a mouse button, to bind that button's command. Parker could not bind one of our
-- buttons to mouse button 4: it only works on buttons that take part in the mode,
-- and ours did not.
--
-- What a button must provide, read from Blizzard_QuickKeybind/QuickKeybind.lua
-- and Blizzard_ActionBar/Shared/ActionButton.lua (retail 12.1 reference tree; the
-- global names are all in the 16001 dump):
--
--   * `commandName`, the binding command, e.g. "MULTIACTIONBAR1BUTTON3". It is
--     the one thing the mode reads off a hovered button: OnEnter calls
--     QuickKeybindFrame:SetSelected(button.commandName, button), which starts
--     KeybindListener listening for that command, and the tooltip is built from
--     it. Without it hovering selects nothing, so no key can bind.
--   * the QuickKeybindButtonTemplateMixin methods. The frame calls back into the
--     hovered button (`mouseOverButton:QuickKeybindButtonSetTooltip()` from
--     QuickKeybindFrame:OnKeyDown), so they have to be on the button itself.
--   * the hover / click forwarding. Stock buttons inherit QuickKeybindButtonTemplate
--     and ActionBarActionButtonDerivedMixin calls QuickKeybindButtonOnEnter /
--     OnLeave / OnShow / OnHide / OnClick from its own handlers. Mouse buttons
--     are captured by the click: QuickKeybindButtonOnClick forwards any click
--     that is not Left or Right to QuickKeybindFrame:OnKeyDown(button), which
--     binds "BUTTON4" etc. Ours forward through HookScript instead, so the
--     secure OnClick of SecureActionButtonTemplate stays untouched.
--
-- Blizzard also keeps a click from casting while the mode is open: its derived
-- OnClick skips SecureActionButton_OnClick when KeybindFrames_InQuickKeybindMode()
-- is true (ActionBarActionButtonMixin:OnClick, StanceButtonMixin_OnClick; retail
-- 12.1 ActionButton.lua). That is a Lua branch inside Blizzard's own secure
-- handler, and an addon cannot do it: our buttons run the template's own secure
-- OnClick, and replacing it with an addon function would taint the cast.
--
-- The obvious stand-in, clearing the secure `type` attribute while the mode is
-- open, does not survive combat: SetAttribute is protected in combat, so closing
-- the mode mid-fight left every button unable to cast on a click until
-- PLAYER_REGEN_ENABLED (keybinds still worked). What is used instead is not an
-- attribute at all: each button gets an INSECURE child Button, the "overlay",
-- covering it and above everything on it, shown only while the mode is open. It
-- takes the mouse, so the secure button underneath never sees the click, and it
-- forwards hover, click and wheel to the stock handlers itself. Showing and
-- hiding an insecure frame is not restricted in combat: implicit protection
-- runs UP from a protected frame to its ancestors (see PetActionBar.lua's
-- header), not down to an ordinary child, and this is the same kind of child as
-- the cooldown and text host frames.
--
-- Research behind that choice, so it is not redone: Blizzard has no non-attribute
-- switch for this on stock buttons (the Lua branch above is the whole mechanism),
-- and the 16001 widget dump lists RegisterForClicks, EnableMouse,
-- SetMouseClickEnabled and SetPassThroughButtons by name only, with no
-- combat-protection information, so none of them could be relied on to be
-- callable on a secure button in combat. The overlay needs none of them on the
-- secure button.
--
-- UNVERIFIED in game on 16001 (see the CLAUDE.md checklist): that the overlay
-- really can be shown and hidden in combat. SyncQuickKeybindState asks
-- CanChangeProtectedState() (a Frame method in the 16001 dump) before touching
-- it, so if it ever answers no, nothing throws; the overlay then waits for
-- PLAYER_REGEN_ENABLED, which for a close in combat means bar clicks do nothing
-- for the rest of that fight (keybinds still work), and one chat line says so.
-- Everything else here is plain UI state. Blizzard has no explicit combat guard in
-- the mode itself (the binding calls simply fail in lockdown), so none is added
-- around the forwarding.
--
-- Bindings reach the action in a different way, and need nothing from us: the
-- canonical command (ACTIONBUTTON3, MULTIACTIONBAR1BUTTON3, BONUSACTIONBUTTONn,
-- SHAPESHIFTBUTTONn) is dispatched by the binding body in Bindings_Mists.xml to
-- Blizzard's own, now hidden, button for that slot (ActionButtonDown /
-- MultiActionButtonDown) or straight to CastPetAction / CastShapeshiftForm. So
-- binding the canonical name does fire the action, just not through our button.

local qkButtons = setmetatable({}, { __mode = "k" })  -- weak: a dropped button stops being tracked
local qkRefreshers = {}
local qkCallbackOwner = {}
local qkHooked = false
local qkPendingSync = false
local qkCombatNoticeShown = false
local qkWarned = false

-- Frame levels the overlay sits above its button. ActionButtonTemplate's
-- cooldowns use useParentLevel="true", so they sit at the button's own level;
-- only the stance and pet cooldowns, built with CreateFrame, sit at button + 1.
-- The text host sits above whichever cooldown applies. 20 clears both cases with
-- room, and only mouse-enabled siblings would matter anyway.
local QK_OVERLAY_LEVEL_OFFSET = 20

local function WarnQuickKeybindOnce(key, message)
    if qkWarned then return end
    qkWarned = true
    FS.LogDegradeOnce(key, "|cffff4488Forever STUwave|r: " .. message)
end

local function InQuickKeybindMode()
    return type(KeybindFrames_InQuickKeybindMode) == "function"
        and KeybindFrames_InQuickKeybindMode() and true or false
end

-- Calls a mixin method on the button if it exists. pcall'd: these run from
-- hover/click hooks, where a throw would repeat on every mouseover.
local function CallQuickKeybind(button, method, ...)
    local fn = button[method]
    if type(fn) ~= "function" then return end
    local ok, err = pcall(fn, button, ...)
    if not ok then
        WarnQuickKeybindOnce("quickkeybind_call",
            "Quick Keybind call " .. method .. " failed (" .. tostring(err) .. ")")
    end
end

local function RunQuickKeybindRefreshers()
    for _, refresh in ipairs(qkRefreshers) do
        local ok, err = pcall(refresh)
        if not ok then
            WarnQuickKeybindOnce("quickkeybind_refresh",
                "Quick Keybind hotkey refresh failed (" .. tostring(err) .. ")")
        end
    end
end

-- Whether the overlay may be shown or hidden right now. CanChangeProtectedState's
-- return is documented SecretReturnsForAspect=ObjectSecurity, and boolean-testing
-- a secret would throw inside the mode-close hook and leave the overlay up over
-- the bar. So the call is pcall'd and a failed call or a secret result counts as
-- "can change": the overlay is not a protected attribute write (see the section
-- header), so trying is the safe default.
local function OverlayCanChange(overlay)
    if not overlay.CanChangeProtectedState then return true end
    local ok, can = pcall(overlay.CanChangeProtectedState, overlay)
    if not ok or IsSecret(can) then return true end
    return can and true or false
end

-- Brings every attached button in line with whether the mode is open.
local function SyncQuickKeybindState()
    local inMode = InQuickKeybindMode()
    local deferred = false

    for button in pairs(qkButtons) do
        -- Highlight and mouse wheel: plain UI state, fine in combat.
        CallQuickKeybind(button, "DoModeChange", inMode)
        CallQuickKeybind(button, "UpdateMouseWheelHandler")

        -- The click-eating overlay. Not a protected attribute write; see the
        -- section header. Only a frame that says it cannot change right now is
        -- left for PLAYER_REGEN_ENABLED.
        local overlay = button.fsQuickKeybindOverlay
        if overlay and overlay:IsShown() ~= inMode then
            if not OverlayCanChange(overlay) then
                deferred = true
            else
                overlay:SetShown(inMode)
            end
        end
    end

    qkPendingSync = deferred
    if not deferred then
        qkCombatNoticeShown = false
    elseif not inMode and not qkCombatNoticeShown then
        qkCombatNoticeShown = true
        FS.LogDegradeOnce("quickkeybind_combat_close",
            "|cffff4488Forever STUwave|r: bar clicks resume after combat "
            .. "(Quick Keybind closed mid-fight); keybinds still work.")
    end
end

local function HookQuickKeybindFrame()
    if qkHooked then return true end
    local frame = _G.QuickKeybindFrame
    if not (frame and frame.HookScript) then return false end

    -- Post-hooks on the stock frame: they run after Blizzard's own OnShow/OnHide
    -- (which also drive ActionButtonUtil's highlight pass over Blizzard's
    -- buttons) and never replace them.
    frame:HookScript("OnShow", SyncQuickKeybindState)
    frame:HookScript("OnHide", function()
        SyncQuickKeybindState()
        RunQuickKeybindRefreshers()
    end)
    -- Fired by KeybindListener after SetBinding succeeds. UPDATE_BINDINGS is the
    -- event stock buttons refresh from, but the mode's own signal costs nothing
    -- and means the text updates even if that event were not raised.
    if _G.EventRegistry and _G.EventRegistry.RegisterCallback then
        _G.EventRegistry:RegisterCallback(
            "KeybindListener.RebindSuccess", RunQuickKeybindRefreshers, qkCallbackOwner)
    end

    qkHooked = true
    if InQuickKeybindMode() then SyncQuickKeybindState() end
    return true
end

-- Only the combat deferral needs an event. There is no ADDON_LOADED fallback for
-- a late QuickKeybindFrame: Blizzard_QuickKeybind is a default-enabled, non-LoD
-- addon, so it has loaded before ours, and its mixin and its frame come from the
-- same load (the mixin is a global of that addon too).
local qkEvents = CreateFrame("Frame")
qkEvents:RegisterEvent("PLAYER_REGEN_ENABLED")
qkEvents:SetScript("OnEvent", function()
    if qkPendingSync then SyncQuickKeybindState() end
end)

local function QuickKeybindDoModeChange(self, isInQuickbindMode)
    self.QuickKeybindHighlightTexture:SetShown(isInQuickbindMode)
end

-- Makes `button` take part in Quick Keybind mode under `commandName`.
function Helpers.AttachQuickKeybind(button, commandName)
    if not (button and commandName) or qkButtons[button] then return end

    local mixin = _G.QuickKeybindButtonTemplateMixin
    if type(mixin) ~= "table" then
        WarnQuickKeybindOnce("quickkeybind_nomixin",
            "QuickKeybindButtonTemplateMixin missing, Quick Keybind mode cannot bind these buttons")
        return
    end

    button.commandName = commandName
    for key, value in pairs(mixin) do
        if button[key] == nil then button[key] = value end
    end

    -- The bindable-button highlight. Blizzard's own is an atlas texture sized
    -- for its 45px button (QuickKeybindHighlightTexture); ours is the same
    -- cut-corner glow a hovered main-bar button gets, in the border cyan, so it
    -- follows the button's chamfered shape (every button this is attached to is a
    -- two-corner cut button). The stock OnEnter/OnLeave drive its alpha (1 hovered,
    -- 0.5 idle), so the idle alpha is set here.
    local highlight = button:CreateTexture(nil, "OVERLAY", nil, 2)
    if Theme.SLICE_CUT2_GLOW_TEXTURE and Theme.ApplyNineSlice then
        local pad = Theme.SLICE_CUT2_GLOW_PAD or 4
        highlight:SetTexture(Theme.SLICE_CUT2_GLOW_TEXTURE)
        Theme.ApplyNineSlice(highlight, Theme.SLICE_CUT2_GLOW_MARGIN)
        highlight:SetPoint("TOPLEFT", button, "TOPLEFT", -pad, pad)
        highlight:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", pad, -pad)
    else
        highlight:SetTexture(Theme.FLAT_TEXTURE)
        highlight:SetAllPoints(button)
    end
    highlight:SetBlendMode("ADD")
    local color = Theme.COLOR_POWER
    highlight:SetVertexColor(color[1], color[2], color[3], 0.9)
    highlight:SetAlpha(0.5)
    highlight:Hide()
    button.QuickKeybindHighlightTexture = highlight

    -- Overrides the stock method, which SetAtlas()es Blizzard's own highlight.
    button.DoModeChange = QuickKeybindDoModeChange

    button:HookScript("OnEnter", function(self) CallQuickKeybind(self, "QuickKeybindButtonOnEnter") end)
    button:HookScript("OnLeave", function(self) CallQuickKeybind(self, "QuickKeybindButtonOnLeave") end)
    button:HookScript("OnShow", function(self) CallQuickKeybind(self, "QuickKeybindButtonOnShow") end)
    button:HookScript("OnHide", function(self) CallQuickKeybind(self, "QuickKeybindButtonOnHide") end)
    -- RegisterForClicks("AnyUp", "AnyDown") delivers each click twice, down then
    -- up. Stock buttons only get the release for a mouse button 4/5 click, so
    -- take only the release here too, or one click would run the binder twice.
    button:HookScript("OnClick", function(self, mouseButton, down)
        if down then return end
        CallQuickKeybind(self, "QuickKeybindButtonOnClick", mouseButton, down)
    end)

    -- The click-eating overlay (see the section header). Built hidden; the mouse
    -- wheel is forwarded too, since with the overlay up the wheel event lands on
    -- it rather than on the button the mixin installs its handler on. Hiding it
    -- while hovered runs the stock leave handler, which would otherwise never
    -- fire (restores the OnUpdate script and hides the binding tooltip).
    local overlay = CreateFrame("Button", nil, button)
    overlay:SetAllPoints(button)
    overlay:SetFrameLevel(button:GetFrameLevel() + QK_OVERLAY_LEVEL_OFFSET)
    overlay:EnableMouse(true)
    overlay:EnableMouseWheel(true)
    overlay:RegisterForClicks("AnyUp")
    overlay:Hide()
    overlay:SetScript("OnEnter", function() CallQuickKeybind(button, "QuickKeybindButtonOnEnter") end)
    overlay:SetScript("OnLeave", function() CallQuickKeybind(button, "QuickKeybindButtonOnLeave") end)
    overlay:SetScript("OnHide", function() CallQuickKeybind(button, "QuickKeybindButtonOnLeave") end)
    overlay:SetScript("OnClick", function(_, mouseButton, down)
        CallQuickKeybind(button, "QuickKeybindButtonOnClick", mouseButton, down)
    end)
    overlay:SetScript("OnMouseWheel", function(_, delta)
        CallQuickKeybind(button, "QuickKeybindButtonOnMouseWheel", delta)
    end)
    button.fsQuickKeybindOverlay = overlay

    qkButtons[button] = true

    if not HookQuickKeybindFrame() then
        WarnQuickKeybindOnce("quickkeybind_nohook",
            "QuickKeybindFrame not found, Quick Keybind mode cannot bind these buttons")
    end
    if InQuickKeybindMode() then SyncQuickKeybindState() end
end

-- Registers a function to run when bindings may have changed under the player
-- (the mode closed, or the binder reported a successful rebind), so a bar can
-- redraw its hotkey text. UPDATE_BINDINGS stays each bar's own event.
function Helpers.OnQuickKeybindChanged(fn)
    qkRefreshers[#qkRefreshers + 1] = fn
end
