-- Forever STUwave: ChatTermBar
-- Split out of the original Chat.lua (2026-09-23): the term bar chrome, its
-- minimise/maximise lamps and the Blizzard title buttons relocated into it,
-- and the scroll cluster (scroll bar skin, scroll-to-bottom button, jump
-- button). Reads/writes the shared FS.Chat state table; see ChatCore.lua's
-- header for why cross-module names live there instead of as locals.

local _, FS = ...
local Chat = FS.Chat

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local SkinButton = FS.Theme.SkinButton
local StripBlizzardChrome = FS.Theme.StripBlizzardChrome
local ApplyMono = FS.Theme.ApplyMono
local COLOR_POWER = FS.Theme.COLOR_POWER -- cyan accent; the mock's "neon border" color for chat
local COLOR_HEALTH = FS.Theme.COLOR_HEALTH -- #ff2e97; matches the mock's .termbar pink status dot

local ICON_CHAT_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\icon_chat.tga"
local ICON_CHANNEL_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\icon_channel.tga"
local ICON_JUMP_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\icon_jump.tga"
local ICON_MINIMIZE_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\icon_minimize.tga"
local ICON_MAXIMIZE_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\icon_maximize.tga"
local SCROLL_RAIL_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\scroll_rail.tga"

-------------------------------------------------------------------------------
-- Scroll cluster
-------------------------------------------------------------------------------

-- Skins the Up/Down/ScrollToBottom buttons on ChatFrameNButtonFrame. Each
-- child name is existence-guarded individually so a missing button silently
-- no-ops instead of indexing a nil global.
function Chat.SkinScrollButtons(index)
    if not SkinButton then return end

    local suffixes = { "UpButton", "DownButton", "BottomButton" }
    for _, suffix in ipairs(suffixes) do
        local button = _G["ChatFrame" .. index .. "ButtonFrame" .. suffix]
        if button then
            SkinButton(button)
        end
    end
end

-------------------------------------------------------------------------------
-- Terminal header bar (mock .termbar; ChatFrame1 only)
-------------------------------------------------------------------------------

-- Idle/hover alphas, deliberately the same pair the social tab uses. These two
-- sit in the title bar rather than the tab row, but they are the same KIND of
-- thing -- a quiet control that lights when you reach for it -- and matching
-- numbers is what keeps the bar reading as one instrument.
local TITLE_BUTTON_SIZE = 16
local TITLE_BUTTON_GAP = 4
local TITLE_BUTTON_ALPHA = 0.85
local TITLE_BUTTON_ALPHA_HOVER = 1.00
-- The scroll bar is NOT a global on this client. Checked against the 16001
-- dump: there is no ChatFrame1ScrollBar, only Wow*ScrollBar* MIXINS, and the
-- live object turned up as an anonymous 8x286 child reachable as
-- ChatFrame1.ScrollBar. Feature-detected here for exactly that reason.
-- The scroll-to-bottom button is the thing that was overhanging the panel.
--
-- It turned up in the frame walk only as `child[6] <anon> 17x15 L=592 R=609`
-- against a panel whose right edge is 606 -- three units outside, with no name
-- to search for. ElvUI named it: `frame.ScrollToBottomButton`
-- (ElvUI/Game/Shared/Modules/Chat/Chat.lua). They Kill() it outright, along
-- with the scroll bar and the whole button frame, which is why ElvUI chat
-- never has furniture hanging off it.
--
-- We keep both, because Parker asked for the scroll bar to be SKINNED rather
-- than removed, so they have to be seated inside the border instead.
local SCROLL_BAR_WIDTH = 14
-- ONE inset for the bar and the jump button, because they stack vertically and
-- any difference reads immediately as a misalignment. Parker caught exactly
-- that when the two carried their own numbers: "it moved the scroll bar over
-- to the right too much and now it isn't lined up with the scroll to bottom
-- glyph." They share a width too, so they share a centre line.
local SCROLL_INSET = 3
-- The bar stops short of the bottom so it does not run into the jump-to-latest
-- arrow parked there. One button height plus a gap, derived rather than typed,
-- so resizing the button cannot silently re-collide them.
local SCROLL_BOTTOM_GAP = 4
local SCROLL_RAIL_ALPHA = 0.22
local SCROLL_THUMB_ALPHA = 0.95

-- The term bar's own chassis, and the reason the header read as "washed out,
-- like they are behind the main terminal" (Parker, 2026-09-22). It was not a
-- draw-order or alpha problem -- measured, everything was level 6 at alpha
-- 1.00 and the active pill was full-strength cyan. There was simply no BAR:
-- the mock's `.termbar` carries an 8% cyan wash and a 30% cyan bottom rule,
-- and neither had been built, so the title and dots floated directly on the
-- panel ground with nothing to sit on. Both values are the mock's
-- (full-ui-layout.html `.termbar` background / border-bottom).
local TERM_BAR_WASH    = 0.08
local TERM_BAR_RULE    = 0.30

-- One round status dot: glow_round.tga alone, ADD blend, tinted `color`. The
-- texture's own cosine falloff (bright core, fading to 0 at its edge) gives
-- dot and glow in a single region, so no separate glow pass is needed.
-- The term bar's left-hand controls: minimise and maximise.
--
-- These were the mock's two decorative status lamps, a pink and a green glow.
-- Turning them into controls first kept the lamp and punched the glyph out of
-- it, traffic-light style. Parker's call was to drop the disc -- "i don't
-- think the icons need the round bg. Lets just make the glyphs similar to the
-- icons on the right and then just color them green and pink" -- so they are
-- now flat tinted glyphs styled exactly like the chat and channel buttons at
-- the other end of the same bar, keeping only the lamps' colours.
--
-- Same idle/hover alphas as those buttons, for the same reason: everything in
-- this bar is quiet at rest and comes up to full when you reach for it.
-- `tooltip` may be a plain string or a function returning one. The minimise
-- and maximise buttons are toggles, so their label depends on `windowState`
-- at hover time; a function lets each resolve its own text instead of
-- freezing one at button-creation time.
function Chat.ResolveTermBarTooltip(tooltip)
    if type(tooltip) == "function" then
        return tooltip()
    end
    return tooltip
end

-- Anchors the tooltip up and to the right of `self` by default, so it never
-- covers the button the user is pointing at -- ANCHOR_TOPLEFT (tried first)
-- pinned the tooltip's corner to the button's corner and overlapped it,
-- because it is not the mirror of ANCHOR_BOTTOMLEFT it appears to be. Falls
-- back to beside the button, vertically centred, when there is no room
-- above: a maximised term bar sits only ~24px under the screen top, too
-- little for most tooltips, and that fallback needs no vertical room at
-- all. Shared by OnEnter and the ApplyWindowState refresh, called after
-- GameTooltip:SetText so its height is already known, and each reading is
-- feature-detected because this runs on every hover and every
-- minimise/maximise toggle.
function Chat.PlaceTermBarTooltip(self)
    if not GameTooltip then return end

    GameTooltip:ClearAllPoints()
    GameTooltip:SetPoint("BOTTOMLEFT", self, "TOPRIGHT", 4, 4)

    if not (GameTooltip.GetHeight and self.GetTop and UIParent and UIParent.GetTop) then
        return
    end

    local height = GameTooltip:GetHeight()
    local buttonTop = self:GetTop()
    local screenTop = UIParent:GetTop()
    if not height or height == 0 or not buttonTop or not screenTop then
        return
    end

    if buttonTop + 4 + height > screenTop then
        GameTooltip:ClearAllPoints()
        GameTooltip:SetPoint("LEFT", self, "RIGHT", 4, 0)
    end
end

local function AddTermBarButton(bar, color, xOffset, glyph, onClick, tooltip)
    local button = CreateFrame("Button", nil, bar)
    button:SetSize(TITLE_BUTTON_SIZE, TITLE_BUTTON_SIZE)
    button:SetPoint("LEFT", bar, "LEFT", xOffset, 0)
    button:RegisterForClicks("LeftButtonUp")
    button:SetScript("OnClick", onClick)
    button.tooltip = tooltip
    button.color = color

    local icon = button:CreateTexture(nil, "ARTWORK")
    icon:SetTexture(glyph)
    icon:SetAllPoints(button)
    icon:SetVertexColor(color[1], color[2], color[3], TITLE_BUTTON_ALPHA)
    button.icon = icon

    button:SetScript("OnEnter", function(self)
        self.icon:SetVertexColor(color[1], color[2], color[3], TITLE_BUTTON_ALPHA_HOVER)
        local text = Chat.ResolveTermBarTooltip(self.tooltip)
        if text and GameTooltip then
            GameTooltip:SetOwner(self, "ANCHOR_NONE")
            GameTooltip:SetText(text, color[1], color[2], color[3])
            Chat.PlaceTermBarTooltip(self)
            GameTooltip:Show()
        end
    end)
    button:SetScript("OnLeave", function(self)
        self.icon:SetVertexColor(color[1], color[2], color[3], TITLE_BUTTON_ALPHA)
        if GameTooltip then GameTooltip:Hide() end
    end)
    return button
end

-- Builds the mock's .termbar strip: pink + green status dots and a cyan mono
-- title. Parented to UIParent for the same reason as the tab strip below it --
-- it is the terminal's chrome, not one window's -- and seated onto the selected
-- window by SeatTerminalChrome. Purely decorative (no reparenting or resizing
-- of any chat frame), so it never touches combat-relevant state.
function Chat.BuildTermBar()
    if Chat.termBar then return end

    local bar = CreateFrame("Frame", nil, Chat.termPanel)
    bar:SetHeight(Chat.TERM_BAR_HEIGHT)

    -- The bar itself, which is what makes the title read as a title bar rather
    -- than as text lying on the panel. BACKGROUND so the dots and the label
    -- (both ARTWORK) stay in front of it.
    local wash = bar:CreateTexture(nil, "BACKGROUND")
    wash:SetAllPoints(bar)
    wash:SetColorTexture(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], TERM_BAR_WASH)
    bar.wash = wash

    -- Closes the band at the bottom, the way the tab strip is already closed
    -- by its own 22% rule. Brighter than that one on purpose: the mock puts 30%
    -- here and 22% there, so the header reads as the stronger division.
    local rule = bar:CreateTexture(nil, "ARTWORK")
    rule:SetColorTexture(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], TERM_BAR_RULE)
    rule:SetPoint("BOTTOMLEFT", bar, "BOTTOMLEFT", 0, 0)
    rule:SetPoint("BOTTOMRIGHT", bar, "BOTTOMRIGHT", 0, 0)
    rule:SetHeight(1)
    bar.rule = rule

    -- Both buttons captured so ApplyWindowState can find whichever one the
    -- tooltip is currently anchored to and refresh its text in place: a click
    -- while hovering changes windowState but does not re-fire OnEnter.
    Chat.minimiseButton = AddTermBarButton(bar, COLOR_HEALTH, 6, ICON_MINIMIZE_TEXTURE,
        function() Chat.ToggleWindowState("min") end,
        function() return (Chat.windowState == "min") and "Normal" or "Minimise" end)
    -- Also captured so ApplyWindowState can rotate its glyph to read as
    -- "restore down" while maximised.
    Chat.maximiseButton = AddTermBarButton(bar, Chat.COLOR_TERM_GREEN, 26, ICON_MAXIMIZE_TEXTURE,
        function() Chat.ToggleWindowState("max") end,
        function() return (Chat.windowState == "max") and "Normal" or "Maximise" end)

    local label = bar:CreateFontString(nil, "ARTWORK")
    label:SetPoint("LEFT", bar, "LEFT", 46, 0)
    ApplyMono(label, 9, COLOR_POWER)
    -- Exact string from the mockup's terminal renderer
    -- (mockups/full-ui-layout.html: <div class="termbar">...stuwave://general).
    label:SetText("stuwave://general")

    Chat.termBar = bar
end

-- The mock's `.term .scan` scanline overlay: a tiled scrim over the message
-- area, OVERLAY layer so it sits above the message text/backdrop wash added
-- by SkinChatFrame. Purely decorative (a Texture never intercepts mouse
-- input), so scrolling/selecting chat text underneath it is unaffected.
-- Guarded by frame.fsChatScan so re-applying never stacks a second overlay.
function Chat.AddChatScanline(frame)
    if not frame or frame.fsChatScan then return end
    if not frame.CreateTexture then return end

    local scan = frame:CreateTexture(nil, "OVERLAY")
    -- REPEAT wrap lets the GPU sample past the texture's own edge; the
    -- SetTexCoord range below (in 4px tile units) is how many times it
    -- repeats across the assigned SetAllPoints size, so this tiles rather
    -- than stretches regardless of the frame's current size.
    scan:SetTexture(Chat.SCANLINE_TEXTURE, "REPEAT", "REPEAT")
    scan:SetAllPoints(frame)
    if scan.SetTexCoord then
        local h = (frame.GetHeight and frame:GetHeight()) or (Chat.SCANLINE_TILE_PX * 4)
        local w = (frame.GetWidth and frame:GetWidth()) or (Chat.SCANLINE_TILE_PX * 4)
        scan:SetTexCoord(0, w / Chat.SCANLINE_TILE_PX, 0, h / Chat.SCANLINE_TILE_PX)
    end
    scan:SetAlpha(Chat.SCANLINE_ALPHA)

    frame.fsChatScan = scan
end

-------------------------------------------------------------------------------
-- The terminal's title-bar buttons, and the scroll bar
-------------------------------------------------------------------------------

local function SkinTitleButton(button, index, iconTexture, tooltip)
    if not button then return end

    button.tooltip = tooltip

    -- NO BORDER, and none of Blizzard's art either. Parker: "We don't need the
    -- borders for these. just the icons will be fine." A box around a 16px
    -- glyph reads as a button widget, and there are already two bordered
    -- shapes in this strip (the tab pills and the social starter); a third
    -- competes with both.
    --
    -- Tinting their glyphs was tried first and only half works, because the
    -- two buttons are built differently. Measured via /fschat parts on 16001:
    --
    --   ChatFrameChannelButton  atlas regions. `chatframe-button-up` / `-down`
    --                           are the bevelled DISC and the glyph is a
    --                           separate OVERLAY (`-icon-voicechat`), so
    --                           hiding the disc leaves a clean speaker.
    --   ChatFrameMenuButton     3 ARTWORK regions, atlas=nil, plain fileIDs
    --                           (130947-9). The rounded frame is painted INTO
    --                           the glyph, so there is nothing to hide: the
    --                           box survives every tint.
    --
    -- Probed for a bare atlas variant of the bubble and this client has none
    -- (`chatframe-button-icon-` + chat / emote / menu / speech all fail to
    -- resolve), so the menu button had to be redrawn whatever we did. Redrawing
    -- only that one would leave a vector glyph beside atlas art at different
    -- weights, hence both. See media/generate_icon_chrome.py.
    for _, region in ipairs({ button:GetRegions() }) do
        if region.GetObjectType and region:GetObjectType() == "Texture" then
            region:SetTexture(nil)
            region:Hide()
        end
    end
    -- QuickJoinToastButton composes several named regions; blank the ones that
    -- are chrome and leave whatever draws the count.
    for _, key in ipairs({ "Background", "FriendsButton", "Toast", "FlashFrame" }) do
        local region = button[key]
        if region and region.SetAlpha then pcall(region.SetAlpha, region, 0) end
    end

    -- Parented to the button rather than installed as its normal texture,
    -- because a normal texture is STATE art: the engine swaps to the pushed
    -- one while the mouse is down, which would blink our glyph off on every
    -- click. An ARTWORK child is ours and stays put through all of it.
    local icon = button.fsIcon
    if not icon then
        icon = button:CreateTexture(nil, "ARTWORK")
        button.fsIcon = icon
    end
    icon:SetTexture(iconTexture)
    icon:SetAllPoints(button)
    icon:SetVertexColor(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 1)
    icon:Show()

    button:SetParent(Chat.termBar)
    button:ClearAllPoints()
    button:SetSize(TITLE_BUTTON_SIZE, TITLE_BUTTON_SIZE)
    button:SetPoint("RIGHT", Chat.termBar, "RIGHT",
        -(TITLE_BUTTON_GAP + (index - 1) * (TITLE_BUTTON_SIZE + TITLE_BUTTON_GAP)), 0)
    button:SetFrameStrata(Chat.termBar:GetFrameStrata())
    button:SetFrameLevel(Chat.termBar:GetFrameLevel() + 1)
    button:SetAlpha(TITLE_BUTTON_ALPHA)
    button:Show()

    -- HookScript, not SetScript, so Blizzard's own OnEnter/OnLeave keep running
    -- alongside ours: ChatFrameChannelButton owns a real Blizzard tooltip (its
    -- voice-chat status) that hooking must not clobber. ChatFrameMenuButton is
    -- the opposite case -- measured on this client, it has NO Blizzard tooltip
    -- handler at all, which is the bug an explicit `tooltip` param here covers.
    -- Mirrors AddTermBarButton's OnEnter/OnLeave (~line 174) in the same shape,
    -- with extra existence guards added here since this function also
    -- has to tolerate a caller passing no tooltip at all. A nil `tooltip`
    -- (the channel button, and any future entry with no label) leaves behavior
    -- identical to before this change.
    button:HookScript("OnEnter", function(self)
        self:SetAlpha(TITLE_BUTTON_ALPHA_HOVER)
        local text = Chat.ResolveTermBarTooltip and Chat.ResolveTermBarTooltip(self.tooltip)
        if text and GameTooltip then
            GameTooltip:SetOwner(self, "ANCHOR_NONE")
            GameTooltip:SetText(text, COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3])
            if Chat.PlaceTermBarTooltip then Chat.PlaceTermBarTooltip(self) end
            GameTooltip:Show()
        end
    end)
    button:HookScript("OnLeave", function(self)
        self:SetAlpha(TITLE_BUTTON_ALPHA)
        if GameTooltip then GameTooltip:Hide() end
    end)
end

function Chat.SkinTitleButtons()
    if not Chat.termBar then return end
    -- QuickJoinToastButton is NOT here any more: the social tab replaces it at
    -- the head of the tab row, and leaving both would give the same action two
    -- controls. Hidden rather than skinned.
    -- Right to left, so index 1 is the rightmost. The chat menu sits outermost
    -- the way a window's own menu control does; the channel speaker reads as
    -- content and sits inboard of it.
    local order = {
        -- "Chat Menu" wording is a placeholder Parker may retune -- he is the
        -- visual judge on label copy in this bar.
        { _G.ChatFrameMenuButton, ICON_CHAT_TEXTURE, "Chat Menu" },
        { _G.ChatFrameChannelButton, ICON_CHANNEL_TEXTURE },
    }
    local quickJoin = _G.QuickJoinToastButton
    if quickJoin then
        -- Parked ON the social tab, not merely hidden. Its OnEnter is called
        -- through on hover and anchors the tooltip to itself, so its rect has
        -- to be the tab's. Events stay registered: the tooltip content depends
        -- on the queue state it tracks.
        if Chat.socialTab then
            quickJoin:ClearAllPoints()
            quickJoin:SetAllPoints(Chat.socialTab)
        end
        quickJoin:Hide()
    end
    for i, entry in ipairs(order) do
        SkinTitleButton(entry[1], i, entry[2], entry[3])
    end

    -- The strip they came out of has nothing left to show. Its own background
    -- and border textures are Blizzard art we never wanted either.
    local strip = _G.ChatFrame1ButtonFrame
    if strip then
        if StripBlizzardChrome then pcall(StripBlizzardChrome, strip) end
        strip:SetAlpha(0)
        strip:EnableMouse(false)
    end
end

-- Re-anchors the scroll bar inside the panel. Called on every scroll, NOT once
-- at skin time, because Blizzard re-anchors it afterwards and wins.
--
-- Measured: after our skin ran, the bar reported L=596.17 against a chat frame
-- whose right edge is 596.17 -- Blizzard had pinned the bar's LEFT to the
-- frame's RIGHT, putting the whole 14px bar outside the chat frame and 4px
-- past the panel border. Our own anchor had been silently replaced.
--
-- Exactly the same shape as the FCF_SetButtonSide hook above: a single
-- placement of Blizzard chat furniture does not survive.
local function SeatScrollBar(frame)
    local bar = frame and frame.ScrollBar
    if not bar then return end
    bar:ClearAllPoints()
    bar:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -SCROLL_INSET, 0)
    bar:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -SCROLL_INSET,
        SCROLL_BAR_WIDTH + SCROLL_BOTTOM_GAP)
    bar:SetWidth(SCROLL_BAR_WIDTH)
end

-- Shows the jump button only when there is somewhere to jump BACK from.
-- Parker: "show it if there is a scroll bar etc." Blizzard drives this itself
-- in stock UI, but we re-anchor and re-skin the button, so the visibility is
-- asserted here rather than assumed -- and a button that is always on screen
-- reads as decoration, not as a control.
local function UpdateJumpButton(frame)
    SeatScrollBar(frame)

    local button = frame and frame.ScrollToBottomButton
    if not button then return end
    -- AtBottom is the honest test: "the scroll bar exists" is true whenever
    -- the buffer is longer than the window, including while you are already
    -- reading the newest line, and there is nothing to jump to then.
    local atBottom = true
    if frame.AtBottom then
        local ok, result = pcall(frame.AtBottom, frame)
        if ok then atBottom = result end
    end
    button:SetShown(not atBottom)
end

function Chat.SeatScrollFurniture(frame)
    local toBottom = frame and frame.ScrollToBottomButton
    if not toBottom then return end

    toBottom:ClearAllPoints()
    toBottom:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -SCROLL_INSET, 3)
    toBottom:SetSize(SCROLL_BAR_WIDTH, SCROLL_BAR_WIDTH)

    -- Blizzard's art is part of the `minimal-scrollbar` atlas family and goes
    -- with the rest of it, so this button needs a glyph of its own -- without
    -- one it sits there correctly positioned and completely invisible, which
    -- is how it shipped for a build.
    for _, region in ipairs({ toBottom:GetRegions() }) do
        if region.GetObjectType and region:GetObjectType() == "Texture" then
            region:SetTexture(nil)
            region:Hide()
        end
    end

    local icon = toBottom.fsIcon
    if not icon then
        icon = toBottom:CreateTexture(nil, "ARTWORK")
        toBottom.fsIcon = icon
        -- Same hover as every other control in the panel: full strength, no
        -- colour change.
        toBottom:HookScript("OnEnter", function(self)
            if self.fsIcon then self.fsIcon:SetVertexColor(1, 1, 1, 1) end
        end)
        toBottom:HookScript("OnLeave", function(self)
            if self.fsIcon then
                self.fsIcon:SetVertexColor(COLOR_HEALTH[1], COLOR_HEALTH[2],
                    COLOR_HEALTH[3], 0.9)
            end
        end)
    end
    icon:SetTexture(ICON_JUMP_TEXTURE)
    icon:SetAllPoints(toBottom)
    -- Magenta, matching the scroll thumb: both mean "you are away from the
    -- live edge", and they are the only two things in the panel that do.
    icon:SetVertexColor(COLOR_HEALTH[1], COLOR_HEALTH[2], COLOR_HEALTH[3], 0.9)
    icon:Show()

    -- Drive the visibility off every route that changes scroll position. There
    -- is no single scroll event on this client, so each mover is hooked and
    -- they all funnel into one updater.
    if not frame.fsJumpHooked then
        frame.fsJumpHooked = true
        for _, method in ipairs({ "ScrollUp", "ScrollDown", "ScrollToTop",
                                  "ScrollToBottom", "PageUp", "PageDown",
                                  "SetScrollOffset", "AddMessage" }) do
            if type(frame[method]) == "function" then
                hooksecurefunc(frame, method, function(self) UpdateJumpButton(self) end)
            end
        end
        -- The wheel does not go through those methods on every path.
        frame:HookScript("OnMouseWheel", function(self) UpdateJumpButton(self) end)
    end
    UpdateJumpButton(frame)
end

function Chat.SkinChatScrollBar(frame)
    Chat.SeatScrollFurniture(frame)

    local bar = frame and frame.ScrollBar
    if not bar or bar.fsScrollSkin then return end
    bar.fsScrollSkin = true


    -- Blizzard's art is the `minimal-scrollbar-*` atlas family, dumped with
    -- /fschat scroll on this client:
    --
    --   bar.Track (a FRAME)  track-top / -bottom / -middle
    --     .Thumb (a BUTTON)  small-thumb-top / -bottom / -middle
    --   bar.Back, bar.Forward  arrow-top / arrow-bottom
    --
    -- THE TRACK IS A FRAME AND THE THUMB LIVES INSIDE IT. The previous pass
    -- did bar.Track:SetAlpha(0) to blank the groove, which also faded the
    -- thumb to nothing, so the bar looked like it had never been skinned at
    -- all. Nothing errored and nothing drew.
    --
    -- So the strip is by ATLAS NAME over the whole subtree, never by hiding a
    -- container: any region whose atlas mentions the scrollbar is Blizzard's,
    -- and everything else is left alone. That also catches the arrows without
    -- hiding their BUTTONS -- the track is anchored between them, and hiding
    -- the buttons themselves would leave the groove spanning the wrong rect.
    local function StripScrollAtlases(obj)
        for _, region in ipairs({ obj:GetRegions() }) do
            if region.GetObjectType and region:GetObjectType() == "Texture" then
                local atlas = region.GetAtlas and region:GetAtlas()
                if atlas and atlas:lower():find("scrollbar") then
                    region:SetTexture(nil)
                    region:Hide()
                end
            end
        end
        for i = 1, select("#", obj:GetChildren()) do
            StripScrollAtlases((select(i, obj:GetChildren())))
        end
    end
    StripScrollAtlases(bar)

    -- The steppers keep their rect (the track measures against them) but stop
    -- taking clicks, because there is no longer anything there to click.
    for _, key in ipairs({ "Back", "Forward" }) do
        local stepper = bar[key]
        if stepper and stepper.EnableMouse then pcall(stepper.EnableMouse, stepper, false) end
    end

    -- The groove: one dim cyan line down the whole bar. media/scroll_rail.tga
    -- varies only ACROSS its width, so stretching it to any height is exact.
    if not bar.fsRail then
        local rail = bar:CreateTexture(nil, "BACKGROUND")
        rail:SetTexture(SCROLL_RAIL_TEXTURE)
        rail:SetPoint("TOPLEFT", bar, "TOPLEFT", 0, 0)
        rail:SetPoint("BOTTOMRIGHT", bar, "BOTTOMRIGHT", 0, 0)
        rail:SetVertexColor(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], SCROLL_RAIL_ALPHA)
        bar.fsRail = rail
    end

    -- The slider: the same light in magenta at full strength, so it reads as
    -- the active thing in the groove exactly the way the live tab reads
    -- against the idle ones.
    SeatScrollBar(frame)
    bar:HookScript("OnShow", function() SeatScrollBar(frame) end)

    local thumb = (bar.Track and bar.Track.Thumb) or bar.Thumb
    if thumb and not thumb.fsThumb then
        local fill = thumb:CreateTexture(nil, "ARTWORK")
        fill:SetTexture(SCROLL_RAIL_TEXTURE)
        -- Vertically from the THUMB, horizontally from the BAR. The thumb
        -- keeps whatever width Blizzard's atlas gave it (8 here) regardless of
        -- how wide the bar is set, so anchoring all four edges to the thumb
        -- would pin the slider to that 8 and it would stop matching the groove
        -- the moment SCROLL_BAR_WIDTH changed. Split this way, the slider is
        -- always exactly as wide as its rail and still tracks the thumb's
        -- position and length.
        fill:SetPoint("LEFT", bar, "LEFT", 0, 0)
        fill:SetPoint("RIGHT", bar, "RIGHT", 0, 0)
        fill:SetPoint("TOP", thumb, "TOP", 0, 0)
        fill:SetPoint("BOTTOM", thumb, "BOTTOM", 0, 0)
        fill:SetVertexColor(COLOR_HEALTH[1], COLOR_HEALTH[2], COLOR_HEALTH[3], SCROLL_THUMB_ALPHA)
        thumb.fsThumb = fill

        -- Hover, matching every other control in this panel: the colour does
        -- not change, it just comes up to full.
        thumb:HookScript("OnEnter", function(self)
            if self.fsThumb then self.fsThumb:SetVertexColor(1, 1, 1, 1) end
        end)
        thumb:HookScript("OnLeave", function(self)
            if self.fsThumb then
                self.fsThumb:SetVertexColor(COLOR_HEALTH[1], COLOR_HEALTH[2],
                    COLOR_HEALTH[3], SCROLL_THUMB_ALPHA)
            end
        end)
    end
end
