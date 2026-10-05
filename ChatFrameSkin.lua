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

    -- Message body stays on Blizzard's default readable font per the CLAUDE.md
    -- convention; SetFont(Mononoki) also fails on this frame's message
    -- fontstrings on this client, so forcing it would just hit the fallback.

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
