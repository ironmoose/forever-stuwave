#!/usr/bin/env python3
"""Runs the real BugReport.lua and ErrorLog.lua headless against a mock WoW API.

BugReport.lua is the `/fsbug` tester bug dump. ErrorLog.lua is the error capture it reads. The
properties worth pinning are the safety ones, not the data:

  * the JSON encoder: escapes, nesting, arrays vs objects, empty tables, cycles, NaN / inf,
    invalid UTF-8, size caps, and that real json.loads accepts what it writes;
  * secrets: with every API answering secret sentinels (whose metamethods raise on any compare,
    concat, arithmetic or tostring) a report still builds, holds the text "secret" and never a
    sentinel, and a failing issecretvalue fails closed;
  * storage: the last 20 reports kept, `clear`, size caps, the slash parsing;
  * the copy box builds, fills, selects on click, closes on Escape, and opens in combat with
    nothing secure about it;
  * error capture: our own errors are logged and suppressed with ONE throttled chat line, other
    addons' errors pass through to the previous handler untouched, dedupe, throttle, the blocked
    action events, a failing handler is safe, a replaced handler is re-wrapped without a cycle.

Known limit of the secret sentinels: they are tables whose metamethods raise, so they trap every
operation Lua routes through a metamethod. `==` against a string and `#` do NOT go through one (Lua
5.1 only calls __eq when both operands are tables, and ignores __len on tables), so a secret string
that is compared with `==` or measured with `#` is not trapped here, while the real client raises.
Checks about secrets therefore assert on the OUTPUT (the word "secret", no sentinel left) and on the
pcall that swallowed a trapped operation, never on "nothing ever touched it".

The mock is NOT the real client. Run:

    python3 tools/fsbug-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ADDON = Path(__file__).resolve().parent.parent
BR_SRC = (ADDON / "BugReport.lua").read_text(encoding="utf-8") if (ADDON / "BugReport.lua").exists() else ""
EL_SRC = (ADDON / "ErrorLog.lua").read_text(encoding="utf-8")

MOCK = r"""
realType = type

-------------------------------------------------------------------------------
-- Secret sentinels: type() reports the pretended type, every operation raises.
-------------------------------------------------------------------------------
SENT = {}
local function sentinel(kind)
    local function bad(what) return function() error("SECRET_OP " .. what, 2) end end
    local s = setmetatable({}, {
        __index = bad("index"), __newindex = bad("newindex"), __call = bad("call"),
        __concat = bad("concat"), __add = bad("add"), __sub = bad("sub"), __mul = bad("mul"),
        __div = bad("div"), __mod = bad("mod"), __pow = bad("pow"), __unm = bad("unm"),
        __lt = bad("lt"), __le = bad("le"), __eq = bad("eq"), __len = bad("len"),
        __tostring = bad("tostring"),
    })
    SENT[s] = kind
    return s
end
SN, SB, SS, ST = sentinel("number"), sentinel("boolean"), sentinel("string"), sentinel("table")
SENTK = { number = SN, boolean = SB, string = SS, table = ST }

function type(v)
    local k = SENT[v]
    if k then return k end
    return realType(v)
end

W = {
    mode = "plain",            -- plain | secret | throw | absent
    combat = false, pet = true,
    class = "PALADIN", level = 70, race = "Human",
    zone = "Shattrath City", subzone = "Terrace of Light",
    inInstance = false, instType = "none",
    group = {}, raid = nil, inRaid = false,
    issecretThrows = false,
    frameThrows = false,
    addons = {
        { "ForeverSynthwave", true }, { "Details", true }, { "DBM-Core", true }, { "Unloaded", false },
    },
}
__apiCalls = 0

function issecretvalue(v)
    __apiCalls = __apiCalls + 1
    if W.issecretThrows then error("boom: issecretvalue") end
    return SENT[v] ~= nil
end

__printed = {}
function print(...)
    local t = {}
    for i = 1, select("#", ...) do t[#t + 1] = tostring((select(i, ...))) end
    __printed[#__printed + 1] = table.concat(t, " ")
end
-- Chat lines with colour codes removed.
function Lines()
    local out = {}
    for i, l in ipairs(__printed) do
        out[i] = (l:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""))
    end
    return out
end

date = os.date
time = os.time
unpack = unpack
tinsert = table.insert
function wipe(t) for k in pairs(t) do t[k] = nil end return t end
__now = 1000
function GetTime() return __now end
__timers = {}
C_Timer = { After = function(sec, fn) __timers[#__timers + 1] = { sec = sec, fn = fn } end }
function RunTimers() local t = __timers; __timers = {}; for _, x in ipairs(t) do x.fn() end end
UISpecialFrames = {}
SlashCmdList = {}

-------------------------------------------------------------------------------
-- Frames
-------------------------------------------------------------------------------
__all = {}
local FM = {}
local newFrame
local FMT = {}
FMT.__index = function(self, k)
    local m = FM[k]
    if m then return m end
    return function(me, ...)
        me._calls[k] = (me._calls[k] or 0) + 1
        me._args[k] = { ... }
        if k:find("^Create") then return newFrame(k:sub(7), nil, me) end
    end
end
function newFrame(kind, name, parent, tmpl)
    local f = setmetatable({ _kind = kind, _name = name, _parent = parent, _tmpl = tmpl, _events = {},
        _scripts = {}, _calls = {}, _args = {}, _points = {}, _shown = true, _w = 0, _h = 0,
        _text = "", _children = {} }, FMT)
    if name then _G[name] = f end
    if parent and parent._children then parent._children[#parent._children + 1] = f end
    __all[#__all + 1] = f
    return f
end
function CreateFrame(kind, name, parent, tmpl)
    __apiCalls = __apiCalls + 1
    if W.frameThrows then error("boom: CreateFrame") end
    return newFrame(kind, name, parent, tmpl)
end
function FM.SetScript(s, k, fn) s._scripts[k] = fn end
function FM.GetScript(s, k) return s._scripts[k] end
function FM.HookScript(s, k, fn) s._scripts[k] = fn end
function FM.RegisterEvent(s, e) s._events[e] = true end
function FM.UnregisterEvent(s, e) s._events[e] = nil end
function FM.Show(s) s._shown = true; s._calls.Show = (s._calls.Show or 0) + 1 end
function FM.Hide(s) s._shown = false; s._calls.Hide = (s._calls.Hide or 0) + 1 end
function FM.IsShown(s) return s._shown end
function FM.IsVisible(s) return s._shown end
function FM.SetShown(s, v) s._shown = v and true or false end
function FM.SetText(s, t)
    s._text = t
    s._calls.SetText = (s._calls.SetText or 0) + 1
    if s._kind == "EditBox" and s._scripts.OnTextChanged then s._scripts.OnTextChanged(s, false) end
end
function FM.GetText(s) return s._text end
function FM.SetWidth(s, w) s._w = w end
function FM.SetHeight(s, h) s._h = h end
function FM.SetSize(s, w, h) s._w, s._h = w, h end
function FM.GetWidth(s) return s._w end
function FM.GetHeight(s) return s._h end
function FM.SetPoint(s, ...) s._points[#s._points + 1] = { ... } end
function FM.ClearAllPoints(s) s._points = {} end
function FM.SetFont() return true end
function FM.SetMovable(s, v) s._movable = v end
function FM.IsMovable(s) return s._movable end
function FM.SetClampedToScreen(s, v) s._clamped = v end
function FM.SetFrameStrata(s, v) s._strata = v end
function FM.SetMultiLine(s, v) s._multi = v end
function FM.SetScrollChild(s, c) s._scrollChild = c end
function FM.GetVerticalScrollRange(s) return math.max(0, (s._scrollChild and s._scrollChild._h or 0) - s._h) end
function FM.SetVerticalScroll(s, v) s._vscroll = v end
function FM.GetVerticalScroll(s) return s._vscroll or 0 end
function FM.GetParent(s) return s._parent end

UIParent = newFrame("Frame", nil, nil)
UIParent._w, UIParent._h = 2133, 1200
function UIParent.GetScale() return 0.64 end
function UIParent.GetEffectiveScale() return 0.64 end

-- Fire an event at every frame that registered it.
function Fire(event, ...)
    for _, f in ipairs(__all) do
        if f._events[event] and f._scripts.OnEvent then f._scripts.OnEvent(f, event, ...) end
    end
end

-------------------------------------------------------------------------------
-- WoW API (installed by InstallApis so a case can pick plain / secret / throw / absent)
-------------------------------------------------------------------------------
local function put(path, fn)
    local a, b = path:match("^(.-)%.(.+)$")
    if a then _G[a] = _G[a] or {}; _G[a][b] = fn else _G[path] = fn end
end

local function ClassOf(unit)
    if unit == "player" then return W.class end
    local p = unit:match("^party(%d+)$")
    if p then return W.group[tonumber(p)] end
    local r = unit:match("^raid(%d+)$")
    if r and W.raid then return W.raid[tonumber(r)] end
end

function InstallApis(mode)
    W.mode = mode or "plain"
    if W.mode == "absent" then return end
    local function api(path, kinds, plain)
        put(path, function(...)
            __apiCalls = __apiCalls + 1
            if W.mode == "throw" then error("boom: " .. path) end
            if W.mode == "secret" then
                local r = {}
                for i = 1, #kinds do r[i] = SENTK[kinds[i]] end
                return unpack(r, 1, #kinds)
            end
            return plain(...)
        end)
    end
    api("InCombatLockdown", { "boolean" }, function() return W.combat end)
    api("GetBuildInfo", { "string", "string", "string", "number" },
        function() return "1.16.1", "61234", "Sep 30 2026", 16001 end)
    api("UnitClass", { "string", "string", "number" }, function(u)
        local c = ClassOf(u)
        if not c then return nil end
        return c:sub(1, 1) .. c:sub(2):lower(), c, 2
    end)
    api("UnitRace", { "string", "string" }, function() return W.race, W.race end)
    api("UnitLevel", { "number" }, function() return W.level end)
    api("UnitExists", { "boolean" }, function(u)
        if u == "pet" then return W.pet end
        return ClassOf(u) ~= nil
    end)
    api("GetNumGroupMembers", { "number" }, function()
        if W.raid then return #W.raid end
        if #W.group > 0 then return 1 + #W.group end
        return 0
    end)
    api("IsInGroup", { "boolean" }, function() return W.raid ~= nil or #W.group > 0 end)
    api("IsInRaid", { "boolean" }, function() return W.raid ~= nil end)
    api("GetZoneText", { "string" }, function() return W.zone end)
    api("GetRealZoneText", { "string" }, function() return W.zone end)
    api("GetSubZoneText", { "string" }, function() return W.subzone end)
    api("IsInInstance", { "boolean", "string" }, function() return W.inInstance, W.instType end)
    api("GetInstanceInfo", { "string", "string", "number", "string", "number", "number", "boolean", "number" },
        function() return "Karazhan", "party", 1, "Normal", 5, 0, false, 532 end)
    api("C_Map.GetBestMapForUnit", { "number" }, function() return 1955 end)
    api("GetSpecialization", { "number" }, function() return 3 end)
    api("GetSpecializationInfo", { "number", "string" }, function() return 70, "Retribution" end)
    api("GetScreenWidth", { "number" }, function() return 2133.33 end)
    api("GetScreenHeight", { "number" }, function() return 1200 end)
    api("GetPhysicalScreenSize", { "number", "number" }, function() return 3413, 1920 end)
    api("GetCVar", { "string" }, function() return "0.64" end)
    api("C_AddOns.GetAddOnMetadata", { "string" }, function() return "0.1.0" end)
    api("C_AddOns.GetNumAddOns", { "number" }, function() return #W.addons end)
    api("C_AddOns.GetAddOnInfo", { "string", "string" }, function(i) return W.addons[i][1], W.addons[i][1] end)
    api("C_AddOns.IsAddOnLoaded", { "boolean" }, function(i)
        if realType(i) == "number" then return W.addons[i][2] end
        for _, a in ipairs(W.addons) do if a[1] == i then return a[2] end end
        return false
    end)
end

-------------------------------------------------------------------------------
-- Error handler plumbing
-------------------------------------------------------------------------------
__dsCalls = 0
__stack = "Interface\\AddOns\\Blizzard_Foo\\Foo.lua:10: in function `Bar'\n"
W.dsThrows = false
function debugstack()
    __dsCalls = __dsCalls + 1
    if W.dsThrows then error("boom: debugstack") end
    return __stack
end
__prevCalls = {}
__prev = function(err) __prevCalls[#__prevCalls + 1] = err end
__handler = __prev
function geterrorhandler() return __handler end
function seterrorhandler(fn) __handler = fn end

-------------------------------------------------------------------------------
-- Loading the real files
-------------------------------------------------------------------------------
function NewFS(opts)
    opts = opts or {}
    local FS = {}
    FS.IsSecret = function(v) return issecretvalue(v) end
    if not opts.noTheme then
        FS.Theme = {
            COLOR_BG = { 0.1, 0.06, 0.14, 0.8 }, COLOR_BORDER = { 0.66, 0.33, 0.97, 1 },
            COLOR_POWER = { 0.13, 0.88, 1, 1 }, COLOR_MUTED = { 0.6, 0.57, 0.77, 1 },
            FONT_MONO = "Interface\\AddOns\\ForeverSynthwave\\fonts\\Mono.ttf",
            SkinPanel = function(f, o) f._skinned = o end,
            SkinButton = function(b, o) b._skinnedButton = true end,
            ApplyMono = function(fs, size, color) fs._mono = size end,
        }
        FS.Layout = { Scale = function() return 0.5 end }
    end
    return FS
end

function LoadBR(opts)
    opts = opts or {}
    local FS = opts.FS or NewFS(opts)
    if opts.apis ~= false then InstallApis(opts.mode or "plain") end
    local chunk = assert(loadstring(BR_SRC, "=BugReport.lua"))
    chunk("ForeverSynthwave", FS)
    return FS, FS.BugReport
end

function LoadEL(FS)
    FS = FS or NewFS()
    ForeverSynthwaveErrorLog = {}
    local chunk = assert(loadstring(EL_SRC, "=ErrorLog.lua"))
    chunk("ForeverSynthwave", FS)
    return FS
end

OURS = "Interface\\AddOns\\ForeverSynthwave\\UnitFrames.lua:120: attempt to index nil"
FOREIGN = "Interface\\AddOns\\Details\\core.lua:33: attempt to call nil"
EXPECT_LINE = "Forever STUwave: error was thrown and logged (/fsbug to report)"

function ContainsSentinel(v, seen)
    if SENT[v] then return true end
    if realType(v) ~= "table" then return false end
    seen = seen or {}
    if seen[v] then return false end
    seen[v] = true
    for k, x in pairs(v) do
        if ContainsSentinel(k, seen) or ContainsSentinel(x, seen) then return true end
    end
    return false
end

function Has(s, sub) return s:find(sub, 1, true) ~= nil end
function CountOf(s, sub)
    local n, i = 0, 1
    while true do
        local a, b = s:find(sub, i, true)
        if not a then return n end
        n = n + 1; i = b + 1
    end
end
function Compact(BR, v, o)
    o = o or {}
    o.indent = false
    return BR.Encode(v, o)
end
"""

CASES: list[tuple[str, str, object]] = []


def case(name: str, body: str, check=None) -> None:
    """body is Lua that asserts. With `check`, body returns a string handed to a Python assertion."""
    CASES.append((name, body, check))


# ===========================================================================
# JSON encoder
# ===========================================================================

case("enc_scalars", """
    local _, BR = LoadBR()
    assert(Compact(BR, nil) == "null")
    assert(Compact(BR, true) == "true" and Compact(BR, false) == "false")
    assert(Compact(BR, 0) == "0" and Compact(BR, -3) == "-3" and Compact(BR, 1.5) == "1.5")
    assert(Compact(BR, "x") == '"x"')
    assert(Compact(BR, 3.0) == "3", "an integral float must not grow a decimal: " .. Compact(BR, 3.0))
    assert(Compact(BR, 0.1 + 0.2) == "0.3", Compact(BR, 0.1 + 0.2))
""")

case("enc_string_escapes", """
    local _, BR = LoadBR()
    assert(Compact(BR, 'a"b') == '"a\\\\"b"')
    assert(Compact(BR, "a\\\\b") == '"a\\\\\\\\b"')
    assert(Compact(BR, "l1\\nl2\\r\\t") == '"l1\\\\nl2\\\\r\\\\t"')
    assert(Compact(BR, "\\1\\31") == '"\\\\u0001\\\\u001f"', Compact(BR, "\\1\\31"))
    assert(Compact(BR, "a/b") == '"a/b"', "forward slash is not escaped")
    assert(Compact(BR, "|cff22e0ffhi|r") == '"|cff22e0ffhi|r"')
""")

case("enc_utf8_passes_and_invalid_bytes_are_escaped", """
    local _, BR = LoadBR()
    local ok = Compact(BR, "caf\\195\\169")           -- a valid two byte sequence
    assert(ok == '"caf\\195\\169"', ok)
    local bad = Compact(BR, "a\\255b")                -- a lone 0xff
    assert(bad == '"a\\\\u00ffb"', bad)
    assert(not bad:find("[\\128-\\255]"), "no raw high byte may survive an invalid sequence")
    local cut = Compact(BR, "a\\195")                 -- a truncated lead byte at the end
    assert(not cut:find("[\\128-\\255]"), cut)
""")

case("enc_nested_objects_have_sorted_keys", """
    local _, BR = LoadBR()
    local s = Compact(BR, { b = 1, a = { c = true, aa = "x" }, z = false })
    assert(s == '{"a":{"aa":"x","c":true},"b":1,"z":false}', s)
""")

case("enc_arrays", """
    local _, BR = LoadBR()
    assert(Compact(BR, { 1, 2, 3 }) == "[1,2,3]")
    assert(Compact(BR, { { a = 1 }, { b = { 2 } } }) == '[{"a":1},{"b":[2]}]')
    assert(Compact(BR, { "x", "y" }) == '["x","y"]')
""")

case("enc_empty_table_is_an_empty_array", """
    local _, BR = LoadBR()
    assert(Compact(BR, {}) == "[]")
    assert(Compact(BR, { a = {} }) == '{"a":[]}')
""")

case("enc_sparse_and_mixed_tables_are_objects", """
    local _, BR = LoadBR()
    assert(Compact(BR, { [1] = "a", [3] = "c" }) == '{"1":"a","3":"c"}', Compact(BR, { [1] = "a", [3] = "c" }))
    local m = Compact(BR, { "a", "b", x = 1 })
    assert(m == '{"1":"a","2":"b","x":1}', m)
""")

case("enc_nan_and_inf_never_emit_bare_tokens", """
    local _, BR = LoadBR()
    local nan, inf = 0 / 0, math.huge
    assert(Compact(BR, nan) == '"NaN"', Compact(BR, nan))
    assert(Compact(BR, inf) == '"inf"' and Compact(BR, -inf) == '"-inf"')
    local s = Compact(BR, { n = nan, list = { inf, -inf, nan } })
    assert(s == '{"list":["inf","-inf","NaN"],"n":"NaN"}', s)
""")

case("enc_cycles_terminate", """
    local _, BR = LoadBR()
    local t = { name = "root" }
    t.self = t
    local s = Compact(BR, t)
    assert(s == '{"name":"root","self":"<cycle>"}', s)
    local a, b = {}, {}
    a.b, b.a = b, a
    local s2 = Compact(BR, a)
    assert(Has(s2, "<cycle>"), s2)
    -- A table referenced twice without a cycle is not a cycle.
    local shared = { 1 }
    local s3 = Compact(BR, { x = shared, y = shared })
    assert(s3 == '{"x":[1],"y":[1]}', s3)
""")

case("enc_depth_cap", """
    local _, BR = LoadBR()
    local t = {}
    local cur = t
    for i = 1, 40 do cur.n = {}; cur = cur.n end
    local s = BR.Encode(t, { indent = false })
    assert(Has(s, "<depth>"), "deep nesting must be cut")
    assert(#s < 400, #s)
    local s2 = BR.Encode({ a = { b = { c = 1 } } }, { indent = false, maxDepth = 2 })
    assert(Has(s2, "<depth>"), s2)
""")

case("enc_item_cap_marks_the_rest", """
    local _, BR = LoadBR()
    local t = {}
    for i = 1, 200 do t[i] = i end
    local s = BR.Encode(t, { indent = false, maxItems = 10 })
    assert(s == "[1,2,3,4,5,6,7,8,9,10,\\"<+190 more>\\"]", s)
    local o = {}
    for i = 1, 100 do o["k" .. string.format("%03d", i)] = i end
    local s2 = BR.Encode(o, { indent = false, maxItems = 3 })
    assert(Has(s2, '"k001":1') and Has(s2, '"k003":3') and not Has(s2, '"k004"'), s2)
    assert(Has(s2, '"_truncated":97'), s2)
""")

case("enc_string_cap_and_utf8_boundary", """
    local _, BR = LoadBR()
    local s = BR.Encode(string.rep("x", 1000), { indent = false, maxString = 20 })
    assert(s == '"' .. string.rep("x", 20) .. '...(+980 chars)"', s)
    -- A multibyte character straddling the cap is dropped whole, not split.
    local e = string.rep("a", 19) .. "\\195\\169"      -- 19 ascii + e-acute = 21 bytes
    local out = BR.Encode(e, { indent = false, maxString = 20 })
    assert(not out:find("[\\128-\\255]"), "a split sequence must not leak: " .. out)
""")

case("enc_functions_and_threads_become_markers", """
    local _, BR = LoadBR()
    assert(Compact(BR, { f = print }) == '{"f":"<function>"}')
    assert(Compact(BR, coroutine.create(function() end)) == '"<thread>"')
""")

case("enc_node_budget_bounds_a_huge_table", """
    local _, BR = LoadBR()
    local t = {}
    for i = 1, 50 do
        t[i] = {}
        for j = 1, 50 do t[i][j] = { v = j } end
    end
    local s = BR.Encode(t, { indent = false, maxItems = 50, maxNodes = 300 })
    assert(Has(s, "<truncated>"), "node budget must trip")
    assert(#s < 12000, #s)
""")

case("enc_secrets_become_the_word_secret", """
    local _, BR = LoadBR()
    local s = Compact(BR, { n = SN, b = SB, s = SS, t = ST, list = { SN, SS } })
    assert(s == '{"b":"secret","list":["secret","secret"],"n":"secret","s":"secret","t":"secret"}', s)
    assert(Compact(BR, SN) == '"secret"')
""")

case("enc_secret_table_key_is_skipped_not_compared", """
    local _, BR = LoadBR()
    local t = { ok = 1 }
    t[SS] = 5
    local s = Compact(BR, t)
    assert(Has(s, '"ok":1'), s)
    assert(not Has(s, "SECRET"), s)
""")

case("enc_unreadable_table_is_marked", """
    local _, BR = LoadBR()
    -- A table whose key walk raises (what a secret table does in the real client).
    local bad = {}
    local realNext = next
    next = function(t, k)
        if t == bad then error("unreadable") end
        return realNext(t, k)
    end
    local s = Compact(BR, { x = bad })
    next = realNext
    assert(s == '{"x":"<unreadable>"}', s)
    -- A table with a throwing __index is still walked by next(), so it is simply empty.
    local odd = setmetatable({}, { __index = function() error("no") end })
    assert(Compact(BR, { x = odd }) == '{"x":[]}', Compact(BR, { x = odd }))
""")

case("enc_integers_at_or_above_2_pow_31_do_not_go_through_percent_d", """
    local _, BR = LoadBR()
    -- The client's Lua can format %d through a 32 bit int. Model that: any %d past 2^31 is garbage.
    local realFormat = string.format
    string.format = function(f, v, ...)
        if f == "%d" and realType(v) == "number" and math.abs(v) >= 2 ^ 31 then return "OVERFLOW" end
        return realFormat(f, v, ...)
    end
    local out = {
        Compact(BR, 2 ^ 31), Compact(BR, 2 ^ 32 + 5), Compact(BR, -2 ^ 33), Compact(BR, 2 ^ 40),
        Compact(BR, 1e14), Compact(BR, 2 ^ 31 - 1), Compact(BR, 0 * -1),
    }
    string.format = realFormat
    assert(out[1] == "2147483648", out[1])
    assert(out[2] == "4294967301", out[2])
    assert(out[3] == "-8589934592", out[3])
    assert(out[4] == "1099511627776", out[4])
    assert(out[5] == "100000000000000", out[5])
    assert(out[6] == "2147483647", out[6])
    assert(out[7] == "0", "negative zero must read 0: " .. out[7])
""")

case("enc_long_table_keys_are_capped", """
    local _, BR = LoadBR()
    local key = string.rep("k", 5000)
    local s = BR.Encode({ [key] = 1, short = 2 }, { indent = false, maxString = 20 })
    assert(s == '{"' .. string.rep("k", 20) .. '...(+4980 chars)":1,"short":2}', s:sub(1, 120))
    -- Under the default cap a 100 KB key cannot make a stored report 100 KB.
    local huge = BR.Encode({ [string.rep("z", 100000)] = true }, { indent = false })
    assert(#huge < 400, #huge)
    -- Capping must not merge two different short keys, and sorting still works.
    assert(Compact(BR, { b = 1, a = 2 }) == '{"a":2,"b":1}')
""")

def _roundtrip(text: str) -> None:
    value = json.loads(text)
    assert value["list"] == [1, 2, 3.5, "two\n\"q\"", {"deep": [True, False]}], value
    assert value["nan"] == "NaN" and value["inf"] == "inf"
    assert value["empty"] == []
    assert value["text"] == "café \\ / \t"
    assert value["cyc"] == {"back": "<cycle>"}


case("enc_pretty_output_is_valid_json", """
    local _, BR = LoadBR()
    local cyc = {}
    cyc.back = cyc
    return BR.Encode({
        list = { 1, 2, 3.5, 'two\\n"q"', { deep = { true, false } } },
        nan = 0 / 0, inf = math.huge, empty = {},
        text = "caf\\195\\169 \\\\ / \\t", cyc = cyc,
    })
""", _roundtrip)

case("enc_pretty_indents_two_spaces", """
    local _, BR = LoadBR()
    local s = BR.Encode({ a = { 1 } })
    assert(s == '{\\n  "a": [\\n    1\\n  ]\\n}', s)
""")

# ===========================================================================
# Secret safety of the snapshot
# ===========================================================================

case("build_with_every_api_secret_holds_no_sentinel", """
    local FS, BR = LoadBR({ mode = "secret" })
    ForeverSynthwaveDB = { petFrame = { x = SN }, label = SS }
    ForeverSynthwaveErrorLog = { { message = SS, stack = SS, count = SN, combat = SB, ours = true } }
    CreateFrame("Frame", "ForeverSynthwavePlayerFrame", UIParent)
    ForeverSynthwavePlayerFrame.GetWidth = function() return SN end
    ForeverSynthwavePlayerFrame.IsShown = function() return SB end
    local report = BR.Build("note")
    assert(not ContainsSentinel(report), "a sentinel leaked into the report")
    assert(report.client.build == "secret", tostring(report.client.build))
    assert(report.player.level == "secret" and report.player.classToken == "secret")
    assert(report.player.inCombat == "secret" and report.player.hasPet == "secret")
    assert(report.frames.ForeverSynthwavePlayerFrame.w == "secret")
    assert(report.frames.ForeverSynthwavePlayerFrame.shown == "secret")
    assert(report.settings.petFrame.x == "secret" and report.settings.label == "secret")
    assert(report.errors[1].message == "secret" and report.errors[1].count == "secret")
    BR.Encode(report)   -- and it still serialises
""")

case("build_secret_group_size_does_not_loop_on_a_secret", """
    local FS, BR = LoadBR({ mode = "secret" })
    local report = BR.Build()
    assert(report.group.size == "secret", tostring(report.group.size))
    assert(realType(report.group.byClass) == "table")
""")

case("build_fails_closed_when_issecretvalue_throws", """
    W.issecretThrows = true
    local FS, BR = LoadBR()
    local report = BR.Build("n")
    -- No value can be proven plain, so none is recorded.
    assert(report.player.level == "secret", tostring(report.player.level))
    assert(report.client.version == "secret")
    assert(report.player.class == "secret")
""")

case("build_survives_every_api_throwing", """
    local FS, BR = LoadBR({ mode = "throw" })
    local report = BR.Build("n")
    assert(report.player.level == "error", tostring(report.player.level))
    assert(report.client.build == "error")
    assert(realType(report.frames) == "table" and realType(report.addons) == "table")
    BR.Encode(report)
""")

case("build_survives_every_api_missing", """
    local FS, BR = LoadBR({ mode = "absent", noTheme = true })
    local report = BR.Build("n")
    assert(report.player.level == "unavailable", tostring(report.player.level))
    assert(report.addon.name == "ForeverSynthwave")
    assert(report.note == "n")
    BR.Encode(report)
""")

case("build_one_throwing_section_does_not_abort_the_report", """
    local FS, BR = LoadBR()
    -- A frame global whose members raise: the frames section throws, nothing else may.
    ForeverSynthwavePlayerFrame = setmetatable({}, { __index = function() error("frame boom") end })
    local r = BR.Build("n")
    assert(r.frames == "error", tostring(r.frames))
    assert(r.player.level == 70 and r.note == "n" and r.group.size == 0, "other sections survive")
    assert(realType(r.addons) == "table" and r.addonCount == 3)
    BR.Encode(r)
""")

case("build_a_throwing_addon_namespace_marks_only_its_sections", """
    local FS, BR = LoadBR()
    C_AddOns = setmetatable({}, { __index = function() error("C_AddOns boom") end })
    local r = BR.Build()
    assert(r.addon == "error", tostring(r.addon))
    assert(r.addons == "error" and r.addonCount == "error", tostring(r.addons))
    assert(r.client.build == "61234" and r.player.level == 70 and realType(r.frames) == "table")
    BR.Encode(r)
""")

case("build_final_pass_makes_whatever_an_api_returned_plain", """
    local FS, BR = LoadBR()
    local cyc = {}
    cyc.me = cyc
    GetZoneText = function() return print end          -- a function
    GetRealZoneText = function() return cyc end        -- a cyclic table
    UnitLevel = function() return 0 / 0 end            -- NaN
    local r = BR.Build()
    assert(r.location.zone == "<function>", tostring(r.location.zone))
    assert(realType(r.location.realZone) == "table" and r.location.realZone.me == "<cycle>")
    assert(r.player.level == "NaN", tostring(r.player.level))
""")

case("sanitize_turns_nan_and_inf_into_text", """
    local _, BR = LoadBR()
    local st = { nodes = 0, bytes = 0, maxDepth = 6, maxItems = 60, maxString = 200, maxNodes = 600, maxBytes = 100000 }
    assert(BR.Sanitize(0 / 0, st, 0, {}) == "NaN")
    assert(BR.Sanitize(math.huge, st, 0, {}) == "inf")
    assert(BR.Sanitize(-math.huge, st, 0, {}) == "-inf")
    assert(BR.Sanitize({ n = 0 / 0 }, st, 0, {}).n == "NaN")
""")

case("errors_section_scrubs_secret_fields_by_itself", """
    local _, BR = LoadBR()
    ForeverSynthwaveErrorLog = {
        { message = SS, stack = SS, count = SN, combat = SB, firstSeen = SS, lastSeen = SS, ours = true },
    }
    -- BR.Errors is called directly, so the final pass of Build cannot be what cleans it.
    local list, ours, other = BR.Errors()
    local e = list[1]
    for _, k in ipairs({ "message", "stack", "count", "combat", "firstSeen", "lastSeen" }) do
        assert(e[k] == "secret", k .. " = " .. tostring(realType(e[k])))
    end
    assert(not ContainsSentinel(list) and ours == 1 and other == 0)
""")

case("build_ui_frame_is_only_set_once_the_frame_fully_built", """
    local FS, BR = LoadBR()
    local real, n = CreateFrame, 0
    CreateFrame = function(...)
        n = n + 1
        if n == 3 then error("boom: third frame") end     -- the EditBox
        return real(...)
    end
    assert(not pcall(BR.ShowFrame, "x"), "a build failure must surface")
    CreateFrame = real
    assert(BR.GetFrame() == nil, "a half built frame must not be kept")
    local f = BR.ShowFrame("again")                        -- a later call builds from scratch
    assert(f:IsShown() and BR.GetEditBox():GetText() == "again")
""")

# ===========================================================================
# Snapshot content
# ===========================================================================

case("report_has_every_requested_field", """
    local FS, BR = LoadBR()
    ForeverSynthwaveDB = { petFrame = { x = 5 } }
    local r = BR.Build("my note")
    assert(r.addon.version == "0.1.0" and r.addon.name == "ForeverSynthwave")
    assert(r.client.version == "1.16.1" and r.client.build == "61234" and r.client.toc == 16001)
    assert(r.time.date:match("^%d%d%d%d%-%d%d%-%d%d %d%d:%d%d:%d%d$"), r.time.date)
    assert(realType(r.time.epoch) == "number")
    assert(r.player.classToken == "PALADIN" and r.player.class == "Paladin" and r.player.level == 70)
    assert(r.player.race == "Human" and r.player.spec == "Retribution")
    assert(r.player.inCombat == false and r.player.hasPet == true)
    assert(r.location.zone == "Shattrath City" and r.location.instanceType == "none")
    assert(r.display.uiScale == 0.64 and r.display.screenWidth == 2133.33 and r.display.screenHeight == 1200)
    assert(r.display.physicalWidth == 3413 and r.display.layoutScale == 0.5)
    assert(r.group.size == 0, tostring(r.group.size))     -- no group, no raid in the mock
    assert(r.note == "my note")
    assert(r.settings.petFrame.x == 5)
    assert(r.schema == 1 and realType(r.id) == "number")
""")

# ===========================================================================
# The /fsrecon class section (Diagnostics.lua hands its last run over through GetClassRecon)
# ===========================================================================

case("report_class_recon_section_carries_the_last_run", """
    local FS, BR = LoadBR()
    FS.Diagnostics = { GetClassRecon = function()
        return { token = "PALADIN", level = 12, spells = { { name = "Holy Light", id = 635, known = true } },
                 buffs = { status = "ok", count = 1, list = { { name = "Seal of Righteousness", spellId = 21084 } } } }
    end }
    local r = BR.Build()
    assert(r.classRecon.token == "PALADIN" and r.classRecon.spells[1].id == 635)
    assert(r.classRecon.buffs.list[1].spellId == 21084)
    assert(r.player.level == 70 and r.note == "", "other sections are untouched")
    local text = BR.Encode(r)
    assert(Has(text, '"classRecon"') and Has(text, "Holy Light"))
""")

case("report_class_recon_is_full_once_then_a_stub_until_the_next_run", """
    local FS, BR = LoadBR()
    local run, marks = nil, 0
    local function NewRun(taken)
        run = { token = "PALADIN", taken = taken, spells = { { name = "Holy Light", id = 635 } } }
    end
    FS.Diagnostics = {
        GetClassRecon = function() return run end,
        MarkClassReconReported = function() marks = marks + 1; run.reported = true end,
    }
    -- a report counts as sent only once /fsbug has shown it, so these go through the command
    local function Slash(note)
        SlashCmdList.FSBUG(note)
        local list = ForeverSynthwaveDB.bugreports
        return list[#list].classRecon
    end
    NewRun("2026-10-03 10:00:00")
    assert(BR.Build().classRecon.token == "PALADIN" and BR.Build().classRecon.token == "PALADIN",
        "Build alone never consumes the recon")
    assert(BR.Capture("peek").classRecon.token == "PALADIN" and BR.Capture("peek").classRecon.token == "PALADIN"
        and marks == 0, "neither does Capture")
    assert(Slash("one").spells[1].id == 635, "first report carries the full recon")
    assert(marks == 1 and run.reported == true)
    local stub = Slash("two")
    assert(stub.taken == "2026-10-03 10:00:00" and stub.note == "attached to an earlier report", stub.note)
    assert(stub.token == nil and stub.spells == nil, "the stub is small")
    assert(Slash("three").note == "attached to an earlier report")
    NewRun("2026-10-03 11:00:00")
    assert(Slash("four").token == "PALADIN", "a new run attaches again")
    assert(Slash("five").taken == "2026-10-03 11:00:00")
    -- an old run saved without a stamp still gets a stub that says so
    run.taken = nil
    assert(Slash("six").taken == "unknown")
""")

case("report_class_recon_is_not_consumed_when_the_command_fails_before_the_tester_has_it", """
    local FS, BR = LoadBR()
    local run, marks = { token = "PALADIN", taken = "2026-10-03 10:00:00", spells = { { name = "Holy Light", id = 635 } } }, 0
    FS.Diagnostics = {
        GetClassRecon = function() return run end,
        MarkClassReconReported = function() marks = marks + 1; run.reported = true end,
    }
    local function Last()
        local list = ForeverSynthwaveDB.bugreports
        return list[#list].classRecon
    end
    local store, show, fmt = BR.Store, BR.ShowFrame, string.format
    -- 1. Store throws: nothing was kept, nothing consumed, the tester is told
    BR.Store = function() error("store boom") end
    SlashCmdList.FSBUG("a")
    BR.Store = store
    assert(marks == 0 and run.reported == nil, "a failed Store consumed the run")
    assert(Has(table.concat(Lines(), "\\n"), "could not build"), table.concat(Lines(), "\\n"))
    -- 2. Serialize throws (the stored report was never shown)
    local armed = false
    BR.Store = function(r) local n = store(r); armed = true; return n end
    string.format = function(f, ...)
        if armed and f == "%.0f" then error("serialize boom") end
        return fmt(f, ...)
    end
    SlashCmdList.FSBUG("b")
    string.format, BR.Store = fmt, store
    assert(armed, "the Serialize failure was never reached")
    assert(marks == 0 and run.reported == nil, "a failed Serialize consumed the run")
    assert(Has(table.concat(Lines(), "\\n"), "bug report failed"), table.concat(Lines(), "\\n"))
    -- 3. the copy box throws
    BR.ShowFrame = function() error("show boom") end
    SlashCmdList.FSBUG("c")
    BR.ShowFrame = show
    assert(marks == 0 and run.reported == nil, "a failed copy box consumed the run")
    assert(Has(table.concat(Lines(), "\\n"), "copy box could not open"), table.concat(Lines(), "\\n"))
    -- 4. the real copy box refusing (a frame that cannot be built)
    W.frameThrows = true
    SlashCmdList.FSBUG("d")
    W.frameThrows = false
    assert(marks == 0 and run.reported == nil, "an unbuildable copy box consumed the run")
    -- the run is still full in every report stored so far, and the next good /fsbug takes it
    assert(Last().spells[1].id == 635)
    SlashCmdList.FSBUG("e")
    assert(marks == 1 and run.reported == true and Last().spells[1].id == 635, "the first good report carries and consumes it")
    SlashCmdList.FSBUG("f")
    assert(Last().note == "attached to an earlier report" and Last().spells == nil, "later reports carry the stub")
""")

case("report_class_recon_not_run_and_unavailable_markers", """
    local FS, BR = LoadBR()
    assert(BR.Build().classRecon == "unavailable", "no Diagnostics table")
    FS.Diagnostics = {}
    assert(BR.Build().classRecon == "unavailable", "no provider function")
    FS.Diagnostics = { GetClassRecon = function() return nil end }
    assert(BR.Build().classRecon == "not run", "a provider with nothing recorded")
    FS.Diagnostics = { GetClassRecon = function() return SS end }
    assert(BR.Build().classRecon == "secret", "a secret as the whole answer")
""")

case("report_class_recon_provider_that_throws_costs_only_its_section", """
    local FS, BR = LoadBR()
    FS.Diagnostics = { GetClassRecon = function() error("provider boom") end }
    local r = BR.Build("n")
    assert(r.classRecon == "error", tostring(r.classRecon))
    assert(r.player.level == 70 and r.note == "n" and realType(r.frames) == "table")
    BR.Encode(r)
    FS.Diagnostics = setmetatable({}, { __index = function() error("namespace boom") end })
    assert(BR.Build().classRecon == "error")
""")

case("report_class_recon_is_bounded_by_the_final_pass", """
    local FS, BR = LoadBR()
    local big = {}
    for i = 1, 500 do big[i] = { name = string.rep("n", 3000), spellId = i } end
    FS.Diagnostics = { GetClassRecon = function() return { list = big } end }
    local r = BR.Build()
    assert(#r.classRecon.list <= 201, #r.classRecon.list)
    assert(#BR.Encode(r) < 400000, #BR.Encode(r))
""")

case("report_class_recon_worst_case_payload_fits_the_report_without_truncation", """
    -- Checked on BR.Build()'s own output, which is what is stored and shown: BR.Encode runs a second,
    -- tighter pass (600 nodes) that the report never goes through.
    local FS, BR = LoadBR()
    local function long(prefix, i) return (prefix .. i .. string.rep("x", 60)):sub(1, 60) end
    local spells, hudKeys, ranked, buffs, debuffs, forms, tabs = {}, {}, {}, {}, {}, {}, {}
    for i = 1, 60 do
        spells[i] = { group = "blessings", name = long("Greater Blessing of Sanctuary ", i), id = 25000 + i, known = true,
            secrecy = 2, secrecyName = "ContextuallySecret" }
    end
    for i = 1, 40 do
        hudKeys[i] = { key = long("key_", i), name = long("Spell ", i), id = 1000 + i, known = true, secrecy = 0,
            secrecyName = "NeverSecret", dictId = 2000 + i }
        buffs[i] = { name = long("Buff ", i), spellId = i, duration = 30, left = 28.5, sourceUnit = long("unit", i),
            dispelName = long("Magic", i) }
    end
    for i = 1, 60 do
        ranked[i] = { tab = 3, id = i, node = i, spellId = i, name = long("Improved Blessing of Might ", i), rank = 5, maxRank = 5 }
    end
    for i = 1, 16 do
        debuffs[i] = { name = long("Judgement of Light ", i), spellId = i, duration = 20 }
    end
    for i = 1, 10 do forms[i] = { index = i, name = long("Form ", i), icon = 132000 + i, active = false, castable = true, spellId = i } end
    for i = 1, 5 do tabs[i] = { name = long("Retribution ", i), points = i } end
    local party = {}
    for _, u in ipairs({ "party1", "party2", "party3", "party4" }) do
        local list = {}
        for i = 1, 20 do list[i] = { name = long("Blessing of Might ", i), spellId = 19740 + i } end
        party[u] = { status = "ok", count = 20, list = list, capped = true }
    end
    local recon = {
        schema = 1, class = long("Paladin", 1), token = "PALADIN", level = 12, inCombat = false, spec = long("Spec", 1),
        taken = "2026-10-03 10:00:00", time = 5000,
        talents = { api = { GetTalentTabInfo = "ok", C_SpecializationInfo = "ok", GetSpecialization = "ok" }, tabs = tabs,
            specIndex = { C_SpecializationInfo = 3, GetSpecialization = 3 }, tabSource = "GetTalentTabInfo",
            ranks = { status = "ok", source = "C_SpecializationInfo.GetTalentInfo", list = ranked, capped = true, skipped = 3 } },
        forms = { count = 10, list = forms },
        spellApi = { info = "C_Spell.GetSpellInfo", secrecy = "C_Spell.GetSpellAuraSecrecy" },
        spells = spells,
        hud = { profile = true, token = "PALADIN", keys = hudKeys },
        buffs = { status = "ok", count = 40, list = buffs, capped = true },
        debuffs = { status = "ok", count = 16, list = debuffs, capped = true },
        party = party,
    }
    FS.Diagnostics = { GetClassRecon = function() return recon end }
    -- the other sections at their own caps too (ten errors at the message and stack caps, 80 addon names
    -- at the name cap), so the whole report is what has to fit the final pass, not the recon alone
    ForeverSynthwaveErrorLog = {}
    for i = 1, 10 do
        ForeverSynthwaveErrorLog[i] = { message = (long("err", i) .. string.rep("m", 300)):sub(1, BR.LIMITS.errMsg),
            stack = string.rep("s", BR.LIMITS.errStack), count = i, combat = false, ours = true, firstSeen = "t", lastSeen = "u" }
    end
    W.addons = {}
    for i = 1, BR.LIMITS.addons do W.addons[i] = { (long("Addon", i) .. string.rep("n", 40)):sub(1, BR.LIMITS.addonName), true } end
    local MARKERS = { "<truncated>", "more>", "...(+", "<depth>", "<cycle>", "<unreadable>" }
    local function Walk(v, path, seen)
        if realType(v) == "string" then
            for _, m in ipairs(MARKERS) do assert(not v:find(m, 1, true), "marker " .. m .. " at " .. path .. ": " .. v) end
        elseif realType(v) == "table" then
            assert(not seen[v], "cycle at " .. path)
            seen[v] = true
            assert(v._truncated == nil, "_truncated at " .. path)
            for k, x in pairs(v) do Walk(x, path .. "." .. tostring(k), seen) end
            seen[v] = nil
        end
    end
    local r = BR.Build()
    local c = r.classRecon
    assert(realType(c) == "table", tostring(c))
    Walk(c, "classRecon", {})
    assert(#c.spells == 60 and #c.hud.keys == 40 and #c.talents.ranks.list == 60 and #c.buffs.list == 40, "a list lost entries")
    assert(#c.debuffs.list == 16 and #c.forms.list == 10 and #c.talents.tabs == 5)
    for _, u in ipairs({ "party1", "party2", "party3", "party4" }) do assert(#c.party[u].list == 20, u) end
    assert(c.spells[60].name == long("Greater Blessing of Sanctuary ", 60) and c.talents.ranks.list[60].name:sub(1, 5) == "Impro")
    assert(not ContainsSentinel(r))
    -- and the rest of the report is not cut by the recon riding along
    Walk(r.frames, "frames", {})
    Walk(r.player, "player", {})
    assert(#r.errors == 10 and #r.addons == BR.LIMITS.addons, "errors or addons lost entries: " .. #r.errors .. " " .. #r.addons)
    Walk(r.errors, "errors", {})
    Walk(r.addons, "addons", {})
    -- the text the tester actually gets is that same data, serialised without a second pass
    SlashCmdList.FSBUG("worst case")
    local text = BR.GetEditBox():GetText()
    for _, m in ipairs(MARKERS) do assert(not Has(text, m), "marker " .. m .. " in the copy box text") end
    assert(Has(text, '"classRecon"') and Has(text, long("Greater Blessing of Sanctuary ", 60)))
""")

def _class_recon_json(text: str) -> None:
    section = json.loads(text).get("classRecon")
    assert isinstance(section, dict), section
    assert section["token"] == "PALADIN" and section["spells"][0]["id"] == 20271, section


case("report_class_recon_is_json_the_tester_can_send", """
    local FS, BR = LoadBR()
    FS.Diagnostics = { GetClassRecon = function()
        return { token = "PALADIN", spells = { { name = "Judgement", id = 20271 } } }
    end }
    return BR.Encode(BR.Build("x"))
""", _class_recon_json)

case("report_group_composition_by_class", """
    local FS, BR = LoadBR()
    W.group = { "PRIEST", "PALADIN", "WARRIOR" }
    local r = BR.Build()
    assert(r.group.inGroup == true and r.group.inRaid == false and r.group.size == 4)
    assert(r.group.byClass.PALADIN == 2 and r.group.byClass.PRIEST == 1 and r.group.byClass.WARRIOR == 1)
    W.group = {}
    W.raid = { "PALADIN", "PALADIN", "MAGE", "MAGE", "MAGE" }
    local r2 = BR.Build()
    assert(r2.group.inRaid == true and r2.group.size == 5)
    assert(r2.group.byClass.MAGE == 3 and r2.group.byClass.PALADIN == 2)
    W.raid = nil
    local solo = BR.Build()
    assert(solo.group.inGroup == false and solo.group.byClass.PALADIN == 1)
""")

case("report_combat_and_pet_flags", """
    local FS, BR = LoadBR()
    W.combat, W.pet = true, false
    local r = BR.Build()
    assert(r.player.inCombat == true and r.player.hasPet == false)
""")

case("report_instance_fields", """
    local FS, BR = LoadBR()
    W.inInstance, W.instType = true, "party"
    local r = BR.Build()
    assert(r.location.inInstance == true and r.location.instanceType == "party")
    assert(r.location.instanceName == "Karazhan" and r.location.instanceID == 532)
""")

case("report_frames_shown_hidden_size_absent", """
    local FS, BR = LoadBR()
    local a = CreateFrame("Frame", "ForeverSynthwavePlayerFrame", UIParent)
    a:SetSize(320.04, 92); a:Show()
    local b = CreateFrame("Frame", "ForeverSynthwaveXPBar", UIParent)
    b:SetSize(100, 8); b:Hide()
    local r = BR.Build()
    local p = r.frames.ForeverSynthwavePlayerFrame
    assert(p.shown == true and p.w == 320 and p.h == 92, "size is rounded: " .. tostring(p.w))
    local x = r.frames.ForeverSynthwaveXPBar
    assert(x.shown == false and x.w == 100 and x.h == 8)
    assert(r.frames.ForeverSynthwaveDeck == "absent")
    assert(#BR.FRAME_NAMES == 28, "the reported frame list changed: " .. #BR.FRAME_NAMES)
    local reported = 0
    for _ in pairs(r.frames) do reported = reported + 1 end
    assert(reported == #BR.FRAME_NAMES, "one entry per listed frame: " .. reported)
    for _, name in ipairs(BR.FRAME_NAMES) do assert(r.frames[name] ~= nil, name) end
""")

case("report_addons_lists_only_loaded_ones", """
    local FS, BR = LoadBR()
    local r = BR.Build()
    local seen = {}
    for _, name in ipairs(r.addons) do seen[name] = true end
    assert(seen.Details and seen["DBM-Core"] and seen.ForeverSynthwave and not seen.Unloaded)
    assert(r.addonCount == 3)
""")

case("report_addon_list_is_capped", """
    local FS, BR = LoadBR()
    W.addons = {}
    for i = 1, 500 do W.addons[i] = { "Addon" .. i, true } end
    local r = BR.Build()
    assert(#r.addons <= BR.LIMITS.addons + 1, #r.addons)
    assert(r.addonCount == 500)
""")

case("report_settings_exclude_bulky_logs_and_reports", """
    local FS, BR = LoadBR()
    ForeverSynthwaveDB = {
        petFrame = { x = 1 }, recon = { big = { 1, 2, 3 } }, reconSkins = {}, reconPos = {},
        fsprobe = { a = 1 }, fontProbe = {}, bugreports = { { id = 1 } }, bugreportSeq = 4,
        degradeLog = { k = { msg = "m" } },
    }
    local r = BR.Build()
    for _, k in ipairs({ "recon", "reconSkins", "reconPos", "fsprobe", "fontProbe", "bugreports", "bugreportSeq" }) do
        assert(r.settings[k] == nil, k .. " must not be copied")
    end
    assert(r.settings.petFrame.x == 1 and r.settings.degradeLog.k.msg == "m")
""")

case("report_carries_the_chat_seat_log_in_its_own_section", """
    local FS, BR = LoadBR()
    local log, prev = {}, { { ev = "old", t = 1, pt = "TOPLEFT", x = 0, y = 0 } }
    for i = 1, 20 do log[i] = { ev = "SetPoint", t = i, pt = "CENTER", x = i, y = -i, ui = 1200 } end
    ForeverSynthwaveDB = { petFrame = { x = 1 }, chatSeatLog = log, chatSeatLogPrev = prev }
    local r = BR.Build()
    assert(r.settings.chatSeatLog == nil and r.settings.chatSeatLogPrev == nil,
        "the logs must not ride in the generic settings copy")
    assert(r.settings.petFrame.x == 1)
    assert(#r.chatSeat.log == 20 and r.chatSeat.log[20].x == 20 and r.chatSeat.log[1].ev == "SetPoint")
    assert(#r.chatSeat.prev == 1 and r.chatSeat.prev[1].ev == "old")
    ForeverSynthwaveDB = {}
    local empty = BR.Build().chatSeat
    assert(type(empty) == "table" and empty.log == nil and empty.prev == nil, "no log yet")
    ForeverSynthwaveDB = nil
    assert(BR.Build().chatSeat == "unavailable", "no DB")
""")

case("report_carries_the_minimap_seat_log_in_its_own_section", """
    local FS, BR = LoadBR()
    local function make(n, ev)
        local log = {}
        for i = 1, n do
            log[i] = { ev = ev, t = i, pt = "TOP", x = 900 + i, y = 600 - i, clamp = false,
                mt = 1191.7, ml = 1900.8, tt = 1191.7, tl = 1900.8, sc = 0.833, ui = 1200, n = 2 }
        end
        return log
    end
    local log, prev, first = make(20, "compensate"), { { ev = "old", t = 1, pt = "TOP", x = 0, y = 0 } }, make(3, "first")
    ForeverSynthwaveDB = { petFrame = { x = 1 }, minimapSeatLog = log, minimapSeatLogPrev = prev, minimapSeatLogFirst = first }
    local r = BR.Build()
    assert(r.settings.minimapSeatLog == nil and r.settings.minimapSeatLogPrev == nil and r.settings.minimapSeatLogFirst == nil,
        "the logs must not ride in the generic settings copy")
    assert(r.settings.petFrame.x == 1)
    assert(#r.minimapSeat.log == 20 and r.minimapSeat.log[20].x == 920 and r.minimapSeat.log[1].ev == "compensate")
    assert(r.minimapSeat.log[20].clamp == false and r.minimapSeat.log[20].tl == 1900.8 and r.minimapSeat.log[20].n == 2)
    assert(#r.minimapSeat.prev == 1 and r.minimapSeat.prev[1].ev == "old")
    assert(#r.minimapSeat.first == 3 and r.minimapSeat.first[1].ev == "first", "the first-session slot is reported")
    assert(r.minimapSeat._truncated == nil, "full entries fit the budget with no truncation marker")
    assert(r.chatSeat.log == nil, "the chat section is not fed from the minimap log")

    -- the worst case: all three logs full, the longest event and point names the code can write
    local worst = function() return make(20, "rescale:EDIT_MODE_LAYOUTS_UPDATED") end
    local w1, w2, w3 = worst(), worst(), worst()
    for _, w in ipairs({ w1, w2, w3 }) do for _, e in ipairs(w) do e.pt = "BOTTOMRIGHT" end end
    ForeverSynthwaveDB = { minimapSeatLog = w1, minimapSeatLogPrev = w2, minimapSeatLogFirst = w3 }
    local m = BR.Build().minimapSeat
    assert(#m.log == 20 and #m.prev == 20 and #m.first == 20, "no log is cut in the worst case")
    assert(m.prev[20].ev == "rescale:EDIT_MODE_LAYOUTS_UPDATED" and m.first[20].pt == "BOTTOMRIGHT" and m._truncated == nil)
    assert(#BR.Encode(m) < 20000, "and the section stays small, got " .. #BR.Encode(m))

    local huge = {}
    for i = 1, 300 do huge[i] = { ev = string.rep("e", 200), pt = "TOP", x = i, y = i } end
    ForeverSynthwaveDB = { minimapSeatLog = huge, minimapSeatLogPrev = huge, minimapSeatLogFirst = huge }
    local big = BR.Build().minimapSeat
    assert(#big.log <= 26 and #big.prev <= 26 and #big.first <= 26, "an oversized log is cut to the item cap, got " .. #big.log)
    assert(#BR.Encode(big) < 12000, "and stays small, got " .. #BR.Encode(big))
    ForeverSynthwaveDB = {}
    local empty = BR.Build().minimapSeat
    assert(type(empty) == "table" and empty.log == nil and empty.prev == nil and empty.first == nil, "no log yet")
    ForeverSynthwaveDB = nil
    assert(BR.Build().minimapSeat == "unavailable", "no DB")
""")

case("report_settings_are_size_capped", """
    local FS, BR = LoadBR()
    local big = {}
    for i = 1, 400 do
        big["k" .. i] = { string.rep("x", 5000), { deep = { deeper = { deepest = { 1, 2, 3 } } } } }
    end
    ForeverSynthwaveDB = { huge = big, longString = string.rep("y", 100000) }
    local r = BR.Build()
    local s = BR.Encode(r)
    assert(#s < 80000, "settings must be bounded, got " .. #s)
    assert(r.settings._truncated ~= nil or r.settings.huge ~= nil, "the byte budget must have cut something")
    ForeverSynthwaveDB = { longString = string.rep("y", 100000) }
    assert(Has(BR.Build().settings.longString, "chars)"))
""")

case("report_note_is_capped_and_defaults_empty", """
    local FS, BR = LoadBR()
    assert(BR.Build().note == "")
    local r = BR.Build(string.rep("n", 5000))
    assert(#r.note <= BR.LIMITS.note + 30, #r.note)
    assert(Has(r.note, "chars)"))
""")

case("report_includes_last_ten_ours_with_caps", """
    local FS, BR = LoadBR()
    ForeverSynthwaveErrorLog = {}
    for i = 1, 15 do
        ForeverSynthwaveErrorLog[#ForeverSynthwaveErrorLog + 1] = {
            message = "err" .. i .. string.rep("m", 2000), stack = string.rep("s", 9000),
            count = i, combat = (i % 2 == 0), ours = true, firstSeen = "t", lastSeen = "u",
        }
    end
    ForeverSynthwaveErrorLog[#ForeverSynthwaveErrorLog + 1] = { message = "other", count = 1, ours = false }
    local r = BR.Build()
    assert(#r.errors == 10, #r.errors)
    assert(r.errors[10].count == 15 and r.errors[1].count == 6, "the LAST ten, oldest first")
    assert(#r.errors[1].message <= BR.LIMITS.errMsg + 30 and #r.errors[1].stack <= BR.LIMITS.errStack + 30)
    assert(r.errors[2].combat == true or r.errors[2].combat == false)
    assert(r.errorCount == 15 and r.otherErrorCount == 1)
""")

case("report_with_no_error_log_global", """
    local FS, BR = LoadBR()
    ForeverSynthwaveErrorLog = nil
    local r = BR.Build()
    assert(#r.errors == 0 and r.errorCount == 0)
""")

# ===========================================================================
# Storage
# ===========================================================================

case("store_keeps_the_last_twenty", """
    local FS, BR = LoadBR()
    ForeverSynthwaveDB = nil
    for i = 1, 25 do BR.Capture("n" .. i) end
    local list = ForeverSynthwaveDB.bugreports
    assert(#list == 20, #list)
    assert(list[1].note == "n6" and list[20].note == "n25", list[1].note)
    assert(list[20].id == 25 and list[1].id == 6)
""")

case("store_survives_a_corrupt_slot", """
    local FS, BR = LoadBR()
    ForeverSynthwaveDB = { bugreports = "junk" }
    BR.Capture("a")
    assert(realType(ForeverSynthwaveDB.bugreports) == "table" and #ForeverSynthwaveDB.bugreports == 1)
""")

case("stored_reports_do_not_nest_earlier_reports", """
    local FS, BR = LoadBR()
    local first
    for i = 1, 5 do first = BR.Capture("x") end
    local last = ForeverSynthwaveDB.bugreports[5]
    assert(last.settings.bugreports == nil)
    local one = #BR.Encode(ForeverSynthwaveDB.bugreports[1])
    local five = #BR.Encode(ForeverSynthwaveDB.bugreports[5])
    assert(five < one * 1.5 + 200, "report size must not grow with the stored count")
""")

case("stored_reports_hold_only_plain_values", """
    local FS, BR = LoadBR({ mode = "secret" })
    BR.Capture("x")
    assert(not ContainsSentinel(ForeverSynthwaveDB.bugreports))
    local function plain(v, seen)
        local t = realType(v)
        if t == "number" then assert(v == v and v ~= math.huge and v ~= -math.huge, "non-finite number stored") end
        assert(t == "string" or t == "number" or t == "boolean" or t == "table", t)
        if t == "table" then for k, x in pairs(v) do plain(k); plain(x) end end
    end
    plain(ForeverSynthwaveDB.bugreports)
""")

case("worst_case_twenty_reports_stay_bounded", """
    local FS, BR = LoadBR()
    W.addons = {}
    for i = 1, 400 do W.addons[i] = { "A" .. string.rep("n", 80) .. i, true } end
    local big = {}
    for i = 1, 300 do big["k" .. i] = { string.rep("x", 4000), { 1, 2, { 3, { 4, { 5 } } } } } end
    ForeverSynthwaveDB = { huge = big, [string.rep("K", 90000)] = 1 }
    ForeverSynthwaveErrorLog = {}
    for i = 1, 80 do
        ForeverSynthwaveErrorLog[i] = { message = string.rep("m", 3000), stack = string.rep("s", 9000), count = 9, ours = true }
    end
    for i = 1, 25 do BR.Capture(string.rep("n", 9000)) end
    local list = ForeverSynthwaveDB.bugreports
    assert(#list == 20)
    -- EncodeReports is what /fsbug all shows and what SavedVariables holds, with no second capping.
    local all = BR.EncodeReports(list)
    local one = #BR.EncodeReports({ list[20] })
    return #all .. " " .. one
""", lambda text: (
    lambda total, one: (
        # measured at the time of writing: about 42 KB per worst case report, 836 KB for twenty. The cap is a bound on a
        # stored report, not a loose ceiling: a regression that lets settings, errors or the addon
        # list grow past their limits moves these numbers.
        one < 50_000 or (_ for _ in ()).throw(AssertionError(f"one worst case report is {one} bytes"))
    ) and (
        total < 20 * 50_000 or (_ for _ in ()).throw(AssertionError(f"20 reports are {total} bytes"))
    ) and (
        total > 20 * one * 0.9 or (_ for _ in ()).throw(AssertionError(f"reports are not alike: {total} vs {one}"))
    )
)(*map(int, text.split())))

case("clear_wipes_reports_only", """
    local FS, BR = LoadBR()
    ForeverSynthwaveDB = { petFrame = { x = 1 } }
    BR.Capture("a"); BR.Capture("b")
    assert(BR.Clear() == 2)
    assert(#ForeverSynthwaveDB.bugreports == 0 and ForeverSynthwaveDB.petFrame.x == 1)
    assert(BR.Clear() == 0)
""")

# ===========================================================================
# Slash parsing and the command
# ===========================================================================

case("slash_is_registered", """
    local FS, BR = LoadBR()
    assert(SLASH_FSBUG1 == "/fsbug")
    assert(realType(SlashCmdList.FSBUG) == "function")
""")

case("slash_parsing", """
    local FS, BR = LoadBR()
    local function P(m) local a, n = BR.ParseArgs(m); return a, n end
    local a, n = P("");            assert(a == "capture" and n == "")
    a, n = P(nil);                 assert(a == "capture" and n == "")
    a, n = P("hello world");       assert(a == "capture" and n == "hello world")
    a, n = P("  spaced note  ");   assert(a == "capture" and n == "spaced note")
    a = P("all");                  assert(a == "all")
    a = P("  ALL ");               assert(a == "all")
    a = P("clear");                assert(a == "clear")
    a = P(" Clear  ");             assert(a == "clear")
    -- A note that merely starts with a keyword is a note.
    a, n = P("all my bars vanished"); assert(a == "capture" and n == "all my bars vanished")
    a, n = P("clear please");      assert(a == "capture" and n == "clear please")
""")

case("run_capture_stores_opens_the_box_and_prints_the_paths", """
    local FS, BR = LoadBR()
    SlashCmdList.FSBUG("bars gone")
    assert(#ForeverSynthwaveDB.bugreports == 1 and ForeverSynthwaveDB.bugreports[1].note == "bars gone")
    local f = ForeverSynthwaveBugReport
    assert(f and f:IsShown(), "the copy box must be open")
    local json = BR.GetEditBox():GetText()
    assert(Has(json, '"note": "bars gone"'), json:sub(1, 200))
    local text = table.concat(Lines(), "\\n")
    assert(Has(text, "WTF/Account/<ACCOUNT>/SavedVariables/ForeverSynthwave.lua"), text)
    assert(Has(text, "World of Warcraft\\\\_classic_beta_\\\\WTF\\\\Account\\\\<ACCOUNT>\\\\SavedVariables\\\\ForeverSynthwave.lua"), text)
    assert(Has(text, "/reload or logout"), text)
""")

case("run_all_shows_one_json_array", """
    local FS, BR = LoadBR()
    BR.Capture("one"); BR.Capture("two"); BR.Capture("three")
    SlashCmdList.FSBUG("all")
    local json = BR.GetEditBox():GetText()
    assert(json:sub(1, 1) == "[" and Has(json, '"note": "one"') and Has(json, '"note": "three"'))
    assert(#ForeverSynthwaveDB.bugreports == 3, "all must not store a new report")
""")

case("run_all_with_nothing_stored_says_so", """
    local FS, BR = LoadBR()
    SlashCmdList.FSBUG("all")
    local text = table.concat(Lines(), "\\n")
    assert(Has(text, "no bug reports"), text)
    assert(ForeverSynthwaveBugReport == nil or not ForeverSynthwaveBugReport:IsShown())
""")

case("run_clear", """
    local FS, BR = LoadBR()
    BR.Capture("a"); BR.Capture("b")
    SlashCmdList.FSBUG("clear")
    assert(#ForeverSynthwaveDB.bugreports == 0)
    assert(Has(table.concat(Lines(), "\\n"), "cleared 2"))
""")

case("run_all_and_clear_leave_the_class_recon_unmarked", """
    -- Only /fsbug itself, once the tester has the report, consumes the run. Showing the stored reports or
    -- deleting them is not "the tester has it", even when a stored report carries the full recon.
    local FS, BR = LoadBR()
    local run, marks = { token = "PALADIN", taken = "2026-10-03 10:00:00", spells = { { name = "Holy Light", id = 635 } } }, 0
    FS.Diagnostics = {
        GetClassRecon = function() return run end,
        MarkClassReconReported = function() marks = marks + 1; run.reported = true end,
    }
    BR.Capture("stored")
    assert(ForeverSynthwaveDB.bugreports[1].classRecon.token == "PALADIN", "the stored report carries the full recon")
    SlashCmdList.FSBUG("all")
    assert(BR.GetEditBox():GetText():find("Holy Light", 1, true), "all shows the stored report")
    assert(marks == 0 and run.reported == nil, "/fsbug all consumed the run")
    SlashCmdList.FSBUG("clear")
    assert(#ForeverSynthwaveDB.bugreports == 0)
    assert(marks == 0 and run.reported == nil, "/fsbug clear consumed the run")
    -- and the next /fsbug still carries it in full, then consumes it
    SlashCmdList.FSBUG("after")
    local list = ForeverSynthwaveDB.bugreports
    assert(list[#list].classRecon.token == "PALADIN" and marks == 1 and run.reported == true)
""")

case("run_never_throws_when_everything_fails", """
    local FS, BR = LoadBR({ mode = "throw" })
    W.frameThrows = true
    ForeverSynthwaveErrorLog = { { message = "x", ours = true } }
    SlashCmdList.FSBUG("note")
    assert(#ForeverSynthwaveDB.bugreports == 1, "the report is still stored")
    assert(Has(table.concat(Lines(), "\\n"), "SavedVariables"), "and the tester is still told where it is")
""")

case("run_opens_in_combat_with_nothing_secure", """
    local FS, BR = LoadBR()
    W.combat = true
    SlashCmdList.FSBUG("pull bug")
    local f = ForeverSynthwaveBugReport
    assert(f:IsShown())
    for _, fr in ipairs(__all) do
        assert(fr._tmpl == nil or not tostring(fr._tmpl):find("Secure") and not tostring(fr._tmpl):find("Protected"),
            "no secure template: " .. tostring(fr._tmpl))
        assert((fr._calls.SetAttribute or 0) == 0, "no attributes touched")
        assert((fr._calls.SetPassThroughButtons or 0) == 0)
    end
    assert(f._parent == UIParent)
    for _, p in ipairs(f._points) do
        assert(p[2] == UIParent or p[2] == nil, "anchored to UIParent only")
    end
""")

# ===========================================================================
# The copy box
# ===========================================================================

case("frame_builds_once_and_is_reused", """
    local FS, BR = LoadBR()
    local f1 = BR.ShowFrame("one")
    local count = #__all
    local f2 = BR.ShowFrame("two")
    assert(f1 == f2 and #__all == count, "second call must reuse the frame")
    assert(BR.GetEditBox():GetText() == "two")
    assert(ForeverSynthwaveBugReport == f1)
""")

case("frame_is_movable_clamped_dialog_strata_and_closes_on_escape_key", """
    local FS, BR = LoadBR()
    local f = BR.ShowFrame("x")
    assert(f._movable == true and f._clamped == true and f._strata == "DIALOG")
    assert(realType(f._scripts.OnDragStart) == "function" and realType(f._scripts.OnDragStop) == "function")
    local n = 0
    for _, name in ipairs(UISpecialFrames) do if name == "ForeverSynthwaveBugReport" then n = n + 1 end end
    assert(n == 1, "registered with the Escape stack exactly once")
    BR.ShowFrame("again")
    n = 0
    for _, name in ipairs(UISpecialFrames) do if name == "ForeverSynthwaveBugReport" then n = n + 1 end end
    assert(n == 1)
""")

case("frame_fills_the_editbox_and_shows_the_hint", """
    local FS, BR = LoadBR()
    local f = BR.ShowFrame('{ "a": 1 }')
    local eb = BR.GetEditBox()
    assert(eb._kind == "EditBox" and eb._multi == true)
    assert(eb:GetText() == '{ "a": 1 }')
    local hint
    for _, fr in ipairs(__all) do
        if fr._kind == "FontString" and fr._text == "Ctrl+A, Ctrl+C, paste into a .txt and send it" then hint = fr end
    end
    assert(hint, "hint text missing")
    assert(f._skinned ~= nil, "styled through Theme.SkinPanel")
""")

case("frame_has_a_close_button", """
    local FS, BR = LoadBR()
    local f = BR.ShowFrame("x")
    local close
    for _, fr in ipairs(__all) do
        if fr._kind == "Button" and fr._scripts.OnClick then close = fr end
    end
    assert(close, "Close button missing")
    local label
    for _, c in ipairs(close._children) do if c._text == "Close" then label = c end end
    assert(label, "button reads Close")
    close._scripts.OnClick(close)
    assert(f:IsShown() == false)
""")

case("a_build_that_throws_partway_leaves_no_visible_orphan_frame", """
    local FS, BR = LoadBR()
    local realCreate = CreateFrame
    CreateFrame = function(kind, ...)
        if kind == "EditBox" then error("boom: EditBox") end
        return realCreate(kind, ...)
    end
    assert(not pcall(BR.ShowFrame, "x"), "the build throws")
    CreateFrame = realCreate
    local orphan = _G.ForeverSynthwaveBugReport
    assert(orphan, "the half built frame exists")
    assert(orphan:IsShown() == false, "and is hidden, not left on screen")
""")

case("editbox_escape_closes_the_frame", """
    local FS, BR = LoadBR()
    local f = BR.ShowFrame("x")
    BR.GetEditBox()._scripts.OnEscapePressed(BR.GetEditBox())
    assert(f:IsShown() == false)
""")

case("editbox_click_selects_all", """
    local FS, BR = LoadBR()
    BR.ShowFrame("x")
    local eb = BR.GetEditBox()
    local before = eb._calls.HighlightText or 0
    eb._scripts.OnMouseUp(eb)
    assert((eb._calls.HighlightText or 0) > before, "click must highlight all")
    assert(eb._calls.SetFocus >= 1)
    before = eb._calls.HighlightText
    eb._scripts.OnEditFocusGained(eb)
    assert(eb._calls.HighlightText > before, "focus must highlight all")
""")

case("editbox_is_read_only", """
    local FS, BR = LoadBR()
    BR.ShowFrame("original")
    local eb = BR.GetEditBox()
    eb._text = "original plus typing"
    eb._scripts.OnTextChanged(eb, true)
    assert(eb:GetText() == "original", eb:GetText())
""")

case("scroll_child_height_follows_the_text", """
    local FS, BR = LoadBR()
    BR.ShowFrame("a\\nb")
    local small = BR.GetEditBox()._h
    local lines = {}
    for i = 1, 400 do lines[i] = "line" .. i end
    BR.ShowFrame(table.concat(lines, "\\n"))
    local tall = BR.GetEditBox()._h
    assert(tall > small and tall >= 400 * 10, tall)
""")

case("frame_builds_without_theme", """
    local FS, BR = LoadBR({ noTheme = true })
    local f = BR.ShowFrame("x")
    assert(f:IsShown() and BR.GetEditBox():GetText() == "x")
""")

case("frame_builds_when_theme_calls_throw", """
    local FS, BR = LoadBR()
    FS.Theme.SkinPanel = function() error("skin boom") end
    FS.Theme.SkinButton = function() error("skin boom") end
    FS.Theme.ApplyMono = function() error("skin boom") end
    local f = BR.ShowFrame("x")
    assert(f:IsShown())
""")

case("chat_lines_have_no_em_dash_and_use_the_addon_name", """
    local FS, BR = LoadBR()
    SlashCmdList.FSBUG("x"); SlashCmdList.FSBUG("clear"); SlashCmdList.FSBUG("all")
    for _, l in ipairs(Lines()) do
        assert(not l:find("\\226\\128\\148"), "em dash: " .. l)
        assert(l:find("^Forever STUwave: "), "line style: " .. l)
    end
""")

case("report_json_roundtrips_through_a_real_parser", """
    local FS, BR = LoadBR()
    W.group = { "PRIEST" }
    ForeverSynthwaveDB = { petFrame = { x = 5, bad = 0 / 0 }, label = "caf\\195\\169\\n\\"q\\"" }
    ForeverSynthwaveErrorLog = { { message = "boom\\nline2", stack = "a\\tb", count = 3, ours = true, combat = true } }
    BR.Capture("rt")
    return BR.EncodeReports(ForeverSynthwaveDB.bugreports)
""", lambda text: (
    lambda v: (
        v[0]["note"] == "rt"
        and v[0]["settings"]["petFrame"]["bad"] == "NaN"
        and v[0]["settings"]["label"] == 'café\n"q"'
        and v[0]["errors"][0]["message"] == "boom\nline2"
        and v[0]["player"]["classToken"] == "PALADIN"
    )
    or (_ for _ in ()).throw(AssertionError(text[:300]))
)(json.loads(text)))

# ===========================================================================
# Error capture (ErrorLog.lua)
# ===========================================================================

case("err_ours_is_logged_suppressed_and_announced_once", """
    local FS = LoadEL()
    __handler(OURS)
    assert(#__prevCalls == 0, "our error must not reach the previous handler (no popup)")
    local log = ForeverSynthwaveErrorLog
    assert(#log == 1)
    local e = log[1]
    assert(e.message == OURS and e.count == 1 and e.ours == true)
    assert(realType(e.stack) == "string" and e.stack ~= "")
    assert(realType(e.time) == "number" and e.firstSeen and e.lastSeen)
    assert(e.combat == false)
    local lines = Lines()
    assert(#lines == 1 and lines[1] == EXPECT_LINE, tostring(lines[1]))
""")

case("err_combat_flag_is_recorded", """
    local FS = LoadEL()
    W.combat = true
    InstallApis("plain")
    __handler(OURS)
    assert(ForeverSynthwaveErrorLog[1].combat == true)
""")

case("err_foreign_passes_through_untouched", """
    local FS = LoadEL()
    __handler(FOREIGN)
    assert(#__prevCalls == 1 and __prevCalls[1] == FOREIGN, "previous handler gets the original error")
    assert(#__printed == 0, "no chat line for somebody else's error")
    assert(ForeverSynthwaveErrorLog[1].ours == false)
""")

FOO = "Interface\\\\AddOns\\\\Blizzard_Foo\\\\Foo.lua"
MENUS = "Interface\\\\AddOns\\\\ForeverSynthwave\\\\Menus.lua"
DET = "Interface\\\\AddOns\\\\Details\\\\core.lua"

case("err_blizzard_message_with_our_frame_among_the_innermost_six_is_attributed", f"""
    local FS = LoadEL()
    -- Blizzard code we called threw: our frame is the 2nd frame of the stack.
    __stack = "{FOO}:10: in function `Bar'\\n{MENUS}:50: in function <...>\\n"
    __handler("{FOO}:10: taint")
    assert(#__prevCalls == 0 and #__printed == 1)
    assert(ForeverSynthwaveErrorLog[1].ours == true)
    -- [C] frames do not use up one of the six: Foo, [C], Foo, ours is still the third real frame.
    __stack = "{FOO}:11: in function `Bar'\\n[C]: in function `securecall'\\n{FOO}:20: in function `Baz'\\n{MENUS}:51: in function <...>\\n"
    __handler("{FOO}:11: taint")
    assert(#__prevCalls == 0 and ForeverSynthwaveErrorLog[2].ours == true)
""")

case("err_our_frame_at_position_four_to_six_under_a_blizzard_helper_is_ours", f"""
    local FS = LoadEL()
    for depth = 4, 6 do
        local frames = {{}}
        for i = 1, depth - 1 do frames[#frames + 1] = "{FOO}:" .. i .. ": in function `H" .. i .. "'" end
        frames[#frames + 1] = "{MENUS}:50: in function <...>"
        __stack = table.concat(frames, "\\n") .. "\\n"
        __handler("{FOO}:" .. (100 + depth) .. ": helper threw")
        assert(#__prevCalls == 0, "our frame at position " .. depth .. " must be ours")
        assert(ForeverSynthwaveErrorLog[#ForeverSynthwaveErrorLog].ours == true)
    end
    -- Position seven is too deep.
    local frames = {{}}
    for i = 1, 6 do frames[#frames + 1] = "{FOO}:" .. i .. ": in function `H" .. i .. "'" end
    frames[#frames + 1] = "{MENUS}:50: in function <...>"
    __stack = table.concat(frames, "\\n") .. "\\n"
    __handler("{FOO}:999: helper threw")
    assert(#__prevCalls == 1, "position seven is foreign")
""")

case("err_a_message_naming_another_addon_is_foreign_even_with_our_frame_in_the_stack", f"""
    local FS = LoadEL()
    -- A foreign hook nested under a Blizzard call we made: our frame is the 3rd real frame, but the
    -- message names the other addon's folder.
    __stack = "{DET}:5: in function `hook'\\n{FOO}:1: in function `A'\\n{MENUS}:50: in function <...>\\n"
    __handler("{DET}:5: attempt to index nil")
    assert(#__prevCalls == 1 and #__printed == 0, "foreign error must reach the previous handler")
    assert(ForeverSynthwaveErrorLog[1].ours == false)
    -- Same with a backslash-free path and with a taint report that names another addon.
    __handler("Interface/AddOns/Details/core.lua:6: attempt to call nil")
    assert(#__prevCalls == 2 and ForeverSynthwaveErrorLog[2].ours == false)
    __handler("attempt to compare a secret number value (tainted by 'Details') x")
    assert(#__prevCalls == 3 and #__printed == 0)
    -- A Blizzard folder in the message is not another addon.
    __handler("{FOO}:7: taint")
    assert(#__prevCalls == 3, "Blizzard folder falls through to the stack, which holds our frame")
""")

case("err_our_frame_deep_in_a_foreign_stack_passes_through", f"""
    local FS = LoadEL()
    -- A foreign hook (Blizzard message) with ours as the 7th real frame: too deep.
    __stack = "{FOO}:5: in function `hook'\\n{FOO}:1: in function `A'\\n{FOO}:2: in function `B'\\n{FOO}:3: in function `C'\\n{FOO}:4: in function `D'\\n{FOO}:6: in function `E'\\n{MENUS}:50: in function <...>\\n"
    __handler("{FOO}:5: attempt to index nil")
    assert(#__prevCalls == 1 and #__printed == 0, "foreign error must reach the previous handler")
    assert(ForeverSynthwaveErrorLog[1].ours == false)
    -- [C] frames do not count, but six real frames before ours is still too deep.
    __stack = "{FOO}:6: in function `hook'\\n[C]: in function `pcall'\\n{FOO}:1: in function `A'\\n{FOO}:2: in function `B'\\n{FOO}:3: in function `C'\\n{FOO}:4: in function `D'\\n{FOO}:8: in function `E'\\n{MENUS}:50: in function <...>\\n"
    __handler("{FOO}:6: attempt to call nil")
    assert(#__prevCalls == 2 and #__printed == 0 and ForeverSynthwaveErrorLog[2].ours == false)
""")

case("err_our_own_handler_frames_do_not_count_as_ours", """
    local FS = LoadEL()
    __stack = "Interface\\\\AddOns\\\\ForeverSynthwave\\\\ErrorLog.lua:80: in function <...>\\n[C]: in function `pcall'\\nInterface\\\\AddOns\\\\Details\\\\x.lua:1: in main chunk\\n"
    __handler(FOREIGN)
    assert(#__prevCalls == 1 and #__printed == 0)
""")

case("err_throttle_one_line_per_ten_seconds_with_a_count", """
    local FS = LoadEL()
    for i = 1, 50 do __handler(OURS) end
    assert(#__printed == 1, #__printed)
    assert(ForeverSynthwaveErrorLog[1].count == 50 and #ForeverSynthwaveErrorLog == 1)
    __now = __now + 5
    __handler(OURS)
    assert(#__printed == 1, "still inside the window")
    __now = __now + 6
    __handler(OURS)
    local lines = Lines()
    assert(#lines == 2, #lines)
    assert(lines[2] == EXPECT_LINE .. " (x51)", lines[2])
    __now = __now + 11
    __handler(OURS)
    assert(Lines()[3] == EXPECT_LINE, "a lone error carries no count: " .. tostring(Lines()[3]))
""")

case("err_throttle_covers_distinct_messages", """
    local FS = LoadEL()
    for i = 1, 5 do __handler("Interface\\\\AddOns\\\\ForeverSynthwave\\\\A.lua:" .. i .. ": e" .. i) end
    assert(#__printed == 1 and #ForeverSynthwaveErrorLog == 5)
""")

case("err_dedupe_by_message_and_first_stack_line", """
    local FS = LoadEL()
    -- A positioned message already pins the site: same text, one entry.
    __handler(OURS); __handler(OURS)
    assert(#ForeverSynthwaveErrorLog == 1 and ForeverSynthwaveErrorLog[1].count == 2)
    -- A message with no file:line is split by the first stack line.
    __stack = "Interface\\\\AddOns\\\\ForeverSynthwave\\\\A.lua:1: in function a\\n"
    __handler("boom")
    __stack = "Interface\\\\AddOns\\\\ForeverSynthwave\\\\B.lua:2: in function b\\n"
    __handler("boom")
    __handler("boom")
    assert(#ForeverSynthwaveErrorLog == 3, #ForeverSynthwaveErrorLog)
    assert(ForeverSynthwaveErrorLog[3].count == 2)
""")

case("err_repeats_do_not_rebuild_the_stack", """
    local FS = LoadEL()
    __handler(OURS)
    local before = __dsCalls
    for i = 1, 200 do __handler(OURS) end
    assert(__dsCalls == before, "a repeat must not call debugstack: " .. (__dsCalls - before))
    __handler(FOREIGN)
    local mid = __dsCalls
    for i = 1, 200 do __handler(FOREIGN) end
    assert(__dsCalls == mid, "a repeated foreign verdict is cached")
""")

case("err_passthrough_setting_forwards_our_errors_too", """
    local FS = LoadEL()
    ForeverSynthwaveDB = { errorPassthrough = true }
    __handler(OURS)
    assert(#__prevCalls == 1 and #ForeverSynthwaveErrorLog == 1 and #__printed == 1)
""")

case("err_a_failing_logger_never_throws_and_foreign_still_passes", """
    local FS = LoadEL()
    W.dsThrows = true
    print = function() error("chat boom") end
    local ok = pcall(__handler, OURS)
    assert(ok, "the handler must not throw")
    assert(#__prevCalls == 0, "recording worked, so ours is still suppressed")
    assert(ForeverSynthwaveErrorLog[1].message == OURS)
    ok = pcall(__handler, FOREIGN)
    assert(ok and __prevCalls[1] == FOREIGN)
""")

case("err_missing_error_handler_api_is_survivable", """
    geterrorhandler, seterrorhandler = nil, nil
    local FS = LoadEL()                  -- must not throw at load
    assert(realType(SlashCmdList.FSERR) == "function")
""")

case("err_gettime_failure_is_safe", """
    local FS = LoadEL()
    GetTime = function() error("no clock") end
    assert(pcall(__handler, OURS))
    assert(pcall(__handler, FOREIGN))
    assert(__prevCalls[1] == FOREIGN)
""")

case("err_secret_error_value_passes_through_and_is_never_read", """
    local FS = LoadEL()
    local ok = pcall(__handler, SS)
    assert(ok, "a secret error value must not raise")
    assert(#__prevCalls == 1 and __prevCalls[1] == SS)
    assert(#__printed == 0 and #ForeverSynthwaveErrorLog == 0)
""")

case("err_non_string_error_is_tolerated", """
    local FS = LoadEL()
    assert(pcall(__handler, { code = 5 }))
    assert(#__prevCalls == 1)
    assert(pcall(__handler, nil))
""")

case("err_a_handler_cycle_does_not_recurse", """
    local FS = LoadEL()
    local ours = __handler
    -- An error addon installs itself after us and chains back into whatever it replaced (us).
    local depth = 0
    __handler = function(err) depth = depth + 1; if depth < 50 then ours(err) end end
    Fire("PLAYER_LOGIN")                 -- we wrap it, so it is now our previous AND we are its previous
    local top = __handler
    assert(top == ours, "our wrapper is reinstalled over it")
    depth = 0
    assert(pcall(top, FOREIGN))
    assert(depth <= 2, "cycle must be cut: depth " .. depth)
    depth = 0
    assert(pcall(top, OURS))
""")

case("err_a_replaced_handler_is_rewrapped_at_login_and_chained", """
    local FS = LoadEL()
    local ours = __handler
    local bugCalls = {}
    local bug = function(err) bugCalls[#bugCalls + 1] = err end
    __handler = bug                      -- an error addon installs itself after us
    Fire("PLAYER_LOGIN")
    assert(__handler ~= bug and __handler ~= nil, "we wrap whatever is current")
    __handler(FOREIGN)
    assert(#bugCalls == 1 and bugCalls[1] == FOREIGN, "the other addon still sees foreign errors")
    __handler(OURS)
    assert(#bugCalls == 1, "ours is swallowed, not forwarded")
    assert(#ForeverSynthwaveErrorLog == 2)
    -- The timed re-check does not stack a second wrapper when nothing changed.
    local current = __handler
    RunTimers()
    assert(__handler == current)
""")

case("err_blocked_action_event_for_our_addon_is_logged_and_announced", """
    local FS = LoadEL()
    Fire("ADDON_ACTION_FORBIDDEN", "ForeverSynthwave", "SetPoint()")
    local e = ForeverSynthwaveErrorLog[1]
    assert(e and e.message == "ADDON_ACTION_FORBIDDEN: SetPoint()" and e.ours == true)
    assert(#__printed == 1 and Lines()[1] == EXPECT_LINE)
    Fire("ADDON_ACTION_BLOCKED", "ForeverSynthwave", "SetAttribute()")
    assert(#ForeverSynthwaveErrorLog == 2 and #__printed == 1, "shares the error throttle")
""")

case("err_blocked_action_event_for_another_addon_is_ignored", """
    local FS = LoadEL()
    Fire("ADDON_ACTION_FORBIDDEN", "Details", "SetPoint()")
    assert(#ForeverSynthwaveErrorLog == 0 and #__printed == 0)
""")

case("err_blocked_action_event_with_secret_args_is_safe", """
    local FS = LoadEL()
    assert(pcall(Fire, "ADDON_ACTION_FORBIDDEN", SS, SS))
    assert(#ForeverSynthwaveErrorLog == 0)
""")

case("err_foreign_log_is_capped_so_it_cannot_bury_ours", """
    local FS = LoadEL()
    for i = 1, 200 do __handler("Interface\\\\AddOns\\\\Other\\\\o.lua:" .. i .. ": e") end
    local foreign = #ForeverSynthwaveErrorLog
    assert(foreign <= 30, foreign)
    __handler(OURS)
    assert(ForeverSynthwaveErrorLog[#ForeverSynthwaveErrorLog].message == OURS)
""")

case("err_log_cap_is_eighty", """
    local FS = LoadEL()
    for i = 1, 200 do __handler("Interface\\\\AddOns\\\\ForeverSynthwave\\\\f.lua:" .. i .. ": e") end
    assert(#ForeverSynthwaveErrorLog == 80, #ForeverSynthwaveErrorLog)
""")

case("err_load_time_errors_survive_the_saved_variable_restore", """
    local FS = LoadEL()
    __handler(OURS)                                  -- thrown while our files load
    -- The client now injects last session's saved table over the global.
    ForeverSynthwaveErrorLog = { { message = "stale from last session", count = 9 } }
    Fire("ADDON_LOADED", "ForeverSynthwave")
    local log = ForeverSynthwaveErrorLog
    assert(#log == 1 and log[1].message == OURS, "stale gone, load-time error kept: " .. tostring(log[1] and log[1].message))
    -- A repeat after the restore still dedupes into the kept entry.
    __handler(OURS)
    assert(#ForeverSynthwaveErrorLog == 1 and ForeverSynthwaveErrorLog[1].count == 2)
""")

case("err_other_addons_loading_does_not_wipe_the_log", """
    local FS = LoadEL()
    Fire("ADDON_LOADED", "ForeverSynthwave")
    __handler(OURS)
    Fire("ADDON_LOADED", "Details")
    assert(#ForeverSynthwaveErrorLog == 1)
""")

case("fserr_clear_still_works", """
    local FS = LoadEL()
    __handler(OURS)
    SlashCmdList.FSERR("clear")
    assert(#ForeverSynthwaveErrorLog == 0)
    __handler(OURS)
    assert(#ForeverSynthwaveErrorLog == 1 and ForeverSynthwaveErrorLog[1].count == 1)
""")

case("bug_report_carries_the_captured_errors", """
    local FS = LoadEL()
    local _, BR = LoadBR({ FS = FS })
    W.combat = true
    InstallApis("plain")
    __handler(OURS); __handler(OURS); __handler(OURS)
    local r = BR.Build()
    assert(#r.errors == 1)
    local e = r.errors[1]
    assert(e.message == OURS and e.count == 3 and e.combat == true and realType(e.stack) == "string")
    assert(e.firstSeen and e.lastSeen)
""")


case("err_foreign_error_still_reaches_blizzards_handler_after_the_rewrap", """
    local FS = LoadEL()
    local ours = __handler
    local seen = {}
    -- A BugGrabber style handler that installs after us and chains to whatever it replaced (us).
    __handler = function(err) seen[#seen + 1] = err; ours(err) end
    Fire("PLAYER_LOGIN")                 -- we wrap it: it is now our previous, and its previous is us
    local top = __handler
    assert(top == ours, "our wrapper is reinstalled over it")
    top(FOREIGN)
    assert(#seen == 1 and seen[1] == FOREIGN, "the other addon sees it once")
    assert(#__prevCalls == 1 and __prevCalls[1] == FOREIGN,
        "Blizzard's handler must still get a foreign error: " .. #__prevCalls)
    top(OURS)
    assert(#__prevCalls == 1 and #seen == 1, "ours is still logged and suppressed")
    assert(#ForeverSynthwaveErrorLog == 2 and ForeverSynthwaveErrorLog[2].ours == true)
    -- And after the timed re-check too.
    RunTimers()
    top("Interface\\\\AddOns\\\\Details\\\\core.lua:99: later")
    assert(#__prevCalls == 2, #__prevCalls)
""")

case("err_the_passthrough_setting_reaches_blizzards_handler_after_the_rewrap", """
    local FS = LoadEL()
    local ours = __handler
    __handler = function(err) ours(err) end
    Fire("PLAYER_LOGIN")
    ForeverSynthwaveDB = { errorPassthrough = true }
    __handler(OURS)
    assert(#__prevCalls == 1 and __prevCalls[1] == OURS, #__prevCalls)
""")

case("err_full_log_still_passes_foreign_messages_through_without_a_stack_when_they_name_their_addon", """
    local FS = LoadEL()
    for i = 1, 80 do __handler("Interface\\\\AddOns\\\\ForeverSynthwave\\\\f.lua:" .. i .. ": e") end
    assert(#ForeverSynthwaveErrorLog == 80)
    local before = __dsCalls
    for i = 1, 50 do __handler("Interface\\\\AddOns\\\\Other\\\\o.lua:" .. i .. ": e") end
    assert(__dsCalls == before, "a message naming another addon needs no debugstack: " .. (__dsCalls - before))
    assert(#__prevCalls == 50, "they all still reach the previous handler: " .. #__prevCalls)
    assert(#ForeverSynthwaveErrorLog == 80)
""")

case("err_full_log_suppresses_our_error_seen_only_in_its_stack_counts_it_and_says_so_once", """
    local FS = LoadEL()
    for i = 1, 80 do __handler("Interface\\\\AddOns\\\\ForeverSynthwave\\\\f.lua:" .. i .. ": e") end
    assert(#ForeverSynthwaveErrorLog == 80)
    local printedBefore = #__printed
    local callsBefore = #__prevCalls
    __now = __now + 30
    __stack = "Interface\\\\AddOns\\\\Blizzard_Foo\\\\Foo.lua:10: in function `Bar'\\nInterface\\\\AddOns\\\\ForeverSynthwave\\\\Menus.lua:50: in function <...>\\n"
    for i = 1, 5 do __handler("Interface\\\\AddOns\\\\Blizzard_Foo\\\\Foo.lua:" .. (200 + i) .. ": taint") end
    assert(#__prevCalls == callsBefore, "ours never reaches the popup path while the log is full")
    assert(#ForeverSynthwaveErrorLog == 80)
    assert(FS.ErrorLogDropped == 5, tostring(FS.ErrorLogDropped))
    local lines = Lines()
    assert(#lines == printedBefore + 1, "one throttled chat line: " .. (#lines - printedBefore))
    assert(lines[#lines] == "Forever STUwave: error log full, /fserr clear", lines[#lines])
    SlashCmdList.FSERR("clear")
    assert(FS.ErrorLogDropped == 0)
""")

case("err_own_name_must_be_anchored_a_lookalike_folder_or_a_mentioned_global_is_not_ours", f"""
    local FS = LoadEL()
    -- Another addon whose folder merely starts with our name, with our frame nowhere in the stack.
    __stack = "{DET}:1: in function `hook'\\n"
    __handler("Interface\\\\AddOns\\\\ForeverSynthwaveX\\\\a.lua:1: boom")
    assert(#__prevCalls == 1 and ForeverSynthwaveErrorLog[1].ours == false, "lookalike folder is foreign")
    -- A foreign message that only mentions our SavedVariable global.
    __handler("{DET}:2: attempt to index global 'ForeverSynthwaveDB' (a nil value)")
    assert(#__prevCalls == 2 and ForeverSynthwaveErrorLog[2].ours == false, "bare ForeverSynthwaveDB is not ours")
    -- Same with no path at all.
    __handler("attempt to index global 'ForeverSynthwaveDB' (a nil value)")
    assert(#__prevCalls == 3 and ForeverSynthwaveErrorLog[3].ours == false, "bare mention, foreign stack")
    assert(#__printed == 0)
""")

case("err_a_lookalike_addon_frame_in_the_stack_is_foreign", f"""
    local FS = LoadEL()
    -- A Blizzard-named message (so the stack decides) whose innermost frame is in a folder that only
    -- starts with our name: not ours.
    local LOOK = "Interface\\\\AddOns\\\\ForeverSynthwaveX\\\\a.lua"
    __stack = LOOK .. ":1: in function `hook'\\n{FOO}:2: in function `A'\\n"
    __handler("{FOO}:5: attempt to index nil")
    assert(#__prevCalls == 1 and #__printed == 0, "lookalike frame must reach the previous handler")
    assert(ForeverSynthwaveErrorLog[1].ours == false, "lookalike frame is foreign")
    -- Same with forward slashes and unusual case.
    __stack = "interface/addons/foreversynthwavex/b.lua:1: in function `hook'\\n"
    __handler("{FOO}:6: attempt to index nil")
    assert(#__prevCalls == 2 and ForeverSynthwaveErrorLog[2].ours == false, "lookalike frame, slashes and case")
    -- A real frame of ours behind the lookalike still counts.
    __stack = LOOK .. ":1: in function `hook'\\n{MENUS}:50: in function <...>\\n"
    __handler("{FOO}:7: attempt to index nil")
    assert(#__prevCalls == 2 and ForeverSynthwaveErrorLog[3].ours == true, "our real frame still counts")
""")

case("err_own_name_anchored_forms_are_ours_without_reading_the_stack", f"""
    local FS = LoadEL()
    __stack = "{DET}:1: in function `hook'\\n"       -- a foreign stack must not matter
    __handler("Interface\\\\AddOns\\\\ForeverSynthwave\\\\Foo.lua:5: boom")
    __handler("Interface/AddOns/ForeverSynthwave/Bar.lua:6: boom")
    __handler("attempt to compare a secret number value (tainted by 'ForeverSynthwave') x")
    __handler("blocked: AddOn 'ForeverSynthwave' tried a protected call")
    __handler("ForeverSynthwave/Baz.lua:7: boom")
    __handler("ForeverSynthwave\\\\Qux.lua:8: boom")
    assert(#__prevCalls == 0, "all six are ours and suppressed: " .. #__prevCalls)
    assert(#ForeverSynthwaveErrorLog == 6)
    for i = 1, 6 do assert(ForeverSynthwaveErrorLog[i].ours == true, i) end
""")

case("err_a_client_truncated_path_or_a_bracketed_chunk_is_ours", f"""
    local FS = LoadEL()
    -- The client cuts a long chunk path to `...` plus its last ~52 characters, so `AddOns/` can be lost.
    __stack = "{DET}:1: in function `hook'\\n"       -- a foreign stack must not matter for a message
    __handler("...ddOns/ForeverSynthwave/LongName.lua:12: boom")
    __handler("...ddOns\\\\ForeverSynthwave\\\\LongName.lua:13: boom")
    __handler("...DDONS/FOREVERSYNTHWAVE/LongName.lua:14: boom")
    -- A string chunk named after our file: the folder follows a quote, not a path separator.
    __handler('[string "ForeverSynthwave/X.lua"]:15: boom')
    assert(#__prevCalls == 0, "all four are ours and suppressed: " .. #__prevCalls)
    assert(#ForeverSynthwaveErrorLog == 4)
    for i = 1, 4 do assert(ForeverSynthwaveErrorLog[i].ours == true, i) end
    -- The same forms as stack frames behind a Blizzard-named message.
    local n = #ForeverSynthwaveErrorLog
    __stack = "{FOO}:1: in function `A'\\n...ddOns/ForeverSynthwave/LongName.lua:12: in function <...>\\n"
    __handler("{FOO}:20: attempt to index nil")
    __stack = '{FOO}:1: in function `A\\'\\n[string "ForeverSynthwave/X.lua"]:5: in function <...>\\n'
    __handler("{FOO}:21: attempt to index nil")
    assert(#__prevCalls == 0, "both frames are ours: " .. #__prevCalls)
    assert(ForeverSynthwaveErrorLog[n + 1].ours == true and ForeverSynthwaveErrorLog[n + 2].ours == true)
    -- A lookalike folder stays foreign in the truncated and bracketed forms, message and frame.
    __stack = "{DET}:1: in function `hook'\\n"
    __handler("...ddOns/ForeverSynthwaveX/LongName.lua:12: boom")
    __handler('[string "ForeverSynthwaveX/X.lua"]:5: boom')
    assert(#__prevCalls == 2, "lookalike messages are foreign: " .. #__prevCalls)
    __stack = "...ddOns/ForeverSynthwaveX/LongName.lua:12: in function `hook'\\n"
    __handler("{FOO}:30: attempt to index nil")
    assert(#__prevCalls == 3 and ForeverSynthwaveErrorLog[#ForeverSynthwaveErrorLog].ours == false, "lookalike frame")
""")

case("err_folder_and_taint_patterns_match_case_insensitively", f"""
    local FS = LoadEL()
    __stack = "{FOO}:1: in function `A'\\n{MENUS}:50: in function <...>\\n"   -- ours is in the stack
    -- Another addon's folder, written with unusual case, still names that addon: foreign.
    __handler("interface\\\\addons\\\\details\\\\core.lua:5: attempt to index nil")
    __handler("INTERFACE/ADDONS/DETAILS/core.lua:6: attempt to index nil")
    __handler("attempt to compare a secret number value (TAINTED BY 'Details') x")
    assert(#__prevCalls == 3 and #__printed == 0, "foreign despite our frame in the stack: " .. #__prevCalls)
    -- A Blizzard folder in any case is Blizzard code, so the stack decides (ours).
    __handler("interface\\\\addons\\\\blizzard_foo\\\\Foo.lua:7: taint")
    __handler("attempt to compare (tainted by 'BLIZZARD_Foo') y")
    assert(#__prevCalls == 3, "Blizzard folder, any case, falls through to the stack")
    -- Our own folder and taint name in any case are ours with no stack.
    __stack = "{DET}:1: in function `hook'\\n"
    __handler("INTERFACE\\\\ADDONS\\\\FOREVERSYNTHWAVE\\\\x.lua:8: boom")
    __handler("attempt to compare (tainted by 'FOREVERSYNTHWAVE') z")
    assert(#__prevCalls == 3 and ForeverSynthwaveErrorLog[#ForeverSynthwaveErrorLog].ours == true)
""")

case("err_full_log_line_has_its_own_throttle_and_does_not_inflate_the_standard_count", """
    local FS = LoadEL()
    for i = 1, 80 do __handler("Interface\\\\AddOns\\\\ForeverSynthwave\\\\f.lua:" .. i .. ": e") end
    __now = __now + 30
    __handler("Interface\\\\AddOns\\\\ForeverSynthwave\\\\f.lua:1: e")      -- flush the standard line
    assert(Lines()[#Lines()] == EXPECT_LINE .. " (x80)", Lines()[#Lines()])
    local FULL = "Forever STUwave: error log full, /fserr clear"
    __now = __now + 1                                                   -- still inside the standard window
    __stack = "Interface\\\\AddOns\\\\Blizzard_Foo\\\\Foo.lua:10: in function `Bar'\\nInterface\\\\AddOns\\\\ForeverSynthwave\\\\Menus.lua:50: in function <...>\\n"
    __handler("Interface\\\\AddOns\\\\Blizzard_Foo\\\\Foo.lua:201: taint")
    assert(Lines()[#Lines()] == FULL, "a standard line must not silence the full line: " .. tostring(Lines()[#Lines()]))
    local n = #Lines()
    for i = 2, 5 do __handler("Interface\\\\AddOns\\\\Blizzard_Foo\\\\Foo.lua:" .. (200 + i) .. ": taint") end
    assert(#Lines() == n, "the full line has its own 10s throttle")
    __now = __now + 11
    __handler("Interface\\\\AddOns\\\\ForeverSynthwave\\\\f.lua:2: e")      -- one repeat of a stored error
    assert(Lines()[#Lines()] == EXPECT_LINE, "dropped errors must not leak into the (xN): " .. tostring(Lines()[#Lines()]))
    __now = __now + 11
    __handler("Interface\\\\AddOns\\\\Blizzard_Foo\\\\Foo.lua:300: taint")
    assert(Lines()[#Lines()] == FULL, "and it speaks again after its own window")
""")

case("err_a_bare_message_ours_in_the_stack_is_suppressed_when_the_log_is_full", """
    local FS = LoadEL()
    for i = 1, 80 do __handler("Interface\\\\AddOns\\\\ForeverSynthwave\\\\f.lua:" .. i .. ": e") end
    __stack = "Interface\\\\AddOns\\\\ForeverSynthwave\\\\A.lua:1: in function a\\n"
    __handler("boom")
    assert(#__prevCalls == 0 and FS.ErrorLogDropped == 1)
""")

case("err_a_positioned_blizzard_message_is_attributed_by_the_stack_each_time_not_by_a_cached_false", """
    local FS = LoadEL()
    local MSG = "Interface\\\\AddOns\\\\Blizzard_Foo\\\\Foo.lua:10: taint"
    __stack = "Interface\\\\AddOns\\\\Blizzard_Foo\\\\Foo.lua:10: in function `Bar'\\n"
    __handler(MSG)
    assert(#__prevCalls == 1 and ForeverSynthwaveErrorLog[1].ours == false)
    -- The same text thrown again, now from our code: the stack decides, no cached false.
    __stack = "Interface\\\\AddOns\\\\Blizzard_Foo\\\\Foo.lua:10: in function `Bar'\\nInterface\\\\AddOns\\\\ForeverSynthwave\\\\Menus.lua:50: in function <...>\\n"
    __handler(MSG)
    assert(#__prevCalls == 1, "second throw is ours, so suppressed")
    -- Record dedupes it into the first entry; the verdict itself must have been ours.
    assert(#__printed == 1, "and announced")
""")

case("err_a_nil_stack_never_caches_a_verdict", """
    local FS = LoadEL()
    local MSG = "Interface\\\\AddOns\\\\Blizzard_Foo\\\\Foo.lua:10: taint"
    W.dsThrows = true
    __handler(MSG)
    assert(#__prevCalls == 1)
    W.dsThrows = false
    __stack = "Interface\\\\AddOns\\\\Blizzard_Foo\\\\Foo.lua:10: in function `Bar'\\nInterface\\\\AddOns\\\\ForeverSynthwave\\\\Menus.lua:50: in function <...>\\n"
    __handler(MSG)
    assert(#__prevCalls == 1 and #__printed == 1, "decided by the stack the second time")
""")

case("err_one_foreign_error_is_delivered_exactly_once_when_the_base_handler_chains_back_into_us", """
    local seen = 0
    __handler = function(err)
        seen = seen + 1
        if seen == 1 then __handler(err) end      -- the base handler calls whatever is current (us)
    end
    local FS = LoadEL()
    assert(pcall(__handler, FOREIGN))
    assert(seen == 1, "one foreign error, one delivery: " .. seen)
""")

case("err_a_bare_message_verdict_is_not_cached", """
    local FS = LoadEL()
    __stack = "Interface\\\\AddOns\\\\Blizzard_Foo\\\\Foo.lua:10: in function `Bar'\\n"
    __handler("boom")
    assert(#__prevCalls == 1 and ForeverSynthwaveErrorLog[1].ours == false)
    -- The same text with no file:line, thrown from our code this time: the stack decides, not a cache.
    __stack = "Interface\\\\AddOns\\\\ForeverSynthwave\\\\A.lua:1: in function a\\n"
    __handler("boom")
    assert(#__prevCalls == 1, "now ours, so suppressed")
    assert(#ForeverSynthwaveErrorLog == 2 and ForeverSynthwaveErrorLog[2].ours == true)
""")

case("err_a_secret_stack_is_never_read", """
    local FS = LoadEL()
    __stack = SS
    assert(pcall(__handler, OURS))
    assert(#__prevCalls == 0, "ours is still logged and suppressed when the stack is secret")
    assert(#ForeverSynthwaveErrorLog == 1 and ForeverSynthwaveErrorLog[1].stack == "(stack unavailable)")
    assert(pcall(__handler, FOREIGN))
    assert(#__prevCalls == 1 and #ForeverSynthwaveErrorLog == 2 and ForeverSynthwaveErrorLog[2].ours == false)
""")

case("err_a_noisy_neighbour_allocates_nothing_per_throw", """
    __prev = function() end
    __handler = __prev
    local FS = LoadEL()
    for i = 1, 40 do __handler("Interface\\\\AddOns\\\\Other\\\\o.lua:" .. i .. ": e") end   -- past the foreign cap
    local msgs = {}
    for i = 1, 2000 do msgs[i] = "Interface\\\\AddOns\\\\Other\\\\o.lua:" .. (1000 + i) .. ": e" end
    collectgarbage("collect")
    collectgarbage("stop")
    local before = collectgarbage("count")
    for i = 1, 2000 do __handler(msgs[i]) end
    local grown = collectgarbage("count") - before
    collectgarbage("restart")
    assert(grown < 40, "2000 distinct foreign throws allocated " .. math.floor(grown) .. " KB")
""")

case("err_a_throwing_classifier_cannot_wedge_the_wrapper", """
    local FS = LoadEL()
    local realFind = string.find
    string.find = function() error("find boom") end       -- Classify and Record both use it
    local ok = pcall(__handler, FOREIGN)
    string.find = realFind
    assert(ok, "the wrapper must not throw into the client")
    assert(#__prevCalls == 1 and __prevCalls[1] == FOREIGN, "the error still reaches the previous handler")
    __handler(OURS)                                       -- and busy was released, so this is handled
    assert(#ForeverSynthwaveErrorLog == 1 and #__prevCalls == 1)
""")


def run_case(name: str, body: str, check) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.globals().BR_SRC = BR_SRC
    rt.globals().EL_SRC = EL_SRC
    try:
        rt.execute(MOCK)
        result = rt.execute("local function main()\n" + body + "\nend\nreturn main()")
        if check is not None:
            if isinstance(result, bytes):
                result = result.decode("utf-8")
            check(result)
    except (LuaError, AssertionError, ValueError) as exc:
        return str(exc)
    return None


def main() -> int:
    failures = 0
    for name, body, check in CASES:
        err = run_case(name, body, check)
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}: {err}")
    print(f"{len(CASES) - failures}/{len(CASES)} checks passed")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
