-- Forever STUwave: Cast Bars (cast bar v2 step 3b)
--
-- PLAYER and TARGET cast bars on the shared chevron engine (ChevronCastBar.lua), laid out
-- as the user's locked "Stack A" (mockups/castbar-v2-compare.html, the "Full combat HUD" card
-- and the player card, variant H): two chamfered bars of the SAME width, the target bar on
-- top and the player bar below, 18 units apart on a FIXED seat (see STACK PLACEMENT; the
-- optional ForeverDebugBridge dev strip used to sit in that gap and now lives in the data bar, decision
-- doc design record, so nothing here reads it). PlayerCastingBarFrame is the
-- correct player cast bar on this client (CastingBarFrame is nil); TargetFrameSpellBar is
-- the target one. Both Blizzard bars are dimmed, not hidden (DimBlizzardFrame); both of ours
-- are plain non-secure frames, so no combat defer is needed.
--
-- A BAR (BuildBar): one frame `S.frame`, shown only while a cast, a channel or a verdict
-- animation is on screen (22 high), unless the HUD turns the idle row on (IDLE ROW API below):
--   chamfered fill + outline (the outline is the engine's flareTarget), two DEDICATED pink
--   glow textures (the engine's glowBurst and holdGlow), the spell icon (18 square, 1px --line
--   stroke) with the interruptible shield, the engine's fill run, the timer column ("0.9 / 1.5":
--   elapsed over the real cast length, remaining over the length for a channel; the " / total"
--   in the mockup's muted colour on the plain path), and a spell-name TAB on the outer edge:
--   target = top edge, right end; player = under the bottom edge, left end. The tab is the
--   mockup's trapezoid, narrow side away from the frame, TAB_SLANT (5) units of lean at each end:
--   a flat fill between two flipped media/tab_slant.tga wedges (ChatTabs.lua and Console.lua
--   build their leaning plates from the same wedge), the free edge and both slanted sides
--   stroked violet.
--   Run (RUN_X 27 in, 18 high), timer column and the chamfer insets add up to chromeW (94 with
--   the fallback column of 56). The timer column is MEASURED once, at the first build, from the
--   font: TIMER_SAMPLE ("0.0 / 0.0") through GetStringWidth in a pcall, plus 2 of padding, and
--   chromeW follows; no usable measurement keeps the mockup's 56. The run is built with
--   fitWidth: it is asked for REQUEST_W - chromeW (166 with the fallback) and widens itself to a
--   whole number of chevrons (174 at pixel scale 1: 14 chevrons), so the frame is 174 + 94 = 268
--   wide at scale 1, and re-fits on every rescale through run.onLayout (which sets the frame
--   width and re-places the stack).
--
-- LOCK-IN: flash + glow burst + chevron burst, NO scale pop (lockSnap is left unset). A
-- channel that runs out plays the engine's channelFinish ("drain") through EndChannel(); a
-- clip (Mind Flay cut by another cast) gets the plain Stop.
--
-- CHANNEL TICK COUNTER (player tab only): "n/T" while channelling, from CHANNEL_TICKS by spell
-- id (every rank of Mind Flay, Drain Soul and Drain Life) and then by English name; a spell with
-- clipAfter shows "CUT" in pink once n >= clipAfter. n comes from the engine's own plain GetTime
-- schedule (the start/end it was handed), never from an event payload or a secret.
--
-- STACK PLACEMENT (PlaceStack). Everything is in UIParent units (the bars are UIParent
-- children at scale 1). Each bar sits on its own FS.Layout entry, `tcast` and `pcast` (CENTER offsets
-- from UIParent's CENTER in UI units: unscaled, noSize, so /fsedit can move them like any component
-- and the fitted bar width stays). The defaults are the old fixed seat: the gap centre at (0, -317)
-- with GAP (18, the gap of the approved off-state mockup mockups/off-state-and-bridge-2026-10-02.html)
-- between the two frames, i.e. tcast y -297 and pcast y -337:
--     target frame CENTER = (SEAT_X, SEAT_Y + GAP / 2 + FRAME_H / 2)
--     player frame CENTER = (SEAT_X, SEAT_Y - GAP / 2 - FRAME_H / 2)
-- Those two formulas are the fallback when FS.Layout (or an entry) is missing. The bars are registered
-- with FS.Layout.Apply at build, so a layout re-seat (/fsedit drop, reset, rescale) puts them back on
-- the entry; the snapped placement below then re-runs from Layout.OnRescale.
-- Nothing here reads `_G.ForeverDebugBridgeFrame`: the dev strip moved into the data bar, and a
-- stack that centred on it would follow it to the bottom of the screen. Each frame's offsets are
-- snapped so its left and bottom edges sit on whole physical pixels (SnapOffset, one pixel = the
-- engine's run.px): the engine nudges its run's origin onto a pixel from the frame's GetLeft,
-- which would otherwise depend on where the stack happened to land. When a placement moved a bar,
-- PlaceAndRefit re-runs each run's Layout once so that nudge is measured against the new seat
-- (never from the onLayout path, where a Layout call is dropped as nested; onLayout calls
-- PlaceStack only). Re-placed on UI_SCALE_CHANGED, DISPLAY_SIZE_CHANGED, PLAYER_LOGIN,
-- PLAYER_ENTERING_WORLD and from either run's onLayout (which also fires when the engine's own
-- scale watcher re-lays a run out after ours, so a stale pixel size is corrected there; no
-- second next-frame pass is needed now that no other addon's frame has to settle first).
--
-- EVENTS. Per bar, the eight UNIT_SPELLCAST_* events through RegisterUnitEvent for its unit,
-- plus PLAYER_ENTERING_WORLD (a loading screen can swallow a verdict) and, for the target,
-- PLAYER_TARGET_CHANGED (drops whatever was showing and re-reads the new target). The handler
-- pcalls HandleEvent directly (no closure per event) and prints a failure under the event's name.
-- UNIT_SPELLCAST_SUCCEEDED is deliberately NOT registered. The verdict mapping is the caller
-- recipe in ChevronCastBar.lua's header, the same as PetCastBar.lua: castID-matched STOP ->
-- Succeed(); INTERRUPTED -> Interrupt() unless MatchesCast is false; FAILED only when it
-- matches (or, for a secret castID, when the cast is plainly gone); CHANNEL_STOP with an
-- interruptedBy -> Interrupt(), a secret interruptedBy -> the quiet stop, nil -> EndChannel();
-- DELAYED / CHANNEL_UPDATE -> UpdateTimes() (never StartCast); everything is ignored while
-- run:IsFinishing(), and cast verdicts are ignored during a channel.
--
-- SECRETS. UnitCastingInfo / UnitChannelInfo are secret for other units' casts (the target's):
-- name, start, end, castID and notInterruptible. Times only become seconds after an
-- IsSecret/type check, the castID is only stored and handed to run:MatchesCast (which never
-- compares a secret), the name goes to SetText untouched (no string method may touch a
-- secret, so a secret name is not upper-cased or trimmed), the interruptible flag only reaches
-- SetAlphaFromBoolean. Secret times make the engine refuse; an engine-timed strip StatusBar
-- (SetTimerDuration with the duration object, CAST_CHEVRON_STRIP_TEXTURE, scaled by the
-- engine's pitch like PetCastBar.lua) takes over, and its timer text passes the duration
-- object's numbers straight into SetFormattedText inside a pcall, in ONE colour (they may be
-- secret), dropping the decimal on a plain total of 10s or more. A strip bar has an end-of-cast
-- safety net on the 0.1s readout ticker (StripIsOver): the unit plainly gone, or neither
-- UnitCastingInfo nor UnitChannelInfo reading back a plain nil name, ends it; every value is
-- IsSecret-checked before a nil compare, and a secret is unknown, never gone.
--
-- IDLE ROW API (for the HUD display task; off by default, nothing shows between casts):
--     FS.CastBars.SetIdleHint(unit, text)   "player" / "target": the tab text of the idle row
--     FS.CastBars.SetIdleVisible(bool)      true: a bar that is not casting shows the engine's
--         row of unlit chevrons (run:ShowIdle(IDLE_DIM_ALPHA)) with its hint on the tab (no hint,
--         no tab), and returns to it after every cast; false: hidden between casts again.
--     FS.CastBars.SetRestAlpha(a)           0 to 1, default 1 (unchanged): the alpha of the idle row
--         only, the HUD's out-of-combat dim (mockup .hud-stack.ooc .bar-host { opacity: .55 }); the
--         plain idle row (chevrons at IDLE_DIM_ALPHA, frame at 1) does NOT produce that look.
--
-- VIEW SEAM (FS.CastBars.SetView, for GunsightTape.lua): the state machine above works on duck
-- typed bar tables, so another display can take it over without a copy of it. SetView({ player = S,
-- target = S }) takes two ready made bar tables (frame, run, strip, icon, shield, timer, tab,
-- tabName, tabTicks: the same members a Stack A bar has, any of them may be a proxy table with the
-- same methods), gives them the unit and state fields and the readout ticker, wires their events
-- and reads the live cast once, then RETIRES the Stack A bars (events off, run stopped, frames
-- hidden; nothing is deleted, FS.playerCastBar / FS.targetCastBar stay Stack A). A view bar carries
-- three optional flags the state machine honours: alwaysIdle (rests on the engine's idle row,
-- never hides), idleDim (the unlit chevron alpha of that row) and stripOnly (a cast is always
-- engine timed on the strip, the run is never started: a target tape that must never depend on
-- plain times). A fourth optional field, onVerdict(S, kind), is called (pcall'd) on an interrupt only
-- (every route to Interrupt(): INTERRUPTED, FAILED, a kicked channel) with "interrupt", right after the
-- readout froze and before the engine's outage starts; Stack A bars have none, so Stack A is untouched.
-- The view bar's readout ticker is a table with Show / Hide that installs its
-- OnUpdate only while shown, so nothing runs between casts. SetView is one shot and returns false,
-- touching nothing, for a view that is incomplete or while another view is active. The seam is
-- REVERSIBLE: FS.CastBars.ClearView() stands the view bars down (events off, engine stopped, readout
-- ended; the frames are theirs to hide) and brings Stack A back (events wired again, re-read from the
-- units, so a cast in progress shows on whichever display takes over); SetView can then take the same
-- bars again. Nothing is built twice: the event frames and view tickers are made once and reused, so
-- repeated hand-offs add no frame and no registration. FS.CastBars.IsStackActive() says whether Stack A
-- is the display. With no view set none of this is read: Stack A runs exactly as it always did.
--
-- Exported as FS.playerCastBar / FS.targetCastBar (the bar tables: .frame, .run, ...) and
-- FS.CastBars (the idle row API, SetView).

local _, FS = ...

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local Theme = FS.Theme
local ApplyMono = Theme.ApplyMono
local AddSliceTexture = Theme.AddSliceTexture
local ApplyNineSlice = Theme.ApplyNineSlice
local AddCut2Texture = Theme.AddCut2Texture
local COLOR_BORDER = Theme.COLOR_BORDER
local COLOR_BAR_TRACK = Theme.COLOR_BAR_TRACK
local COLOR_BAR_BORDER = Theme.COLOR_BAR_BORDER
local COLOR_POWER = Theme.COLOR_POWER
local COLOR_HEALTH = Theme.COLOR_HEALTH
local COLOR_PARCHMENT = Theme.COLOR_TEXT_PARCHMENT
local COLOR_CAST_NO_INTERRUPT = Theme.COLOR_CAST_NO_INTERRUPT
local IsSecret = FS.IsSecret

-- Dim a Blizzard default frame the Edit Mode-safe way. Shared plumbing lives
-- in FrameHelpers.lua (FS.FrameHelpers.DimBlizzardFrame).
local DimBlizzardFrame = FS.FrameHelpers.DimBlizzardFrame

-------------------------------------------------------------------------------
-- Layout constants (UIParent units) -- SINGLE-POINT TUNABLE, need Parker's eyeball
-------------------------------------------------------------------------------

local FRAME_H = 22
local CHAMFER = 5                         -- the mockup's c: inset of icon and timer from the frame edge
local RUN_Y = 2
local RUN_H = FRAME_H - 2 * RUN_Y         -- 18: the chevron box is 18 wide, arm 9, gap 3, pitch 12
local ICON = FRAME_H - 2 * RUN_Y          -- 18, square
local COLUMN_GAP = 4
local RUN_X = CHAMFER + ICON + COLUMN_GAP -- 27
local TIMER_SAMPLE = "0.0 / 0.0"          -- the widest readout the column has to hold
local TIMER_PAD = 2                       -- added to the measured sample, as the mockup does
local TIMER_W_FALLBACK = 56               -- the mockup's measured sample (54) plus the padding
local REQUEST_W = 260                     -- the stack size before fitting to whole chevrons
-- The run's seat and the timer column make up the frame's fixed chrome: RUN_X, the gap, the timer
-- column, 2 of padding and the chamfer (94 with the fallback column). The column is measured from
-- the font once, at the first build (MeasureTimerColumn), so these two start at the fallback.
local function ChromeFor(timerW) return RUN_X + COLUMN_GAP + timerW + 2 + CHAMFER end
local chromeW = ChromeFor(TIMER_W_FALLBACK)
local runRequest = REQUEST_W - chromeW   -- 166 -> fitted 174 -> frame 268 at pixel scale 1

local TIMER_FONT_SIZE = 11
local TAB_FONT_SIZE = 12
local TAB_H = 15
local TAB_PAD = 6
local TAB_SLANT = 5                       -- the mockup's sl: how far each end of the tab leans
local TAB_EDGE_INSET = CHAMFER + 1        -- the mockup: the tab starts one unit past the chamfer
local TAB_TICK_GAP = 4
local TAB_SECRET_NAME_W = 140             -- a secret name cannot be measured

local GAP = 18                            -- player frame top to target frame bottom (frames, not tabs): the off-state mockup's
local SEAT_X, SEAT_Y = 0, -317            -- the gap centre, from UIParent's CENTER (interim fixed seat)

local GLOW_BURST_EXPAND = 5
local SEED_SALT = 13                      -- the mockup's player-size bar

local TICK_INTERVAL = 0.1                 -- seconds between readout refreshes
local IDLE_DIM_ALPHA = 0.35               -- the unlit chevrons of the idle row (PetCastBar.lua's value)

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local TAB_SLANT_TEXTURE = MEDIA .. "tab_slant.tga"
-- The mockup's --muted, for the " / total" part of the timer. Not a Theme token: this is its only user.
local MUTED_HEX = "9a8fbd"
local PLAIN_TIMER_FORMAT = "%.1f|cff" .. MUTED_HEX .. " / %.1f|r"
local PLAIN_TIMER_FORMAT_LONG = "%.1f|cff" .. MUTED_HEX .. " / %.0f|r"

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

-- Channels that show an "n/T" tick counter on the player tab. clipAfter: the tick after which
-- the channel is normally cut for the next cast ("CUT" in pink from then on). Health Funnel and
-- Shoot (the wand) deliberately have no entry: no counter. Looked up by spell id first (a cast
-- reports its RANK id, and a localized client changes the name), then by English name.
local MIND_FLAY = { ticks = 3, clipAfter = 2 }      -- 3s
local DRAIN_SOUL = { ticks = 5 }                    -- 15s
local DRAIN_LIFE = { ticks = 5 }                    -- 5s

local CHANNEL_TICKS = {
    ["Drain Soul"] = DRAIN_SOUL,
    ["Drain Life"] = DRAIN_LIFE,
    ["Mind Flay"] = MIND_FLAY,
}

-- Every rank's spell id (TBC: Mind Flay 7, Drain Soul 5, Drain Life 8). From memory, not read off
-- the client: a rank missing here still gets its counter through the name.
local CHANNEL_TICKS_BY_ID = {}
local function AddTickIds(spec, ids)
    for _, id in ipairs(ids) do CHANNEL_TICKS_BY_ID[id] = spec end
end
AddTickIds(MIND_FLAY, { 15407, 17311, 17312, 17313, 17314, 18807, 25387 })
AddTickIds(DRAIN_SOUL, { 1120, 8288, 8289, 11675, 27217 })
AddTickIds(DRAIN_LIFE, { 689, 699, 709, 7651, 11699, 11700, 27219, 27220 })

local function TickSpecFor(name, spellID)
    if type(spellID) == "number" and not IsSecret(spellID) then
        local byId = CHANNEL_TICKS_BY_ID[spellID]
        if byId then return byId end
    end
    if type(name) == "string" and not IsSecret(name) then return CHANNEL_TICKS[name] end
    return nil
end

-------------------------------------------------------------------------------
-- Small helpers
-------------------------------------------------------------------------------

-- Text printed before " failed: <err>" for a cast-bar step/registration failure.
local function DescribeCastBarStep(label)
    return "ForeverSTUwave castbar: " .. label
end

-- Runs one step under pcall so a failing step cannot break the bar silently; prints which
-- step failed plus the error. Shared plumbing: FS.FrameHelpers.NewStepRunner.
local TryStep = FS.FrameHelpers.NewStepRunner(DescribeCastBarStep)

local function ReportRegisterFailure(event, err)
    print(DescribeCastBarStep("register " .. event) .. " failed: " .. tostring(err))
end

local function SafeRegisterUnitEvent(events, event, unit)
    FS.FrameHelpers.SafeRegisterUnitEvent(events, event, unit, ReportRegisterFailure)
end

-- 12.0 "secret values": the feature-detected duration-object pair PetCastBar.lua uses.
local HAS_CAST_DURATION = type(UnitCastingDuration) == "function"
    and type(UnitChannelDuration) == "function"

local function HasTimerDuration(bar)
    return type(bar.SetTimerDuration) == "function"
end

-- True when a value exists, WITHOUT a nil test on a secret (comparing a secret to nil is
-- itself an illegal comparison): a secret is unknown but present.
local function Present(v)
    return IsSecret(v) or v ~= nil
end

-- A plain finite number (never a secret).
local function IsNum(v)
    return type(v) == "number" and not IsSecret(v) and v == v
end

-- A time in ms -> seconds, or nil when it is secret or not a number. The only place a
-- UnitCastingInfo time is ever divided, and only after the guard.
local function PlainSeconds(ms)
    if IsSecret(ms) or type(ms) ~= "number" then return nil end
    return ms / 1000
end

-- Several generic casts carry a subtext rank that the game exposes as part of
-- the name, e.g. looting a chest casts "Opening - No Text". Show just the verb.
-- Written with ASCII escapes only: embedding a literal en/em dash here put raw
-- UTF-8 bytes (which include newlines) inside the pattern and broke the file.
local function CleanSpellName(name)
    if type(name) ~= "string" then return "" end

    -- UnitCastingInfo/UnitChannelInfo hand back a PLAIN name for casts by units we
    -- control and a SECRET one for everybody else (seen live on another player
    -- crafting). type() still reports "string" on a secret, so the guard above lets it
    -- through; the throw is on the first string method (a method call is an index, and
    -- indexing a secret is forbidden). There is no way to inspect it; hand it straight
    -- back and let SetText, which is whitelisted for secrets, render it.
    if IsSecret(name) then return name end

    -- Cut at a trailing "No Text" subtext and trim the separator before it.
    local cut = name:find("No Text", 1, true)
    if not cut then return name end

    local trimmed = name:sub(1, cut - 1)
    trimmed = trimmed:gsub("[%s%-]+$", "")
    trimmed = trimmed:gsub("%s+$", "")
    if trimmed ~= "" then return trimmed end
    return name
end

-- The tab's text: the cleaned name in capitals (the mockup's tab). A secret name stays as it
-- is: upper-casing it would be a string method.
local function TabLabel(name)
    local clean = CleanSpellName(name)
    if IsSecret(clean) then return clean end
    return clean:upper()
end

-------------------------------------------------------------------------------
-- Frame assembly
-------------------------------------------------------------------------------

-- A dedicated pink halo texture just outside the bar (nine-sliced, ADD). One call per
-- region: the engine's burst and hold glow must be separate regions.
local function BuildGlow(parent)
    local pad = Theme.SLICE_GLOW_PAD
    local glow = AddSliceTexture(parent, Theme.SLICE_GLOW_TEXTURE, COLOR_HEALTH, "BACKGROUND", -1, -pad)
    ApplyNineSlice(glow, Theme.SLICE_GLOW_MARGIN)
    glow:SetBlendMode("ADD")
    return glow
end

-- One slanted end of the tab: the shared tab_slant.tga wedge (a right triangle in alpha, solid
-- side on the right, wide at the bottom: the LEFT end of a tab attached at its bottom, as it
-- comes), stretched to SLANT x full height so both ends keep the same angle. `top` = the tab
-- hangs from a top edge (wide end at the top): the wedge is flipped vertically for it, for BOTH
-- ends, so the two caps are always wide at the same vertical end (a trapezoid, not a
-- parallelogram). The right end is the mirror image of the left: flipped horizontally.
local function TabCap(tab, layer, sublevel, color, right, top, x)
    local cap = tab:CreateTexture(nil, layer, nil, sublevel)
    cap:SetTexture(TAB_SLANT_TEXTURE)
    cap:SetWidth(TAB_SLANT)
    local side = right and "RIGHT" or "LEFT"
    cap:SetPoint("TOP" .. side, tab, "TOP" .. side, right and -x or x, 0)
    cap:SetPoint("BOTTOM" .. side, tab, "BOTTOM" .. side, right and -x or x, 0)
    local flipX, flipY = right, top
    cap:SetTexCoord(flipX and 1 or 0, flipX and 0 or 1, flipY and 1 or 0, flipY and 0 or 1)
    cap:SetVertexColor(color[1], color[2], color[3], color[4] or 1)
    return cap
end

-- The spell-name tab: the mockup's trapezoid on the outer edge of the frame (target: above, right
-- end; player: below, left end), SLANT units of lean at each end, the narrow side away from the
-- frame, its free edge and both slanted sides stroked 1px (the side attached to the frame is not:
-- the frame's own outline is there). A flat fill between two flipped wedges, the way a leaning shape
-- has to be built (it cannot be nine-sliced, see media/generate_tab_slant.py); the stroke is a
-- violet wedge under each fill wedge, which sits one stroke width further in. Holds the name and,
-- for the player, the tick counter.
local STROKE_DX = math.sqrt(1 + (TAB_SLANT / TAB_H) ^ 2)   -- one pixel across the slant, in x

local function BuildTab(S)
    local f = S.frame
    local top = not S.isTarget                     -- the player's tab hangs under the frame
    local tab = CreateFrame("Frame", nil, f)
    tab:SetSize(TAB_SLANT * 2 + TAB_PAD * 2, TAB_H)
    if S.isTarget then
        tab:SetPoint("BOTTOMRIGHT", f, "TOPRIGHT", -TAB_EDGE_INSET, 0)
    else
        tab:SetPoint("TOPLEFT", f, "BOTTOMLEFT", TAB_EDGE_INSET, 0)
    end

    local track = { COLOR_BAR_TRACK[1], COLOR_BAR_TRACK[2], COLOR_BAR_TRACK[3], 0.95 }
    local parts = {}
    parts.edgeL = TabCap(tab, "BACKGROUND", 0, COLOR_BORDER, false, top, 0)
    parts.edgeR = TabCap(tab, "BACKGROUND", 0, COLOR_BORDER, true, top, 0)
    parts.capL = TabCap(tab, "BACKGROUND", 1, track, false, top, STROKE_DX)
    parts.capR = TabCap(tab, "BACKGROUND", 1, track, true, top, STROKE_DX)
    local body = tab:CreateTexture(nil, "BACKGROUND", nil, 1)
    body:SetColorTexture(track[1], track[2], track[3], track[4])
    body:SetPoint("TOPLEFT", tab, "TOPLEFT", TAB_SLANT + STROKE_DX, 0)
    body:SetPoint("BOTTOMRIGHT", tab, "BOTTOMRIGHT", -(TAB_SLANT + STROKE_DX), 0)
    parts.body = body

    local line = tab:CreateTexture(nil, "BORDER")
    line:SetColorTexture(COLOR_BORDER[1], COLOR_BORDER[2], COLOR_BORDER[3], 1)
    local edge = top and "BOTTOM" or "TOP"        -- the free edge: far from the frame
    line:SetPoint(edge .. "LEFT", tab, edge .. "LEFT", TAB_SLANT, 0)
    line:SetPoint(edge .. "RIGHT", tab, edge .. "RIGHT", -TAB_SLANT, 0)
    line:SetHeight(1)
    parts.line = line

    local name = tab:CreateFontString(nil, "OVERLAY")
    name:SetPoint("LEFT", tab, "LEFT", TAB_SLANT + TAB_PAD, 0)
    name:SetJustifyH("LEFT")
    if name.SetWordWrap then name:SetWordWrap(false) end
    ApplyMono(name, TAB_FONT_SIZE, COLOR_POWER)

    local ticks = tab:CreateFontString(nil, "OVERLAY")
    ticks:SetPoint("LEFT", name, "RIGHT", TAB_TICK_GAP, 0)
    ticks:SetJustifyH("LEFT")
    ApplyMono(ticks, TAB_FONT_SIZE, COLOR_PARCHMENT)
    ticks:Hide()

    S.tab, S.tabName, S.tabTicks, S.tabParts = tab, name, ticks, parts
end

-- Strip fallback tile scale: the strip file is 32 wide with 2 chevrons (16 per chevron).
-- Scaling the bar by 2 * pitch / 32 makes one tile two engine pitches wide (the engine's own
-- whole-pixel pitch, run.pitch, refreshed from run.onLayout). The anchors still span the run,
-- so the texture is stretched to its height.
local function ApplyStripScale(S)
    local strip, run = S.strip, S.run
    if not (strip and run) then return end
    local pitch = run.pitch
    if not pitch or pitch <= 0 then return end
    local scale = 2 * pitch / Theme.CAST_CHEVRON_STRIP_TILE_W
    if scale < 0.01 then scale = 0.01 end
    strip:SetScale(scale)
end

-------------------------------------------------------------------------------
-- Stack placement (see the header for the math)
-------------------------------------------------------------------------------

local bars = {}            -- bars.player / bars.target

-- The CENTER offset that puts a frame's `size`-long edge (its left, or its bottom) on a whole
-- physical pixel: `uiCentre` is UIParent's centre on that axis, `px` one pixel, all UIParent units.
local function SnapOffset(centreOff, uiCentre, size, px)
    local edge = math.floor((uiCentre + centreOff - size / 2) / px + 0.5) * px
    return edge + size / 2 - uiCentre
end

-- Seats one frame at CENTER offsets (x, y) from UIParent's centre, snapped to whole pixels when
-- `px` is known. True when it ended up somewhere new.
local function SeatBar(S, x, y, px, ux, uy)
    local fw = S.frame:GetWidth()
    if px and IsNum(fw) and fw > 0 then
        x = SnapOffset(x, ux, fw, px)
        y = SnapOffset(y, uy, FRAME_H, px)
    end
    local moved = S.seatX ~= x or S.seatY ~= y
    S.seatX, S.seatY = x, y
    S.frame:ClearAllPoints()
    S.frame:SetPoint("CENTER", UIParent, "CENTER", x, y)
    return moved
end

-- The CENTER offsets of one bar: its FS.Layout entry (`tcast` / `pcast`, UI units), or the old fixed
-- seat when Layout or the entry is missing or unusable.
local function StackSeat(id, fallbackY)
    local L = FS.Layout and FS.Layout[id]
    if type(L) == "table" and IsNum(L.x) and IsNum(L.y) then return L.x, L.y end
    return SEAT_X, fallbackY
end

-- Seats both bars on their layout entries. Returns true when either bar moved.
local function PlaceStack()
    local player, target = bars.player, bars.target
    if not (player and target) then return false end

    -- Whole physical pixels: the engine nudges its run's origin onto a pixel from the frame's
    -- GetLeft, so a frame resting on a fractional pixel would make that nudge depend on where the
    -- stack happened to be placed. One pixel in UIParent units is the engine's own run.px.
    local px = player.run.px
    local ux, uy = UIParent:GetCenter()
    if not (IsNum(px) and px > 0 and IsNum(ux) and IsNum(uy)) then px = nil end

    local half = GAP / 2 + FRAME_H / 2
    local tx, ty = StackSeat("tcast", SEAT_Y + half)
    local pX, pY = StackSeat("pcast", SEAT_Y - half)
    local movedTarget = SeatBar(target, tx, ty, px, ux, uy)
    local movedPlayer = SeatBar(player, pX, pY, px, ux, uy)
    return movedTarget or movedPlayer
end

-- PlaceStack for the callers that are NOT the engine's onLayout (build, the scale and display
-- events): when the stack moved, each engine re-measures its origin against the new seat. A
-- Layout from onLayout itself would be dropped as nested, and needs no second pass: onLayout
-- runs PlaceStack, not this, so the two cannot loop.
local function PlaceAndRefit()
    if not PlaceStack() then return end
    for _, S in ipairs({ bars.player, bars.target }) do
        S.run:Layout(runRequest, RUN_H)
    end
end

-------------------------------------------------------------------------------
-- Readout: timer text and the tick counter
-------------------------------------------------------------------------------

local function ClearReadout(S)
    S.ticker:Hide()
    S.activeDuration = nil
    S.timer:SetText("")
    S.tabTicks:SetText("")
    S.tabTicks:Hide()
    S.tickSpec, S.tickDone, S.tickCut = nil, nil, nil
end

-- Writes the tick counter for `done` ticks. Only touches the FontString when the number or
-- the CUT state changed.
local function WriteTicks(S, done)
    local spec = S.tickSpec
    local cut = (spec.clipAfter ~= nil and done >= spec.clipAfter)
    if done == S.tickDone and cut == S.tickCut then return end
    S.tickDone, S.tickCut = done, cut
    if cut then
        S.tabTicks:SetTextColor(COLOR_HEALTH[1], COLOR_HEALTH[2], COLOR_HEALTH[3])
        S.tabTicks:SetText("CUT")
    else
        S.tabTicks:SetTextColor(COLOR_PARCHMENT[1], COLOR_PARCHMENT[2], COLOR_PARCHMENT[3])
        S.tabTicks:SetFormattedText("%d/%d", done, spec.ticks)
    end
end

-- Plain-timed readout at clock `now`, from the engine's own schedule (S.t0 / S.t1, the plain
-- GetTime seconds the engine was handed): "elapsed / total" for a cast, "remaining / total"
-- for a channel, and the tick counter. The " / total" part is the mockup's muted colour (every
-- number here is plain, so a colour escape in the format is safe). A total of 10s or more drops
-- the decimal on the total so the text still fits the 9 character column ("14.9 / 15").
local function WritePlainReadout(S, now)
    local total = S.t1 - S.t0
    if total <= 0 then return end
    local el = now - S.t0
    if el < 0 then el = 0 elseif el > total then el = total end
    S.timer:SetFormattedText(total >= 10 and PLAIN_TIMER_FORMAT_LONG or PLAIN_TIMER_FORMAT,
        S.channeling and (total - el) or el, total)
    if S.tickSpec then
        local n = S.tickSpec.ticks
        local done = math.floor(el / total * n + 1e-6)
        if done > n then done = n end
        WriteTicks(S, done)
    end
end

-- Secret-timed readout: the duration object's numbers go straight into SetFormattedText
-- (a pcall; never compared, truth-tested or formatted by hand). Elapsed over total for a
-- cast, remaining over total for a channel. The first failure latches and logs once. One colour
-- only: the numbers may be secret, and nothing here is known to take a colour escape around them.
-- The total drops its decimal from 10s up, as the plain path does, but only when it is a plain
-- number: a secret total cannot be compared, so it keeps the decimal.
local timerBroken = false

local function WriteDurationText(S)
    local d = S.activeDuration
    local total = d:GetTotalDuration()
    S.timer:SetFormattedText((IsNum(total) and total >= 10) and "%.1f / %.0f" or "%.1f / %.1f",
        S.channeling and d:GetRemainingDuration() or d:GetElapsedDuration(), total)
end

local function WriteDurationReadout(S)
    if not S.activeDuration or timerBroken then return end
    if pcall(WriteDurationText, S) then return end
    timerBroken = true
    S.timer:SetText("")
    FS.LogDegradeOnce("castbar_timer",
        "ForeverSTUwave castbar: timer text disabled, SetFormattedText rejected the duration object's values.")
end

local GoIdle   -- assigned in "Cast state" below; the strip safety net ends a bar through it

-- The strip's end-of-cast safety net, on the readout ticker (a strip bar is engine timed, with no
-- schedule of its own to notice the end, so a lost verdict event would strand it): the unit is
-- plainly gone, or neither UnitCastingInfo nor UnitChannelInfo reads back a plain nil name. A
-- secret anything is unknown, never gone, and is IsSecret-checked before any nil compare.
local function StripIsOver(S)
    local exists = UnitExists(S.unit)
    if not IsSecret(exists) and not exists then return true end
    local casting, channelling = UnitCastingInfo(S.unit), UnitChannelInfo(S.unit)
    return not IsSecret(casting) and casting == nil and not IsSecret(channelling) and channelling == nil
end

local function RefreshReadout(S)
    if S.mode == "run" then
        WritePlainReadout(S, GetTime())
    elseif S.mode == "strip" then
        if StripIsOver(S) then
            GoIdle(S)
            return
        end
        WriteDurationReadout(S)
    end
end

-- One step of the readout ticker (Stack A's and a view bar's): refreshes every TICK_INTERVAL.
local function TickReadout(S, elapsed)
    S.tickerElapsed = S.tickerElapsed + elapsed
    if S.tickerElapsed < TICK_INTERVAL then return end
    S.tickerElapsed = 0
    RefreshReadout(S)
end

local function StartReadout(S)
    RefreshReadout(S)
    S.tickerElapsed = 0
    S.ticker:Show()
end

-- A verdict ends the live readout. `at` = the clock to settle the text at (the scheduled end
-- for a lock-in or a natural channel end, now for an interrupt); nil leaves the text as is.
local function FreezeReadout(S, at)
    S.ticker:Hide()
    if at and S.mode == "run" then WritePlainReadout(S, at) end
end

-------------------------------------------------------------------------------
-- Cast state
-------------------------------------------------------------------------------

-- Normalizes UnitCastingInfo/UnitChannelInfo for the bar's unit: the name, texture, times,
-- castID (UnitCastingInfo's 7th return; a channel has none) and notInterruptible. All carried
-- as opaque values: a secret is never compared here.
local function GetCastInfo(unit)
    local name, _, texture, startMS, endMS, _, castID, notInterruptible = UnitCastingInfo(unit)
    if Present(name) then
        return {
            name = name, texture = texture, channeling = false, notInterruptible = notInterruptible,
            startMS = startMS, endMS = endMS, castID = castID,
        }
    end

    -- A channel's 8th return is its spell id (plain for our own channels, which is all it is used for).
    local spellID
    name, _, texture, startMS, endMS, _, notInterruptible, spellID = UnitChannelInfo(unit)
    if Present(name) then
        return {
            name = name, texture = texture, channeling = true, notInterruptible = notInterruptible,
            startMS = startMS, endMS = endMS, spellID = spellID,
        }
    end

    return nil
end

-- True only when UnitCastingInfo says, in a plain value, that the unit is not casting. A
-- secret name means unknown, so it is not "gone".
local function CastIsGone(S)
    local exists = UnitExists(S.unit)
    if not IsSecret(exists) and not exists then return true end
    local name = UnitCastingInfo(S.unit)
    if IsSecret(name) then return false end
    return name == nil
end

-- Shield tint: the ONLY sanctioned secret-boolean consumer is SetAlphaFromBoolean, so the flag
-- is type-checked (legal on a secret) and handed straight to the setter, never truth-tested.
local function ApplyCastInterruptible(S, notInterruptible)
    local shield = S.shield
    if type(notInterruptible) == "boolean" then
        if type(shield.SetAlphaFromBoolean) == "function" then
            shield:SetAlphaFromBoolean(notInterruptible, 1, 0)
        end
        return
    end
    shield:SetAlpha(0)
end

-- Sets the tab's text and width and shows it. The tab is as wide as its name plus, for a channel
-- with a counter, the widest counter text, plus the padding and a slant at each end. A secret name
-- cannot be measured and gets a fixed width.
local function SetTab(S, name)
    local label = TabLabel(name)
    S.tabName:SetText(label)
    S.tab:Show()

    local nameW = TAB_SECRET_NAME_W
    if not IsSecret(label) then
        local w = S.tabName:GetStringWidth()
        nameW = IsNum(w) and w or 0
    end
    local tickW = 0
    if S.tickSpec then
        S.tabTicks:SetFormattedText("%d/%d", S.tickSpec.ticks, S.tickSpec.ticks)
        S.tabTicks:Show()
        local w = S.tabTicks:GetStringWidth()
        tickW = TAB_TICK_GAP + (IsNum(w) and w or 0)
        S.tickDone, S.tickCut = nil, nil
    else
        S.tabTicks:Hide()
    end
    S.tab:SetWidth(nameW + tickW + 2 * TAB_PAD + 2 * TAB_SLANT)
end

-- The OPT-IN idle row (FS.CastBars.SetIdleVisible, for the HUD): the engine's row of unlit
-- chevrons at IDLE_DIM_ALPHA between casts, with the bar's idle hint (if any) on the tab, instead
-- of a hidden bar. Off by default, so a bar only shows while there is something to show.
local idleVisible = false

-- The resting alpha of the idle row (FS.CastBars.SetRestAlpha, 1 by default): the HUD's
-- out-of-combat look, the mockup's `.hud-stack.ooc .bar-host { opacity: .55 }`, on top of the
-- engine's own dim chevrons. The engine owns the frame's alpha and caches the last value it wrote,
-- so the rest alpha is written only AFTER ShowIdle (the engine's last write is then 1), and
-- ClearRest puts the frame back to 1 before anything the engine animates starts, so its cache and
-- the frame agree again. A running cast, a verdict and a hidden bar are never dimmed.
local restAlpha = 1

local function ClearRest(S)
    if S.restDimmed then
        S.restDimmed = false
        S.frame:SetAlpha(1)
    end
end

local function ApplyRest(S)
    if restAlpha < 1 then
        S.restDimmed = true
        S.frame:SetAlpha(restAlpha)
    else
        ClearRest(S)
    end
end

local function ShowIdleRow(S)
    S.run:ShowIdle(S.idleDim or IDLE_DIM_ALPHA)
    ApplyRest(S)
    S.frame:Show()
    if S.idleHint then
        S.tickSpec = nil
        SetTab(S, S.idleHint)
    else
        S.tab:Hide()
    end
end

local function HideIdleRow(S)
    ClearRest(S)
    S.run:Stop()
    S.frame:Hide()
end

-- Ends whatever is showing: the engine is reset and the bar goes to its resting state, hidden
-- unless the idle row is on. The engine's onFinished, a quiet stop, an abandoned cast, the
-- PLAYER_ENTERING_WORLD reset and the build all come here.
function GoIdle(S)
    S.mode = nil
    ClearReadout(S)
    S.strip:Hide()
    S.icon:SetTexture(nil)
    S.shield:SetAlpha(0)
    S.tabName:SetText("")
    if idleVisible or S.alwaysIdle then ShowIdleRow(S) else HideIdleRow(S) end
end

-- An abandoned cast: the unit changed, or a refresh found nothing to show.
local AbortCast = GoIdle

local function FetchDuration(S, isChannel)
    if not HAS_CAST_DURATION then return nil end
    local ok, d = pcall(isChannel and UnitChannelDuration or UnitCastingDuration, S.unit)
    if ok then return d end
    return nil
end

local function SetStripDuration(S, duration)
    -- A channel gets the IDENTICAL single-arg call as a cast: this client's StatusBar has no
    -- reverse-fill variant, so a channel fills up rather than draining down (the accepted
    -- limitation PetCastBar.lua documents).
    local strip = S.strip
    if duration and HasTimerDuration(strip) then
        pcall(function() strip:SetTimerDuration(duration) end)
    else
        -- No duration-object support: a static full bar rather than a throw.
        strip:SetValue(1)
    end
end

-- Secret-timing fallback: no engine, an engine-timed StatusBar instead.
local function StartStrip(S, info)
    -- Stop() also puts the frame's alpha back to 1 after an earlier outage.
    S.run:Stop()
    S.run:SetCastID(info.castID)
    S.mode = "strip"
    S.channeling = info.channeling
    S.tickSpec = nil

    local duration = FetchDuration(S, info.channeling)
    S.strip:SetMinMaxValues(0, 1)
    SetStripDuration(S, duration)
    S.strip:Show()
    S.activeDuration = duration
    SetTab(S, info.name)
    S.frame:Show()
    StartReadout(S)
end

-- Starts (or restarts) the bar for `info`. The bar is shown first: the engine's OnUpdate does
-- not run while an ancestor is hidden.
local function BeginCast(S, info)
    ClearRest(S)
    S.strip:Hide()
    S.icon:SetTexture(info.texture)
    ApplyCastInterruptible(S, info.notInterruptible)
    S.frame:Show()

    local startTime, endTime = PlainSeconds(info.startMS), PlainSeconds(info.endMS)
    -- nil times (secret) are refused by the engine without a throw.
    if not S.stripOnly and S.run:StartCast(startTime, endTime, info.channeling, info.castID) then
        S.mode = "run"
        S.channeling = info.channeling
        S.t0, S.t1 = startTime, endTime
        S.activeDuration = nil
        -- The counter's spec: the player's own channels only (a target's name is secret).
        S.tickSpec = nil
        if info.channeling and not S.isTarget then
            S.tickSpec = TickSpecFor(info.name, info.spellID)
        end
        SetTab(S, info.name)
        StartReadout(S)
        return
    end

    if startTime and endTime and not S.stripOnly then
        -- Plain times the engine still refused: a stale or degenerate cast. Nothing real to show.
        AbortCast(S)
        return
    end

    StartStrip(S, info)
end

-- START / CHANNEL_START and the build-time seed: show whatever the unit is casting now.
local function StartFromUnit(S)
    if not UnitExists(S.unit) then
        AbortCast(S)
        return
    end

    local info = GetCastInfo(S.unit)
    if info then
        BeginCast(S, info)
        return
    end

    -- Nothing to show. While a verdict is playing (hold, fade, outage) that is the expected
    -- state, and a nil refresh must not kill it.
    if S.mode == "run" and S.run:IsFinishing() then return end
    AbortCast(S)
end

-- DELAYED / CHANNEL_UPDATE: new times for the running cast.
local function RetimeCast(S)
    if S.mode == "run" and S.run:IsFinishing() then return end

    local info = GetCastInfo(S.unit)
    if not info then return end

    -- A missed START, or the unit moved from a cast to a channel: begin it afresh.
    if S.mode == nil or info.channeling ~= S.channeling then
        BeginCast(S, info)
        return
    end

    if S.mode == "strip" then
        local duration = FetchDuration(S, S.channeling)
        SetStripDuration(S, duration)
        S.activeDuration = duration
        WriteDurationReadout(S)
        return
    end

    local startTime, endTime = PlainSeconds(info.startMS), PlainSeconds(info.endMS)
    if startTime and endTime then
        -- UpdateTimes, not StartCast: StartCast would reset every lit segment's ignite.
        if S.run:UpdateTimes(startTime, endTime) then
            S.t0, S.t1 = startTime, endTime
            WritePlainReadout(S, GetTime())
        end
    else
        -- The times went secret mid cast: hand over.
        StartStrip(S, info)
    end
end

-- Verdict helpers: the live readout stops with the verdict.
local function SucceedCast(S)
    FreezeReadout(S, S.t1)
    S.run:Succeed()
end

local function InterruptCast(S)
    FreezeReadout(S, GetTime())
    -- Only a view bar (GunsightTape's) sets onVerdict, so Stack A runs exactly as before. pcall'd: a
    -- display's look must never stop the verdict itself.
    if S.onVerdict then pcall(S.onVerdict, S, "interrupt") end
    S.run:Interrupt()
end

-- CHANNEL_STOP without a kick: the engine decides natural end or clip from its own schedule.
local function EndChannel(S)
    local result = S.run:EndChannel()
    if result == true then
        FreezeReadout(S, S.t1)      -- the finish plays; onFinished goes idle at its end
    elseif result == false then
        GoIdle(S)                   -- a clip: the engine already stopped, no onFinished
    end
end

-- Verdicts while the engine runs, in the cast phase only (see the header for the map).
local function HandleRunVerdict(S, event, castID, interruptedBy)
    if event == "UNIT_SPELLCAST_CHANNEL_STOP" then
        if not S.channeling then return end
        if IsSecret(interruptedBy) then
            GoIdle(S)               -- cannot tell kicked from ended: the quiet outcome
        elseif interruptedBy ~= nil then
            InterruptCast(S)
        else
            EndChannel(S)
        end
        return
    end

    if S.channeling then return end

    -- true / false / nil (nil = a castID is missing or secret; never compared).
    local matches = S.run:MatchesCast(castID)
    if event == "UNIT_SPELLCAST_STOP" then
        if matches == true or (matches == nil and S.run:IsComplete()) then
            SucceedCast(S)
        elseif matches == nil and CastIsGone(S) then
            GoIdle(S)
        end
    elseif event == "UNIT_SPELLCAST_INTERRUPTED" then
        if matches ~= false then InterruptCast(S) end
    elseif event == "UNIT_SPELLCAST_FAILED" then
        if matches == true or (matches == nil and CastIsGone(S)) then InterruptCast(S) end
    end
end

-- The strip fallback has no animation to protect: the same matching decides, and a verdict
-- just ends the bar.
local function HandleStripVerdict(S, event, castID)
    if event == "UNIT_SPELLCAST_CHANNEL_STOP" then
        if S.channeling then GoIdle(S) end
        return
    end

    if S.channeling then return end

    local matches = S.run:MatchesCast(castID)
    if event == "UNIT_SPELLCAST_INTERRUPTED" then
        if matches ~= false then GoIdle(S) end
    elseif matches == true or (matches == nil and CastIsGone(S)) then
        GoIdle(S)
    end
end

-- Drops whatever is showing and re-reads the unit: it may be mid cast already.
local function ResetFromUnit(S)
    AbortCast(S)
    if UnitExists(S.unit) then StartFromUnit(S) end
end

local function HandleEvent(S, event, castID, interruptedBy)
    -- Neither carries a unit or a castID, so they run before any unit test. A loading screen
    -- can swallow a verdict; a target change makes the old target's cast meaningless.
    if event == "PLAYER_ENTERING_WORLD" or event == "PLAYER_TARGET_CHANGED" then
        ResetFromUnit(S)
        return
    end

    if event == "UNIT_SPELLCAST_START" or event == "UNIT_SPELLCAST_CHANNEL_START" then
        StartFromUnit(S)
        return
    end

    if event == "UNIT_SPELLCAST_DELAYED" or event == "UNIT_SPELLCAST_CHANNEL_UPDATE" then
        RetimeCast(S)
        return
    end

    if S.mode == "strip" then
        HandleStripVerdict(S, event, castID)
    elseif S.mode == "run" and S.run:GetPhase() == "cast" then
        -- Not "cast" means a verdict is already playing (IsFinishing) or the run is idle:
        -- STOP/FAILED/INTERRUPTED are ignored.
        HandleRunVerdict(S, event, castID, interruptedBy)
    end
end

-------------------------------------------------------------------------------
-- Assembly
-------------------------------------------------------------------------------

-- The timer column is as wide as the font makes TIMER_SAMPLE: measured once, on the first bar's
-- timer FontString (the font is already applied to it), and shared by both bars so the stack stays
-- one width. A client that cannot measure (a throw, a secret, a non-number, no width) keeps the
-- mockup's 56. Sets chromeW and runRequest, which nothing has read yet at that point.
local timerMeasured = false

local function MeasureTimerColumn(fontString)
    if timerMeasured then return end
    timerMeasured = true
    local timerW = TIMER_W_FALLBACK
    local ok, w = pcall(function()
        fontString:SetText(TIMER_SAMPLE)
        return fontString:GetStringWidth()
    end)
    fontString:SetText("")
    if ok and IsNum(w) and w > 0 then timerW = math.ceil(w - 1e-6) + TIMER_PAD end
    chromeW = ChromeFor(timerW)
    runRequest = REQUEST_W - chromeW
end

-- The engine re-lays out on a scale or display change by itself and tells us here: the frame
-- is the run plus the fixed chrome, so it is re-sized from run.W, the strip is re-scaled and the
-- stack re-placed. (A Layout call from here would be dropped as nested; none is made.)
local function OnRunLayout(S, run)
    S.frame:SetWidth(run.W + chromeW)
    ApplyStripScale(S)
    PlaceStack()
end

local function BuildBar(unit, frameName)
    local S = { unit = unit, isTarget = (unit == "target"), mode = nil, channeling = false }

    local f = CreateFrame("Frame", frameName, UIParent)
    f:SetSize(REQUEST_W, FRAME_H)
    f:Hide() -- shown only while a cast/channel/verdict is on screen
    S.frame = f

    -- Chrome: the chamfered plate and outline. The outline is the engine's flareTarget; it
    -- starts at the engine's flareBase (COLOR_BORDER), which is what the flare eases back to.
    AddCut2Texture(f, Theme.SLICE_CUT2_FILL_TEXTURE, { COLOR_BAR_TRACK[1], COLOR_BAR_TRACK[2], COLOR_BAR_TRACK[3], 0.92 }, "BACKGROUND", 0)
    local outline = AddCut2Texture(f, Theme.SLICE_CUT2_OUTLINE_TEXTURE, COLOR_BORDER, "BORDER")
    local glowBurst = BuildGlow(f)
    local holdGlow = BuildGlow(f)
    holdGlow:SetAlpha(0)

    -- Spell icon (18 square) and its interruptible shield.
    local icon = f:CreateTexture(nil, "ARTWORK")
    icon:SetPoint("TOPLEFT", f, "TOPLEFT", CHAMFER, -RUN_Y)
    icon:SetSize(ICON, ICON)
    icon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
    icon:SetTexture(nil)
    S.icon = icon
    -- The mockup's 1px --line stroke around the icon, inside its edge, above the shield.
    local function IconEdge(point1, point2, horizontal)
        local t = f:CreateTexture(nil, "OVERLAY", nil, 2)
        t:SetColorTexture(COLOR_BAR_BORDER[1], COLOR_BAR_BORDER[2], COLOR_BAR_BORDER[3], 1)
        t:SetPoint(point1, icon, point1, 0, 0)
        t:SetPoint(point2, icon, point2, 0, 0)
        if horizontal then t:SetHeight(1) else t:SetWidth(1) end
        return t
    end
    S.iconEdges = {
        IconEdge("TOPLEFT", "TOPRIGHT", true), IconEdge("BOTTOMLEFT", "BOTTOMRIGHT", true),
        IconEdge("TOPLEFT", "BOTTOMLEFT", false), IconEdge("TOPRIGHT", "BOTTOMRIGHT", false),
    }
    local shield = f:CreateTexture(nil, "OVERLAY")
    shield:SetAllPoints(icon)
    shield:SetColorTexture(1, 1, 1, 1)
    shield:SetVertexColor(COLOR_CAST_NO_INTERRUPT[1], COLOR_CAST_NO_INTERRUPT[2], COLOR_CAST_NO_INTERRUPT[3], 1)
    shield:SetAlpha(0)
    S.shield = shield

    -- Timer column: right aligned, no fixed width on the FontString (a width would truncate an
    -- overlong text with an ellipsis; it grows leftwards instead).
    local timer = f:CreateFontString(nil, "OVERLAY")
    timer:SetPoint("RIGHT", f, "RIGHT", -(CHAMFER + 2), 0)
    timer:SetJustifyH("RIGHT")
    ApplyMono(timer, TIMER_FONT_SIZE, COLOR_PARCHMENT)
    timer:SetText("")
    S.timer = timer
    MeasureTimerColumn(timer)     -- before the first Layout below: chromeW and runRequest come from it

    BuildTab(S)

    -- The engine: fitWidth, so it widens its own run to whole chevrons. It sizes its own frame
    -- (no points given), so only its seat is ours.
    local run = FS.ChevronCastBar.Create(f, {
        fitWidth = true,
        seedSalt = SEED_SALT,
        scaleTarget = f,
        alphaTarget = f,
        flareTarget = outline,
        glowBurst = glowBurst,
        glowBurstExpand = GLOW_BURST_EXPAND,
        holdGlow = holdGlow,
    })
    S.run = run
    run.frame:SetPoint("TOPLEFT", f, "TOPLEFT", RUN_X, -RUN_Y)
    run.onFinished = function() GoIdle(S) end
    run.onLayout = function(r) OnRunLayout(S, r) end

    -- Secret-timing fallback bar (see the header), built once, hidden until needed. A child of
    -- the bar frame, not of the run frame (Stop() hides that one), spanning the run's rect.
    local strip = CreateFrame("StatusBar", nil, f)
    strip:SetPoint("TOPLEFT", run.frame, "TOPLEFT", 0, 0)
    strip:SetPoint("BOTTOMRIGHT", run.frame, "BOTTOMRIGHT", 0, 0)
    strip:SetStatusBarTexture(Theme.CAST_CHEVRON_STRIP_TEXTURE)
    strip:SetStatusBarColor(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 1)
    local stripFill = strip:GetStatusBarTexture()
    if stripFill and stripFill.SetHorizTile then stripFill:SetHorizTile(true) end
    strip:SetMinMaxValues(0, 1)
    strip:SetValue(0)
    strip:Hide()
    S.strip = strip

    -- The readout ticker: hidden unless a cast is live, so its OnUpdate costs nothing between
    -- casts. The closure is built once.
    S.tickerElapsed = 0
    local ticker = CreateFrame("Frame", nil, f)
    ticker:Hide()
    ticker:SetScript("OnUpdate", function(_, elapsed) TickReadout(S, elapsed) end)
    S.ticker = ticker

    -- First layout, now that onLayout and the run's seat exist: asks for RUN_REQUEST, gets the
    -- fitted width back through onLayout.
    run:Layout(runRequest, RUN_H)
    return S
end

-------------------------------------------------------------------------------
-- Events
-------------------------------------------------------------------------------

-- Idempotent: the event frame is made once per bar and reused (a hand-off between displays calls this
-- again), so repeated hand-offs add neither a frame nor a second registration.
local function WireEvents(S)
    local events = S.events
    if events then
        events:UnregisterAllEvents()
    else
        events = CreateFrame("Frame")
        S.events = events
    end
    for _, event in ipairs(CAST_EVENTS) do
        SafeRegisterUnitEvent(events, event, S.unit)
    end
    if S.isTarget then
        events:RegisterEvent("PLAYER_TARGET_CHANGED")
    end
    local registered, err = pcall(events.RegisterEvent, events, "PLAYER_ENTERING_WORLD")
    if not registered then ReportRegisterFailure("PLAYER_ENTERING_WORLD", err) end

    -- One closure per bar, built here: the step is pcall'd directly (no per-event closure the way
    -- TryStep would take one), and a failure is reported under the event's name like TryStep does.
    S.onEvent = S.onEvent or function(_, event, _, castID, _, interruptedBy)
        local stepOk, stepErr = pcall(HandleEvent, S, event, castID, interruptedBy)
        if not stepOk then print(DescribeCastBarStep(event) .. " failed: " .. tostring(stepErr)) end
    end
    events:SetScript("OnEvent", S.onEvent)
end

-- Re-places the stack when the scale or display changes (and at login and on entering the world).
local function WirePlacement()
    local watcher = CreateFrame("Frame")
    for _, event in ipairs({ "UI_SCALE_CHANGED", "DISPLAY_SIZE_CHANGED", "PLAYER_LOGIN", "PLAYER_ENTERING_WORLD" }) do
        watcher:RegisterEvent(event)
    end
    watcher:SetScript("OnEvent", function()
        pcall(PlaceAndRefit)
    end)
    -- A layout re-seat (an /fsedit drop or reset, a rescale) puts each bar back on its entry unsnapped;
    -- the snapped placement runs again from here.
    if FS.Layout and FS.Layout.OnRescale then
        FS.Layout.OnRescale(function() pcall(PlaceAndRefit) end)
    end
end

-- Registers the two bars with FS.Layout so /fsedit and the layout re-seat know them. Apply seats the bar
-- on its entry once (noSize keeps the fitted width); PlaceStack then snaps it.
local function RegisterLayout(player, target)
    if not (FS.Layout and type(FS.Layout.Apply) == "function") then return end
    for _, pair in ipairs({ { player, "pcast" }, { target, "tcast" } }) do
        local ok, err = pcall(FS.Layout.Apply, pair[1].frame, pair[2])
        if not ok then FS.LogDegradeOnce("castbar_layout_" .. pair[2], "cast bar layout entry failed: " .. tostring(err)) end
    end
end

-------------------------------------------------------------------------------
-- Idle row API (for the HUD display task)
-------------------------------------------------------------------------------

-- Both bars are hidden between casts unless the HUD turns the idle row on. FS.CastBars:
--   SetIdleHint(unit, text)  "player" or "target": the text the tab shows on the idle row (a
--                            plain string, shown in capitals; nil or "" clears it, and a bar
--                            with no hint has no tab on its idle row). Returns false for an
--                            unknown unit.
--   SetIdleVisible(visible)  true: every bar that is not casting, channelling or playing a verdict
--                            shows the engine's row of unlit chevrons (run:ShowIdle) with its hint
--                            on the tab, and returns to it after each cast; false (the default):
--                            the bar hides between casts. A bar mid-cast is left alone and takes
--                            the new setting when it ends.
local CastBarsAPI = {}

function CastBarsAPI.SetIdleHint(unit, text)
    local S = bars[unit]
    if not S then return false end
    if type(text) ~= "string" or IsSecret(text) or text == "" then text = nil end
    S.idleHint = text
    if idleVisible and S.mode == nil and not S.retired then ShowIdleRow(S) end
    return true
end

-- SetRestAlpha(alpha)      0 to 1, default 1 (no change from the plain look): the alpha of the idle
--                          row only (the HUD's out-of-combat dim). Never applied to a running cast,
--                          a verdict or a hidden bar. Returns false for a value that is not a plain
--                          number (nothing changes).
function CastBarsAPI.SetRestAlpha(alpha)
    if IsSecret(alpha) or type(alpha) ~= "number" or alpha ~= alpha then return false end
    restAlpha = math.max(0, math.min(1, alpha))
    for _, S in pairs(bars) do
        if S.mode == nil and idleVisible and not S.retired then ApplyRest(S) end
    end
    return true
end

function CastBarsAPI.SetIdleVisible(visible)
    idleVisible = visible and true or false
    for _, S in pairs(bars) do
        if S.mode == nil and not S.retired then
            if idleVisible then ShowIdleRow(S) else HideIdleRow(S) end
        end
    end
end

-- The view seam (see VIEW SEAM in the header). The members a view bar must bring.
local VIEW_FIELDS = { "frame", "run", "strip", "icon", "shield", "timer", "tab", "tabName", "tabTicks" }

local function ViewIsUsable(view)
    if type(view) ~= "table" or view.player == view.target then return false end
    for _, unit in ipairs({ "player", "target" }) do
        local S = view[unit]
        if type(S) ~= "table" then return false end
        for _, field in ipairs(VIEW_FIELDS) do
            if type(S[field]) ~= "table" then return false end
        end
    end
    return true
end

-- Stack A stops listening and drawing: events cleared, engine stopped, readout ended, frames
-- hidden. The tables stay (FS.playerCastBar / FS.targetCastBar, PlaceStack).
local function SilenceEvents(S)
    S.events:SetScript("OnEvent", nil)
    S.events:UnregisterAllEvents()      -- the frame is silent for good, not merely handler-less
end

local function RetireBar(S)
    S.retired = true
    SilenceEvents(S)
    ClearReadout(S)
    S.run:Stop()
    S.strip:Hide()
    S.frame:Hide()
    S.mode = nil
end

-- A view bar stands down: back to its resting look (readout ended, icon, shield and name cleared, strips
-- hidden, the engine on its idle row; the frame itself is the view's, never hidden here), then silent.
local function StandDownViewBar(S)
    GoIdle(S)
    SilenceEvents(S)
    S.retired = true
end

-- The readout ticker of a view bar: Show installs the OnUpdate and shows the frame, Hide clears
-- the script, so there is no OnUpdate at all between casts.
local function BuildViewTicker(S)
    local frame = CreateFrame("Frame", nil, S.frame)
    frame:Hide()
    local function onUpdate(_, elapsed) TickReadout(S, elapsed) end
    local ticker = { frame = frame }
    function ticker.Show()
        frame:SetScript("OnUpdate", onUpdate)
        frame:Show()
    end
    function ticker.Hide()
        frame:SetScript("OnUpdate", nil)
        frame:Hide()
    end
    return ticker
end

local activeView = nil

-- Hands the cast state machine to another display. True when the view was taken; false for an unusable
-- view or while a view is already active (ClearView first).
function CastBarsAPI.SetView(view)
    if activeView or not ViewIsUsable(view) then return false end
    activeView = view
    for _, unit in ipairs({ "player", "target" }) do
        local S = view[unit]
        S.unit, S.isTarget, S.mode, S.channeling = unit, unit == "target", nil, false
        S.retired = nil
        S.tickerElapsed = 0
        S.ticker = S.ticker or BuildViewTicker(S)
        S.run.onFinished = function() GoIdle(S) end
        if bars[unit] and not bars[unit].retired then RetireBar(bars[unit]) end
    end
    -- Wired once both Stack A bars are silent: only one display ever draws a cast.
    for _, unit in ipairs({ "player", "target" }) do
        local S = view[unit]
        WireEvents(S)
        TryStep(S, "refresh", ResetFromUnit)
    end
    return true
end

-- Takes the view back and gives the casts to Stack A. A cast in progress is re-read from the units, so
-- it shows on Stack A at once. False when no view is active.
function CastBarsAPI.ClearView()
    local view = activeView
    if not view then return false end
    activeView = nil
    for _, unit in ipairs({ "player", "target" }) do StandDownViewBar(view[unit]) end
    -- Wired once both view bars are silent: only one display ever draws a cast.
    for _, unit in ipairs({ "player", "target" }) do
        local S = bars[unit]
        if S then
            S.retired = false
            WireEvents(S)
            TryStep(S, "refresh", ResetFromUnit)
        end
    end
    return true
end

-- True while Stack A is the display (no view active): its frames are the ones that show casts.
function CastBarsAPI.IsStackActive()
    return activeView == nil
end

FS.CastBars = CastBarsAPI

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

-- Both cast bars are plain non-secure frames (no SecureUnitButtonTemplate, no protected
-- attributes), so building and styling them is safe in combat. Ours are built FIRST and
-- Blizzard's are dimmed only once both builds succeeded, so a build failure leaves the stock bars.
-- PlayerCastingBarFrame/TargetFrameSpellBar are themselves Edit Mode-registered cast bar
-- systems though, so DimBlizzardFrame (not HideBlizzardFrame) is used to silence them --
-- Hide()+HookScript would taint their secure Update path the same way it did
-- BuffFrame/DebuffFrame (see Buffs.lua/FrameHelpers.lua, CLAUDE.md 2026-09-25). No
-- PLAYER_REGEN_ENABLED defer is needed, unlike UnitFrames.lua Init.
local function Init()
    -- Ours first: Blizzard's bars are only silenced once both of ours are built, so a build failure
    -- leaves the stock bars up.
    local player = BuildBar("player", "ForeverSTUwavePlayerCastBar")
    local target = BuildBar("target", "ForeverSTUwaveTargetCastBar")
    bars.player, bars.target = player, target
    DimBlizzardFrame(PlayerCastingBarFrame)
    DimBlizzardFrame(TargetFrameSpellBar)
    -- pcall'd like every other caller: a throw here must not skip the event wiring below and leave
    -- Blizzard's bars dimmed with nothing of ours listening.
    RegisterLayout(player, target)
    local placed, placeErr = pcall(PlaceAndRefit)
    if not placed then
        FS.LogDegradeOnce("castbar_place", "cast bar placement failed at build: " .. tostring(placeErr))
    end

    WireEvents(player)
    WireEvents(target)
    WirePlacement()

    FS.playerCastBar, FS.targetCastBar = player, target

    TryStep(player, "refresh", ResetFromUnit)
    TryStep(target, "refresh", ResetFromUnit)
end

Init()
