-- Forever Synthwave: Issue Reporter placement
--
-- The beta client's PTR feedback widget re-seats itself at a fixed default on
-- every reload, which meant dragging it out of that spot every single time.
--
-- Cause, from Blizzard_PTRFeedback_Frames.lua (CreateMainView) on the `forever`
-- branch: `PTR_IssueReporter` is a global frame whose OWN OnShow handler
-- re-seats it, and the branch it takes when its saved coordinates are missing
-- is horizontally centred, a quarter of the screen height up --
--
--     PTR_IssueReporter:SetPoint("BOTTOM", UIParent, "BOTTOM",
--                                0, UIParent:GetHeight()*0.25)
--
-- It writes Blizzard_PTRIssueReporter_Saved.x/y on OnDragStop, so the drag is
-- meant to persist; on this client it evidently does not survive a reload, and
-- the fallback runs instead.
--
-- Rather than guess coordinates, this records where Parker actually drags it
-- and re-applies that. He positions it once more and it stays.
--
-- THE FIRST ATTEMPT FAILED, and why is the interesting part. It used
-- HookScript("OnShow", ...) as its backstop. But CreateMainView does
-- `PTR_IssueReporter:SetScript("OnShow", SetFrameLocation)`, and SetScript
-- REPLACES the whole handler chain -- HookScript hooks included. The frame is
-- created at file scope, so we find it and hook it early, and then their
-- view-building silently deletes our hook. Parker's drag survived exactly until
-- the next reload, every time.
--
-- So the mechanisms now are:
--   1. hooksecurefunc on the frame's SHOW METHOD. A method hook cannot be wiped
--      by SetScript, and it runs after Show() completes -- their OnShow
--      included -- so our placement lands last.
--   2. Write Blizzard's OWN saved table, so SetFrameLocation agrees with us
--      rather than fighting.
--   3. A settle pass 2s after install, because CreateMainView schedules a
--      C_Timer.After(1) reminder that can re-place the frame behind us.
--   4. HookScript("OnShow") kept as well -- it costs nothing and covers a Show
--      that never fires because the frame was already visible.
--
-- ForeverSynthwaveIssueReporterDiag records which of these actually fired, so
-- if it STILL drifts the next round is measured instead of guessed at.
--
-- Nothing here touches the widget's behaviour -- it stays draggable, and a new
-- drag simply records a new position.

local addonName, _ = ...

-- Per-character SavedVariable, declared in the .toc. Blizzard's own table is
-- written too, but ours is the one that is actually trusted to come back.
-- Captured BEFORE we touch the global, so the log can say whether the client
-- had already restored last session's table by the time this file ran. The
-- three probes (file scope / ADDON_LOADED / PLAYER_LOGIN) bracket every moment
-- the value could go missing, which is the only way to tell "never restored"
-- from "restored then clobbered".
local xAtFileScope = type(ForeverSynthwaveIssueReporterPos) == "table"
    and tostring(ForeverSynthwaveIssueReporterPos.x) or "NO-TABLE"

-- Declared up here, not next to the event frame that fills it: Install()
-- references it and is defined above that point, so a later `local` would make
-- Install capture the nil GLOBAL of this name instead. Same trap that bit
-- ReseatBags in MicroBars.lua.
local xAtAddonLoaded = "not-seen"

-- ACCOUNT-WIDE store, run alongside the per-character one as a controlled
-- experiment. Everything points at the per-character variables being written
-- and then ignored on load -- the file on disk is small, valid Lua 5.1, and
-- literally contains `boot = 1`, yet every login reports boot #1 with the
-- table absent at file scope. Whether that is specific to
-- SavedVariablesPerCharacter is the one thing not yet tested, and the two
-- declarations cost nothing to run side by side.
--
-- If ForeverSynthwaveDB survives a reload and the per-character table does
-- not, the fix is simply to keep the position here.
ForeverSynthwaveDB = ForeverSynthwaveDB or {}
local dbAtFileScope = type(ForeverSynthwaveDB.issueReporterX) == "number"
    and tostring(ForeverSynthwaveDB.issueReporterX) or "nil"

ForeverSynthwaveIssueReporterPos = ForeverSynthwaveIssueReporterPos or {}

-- Fallback, used ALWAYS in practice, not just until the first drag: the
-- Forever beta client never restores SavedVariables on load (confirmed via
-- the boot-counter probe above; design notes), so `saved.x/saved.y` below
-- can never survive a reload and this branch is the one that actually seats
-- the frame every single time. A dragged position simply cannot persist
-- until that client bug is fixed.
--
-- Hardwired to the spot Parker dragged the frame to and had captured live
-- (2026-09-24): PTR_IssueReporter:GetRect() read left=1527.1, bottom=165.1
-- against UIParent 2132.95x1200 (scale 0.64) -- clear of the bags and the
-- tooltip that the old bottom-right default collided with. Expressed as a
-- fraction of UIParent's size rather than fixed pixels, so it reproduces
-- that same spot at any resolution/scale.
local IR_DEFAULT_XFRAC = 0.716
local IR_DEFAULT_YFRAC = 0.138

local hooked = false

-- Diagnostics, so the NEXT round is measured rather than guessed at. Written to
-- SavedVariables and readable off disk after a reload.
ForeverSynthwaveIssueReporterDiag = ForeverSynthwaveIssueReporterDiag or {}

local function Note(line)
    local diag = ForeverSynthwaveIssueReporterDiag
    diag[#diag + 1] = ("%s  %s"):format(date("%H:%M:%S"), line)
    -- Bounded: this must never become the memory problem it is diagnosing.
    while #diag > 40 do table.remove(diag, 1) end
end

local function Seat(why)
    local frame = PTR_IssueReporter
    if not (frame and frame.SetPoint and frame.ClearAllPoints) then return end

    local saved = ForeverSynthwaveIssueReporterPos
    frame:ClearAllPoints()

    -- ForeverSynthwaveDB is the account-wide store and the ONLY one that
    -- survives a reload on this client; see the .toc for the measurement. The
    -- per-character table is still written for the current session's
    -- convenience, but it is never what comes back.
    if not (saved.x and saved.y)
        and type(ForeverSynthwaveDB.issueReporterX) == "number" then
        saved.x = ForeverSynthwaveDB.issueReporterX
        saved.y = ForeverSynthwaveDB.issueReporterY
    end

    if saved.x and saved.y then
        -- GetRect returns the frame's bottom-left in UI units, which is what
        -- Blizzard's own OnDragStop records, so the two agree.
        frame:SetPoint("BOTTOMLEFT", UIParent, "BOTTOMLEFT", saved.x, saved.y)
    else
        frame:SetPoint("BOTTOMLEFT", UIParent, "BOTTOMLEFT",
            IR_DEFAULT_XFRAC * UIParent:GetWidth(), IR_DEFAULT_YFRAC * UIParent:GetHeight())
    end

    if why then
        -- Log what the frame ACTUALLY ended up at, not just what we asked for.
        -- The drag is captured and persisted correctly now, so the remaining
        -- fault is in APPLYING it -- and the two numbers disagreeing is the
        -- only way to see that from off-machine.
        --
        -- The prime suspect is SetClampedToScreen, which Blizzard's AddDrag
        -- turns on: if our coordinates push any part of the frame past an edge,
        -- the client slides it back and our position is quietly discarded. That
        -- would happen if GetRect's numbers and SetPoint-against-UIParent are
        -- not in the same coordinate space -- different effective scales.
        local left, bottom = 0, 0
        if frame.GetRect then left, bottom = frame:GetRect() end
        Note(("seat(%s) want x=%s y=%s -> got x=%.1f y=%.1f | UIP %.0fx%.0f scale %.3f/%.3f clamp=%s")
            :format(why, tostring(saved.x), tostring(saved.y),
                left or -1, bottom or -1,
                UIParent:GetWidth() or 0, UIParent:GetHeight() or 0,
                UIParent:GetEffectiveScale() or 0,
                frame:GetEffectiveScale() or 0,
                tostring(frame.IsClampedToScreen and frame:IsClampedToScreen())))
    end
end

-- Mirrors our stored position into Blizzard's table so its own placement code
-- agrees with ours instead of fighting it.
local function PushToBlizzard()
    local saved = ForeverSynthwaveIssueReporterPos
    if not (saved.x and saved.y) then return end
    if type(Blizzard_PTRIssueReporter_Saved) ~= "table" then return end
    Blizzard_PTRIssueReporter_Saved.x = saved.x
    Blizzard_PTRIssueReporter_Saved.y = saved.y
end

local function Remember(frame)
    if not (frame and frame.GetRect) then return end
    local left, bottom = frame:GetRect()
    if not (left and bottom) then return end
    -- Both capture paths can fire for one drag; storing the same numbers twice
    -- is harmless, but the log line is not worth duplicating.
    local saved = ForeverSynthwaveIssueReporterPos
    if saved.x == left and saved.y == bottom then return end
    ForeverSynthwaveIssueReporterPos.x = left
    ForeverSynthwaveIssueReporterPos.y = bottom
    ForeverSynthwaveDB.issueReporterX = left
    ForeverSynthwaveDB.issueReporterY = bottom
    PushToBlizzard()
    Note(("drag stored x=%.1f y=%.1f"):format(left, bottom))
end

local function Install()
    local frame = PTR_IssueReporter
    if not frame or hooked then return end
    if not frame.HookScript then return end

    -- hooksecurefunc on the frame's SHOW METHOD, not HookScript("OnShow").
    --
    -- That distinction is the whole bug. Blizzard's CreateMainView does
    -- `PTR_IssueReporter:SetScript("OnShow", SetFrameLocation)`, and SetScript
    -- REPLACES the entire handler chain -- including any HookScript hooks
    -- already attached. The frame is created at file scope, so we find it and
    -- hook it early, and then their view-building silently deletes our hook.
    -- That is why Parker's drag survived until the next reload and no further.
    --
    -- A method hook cannot be wiped by SetScript, and it runs AFTER Show()
    -- completes -- which includes their OnShow handler -- so our placement is
    -- applied last either way.
    pcall(hooksecurefunc, frame, "Show", function() Seat("show") end)

    -- Kept as well: it costs nothing and covers a Show that never happens
    -- because the frame was already visible.
    frame:HookScript("OnShow", function() Seat("onshow") end)

    -- The DRAG is captured the same way, and for the same reason. The first
    -- version used HookScript("OnDragStop", ...) and the diagnostic log proved
    -- it never fired even once:
    --
    --     ForeverSynthwaveIssueReporterPos = { }
    --     "seat(install) -> x=nil y=nil"        -- and no "drag stored" line
    --
    -- CreateMainView calls AddDrag (which SetScripts OnDragStop) and then
    -- SetScripts OnDragStop AGAIN itself, so a hook attached before either of
    -- those is simply gone. Both of those handlers end by calling
    -- self:StopMovingOrSizing(), which is a METHOD -- so hooking that catches
    -- the end of every drag no matter how many times the script is replaced.
    pcall(hooksecurefunc, frame, "StopMovingOrSizing", function(self)
        Remember(self)
    end)

    -- Kept as a second path in case a future build drops the
    -- StopMovingOrSizing call.
    frame:HookScript("OnDragStop", Remember)

    hooked = true

    -- Decisive persistence test. If this reads "boot #1" on every login, the
    -- table is not surviving a reload at all and no amount of hooking the drag
    -- will ever help -- which is the difference between "we failed to capture
    -- the position" (ruled out: the capture works) and "we captured it and the
    -- client threw it away".
    local saved = ForeverSynthwaveIssueReporterPos
    saved.boot = (saved.boot or 0) + 1
    ForeverSynthwaveDB.boot = (ForeverSynthwaveDB.boot or 0) + 1
    Note(("perChar boot #%d (fileScope=%s addonLoaded=%s) | account boot #%d (fileScope x=%s)")
        :format(saved.boot, xAtFileScope, tostring(xAtAddonLoaded),
                ForeverSynthwaveDB.boot, dbAtFileScope))

    PushToBlizzard()
    Seat("install")

    -- Blizzard's own CreateMainView runs a C_Timer.After(1, ...) reminder that
    -- can re-place the frame after we have seated it, so re-assert once the
    -- dust has settled rather than racing it.
    if C_Timer and C_Timer.After then
        C_Timer.After(2, function() Seat("settle") end)
    end

    Note(("installed; blizzSaved=%s"):format(
        type(Blizzard_PTRIssueReporter_Saved) == "table"
            and tostring(Blizzard_PTRIssueReporter_Saved.x) or "nil"))
end

local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:RegisterEvent("ADDON_LOADED")
events:RegisterEvent("PLAYER_ENTERING_WORLD")
events:SetScript("OnEvent", function(_, event, loadedAddon)
    -- Blizzard_PTRFeedback can load after us, so this waits for it rather than
    -- assuming PTR_IssueReporter exists at our own login.
    if event == "ADDON_LOADED" then
        -- Our OWN ADDON_LOADED is the moment the client is documented to have
        -- injected saved globals. If x is nil here but present in the file on
        -- disk, the restore is simply not happening for this addon.
        if loadedAddon == addonName then
            xAtAddonLoaded = type(ForeverSynthwaveIssueReporterPos) == "table"
                and tostring(ForeverSynthwaveIssueReporterPos.x) or "NO-TABLE"
        end
        if loadedAddon ~= "Blizzard_PTRFeedback" then return end
    end
    Install()
    if hooked and event == "PLAYER_ENTERING_WORLD" then Seat("entering") end
end)
