-- Forever Synthwave: Pet Frame Cast Bar (console dock, option C: one 26 high plate beside the
-- status block)
--
-- Chevron cast/channel bar for FS.PetFrame.castSlot, the top-row slot PetFrame.lua reserves
-- to the right of the status slot (the console-docked pet component, option C of
-- mockups/gunsight-hud-v2-2026-10-02: the slot is 198 x 26, the 10 pet buttons sit under it).
-- A leaf module like CastBars.lua: nothing else in the addon consumes anything from this
-- file, so there is no FS.PetCastBar export. Loads after Theme.lua/FrameHelpers.lua/
-- ChevronCastBar.lua/PetFrame.lua per the .toc, so FS.Theme.*/FS.FrameHelpers.* fields are
-- captured into file-scope locals below exactly like CastBars.lua does. FS.ChevronCastBar is
-- read at Build time.
--
-- GEOMETRY. Every number is a design px from the mockup's peCastDc / peDcCount / PE_DC_* times
-- FS.Layout.Scale(); the harness parses them back out of the mockup, so a mockup move fails there.
-- The slot is 26 high and the bar fills it (`barFrame`), there is NO tab. A 20 square icon sits at
-- (3, 3); the engine run is 14 high from x 28, centred in the bar (y 6), at the pet geometry (7 arm,
-- 7 tip, gapFraction 0.2 so the pitch is 10); on the right a text column holds the spell name (8 pt
-- cyan) over the "elapsed / total" timer (8.5 pt, 7.5 pt while both numbers are 10 or more, see TIMER SIZE),
-- both right aligned 6 in from the right edge.
--
-- TEXT COLUMN AND CHEVRON COUNT. Nothing is measured: the text column is a fixed design constant,
-- NAME_MAX_W (43 design px), picked by eye. It holds the timer sample "0.0 / 0.0" at 8.5 pt (about 43 px
-- at Mononoki's 0.5615 em advance; the timer box itself is RUN_GAP wider, see below) and about 9 characters of an 8 pt spell name (4.5 px each), so
-- Firebolt and Seduction show whole and the longer pet names (Lash of Pain, Consume Shadows) are cut by
-- the engine's own truncation: the name FontString is NAME_MAX_W wide with SetWordWrap(false). The track
-- the chevrons run along is a pure function of constants: `trackW` = the slot (198) less the run's x (28),
-- NAME_MAX_W, the right pad (6) and the gap (5), and the run is sized with `run:FitWithin(trackW, 14)`
-- (FitWidth's round-down twin: a whole number of chevrons at the current pixel pitch). At scale 1 the
-- track is 116 px against the 114 that 11 chevrons need, which gives the mockup's 11 at scales 1 and
-- 0.8333 and 10 at 0.64. The count has no font dependence (it does not depend on the font's glyph
-- widths), because no font is consulted. It is not immune to pixel snapping: ChevronCastBar.lua rounds
-- the chevron size and pitch to whole physical pixels, so at other UI scales the 0.8333 and 0.64 counts
-- can still land one chevron either side (10 or 11). Of the widths around it, 39 to 45 give 11 / 11 / 10
-- at scales 1, 0.8333 and 0.64, while 38 (12 at 0.8333) and 46 (10 at scale 1) each break it (the
-- sweep test in petcastbar-harness.py), so 43 sits mid window. There is no slack constant: it existed
-- only to absorb a MEASURED width that could come out a hair wider than the mockup's, and a constant
-- column has no such error. The spell name is never measured, compared or truth-tested (it may be
-- secret), only handed to SetText.
--
-- CHROME. The bar draws its own plate and outline (`SLICE_CUT2_*` through Theme.AddCut2Texture,
-- TOP-LEFT and BOTTOM-RIGHT cut only). The outline is the engine's flareTarget. Both are a ghost
-- at idle (alpha 0.4) and firm up while a cast runs (plate 0.92, outline 1), the mockup's two
-- states. The icon box shows only while a cast is on screen. The cut textures are baked at
-- chamfer 6, the mockup draws 4 on the bar and 3 on the icon, so the corners read slightly larger
-- than the mockup's. The icon is square (a mask does not clip on this client) instead of the
-- mockup's cut icon.
--
-- OWN FRAMES: everything this module draws lives on `castPanel`, a plain Frame that fills
-- castSlot, and its child `barFrame`. castPanel is the engine's
-- scaleTarget (the lock-in pop 1.0 -> 1.04 -> 1.0, which is OFF by default and only plays if the
-- engine's opts.lockSnap is set; this file does not set it) and alphaTarget (the outage dims
-- it), NOT the whole pet container: the container is the parent of the secure pet action buttons
-- (barSlot), and a pop over it would scale the buttons too. The panel is never hidden (the
-- engine's OnUpdate does not run while its frame is hidden).
--
-- IDLE ROW. Between casts the slot is NOT blank: the mockup's idle is a ghost, a faint
-- plate and outline (alpha 0.4) under a row of OUTLINE chevrons (cyan, GHOST_ALPHA 0.24), with NO
-- icon box (no icon, stroke or shield), no spell name and no timer. The engine can only dim its
-- filled chevron, so `GoIdle` parks it in run:ShowIdle(0) and `SyncGhosts` shows one outline chevron
-- (the engine's own caret outline art, run.textures.outline) over each engine chevron, anchored to
-- it so it follows every relayout and every change of the count; the outline is about 2 px thick
-- against the mockup's pLW(0.55) (0.55 is a line weight multiplier in the mockup's drawing code, not
-- a pixel width). A cast ignites from it (BeginCast hides the ghosts and shows the icon
-- box, StartCast puts the unlit filled chevrons back to the engine's own 0.2), and every end of a
-- cast (onFinished, a quiet Stop, an abandoned cast, the strip's verdict, the PLAYER_ENTERING_WORLD
-- reset) lands back here. GoIdle is the only place the panel's state is reset.
--
-- SPELL NAME. `nameText`, a FontString above the timer. The name goes to SetText untouched by
-- `ShowName` (a secret value is fine there) and is never measured, compared, truth-tested or
-- upper-cased; the FontString has a fixed width (NAME_MAX_W) and no word wrap, so a long name is cut
-- by the engine instead of running into the chevrons. Blank at idle.
--
-- The engine's glow regions are two DEDICATED textures on barFrame (a pink nine-sliced halo
-- just outside the bar): `glowBurst` (scaled out and faded at lock-in, then hidden by the
-- engine) and `holdGlow` (held at 0.7 through the hold and fade). Never pass a permanent
-- glow for either: the engine leaves them at alpha 0.
--
-- EVENTS. UnitCastingInfo("pet")/UnitChannelInfo("pet") read through the eight
-- UNIT_SPELLCAST_* events CastBars.lua registers (RegisterUnitEvent, unit "pet"), plus
-- a plain UNIT_PET listener (fires on the OWNER token "player", not "pet" -- see
-- PetFrame.lua's own header; other units' pets fire it too, so only the owner's
-- resets state; while a verdict plays and the pet GUID is plain and unchanged it is
-- ignored, so a same-pet UNIT_PET does not cut the hold) and PLAYER_ENTERING_WORLD (a
-- loading screen can swallow a verdict: it resets to the idle row and re-reads the pet).
-- UNIT_SPELLCAST_SUCCEEDED is deliberately NOT registered: it fires
-- for every successful cast of the unit, instants included, and must not drive the
-- bar. The verdict mapping is the caller recipe in ChevronCastBar.lua's header:
--   START / CHANNEL_START  read UnitCastingInfo/UnitChannelInfo, capture the castID
--                          (7th return of UnitCastingInfo; channels have none) and
--                          call run:StartCast(startSec, endSec, isChannel, castID);
--   STOP                   castID matches (run:MatchesCast == true) -> Succeed();
--   INTERRUPTED            MatchesCast ~= false -> Interrupt() (a nil answer is a
--                          secret castID: INTERRUPTED only fires for a cast that
--                          started, so it still interrupts);
--   FAILED                 MatchesCast == true -> Interrupt(); nil (secret) -> only
--                          when UnitCastingInfo now returns a plain nil name;
--   CHANNEL_STOP           interruptedBy present -> Interrupt(), else (and for a secret
--                          interruptedBy) the quiet end: QuietStop -> GoIdle -> ShowIdle,
--                          which resets the engine like Stop() and parks the idle row (no
--                          engine finish plays and onFinished does not fire);
--   DELAYED / CHANNEL_UPDATE  run:UpdateTimes(): re-times the running cast without
--                          restarting it, so already-lit segments do not re-ignite;
--   while run:IsFinishing() (hold, fade, outage) every STOP/FAILED/INTERRUPTED and any
--   refresh that finds no cast is ignored: a nil UnitCastingInfo must never be mapped
--   to Stop(), it would kill the hold and the lock-in.
-- Cast events are ignored while a channel runs and CHANNEL_STOP is ignored while a
-- cast runs (a channel has no castID, Blizzard keys it on the event alone).
--
-- TIMING SECRECY. Pet timing is expected to be plain. UnitCastingInfo/UnitChannelInfo
-- start and end are only ever converted (ms to seconds) after an IsSecret/type check;
-- if either is secret the engine is not used (StartCast is handed nil and refuses) and
-- an engine-timed StatusBar (`stripBar`) takes over: a duration object goes to
-- SetTimerDuration, the same duration-object approach CastBars.lua uses, and the fill is
-- the tiled Theme.CAST_CHEVRON_STRIP_TEXTURE (SetHorizTile). The strip tiles at its
-- native 32 units (2 chevrons, 16 per chevron) and its arm is fatter than the engine's,
-- so it is an approximation: the bar is scaled (SetScale, with the anchors still
-- spanning the run column, so the texture stays stretched to the column's height) until
-- one tile equals two engine pitches. A secret value is never compared, formatted or
-- used in arithmetic here. The timer text reads "elapsed / total" (for a channel, what is left
-- over the total): the duration object's GetElapsedDuration() (GetRemainingDuration() for a
-- channel) and GetTotalDuration() go straight into SetFormattedText("%.1f / %.1f") on a 0.1s
-- ticker, inside a pcall; the values are never truth-tested or used in arithmetic, and the first
-- number is compared only once IsSecret has said it is plain (TIMER SIZE below). One colour: the
-- mockup's muted " / total" would need a colour escape around a value that may be secret.
-- Those values may be secret (the strip path), so the format cannot be chosen by comparing them (no
-- shorter "10 / 12" once a value reaches 10). The timer FontString is instead (NAME_MAX_W + RUN_GAP)
-- wide (48 px), right justified, with SetWordWrap(false): the gap is free for it, because the chevron
-- run ends a whole RUN_GAP before the text column starts, so the box never overlaps the run. The common
-- readouts fit whole ("0.0 / 0.0" is about 43 px, "0.0 / 12.0" about 47.7).
--
-- TIMER SIZE (Parker: "if both casts are 10s or more... temporarily decrease the font size"). A readout
-- wider than the box ("10.0 / 12.5" is 11 characters, about 52 px at 8.5 pt against 48) would be cut by
-- the engine's own truncation, and it only grows to 11 characters while BOTH numbers are 10 or more. The
-- first number (elapsed for a cast, remaining for a channel) is never above the total, so that is exactly
-- "the first number is 10 or more": the timer wears TIMER_SMALL_FONT_SIZE (7.5 pt) while it is and 8.5 pt
-- the rest of the time, so the font can change in the middle of a cast (a cast grows into it, a channel
-- counts out of it; "temporarily"), and 8.5 pt returns at every cast start and stop. The cutoff is
-- TIMER_SMALL_FIRST_FROM = 9.95, not 10: "%.1f" prints 9.95 and above as "10.0", the 11 character
-- readout, so the small font has to be on from there. 7.5 is the largest half point that fits the widest
-- readout "99.9 / 99.9" (11 characters, 11 * 7.5 * 0.5615 = 46.3 px; 8.0 would be 49.4); that fit is
-- computed with a linear glyph advance, and the real pixel snapping of the font at small scales is
-- UNVERIFIED (the harness pins it at scales 1, 0.8333 and 0.64). The decision is the same on both paths:
--   * PLAIN first number (not IsSecret, a number): compared with 9.95, and timerText is given the small
--     font through ApplyMono only when that state CHANGES (a steady stretch re-applies nothing on its
--     ticks). A secret total beside a plain first number changes nothing here.
--   * SECRET first number (the strip path, timing secret): never compared, formatted, truth-tested or
--     used in arithmetic. A second FontString, `timerSmall`, takes the same SetFormattedText and the
--     ENGINE picks the layer: duration:EvaluateElapsedDuration(curve) (EvaluateRemainingDuration for a
--     channel, the method that matches the number shown) with a Step curve at 9.95 (1 below, 0 from it
--     for timerText; the inverse for timerSmall) goes straight into SetAlpha, the way PetFrame.lua's
--     UpdatePetLowHealth drives alpha from UnitHealthPercent(unit, false, curve). Whether the engine's
--     answer is itself secret is not documented (see below); the code only type()s it and hands it to
--     SetAlpha, so it is correct either way.
--     The first refusal (no method, a throw, a non-number result, a refused SetAlpha) latches
--     `timerFadeBroken`, is logged once (key petcast_timer_fade) and the readout stays at 8.5 pt,
--     clipped as before; so does a client with no C_CurveUtil.CreateCurve / Enum.LuaCurveType.Step.
--     So the shrink applies whenever the timing is readable, and also on the secret path when the
--     curve API answers.
--   API verification (never guessed): LuaDurationObject:EvaluateElapsedDuration(curve, modifier) and
--   EvaluateRemainingDuration return a LuaCurveEvaluatedResult marked SecretWhenCurveSecret only (so
--   the documentation does not say the answer is secret for a secret duration) in the retail 12.1.0 API
--   documentation, Blizzard_APIDocumentationGenerated/LuaDurationObjectAPIDocumentation.lua:37-52 and
--   :73-88 (EvaluateTotalDuration is :109-124 and is not used); Region:SetAlpha accepts a
--   secret (SecretArgumentsAddAspect Alpha, SecretArguments AllowedWhenTainted),
--   SimpleRegionAPIDocumentation.lua:122-132; the curve is C_CurveUtil.CreateCurve() (CurveUtilDocumentation.lua:21,
--   also namespaces.txt:1335 of the 16001 dump) with curve:SetType(Enum.LuaCurveType.Step)
--   (LuaCurveObjectBaseAPIDocumentation.lua:40, LuaCurveObjectConstantsDocumentation.lua:14) and
--   curve:AddPoint(x, y) (LuaCurveObjectAPIDocumentation.lua:11); FontString:SetAlpha is in the 16001
--   dump (widgets.txt:5966). NOT in the 16001 dump: the duration object's own methods and Enum.LuaCurveType
--   (neither class is dumped), so on the live client the secret path is UNVERIFIED in game and runs
--   behind the feature detection and latch above. Also UNVERIFIED: whether a Step curve evaluated at
--   exactly 9.95 takes the 9.95 point (the plain path counts 9.95 as long).
--
-- STRIP SAFETY NET. A dropped verdict (a loading screen) must not leave the full strip
-- showing. PLAYER_ENTERING_WORLD resets to the idle row, and the next cast replaces it.
-- A one-shot C_Timer.After past the cast's end was NOT added, deliberately: with secret
-- timing the end time cannot be computed, and the only remaining-time reader on the
-- duration object (GetRemainingDuration, LuaDurationObjectAPI) is not marked
-- ReturnsNeverSecret, so it is secret exactly when the timing is. HasSecretValues is
-- never secret but carries no number. C_Timer.After itself exists (namespaces.txt of the
-- 16001 dump); there is just nothing plain to hand it.
--
-- No combat gating anywhere in this file, deliberately: this cast bar is a plain,
-- non-secure visual built entirely inside castSlot, a SIBLING of barSlot (where Phase
-- 5's secure pet-action buttons live), never an ancestor/descendant of anything
-- implicitly protected -- mirrors CastBars.lua's own file-header note that its cast
-- bars are "plain non-secure frames... so building and styling them is safe in
-- combat." Build()/Init() still go through the same defensive pcall idiom
-- PetFrame.lua/PetActionBar.lua/CastBars.lua all use, and Init is deferred to
-- PLAYER_LOGIN (needed here because FS.PetFrame.castSlot only exists once
-- PetFrame.lua's own PLAYER_LOGIN-deferred Build has run -- PetFrame.lua loads
-- earlier in the .toc, so its loader frame registers PLAYER_LOGIN first and its
-- handler fires first) -- but, per this file's own no-combat-gating rule, WITHOUT the
-- InCombatLockdown -> PLAYER_REGEN_ENABLED fallback PetFrame.lua/PetActionBar.lua add
-- for their own, differently-scoped reasons.

local addonName, FS = ...

local ApplyMono = FS.Theme.ApplyMono
local COLOR_POWER = FS.Theme.COLOR_POWER
local COLOR_HEALTH = FS.Theme.COLOR_HEALTH
local COLOR_BORDER = FS.Theme.COLOR_BORDER
local COLOR_BAR_TRACK = FS.Theme.COLOR_BAR_TRACK
local COLOR_BAR_BORDER = FS.Theme.COLOR_BAR_BORDER
local COLOR_CAST_NO_INTERRUPT = FS.Theme.COLOR_CAST_NO_INTERRUPT
local AddSliceTexture = FS.Theme.AddSliceTexture
local AddCut2Texture = FS.Theme.AddCut2Texture
local ApplyNineSlice = FS.Theme.ApplyNineSlice
local IsSecret = FS.IsSecret

-------------------------------------------------------------------------------
-- Geometry constants: design px from the mockup, times FS.Layout.Scale()
-------------------------------------------------------------------------------

-- The bar: peCastDc's bh. The slot is the whole 26 high top row.
local BAR_HEIGHT = 26

-- The cast slot's width (PetFrame.lua's 198: 3/5 of the interior less the gap), the one number the
-- run's track is derived from. The harness checks it against the mockup's cw.
local CAST_SLOT_W = 198

-- The spell icon box: peIcon(x + 3, y + 3, 20).
local ICON_X, ICON_Y, ICON_SIZE = 3, 3, 20

-- The chevron run: PE_DC_RUNX and PE_DC_CH, centred in the bar ((26 - 14) / 2). The chevron
-- geometry itself (7 arm, 7 tip, pitch 10 at 14 high) comes from the engine with gapFraction 0.2
-- (PE_DC_CW / PE_DC_PITCH).
local RUN_X, RUN_HEIGHT = 28, 14
local RUN_Y = (BAR_HEIGHT - RUN_HEIGHT) / 2
local RUN_GAP_FRACTION = 0.2

-- The text column on the right: both lines right aligned this far in from the bar's right edge
-- (PE_PAD) and the run's gap to it (PE_DC_GAP).
local RIGHT_PAD, RUN_GAP = 6, 5

-- The text column's width in design px, a FIXED constant (never measured, see the header): wide enough
-- for the timer sample at 8.5 pt and about 9 characters of the 8 pt spell name. The track the run fits
-- is derived from it, so changing it changes the chevron count (11 chevrons need a track of at least 114;
-- the harness pins 11 / 11 / 10 at scales 1 / 0.8333 / 0.64).
local NAME_MAX_W = 43

-- The timer (peTimer 8.5 pt, the widest readout is "0.0 / 0.0") and the spell name (peT 8 pt cyan)
-- above it. The font sizes only; neither string is ever measured.
local TIMER_FONT_SIZE = 8.5
local NAME_FONT_SIZE = 8

-- A readout whose FIRST number (elapsed for a cast, remaining for a channel) is 10 or more is
-- "10.0 / 12.5", 11 characters (about 52 px at 8.5 pt) in a 48 px timer box, so while it is the timer
-- wears TIMER_SMALL_FONT_SIZE. The first number is never above the total, so "both numbers are at least
-- 10" is exactly "the first is". 7.5 is the largest half point that fits the widest readout
-- "99.9 / 99.9" (11 characters at Mononoki's 0.5615 em advance, a linear advance: 11 * 7.5 * 0.5615 =
-- 46.3 px; 8.0 would be 49.4).
local TIMER_SMALL_FONT_SIZE = 7.5
-- 9.95, not 10: "%.1f" prints 9.95 and above as "10.0", the 11 character readout, so that is where the
-- shrink must already be on. (The double nearest 9.95 itself still prints "9.9"; one reading early is
-- harmless.) Both paths use it: the plain compare and the Step curve point.
local TIMER_SMALL_FIRST_FROM = 9.95

-- The one format both timer FontStrings are written with.
local TIMER_FORMAT = "%.1f / %.1f"

-- Where the two lines sit, as design px from the bar's TOP edge to the glyph middle: the mockup's
-- baseline (10 and 21) less about 0.36 em.
local NAME_Y, TIMER_Y = 7, 18

-- Seconds between timer text refreshes; one decimal place never needs faster.
local TIMER_TICK_INTERVAL = 0.1

-- Plate and outline alpha: a ghost at idle, firm while casting (the mockup's two states).
local PLATE_IDLE_ALPHA, PLATE_CAST_ALPHA = 0.4, 0.92
local OUTLINE_IDLE_ALPHA, OUTLINE_CAST_ALPHA = 0.4, 1

-- The mockup draws the pet bar with salt 7 and the player bar with 13, so the
-- two flicker differently.
local PET_SEED_SALT = 7

-- Alpha of the idle row's ghost chevrons: the mockup's ghost run (an OUTLINE of each chevron,
-- cyan at 0.24, no fill). The engine's own unlit (filled) look during a cast is 0.2.
local GHOST_ALPHA = 0.24

-- The pink halo around the bar: lock-in burst peak is the engine's own 0.9; the hold
-- glow alpha is the engine's (0.7). Only the tint lives here.
--
-- VISUAL NOTE (estimate, needs Parker's eyeball): the halo is a nine-slice that sits
-- SLICE_GLOW_PAD (4) outside the bar (BuildGlow), the lock-in burst grows it a further
-- GLOW_BURST_EXPAND (5) units, and the 1.04 pop (off by default) would scale the whole panel.
-- For about 0.3s at lock-in the halo bleeds roughly 4-9 px past the bar, which is onto the status
-- slot's right edge and the top of the pet buttons. To shrink it: lower GLOW_BURST_EXPAND (the
-- engine's glowBurstExpand option, 0 = no growth) and/or the pad inside BuildGlow.
local GLOW_COLOR = COLOR_HEALTH
local GLOW_BURST_EXPAND = 5

local CAST_EVENTS = {
    "UNIT_SPELLCAST_START",
    "UNIT_SPELLCAST_STOP",
    "UNIT_SPELLCAST_FAILED",
    "UNIT_SPELLCAST_INTERRUPTED",
    "UNIT_SPELLCAST_DELAYED",
    "UNIT_SPELLCAST_CHANNEL_START",
    "UNIT_SPELLCAST_CHANNEL_STOP",
    "UNIT_SPELLCAST_CHANNEL_UPDATE",
}

-------------------------------------------------------------------------------
-- Module state
-------------------------------------------------------------------------------

local castPanel, barFrame, runColumn, run, stripBar
local iconTexture, shieldOverlay, glowBurst, holdGlow, timerText, timerSmall
local plate, outline, iconEdges
local ghosts, ghostOn
local nameText

-- What is on screen: "run" (the engine), "strip" (the secret-timing fallback) or nil
-- (idle: the row of unlit chevrons). `channeling` is the current cast's kind.
local mode
local channeling = false

-- UnitGUID("pet") captured when the current cast began; nil when idle or not readable.
-- Lets UNIT_PET tell "the same pet" from a swap while a verdict plays.
local castPetGUID

-- Timer text state: the live duration object (and whether it counts down, a channel), the
-- ticker frame that polls it, and latches so one failed call or one log line disables/prints
-- only once.
local timerTicker, activeDuration, activeCountdown
local timerElapsed = 0
local timerBroken = false

-- Timer size state (see the TIMER SIZE header paragraph). `timerSmallFont` is whether `timerText`
-- wears the small font (the plain path); `timerFadeOn` is whether the secret path's crossfade is
-- driving the two layers' alphas; the two curves are Step curves at TIMER_SMALL_FIRST_FROM (nil with no
-- curve API); `timerFadeBroken` latches the first refusal so the fallback (8.5 pt, clipped) is
-- logged once and kept.
local timerSmallFont = false
local timerFadeOn = false
local timerFadeBroken = false
local timerCurveNormal, timerCurveSmall

-------------------------------------------------------------------------------
-- Small helpers (TryStep / SafeRegisterUnitEvent, same idioms CastBars.lua
-- uses, reusing FS.FrameHelpers' shared plumbing)
-------------------------------------------------------------------------------

local function DescribePetCastBarStep(label)
    return "ForeverSynthwave pet cast bar: " .. label
end

local TryStep = FS.FrameHelpers.NewStepRunner(DescribePetCastBarStep)

-- Placeholder "frame" argument for TryStep/pcall(fn, frame): this module is a
-- singleton over module-scope locals, so there is no per-instance object to
-- pass -- the step functions ignore their argument.
local runnerHost = {}

local function ReportRegisterFailure(event, err)
    print(DescribePetCastBarStep("register " .. event) .. " failed: " .. tostring(err))
end

local function SafeRegisterUnitEvent(events, event)
    FS.FrameHelpers.SafeRegisterUnitEvent(events, event, "pet", ReportRegisterFailure)
end

-- 12.0 "secret values": same feature-detected duration-object pair
-- CastBars.lua's own HAS_CAST_DURATION uses.
local HAS_CAST_DURATION = type(UnitCastingDuration) == "function"
    and type(UnitChannelDuration) == "function"

local function HasTimerDuration(bar)
    return type(bar.SetTimerDuration) == "function"
end

-- True when a value exists, WITHOUT a nil test on a secret (comparing a secret to
-- nil is itself an illegal comparison): a secret is unknown but present.
local function Present(v)
    return IsSecret(v) or v ~= nil
end

-- A time in ms -> seconds, or nil when it is secret or not a number. The only place a
-- UnitCastingInfo time is ever divided, and only after the guard.
local function PlainSeconds(ms)
    if IsSecret(ms) or type(ms) ~= "number" then return nil end
    return ms / 1000
end

-------------------------------------------------------------------------------
-- Slot geometry
-------------------------------------------------------------------------------

-- Strip fallback tile scale: the strip file is 32 wide with 2 chevrons (16 per
-- chevron). Scaling the bar by 2 * pitch / 32 makes one tile two engine pitches wide.
-- The pitch is the engine's own whole-pixel pitch (run.pitch), not a recomputation:
-- the engine rounds to physical pixels, so the two differ by up to ~14%. It is the
-- run's onLayout callback, so a re-layout from a UI scale or display size change
-- (which the engine detects itself) updates the strip too. The anchors still span the
-- column, so the texture is stretched to its height.
local function ApplyStripScale()
    if not (stripBar and run) then return end
    local pitch = run.pitch
    if not pitch or pitch <= 0 then return end
    local stripScale = 2 * pitch / FS.Theme.CAST_CHEVRON_STRIP_TILE_W
    if stripScale < 0.01 then stripScale = 0.01 end
    stripBar:SetScale(stripScale)
end

-- The idle ghost row: one outline chevron (the engine's caret outline art) laid over each engine
-- chevron, at the mockup's ghost alpha. The engine can only dim its FILLED chevron, so at idle it
-- is parked at alpha 0 (run:ShowIdle(0)) and these draw the row instead. Each ghost is anchored to
-- its engine chevron (SetAllPoints), so it follows every relayout, rescale and pixel snap by
-- itself; this only creates the ghosts the layout needs and shows them at idle. Runs from the
-- engine's onLayout and from GoIdle / BeginCast, which flip `ghostOn`.
local function SyncGhosts()
    if not (run and run.frame and ghosts) then return end
    local count = run.count or 0
    for i = 1, count do
        local g = ghosts[i]
        if not g then
            g = run.frame:CreateTexture(nil, "BACKGROUND", nil, 1)
            g:SetTexture(run.textures.outline)
            g:SetVertexColor(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], GHOST_ALPHA)
            g:SetAllPoints(run.segs[i].dim)
            ghosts[i] = g
        end
        g:SetShown(ghostOn and true or false)
    end
    for i = count + 1, #ghosts do ghosts[i]:Hide() end
end

-- The icon box (icon, its 1px stroke and the shield) belongs to a cast; the mockup's idle bar
-- has none of it.
local function SetIconBox(on)
    if iconTexture then iconTexture:SetShown(on) end
    if iconEdges then
        for _, edge in ipairs(iconEdges) do edge.tex:SetShown(on) end
    end
    if shieldOverlay then shieldOverlay:SetShown(on) end
end

local function OnRunLayout()
    ApplyStripScale()
    SyncGhosts()
end

-- The spell name goes to the FontString untouched: it may be a secret value, so it is never
-- measured, compared or truth-tested here (the FontString has a fixed width instead).
local function ShowName(name)
    if nameText then nameText:SetText(name) end
end

local function HideName()
    if nameText then nameText:SetText("") end
end

local function CurrentScale()
    return (FS.Layout and FS.Layout.Scale) and FS.Layout.Scale() or 1
end

-- (Re)seats everything from the design numbers: the bar across the slot, the icon, the text column,
-- and the engine's run. Called once at build time and again from the FS.Layout.OnRescale callback
-- below. Plain frames only, so it needs no combat gate.
local function ApplyGeometry()
    if not (castPanel and barFrame and runColumn and run and timerText and timerSmall) then return end

    local scale = CurrentScale()

    barFrame:ClearAllPoints()
    barFrame:SetPoint("TOPLEFT", castPanel, "TOPLEFT", 0, 0)
    barFrame:SetPoint("TOPRIGHT", castPanel, "TOPRIGHT", 0, 0)
    barFrame:SetHeight(BAR_HEIGHT * scale)

    iconTexture:ClearAllPoints()
    iconTexture:SetPoint("TOPLEFT", barFrame, "TOPLEFT", ICON_X * scale, -ICON_Y * scale)
    iconTexture:SetSize(ICON_SIZE * scale, ICON_SIZE * scale)
    for _, edge in ipairs(iconEdges) do
        if edge.horizontal then edge.tex:SetHeight(scale) else edge.tex:SetWidth(scale) end
    end

    -- The text column: the name over the timer, right aligned. The name is a fixed NAME_MAX_W wide and
    -- the timer NAME_MAX_W + RUN_GAP (the run ends RUN_GAP before the column, so the timer may use the
    -- gap). Neither wraps, so a longer name or timer readout is cut by the engine's own truncation.
    nameText:ClearAllPoints()
    nameText:SetPoint("RIGHT", barFrame, "TOPRIGHT", -RIGHT_PAD * scale, -NAME_Y * scale)
    nameText:SetWidth(NAME_MAX_W * scale)
    ApplyMono(nameText, NAME_FONT_SIZE * scale, COLOR_POWER)
    -- Both timer FontStrings take the same box; the small one is only ever visible on a long cast.
    for _, fs in ipairs({ timerText, timerSmall }) do
        fs:ClearAllPoints()
        fs:SetPoint("RIGHT", barFrame, "TOPRIGHT", -RIGHT_PAD * scale, -TIMER_Y * scale)
        fs:SetWidth((NAME_MAX_W + RUN_GAP) * scale)
    end
    ApplyMono(timerText, (timerSmallFont and TIMER_SMALL_FONT_SIZE or TIMER_FONT_SIZE) * scale)
    ApplyMono(timerSmall, TIMER_SMALL_FONT_SIZE * scale)

    -- The run: the largest whole number of chevrons that fits the track between its left edge and
    -- the text column (a pure function of constants), 14 high, centred in the bar. FitWithin is nil
    -- when not even one fits; the smallest fit (one chevron) stands in.
    local runHeight = RUN_HEIGHT * scale
    local track = (CAST_SLOT_W - RUN_X - NAME_MAX_W - RIGHT_PAD - RUN_GAP) * scale
    local runWidth = run:FitWithin(track, runHeight) or run:FitWidth(1, runHeight) or track
    runColumn:ClearAllPoints()
    runColumn:SetPoint("TOPLEFT", barFrame, "TOPLEFT", RUN_X * scale, -RUN_Y * scale)
    runColumn:SetSize(runWidth, runHeight)
    run:Layout(runWidth, runHeight)
end

-------------------------------------------------------------------------------
-- Cast state
-------------------------------------------------------------------------------

-- Normalizes UnitCastingInfo/UnitChannelInfo for "pet", mirroring CastBars.lua's own
-- GetCastInfo shape plus the spell name (opaque, only ever handed to SetText), the castID
-- (UnitCastingInfo's 7th return; a channel has none) and the notInterruptible return (position per ForeverSynthwave.lua's own
-- GetPlateCastInfo, itself UNVERIFIED on 16001 -- captured as an opaque value and only
-- ever handed to SetAlphaFromBoolean, never truth-tested). startMS/endMS are carried as
-- opaque values and only converted through PlainSeconds; the castID is only ever stored
-- and handed to run:MatchesCast, which never compares a secret.
local function GetCastInfo(unit)
    local name, _, texture, startMS, endMS, _, castID, notInterruptible = UnitCastingInfo(unit)
    if Present(name) then
        return {
            name = name, texture = texture, channeling = false, notInterruptible = notInterruptible,
            startMS = startMS, endMS = endMS, castID = castID,
        }
    end

    name, _, texture, startMS, endMS, _, notInterruptible = UnitChannelInfo(unit)
    if Present(name) then
        return {
            name = name, texture = texture, channeling = true, notInterruptible = notInterruptible,
            startMS = startMS, endMS = endMS,
        }
    end

    return nil
end

-- True only when UnitCastingInfo says, in a plain value, that the pet is not casting.
-- A secret name means unknown, so it is not "gone".
local function CastIsGone()
    if not UnitExists("pet") then return true end
    local name = UnitCastingInfo("pet")
    if IsSecret(name) then return false end
    return name == nil
end

-- Interruptible/shield tint (OPTIONAL per the design brief; implemented
-- here). Exact idiom as ForeverSynthwave.lua's nameplate ApplyCastInterruptible:
-- the ONLY sanctioned secret-boolean consumer is SetAlphaFromBoolean, so
-- `notInterruptible` is type-checked (legal on a secret) and handed straight
-- to the setter, NEVER truth-tested directly. Narrower scope than the
-- nameplate's own version: this file does not additionally listen for
-- UNIT_SPELLCAST_INTERRUPTIBLE/NOT_INTERRUPTIBLE (not in the pet cast event
-- list this phase's design specifies), so a live flip mid-cast without any
-- other cast-state event firing would not be reflected here -- a known,
-- accepted limitation of this optional feature, not a bug.
local function ApplyCastInterruptible(notInterruptible)
    if not shieldOverlay then return end
    if type(notInterruptible) == "boolean" then
        if type(shieldOverlay.SetAlphaFromBoolean) == "function" then
            shieldOverlay:SetAlphaFromBoolean(notInterruptible, 1, 0)
        end
        return
    end
    shieldOverlay:SetAlpha(0)
end

-- TIMER SIZE. Two FontStrings take the same readout: `timerText` (8.5 pt) and `timerSmall` (the small
-- size, alpha 0 unless the secret path shows it).
--   Plain first number (elapsed, or remaining for a channel): IsSecret first, then
--   `first >= TIMER_SMALL_FIRST_FROM` picks the state, and `timerText` itself is given the small font
--   (ApplyMono) only when that state CHANGES, so a steady stretch re-applies nothing on its 0.1s
--   ticks. The state flips mid cast (a cast grows into it, a channel counts out of it); that is the
--   point ("temporarily"). A secret total beside a plain first number changes nothing here.
--   Secret first number: it is never compared, formatted by hand or truth-tested. The engine compares
--   it: duration:EvaluateElapsedDuration(curve) (EvaluateRemainingDuration for a channel, the same
--   method as the number shown) with a Step curve at TIMER_SMALL_FIRST_FROM (1 below, 0 from it for
--   `timerText`; the inverse for `timerSmall`) goes straight into SetAlpha, so exactly one layer
--   shows. The first refusal (no method, a throw, a non-number result, a refused SetAlpha) latches
--   `timerFadeBroken`, is logged once, and leaves the readout at 8.5 pt, clipped as it was.
local function BuildTimerCurve(below, atOrAbove)
    local curve = C_CurveUtil.CreateCurve()
    curve:SetType(Enum.LuaCurveType.Step)
    curve:AddPoint(0, below)
    curve:AddPoint(TIMER_SMALL_FIRST_FROM, atOrAbove)
    return curve
end

-- Built at Build time (feature-detected, like PetFrame.lua's low-HP curves); nil without the API.
local function BuildTimerCurves()
    timerCurveNormal, timerCurveSmall = nil, nil
    if not (type(C_CurveUtil) == "table" and type(C_CurveUtil.CreateCurve) == "function"
        and type(Enum) == "table" and type(Enum.LuaCurveType) == "table"
        and Enum.LuaCurveType.Step ~= nil) then
        return
    end
    local okNormal, normal = pcall(BuildTimerCurve, 1, 0)
    local okSmall, small = pcall(BuildTimerCurve, 0, 1)
    if okNormal and okSmall then timerCurveNormal, timerCurveSmall = normal, small end
end

-- The plain path's font switch. A no-op unless the state changes.
local function SetTimerFontSmall(on)
    if timerSmallFont == on then return end
    timerSmallFont = on
    ApplyMono(timerText, (on and TIMER_SMALL_FONT_SIZE or TIMER_FONT_SIZE) * CurrentScale())
end

-- False when either setter refused (the values may be engine results, never read here).
local function SetTimerLayers(normal, small)
    return pcall(timerText.SetAlpha, timerText, normal) and pcall(timerSmall.SetAlpha, timerSmall, small)
end

-- Leaves the crossfade: the 8.5 pt layer plain 1, the small one plain 0 and blank.
local function LeaveTimerFade()
    if not timerFadeOn then return end
    timerFadeOn = false
    timerText:SetAlpha(1)
    timerSmall:SetAlpha(0)
    timerSmall:SetText("")
end

-- Cast start and stop: 8.5 pt, no crossfade.
local function ResetTimerLook()
    if not (timerText and timerSmall) then return end
    SetTimerFontSmall(false)
    LeaveTimerFade()
end

-- The curve is evaluated on the same duration method as the first number shown, so the engine
-- compares exactly what the readout prints. A missing method is an error the caller's pcall catches.
local function EvaluateTimerCurves()
    local method = activeCountdown and "EvaluateRemainingDuration" or "EvaluateElapsedDuration"
    return activeDuration[method](activeDuration, timerCurveNormal),
        activeDuration[method](activeDuration, timerCurveSmall)
end

local function TimerFadeAvailable()
    return timerCurveNormal ~= nil and not timerFadeBroken
end

-- The secret path: the engine picks the layer. Without it the readout stays at 8.5 pt, clipped.
local function ApplyTimerFade()
    SetTimerFontSmall(false)
    if TimerFadeAvailable() then
        local ok, normal, small = pcall(EvaluateTimerCurves)
        if ok and type(normal) == "number" and type(small) == "number"
            and SetTimerLayers(normal, small) then
            timerFadeOn = true
            return
        end
        timerFadeBroken = true
        FS.LogDegradeOnce("petcast_timer_fade",
            "ForeverSynthwave pet cast bar: long cast timer shrink disabled, the engine refused the duration curve; a secret timing readout stays at full size.")
        timerFadeOn = true  -- a setter may have written half of it: LeaveTimerFade puts both back
    end
    LeaveTimerFade()
end

-- WriteTimerText and UpdateTimerText are defined once so the 0.1s ticker allocates no closures.
-- "elapsed / total" for a cast, "remaining / total" for a channel (it counts down), straight
-- off the duration object: the values may be secret, so they only ever flow into SetFormattedText
-- (and, for the first number, into the engine's curve).
local function WriteTimerText()
    local first
    if activeCountdown then
        first = activeDuration:GetRemainingDuration()
    else
        first = activeDuration:GetElapsedDuration()
    end
    local total = activeDuration:GetTotalDuration()
    timerText:SetFormattedText(TIMER_FORMAT, first, total)
    if IsSecret(first) then
        if TimerFadeAvailable() then timerSmall:SetFormattedText(TIMER_FORMAT, first, total) end
        ApplyTimerFade()
    else
        LeaveTimerFade()
        if type(first) == "number" then SetTimerFontSmall(first >= TIMER_SMALL_FIRST_FROM) end
    end
end

local function ReadTimerGetters(duration)
    return duration.GetElapsedDuration, duration.GetRemainingDuration, duration.GetTotalDuration
end

-- The first failed call latches timerBroken and stops the ticker for the session.
local function UpdateTimerText()
    if not activeDuration or timerBroken then return end
    if pcall(WriteTimerText) then return end

    timerBroken = true
    timerText:SetText("")
    timerSmall:SetText("")
    timerTicker:Hide()
    FS.LogDegradeOnce("petcast_timer",
        "ForeverSynthwave pet cast bar: timer text disabled, SetFormattedText rejected the duration object's times.")
end

local function TimerTick(_, elapsed)
    timerElapsed = timerElapsed + elapsed
    if timerElapsed < TIMER_TICK_INTERVAL then return end
    timerElapsed = 0
    UpdateTimerText()
end

local function ClearTimer()
    activeDuration = nil
    if timerTicker then timerTicker:Hide() end
    if timerText then timerText:SetText("") end
    if timerSmall then timerSmall:SetText("") end
    ResetTimerLook()
end

-- A prior reading is cleared first, then the ticker starts only if this duration object
-- actually exposes the three readers. UpdateTimerText runs once up front so the text is not
-- blank for the first 0.1s.
local function StartTimer(duration, isChannel)
    ClearTimer()
    if duration and timerText and timerTicker and not timerBroken then
        local ok, elapsedFn, remainingFn, totalFn = pcall(ReadTimerGetters, duration)
        if ok and type(totalFn) == "function"
            and type(isChannel and remainingFn or elapsedFn) == "function" then
            activeDuration = duration
            activeCountdown = isChannel and true or false
            timerElapsed = 0
            UpdateTimerText()
            if not timerBroken then timerTicker:Show() end
        end
    end
end

local function FetchDuration(isChannel)
    if not HAS_CAST_DURATION then return nil end
    local ok, d = pcall(isChannel and UnitChannelDuration or UnitCastingDuration, "pet")
    if ok then return d end
    return nil
end

-- Ends whatever is showing and returns to the idle row (see the header). The engine's
-- ShowIdle does the full reset (effects, lit segments, OnUpdate, the panel's alpha), so
-- this is also how an abandoned cast or a hold is ended. Called from the engine's
-- onFinished and for every other end of a cast.
local function GoIdle()
    mode = nil
    castPetGUID = nil
    ClearTimer()
    if stripBar then stripBar:Hide() end
    if iconTexture then iconTexture:SetTexture(nil) end
    if shieldOverlay then shieldOverlay:SetAlpha(0) end
    SetIconBox(false)
    if plate then plate:SetAlpha(PLATE_IDLE_ALPHA) end
    if outline then outline:SetAlpha(OUTLINE_IDLE_ALPHA) end
    HideName()
    ghostOn = true
    if run then
        -- The engine's filled row is parked at alpha 0: the ghost outlines draw the idle row.
        run:ShowIdle(0)
        SyncGhosts()
    end
end

-- An abandoned cast: the unit changed, or a refresh found nothing to show.
local AbortCast = GoIdle

-- Secret-timing fallback: no engine, an engine-timed StatusBar instead.
local function StartStrip(info)
    -- Stop() also puts the panel's alpha back to 1 after an earlier outage.
    run:Stop()
    run:SetCastID(info.castID)
    mode = "strip"
    channeling = info.channeling

    local duration = FetchDuration(info.channeling)
    stripBar:SetMinMaxValues(0, 1)
    if duration and HasTimerDuration(stripBar) then
        -- A channel gets the IDENTICAL single-arg call as a cast: this client's
        -- StatusBar has no reverse-fill variant, so a channel fills up rather than
        -- draining down, the same accepted limitation CastBars.lua documents.
        pcall(function() stripBar:SetTimerDuration(duration) end)
    else
        -- No duration-object support on this client: static full bar, mirroring
        -- CastBars.lua's own no-duration-object fallback.
        stripBar:SetValue(1)
    end
    stripBar:Show()
    StartTimer(duration, info.channeling)
end

-- Starts (or restarts) the bar for `info`. The panel is always shown (the idle row), so the
-- engine's OnUpdate runs from the first frame.
local function BeginCast(info)
    castPetGUID = UnitGUID("pet")
    stripBar:Hide()
    ghostOn = false
    SyncGhosts()
    SetIconBox(true)
    iconTexture:SetTexture(info.texture)
    ApplyCastInterruptible(info.notInterruptible)
    plate:SetAlpha(PLATE_CAST_ALPHA)
    outline:SetAlpha(OUTLINE_CAST_ALPHA)
    ShowName(info.name)

    local startTime, endTime = PlainSeconds(info.startMS), PlainSeconds(info.endMS)
    -- nil times (secret) are refused by the engine without a throw.
    if run:StartCast(startTime, endTime, info.channeling, info.castID) then
        mode = "run"
        channeling = info.channeling
        StartTimer(FetchDuration(info.channeling), info.channeling)
        return
    end

    if startTime and endTime then
        -- Plain times the engine still refused: a stale or degenerate cast. There is
        -- nothing real to show.
        AbortCast()
        return
    end

    StartStrip(info)
end

-- START / CHANNEL_START and the build-time seed: show whatever the pet is casting now.
local function StartFromUnit()
    if not UnitExists("pet") then
        AbortCast()
        return
    end

    local info = GetCastInfo("pet")
    if info then
        BeginCast(info)
        return
    end

    -- Nothing to show. While a verdict is playing (hold, fade, outage) that is the
    -- expected state, and a nil refresh must not kill it.
    if mode == "run" and run:IsFinishing() then return end
    AbortCast()
end

-- DELAYED / CHANNEL_UPDATE: new times for the running cast.
local function RetimeCast()
    if mode == "run" and run:IsFinishing() then return end

    local info = GetCastInfo("pet")
    if not info then return end

    -- A missed START, or the pet moved from a cast to a channel: begin it afresh.
    if mode == nil or info.channeling ~= channeling then
        BeginCast(info)
        return
    end

    if mode == "strip" then
        local duration = FetchDuration(channeling)
        if duration and HasTimerDuration(stripBar) then
            pcall(function() stripBar:SetTimerDuration(duration) end)
        end
        StartTimer(duration, channeling)
        return
    end

    local startTime, endTime = PlainSeconds(info.startMS), PlainSeconds(info.endMS)
    if startTime and endTime then
        -- UpdateTimes, not StartCast: StartCast would reset every lit segment's ignite.
        run:UpdateTimes(startTime, endTime)
        StartTimer(FetchDuration(channeling), channeling)
    else
        -- The times went secret mid cast (not expected for a pet): hand over.
        StartStrip(info)
    end
end

-- Verdict helpers. The timer is blanked on every verdict: it would otherwise keep
-- counting down through the hold and the outage.
local function SucceedCast()
    ClearTimer()
    run:Succeed()
end

local function InterruptCast()
    ClearTimer()
    run:Interrupt()
end

-- A quiet end (no verdict animation) goes straight back to the idle row.
local function QuietStop()
    GoIdle()
end

-- Verdicts while the engine runs, in the cast phase only (see the header for the map).
local function HandleRunVerdict(event, castID, interruptedBy)
    if event == "UNIT_SPELLCAST_CHANNEL_STOP" then
        if not channeling then return end
        if not IsSecret(interruptedBy) and interruptedBy ~= nil then
            InterruptCast()
        else
            QuietStop()
        end
        return
    end

    if channeling then return end

    -- true / false / nil (nil = a castID is missing or secret; never compared).
    local matches = run:MatchesCast(castID)
    if event == "UNIT_SPELLCAST_STOP" then
        if matches == true or (matches == nil and run:IsComplete()) then
            SucceedCast()
        elseif matches == nil and CastIsGone() then
            QuietStop()
        end
    elseif event == "UNIT_SPELLCAST_INTERRUPTED" then
        if matches ~= false then InterruptCast() end
    elseif event == "UNIT_SPELLCAST_FAILED" then
        if matches == true or (matches == nil and CastIsGone()) then InterruptCast() end
    end
end

-- The strip fallback has no animation to protect: the same matching decides, and a
-- verdict just returns to the idle row.
local function HandleStripVerdict(event, castID)
    if event == "UNIT_SPELLCAST_CHANNEL_STOP" then
        if channeling then GoIdle() end
        return
    end

    if channeling then return end

    local matches = run:MatchesCast(castID)
    if event == "UNIT_SPELLCAST_INTERRUPTED" then
        if matches ~= false then GoIdle() end
    elseif matches == true or (matches == nil and CastIsGone()) then
        GoIdle()
    end
end

-- Drops whatever is showing and re-reads the pet: it may be mid cast already.
local function ResetFromUnit()
    AbortCast()
    if UnitExists("pet") then StartFromUnit() end
end

-- True while a verdict plays (hold, fade, outage) for the very pet that cast, proven by
-- two plain, equal GUIDs. A secret GUID, a missing one or a changed one is "cannot say
-- it is the same pet", and the caller keeps the old behaviour (abort).
local function SamePetMidVerdict()
    if mode ~= "run" or not run:IsFinishing() then return false end
    if not UnitExists("pet") then return false end
    local now, was = UnitGUID("pet"), castPetGUID
    if IsSecret(now) or IsSecret(was) then return false end
    return now ~= nil and now == was
end

local function HandleEvent(event, unit, castID, interruptedBy)
    if event == "UNIT_PET" then
        -- Fires for every unit's pet; only the owner's swap/dismiss/resummon resets
        -- ours, or a stale reveal from the OLD pet's last cast could carry into the
        -- new pet's frame. The same pet during a verdict is left alone: aborting would
        -- cut the hold and the lock-in for nothing.
        if unit ~= nil and unit ~= "player" then return end
        if SamePetMidVerdict() then return end
        ResetFromUnit()
        return
    end

    if event == "PLAYER_ENTERING_WORLD" then
        -- A loading screen can swallow a verdict (STOP/INTERRUPTED never arrive). Its
        -- first argument is isInitialLogin, not a unit, so this runs before any unit test.
        ResetFromUnit()
        return
    end

    if event == "UNIT_SPELLCAST_START" or event == "UNIT_SPELLCAST_CHANNEL_START" then
        StartFromUnit()
        return
    end

    if event == "UNIT_SPELLCAST_DELAYED" or event == "UNIT_SPELLCAST_CHANNEL_UPDATE" then
        RetimeCast()
        return
    end

    if mode == "strip" then
        HandleStripVerdict(event, castID)
    elseif mode == "run" and run:GetPhase() == "cast" then
        -- Not "cast" means a verdict is already playing (IsFinishing) or the run is
        -- idle: STOP/FAILED/INTERRUPTED are ignored.
        HandleRunVerdict(event, castID, interruptedBy)
    end
end

-------------------------------------------------------------------------------
-- Events
-------------------------------------------------------------------------------

local function RegisterEvents()
    local events = CreateFrame("Frame")
    for _, event in ipairs(CAST_EVENTS) do
        SafeRegisterUnitEvent(events, event)
    end

    -- UNIT_PET fires on the pet's OWNER token ("player"), not "pet" -- same as
    -- PetFrame.lua's own handling of this event (see its header). Plain
    -- RegisterEvent, not RegisterUnitEvent, for the same reason.
    pcall(events.RegisterEvent, events, "UNIT_PET")

    -- Resets a cast stranded by a loading screen (see HandleEvent). Plain RegisterEvent:
    -- it is not a unit event.
    local registered, err = pcall(events.RegisterEvent, events, "PLAYER_ENTERING_WORLD")
    if not registered then ReportRegisterFailure("PLAYER_ENTERING_WORLD", err) end

    events:SetScript("OnEvent", function(_, event, unit, castID, _, interruptedBy)
        TryStep(runnerHost, event, function()
            HandleEvent(event, unit, castID, interruptedBy)
        end)
    end)
end

-------------------------------------------------------------------------------
-- Assembly
-------------------------------------------------------------------------------

-- A dedicated pink halo texture just outside the bar (nine-sliced, ADD). One call per
-- region: the engine's burst and hold glow must be separate regions.
local function BuildGlow(parent)
    local pad = FS.Theme.SLICE_GLOW_PAD
    local glow = AddSliceTexture(parent, FS.Theme.SLICE_GLOW_TEXTURE, GLOW_COLOR, "BACKGROUND", -1, -pad)
    ApplyNineSlice(glow, FS.Theme.SLICE_GLOW_MARGIN)
    glow:SetBlendMode("ADD")
    return glow
end

-- The 1px --line stroke inside the icon's edge, four edge textures above the shield (the
-- player bar's, CastBars.lua).
local function BuildIconEdges()
    local function Edge(point1, point2, horizontal)
        local t = barFrame:CreateTexture(nil, "OVERLAY", nil, 2)
        t:SetColorTexture(COLOR_BAR_BORDER[1], COLOR_BAR_BORDER[2], COLOR_BAR_BORDER[3], 1)
        t:SetPoint(point1, iconTexture, point1, 0, 0)
        t:SetPoint(point2, iconTexture, point2, 0, 0)
        return { tex = t, horizontal = horizontal }
    end
    iconEdges = {
        Edge("TOPLEFT", "TOPRIGHT", true), Edge("BOTTOMLEFT", "BOTTOMRIGHT", true),
        Edge("TOPLEFT", "BOTTOMLEFT", false), Edge("TOPRIGHT", "BOTTOMRIGHT", false),
    }
end

local function Build()
    local castSlot = FS.PetFrame.castSlot
    if not castSlot then
        -- PetFrame.lua's own Build() failed (its Init already pcall's and
        -- prints on failure) or FS.PetFrame.castSlot otherwise never got
        -- populated -- degrade gracefully rather than throwing on a nil
        -- parent.
        return
    end

    -- The cast bar's own frame (see the header): fills the slot, always shown (the idle
    -- row between casts).
    castPanel = CreateFrame("Frame", nil, castSlot)
    castPanel:SetAllPoints(castSlot)

    -- The bar itself: the whole 26 high slot. The plate, outline, icon, glows, run, spell name and
    -- timer live on it.
    barFrame = CreateFrame("Frame", nil, castPanel)

    -- Chrome: the chamfered plate and outline. The outline is the engine's flareTarget (it
    -- eases back to the engine's flareBase, COLOR_BORDER). Alpha is the ghost/cast state,
    -- driven by GoIdle/BeginCast; vertex colour alpha stays 1.
    plate = AddCut2Texture(barFrame, FS.Theme.SLICE_CUT2_FILL_TEXTURE,
        { COLOR_BAR_TRACK[1], COLOR_BAR_TRACK[2], COLOR_BAR_TRACK[3], 1 }, "BACKGROUND", 0)
    outline = AddCut2Texture(barFrame, FS.Theme.SLICE_CUT2_OUTLINE_TEXTURE, COLOR_BORDER, "BORDER")

    -- The engine's own dedicated glow regions (see the header).
    glowBurst = BuildGlow(barFrame)
    holdGlow = BuildGlow(barFrame)
    holdGlow:SetAlpha(0)

    -- Icon box: square, blank until a cast is active (SetTexture(nil)).
    iconTexture = barFrame:CreateTexture(nil, "ARTWORK")
    iconTexture:SetTexCoord(0.08, 0.92, 0.08, 0.92)
    iconTexture:SetTexture(nil)
    BuildIconEdges()

    -- Shield overlay (optional interruptible tint, implemented): a single
    -- steel-grey overlay on the icon box, alpha driven only through
    -- SetAlphaFromBoolean, exactly ForeverSynthwave.lua's nameplate idiom.
    shieldOverlay = barFrame:CreateTexture(nil, "OVERLAY")
    shieldOverlay:SetAllPoints(iconTexture)
    shieldOverlay:SetColorTexture(1, 1, 1, 1)
    shieldOverlay:SetVertexColor(COLOR_CAST_NO_INTERRUPT[1], COLOR_CAST_NO_INTERRUPT[2], COLOR_CAST_NO_INTERRUPT[3], 1)
    shieldOverlay:SetAlpha(0)

    -- Timer text: blank until a cast enables the ticker. The ticker is hidden by default, so its
    -- OnUpdate costs nothing while no cast is active. Fixed width (set by ApplyGeometry), right
    -- justified and no wrap, so a readout wider than the text column is cut instead of growing
    -- leftwards over the chevrons.
    timerText = barFrame:CreateFontString(nil, "OVERLAY")
    ApplyMono(timerText, TIMER_FONT_SIZE)
    timerText:SetJustifyH("RIGHT")
    if timerText.SetWordWrap then timerText:SetWordWrap(false) end
    timerText:SetText("")

    -- The long cast layer: the same readout at the small size, invisible unless the secret path's
    -- engine curve shows it (the plain path shrinks timerText itself and never uses this).
    timerSmall = barFrame:CreateFontString(nil, "OVERLAY")
    ApplyMono(timerSmall, TIMER_SMALL_FONT_SIZE)
    timerSmall:SetJustifyH("RIGHT")
    if timerSmall.SetWordWrap then timerSmall:SetWordWrap(false) end
    timerSmall:SetText("")
    timerSmall:SetAlpha(0)
    BuildTimerCurves()

    -- Spell name: above the timer, cyan, blank until a cast. Fixed width (set by ApplyGeometry), no
    -- wrap, so a long or secret name clips at the text column.
    nameText = barFrame:CreateFontString(nil, "OVERLAY")
    ApplyMono(nameText, NAME_FONT_SIZE, COLOR_POWER)
    nameText:SetJustifyH("RIGHT")
    if nameText.SetWordWrap then nameText:SetWordWrap(false) end
    nameText:SetText("")

    timerTicker = CreateFrame("Frame", nil, barFrame)
    timerTicker:Hide()
    timerTicker:SetScript("OnUpdate", TimerTick)

    -- Run column: geometry (position/size) is entirely owned by ApplyGeometry below,
    -- called once immediately after this block. Both the engine's run frame and the
    -- strip fallback span it.
    runColumn = CreateFrame("Frame", nil, barFrame)

    run = FS.ChevronCastBar.Create(runColumn, {
        points = {
            { "TOPLEFT", runColumn, "TOPLEFT", 0, 0 },
            { "BOTTOMRIGHT", runColumn, "BOTTOMRIGHT", 0, 0 },
        },
        seedSalt = PET_SEED_SALT,
        gapFraction = RUN_GAP_FRACTION,
        scaleTarget = castPanel,
        alphaTarget = castPanel,
        flareTarget = outline,
        glowBurst = glowBurst,
        glowBurstExpand = GLOW_BURST_EXPAND,
        holdGlow = holdGlow,
    })
    -- The engine never touches the panel: the caller parks it on the idle row once the
    -- fade or outage ends.
    run.onFinished = GoIdle

    -- Secret-timing fallback bar (see the header), built once, hidden until needed.
    stripBar = CreateFrame("StatusBar", nil, runColumn)
    stripBar:SetPoint("TOPLEFT", runColumn, "TOPLEFT", 0, 0)
    stripBar:SetPoint("BOTTOMRIGHT", runColumn, "BOTTOMRIGHT", 0, 0)
    stripBar:SetStatusBarTexture(FS.Theme.CAST_CHEVRON_STRIP_TEXTURE)
    stripBar:SetStatusBarColor(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 1)
    local stripFill = stripBar:GetStatusBarTexture()
    if stripFill and stripFill.SetHorizTile then stripFill:SetHorizTile(true) end
    stripBar:SetMinMaxValues(0, 1)
    stripBar:SetValue(0)
    stripBar:Hide()

    ghosts, ghostOn = {}, false
    run.onLayout = OnRunLayout
    ApplyGeometry()
    GoIdle()

    -- FS.Layout.OnRescale may not exist on this client -- feature-detected
    -- exactly like PetFrame.lua does it.
    if FS.Layout.OnRescale then
        FS.Layout.OnRescale(function()
            pcall(ApplyGeometry)
        end)
    end

    RegisterEvents()

    -- Populates cast state once at build time, so a pet already mid-cast at
    -- login shows the bar immediately rather than waiting on the first
    -- UNIT_SPELLCAST_* event.
    TryStep(runnerHost, "seed", StartFromUnit)
end

-- Mirrors PetFrame.lua's/PetActionBar.lua's/CastBars.lua's defensive pcall:
-- a construction-time failure degrades gracefully with no pet cast bar
-- built, rather than surfacing as an uncaught addon error.
local function Init()
    local ok, err = pcall(Build)
    if not ok then
        print("|cff22e0ffForever STUwave|r: pet cast bar failed to build ("
            .. tostring(err) .. "); pet cast bar not created.")
    end
end

-- Deferred to PLAYER_LOGIN (needed so FS.PetFrame.castSlot exists -- see this
-- file's header). Deliberately NO InCombatLockdown -> PLAYER_REGEN_ENABLED
-- fallback, per this file's own no-combat-gating rule: nothing built here is
-- combat-restricted, so there is nothing to defer past PLAYER_LOGIN itself.
local loader = CreateFrame("Frame")
loader:RegisterEvent("PLAYER_LOGIN")
loader:SetScript("OnEvent", function(self)
    self:UnregisterEvent("PLAYER_LOGIN")
    Init()
end)
