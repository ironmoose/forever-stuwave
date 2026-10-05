-- Forever STUwave: Error log
--
-- Captures Lua errors to SavedVariables so they can be read off disk instead of
-- transcribed out of screenshots of the error frame. Added 2026-09-20 after a
-- debugging round where every iteration cost a screenshot, a retype and a guess
-- -- the error frame truncates long stacks, and the interesting frame is
-- usually the one that got cut.
--
-- Loads FIRST in the .toc (before Theme.lua and every component) so it is
-- already installed when the rest of the addon runs and can catch load-time
-- errors from our own files.
--
-- Reading it: /reload or log out (SavedVariables only flush then), then read
--   WTF/Account/<id>/SavedVariables/forever-stuwave.lua
--
-- Slash commands: /fserr        summarise what has been captured
--                 /fserr clear  wipe the log

local addonName, FS = ...

-- Declared in the .toc as an account-wide SavedVariable (## SavedVariables, not
-- SavedVariablesPerCharacter, which this client never restores). Intentionally
-- global: that is the only way the client persists it.
--
-- Reset per session rather than accumulated. SavedVariables are written when
-- the UI unloads, so the file always holds exactly the session that just
-- ended -- which is what a dev loop wants. Carrying entries forward instead
-- made a stale error from an older build sit at the top of the file and look
-- like a live one, which cost two debugging rounds.
--
-- The wipe MUST happen in ADDON_LOADED, not here in the main chunk. The client
-- executes an addon's Lua files FIRST and only then injects the saved globals
-- over the top, so a main-chunk assignment is silently overwritten by the
-- restored table -- which is exactly what kept resurrecting the stale entry.
ForeverSTUwaveErrorLog = ForeverSTUwaveErrorLog or {}

-- A single bad update path can throw every frame, so cap the stored count and
-- deduplicate by message. Without this a 60fps error would fill the file with
-- thousands of identical entries and push out the first (most useful) one.
local MAX_ENTRIES = 80
-- Other addons' errors are kept too (they were always logged here), but capped
-- separately so a noisy neighbour cannot fill the log and bury ours.
local MAX_FOREIGN = 30
local byMessage = {}
local foreignStored = 0

-- Entries recorded before ADDON_LOADED. The client restores the saved table
-- OVER the global after our files have run, so anything logged while loading
-- (the errors a tester most needs) lives in a table that is about to be
-- discarded. They are kept here and put back in ADDON_LOADED.
local preLoad = {}
local loaded = false

local PREFIX = "|cff22e0ffForever STUwave|r"
local CHAT_INTERVAL = 10

local function Secret(v)
    local fn = _G.issecretvalue
    if type(fn) ~= "function" then return false end
    local ok, r = pcall(fn, v)
    if not ok then return true end
    return r ~= false
end

-- The raw debugstack text, or nil when it cannot be had or cannot be trusted. Level 1 is pcall (the
-- direct caller of debugstack), then whoever called pcall, then up through this file's handler
-- frames to the frame that raised the error, so the innermost real frames come first once our own
-- are skipped. A secret result is never read.
local function RawStack()
    local ok, text = pcall(debugstack, 1, 24, 0)
    if not ok or type(text) ~= "string" or Secret(text) then return nil end
    return text
end

-- The stack with our own handler frames removed, so a stack that only passes through this file is
-- not mistaken for one that touches the addon. Builds a table and a string, so it runs only when an
-- entry is actually stored (see Record), never per throw.
local function FilterStack(raw)
    if not raw then return nil end
    local kept = {}
    for line in raw:gmatch("[^\n]+") do
        if not line:find("ErrorLog.lua", 1, true) then kept[#kept + 1] = line end
    end
    return table.concat(kept, "\n")
end

local function FirstFrame(raw)
    if not raw then return "" end
    for line in raw:gmatch("[^\n]+") do
        if not line:find("ErrorLog.lua", 1, true) then return line end
    end
    return ""
end

-- How many of the innermost real frames may carry our name for a foreign looking error to count as
-- ours. Any frame anywhere in the stack is too loose: a foreign hook that runs nested under a
-- Blizzard call we made has our frame deep below it, and swallowing that error hides somebody else's
-- bug. Six covers Blizzard code we called (a chain of its own helper frames, then ours). The stack
-- only decides for a message that does not name another addon (see NamesOtherAddon), which is what
-- keeps the wider window from swallowing a foreign hook's error.
local INNERMOST = 6

-- Case-insensitive form of a literal, as a Lua pattern, built once at load: the client's path casing
-- is not guaranteed, and lowercasing every message instead would allocate a string per throw of a
-- noisy addon.
local function CI(s)
    return (s:gsub("%a", function(c) return "[" .. c:lower() .. c:upper() .. "]" end):gsub("[^%w%[%]]", "%%%0"))
end

-- Anchored on the separator or quote BEFORE our folder name, not on `AddOns/`: the client cuts a long
-- chunk path to `...` plus its last ~52 characters (`...ddOns/<us>/LongName.lua:12:`), and a string
-- chunk is `[string "<us>/X.lua"]`. The trailing separator keeps a `<us>X/` lookalike out.
local OWN_PATH = "[/\\\"]" .. CI(addonName) .. "[/\\]"
local OWN_BARE = "^" .. CI(addonName) .. "[/\\]"
local OWN_TAINT = "'" .. CI(addonName) .. "'"
local OTHER_FOLDER = CI("AddOns") .. "[/\\][^/\\]+[/\\]"
local TAINT_OPEN = CI("tainted by") .. " '"
local BLIZZARD_PREFIX = "^" .. CI("Blizzard_")

-- True when the message names OUR addon in an anchored form: a path inside our folder
-- (`/<us>/`, `\<us>\` or `"<us>/`, so a client-truncated `...ddOns/<us>/` and `[string "<us>/X.lua"]`
-- count too), a bare chunk name at the start (`<us>/File.lua`) or a taint
-- report naming us (`tainted by '<us>'`, `AddOn '<us>'`). A bare substring is not enough: another
-- addon whose folder starts with our name, or a foreign message that only mentions our global
-- (`ForeverSTUwaveDB`), would be swallowed as ours.
local function NamesUs(err)
    return err:find(OWN_PATH) ~= nil or err:find(OWN_BARE) ~= nil or err:find(OWN_TAINT) ~= nil
end

-- True when the message itself names an addon that is not ours: a path inside another addon's
-- folder (`AddOns/<other>/` or `AddOns\<other>\`) or a taint report (`tainted by '<other>'`), matched
-- case-insensitively. Blizzard's own folders (`Blizzard_*`) are not another addon: Blizzard code we
-- called is exactly what the stack check exists for. Position arithmetic only, no strings or tables
-- built: this runs on every throw of a noisy addon. Our own name is handled before this (Classify).
local function NamesOtherAddon(err)
    local pos = 1
    while true do
        local s, e = err:find(OTHER_FOLDER, pos)
        if not s then break end
        if not err:find(BLIZZARD_PREFIX, s + 7) then return true end
        pos = e + 1
    end
    pos = 1
    while true do
        local _, e = err:find(TAINT_OPEN, pos)
        if not e then break end
        if not err:find(BLIZZARD_PREFIX, e + 1) then return true end
        pos = e + 1
    end
    return false
end

-- True when one of the first INNERMOST non-[C], non-ErrorLog frames names our addon. Walks the text
-- with find() positions and builds no strings or tables: it can run on every throw of a noisy addon.
local function OursByStack(raw)
    local pos, len, seen = 1, #raw, 0
    while pos <= len and seen < INNERMOST do
        local eol = raw:find("\n", pos, true) or (len + 1)
        if eol > pos and not raw:find("^%[C%]", pos) then
            local own = raw:find("ErrorLog.lua", pos, true)
            if not (own and own < eol) then
                seen = seen + 1
                -- Anchored to our folder, like NamesUs: a bare substring would count a
                -- `ForeverSTUwaveX` frame. A frame may also start with the bare chunk name
                -- (`<us>/File.lua`); OWN_BARE is `^`-anchored, so with `pos` it matches only here.
                local hit = raw:find(OWN_PATH, pos)
                if (hit and hit < eol) or raw:find(OWN_BARE, pos) then return true end
            end
        end
        pos = eol + 1
    end
    return false
end

local function Combat()
    local fn = _G.InCombatLockdown
    if type(fn) ~= "function" then return false end
    local ok, r = pcall(fn)
    return ok and r == true
end

local function Stamp() return date("%Y-%m-%d %H:%M:%S") end

-- Returns the entry, or nil when it was a repeat or could not be stored. A second result of true
-- means an error of ours was dropped because the log is full.
local function Record(err, stackOverride, ours, plainKey)
    err = tostring(err or "")

    -- A Lua runtime message embeds file:line, which already pins the site. A
    -- bare message (error("boom", 0), a library's own text) does not, so those
    -- also key on the first stack line; the stack is only built for them.
    -- `stack` is the RAW debugstack text (or nil); it is filtered only when stored.
    local key = err
    local stack = stackOverride
    if not plainKey and not err:find(":%d+:") then
        -- Somebody else's bare message that cannot be stored anyway (log full, or the foreign cap
        -- reached): do not build a key for it. Only its repeat count is lost.
        if not ours and (#ForeverSTUwaveErrorLog >= MAX_ENTRIES or foreignStored >= MAX_FOREIGN) then
            return nil
        end
        stack = stack or RawStack()
        key = err .. "\n" .. FirstFrame(stack)
    end

    local existing = byMessage[key]
    if existing then
        existing.count = existing.count + 1
        -- lastSeen at most once a second. date() builds a fresh string every
        -- call, and a bad update path throws at frame rate -- Parker's combat
        -- pull produced 89 throws, each one allocating a timestamp nobody
        -- reads, on top of whatever the error itself allocated. Cheap to fix
        -- and the log is no less useful to the second.
        local now = GetTime and GetTime() or 0
        if now - (existing.lastStampAt or 0) >= 1 then
            existing.lastStampAt = now
            existing.lastSeen = Stamp()
        end
        return nil
    end

    if #ForeverSTUwaveErrorLog >= MAX_ENTRIES then return nil, ours and true or false end
    if not ours then
        if foreignStored >= MAX_FOREIGN then return nil end
        foreignStored = foreignStored + 1
    end

    local entry = {
        message = err,
        stack = FilterStack(stack or RawStack()) or "(stack unavailable)",
        firstSeen = Stamp(),
        lastSeen = Stamp(),
        time = time(),
        count = 1,
        combat = Combat(),
        ours = ours and true or false,
        key = key,
    }

    byMessage[key] = entry
    ForeverSTUwaveErrorLog[#ForeverSTUwaveErrorLog + 1] = entry
    if not loaded then preLoad[#preLoad + 1] = entry end
    return entry
end

-- One chat line per ~10 seconds however hard an error loops, with a count of
-- everything it stands for. print() is the cheap path; this never builds a
-- string except when it actually speaks.
local lastChatAt, lastFullAt
local pending = 0
local function Announce(text)
    local ok, now = pcall(GetTime)
    if not ok or type(now) ~= "number" then now = 0 end
    if text then
        -- The "log full" line has its own throttle and its own (absent) count: sharing the standard
        -- one let a standard line silence it, and dropped errors inflated the next (xN).
        if lastFullAt and now - lastFullAt < CHAT_INTERVAL then return end
        lastFullAt = now
        print(PREFIX .. text)
        return
    end
    pending = pending + 1
    if lastChatAt and now - lastChatAt < CHAT_INTERVAL then return end
    lastChatAt = now
    local n = pending
    pending = 0
    local line = PREFIX .. ": error was thrown and logged (/fsbug to report)"
    if n > 1 then line = line .. " (x" .. n .. ")" end
    print(line)
end

-- Verdict cache: message -> true, ONLY for POSITIONED messages (file:line in the text) that the
-- stack proved to be ours. A looping error of ours would otherwise pay for a debugstack on every
-- throw. A "not ours" verdict is never cached, and neither is anything decided without a stack: the
-- same Blizzard message can be thrown on a foreign path and then on one of ours, and a cached false
-- would hide the second. A bare message is never cached either: its text says nothing about where
-- it was thrown.
local verdicts = {}
local verdictCount = 0
local VERDICT_CAP = 100

-- Returns ours, rawStack. `rawStack` is only set when it had to be built to decide.
--   * our name in the message (a path inside the addon, or a taint report naming it): ours;
--   * another addon's folder or taint report in the message: foreign, no stack needed;
--   * otherwise the innermost INNERMOST real stack frames decide (see OursByStack). That runs even
--     with the log full: an error of ours must never reach the popup path just because nothing can
--     be stored (Handle counts it as dropped and says so).
local function Classify(err)
    if NamesUs(err) then return true end
    -- Known narrow gap: a cached true outlives the stack that proved it, so the identical positioned
    -- message thrown later from a foreign path is still read as ours until the cache is wiped.
    if verdicts[err] then return true end
    if NamesOtherAddon(err) then return false end
    local stack = RawStack()
    local ours = stack ~= nil and OursByStack(stack)
    if ours and err:find(":%d+:") then
        if verdictCount >= VERDICT_CAP then
            wipe(verdicts)
            verdictCount = 0
        end
        verdicts[err] = true
        verdictCount = verdictCount + 1
    end
    return ours, stack
end

-- Returns true when the error was ours and has been logged. Never throws.
local function Handle(err)
    if type(err) ~= "string" then
        if Secret(err) then return false end
        local ok, text = pcall(tostring, err)
        if not ok then return false end
        err = text
    elseif Secret(err) then
        return false
    end

    local ours, stack = Classify(err)
    local ok, _, dropped = pcall(Record, err, stack, ours)
    if ours then
        if ok then
            if dropped then
                FS.ErrorLogDropped = (FS.ErrorLogDropped or 0) + 1
                pcall(Announce, ": error log full, /fserr clear")
            else
                pcall(Announce)
            end
        end
        return ok
    end
    return false
end

-- Both calls are pcall'd: if a client build ever restricts or removes the error handler API the
-- addon still loads, it just stops capturing (and /fserr shows an empty log).
local okPrev, previousHandler = pcall(geterrorhandler)
if not okPrev then previousHandler = nil end
-- The handler that was installed when this file loaded: Blizzard's, or an error addon that loads
-- before us (!BugGrabber normally does). Never replaced, so a later re-wrap cannot orphan it.
local baseHandler = previousHandler
local wrapper
local busy = false
local inBase = false

-- Our own errors are logged and NOT forwarded: the previous handler is what
-- raises the Blizzard error popup, and the point is to not interrupt play.
-- Everything else goes to it untouched. ForeverSTUwaveDB.errorPassthrough
-- forwards ours as well, for when the popup is wanted back.
--
-- `busy` cuts a handler cycle: an error addon that wraps whatever handler is
-- current when it loads can end up with us as its previous while it is ours,
-- and without this one throw would recurse forever.
-- On re-entry the error has already been through Handle once (a foreign one is what got forwarded
-- here), so nothing is logged again. But swallowing it would orphan the base handler whenever the
-- re-install wrapped an addon that chains back into us (we are its previous AND it is ours), so
-- anything that is not ours is handed straight to the base handler. `inBase` cuts the cycle if the
-- base handler itself ever leads back here.
local function ForwardOnReentry(err)
    -- The outer call already handed this error to the previous handler, and that handler is the one
    -- that chained back into us: forwarding again would deliver it twice.
    if baseHandler == previousHandler then return end
    if type(err) == "string" and not Secret(err) and NamesUs(err) then
        local db = _G.ForeverSTUwaveDB
        if not (type(db) == "table" and db.errorPassthrough == true) then return end
    end
    inBase = true
    local ok, r = pcall(baseHandler, err)
    inBase = false
    if ok then return r end
end

wrapper = function(err)
    if busy then
        if inBase or not baseHandler or baseHandler == wrapper then return end
        local ok, r = pcall(ForwardOnReentry, err)
        inBase = false
        if ok then return r end
        return
    end
    busy = true
    local okHandle, handled = pcall(Handle, err)
    local forward = not (okHandle and handled)
    if not forward then
        local db = _G.ForeverSTUwaveDB
        forward = type(db) == "table" and db.errorPassthrough == true
    end
    local result
    if forward and previousHandler then
        local ok, r = pcall(previousHandler, err)
        if ok then result = r end
    end
    busy = false
    return result
end

pcall(seterrorhandler, wrapper)

-- BugGrabber / BugSack or another error addon may install its handler after
-- ours. Re-check once at login and once shortly after: if the current handler
-- is not ours, wrap it (it becomes the previous one) so we still see errors and
-- it still sees everything we do not swallow. Only ever twice, never a loop.
local function EnsureInstalled()
    local ok, current = pcall(geterrorhandler)
    if ok and current ~= wrapper and type(current) == "function" then
        previousHandler = current
        pcall(seterrorhandler, wrapper)
    end
end

local installFrame = CreateFrame("Frame")
installFrame:RegisterEvent("PLAYER_LOGIN")
installFrame:SetScript("OnEvent", function(self)
    self:UnregisterEvent("PLAYER_LOGIN")
    pcall(EnsureInstalled)
    if C_Timer and C_Timer.After then C_Timer.After(5, function() pcall(EnsureInstalled) end) end
end)

-------------------------------------------------------------------------------
-- Blocked protected-action capture
-------------------------------------------------------------------------------

-- The "ForeverSTUwave has been blocked from an action only available to the
-- Blizzard UI" popup (ADDON_ACTION_FORBIDDEN) and the one-shot chat line for
-- ADDON_ACTION_BLOCKED are not Lua errors, so the error handler above never
-- sees them and nothing recorded WHICH protected function was blocked. The
-- client fires both events with the offending addon name and function name, so
-- log those through the same Record path (same dedupe by message, same 80 cap,
-- same lastSeen throttle) and announce them with the same throttled chat line.
--
-- Blizzard's own forbidden popup is raised by the client itself and is not
-- something an addon can suppress without touching protected state, so it is
-- left alone; this only makes sure the cause is written down.
--
-- Only our own addon is recorded: every other addon's blocked actions fire the
-- same events and would bury ours. A secret argument is ignored rather than
-- compared. The message carries only the function name so repeats of
-- the same block dedupe into one counted entry. The short stack goes in the
-- entry's stack field instead: it can sometimes show the tainting caller, and
-- is bounded (12 frames) and pcall'd because it is diagnostic only and this
-- handler must never throw into the client's event dispatch.
local function OnActionBlocked(event, blockedAddon, blockedFunc)
    if Secret(blockedAddon) or Secret(blockedFunc) then return end
    if blockedAddon ~= addonName then return end
    local msg = event .. ": " .. tostring(blockedFunc)
    -- A repeat (or a full log) never uses a stack, so skip building one.
    if byMessage[msg] or #ForeverSTUwaveErrorLog >= MAX_ENTRIES then
        Record(msg, nil, true, true)
    else
        local ok, s = pcall(debugstack, 2, 12, 0)
        -- Always pass a string: a nil would make Record fall back to its own
        -- stack call. A secret result is never read.
        if not ok or type(s) ~= "string" or Secret(s) then s = "(stack unavailable)" end
        Record(msg, s, true, true)
    end
    pcall(Announce)
end

local blockedFrame = CreateFrame("Frame")
-- Feature-detected: RegisterEvent errors on an event name the client does not
-- know, and a failure here must not stop the rest of the addon loading.
pcall(blockedFrame.RegisterEvent, blockedFrame, "ADDON_ACTION_BLOCKED")
pcall(blockedFrame.RegisterEvent, blockedFrame, "ADDON_ACTION_FORBIDDEN")
blockedFrame:SetScript("OnEvent", function(_, event, blockedAddon, blockedFunc)
    pcall(OnActionBlocked, event, blockedAddon, blockedFunc)
end)

-------------------------------------------------------------------------------
-- Shared warn-once-and-persist helper
-------------------------------------------------------------------------------

-- Several modules print a warning exactly once per session when they degrade
-- gracefully instead of erroring (a missing API, an unexpected region count, a
-- missing export). That chat line scrolls away and is gone -- same problem
-- Diagnostics.lua's /fsfont solved for font-load failures by also writing to
-- ForeverSTUwaveDB, which survives past the chat frame and can be read off
-- disk after a /reload. This is that same fix, shared, so every degrade site
-- routes its existing chat print through one place instead of duplicating the
-- SavedVariables plumbing per call site.
--
-- Callers keep their OWN once-per-session guard exactly as before (a boolean
-- upvalue, checked before ever calling this) -- this function does not decide
-- whether to print, only how the print is also persisted. `key` identifies the
-- degrade site (stable across calls, e.g. "nilslicemargins"); calling this
-- more than once for the same key just overwrites that key's record, so it is
-- safe to call every time the caller's own guard lets it through.
function FS.LogDegradeOnce(key, msg)
    if DEFAULT_CHAT_FRAME and DEFAULT_CHAT_FRAME.AddMessage then
        DEFAULT_CHAT_FRAME:AddMessage(msg)
    else
        print(msg)
    end

    -- Same guard style as Diagnostics.lua's /fsfont and every other
    -- ForeverSTUwaveDB writer in this addon: create the table if this is the
    -- first write of the session rather than requiring some other file to have
    -- done it first.
    ForeverSTUwaveDB = ForeverSTUwaveDB or {}
    ForeverSTUwaveDB.degradeLog = ForeverSTUwaveDB.degradeLog or {}
    ForeverSTUwaveDB.degradeLog[key] = { msg = msg, time = time() }
end

SLASH_FSERR1 = "/fserr"
SlashCmdList["FSERR"] = function(msg)
    msg = (msg or ""):lower():gsub("%s", "")

    if msg == "clear" then
        wipe(ForeverSTUwaveErrorLog)
        wipe(byMessage)
        wipe(preLoad)
        foreignStored = 0
        FS.ErrorLogDropped = 0
        print("|cff22e0ffForever STUwave|r: error log cleared.")
        return
    end

    local total = #ForeverSTUwaveErrorLog
    if total == 0 then
        print("|cff22e0ffForever STUwave|r: no errors captured.")
        return
    end

    print(("|cff22e0ffForever STUwave|r: %d distinct error(s) captured."):format(total))
    if (FS.ErrorLogDropped or 0) > 0 then
        print(("|cff22e0ffForever STUwave|r: log full, %d error(s) of ours not stored. /fserr clear."):format(FS.ErrorLogDropped))
    end
    for i = 1, math.min(total, 5) do
        local entry = ForeverSTUwaveErrorLog[i]
        print(("  %d) x%d  %s"):format(i, entry.count, entry.message))
    end
    print("|cff22e0ffForever STUwave|r: /reload to flush them to SavedVariables.")
end

-------------------------------------------------------------------------------
-- Guarded reload
-------------------------------------------------------------------------------

-- /fsreload -- reload, but only when it is safe to steal the keyboard.
--
-- Parker's idea ("we should make a macro for your check so you are not typing
-- it every time"). fsdev.py drives reloads by typing into the chat box, and
-- the guarded form of that was a long /run one-liner -- noisy, and close to
-- the chat box's 255-character limit. This is nine characters.
--
-- The guard exists because a reload opens the chat box and captures the
-- keyboard. Firing one mid-fight cost Parker his only healing potion; firing
-- one mid-run is its own problem. The client is the only thing that actually
-- knows, so the client decides.
--
-- fsdev.py falls back to the inline /run if this command is missing, which
-- matters: if the addon ever fails to load, this would not exist, and without
-- that fallback there would be no way to reload in order to FIX it.
SLASH_FSRELOAD1 = "/fsreload"
SlashCmdList["FSRELOAD"] = function()
    if InCombatLockdown() then
        print("|cff22e0ffForever STUwave|r: reload refused -- in combat.")
        return
    end

    if type(GetUnitSpeed) ~= "function" then
        print("|cff22e0ffForever STUwave|r: reload refused -- can't verify movement, refusing to be safe.")
        return
    end

    local speed = GetUnitSpeed("player")
    if speed > 0 then
        print("|cff22e0ffForever STUwave|r: reload refused -- moving.")
        return
    end

    ReloadUI()
end

-------------------------------------------------------------------------------
-- Memory diagnostic
-------------------------------------------------------------------------------

-- Parker watched FS MEM climb and asked whether we are leaking. The data bar
-- cannot answer that on its own: GetAddOnMemoryUsage reports memory ATTRIBUTED
-- to the addon that has not been collected yet, so it climbs for every addon
-- between garbage collections and drops when one runs. A rising number is
-- ordinary churn until proven otherwise.
--
-- What separates churn from a leak is the RETAINED figure -- what survives a
-- full collection. This command forces one and reports both, plus the change
-- since the last time it was run, so two calls a few minutes apart settle it:
--   retained flat, live climbing  -> churn, look at allocation rate
--   retained climbing             -> a real leak, something is being held
--
-- collectgarbage("collect") stalls a frame, which is why this is a manual
-- command and not something the data bar does on a timer.
local lastRetained, lastAt

SLASH_FSMEM1 = "/fsmem"
SlashCmdList["FSMEM"] = function()
    if not (UpdateAddOnMemoryUsage and GetAddOnMemoryUsage) then
        print("|cff22e0ffForever STUwave|r: memory APIs unavailable on this client.")
        return
    end

    UpdateAddOnMemoryUsage()
    local live = GetAddOnMemoryUsage(addonName) or 0
    local heapLive = collectgarbage("count")

    collectgarbage("collect")
    UpdateAddOnMemoryUsage()
    local retained = GetAddOnMemoryUsage(addonName) or 0
    local heapRetained = collectgarbage("count")

    print(("|cff22e0ffForever STUwave|r: live %.0fK -> retained %.0fK after GC (UI heap %.0fK -> %.0fK)")
        :format(live, retained, heapLive, heapRetained))

    local now = GetTime and GetTime() or 0
    if lastRetained then
        local delta = retained - lastRetained
        local minutes = (now - lastAt) / 60
        print(("  retained change since last check: %+.0fK over %.1f min (%+.0fK/min)")
            :format(delta, minutes, minutes > 0 and delta / minutes or 0))
        print("  flat retained = churn, not a leak. Climbing retained = a real leak.")
    else
        print("  baseline recorded -- run /fsmem again in a few minutes to see the trend.")
    end

    lastRetained, lastAt = retained, now

    ForeverSTUwaveMemDiag = ForeverSTUwaveMemDiag or {}
    ForeverSTUwaveMemDiag[#ForeverSTUwaveMemDiag + 1] = {
        at = date("%Y-%m-%d %H:%M:%S"),
        live = live,
        retained = retained,
        heapLive = heapLive,
        heapRetained = heapRetained,
    }
end

-------------------------------------------------------------------------------
-- Secure-snippet probe
-------------------------------------------------------------------------------

-- Settles, with observable evidence rather than inference, whether this client
-- can compile a NEW restricted closure at addon-load time.
--
-- Why this exists: RegisterStateDriver on our action bars fails inside
-- BuildRestrictedClosure (RestrictedExecution.lua:79, which calls
-- loadstring_untainted). Reading `type(loadstring_untainted)` from /run proves
-- nothing, because that runs in the tainted environment after the global may
-- have been captured into a local and removed from _G. And a bare Execute()
-- proves nothing either, because SecureHandlerExecute only queues the body via
-- an attribute -- the print fires whether or not the snippet ever ran.
--
-- So: run a snippet whose ONLY job is to leave a value behind, then read that
-- value back. If it comes back, snippets compile. If not, they do not.
ForeverSTUwaveProbe = ForeverSTUwaveProbe or {}

local function Probe()
    local result = {
        when = date("%Y-%m-%d %H:%M:%S"),
        loadstringUntainted = type(loadstring_untainted),
        loadstring = type(loadstring),
    }

    local frame = CreateFrame("Frame", "FSProbeHeader", UIParent, "SecureHandlerStateTemplate")
    result.isProtected = tostring(frame:IsProtected())
    result.explicitlyProtected = tostring(select(2, frame:IsProtected()))

    -- 1. Does a brand-new Execute body compile and actually run?
    local ok, err = pcall(function()
        frame:Execute([[ self:SetAttribute("fsprobe", "ran") ]])
    end)
    result.executeCallOk = tostring(ok)
    result.executeError = ok and "" or tostring(err)
    result.executeSideEffect = tostring(frame:GetAttribute("fsprobe"))

    -- 2. Does a state driver install without throwing? This is the exact call
    --    that fails in ActionBars.lua, reduced to the smallest possible body.
    local ok2, err2 = pcall(function()
        frame:SetAttribute("_onstate-probe", [[ self:SetAttribute("fsprobe2", "ran") ]])
        RegisterStateDriver(frame, "probe", "1")
    end)
    result.stateDriverOk = tostring(ok2)
    result.stateDriverError = ok2 and "" or tostring(err2)
    result.stateDriverSideEffect = tostring(frame:GetAttribute("fsprobe2"))

    -- 3. Does re-running a body Blizzard ALREADY compiled work? If a previously
    --    seen body succeeds while a new one fails, the factory cache is warm
    --    from load and the compiler itself is unavailable now -- which would
    --    explain why Blizzard's own UI works and ours does not.
    local ok3 = pcall(function()
        frame:Execute([[ self:SetAttribute("fsprobe", "ran") ]])
    end)
    result.executeRepeatOk = tostring(ok3)

    ForeverSTUwaveProbe = result
end

local probeFrame = CreateFrame("Frame")
probeFrame:RegisterEvent("ADDON_LOADED")
probeFrame:RegisterEvent("PLAYER_LOGIN")
probeFrame:SetScript("OnEvent", function(self, event, loadedAddon)
    if event == "ADDON_LOADED" then
        if loadedAddon ~= addonName then return end
        self:UnregisterEvent("ADDON_LOADED")
        -- Saved globals have landed by now, so this wipe actually sticks.
        wipe(ForeverSTUwaveErrorLog)
        wipe(byMessage)
        foreignStored = 0
        -- Put back what was logged while our files loaded (see preLoad).
        for _, entry in ipairs(preLoad) do
            ForeverSTUwaveErrorLog[#ForeverSTUwaveErrorLog + 1] = entry
            byMessage[entry.key or entry.message] = entry
            if not entry.ours then foreignStored = foreignStored + 1 end
        end
        wipe(preLoad)
        loaded = true
        return
    end

    self:UnregisterEvent("PLAYER_LOGIN")

    -- Measured HERE, on PLAYER_LOGIN, not at file scope: the client restores
    -- saved globals AFTER an addon's files run, so anything assigned during
    -- load is silently clobbered by last session's value. That is what kept
    -- the grid diagnostic looking stale.
    ForeverSTUwaveScaleDiag = {
        when = date("%H:%M:%S"),
        uiParentW = UIParent:GetWidth(),
        uiParentH = UIParent:GetHeight(),
        uiParentScale = UIParent:GetScale(),
        uiParentEffScale = UIParent:GetEffectiveScale(),
        screenW = GetScreenWidth and GetScreenWidth() or -1,
        screenH = GetScreenHeight and GetScreenHeight() or -1,
        uiScaleCVar = tostring(GetCVar and GetCVar("uiScale")),
        layoutScale = (FS.Layout and FS.Layout.Scale) and FS.Layout.Scale() or -1,
        gridW = FSActionGrid and FSActionGrid:GetWidth() or -1,
        gridLeft = FSActionGrid and FSActionGrid:GetLeft() or -1,
        gridBottom = FSActionGrid and FSActionGrid:GetBottom() or -1,
        stackW = FSActionBarStack and FSActionBarStack:GetWidth() or -1,
    }
end)

-- The probe answered its question on 2026-09-20 (snippets do not execute here)
-- and its two deliberate failures were popping the error frame on every login,
-- so it no longer runs automatically. /fssnippet re-runs it if the client ever
-- changes and the answer needs re-checking. It was /fsprobe until FSProbe.lua
-- (the secret-value probe) took that name; this one is /fssnippet now.
SLASH_FSSNIPPET1 = "/fssnippet"
SlashCmdList["FSSNIPPET"] = function()
    pcall(Probe)
    print("|cff22e0ffForever STUwave|r: probe run; /reload to flush it to SavedVariables.")
end

-------------------------------------------------------------------------------
-- Single secure-button test  (/fsbtn)
-------------------------------------------------------------------------------

-- The smallest possible test of the ONLY remaining action-bar design, before
-- anything gets built on top of it.
--
-- The probe above proved secure SNIPPETS never execute on this client, which
-- rules out LibActionButton: its buttons receive their type/action attributes
-- inside the UpdateState snippet, so they would stay permanently empty.
--
-- What is untested is whether a plain SecureActionButtonTemplate whose
-- attributes are set DIRECTLY from Lua still casts. That path involves no
-- restricted closure at all -- the click handling is C-side -- so it should be
-- unaffected. "Should be" is exactly the kind of claim that cost this project
-- an evening, so: one button, clicked by a human, before 72 more get built.
--
-- /fsbtn  puts a button in the middle of the screen bound to action slot 1
--         (the first slot of the main bar). Click it. If it casts what slot 1
--         holds, the design works and the rebuild is straightforward.
local testButton

SLASH_FSBTN1 = "/fsbtn"
SlashCmdList["FSBTN"] = function()
    if InCombatLockdown() then
        print("|cff22e0ffForever STUwave|r: out of combat only.")
        return
    end

    if not testButton then
        testButton = CreateFrame(
            "CheckButton", "FSTestSecureButton", UIParent,
            "ActionButtonTemplate, SecureActionButtonTemplate"
        )
        testButton:SetSize(64, 64)
        testButton:SetPoint("CENTER", UIParent, "CENTER", 0, 120)
        testButton:RegisterForClicks("AnyUp", "AnyDown")
    end

    -- Set directly, no snippet anywhere in the path.
    testButton:SetAttribute("type", "action")
    testButton:SetAttribute("action", 1)

    -- Paint it by hand: without LibActionButton nothing else will.
    local texture = GetActionTexture and GetActionTexture(1)
    if texture and testButton.icon then
        testButton.icon:SetTexture(texture)
    end

    testButton:Show()

    print("|cff22e0ffForever STUwave|r: test button up, centre screen, bound to "
        .. "action slot 1. Click it -- does it cast what is in slot 1?")
    print(("|cff22e0ffForever STUwave|r: slot 1 texture = %s"):format(tostring(texture)))
end
