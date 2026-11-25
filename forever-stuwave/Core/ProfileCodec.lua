-- Forever STUwave: profile export and import string codec
-- FS.ProfileCodec turns the active profile into a text string and reads one back, as data only: nothing in a string is ever
-- run (no load, loadstring or dofile anywhere in this file). A string is "STUW1" + a codec letter + ":" + the payload:
--   STUW1C:  C_EncodingUtil: SerializeCBOR, CompressString (Deflate), EncodeBase64. Used on export only when every function
--            exists and a round trip gives the same table back.
--   STUW1L:  the in-house codec: a plain table serializer, an 8 digit check word in front, base64. No compression (a few KB).
-- The payload table is { v = 1, addon = version, name = profile name, settings = {}, layout = { v = 1, frames = {} },
-- modules = { [key] = on } }; settings, layout and modules are each optional.
--
-- Read(text) decodes, then Validate drops or clamps whatever this version does not know: settings need a registered default
-- of the same type (numbers are clamped to their row's min and max, text to its listed options), frame ids need a seat in
-- FS.Layout, module keys need a switch in FS.ModuleSwitch. What comes out is fresh tables; nothing aliases the string or
-- the saved profile. Config.ImportProfile then files it as a new profile (ConfigShare.lua owns the dialogs).

local _, FS = ...
local addonName = ...                -- the folder name, for the TOC version line

local Codec = FS.ProfileCodec or {}
FS.ProfileCodec = Codec

local VERSION = 1
local LAYOUT_VERSION = 1
local PREFIX = "STUW" .. VERSION

Codec.VERSION = VERSION
Codec.PREFIX = PREFIX

-- code -> the one line the dialog shows
Codec.REASON = {
    notprofile = "Not a STUwave profile string",
    newer = "Made by a newer STUwave",
    damaged = "Damaged string",
    unsupported = "This client cannot read this string",
}

-- Bounds, so a paste of any size or shape returns at once. A real profile is a few KB: the Lua codec at about 40 characters
-- a setting, the C codec far less. A Deflate stream cannot inflate more than about 1000 times, so MAX_C also bounds what
-- DecompressString may be asked to make (about 32 MB at worst).
local MAX_C = 32768          -- characters of a C string's payload
local MAX_L = 131072         -- characters of a Lua string's payload
local MAX_STRING = 4096      -- longest string inside a Lua payload
local MAX_NODES = 60000      -- values in a Lua payload
local MAX_DEPTH = 8          -- tables inside tables in a Lua payload
local MAX_ENTRIES = 20000    -- settings, frames or modules in one payload
local MAX_TEXT = 256         -- longest text a setting may hold
local MAX_LIST = 64          -- most items in a list or map setting (a list default may grow to twice its length)
local NUMBER_LIMIT = 1e6     -- the bound for a number whose row is not known (a tab nobody opened)
local NAME_MAX = 32

local floor, byte, char, find, sub, gsub, match = math.floor, string.byte, string.char, string.find, string.sub, string.gsub, string.match

-------------------------------------------------------------------------------
-- Base64 and a check word
-------------------------------------------------------------------------------

local ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
local B64_CHAR, B64_INDEX = {}, {}
for i = 1, 64 do
    local c = sub(ALPHABET, i, i)
    B64_CHAR[i - 1] = c
    B64_INDEX[byte(c)] = i - 1
end

local function Base64Encode(s)
    local out, n = {}, 0
    local len = #s
    for i = 1, len - 2, 3 do
        local a, b, c = byte(s, i, i + 2)
        local v = a * 65536 + b * 256 + c
        n = n + 1
        out[n] = B64_CHAR[floor(v / 262144)] .. B64_CHAR[floor(v / 4096) % 64] .. B64_CHAR[floor(v / 64) % 64] .. B64_CHAR[v % 64]
    end
    local rest = len % 3
    if rest == 1 then
        local v = byte(s, len) * 65536
        out[n + 1] = B64_CHAR[floor(v / 262144)] .. B64_CHAR[floor(v / 4096) % 64] .. "=="
    elseif rest == 2 then
        local a, b = byte(s, len - 1, len)
        local v = a * 65536 + b * 256
        out[n + 1] = B64_CHAR[floor(v / 262144)] .. B64_CHAR[floor(v / 4096) % 64] .. B64_CHAR[floor(v / 64) % 64] .. "="
    end
    return table.concat(out)
end

-- The bytes, or nil when `s` is not base64 (padding may be missing; a stray = in the middle is not base64).
local function Base64Decode(s)
    s = gsub(s, "=+$", "")
    local len = #s
    if len == 0 or len % 4 == 1 or find(s, "=", 1, true) then return nil end
    local out, n = {}, 0
    local whole = len - len % 4
    for i = 1, whole, 4 do
        local a, b, c, d = byte(s, i, i + 3)
        a, b, c, d = B64_INDEX[a], B64_INDEX[b], B64_INDEX[c], B64_INDEX[d]
        if not (a and b and c and d) then return nil end
        local v = a * 262144 + b * 4096 + c * 64 + d
        n = n + 1
        out[n] = char(floor(v / 65536), floor(v / 256) % 256, v % 256)
    end
    local rest = len % 4
    if rest == 2 then
        local a, b = B64_INDEX[byte(s, whole + 1)], B64_INDEX[byte(s, whole + 2)]
        if not (a and b) then return nil end
        out[n + 1] = char(floor((a * 262144 + b * 4096) / 65536))
    elseif rest == 3 then
        local a, b, c = B64_INDEX[byte(s, whole + 1)], B64_INDEX[byte(s, whole + 2)], B64_INDEX[byte(s, whole + 3)]
        if not (a and b and c) then return nil end
        local v = a * 262144 + b * 4096 + c * 64
        out[n + 1] = char(floor(v / 65536), floor(v / 256) % 256)
    end
    return table.concat(out)
end

-- Adler-32 style sums, high half then low half, 8 hex digits. Catches a cut, a changed or an inserted character.
local function Checksum(s)
    local a, b = 1, 0
    for i = 1, #s do
        a = (a + byte(s, i)) % 65521
        b = (b + a) % 65521
    end
    return ("%04x%04x"):format(b, a)
end

-------------------------------------------------------------------------------
-- The Lua codec: serialize and parse plain tables
--
--   T / F            booleans
--   n<number>;       a number (never NaN or infinite)
--   s<length>:<text> a string, any bytes
--   { key value ... }  a table; keys are strings or numbers
-------------------------------------------------------------------------------

local MALFORMED = "malformed"

local function FormatNumber(n)
    local text = ("%.14g"):format(n)
    if tonumber(text) ~= n then text = ("%.17g"):format(n) end
    return text
end

local function SortedKeys(t)
    local numbers, strings = {}, {}
    for key in pairs(t) do
        local kind = type(key)
        if kind == "number" then
            numbers[#numbers + 1] = key
        elseif kind == "string" then
            strings[#strings + 1] = key
        else
            error(MALFORMED, 0)
        end
    end
    table.sort(numbers)
    table.sort(strings)
    for i = 1, #strings do numbers[#numbers + 1] = strings[i] end
    return numbers
end

local function SerializeInto(out, value, depth)
    local kind = type(value)
    if kind == "string" then
        out[#out + 1] = "s" .. #value .. ":" .. value
    elseif kind == "boolean" then
        out[#out + 1] = value and "T" or "F"
    elseif kind == "number" then
        if value ~= value or value - value ~= 0 then error(MALFORMED, 0) end
        out[#out + 1] = "n" .. FormatNumber(value) .. ";"
    elseif kind == "table" then
        if depth >= MAX_DEPTH then error(MALFORMED, 0) end
        out[#out + 1] = "{"
        for _, key in ipairs(SortedKeys(value)) do
            SerializeInto(out, key, depth + 1)
            SerializeInto(out, value[key], depth + 1)
        end
        out[#out + 1] = "}"
    else
        error(MALFORMED, 0)
    end
end

local nodes = 0

-- Returns the value and the position after it; raises MALFORMED for anything else.
local function ParseValue(s, pos, depth)
    nodes = nodes + 1
    if nodes > MAX_NODES then error(MALFORMED, 0) end
    local c = byte(s, pos)
    if c == 84 then return true, pos + 1 end           -- T
    if c == 70 then return false, pos + 1 end          -- F
    if c == 110 then                                    -- n
        local stop = find(s, ";", pos + 1, true)
        if not stop or stop - pos > 32 then error(MALFORMED, 0) end
        local text = sub(s, pos + 1, stop - 1)
        if not find(text, "^[%d%+%-%.eE]+$") then error(MALFORMED, 0) end
        local number = tonumber(text)
        if not number or number ~= number or number - number ~= 0 then error(MALFORMED, 0) end
        return number, stop + 1
    end
    if c == 115 then                                    -- s
        local colon = find(s, ":", pos + 1, true)
        if not colon or colon - pos > 8 then error(MALFORMED, 0) end
        local digits = sub(s, pos + 1, colon - 1)
        if not find(digits, "^%d+$") then error(MALFORMED, 0) end
        local length = tonumber(digits)
        if length > MAX_STRING or colon + length > #s then error(MALFORMED, 0) end
        return sub(s, colon + 1, colon + length), colon + length + 1
    end
    if c == 123 then                                    -- {
        if depth >= MAX_DEPTH then error(MALFORMED, 0) end
        local t, p = {}, pos + 1
        while true do
            local nextByte = byte(s, p)
            if nextByte == 125 then return t, p + 1 end
            if nextByte == nil then error(MALFORMED, 0) end
            local key, value
            key, p = ParseValue(s, p, depth + 1)
            local kind = type(key)
            if kind ~= "string" and kind ~= "number" then error(MALFORMED, 0) end
            value, p = ParseValue(s, p, depth + 1)
            t[key] = value
        end
    end
    error(MALFORMED, 0)
end

local function EncodeLua(payload)
    local out = {}
    SerializeInto(out, payload, 0)
    local body = table.concat(out)
    return Base64Encode(Checksum(body) .. body)
end

-- The table, or nil when the payload is not one of ours.
local function DecodeLua(text)
    local raw = Base64Decode(text)
    if not raw or #raw < 10 then return nil end
    local want, body = sub(raw, 1, 8), sub(raw, 9)
    if Checksum(body) ~= want then return nil end
    nodes = 0
    local ok, value, pos = pcall(ParseValue, body, 1, 0)
    if not ok or pos ~= #body + 1 or type(value) ~= "table" then return nil end
    return value
end

-------------------------------------------------------------------------------
-- The C codec: C_EncodingUtil
-------------------------------------------------------------------------------

local ENCODING_FUNCTIONS = { "SerializeCBOR", "DeserializeCBOR", "CompressString", "DecompressString", "EncodeBase64", "DecodeBase64" }

local function EncodingApi()
    local api = _G.C_EncodingUtil
    if type(api) ~= "table" then return nil end
    for _, name in ipairs(ENCODING_FUNCTIONS) do
        if type(api[name]) ~= "function" then return nil end
    end
    return api
end

function Codec.CanUseEncodingApi()
    return EncodingApi() ~= nil
end

local function DeflateMethod()
    local enum = _G.Enum
    local methods = type(enum) == "table" and enum.CompressionMethod or nil
    if type(methods) == "table" then return methods.Deflate end
end

-- One call into the engine: its result, or nil when it threw or answered a secret.
local function Call(fn, input, method)
    local ok, result
    if method ~= nil then ok, result = pcall(fn, input, method) else ok, result = pcall(fn, input) end
    if not ok then return nil end
    local isSecret = _G.issecretvalue
    if isSecret and isSecret(result) then return nil end
    return result
end

local function EncodeC(payload)
    local api = EncodingApi()
    if not api then return nil end
    local cbor = Call(api.SerializeCBOR, payload)
    if type(cbor) ~= "string" or cbor == "" then return nil end
    local packed = Call(api.CompressString, cbor, DeflateMethod())
    if type(packed) ~= "string" or packed == "" then return nil end
    local text = Call(api.EncodeBase64, packed)
    if type(text) ~= "string" or not find(text, "^[%w%+/=_%-]+$") then return nil end
    return text
end

-- The table, or nil and the reason code.
local function DecodeC(text)
    local api = EncodingApi()
    if not api then return nil, "unsupported" end
    local packed = Call(api.DecodeBase64, text)
    if type(packed) ~= "string" or packed == "" then return nil, "damaged" end
    local cbor = Call(api.DecompressString, packed, DeflateMethod())
    if type(cbor) ~= "string" or cbor == "" then return nil, "damaged" end
    local value = Call(api.DeserializeCBOR, cbor)
    if type(value) ~= "table" then return nil, "damaged" end
    return value
end

local function Same(a, b, depth)
    if type(a) ~= type(b) then return false end
    if type(a) == "table" then
        if depth > MAX_DEPTH + 2 then return false end
        for key, value in pairs(a) do
            if not Same(value, b[key], depth + 1) then return false end
        end
        for key in pairs(b) do
            if a[key] == nil then return false end
        end
        return true
    end
    return a == b
end

-------------------------------------------------------------------------------
-- Strings: encode and decode
-------------------------------------------------------------------------------

-- The text of `payload` as a string, and which codec made it. kind nil = C when the client has it and the round trip holds,
-- else Lua; "C" or "L" asks for one (nil and a reason when it cannot). The payload is written as it is: Validate first.
function Codec.Encode(payload, kind)
    if type(payload) ~= "table" then return nil, "damaged" end
    if kind == nil or kind == "C" then
        local body = EncodeC(payload)
        if body then
            local back = DecodeC(body)
            if back and Same(payload, back, 0) then return PREFIX .. "C:" .. body, "C" end
        end
        if kind == "C" then return nil, "unsupported" end
    end
    local ok, body = pcall(EncodeLua, payload)
    if not ok then return nil, "damaged" end
    return PREFIX .. "L:" .. body, "L"
end

-- Finds "STUW<version><letter>:" anywhere in `text` (words around it, quotes, line breaks inside it are fine) and takes the
-- run of base64 characters after it.
local function Extract(text)
    if type(text) ~= "string" then return nil end
    local compact = gsub(text, "%s+", "")
    local init = 1
    while true do
        local at = find(compact, "STUW", init, true)
        if not at then return nil end
        local digits, letter = match(compact, "^STUW(%d+)(%a):", at)
        if digits then
            local start = at + 4 + #digits + 2
            return tonumber(digits), letter, match(compact, "^[%w%+/=_%-]*", start)
        end
        init = at + 1
    end
end

-- The raw payload table (nothing checked inside it yet), the codec letter; or nil and a reason code.
function Codec.Decode(text)
    local version, letter, body = Extract(text)
    if not version then return nil, "notprofile" end
    if version < 1 then return nil, "notprofile" end
    if version > VERSION or (letter ~= "C" and letter ~= "L") then return nil, "newer" end
    if #body == 0 or #body > (letter == "C" and MAX_C or MAX_L) then return nil, "damaged" end
    local payload, code
    if letter == "C" then
        payload, code = DecodeC(body)
    else
        payload, code = DecodeLua(body), "damaged"
    end
    if not payload then return nil, code end
    return payload, letter
end

-------------------------------------------------------------------------------
-- Validation
-------------------------------------------------------------------------------

local function Finite(v)
    return type(v) == "number" and v == v and v - v == 0
end

-- Text for a name or a version: no control characters, no escape pipes, trimmed, at most `max` characters.
local function CleanText(text, max)
    if type(text) ~= "string" then return nil end
    text = gsub(gsub(text, "%c", ""), "|", "")
    text = match(text, "^%s*(.-)%s*$")
    if text == "" then return nil end
    local chars = 0
    for start in text:gmatch("()[\1-\127\194-\244][\128-\191]*") do
        chars = chars + 1
        if chars > max then return (gsub(sub(text, 1, start - 1), "%s+$", "")) end
    end
    return text
end

local function CleanVersion(text)
    if type(text) == "string" and #text <= 32 and find(text, "^[%w%.%-_+]+$") then return text end
end

-- Text a setting may hold: short, no control characters, and no escape pipe unless the default has one.
local function PlainText(value, sample)
    if #value > MAX_TEXT or find(value, "%c") then return false end
    if find(value, "|", 1, true) and not (type(sample) == "string" and find(sample, "|", 1, true)) then return false end
    return true
end

local function Member(list, value)
    for i = 1, #list do
        if list[i] == value then return true end
    end
    return false
end

-- The value fitted to the type of its default `def` and to its row's limits `lim` ({ min, max, options }), or nil to drop it;
-- the second result is true when a number was moved to fit.
local function FitScalar(value, def, lim)
    local kind = type(def)
    if type(value) ~= kind then return nil end
    if kind == "boolean" then return value, false end
    if kind == "number" then
        if not Finite(value) then return nil end
        if lim and lim.options and not Member(lim.options, value) then return nil end
        local lo = lim and lim.min or -NUMBER_LIMIT
        local hi = lim and lim.max or NUMBER_LIMIT
        local fixed = value
        if fixed < lo then fixed = lo elseif fixed > hi then fixed = hi end
        return fixed, fixed ~= value
    end
    if kind == "string" then
        if not PlainText(value, def) then return nil end
        if lim and lim.options and not Member(lim.options, value) then return nil end
        return value, false
    end
    return nil
end

-- A list or map setting: a list default takes a list of the same kind of item, anything else a flat map of plain values.
local function FitTable(value, def)
    if type(value) ~= "table" then return nil end
    local n = 0
    for _ in pairs(value) do
        n = n + 1
        if n > 2 * MAX_LIST then return nil end
    end
    local copy = {}
    if #def > 0 then
        local sample = def[1]
        if type(sample) == "table" or n > math.max(MAX_LIST, 2 * #def) then return nil end
        for i = 1, n do
            local item = value[i]
            if item == nil then return nil end
            local fixed = FitScalar(item, sample, nil)
            if fixed == nil then return nil end
            copy[i] = fixed
        end
        return copy
    end
    if n > MAX_LIST then return nil end
    for key, item in pairs(value) do
        local keyKind, itemKind = type(key), type(item)
        if keyKind == "string" then
            if #key > 64 then return nil end
        elseif keyKind ~= "number" then
            return nil
        end
        if itemKind == "string" then
            if not PlainText(item, nil) then return nil end
        elseif itemKind == "number" then
            if not Finite(item) then return nil end
        elseif itemKind ~= "boolean" then
            return nil
        end
        copy[key] = item
    end
    return copy
end

local function LayoutKnown(id)
    local layout = FS.Layout
    if type(layout) ~= "table" or type(id) ~= "string" or sub(id, 1, 1) == "_" then return false end
    local entry = layout[id]
    return type(entry) == "table" and Finite(entry.x) and Finite(entry.y)
end

local function LayoutLimit()
    local layout = FS.Layout
    local width = type(layout) == "table" and Finite(layout.DESIGN_W) and layout.DESIGN_W or 2560
    return 2 * width
end

local function ModuleSwitch()
    local switch = FS.ModuleSwitch
    if type(switch) == "table" and type(switch.Snapshot) == "function" and type(switch.Set) == "function"
        and type(switch.Label) == "function" then
        return switch
    end
end

-- Registers where the rows' own limits come from: fn() returns { [key] = { min, max, options = { value, ... } } }. The
-- config window does this; the codec itself knows nothing of rows.
function Codec.SetLimitSource(fn)
    Codec.limitSource = type(fn) == "function" and fn or nil
end

local function Resolve(env)
    env = env or {}
    local ctx = {
        default = env.default or (FS.Config and FS.Config.GetDefault) or function() return nil end,
        layoutKnown = env.layoutKnown or LayoutKnown,
    }
    local limits = env.limits
    if limits == nil and Codec.limitSource then
        local ok, result = pcall(Codec.limitSource)
        if ok and type(result) == "table" then limits = result end
    end
    ctx.limits = limits
    return ctx
end

local function FitSettings(settings, ctx, report)
    local out, seen = {}, 0
    for key, value in pairs(settings) do
        seen = seen + 1
        if seen > MAX_ENTRIES then return nil end
        local def
        if type(key) == "string" then def = ctx.default(key) end   -- false is a default too
        if def == nil then
            report.ignored = report.ignored + 1
        else
            local fixed, moved
            if type(def) == "table" then
                fixed = FitTable(value, def)
            else
                fixed, moved = FitScalar(value, def, ctx.limits and ctx.limits[key])
            end
            if fixed == nil then
                report.ignored = report.ignored + 1
            else
                if moved then report.clamped = report.clamped + 1 end
                -- a value that is the default here is stored as nothing, so it is not a setting of the profile
                if fixed ~= def or type(fixed) == "table" then
                    out[key] = fixed
                    report.settings = report.settings + 1
                end
            end
        end
    end
    return out
end

local function Clamp(v, limit)
    if v < -limit then return -limit elseif v > limit then return limit end
    return v
end

-- The cleaned layout, or nil and a reason code.
local function FitLayout(layout, ctx, report)
    if type(layout) ~= "table" then return nil, "damaged" end
    local version = layout.v
    if version ~= nil then
        if type(version) ~= "number" then return nil, "damaged" end
        if version > LAYOUT_VERSION then return nil, "newer" end
    end
    local frames = layout.frames
    if frames == nil then frames = {} end
    if type(frames) ~= "table" then return nil, "damaged" end
    local out, seen, limit = {}, 0, LayoutLimit()
    for id, pos in pairs(frames) do
        seen = seen + 1
        if seen > MAX_ENTRIES then return nil, "damaged" end
        if type(id) ~= "string" or not ctx.layoutKnown(id) or type(pos) ~= "table" or not (Finite(pos.x) and Finite(pos.y)) then
            report.ignored = report.ignored + 1
        else
            local x, y = Clamp(pos.x, limit), Clamp(pos.y, limit)
            if x ~= pos.x or y ~= pos.y then report.clamped = report.clamped + 1 end
            out[id] = { x = x, y = y }
            report.frames = report.frames + 1
        end
    end
    return { v = LAYOUT_VERSION, frames = out }
end

local function FitModules(modules, report)
    if type(modules) ~= "table" then return nil, "damaged" end
    local switch = ModuleSwitch()
    if not switch then return nil end
    local out, seen = {}, 0
    for key, on in pairs(modules) do
        seen = seen + 1
        if seen > MAX_ENTRIES then return nil, "damaged" end
        local ok, label = false, nil
        if type(key) == "string" and type(on) == "boolean" then ok, label = pcall(switch.Label, key) end
        if ok and label ~= nil then
            out[key] = on
            report.modules = report.modules + 1
        else
            report.ignored = report.ignored + 1
        end
    end
    return out
end

-- Checks a decoded payload. Returns the clean payload and a report { settings, frames, modules, ignored, clamped } (counts of
-- what was kept, dropped and moved), or nil and a reason code. `env` ({ default, limits, layoutKnown }) overrides where the
-- defaults, the rows' limits and the frame ids come from.
function Codec.Validate(payload, env)
    if type(payload) ~= "table" then return nil, "damaged" end
    local version = payload.v
    if type(version) ~= "number" or version ~= version or version < 1 or version ~= floor(version) then return nil, "damaged" end
    if version > VERSION then return nil, "newer" end
    local present = 0
    for _, name in ipairs({ "settings", "layout", "modules" }) do
        local section = payload[name]
        if section ~= nil then
            if type(section) ~= "table" then return nil, "damaged" end
            present = present + 1
        end
    end
    if present == 0 then return nil, "damaged" end
    local ctx = Resolve(env)
    local report = { settings = 0, frames = 0, modules = 0, ignored = 0, clamped = 0 }
    local clean = { v = VERSION, name = CleanText(payload.name, NAME_MAX), addon = CleanVersion(payload.addon) }
    if payload.settings ~= nil then
        clean.settings = FitSettings(payload.settings, ctx, report)
        if not clean.settings then return nil, "damaged" end
    end
    if payload.layout ~= nil then
        local layout, code = FitLayout(payload.layout, ctx, report)
        if not layout then return nil, code end
        clean.layout = layout
    end
    if payload.modules ~= nil then
        local modules, code = FitModules(payload.modules, report)
        if code then return nil, code end
        clean.modules = modules
    end
    return clean, report
end

-------------------------------------------------------------------------------
-- Reading a string
-------------------------------------------------------------------------------

-- Decodes and validates `text`. Returns { payload, report, kind, info } or nil, a reason code and its line.
function Codec.Read(text, env)
    local payload, kind = Codec.Decode(text)
    if not payload then return nil, kind, Codec.REASON[kind] end   -- on a failure the second value is the reason code
    local clean, report = Codec.Validate(payload, env)
    if not clean then return nil, report, Codec.REASON[report] end
    return { payload = clean, report = report, kind = kind, info = Codec.Info(clean, report, kind) }
end

-- What a dialog says about a payload.
function Codec.Info(clean, report, kind)
    return {
        name = clean.name, addon = clean.addon, kind = kind,
        settings = report.settings, frames = report.frames, modules = report.modules,
        hasSettings = clean.settings ~= nil, hasLayout = clean.layout ~= nil,
        ignored = report.ignored, clamped = report.clamped,
    }
end

-- "48 settings and 14 frame positions"
function Codec.CountsText(info)
    local parts = {}
    if info.hasSettings then
        parts[#parts + 1] = ("%d setting%s"):format(info.settings, info.settings == 1 and "" or "s")
    end
    if info.hasLayout then
        parts[#parts + 1] = ("%d frame position%s"):format(info.frames, info.frames == 1 and "" or "s")
    end
    if #parts == 0 then return "module switches only" end
    return table.concat(parts, " and ")
end

-------------------------------------------------------------------------------
-- Writing a string
-------------------------------------------------------------------------------

local function AddonVersion()
    local get = _G.C_AddOns and _G.C_AddOns.GetAddOnMetadata or _G.GetAddOnMetadata
    if type(get) ~= "function" then return nil end
    local ok, value = pcall(get, addonName, "Version")
    if ok and type(value) == "string" and value ~= "" then return value end
end

-- The active profile's stored settings and layout frames, straight from the saved variable (Config keeps the schema).
local function ReadActive()
    local db = _G.ForeverSTUwaveDB
    local config = FS.Config
    local profile = type(db) == "table" and type(db.profiles) == "table" and config and config.ActiveProfile
        and db.profiles[config.ActiveProfile()] or nil
    if type(profile) ~= "table" then return {}, {} end
    local settings = type(profile.settings) == "table" and profile.settings or {}
    local layout = profile.layout
    local frames = type(layout) == "table" and type(layout.frames) == "table" and layout.frames or {}
    return settings, frames
end

-- The clean payload of the active profile for a Share choice ("all", "settings" or "layout") and its report. It goes through
-- the same Validate an import does, so a string holds exactly what an import of it keeps. Module switches ride along on
-- every choice when ModuleSwitch exists.
function Codec.BuildPayload(what, env)
    if what ~= "settings" and what ~= "layout" then what = "all" end
    local config = FS.Config
    local settings, frames = ReadActive()
    local raw = { v = VERSION, addon = AddonVersion(), name = config and config.ActiveProfile and config.ActiveProfile() or nil }
    if what ~= "layout" then raw.settings = settings end
    if what ~= "settings" then raw.layout = { v = LAYOUT_VERSION, frames = frames } end
    local switch = ModuleSwitch()
    if switch then
        local ok, snapshot = pcall(switch.Snapshot)
        if ok and type(snapshot) == "table" then raw.modules = snapshot end
    end
    return Codec.Validate(raw, env)
end

-- The string for the active profile and what it says (see Info), or nil and a reason code.
function Codec.Export(what, kind)
    local clean, report = Codec.BuildPayload(what)
    if not clean then return nil, { error = report } end
    local text, used = Codec.Encode(clean, kind)
    if not text then return nil, { error = used } end
    return text, Codec.Info(clean, report, used)
end
