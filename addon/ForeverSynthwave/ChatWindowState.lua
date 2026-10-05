-- Forever Synthwave: ChatWindowState
-- Split out of the original Chat.lua (2026-09-23): seating the primary chat
-- window at its layout anchor, and the minimise/maximise/restore state
-- machine (ApplyWindowState/ToggleWindowState) that drives it and the term
-- bar lamps. Reads/writes the shared FS.Chat state table; see ChatCore.lua's
-- header for why cross-module names live there instead of as locals.

local _, FS = ...
local Chat = FS.Chat

-- How close the maximised panel's top edge comes to the top of the screen.
local MAX_TOP_MARGIN = 24
-- Frame level the maximised panel sits at within its strata. High enough to
-- clear addons that park at HIGH with a default level, low enough to leave
-- headroom above it.
local MAX_FRAME_LEVEL = 200

-------------------------------------------------------------------------------
-- Primary chat layout seat
-------------------------------------------------------------------------------

-- Ring buffer of every seat and every move of ChatFrame1 we did not make, in
-- ForeverSynthwaveDB.chatSeatLog (the previous session's copy is kept in
-- chatSeatLogPrev, so a reload right after the bug does not erase it). /fsbug
-- reports both in their own `chatSeat` section. The first SEAT_LOG_PIN entries
-- of a session are pinned and only the tail rolls, because the login sequence
-- is the evidence and a later burst of moves must not push it out. Read-only:
-- logging never moves anything.
local SEAT_LOG_MAX = 20
local SEAT_LOG_PIN = 10

-- True while the maximise branch below is the one calling SetPoint on
-- ChatFrame1, so the SetPoint hook does not log our own move as foreign.
-- (FS.Layout.applying is the same flag for Layout.Apply.)
Chat.seating = false

-- pcall that keeps the inner stack frames (FS.Layout.CallTraced), plain pcall
-- if Layout.lua is somehow absent.
local function Traced(fn)
    if FS.Layout and FS.Layout.CallTraced then return FS.Layout.CallTraced(fn) end
    return pcall(fn)
end

local function LogSeat(ev, frame)
    local db = ForeverSynthwaveDB
    if type(db) ~= "table" then return end
    local log = db.chatSeatLog
    if type(log) ~= "table" then
        log = {}
        db.chatSeatLog = log
    end

    local entry = { ev = ev, t = GetTime() }
    if UIParent and UIParent.GetHeight then entry.ui = UIParent:GetHeight() end
    if frame and frame.GetPoint then
        local ok, point, _, _, x, y = pcall(frame.GetPoint, frame, 1)
        if ok then
            entry.pt = point
            entry.x = x and math.floor(x * 10 + 0.5) / 10
            entry.y = y and math.floor(y * 10 + 0.5) / 10
        end
    end

    -- The same move repeated (Blizzard sets a point several times in a row)
    -- counts up instead of taking a slot.
    local last = log[#log]
    if last and last.ev == ev and last.pt == entry.pt and last.x == entry.x and last.y == entry.y then
        last.n = (last.n or 1) + 1
        return
    end

    log[#log + 1] = entry
    while #log > SEAT_LOG_MAX do table.remove(log, SEAT_LOG_PIN + 1) end
end

-- Seats the docked primary window (ChatFrame1 only) at the canonical
-- FS.Layout "chat" anchor. No-ops if FS.Layout hasn't loaded or lacks Apply.
-- `why` only labels the chatSeatLog entry.
function Chat.SeatPrimaryChat(frame, why)
    if not frame then return end
    if not FS.Layout or type(FS.Layout.Apply) ~= "function" then return end
    FS.Layout.Apply(frame, "chat")
    LogSeat(why or "seat", frame)
end

-- ChatFrame1 is an Edit Mode system frame. EDIT_MODE_LAYOUTS_UPDATED runs
-- EditModeManagerFrame:UpdateLayoutInfo (Blizzard_EditMode/Shared/
-- EditModeManager.lua), which parks every system at TOPLEFT UIParent 0,0
-- (InitSystemAnchors) and then runs each system's UpdateSystem: ApplySystemAnchor,
-- the settings SetSize, and RefreshSystemPosition -> OnSystemPositionChange, which
-- reads GetPoint(1) back into the layout's anchorInfo. The server sends that
-- event after login, so on a character's FIRST login it lands after our seat and
-- puts the chat back at the Edit Mode layout's spot; on a /reload the client
-- already has the layout, so it applies before us and the seat sticks.
--
-- So the re-seat runs from a post-hook on UpdateLayoutInfo, after every system
-- applied. (FS.Layout re-seats the OTHER Edit Mode frames the same way and skips
-- this one, which has the window state to honour.) Seating from
-- the ApplySystemAnchor hook instead would land mid-UpdateSystem, before the
-- settings loop: our size would be overwritten and OnSystemPositionChange would
-- store OUR seat as the layout's anchor, which a later Edit Mode save persists.
-- That hook is log-only plus a deferred re-seat for paths that call
-- ApplySystemAnchor without UpdateLayoutInfo (Reset to default position).
local reasserting = false
local reassertPending = false
local deferPending = false

-- Same rule as Layout.lua's IsHeldInCombat: a protected frame refuses SetPoint
-- in combat. ChatFrame1 normally is not protected, so this is a guard only.
local function HeldInCombat(frame)
    if not InCombatLockdown() then return false end
    if not frame.IsProtected then return false end
    local ok, protected = pcall(frame.IsProtected, frame)
    return not ok or protected and true or false
end

-- Puts ChatFrame1 back at our seat after Blizzard moved it. Idempotent, and
-- guarded so nothing our own seat triggers can re-enter it.
function Chat.ReassertPrimaryChat()
    local frame = ChatFrame1
    if not frame or reasserting then return end
    deferPending = false
    if HeldInCombat(frame) then
        reassertPending = true
        return
    end
    reassertPending = false

    reasserting = true
    local ok, err = Traced(function()
        Chat.SeatPrimaryChat(frame, "reseat")
        -- min/max derive more than the anchor (hidden frame, grown height), so
        -- they go back through the one function that owns that geometry.
        if Chat.windowState ~= "normal" then Chat.ApplyWindowState() end
    end)
    reasserting = false
    if not ok then error(err, 0) end
end

-- One re-seat a frame from now, however many Blizzard calls ask for it.
local function DeferReassert()
    if deferPending then return end
    if not (C_Timer and type(C_Timer.After) == "function") then return end
    deferPending = true
    C_Timer.After(0, function()
        if deferPending then Chat.ReassertPrimaryChat() end
    end)
end

local primaryHooked = false
local editModeHooked = false

local function HookUpdateLayoutInfo()
    if editModeHooked or type(hooksecurefunc) ~= "function" then return end
    if not (EditModeManagerFrame and type(EditModeManagerFrame.UpdateLayoutInfo) == "function") then return end
    editModeHooked = true
    -- A post-hook on a Blizzard function must not throw into Blizzard's caller
    -- (it may unwind the rest of UpdateLayoutInfo's callers), so a failed seat is
    -- forwarded to the error handler instead; the event paths below may rethrow.
    hooksecurefunc(EditModeManagerFrame, "UpdateLayoutInfo", function()
        local ok, err = Traced(function()
            LogSeat("UpdateLayoutInfo", ChatFrame1)
            Chat.ReassertPrimaryChat()
        end)
        if ok then return end
        if FS.Layout and FS.Layout.ForwardError then
            FS.Layout.ForwardError(err)
        else
            error(err, 0)   -- no Layout.lua: the old behaviour, never silent
        end
    end)
end

-- Installs the re-seat. Call before the first SeatPrimaryChat so the log starts
-- at our own first seat. Every Blizzard name is feature-detected.
function Chat.HookPrimaryChatReseat()
    if primaryHooked or not ChatFrame1 then return end
    primaryHooked = true
    if FS.Layout and FS.Layout.SkipEditModeReseat then FS.Layout.SkipEditModeReseat(ChatFrame1) end

    ForeverSynthwaveDB = ForeverSynthwaveDB or {}
    ForeverSynthwaveDB.chatSeatLogPrev = ForeverSynthwaveDB.chatSeatLog
    ForeverSynthwaveDB.chatSeatLog = {}

    if type(hooksecurefunc) == "function" then
        if type(ChatFrame1.ApplySystemAnchor) == "function" then
            hooksecurefunc(ChatFrame1, "ApplySystemAnchor", function(self)
                LogSeat("ApplySystemAnchor", self)
                DeferReassert()
            end)
        end
        if type(ChatFrame1.SetPoint) == "function" then
            hooksecurefunc(ChatFrame1, "SetPoint", function(self)
                if Chat.seating or FS.Layout and FS.Layout.applying or reasserting then return end
                LogSeat("SetPoint", self)
            end)
        end
    end
    HookUpdateLayoutInfo()

    local watcher = CreateFrame("Frame")
    watcher:RegisterEvent("EDIT_MODE_LAYOUTS_UPDATED")
    watcher:RegisterEvent("PLAYER_ENTERING_WORLD")
    watcher:RegisterEvent("PLAYER_REGEN_ENABLED")
    if not editModeHooked then watcher:RegisterEvent("ADDON_LOADED") end
    -- Logged only: they show whether FCF's window setup or a rescale lands
    -- before or after us. (Layout.lua re-seats on the two scale events.)
    watcher:RegisterEvent("UPDATE_CHAT_WINDOWS")
    watcher:RegisterEvent("UPDATE_FLOATING_CHAT_WINDOWS")
    watcher:RegisterEvent("UI_SCALE_CHANGED")
    watcher:RegisterEvent("DISPLAY_SIZE_CHANGED")
    watcher:SetScript("OnEvent", function(self, event, arg1, arg2)
        if event == "PLAYER_REGEN_ENABLED" then
            if reassertPending then Chat.ReassertPrimaryChat() end
        elseif event == "ADDON_LOADED" then
            if arg1 == "Blizzard_EditMode" then
                HookUpdateLayoutInfo()
                self:UnregisterEvent("ADDON_LOADED")
            end
        elseif event == "PLAYER_ENTERING_WORLD" then
            -- Zone changes fire this too; only a login or reload needs the re-seat.
            if arg1 or arg2 then
                LogSeat(event, ChatFrame1)
                Chat.ReassertPrimaryChat()
            end
        elseif event == "EDIT_MODE_LAYOUTS_UPDATED" then
            LogSeat(event, ChatFrame1)
            Chat.ReassertPrimaryChat()
        else
            LogSeat(event, ChatFrame1)
        end
    end)
end

-- Minimise / maximise / restore.
--
-- All three go through ONE function that re-derives the whole geometry from
-- `windowState`, rather than each button nudging the panel from wherever it
-- happens to be. Toggling min -> max -> normal in any order then lands in the
-- same place every time, and there is no "restore" path to keep in sync with
-- the two that changed things.
--
-- Restoring calls SeatPrimaryChat rather than replaying a saved rect: the
-- layout already owns where the chat belongs, so asking it again is both
-- shorter and correct after a UI rescale, which a captured rect would not be.
function Chat.ApplyWindowState()
    local frame = ChatFrame1
    if not frame then return end

    if Chat.windowState == "min" then
        -- The chat itself goes; the term bar is all that is left, and it is
        -- parented to UIParent rather than to the chat frame, so it survives.
        frame:Hide()
    else
        frame:Show()

        Chat.SeatPrimaryChat(frame)

        if Chat.windowState == "max" then
            -- Grow UPWARD to near the top of the screen. The chat frame is
            -- anchored by its top, so SetHeight alone grows it DOWNWARD over
            -- the action bars -- measured: adding 6 moved the bottom down by
            -- 6 and left the top where it was. Pinning the bottom first is
            -- what makes the growth go the other way.
            -- SCALE CONVERSION, and leaving it out is what made the bottom
            -- drop instead of staying put. GetBottom/GetLeft report in the
            -- FRAME's own coordinate space; an offset passed to SetPoint is
            -- read in the ANCHOR's. The chat frame does not share UIParent's
            -- effective scale, so feeding one straight into the other moved
            -- the bottom edge from 69.6 down to 32.0 -- the panel grew in both
            -- directions and buried the action bars.
            local fs = frame:GetEffectiveScale()
            local us = UIParent:GetEffectiveScale()
            local toUI = (us > 0) and (fs / us) or 1
            local toFrame = (fs > 0) and (us / fs) or 1

            local bottom, left = frame:GetBottom(), frame:GetLeft()
            local screenTop = UIParent:GetTop()
            if bottom and left and screenTop then
                -- Everything below is in FRAME space except the SetPoint
                -- offsets, which are converted on the way out.
                local height = (screenTop * toFrame) - bottom
                    - Chat.PAD_TOP - MAX_TOP_MARGIN
                if height > frame:GetHeight() then
                    -- The Edit Mode Base originals when present: see the note in
                    -- FS.Layout.Apply. Reset the flag even if a call throws.
                    local clear = frame.ClearAllPointsBase or frame.ClearAllPoints
                    local set = frame.SetPointBase or frame.SetPoint
                    Chat.seating = true
                    local ok, err = Traced(function()
                        clear(frame)
                        set(frame, "BOTTOMLEFT", UIParent, "BOTTOMLEFT",
                            left * toUI, bottom * toUI)
                        frame:SetHeight(height)
                    end)
                    Chat.seating = false
                    if not ok then error(err, 0) end
                end
            end
        end
    end

    -- Maximised, the panel goes OVER everything -- and this is now ONE call,
    -- which is the whole point of the chat terminal container. Parker:
    -- "wouldn't it be easier if like the whole chat panel was its own group
    -- and you just changed the strata of the container group and all the stuff
    -- inside stayed."
    --
    -- It was previously four assignments (chat frame, backdrop, chrome, title
    -- buttons) because the pieces lived under three different parents, and a
    -- frame that has had its own strata set ignores its parent's -- so each
    -- one had to be found and moved, and anything missed stayed behind. Inside
    -- the container nothing sets its own strata, so they all follow this.
    --
    -- HIGH, not DIALOG: DIALOG and up is where static popups, tooltips and the
    -- tab context menu live, and burying a logout confirmation under the chat
    -- is worse than the bug being fixed. Clearing other HIGH frames is the
    -- container's frame level's job.
    local maximised = (Chat.windowState == "max")
    Chat.termPanel:SetFrameStrata(maximised and "HIGH" or "LOW")
    Chat.termPanel:SetFrameLevel(maximised and MAX_FRAME_LEVEL or 1)

    -- Min-state visibility for the tab strip, edit box and prompt host lives
    -- inside SeatTerminalChrome now, not here: ApplyDockState has other
    -- callers besides this one, and a rule that only ran after this specific
    -- call left the strip shown again on a reload into "min" once any of
    -- those other callers ran.
    Chat.ApplyDockState()

    -- Maximise glyph reads as "restore down" while maximised, flipped back
    -- the rest of the time. SetRotation is feature-detected: this client is
    -- interface 16001 and a nil method call throws, which would take the
    -- whole file down with it.
    if Chat.maximiseButton and Chat.maximiseButton.icon and Chat.maximiseButton.icon.SetRotation then
        Chat.maximiseButton.icon:SetRotation(maximised and math.pi or 0)
    end

    -- A click on one of these buttons changes windowState without OnEnter
    -- firing again, so a tooltip already open on it would otherwise keep
    -- showing the stale label until the mouse leaves and returns.
    if GameTooltip and GameTooltip.GetOwner and GameTooltip.SetText then
        local owner = GameTooltip:GetOwner()
        if owner == Chat.minimiseButton or owner == Chat.maximiseButton then
            local text = Chat.ResolveTermBarTooltip(owner.tooltip)
            local c = owner.color
            if text and c then
                GameTooltip:SetText(text, c[1], c[2], c[3])
                Chat.PlaceTermBarTooltip(owner)
            end
        end
    end

    if ForeverSynthwaveDB then ForeverSynthwaveDB.chatWindowState = Chat.windowState end
end

-- Clicking a lamp toggles its own state OFF back to normal, which is what a
-- window control does everywhere else: the minimise button on a minimised
-- window restores it.
function Chat.ToggleWindowState(target)
    Chat.windowState = (Chat.windowState == target) and "normal" or target
    Chat.ApplyWindowState()
end
