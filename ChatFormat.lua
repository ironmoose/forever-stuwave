-- Forever Synthwave: ChatFormat
-- Restyles the TEXT of chat lines, not the frame around them. Chat.lua owns the
-- terminal chassis (border, term bar, tab strip, edit box); this file owns what
-- a message looks like once it is printed.
--
-- The complaint this answers (Parker, 2026-09-21): "the text of the chat like
-- '1:[general] somecharacter: yea bro totally and stuff' -- that is the default
-- blizzard font colors and pattern."
--
-- Read off the mockup's `.termbody` and its example lines:
--     System: Entered Nagrand.
--     [Guild] Vex: inv for heroic?
--     Kaine: one sec, repairing
--     [Party] Nyx: pulling in 5
--     You: hots rolling
-- So: a per-channel coloured tag in square brackets, a named speaker, and a pale
-- mint BODY. The body colour is the biggest single change, because today every
-- line is tinted its channel's colour, and that is what makes stock chat read as
-- noise.
--
-- ONE DELIBERATE DEPARTURE FROM THE MOCK: the mock draws every speaker in flat
-- cyan, but Parker asked for class colours ("i like the class colored authors"),
-- so names render by class and cyan is only the fallback. See NAME below.
--
-- SCOPE: the cases the mock draws, plus numbered channels. Whispers, yells,
-- emotes, raid, officer, loot/money/XP lines and timestamps are deliberately
-- left STOCK, because the mock does not specify them and guessing would mean
-- restyling most of chat on my own taste. Having styled and stock in one window
-- is what makes the remaining design calls concrete rather than hypothetical.

local _, FS = ...

-------------------------------------------------------------------------------
-- Palette
-------------------------------------------------------------------------------

-- Hex, not Theme's {r,g,b} tables, because these go into |cffRRGGBB escape
-- sequences inside format strings rather than into SetTextColor. Values are the
-- mock's own CSS custom properties (full-ui-layout.html `:root`).
local PINK   = "ff2e97" -- --pink,  whispers
local GREEN  = "39ff14" -- --green, guild
local AMBER  = "ffb648" -- --amber, System: tag
local CYAN   = "22e0ff" -- --cyan,  party; also the speaker colon and name fallback
-- Not a mock colour: the mock never drew a raid line. Picked to sit clearly
-- apart from AMBER, which is close enough in hue to be confused with it at a
-- glance if the orange is not pushed well past it.
local ORANGE = "ff6a1a" -- raid and battleground (instance chat)

-- Locked colours for two SPECIFIC numbered channels (Parker, 2026-09-24), not
-- part of the capture-and-preserve scheme every other numbered channel still
-- uses -- see RewriteChannelTag below.
local GEN_VIOLET   = "a56bff" -- [General] tag
local TRADE_AZURE  = "5b9cff" -- [Trade] tag

-- --termbody colour #bfe9d6. This one IS a {r,g,b}: it is not embedded in the
-- string, it replaces the colour the message handler passes to AddMessage, so
-- that everything in the line NOT wrapped in its own |cff reads mint.
--
-- Byte-identical to Theme.lua's COLOR_TEXT_PARCHMENT (also #bfe9d6, "the
-- terminal body colour"), so this consumes that shared token instead of
-- keeping its own duplicate copy.
local MINT = FS.Theme.COLOR_TEXT_PARCHMENT

-- Mock: `.termbody { gap: 4px }`.
local LINE_SPACING = 4

local MAX_CHAT_FRAMES = 10

-------------------------------------------------------------------------------
-- What gets restyled
-------------------------------------------------------------------------------

-- The speaker. Parker, on seeing the first build: "i like the class colored
-- authors" -- so the mock's flat cyan name is deliberately NOT what ships. This
-- renders the name in the player's class colour and keeps cyan only as the
-- fallback for a name Blizzard did not colour.
--
-- Nesting is what makes that fallback free rather than a special case. With
-- class colouring on, %s arrives already wrapped, so the span expands to
-- |cff22e0ff|cffC41F3BVex|r|r -- two opens, two closes -- and the inner colour
-- wins for the name itself. With it off, %s is a bare name and the cyan shows.
--
-- The colon is its OWN span rather than sharing the name's, even though the mock
-- draws them as one `<span class="cy">Vex:</span>`. Writing it as
-- |cff22e0ff%s:|r would leave the colon's colour depending on whether this
-- client's escape parser treats |r as popping one level or resetting outright,
-- and that is not a thing worth betting the look on. Two balanced spans render
-- the same under either rule: class-coloured name, cyan colon, mint body.
local NAME = "|cff" .. CYAN .. "%s|r|cff" .. CYAN .. ":|r "

-- Keyed by the ChatTypeInfo key, which is also the CHAT_<key>_GET suffix and
-- (prefixed with CHAT_MSG_) the event name. One table drives all three, so a
-- type cannot be half-converted.
--
-- Blizzard's |Hchannel:...|h wrapper is preserved on the tag so it stays
-- clickable (click [Guild] to reply in guild). The |cff sits OUTSIDE the
-- hyperlink: a colour opened inside |h...|h does not reliably survive the link.
-- Tag colours are Parker's call, 2026-09-21: "i want guild our neon green or
-- whatever color we are using for green, whispers hot pink. party cyan. raid
-- and battlegrounds hot orange." That reassigns guild and party from the
-- first cut, which had them pink and green respectively.
--
-- BATTLEGROUND is not a chat type on this client. Checked against the 16001
-- globals dump rather than assumed: there is no CHAT_BATTLEGROUND_GET, and
-- battleground chat arrives as INSTANCE_CHAT / INSTANCE_CHAT_LEADER, which is
-- where "battlegrounds hot orange" is therefore implemented.
--
-- Only GUILD and PARTY carry a |Hchannel:...|h link, because those two targets
-- are the ones already proven to work here. The link target for raid, instance
-- and whisper tags is NOT guessed at: a wrong target is a click that errors or
-- silently does nothing, and these tags are plain coloured text until their
-- stock strings have been read (`/fschatfmt dump`).
local FORMATS = {
    SAY = {
        -- Drops "says". Yell is untouched, so say-vs-yell stays legible.
        format = NAME,
    },
    GUILD = {
        format = "|cff" .. GREEN .. "|Hchannel:Guild|h[Guild]|h|r " .. NAME,
    },
    PARTY = {
        format = "|cff" .. CYAN .. "|Hchannel:Party|h[Party]|h|r " .. NAME,
    },
    PARTY_LEADER = {
        -- Kept distinct from PARTY rather than flattened to one [Party]: the
        -- mock only ever draws one party line, and dropping who the leader is
        -- would be losing information for the sake of matching a mock that
        -- never had to represent it.
        format = "|cff" .. CYAN .. "|Hchannel:Party|h[Party Leader]|h|r " .. NAME,
    },
    RAID = {
        format = "|cff" .. ORANGE .. "[Raid]|r " .. NAME,
    },
    RAID_LEADER = {
        format = "|cff" .. ORANGE .. "[Raid Leader]|r " .. NAME,
    },
    -- Battleground chat, and any instance group.
    INSTANCE_CHAT = {
        format = "|cff" .. ORANGE .. "[Instance]|r " .. NAME,
    },
    INSTANCE_CHAT_LEADER = {
        format = "|cff" .. ORANGE .. "[Instance Leader]|r " .. NAME,
    },
    -- Direction is kept rather than flattened to one [Whisper]: which way a
    -- whisper went is the whole point of seeing it, and stock carries that in
    -- the "whispers" / "To" wording this format replaces. WHISPER_INFORM's %s
    -- is the RECIPIENT, which is what makes [To] read correctly.
    WHISPER = {
        format = "|cff" .. PINK .. "[From]|r " .. NAME,
    },
    WHISPER_INFORM = {
        format = "|cff" .. PINK .. "[To]|r " .. NAME,
    },
}

-- SYSTEM has no CHAT_SYSTEM_GET and no author, so it cannot be done with a
-- format string. Blizzard prints the bare text; the mock wants an amber
-- `System:` in front of it. That prefix is added by a message filter instead.
local SYSTEM_PREFIX = "|cff" .. AMBER .. "System:|r "

-- Every type whose BODY becomes mint. SYSTEM is here even though it has no
-- format string, because the mint body is the ChatTypeInfo half of the job and
-- that half works for it exactly the same way.
local MINT_TYPES = {
    "SAY", "GUILD", "PARTY", "PARTY_LEADER", "SYSTEM",
    "RAID", "RAID_LEADER", "INSTANCE_CHAT", "INSTANCE_CHAT_LEADER",
    "WHISPER", "WHISPER_INFORM",
}

-------------------------------------------------------------------------------
-- Numbered channels
-------------------------------------------------------------------------------

-- Parker: "i really liked the mockup of no channel number. the [channel] had
-- the colour in it and was obvious enough."
--
-- General/Trade/LFG cannot be done the way guild and party are. Their bracketed
-- header is assembled by the message handler, not by CHAT_CHANNEL_GET, and this
-- client will not tell us what argument layout that format string is called
-- with. Guessing it wrong would garble every line in General rather than
-- degrading quietly, so the format string is left alone entirely and the whole
-- change is made through the event's own arguments, which ARE documented:
-- CHAT_MSG_CHANNEL carries the channel name TWICE, numbered as arg4
-- ("1. General") and bare as arg9 ("General"), and the handler displays arg4.
-- Substituting one for the other drops the number without touching anything
-- around it.
--
-- THAT WAS WRONG ON THIS CLIENT, AND IT THREW. Measured 2026-09-21 in game, a
-- channel message a few seconds after login:
--
--   ChatFrameUtil.lua:124: attempt to index local 'communityChannel' (a nil value)
--   GetCommunityAndStreamFromChannel <- ResolveChannelName <- ResolvePrefixedChannelName
--   <- ChatFrameOverrides.lua:652 <- MessageEventHandler
--
-- arg4 is not display-only. The handler also feeds it to
-- `ResolvePrefixedChannelName`, whose whole job is to parse the PREFIX off a
-- name -- the "1. " we were removing, and the community prefix a community
-- channel carries instead. Handed a bare (or colour-wrapped) name it resolves
-- to nil and the caller indexes it. So arg4 is now passed through untouched.
--
-- So the relabel happens DOWNSTREAM of the resolver instead, on the finished
-- line, in an `AddMessage` wrapper. That is also what ElvUI does, which is
-- where this shape was read off rather than invented (`CH:HandleShortChannels`
-- / `CH:ShortChannel`, ElvUI/Game/Shared/Modules/Chat/Chat.lua): match the
-- whole tag span `|Hchannel:(.-)|h%[(.-)%]|h`, keep capture 1 (the link target,
-- `channel:2`) EXACTLY as it came, and rewrite only capture 2 (the label).
-- Rebuilding the link verbatim is what keeps click-to-reply working; ElvUI's
-- own line 2229 shows the label is the only free part.
--
-- What the label actually looks like on this client, measured off a real line
-- rather than assumed: `2. General - Tirisfal Glades`. Two pieces to remove,
-- the leading index and the trailing zone, and the client brackets the
-- SPEAKER as well (`[Law Aholic]:`), which is its own formatting and is left
-- alone.
local CHANNEL_COUNT = 10 -- ChatTypeInfo carries CHANNEL1..CHANNEL10

local CHANNEL_TYPES = {}
for i = 1, CHANNEL_COUNT do
    CHANNEL_TYPES[i] = "CHANNEL" .. i
    MINT_TYPES[#MINT_TYPES + 1] = CHANNEL_TYPES[i]
end

-- Every type with a speaker whose name should take a class colour. Channels
-- included, since Parker wants class-coloured authors and General is where most
-- unfamiliar names turn up.
local SPEAKER_TYPES = {}
for typeKey in pairs(FORMATS) do
    SPEAKER_TYPES[#SPEAKER_TYPES + 1] = typeKey
end
for _, typeKey in ipairs(CHANNEL_TYPES) do
    SPEAKER_TYPES[#SPEAKER_TYPES + 1] = typeKey
end

-------------------------------------------------------------------------------
-- Saved originals
-------------------------------------------------------------------------------

-- Everything this file overwrites is stashed here before the first write, so
-- /fschatfmt off is a true restore rather than a best guess at Blizzard's
-- defaults. Populated once; a second enable reuses it.
local saved = {
    formats = nil,     -- CHAT_<type>_GET string, by type
    colors = nil,      -- { r, g, b }, by type
    classColor = nil,  -- ChatTypeInfo[type].colorNameByClass, by type
    channelTag = nil,  -- "rrggbb" tag colour, by numbered-channel index
    spacing = nil,     -- chat frame :GetSpacing(), by frame index
}

local applied = false

-- Success counts from the last Enable(), read back by the /fschatfmt status
-- print so a client missing ChatFrame_AddMessageEventFilter or FS.Chat
-- reports the shortfall instead of an unconditional "ON".
local lastFilterCount, lastFilterTotal = 0, 0
local lastWrapCount, lastWrapTotal = 0, 0

-------------------------------------------------------------------------------
-- Message filters
-------------------------------------------------------------------------------

-- The mock writes the player's own lines as "You: hots rolling" rather than
-- repeating their character name back at them. A message filter is the only
-- place this can happen: the author is read by the handler AFTER filters run,
-- so rewriting it here is what actually reaches the format string's %s.
--
-- Returning false means "not suppressed, use these arguments instead" -- the
-- documented filter contract. Returning nothing at all would also pass the
-- message through, but would discard the rewrite.
local function SelfName(author)
    local player = UnitName("player")
    if player and author == player then return "You" end
    return author
end

local function SelfNameFilter(_, _, msg, author, ...)
    local swapped = SelfName(author)
    if swapped ~= author then
        return false, msg, swapped, ...
    end
    return false
end

local function SystemPrefixFilter(_, _, msg, ...)
    if type(msg) ~= "string" then return false end
    -- Idempotence guard: a filter can be registered against more than one frame
    -- and Blizzard runs the chain per frame, so without this a line shown in
    -- two docked windows could pick up two prefixes.
    if msg:find(SYSTEM_PREFIX, 1, true) == 1 then return false end
    return false, SYSTEM_PREFIX .. msg, ...
end

-- Channels get the same "You" rewrite as every other type, and nothing else.
-- One filter per event, so it happens here rather than by also registering
-- SelfNameFilter.
--
-- `channel` (arg4) is deliberately passed through UNCHANGED. See the block
-- above: it is an input to the client's channel-name resolver, not just a
-- label, and rewriting it threw on a live channel message. The per-channel tag
-- colour still comes from `ChatTypeInfo`, which is captured and re-asserted
-- below; it is only the number-drop that is gone.
local function ChannelFilter(_, _, msg, author, lang, channel, target, flags, zoneID, index, baseName, ...)
    return false, msg, SelfName(author), lang, channel, target, flags, zoneID, index, baseName, ...
end

local FILTERS = {}

-- Returns (registered, wanted) so the status print can report a shortfall.
-- `wanted` is computed up front so it is correct even on the early-out below,
-- where nothing gets registered; `registered` is a real count of the
-- ChatFrame_AddMessageEventFilter calls actually made, not an assumption.
local function AddFilters()
    local wanted = 0
    for _ in pairs(FORMATS) do wanted = wanted + 1 end
    wanted = wanted + 2 -- CHAT_MSG_SYSTEM, CHAT_MSG_CHANNEL

    if type(ChatFrame_AddMessageEventFilter) ~= "function" then return 0, wanted end

    for typeKey in pairs(FORMATS) do
        FILTERS["CHAT_MSG_" .. typeKey] = SelfNameFilter
    end
    FILTERS["CHAT_MSG_SYSTEM"] = SystemPrefixFilter
    FILTERS["CHAT_MSG_CHANNEL"] = ChannelFilter

    local registeredCount = 0
    for event, fn in pairs(FILTERS) do
        ChatFrame_AddMessageEventFilter(event, fn)
        registeredCount = registeredCount + 1
    end
    return registeredCount, wanted
end

local function RemoveFilters()
    if type(ChatFrame_RemoveMessageEventFilter) ~= "function" then return end
    for event, fn in pairs(FILTERS) do
        ChatFrame_RemoveMessageEventFilter(event, fn)
    end
    FILTERS = {}
end

-------------------------------------------------------------------------------
-- Apply / restore
-------------------------------------------------------------------------------

local function CaptureOriginals()
    if saved.formats then return end

    saved.formats = {}
    for typeKey in pairs(FORMATS) do
        saved.formats[typeKey] = _G["CHAT_" .. typeKey .. "_GET"]
    end

    saved.colors = {}
    for _, typeKey in ipairs(MINT_TYPES) do
        local info = ChatTypeInfo and ChatTypeInfo[typeKey]
        if info then
            saved.colors[typeKey] = { info.r, info.g, info.b }
        end
    end

    -- Only types with a speaker; SYSTEM has no author to colour.
    --
    -- A nil flag is NOT recorded, and the type is then left alone entirely
    -- below. There is no GetChatColorNameByClass on this client to read the
    -- setting back with, so ChatTypeInfo is the only source: if the field is
    -- missing, we do not know what the player had, and flipping it would mean
    -- "restoring" it to a value we invented.
    -- The tag colour for each numbered channel, as hex, taken from the colour
    -- the player already has for it. Nothing is invented: every numbered
    -- channel stays as distinguishable from the others as it was, which is
    -- what lets the number go without the tags collapsing into one another.
    -- General and Trade are the exception -- RewriteChannelTag overrides them
    -- with GEN_VIOLET/TRADE_AZURE by NAME rather than reading this table, but
    -- their stock colour is still captured here so /fschatfmt off restores it
    -- genuinely rather than leaving the override in place.
    --
    -- Order matters. This reads ChatTypeInfo, and ApplyBodyColors is about to
    -- overwrite the same fields with mint, so the tag colour has to be taken
    -- first. One consequence worth knowing: recolouring a channel in Blizzard's
    -- chat config while the skin is ON changes the body's saved restore value
    -- but not the tag, because the original is gone by then. /fschatfmt off/on
    -- picks the new colour up.
    saved.channelTag = {}
    for i = 1, CHANNEL_COUNT do
        local info = ChatTypeInfo and ChatTypeInfo["CHANNEL" .. i]
        if info and type(info.r) == "number" then
            saved.channelTag[i] = ("%02x%02x%02x"):format(
                info.r * 255, info.g * 255, info.b * 255)
        end
    end

    saved.classColor = {}
    for _, typeKey in ipairs(SPEAKER_TYPES) do
        local info = ChatTypeInfo and ChatTypeInfo[typeKey]
        if info and type(info.colorNameByClass) == "boolean" then
            saved.classColor[typeKey] = info.colorNameByClass
        end
    end

    saved.spacing = {}
    for i = 1, MAX_CHAT_FRAMES do
        local frame = _G["ChatFrame" .. i]
        if not frame then break end
        if frame.GetSpacing then
            saved.spacing[i] = frame:GetSpacing()
        end
    end
end

-- Class-coloured speaker names, on Parker's call ("i like the class colored
-- authors"). Turned on only for the types this file restyles, so the player's
-- setting for every other channel is untouched.
--
-- Worth being clear about why this is set rather than merely relied on: the
-- format string's nesting already lets a class colour win where Blizzard
-- applies one, but Blizzard only applies one when this flag is set. Leaving it
-- to whatever the account happened to have would make the look depend on a
-- setting nobody in this project chose.
local function ApplyClassColors(enable)
    if type(SetChatColorNameByClass) ~= "function" then return end
    for typeKey, original in pairs(saved.classColor) do
        local want = enable and true or original
        local info = ChatTypeInfo and ChatTypeInfo[typeKey]
        -- Only write on an actual change. SetChatColorNameByClass fires
        -- UPDATE_CHAT_COLOR, and this file listens to that event so it can
        -- re-assert itself after the chat config is touched; writing
        -- unconditionally from inside that handler is a loop.
        if not info or info.colorNameByClass ~= want then
            SetChatColorNameByClass(typeKey, want)
        end
    end
end

-- The mint half. Kept separate from the format-string half because Blizzard
-- fires UPDATE_CHAT_COLOR and re-reads ChatTypeInfo from CVars whenever the
-- player touches a colour in the chat config, which would silently put the
-- channel tint back. This is cheap enough to simply re-run on that event.
local function ApplyBodyColors()
    if not ChatTypeInfo then return end
    for _, typeKey in ipairs(MINT_TYPES) do
        local info = ChatTypeInfo[typeKey]
        if info then
            info.r, info.g, info.b = MINT[1], MINT[2], MINT[3]
        end
    end
end

local function ApplySpacing()
    for i = 1, MAX_CHAT_FRAMES do
        local frame = _G["ChatFrame" .. i]
        if not frame then break end
        if frame.SetSpacing then frame:SetSpacing(LINE_SPACING) end
    end
end

-------------------------------------------------------------------------------
-- The channel tag, rewritten on the finished line
-------------------------------------------------------------------------------

-- Everything above works on the message BEFORE the handler assembles it. The
-- channel tag is the one piece that only exists AFTER, so it is the one piece
-- that has to be caught here. See the CHANNEL_TYPES block for why upstream is
-- not an option: arg4 is the resolver's input, not a label.

-- `|Hchannel:(.-)|h%[(.-)%]|h` spans the whole clickable tag. Capture 1 is the
-- link target and is rebuilt byte-for-byte, so the tag stays click-to-reply;
-- capture 2 is the visible label and is the only thing rewritten.
local CHANNEL_TAG_PATTERN = "|Hchannel:(.-)|h%[(.-)%]|h"

-- The colour goes OUTSIDE the whole |h...|h span, matching what the GUILD and
-- PARTY format strings already do successfully on this client. A |cff opened
-- INSIDE a hyperlink does not reliably survive it here, which is exactly why
-- those formats are written that way, so this does not re-litigate it.
local function RewriteChannelTag(link, label)
    -- Guild/Party/Officer links come through this pattern too. Their tags are
    -- already built by our own format strings, wrapped in their own colour, so
    -- returning nil (gsub leaves the match untouched) is the correct no-op.
    local index = tonumber(link:match("^channel:(%d+)$"))
    if not index then return nil end

    -- Measured label: "2. General - Tirisfal Glades". The leading index is the
    -- thing Parker asked to lose; the trailing zone is dead weight next to it,
    -- and both patterns are no-ops on a label that lacks them, which is the
    -- safe way to be wrong about a custom channel's name.
    label = label:gsub("^%s*%d+%.%s*", ""):gsub("%s+%-%s+.*$", "")
    if label == "" then return nil end

    -- General and Trade get LOCKED synthwave colours instead of the player's
    -- captured per-channel colour (Parker, 2026-09-24), matched by the
    -- RESOLVED NAME rather than by index: channel numbering is per-character,
    -- so an index-keyed colour would paint whatever channel happens to sit at
    -- that slot on an alt, not necessarily General/Trade. `label` at this
    -- point is already the cleaned bare name (the "N. " index and " - Zone"
    -- suffix are stripped above), which is what makes the match possible here.
    -- Every OTHER numbered channel (LFG, custom, ...) is untouched -- it falls
    -- through to the existing capture-and-preserve lookup unchanged.
    local nameLower = label:lower()
    local hex
    if nameLower == "general" then
        hex = GEN_VIOLET
    elseif nameLower == "trade" then
        hex = TRADE_AZURE
    else
        hex = saved.channelTag and saved.channelTag[index]
    end

    local tag = "|Hchannel:" .. link .. "|h[" .. label .. "]|h"
    if hex then
        return "|cff" .. hex .. tag .. "|r"
    end
    return tag
end

-- Registered on FS.Chat.WrapAddMessage rather than reassigning frame.AddMessage
-- here directly: Chat.lua's terminal chassis also touches AddMessage (its
-- scroll furniture watches it via hooksecurefunc), and a second, independent
-- reassignment written later in either file could silently clobber whichever
-- one assigned first. The shared wrap point is the one place AddMessage is
-- ever reassigned, so that is no longer possible by construction.
--
-- The transform itself is installed ONCE and never removed; /fschatfmt off is
-- honoured by the `applied` check inside it. `registered` is this file's own
-- idempotence guard on TOP of that: FS.Chat.WrapAddMessage layers a new entry
-- onto its transforms list on every call, so calling it again on a later
-- Enable() (off, then on) would stack a second copy of the same rewrite
-- rather than reusing the first.
local function ChannelTagTransform(text)
    if applied and text:find("|Hchannel:", 1, true) then
        return text:gsub(CHANNEL_TAG_PATTERN, RewriteChannelTag)
    end
    return text
end

local registered = setmetatable({}, { __mode = "k" })

-- Returns (wrapped, frameCount): frameCount is every ChatFrame slot that
-- exists, whether or not it got wrapped, so the status print can tell "FS.Chat
-- was missing for some frames" apart from "there just weren't more frames
-- open". A frame already in `registered` from a prior Enable() cycle counts
-- toward `wrapped` too -- re-wrapping it is deliberately skipped (see
-- `registered` above), not a failure to report.
local function WrapChatFrames()
    local wrapped, frameCount = 0, 0
    for i = 1, MAX_CHAT_FRAMES do
        local frame = _G["ChatFrame" .. i]
        if frame then
            frameCount = frameCount + 1
            if registered[frame] then
                wrapped = wrapped + 1
            elseif FS.Chat then
                FS.Chat.WrapAddMessage(frame, ChannelTagTransform)
                registered[frame] = true
                wrapped = wrapped + 1
            end
        end
    end
    return wrapped, frameCount
end

local function Enable()
    if applied then return end
    CaptureOriginals()

    for typeKey, entry in pairs(FORMATS) do
        _G["CHAT_" .. typeKey .. "_GET"] = entry.format
    end

    ApplyBodyColors()
    ApplyClassColors(true)
    ApplySpacing()
    lastFilterCount, lastFilterTotal = AddFilters()
    lastWrapCount, lastWrapTotal = WrapChatFrames()

    applied = true
end

local function Disable()
    if not applied then return end

    for typeKey in pairs(FORMATS) do
        _G["CHAT_" .. typeKey .. "_GET"] = saved.formats[typeKey]
    end

    if ChatTypeInfo then
        for typeKey, rgb in pairs(saved.colors) do
            local info = ChatTypeInfo[typeKey]
            if info then
                info.r, info.g, info.b = rgb[1], rgb[2], rgb[3]
            end
        end
    end

    ApplyClassColors(false)

    for i, spacing in pairs(saved.spacing) do
        local frame = _G["ChatFrame" .. i]
        if frame and frame.SetSpacing and spacing then frame:SetSpacing(spacing) end
    end

    RemoveFilters()
    applied = false
end

-------------------------------------------------------------------------------
-- Toggle
-------------------------------------------------------------------------------

-- Default ON: the point of shipping it is to see it. This touches every line of
-- chat, though, which is how Parker actually plays, so the off switch has to
-- exist and has to be a true restore -- hence CaptureOriginals above.
local function Wanted()
    if type(ForeverSynthwaveDB) ~= "table" then return true end
    if ForeverSynthwaveDB.chatFormat == nil then return true end
    return ForeverSynthwaveDB.chatFormat and true or false
end

SLASH_FSCHATFMT1 = "/fschatfmt"
SlashCmdList["FSCHATFMT"] = function(msg)
    msg = (msg or ""):lower():gsub("%s", "")

    ForeverSynthwaveDB = ForeverSynthwaveDB or {}

    -- Prints the STOCK format string for every type we override, escaped so the
    -- chat frame shows the source rather than rendering it. The point is the
    -- |Hchannel:...|h link target inside each one: RAID, INSTANCE_CHAT and
    -- WHISPER ship with plain uncoloured tags precisely because those targets
    -- were not going to be guessed at, and this is how they get read.
    if msg == "dump" then
        if not saved.formats then
            print("|cff22e0ffsynthwave://chat|r  nothing captured yet; /fschatfmt on first")
            return
        end
        local keys = {}
        for typeKey in pairs(saved.formats) do keys[#keys + 1] = typeKey end
        table.sort(keys)
        for _, typeKey in ipairs(keys) do
            local stock = saved.formats[typeKey]
            print(("|cff22e0ff%s|r  %s"):format(
                typeKey, (tostring(stock):gsub("|", "||"))))
        end
        return
    end

    if msg == "on" then
        ForeverSynthwaveDB.chatFormat = true
    elseif msg == "off" then
        ForeverSynthwaveDB.chatFormat = false
    elseif msg == "" then
        ForeverSynthwaveDB.chatFormat = not Wanted()
    else
        print("|cff22e0ffsynthwave://chat|r  /fschatfmt [on|off|dump]")
        return
    end

    if ForeverSynthwaveDB.chatFormat then Enable() else Disable() end

    print(("|cff22e0ffsynthwave://chat|r  message format %s"):format(
        applied and "|cff39ff14ON|r" or "|cffff2e97OFF (stock)|r"))

    -- Reports rather than diagnoses now that class-coloured names are the
    -- intended look. A type listed as off is one where ChatTypeInfo carried no
    -- colorNameByClass flag to read, so it was left alone and its names will
    -- fall back to cyan.
    if applied then
        -- Listed by EXCEPTION rather than in full: with the ten numbered
        -- channels in the set, printing every type that worked would bury the
        -- one or two that did not.
        local off = {}
        for _, typeKey in ipairs(SPEAKER_TYPES) do
            local info = ChatTypeInfo and ChatTypeInfo[typeKey]
            if not (info and info.colorNameByClass) then
                off[#off + 1] = typeKey:lower()
            end
        end
        print(("|cff9a8cc8class-coloured names: %s|r"):format(
            #off == 0 and "all"
            or ("all but " .. table.concat(off, ", ") .. " (cyan fallback)")))

        -- Same by-exception convention: on a full API this always reads
        -- N/N and prints nothing, so it only speaks up when Enable() came up
        -- short (missing ChatFrame_AddMessageEventFilter or FS.Chat).
        local short = {}
        if lastFilterCount < lastFilterTotal then
            short[#short + 1] = ("filters %d/%d"):format(lastFilterCount, lastFilterTotal)
        end
        if lastWrapCount < lastWrapTotal then
            short[#short + 1] = ("chat frames %d/%d"):format(lastWrapCount, lastWrapTotal)
        end
        if #short > 0 then
            print(("|cffffb648partial apply: %s|r"):format(table.concat(short, ", ")))
        end
    end
end

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

local watcher = CreateFrame("Frame")
watcher:RegisterEvent("PLAYER_LOGIN")
watcher:RegisterEvent("UPDATE_CHAT_COLOR")
watcher:SetScript("OnEvent", function(_, event)
    if event == "PLAYER_LOGIN" then
        -- Deferred to PLAYER_LOGIN rather than run at file scope: the saved
        -- variables table does not exist yet when this file loads, so Wanted()
        -- would read a default rather than the player's choice.
        if Wanted() then Enable() end
    elseif applied then
        -- Blizzard just re-read ChatTypeInfo from the CVars, which puts the
        -- channel tint back over our mint and can drop the class-name flag with
        -- it. Only those two need re-asserting; the format strings are
        -- untouched by this event. ApplyClassColors writes only on a real
        -- change, so re-entering through the event it fires terminates.
        ApplyBodyColors()
        ApplyClassColors(true)
    end
end)

FS.ChatFormat = {
    Enable = Enable,
    Disable = Disable,
    IsApplied = function() return applied end,
}
