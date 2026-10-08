-- Forever STUwave: tester bug dump (/fsbug)
--
-- A tester should be able to send ONE text file instead of a pile of screenshots. A WoW
-- addon cannot write arbitrary files, so this uses the two routes it does have:
--
--   * a copy box: /fsbug builds a snapshot, shows it as JSON in a scrollable EditBox, and the
--     tester selects it (click, or Ctrl+A), copies it and pastes it into a .txt file;
--   * SavedVariables: the same report is appended to ForeverSTUwaveDB.bugreports (the last
--     20 are kept), which the client writes to
--       WTF/Account/<ACCOUNT>/SavedVariables/forever-stuwave.lua
--     on /reload or logout.
--
--   /fsbug [note]   capture a snapshot (note is free text) and open the copy box
--   /fsbug all      show every stored report as one JSON array
--   /fsbug clear    delete the stored reports
--
-- The Lua errors in the report come from ErrorLog.lua (ForeverSTUwaveErrorLog); this file only
-- reads them.
--
-- SECRET VALUES. Every read goes through Call(), which pcalls the API and replaces any secret
-- result with the text "secret" BEFORE anything else touches it. IsSecret fails closed (a throwing
-- issecretvalue means "secret"). A secret is never compared, concatenated, indexed or tostring'd
-- here, so nothing in a report can raise and nothing secret reaches SavedVariables.
--
-- SIZE. Every string, list, table depth and the total node/byte count of the copied settings are
-- capped, so 20 stored reports cannot bloat the SavedVariables file.
--
-- COMBAT. The copy box is a plain, non-secure Frame parented to UIParent and anchored only to
-- UIParent. Showing it in combat is safe (nothing protected is touched), so it simply opens.

local addonName, FS = ...

local BR = FS.BugReport or {}
FS.BugReport = BR

local SECRET = "secret"
local PREFIX = "|cff22e0ffForever STUwave|r"

local LIMITS = {
    reports = 20,    -- stored reports kept
    errors = 10,     -- last N captured Lua errors per report
    note = 500,
    str = 200,       -- any string inside the copied settings
    errMsg = 300,
    errStack = 1000,
    addons = 80,     -- loaded addon names listed (the true count is recorded too)
    addonName = 40,
    depth = 6,
    items = 60,      -- entries kept per table
    nodes = 600,     -- values visited in one settings copy
    bytes = 10000,   -- string bytes in one settings copy
}
BR.LIMITS = LIMITS

-- ForeverSTUwaveDB keys that are bulky logs or probes, or the reports themselves.
BR.EXCLUDE = {
    bugreports = true, bugreportSeq = true, recon = true, reconSkins = true, reconPos = true,
    fsprobe = true, fontProbe = true, labelsAtApply = true,
    -- Reported in their own `chatSeat` section (ChatSeat below), not through the generic copy.
    chatSeatLog = true, chatSeatLogPrev = true,
    -- Likewise reported in their own `minimapSeat` section (MinimapSeat below).
    minimapSeatLog = true, minimapSeatLogPrev = true, minimapSeatLogFirst = true,
    -- Account-wide profile data names every character (GUID, Name-Realm) and every profile; only the
    -- active profile's name and layout are reported (ActiveProfile below).
    profiles = true, profileKeys = true, profileLabels = true,
}

-- Frames reported by global name: ours, then the Blizzard ones we sit over.
BR.FRAME_NAMES = {
    "ForeverSTUwavePlayerFrame", "ForeverSTUwaveTargetFrame", "ForeverSTUwaveFocusFrame",
    "ForeverSTUwaveBoss1Frame",
    "ForeverSTUwavePartyRow1", "ForeverSTUwavePartyRow2", "ForeverSTUwavePartyRow3",
    "ForeverSTUwavePartyRow4", "ForeverSTUwavePartyRow5",
    "ForeverSTUwavePlayerCastBar", "ForeverSTUwaveTargetCastBar", "ForeverSTUwaveXPBar",
    "ForeverSTUwaveDataBar", "ForeverSTUwaveDeck", "ForeverSTUwaveBagBar",
    "ForeverSTUwaveMicroBar", "ForeverSTUwaveCombatHud",
    "FSActionBar", "FSActionBarStack", "FSActionGrid", "FSStanceBar", "FSPetContainer", "FSConsole",
    "PlayerFrame", "TargetFrame", "MinimapCluster", "ChatFrame1", "PTR_IssueReporter",
}

-- The game folder name for this client. It is the Forever beta build; the tester guide tells
-- anyone on another client to look for the folder that holds Interface\AddOns\forever-stuwave.
BR.CLIENT_FOLDER = "_classic_beta_"
BR.SV_PATH_SLASH = "WTF/Account/<ACCOUNT>/SavedVariables/forever-stuwave.lua"
BR.SV_PATH_WINDOWS = "World of Warcraft\\" .. BR.CLIENT_FOLDER
    .. "\\WTF\\Account\\<ACCOUNT>\\SavedVariables\\forever-stuwave.lua"
BR.HINT = "Ctrl+A, Ctrl+C, paste into a .txt and send it"

-------------------------------------------------------------------------------
-- Secret-safe primitives
-------------------------------------------------------------------------------

-- True when v is secret OR when that could not be determined. Failing closed means a broken
-- issecretvalue can only ever cost us data, never leak a value.
local function IsSecret(v)
    local fn = FS.IsSecret or _G.issecretvalue
    if type(fn) ~= "function" then return false end
    local ok, r = pcall(fn, v)
    if not ok then return true end
    return r ~= false
end

local function pack(...)
    return { n = select("#", ...), ... }
end

-- Calls fn under pcall. Result: { status = "ok" | "error" | "unavailable", [i] = value, n = count }
-- with every secret value already replaced by "secret".
local function Call(fn, ...)
    if type(fn) ~= "function" then return { status = "unavailable", n = 0 } end
    local r = pack(pcall(fn, ...))
    if not r[1] then return { status = "error", n = 0 } end
    local out = { status = "ok", n = r.n - 1 }
    for i = 2, r.n do
        local v = r[i]
        if IsSecret(v) then out[i - 1] = SECRET else out[i - 1] = v end
    end
    return out
end

-- The i-th result, or the status text ("error" / "unavailable") when the call did not run.
local function Val(r, i)
    if r.status ~= "ok" then return r.status end
    return r[i]
end

local function API(name) return _G[name] end
local function NS(ns, name)
    local t = _G[ns]
    if type(t) == "table" then return t[name] end
end

local function Round1(v)
    if type(v) ~= "number" then return v end
    return math.floor(v * 10 + 0.5) / 10
end

local function Say(text)
    pcall(print, PREFIX .. ": " .. text)
end

-------------------------------------------------------------------------------
-- Sanitize + JSON
-------------------------------------------------------------------------------

-- Cuts s to `max` bytes without splitting a UTF-8 sequence, and says how much went.
local function CapString(s, max)
    if #s <= max then return s end
    local cut = max
    while cut > 0 do
        local b = s:byte(cut + 1)
        if b and b >= 128 and b < 192 then cut = cut - 1 else break end
    end
    return s:sub(1, cut) .. "...(+" .. (#s - cut) .. " chars)"
end
BR.CapString = CapString

local function NewState(o)
    o = o or {}
    return {
        maxDepth = o.maxDepth or LIMITS.depth,
        maxItems = o.maxItems or LIMITS.items,
        maxString = o.maxString or LIMITS.str,
        maxNodes = o.maxNodes or LIMITS.nodes,
        maxBytes = o.maxBytes or 100000000,
        nodes = 0, bytes = 0, over = false,
    }
end

local function KeyLess(a, b)
    local ta, tb = type(a), type(b)
    if ta ~= tb then return ta == "number" end
    return a < b
end

-- Tables and table KEYS are judged by issecretvalue alone and a failing check does NOT make them
-- secret: a secret table cannot be traversed anyway (the pcall'd key walk fails and it reads
-- "<unreadable>", and a secret key that slipped through makes the pcall'd sort fail the same way),
-- while failing closed here would turn the whole report into the word "secret". Scalar VALUES do
-- fail closed (IsSecret above).
local function TableSecret(v)
    local fn = FS.IsSecret or _G.issecretvalue
    if type(fn) ~= "function" then return false end
    local ok, r = pcall(fn, v)
    return ok and r ~= false
end

local function CollectKeys(t)
    local keys = {}
    for k in next, t do
        local tk = type(k)
        if (tk == "string" or tk == "number") and not TableSecret(k) then keys[#keys + 1] = k end
    end
    table.sort(keys, KeyLess)
    return keys
end

-- A plain, acyclic, capped copy of v: secrets become "secret", cycles "<cycle>", NaN/inf the
-- strings "NaN" / "inf" / "-inf", functions "<function>", over-deep tables "<depth>". Only
-- strings, finite numbers, booleans and tables come out, so the result is always safe to store
-- in SavedVariables and to serialise.
local function Sanitize(v, st, depth, stack)
    local t = type(v)
    if t == "table" then
        if TableSecret(v) then return SECRET end
    elseif IsSecret(v) then
        return SECRET
    end
    if t == "nil" then return nil end
    if t == "boolean" then return v end
    if t == "number" then
        if v ~= v then return "NaN" end
        if v == math.huge then return "inf" end
        if v == -math.huge then return "-inf" end
        return v
    end
    st.nodes = st.nodes + 1
    if st.nodes > st.maxNodes then st.over = true end
    if t == "string" then
        local s = CapString(v, st.maxString)
        st.bytes = st.bytes + #s
        if st.bytes > st.maxBytes then st.over = true end
        if st.over then return "<truncated>" end
        return s
    end
    if t ~= "table" then return "<" .. t .. ">" end
    if st.over then return "<truncated>" end
    if stack[v] then return "<cycle>" end
    if depth >= st.maxDepth then return "<depth>" end

    local ok, keys = pcall(CollectKeys, v)
    if not ok then return "<unreadable>" end

    local n = #keys
    local isArray = n > 0
    for i = 1, n do
        if keys[i] ~= i then isArray = false; break end
    end

    stack[v] = true
    local out = {}
    local limit = math.min(n, st.maxItems)
    for i = 1, limit do
        if st.over then break end
        local k = keys[i]
        local okGet, val = pcall(rawget, v, k)
        if okGet then
            local clean = Sanitize(val, st, depth + 1, stack)
            if clean ~= nil then
                -- A string key is as unbounded as a string value, so it is capped the same way and
                -- counted against the byte budget. Two keys that collapse to one keep the first.
                local name = k
                if type(k) == "string" then
                    name = CapString(k, st.maxString)
                    st.bytes = st.bytes + #name
                    if st.bytes > st.maxBytes then st.over = true end
                end
                if out[name] == nil then out[name] = clean end
            end
        end
    end
    stack[v] = nil

    if st.over then
        if isArray then out[#out + 1] = "<truncated>" else out._truncated = "<truncated>" end
    elseif n > limit then
        if isArray then out[limit + 1] = "<+" .. (n - limit) .. " more>" else out._truncated = n - limit end
    end
    return out
end
BR.Sanitize = Sanitize

local ESC = {
    ['"'] = '\\"', ["\\"] = "\\\\", ["\n"] = "\\n", ["\r"] = "\\r", ["\t"] = "\\t",
    ["\b"] = "\\b", ["\f"] = "\\f",
}

-- Byte length of the valid UTF-8 sequence starting at i, or nil when it is not valid.
local function Utf8Len(s, i)
    local b = s:byte(i)
    local need, lo, hi
    if b >= 0xC2 and b <= 0xDF then need, lo, hi = 1, 0x80, 0xBF
    elseif b == 0xE0 then need, lo, hi = 2, 0xA0, 0xBF
    elseif b == 0xED then need, lo, hi = 2, 0x80, 0x9F
    elseif b >= 0xE1 and b <= 0xEF then need, lo, hi = 2, 0x80, 0xBF
    elseif b == 0xF0 then need, lo, hi = 3, 0x90, 0xBF
    elseif b >= 0xF1 and b <= 0xF3 then need, lo, hi = 3, 0x80, 0xBF
    elseif b == 0xF4 then need, lo, hi = 3, 0x80, 0x8F
    else return nil end
    local b2 = s:byte(i + 1)
    if not b2 or b2 < lo or b2 > hi then return nil end
    for j = 2, need do
        local c = s:byte(i + j)
        if not c or c < 0x80 or c > 0xBF then return nil end
    end
    return need + 1
end

local function Escape(c)
    return ESC[c] or string.format("\\u%04x", c:byte())
end

local function Quote(s)
    if not s:find("[\128-\255]") then
        return '"' .. s:gsub('[%c"\\]', Escape) .. '"'
    end
    local out, i, n = {}, 1, #s
    while i <= n do
        local b = s:byte(i)
        if b < 128 then
            local c = string.char(b)
            if c:find('[%c"\\]') then c = Escape(c) end
            out[#out + 1] = c
            i = i + 1
        else
            local len = Utf8Len(s, i)
            if len then
                out[#out + 1] = s:sub(i, i + len - 1)
                i = i + len
            else
                out[#out + 1] = string.format("\\u%04x", b)
                i = i + 1
            end
        end
    end
    return '"' .. table.concat(out) .. '"'
end

local function Num(v)
    if v ~= v then return '"NaN"' end
    if v == math.huge then return '"inf"' end
    if v == -math.huge then return '"-inf"' end
    if v == 0 then return "0" end    -- also turns -0 into 0
    -- %.0f, not %d: the client's %d goes through a C int on some builds, which breaks from 2^31 up.
    if v == math.floor(v) and math.abs(v) < 1e15 then return string.format("%.0f", v) end
    return string.format("%.14g", v)
end

local function IsArray(t)
    local n = #t
    if n == 0 then return false end
    local count = 0
    for _ in pairs(t) do count = count + 1 end
    if count ~= n then return false end
    for i = 1, n do
        if t[i] == nil then return false end
    end
    return true
end

-- Serialises an already sanitised value. Defensive anyway: it never recurses past 64 levels.
local function Serialize(v, indent, level)
    local t = type(v)
    if t == "string" then return Quote(v) end
    if t == "number" then return Num(v) end
    if t == "boolean" then return v and "true" or "false" end
    if t == "nil" then return "null" end
    if t ~= "table" then return '"<' .. t .. '>"' end
    if level > 64 then return '"<depth>"' end

    local pretty = indent > 0
    local pad = pretty and string.rep(" ", indent * (level + 1)) or ""
    local close = pretty and ("\n" .. string.rep(" ", indent * level)) or ""
    local nl = pretty and "\n" or ""
    local sep = pretty and ": " or ":"
    local parts = {}

    if IsArray(v) then
        for i = 1, #v do parts[i] = pad .. Serialize(v[i], indent, level + 1) end
        return "[" .. nl .. table.concat(parts, "," .. nl) .. close .. "]"
    end

    local names, byName = {}, {}
    for k, x in pairs(v) do
        local tk = type(k)
        if tk == "string" or tk == "number" then
            local name = tk == "string" and k or Num(k):gsub('"', "")
            names[#names + 1] = name
            byName[name] = x
        end
    end
    if #names == 0 then return "[]" end
    table.sort(names)
    for i, name in ipairs(names) do
        parts[i] = pad .. Quote(name) .. sep .. Serialize(byName[name], indent, level + 1)
    end
    return "{" .. nl .. table.concat(parts, "," .. nl) .. close .. "}"
end

-- JSON text for any Lua value. opts: indent (spaces, default 2, false for compact), maxDepth,
-- maxItems, maxString, maxNodes.
function BR.Encode(value, opts)
    opts = opts or {}
    local clean = Sanitize(value, NewState(opts), 0, {})
    local indent = opts.indent
    if indent == nil then indent = 2 elseif indent == false then indent = 0 end
    return Serialize(clean, indent, 0)
end

-- JSON for reports that were already sanitised when they were captured (no second capping, so
-- their own truncation markers are not cut again).
function BR.EncodeReports(list)
    return Serialize(list, 2, 0)
end

-------------------------------------------------------------------------------
-- The snapshot
-------------------------------------------------------------------------------

local function Spec()
    local fn = API("GetSpecialization")
    if type(fn) == "function" then
        local idx = Val(Call(fn), 1)
        if type(idx) == "number" then
            local name = Val(Call(API("GetSpecializationInfo"), idx), 2)
            if type(name) == "string" then return name end
        end
        if type(idx) == "string" then return idx end
        return "unavailable"
    end
    -- Classic style talent tabs: name, icon, points spent. Best effort, the tab with most points.
    local tabs = Val(Call(API("GetNumTalentTabs")), 1)
    if type(tabs) == "number" then
        local bestName, bestPoints = nil, -1
        for i = 1, math.min(tabs, 5) do
            local r = Call(API("GetTalentTabInfo"), i)
            local name, points = Val(r, 1), Val(r, 3)
            if type(name) == "string" and type(points) == "number" and points > bestPoints then
                bestName, bestPoints = name, points
            end
        end
        if bestName then return bestName end
    end
    return "unavailable"
end

local function AddClass(byClass, unit)
    local token = Val(Call(API("UnitClass"), unit), 2)
    if type(token) == "string" then byClass[token] = (byClass[token] or 0) + 1 end
end

local function Group()
    local size = Val(Call(API("GetNumGroupMembers")), 1)
    local inRaid = Val(Call(API("IsInRaid")), 1)
    local g = {
        inGroup = Val(Call(API("IsInGroup")), 1),
        inRaid = inRaid,
        size = size,
        byClass = {},
    }
    if type(size) == "number" and size > 0 then
        local count = math.min(size, 40)
        if inRaid == true then
            for i = 1, count do AddClass(g.byClass, "raid" .. i) end
        else
            AddClass(g.byClass, "player")
            for i = 1, count - 1 do AddClass(g.byClass, "party" .. i) end
        end
    else
        AddClass(g.byClass, "player")
    end
    return g
end

local function Frames()
    local out = {}
    for _, name in ipairs(BR.FRAME_NAMES) do
        local f = _G[name]
        if type(f) ~= "table" then
            out[name] = "absent"
        else
            out[name] = {
                shown = Val(Call(f.IsShown, f), 1),
                visible = Val(Call(f.IsVisible, f), 1),
                w = Round1(Val(Call(f.GetWidth, f), 1)),
                h = Round1(Val(Call(f.GetHeight, f), 1)),
            }
        end
    end
    return out
end

local function Addons()
    local CA = _G.C_AddOns
    local getNum = (type(CA) == "table" and CA.GetNumAddOns) or API("GetNumAddOns")
    local getInfo = (type(CA) == "table" and CA.GetAddOnInfo) or API("GetAddOnInfo")
    local isLoaded = (type(CA) == "table" and CA.IsAddOnLoaded) or API("IsAddOnLoaded")
    local total = Val(Call(getNum), 1)
    local names, loadedCount = {}, 0
    if type(total) ~= "number" then return names, total end
    local more = 0
    for i = 1, math.min(total, 1000) do
        if Val(Call(isLoaded, i), 1) == true then
            loadedCount = loadedCount + 1
            if #names < LIMITS.addons then
                local info = Call(getInfo, i)
                local name = Val(info, 1)
                if type(name) == "table" then name = name.name end
                if type(name) == "string" then
                    names[#names + 1] = CapString(name, LIMITS.addonName)
                else
                    names[#names + 1] = "?"
                end
            else
                more = more + 1
            end
        end
    end
    if more > 0 then names[#names + 1] = "<+" .. more .. " more>" end
    return names, loadedCount
end

local function ActiveProfile(db)
    local config = FS.Config
    if type(config) ~= "table" or type(config.ActiveProfile) ~= "function" then return nil end
    local ok, name = pcall(config.ActiveProfile)
    if not ok or type(name) ~= "string" then return nil end
    local okGet, profiles = pcall(rawget, db, "profiles")
    local profile = okGet and type(profiles) == "table" and rawget(profiles, name) or nil
    return { name = name, layout = type(profile) == "table" and rawget(profile, "layout") or nil }
end

local function Settings()
    local db = _G.ForeverSTUwaveDB
    if type(db) ~= "table" then return {} end
    local copy = {}
    local ok, keys = pcall(CollectKeys, db)
    if not ok then return { _unreadable = true } end
    for _, k in ipairs(keys) do
        if not BR.EXCLUDE[k] then
            local okGet, v = pcall(rawget, db, k)
            if okGet then copy[k] = v end
        end
    end
    copy.activeProfile = ActiveProfile(db)
    local st = NewState({ maxBytes = LIMITS.bytes })
    return Sanitize(copy, st, 0, {}) or {}
end

-- A seat log (this session and the last one, plus an optional third slot): what seated or moved a frame, in
-- order, so a frame that sat wrong after a first login can be traced to the call that moved it. Its own
-- section with its own small budget, so it neither crowds out the settings nor depends on them.
local function SeatLogs(keys, limits)
    local db = _G.ForeverSTUwaveDB
    if type(db) ~= "table" then return "unavailable" end
    local out = {}
    for field, key in pairs(keys) do
        local ok, v = pcall(rawget, db, key)
        if ok then out[field] = v end
    end
    local st = NewState(limits)
    return Sanitize(out, st, 0, {}) or {}
end

-- ChatWindowState.lua's seat log (ChatFrame1).
local function ChatSeat()
    return SeatLogs({ log = "chatSeatLog", prev = "chatSeatLogPrev" },
        { maxItems = 25, maxNodes = 500, maxBytes = 6000, maxDepth = 4, maxString = 40 })
end

-- Minimap.lua's seat log (MinimapCluster and the map inside it): this session (`log`), the last one (`prev`)
-- and the first session ever logged (`first`, never overwritten, so two reloads cannot erase a first login).
-- The byte budget counts string VALUES and string KEYS (numbers are free). A full entry is a table, an event
-- name of up to 33 characters, a point name of up to 11 and 13 keys of 25 bytes in all, so the worst case is
-- 3 logs x 20 entries x 69 bytes = 4140 bytes and 3 x 20 x 3 = 180 nodes; a typical entry (12 + 3 + 25) is
-- about 40, so a typical set of three logs is about 2.4 KB and two (log and prev) about 1.6 KB. The caps
-- sit just above the worst case, so a full set of logs is never cut.
local function MinimapSeat()
    return SeatLogs({ log = "minimapSeatLog", prev = "minimapSeatLogPrev", first = "minimapSeatLogFirst" },
        { maxItems = 25, maxNodes = 260, maxBytes = 4600, maxDepth = 4, maxString = 40 })
end

local function Field(e, key)
    local ok, v = pcall(rawget, e, key)
    if not ok then return nil end
    if IsSecret(v) then return SECRET end
    return v
end

local function TextField(e, key, max)
    local v = Field(e, key)
    if v == SECRET or v == nil then return v end
    if type(v) ~= "string" then return "(" .. type(v) .. ")" end
    return CapString(v, max)
end

-- The last N of OUR captured errors (ErrorLog.lua), plus how many came from other addons.
local function Errors()
    local log = _G.ForeverSTUwaveErrorLog
    local ours, other = {}, 0
    if type(log) == "table" then
        for i = 1, math.min(#log, 200) do
            local e = log[i]
            if type(e) == "table" then
                if Field(e, "ours") == false then other = other + 1 else ours[#ours + 1] = e end
            end
        end
    end
    local first = math.max(1, #ours - LIMITS.errors + 1)
    local list = {}
    for i = first, #ours do
        local e = ours[i]
        list[#list + 1] = {
            message = TextField(e, "message", LIMITS.errMsg),
            stack = TextField(e, "stack", LIMITS.errStack),
            count = Field(e, "count"),
            combat = Field(e, "combat"),
            firstSeen = TextField(e, "firstSeen", 40),
            lastSeen = TextField(e, "lastSeen", 40),
        }
    end
    return list, #ours, other
end

BR.Errors = Errors

-- The last `/fsrecon class` run (Diagnostics.lua). Read through FS.Diagnostics at call time, since
-- that file loads after this one. The tester runs the recon once, then /fsbug; the final Sanitize
-- pass in BR.Build bounds and scrubs whatever it hands back.
-- The full run goes into the first report after the tester ran the recon; once /fsbug has shown that
-- report (BR.MarkReported, last step of RunCapture) it is marked reported, and later reports (other
-- characters included) carry a stub with the run's date instead. Build and Capture never mark, so a
-- failure in the store, the serialiser or the copy box leaves the run for the next /fsbug.
-- There is ONE recon slot (Diagnostics keeps only the latest run, whichever character ran it), so the
-- stub's `taken` stamp and the full run's `taken` and `token` are what tie a report to its run.
local CLASS_RECON_STUB = "attached to an earlier report"

local function ClassRecon()
    local D = FS.Diagnostics
    if type(D) ~= "table" or type(D.GetClassRecon) ~= "function" then return "unavailable" end
    local data = D.GetClassRecon()
    if IsSecret(data) then return SECRET end
    if data == nil then return "not run" end
    local okFlag, reported = pcall(rawget, data, "reported")
    if okFlag and not IsSecret(reported) and reported == true then
        local okTaken, taken = pcall(rawget, data, "taken")
        if not okTaken or IsSecret(taken) or type(taken) ~= "string" then taken = "unknown" end
        return { taken = taken, note = CLASS_RECON_STUB }
    end
    return data
end

local function NextId()
    local db = _G.ForeverSTUwaveDB
    local seq = type(db) == "table" and rawget(db, "bugreportSeq") or nil
    if type(seq) ~= "number" or seq ~= seq or seq < 0 then seq = 0 end
    return seq + 1
end

-- Runs one section of the report. A section that throws becomes the word "error" and the rest of
-- the report is still built; a tester's one bad API must not cost the whole report.
local function Guard(fn, ...)
    local ok, a, b, c = pcall(fn, ...)
    if not ok then return "error" end
    return a, b, c
end

-- One snapshot, as plain capped data (strings, finite numbers, booleans, tables only).
function BR.Build(note)
    local okId, id = pcall(NextId)
    local report = { schema = 1, id = okId and id or 1 }

    if note == nil or IsSecret(note) or type(note) ~= "string" then note = "" end
    report.note = CapString(note, LIMITS.note)

    report.time = Guard(function()
        local okDate, stamp = pcall(date, "%Y-%m-%d %H:%M:%S")
        local okTime, epoch = pcall(time)
        return { date = okDate and stamp or "unavailable", epoch = okTime and epoch or nil }
    end)

    report.addon = Guard(function()
        local CA = _G.C_AddOns
        local metaFn = (type(CA) == "table" and CA.GetAddOnMetadata) or API("GetAddOnMetadata")
        return { name = addonName, version = Val(Call(metaFn, addonName, "Version"), 1) }
    end)

    report.client = Guard(function()
        local b = Call(API("GetBuildInfo"))
        return {
            version = Val(b, 1), build = Val(b, 2), buildDate = Val(b, 3), toc = Val(b, 4),
            project = type(_G.WOW_PROJECT_ID) == "number" and _G.WOW_PROJECT_ID or nil,
        }
    end)

    report.player = Guard(function()
        local cls = Call(API("UnitClass"), "player")
        local race = Call(API("UnitRace"), "player")
        return {
            class = Val(cls, 1), classToken = Val(cls, 2),
            race = Val(race, 1),
            level = Val(Call(API("UnitLevel"), "player"), 1),
            spec = Spec(),
            inCombat = Val(Call(API("InCombatLockdown")), 1),
            hasPet = Val(Call(API("UnitExists"), "pet"), 1),
        }
    end)

    report.location = Guard(function()
        local inst = Call(API("IsInInstance"))
        local info = Call(API("GetInstanceInfo"))
        return {
            zone = Val(Call(API("GetZoneText")), 1),
            realZone = Val(Call(API("GetRealZoneText")), 1),
            subZone = Val(Call(API("GetSubZoneText")), 1),
            inInstance = Val(inst, 1), instanceType = Val(inst, 2),
            instanceName = Val(info, 1), difficultyID = Val(info, 3), instanceID = Val(info, 8),
            mapID = Val(Call(NS("C_Map", "GetBestMapForUnit"), "player"), 1),
        }
    end)

    report.display = Guard(function()
        local ui = _G.UIParent
        local phys = Call(API("GetPhysicalScreenSize"))
        return {
            uiScale = Val(Call(ui and ui.GetScale, ui), 1),
            effectiveScale = Val(Call(ui and ui.GetEffectiveScale, ui), 1),
            screenWidth = Val(Call(API("GetScreenWidth")), 1),
            screenHeight = Val(Call(API("GetScreenHeight")), 1),
            physicalWidth = Val(phys, 1), physicalHeight = Val(phys, 2),
            uiScaleCVar = Val(Call(API("GetCVar"), "uiScale"), 1),
            layoutScale = Val(Call(type(FS.Layout) == "table" and FS.Layout.Scale or nil), 1),
        }
    end)

    report.group = Guard(Group)
    report.frames = Guard(Frames)
    report.settings = Guard(Settings)
    report.chatSeat = Guard(ChatSeat)
    report.minimapSeat = Guard(MinimapSeat)
    report.classRecon = Guard(ClassRecon)

    local errors, errorCount, otherCount = Guard(Errors)
    if errors == "error" then errorCount, otherCount = "error", "error" end
    report.errors = errors
    report.errorCount = errorCount
    report.otherErrorCount = otherCount

    local names, count = Guard(Addons)
    if names == "error" then count = "error" end
    report.addons = names
    report.addonCount = count

    -- Final pass: guarantees plain data whatever the sections above did. Settings were already
    -- capped tightly; this one only has to leave their markers and the error stacks alone.
    return Sanitize(report, NewState({
        maxString = 2000, maxItems = 200, maxDepth = 9, maxNodes = 8000, maxBytes = 100000,
    }), 0, {}) or {}
end

-------------------------------------------------------------------------------
-- Storage
-------------------------------------------------------------------------------

function BR.Store(report)
    local db = _G.ForeverSTUwaveDB
    if type(db) ~= "table" then
        db = {}
        _G.ForeverSTUwaveDB = db
    end
    local list = db.bugreports
    if type(list) ~= "table" then
        list = {}
        db.bugreports = list
    end
    list[#list + 1] = report
    while #list > LIMITS.reports do table.remove(list, 1) end
    if type(report.id) == "number" then db.bugreportSeq = report.id end
    return #list
end

-- Builds and stores a report. It does NOT consume the class recon run: RunCapture does that once the
-- tester has the report in front of them.
function BR.Capture(note)
    local report = BR.Build(note)
    BR.Store(report)
    return report
end

-- Consumes the class recon run a report carries, so later reports get the stub. Never throws. A report
-- that holds only a stub (or no recon) leaves the run alone; marking is idempotent, so a stub needs no
-- special case.
function BR.MarkReported(report)
    pcall(function()
        local recon = type(report) == "table" and report.classRecon or nil
        local D = FS.Diagnostics
        if type(recon) == "table" and type(D) == "table" and type(D.MarkClassReconReported) == "function" then
            D.MarkClassReconReported()
        end
    end)
end

function BR.Clear()
    local db = _G.ForeverSTUwaveDB
    if type(db) ~= "table" or type(db.bugreports) ~= "table" then return 0 end
    local n = #db.bugreports
    for i = n, 1, -1 do db.bugreports[i] = nil end
    return n
end

-------------------------------------------------------------------------------
-- The copy box
-------------------------------------------------------------------------------

local FRAME_NAME = "ForeverSTUwaveBugReport"
local FRAME_W, FRAME_H = 640, 440
local PAD, TOP, BOTTOM, GUTTER = 14, 54, 44, 30
local LINE_H, CHAR_W = 13, 6.6

local ui = {}

local function Theme() return FS.Theme end

local function Label(parent, text, size, color)
    local fs = parent:CreateFontString(nil, "OVERLAY")
    local th = Theme()
    local ok = th and th.ApplyMono and pcall(th.ApplyMono, fs, size, color)
    if not ok and _G.GameFontHighlightSmall then pcall(fs.SetFontObject, fs, _G.GameFontHighlightSmall) end
    fs:SetText(text)
    return fs
end

local function EstimateHeight(text, width)
    local cols = math.max(20, math.floor(width / CHAR_W))
    local lines = 0
    for line in (text .. "\n"):gmatch("(.-)\n") do
        lines = lines + math.max(1, math.ceil(#line / cols))
    end
    return lines * LINE_H + 12
end

local function UpdateThumb()
    local scroll, thumb = ui.scroll, ui.thumb
    -- ui.frame is only set once the whole frame has built, so an early scroll event is a no-op.
    if not (scroll and thumb and ui.frame) then return end
    local range = scroll:GetVerticalScrollRange()
    local view = scroll:GetHeight()
    if type(range) ~= "number" or type(view) ~= "number" or range <= 0 or view <= 0 then
        thumb:Hide()
        return
    end
    local thumbH = math.max(20, view * view / (view + range))
    local y = (scroll:GetVerticalScroll() / range) * (view - thumbH)
    thumb:SetHeight(thumbH)
    thumb:ClearAllPoints()
    thumb:SetPoint("TOPRIGHT", ui.frame, "TOPRIGHT", -PAD, -TOP - y)
    thumb:Show()
end

-- ui.frame is set only as the LAST step. If anything below throws, the half built frame is simply
-- dropped and the next ShowFrame builds again, instead of finding a frame with no edit box.
local function Build()
    local th = Theme()
    local frame = CreateFrame("Frame", FRAME_NAME, UIParent)
    -- A new frame is shown by default. Hide it at once so a throw partway through this function
    -- never leaves a half built frame on screen.
    frame:Hide()
    frame:SetSize(FRAME_W, FRAME_H)
    frame:SetPoint("CENTER", UIParent, "CENTER", 0, 40)
    frame:SetFrameStrata("DIALOG")
    frame:SetToplevel(true)
    frame:SetClampedToScreen(true)
    frame:SetMovable(true)
    frame:EnableMouse(true)
    frame:RegisterForDrag("LeftButton")
    frame:SetScript("OnDragStart", frame.StartMoving)
    frame:SetScript("OnDragStop", frame.StopMovingOrSizing)

    local skinned = th and th.SkinPanel and pcall(th.SkinPanel, frame, { strip = false, title = "bugreport" })
    if not skinned then
        local bg = frame:CreateTexture(nil, "BACKGROUND")
        bg:SetAllPoints(frame)
        bg:SetColorTexture(0.102, 0.063, 0.145, 0.95)
    end

    local muted = th and th.COLOR_MUTED or { 0.62, 0.58, 0.77, 1 }
    local cyan = th and th.COLOR_POWER or { 0.13, 0.88, 1, 1 }

    ui.hint = Label(frame, BR.HINT, 11, cyan)
    ui.hint:SetPoint("TOPLEFT", frame, "TOPLEFT", PAD, -30)

    ui.status = Label(frame, "", 10, muted)
    ui.status:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -PAD, -31)

    local viewW = FRAME_W - PAD - GUTTER
    local viewH = FRAME_H - TOP - BOTTOM
    ui.viewW, ui.viewH = viewW, viewH

    local well = frame:CreateTexture(nil, "BACKGROUND", nil, 1)
    well:SetColorTexture(0.039, 0.016, 0.086, 0.95)
    well:SetPoint("TOPLEFT", frame, "TOPLEFT", PAD, -TOP)
    well:SetSize(viewW, viewH)

    local scroll = CreateFrame("ScrollFrame", nil, frame)
    ui.scroll = scroll
    scroll:SetPoint("TOPLEFT", frame, "TOPLEFT", PAD, -TOP)
    scroll:SetSize(viewW, viewH)
    scroll:EnableMouseWheel(true)
    scroll:SetScript("OnMouseWheel", function(self, delta)
        if type(delta) ~= "number" then return end
        local range = self:GetVerticalScrollRange()
        local nextV = math.min(math.max(self:GetVerticalScroll() - delta * LINE_H * 3, 0), range)
        self:SetVerticalScroll(nextV)
        UpdateThumb()
    end)
    scroll:SetScript("OnVerticalScroll", function() pcall(UpdateThumb) end)
    scroll:SetScript("OnScrollRangeChanged", function() pcall(UpdateThumb) end)

    local edit = CreateFrame("EditBox", nil, scroll)
    ui.edit = edit
    edit:SetMultiLine(true)
    edit:SetAutoFocus(false)
    if _G.ChatFontNormal then pcall(edit.SetFontObject, edit, _G.ChatFontNormal) end
    if th and th.FONT_MONO then pcall(edit.SetFont, edit, th.FONT_MONO, 11, "") end
    pcall(edit.SetMaxLetters, edit, 0)
    pcall(edit.SetMaxBytes, edit, 0)
    edit:SetTextInsets(4, 4, 4, 4)
    edit:SetWidth(viewW)
    edit:SetHeight(viewH)
    scroll:SetScrollChild(edit)

    -- Read only in effect: any typed or pasted change is put straight back, so the report cannot
    -- be damaged by a stray key, while select and copy still work.
    edit:SetScript("OnTextChanged", function(self, userInput)
        if userInput and self.fsText and self:GetText() ~= self.fsText then
            self:SetText(self.fsText)
        end
    end)
    edit:SetScript("OnEditFocusGained", function(self) self:HighlightText() end)
    edit:SetScript("OnMouseUp", function(self)
        self:SetFocus()
        self:HighlightText()
    end)
    edit:SetScript("OnEscapePressed", function() frame:Hide() end)
    edit:SetScript("OnCursorChanged", function(_, _, y, _, h)
        if type(y) ~= "number" or type(h) ~= "number" then return end
        local top, view = scroll:GetVerticalScroll(), scroll:GetHeight()
        local at = -y
        if at < top then
            scroll:SetVerticalScroll(at)
        elseif at + h > top + view then
            scroll:SetVerticalScroll(at + h - view)
        end
    end)

    local track = frame:CreateTexture(nil, "ARTWORK")
    track:SetColorTexture(0.227, 0.129, 0.408, 0.6)
    track:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -PAD, -TOP)
    track:SetSize(4, viewH)
    local thumb = frame:CreateTexture(nil, "OVERLAY")
    thumb:SetColorTexture(0.659, 0.333, 0.969, 1)
    thumb:SetWidth(4)
    ui.thumb = thumb

    local close = CreateFrame("Button", nil, frame)
    close:SetSize(90, 22)
    close:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -PAD, 12)
    local skinnedButton = th and th.SkinButton and pcall(th.SkinButton, close)
    if not skinnedButton then
        local fill = close:CreateTexture(nil, "BACKGROUND")
        fill:SetAllPoints(close)
        fill:SetColorTexture(0.227, 0.129, 0.408, 0.9)
    end
    local closeLabel = Label(close, "Close", 11, cyan)
    closeLabel:SetPoint("CENTER", close, "CENTER", 0, 0)
    close:SetScript("OnClick", function() frame:Hide() end)

    -- Escape closes it through the client's own special-frame stack, once.
    local specials = _G.UISpecialFrames
    if type(specials) == "table" then
        local present = false
        for _, name in ipairs(specials) do
            if name == FRAME_NAME then present = true end
        end
        if not present then table.insert(specials, FRAME_NAME) end
    end

    frame:Hide()
    ui.frame = frame
    return frame
end

function BR.GetFrame() return ui.frame end
function BR.GetEditBox() return ui.edit end

-- Shows `text` in the copy box (building it on first use). Safe in combat: a plain frame.
function BR.ShowFrame(text, status)
    local frame = ui.frame or Build()
    text = type(text) == "string" and text or ""
    ui.edit.fsText = text
    ui.edit:SetText(text)
    ui.edit:SetCursorPosition(0)
    ui.edit:SetHeight(math.max(ui.viewH, EstimateHeight(text, ui.viewW)))
    ui.scroll:SetVerticalScroll(0)
    ui.status:SetText(status or "")
    frame:Show()
    pcall(UpdateThumb)
    return frame
end

-------------------------------------------------------------------------------
-- /fsbug
-------------------------------------------------------------------------------

-- "all" and "clear" count only when they are the whole argument, so a note that happens to
-- start with one ("all my bars vanished") is still a note.
function BR.ParseArgs(msg)
    local text = type(msg) == "string" and msg or ""
    text = text:match("^%s*(.-)%s*$")
    local word = text:lower()
    if word == "all" then return "all", "" end
    if word == "clear" then return "clear", "" end
    return "capture", text
end

local function Describe(count, size)
    return ("%d stored (max %d), about %d KB"):format(count, LIMITS.reports, math.floor(size / 1024 + 0.5))
end

local function RunCapture(note)
    local okBuild, report = pcall(BR.Capture, note)
    if not okBuild or type(report) ~= "table" then
        Say("could not build the bug report.")
        return
    end
    local text = Serialize(report, 2, 0)
    local list = _G.ForeverSTUwaveDB and _G.ForeverSTUwaveDB.bugreports
    local okShow = pcall(BR.ShowFrame, text, "report #" .. report.id .. ", "
        .. Describe(type(list) == "table" and #list or 1, #text))
    if okShow then
        -- Last, so a throw in the store, the serialiser or the copy box leaves the run for the next /fsbug.
        BR.MarkReported(report)
        Say(("bug report #%d captured. Click the box, Ctrl+A, Ctrl+C, paste it into a .txt file and send it."):format(report.id))
    else
        Say(("bug report #%d captured, but the copy box could not open. Send the saved file below instead."):format(report.id))
    end
    Say("it is also saved to " .. BR.SV_PATH_SLASH .. " after /reload or logout.")
    Say("on Windows, inside your game folder: " .. BR.SV_PATH_WINDOWS)
end

local function RunAll()
    local db = _G.ForeverSTUwaveDB
    local list = type(db) == "table" and db.bugreports
    if type(list) ~= "table" or #list == 0 then
        Say("no bug reports stored yet. Run /fsbug first.")
        return
    end
    local text = BR.EncodeReports(list)
    local ok = pcall(BR.ShowFrame, text, Describe(#list, #text))
    if ok then
        Say(("showing all %d stored reports. Ctrl+A, Ctrl+C, paste into a .txt file and send it."):format(#list))
    else
        Say("the copy box could not open. The reports are in " .. BR.SV_PATH_SLASH .. " after /reload or logout.")
    end
end

local function Run(msg)
    local action, note = BR.ParseArgs(msg)
    if action == "all" then
        RunAll()
    elseif action == "clear" then
        Say(("cleared %d bug report(s)."):format(BR.Clear()))
    else
        RunCapture(note)
    end
end

-- A slash handler must never throw into the client.
function BR.Run(msg)
    local ok, err = pcall(Run, msg)
    if not ok then Say("bug report failed: " .. (type(err) == "string" and err or "unknown error")) end
end

SLASH_FSBUG1 = "/fsbug"
SlashCmdList["FSBUG"] = BR.Run
