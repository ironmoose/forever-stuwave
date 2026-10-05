-- Forever Synthwave: ChatFrameSkin
-- Split out of the original Chat.lua (2026-09-23): SkinChatFrame, the
-- per-frame wiring for one ChatFrameN's backdrop, edit box and scroll
-- furniture. It calls only ChatCore, ChatTermBar, ChatTabs and ChatEditBox
-- exports, all of which load before it (see ForeverSynthwave.toc); it loads
-- before ChatSlashCommands.lua, whose Apply() is what calls SkinChatFrame.
-- Reads/writes the shared FS.Chat state table; see ChatCore.lua's header for
-- why cross-module names live there instead of as locals.

local _, FS = ...
local Chat = FS.Chat

local SkinPanel = FS.Theme.SkinPanel
local AddRoundedFill = FS.Theme.AddRoundedFill
local COLOR_POWER = FS.Theme.COLOR_POWER -- cyan accent; the mock's "neon border" color for chat

-- Texels the message container is grown past the chat frame on each side so
-- ascenders and descenders are not clipped. ElvUI uses 3; our panel padding is
-- 10, so the text still cannot reach the border.
local TEXT_BLEED = 3

-------------------------------------------------------------------------------
-- Message font size
-------------------------------------------------------------------------------

-- Parker: "lets also default the chat to 14pt". Blizzard's own default is
-- CHAT_FRAME_DEFAULT_FONT_SIZE (18), and a chat-cache size of 0 means "use
-- that", so left alone each window wore 18. ForeverSynthwaveDB.chatFontSize
-- (account-wide: per-character saved variables are discarded on this beta
-- client) overrides it; /fschat size N sets it.
Chat.DEFAULT_FONT_SIZE = 14
Chat.MIN_FONT_SIZE = 10
Chat.MAX_FONT_SIZE = 24

-- The saved size, or nil when there is none. Validated rather than trusted
-- (saved variables can hold anything); a bad value reads as no value.
function Chat.SavedFontSize()
    local saved = type(ForeverSynthwaveDB) == "table" and ForeverSynthwaveDB.chatFontSize
    if type(saved) == "number" and saved >= Chat.MIN_FONT_SIZE
        and saved <= Chat.MAX_FONT_SIZE and saved == math.floor(saved) then
        return saved
    end
end

-- The wanted size: the saved one, else the default.
function Chat.FontSize()
    return Chat.SavedFontSize() or Chat.DEFAULT_FONT_SIZE
end

-- Blizzard's stock size, and what a chat-cache size of 0 (never set) means.
local STOCK_FONT_SIZE = 18
-- Built-in windows are ChatFrame1..10 and own a chat-cache slot; a temporary
-- window (whisper, tear-off) has id 11+ and none.
local MAX_CACHED_WINDOW_ID = 10

-- Puts one chat MESSAGE frame at the wanted size, keeping the face and flags it
-- already has. Only the message frame: the edit box and the tab strip have their
-- own fonts and are not touched. Goes through Blizzard's own
-- FCF_SetChatWindowFontSize, which also writes the chat-cache
-- (SetChatWindowSize) so Blizzard's font menu and the next
-- UPDATE_CHAT_WINDOWS agree with what is shown; without it the same two writes
-- are made by hand. Writes nothing when the frame AND the cache already match,
-- which is also what ends any event loop. Returns true when it wrote.
--
-- With no SAVED size, the default only goes onto a window that has never been
-- sized: its chat-cache size is 0 (unset) or the stock 18 (what
-- FCF_ResetChatWindow leaves). Any other cached size is a choice made in
-- Blizzard's font menu, which fires no event of its own, so the next
-- UPDATE_CHAT_WINDOWS would otherwise revert it on every login. A saved size
-- (`/fschat size N`) is explicit and is enforced on every window. Where the
-- cache cannot be read (a temporary window, or no API) the frame's own size
-- is judged instead. The first apply is PLAYER_LOGIN. The table guard below
-- only protects against a future caller that runs before the saved variables
-- exist (a write then could be the wrong size); no current caller does.
function Chat.ApplyFontSize(frame)
    if type(ForeverSynthwaveDB) ~= "table" then return false end
    if not frame or not frame.GetFont or not frame.SetFont then return false end
    local want = Chat.FontSize()
    local face, size, flags = frame:GetFont()
    if not face or not size then return false end

    local id = frame.GetID and frame:GetID()
    local cacheable = id and id >= 1 and id <= MAX_CACHED_WINDOW_ID
    local cached
    if cacheable and type(GetChatWindowInfo) == "function" then
        local ok, _, cacheSize = pcall(GetChatWindowInfo, id)
        if ok then cached = cacheSize end
    end

    if not Chat.SavedFontSize() then
        local current = cached or math.floor(size + 0.5)
        if current ~= 0 and current ~= STOCK_FONT_SIZE then return false end
    end
    if math.abs(size - want) < 0.01 and (cached == nil or cached == want) then
        return false
    end

    if type(FCF_SetChatWindowFontSize) == "function"
        and pcall(FCF_SetChatWindowFontSize, nil, frame, want) then
        return true
    end
    pcall(frame.SetFont, frame, face, want, flags)
    if cacheable and type(SetChatWindowSize) == "function" then
        pcall(SetChatWindowSize, id, want)
    end
    return true
end

function Chat.ApplyAllFontSizes()
    for _, frame in ipairs(Chat.skinnedChatFrames or {}) do
        Chat.ApplyFontSize(frame)
    end
end

-------------------------------------------------------------------------------
-- Frame backdrop
-------------------------------------------------------------------------------

-- Backdrop + edit box for one ChatFrameN. Guarded by frame.fsChatSkin so
-- re-applying never stacks a second set of chrome textures. Tabs are not this
-- function's business any more: the terminal draws ONE strip for the whole
-- dock (BuildTermTabs), rather than one treatment per chat frame.
function Chat.SkinChatFrame(frame, index)
    if not frame or frame.fsChatSkin then return end

    -- Strip the chat frame's OWN art first. This is what was still hanging
    -- outside the panel after the scroll furniture was seated -- `/fschat
    -- spill` named them: a 581x320 background, two 8x8 corners and a 16x312
    -- right edge, all regions of ChatFrame1 itself, drawing at alpha 0.16 and
    -- reaching 5 to 9 units past the border.
    --
    -- They were missed because every previous pass looked at CHILD FRAMES.
    -- These are plain texture regions on the chat frame, with no name and no
    -- child to find them by, and 0.16 alpha is faint enough to read as a
    -- shadow rather than as Blizzard art nobody removed. ElvUI just calls
    -- frame:StripTextures() here for the same reason.
    --
    -- Safe before our own chrome goes on: everything we add lives on the
    -- backdrop CHILD or on the edit box, never on the chat frame's own
    -- regions, and StripBlizzardChrome's re-strip pass only re-hides what it
    -- hid the first time.
    if FS.Theme.StripBlizzardChrome then pcall(FS.Theme.StripBlizzardChrome, frame) end


    -- Give the message text room for its ascenders and descenders.
    --
    -- Parker: "If the first line of chat has letters that go below the base
    -- like a g it gets cut off", and then the same at the top. Measured: the
    -- cut sits exactly at ChatFrame1's bottom edge, and the glyphs are flush
    -- to both ends.
    --
    -- The text is NOT drawn on the chat frame. It lives in FontStringContainer
    -- -- the anonymous 564x311 child that the frame walk kept turning up --
    -- and that container is sized EXACTLY to the chat frame, so a descender
    -- has nowhere to go and is clipped at the container's own edge.
    --
    -- Hence none of the obvious levers move it: growing the frame moves the
    -- container with it, SetClipsChildren(false) does not apply, and extra
    -- line spacing just spaces lines that are still flush. All three were
    -- tried on the live client and all three changed nothing.
    --
    -- Taken from ElvUI, which grows the container past the frame on every side
    -- (Chat.lua: FontStringContainer:SetPoint('TOPLEFT', -3, 3) and
    -- ('BOTTOMRIGHT', 3, -3)). The 3px lands inside our 10px panel padding, so
    -- the text still cannot reach the border.
    local textHost = frame.FontStringContainer
    if not textHost and frame.GetChildren then
        -- Feature-detected: the field is not guaranteed on this client, and
        -- the container is anonymous here, so fall back to the first child --
        -- which is what the walk showed it to be.
        local first = select(1, frame:GetChildren())
        if first and first.GetObjectType and first:GetObjectType() == "Frame" then
            textHost = first
        end
    end
    if textHost then
        textHost:ClearAllPoints()
        textHost:SetPoint("TOPLEFT", frame, "TOPLEFT", -TEXT_BLEED, TEXT_BLEED)
        textHost:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", TEXT_BLEED, -TEXT_BLEED)
        frame.fsTextHost = textHost
    end

    -- The chrome used to be drawn ON the ChatFrame itself, which put the border
    -- flush against the message text and let lines run under the term bar. WoW
    -- gives no way to inset a ChatFrame's text area, so instead the skin moves
    -- to a BACKDROP frame anchored OUTSIDE the chat frame: the border sits
    -- further out by exactly the padding we want, and the top inset reserves
    -- room for the term bar so messages never reach it.
    --
    -- Mockup: .termbody padding 6px 10px, .termbar its own row above it.
    local backdrop = CreateFrame("Frame", nil, Chat.termPanel)
    Chat.AnchorBackdrop(frame, backdrop)
    -- Behind the text, which lives on the chat frame itself.
    backdrop:SetFrameLevel(Chat.termPanel:GetFrameLevel() + Chat.LEVEL_BACKDROP)
    frame.fsBackdrop = backdrop

    if SkinPanel then
        SkinPanel(backdrop, {
            -- Our own frame, built empty a few lines up: there is no Blizzard
            -- art on it to strip, and it draws its own scanline and term bar
            -- below, so both are off here.
            strip = false,
            scanline = false,
            fillColor = Chat.COLOR_TERM_BG,
            borderColor = COLOR_POWER,
            radius = FS.Theme.SLICE_MARGIN,
            borderThickness = 1,
            glowSize = 6,
            glowAlpha = 0.3,
        })

        -- Faint inner cyan tint layered on top of the near-black terminal
        -- fill, matching the mock's .term inner wash; same chamfer as the
        -- SkinPanel slice above (Theme.SLICE_MARGIN: 6 cut, 5 round), so the wash doesn't poke
        -- past its TOP-LEFT / BOTTOM-RIGHT cut corners.
        if AddRoundedFill then
            AddRoundedFill(backdrop, { COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.04 }, FS.Theme.SLICE_MARGIN)
        end
    end

    -- Built once for the whole dock rather than per frame, and deliberately NOT
    -- gated on index 1 any more: the chrome has to exist regardless of which
    -- window happens to be skinned first, and it seats itself onto the selected
    -- one below.
    Chat.BuildTermBar()
    Chat.BuildTermTabs()
    Chat.BuildSocialTab()
    Chat.SkinTitleButtons()
    Chat.ApplyDockState()

    Chat.AddChatScanline(backdrop)

    -- Message body stays on Blizzard's default readable font FACE per the
    -- CLAUDE.md convention; SetFont(Mononoki) also fails on this frame's message
    -- fontstrings on this client, so forcing it would just hit the fallback.
    -- Only the SIZE is ours (Chat.ApplyFontSize, applied from PLAYER_LOGIN and
    -- the late-window path in ChatSlashCommands.lua, not while skinning).

    local editBox = _G["ChatFrame" .. index .. "EditBox"]
    Chat.HideBlizzardEditBoxArt(index)
    Chat.StyleEditBox(editBox)
    Chat.SeatEditBox(editBox, backdrop)
    Chat.HookEditBoxFocusGlow(editBox)
    Chat.ApplyEditBoxArrowKeys(editBox)
    Chat.SeatPrompt(editBox)

    Chat.SkinScrollButtons(index)

    -- Register the window. This table was declared and never filled, so both
    -- loops over it did nothing at all -- harmless while every backdrop was a
    -- child of its own chat frame and inherited that frame's visibility, and
    -- the moment the backdrops moved into the terminal it meant all ten drew
    -- at once. An empty table is a silent no-op, which is why a loop that had
    -- never run looked like working code.
    Chat.skinnedChatFrames[#Chat.skinnedChatFrames + 1] = frame

    frame.fsChatSkin = true
    Chat.SkinChatScrollBar(frame)
end
