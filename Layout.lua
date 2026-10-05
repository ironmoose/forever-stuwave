-- Forever Synthwave: Layout
-- FS.Layout: canonical screen anchors/sizes plus the UIParent-relative
-- Apply/Scale/OnRescale machinery every component seats itself with.
-- Split out of Theme.lua, which still owns chrome/tokens. Loads after
-- Theme.lua and before every component that consumes FS.Layout (see .toc).

local _, FS = ...

-------------------------------------------------------------------------------
-- Layout
-------------------------------------------------------------------------------

-- Canonical layout/anchors, baked from Parker's finalized planner export
-- (artifact 7nuxcfvA6WA1eg8bMqcsZq). Every entry anchors point="CENTER" of the
-- frame to relPoint="CENTER" of UIParent; x/y are the game-px offset from
-- UIParent's center to the element's own center at 2560x1440 (Y is +up), so
-- these offsets are resolution-independent across screen sizes. w/h are the
-- element size in game px at that resolution. Not every id below has a built
-- frame yet -- this is the complete canonical map, not what exists today.
FS.Layout = FS.Layout or {
    grid        = { point = "CENTER", relPoint = "CENTER", x = 2,     y = -625, w = 2560, h = 183 },
    player      = { point = "CENTER", relPoint = "CENTER", x = -1089, y = 643,  w = 320,  h = 92  },
    target      = { point = "CENTER", relPoint = "CENTER", x = -706,  y = 640,  w = 320,  h = 92  },
    tot         = { point = "CENTER", relPoint = "CENTER", x = -451,  y = 623,  w = 150,  h = 54  },
    focus       = { point = "CENTER", relPoint = "CENTER", x = -723,  y = -142, w = 190,  h = 66  },
    pet         = { point = "CENTER", relPoint = "CENTER", x = -448,  y = -361, w = 180,  h = 62  },
    party       = { point = "CENTER", relPoint = "CENTER", x = -389,  y = -75,  w = 231,  h = 294 },
    raid        = { point = "CENTER", relPoint = "CENTER", x = -1076, y = 25,   w = 360,  h = 190 },
    boss        = { point = "CENTER", relPoint = "CENTER", x = 728,   y = 152,  w = 210,  h = 210 },
    pcast       = { point = "CENTER", relPoint = "CENTER", x = 0,     y = -300, w = 340,  h = 30  },
    tcast       = { point = "CENTER", relPoint = "CENTER", x = 0,     y = -334, w = 270,  h = 26  },
    action      = { point = "CENTER", relPoint = "CENTER", x = -7,    y = -540, w = 1089, h = 178 },
    multibar    = { point = "CENTER", relPoint = "CENTER", x = 1253,  y = 97,   w = 50,   h = 320 },
    stance      = { point = "CENTER", relPoint = "CENTER", x = 0,     y = -427, w = 320,  h = 38  },
    petbar      = { point = "CENTER", relPoint = "CENTER", x = -380,  y = -428, w = 320,  h = 38  },
    -- The pet component's one panel (PetFrame.lua): supersedes the `pet`/`petbar`
    -- slots above for that purpose. `pet`/`petbar` stay in the table unremoved --
    -- a concurrent lane may still reference either -- this is a new entry, not a
    -- replacement of them. 348 x 68 is the approved console dock option C
    -- (mockups/gunsight-hud-v2-2026-10-02, PE_G.dc: 5 top inset + 26 top row + 3 +
    -- 30 buttons + 4 bottom pad, 6 on the sides; HP/mana left and the cast bar right
    -- over the 10 buttons); petframe-harness.py parses the size back out of the mockup.
    -- SEAT (2026-10-03): moved from (-380, -405) to (-363, -403) because the Console
    -- chassis (Console.lua) and its halo draw OUTSIDE the action rect and had grown into it.
    -- Bottom edge -444 is CONSOLE_PET_GAP (8) above the halo top (-452.2 at the live scale
    -- 0.8333, -452 at scale 1; the stack is centred on y -540 and shrank with the narrower
    -- Console buttons). The seat is CENTER anchored, so the bottom edge is y - h / 2: when
    -- option C cut the height from 82 to 68 the y moved from -403 to -410 to keep that edge
    -- at -444 (-410 - 34; the old -403 - 41). Left edge -537 is CHAT_CLEARANCE (12) right of
    -- the chat terminal's outer edge, glow included (CHAT_CHROME_RIGHT -549, constants
    -- below). x span -537..-189 clears the shoulder tab (x 85 and right) and sits 29 left of
    -- the stance bar (x -160..160); the panel has no glow of its own. petframe-harness.py
    -- checks both gaps and the -444.
    petcontainer = { point = "CENTER", relPoint = "CENTER", x = -363, y = -410, w = 348, h = 68  },
    -- The control deck (micro keys + bag slots, Deck.lua) replaced the old
    -- `micro` (774, -664, 320x32) and `bagbar` (1073, -652, 230x36) blocks. It
    -- is DELIBERATELY not a CENTER-anchored entry: it rests on the XP bar's top
    -- edge, and that bar's height changes with /fsxp, so Deck.lua anchors
    -- BOTTOMRIGHT to the XP bar's TOPRIGHT and reads only h and rightMargin
    -- from here (a fallback in Deck.lua keeps the same numbers if this entry is
    -- missing). w is the MAX width, not the live one: the micro slot follows the
    -- number of SHOWN micro keys (MicroBars.lua tells Deck.lua), so the deck
    -- shrinks leftward from this and never grows past it. w must equal the sum
    -- of the max parts Deck.lua builds from (12 + 314 + 28 + 206 + 12 = 572;
    -- the 314 is the nested 12 key micro row, see Deck.lua);
    -- `python3 addons/microbars-harness.py` checks it. No point/x/y on purpose,
    -- so FS.Layout.Apply would do nothing with it. rightMargin 92 puts the
    -- deck's right edge at 1188 of the 1280 half-width, where the old bag block
    -- ended (1073 + 230 / 2). Measured from the xpbar entry's top edge (y -675),
    -- its footprint is y -637..-675 and x 616..1188 at most; the live XP bar's
    -- own variant height (12 for most variants, 18 for spectrum) moves that
    -- edge, and the deck with it. The action stack ends at y -629 (x to 537),
    -- professions at y -555, so the only neighbour is the action stack, 8
    -- design px clear above it.
    deck        = { w = 572, h = 38, rightMargin = 92 },
    xpbar       = { point = "CENTER", relPoint = "CENTER", x = 0,     y = -683, w = 1000, h = 16  },
    -- x is DELIBERATELY left of the planner's export (802 / 842), and re-porting
    -- it "back" is a regression, not a fix -- that was tried on 2026-09-22 and
    -- put both blocks under the minimap. The export still assumes a 210-wide
    -- minimap; ours grew to 250 when it gained the CRT console, so its left
    -- edge moved from 1024 to 1011. At the exported x these blocks end at 1012
    -- and collide. At 773 / 808 they end at 983 / 978 and clear it.
    buffs       = { point = "CENTER", relPoint = "CENTER", x = 773,   y = 637,  w = 420,  h = 80  },
    debuffs     = { point = "CENTER", relPoint = "CENTER", x = 808,   y = 493,  w = 340,  h = 56  },
    -- x shifted from 1136 to 1126 (2026-09-25, Parker: "cut off on the right
    -- side"). At the design canvas's right edge (half-width 1280), the old
    -- x=1136 left the map's own right edge (1136 + 250/2 = 1261) only 19
    -- design px of margin -- and ApplyChrome's outer glow (GLOW_SIZE =
    -- max(4, m*0.038), m the map's ~250px scaled size, Minimap.lua) reaches
    -- that same ~19px past the map's edge, with zero buffer for float
    -- rounding, CompensateClusterInset's own measured correction, or a
    -- non-16:9 display. The new x buys a ~10px buffer (margin ~29px vs the
    -- glow's ~19px reach) without touching GLOW_SIZE itself, which is sized
    -- to match the mockup's glow:60 spec and would be a visual regression to
    -- shrink. minimaptray's x moves the same ~10px (1137 -> 1127) since it
    -- must stay flush under the map. Re-verified this does not collide with
    -- buffs/debuffs above: minimap's new left edge is 1126 - 125 = 1001;
    -- buffs (x=773, w=420) right edge is 773+210=983, clearance 18px;
    -- debuffs (x=808, w=340) right edge is 808+170=978, clearance 23px --
    -- both still comfortably positive (was 28px/33px before this shift).
    -- On-screen result UNVERIFIED -- cannot launch the client to check.
    -- Raise the whole console 9 design px. Its 126px half-height and ~9.5px
    -- outer glow then fit inside the canvas top at y=720; move the tray with
    -- the map so their seam stays flush. In-game position remains unverified.
    minimap     = { point = "CENTER", relPoint = "CENTER", x = 1126,  y = 584,  w = 250,  h = 252 },
    minimaptray = { point = "CENTER", relPoint = "CENTER", x = 1127,  y = 397,  w = 250,  h = 37  },
    databar     = { point = "CENTER", relPoint = "CENTER", x = 0,     y = -710, w = 2560, h = 20  },
    -- y raised from the planner's -493. Our terminal draws its chrome on a
    -- backdrop OUTSET below the chat frame (Chat.lua PAD_BOTTOM, which also
    -- houses the edit box), so the visible panel extends lower than the planner
    -- rect and was overlapping the XP and data bars. The offset is that padding
    -- plus a small gap, converted back to design px.
    chat        = { point = "CENTER", relPoint = "CENTER", x = -923,  y = -450, w = 677,  h = 373 },
    tracker     = { point = "CENTER", relPoint = "CENTER", x = 975,   y = 170,  w = 270,  h = 320 },
    -- Mirrors `chat` on the opposite side of the screen: same y, x negated.
    professions = { point = "CENTER", relPoint = "CENTER", x = 923,   y = -450, w = 300,  h = 210 },
}

-- Clearances the Console chassis and the pet panel keep from the chat terminal, in DESIGN
-- px (centre-relative x, like the entries above). The chat entry's own right edge is
-- -584.5, but the terminal draws OUTSIDE it: ChatCore's backdrop is outset PAD_X (10 UI
-- units) and SkinPanel's glow SLICE_GLOW_PAD (4) past that, which the code puts at about
-- -568 at the live UI scale. Measured on the live client 2026-10-03 (UIParent 1200 tall,
-- scale 0.8333, debug/gunsight-live-2026-10-03-full.png) the border sits at -554 and its
-- glow reaches about -549, so the measured edge is used: CHAT_CHROME_RIGHT is the
-- terminal's outermost right edge, glow included. THIS IS A SANITY FLOOR ONLY: the check
-- asserts it is never left of the edge the chat code implies (~-568), leaving about 19px
-- of unexplained code-implied width, so it only fires if the chat outset grows a lot. The
-- real guard is re-measuring from a live screenshot when the chat chrome changes.
-- CHAT_CLEARANCE is the gap Console.lua's halo (ActionBars narrows the stack to fit) and
-- PetFrame's panel keep from it. CONSOLE_PET_GAP is the gap between the Console's halo top
-- and the pet panel's bottom edge (the seat of the `petcontainer` entry above).
FS.Layout.CHAT_CHROME_RIGHT = -549
FS.Layout.CHAT_CLEARANCE = 12
FS.Layout.CONSOLE_PET_GAP = 8

-- The layout planner exports in SCREEN PIXELS at this resolution (the "resolution"
-- field of mockups/layout-v2.json). WoW frames are positioned in UI units, and
-- UIParent is only ever ~768 units tall no matter the monitor, so the exported
-- numbers are roughly 1.9x too large as-is.
--
-- Measured in game 2026-09-20: the grid frame, seated at the exported
-- CENTER (2,-625) with size 2560x183, reported left = -589 and bottom = -332 --
-- entirely off-screen, which is why it drew nothing at all. Working back from
-- those two numbers gives UIParent = 1377 x 768 units against a 2560 x 1440
-- design, i.e. a factor of 768/1440. Every component using FS.Layout was
-- mis-seated by that same factor, which is also why the action bars sat far
-- lower than the mockup.
FS.Layout.DESIGN_W = 2560
FS.Layout.DESIGN_H = 1440

-- Derived from UIParent's CURRENT height rather than a baked constant, so the
-- addon follows the player's UI Scale slider instead of assuming one setting.
function FS.Layout.Scale()
    local height = UIParent and UIParent:GetHeight()
    if not height or height <= 0 then return 1 end
    return height / FS.Layout.DESIGN_H
end

-- pcall that keeps the inner frames: returns ok, err where a string err carries
-- the stack at the throw site, so rethrowing it (error(err, 0)) still lands in
-- ForeverSynthwaveErrorLog with the frames that matter instead of just the
-- rethrow line. Callers use it to reset a flag and then rethrow.
--
-- The handler must never throw (it would replace the real error with "error in
-- error handling"): a secret message or stack would make the concat throw, so
-- both are checked first (issecretvalue is a global that may not exist, and
-- FS.IsSecret is not loaded yet at this point in the .toc; same guard as
-- ErrorLog.lua), and debugstack runs under pcall. When no stack can be had the
-- error goes out alone.
--
-- A rethrow (error(err, 0)) hands the same string to an outer CallTraced; it is
-- recognised through FS.Layout._recentTraced (the last RECENT_TRACED strings
-- handed out, a ring, so several errors alive in one pass each keep their one
-- stack) and passed on as is, so an error that crosses two of them carries ONE
-- stack, and its text (the dedupe key) is the same as with one.
local RECENT_TRACED = 4

function FS.Layout.CallTraced(fn)
    return xpcall(fn, function(err)
        local function secret(v)
            local isSecret = _G.issecretvalue
            if type(isSecret) ~= "function" then return false end
            local ok, r = pcall(isSecret, v)
            return not ok or r ~= false
        end
        if type(err) ~= "string" or secret(err) then return err end
        local recent = FS.Layout._recentTraced
        if not recent then
            recent = {}
            FS.Layout._recentTraced = recent
        end
        for i = 1, #recent do
            if recent[i] == err then return err end
        end
        local stack
        if type(debugstack) == "function" then
            -- Level 3: pcall is level 1, this handler 2, the throw site 3.
            local ok, text = pcall(debugstack, 3)
            if ok and type(text) == "string" and not secret(text) then stack = text end
        elseif debug and debug.traceback then
            stack = debug.traceback("", 2)
        end
        if not stack then return err end
        local traced = err .. "\n" .. stack
        local slot = (FS.Layout._recentTracedNext or 0) % RECENT_TRACED + 1
        FS.Layout._recentTracedNext = slot
        recent[slot] = traced
        return traced
    end)
end

-- Applies a saved layout entry to `frame`, clearing any prior anchor first.
-- Nil-safe: does nothing if `frame` or the `id` entry is missing. Returns the
-- layout entry so callers can read w/h to size children.
--
-- Returns the entry with its ORIGINAL design values, plus scaled w/h under
-- `scaledW`/`scaledH`: callers that lay out children (the action bars solve
-- their button size from w) need to know which space they are working in.
function FS.Layout.Apply(frame, id, parent)
    local L = FS.Layout[id]
    if not frame or not L then return end

    local scale = FS.Layout.Scale()

    -- Edit Mode system frames (ChatFrame1) replace ClearAllPoints/SetPoint with
    -- overrides that write EditModeManagerFrame's anchor-dirty flag, which our
    -- insecure call would leave tainted. They keep the originals as
    -- ClearAllPointsBase/SetPointBase; use those when present, plain calls
    -- otherwise. `applying` tells the chat seat log this move is ours.
    local clear = frame.ClearAllPointsBase or frame.ClearAllPoints
    local set = frame.SetPointBase or frame.SetPoint
    FS.Layout.applying = true
    local ok, err = FS.Layout.CallTraced(function()
        clear(frame)
        set(frame, L.point, parent or UIParent, L.relPoint, L.x * scale, L.y * scale)
        if L.w and L.h and frame.SetSize then
            frame:SetSize(L.w * scale, L.h * scale)
        end
    end)
    FS.Layout.applying = false
    if not ok then error(err, 0) end

    L.scaledW = L.w and (L.w * scale) or nil
    L.scaledH = L.h and (L.h * scale) or nil

    -- Remember it so the watcher below can re-seat it once UIParent settles.
    FS.Layout._applied[frame] = { id = id, parent = parent }
    return L
end

-- UIParent is NOT fully sized while addons are loading. Measured on this client
-- 2026-09-20: at file scope it reports 768 tall (scale -> 0.533) and by
-- PLAYER_LOGIN it reports 1200 (scale -> 0.833). Anything seated during load
-- therefore lands at ~64% of its intended size and position, which is why the
-- grid covered only part of the screen and the bars sat small and low.
--
-- Rather than make every component remember to defer, re-seat everything that
-- has ever been through Apply once UIParent is real -- and again whenever the
-- player changes UI Scale or resolution, which has the same effect.
FS.Layout._applied = FS.Layout._applied or {}

-- Components that size CHILDREN from the layout (the action bars solve their
-- button edge from the stack width) need to rebuild, not just move, so they
-- can register a callback here.
FS.Layout._rescaleCallbacks = FS.Layout._rescaleCallbacks or {}

function FS.Layout.OnRescale(fn)
    FS.Layout._rescaleCallbacks[#FS.Layout._rescaleCallbacks + 1] = fn
end

-- A protected frame (a secure button, or anything that holds or is anchored to one,
-- like the stance container) refuses ClearAllPoints/SetPoint/SetSize in combat and
-- raises ADDON_ACTION_BLOCKED, so a rescale that lands mid-fight must leave it alone
-- and re-seat it when combat ends. Frames that are not protected are seated at once.
-- IsProtected can itself throw on an odd frame, in which case it counts as protected
-- (holding one back is only a delay; touching one is a blocked action).
local function IsHeldInCombat(frame)
    if not InCombatLockdown() then return false end
    if not frame.IsProtected then return false end
    local ok, protected = pcall(frame.IsProtected, frame)
    return not ok or protected and true or false
end

local deferredRescale = false

local function RunRescaleCallbacks()
    for _, fn in ipairs(FS.Layout._rescaleCallbacks) do
        pcall(fn)
    end
end

local layoutWatcher = CreateFrame("Frame")
layoutWatcher:RegisterEvent("PLAYER_LOGIN")
layoutWatcher:RegisterEvent("UI_SCALE_CHANGED")
layoutWatcher:RegisterEvent("DISPLAY_SIZE_CHANGED")
layoutWatcher:RegisterEvent("PLAYER_REGEN_ENABLED")
layoutWatcher:SetScript("OnEvent", function(_, event)
    if event == "PLAYER_REGEN_ENABLED" and not deferredRescale then return end
    local deferred = false
    for frame, info in pairs(FS.Layout._applied) do
        if frame and frame.SetPoint then
            if IsHeldInCombat(frame) then
                deferred = true
            else
                FS.Layout.Apply(frame, info.id, info.parent)
            end
        end
    end
    deferredRescale = deferred
    -- Callbacks run on the rescale itself (so unprotected components rebuild at once)
    -- and again once the held frames are seated, so a component that sizes children
    -- from the layout sees their final position; each callback guards its own combat
    -- work (the action bars and the stance bar both defer to PLAYER_REGEN_ENABLED).
    RunRescaleCallbacks()
end)

-------------------------------------------------------------------------------
-- Edit Mode re-seat
--
-- Every Edit Mode system frame we seat through Apply (ChatFrame1, MinimapCluster)
-- is parked at TOPLEFT 0,0 and re-anchored by EditModeManagerFrame:UpdateLayoutInfo,
-- which the server triggers (EDIT_MODE_LAYOUTS_UPDATED) AFTER login on a character's
-- first login, i.e. after the PLAYER_LOGIN pass above. So re-seat them from a
-- post-hook on UpdateLayoutInfo, which runs after every system applied (seating
-- from inside a system's own ApplySystemAnchor would land before its settings
-- loop; see ChatWindowState.lua). Apply uses the Base anchor calls, so this
-- writes nothing under our taint and cannot retrigger Edit Mode. An Edit Mode
-- frame is recognised by the SetPointBase Edit Mode stores on it.
--
-- A module that re-seats its own frame with more logic (the chat, which has a
-- minimised/maximised state) opts out with SkipEditModeReseat.
-------------------------------------------------------------------------------

local editModeSkip = setmetatable({}, { __mode = "k" })

function FS.Layout.SkipEditModeReseat(frame)
    if frame then editModeSkip[frame] = true end
end

-- Hands an error to the client's error handler without ever throwing (the whole
-- lookup-and-call is under pcall, as in ErrorLog.lua). For post-hooks on
-- Blizzard functions, which must not throw into Blizzard's caller (it may unwind
-- the rest of Blizzard's own function; see ReseatFromHook). The nil test is a
-- truth test INSIDE the pcall: an error value may be secret, and comparing a
-- secret with == is illegal.
function FS.Layout.ForwardError(err)
    pcall(function()
        if not err then return end
        local handler = geterrorhandler()
        if type(handler) == "function" then handler(err) end
    end)
end

local function ReseatEditModeFrames()
    -- `failed` is a plain flag: the error itself may be secret and is never compared.
    local any, failed, firstErr = false, false, nil
    for frame, info in pairs(FS.Layout._applied) do
        -- One frame's throw (the field lookups included) must not skip the
        -- frames after it or the callbacks below; the first error is RETURNED
        -- for the caller to report (the hook forwards it to the error handler,
        -- the event path rethrows it).
        local ok, err = FS.Layout.CallTraced(function()
            if frame and frame.SetPointBase and not editModeSkip[frame] then
                any = true
                if IsHeldInCombat(frame) then
                    -- Seated by the PLAYER_REGEN_ENABLED pass above.
                    deferredRescale = true
                else
                    FS.Layout.Apply(frame, info.id, info.parent)
                end
            end
        end)
        if not ok and not failed then failed, firstErr = true, err end
    end
    -- Components that size children from the frame (the minimap's inset
    -- compensation) rebuild after the move, as after a rescale.
    if any then RunRescaleCallbacks() end
    return failed, firstErr
end

local editModeHooked = false
-- Set by the post-hook, cleared by the event watcher: tells the watcher whether
-- UpdateLayoutInfo's post-hook already re-seated for this event. A hook run that
-- came from somewhere else than the event leaves it set until the next event, so
-- if that event's UpdateLayoutInfo then throws before the hook, the re-seat is
-- missed; accepted, the hook has just re-seated anyway.
local hookRanSinceEvent = false

-- The post-hook runs inside Blizzard's own call chain: a throw here may unwind
-- into EditModeManager (whose later steps are UpdateTopFramePositions,
-- NotifyChatOfLayoutChange, ManageFramePositions, ...; whether the engine
-- contains a hook's error cannot be confirmed from the UI source), so the hook
-- never throws: anything ReseatEditModeFrames returns OR throws (its per-frame
-- isolation does not cover iterating _applied or the callbacks' loop) goes to
-- the error handler instead.
local function ReseatFromHook()
    hookRanSinceEvent = true
    -- (true, failed, firstErr) normally, (false, thrown error) if it escaped.
    local ok, failed, err = FS.Layout.CallTraced(ReseatEditModeFrames)
    if not ok then failed, err = true, failed end
    if failed then FS.Layout.ForwardError(err) end
end

local function HookUpdateLayoutInfo()
    if editModeHooked or type(hooksecurefunc) ~= "function" then return end
    if not (EditModeManagerFrame and type(EditModeManagerFrame.UpdateLayoutInfo) == "function") then return end
    editModeHooked = true
    hooksecurefunc(EditModeManagerFrame, "UpdateLayoutInfo", ReseatFromHook)
end
HookUpdateLayoutInfo()

-- The event is the fallback for a client where the post-hook could not be
-- installed, or where UpdateLayoutInfo threw before the hook ran: Blizzard's own
-- OnEvent runs first (it registered first) and calls UpdateLayoutInfo, so when
-- the hook already re-seated for this event (hookRanSinceEvent) the handler
-- stands down instead of re-seating and running every callback twice. The
-- ADDON_LOADED retry covers a client that loads Blizzard_EditMode after us.
local editModeWatcher = CreateFrame("Frame")
editModeWatcher:RegisterEvent("EDIT_MODE_LAYOUTS_UPDATED")
if not editModeHooked then editModeWatcher:RegisterEvent("ADDON_LOADED") end
editModeWatcher:SetScript("OnEvent", function(self, event, addon)
    if event == "ADDON_LOADED" then
        if addon == "Blizzard_EditMode" then
            HookUpdateLayoutInfo()
            self:UnregisterEvent("ADDON_LOADED")
        end
    elseif editModeHooked and hookRanSinceEvent then
        hookRanSinceEvent = false
    else
        -- Event site: nothing of Blizzard's follows our handler, so rethrow.
        local failed, err = ReseatEditModeFrames()
        if failed then error(err, 0) end
    end
end)
