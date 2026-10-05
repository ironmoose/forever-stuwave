-- Forever Synthwave: ChevronCastBar
--
-- The shared chevron cast-bar ENGINE: a run of nested chevron segments that
-- light as a cast progresses, a hollow chevron caret at the leading edge, the
-- success lock-in, the power-outage interrupt and the channel drain and finish. It owns
-- only the fill run; the frame chrome, name tab and spell icon belong to the
-- caller (PetCastBar.lua / CastBars.lua).
--
-- SOURCE OF TRUTH: mockups/castbar-v2-chevrons-locked-2026-10-01.html (card H,
-- Medium ignite, Finish None, Lock-in "All (burst)", Caret "Chevron outline",
-- interrupt 25/30/25/20 over 1.0s, hold 1.0s, fade 300ms). The math below is a
-- port of that script; local function names match the JS names so the two can
-- be diffed side by side: rng, makeBusyFlicker, makeFlicker, flick, phaseOf,
-- pulse, bumpA, bumpB, bumps, stutterTint, intrParams, colorOf, segLook,
-- segsChev (as Layout), lockInFlare.
--
-- API (FS.ChevronCastBar):
--   run = FS.ChevronCastBar.Create(parent, opts)
--     opts.width, opts.height   run size in UI units (calls Layout for you)
--     opts.points               { { point, relativeTo, relativePoint, x, y }, ... }
--                               anchors for the run frame (alternative to width)
--     opts.gapFraction          gap between chevrons / chevron width
--                               (default Theme.CAST_CHEVRON_GAP_FRACTION). The PET
--                               bar must pass 0.2 (the prototype's pet chevG 2 over
--                               a 10 high run); the default is the player bar's.
--     opts.seedSalt             per-bar PRNG salt (the prototype used 13 for the
--                               player bar and 7 for the pet bar)
--     opts.colors               { base, warm, core, text, flareBase }, each an
--                               { r, g, b [, a] } triple; defaults are Theme
--                               tokens (base = COLOR_POWER, flareBase =
--                               COLOR_BORDER) plus the prototype's warm/core/text
--     opts.flareTarget          texture/region whose vertex color flares toward
--                               near-white at lock-in (the bar's frame outline)
--     opts.glowBurst            optional region (outer glow) that scales out
--                               opts.glowBurstExpand (5) units and fades at lock-in.
--                               Must be a DEDICATED region (see Ownership below).
--     opts.holdGlow             optional region held at 0.7 alpha through hold+fade
--     opts.scaleTarget          optional frame that pops 1.0 -> 1.04 -> 1.0, ONLY when
--                               opts.lockSnap is true (see below)
--     opts.lockSnap             default false. "lets drop the snap" (2026-10-02): the lock-in is
--                               flash + glow burst + chevron burst with NO scale pop. true restores
--                               the old 180ms pop on scaleTarget for casts exactly. Never applies
--                               to a channel finish (none of them scale the bar) or in reduced motion.
--     opts.channelFinish        what a channel that RUNS OUT plays over its empty bar: "drain" (default;
--                               chevron burst at the left end pointing left, frame flash, glow
--                               burst), "echo" (the whole row as a near-white ghost that settles and
--                               fades, frame flash, glow burst), "sweep" (a near-white wave left to
--                               right, then a cyan afterglow), "ember" (the last chevron to go out
--                               flares and pops, frame flash) or "none" (the plain stop). Lasts the
--                               hold (opts.holdMs, 1.0s; 200ms in reduced motion; nothing plays when
--                               that is under 80ms). run:SetChannelFinish(mode) changes it later.
--     opts.fitWidth             default false. When true, the width handed to Layout (opts.width or a
--                               later Layout call) is a REQUEST: the run is widened to the smallest
--                               width holding a whole number of chevrons with zero slack, refitted
--                               from the request on every rescale. Read run.W (the fitted width)
--                               in run.onLayout to size the chrome. See Run:FitWidth.
--     opts.vertical             default false. true makes the run GROW BOTTOM TO TOP (the Gunsight cast
--                               tapes): width is the cross width, height the run's length, the seats stack
--                               on the Y axis with the same whole-pixel pitch logic (chevron box, pitch and
--                               origin on physical pixels; the origin is nudged up, or down when there is
--                               no slack, from GetBottom), the caret tip rides the top edge of its box at
--                               origin + f * span, and the end-cap burst is at the TOP (a channel finish
--                               puts it on the first, bottom, chevron). It uses UPRIGHT art, so pass
--                               opts.textures (FS.ChevronCastBar.TEXTURES_UP); no 8-argument SetTexCoord
--                               rotation is used anywhere. A channel flips the art along Y with the plain
--                               4-argument SetTexCoord(0, 1, 1, 0), the vertical twin of the horizontal
--                               mirror; opts.mirrorChannel = false keeps it upright. Not supported when
--                               vertical: opts.fitWidth (ignored) and run:FitWidth (returns nil).
--     opts.chevronWidth, opts.chevronHeight
--                               vertical only: the chevron box in run units (plain positive numbers;
--                               anything else is ignored). The same art serves any width, stretched
--                               across (a 20 wide run and a 28 wide one alike). Defaults: the cross
--                               width, and 13.5 / 28 of it high (the mockup's chevron depth over the
--                               width of its wide hw 14 chevron).
--     opts.pitch                vertical only: distance between chevron seats along the run, in run units
--                               (rounded to whole pixels, at least 1). Default chevronHeight * 12.2 / 13.5,
--                               the mockup's nesting (15.6 design units for a 17.28 high chevron).
--     opts.textures             { fill, lit, outline, glow, burst, strip } texture paths overriding the
--                               Theme.CAST_CHEVRON_* defaults (string values only; anything else keeps the
--                               default). fill is the dim chevron, lit the lit one (default: fill), outline
--                               the hollow caret, glow its halo, burst the end-cap burst, strip the
--                               StatusBar tile run:CreateStrip uses. The glow and burst are drawn at 2x
--                               the caret / chevron box, centred (both art sets are padded to match).
--                               FS.ChevronCastBar.TEXTURES_UP is the up-pointing set from media/.
--     opts.alphaTarget          frame faded to 0.3 during the outage's last phase
--                               (default: the run's own frame)
--     opts.reducedMotion        WoW has no OS flag, so the caller passes it: ignite
--                               snaps on, the outage is a plain 1.0s dim, no scale
--                               pop, no chevron burst movement, no fade after hold
--     opts.holdMs (1000), opts.interruptMs (1000)
--   run:Layout(width, height)   (re)build the segments; recycles textures. The chevrons sit
--                               on the physical pixel grid (see PIXEL GRID below). A nested
--                               Layout call (from onLayout or onFinished) is DROPPED and
--                               returns false; a rescale fired from inside one is replayed
--                               once afterwards. A throw (an erroring onLayout) is rethrown
--                               and the next trigger relayouts.
--   run:FitWidth(requested [, height]) -> width | nil
--                               the smallest width >= requested that holds a whole number of
--                               chevrons at the CURRENT pixel pitch with zero slack (nothing left
--                               before the timer). A width that already fits is returned as is.
--                               height defaults to the last laid-out one. nil for a secret,
--                               non-number, NaN, infinite or non-positive argument. Callers size
--                               their bar with it; with opts.fitWidth the run does it itself on every
--                               Layout and rescale (through onLayout). The mockup's results, from
--                               run widths with 4 units of slack: pet 180 -> 183 (17 chevrons),
--                               player 320 -> 328 (19), stack 260 -> 268 (14), stackw 440 -> 448 (29).
--   run:FitWithin(maxWidth [, height]) -> width | nil
--                               FitWidth's twin that rounds DOWN: the largest width <= maxWidth holding
--                               a whole number of chevrons at the CURRENT pixel pitch (zero slack). nil
--                               when not even one chevron fits, for a vertical run and for an unusable
--                               argument (same rules as FitWidth). For a track of fixed length (the pet
--                               bar between icon and timer column) where FitWidth could overshoot by a
--                               pitch. Pet run (h 14, gapFraction 0.2, pitch 10): 111 -> 104 (10
--                               chevrons), 114 -> 114 (11).
--   run:CreateStrip([parent]) -> strip | nil, reason
--                               the engine-timed fallback StatusBar for a secret-timed cast: a hidden
--                               StatusBar (parent default: the run frame) filled with the run's strip
--                               texture, tiled along the growth axis (SetHorizTile, or for a vertical run
--                               SetOrientation("VERTICAL") plus SetVertTile, feature-detected). The caller
--                               anchors it, colours it (SetStatusBarColor) and drives it with
--                               SetTimerDuration. A vertical run on a client that lacks SetOrientation or
--                               SetVertTile gets nil and the reason, so the consumer can fall back.
--                               strip.fsTexelsPerChevron is 16 (one chevron per 16 texels of tile).
--   run:ApplyStripScale(strip) -> scale | nil
--                               SetScale(run.pitch / 16) on a strip from CreateStrip, so one chevron of
--                               tile is one engine pitch (0.976 for the mockup's 15.6 design pitch; the
--                               same 2 * pitch / 32 PetCastBar applies to its horizontal strip). Call it
--                               from run.onLayout so a rescale follows. Assumes tiling is in frame local
--                               units, UNVERIFIED in game.
--   run:SupportsVerticalStrip() -> ok, caps
--   FS.ChevronCastBar.SupportsVerticalStrip()
--                               what a probe StatusBar (built on first call, hidden) feature-detected:
--                               caps = { orientation = SetOrientation, vertTile = SetVertTile on the fill
--                               texture, horizTile, timer = SetTimerDuration }, ok = orientation and
--                               vertTile and timer. Method presence only: whether a VERTICAL bar really
--                               fills from SetTimerDuration is the in-game probe's answer (/fsprobe
--                               gunsight), and a consumer falls back when it fails.
--   FS.ChevronCastBar.TEXTURES_UP  the up-pointing art set for opts.textures (fill, outline, glow, burst,
--                               strip = media/cast_chevron_up_*.tga).
--   FS.ChevronCastBar.Fx        the motion functions, for other consumers (see FX below).
--   run:RefreshPixels()         re-Layout at the last size when the physical pixel size
--                               (in the run's units) differs from the one the segments were
--                               built for; true when it did. Called by the engine itself on
--                               UI_SCALE_CHANGED, DISPLAY_SIZE_CHANGED, any ancestor's
--                               SetScale, OnShow (HookScript) and StartCast / ShowIdle;
--                               callers need not.
--   run.onLayout(run)           optional, set by the caller; fired at the end of every
--                               Layout, including the engine's own re-layouts. Read
--                               run.pitch (the whole-pixel pitch in the run's units) there
--                               to size anything tied to it (the pet strip fallback).
--   run:StartCast(startTime, endTime, isChannel [, castID]) -> true | false
--                               GetTime() seconds, PLAIN NUMBERS ONLY (see secret
--                               contract). Returns false and does nothing for a
--                               secret, a non-number, NaN, an infinity,
--                               endTime <= startTime, or a cast that ended more than
--                               the 0.5s verdict grace ago (stale: starting it would
--                               replay a lock-in). A cast that ended inside the grace
--                               window is accepted, snaps to complete and takes the
--                               normal verdict or safety-net path. castID, if given,
--                               is stored as by SetCastID (and replaces the old one).
--   run:UpdateTimes(startTime, endTime) -> true | false
--                               re-time the running cast (DELAYED, CHANNEL_UPDATE) without
--                               restarting it: lit segments keep their ignite clock and
--                               the castID is kept. Same argument gate as StartCast.
--                               False and no change when no cast is running (idle, or in
--                               hold/fade/outage) or the times are unusable.
--   run:SetCastID(id)           remember the current cast's castID (stored, never
--                               compared; a secret is fine). Cleared by StartCast.
--   run:MatchesCast(id)         true | false | nil: does an event's castID belong to
--                               the current cast? nil when either side is nil or
--                               secret. A secret is never compared.
--   run:SetProgressOverride(f)  tests: pin the elapsed fraction (nil clears it)
--   run:Succeed()               cast: hold (all lit), lock-in, fade, then onFinished. Channel: the
--                               channelFinish over the empty bar, then onFinished (at once with "none")
--   run:EndChannel() -> true | false | nil
--                               the call for CHANNEL_STOP with a nil interruptedBy. Natural end or
--                               clip is decided from the engine's own schedule (see recipe 4): a
--                               natural end plays the channel finish (true; onFinished fires at its
--                               end), a clip or "none" gets the plain Stop() (false; no onFinished,
--                               the caller goes idle), nil when it was not a running channel or a
--                               verdict is already playing.
--   run:SetChannelFinish(mode)  "drain" | "echo" | "sweep" | "ember" | "none"; false for anything else
--   run:Interrupt()             power outage, then onFinished
--   run:Stop()                  immediate hide and reset; does NOT fire onFinished
--   run:ShowIdle([dimAlpha])    same reset, but the frame stays VISIBLE showing the row of
--                               unlit chevrons (no OnUpdate): the resting look for a bar
--                               that is never blank. dimAlpha (default 0.2) is the unlit
--                               alpha for the idle row only; StartCast puts it back to
--                               0.2. Also the way out of hold/fade/outage; safe from
--                               onFinished. Does NOT fire onFinished.
--   run:IsBusy()                true from StartCast until onFinished/Stop
--   run:GetPhase()              "idle" | "cast" | "hold" | "fade" | "intr"
--   run:IsFinishing()           true in hold, fade or intr (a verdict was given)
--   run:IsComplete()            true when the cast has reached progress >= 1 and
--                               is still in phase "cast" (no verdict yet)
--   run:GetProgress()           elapsed fraction of the current cast, 0 when idle
--   run.onFinished(run)         set by the caller; fired when the fade, outage or channel
--                               finish completes, when a channel is Succeed()ed with no finish, or when
--                               the safety net below ends a channel. The run
--                               frame is left as it ended (the safety net's channel
--                               path calls Stop(), which hides it): the CALLER
--                               hides the panel.
--   run.frame                   the run's child frame (draws the segments)
--   Read-only: run.count, run.span (length the chevrons occupy along the run), run.px (one physical
--   pixel, run units), run.pitch (chevron pitch, run units), run.vertical, run.segW (chevron box
--   width, across), run.segLen (chevron box length ALONG the run: its width when horizontal, its
--   depth when vertical), run.origin (where the first chevron starts along the run, nudged onto a
--   pixel), run.xOff (vertical: the chevron column's offset from the frame's left), run.textures
--   (the resolved art paths), and for tests run.segs[i] { lit, dim, a, b, frac, x0 (along the run),
--   ign, blinks, jit, litSince }, run.phase, run.intrPhase, FS.ChevronCastBar.rngOk.
--
-- CALLER CONTRACT (verdict recipe). The engine cannot tell a finished cast from a
-- dropped event: a cast that reaches progress 1 with no verdict stays in phase
-- "cast" and IsBusy() stays true. Callers that route every spellcast event into
-- one refresh which calls StopCast when UnitCastingInfo returns nil must NOT map
-- "nil info" to run:Stop(): that would kill the 1s hold and the lock-in.
-- The recipe mirrors Blizzard's own cast bar. Reference lines are in
-- Interface/AddOns/Blizzard_UIPanels_Game/Shared/CastingBarFrame.lua of the 12.1.0
-- UI source (CBF below); UnitDocumentation.lua is in Blizzard_APIDocumentationGenerated.
--   0. START. Capture castID from UnitCastingInfo's 7th return (CBF:368, stored at
--      :423) and pass it as StartCast's 4th argument (or call SetCastID). A channel
--      has no castID from UnitChannelInfo (CBF:366; :423 sits in the non-channel
--      branch), so channels are not castID-matched: Blizzard keys them on the event
--      alone (CBF:450, :454).
--   1. COMPLETION (cast) = UNIT_SPELLCAST_STOP whose castGUID matches the current
--      cast, with no INTERRUPTED or FAILED seen first. When
--      run:MatchesCast(castGUID) == true and run:GetPhase() == "cast", call
--      Succeed(). Blizzard: CBF:132 reads castGUID, :449 requires
--      `self.casting and event == STOP and castID == self.castID`, and :459-480
--      play the finish. The "nothing seen first" half is Blizzard clearing
--      self.casting on interrupt/fail (CBF:558) so a trailing STOP no longer
--      matches; here the phase leaving "cast" (IsFinishing() true) does that job.
--      A STOP for a different castID (an instant cast mid-cast) is ignored.
--   2. UNIT_SPELLCAST_SUCCEEDED MUST NOT DRIVE THE BAR, for casts or channels.
--      It fires for every successful cast of the unit, including instants and off
--      global cooldown spells cast WHILE this cast or channel is running, with that
--      other spell's castGUID, so using it would lock in the bar early. Blizzard
--      never handles it: it is neither registered (CBF:238-251) nor in
--      OnEvent (CBF:107-157); only ActionButton.lua:1037 reacts to it. Whether it
--      also fires at channel START is UNVERIFIED: no reference file documents it
--      (UnitDocumentation.lua:4698-4710 lists only the payload). The recipe does
--      not depend on the answer.
--   3. FAILURE (cast) = UNIT_SPELLCAST_INTERRUPTED or UNIT_SPELLCAST_FAILED. Call
--      Interrupt() only when run:MatchesCast(castID) == true and
--      run:GetPhase() == "cast". Blizzard's guard is the same:
--      HandleInterruptOrSpellFailed requires `castID == self.castID` and that no
--      fade is playing (CBF:541-542; events at :143-149). A mismatch (false) is
--      IGNORED: FAILED also fires for attempts that never started a cast (spell not
--      ready, key mashing) and must not blow up a healthy bar.
--      SECRET castID (nil from MatchesCast). castGUID is secret when unit spellcasts
--      are restricted (SecretWhenUnitSpellCastRestricted: UnitDocumentation.lua:4570
--      FAILED, :4598 INTERRUPTED, :4687 STOP, :4483 CHANNEL_STOP; UnitCastingInfo's
--      castID return at :835), and tainted code cannot compare a secret. Blizzard's
--      12.1 cast bar compares castIDs with no issecretvalue guard (grep of CBF finds
--      none) because it runs untainted, so there is no addon-safe precedent to copy.
--      Fallback: on nil, INTERRUPTED still calls Interrupt() (it only fires for a
--      cast that started); FAILED is ignored unless UnitCastingInfo(unit) now
--      returns a plain nil name (check FS.IsSecret(name) first: secret means
--      unknown, so ignore), in which case call Interrupt(). Whether the player's own
--      castID is ever secret on this client is unverified.
--   4. CHANNEL END = UNIT_SPELLCAST_CHANNEL_STOP, whose 4th payload value is
--      interruptedBy (CBF:137; Blizzard's `complete = interruptedBy == nil`, :138).
--      interruptedBy non-nil (a kicked channel): call Interrupt(); Blizzard routes it
--      to the interrupt path without a castID check (CBF:452-455, :542). nil: the
--      channel stopped without a kick: call EndChannel(). A nil interruptedBy cannot
--      tell a natural end from a player clip (casting something else over Mind Flay),
--      so the ENGINE decides from its own plain GetTime schedule (StartCast / UpdateTimes
--      times): a stop within 0.15s of the scheduled end plays the channel finish, an
--      earlier one is a clip and gets the plain Stop(). The finish clock starts at the
--      EndChannel call, not at the scheduled end, so it can be up to 0.15s off it (an
--      early call also clears chevrons that were still lit). EndChannel returns true (finish
--      playing: wait for onFinished), false (it already Stop()ped: no onFinished, so the
--      caller hides the panel / goes idle) or nil (ignored). If interruptedBy is secret,
--      call Stop() directly: the quiet outcome is the safer misfire. When in doubt (a late
--      schedule) the engine errs to the plain Stop. Calling Stop() instead of EndChannel()
--      keeps the old no-animation behaviour.
--   5. While IsFinishing() is true, ignore STOP / FAILED / INTERRUPTED / refresh-nil
--      events.
--   6. Call Stop() otherwise only for a genuinely abandoned cast (unit changed, panel
--      torn down).
-- No progress threshold is part of the recipe: a castID-matched STOP is the
-- completion signal. IsComplete() / GetProgress() remain as queries for the caller's
-- own use.
-- SAFETY NET: if a cast sits at progress >= 1 with no verdict for 0.5s the engine
-- gives one itself: a cast auto-Succeed()s; a channel (which ends empty) is Stop()ped
-- and onFinished fires. A dropped event therefore cannot leave the panel stuck.
-- OnUpdate stays installed for that window and is cleared afterwards. OnUpdate does
-- NOT run while the run frame is hidden, so the caller must keep the panel (and so
-- the run frame) shown until onFinished fires, or the hold, fade, outage and safety
-- net never advance.
--
-- OWNERSHIP
--   * opts.glowBurst and the engine's own chevron burst must be DEDICATED regions:
--     their animation groups use SetToFinalAlpha, which leaves the region at alpha 0
--     when the burst ends, and OnFinished hides them. Never pass the panel's
--     permanent glow as glowBurst.
--   * The engine assumes it is the ONLY writer of alphaTarget's alpha (it caches
--     the last value it wrote and skips redundant SetAlpha calls), and StartCast
--     forces that alpha to 1. A caller that fades the same frame itself will be
--     overwritten or will desync the cache.
--
-- CARET CLIP (unverified in game). The caret glow and outline textures are regions
-- of a child frame ("body") of the frame that carries SetClipsChildren, not of the
-- clipping frame itself: the repo's convention (FrameHelpers.lua CreateCaret and
-- CreatePillBar) is that SetClipsChildren clips child FRAMES, not the clipping
-- frame's own regions. Whether the clip works on this client is not yet verified.
-- The segments sit on the run frame and never extend past it, so they are not
-- clipped.
--
-- PERFORMANCE RULES (hard):
--   * OnUpdate is installed ONLY while something animates (casting, including the
--     verdict window after progress reaches 1, hold, fade, outage) and cleared with
--     SetScript("OnUpdate", nil) otherwise.
--   * Nothing is allocated per frame: scratch tables (LOOK, CTX, IP, PH) are
--     module level, the OnUpdate closure is built once per run, textures are
--     recycled across Layout calls.
--   * Per frame the engine only touches SetVertexColor / SetShown / SetAlpha on
--     textures whose value CHANGED (each segment caches what it last applied) plus
--     the caret's one SetPoint. Nothing else is re-anchored.
--   * Scale pop (lockSnap only), glow burst, chevron burst and the ember burst are
--     native AnimationGroups built once in Create. The OnUpdate only drives what an
--     animation cannot: the segment lighting, the caret, the outage, the channel finish
--     ghosts and the frame-outline flare.
--
-- SECRET CONTRACT: StartCast times must be plain numbers the CALLER has already
-- proven non-secret. They are still checked with FS.IsSecret and type() before
-- any comparison or arithmetic; a secret (times or isChannel) refuses the cast
-- (returns false) and the engine never touches it. No secret value is ever
-- compared, formatted or used in arithmetic here. Secret-timed casts use the
-- engine-timed StatusBar path in the caller (CAST_CHEVRON_STRIP_TEXTURE), not this
-- engine.
--
-- LOAD-TIME SELF-CHECK: the PRNG is a port of the prototype's mulberry32 built on
-- the client's `bit` library. One golden draw (from the prototype's JS) is checked
-- at load; on a mismatch FS.LogDegradeOnce("chevron_rng_mismatch") is called,
-- ChevronCastBar.rngOk is false, and the engine keeps running with different (but
-- still valid) flicker patterns.
--
-- PIXEL GRID. WoW snaps every texture to the physical pixel grid on its own, so a
-- fractional pitch makes neighbouring gaps differ by a pixel and the chevrons
-- rasterize differently. Layout therefore works in whole physical pixels: one pixel
-- in the run's units is PixelUtil.GetPixelToUIUnitFactor() / frame:GetEffectiveScale()
-- (see pixelSize for the API citation), the chevron width, the arm, the gap and so the
-- pitch are whole multiples of it, and the run's origin is nudged (by under a pixel:
-- right when the slack allows, else left, so the run never passes its right edge) so
-- its left edge lands on a pixel. Every chevron is then identical and every
-- gap equal. The count rule is unchanged (as many whole chevrons as fit); the leftover
-- slack, under one pitch plus the pixel rounding of the width, sits at the FAR end of
-- the run and the chevrons are never stretched. Progress maps onto the SPAN the
-- chevrons occupy (run.span), not the run width, so the last chevron lights exactly
-- at 1.0: seg.a / seg.b / seg.frac, the caret x and the burst all use the span.
-- The pixel size changes with UI scale, display size or an ancestor's scale, so the
-- run re-lays out (RefreshPixels) on those and ONLY when the computed pixel size
-- changed; OnUpdate never queries it.
--
-- VERTICAL RUNS use the same grid on the Y axis (opts.vertical): the chevron box, the pitch and the span
-- are whole physical pixels, the first chevron's bottom edge is nudged onto a pixel from a pcall'd
-- GetBottom (up when the slack allows, else down), the column's left edge from GetLeft, the leftover
-- slack is at the TOP, and progress maps onto run.span, so the top chevron lights exactly at 100%.
--
-- FX (FS.ChevronCastBar.Fx). The file-local motion functions the runs use, exported so another piece of
-- UI (the Gunsight toggle key rings) can reuse the exact ignite flicker and power outage in its own
-- colour: rng, makeBusyFlicker, makeFlicker, flick, phaseOf, intrParams, segLook, bumps / bumpA / bumpB,
-- stutterTint, lockInFlare, ease / spike / mix / clamp, plus MakePalette(colors [, reducedMotion]) (the
-- run's colour fields, base passed in: { base, warm, core, text } as { r, g, b }), NewSeg(seed),
-- NewContext(), SeedFor(salt, index), GetBoost() and the constants INT_FR, SURGE, DIM_ALPHA, INTR_MS,
-- FADE_MS, LOCK_MS, FLARE_MS, HOLD_MS, HOLD_GLOW_ALPHA, WARM, CORE, TEXT. They are the engine's own
-- functions, not copies, so the two cannot drift; the recipe is at the definition (search "FX.").
--
-- Known divergences from the prototype (documentation only):
--   * The engine and the mockup now agree on the layout: an exact integer pitch, no
--     stretching, the slack at the far (right) end. The only difference is rounding:
--     here the chevron width, arm and gap are rounded to whole PHYSICAL pixels (the
--     mockup's are integer CSS pixels), so a segment can sit up to half a pixel off
--     the JS one.
--   * The pet bar must pass gapFraction 0.2 (see opts.gapFraction); the default is
--     the player bar's, and a pet bar left on it gets the wrong pitch and count.
--   * After an outage the prototype ramps the frame alpha back 0.3 -> 1 over 200ms
--     (its restore step). This engine has no such ramp: the caller hides the panel
--     at onFinished and Stop()/StartCast put the alpha straight back to 1.
--   * Animation easing is approximated with the native AnimationGroup smoothings:
--     the chevron burst, glow burst and scale pop use "OUT" where the prototype
--     runs its own hand-written curves per frame, so their in-between values (not
--     their start and end) differ slightly. The channel finish's glint fades are linear
--     (the mockup's are (1 - u)^1.2) and its glow burst is one scale-out plus alpha, not
--     the mockup's stroke width ramp. The echo, sweep and ember ghosts are per-frame ports
--     of the mockup's chanGhost (same timing, ease and spike curves).
--   * Fit width: the mockup's build() always grows the bar by one full pitch minus the
--     slack, so a run that already fits still gains a chevron. FitWidth returns an exact
--     fit unchanged (the smallest width that works); for any run with slack the two
--     agree.
--
-- The channel finish styles (drain, echo, sweep, ember) are ports of the Channel finish gallery in
-- the cast bar comparison mockup (castbar-v2-compare): chanGhost, flareFx and glintFx timings.
--
-- Not ported from the prototype (not part of the locked spec): the Busy and
-- Calm flicker styles, the cast finish wave/chase, the lock-in modes other than "all",
-- the other segment shapes. makeBusyFlicker IS ported because Medium inherits
-- the segment's `jit` from it.

local _, FS = ...
local Theme = FS.Theme
local IsSecret = FS.IsSecret

local ChevronCastBar = {}
FS.ChevronCastBar = ChevronCastBar

-- The up-pointing art set (media/generate_cast_chevron_up.py), for opts.textures. Not Theme tokens: the
-- engine is the only reader.
local MEDIA = "Interface\\AddOns\\ForeverSynthwave\\media\\"
ChevronCastBar.TEXTURES_UP = {
    fill = MEDIA .. "cast_chevron_up_fill.tga",       -- 64x32
    outline = MEDIA .. "cast_chevron_up_outline.tga", -- 64x32, the bigger hollow caret
    glow = MEDIA .. "cast_chevron_up_glow.tga",       -- 128x64, drawn 2x, centred
    burst = MEDIA .. "cast_chevron_up_burst.tga",     -- 128x64, drawn 2x, centred
    strip = MEDIA .. "cast_chevron_up_strip.tga",     -- 32x16, one chevron per 16 texels
}

local Run = {}
Run.__index = Run

local floor, min, max, sin, pi = math.floor, math.min, math.max, math.sin, math.pi

-------------------------------------------------------------------------------
-- Constants (the prototype's, same names and values)
-------------------------------------------------------------------------------

local FADE_MS = 300
local LOCK_MS = 360        -- lock-in window, starts with the hold
local POP_MS = 180         -- scale pop part of the lock-in (opts.lockSnap only; off by default)
local FLARE_MS = 250       -- frame flare easing back
local HOLD_MS = 1000
local INTR_MS = 1000
local CHANNEL_STAGGER_MS = 350
local VERDICT_GRACE = 0.5  -- seconds a finished cast waits for a verdict before the safety net acts
-- Channel finish (a channel that runs out). WAVE_MS is the sweep's wave length, EMBER_MS the last
-- ember's longest effect and MIN_FINISH_MS the shortest finish worth playing (all the mockup's).
-- NATURAL_SLACK_S is how far before the engine's own scheduled end a non-interrupted
-- CHANNEL_STOP still counts as the natural end (event latency, a tick landing early): a stop
-- earlier than that is a clip (the player cast something else), which gets the plain Stop.
local WAVE_MS = 300
local EMBER_MS = 600
local MIN_FINISH_MS = 80
local REDUCED_FINISH_MS = 200
local NATURAL_SLACK_S = 0.15
local CHANNEL_FINISHES = { drain = true, echo = true, sweep = true, ember = true, none = true }
local DEFAULT_CHANNEL_FINISH = "drain"
local INT_FR = { brown = 0.25, stutter = 0.30, cut = 0.25, fade = 0.20 }
local SURGE = 0.6
local DIM_ALPHA = 0.2      -- unlit chevron (H card: cyan @ 0.2)
local HOLD_GLOW_ALPHA = 0.7
local GLOW_SCALE = 1 + 2 * (Theme.CAST_CHEVRON_GLOW_PAD_FRACTION or 0.5)

local WARM = { 1, 0.239, 0.122 }              -- #ff3d1f
local CORE = { 0.918, 0.988, 1 }              -- #eafcff
local TEXT = { 0.886, 0.910, 0.941 }          -- #e2e8f0

-- Vertical runs (the Gunsight tapes). The mockup's chevron (chevPath with d 8, t 5.5) is 13.5 image px
-- deep and seats 12.2 apart, the mockup's default wide (hw 14) one 28 across (the Gunsight tapes
-- themselves run hw 10, 20 across); the caret is drawn with (hw + 3, d + 1,
-- t 7): 3 image px wider each side and 16 deep. Everything is a fraction of the chevron's own depth, so
-- one unit u = chevronHeight / 13.5 sizes it (media/generate_cast_chevron_up.py has the geometry).
local VERT_H_FRACTION = 13.5 / 28        -- default chevron depth over its width
local VERT_PITCH_FRACTION = 12.2 / 13.5  -- default pitch over the chevron depth
local VERT_DEPTH_UNITS = 13.5
local CARET_PAD_UNITS = 3                -- caret box wider than the chevron by this, each side
local CARET_DEPTH_UNITS = 16
local STRIP_TEXELS_PER_CHEVRON = 16      -- both strip tiles: 32x16 up (one chevron) and 32x16 across (two, 16 each)

-------------------------------------------------------------------------------
-- Helpers
-------------------------------------------------------------------------------

local function clamp(v) return v < 0 and 0 or (v > 1 and 1 or v) end
local function ease(u) return u * u * (3 - 2 * u) end
-- Sharp attack to 1 at u = pk, then an ease back to 0 by u = 1 (power pw, default 2).
local function spike(u, pk, pw)
    if u < pk then return u / pk end
    return (1 - clamp((u - pk) / (1 - pk))) ^ (pw or 2)
end
local function mix(ar, ag, ab, br, bg, bb, t)
    return ar + (br - ar) * t, ag + (bg - ag) * t, ab + (bb - ab) * t
end

local function pickColor(opt, default)
    local c = opt or default
    return c[1], c[2], c[3]
end

-- Writes the colour fields segLook, colorOf and the channel finish ghosts read onto `t`: the base, the
-- warm (outage tint), the core (near-white), the text (settle overshoot) and the pale off-hue flash
-- (the base pulled 60% toward the text). `t` is a run, or a bare table from Fx.MakePalette; nothing
-- else about the colours is hard-wired, so a consumer with another base colour (the toggle key rings)
-- gets the same motion in its own hue.
local function applyPalette(t, colors)
    colors = colors or {}
    t.baseR, t.baseG, t.baseB = pickColor(colors.base, Theme.COLOR_POWER)
    t.warmR, t.warmG, t.warmB = pickColor(colors.warm, WARM)
    t.coreR, t.coreG, t.coreB = pickColor(colors.core, CORE)
    t.textR, t.textG, t.textB = pickColor(colors.text, TEXT)
    t.paleR, t.paleG, t.paleB = mix(t.baseR, t.baseG, t.baseB, t.textR, t.textG, t.textB, 0.6)
    return t
end

-- One physical pixel in `frame`'s own coordinate units: the client's UI-unit size of a
-- pixel over the frame's effective scale. API, as dumped for interface 16001
-- (reference/wow-api-dump-16001/globals.txt): line 39479 `PixelUtil table` (its
-- GetPixelToUIUnitFactor is 768 / physical height, Blizzard_SharedXML/PixelUtil.lua:3-6,
-- used as factor / GetEffectiveScale in Blizzard_GlueParent) and line 24254
-- `GetPhysicalScreenSize function`; frame:GetEffectiveScale is in widgets.txt. The
-- dump lists only the PixelUtil table, not its members, so the member is feature
-- detected and the fallback is the same 768 / physical height. Neither value is ever
-- secret; the IsSecret / type gates only keep a bad return from poisoning the layout.
local degradeLogged = false
local function pixelSize(frame)
    local factor
    if type(PixelUtil) == "table" and type(PixelUtil.GetPixelToUIUnitFactor) == "function" then
        factor = PixelUtil.GetPixelToUIUnitFactor()
    elseif type(GetPhysicalScreenSize) == "function" then
        local _, physH = GetPhysicalScreenSize()
        if type(physH) == "number" and not IsSecret(physH) and physH > 0 then factor = 768 / physH end
    end
    if type(factor) ~= "number" or IsSecret(factor) or factor ~= factor or factor <= 0 then
        -- Neither API answered: snap to whole UI units rather than not at all.
        factor = 1
        if not degradeLogged and FS.LogDegradeOnce then
            degradeLogged = true
            FS.LogDegradeOnce("chevron_no_pixel_api",
                "ForeverSynthwave: ChevronCastBar found no PixelUtil / GetPhysicalScreenSize; chevrons snap to whole UI units")
        end
    end
    local scale = frame:GetEffectiveScale()
    -- Not laid out yet (0 or nil) reads as 1; the OnShow / StartCast check corrects it.
    if type(scale) ~= "number" or IsSecret(scale) or scale ~= scale or scale <= 0 then scale = 1 end
    return factor / scale
end

-- One event watcher and one SetScale post-hook per ancestor frame, shared by every run
-- (a per-run wrapper would stack on UIParent for good). `runs` is weak only so the
-- registry itself adds no reference: a run lives as long as its frame in practice,
-- because the frame's OnShow HookScript closure holds the run, and frames are never
-- collected.
local runs = setmetatable({}, { __mode = "k" })
local hookedFrames = setmetatable({}, { __mode = "k" })
local watcher

-- Each run is refreshed under its own pcall so one bad run cannot skip the rest; the
-- error still goes to the client's handler.
local function refreshAll()
    for run in pairs(runs) do
        local okr, err = pcall(run.RefreshPixels, run)
        if not okr and type(geterrorhandler) == "function" then geterrorhandler()(err) end
    end
end

-- Registers `run` and hooks SetScale on its frame and every ancestor not hooked yet.
-- Each hook is its own pcall, a frame counts as hooked only once its hook took, and
-- the walk continues upward after a failure (a refused frame is retried by the next run).
local function watchPixels(run)
    runs[run] = true
    if not watcher then
        watcher = CreateFrame("Frame")
        watcher:RegisterEvent("UI_SCALE_CHANGED")
        watcher:RegisterEvent("DISPLAY_SIZE_CHANGED")
        watcher:SetScript("OnEvent", refreshAll)
    end
    if type(hooksecurefunc) ~= "function" then return end
    local f = run.frame
    while f do
        if f.SetScale and not hookedFrames[f] and pcall(hooksecurefunc, f, "SetScale", refreshAll) then
            hookedFrames[f] = true
        end
        local gotParent, parent = pcall(f.GetParent or error, f)
        f = gotParent and parent or nil
    end
end

-------------------------------------------------------------------------------
-- Seeded PRNG: mulberry32, a line for line port of the prototype's rng().
-- Math.imul is rebuilt from 16 bit halves because a plain double multiply loses
-- the low bits above 2^53. Every result is normalised back to 0 .. 2^32 - 1.
-------------------------------------------------------------------------------

local TWO32 = 4294967296

local function imul(a, b)
    local ah, al = floor(a / 65536), a % 65536
    local bh, bl = floor(b / 65536), b % 65536
    return (al * bl + ((ah * bl + al * bh) % 65536) * 65536) % TWO32
end

local function rng(seed)
    local s = seed % TWO32
    return function()
        s = (s + 0x6D2B79F5) % TWO32
        local t = s
        t = imul(bit.bxor(t, bit.rshift(t, 15)) % TWO32, bit.bor(t, 1) % TWO32)
        t = bit.bxor(t, (t + imul(bit.bxor(t, bit.rshift(t, 7)) % TWO32, bit.bor(t, 61) % TWO32)) % TWO32) % TWO32
        return (bit.bxor(t, bit.rshift(t, 14)) % TWO32) / TWO32
    end
end

-- Load-time self-check: the first draw of rng(12345) as the prototype's own JS
-- produces it (node, 2026-10-01). A client whose `bit` library diverges would
-- otherwise just flicker differently, silently.
local RNG_GOLDEN_SEED, RNG_GOLDEN = 12345, 0.9797282677609473
ChevronCastBar.rngOk = true
do
    local good, draw = pcall(function() return rng(RNG_GOLDEN_SEED)() end)
    if not good or type(draw) ~= "number" or math.abs(draw - RNG_GOLDEN) > 1e-12 then
        ChevronCastBar.rngOk = false
        if FS.LogDegradeOnce then
            FS.LogDegradeOnce("chevron_rng_mismatch",
                "ForeverSynthwave: ChevronCastBar PRNG does not match the prototype (bit library differs); flicker patterns will differ")
        end
    end
end

-------------------------------------------------------------------------------
-- Flicker (Layout time only; allocation is fine here, never per frame)
-------------------------------------------------------------------------------

-- Busy flicker. Only its `jit` (and the rng sequence that produces it) is used
-- by Medium, but the whole sequence must run to land on the same jit value.
local function makeBusyFlicker(seed)
    local r = rng(seed)
    local ign = 250 + floor(r() * 150)
    local nb = 3 + floor(r() * 3)
    local ws, tot = {}, 0
    for i = 0, nb * 2 do
        local w
        if i % 2 == 0 then w = 0.5 + r() * 1.4 else w = 0.35 + r() * 0.8 end
        ws[#ws + 1] = w
        tot = tot + w
    end
    local span, t, blinks, hasAlt = 0.78, 0, {}, false
    for i = 0, #ws - 1 do
        local d = ws[i + 1] / tot * span
        if i % 2 == 1 then
            local pick = r()
            local code = pick < 0.34 and 1 or (pick < 0.68 and 2 or 4)
            if code == 2 then hasAlt = true end
            blinks[#blinks + 1] = { t0 = t, t1 = t + d, code = code }
        end
        t = t + d
    end
    if not hasAlt and #blinks > 0 then blinks[floor(r() * #blinks) + 1].code = 2 end
    return { ign = ign, blinks = blinks, jit = r() }
end

-- Medium: two blinks over about 200ms, off-hue flash on about 1 in 3. Writes
-- straight into the segment (seg.blinks keeps its two preallocated entries).
local function makeFlicker(seg, seed)
    local fk = makeBusyFlicker(seed)
    local r = rng(seed + 31)
    local alt = r() < 0.34
    local a0 = 0.04 + r() * 0.06
    local b0 = 0.40 + r() * 0.08
    seg.ign = 190 + floor(r() * 30)
    local b1, b2 = seg.blinks[1], seg.blinks[2]
    b1.t0, b1.t1, b1.code = a0, a0 + 0.2, alt and 2 or 1
    b2.t0, b2.t1, b2.code = b0, b0 + 0.18, 4
    seg.settle = 0.75
    seg.boostMax = 0.3
    seg.jit = fk.jit
end

-- Returns 0 off, 1 dim, 2 off-hue flash, 3 lit, 4 mid, 5 faint off-hue. Sets
-- BOOST for the settle overshoot. age is in ms.
local BOOST = 0
local function flick(seg, age)
    BOOST = 0
    if age < 0 then return 0 end
    local u = age / seg.ign
    if u >= 1 then return 3 end
    if u >= seg.settle then
        local k = (u - seg.settle) / (1 - seg.settle)
        BOOST = seg.boostMax * (1 - k) * (1 - k)
        return 3
    end
    local blinks = seg.blinks
    for i = 1, #blinks do
        local b = blinks[i]
        if u >= b.t0 and u < b.t1 then return b.code end
    end
    return 0
end

-------------------------------------------------------------------------------
-- Interrupt (power outage). PH and IP are shared scratch tables: no allocation.
-------------------------------------------------------------------------------

local PH = { phase = "brown", u = 0, uT = 0 }
local IP = { level = 1, tint = 0, cutU = -1, reduced = false, dead = false }

local function phaseOf(uT)
    local b = INT_FR.brown
    local s = b + INT_FR.stutter
    local c = s + INT_FR.cut
    PH.uT = uT
    if uT < b then PH.phase, PH.u = "brown", uT / b
    elseif uT < s then PH.phase, PH.u = "stutter", (uT - b) / INT_FR.stutter
    elseif uT < c then PH.phase, PH.u = "cut", (uT - s) / INT_FR.cut
    else PH.phase, PH.u = "fade", (uT - c) / INT_FR.fade end
    return PH
end

local function pulse(u, a, b, h)
    if u < a or u > b then return 0 end
    return h * sin(pi * (u - a) / (b - a))
end
-- Two uneven flickers on top of the 0.4 floor, each surging up to full lit
-- (0.4 + 0.6). The second is the last one before the cut-out.
local function bumpA(u, j) return pulse(u, 0.12 + j * 0.06, 0.30 + j * 0.04, SURGE) end
local function bumpB(u, j) return pulse(u, 0.55 + j * 0.05, 0.72, SURGE) end
local function bumps(u, j) return max(bumpA(u, j), bumpB(u, j)) end
-- Brownout red tint fades out at a surge peak and returns in the troughs.
local function stutterTint(u, j) return 0.55 * (1 - bumps(u, j) / SURGE) end

local function intrParams(intr)
    if not intr then
        IP.level, IP.tint, IP.cutU, IP.reduced, IP.dead = 1, 0, -1, false, false
        return IP
    end
    local ph = intr.phase
    if ph == "reduced" then
        IP.level, IP.tint, IP.cutU, IP.reduced, IP.dead = 1 - intr.uT, 0, -1, true, false
        return IP
    end
    local e = ease(intr.u)
    IP.reduced, IP.dead = false, false
    if ph == "brown" then
        IP.level, IP.tint, IP.cutU = 1 - 0.6 * e, 0.55 * e, -1
    elseif ph == "stutter" then
        IP.level, IP.tint, IP.cutU = 0.4 + bumps(intr.u, 0.5), stutterTint(intr.u, 0.5), -1
    elseif ph == "cut" then
        IP.level, IP.tint, IP.cutU = 0.4, 0.55, intr.u
    else
        IP.level, IP.tint, IP.cutU, IP.dead = 0, 0.55, -1, true
    end
    return IP
end

-------------------------------------------------------------------------------
-- Segment look
-------------------------------------------------------------------------------

-- Scratch: segLook writes LOOK.alpha (0 = unlit), LOOK.r/g/b, LOOK.anim.
local LOOK = { alpha = 0, r = 0, g = 0, b = 0, anim = false }
-- Scratch context filled by paintAll: lit, snap, level, fadeLit, extent, intr, ip.
local CTX = { lit = false, snap = false, level = 1, fadeLit = 1, extent = 1, intr = nil, ip = IP }

local function colorOf(run, tint, boost)
    local r, g, b = run.baseR, run.baseG, run.baseB
    if tint ~= 0 then r, g, b = mix(r, g, b, run.warmR, run.warmG, run.warmB, tint) end
    if boost ~= 0 then r, g, b = mix(r, g, b, run.textR, run.textG, run.textB, boost) end
    LOOK.r, LOOK.g, LOOK.b = r, g, b
end

local function segLook(run, seg, now, c)
    LOOK.anim = false
    LOOK.alpha = 0
    if not c.lit then seg.litSince = false; return LOOK end
    if seg.litSince == false then seg.litSince = now end
    if c.snap then seg.litSince = -1e9 end
    local code, boost = 3, 0
    if not run.reducedMotion and not c.snap then
        local age = now - seg.litSince
        if age < seg.ign then LOOK.anim = true; code = flick(seg, age); boost = BOOST end
    end
    local ip, intr = c.ip, c.intr
    local lvl, tn, hot = c.level, ip.tint, 0
    if intr and not ip.reduced then
        local ph = intr.phase
        if ph == "stutter" then
            lvl = c.fadeLit * (0.4 + bumps(intr.u, seg.jit))
            tn = stutterTint(intr.u, seg.jit)
            hot = 0.3 * bumpB(intr.u, seg.jit) / SURGE
        elseif ph == "cut" then
            -- The segment nearest the leading edge goes first; jit staggers neighbours.
            local t = 1 - clamp(seg.a / max(c.extent, 1e-6))
            local thr = min(0.97, 0.9 * t + seg.jit * 0.08)
            if intr.u > thr then return LOOK end
        elseif ph == "fade" then
            return LOOK
        end
    end
    if code == 0 then return LOOK end
    if code == 1 then
        colorOf(run, tn, 0); LOOK.alpha = 0.35 * lvl
    elseif code == 2 then
        LOOK.r, LOOK.g, LOOK.b = run.paleR, run.paleG, run.paleB; LOOK.alpha = 0.95 * lvl
    elseif code == 4 then
        colorOf(run, tn, 0); LOOK.alpha = 0.8 * lvl
    elseif code == 5 then
        LOOK.r, LOOK.g, LOOK.b = run.paleR, run.paleG, run.paleB; LOOK.alpha = 0.5 * lvl
    else
        colorOf(run, tn, boost)
        if hot > 0 then
            local r, g, b = run.baseR, run.baseG, run.baseB
            if tn ~= 0 then r, g, b = mix(r, g, b, run.warmR, run.warmG, run.warmB, tn) end
            LOOK.r, LOOK.g, LOOK.b = mix(r, g, b, run.coreR, run.coreG, run.coreB, hot)
        end
        LOOK.alpha = lvl
    end
    return LOOK
end

-- Lock-in frame flare: sharp attack, then ease back to the base outline color.
local function lockInFlare(lt)
    local u = clamp(lt / FLARE_MS)
    if u < 0.12 then return u / 0.12 end
    local k = 1 - (u - 0.12) / 0.88
    return k * k
end

-- The seed a run gives chevron `i` (1 based) of a bar with salt `salt` (the prototype's
-- (72 * 131 + salt) * 1009 + i * 7919 + 12345). Exported so another consumer can flicker identically.
local function flickerSeed(salt, i)
    return (72 * 131 + salt) * 1009 + (i - 1) * 7919 + 12345
end

-- A bare segment for a consumer that has no textures of its own to light (the toggle key rings): the
-- fields makeFlicker, flick and segLook read and write, ignited from the given seed.
local function newFxSeg(seed)
    local seg = {
        blinks = { { t0 = 0, t1 = 0, code = 1 }, { t0 = 0, t1 = 0, code = 4 } },
        a = 0, b = 0, frac = 0, x0 = 0, ign = 200, jit = 0, settle = 0.75, boostMax = 0.3,
        litSince = false,
    }
    makeFlicker(seg, seed or 0)
    return seg
end

-- The scratch table segLook reads its per-frame inputs from (paintAll's CTX is the engine's own).
local function newFxContext()
    return { lit = false, snap = false, level = 1, fadeLit = 1, extent = 1, intr = nil, ip = IP }
end

-- FX. The motion, exported for other consumers: the exact ignite flicker (makeFlicker / flick) and
-- power outage (phaseOf / intrParams / segLook) the cast runs use, with the BASE COLOUR passed in
-- through a palette instead of hard-wired. To drive your own pieces:
--     local pal = Fx.MakePalette({ base = { r, g, b } })          -- warm / core / text optional
--     local seg = Fx.NewSeg(Fx.SeedFor(salt, i))                 -- one per piece; seg.litSince = false
--     local ctx = Fx.NewContext()
--     ctx.lit, ctx.snap, ctx.level, ctx.fadeLit, ctx.extent = isLit, false, 1, 1, 1
--     ctx.intr = Fx.phaseOf(uT); ctx.ip = Fx.intrParams(ctx.intr)  -- or intr nil, ip = Fx.intrParams(nil)
--     local look = Fx.segLook(pal, seg, nowMs, ctx)                -- look.alpha 0 = off, look.r/g/b
-- segLook starts a segment's ignite clock the first frame it is lit and clears it when it is not;
-- seg.a is the piece's start along the 0..1 run (the outage cuts the leading edge first, ctx.extent
-- being the lit front). The returns are SHARED SCRATCH tables (segLook's look, phaseOf's PH,
-- intrParams' IP, GetBoost's BOOST): read them at once, never keep them across calls. Allocation free
-- per call. INTR_MS is the outage length (1.0s) the phaseOf argument is a fraction of.
ChevronCastBar.Fx = {
    rng = rng, makeBusyFlicker = makeBusyFlicker, makeFlicker = makeFlicker, flick = flick,
    phaseOf = phaseOf, intrParams = intrParams, segLook = segLook,
    bumps = bumps, bumpA = bumpA, bumpB = bumpB, stutterTint = stutterTint, lockInFlare = lockInFlare,
    ease = ease, spike = spike, mix = mix, clamp = clamp,
    MakePalette = function(colors, reducedMotion)
        local pal = applyPalette({}, colors)
        pal.reducedMotion = reducedMotion and true or false
        return pal
    end,
    NewSeg = newFxSeg,
    NewContext = newFxContext,
    SeedFor = flickerSeed,
    GetBoost = function() return BOOST end,
    INT_FR = INT_FR, SURGE = SURGE, DIM_ALPHA = DIM_ALPHA, INTR_MS = INTR_MS, FADE_MS = FADE_MS,
    LOCK_MS = LOCK_MS, FLARE_MS = FLARE_MS, HOLD_MS = HOLD_MS, HOLD_GLOW_ALPHA = HOLD_GLOW_ALPHA,
    WARM = WARM, CORE = CORE, TEXT = TEXT,
}

-- Channel finish ghost for one chevron, ft ms into a finish fd ms long (the mockup's chanGhost).
-- Writes GH.a (opacity, 0 = none) and GH.k (near-white mix, 0 .. 1). Echo: the whole row as a
-- near-white ghost that settles to the base color and fades. Sweep: a wave from the left end to the
-- right, then a cyan afterglow. Ember: only the last chevron to go out (the leftmost, segs[1]).
-- Reduced motion drops the whitening, the wave and the ember's pop.
local GH = { a = 0, k = 0 }
local function chanGhost(run, seg, mode, ft, fd)
    local u = clamp(ft / fd)
    local a, k = 0, 0
    local red = run.reducedMotion
    if mode == "echo" then
        a = 0.6 * (1 - u) * clamp(ft / 40)
        k = red and 0 or 0.9 * (1 - ease(clamp(ft / 300)))
    elseif mode == "sweep" then
        if red then
            a = 0.5 * (1 - u)
        else
            local w = min(WAVE_MS, fd)
            local fl = w * 0.5
            local t0 = seg.frac * (w - fl)
            local uu = (ft - t0) / fl
            if uu > 0 then
                k = spike(uu, 0.2)
                local tail = 0.4 * (1 - clamp((ft - t0 - fl * 0.2) / max(1, fd - t0 - fl * 0.2)))
                a = uu < 0.2 and k or max(k, tail)
            end
        end
    elseif mode == "ember" and seg == run.segs[1] then
        local eu = clamp(ft / min(fd, EMBER_MS))
        a = spike(eu, 0.1, 1.5)
        k = red and 0 or 1 - ease(eu)
    end
    GH.a, GH.k = a, k
end

-------------------------------------------------------------------------------
-- Painting (only touches an engine object when its value changed)
-------------------------------------------------------------------------------

local function paintSeg(seg, lk)
    local a = lk.alpha
    if a <= 0 then
        if seg.shown ~= false then seg.lit:SetShown(false); seg.shown = false end
        return
    end
    local r, g, b = lk.r, lk.g, lk.b
    if r ~= seg.cr or g ~= seg.cg or b ~= seg.cb or a ~= seg.ca then
        seg.lit:SetVertexColor(r, g, b, a)
        seg.cr, seg.cg, seg.cb, seg.ca = r, g, b, a
    end
    if seg.shown ~= true then seg.lit:SetShown(true); seg.shown = true end
end

-- Lights each segment from the caret position f (cast: once f has cleared its
-- END; channel, mirrored: it stays lit until f passes its START) and paints it.
-- Returns true while any segment is still mid-flicker.
local function paintAll(run, nowMs, f, hold, snap, level, fadeLit, intr)
    local ctx = CTX
    ctx.snap, ctx.level, ctx.fadeLit, ctx.extent, ctx.intr, ctx.ip = snap, level, fadeLit, f, intr, IP
    local channel = run.channel
    local segs = run.segs
    local anim = false
    for i = 1, run.count do
        local seg = segs[i]
        local lit = hold
        if not lit then
            if channel then lit = f > seg.a else lit = f >= seg.b end
        end
        ctx.lit = lit
        local lk = segLook(run, seg, nowMs, ctx)
        if lk.anim then anim = true end
        paintSeg(seg, lk)
    end
    return anim
end

-- Paints the channel finish ghosts (ember: the one chevron it uses). Nothing allocates.
local function paintGhosts(run, mode, ft, fd)
    local segs = run.segs
    local last = mode == "ember" and 1 or run.count
    for i = 1, last do
        local seg = segs[i]
        chanGhost(run, seg, mode, ft, fd)
        local k = GH.k
        if k > 0 then
            LOOK.r, LOOK.g, LOOK.b = mix(run.baseR, run.baseG, run.baseB, run.coreR, run.coreG, run.coreB, k)
        else
            LOOK.r, LOOK.g, LOOK.b = run.baseR, run.baseG, run.baseB
        end
        LOOK.alpha = GH.a
        paintSeg(seg, LOOK)
    end
end

-- Hides every lit chevron (the bar is empty again).
local function clearLit(run)
    LOOK.alpha = 0
    for i = 1, run.count do paintSeg(run.segs[i], LOOK) end
end

local function setCaretShown(run, show)
    if run.caretShown ~= show then
        run.clip:SetShown(show)
        run.caretShown = show
    end
end

-- The caret's tip sits at f * span past the run's origin (the span the chevrons
-- occupy, so the tip is at the last chevron's end at f = 1). One SetPoint per frame,
-- and none when the position did not change.
local function placeCaret(run, f, show)
    if not show then setCaretShown(run, false); return end
    if run.vertical then
        -- The tip is the box's TOP edge for a cast (the art points up) and its BOTTOM edge for a
        -- flipped channel. caretX caches the along-axis position of the box's bottom.
        local y = run.origin + f * run.span
        local cy0 = run.channel and y or (y - run.capH)
        if cy0 ~= run.caretX then
            run.outline:SetPoint("BOTTOMLEFT", run.body, "BOTTOMLEFT", run.capX, cy0)
            run.caretX = cy0
        end
        setCaretShown(run, true)
        return
    end
    local x = run.originX + f * run.span
    local cx0 = run.channel and x or (x - run.segW)
    if cx0 ~= run.caretX then
        run.outline:SetPoint("TOPLEFT", run.body, "TOPLEFT", cx0, 0)
        run.caretX = cx0
    end
    setCaretShown(run, true)
end

local function setAlphaTarget(run, a)
    if run.atAlpha ~= a then
        run.alphaTarget:SetAlpha(a)
        run.atAlpha = a
    end
end

local function setFlare(run, fk)
    local t = run.flareTarget
    if not t then return end
    local base = run.flareBase
    if fk <= 0 then
        t:SetVertexColor(base[1], base[2], base[3], base[4] or 1)
        run.flareOn = false
        return
    end
    local r, g, b = mix(base[1], base[2], base[3], run.coreR, run.coreG, run.coreB, fk)
    t:SetVertexColor(r, g, b, base[4] or 1)
    run.flareOn = true
end

local function setHoldGlow(run, a)
    local g = run.holdGlow
    if g and run.glowAlpha ~= a then
        g:SetAlpha(a)
        run.glowAlpha = a
    end
end

-------------------------------------------------------------------------------
-- Lock-in / cancellation (native AnimationGroups)
-------------------------------------------------------------------------------

-- Centers the chevron burst on the last chevron (right end, cast lock-in) or on the first (left
-- end, mirrored to point left: the channel finish). Geometry comes from the last Layout.
local function placeBurst(run, left)
    run.burstLeft = left
    run.burst:ClearAllPoints()
    if run.vertical then
        -- `left` means the START end here: the first (bottom) chevron, art flipped to point down.
        local cy = left and (run.origin + run.segLen / 2) or (run.origin + run.span - run.segLen / 2)
        run.burst:SetPoint("CENTER", run.frame, "BOTTOMLEFT", run.xOff + run.segW / 2, cy)
        if left then run.burst:SetTexCoord(0, 1, 1, 0) else run.burst:SetTexCoord(0, 1, 0, 1) end
        return
    end
    local cx = left and (run.originX + run.segW / 2) or (run.originX + run.span - run.segW / 2)
    run.burst:SetPoint("CENTER", run.frame, "TOPLEFT", cx, -run.H / 2)
    if left then run.burst:SetTexCoord(1, 0, 0, 1) else run.burst:SetTexCoord(0, 1, 0, 1) end
end

local function stopGroup(g, region)
    if g then g:Stop() end
    if region then region:Hide() end
end

-- Cancels anything the hold/lock-in/outage left running or showing.
local function resetEffects(run)
    stopGroup(run.burstGroup, run.burst)
    if run.emberGroup then run.emberGroup:Stop() end
    if run.popGroup then run.popGroup:Stop() end
    if run.burstLeft then placeBurst(run, false) end
    stopGroup(run.glowGroup, run.glowBurst)
    if run.flareOn then setFlare(run, 0) end
    setHoldGlow(run, 0)
    setAlphaTarget(run, 1)
end

-- The outer glow burst (lock-in and the echo/drain channel finishes).
local function playGlow(run)
    local g = run.glowBurst
    if run.glowGroup then
        if g then
            if run.glowScale then
                local gw, gh = g:GetSize()
                local e = run.glowExpand
                -- A secret size cannot be compared: skip the sizing and keep the
                -- scale the group was built with.
                if not IsSecret(gw) and not IsSecret(gh) and gw and gw > 0 and gh and gh > 0 then
                    run.glowScale:SetScaleTo(1 + 2 * e / gw, 1 + 2 * e / gh)
                end
            end
            g:Show()
        end
        run.glowGroup:Stop()
        run.glowGroup:Play()
    end
end

-- The chevron burst on the end cap (or, for a channel finish, the left end).
local function playBurst(run, group)
    run.burst:Show()
    group:Stop()
    group:Play()
end

-- The lock-in is flash + glow burst + chevron burst; the scale pop joins only with opts.lockSnap.
local function playLockIn(run)
    playGlow(run)
    playBurst(run, run.burstGroup)
    if run.popGroup then
        run.popGroup:Stop()
        run.popGroup:Play()
    end
end

-------------------------------------------------------------------------------
-- Phase ticks
-------------------------------------------------------------------------------

local function clearOnUpdate(run)
    if run.updating then
        run.frame:SetScript("OnUpdate", nil)
        run.updating = false
    end
end

local function setOnUpdate(run)
    if not run.updating then
        run.frame:SetScript("OnUpdate", run.onUpdate)
        run.updating = true
    end
end

-- Ends the run: clears OnUpdate FIRST so a re-entrant StartCast from the
-- callback can install its own.
local function finish(run)
    run.phase = "idle"
    clearOnUpdate(run)
    if run.flareOn then setFlare(run, 0) end
    setHoldGlow(run, 0)
    setCaretShown(run, false)
    local cb = run.onFinished
    if cb then cb(run) end
end

local function progressOf(run, nowSec)
    local o = run.override
    if o then return o end
    local d = run.dur
    if d <= 0 then return 1 end
    return clamp((nowSec - run.start) / d)
end

local function tickCast(run, nowSec, nowMs)
    local p = progressOf(run, nowSec)
    run.p = p
    local f = run.channel and 1 - p or p
    local snap = run.snapNext
    run.snapNext = false
    setAlphaTarget(run, 1)
    intrParams(nil)
    local anim = paintAll(run, nowMs, f, false, snap, 1, 1, nil)
    placeCaret(run, f, f > 0.0001 and f < 0.9999)
    if p < 1 then
        run.doneAt = nil
        return
    end
    -- Progress is 1 and the caller has not given a verdict. OnUpdate stays alive for
    -- the grace window; if nothing arrives, give the verdict here so a dropped event
    -- cannot leave the panel stuck. Succeed/Stop leave the cast phase, which ends
    -- this window (the hold/fade/finish own OnUpdate from then on).
    local doneAt = run.doneAt
    if not doneAt then
        run.doneAt = nowSec
    elseif nowSec - doneAt >= VERDICT_GRACE then
        run.doneAt = nil
        if run.channel then
            Run.Stop(run)
            local cb = run.onFinished
            if cb then cb(run) end
        else
            Run.Succeed(run)
        end
    end
end

local function tickFade(run, nowMs)
    local el = nowMs - run.t0
    if el >= FADE_MS then return finish(run) end
    local lit = 1 - el / FADE_MS
    intrParams(nil)
    paintAll(run, nowMs, 1, true, true, lit, lit, nil)
    setHoldGlow(run, HOLD_GLOW_ALPHA * lit)
end

-- Channel finish: the bar is empty and the chosen style plays over it for run.chanFd ms. The
-- frame flare is a vertex color ease, so it rides the OnUpdate like the lock-in's. The style is
-- run.chanMode, the snapshot startChannelFinish took, so SetChannelFinish mid-play cannot switch it.
local function tickChanHold(run, nowMs)
    local ft = nowMs - run.t0
    local fd = run.chanFd
    if ft >= fd then
        clearLit(run)
        return finish(run)
    end
    local mode = run.chanMode
    if mode ~= "drain" then paintGhosts(run, mode, ft, fd) end
    if run.chanFlare then
        if ft < FLARE_MS then setFlare(run, lockInFlare(ft)) elseif run.flareOn then setFlare(run, 0) end
    end
end

local function tickHold(run, nowMs)
    if run.channel then return tickChanHold(run, nowMs) end
    local el = nowMs - run.t0
    if el >= run.holdMs then
        if run.reducedMotion then return finish(run) end
        run.phase = "fade"
        run.t0 = run.t0 + run.holdMs
        return tickFade(run, nowMs)
    end
    intrParams(nil)
    paintAll(run, nowMs, 1, true, true, 1, 1, nil)
    placeCaret(run, 1, false)
    -- The flare is a vertex color ease, so it rides the OnUpdate; it ends with
    -- the lock-in window (200ms when reduced, otherwise LOCK_MS).
    local ld = min(run.reducedMotion and 200 or LOCK_MS, run.holdMs)
    if el < ld then setFlare(run, lockInFlare(el)) elseif run.flareOn then setFlare(run, 0) end
end

local function tickIntr(run, nowMs)
    local uT = (nowMs - run.t0) / run.intrMs
    if uT >= 1 then return finish(run) end
    if run.reducedMotion then
        PH.phase, PH.u, PH.uT = "reduced", uT, uT
    else
        phaseOf(uT)
    end
    run.intrPhase = PH.phase
    local ip = intrParams(PH)
    local f = run.channel and 1 - run.p0 or run.p0
    paintAll(run, nowMs, f, false, true, ip.level, 1, PH)
    placeCaret(run, f, false)
    setAlphaTarget(run, PH.phase == "fade" and (1 - 0.7 * PH.u) or 1)
end

local function tick(run, nowSec)
    local ph = run.phase
    if ph == "idle" then return end
    local nowMs = nowSec * 1000
    if ph == "cast" then tickCast(run, nowSec, nowMs)
    elseif ph == "hold" then tickHold(run, nowMs)
    elseif ph == "fade" then tickFade(run, nowMs)
    elseif ph == "intr" then tickIntr(run, nowMs) end
end

-------------------------------------------------------------------------------
-- Construction
-------------------------------------------------------------------------------

local function newGroup(region)
    local g = region:CreateAnimationGroup()
    if g.SetToFinalAlpha then g:SetToFinalAlpha(true) end
    return g
end

local function addAlpha(g, order, from, to, dur, smoothing)
    local a = g:CreateAnimation("Alpha")
    a:SetOrder(order)
    a:SetDuration(dur)
    if a.SetFromAlpha then
        a:SetFromAlpha(from)
        a:SetToAlpha(to)
    end
    if smoothing and a.SetSmoothing then a:SetSmoothing(smoothing) end
    return a
end

local function addScale(g, order, from, to, dur, smoothing)
    local s = g:CreateAnimation("Scale")
    s:SetOrder(order)
    s:SetDuration(dur)
    if s.SetScaleFrom then
        s:SetScaleFrom(from, from)
        s:SetScaleTo(to, to)
    else
        s:SetScale(to / from, to / from)
    end
    if s.SetOrigin then s:SetOrigin("CENTER", 0, 0) end
    if smoothing and s.SetSmoothing then s:SetSmoothing(smoothing) end
    return s
end

-- Texture coordinates for the channel mirror: across x for a horizontal run (the chevron then points
-- left), along y for a vertical one (it then points down). Plain 4-argument SetTexCoord both ways.
local function mirrorCoords(run, on)
    if run.vertical then
        if on then return 0, 1, 1, 0 end
        return 0, 1, 0, 1
    end
    if on then return 1, 0, 0, 1 end
    return 0, 1, 0, 1
end

local function setMirror(run, on)
    on = on and run.mirrorChannel and true or false
    if run.mirrored == on then return end
    run.mirrored = on
    local l, r, t, b = mirrorCoords(run, on)
    for i = 1, #run.segs do
        local seg = run.segs[i]
        seg.dim:SetTexCoord(l, r, t, b)
        seg.lit:SetTexCoord(l, r, t, b)
    end
    run.outline:SetTexCoord(l, r, t, b)
    run.glow:SetTexCoord(l, r, t, b)
end

local function ensureSeg(run, i)
    local seg = run.segs[i]
    if seg then return seg end
    seg = {
        dim = run.frame:CreateTexture(nil, "BACKGROUND", nil, 0),
        lit = run.frame:CreateTexture(nil, "ARTWORK", nil, 1),
        blinks = { { t0 = 0, t1 = 0, code = 1 }, { t0 = 0, t1 = 0, code = 4 } },
        a = 0, b = 0, frac = 0, x0 = 0, ign = 200, jit = 0, settle = 0.75, boostMax = 0.3,
        -- Every field a frame writes exists from the start, so no table ever grows
        -- at run time. cr..ca cache the last color applied; litSince false = unlit.
        shown = false, cr = -1, cg = -1, cb = -1, ca = -1, litSince = false,
    }
    seg.dim:SetTexture(run.textures.fill)
    seg.dim:SetVertexColor(run.baseR, run.baseG, run.baseB, run.dimAlpha)
    seg.lit:SetTexture(run.textures.lit)
    seg.lit:SetShown(false)
    seg.shown = false
    run.segs[i] = seg
    if run.mirrored then
        local l, r, t, b = mirrorCoords(run, true)
        seg.dim:SetTexCoord(l, r, t, b)
        seg.lit:SetTexCoord(l, r, t, b)
    end
    return seg
end

-- Repaints every unlit (dim) chevron at alpha `a`. run.dimAlpha is the value Layout's new
-- segments are built with too, so a rescale in the idle row stays consistent.
local function setDimAlpha(run, a)
    if run.dimAlpha == a then return end
    run.dimAlpha = a
    for i = 1, #run.segs do
        run.segs[i].dim:SetVertexColor(run.baseR, run.baseG, run.baseB, a)
    end
end

-- A plain, finite, positive number or nil. IsSecret first: nothing else may touch a secret.
local function plainPositive(v)
    if IsSecret(v) or type(v) ~= "number" then return nil end
    if v ~= v or v <= 0 or v == math.huge then return nil end
    return v
end

-- The texture paths of a run: the Theme defaults, overridden per key by opts.textures (string values
-- only). lit falls back to fill. Fixed key list, never pairs over caller data.
local TEXTURE_KEYS = { "fill", "lit", "outline", "glow", "burst", "strip" }
local function resolveTextures(given)
    local out = {
        fill = Theme.CAST_CHEVRON_FILL_TEXTURE,
        outline = Theme.CAST_CHEVRON_OUTLINE_TEXTURE,
        glow = Theme.CAST_CHEVRON_GLOW_TEXTURE,
        burst = Theme.CAST_CHEVRON_BURST_TEXTURE,
        strip = Theme.CAST_CHEVRON_STRIP_TEXTURE,
    }
    local usable = type(given) == "table" and not IsSecret(given)
    local function pick(key)
        if not usable then return nil end
        local v = given[key]
        if IsSecret(v) or type(v) ~= "string" then return nil end
        return v
    end
    for i = 1, #TEXTURE_KEYS do
        local k = TEXTURE_KEYS[i]
        if k ~= "lit" then out[k] = pick(k) or out[k] end
    end
    out.lit = pick("lit") or out.fill
    return out
end

function ChevronCastBar.Create(parent, opts)
    opts = opts or {}
    local colors = opts.colors or {}
    local run = setmetatable({}, Run)
    run.segs = {}
    run.count = 0
    run.dimAlpha = DIM_ALPHA
    run.W, run.H, run.segW = 0, 0, 0
    run.span, run.originX, run.px, run.pitch = 0, 0, nil, 0
    run.phase = "idle"
    run.p, run.p0 = 0, 0
    run.start, run.dur = 0, 1
    run.t0 = 0
    run.channel = false
    run.reducedMotion = opts.reducedMotion and true or false
    run.gapFraction = opts.gapFraction or Theme.CAST_CHEVRON_GAP_FRACTION
    run.seedSalt = opts.seedSalt or 13
    run.holdMs = opts.holdMs or HOLD_MS
    run.intrMs = opts.interruptMs or INTR_MS
    applyPalette(run, colors)
    run.flareBase = colors.flareBase or Theme.COLOR_BORDER
    run.flareTarget = opts.flareTarget
    run.glowBurst = opts.glowBurst
    run.glowExpand = opts.glowBurstExpand or 5
    run.holdGlow = opts.holdGlow
    run.scaleTarget = opts.scaleTarget
    -- The scale pop is OFF unless the caller asks: "lets drop the snap" (2026-10-02). lockSnap = true
    -- brings back the 1.0 -> 1.04 -> 1.0 pop on scaleTarget for the cast lock-in (a channel finish
    -- never scales).
    run.lockSnap = opts.lockSnap and true or false
    -- IsSecret first: a secret key must never index the table.
    local cf = opts.channelFinish
    run.channelFinish = (not IsSecret(cf) and CHANNEL_FINISHES[cf]) and cf or DEFAULT_CHANNEL_FINISH
    run.vertical = opts.vertical and true or false
    -- A vertical run's fit is not supported (see opts.vertical): the flag stays off so RefreshPixels
    -- relayouts at the size it was given.
    run.fit = opts.fitWidth and not run.vertical and true or false
    run.chevW, run.chevH, run.pitchOpt = plainPositive(opts.chevronWidth), plainPositive(opts.chevronHeight), plainPositive(opts.pitch)
    run.mirrorChannel = opts.mirrorChannel ~= false
    run.textures = resolveTextures(opts.textures)
    run.origin, run.segLen, run.xOff = 0, 0, 0
    run.capW, run.capH, run.capX = 0, 0, 0

    local frame = CreateFrame("Frame", nil, parent)
    run.frame = frame
    run.alphaTarget = opts.alphaTarget or frame
    if opts.points then
        for i = 1, #opts.points do
            local p = opts.points[i]
            frame:SetPoint(p[1], p[2], p[3], p[4], p[5])
        end
    else
        run.ownsSize = true
    end

    -- Caret: clip is a child frame of the run that clips its own child frames to
    -- the run (SetClipsChildren does not clip the clipping frame's own regions).
    local clip = CreateFrame("Frame", nil, frame)
    clip:SetAllPoints(frame)
    if clip.SetClipsChildren then clip:SetClipsChildren(true) end
    clip:SetShown(false)
    run.clip = clip
    -- The caret textures go on a child frame of the clipping frame (see the CARET
    -- CLIP note in the header); clip itself carries no regions.
    local body = CreateFrame("Frame", nil, clip)
    body:SetAllPoints(clip)
    run.body = body
    run.caretShown = false
    run.glow = body:CreateTexture(nil, "ARTWORK", nil, 0)
    run.glow:SetTexture(run.textures.glow)
    run.glow:SetBlendMode("ADD")
    run.glow:SetVertexColor(run.baseR, run.baseG, run.baseB, 0.9)
    run.outline = body:CreateTexture(nil, "ARTWORK", nil, 1)
    run.outline:SetTexture(run.textures.outline)
    run.outline:SetVertexColor(run.coreR, run.coreG, run.coreB, 1)
    run.glow:SetPoint("CENTER", run.outline, "CENTER", 0, 0)

    -- Chevron burst at the end cap (not clipped: lives on the run frame).
    run.burst = frame:CreateTexture(nil, "OVERLAY", nil, 2)
    run.burst:SetTexture(run.textures.burst)
    run.burst:SetBlendMode("ADD")
    run.burst:SetVertexColor(run.coreR, run.coreG, run.coreB, 1)
    run.burst:Hide()
    do
        local burst = run.burst
        local g = newGroup(burst)
        if run.reducedMotion then
            -- Static chevron that flashes and fades: no scale.
            addAlpha(g, 1, 0, 1, 0.03)
            addAlpha(g, 2, 1, 0, 0.17)
        else
            addScale(g, 1, 1, 1.6, 0.3, "OUT")
            addAlpha(g, 1, 1, 0, 0.3)
        end
        g:SetScript("OnFinished", function() burst:Hide() end)
        run.burstGroup = g
        -- Last ember's smaller pop (1.0 -> 1.3 over 240ms, peak alpha 0.9). Reduced motion
        -- plays the plain static flash above instead.
        if not run.reducedMotion then
            local e = newGroup(burst)
            addScale(e, 1, 1, 1.3, 0.24, "OUT")
            addAlpha(e, 1, 0.9, 0, 0.24)
            e:SetScript("OnFinished", function() burst:Hide() end)
            run.emberGroup = e
        end
    end

    -- Outer glow burst: expands about 5 units and fades.
    if run.glowBurst then
        local region = run.glowBurst
        region:Hide()
        local g = newGroup(region)
        if not run.reducedMotion then
            run.glowScale = addScale(g, 1, 1, 1.05, 0.3, "OUT")
        end
        addAlpha(g, 1, 0.9, 0, 0.3, "OUT")
        g:SetScript("OnFinished", function() region:Hide() end)
        run.glowGroup = g
    end

    -- Bar scale pop 1.0 -> 1.04 -> 1.0 over POP_MS (20% up, 80% back down). Only with lockSnap.
    if run.lockSnap and run.scaleTarget and not run.reducedMotion then
        local g = run.scaleTarget:CreateAnimationGroup()
        addScale(g, 1, 1, 1.04, POP_MS * 0.2 / 1000, "OUT")
        addScale(g, 2, 1.04, 1, POP_MS * 0.8 / 1000, "OUT")
        run.popGroup = g
    end

    run.onUpdate = function() tick(run, GetTime()) end

    -- Pixel size can change under the run: UI scale or display size (events), an
    -- ancestor's SetScale (post-hooks), or a change nobody told us about (OnShow,
    -- StartCast, ShowIdle re-check). Each path only compares the pixel size and re-lays
    -- out when it differs. HookScript, so a caller's own OnShow is not displaced.
    watchPixels(run)
    if frame.HookScript then frame:HookScript("OnShow", function() run:RefreshPixels() end) end

    if type(opts.width) == "number" and type(opts.height) == "number" then
        run:Layout(opts.width, opts.height)
    end
    return run
end

-------------------------------------------------------------------------------
-- Layout: nested chevrons. Pitch = arm width + gap, so each tip sits in the
-- next chevron's notch (the prototype's segsChev). Textures are recycled.
-------------------------------------------------------------------------------

-- Whole-pixel chevron geometry for a run `h` high at pixel size `px`: the chevron box width and the
-- pitch (arm + gap), both in physical pixels. Shared by layout and FitWidth.
local function chevronPixels(self, h, px)
    -- Round half up with an epsilon: at 1080p a pet run is exactly 7.5 px high, and without
    -- it float noise rounds the same physical size to 8 at one scale and 7 at another.
    local wPx = max(1, floor(h * Theme.CAST_CHEVRON_ASPECT / px + 0.5 + 1e-6))   -- chevron box width
    local armPx = max(1, floor(wPx - h / (2 * px) + 0.5 + 1e-6))                 -- one arm (D); the tip is w - arm deep
    local gapPx = max(0, floor(self.gapFraction * wPx + 0.5 + 1e-6))
    return wPx, armPx + gapPx                                             -- pitch >= 1
end

-- Pixels spanned by the fewest whole chevrons that cover `requested` (run units).
local function fitSpanPx(requested, px, wPx, pitchPx)
    local reqPx = math.ceil(requested / px - 1e-6)
    local n = max(1, math.ceil((reqPx - wPx) / pitchPx - 1e-9) + 1)
    return (n - 1) * pitchPx + wPx
end

-- Where the first chevron's near edge goes so it lands on a physical pixel: `edge` is the run frame's
-- own GetLeft (or GetBottom) in frame units, `basePx` the whole pixels the chevron is already offset
-- from that edge, `spanPx` the pixels it spans, `totalPx` the pixels of room. Returns the offset in
-- frame units: the nudge goes toward the far side when the slack allows, else back, so the run never
-- passes its far edge (the back case overhangs the near edge by under a pixel). `edge` comes from a
-- pcall'd getter: nil until the frame has a rect, can throw ("can't measure restricted regions"), and
-- is never trusted when secret, so no measurement means no nudge.
local function snapOrigin(gotEdge, edge, px, basePx, spanPx, totalPx)
    if gotEdge and type(edge) == "number" and not IsSecret(edge) and edge == edge then
        local lp = edge / px + basePx
        local fwd = math.ceil(lp - 1e-9) - lp                  -- pixels to the next boundary, [0, 1)
        if basePx + fwd + spanPx <= totalPx + 1e-6 then
            return (basePx + fwd) * px
        end
        return (basePx + floor(lp + 1e-9) - lp) * px           -- (-1, 0] more
    end
    return basePx * px
end

-- Vertical layout: the chevrons stack bottom to top. `width` is the run frame's cross width and
-- `height` its length. Everything is in whole physical pixels exactly as the horizontal layout (see
-- PIXEL GRID), with the chevron box and the pitch given in run units (opts.chevronWidth /
-- chevronHeight / pitch, defaulted from the cross width) and the pitch free to be smaller than the
-- chevron's depth (the arms nest). Anchors are BOTTOMLEFT of the run frame.
local function layoutVertical(self, width, height)
    local px = pixelSize(self.frame)
    local cw = self.chevW or width
    local ch = self.chevH or (cw * VERT_H_FRACTION)
    local pitch = self.pitchOpt or (ch * VERT_PITCH_FRACTION)
    local wPx = max(1, floor(cw / px + 0.5 + 1e-6))
    local hPx = max(1, floor(ch / px + 0.5 + 1e-6))
    local pitchPx = max(1, floor(pitch / px + 0.5 + 1e-6))
    local crossPx = floor(width / px + 1e-6)
    local lenPx = floor(height / px + 1e-6)
    local n = max(1, floor((lenPx - hPx) / pitchPx + 1e-6) + 1)
    local spanPx = (n - 1) * pitchPx + hPx
    local w, hSeg, span = wPx * px, hPx * px, spanPx * px
    local gotB, bottom = pcall(self.frame.GetBottom, self.frame)
    local y = snapOrigin(gotB, bottom, px, 0, spanPx, lenPx)
    local gotL, left = pcall(self.frame.GetLeft, self.frame)
    local x = snapOrigin(gotL, left, px, floor((crossPx - wPx) / 2), wPx, crossPx)
    self.W, self.H, self.segW, self.segLen, self.count = width, height, w, hSeg, n
    self.px, self.span, self.origin, self.xOff = px, span, y, x
    self.pitch = pitchPx * px
    if self.ownsSize then self.frame:SetSize(width, height) end
    for i = 1, n do
        local seg = ensureSeg(self, i)
        local k = (i - 1) * pitchPx                  -- whole pixels up from the first chevron
        local y0 = y + k * px
        seg.x0 = y0                                  -- along the run
        seg.a = k / spanPx
        seg.b = (k + hPx) / spanPx
        seg.frac = (k + hPx / 2) / spanPx
        makeFlicker(seg, flickerSeed(self.seedSalt, i))
        seg.dim:SetSize(w, hSeg)
        seg.dim:SetPoint("BOTTOMLEFT", self.frame, "BOTTOMLEFT", x, y0)
        seg.dim:SetShown(true)
        seg.lit:SetSize(w, hSeg)
        seg.lit:SetPoint("BOTTOMLEFT", self.frame, "BOTTOMLEFT", x, y0)
        seg.lit:SetShown(false)
        seg.shown, seg.cr, seg.cg, seg.cb, seg.ca, seg.litSince = false, -1, -1, -1, -1, false
    end
    for i = n + 1, #self.segs do
        local seg = self.segs[i]
        seg.dim:SetShown(false)
        seg.lit:SetShown(false)
        seg.shown, seg.litSince = false, false
    end
    -- The caret is the bigger, thicker chevron: wider by CARET_PAD_UNITS a side and CARET_DEPTH_UNITS
    -- deep, in units of one image px (the chevron's depth over VERT_DEPTH_UNITS).
    local u = hSeg / VERT_DEPTH_UNITS
    local capW, capH = w + 2 * CARET_PAD_UNITS * u, CARET_DEPTH_UNITS * u
    self.capW, self.capH = capW, capH
    -- The clip frame is widened across by the caret's width so neither the caret nor its halo is
    -- shaved at the sides; along the run it still ends where the run does.
    local m = capW
    self.clip:ClearAllPoints()
    self.clip:SetPoint("TOPLEFT", self.frame, "TOPLEFT", -m, 0)
    self.clip:SetPoint("BOTTOMRIGHT", self.frame, "BOTTOMRIGHT", m, 0)
    self.capX = x + (w - capW) / 2 + m              -- relative to the body (= the clip frame)
    self.outline:SetSize(capW, capH)
    self.glow:SetSize(capW * GLOW_SCALE, capH * GLOW_SCALE)
    self.caretX = nil
    self.burst:SetSize(w * GLOW_SCALE, hSeg * GLOW_SCALE)
    placeBurst(self, self.burstLeft or false)
    if self.phase ~= "idle" then
        self.snapNext = true
        tick(self, GetTime())
    end
    local cb = self.onLayout
    if cb then cb(self) end
    return true
end

local function layout(self, width, height)
    if IsSecret(width) or IsSecret(height) then return false end
    if type(width) ~= "number" or type(height) ~= "number" or width <= 0 or height <= 0 then return false end
    if self.vertical then return layoutVertical(self, width, height) end
    local W, h = width, height
    -- Whole physical pixels from here on (see PIXEL GRID in the header).
    local px = pixelSize(self.frame)
    local wPx, pitchPx = chevronPixels(self, h, px)
    if self.fit then
        -- Fit mode: `width` is the REQUEST; the run is widened to a whole number of chevrons with no
        -- slack, and the request is kept so a rescale refits from it, not from the last fitted width.
        self.requestedW = width
        W = fitSpanPx(width, px, wPx, pitchPx) * px
    end
    -- 1e-6 guards the floors against 11.999999999 from float arithmetic.
    local n = max(1, floor((floor(W / px + 1e-6) - wPx) / pitchPx + 1e-6) + 1)
    local spanPx = (n - 1) * pitchPx + wPx
    local w, span = wPx * px, spanPx * px
    -- Origin: the first chevron's left edge on a physical pixel. GetLeft is in the
    -- frame's own units; it is nil until the frame has a rect and can throw ("can't
    -- measure restricted regions"), so it is pcall'd and no measurement means no nudge.
    -- Nudge right when the slack allows, else left, so the run never passes its own
    -- right edge (the left case overhangs the left edge by under one pixel).
    local gotLeft, left = pcall(self.frame.GetLeft, self.frame)
    local x = snapOrigin(gotLeft, left, px, 0, spanPx, W / px)
    self.W, self.H, self.segW, self.segLen, self.count = W, h, w, w, n
    self.px, self.span, self.originX, self.origin = px, span, x, x
    self.pitch = pitchPx * px
    if self.ownsSize then self.frame:SetSize(W, h) end
    for i = 1, n do
        local seg = ensureSeg(self, i)
        local k = (i - 1) * pitchPx                  -- whole pixels from the first chevron
        local x0 = x + k * px
        seg.x0 = x0
        -- Fractions of the occupied span (not of W): the last chevron ends at exactly 1.
        seg.a = k / spanPx
        seg.b = (k + wPx) / spanPx
        seg.frac = (k + wPx / 2) / spanPx
        makeFlicker(seg, flickerSeed(self.seedSalt, i))
        seg.dim:SetSize(w, h)
        seg.dim:SetPoint("TOPLEFT", self.frame, "TOPLEFT", x0, 0)
        seg.dim:SetShown(true)
        seg.lit:SetSize(w, h)
        seg.lit:SetPoint("TOPLEFT", self.frame, "TOPLEFT", x0, 0)
        seg.lit:SetShown(false)
        seg.shown, seg.cr, seg.cg, seg.cb, seg.ca, seg.litSince = false, -1, -1, -1, -1, false
    end
    for i = n + 1, #self.segs do
        local seg = self.segs[i]
        seg.dim:SetShown(false)
        seg.lit:SetShown(false)
        seg.shown, seg.litSince = false, false
    end
    self.outline:SetSize(w, h)
    self.glow:SetSize(w * GLOW_SCALE, h * GLOW_SCALE)
    self.caretX = nil
    self.burst:SetSize(w * GLOW_SCALE, h * GLOW_SCALE)
    -- On the last chevron (the end of the span), not the run's right edge: the slack
    -- sits beyond it. A channel finish parks it on the first chevron instead (burstLeft).
    placeBurst(self, self.burstLeft or false)
    if self.phase ~= "idle" then
        self.snapNext = true
        tick(self, GetTime())
    end
    local cb = self.onLayout
    if cb then cb(self) end
    return true
end

-- layout() under the re-entrancy flag RefreshPixels checks. A throw (an onLayout that
-- errors) releases the flag, resets px so the next trigger relayouts, and is rethrown
-- with its message and, where the client has debugstack, the throw site kept. A nested
-- Layout call (from onLayout or onFinished) is dropped and returns false.
local function addStack(err)
    if type(err) == "string" and type(debugstack) == "function" then
        return err .. "\n" .. tostring(debugstack(2))
    end
    return err
end

function Run:Layout(width, height)
    if self.inLayout then return false end
    self.inLayout = true
    self.pendingRefresh = false
    local okl, res = xpcall(function() return layout(self, width, height) end, addStack)
    self.inLayout = false
    if not okl then
        self.px, self.pendingRefresh = 0, false
        error(res, 0)
    end
    if self.pendingRefresh then
        -- A rescale arrived while laying out: replay it once (settling stops a cascade).
        self.pendingRefresh = false
        self.settling = true
        local okr, err = pcall(self.RefreshPixels, self)
        self.settling = false
        if not okr then error(err, 0) end
    end
    return res
end

-- Re-lays out at the last size when the physical pixel size changed since the
-- segments were built. The one place a rescale is detected; every trigger (events, an
-- ancestor's SetScale, OnShow, StartCast, ShowIdle) funnels through it, and a trigger
-- whose pixel size is unchanged costs one GetEffectiveScale and a compare.
function Run:RefreshPixels()
    local old = self.px
    if not old or self.W <= 0 then return false end      -- never laid out: nothing to redo
    -- A rescale fired from inside Layout (an onLayout, or onFinished via Layout's tick) must
    -- not re-enter it. It is remembered and replayed once Layout is done, unless that is
    -- already the replay (then a callback that rescales on every layout cannot loop).
    if self.inLayout then
        if not self.settling then self.pendingRefresh = true end
        return false
    end
    local px = pixelSize(self.frame)
    if math.abs(px - old) <= old * 1e-9 then return false end
    return self:Layout(self.fit and self.requestedW or self.W, self.H)
end

-- The smallest width at least `requested` (run units) that holds a whole number of chevrons at
-- the CURRENT pixel pitch with zero slack, so nothing is left over before whatever sits after the
-- run (the timer). Callers size their bar with it; opts.fitWidth makes the run do it itself on
-- every Layout and rescale (read run.W in onLayout to size the chrome). `height` defaults to the
-- last laid-out height. Returns nil for an unusable argument. A width that already fits is
-- returned unchanged (the mockup always grows by one more chevron; see the header).
function Run:FitWidth(requested, height)
    if self.vertical then return nil end      -- a horizontal feature (see opts.vertical)
    if height ~= nil and IsSecret(height) then return nil end    -- before any boolean test of it
    height = height or self.H
    if IsSecret(requested) or IsSecret(height) then return nil end
    if type(requested) ~= "number" or type(height) ~= "number" then return nil end
    if requested ~= requested or requested <= 0 or requested == math.huge or height <= 0 or height == math.huge then return nil end
    local px = pixelSize(self.frame)
    local wPx, pitchPx = chevronPixels(self, height, px)
    return fitSpanPx(requested, px, wPx, pitchPx) * px
end

-- The largest width at most `maxWidth` (run units) that holds a whole number of chevrons at the
-- CURRENT pixel pitch: FitWidth's twin that rounds DOWN, for a track of fixed length (the pet bar
-- between the spell icon and the timer column) that FitWidth would overshoot by up to a pitch. nil when
-- not even one chevron fits, for a vertical run and for an unusable argument, as FitWidth. A maxWidth
-- that is already an exact fit comes back unchanged. `height` defaults to the last laid-out one.
function Run:FitWithin(maxWidth, height)
    if self.vertical then return nil end      -- a horizontal feature (see opts.vertical)
    if height ~= nil and IsSecret(height) then return nil end    -- before any boolean test of it
    height = height or self.H
    if IsSecret(maxWidth) or IsSecret(height) then return nil end
    if type(maxWidth) ~= "number" or type(height) ~= "number" then return nil end
    if maxWidth ~= maxWidth or maxWidth <= 0 or maxWidth == math.huge or height <= 0 or height == math.huge then return nil end
    local px = pixelSize(self.frame)
    local wPx, pitchPx = chevronPixels(self, height, px)
    local maxPx = floor(maxWidth / px + 1e-6)
    if maxPx < wPx then return nil end        -- not even one chevron
    return ((floor((maxPx - wPx) / pitchPx + 1e-9)) * pitchPx + wPx) * px
end

-------------------------------------------------------------------------------
-- Strip: the engine-timed StatusBar for a secret-timed cast
-------------------------------------------------------------------------------

-- What the client's StatusBar can do, found once by a probe bar (built on the first ask, hidden, never
-- destroyed) rather than at load. Method presence only; see SupportsVerticalStrip.
local stripCaps
local function stripSupport()
    if stripCaps then return stripCaps end
    local caps = { orientation = false, vertTile = false, horizTile = false, timer = false, ok = false }
    local built, bar = pcall(CreateFrame, "StatusBar", nil, UIParent)
    if built and bar then
        caps.orientation = type(bar.SetOrientation) == "function"
        caps.timer = type(bar.SetTimerDuration) == "function"
        if type(bar.SetStatusBarTexture) == "function" and type(bar.GetStatusBarTexture) == "function" then
            pcall(bar.SetStatusBarTexture, bar, ChevronCastBar.TEXTURES_UP.fill)
            local got, fill = pcall(bar.GetStatusBarTexture, bar)
            if got and fill then
                caps.vertTile = type(fill.SetVertTile) == "function"
                caps.horizTile = type(fill.SetHorizTile) == "function"
            end
        end
        pcall(bar.Hide, bar)
    end
    caps.ok = caps.orientation and caps.vertTile and caps.timer
    -- A probe that could not even be built is not an answer: ask again next time.
    if built and bar then stripCaps = caps end
    return caps
end

function ChevronCastBar.SupportsVerticalStrip()
    local caps = stripSupport()
    return caps.ok, caps
end

Run.SupportsVerticalStrip = ChevronCastBar.SupportsVerticalStrip

-- The engine-timed fallback bar: hidden, filled with the run's strip texture and tiled along the
-- growth axis. The caller anchors and colours it and drives it with SetTimerDuration. A vertical bar
-- needs SetOrientation and a fill texture with SetVertTile; without them nil and the reason come
-- back (nothing is built), so the consumer can fall back.
function Run:CreateStrip(parent)
    local caps = stripSupport()
    if self.vertical then
        if not caps.orientation then return nil, "StatusBar:SetOrientation is missing" end
        if not caps.vertTile then return nil, "Texture:SetVertTile is missing" end
    end
    local bar = CreateFrame("StatusBar", nil, parent or self.frame)
    if self.textures.strip then bar:SetStatusBarTexture(self.textures.strip) end
    local fill = bar:GetStatusBarTexture()
    if self.vertical then
        bar:SetOrientation("VERTICAL")
        if fill then fill:SetVertTile(true) end
    elseif fill and caps.horizTile then
        fill:SetHorizTile(true)
    end
    bar:SetMinMaxValues(0, 1)
    bar:SetValue(0)
    bar:Hide()
    bar.fsTexelsPerChevron = STRIP_TEXELS_PER_CHEVRON
    return bar
end

-- Scales a CreateStrip bar so one chevron of its tile spans one engine pitch (the engine's
-- whole-pixel run.pitch over the 16 texels per chevron). Returns the scale, nil for no strip or a run
-- not laid out yet.
function Run:ApplyStripScale(strip)
    if not strip or not strip.SetScale then return nil end
    local pitch = self.pitch
    if type(pitch) ~= "number" or pitch <= 0 then return nil end
    local scale = pitch / (strip.fsTexelsPerChevron or STRIP_TEXELS_PER_CHEVRON)
    strip:SetScale(scale)
    return scale
end

-------------------------------------------------------------------------------
-- Public methods
-------------------------------------------------------------------------------

-- Shared argument gate of StartCast and UpdateTimes. IsSecret first: type() is safe on
-- a secret, comparison and arithmetic are not.
local function timesAreUsable(startTime, endTime)
    if IsSecret(startTime) or IsSecret(endTime) then return false end
    if type(startTime) ~= "number" or type(endTime) ~= "number" then return false end
    -- NaN never equals itself; an infinite time would leave OnUpdate running for good.
    if startTime ~= startTime or endTime ~= endTime then return false end
    if startTime == math.huge or startTime == -math.huge or endTime == math.huge or endTime == -math.huge then return false end
    if endTime <= startTime then return false end
    -- A cast that ended longer ago than the verdict grace window is stale (a late or
    -- replayed event): starting it would hit the safety net at once and replay a
    -- lock-in for a cast the player finished long ago. Refuse without touching state.
    -- Inside the window it is usable: progress clamps to 1 (snap to complete) and
    -- the normal verdict or safety-net path runs.
    if GetTime() > endTime + VERDICT_GRACE then return false end
    return true
end

function Run:StartCast(startTime, endTime, isChannel, castID)
    if IsSecret(isChannel) then return false end
    if not timesAreUsable(startTime, endTime) then return false end
    resetEffects(self)
    setDimAlpha(self, DIM_ALPHA)    -- leaves an idle row's own dim presence (ShowIdle)
    self.castID = castID
    self.override = nil
    self.channel = isChannel and true or false
    self.start, self.dur = startTime, endTime - startTime
    self.doneAt = nil
    self.phase = "cast"
    self.intrPhase = nil
    -- A rescale nobody told us about. After the state above is settled: a re-layout in a
    -- stale hold/fade/outage phase would tick that phase and could fire onFinished here.
    self:RefreshPixels()
    setMirror(self, self.channel)
    local nowSec = GetTime()
    local nowMs = nowSec * 1000
    -- Joining a cast already underway: settle the segments instead of flickering
    -- the whole run at once. A fresh channel cascades right to left instead.
    local p = progressOf(self, nowSec)
    self.snapNext = p > 0.02
    for i = 1, self.count do
        local seg = self.segs[i]
        if self.channel and p <= 0.02 then
            seg.litSince = nowMs + (1 - seg.frac) * CHANNEL_STAGGER_MS
        else
            seg.litSince = false
        end
        seg.lit:SetShown(false)
        seg.shown = false
    end
    self.caretX = nil
    setCaretShown(self, false)
    self.frame:Show()
    setOnUpdate(self)
    tick(self, nowSec)
    return true
end

-- Re-times the cast that is running (UNIT_SPELLCAST_DELAYED, UNIT_SPELLCAST_CHANNEL_UPDATE)
-- WITHOUT restarting it. StartCast would reset every segment's ignite clock and the castID,
-- so a segment that already settled would flicker again; this only swaps the clock, so
-- progress follows the new length and the lit segments carry on. A pushback can drop
-- progress below a segment's end; that segment then goes dark and, as it must, ignites
-- again when the cast reaches it. Returns true when applied; false (nothing changed) when
-- no cast is running (idle, or a verdict is already playing) or the times are unusable
-- (same gate as StartCast, secrets included).
function Run:UpdateTimes(startTime, endTime)
    if self.phase ~= "cast" then return false end
    if not timesAreUsable(startTime, endTime) then return false end
    self.start, self.dur = startTime, endTime - startTime
    self.doneAt = nil
    tick(self, GetTime())
    return true
end

-- Remembers the current cast's castID (UnitCastingInfo's 7th return, or a channel's
-- castGUID) so MatchesCast can answer for later events. StartCast's optional 4th
-- argument does the same. The value is only stored, never compared here, so a secret
-- id is safe to pass. The next StartCast clears it.
function Run:SetCastID(id)
    self.castID = id
end

-- Does an event's castID belong to the current cast? true | false | nil.
-- nil means "cannot tell": either side is nil or secret. A secret is never compared
-- (comparison throws for tainted code), so the caller must pick the fallback in the
-- CALLER CONTRACT below.
function Run:MatchesCast(id)
    local mine = self.castID
    if id == nil or mine == nil then return nil end
    if IsSecret(id) or IsSecret(mine) then return nil end
    return id == mine
end

function Run:SetProgressOverride(fraction)
    if fraction ~= nil then
        if IsSecret(fraction) or type(fraction) ~= "number" then return end
        fraction = clamp(fraction)
    end
    self.override = fraction
    if self.phase == "cast" then tick(self, GetTime()) end
end

-- Length in ms of the channel finish that would play now, 0 for none: the style is "none", or the hold
-- (200ms at most in reduced motion) is under MIN_FINISH_MS.
local function channelFinishLength(run)
    if run.channelFinish == "none" then return 0 end
    local fd = run.reducedMotion and min(REDUCED_FINISH_MS, run.holdMs) or run.holdMs
    if fd < MIN_FINISH_MS then return 0 end
    return fd
end

-- Starts the chosen channel finish over the empty bar (phase "hold"; onFinished fires after fd ms).
-- Echo and drain flash the frame and burst the outer glow, ember flashes the frame only, sweep neither;
-- drain and ember add a chevron burst at the LEFT end (the last chevron to go out), pointing left.
local function startChannelFinish(run, fd)
    local mode = run.channelFinish
    run.chanMode = mode          -- snapshot: SetChannelFinish while this plays applies to the NEXT finish
    clearLit(run)
    run.phase = "hold"
    run.t0 = GetTime() * 1000
    run.chanFd = fd
    run.chanFlare = mode ~= "sweep"
    setCaretShown(run, false)
    if mode == "echo" or mode == "drain" then playGlow(run) end
    if mode == "drain" or mode == "ember" then
        placeBurst(run, true)
        playBurst(run, mode == "ember" and run.emberGroup or run.burstGroup)
    end
    setOnUpdate(run)
    tick(run, GetTime())
end

-- The recipe call for UNIT_SPELLCAST_CHANNEL_STOP with a nil interruptedBy: the stop of a channel
-- that was not kicked. Natural end or player clip? The engine decides from its OWN schedule (the
-- plain GetTime start and end it was handed, as retimed by UpdateTimes): a stop within
-- NATURAL_SLACK_S of the scheduled end is a natural end and plays the channel finish; an earlier
-- stop (clipping Mind Flay with another cast) gets the plain Stop(). No event payload is read, so no
-- secret is ever involved. Returns true when the finish plays (onFinished fires when it ends),
-- false when it did a plain Stop() (frame hidden, no onFinished: the caller goes idle), nil when
-- nothing applied (not a running channel, or a verdict is already playing).
function Run:EndChannel()
    if self.phase ~= "cast" or not self.channel then return nil end
    local remaining = (1 - progressOf(self, GetTime())) * self.dur
    if remaining <= NATURAL_SLACK_S then
        local fd = channelFinishLength(self)
        if fd > 0 then
            startChannelFinish(self, fd)
            return true
        end
    end
    self:Stop()
    return false
end

-- Picks the channel finish style at run time ("drain", "echo", "sweep", "ember" or "none").
-- Returns false and keeps the current style for anything else. A finish that is already playing
-- keeps the style it started with; the new one applies to the next finish.
function Run:SetChannelFinish(mode)
    if IsSecret(mode) or not CHANNEL_FINISHES[mode] then return false end
    self.channelFinish = mode
    return true
end

function Run:Succeed()
    if self.phase ~= "cast" then return false end
    if self.channel then
        -- A channel plays its finish style over the empty bar; with none (or a hold too short) it
        -- ends at once.
        local fd = channelFinishLength(self)
        if fd > 0 then startChannelFinish(self, fd) else finish(self) end
        return true
    end
    self.phase = "hold"
    self.t0 = GetTime() * 1000
    setCaretShown(self, false)
    setHoldGlow(self, HOLD_GLOW_ALPHA)
    playLockIn(self)
    setOnUpdate(self)
    tick(self, GetTime())
    return true
end

function Run:Interrupt()
    if self.phase ~= "cast" then return false end
    self.p0 = progressOf(self, GetTime())
    self.phase = "intr"
    self.t0 = GetTime() * 1000
    self.intrPhase = "brown"
    setOnUpdate(self)
    tick(self, GetTime())
    return true
end

-- Everything Stop and ShowIdle share: no phase, no OnUpdate, no effects, nothing lit, no
-- caret. The run frame's visibility is left to the caller.
local function toIdle(run)
    run.phase = "idle"
    run.override = nil
    run.doneAt = nil
    run.chanMode = nil
    clearOnUpdate(run)
    resetEffects(run)
    for i = 1, #run.segs do
        local seg = run.segs[i]
        seg.lit:SetShown(false)
        seg.shown, seg.litSince = false, false
    end
    setCaretShown(run, false)
end

function Run:Stop()
    toIdle(self)
    self.frame:Hide()
end

-- The resting look between casts: the row of UNLIT chevrons, visible, with no OnUpdate. A
-- caller that wants a bar that is never blank (the pet cast bar) parks the run here instead
-- of Stop(), which hides the frame. `dimAlpha` (optional, default the cast look's 0.2)
-- sets the unlit chevrons' alpha for the idle row only; the next StartCast puts it back to
-- 0.2. Same effect reset as Stop (so it is also the way out of a hold, fade or outage),
-- safe to call from onFinished, and the alpha target is restored to 1.
function Run:ShowIdle(dimAlpha)
    toIdle(self)
    self:RefreshPixels()
    if IsSecret(dimAlpha) or type(dimAlpha) ~= "number" or dimAlpha ~= dimAlpha then dimAlpha = DIM_ALPHA end
    setDimAlpha(self, dimAlpha)
    self.frame:Show()
end

function Run:IsBusy()
    return self.phase ~= "idle"
end

function Run:GetPhase()
    return self.phase
end

-- True once a verdict has been given (hold, fade or outage is playing).
function Run:IsFinishing()
    local ph = self.phase
    return ph == "hold" or ph == "fade" or ph == "intr"
end

-- Elapsed fraction of the current cast, read off the clock now (not the last frame).
function Run:GetProgress()
    if self.phase == "idle" then return 0 end
    return progressOf(self, GetTime())
end

-- A cast that has run its full length and is still waiting for a verdict.
function Run:IsComplete()
    return self.phase == "cast" and progressOf(self, GetTime()) >= 1
end
