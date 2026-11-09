#!/usr/bin/env python3
"""Runs the real ChatFormat.lua headless against a mock chat client.

The tags (guild green, party cyan, instance orange, whisper pink) are drawn on the FINISHED line in the
AddMessage wrapper, never by writing Blizzard's CHAT_<type>_GET globals: a global written by an addon taints
Blizzard's line builder, which then cannot touch a secret battleground message. These checks pin:

  * enabling leaves every CHAT_<type>_GET global exactly as the client had it;
  * a guild, say, whisper and instance line get our tag and speaker style, timestamp and AFK flag kept;
  * a line that does not match the stock shape (an emote, a Discord sender) passes through untouched;
  * numbered channels still drop the index and zone;
  * the chat wrapper never runs a transform on a secret line.

    python3 tools/chatformat-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ROOT = Path(__file__).resolve().parent.parent / "forever-stuwave/Modules/Chat"
SRC = (ROOT / "ChatFormat.lua").read_text(encoding="utf-8")
CORE = (ROOT / "ChatCore.lua").read_text(encoding="utf-8")

MOCK = r"""
STOCK = {
    SAY = "%s says: ", GUILD = "|Hchannel:GUILD|h[Guild]|h %s: ", PARTY = "|Hchannel:PARTY|h[Party]|h %s: ",
    PARTY_LEADER = "|Hchannel:PARTY|h[Party Leader]|h %s: ", RAID = "|Hchannel:RAID|h[Raid]|h %s: ",
    RAID_LEADER = "|Hchannel:RAID|h[Raid Leader]|h %s: ",
    INSTANCE_CHAT = "|Hchannel:INSTANCE_CHAT|h[Instance]|h %s: ",
    INSTANCE_CHAT_LEADER = "|Hchannel:INSTANCE_CHAT|h[Instance Leader]|h %s: ",
    WHISPER = "%s whispers: ", WHISPER_INFORM = "To %s: ",
}
for k, v in pairs(STOCK) do _G["CHAT_" .. k .. "_GET"] = v end
ChatTypeInfo = {}
for _, k in ipairs({ "SAY", "GUILD", "PARTY", "PARTY_LEADER", "SYSTEM", "RAID", "RAID_LEADER", "INSTANCE_CHAT",
    "INSTANCE_CHAT_LEADER", "WHISPER", "WHISPER_INFORM", "CHANNEL1", "CHANNEL2" }) do
    ChatTypeInfo[k] = { r = 1, g = 1, b = 1, colorNameByClass = true }
end
SlashCmdList = {}
function UnitName() return "Stu" end
function ChatFrame_AddMessageEventFilter() end
function SetChatColorNameByClass() end
__wrapped = nil
FS = { Theme = { COLOR_TEXT_PARCHMENT = { 0.8, 1, 0.9 } }, IsSecret = function(v) return v == SECRET end }
SECRET = setmetatable({}, { __index = function() error("touched a secret") end })
-- A chat frame with a history, Blizzard's AddMessage (a plain field) and the secure mixin's TransformMessages.
ChatFrame1 = { history = {}, GetSpacing = function() return 0 end, SetSpacing = function() end }
function ChatFrame1:AddMessage(text, r, g, b, ...)
    self.history[#self.history + 1] = { text, r, g, b, ... }
end
__blizzAddMessage = ChatFrame1.AddMessage
function ChatFrame1:TransformMessages(match, rewrite)
    for i, e in ipairs(self.history) do
        if match(unpack(e)) then self.history[i] = { rewrite(unpack(e)) } end
    end
end
function hooksecurefunc(t, name, fn)
    local orig = t[name]
    t[name] = function(...) local r = { orig(...) }; fn(...); return unpack(r) end
    __hooked = (__hooked or 0) + 1
end
ChatTypeInfo.SYSTEM.r = 0.5
local Loose = { __index = function(t, k)
    if type(k) == "string" and k:match("^%u") then return function() return setmetatable({}, getmetatable(t)) end end
end }
local watcher
function CreateFrame()
    local f = setmetatable({}, Loose)
    function f:SetScript(_, fn) self.fn = fn end
    watcher = f
    return f
end
assert(loadstring(CORE, "@ChatCore.lua"))("forever-stuwave", FS)
assert(loadstring(SRC, "@ChatFormat.lua"))("forever-stuwave", FS)
watcher.fn(watcher, "PLAYER_LOGIN")
function Last() return ChatFrame1.history[#ChatFrame1.history] end
function Line(text, event) ChatFrame1:AddMessage(text, 1, 1, 1, 0, 0, 0, event); return Last()[1] end
LINK = "|Hplayer:Law-Realm:12:GUILD|h[Law Aholic]|h"
NAMED = "|cff22e0ff" .. LINK .. "|r|cff22e0ff:|r "
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("enable_never_writes_the_format_globals", """
    for k, v in pairs(STOCK) do assert(_G["CHAT_" .. k .. "_GET"] == v, k .. " was written") end
    assert(FS.ChatFormat.IsApplied())
""")

case("guild_say_whisper_and_instance_lines_are_restyled", """
    local out = Line("|Hchannel:GUILD|h[Guild]|h " .. LINK .. ": hots rolling", "CHAT_MSG_GUILD")
    assert(out == "|cff39ff14|Hchannel:Guild|h[Guild]|h|r " .. NAMED .. "hots rolling", out)
    out = Line(LINK .. " says: hi", "CHAT_MSG_SAY")
    assert(out == NAMED .. "hi", out)
    out = Line("To " .. LINK .. ": ok", "CHAT_MSG_WHISPER_INFORM")
    assert(out == "|cffff2e97[To]|r " .. NAMED .. "ok", out)
    out = Line("|Hchannel:INSTANCE_CHAT|h[Instance]|h " .. LINK .. ": inc mid", "CHAT_MSG_INSTANCE_CHAT")
    assert(out == "|cffff6a1a[Instance]|r " .. NAMED .. "inc mid", out)
""")

case("timestamp_and_afk_flag_are_kept", """
    local out = Line("12:01 |Hchannel:GUILD|h[Guild]|h <AFK>" .. LINK .. ": brb", "CHAT_MSG_GUILD")
    assert(out == "12:01 |cff39ff14|Hchannel:Guild|h[Guild]|h|r <AFK>" .. NAMED .. "brb", out)
    out = Line("12:01 <DND>" .. LINK .. " whispers: yo", "CHAT_MSG_WHISPER")
    assert(out == "12:01 |cffff2e97[From]|r <DND>" .. NAMED .. "yo", out)
""")

case("a_line_of_another_shape_passes_through", """
    local plain = "Law Aholic dances with you."
    assert(Line(plain, "CHAT_MSG_SAY") == plain)
    local discord = "|Hchannel:GUILD|h[Guild]|h |HDiscord:1|h[Law]|h: hi"
    assert(Line(discord, "CHAT_MSG_GUILD") == discord)
    assert(Line("You have learned a new spell.", nil) == "You have learned a new spell.")
""")

case("numbered_channels_still_drop_the_index_and_zone", """
    local out = Line("|Hchannel:channel:1|h[1. General - Mulgore]|h " .. LINK .. ": wts", "CHAT_MSG_CHANNEL")
    assert(out:find("[General]", 1, true) and not out:find("1. General", 1, true), out)
""")

case("a_secret_line_is_never_transformed", """
    ChatFrame1:AddMessage(SECRET, 1, 1, 1, 0, 0, 0, "CHAT_MSG_INSTANCE_CHAT")
    assert(Last()[1] == SECRET)
    -- and a later plain line's rewrite does not touch the secret entry
    Line(LINK .. " says: hi", "CHAT_MSG_SAY")
    assert(ChatFrame1.history[#ChatFrame1.history - 1][1] == SECRET)
""")

case("blizzards_chat_state_is_never_written", """
    -- AddMessage is hooked, never assigned (a written AddMessage taints every Blizzard caller in a BG)
    assert(__hooked == 1, "hooked " .. tostring(__hooked))
    -- ChatTypeInfo keeps Blizzard's colours; the mint body is set per line
    assert(ChatTypeInfo.SYSTEM.r == 0.5 and ChatTypeInfo.GUILD.r == 1, "ChatTypeInfo was written")
    Line("|Hchannel:GUILD|h[Guild]|h " .. LINK .. ": hi", "CHAT_MSG_GUILD")
    local e = Last()
    assert(e[2] == 0.8 and e[3] == 1 and e[4] == 0.9, "guild body not mint")
    assert(e[8] == "CHAT_MSG_GUILD", "the line keeps its extra arguments")
    Line("8 players have joined the battle.", nil)
    assert(Last()[2] == 1, "a non chat line keeps its colour")
""")

case("a_repeated_line_is_restyled_once", """
    local raw = "|Hchannel:GUILD|h[Guild]|h " .. LINK .. ": again"
    Line(raw, "CHAT_MSG_GUILD")
    Line(raw, "CHAT_MSG_GUILD")
    local a, b = ChatFrame1.history[#ChatFrame1.history - 1][1], Last()[1]
    assert(a == b and a:find("39ff14", 1, true), a)
    local _, n = a:gsub("39ff14", "")
    assert(n == 1, "styled twice: " .. a)
""")

case("guild_and_party_rows_get_a_tinted_band_that_follows_the_row", """
    local textures = {}
    function ChatFrame1:CreateTexture()
        local t = { shown = true, alpha = 1 }
        function t:SetPoint() end
        function t:SetWidth() end
        function t:SetColorTexture(r, g, b, a) self.rgba = { r, g, b, a } end
        function t:SetAlpha(a) self.alpha = a end
        function t:Show() self.shown = true end
        function t:Hide() self.shown = false end
        textures[#textures + 1] = t
        return t
    end
    function ChatFrame1:AddOnDisplayRefreshedCallback(fn) self.refreshed = fn end
    local function Row(event)
        local r = { shown = true, alpha = 1, messageInfo = { extraData = { 0, 0, 0, event, n = 4 } } }
        function r:IsShown() return self.shown end
        function r:GetAlpha() return self.alpha end
        function r:SetAlpha(a) self.alpha = a end
        function r:SetShown(v) self.shown = v end
        function r:Show() self.shown = true end
        function r:Hide() self.shown = false end
        return r
    end
    FS.ChatFormat.Disable(); FS.ChatFormat.Enable()
    assert(ChatFrame1.refreshed, "no display callback registered")
    local guild, party, say, secret = Row("CHAT_MSG_GUILD"), Row("CHAT_MSG_PARTY"), Row("CHAT_MSG_SAY"), Row(SECRET)
    ChatFrame1.visibleLines = { guild, party, say, secret }
    ChatFrame1.refreshed(ChatFrame1)
    assert(guild.fsBand and party.fsBand, "guild/party rows got no band")
    assert(not say.fsBand and not secret.fsBand, "say or secret row got a band")
    assert(guild.fsBand.fill.shown and guild.fsBand.fill.rgba[2] == 1 and guild.fsBand.fill.rgba[4] < 0.2, "guild band not green and faint")
    assert(party.fsBand.fill.rgba[3] == 1, "party band not cyan")
    -- fading: the row's alpha and hide carry to its band
    guild:SetAlpha(0.4)
    assert(guild.fsBand.fill.alpha == 0.4, "band did not fade with the row")
    guild:SetShown(false)
    assert(not guild.fsBand.fill.shown, "band stayed up on a hidden row")
    -- a pooled row reused for a say line loses its band on the next redraw
    party.messageInfo.extraData[4] = "CHAT_MSG_SAY"
    ChatFrame1.refreshed(ChatFrame1)
    assert(not party.fsBand.fill.shown, "stale band on a reused row")
    -- /fschatfmt off clears every band
    guild:SetShown(true)
    ChatFrame1.refreshed(ChatFrame1)
    assert(guild.fsBand.fill.shown)
    FS.ChatFormat.Disable()
    assert(not guild.fsBand.fill.shown and not guild.fsBand.edge.shown, "band survived off")
""")


def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.globals().SRC = SRC
    rt.globals().CORE = CORE
    try:
        rt.execute(MOCK)
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


def main() -> int:
    failures = 0
    for name, body in CASES:
        err = run_case(body)
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}: {err}")
    print(f"{len(CASES) - failures}/{len(CASES)} checks passed")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
