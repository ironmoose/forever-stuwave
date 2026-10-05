#!/usr/bin/env python3
"""Runs the real ChatFrameSkin.lua and ChatSlashCommands.lua headless against a mock WoW API.

Parker: "lets also default the chat to 14pt". Nothing in the addon set the chat font size,
so each window wore Blizzard's per-window size (the stock default is
CHAT_FRAME_DEFAULT_FONT_SIZE = 18, and an unset chat-cache size of 0 means "use 18").
These checks pin the addon's own default:

  * every skinned message frame gets ForeverSynthwaveDB.chatFontSize (14 when nil or
    invalid) through Blizzard's own FCF_SetChatWindowFontSize, so the chat-cache
    (SetChatWindowSize) agrees with what is shown, keeping the frame's face and flags;
  * the saved variables do not exist when the files load, so PLAYER_LOGIN re-applies, and
    so does UPDATE_CHAT_WINDOWS (Blizzard resets each frame to the cached size there);
  * /fschat size N validates 10-24, saves and applies; /fschat size prints it;
  * a late window (whisper / tear-off) gets it;
  * re-applying writes nothing when the size already matches (no event loop);
  * the edit box and the tab strip fonts are never touched;
  * a missing FCF function falls back to SetChatWindowSize + SetFont; a throwing API is
    contained.

ChatFrameSkin.lua and ChatSlashCommands.lua are the real files; every other Chat export is a
no-op stub and the frames are a recording mock, NOT the real client.

    python3 tools/chatfont-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ADDON = Path(__file__).resolve().parent.parent / "addon" / "ForeverSynthwave"

MOCK = r"""
__combat = false
__frames = {}
__printed = {}
__timers = {}

local Frame = {}
Frame.__index = Frame
function Frame:RegisterEvent(e) self._events[e] = true end
function Frame:UnregisterEvent(e) self._events[e] = nil end
function Frame:SetScript(k, fn) self._scripts[k] = fn end
function Frame:SetPoint() end
function Frame:ClearAllPoints() end
function Frame:SetFrameLevel() end
function Frame:GetFrameLevel() return 1 end
function Frame:GetID() return self._id end
function Frame:GetName() return self._name end
function Frame:GetChildren() return end
-- A font owner: records every SetFont so "no write" and "never touched" are countable.
function Frame:SetFont(face, size, flags)
    self._font = { face, size, flags }
    self.setFontCalls = (self.setFontCalls or 0) + 1
end
function Frame:GetFont()
    local f = self._font
    if not f then return end
    return f[1], f[2], f[3]
end

function CreateFrame()
    local f = setmetatable({ _events = {}, _scripts = {} }, Frame)
    __frames[#__frames + 1] = f
    return f
end
function InCombatLockdown() return __combat end
function __fire(event, ...)
    for _, f in ipairs(__frames) do
        if f._events[event] and f._scripts.OnEvent then f._scripts.OnEvent(f, event, ...) end
    end
end
function print(...)
    local parts = {}
    for i = 1, select("#", ...) do parts[#parts + 1] = tostring((select(i, ...))) end
    __printed[#__printed + 1] = table.concat(parts, " ")
end

function hooksecurefunc(name, fn)
    local orig = _G[name]
    assert(type(orig) == "function", "hooksecurefunc: " .. tostring(name) .. " is not a function")
    _G[name] = function(...)
        local r = { orig(...) }
        fn(...)
        return unpack(r)
    end
end
function geterrorhandler() return function() end end
C_Timer = { After = function(_, fn) __timers[#__timers + 1] = fn end }

SlashCmdList = {}
-- No saved variables while the files load, as on the client.
ForeverSynthwaveDB = nil

-- Blizzard's chat-cache: GetChatWindowInfo / SetChatWindowSize, size 0 = never set.
__cache = {}
__cacheWrites = 0
__throwCache = false
function GetChatWindowInfo(id) return "Window" .. id, __cache[id] or 0, 0, 0, 0, 1, true end
function SetChatWindowSize(id, size)
    if __throwCache then error("SetChatWindowSize exploded") end
    __cache[id] = size
    __cacheWrites = __cacheWrites + 1
end
-- FloatingChatFrame.lua FCF_SetChatWindowFontSize, minus the GM/Communities frames.
__fcfCalls = 0
function FCF_SetChatWindowFontSize(self, chatFrame, fontSize)
    __fcfCalls = __fcfCalls + 1
    local fontFile, unused, fontFlags = chatFrame:GetFont()
    chatFrame:SetFont(fontFile, fontSize, fontFlags)
    SetChatWindowSize(chatFrame:GetID(), fontSize)
end

-- A chat window as Blizzard builds it: stock face and flags, an edit box and a tab that
-- must never be touched.
FACE, FLAGS = "Fonts\\FRIZQT__.TTF", "OUTLINE"
local function newChat(id, size)
    local f = CreateFrame()
    f._id, f._name = id, "ChatFrame" .. id
    f._font = { FACE, size or 12, FLAGS }
    f.setFontCalls = 0
    local eb, tab = CreateFrame(), CreateFrame()
    eb._font, tab._font = { FACE, 14, "" }, { FACE, 12, "" }
    eb.setFontCalls, tab.setFontCalls = 0, 0
    _G["ChatFrame" .. id] = f
    _G["ChatFrame" .. id .. "EditBox"] = eb
    _G["ChatFrame" .. id .. "Tab"] = tab
    f.eb, f.tab = eb, tab
    return f
end
__newChat = newChat

-- Blizzard's handler for UPDATE_CHAT_WINDOWS (ChatFrameOverrides.lua): each frame goes back to
-- the cached size, 0 meaning the stock 18. Registered before every addon file, so it runs first.
function __blizzardReset(count)
    for i = 1, count do
        local f = _G["ChatFrame" .. i]
        local cached = __cache[i] or 0
        local size = cached == 0 and 18 or cached
        local face, _, flags = f:GetFont()
        f:SetFont(face, size, flags)
    end
end
"""

LOAD = r"""
function(file, src, fs)
    local chunk = assert(load(src, "@" .. file))
    chunk("ForeverSynthwave", fs)
end
"""

SETUP = r"""
-- Every Chat export the real files call is a no-op unless defined here.
local Chat = setmetatable({}, { __index = function() return function() end end })
Chat.MAX_CHAT_FRAMES = 3
Chat.LEVEL_BACKDROP = 1
Chat.windowState = "normal"
Chat.skinnedChatFrames = {}
Chat.termPanel = CreateFrame()
Chat.DockedChatFrames = function() return {} end
Chat.AnchorBackdrop = function() end
-- Production's first act (ChatWindowState.lua) is a placeholder table; the client replaces it
-- with the saved one after the files have run.
Chat.HookPrimaryChatReseat = function() ForeverSynthwaveDB = ForeverSynthwaveDB or {} end
FS = { Chat = Chat, Theme = {} }
"""

CHECKS = r"""
local T = {}
local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end
local function sizeOf(f) return select(2, f:GetFont()) end
local function login()
    ForeverSynthwaveDB = ForeverSynthwaveDB or {}
    __fire("PLAYER_LOGIN")
end
local function lastPrint() return __printed[#__printed] or "" end
local function slash(msg) SlashCmdList["FSCHAT"](msg) end

function T.default_14_on_every_skinned_window()
    login()
    for i = 1, 3 do
        local f = _G["ChatFrame" .. i]
        eq(sizeOf(f), 14, "ChatFrame" .. i .. " size")
        eq(__cache[i], 14, "ChatFrame" .. i .. " chat-cache size")
    end
end

function T.nothing_written_at_load()
    -- the files ran at load over a placeholder table: a write now could be the wrong size
    eq(type(ForeverSynthwaveDB), "table", "placeholder like production")
    for i = 1, 3 do eq(sizeOf(_G["ChatFrame" .. i]), 12, "ChatFrame" .. i) end
    eq(__cacheWrites, 0, "chat-cache written at load")
    eq(__fcfCalls, 0, "Blizzard's setter called at load")
    login()
    eq(sizeOf(ChatFrame1), 14, "applied once the table exists")
end

function T.apply_reports_whether_it_wrote()
    login()
    eq(FS.Chat.ApplyFontSize(ChatFrame1), false, "already at size")
    ForeverSynthwaveDB.chatFontSize = 16
    eq(FS.Chat.ApplyFontSize(ChatFrame1), true, "changed")
    eq(FS.Chat.ApplyFontSize(ChatFrame1), false, "repeat")
end

function T.menu_choice_sticks_without_a_saved_size()
    login()
    FCF_SetChatWindowFontSize(nil, ChatFrame1, 16)   -- Blizzard's font menu: no event
    __blizzardReset(3)                               -- next login / UPDATE_CHAT_WINDOWS
    __fire("UPDATE_CHAT_WINDOWS")
    eq(sizeOf(ChatFrame1), 16, "menu choice reverted")
    eq(__cache[1], 16, "menu choice's cache reverted")
    eq(sizeOf(ChatFrame2), 14, "an untouched window stays at the default")
    -- a window reset to stock (cache 0, or 18) is still defaulted
    FCF_SetChatWindowFontSize(nil, ChatFrame3, 18)
    __fire("UPDATE_CHAT_WINDOWS")
    eq(sizeOf(ChatFrame3), 14, "a stock 18 window")
end

function T.saved_size_overrides_a_menu_choice()
    login()
    slash("size 20")
    FCF_SetChatWindowFontSize(nil, ChatFrame1, 16)
    __fire("UPDATE_CHAT_WINDOWS")
    eq(sizeOf(ChatFrame1), 20, "the saved size enforces on every window")
    ForeverSynthwaveDB.chatFontSize = 14
    FCF_SetChatWindowFontSize(nil, ChatFrame2, 16)
    __fire("UPDATE_CHAT_WINDOWS")
    eq(sizeOf(ChatFrame2), 14, "a saved 14 enforces too")
end

function T.face_and_flags_kept()
    login()
    for i = 1, 3 do
        local face, _, flags = _G["ChatFrame" .. i]:GetFont()
        eq(face, FACE, "face"); eq(flags, FLAGS, "flags")
    end
end

function T.saved_size_honoured_at_login()
    ForeverSynthwaveDB = { chatFontSize = 18 }   -- the client replaces the table after the files load
    login()
    eq(sizeOf(ChatFrame1), 18); eq(sizeOf(ChatFrame3), 18); eq(__cache[2], 18)
end

function T.invalid_saved_size_falls_back_to_14()
    for _, bad in ipairs({ "big", 9, 25, 14.5, -3, 0, true }) do
        ForeverSynthwaveDB = { chatFontSize = bad }
        login()
        eq(sizeOf(ChatFrame1), 14, "saved " .. tostring(bad))
    end
end

function T.blizzard_reset_is_reapplied()
    login()
    __cache = {}                       -- the cache lost it: stock reset goes to 18
    __blizzardReset(3)
    eq(sizeOf(ChatFrame1), 18, "Blizzard's own reset ran first")
    __fire("UPDATE_CHAT_WINDOWS")
    for i = 1, 3 do eq(sizeOf(_G["ChatFrame" .. i]), 14, "ChatFrame" .. i) end
    eq(__cache[1], 14, "chat-cache rewritten")
    __cache[2] = 0                     -- unset again: Blizzard's reset puts the window back to 18
    __blizzardReset(3)
    eq(sizeOf(ChatFrame2), 18, "Blizzard's own reset ran first")
    __fire("UPDATE_FLOATING_CHAT_WINDOWS")
    eq(sizeOf(ChatFrame2), 14, "floating update too")
end

function T.slash_size_saves_and_applies()
    login()
    slash("size 20")
    eq(ForeverSynthwaveDB.chatFontSize, 20, "saved")
    for i = 1, 3 do eq(sizeOf(_G["ChatFrame" .. i]), 20); eq(__cache[i], 20) end
    local face, _, flags = ChatFrame1:GetFont()
    eq(face, FACE); eq(flags, FLAGS)
    slash("SIZE   12")
    eq(ForeverSynthwaveDB.chatFontSize, 12); eq(sizeOf(ChatFrame2), 12)
    -- and the next login keeps it
    __blizzardReset(3); __fire("UPDATE_CHAT_WINDOWS")
    eq(sizeOf(ChatFrame1), 12, "survives a Blizzard reset")
end

function T.slash_size_prints_current()
    login()
    slash("size")
    assert(lastPrint():find("14", 1, true), "prints default: " .. lastPrint())
    slash("size 18")
    __printed = {}
    slash("size")
    assert(lastPrint():find("18", 1, true), "prints saved: " .. lastPrint())
    eq(ForeverSynthwaveDB.chatFontSize, 18, "printing does not change it")
end

function T.slash_size_rejects_bad_input()
    login()
    for _, bad in ipairs({ "size 9", "size 25", "size abc", "size 14.5", "size -5", "size 0", "size 1e1" }) do
        __printed = {}
        slash(bad)
        eq(ForeverSynthwaveDB.chatFontSize, nil, bad .. " saved something")
        eq(sizeOf(ChatFrame1), 14, bad .. " changed the font")
        assert(lastPrint():find("10", 1, true) and lastPrint():find("24", 1, true),
            bad .. " gave no range message: " .. lastPrint())
    end
end

function T.edit_box_and_tab_fonts_untouched()
    login()
    slash("size 22")
    __blizzardReset(3); __fire("UPDATE_CHAT_WINDOWS")
    for i = 1, 3 do
        eq(_G["ChatFrame" .. i .. "EditBox"].setFontCalls, 0, "edit box " .. i)
        eq(_G["ChatFrame" .. i .. "Tab"].setFontCalls, 0, "tab " .. i)
        eq(select(2, _G["ChatFrame" .. i .. "EditBox"]:GetFont()), 14)
    end
end

function T.no_write_when_unchanged()
    login()
    local function writes()
        local n = __cacheWrites + __fcfCalls
        for i = 1, 3 do n = n + _G["ChatFrame" .. i].setFontCalls end
        return n
    end
    local before = writes()
    assert(before > 0, "the first apply must have written")
    __fire("PLAYER_LOGIN"); __fire("UPDATE_CHAT_WINDOWS"); __fire("UPDATE_FLOATING_CHAT_WINDOWS")
    eq(writes(), before, "an idempotent event wrote")
    slash("size 14")
    eq(writes(), before, "/fschat size <current> wrote")
    slash("size 16")
    assert(writes() > before, "a real change must write")
    before = writes()
    slash("size 16")
    eq(writes(), before, "repeat of the new size wrote")
end

function T.stale_chat_cache_alone_triggers_a_write()
    login()
    __cache[2] = 0                     -- the frame shows 14 but the cache says "unset" (= 18)
    __fire("UPDATE_CHAT_WINDOWS")
    eq(__cache[2], 14, "cache repaired")
end

function T.falls_back_without_fcf()
    login()
    for i = 1, 3 do
        local f = _G["ChatFrame" .. i]
        local face, size, flags = f:GetFont()
        eq(size, 14); eq(face, FACE); eq(flags, FLAGS)
        eq(__cache[i], 14)
    end
    eq(__fcfCalls, 0)
    -- a temporary window (id above the 10 built-in ones) has no chat-cache slot to write
    local temp = __newChat(11, 18)
    eq(FS.Chat.ApplyFontSize(temp), true, "temporary window")
    eq(sizeOf(temp), 14); eq(__cache[11], nil, "temporary window's cache slot written")
end

function T.throwing_api_is_contained()
    __throwCache = true
    login()                            -- must not throw out of the event handler
    eq(sizeOf(ChatFrame1), 14, "frame still sized")
    slash("size 20")                   -- nor out of the slash handler
    eq(ForeverSynthwaveDB.chatFontSize, 20, "still saved")
    for i = 1, 3 do eq(sizeOf(_G["ChatFrame" .. i]), 20, "ChatFrame" .. i) end
end

function T.no_chat_cache_api_judges_by_frame_size()
    -- no cache to read: a window still at the stock 18 is defaulted, one at another size is left
    ChatFrame1:SetFont(FACE, 18, FLAGS)
    ChatFrame2:SetFont(FACE, 16, FLAGS)
    login()
    eq(sizeOf(ChatFrame1), 14, "stock 18")
    eq(sizeOf(ChatFrame2), 16, "chosen 16")
    eq(sizeOf(ChatFrame3), 12, "chosen 12")
    slash("size 20")
    eq(sizeOf(ChatFrame2), 20, "saved size enforces")
end

__checks = T
"""

# Late-window world: the Blizzard window-creation functions exist at load, as they do on the client.
PRELOAD_LATE = r"""
__late = nil
function FCF_GetCurrentChatFrame() return __late end
function FCF_OpenTemporaryWindow() end
function FCF_OpenNewWindow() end
"""

FILES = ("ChatFrameSkin.lua", "ChatSlashCommands.lua")


# Worlds where a Blizzard API is missing from the start, as the files see it at load.
WORLDS = {
    "falls_back_without_fcf": "FCF_SetChatWindowFontSize = nil",
    "no_chat_cache_api_judges_by_frame_size": (
        "GetChatWindowInfo, SetChatWindowSize, FCF_SetChatWindowFontSize = nil, nil, nil"
    ),
}


def boot(late: bool = False, world: str = "") -> "LuaRuntime":
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    if world:
        lua.execute(world)
    if late:
        lua.execute(PRELOAD_LATE)
    lua.execute("for i = 1, 3 do __newChat(i, 12) end")
    # Blizzard's frames registered first: its handlers run before ours.
    lua.execute(SETUP)
    load = lua.eval(LOAD)
    for name in FILES:
        load(name, (ADDON / name).read_text(encoding="utf-8"), lua.eval("FS"))
    lua.execute(CHECKS)
    return lua


def check_late_window() -> bool:
    """A whisper / tear-off window made after login is skinned and gets the size."""
    lua = boot(late=True)
    lua.execute(
        r"""
        ForeverSynthwaveDB = {}
        __fire("PLAYER_LOGIN")
        local late = __newChat(4, 12)
        __late = late
        FCF_OpenTemporaryWindow()
        assert(select(2, late:GetFont()) == 14, "temporary window size " .. tostring(select(2, late:GetFont())))
        assert(__cache[4] == 14, "temporary window cache")
        local face, _, flags = late:GetFont()
        assert(face == FACE and flags == FLAGS, "face/flags kept")
        assert(late.eb.setFontCalls == 0 and late.tab.setFontCalls == 0, "edit box / tab untouched")

        local second = __newChat(5, 12)
        __late = second
        FCF_OpenNewWindow()
        assert(select(2, second:GetFont()) == 14, "tear-off window size")

        -- a saved size is honoured by a late window too, and re-showing it writes nothing
        ForeverSynthwaveDB.chatFontSize = 18
        local third = __newChat(6, 12)
        __late = third
        FCF_OpenTemporaryWindow()
        assert(select(2, third:GetFont()) == 18, "late window honours the saved size")
        local calls = third.setFontCalls
        FCF_OpenTemporaryWindow()
        assert(third.setFontCalls == calls, "a reused window already at size was rewritten")

        -- a window skinned already and reused by Blizzard at another size is corrected
        third:SetFont(FACE, 12, FLAGS)
        FCF_OpenTemporaryWindow()
        assert(select(2, third:GetFont()) == 18, "a reused window was not re-sized")
        """
    )
    return True


def main() -> int:
    names = sorted(k for k in boot().eval("__checks").keys())
    failed = 0
    total = 0
    for name in names:
        total += 1
        # A fresh client per check: the cache, the hooks and the saved table must not leak.
        try:
            boot(world=WORLDS.get(name, "")).eval("__checks")[name]()
            print(f"ok    {name}")
        except LuaError as err:
            failed += 1
            print(f"FAIL  {name}: {err}")
    total += 1
    try:
        check_late_window()
        print("ok    late_window_gets_it")
    except LuaError as err:
        failed += 1
        print(f"FAIL  late_window_gets_it: {err}")
    print(f"{total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
