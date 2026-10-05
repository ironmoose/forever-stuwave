-- Forever STUwave: ChatCore
-- Split out of the original Chat.lua (2026-09-23): the chat terminal's shared
-- namespace, frame-level/geometry constants, the FS.Chat state table every
-- other Chat* module reads and writes, and the functions that seat the
-- terminal chrome onto whichever chat window is currently selected
-- (DockedChatFrames, ActiveChatFrame, DockAnchorFrame, AnchorBackdrop,
-- SeatTerminalChrome).
--
-- FS.Chat IS THE FIX for a problem the single-file version solved with
-- forward-declared locals: a Lua local is invisible outside the file that
-- declares it, so a name one module defines and another module's closure
-- needs (DockedChatFrames, SeatScrollFurniture, ApplyWindowState,
-- ToggleWindowState, and every piece of shared UI state) cannot be a plain
-- local once the terminal is split across files. Every such name lives on
-- this table instead, assigned by whichever module owns it, and read back
-- through the table AT CALL TIME by everyone else -- never captured into a
-- consumer's own local -- so load order and definition order stop mattering.
-- ChatCore loads first (see forever-stuwave.toc) and owns this table's
-- creation, but ownership of individual fields is spread across every
-- Chat* module; see each module's own header for what it assigns.

local _, FS = ...
FS.Chat = FS.Chat or {}
local Chat = FS.Chat

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

-------------------------------------------------------------------------------
-- Frame-level and geometry constants
--
-- Exported onto Chat.* wherever another module also needs them; every other
-- Chat* module reads those through the table (Chat.PAD_TOP, Chat.LEVEL_DOCK,
-- and so on) rather than aliasing them into a local of its own, for the same
-- reason the state table exists: this file's own locals are invisible
-- elsewhere.
-------------------------------------------------------------------------------

local MAX_CHAT_FRAMES = 10
Chat.MAX_CHAT_FRAMES = MAX_CHAT_FRAMES

-- Mockup .termbody padding is 6px 10px; the top additionally clears .termbar so
-- message lines never run underneath it, and the bottom clears the edit box.
local PAD_X = 10
-- Term bar (14) + tab strip (15) + a little breathing room. The strip lives
-- in this band ABOVE ChatFrame1, so adding it never resizes Blizzard's
-- message area.
-- The edit box sits INSIDE the terminal (Parker's call), so the bottom padding
-- has to reserve its full height plus a little breathing room -- otherwise the
-- message text runs underneath it.
local EDITBOX_HEIGHT = 20
local EDITBOX_MARGIN = 4
local PAD_BOTTOM = EDITBOX_HEIGHT + EDITBOX_MARGIN * 2
Chat.EDITBOX_HEIGHT = EDITBOX_HEIGHT
Chat.EDITBOX_MARGIN = EDITBOX_MARGIN

-- Mock's .term shell background (#07031a), distinct from the shared
-- Theme.COLOR_BG (dark violet) used elsewhere in the addon; kept local here
-- rather than added to Theme.lua, which is outside this pass's file surface.
local COLOR_TERM_BG = { 0.027, 0.012, 0.102, 0.85 }
Chat.COLOR_TERM_BG = COLOR_TERM_BG

-- Mock's .termbar green status dot; a decorative one-off with no other
-- consumer, so (per Theme.lua's own convention for non-canonical values)
-- kept local instead of promoted to a shared design token.
local COLOR_TERM_GREEN = { 0.22, 1, 0.08, 1 }
Chat.COLOR_TERM_GREEN = COLOR_TERM_GREEN

-- Existing shipped asset (see UnitFrames.lua's identical local declaration):
-- a radial soft-glow blob, ADD blend, full white with a cosine falloff. Used
-- here for the termbar status dots so "dot" and "glow" are one texture.
local GLOW_ROUND_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\glow_round.tga"
Chat.GLOW_ROUND_TEXTURE = GLOW_ROUND_TEXTURE

-- Existing shipped asset (see Minimap.lua's identical local declaration for
-- its own scanline overlay): a 4x4 tiling texture, one dark row over
-- transparent. SCANLINE_ALPHA is lower than 1 so the baked .30 row alpha
-- reads as a subtle scrim over the message area rather than a heavy stripe.
local SCANLINE_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\scanline.tga"
local SCANLINE_ALPHA = 0.4
local SCANLINE_TILE_PX = 4
Chat.SCANLINE_TEXTURE = SCANLINE_TEXTURE
Chat.SCANLINE_ALPHA = SCANLINE_ALPHA
Chat.SCANLINE_TILE_PX = SCANLINE_TILE_PX

-- 14pt glyphs plus 4px above and below. The strip was 15 tall for a 9pt label
-- and had to grow with the font, or the pills clip.
local TAB_FONT_SIZE    = 14
local TAB_PAD_Y        = 4
local TERM_TABS_HEIGHT = TAB_FONT_SIZE + TAB_PAD_Y * 2
Chat.TAB_FONT_SIZE = TAB_FONT_SIZE
Chat.TERM_TABS_HEIGHT = TERM_TABS_HEIGHT

-- The title bar matches the tab strip rather than keeping its old 14. Two
-- stacked bands of different heights read as a mistake, and the tabs are the
-- one that has to be tall enough for their font -- so the title follows them.
local TERM_BAR_HEIGHT  = TERM_TABS_HEIGHT
Chat.TERM_BAR_HEIGHT = TERM_BAR_HEIGHT

-- Term bar + tab strip + PAD_X. The last term is the fix for "the height of
-- the actual chat logs needs some padding at the top. You have it going ALL
-- the way to teh cyan line" -- the band used to clear the chrome and stop, so
-- the first message sat flush against the tab strip's rule while the left and
-- right sides had 10px. Derived, not a magic number, so changing the font or
-- the strip height keeps the padding.
local PAD_TOP = TERM_BAR_HEIGHT + TERM_TABS_HEIGHT + PAD_X
Chat.PAD_TOP = PAD_TOP

-- Collapsed height of the panel: the term bar and nothing else.
local MIN_PANEL_EXTRA = 2

-------------------------------------------------------------------------------
-- Draw order inside the terminal
--
-- These are OFFSETS from termPanel:GetFrameLevel(), not absolute levels.
-- Measured in game 2026-09-22: a child's level is clamped UP to its parent's,
-- so in the max state (container level 200, via the clamp) an absolute
-- LEVEL_BACKDROP of 1 read back as 200 -- our own fill landed above our own
-- chrome and chat text instead of below them. Every call site adds its
-- constant to the container's current level instead.
-------------------------------------------------------------------------------

local LEVEL_DOCK = 0         -- GeneralDockManager and its tabs, at the container's own level
-- 2 and not 1: measured in game in the max state, GeneralDockManager sits at
-- LEVEL_DOCK (the container's own level) and Blizzard re-levels its own dock
-- tabs to dockmgr+1 -- which lands exactly on a LEVEL_BACKDROP of 1, tying the
-- fill with the tabs. A tie is resolved by an engine rule we do not control,
-- and 3 of ChatFrame1Tab's 11 regions still showed through at that tie. 2
-- clears the tabs' dockmgr+1 outright instead of depending on the tie.
local LEVEL_BACKDROP = 2     -- the panel's fill, border and glow
local LEVEL_CHAT = 5         -- Blizzard's message frames, above the fill
local LEVEL_CHROME = 12      -- term bar, tab strip, edit box, prompt
Chat.LEVEL_DOCK = LEVEL_DOCK
Chat.LEVEL_BACKDROP = LEVEL_BACKDROP
Chat.LEVEL_CHAT = LEVEL_CHAT
Chat.LEVEL_CHROME = LEVEL_CHROME

-------------------------------------------------------------------------------
-- Shared mutable UI state
--
-- Every Chat* module reads and writes these through Chat.* directly -- never
-- into a local of its own -- because they are ASSIGNED at runtime (inside
-- Build/Apply functions called well after every file has finished loading),
-- not at file-load time, so a local captured at another module's file-top
-- would freeze on whatever this table held at that module's load, almost
-- always nil. A plain field access always sees the current value.
-------------------------------------------------------------------------------

Chat.skinnedChatFrames = {} -- every chat window skinned, docked or torn off
Chat.activeChatFrame = nil  -- which docked window is actually up (see ActiveChatFrame below)
Chat.windowState = "normal" -- "normal", "min" or "max"; persisted across reloads
Chat.termTabs = nil         -- the tab strip Frame (ChatTabs.BuildTermTabs)
Chat.socialTab = nil        -- the social tab Button (ChatTabs.BuildSocialTab)
Chat.termBar = nil          -- the term bar Frame (ChatTermBar.BuildTermBar)
Chat.minimiseButton = nil   -- term bar lamp (ChatTermBar.BuildTermBar)
Chat.maximiseButton = nil   -- term bar lamp (ChatTermBar.BuildTermBar)

-- The docked tab selected last session, read here and only here.
--
-- Captured at FILE LOAD TIME rather than inside ChatTabs.ApplyDockState's own
-- restore branch, and this is the whole point. ApplyDockState is also where
-- the CURRENT selection gets saved back to this same SavedVariables key, and
-- its first call during login happens inside ChatSlashCommands.lua's Apply(),
-- which does not run until every Chat* module -- this file included -- has
-- already finished loading. Reading ForeverSTUwaveDB.chatSelectedTab that
-- late would find whatever ApplyDockState's own save had ALREADY overwritten
-- it with (Blizzard's login default, usually tab 1) rather than the value
-- from the previous session. Reading it now, before any Chat* module has run
-- a single line of Apply-time code, is what avoids that race.
--
-- Consumed and cleared by Chat.ApplyDockState the first time it runs; nil
-- afterwards means either there was nothing to restore or it already
-- happened, and either way that function's restore branch is a no-op.
Chat.pendingSelectedTab = ForeverSTUwaveDB and ForeverSTUwaveDB.chatSelectedTab

-- Interim default: force the comms tab active at login when chatSelectedTab
-- is unset, so a persisted user choice still wins once the client's
-- SavedVariables bug is fixed. The Forever beta client never restores
-- per-character SavedVariables across a /reload (design notes), so this
-- default always fires today -- Parker's interim call, companion to
-- ChatTabs.lua's comms-first pill hardcode (design notes tracks the real
-- persisted-order/selection feature this stands in for).
-- Consumed and cleared by Chat.ApplyDockState's own one-shot block, same
-- discipline as Chat.pendingSelectedTab above.
Chat.pendingDefaultComms = not (ForeverSTUwaveDB and ForeverSTUwaveDB.chatSelectedTab)

-------------------------------------------------------------------------------
-- THE CHAT TERMINAL COMPONENT.
--
-- One frame that owns every piece of chat: the backdrops, the term bar, the
-- tab strip, the social tab, the edit boxes, the prompt, and the Blizzard chat
-- windows and tabs themselves. Parker's design: "like 'component chat
-- terminal' holds all things chat".
--
-- It exists because z-order was being maintained by hand in four places. The
-- pieces lived under three different parents -- UIParent for the chrome, the
-- chat frame for its backdrop, Blizzard's dock for the tabs -- so raising the
-- panel meant finding each one and setting its strata, and any piece missed
-- stayed behind. Inheritance does not help there: a frame that has had its own
-- strata set ignores its parent's.
--
-- Inside ONE container, strata is set once on the container and ordering
-- within it is done with frame LEVELS, which is what levels are for. That is
-- also how ElvUI does it (chat:SetParent(LeftChatPanel), the tabs with it, and
-- GeneralDockManager too).
--
-- Full-screen and mouse-transparent: it is a z-order and ownership container,
-- not a visible panel, and it must not eat clicks meant for the world.
-------------------------------------------------------------------------------

local termPanel = CreateFrame("Frame", "ForeverSTUwaveChatTerminal", UIParent)
termPanel:SetAllPoints(UIParent)
termPanel:SetFrameStrata("LOW")
termPanel:EnableMouse(false)
Chat.termPanel = termPanel
FS.chatTerminal = termPanel

-------------------------------------------------------------------------------
-- Shared AddMessage wrap point
--
-- Two independent pieces of this addon touch a chat frame's AddMessage:
-- ChatTermBar's scroll furniture OBSERVES it (hooksecurefunc, to reveal the
-- jump button on new text) and ChatFormat TRANSFORMS it (rewriting a numbered
-- channel's tag before Blizzard ever sees the line). Only a REPLACEMENT of
-- AddMessage can change what gets printed, so the transform case cannot use
-- hooksecurefunc -- and a second, independent replacement written later would
-- silently overwrite whichever one assigned first. This is the one place
-- AddMessage is ever reassigned, so that mistake is no longer possible to make
-- by accident: every transform layers onto the same wrapper instead.
-------------------------------------------------------------------------------

local addMessageWraps = setmetatable({}, { __mode = "k" })

-- Registers `transform(text) -> text` to run on every AddMessage call for
-- `frame`, ahead of whatever Blizzard (or the original AddMessage) does with
-- it. Wrapping the same frame more than once layers transforms in
-- registration order rather than replacing the previous one.
function Chat.WrapAddMessage(frame, transform)
    if not frame or type(transform) ~= "function" then return end

    local entry = addMessageWraps[frame]
    if not entry then
        local original = frame.AddMessage
        if type(original) ~= "function" then return end
        entry = { original = original, transforms = {} }
        addMessageWraps[frame] = entry

        frame.AddMessage = function(self, text, ...)
            if type(text) == "string" then
                for _, fn in ipairs(entry.transforms) do
                    -- pcall each transform: a throwing transform must not propagate
                    -- out of AddMessage and blank the frame. On error or a non-string
                    -- return, keep the prior text so the line still prints, just
                    -- untransformed, instead of dropping it or erroring.
                    local ok, result = pcall(fn, text)
                    if ok and type(result) == "string" then
                        text = result
                    end
                end
            end
            return entry.original(self, text, ...)
        end
    end

    entry.transforms[#entry.transforms + 1] = transform
end

-------------------------------------------------------------------------------
-- Docked-frame queries
-------------------------------------------------------------------------------

-- The docked frames, in dock order, so our strip matches the order the player
-- actually arranged. Falls back to a shown-frame scan on a client where the
-- dock helpers are missing.
function Chat.DockedChatFrames()
    if type(FCFDock_GetChatFrames) == "function" and GeneralDockManager then
        local ok, frames = pcall(FCFDock_GetChatFrames, GeneralDockManager)
        if ok and type(frames) == "table" and #frames > 0 then
            return frames
        end
    end

    local list = {}
    for i = 1, Chat.MAX_CHAT_FRAMES do
        local frame = _G["ChatFrame" .. i]
        if not frame then break end
        if frame.IsShown and frame:IsShown() then
            list[#list + 1] = frame
        end
    end
    return list
end

-- Which docked window is actually up.
--
-- NOT SELECTED_CHAT_FRAME. Measured 2026-09-22: after switching to the Combat
-- Log that global still read ChatFrame1, while ChatFrame1 was shown=false and
-- ChatFrame2 shown=true. Trusting it is what left the chrome seated on the
-- hidden window and the active pill stuck on "general" after a swap.
-- Visibility is the state the dock actually maintains, so read that.
function Chat.ActiveChatFrame()
    for _, cf in ipairs(Chat.DockedChatFrames()) do
        if cf.IsShown and cf:IsShown() then return cf end
    end
    return Chat.activeChatFrame or SELECTED_CHAT_FRAME or ChatFrame1
end

-- The window the whole dock is sized from. Docked chat frames are NOT all the
-- same height on this client: measured 2026-09-22, ChatFrame1 is 310.8 and
-- ChatFrame2 (Combat Log) is 286.8, sharing a bottom edge and differing by 24
-- at the top. Anchoring each backdrop to its own frame therefore made the
-- panel visibly change height as you switched tabs, which is what Parker saw
-- ("fix the combat tab so the bg stays the same height").
--
-- ChatFrame1 is the dock's primary and keeps a valid rect even while hidden
-- (measured: shown=false with top/bottom intact), so it can be the reference
-- for every docked window regardless of which one is up.
function Chat.DockAnchorFrame()
    return ChatFrame1
end

-- Anchors one window's backdrop. DOCKED windows all measure from the dock
-- anchor so the panel is the same rect whichever tab is selected; a torn-off
-- or undocked window has no dock to match and measures from itself.
function Chat.AnchorBackdrop(frame, backdrop)
    backdrop = backdrop or (frame and frame.fsBackdrop)
    if not (frame and backdrop) then return end

    local reference = Chat.DockAnchorFrame()
    local docked = false
    for _, cf in ipairs(Chat.DockedChatFrames()) do
        if cf == frame then docked = true break end
    end
    if not (docked and reference) then reference = frame end

    backdrop:ClearAllPoints()
    backdrop:SetPoint("TOPLEFT", reference, "TOPLEFT", -PAD_X, PAD_TOP)

    -- Minimised: the panel sits at the bottom of the screen, so collapsing
    -- toward the BOTTOM leaves the term bar where the chat was, rather than
    -- stranding it up where the panel's top edge used to be. Parker: "when it
    -- minimizes it goes from the bottom up to the top instead of from the top
    -- down to the bottom." Anchoring the bottom to the chat frame the way the
    -- normal case does would keep the panel full height, because a hidden
    -- frame still reports the rect it had -- so the bottom is anchored to the
    -- reference instead, the same fixed offsets the normal branch's
    -- BOTTOMRIGHT anchor uses.
    --
    -- ClearAllPoints first: the shared TOPLEFT set above applies to every
    -- state, and a frame anchored on both TOP and BOTTOM with an explicit
    -- height is over-constrained -- WoW ignores the height and stretches
    -- between the anchors instead, which would leave minimise doing nothing.
    if Chat.windowState == "min" then
        backdrop:ClearAllPoints()
        backdrop:SetPoint("BOTTOMLEFT", reference, "BOTTOMLEFT", -PAD_X, -PAD_BOTTOM)
        backdrop:SetPoint("BOTTOMRIGHT", reference, "BOTTOMRIGHT", PAD_X, -PAD_BOTTOM)
        backdrop:SetHeight(TERM_BAR_HEIGHT + MIN_PANEL_EXTRA)
        return
    end

    -- Clear any explicit height left over from the collapsed branch above.
    -- SetHeight(0) is WoW's way of saying "no fixed height, derive it from the
    -- anchors" -- without it the panel keeps the term-bar height for one more
    -- layout pass after being restored, which reads as a restore that only
    -- half worked and then fixes itself on the next toggle.
    backdrop:SetHeight(0)
    backdrop:SetPoint("BOTTOMRIGHT", reference, "BOTTOMRIGHT", PAD_X, -PAD_BOTTOM)
end

-- Puts the term bar and the tab strip onto whichever docked window is currently
-- showing. Both are children of UIParent, so this is the only thing that ties
-- them to a chat frame, and re-running it on every selection change is what
-- makes them survive a switch to the Combat Log.
--
-- They sit in the band the backdrop reserves ABOVE the chat frame (PAD_TOP), so
-- nothing here moves or resizes Blizzard's frame or its message area.
function Chat.SeatTerminalChrome(frame)
    local target = frame or Chat.activeChatFrame or Chat.ActiveChatFrame()
    local backdrop = target and target.fsBackdrop
    if not backdrop then return end

    -- LEVELS ONLY. Everything here lives in the chat terminal container now,
    -- so they all share its strata and the level is what decides order.
    --
    -- This used to compute a strata one step above the backdrop's, because the
    -- pieces lived under different parents and the dock raises whichever chat
    -- window is selected -- a level computed from a hidden window's backdrop
    -- lost to the visible one's, and the tab glyphs came out sheared in half
    -- by the other panel's top edge. Inside one container that cannot happen:
    -- the chrome is above every chat frame by a fixed margin, whichever one
    -- the dock raises.
    local level = termPanel:GetFrameLevel() + LEVEL_CHROME

    -- The edit box rides with the chrome, not with the chat window.
    --
    -- Its ">" prompt is the terminal's, and it was being buried by the panel
    -- whenever the box did not have focus: the client only raises the edit box
    -- on focus, so an unfocused prompt loses the z fight to the backdrop.
    -- Parker: "the > needs to be brougth forward in front of the chat cyan
    -- border bg regardless if it is active or not." Seating it here makes that
    -- true by construction, focused or not, rather than depending on what the
    -- client happens to raise.
    local editBox = target.GetName and _G[(target:GetName() or "") .. "EditBox"]

    -- The prompt host rides with the chrome too, for the same reason the edit
    -- box does: it has to clear the backdrop whichever window the dock raises.
    local promptHost = editBox and editBox.fsChatPromptHost

    for _, chrome in ipairs({ Chat.termBar, Chat.termTabs, editBox, promptHost }) do
        if chrome then
            -- SetParent, every pass: Blizzard re-parents its edit box on dock
            -- changes, and a piece that has wandered out of the container is
            -- back to carrying its own strata.
            if chrome:GetParent() ~= termPanel then chrome:SetParent(termPanel) end
            if chrome.SetFrameLevel then chrome:SetFrameLevel(level) end
        end
    end

    if Chat.termBar then
        Chat.termBar:ClearAllPoints()
        Chat.termBar:SetPoint("TOPLEFT", backdrop, "TOPLEFT", 1, -1)
        Chat.termBar:SetPoint("TOPRIGHT", backdrop, "TOPRIGHT", -1, -1)
        -- Always shown, even minimised: this bar IS the collapsed panel.
        Chat.termBar:Show()
    end

    -- Minimised collapses the panel down to the term bar alone, so the tab
    -- strip, the edit box and the prompt host all hide here. This is the
    -- single place that rule lives: ApplyDockState (which calls this) has
    -- five call sites plus the dock and tab-selection event hooks, and only
    -- one caller used to re-hide this chrome afterward, so a reload that
    -- restored "min" state still showed the strip the moment any other
    -- caller ran.
    local minimised = (Chat.windowState == "min")

    if Chat.termTabs then
        Chat.termTabs:ClearAllPoints()
        Chat.termTabs:SetPoint("TOPLEFT", backdrop, "TOPLEFT", 1, -(TERM_BAR_HEIGHT + 1))
        Chat.termTabs:SetPoint("TOPRIGHT", backdrop, "TOPRIGHT", -1, -(TERM_BAR_HEIGHT + 1))
        Chat.termTabs:SetShown(not minimised)
    end

    if editBox then editBox:SetShown(not minimised) end
    if promptHost then promptHost:SetShown(not minimised) end

    -- Diagnostic handle. These are locals and the chrome's draw order is the
    -- thing most likely to be wrong about them, so expose enough to answer
    -- "what is actually on top" with a /dump instead of a redeploy.
    ForeverSTUwaveTermChrome = {
        bar = Chat.termBar, tabs = Chat.termTabs, backdrop = backdrop, target = target,
    }
end
