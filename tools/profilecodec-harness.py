#!/usr/bin/env python3
"""Runs the real ProfileCodec.lua, Config.lua, ConfigShare.lua and the config window headless to pin profile export and import
(ticket B4).

What is pinned here:

  * the format: "STUW1C:" is C_EncodingUtil (SerializeCBOR, CompressString, EncodeBase64), "STUW1L:" is the in-house Lua codec
    (a plain table serializer, a checksum and base64); export takes C only when every function exists, checks the round trip
    and falls back to the Lua codec otherwise; import reads both prefixes whichever this client can decode;
  * a round trip, export then import, gives back the source for both codecs and for all three Share choices (All, Settings,
    Layout); module switches ride along on every export when ModuleSwitch exists;
  * every bad string gets its one reason (not a STUwave string, made by a newer STUwave, damaged, this client cannot read it);
    whitespace and surrounding words are tolerated; one wrong character or a cut string is damaged;
  * validation: unknown keys, wrong types, unknown options, odd text, non finite numbers, unknown frame ids and unknown module
    keys are dropped; numbers outside a row's min and max (read from the config rows) are clamped; and nothing is ever run from
    a string (load, loadstring, dofile and friends are trapped, and the source is scanned for them);
  * a 200 KB paste of any shape comes back at once without an error;
  * Config.GetDefault and Config.ImportProfile: a new profile only, never over another, no switch, no callback;
  * the // SHARE section of the Profiles page and both dialogs: the export box opens focused with every character selected and
    no letter limit, the Share choice changes the string and the line, the import box parses on every change and shows the
    line or one pink reason, Save as is made unique and checked, the button is off until the string and the name are fine,
    the modules checkbox, the note about what was skipped or adjusted, and nothing is switched to the new profile;
  * the changed marker's ? tip says "Changed. Default: <value>".

The encoding API and ModuleSwitch are mocks, and the frames are a recording mock: whether the real C_EncodingUtil round trip
holds, the box's line height and the look of the dialogs are client checks.

    python3 tools/profilecodec-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
# The *_LUA variables point the harness at a mutant copy (a check must fail on a broken one).
CODEC_FILE = Path(os.environ.get("PROFILECODEC_LUA", ADDON / "Core/ProfileCodec.lua"))
SHARE_FILE = Path(os.environ.get("CONFIGSHARE_LUA", ADDON / "Modules/Config/ConfigShare.lua"))
CONFIG_FILE = Path(os.environ.get("CONFIG_LUA", ADDON / "Core/Config.lua"))
WINDOW_PARTS = ("ConfigSpec.lua", "ConfigWindow.lua", "ConfigBuilders.lua", "ConfigPageProfiles.lua", "ConfigShare.lua")


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The config window's frame mock and session loader are shared with its own harness.
cw = _load("configwindow_harness", "configwindow-harness.py")

# Methods the window harness's frame mock does not record; the dialogs need to be seen using them.
EXTRA_MOCK = r"""
local Obj = getmetatable(UIParent)
function Obj:HighlightText(a, b) self.hl = { a, b } end
function Obj:SetMultiLine(v) self.multi = v end
function Obj:SetMaxLetters(n) self.maxLetters = n end
function Obj:SetMaxBytes(n) self.maxBytes = n end
function Obj:SetSpacing(n) self.spacing = n end
function Obj:SetTextInsets() end
function Obj:SetJustifyH(v) self.justifyH = v end
function Obj:SetWordWrap(v) self.wordWrap = v end
"""

CHECKS = r"""
local T = {}
local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end
local function yes(v, msg) if not v then error(msg or "expected true", 2) end end
local function no(v, msg) if v then error(msg or "expected false", 2) end end

-- The first difference between two plain values as a path, or nil when they are equal.
local function same(a, b, path)
    path = path or "$"
    if type(a) ~= type(b) then return path .. ": " .. type(a) .. " vs " .. type(b) end
    if type(a) == "table" then
        for k, v in pairs(a) do
            local d = same(v, b[k], path .. "." .. tostring(k))
            if d then return d end
        end
        for k in pairs(b) do
            if a[k] == nil then return path .. "." .. tostring(k) .. ": extra" end
        end
        return nil
    end
    if a ~= b then return path .. ": " .. tostring(a) .. " vs " .. tostring(b) end
end
local function eqt(a, b, msg)
    local d = same(a, b)
    if d then error((msg or "tables differ") .. " at " .. d, 2) end
end
local function count(t) local n = 0; for _ in pairs(t) do n = n + 1 end; return n end
local function copy(v)
    if type(v) ~= "table" then return v end
    local c = {}
    for k, x in pairs(v) do c[k] = copy(x) end
    return c
end

-------------------------------------------------------------------------------
-- The world: defaults, layout seats, a mock of C_EncodingUtil, a mock of ModuleSwitch
-------------------------------------------------------------------------------

local function demoDefaults()
    local C = FS.Config
    C.RegisterDefault("demo.on", false)
    C.RegisterDefault("demo.flag", true)
    C.RegisterDefault("demo.size", 10)
    C.RegisterDefault("demo.mode", "Auto")
    C.RegisterDefault("demo.text", "Hello")
    C.RegisterDefault("demo.order", { "a", "b", "c" })
end

-- C_EncodingUtil as the client has it: CBOR is an opaque handle here (the point is that the table goes in and comes back),
-- compression reverses the bytes, base64 is hex. Each step rejects what it did not make, like the real ones.
local function installEncoding(o)
    o = o or {}
    __cbor = {}
    local api = {}
    function api.SerializeCBOR(v) __cbor[#__cbor + 1] = copy(v); return "cbor#" .. #__cbor end
    function api.DeserializeCBOR(s)
        local id = type(s) == "string" and tonumber(s:match("^cbor#(%d+)$"))
        if not id then error("bad cbor") end
        local v = copy(__cbor[id])
        if o.mangle and type(v) == "table" then v.name = "mangled" end
        return v
    end
    function api.CompressString(s, method)
        if method ~= nil and method ~= Enum.CompressionMethod.Deflate then error("bad method") end
        return "Z" .. s:reverse()
    end
    function api.DecompressString(s, method)
        if type(s) ~= "string" or s:sub(1, 1) ~= "Z" then error("bad data") end
        return s:sub(2):reverse()
    end
    function api.EncodeBase64(s) return (s:gsub(".", function(c) return ("%02X"):format(c:byte()) end)) end
    function api.DecodeBase64(s)
        if #s % 2 == 1 or s:find("[^0-9A-F]") then error("bad base64") end
        return (s:gsub("..", function(h) return string.char(tonumber(h, 16)) end))
    end
    if o.without then api[o.without] = nil end
    Enum = Enum or {}
    Enum.CompressionMethod = { Deflate = 0 }
    C_EncodingUtil = api
end

-- ModuleSwitch as lane B5 has it, as far as the codec and the dialog use it.
local function installModules(state)
    local MS = { sets = {} }
    local order = {}
    for k in pairs(state) do order[#order + 1] = k end
    table.sort(order)
    function MS.Keys() local list = {}; for i, k in ipairs(order) do list[i] = k end; return list end
    function MS.Label(k) if state[k] ~= nil then return "Label " .. k end end
    function MS.Snapshot() return copy(state) end
    function MS.Wanted(k) return state[k] end
    function MS.IsWritable() return true end
    function MS.Set(k, on)
        if state[k] == nil then return false, "no such module" end
        MS.sets[#MS.sets + 1] = { k, on }
        state[k] = on
        return true
    end
    FS.ModuleSwitch = MS
    return MS
end

-- o: db (saved variable), encoding (false = no C_EncodingUtil; a table = options for the mock), modules (state table),
-- pre (a function run before the codec loads), noLogin.
local function boot(o)
    o = o or {}
    __session(__configSrc, "", __windowSrc, {
        db = o.db, noGunsight = true, noHelp = true, noLogin = o.noLogin,
        preWindow = function()
            FS.Layout.DESIGN_W = 2560
            FS.Layout.stance = { x = 100, y = -200 }
            FS.Layout.player = { x = 0, y = 0 }
            FS.Layout.chat = { x = 5, y = 5 }
            FS.Layout.deck = { 1, 2 }
            demoDefaults()
            if o.encoding ~= false then installEncoding(o.encoding) else C_EncodingUtil = nil end
            if o.modules then installModules(o.modules) else FS.ModuleSwitch = nil end
            assert(load(__codecSrc, "@ProfileCodec.lua"))("forever-stuwave", FS)
            if o.pre then o.pre() end
        end,
    }, "", "", "", "")
    return FS
end

local SOURCE_FRAMES = { stance = { x = 12.5, y = -30 }, player = { x = -5, y = 7 } }
local function seed()
    local C = FS.Config
    C.Set("demo.on", true)
    C.Set("demo.size", 14)
    C.Set("demo.mode", "Left")
    C.Set("demo.text", "World")
    C.Set("demo.order", { "c", "a" })
    ForeverSTUwaveDB.profiles[C.ActiveProfile()].layout.frames = copy(SOURCE_FRAMES)
end
local function stored() return copy(ForeverSTUwaveDB.profiles[FS.Config.ActiveProfile()].settings) end

local function limits(map) FS.ProfileCodec.SetLimitSource(function() return map end) end

-------------------------------------------------------------------------------
-- Config: GetDefault and ImportProfile
-------------------------------------------------------------------------------

function T.get_default_returns_the_registered_default()
    boot()
    local C = FS.Config
    eq(C.GetDefault("demo.size"), 10)
    eq(C.GetDefault("demo.on"), false)
    eq(C.GetDefault("demo.mode"), "Auto")
    eqt(C.GetDefault("demo.order"), { "a", "b", "c" })
    eq(C.GetDefault("no.such.key"), nil)
    eq(C.GetDefault(5), nil)
    eq(C.GetDefault(nil), nil)
    C.Set("demo.size", 14)
    eq(C.GetDefault("demo.size"), 10, "the default does not follow the stored value")
end

function T.import_profile_makes_a_profile_and_switches_and_fires_nothing()
    local binds = 0
    boot({ pre = function() FS.Layout.UseStore = function() binds = binds + 1 end end })
    local C = FS.Config
    local before = binds
    local fired = 0
    C.OnAnyChange(function() fired = fired + 1 end)
    C.OnChange("demo.size", function() fired = fired + 1 end)
    local data = { settings = { ["demo.size"] = 14, ["demo.on"] = true },
                   layout = { v = 1, frames = { stance = { x = 1, y = 2 } } } }
    local ok, name = C.ImportProfile("Friend", data)
    yes(ok, "imported")
    eq(name, "Friend")
    eq(C.ActiveProfile(), "Default", "never switches")
    eq(fired, 0, "no callback fires")
    eq(binds, before, "the layout store is not rebound")
    local p = ForeverSTUwaveDB.profiles.Friend
    eq(p.settings["demo.size"], 14)
    eq(p.settings["demo.on"], true)
    eq(p.layout.v, 1)
    eq(p.layout.frames.stance.x, 1)
    eq(C.Get("demo.size"), 10, "the active profile is untouched")
    local listed = false
    for _, n in ipairs(C.ListProfiles()) do if n == "Friend" then listed = true end end
    yes(listed, "listed")
    -- what went in is a copy
    data.settings["demo.size"] = 99
    data.layout.frames.stance.x = 99
    eq(p.settings["demo.size"], 14, "settings are copied")
    eq(p.layout.frames.stance.x, 1, "layout is copied")
end

function T.import_profile_never_overwrites_and_obeys_the_name_rules()
    boot()
    local C = FS.Config
    yes(C.NewProfile("Raid"))
    C.Set("demo.size", 12)
    local ok, err = C.ImportProfile("Raid", { settings = {} })
    no(ok); yes(type(err) == "string" and err ~= "", "a reason")
    ok = C.ImportProfile("raid", { settings = {} })
    no(ok, "names compare without case")
    ok = C.ImportProfile("default", { settings = {} })
    no(ok, "Default is taken")
    no(C.ImportProfile("", { settings = {} }), "empty")
    no(C.ImportProfile("   ", { settings = {} }), "blank")
    no(C.ImportProfile(string.rep("x", 33), { settings = {} }), "too long")
    no(C.ImportProfile("a|cffff0000b", { settings = {} }), "no escape characters")
    no(C.ImportProfile("two\nlines", { settings = {} }), "no control characters")
    no(C.ImportProfile(5, { settings = {} }), "not text")
    no(C.ImportProfile("Fine", nil), "needs data")
    no(C.ImportProfile("Fine", "text"), "needs a table")
    eq(count(ForeverSTUwaveDB.profiles), 2, "nothing was made by the refusals")
    local ok2, name = C.ImportProfile("  Trimmed  ", { settings = {} })
    yes(ok2); eq(name, "Trimmed")
    yes(ForeverSTUwaveDB.profiles.Trimmed)
    eq(C.Get("demo.size"), 12)
end

function T.import_profile_is_refused_when_settings_are_read_only()
    boot({ db = "junk" })
    local C = FS.Config
    yes(C.IsReadOnly())
    local ok, err = C.ImportProfile("Friend", { settings = {} })
    no(ok)
    yes(err:find("read%-only"), err)
end

function T.import_profile_stores_nothing_for_a_value_equal_to_the_default_and_nothing_foreign()
    boot()
    local C = FS.Config
    yes(C.ImportProfile("Friend", { settings = { ["demo.size"] = 10, ["demo.on"] = true, ["demo.flag"] = true, [3] = true,
        ["demo.fn"] = function() end } }))
    local s = ForeverSTUwaveDB.profiles.Friend.settings
    eq(s["demo.size"], nil, "equal to the default is stored as nothing")
    eq(s["demo.flag"], nil)
    eq(s["demo.on"], true)
    eq(s[3], nil, "a key that is not text")
    eq(s["demo.fn"], nil, "a function is never stored")
    yes(C.ImportProfile("Bare", { layout = { v = 7, frames = { x = 1 } } }))
    local p = ForeverSTUwaveDB.profiles.Bare
    eqt(p.settings, {})
    eq(p.layout.v, 1, "the layout version is this addon's")
    eqt(p.layout.frames, { x = 1 })
end

-------------------------------------------------------------------------------
-- The codec: formats, round trips
-------------------------------------------------------------------------------

local function expectedSettings() return { ["demo.on"] = true, ["demo.size"] = 14, ["demo.mode"] = "Left",
    ["demo.text"] = "World", ["demo.order"] = { "c", "a" } } end

function T.the_lua_codec_round_trips_every_share_choice()
    boot({ encoding = false, modules = { ["m.cast"] = false, ["m.chat"] = true } })
    seed()
    local Codec = FS.ProfileCodec
    for _, what in ipairs({ "all", "settings", "layout" }) do
        local text, info = Codec.Export(what)
        yes(text:sub(1, 7) == "STUW1L:", what .. ": the Lua prefix, got " .. tostring(text):sub(1, 12))
        eq(info.kind, "L")
        local result, code = Codec.Read(text)
        yes(result, what .. ": " .. tostring(code))
        eq(result.kind, "L")
        local p = result.payload
        eq(p.v, 1)
        eq(p.name, "Default")
        eq(p.addon, "1.0.0-beta.1")
        if what == "layout" then
            eq(p.settings, nil, "layout only carries no settings")
        else
            eqt(p.settings, expectedSettings(), what .. ": settings")
        end
        if what == "settings" then
            eq(p.layout, nil, "settings only carries no layout")
        else
            eq(p.layout.v, 1)
            eqt(p.layout.frames, SOURCE_FRAMES, what .. ": frames")
        end
        eqt(p.modules, { ["m.cast"] = false, ["m.chat"] = true }, what .. ": modules ride along")
        if what == "all" then
            eq(info.settings, 5); eq(info.frames, 2)
        elseif what == "settings" then
            eq(info.settings, 5); eq(info.frames, 0)
        else
            eq(info.settings, 0); eq(info.frames, 2)
        end
    end
end

function T.the_c_codec_round_trips_every_share_choice()
    boot({ modules = { ["m.cast"] = false } })
    seed()
    local Codec = FS.ProfileCodec
    yes(Codec.CanUseEncodingApi(), "every function exists")
    for _, what in ipairs({ "all", "settings", "layout" }) do
        local text, info = Codec.Export(what)
        yes(text:sub(1, 7) == "STUW1C:", what .. ": the C prefix, got " .. tostring(text):sub(1, 12))
        eq(info.kind, "C")
        local result, code = Codec.Read(text)
        yes(result, what .. ": " .. tostring(code))
        eq(result.kind, "C")
        if what ~= "layout" then eqt(result.payload.settings, expectedSettings(), what .. ": settings") end
        if what ~= "settings" then eqt(result.payload.layout.frames, SOURCE_FRAMES, what .. ": frames") end
        eqt(result.payload.modules, { ["m.cast"] = false })
    end
end

function T.export_takes_c_only_when_every_function_exists_and_the_round_trip_holds()
    for _, missing in ipairs({ "SerializeCBOR", "DeserializeCBOR", "CompressString", "DecompressString", "EncodeBase64", "DecodeBase64" }) do
        boot({ encoding = { without = missing } })
        seed()
        no(FS.ProfileCodec.CanUseEncodingApi(), missing .. " missing")
        local text = FS.ProfileCodec.Export("all")
        yes(text:sub(1, 7) == "STUW1L:", missing .. " missing falls back to the Lua codec")
    end
    boot({ encoding = false })
    seed()
    yes(FS.ProfileCodec.Export("all"):sub(1, 7) == "STUW1L:", "no API at all")
    -- the API is there but does not give the table back: the Lua codec is used
    boot({ encoding = { mangle = true } })
    seed()
    local text, info = FS.ProfileCodec.Export("all")
    yes(text:sub(1, 7) == "STUW1L:", "a C round trip that fails is not used")
    eq(info.kind, "L")
    yes(FS.ProfileCodec.Read(text), "and the string reads")
    -- a function that throws
    boot({ pre = function() end })
    seed()
    C_EncodingUtil.CompressString = function() error("nope") end
    text = FS.ProfileCodec.Export("all")
    yes(text:sub(1, 7) == "STUW1L:", "a throwing C step falls back")
end

function T.import_reads_both_prefixes_and_says_when_this_client_cannot_read_c()
    boot({ encoding = false })
    seed()
    local lText = FS.ProfileCodec.Export("all")
    boot()
    seed()
    local cText = FS.ProfileCodec.Export("all")
    yes(cText:sub(1, 7) == "STUW1C:")
    local Codec = FS.ProfileCodec
    yes(Codec.Read(lText), "this client reads a Lua string")
    yes(Codec.Read(cText), "and a C string")
    -- the same C string on a client with no API
    local saved = C_EncodingUtil
    C_EncodingUtil = nil
    local r, code = Codec.Read(cText)
    eq(r, nil)
    eq(code, "unsupported")
    eq(Codec.REASON[code], "This client cannot read this string")
    yes(Codec.Read(lText), "a Lua string reads without the API")
    -- with some of it missing
    C_EncodingUtil = { SerializeCBOR = saved.SerializeCBOR }
    local _, code2 = Codec.Read(cText)
    eq(code2, "unsupported")
    C_EncodingUtil = saved
end

function T.every_bad_string_gets_its_reason()
    boot({ modules = { ["m.cast"] = true } })
    seed()
    local Codec = FS.ProfileCodec
    local R = Codec.REASON
    eq(R.notprofile, "Not a STUwave profile string")
    eq(R.newer, "Made by a newer STUwave")
    eq(R.damaged, "Damaged string")
    eq(R.unsupported, "This client cannot read this string")
    local good = Codec.Export("all", "L")
    local function reason(text) local r, code, message = Codec.Read(text); eq(r, nil, "refused"); eq(message, R[code]); return code end
    eq(reason(nil), "notprofile")
    eq(reason(42), "notprofile")
    eq(reason(""), "notprofile")
    eq(reason("   \n "), "notprofile")
    eq(reason("hello world"), "notprofile")
    eq(reason("STUWAVE is a nice addon"), "notprofile")
    eq(reason("STUW0L:AAAA"), "notprofile")
    eq(reason("STUW1L:"), "damaged")
    eq(reason("STUW1L:!!!"), "damaged")
    eq(reason("STUW1L:AAAA"), "damaged")
    eq(reason("STUW1L:" .. string.rep("A", 40)), "damaged")
    eq(reason("STUW1C:"), "damaged")
    eq(reason("STUW1C:ZZZZ"), "damaged")
    eq(reason("STUW2L:" .. good:sub(8)), "newer")
    eq(reason("STUW9C:abcd"), "newer")
    eq(reason("STUW1Z:abcd"), "newer")
    -- cut short, one character changed, one character inserted
    eq(reason(good:sub(1, #good - 6)), "damaged")
    local at = 40
    local flipped = good:sub(1, at - 1) .. (good:sub(at, at) == "A" and "B" or "A") .. good:sub(at + 1)
    eq(reason(flipped), "damaged")
    eq(reason(good:sub(1, at) .. "A" .. good:sub(at + 1)), "damaged")
    -- a payload made by a newer format version, and a newer layout
    local newer = Codec.Encode({ v = 2, name = "X", settings = {} }, "L")
    eq(reason(newer), "newer")
    local newerLayout = Codec.Encode({ v = 1, name = "X", layout = { v = 2, frames = {} } }, "L")
    eq(reason(newerLayout), "newer")
    -- structurally wrong payloads
    eq(reason(Codec.Encode({ v = 1, name = "X" }, "L")), "damaged")
    eq(reason(Codec.Encode({ name = "X", settings = {} }, "L")), "damaged")
    eq(reason(Codec.Encode({ v = "1", settings = {} }, "L")), "damaged")
    eq(reason(Codec.Encode({ v = 1, settings = "no" }, "L")), "damaged")
    eq(reason(Codec.Encode({ v = 1, layout = { v = 1, frames = 5 } }, "L")), "damaged")
    eq(reason(Codec.Encode({ 1, 2, 3 }, "L")), "damaged")
    -- the C path: a stream that is not ours
    eq(reason("STUW1C:" .. C_EncodingUtil.EncodeBase64("not compressed")), "damaged")
    eq(reason("STUW1C:" .. C_EncodingUtil.EncodeBase64(C_EncodingUtil.CompressString("not cbor"))), "damaged")
    eq(reason("STUW1C:" .. C_EncodingUtil.EncodeBase64(C_EncodingUtil.CompressString(C_EncodingUtil.SerializeCBOR("text")))), "damaged")
end

function T.a_string_survives_being_pasted_through_chat_or_mail()
    boot({ encoding = false })
    seed()
    local Codec = FS.ProfileCodec
    local good = Codec.Export("all")
    local function reads(text, msg) local r, code = Codec.Read(text); yes(r, msg .. ": " .. tostring(code)); return r end
    reads("  " .. good .. "  \n", "spaces around")
    reads("Here is my setup: " .. good, "words before")
    reads("\"" .. good .. "\"", "quotes around")
    reads(good .. ".", "a full stop after")
    reads("<" .. good .. ">", "angle brackets around")
    local wrapped = good:gsub("(" .. string.rep(".", 60) .. ")", "%1\n")
    reads(wrapped, "wrapped lines")
    reads((good:gsub("(" .. string.rep(".", 50) .. ")", "%1 \r\n  ")), "wrapped with indents")
    eqt(reads(wrapped, "same").payload.settings, expectedSettings())
end

function T.export_is_the_same_twice_and_names_the_profile_and_the_version()
    boot({ encoding = false })
    seed()
    local Codec = FS.ProfileCodec
    local a, b = Codec.Export("all"), Codec.Export("all")
    eq(a, b)
    yes(FS.Config.NewProfile("Stu Shockalaka"))
    FS.Config.SetActiveProfile("Stu Shockalaka")
    local text, info = Codec.Export("all")
    eq(info.name, "Stu Shockalaka")
    eq(info.addon, "1.0.0-beta.1")
    eq(Codec.Read(text).payload.name, "Stu Shockalaka")
    eq(info.settings, 0)
    eq(info.frames, 0)
end

function T.a_big_profile_round_trips_in_both_codecs()
    for _, codec in ipairs({ false, true }) do
        boot({ encoding = codec and {} or false, pre = function()
            for i = 1, 1500 do FS.Config.RegisterDefault(("big.key.%04d"):format(i), false) end
        end })
        for i = 1, 1500 do FS.Config.Set(("big.key.%04d"):format(i), true) end
        local Codec = FS.ProfileCodec
        local text, info = Codec.Export("all")
        eq(info.settings, 1500)
        local t0 = os.clock()
        local r, code = Codec.Read(text)
        yes(r, tostring(code))
        eq(count(r.payload.settings), 1500)
        yes(os.clock() - t0 < 1.5, "reads quickly")
    end
end

-------------------------------------------------------------------------------
-- Validation
-------------------------------------------------------------------------------

function T.validation_drops_the_unknown_the_mistyped_and_the_odd()
    boot({ modules = { ["m.cast"] = true } })
    local Codec = FS.ProfileCodec
    limits({ ["demo.size"] = { min = 4, max = 20 }, ["demo.mode"] = { options = { "Auto", "Left", "Right" } } })
    local raw = { v = 1, name = "Stu", settings = {
        ["demo.on"] = true,
        ["demo.size"] = 999,
        ["demo.mode"] = "Sideways",
        ["demo.text"] = 5,
        ["no.such.key"] = true,
        ["demo.flag"] = true,
        [5] = true,
    } }
    local clean, report = Codec.Validate(raw)
    yes(clean, "valid")
    eqt(clean.settings, { ["demo.on"] = true, ["demo.size"] = 20 })
    eq(report.settings, 2)
    eq(report.clamped, 1, "one clamp")
    eq(report.ignored, 4, "mode, text, unknown key, non text key")
    -- below the minimum
    clean = Codec.Validate({ v = 1, settings = { ["demo.size"] = -50 } })
    eq(clean.settings["demo.size"], 4)
    -- inside the range is left alone, fractions included
    clean = Codec.Validate({ v = 1, settings = { ["demo.size"] = 12.5 } })
    eq(clean.settings["demo.size"], 12.5)
    -- a value that is a listed option stays
    clean = Codec.Validate({ v = 1, settings = { ["demo.mode"] = "Right" } })
    eq(clean.settings["demo.mode"], "Right")
end

function T.validation_has_a_sane_bound_for_a_number_with_no_row()
    boot()
    local Codec = FS.ProfileCodec
    limits({})
    local clean, report = Codec.Validate({ v = 1, settings = { ["demo.size"] = 5e300 } })
    yes(clean.settings["demo.size"] <= 1e6, "bounded")
    eq(report.clamped, 1)
    clean = Codec.Validate({ v = 1, settings = { ["demo.size"] = 0 / 0 } })
    eq(clean.settings["demo.size"], nil, "NaN dropped")
    clean = Codec.Validate({ v = 1, settings = { ["demo.size"] = math.huge } })
    eq(clean.settings["demo.size"], nil, "infinity dropped")
    clean = Codec.Validate({ v = 1, settings = { ["demo.size"] = -math.huge } })
    eq(clean.settings["demo.size"], nil, "negative infinity dropped")
end

function T.validation_keeps_settings_text_plain()
    boot()
    local Codec = FS.ProfileCodec
    limits({})
    for _, bad in ipairs({ "a|cffff0000b", "a|Hitem:1|h[x]|h", "line\nbreak", "bell\a", string.rep("x", 300) }) do
        local clean, report = Codec.Validate({ v = 1, settings = { ["demo.text"] = bad } })
        eq(clean.settings["demo.text"], nil, "dropped")
        eq(report.ignored, 1)
    end
    local clean = Codec.Validate({ v = 1, settings = { ["demo.text"] = "Plain words, 12 of them." } })
    eq(clean.settings["demo.text"], "Plain words, 12 of them.")
end

function T.validation_checks_the_shape_of_a_list_setting()
    boot()
    local Codec = FS.ProfileCodec
    limits({})
    local function fit(v) return Codec.Validate({ v = 1, settings = { ["demo.order"] = v } }).settings["demo.order"] end
    eqt(fit({ "x", "y" }), { "x", "y" })
    eqt(fit({ "x" }), { "x" })
    eq(fit({ 1, 2 }), nil, "wrong element type")
    eq(fit("text"), nil, "not a table")
    eq(fit({ a = "x" }), nil, "not a list")
    eq(fit({ [1] = "x", [3] = "z" }), nil, "a list with a hole")
    local long = {}
    for i = 1, 200 do long[i] = "k" .. i end
    eq(fit(long), nil, "far too long")
    eq(fit({ { "x" } }), nil, "no nested tables")
    eq(fit({ "bad|cffff0000" }), nil, "elements are plain text too")
    -- a copy, not the table that came in
    local given = { "x", "y" }
    local out = fit(given)
    yes(out ~= given)
end

function T.validation_drops_unknown_frame_ids_and_clamps_offsets()
    boot()
    local Codec = FS.ProfileCodec
    limits({})
    local raw = { v = 1, name = "X", layout = { v = 1, frames = {
        stance = { x = 5, y = 6 },
        player = { x = 1e9, y = -1e9 },
        chat = { x = "a", y = 1 },
        ghost = { x = 1, y = 1 },
        deck = { x = 1, y = 1 },
        _defaults = { x = 1, y = 1 },
        [7] = { x = 1, y = 1 },
    } } }
    local clean, report = Codec.Validate(raw)
    yes(clean)
    eqt(clean.layout.frames, { stance = { x = 5, y = 6 }, player = { x = 5120, y = -5120 } })
    eq(clean.layout.v, 1)
    eq(report.frames, 2)
    eq(report.clamped, 1, "one frame had both offsets clamped")
    eq(report.ignored, 5, "chat (bad x), ghost, deck, _defaults, [7]")
    -- extra fields on a frame do not travel
    clean = Codec.Validate({ v = 1, layout = { v = 1, frames = { stance = { x = 1, y = 2, scale = 9, evil = {} } } } })
    eqt(clean.layout.frames.stance, { x = 1, y = 2 })
end

function T.validation_drops_unknown_module_keys_and_ignores_modules_without_the_switch()
    boot({ modules = { ["m.cast"] = true, ["m.chat"] = true } })
    local Codec = FS.ProfileCodec
    local raw = { v = 1, name = "X", settings = {}, modules = { ["m.cast"] = false, ["m.nosuch"] = true, ["m.chat"] = "yes" } }
    local clean, report = Codec.Validate(raw)
    eqt(clean.modules, { ["m.cast"] = false })
    eq(report.modules, 1)
    eq(report.ignored, 2)
    boot({ encoding = false })
    Codec = FS.ProfileCodec
    clean, report = Codec.Validate(raw)
    yes(clean, "still valid")
    eq(clean.modules, nil, "no ModuleSwitch, nothing to set")
    eq(report.modules, 0)
    -- the export carries none without the switch
    seed()
    eq(Codec.Read(Codec.Export("all")).payload.modules, nil)
end

function T.validation_does_not_read_other_peoples_tables_by_reference_and_reads_odd_keys_safely()
    boot()
    local Codec = FS.ProfileCodec
    limits({})
    local raw = { v = 1, settings = setmetatable({}, { __index = function() error("index") end }) }
    raw.settings["demo.on"] = true
    local ok, clean = pcall(Codec.Validate, raw)
    yes(ok, "no error")
    eq(clean.settings["demo.on"], true)
    -- a cyclic table in a setting is not followed
    local loop = {}
    loop[1] = loop
    ok, clean = pcall(Codec.Validate, { v = 1, settings = { ["demo.order"] = loop } })
    yes(ok, "a cycle does not hang or throw")
    eq(clean.settings["demo.order"], nil)
end

-------------------------------------------------------------------------------
-- No code from a string, and big pastes
-------------------------------------------------------------------------------

function T.no_code_is_ever_run_from_a_string()
    boot()
    seed()
    local Codec = FS.ProfileCodec
    local calls = {}
    local names = { "load", "loadstring", "loadfile", "dofile", "setfenv", "RunScript", "require", "pcall_code" }
    local saved = {}
    for _, n in ipairs(names) do
        saved[n] = _G[n]
        _G[n] = function() calls[#calls + 1] = n; error("forbidden " .. n) end
    end
    local texts = {}
    for _, b64 in ipairs(HOSTILE) do
        texts[#texts + 1] = "STUW1L:" .. b64
        texts[#texts + 1] = "STUW1C:" .. b64
    end
    texts[#texts + 1] = Codec.Encode({ v = 1, name = "return os.exit()", settings = { ["demo.text"] = "return os.execute('boom')" } }, "L")
    texts[#texts + 1] = "return os.execute('boom')"
    texts[#texts + 1] = "STUW1L:cmV0dXJuIG9zLmV4ZWN1dGUoJ2Jvb20nKQ=="
    for _, text in ipairs(texts) do
        local ok, err = pcall(Codec.Read, text)
        yes(ok, "Read never throws: " .. tostring(err))
    end
    local made = Codec.Read(texts[#texts - 2])
    eq(made.payload.settings["demo.text"], "return os.execute('boom')", "code in a value is only text")
    for _, n in ipairs(names) do _G[n] = saved[n] end
    eq(#calls, 0, "nothing was loaded or run: " .. table.concat(calls, ","))
end

function T.a_200_kb_paste_returns_at_once_without_an_error()
    boot()
    local Codec = FS.ProfileCodec
    local big = string.rep("A", 200000)
    local shapes = {
        big,
        "STUW1L:" .. big,
        "STUW1C:" .. big,
        string.rep("STUW1L:", 30000),
        string.rep("x ", 100000),
        string.rep("STUW", 50000),
        "STUW1L:" .. string.rep("AAAA", 50000) .. "!",
        string.rep("{", 200000),
        "STUW1L:" .. string.rep("e", 200000),
        string.rep("\n", 200000),
    }
    local t0 = os.clock()
    for i, text in ipairs(shapes) do
        local ok, r, code = pcall(Codec.Read, text)
        yes(ok, "shape " .. i .. " threw: " .. tostring(r))
        eq(r, nil, "shape " .. i .. " is not a profile")
        yes(Codec.REASON[code], "shape " .. i .. " has a reason, got " .. tostring(code))
    end
    yes(os.clock() - t0 < 3, "all shapes together took " .. (os.clock() - t0) .. "s")
end

function T.a_deeply_nested_or_huge_lua_payload_is_refused_not_followed()
    boot({ encoding = false })
    local Codec = FS.ProfileCodec
    local b64 = HOSTILE_DEEP
    local ok, r, code = pcall(Codec.Read, "STUW1L:" .. b64)
    yes(ok, "no error")
    eq(r, nil)
    eq(code, "damaged")
end

-------------------------------------------------------------------------------
-- The Profiles page and the dialogs
-------------------------------------------------------------------------------

local function under(root, o)
    while o do
        if o == root then return true end
        o = o.parent
    end
    return false
end
local function findText(text, root)
    for _, o in ipairs(ALL) do
        if o.kind == "FontString" and o:IsVisible() and (root == nil or under(root, o)) and o:GetText() == text then return o end
    end
end
local function hasText(root, needle)
    for _, o in ipairs(ALL) do
        if o.kind == "FontString" and o:IsVisible() and under(root, o) and o:GetText():find(needle, 1, true) then return true end
    end
    return false
end
local function owner(fs, field)
    local o = fs.parent
    while o do
        if (field == nil and o.scripts.OnClick) or (field and o[field]) then return o end
        o = o.parent
    end
end
local function click(text, root)
    local fs = findText(text, root)
    if not fs then error("no visible text '" .. text .. "'", 2) end
    local b = owner(fs)
    if not b then error("no clickable owner for '" .. text .. "'", 2) end
    if not b.enabled then return false end
    b.scripts.OnClick(b, "LeftButton")
    return true
end
local function button(text, root)
    local fs = findText(text, root)
    if not fs then error("no visible text '" .. text .. "'", 2) end
    return owner(fs)
end
local function win() return _G.ForeverSTUwaveConfig end
local function profilesPage()
    local W = FS.ConfigWindow
    W.Open("profiles")
    return W
end
local function share() return FS.ConfigWindow.Share end
local function paste(text)
    local box = share().ui.box
    box:SetText(text)
    box.scripts.OnTextChanged(box, true)
end
local function typeName(text)
    local edit = share().ui.saveEdit
    edit:SetText(text)
    edit.scripts.OnTextChanged(edit, true)
end
local function lineText() return share().ui.line:GetText() end
local function noteText() local n = share().ui.note; return n:IsShown() and n:GetText() or nil end
local function demoPage()
    local W = FS.ConfigWindow
    W.RegisterCategory({ key = "demo", label = "Demo", group = "GENERAL", order = 50, tabs = { { key = "d", label = "Demo", build = function(content)
        local UI = W.UI
        UI.Toggle(content, { label = "Demo on", key = "demo.on" })
        UI.Slider(content, { label = "Demo size", key = "demo.size", min = 4, max = 20, fmt = "%s px" })
        UI.Segmented(content, { label = "Demo mode", key = "demo.mode", options = {
            { value = "Auto", text = "Auto" }, { value = "Left", text = "Left" }, { value = "Right", text = "Right" } } })
    end } } })
    W.Open("demo")
end
local function exportString(what, kind)
    return (FS.ProfileCodec.Export(what, kind))
end
local C_PINK = function() return FS.ConfigWindow.C.pink end
local C_CYAN = function() return FS.ConfigWindow.C.cyan end

function T.the_profiles_page_has_a_share_section_with_export_and_import()
    boot()
    profilesPage()
    yes(findText("SHARE", win()) or hasText(win(), "SHARE"), "the // SHARE header")
    yes(findText("Export this profile", win()), "export row")
    yes(findText("Import a profile", win()), "import row")
    yes(findText("EXPORT", win()) and findText("IMPORT", win()), "the two buttons")
    local tips = {}
    for _, o in ipairs(ALL) do if o.fsTip and o:IsVisible() then tips[#tips + 1] = o.fsTip end end
    local all = table.concat(tips, "\n")
    yes(all:find("Makes a text string of this profile to paste on another character or give to a friend.", 1, true), "export tip")
    yes(all:find("Paste a string to add it as a new profile.", 1, true), "import tip")
    -- Share sits after Manage and before Saved data
    local order = {}
    for _, e in ipairs(FS.ConfigWindow.Rows()) do if e.page == "profiles" then order[#order + 1] = e.section or "?" end end
    local seen, flat = {}, {}
    for _, s in ipairs(order) do if not seen[s] then seen[s] = true; flat[#flat + 1] = s end end
    local i, j = 0, 0
    for n, s in ipairs(flat) do
        if s == "Manage" then i = n end
        if s == "Share" then j = n end
    end
    yes(i > 0 and j > i, "Share after Manage: " .. table.concat(flat, ","))
end

function T.the_share_buttons_are_off_while_settings_are_read_only()
    boot({ db = "junk" })
    profilesPage()
    no(button("EXPORT", win()).enabled, "export off")
    no(button("IMPORT", win()).enabled, "import off")
end

function T.the_export_dialog_opens_with_the_string_selected_and_nothing_to_type()
    boot({ encoding = false })
    seed()
    profilesPage()
    yes(click("EXPORT", win()))
    local ui = share().ui
    yes(ui.overlay:IsShown(), "dialog shown")
    yes(findText("EXPORT PROFILE", ui.panel), "the title")
    local text = exportString("all")
    eq(ui.box:GetText(), text, "the box holds the string")
    yes(ui.box.focused, "the box is focused")
    yes(ui.box.hl and ui.box.hl[1] == nil and ui.box.hl[2] == nil, "every character is selected")
    eq(ui.box.maxLetters, 0, "no letter limit")
    eq(lineText(), "Default / 5 settings and 2 frame positions / v1.0.0-beta.1")
    eq(ui.line.themeColor, C_CYAN())
    yes(findText("DONE", ui.panel), "DONE")
    yes(findText("Share", ui.panel), "the Share choice")
    for _, label in ipairs({ "All", "Settings", "Layout" }) do yes(findText(label, ui.panel), label) end
    no(ui.saveEdit and ui.saveEdit:IsVisible(), "no Save as in export")
end

function T.the_export_share_choice_changes_the_string_and_the_line()
    boot({ encoding = false })
    seed()
    profilesPage()
    click("EXPORT", win())
    local ui = share().ui
    yes(click("Settings", ui.panel))
    eq(ui.box:GetText(), exportString("settings"))
    eq(lineText(), "Default / 5 settings / v1.0.0-beta.1")
    yes(ui.box.focused and ui.box.hl, "re-selected after the change")
    yes(click("Layout", ui.panel))
    eq(ui.box:GetText(), exportString("layout"))
    eq(lineText(), "Default / 2 frame positions / v1.0.0-beta.1")
    yes(click("All", ui.panel))
    eq(ui.box:GetText(), exportString("all"))
    eq(lineText(), "Default / 5 settings and 2 frame positions / v1.0.0-beta.1")
end

function T.the_export_line_counts_in_the_singular()
    boot({ encoding = false })
    FS.Config.Set("demo.on", true)
    ForeverSTUwaveDB.profiles.Default.layout.frames = { stance = { x = 1, y = 2 } }
    profilesPage()
    click("EXPORT", win())
    eq(lineText(), "Default / 1 setting and 1 frame position / v1.0.0-beta.1")
end

function T.the_export_box_puts_back_anything_typed_and_done_closes()
    boot({ encoding = false })
    seed()
    profilesPage()
    click("EXPORT", win())
    local ui = share().ui
    local text = ui.box:GetText()
    ui.box:SetText(text .. "x")
    ui.box.scripts.OnTextChanged(ui.box, true)
    eq(ui.box:GetText(), text, "a typed change is put back")
    ui.box.scripts.OnEscapePressed(ui.box)
    no(ui.overlay:IsShown(), "Escape in the box closes")
    click("EXPORT", win())
    yes(ui.overlay:IsShown())
    yes(click("DONE", ui.panel))
    no(ui.overlay:IsShown(), "DONE closes")
    no(ui.box.focused, "focus is let go")
end

function T.the_export_dialog_uses_c_when_the_client_has_it()
    boot()
    seed()
    profilesPage()
    click("EXPORT", win())
    yes(share().ui.box:GetText():sub(1, 7) == "STUW1C:")
end

function T.the_import_dialog_starts_empty_with_the_import_button_off()
    boot({ encoding = false })
    profilesPage()
    yes(click("IMPORT", win()))
    local ui = share().ui
    yes(ui.overlay:IsShown())
    yes(findText("IMPORT PROFILE", ui.panel), "the title")
    yes(findText("Paste a profile here (Ctrl+V)", ui.panel), "the placeholder")
    yes(ui.box.focused, "ready for Ctrl+V")
    eq(ui.box.maxLetters, 0)
    eq(ui.box:GetText(), "")
    yes(findText("Save as", ui.panel))
    yes(findText("CANCEL", ui.panel))
    local accept = button("IMPORT AS NEW PROFILE", ui.panel)
    no(accept.enabled, "off until there is a valid string")
    eq(lineText(), "")
    -- clicking an off button does nothing
    accept.scripts.OnClick(accept)
    eq(count(ForeverSTUwaveDB.profiles), 1)
end

function T.a_valid_string_shows_the_line_a_unique_name_and_turns_the_button_on()
    boot({ encoding = false })
    seed()
    local text = exportString("all")
    profilesPage()
    click("IMPORT", win())
    paste(text)
    local ui = share().ui
    eq(lineText(), "Default / 5 settings and 2 frame positions / made on v1.0.0-beta.1")
    eq(ui.line.themeColor, C_CYAN())
    eq(ui.saveEdit:GetText(), "Default 2", "<name> 2, made unique")
    yes(button("IMPORT AS NEW PROFILE", ui.panel).enabled, "on")
    no(findText("Paste a profile here (Ctrl+V)", ui.panel), "the placeholder is gone")
    eq(noteText(), nil, "nothing was skipped")
    -- clearing the box goes back to the start
    paste("")
    eq(lineText(), "")
    no(button("IMPORT AS NEW PROFILE", ui.panel).enabled)
    yes(findText("Paste a profile here (Ctrl+V)", ui.panel), "the placeholder is back")
end

function T.the_default_name_is_made_unique_and_fits_the_name_limit()
    boot({ encoding = false })
    local S = FS.ConfigWindow.Share
    yes(FS.Config.NewProfile("Stu"))
    yes(FS.Config.NewProfile("Stu 2"))
    yes(FS.Config.NewProfile("Stu 3"))
    eq(S.SuggestName("Stu"), "Stu 4")
    eq(S.SuggestName("stu"), "stu 4", "names compare without case")
    eq(S.SuggestName("Fresh"), "Fresh 2")
    eq(S.SuggestName(nil), "Imported 2")
    eq(S.SuggestName("   "), "Imported 2")
    local long = string.rep("x", 32)
    local made = S.SuggestName(long)
    yes(#made <= FS.Config.NAME_MAX, "trimmed to NAME_MAX: " .. #made)
    eq(made, string.rep("x", 30) .. " 2")
    yes(FS.Config.NewProfile(made))
    eq(S.SuggestName(long), string.rep("x", 30) .. " 3")
    -- by characters, not bytes
    local accents = string.rep("\195\169", 32)
    local m2 = S.SuggestName(accents)
    eq(m2, string.rep("\195\169", 30) .. " 2")
    eq(S.SuggestName("a|cffff0000b"), "acffff0000b 2", "escape characters are taken out")
end

function T.every_bad_string_in_the_dialog_shows_one_pink_reason()
    boot({ encoding = false })
    seed()
    local good = exportString("all")
    profilesPage()
    click("IMPORT", win())
    local ui = share().ui
    local R = FS.ProfileCodec.REASON
    for _, case in ipairs({
        { "hello", R.notprofile },
        { "STUW2L:AAAA", R.newer },
        { "STUW1L:AAAA", R.damaged },
        { good:sub(1, #good - 5), R.damaged },
    }) do
        paste(case[1])
        eq(lineText(), case[2])
        eq(ui.line.themeColor, C_PINK())
        no(button("IMPORT AS NEW PROFILE", ui.panel).enabled, case[2])
    end
    -- and a good one afterwards recovers
    paste(good)
    eq(ui.line.themeColor, C_CYAN())
    yes(button("IMPORT AS NEW PROFILE", ui.panel).enabled)
    -- a C string on a client that cannot read it
    boot({ encoding = {} })
    seed()
    local c = exportString("all")
    yes(c:sub(1, 7) == "STUW1C:")
    C_EncodingUtil = nil
    profilesPage()
    click("IMPORT", win())
    paste(c)
    eq(lineText(), R.unsupported)
    eq(share().ui.line.themeColor, C_PINK())
end

function T.the_save_as_name_is_checked_and_the_button_follows_it()
    boot({ encoding = false })
    seed()
    local good = exportString("all")
    profilesPage()
    click("IMPORT", win())
    paste(good)
    local ui = share().ui
    local accept = button("IMPORT AS NEW PROFILE", ui.panel)
    eq(ui.saveEdit.maxLetters, FS.Config.NAME_MAX, "the name box is limited to NAME_MAX")
    typeName("default")
    eq(lineText(), "A profile with that name exists")
    eq(ui.line.themeColor, C_PINK())
    no(accept.enabled)
    typeName("   ")
    yes(lineText() ~= "" and ui.line.themeColor == C_PINK(), "an empty name is a reason")
    no(accept.enabled)
    typeName("a|cffff0000b")
    eq(ui.line.themeColor, C_PINK())
    no(accept.enabled, "no escape characters")
    typeName(("x"):rep(FS.Config.NAME_MAX + 1))
    eq(lineText(), "The name is longer than " .. FS.Config.NAME_MAX .. " characters", "a pasted name can pass the box's own limit")
    no(accept.enabled)
    typeName(("x"):rep(FS.Config.NAME_MAX))
    yes(accept.enabled, "exactly at the limit is fine")
    typeName("Friend")
    eq(ui.line.themeColor, C_CYAN())
    eq(lineText(), "Default / 5 settings and 2 frame positions / made on v1.0.0-beta.1")
    yes(accept.enabled)
    -- a name the user typed is not replaced when the string changes
    paste(good)
    eq(ui.saveEdit:GetText(), "Friend")
end

function T.import_as_new_profile_makes_it_closes_and_does_not_switch()
    boot({ encoding = false })
    seed()
    local good = exportString("all")
    profilesPage()
    click("IMPORT", win())
    paste(good)
    local ui = share().ui
    typeName("Friend")
    yes(click("IMPORT AS NEW PROFILE", ui.panel))
    no(ui.overlay:IsShown(), "closed")
    eq(FS.Config.ActiveProfile(), "Default", "not switched")
    local p = ForeverSTUwaveDB.profiles.Friend
    yes(p, "the profile exists")
    eqt(p.settings, expectedSettings())
    eqt(p.layout.frames, SOURCE_FRAMES)
    eq(p.layout.v, 1)
    local said = false
    for _, line in ipairs(__printed) do if line:find("Friend", 1, true) then said = true end end
    yes(said, "says what it made")
    -- the Profile in use list offers it
    local listed = false
    for _, n in ipairs(FS.Config.ListProfiles()) do if n == "Friend" then listed = true end end
    yes(listed)
    -- the source is untouched
    eqt(stored(), expectedSettings())
end

function T.import_from_a_c_string_works_the_same()
    boot()
    seed()
    local c = exportString("all")
    yes(c:sub(1, 7) == "STUW1C:")
    profilesPage()
    click("IMPORT", win())
    paste(c)
    yes(button("IMPORT AS NEW PROFILE", share().ui.panel).enabled)
    click("IMPORT AS NEW PROFILE", share().ui.panel)
    eqt(ForeverSTUwaveDB.profiles["Default 2"].settings, expectedSettings())
end

function T.cancel_and_escape_close_the_import_dialog_and_make_nothing()
    boot({ encoding = false })
    seed()
    local good = exportString("all")
    profilesPage()
    click("IMPORT", win())
    paste(good)
    yes(click("CANCEL", share().ui.panel))
    no(share().ui.overlay:IsShown())
    eq(count(ForeverSTUwaveDB.profiles), 1)
    click("IMPORT", win())
    yes(share().ui.overlay:IsShown())
    eq(share().ui.box:GetText(), "", "opens empty each time")
    share().ui.box.scripts.OnEscapePressed(share().ui.box)
    no(share().ui.overlay:IsShown(), "Escape in the box")
    click("IMPORT", win())
    local ov = share().ui.overlay
    ov.scripts.OnKeyDown(ov, "ESCAPE")
    no(ov:IsShown(), "Escape on the dialog")
    eq(ov.propagate, false, "the key stops here so the window stays open")
    yes(win():IsShown(), "the config window is still open")
    ov:Show()
    ov.scripts.OnKeyDown(ov, "W")
    eq(ov.propagate, true, "other keys reach the game")
end

function T.the_dialog_closes_with_the_window()
    boot({ encoding = false })
    profilesPage()
    click("EXPORT", win())
    yes(share().ui.overlay:IsShown())
    FS.ConfigWindow.Close()
    FS.ConfigWindow.Open("profiles")
    no(share().ui.overlay:IsShown(), "not left open")
end

function T.import_clamps_to_the_rows_range_and_drops_an_unlisted_option()
    boot({ encoding = false })
    profilesPage()
    demoPage()
    FS.ConfigWindow.Open("profiles")
    local text = FS.ProfileCodec.Encode({ v = 1, name = "Odd", settings = {
        ["demo.size"] = 999, ["demo.mode"] = "Sideways", ["demo.on"] = true } }, "L")
    click("IMPORT", win())
    paste(text)
    click("IMPORT AS NEW PROFILE", share().ui.panel)
    local s = ForeverSTUwaveDB.profiles["Odd 2"].settings
    eq(s["demo.size"], 20, "clamped to the slider's max")
    eq(s["demo.mode"], nil, "not one of the segment values")
    eq(s["demo.on"], true)
end

function T.the_note_line_counts_what_was_skipped_and_adjusted()
    boot({ encoding = false })
    profilesPage()
    demoPage()
    FS.ConfigWindow.Open("profiles")
    local text = FS.ProfileCodec.Encode({ v = 1, name = "Odd", settings = {
        ["demo.on"] = true, ["demo.size"] = 999, ["no.such.key"] = 1, ["another.unknown"] = 2 } }, "L")
    click("IMPORT", win())
    paste(text)
    eq(lineText(), "Odd / 2 settings", "no version is named when the string has none")
    eq(noteText(), "2 skipped, 1 adjusted to fit")
    yes(button("IMPORT AS NEW PROFILE", share().ui.panel).enabled, "still importable")
    paste(FS.ProfileCodec.Encode({ v = 1, name = "Odd", settings = { ["demo.on"] = true, ["x.y"] = 1 } }, "L"))
    eq(noteText(), "1 skipped")
    paste(FS.ProfileCodec.Encode({ v = 1, name = "Odd", settings = { ["demo.size"] = 1 } }, "L"))
    eq(noteText(), "1 adjusted to fit")
    paste(FS.ProfileCodec.Encode({ v = 1, name = "Odd", settings = { ["demo.on"] = true } }, "L"))
    eq(noteText(), nil, "no note when nothing was touched")
end

function T.the_modules_checkbox_shows_only_when_the_string_carries_them_and_is_off_by_default()
    boot({ encoding = false, modules = { ["m.cast"] = false, ["m.chat"] = true } })
    seed()
    local withModules = exportString("all")
    local MS = FS.ModuleSwitch
    profilesPage()
    click("IMPORT", win())
    local ui = share().ui
    paste(withModules)
    yes(ui.modulesBox:IsVisible(), "the string carries module switches")
    yes(findText("Also set which modules are on", ui.panel))
    no(ui.modulesBox.fsChecked, "off by default")
    -- this client has them both on; ticking would turn Cast bars off
    MS.Snapshot = function() return { ["m.cast"] = true, ["m.chat"] = true } end
    MS.Wanted = function(k) return true end
    click("IMPORT AS NEW PROFILE", ui.panel)
    eq(#MS.sets, 0, "unticked sets nothing")
    -- again, ticked
    click("IMPORT", win())
    paste(withModules)
    typeName("Second")
    ui.modulesBox.scripts.OnClick(ui.modulesBox)
    yes(ui.modulesBox.fsChecked, "ticked")
    click("IMPORT AS NEW PROFILE", ui.panel)
    eq(#MS.sets, 1, "only the one that differs")
    eq(MS.sets[1][1], "m.cast")
    eq(MS.sets[1][2], false)
    -- a string with no modules, and a client without the switch, show no checkbox
    boot({ encoding = false })
    seed()
    local plain = exportString("all")
    profilesPage()
    click("IMPORT", win())
    paste(withModules)
    no(share().ui.modulesBox:IsVisible(), "no ModuleSwitch here")
    paste(plain)
    no(share().ui.modulesBox:IsVisible())
end

function T.the_modules_tip_says_what_would_change_and_when_a_reload_is_needed()
    boot({ encoding = false, modules = { ["m.cast"] = false, ["m.chat"] = true, ["m.same"] = true } })
    seed()
    local MS = FS.ModuleSwitch
    local text = exportString("all")
    MS.Snapshot = function() return { ["m.cast"] = true, ["m.chat"] = false, ["m.same"] = true } end
    profilesPage()
    click("IMPORT", win())
    local ui = share().ui
    paste(text)
    eq(ui.modulesHelp.fsTip, "Turns off: Label m.cast.\nTurns on: Label m.chat.\nTakes a Reload UI.")
    -- a module that switches at once needs no reload
    MS.IsLive = function() return true end
    paste("")
    paste(text)
    eq(ui.modulesHelp.fsTip, "Turns off: Label m.cast.\nTurns on: Label m.chat.", "every change is live")
    MS.Snapshot = function() return { ["m.cast"] = false, ["m.chat"] = true, ["m.same"] = true } end
    paste("")
    paste(text)
    eq(ui.modulesHelp.fsTip, "The modules in this string are already set the same here.")
end

function T.a_string_without_modules_shows_no_checkbox_and_the_box_resets_between_strings()
    boot({ encoding = false, modules = { ["m.cast"] = true } })
    seed()
    local MS = FS.ModuleSwitch
    local withModules = exportString("all")
    local FSMS = FS.ModuleSwitch
    FS.ModuleSwitch = nil
    local without = exportString("all")
    FS.ModuleSwitch = FSMS
    profilesPage()
    click("IMPORT", win())
    local ui = share().ui
    paste(without)
    no(ui.modulesBox:IsVisible(), "none carried")
    paste(withModules)
    yes(ui.modulesBox:IsVisible())
    ui.modulesBox.scripts.OnClick(ui.modulesBox)
    yes(ui.modulesBox.fsChecked)
    paste(without)
    no(ui.modulesBox:IsVisible())
    paste(withModules)
    no(ui.modulesBox.fsChecked, "a new string starts unticked")
end

-------------------------------------------------------------------------------
-- The changed marker's tip
-------------------------------------------------------------------------------

local function tipOf(label)
    for _, o in ipairs(ALL) do
        if o.kind == "FontString" and o:IsVisible() and o:GetText() == label then
            local r = owner(o, "fsHelp")
            if r then return r.fsHelp.fsTip end
        end
    end
end

function T.the_changed_tip_names_the_default()
    boot({ encoding = false })
    local W = FS.ConfigWindow
    W.RegisterCategory({ key = "demo", label = "Demo", group = "GENERAL", order = 50, tabs = { { key = "d", label = "Demo", build = function(content)
        local UI = W.UI
        UI.Toggle(content, { label = "Demo on", key = "demo.on", tip = "Tip on." })
        UI.Slider(content, { label = "Demo size", key = "demo.size", min = 4, max = 20, fmt = "%s px", tip = "Tip size." })
        UI.Segmented(content, { label = "Demo mode", key = "demo.mode", tip = "Tip mode.", options = {
            { value = "Auto", text = "Automatic" }, { value = "Left", text = "Left" } } })
        UI.Toggle(content, { label = "Demo shown", key = "demo.flag", inverted = true, tip = "Tip shown." })
    end } } })
    W.Open("demo")
    eq(tipOf("Demo on"), "Tip on.", "not changed: just the tip")
    FS.Config.Set("demo.on", true)
    W.RefreshAll()
    eq(tipOf("Demo on"), "Tip on.\nChanged. Default: off")
    FS.Config.Set("demo.size", 14)
    W.RefreshAll()
    eq(tipOf("Demo size"), "Tip size.\nChanged. Default: 10 px")
    FS.Config.Set("demo.mode", "Left")
    W.RefreshAll()
    eq(tipOf("Demo mode"), "Tip mode.\nChanged. Default: Automatic", "the option's own text")
    FS.Config.Set("demo.flag", false)
    W.RefreshAll()
    eq(tipOf("Demo shown"), "Tip shown.\nChanged. Default: off", "an inverted row names the inverse of the saved default")
    FS.Config.Set("demo.on", nil)
    W.RefreshAll()
    eq(tipOf("Demo on"), "Tip on.", "back to the default: the line is gone")
end

function T.the_changed_tip_without_a_registered_default_keeps_the_plain_line()
    boot({ encoding = false })
    local W = FS.ConfigWindow
    local on = false
    W.RegisterCategory({ key = "demo", label = "Demo", group = "GENERAL", order = 50, tabs = { { key = "d", label = "Demo", build = function(content)
        W.UI.Toggle(content, { label = "Own state", tip = "Tip own.", get = function() return on end, set = function(v) on = v end,
            isChanged = function() return on end, reset = function() on = false end })
    end } } })
    W.Open("demo")
    on = true
    W.RefreshAll()
    eq(tipOf("Own state"), "Tip own.\nChanged from the default.", "a get/set row has no key to look a default up by")
end

__checks = T
"""

SOURCE_RULES = [
    ("never_loads_code_from_a_string", CODEC_FILE, r"\b(loadstring|loadfile|dofile|setfenv|RunScript|getfenv)\b|(?<![\w.])load\s*\(",
     "ProfileCodec.lua runs or loads code"),
    ("codec_never_reaches_into_globals_by_name", CODEC_FILE, r"_G\s*\[", "ProfileCodec.lua indexes _G with a computed name"),
]

HOSTILE_TEXT = [
    b"return os.execute('boom')",
    b"function() os.exit() end",
    b"{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{{",
    b"n1e999;",
    b"s999999999:x",
]


def checksum(body: bytes) -> str:
    """The Lua codec's check word: Adler-32 style sums mod 65521, written as the high half then the low half in hex."""
    a, b = 1, 0
    for byte in body:
        a = (a + byte) % 65521
        b = (b + a) % 65521
    return f"{b:04x}{a:04x}"


def lua_runtime() -> "LuaRuntime":
    import base64

    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(cw.MOCK)
    lua.execute(EXTRA_MOCK)
    lua.globals().__session = lua.eval(cw.SESSION)
    lua.globals().__configSrc = CONFIG_FILE.read_text(encoding="utf-8")
    lua.globals().__codecSrc = CODEC_FILE.read_text(encoding="utf-8")
    lua.globals().__windowSrc = cw.to_lua(lua, window_sources())
    lua.globals().HOSTILE = cw.to_lua(lua, [base64.b64encode(t).decode() for t in HOSTILE_TEXT])
    # a payload nested far deeper than any profile, with the checksum right so only the depth can refuse it
    deep = b"{" * 100000
    lua.globals().HOSTILE_DEEP = base64.b64encode(checksum(deep).encode() + deep).decode()
    lua.execute(CHECKS)
    return lua


def window_sources() -> list[list[str]]:
    out = []
    for path in cw.config_files():
        if path.name not in WINDOW_PARTS:
            continue
        if path.name == "ConfigShare.lua":
            path = SHARE_FILE
        out.append([path.name, path.read_text(encoding="utf-8")])
    return out


def source_checks() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    for name, path, pattern, problem in SOURCE_RULES:
        src = path.read_text(encoding="utf-8") if path.exists() else ""
        # comments may name what the code does not do
        code = "\n".join(line.split("--", 1)[0] for line in src.splitlines())
        out.append((name, None if src and not re.search(pattern, code) else (problem if src else f"{path} does not exist")))
    for label, path in (("codec", CODEC_FILE), ("share", SHARE_FILE), ("config", CONFIG_FILE)):
        src = path.read_text(encoding="utf-8") if path.exists() else ""
        out.append((f"{label}_has_no_em_or_en_dash", "a dash character is in the file" if re.search("[–—]", src) else None))
    codec = CODEC_FILE.read_text(encoding="utf-8") if CODEC_FILE.exists() else ""
    out.append(("both_prefixes_are_in_the_codec", None if "STUW1" in codec and '"C"' in codec and '"L"' in codec
                else "the STUW1 prefix with the C and L codec letters is missing"))
    toc = [ln.strip() for ln in (ADDON / "forever-stuwave.toc").read_text(encoding="utf-8").splitlines()
           if ln.strip() and not ln.startswith("##")]
    problems = []
    for want in ("Core/ProfileCodec.lua", "Modules/Config/ConfigShare.lua"):
        if want not in toc:
            problems.append(f"{want} is not in the .toc")
    if not problems:
        if toc.index("Core/ProfileCodec.lua") < toc.index("Core/Config.lua"):
            problems.append("ProfileCodec.lua must load after Config.lua")
        if toc.index("Modules/Config/ConfigShare.lua") < toc.index("Modules/Config/ConfigWindow.lua"):
            problems.append("ConfigShare.lua must load after the window")
        if toc.index("Core/ProfileCodec.lua") > toc.index("Modules/Config/ConfigShare.lua"):
            problems.append("ProfileCodec.lua must load before ConfigShare.lua")
    out.append(("toc_order", "; ".join(problems) or None))
    return out


# Checks that provoke an error on purpose; every other check must forward none.
EXPECTS_ERRORS: set[str] = set()


def main() -> int:
    names = sorted(k for k in lua_runtime().eval("__checks").keys())
    failed = 0
    for name in names:
        # A fresh client per check: the saved variable, frames and callbacks must not leak.
        try:
            lua = lua_runtime()
            lua.eval("__checks")[name]()
            leaked = [] if name in EXPECTS_ERRORS else list(lua.eval("__errors").values())
            if leaked:
                raise LuaError(f"errors were forwarded to the error handler: {leaked}")
            print(f"ok    {name}")
        except LuaError as err:
            failed += 1
            print(f"FAIL  {name}: {err}")
    total = len(names)
    for name, problem in source_checks():
        total += 1
        if problem:
            failed += 1
            print(f"FAIL  {name}: {problem}")
        else:
            print(f"ok    {name}")
    print(f"{total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
